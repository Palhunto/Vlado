"""Mesa em tela estreita: regressões de DOM sintético (voltar, conexão, faixa) e ativos móveis."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import unittest

from auxiliar_node import localizar_node

RAIZ = Path(__file__).resolve().parents[1]


class MesaMovelTest(unittest.TestCase):
    def test_voltar_conexao_e_faixa_de_ambiente(self):
        node = localizar_node(self)
        result = subprocess.run([node, '--test', str(RAIZ / 'testes/mobile_navegacao.cjs')],
                                cwd=RAIZ, capture_output=True, text=True, encoding='utf-8', timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_pdfjs_incorporado_confere_com_o_manifesto(self):
        base = RAIZ / 'interface/vendor/pdfjs'
        manifesto = json.loads((base / 'manifesto.json').read_text(encoding='utf-8'))
        self.assertEqual(manifesto['name'], 'pdfjs-dist')
        self.assertEqual(manifesto['build'], 'legacy')
        for nome, esperado in manifesto['files'].items():
            self.assertEqual(hashlib.sha256((base / nome).read_bytes()).hexdigest(), esperado, nome)

    def test_manifesto_web_e_icones_existem(self):
        manifesto = json.loads((RAIZ / 'interface/manifest.webmanifest').read_text(encoding='utf-8'))
        self.assertEqual(manifesto['start_url'], '/')
        self.assertEqual(manifesto['display'], 'standalone')
        for icone in manifesto['icons']:
            self.assertTrue((RAIZ / 'interface' / icone['src'].lstrip('/')).is_file(), icone['src'])
        html = (RAIZ / 'interface/index.html').read_text(encoding='utf-8')
        self.assertIn('<link rel="manifest" href="/manifest.webmanifest">', html)
        self.assertIn('<meta name="theme-color"', html)


    def test_servidor_publica_pdfjs_manifesto_e_icones_com_csp_sem_eval(self):
        import threading
        import urllib.request
        from fixture_achados import Ambiente
        from interface_pesquisa import Servidor
        fx = Ambiente()
        server = Servidor(('127.0.0.1', 0), fx.root)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            for rota, tipo in [('/vendor/pdfjs/legacy/build/pdf.min.mjs', 'text/javascript'),
                               ('/vendor/pdfjs/legacy/build/pdf.worker.min.mjs', 'text/javascript'),
                               ('/manifest.webmanifest', 'application/manifest+json'),
                               ('/icones/vlado.svg', 'image/svg+xml'), ('/icones/vlado-192.png', 'image/png')]:
                with urllib.request.urlopen(server.origin + rota) as resposta:
                    self.assertEqual(resposta.status, 200, rota)
                    self.assertTrue(resposta.headers['Content-Type'].startswith(tipo), rota)
                    csp = resposta.headers['Content-Security-Policy']
                    self.assertIn("worker-src 'self'", csp)
                    self.assertNotIn('unsafe-eval', csp)
                    self.assertNotIn('unsafe-inline', csp)
        finally:
            server.shutdown()
            server.server_close()
            fx.cleanup()


if __name__ == '__main__':
    unittest.main()
