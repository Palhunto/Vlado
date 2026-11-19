"""Failure states and retry of the same frozen round; fake provider, no model calls or keys."""
import json
from pathlib import Path
import unittest

import test_codex_integracao as fixture
import test_inferencia_api as api
from agente_fluxo_fixture import aguardar_fim, aguardar_threads, encerrar_gerenciador, entrega, esperar
from codex_apuracao import Conversas, classificar_erro, retomavel
from comum import escrever_json, ler_json
from inferencia_api import ErroIA, Resposta, ServidorAPI

ETAPAS = ('inventario', 'plano', 'busca', 'geracao_inicial', 'revisao', 'sintese')


class Base(unittest.TestCase):
    start = fixture.CodexIntegrationTest.start

    def setUp(self):
        # The fixture runs on this test, so its cleanups (threads, manager, temporary folder)
        # are registered here and their errors are reported, as in ContinuarDocumentosTest.
        fixture.CodexIntegrationTest.setUp(self)
        self.fx = self
        self.refs = {}

    def estado(self, manager, identifier):
        return manager.eventos(identifier)['conversa']

    def etapa(self, manager, identifier, stage, entregar=True, encerrar=True):
        """Drive one stage like the model would: wait for its turn, deliver, end the turn."""
        ctx = manager.contexts[identifier]
        esperar(lambda: ctx['meta'].get('etapa') == stage and ctx['meta'].get('turn_id'))
        if not entregar:
            return
        tool = lambda args: manager.ferramenta(identifier, args)[0]
        if stage not in ('inventario', 'plano', 'busca') and 'hit' not in self.refs:
            self.refs['hit'] = next(iter(ctx['references'].values()))
        raw = entrega(stage, tool, self.refs)
        tool({'acao': 'guardar', 'etapa': stage, 'texto': raw})
        if encerrar:
            turn = ctx['meta']['turn_id']
            manager.rpc.emit('turn/completed', {'turn': {'id': turn, 'status': 'completed'}})

    def completar_de(self, manager, identifier, primeira):
        for stage in ETAPAS[ETAPAS.index(primeira):]:
            self.etapa(manager, identifier, stage)
        aguardar_fim(manager, identifier)

    def travar_como_queda(self, manager, identifier):
        """Simulates a crash: the worker stops and nothing is recorded, as if the process died."""
        manager.contexts[identifier]['busy'] = False
        aguardar_threads(manager)  # the stopped worker returns without writing anything

    def novo_backend(self):
        novo = Conversas(self.root, fixture.FakeServer)
        self.addCleanup(encerrar_gerenciador, novo)
        return novo

    def revisoes(self, identifier):
        run = self.manager.contexts[identifier]['run']
        return sorted(p.name for p in (run / 'saidas/achados/revisoes').iterdir())


class QuedaEReinicioTest(Base):
    def test_queda_no_meio_da_etapa_retoma_a_mesma_rodada_sem_duplicar(self):
        identifier = self.fx.start()
        for stage in ('inventario', 'plano', 'busca', 'geracao_inicial'):
            self.etapa(self.manager, identifier, stage)
        self.etapa(self.manager, identifier, 'revisao', entregar=False)
        run = self.manager.contexts[identifier]['run']
        antes = sorted(p.name for p in (run / 'saidas').glob('codex_*'))
        self.travar_como_queda(self.manager, identifier)

        novo = self.novo_backend()
        conversa = self.estado(novo, identifier)
        self.assertEqual(conversa['estado'], 'interrompido')
        self.assertEqual((conversa['situacao']['codigo'], conversa['situacao']['causa']), ('interrompido', 'reinicio'))
        self.assertTrue(conversa['retomavel'])
        self.assertEqual(conversa['progresso']['aceitas'], list(ETAPAS[:4]))
        self.assertEqual(conversa['progresso']['proxima'], 'revisao')
        self.assertEqual(novo.listar('alpha')['conversas'][0]['pergunta'], 'Pergunta técnica sintética.')
        self.assertTrue(novo.listar('alpha')['conversas'][0]['retomavel'])

        resposta = novo.retomar(identifier)
        self.assertEqual((resposta['conversa'], resposta['retomada_da_etapa']), (identifier, 'revisao'))
        self.completar_de(novo, identifier, 'revisao')

        meta = novo.contexts[identifier]['meta']
        self.assertEqual((meta['estado'], meta['rodadas'], meta['situacao']['codigo']), ('concluido', ['R001'], 'concluido'))
        self.assertEqual(sorted(p.name for p in (self.root / 'execucoes/alpha').iterdir()), ['R001'])
        self.assertEqual(self.revisoes(identifier), ['r1_busca', 'r2_revisao', 'r3_sintese'])
        for nome in antes:  # earlier artifacts are reused, never rewritten or removed
            self.assertTrue((run / 'saidas' / nome).exists())
        retomada = [e for e in novo.eventos(identifier)['eventos'] if e['tipo'] == 'retomada']
        self.assertEqual([(e['dados']['etapa'], e['dados']['etapas_aceitas']) for e in retomada],
                         [('revisao', list(ETAPAS[:4]))])
        self.assertTrue(any(m == 'thread/resume' and p['threadId'] == 'thread-fixture' for m, p in novo.rpc.calls))
        stages = [e['dados']['etapa'] for e in novo.eventos(identifier)['eventos'] if e['tipo'] == 'etapa']
        self.assertEqual(stages.count('inventario'), 1)
        registro = ler_json(run / 'saidas/codex_execucao.json')
        self.assertEqual((registro['situacao']['codigo'], registro['etapas_sem_registro']), ('concluido', []))
        self.assertEqual(registro['publicacao_achados']['estado'], 'verificado')

    def test_queda_depois_da_ultima_etapa_so_publica_e_verifica(self):
        identifier = self.fx.start()
        for stage in ETAPAS[:-1]:
            self.etapa(self.manager, identifier, stage)
        self.etapa(self.manager, identifier, 'sintese', encerrar=False)  # accepted, turn never ended
        self.travar_como_queda(self.manager, identifier)

        novo = self.novo_backend()
        self.assertEqual(self.estado(novo, identifier)['progresso']['proxima'], None)
        self.assertEqual(novo.retomar(identifier)['retomada_da_etapa'], 'publicacao')
        aguardar_fim(novo, identifier)
        self.assertEqual(novo.contexts[identifier]['meta']['estado'], 'concluido')
        self.assertFalse(any(m == 'turn/start' for m, _ in novo.rpc.calls))
        self.assertEqual(self.revisoes(identifier), ['r1_busca', 'r2_revisao', 'r3_sintese'])
        publicacoes = [e for e in novo.eventos(identifier)['eventos'] if e['tipo'] == 'publicacao']
        self.assertEqual(len(publicacoes), 1)
        self.assertEqual(publicacoes[0]['dados']['estado'], 'verificado')

    def test_dono_e_convite_unico_valem_para_a_retomada(self):
        identifier = self.manager.perguntar(
            {'caso': 'alpha', 'pergunta': 'Pergunta do convite.'}, dono='convite-1')['conversa']
        esperar(lambda: self.manager.contexts[identifier]['meta'].get('turn_id'))
        self.travar_como_queda(self.manager, identifier)
        novo = self.novo_backend()
        with self.assertRaisesRegex(ValueError, 'indisponível'):
            novo.retomar(identifier, dono='convite-2')
        outra = novo.perguntar({'caso': 'alpha', 'pergunta': 'Outra pergunta.'}, dono='convite-1')['conversa']
        with self.assertRaisesRegex(ValueError, 'em andamento'):
            novo.retomar(identifier, dono='convite-1')
        novo.cancelar(outra)
        aguardar_fim(novo, outra)
        with self.assertRaisesRegex(ValueError, 'indisponível'):  # invitation no longer covers the case
            novo.retomar(identifier, dono='convite-1', casos=['beta'])
        self.assertEqual(novo.retomar(identifier, dono='convite-1', casos=['alpha'])['conversa'], identifier)
        novo.cancelar(identifier)

    def test_revisao_publicada_sem_etapa_aceita_recusa_retomada_antes_de_gastar(self):
        identifier = self.fx.start()
        for stage in ('inventario', 'plano', 'busca', 'geracao_inicial'):
            self.etapa(self.manager, identifier, stage)
        self.etapa(self.manager, identifier, 'revisao', entregar=False)
        self.travar_como_queda(self.manager, identifier)
        run = self.manager.contexts[identifier]['run']
        (run / 'saidas/achados/revisoes/r2_revisao').mkdir()  # published, but the crash lost the acceptance
        novo = self.novo_backend()
        with self.assertRaisesRegex(ValueError, 'não pode ser retomada com segurança'):
            novo.retomar(identifier)
        chamadas = [m for m, _ in novo.rpc.calls] if novo.rpc else []
        self.assertFalse({'turn/start', 'thread/resume'} & set(chamadas))
        self.assertFalse(novo.contexts[identifier]['busy'])
        self.assertFalse(any(e['tipo'] == 'retomada' for e in novo.eventos(identifier)['eventos']))


class SituacoesTest(Base):
    def falhar(self, identifier, codigo=None, mensagem='Falha sintética.'):
        turn = self.manager.contexts[identifier]['meta']['turn_id']
        erro = {'message': mensagem}
        if codigo:
            erro['codexErrorInfo'] = codigo
        self.manager.rpc.emit('turn/completed', {'turn': {'id': turn, 'status': 'failed', 'error': erro}})
        aguardar_fim(self.manager, identifier)

    def test_cancelamento_pelo_usuario(self):
        identifier = self.fx.start()
        self.manager.cancelar(identifier)
        aguardar_fim(self.manager, identifier)
        conversa = self.estado(self.manager, identifier)
        self.assertEqual((conversa['estado'], conversa['situacao']['codigo'], conversa['situacao']['causa']),
                         ('interrompido', 'cancelado', 'usuario'))
        self.assertTrue(conversa['retomavel'])
        registro = ler_json(self.manager.contexts[identifier]['run'] / 'saidas/codex_execucao.json')
        self.assertEqual(registro['situacao']['codigo'], 'cancelado')
        final = [e for e in self.manager.eventos(identifier)['eventos'] if e['tipo'] == 'estado'][-1]['dados']
        self.assertEqual((final['situacao'], final['retomavel']), ('cancelado', True))

    def test_cancelamento_do_usuario_prevalece_sobre_causa_anterior(self):
        identifier = self.fx.start()
        self.manager.contexts[identifier]['causa'] = ('erro', 'conexao', 'Falha sintética de conexão.')
        self.manager.cancelar(identifier)
        aguardar_fim(self.manager, identifier)
        situacao = self.estado(self.manager, identifier)['situacao']
        self.assertEqual((situacao['codigo'], situacao['causa']), ('cancelado', 'usuario'))

    def test_codigos_da_api_viram_situacoes(self):
        casos = {'limite': ('sem_cota', 'limite_api'), 'autenticacao': ('erro', 'autenticacao'),
                 'conexao': ('erro', 'conexao'), 'servidor': ('erro', 'servidor'),
                 'max_tokens': ('erro', 'max_tokens'), 'contexto': ('erro', 'contexto'),
                 None: ('erro', 'erro'), 'estranho': ('erro', 'estranho')}
        for codigo, (situacao, causa) in casos.items():
            with self.subTest(codigo=codigo):
                self.assertEqual(classificar_erro(codigo, 'x')[:2], (situacao, causa))

    def test_limite_da_api_vira_sem_cota_e_erro_generico_vira_erro(self):
        identifier = self.fx.start()
        self.falhar(identifier, 'limite', 'Limite de uso da API atingido.')
        conversa = self.estado(self.manager, identifier)
        self.assertEqual((conversa['estado'], conversa['situacao']['codigo'], conversa['situacao']['causa']),
                         ('erro', 'sem_cota', 'limite_api'))
        self.assertIn('Limite', conversa['situacao']['mensagem'])
        self.assertTrue(conversa['retomavel'])
        self.manager.retomar(identifier)
        self.etapa(self.manager, identifier, 'inventario', entregar=False)
        self.falhar(identifier, None, 'Falha sintética genérica.')
        conversa = self.estado(self.manager, identifier)
        self.assertEqual((conversa['situacao']['codigo'], conversa['situacao']['causa']), ('erro', 'erro'))
        self.assertIn('Falha sintética genérica.', conversa['situacao']['mensagem'])

    def test_contexto_excedido_nao_e_retomavel(self):
        identifier = self.fx.start()
        self.falhar(identifier, 'contexto')
        self.assertFalse(self.estado(self.manager, identifier)['retomavel'])
        with self.assertRaisesRegex(ValueError, 'nova conversa'):
            self.manager.retomar(identifier)

    def test_limite_de_tokens_da_consulta_e_do_dia_viram_sem_cota(self):
        escrever_json(self.root / 'configuracao.json', {'caso_ativo': None, 'manifesto_ativo': None,
            'maximo_documentos_inicial': 20, 'indice_sqlite': True,
            'limites': {'tokens_por_consulta': 100, 'tokens_por_dia': None}})
        identifier = self.fx.start()
        self.manager.rpc.emit('item/usage', {'turnId': 'turn-1', 'modelo': 'm', 'uso': {'entrada': 150, 'saida': 10}})
        aguardar_fim(self.manager, identifier)
        conversa = self.estado(self.manager, identifier)
        self.assertEqual((conversa['estado'], conversa['situacao']['codigo'], conversa['situacao']['causa']),
                         ('interrompido', 'sem_cota', 'limite_consulta'))
        with self.assertRaisesRegex(ValueError, 'limite de tokens por consulta'):
            self.manager.retomar(identifier)
        escrever_json(self.root / 'configuracao.json', {'caso_ativo': None, 'manifesto_ativo': None,
            'maximo_documentos_inicial': 20, 'indice_sqlite': True,
            'limites': {'tokens_por_consulta': 1000000, 'tokens_por_dia': None}})
        self.manager.retomar(identifier)
        self.manager.cancelar(identifier)

    def test_retomar_apos_sem_cota_continua_da_etapa_certa_e_arquiva_o_registro(self):
        identifier = self.fx.start()
        self.etapa(self.manager, identifier, 'inventario')
        self.etapa(self.manager, identifier, 'plano')
        self.etapa(self.manager, identifier, 'busca', entregar=False)
        self.falhar(identifier, 'limite', 'Limite de uso da API atingido.')
        run = self.manager.contexts[identifier]['run']
        self.assertEqual(self.manager.contexts[identifier]['meta']['situacao']['codigo'], 'sem_cota')
        self.assertTrue((run / 'saidas/codex_execucao.json').exists())
        self.manager.rpc.ready.clear()
        self.assertEqual(self.manager.retomar(identifier)['retomada_da_etapa'], 'busca')
        self.assertEqual(self.estado(self.manager, identifier)['situacao']['codigo'], 'em_andamento')
        self.completar_de(self.manager, identifier, 'busca')
        meta = self.manager.contexts[identifier]['meta']
        self.assertEqual((meta['estado'], meta['rodadas'], meta['retomadas']), ('concluido', ['R001'], 1))
        anterior = ler_json(run / 'saidas/codex_execucao_tentativa_01.json')
        self.assertEqual(anterior['situacao']['codigo'], 'sem_cota')
        self.assertEqual(ler_json(run / 'saidas/codex_execucao.json')['situacao']['codigo'], 'concluido')
        self.assertEqual(self.revisoes(identifier), ['r1_busca', 'r2_revisao', 'r3_sintese'])

    def test_retomada_recusada_em_execucao_para_outro_dono_e_apos_concluir(self):
        identifier = self.manager.perguntar({'caso': 'alpha', 'pergunta': 'Pergunta.'}, dono='convite-1')['conversa']
        esperar(lambda: self.manager.contexts[identifier]['meta'].get('turn_id'))
        with self.assertRaisesRegex(ValueError, 'em execução'):
            self.manager.retomar(identifier, dono='convite-1')
        with self.assertRaisesRegex(ValueError, 'indisponível'):
            self.manager.retomar(identifier, dono='convite-2')
        self.completar_de(self.manager, identifier, 'inventario')
        self.assertEqual(self.manager.contexts[identifier]['meta']['estado'], 'concluido')
        self.assertFalse(retomavel(self.manager.contexts[identifier]['meta']))
        with self.assertRaisesRegex(ValueError, 'já foi concluída'):
            self.manager.retomar(identifier, dono='convite-1')
        with self.assertRaisesRegex(ValueError, 'inválida'):
            self.manager.retomar('conversa-invalida')

    def test_retomada_sem_chave_ou_com_limite_diario_e_recusada(self):
        identifier = self.fx.start()
        self.falhar(identifier, 'autenticacao')
        self.manager.rpc.authenticated = False
        with self.assertRaisesRegex(ValueError, 'Chave de API'):
            self.manager.retomar(identifier)
        self.manager.rpc.authenticated = True
        escrever_json(self.root / 'configuracao.json', {'caso_ativo': None, 'manifesto_ativo': None,
            'maximo_documentos_inicial': 20, 'indice_sqlite': True,
            'limites': {'tokens_por_consulta': None, 'tokens_por_dia': 5}})
        import limites
        limites.somar_dia(self.root, 10)
        with self.assertRaisesRegex(ValueError, 'Limite diário'):
            self.manager.retomar(identifier)


class HistoricoDoProvedorTest(api.Base):
    def test_thread_resume_descarta_pergunta_sem_resposta_do_turno_que_falhou(self):
        self.provedor.roteiro = [ErroIA('Limite sintético.', codigo='limite')]
        thread = self.iniciar_thread()
        self.turno(thread, 'Etapa sintética.')
        falha = self.proxima('turn/completed')['params']['turn']
        self.assertEqual((falha['status'], falha['error']['codexErrorInfo']), ('failed', 'limite'))
        servidor = self.novo_servidor()  # as after a backend restart
        servidor.call('thread/resume', {'threadId': thread, 'cwd': str(self.workspace), 'model': 'modelo-sintetico',
                                        'developerInstructions': 'Instrução sintética.'})
        self.assertEqual(servidor.threads[thread].mensagens, [])
        self.provedor.roteiro = [Resposta(texto='Ok.')]
        self.turno(thread, 'Etapa sintética.', servidor=servidor)
        self.assertEqual(self.proxima('turn/completed')['params']['turn']['status'], 'completed')
        self.assertEqual([m['papel'] for m in self.provedor.chamadas[-1]['historico']], ['usuario'])


if __name__ == '__main__':
    unittest.main()
