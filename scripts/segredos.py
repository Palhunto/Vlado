"""API keys pasted in the Mesa: stored outside git, never returned to the browser.

Order of precedence: environment variable of the server process, then the
saved file. The file lives in `segredos/chaves.json` (gitignored) or in the
path given by VLADO_SEGREDOS (e.g. a Docker volume). Only the last four
characters ever leave this module.

A newsroom may have a key of its own (contract of accounts, 8.5), kept in `chaves_redacoes.json` next to that
file, by newsroom id. Every function takes `redacao`: with it, the newsroom's own key comes first and the key of
the service (environment, then file) is what is left; of the service's key a newsroom only ever learns that it
exists. A separate file, so that the key of the service is never rewritten when a newsroom saves its own.
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
ARQUIVO_DAS_REDACOES = 'chaves_redacoes.json'
_REDACAO = re.compile(r'org[0-9a-f]{16}')  # the id the accounts store gives a newsroom: never a name, never a path
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


def caminho_das_redacoes(root: Path) -> Path:
    return caminho(root).parent / ARQUIVO_DAS_REDACOES


def _redacao(redacao) -> str:
    if not isinstance(redacao, str) or not _REDACAO.fullmatch(redacao):
        raise ValueError('Redação inválida para a chave de API.')
    return redacao


class ChavesIlegiveis(ValueError):
    """The file of the newsrooms' keys exists and cannot be read. Whose key it held is unknown, so no newsroom
    falls on the key of the service in its place (contract of accounts, 8.5): its data would go through the
    service's provider account and its spend to the quota the service pays, without it knowing. The key of the
    service, asked without a newsroom, never reads this file."""


ILEGIVEIS = ('O arquivo de chaves de IA das redações está ilegível. Restaure-o a partir da cópia guardada com os '
             'segredos; até lá, nenhuma redação usa a IA pela Mesa e nenhuma chave de redação é gravada.')


def _ler_redacoes(root: Path) -> dict:
    """{newsroom id: {provider: key}}, only what is well formed. Raises `ChavesIlegiveis` when the file is there
    and is not a JSON object."""
    arquivo = caminho_das_redacoes(root)
    if not arquivo.is_file():
        return {}
    try:
        dados = json.loads(arquivo.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise ChavesIlegiveis(ILEGIVEIS) from exc
    if not isinstance(dados, dict):
        raise ChavesIlegiveis(ILEGIVEIS)
    return {redacao: {k: v for k, v in chaves.items() if k in CHAVES_AMBIENTE and isinstance(v, str)}
            for redacao, chaves in dados.items() if _REDACAO.fullmatch(str(redacao)) and isinstance(chaves, dict)}


def _da_redacao(root: Path, provedor: str, redacao) -> str | None:
    return _ler_redacoes(root).get(_redacao(redacao), {}).get(provedor) if redacao is not None else None


def _gravar(root: Path, dados: dict, arquivo: Path | None = None) -> None:
    arquivo = arquivo or caminho(root)
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    _atomico(arquivo, (json.dumps(dados, indent=2) + '\n').encode('utf-8'))
    try:
        os.chmod(arquivo, 0o600)  # best effort; Windows keeps the folder ACL
    except OSError:
        pass


def origem_da_chave(root: Path, provedor: str, redacao=None) -> str | None:
    """Where the key `ler_chave` gives comes from: 'redacao' (the newsroom's own, which the service does not pay
    for), 'ambiente' or 'salva' (the key of the service), or None when there is none."""
    _provedor(provedor)
    if _da_redacao(root, provedor, redacao):
        return 'redacao'
    if os.environ.get(CHAVES_AMBIENTE[provedor], '').strip():
        return 'ambiente'
    return 'salva' if _ler(root).get(provedor) else None


def ler_chave(root: Path, provedor: str, redacao=None) -> str | None:
    """The key to call the provider with. With `redacao`: the newsroom's own key when it has one, else the key of
    the service (environment, then file), as for a caller without a newsroom."""
    propria = _da_redacao(root, _provedor(provedor), redacao)
    if propria:
        return _registrar(propria)
    do_ambiente = os.environ.get(CHAVES_AMBIENTE[provedor], '').strip()
    if do_ambiente:
        return _registrar(do_ambiente)
    return _registrar(_ler(root).get(provedor))


def salvar_chave(root: Path, provedor: str, chave, redacao=None) -> None:
    """Save the key of the service or, with `redacao`, the newsroom's own (the service's is not touched)."""
    _provedor(provedor)
    if redacao is not None:
        _redacao(redacao)
    if not isinstance(chave, str) or not FORMATO.fullmatch(chave.strip()):
        # Never echo the submitted value: it may be a real key with a typo.
        raise ValueError('Chave de API em formato inválido: cole somente a chave, sem espaços (20 a 300 caracteres).')
    if redacao is None:
        with _TRAVA, trava_arquivo(caminho(root)):
            dados = _ler(root)
            dados[provedor] = chave.strip()
            _gravar(root, dados)
    else:
        with _TRAVA, trava_arquivo(caminho_das_redacoes(root)):
            dados = _ler_redacoes(root)
            dados.setdefault(redacao, {})[provedor] = chave.strip()
            _gravar(root, dados, caminho_das_redacoes(root))
    _registrar(chave.strip())


def remover_chave(root: Path, provedor: str, redacao=None) -> None:
    _provedor(provedor)
    if redacao is None:
        with _TRAVA, trava_arquivo(caminho(root)):
            dados = _ler(root)
            if dados.pop(provedor, None) is not None:
                _gravar(root, dados)
        return
    _redacao(redacao)
    with _TRAVA, trava_arquivo(caminho_das_redacoes(root)):
        dados = _ler_redacoes(root)
        if dados.get(redacao, {}).pop(provedor, None) is not None:
            if not dados[redacao]:
                del dados[redacao]
            _gravar(root, dados, caminho_das_redacoes(root))


def resumo(root: Path, redacao=None) -> dict:
    """Presence, origin and last four characters only. With `redacao`, what that newsroom may know: its own key
    (origin 'redacao', with the last four characters) or, when it has none, only whether the service has one
    (origin 'servico', nothing of the key itself)."""
    proprias = _ler_redacoes(root).get(_redacao(redacao), {}) if redacao is not None else {}
    saida = {}
    for provedor, variavel in CHAVES_AMBIENTE.items():
        do_ambiente = os.environ.get(variavel, '').strip()
        salva = None if do_ambiente else _ler(root).get(provedor)
        valor = do_ambiente or salva
        if redacao is None:
            saida[provedor] = {'configurada': bool(valor), 'origem': ('ambiente' if do_ambiente else 'salva' if salva else None),
                               'final': valor[-4:] if valor else None}
        elif proprias.get(provedor):
            saida[provedor] = {'configurada': True, 'origem': 'redacao', 'final': proprias[provedor][-4:]}
        else:
            saida[provedor] = {'configurada': bool(valor), 'origem': 'servico' if valor else None, 'final': None}
    return saida


def conferir_chaves_das_redacoes(root: Path) -> str | None:
    """For the start of the server: the warning for the operator when the file of the newsrooms' keys is there
    and unreadable, or None. It also goes to the audit log (`chaves_ia_ilegiveis`). Nothing is repaired here."""
    try:
        _ler_redacoes(root)
        return None
    except ChavesIlegiveis:
        pass
    import registro_acesso
    registro_acesso.lembrar_raiz(root)
    registro_acesso.registrar('chaves_ia_ilegiveis', 'falha')
    return f'ATENÇÃO: {ILEGIVEIS}'
