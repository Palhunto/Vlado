"""Quadro de hipóteses e evidências: o que sustenta, o que contraria e o que falta.

A situação de uma hipótese é declarada por uma pessoa; o quadro só organiza as
evidências vinculadas e aponta lacunas técnicas. Uma hipótese sem evidência de
suporte conferida aparece como pendência, nunca como fato. Nada aqui conclui que
uma hipótese é verdadeira nem faz chamada de modelo ou rede.
"""
import re

import evidencias as ev
import diligencias

SITUACOES = ('em_aberto', 'sustentada', 'contrariada', 'inconclusiva', 'descartada')
PADROES = {'enunciado': None, 'situacao': 'em_aberto', 'evidencias': [], 'lacunas': []}
# Situação declarada → papel exigido de uma evidência sustentada de natureza documental.
EXIGE = {'sustentada': 'suporte', 'contrariada': 'contradicao'}
# Situações que encerram a hipótese sem afirmar nada: vínculos salvos cuja fonte sumiu são preservados.
ENCERRAM = ('inconclusiva', 'descartada')


def _base(links, papel):
    """Há evidência do papel, avaliada como sustentada, que o documento declara ou atribui?"""
    return any(x['papel'] == papel and x['suporte'] == 'sustentado' and x['natureza'] in ev.NATUREZAS_DOCUMENTAIS
               for x in links)


def _lacuna(item):
    if not isinstance(item, dict) or set(item) - {'descricao', 'diligencia_id'} or 'descricao' not in item:
        raise ValueError('Lacuna inválida.')
    followup = item.get('diligencia_id')
    if followup is not None and (not isinstance(followup, str) or not re.fullmatch(diligencias.ID, followup)):
        raise ValueError('Diligência da lacuna inválida.')
    return {'descricao': ev.texto(item['descricao'], 'O que falta', 1000), 'diligencia_id': followup}


def _regras(state):
    """Regras puras do quadro, reaplicadas na leitura de cada evento do histórico."""
    if state['situacao'] not in SITUACOES:
        raise ValueError('Situação da hipótese inválida.')
    ev.texto(state['enunciado'], 'Hipótese', 1000)
    if not isinstance(state['lacunas'], list) or len(state['lacunas']) > 50:
        raise ValueError('Registre até 50 lacunas.')
    for gap in state['lacunas']:
        _lacuna(gap)
    papel = EXIGE.get(state['situacao'])
    if papel and not _base(state['evidencias'], papel):
        nome = 'suporte' if papel == 'suporte' else 'contradição'
        raise ValueError(f'Para marcar como {state["situacao"]}, vincule ao menos uma evidência de {nome} avaliada '
                         'como sustentada, de natureza declaração documental ou alegação atribuída.')


def _normalizar(root, case, data, atual, _identificador):
    state = ev.mesclar(data, atual, PADROES)
    if state['situacao'] not in SITUACOES:
        raise ValueError('Situação da hipótese inválida.')
    links = ev.vinculos(root, case, state['evidencias'], preservar_indisponiveis=state['situacao'] in ENCERRAM)
    if not isinstance(state['lacunas'], list) or len(state['lacunas']) > 50:
        raise ValueError('Registre até 50 lacunas.')
    known = {g['diligencia_id'] for g in (atual or {}).get('lacunas', []) if g['diligencia_id']}
    gaps = []
    for item in state['lacunas']:
        gap = _lacuna(item)
        if gap['diligencia_id'] and gap['diligencia_id'] not in known:
            diligencias.detalhe(root, case, gap['diligencia_id'])  # só a diligência nova é conferida
        gaps.append(gap)
    result = {'enunciado': ev.texto(state['enunciado'], 'Hipótese', 1000), 'situacao': state['situacao'],
              'evidencias': links, 'lacunas': gaps}
    _regras(result)
    return result


COLECAO = ev.Colecao('hipoteses', 'H', PADROES, _normalizar, _regras, 'hipóteses')


def salvar(root, data, operation='criar', conta=None):
    return COLECAO.salvar(root, data, operation, conta)


def detalhe(root, case, identifier):
    return COLECAO.detalhe(root, case, identifier)


def listar(root, case):
    return COLECAO.listar(root, case)


def _declarada_por(history):
    """Autor do último evento que mudou a situação (ou do que criou a hipótese)."""
    for i in range(len(history) - 1, 0, -1):
        if history[i]['estado']['situacao'] != history[i - 1]['estado']['situacao']:
            return history[i]['autor']
    return history[0]['autor']


def quadro(root, case):
    """Hipóteses com evidências separadas por papel e o que ainda falta, sem julgamento automático."""
    cache, rows, broken = {}, [], []
    for item in COLECAO.listar(root, case):
        if item['divergente']:
            broken.append({'id': item['id'], 'erro': item['erro']})
            continue
        state = item['estado']
        links = ev.conferir_vinculos(root, case, state['evidencias'], cache)
        checked = [x for x in links if x['estado'] == 'conferida']
        groups = {role: [x for x in checked if x['papel'] == role] for role in ev.PAPEIS}
        faltam = []
        for gap in state['lacunas']:
            entry = {'origem': 'registrada', 'descricao': gap['descricao'], 'diligencia_id': gap['diligencia_id'],
                     'diligencia_estado': None}
            if gap['diligencia_id']:
                try:
                    entry['diligencia_estado'] = diligencias.detalhe(root, case, gap['diligencia_id'])['diligencia']['estado']
                except ValueError as exc:
                    entry['diligencia_estado'] = 'indisponivel'; entry['erro'] = str(exc)
            faltam.append(entry)
        auto = lambda text: faltam.append({'origem': 'automatica', 'descricao': text, 'diligencia_id': None,
                                           'diligencia_estado': None})
        # "Com evidência" exige suporte conferido, avaliado como sustentado e de natureza documental.
        support = _base(checked, 'suporte')
        if not groups['suporte']:
            auto('Nenhuma evidência de suporte conferida.')
        elif all(x['natureza'] == 'pendencia' for x in groups['suporte']):
            auto('Evidências de suporte ainda marcadas como pendência; indique o tipo de afirmação.')
        elif not support:
            auto('Nenhuma evidência de suporte avaliada como sustentada, de natureza documental.')
        pending = sum(1 for x in links if x['papel'] != 'contexto' and x['suporte'] == 'nao_revisado')
        if pending:
            auto(f'{pending} evidência(s) com suporte ainda não revisado.')
        missing = len(links) - len(checked)
        if missing:
            auto(f'{missing} evidência(s) indisponível(is) para conferência no original.')
        if _base(checked, 'suporte') and _base(checked, 'contradicao'):
            auto('Há evidências sustentadas nos dois sentidos; conferir antes de concluir.')
        sustaining = [x for x in groups['suporte'] if x['suporte'] == 'sustentado']
        if sustaining and all(x['natureza'] == 'alegacao_atribuida' for x in sustaining):
            auto('Suporte sustentado apenas por alegação atribuída: a fonte atribui a afirmação a terceiros.')
        papel = EXIGE.get(state['situacao'])
        without_base = bool(papel) and not _base(checked, papel)
        if without_base:
            auto('A situação declarada perdeu a evidência conferida que a fundamentava; revisar.')
        rows.append({'id': item['id'], 'sha256': item['sha256'], 'enunciado': state['enunciado'],
                     'situacao': state['situacao'], 'situacao_declarada_por': _declarada_por(item['historico']),
                     'situacao_sem_base': without_base,
                     'condicao': 'com_evidencia' if support else 'pendencia',
                     'natureza': 'inferencia' if support else 'pendencia',
                     'sustentam': groups['suporte'], 'contrariam': groups['contradicao'],
                     'contexto': groups['contexto'], 'indisponiveis': [x for x in links if x['estado'] != 'conferida'],
                     'faltam': faltam, 'atualizado_em_utc': state['atualizado_em_utc']})
    return {'caso': case, 'hipoteses': rows, 'total': len(rows), 'divergentes': broken,
            'aviso': 'Situações declaradas por pessoas; o quadro não avalia veracidade. '
                     'Hipótese é inferência sobre as evidências; sem suporte conferido, é pendência.'}
