"""Orientação das páginas digitalizadas nos dois motores de OCR.

Com confiança do OSD de pelo menos ``ocr.CONFIANCA_OSD_MINIMA`` (14, o padrão do OCRmyPDF) a
página gira como o OSD diz. Abaixo disso o OSD erra com frequência: pede "gire 180" para páginas
RETAS em maiúsculas e tabelas de valores borradas ou em baixa resolução. Nesses casos a página é
lida como está e como o OSD sugere, e o giro só vence se a confiança média das palavras superar a
leitura original por ``ocr.MARGEM_LEITURA_DUPLA``; a decisão vai para o recibo. Assim páginas
curtas giradas são endireitadas e páginas retas ficam retas. Os testes com OCR real pulam sem
Tesseract, exceto com ``VLADO_EXIGIR_OCR=1`` (CI), quando falham.
"""
import importlib.util
import io
import os
from pathlib import Path
import random
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import ocr  # noqa: E402
from auxiliar_node import pular_sem_ocr  # noqa: E402

HAS_FITZ = importlib.util.find_spec('pymupdf') is not None
HAS_PYPDF = importlib.util.find_spec('pypdf') is not None
HAS_TESSERACT = HAS_FITZ and ocr.diagnostico()['tesseract']['disponivel']
HAS_OCRMYPDF = HAS_TESSERACT and ocr._ocrmypdf_disponivel()
PROSA = ('Relatório da fiscalização sobre a licitação número 42. A comissão examinou os contratos '
         'firmados pela prefeitura entre janeiro e junho, os pagamentos feitos aos fornecedores e as '
         'notas fiscais apresentadas. Foram encontradas divergências entre os valores empenhados e os '
         'valores pagos, além de documentos sem a assinatura do responsável pelo setor de compras. ')
LINHAS = ['Relatório da fiscalização sobre a licitação número 42, aberta pela prefeitura em março.',
          'A comissão examinou os contratos firmados entre janeiro e junho e os pagamentos feitos.',
          'Foram encontradas divergências entre os valores empenhados e os valores efetivamente pagos.',
          'Alguns documentos não tinham a assinatura do responsável pelo setor de compras da cidade.',
          'O relatório recomenda a abertura de processo administrativo e o envio ao Ministério Público.']


def valores_da_tabela():
    """45 linhas x 5 colunas de valores em reais, fixos (semente 3)."""
    sorteio = random.Random(3)
    return [[f'{sorteio.randint(1, 999)}.{sorteio.randint(0, 999):03d},{sorteio.randint(0, 99):02d}'
             for _ in range(5)] for _ in range(45)]


def pagina_digitalizada(path, texto, *, fonte=11, rotacao=0, degradacao=None, margem=60):
    """A4 só com imagem (sem camada de texto), degradada e girada `rotacao` graus se pedido."""
    import pymupdf
    from PIL import Image, ImageFilter
    origem = pymupdf.open()
    pagina = origem.new_page(width=595, height=842)
    pagina.insert_textbox(pymupdf.Rect(margem, margem, 595 - margem, 842 - margem), texto,
                          fontsize=fonte, fontname='helv')
    imagem = Image.open(io.BytesIO(pagina.get_pixmap(dpi=200).tobytes('png'))).convert('L')
    if degradacao == 'borrada':
        imagem = imagem.filter(ImageFilter.GaussianBlur(1.6))
    elif degradacao == 'baixa_resolucao':  # cerca de 75 dpi, ampliada de volta
        largura, altura = imagem.size
        imagem = imagem.resize((largura * 3 // 8, altura * 3 // 8), Image.BILINEAR).resize((largura, altura), Image.BILINEAR)
    if rotacao:
        imagem = imagem.rotate(rotacao, expand=True, fillcolor=255)
    buffer = io.BytesIO()
    imagem.save(buffer, 'PNG')
    largura, altura = (842, 595) if rotacao in (90, 270) else (595, 842)
    documento = pymupdf.open()
    nova = documento.new_page(width=largura, height=altura)
    nova.insert_image(nova.rect, stream=buffer.getvalue())
    documento.save(path)
    return Path(path)


class DecisaoDeOrientacaoTest(unittest.TestCase):
    """Regras sem OCR real: limiar, medida e escolha da leitura."""

    def test_ocrmypdf_usa_o_limiar_conservador(self):
        chamadas = []

        def falso(args, **kwargs):
            chamadas.append(args)
            Path(args[args.index('--sidecar') + 1]).write_text('Texto.', encoding='utf-8')
            return type('P', (), {'returncode': 0, 'stdout': b'', 'stderr': b''})()

        with tempfile.TemporaryDirectory() as pasta:
            pdf = Path(pasta) / 'a.pdf'
            pdf.write_bytes(b'%PDF-1.4')
            config = {**ocr.configuracao(), 'tesseract': 'tesseract', 'tessdata': None, 'motor': 'auto'}
            with patch('ocr._executar', side_effect=falso), patch('ocr._versoes', return_value={}):
                ocr._motor_ocrmypdf(pdf, [1], 1, config)
        argumentos = chamadas[0]
        self.assertIn('--rotate-pages', argumentos)
        self.assertEqual(argumentos[argumentos.index('--rotate-pages-threshold') + 1], str(ocr.CONFIANCA_OSD_MINIMA))
        # Upright pages in capitals measure up to ~9 asking for 180; full pages measure 17 or more.
        self.assertGreaterEqual(ocr.CONFIANCA_OSD_MINIMA, 10)
        self.assertLessEqual(ocr.CONFIANCA_OSD_MINIMA, 15)

    def test_tesseract_direto_nao_gira_so_pelo_osd_abaixo_do_limiar(self):
        saida = type('P', (), {'returncode': 0, 'stdout': b'Rotate: 180\nOrientation confidence: 8.71\n', 'stderr': b''})()
        config = {**ocr.configuracao(), 'tesseract': 'tesseract', 'tessdata': None}
        with patch('ocr._executar', return_value=saida):
            self.assertEqual(ocr._giro_osd(Path('p.png'), config), 0)
            self.assertEqual(ocr._osd(Path('p.png'), config), (180, 8.71))
        saida.stdout = b'Rotate: 180\nOrientation confidence: 18.75\n'
        with patch('ocr._executar', return_value=saida):
            self.assertEqual(ocr._giro_osd(Path('p.png'), config), 180)

    def test_tesseract_direto_roda_com_uma_thread_openmp(self):
        # Two OCR jobs at once with OpenMP threads: 100-250 s per page and timeouts; one thread: 3-4 s.
        saida = type('P', (), {'returncode': 0, 'stdout': b'Rotate: 0\nOrientation confidence: 20\n', 'stderr': b''})()
        config = {**ocr.configuracao(), 'tesseract': 'tesseract', 'tessdata': None}
        for definido, esperado in ((None, '1'), ('3', '3')):
            ambiente = {k: v for k, v in os.environ.items() if k != 'OMP_THREAD_LIMIT'}
            if definido:
                ambiente['OMP_THREAD_LIMIT'] = definido
            with self.subTest(definido=definido), patch.dict(os.environ, ambiente, clear=True), \
                    patch('ocr._executar', return_value=saida) as executar:
                ocr._osd(Path('p.png'), config)
                self.assertEqual(executar.call_args.kwargs['env']['OMP_THREAD_LIMIT'], esperado)

    def test_medida_pondera_a_confianca_pelos_caracteres(self):
        cabecalho = 'level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext'
        linhas = [cabecalho, '5\t1\t1\t1\t1\t1\t0\t0\t1\t1\t90\tlicitação', '5\t1\t1\t1\t1\t2\t0\t0\t1\t1\t30\tde',
                  '5\t1\t1\t1\t1\t3\t0\t0\t1\t1\t-1\t', '4\t1\t1\t1\t1\t0\t0\t0\t1\t1\t-1\t', '5\t1\t1\t1\t1\t4\t0\t0\t1\t1\t50\t--']
        # 'licitação' has 9 alphanumeric characters at 90, 'de' 2 at 30; empty words and punctuation do not count.
        self.assertEqual(ocr._medida_tsv('\n'.join(linhas)), (round((90 * 9 + 30 * 2) / 11, 1), 2))

    def _decidir(self, confianca, medida_original, medida_girada):
        pagina = type('Pagina', (), {'rotation': 0, 'set_rotation': lambda self, r: setattr(self, 'rotation', r)})()
        leituras = {'p.png': ('como esta', medida_original, 5), 'p_g180.png': ('girada', medida_girada, 5)}
        with patch('ocr._osd', return_value=(180, confianca)), patch('ocr._renderizar'), \
                patch('ocr._ler_com_medida', side_effect=lambda imagem, config: leituras[imagem.name]):
            return ocr._orientar_pagina(pagina, Path('p.png'), {})

    def test_leitura_dupla_so_gira_quando_a_girada_vence_pela_margem(self):
        margem = ocr.MARGEM_LEITURA_DUPLA
        texto, registro = self._decidir(5.0, 45.0, 45.0 + margem)
        self.assertEqual((texto, registro['decisao'], registro['giro_aplicado']), ('girada', 'leitura_dupla', 180))
        self.assertEqual((registro['original']['medida'], registro['girada']['medida']), (45.0, 45.0 + margem))
        texto, registro = self._decidir(5.0, 80.0, 80.0 + margem - 0.1)
        self.assertEqual((texto, registro['giro_aplicado']), ('como esta', 0))
        # A turned reading of junk (an upright grid without text read 0 and 25.6) never wins.
        texto, registro = self._decidir(5.0, 0.0, ocr.MEDIDA_MINIMA_GIRADA - 0.1)
        self.assertEqual((texto, registro['giro_aplicado']), ('como esta', 0))
        texto, registro = self._decidir(ocr.CONFIANCA_OSD_MINIMA, 0.0, 0.0)
        self.assertEqual((texto, registro['decisao'], registro['giro_aplicado']), ('girada', 'osd', 180))


@pular_sem_ocr(HAS_TESSERACT and HAS_PYPDF, 'Requer Tesseract (por, eng, osd), PyMuPDF e pypdf')
class OrientacaoComOcrRealTest(unittest.TestCase):
    MOTORES = ('ocrmypdf', 'tesseract') if HAS_OCRMYPDF else ('tesseract',)

    def setUp(self):
        if os.environ.get('VLADO_EXIGIR_OCR') == '1':
            self.assertTrue(HAS_OCRMYPDF, 'VLADO_EXIGIR_OCR=1 exige o OCRmyPDF')
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.pasta = Path(pasta.name)

    def reconhecer(self, motor, pdf):
        with patch.dict(os.environ, {'VLADO_OCR_MOTOR': motor, 'VLADO_OCR': '1'}):
            resultado = ocr.reconhecer(pdf, [1])
        self.assertEqual(resultado['motor'], motor, resultado.get('avisos'))
        return resultado['paginas'][1]

    def assertLeProsa(self, pdf):
        for motor in self.MOTORES:
            with self.subTest(pdf=pdf.name, motor=motor):
                pagina = self.reconhecer(motor, pdf)
                texto = pagina.get('texto', '').lower()
                self.assertIn('fiscaliza', texto, pagina.get('orientacao'))
                self.assertIn('licita', texto, pagina.get('orientacao'))

    def test_pagina_cheia_girada_e_endireitada(self):
        for rotacao in (90, 180, 270):
            self.assertLeProsa(pagina_digitalizada(self.pasta / f'cheia{rotacao}.pdf', PROSA * 6, rotacao=rotacao))

    def test_pagina_curta_girada_e_endireitada_pela_leitura_dupla(self):
        for linhas in (1, 3):
            for rotacao in (90, 180, 270):
                self.assertLeProsa(pagina_digitalizada(self.pasta / f'curta{linhas}_{rotacao}.pdf',
                                                       '\n'.join(LINHAS[:linhas]), rotacao=rotacao))

    def test_pagina_reta_em_maiusculas_nao_e_virada(self):
        for linhas in (1, 3, 20):
            texto = '\n'.join(LINHAS[i % len(LINHAS)] for i in range(linhas)).upper()
            pdf = pagina_digitalizada(self.pasta / f'caixa{linhas}.pdf', texto)
            for motor in self.MOTORES:
                with self.subTest(motor=motor, linhas=linhas):
                    pagina = self.reconhecer(motor, pdf)
                    lido = pagina.get('texto', '').upper()
                    self.assertIn('FISCALIZA', lido, pagina.get('orientacao'))
                    self.assertIn('LICITA', lido, pagina.get('orientacao'))
                    self.assertEqual(pagina.get('orientacao', {}).get('giro_aplicado', 0), 0)

    def test_tabela_de_valores_reta_nao_e_virada(self):
        valores = valores_da_tabela()
        texto = '\n'.join('  '.join(f'{v:>11}' for v in linha) for linha in valores)
        esperados = {v for linha in valores for v in linha}
        for degradacao in ('borrada', 'baixa_resolucao'):
            # OSD asks for 180 on these upright pages, with confidence 2 to 5.
            pdf = pagina_digitalizada(self.pasta / f'tabela_{degradacao}.pdf', texto, fonte=9,
                                      degradacao=degradacao, margem=50)
            for motor in self.MOTORES:
                with self.subTest(motor=motor, degradacao=degradacao):
                    pagina = self.reconhecer(motor, pdf)
                    lidos = set(re.findall(r'\d{1,3}\.\d{3},\d{2}', pagina.get('texto', '')))
                    # Upright, OCR reads 97-100% of the values; turned upside down, none.
                    self.assertGreaterEqual(len(lidos & esperados), int(len(esperados) * 0.9), pagina.get('orientacao'))
                    self.assertEqual(pagina.get('orientacao', {}).get('giro_aplicado', 0), 0)

    def test_recibo_registra_orientacao_e_medida(self):
        from extrair_pdf import extrair_pdf
        pdf = pagina_digitalizada(self.pasta / 'curta.pdf', '\n'.join(LINHAS[:1]), rotacao=180)
        for motor in self.MOTORES:
            with self.subTest(motor=motor), patch.dict(os.environ, {'VLADO_OCR_MOTOR': motor}):
                alvo = self.pasta / f'curta_{motor}.md'
                resultado = extrair_pdf(pdf, 'D001', alvo)
                registro = resultado['ocr_orientacao']['1']
                self.assertEqual((registro['decisao'], registro['giro_aplicado'], registro['osd_giro']),
                                 ('leitura_dupla', 180, 180))
                self.assertLess(registro['osd_confianca'], ocr.CONFIANCA_OSD_MINIMA)
                self.assertGreaterEqual(registro['girada']['medida'],
                                        registro['original']['medida'] + ocr.MARGEM_LEITURA_DUPLA)
                cabecalho = alvo.read_text(encoding='utf-8').split('## D001')[0]
                self.assertIn('Orientacao do OCR por pagina: 1=girada 180 graus (OSD sugeriu 180', cabecalho)


if __name__ == '__main__':
    unittest.main()
