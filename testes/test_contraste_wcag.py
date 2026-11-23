"""Testes do medidor de contraste WCAG (testes/contraste_wcag.py) que não precisam de navegador: a matemática e o relatório.

Os testes que provam no navegador que o medidor reprova (página sintética de razões conhecidas) ficam em
test_contraste_wcag_navegador.py, na suíte lenta. A medição das telas da Mesa roda à mão: `python testes/contraste_wcag.py medir`.
"""
import unittest

import contraste_wcag as cw


class MatematicaTest(unittest.TestCase):
    def test_extremos(self):
        self.assertAlmostEqual(cw.razao((0, 0, 0), (255, 255, 255)), 21.0, places=2)
        self.assertAlmostEqual(cw.razao((255, 255, 255), (255, 255, 255)), 1.0, places=2)

    def test_cinza_do_limite(self):
        self.assertGreaterEqual(cw.razao(cw.parse_hex('#767676'), (255, 255, 255)), 4.5)
        self.assertLess(cw.razao(cw.parse_hex('#777777'), (255, 255, 255)), 4.5)

    def test_texto_grande(self):
        self.assertTrue(cw.texto_grande(24, 400))
        self.assertTrue(cw.texto_grande(18.66, 700))
        self.assertFalse(cw.texto_grande(18.66, 400))
        self.assertFalse(cw.texto_grande(16, 700))
        self.assertEqual(cw.minimo_do_texto(24, 400), 3.0)
        self.assertEqual(cw.minimo_do_texto(16, 400), 4.5)

    def test_arredondamento_nunca_sobe(self):
        self.assertEqual(cw.arredondar(4.499), 4.49)
        self.assertTrue(cw.reprovado({'r': 4.499, 'min': 4.5}))
        self.assertFalse(cw.reprovado({'r': 4.5, 'min': 4.5}))
        self.assertTrue(cw.reprovado({'r': 0, 'min': 3, 'falha_tipo': 'sem contorno de foco'}))

    def test_foco_so_por_sublinhado_mede_a_cor_do_sublinhado(self):
        sem = {l: ['rgb(0, 0, 0)', '0px', 'none'] for l in ('Top', 'Right', 'Bottom', 'Left')}
        base = {'cat': 'foco', 's': 'a', 't': 'x', 'adj': ['#ffffff'], 'proprio': ['#ffffff']}
        sem_deco = {'bg': 'rgba(0, 0, 0, 0)', 'bordas': sem, 'deco': 'none', 'decoCor': 'rgb(240, 240, 240)', 'cor': 'rgb(20, 20, 20)', 'sombra': 'none'}
        com_deco = {**sem_deco, 'deco': 'underline'}
        r = cw.indicador_alternativo(base, com_deco, sem_deco, lambda css: '#f0f0f0' if '240' in css else '#141414')
        self.assertTrue(cw.reprovado(r), 'sublinhado quase branco sobre branco não pode passar')
        self.assertLess(r['r'], 1.2)
        com_deco_escuro = {**com_deco, 'decoCor': 'rgb(20, 20, 20)'}
        r = cw.indicador_alternativo(base, com_deco_escuro, sem_deco, lambda css: '#f0f0f0' if '240' in css else '#141414')
        self.assertFalse(cw.reprovado(r))
        self.assertGreater(r['r'], 15)

    def test_foco_sem_contorno_mede_a_mudanca(self):
        base = {'cat': 'foco', 's': 'a', 't': 'x', 'adj': ['#ffffff'], 'proprio': ['#ffffff']}
        sem = {l: ['rgb(0, 0, 0)', '0px', 'none'] for l in ('Top', 'Right', 'Bottom', 'Left')}
        igual = {'bg': 'rgba(0, 0, 0, 0)', 'bordas': sem, 'deco': 'none', 'cor': 'x', 'sombra': 'none'}
        r = cw.indicador_alternativo(base, igual, dict(igual), lambda css: None)
        self.assertTrue(cw.reprovado(r))
        com_borda = {**igual, 'bordas': {**sem, 'Bottom': ['rgb(0, 0, 0)', '2px', 'solid']}}   # só a borda de baixo muda, como no caderno
        r = cw.indicador_alternativo(base, com_borda, dict(igual), lambda css: '#000000')
        self.assertFalse(cw.reprovado(r))
        r = cw.indicador_alternativo(base, com_borda, dict(igual), lambda css: '#f8f8f8')
        self.assertTrue(cw.reprovado(r))


class RelatorioTest(unittest.TestCase):
    def test_excecao_declarada_aparece_no_relatorio_com_o_pior_caso(self):
        import tempfile
        from pathlib import Path
        seta = {'cat': 'seta', 's': 'select#contexto-caso', 't': 'x', 'fg': '#222222', 'bg': '#ffffff', 'r': 15.9, 'min': 3, 'excecao': 'P34'}
        texto = {'cat': 'campo-texto', 's': 'select#contexto-caso', 't': 'x', 'fg': '#222222', 'bg': '#ffffff', 'r': 15.9, 'min': 4.5, 'excecao': 'P34'}
        dados = {'navegador': 'x', 'problemas': [], 'gerado_em_utc': 'hoje',
                 'resultados': {'inicio__375__claro': {'tela': 'inicio', 'largura': 375, 'tema': 'claro', 'focos': [], 'focos_invisiveis': 0, 'focos_isentos': 0,
                                                       'texto': {'itens': [seta, texto], 'nao_medidos': [], 'por_motivo': {}, 'isentos': 0, 'nos': 2}}}}
        with tempfile.TemporaryDirectory() as tmp:
            md = cw.escrever_relatorio(dados, Path(tmp)).read_text(encoding='utf-8')
        self.assertIn('## Exceções declaradas', md)
        self.assertIn('P34', md)
        self.assertIn('pior seta: 15.90:1', md)
        self.assertIn('Nenhuma reprovação.', md)


if __name__ == '__main__':
    unittest.main()
