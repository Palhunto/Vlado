"""Mandatory workflow and canonical database publication; synthetic agent only."""
import json
from unittest.mock import patch
import unittest

import test_codex_integracao as fixture
from agente_fluxo_fixture import aguardar_fim, entrega, esperar, completar
from comum import ler_json, sha256
from indice_achados import catalogo, consultar, verificar


class FluxoAutomaticoTest(unittest.TestCase):
    start = fixture.CodexIntegrationTest.start

    def setUp(self):
        # The fixture runs on this test, so its cleanups (threads, manager, temporary folder)
        # are registered here and their errors are reported, as in ContinuarDocumentosTest.
        fixture.CodexIntegrationTest.setUp(self)
        self.fx = self
        self.identifier = self.fx.start()
        self.ctx = self.manager.contexts[self.identifier]
        self.refs = {}

    def tool(self, args):
        return self.manager.ferramenta(self.identifier, args)[0]

    def wait_stage(self, stage, attempt=1):
        esperar(lambda: self.manager.eventos(self.identifier)['conversa'].get('etapa') == stage
                and self.ctx['meta'].get('tentativa_etapa') == attempt and self.ctx['meta'].get('turn_id'))

    def end(self):
        turn = self.ctx['meta']['turn_id']
        self.manager.rpc.emit('item/completed', {'item': {'id': 'raw-' + turn,
            'type': 'agentMessage', 'phase': 'final_answer', 'text': 'Mensagem provisória da fixture.'}})
        self.manager.rpc.emit('turn/completed', {'turn': {'id': turn, 'status': 'completed'}})

    def step(self, stage, payload=None):
        self.wait_stage(stage)
        raw = entrega(stage, self.tool, self.refs) if payload is None else payload
        self.tool({'acao': 'guardar', 'etapa': stage, 'texto': raw if isinstance(raw, str) else json.dumps(raw)})
        self.end()

    def through(self, stage):
        for name in ('inventario', 'plano', 'busca', 'geracao_inicial', 'revisao', 'sintese'):
            self.step(name)
            if name == stage:
                return

    def terminal(self):
        aguardar_fim(self.manager, self.identifier)

    def test_complemento_publica_e_verifica_banco_sem_alterar_primeira_rodada(self):
        completar(self.manager, self.identifier)
        first = self.ctx['run']
        hashes = {str(p.relative_to(first)): sha256(p) for p in first.rglob('*') if p.is_file()}
        self.manager.rpc.ready.clear()
        self.fx.start(conversa=self.identifier, pergunta='Complemento técnico sintético.')
        completar(self.manager, self.identifier)
        self.assertEqual(self.ctx['meta']['rodadas'], ['R001', 'R002'])
        for run in ('R001', 'R002'):
            report = ler_json(self.root / f'execucoes/alpha/{run}/saidas/codex_execucao.json')
            self.assertEqual(report['estado'], 'concluido')
            self.assertEqual(report['etapas_sem_registro'], [])
            self.assertEqual(report['publicacao_achados']['estado'], 'verificado')
            self.assertEqual(catalogo(self.root, 'alpha', run)['revisoes'], ['r1_busca', 'r2_revisao', 'r3_sintese'])
            self.assertEqual(verificar(self.root, 'alpha', run, 'r3_sintese', 'g1')['achados'], 1)
            data = consultar(self.root, 'alpha', run, 'r3_sintese', 'g1')
            self.assertTrue(data)
        self.assertTrue(all(sha256(first / p) == digest for p, digest in hashes.items()))
        events = self.ctx['events']
        self.assertEqual(sum(e['tipo'] == 'pergunta' for e in events), 2)
        self.assertEqual(sum(e['tipo'] == 'publicacao' for e in events), 2)

    def test_resposta_sem_entrega_tenta_corrigir_e_nunca_conclui_silenciosamente(self):
        self.wait_stage('inventario')
        self.end()
        self.wait_stage('inventario', 2)
        self.assertIn('sem uma entrega validada', self.manager.rpc.calls[-1][1]['input'][0]['text'])
        self.end()
        self.terminal()
        self.assertEqual(self.ctx['meta']['estado'], 'incompleto')
        self.assertEqual(catalogo(self.root, 'alpha', 'R001')['estado'], 'nao_produzidos')
        self.assertFalse(any(e['tipo'] == 'resposta' and e['dados'].get('publicada') for e in self.ctx['events']))
        self.assertEqual(sum(m == 'turn/start' for m, _ in self.manager.rpc.calls), 2)

    def test_geracao_invalida_preservada_e_corrigida_na_mesma_rodada(self):
        self.through('busca')
        self.wait_stage('geracao_inicial')
        correct = entrega('geracao_inicial', self.tool, self.refs)
        invalid = json.loads(correct)
        invalid['achados'][0]['evidencias'][0]['trecho'] = 'Trecho inexistente na fonte.'
        with self.assertRaisesRegex(ValueError, 'Trecho literal'):
            self.tool({'acao': 'guardar', 'etapa': 'geracao_inicial', 'texto': json.dumps(invalid)})
        self.assertEqual(catalogo(self.root, 'alpha', 'R001')['revisoes'], [])
        self.end()
        self.wait_stage('geracao_inicial', 2)
        self.tool({'acao': 'guardar', 'etapa': 'geracao_inicial', 'texto': correct})
        self.end()
        self.step('revisao'); self.step('sintese'); self.terminal()
        self.assertEqual(self.ctx['meta']['estado'], 'concluido')
        self.assertEqual(self.ctx['meta']['rodadas'], ['R001'])
        self.assertEqual(len(list((self.ctx['run'] / 'saidas').glob('codex_tentativa_geracao_inicial_*.json'))), 2)

    def test_revisao_exige_fonte_reaberta_e_recusa_aprovacao_humana_inventada(self):
        self.through('geracao_inicial')
        self.wait_stage('revisao')
        payload = {'texto': 'Revisão', 'revisoes': [{'achado_id': 'A001', 'suporte': 'sustentado',
                   'motivo': 'Fixture', 'limitacoes': 'Fixture', 'acao': 'manter'}]}
        with self.assertRaisesRegex(ValueError, 'Reabra'):
            self.tool({'acao': 'guardar', 'etapa': 'revisao', 'texto': json.dumps(payload)})
        payload['conferencias_humanas'] = [{'aprovado': True}]
        with self.assertRaisesRegex(ValueError, 'Campos não autorizados'):
            self.tool({'acao': 'guardar', 'etapa': 'revisao', 'texto': json.dumps(payload)})
        self.assertEqual(catalogo(self.root, 'alpha', 'R001')['revisoes'], ['r1_busca'])
        self.manager.cancelar(self.identifier); self.terminal()

    def test_sintese_nao_promove_suporte_parcial(self):
        self.through('geracao_inicial'); self.wait_stage('revisao')
        raw = json.loads(entrega('revisao', self.tool, self.refs))
        raw['revisoes'][0].update(suporte='parcial', acao='pendencia')
        self.step('revisao', raw)
        self.wait_stage('sintese')
        with self.assertRaisesRegex(ValueError, 'última revisão sustentado'):
            self.tool({'acao': 'guardar', 'etapa': 'sintese', 'texto': entrega('sintese', self.tool, self.refs)})
        self.step('sintese', {'texto': 'Insuficiência de suporte para apresentar o achado como sustentado.',
            'destinos': [{'achado_id': 'A001', 'destino': 'pendencia', 'motivo': 'Suporte parcial.'}]})
        self.terminal()
        self.assertEqual(self.ctx['meta']['estado'], 'concluido')
        self.assertIsNotNone(self.ctx['pipeline'].publication)

    def test_falha_indexacao_recusa_conclusao_e_preserva_revisoes(self):
        with patch('fluxo_codex.indice_achados.construir', side_effect=OSError('Fixture: falha de disco')) as build:
            completar(self.manager, self.identifier)
        self.assertEqual(self.ctx['meta']['estado'], 'erro')
        self.assertEqual(build.call_count, 2)
        self.assertEqual(catalogo(self.root, 'alpha', 'R001')['revisoes'], ['r1_busca', 'r2_revisao', 'r3_sintese'])
        self.assertFalse(any(e['tipo'] == 'publicacao' for e in self.ctx['events']))
        self.assertFalse(any(e['tipo'] == 'resposta' and e['dados'].get('publicada') for e in self.ctx['events']))

    def test_finalizacao_idempotente_nao_duplica_revisoes_nem_indices(self):
        completar(self.manager, self.identifier)
        path = self.ctx['run'] / 'saidas/achados/indices/g1/achados.sqlite'
        digest = sha256(path)
        first = self.ctx['pipeline'].finalize()
        self.assertEqual(first, self.ctx['pipeline'].finalize())
        self.assertEqual(sha256(path), digest)
        self.assertEqual(len(catalogo(self.root, 'alpha', 'R001')['indices']), 1)

    def test_erro_de_busca_nao_e_aceito_como_busca_sem_resultados(self):
        self.through('plano'); self.wait_stage('busca')
        result = self.tool({'acao': 'buscar', 'consulta': '"aspa aberta', 'modo': 'fts'})
        self.assertEqual(result['estado'], 'erro_consulta')
        with self.assertRaisesRegex(ValueError, 'ao menos uma busca real'):
            self.tool({'acao': 'guardar', 'etapa': 'busca', 'texto': 'Relatório da tentativa com erro.'})
        self.manager.cancelar(self.identifier); self.terminal()

    def test_insuficiencia_publica_conjunto_vazio_revisado(self):
        self.through('busca')
        self.step('geracao_inicial', {'texto': 'Sem achados com suporte para a pergunta sintética.', 'achados': []})
        self.step('revisao', {'texto': 'Insuficiência revisada pela IA, sem fontes adicionais.', 'revisoes': []})
        self.step('sintese', {'texto': 'Insuficiência de evidências para responder à pergunta.', 'destinos': []})
        self.terminal()
        self.assertEqual(self.ctx['meta']['estado'], 'concluido')
        self.assertEqual(verificar(self.root, 'alpha', 'R001', 'r3_sintese', 'g1')['achados'], 0)

    def test_correcao_cria_versao_e_revisao_proprias(self):
        self.through('geracao_inicial'); self.wait_stage('revisao')
        raw = json.loads(entrega('revisao', self.tool, self.refs))
        raw['revisoes'][0].update(suporte='parcial', acao='corrigir', correcao={
            'redacao': 'A fonte declara, no teste sintético, o valor 123.', 'natureza': 'alegacao_atribuida',
            'limitacoes': 'Declaração sintética.', 'suporte': 'sustentado', 'motivo': 'A nova redação mantém a atribuição.'})
        self.step('revisao', raw)
        self.step('sintese', {'texto': '[A001@v2] A fonte declara o valor 123. [fonte:' + self.refs['hit']['referencia'] + ']',
            'destinos': [{'achado_id': 'A001', 'destino': 'incluido', 'motivo': 'Versão corrigida revisada.'}]})
        self.terminal()
        from registros_achados import carregar
        initial, _ = carregar(self.root, 'alpha', 'R001', 'r1_busca')
        final, _ = carregar(self.root, 'alpha', 'R001', 'r3_sintese')
        self.assertEqual(len(initial['achados'][0]['versoes']), 1)
        self.assertEqual(len(final['achados'][0]['versoes']), 2)
        self.assertEqual([(r['versao'], r['suporte']) for r in final['revisoes_assistidas']], [(1, 'parcial'), (2, 'sustentado')])
        self.assertEqual(final['conferencias_humanas'], [])

    def test_evidencia_adicional_preserva_relatorios_iniciais(self):
        self.through('geracao_inicial'); self.wait_stage('revisao')
        from registros_achados import carregar
        initial, _ = carregar(self.root, 'alpha', 'R001', 'r1_busca')
        raw = json.loads(entrega('revisao', self.tool, self.refs))
        extra = json.loads(entrega('geracao_inicial', self.tool, self.refs))['achados'][0]['evidencias'][0]
        extra.update(trecho=self.refs['hit']['trecho'].splitlines()[1], papel='contexto', justificativa='Conteúdo estranho permanece dado, sem execução.')
        raw['revisoes'][0]['evidencias_adicionais'] = [extra]
        self.step('revisao', raw); self.step('sintese'); self.terminal()
        final, _ = carregar(self.root, 'alpha', 'R001', 'r3_sintese')
        self.assertEqual(len(final['evidencias']), 2)
        self.assertEqual(final['evidencias'][0], initial['evidencias'][0])
        self.assertEqual(final['artefatos'][:len(initial['artefatos'])], initial['artefatos'])
