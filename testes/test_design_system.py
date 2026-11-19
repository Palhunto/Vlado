"""Run the design system contracts (tokens, contrast, theme sets) as part of the required suite."""
import http.client
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / 'scripts'))
from interface_pesquisa import Servidor  # noqa: E402

CONTRATOS = ('estilo_tokens.cjs', 'caderno_estilo.cjs', 'veredito.cjs')


class DesignSystemTest(unittest.TestCase):
    def test_contratos_de_estilo(self):
        node = shutil.which('node')
        self.assertIsNotNone(node, 'Node.js é necessário para os contratos de estilo da interface.')
        result = subprocess.run([node, '--test', *(str(RAIZ / 'testes' / nome) for nome in CONTRATOS)],
                                cwd=RAIZ, capture_output=True, text=True, encoding='utf-8', timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_tokens_servidos_pela_mesa(self):
        pasta = tempfile.TemporaryDirectory(); self.addCleanup(pasta.cleanup)
        server = Servidor(('127.0.0.1', 0), Path(pasta.name))
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(lambda: (server.shutdown(), server.server_close(), thread.join(timeout=3)))
        con = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=10)
        con.request('GET', '/tokens.css'); resposta = con.getresponse(); corpo = resposta.read(); con.close()
        self.assertEqual(resposta.status, 200)
        self.assertTrue(resposta.getheader('Content-Type').startswith('text/css'))
        self.assertIn(b'--vlado-verde-700', corpo)


if __name__ == '__main__':
    unittest.main()
