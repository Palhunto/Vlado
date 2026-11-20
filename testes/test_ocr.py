"""OCR local de PDFs digitalizados: configuracao, motores, cadastro, indice e reprocessamento.

Os PDFs sao gerados em diretorios temporarios; nenhum binario e versionado.
Testes que exigem Tesseract/PyMuPDF sao ignorados quando ausentes.
"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import cadastrar_documentos as cadastro
import ocr
from comum import ler_json, sha256
from extrair_pdf import extrair_pdf
from indice_sqlite import cobertura, ler_passagem, pesquisar
from nova_rodada import criar_rodada
from selecionar_caso import selecionar
import test_registros as fixtures
from test_extracao_cadastro_pdf import pdf_sintetico

HAS_FITZ = importlib.util.find_spec('pymupdf') is not None
HAS_PYPDF = importlib.util.find_spec('pypdf') is not None
HAS_TESSERACT = HAS_FITZ and ocr.diagnostico()['tesseract']['disponivel']
FRASE = 'Relatório da fiscalização sobre a licitação número 42.'
FRASE_2 = 'Contrato firmado em São Paulo pela prefeitura.'
PRECISA_OCR = unittest.skipUnless(HAS_TESSERACT and HAS_PYPDF, 'Requer Tesseract, PyMuPDF e pypdf')


def _imagem_da_pagina(texto, rotacao=0):
    """Rasteriza um texto (sem camada textual) e devolve PNG, para simular digitalizacao."""
    import pymupdf
    from PIL import Image
    import io
    origem = pymupdf.open()
    pagina = origem.new_page(width=480, height=320)
    pagina.insert_textbox(pymupdf.Rect(20, 20, 460, 300), texto, fontsize=20, fontname='helv')
    png = pagina.get_pixmap(dpi=200).tobytes('png')
    if rotacao:
        imagem = Image.open(io.BytesIO(png)).rotate(rotacao, expand=True)
        buffer = io.BytesIO()
        imagem.save(buffer, 'PNG')
        png = buffer.getvalue()
    return png


def pdf_digitalizado(path, paginas, *, rotacoes=None, rotate_pdf=None, nativas=None):
    """Cria PDF so com imagens (paginas digitalizadas); `nativas` mapeia pagina->texto nativo."""
    import pymupdf
    documento = pymupdf.open()
    for indice, texto in enumerate(paginas, 1):
        if nativas and indice in nativas:
            pagina = documento.new_page(width=480, height=320)
            pagina.insert_textbox(pymupdf.Rect(20, 20, 460, 300), nativas[indice], fontsize=14, fontname='helv')
            continue
        rotacao = (rotacoes or {}).get(indice, 0)
        png = _imagem_da_pagina(texto, rotacao)
        largura, altura = (320, 480) if rotacao in (90, 270) else (480, 320)
        pagina = documento.new_page(width=largura, height=altura)
        pagina.insert_image(pagina.rect, stream=png)
        if rotate_pdf and indice in rotate_pdf:
            pagina.set_rotation(rotate_pdf[indice])
    documento.save(path)
    documento.close()
    return Path(path)


class ConfiguracaoOcrTest(unittest.TestCase):
    def test_padroes_e_variaveis_de_ambiente(self):
        with patch.dict(os.environ, {'VLADO_OCR_IDIOMAS': 'eng', 'VLADO_TESSERACT': 'C:/x/tesseract.exe',
                                     'VLADO_TESSDATA': 'C:/x/tessdata', 'VLADO_OCR': '1'}):
            config = ocr.configuracao()
        self.assertEqual((config['idiomas'], config['tesseract'], config['tessdata'], config['habilitado']),
                         ('eng', 'C:/x/tesseract.exe', 'C:/x/tessdata', True))
        env = {k: v for k, v in os.environ.items() if not k.startswith('VLADO_OCR')}
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(ocr.configuracao()['idiomas'], 'por+eng')

    def test_vlado_ocr_zero_desabilita(self):
        for valor in ('0', 'false', 'nao'):
            with patch.dict(os.environ, {'VLADO_OCR': valor}):
                self.assertFalse(ocr.configuracao()['habilitado'])
                self.assertFalse(ocr.diagnostico()['disponivel'])
                with self.assertRaises(ocr.OcrIndisponivel):
                    ocr.reconhecer(Path('qualquer.pdf'), [1])

    def test_idiomas_invalidos_sao_recusados(self):
        with patch.dict(os.environ, {'VLADO_OCR_IDIOMAS': 'por+eng; calc'}):
            with self.assertRaises(ValueError):
                ocr.configuracao()

    def test_subprocessos_sem_janela_com_timeout_e_saida_capturada(self):
        capturado = {}

        def falso(args, **kwargs):
            capturado.update(kwargs)
            return subprocess.CompletedProcess(args, 0, b'ok', b'')
        with patch('ocr.subprocess.run', side_effect=falso):
            ocr._executar(['x'], timeout=7)
        self.assertEqual(capturado['timeout'], 7)
        self.assertTrue(capturado['capture_output'])
        if os.name == 'nt':
            self.assertEqual(capturado['creationflags'], subprocess.CREATE_NO_WINDOW)

    def test_sidecar_do_ocrmypdf_mapeia_paginas_e_marcadores_de_salto(self):
        texto = 'primeira\f[OCR skipped on page(s) 2-3]\fquarta\f\fsexta'
        paginas = ocr._paginas_do_sidecar(texto, 6)
        self.assertEqual(paginas, {1: 'primeira', 4: 'quarta', 5: '', 6: 'sexta'})

    def test_motor_ocrmypdf_usa_opcoes_locais_e_le_sidecar(self):
        chamadas = []

        def falso(args, **kwargs):
            chamadas.append((list(args), kwargs))
            lado = Path(args[args.index('--sidecar') + 1])
            lado.write_text('[OCR skipped on page(s) 1]\fTexto reconhecido.', encoding='utf-8')
            return subprocess.CompletedProcess(args, 0, b'', b'')
        with tempfile.TemporaryDirectory() as pasta:
            pdf = Path(pasta) / 'a.pdf'
            pdf.write_bytes(b'%PDF-1.4')
            config = {**ocr.configuracao(), 'tesseract': 'C:/t/tesseract.exe', 'tessdata': 'C:/t/data',
                      'idiomas': 'por+eng', 'habilitado': True, 'motor': 'auto'}
            with patch('ocr._executar', side_effect=falso), \
                    patch('ocr._versoes', return_value={'ocrmypdf': '16.10.4'}):
                resultado = ocr._motor_ocrmypdf(pdf, [2], 2, config)
        argumentos, kwargs = chamadas[0]
        self.assertIn('--rotate-pages', argumentos)
        self.assertEqual(argumentos[argumentos.index('-l') + 1], 'por+eng')
        self.assertEqual(argumentos[argumentos.index('--pages') + 1], '2')
        self.assertEqual(kwargs['env']['TESSDATA_PREFIX'], 'C:/t/data')
        self.assertEqual(resultado['paginas'][2]['texto'], 'Texto reconhecido.')
        self.assertEqual(resultado['motor'], 'ocrmypdf')

    def test_ocrmypdf_falho_cai_para_tesseract_direto(self):
        configuracao = {**ocr.configuracao(), 'habilitado': True, 'motor': 'auto'}
        with patch('ocr.configuracao', return_value=configuracao), \
                patch('ocr._ocrmypdf_disponivel', return_value=True), \
                patch('ocr._tesseract_disponivel', return_value=True), \
                patch('ocr._motor_ocrmypdf', side_effect=ocr.OcrFalha('gs ausente')), \
                patch('ocr._motor_tesseract', return_value={'motor': 'tesseract', 'versoes': {}, 'idiomas': 'por+eng',
                                                            'paginas': {1: {'texto': 'ok'}}, 'avisos': []}):
            resultado = ocr.reconhecer(Path('x.pdf'), [1])
        self.assertEqual(resultado['motor'], 'tesseract')
        self.assertTrue(any('gs ausente' in aviso for aviso in resultado['avisos']))


class OcrCadastroBase(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.RegistrosTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        selecionar(self.root, None)

    def cadastrar(self, fontes):
        return cadastro.cadastrar(self.root, 'alpha', fontes, novo=True, titulo='OCR sintetico', natureza='sinteticos')

    def manifesto(self):
        return ler_json(self.root / 'casos/alpha/manifesto.json')

    def indexar(self, rodada='R001'):
        selecionar(self.root, 'alpha')
        return criar_rodada(self.root, rodada, 'Pergunta sintetica de localizacao.', indice=True)


@PRECISA_OCR
class OcrCadastroTest(OcrCadastroBase):
    def test_pdf_totalmente_digitalizado_vira_texto_pesquisavel_com_pagina_fisica(self):
        pdf = pdf_digitalizado(self.root / 'scan.pdf', [FRASE, FRASE_2])
        antes = sha256(pdf)
        recibo = self.cadastrar([pdf])
        info = recibo['arquivos'][0]['extracao_pdf']
        self.assertEqual(info['paginas_ocr'], [1, 2])
        self.assertEqual(info['paginas_texto_nativo'], [])
        self.assertEqual(info['paginas_sem_texto'], [])
        self.assertEqual(info['estado'], 'extraido')
        self.assertTrue(info['ocr'])
        self.assertIn(info['ocr_motor']['motor'], ('ocrmypdf', 'tesseract'))
        self.assertTrue(info['ocr_motor']['versoes'])
        self.assertEqual(info['ocr_motor']['idiomas'], 'por+eng')
        resumo = recibo['extracao_pdf_resumo']
        self.assertEqual((resumo['paginas_ocr'], resumo['paginas_texto_nativo'], resumo['paginas_sem_texto'],
                          resumo['paginas_com_erro']), (2, 0, 0, 0))
        doc = self.manifesto()['documentos'][0]
        self.assertEqual(doc['sha256'], antes)
        self.assertEqual(sha256(self.root / doc['arquivo']), antes)
        derivado = doc['derivados'][0]
        self.assertEqual(sha256(self.root / derivado['arquivo']), derivado['sha256'])
        self.assertEqual(derivado['origem_sha256'], antes)
        self.assertEqual(derivado['paginas_origem'], {'1': 'ocr', '2': 'ocr'})
        corpo = (self.root / derivado['arquivo']).read_text(encoding='utf-8')
        self.assertIn('ocr', corpo.split('## D001 - pagina PDF 1')[0])
        run = self.indexar()
        resposta = pesquisar(self.root, 'alpha', 'R001', 'licitacao')
        self.assertEqual(resposta['retornados'], 1)
        hit = resposta['resultados'][0]
        self.assertEqual(hit['pagina_pdf'], 1)
        self.assertEqual(sha256(run / hit['original']), antes)
        contexto = json.dumps(ler_passagem(self.root, 'alpha', 'R001', hit['referencia']), ensure_ascii=False)
        self.assertIn('fiscaliza', contexto)
        segunda = pesquisar(self.root, 'alpha', 'R001', 'prefeitura')['resultados'][0]
        self.assertEqual(segunda['pagina_pdf'], 2)

    def test_pdf_misto_usa_texto_nativo_e_ocr_somente_onde_falta(self):
        pdf = pdf_digitalizado(self.root / 'misto.pdf', ['', FRASE], nativas={1: 'Marcador nativo exclusivo da primeira pagina.'})
        recibo = self.cadastrar([pdf])
        info = recibo['arquivos'][0]['extracao_pdf']
        self.assertEqual((info['paginas_texto_nativo'], info['paginas_ocr'], info['paginas_sem_texto']), ([1], [2], []))
        self.assertEqual(info['paginas_com_texto'], 2)
        derivado = self.manifesto()['documentos'][0]['derivados'][0]
        self.assertEqual(derivado['paginas_origem'], {'1': 'texto_nativo', '2': 'ocr'})
        self.indexar()
        self.assertEqual(pesquisar(self.root, 'alpha', 'R001', 'nativo')['resultados'][0]['pagina_pdf'], 1)
        self.assertEqual(pesquisar(self.root, 'alpha', 'R001', 'licitacao')['resultados'][0]['pagina_pdf'], 2)

    def test_pagina_digitalizada_girada_e_reconhecida(self):
        for rotacao in (90, 180):
            with self.subTest(rotacao=rotacao):
                destino = self.root / f'rot{rotacao}.pdf'
                pdf_digitalizado(destino, [FRASE], rotacoes={1: rotacao})
                alvo = self.root / f'texto{rotacao}.md'
                resultado = extrair_pdf(destino, 'D001', alvo)
                self.assertEqual(resultado['paginas_ocr'], [1], resultado)
                texto = alvo.read_text(encoding='utf-8').lower()
                self.assertIn('licita', texto)
                self.assertIn('fiscaliza', texto)

    def test_pagina_com_rotate_do_pdf_e_reconhecida(self):
        destino = self.root / 'rotate.pdf'
        pdf_digitalizado(destino, [FRASE], rotate_pdf={1: 90})
        resultado = extrair_pdf(destino, 'D001', self.root / 'rotate.md')
        self.assertEqual(resultado['paginas_ocr'], [1], resultado)

    def test_ocr_desabilitado_mantem_comportamento_anterior(self):
        pdf = pdf_digitalizado(self.root / 'scan.pdf', [FRASE])
        with patch.dict(os.environ, {'VLADO_OCR': '0'}):
            recibo = self.cadastrar([pdf])
        info = recibo['arquivos'][0]['extracao_pdf']
        self.assertEqual((info['estado'], info['paginas_sem_texto'], info['paginas_ocr']), ('sem_texto', [1], []))
        self.assertFalse(info['ocr'])
        self.assertFalse(info['ocr_tentado'])

    def test_preparar_pdfs_reprocessa_em_nova_versao_sem_tocar_rodadas_antigas(self):
        pdf = pdf_digitalizado(self.root / 'scan.pdf', [FRASE])
        with patch.dict(os.environ, {'VLADO_OCR': '0'}):
            self.cadastrar([pdf])
        antes = self.manifesto()['documentos'][0]
        antigo = self.indexar('R001')
        self.assertEqual(pesquisar(self.root, 'alpha', 'R001', 'licitacao')['retornados'], 0)
        hashes = {p.relative_to(antigo): sha256(p) for p in antigo.rglob('*') if p.is_file()}
        resultado = cadastro.preparar_pdfs(self.root, 'alpha')
        self.assertEqual(resultado['corpus_id'], 'alpha_v2')
        self.assertEqual(resultado['extracao_pdf_resumo']['paginas_ocr'], 1)
        doc = self.manifesto()['documentos'][0]
        self.assertEqual((doc['id'], doc['arquivo'], doc['sha256']), (antes['id'], antes['arquivo'], antes['sha256']))
        self.assertEqual(len(doc['derivados']), 1)
        self.assertNotEqual(doc['derivados'][0]['arquivo'], antes['derivados'][0]['arquivo'] if antes['derivados'] else None)
        self.assertEqual(hashes, {p.relative_to(antigo): sha256(p) for p in antigo.rglob('*') if p.is_file()})
        criar_rodada(self.root, 'R002', 'Pergunta sintetica posterior.', indice=True)
        self.assertEqual(pesquisar(self.root, 'alpha', 'R002', 'licitacao')['retornados'], 1)
        # Segunda preparacao nao repete OCR concluido.
        with patch('extrair_pdf.ocr.reconhecer', side_effect=AssertionError('OCR repetido')):
            cadastro.preparar_pdfs(self.root, 'alpha')
        self.assertEqual(self.manifesto()['corpus_id'], 'alpha_v2')

    def test_falha_de_ocr_em_pagina_fica_no_recibo_com_numero(self):
        pdf = pdf_digitalizado(self.root / 'scan.pdf', [FRASE, FRASE_2])
        real = ocr.reconhecer

        def parcial(origem, paginas, **kwargs):
            resultado = real(origem, [paginas[0]], **kwargs)
            resultado['paginas'][paginas[1]] = {'erro': 'falha sintetica'}
            return resultado
        with patch('extrair_pdf.ocr.reconhecer', side_effect=parcial):
            recibo = self.cadastrar([pdf])
        info = recibo['arquivos'][0]['extracao_pdf']
        self.assertEqual(info['paginas_ocr'], [1])
        self.assertEqual([(p['pagina_pdf'], p['etapa']) for p in info['paginas_com_erro']], [(2, 'ocr')])
        self.assertEqual(info['estado'], 'parcial')
        self.assertEqual(recibo['extracao_pdf_resumo']['paginas_com_erro'], 1)


@unittest.skipUnless(HAS_PYPDF, 'Requer pypdf')
class OcrSemMotorTest(OcrCadastroBase):
    def test_pdf_protegido_nao_quebra_preserva_original_e_aparece_no_recibo(self):
        pdf = pdf_sintetico(self.root / 'senha.pdf', ['Texto protegido.'], password='sintetica')
        antes = sha256(pdf)
        recibo = self.cadastrar([pdf])
        info = recibo['arquivos'][0]['extracao_pdf']
        self.assertEqual(info['estado'], 'erro')
        self.assertTrue(info['protegido'])
        self.assertEqual(recibo['extracao_pdf_resumo']['protegidos'], 1)
        doc = self.manifesto()['documentos'][0]
        self.assertEqual(sha256(self.root / doc['arquivo']), antes)
        self.assertEqual(doc['derivados'], [])

    def test_motor_indisponivel_registra_limitacao_sem_falhar(self):
        pdf = pdf_sintetico(self.root / 'vazio.pdf', [None])
        with patch('extrair_pdf.ocr.diagnostico', return_value={'disponivel': False, 'motivo': 'sem motor'}):
            recibo = self.cadastrar([pdf])
        info = recibo['arquivos'][0]['extracao_pdf']
        self.assertEqual((info['estado'], info['paginas_sem_texto'], info['ocr_tentado']), ('sem_texto', [1], False))
        self.assertEqual(info['ocr_indisponivel'], 'sem motor')

    def test_texto_nativo_nao_aciona_ocr(self):
        pdf = pdf_sintetico(self.root / 'nativo.pdf', ['Texto nativo suficiente para dispensar reconhecimento.'])
        with patch('extrair_pdf.ocr.reconhecer', side_effect=AssertionError('OCR desnecessario')):
            recibo = self.cadastrar([pdf])
        info = recibo['arquivos'][0]['extracao_pdf']
        self.assertEqual((info['paginas_texto_nativo'], info['paginas_ocr']), ([1], []))


if __name__ == '__main__':
    unittest.main()
