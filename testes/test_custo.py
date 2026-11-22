"""Custo em dinheiro (CUS-01, CUS-03), só com provedor simulado: nenhuma chamada paga.

Cobre: preço de cada tipo de token com cache (escrita de 5 minutos e de 1 hora, leitura) nos dois
provedores, a partir do uso como cada API o informa; registro do custo por chamada; cota mensal em
reais por conta e da organização, com estouro no meio do mês e renovação no mês seguinte; cota do
administrador; recusa antes de começar e interrupção no meio da pergunta, com a mensagem do W11;
teto de perguntas simultâneas por conta e no total; lista de modelos permitidos na configuração e
na pergunta; tabela de preços versionada; rota de leitura do gasto e do saldo.
"""
from decimal import Decimal
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest import mock

TESTES = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTES.parent / 'scripts'))
from agente_fluxo_fixture import aguardar_fim, esperar  # noqa: E402
from comum import ROOT, escrever_json, ler_json  # noqa: E402
import custo  # noqa: E402
import erros  # noqa: E402
import inferencia_api  # noqa: E402
import provedor_anthropic  # noqa: E402
import provedor_openai  # noqa: E402
import test_codex_integracao as integracao  # noqa: E402

SONNET = 'claude-sonnet-5-5'
PRECO_OPENAI = {'entrada': 1.25, 'cache_leitura': 0.125, 'cache_escrita_5m': 0.0, 'cache_escrita_1h': 0.0, 'saida': 10.0}


def uso_anthropic(entrada=1000, saida=500, lidos=200000, escritos_5m=20000, escritos_1h=10000, divisao=True):
    """Usage as the Anthropic SDK gives it (input_tokens excludes the cache)."""
    criacao = SimpleNamespace(ephemeral_5m_input_tokens=escritos_5m, ephemeral_1h_input_tokens=escritos_1h) if divisao else None
    return provedor_anthropic.uso_da_resposta(SimpleNamespace(
        input_tokens=entrada, output_tokens=saida, cache_read_input_tokens=lidos,
        cache_creation_input_tokens=escritos_5m + escritos_1h, cache_creation=criacao))


class Base(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        escrever_json(self.root / 'configuracao.json', {'provedor': 'anthropic', 'modelo_preferido': None})

    def orcamento(self, **valores):
        config = ler_json(self.root / 'configuracao.json')
        escrever_json(self.root / 'configuracao.json', {**config, 'orcamento': valores})

    def tabela(self, **mudancas):
        tabela = ler_json(ROOT / custo.TABELA)
        for chave, valor in mudancas.items():
            tabela[chave] = valor
        escrever_json(self.root / custo.TABELA, tabela)
        return tabela


class PrecoTest(Base):
    def test_cada_tipo_de_token_da_anthropic_tem_o_seu_preco(self):
        uso = uso_anthropic()
        self.assertEqual(custo.uso_normalizado(uso), {'entrada_sem_cache': 1000, 'cache_leitura': 200000,
                                                      'cache_escrita_5m': 20000, 'cache_escrita_1h': 10000, 'saida': 500})
        _, preco = custo.preco(self.root, SONNET)
        # 1000 x 2 + 200000 x 0.10 + 20000 x 2.50 + 10000 x 4 + 500 x 10, per million: the cache is most of it.
        self.assertEqual(custo.custo_usd(uso, preco), Decimal('0.117'))
        self.assertEqual(custo.custo_usd({'entrada': 1000, 'saida': 500}, preco), Decimal('0.007'))  # what was counted before
        self.assertEqual(custo.tokens_totais(uso), 231500)

    def test_escrita_sem_divisao_por_validade_conta_como_5_minutos(self):
        uso = uso_anthropic(escritos_5m=30000, escritos_1h=0, divisao=False)
        self.assertEqual((uso['cache_escrita_5m'], uso['cache_escrita_1h']), (30000, 0))

    def test_openai_conta_o_cache_dentro_da_entrada_e_nao_cobra_escrita(self):
        uso = provedor_openai.uso_da_resposta(SimpleNamespace(
            input_tokens=10000, output_tokens=2000, input_tokens_details=SimpleNamespace(cached_tokens=8000),
            output_tokens_details=SimpleNamespace(reasoning_tokens=500)))
        self.assertEqual(custo.uso_normalizado(uso), {'entrada_sem_cache': 2000, 'cache_leitura': 8000,
                                                      'cache_escrita_5m': 0, 'cache_escrita_1h': 0, 'saida': 2000})
        # 2000 x 1.25 + 8000 x 0.125 + 2000 x 10 (reasoning is output), per million.
        self.assertEqual(custo.custo_usd(uso, PRECO_OPENAI), Decimal('0.0235'))
        self.assertEqual(custo.tokens_totais(uso), 12000)  # not 20000: the cached part is not counted twice

    def test_custo_da_chamada_em_reais_com_o_cambio_e_a_tabela(self):
        registro = custo.custo_da_chamada(self.root, SONNET, uso_anthropic())
        self.assertEqual((registro['usd'], registro['cambio_brl_por_usd'], registro['brl']), ('0.117000', '5.5', '0.643500'))
        self.assertEqual((registro['micro_brl'], registro['preco_de']), (643500, SONNET))
        self.assertEqual(registro['tabela_vigente_em'], ler_json(ROOT / custo.TABELA)['vigente_em'])
        self.orcamento(cambio_brl_por_usd=6.0)
        self.assertEqual(custo.custo_da_chamada(self.root, SONNET, uso_anthropic())['brl'], '0.702000')

    def test_modelo_sem_preco_nunca_fica_sem_conta(self):
        uso = {'entrada': 1_000_000, 'saida': 0}
        self.assertEqual(custo.custo_da_chamada(self.root, 'modelo-sem-preco', uso, SONNET)['preco_de'], SONNET)
        caro = custo.custo_da_chamada(self.root, 'modelo-sem-preco', uso)
        self.assertIn('preço mais alto da tabela', caro['preco_de'])
        self.assertEqual(caro['usd'], '8.000000')  # the most expensive input of the table

    def test_tabela_versionada_valida_cada_preco(self):
        tabela = ler_json(ROOT / custo.TABELA)
        self.assertTrue(tabela['vigente_em'] and tabela['fonte'] and tabela['cambio']['vigente_em'])
        for _, lista in tabela['modelos'].items():
            for modelo, preco in lista.items():
                self.assertEqual(set(preco), set(custo.PRECO_DE.values()), modelo)
        ruim = json.loads(json.dumps(tabela))
        del ruim['modelos']['anthropic'][SONNET]['cache_leitura']
        escrever_json(self.root / custo.TABELA, ruim)
        with self.assertRaisesRegex(ValueError, 'cache_leitura'):
            custo.tabela_precos(self.root)


class CotaTest(Base):
    def gastar(self, conta, reais):
        return custo.somar_gasto(self.root, conta, int(Decimal(str(reais)) * custo.MICRO))

    def test_gasto_mensal_por_conta_e_da_organizacao_renova_no_mes_seguinte(self):
        with mock.patch.object(custo, 'mes', return_value='2026-11'):
            self.gastar('a', 30)
            self.assertEqual(self.gastar('b', 12.5), {'conta': 12_500_000, 'organizacao': 42_500_000})
            self.assertEqual(custo.gasto(self.root, 'a'), {'conta': 30_000_000, 'organizacao': 42_500_000})
        with mock.patch.object(custo, 'mes', return_value='2026-12'):
            self.assertEqual(custo.gasto(self.root, 'a'), {'conta': 0, 'organizacao': 0})
            custo.conferir_antes(self.root, 'a', SONNET)
        registro = ler_json(self.root / 'ajustes/gasto_mensal.json')
        self.assertEqual(sorted(registro['meses']), ['2026-11'])  # December spent nothing yet

    def test_estouro_no_meio_do_mes_recusa_com_a_mensagem_do_w11(self):
        self.orcamento(mensal_por_conta_brl=50)
        with mock.patch.object(custo, 'mes', return_value='2026-11'):
            self.gastar('a', 49.5)  # the balance does not cover a short question (about R$ 1,10)
            with self.assertRaises(custo.CotaEsgotada) as recusa:
                custo.conferir_antes(self.root, 'a', SONNET)
        mensagem = str(recusa.exception)
        self.assertEqual(mensagem, 'Sua cota do mês acabou. Você usou R$ 49,50 de R$ 50,00. Documentos, conferência e '
                                   'caderno seguem funcionando.')
        self.assertEqual(erros.codigo_de(mensagem), ('cota_mensal_conta', {'usado': '49,50', 'teto': '50,00'}))
        custo.conferir_antes(self.root, 'outra', SONNET)  # another account still has its quota

    def test_cota_da_organizacao_e_o_convidado_nao_ve_os_valores(self):
        self.orcamento(mensal_por_conta_brl=50, mensal_organizacao_brl=60)
        self.gastar('a', 40), self.gastar('b', 20)
        with self.assertRaisesRegex(custo.CotaEsgotada, r'^A cota do mês da instalação acabou\. Foram usados R\$ 60,00 de R\$ 60,00\.'):
            custo.conferir_antes(self.root, 'c', SONNET)
        with self.assertRaises(custo.CotaEsgotada) as recusa:
            custo.conferir_antes(self.root, 'c', SONNET, convidado=True)
        self.assertNotIn('R$', str(recusa.exception))
        self.assertEqual(erros.codigo_de(str(recusa.exception))[0], 'cota_mensal_organizacao')

    def test_situacao_para_a_barra_de_cota(self):
        self.orcamento(mensal_por_conta_brl=50, mensal_organizacao_brl=500)
        self.gastar('a', 12.345)
        administrador = custo.situacao(self.root, 'a', administrador=True)
        self.assertEqual(administrador['conta'], {'gasto_brl': '12.35', 'teto_brl': '50.00', 'saldo_brl': '37.65',
                                                  'esgotada': False})
        self.assertEqual(administrador['organizacao']['gasto_brl'], '12.35')
        self.assertEqual(administrador['moeda'], 'BRL')
        self.assertNotIn('organizacao', custo.situacao(self.root, 'a'))

    def test_configuracao_invalida_recusa_sem_gastar(self):
        for invalido in ({'mensal_por_conta_brl': 0}, {'mensal_organizacao_brl': 'muito'}, {'outro': 1},
                         {'execucoes_simultaneas': 0}, {'modelos_permitidos': []}, {'cambio_brl_por_usd': -1}):
            with self.subTest(invalido):
                self.orcamento(**invalido)
                with self.assertRaises(ValueError):
                    custo.conferir_antes(self.root, 'a', SONNET)


class ModelosPermitidosTest(Base):
    def test_configuracao_recusa_modelo_fora_da_lista(self):
        inferencia_api.salvar_inferencia(self.root, {'provedor': 'anthropic', 'modelo_preferido': SONNET})
        antes = (self.root / 'ajustes/inferencia.json').read_bytes()
        with self.assertRaises(ValueError) as recusa:
            inferencia_api.salvar_inferencia(self.root, {'provedor': 'anthropic', 'modelo_preferido': 'claude-fable-5-2'})
        self.assertIn('claude-fable-5-2 não está entre os permitidos nesta instalação (claude-sonnet-5-5)', str(recusa.exception))
        self.assertEqual(erros.codigo_de(str(recusa.exception))[0], 'modelo_nao_permitido')
        self.assertEqual((self.root / 'ajustes/inferencia.json').read_bytes(), antes)  # nothing saved
        with self.assertRaisesRegex(ValueError, 'nenhum deste provedor'):
            inferencia_api.salvar_inferencia(self.root, {'provedor': 'openai', 'modelo_preferido': None})
        self.orcamento(modelos_permitidos=[SONNET, 'claude-fable-5-2'])
        inferencia_api.salvar_inferencia(self.root, {'provedor': 'anthropic', 'modelo_preferido': 'claude-fable-5-2'})
        self.assertEqual(inferencia_api.resumo_inferencia(self.root)['modelos_permitidos'],
                         [{'modelo': SONNET, 'provedor': 'anthropic'}, {'modelo': 'claude-fable-5-2', 'provedor': 'anthropic'}])

    def test_modelo_permitido_precisa_de_preco(self):
        self.orcamento(modelos_permitidos=['modelo-caro-sem-preco'])
        with self.assertRaisesRegex(ValueError, 'sem preço em precos_modelos.json'):
            custo.conferir_modelo(self.root, 'anthropic', 'modelo-caro-sem-preco')
        self.tabela(modelos={'anthropic': {}, 'openai': {'modelo-openai-sintetico': PRECO_OPENAI}})
        self.orcamento(modelos_permitidos=['modelo-openai-sintetico'])
        custo.conferir_modelo(self.root, 'openai', 'modelo-openai-sintetico')

    def test_servidor_de_inferencia_avisa_o_modelo_recusado_na_pergunta(self):
        escrever_json(self.root / 'configuracao.json', {'provedor': 'anthropic', 'modelo_preferido': 'claude-fable-5-2'})
        servidor = inferencia_api.ServidorAPI.__new__(inferencia_api.ServidorAPI)
        servidor.root = self.root
        with mock.patch.object(inferencia_api.ServidorAPI, '_chave', return_value='chave-sintetica-de-teste'):
            conta = servidor._conta({})['account']
            self.assertIn('claude-fable-5-2 não está entre os permitidos', conta['recusa_modelo'])
            self.orcamento(modelos_permitidos=['claude-fable-5-2'])
            self.assertNotIn('recusa_modelo', servidor._conta({})['account'])


class ServidorRecusando(integracao.FakeServer):
    recusa = 'O modelo claude-fable-5-2 não está entre os permitidos nesta instalação (claude-sonnet-5-5).'

    def call(self, method, params=None):
        resposta = super().call(method, params)
        if method == 'account/read':
            resposta['account']['recusa_modelo'] = self.recusa
        return resposta


class PerguntaTest(unittest.TestCase):
    """Through Conversas with the simulated provider (integracao.FakeServer)."""
    start = integracao.CodexIntegrationTest.start

    def setUp(self):
        integracao.CodexIntegrationTest.setUp(self)
        self.config = ler_json(self.root / 'configuracao.json')

    def orcamento(self, **valores):
        escrever_json(self.root / 'configuracao.json', {**self.config, 'orcamento': valores})

    def ocupada(self, conta, dono=None):
        """An execution in course for ``conta`` (as perguntar leaves it while the stages run)."""
        identificador = f'{len(self.manager.contexts):032x}'
        self.manager.contexts[identificador] = {'meta': {'conta': conta, 'dono': dono, 'estado': 'executando'},
                                                'busy': True, 'events': []}
        self.addCleanup(self.manager.contexts.pop, identificador, None)

    def pergunta(self, **extra):
        return {'caso': 'alpha', 'pergunta': 'Pergunta técnica sintética.', **extra}

    def test_gasto_com_cache_registrado_por_chamada_e_estouro_no_meio_interrompe(self):
        self.orcamento(mensal_por_conta_brl=1.0)
        identificador = self.start()
        rpc = self.manager.rpc
        uso = uso_anthropic()  # R$ 0,6435 at Sonnet 5.5
        rpc.emit('item/usage', {'turnId': 'turn-1', 'modelo': SONNET, 'uso': uso})
        ctx = self.manager.contexts[identificador]
        esperar(lambda: ctx['meta'].get('custo_micro_brl') == 643500, 5)
        registro = ler_json(ctx['run'] / 'saidas/api_uso_0001.json')
        self.assertEqual((registro['custo']['brl'], registro['custo']['preco_de']), ('0.643500', SONNET))
        self.assertEqual(registro['custo']['tokens']['cache_leitura'], 200000)
        self.assertFalse(ctx.get('cancel'))
        rpc.emit('item/usage', {'turnId': 'turn-1', 'modelo': SONNET, 'uso': uso})  # R$ 1,287 > R$ 1,00
        aguardar_fim(self.manager, identificador)
        eventos = self.manager.eventos(identificador)['eventos']
        self.assertTrue(any(e['tipo'] == 'erro' and e['dados']['mensagem'].startswith(
            'Sua cota do mês acabou. Você usou R$ 1,29 de R$ 1,00.') for e in eventos))
        self.assertTrue(any(method == 'turn/interrupt' for method, _ in rpc.calls))
        self.assertEqual(ctx['meta']['situacao']['causa'], 'limite_cota_conta')
        self.assertEqual(custo.gasto(self.root, None)['conta'], 1_287_000)
        with self.assertRaisesRegex(custo.CotaEsgotada, r'Você usou R\$ 1,29 de R\$ 1,00'):
            self.manager.perguntar(self.pergunta())

    def test_gasto_somado_mesmo_com_limites_de_tokens_ilegiveis(self):
        identificador = self.start()
        escrever_json(self.root / 'configuracao.json', {**self.config, 'limites': {'outro': 1}})  # broken mid-question
        self.manager.rpc.emit('item/usage', {'turnId': 'turn-1', 'modelo': SONNET, 'uso': uso_anthropic()})
        esperar(lambda: custo.gasto(self.root, None)['conta'] == 643500, 5, 'o gasto não foi somado')
        eventos = self.manager.eventos(identificador)['eventos']
        self.assertTrue(any(e['tipo'] == 'aviso' and 'Limites de tokens não conferidos' in e['dados']['mensagem']
                            for e in eventos))

    def test_administrador_tambem_tem_cota(self):
        self.orcamento(mensal_por_conta_brl=5.0)
        custo.somar_gasto(self.root, 'conta-admin', 5 * 1_000_000)
        with self.assertRaisesRegex(custo.CotaEsgotada, 'Sua cota do mês acabou'):
            self.manager.perguntar(self.pergunta(), dono=None, conta='conta-admin')
        self.assertTrue(self.manager.perguntar(self.pergunta(), dono=None, conta='outro-admin')['conversa'])

    def test_teto_de_perguntas_simultaneas_por_conta_e_no_total(self):
        self.orcamento(execucoes_simultaneas_por_conta=1, execucoes_simultaneas=2)
        self.ocupada('a')
        with self.assertRaises(ValueError) as recusa:
            self.manager.perguntar(self.pergunta(), conta='a')
        self.assertTrue(str(recusa.exception).startswith('Já há 1 pergunta em andamento nesta conta.'))
        self.assertEqual(erros.codigo_de(str(recusa.exception)), ('execucoes_simultaneas_conta', {'limite': 1}))
        self.ocupada('b')
        with self.assertRaises(ValueError) as recusa:
            self.manager.perguntar(self.pergunta(), conta='c')
        self.assertTrue(str(recusa.exception).startswith('A Mesa já está com 2 perguntas em andamento.'))
        self.assertEqual(erros.codigo_de(str(recusa.exception))[0], 'execucoes_simultaneas_mesa')

    def test_modelo_fora_da_lista_recusado_antes_da_pergunta(self):
        self.manager.factory, self.manager.rpc = ServidorRecusando, None  # the next status() asks the new one
        antes = set(self.manager.contexts)
        with self.assertRaisesRegex(ValueError, 'não está entre os permitidos'):
            self.manager.perguntar(self.pergunta())
        self.assertEqual(set(self.manager.contexts), antes)  # no conversation was created

    def test_limite_de_tokens_conta_o_cache(self):
        config = {**self.config, 'limites': {'tokens_por_consulta': 100000, 'tokens_por_dia': 10_000_000}}
        escrever_json(self.root / 'configuracao.json', config)
        identificador = self.start()
        # entrada + saida = 1500 (it passed before); with the cache, 231500 tokens.
        self.manager.rpc.emit('item/usage', {'turnId': 'turn-1', 'modelo': SONNET, 'uso': uso_anthropic()})
        aguardar_fim(self.manager, identificador)
        eventos = self.manager.eventos(identificador)['eventos']
        self.assertTrue(any(e['tipo'] == 'erro' and 'Limite de tokens por consulta atingido (231500 de 100000)'
                            in e['dados']['mensagem'] for e in eventos))


class RotaDaCotaTest(Base):
    def test_get_api_cota(self):
        from interface_pesquisa import Servidor
        server = Servidor(('127.0.0.1', 0), self.root)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (server.shutdown(), server.server_close(), thread.join(5)))
        custo.somar_gasto(self.root, None, 2_500_000)
        con = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=10)
        try:
            con.request('GET', '/api/cota', headers={'X-Session-Token': server.token})
            resposta = con.getresponse()
            corpo = json.loads(resposta.read())
        finally:
            con.close()
        self.assertEqual(resposta.status, 200)
        self.assertEqual((corpo['conta']['gasto_brl'], corpo['conta']['teto_brl'], corpo['conta']['saldo_brl']),
                         ('2.50', '50.00', '47.50'))
        self.assertEqual(corpo['organizacao']['gasto_brl'], '2.50')  # the local operator is the administrator


if __name__ == '__main__':
    unittest.main()
