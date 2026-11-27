"""Sugestões da IA para os quadros (Onda 4, P45; contrato em ``.maestro/equipe/CONTRATO_QUADROS_ONDA4.md``, seções 1 e 2).

A síntese pode trazer ``candidatos``: pessoa, organização, ligação, acontecimento datado e hipótese, cada um preso a
evidências publicadas de um achado da rodada. ``conferir`` valida cada candidato contra a revisão publicada (sem
modelo): o que não tem referência válida é recusado sozinho e fica registrado, o resto vira sugestão. Os candidatos
de uma rodada ficam em ``saidas/achados/candidatos/<revisao>.json``, imutável e preso ao hash da revisão; a leitura
confere tudo de novo, também nos arquivos do agente de chat.

As decisões das pessoas (confirmar, corrigir, descartar, restaurar) são eventos em ``casos/<caso>/quadros/sugestoes``
(``evidencias.Colecao``), uma decisão por registro. Confirmar põe o item no quadro com o vínculo preenchido pela P47;
a sugestão nunca aparece como conferida, e a hipótese confirmada nasce "em aberto". Sem modelo e sem rede.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
import re
import uuid
import unicodedata

from comum import dentro, escrever_json, ler_json
from indice_sqlite import caminho_rodada
from registros_achados import base as base_achados
import caderno
import evidencias as ev
import hipoteses
import linha_tempo
import lixeira
import mapa_relacoes as mapa
import vinculo_ia

ESQUEMA = 1
TIPOS = ('pessoa', 'organizacao', 'ligacao', 'acontecimento', 'hipotese')
QUADRO_DO_TIPO = {'pessoa': 'mapa', 'organizacao': 'mapa', 'ligacao': 'mapa', 'acontecimento': 'linha_tempo',
                  'hipotese': 'hipoteses'}
QUADROS = ('mapa', 'linha_tempo', 'hipoteses')
MAXIMO = 40
MAXIMO_EVIDENCIAS = 5
CHAVE = re.compile(r'C[1-9][0-9]{0,2}')
ID = r'S[a-f0-9]{32}'
CAMPOS_CANDIDATO = {'chave', 'tipo', 'achado_id', 'evidencias', 'campos'}
CAMPOS = {'pessoa': ({'nome'}, {'variantes'}), 'organizacao': ({'nome'}, {'variantes'}),
          'ligacao': ({'de', 'para', 'tipo'}, {'descricao'}), 'acontecimento': ({'descricao', 'datas'}, set()),
          'hipotese': ({'enunciado'}, set())}
CAMPOS_DATA = {'tipo', 'valor', 'aproximada', 'fonte', 'observacao'}
ACOES = ('confirmar', 'corrigir', 'descartar', 'restaurar')
PASTA = 'candidatos'
# CPF (000.000.000-00) or CNPJ (00.000.000/0000-00), with or without punctuation, anywhere in the candidate's text.
_SEP = r'[\s.\-\u2010-\u2015/]{0,3}'  # spaces, dots, hyphens and dashes, slash, between the groups (R3)
DOCUMENTO_PESSOAL = re.compile(rf'(?<!\d)(\d{{3}}{_SEP}\d{{3}}{_SEP}\d{{3}}{_SEP}\d{{2}}'
                               rf'|\d{{2}}{_SEP}\d{{3}}{_SEP}\d{{3}}{_SEP}\d{{4}}{_SEP}\d{{2}})(?![\d])')


class Recusa(ValueError):
    """One candidate refused: ``codigo`` is stored with it (never shown as a suggestion)."""

    def __init__(self, codigo, mensagem):
        self.codigo = codigo
        super().__init__(mensagem)


# --- candidates ----------------------------------------------------------------------------------------------------

def aplica(instrucoes):
    """The synthesis takes ``candidatos`` only in rounds frozen in the mesa mode with MESA.md 1.3.0 or later."""
    if (instrucoes or {}).get('modo') != 'mesa':
        return False
    try:
        versao = tuple(int(x) for x in str(instrucoes.get('versao') or '').split('.'))
    except ValueError:
        return False
    return len(versao) == 3 and versao >= (1, 3, 0)


def estrutura(lista):
    """Shape of the whole list (a malformed list refuses the synthesis, so the model fixes it)."""
    if not isinstance(lista, list) or len(lista) > MAXIMO:
        raise ValueError(f'Candidatos para os quadros: envie uma lista de até {MAXIMO} candidatos.')
    chaves = [item.get('chave') if isinstance(item, dict) else None for item in lista]
    if not all(isinstance(c, str) and CHAVE.fullmatch(c) for c in chaves) or len(set(chaves)) != len(chaves):
        raise ValueError('Candidatos para os quadros: cada candidato precisa de uma chave única, de C1 a C999.')
    return lista


def _texto(value, field, maximum, *, vazio=False):
    try:
        return ev.texto(value, field, maximum, vazio=vazio)
    except ValueError as exc:
        raise Recusa('campo_invalido', str(exc)) from exc


def _um(item, data, aceitos):
    if set(item) != CAMPOS_CANDIDATO:
        raise Recusa('campos_invalidos', 'O candidato tem campos a mais ou a menos.')
    kind = item['tipo']
    if kind not in TIPOS:
        raise Recusa('tipo_invalido', 'Tipo de candidato inválido.')
    claim = next((c for c in data['achados'] if c['id'] == item['achado_id']), None)
    if claim is None:
        raise Recusa('achado_inexistente', 'O achado do candidato não está publicado nesta rodada.')
    eids = item['evidencias']
    if (not isinstance(eids, list) or not 1 <= len(eids) <= MAXIMO_EVIDENCIAS or len(set(eids)) != len(eids)
            or not all(isinstance(e, str) for e in eids)):
        raise Recusa('evidencias_invalidas', f'Indique de 1 a {MAXIMO_EVIDENCIAS} evidências diferentes do achado.')
    roles = {}
    for eid in eids:
        links = [v for v in data['vinculos'] if v['achado_id'] == claim['id'] and v['evidencia_id'] == eid]
        if not links:
            raise Recusa('evidencia_fora_do_achado', f'{eid} não é evidência publicada de {claim["id"]}.')
        roles[eid] = max(links, key=lambda v: v['versao'])['papel']
    fields = item['campos']
    required, optional = CAMPOS[kind]
    if not isinstance(fields, dict) or not required <= set(fields) <= required | optional:
        raise Recusa('campos_invalidos', 'Campos do candidato inválidos para o tipo.')
    if kind in ('ligacao', 'acontecimento') and 'suporte' not in roles.values():
        raise Recusa('sem_suporte', 'Ligação e acontecimento precisam de uma evidência de suporte.')
    if kind in ('pessoa', 'organizacao'):
        variants = fields.get('variantes', [])
        if not isinstance(variants, list) or len(variants) > 20:
            raise Recusa('campo_invalido', 'Registre até 20 variantes de nome.')
        campos = {'nome': _texto(fields['nome'], 'Nome', 300),
                  'variantes': list(dict.fromkeys(_texto(v, 'Variante de nome', 300) for v in variants))}
    elif kind == 'ligacao':
        ends = (fields['de'], fields['para'])
        if (not all(isinstance(e, str) and aceitos.get(e) in ('pessoa', 'organizacao') for e in ends)
                or ends[0] == ends[1]):
            raise Recusa('ponta_invalida', 'As pontas da ligação são duas pessoas ou organizações aceitas desta lista.')
        campos = {'de': ends[0], 'para': ends[1], 'tipo': _texto(fields['tipo'], 'Tipo de relação', 120),
                  'descricao': _texto(fields.get('descricao', ''), 'Descrição', 2000, vazio=True)}
    elif kind == 'acontecimento':
        dates = fields['datas']
        if not isinstance(dates, list) or not 1 <= len(dates) <= 10:
            raise Recusa('datas_invalidas', 'Informe de 1 a 10 datas.')
        clean = []
        for value in dates:
            if not isinstance(value, dict) or not {'tipo', 'valor'} <= set(value) <= CAMPOS_DATA:
                raise Recusa('datas_invalidas', 'Data do acontecimento inválida.')
            source = value.get('fonte', 0)
            if (value['tipo'] not in linha_tempo.TIPOS_DATA or type(source) is not int or not 0 <= source < len(eids)
                    or type(value.get('aproximada', False)) is not bool):
                raise Recusa('datas_invalidas', 'Data do acontecimento inválida.')
            try:
                linha_tempo.data_parcial(value['valor'])
            except ValueError as exc:
                raise Recusa('datas_invalidas', str(exc)) from exc
            role = roles[eids[source]]
            if role == 'contradicao' or role == 'contexto' and value['tipo'] != 'declarada_por_fonte':
                raise Recusa('datas_invalidas', 'A fonte da data precisa ser evidência de suporte (ou de contexto, '
                                                'para data declarada por fonte).')
            clean.append({'tipo': value['tipo'], 'valor': value['valor'], 'aproximada': value.get('aproximada', False),
                          'fonte': source,
                          'observacao': _texto(value.get('observacao', ''), 'Observação da data', 500, vazio=True)})
        campos = {'descricao': _texto(fields['descricao'], 'Acontecimento', 1000), 'datas': clean}
    else:
        campos = {'enunciado': _texto(fields['enunciado'], 'Hipótese', 1000)}
    if any(DOCUMENTO_PESSOAL.search(text) for text in _textos(campos)):
        raise Recusa('dado_pessoal', 'O candidato traz CPF ou CNPJ no texto; identificadores ficam para a pessoa digitar.')
    return {'chave': item['chave'], 'tipo': kind, 'achado_id': claim['id'], 'evidencias': list(eids), 'campos': campos}


def _textos(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _textos(item)
    elif isinstance(value, list):
        for item in value:
            yield from _textos(item)


def conferir(lista, data):
    """``(aceitos, recusados)`` of a structurally valid list against the published revision ``data``."""
    accepted, refused, kinds = [], [], {}
    # Entities first: a link is accepted only with both ends accepted.
    ordered = sorted(enumerate(lista), key=lambda pair: pair[1].get('tipo') == 'ligacao')
    results = {}
    for index, item in ordered:
        try:
            ok = _um(item, data, kinds)
            kinds[ok['chave']] = ok['tipo']
            results[index] = ('ok', ok)
        except Recusa as exc:
            results[index] = ('no', {'chave': item.get('chave'), 'codigo': exc.codigo, 'motivo': str(exc)})
        except (KeyError, TypeError, AttributeError):
            results[index] = ('no', {'chave': item.get('chave'), 'codigo': 'campos_invalidos',
                                     'motivo': 'Candidato malformado.'})
    for index in range(len(lista)):
        status, value = results[index]
        (accepted if status == 'ok' else refused).append(value)
    return accepted, refused


def caminho(run, revisao):
    return dentro(base_achados(run), f'{PASTA}/{revisao}.json')


def hash_previsto(data):
    """The ``registros_sha256`` ``registros_achados.publicar`` will give ``data`` (same round trip, same writer)."""
    canonical = json.loads(json.dumps(data, ensure_ascii=False))
    return hashlib.sha256((json.dumps(canonical, ensure_ascii=False, indent=2) + '\n').encode('utf-8')).hexdigest()


def gravar(run, data, lista, versao_mesa, *, pasta=PASTA, chave='candidatos', conferir_lista=None):
    """Writes the round's candidates BEFORE the revision is published (N2 of the Coruja), bound to the hash the
    publication will have. While the revision is not published, a file left by a failed attempt is replaced;
    once it is, the file is immutable (the same content is accepted). Readers ignore a file whose hash is not the
    published one."""
    accepted, refused = (conferir_lista or conferir)(lista, data)
    record = {'esquema': ESQUEMA, 'caso_id': data['caso_id'], 'rodada': data['rodada'], 'revisao': data['revisao'],
              'registros_sha256': hash_previsto(data), 'versao_mesa': versao_mesa, chave: accepted, 'recusados': refused}
    path = dentro(base_achados(run), f'{pasta}/{data["revisao"]}.json')
    published = dentro(base_achados(run), f'revisoes/{data["revisao"]}').exists()
    if path.exists() and published:
        if ler_json(path) != record:
            raise ValueError('Candidatos para os quadros já gravados com outro conteúdo; sobrescrita recusada.')
        return record
    path.parent.mkdir(parents=True, exist_ok=True)
    staged = path.with_name(f'.{path.stem}.{uuid.uuid4().hex}.tmp')
    try:
        escrever_json(staged, record, exclusivo=True)
        os.replace(staged, path)
    finally:
        if staged.exists():
            staged.unlink()
    return record


# --- decisions -----------------------------------------------------------------------------------------------------

CAMPOS_DECISAO = {'sugestao_id': None, 'acao': None, 'quadro': None, 'item_id': None, 'alterados': []}
ID_ITEM = re.compile(r'[HTPL][a-f0-9]{32}')


def _regras_decisao(state):
    if (not isinstance(state['sugestao_id'], str) or not re.fullmatch(ID, state['sugestao_id'])
            or state['acao'] not in ACOES or state['quadro'] not in QUADROS
            or (state['item_id'] is None) != (state['acao'] not in ('confirmar', 'corrigir'))
            or state['item_id'] is not None and not (isinstance(state['item_id'], str) and ID_ITEM.fullmatch(state['item_id']))
            or not isinstance(state['alterados'], list) or len(state['alterados']) > 20
            or not all(isinstance(a, str) and 0 < len(a) <= 40 for a in state['alterados'])
            or state['alterados'] and state['acao'] != 'corrigir'):
        raise ValueError('Decisão de sugestão inválida.')


def _normalizar_decisao(_root, _case, data, atual, _identificador):
    if atual is not None:
        raise ValueError('Decisão de sugestão inválida.')  # a decision is never edited: the next one is a new record
    state = ev.mesclar(data, None, CAMPOS_DECISAO)
    _regras_decisao(state)
    return state


DECISOES = ev.Colecao('sugestoes', 'K', CAMPOS_DECISAO, _normalizar_decisao, _regras_decisao, 'sugestões')


def _sugestao_do_registro(root, case, identifier):
    """The suggestion a diverging decision record is about, read from any of its event files (no trust beyond
    the id), or None when nothing in it can be read."""
    folder = dentro(DECISOES.pasta(root, case), identifier)
    for path in sorted(folder.glob('*.json')) if folder.is_dir() else []:
        try:
            sid = ler_json(dentro(folder, path.name)).get('estado', {}).get('sugestao_id')
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(sid, str) and re.fullmatch(ID, sid):
            return sid
    return None


def _decisoes(root, case):
    """``({sugestao_id: [decision, ...]}, {sugestao_id with a diverging decision})``, in the order they were made.

    A diverging record blocks only its own suggestion (R1 of the Coruja on ef88880); a record so damaged that no
    suggestion can be read from it still stops everything, because it could hide a confirmation."""
    grouped, broken = {}, set()
    for record in DECISOES.listar(root, case):
        if record['divergente']:
            sid = _sugestao_do_registro(root, case, record['id'])
            if sid is None:
                raise ValueError('Histórico do registro divergente nas decisões sobre sugestões (registro ilegível); '
                                 'nenhuma decisão foi aplicada.')
            broken.add(sid)
            continue
        first = record['historico'][0]
        grouped.setdefault(record['estado']['sugestao_id'], []).append(
            {**record['estado'], 'id': record['id'], 'por': first['autor'], 'conta_id': first.get('conta_id'),
             'em_utc': first['em_utc']})
    for items in grouped.values():
        items.sort(key=lambda d: (d['em_utc'], d['id']))
    return grouped, broken


@lixeira.leitura_da_exportacao
def itens_da_conta(root, conta, casos):
    """The decisions the account made on the AI's suggestions, for its own data export (E4b-2b of Contas; the
    Maestro, 27/11): ``[{tipo: 'sugestao_<acao>', caso, criado_em, id: '<quadro>/<sugestão>[/<item criado>]'}]``,
    only in ``casos`` (those it reaches, as the caller says) and only decisions of this account: never the
    suggestion's content nor anything of another person. Cases in the trash stay out. A decision record that cannot
    be read raises ValueError (whose decision it is would be unknown)."""
    casos, _ = lixeira.casos_da_exportacao(root, conta, casos)
    itens = []
    for case in casos:
        for record in DECISOES.listar(root, case):
            historico = record.get('historico')
            if record.get('divergente') or not historico:
                raise ValueError('Registro ilegível nas decisões sobre sugestões.')
            first, state = historico[0], record['estado']
            if first.get('conta_id') == conta and first.get('origem_autoria') == caderno.AUTORIA_CONTA:
                ref = '/'.join(x for x in (state['quadro'], state['sugestao_id'], state['item_id']) if x)
                itens.append(lixeira.item_exportado(f'sugestao_{state["acao"]}', case, first.get('em_utc'), ref))
    itens.sort(key=lambda item: (item['criado_em'], item['id']))
    return itens


# --- suggestions ---------------------------------------------------------------------------------------------------

def _normal(value):
    plain = unicodedata.normalize('NFD', value.casefold())
    return ' '.join(''.join(c for c in plain if not unicodedata.combining(c)).split())


def identidade(case, rodada, registros, chave):
    return 'S' + hashlib.sha256(f'{case}|{rodada}|{registros}|{chave}'.encode()).hexdigest()[:32]


def _pergunta(run):
    question = run / '00_pergunta_original.md'
    try:
        return question.read_text(encoding='utf-8').strip()[:300] if question.is_file() else ''
    except (OSError, UnicodeDecodeError):
        return ''


def _registros(root, case, cache):
    """Every round with accepted candidates: [(analise, data, accepted)], newest round first."""
    folder = dentro(root, f'execucoes/{case}')
    rounds = []
    for run in sorted(folder.iterdir()) if folder.is_dir() else []:
        if not run.is_dir() or not re.fullmatch(lixeira.ID_RODADA, run.name) or lixeira.excluido(root, case, rodada=run.name):
            continue
        pasta = dentro(base_achados(run), PASTA)
        for path in sorted(pasta.glob('*.json')) if pasta.is_dir() else []:
            try:
                record = ler_json(dentro(pasta, path.name))
                data, manifest = vinculo_ia._dados(root, case, run.name, path.stem, cache)
                if (record.get('esquema') != ESQUEMA or record.get('caso_id') != case or record.get('rodada') != run.name
                        or record.get('revisao') != path.stem
                        or record.get('registros_sha256') != manifest['registros_sha256']):
                    continue
                accepted, _ = conferir(estrutura(record['candidatos']), data)
            except (ValueError, OSError, KeyError, TypeError):
                continue  # candidates that do not check against their revision are not shown
            analise = {'caso': case, 'rodada': run.name, 'revisao': path.stem,
                       'registros_sha256': manifest['registros_sha256'], 'em_utc': manifest.get('criado_em_utc'),
                       'pergunta': _pergunta(run)}
            rounds.append((analise, data, accepted))
    rounds.sort(key=lambda r: (r[0]['em_utc'] or '', r[0]['rodada']), reverse=True)
    return rounds


def _evidencia(root, case, ref, achado_id, cache):
    # The values of the candidate's finding, never of another finding with the same E-ID (B1 of the Coruja).
    review = vinculo_ia.revisao_ia(root, case, ref, cache, achado_id)
    out = {'referencia': ref, 'revisao_ia': review, 'conferencia_humana': None}
    try:
        resolved = ev.resolver(root, case, ref, cache)
        out.update(estado='conferida', documento={'documento_id': resolved['documento']['documento_id'],
                                                  'nome': resolved['documento']['nome']},
                   localizador=resolved['localizador'], trecho=resolved['trecho'])
    except ValueError as exc:
        out.update(estado='indisponivel', erro=str(exc), documento=None, localizador=None, trecho=None)
    if review is not None:
        out['conferencia_humana'] = vinculo_ia._marca_humana(root, case, ref['rodada'], review['achado_id'],
                                                             review['versao'], cache)
    return out


def _assinatura(data, cand):
    evidences = {e['id']: e for e in data['evidencias']}
    return sorted(json.dumps([evidences[e]['documento_id'], evidences[e]['original_sha256'], evidences[e]['localizador'],
                              evidences[e]['trecho']], ensure_ascii=False, sort_keys=True) for e in cand['evidencias'])


def _chave_item(cand, by_key):
    fields = cand['campos']
    if cand['tipo'] in ('pessoa', 'organizacao'):
        return mapa.nome_normalizado(fields['nome'], cand['tipo'])
    if cand['tipo'] == 'ligacao':
        ends = [by_key[fields[k]] for k in ('de', 'para')]
        return [_normal(fields['tipo'])] + [mapa.nome_normalizado(e['campos']['nome'], e['tipo']) for e in ends]
    if cand['tipo'] == 'acontecimento':
        return [_normal(fields['descricao'])] + sorted([d['tipo'], d['valor']] for d in fields['datas'])
    return _normal(fields['enunciado'])


ESTADO_DA_ACAO = {'confirmar': 'confirmada', 'corrigir': 'confirmada', 'descartar': 'descartada', 'restaurar': 'aberta'}


def _todas(root, case, cache=None):
    """{id: suggestion} of the case (contract, section 2.1), with the decisions applied, newest round first."""
    cache = {} if cache is None else cache
    decisions, broken = _decisoes(root, case)
    built, order = {}, []
    for analise, data, accepted in _registros(root, case, cache):
        by_key = {c['chave']: c for c in accepted}
        ids = {c['chave']: identidade(case, analise['rodada'], analise['registros_sha256'], c['chave']) for c in accepted}
        # B1 of the Coruja on ef88880: what a later revision says (withdrawn, not supported) is what counts.
        latest = vinculo_ia.ultima_revisao(root, case, analise['rodada'], cache) or analise['revisao']
        newest, newest_manifest = vinculo_ia._dados(root, case, analise['rodada'], latest, cache)
        for cand in accepted:
            sid = ids[cand['chave']]
            claim = next(c for c in data['achados'] if c['id'] == cand['achado_id'])
            version = claim['versoes'][-1]
            current_claim = next((c for c in newest['achados'] if c['id'] == claim['id']), claim)
            key = (claim['id'], current_claim['versoes'][-1]['versao'])
            reviews = [r for r in newest['revisoes_assistidas'] if (r['achado_id'], r['versao']) == key]
            fates = [d for d in newest['destinos'] if (d['achado_id'], d['versao']) == key]
            refs = [{'tipo': 'ia', 'caso_id': case, 'rodada': analise['rodada'], 'revisao': latest,
                     'registros_sha256': newest_manifest['registros_sha256'], 'evidencia_id': e} for e in cand['evidencias']]
            evidencias = [_evidencia(root, case, ref, cand['achado_id'], cache) for ref in refs]
            links = []
            for ref, resolved in zip(refs, evidencias):
                fill = vinculo_ia.preenchimento(resolved['revisao_ia'])
                links.append({'referencia': ref, 'papel': fill['papel'], 'suporte': fill['suporte'],
                              'natureza': fill['natureza'],
                              'justificativa': vinculo_ia.justificativa_ia(root, case, ref, cache, cand['achado_id']),
                              'achado_id': cand['achado_id']})
            achado = {'id': claim['id'], 'versao': version['versao'], 'redacao': version['redacao'],
                      'natureza': version['natureza'], 'suporte_ia': reviews[-1]['suporte'] if reviews else 'nao_revisado',
                      'destino': fates[-1]['destino'] if fates else None,
                      'motivo_destino': fates[-1]['motivo'] if fates else None,
                      'versao_atual': current_claim['versoes'][-1]['versao']}
            own = decisions.get(sid, [])
            last = own[-1] if own else None
            built[sid] = {'id': sid, 'tipo': cand['tipo'], 'quadro': QUADRO_DO_TIPO[cand['tipo']],
                          'evidencias': evidencias, 'achado': achado, 'analise': analise,
                          'estado': ESTADO_DA_ACAO[last['acao']] if last else 'aberta',
                          'decisao': ({k: last[k] for k in ('acao', 'por', 'conta_id', 'em_utc', 'item_id', 'quadro',
                                                            'alterados')} if last else None),
                          'descartada_antes': None,
                          '_cand': cand, '_links': links, '_ids': ids, '_com_revisao': bool(newest['revisoes_assistidas']),
                          '_divergente': sid in broken,
                          '_assinatura': json.dumps([cand['tipo'], _chave_item(cand, by_key), _assinatura(data, cand)],
                                                    ensure_ascii=False)}
            order.append(sid)
    # "Already discarded": the same item with the same evidence, discarded (by a person) in another suggestion.
    discarded = {}
    for sid in order:
        item = built[sid]
        if item['estado'] == 'descartada' and item['decisao']:
            previous = discarded.get(item['_assinatura'])
            if previous is None or item['decisao']['em_utc'] < previous['decisao']['em_utc']:
                discarded[item['_assinatura']] = item
    for sid in order:
        item = built[sid]
        earlier = discarded.get(item['_assinatura'])
        if item['decisao'] is None and earlier is not None and earlier['id'] != sid:
            item['estado'] = 'descartada'
            item['descartada_antes'] = {'sugestao_id': earlier['id'], 'rodada': earlier['analise']['rodada'],
                                        'por': earlier['decisao']['por'], 'em_utc': earlier['decisao']['em_utc']}
    for sid in order:
        _completar(built, built[sid])
    return {sid: built[sid] for sid in order}


def _completar(built, item):
    """``campos``, ``pontas``, ``avisos`` and ``bloqueio`` (needs the other suggestions of the round)."""
    cand, links = item['_cand'], deepcopy(item['_links'])
    fields = cand['campos']
    item['pontas'] = None
    if cand['tipo'] in ('pessoa', 'organizacao'):
        campos = {'tipo': cand['tipo'], 'nome': fields['nome'], 'variantes': list(fields['variantes']),
                  'identificadores': [], 'evidencias': links}
    elif cand['tipo'] == 'ligacao':
        ends = {}
        for side, key in (('origem', 'de'), ('destino', 'para')):
            other = built[item['_ids'][fields[key]]]
            ends[side] = {'sugestao_id': other['id'], 'estado': other['estado'],
                          'item_id': other['decisao']['item_id'] if other['estado'] == 'confirmada' else None,
                          'nome': other['_cand']['campos']['nome']}
        item['pontas'] = ends
        campos = {'origem': ends['origem']['item_id'], 'destino': ends['destino']['item_id'], 'tipo': fields['tipo'],
                  'descricao': fields['descricao'], 'evidencias': links}
    elif cand['tipo'] == 'acontecimento':
        campos = {'descricao': fields['descricao'], 'datas': deepcopy(fields['datas']), 'evidencias': links,
                  'retirado': False, 'motivo_retirada': ''}
    else:
        campos = {'enunciado': fields['enunciado'], 'situacao': 'em_aberto', 'lacunas': [], 'evidencias': links}
    item['campos'] = campos
    achado = item['achado']
    substituida = achado['versao_atual'] > achado['versao'] or achado['destino'] == 'substituido'
    avisos = [name for name, on in (('analise_sem_revisao', not item['_com_revisao']),
                                    ('achado_retirado', achado['destino'] == 'retirado'),
                                    ('versao_substituida', substituida),
                                    ('evidencia_indisponivel', any(e['estado'] != 'conferida' for e in item['evidencias'])),
                                    ('decisao_divergente', item['_divergente']))
              if on]
    item['avisos'] = avisos
    block = None
    if item['estado'] == 'aberta':
        if 'evidencia_indisponivel' in avisos:
            block = 'evidencia_indisponivel'
        elif achado['destino'] == 'retirado':
            block = 'achado_retirado'
        elif substituida:
            block = 'versao_substituida'
        elif achado['suporte_ia'] in ('nao_sustentado', 'ilegivel'):
            block = achado['suporte_ia']
        elif item['pontas']:
            states = [item['pontas'][s]['estado'] for s in ('origem', 'destino')]
            block = 'ponta_descartada' if 'descartada' in states else 'ponta_ainda_sugestao' if 'aberta' in states else None
    item['bloqueio'] = 'historico_divergente' if item['_divergente'] else block


def publico(item):
    return {k: v for k, v in item.items() if not k.startswith('_')}


def listar(root, case, data):
    """``sugestoes-listar``: the suggestions of one board (contract, section 2.1)."""
    if not isinstance(data, dict) or set(data) - {'caso', 'quadro', 'incluir_decididas'}:
        raise ValueError('Campos inválidos no pedido do quadro.')
    quadro, todas = data.get('quadro'), data.get('incluir_decididas', False)
    if quadro not in QUADROS:
        raise ValueError('Quadro de sugestões inválido: use mapa, linha_tempo ou hipoteses.')
    if type(todas) is not bool:
        raise ValueError('Campos inválidos no pedido do quadro.')
    items = [i for i in _todas(root, case).values() if i['quadro'] == quadro]
    count = {'abertas': sum(i['estado'] == 'aberta' for i in items),
             'descartadas': sum(i['estado'] == 'descartada' for i in items)}
    shown = [publico(i) for i in items if todas or i['estado'] != 'confirmada']
    return {'caso': case, 'quadro': quadro, 'contagem': count, 'sugestoes': shown}


MENSAGENS = {
    'evidencia_indisponivel': 'A evidência da sugestão não está mais disponível. Descarte ou corrija com outra.',
    'achado_retirado': 'A revisão da IA retirou este achado. Corrija com outra evidência ou descarte.',
    'versao_substituida': 'Há uma versão mais nova deste achado. Corrija para ligar a nova versão.',
    'nao_sustentado': 'A revisão da IA não sustentou esta evidência. Corrija com outra evidência ou descarte.',
    'ilegivel': 'A revisão da IA não conseguiu ler esta evidência. Confira no original e corrija, ou descarte.'}


def _recusa_ponta(item, side):
    end = item['pontas'][side]
    if end['estado'] == 'descartada':
        return ValueError(f'A ponta {side} da ligação ({end["nome"]}) está em Descartadas. '
                          'Restaure-a ou troque a ponta em Corrigir.')
    return ValueError(f'A ponta {side} da ligação ({end["nome"]}) ainda é sugestão. Confirme-a antes.')


def _criar_item(root, item, campos, base, conta):
    payload = {**base, **campos}
    if item['quadro'] == 'hipoteses':
        return hipoteses.salvar(root, payload, 'criar', conta)
    if item['quadro'] == 'linha_tempo':
        return linha_tempo.salvar(root, payload, 'criar', conta)
    if item['tipo'] == 'ligacao':
        return mapa.salvar_relacao(root, payload, 'criar', conta)
    return mapa.salvar_entidade(root, payload, 'criar', conta)


def _detalhe_item(root, case, quadro, item_id):
    if quadro == 'hipoteses':
        return hipoteses.detalhe(root, case, item_id)
    if quadro == 'linha_tempo':
        return linha_tempo.detalhe(root, case, item_id)
    return (mapa.detalhe_relacao if item_id.startswith('L') else mapa.detalhe_entidade)(root, case, item_id)


def _referencias(links):
    if not isinstance(links, list):
        raise ValueError('Vínculo de evidência inválido.')
    return sorted(ev.chave(x['referencia']) if isinstance(x, dict) and 'referencia' in x else '' for x in links)


def decidir(root, data, acao, conta=None):
    """``sugestoes-<acao>`` (contract, section 2.2): ``{'sugestao', 'item'}``. ``data['caso']`` was checked by the route."""
    allowed = {'caso', 'id', 'requisicao_id', 'autor'} | ({'campos'} if acao == 'corrigir' else set())
    if acao not in ACOES or not isinstance(data, dict) or set(data) - allowed:
        raise ValueError('Campos inválidos no pedido do quadro.')
    case, sid, rid = data.get('caso'), data.get('id'), data.get('requisicao_id')
    if not isinstance(sid, str) or not re.fullmatch(ID, sid):
        raise ValueError('Sugestão não encontrada nesta apuração.')
    if not isinstance(rid, str) or not re.fullmatch(r'[a-f0-9]{32}', rid):
        raise ValueError('Identidade de salvamento inválida.')
    base = {'caso': case, **({'autor': data['autor']} if 'autor' in data else {})}
    with ev._trava(dentro(root, f'casos/{case}/quadros/.sugestoes'), 'sugestões'):
        item = _todas(root, case).get(sid)
        if item is None:
            raise ValueError('Sugestão não encontrada nesta apuração.')
        if item['_divergente']:
            raise ValueError('Histórico do registro divergente nas decisões desta sugestão; nenhuma decisão foi aplicada.')
        done = next((d for d in _decisoes(root, case)[0].get(sid, []) if d['id'] == 'K' + rid), None)
        if done is not None and done['acao'] != acao:
            raise ValueError('Esta tentativa já foi usada com outro conteúdo. Atualize o registro.')
        if done is None:
            expected = 'descartada' if acao == 'restaurar' else 'aberta'
            if item['estado'] != expected:
                raise ValueError('Esta sugestão já foi decidida: ' + {'confirmada': 'está confirmada.',
                                 'descartada': 'está em Descartadas.', 'aberta': 'está aberta.'}[item['estado']])
            alterados, created = [], None
            if acao == 'confirmar':
                if item['bloqueio'] in MENSAGENS:
                    raise ValueError(MENSAGENS[item['bloqueio']])
                if item['bloqueio']:
                    raise _recusa_ponta(item, next(s for s in ('origem', 'destino') if item['pontas'][s]['item_id'] is None))
                campos = item['campos']
            elif acao == 'corrigir':
                campos = data.get('campos')
                if not isinstance(campos, dict) or set(campos) & {'caso', 'id', 'requisicao_id', 'anterior_sha256',
                                                                  'autor', 'observacao'}:
                    raise ValueError('Campos inválidos no registro.')
                if item['tipo'] == 'ligacao':
                    for side in ('origem', 'destino'):
                        if campos.get(side) is None and item['pontas'][side]['item_id'] is None:
                            raise _recusa_ponta(item, side)
                alterados = sorted(k for k in campos if k != 'evidencias' and campos[k] != item['campos'].get(k))
                if _referencias(campos.get('evidencias', [])) != _referencias(item['campos']['evidencias']):
                    alterados.append('evidencias')
            if acao in ('confirmar', 'corrigir'):
                item_rid = hashlib.sha256(f'{sid}|{rid}'.encode()).hexdigest()[:32]
                created = _criar_item(root, item, campos, {**base, 'requisicao_id': item_rid}, conta)
            DECISOES.salvar(root, {**base, 'requisicao_id': rid, 'sugestao_id': sid, 'acao': acao, 'quadro': item['quadro'],
                                   'item_id': created['id'] if created else None, 'alterados': alterados}, 'criar', conta)
        updated = _todas(root, case)[sid]
        item_id = (updated['decisao'] or {}).get('item_id')
        return {'sugestao': publico(updated),
                'item': _detalhe_item(root, case, updated['quadro'], item_id) if item_id else None}
