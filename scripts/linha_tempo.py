"""Linha do tempo com fontes: acontecimentos documentados e tipos de data distintos.

Cada data aponta para a evidência vinculada que a documenta. Datas de tipos
diferentes (ocorrência, documento, publicação, registro...) nunca são fundidas; datas
do mesmo tipo e diferentes no mesmo evento são sinalizadas, não resolvidas.

Correspondência com os tipos pedidos pela apuração: ocorrência → ``fato``;
documento → ``emissao_documento``; publicação → ``publicacao``; registro → ``registro``.
Ordem de datas parciais: a data vai para o início do seu período, e a precisão mais
grossa vem primeiro (``2024`` antes de ``2024-01-01``), o que não afirma que o fato
ocorreu no início do período.
"""
from datetime import date
import re

import evidencias as ev

TIPOS_DATA = {
    'fato': 'Data do fato (ocorrência)',
    'emissao_documento': 'Data de emissão do documento',
    'assinatura': 'Data de assinatura',
    'publicacao': 'Data de publicação',
    'registro': 'Data de registro (cartório, sistema ou órgão)',
    'vigencia_inicio': 'Início de vigência',
    'vigencia_fim': 'Fim de vigência',
    'pagamento': 'Data de pagamento',
    'recebimento': 'Data de recebimento ou protocolo',
    'declarada_por_fonte': 'Data declarada por uma fonte',
}
PRECISOES = {4: 'ano', 7: 'mes', 10: 'dia'}
PADROES = {'descricao': None, 'datas': None, 'evidencias': [], 'retirado': False, 'motivo_retirada': ''}
CAMPOS_DATA = {'tipo', 'valor', 'aproximada', 'fonte', 'observacao', 'precisao'}


def data_parcial(value):
    """Aceita AAAA, AAAA-MM ou AAAA-MM-DD; devolve a precisão observada."""
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}(-\d{2}(-\d{2})?)?', value):
        raise ValueError('Data inválida: use AAAA, AAAA-MM ou AAAA-MM-DD, conforme a precisão do documento.')
    padded = value + '-01' * ((10 - len(value)) // 3)
    try:
        date.fromisoformat(padded)
    except ValueError as exc:
        raise ValueError('Data inexistente no calendário.') from exc
    return PRECISOES[len(value)]


def _datas(items, links):
    """Valida as datas; aceita a forma salva (``precisao`` é recalculada, nunca confiada)."""
    if not isinstance(items, list) or not 1 <= len(items) <= 10:
        raise ValueError('Informe de 1 a 10 datas para o acontecimento.')
    result, seen = [], set()
    for item in items:
        if not isinstance(item, dict) or set(item) - CAMPOS_DATA or not {'tipo', 'valor', 'fonte'} <= set(item):
            raise ValueError('Data do acontecimento inválida.')
        if not isinstance(item['tipo'], str) or item['tipo'] not in TIPOS_DATA:
            raise ValueError('Tipo de data inválido.')
        approx = item.get('aproximada', False)
        if type(approx) is not bool:
            raise ValueError('Indique se a data é aproximada.')
        source = ev.indice_fonte(item['fonte'], links, 'Fonte da data')
        if source is None:
            raise ValueError('Fonte da data: indique a evidência vinculada que documenta esta data.')
        role = links[source]['papel']
        if role == 'contradicao':
            raise ValueError('Uma evidência de contradição não documenta a data do acontecimento; '
                             'registre-a como suporte de outro acontecimento.')
        if role == 'contexto' and item['tipo'] != 'declarada_por_fonte':
            raise ValueError('Uma evidência de contexto só documenta data declarada por fonte.')
        precision = data_parcial(item['valor'])
        key = (item['tipo'], item['valor'], source)
        if key in seen:
            raise ValueError('Data repetida.')
        seen.add(key)
        result.append({'tipo': item['tipo'], 'valor': item['valor'], 'precisao': precision,
                       'aproximada': approx, 'fonte': source,
                       'observacao': ev.texto(item.get('observacao', ''), 'Observação da data', 500, vazio=True)})
    return result


def _regras(state):
    ev.texto(state['descricao'], 'Acontecimento', 1000)
    links = state['evidencias']
    if not links or not any(x['papel'] == 'suporte' for x in links):
        raise ValueError('Acontecimento documentado exige ao menos uma evidência de suporte.')
    if _datas(state['datas'], links) != state['datas']:
        raise ValueError('Datas preservadas divergem da forma canônica.')
    if ev.retirada(state) != (state['retirado'], state['motivo_retirada']):
        raise ValueError('Retirada preservada inválida.')


def _normalizar(root, case, data, atual, _identificador):
    state = ev.mesclar(data, atual, PADROES)
    removing, reason = ev.retirada(state)
    links = ev.vinculos(root, case, state['evidencias'], minimo=1, preservar_indisponiveis=removing)
    if not any(x['papel'] == 'suporte' for x in links):
        raise ValueError('Acontecimento documentado exige ao menos uma evidência de suporte.')
    dates = state['datas']
    if atual and 'evidencias' in data and 'datas' not in data:
        mover = ev.realocar_fontes(atual['evidencias'], links, 'a data')
        dates = [{**d, 'fonte': mover(d['fonte'])} for d in dates]
    result = {'descricao': ev.texto(state['descricao'], 'Acontecimento', 1000),
              'datas': _datas(dates, links), 'evidencias': links, 'retirado': removing, 'motivo_retirada': reason}
    _regras(result)
    return result


COLECAO = ev.Colecao('linha_do_tempo', 'T', PADROES, _normalizar, _regras, 'linha do tempo')


def salvar(root, data, operation='criar', conta=None):
    return COLECAO.salvar(root, data, operation, conta)


def detalhe(root, case, identifier):
    return COLECAO.detalhe(root, case, identifier)


def listar(root, case):
    return COLECAO.listar(root, case)


def _ordem(value):
    # Partial dates sort at the start of their period, coarser precision first.
    return (value + '-00' * ((10 - len(value)) // 3), len(value))


def _compativeis(a, b):
    """Uma data contém a outra (``2024-03`` e ``2024-03-15``)?"""
    short, long_ = sorted((a, b), key=len)
    return short != long_ and long_.startswith(short)


def _divergencia(values):
    values = sorted(values)
    if len(values) < 2:
        return None
    pairs = [(a, b) for i, a in enumerate(values) for b in values[i + 1:]]
    return 'compativel_precisao_diferente' if all(_compativeis(a, b) for a, b in pairs) else 'conflitante'


def linha(root, case, *, tipos=None, incluir_retirados=False):
    """Entradas (acontecimento, data) em ordem cronológica, com a evidência de cada data aberta."""
    if tipos is not None and (not isinstance(tipos, list) or set(tipos) - set(TIPOS_DATA)):
        raise ValueError('Filtro de tipos de data inválido.')
    cache, entries, divergences, unavailable, broken = {}, [], [], [], []
    for item in COLECAO.listar(root, case):
        if item['divergente']:
            broken.append({'id': item['id'], 'erro': item['erro']})
            continue
        state = item['estado']
        if state['retirado'] and not incluir_retirados:
            continue
        links = ev.conferir_vinculos(root, case, state['evidencias'], cache)
        by_type = {}
        for d in state['datas']:
            by_type.setdefault(d['tipo'], set()).add(d['valor'])
        classes = {kind: _divergencia(values) for kind, values in by_type.items()}
        for kind, values in sorted(by_type.items()):
            if classes[kind]:
                divergences.append({'evento_id': item['id'], 'tipo': kind, 'valores': sorted(values),
                                    'classe': classes[kind],
                                    'aviso': 'Fontes registram datas diferentes do mesmo tipo; conferir os originais.'})
        for d in state['datas']:
            if tipos is not None and d['tipo'] not in tipos:
                continue
            source = links[d['fonte']]
            checked = source['estado'] == 'conferida'
            if not checked:
                unavailable.append({'evento_id': item['id'], 'tipo': d['tipo'], 'valor': d['valor'],
                                    'erro': source.get('erro')})
            entries.append({'evento_id': item['id'], 'sha256': item['sha256'], 'descricao': state['descricao'],
                            'data': {**d, 'rotulo': TIPOS_DATA[d['tipo']]}, 'fonte_da_data': source,
                            'fonte_conferida': checked, 'evidencias': links,
                            'divergente': classes[d['tipo']] is not None, 'divergencia': classes[d['tipo']],
                            'retirado': state['retirado'], 'motivo_retirada': state['motivo_retirada']})
    entries.sort(key=lambda e: (_ordem(e['data']['valor']), e['data']['tipo'], e['evento_id']))
    return {'caso': case, 'entradas': entries, 'total': len(entries), 'divergencias': divergences,
            'fontes_indisponiveis': unavailable, 'divergentes': broken, 'tipos_data': TIPOS_DATA,
            'aviso': 'Ordem por data registrada; datas parciais vão para o início do período, com a precisão mais '
                     'grossa primeiro. Tipos de data diferentes não indicam sequência causal.'}
