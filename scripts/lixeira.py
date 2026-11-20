"""Reversible UI exclusions. Source files, snapshots and outputs stay in place."""
from __future__ import annotations

from datetime import datetime, timezone
import re
import uuid

from comum import dentro, ler_json

ID_CASO = r'[a-z0-9][a-z0-9_-]{0,63}'
ID_CONVERSA = r'[a-f0-9]{32}'
ID_RODADA = r'R[0-9]{3,6}'


def registros(root):
    path = dentro(root, 'lixeira/registro.json')
    return ler_json(path)['itens'] if path.exists() else []


def ativos(root):
    return [item for item in registros(root) if not item.get('restaurado_em_utc')]


def excluido(root, caso, *, conversa=None, rodada=None, itens=None):
    for item in ativos(root) if itens is None else itens:
        if item['caso'] != caso:
            continue
        if item['tipo'] == 'caso':
            return True
        if conversa and item.get('conversa') == conversa:
            return True
        if rodada and (item.get('rodada') == rodada or rodada in item.get('rodadas', [])):
            return True
    return False


def conferir_disponivel(root, caso, **scope):
    if excluido(root, caso, **scope):
        raise ValueError('Este item está na lixeira. Restaure-o em Gerenciar para continuar.')


def validar(tipo, caso, conversa=None, rodada=None):
    if not isinstance(caso, str) or not re.fullmatch(ID_CASO, caso):
        raise ValueError('Identificador de apuração inválido.')
    if tipo not in ('caso', 'conversa', 'rodada'):
        raise ValueError('Tipo de item inválido.')
    value, pattern = (conversa, ID_CONVERSA) if tipo == 'conversa' else (rodada, ID_RODADA)
    if tipo != 'caso' and (not isinstance(value, str) or not re.fullmatch(pattern, value)):
        raise ValueError('Identificador de item inválido.')


def salvar(root, itens):
    # Callers hold the registration lock and the conversation manager lock.
    from cadastrar_documentos import _atomico, _bytes
    path = dentro(root, 'lixeira/registro.json')
    path.parent.mkdir(exist_ok=True)
    _atomico(path, _bytes({'versao': 1, 'itens': itens}))


def adicionar(root, tipo, caso, titulo, *, conversa=None, rodada=None, rodadas=None):
    itens = registros(root)
    item = {'id': uuid.uuid4().hex, 'tipo': tipo, 'caso': caso, 'titulo': titulo,
            'excluido_em_utc': datetime.now(timezone.utc).isoformat()}
    if conversa:
        item.update(conversa=conversa, rodadas=list(rodadas or []))
    if rodada:
        item['rodada'] = rodada
    itens.append(item)
    salvar(root, itens)
    return item


def restaurar(root, identifier):
    if not isinstance(identifier, str) or not re.fullmatch(ID_CONVERSA, identifier):
        raise ValueError('Identificador da lixeira inválido.')
    itens = registros(root)
    item = next((i for i in itens if i['id'] == identifier and not i.get('restaurado_em_utc')), None)
    if not item:
        raise ValueError('Item não encontrado na lixeira.')
    if item['tipo'] != 'caso' and excluido(root, item['caso']):
        raise ValueError('Restaure primeiro a apuração à qual este item pertence.')
    item['restaurado_em_utc'] = datetime.now(timezone.utc).isoformat()
    salvar(root, itens)
    return item


def alcance(root, identificador):
    """Alcance do apagamento definitivo (sem apagar). Veja scripts/apagamento.py."""
    from apagamento import alcance_publico
    return alcance_publico(root, identificador)


def apagar_definitivamente(root, identificador, confirmacao, *, quem, gerenciador=None, ativa=None):
    """Apaga de vez um item da lixeira, com confirmação derivada do alcance."""
    from apagamento import apagar
    return apagar(root, identificador, confirmacao, quem=quem, gerenciador=gerenciador, ativa=ativa)
