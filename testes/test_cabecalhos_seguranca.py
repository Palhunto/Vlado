"""SEG-06: nenhuma resposta revela a versão do Python ou do servidor, HSTS com includeSubDomains (sem preload) e a conexão do Caddy para a
Mesa expira antes da Mesa. Parte HTTP (a Mesa em modo piloto de verdade, fixture de test_autorizacao) e parte de texto/validação dos
dois Caddyfiles."""
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import unittest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_autorizacao import Http, ORIGEM

HSTS = 'max-age=31536000; includeSubDomains'
CADDYFILES = ('deploy/Caddyfile', 'deploy/Caddyfile.interno')
SEM_VERSAO = re.compile(r'(?i)python|basehttp|\d+\.\d+\.\d+')


class RespostasDaMesaTest(Http):
    def assertSemServer(self, cabecalhos, onde):
        nomes = {k.lower() for k in cabecalhos}
        self.assertNotIn('server', nomes, f'{onde}: cabeçalho Server presente: {cabecalhos.get("Server")}')
        for nome, valor in cabecalhos.items():
            self.assertIsNone(re.search(r'(?i)python|basehttp', f'{nome}: {valor}'), f'{onde}: {nome}: {valor}')

    def test_nenhuma_resposta_leva_o_cabecalho_server_nem_a_versao_do_python(self):
        for metodo, caminho, corpo in (('GET', '/saude', None), ('GET', '/entrar', None), ('GET', '/', None),
                                       ('GET', '/api/sessao', None), ('GET', '/nao-existe-xyz', None),
                                       ('GET', '/style.css', None), ('GET', '/%2e%2e/etc/passwd', None),
                                       ('POST', '/api/entrar', '{"login": "x", "senha": "y"}'),
                                       ('POST', '/api/operacao-que-nao-existe', '{}')):
            with self.subTest(metodo=metodo, caminho=caminho):
                status, cabecalhos, _ = self.request(metodo, caminho, corpo, {'Origin': ORIGEM, 'Content-Type': 'application/json'} if corpo else None)
                self.assertSemServer(cabecalhos, f'{metodo} {caminho} ({status})')

    def test_resposta_de_erro_do_proprio_servidor_http_tambem_nao_revela_nada(self):
        """send_error (método desconhecido, requisição quebrada) passa por send_response: sem Server, sem versão no corpo."""
        for requisicao in (b'XXX /x HTTP/1.1\r\nHost: vlado.test\r\n\r\n', b'GET /x HTTP/9.9\r\nHost: vlado.test\r\n\r\n',
                           b'GARBAGE\r\n\r\n', b'GET / HTTP/1.1\r\nHost: vlado.test\r\nContent-Length: abc\r\n\r\n'):
            with self.subTest(requisicao=requisicao[:20]):
                with socket.create_connection(('127.0.0.1', self.server.server_port), timeout=10) as s:
                    s.sendall(requisicao)
                    bruto = b''
                    s.settimeout(5)
                    try:
                        while chunk := s.recv(4096):
                            bruto += chunk
                    except (socket.timeout, ConnectionError):
                        pass
                texto = bruto.decode('latin1')
                self.assertTrue(texto, 'o servidor respondeu algo')  # requisição quebrada: o Python responde sem linha de status (HTTP/0.9)
                self.assertNotRegex(texto, r'(?im)^server:', texto)
                self.assertIsNone(re.search(r'(?i)python|basehttp', texto), texto)

    def test_hsts_em_modo_piloto_tem_includesubdomains_e_nao_tem_preload(self):
        for caminho in ('/saude', '/entrar', '/nao-existe-xyz'):
            status, cabecalhos, _ = self.request('GET', caminho)
            self.assertEqual(cabecalhos.get('Strict-Transport-Security'), HSTS, f'{caminho} ({status})')
            self.assertNotIn('preload', cabecalhos['Strict-Transport-Security'])
        status, cabecalhos, _ = self.request('POST', '/api/entrar', '{"login": "x", "senha": "y"}',
                                             {'Origin': ORIGEM, 'Content-Type': 'application/json'})
        self.assertEqual(cabecalhos.get('Strict-Transport-Security'), HSTS)

    def test_os_demais_cabecalhos_de_seguranca_seguem_iguais(self):
        _, cabecalhos, _ = self.request('GET', '/entrar')
        self.assertEqual(cabecalhos['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(cabecalhos['Referrer-Policy'], 'no-referrer')
        self.assertIn("frame-ancestors 'none'", cabecalhos['Content-Security-Policy'])
        self.assertEqual(cabecalhos['Cache-Control'], 'no-store')
        self.assertIn('Date', cabecalhos)


class CaddyfilesTest(unittest.TestCase):
    def setUp(self):
        self.textos = {nome: (RAIZ / nome).read_text(encoding='utf-8') for nome in CADDYFILES}

    def sem_comentarios(self, texto):
        return '\n'.join(l for l in texto.splitlines() if not l.lstrip().startswith('#'))

    def test_os_dois_tiram_o_server_nas_respostas_normais_e_nas_de_erro_do_caddy(self):
        for nome, texto in self.textos.items():
            codigo = self.sem_comentarios(texto)
            self.assertEqual(len(re.findall(r'(?m)^\t\theader -Server$|^\t\t-Server$', codigo)), 2, f'{nome}: -Server no header e no handle_errors')
            self.assertRegex(codigo, r'(?s)\theader \{\n\t\t-Server\n', nome)
            self.assertRegex(codigo, r'(?s)handle_errors \{\n\t\theader -Server\n', nome)

    def test_hsts_com_includesubdomains_no_publico_e_sem_preload(self):
        publico = self.sem_comentarios(self.textos['deploy/Caddyfile'])
        achados = re.findall(r'Strict-Transport-Security "([^"]+)"', publico)
        self.assertEqual(achados, [HSTS, HSTS], 'no header do site e no handle_errors')
        for nome, texto in self.textos.items():
            self.assertNotIn('preload', self.sem_comentarios(texto), nome)
        interno = self.sem_comentarios(self.textos['deploy/Caddyfile.interno'])
        self.assertNotIn('Strict-Transport-Security', interno, 'a CA local não fixa HSTS em nome de teste')

    def test_keepalive_do_caddy_para_a_mesa_expira_antes_do_fechamento_ocioso_da_mesa(self):
        """A Mesa fecha a conexão ociosa aos 10 s (CONF-03): o Caddy a descarta antes, em 5 s, para nunca reutilizá-la no instante
        em que ela fecha (seria um 502)."""
        for nome, texto in self.textos.items():
            codigo = self.sem_comentarios(texto)
            bloco = re.search(r'reverse_proxy vlado:8765 \{\n\t\ttransport http \{\n\t\t\tkeepalive (\d+)s\n\t\t\}\n\t\}', codigo)
            self.assertIsNotNone(bloco, f'{nome}: reverse_proxy sem transport http { "{" } keepalive ... }}')
            self.assertLess(int(bloco.group(1)), 10, nome)
            self.assertEqual(int(bloco.group(1)), 5)
        trechos = {nome: re.search(r'reverse_proxy vlado:8765 \{.*?\n\t\}\n', t, re.S).group(0) for nome, t in self.textos.items()}
        self.assertEqual(len(set(trechos.values())), 1, 'os dois Caddyfiles têm o mesmo bloco do upstream')

    def test_os_novos_blocos_ficam_fora_do_registro_de_acesso(self):
        """O teste de registro compara o bloco `log_append`..`log` dos dois arquivos: os cabeçalhos não podem entrar nele."""
        for nome, texto in self.textos.items():
            inicio = texto.index('log_append rota')
            fim = re.compile(r'(?m)^\t\}$').search(texto, texto.index('\tlog {', inicio)).end()
            bloco = texto[inicio:fim]
            for proibido in ('-Server', 'Strict-Transport-Security', 'keepalive'):
                self.assertNotIn(proibido, bloco, nome)

    @unittest.skipUnless(shutil.which('docker'), 'sem docker no PATH')
    def test_caddy_de_verdade_aceita_os_dois_arquivos(self):
        imagem = re.search(r'image: (caddy:\S+)', (RAIZ / 'docker-compose.yml').read_text(encoding='utf-8')).group(1)
        for nome in CADDYFILES:
            r = subprocess.run(['docker', 'run', '--rm', '-e', 'VLADO_DOMINIO=vlado.localhost', '-v',
                                f'{(RAIZ / nome).resolve()}:/etc/caddy/Caddyfile:ro', imagem, 'caddy', 'validate',
                                '--config', '/etc/caddy/Caddyfile', '--adapter', 'caddyfile'],
                               capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120)
            if r.returncode != 0 and ('daemon' in r.stderr.lower() or 'pipe' in r.stderr.lower()):
                self.skipTest('daemon do Docker indisponível')
            self.assertEqual(r.returncode, 0, f'{nome}: {r.stderr[-400:]}')
            self.assertIn('Valid configuration', r.stdout + r.stderr)


class DocumentacaoTest(unittest.TestCase):
    def test_monitoramento_registra_as_decisoes_do_seg_06(self):
        texto = (RAIZ / 'deploy' / 'MONITORAMENTO.md').read_text(encoding='utf-8')
        secao = texto[texto.index('## Cabeçalhos e conexões (SEG-06)'):texto.index('## Pendências que dependem de pessoa')]
        for trecho in ('includeSubDomains', 'preload', 'não entra, por ora', 'Server', 'keepalive', '5 s', '10 s',
                       'VLADO_CONSULTAS_MAX_ARQUIVOS', 'VLADO_CONSULTAS_MAX_MB', 'consultas_sqlite', 'ref.', 'texto fixo'):
            self.assertIn(trecho, secao, trecho)


if __name__ == '__main__':
    unittest.main()
