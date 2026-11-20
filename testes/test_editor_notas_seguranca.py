"""Run the note editor sanitization test (editor_notas_seguranca.cjs) in the unittest suite."""
from pathlib import Path
import shutil
import subprocess
import unittest


class EditorNotasSegurancaTest(unittest.TestCase):
    def test_limpeza_do_editor_e_csp(self):
        node = shutil.which('node')
        self.assertIsNotNone(node, 'Node.js é necessário para o teste de limpeza do editor de notas.')
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run([node, '--test', str(root / 'testes/editor_notas_seguranca.cjs')],
                                cwd=root, capture_output=True, text=True, encoding='utf-8', timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
