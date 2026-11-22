"""Falhas reais do provedor, de ponta a ponta, sem rede nem chamada paga (CONF-04).

A Mesa (Conversas) fala com o ServidorAPI de verdade, que chama o agente sintético de
``agente_api_sintetico``: ele faz cada etapa por chamadas de ferramenta reais e tira o que precisa
do histórico salvo. As falhas vêm do SDK de verdade (anthropic e openai, nas opções da produção)
sobre um transporte HTTP falso, e o próprio SDK escolhe a exceção e refaz o pedido quando é o caso:

- chave inválida (401): para com a causa de autenticação, sem nova tentativa, sem gasto e sem a
  chave em nenhum evento ou arquivo;
- chave recusada que o provedor ecoa mascarada (a OpenAI mostra o começo e os 4 últimos
  caracteres): nenhum trecho dela, mascarado ou não, em evento ou arquivo;
- cobrança: 402 ``billing_error``, o 400 de saldo baixo e o teto de gasto da conta (429
  ``enforced_spend_limit_reached``) na Anthropic; cota esgotada (429 ``insufficient_quota``) e conta
  inativa (403 ``billing_not_active``) na OpenAI: causa própria, que não manda tentar de novo mais
  tarde; o gasto das chamadas feitas fica; retomar segue da etapa certa;
- limite de uso (429): causa de limite, depois das novas tentativas do SDK;
- tempo esgotado: causa de conexão, depois das novas tentativas do SDK;
- queda no meio da etapa: o processo da Mesa é morto de verdade; outra Mesa na mesma pasta marca a
  conversa interrompida e a retomada segue da etapa cortada, na mesma rodada, com o histórico que o
  outro processo salvou e o gasto de antes da queda contado uma vez.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

TESTES = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTES.parent / 'scripts'))
from agente_api_sintetico import AgenteSintetico, falhar_com  # noqa: E402
from agente_fluxo_fixture import aguardar_fim, encerrar_gerenciador, esperar  # noqa: E402
from codex_apuracao import Conversas  # noqa: E402
from comum import escrever_json, ler_json  # noqa: E402
import custo  # noqa: E402
from inferencia_api import MODELOS_PADRAO, ServidorAPI  # noqa: E402
from modelo_pasta import copiar  # noqa: E402
import test_codex_integracao as integracao  # noqa: E402

AUXILIAR = TESTES / 'apoio_falhas_provedor.py'
ETAPAS = ['inventario', 'plano', 'busca', 'geracao_inicial', 'revisao', 'sintese']
CHAVES = {'ANTHROPIC_API_KEY': 'sk-ant-sintetica-XK4P', 'OPENAI_API_KEY': 'sk-sintetica-QZ7W'}
# The keys as a provider echoes them, masked: OpenAI does it when it refuses a key (its message keeps a
# prefix and the last 4 characters); the Anthropic case checks the same cleaning on the other adapter.
ECO = {'anthropic': 'invalid x-api-key: sk-ant-' + '*' * 12 + 'XK4P',
       'openai': 'Incorrect API key provided: sk-sint' + '*' * 20 + 'QZ7W. You can find your API key at '
                 'https://platform.openai.com/account/api-keys.'}


def erro_anthropic(tipo, mensagem, codigo=None):
    erro = {'type': tipo, 'message': mensagem}
    if codigo:
        erro['details'] = {'error_code': codigo}
    return {'type': 'error', 'error': erro}


def erro_openai(tipo, mensagem, codigo):
    return {'error': {'message': mensagem, 'type': tipo, 'param': None, 'code': codigo}}


class Base:
    provedor = None
    CHAVE_INVALIDA = None
    COBRANCAS = {}
    LIMITE = None

    def setUp(self):
        temp, self.root, _ = copiar('CodexIntegrationTest', integracao.CodexIntegrationTest.montar)
        self.addCleanup(temp.cleanup)
        config = ler_json(self.root / 'configuracao.json')
        escrever_json(self.root / 'configuracao.json', {**config, 'provedor': self.provedor, 'modelo_preferido': None})
        ambiente = mock.patch.dict(os.environ, CHAVES)
        ambiente.start()
        self.addCleanup(ambiente.stop)

    def mesa(self, agente):
        manager = Conversas(self.root, lambda root, callback: ServidorAPI(
            root, callback, criar_provedor=lambda inferencia, chave: agente))
        self.addCleanup(encerrar_gerenciador, manager)
        return manager

    def perguntar(self, manager):
        return manager.perguntar({'caso': 'alpha', 'pergunta': 'Pergunta técnica sintética.'})['conversa']

    def custo_por_chamada(self):
        return custo.custo_da_chamada(self.root, MODELOS_PADRAO[self.provedor],
                                      AgenteSintetico(self.provedor).uso)['micro_brl']

    def gasto(self):
        return custo.gasto(self.root, None)['conta']

    def situacao(self, final):
        return final['estado'], final['situacao']['codigo'], final['situacao']['causa']

    def falhar(self, etapa, **resposta):
        falha, pedidos = falhar_com(self.provedor, **resposta)
        agente = AgenteSintetico(self.provedor, falhas={(etapa, 0): falha})
        manager = self.mesa(agente)
        conversa = self.perguntar(manager)
        return agente, manager, conversa, aguardar_fim(manager, conversa, 60), pedidos

    def test_pergunta_inteira_pelo_servidor_api_com_o_gasto_de_cada_chamada(self):
        agente = AgenteSintetico(self.provedor)
        manager = self.mesa(agente)
        final = aguardar_fim(manager, self.perguntar(manager), 60)
        self.assertEqual(final['estado'], 'concluido', final.get('situacao'))
        self.assertEqual([etapa for etapa, passo in agente.pedidos if passo == 0], ETAPAS)
        self.assertTrue(agente.achado_do_historico and all(agente.achado_do_historico))
        self.assertEqual(self.gasto(), agente.respondidas * self.custo_por_chamada())

    def test_chave_invalida_para_com_a_causa_sem_nova_tentativa_sem_gasto_e_sem_a_chave(self):
        corpo = json.loads(json.dumps(self.CHAVE_INVALIDA).replace('ECO_DA_CHAVE', ECO[self.provedor]))
        agente, manager, conversa, final, pedidos = self.falhar('inventario', status=401, corpo=corpo)
        self.assertEqual(self.situacao(final), ('erro', 'erro', 'autenticacao'))
        self.assertEqual(len(pedidos), 1)  # the SDK does not retry a refused key
        self.assertEqual(self.gasto(), 0)
        textos = [json.dumps(manager.eventos(conversa), ensure_ascii=False)]
        textos += [p.read_text(encoding='utf-8', errors='replace') for p in self.root.rglob('*')
                   if p.is_file() and p.suffix in ('.json', '.jsonl', '.md', '.txt', '.log')]
        self.assertTrue(any('eventos.jsonl' == p.name for p in self.root.rglob('*')))
        self.assertIn('credencial omitida', textos[0])  # the echo reached the event, cleaned
        for trecho in [*CHAVES.values(), *(chave[-4:] for chave in CHAVES.values()), '*' * 5]:
            with self.subTest(trecho=trecho):  # neither the key nor a piece of it, masked or not
                self.assertFalse(any(trecho in texto for texto in textos), 'trecho de chave num evento ou arquivo')

    def test_trechos_de_chave_mascarada_saem_e_o_texto_comum_fica(self):
        from inferencia_api import seguro
        for eco, resto in (('chave sk-proj-****wxyz.', 'chave [credencial omitida].'),
                           ('chave sk-abc...wxyz recusada', 'chave [credencial omitida] recusada'),
                           ('chave ********wxyz recusada', 'chave [credencial omitida] recusada'),
                           ('chave sk-ant-api03-\u2022\u2022\u2022\u2022wxyz', 'chave [credencial omitida]')):
            with self.subTest(eco=eco):
                self.assertEqual(seguro(eco), resto)
        self.assertEqual(seguro('Pergunta... sintética, **destaque** e 3 * 4.'), 'Pergunta... sintética, **destaque** e 3 * 4.')

    def test_cobranca_tem_causa_propria_guarda_o_gasto_feito_e_retoma_da_etapa(self):
        for vez, (nome, (status, corpo)) in enumerate(self.COBRANCAS.items()):
            with self.subTest(nome):
                if vez:
                    self.setUp()  # a fresh folder for each case
                agente, manager, conversa, final, pedidos = self.falhar('geracao_inicial', status=status, corpo=corpo)
                self.assertEqual(self.situacao(final), ('erro', 'sem_cota', 'cobranca_api'))
                self.assertIn('cobrança', final['situacao']['mensagem'])
                self.assertNotIn('Tente novamente mais tarde', final['situacao']['mensagem'])
                antes = agente.respondidas  # inventario, plano and busca: answered and billed
                self.assertEqual(self.gasto(), antes * self.custo_por_chamada())
                pedidos_antes = len(agente.pedidos)
                manager.retomar(conversa)
                final = aguardar_fim(manager, conversa, 60)
                self.assertEqual(final['estado'], 'concluido', final.get('situacao'))
                retomada = agente.pedidos[pedidos_antes:]
                self.assertEqual(retomada[0], ('geracao_inicial', 0))
                self.assertFalse({'inventario', 'plano', 'busca'} & {etapa for etapa, _ in retomada})
                self.assertEqual(self.gasto(), agente.respondidas * self.custo_por_chamada())
                encerrar_gerenciador(manager)

    def test_limite_de_uso_vira_sem_cota_depois_das_novas_tentativas_do_sdk(self):
        status, corpo = self.LIMITE
        _, _, _, final, pedidos = self.falhar('plano', status=status, corpo=corpo, cabecalhos={'retry-after': '0'})
        self.assertEqual(self.situacao(final), ('erro', 'sem_cota', 'limite_api'))
        self.assertEqual(len(pedidos), 3)  # the request and the SDK's two retries

    def test_tempo_esgotado_vira_conexao_depois_das_novas_tentativas_do_sdk(self):
        import httpx2
        _, _, _, final, pedidos = self.falhar('busca', excecao=httpx2.ReadTimeout)
        self.assertEqual(self.situacao(final), ('erro', 'erro', 'conexao'))
        self.assertEqual(len(pedidos), 3)


class FalhasAnthropicTest(Base, unittest.TestCase):
    provedor = 'anthropic'
    CHAVE_INVALIDA = erro_anthropic('authentication_error', 'ECO_DA_CHAVE')
    COBRANCAS = {
        '402 billing_error': (402, erro_anthropic('billing_error', 'Your credit balance is too low.')),
        '400 saldo baixo': (400, erro_anthropic('invalid_request_error', 'Your credit balance is too low to access '
                                                'the Anthropic API. Please go to Plans & Billing to upgrade or '
                                                'purchase credits.')),
        '429 teto de gasto': (429, erro_anthropic('rate_limit_error', 'You have reached your monthly spend limit.',
                                                  'enforced_spend_limit_reached')),
    }
    LIMITE = (429, erro_anthropic('rate_limit_error', 'Number of request tokens has exceeded your rate limit.'))

    def test_queda_no_meio_da_etapa_retoma_noutro_processo_com_o_historico_salvo(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        marca = Path(pasta.name) / 'marca.json'
        processo = subprocess.Popen([sys.executable, str(AUXILIAR), str(self.root), str(marca), 'geracao_inicial'],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
        self.addCleanup(lambda: processo.poll() is None and (processo.kill(), processo.communicate(timeout=15)))
        esperar(lambda: marca.exists() or processo.poll() is not None, 90, 'a Mesa não chegou à etapa')
        self.assertIsNone(processo.poll(), 'a Mesa do outro processo terminou antes da queda')
        processo.kill()  # TerminateProcess / SIGKILL: no orderly shutdown
        saida, _ = processo.communicate(timeout=15)
        conversa = json.loads(saida.splitlines()[0])['conversa']
        antes = json.loads(marca.read_text(encoding='utf-8'))['respondidas']
        self.assertGreater(antes, 0)
        self.assertEqual(self.gasto(), antes * self.custo_por_chamada())  # each answered call counted before the crash

        agente = AgenteSintetico(self.provedor)
        manager = self.mesa(agente)  # another Mesa on the same folder, as the Compose restart does
        conversa_meta = manager.eventos(conversa)['conversa']
        self.assertEqual((conversa_meta['estado'], conversa_meta['situacao']['causa']), ('interrompido', 'reinicio'))
        manager.retomar(conversa)
        final = aguardar_fim(manager, conversa, 60)
        self.assertEqual(final['estado'], 'concluido', final.get('situacao'))
        self.assertEqual(agente.pedidos[0], ('geracao_inicial', 0))  # from the stage cut in the middle
        self.assertFalse({'inventario', 'plano', 'busca'} & {etapa for etapa, _ in agente.pedidos})
        # The hit read by busca in the other process came back with the history it saved.
        self.assertTrue(agente.achado_do_historico and all(agente.achado_do_historico))
        self.assertEqual(sorted(p.name for p in (self.root / 'execucoes/alpha').iterdir() if p.is_dir()), ['R001'])
        self.assertEqual(self.gasto(), (antes + agente.respondidas) * self.custo_por_chamada())


class FalhasOpenAITest(Base, unittest.TestCase):
    provedor = 'openai'
    CHAVE_INVALIDA = erro_openai('invalid_request_error', 'ECO_DA_CHAVE', 'invalid_api_key')
    COBRANCAS = {
        '429 insufficient_quota': (429, erro_openai('insufficient_quota', 'You exceeded your current quota.',
                                                    'insufficient_quota')),
        '403 billing_not_active': (403, erro_openai('billing_not_active', 'Your account is not active, please '
                                                    'check your billing details on our website.',
                                                    'billing_not_active')),
    }
    LIMITE = (429, erro_openai('requests', 'Rate limit reached for requests.', 'rate_limit_exceeded'))

    def test_cota_esgotada_no_meio_do_fluxo_tambem_e_cobranca(self):
        # A response that fails while streaming (response.failed) carries the same codes in its error.
        from types import SimpleNamespace
        import provedor_openai
        falha = lambda codigo: provedor_openai._falha(SimpleNamespace(code=codigo, message='Falha sintética.'))  # noqa: E731
        self.assertEqual(falha('insufficient_quota').codigo, 'cobranca')
        self.assertEqual(falha('rate_limit_exceeded').codigo, 'limite')
        self.assertIsNone(falha('server_error').codigo)


if __name__ == '__main__':
    unittest.main()
