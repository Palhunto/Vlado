"""Preparação de entrevistas e pedidos de informação a partir de lacunas da apuração.

Uma lacuna escolhida (o que falta numa hipótese do quadro ou uma afirmação ``sem_suporte``
da conferência da redação) vira um rascunho de pergunta por modelo de texto fixo, sem IA,
guardado com a evidência que motiva a pergunta. Cada pergunta nasce ligada a uma diligência
(``diligencias.py``) com destinatário, tipo de contato (entrevista, pedido de informação ou
pedido via LAI) e prazo. A resposta recebida entra como fonte do caderno (``caderno.salvar``),
citável pelo contrato do Core como referência ``humana``, e a lacuna fica marcada como
respondida, parcial ou sem resposta. A pauta da entrevista e o texto do pedido saem em
Markdown. O pedido leva só as perguntas: evidências e anotações internas ficam na pauta, que
é documento interno. Nada aqui chama modelo ou rede.
"""
from copy import deepcopy
from datetime import datetime, timezone
import re

import caderno
import conferencia_redacao as redacao
import diligencias
import evidencias as ev
import hipoteses

SITUACOES = ('aberta', 'respondida', 'parcial', 'sem_resposta')
RESPOSTAS = SITUACOES[1:]
COM_FONTE = ('respondida', 'parcial')
TIPOS = diligencias.TIPOS
ROTULOS = {'entrevista': 'Entrevista', 'pedido_informacao': 'Pedido de informação', 'pedido_lai': 'Pedido via LAI'}
FORMATOS = ('pauta', 'pedido')
PADROES = {'origem': None, 'motivo': None, 'pergunta': None, 'evidencias': [], 'diligencia_id': None,
           'situacao': 'aberta', 'respostas': []}
CAMPOS_ORIGEM = {'hipotese': {'tipo', 'hipotese_id', 'hipotese_sha256', 'lacuna'},
                 'afirmacao': {'tipo', 'texto_id', 'texto_sha256', 'afirmacao_id'}}
CAMPOS_RESPOSTA_CADERNO = {'origem_id', 'documento_id', 'documento_sha256', 'pagina_pdf', 'localizador', 'trecho',
                           'transcricao_manual', 'titulo', 'anotacao'}
CAMPOS_BASE = {'caso', 'requisicao_id', 'autor', 'observacao'}
LIMITE_EXPORTACAO = 50


def _forma_origem(origem):
    kind = origem.get('tipo') if isinstance(origem, dict) else None
    if kind not in CAMPOS_ORIGEM or set(origem) != CAMPOS_ORIGEM[kind]:
        raise ValueError('Origem da pergunta inválida: escolha uma lacuna do quadro de hipóteses ou uma afirmação sem suporte.')
    if kind == 'hipotese':
        if (not re.fullmatch(hipoteses.COLECAO.id, str(origem['hipotese_id']))
                or not re.fullmatch(ev.HASH, str(origem['hipotese_sha256']))):
            raise ValueError('Origem da pergunta inválida: escolha uma lacuna do quadro de hipóteses ou uma afirmação sem suporte.')
        return {**origem, 'lacuna': ev.texto(origem['lacuna'], 'Lacuna', 1000)}
    if (not re.fullmatch(redacao.ID_TEXTO, str(origem['texto_id'])) or not re.fullmatch(ev.HASH, str(origem['texto_sha256']))
            or not re.fullmatch(redacao.ID_AFIRMACAO, str(origem['afirmacao_id']))):
        raise ValueError('Origem da pergunta inválida: escolha uma lacuna do quadro de hipóteses ou uma afirmação sem suporte.')
    return dict(origem)


def _salvos(links):
    """Forma salva dos vínculos de uma visão (sem o estado e a evidência resolvida acrescentados na leitura)."""
    return [{k: x[k] for k in ev.CAMPOS_SALVOS} for x in links]


def _chave(origem):
    return ((origem['tipo'], origem['hipotese_id'], origem['lacuna']) if origem['tipo'] == 'hipotese'
            else (origem['tipo'], origem['texto_id'], origem['afirmacao_id']))


def _candidatas(root, case):
    """Lacunas atuais do caso, cada uma com a origem exata que ``preparar`` aceita."""
    rows = []
    for item in hipoteses.quadro(root, case)['hipoteses']:
        links = _salvos(item['sustentam'] + item['contrariam'] + item['contexto'])
        for gap in item['faltam']:
            rows.append({'origem': {'tipo': 'hipotese', 'hipotese_id': item['id'], 'hipotese_sha256': item['sha256'],
                                    'lacuna': gap['descricao']},
                         'motivo': {'contexto': item['enunciado'], 'lacuna': gap['descricao'], 'origem_lacuna': gap['origem']},
                         'evidencias': links})
    for text in redacao.quadro(root, case)['textos']:
        view = redacao.conferencia(root, case, text['id'])
        for claim in view['afirmacoes']:
            if claim['estado'] == 'sem_suporte':
                rows.append({'origem': {'tipo': 'afirmacao', 'texto_id': view['id'], 'texto_sha256': view['sha256'],
                                        'afirmacao_id': claim['id']},
                             'motivo': {'contexto': view['titulo'], 'lacuna': claim['texto'], 'origem_lacuna': 'afirmacao_sem_suporte'},
                             'evidencias': _salvos([x for x in claim['evidencias'] if x['estado'] == 'conferida'])})
    return rows


def lacunas(root, case):
    """Lacunas que podem virar pergunta, com a pergunta já preparada (se houver) e a situação dela."""
    asked = {}
    for item in COLECAO.listar(root, case):
        if not item['divergente']:
            asked.setdefault(_chave(item['estado']['origem']), item)
    rows = []
    for row in _candidatas(root, case):
        question = asked.get(_chave(row['origem']))
        rows.append({**row, 'pergunta_id': question['id'] if question else None,
                     'situacao': question['estado']['situacao'] if question else None})
    return {'caso': case, 'lacunas': rows, 'total': len(rows),
            'aviso': 'Lacunas do quadro de hipóteses e afirmações sem suporte; a pergunta é um rascunho a revisar.'}


def _atual(root, case, origem):
    """A lacuna de origem como está agora; recusa se o item mudou desde que a lacuna foi listada."""
    for row in _candidatas(root, case):
        if row['origem'] == origem:
            return row
    raise ValueError('A lacuna de origem mudou ou não existe mais. Atualize a lista de lacunas antes de preparar a pergunta.')


def _limpo(text):
    return ' '.join(text.split()).rstrip(' .;:!?')


def rascunho(motivo):
    """Pergunta por modelo de texto fixo, neutro e sem IA, a partir do motivo da lacuna."""
    gap, context = _limpo(motivo['lacuna']), _limpo(motivo['contexto'])
    if motivo['origem_lacuna'] == 'afirmacao_sem_suporte':
        return (f'Pode confirmar ou corrigir a seguinte informação e indicar o documento que a registra: “{gap}”?')
    if motivo['origem_lacuna'] == 'registrada':
        return f'A respeito de “{context}”: pode informar e, se possível, documentar o seguinte ponto: {gap}?'
    return f'Há documento ou registro que permita confirmar ou afastar o seguinte: “{context}”?'


def _normalizar(root, case, data, atual, identificador):
    if atual is None:
        if set(data) != {'origem', 'motivo', 'pergunta', 'evidencias', 'diligencia_id'}:
            raise ValueError('Campos inválidos no registro.')
        followup = diligencias.detalhe(root, case, data['diligencia_id'])['diligencia']
        if followup.get('pergunta_id') != identificador:
            raise ValueError('A diligência indicada não pertence a esta pergunta.')
        state = {'origem': _forma_origem(data['origem']), 'motivo': data['motivo'],
                 'pergunta': ev.texto(data['pergunta'], 'Pergunta', 2000),
                 'evidencias': ev.vinculos(root, case, data['evidencias']), 'diligencia_id': data['diligencia_id'],
                 'situacao': 'aberta', 'respostas': []}
        _regras(state)
        return state
    state = deepcopy({k: atual[k] for k in PADROES})
    if set(data) == {'pergunta'}:
        state['pergunta'] = ev.texto(data['pergunta'], 'Pergunta', 2000)
        if state['pergunta'] == atual['pergunta']:
            raise ValueError('Nada mudou na pergunta.')
    elif set(data) == {'situacao', 'respostas'}:
        answers = data['respostas']
        if data['situacao'] not in RESPOSTAS or not isinstance(answers, list) or len(answers) != 1:
            raise ValueError('Situação da resposta inválida: use respondida, parcial ou sem_resposta.')
        answer = _resposta(root, case, answers[0])
        if answer['situacao'] != data['situacao']:
            raise ValueError('Situação da resposta inválida: use respondida, parcial ou sem_resposta.')
        state['situacao'] = answer['situacao']
        state['respostas'].append(answer)
    else:
        raise ValueError('Campos inválidos no registro.')
    _regras(state)
    return state


def _resposta(root, case, answer):
    if not isinstance(answer, dict) or set(answer) != {'situacao', 'referencia', 'observacao'}:
        raise ValueError('Resposta inválida.')
    status, ref = answer['situacao'], answer['referencia']
    if status not in RESPOSTAS:
        raise ValueError('Situação da resposta inválida: use respondida, parcial ou sem_resposta.')
    if (status in COM_FONTE) != (ref is not None):
        raise ValueError('Resposta respondida ou parcial precisa da fonte registrada no caderno; sem resposta não leva fonte.')
    if ref is not None:
        ref = ev.referencia(ref)
        if ref['tipo'] != 'humana':
            raise ValueError('A fonte da resposta deve ser um registro do caderno.')
        ev.resolver(root, case, ref)  # citável: resolve contra o original com hash conferido
    return {'situacao': status, 'referencia': ref, 'observacao': ev.texto(answer['observacao'], 'Observação', 2000, vazio=True)}


def _regras(state):
    _forma_origem(state['origem'])
    motive = state['motivo']
    if (not isinstance(motive, dict) or set(motive) != {'contexto', 'lacuna', 'origem_lacuna'}
            or motive['origem_lacuna'] not in ('registrada', 'automatica', 'afirmacao_sem_suporte')):
        raise ValueError('Motivo da pergunta inválido.')
    ev.texto(motive['contexto'], 'Contexto', 1000)
    ev.texto(motive['lacuna'], 'Lacuna', 5000)
    ev.texto(state['pergunta'], 'Pergunta', 2000)
    if not isinstance(state['evidencias'], list) or len(state['evidencias']) > ev.MAXIMO_VINCULOS:
        raise ValueError('Evidências da pergunta inválidas.')
    for link in state['evidencias']:
        ev.validar_vinculo_salvo(link)
    if not re.fullmatch(diligencias.ID, str(state['diligencia_id'])):
        raise ValueError('Diligência da pergunta inválida.')
    if state['situacao'] not in SITUACOES or not isinstance(state['respostas'], list) or len(state['respostas']) > 50:
        raise ValueError('Situação da resposta inválida: use respondida, parcial ou sem_resposta.')
    for answer in state['respostas']:
        if (not isinstance(answer, dict) or set(answer) != {'situacao', 'referencia', 'observacao'}
                or answer['situacao'] not in RESPOSTAS
                or (answer['situacao'] in COM_FONTE) != (answer['referencia'] is not None)):
            raise ValueError('Resposta preservada inválida.')
        if answer['referencia'] is not None and ev.referencia(answer['referencia'])['tipo'] != 'humana':
            raise ValueError('Resposta preservada inválida.')
    if state['situacao'] != (state['respostas'][-1]['situacao'] if state['respostas'] else 'aberta'):
        raise ValueError('Situação da pergunta diverge da última resposta.')


COLECAO = ev.Colecao('perguntas', 'J', PADROES, _normalizar, _regras, 'entrevistas e pedidos')


def _campos(data, extra):
    if not isinstance(data, dict) or set(data) - CAMPOS_BASE - extra:
        raise ValueError('Campos inválidos no registro.')


def _sub(rid, etapa):
    """Identidade derivada e estável de uma etapa do pedido: repetir o pedido repete as mesmas etapas."""
    if not isinstance(rid, str) or not re.fullmatch(r'[a-f0-9]{32}', rid):
        raise ValueError('Identidade de salvamento inválida.')
    return caderno._hash(['entrevistas', etapa, rid])[:32]


def preparar(root, data, conta=None):
    """Lacuna → pergunta por modelo fixo, ligada a uma diligência nova de contato.

    ``data = {caso, requisicao_id, autor, observacao?, origem, tipo, destinatario, responsavel, prazo?}``,
    em que ``origem`` vem exatamente de ``lacunas``.
    """
    _campos(data, {'origem', 'tipo', 'destinatario', 'responsavel', 'prazo'})
    case, rid = data.get('caso'), data.get('requisicao_id')
    _sub(rid, 'validar')  # recusa identidade de salvamento inválida antes de qualquer leitura
    identifier = 'J' + rid
    # Repetir um pedido já aplicado devolve a pergunta salva, sem refazer a diligência.
    if _repetida(root, case, identifier, rid):
        return COLECAO.detalhe(root, case, identifier)
    return _preparar(root, data, conta, identifier)


def _repetida(root, case, identifier, rid):
    try:
        return any(e['requisicao_id'] == rid for e in COLECAO.detalhe(root, case, identifier)['historico'])
    except ValueError:
        return False


def _preparar(root, data, conta, identifier):
    case = data.get('caso')
    if data.get('tipo') not in TIPOS:
        raise ValueError('Escolha o tipo de contato: entrevista, pedido de informação ou pedido via LAI.')
    row = _atual(root, case, _forma_origem(data.get('origem')))
    question = rascunho(row['motivo'])
    followup = diligencias.salvar(root, {
        'caso': case, 'requisicao_id': _sub(data['requisicao_id'], 'diligencia'), 'autor': data.get('autor'),
        'observacao': '', 'origem': None, 'acao': f'{ROTULOS[data["tipo"]]}: {question}'[:1000],
        'responsavel': data.get('responsavel'), 'prazo': data.get('prazo'), 'tipo': data['tipo'],
        'destinatario': data.get('destinatario'), 'pergunta_id': identifier}, 'criar', conta)
    body = {k: data[k] for k in CAMPOS_BASE if k in data}
    body.update(origem=row['origem'], motivo=row['motivo'], pergunta=question, evidencias=row['evidencias'],
                diligencia_id=followup['id'])
    return COLECAO.salvar(root, body, 'criar', conta)


def editar(root, data, conta=None):
    """``{…, id, anterior_sha256, pergunta}``: a pessoa reescreve o rascunho; o histórico guarda a versão anterior."""
    _campos(data, {'id', 'anterior_sha256', 'pergunta'})
    return COLECAO.salvar(root, data, 'atualizar', conta)


def responder(root, data, conta=None):
    """Registra a resposta: ``{…, id, anterior_sha256, situacao, resposta?, observacao_resposta?}``.

    ``respondida`` e ``parcial`` exigem ``resposta`` com o trecho do documento da resposta, já
    cadastrado no caso (os campos de ``caderno.salvar``: ``origem_id``, ``documento_id``,
    ``documento_sha256``, ``pagina_pdf``, ``localizador``, ``trecho``, ``transcricao_manual`` e,
    opcionais, ``titulo`` e ``anotacao``). O trecho vira registro do caderno, citável pelo
    contrato do Core, o documento entra como resposta da diligência e a lacuna é marcada.
    ``sem_resposta`` não leva fonte.
    """
    _campos(data, {'id', 'anterior_sha256', 'situacao', 'resposta', 'observacao_resposta'})
    case, rid = data.get('caso'), data.get('requisicao_id')
    current = COLECAO.detalhe(root, case, data.get('id'))
    if any(e['requisicao_id'] == rid for e in current['historico']):
        return current
    status, payload = data.get('situacao'), data.get('resposta')
    if status not in RESPOSTAS:
        raise ValueError('Situação da resposta inválida: use respondida, parcial ou sem_resposta.')
    if (status in COM_FONTE) != (payload is not None):
        raise ValueError('Resposta respondida ou parcial precisa da fonte registrada no caderno; sem resposta não leva fonte.')
    ref = None
    if payload is not None:
        if not isinstance(payload, dict) or set(payload) - CAMPOS_RESPOSTA_CADERNO:
            raise ValueError('Campos inválidos na fonte da resposta.')
        followup = diligencias.detalhe(root, case, current['estado']['diligencia_id'])
        recipient = followup['diligencia'].get('destinatario', 'destinatário')
        note = caderno.salvar(root, {
            'caso': case, 'requisicao_id': _sub(rid, 'caderno'), 'autor': data.get('autor'), 'tipo': 'trecho',
            'titulo': payload.get('titulo') or f'Resposta de {recipient}'[:200], 'anotacao': payload.get('anotacao', ''),
            **{k: payload[k] for k in CAMPOS_RESPOSTA_CADERNO - {'titulo', 'anotacao'} if k in payload}}, conta)
        ref = {'tipo': 'humana', 'caso_id': case, 'registro_id': note['registro']['id'], 'sha256': note['sha256'], 'fonte': 0}
        step = _sub(rid, 'diligencia')
        if not any(e['requisicao_id'] == step for e in followup['historico']):
            diligencias.salvar(root, {
                'caso': case, 'requisicao_id': step, 'autor': data.get('autor'),
                'observacao': f'Resposta à pergunta {current["id"]}.', 'diligencia_id': followup['id'],
                'anterior_sha256': followup['sha256'], 'origem_id': payload.get('origem_id'),
                'documentos': [{'documento_id': payload.get('documento_id'), 'sha256': payload.get('documento_sha256')}]},
                'responder', conta)
    body = {k: data[k] for k in CAMPOS_BASE | {'id', 'anterior_sha256'} if k in data}
    body.update(situacao=status, respostas=[{'situacao': status, 'referencia': ref,
                                              'observacao': data.get('observacao_resposta', '')}])
    return COLECAO.salvar(root, body, 'atualizar', conta)


def _visao(root, case, record, cache):
    state = record['estado']
    try:
        followup = diligencias.detalhe(root, case, state['diligencia_id'])['diligencia']
        contact = {'id': state['diligencia_id'], 'estado': followup['estado'], 'tipo': followup.get('tipo'),
                   'destinatario': followup.get('destinatario'), 'prazo': followup.get('prazo'),
                   'responsavel': followup['responsavel'], 'disponivel': True}
    except ValueError as exc:
        contact = {'id': state['diligencia_id'], 'disponivel': False, 'erro': str(exc)}
    answers = []
    for answer in state['respostas']:
        source = None
        if answer['referencia']:
            # A fonte da resposta é uma referência (não um vínculo): resolve contra o original sem derrubar a visão.
            try:
                source = {'estado': 'conferida', 'evidencia': ev.resolver(root, case, answer['referencia'], cache),
                          'erro': None}
            except ValueError as exc:
                source = {'estado': 'indisponivel', 'evidencia': None, 'erro': str(exc)}
        answers.append({**answer, 'fonte': source})
    return {'id': record['id'], 'sha256': record['sha256'], 'origem': state['origem'], 'motivo': state['motivo'],
            'pergunta': state['pergunta'], 'situacao': state['situacao'],
            'evidencias': ev.conferir_vinculos(root, case, state['evidencias'], cache), 'diligencia': contact,
            'respostas': answers, 'atualizado_em_utc': state['atualizado_em_utc'],
            'historico': [{k: e[k] for k in ('sequencia', 'operacao', 'autor', 'origem_autoria', 'em_utc')}
                          for e in record['historico']]}


def detalhe(root, case, identifier):
    return _visao(root, case, COLECAO.detalhe(root, case, identifier), {})


def listar(root, case):
    cache, rows, broken = {}, [], []
    for item in COLECAO.listar(root, case):
        if item['divergente']:
            broken.append({'id': item['id'], 'erro': item['erro']})
        else:
            rows.append(_visao(root, case, item, cache))
    return {'caso': case, 'perguntas': rows, 'total': len(rows), 'divergentes': broken}


def _md(text):
    """Texto do usuário numa linha de Markdown, sem virar marcação."""
    return re.sub(r'([\\`*_\[\]<>#|])', r'\\\1', ' '.join(str(text).split()))


def exportar(root, case, ids, formato='pauta'):
    """Pauta (documento interno, com motivos e evidências) ou pedido (só as perguntas) em Markdown."""
    if formato not in FORMATOS:
        raise ValueError('Formato de exportação inválido: use pauta ou pedido.')
    if not isinstance(ids, list) or not 1 <= len(ids) <= LIMITE_EXPORTACAO or len(set(map(str, ids))) != len(ids):
        raise ValueError(f'Selecione de 1 a {LIMITE_EXPORTACAO} perguntas para exportar.')
    items = [detalhe(root, case, identifier) for identifier in ids]
    today = datetime.now(timezone.utc).date().isoformat()
    if formato == 'pedido':
        contacts = {(q['diligencia'].get('tipo'), q['diligencia'].get('destinatario')) for q in items}
        kind, recipient = next(iter(contacts))
        if len(contacts) != 1 or kind not in ('pedido_informacao', 'pedido_lai'):
            raise ValueError('Para o pedido, selecione perguntas de pedido de informação com o mesmo destinatário.')
        lines = [f'# {ROTULOS[kind]}', '', f'**Destinatário:** {_md(recipient)}', f'**Data:** {today}', '']
        if kind == 'pedido_lai':
            lines += ['Com fundamento na Lei nº 12.527/2011 (Lei de Acesso à Informação), solicito as seguintes '
                      'informações:', '']
        else:
            lines += ['Solicito, para fins jornalísticos, as seguintes informações:', '']
        lines += [f'{i}. {_md(q["pergunta"])}' for i, q in enumerate(items, 1)]
        deadlines = sorted({q['diligencia'].get('prazo') for q in items if q['diligencia'].get('prazo')})
        lines += ['']
        if deadlines:
            lines += [f'Peço, se possível, resposta até {deadlines[0]}.', '']
        if kind == 'pedido_lai':
            lines += ['O prazo legal de resposta é de até 20 dias, prorrogável por mais 10 mediante justificativa '
                      '(art. 11 da Lei nº 12.527/2011).', '']
        lines += ['Atenciosamente,', '', '[nome, veículo e contato de quem solicita]', '']
        name = f'pedido_{case}_{today}.md'
    else:
        lines = ['# Pauta de entrevista e pedidos', '', f'**Apuração:** {_md(case)}  ', f'**Preparada em:** {today}', '',
                 '> Documento interno: traz motivos e evidências da apuração. Não enviar à fonte; para enviar, '
                 'exporte o pedido.', '']
        for i, q in enumerate(items, 1):
            contact = q['diligencia']
            lines += [f'## {i}. {_md(q["pergunta"])}', '']
            if contact.get('disponivel'):
                lines += [f'- **Contato:** {ROTULOS.get(contact["tipo"], "Diligência")} · {_md(contact["destinatario"] or "sem destinatário")}'
                          f' · prazo {contact["prazo"] or "não definido"} · responsável {_md(contact["responsavel"])}',
                          f'- **Diligência:** {contact["id"]} ({contact["estado"]})']
            else:
                lines += [f'- **Diligência:** {q["diligencia"]["id"]} indisponível']
            lines += [f'- **Situação da lacuna:** {q["situacao"]}',
                      f'- **Motivo:** {_md(q["motivo"]["lacuna"])} (sobre: {_md(q["motivo"]["contexto"])})']
            if q['evidencias']:
                lines += ['- **Evidências que motivam a pergunta:**']
                for link in q['evidencias']:
                    if link['estado'] == 'conferida':
                        found = link['evidencia']
                        lines += [f'  - {_md(found["localizador"]["legivel"])} ({link["papel"]}): '
                                  f'“{_md(found["trecho"]) or "sem trecho textual; ver o original"}”']
                    else:
                        lines += [f'  - {_md(link["localizador"]["legivel"])}: fonte indisponível para conferência']
            else:
                lines += ['- **Evidências:** nenhuma vinculada; a pergunta busca a primeira fonte.']
            lines += ['']
        name = f'pauta_{case}_{today}.md'
    return {'caso': case, 'formato': formato, 'nome_arquivo': name, 'markdown': '\n'.join(lines)}
