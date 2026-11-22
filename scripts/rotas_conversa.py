"""Operações da conversa com os documentos (``POST /api/codex-*``).

Separado de ``interface_pesquisa``. Os nomes mantêm o prefixo histórico ``codex-``; a
inferência passa por ``codex_apuracao.Conversas`` e pelo adaptador da API. O servidor já
conferiu sessão, CSRF, origem e papel (``rotas_contas._negado``) e já descontou a cota do
convidado; aqui a cota é devolvida quando a pergunta é recusada, e o convidado nunca recebe o
dono nem os identificadores internos do provedor. ``codex-documentos-cadastrar`` envia o lote
pela fila de extração (``fila_extracao``), sem trava presa durante a leitura; ``Conversas.lock``
fica preso apenas na conferência da conversa. Nada daqui passa por ``cadastro_lock``.
"""
from __future__ import annotations

import threading

import acesso
import autorizacao
import custo
import diligencias
from rotas_documentos import receber_documentos

OPERACOES = ('codex-status', 'codex-listar',
             'codex-perguntar', 'codex-retomar', 'codex-eventos', 'codex-cancelar', 'codex-original',
             'codex-desligar', 'codex-observacoes', 'codex-corpus-previa', 'codex-documentos-cadastrar', 'codex-caderno-previa', 'codex-diligencias-previa')
CAMPOS_INTERNOS_CONVERSA = frozenset({'dono', 'conta', 'thread_id', 'turn_id', 'politica'})
# Returned by ``_conversa`` when the response (a file or the shutdown notice) was already sent.
RESPONDIDO = object()


def _sem_internos(result):
    """Guests see their conversation, not the owner id or provider thread/turn identifiers."""
    if not isinstance(result, dict) or not isinstance(result.get('conversa'), dict):
        return result
    conversa = {k: v for k, v in result['conversa'].items() if k not in CAMPOS_INTERNOS_CONVERSA}
    return {**result, 'conversa': conversa}


class RotasConversa:
    """Mixin of the request handler: uses its ``_send``, ``_json`` and ``server``."""

    def _cota(self):
        """`GET /api/cota`: this month's spend and balance in reais (the quota bar). Each account sees its
        own; the dono also sees the newsroom's. No case content."""
        principal = self._principal()
        if principal is None:
            self._proibido()
            return
        try:
            autorizacao.conferir(self.server.root, self.server.modo, principal, 'GET:/api/cota', {})
            self._json(200, custo.situacao(self.server.root, principal['conta'],
                                           administrador=autorizacao.ve_redacao(principal)))
        except autorizacao.Recusa as recusa:
            self._recusado(recusa, principal)
        except ValueError as exc:
            self._json(400, {'erro': str(exc)}, exc)

    def _conversa(self, operation, data, dono, casos_liberados, consulta_contada, conta=None):
        """Result to answer as JSON, or ``RESPONDIDO``. ``dono`` is the guest account (None for admins);
        ``conta`` the account that asks, administrators included (it spends the month's quota)."""
        manager = self.server.conversas
        if operation == 'codex-desligar':
            self._json(200, {'estado': 'encerrando'})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return RESPONDIDO
        if operation == 'codex-original':
            path = manager.fonte(data.get('conversa'), data.get('referencia'), dono=dono, casos=casos_liberados)
            self._send(200, path.read_bytes(), 'application/octet-stream',
                       {'Content-Disposition': f'attachment; filename="original{path.suffix}"'})
            return RESPONDIDO
        if operation == 'codex-status':
            result = manager.status()
        elif operation == 'codex-listar':
            result = manager.listar(data.get('caso'), dono=dono)
        elif operation == 'codex-perguntar':
            try:
                result = manager.perguntar(data, dono=dono, conta=conta)
            except Exception:
                if consulta_contada:
                    acesso.devolver_consulta(self.server.root, dono)
                raise
        elif operation == 'codex-retomar':
            try:
                result = manager.retomar(data.get('conversa'), dono=dono, casos=casos_liberados, conta=conta)
            except FileNotFoundError as exc:
                if consulta_contada:
                    acesso.devolver_consulta(self.server.root, dono)
                raise ValueError('Conversa indisponível para este acesso.') from exc
            except Exception:
                if consulta_contada:
                    acesso.devolver_consulta(self.server.root, dono)
                raise
        elif operation == 'codex-observacoes':
            result = manager.observacoes(data)
        elif operation == 'codex-corpus-previa':
            result = manager.preparar_corpus(data)
        elif operation == 'codex-caderno-previa':
            result = manager.caderno_previa(data)
        elif operation == 'codex-diligencias-previa':
            result = manager.caderno_previa(data, diligencias)
        elif operation == 'codex-documentos-cadastrar':
            # Conversas.lock only for the check (reservar_para_documentos); the batch goes through the
            # extraction queue, with no lock held while it is read; new questions on this one wait.
            with manager.reservar_para_documentos(data.get('caso'), data.get('conversa')):
                result = receber_documentos(self.server.root, {'caso': data.get('caso'),
                    'arquivos': data.get('arquivos'), 'natureza': data.get('natureza')},
                    fila=self.server.fila, fluxo=self.__dict__.get('_fluxo'))
        elif operation == 'codex-eventos':
            result = manager.eventos(data.get('conversa'), data.get('cursor', 0), data.get('espera', 0), dono=dono,
                                     casos=casos_liberados)
        elif operation == 'codex-cancelar':
            result = manager.cancelar(data.get('conversa'), dono=dono, casos=casos_liberados)
        if dono is not None:
            result = _sem_internos(result)
        return result
