"""Conferência da redação por afirmação: suporte de cada frase, sinais de exagero e revisão humana.

O texto da reportagem é dividido em afirmações (frases ou orações declarativas), cada uma
com a posição exata no texto enviado. Cada afirmação pode receber vínculos de evidência pelo
contrato do Core (``evidencias.vinculos``), com papel, suporte e tipo de afirmação (natureza).
A conferência compara a afirmação com os trechos das evidências de suporte e aponta, por
regras fixas e sem modelo, onde o texto pode ir além da fonte:

- número ou data que não aparece nas evidências de suporte;
- quantificador mais forte que o da fonte ("todos", "sempre", "nunca");
- causalidade sem suporte ("por causa de", "provocou");
- certeza onde a fonte só atribui ("é" contra "segundo X").

Os sinais são alertas para quem revisa, nunca um julgamento. O estado automático
(``sem_suporte``, ``suporte_parcial`` ou ``suportada``) é recalculado a cada leitura a partir
dos vínculos conferidos contra o original. ``revisada_por_humano`` só existe quando uma conta
autenticada da Mesa registrou a revisão: o evento guarda a conta, e a leitura confere que cada
revisão salva corresponde a um evento daquela conta; sem conta, a revisão é recusada. A IA não
revisa por aqui. Uma nova versão do texto preserva o histórico (eventos encadeados do Core) e
reabre as afirmações alteradas. Nada aqui chama modelo ou rede.
"""
from copy import deepcopy
import difflib
from decimal import Decimal, InvalidOperation
import re
import unicodedata

import caderno
import comparador
import evidencias as ev
from revisao_humana import ESTADOS as ESTADOS_REVISAO_HUMANA

ESTADOS = ('sem_suporte', 'suporte_parcial', 'suportada', 'revisada_por_humano')
# Decisões da revisão humana: as mesmas da conferência de achados (revisao_humana.py), sem "pendente".
DECISOES = tuple(e for e in ESTADOS_REVISAO_HUMANA if e != 'pendente')
TIPOS_SINAL = ('numero_divergente', 'quantificador_mais_forte', 'causalidade_sem_suporte', 'certeza_sem_atribuicao')
PADROES = {'titulo': None, 'texto': None, 'versao': 1, 'afirmacoes': [], 'revisao': None}
ID_AFIRMACAO = r'F[a-f0-9]{32}'
ID_TEXTO = r'C[a-f0-9]{32}'  # prefixo C; W é o ID de documento das capturas web (contrato §5.8)
LIMITE_TEXTO = 50000
LIMITE_AFIRMACOES = 500
SEMELHANCA_REABERTURA = 0.6
CAMPOS_AFIRMACAO = {'id', 'texto', 'texto_sha256', 'inicio', 'fim', 'tipo', 'evidencias', 'revisao_humana',
                    'reaberta', 'anterior_id', 'desde_versao'}
CAMPOS_REVISAO = {'decisao', 'observacao', 'conta_id', 'responsavel', 'sequencia', 'texto_sha256'}
CAMPOS_PEDIDO_REVISAO = {'afirmacao_id', 'decisao', 'observacao', 'conta_id', 'responsavel', 'sequencia'}
CAMPOS_EVENTO_REVISAO = {'afirmacao_id', 'decisao', 'conta_id', 'sequencia'}

# Abreviações que não encerram frase (comparadas sem acento e em minúsculas).
_ABREVIACOES = {'sr', 'sra', 'srs', 'sras', 'dr', 'dra', 'drs', 'dras', 'prof', 'profa', 'av', 'art', 'arts',
                'inc', 'n', 'no', 'nos', 'num', 'fl', 'fls', 'p', 'pp', 'pag', 'cap', 'ltda', 'cia', 'gov', 'dep',
                'sen', 'min', 'max', 'vol', 'ed', 'op', 'cit', 'aprox', 'tel', 'obs', 'ex', 'eng', 'adv', 'gen', 'cel'}
_FIM_FRASE = re.compile(r'[.!?…]+["\'”»)\]]*(?=\s|$)')
_QUANTIFICADORES = ('todos', 'todas', 'sempre', 'nunca', 'jamais', 'nenhum', 'nenhuma', 'ninguem', 'totalmente',
                    'completamente', 'inteiramente', 'sem excecao', 'absolutamente')
_CAUSAIS = (r'por causa d[eoa]s?', r'provoc\w*', r'caus(?:ou|aram|ar|ando|ara|aria)', r'result(?:ou|aram) em',
            r'lev(?:ou|aram) a', r'devido a', r'em razao d', r'em decorrencia d', r'em consequencia d',
            r'gracas a', r'culpa d', r'por culpa', r'motivad[oa]s? por', r'ocasion(?:ou|aram)')
_ATRIBUICAO = (r'segundo', r'de acordo com', r'conforme', r'afirm\w*', r'declar\w*', r'aleg\w*', r'diss(?:e|eram)',
               r'diz(?:em)?', r'informa(?:ram|ou)?', r'relat(?:a|ou|aram)', r'na avaliacao d', r'na versao d',
               r'sustent(?:a|ou|aram)', r'atribu\w*', r'supostamente', r'teria(?:m)?')


def _sem_acento(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text) if not unicodedata.combining(c)).casefold()


def _termos(padroes):
    return re.compile(r'\b(?:' + '|'.join(padroes) + r')\b')


_RE_QUANTIFICADOR = _termos(re.escape(q) for q in _QUANTIFICADORES)
_RE_CAUSAL = _termos(_CAUSAIS)
_RE_ATRIBUICAO = _termos(_ATRIBUICAO)


def _normal(text):
    return ' '.join(text.split())


def _texto_integral(value, field, maximum):
    """Texto validado e preservado como enviado (as posições das afirmações se referem a ele)."""
    caderno._texto(value, field, maximum)
    return value


def _fim_valido(text, end):
    """Um ponto final encerra frase, salvo abreviação conhecida ou inicial de nome ("J. Silva")."""
    punct = text[:end].rstrip('"\'”»)]')
    if not punct.endswith('.') or punct.endswith('..'):
        return True  # "!", "?", "…" e reticências encerram a frase
    match = re.search(r'(\w+)\.$', punct)
    word = match.group(1) if match else ''
    if _sem_acento(word) in _ABREVIACOES or re.fullmatch(r'[A-ZÀ-Ý]', word):
        return False
    following = text[end:].lstrip()
    return not following or not following[0].islower()


def _segmentos(text):
    """Pedaços ``(inicio, fim, tipo)`` do texto: frases e, dentro delas, orações separadas por ponto e vírgula."""
    pieces = []
    for block in re.finditer(r'[^\n]+', text):
        start = block.start()
        for match in _FIM_FRASE.finditer(text, block.start(), block.end()):
            if _fim_valido(text, match.end()):
                pieces.append((start, match.end()))
                start = match.end()
        if start < block.end():
            pieces.append((start, block.end()))
    result = []
    for begin, end in pieces:
        clauses = list(re.finditer(r'[^;]+;?', text[begin:end]))
        kind = 'oracao' if len(clauses) > 1 else 'frase'
        for clause in clauses:
            a, b = begin + clause.start(), begin + clause.end()
            while a < b and text[a].isspace():
                a += 1
            while b > a and text[b - 1].isspace():
                b -= 1
            if a < b:
                result.append((a, b, kind))
    return result


def dividir(texto):
    """Afirmações candidatas: frases ou orações declarativas com ao menos três palavras.

    Perguntas e fragmentos curtos (títulos de uma ou duas palavras) ficam de fora. Cada item
    traz ``inicio`` e ``fim`` no texto recebido, de modo que ``texto[inicio:fim]`` é a afirmação.
    """
    if not isinstance(texto, str):
        raise ValueError('Texto da reportagem: informe texto válido.')
    result = []
    for begin, end, kind in _segmentos(texto):
        segment = texto[begin:end]
        if segment.rstrip('"\'”»)]').endswith('?') or len(re.findall(r'\w+', segment)) < 3:
            continue
        result.append({'inicio': begin, 'fim': end, 'texto': segment, 'tipo': kind})
    return result


def _id(identificador, versao, indice):
    return 'F' + caderno._hash(['afirmacao', identificador, versao, indice])[:32]


def _digest(text):
    return caderno._hash(['afirmacao', _normal(text)])


def _nova(identificador, versao, indice, segment, **extra):
    return {'id': _id(identificador, versao, indice), 'texto': segment['texto'], 'texto_sha256': _digest(segment['texto']),
            'inicio': segment['inicio'], 'fim': segment['fim'], 'tipo': segment['tipo'], 'evidencias': [],
            'revisao_humana': None, 'reaberta': False, 'anterior_id': None, 'desde_versao': versao, **extra}


def _reconciliar(identificador, versao, texto, anteriores):
    """Afirmações da nova versão: as idênticas mantêm identidade, vínculos e revisão; as alteradas reabrem."""
    segments = dividir(texto)
    used, result = set(), [None] * len(segments)
    for i, segment in enumerate(segments):
        digest = _digest(segment['texto'])
        same = next((a for a in anteriores if a['texto_sha256'] == digest and a['id'] not in used), None)
        if same:
            used.add(same['id'])
            result[i] = {**deepcopy(same), 'texto': segment['texto'], 'inicio': segment['inicio'],
                         'fim': segment['fim'], 'tipo': segment['tipo']}
    for i, segment in enumerate(segments):
        if result[i] is not None:
            continue
        best, score = None, SEMELHANCA_REABERTURA
        for old in anteriores:
            if old['id'] in used:
                continue
            ratio = difflib.SequenceMatcher(None, _normal(old['texto']), _normal(segment['texto'])).ratio()
            if ratio >= score:
                best, score = old, ratio
        if best:
            # Afirmação alterada: os vínculos seguem para conferência; a revisão humana não vale para o texto novo.
            used.add(best['id'])
            result[i] = _nova(identificador, versao, i, segment, evidencias=deepcopy(best['evidencias']),
                              reaberta=True, anterior_id=best['id'])
        else:
            result[i] = _nova(identificador, versao, i, segment)
    return result


def _afirmacao(state, identifier):
    found = None
    if isinstance(identifier, str) and re.fullmatch(ID_AFIRMACAO, identifier):
        found = next((a for a in state['afirmacoes'] if a['id'] == identifier), None)
    if found is None:
        raise ValueError('Afirmação não encontrada nesta versão do texto.')
    return found


def _revisar(state, request):
    if not isinstance(request, dict) or set(request) != CAMPOS_PEDIDO_REVISAO:
        raise ValueError('Revisão humana inválida.')
    claim = _afirmacao(state, request['afirmacao_id'])
    if request['decisao'] not in DECISOES:
        raise ValueError('Escolha uma decisão de revisão válida.')
    if request['decisao'] == 'conferida_no_original' and not any(x['papel'] == 'suporte' for x in claim['evidencias']):
        raise ValueError('Esta afirmação não tem evidência de suporte vinculada. Registre ajuste ou suporte '
                         'insuficiente, conforme sua avaliação.')
    review = {'decisao': request['decisao'], 'observacao': ev.texto(request['observacao'], 'Observação', 500, vazio=True),
              'conta_id': request['conta_id'], 'responsavel': request['responsavel'],
              'sequencia': request['sequencia'], 'texto_sha256': claim['texto_sha256']}
    same = lambda mark: {k: v for k, v in mark.items() if k != 'sequencia'}
    if claim['revisao_humana'] and same(claim['revisao_humana']) == same(review):
        raise ValueError('Nada mudou na revisão desta afirmação.')
    claim.update(revisao_humana=review, reaberta=False)
    state['revisao'] = {'afirmacao_id': claim['id'], 'decisao': review['decisao'], 'conta_id': review['conta_id'],
                        'sequencia': review['sequencia']}


def _normalizar(root, case, data, atual, identificador):
    if atual is None:
        if set(data) != {'titulo', 'texto'}:
            raise ValueError('Campos inválidos no registro.')
        text = _texto_integral(data['texto'], 'Texto da reportagem', LIMITE_TEXTO)
        state = {'titulo': ev.texto(data['titulo'], 'Título do texto', 300), 'texto': text, 'versao': 1,
                 'afirmacoes': [_nova(identificador, 1, i, s) for i, s in enumerate(dividir(text))], 'revisao': None}
        _regras(state)
        return state
    atual = {k: atual[k] for k in PADROES}  # sem origem_autoria/atualizado_em_utc, que o Core acrescenta
    state = deepcopy(atual)
    state['revisao'] = None
    keys = set(data)
    if keys and keys <= {'titulo', 'texto'}:
        if 'titulo' in data:
            state['titulo'] = ev.texto(data['titulo'], 'Título do texto', 300)
        if 'texto' in data and _texto_integral(data['texto'], 'Texto da reportagem', LIMITE_TEXTO) != atual['texto']:
            state['versao'] = atual['versao'] + 1
            state['texto'] = data['texto']
            state['afirmacoes'] = _reconciliar(identificador, state['versao'], data['texto'], atual['afirmacoes'])
        if state == {**atual, 'revisao': None}:
            raise ValueError('Nada mudou no texto: envie uma nova versão ou outro título.')
    elif keys == {'afirmacoes'}:
        patch = data['afirmacoes']
        if (not isinstance(patch, list) or len(patch) != 1 or not isinstance(patch[0], dict)
                or set(patch[0]) != {'id', 'evidencias'}):
            raise ValueError('Vínculos da afirmação inválidos.')
        claim = _afirmacao(state, patch[0]['id'])
        links = ev.vinculos(root, case, patch[0]['evidencias'])
        if links == claim['evidencias']:
            raise ValueError('Nada mudou nos vínculos desta afirmação.')
        # Mudar as evidências reabre a afirmação: a revisão humana anterior não cobre o novo suporte.
        claim.update(evidencias=links, reaberta=bool(claim['revisao_humana']) or claim['reaberta'], revisao_humana=None)
    elif keys == {'revisao'}:
        _revisar(state, data['revisao'])
    else:
        raise ValueError('Campos inválidos no registro.')
    _regras(state)
    return state


def _regras(state):
    """Regras puras, reaplicadas pelo Core na leitura de cada evento do histórico."""
    ev.texto(state['titulo'], 'Título do texto', 300)
    text = state['texto']
    caderno._texto(text, 'Texto da reportagem', LIMITE_TEXTO)
    if type(state['versao']) is not int or state['versao'] < 1:
        raise ValueError('Versão do texto inválida.')
    claims = state['afirmacoes']
    if not isinstance(claims, list) or len(claims) > LIMITE_AFIRMACOES:
        raise ValueError(f'O texto tem mais de {LIMITE_AFIRMACOES} afirmações; divida a conferência em partes.')
    seen = set()
    for claim in claims:
        if not isinstance(claim, dict) or set(claim) != CAMPOS_AFIRMACAO or not re.fullmatch(ID_AFIRMACAO, str(claim['id'])):
            raise ValueError('Afirmação preservada inválida.')
        if claim['id'] in seen:
            raise ValueError('Afirmação repetida no texto.')
        seen.add(claim['id'])
        begin, end = claim['inicio'], claim['fim']
        if (type(begin) is not int or type(end) is not int or not 0 <= begin < end <= len(text)
                or text[begin:end] != claim['texto'] or claim['texto_sha256'] != _digest(claim['texto'])
                or claim['tipo'] not in ('frase', 'oracao') or type(claim['reaberta']) is not bool
                or type(claim['desde_versao']) is not int or not 1 <= claim['desde_versao'] <= state['versao']
                or claim['anterior_id'] is not None and not re.fullmatch(ID_AFIRMACAO, str(claim['anterior_id']))):
            raise ValueError('Afirmação preservada inválida (posição ou texto divergente).')
        if not isinstance(claim['evidencias'], list) or len(claim['evidencias']) > ev.MAXIMO_VINCULOS:
            raise ValueError('Vínculos da afirmação inválidos.')
        for link in claim['evidencias']:
            ev.validar_vinculo_salvo(link)
        review = claim['revisao_humana']
        if review is not None and (not isinstance(review, dict) or set(review) != CAMPOS_REVISAO
                                   or review['decisao'] not in DECISOES or review['texto_sha256'] != claim['texto_sha256']
                                   or not isinstance(review['conta_id'], str) or not review['conta_id']
                                   or not isinstance(review['responsavel'], str)
                                   or type(review['sequencia']) is not int or review['sequencia'] < 1):
            raise ValueError('Revisão humana preservada inválida.')
    event_review = state['revisao']
    if event_review is not None:
        if not isinstance(event_review, dict) or set(event_review) != CAMPOS_EVENTO_REVISAO:
            raise ValueError('Revisão humana preservada inválida.')
        if 'origem_autoria' in state and state['origem_autoria'] != caderno.AUTORIA_CONTA:
            raise ValueError('A revisão humana exige uma conta autenticada da Mesa.')


COLECAO = ev.Colecao('redacao', 'C',PADROES, _normalizar, _regras, 'conferência da redação')
CAMPOS_BASE = {'caso', 'requisicao_id', 'autor', 'observacao'}
_DIVERGENTE = ('Histórico do registro divergente (revisão humana sem ação de conta correspondente); '
               'nenhuma atualização foi aplicada.')


def _conferir_revisoes(record):
    """Toda revisão humana salva precisa corresponder a um evento da mesma conta, com a mesma decisão."""
    history = record['historico']
    for event in history:
        state = event['estado']
        review = state['revisao']
        if review and (event.get('conta_id') != review['conta_id'] or review['sequencia'] != event['sequencia']
                       or event['origem_autoria'] != caderno.AUTORIA_CONTA):
            raise ValueError(_DIVERGENTE)
        for claim in state['afirmacoes']:
            mark = claim['revisao_humana']
            if not mark:
                continue
            origin = history[mark['sequencia'] - 1]['estado']['revisao'] if mark['sequencia'] <= event['sequencia'] else None
            if (not origin or origin['afirmacao_id'] != claim['id'] or origin['conta_id'] != mark['conta_id']
                    or origin['decisao'] != mark['decisao']):
                raise ValueError(_DIVERGENTE)
    return record


def detalhe(root, case, identifier):
    return _conferir_revisoes(COLECAO.detalhe(root, case, identifier))


def listar(root, case):
    result = []
    for item in COLECAO.listar(root, case):
        if not item['divergente']:
            try:
                _conferir_revisoes(item)
            except ValueError as exc:
                item = {**item, 'estado': None, 'historico': [], 'divergente': True, 'erro': str(exc)}
        result.append(item)
    return result


def _campos(data, extra):
    if not isinstance(data, dict) or set(data) - CAMPOS_BASE - extra:
        raise ValueError('Campos inválidos no registro.')


def _sem_cr(data):
    return {**data, 'texto': data['texto'].replace('\r\n', '\n')} if isinstance(data.get('texto'), str) else data


def criar(root, data, conta=None):
    """``{caso, requisicao_id, autor, observacao?, titulo, texto}`` → registro com as afirmações da versão 1."""
    _campos(data, {'titulo', 'texto'})
    return _conferir_revisoes(COLECAO.salvar(root, _sem_cr(data), 'criar', conta))


def nova_versao(root, data, conta=None):
    """``{…, id, anterior_sha256, texto?, titulo?}``: afirmações iguais mantêm vínculos e revisão; as alteradas reabrem."""
    _campos(data, {'id', 'anterior_sha256', 'titulo', 'texto'})
    return _salvar(root, _sem_cr(data), conta)


def vincular(root, data, conta=None):
    """``{…, id, anterior_sha256, afirmacao_id, evidencias}``: substitui os vínculos de uma afirmação."""
    _campos(data, {'id', 'anterior_sha256', 'afirmacao_id', 'evidencias'})
    body = {k: v for k, v in data.items() if k not in ('afirmacao_id', 'evidencias')}
    body['afirmacoes'] = [{'id': data.get('afirmacao_id'), 'evidencias': data.get('evidencias')}]
    return _salvar(root, body, conta)


def revisar(root, data, conta=None):
    """``{…, id, anterior_sha256, afirmacao_id, decisao, observacao_revisao?}`` → revisão humana registrada.

    Só uma conta autenticada da Mesa revisa: sem ``conta`` o pedido é recusado, e o evento
    gravado leva a conta e o horário. Nenhum campo do cliente declara a revisão por conta própria.
    """
    _campos(data, {'id', 'anterior_sha256', 'afirmacao_id', 'decisao', 'observacao_revisao'})
    account = caderno.conta_valida(conta)
    if account is None:
        raise ValueError('A revisão humana exige uma conta autenticada da Mesa; a IA e o modo local não registram revisão.')
    current = detalhe(root, data.get('caso'), data.get('id'))
    # A sequência do evento entra no pedido; numa repetição ela é a do evento já gravado, e o Core
    # devolve o registro (mesmo conteúdo) ou recusa a tentativa reutilizada com outro conteúdo.
    done = next((e['sequencia'] for e in current['historico'] if e['requisicao_id'] == data.get('requisicao_id')), None)
    sequence = done if done is not None else len(current['historico']) + 1
    body = {k: v for k, v in data.items() if k not in ('afirmacao_id', 'decisao', 'observacao_revisao')}
    body['revisao'] = {'afirmacao_id': data.get('afirmacao_id'), 'decisao': data.get('decisao'),
                       'observacao': data.get('observacao_revisao', ''), 'conta_id': account['id'],
                       'responsavel': account['nome'], 'sequencia': sequence}
    return _salvar(root, body, account)


def _salvar(root, data, conta):
    return _conferir_revisoes(COLECAO.salvar(root, data, 'atualizar', conta))


def _valores(text):
    """Números, valores e datas do texto como chaves comparáveis, sem conversão de unidade."""
    result = {}
    for mark in comparador.marcas(text):
        if mark['tipo'] == 'data':
            key = ('data', mark['normalizado'])
        elif mark['tipo'] in ('numero', 'valor_monetario', 'percentual'):
            try:
                key = (mark['tipo'], mark['unidade'], Decimal(mark['valor']))
            except InvalidOperation:
                continue
        else:
            continue
        result.setdefault(key, mark)
    return result


def sinais(texto, trechos, *, atribuida=False):
    """Sinais determinísticos de que a afirmação vai além dos trechos de suporte.

    ``atribuida`` indica que algum vínculo de suporte foi classificado como alegação atribuída.
    Sem trecho textual (evidência visual) não há comparação: devolve lista vazia.
    """
    sources = [t for t in trechos if isinstance(t, str) and t.strip()]
    if not sources:
        return []
    found = []
    claim_plain, sources_plain = _sem_acento(texto), [_sem_acento(t) for t in sources]
    source_values = {}
    for source in sources:
        source_values.update(_valores(source))
    for key, mark in _valores(texto).items():
        if key not in source_values:
            found.append({'tipo': 'numero_divergente', 'trecho': mark['bruto'], 'posicao': mark['posicao'],
                          'detalhe': f'“{mark["bruto"]}” não aparece nas evidências de suporte.'})
    for match in _RE_QUANTIFICADOR.finditer(claim_plain):
        if not any(re.search(r'\b' + re.escape(match.group(0)) + r'\b', s) for s in sources_plain):
            word = texto[match.start():match.end()]
            found.append({'tipo': 'quantificador_mais_forte', 'trecho': word, 'posicao': match.start(),
                          'detalhe': f'“{word}” é mais forte que o que as evidências dizem.'})
    causal = _RE_CAUSAL.search(claim_plain)
    if causal and not any(_RE_CAUSAL.search(s) for s in sources_plain):
        found.append({'tipo': 'causalidade_sem_suporte', 'trecho': texto[causal.start():causal.end()],
                      'posicao': causal.start(),
                      'detalhe': 'A afirmação estabelece causa que as evidências de suporte não declaram.'})
    if (atribuida or any(_RE_ATRIBUICAO.search(s) for s in sources_plain)) and not _RE_ATRIBUICAO.search(claim_plain):
        found.append({'tipo': 'certeza_sem_atribuicao', 'trecho': None, 'posicao': None,
                      'detalhe': 'A fonte atribui a informação a alguém; a afirmação a apresenta como certeza.'})
    return found


def _estado_automatico(links, signals):
    support = [x for x in links if x['estado'] == 'conferida' and x['papel'] == 'suporte']
    if not support:
        return 'sem_suporte'
    strong = any(x['suporte'] == 'sustentado' and x['natureza'] in ev.NATUREZAS_DOCUMENTAIS for x in support)
    contradicted = any(x['estado'] == 'conferida' and x['papel'] == 'contradicao' and x['suporte'] == 'sustentado'
                       for x in links)
    return 'suportada' if strong and not signals and not contradicted else 'suporte_parcial'


def conferencia(root, case, identifier):
    """Visão da conferência: cada afirmação com vínculos conferidos, sinais, estado e revisão humana."""
    record = detalhe(root, case, identifier)
    state, history, cache = record['estado'], record['historico'], {}
    claims, counts = [], dict.fromkeys(ESTADOS, 0)
    for claim in state['afirmacoes']:
        links = ev.conferir_vinculos(root, case, claim['evidencias'], cache)
        support = [x for x in links if x['estado'] == 'conferida' and x['papel'] == 'suporte']
        signals = sinais(claim['texto'], [x['evidencia']['trecho'] for x in support],
                         atribuida=any(x['natureza'] == 'alegacao_atribuida' for x in support))
        automatic = _estado_automatico(links, signals)
        review = None
        if claim['revisao_humana']:
            event = history[claim['revisao_humana']['sequencia'] - 1]
            review = {**claim['revisao_humana'], 'em_utc': event['em_utc'], 'origem_autoria': event['origem_autoria']}
        status = 'revisada_por_humano' if review else automatic
        counts[status] += 1
        claims.append({**claim, 'evidencias': links, 'sinais': signals, 'estado_automatico': automatic,
                       'estado': status, 'revisao_humana': review,
                       'indisponiveis': sum(1 for x in links if x['estado'] != 'conferida')})
    versions = []
    for event in history:
        if not versions or event['estado']['versao'] != versions[-1]['versao']:
            versions.append({'versao': event['estado']['versao'], 'sequencia': event['sequencia'],
                             'autor': event['autor'], 'em_utc': event['em_utc']})
    return {'caso': case, 'id': record['id'], 'sha256': record['sha256'], 'titulo': state['titulo'],
            'texto': state['texto'], 'versao': state['versao'], 'afirmacoes': claims,
            'resumo': {'total': len(claims), 'por_estado': counts,
                       'com_sinais': sum(1 for c in claims if c['sinais']),
                       'reabertas': sum(1 for c in claims if c['reaberta'])},
            'versoes': versions,
            'aviso': 'Sinais de exagero são regras fixas sobre o texto extraído, para conferência humana; não '
                     'julgam a reportagem. Só uma conta autenticada registra revisão humana; a IA não revisa.'}


def quadro(root, case):
    """Lista de textos com o resumo de cada conferência, para a entrada da tela."""
    rows, broken = [], []
    for item in listar(root, case):
        if item['divergente']:
            broken.append({'id': item['id'], 'erro': item['erro']})
            continue
        view = conferencia(root, case, item['id'])
        rows.append({**{k: view[k] for k in ('id', 'sha256', 'titulo', 'versao', 'resumo')},
                     'atualizado_em_utc': item['estado']['atualizado_em_utc']})
    return {'caso': case, 'textos': rows, 'total': len(rows), 'divergentes': broken}
