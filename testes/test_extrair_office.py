"""DOCX/XLSX extraction with locators; packages are built inside the tests with zipfile."""
from pathlib import Path
import sys
import json
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import extrair_office
from extrair_office import extrair_office as extrair, ler_docx, ler_xlsx, referencia_celula

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
S = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PR = 'http://schemas.openxmlformats.org/package/2006/relationships'
REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'


def _p(text):
    return f'<w:p><w:r><w:t xml:space="preserve">{text}</w:t></w:r></w:p>'


def _zip(path: Path, parts: dict):
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as package:
        for name, content in parts.items():
            package.writestr(name, content)
    return path


def docx(path: Path, body: str, extra: dict | None = None, rels: str = ''):
    parts = {
        '[Content_Types].xml': '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        'word/document.xml': f'<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="{W}" xmlns:r="{R}"><w:body>{body}</w:body></w:document>',
        'word/_rels/document.xml.rels': f'<?xml version="1.0"?><Relationships xmlns="{PR}">{rels}</Relationships>',
    }
    parts.update(extra or {})
    return _zip(path, parts)


def xlsx(path: Path, sheets: list, shared=(), styles: str | None = None, extra: dict | None = None):
    """sheets = [(name, sheetData xml, state)]."""
    sheet_entries = ''.join(
        f'<sheet name="{name}" sheetId="{i}" r:id="rId{i}"{f" state=\"{state}\"" if state else ""}/>'
        for i, (name, _, state) in enumerate(sheets, 1))
    rels = ''.join(f'<Relationship Id="rId{i}" Type="{REL}/worksheet" Target="worksheets/sheet{i}.xml"/>'
                   for i in range(1, len(sheets) + 1))
    parts = {
        '[Content_Types].xml': '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        'xl/workbook.xml': f'<?xml version="1.0"?><workbook xmlns="{S}" xmlns:r="{R}"><sheets>{sheet_entries}</sheets></workbook>',
        'xl/_rels/workbook.xml.rels': f'<?xml version="1.0"?><Relationships xmlns="{PR}">{rels}</Relationships>',
    }
    for i, (_, data, _) in enumerate(sheets, 1):
        parts[f'xl/worksheets/sheet{i}.xml'] = f'<?xml version="1.0"?><worksheet xmlns="{S}"><sheetData>{data}</sheetData></worksheet>'
    if shared:
        items = ''.join(f'<si><t>{t}</t></si>' for t in shared)
        parts['xl/sharedStrings.xml'] = f'<?xml version="1.0"?><sst xmlns="{S}">{items}</sst>'
    if styles:
        parts['xl/styles.xml'] = f'<?xml version="1.0"?><styleSheet xmlns="{S}">{styles}</styleSheet>'
    parts.update(extra or {})
    return _zip(path, parts)


class ExtrairOfficeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_docx_paragrafos_tabela_cabecalho_e_notas_em_ordem(self):
        table = ('<w:tbl><w:tr><w:tc>' + _p('Contrato') + '</w:tc><w:tc>' + _p('Valor') + '</w:tc></w:tr>'
                 '<w:tr><w:tc><w:tcPr><w:gridSpan w:val="2"/></w:tcPr>' + _p('Linha unica') + '</w:tc></w:tr>'
                 '<w:tr><w:tc>' + _p('Obra A') + '</w:tc><w:tc>' + _p('R$ 10') + _p('pago') + '</w:tc></w:tr></w:tbl>')
        body = (_p('Primeiro paragrafo.') + '<w:p/>' + table
                + '<w:p><w:r><w:t>Com nota</w:t></w:r><w:r><w:footnoteReference w:id="1"/></w:r>'
                  '<w:del><w:r><w:delText>apagado</w:delText></w:r></w:del></w:p>')
        extra = {
            'word/header1.xml': f'<w:hdr xmlns:w="{W}">{_p("Cabecalho oficial")}</w:hdr>',
            'word/footnotes.xml': (f'<w:footnotes xmlns:w="{W}"><w:footnote w:type="separator" w:id="-1">{_p("---")}</w:footnote>'
                                   f'<w:footnote w:id="1">{_p("Fonte da nota")}</w:footnote></w:footnotes>'),
        }
        rels = f'<Relationship Id="rId9" Type="{REL}/header" Target="header1.xml"/>'
        source = docx(self.dir / 'relatorio.docx', body, extra, rels)
        target = self.dir / 'D001_texto_docx.md'
        result = extrair(source, 'D001', target)
        self.assertEqual(result['estado'], 'extraido')
        self.assertEqual(result['origem'], 'extracao_docx')
        self.assertEqual(result['versao_extrator'], extrair_office.VERSAO_EXTRATOR)
        counts = result['contagens']
        self.assertEqual((counts['paragrafos'], counts['tabelas'], counts['celulas_tabela']), (2, 1, 5))
        self.assertEqual((counts['cabecalhos'], counts['notas_rodape']), (1, 1))
        self.assertTrue(any('controle de alterações' in a for a in result['avisos']))
        text = target.read_text(encoding='utf-8')
        lines = [line for line in text.splitlines() if line.startswith('[')]
        self.assertEqual(lines[:6], [
            '[P0001] Primeiro paragrafo.', '[T01 L01 C01] Contrato', '[T01 L01 C02] Valor',
            '[T01 L02 C01] Linha unica', '[T01 L03 C01] Obra A', '[T01 L03 C02] R$ 10 ¶ pago'])
        self.assertIn('[P0002] Com nota[nota 1]', lines)
        self.assertNotIn('apagado', text)
        self.assertIn('## D001 - cabecalho 1', text)
        self.assertIn('[CAB1 P0001] Cabecalho oficial', lines)
        self.assertIn('[NOTA 1 P0001] Fonte da nota', lines)
        self.assertNotIn('---', ''.join(lines))
        self.assertIn('SHA-256 do original: ', text)
        self.assertIn('Origem: extracao_docx', text)

    def test_xlsx_celulas_formulas_e_valor_exibido(self):
        styles = ('<numFmts count="1"><numFmt numFmtId="164" formatCode="#,##0.00"/></numFmts>'
                  '<cellXfs count="3"><xf numFmtId="0"/><xf numFmtId="164"/><xf numFmtId="14"/></cellXfs>')
        data1 = ('<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>'
                 '<row r="2"><c r="A2" t="s"><v>2</v></c><c r="B2" s="1"><v>1234.5</v></c><c r="C2" s="2"><v>45292</v></c></row>'
                 '<row r="3"><c r="A3" t="inlineStr"><is><t>Total</t></is></c><c r="B3" s="1"><f>SUM(B2:B2)</f><v>1234.5</v></c>'
                 '<c r="D3" s="1"/></row>')
        data2 = '<row r="1"><c r="A1" t="b"><v>1</v></c><c r="B1"><f>A1*2</f></c></row>'
        source = xlsx(self.dir / 'gastos.xlsx', [('Gastos', data1, None), ('Minha aba', data2, 'hidden')],
                      shared=('Item', 'Valor', 'Obra A'), styles=styles)
        target = self.dir / 'D002_texto_xlsx.md'
        result = extrair(source, 'D002', target)
        self.assertEqual(result['estado'], 'extraido')
        self.assertEqual(result['origem'], 'extracao_xlsx')
        self.assertEqual(result['contagens'], {'abas': 2, 'celulas': 9, 'formulas': 2})
        self.assertEqual([(a['nome'], a['celulas'], a['formulas'], a['oculta']) for a in result['abas']],
                         [('Gastos', 7, 1, False), ('Minha aba', 2, 1, True)])
        lines = target.read_text(encoding='utf-8').splitlines()
        self.assertIn('[Gastos!A1] Item', lines)
        self.assertIn('[Gastos!B2] 1234.5 || exibido: 1,234.50', lines)
        self.assertIn('[Gastos!C2] 45292 || exibido: 2024-01-01', lines)
        self.assertIn('[Gastos!B3] 1234.5 || exibido: 1,234.50 || formula: =SUM(B2:B2)', lines)
        self.assertFalse(any(line.startswith('[Gastos!D3]') for line in lines), 'célula só com estilo não é preenchida')
        self.assertIn("['Minha aba'!A1] TRUE", lines)
        self.assertIn("['Minha aba'!B1] (sem valor gravado) || formula: =A1*2", lines)
        self.assertIn('[aba oculta no original]', lines)
        cells = ler_xlsx(source)['abas'][0]['celulas']
        self.assertEqual(cells[3], {'celula': 'B2', 'localizador': 'Gastos!B2', 'tipo': 'numero',
                                    'valor': '1234.5', 'exibido': '1,234.50', 'formula': None})

    def test_referencia_celula_cita_aba_como_excel(self):
        self.assertEqual(referencia_celula('Plan1', 'B3'), 'Plan1!B3')
        self.assertEqual(referencia_celula("Gastos d'obra", 'A1'), "'Gastos d''obra'!A1")
        self.assertEqual(referencia_celula('A1', 'C2'), "'A1'!C2")

    def test_corrompido_vira_pendencia_sem_derivado_e_original_preservado(self):
        source = self.dir / 'quebrado.docx'
        source.write_bytes(b'nao sou um zip')
        target = self.dir / 'D003.md'
        result = extrair(source, 'D003', target)
        self.assertEqual((result['estado'], result['recusa']), ('erro', 'corrompido'))
        self.assertIn('original fica preservado', result['mensagem'])
        self.assertFalse(target.exists())
        self.assertEqual(source.read_bytes(), b'nao sou um zip')

    def test_xml_invalido_e_pacote_sem_documento_sao_corrompidos(self):
        bad = _zip(self.dir / 'xml.docx', {'word/document.xml': '<w:document'})
        self.assertEqual(extrair(bad, 'D1', self.dir / 'a.md')['recusa'], 'corrompido')
        empty = _zip(self.dir / 'vazio.xlsx', {'outra.xml': '<a/>'})
        result = extrair(empty, 'D2', self.dir / 'b.md')
        self.assertEqual(result['recusa'], 'corrompido')
        self.assertIn('xl/workbook.xml', result['mensagem'])

    def test_aba_corrompida_e_parcial_sem_abortar(self):
        source = xlsx(self.dir / 'parcial.xlsx', [('Boa', '<row r="1"><c r="A1"><v>7</v></c></row>', None),
                                                   ('Ruim', '', None)],
                      extra={'xl/worksheets/sheet2.xml': '<worksheet><sheetData>'})
        result = extrair(source, 'D4', self.dir / 'c.md')
        self.assertEqual(result['estado'], 'parcial')
        self.assertEqual(result['falhas'][0]['aba'], 'Ruim')

    def test_macro_e_recusada_pela_extensao_e_pelo_conteudo(self):
        source = docx(self.dir / 'macro.docm', _p('x'))
        result = extrair(source, 'D5', self.dir / 'd.md')
        self.assertEqual((result['estado'], result['recusa']), ('erro', 'macro'))
        self.assertTrue(source.exists())
        hidden = docx(self.dir / 'disfarcado.docx', _p('x'), {'word/vbaProject.bin': b'\x00' * 10})
        self.assertEqual(extrair(hidden, 'D6', self.dir / 'e.md')['recusa'], 'macro')

    def test_protegido_por_senha_e_recusado(self):
        source = self.dir / 'senha.xlsx'
        source.write_bytes(extrair_office.ASSINATURA_OLE + b'\x00' * 512)
        result = extrair(source, 'D7', self.dir / 'f.md')
        self.assertEqual((result['estado'], result['recusa']), ('erro', 'protegido'))

    def test_zip_grande_demais_e_recusado(self):
        big = _p('A' * 5000) * 50
        source = docx(self.dir / 'grande.docx', big)
        result = extrair(source, 'D8', self.dir / 'g.md', limite_total=50_000)
        self.assertEqual((result['estado'], result['recusa']), ('erro', 'limite'))
        result = extrair(source, 'D8', self.dir / 'g.md', limite_membro=50_000)
        self.assertEqual(result['recusa'], 'limite')
        self.assertFalse((self.dir / 'g.md').exists())

    def test_tamanho_real_conta_mesmo_com_cabecalho_mentiroso(self):
        source = docx(self.dir / 'mente.docx', _p('B' * 200_000))
        pacote = extrair_office._Pacote(source, 10**9, 100_000)
        with pacote:
            with self.assertRaises(extrair_office.Recusa) as ctx:
                pacote.ler('word/document.xml')  # declared total is small; the per-part read budget still applies
            self.assertEqual(ctx.exception.motivo, 'limite')
            pacote.nomes['word/document.xml'].file_size = 10
            with self.assertRaises(extrair_office.Recusa) as ctx:
                pacote.ler('word/document.xml')  # a lying header is caught by zipfile's size/CRC check
            self.assertEqual(ctx.exception.motivo, 'corrompido')

    def test_dtd_e_entidades_sao_recusadas(self):
        evil = (f'<?xml version="1.0"?><!DOCTYPE d [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
                f'<w:document xmlns:w="{W}"><w:body><w:p><w:r><w:t>&x;</w:t></w:r></w:p></w:body></w:document>')
        source = _zip(self.dir / 'xxe.docx', {'word/document.xml': evil})
        result = extrair(source, 'D9', self.dir / 'h.md')
        self.assertEqual(result['recusa'], 'corrompido')
        self.assertIn('DTD', result['mensagem'])

    def test_nao_sobrescreve_derivado(self):
        source = docx(self.dir / 'ok.docx', _p('texto'))
        target = self.dir / 'i.md'
        self.assertEqual(extrair(source, 'D10', target)['estado'], 'extraido')
        with self.assertRaises(FileExistsError):
            extrair(source, 'D10', target)

    def test_documento_sem_texto(self):
        source = docx(self.dir / 'vazio.docx', '<w:p/>')
        target = self.dir / 'j.md'
        self.assertEqual(extrair(source, 'D11', target)['estado'], 'sem_texto')
        self.assertIn(extrair_office.SEM_TEXTO, target.read_text(encoding='utf-8'))

    def test_ler_docx_devolve_unidades_com_localizador(self):
        source = docx(self.dir / 'u.docx', _p('Um') + _p('Dois'))
        units = ler_docx(source)['secoes'][0]['unidades']
        self.assertEqual(units, [{'localizador': 'P0001', 'texto': 'Um'}, {'localizador': 'P0002', 'texto': 'Dois'}])

    # Regressões da revisão independente da Fase 04 (Working/tabelas-revisao.md).

    def test_exibido_arredonda_como_o_excel_e_nao_derruba_a_planilha(self):
        exibir = extrair_office._exibir
        self.assertEqual(exibir('2.5', '0', False), '3')
        self.assertEqual(exibir('0.125', '0.00', False), '0.13')
        self.assertEqual(exibir('-0.125', '0.00', False), '-0.13')
        self.assertEqual(exibir('0.125', '0%', False), '13%')
        self.assertEqual(exibir('-0.001', '0.00', False), '0.00')
        self.assertEqual(exibir('1E+30', '#,##0.00', False), '1,000,000,000,000,000,000,000,000,000,000.00')
        self.assertIsNone(exibir('2958000', 'data', True))  # fora do intervalo de datas com base 1904
        styles = ('<numFmts count="1"><numFmt numFmtId="164" formatCode="0.00"/></numFmts>'
                  '<cellXfs count="3"><xf numFmtId="0"/><xf numFmtId="164"/><xf numFmtId="14"/></cellXfs>')
        data = ('<row r="1"><c r="A1" s="1"><v>1.5E+26</v></c><c r="B1" s="2"><v>2958000</v></c>'
                '<c r="C1" s="1"><v>2.345</v></c></row>')
        source = xlsx(self.dir / 'grande.xlsx', [('P', data, None)], styles=styles,
                      extra={'xl/workbook.xml': f'<?xml version="1.0"?><workbook xmlns="{S}" xmlns:r="{R}">'
                                                '<workbookPr date1904="1"/><sheets><sheet name="P" sheetId="1" r:id="rId1"/>'
                                                '</sheets></workbook>'})
        result = extrair(source, 'X20', self.dir / 'x20.md')
        self.assertEqual(result['estado'], 'extraido')
        cells = {c['celula']: c for c in ler_xlsx(source)['abas'][0]['celulas']}
        self.assertEqual((cells['A1']['valor'], cells['A1']['exibido']), ('1.5E+26', '150000000000000000000000000.00'))
        self.assertEqual((cells['B1']['valor'], cells['B1']['exibido']), ('2958000', None))
        self.assertEqual(cells['C1']['exibido'], '2.35')

    def test_celulas_e_linhas_sem_referencia_sao_inferidas_pela_posicao(self):
        data = ('<row><c t="inlineStr"><is><t>a</t></is></c><c><v>2</v></c></row>'
                '<row r="5"><c r="C5"><v>3</v></c><c><v>4</v></c></row><row><c><v>5</v></c></row>')
        result = ler_xlsx(xlsx(self.dir / 'semr.xlsx', [('P', data, None)]))
        self.assertEqual(result['falhas'], [])
        self.assertEqual([c['localizador'] for c in result['abas'][0]['celulas']],
                         ['P!A1', 'P!B1', 'P!C5', 'P!D5', 'P!A6'])
        self.assertEqual(extrair_office._letras_coluna(28), 'AB')
        self.assertEqual(extrair_office._numero_coluna('AB7'), 28)

    def test_indice_negativo_de_texto_compartilhado_e_falha(self):
        data = '<row r="1"><c r="A1" t="s"><v>-1</v></c><c r="B1" t="s"><v>0</v></c></row>'
        result = ler_xlsx(xlsx(self.dir / 'neg.xlsx', [('P', data, None)], shared=('um', 'dois')))
        self.assertEqual([c['valor'] for c in result['abas'][0]['celulas']], ['um'])
        self.assertEqual(result['falhas'][0]['celula'], 'A1')

    def test_tabela_docx_com_controle_de_conteudo_e_grid_before(self):
        table = ('<w:tbl><w:tr><w:tc>' + _p('A') + '</w:tc><w:tc>' + _p('B') + '</w:tc><w:tc>' + _p('C') + '</w:tc></w:tr>'
                 '<w:sdt><w:sdtContent><w:tr><w:tc>' + _p('Linha no controle') + '</w:tc>'
                 '<w:sdt><w:sdtContent><w:tc>' + _p('Celula no controle') + '</w:tc></w:sdtContent></w:sdt>'
                 '</w:tr></w:sdtContent></w:sdt>'
                 '<w:tr><w:trPr><w:gridBefore w:val="1"/></w:trPr><w:tc>' + _p('Deslocada') + '</w:tc></w:tr></w:tbl>')
        units = ler_docx(docx(self.dir / 'sdt.docx', table))['secoes'][0]['unidades']
        self.assertEqual([(u['localizador'], u['texto']) for u in units], [
            ('T01 L01 C01', 'A'), ('T01 L01 C02', 'B'), ('T01 L01 C03', 'C'),
            ('T01 L02 C01', 'Linha no controle'), ('T01 L02 C02', 'Celula no controle'),
            ('T01 L03 C02', 'Deslocada')])

    def test_caixa_de_texto_nao_duplica_texto_nem_paragrafos(self):
        mc = 'http://schemas.openxmlformats.org/markup-compatibility/2006'
        caixa = (f'<w:p><w:r><w:t>Ancora </w:t></w:r><w:r><mc:AlternateContent xmlns:mc="{mc}">'
                 '<mc:Choice Requires="wps"><w:drawing><w:txbxContent>' + _p('Na caixa') + '</w:txbxContent></w:drawing></mc:Choice>'
                 '<mc:Fallback><w:pict><w:txbxContent>' + _p('Na caixa') + '</w:txbxContent></w:pict></mc:Fallback>'
                 '</mc:AlternateContent></w:r></w:p>')
        table = '<w:tbl><w:tr><w:tc>' + caixa + '</w:tc></w:tr></w:tbl>'
        units = ler_docx(docx(self.dir / 'caixa.docx', caixa + table))['secoes'][0]['unidades']
        self.assertEqual([(u['localizador'], u['texto']) for u in units],
                         [('P0001', 'Ancora Na caixa'), ('T01 L01 C01', 'Ancora Na caixa')])

    def test_cabecalhos_seguem_ordem_numerica_das_partes(self):
        extra = {f'word/header{n}.xml': f'<w:hdr xmlns:w="{W}">{_p(f"Cabecalho {n}")}</w:hdr>' for n in (2, 10)}
        rels = ''.join(f'<Relationship Id="rId{n}" Type="{REL}/header" Target="header{n}.xml"/>' for n in (10, 2))
        secoes = ler_docx(docx(self.dir / 'cab.docx', _p('x'), extra, rels))['secoes']
        self.assertEqual([s['unidades'][0]['texto'] for s in secoes if s['titulo'].startswith('cabecalho')],
                         ['Cabecalho 2', 'Cabecalho 10'])

    def test_dtd_e_macro_em_utf16_tambem_sao_detectados(self):
        evil = (f'<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE d [<!ENTITY x "y">]>'
                f'<w:document xmlns:w="{W}"><w:body>{_p("&x;")}</w:body></w:document>')
        source = _zip(self.dir / 'utf16.docx', {'word/document.xml': evil.encode('utf-16')})
        result = extrair(source, 'D21', self.dir / 'd21.md')
        self.assertEqual(result['recusa'], 'corrompido')
        self.assertIn('DTD', result['mensagem'])
        tipos = ('<?xml version="1.0" encoding="UTF-16"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/'
                 'content-types"><Override PartName="/word/outra.bin" ContentType="application/vnd.ms-office.vbaProject"/>'
                 '</Types>').encode('utf-16')
        source = docx(self.dir / 'macro16.docx', _p('x'), {'[Content_Types].xml': tipos})
        self.assertEqual(extrair(source, 'D22', self.dir / 'd22.md')['recusa'], 'macro')

    def test_quebras_de_linha_nao_separam_texto_do_localizador(self):
        data = '<row r="1"><c r="A1" t="inlineStr"><is><t>um\u2028dois\x85fim</t></is></c></row>'
        source = xlsx(self.dir / 'quebras.xlsx', [('Plan1', data, None)])
        target = self.dir / 'k.md'
        extrair(source, 'D12', target)
        self.assertIn('[Plan1!A1] um ⏎ dois ⏎ fim', target.read_text(encoding='utf-8').splitlines())


def png_branco(path: Path, size=8):
    """Minimal valid grayscale PNG built with zlib (no image library needed)."""
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    raw = b''.join(b'\x00' + b'\xff' * size for _ in range(size))
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 0, 0, 0, 0))
                     + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))
    return path


class CadastroOfficeTest(unittest.TestCase):
    """Registration, receipt, SQLite index and opt-in image OCR on synthetic files."""

    def setUp(self):
        from comum import PARTES, escrever_json, fluxo_esperado, manifesto_prompts
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'prompts').mkdir()
        for name in PARTES:
            (self.root / 'prompts' / name).write_text('# Fixture sintetica\n', encoding='utf-8')
        (self.root / 'prompts' / 'FLUXO_COMPLETO.md').write_bytes(fluxo_esperado(self.root))
        escrever_json(self.root / 'prompts' / 'manifesto_prompts.json', manifesto_prompts(self.root))
        (self.root / 'AGENTS.md').write_text('Fixture tecnica.', encoding='utf-8')
        escrever_json(self.root / 'configuracao.json', {'versao': '1.1.0', 'caso_ativo': None,
            'manifesto_ativo': None, 'maximo_documentos_inicial': 20, 'indice_sqlite': True})
        self.src = self.root / 'recebidos'
        self.src.mkdir()

    def arquivos(self):
        planilha = ('<row r="1"><c r="A1" t="inlineStr"><is><t>Item</t></is></c>'
                    '<c r="B1" t="inlineStr"><is><t>Fornecedor</t></is></c></row>'
                    '<row r="3"><c r="A3" t="inlineStr"><is><t>Obra sintetica</t></is></c>'
                    '<c r="B3" t="inlineStr"><is><t>Empresa Zeta</t></is></c>'
                    '<c r="C3"><f>SUM(C1:C2)</f><v>10</v></c></row>')
        xl = xlsx(self.src / 'gastos.xlsx', [('Plan1', planilha, None), ("Gastos d'obra", '<row r="1"><c r="A1"><v>7</v></c></row>', None)])
        table = '<w:tbl><w:tr><w:tc>' + _p('Contrato') + '</w:tc><w:tc>' + _p('Empresa Zeta assinou') + '</w:tc></w:tr></w:tbl>'
        doc = docx(self.src / 'nota.docx', _p('Paragrafo sintetico unico.') + table)
        return doc, xl

    def cadastrar(self, sources, **kwargs):
        import cadastrar_documentos
        kwargs.setdefault('novo', True)
        if kwargs['novo']:
            kwargs.setdefault('titulo', 'Caso sintetico Office')
        return cadastrar_documentos.cadastrar(self.root, 'alpha', sources, natureza='sinteticos', **kwargs)

    def manifest(self):
        return json.loads((self.root / 'casos/alpha/manifesto.json').read_text(encoding='utf-8'))

    def rodada(self):
        from nova_rodada import criar_rodada
        from selecionar_caso import selecionar
        selecionar(self.root, 'alpha')
        return criar_rodada(self.root, 'R001', 'Pergunta sintetica de armazenamento, sem apuracao.')

    def test_cadastro_registra_derivado_hash_origem_versao_e_recibo(self):
        from comum import sha256
        doc, xl = self.arquivos()
        result = self.cadastrar([doc, xl])
        docs = {d['nome_recebido']: d for d in self.manifest()['documentos']}
        for name, kind in (('nota.docx', 'docx'), ('gastos.xlsx', 'xlsx')):
            entry = docs[name]
            self.assertEqual(entry['extracao_office']['estado'], 'extraido')
            [derived] = entry['derivados']
            self.assertEqual(derived['tipo'], f'texto_extraido_{kind}')
            self.assertEqual(derived['origem'], f'extracao_{kind}')
            self.assertEqual(derived['versao_extrator'], extrair_office.VERSAO_EXTRATOR)
            self.assertEqual(derived['origem_sha256'], entry['sha256'])
            self.assertTrue(derived['arquivo'].endswith(f'/derivados/{entry["id"]}_texto_{kind}.md'))
            self.assertEqual(sha256(self.root / derived['arquivo']), derived['sha256'])
            self.assertEqual(sha256(self.root / entry['arquivo']), entry['sha256'])
        summary = result['extracao_office_resumo']
        self.assertEqual({k: summary[k] for k in ('documentos', 'processados_agora', 'docx', 'xlsx', 'extraido',
                                                    'paragrafos', 'celulas_tabela', 'abas', 'celulas', 'formulas', 'falhas')},
                         {'documentos': 2, 'processados_agora': 2, 'docx': 1, 'xlsx': 1, 'extraido': 2,
                          'paragrafos': 1, 'celulas_tabela': 2, 'abas': 2, 'celulas': 6, 'formulas': 1, 'falhas': 0})
        receipt = json.loads((self.root / result['arquivo_recibo']).read_text(encoding='utf-8'))
        self.assertEqual(receipt['extracao_office_resumo'], summary)
        self.assertTrue(all(item['derivados'] and item['extracao_office'] for item in receipt['arquivos']))
        self.assertEqual(result['inventario']['documentos'][0]['derivados'], 1)

    def test_reenvio_nao_reprocessa_extracao_legivel(self):
        doc, _ = self.arquivos()
        first = self.cadastrar([doc])
        again = self.cadastrar([doc], novo=False)
        self.assertEqual(again['duplicados'], 1)
        self.assertEqual(again['extracao_office_resumo']['processados_agora'], 0)
        self.assertEqual(again['corpus_id'], first['corpus_id'])

    def test_macro_e_corrompido_ficam_pendentes_sem_abortar_o_lote(self):
        from comum import sha256
        doc, _ = self.arquivos()
        macro = docx(self.src / 'macro.xlsm', _p('x'))
        broken = self.src / 'quebrado.docx'
        broken.write_bytes(b'nao sou um zip')
        result = self.cadastrar([doc, macro, broken])
        self.assertEqual(result['novos'], 3)
        docs = {d['nome_recebido']: d for d in self.manifest()['documentos']}
        for name, reason in (('macro.xlsm', 'macro'), ('quebrado.docx', 'corrompido')):
            entry = docs[name]
            self.assertEqual((entry['extracao_office']['estado'], entry['extracao_office']['recusa']), ('erro', reason))
            self.assertIn('original fica preservado', entry['extracao_office']['mensagem'])
            self.assertEqual(entry['derivados'], [])
            self.assertEqual(sha256(self.root / entry['arquivo']), entry['sha256'])
        self.assertEqual(result['extracao_office_resumo']['recusados'], {'macro': 1, 'corrompido': 1})
        self.assertEqual(result['extracao_office_resumo']['erro'], 2)

    def test_busca_no_indice_devolve_aba_celula_e_paragrafo(self):
        from indice_sqlite import cobertura, ler_passagem, pesquisar, verificar_indice
        doc, xl = self.arquivos()
        self.cadastrar([doc, xl])
        self.rodada()
        ids = {d['nome_recebido']: d['id'] for d in self.manifest()['documentos']}
        response = pesquisar(self.root, 'alpha', 'R001', 'Zeta', documentos=[ids['gastos.xlsx']])
        [hit] = response['resultados']
        self.assertEqual(hit['formato'], 'xlsx')
        self.assertEqual(hit['localizadores_com_termo'], ['Plan1!B3'])
        self.assertEqual(hit['localizadores'], ['Plan1!A1', 'Plan1!B1', 'Plan1!A3', 'Plan1!B3', 'Plan1!C3'])
        self.assertIsNone(hit['pagina_pdf'])
        self.assertIn('[Plan1!B3] Empresa Zeta', hit['trecho'])
        literal = pesquisar(self.root, 'alpha', 'R001', 'Empresa Zeta', modo='literal', documentos=[ids['gastos.xlsx']])
        self.assertEqual(literal['resultados'][0]['localizadores_com_termo'], ['Plan1!B3'])
        quoted = pesquisar(self.root, 'alpha', 'R001', '7', modo='literal', documentos=[ids['gastos.xlsx']])
        self.assertEqual(quoted['resultados'][0]['localizadores_com_termo'], ["'Gastos d''obra'!A1"])
        docx_hit = pesquisar(self.root, 'alpha', 'R001', 'Zeta', documentos=[ids['nota.docx']])['resultados'][0]
        self.assertEqual(docx_hit['localizadores_com_termo'], ['T01 L01 C02'])
        self.assertEqual(docx_hit['localizador_inicio'], 'P0001')
        passage = ler_passagem(self.root, 'alpha', 'R001', hit['referencia'])
        self.assertEqual(passage['unidade_completa'][3]['localizador'], 'Plan1!B3')
        report = cobertura(self.root, 'alpha', 'R001')['cobertura']
        adapters = {f['adaptador'] for d in report['documentos'] for f in d['fontes'] if f['tipo'] == 'derivado'}
        self.assertEqual(adapters, {'markdown_docx_v1', 'markdown_xlsx_v1'})
        self.assertEqual(report['documentos_pesquisaveis'], 2)
        self.assertEqual(pesquisar(self.root, 'alpha', 'R001', 'SHA-256')['total_correspondencias'], 0)
        self.assertEqual(verificar_indice(self.root, 'alpha', 'R001')['estado'], 'ok')

    def test_derivado_incoerente_nao_ganha_localizador(self):
        from indice_sqlite import _adaptar
        doc, xl = self.arquivos()
        self.cadastrar([xl])
        entry = self.manifest()['documentos'][0]
        derived = self.root / entry['derivados'][0]['arquivo']
        good = derived.read_text(encoding='utf-8')
        self.assertEqual(_adaptar(derived, entry['id'], entry['sha256'], 'derivado')[2][0]['estado'], 'com_texto')
        for bad in (good.replace('[Plan1!B3]', '[Outra!B3]'), good.replace('[Plan1!B3] ', ''),
                    good.replace(entry['sha256'], '0' * 64)):
            copy = self.root / 'incoerente.md'
            copy.write_text(bad, encoding='utf-8')
            adapter, _, units = _adaptar(copy, entry['id'], entry['sha256'], 'derivado')
            self.assertEqual(adapter, 'markdown_xlsx_v1')
            self.assertEqual([u['estado'] for u in units], ['erro_leitura'])

    def test_marcadores_do_indice_correspondem_aos_dos_extratores(self):
        import indice_sqlite
        import ocr
        self.assertEqual(indice_sqlite.MARCADORES_OFFICE, extrair_office.MARCADORES)
        self.assertEqual(indice_sqlite.SEM_TEXTO_IMAGEM, ocr.SEM_TEXTO_IMAGEM)
        self.assertEqual(indice_sqlite.AVISO_OCR_IMAGEM, ocr.AVISO_OCR_IMAGEM)

    def test_imagem_sem_ocr_por_padrao(self):
        image = png_branco(self.src / 'foto.png')
        with patch('ocr.reconhecer_imagem') as engine:
            result = self.cadastrar([image])
        engine.assert_not_called()
        entry = self.manifest()['documentos'][0]
        self.assertNotIn('ocr_imagem', entry)
        self.assertEqual(entry['derivados'], [])
        self.assertEqual(result['ocr_imagens_resumo'],
                         {'solicitado': False, 'imagens': 1, 'processadas_agora': 0, 'extraido': 0,
                          'sem_texto': 0, 'pendente': 0, 'erro': 0, 'sem_ocr': 1})

    def test_ocr_imagens_sem_tesseract_fica_pendente_com_mensagem(self):
        import ocr
        image = png_branco(self.src / 'foto.png')
        config = {**ocr.configuracao(), 'habilitado': True, 'tesseract': None}
        with patch('ocr.configuracao', return_value=config):
            result = self.cadastrar([image], ocr_imagens=True)
        entry = self.manifest()['documentos'][0]
        self.assertEqual(entry['ocr_imagem']['estado'], 'pendente')
        self.assertIn('Tesseract nao encontrado', entry['ocr_imagem']['mensagem'])
        self.assertEqual(entry['derivados'], [])
        self.assertEqual(result['ocr_imagens_resumo']['pendente'], 1)

    def test_ocr_imagens_marca_origem_ocr_e_indexa_com_aviso(self):
        from indice_sqlite import pesquisar
        image = png_branco(self.src / 'foto.png')
        fake = {'motor': 'tesseract', 'versoes': {'tesseract': '5.x (simulado)'}, 'idiomas': 'por+eng',
                'texto': 'Placa sintetica\nNumero 42', 'avisos': []}
        with patch('ocr.reconhecer_imagem', return_value=fake):
            result = self.cadastrar([image], ocr_imagens=True)
        entry = self.manifest()['documentos'][0]
        self.assertEqual((entry['ocr_imagem']['estado'], entry['ocr_imagem']['origem']), ('extraido', 'ocr'))
        [derived] = entry['derivados']
        self.assertEqual((derived['tipo'], derived['origem']), ('texto_ocr_imagem', 'ocr'))
        self.assertIn('conferir no original', derived['aviso'])
        self.assertIn('conferir no original', result['ocr_imagens_resumo']['aviso'])
        self.rodada()
        [hit] = pesquisar(self.root, 'alpha', 'R001', 'Numero 42')['resultados']
        self.assertEqual((hit['origem_texto'], hit['linha_inicio'], hit['linha_fim']), ('ocr', 1, 2))
        self.assertIn('conferir no original', hit['aviso_ocr'])

    @unittest.skipUnless(__import__('ocr').diagnostico()['tesseract']['disponivel'], 'Tesseract local ausente')
    def test_ocr_imagens_com_tesseract_real(self):
        image = png_branco(self.src / 'branca.png', size=64)
        result = self.cadastrar([image], ocr_imagens=True)
        info = self.manifest()['documentos'][0]['ocr_imagem']
        self.assertIn(info['estado'], ('sem_texto', 'extraido'))
        self.assertEqual(info['motor'], 'tesseract')
        self.assertEqual(result['ocr_imagens_resumo']['processadas_agora'], 1)


if __name__ == '__main__':
    unittest.main()
