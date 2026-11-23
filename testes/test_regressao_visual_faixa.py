"""Testes sem navegador de regressao_visual_faixa.py: o julgamento das medidas da faixa que rola e a comparação com o manifesto."""
import unittest

import regressao_visual_extras as ex
import regressao_visual_faixa as faixa


def medida(**mudancas):
    base = {'nome': '#mesa-etapas', 'tipo': 'faixa', 'scrollWidth': 600, 'clientWidth': 288, 'scrollLeft': 0, 'dataRola': 'fim', 'mascara': True,
            'faixaEsq': 16, 'faixaDir': 304, 'janela': 320, 'ativo': {'texto': '1 Documentos', 'esq': 32, 'dir': 160}}
    return {**base, **mudancas}


class JulgarTest(unittest.TestCase):
    def julgar(self, *medidas):
        return faixa.julgar('caderno__320__claro', list(medidas))

    def test_faixa_com_o_ativo_inteiro_e_o_lado_certo_passa(self):
        self.assertEqual(self.julgar(medida()), ([], []))

    def test_ativo_cortado_na_direita_reprova(self):
        reprovacoes, _ = self.julgar(medida(ativo={'texto': '4 Caderno', 'esq': 250, 'dir': 380}))
        self.assertEqual(len(reprovacoes), 1)
        self.assertIn('4 Caderno', reprovacoes[0])
        self.assertIn('não cabe inteiro', reprovacoes[0])

    def test_ativo_dentro_da_faixa_mas_fora_da_janela_reprova(self):
        reprovacoes, _ = self.julgar(medida(faixaDir=420, scrollWidth=900, clientWidth=404, ativo={'texto': 'Mapa', 'esq': 300, 'dir': 340}, janela=320))
        self.assertTrue(any('não cabe inteiro' in r for r in reprovacoes))

    def test_ativo_cortado_na_esquerda_reprova(self):
        reprovacoes, _ = self.julgar(medida(scrollLeft=100, dataRola='ambos', ativo={'texto': 'Hipóteses', 'esq': -40, 'dir': 60}))
        self.assertTrue(any('Hipóteses' in r for r in reprovacoes))

    def test_item_com_tolerancia_de_subpixel_passa(self):
        self.assertEqual(self.julgar(medida(ativo={'texto': 'x', 'esq': 15.7, 'dir': 304.4}))[0], [])

    def test_data_rola_precisa_bater_com_a_posicao(self):
        self.assertEqual(faixa.lado_esperado(medida(scrollLeft=0)), 'fim')
        self.assertEqual(faixa.lado_esperado(medida(scrollLeft=150)), 'ambos')
        self.assertEqual(faixa.lado_esperado(medida(scrollLeft=312)), 'inicio')
        self.assertEqual(faixa.lado_esperado(medida(scrollWidth=288)), '')
        reprovacoes, _ = self.julgar(medida(scrollLeft=312, dataRola='fim'))
        self.assertTrue(any("data-rola='fim', esperado 'inicio'" in r for r in reprovacoes))

    def test_sem_estouro_a_faixa_nao_tem_atributo(self):
        self.assertEqual(self.julgar(medida(scrollWidth=288, dataRola=None, mascara=False)), ([], []))
        reprovacoes, _ = self.julgar(medida(scrollWidth=288, dataRola='fim'))
        self.assertTrue(any("esperado ''" in r for r in reprovacoes))

    def test_atributo_sem_mascara_reprova(self):
        reprovacoes, _ = self.julgar(medida(mascara=False))
        self.assertTrue(any('sem mask-image' in r for r in reprovacoes))

    def test_tabela_que_rola_nao_e_reprovada_nem_avisada(self):
        tabela = medida(nome='div.mesa-table-wrap', tipo='tabela', dataRola=None, mascara=False, ativo=None)
        self.assertEqual(self.julgar(tabela), ([], []))

    def test_elemento_que_rola_e_nao_e_faixa_vira_aviso_com_o_ativo_a_vista(self):
        abas = medida(nome='nav.mesa-tabs', tipo='outro', dataRola=None, mascara=False, ativo={'texto': 'Acervo cadastrado', 'esq': 16, 'dir': 200})
        reprovacoes, avisos = self.julgar(abas)
        self.assertEqual(reprovacoes, [])
        self.assertEqual(len(avisos), 1)
        self.assertIn('nav.mesa-tabs', avisos[0])

    def test_elemento_que_rola_e_nao_e_faixa_com_o_ativo_cortado_reprova(self):
        abas = medida(nome='nav.notebook-tabs', tipo='outro', dataRola=None, mascara=False, ativo={'texto': 'Trechos com fonte', 'esq': 230, 'dir': 420})
        reprovacoes, _ = self.julgar(abas)
        self.assertEqual(len(reprovacoes), 1)

    def test_resumo_guarda_so_o_que_rola_ou_e_faixa(self):
        quieto = medida(nome='nav.quieto', tipo='outro', scrollWidth=288)
        faixa_quieta = medida(nome='.quadros-abas', scrollWidth=288)
        resumo = faixa.resumo_interno([medida(), quieto, faixa_quieta])
        self.assertEqual([r['nome'] for r in resumo], ['#mesa-etapas', '.quadros-abas'])
        self.assertEqual(set(resumo[0]), {'nome', 'tipo', 'scrollWidth', 'clientWidth'})


class PilulasTest(unittest.TestCase):
    def pilula(self, largura, cliente=288):
        return {'nome': '#caderno-abas', 'cliente': cliente, 'rola': False, 'largura': largura, 'texto': 'Trechos com fonte e contribuições'}

    def test_pilula_que_cabe_com_a_folga_passa(self):
        self.assertEqual(faixa.julgar_pilulas('caderno__320__claro', [self.pilula(267.8)]), [])
        self.assertEqual(faixa.julgar_pilulas('x', [self.pilula(272.0)]), [])   # exatamente faixa menos folga

    def test_pilula_mais_larga_que_a_faixa_menos_a_folga_reprova(self):
        reprovacoes = faixa.julgar_pilulas('caderno__320__claro', [self.pilula(273.0)])
        self.assertEqual(len(reprovacoes), 1)
        self.assertIn('Trechos com fonte e contribuições', reprovacoes[0])
        self.assertIn('cabem 272', reprovacoes[0])


class ComparacaoTest(unittest.TestCase):
    def test_sem_a_chave_no_manifesto_nao_ha_o_que_comparar(self):
        self.assertEqual(faixa.novas_internas({}, {'rolagem_interna': {'a__320__claro': [{'nome': 'x', 'tipo': 'outro'}]}}), {})

    def test_so_o_elemento_novo_reprova(self):
        antes = {'rolagem_interna': {'a__320__claro': [{'nome': '#mesa-etapas', 'tipo': 'faixa'}]}}
        agora = {'rolagem_interna': {'a__320__claro': [{'nome': '#mesa-etapas', 'tipo': 'faixa'}, {'nome': 'nav.mesa-tabs', 'tipo': 'outro'}],
                                     'b__320__claro': [{'nome': 'div.x', 'tipo': 'outro'}]}}
        self.assertEqual(faixa.novas_internas(antes, agora), {'a__320__claro': ['nav.mesa-tabs'], 'b__320__claro': ['div.x']})
        self.assertEqual(faixa.novas_internas(antes, agora, nomes=['a__320__claro']), {'a__320__claro': ['nav.mesa-tabs']})


class CenariosTest(unittest.TestCase):
    def test_a_prova_pede_320_390_e_430_em_caderno_documentos_e_quadros(self):
        self.assertEqual({k: v['viewport']['width'] for k, v in faixa.CENARIOS_FAIXA.items()}, {'320': 320, '390': 390, '430': 430})
        self.assertEqual(faixa.TELAS_FAIXA, ('caderno', 'documentos', 'quadros'))
        for tela in faixa.TELAS_FAIXA:
            self.assertIn(tela, ex.TELAS)

    def test_o_430_e_o_mesmo_das_extras(self):
        self.assertEqual(faixa.CENARIOS_FAIXA['430'], ex.CENARIOS['430'])
        self.assertEqual(ex.TODOS_OS_CENARIOS['430'], ex.CENARIOS['430'])
        self.assertEqual(set(ex.CENARIOS), {'paisagem', '430', 'zoom200', 'reflow320'})   # a linha de base das extras não muda

    def test_a_pasta_da_faixa_nao_e_a_das_extras_nem_a_da_linha_de_base(self):
        self.assertTrue(faixa.pasta_faixa().name.endswith('_faixa'))
        self.assertNotEqual(faixa.pasta_faixa(), ex.pasta_extras())


if __name__ == '__main__':
    unittest.main()
