"""Canonical, append-only findings. Technical validation is not factual verification."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
import uuid

from comum import dentro, escrever_json, ler_json, sha256, pasta_preparacao
from indice_sqlite import (_entradas, _adaptar, caminho_rodada, ler_passagem,
                           ID_GERACAO)

RAIZ_MODELOS = (Path(sys._MEIPASS) / 'modelo_dados' if hasattr(sys, '_MEIPASS')
                else Path(__file__).resolve().parents[1])
SCHEMA = RAIZ_MODELOS / 'modelos/ACHADOS.schema.json'
NATUREZAS = ('declaracao_documental', 'alegacao_atribuida', 'inferencia', 'pendencia')
SUPORTES = ('nao_revisado', 'sustentado', 'parcial', 'nao_sustentado', 'ilegivel')
DESTINOS = ('incluido', 'pendencia', 'retirado', 'substituido')


def validar_esquema(value, schema=None, at='$'):
    """The deliberately small JSON Schema subset used by the shipped contract."""
    schema = ler_json(SCHEMA) if schema is None else schema
    kind = schema.get('type')
    valid = {'object': isinstance(value, dict), 'array': isinstance(value, list),
             'string': isinstance(value, str), 'integer': type(value) is int,
             'null': value is None, 'boolean': type(value) is bool}
    if kind and not any(valid.get(k, False) for k in (kind if isinstance(kind, list) else [kind])):
        raise ValueError(f'{at}: tipo inválido.')
    if 'enum' in schema and value not in schema['enum']:
        raise ValueError(f'{at}: estado não permitido.')
    if 'const' in schema and value != schema['const']:
        raise ValueError(f'{at}: versão/constante incompatível.')
    if value is None:
        return
    if isinstance(value, dict):
        if not set(schema.get('required', [])) <= value.keys():
            raise ValueError(f'{at}: campos obrigatórios ausentes.')
        props = schema.get('properties', {})
        if schema.get('additionalProperties') is False and value.keys() - props.keys():
            raise ValueError(f'{at}: campos desconhecidos {sorted(value.keys() - props.keys())}.')
        for key, item in value.items():
            if key in props:
                validar_esquema(item, props[key], f'{at}.{key}')
    elif isinstance(value, list):
        if len(value) < schema.get('minItems', 0):
            raise ValueError(f'{at}: lista vazia não permitida.')
        for i, item in enumerate(value):
            validar_esquema(item, schema.get('items', {}), f'{at}[{i}]')
    elif isinstance(value, str):
        if len(value.strip()) < schema.get('minLength', 0) or len(value) > schema.get('maxLength', 1000000):
            raise ValueError(f'{at}: comprimento inválido.')
        if 'pattern' in schema and not re.fullmatch(schema['pattern'], value):
            raise ValueError(f'{at}: identificador/formato inválido.')
    elif type(value) is int and value < schema.get('minimum', value):
        raise ValueError(f'{at}: número fora do intervalo.')


def identificador(value):
    if not isinstance(value, str) or not re.fullmatch(ID_GERACAO, value):
        raise ValueError('Revisão/geração inválida.')
    return value


def base(run):
    return dentro(run, 'saidas/achados')


@contextmanager
def trava(run):
    folder = base(run)
    folder.mkdir(parents=True, exist_ok=True)
    path = dentro(folder, '.trava')
    try:
        stream = path.open('x', encoding='utf-8')
    except FileExistsError as exc:
        raise ValueError('Operação concorrente ou interrompida: trava de achados existente; investigar antes de remover.') from exc
    try:
        with stream:
            stream.write(str(uuid.uuid4()))
        yield
    finally:
        path.unlink()


def recibo(run, operation, **values):
    relative = f'saidas/achados/operacoes/{uuid.uuid4().hex}.json'
    result = {'operacao': operation, 'em_utc': datetime.now(timezone.utc).isoformat(),
              'arquivo_recibo': relative, **values}
    escrever_json(dentro(run, relative), result, exclusivo=True)
    return result


def _arquivo(run, relative, digest):
    path = dentro(run, relative)
    if not path.is_file() or sha256(path) != digest:
        raise ValueError(f'Fonte/artefato indisponível ou hash divergente: {relative}')
    return path


def _fontes(run, caso, rodada):
    _, descriptor = _entradas(run, caso, rodada)
    return {f"entradas/{s['arquivo']}": s for s in descriptor['fontes']}


def conferir_evidencia(root, caso, rodada, evidence, sources=None):
    """Validate frozen source identity and observable positions, including non-FTS sources."""
    run = caminho_rodada(root, caso, rodada)
    sources = _fontes(run, caso, rodada) if sources is None else sources
    original = sources.get(evidence['original'])
    if (not original or original['tipo'] != 'original'
            or original['documento_id'] != evidence['documento_id']
            or original['sha256'] != evidence['original_sha256']):
        raise ValueError('Original fora do snapshot/documento ou hash divergente.')
    original_path = _arquivo(run, evidence['original'], evidence['original_sha256'])
    loc = evidence['localizador']
    if evidence['modo'] == 'visual':
        if evidence['fonte_textual'] is not None or evidence['fonte_sha256'] is not None or evidence['indice'] is not None or loc['tipo'] not in ('pagina', 'regiao', 'celula'):
            raise ValueError('Evidência visual requer localizador visual e não recebe referência textual.')
        if original_path.suffix.lower() == '.pdf':
            try:
                from pypdf import PdfReader
                count = len(PdfReader(original_path).pages)
            except Exception as exc:
                raise ValueError('Página visual não validável: PDF ilegível/protegido ou pypdf indisponível.') from exc
            if type(loc['pagina_pdf']) is not int or not 1 <= loc['pagina_pdf'] <= count:
                raise ValueError('Página visual fora do PDF.')
            if loc['tipo'] == 'celula':
                raise ValueError('PDF usa página/região; célula exige planilha.')
        elif loc['pagina_pdf'] is not None or loc['tipo'] == 'pagina':
            raise ValueError('Não inventar página PDF para outro formato.')
        if loc['tipo'] == 'regiao' and (original_path.suffix.lower() not in ('.pdf', '.png', '.jpg', '.jpeg', '.webp', '.tif', '.tiff', '.bmp') or not loc['descricao'].strip()):
            raise ValueError('Região exige imagem/PDF e descrição observável.')
        if loc['tipo'] == 'celula':
            # Only supported tabular formats can publish a technical cell reference.
            if original_path.suffix.lower() not in ('.csv', '.tsv'):
                raise ValueError('Células: nesta versão usar CSV/TSV autorizado; outros formatos ficam pendentes.')
            import csv
            match = re.fullmatch(r'([A-Z]+)([1-9][0-9]*)', loc['descricao'])
            if not match:
                raise ValueError('Célula deve ser A1, B2 etc.')
            column = 0
            for c in match[1]:
                column = column * 26 + ord(c) - 64
            with original_path.open(encoding='utf-8-sig', newline='') as stream:
                rows = list(csv.reader(stream, delimiter='\t' if original_path.suffix.lower() == '.tsv' else ','))
            row = int(match[2])
            if row > len(rows) or column > len(rows[row-1]):
                raise ValueError('Célula fora da tabela.')
            if evidence['trecho'] and evidence['trecho'] not in rows[row-1][column-1]:
                raise ValueError('Trecho diverge da célula.')
        if loc['linha_inicio'] is not None or loc['linha_fim'] is not None:
            raise ValueError('Não inventar linhas em evidência visual.')
        return {'evidencia': evidence, 'contexto': None, 'aviso': 'Leitura visual: contexto textual indisponível; conferir o original.'}
    source = sources.get(evidence['fonte_textual'])
    if (not source or source['documento_id'] != evidence['documento_id']
            or source['sha256'] != evidence['fonte_sha256']):
        raise ValueError('Fonte textual fora do snapshot/documento ou hash divergente.')
    path = _arquivo(run, evidence['fonte_textual'], evidence['fonte_sha256'])
    if loc['tipo'] != 'linhas' or type(loc['linha_inicio']) is not int or type(loc['linha_fim']) is not int:
        raise ValueError('Texto requer intervalo de linhas observáveis.')
    if evidence['modo'] == 'indexada':
        index = evidence['indice']
        if not index:
            raise ValueError('Evidência indexada sem identidade do índice.')
        result = ler_passagem(root, caso, rodada, index['referencia'], geracao=index['geracao'])
        if any(result[k] != index[k] for k in ('indice_id', 'banco_sha256')):
            raise ValueError('Identidade do índice documental divergente.')
        hit = result['passagem']
        for key in ('documento_id', 'original', 'original_sha256', 'fonte_textual', 'fonte_sha256', 'pagina_pdf'):
            if hit[key] != (loc[key] if key == 'pagina_pdf' else evidence[key]):
                raise ValueError('Passagem pertence a outra fonte/localização.')
        if not hit['linha_inicio'] <= loc['linha_inicio'] <= loc['linha_fim'] <= hit['linha_fim']:
            raise ValueError('Intervalo fora da passagem indexada.')
        lines = [(x['linha'], x['texto']) for x in result['unidade_completa']]
    else:
        if evidence['indice'] is not None:
            raise ValueError('Leitura direta não declara referência de índice.')
        _, _, units = _adaptar(path, evidence['documento_id'], evidence['original_sha256'], source['tipo'])
        matches = [u for u in units if u['pagina_pdf'] == loc['pagina_pdf'] and u['estado'] == 'com_texto']
        if len(matches) != 1:
            raise ValueError('Página/unidade textual inválida ou indisponível.')
        lines = matches[0]['linhas']
    if not lines or not lines[0][0] <= loc['linha_inicio'] <= loc['linha_fim'] <= lines[-1][0]:
        raise ValueError('Intervalo de linhas inválido.')
    selected = '\n'.join(t for n, t in lines if loc['linha_inicio'] <= n <= loc['linha_fim'])
    if not evidence['trecho'].strip() or evidence['trecho'] not in selected:
        raise ValueError('Trecho literal não corresponde ao intervalo autorizado.')
    return {'evidencia': evidence, 'contexto': [{'linha': n, 'texto': t} for n, t in lines],
            'aviso': 'Contexto textual; a validação técnica não avalia suporte semântico nem substitui o original.'}


def _prefix(old, new, name):
    if new[:len(old)] != old:
        raise ValueError(f'Histórico alterado/removido: {name}. Acrescentar eventos/versões.')


def validar(root, caso, rodada, data, anterior=None):
    validar_esquema(data)
    run = caminho_rodada(root, caso, rodada)
    if data['caso_id'] != caso or data['rodada'] != rodada or data['snapshot_sha256'] != sha256(run / 'snapshot.json'):
        raise ValueError('Conjunto pertence a outro caso/rodada/snapshot.')
    sources = _fontes(run, caso, rodada)
    claims, versions, evidences = {}, {}, {}
    for claim in data['achados']:
        if claim['id'] in claims:
            raise ValueError('ID de achado repetido.')
        claims[claim['id']] = claim
        for number, version in enumerate(claim['versoes'], 1):
            if version['versao'] != number:
                raise ValueError('Versões de redação devem ser sequenciais desde 1.')
            versions[(claim['id'], number)] = version
    for evidence in data['evidencias']:
        if evidence['id'] in evidences:
            raise ValueError('ID de evidência repetido.')
        evidences[evidence['id']] = evidence
        conferir_evidencia(root, caso, rodada, evidence, sources)
    links = set()
    for link in data['vinculos']:
        key = (link['achado_id'], link['versao'])
        pair = (*key, link['evidencia_id'], link['papel'])
        if key not in versions or link['evidencia_id'] not in evidences or pair in links:
            raise ValueError('Vínculo órfão ou repetido.')
        links.add(pair)
    reviewed = {}
    for review in data['revisoes_assistidas']:
        key = (review['achado_id'], review['versao'])
        if key not in versions or not set(review['fontes_reabertas']) <= evidences.keys():
            raise ValueError('Revisão órfã ou fontes desconhecidas.')
        linked = {p[2] for p in links if p[:2] == key}
        if not set(review['fontes_reabertas']) <= linked:
            raise ValueError('Fonte reaberta sem vínculo com a redação avaliada.')
        if review['suporte'] in ('sustentado', 'parcial') and not any(p[:2] == key and p[3] == 'suporte' and p[2] in review['fontes_reabertas'] for p in links):
            raise ValueError('Suporte exige evidências vinculadas e fontes reabertas.')
        if versions[key]['natureza'] == 'pendencia' and review['suporte'] == 'sustentado':
            raise ValueError('Pendência não pode ser sustentada.')
        reviewed[key] = review
    for claim in claims.values():
        for v in claim['versoes']:
            key = (claim['id'], v['versao'])
            if not any(p[:2] == key for p in links) and v['natureza'] != 'pendencia':
                raise ValueError('Pista sem evidência deve permanecer pendência.')
    artifacts = {}
    for artifact in data['artefatos']:
        relative = artifact['arquivo']
        parts = Path(relative).parts
        if parts[:1] != ('saidas',) or parts[:2] == ('saidas', 'achados') or Path(relative).suffix != '.md' or relative in artifacts:
            raise ValueError('Artefato deve ser relatório/briefing Markdown único em saidas/.')
        _arquivo(run, relative, artifact['sha256'])
        artifacts[relative] = artifact
    decisions = {}
    for decision in data['destinos']:
        key = (decision['achado_id'], decision['versao'])
        if key not in versions:
            raise ValueError('Destino editorial órfão.')
        if decision['destino'] == 'incluido':
            artifact = artifacts.get(decision['briefing'])
            ordinal = decision['revisao_suporte']
            support = data['revisoes_assistidas'][ordinal-1] if type(ordinal) is int and 1 <= ordinal <= len(data['revisoes_assistidas']) else {}
            if (not artifact or artifact['tipo'] != 'briefing' or support.get('suporte') != 'sustentado'
                    or (support.get('achado_id'), support.get('versao')) != key):
                raise ValueError('Inclusão exige redação sustentada e briefing identificado.')
            marker = f'[{key[0]}@v{key[1]}]'
            if marker not in dentro(run, decision['briefing']).read_text(encoding='utf-8-sig'):
                raise ValueError('ID/versão ausente do briefing.')
        elif decision['briefing'] is not None or decision['revisao_suporte'] is not None:
            raise ValueError('Destino sem inclusão não recebe briefing/revisão de suporte.')
        decisions[key] = decision
    for key, decision in decisions.items():
        if decision['destino'] == 'incluido' and reviewed.get(key, {}).get('suporte') != 'sustentado':
            raise ValueError('Suporte mudou: acrescentar retirada/substituição do destino antes de publicar.')
    for artifact in artifacts.values():
        content = dentro(run, artifact['arquivo']).read_text(encoding='utf-8-sig')
        if artifact['tipo'] == 'briefing':
            for identifier, number in re.findall(r'\[(A[0-9]{3,})@v([1-9][0-9]*)\]', content):
                if not any(d['achado_id'] == identifier and d['versao'] == int(number) and d['destino'] == 'incluido' and d['briefing'] == artifact['arquivo'] for d in data['destinos']):
                    raise ValueError('Referência do briefing sem destino correspondente.')
    for feedback in data['conferencias_humanas']:
        if (feedback['achado_id'], feedback['versao']) not in versions:
            raise ValueError('Conferência humana órfã.')
        # Literal feedback/scope are mandatory; no automatic approval is generated.
    if data['verificacao_externa']['estado'] == 'informada':
        config = ler_json(dentro(run, 'entradas/configuracao.json'))
        if not config.get('web_na_apuracao') or not data['verificacao_externa']['relato']:
            raise ValueError('Verificação externa não permitida neste corpus ou sem relato efetivo.')
    elif data['verificacao_externa']['relato'] is not None:
        raise ValueError('Verificação não realizada não recebe relato de verificação.')
    stages = []
    for event in data['procedencia']:
        if not set(event['artefatos']) <= artifacts.keys():
            raise ValueError('Procedência aponta artefato não registrado.')
        kinds = {artifacts[p]['tipo'] for p in event['artefatos']}
        stage = event['etapa']
        required = {'busca': ({'evidencias', 'cruzamentos'},),
                    'revisao': ({'revisao', 'achados_revisados'}, {'insuficiencia'}),
                    'sintese': ({'briefing'}, {'insuficiencia'}),
                    'retorno_humano': ({'retorno_humano'},)}[stage]
        if not any(group <= kinds for group in required):
            raise ValueError('Etapa sem seus relatórios Markdown associados: ' + stage)
        if (stage == 'revisao' and 'busca' not in stages) or (stage == 'sintese' and 'revisao' not in stages):
            raise ValueError('Publicar busca antes da revisão e revisão antes da síntese.')
        if stage == 'retorno_humano' and not data['conferencias_humanas']:
            raise ValueError('Etapa humana sem retorno efetivamente registrado.')
        stages.append(stage)
    if data['anterior'] is None and (set(stages) != {'busca'} or any(len(c['versoes']) != 1 for c in claims.values())):
        raise ValueError('Publicar a geração inicial de busca antes de acrescentar revisão/síntese.')
    # Existence and ID consistency only; prose semantics remain an assisted review task.
    for field, artifact_kind in (('evidencias', 'evidencias'), ('achados', 'cruzamentos')):
        contents = '\n'.join(dentro(run, a['arquivo']).read_text(encoding='utf-8-sig')
                             for a in artifacts.values() if a['tipo'] == artifact_kind)
        prefix = 'E' if field == 'evidencias' else 'A'
        ids = set(re.findall(r'\b' + prefix + r'[0-9]{3,}\b', contents))
        if {x['id'] for x in data[field]} != ids:
            raise ValueError('IDs estruturados sem correspondência nos relatórios brutos: ' + field)
    if (data['revisoes_assistidas'] and 'revisao' not in stages
            or data['destinos'] and 'sintese' not in stages
            or data['conferencias_humanas'] and 'retorno_humano' not in stages):
        raise ValueError('Eventos sem procedência da etapa correspondente.')
    if anterior is not None:
        if data['revisao'] == anterior['revisao']:
            raise ValueError('Usar nova revisão, sem sobrescrita.')
        old_claims = anterior['achados']
        if [c['id'] for c in data['achados'][:len(old_claims)]] != [c['id'] for c in old_claims]:
            raise ValueError('Achados anteriores não podem ser removidos/reordenados.')
        for old, new in zip(old_claims, data['achados']):
            if old['subquestao'] != new['subquestao']:
                raise ValueError('Subquestão histórica alterada.')
            _prefix(old['versoes'], new['versoes'], old['id'])
        for field in ('evidencias', 'vinculos', 'revisoes_assistidas', 'destinos', 'conferencias_humanas', 'procedencia', 'artefatos'):
            _prefix(anterior[field], data[field], field)
        if anterior['verificacao_externa']['estado'] == 'informada' and anterior['verificacao_externa'] != data['verificacao_externa']:
            raise ValueError('Relato externo anterior deve ser preservado.')
    return {'estado': 'valido', 'achados': len(claims), 'evidencias': len(evidences),
            'aviso': 'Validação técnica; não comprova a semântica do suporte ou conferência humana.'}


def carregar(root, caso, rodada, revisao, _seen=None):
    run = caminho_rodada(root, caso, rodada)
    identificador(revisao)
    seen = set() if _seen is None else _seen
    if revisao in seen:
        raise ValueError('Ciclo no histórico de revisões.')
    seen.add(revisao)
    folder = dentro(base(run), f'revisoes/{revisao}')
    manifest = ler_json(dentro(folder, 'manifesto.json'))
    path = _arquivo(folder, 'registros.json', manifest['registros_sha256'])
    data = ler_json(path)
    if data.get('revisao') != revisao or manifest.get('revisao') != revisao or manifest.get('caso_id') != caso or manifest.get('rodada') != rodada:
        raise ValueError('Manifesto de revisão divergente.')
    previous = data['anterior']
    old = None
    if previous:
        old, old_manifest = carregar(root, caso, rodada, previous['revisao'], seen)
        if old_manifest['registros_sha256'] != previous['registros_sha256']:
            raise ValueError('Vínculo com revisão anterior divergente.')
    validar(root, caso, rodada, data, old)
    if manifest.get('artefatos') != data['artefatos'] or manifest.get('snapshot_sha256') != data['snapshot_sha256'] or manifest.get('anterior') != previous or manifest.get('esquema') != 1:
        raise ValueError('Manifesto e registros divergentes.')
    return data, manifest


def listar(root, caso, rodada):
    run = caminho_rodada(root, caso, rodada)
    folder = dentro(base(run), 'revisoes')
    revisions = []
    for path in sorted(folder.iterdir()) if folder.is_dir() else []:
        if path.is_dir() and re.fullmatch(ID_GERACAO, path.name):
            revisions.append(path.name)
    return {'estado': 'disponivel' if revisions else 'nao_produzidos', 'caso_id': caso,
            'rodada': rodada, 'revisoes': revisions}


def publicar(root, caso, rodada, data):
    run = caminho_rodada(root, caso, rodada)
    # JSON round trip isolates caller mutations during publication.
    data = json.loads(json.dumps(data, ensure_ascii=False))
    with trava(run):
        try:
            validar_esquema(data)
            existing = listar(root, caso, rodada)['revisoes']
            previous, old = data['anterior'], None
            if previous:
                old, manifest = carregar(root, caso, rodada, previous['revisao'])
                if manifest['registros_sha256'] != previous['registros_sha256']:
                    raise ValueError('Hash da revisão anterior divergente.')
                # Linear history: stale writers cannot fork silently.
                for revision in existing:
                    m = ler_json(dentro(base(run), f'revisoes/{revision}/manifesto.json'))
                    if m.get('anterior') and m['anterior']['revisao'] == previous['revisao']:
                        raise ValueError('Revisão anterior já possui sucessora; atualizar a base explicitamente.')
            elif existing:
                raise ValueError('Revisão inicial já publicada; informar anterior.')
            validar(root, caso, rodada, data, old)
            destination = dentro(base(run), f"revisoes/{data['revisao']}")
            if destination.exists():
                raise FileExistsError('Revisão já existe; sobrescrita recusada.')
            with pasta_preparacao(base(run), '.publicacao_') as temp:
                work = Path(temp) / 'revisao'
                work.mkdir()
                escrever_json(work / 'registros.json', data, exclusivo=True)
                manifest = {'esquema': 1, 'caso_id': caso, 'rodada': rodada, 'revisao': data['revisao'],
                            'snapshot_sha256': data['snapshot_sha256'], 'anterior': previous,
                            'registros_sha256': sha256(work / 'registros.json'), 'artefatos': data['artefatos'],
                            'criado_em_utc': datetime.now(timezone.utc).isoformat()}
                escrever_json(work / 'manifesto.json', manifest, exclusivo=True)
                validar(root, caso, rodada, data, old)
                destination.parent.mkdir(exist_ok=True)
                work.rename(destination)
            return recibo(run, 'registrar', estado='publicado_sem_indice', caso_id=caso, rodada=rodada,
                          revisao=data['revisao'], manifesto=manifest)
        except (ValueError, OSError, KeyError, TypeError) as exc:
            recibo(run, 'registrar', estado='falha', caso_id=caso, rodada=rodada, erro=str(exc))
            raise
