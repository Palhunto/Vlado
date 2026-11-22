"""Envio de documentos em fluxo e prazo do corpo do pedido (CONF-03, parte 2).

- Lote em fluxo (``application/vnd.vlado.lote``, nas operações ``cadastrar`` e
  ``codex-documentos-cadastrar``): uma linha com o manifesto em JSON e depois os bytes dos arquivos
  como são, sem base64. Os bytes vão para o disco em blocos e chegam iguais ao caso.
- Nomes, tamanhos e total são conferidos antes de ler qualquer byte de conteúdo; manifesto errado,
  sessão errada ou tamanho que não confere recusam sem criar lote, e a resposta chega ao cliente.
- Corpo de qualquer pedido com taxa mínima: um corpo mandado um byte por vez é fechado no prazo e a
  vaga volta; um envio lento, mas acima da taxa, passa mesmo levando mais que o prazo-base.
Dados sintéticos; servidor local em 127.0.0.1, sem rede externa nem modelo.
"""
import http.client
import json
from pathlib import Path
import socket
import sys
import threading
import time
import unittest
from unittest import mock

TESTES = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTES.parent / 'scripts'))
import interface_pesquisa  # noqa: E402
import rotas_documentos  # noqa: E402
from modelo_pasta import copiar  # noqa: E402
import test_codex_integracao as integracao  # noqa: E402

TIPO = rotas_documentos.TIPO_LOTE


class Base(unittest.TestCase):
    maximo_conexoes = 96

    def setUp(self):
        temp, self.root, _ = copiar('CodexIntegrationTest', integracao.CodexIntegrationTest.montar)
        self.addCleanup(temp.cleanup)
        with mock.patch.object(interface_pesquisa, 'MAXIMO_CONEXOES', self.maximo_conexoes):
            self.server = interface_pesquisa.Servidor(('127.0.0.1', 0), self.root)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (self.server.shutdown(), self.server.server_close(), thread.join(5)))

    def conectar(self):
        conexao = socket.create_connection(('127.0.0.1', self.server.server_port), timeout=60)
        self.addCleanup(conexao.close)
        return conexao

    def cabecalhos(self, tamanho, caminho='/api/cadastrar', tipo=TIPO, token=None):
        linhas = [f'POST {caminho} HTTP/1.1', f'Host: 127.0.0.1:{self.server.server_port}',
                  f'Content-Type: {tipo}', f'Content-Length: {tamanho}', f'Origin: {self.server.origin}',
                  f'X-Session-Token: {token or self.server.token}', '', '']
        return '\r\n'.join(linhas).encode('ascii')

    @staticmethod
    def lote(arquivos, **opcoes):
        manifesto = {'caso': 'alpha', 'natureza': 'sinteticos', **opcoes,
                     'arquivos': [{'nome': nome, 'tamanho': len(conteudo)} for nome, conteudo in arquivos]}
        return json.dumps(manifesto, ensure_ascii=False).encode('utf-8') + b'\n' + b''.join(c for _, c in arquivos)

    def enviar(self, corpo, pedaco=None, pausa=0.0, **cabecalhos):
        """(status, JSON answer) of a raw POST, the body sent in ``pedaco`` bytes every ``pausa`` s."""
        conexao = self.conectar()
        conexao.sendall(self.cabecalhos(len(corpo), **cabecalhos))
        for inicio in range(0, len(corpo), pedaco or len(corpo) or 1):
            conexao.sendall(corpo[inicio:inicio + (pedaco or len(corpo))])
            time.sleep(pausa)
        resposta = http.client.HTTPResponse(conexao)
        resposta.begin()
        return resposta.status, json.loads(resposta.read() or b'{}')

    def lotes_na_fila(self):
        pasta = self.root / 'casos/.fila'
        return sorted(p.name for p in pasta.iterdir() if p.is_dir() and not p.name.startswith('.')) if pasta.is_dir() else []

    def original(self, nome, inicio=False):
        casa = (lambda n: n.startswith(nome)) if inicio else (lambda n: n.endswith(nome))
        achados = [p for p in (self.root / 'casos/alpha/cadastros').rglob('*') if p.is_file() and casa(p.name)
                   and p.parent.name == 'originais']
        self.assertEqual(len(achados), 1, achados)
        return achados[0].read_bytes()


class EnvioEmFluxoTest(Base):
    def test_lote_em_fluxo_chega_igual_ao_caso_em_blocos(self):
        grande = bytes(range(256)) * 40 + 'Fim sintético: relatório.\n'.encode('utf-8')  # ~10 KB, every byte value
        arquivos = [('relatório final.txt', 'Relatório sintético. Valor 456.\n'.encode('utf-8')),
                    ('dados.bin.txt', grande)]
        with mock.patch.object(rotas_documentos, 'BLOCO', 1000):  # many blocks for one file
            status, resposta = self.enviar(self.lote(arquivos))
        self.assertEqual(status, 200, resposta)
        self.assertEqual(resposta['corpus_id'], 'alpha_v2')
        # The case keeps each file byte for byte (its name normalized: D002_relatório_final.txt, D003_dados_bin.txt).
        for numero, (_, conteudo) in enumerate(arquivos, start=2):
            self.assertEqual(self.original(f'D{numero:03}_', inicio=True), conteudo)

    def test_o_mesmo_lote_em_json_continua_aceito(self):
        import base64
        corpo = json.dumps({'caso': 'alpha', 'natureza': 'sinteticos', 'arquivos': [
            {'nome': 'em_json.txt', 'base64': base64.b64encode(b'Documento sintetico em JSON.\n').decode('ascii')}]})
        status, resposta = self.enviar(corpo.encode('utf-8'), tipo='application/json')
        self.assertEqual(status, 200, resposta)
        self.assertEqual(self.original('em_json.txt'), b'Documento sintetico em JSON.\n')

    def test_manifesto_errado_recusa_antes_de_ler_o_conteudo_e_a_resposta_chega(self):
        conteudo = b'Documento sintetico.\n'
        casos = {
            'tamanho que não confere': (self.lote([('a.txt', conteudo)])[:-3], 'não confere'),
            'sem a linha do manifesto': (b'{"caso": "alpha"' + b'x' * 100, 'manifesto em JSON'),
            'base64 no fluxo': (json.dumps({'caso': 'alpha', 'arquivos': [{'nome': 'a.txt', 'tamanho': 21, 'base64': ''}]})
                                .encode() + b'\n' + conteudo, 'sem base64'),
            'nome com caminho': (self.lote([('../a.txt', conteudo)]), 'Nome de arquivo inválido'),
            'acima de 50 MB': (json.dumps({'caso': 'alpha', 'arquivos': [{'nome': 'a.txt', 'tamanho': 60 * 1024 * 1024}]})
                               .encode() + b'\n' + conteudo, 'excede 50 MB'),
        }
        for nome, (corpo, mensagem) in casos.items():
            with self.subTest(nome):
                status, resposta = self.enviar(corpo)
                self.assertEqual(status, 400, resposta)
                self.assertIn(mensagem, resposta['erro'])
                self.assertEqual(self.lotes_na_fila(), [])  # nothing queued, nothing written

    def test_manifesto_recusado_responde_e_fecha_logo_sem_esperar_o_resto(self):
        # The rest of the body never comes: the answer arrives and the slot is free in well under the
        # 10 s of the body's deadline (the Coruja's ressalva 2).
        linha = json.dumps({'caso': 'alpha', 'arquivos': [{'nome': 'a.txt', 'tamanho': 10}]}).encode() + b'\n'
        conexao = self.conectar()
        conexao.sendall(self.cabecalhos(len(linha) + 100000) + linha)
        inicio = time.monotonic()
        resposta = http.client.HTTPResponse(conexao)
        resposta.begin()
        self.assertEqual(resposta.status, 400)
        self.assertIn('não confere', json.loads(resposta.read())['erro'])
        conexao.settimeout(5)
        try:
            while conexao.recv(65536):
                pass
        except ConnectionError:
            pass  # closed with what was unread: a reset after the answer
        self.assertLess(time.monotonic() - inicio, 2)

    def test_a_mesa_anuncia_o_envio_em_fluxo_e_a_fila_por_caso(self):
        # The page uses the stream only when the server says so (an older server keeps the JSON upload).
        con = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        try:
            con.request('GET', '/api/integracao', headers={'Cookie': f'apuracao_session={self.server.token}'})
            resposta = con.getresponse()
            corpo = json.loads(resposta.read())
        finally:
            con.close()
        self.assertEqual(resposta.status, 200, corpo)
        self.assertIs(corpo['envio_fluxo'], True)
        self.assertIs(corpo['fila_por_caso'], True)

    def test_taxa_minima_padrao_deixa_passar_64_kbit_s(self):
        self.assertLessEqual(interface_pesquisa.TAXA_MINIMA_CORPO, 8 * 1024)  # weak 3G or EDGE still sends

    def test_sessao_errada_nao_le_o_lote(self):
        status, resposta = self.enviar(self.lote([('a.txt', b'Documento sintetico.\n')]), token='outra')
        self.assertEqual(status, 403, resposta)
        self.assertEqual(self.lotes_na_fila(), [])

    def test_lote_em_fluxo_so_nas_operacoes_de_envio(self):
        status, _ = self.enviar(self.lote([('a.txt', b'x\n')]), caminho='/api/buscar')
        self.assertEqual(status, 403)  # elsewhere the batch type is not JSON: refused like any other type


class PrazoDoCorpoTest(Base):
    maximo_conexoes = 2

    @staticmethod
    def gotejar_ate_fechar(conexao, intervalo, prazo):
        inicio = time.monotonic()
        while time.monotonic() - inicio < prazo:
            try:
                conexao.send(b'a')
            except OSError:
                return time.monotonic() - inicio
            time.sleep(intervalo)
        return None

    def test_corpo_gota_a_gota_fecha_no_prazo_e_devolve_a_vaga(self):
        # The Coruja's case: a POST declaring 5000 bytes, sent a byte at a time, held its slot (16 s and more).
        with mock.patch.object(interface_pesquisa, 'PRAZO_CORPO', 1.0), \
                mock.patch.object(interface_pesquisa, 'TAXA_MINIMA_CORPO', 1000):
            fechadas = []
            for _ in range(2):  # both slots
                conexao = self.conectar()
                conexao.sendall(self.cabecalhos(5000, caminho='/api/buscar', tipo='application/json'))
                fechadas.append(conexao)
            inicio = time.monotonic()
            tempos = []
            threads = [threading.Thread(target=lambda c=c: tempos.append(self.gotejar_ate_fechar(c, 0.2, 15)), daemon=True)
                       for c in fechadas]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(20)
        self.assertEqual(len(tempos), 2)
        self.assertTrue(all(t is not None and t < 4 for t in tempos), tempos)  # about 1 s, never the 60 s of each read
        limite = inicio + 8
        while True:
            con = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
            con.request('GET', '/saude')
            estado = con.getresponse().status
            con.close()
            if estado == 200:
                break
            self.assertLess(time.monotonic(), limite, 'as vagas não voltaram depois do prazo do corpo')
            time.sleep(0.1)

    def test_envio_lento_acima_da_taxa_passa_mesmo_depois_do_prazo_base(self):
        conteudo = b'Documento sintetico lento. ' * 300  # 8 KB
        with mock.patch.object(interface_pesquisa, 'PRAZO_CORPO', 0.5), \
                mock.patch.object(interface_pesquisa, 'TAXA_MINIMA_CORPO', 2000):
            inicio = time.monotonic()
            status, resposta = self.enviar(self.lote([('lento.txt', conteudo)]), pedaco=400, pausa=0.05)  # ~8 KB/s
        self.assertGreater(time.monotonic() - inicio, 0.5)  # longer than the base deadline
        self.assertEqual(status, 200, resposta)
        self.assertEqual(self.original('lento.txt'), conteudo)


if __name__ == '__main__':
    unittest.main()
