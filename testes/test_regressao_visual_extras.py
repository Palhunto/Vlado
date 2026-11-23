"""Testes do que não precisa de navegador em regressao_visual_extras.py: os cenários, os nomes e a seleção."""
import argparse
import hashlib
import json
import unittest

from PIL import Image

import regressao_visual as rv
import regressao_visual_extras as ex


class ExtrasTest(unittest.TestCase):
    def test_cenarios_pedidos_pelo_design(self):
        self.assertEqual(set(ex.CENARIOS), {'paisagem', '430', 'zoom200', 'reflow320'})
        self.assertEqual(ex.CENARIOS['paisagem']['viewport'], {'width': 812, 'height': 375})
        self.assertEqual(ex.CENARIOS['430']['viewport']['width'], 430)
        # reflow (WCAG 1.4.10): 320 px de largura em CSS, sem ampliar
        self.assertEqual(ex.CENARIOS['reflow320']['viewport']['width'], 320)
        self.assertEqual(ex.CENARIOS['reflow320']['escala'], 1)
        # 200%: 640 px de largura em CSS com fator 2 = a janela de 1280 px ampliada a 200%
        self.assertEqual(ex.CENARIOS['zoom200']['viewport']['width'] * ex.CENARIOS['zoom200']['escala'], 1280)

    def test_as_telas_sao_as_da_linha_de_base_sem_os_focos(self):
        self.assertEqual(len(ex.TELAS), 14)
        self.assertFalse([t for t in ex.TELAS if t in rv.FOCOS])
        self.assertIn('nova', ex.TELAS)
        self.assertNotIn('cadastro', ex.TELAS)

    def test_112_capturas_no_conjunto_completo(self):
        nomes = ex.nomes_esperados(ex.TELAS, list(ex.CENARIOS), list(rv.TEMAS))
        self.assertEqual(len(nomes), 14 * 4 * 2)
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


class ReferenciasExtrasTest(unittest.TestCase):
    """As 112 referências versionadas conferem com o manifesto, têm a largura do cenário e nenhuma é uma página em branco."""

    def setUp(self):
        self.pasta = ex.pasta_extras()
        if not (self.pasta / 'manifesto.json').is_file():
            self.skipTest('sem referências extras para esta plataforma: rode `regressao_visual_extras.py gerar`')
        self.manifesto = json.loads((self.pasta / 'manifesto.json').read_text(encoding='utf-8'))

    def test_manifesto_confere_com_as_imagens(self):
        esperados = set(ex.nomes_esperados(ex.TELAS, list(ex.CENARIOS), list(rv.TEMAS)))
        self.assertEqual(set(self.manifesto['capturas']), esperados)
        self.assertEqual({p.stem for p in self.pasta.glob('*.png')}, esperados)
        for nome, dados in self.manifesto['capturas'].items():
            arquivo = self.pasta / f'{nome}.png'
            self.assertEqual(hashlib.sha256(arquivo.read_bytes()).hexdigest(), dados['sha256'], f'{nome}: imagem trocada ou apagada à mão')
            self.assertEqual(arquivo.stat().st_size, dados['bytes'], nome)

    def test_largura_do_cenario_e_conteudo(self):
        for nome in self.manifesto['capturas']:
            tela, cenario, tema = nome.split('__')
            config = ex.CENARIOS[cenario]
            with Image.open(self.pasta / f'{nome}.png') as imagem:
                rgb = imagem.convert('RGB')
                self.assertGreaterEqual(rgb.width, config['viewport']['width'] * config['escala'], nome)
                cinza = rgb.convert('L').histogram()
                self.assertLess(max(cinza) / sum(cinza), 0.985, f'{nome} parece em branco')

    def test_nenhuma_rolagem_horizontal_nas_referencias(self):
        self.assertEqual(self.manifesto['rolagem_horizontal'], {}, 'uma referência extra com rolagem horizontal precisa de decisão do Design')


if __name__ == '__main__':
    unittest.main()
