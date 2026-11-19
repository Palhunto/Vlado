"""Operações da Mesa para as tabelas de apuração (``POST /api/tabelas-*``).

Segue o padrão de ``rotas_evidencia``: o servidor confere sessão, CSRF, origem e papel
(somente administradores; convidados não alcançam estas operações) e aqui ficam a lista
branca dos campos de cada leitura, a validação do caso (a mesma dos quadros do Core) e o
despacho para ``tabelas_apuracao``, que guarda as regras das células e dos cálculos. Nada
aqui chama modelo ou rede, e nenhum caminho vem do cliente: o caso e os IDs são
resolvidos pelo módulo dentro de ``casos/<caso>``.
"""
from rotas_evidencia import _caso, _sim_nao
import tabelas_apuracao as tabelas

LEITURA = ('tabelas-listar', 'tabelas-detalhe', 'tabelas-historico-celula', 'tabelas-calcular')
# Pedidos que gravam um evento. Uma tabela chega inteira na criação, então o servidor aceita corpo de até 2 MB.
SALVAR = ('tabelas-criar', 'tabelas-atualizar', 'tabelas-corrigir')
# Devolve o CSV como anexo (o servidor responde com o arquivo, como na exportação do caderno).
EXPORTAR = 'tabelas-exportar'
OPERACOES = LEITURA + SALVAR + (EXPORTAR,)
# Campos aceitos em cada leitura; qualquer outro recusa o pedido antes de abrir a tabela.
_CAMPOS = {'tabelas-listar': {'caso', 'incluir_retirados'}, 'tabelas-detalhe': {'caso', 'id'},
           'tabelas-historico-celula': {'caso', 'id', 'linha', 'coluna'},
           'tabelas-calcular': {'caso', 'id', 'calculo', 'sequencia'}, EXPORTAR: {'caso', 'id', 'formato'}}


def _campos(operation, data):
    if set(data) - _CAMPOS[operation]:
        raise ValueError('Campos inválidos no pedido do quadro.')


def exportar(root, data, casos=None):
    """``(nome do arquivo, bytes do CSV)`` de uma tabela do caso, com as conferências das demais leituras."""
    if not isinstance(data, dict):
        raise ValueError('Operação das tabelas de apuração desconhecida.')
    case = _caso(root, data.get('caso'), casos)
    _campos(EXPORTAR, data)
    return tabelas.exportar_csv(root, case, data.get('id'), data.get('formato', 'padrao'))


def executar(root, operation, data, conta=None, casos=None):
    """Despacha uma operação das tabelas. ``casos`` é None para administradores (todas as apurações)."""
    if operation not in OPERACOES or not isinstance(data, dict):
        raise ValueError('Operação das tabelas de apuração desconhecida.')
    case = _caso(root, data.get('caso'), casos)
    # Salvamentos devolvem o registro sem os estados completos de cada evento (tabelas podem ser grandes).
    if operation == 'tabelas-corrigir':
        return tabelas.compacto(tabelas.corrigir(root, data, conta))
    if operation in SALVAR:
        return tabelas.compacto(tabelas.salvar(root, data, operation.rsplit('-', 1)[1], conta))
    _campos(operation, data)
    if operation == 'tabelas-listar':
        return tabelas.quadro(root, case, incluir_retirados=_sim_nao(data, 'incluir_retirados'))
    if operation == 'tabelas-detalhe':
        return tabelas.tabela(root, case, data.get('id'))
    if operation == 'tabelas-historico-celula':
        return tabelas.historico_celula(root, case, data.get('id'), data.get('linha'), data.get('coluna'))
    if operation == 'tabelas-calcular':
        return tabelas.calcular_tabela(root, case, data.get('id'), data.get('calculo'), data.get('sequencia'))
    name, content = exportar(root, data, casos)
    return {'caso': case, 'id': data.get('id'), 'arquivo': name, 'csv': content.decode('utf-8-sig')}
