"""Operações da Mesa para a conferência da redação (``POST /api/redacao-*``).

Segue o padrão de ``rotas_evidencia`` e ``rotas_tabelas``: o servidor confere sessão, CSRF,
origem e papel (somente administradores; convidados não alcançam estas operações) e aqui
ficam a lista branca dos campos de cada pedido, a validação do caso e o despacho para os
módulos, que guardam as regras. A revisão humana recebe a conta autenticada do servidor;
sem conta (modo local) ela é recusada pelo módulo. Nada aqui chama modelo ou rede, e nenhum
caminho vem do cliente.
"""
from rotas_evidencia import _caso
import conferencia_redacao as redacao

LEITURA = ('redacao-listar', 'redacao-conferir', 'redacao-dividir')
# Pedidos que gravam um evento; o texto chega inteiro, então o servidor aceita corpo de até 128 KB.
SALVAR = ('redacao-criar', 'redacao-nova-versao', 'redacao-vincular', 'redacao-revisar')
OPERACOES = LEITURA + SALVAR
_REDACAO = {'redacao-criar': redacao.criar, 'redacao-nova-versao': redacao.nova_versao,
            'redacao-vincular': redacao.vincular, 'redacao-revisar': redacao.revisar}
_CAMPOS = {'redacao-listar': {'caso'}, 'redacao-conferir': {'caso', 'id'}, 'redacao-dividir': {'caso', 'texto'}}


def executar(root, operation, data, conta=None, casos=None):
    """Despacha uma operação. ``casos`` é None para administradores (todas as apurações)."""
    if operation not in OPERACOES or not isinstance(data, dict):
        raise ValueError('Operação da conferência da redação desconhecida.')
    case = _caso(root, data.get('caso'), casos)
    if operation in _REDACAO:
        record = _REDACAO[operation](root, data, conta)
        return redacao.conferencia(root, case, record['id'])
    if set(data) - _CAMPOS[operation]:
        raise ValueError('Campos inválidos no pedido do quadro.')
    if operation == 'redacao-listar':
        return redacao.quadro(root, case)
    if operation == 'redacao-conferir':
        return redacao.conferencia(root, case, data.get('id'))
    text = data.get('texto')
    if not isinstance(text, str) or len(text) > redacao.LIMITE_TEXTO:
        raise ValueError('Texto da reportagem: informe texto válido.')
    return {'caso': case, 'afirmacoes': redacao.dividir(text.replace('\r\n', '\n'))}
