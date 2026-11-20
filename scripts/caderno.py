"""Immutable, explicitly human-authored notes, separate from AI findings and FTS."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from comum import dentro, ler_json, escrever_json, pasta_preparacao, sha256
from indice_sqlite import _entradas, caminho_rodada
import lixeira

ID = r'N[a-f0-9]{32}'
HASH = r'[a-f0-9]{64}'
AUTORIA_DECLARADA = 'humana_declarada_na_interface'
AUTORIA_CONTA = 'humana_autenticada_pela_conta_da_mesa'
ORIGENS_AUTORIA = (AUTORIA_DECLARADA, AUTORIA_CONTA)


def _canon(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def _hash(value):
    return hashlib.sha256(_canon(value)).hexdigest()


def _texto(value, field, maximum, *, vazio=False):
    if (not isinstance(value, str) or len(value) > maximum or not vazio and not value.strip()
            or any(ord(c) < 32 and c not in '\n\t' for c in value)):
        raise ValueError(f'{field}: informe texto válido, até {maximum} caracteres.')
    return value.strip()


def conta_valida(conta):
    """Valida a conta do servidor ({'id', 'nome'}); None significa modo local."""
    if conta is None:
        return None
    if (not isinstance(conta, dict) or not isinstance(conta.get('id'), str) or not conta['id'].strip()
            or len(conta['id']) > 200):
        raise ValueError('Conta autenticada inválida.')
    return {'id': conta['id'], 'nome': _texto(conta.get('nome'), 'Nome da conta', 120)}


def autoria(conta, declarado, campo='Autoria humana'):
    """Resolve o autor. Com conta, o nome enviado pelo navegador é ignorado."""
    conta = conta_valida(conta)
    if conta:
        return {'autor': conta['nome'], 'origem_autoria': AUTORIA_CONTA, 'conta_id': conta['id']}
    return {'autor': _texto(declarado, campo, 120), 'origem_autoria': AUTORIA_DECLARADA}


def com_conta(solicitacao, conta):
    """Amarra o digest de idempotência à conta sem alterar digests do modo local."""
    return solicitacao if not conta else {**solicitacao, '_conta_id': conta['id']}


def _pasta(root, case):
    if not isinstance(case, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', case):
        raise ValueError('Selecione uma apuração para o caderno.')
    lixeira.conferir_disponivel(root, case)
    path = dentro(root, f'casos/{case}')
    if not path.is_dir():
        raise ValueError('Apuração não encontrada.')
    return dentro(root, f'casos/{case}/caderno')


@contextmanager
def _trava(folder):
    folder.mkdir(parents=True, exist_ok=True)
    lock = dentro(folder, '.trava')
    try:
        lock.mkdir()
    except FileExistsError as exc:
        raise ValueError('O caderno está sendo salvo em outra janela. Tente novamente.') from exc
    try:
        yield
    finally:
        lock.rmdir()


def contexto(root, case, rodada=None):
    _pasta(root, case)
    if rodada:
        lixeira.conferir_disponivel(root, case, rodada=rodada)
        run = caminho_rodada(root, case, rodada)
        manifest, _ = _entradas(run, case, rodada)
        config = ler_json(dentro(run, 'entradas/configuracao.json'))
        manifest_path = dentro(run, 'entradas/' + config['manifesto_ativo'])
        snapshot = sha256(run / 'snapshot.json')
    else:
        manifest_path = dentro(root, f'casos/{case}/manifesto.json')
        manifest = ler_json(manifest_path)
        snapshot = None
    if manifest.get('caso_id') != case or not isinstance(manifest.get('documentos'), list):
        raise ValueError('Manifesto documental inválido para o caderno.')
    origin = {'caso_id': case, 'rodada': rodada or None, 'corpus_id': manifest['corpus_id'],
              'manifesto_sha256': sha256(manifest_path), 'snapshot_sha256': snapshot, 'manifesto': manifest}
    return origin, _hash(origin)


def documentos(root, case, rodada=None):
    origin, identity = contexto(root, case, rodada)
    return {'caso': case, 'rodada': origin['rodada'], 'corpus_id': origin['corpus_id'], 'origem_id': identity,
        'documentos': [{'documento_id': d['id'], 'sha256': d['sha256'],
            'nome_recebido': d.get('nome_recebido', Path(d['arquivo']).name),
            'formato': Path(d['arquivo']).suffix.lower(), 'paginas_pdf': d.get('paginas_pdf')}
            for d in origin['manifesto']['documentos']]}


def _original(root, origin, identifier, expected, cache=None):
    case = origin['caso_id']
    doc = next((d for d in origin['manifesto']['documentos'] if d['id'] == identifier), None)
    if not doc or doc['sha256'] != expected or Path(doc['arquivo']).parts[:2] != ('casos', case):
        raise ValueError('Documento ou hash fora da origem autorizada do registro humano.')
    relative = (f'execucoes/{case}/{origin["rodada"]}/entradas/' if origin['rodada'] else '') + doc['arquivo']
    path = dentro(root, relative)
    cache = {} if cache is None else cache
    if path not in cache:
        cache[path] = sha256(path)
    if cache[path] != expected:
        raise ValueError('O original mudou ou não está acessível. O registro humano foi preservado.')
    return path, doc


def original_documento(root, data):
    origin, identity = contexto(root, data.get('caso'), data.get('rodada'))
    if data.get('origem_id') != identity:
        raise ValueError('O inventário mudou. Abra o formulário novamente.')
    return _original(root, origin, data.get('documento_id'), data.get('documento_sha256'))[0]


def _carregar(root, case, identifier, expected=None, *, cache=None, seen=None):
    if not isinstance(identifier, str) or not re.fullmatch(ID, identifier):
        raise ValueError('Registro do caderno inválido.')
    folder = _pasta(root, case)
    path = dentro(folder, f'registros/{identifier}.json')
    digest = sha256(path)
    if expected is not None and digest != expected:
        raise ValueError('O registro do caderno mudou. Atualize a seleção.')
    cache = {} if cache is None else cache
    seen = set() if seen is None else seen
    if identifier in seen:
        raise ValueError('Vínculo circular no caderno.')
    key = ('registro', case, identifier, digest)
    if key in cache:
        return cache[key]
    entry = ler_json(path)
    if (entry.get('esquema') != 1 or entry.get('caso_id') != case or entry.get('id') != identifier
            or entry.get('origem_autoria') not in ORIGENS_AUTORIA
            or (entry['origem_autoria'] == AUTORIA_CONTA and not isinstance(entry.get('conta_id'), str))
            or entry.get('tipo') not in ('trecho', 'achado', 'cruzamento')
            or not isinstance(entry.get('fontes'), list) or not entry['fontes']
            or not re.fullmatch(HASH, str(entry.get('solicitacao_sha256', '')))):
        raise ValueError('Registro humano inválido; não foi carregado como achado da IA.')
    _texto(entry.get('autor'), 'Autoria humana', 120)
    _texto(entry.get('titulo'), 'Título', 200)
    _texto(entry.get('anotacao'), 'Anotação', 5000, vazio=entry['tipo'] == 'trecho')
    seen = seen | {identifier}
    for source in entry['fontes']:
        oid = source.get('origem_id')
        if not isinstance(oid, str) or not re.fullmatch(HASH, oid):
            raise ValueError('Origem do registro inválida.')
        opath = dentro(folder, f'origens/{oid}.json')
        origin = ler_json(opath)
        if sha256(opath) != oid or _hash(origin) != oid or origin.get('caso_id') != case:
            raise ValueError('Origem documental do caderno divergente.')
        _original(root, origin, source.get('documento_id'), source.get('original_sha256'), cache)
        _texto(source.get('trecho'), 'Trecho', 12000)
        _texto(source.get('localizador'), 'Localização', 300)
        if source.get('conferencia_textual') not in ('literal_localizado', 'transcricao_humana'):
            raise ValueError('Estado da transcrição inválido.')
    for parent in entry.get('vinculos', []):
        _carregar(root, case, parent['registro_id'], parent['sha256'], cache=cache, seen=seen)
    cache[key] = (entry, digest)
    return entry, digest


def detalhe(root, case, identifier, expected=None):
    entry, digest = _carregar(root, case, identifier, expected)
    return {'registro': entry, 'sha256': digest}


def listar(root, case, *, texto='', limite=20, deslocamento=0):
    folder = _pasta(root, case)
    query = _texto(texto, 'Pesquisa', 500, vazio=True).casefold()
    if type(limite) is not int or not 1 <= limite <= 100 or type(deslocamento) is not int or deslocamento < 0:
        raise ValueError('Paginação do caderno inválida.')
    cache, entries = {}, []
    records = dentro(folder, 'registros')
    for path in sorted(records.glob('N*.json')) if records.exists() else []:
        entry, digest = _carregar(root, case, path.stem, cache=cache)
        if not query or query in json.dumps(entry, ensure_ascii=False).casefold():
            entries.append({'registro': entry, 'sha256': digest})
    entries.sort(key=lambda item: (item['registro']['criado_em_utc'], item['registro']['id']), reverse=True)
    total = len(entries)
    origens = {item['registro'].get('origem_autoria', AUTORIA_DECLARADA) for item in entries}
    return {'caso': case, 'origem_autoria': origens.pop() if len(origens) == 1 else
            (AUTORIA_DECLARADA if not origens else 'mista'), 'total': total,
        'resultados': entries[deslocamento:deslocamento + limite], 'deslocamento': deslocamento,
        'proximo_deslocamento': deslocamento + limite if deslocamento + limite < total else None}


def selecionar(root, case, choices, *, minimo=1):
    if not isinstance(choices, list) or not minimo <= len(choices) <= 20:
        raise ValueError(f'Selecione de {minimo} a 20 registros humanos.')
    entries, seen, cache = [], set(), {}
    for choice in choices:
        if (not isinstance(choice, dict) or set(choice) != {'registro_id', 'sha256'}
                or not isinstance(choice['sha256'], str) or not re.fullmatch(HASH, choice['sha256'])
                or not isinstance(choice['registro_id'], str) or choice['registro_id'] in seen):
            raise ValueError('Seleção do caderno inválida ou duplicada.')
        entry, digest = _carregar(root, case, choice['registro_id'], choice['sha256'], cache=cache)
        seen.add(choice['registro_id']); entries.append({'registro': entry, 'sha256': digest})
    bundle = {'esquema': 1, 'caso_id': case, 'origem': 'contribuicoes_humanas_selecionadas', 'registros': entries}
    if len(_canon(bundle)) > 200000:
        raise ValueError('Os registros excedem o limite de contexto. Selecione menos contribuições.')
    return bundle


def validar_destino(bundle, manifest):
    if bundle['caso_id'] != manifest['caso_id']:
        raise ValueError('Contribuições humanas de outra apuração não podem entrar nesta pergunta.')
    documents = {d['id']: d for d in manifest['documentos']}
    for item in bundle['registros']:
        for source in item['registro']['fontes']:
            doc = documents.get(source['documento_id'])
            if not doc or doc['sha256'] != source['original_sha256']:
                raise ValueError('Uma fonte do caderno não pertence à versão desta conversa. Use Continuar com novos documentos ou escolha uma nova conversa.')


def _publicar(root, case, request, build, conta=None):
    folder = _pasta(root, case)
    rid = request.get('requisicao_id')
    if not isinstance(rid, str) or not re.fullmatch(r'[a-f0-9]{32}', rid):
        raise ValueError('Identidade de salvamento inválida.')
    identifier, request_hash = 'N' + rid, _hash(com_conta(request, conta_valida(conta)))
    with _trava(folder):
        target = dentro(folder, f'registros/{identifier}.json')
        if target.exists():
            entry, digest = _carregar(root, case, identifier)
            if entry['solicitacao_sha256'] != request_hash:
                raise ValueError('Esta tentativa de salvamento já foi usada. Abra um novo registro.')
            return {'estado': 'ja_registrado', 'registro': entry, 'sha256': digest}
        entry, origins = build()
        for identity, origin in origins.items():
            opath = dentro(folder, f'origens/{identity}.json')
            opath.parent.mkdir(parents=True, exist_ok=True)
            if opath.exists():
                if sha256(opath) != identity:
                    raise ValueError('Origem preservada com hash divergente.')
            else:
                with opath.open('xb') as stream:
                    stream.write(_canon(origin))
        entry.setdefault('origem_autoria', AUTORIA_DECLARADA)
        entry.update(esquema=1, id=identifier, caso_id=case,
            solicitacao_sha256=request_hash, criado_em_utc=datetime.now(timezone.utc).isoformat())
        target.parent.mkdir(parents=True, exist_ok=True)
        with pasta_preparacao(folder, '.preparacao_') as staging:
            staged = staging / 'registro.json'; escrever_json(staged, entry, exclusivo=True); staged.rename(target)
        return {'estado': 'registrado', 'registro': entry, 'sha256': sha256(target)}


def salvar(root, data, conta=None):
    fields = {'caso', 'rodada', 'origem_id', 'documento_id', 'documento_sha256', 'pagina_pdf',
              'localizador', 'trecho', 'anotacao', 'autor', 'titulo', 'tipo', 'transcricao_manual', 'requisicao_id'}
    if not isinstance(data, dict) or set(data) - fields:
        raise ValueError('Campos não autorizados no registro humano.')
    case = data.get('caso')
    conta = conta_valida(conta)
    def build():
        kind = data.get('tipo')
        if kind not in ('trecho', 'achado') or type(data.get('transcricao_manual', False)) is not bool:
            raise ValueError('Tipo de contribuição ou confirmação de transcrição inválido.')
        who = autoria(conta, data.get('autor'))
        quote = _texto(data.get('trecho'), 'Trecho', 12000)
        note = _texto(data.get('anotacao', ''), 'Anotação', 5000, vazio=kind == 'trecho')
        title = _texto(data.get('titulo'), 'Título', 200)
        origin, identity = contexto(root, case, data.get('rodada'))
        if data.get('origem_id') != identity:
            raise ValueError('O inventário mudou. Abra o formulário novamente antes de salvar.')
        path, doc = _original(root, origin, data.get('documento_id'), data.get('documento_sha256'))
        page, content = data.get('pagina_pdf'), ''
        locator = _texto(data.get('localizador', ''), 'Localização', 300, vazio=path.suffix.lower() == '.pdf')
        if path.suffix.lower() == '.pdf':
            from pypdf import PdfReader
            try:
                reader = PdfReader(path)
                if type(page) is not int or not 1 <= page <= len(reader.pages):
                    raise ValueError('Informe uma página física existente neste PDF.')
                content = reader.pages[page - 1].extract_text() or ''
            except ValueError:
                raise
            except Exception as exc:
                raise ValueError('Não foi possível conferir a página deste PDF. Verifique o original antes de registrar.') from exc
            locator = f'Página física PDF {page}' + (f' · {locator}' if locator else '')
        else:
            if page is not None:
                raise ValueError('Página PDF não se aplica a este documento; informe a localização observada.')
            if path.suffix.lower() in ('.txt', '.md', '.csv', '.tsv'):
                content = path.read_text(encoding='utf-8-sig')
        locator = _texto(locator, 'Localização', 300)
        normal = lambda value: re.sub(r'\s+', ' ', value).strip()
        matched = bool(content) and normal(quote) in normal(content)
        if not matched and not data.get('transcricao_manual'):
            raise ValueError('O trecho não foi localizado automaticamente. Confira o original e marque a transcrição manual para registrá-lo.')
        source = {'origem_id': identity, 'documento_id': doc['id'], 'original_sha256': doc['sha256'],
            'nome_documento': doc.get('nome_recebido', path.name), 'corpus_id': origin['corpus_id'],
            'rodada_origem': origin['rodada'], 'pagina_pdf': page, 'localizador': locator, 'trecho': quote,
            'conferencia_textual': 'literal_localizado' if matched else 'transcricao_humana'}
        return {'tipo': kind, 'titulo': title, **who, 'anotacao': note,
                'fontes': [source], 'vinculos': []}, {identity: origin}
    return _publicar(root, case, data, build, conta)


def cruzar(root, data, conta=None):
    if not isinstance(data, dict) or set(data) - {'caso', 'selecoes', 'titulo', 'anotacao', 'autor', 'requisicao_id'}:
        raise ValueError('Campos não autorizados no cruzamento humano.')
    case = data.get('caso')
    conta = conta_valida(conta)
    def build():
        bundle = selecionar(root, case, data.get('selecoes'), minimo=2)
        sources, parents, seen = [], [], set()
        for item in bundle['registros']:
            entry = item['registro']
            parents.append({'registro_id': entry['id'], 'sha256': item['sha256'], 'titulo': entry['titulo'], 'autor': entry['autor']})
            for source in entry['fontes']:
                key = _hash(source)
                if key not in seen:
                    seen.add(key); sources.append(deepcopy(source))
        return {'tipo': 'cruzamento', 'titulo': _texto(data.get('titulo'), 'Título', 200),
            **autoria(conta, data.get('autor')),
            'anotacao': _texto(data.get('anotacao'), 'Anotação do cruzamento', 5000),
            'fontes': sources, 'vinculos': parents}, {}
    return _publicar(root, case, data, build, conta)


def original_registro(root, data):
    entry, _ = _carregar(root, data.get('caso'), data.get('registro_id'), data.get('sha256'))
    index = data.get('fonte_indice', 0)
    if type(index) is not int or not 0 <= index < len(entry['fontes']):
        raise ValueError('Fonte fora deste registro humano.')
    source = entry['fontes'][index]
    origin = ler_json(dentro(_pasta(root, data['caso']), f'origens/{source["origem_id"]}.json'))
    return _original(root, origin, source['documento_id'], source['original_sha256'])[0]
