"""Operações de administração da Mesa: ambiente, provedor de IA, gerenciamento e lixeira.

Separado de ``interface_pesquisa`` sem mudar comportamento. Só o administrador alcança estas
operações (convidados param em ``rotas_contas._negado``). A chave de API é só de escrita do
ponto de vista do navegador: ``ia-config`` devolve se há chave e os quatro últimos caracteres.
Exclusão, restauração e apagamento definitivo correm dentro da trava de cadastro.
"""
from __future__ import annotations

import acesso
import apagamento
import continuidade
from inferencia_api import resumo_inferencia, salvar_inferencia
import lixeira
from rotas_documentos import catalogo
import segredos

SO_A_CHAVE = ('O provedor e o modelo deste serviço são definidos por quem o administra. Aqui a redação grava ou remove '
              'somente a própria chave.')


def resumo_da_redacao(root, redacao):
    """`ia-config` as a newsroom of the hosted service sees it: provider and model of the service, and of the keys
    only its own (presence and last four characters); of the service's key, that it exists."""
    return {**resumo_inferencia(root), 'chaves': segredos.resumo(root, redacao)}


def salvar_chave_da_redacao(root, redacao, conta, dados):
    """`ia-config-salvar` in the hosted service (contract of accounts, 5.5 and 8.5): the dono saves or removes the
    newsroom's own key, and nothing else. Provider and model are the operator's: a body that would change them is
    refused whole, before anything is written. The key of the service is never touched from here."""
    if not isinstance(dados, dict) or set(dados) - {'provedor', 'modelo_preferido', 'chave', 'remover_chave'}:
        raise ValueError('Campos de configuração inválidos.')
    atual = resumo_inferencia(root)
    modelo = dados.get('modelo_preferido')
    modelo = (modelo.strip() if isinstance(modelo, str) else modelo) or None
    if dados.get('provedor') != atual['provedor'] or ('modelo_preferido' in dados and modelo != atual['modelo_preferido']):
        raise ValueError(SO_A_CHAVE)
    chave, remover = dados.get('chave'), dados.get('remover_chave', False)
    if type(remover) is not bool:
        raise ValueError('Indicação de remoção da chave inválida.')
    if chave not in (None, ''):
        segredos.salvar_chave(root, atual['provedor'], chave, redacao)
        acesso.registrar_chave_de_ia(root, conta, 'chave_ia_salva')
    elif remover:
        tinha = segredos.origem_da_chave(root, atual['provedor'], redacao) == 'redacao'
        segredos.remover_chave(root, atual['provedor'], redacao)
        if tinha:
            acesso.registrar_chave_de_ia(root, conta, 'chave_ia_removida')
    else:
        raise ValueError('Informe a chave da redação, ou peça a remoção dela.')
    return resumo_da_redacao(root, redacao)

# Provider choice and API key; the key is write-only from the browser's point of view.
IA_OPERACOES = ('ia-config', 'ia-config-salvar')
GERENCIAR = ('gerenciar-listar', 'excluir', 'restaurar')
LIXEIRA = ('lixeira-alcance', 'lixeira-apagar')
OPERACOES = ('ambiente', *IA_OPERACOES, *LIXEIRA, *GERENCIAR, 'continuidade-resumo')


class RotasGestao:
    """Mixin of the request handler: uses its ``server``."""

    def _senha_de_novo(self, data, principal):
        """Where accounts exist, saving the AI key and deleting for good ask the password of who does it again
        (contrato de contas, 5.15): a session left open, or hostile content shown in the Mesa, cannot run them.
        Without it 403 ``senha_necessaria``; a wrong one 403 ``senha_atual_incorreta`` and counts; five in a row 429."""
        acesso.confirmar_senha(self.server.root, principal.get('conta'), data.get('senha'), self._ip())

    def _gestao(self, operation, data, principal, concedido=None):
        if operation == 'ambiente':
            return self.server.ambiente
        # In the hosted service the Mesa shows and saves the key of the caller's own newsroom, never the service's.
        # In the local modes the installation has one key, as ever.
        # A caller of the hosted service without a newsroom gets neither: it fails closed, never on the service's key.
        piloto = self.server.modo == 'piloto'
        redacao = (principal.get('organizacao') or {}).get('id') if piloto else None
        if operation in IA_OPERACOES and piloto and not redacao:
            raise ValueError(SO_A_CHAVE)
        if operation == 'ia-config':
            return resumo_da_redacao(self.server.root, redacao) if piloto else resumo_inferencia(self.server.root)
        if operation == 'ia-config-salvar':
            if self.server.com_contas:  # the password goes in the same body and never reaches the settings
                self._senha_de_novo(data, principal)
                data = {campo: valor for campo, valor in data.items() if campo != 'senha'}
            if piloto:
                return salvar_chave_da_redacao(self.server.root, redacao, principal['conta'], data)
            return salvar_inferencia(self.server.root, data)
        if operation == 'lixeira-alcance':
            return lixeira.alcance(self.server.root, data.get('item'))
        if operation == 'lixeira-apagar':
            # The name first (a typing slip is not a wrong password), then the password, both outside the lock.
            esperado = apagamento.nome_para_confirmar(self.server.root, data.get('item'))
            nome = data.get('nome')
            if not isinstance(nome, str) or nome.strip().casefold() != str(esperado).strip().casefold():
                raise ValueError('Digite o nome do item exatamente como mostrado para confirmar.')
            if self.server.com_contas:
                self._senha_de_novo(data, principal)
            # Under the locks only the check and the quarantine (quick); the files go in the background.
            with self.server.cadastro_lock:
                esperado = apagamento.nome_para_confirmar(self.server.root, data.get('item'))
                if nome.strip().casefold() != str(esperado).strip().casefold():
                    raise ValueError('Digite o nome do item exatamente como mostrado para confirmar.')
                resultado = lixeira.apagar_definitivamente(
                    self.server.root, data.get('item'), data.get('confirmacao'),
                    quem=principal.get('nome') or principal.get('conta') or 'operador local',
                    gerenciador=self.server.conversas, segundo_plano=True)
                item = getattr(concedido, 'item', None)
                if item and item.get('tipo') == 'caso':
                    # The ownership record stays as a mark nobody reaches: the id is never used again.
                    acesso.marcar_caso_apagado(self.server.root, item.get('caso'))
                return resultado
        if operation in GERENCIAR:
            with self.server.cadastro_lock:
                manager = self.server.conversas
                if operation == 'gerenciar-listar':
                    with manager.lock:
                        visible = catalogo(self.server.root)
                        selected = data.get('caso')
                        return {**visible, 'lixeira': lixeira.ativos(self.server.root),
                                'conversas': manager.listar(selected)['conversas']
                                if selected in {c['id'] for c in visible['casos']} else []}
                return manager.gerenciar(operation, data)
        if operation == 'continuidade-resumo':
            # Admin only (not a guest operation): metadata of the active case, never draft text.
            conta = ({'id': principal['conta'], 'nome': principal['nome']}
                     if self.server.com_contas else None)
            with self.server.cadastro_lock:
                return continuidade.executar_resumo(self.server.root, data, conta,
                    lambda caso: self.server.conversas.listar(caso)['conversas'])
        raise ValueError('Operação de gestão desconhecida.')
