"""Operações da conversa com os documentos (``POST /api/codex-*``).

Separado de ``interface_pesquisa``. Os nomes mantêm o prefixo histórico ``codex-``; a
inferência passa por ``codex_apuracao.Conversas`` e pelo adaptador da API. O servidor já
conferiu sessão, CSRF, origem e papel (``rotas_contas._negado``) e já descontou a cota do
convidado; aqui a cota é devolvida quando a pergunta é recusada, e o convidado nunca recebe o
dono nem os identificadores internos do provedor. Só ``codex-documentos-cadastrar`` passa pela
trava de cadastro da Mesa; ``Conversas.lock`` fica preso apenas na conferência da conversa.
"""
from __future__ import annotations

import threading

import acesso
import diligencias
from rotas_documentos import receber_documentos

OPERACOES = ('codex-status', 'codex-listar',
             'codex-perguntar', 'codex-retomar', 'codex-eventos', 'codex-cancelar', 'codex-original',
             'codex-desligar', 'codex-observacoes', 'codex-corpus-previa', 'codex-documentos-cadastrar', 'codex-caderno-previa', 'codex-diligencias-previa')
CAMPOS_INTERNOS_CONVERSA = frozenset({'dono', 'thread_id', 'turn_id', 'politica'})
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

    def _conversa(self, operation, data, dono, casos_liberados, consulta_contada):
        """Result to answer as JSON, or ``RESPONDIDO``. ``dono`` is the guest account (None for admins)."""
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
                result = manager.perguntar(data, dono=dono)
            except Exception:
                if consulta_contada:
                    acesso.devolver_consulta(self.server.root, dono)
                raise
        elif operation == 'codex-retomar':
            try:
                result = manager.retomar(data.get('conversa'), dono=dono, casos=casos_liberados)
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
            # Conversas.lock only for the check (reservar_para_documentos): the cadastro may take
            # minutes and must not freeze the other conversations; new questions on this one wait.
            with self.server.cadastro_lock, manager.reservar_para_documentos(data.get('caso'), data.get('conversa')):
                result = receber_documentos(self.server.root, {'caso': data.get('caso'),
                    'arquivos': data.get('arquivos'), 'natureza': data.get('natureza', 'nao_informada')})
        elif operation == 'codex-eventos':
            result = manager.eventos(data.get('conversa'), data.get('cursor', 0), data.get('espera', 0), dono=dono,
                                     casos=casos_liberados)
        elif operation == 'codex-cancelar':
            result = manager.cancelar(data.get('conversa'), dono=dono, casos=casos_liberados)
        if dono is not None:
            result = _sem_internos(result)
        return result
