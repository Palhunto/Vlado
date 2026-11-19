"""Operações da Mesa para a conferência da redação e as entrevistas (``POST /api/redacao-*``, ``/api/entrevistas-*``).

Segue o padrão de ``rotas_evidencia`` e ``rotas_tabelas``: o servidor confere sessão, CSRF,
origem e papel (somente administradores; convidados não alcançam estas operações) e aqui
ficam a lista branca dos campos de cada pedido, a validação do caso e o despacho para os
módulos, que guardam as regras. A revisão humana recebe a conta autenticada do servidor;
sem conta (modo local) ela é recusada pelo módulo. Nada aqui chama modelo ou rede, e nenhum
caminho vem do cliente.
"""
from rotas_evidencia import _caso
import conferencia_redacao as redacao
import entrevistas

LEITURA = ('redacao-listar', 'redacao-conferir', 'redacao-dividir',
           'entrevistas-lacunas', 'entrevistas-listar', 'entrevistas-detalhe', 'entrevistas-exportar')
# Pedidos que gravam um evento; o texto chega inteiro, então o servidor aceita corpo de até 128 KB.
SALVAR = ('redacao-criar', 'redacao-nova-versao', 'redacao-vincular', 'redacao-revisar',
          'entrevistas-preparar', 'entrevistas-editar', 'entrevistas-responder')
OPERACOES = LEITURA + SALVAR
# Pedidos que levam o texto inteiro da reportagem (até redacao.LIMITE_TEXTO caracteres). Em UTF-8 um caractere
# ocupa até 4 bytes e o JSON pode dobrar aspas e barras, então o corpo aceita até 512 KB (limite de transporte;
# o limite de conteúdo continua em caracteres, no módulo).
TEXTO = ('redacao-criar', 'redacao-nova-versao', 'redacao-dividir')
LIMITE_CORPO_TEXTO = 512 * 1024
_REDACAO = {'redacao-criar': redacao.criar, 'redacao-nova-versao': redacao.nova_versao,
            'redacao-vincular': redacao.vincular, 'redacao-revisar': redacao.revisar}
_ENTREVISTAS = {'entrevistas-preparar': entrevistas.preparar, 'entrevistas-editar': entrevistas.editar,
                'entrevistas-responder': entrevistas.responder}
_CAMPOS = {'redacao-listar': {'caso'}, 'redacao-conferir': {'caso', 'id'}, 'redacao-dividir': {'caso', 'texto'},
           'entrevistas-lacunas': {'caso'}, 'entrevistas-listar': {'caso'}, 'entrevistas-detalhe': {'caso', 'id'},
           'entrevistas-exportar': {'caso', 'ids', 'formato'}}


def executar(root, operation, data, conta=None, casos=None):
    """Despacha uma operação. ``casos`` é None para administradores (todas as apurações)."""
    if operation not in OPERACOES or not isinstance(data, dict):
        raise ValueError('Operação da conferência da redação desconhecida.')
    case = _caso(root, data.get('caso'), casos)
    if operation in _REDACAO:
        record = _REDACAO[operation](root, data, conta)
        return redacao.conferencia(root, case, record['id'])
    if operation in _ENTREVISTAS:
        record = _ENTREVISTAS[operation](root, data, conta)
        return entrevistas.detalhe(root, case, record['id'])
    if set(data) - _CAMPOS[operation]:
        raise ValueError('Campos inválidos no pedido do quadro.')
    if operation == 'redacao-listar':
        return redacao.quadro(root, case)
    if operation == 'redacao-conferir':
        return redacao.conferencia(root, case, data.get('id'))
    if operation == 'entrevistas-lacunas':
        return entrevistas.lacunas(root, case)
    if operation == 'entrevistas-listar':
        return entrevistas.listar(root, case)
    if operation == 'entrevistas-detalhe':
        return entrevistas.detalhe(root, case, data.get('id'))
    if operation == 'entrevistas-exportar':
        return entrevistas.exportar(root, case, data.get('ids'), data.get('formato', 'pauta'))
    text = data.get('texto')
    if not isinstance(text, str) or len(text) > redacao.LIMITE_TEXTO:
        raise ValueError('Texto da reportagem: informe texto válido.')
    return {'caso': case, 'afirmacoes': redacao.dividir(text.replace('\r\n', '\n'))}
