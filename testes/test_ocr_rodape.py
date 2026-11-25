"""L7: a página digitalizada que só tem um rodapé de texto nativo também passa pelo OCR.

O caso comum: um documento escaneado ganha, na assinatura eletrônica, um rodapé de texto nativo (quem assinou,
quando, o código de verificação). Esse rodapé passa do mínimo de 10 caracteres, e o corpo da página, que é imagem,
nunca era lido. Agora a página entra no OCR quando imagens cobrem a maior parte dela e o texto nativo é curto; o
OCR só vai à página quando o texto nativo dela fica só nas faixas de cabeçalho e rodapé (B3 da Coruja: o ofício
com timbre como imagem de página inteira e corpo nativo curto continua nativo), e só substitui o texto nativo quando traz ao menos GANHO_MINIMO_OCR caracteres a mais (cerca de uma frase), para que uma página nativa com uma
foto grande e a legenda continue com o texto nativo.
"""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import extrair_pdf as ex  # noqa: E402
import test_ocr as ocr_de_teste  # noqa: E402  (módulo, para não recoletar os TestCases dele)

HAS_FITZ = importlib.util.find_spec('pymupdf') is not None
HAS_PYPDF = importlib.util.find_spec('pypdf') is not None
CORPO = 'Termo aditivo sintetico numero 7 prorroga a vigencia do contrato por doze meses.'
RODAPE = ('Documento assinado eletronicamente por Pessoa Sintetica em 01/02/2025 as 10:00. '
          'Codigo verificador 0000000 e codigo CRC ABCDEF12.')
OFICIO = ('Oficio sintetico numero 12. Encaminhamos a copia do contrato e do aditivo, '
          'conforme solicitado. Atenciosamente, a Secretaria.')
LEGENDA = 'Foto sintetica da fachada do predio, tirada pela equipe em visita de campo.'


def _png(texto, largura=480, altura=600):
    import pymupdf
    origem = pymupdf.open()
    pagina = origem.new_page(width=largura, height=altura)
    pagina.insert_textbox(pymupdf.Rect(20, 20, largura - 20, altura - 20), texto, fontsize=20, fontname='helv')
    return pagina.get_pixmap(dpi=150).tobytes('png')


def pdf(caminho, paginas):
    """paginas: lista de ('digitalizada_com_rodape' | 'foto_com_legenda' | 'nativa' | 'foto_pequena' |
    'oficio_com_timbre')."""
    import pymupdf
    documento = pymupdf.open()
    for tipo in paginas:
        pagina = documento.new_page(width=480, height=640)
        if tipo == 'digitalizada_com_rodape':
            pagina.insert_image(pymupdf.Rect(0, 0, 480, 600), stream=_png(CORPO))
            pagina.insert_text((20, 625), RODAPE[:80], fontsize=7, fontname='helv')
            pagina.insert_text((20, 635), RODAPE[80:], fontsize=7, fontname='helv')
        elif tipo == 'foto_com_legenda':
            pagina.insert_image(pymupdf.Rect(0, 0, 480, 560), stream=_png('', 480, 560))
            pagina.insert_text((20, 600), LEGENDA, fontsize=9, fontname='helv')
        elif tipo == 'oficio_com_timbre':
            # Letterhead drawn as a full-page image (logo on top, line at the bottom), short native body.
            pagina.insert_image(pagina.rect, stream=_png('PREFEITURA SINTETICA - GABINETE', 480, 640))
            pagina.insert_textbox(pymupdf.Rect(40, 200, 440, 400), OFICIO, fontsize=11, fontname='helv')
        elif tipo == 'foto_pequena':
            pagina.insert_image(pymupdf.Rect(20, 20, 160, 120), stream=_png('', 140, 100))
            pagina.insert_text((20, 300), LEGENDA, fontsize=9, fontname='helv')
        else:
            pagina.insert_textbox(pymupdf.Rect(20, 20, 460, 620), (CORPO + ' ') * 12, fontsize=11, fontname='helv')
    documento.save(str(caminho))
    documento.close()


@unittest.skipUnless(HAS_FITZ and HAS_PYPDF, 'Requer PyMuPDF e pypdf')
class RodapeTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.pasta = Path(temp.name)

    def extrair(self, paginas, reconhecido=None):
        """Extrai com um OCR simulado: devolve o texto de `reconhecido` para as páginas pedidas."""
        fonte = self.pasta / 'doc.pdf'
        pdf(fonte, paginas)
        chamadas = []

        def reconhecer(origem, candidatas):
            chamadas.append(list(candidatas))
            return {'motor': 'simulado', 'versoes': {}, 'idiomas': 'por',
                    'paginas': {n: {'texto': (reconhecido or {}).get(n, '')} for n in candidatas}}
        with patch('extrair_pdf.ocr.diagnostico', return_value={'disponivel': True}), \
                patch('extrair_pdf.ocr.reconhecer', side_effect=reconhecer):
            info = ex.extrair_pdf(fonte, 'D001', self.pasta / 'D001.md')
        return info, chamadas, (self.pasta / 'D001.md').read_text(encoding='utf-8')

    def test_pagina_digitalizada_com_rodape_nativo_vai_ao_ocr(self):
        lido = CORPO + '\n' + RODAPE
        info, chamadas, texto = self.extrair(['digitalizada_com_rodape', 'nativa'], {1: lido})
        self.assertEqual(chamadas, [[1]])
        self.assertEqual(info['paginas_imagem_com_rodape'], [1])
        self.assertEqual(info['paginas_origem'], {'1': 'ocr', '2': 'texto_nativo'})
        self.assertIn('prorroga a vigencia', texto)
        self.assertIn('cobertas por imagem com so um rodape de texto nativo', info['metodo'])

    def test_rodape_sozinho_passa_do_minimo_de_texto_nativo(self):
        # The premise of L7: without the image rule, the footer alone keeps the page away from the OCR.
        import pypdf
        fonte = self.pasta / 'so.pdf'
        pdf(fonte, ['digitalizada_com_rodape'])
        nativo = pypdf.PdfReader(fonte).pages[0].extract_text()
        self.assertGreater(ex._alfanumericos(nativo), ex.MINIMO_ALFANUMERICOS_NATIVO)
        self.assertLessEqual(ex._alfanumericos(nativo), ex.MAXIMO_ALFANUMERICOS_RODAPE)
        fracao, corpo = ex.imagem_e_corpo(fonte, [1])[1]
        self.assertGreaterEqual(fracao, ex.COBERTURA_MINIMA_IMAGEM)
        self.assertFalse(corpo)  # o texto nativo só está na faixa do rodapé

    def test_foto_grande_com_legenda_fica_com_o_texto_nativo(self):
        # O OCR da página renderizada traz a legenda e pouco mais: não ganha do texto nativo.
        info, chamadas, texto = self.extrair(['foto_com_legenda'], {1: LEGENDA + ' ~ ~'})
        self.assertEqual(chamadas, [[1]])
        self.assertEqual(info['paginas_origem'], {'1': 'texto_nativo'})
        self.assertIn('Foto sintetica da fachada', texto)

    def test_oficio_com_timbre_e_corpo_nativo_curto_fica_com_o_texto_nativo(self):
        """B3: o timbre é imagem de página inteira, mas o corpo é texto nativo: a página não vai ao OCR, e o
        texto nativo, exato, não é trocado por uma leitura que pode errar."""
        import pypdf
        fonte = self.pasta / 'oficio.pdf'
        pdf(fonte, ['oficio_com_timbre'])
        nativo = pypdf.PdfReader(fonte).pages[0].extract_text()
        self.assertLessEqual(ex._alfanumericos(nativo), ex.MAXIMO_ALFANUMERICOS_RODAPE)  # curto como um rodapé
        fracao, corpo = ex.imagem_e_corpo(fonte, [1])[1]
        self.assertGreaterEqual(fracao, ex.COBERTURA_MINIMA_IMAGEM)
        self.assertTrue(corpo)
        info, chamadas, texto = self.extrair(['oficio_com_timbre'], {1: 'PREFEITURA SINTETICA GABINETE ' + OFICIO * 3})
        self.assertEqual(chamadas, [])
        self.assertNotIn('paginas_imagem_com_rodape', info)
        self.assertEqual(info['paginas_origem'], {'1': 'texto_nativo'})
        self.assertIn('Encaminhamos a copia do contrato', texto)

    def test_foto_pequena_e_pagina_nativa_nao_vao_ao_ocr(self):
        info, chamadas, _ = self.extrair(['foto_pequena', 'nativa'])
        self.assertEqual(chamadas, [])
        self.assertNotIn('paginas_imagem_com_rodape', info)
        self.assertEqual(info['paginas_origem'], {'1': 'texto_nativo', '2': 'texto_nativo'})

    def test_sem_pymupdf_vale_so_o_minimo_de_texto_nativo(self):
        with patch('extrair_pdf.imagem_e_corpo', return_value={}):
            info, chamadas, _ = self.extrair(['digitalizada_com_rodape'], {1: CORPO})
        self.assertEqual(chamadas, [])
        self.assertEqual(info['paginas_origem'], {'1': 'texto_nativo'})

    def test_sem_ocr_pedido_nada_muda(self):
        fonte = self.pasta / 'doc.pdf'
        pdf(fonte, ['digitalizada_com_rodape'])
        with patch('extrair_pdf.ocr.reconhecer') as reconhecer:
            info = ex.extrair_pdf(fonte, 'D001', self.pasta / 'D001.md', ocr_ativo=False)
        reconhecer.assert_not_called()
        self.assertEqual(info['paginas_origem'], {'1': 'texto_nativo'})


@ocr_de_teste.PRECISA_OCR  # skip without Tesseract; a failure under VLADO_EXIGIR_OCR=1 (the CI job)
class RodapeComOcrDeVerdadeTest(unittest.TestCase):
    """Com o Tesseract instalado, o corpo da página digitalizada é lido de fato."""

    def test_corpo_reconhecido(self):
        with tempfile.TemporaryDirectory() as pasta:
            fonte = Path(pasta) / 'doc.pdf'
            pdf(fonte, ['digitalizada_com_rodape'])
            info = ex.extrair_pdf(fonte, 'D001', Path(pasta) / 'D001.md')
            texto = (Path(pasta) / 'D001.md').read_text(encoding='utf-8')
        self.assertEqual(info['paginas_origem'], {'1': 'ocr'}, info.get('ocr_indisponivel'))
        self.assertIn('vigencia', texto.lower())


if __name__ == '__main__':
    unittest.main()
