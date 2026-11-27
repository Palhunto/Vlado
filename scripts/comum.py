"""File integrity helpers. No model or network calls."""
from __future__ import annotations

import contextvars
import hashlib
import json
import os
from pathlib import Path
from contextlib import contextmanager
import shutil
import stat
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
VERSAO_PROMPTS = '1.5.0'
# prompts/MESA.md: the Mesa's own instruction (T3). Each round chooses it by its frozen manifest
# (scripts/instrucoes_mesa.py); the chat agent keeps FLUXO_COMPLETO.md, assembled from PARTES only.
VERSAO_MESA = '1.3.0'
PARTES = (
    '00_REGRAS.md', '01_DESCREVER_CORPUS.md', '02_PLANEJAR.md',
    '03_BUSCAR_E_CRUZAR.md', '04_REVISAR_SUPORTE.md',
    '05_SINTETIZAR.md', '06_INCORPORAR_REVISAO_HUMANA.md',
)


# One server request (the boards and the evidence selector; ``pedido``). With a real case, a single
# evidencia-buscar re-checked the frozen inputs of the round once per evidence: 10,872 checks, 13,176 hashes and
# 65,892 path resolutions, 86 s on the Sinfra case (Maestro, 27/11). Inside a request: ``dentro`` resolves each
# (root, relative) once, the modules keep their checks in ``memo`` (the round's inputs, the index, each evidence),
# and ``sha256`` reuses a hash while the file keeps its identity (path, size, mtime_ns, ctime_ns, inode). Where
# the hash is kept depends on the system (B1 of the Coruja on 7f05beb; the Maestro chose custody over 0.8 s):
# - Linux (the server in production): kept between requests (``_HASHES``). Any write changes the ctime, also a
#   write through mmap and a same-size change whose mtime is put back by hand, and the ctime cannot be set back;
#   the next request hashes again and refuses what diverges.
# - Windows (the local desk): kept only inside the request. On NTFS a write through mmap changes neither size,
#   mtime, ctime (the creation time there) nor inode, and the mtime can be put back by hand, so the identity does
#   not prove the content is the same: each request hashes each file again, once.
# On both, a change in the middle of a request is seen by the next one. Outside a request (tests, command line,
# the extraction worker) nothing is remembered.
GUARDA_ENTRE_PEDIDOS = os.name != 'nt'
_PEDIDO = contextvars.ContextVar('vlado_pedido', default=None)
_HASHES: dict = {}  # between requests, only where GUARDA_ENTRE_PEDIDOS
MAXIMO_HASHES = 20000
# The racy-git rule: a file modified in the last FOLGA_HASH_NS could change again within the same mtime tick
# without changing its identity, so its hash is not kept.
FOLGA_HASH_NS = 2_000_000_000


@contextmanager
def pedido():
    """The scope of one server request (see above). A nested scope uses the outer one."""
    if _PEDIDO.get() is not None:
        yield
        return
    token = _PEDIDO.set({})
    try:
        yield
    finally:
        _PEDIDO.reset(token)


def em_pedido() -> bool:
    return _PEDIDO.get() is not None


def memo(nome: str):
    """The request's dict for ``nome`` (a module's per-request checks), or None outside a request."""
    scope = _PEDIDO.get()
    return None if scope is None else scope.setdefault(nome, {})


def _hash_do_arquivo(path) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _identidade(info):
    return (info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_ino, info.st_dev)


def sha256(path: Path) -> str:
    scope = _PEDIDO.get()
    if scope is None:
        return _hash_do_arquivo(path)
    guardados = _HASHES if GUARDA_ENTRE_PEDIDOS else scope.setdefault('hashes', {})
    key = os.fspath(path)
    try:
        before = _identidade(os.stat(key))
    except OSError:
        return _hash_do_arquivo(path)  # raises as before
    known = guardados.get(key)
    if known is not None and known[0] == before:
        return known[1]
    digest = _hash_do_arquivo(path)
    try:
        after = os.stat(key)
    except OSError:
        return digest
    if _identidade(after) == before and time.time_ns() - after.st_mtime_ns > FOLGA_HASH_NS:
        if len(guardados) >= MAXIMO_HASHES:
            guardados.clear()
        guardados[key] = (before, digest)
    return digest


def dentro(root: Path, relative: str) -> Path:
    """Refuse absolute, parent and symlink paths outside the package."""
    rel = Path(relative)
    if not relative or rel.is_absolute() or rel.drive or '..' in rel.parts:
        raise ValueError(f'Caminho nao relativo ao projeto: {relative}')
    resolved = memo('dentro')
    key = (os.fspath(root), os.fspath(relative))
    if resolved is not None and key in resolved:
        return resolved[key]
    resolved_root = resolved.get(os.fspath(root)) if resolved is not None else None
    if resolved_root is None:
        resolved_root = root.resolve()
        if resolved is not None:
            resolved[os.fspath(root)] = resolved_root
    target = (resolved_root / rel).resolve()
    if not target.is_relative_to(resolved_root):
        raise ValueError(f'Caminho fora do projeto: {relative}')
    if resolved is not None:
        resolved[key] = target
    return target


def ler_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def escrever_json(path: Path, value, exclusivo: bool = False):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x' if exclusivo else 'w', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


@contextmanager
def trava_arquivo(caminho: Path):
    """Exclusive advisory lock across processes (server and CLI) for a small JSON store."""
    import os
    trava = Path(str(caminho) + '.lock')
    trava.parent.mkdir(parents=True, exist_ok=True)
    with open(trava, 'a+b') as stream:
        if os.name == 'nt':
            import msvcrt
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)  # retries for ~10 s, then OSError
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)


@contextmanager
def pasta_preparacao(parent: Path, prefix: str):
    """Stage project artifacts with their parent's ACL, including on Windows.

    TemporaryDirectory creates a private directory. Moving its descendants to
    the archive preserves that private ACL and can exclude the desktop user.
    These project-local stages inherit the existing project permissions instead.
    Private upload buffers that are never published still use TemporaryDirectory.
    """
    parent = Path(parent).resolve()
    if not prefix or any(c in prefix for c in '/\\:'):
        raise ValueError('Prefixo de preparação inválido.')
    staging = parent / (prefix + uuid.uuid4().hex)
    staging.mkdir()  # Ordinary project directory: inherits the parent's ACL.
    try:
        yield staging
    finally:
        # Validate the resolved target before recursive cleanup, including junctions.
        if staging.resolve().parent != parent:
            raise ValueError('Diretório de preparação saiu da pasta autorizada.')
        shutil.rmtree(staging)


def conferir_arquivo(root: Path, relative: str, expected: str, *, rotulo='arquivo') -> Path:
    """Distinguish access denial, missing source and content mismatch."""
    try:
        path = dentro(root, relative)
        if not stat.S_ISREG(path.stat().st_mode):
            raise ValueError(f'{rotulo.capitalize()} não é arquivo regular: {relative}')
        actual = sha256(path)
    except PermissionError as exc:
        raise ValueError(f'Acesso negado ao ler {rotulo}: {relative}. '
                         'Verifique as permissões de leitura dessa pasta no Windows.') from exc
    except (FileNotFoundError, NotADirectoryError) as exc:
        raise ValueError(f'{rotulo.capitalize()} ausente: {relative}') from exc
    if actual != expected:
        raise ValueError(f'Hash divergente: {rotulo.capitalize()} {relative}')
    return path


def carregar_corpus(root: Path = ROOT):
    config = ler_json(root / 'configuracao.json')
    if not config.get('manifesto_ativo'):
        raise ValueError('Nenhum caso ativo; cadastrar ou selecionar uma apuracao primeiro.')
    manifest_path = dentro(root, config['manifesto_ativo'])
    manifest = ler_json(manifest_path)
    if manifest.get('caso_id') != config.get('caso_ativo'):
        raise ValueError('Caso ativo e manifesto nao correspondem.')
    return config, manifest_path, manifest


def arquivos_do_cadastro(root: Path, manifest: dict):
    for record in manifest.get('registros_cadastro', []):
        relative = record['arquivo']
        path = Path(relative)
        if path.parts[:3] != ('casos', manifest['caso_id'], 'cadastros'):
            raise ValueError('Recibo não pertence ao cadastro deste caso.')
        source = conferir_arquivo(root, relative, record['sha256'], rotulo='recibo de cadastro')
        yield relative, source


def arquivos_do_corpus(root: Path, manifest: dict):
    list(arquivos_do_cadastro(root, manifest))
    seen_ids = set()
    seen_paths = set()
    for document in manifest['documentos']:
        identifier = document['id']
        if identifier in seen_ids:
            raise ValueError(f'ID repetido: {identifier}')
        seen_ids.add(identifier)
        for item in [document, *document.get('derivados', [])]:
            relative = item['arquivo']
            if relative in seen_paths:
                raise ValueError(f'Arquivo duplicado no corpus: {relative}')
            seen_paths.add(relative)
            path = conferir_arquivo(root, relative, item['sha256'])
            yield relative, path


def capturas_como_documentos(manifest: dict) -> list[dict]:
    """Web captures shaped like documents (id, arquivo, sha256, derivados), for indexing and reading.

    Kept here, with no network code, so the portable copy of `banco.py` (banco, indice_sqlite,
    comum) keeps working. Mode and domain are checked in `fontes_web`; a manifest with captures
    but without the "documentos_web" mode is refused.
    """
    captures = manifest.get('capturas_web') or []
    if captures and (manifest.get('fontes_web') or {}).get('modo') != 'documentos_web':
        raise ValueError('Caso somente documental não pode ter domínio ou capturas web.')
    return [{'id': c['id'], 'arquivo': c['arquivo'], 'sha256': c['sha256'],
             'nome_recebido': c['url_final'], 'tipo_fonte': 'captura_web',
             'origem_informada': {'url_solicitada': c['url_solicitada'], 'url_final': c['url_final'],
                                  'acessado_em_utc': c['acessado_em_utc']},
             'derivados': c.get('derivados', [])} for c in captures]


def documentos_e_capturas(manifest: dict) -> list[dict]:
    return [*manifest.get('documentos', []), *capturas_como_documentos(manifest)]


def fluxo_esperado(root: Path = ROOT) -> bytes:
    header = (
        f'# Apuracao v1 online - fluxo completo v{VERSAO_PROMPTS}\n\n'
        'Procedimento por estados. Carregar este roteiro nao fornece uma pergunta editorial.\n\n'
    )
    text = header + '\n\n---\n\n'.join(
        (root / 'prompts' / name).read_text(encoding='utf-8-sig').strip()
        for name in PARTES
    ) + '\n'
    return text.encode('utf-8')


def manifesto_prompts(root: Path = ROOT) -> dict:
    mesa = root / 'prompts' / 'MESA.md'
    extra = {'mesa': {'arquivo': 'prompts/MESA.md', 'versao': VERSAO_MESA, 'sha256': sha256(mesa)}} if mesa.is_file() else {}
    return {
        'versao': VERSAO_PROMPTS,
        'modulos': [
            {'arquivo': f'prompts/{name}', 'sha256': sha256(root / 'prompts' / name)}
            for name in PARTES
        ],
        'fluxo_completo': {
            'arquivo': 'prompts/FLUXO_COMPLETO.md',
            'sha256': hashlib.sha256(fluxo_esperado(root)).hexdigest(),
        },
        **extra,
    }


def conferir_prompts(root: Path = ROOT):
    path = root / 'prompts' / 'FLUXO_COMPLETO.md'
    if not path.is_file() or path.read_bytes() != fluxo_esperado(root):
        raise ValueError('Fluxo completo ausente ou divergente dos modulos')
    if ler_json(root / 'prompts' / 'manifesto_prompts.json') != manifesto_prompts(root):
        raise ValueError('Manifesto de prompts desatualizado')
    if (root / 'prompts' / 'MESA.md').is_file():
        from instrucoes_mesa import blocos_mesa
        blocos_mesa((root / 'prompts' / 'MESA.md').read_bytes().decode('utf-8-sig'))


def conferir_projeto(root: Path = ROOT) -> dict:
    conferir_prompts(root)
    config = ler_json(root / 'configuracao.json')
    if not config.get('manifesto_ativo'):
        if config.get('caso_ativo'):
            raise ValueError('Caso ativo sem manifesto configurado.')
        return {'estado':'sem_caso_selecionado', 'documentos':0, 'arquivos_autorizados':0,
                'versao_prompts': VERSAO_PROMPTS}
    config, _, manifest = carregar_corpus(root)
    documents = manifest['documentos']
    if not documents:
        raise ValueError('Corpus ativo vazio')
    if len(documents) > config['maximo_documentos_inicial']:
        raise ValueError('Corpus excede o limite configurado')
    files = list(arquivos_do_corpus(root, manifest))
    return {'documentos': len(documents), 'arquivos_autorizados': len(files),
            'corpus_id': manifest['corpus_id'], 'versao_prompts': VERSAO_PROMPTS}
