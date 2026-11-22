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
SOL = 'gpt-6.1-sol'  # GPT Sol 6.1, prices given by the owner on 2026-11-21 (identifier to be confirmed)
PRECO_OPENAI = {'entrada': 1.25, 'cache_leitura': 0.125, 'cache_escrita_30m': 0.0, 'cache_escrita_12h': 0.0, 'saida': 10.0}


def uso_openai(entrada=10000, saida=2000, lidos=6000, escritos=3000, doze_horas=1000, detalhe=True):
    """Usage as the OpenAI SDK gives it (input_tokens_details breaks input_tokens down)."""
    validades = SimpleNamespace(ttl_30m_tokens=escritos - doze_horas, ttl_12h_tokens=doze_horas) if detalhe else None
    return provedor_openai.uso_da_resposta(SimpleNamespace(
        input_tokens=entrada, output_tokens=saida, output_tokens_details=SimpleNamespace(reasoning_tokens=500),
        input_tokens_details=SimpleNamespace(cached_tokens=lidos, cache_write_tokens=escritos,
                                             cache_write_tokens_details=validades)))


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

    def test_gpt_sol_conta_leitura_e_gravacao_de_30_minutos_e_12_horas_pelo_seu_preco(self):
        uso = uso_openai()
        self.assertEqual(custo.uso_normalizado(uso), {'entrada_sem_cache': 1000, 'cache_leitura': 6000,
                                                      'cache_escrita_30m': 2000, 'cache_escrita_12h': 1000, 'saida': 2000})
        provedor, preco = custo.preco(self.root, SOL)
        self.assertEqual(provedor, 'openai')
        # 1000 x 2 + 6000 x 0.10 + 2000 x 2.50 + 1000 x 5 + 2000 x 10 (reasoning is output), per million.
        self.assertEqual(custo.custo_usd(uso, preco), Decimal('0.0326'))
        self.assertEqual(custo.tokens_totais(uso), 12000)  # input + output: the cache is inside the input
        registro = custo.custo_da_chamada(self.root, SOL, uso)
        self.assertEqual((registro['usd'], registro['preco_de'], registro['preco_estimado']), ('0.032600', SOL, False))

    def test_gpt_sol_sem_divisao_por_validade_conta_como_30_minutos_e_registra(self):
        uso = uso_openai(detalhe=False)
        self.assertEqual((uso['cache_escrita_30m'], uso['cache_escrita_12h'], uso['cache_escrita_30m_suposto']), (3000, 0, 3000))
        self.assertEqual(custo.uso_normalizado(uso)['cache_escrita_30m'], 3000)

    def test_validade_que_o_modelo_nao_tem_conta_pela_escrita_mais_cara_dele(self):
        registro = custo.custo_da_chamada(self.root, SONNET, {'entrada': 0, 'saida': 0, 'cache_escrita_30m': 1_000_000})
        self.assertEqual((registro['usd'], registro['preco_estimado']), ('4.000000', True))  # Sonnet's 1-hour write

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
        self.assertEqual((caro['usd'], caro['preco_estimado']), ('8.000000', True))  # the most expensive input
        self.assertFalse(custo.custo_da_chamada(self.root, SONNET, uso)['preco_estimado'])

    def test_modelo_da_openai_permitido_sem_preco_conta_pelo_maior_preco_de_cada_tipo(self):
        self.orcamento(modelos_permitidos=[SONNET, SOL, 'gpt-outro-sem-preco'])
        custo.conferir_modelo(self.root, 'openai', 'gpt-outro-sem-preco')
        self.assertIn({'modelo': 'gpt-outro-sem-preco', 'provedor': 'openai', 'preco_estimado': True},
                      custo.modelos_permitidos(self.root))
        uso = {**uso_openai(), 'cache_escrita_5m': 1000}
        tabela = custo.tabela_precos(self.root)
        maximo = custo.preco_maximo(tabela)
        self.assertEqual({k: maximo[k] for k in ('entrada', 'cache_leitura', 'saida', 'cache_escrita_12h')},
                         {'entrada': 8.0, 'cache_leitura': 0.5, 'saida': 40.0, 'cache_escrita_12h': 5.0})
        with self.assertLogs('vlado.custo', 'WARNING') as aviso:
            registro = custo.custo_da_chamada(self.root, 'gpt-outro-sem-preco', uso)
        self.assertIn('gpt-outro-sem-preco', '\n'.join(aviso.output))
        self.assertTrue(registro['preco_estimado'])
        self.assertEqual(Decimal(registro['usd']), custo.custo_usd(uso, maximo).quantize(Decimal('0.000001')))
        self.assertGreater(custo.estimativa_minima_brl(self.root, 'gpt-outro-sem-preco'), custo.estimativa_minima_brl(self.root, SOL))
        self.orcamento(modelos_permitidos=[SONNET, SOL])
        with self.assertRaisesRegex(ValueError, 'gpt-outro-sem-preco não está entre os permitidos'):
            custo.conferir_modelo(self.root, 'openai', 'gpt-outro-sem-preco')

    def test_tabela_versionada_valida_cada_preco(self):
        tabela = ler_json(ROOT / custo.TABELA)
        self.assertTrue(tabela['vigente_em'] and tabela['fonte'] and tabela['cambio']['vigente_em'])
        self.assertIn(SOL, tabela['modelos']['openai'])
        self.assertIn('A CONFERIR PELO DONO', tabela['fonte'])
        for _, lista in tabela['modelos'].items():
            for modelo, preco in lista.items():
                self.assertLessEqual(set(custo.PRECO_DE.values()), set(preco), modelo)
                self.assertTrue(all(k in custo.PRECO_DE.values() or custo.ESCRITA.fullmatch(k) for k in preco), modelo)
        self.assertEqual(tabela['orcamento_padrao']['modelos_permitidos'], [SONNET, SOL])
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
        self.assertEqual(sorted(registro['meses']), ['2026-11', '2026-12'])  # the check before the question writes it
        self.assertEqual(registro['meses']['2026-12']['contas'], {'a': 0})

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

    def test_registro_ilegivel_nunca_vira_zero_gasto(self):
        registro = self.root / 'ajustes/gasto_mensal.json'
        registro.parent.mkdir()
        registro.write_text('{corrompido', encoding='utf-8')  # and no previous copy
        with self.assertLogs('vlado.custo', 'WARNING'), self.assertRaises(custo.GastoSemRegistro) as recusa:
            custo.conferir_antes(self.root, 'a', SONNET)
        self.assertIsInstance(recusa.exception, custo.CotaEsgotada)  # treated as an exhausted quota
        self.assertEqual(erros.codigo_de(str(recusa.exception))[0], 'gasto_ilegivel')
        with self.assertRaises(custo.GastoSemRegistro):
            custo.situacao(self.root, 'a')

    def test_registro_ilegivel_lido_da_copia_anterior(self):
        self.gastar('a', 40)
        (self.root / 'ajustes/gasto_mensal.json').write_text('{corrompido', encoding='utf-8')
        with self.assertLogs('vlado.custo', 'WARNING') as aviso:
            self.assertEqual(custo.gasto(self.root, 'a')['conta'], 40_000_000)
        self.assertIn('cópia anterior', '\n'.join(aviso.output))
        self.orcamento(mensal_por_conta_brl=40)
        with self.assertLogs('vlado.custo', 'WARNING'), self.assertRaisesRegex(custo.CotaEsgotada, 'Você usou R\\$ 40,00'):
            custo.conferir_antes(self.root, 'a', SONNET)

    def test_gasto_que_nao_grava_recusa_a_pergunta(self):
        with mock.patch.object(custo, '_atomico', side_effect=OSError(28, 'No space left on device')), \
                self.assertLogs('vlado.custo', 'WARNING'):
            with self.assertRaises(custo.GastoSemRegistro) as recusa:
                custo.conferir_antes(self.root, 'a', SONNET)
        self.assertEqual(erros.codigo_de(str(recusa.exception))[0], 'gasto_nao_registrado')
        custo.conferir_antes(self.root, 'a', SONNET)  # writable again

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
        inferencia_api.salvar_inferencia(self.root, {'provedor': 'openai', 'modelo_preferido': None})  # GPT Sol 6.1
        self.orcamento(modelos_permitidos=[SONNET, 'claude-fable-5-2'])
        with self.assertRaisesRegex(ValueError, 'nenhum deste provedor'):
            inferencia_api.salvar_inferencia(self.root, {'provedor': 'openai', 'modelo_preferido': None})
        inferencia_api.salvar_inferencia(self.root, {'provedor': 'anthropic', 'modelo_preferido': 'claude-fable-5-2'})
        self.assertEqual(inferencia_api.resumo_inferencia(self.root)['modelos_permitidos'],
                         [{'modelo': SONNET, 'provedor': 'anthropic', 'preco_estimado': False},
                          {'modelo': 'claude-fable-5-2', 'provedor': 'anthropic', 'preco_estimado': False}])

    def test_modelo_da_anthropic_sem_preco_nao_entra_nos_permitidos(self):
        self.orcamento(modelos_permitidos=['claude-sonet-5-5'])  # a mistyped name: no price, so it is never Anthropic
        with self.assertRaisesRegex(ValueError, 'claude-sonet-5-5 não está entre os permitidos'):
            custo.conferir_modelo(self.root, 'anthropic', 'claude-sonet-5-5')
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
        # The simulated model has no price: its minimum estimate is at the highest prices, kept small here.
        self.orcamento(mensal_por_conta_brl=1.0, estimativa_minima_tokens={'entrada': 1000, 'saida': 100})
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

    def test_gasto_que_nao_grava_interrompe_e_recusa_a_proxima(self):
        identificador = self.start()
        with mock.patch.object(custo, '_atomico', side_effect=OSError(28, 'No space left on device')), \
                self.assertLogs('vlado.custo', 'WARNING'):
            self.manager.rpc.emit('item/usage', {'turnId': 'turn-1', 'modelo': SONNET, 'uso': uso_anthropic()})
            aguardar_fim(self.manager, identificador)
            eventos = self.manager.eventos(identificador)['eventos']
            self.assertTrue(any(e['tipo'] == 'erro' and e['dados']['mensagem'].startswith(
                'O gasto do mês não pode ser registrado agora') for e in eventos))
            self.assertTrue(any(method == 'turn/interrupt' for method, _ in self.manager.rpc.calls))
            self.assertEqual(self.manager.contexts[identificador]['meta']['situacao']['causa'], 'gasto_nao_registrado')
            with self.assertRaisesRegex(custo.GastoSemRegistro, 'nenhuma pergunta é feita até o registro voltar'):
                self.manager.perguntar(self.pergunta())
        self.assertTrue(self.manager.perguntar(self.pergunta())['conversa'])  # recorded again: questions go on

    def test_custo_que_nao_calcula_interrompe(self):
        identificador = self.start()
        with mock.patch.object(custo, 'custo_da_chamada', side_effect=ValueError('precos_modelos.json ilegível')):
            self.manager.rpc.emit('item/usage', {'turnId': 'turn-1', 'modelo': SONNET, 'uso': uso_anthropic()})
            aguardar_fim(self.manager, identificador)
        eventos = self.manager.eventos(identificador)['eventos']
        self.assertTrue(any(e['tipo'] == 'erro' and 'o custo da última chamada não pôde ser calculado'
                            in e['dados']['mensagem'] for e in eventos))

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
