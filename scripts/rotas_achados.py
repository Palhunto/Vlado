"""Operações dos achados de uma rodada e da revisão humana (``POST /api/achados-*``).

Separado de ``interface_pesquisa.executar`` sem mudar comportamento. Identidades explícitas
(caso, rodada, revisão, geração); a anotação humana nunca altera os registros canônicos da
IA. O servidor já conferiu que caso e rodada não estão na lixeira e chama dentro da trava
de cadastro. ``achados-original`` devolve a evidência validada; o arquivo sai por
``rotas_downloads``.
"""
from __future__ import annotations

import re

import indice_achados
import revisao_humana

OPERACOES = ('achados-revisao-salvar',
             'achados-catalogo', 'achados-buscar', 'achados-detalhe',
             'achados-evidencia', 'achados-original', 'achados-exportar', 'achados-briefing')


def executar(root, operation, data, conta, case, run, originais_abertos):
    # Explicit identities; human annotations never alter canonical AI records.
    if operation == 'achados-catalogo':
        return indice_achados.catalogo(root, case, run)
    revision, gen = data.get('revisao'), data.get('geracao_achados')
    if operation == 'achados-revisao-salvar':
        return revisao_humana.salvar(root, case, run, revision,
            achado_id=data.get('achado_id'), achado_versao=data.get('achado_versao'),
            registros_sha256=data.get('registros_sha256'), estado=data.get('estado'),
            observacao=data.get('observacao', ''), anterior=data.get('anterior'), conta=conta,
            originais_abertos=originais_abertos)
    if operation == 'achados-briefing':
        digest = data.get('artefato_sha256')
        if not isinstance(digest, str) or not re.fullmatch(r'[a-f0-9]{64}', digest):
            raise ValueError('Identidade de briefing inválida.')
        return indice_achados.artefato(root, case, run, revision, digest)
    if operation in ('achados-evidencia', 'achados-original'):
        evidence_id = data.get('evidencia_id')
        if not isinstance(evidence_id, str) or not re.fullmatch(r'E[0-9]{3,}', evidence_id):
            raise ValueError('ID de evidência inválido.')
        return indice_achados.evidencia(root, case, run, revision, evidence_id)
    if operation == 'achados-detalhe':
        claim_id = data.get('achado_id')
        if not isinstance(claim_id, str) or not re.fullmatch(r'A[0-9]{3,}', claim_id):
            raise ValueError('ID de achado inválido.')
        return revisao_humana.detalhe(root, case, run, revision, gen, claim_id)
    if operation in ('achados-buscar', 'achados-exportar'):
        return revisao_humana.consultar(root, case, run, revision, gen,
                   filtros=data.get('filtros'), limite=data.get('limite', 10),
                   deslocamento=data.get('deslocamento', 0), completa=operation == 'achados-exportar')
    raise ValueError('Operação de achados desconhecida.')
