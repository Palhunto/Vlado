"""Local mode with accounts (installed Windows desk): first administrator, sign-in, sign-out, guest limits.

Plain HTTP on 127.0.0.1, so cookies are HttpOnly + SameSite=Strict but never Secure.
Reuses the synthetic cases alpha/beta of the integration fixture. No paid API.
"""
import http.client
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import acesso
import interface_pesquisa
import test_codex_integracao as integracao  # module import: its TestCase is not re-collected here
from test_acesso import SENHA, hasher_rapido
from interface_pesquisa import Servidor


class PrimeiroAdminStoreTest(unittest.TestCase):
    """The store guarantees one first administrator, even under concurrent calls."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        env = patch.dict(os.environ, {'VLADO_ACESSO': ''})
        env.start()
        self.addCleanup(env.stop)
        hasher_rapido(self)

    def test_cria_admin_com_senha_e_depois_recusa(self):
        self.assertTrue(acesso.primeiro_acesso_disponivel(self.root))
        conta = acesso.criar_primeiro_admin(self.root, 'Editora', 'editora', SENHA)
        self.assertEqual((conta['papel'], conta['situacao'], conta['login']), ('admin', 'ativa', 'editora'))
        self.assertFalse(acesso.primeiro_acesso_disponivel(self.root))
        with self.assertRaises(acesso.PrimeiroAcessoEncerrado):
            acesso.criar_primeiro_admin(self.root, 'Outra', 'outra', SENHA)
        sid, _, publica = acesso.entrar(self.root, 'editora', SENHA)
        self.assertEqual(acesso.sessao(self.root, sid)['papel'], 'admin')
        self.assertEqual(publica['login'], 'editora')
        self.assertIn('primeiro_admin', [e['tipo'] for e in acesso.eventos(self.root)])

    def test_senha_curta_e_login_invalido_recusados_sem_gravar(self):
        with self.assertRaises(ValueError):
            acesso.criar_primeiro_admin(self.root, 'Editora', 'editora', 'curta')
        with self.assertRaises(ValueError):
            acesso.criar_primeiro_admin(self.root, 'Editora', 'X', SENHA)
        self.assertTrue(acesso.primeiro_acesso_disponivel(self.root))

    def test_existencia_de_qualquer_conta_encerra_o_primeiro_acesso(self):
        acesso.criar_conta(self.root, 'Ana', 'ana', casos=['alpha'])
        self.assertFalse(acesso.primeiro_acesso_disponivel(self.root))
        with self.assertRaises(acesso.PrimeiroAcessoEncerrado):
            acesso.criar_primeiro_admin(self.root, 'Editora', 'editora', SENHA)

    def test_corrida_entre_duas_criacoes_deixa_um_unico_admin(self):
        barreira, resultados = threading.Barrier(6), []

        def criar(numero):
            barreira.wait()
            try:
                acesso.criar_primeiro_admin(self.root, f'Pessoa {numero}', f'pessoa{numero}', SENHA)
                resultados.append('ok')
            except acesso.PrimeiroAcessoEncerrado:
                resultados.append('recusado')
        fios = [threading.Thread(target=criar, args=(n,)) for n in range(6)]
        for fio in fios:
            fio.start()
        for fio in fios:
            fio.join(30)
        self.assertEqual(sorted(resultados), ['ok'] + ['recusado'] * 5)
        self.assertEqual(len(acesso.listar(self.root)), 1)


class LocalContasHttp(unittest.TestCase):
    def setUp(self):
        integracao.CodexIntegrationTest.setUp(self)
        env = patch.dict(os.environ, {'VLADO_ACESSO': '', 'VLADO_AMBIENTE': '', 'VLADO_CONFIAR_PROXY': ''})
        env.start()
        self.addCleanup(env.stop)
        hasher_rapido(self)
        acesso.limpar_limites()
        self.server = Servidor(('127.0.0.1', 0), self.root, modo='local-contas')
        self.server.conversas.close()
        self.server.conversas = self.manager
        self.origem = f'http://127.0.0.1:{self.server.server_port}'
        self.host = f'127.0.0.1:{self.server.server_port}'
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (self.server.shutdown(), self.server.server_close(), thread.join(3)))

    def request(self, method, path, body=None, headers=None):
        con = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=15)
        con.request(method, path, body, {'Host': self.host, **(headers or {})})
        response = con.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        con.close()
        return result

    def publico(self, operation, data, origin='padrao', host=None):
        headers = {'Content-Type': 'application/json'}
        if origin:
            headers['Origin'] = self.origem if origin == 'padrao' else origin
        if host:
            headers['Host'] = host
        status, headers, body = self.request('POST', '/api/' + operation, json.dumps(data), headers)
        return status, headers, json.loads(body or b'{}')

    def criar_admin(self, login='editora'):
        return self.publico('primeiro-admin', {'nome': 'Editora', 'login': login, 'senha': SENHA,
                                               'confirmacao': SENHA})

    def entrar(self, login='editora', senha=SENHA):
        status, headers, body = self.publico('entrar', {'login': login, 'senha': senha})
        self.assertEqual(status, 200, body)
        return headers['Set-Cookie'], body['csrf']

    def post(self, sessao, operation, data):
        cookie, csrf = sessao
        headers = {'Content-Type': 'application/json', 'Cookie': cookie.split(';')[0], 'X-Session-Token': csrf,
                   'Origin': self.origem}
        status, _, body = self.request('POST', '/api/' + operation, json.dumps(data), headers)
        return status, json.loads(body or b'{}')


class PrimeiraAberturaTest(LocalContasHttp):
    def test_sem_contas_toda_pagina_leva_a_criar_administrador(self):
        for caminho in ('/', '/entrar'):
            status, headers, _ = self.request('GET', caminho)
            self.assertEqual((status, headers.get('Location')), (303, '/primeiro-acesso'), caminho)
        status, headers, corpo = self.request('GET', '/primeiro-acesso')
        self.assertEqual(status, 200)
        self.assertIn(b'primeiro-secao', corpo)
        self.assertEqual(headers['Cache-Control'], 'no-store')
        status, _, corpo = self.request('GET', '/api/primeiro-acesso')
        self.assertEqual((status, json.loads(corpo)), (200, {'disponivel': True}))
        self.assertEqual(self.request('GET', '/api/catalogo')[0], 401)

    def test_cria_admin_uma_vez_e_a_tela_some_de_vez(self):
        status, _, corpo = self.criar_admin()
        self.assertEqual(status, 200, corpo)
        self.assertEqual(corpo['login'], 'editora')
        status, _, corpo = self.criar_admin('outra')
        self.assertEqual((status, corpo.get('codigo')), (410, 'primeiro_acesso_encerrado'))
        status, headers, _ = self.request('GET', '/primeiro-acesso')
        self.assertEqual((status, headers.get('Location')), (303, '/entrar'))
        self.assertEqual(self.request('GET', '/entrar')[0], 200)
        self.assertEqual(json.loads(self.request('GET', '/api/primeiro-acesso')[2]), {'disponivel': False})
        self.assertEqual([c['login'] for c in acesso.listar(self.root)], ['editora'])

    def test_recusa_origem_host_ou_cliente_nao_local(self):
        dados = {'nome': 'E', 'login': 'editora', 'senha': SENHA, 'confirmacao': SENHA}
        for origem in ('http://localhost:%d' % self.server.server_port, 'http://evil.test', None):
            self.assertEqual(self.publico('primeiro-admin', dados, origin=origem)[0], 403, origem)
        self.assertEqual(self.publico('primeiro-admin', dados, host='evil.test')[0], 403)
        self.assertEqual(self.publico('primeiro-admin', dados, host=f'localhost:{self.server.server_port}')[0], 403)
        with patch.object(interface_pesquisa.Handler, '_endereco_socket', return_value='192.168.0.20'), \
                patch.dict(os.environ, {'VLADO_CONFIAR_PROXY': '1'}):
            status, _, _ = self.request('POST', '/api/primeiro-admin', json.dumps(dados), {
                'Content-Type': 'application/json', 'Origin': self.origem, 'X-Forwarded-For': '127.0.0.1'})
            self.assertEqual(status, 403)
        self.assertTrue(acesso.primeiro_acesso_disponivel(self.root))

    def test_senha_curta_ou_confirmacao_diferente_nao_cria_conta(self):
        status, _, corpo = self.publico('primeiro-admin', {'nome': 'E', 'login': 'editora', 'senha': 'curta',
                                                          'confirmacao': 'curta'})
        self.assertEqual((status, corpo.get('codigo')), (400, 'senha_invalida'))
        status, _, corpo = self.publico('primeiro-admin', {'nome': 'E', 'login': 'editora', 'senha': SENHA,
                                                          'confirmacao': SENHA + 'x'})
        self.assertEqual((status, corpo.get('codigo')), (400, 'senha_diferente'))
        self.assertTrue(acesso.primeiro_acesso_disponivel(self.root))

    def test_duas_criacoes_simultaneas_por_http_deixam_um_admin(self):
        barreira, estados = threading.Barrier(4), []

        def criar(numero):
            barreira.wait()
            estados.append(self.criar_admin(f'pessoa{numero}')[0])
        fios = [threading.Thread(target=criar, args=(n,)) for n in range(4)]
        for fio in fios:
            fio.start()
        for fio in fios:
            fio.join(30)
        self.assertEqual(sorted(estados), [200, 410, 410, 410])
        self.assertEqual(len(acesso.listar(self.root)), 1)


class CorpoDeRecusaTest(LocalContasHttp):
    """A refused POST drops a small body before answering; on Windows, closing with unread bytes
    sends a TCP reset and the client loses the answer (WinError 10053). A large body is never read."""

    def cru(self, host, comprimento, origem=None):
        """Raw POST, headers only: returns the open socket (http.client sends headers and body together)."""
        cabecalho = (f'POST /api/primeiro-admin HTTP/1.1\r\nHost: {host}\r\nContent-Type: application/json\r\n'
                     f'Origin: {origem or self.origem}\r\nContent-Length: {comprimento}\r\n\r\n')
        conexao = socket.create_connection(('127.0.0.1', self.server.server_port), timeout=15)
        self.addCleanup(conexao.close)
        conexao.sendall(cabecalho.encode('ascii'))
        return conexao

    @staticmethod
    def resposta(conexao):
        dados = b''
        while parte := conexao.recv(65536):
            dados += parte
        return dados.split(b'\r\n', 1)[0]

    def nada_antes_do_corpo(self, conexao):
        conexao.settimeout(0.3)
        with self.assertRaises(TimeoutError, msg='respondeu sem ler o corpo pequeno'):
            conexao.recv(1)
        conexao.settimeout(15)

    def test_host_recusado_le_corpo_pequeno_antes_de_responder(self):
        corpo = json.dumps({'nome': 'E', 'login': 'editora', 'senha': SENHA, 'confirmacao': SENHA}).encode()
        for host in (f'localhost:{self.server.server_port}', 'evil.test'):
            with self.subTest(host=host):
                conexao = self.cru(host, len(corpo))
                self.nada_antes_do_corpo(conexao)
                conexao.sendall(corpo)
                self.assertEqual(self.resposta(conexao), b'HTTP/1.0 403 Forbidden')
        self.assertTrue(acesso.primeiro_acesso_disponivel(self.root))

    def test_operacao_publica_com_corpo_acima_de_4096_descarta_ate_32_kb(self):
        conexao = self.cru(self.host, 5000)
        self.nada_antes_do_corpo(conexao)
        conexao.sendall(b' ' * 5000)
        self.assertEqual(self.resposta(conexao), b'HTTP/1.0 400 Bad Request')

    def test_corpo_grande_nunca_e_lido(self):
        # Answered from the headers alone: the server does not wait for (or read) 10 MB.
        for host, status in ((self.host, b'400 Bad Request'), ('evil.test', b'403 Forbidden'),
                             (f'localhost:{self.server.server_port}', b'403 Forbidden')):
            with self.subTest(host=host):
                conexao = self.cru(host, 10 * 1024 * 1024)
                self.assertEqual(self.resposta(conexao), b'HTTP/1.0 ' + status)


class SessaoLocalTest(LocalContasHttp):
    def setUp(self):
        super().setUp()
        self.assertEqual(self.criar_admin()[0], 200)

    def test_sem_sessao_tudo_bloqueado(self):
        status, headers, _ = self.request('GET', '/')
        self.assertEqual((status, headers.get('Location')), (303, '/entrar'))
        self.assertEqual(self.request('GET', '/api/catalogo')[0], 401)
        self.assertEqual(self.request('GET', '/api/sessao')[0], 401)
        for operacao in ('ambiente', 'cadastrar', 'contas-listar', 'codex-desligar'):
            status, _, _ = self.request('POST', '/api/' + operacao, '{}',
                                        {'Content-Type': 'application/json', 'Origin': self.origem})
            self.assertEqual(status, 401, operacao)

    def test_login_com_cookie_local_sem_secure_e_logout(self):
        cookie, csrf = self.entrar()
        self.assertIn('HttpOnly', cookie)
        self.assertIn('SameSite=Strict', cookie)
        self.assertNotIn('Secure', cookie)
        sessao = (cookie, csrf)
        status, headers, corpo = self.request('GET', '/', headers={'Cookie': cookie.split(';')[0]})
        self.assertEqual(status, 200)
        self.assertIn(b'data-modo="local-contas"', corpo)
        self.assertIn(b'data-papel="admin"', corpo)
        self.assertNotIn('Strict-Transport-Security', headers)
        self.assertEqual(self.post(sessao, 'ambiente', {})[0], 200)
        status, contas = self.post(sessao, 'contas-listar', {})
        self.assertEqual(status, 200, contas)
        self.assertEqual(self.post(sessao, 'sessao-sair', {})[0], 200)
        self.assertEqual(self.post(sessao, 'ambiente', {})[0], 401)

    def test_logout_apaga_cookie_sem_secure(self):
        cookie, csrf = self.entrar()
        con = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=15)
        con.request('POST', '/api/sessao-sair', '{}', {'Host': self.host, 'Content-Type': 'application/json',
                    'Cookie': cookie.split(';')[0], 'X-Session-Token': csrf, 'Origin': self.origem})
        resposta = con.getresponse()
        apagar = resposta.getheader('Set-Cookie')
        resposta.read()
        con.close()
        self.assertIn('Max-Age=0', apagar)
        self.assertIn('HttpOnly', apagar)
        self.assertNotIn('Secure', apagar)

    def test_senha_errada_e_limitada(self):
        for _ in range(acesso.FALHAS_BLOQUEIO - 1):
            self.assertEqual(self.publico('entrar', {'login': 'editora', 'senha': 'errada-errada-1'})[0], 401)
        self.assertEqual(self.publico('entrar', {'login': 'editora', 'senha': 'errada-errada-1'})[0], 429)

    def test_convidado_restrito_ao_caso_e_a_perguntar(self):
        admin = self.entrar()
        status, corpo = self.post(admin, 'contas-criar', {'nome': 'Ana', 'login': 'ana', 'casos': ['alpha'],
                                                          'cota_diaria': 3})
        self.assertEqual(status, 200, corpo)
        self.assertTrue(corpo['link'].startswith(self.origem + '/ativar/'))
        token = corpo['link'].rsplit('/', 1)[1]
        self.assertEqual(self.publico('ativar', {'token': token, 'senha': SENHA})[0], 200)
        ana = self.entrar('ana')
        _, _, corpo = self.request('GET', '/', headers={'Cookie': ana[0].split(';')[0]})
        self.assertIn(b'data-papel="convidado"', corpo)
        for operacao in ('cadastrar', 'ambiente', 'contas-listar', 'codex-desligar', 'ia-config-salvar',
                         'caderno-listar', 'gerenciar-listar'):
            status, _ = self.post(ana, operacao, {'caso': 'alpha'})
            self.assertEqual(status, 403, operacao)
        status, corpo = self.post(ana, 'codex-listar', {'caso': 'beta'})
        self.assertEqual((status, corpo.get('codigo')), (403, 'caso_nao_liberado'))
        self.assertEqual(self.post(ana, 'codex-listar', {'caso': 'alpha'})[0], 200)
        dados = json.loads(self.request('GET', '/api/catalogo', headers={'Cookie': ana[0].split(';')[0]})[2])
        self.assertEqual([c['id'] for c in dados['casos']], ['alpha'])

    def test_admin_pode_encerrar_o_servico_local(self):
        handler = interface_pesquisa.Handler.__new__(interface_pesquisa.Handler)
        handler.server = self.server
        self.assertIsNone(handler._negado('codex-desligar', {}, {'papel': 'admin'}))
        self.assertIsNotNone(handler._negado('codex-desligar', {}, {'papel': 'convidado', 'casos': []}))


class ModosTest(unittest.TestCase):
    def test_modo_invalido_recusado(self):
        with self.assertRaises(ValueError):
            Servidor(('127.0.0.1', 0), modo='aberto')


if __name__ == '__main__':
    unittest.main()
