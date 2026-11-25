"""O medidor de contraste WCAG reprova de verdade? (suíte lenta; precisa de Playwright e do Chromium).

Abre uma página sintética de razões conhecidas no navegador e confere o que `contraste_wcag.py` mede: limite de 4,5:1, texto grande,
translúcido, gradiente, imagem de fundo, controle desativado, texto SVG, anel de foco por fora e por dentro, a exceção P34 e o campo
sem caixa. Sem Playwright (ou sem o Chromium) o teste PULA; com VLADO_EXIGIR_PLAYWRIGHT=1 (como no CI) FALHA, para um medidor que não
roda nunca passar por verde. A parte que não precisa de navegador está em test_contraste_wcag.py, na suíte rápida.
"""
import os
import unittest

import contraste_wcag as cw

try:
    from playwright.sync_api import sync_playwright
    SEM_PLAYWRIGHT = ''
except ImportError:   # pragma: no cover - depende do ambiente
    SEM_PLAYWRIGHT = 'Playwright não instalado (testes/requirements-teste.txt)'

EXIGIR = os.environ.get('VLADO_EXIGIR_PLAYWRIGHT') == '1'


def indisponivel(motivo):
    """Sem o navegador: falha quando o CI o exige, senão pula."""
    if EXIGIR:
        raise AssertionError(motivo + ' e VLADO_EXIGIR_PLAYWRIGHT=1')
    raise unittest.SkipTest(motivo)


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
<p><select id="contexto-caso" style="border:0;background:transparent;color:#222222"><option>Vila Serena</option></select>
<select id="sem-excecao" style="border:0;background:transparent;color:#222222"><option>Outro campo</option></select></p>
<button class="a">Foco branco</button><button class="b">Foco preto</button><button class="c">Sem foco</button>
"""


class NavegadorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if SEM_PLAYWRIGHT:
            indisponivel(SEM_PLAYWRIGHT)
        try:
            cls.pw = sync_playwright().start()
            cls.navegador = cls.pw.chromium.launch(args=['--force-color-profile=srgb', '--disable-gpu'])
        except Exception as exc:   # noqa: BLE001 - Chromium ausente
            if hasattr(cls, 'pw'):
                cls.pw.stop()
            indisponivel(f'Chromium indisponível: {str(exc)[:120]}')
        pagina = cls.navegador.new_page(viewport={'width': 600, 'height': 600})
        pagina.set_content(PAGINA)
        pagina.evaluate(cw.JS_PREPARO)
        cls.texto = pagina.evaluate(cw.JS_TEXTO, cw.EXCECOES_CAMPO)
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

    def test_excecao_p34_mede_a_seta_e_nao_a_borda(self):
        seta = [i for i in self.texto['itens'] if i['cat'] == 'seta']
        self.assertEqual([i['s'] for i in seta], ['select#contexto-caso'])
        self.assertEqual(seta[0]['excecao'], 'P34')
        self.assertFalse(cw.reprovado(seta[0]))
        self.assertFalse([i for i in self.texto['itens'] if i['cat'] == 'campo' and i['s'].endswith('select#contexto-caso')])
        # sem a exceção, o mesmo campo sem caixa reprova no contorno
        sem = [i for i in self.texto['itens'] if i['cat'] == 'campo' and i['s'].endswith('select#sem-excecao')]
        self.assertEqual(len(sem), 1)
        self.assertTrue(cw.reprovado(sem[0]))

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


PAGINA_FAIXA = """<!doctype html><meta charset="utf-8"><style>
body{margin:0;background:#ffffff;font:16px Arial}
#faixa{position:absolute;left:20px;top:20px;width:300px;overflow-x:auto;white-space:nowrap}
.pilula{display:inline-block;margin:0 16px 0 0;padding:8px 16px;background:#1e4d3e;color:#ffffff}
.vao{display:inline-block;width:250px}
</style>
<div id="faixa"><span class="pilula">Hipóteses</span><span class="vao"></span><span class="pilula" id="mapa">Mapa de relações</span></div>
"""


class FaixaTest(unittest.TestCase):
    """Texto dentro da janela mas cortado pelo overflow da faixa que rola: o medidor mede a pílula, não o fundo da página (Q5, Mapa a 375 px)."""

    def test_item_cortado_pela_faixa_e_medido_sobre_o_proprio_fundo(self):
        if SEM_PLAYWRIGHT:
            indisponivel(SEM_PLAYWRIGHT)
        try:
            pw = sync_playwright().start()
            navegador = pw.chromium.launch(args=['--force-color-profile=srgb', '--disable-gpu'])
        except Exception as exc:   # noqa: BLE001 - Chromium ausente
            indisponivel(f'Chromium indisponível: {str(exc)[:120]}')
        try:
            pagina = navegador.new_page(viewport={'width': 600, 'height': 300})
            pagina.set_content(PAGINA_FAIXA)
            # a segunda pílula fica além da borda direita da faixa (20..320) mas dentro da janela de 600 px
            fora = pagina.evaluate("(() => { const r = document.getElementById('mapa').getBoundingClientRect(); return [r.left + r.width / 2, document.getElementById('faixa').getBoundingClientRect().right]; })()")
            self.assertGreater(fora[0], fora[1], 'o caso de teste precisa começar com o centro do texto fora da faixa')
            self.assertLess(fora[0], 600)
            pagina.evaluate(cw.JS_PREPARO)
            texto = pagina.evaluate(cw.JS_TEXTO, cw.EXCECOES_CAMPO)
            mapa = [i for i in texto['itens'] if i['t'].startswith('Mapa')]
            self.assertEqual(len(mapa), 1, texto)
            self.assertEqual(mapa[0]['bg'], '#1e4d3e')
            self.assertEqual(mapa[0]['fg'], '#ffffff')
            self.assertFalse(cw.reprovado(mapa[0]))
            self.assertGreater(mapa[0]['r'], 9)
            self.assertFalse(texto['nao_medidos'], texto['nao_medidos'])
        finally:
            navegador.close()
            pw.stop()


PAGINA_CORTES = """<!doctype html><meta charset="utf-8"><style>
body{margin:0;background:#ffffff;font:16px Arial}
#faixa{position:absolute;left:20px;top:20px;width:300px;overflow-x:auto;white-space:nowrap}
.vao{display:inline-block;width:330px}
#longe{position:absolute;left:900px;top:100px;pointer-events:none;color:#000000}
#campo{background:#ffffff;color:#000000;border:1px solid #000000}
</style>
<div id="faixa"><span class="vao"></span><input id="campo" value="Campo cortado pela faixa" size="20"></div>
<p id="longe">Texto fora da janela e fora da pilha</p>
"""


class CortesTest(unittest.TestCase):
    """M1 e M2 da Coruja: nenhuma das duas formas de ficar cortado vira texto que some ou 'não medido' à toa."""

    @classmethod
    def setUpClass(cls):
        if SEM_PLAYWRIGHT:
            indisponivel(SEM_PLAYWRIGHT)
        try:
            cls.pw = sync_playwright().start()
            cls.navegador = cls.pw.chromium.launch(args=['--force-color-profile=srgb', '--disable-gpu'])
        except Exception as exc:   # noqa: BLE001 - Chromium ausente
            indisponivel(f'Chromium indisponível: {str(exc)[:120]}')
        pagina = cls.navegador.new_page(viewport={'width': 600, 'height': 300})
        pagina.set_content(PAGINA_CORTES)
        pagina.evaluate(cw.JS_PREPARO)
        cls.texto = pagina.evaluate(cw.JS_TEXTO, cw.EXCECOES_CAMPO)

    @classmethod
    def tearDownClass(cls):
        cls.navegador.close()
        cls.pw.stop()

    def test_texto_fora_da_janela_e_sem_pilha_e_medido_e_nao_vira_nao_medido(self):
        longe = [i for i in self.texto['itens'] if i['t'].startswith('Texto fora da janela')]
        self.assertEqual(len(longe), 1, self.texto)
        self.assertEqual(longe[0]['bg'], '#ffffff')
        self.assertFalse(cw.reprovado(longe[0]))
        self.assertFalse([d for d in self.texto['nao_medidos_detalhe'] if d['t'].startswith('Texto fora')] if 'nao_medidos_detalhe' in self.texto else [])

    def test_campo_cortado_pela_faixa_e_medido_ou_contado(self):
        campo = [i for i in self.texto['itens'] if i['cat'] == 'campo-texto']
        contado = self.texto['por_motivo'].get('fora da área visível', 0)
        self.assertTrue(campo or contado, 'o campo sumiu sem ser medido nem contado')
        self.assertEqual(len(campo), 1, self.texto)   # a rolagem o traz à vista: é medido, não só contado
        self.assertFalse(cw.reprovado(campo[0]))


if __name__ == '__main__':
    unittest.main()
