"""Separate rebuildable findings database; never modifies the documentary FTS."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import unicodedata

from comum import dentro, escrever_json, ler_json, sha256, pasta_preparacao
from indice_sqlite import caminho_rodada
from registros_achados import (base, carregar, conferir_evidencia, identificador,
                               listar, recibo, trava, NATUREZAS, SUPORTES, DESTINOS)


def compact(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def texto(value):
    return ''.join(c for c in unicodedata.normalize('NFD', value.casefold()) if not unicodedata.combining(c))


def resumo(data, claim):
    identifier, current = claim['id'], claim['versoes'][-1]
    key = (identifier, current['versao'])
    matching = lambda field: [x for x in data[field] if (x['achado_id'], x['versao']) == key]
    reviews, destinations, humans = matching('revisoes_assistidas'), matching('destinos'), matching('conferencias_humanas')
    links = matching('vinculos')
    evidence_ids = {x['evidencia_id'] for x in links}
    evidences = [e for e in data['evidencias'] if e['id'] in evidence_ids]
    history_links = [x for x in data['vinculos'] if x['achado_id'] == identifier]
    return {'id': identifier, 'subquestao': claim['subquestao'], **current,
            'suporte': reviews[-1]['suporte'] if reviews else 'nao_revisado',
            'conferencia_humana': 'retorno_recebido' if humans else 'nao_realizada',
            'destino': destinations[-1]['destino'] if destinations else 'pendencia',
            'briefing': destinations[-1]['briefing'] if destinations else None,
            'verificacao_externa': data['verificacao_externa'],
            'evidencias': evidences, 'vinculos': links,
            'historico': {'versoes': claim['versoes'],
                         'evidencias': [e for e in data['evidencias'] if e['id'] in {x['evidencia_id'] for x in history_links}],
                         **{f: [x for x in data[f] if x['achado_id'] == identifier]
                         for f in ('vinculos', 'revisoes_assistidas', 'destinos', 'conferencias_humanas')}}}


def _rows(data):
    rows = []
    for claim in data['achados']:
        item = resumo(data, claim)
        searchable = texto(compact([claim, {k: v for k, v in item['historico'].items() if k != 'evidencias'}]))
        rows.append((item['id'], item['natureza'], item['suporte'], item['conferencia_humana'],
                     item['destino'], searchable, compact(item)))
    return rows


def _verificar(con, data):
    if con.execute('PRAGMA user_version').fetchone()[0] != 1 or con.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
        raise ValueError('Integridade/esquema do banco de achados reprovado.')
    canonical = con.execute('SELECT valor FROM metadados WHERE chave=?', ('conjunto',)).fetchone()
    if not canonical or json.loads(canonical[0]) != data:
        raise ValueError('Conjunto canônico do banco divergente.')
    actual = con.execute('SELECT id,natureza,suporte,humana,destino,busca,payload FROM achados ORDER BY id').fetchall()
    if actual != sorted(_rows(data)):
        raise ValueError('Banco e registros canônicos divergentes.')
    for field in ('evidencias', 'vinculos', 'revisoes_assistidas', 'destinos', 'conferencias_humanas', 'procedencia', 'artefatos'):
        actual = [json.loads(r[0]) for r in con.execute(f'SELECT payload FROM {field} ORDER BY ordem')]
        if actual != data[field]:
            raise ValueError('Histórico do banco divergente: ' + field)
    expected = [(c['id'], v['versao'], compact(v)) for c in data['achados'] for v in c['versoes']]
    if con.execute('SELECT achado_id,versao,payload FROM versoes ORDER BY achado_id,versao').fetchall() != sorted(expected):
        raise ValueError('Versões do banco divergentes.')
    docs = sorted((c['id'], e['documento_id']) for c in data['achados']
                  for e in resumo(data, c)['evidencias'])
    if con.execute('SELECT achado_id,documento_id FROM documentos ORDER BY achado_id,documento_id').fetchall() != docs:
        raise ValueError('Relações documentais divergentes.')


def construir(root, caso, rodada, revisao, geracao):
    identificador(geracao)
    run = caminho_rodada(root, caso, rodada)
    with trava(run):
        try:
            data, origin = carregar(root, caso, rodada, revisao)
            destination = dentro(base(run), f'indices/{geracao}')
            if destination.exists():
                raise FileExistsError('Geração de achados já existe; escolher outra, sem sobrescrever.')
            with pasta_preparacao(base(run), '.indice_') as temp:
                work = Path(temp) / 'indice'
                work.mkdir()
                db = work / 'achados.sqlite'
                with closing(sqlite3.connect(db)) as con:
                    con.executescript('''PRAGMA user_version=1;
                      CREATE TABLE metadados (chave TEXT PRIMARY KEY, valor TEXT NOT NULL);
                      CREATE TABLE achados (id TEXT PRIMARY KEY,natureza TEXT,suporte TEXT,humana TEXT,destino TEXT,busca TEXT,payload TEXT);
                      CREATE TABLE versoes (achado_id TEXT,versao INTEGER,payload TEXT,PRIMARY KEY(achado_id,versao));
                      CREATE TABLE documentos (achado_id TEXT,documento_id TEXT);
                      CREATE INDEX filtro_documento ON documentos(documento_id,achado_id);''')
                    with con:
                        con.execute('INSERT INTO metadados VALUES (?,?)', ('origem', compact(origin)))
                        con.execute('INSERT INTO metadados VALUES (?,?)', ('conjunto', compact(data)))
                        con.executemany('INSERT INTO achados VALUES (?,?,?,?,?,?,?)', _rows(data))
                        for claim in data['achados']:
                            for version in claim['versoes']:
                                con.execute('INSERT INTO versoes VALUES (?,?,?)', (claim['id'], version['versao'], compact(version)))
                            for e in resumo(data, claim)['evidencias']:
                                con.execute('INSERT INTO documentos VALUES (?,?)', (claim['id'], e['documento_id']))
                        for field in ('evidencias', 'vinculos', 'revisoes_assistidas', 'destinos', 'conferencias_humanas', 'procedencia', 'artefatos'):
                            con.execute(f'CREATE TABLE {field} (ordem INTEGER PRIMARY KEY,payload TEXT NOT NULL)')
                            con.executemany(f'INSERT INTO {field} VALUES (?,?)', enumerate(map(compact, data[field])))
                    _verificar(con, data)
                manifest = {'esquema': 1, 'caso_id': caso, 'rodada': rodada, 'revisao': revisao,
                            'geracao': geracao, 'registros_sha256': origin['registros_sha256'],
                            'snapshot_sha256': data['snapshot_sha256'], 'banco_sha256': sha256(db)}
                escrever_json(work / 'manifesto.json', manifest, exclusivo=True)
                if carregar(root, caso, rodada, revisao)[1] != origin:
                    raise ValueError('Origem alterada durante construção.')
                destination.parent.mkdir(exist_ok=True)
                work.rename(destination)
            return recibo(run, 'construir', estado='indexado', **manifest)
        except (ValueError, OSError, KeyError, TypeError, sqlite3.Error) as exc:
            recibo(run, 'construir', estado='falha', caso_id=caso, rodada=rodada,
                   revisao=revisao, geracao=geracao, erro=str(exc), registros_preservados=True)
            raise


def _abrir(root, caso, rodada, revisao, geracao):
    identificador(geracao)
    data, origin = carregar(root, caso, rodada, revisao)
    run = caminho_rodada(root, caso, rodada)
    folder = dentro(base(run), f'indices/{geracao}')
    if not (folder / 'manifesto.json').is_file():
        raise ValueError('Índice derivado ausente; construir uma geração explicitamente.')
    manifest = ler_json(dentro(folder, 'manifesto.json'))
    db = dentro(folder, 'achados.sqlite')
    for key, expected in {'esquema': 1, 'caso_id': caso, 'rodada': rodada, 'revisao': revisao,
                          'geracao': geracao, 'registros_sha256': origin['registros_sha256'],
                          'snapshot_sha256': data['snapshot_sha256']}.items():
        if manifest.get(key) != expected:
            raise ValueError('Identidade/revisão do índice de achados divergente.')
    if not db.is_file() or sha256(db) != manifest.get('banco_sha256'):
        raise ValueError('Banco de achados indisponível ou hash divergente.')
    con = sqlite3.connect(db.resolve().as_uri() + '?mode=ro', uri=True)
    try:
        meta = con.execute('SELECT valor FROM metadados WHERE chave=?', ('origem',)).fetchone()
        if not meta or json.loads(meta[0]) != origin:
            raise ValueError('Metadados do índice de achados divergentes.')
        _verificar(con, data)
    except Exception:
        con.close()
        raise
    return con, data, manifest


def catalogo(root, caso, rodada):
    result = listar(root, caso, rodada)
    run = caminho_rodada(root, caso, rodada)
    folder = dentro(base(run), 'indices')
    generations = []
    for path in sorted(folder.iterdir()) if folder.is_dir() else []:
        if path.is_dir():
            identificador(path.name)
            manifest = ler_json(dentro(path, 'manifesto.json'))
            generations.append({'geracao': path.name, 'revisao': manifest['revisao']})
    result['indices'] = generations
    # Metadata only: no hidden selection or loading of all revisions.
    return result


def _consulta(root, caso, rodada, revisao, geracao, *, filtros=None, limite=10, deslocamento=0, completa=False):
    filtros = {} if filtros is None else filtros
    if not isinstance(filtros, dict) or filtros.keys() - {'texto', 'documento', 'natureza', 'suporte', 'humana', 'destino', 'briefing'}:
        raise ValueError('Filtros de achados inválidos.')
    if type(limite) is not int or not 1 <= limite <= 50 or type(deslocamento) is not int or deslocamento < 0 or type(completa) is not bool:
        raise ValueError('Paginação/exportação inválida.')
    conditions, params = [], []
    for key, value in filtros.items():
        if not isinstance(value, str) or len(value) > 2000:
            raise ValueError('Filtro deve ser texto de até 2000 caracteres.')
        if not value:
            continue
        if key == 'texto':
            conditions.append('instr(busca,?)>0')
            params.append(texto(value))
        elif key == 'documento':
            conditions.append('id IN (SELECT achado_id FROM documentos WHERE documento_id=?)')
            params.append(value)
        elif key == 'briefing':
            if value not in ('sim', 'nao'):
                raise ValueError('Filtro de briefing inválido.')
            conditions.append('destino' + ('=' if value == 'sim' else '!=') + '?')
            params.append('incluido')
        else:
            allowed = {'natureza': NATUREZAS, 'suporte': SUPORTES,
                       'humana': ('nao_realizada', 'retorno_recebido'), 'destino': DESTINOS}[key]
            if value not in allowed:
                raise ValueError('Estado de filtro desconhecido.')
            conditions.append(key + '=?')
            params.append(value)
    con, data, manifest = _abrir(root, caso, rodada, revisao, geracao)
    with closing(con):
        where = ' WHERE ' + ' AND '.join(conditions) if conditions else ''
        total = con.execute('SELECT count(*) FROM achados' + where, params).fetchone()[0]
        sql = 'SELECT payload FROM achados' + where + ' ORDER BY id'
        rows = con.execute(sql if completa else sql + ' LIMIT ? OFFSET ?', params if completa else [*params, limite, deslocamento]).fetchall()
        results = [json.loads(row[0]) for row in rows]
        count = len(data['achados'])
        only_pending = count and all(resumo(data, c)['natureza'] == 'pendencia' for c in data['achados'])
        state = 'sem_achados_apos_revisao' if not count and any(e['etapa'] in ('revisao', 'sintese') for e in data['procedencia']) else ('sem_achados_iniciais' if not count else ('somente_pendencias' if only_pending else 'disponivel'))
        result = {**manifest, 'estado': state, 'filtros': filtros, 'resultados': results,
                  'total_correspondencias': total, 'retornados': len(results),
                  'deslocamento': 0 if completa else deslocamento, 'limite': None if completa else limite,
                  'completa': completa, 'escopo_exportacao': 'selecao_filtrada_inteira' if completa else 'pagina',
                  'truncado': False if completa else deslocamento > 0 or deslocamento + len(results) < total,
                  'proximo_deslocamento': None if completa or deslocamento + len(results) >= total else deslocamento + len(results),
                  'documentos': sorted({e['documento_id'] for e in data['evidencias']}),
                  'artefatos': data['artefatos'], 'procedencia': data['procedencia'],
                  'revisoes_sucessoras': []}
        for revision in listar(root, caso, rodada)['revisoes']:
            m = ler_json(dentro(base(caminho_rodada(root, caso, rodada)), f'revisoes/{revision}/manifesto.json'))
            if m.get('anterior') and m['anterior']['revisao'] == revisao:
                result['revisoes_sucessoras'].append(revision)
    return result, data


def consultar(root, caso, rodada, revisao, geracao, *, filtros=None, limite=10, deslocamento=0, completa=False):
    result, _ = _consulta(root, caso, rodada, revisao, geracao, filtros=filtros,
                         limite=limite, deslocamento=deslocamento, completa=completa)
    return recibo(caminho_rodada(root, caso, rodada), 'exportar' if completa else 'consultar', **result)


def detalhe(root, caso, rodada, revisao, geracao, achado_id):
    con, data, manifest = _abrir(root, caso, rodada, revisao, geracao)
    with closing(con):
        row = con.execute('SELECT payload FROM achados WHERE id=?', (achado_id,)).fetchone()
        if not row:
            raise ValueError('Achado não pertence a esta seleção.')
    return recibo(caminho_rodada(root, caso, rodada), 'detalhe', **manifest, achado=json.loads(row[0]))


def evidencia(root, caso, rodada, revisao, evidencia_id):
    data, manifest = carregar(root, caso, rodada, revisao)
    item = next((e for e in data['evidencias'] if e['id'] == evidencia_id), None)
    if item is None:
        raise ValueError('Evidência não pertence a esta revisão/caso/rodada.')
    result = conferir_evidencia(root, caso, rodada, item, registrar=True)  # a person's reading of the context (W1)
    return recibo(caminho_rodada(root, caso, rodada), 'evidencia', caso_id=caso, rodada=rodada,
                  revisao=revisao, registros_sha256=manifest['registros_sha256'], **result)


def artefato(root, caso, rodada, revisao, artefato_sha256):
    data, manifest = carregar(root, caso, rodada, revisao)
    item = next((a for a in data['artefatos'] if a['sha256'] == artefato_sha256 and a['tipo'] == 'briefing'), None)
    if item is None:
        raise ValueError('Briefing não pertence a esta revisão/caso/rodada.')
    run = caminho_rodada(root, caso, rodada)
    return recibo(run, 'briefing', caso_id=caso, rodada=rodada, revisao=revisao,
                  registros_sha256=manifest['registros_sha256'], artefato=item,
                  texto=dentro(run, item['arquivo']).read_text(encoding='utf-8-sig'))


def verificar(root, caso, rodada, revisao, geracao):
    con, data, manifest = _abrir(root, caso, rodada, revisao, geracao)
    con.close()
    return {'estado': 'valido', **manifest, 'achados': len(data['achados'])}
