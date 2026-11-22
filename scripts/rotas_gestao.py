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

# Provider choice and API key; the key is write-only from the browser's point of view.
IA_OPERACOES = ('ia-config', 'ia-config-salvar')
GERENCIAR = ('gerenciar-listar', 'excluir', 'restaurar')
LIXEIRA = ('lixeira-alcance', 'lixeira-apagar')
OPERACOES = ('ambiente', *IA_OPERACOES, *LIXEIRA, *GERENCIAR, 'continuidade-resumo')


class RotasGestao:
    """Mixin of the request handler: uses its ``server``."""

    def _gestao(self, operation, data, principal, concedido=None):
        if operation == 'ambiente':
            return self.server.ambiente
        if operation == 'ia-config':
            return resumo_inferencia(self.server.root)
        if operation == 'ia-config-salvar':
            return salvar_inferencia(self.server.root, data)
        if operation == 'lixeira-alcance':
            return lixeira.alcance(self.server.root, data.get('item'))
        if operation == 'lixeira-apagar':
            # Under the locks only the check and the quarantine (quick); the files go in the background.
            with self.server.cadastro_lock:
                esperado = apagamento.nome_para_confirmar(self.server.root, data.get('item'))
                nome = data.get('nome')
                if not isinstance(nome, str) or nome.strip().casefold() != str(esperado).strip().casefold():
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
