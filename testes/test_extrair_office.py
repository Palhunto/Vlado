"""DOCX/XLSX extraction with locators; packages are built inside the tests with zipfile."""
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

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


if __name__ == '__main__':
    unittest.main()
