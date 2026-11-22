"""Server-side limits: tokens per question, per day for the whole installation and per day for each
organization (the newsroom, in the modes with accounts), and draft sizes.

Token values come from configuracao.json "limites" (null disables one limit). The daily
counter lives in ajustes/uso_diario.json (gitignored, Docker volume) and only
keeps the current UTC day: the installation's total and each organization's. Draft sizes (scripts/rascunhos.py) are fixed here: a note of the
Caderno accepts 200 000 characters, so one draft holds it with room to spare.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import threading

from cadastrar_documentos import _atomico
from comum import ler_json, trava_arquivo

# tokens_por_dia is the installation's total; tokens_por_dia_por_organizacao, each newsroom's (null: none
# of its own, only the total). Its value for a pilot with several newsrooms is the operator's to set.
PADROES = {'tokens_por_consulta': 3_000_000, 'tokens_por_dia': 30_000_000, 'tokens_por_dia_por_organizacao': None}
# Bytes of the canonical JSON of a draft's fields, per draft and summed over every open draft of a case.
RASCUNHOS = {'bytes_por_rascunho': 1024 * 1024, 'bytes_rascunhos_por_caso': 16 * 1024 * 1024,
             'rascunhos_por_caso': 200,
             # A guest (convidado) keeps few drafts, so one guest cannot fill the case's limit for everyone.
             'rascunhos_por_convidado': 10,
             # Files (open drafts + discard marks) per account and case; past it, the oldest marks are deleted.
             'arquivos_por_convidado': 20, 'arquivos_por_conta': 200}
_TRAVA = threading.Lock()


def hoje() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%d')


def ler(root: Path) -> dict:
    try:
        config = ler_json(Path(root) / 'configuracao.json')
    except (OSError, ValueError) as exc:
        raise ValueError('configuracao.json ilegível; não foi possível ler os limites.') from exc
    valores = config.get('limites', {}) if isinstance(config, dict) else None
    if not isinstance(valores, dict) or set(valores) - set(PADROES):
        raise ValueError('"limites" em configuracao.json aceita só ' + ', '.join(PADROES) + '.')
    resultado = {**PADROES, **valores}
    for chave, valor in resultado.items():
        if valor is not None and (type(valor) is not int or valor < 1):
            raise ValueError(f'limites.{chave} deve ser um inteiro positivo ou null.')
    return resultado


def _arquivo(root: Path) -> Path:
    return Path(root) / 'ajustes' / 'uso_diario.json'


def _contagem(valor) -> int:
    return valor if type(valor) is int and valor >= 0 else 0


def _hoje(root: Path) -> dict:
    """Today's counter: {'tokens': installation total, 'organizacoes': {organization: tokens}}."""
    arquivo = _arquivo(root)
    vazio = {'tokens': 0, 'organizacoes': {}}
    if not arquivo.is_file():
        return vazio
    try:
        dados = json.loads(arquivo.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return vazio  # a damaged counter must not block the installation; it restarts from zero
    if not isinstance(dados, dict) or dados.get('dia') != hoje():
        return vazio
    organizacoes = dados.get('organizacoes')
    organizacoes = {k: _contagem(v) for k, v in organizacoes.items() if isinstance(k, str) and k} \
        if isinstance(organizacoes, dict) else {}
    return {'tokens': _contagem(dados.get('tokens', 0)), 'organizacoes': organizacoes}


def _total(root: Path) -> int:
    return _hoje(root)['tokens']


def dia_da_organizacao(root: Path, organizacao: str) -> int:
    """Tokens one organization (a newsroom, in the modes with accounts) spent today."""
    return _hoje(root)['organizacoes'].get(organizacao, 0)


def somar_dia(root: Path, tokens: int, organizacao: str | None = None) -> int:
    """Add to today's installation total and, with ``organizacao``, to that organization's; returns the total."""
    with _TRAVA, trava_arquivo(_arquivo(root)):
        atual, somar = _hoje(root), max(0, int(tokens))
        atual['tokens'] += somar
        if isinstance(organizacao, str) and organizacao:
            atual['organizacoes'][organizacao] = atual['organizacoes'].get(organizacao, 0) + somar
        arquivo = _arquivo(root)
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        _atomico(arquivo, (json.dumps({'dia': hoje(), **atual}, sort_keys=True) + '\n').encode('utf-8'))
        return atual['tokens']


# No answer carries a number that adds up several newsrooms (accounts contract, 4.5): the installation's
# refusal has none; a newsroom's carries only its own limit.
DIA_INSTALACAO = 'Limite diário de uso da instalação atingido. Novas perguntas voltam amanhã (UTC).'


def conferir_dia(root: Path, organizacao: str | None = None) -> None:
    """Before a question: the installation's daily total, then the organization's (when it has a limit)."""
    valores = ler(root)
    atual = _hoje(root)
    if valores['tokens_por_dia'] is not None and atual['tokens'] >= valores['tokens_por_dia']:
        raise ValueError(DIA_INSTALACAO)
    limite = valores['tokens_por_dia_por_organizacao']
    if limite is not None and organizacao and atual['organizacoes'].get(organizacao, 0) >= limite:
        raise ValueError(f'Limite diário de tokens da redação atingido ({limite}). Novas perguntas voltam amanhã (UTC).')


def conferir_tamanho(tamanho: int, limite: int, rotulo: str) -> None:
    """Refuse a stored item over its byte limit; the message carries the limit in KB."""
    if tamanho > limite:
        raise ValueError(f'{rotulo} (limite de {limite // 1024} KB). Reduza o texto ou divida-o em partes.')
