"""Run the design system contracts (tokens, contrast, theme sets) as part of the required suite."""
import http.client
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

from auxiliar_node import localizar_node

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / 'scripts'))
from interface_pesquisa import Servidor  # noqa: E402

CONTRATOS = ('estilo_tokens.cjs', 'caderno_estilo.cjs', 'veredito.cjs', 'quadros_evidencia.cjs', 'analise_evidencia.cjs')


class DesignSystemTest(unittest.TestCase):
    def test_contratos_de_estilo(self):
        node = localizar_node(self)
        result = subprocess.run([node, '--test', *(str(RAIZ / 'testes' / nome) for nome in CONTRATOS)],
                                cwd=RAIZ, capture_output=True, text=True, encoding='utf-8', timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_dados_sinteticos_das_capturas_das_telas(self):
        # qa_quadros.py builds its case through the Core's own demo; this keeps that fixture working.
        import qa_quadros
        from fixture_achados import Ambiente
        env = Ambiente(); self.addCleanup(env.cleanup)
        self.assertEqual(qa_quadros.montar(env), {'hipoteses': 2, 'eventos': 4, 'alteracoes': 2, 'entidades': 3, 'celulas_corrigidas': 1})

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
