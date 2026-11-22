"""Rebuildable SQLite/FTS5 indexes of authorized round snapshots. No inference/network."""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import uuid

import unicodedata

from comum import dentro, escrever_json, ler_json, sha256, pasta_preparacao
from comum import documentos_e_capturas  # no network code: keeps the portable banco.py copy working

# Copies of the working-copy markers, so banco.py + indice_sqlite.py + comum.py stay a
# portable set; testes/test_extrair_office.py checks they match extrair_office and ocr.
MARCADORES_OFFICE = frozenset({'[SEM TEXTO EXTRAIVEL NESTE DOCUMENTO]', '[ABA SEM CELULAS PREENCHIDAS]',
                               '[aba oculta no original]', '[aba de grafico; sem celulas]'})
SEM_TEXTO_IMAGEM = '[SEM TEXTO RECONHECIDO NA IMAGEM]'
AVISO_OCR_IMAGEM = ('Texto de reconhecimento automatico (OCR), sujeito a erros; '
                    'conferir no original antes de usar como evidencia.')

ESQUEMA = 1
IMPLEMENTACAO = '1.0.0'
# REGRAS and IMPLEMENTACAO enter every index identity: changing them would make every
# existing round's index unverifiable. DOCX/XLSX/image-OCR adapters below only apply to
# derivatives that did not exist before, so PDF and plain-text indexing is unchanged.
REGRAS = {'adaptadores': 'texto_utf8_e_markdown_paginado_v1',
          'linhas_por_trecho': 40, 'sobreposicao_linhas': 4,
          'tokenizador': 'unicode61 remove_diacritics 2'}
ADAPTADORES_OFFICE = {'docx': 'markdown_docx_v1', 'xlsx': 'markdown_xlsx_v1'}
ADAPTADOR_OCR_IMAGEM = 'markdown_ocr_imagem_v1'
SECAO = re.compile(r'^## ([A-Za-z0-9_-]+) - (.+)$')
LOCALIZADOR_DOCX = re.compile(r'^\[((?:(?:CAB|ROD)[0-9]+ |(?:NOTA|NOTAFIM|COMENT) [^\s\[\]]+ )?P[0-9]{4,}'
                              r'|T[0-9]{2,} L[0-9]{2,} C[0-9]{2,})\](?: (.*))?$')
LOCALIZADOR_XLSX = re.compile(r"^\[((?:[A-Za-z_][A-Za-z0-9_.]*|'(?:[^']|'')+')![A-Z]{1,3}[1-9][0-9]*)\](?: (.*))?$")
ID_CASO = r'[a-z0-9][a-z0-9_-]{0,63}'
ID_RODADA = r'R[0-9]{3,6}'
ID_GERACAO = r'[a-z0-9][a-z0-9_-]{0,31}'
ID_DOCUMENTO = r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}'
PAGINA = re.compile(r'^## ([A-Za-z0-9_-]+) - pagina PDF ([1-9][0-9]*)$')
LINHA = re.compile(r'^\[L([0-9]{4,})\] ?(.*)$')
SEM_TEXTO = '[SEM TEXTO EXTRAIVEL NESTA PAGINA]'
ERRO_TEXTO = '[ERRO DE EXTRACAO NESTA PAGINA]'

DDL = '''
PRAGMA user_version=1;
CREATE TABLE metadados (chave TEXT PRIMARY KEY, valor TEXT NOT NULL);
CREATE TABLE documentos (
 documento_id TEXT PRIMARY KEY, arquivo TEXT NOT NULL UNIQUE,
 sha256 TEXT NOT NULL, nome TEXT NOT NULL, origem TEXT
);
CREATE TABLE fontes (
 fonte_id TEXT PRIMARY KEY, documento_id TEXT NOT NULL REFERENCES documentos,
 arquivo TEXT NOT NULL UNIQUE, sha256 TEXT NOT NULL,
 tipo TEXT NOT NULL CHECK(tipo IN ('original','derivado')),
 metodo TEXT NOT NULL, adaptador TEXT NOT NULL
);
CREATE TABLE unidades (
 unidade_id INTEGER PRIMARY KEY, fonte_id TEXT NOT NULL REFERENCES fontes,
 ordem INTEGER NOT NULL, pagina_pdf INTEGER CHECK(pagina_pdf > 0),
 linhas_json TEXT NOT NULL, estado TEXT NOT NULL, motivo TEXT,
 UNIQUE(fonte_id, ordem)
);
CREATE TABLE trechos (
 trecho_id INTEGER PRIMARY KEY, referencia TEXT NOT NULL UNIQUE,
 unidade_id INTEGER NOT NULL REFERENCES unidades,
 linha_inicio INTEGER NOT NULL CHECK(linha_inicio > 0),
 linha_fim INTEGER NOT NULL CHECK(linha_fim >= linha_inicio), texto TEXT NOT NULL
);
CREATE INDEX trechos_unidade ON trechos(unidade_id);
CREATE INDEX unidades_fonte ON unidades(fonte_id);
CREATE VIRTUAL TABLE trechos_fts USING fts5(texto,
 tokenize='unicode61 remove_diacritics 2');
'''


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _identidade(value):
    return hashlib.sha256(_json(value).encode('utf-8')).hexdigest()


def _validar_ids(caso, rodada, geracao='v1'):
    for value, pattern, name in ((caso, ID_CASO, 'caso'),
                                 (rodada, ID_RODADA, 'rodada'),
                                 (geracao, ID_GERACAO, 'geracao')):
        if not isinstance(value, str) or not re.fullmatch(pattern, value):
            raise ValueError(f'Identificador de {name} invalido.')


def caminho_rodada(root: Path, caso: str, rodada: str) -> Path:
    _validar_ids(caso, rodada)
    run = dentro(root, f'execucoes/{caso}/{rodada}')
    if not run.is_dir():
        raise ValueError('Rodada inexistente; nao criar nem selecionar caso automaticamente.')
    return run


def _caminho_caso(relative, caso):
    path = Path(relative)
    if path.drive or path.is_absolute() or '..' in path.parts or path.parts[:2] != ('casos', caso):
        raise ValueError(f'Arquivo nao pertence ao caso {caso}: {relative}')
    return path.as_posix()


def _entradas(run: Path, caso: str, rodada: str):
    """Use frozen authorization only; never consult a live manifest or inactive case."""
    _validar_ids(caso, rodada)
    record = ler_json(dentro(run, 'registro.json'))
    if record.get('caso_id') != caso or record.get('rodada') != rodada:
        raise ValueError('Caso/rodada divergem do registro congelado.')
    frozen = ler_json(dentro(run, 'snapshot.json'))
    hashes = {}
    for item in frozen:
        relative = item['arquivo']
        dentro(run, relative)
        normalized = Path(relative).as_posix()
        if normalized in hashes:
            raise ValueError('Caminho duplicado no snapshot.')
        hashes[normalized] = item['sha256']

    def conferir(relative):
        path = dentro(run, relative)
        if relative not in hashes or not path.is_file() or sha256(path) != hashes[relative]:
            raise ValueError(f'Arquivo nao congelado, ausente ou hash divergente: {relative}')
        return path

    config = ler_json(conferir('entradas/configuracao.json'))
    if config.get('caso_ativo') != caso:
        raise ValueError('Caso diverge da configuracao congelada.')
    relative = _caminho_caso(config.get('manifesto_ativo') or '', caso)
    manifest_path = conferir(f'entradas/{relative}')
    manifest = ler_json(manifest_path)
    if manifest.get('caso_id') != caso:
        raise ValueError('Caso diverge do manifesto congelado.')
    if not manifest.get('documentos'):
        raise ValueError('Manifesto documental vazio.')
    documents = documentos_e_capturas(manifest)
    sources, identifiers, paths = [], set(), set()
    for document in documents:
        identifier = document['id']
        if not re.fullmatch(ID_DOCUMENTO, identifier) or identifier in identifiers:
            raise ValueError('ID documental invalido ou repetido.')
        identifiers.add(identifier)
        for number, item in enumerate([document, *document.get('derivados', [])]):
            relative = _caminho_caso(item['arquivo'], caso)
            if relative in paths:
                raise ValueError('Arquivo repetido no manifesto.')
            paths.add(relative)
            path = conferir(f'entradas/{relative}')
            if item['sha256'] != hashes[f'entradas/{relative}']:
                raise ValueError(f'Hash do manifesto diverge do snapshot: {relative}')
            sources.append({'documento_id': identifier, 'arquivo': relative,
                            'sha256': item['sha256'], 'tipo': 'original' if number == 0 else 'derivado',
                            'metodo_informado': item.get('metodo') or item.get('metodo_extracao')})
    sources.sort(key=lambda x: (x['documento_id'], x['arquivo']))
    descriptor = {'esquema': ESQUEMA, 'implementacao': IMPLEMENTACAO,
                  'caso_id': caso, 'rodada': rodada, 'regras': REGRAS,
                  'snapshot_sha256': sha256(run / 'snapshot.json'),
                  'manifesto_sha256': sha256(manifest_path), 'fontes': sources}
    return manifest, descriptor


def _unidade(ordem, pagina, linhas, estado=None, motivo=None):
    has_text = any(text.strip() for _, text in linhas)
    return {'ordem': ordem, 'pagina_pdf': pagina, 'linhas': linhas,
            'estado': estado or ('com_texto' if has_text else 'sem_texto'),
            'motivo': motivo or (None if has_text else 'Sem texto pesquisavel nesta unidade.')}


def _adaptar(path: Path, document_id: str, original_hash: str, tipo: str):
    """Keep source line numbers; never OCR or invent PDF page positions."""
    if path.suffix.lower() not in ('.txt', '.md'):
        return 'nao_suportado', 'nao_informado', [
            _unidade(1, None, [], 'nao_suportado', 'Formato sem adaptador textual; usar original ou derivado autorizado.')]
    try:
        content = path.read_text(encoding='utf-8-sig')
    except UnicodeError:
        return 'utf8', 'nao_informado', [_unidade(1, None, [], 'erro_leitura', 'Texto nao e UTF-8 valido.')]
    lines = content.splitlines()
    # Only derivatives with an explicit work-copy header are treated as extracted pages.
    paginated = tipo == 'derivado' and bool(lines) and lines[0] == f'# {document_id} - copia textual de trabalho'
    if not paginated:
        method = 'Leitura direta de texto UTF-8' if tipo == 'original' else 'Leitura UTF-8; metodo de origem nao informado'
        return 'texto_linhas_v1', method, [
            _unidade(1, None, list(enumerate(lines, 1)))]
    header = lines[:next((i for i, line in enumerate(lines) if line.startswith('## ')), len(lines))]
    declared_format = next((line.removeprefix('Formato: ') for line in header if line.startswith('Formato: ')), None)
    if declared_format in ADAPTADORES_OFFICE or declared_format == 'imagem':
        return _adaptar_secoes(lines, header, document_id, original_hash, declared_format)
    units, buffer, page, empty, failed = [], [], None, False, False
    method = next((line.removeprefix('Metodo: ') for line in lines if line.startswith('Metodo: ')), 'nao_informado')
    declared_hash = next((line.removeprefix('SHA-256 do PDF: ') for line in lines if line.startswith('SHA-256 do PDF: ')), None)

    def finish():
        if page is not None:
            units.append(_unidade(len(units) + 1, page, buffer.copy(),
                                  'erro_leitura' if failed else None,
                                  'Erro de extracao nesta pagina; conferir o original e o recibo.' if failed else None))

    try:
        if declared_hash != original_hash:
            raise ValueError('Hash de origem ausente ou divergente no derivado paginado.')
        for line in lines:
            match = PAGINA.fullmatch(line)
            if match:
                finish()
                if match[1] != document_id or int(match[2]) != len(units) + 1:
                    raise ValueError('Cabecalho de pagina incoerente ou paginas fora de sequencia.')
                page, buffer, empty, failed = int(match[2]), [], False, False
            elif page is not None:
                if line == SEM_TEXTO:
                    empty = True
                elif line == ERRO_TEXTO:
                    failed = True
                elif line:
                    match = LINHA.fullmatch(line)
                    if not match or int(match[1]) != len(buffer) + 1:
                        raise ValueError('Linha sem localizador valido no derivado paginado.')
                    buffer.append((int(match[1]), match[2]))
                if (empty or failed) and any(text.strip() for _, text in buffer):
                    raise ValueError('Pagina marcada sem texto ou com erro contem texto nao vazio.')
        finish()
        if not units:
            raise ValueError('Derivado paginado sem paginas reconhecidas.')
    except ValueError as exc:
        return 'markdown_paginado_v1', method, [_unidade(1, None, [], 'erro_leitura', str(exc))]
    return 'markdown_paginado_v1', method, units


def _aba_do_localizador(locator):
    sheet = locator.rsplit('!', 1)[0]
    return sheet[1:-1].replace("''", "'") if sheet.startswith("'") else sheet


def _adaptar_secoes(lines, header, document_id, original_hash, kind):
    """DOCX/XLSX/image-OCR working copies: one unit per `## ID - <section>` block.

    Each content line keeps its source locator (`[P0001]`, `[T01 L02 C03]`, `[Aba!B3]`,
    `[L0001]`) in the indexed text and is numbered 1..n inside its unit. Informational
    markers are not content. Any incoherence makes the whole source unreadable rather
    than indexing doubtful locators.
    """
    adapter = ADAPTADORES_OFFICE.get(kind, ADAPTADOR_OCR_IMAGEM)
    method = next((line.removeprefix('Metodo: ') for line in header if line.startswith('Metodo: ')), 'nao_informado')
    declared_hash = next((line.removeprefix('SHA-256 do original: ') for line in header
                          if line.startswith('SHA-256 do original: ')), None)
    pattern = {'docx': LOCALIZADOR_DOCX, 'xlsx': LOCALIZADOR_XLSX}.get(kind, LINHA)
    markers = MARCADORES_OFFICE if kind in ADAPTADORES_OFFICE else {SEM_TEXTO_IMAGEM}
    sections = []
    try:
        if declared_hash != original_hash:
            raise ValueError('Hash de origem ausente ou divergente no derivado.')
        for line in lines[len(header):]:
            match = SECAO.fullmatch(line)
            if match:
                if match[1] != document_id:
                    raise ValueError('Cabecalho de secao de outro documento.')
                title = match[2]
                if kind == 'xlsx' and not title.startswith('aba '):
                    raise ValueError('Secao de planilha sem aba identificada.')
                if kind == 'imagem' and (title != 'imagem' or sections):
                    raise ValueError('Derivado de OCR de imagem com secao inesperada.')
                sections.append((title, []))
            elif not line or line in markers:
                continue
            elif not sections:
                raise ValueError('Conteudo antes da primeira secao.')
            else:
                found = pattern.fullmatch(line)
                if not found:
                    raise ValueError('Linha sem localizador valido no derivado.')
                buffer = sections[-1][1]
                if kind == 'xlsx' and _aba_do_localizador(found[1]) != sections[-1][0].removeprefix('aba '):
                    raise ValueError('Celula citada em aba diferente da secao.')
                if kind == 'imagem':
                    if int(found[1]) != len(buffer) + 1:
                        raise ValueError('Linhas do OCR fora de sequencia.')
                    buffer.append((len(buffer) + 1, found[2]))
                else:
                    buffer.append((len(buffer) + 1, line))
        if not sections:
            raise ValueError('Derivado sem secoes reconhecidas.')
    except ValueError as exc:
        return adapter, method, [_unidade(1, None, [], 'erro_leitura', str(exc))]
    return adapter, method, [_unidade(number, None, buffer) for number, (_, buffer) in enumerate(sections, 1)]


def _localizadores(adapter, linhas, start, end):
    """(locator, text) of each Office line in a block; None for other adapters."""
    pattern = {'markdown_docx_v1': LOCALIZADOR_DOCX, 'markdown_xlsx_v1': LOCALIZADOR_XLSX}.get(adapter)
    if not pattern:
        return None
    found = [pattern.fullmatch(text) for number, text in linhas if start <= number <= end]
    return [(m[1], m[2] or '') for m in found if m]


def _normalizar(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text.casefold()) if not unicodedata.combining(c))


def _partes(lines):
    size = REGRAS['linhas_por_trecho']
    step = size - REGRAS['sobreposicao_linhas']
    for start in range(0, len(lines), step):
        block = lines[start:start + size]
        if any(text.strip() for _, text in block):
            yield block
        if start + size >= len(lines):
            break


def _validar_banco(con):
    if con.execute('PRAGMA user_version').fetchone()[0] != ESQUEMA:
        raise ValueError('Versao de esquema SQLite desconhecida.')
    if con.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
        raise ValueError('Integridade SQLite reprovada.')
    if con.execute('PRAGMA foreign_key_check').fetchone():
        raise ValueError('Relacionamentos SQLite invalidos.')
    mismatch = con.execute('''
      SELECT 1 FROM trechos t LEFT JOIN trechos_fts f ON f.rowid=t.trecho_id
      WHERE f.rowid IS NULL OR f.texto != t.texto
      UNION ALL
      SELECT 1 FROM trechos_fts f LEFT JOIN trechos t ON t.trecho_id=f.rowid
      WHERE t.trecho_id IS NULL LIMIT 1''').fetchone()
    if mismatch:
        raise ValueError('FTS e trechos divergentes.')


def construir_snapshot(run: Path, caso: str, rodada: str, geracao='v1') -> dict:
    """Called before publishing a new round, or explicitly on an existing snapshot."""
    _validar_ids(caso, rodada, geracao)
    manifest, descriptor = _entradas(run, caso, rodada)
    destination = dentro(run, f'indice/{geracao}')
    if destination.exists():
        raise FileExistsError('Geracao de indice ja existe; preservar e escolher outra geracao.')
    with pasta_preparacao(run, '.indice_') as staging:
        work = Path(staging) / geracao
        work.mkdir()
        db = work / 'apuracao.sqlite'
        with closing(sqlite3.connect(db)) as con:
            con.execute('PRAGMA foreign_keys=ON')
            if con.execute('PRAGMA foreign_keys').fetchone()[0] != 1:
                raise ValueError('SQLite sem suporte ativo a chaves estrangeiras.')
            con.executescript(DDL)
            with con:
                con.execute('INSERT INTO metadados VALUES (?,?)', ('descriptor', _json(descriptor)))
                documents = documentos_e_capturas(manifest)
                for document in sorted(documents, key=lambda x: x['id']):
                    con.execute('INSERT INTO documentos VALUES (?,?,?,?,?)',
                                (document['id'], Path(document['arquivo']).as_posix(), document['sha256'],
                                 document.get('nome_recebido') or Path(document['arquivo']).name,
                                 _json(document.get('origem_informada'))))
                for source in descriptor['fontes']:
                    path = dentro(run, f"entradas/{source['arquivo']}")
                    document = next(x for x in documents if x['id'] == source['documento_id'])
                    adapter, method, units = _adaptar(path, document['id'], document['sha256'], source['tipo'])
                    source_id = _identidade(source)
                    con.execute('INSERT INTO fontes VALUES (?,?,?,?,?,?,?)',
                                (source_id, document['id'], source['arquivo'], source['sha256'],
                                 source['tipo'], source['metodo_informado'] or method, adapter))
                    for unit in units:
                        cursor = con.execute('''INSERT INTO unidades
                          (fonte_id,ordem,pagina_pdf,linhas_json,estado,motivo) VALUES (?,?,?,?,?,?)''',
                          (source_id, unit['ordem'], unit['pagina_pdf'], _json(unit['linhas']),
                           unit['estado'], unit['motivo']))
                        unit_id = cursor.lastrowid
                        if unit['estado'] != 'com_texto':
                            continue
                        for block in _partes(unit['linhas']):
                            reference = _identidade([caso, document['id'], document['sha256'],
                                                    source['sha256'], source['arquivo'], adapter,
                                                    unit['ordem'], block[0][0], block[-1][0], IMPLEMENTACAO])
                            text = '\n'.join(text for _, text in block)
                            cursor = con.execute('''INSERT INTO trechos
                              (referencia,unidade_id,linha_inicio,linha_fim,texto) VALUES (?,?,?,?,?)''',
                              (reference, unit_id, block[0][0], block[-1][0], text))
                            con.execute('INSERT INTO trechos_fts(rowid,texto) VALUES (?,?)', (cursor.lastrowid, text))
                con.execute("INSERT INTO trechos_fts(trechos_fts) VALUES ('integrity-check')")
            _validar_banco(con)
            coverage = _cobertura(con)
        # Refuse a source changed during construction; publish only after closing SQLite.
        if _entradas(run, caso, rodada)[1] != descriptor:
            raise ValueError('Entradas alteradas durante a construcao.')
        index_manifest = {'esquema': ESQUEMA, 'geracao': geracao, 'descriptor': descriptor,
                          'indice_id': _identidade(descriptor), 'banco_sha256': sha256(db),
                          'criado_em_utc': datetime.now(timezone.utc).isoformat(),
                          'sqlite_construcao': sqlite3.sqlite_version, 'cobertura': coverage}
        escrever_json(work / 'manifesto.json', index_manifest, exclusivo=True)
        destination.parent.mkdir(exist_ok=True)
        work.rename(destination)
    return index_manifest


def construir_indice(root: Path, caso: str, rodada: str, geracao='v1') -> dict:
    return construir_snapshot(caminho_rodada(root, caso, rodada), caso, rodada, geracao)


def _abrir(run: Path, caso, rodada, geracao):
    _validar_ids(caso, rodada, geracao)
    _, expected = _entradas(run, caso, rodada)
    folder = dentro(run, f'indice/{geracao}')
    db = dentro(folder, 'apuracao.sqlite')
    if not db.is_file() or not (folder / 'manifesto.json').is_file():
        raise ValueError('Indice inexistente; construir explicitamente a geracao solicitada.')
    manifest = ler_json(dentro(folder, 'manifesto.json'))
    if (manifest.get('esquema') != ESQUEMA or manifest.get('geracao') != geracao
            or manifest.get('descriptor') != expected or manifest.get('indice_id') != _identidade(expected)):
        raise ValueError('Indice pertence a outro caso/rodada ou a outras entradas/regras.')
    if sha256(db) != manifest.get('banco_sha256'):
        raise ValueError('Hash do banco divergente; preservar o artefato e investigar.')
    con = sqlite3.connect(db.resolve().as_uri() + '?mode=ro', uri=True)
    try:
        descriptor = con.execute('SELECT valor FROM metadados WHERE chave=?', ('descriptor',)).fetchone()
        if not descriptor or json.loads(descriptor[0]) != expected:
            raise ValueError('Metadados internos do banco divergentes.')
        if con.execute('PRAGMA user_version').fetchone()[0] != ESQUEMA:
            raise ValueError('Versao de esquema SQLite desconhecida.')
    except Exception:
        con.close()
        raise
    return con, manifest


def _cobertura(con):
    documents = []
    for document_id, name in con.execute('SELECT documento_id,nome FROM documentos ORDER BY documento_id'):
        sources = []
        for source_id, file, kind, method, adapter in con.execute('''
          SELECT fonte_id,arquivo,tipo,metodo,adaptador FROM fontes WHERE documento_id=? ORDER BY arquivo''', (document_id,)):
            units = [{'ordem': order, 'pagina_pdf': page, 'estado': state, 'motivo': reason,
                      'trechos': count}
                     for order, page, state, reason, count in con.execute('''
                       SELECT u.ordem,u.pagina_pdf,u.estado,u.motivo,count(t.trecho_id)
                       FROM unidades u LEFT JOIN trechos t USING(unidade_id)
                       WHERE u.fonte_id=? GROUP BY u.unidade_id ORDER BY u.ordem''', (source_id,))]
            sources.append({'arquivo': file, 'tipo': kind, 'metodo': method,
                            'adaptador': adapter, 'unidades': units})
        documents.append({'documento_id': document_id, 'nome_documento': name, 'fontes': sources,
                          'pesquisavel': any(u['trechos'] > 0 for f in sources for u in f['unidades'])})
    return {'documentos': documents, 'documentos_pesquisaveis': sum(d['pesquisavel'] for d in documents),
            'total_documentos': len(documents),
            'aviso': 'Cobertura de texto extraido; nao comprova leitura visual, fidelidade ou ausencia no acervo.'}


# SEG-06: teto do registro bruto das consultas, por rodada. Cada consulta (busca, leitura de contexto, cobertura) grava um JSON
# novo em saidas/consultas_sqlite/ da rodada; sem teto, uma rodada com milhares de consultas encheria o volume de dados.
#
# Decisão: o texto da consulta e as passagens devolvidas CONTINUAM no registro bruto. Ele mora dentro da pasta da rodada do caso,
# com o mesmo acesso, o mesmo backup e o mesmo ciclo de vida do caso (sai junto quando o caso é apagado), é o registro editorial
# das consultas que o AGENTS.md manda preservar e nunca vai para um registro global (o registro de auditoria da Mesa não vê a
# busca). Amostrar ou apagar os mais antigos quebraria essa garantia (cada resultado tem um registro bruto); por isso o desenho é
# o teto: passado ele, a consulta é recusada com mensagem clara, nada é apagado e o registro já feito fica preservado.
# Variáveis: VLADO_CONSULTAS_MAX_ARQUIVOS (padrão 2000) e VLADO_CONSULTAS_MAX_MB (padrão 256), por rodada.
TETO_ARQUIVOS_PADRAO = 2000
TETO_MB_PADRAO = 256


def _teto(nome: str, padrao: int, maximo: int) -> int:
    bruto = os.environ.get(nome, '').strip()
    if not bruto:
        return padrao
    try:
        return max(1, min(maximo, int(bruto)))
    except ValueError as exc:
        raise ValueError(f'{nome} deve ser um número inteiro.') from exc


def _conferir_teto_do_registro(pasta: Path) -> None:
    """Recusa uma consulta nova quando a rodada já guarda arquivos demais ou bytes demais de registro bruto."""
    maximo_arquivos = _teto('VLADO_CONSULTAS_MAX_ARQUIVOS', TETO_ARQUIVOS_PADRAO, 10_000_000)
    maximo_mb = _teto('VLADO_CONSULTAS_MAX_MB', TETO_MB_PADRAO, 1_048_576)
    arquivos = total = 0
    try:
        with os.scandir(pasta) as itens:
            for item in itens:
                if item.is_file(follow_symlinks=False):
                    arquivos += 1
                    total += item.stat(follow_symlinks=False).st_size
    except FileNotFoundError:
        return
    if arquivos >= maximo_arquivos or total >= maximo_mb << 20:
        raise ValueError(f'Teto do registro de consultas desta rodada atingido ({arquivos} arquivos, {total >> 20} MB; limite '
                         f'{maximo_arquivos} arquivos ou {maximo_mb} MB). Abra uma nova rodada para continuar consultando; o '
                         'registro bruto das consultas anteriores foi preservado.')


def _salvar_log(run, result):
    _conferir_teto_do_registro(dentro(run, 'saidas/consultas_sqlite'))
    relative = f'saidas/consultas_sqlite/{uuid.uuid4().hex}.json'
    result['arquivo_log'] = relative
    result['executada_em_utc'] = datetime.now(timezone.utc).isoformat()
    result['ferramenta'] = 'scripts/banco.py'
    result['sqlite_consulta'] = sqlite3.sqlite_version
    escrever_json(dentro(run, relative), result, exclusivo=True)
    return result


def _base(manifest, operation):
    return {'operacao': operation, 'estado': 'ok', 'caso_id': manifest['descriptor']['caso_id'],
            'rodada': manifest['descriptor']['rodada'], 'geracao': manifest['geracao'],
            'indice_id': manifest['indice_id'], 'banco_sha256': manifest['banco_sha256']}


def cobertura(root, caso, rodada, geracao='v1'):
    run = caminho_rodada(root, caso, rodada)
    con, manifest = _abrir(run, caso, rodada, geracao)
    with closing(con):
        result = _base(manifest, 'cobertura')
        result['cobertura'] = _cobertura(con)
    return _salvar_log(run, result)


def verificar_indice(root, caso, rodada, geracao='v1'):
    run = caminho_rodada(root, caso, rodada)
    con, manifest = _abrir(run, caso, rodada, geracao)
    with closing(con):
        _validar_banco(con)
        if _cobertura(con) != manifest['cobertura']:
            raise ValueError('Cobertura do manifesto diverge do banco.')
        result = _base(manifest, 'verificar')
        result['cobertura'] = manifest['cobertura']
    return result


def _consulta_comum(query):
    try:
        parts = re.findall(r'"([^"\n]+)"|([^\s"]+)', query)
        if query.count('"') % 2:
            raise ValueError('Aspas nao fechadas na consulta.')
        terms = [phrase or term for phrase, term in parts]
        if not terms or not all(any(c.isalnum() for c in term) for term in terms):
            raise ValueError('Consulta sem termos pesquisaveis.')
        return ' AND '.join('"' + term.replace('"', '""') + '"' for term in terms)
    except TypeError as exc:
        raise ValueError('Consulta deve ser texto.') from exc


SELECT_TRECHO = '''SELECT t.referencia,d.documento_id,d.arquivo,d.sha256,
 f.arquivo,f.sha256,f.tipo,f.metodo,u.pagina_pdf,t.linha_inicio,t.linha_fim,t.texto,
 u.linhas_json,u.unidade_id,d.nome,f.adaptador FROM trechos t
 JOIN unidades u USING(unidade_id) JOIN fontes f USING(fonte_id)
 JOIN documentos d USING(documento_id)'''


def _resultado(row, caso, consulta=None, modo=None):
    result = {'referencia': row[0], 'caso_id': caso, 'documento_id': row[1],
              'nome_documento': row[14],
              'original': f'entradas/{row[2]}', 'original_sha256': row[3],
              'fonte_textual': f'entradas/{row[4]}', 'fonte_sha256': row[5],
              'tipo_fonte': row[6], 'metodo': row[7], 'pagina_pdf': row[8],
              'linha_inicio': row[9], 'linha_fim': row[10], 'trecho': row[11],
              'linhas_referem_se_a': 'copia textual de trabalho' if row[6] == 'derivado' else 'arquivo textual original'}
    if row[15] == ADAPTADOR_OCR_IMAGEM:
        result.update(origem_texto='ocr', aviso_ocr=AVISO_OCR_IMAGEM)
    located = _localizadores(row[15], json.loads(row[12]), row[9], row[10])
    if located is None:
        return result
    # Lines of a DOCX/XLSX unit are positions in the working copy; the citable place in
    # the original is the locator (paragraph, table cell or Aba!A1) written on each line.
    result.update(formato=next(k for k, v in ADAPTADORES_OFFICE.items() if v == row[15]),
                  localizadores=[loc for loc, _ in located],
                  localizador_inicio=located[0][0] if located else None,
                  localizador_fim=located[-1][0] if located else None)
    if modo == 'literal':
        needle = consulta.strip()
        result['localizadores_com_termo'] = [loc for loc, text in located if needle in text]
    elif modo == 'comum':
        terms = [_normalizar(phrase or term) for phrase, term in re.findall(r'"([^"\n]+)"|([^\s"]+)', consulta)]
        result['localizadores_com_termo'] = [loc for loc, text in located
                                             if any(term in _normalizar(text) for term in terms)]
    if 'localizadores_com_termo' in result:
        result['observacao_localizadores'] = ('Linhas do trecho cujo conteudo (sem o localizador) contem algum termo '
                                              'da consulta, por comparacao simples; conferir no original.')
    return result


def pesquisar(root, caso, rodada, consulta, *, modo='comum', documentos=None,
              pagina=None, limite=10, deslocamento=0, geracao='v1'):
    run = caminho_rodada(root, caso, rodada)
    con, manifest = _abrir(run, caso, rodada, geracao)
    with closing(con):
        result = _base(manifest, 'buscar')
        result.update(consulta_recebida=consulta, consulta_efetiva=None, modo=modo,
                      filtros={'documentos': documentos or [], 'pagina_pdf': pagina},
                      limite=limite, deslocamento=deslocamento, resultados=[])
        result['cobertura'] = _cobertura(con)
        try:
            if modo not in ('comum', 'fts', 'literal'):
                raise ValueError('Modo deve ser comum, fts ou literal.')
            if not isinstance(consulta, str) or not consulta.strip() or len(consulta) > 2000:
                raise ValueError('Consulta deve ter de 1 a 2000 caracteres nao vazios.')
            if not isinstance(limite, int) or not 1 <= limite <= 50 or not isinstance(deslocamento, int) or deslocamento < 0:
                raise ValueError('Limite deve ser de 1 a 50; deslocamento deve ser nao negativo.')
            if pagina is not None and (not isinstance(pagina, int) or pagina < 1):
                raise ValueError('Pagina deve ser uma posicao fisica positiva.')
            known = {row[0] for row in con.execute('SELECT documento_id FROM documentos')}
            if documentos and (not isinstance(documentos, list) or not set(documentos) <= known):
                raise ValueError('Filtro documental fora do corpus autorizado.')
            effective = _consulta_comum(consulta) if modo == 'comum' else consulta.strip()
            result['consulta_efetiva'] = effective
            condition = 'instr(t.texto, ?) > 0' if modo == 'literal' else 'trechos_fts MATCH ?'
            join = '' if modo == 'literal' else ' JOIN trechos_fts ON trechos_fts.rowid=t.trecho_id'
            params = [effective]
            if documentos:
                condition += ' AND d.documento_id IN (' + ','.join('?' for _ in documentos) + ')'
                params.extend(documentos)
            if pagina is not None:
                condition += ' AND u.pagina_pdf=?'
                params.append(pagina)
            base = SELECT_TRECHO + join + ' WHERE ' + condition
            total = con.execute('SELECT count(*) FROM (' + base + ')', params).fetchone()[0]
            order = 't.referencia' if modo == 'literal' else 'bm25(trechos_fts), t.referencia'
            rows = con.execute(base + ' ORDER BY ' + order + ' LIMIT ? OFFSET ?',
                               [*params, limite, deslocamento]).fetchall()
            result['resultados'] = [_resultado(row, caso, consulta, modo) for row in rows]
            result.update(total_correspondencias=total, retornados=len(rows),
                          truncado=deslocamento > 0 or deslocamento + len(rows) < total,
                          proximo_deslocamento=deslocamento + len(rows) if deslocamento + len(rows) < total else None)
            if modo == 'literal':
                result['observacao_modo'] = 'Substring exata; distingue maiusculas, acentos e pontuacao.'
        except (ValueError, sqlite3.OperationalError) as exc:
            result.update(estado='erro_consulta', erro=str(exc), total_correspondencias=None)
    return _salvar_log(run, result)


def ler_passagem(root, caso, rodada, referencia, *, geracao='v1'):
    run = caminho_rodada(root, caso, rodada)
    con, manifest = _abrir(run, caso, rodada, geracao)
    with closing(con):
        row = con.execute(SELECT_TRECHO + ' WHERE t.referencia=?', (referencia,)).fetchone()
        if not row:
            raise ValueError('Referencia nao encontrada nesta geracao/caso/rodada.')
        result = _base(manifest, 'ler')
        result['passagem'] = _resultado(row, caso)
        linhas = json.loads(row[12])
        result['unidade_completa'] = [{'linha': number, 'texto': text} for number, text in linhas]
        located = _localizadores(row[15], linhas, 1, len(linhas))
        if located is not None and len(located) == len(linhas):
            for item, (locator, _) in zip(result['unidade_completa'], located):
                item['localizador'] = locator
        result['aviso'] = 'Contexto textual; conferir original quando houver imagens, tabelas ou erro de extracao.'
    return _salvar_log(run, result)
