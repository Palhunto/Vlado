"""Trava de cadastro e conversas (CONF-01): ordem das travas, espera da pergunta e envio de originais.

- A pergunta que encontra um cadastro em curso espera para congelar sem prender as outras
  conversas, avisa que está esperando e desiste se for cancelada.
- O congelamento não pega ``Conversas.lock`` dentro da trava de cadastro: quem segura
  ``Conversas.lock`` esperando a trava (gestão, lixeira) não fica num impasse com ele.
- ``codex-documentos-cadastrar`` só prende ``Conversas.lock`` na conferência; durante o
  cadastro as outras conversas andam e a conversa conferida não recebe pergunta nova.
- Originais (ressalva 7 da Onda 0): lidos dentro da trava da Mesa, enviados fora dela.
Provedor simulado e dados sintéticos; sem rede nem modelo.
"""
import base64
import http.client
import json
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace
import unittest
from unittest import mock

TESTES = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTES.parent / 'scripts'))
import test_codex_integracao as integracao  # noqa: E402
from agente_fluxo_fixture import aguardar_fim, completar, esperar  # noqa: E402
import apuracao  # noqa: E402
import caderno  # noqa: E402
from cadastrar_documentos import _trava  # noqa: E402
import codex_apuracao  # noqa: E402
from codex_apuracao import ACTIVE  # noqa: E402
import diligencias  # noqa: E402
import interface_pesquisa  # noqa: E402
from interface_pesquisa import Servidor  # noqa: E402
import rotas_conversa  # noqa: E402
import rotas_downloads  # noqa: E402


class Base(unittest.TestCase):
    start = integracao.CodexIntegrationTest.start

    def setUp(self):
        integracao.CodexIntegrationTest.setUp(self)

    def segurar_trava(self):
        """Hold the cadastro lock in another thread (as a CLI cadastro would); returns its release."""
        dentro, fim = threading.Event(), threading.Event()

        def alvo():
            with _trava(self.root, operacao='teste'):
                dentro.set()
                fim.wait(30)
        thread = threading.Thread(target=alvo, daemon=True)
        thread.start()
        self.assertTrue(dentro.wait(5))
        self.addCleanup(lambda: (fim.set(), thread.join(5)))
        return fim

    def servidor(self):
        server = Servidor(('127.0.0.1', 0), self.root)
        server.conversas = self.manager
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (server.shutdown(), server.server_close(), thread.join(3)))
        return server

    @staticmethod
    def post(server, operacao, dados, prazo=10):
        con = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=prazo)
        try:
            con.request('POST', '/api/' + operacao, json.dumps(dados),
                        {'Content-Type': 'application/json', 'Origin': server.origin, 'X-Session-Token': server.token})
            resposta = con.getresponse()
            corpo = resposta.read()
            tipo = resposta.getheader('Content-Type', '')
            return resposta.status, json.loads(corpo) if tipo.startswith('application/json') else corpo
        finally:
            con.close()


class CongelamentoTest(Base):
    def test_pergunta_espera_cadastro_em_curso_sem_prender_as_conversas(self):
        soltar = self.segurar_trava()
        identifier = self.manager.perguntar({'caso': 'alpha', 'pergunta': 'Pergunta técnica sintética.'})['conversa']
        ctx = self.manager.contexts[identifier]
        esperar(lambda: any(e['tipo'] == 'aviso' and 'Aguardando o fim de um cadastro' in e['dados']['mensagem']
                            for e in ctx['events']), 5)
        time.sleep(0.3)
        inicio = time.monotonic()
        self.assertEqual(self.manager.listar('alpha')['conversas'][0]['estado'], 'preparando')
        self.manager.eventos(identifier)
        self.assertLess(time.monotonic() - inicio, 1, 'a espera do congelamento prendeu Conversas.lock')
        self.assertFalse((self.root / 'execucoes/alpha/R001').exists())
        soltar.set()
        esperar(lambda: ctx['meta'].get('turn_id'), 10)
        self.assertEqual(ctx['meta']['estado'], 'executando')
        self.assertEqual(ctx['meta']['rodada'], 'R001')

    def test_cancelar_enquanto_espera_nao_congela_nem_espera_o_prazo(self):
        self.segurar_trava()
        identifier = self.manager.perguntar({'caso': 'alpha', 'pergunta': 'Pergunta técnica sintética.'})['conversa']
        time.sleep(0.3)
        inicio = time.monotonic()
        self.manager.cancelar(identifier)
        conversa = aguardar_fim(self.manager, identifier, timeout=5)
        self.assertLess(time.monotonic() - inicio, 3)
        self.assertEqual(conversa['situacao']['codigo'], 'cancelado')
        self.assertFalse((self.root / 'execucoes/alpha/R001').exists())

    def test_congelamento_e_quem_segura_conversas_esperando_a_trava_nao_se_impedem(self):
        dentro, seguir = threading.Event(), threading.Event()
        original = codex_apuracao._criar_rodada

        def pausa(*args, **kwargs):
            dentro.set()
            seguir.wait(10)
            return original(*args, **kwargs)
        with mock.patch.object(codex_apuracao, '_criar_rodada', pausa):
            identifier = self.manager.perguntar({'caso': 'alpha', 'pergunta': 'Pergunta técnica sintética.'})['conversa']
            self.assertTrue(dentro.wait(5))
            feito = threading.Event()

            def gestao():  # same order as gerenciar and the trash: Conversas.lock, then the cadastro lock
                with self.manager.lock, _trava(self.root, espera=10):
                    feito.set()
            outra = threading.Thread(target=gestao, daemon=True)
            outra.start()
            time.sleep(0.3)
            inicio = time.monotonic()
            seguir.set()
            self.assertTrue(feito.wait(5))
            esperar(lambda: self.manager.contexts[identifier]['meta'].get('turn_id'), 5)
            self.assertLess(time.monotonic() - inicio, 3, 'congelamento e gestão ficaram esperando um pelo outro')
            outra.join(5)


class DocumentosNaConversaTest(Base):
    def setUp(self):
        super().setUp()
        self.chat = self.start()
        completar(self.manager, self.chat)
        self.lote = {'caso': 'alpha', 'conversa': self.chat, 'natureza': 'sinteticos', 'arquivos': [
            {'nome': 'assessoria.txt', 'base64': base64.b64encode(b'Contrato adicional. Valor total 246.\n').decode()}]}

    def test_conversa_conferida_fica_reservada_e_as_outras_andam(self):
        server = self.servidor()
        dentro, seguir = threading.Event(), threading.Event()
        original = rotas_conversa.receber_documentos

        def pausa(*args, **kwargs):
            dentro.set()
            seguir.wait(10)
            return original(*args, **kwargs)
        resultado = {}
        with mock.patch.object(rotas_conversa, 'receber_documentos', pausa):
            envio = threading.Thread(target=lambda: resultado.update(r=self.post(server, 'codex-documentos-cadastrar',
                                                                                 self.lote, prazo=30)), daemon=True)
            envio.start()
            self.assertTrue(dentro.wait(5))
            # Conversas.lock is free while the batch is registered: other conversations move on.
            self.assertTrue(self.manager.lock.acquire(timeout=1))
            self.manager.lock.release()
            inicio = time.monotonic()
            self.assertEqual(self.post(server, 'codex-eventos', {'conversa': self.chat})[0], 200)
            status, outra = self.post(server, 'codex-perguntar', {'caso': 'beta', 'pergunta': 'Outra apuração.'})
            self.assertEqual(status, 200, outra)
            self.assertLess(time.monotonic() - inicio, 3)
            # The checked conversation stays as checked: no new question until the batch is in.
            status, recusa = self.post(server, 'codex-perguntar', {'caso': 'alpha', 'conversa': self.chat,
                                                                   'pergunta': 'Pergunta no meio do cadastro.'})
            self.assertEqual(status, 400)
            self.assertIn('recebendo documentos', recusa['erro'])
            seguir.set()
            envio.join(10)
        status, recibo = resultado['r']
        self.assertEqual((status, recibo['novos'], recibo['corpus_id']), (200, 1, 'alpha_v2'))
        self.assertEqual(self.manager.contexts[self.chat]['documentos_em_cadastro'], 0)
        self.assertEqual(self.manager.contexts[self.chat]['meta']['rodadas'], ['R001'])
        status, previa = self.post(server, 'codex-corpus-previa', {'caso': 'alpha', 'conversa': self.chat})
        self.assertEqual((status, previa['corpus_novo']), (200, 'alpha_v2'))
        status, resposta = self.post(server, 'codex-perguntar', {'caso': 'alpha', 'conversa': self.chat,
                                                                 'pergunta': 'Continuar com o documento novo.',
                                                                 'atualizar_corpus': previa['solicitacao']})
        self.assertEqual(status, 200, resposta)

    def test_cadastro_recusado_libera_a_conversa(self):
        server = self.servidor()
        invalido = {**self.lote, 'arquivos': [{'nome': 'negado.exe', 'base64': 'eA=='}]}
        self.assertEqual(self.post(server, 'codex-documentos-cadastrar', invalido)[0], 400)
        self.assertEqual(self.manager.contexts[self.chat]['documentos_em_cadastro'], 0)
        ocupada = {**self.lote, 'conversa': self.chat}
        self.manager.contexts[self.chat]['busy'] = True  # a running execution is refused before any cadastro
        try:
            status, recusa = self.post(server, 'codex-documentos-cadastrar', ocupada)
        finally:
            self.manager.contexts[self.chat]['busy'] = False
        self.assertEqual(status, 400)
        self.assertIn('Aguarde o encerramento', recusa['erro'])
        self.assertEqual(self.manager.contexts[self.chat]['documentos_em_cadastro'], 0)
        self.assertEqual(self.post(server, 'codex-documentos-cadastrar', self.lote)[0], 200)


class FalsoOriginal:
    suffix = '.txt'

    def __init__(self, trava, visto):
        self.trava, self.visto = trava, visto

    def read_bytes(self):
        self.visto['leitura_com_trava'] = self.trava.locked()
        return b'original sintetico'


class FalsoHandler(rotas_downloads.RotasDownloads):
    def __init__(self):
        self.server = SimpleNamespace(cadastro_lock=threading.Lock(), root=Path('.'))
        self.enviados = []

    def _send(self, status, content, content_type='', extra=None):
        self.enviados.append((status, content, self.server.cadastro_lock.locked()))


class OriginaisTest(unittest.TestCase):
    def test_originais_do_caderno_diligencias_e_apuracao_lidos_dentro_e_enviados_fora(self):
        casos = (('apuracao-original', apuracao, 'original', {}),
                 ('diligencias-original', diligencias, 'original_resposta', {}),
                 ('caderno-original', caderno, 'original_registro', {'registro_id': 'N0001'}),
                 ('caderno-original', caderno, 'original_documento', {}))
        for operacao, modulo, funcao, dados in casos:
            with self.subTest(operacao=operacao, funcao=funcao):
                handler, visto = FalsoHandler(), {}
                original = FalsoOriginal(handler.server.cadastro_lock, visto)
                with mock.patch.object(modulo, funcao, return_value=original):
                    handler._baixar(operacao, dados, {'casos': None})
                self.assertTrue(visto['leitura_com_trava'], 'o original foi lido fora da trava')
                self.assertEqual(handler.enviados, [(200, b'original sintetico', False)])


class OriginalDaPassagemTest(Base):
    def test_original_da_passagem_lido_dentro_e_enviado_fora_da_trava(self):
        identifier = self.start()
        hit = self.manager.ferramenta(identifier, {'acao': 'buscar', 'consulta': 'Alfabeto'})[0]['resultados'][0]
        server = self.servidor()
        estados = {}
        ler, enviar = interface_pesquisa.Handler._ler_original, interface_pesquisa.Handler._send

        def ler_espiao(handler, *args):
            estados['leitura'] = handler.server.cadastro_lock.locked()
            return ler(handler, *args)

        def enviar_espiao(handler, status, content, content_type='application/json; charset=utf-8', *args, **kwargs):
            if content_type == 'application/octet-stream':
                estados['envio'] = handler.server.cadastro_lock.locked()
            return enviar(handler, status, content, content_type, *args, **kwargs)
        with mock.patch.object(interface_pesquisa.Handler, '_ler_original', ler_espiao), \
                mock.patch.object(interface_pesquisa.Handler, '_send', enviar_espiao):
            status, conteudo = self.post(server, 'original', {'caso': 'alpha', 'rodada': 'R001',
                                                              'referencia': hit['referencia_sqlite']})
        self.assertEqual(status, 200, conteudo)
        self.assertIn('Alfabeto'.encode('utf-8'), conteudo)
        self.assertEqual(estados, {'leitura': True, 'envio': False})
        self.manager.cancelar(identifier)
        self.assertNotIn(aguardar_fim(self.manager, identifier)['estado'], ACTIVE)


if __name__ == '__main__':
    unittest.main()
