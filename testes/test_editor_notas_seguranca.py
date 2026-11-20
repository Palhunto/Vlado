"""Run the note editor sanitization test (editor_notas_seguranca.cjs) in the unittest suite."""
from pathlib import Path
import shutil
import subprocess
import unittest

from auxiliar_node import localizar_node


class EditorNotasSegurancaTest(unittest.TestCase):
    def test_limpeza_do_editor_e_csp(self):
        node = localizar_node(self)
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run([node, '--test', str(root / 'testes/editor_notas_seguranca.cjs')],
                                cwd=root, capture_output=True, text=True, encoding='utf-8', timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
