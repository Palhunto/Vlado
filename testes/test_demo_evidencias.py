"""A demonstração do núcleo de evidências roda sem argumentos, sem rede e sem modelo, e limpa a pasta temporária."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

DEMO = Path(__file__).resolve().parents[1] / 'scripts' / 'demo_evidencias.py'


class DemoEvidenciasTest(unittest.TestCase):
    def test_demo_termina_com_codigo_zero_e_imprime_os_quadros(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {**os.environ, 'TMP': tmp, 'TEMP': tmp, 'TMPDIR': tmp, 'PYTHONIOENCODING': 'utf-8'}
            for key in ('ANTHROPIC_API_KEY', 'OPENAI_API_KEY'):
                env.pop(key, None)
            result = subprocess.run([sys.executable, str(DEMO)], capture_output=True, text=True, encoding='utf-8',
                                    env=env, timeout=300, cwd=tmp)
            self.assertEqual(result.returncode, 0, result.stderr)
            for titulo in ('QUADRO DE HIPÓTESES (2)', 'LINHA DO TEMPO', 'COMPARAÇÃO D001 × D002', 'MAPA DE RELAÇÕES',
                           'possível homônimo', 'não foram fundidas', 'D001 · linha 1'):
                self.assertIn(titulo, result.stdout)
            self.assertEqual(list(Path(tmp).iterdir()), [], 'a demonstração deixou arquivos temporários')


if __name__ == '__main__':
    unittest.main()
