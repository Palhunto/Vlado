"""Operações da Mesa para os quadros de evidência (hipóteses, linha do tempo, comparador e mapa).

Cada operação chega como ``POST /api/<operacao>`` depois de o servidor conferir sessão,
CSRF, origem e papel (somente administradores; convidados não alcançam estas operações).
Aqui ficam só a lista branca dos campos de cada pedido, a validação do caso e o despacho
para os módulos dos quadros, que guardam as regras de evidência. Nada aqui chama modelo
ou rede, e nenhum caminho vem do cliente: o caso, a rodada e os IDs são resolvidos pelos
módulos dentro de ``casos/<caso>`` e ``execucoes/<caso>/<rodada>``.
"""
import re

import caderno
import comparador
from indice_sqlite import ID_DOCUMENTO
import evidencias as ev
import hipoteses
import linha_tempo
import lixeira
import mapa_relacoes

LEITURA = ('hipoteses-listar', 'hipoteses-detalhe', 'hipoteses-quadro',
           'linha-tempo-listar', 'linha-tempo-detalhe',
           'comparar-evidencias', 'comparar-documentos',
           'mapa-ver', 'mapa-homonimos')
# Pedidos que gravam um evento com vínculos de evidência: o servidor aceita corpo de até 128 KB.
SALVAR = ('hipoteses-criar', 'hipoteses-atualizar', 'linha-tempo-criar', 'linha-tempo-atualizar',
          'mapa-entidade-criar', 'mapa-entidade-atualizar', 'mapa-relacao-criar', 'mapa-relacao-atualizar')
OPERACOES = LEITURA + SALVAR

_SALVADORES = {'hipoteses': hipoteses.salvar, 'linha-tempo': linha_tempo.salvar,
               'mapa-entidade': mapa_relacoes.salvar_entidade, 'mapa-relacao': mapa_relacoes.salvar_relacao}
# Campos aceitos em cada leitura; qualquer outro recusa o pedido antes de abrir o caso.
_CAMPOS = {'hipoteses-listar': {'caso'}, 'hipoteses-detalhe': {'caso', 'id'}, 'hipoteses-quadro': {'caso'},
           'linha-tempo-listar': {'caso', 'tipos', 'incluir_retirados'}, 'linha-tempo-detalhe': {'caso', 'id'},
           'comparar-evidencias': {'caso', 'a', 'b'},
           'comparar-documentos': {'caso', 'rodada', 'documento_a', 'documento_b', 'contexto'},
           'mapa-ver': {'caso', 'incluir_retirados'}, 'mapa-homonimos': {'caso'}}


def _caso(root, case, casos):
    """Caso explícito, existente e fora da lixeira; ``casos`` restringe as apurações da conta."""
    if not isinstance(case, str) or not re.fullmatch(lixeira.ID_CASO, case):
        raise ValueError('Selecione uma apuração para os quadros de evidência.')
    if casos is not None and case not in casos:
        raise ValueError('Apuração não liberada para esta conta.')
    caderno._pasta(root, case)
    return case


def _sim_nao(data, field):
    value = data.get(field, False)
    if type(value) is not bool:
        raise ValueError('Indique com verdadeiro ou falso se inclui registros retirados.')
    return value


def _com_evidencias(root, case, item):
    """Detalhe do registro com cada vínculo conferido contra a fonte (ou marcado indisponível)."""
    return {**item, 'evidencias': ev.conferir_vinculos(root, case, item['estado'].get('evidencias', []))}


def executar(root, operation, data, conta=None, casos=None):
    """Despacha uma operação dos quadros. ``casos`` é None para administradores (todas as apurações)."""
    if operation not in OPERACOES or not isinstance(data, dict):
        raise ValueError('Operação dos quadros de evidência desconhecida.')
    case = _caso(root, data.get('caso'), casos)
    if operation in SALVAR:
        prefix, action = operation.rsplit('-', 1)
        return _SALVADORES[prefix](root, data, action, conta)
    if set(data) - _CAMPOS[operation]:
        raise ValueError('Campos inválidos no pedido do quadro.')
    if operation == 'hipoteses-listar':
        return {'caso': case, 'hipoteses': hipoteses.listar(root, case)}
    if operation == 'hipoteses-detalhe':
        return _com_evidencias(root, case, hipoteses.detalhe(root, case, data.get('id')))
    if operation == 'hipoteses-quadro':
        return hipoteses.quadro(root, case)
    if operation == 'linha-tempo-listar':
        return linha_tempo.linha(root, case, tipos=data.get('tipos'),
                                 incluir_retirados=_sim_nao(data, 'incluir_retirados'))
    if operation == 'linha-tempo-detalhe':
        return _com_evidencias(root, case, linha_tempo.detalhe(root, case, data.get('id')))
    if operation == 'comparar-evidencias':
        return comparador.comparar_evidencias(root, case, data.get('a'), data.get('b'))
    if operation == 'comparar-documentos':
        run = data.get('rodada')
        if not isinstance(run, str) or not re.fullmatch(lixeira.ID_RODADA, run):
            raise ValueError('Selecione uma rodada da apuração para comparar documentos.')
        docs = data.get('documento_a'), data.get('documento_b')
        if not all(isinstance(d, str) and re.fullmatch(ID_DOCUMENTO, d) for d in docs):
            raise ValueError('Escolha dois documentos da rodada para comparar.')
        return comparador.comparar_documentos(root, case, run, *docs, contexto=data.get('contexto', 2))
    if operation == 'mapa-ver':
        return mapa_relacoes.mapa(root, case, incluir_retirados=_sim_nao(data, 'incluir_retirados'))
    return {'caso': case, 'homonimos': mapa_relacoes.homonimos(root, case)}
