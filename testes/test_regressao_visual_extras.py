"""Testes do que não precisa de navegador em regressao_visual_extras.py: os cenários, os nomes e a seleção."""
import argparse
import unittest

import regressao_visual as rv
import regressao_visual_extras as ex


class ExtrasTest(unittest.TestCase):
    def test_cenarios_pedidos_pelo_design(self):
        self.assertEqual(set(ex.CENARIOS), {'paisagem', '430', 'zoom200'})
        self.assertEqual(ex.CENARIOS['paisagem']['viewport'], {'width': 812, 'height': 375})
        self.assertEqual(ex.CENARIOS['430']['viewport']['width'], 430)
        # 200%: 640 px de largura em CSS com fator 2 = a janela de 1280 px ampliada a 200%
        self.assertEqual(ex.CENARIOS['zoom200']['viewport']['width'] * ex.CENARIOS['zoom200']['escala'], 1280)

    def test_as_telas_sao_as_da_linha_de_base_sem_os_focos(self):
        self.assertEqual(len(ex.TELAS), 14)
        self.assertFalse([t for t in ex.TELAS if t in rv.FOCOS])
        self.assertIn('nova', ex.TELAS)
        self.assertNotIn('cadastro', ex.TELAS)

    def test_84_capturas_no_conjunto_completo(self):
        nomes = ex.nomes_esperados(ex.TELAS, list(ex.CENARIOS), list(rv.TEMAS))
        self.assertEqual(len(nomes), 14 * 3 * 2)
        self.assertEqual(len(set(nomes)), len(nomes))
        self.assertIn('inicio__paisagem__claro', nomes)

    def test_nao_toca_na_pasta_da_linha_de_base(self):
        self.assertNotEqual(ex.pasta_extras(), rv.pasta_referencia())
        self.assertTrue(ex.pasta_extras().name.endswith('_extras'))

    def test_selecao_invalida_e_recusada(self):
        with self.assertRaises(SystemExit):
            ex._selecao(argparse.Namespace(telas='cadastro', cenarios=None, temas=None))
        with self.assertRaises(SystemExit):
            ex._selecao(argparse.Namespace(telas=None, cenarios='tablet', temas=None))


if __name__ == '__main__':
    unittest.main()
