"""Run synthetic JavaScript DOM regressions as part of the required unittest suite."""
from pathlib import Path
import json
import shutil
import subprocess
import unittest

from auxiliar_node import localizar_node


class ComportamentosInterfaceTest(unittest.TestCase):
    def test_fixture_continuidade_nao_substitui_digitos_de_referencia(self):
        from agente_fluxo_fixture import entrega
        reference = 'alpha/R002/hash123sintetico'
        refs = {'hit': {'referencia': reference, 'trecho': 'Contrato adicional. Valor total 246.'}}
        generation = json.loads(entrega('geracao_inicial', lambda args: None, refs, valor='246'))
        self.assertEqual(generation['achados'][0]['evidencias'][0]['referencia'], reference)
        self.assertIn('246', generation['achados'][0]['redacao'])
        synthesis = json.loads(entrega('sintese', lambda args: None, refs, valor='246'))
        self.assertIn('[fonte:' + reference + ']', synthesis['texto'])
        self.assertIn('valor 246', synthesis['texto'])

    def test_regressoes_dos_cinco_comportamentos(self):
        node = localizar_node(self)
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run([node, '--test', str(root / 'testes/regressao_comportamentos.cjs')],
                                cwd=root, capture_output=True, text=True, encoding='utf-8', timeout=45)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
