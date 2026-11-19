"""Web sources per case, served by a local HTTP server. No internet, no model calls."""
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
from pathlib import Path
import sys
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import cadastrar_documentos as cadastro
import fontes_web
import test_registros as fixtures
from comum import escrever_json, ler_json
from indice_sqlite import pesquisar
from nova_rodada import criar_rodada
from registros_achados import conferir_evidencia
from selecionar_caso import selecionar

PAGINA = ('<!doctype html><html><head><meta charset="utf-8"><title>Contrato 12/2026</title>'
          '<script>var segredo = "nao indexar";</script><style>p{color:red}</style></head>'
          '<body><h1>Extrato do contrato</h1><p>Valor global: R$ 1.234,56</p>'
          '<p>Vigência de doze meses, assinado em 3 de março.</p></body></html>').encode('utf-8')


class _Servidor(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.server.pedidos.append(self.path)
        port = self.server.server_address[1]
        if self.path.startswith('/pagina'):
            self._enviar(200, 'text/html; charset=utf-8', PAGINA)
        elif self.path == '/texto':
            self._enviar(200, 'text/plain; charset=latin-1', 'Ofício nº 7\nResposta enviada.'.encode('latin-1'))
        elif self.path == '/redir-interno':
            self._redirecionar('/pagina?via=redir')
        elif self.path == '/redir-externo':
            # Same machine, other host name: must be treated as another domain.
            self._redirecionar(f'http://localhost:{port}/pagina')
        else:
            self._enviar(404, 'text/plain', b'nao encontrado')

    def _enviar(self, code, kind, body):
        self.send_response(code)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _redirecionar(self, location):
        self.send_response(302)
        self.send_header('Location', location)
        self.send_header('Content-Length', '0')
        self.end_headers()


class FontesWebTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.RegistrosTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        config = ler_json(self.root / 'configuracao.json')
        escrever_json(self.root / 'configuracao.json', {**config, 'indice_sqlite': True})
        selecionar(self.root, None)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), _Servidor)
        self.server.pedidos = []
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base = f'http://127.0.0.1:{self.server.server_address[1]}'

    def criar(self, caso='web', **kwargs):
        return cadastro.cadastrar(self.root, caso, [self.root / 'fonte.txt'], novo=True,
                                  titulo='Caso sintético', natureza='sinteticos', **kwargs)

    def manifesto(self, caso='web'):
        return ler_json(self.root / f'casos/{caso}/manifesto.json')

    def criar_web(self):
        return self.criar(modo_fontes='documentos_e_web', dominio_web='127.0.0.1')

    def test_padrao_e_somente_documental_e_recusa_captura_sem_acessar_rede(self):
        result = self.criar()
        self.assertEqual(result['inventario']['fontes_web'], {'modo': 'somente_documentos', 'dominio_permitido': None})
        before = (self.root / 'casos/web/manifesto.json').read_bytes()
        with self.assertRaisesRegex(ValueError, 'somente documental'):
            fontes_web.capturar(self.root, 'web', self.base + '/pagina')
        self.assertEqual(self.server.pedidos, [])
        self.assertEqual((self.root / 'casos/web/manifesto.json').read_bytes(), before)
        self.assertFalse((self.root / 'casos/web/web').exists())

    def test_modo_so_e_escolhido_na_criacao(self):
        self.criar()
        with self.assertRaisesRegex(ValueError, 'só é escolhido na criação'):
            cadastro.cadastrar(self.root, 'web', [self.root / 'fonte.txt'],
                               modo_fontes='documentos_e_web', dominio_web='127.0.0.1')
        self.assertEqual(self.manifesto()['fontes_web']['modo'], 'somente_documentos')

    def test_dominio_permitido_precisa_ser_um_nome_de_site(self):
        for invalid in ('', 'http://exemplo.gov.br', 'exemplo.gov.br/pagina', '*.exemplo.gov.br',
                        'exemplo.gov.br:8080', '-x.gov.br'):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                fontes_web.normalizar_dominio(invalid)
        self.assertEqual(fontes_web.normalizar_dominio('WWW.Exemplo.GOV.br.'), 'www.exemplo.gov.br')
        with self.assertRaises(ValueError):
            self.criar(modo_fontes='documentos_e_web')
        with self.assertRaises(ValueError):
            self.criar(modo_fontes='somente_documentos', dominio_web='exemplo.gov.br')
        self.assertFalse((self.root / 'casos/web').exists())

    def test_captura_registra_endereco_horario_conteudo_e_hash_separados_dos_originais(self):
        self.criar_web()
        url = self.base + '/pagina?ano=2026&id=12'
        result = fontes_web.capturar(self.root, 'web', url, observacao='Extrato publicado')
        capture = result['captura']
        manifest = self.manifesto()
        self.assertEqual(manifest['fontes_web']['dominio_permitido'], '127.0.0.1')
        self.assertEqual(manifest['capturas_web'][0]['id'], 'W001')
        self.assertEqual((capture['url_solicitada'], capture['url_final']), (url, url))
        self.assertEqual(datetime.fromisoformat(capture['acessado_em_utc']).utcoffset().total_seconds(), 0)
        self.assertEqual(capture['status_http'], 200)
        stored = self.root / capture['arquivo']
        self.assertEqual(stored.read_bytes(), PAGINA)
        self.assertEqual(capture['sha256'], hashlib.sha256(PAGINA).hexdigest())
        self.assertEqual(Path(capture['arquivo']).parts[:3], ('casos', 'web', 'web'))
        self.assertEqual([d['id'] for d in manifest['documentos']], ['D001'])
        text = (self.root / capture['derivados'][0]['arquivo']).read_text(encoding='utf-8')
        self.assertIn('Valor global: R$ 1.234,56', text)
        self.assertNotIn('nao indexar', text)
        self.assertEqual(capture['derivados'][0]['titulo_pagina'], 'Contrato 12/2026')
        record = ler_json(self.root / capture['registro']['arquivo'])
        self.assertEqual((record['caso_id'], record['url_final'], record['sha256']), ('web', url, capture['sha256']))
        self.assertEqual(manifest['corpus_id'], 'web_v2')
        self.assertEqual(len(list(fontes_web.arquivos_web(self.root, manifest))), 3)

    def test_recusa_outro_dominio_antes_de_acessar(self):
        self.criar_web()
        before = (self.root / 'casos/web/manifesto.json').read_bytes()
        port = self.server.server_address[1]
        for url in (f'http://localhost:{port}/pagina', 'https://exemplo.org/', 'ftp://127.0.0.1/x',
                    f'http://usuario:senha@127.0.0.1:{port}/pagina', 'http://127.0.0.1.evil.example/'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                fontes_web.capturar(self.root, 'web', url)
        self.assertEqual(self.server.pedidos, [])
        self.assertEqual((self.root / 'casos/web/manifesto.json').read_bytes(), before)

    def test_redirecionamento_para_outro_dominio_e_recusado_sem_gravar(self):
        self.criar_web()
        before = (self.root / 'casos/web/manifesto.json').read_bytes()
        with self.assertRaises(fontes_web.DominioRecusado):
            fontes_web.capturar(self.root, 'web', self.base + '/redir-externo')
        self.assertEqual(self.server.pedidos, ['/redir-externo'])
        self.assertEqual((self.root / 'casos/web/manifesto.json').read_bytes(), before)
        self.assertFalse((self.root / 'casos/web/web').exists())

    def test_redirecionamento_no_mesmo_dominio_registra_cadeia_e_endereco_final(self):
        self.criar_web()
        capture = fontes_web.capturar(self.root, 'web', self.base + '/redir-interno')['captura']
        self.assertEqual(capture['url_final'], self.base + '/pagina?via=redir')
        self.assertEqual(capture['redirecionamentos'][0]['status_http'], 302)

    def test_erro_http_nao_gera_captura(self):
        self.criar_web()
        with self.assertRaisesRegex(ValueError, '404'):
            fontes_web.capturar(self.root, 'web', self.base + '/inexistente')
        self.assertNotIn('capturas_web', self.manifesto())

    def test_texto_com_charset_declarado(self):
        self.criar_web()
        capture = fontes_web.capturar(self.root, 'web', self.base + '/texto')['captura']
        text = (self.root / capture['derivados'][0]['arquivo']).read_text(encoding='utf-8')
        self.assertEqual(text, 'Ofício nº 7\nResposta enviada.\n')

    def test_captura_alterada_e_detectada(self):
        self.criar_web()
        capture = fontes_web.capturar(self.root, 'web', self.base + '/pagina')['captura']
        (self.root / capture['arquivo']).write_bytes(b'alterado')
        with self.assertRaisesRegex(ValueError, 'Hash divergente'):
            list(fontes_web.arquivos_web(self.root, self.manifesto()))
        with self.assertRaisesRegex(ValueError, 'Hash divergente'):
            fontes_web.capturar(self.root, 'web', self.base + '/texto')

    def test_manifesto_documental_com_captura_injetada_e_recusado(self):
        self.criar()
        manifest = self.manifesto()
        manifest['capturas_web'] = [{'id': 'W001'}]
        with self.assertRaises(ValueError):
            fontes_web.modo_do_caso(manifest)

    def test_rodada_congela_capturas_indexa_e_valida_localizador(self):
        self.criar_web()
        capture = fontes_web.capturar(self.root, 'web', self.base + '/pagina')['captura']
        run = criar_rodada(self.root, 'R001', 'Qual o valor do contrato?', caso='web')
        frozen = {x['arquivo'] for x in ler_json(run / 'snapshot.json')}
        self.assertIn('entradas/' + capture['arquivo'], frozen)
        self.assertIn('entradas/' + capture['registro']['arquivo'], frozen)
        record = ler_json(run / 'registro.json')
        self.assertEqual((record['modo_fontes'], record['dominio_web_permitido'], record['capturas_web_congeladas'],
                          record['web_usada']), ('documentos_e_web', '127.0.0.1', 1, True))
        hits = pesquisar(self.root, 'web', 'R001', 'valor global')['resultados']
        self.assertEqual({h['documento_id'] for h in hits}, {'W001'})
        lines = (run / 'entradas' / capture['derivados'][0]['arquivo']).read_text(encoding='utf-8').splitlines()
        number = next(i for i, line in enumerate(lines, 1) if 'Valor global' in line)
        evidence = fontes_web.localizador(capture, number, number, 'R$ 1.234,56')
        self.assertIn(capture['url_final'], evidence['localizador']['descricao'])
        checked = conferir_evidencia(self.root, 'web', 'R001', evidence)
        self.assertEqual(checked['evidencia']['documento_id'], 'W001')
        with self.assertRaises(ValueError):
            conferir_evidencia(self.root, 'web', 'R001', {**evidence, 'trecho': 'R$ 9.999,99'})

    def test_rodada_de_caso_documental_registra_modo(self):
        self.criar()
        run = criar_rodada(self.root, 'R001', 'Pergunta sintética', caso='web')
        record = ler_json(run / 'registro.json')
        self.assertEqual((record['modo_fontes'], record['capturas_web_congeladas'], record['web_usada']),
                         ('somente_documentos', 0, False))


if __name__ == '__main__':
    unittest.main()
