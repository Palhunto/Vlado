"""Human-managed follow-ups with immutable origin, event history and response sources."""
from copy import deepcopy
from datetime import date, datetime, timezone
import re

from comum import dentro, escrever_json, ler_json, pasta_preparacao, sha256
import caderno
import lixeira
from indice_achados import resumo
from registros_achados import carregar

ID = r'G[a-f0-9]{32}'
ESTADOS = ('a_solicitar', 'em_andamento', 'aguardando_resposta', 'resposta_recebida', 'concluida', 'cancelada')
# Campos opcionais de diligências de contato (entrevistas.py). Diligências antigas não os têm e continuam válidas.
TIPOS = ('entrevista', 'pedido_informacao', 'pedido_lai')
ID_PERGUNTA = r'J[a-f0-9]{32}'
CAMPOS_CONTATO = ('tipo', 'destinatario', 'pergunta_id')


def _contato(data):
    """Tipo, destinatário e pergunta de origem, quando a diligência é um contato; ``{}`` se não for."""
    if not any(k in data for k in CAMPOS_CONTATO):
        return {}
    if data.get('tipo') not in TIPOS:
        raise ValueError('Escolha o tipo de contato: entrevista, pedido de informação ou pedido via LAI.')
    question = data.get('pergunta_id')
    if question is not None and (not isinstance(question, str) or not re.fullmatch(ID_PERGUNTA, question)):
        raise ValueError('Pergunta de origem da diligência inválida.')
    return {'tipo': data['tipo'], 'destinatario': caderno._texto(data.get('destinatario'), 'Destinatário', 200),
            'pergunta_id': question}


def _pasta(root, case):
    caderno._pasta(root, case)
    return dentro(root, f'casos/{case}/diligencias')


def _origem(root, case, choice):
    if choice is None:
        return {'identidade': {'tipo': 'livre'}, 'redacao': 'Diligência sem achado vinculado',
                'autor': 'Jornalista', 'anotacao': '', 'fontes': []}
    if not isinstance(choice, dict):
        raise ValueError('Selecione o achado que originou a diligência.')
    if choice.get('tipo') == 'humana' and set(choice) == {'tipo', 'registro_id', 'sha256'}:
        if not isinstance(choice['sha256'], str) or not re.fullmatch(caderno.HASH, choice['sha256']):
            raise ValueError('Hash do achado humano inválido.')
        note = caderno.detalhe(root, case, choice['registro_id'], choice['sha256'])['registro']
        return {'identidade': choice, 'redacao': note['titulo'], 'autor': note['autor'],
                'anotacao': note['anotacao'], 'fontes': note['fontes']}
    if choice.get('tipo') == 'ia' and set(choice) == {'tipo', 'rodada', 'revisao', 'registros_sha256', 'achado_id', 'achado_versao'}:
        lixeira.conferir_disponivel(root, case, rodada=choice['rodada'])
        data, manifest = carregar(root, case, choice['rodada'], choice['revisao'])
        claim = next((c for c in data['achados'] if c['id'] == choice['achado_id']), None)
        if (manifest['registros_sha256'] != choice['registros_sha256'] or claim is None
                or type(choice['achado_versao']) is not int or claim['versoes'][-1]['versao'] != choice['achado_versao']):
            raise ValueError('A identidade do achado mudou. Abra novamente suas fontes.')
        item = resumo(data, claim)
        return {'identidade': choice, 'redacao': item['redacao'], 'autor': 'IA',
                'anotacao': item['limitacoes'], 'fontes': item['evidencias']}
    raise ValueError('Vínculo de origem inválido ou de outra apuração.')


def _prazo(value):
    if value in (None, ''):
        return None
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('Informe um prazo válido ou deixe em branco.')
    date.fromisoformat(value)
    return value


def detalhe(root, case, identifier):
    folder = _pasta(root, case)
    if not isinstance(identifier, str) or not re.fullmatch(ID, identifier):
        raise ValueError('Identidade da diligência inválida.')
    records = dentro(folder, identifier)
    paths = sorted(records.glob('*.json')) if records.exists() else []
    if not paths:
        raise ValueError('Diligência não encontrada nesta apuração.')
    events, previous, state = [], None, None
    for path in paths:
        event = ler_json(dentro(records, path.name))
        if (event.get('esquema') != 1 or event.get('caso_id') != case or event.get('id') != identifier
                or event.get('sequencia') != len(events) + 1 or event.get('anterior_sha256') != previous
                or event.get('operacao') not in ('criar', 'atualizar', 'responder')
                or not re.fullmatch(r'[a-f0-9]{32}', str(event.get('requisicao_id', '')))
                or not re.fullmatch(caderno.HASH, str(event.get('solicitacao_sha256', '')))):
            raise ValueError('Histórico da diligência divergente; nenhuma atualização foi aplicada.')
        caderno._texto(event.get('autor'), 'Autor da atualização', 120)
        current = event['diligencia']
        if (current.get('estado') not in ESTADOS or current.get('origem_autoria') not in caderno.ORIGENS_AUTORIA
                or not isinstance(current.get('respostas'), list)
                or state and current['origem'] != state['origem']):
            raise ValueError('Estado ou origem da diligência inválidos.')
        caderno._texto(current.get('acao'), 'Ação', 1000)
        caderno._texto(current.get('responsavel'), 'Responsável', 120)
        _prazo(current.get('prazo'))
        contact = {k: current[k] for k in CAMPOS_CONTATO if k in current}
        if (contact and _contato(contact) != contact
                or state and contact != {k: state[k] for k in CAMPOS_CONTATO if k in state}):
            raise ValueError('Estado ou origem da diligência inválidos.')
        events.append(event); previous = sha256(path); state = current
    identity = state['origem']['identidade']
    origin = _origem(root, case, None if identity == {'tipo': 'livre'} else identity)
    if origin != state['origem']:
        raise ValueError('A origem preservada diverge do achado vinculado.')
    cache = {}
    for response in state['respostas']:
        origin = response['origem']
        if origin.get('caso_id') != case or caderno._hash(origin) != response['origem_id']:
            raise ValueError('Origem da resposta documental divergente.')
        for doc in response['documentos']:
            caderno._original(root, origin, doc['documento_id'], doc['sha256'], cache)
    return {'caso': case, 'id': identifier, 'sha256': previous, 'diligencia': state, 'historico': events}


def listar(root, case, *, estado='', responsavel='', texto=''):
    folder = _pasta(root, case)
    if estado and estado not in ESTADOS:
        raise ValueError('Estado de diligência inválido.')
    who = caderno._texto(responsavel, 'Responsável', 120, vazio=True).casefold()
    query = caderno._texto(texto, 'Pesquisa', 500, vazio=True).casefold()
    result = []
    for path in sorted(folder.glob('G*')) if folder.exists() else []:
        if not re.fullmatch(ID, path.name) or not path.is_dir():
            continue
        item = detalhe(root, case, path.name); state = item['diligencia']
        if ((not estado or state['estado'] == estado) and (not who or who in state['responsavel'].casefold())
                and (not query or query in (state['acao'] + ' ' + state['origem']['redacao'] + ' '
                                            + state.get('destinatario', '')).casefold())):
            result.append(item)
    result.sort(key=lambda item: (item['diligencia']['atualizada_em_utc'], item['id']), reverse=True)
    return {'caso': case, 'resultados': result, 'total': len(result)}


def salvar(root, data, operation='criar', conta=None):
    fields = {'caso', 'requisicao_id', 'autor', 'observacao'}
    fields |= ({'origem', 'acao', 'responsavel', 'prazo', *CAMPOS_CONTATO} if operation == 'criar'
               else {'diligencia_id', 'anterior_sha256'})
    fields |= {'acao', 'responsavel', 'prazo', 'estado'} if operation == 'atualizar' else set()
    fields |= {'origem_id', 'documentos'} if operation == 'responder' else set()
    if operation not in ('criar', 'atualizar', 'responder') or not isinstance(data, dict) or set(data) - fields:
        raise ValueError('Campos inválidos na diligência.')
    case = data.get('caso'); folder = _pasta(root, case)
    rid = data.get('requisicao_id')
    if not isinstance(rid, str) or not re.fullmatch(r'[a-f0-9]{32}', rid):
        raise ValueError('Identidade de salvamento inválida.')
    identifier = 'G' + rid if operation == 'criar' else data.get('diligencia_id')
    if not isinstance(identifier, str) or not re.fullmatch(ID, identifier):
        raise ValueError('Diligência inválida.')
    who = caderno.autoria(conta, data.get('autor'), 'Autor da atualização')
    author = who['autor']
    note = caderno._texto(data.get('observacao', ''), 'Observação', 5000, vazio=operation == 'criar')
    request_hash = caderno._hash(caderno.com_conta({'operacao': operation, **data}, caderno.conta_valida(conta)))
    with caderno._trava(folder):
        records = dentro(folder, identifier)
        current = detalhe(root, case, identifier) if records.exists() else None
        if current:
            for event in current['historico']:
                if event['requisicao_id'] == rid:
                    if event['solicitacao_sha256'] != request_hash:
                        raise ValueError('Esta tentativa já foi usada com outro conteúdo. Atualize a diligência.')
                    return current
        if operation == 'criar':
            if current:
                raise ValueError('Diligência já existe.')
            state = {'origem': _origem(root, case, data.get('origem')), 'estado': 'a_solicitar',
                'origem_autoria': who['origem_autoria'], 'respostas': [],
                'acao': caderno._texto(data.get('acao'), 'Ação', 1000),
                'responsavel': caderno._texto(data.get('responsavel'), 'Responsável', 120),
                'prazo': _prazo(data.get('prazo')), **_contato(data)}
        else:
            if not current or data.get('anterior_sha256') != current['sha256']:
                raise ValueError('A diligência mudou. Atualize antes de salvar; seu formulário foi preservado.')
            state = deepcopy(current['diligencia'])
        if operation == 'atualizar':
            if data.get('estado') not in ESTADOS:
                raise ValueError('Escolha um estado válido para a diligência.')
            state.update(estado=data['estado'], acao=caderno._texto(data.get('acao'), 'Ação', 1000),
                responsavel=caderno._texto(data.get('responsavel'), 'Responsável', 120), prazo=_prazo(data.get('prazo')))
        if operation == 'responder':
            origin, oid = caderno.contexto(root, case)
            if data.get('origem_id') != oid:
                raise ValueError('O cadastro mudou. Atualize os documentos antes de vincular a resposta.')
            documents = data.get('documentos')
            if not isinstance(documents, list) or not 1 <= len(documents) <= 100:
                raise ValueError('Selecione os documentos da resposta já cadastrados nesta apuração.')
            selected, seen = [], set()
            for doc in documents:
                if not isinstance(doc, dict) or set(doc) != {'documento_id', 'sha256'} or not isinstance(doc['documento_id'], str) or doc['documento_id'] in seen:
                    raise ValueError('Documento da resposta inválido ou duplicado.')
                _, source = caderno._original(root, origin, doc['documento_id'], doc['sha256'])
                selected.append({**doc, 'nome_recebido': source.get('nome_recebido', doc['documento_id'])}); seen.add(doc['documento_id'])
            state['respostas'].append({'origem': origin, 'origem_id': oid, 'documentos': selected,
                'observacao': note, 'autor': author, 'origem_autoria': who['origem_autoria'], 'recebida_em_utc': datetime.now(timezone.utc).isoformat()})
            state['estado'] = 'resposta_recebida'
        state['atualizada_em_utc'] = datetime.now(timezone.utc).isoformat()
        event = {'esquema': 1, 'caso_id': case, 'id': identifier, 'sequencia': len(current['historico']) + 1 if current else 1,
            'anterior_sha256': current['sha256'] if current else None, 'operacao': operation,
            'requisicao_id': rid, 'solicitacao_sha256': request_hash, 'autor': author,
            'origem_autoria': who['origem_autoria'], **({'conta_id': who['conta_id']} if 'conta_id' in who else {}),
            'observacao': note, 'em_utc': state['atualizada_em_utc'], 'diligencia': state}
        with pasta_preparacao(folder, '.preparacao_') as staging:
            staged = staging / 'evento.json'; escrever_json(staged, event, exclusivo=True)
            filename = f'{event["sequencia"]:08d}_{rid}.json'
            if current:
                staged.rename(dentro(records, filename))
            else:
                staged_folder = staging / identifier; staged_folder.mkdir()
                staged.rename(staged_folder / filename); staged_folder.rename(records)
        return detalhe(root, case, identifier)


def selecionar(root, case, choices):
    if not isinstance(choices, list) or not 1 <= len(choices) <= 20:
        raise ValueError('Selecione de 1 a 20 diligências para retomar.')
    result, seen = [], set()
    for choice in choices:
        if not isinstance(choice, dict) or set(choice) != {'diligencia_id', 'sha256'} or not isinstance(choice['diligencia_id'], str) or choice['diligencia_id'] in seen:
            raise ValueError('Seleção de diligências inválida ou duplicada.')
        item = detalhe(root, case, choice['diligencia_id'])
        if choice['sha256'] != item['sha256']:
            raise ValueError('A diligência mudou. Confira novamente antes de retomar.')
        seen.add(item['id']); state = deepcopy(item['diligencia'])
        for response in state['respostas']:
            response.pop('origem')
        result.append({'id': item['id'], 'sha256': item['sha256'], **state})
    bundle = {'esquema': 1, 'caso_id': case, 'origem': 'diligencias_humanas_selecionadas', 'diligencias': result}
    if len(caderno._canon(bundle)) > 200000:
        raise ValueError('As diligências excedem o limite de contexto. Selecione menos registros.')
    return bundle


def validar_destino(bundle, manifest):
    if bundle['caso_id'] != manifest['caso_id']:
        raise ValueError('Diligência de outra apuração.')
    documents = {d['id']: d['sha256'] for d in manifest['documentos']}
    for item in bundle['diligencias']:
        sources = [(s['documento_id'], s['original_sha256']) for s in item['origem']['fontes']]
        sources += [(d['documento_id'], d['sha256']) for r in item['respostas'] for d in r['documentos']]
        if any(documents.get(identifier) != digest for identifier, digest in sources):
            raise ValueError('Há fontes ou respostas fora desta versão. Use Continuar com novos documentos antes de retomar, ou escolha uma nova conversa.')


def original_resposta(root, data):
    item = detalhe(root, data.get('caso'), data.get('diligencia_id'))
    if item['sha256'] != data.get('sha256'):
        raise ValueError('A diligência mudou. Atualize a lista.')
    response_index, doc_index = data.get('resposta_indice'), data.get('documento_indice')
    responses = item['diligencia']['respostas']
    if type(response_index) is not int or not 0 <= response_index < len(responses):
        raise ValueError('Resposta fora desta diligência.')
    response = responses[response_index]
    if type(doc_index) is not int or not 0 <= doc_index < len(response['documentos']):
        raise ValueError('Documento fora desta resposta.')
    doc = response['documentos'][doc_index]
    return caderno._original(root, response['origem'], doc['documento_id'], doc['sha256'])[0]
