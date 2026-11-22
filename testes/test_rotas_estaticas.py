"""Cache imutável por hash, marcadores de versão e compressão das rotas estáticas (parte C, com o Lume).

Interface sintética numa pasta temporária no lugar de ``interface/``; servidor local em 127.0.0.1.
- ``?v=<versão>`` certa dá cache imutável; ``v`` errada ou ausente revalida (no-cache, ETag).
- ``__V:<nome>__`` é trocado no CSS, no ``index.html`` e no ``entrar.html``; a versão do CSS é a do
  conteúdo já trocado (fontes, depois CSS, depois página); ``__VERSOES__`` traz a de todos os listados.
- Arquivo listado que não existe dá 404; versão muda quando o arquivo muda no disco.
- gzip só quando aceito, e nunca para fontes, imagens ou a página com o token da sessão.
"""
import gzip
import hashlib
import http.client
import json
from pathlib import Path
import re
import sys
import tempfile
import threading
import unittest
from unittest import mock

TESTES = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTES.parent / 'scripts'))
import interface_pesquisa  # noqa: E402
import rotas_estaticas  # noqa: E402
from modelo_pasta import copiar  # noqa: E402
import test_codex_integracao as integracao  # noqa: E402

JS = 'text/javascript; charset=utf-8'
CSS = 'text/css; charset=utf-8'


class RotasEstaticasTest(unittest.TestCase):
    def setUp(self):
        temp, self.root, _ = copiar('CodexIntegrationTest', integracao.CodexIntegrationTest.montar)
        self.addCleanup(temp.cleanup)
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.assets = Path(pasta.name)
        (self.assets / 'fonts').mkdir()
        self.fonte = bytes(range(256)) * 8
        (self.assets / 'fonts/Fonte-latin.woff2').write_bytes(self.fonte)
        (self.assets / 'style.css').write_text(
            "@font-face{src:url('/fonts/Fonte-latin.woff2?v=__V:Fonte-latin.woff2__')}"
            ".a{background:url('/icone.png?v=__V:icone.png__')}.b{x:'__V:nao_listado.js__'}", encoding='utf-8')
        (self.assets / 'app.js').write_text('console.log("Mesa sintética");\n' * 200, encoding='utf-8')
        (self.assets / 'icone.png').write_bytes(b'\x89PNG' + bytes(500))
        pagina = ('<link href="/style.css?v=__V:style.css__"><script src="/app.js?v=__V:app.js__"></script>'
                  "<meta name=\"vlado-versoes\" content='__VERSOES__'>")
        (self.assets / 'index.html').write_text(pagina + '<i>__SESSION_TOKEN__</i>', encoding='utf-8')
        (self.assets / 'entrar.html').write_text(pagina, encoding='utf-8')
        arquivos = {'/': ('index.html', 'text/html; charset=utf-8'), '/style.css': ('style.css', CSS),
                    '/app.js': ('app.js', JS), '/fonts/Fonte-latin.woff2': ('fonts/Fonte-latin.woff2', 'font/woff2'),
                    '/icone.png': ('icone.png', 'image/png'), '/falta.js': ('falta.js', JS)}
        for alvo, valor in ((rotas_estaticas, {'ASSETS': self.assets, 'ARQUIVOS': arquivos,
                                              '_lidos': {}, '_comprimidos': {}}),):
            for nome, novo in valor.items():
                remendo = mock.patch.object(alvo, nome, novo)
                remendo.start()
                self.addCleanup(remendo.stop)
        self.server = interface_pesquisa.Servidor(('127.0.0.1', 0), self.root)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (self.server.shutdown(), self.server.server_close(), thread.join(5)))

    def get(self, caminho, **cabecalhos):
        con = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        try:
            con.request('GET', caminho, headers=cabecalhos)
            resposta = con.getresponse()
            return resposta.status, {k.lower(): v for k, v in resposta.getheaders()}, resposta.read()
        finally:
            con.close()

    def test_v_certo_e_imutavel_e_v_errado_ou_ausente_revalida(self):
        versao = rotas_estaticas.versao('app.js')
        self.assertEqual(versao, hashlib.sha256((self.assets / 'app.js').read_bytes()).hexdigest()[:12])
        _, certo, corpo = self.get('/app.js?v=' + versao)
        self.assertEqual(certo['cache-control'], 'public, max-age=31536000, immutable')
        for consulta in ('?v=000000000000', '', '?v=1'):
            with self.subTest(consulta=consulta):
                status, cabecalhos, outro = self.get('/app.js' + consulta)
                self.assertEqual((status, cabecalhos['cache-control'], outro), (200, 'no-cache', corpo))
                self.assertEqual(cabecalhos['etag'], certo['etag'])

    def test_marcadores_trocados_no_css_e_nas_paginas_na_ordem_fontes_css_pagina(self):
        _, _, css = self.get('/style.css')
        versao_fonte = hashlib.sha256(self.fonte).hexdigest()[:12]
        self.assertIn(f"/fonts/Fonte-latin.woff2?v={versao_fonte}'".encode(), css)  # by its file name alone
        self.assertIn(b"'__V:nao_listado.js__'", css)  # not listed: left as it is
        versao_css = hashlib.sha256(css).hexdigest()[:12]  # the CSS as served, markers replaced
        self.assertEqual(rotas_estaticas.versao('style.css'), versao_css)
        self.assertEqual(self.get('/style.css?v=' + versao_css)[1]['cache-control'], 'public, max-age=31536000, immutable')
        _, _, indice = self.get('/')
        entrar = rotas_estaticas.conteudo('entrar.html')
        for pagina in (indice, entrar):
            with self.subTest(pagina=pagina[:40]):
                self.assertIn(f'/style.css?v={versao_css}"'.encode(), pagina)
                self.assertIn(f'/app.js?v={rotas_estaticas.versao("app.js")}"'.encode(), pagina)
                versoes = json.loads(re.search(rb"content='([^']*)'", pagina).group(1))
                self.assertEqual(versoes, {'style.css': versao_css, 'app.js': rotas_estaticas.versao('app.js'),
                                           'fonts/Fonte-latin.woff2': versao_fonte,
                                           'icone.png': rotas_estaticas.versao('icone.png')})  # falta.js: not on disk
                self.assertNotIn(b'__V:', pagina.replace(b'__V:nao_listado', b''))
        self.assertNotIn(b'__SESSION_TOKEN__', indice)

    def test_arquivo_listado_que_nao_existe_da_404(self):
        self.assertEqual(self.get('/falta.js')[0], 404)
        self.assertEqual(self.get('/nao-listado.js')[0], 404)

    def test_versao_muda_quando_o_arquivo_muda_no_disco(self):
        antes = rotas_estaticas.versao('app.js')
        (self.assets / 'app.js').write_text('console.log("outra");\n', encoding='utf-8')
        self.assertNotEqual(rotas_estaticas.versao('app.js'), antes)
        self.assertNotEqual(self.get('/app.js?v=' + antes)[1]['cache-control'], 'public, max-age=31536000, immutable')

    def test_gzip_so_quando_aceito_e_nunca_para_fonte_imagem_ou_pagina_com_token(self):
        _, simples, corpo = self.get('/app.js')
        status, comprimido, corpo_gz = self.get('/app.js', **{'Accept-Encoding': 'gzip, deflate, br'})
        self.assertEqual((status, comprimido.get('content-encoding'), comprimido.get('vary')), (200, 'gzip', 'Accept-Encoding'))
        self.assertEqual(gzip.decompress(corpo_gz), corpo)
        self.assertLess(len(corpo_gz), len(corpo) // 3)
        self.assertEqual(comprimido['etag'], simples['etag'])  # the ETag of the content itself
        self.assertEqual(simples.get('vary'), 'Accept-Encoding')
        self.assertNotIn('content-encoding', simples)
        for aceita in ('identity', 'gzip;q=0', 'br'):
            with self.subTest(aceita=aceita):
                self.assertNotIn('content-encoding', self.get('/app.js', **{'Accept-Encoding': aceita})[1])
        self.assertEqual(self.get('/style.css', **{'Accept-Encoding': 'gzip'})[1].get('content-encoding'), 'gzip')
        for caminho in ('/fonts/Fonte-latin.woff2', '/icone.png', '/'):
            with self.subTest(caminho=caminho):
                status, cabecalhos, _ = self.get(caminho, **{'Accept-Encoding': 'gzip'})
                self.assertEqual(status, 200)
                self.assertNotIn('content-encoding', cabecalhos)


if __name__ == '__main__':
    unittest.main()
