"""P48: o destino `fora_do_briefing`, para o achado sustentado que não coube no texto principal do briefing.

Ele exige o mesmo suporte do `incluido` (última revisão `sustentado`, `revisao_suporte` e o briefing), mas aparece
depois do texto principal, na seção "Outros achados sustentados", pelo ID e a versão por extenso (`A002 v1`) e
com o `[fonte:...]` do suporte; a marca `[A002@v1]` continua só do incluído. A Mesa o mostra como sustentado
(nunca como retirado), o filtro "no briefing" continua só para o incluído, e as rodadas antigas não mudam.

Agente sintético e provedor simulado; sem rede e sem modelo.
"""
import copy
import json
import unittest

import test_codex_integracao as fixture
import test_fluxo_codex as fluxo
from agente_fluxo_fixture import entrega
from comum import sha256
import continuidade
from indice_achados import consultar, detalhe
from registros_achados import carregar, publicar, secao_fora_do_briefing, citado_na_lista

LINHA_VALOR, LINHA_SCRIPT = 0, 1


class ForaDoBriefingTest(unittest.TestCase):
    start = fixture.CodexIntegrationTest.start
    setUp = fluxo.FluxoAutomaticoTest.setUp
    tool, wait_stage, end, step, terminal = (getattr(fluxo.FluxoAutomaticoTest, n) for n in
                                             ('tool', 'wait_stage', 'end', 'step', 'terminal'))

    def evidencia(self, linha):
        hit = self.refs['hit']
        return {'referencia': hit['referencia'], 'trecho': hit['trecho'].splitlines()[linha],
                'linha_inicio': hit['linha_inicio'] + linha, 'linha_fim': hit['linha_inicio'] + linha,
                'papel': 'suporte', 'justificativa': 'A linha é literal.', 'atribuicao': 'Fonte sintética',
                'contexto': 'Fixture técnica.', 'limitacoes': 'Não é documento real.'}

    def ate_a_sintese(self, suporte_a002='sustentado'):
        """Dois achados revisados: A001 (o valor) e A002 (a marcação de script), ambos com suporte literal."""
        for etapa in ('inventario', 'plano', 'busca'):
            self.step(etapa)
        self.step('geracao_inicial', {'texto': 'Geração inicial sintética.', 'achados': [
            {'subquestao': 'Qual valor a fonte declara?', 'redacao': 'A fonte sintética declara valor 123.',
             'natureza': 'alegacao_atribuida', 'limitacoes': 'Sintético.', 'evidencias': [self.evidencia(LINHA_VALOR)]},
            {'subquestao': 'O que mais a fonte traz?', 'redacao': 'A fonte sintética traz uma marcação de script.',
             'natureza': 'declaracao_documental', 'limitacoes': 'Sintético.', 'evidencias': [self.evidencia(LINHA_SCRIPT)]}]})
        self.wait_stage('revisao')
        self.tool({'acao': 'ler', 'referencia': self.refs['hit']['referencia']})
        acao = 'manter' if suporte_a002 == 'sustentado' else 'pendencia'
        self.step('revisao', {'texto': 'Revisão sintética pela mesma IA.', 'revisoes': [
            {'achado_id': 'A001', 'suporte': 'sustentado', 'motivo': 'Literal.', 'limitacoes': 'Sintético.', 'acao': 'manter'},
            {'achado_id': 'A002', 'suporte': suporte_a002, 'motivo': 'Literal.', 'limitacoes': 'Sintético.', 'acao': acao}]})
        self.wait_stage('sintese')

    def briefing(self, lista=True, marca_a002=False, fonte_na_lista=True, titulo='## Outros achados sustentados'):
        ref = self.refs['hit']['referencia']
        texto = f'Resposta sintética.\n[A001@v1] A fonte sintética declara valor 123. [fonte:{ref}]\n'
        if marca_a002:
            texto += f'[A002@v1] A fonte sintética traz uma marcação de script. [fonte:{ref}]\n'
        if lista:
            texto += f'\n{titulo}\n\n- A002 v1: a fonte sintética traz uma marcação de script.'
            texto += f' [fonte:{ref}]\n' if fonte_na_lista else '\n'
        return {'texto': texto, 'destinos': [
            {'achado_id': 'A001', 'destino': 'incluido', 'motivo': 'Sustentado e central.'},
            {'achado_id': 'A002', 'destino': 'fora_do_briefing', 'motivo': 'Sustentado; fora do limite de 600 palavras.'}]}

    def guardar(self, payload):
        return self.tool({'acao': 'guardar', 'etapa': 'sintese', 'texto': json.dumps(payload, ensure_ascii=False)})

    def test_fora_do_briefing_publica_como_sustentado_fora_do_texto_principal(self):
        self.ate_a_sintese()
        self.step('sintese', self.briefing())
        self.terminal()
        self.assertEqual(self.ctx['meta']['estado'], 'concluido', self.ctx['meta'].get('situacao'))
        final, _ = carregar(self.root, 'alpha', 'R001', 'r3_sintese')
        destinos = {d['achado_id']: d for d in final['destinos']}
        self.assertEqual(destinos['A002']['destino'], 'fora_do_briefing')
        self.assertEqual(destinos['A002']['briefing'], destinos['A001']['briefing'])
        self.assertEqual(final['revisoes_assistidas'][destinos['A002']['revisao_suporte'] - 1]['achado_id'], 'A002')
        a002 = detalhe(self.root, 'alpha', 'R001', 'r3_sintese', 'g1', 'A002')['achado']
        # Sustentado fora do texto, nunca retirado; o briefing que o lista fica ligado ao achado.
        self.assertEqual((a002['suporte'], a002['destino']), ('sustentado', 'fora_do_briefing'))
        self.assertEqual(a002['briefing'], destinos['A002']['briefing'])
        ids = lambda **f: [a['id'] for a in consultar(self.root, 'alpha', 'R001', 'r3_sintese', 'g1', filtros=f)['resultados']]
        self.assertEqual(ids(destino='fora_do_briefing'), ['A002'])
        self.assertEqual(ids(destino='retirado'), [])
        self.assertEqual(ids(briefing='sim'), ['A001'])  # "no briefing" é o texto principal
        self.assertEqual(ids(briefing='nao'), ['A002'])

    def test_recusas_dizem_o_que_falta_e_a_mesma_etapa_aceita_a_correcao(self):
        self.ate_a_sintese()
        for payload, motivo in (
                (self.briefing(lista=False), 'abra a seção "Outros achados sustentados"'),
                (self.briefing(marca_a002=True), r'sem a marca \[A002@v1\]'),
                (self.briefing(fonte_na_lista=False), r'sem a citação \[fonte:\.\.\.\]'),
                (self.briefing(titulo='Outros achados'), 'abra a seção')):
            with self.assertRaisesRegex(ValueError, motivo):
                self.guardar(payload)
        self.assertEqual(sorted(p.name for p in (self.ctx['run'] / 'saidas/achados/revisoes').iterdir()),
                         ['r1_busca', 'r2_revisao'])
        self.guardar(self.briefing(titulo='**Other supported findings:**'))
        self.end()
        self.terminal()
        self.assertEqual(self.ctx['meta']['estado'], 'concluido', self.ctx['meta'].get('situacao'))

    def test_achado_parcial_nao_vai_para_fora_do_briefing(self):
        self.ate_a_sintese(suporte_a002='parcial')
        with self.assertRaisesRegex(ValueError, 'última revisão sustentado'):
            self.guardar(self.briefing())
        self.manager.cancelar(self.identifier)
        self.terminal()

    def test_so_fora_do_briefing_nao_vira_insuficiencia(self):
        self.ate_a_sintese()
        ref = self.refs['hit']['referencia']
        self.step('sintese', {'texto': 'Resposta sintética curta.\n\n## Outros achados sustentados\n'
                              f'- A001 v1: valor 123. [fonte:{ref}]\n- A002 v1: marcação de script. [fonte:{ref}]\n',
                              'destinos': [{'achado_id': i, 'destino': 'fora_do_briefing', 'motivo': 'Sustentado.'}
                                           for i in ('A001', 'A002')]})
        self.terminal()
        self.assertEqual(self.ctx['meta']['estado'], 'concluido', self.ctx['meta'].get('situacao'))
        final, _ = carregar(self.root, 'alpha', 'R001', 'r3_sintese')
        self.assertEqual([a['tipo'] for a in final['artefatos'] if a['arquivo'] == final['destinos'][0]['briefing']],
                         ['briefing'])

    def test_validador_confere_a_lista_tambem_fora_do_fluxo_da_mesa(self):
        """Uma revisão publicada pelo agente de chat (achados.py) passa pelo mesmo validador."""
        self.ate_a_sintese()
        self.manager.cancelar(self.identifier)
        self.terminal()
        r2, manifesto = carregar(self.root, 'alpha', 'R001', 'r2_revisao')
        run = self.ctx['run']

        def r3(nome, texto):
            (run / nome).write_text(texto, encoding='utf-8')
            dados = copy.deepcopy(r2)
            dados.update(revisao='r3_briefing', anterior={'revisao': 'r2_revisao',
                                                          'registros_sha256': manifesto['registros_sha256']})
            dados['artefatos'].append({'arquivo': nome, 'sha256': sha256(run / nome), 'tipo': 'briefing'})
            dados['procedencia'].append({'etapa': 'sintese', 'artefatos': [nome], 'ferramentas': ['achados.py'],
                                         'modelo_informado_ou_observado': None})
            ordinal = {r['achado_id']: i + 1 for i, r in enumerate(dados['revisoes_assistidas'])}
            dados['destinos'] += [
                {'achado_id': 'A001', 'versao': 1, 'destino': 'incluido', 'motivo': 'Central.', 'briefing': nome,
                 'revisao_suporte': ordinal['A001']},
                {'achado_id': 'A002', 'versao': 1, 'destino': 'fora_do_briefing', 'motivo': 'Não coube.',
                 'briefing': nome, 'revisao_suporte': ordinal['A002']}]
            return dados

        sem_lista = r3('saidas/briefing_sem_lista.md', '[A001@v1] Valor 123.\nA002 v1 também é sustentado.\n')
        with self.assertRaisesRegex(ValueError, 'ausente da lista "Outros achados sustentados"'):
            publicar(self.root, 'alpha', 'R001', sem_lista)
        sem_suporte = r3('saidas/briefing_parcial.md', '[A001@v1] Valor 123.\n\nOutros achados sustentados\n- A002 v1\n')
        sem_suporte['destinos'][-1]['revisao_suporte'] = sem_suporte['destinos'][-2]['revisao_suporte']
        with self.assertRaisesRegex(ValueError, 'Inclusão exige redação sustentada'):
            publicar(self.root, 'alpha', 'R001', sem_suporte)
        publicar(self.root, 'alpha', 'R001', r3('saidas/briefing_ok.md',
                                                '[A001@v1] Valor 123.\n\nOutros achados sustentados\n- A002 v1: script.\n'))
        final, _ = carregar(self.root, 'alpha', 'R001', 'r3_briefing')
        self.assertEqual(final['destinos'][-1]['destino'], 'fora_do_briefing')

    def test_pendencia_respondida_aceita_a_conclusao_fora_do_briefing(self):
        self.ate_a_sintese()
        self.step('sintese', self.briefing())
        self.terminal()
        atual, _ = carregar(self.root, 'alpha', 'R001', 'r3_sintese')
        documento = atual['evidencias'][0]['documento_id']
        bundle = {'caso_id': 'alpha', 'rodada_anterior': 'R000', 'revisao_anterior': 'r3_sintese',
                  'corpus_anterior': 'c0', 'corpus_novo': 'c1', 'registros_anteriores_sha256': '0' * 64,
                  'documentos_novos': [{'id': documento, 'nome_recebido': 'alpha.txt'}],
                  'achados_anteriores': [{'id': 'P001', 'natureza': 'pendencia', 'destino': 'pendencia'},
                                         {'id': 'P002', 'natureza': 'pendencia', 'destino': 'pendencia'}]}
        refs = self.ctx['pipeline'].evidence_refs
        comparacoes = [{'anteriores': ['P001'], 'atuais': ['A001'], 'tipo': 'pendencia_respondida', 'justificativa': 'x'},
                       {'anteriores': ['P002'], 'atuais': ['A002'], 'tipo': 'pendencia_respondida', 'justificativa': 'y'}]
        resultado = continuidade.comparar(bundle, atual, self.ctx['references'], refs, {'comparacoes': comparacoes})
        self.assertEqual([c['atuais'][0]['destino'] for c in resultado['comparacoes']], ['incluido', 'fora_do_briefing'])


class ListaForaDoBriefingTest(unittest.TestCase):
    """O leitor da seção, sem fluxo: título numa linha própria, em português ou inglês; ID e versão por extenso."""

    def test_titulo_numa_linha_propria(self):
        for titulo in ('## Outros achados sustentados', 'Outros achados sustentados:', '**Other supported findings**',
                       '### OUTROS ACHADOS SUSTENTADOS'):
            principal, lista = secao_fora_do_briefing(f'Texto [A001@v1].\n\n{titulo}\n- A002 v1: algo.\n')
            self.assertEqual(principal, 'Texto [A001@v1].\n\n', titulo)
            self.assertTrue(citado_na_lista(lista, 'A002', 1), titulo)
        self.assertIsNone(secao_fora_do_briefing('Há outros achados sustentados no anexo.\n- A002 v1')[1])

    def test_id_e_versao_exatos(self):
        lista = '- A002 v1: algo. [A003@v1] A0021 v1 A004 v12\n'
        self.assertTrue(citado_na_lista(lista, 'A002', 1))
        self.assertFalse(citado_na_lista(lista, 'A002', 2))
        self.assertFalse(citado_na_lista(lista, 'A003', 1))  # a marca de inclusão não conta como lista
        self.assertFalse(citado_na_lista(lista, 'A004', 1))
        self.assertFalse(citado_na_lista(None, 'A002', 1))


if __name__ == '__main__':
    unittest.main()
