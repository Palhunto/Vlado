import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import acesso  # noqa: E402
import apuracao  # noqa: E402
import semear_ambiente  # noqa: E402
import test_codex_integracao as base  # noqa: E402


class SemearAmbienteTest(unittest.TestCase):
    def setUp(self):
        fixture = base.CodexIntegrationTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.root = fixture.root
        env = mock.patch.dict(os.environ, {'VLADO_ACESSO': str(self.root / 'acesso/acesso.json')})
        env.start()
        self.addCleanup(env.stop)
        acesso.limpar_limites()

    def test_recusa_ambiente_editorial(self):
        with self.assertRaises(SystemExit):
            semear_ambiente.semear(self.root, 'editorial', 'https://x.invalid', self.root / 'links.txt')
        self.assertFalse((self.root / 'acesso/acesso.json').exists())

    def test_semeia_casos_contas_e_nota_de_forma_idempotente(self):
        saida = self.root / 'links.txt'
        feitos = semear_ambiente.semear(self.root, 'demonstracao', 'https://demo.invalid', saida)
        self.assertEqual(feitos['contas'], ['demo.admin', 'demo.convidado1', 'demo.convidado2'])
        linhas = saida.read_text(encoding='utf-8').splitlines()
        self.assertEqual(len(linhas), 3)
        self.assertTrue(all('https://demo.invalid/ativar/' in linha for linha in linhas))
        contas = {c['login']: c for c in acesso.listar(self.root)}
        self.assertEqual(contas['demo.convidado1']['casos'], [semear_ambiente.CASO_A])
        self.assertEqual(contas['demo.convidado2']['casos'], [semear_ambiente.CASO_B])
        notas = apuracao.listar_notas(self.root, semear_ambiente.CASO_A)['notas']
        self.assertEqual([n['titulo'] for n in notas], ['Pauta Vila Serena'])
        segunda = semear_ambiente.semear(self.root, 'demonstracao', 'https://demo.invalid', saida)
        self.assertEqual(segunda, {'casos': [], 'contas': [], 'nota': None})


if __name__ == '__main__':
    unittest.main()
