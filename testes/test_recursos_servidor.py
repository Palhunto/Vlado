"""Recursos do servidor sob carga (CONF-03): teto de conexões e conversas ociosas fora da memória.

- O servidor atende até ``MAXIMO_CONEXOES`` conexões ao mesmo tempo, uma thread cada; acima disso
  responde 503 na hora, sem abrir thread, e a vaga volta quando uma conexão termina.
- Conversa ociosa sai da memória (tempo sem uso, e a mais antiga quando passa do teto) e volta do
  disco no próximo uso, como depois de uma reinicialização; conversa em execução ou recebendo
  documentos nunca sai.
Provedor simulado e dados sintéticos; sem rede externa nem modelo.
"""
import http.client
import json
from pathlib import Path
import shutil
import socket
import sys
import threading
import time
import unittest
from unittest import mock
import uuid

TESTES = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTES.parent / 'scripts'))
from agente_fluxo_fixture import completar, esperar  # noqa: E402
import codex_apuracao  # noqa: E402
import interface_pesquisa  # noqa: E402
import test_codex_integracao as integracao  # noqa: E402
import test_registros as fixtures  # noqa: E402


class TetoDeConexoesTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.RegistrosTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        with mock.patch.object(interface_pesquisa, 'MAXIMO_CONEXOES', 2):
            self.server = interface_pesquisa.Servidor(('127.0.0.1', 0), self.fixture.root)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (self.server.shutdown(), self.server.server_close(), thread.join(5)))

    def parada(self):
        """A connection that sends nothing: its thread waits for the request line."""
        conexao = socket.create_connection(('127.0.0.1', self.server.server_port), timeout=10)
        self.addCleanup(conexao.close)
        return conexao

    def saude(self):
        con = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        try:
            con.request('GET', '/saude')
            resposta = con.getresponse()
            resposta.read()
            return resposta.status, resposta.getheader('Retry-After')
        finally:
            con.close()

    def test_acima_do_teto_503_na_hora_e_a_vaga_volta(self):
        self.assertEqual(self.saude()[0], 200)
        primeira, segunda = self.parada(), self.parada()
        time.sleep(0.3)  # both are being handled (each holds a thread)
        inicio = time.monotonic()
        self.assertEqual(self.saude(), (503, '2'))
        self.assertLess(time.monotonic() - inicio, 2)
        primeira.close()
        segunda.close()
        limite = time.monotonic() + 10
        while self.saude()[0] != 200:
            self.assertLess(time.monotonic(), limite, 'a vaga não voltou depois de fechar as conexões')
            time.sleep(0.1)


class ConversasOciosasTest(unittest.TestCase):
    start = integracao.CodexIntegrationTest.start

    def setUp(self):
        integracao.CodexIntegrationTest.setUp(self)
        self.primeira = self.start()  # one real question, answered by the simulated provider
        completar(self.manager, self.primeira)
        esperar(lambda: not self.manager.contexts[self.primeira].get('busy'))

    def copia(self):
        """Another finished conversation on disk: the first one's folder under a new id (no thread)."""
        novo = uuid.uuid4().hex
        origem, destino = self.manager._path(self.primeira), self.manager._path(novo)
        shutil.copytree(origem, destino)
        meta = json.loads((destino / 'conversa.json').read_text(encoding='utf-8'))
        meta.update(id=novo, thread_id=None, turn_id=None)
        (destino / 'conversa.json').write_text(json.dumps(meta, ensure_ascii=False), encoding='utf-8')
        self.manager.eventos(novo)  # loaded into memory
        return novo

    def test_ociosa_sai_da_memoria_e_volta_igual_do_disco(self):
        eventos = self.manager.eventos(self.primeira)['eventos']
        segunda = self.copia()
        with mock.patch.object(codex_apuracao, 'OCIOSO_CONTEXTO', 0):
            self.manager.eventos(segunda)  # any use sweeps the idle ones
        self.assertNotIn(self.primeira, self.manager.contexts)
        self.assertIn(segunda, self.manager.contexts)
        self.assertEqual(self.manager.eventos(self.primeira)['eventos'], eventos)  # read again from disk
        self.assertIn(self.primeira, self.manager.contexts)

    def test_em_execucao_ou_recebendo_documentos_nunca_sai(self):
        reservada, ociosa = self.copia(), self.copia()
        self.manager.contexts[reservada]['documentos_em_cadastro'] = 1
        self.addCleanup(self.manager.contexts[reservada].update, documentos_em_cadastro=0)
        ocupada = uuid.uuid4().hex  # an execution in course (as perguntar leaves it while the stages run)
        self.manager.contexts[ocupada] = {'meta': {'id': ocupada, 'estado': 'executando', 'caso': 'alpha'},
                                          'busy': True, 'events': []}
        self.addCleanup(self.manager.contexts.pop, ocupada, None)
        with mock.patch.object(codex_apuracao, 'OCIOSO_CONTEXTO', 0), mock.patch.object(codex_apuracao, 'MAXIMO_CONTEXTOS', 0):
            self.manager.eventos(self.primeira)
        self.assertEqual(sorted(self.manager.contexts), sorted([self.primeira, reservada, ocupada]))
        self.assertNotIn(ociosa, self.manager.contexts)

    def test_acima_do_teto_sai_a_menos_usada(self):
        segunda, terceira = self.copia(), self.copia()
        with mock.patch.object(codex_apuracao, 'MAXIMO_CONTEXTOS', 2):
            self.manager.eventos(terceira)
            self.manager.eventos(segunda)
            self.manager.eventos(self.primeira)  # the least recently used goes first
        self.assertEqual(sorted(self.manager.contexts), sorted([self.primeira, segunda]))


if __name__ == '__main__':
    unittest.main()
