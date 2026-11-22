"""Quem participa de uma apuração (``POST /api/caso-*``): listar, incluir, retirar e trocar o responsável.

Contrato de contas, seções 2.5 e 5.6. O portão (``autorizacao.conferir``) já conferiu, antes de chegar aqui, que a
apuração está ao alcance de quem pede e que o papel alcança a operação: o dono em toda apuração da redação; o
repórter, para incluir e retirar, só nas que é responsável. Aqui ficam a lista fechada dos campos e o despacho para
``acesso``, que guarda as regras: só entram contas da mesma redação (a de outra redação responde como inexistente),
o responsável é dono ou repórter, e o responsável não é retirado sem que outro seja indicado. As respostas levam nomes
de colegas da própria redação e nada da apuração. Sem modelo e sem rede; nenhum caminho vem do cliente.
"""
from __future__ import annotations

import acesso

OPERACOES = ('caso-participantes', 'caso-incluir', 'caso-retirar', 'caso-responsavel')
_CAMPOS = {'caso-participantes': {'caso'}, 'caso-incluir': {'caso', 'conta'}, 'caso-retirar': {'caso', 'conta'},
           'caso-responsavel': {'caso', 'conta'}}
_ACOES = {'caso-incluir': acesso.incluir_participante, 'caso-retirar': acesso.retirar_participante,
          'caso-responsavel': acesso.definir_responsavel}


def executar(root, operation, data, principal):
    """``principal`` é a conta da sessão: dele vêm a redação e quem faz, nunca do corpo do pedido."""
    if operation not in OPERACOES or not isinstance(data, dict):
        raise ValueError('Operação de equipe desconhecida.')
    if set(data) - _CAMPOS[operation]:
        raise ValueError('Campos inválidos no pedido de equipe.')
    redacao = (principal.get('organizacao') or {}).get('id')
    if not redacao or not principal.get('conta'):
        raise ValueError('Contas só existem nos modos com login.')
    if operation == 'caso-participantes':
        return acesso.participantes(root, data.get('caso'), redacao)
    return _ACOES[operation](root, data.get('caso'), data.get('conta'), principal['conta'], redacao)
