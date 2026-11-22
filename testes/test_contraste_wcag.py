"""Testes do medidor de contraste WCAG (testes/contraste_wcag.py).

A matemática roda sempre. A parte que mede no navegador usa uma página sintética de razões conhecidas e PULA se o Playwright
ou o Chromium não estiver instalado (ficam fora da imagem da Mesa; ver testes/requirements-teste.txt). A medição das telas
da Mesa roda à mão: `python testes/contraste_wcag.py medir`.
"""
import unittest

import contraste_wcag as cw

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT = True
except ImportError:   # pragma: no cover - depende do ambiente
    PLAYWRIGHT = False

PAGINA = """<!doctype html><meta charset="utf-8"><style>
body{margin:0;background:#ffffff;font:16px Arial}
p{margin:8px}
#ok{color:#767676}                 /* 4,54:1 sobre branco: passa */
#baixo{color:#777777}              /* 4,48:1: reprova (texto comum) */
#grande{color:#777777;font-size:24px}   /* 4,48:1, mas texto grande: passa em 3:1 */
#escuro{background:#202020;color:#8a8a8a}   /* ~4,6:1 sobre #202020: passa */
#translucido{color:rgba(0,0,0,.5)}  /* preto a 50% sobre branco = #808080, 3,95:1: reprova */
#grad{background:linear-gradient(90deg,#ffffff,#000000);color:#555555}   /* 7,5:1 no branco, 2,9:1 no preto da ponta: reprova */
#foto{background-image:url(data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==);color:#000}
#desativado[disabled]{color:#cccccc}
.a:focus-visible{outline:3px solid #ffffff;outline-offset:2px}   /* branco sobre branco: reprova */
.b:focus-visible{outline:3px solid #000000;outline-offset:2px}   /* passa */
.d{background:#ffffff;color:#000}.d:focus-visible{outline:3px solid #ffffff;outline-offset:-3px}   /* anel por dentro: vale o fundo do próprio botão (branco): reprova */
.e{background:#ffffff;color:#000}.e:focus-visible{outline:3px solid #000000;outline-offset:-3px}  /* por dentro, preto sobre branco: passa, mesmo ao lado de um vizinho preto */
.vizinho{display:inline-block;background:#000;width:80px;height:30px;vertical-align:top}
.c:focus-visible{outline:none}                                 /* sem indicador nenhum: reprova */
</style>
<p id="ok">Texto com contraste suficiente</p>
<p id="baixo">Texto abaixo do mínimo</p>
<p id="grande">Texto grande</p>
<p id="escuro">Texto claro sobre fundo escuro</p>
<p id="translucido">Texto translúcido</p>
<p id="grad">Texto sobre gradiente</p>
<p id="foto">Texto sobre imagem</p>
<button id="desativado" disabled>Desativado</button>
<svg width="300" height="40"><rect width="300" height="40" fill="#ffffff"/><text id="svgt" x="10" y="25" fill="#222222">Texto SVG sobre retângulo claro</text></svg>
<button class="d">Anel interno branco</button><span class="vizinho"></span><button class="e">Anel interno preto</button><span class="vizinho"></span>
<button class="a">Foco branco</button><button class="b">Foco preto</button><button class="c">Sem foco</button>
"""


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


@unittest.skipUnless(PLAYWRIGHT, 'Playwright não instalado (testes/requirements-teste.txt)')
class NavegadorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.pw = sync_playwright().start()
            cls.navegador = cls.pw.chromium.launch(args=['--force-color-profile=srgb', '--disable-gpu'])
        except Exception as exc:   # noqa: BLE001 - Chromium ausente
            if hasattr(cls, 'pw'):
                cls.pw.stop()
            raise unittest.SkipTest(f'Chromium indisponível: {str(exc)[:120]}')
        pagina = cls.navegador.new_page(viewport={'width': 600, 'height': 600})
        pagina.set_content(PAGINA)
        pagina.evaluate(cw.JS_PREPARO)
        cls.texto = pagina.evaluate(cw.JS_TEXTO)
        cls.pagina = pagina
        cls.problemas = []
        cls.focos = cw.medir_tela(pagina, 'sintetica', cls.problemas)['focos']

    @classmethod
    def tearDownClass(cls):
        cls.navegador.close()
        cls.pw.stop()

    def item(self, seletor_final):
        achados = [i for i in self.texto['itens'] if i['s'].endswith(seletor_final)]
        self.assertTrue(achados, f'sem medida para {seletor_final}: {self.texto["itens"]}')
        return achados[0]

    def test_limite_4_5(self):
        self.assertFalse(cw.reprovado(self.item('p#ok')))
        self.assertTrue(cw.reprovado(self.item('p#baixo')))

    def test_texto_grande_usa_3(self):
        i = self.item('p#grande')
        self.assertEqual(i['min'], 3)
        self.assertFalse(cw.reprovado(i))

    def test_texto_svg_nao_e_medido_contra_o_proprio_preenchimento(self):
        i = self.item('text#svgt')
        self.assertEqual(i['bg'], '#ffffff')
        self.assertFalse(cw.reprovado(i))

    def test_fundo_escuro(self):
        self.assertFalse(cw.reprovado(self.item('p#escuro')))

    def test_texto_translucido_compoe_com_o_fundo(self):
        i = self.item('p#translucido')
        self.assertEqual(i['fg'], '#808080')
        self.assertTrue(cw.reprovado(i))

    def test_gradiente_vale_a_pior_parada(self):
        i = self.item('p#grad')
        self.assertTrue(cw.reprovado(i))
        self.assertEqual(i['bg'], '#000000')

    def test_imagem_de_fundo_nao_e_medida_mas_e_contada(self):
        self.assertFalse([i for i in self.texto['itens'] if i['s'].endswith('p#foto')])
        self.assertEqual(self.texto['por_motivo'].get('fundo com imagem'), 1)

    def test_desativado_e_isento(self):
        self.assertFalse([i for i in self.texto['itens'] if 'desativado' in i['s']])
        self.assertGreaterEqual(self.texto['isentos'], 1)

    def test_foco(self):
        por_rotulo = {f['t']: f for f in self.focos}
        self.assertTrue(cw.reprovado(por_rotulo['Foco branco']))
        self.assertFalse(cw.reprovado(por_rotulo['Foco preto']))
        self.assertTrue(cw.reprovado(por_rotulo['Sem foco']))
        self.assertTrue(cw.reprovado(por_rotulo['Anel interno branco']))
        self.assertFalse(cw.reprovado(por_rotulo['Anel interno preto']))
        self.assertEqual(self.problemas, [])


if __name__ == '__main__':
    unittest.main()
