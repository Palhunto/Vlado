"""Comparação entre processos com campos estruturados (L9; contrato CONTRATO_QUADROS_ONDA4, seção 5).

A revisão do modo mesa (MESA.md 1.3.0 ou depois) pode trazer ``comparacoes``: o mesmo fundamento (documento,
parecer) em dois processos, a chave que os liga (identificador, data, emissor, versão), a questão, a fase e o
desfecho de cada lado, e as seis conferências da revisão da IA (mesma versão, data, emissor, trecho, questão e
fase). ``conferir`` valida cada comparação contra a revisão publicada; a malformada sozinha é recusada e fica
registrada. Os aceitos e os recusados vão para ``saidas/achados/comparacoes/<revisao>.json``, preso ao hash da
revisão. A leitura (``comparar-processos``) confere de novo e resolve as evidências na revisão mais recente da
rodada. A diferença de desfecho não prova irregularidade, e nada aqui a chama de erro. Sem modelo e sem rede.
"""
from __future__ import annotations

import re

from comum import dentro, ler_json
from registros_achados import base as base_achados
import evidencias as ev
import lixeira
import seletor_evidencia
import vinculo_ia

ESQUEMA = 1
PASTA = 'comparacoes'
MAXIMO = 20
CONFERENCIAS = ('versao', 'data', 'emissor', 'trecho', 'questao', 'fase')
RESULTADOS = ('mesmo', 'diferente', 'a_conferir')
CAMPOS = {'achado_id', 'chave', 'lados', 'conferencias'}
CAMPOS_CHAVE = ('identificador', 'data', 'emissor', 'versao')
CAMPOS_LADO = {'processo', 'fundamento', 'questao', 'fase', 'desfecho', 'desfecho_evidencia'}
LIMITES_LADO = {'processo': 300, 'questao': 500, 'fase': 120, 'desfecho': 1000}


class Recusa(ValueError):
    def __init__(self, codigo, mensagem):
        self.codigo = codigo
        super().__init__(mensagem)


def estrutura(lista):
    if not isinstance(lista, list) or len(lista) > MAXIMO or not all(isinstance(i, dict) for i in lista):
        raise ValueError(f'Comparações entre processos: envie uma lista de até {MAXIMO} comparações.')
    return lista


def _texto(value, field, maximum, vazio=False):
    try:
        return ev.texto(value, field, maximum, vazio=vazio)
    except ValueError as exc:
        raise Recusa('campo_invalido', str(exc)) from exc


def _uma(item, data):
    if set(item) != CAMPOS:
        raise Recusa('campos_invalidos', 'A comparação tem campos a mais ou a menos.')
    claim = next((c for c in data['achados'] if c['id'] == item['achado_id']), None)
    if claim is None:
        raise Recusa('achado_inexistente', 'O achado da comparação não está publicado nesta rodada.')
    own = {v['evidencia_id'] for v in data['vinculos'] if v['achado_id'] == claim['id']}
    key = item['chave']
    if not isinstance(key, dict) or set(key) != set(CAMPOS_CHAVE):
        raise Recusa('campos_invalidos', 'A chave da comparação tem identificador, data, emissor e versão.')
    sides = item['lados']
    if not isinstance(sides, list) or len(sides) != 2:
        raise Recusa('campos_invalidos', 'A comparação tem exatamente dois lados.')
    clean_sides = []
    for side in sides:
        if not isinstance(side, dict) or set(side) != CAMPOS_LADO:
            raise Recusa('campos_invalidos', 'Cada lado tem processo, fundamento, questão, fase, desfecho e a evidência do desfecho.')
        for field in ('fundamento', 'desfecho_evidencia'):
            value = side[field]
            if (value is not None or field == 'fundamento') and value not in own:
                raise Recusa('evidencia_fora_do_achado', f'{value} não é evidência publicada de {claim["id"]}.')
        clean_sides.append({**{k: _texto(side[k], k, n) for k, n in LIMITES_LADO.items()},
                            'fundamento': side['fundamento'], 'desfecho_evidencia': side['desfecho_evidencia']})
    if clean_sides[0]['fundamento'] == clean_sides[1]['fundamento']:
        raise Recusa('lados_iguais', 'Os dois lados citam a mesma evidência do fundamento.')
    checks = item['conferencias']
    if (not isinstance(checks, dict) or set(checks) != set(CONFERENCIAS)
            or not all(checks[k] in RESULTADOS for k in CONFERENCIAS)):
        raise Recusa('conferencias_invalidas', 'As seis conferências são mesmo, diferente ou a_conferir.')
    return {'achado_id': claim['id'], 'chave': {k: _texto(key[k], k, 300, vazio=True) for k in CAMPOS_CHAVE},
            'lados': clean_sides, 'conferencias': {k: checks[k] for k in CONFERENCIAS}}


def conferir(lista, data):
    accepted, refused = [], []
    for index, item in enumerate(lista):
        try:
            accepted.append(_uma(item, data))
        except Recusa as exc:
            refused.append({'indice': index, 'codigo': exc.codigo, 'motivo': str(exc)})
        except (KeyError, TypeError, AttributeError):
            refused.append({'indice': index, 'codigo': 'campos_invalidos', 'motivo': 'Comparação malformada.'})
    return accepted, refused


def caminho(run, revisao):
    return dentro(base_achados(run), f'{PASTA}/{revisao}.json')


def gravar(run, data, lista, versao_mesa):
    """Written before the review is published, with the hash the publication will have (as the candidates)."""
    import sugestoes_quadros
    return sugestoes_quadros.gravar(run, data, lista, versao_mesa, pasta=PASTA, chave='comparacoes',
                                    conferir_lista=conferir)


def _resolvida(root, case, ref, achado_id, cache):
    # N2 of the Coruja on the forms: the review and the P47 fill of each evidence, so "Criar hipótese com esta
    # comparação" links them as the AI said, never with a role or support fixed as if a person had chosen it.
    try:
        review = vinculo_ia.revisao_ia(root, case, ref, cache, achado_id)
    except ValueError:
        review = None
    fill = vinculo_ia.preenchimento_atual(root, case, ref, review, cache)
    common = {'achado_id': achado_id, 'revisao_ia': review, 'preenchimento': fill}
    try:
        resolved = ev.resolver(root, case, ref, cache)
    except ValueError as exc:
        return {'referencia': ref, **common, 'estado': 'indisponivel', 'erro': str(exc), 'documento': None,
                'localizador': None, 'trecho': None, 'original_sha256': None}
    return {'referencia': ref, **common, 'estado': 'conferida',
            'documento': {'documento_id': resolved['documento']['documento_id'], 'nome': resolved['documento']['nome']},
            'localizador': resolved['localizador'], 'trecho': resolved['trecho'],
            'original_sha256': resolved['documento']['original_sha256']}


def comparar(root, case, data):
    """``comparar-processos``: the structured comparisons of an analysis (the newest with findings, or ``rodada``)."""
    if not isinstance(data, dict) or set(data) - {'caso', 'rodada'}:
        raise ValueError('Campos inválidos no pedido do quadro.')
    cache = {}
    found = seletor_evidencia.analises(root, case, cache)
    chosen = data.get('rodada')
    if chosen is None:
        analise = found[0] if found else None
    else:
        if not isinstance(chosen, str) or not re.fullmatch(lixeira.ID_RODADA, chosen):
            raise ValueError('Selecione uma rodada da apuração para buscar evidências.')
        analise = next((a for a in found if a['rodada'] == chosen), None)
        if analise is None:
            raise ValueError('Rodada sem achados publicados nesta apuração.')
    result = {'caso': case, 'analise': analise, 'estruturada': False, 'comparacoes': []}
    if analise is None:
        return result
    run = dentro(root, f'execucoes/{case}/{analise["rodada"]}')
    folder = dentro(base_achados(run), PASTA)
    latest, _ = vinculo_ia._dados(root, case, analise['rodada'], analise['revisao'], cache)
    for path in sorted(folder.glob('*.json')) if folder.is_dir() else []:
        try:
            record = ler_json(dentro(folder, path.name))
            own, manifest = vinculo_ia._dados(root, case, analise['rodada'], path.stem, cache)
            if (record.get('esquema') != ESQUEMA or record.get('caso_id') != case or record.get('rodada') != analise['rodada']
                    or record.get('revisao') != path.stem or record.get('registros_sha256') != manifest['registros_sha256']):
                continue
            accepted, _ = conferir(estrutura(record['comparacoes']), own)
        except (ValueError, OSError, KeyError, TypeError):
            continue
        result['estruturada'] = True
        for item in accepted:
            result['comparacoes'].append(_leitura(root, case, analise, latest, item, cache))
    return result


def _leitura(root, case, analise, latest, item, cache):
    claim = next(c for c in latest['achados'] if c['id'] == item['achado_id'])
    version = claim['versoes'][-1]
    key = (claim['id'], version['versao'])
    reviews = [r for r in latest['revisoes_assistidas'] if (r['achado_id'], r['versao']) == key]
    fates = [d for d in latest['destinos'] if (d['achado_id'], d['versao']) == key]
    ref = lambda eid: {'tipo': 'ia', 'caso_id': case, 'rodada': analise['rodada'], 'revisao': analise['revisao'],
                       'registros_sha256': analise['registros_sha256'], 'evidencia_id': eid}
    sides = []
    for side in item['lados']:
        sides.append({**{k: side[k] for k in LIMITES_LADO},
                      'fundamento': _resolvida(root, case, ref(side['fundamento']), item['achado_id'], cache),
                      'desfecho_evidencia': (_resolvida(root, case, ref(side['desfecho_evidencia']), item['achado_id'], cache)
                                             if side['desfecho_evidencia'] else None)})
    hashes = [s['fundamento']['original_sha256'] for s in sides]
    support = reviews[-1]['suporte'] if reviews else 'nao_revisado'
    fate = fates[-1]['destino'] if fates else None
    pending = (support != 'sustentado' or version['natureza'] == 'pendencia' or fate == 'pendencia'
               or any(v != 'mesmo' for v in item['conferencias'].values()))
    return {'achado': {'id': claim['id'], 'versao': version['versao'], 'redacao': version['redacao'],
                       'natureza': version['natureza'], 'suporte_ia': support, 'destino': fate},
            'chave': item['chave'], 'lados': sides, 'conferencias': item['conferencias'],
            'mesmo_arquivo': None not in hashes and hashes[0] == hashes[1], 'pendente': pending,
            'revisao_ia': vinculo_ia.revisao_ia(root, case, ref(item['lados'][0]['fundamento']), cache, item['achado_id'])}
