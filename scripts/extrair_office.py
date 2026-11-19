"""Extract DOCX and XLSX to a located working copy using only the standard library.

DOCX: body paragraphs and table cells in document order, plus headers, footers,
footnotes, endnotes and comments when present. XLSX: every filled cell of every
sheet with its `Aba!A1` reference, the stored value, a displayed value for simple
number formats and the formula as text (never evaluated).

Files with macros (.docm/.xlsm or a vbaProject part), encrypted/protected files,
corrupted packages and packages over the decompression limits are refused as a
readable pending outcome (`estado: erro`, `recusa`), without touching the original.
No network, no model calls, no XML DTD or entity resolution.
"""
import argparse
import datetime as _dt
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from pathlib import Path, PurePosixPath

from comum import sha256

VERSAO_EXTRATOR = '1'
SEM_TEXTO = '[SEM TEXTO EXTRAIVEL NESTE DOCUMENTO]'
SEPARADOR_PARAGRAFOS_CELULA = ' ¶ '

# Decompression limits (bytes actually read, not the sizes declared in the zip headers).
LIMITE_DESCOMPACTADO_TOTAL = 200 * 1024 * 1024
LIMITE_DESCOMPACTADO_MEMBRO = 64 * 1024 * 1024
LIMITE_MEMBROS = 5000
LIMITE_RAZAO_COMPRESSAO = 200
LIMITE_CELULAS = 1_000_000

EXTENSOES_MACRO = {'.docm', '.xlsm', '.dotm', '.xltm', '.xlam'}
EXTENSOES = {'.docx': 'docx', '.xlsx': 'xlsx'}
ASSINATURA_OLE = b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'

REL_HEADER = 'header'
REL_FOOTER = 'footer'


class Recusa(Exception):
    """A readable refusal: the original stays registered, the extraction is pending."""

    def __init__(self, motivo: str, mensagem: str):
        super().__init__(mensagem)
        self.motivo = motivo


# ---------------------------------------------------------------- zip and XML safety

def _local(tag) -> str:
    return tag.rsplit('}', 1)[-1] if isinstance(tag, str) else ''


def _attr(element, name, default=None):
    """Attribute lookup by local name, so Transitional and Strict OOXML both work."""
    for key, value in element.attrib.items():
        if _local(key) == name:
            return value
    return default


def _filhos(element, name):
    return [child for child in element if _local(child.tag) == name]


def _filho(element, name):
    return next((child for child in element if _local(child.tag) == name), None)


class _Pacote:
    """Read-only OOXML zip with a running budget of decompressed bytes."""

    def __init__(self, source: Path, limite_total: int, limite_membro: int):
        with source.open('rb') as stream:
            head = stream.read(8)
        if head == ASSINATURA_OLE:
            raise Recusa('protegido', 'Arquivo protegido por senha ou criptografado (contêiner OLE); conteúdo não extraído.')
        try:
            self.zip = zipfile.ZipFile(source)
        except zipfile.BadZipFile as exc:
            raise Recusa('corrompido', f'Arquivo corrompido ou não é um pacote Office (zip inválido: {exc}).') from exc
        infos = self.zip.infolist()
        if len(infos) > LIMITE_MEMBROS:
            raise Recusa('limite', f'Pacote com {len(infos)} partes, acima do limite de {LIMITE_MEMBROS}.')
        if any(info.flag_bits & 0x1 for info in infos):
            raise Recusa('protegido', 'Pacote com partes criptografadas; conteúdo não extraído.')
        declarado = sum(info.file_size for info in infos)
        if declarado > limite_total:
            raise Recusa('limite', f'Tamanho descompactado declarado ({declarado} bytes) acima do limite de {limite_total} bytes.')
        for info in infos:
            if info.compress_size and info.file_size / info.compress_size > LIMITE_RAZAO_COMPRESSAO and info.file_size > 1024 * 1024:
                raise Recusa('limite', f'Parte {info.filename} com razão de compressão suspeita; possível zip bomb.')
        self.nomes = {info.filename: info for info in infos}
        self.restante = limite_total
        self.limite_membro = limite_membro

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.zip.close()

    def existe(self, name: str) -> bool:
        return name in self.nomes

    def ler(self, name: str) -> bytes:
        info = self.nomes[name]
        limite = min(self.limite_membro, self.restante)
        partes, lido = [], 0
        try:
            with self.zip.open(info) as stream:
                while True:
                    bloco = stream.read(1024 * 1024)
                    if not bloco:
                        break
                    lido += len(bloco)
                    if lido > limite:
                        raise Recusa('limite', f'Parte {name} excede o limite de descompactação ({limite} bytes); possível zip bomb.')
                    partes.append(bloco)
        except (zipfile.BadZipFile, EOFError, OSError, RuntimeError, NotImplementedError, ValueError) as exc:
            if isinstance(exc, RuntimeError) and 'encrypted' in str(exc).lower():
                raise Recusa('protegido', f'Parte {name} criptografada; conteúdo não extraído.') from exc
            raise Recusa('corrompido', f'Parte {name} corrompida: {type(exc).__name__}: {str(exc)[:300]}') from exc
        self.restante -= lido
        return b''.join(partes)

    def xml(self, name: str):
        return _parse_xml(self.ler(name), name)


_DTD = re.compile(rb'<!DOCTYPE|<!ENTITY', re.IGNORECASE)


def _parse_xml(data: bytes, name: str):
    # OOXML never needs a DTD; refusing it blocks external entities and entity expansion.
    if _DTD.search(data):
        raise Recusa('corrompido', f'Parte {name} declara DTD/entidades XML; recusada por segurança.')
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise Recusa('corrompido', f'Parte {name} com XML inválido: {exc}') from exc


def _verificar_macro(pacote: _Pacote):
    if any(PurePosixPath(n).name.lower() == 'vbaproject.bin' for n in pacote.nomes):
        raise Recusa('macro', 'Pacote contém macros (vbaProject.bin); conteúdo não extraído.')
    if pacote.existe('[Content_Types].xml'):
        tipos = pacote.ler('[Content_Types].xml').lower()
        if b'macroenabled' in tipos or b'vbaproject' in tipos:
            raise Recusa('macro', 'Pacote declarado como habilitado para macros; conteúdo não extraído.')


def _relacoes(pacote: _Pacote, parte: str) -> dict:
    """Map relationship id -> (type local name, absolute part name) for one part."""
    caminho = PurePosixPath(parte)
    rels_name = str(caminho.parent / '_rels' / f'{caminho.name}.rels')
    if not pacote.existe(rels_name):
        return {}
    result = {}
    for rel in pacote.xml(rels_name):
        if _local(rel.tag) != 'Relationship' or _attr(rel, 'TargetMode') == 'External':
            continue
        target = _attr(rel, 'Target') or ''
        if target.startswith('/'):
            absolute = target.lstrip('/')
        else:
            partes = []
            for piece in (caminho.parent / target).parts:
                if piece == '..':
                    if partes:
                        partes.pop()
                elif piece != '.':
                    partes.append(piece)
            absolute = '/'.join(partes)
        result[_attr(rel, 'Id')] = (_attr(rel, 'Type', '').rsplit('/', 1)[-1], absolute)
    return result


# ---------------------------------------------------------------- DOCX

def _texto_paragrafo(paragraph) -> str:
    pieces = []

    def walk(node):
        for child in node:
            name = _local(child.tag)
            if name in ('t',):
                pieces.append(child.text or '')
            elif name == 'tab':
                pieces.append('\t')
            elif name in ('br', 'cr'):
                pieces.append(' ')
            elif name == 'noBreakHyphen':
                pieces.append('-')
            elif name == 'footnoteReference':
                pieces.append(f'[nota {_attr(child, "id")}]')
            elif name == 'endnoteReference':
                pieces.append(f'[nota final {_attr(child, "id")}]')
            elif name in ('delText', 'instrText', 'del', 'moveFrom', 'rPr', 'pPr'):
                continue  # deleted text, field codes and formatting are not displayed text
            else:
                walk(child)
    walk(paragraph)
    return ''.join(pieces).strip()


def _paragrafos_de(node):
    """All paragraphs below node, in order, including those inside nested tables/controls."""
    return [p for p in node.iter() if _local(p.tag) == 'p']


def _blocos(container):
    """Body-level paragraphs and tables in order, unwrapping content controls."""
    for child in container:
        name = _local(child.tag)
        if name in ('p', 'tbl'):
            yield child
        elif name in ('sdt', 'customXml', 'ins', 'moveTo'):
            content = _filho(child, 'sdtContent') if name == 'sdt' else child
            if content is not None:
                yield from _blocos(content)


def _ler_parte_paragrafos(raiz, prefixo, unidades):
    count = 0
    for paragraph in _paragrafos_de(raiz):
        text = _texto_paragrafo(paragraph)
        if text:
            count += 1
            unidades.append({'localizador': f'{prefixo}P{count:04d}', 'texto': text})
    return count


def ler_docx(source: Path, *, limite_total=None, limite_membro=None) -> dict:
    """Return {'secoes': [{'titulo', 'unidades': [{'localizador', 'texto', ...}]}], 'contagens', 'avisos', 'falhas'}."""
    limite_total = limite_total or LIMITE_DESCOMPACTADO_TOTAL
    limite_membro = limite_membro or LIMITE_DESCOMPACTADO_MEMBRO
    with _Pacote(source, limite_total, limite_membro) as pacote:
        _verificar_macro(pacote)
        principal = 'word/document.xml'
        if not pacote.existe(principal):
            raise Recusa('corrompido', 'Pacote sem word/document.xml; não é um DOCX legível.')
        raiz = pacote.xml(principal)
        body = _filho(raiz, 'body')
        if body is None:
            raise Recusa('corrompido', 'word/document.xml sem corpo (w:body).')
        contagens = {'paragrafos': 0, 'tabelas': 0, 'celulas_tabela': 0, 'cabecalhos': 0, 'rodapes': 0,
                     'notas_rodape': 0, 'notas_fim': 0, 'comentarios': 0}
        avisos, falhas = [], []
        if any(_local(e.tag) in ('ins', 'del') for e in raiz.iter()):
            avisos.append('Documento com controle de alterações: o texto segue a versão com inserções e sem exclusões.')
        corpo = []
        for bloco in _blocos(body):
            if _local(bloco.tag) == 'p':
                text = _texto_paragrafo(bloco)
                if text:
                    contagens['paragrafos'] += 1
                    corpo.append({'localizador': f'P{contagens["paragrafos"]:04d}', 'texto': text})
                continue
            contagens['tabelas'] += 1
            tabela = contagens['tabelas']
            for linha, row in enumerate(_filhos(bloco, 'tr'), 1):
                coluna = 1
                for cell in _filhos(row, 'tc'):
                    props = _filho(cell, 'tcPr')
                    span = 1
                    if props is not None:
                        grid = _filho(props, 'gridSpan')
                        if grid is not None:
                            try:
                                span = max(1, int(_attr(grid, 'val', '1')))
                            except ValueError:
                                span = 1
                    textos = [t for t in (_texto_paragrafo(p) for p in _paragrafos_de(cell)) if t]
                    if textos:
                        contagens['celulas_tabela'] += 1
                        corpo.append({'localizador': f'T{tabela:02d} L{linha:02d} C{coluna:02d}',
                                      'texto': SEPARADOR_PARAGRAFOS_CELULA.join(textos)})
                    coluna += span
        secoes = [{'titulo': 'documento', 'unidades': corpo}]

        rels = _relacoes(pacote, principal)
        vistos = set()
        for kind, label, prefix, key in ((REL_HEADER, 'cabecalho', 'CAB', 'cabecalhos'),
                                         (REL_FOOTER, 'rodape', 'ROD', 'rodapes')):
            numero = 0
            for _, (tipo, parte) in sorted(rels.items(), key=lambda item: item[1][1]):
                if tipo != kind or parte in vistos or not pacote.existe(parte):
                    continue
                vistos.add(parte)
                try:
                    unidades = []
                    if _ler_parte_paragrafos(pacote.xml(parte), f'{prefix}{numero + 1} ', unidades):
                        numero += 1
                        contagens[key] += 1
                        secoes.append({'titulo': f'{label} {numero}', 'unidades': unidades})
                except Recusa as exc:
                    if exc.motivo == 'limite':
                        raise
                    falhas.append({'parte': parte, 'erro': str(exc)})

        for parte, label, prefix, key in (('word/footnotes.xml', 'notas de rodape', 'NOTA', 'notas_rodape'),
                                          ('word/endnotes.xml', 'notas finais', 'NOTAFIM', 'notas_fim'),
                                          ('word/comments.xml', 'comentarios', 'COMENT', 'comentarios')):
            if not pacote.existe(parte):
                continue
            try:
                raiz_notas = pacote.xml(parte)
            except Recusa as exc:
                if exc.motivo == 'limite':
                    raise
                falhas.append({'parte': parte, 'erro': str(exc)})
                continue
            unidades = []
            for note in raiz_notas:
                if _local(note.tag) not in ('footnote', 'endnote', 'comment') or _attr(note, 'type'):
                    continue  # separators carry w:type and no author text
                ident = _attr(note, 'id', '?')
                count = 0
                for paragraph in _paragrafos_de(note):
                    text = _texto_paragrafo(paragraph)
                    if text:
                        count += 1
                        unit = {'localizador': f'{prefix} {ident} P{count:04d}', 'texto': text}
                        if key == 'comentarios' and _attr(note, 'author'):
                            unit['autor'] = _attr(note, 'author')
                        unidades.append(unit)
                if count:
                    contagens[key] += 1
            if unidades:
                secoes.append({'titulo': label, 'unidades': unidades})

        protecao = 'word/settings.xml'
        if pacote.existe(protecao):
            try:
                settings = pacote.xml(protecao)
                if any(_local(e.tag) in ('documentProtection', 'writeProtection') for e in settings):
                    avisos.append('Documento marcado com proteção de edição; a leitura do texto não foi afetada.')
            except Recusa as exc:
                if exc.motivo == 'limite':
                    raise
    return {'secoes': secoes, 'contagens': contagens, 'avisos': avisos, 'falhas': falhas}


# ---------------------------------------------------------------- XLSX

_CELULA = re.compile(r'^([A-Z]{1,3})([1-9][0-9]*)$')
_NOME_SIMPLES = re.compile(r'^[A-Za-z_][A-Za-z0-9_.]*$')
FORMATOS_EMBUTIDOS = {1: '0', 2: '0.00', 3: '#,##0', 4: '#,##0.00', 9: '0%', 10: '0.00%',
                      14: 'data', 15: 'data', 16: 'data', 17: 'data', 22: 'data_hora'}
_FORMATO_NUMERICO = re.compile(r'^(#,##)?0(\.0+)?(%)?$')
_FORMATO_DATA = re.compile(r'^[dmyhs:/\-. ,]+(?:AM/PM)?$', re.IGNORECASE)


def referencia_celula(aba: str, celula: str) -> str:
    """`Aba!B3`, quoting the sheet name as Excel does when it is not a plain identifier."""
    nome = aba if _NOME_SIMPLES.fullmatch(aba) and not _CELULA.fullmatch(aba.upper()) else "'" + aba.replace("'", "''") + "'"
    return f'{nome}!{celula}'


def _classificar_formato(codigo: str):
    codigo = (codigo or '').strip()
    if not codigo or codigo.lower() == 'general' or ';' in codigo or '"' in codigo:
        return None
    if _FORMATO_NUMERICO.fullmatch(codigo):
        return codigo
    sem_cor = re.sub(r'\[[^\]]*\]', '', codigo).replace('\\', '').strip()
    if _FORMATO_DATA.fullmatch(sem_cor) and re.search(r'[dy]', sem_cor, re.IGNORECASE):
        return 'data_hora' if re.search(r'h', sem_cor, re.IGNORECASE) else 'data'
    return None


def _formatos(pacote: _Pacote) -> list:
    """Index cellXfs -> simple format kind or None."""
    if not pacote.existe('xl/styles.xml'):
        return []
    styles = pacote.xml('xl/styles.xml')
    custom = {}
    numfmts = _filho(styles, 'numFmts')
    if numfmts is not None:
        for fmt in _filhos(numfmts, 'numFmt'):
            try:
                custom[int(_attr(fmt, 'numFmtId'))] = _attr(fmt, 'formatCode', '')
            except (TypeError, ValueError):
                continue
    xfs = _filho(styles, 'cellXfs')
    result = []
    for xf in (_filhos(xfs, 'xf') if xfs is not None else []):
        try:
            ident = int(_attr(xf, 'numFmtId', '0'))
        except ValueError:
            ident = 0
        result.append(_classificar_formato(custom[ident]) if ident in custom else FORMATOS_EMBUTIDOS.get(ident))
    return result


def _exibir(valor: str, formato, data1904: bool):
    if not formato:
        return None
    try:
        number = Decimal(valor)
    except (InvalidOperation, ValueError):
        return None
    if not number.is_finite():
        return None
    if formato in ('data', 'data_hora'):
        if number < 0 or number > 2958465:
            return None
        base = _dt.datetime(1904, 1, 1) if data1904 else _dt.datetime(1899, 12, 30)
        if not data1904 and number < 61:
            base = _dt.datetime(1899, 12, 31)  # Excel's 1900 leap-year bug only shifts serials >= 61
            if number == 60:
                return None
        moment = base + _dt.timedelta(seconds=round(float(number) * 86400))
        return moment.date().isoformat() if formato == 'data' else moment.strftime('%Y-%m-%d %H:%M:%S')
    percent = formato.endswith('%')
    if percent:
        number *= 100
    decimals = len(formato.split('.', 1)[1].rstrip('%')) if '.' in formato else 0
    quantized = number.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_EVEN)
    text = f'{quantized:,.{decimals}f}' if formato.startswith('#,##') else f'{quantized:.{decimals}f}'
    return text + ('%' if percent else '')


def _strings_compartilhadas(pacote: _Pacote) -> list:
    parte = 'xl/sharedStrings.xml'
    if not pacote.existe(parte):
        return []
    result = []
    for si in pacote.xml(parte):
        if _local(si.tag) != 'si':
            continue
        pieces = []

        def walk(node):
            for child in node:
                name = _local(child.tag)
                if name == 'rPh':
                    continue  # phonetic guide, not displayed text
                if name == 't':
                    pieces.append(child.text or '')
                else:
                    walk(child)
        walk(si)
        result.append(''.join(pieces))
    return result


def ler_xlsx(source: Path, *, limite_total=None, limite_membro=None) -> dict:
    """Return {'abas': [{'nome', 'tipo', 'oculta', 'celulas': [...]}], 'contagens', 'avisos', 'falhas'}."""
    limite_total = limite_total or LIMITE_DESCOMPACTADO_TOTAL
    limite_membro = limite_membro or LIMITE_DESCOMPACTADO_MEMBRO
    with _Pacote(source, limite_total, limite_membro) as pacote:
        _verificar_macro(pacote)
        principal = 'xl/workbook.xml'
        if not pacote.existe(principal):
            raise Recusa('corrompido', 'Pacote sem xl/workbook.xml; não é um XLSX legível.')
        workbook = pacote.xml(principal)
        props = _filho(workbook, 'workbookPr')
        data1904 = props is not None and _attr(props, 'date1904') in ('1', 'true')
        sheets_node = _filho(workbook, 'sheets')
        if sheets_node is None:
            raise Recusa('corrompido', 'xl/workbook.xml sem lista de abas.')
        rels = _relacoes(pacote, principal)
        strings = _strings_compartilhadas(pacote)
        formatos = _formatos(pacote)
        avisos, falhas, abas = [], [], []
        total = formulas_total = 0
        if _filho(workbook, 'workbookProtection') is not None:
            avisos.append('Pasta de trabalho com proteção de estrutura; a leitura das células não foi afetada.')
        for sheet in _filhos(sheets_node, 'sheet'):
            nome = _attr(sheet, 'name', '?')
            tipo_rel, parte = rels.get(_attr(sheet, 'id'), (None, None))
            aba = {'nome': nome, 'tipo': 'planilha', 'oculta': _attr(sheet, 'state', 'visible') != 'visible',
                   'celulas': []}
            abas.append(aba)
            if tipo_rel == 'chartsheet':
                aba['tipo'] = 'grafico'
                continue
            if not parte or not pacote.existe(parte):
                falhas.append({'aba': nome, 'erro': 'Parte da aba ausente no pacote.'})
                continue
            try:
                raiz = pacote.xml(parte)
            except Recusa as exc:
                if exc.motivo == 'limite':
                    raise
                falhas.append({'aba': nome, 'erro': str(exc)})
                continue
            if _filho(raiz, 'sheetProtection') is not None:
                avisos.append(f'Aba {nome} com proteção de edição; a leitura das células não foi afetada.')
            data = _filho(raiz, 'sheetData')
            for row in (_filhos(data, 'row') if data is not None else []):
                for cell in _filhos(row, 'c'):
                    ref = (_attr(cell, 'r') or '').upper()
                    if not _CELULA.fullmatch(ref):
                        falhas.append({'aba': nome, 'erro': f'Célula sem referência válida ({ref or "vazia"}); ignorada.'})
                        continue
                    kind = _attr(cell, 't', 'n')
                    v = _filho(cell, 'v')
                    f = _filho(cell, 'f')
                    raw = v.text if v is not None and v.text is not None else None
                    if kind == 'inlineStr':
                        inline = _filho(cell, 'is')
                        raw = ''.join(t.text or '' for t in inline.iter() if _local(t.tag) == 't') if inline is not None else None
                        kind = 'texto'
                    elif kind == 's' and raw is not None:
                        try:
                            raw = strings[int(raw)]
                        except (ValueError, IndexError):
                            falhas.append({'aba': nome, 'celula': ref, 'erro': 'Índice de texto compartilhado inválido.'})
                            continue
                        kind = 'texto'
                    elif kind == 'str':
                        kind = 'texto'
                    elif kind == 'b' and raw is not None:
                        raw, kind = ('TRUE' if raw.strip() == '1' else 'FALSE'), 'booleano'
                    elif kind == 'e':
                        kind = 'erro'
                    elif kind == 'd':
                        kind = 'data'
                    else:
                        kind = 'numero'
                    formula = None
                    if f is not None:
                        if f.text:
                            formula = '=' + f.text
                        elif _attr(f, 't') == 'shared':
                            formula = f'(fórmula compartilhada si={_attr(f, "si", "?")})'
                    if (raw is None or raw == '') and formula is None:
                        continue
                    exibido = None
                    if kind == 'numero' and raw is not None:
                        try:
                            style = int(_attr(cell, 's', '0'))
                        except ValueError:
                            style = 0
                        formato = formatos[style] if 0 <= style < len(formatos) else None
                        exibido = _exibir(raw, formato, data1904)
                    total += 1
                    if total > LIMITE_CELULAS:
                        raise Recusa('limite', f'Planilha com mais de {LIMITE_CELULAS} células preenchidas.')
                    formulas_total += formula is not None
                    aba['celulas'].append({'celula': ref, 'localizador': referencia_celula(nome, ref),
                                           'tipo': kind, 'valor': raw, 'exibido': exibido, 'formula': formula})
    contagens = {'abas': len(abas), 'celulas': total, 'formulas': formulas_total}
    return {'abas': abas, 'contagens': contagens, 'avisos': avisos, 'falhas': falhas}


# ---------------------------------------------------------------- derived working copy

def _linha_celula(cell) -> str:
    def clean(text):
        return (text or '').replace('\r', ' ').replace('\n', ' ⏎ ')
    parts = [clean(cell['valor']) if cell['valor'] is not None else '(sem valor gravado)']
    if cell['exibido'] is not None and cell['exibido'] != cell['valor']:
        parts.append(f'exibido: {cell["exibido"]}')
    if cell['formula']:
        parts.append(f'formula: {clean(cell["formula"])}')
    return f'[{cell["localizador"]}] ' + ' || '.join(parts)


def _metodo(formato: str) -> str:
    base = f'extrair_office {VERSAO_EXTRATOR}; zipfile + xml.etree da biblioteca padrao'
    if formato == 'docx':
        return f'{base}; paragrafos e celulas de tabela em ordem; sem OCR, sem avaliacao ou correcao editorial.'
    return f'{base}; celulas preenchidas com valor gravado e formula como texto, sem avaliar; sem correcao editorial.'


def _resultado_base(formato: str) -> dict:
    return {'estado': 'erro', 'formato': formato, 'origem': f'extracao_{formato}',
            'versao_extrator': VERSAO_EXTRATOR, 'metodo': _metodo(formato), 'recusa': None,
            'mensagem': None, 'contagens': {}, 'abas': [], 'falhas': [], 'avisos': [],
            'conferencia_humana': 'nao_realizada'}


def extrair_office(source: Path, identifier: str, target: Path, *,
                   limite_total=None, limite_membro=None) -> dict:
    """Write the located working copy of a DOCX/XLSX and return an explicit outcome.

    Refusals (macro, protected, corrupted, over limits) return `estado: erro` with a
    readable `mensagem` and write nothing; the original is never touched. A failed
    write of the derived file still raises, as for PDF.
    """
    source, target = Path(source), Path(target)
    if target.exists():
        raise FileExistsError('Nao sobrescrever extracao existente; usar nova versao.')
    suffix = source.suffix.lower()
    formato = EXTENSOES.get(suffix) or ('xlsx' if suffix.startswith('.xl') else 'docx')
    result = _resultado_base(formato)
    if suffix in EXTENSOES_MACRO:
        result.update(recusa='macro', mensagem=f'Formato {suffix} habilitado para macros; conteúdo não extraído por segurança. O original fica preservado.')
        return result
    if suffix not in EXTENSOES:
        result.update(recusa='formato', mensagem=f'Formato {suffix or "sem extensão"} sem extrator Office.')
        return result
    try:
        lido = (ler_docx if formato == 'docx' else ler_xlsx)(source, limite_total=limite_total, limite_membro=limite_membro)
    except Recusa as exc:
        result.update(recusa=exc.motivo, mensagem=f'{exc} O original fica preservado.')
        return result
    except Exception as exc:  # reading only: an unexpected package shape is a readable pending outcome
        if not source.is_file():
            raise
        result.update(recusa='corrompido',
                      mensagem=f'Leitura interrompida ({type(exc).__name__}: {str(exc)[:500]}). O original fica preservado.')
        return result

    result['contagens'] = lido['contagens']
    result['falhas'] = lido['falhas']
    result['avisos'] = lido['avisos']
    body = []
    if formato == 'docx':
        unidades = 0
        for secao in lido['secoes']:
            if not secao['unidades'] and secao['titulo'] != 'documento':
                continue
            body.extend([f'## {identifier} - {secao["titulo"]}', ''])
            for unit in secao['unidades']:
                body.append(f'[{unit["localizador"]}] {unit["texto"]}')
                unidades += 1
            if not secao['unidades']:
                body.append(SEM_TEXTO)
            body.append('')
        tem_texto = unidades > 0
    else:
        result['abas'] = [{'nome': a['nome'], 'tipo': a['tipo'], 'oculta': a['oculta'],
                           'celulas': len(a['celulas']),
                           'formulas': sum(1 for c in a['celulas'] if c['formula'])} for a in lido['abas']]
        for aba in lido['abas']:
            body.extend([f'## {identifier} - aba {aba["nome"]}', ''])
            if aba['oculta']:
                body.append('[aba oculta no original]')
            if aba['tipo'] == 'grafico':
                body.append('[aba de grafico; sem celulas]')
            body.extend(_linha_celula(cell) for cell in aba['celulas'])
            if not aba['celulas'] and aba['tipo'] != 'grafico':
                body.append('[ABA SEM CELULAS PREENCHIDAS]')
            body.append('')
        tem_texto = lido['contagens']['celulas'] > 0
    if result['falhas']:
        result['estado'] = 'parcial' if tem_texto else 'erro'
        result['mensagem'] = f'{len(result["falhas"])} falha(s) de leitura; conferir o original.'
    else:
        result['estado'] = 'extraido' if tem_texto else 'sem_texto'

    header = [f'# {identifier} - copia textual de trabalho', '',
              f'Original: {source.name}', f'SHA-256 do original: {sha256(source)}',
              f'Formato: {formato}', f'Origem: extracao_{formato}',
              f'Metodo: {result["metodo"]}']
    if formato == 'docx':
        header.append('Localizadores: P = n-esimo paragrafo com texto da secao (vazios nao contam); '
                      f'T L C = tabela, linha e coluna da grade; paragrafos dentro da celula unidos por "{SEPARADOR_PARAGRAFOS_CELULA.strip()}".')
    else:
        header.append('Localizadores: Aba!A1. Valor = conteudo gravado no arquivo; exibido = formato numerico simples '
                      '(separadores do codigo de formato, nao da localidade); formulas como texto, nao avaliadas.')
    header.extend([f'Aviso: {aviso}' for aviso in result['avisos']])
    header.extend(['Copia de trabalho, nao o original; conferir o original antes de usar como evidencia.', ''])
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write('\n'.join(header + body))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--arquivo', required=True, help='DOCX ou XLSX.')
    parser.add_argument('--id', required=True)
    parser.add_argument('--saida', required=True)
    args = parser.parse_args()
    result = extrair_office(Path(args.arquivo), args.id, Path(args.saida))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result['estado'] == 'erro' else 0


if __name__ == '__main__':
    raise SystemExit(main())
