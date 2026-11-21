"""Orientação das páginas digitalizadas nos dois motores de OCR.

Com confiança do OSD de pelo menos ``ocr.CONFIANCA_OSD_MINIMA`` (14, o padrão do OCRmyPDF) a
página gira como o OSD diz. Abaixo disso o OSD erra com frequência: pede "gire 180" para páginas
RETAS em maiúsculas e tabelas de valores borradas ou em baixa resolução. Nesses casos a página é
lida como está e como o OSD sugere, e o giro só vence se a confiança média das palavras superar a
leitura original por ``ocr.MARGEM_LEITURA_DUPLA``; a decisão vai para o recibo. Assim páginas
curtas giradas são endireitadas e páginas retas ficam retas. Os testes com OCR real pulam sem
Tesseract, exceto com ``VLADO_EXIGIR_OCR=1`` (CI), quando falham.
"""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
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


def valores_da_tabela(linhas=45, semente=3):
    """`linhas` x 5 colunas de valores em reais, fixos pela semente."""
    sorteio = random.Random(semente)
    return [[f'{sorteio.randint(1, 999)}.{sorteio.randint(0, 999):03d},{sorteio.randint(0, 99):02d}'
             for _ in range(5)] for _ in range(linhas)]


def pagina_digitalizada(path, texto, *, fonte=11, rotacao=0, degradacao=None, margem=60, nome_fonte='helv'):
    """A4 só com imagem (sem camada de texto), degradada e girada `rotacao` graus se pedido."""
    import pymupdf

    def desenhar(pagina):
        pagina.insert_textbox(pymupdf.Rect(margem, margem, 595 - margem, 842 - margem), texto,
                              fontsize=fonte, fontname=nome_fonte)
    return pagina_desenhada(path, desenhar, rotacao=rotacao, degradacao=degradacao)


def grade_de_numeros(semente):
    """18 x 6 células, 70% delas com um número de até 5 dígitos (fixos pela semente)."""
    sorteio = random.Random(semente)
    return [[str(sorteio.randint(1, 99999)) if sorteio.random() < 0.7 else '' for _ in range(6)] for _ in range(18)]


def desenhar_grade(celulas):
    def desenhar(pagina):
        x0, y0, x1, y1 = 60, 80, 535, 700
        for i in range(len(celulas) + 1):
            y = y0 + (y1 - y0) * i / len(celulas)
            pagina.draw_line((x0, y), (x1, y))
        for j in range(7):
            x = x0 + (x1 - x0) * j / 6
            pagina.draw_line((x, y0), (x, y1))
        for i, linha in enumerate(celulas):
            for j, valor in enumerate(linha):
                if valor:
                    pagina.insert_text((x0 + (x1 - x0) * j / 6 + 6, y0 + (y1 - y0) * (i + 0.65) / len(celulas)),
                                       valor, fontsize=9, fontname='helv')
    return desenhar


def pagina_desenhada(path, desenhar, *, rotacao=0, degradacao=None):
    """A4 drawn by `desenhar`, rasterized at 200 dpi into an image-only PDF, degraded and turned."""
    import pymupdf
    from PIL import Image, ImageFilter
    origem = pymupdf.open()
    pagina = origem.new_page(width=595, height=842)
    desenhar(pagina)
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

    def _decidir(self, confianca, medida_original, medida_girada, *, motor_direto=True):
        pagina = type('Pagina', (), {'rotation': 0, 'set_rotation': lambda self, r: setattr(self, 'rotation', r)})()
        leituras = {'p.png': ('como esta', medida_original, 5), 'p_g180.png': ('girada', medida_girada, 5)}
        with patch('ocr._osd', return_value=(180, confianca)), patch('ocr._renderizar'), \
                patch('ocr._reconhecer_imagem', side_effect=lambda imagem, config: leituras[imagem.name][0]), \
                patch('ocr._ler_com_medida', side_effect=lambda imagem, config: leituras[imagem.name]):
            return ocr._orientar_pagina(pagina, Path('p.png'), {}, motor_direto=motor_direto)

    def test_leitura_dupla_so_gira_quando_a_girada_vence_pela_margem(self):
        # Literal measures, not the constants: a margin or minimum set to zero must fail here.
        texto, registro = self._decidir(5.0, 45.0, 55.0)
        self.assertEqual((texto, registro['decisao'], registro['giro_aplicado']), ('girada', 'leitura_dupla', 180))
        self.assertEqual((registro['original']['medida'], registro['girada']['medida']), (45.0, 55.0))
        # 9.9 points better is not enough (margin 10): symmetric digits read 94 upright and 86 turned.
        texto, registro = self._decidir(5.0, 80.0, 89.9)
        self.assertEqual((texto, registro['giro_aplicado']), ('como esta', 0))
        texto, registro = self._decidir(5.0, 1.0, 10.9)
        self.assertEqual((texto, registro['giro_aplicado']), ('como esta', 0))
        # A turned reading of junk never wins (an upright grid without text read 0 and 25.6; minimum 50).
        texto, registro = self._decidir(5.0, 0.0, 49.9)
        self.assertEqual((texto, registro['giro_aplicado']), ('como esta', 0))
        texto, registro = self._decidir(5.0, 30.0, 50.0)
        self.assertEqual((texto, registro['giro_aplicado']), ('girada', 180))
        self.assertEqual((ocr.MARGEM_LEITURA_DUPLA, ocr.MEDIDA_MINIMA_GIRADA), (10.0, 50.0))
        texto, registro = self._decidir(14.0, 0.0, 0.0)
        self.assertEqual((texto, registro['decisao'], registro['giro_aplicado']), ('girada', 'osd', 180))

    def test_no_motor_ocrmypdf_a_decisao_nao_devolve_a_leitura_direta(self):
        # OSD >= threshold and "keep as it is": None, OCRmyPDF reads the page; "turn": the direct reading,
        # used only if the turned copy for OCRmyPDF cannot be made.
        self.assertEqual(self._decidir(18.0, 0.0, 0.0, motor_direto=False)[0], None)
        texto, registro = self._decidir(5.0, 80.0, 85.0, motor_direto=False)
        self.assertEqual((texto, registro['decisao'], registro['giro_aplicado']), (None, 'leitura_dupla', 0))
        texto, registro = self._decidir(5.0, 30.0, 90.0, motor_direto=False)
        self.assertEqual((texto, registro['giro_aplicado']), ('girada', 180))

    def test_sem_tsv_a_pagina_fica_como_esta(self):
        texto, registro = self._decidir(5.0, None, None)
        self.assertEqual((texto, registro['giro_aplicado']), ('como esta', 0))
        self.assertIn('.tsv', registro['aviso'])

    def test_leitura_com_medida_pede_txt_e_tsv_sem_arquivo_de_configuracao(self):
        chamadas = []

        def falso(args, **kwargs):
            chamadas.append(list(args))
            Path(args[2] + '.txt').write_text('Texto lido.\n', encoding='utf-8')  # no .tsv
            return type('P', (), {'returncode': 0, 'stdout': b'', 'stderr': b''})()

        with tempfile.TemporaryDirectory() as pasta:
            config = {**ocr.configuracao(), 'tesseract': 'tesseract', 'tessdata': pasta}
            with patch('ocr._executar', side_effect=falso):
                self.assertEqual(ocr._ler_com_medida(Path(pasta) / 'p.png', config), ('Texto lido.', None, 0))
        argumentos = chamadas[0]
        # The `txt`/`tsv` config files live in tessdata/configs, absent from a folder of .traineddata only.
        self.assertNotIn('txt', argumentos)
        self.assertNotIn('tsv', argumentos)
        self.assertIn('tessedit_create_txt=1', argumentos)
        self.assertIn('tessedit_create_tsv=1', argumentos)

    def test_imagem_avulsa_avisa_quando_o_osd_sugere_giro(self):
        config = {**ocr.configuracao(), 'habilitado': True, 'tesseract': __file__, 'tessdata': None}
        for osd, duvida in (((180, 4.42), True), ((90, 20.5), False), ((0, 30.0), None)):
            with self.subTest(osd=osd), patch('ocr.configuracao', return_value=config), \
                    patch('ocr._idiomas_ausentes', return_value=[]), patch('ocr._osd', return_value=osd), \
                    patch('ocr._reconhecer_imagem', return_value='texto'), patch('ocr._versao_tesseract', return_value='5'):
                avisos = ocr.reconhecer_imagem(Path('imagem.png'))['avisos']
                if duvida is None:
                    self.assertEqual(avisos, [])
                    continue
                self.assertIn(f'parece girada {osd[0]} graus (OSD, confianca {osd[1]:g})', avisos[0])
                self.assertEqual('alarme falso' in avisos[0], duvida)


@unittest.skipUnless(HAS_FITZ, 'Requer PyMuPDF')
class MotorOcrmypdfSemOcrRealTest(unittest.TestCase):
    """Motor OCRmyPDF com o Tesseract e o OCRmyPDF simulados: cópia girada, recibo, avisos, temporários."""

    def setUp(self):
        import pymupdf
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.pasta = Path(pasta.name)
        self.pdf = self.pasta / 'tres.pdf'
        documento = pymupdf.open()
        for _ in range(3):
            documento.new_page(width=595, height=842)
        documento.save(self.pdf)
        self.config = {**ocr.configuracao(), 'tesseract': 'tesseract', 'tessdata': None, 'motor': 'ocrmypdf'}

    def motor(self, decisoes, *, copia_falha=False):
        """decisoes: {page: (direct text or None, record or None) or an exception}."""
        lidos = {}

        def decidir(pagina, numero, config, *, motor_direto):
            decisao = decisoes.get(numero, (None, None))
            if isinstance(decisao, Exception):
                raise decisao
            return decisao

        def sidecar(pdf, paginas, total, config):
            import pymupdf
            with pymupdf.open(str(pdf)) as documento:
                lidos.update(pdf=Path(pdf), paginas=list(paginas),
                             rotacoes={n: documento[n - 1].rotation for n in paginas})
            return {n: f'sidecar {n}' for n in paginas}

        falha = patch('ocr._copia_girada', side_effect=OSError('disco cheio')) if copia_falha else contextlib.nullcontext()
        with patch('ocr._pagina_orientada', side_effect=decidir), patch('ocr._sidecar_ocrmypdf', side_effect=sidecar), \
                patch('ocr._versao_tesseract', return_value='5.5.0'), patch('ocr._versoes',
                                                                          return_value={'tesseract': '5.5.0', 'ocrmypdf': '16'}), \
                falha:
            return ocr._motor_ocrmypdf(self.pdf, [1, 2, 3], 3, self.config), lidos

    def test_pagina_que_a_leitura_dupla_gira_vai_girada_para_o_ocrmypdf(self):
        girada = {'osd_giro': 180, 'osd_confianca': 4.0, 'decisao': 'leitura_dupla', 'giro_aplicado': 180}
        mantida = {'osd_giro': 180, 'osd_confianca': 2.0, 'decisao': 'leitura_dupla', 'giro_aplicado': 0}
        osd = {'osd_giro': 90, 'osd_confianca': 20.0, 'decisao': 'osd', 'giro_aplicado': 90}
        resultado, lidos = self.motor({1: (None, mantida), 2: ('direta 2', girada), 3: (None, osd)})
        self.assertEqual(lidos['paginas'], [1, 2, 3])
        self.assertNotEqual(lidos['pdf'], self.pdf)
        self.assertEqual(lidos['rotacoes'], {1: 0, 2: 180, 3: 0})  # only the turned page; OCRmyPDF turns page 3
        self.assertFalse(lidos['pdf'].exists())  # the temporary copy is gone
        import pymupdf
        with pymupdf.open(str(self.pdf)) as original:
            self.assertEqual([p.rotation for p in original], [0, 0, 0])
        paginas = resultado['paginas']
        self.assertEqual([paginas[n]['texto'] for n in (1, 2, 3)], ['sidecar 1', 'sidecar 2', 'sidecar 3'])
        self.assertEqual([paginas[n]['orientacao']['texto_de'] for n in (1, 2, 3)], ['ocrmypdf'] * 3)
        self.assertEqual(paginas[2]['orientacao']['giro_aplicado'], 180)
        self.assertEqual((resultado['paginas_giradas_antes'], resultado['paginas_tesseract_direto']), ([2], []))
        self.assertIn('pymupdf', resultado['versoes'])

    def test_sem_copia_girada_fica_a_leitura_direta_com_aviso(self):
        girada = {'osd_giro': 180, 'osd_confianca': 4.0, 'decisao': 'leitura_dupla', 'giro_aplicado': 180}
        resultado, lidos = self.motor({2: ('direta 2', girada)}, copia_falha=True)
        self.assertEqual(lidos['paginas'], [1, 3])
        self.assertEqual(lidos['pdf'], self.pdf)
        pagina = resultado['paginas'][2]
        self.assertEqual((pagina['texto'], pagina['orientacao']['texto_de']), ('direta 2', 'tesseract'))
        self.assertIn('disco cheio', pagina['aviso_orientacao'])
        self.assertEqual((resultado['paginas_giradas_antes'], resultado['paginas_tesseract_direto']), ([], [2]))
        self.assertIn('pymupdf', resultado['versoes'])
        self.assertTrue(any(a.startswith('pagina 2:') for a in resultado['avisos']))

    def test_conferencia_que_falha_deixa_aviso_na_pagina_e_no_lote(self):
        resultado, lidos = self.motor({2: ocr.OcrFalha('Tesseract excedeu 180s.')})
        self.assertEqual(lidos['paginas'], [1, 2, 3])
        self.assertEqual(resultado['paginas'][2]['texto'], 'sidecar 2')
        self.assertIn('excedeu 180s', resultado['paginas'][2]['aviso_orientacao'])
        self.assertEqual(len(resultado['avisos']), 1)
        self.assertNotIn('pymupdf', resultado['versoes'])

    def test_arquivos_temporarios_saem_ao_fim_de_cada_pagina(self):
        vistos = []

        def orientar(pagina, imagem, config, *, motor_direto):
            for anterior in vistos:
                self.assertFalse(anterior.exists(), anterior)  # the previous page's folder is already gone
            self.assertTrue(imagem.is_file())
            vistos.append(imagem.parent)
            return None, None

        for motor in ('ocrmypdf', 'tesseract'):
            vistos.clear()
            with self.subTest(motor=motor), patch('ocr._orientar_pagina', side_effect=orientar), \
                    patch('ocr._sidecar_ocrmypdf', return_value={1: 'a', 2: 'b', 3: 'c'}), \
                    patch('ocr._versoes', return_value={}):
                if motor == 'ocrmypdf':
                    ocr._motor_ocrmypdf(self.pdf, [1, 2, 3], 3, self.config)
                else:
                    ocr._motor_tesseract(self.pdf, [1, 2, 3], self.config)
            self.assertEqual(len(vistos), 3)
            self.assertFalse(vistos[-1].exists())


@unittest.skipUnless(HAS_FITZ and HAS_PYPDF, 'Requer PyMuPDF e pypdf')
class ReciboDoOcrTest(unittest.TestCase):
    """O recibo e o cabeçalho dizem quem leu cada página e trazem os avisos da conferência."""

    def extrair(self, reconhecido):
        import pymupdf
        from extrair_pdf import extrair_pdf
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        pdf = Path(pasta.name) / 'branco.pdf'
        documento = pymupdf.open()
        for _ in range(3):
            documento.new_page(width=595, height=842)
        documento.save(pdf)
        alvo = Path(pasta.name) / 'copia.md'
        with patch('extrair_pdf.ocr.diagnostico', return_value={'disponivel': True}), \
                patch('extrair_pdf.ocr.reconhecer', return_value=reconhecido):
            resultado = extrair_pdf(pdf, 'D001', alvo)
        return resultado, alvo.read_text(encoding='utf-8').split('## D001')[0]

    def test_metodo_orientacao_e_aviso_chegam_ao_recibo_e_ao_cabecalho(self):
        girada = {'osd_giro': 180, 'osd_confianca': 4.0, 'limiar': 14.0, 'decisao': 'leitura_dupla',
                  'giro_aplicado': 180, 'original': {'medida': 30.0, 'palavras': 9},
                  'girada': {'medida': 96.0, 'palavras': 9}}
        reconhecido = {
            'motor': 'ocrmypdf', 'idiomas': 'por+eng', 'avisos': ['pagina 3: Orientacao nao conferida: x'],
            'versoes': {'tesseract': '5.5.0', 'ocrmypdf': '16.10.4', 'ghostscript': '10', 'pymupdf': '1.26'},
            'paginas_giradas_antes': [1], 'paginas_tesseract_direto': [2],
            'paginas': {1: {'texto': 'Primeira pagina lida.', 'orientacao': {**girada, 'texto_de': 'ocrmypdf'}},
                        2: {'texto': 'Segunda pagina lida.', 'orientacao': {**girada, 'texto_de': 'tesseract'},
                            'aviso_orientacao': 'Copia girada nao criada'},
                        3: {'texto': 'Terceira pagina lida.', 'aviso_orientacao': 'Orientacao nao conferida: x'}}}
        resultado, cabecalho = self.extrair(reconhecido)
        self.assertIn('pymupdf 1.26', resultado['metodo'])
        self.assertIn('paginas 1 giradas pelo PyMuPDF numa copia temporaria antes do OCRmyPDF', resultado['metodo'])
        self.assertIn('paginas 2 lidas pelo Tesseract direto', resultado['metodo'])
        self.assertIn(f'Metodo: {resultado["metodo"]}', cabecalho)
        self.assertIn('1=girada 180 graus (OSD sugeriu 180 com confianca 4.0; leitura dupla, confianca media '
                      'das palavras 30.0 como esta e 96.0 girada; texto de ocrmypdf)', cabecalho)
        self.assertIn('; texto de tesseract)', cabecalho)
        self.assertEqual(resultado['ocr_avisos_orientacao'],
                         {'2': 'Copia girada nao criada', '3': 'Orientacao nao conferida: x'})
        self.assertIn('Aviso do OCR por pagina: 2=Copia girada nao criada; 3=Orientacao nao conferida: x', cabecalho)
        self.assertEqual(resultado['ocr_motor']['avisos'], ['pagina 3: Orientacao nao conferida: x'])

    def test_sem_medida_o_cabecalho_diz_por_que(self):
        sem = {'osd_giro': 180, 'osd_confianca': 4.0, 'decisao': 'leitura_dupla', 'giro_aplicado': 0,
               'original': {'medida': None, 'palavras': 0}, 'girada': {'medida': None, 'palavras': 0},
               'texto_de': 'tesseract'}
        reconhecido = {'motor': 'tesseract', 'idiomas': 'por', 'avisos': [], 'versoes': {'tesseract': '5'},
                       'paginas': {n: {'texto': f'Pagina {n} lida.', 'orientacao': sem} for n in (1, 2, 3)}}
        _, cabecalho = self.extrair(reconhecido)
        self.assertIn('1=como esta (OSD sugeriu 180 com confianca 4.0; leitura dupla, sem medida '
                      '(Tesseract nao gerou o .tsv); texto de tesseract)', cabecalho)


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
                # Who read the page: OCRmyPDF on a copy turned by PyMuPDF, or Tesseract on the PyMuPDF render.
                self.assertIn(f'texto de {motor})', cabecalho)
                self.assertIn('pymupdf', resultado['ocr_motor']['versoes'])
                if motor == 'ocrmypdf':
                    self.assertIn('paginas 1 giradas pelo PyMuPDF numa copia temporaria antes do OCRmyPDF',
                                  resultado['metodo'])

    def test_tabela_em_courier_girada_e_lida_inteira_pelo_motor_ocrmypdf(self):
        # Typed ledger scanned sideways. OSD measures 13.7 to 14.7 on these pages, both sides of the
        # threshold. The direct reading (PyMuPDF render + Tesseract) tears these values apart even
        # upright (0 of 40 whole); OCRmyPDF reads all 40, so the OCRmyPDF engine has to read the page
        # itself, turned. In the direct engine only the turn is checked: its torn values are the
        # alternative engine's known defect (Onda 1: render at the image's own resolution).
        valores = valores_da_tabela(8, 5)
        texto = '\n'.join('  '.join(f'{v:>11}' for v in linha) for linha in valores)
        esperados = {v for linha in valores for v in linha}
        for rotacao in (90, 180, 270):
            pdf = pagina_digitalizada(self.pasta / f'courier{rotacao}.pdf', texto, fonte=9, rotacao=rotacao,
                                      margem=50, nome_fonte='cour')
            for motor in self.MOTORES:
                with self.subTest(motor=motor, rotacao=rotacao):
                    pagina = self.reconhecer(motor, pdf)
                    orientacao = pagina.get('orientacao', {})
                    self.assertEqual(orientacao.get('giro_aplicado'), rotacao, orientacao)
                    if motor == 'ocrmypdf':
                        lidos = set(re.findall(r'\d{1,3}\.\d{3},\d{2}', pagina.get('texto', '')))
                        self.assertGreaterEqual(len(lidos & esperados), 36, orientacao)
                        self.assertEqual(orientacao['texto_de'], 'ocrmypdf')

    def test_grade_de_numeros_reta_e_borrada_fica_reta(self):
        # OSD asks for 180 on these upright grids with confidence below 2; the double reading keeps
        # them upright. OCRmyPDF reads every number; the direct reading reads almost none (Onda 1).
        for semente in (2, 3):
            celulas = grade_de_numeros(semente)
            esperados = {v for linha in celulas for v in linha if v}
            pdf = pagina_desenhada(self.pasta / f'grade{semente}.pdf', desenhar_grade(celulas), degradacao='borrada')
            for motor in self.MOTORES:
                with self.subTest(motor=motor, semente=semente):
                    pagina = self.reconhecer(motor, pdf)
                    orientacao = pagina.get('orientacao', {})
                    self.assertEqual(orientacao.get('giro_aplicado', 0), 0, orientacao)
                    if motor == 'ocrmypdf':
                        lidos = set(re.findall(r'\d+', pagina.get('texto', '')))
                        self.assertGreaterEqual(len(lidos & esperados), int(len(esperados) * 0.9), orientacao)
                        if orientacao:
                            self.assertEqual(orientacao['texto_de'], 'ocrmypdf')

    def test_pdf_de_varias_paginas_com_uma_girada_no_meio(self):
        import pymupdf
        partes = [pagina_digitalizada(self.pasta / 'm1.pdf', PROSA * 6),
                  pagina_digitalizada(self.pasta / 'm2.pdf', LINHAS[0], rotacao=180),
                  pagina_digitalizada(self.pasta / 'm3.pdf', PROSA * 6, rotacao=180),
                  pagina_digitalizada(self.pasta / 'm4.pdf', '\n'.join(LINHAS))]
        pdf = self.pasta / 'varias.pdf'
        documento = pymupdf.open()
        for parte in partes:
            with pymupdf.open(str(parte)) as origem:
                documento.insert_pdf(origem)
        documento.save(pdf)
        chamadas, original = [], ocr._sidecar_ocrmypdf

        def espiao(fonte, paginas, total, config):
            chamadas.append(list(paginas))
            return original(fonte, paginas, total, config)

        for motor in self.MOTORES:
            for pedidas in ([1, 2, 3, 4], [2, 3]):
                chamadas.clear()
                with self.subTest(motor=motor, pedidas=pedidas), \
                        patch.dict(os.environ, {'VLADO_OCR_MOTOR': motor, 'VLADO_OCR': '1'}), \
                        patch('ocr._sidecar_ocrmypdf', side_effect=espiao):
                    resultado = ocr.reconhecer(pdf, pedidas)
                    self.assertEqual(sorted(resultado['paginas']), pedidas)
                    for numero in pedidas:  # each page keeps its own text, in its own position
                        pagina = resultado['paginas'][numero]
                        self.assertIn('fiscaliza', pagina.get('texto', '').lower(), (numero, pagina.get('orientacao')))
                        esperado = 180 if numero in (2, 3) else 0
                        self.assertEqual(pagina.get('orientacao', {}).get('giro_aplicado', 0), esperado, numero)
                    self.assertEqual(resultado['paginas'][2]['orientacao']['decisao'], 'leitura_dupla')
                    if motor == 'ocrmypdf':
                        self.assertEqual(chamadas, [pedidas])  # one OCRmyPDF run, --pages as asked
                        self.assertEqual(resultado['paginas_giradas_antes'], [2])
                        self.assertEqual(resultado['paginas_tesseract_direto'], [])

    def test_tessdata_so_com_os_arquivos_de_idioma(self):
        # What docs/CADASTRO_DOCUMENTOS.md tells a notebook user to set up: no tessdata/configs folder.
        config = ocr.configuracao()
        origem = config.get('tessdata')
        if not origem:
            saida = subprocess.run([config['tesseract'], '--list-langs'], capture_output=True, text=True)
            origem = re.search(r'"([^"]+)"', saida.stdout + saida.stderr)[1]
        pasta = self.pasta / 'tessdata'
        pasta.mkdir()
        for idioma in ('por', 'eng', 'osd'):
            shutil.copy2(Path(origem) / f'{idioma}.traineddata', pasta)
        pdf = pagina_digitalizada(self.pasta / 'curta.pdf', LINHAS[0], rotacao=180)
        ambiente = {k: v for k, v in os.environ.items() if k != 'TESSDATA_PREFIX'}
        # The OCRmyPDF engine itself needs tessdata/configs (hocr); "auto" falls back to the direct engine.
        for motor in ('tesseract', 'auto'):
            with self.subTest(motor=motor), patch.dict(os.environ, {**ambiente, 'VLADO_TESSDATA': str(pasta),
                                                                     'VLADO_OCR_MOTOR': motor, 'VLADO_OCR': '1'}, clear=True):
                pagina = ocr.reconhecer(pdf, [1])['paginas'][1]
                self.assertNotIn('erro', pagina)
                self.assertIn('fiscaliza', pagina.get('texto', '').lower())
                orientacao = pagina['orientacao']
                self.assertEqual((orientacao['decisao'], orientacao['giro_aplicado']), ('leitura_dupla', 180))
                self.assertIsNotNone(orientacao['girada']['medida'])

    def test_imagem_avulsa_girada_recebe_aviso(self):
        from PIL import Image
        import pymupdf
        origem = pymupdf.open()
        pagina = origem.new_page(width=595, height=842)
        pagina.insert_textbox(pymupdf.Rect(60, 60, 535, 782), '\n'.join(LINHAS[:3]), fontsize=11, fontname='helv')
        imagem = Image.open(io.BytesIO(pagina.get_pixmap(dpi=200).tobytes('png'))).convert('L').rotate(180, expand=True)
        caminho = self.pasta / 'avulsa.png'
        imagem.save(caminho)
        with patch.dict(os.environ, {'VLADO_OCR': '1'}):
            avisos = ocr.reconhecer_imagem(caminho)['avisos']
        self.assertTrue(avisos and 'parece girada' in avisos[0] and 'confianca' in avisos[0], avisos)


if __name__ == '__main__':
    unittest.main()
