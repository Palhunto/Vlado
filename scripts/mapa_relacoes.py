"""Mapa de pessoas e organizações: relações documentadas e conferência de homônimos.

Cada relação exige evidência de suporte, e só aparece como ``documentada`` quando
uma evidência de suporte conferida foi avaliada como sustentada. Nomes parecidos ou
o mesmo identificador geram candidatos a homônimo que só uma pessoa resolve (mesma
entidade, entidade distinta ou indeterminado), com evidência. Nada é fundido nem
ligado automaticamente.
"""
import difflib
import re
import unicodedata

import evidencias as ev

TIPOS = ('pessoa', 'organizacao')
TIPOS_ID = ('cpf', 'cnpj', 'registro_profissional', 'matricula', 'outro')
DECISOES = ('mesma_entidade', 'entidade_distinta', 'indeterminado')
# Sufixos societários, comparados sobre o nome já normalizado ("S.A." vira "s a").
SUFIXOS = ('ltda', 'sa', 's a', 'me', 'epp', 'eireli', 'cia')
ID_ENTIDADE = r'P[a-f0-9]{32}'
PADROES_ENTIDADE = {'tipo': None, 'nome': None, 'variantes': [], 'identificadores': [], 'evidencias': [],
                    'conferencias': [], 'retirado': False, 'motivo_retirada': ''}
PADROES_RELACAO = {'origem': None, 'destino': None, 'tipo': None, 'descricao': '', 'evidencias': [],
                   'retirado': False, 'motivo_retirada': ''}


def nome_normalizado(value, kind='pessoa'):
    plain = ''.join(c for c in unicodedata.normalize('NFD', value.casefold()) if not unicodedata.combining(c))
    name = ' '.join(re.sub(r'[^a-z0-9]+', ' ', plain).split())
    if kind == 'organizacao':
        changed = True
        while changed:
            changed = False
            for suffix in sorted(SUFIXOS, key=len, reverse=True):
                if name.endswith(' ' + suffix):
                    name, changed = name[:-len(suffix) - 1], True
                    break
    return ' '.join(w for w in name.split() if w not in ('de', 'da', 'do', 'das', 'dos', 'e'))


def mascarar(kind, value):
    """Forma de exibição: CPF/CNPJ com dígitos iniciais e finais ocultos; o valor salvo não muda."""
    if kind == 'cpf':
        return f'***.{value[3:6]}.{value[6:9]}-**'
    if kind == 'cnpj':
        return f'**.{value[2:5]}.{value[5:8]}/****-**'
    return value


def _identificador(item, links):
    if not isinstance(item, dict) or set(item) - {'tipo', 'valor', 'fonte'} or not {'tipo', 'valor'} <= set(item):
        raise ValueError('Identificador inválido.')
    if not isinstance(item['tipo'], str) or item['tipo'] not in TIPOS_ID:
        raise ValueError('Tipo de identificador inválido.')
    value = ev.texto(item['valor'], 'Identificador', 100)
    if item['tipo'] in ('cpf', 'cnpj'):
        digits = re.sub(r'\D', '', value)
        if len(digits) != (11 if item['tipo'] == 'cpf' else 14):
            raise ValueError('CPF/CNPJ com número de dígitos inválido; transcreva como consta no documento.')
        value = digits
    source = ev.indice_fonte(item.get('fonte'), links, 'Fonte do identificador')
    if source is None:
        raise ValueError('Fonte do identificador: indique a evidência em que ele aparece.')
    return {'tipo': item['tipo'], 'valor': value, 'fonte': source}


def _conferencia_forma(item, links, own_id):
    """Parte pura da conferência de homônimo (sem abrir a outra entidade)."""
    if not isinstance(item, dict) or set(item) - {'entidade_id', 'decisao', 'justificativa', 'fontes'} \
            or not {'entidade_id', 'decisao', 'justificativa'} <= set(item):
        raise ValueError('Conferência de homônimo inválida.')
    if not isinstance(item['decisao'], str) or item['decisao'] not in DECISOES:
        raise ValueError('Decisão de homônimo inválida.')
    other = item['entidade_id']
    if not isinstance(other, str) or not re.fullmatch(ID_ENTIDADE, other):
        raise ValueError('Entidade comparada inválida.')
    if other == own_id:
        raise ValueError('Uma entidade não é homônima de si mesma.')
    sources = item.get('fontes', [])
    if not isinstance(sources, list) or len(sources) > 20:
        raise ValueError('Fontes da conferência inválidas.')
    sources = {ev.indice_fonte(s, links, 'Fonte da conferência') for s in sources}
    if None in sources:
        raise ValueError('Fonte da conferência: indique uma evidência vinculada a esta entidade.')
    sources = sorted(sources)
    if item['decisao'] != 'indeterminado' and not sources:
        raise ValueError('Para decidir sobre o homônimo, indique a evidência que fundamenta a decisão.')
    return {'entidade_id': other, 'decisao': item['decisao'], 'fontes': sources,
            'justificativa': ev.texto(item['justificativa'], 'Justificativa', 2000)}


def _regras_entidade(state, own_id=None):
    if state['tipo'] not in TIPOS:
        raise ValueError('Informe se é pessoa ou organização.')
    ev.texto(state['nome'], 'Nome', 300)
    links = state['evidencias']
    for key, maximum in (('variantes', 20), ('identificadores', 20), ('conferencias', 50)):
        if not isinstance(state[key], list) or len(state[key]) > maximum:
            raise ValueError(f'Registre até {maximum} {key}.')
    for variant in state['variantes']:
        ev.texto(variant, 'Variante de nome', 300)
    if [_identificador(i, links) for i in state['identificadores']] != state['identificadores']:
        raise ValueError('Identificadores preservados divergem da forma canônica.')
    checks = [_conferencia_forma(c, links, own_id) for c in state['conferencias']]
    if checks != state['conferencias'] or len({c['entidade_id'] for c in checks}) != len(checks):
        raise ValueError('Conferências de homônimo preservadas são inválidas.')
    if ev.retirada(state) != (state['retirado'], state['motivo_retirada']):
        raise ValueError('Retirada preservada inválida.')


def _normalizar_entidade(root, case, data, atual, own_id):
    state = ev.mesclar(data, atual, PADROES_ENTIDADE)
    if state['tipo'] not in TIPOS:
        raise ValueError('Informe se é pessoa ou organização.')
    if atual and state['tipo'] != atual['tipo']:
        raise ValueError('O tipo da entidade não muda; registre uma nova entidade.')
    removing, reason = ev.retirada(state)
    links = ev.vinculos(root, case, state['evidencias'], preservar_indisponiveis=removing)
    name = ev.texto(state['nome'], 'Nome', 300)
    variants = state['variantes']
    if not isinstance(variants, list) or len(variants) > 20:
        raise ValueError('Registre até 20 variantes de nome.')
    variants = list(dict.fromkeys(ev.texto(v, 'Variante de nome', 300) for v in variants))
    ids, checks = state['identificadores'], state['conferencias']
    if not isinstance(ids, list) or len(ids) > 20:
        raise ValueError('Registre até 20 identificadores.')
    if not isinstance(checks, list) or len(checks) > 50:
        raise ValueError('Registre até 50 conferências de homônimo.')
    if atual and 'evidencias' in data:
        if 'identificadores' not in data:
            mover = ev.realocar_fontes(atual['evidencias'], links, 'o identificador')
            ids = [{**i, 'fonte': mover(i['fonte'])} for i in ids]
        if 'conferencias' not in data:
            mover = ev.realocar_fontes(atual['evidencias'], links, 'a conferência de homônimo')
            checks = [{**c, 'fontes': [mover(s) for s in c['fontes']]} for c in checks]
    ids = [_identificador(i, links) for i in ids]
    known = {c['entidade_id']: c for c in (atual or {}).get('conferencias', [])}
    result = []
    for check in checks:
        check = _conferencia_forma(check, links, own_id)
        if check['entidade_id'] not in known:  # a entidade comparada só é aberta na conferência nova
            other = ENTIDADES.detalhe(root, case, check['entidade_id'])['estado']
            if other['tipo'] != state['tipo']:
                raise ValueError('Conferência de homônimo só entre entidades do mesmo tipo.')
        result.append(check)
    if len({c['entidade_id'] for c in result}) != len(result):
        raise ValueError('Uma conferência por entidade comparada.')
    state = {'tipo': state['tipo'], 'nome': name, 'variantes': variants, 'identificadores': ids,
             'evidencias': links, 'conferencias': result, 'retirado': removing, 'motivo_retirada': reason}
    _regras_entidade(state, own_id)
    return state


def _regras_relacao(state):
    for key in ('origem', 'destino'):
        if not isinstance(state[key], str) or not re.fullmatch(ID_ENTIDADE, state[key]):
            raise ValueError('Escolha duas entidades registradas.')
    if state['origem'] == state['destino']:
        raise ValueError('Escolha duas entidades diferentes.')
    ev.texto(state['tipo'], 'Tipo de relação', 120)
    ev.texto(state['descricao'], 'Descrição', 2000, vazio=True)
    if not any(x['papel'] == 'suporte' for x in state['evidencias']):
        raise ValueError('Relação documentada exige ao menos uma evidência de suporte.')
    if ev.retirada(state) != (state['retirado'], state['motivo_retirada']):
        raise ValueError('Retirada preservada inválida.')


def _normalizar_relacao(root, case, data, atual, _identificador):
    state = ev.mesclar(data, atual, PADROES_RELACAO)
    for key in ('origem', 'destino'):
        if not isinstance(state[key], str) or not re.fullmatch(ID_ENTIDADE, state[key]):
            raise ValueError('Escolha duas entidades registradas.')
    if state['origem'] == state['destino']:
        raise ValueError('Escolha duas entidades diferentes.')
    removing, reason = ev.retirada(state)
    if not removing:
        for key in ('origem', 'destino'):
            ENTIDADES.detalhe(root, case, state[key])
    links = ev.vinculos(root, case, state['evidencias'], minimo=1, preservar_indisponiveis=removing)
    result = {'origem': state['origem'], 'destino': state['destino'],
              'tipo': ev.texto(state['tipo'], 'Tipo de relação', 120),
              'descricao': ev.texto(state['descricao'], 'Descrição', 2000, vazio=True), 'evidencias': links,
              'retirado': removing, 'motivo_retirada': reason}
    _regras_relacao(result)
    return result


ENTIDADES = ev.Colecao('entidades', 'P', PADROES_ENTIDADE, _normalizar_entidade, _regras_entidade, 'entidades')
RELACOES = ev.Colecao('relacoes', 'L', PADROES_RELACAO, _normalizar_relacao, _regras_relacao, 'relações')


def salvar_entidade(root, data, operation='criar', conta=None):
    return ENTIDADES.salvar(root, data, operation, conta)


def salvar_relacao(root, data, operation='criar', conta=None):
    return RELACOES.salvar(root, data, operation, conta)


def detalhe_entidade(root, case, identifier):
    return ENTIDADES.detalhe(root, case, identifier)


def listar_entidades(root, case):
    return ENTIDADES.listar(root, case)


def detalhe_relacao(root, case, identifier):
    return RELACOES.detalhe(root, case, identifier)


def listar_relacoes(root, case):
    return RELACOES.listar(root, case)


def _decisoes(a, b):
    found = []
    for x, y in ((a, b), (b, a)):
        check = next((c for c in x['estado']['conferencias'] if c['entidade_id'] == y['id']), None)
        if check:
            found.append({**check, 'registrada_em': x['id']})
    return found


def _motivo(na, nb):
    if na & nb:
        return 'nome_igual'
    if any(sorted(x.split()) == sorted(y.split()) for x in na for y in nb):
        return 'mesmas_palavras'
    if any(len(set(x.split()) & set(y.split())) >= 2 and
           (set(x.split()) <= set(y.split()) or set(y.split()) <= set(x.split())) for x in na for y in nb):
        return 'nome_contido'
    if any(difflib.SequenceMatcher(None, x, y).ratio() >= 0.88 for x in na for y in nb):
        return 'grafia_parecida'
    return None


def homonimos(root, case, entidades=None):
    """Pares de mesmo tipo com nomes parecidos ou identificador igual; a decisão fica com a pessoa."""
    items = ENTIDADES.listar(root, case) if entidades is None else entidades
    items = [e for e in items if not e.get('divergente') and not e['estado']['retirado']]
    result = []
    for i, a in enumerate(items):
        for b in items[i + 1:]:
            sa, sb = a['estado'], b['estado']
            if sa['tipo'] != sb['tipo']:
                continue
            na = {nome_normalizado(n, sa['tipo']) for n in [sa['nome'], *sa['variantes']]} - {''}
            nb = {nome_normalizado(n, sb['tipo']) for n in [sb['nome'], *sb['variantes']]} - {''}
            ia = {(x['tipo'], x['valor']) for x in sa['identificadores']}
            ib = {(x['tipo'], x['valor']) for x in sb['identificadores']}
            reason = _motivo(na, nb) or ('identificador_igual' if ia & ib else None)
            if not reason:
                continue
            shared_types = {t for t, _ in ia} & {t for t, _ in ib}
            decisions = _decisoes(a, b)
            kinds = {d['decisao'] for d in decisions}
            situation = 'pendente' if not decisions else kinds.pop() if len(kinds) == 1 else 'decisoes_divergentes'
            result.append({'entidades': [a['id'], b['id']], 'nomes': [sa['nome'], sb['nome']], 'motivo': reason,
                           'identificadores_comuns': sorted(ia & ib),
                           'identificadores_divergentes': sorted(t for t in shared_types
                               if {v for k, v in ia if k == t} != {v for k, v in ib if k == t}),
                           'conferencias': decisions, 'situacao': situation,
                           'aviso': 'Sugestão para conferência humana; as entidades não foram fundidas.'})
    return result


def _situacao_relacao(links):
    support = [x for x in links if x['papel'] == 'suporte' and x['estado'] == 'conferida']
    values = {x['suporte'] for x in support}
    if not support:
        return 'fonte_indisponivel'
    if 'sustentado' in values:
        return 'documentada'
    if 'parcial' in values:
        return 'suporte_parcial'
    if 'nao_revisado' in values:
        return 'suporte_nao_revisado'
    return 'sem_suporte_sustentado'


def _situacao_entidade(links):
    if not links:
        return 'sem_evidencia'
    return 'com_evidencia' if any(x['estado'] == 'conferida' for x in links) else 'evidencia_indisponivel'


def mapa(root, case, *, incluir_retirados=False):
    """Nós, ligações com evidências conferidas e candidatos a homônimo."""
    cache = {}
    listed = ENTIDADES.listar(root, case)
    broken = [{'colecao': 'entidades', 'id': e['id'], 'erro': e['erro']} for e in listed if e['divergente']]
    entities = [e for e in listed if not e['divergente'] and (incluir_retirados or not e['estado']['retirado'])]
    active = {e['id'] for e in entities if not e['estado']['retirado']}
    nodes = []
    for e in entities:
        state = e['estado']
        links = ev.conferir_vinculos(root, case, state['evidencias'], cache)
        nodes.append({'id': e['id'], 'sha256': e['sha256'], **{k: state[k] for k in ('tipo', 'nome', 'variantes')},
                      'identificadores': [{**i, 'valor_exibicao': mascarar(i['tipo'], i['valor'])}
                                          for i in state['identificadores']],
                      'evidencias': links, 'situacao': _situacao_entidade(links),
                      'retirado': state['retirado'], 'motivo_retirada': state['motivo_retirada']})
    edges = []
    for rel in RELACOES.listar(root, case):
        if rel['divergente']:
            broken.append({'colecao': 'relacoes', 'id': rel['id'], 'erro': rel['erro']})
            continue
        state = rel['estado']
        if state['retirado'] and not incluir_retirados:
            continue
        links = ev.conferir_vinculos(root, case, state['evidencias'], cache)
        edges.append({'id': rel['id'], 'sha256': rel['sha256'], **{k: state[k] for k in ('origem', 'destino', 'tipo', 'descricao')},
                      'evidencias': links, 'situacao': _situacao_relacao(links),
                      'entidades_disponiveis': state['origem'] in active and state['destino'] in active,
                      'retirado': state['retirado'], 'motivo_retirada': state['motivo_retirada']})
    return {'caso': case, 'entidades': nodes, 'relacoes': edges, 'homonimos': homonimos(root, case, listed),
            'divergentes': broken,
            'aviso': 'Ligações registradas por pessoas a partir de evidências; não indicam culpa nem causalidade. '
                     'Só é documentada a ligação com suporte conferido avaliado como sustentado.'}
