"""Operações do caderno de apuração, das notas, das diligências e do caderno humano.

Separado de ``interface_pesquisa.executar`` sem mudar comportamento. As regras de cada
registro ficam nos módulos ``apuracao``, ``diligencias`` e ``caderno``; aqui só o despacho
por prefixo. O servidor chama dentro da trava de cadastro; nada aqui chama modelo ou rede.
Os downloads destes registros (exportação e originais) ficam em ``rotas_downloads``.
"""
from __future__ import annotations

import apuracao
import caderno
import diligencias

CADERNO_OPERACOES = ('caderno-documentos', 'caderno-listar', 'caderno-detalhe', 'caderno-salvar',
                     'caderno-cruzar', 'caderno-exportar', 'caderno-original')
DILIGENCIAS_OPERACOES = ('diligencias-listar', 'diligencias-criar', 'diligencias-atualizar',
                        'diligencias-responder', 'diligencias-original')
PREFIXOS = ('apuracao-', 'diligencias-', 'caderno-')


def executar(root, operation, data, conta):
    if operation.startswith('apuracao-'):
        if operation == 'apuracao-listar':
            return apuracao.listar(root, data.get('caso'))
        if operation in apuracao.OPERACOES_NOTAS:
            return apuracao.executar(root, operation, data, conta)
        return apuracao.alterar(root, operation, data, conta)
    if operation.startswith('diligencias-'):
        if operation == 'diligencias-listar':
            return diligencias.listar(root, data.get('caso'), estado=data.get('estado', ''),
                responsavel=data.get('responsavel', ''), texto=data.get('texto', ''))
        if operation in ('diligencias-criar', 'diligencias-atualizar', 'diligencias-responder'):
            return diligencias.salvar(root, data, operation.split('-')[1], conta)
        raise ValueError('Operação de diligência desconhecida.')
    if operation.startswith('caderno-'):
        case = data.get('caso')
        if operation == 'caderno-documentos':
            return caderno.documentos(root, case, data.get('rodada'))
        if operation == 'caderno-listar':
            return caderno.listar(root, case, texto=data.get('texto', ''), limite=data.get('limite', 20), deslocamento=data.get('deslocamento', 0))
        if operation == 'caderno-detalhe':
            return caderno.detalhe(root, case, data.get('registro_id'), data.get('sha256'))
        if operation == 'caderno-salvar':
            return caderno.salvar(root, data, conta)
        if operation == 'caderno-cruzar':
            return caderno.cruzar(root, data, conta)
        if operation == 'caderno-exportar':
            return caderno.selecionar(root, case, data.get('selecoes'))
        raise ValueError('Operação do caderno desconhecida.')
    raise ValueError('Operação desconhecida.')
