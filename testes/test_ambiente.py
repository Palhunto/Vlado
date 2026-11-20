"""Check dependency selection, including the Windows entry point, without a server."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from ambiente import diagnostico


class AmbienteTest(unittest.TestCase):
    def test_python_que_inicia_sem_extrator_nao_e_considerado_pronto(self):
        with patch('ambiente.importlib.import_module', side_effect=ImportError('sem pypdf')):
            result = diagnostico()
        self.assertFalse(result['pronto'])
        self.assertFalse(result['extracao_pdf']['disponivel'])
        self.assertEqual(result['python'], sys.executable)

    def test_informa_sdks_e_chaves_da_api_sem_expor_valores(self):
        with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'sk-ant-nao-exibir', 'OPENAI_API_KEY': ''}):
            result = diagnostico()
        api = result['inferencia_api']
        self.assertEqual(set(api['sdks']), {'anthropic', 'openai'})
        self.assertEqual(api['chaves'], {'ANTHROPIC_API_KEY': True, 'OPENAI_API_KEY': False})
        self.assertNotIn('sk-ant-nao-exibir', json.dumps(result))

    def test_sdk_de_api_ausente_nao_e_considerado_pronto(self):
        real = __import__('importlib').import_module

        def sem_anthropic(name, *args):
            if name == 'anthropic':
                raise ImportError('sem anthropic')
            return real(name, *args)

        with patch('ambiente.importlib.import_module', side_effect=sem_anthropic):
            result = diagnostico()
        self.assertFalse(result['inferencia_api']['sdks']['anthropic']['disponivel'])
        self.assertFalse(result['pronto'])

    # Opens a console window (cmd.exe); run only on request: VLADO_TESTAR_INICIADOR=1.
    @unittest.skipUnless(os.name == 'nt' and os.environ.get('VLADO_TESTAR_INICIADOR') == '1',
                         'Iniciador Windows: defina VLADO_TESTAR_INICIADOR=1 para executar')
    def test_iniciador_verifica_o_runtime_com_dependencias_sem_abrir_servidor(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(['cmd.exe', '/d', '/c', 'call', 'Iniciar pesquisa.cmd', '--verificar-runtime'],
                                cwd=root, env={**os.environ, 'APURACAO_OCULTO': '1'},
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        environment = json.loads(result.stdout)
        self.assertTrue(environment['pronto'])
        self.assertTrue(environment['extracao_pdf']['disponivel'])
        self.assertTrue(environment['sqlite_fts5'])
