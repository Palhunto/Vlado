"""API keys pasted in the Mesa: stored outside git, never returned to the browser.

Order of precedence: environment variable of the server process, then the
saved file. The file lives in `segredos/chaves.json` (gitignored) or in the
path given by VLADO_SEGREDOS (e.g. a Docker volume). Only the last four
characters ever leave this module.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import threading

from cadastrar_documentos import _atomico
from comum import trava_arquivo

CHAVES_AMBIENTE = {'anthropic': 'ANTHROPIC_API_KEY', 'openai': 'OPENAI_API_KEY'}
FORMATO = re.compile(r'[A-Za-z0-9_\-.]{20,300}')
_TRAVA = threading.Lock()
_CONHECIDAS: set[str] = set()


def conhecidas() -> frozenset[str]:
    """Values read or saved in this process, so error redaction can remove them verbatim."""
    return frozenset(_CONHECIDAS)


def _registrar(valor: str | None) -> str | None:
    if valor and len(valor) >= 8:
        _CONHECIDAS.add(valor)
    return valor


def caminho(root: Path) -> Path:
    destino = os.environ.get('VLADO_SEGREDOS', '').strip()
    return Path(destino) if destino else Path(root) / 'segredos' / 'chaves.json'


def _provedor(provedor: str) -> str:
    if provedor not in CHAVES_AMBIENTE:
        raise ValueError('Provedor de API desconhecido.')
    return provedor


def _ler(root: Path) -> dict:
    arquivo = caminho(root)
    if not arquivo.is_file():
        return {}
    try:
        dados = json.loads(arquivo.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise ValueError('O arquivo de chaves salvas está ilegível; salve a chave novamente.') from exc
    return {k: v for k, v in dados.items() if k in CHAVES_AMBIENTE and isinstance(v, str)} if isinstance(dados, dict) else {}


def _gravar(root: Path, dados: dict) -> None:
    arquivo = caminho(root)
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    _atomico(arquivo, (json.dumps(dados, indent=2) + '\n').encode('utf-8'))
    try:
        os.chmod(arquivo, 0o600)  # best effort; Windows keeps the folder ACL
    except OSError:
        pass


def ler_chave(root: Path, provedor: str) -> str | None:
    do_ambiente = os.environ.get(CHAVES_AMBIENTE[_provedor(provedor)], '').strip()
    if do_ambiente:
        return _registrar(do_ambiente)
    return _registrar(_ler(root).get(provedor))


def salvar_chave(root: Path, provedor: str, chave) -> None:
    _provedor(provedor)
    if not isinstance(chave, str) or not FORMATO.fullmatch(chave.strip()):
        # Never echo the submitted value: it may be a real key with a typo.
        raise ValueError('Chave de API em formato inválido: cole somente a chave, sem espaços (20 a 300 caracteres).')
    with _TRAVA, trava_arquivo(caminho(root)):
        dados = _ler(root)
        dados[provedor] = chave.strip()
        _gravar(root, dados)
    _registrar(chave.strip())


def remover_chave(root: Path, provedor: str) -> None:
    _provedor(provedor)
    with _TRAVA, trava_arquivo(caminho(root)):
        dados = _ler(root)
        if dados.pop(provedor, None) is not None:
            _gravar(root, dados)


def resumo(root: Path) -> dict:
    """Presence, origin and last four characters only."""
    saida = {}
    for provedor, variavel in CHAVES_AMBIENTE.items():
        do_ambiente = os.environ.get(variavel, '').strip()
        salva = None if do_ambiente else _ler(root).get(provedor)
        valor = do_ambiente or salva
        saida[provedor] = {'configurada': bool(valor), 'origem': ('ambiente' if do_ambiente else 'salva' if salva else None),
                           'final': valor[-4:] if valor else None}
    return saida
