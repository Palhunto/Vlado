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
import re
import unicodedata

from comum import dentro, escrever_json, ler_json, sha256
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
    return {'chave': item['chave'], 'tipo': kind, 'achado_id': claim['id'], 'evidencias': list(eids), 'campos': campos}


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


def gravar(run, data, manifest, lista, versao_mesa):
    """Writes the round's candidates after the synthesis is published (exclusive; the same content is accepted)."""
    accepted, refused = conferir(lista, data)
    record = {'esquema': ESQUEMA, 'caso_id': data['caso_id'], 'rodada': data['rodada'], 'revisao': data['revisao'],
              'registros_sha256': manifest['registros_sha256'], 'versao_mesa': versao_mesa,
              'candidatos': accepted, 'recusados': refused}
    path = caminho(run, data['revisao'])
    if path.exists():
        if ler_json(path) != record:
            raise ValueError('Candidatos para os quadros já gravados com outro conteúdo; sobrescrita recusada.')
        return record
    path.parent.mkdir(parents=True, exist_ok=True)
    escrever_json(path, record, exclusivo=True)
    return record
