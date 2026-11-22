"""Recursos do servidor sob carga (CONF-03): teto de conexões e conversas ociosas fora da memória.

- O servidor atende até ``MAXIMO_CONEXOES`` conexões ao mesmo tempo, uma thread cada; acima disso
  responde 503 na hora, sem abrir thread, e a vaga volta quando uma conexão termina. Um cliente lento
  acima do teto não atrasa o 503 dos outros e é fechado no prazo ou no teto de bytes (B1).
- A linha do pedido e os cabeçalhos têm prazo total, mesmo chegando um byte por vez; conexão parada
  sai no mesmo prazo e devolve a vaga.
- No modo piloto, um mesmo endereço de cliente (o do registro de acessos, com os proxies confiáveis)
  tem no máximo ``MAXIMO_POR_IP`` pedidos em curso; acima disso, 429 na hora, e os outros clientes
  seguem. Atrás de um proxy fora da lista o cliente não é conhecido e não há teto por endereço.
- Conversa ociosa sai da memória (tempo sem uso, e a mais antiga quando passa do teto) e volta do
  disco no próximo uso, como depois de uma reinicialização; conversa em execução ou recebendo
  documentos nunca sai.
Provedor simulado e dados sintéticos; sem rede externa nem modelo.
"""
import http.client
import json
import os
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

    def conectar(self):
        conexao = socket.create_connection(('127.0.0.1', self.server.server_port), timeout=5)
        self.addCleanup(conexao.close)
        return conexao

    @staticmethod
    def gotejar_ate_fechar(conexao, intervalo, prazo):
        """A byte every ``intervalo`` s (the headers never end) until the server closes the connection
        (sending fails); the seconds it took, or None after ``prazo``."""
        inicio = time.monotonic()
        while time.monotonic() - inicio < prazo:
            try:
                conexao.send(b'a')
            except OSError:
                return time.monotonic() - inicio
            time.sleep(intervalo)
        return None

    def em_paralelo(self, funcao, *args):
        resultado = []
        thread = threading.Thread(target=lambda: resultado.append(funcao(*args)), daemon=True)
        thread.start()
        self.addCleanup(thread.join, 15)
        return thread, resultado

    def test_cliente_lento_acima_do_teto_nao_atrasa_os_outros(self):
        self.parada(), self.parada()
        time.sleep(0.3)  # both slots taken
        with mock.patch.object(interface_pesquisa, 'PRAZO_RECUSA', 1.5):
            lenta = self.conectar()
            lenta.send(b'G')
            self.assertTrue(lenta.recv(1024).startswith(b'HTTP/1.1 503'))  # its 503 at once too
            thread, fechada = self.em_paralelo(self.gotejar_ate_fechar, lenta, 0.3, 10)
            time.sleep(0.3)
            for _ in range(3):  # B1: these waited for the slow one to stop (6 s and more)
                inicio = time.monotonic()
                self.assertEqual(self.saude(), (503, '2'))
                self.assertLess(time.monotonic() - inicio, 1)
            thread.join(12)
        self.assertIsNotNone(fechada[0], 'a conexão recusada e lenta não foi fechada')
        self.assertLess(fechada[0], 4)  # 1.5 s to read it, then closed

    def test_recusada_que_despeja_bytes_e_fechada_no_teto(self):
        self.parada(), self.parada()
        time.sleep(0.3)
        with mock.patch.object(interface_pesquisa, 'TETO_BYTES_RECUSA', 64 * 1024), \
                mock.patch.object(interface_pesquisa, 'PRAZO_RECUSA', 60):
            despejo = self.conectar()
            inicio = time.monotonic()
            with self.assertRaises(OSError):  # closed by the server: sending fails
                for _ in range(1000):  # 64 MB at most
                    despejo.sendall(b'x' * 65536)
            self.assertLess(time.monotonic() - inicio, 4)  # at the byte ceiling, long before the deadline
            self.assertEqual(self.saude(), (503, '2'))

    def test_cabecalhos_com_prazo_total_mesmo_gota_a_gota(self):
        with mock.patch.object(interface_pesquisa, 'PRAZO_CABECALHOS', 1.0):
            parada, gotejando = self.parada(), self.conectar()
            thread, fechada = self.em_paralelo(self.gotejar_ate_fechar, gotejando, 0.2, 10)
            time.sleep(0.4)
            self.assertEqual(self.saude(), (503, '2'))  # both slots taken
            thread.join(12)
            parada.settimeout(5)
            self.assertEqual(parada.recv(1), b'')  # the idle one: closed quietly, in the same deadline
            limite = time.monotonic() + 3
            while self.saude()[0] != 200:
                self.assertLess(time.monotonic(), limite, 'as vagas não voltaram depois do prazo dos cabeçalhos')
                time.sleep(0.1)
        # A byte every 0.2 s never trips the 60 s of each read; the deadline is for the headers in all.
        self.assertIsNotNone(fechada[0], 'a conexão que manda um byte por vez não foi fechada')
        self.assertLess(fechada[0], 3)

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


class TetoPorEnderecoTest(unittest.TestCase):
    def setUp(self):
        from modelo_pasta import copiar
        temp, self.root, _ = copiar('CodexIntegrationTest', integracao.CodexIntegrationTest.montar)
        self.addCleanup(temp.cleanup)
        ambiente = mock.patch.dict(os.environ, {'VLADO_ACESSO': '', 'VLADO_AMBIENTE': '', 'VLADO_CONFIAR_PROXY': '',
                                                'VLADO_PROXIES_CONFIAVEIS': '127.0.0.1/32'})
        ambiente.start()
        self.addCleanup(ambiente.stop)
        teto = mock.patch.object(interface_pesquisa, 'MAXIMO_POR_IP', 2)
        teto.start()
        self.addCleanup(teto.stop)
        self.server = interface_pesquisa.Servidor(('127.0.0.1', 0), self.root, modo='piloto', origem='https://vlado.test')
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (self.server.shutdown(), self.server.server_close(), thread.join(5)))

    def em_curso(self, cliente):
        """A request in course for ``cliente`` (behind the trusted proxy): its body never comes."""
        conexao = socket.create_connection(('127.0.0.1', self.server.server_port), timeout=10)
        self.addCleanup(conexao.close)
        linhas = ['POST /api/entrar HTTP/1.1', 'Host: vlado.test', 'Content-Type: application/json',
                  'Content-Length: 100', f'X-Forwarded-For: {cliente}', '', '']
        conexao.sendall('\r\n'.join(linhas).encode('ascii'))
        return conexao

    def saude(self, cliente=None):
        con = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        try:
            con.request('GET', '/saude', headers={'Host': 'vlado.test', **({'X-Forwarded-For': cliente} if cliente else {})})
            resposta = con.getresponse()
            corpo = resposta.read()
            return resposta.status, resposta.getheader('Retry-After'), corpo
        finally:
            con.close()

    def test_acima_do_teto_do_endereco_429_na_hora_e_os_outros_seguem(self):
        self.em_curso('203.0.113.7'), self.em_curso('203.0.113.7')
        time.sleep(0.3)
        inicio = time.monotonic()
        status, espera, corpo = self.saude('203.0.113.7')
        self.assertEqual((status, espera), (429, '2'))
        self.assertLess(time.monotonic() - inicio, 2)
        self.assertIn('Muitas requisições', json.loads(corpo)['erro'])
        self.assertEqual(self.saude('198.51.100.9')[0], 200)  # another client
        self.assertEqual(self.saude()[0], 200)  # straight to the Mesa: its own address

    def test_a_vaga_do_endereco_volta_quando_o_pedido_termina(self):
        conexoes = [self.em_curso('203.0.113.7'), self.em_curso('203.0.113.7')]
        time.sleep(0.3)
        self.assertEqual(self.saude('203.0.113.7')[0], 429)
        for conexao in conexoes:
            conexao.close()
        limite = time.monotonic() + 5
        while self.saude('203.0.113.7')[0] != 200:
            self.assertLess(time.monotonic(), limite, 'a vaga do endereço não voltou')
            time.sleep(0.1)
        # Nothing left counted (each request leaves the count just after its answer is sent).
        esperar(lambda: self.server._por_ip == {}, 5, f'contagem por endereço sobrou: {self.server._por_ip}')

    def test_atras_de_proxy_fora_da_lista_nao_ha_teto_por_endereco(self):
        with mock.patch.dict(os.environ, {'VLADO_PROXIES_CONFIAVEIS': ''}):
            self.em_curso('203.0.113.7'), self.em_curso('203.0.113.7'), self.em_curso('203.0.113.7')
            time.sleep(0.3)
            self.assertEqual(self.saude('203.0.113.7')[0], 200)  # all seem to come from the proxy: not limited


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
        class Parado:  # T1: the Windows clock ties within 16 ms; the order of use decides, never the id
            monotonic = staticmethod(lambda: 1000.0)

            def __getattr__(self, nome):
                return getattr(time, nome)
        segunda, terceira = self.copia(), self.copia()
        with mock.patch.object(codex_apuracao, 'time', Parado()), mock.patch.object(codex_apuracao, 'MAXIMO_CONTEXTOS', 2):
            self.manager.eventos(terceira)
            self.manager.eventos(segunda)
            self.manager.eventos(self.primeira)  # the least recently used goes first
        self.assertEqual(sorted(self.manager.contexts), sorted([self.primeira, segunda]))


if __name__ == '__main__':
    unittest.main()
