"""Run the browser draft and resume summary DOM tests (salvamento_automatico.cjs) in the unittest suite."""
from pathlib import Path
import shutil
import subprocess
import unittest


class SalvamentoInterfaceTest(unittest.TestCase):
    def test_salvamento_automatico_e_retomada(self):
        node = shutil.which('node')
        self.assertIsNotNone(node, 'Node.js é necessário para os testes do salvamento no navegador.')
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run([node, '--test', str(root / 'testes/salvamento_automatico.cjs')],
                                cwd=root, capture_output=True, text=True, encoding='utf-8', timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
