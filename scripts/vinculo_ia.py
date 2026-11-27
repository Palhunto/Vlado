"""Registro do vínculo (Onda 4, P47 e #registro-vinculo): o que a revisão da IA disse e o que uma pessoa mudou.

Um vínculo dos quadros (``evidencias.Colecao``) guarda, além de referência, papel, suporte, natureza e
justificativa, dois campos opcionais, sempre calculados pelo servidor e nunca aceitos do cliente:

- ``revisao_ia``: no vínculo com evidência dos achados, os valores da revisão da IA no momento de ligar
  (papel, suporte e natureza), com a análise (rodada, revisão, hash), a versão do achado e o destino;
- ``alteracoes``: por campo (papel, suporte, natureza), a última mudança feita por pessoa: valor anterior,
  valor novo, quem e quando. No vínculo do caderno, só o suporte (quem o escolheu e quando).

Na leitura, ``leitura`` acrescenta o que é calculado agora: a conferência humana do achado, o destino atual
e a versão nova do achado na rodada, e se o suporte é só da IA. Vínculo antigo volta sem nada disso: a tela
não deduz o que o registro não traz. Rodada na lixeira não alimenta nenhum desses campos.

A mesma E-ID pode estar ligada a mais de um achado (o validador dos achados deixa). Os valores da revisão vêm
sempre do achado escolhido: o vínculo de entrada leva ``achado_id`` quando a E-ID está em mais de um achado, e
sem a escolha o servidor recusa. Uma E-ID que não está ligada a nenhum achado também é recusada ao ligar nos
quadros: não há revisão da IA para mostrar. Sem modelo e sem rede; só lê ``execucoes/<caso>``.
"""
from __future__ import annotations

import re

from comum import dentro, ler_json
from indice_sqlite import caminho_rodada
from registros_achados import NATUREZAS, SUPORTES, base, carregar, listar
import lixeira
import revisao_humana

CAMPOS_REVISAO = ('rodada', 'revisao', 'registros_sha256', 'achado_id', 'versao', 'papel', 'suporte', 'natureza',
                  'destino')
CAMPOS_ALTERACAO = ('anterior', 'valor', 'por', 'conta_id', 'em_utc')
ALTERAVEIS = ('papel', 'suporte', 'natureza')
DESTINOS = ('incluido', 'fora_do_briefing', 'pendencia', 'retirado', 'substituido')
PAPEIS = ('suporte', 'contradicao', 'contexto')
# Collections whose links keep this record (the four boards of the spec). The others keep their links as before.
COLECOES = ('hipoteses', 'linha_do_tempo', 'entidades', 'relacoes')
_HASH = r'[a-f0-9]{64}'
ID_ACHADO = r'A[0-9]{3,}'


def _dados(root, case, rodada, revisao, cache):
    """The published revision, through the same cache key ``evidencias._resolver_ia`` uses."""
    key = ('ia', case, rodada, revisao)
    if key not in cache:
        cache[key] = carregar(root, case, rodada, revisao)
    return cache[key]


def _manifestos(root, case, rodada, cache):
    """{revision: manifest} of the round, read from the manifests only (the chain is validated once, when the
    newest revision is loaded; R2 of the Coruja)."""
    key = ('manifestos', case, rodada)
    if key not in cache:
        folder = dentro(base(caminho_rodada(root, case, rodada)), 'revisoes')
        cache[key] = {name: ler_json(dentro(folder, f'{name}/manifesto.json')) for name in listar(root, case, rodada)['revisoes']}
    return cache[key]


def ultima_revisao(root, case, rodada, cache):
    """Name of the newest published revision of the round (the end of the linear chain), or None."""
    key = ('ultima_revisao', case, rodada)
    if key not in cache:
        manifests = _manifestos(root, case, rodada, cache)
        anteriores = {m['anterior']['revisao'] for m in manifests.values() if m.get('anterior')}
        ends = [n for n in manifests if n not in anteriores]
        cache[key] = ends[0] if len(ends) == 1 else None
    return cache[key]


def achados_da_evidencia(data, evidencia_id):
    """Findings whose published links carry this E-ID, in ID order."""
    return sorted({v['achado_id'] for v in data['vinculos'] if v['evidencia_id'] == evidencia_id})


def _valores(data, manifest, rodada, evidencia_id, achado_id=None):
    """What the published revision says about this E-ID in one finding: its newest version that links it.

    ``achado_id`` chooses the finding; without it, the E-ID must be in a single finding (else ValueError, so the
    values of one finding never pass as another's). None when the E-ID links no finding."""
    owners = achados_da_evidencia(data, evidencia_id)
    if achado_id is not None:
        if achado_id not in owners:
            raise ValueError(f'O achado indicado ({achado_id}) não está ligado a {evidencia_id} nesta revisão.')
    elif len(owners) > 1:
        raise ValueError(f'{evidencia_id} está ligada a mais de um achado ({", ".join(owners)}); indique o achado '
                         '(achado_id) ao ligar a evidência.')
    elif not owners:
        return None
    else:
        achado_id = owners[0]
    links = [v for v in data['vinculos'] if v['evidencia_id'] == evidencia_id and v['achado_id'] == achado_id]
    link = max(links, key=lambda v: v['versao'])
    claim = next(c for c in data['achados'] if c['id'] == link['achado_id'])
    version = next(v for v in claim['versoes'] if v['versao'] == link['versao'])
    reviews = [r for r in data['revisoes_assistidas'] if (r['achado_id'], r['versao']) == (claim['id'], link['versao'])]
    fates = [d for d in data['destinos'] if (d['achado_id'], d['versao']) == (claim['id'], link['versao'])]
    return {'rodada': rodada, 'revisao': data['revisao'], 'registros_sha256': manifest['registros_sha256'],
            'achado_id': claim['id'], 'versao': link['versao'], 'papel': link['papel'],
            'suporte': reviews[-1]['suporte'] if reviews else 'nao_revisado', 'natureza': version['natureza'],
            'destino': fates[-1]['destino'] if fates else None,
            '_ultima_versao': claim['versoes'][-1]['versao'], '_justificativa': link['justificativa']}


def revisao_ia(root, case, ref, cache, achado_id=None):
    """``revisao_ia`` of a reference to the findings, in the chosen finding (None for the notebook or when the
    E-ID links no finding; ValueError when it links several and none was chosen)."""
    if ref.get('tipo') != 'ia':
        return None
    data, manifest = _dados(root, case, ref['rodada'], ref['revisao'], cache)
    values = _valores(data, manifest, ref['rodada'], ref['evidencia_id'], achado_id)
    return {k: values[k] for k in CAMPOS_REVISAO} if values else None


def justificativa_ia(root, case, ref, cache, achado_id=None):
    data, manifest = _dados(root, case, ref['rodada'], ref['revisao'], cache)
    values = _valores(data, manifest, ref['rodada'], ref['evidencia_id'], achado_id)
    return values['_justificativa'] if values else ''


def escolha(item):
    """The optional ``achado_id`` of an input link (only for evidence of the findings); ValueError if malformed."""
    value = item.get('achado_id') if isinstance(item, dict) else None
    if value is None:
        return None
    ref = item.get('referencia')
    if not isinstance(value, str) or not re.fullmatch(ID_ACHADO, value) or not isinstance(ref, dict) or ref.get('tipo') != 'ia':
        raise ValueError('Achado do vínculo inválido: indique o achado (A001) só em evidência dos achados.')
    return value


def preenchimento(revisao):
    """P47: papel, suporte and natureza a new link starts with. ``revisao`` None = notebook source: role
    "suporte" (the person may change it), support "not reviewed" and no nature (the person picks it)."""
    if revisao is None:
        return {'papel': 'suporte', 'suporte': 'nao_revisado', 'natureza': None}
    suporte = revisao['suporte']
    if (revisao['destino'] == 'retirado' or revisao['papel'] == 'contexto'
            or revisao['natureza'] == 'pendencia' and suporte == 'sustentado'):
        suporte = 'nao_revisado'
    return {'papel': revisao['papel'], 'suporte': suporte, 'natureza': revisao['natureza']}


def validar(item):
    """Shape of the optional fields of a saved link (raises ValueError)."""
    error = ValueError('Vínculo de evidência preservado é inválido.')
    review = item.get('revisao_ia')
    if 'revisao_ia' in item:
        if (not isinstance(review, dict) or set(review) != set(CAMPOS_REVISAO)
                or item['referencia'].get('tipo') != 'ia'
                or not isinstance(review['rodada'], str) or not re.fullmatch(r'R[0-9]{3,6}', review['rodada'])
                or not isinstance(review['revisao'], str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,31}', review['revisao'])
                or not isinstance(review['registros_sha256'], str) or not re.fullmatch(_HASH, review['registros_sha256'])
                or not isinstance(review['achado_id'], str) or not re.fullmatch(r'A[0-9]{3,}', review['achado_id'])
                or type(review['versao']) is not int or review['versao'] < 1
                or review['papel'] not in PAPEIS or review['suporte'] not in SUPORTES
                or review['natureza'] not in NATUREZAS or not (review['destino'] is None or review['destino'] in DESTINOS)):
            raise error
    if 'alteracoes' in item:
        changes = item['alteracoes']
        allowed = ALTERAVEIS if review is not None else ('suporte',) if item['referencia'].get('tipo') == 'humana' else ()
        if not isinstance(changes, dict) or not changes or set(changes) - set(allowed):
            raise error
        for field, change in changes.items():
            enum = {'papel': PAPEIS, 'suporte': SUPORTES, 'natureza': NATUREZAS}[field]
            if (not isinstance(change, dict) or set(change) != set(CAMPOS_ALTERACAO)
                    or change['anterior'] not in enum or change['valor'] not in enum or change['valor'] != item[field]
                    or change['anterior'] == change['valor']
                    or not isinstance(change['por'], str) or not 0 < len(change['por']) <= 120
                    or not (change['conta_id'] is None or isinstance(change['conta_id'], str))
                    or not isinstance(change['em_utc'], str) or not 0 < len(change['em_utc']) <= 64):
                raise error


def _pares(novos, antigos, chave):
    """Pairs each new link with the previous one of the same reference (same role first)."""
    livres = list(range(len(antigos)))
    pares = [None] * len(novos)
    for match_role in (True, False):
        for i, link in enumerate(novos):
            if pares[i] is not None:
                continue
            for j in livres:
                old = antigos[j]
                if chave(old['referencia']) == chave(link['referencia']) and (not match_role or old['papel'] == link['papel']):
                    pares[i] = old
                    livres.remove(j)
                    break
    return pares


def registrar(root, case, novos, antigos, quem, agora, chave, escolhas=None, cache=None):
    """Fills ``revisao_ia`` and ``alteracoes`` of the links about to be saved (in place).

    ``novos`` come from ``evidencias.vinculos`` (canonical, without the optional fields); ``antigos`` are the
    links of the current state (empty on creation); ``escolhas`` is the ``achado_id`` each input link chose
    (or None). A link kept from before keeps the ``revisao_ia`` of the moment it was linked (a legacy link,
    without it, stays without it), unless another finding is chosen now; a new link to the findings gets it
    now, from the chosen finding, and is refused (ValueError) when the E-ID links no finding or several without
    a choice. A field equal to what the AI review gives (P47) carries no mark; a field changed now is marked
    with who and when; a field already marked and unchanged keeps its mark.
    """
    cache = {} if cache is None else cache
    escolhas = escolhas or [None] * len(novos)
    for link, old, chosen in zip(novos, _pares(novos, antigos, chave), escolhas):
        link.pop('revisao_ia', None); link.pop('alteracoes', None)
        kept = old.get('revisao_ia') if old is not None else None
        if old is not None and (chosen is None or kept is None or kept['achado_id'] == chosen):
            review = kept
        else:
            old = None  # another finding chosen for the same evidence: a new link, compared with its own review
            review = revisao_ia(root, case, link['referencia'], cache, chosen)
            if review is None and link['referencia']['tipo'] == 'ia':
                raise ValueError(f'{link["referencia"]["evidencia_id"]} não está ligada a nenhum achado desta revisão, '
                                 'então não tem revisão da IA; ligue uma evidência de um achado.')
        human = link['referencia']['tipo'] == 'humana'
        if review is None and not human:
            continue  # legacy link to the findings: nothing to compare with
        if review is not None:
            link['revisao_ia'] = review
        base = preenchimento(review)
        changes = {}
        for field in (ALTERAVEIS if review is not None else ('suporte',)):
            if link[field] == base[field]:
                continue  # the AI's value (or "not reviewed" in the notebook): "back to the AI's" clears the mark
            if old is not None and link[field] == old[field]:
                mark = old.get('alteracoes', {}).get(field)
                if mark is not None:  # unchanged: the mark stays; a value from before this record has no author
                    changes[field] = mark
                continue
            changes[field] = {'anterior': old[field] if old is not None else base[field], 'valor': link[field],
                              'por': quem['autor'], 'conta_id': quem.get('conta_id'), 'em_utc': agora}
        if changes:
            link['alteracoes'] = changes


def _marca_humana(root, case, rodada, achado_id, versao, cache):
    key = ('marcas', case, rodada)
    if key not in cache:
        run = caminho_rodada(root, case, rodada)
        events = []
        for name, manifest in _manifestos(root, case, rodada, cache).items():
            events.extend(revisao_humana._historico(run, name, manifest['registros_sha256'])[0])
        cache[key] = events
    history = [e for e in cache[key] if (e['achado_id'], e['achado_versao']) == (achado_id, versao)]
    if not history:
        return None
    last = max(history, key=lambda e: e['em_utc'])
    return {'estado': last['estado'], 'por': last.get('responsavel'), 'em_utc': last['em_utc']}


def atual(root, case, ref, cache, achado_id=None):
    """What the newest revision of the round says about the E-ID in the finding: ``(values, referencia)`` or
    ``(None, None)``."""
    latest = ultima_revisao(root, case, ref['rodada'], cache)
    if latest is None:
        return None, None
    data, manifest = _dados(root, case, ref['rodada'], latest, cache)
    values = _valores(data, manifest, ref['rodada'], ref['evidencia_id'], achado_id)
    if values is None:
        return None, None
    return values, {**ref, 'revisao': latest, 'registros_sha256': manifest['registros_sha256']}


def leitura(root, case, item, cache):
    """Read-time fields of a link: the saved record plus what is computed now (see the module docstring)."""
    review = item.get('revisao_ia')
    changes = item.get('alteracoes') or {}
    out = {'revisao_ia': review, 'alteracoes': changes, 'conferencia_humana': None, 'destino_atual': None,
           'versao_nova': None, 'suporte_so_da_ia': False}
    ref = item.get('referencia') or {}
    if ref.get('tipo') != 'ia' or lixeira.excluido(root, case, rodada=ref['rodada']):
        return out  # a round in the trash feeds nothing (R1 of the Coruja)
    try:
        own = review or revisao_ia(root, case, ref, cache)
        values, newest = atual(root, case, ref, cache, own['achado_id'] if own else None)
        if own is not None:
            out['conferencia_humana'] = _marca_humana(root, case, ref['rodada'], own['achado_id'], own['versao'], cache)
        if values is not None:
            out['destino_atual'] = values['destino']
            if own is not None and values['versao'] > own['versao']:
                out['versao_nova'] = {'referencia': newest, 'achado_id': values['achado_id'], 'versao': values['versao'],
                                      'revisao_ia': {k: values[k] for k in CAMPOS_REVISAO}}
    except (ValueError, OSError, KeyError, TypeError):
        return out  # the source is unavailable: conferir_vinculos already says so
    conferida = (out['conferencia_humana'] or {}).get('estado') == 'conferida_no_original'
    out['suporte_so_da_ia'] = (review is not None and 'suporte' not in changes and item.get('suporte') == review['suporte']
                               and not conferida)
    return out
