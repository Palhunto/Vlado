"""Seletor comum de evidência (Onda 4, P47; contrato em ``.maestro/equipe/CONTRATO_QUADROS_ONDA4.md``, seção 4).

Busca, só na apuração aberta, nos achados da IA de uma análise (a mais recente com achados, ou a rodada
escolhida) e nas fontes do caderno. Cada resultado traz a referência no formato de sempre
(``evidencias.referencia``) e o vínculo já preenchido como a P47 manda (``vinculo_ia.preenchimento``).
Sem modelo e sem rede; nada fora de ``casos/<caso>`` e ``execucoes/<caso>``.
"""
from __future__ import annotations

import re
import unicodedata

from comum import dentro
import caderno
import evidencias as ev
import lixeira
import vinculo_ia

ORIGENS = ('tudo', 'ia', 'caderno')
CAMPOS = {'caso', 'texto', 'origem', 'rodada', 'item', 'limite', 'deslocamento'}
# Board of the item being edited -> its collection (to mark "already linked to this item").
QUADROS = {'hipoteses': ('hipoteses', 'COLECAO'), 'linha_tempo': ('linha_tempo', 'COLECAO'),
           'entidades': ('mapa_relacoes', 'ENTIDADES'), 'relacoes': ('mapa_relacoes', 'RELACOES')}
MAXIMO_PERGUNTA = 300


def _normal(value):
    plain = unicodedata.normalize('NFD', value.casefold())
    return ''.join(c for c in plain if not unicodedata.combining(c))


def _pergunta(run):
    path = run / '00_pergunta_original.md'
    try:
        text = path.read_text(encoding='utf-8').strip() if path.is_file() else ''
    except (OSError, UnicodeDecodeError):
        text = ''
    return text[:MAXIMO_PERGUNTA]


def analises(root, case, cache):
    """Rounds of this case with published findings, newest first: the "Avançado" list of the selector."""
    folder = dentro(root, f'execucoes/{case}')
    result = []
    for run in sorted(folder.iterdir()) if folder.is_dir() else []:
        if not run.is_dir() or not re.fullmatch(lixeira.ID_RODADA, run.name) or lixeira.excluido(root, case, rodada=run.name):
            continue
        try:
            latest = vinculo_ia.ultima_revisao(root, case, run.name, cache)
            if latest is None:
                continue
            data, manifest = vinculo_ia._dados(root, case, run.name, latest, cache)
        except (ValueError, OSError, KeyError, TypeError):
            continue  # a round whose findings do not load offers nothing to link
        result.append({'rodada': run.name, 'revisao': latest, 'registros_sha256': manifest['registros_sha256'],
                       'em_utc': manifest.get('criado_em_utc'), 'pergunta': _pergunta(run),
                       'com_revisao': bool(data['revisoes_assistidas'])})
    result.sort(key=lambda a: (a['em_utc'] or '', a['rodada']), reverse=True)
    return result


def _ligadas(root, case, item):
    if item is None:
        return set()
    if (not isinstance(item, dict) or set(item) != {'quadro', 'id'} or item['quadro'] not in QUADROS
            or not isinstance(item['id'], str)):
        raise ValueError('Item selecionado inválido para o seletor de evidência.')
    import importlib
    module, name = QUADROS[item['quadro']]
    colecao = getattr(importlib.import_module(module), name)
    try:
        state = colecao.detalhe(root, case, item['id'])['estado']
    except ValueError as exc:
        raise ValueError('Item selecionado inválido para o seletor de evidência.') from exc
    return {ev.chave(link['referencia']) for link in state.get('evidencias', [])}


def _candidatos_ia(root, case, analise, cache):
    """One entry per (evidence, finding) in the newest version of each finding of the chosen analysis."""
    data, _ = vinculo_ia._dados(root, case, analise['rodada'], analise['revisao'], cache)
    frozen = ev._rodada(root, case, analise['rodada'], cache)
    evidences = {e['id']: e for e in data['evidencias']}
    out = []
    for claim in data['achados']:
        version = claim['versoes'][-1]
        fates = [d for d in data['destinos'] if (d['achado_id'], d['versao']) == (claim['id'], version['versao'])]
        for link in (v for v in data['vinculos'] if (v['achado_id'], v['versao']) == (claim['id'], version['versao'])):
            evidence = evidences[link['evidencia_id']]
            name = frozen['documentos'].get(evidence['documento_id'], {}).get('nome_recebido', '')
            ref = {'tipo': 'ia', 'caso_id': case, 'rodada': analise['rodada'], 'revisao': analise['revisao'],
                   'registros_sha256': analise['registros_sha256'], 'evidencia_id': evidence['id']}
            out.append({'busca': _normal(' '.join((version['redacao'], evidence['trecho'], name, evidence['documento_id']))),
                        'origem': 'ia', 'tipo_fonte': 'achado_ia', 'texto': version['redacao'], 'referencia': ref,
                        'achado': {'id': claim['id'], 'versao': version['versao'],
                                   'destino': fates[-1]['destino'] if fates else None},
                        'justificativa': link['justificativa']})
    return out


def _candidatos_caderno(root, case):
    out, offset = [], 0
    while offset is not None:
        page = caderno.listar(root, case, limite=100, deslocamento=offset)
        for entry in page['resultados']:
            record = entry['registro']
            for index, source in enumerate(record['fontes']):
                if source.get('rodada_origem') and lixeira.excluido(root, case, rodada=source['rodada_origem']):
                    continue
                text = record.get('titulo') or record.get('anotacao') or source['trecho']
                out.append({'busca': _normal(' '.join((record.get('titulo') or '', record.get('anotacao') or '',
                                                       source['trecho'], source.get('nome_documento') or '',
                                                       source.get('documento_id') or ''))),
                            'origem': 'caderno', 'tipo_fonte': record['tipo'], 'texto': text,
                            'referencia': {'tipo': 'humana', 'caso_id': case, 'registro_id': record['id'],
                                           'sha256': entry['sha256'], 'fonte': index},
                            'achado': None, 'justificativa': '', 'conferencia_textual': source['conferencia_textual']})
        offset = page['proximo_deslocamento']
    return out


def _resultado(root, case, entry, ligadas, cache):
    try:
        resolved, error = ev.resolver(root, case, entry['referencia'], cache), None
    except ValueError as exc:  # the source stopped resolving: listed as unavailable, never as linkable
        resolved, error = None, str(exc)
    # B1 of the Coruja: the values come from this result's finding, never from another finding with the same E-ID.
    review = (vinculo_ia.revisao_ia(root, case, entry['referencia'], cache, entry['achado']['id'])
              if entry['origem'] == 'ia' else None)
    fill = vinculo_ia.preenchimento(review)
    human = None
    if review is not None:
        human = vinculo_ia._marca_humana(root, case, review['rodada'], review['achado_id'], review['versao'], cache)
    result = {'origem': entry['origem'], 'tipo_fonte': entry['tipo_fonte'], 'texto': entry['texto'],
              'estado': 'conferida' if resolved else 'indisponivel', **({'erro': error} if error else {}),
              'trecho': resolved['trecho'] if resolved else None,
              'documento': {'documento_id': resolved['documento']['documento_id'],
                            'nome': resolved['documento']['nome']} if resolved else None,
              'localizador': resolved['localizador'] if resolved else None, 'achado': entry['achado'], 'revisao_ia': review,
              'conferencia_humana': human,
              'vinculo_sugerido': {'referencia': entry['referencia'], 'papel': fill['papel'], 'suporte': fill['suporte'],
                                   'natureza': fill['natureza'], 'justificativa': entry['justificativa'],
                                   **({'achado_id': entry['achado']['id']} if entry['origem'] == 'ia' else {})},
              'ja_ligado': ev.chave(entry['referencia']) in ligadas}
    if entry['origem'] == 'caderno':
        result['conferencia_textual'] = entry['conferencia_textual']
    return result


def buscar(root, case, data):
    """``evidencia-buscar``: see the contract, section 4. ``case`` was already checked by the route."""
    if not isinstance(data, dict) or set(data) - CAMPOS:
        raise ValueError('Campos inválidos no pedido do quadro.')
    query = data.get('texto', '')
    if not isinstance(query, str) or len(query) > 500:
        raise ValueError('Campos inválidos no pedido do quadro.')
    query = _normal(' '.join(query.split()))
    if len(query) == 1:
        raise ValueError('A busca precisa de ao menos 2 caracteres.')
    origin, limit, offset = data.get('origem', 'tudo'), data.get('limite', 20), data.get('deslocamento', 0)
    if (origin not in ORIGENS or type(limit) is not int or not 1 <= limit <= 50
            or type(offset) is not int or offset < 0):
        raise ValueError('Campos inválidos no pedido do quadro.')
    cache = {}
    ligadas = _ligadas(root, case, data.get('item'))
    found = analises(root, case, cache)
    chosen = data.get('rodada')
    if chosen is None:
        analise = found[0] if found else None
    else:
        if not isinstance(chosen, str) or not re.fullmatch(lixeira.ID_RODADA, chosen):
            raise ValueError('Selecione uma rodada da apuração para buscar evidências.')
        analise = next((a for a in found if a['rodada'] == chosen), None)
        if analise is None:
            raise ValueError('Rodada sem achados publicados nesta apuração.')
    entries = []
    if origin in ('tudo', 'ia') and analise is not None:
        entries += _candidatos_ia(root, case, analise, cache)
    if origin in ('tudo', 'caderno'):
        entries += _candidatos_caderno(root, case)
    if query:
        entries = [e for e in entries if query in e['busca']]
    page = entries[offset:offset + limit]
    return {'caso': case, 'analise': analise, 'analises': found, 'total': len(entries),
            'deslocamento': offset, 'proximo_deslocamento': offset + limit if offset + limit < len(entries) else None,
            'resultados': [_resultado(root, case, e, ligadas, cache) for e in page]}
