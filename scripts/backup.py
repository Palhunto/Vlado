"""Backup and restore of the Mesa's data folders (cases, conversations, rounds, access, settings).

Two ways to use it:

* Manual (unchanged): `criar` writes a .tar.gz, `restaurar` reads it. Add `--cifrar-para` to get an
  age-encrypted file instead.
* Scheduled (SEG-03): the `backup` Compose service runs `agendado`: every day it snapshots the data
  folders (read-only mounts), encrypts the archive with age to PUBLIC keys only (the server can write
  backups but never read them), uploads it with rclone to a destination outside the server, prunes old
  copies by a retention rule and records the outcome in a status file that feeds the health check.

The decryption (private) key is never on the server, in the image, in git or in logs. API keys in
segredos/ are left out unless asked: a pasted key can be pasted again, and a backup is easier to leak than a
server volume. Everything else a user created is in: cases, rounds, conversations, trash, intake, accounts
(with password hashes) and settings.

  python scripts/backup.py criar --destino backups/ [--cifrar-para age1... | ARQUIVO_DE_CHAVES_PUBLICAS]
  python scripts/backup.py criar --destino -  > vlado-dados.tar.gz      (stream, e.g. from a container)
  python scripts/backup.py restaurar ARQUIVO [--identidade CHAVE_PRIVADA] [--substituir]
  python scripts/backup.py restaurar --do-destino ultimo|NOME --identidade CHAVE_PRIVADA --substituir
  python scripts/backup.py verificar ARQUIVO|--do-destino ultimo --identidade CHAVE_PRIVADA
  python scripts/backup.py rodada | agendado | listar | saude        (service commands, configured by VLADO_BACKUP_*)
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request

ROOT = Path(os.environ.get('VLADO_BACKUP_RAIZ') or Path(__file__).resolve().parents[1])
PASTAS = ('casos', 'conversas', 'execucoes', 'lixeira', 'entrada', 'acesso', 'ajustes')
SEGREDOS = 'segredos'
MANIFESTO = 'manifesto_backup.json'
PROIBIDOS = (chr(92), ':', chr(0))  # backslash (Windows separator), drive letter, NUL
# Work in progress that the application publishes by renaming: never part of a backup, and while one
# exists a multi-file operation (registration, freezing, notebook save, index build) is under way.
# `casos/.cadastro.lock` (a folder) is the old registration lock and `.trava` the notebook's; the rest are
# staging folders. The current registration lock is NOT a marker: `casos/.cadastro.trava` is a file that always
# exists and is held with an operating-system lock; see `_trava_cadastro_em_uso`.
MARCADORES = ('.cadastro.lock', '.trava', '.lote_', '.web_', '.preparacao_', '.indice_', '.r_', '.publicacao_',
              '.restaurando-', '.antiga-')
TRAVA_CADASTRO = '.cadastro.trava'
# A staging folder older than this is leftover of a crash (the application only clears it on its next start):
# it is left out of the backup and reported, but it no longer makes the backup wait.
MARCADOR_IDADE_MAX_S = 7200.0
RETENCAO_PADRAO = 'diarios=7,semanais=4,mensais=6'
PREFIXO = 'vlado'
SUFIXO_CIFRADO = '.tar.gz.age'


def _pastas(incluir_segredos: bool) -> tuple[str, ...]:
    return PASTAS + ((SEGREDOS,) if incluir_segredos else ())


class BackupOcupado(ValueError):
    """An operation that writes several files is under way; a backup now could mix two states."""


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _marcador(nome: str) -> bool:
    return nome.startswith(MARCADORES)


def _trava_cadastro_em_uso(root: Path) -> bool:
    """Is someone holding the registration lock right now? A probe that never keeps the lock.

    The lock is `casos/.cadastro.trava` (an `flock` on Linux). The file is opened read-only (the backup mounts the
    data read-only), a non-blocking SHARED lock is tried and released at once: it fails only while the holder has
    the exclusive lock, and it is gone before a user's registration can notice it. The lock is never held while
    copying, otherwise registrations would be refused for as long as a backup runs. The file existing, or its text
    saying 'ocupada' after a crash, means nothing: only the operating-system lock does. (Windows, development
    only, has no flock: there the recorded owner decides.)"""
    caminho = root / 'casos' / TRAVA_CADASTRO
    try:
        descritor = os.open(caminho, os.O_RDONLY | getattr(os, 'O_BINARY', 0))
    except OSError:
        return False  # never created: no registration has ever run here
    try:
        if os.name == 'nt':
            try:
                registro = json.loads(os.read(descritor, 2048).replace(bytes(1), b'').strip() or b'{}')
            except ValueError:
                return False
            return isinstance(registro, dict) and registro.get('estado') == 'ocupada'
        import fcntl
        try:
            fcntl.flock(descritor, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except OSError:
            return True
        fcntl.flock(descritor, fcntl.LOCK_UN)
        return False
    finally:
        os.close(descritor)


def _assinatura_casos(root: Path):
    """Proof that no registration, freezing, web-capture publication or deletion finished while a backup copied:
    the state of `casos/.cadastro.trava`. Whoever takes the lock writes 'ocupada' and, on release, 'livre' (the same
    bytes as before), but the inode times change on every operation. None while the file does not exist."""
    try:
        estado = os.stat(root / 'casos' / TRAVA_CADASTRO)
    except OSError:
        return None
    return (estado.st_ino, estado.st_mtime_ns, estado.st_ctime_ns)


def _inspecionar_marcadores(root: Path, pastas: tuple[str, ...]) -> tuple[list[str], list[str]]:
    """(live, abandoned) signs of work in progress under the data folders. Read-only look; no lock is held.
    The operating-system probe is the reliable sign for the registration lock; a staging folder counts only while
    it is recent (see MARCADOR_IDADE_MAX_S), because a crash leaves them behind."""
    limite = float(os.environ.get('VLADO_BACKUP_MARCADOR_IDADE_MAX_S') or MARCADOR_IDADE_MAX_S)
    vivos, abandonados = [], []
    if 'casos' in pastas and _trava_cadastro_em_uso(root):
        vivos.append(f'casos/{TRAVA_CADASTRO} (cadastro em curso)')
    agora = time.time()
    for pasta in pastas:
        base = root / pasta
        if not base.is_dir():
            continue
        for atual, dirs, arquivos in os.walk(base):
            for nome in dirs + arquivos:
                if _marcador(nome):
                    caminho = Path(atual, nome)
                    try:
                        idade = agora - caminho.stat().st_mtime
                    except OSError:
                        continue  # gone already
                    (vivos if idade <= limite else abandonados).append(caminho.relative_to(root).as_posix())
            dirs[:] = [d for d in dirs if not _marcador(d)]
    return sorted(vivos), sorted(abandonados)


def _marcadores(root: Path, pastas: tuple[str, ...]) -> list[str]:
    return _inspecionar_marcadores(root, pastas)[0]


def _aguardar_ociosidade(root: Path, pastas: tuple[str, ...], espera: float, passo: float = 5.0) -> None:
    limite = time.monotonic() + espera
    while True:
        ocupado = _marcadores(root, pastas)
        if not ocupado:
            return
        if time.monotonic() >= limite:
            raise BackupOcupado('Há operação em andamento (' + ', '.join(ocupado[:3]) +
                                '); o backup não foi feito para não misturar dois estados.')
        time.sleep(min(passo, max(0.0, limite - time.monotonic())))


def _entradas(root: Path, pastas: tuple[str, ...]):
    """(posix path, Path, is_dir) of every directory and regular file, deterministic; skips staging and links.
    The last item is (None, list of skipped non-regular paths, None)."""
    ignorados = []
    for pasta in pastas:
        base = root / pasta
        if not base.is_dir():
            continue
        yield pasta, base, True
        pilha = [base]
        while pilha:
            atual = pilha.pop()
            with os.scandir(atual) as it:
                itens = sorted(it, key=lambda e: e.name)
            subpastas = []
            for item in itens:
                relativo = Path(item.path).relative_to(root).as_posix()
                if _marcador(item.name):
                    continue
                if item.is_file(follow_symlinks=False) and (item.name == TRAVA_CADASTRO or item.name.endswith('.lock')):
                    continue  # lock files are not data: a restored lock record would look like an abandoned lock
                if item.is_symlink() or not (item.is_dir(follow_symlinks=False) or item.is_file(follow_symlinks=False)):
                    ignorados.append(relativo)
                    continue
                if item.is_dir(follow_symlinks=False):
                    yield relativo, Path(item.path), True
                    subpastas.append(Path(item.path))
                else:
                    yield relativo, Path(item.path), False
            pilha.extend(reversed(subpastas))
    yield None, ignorados, None


def _valida(caminho: Path, conteudo: Path) -> str | None:
    """Reason a copied file is unusable (partial JSON, damaged SQLite), or None."""
    sufixo = caminho.suffix.lower()
    if sufixo == '.json':
        try:
            json.loads(conteudo.read_bytes().decode('utf-8-sig'))
        except (ValueError, OSError):
            return 'JSON ilegível'
    elif sufixo in ('.sqlite', '.sqlite3', '.db'):
        import sqlite3
        try:
            ligacao = sqlite3.connect(conteudo.resolve().as_uri() + '?mode=ro', uri=True)
            try:
                if ligacao.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                    return 'SQLite com falha no quick_check'
            finally:
                ligacao.close()
        except sqlite3.Error:
            return 'SQLite ilegível'
    return None


def _copiar(caminho: Path, trabalho: Path):
    """Copy to a new temporary file; returns (copy, sha256, stat before, stat after). None if the file vanished."""
    try:
        antes = os.stat(caminho)
        descritor, nome = tempfile.mkstemp(dir=trabalho, prefix='copia-')
        destino = Path(nome)
        resumo = hashlib.sha256()
        with open(caminho, 'rb') as origem, os.fdopen(descritor, 'wb') as saida:
            for bloco in iter(lambda: origem.read(1 << 20), b''):
                resumo.update(bloco)
                saida.write(bloco)
        depois = os.stat(caminho)
    except FileNotFoundError:
        return None
    return destino, resumo.hexdigest(), antes, depois


def _copia_estavel(caminho: Path, trabalho: Path, tentativas: int = 4):
    """Copy one file so that it is a state the writer really had: size and mtime must not change while reading
    and the copy must be valid (JSON parses, SQLite passes quick_check). After the retries the last readable
    state is kept with a problem note. Returns (copy path, sha256, bytes, stat key, problem); None if the
    file vanished."""
    ultimo = None
    for tentativa in range(tentativas):
        copia = _copiar(caminho, trabalho)
        if copia is None:
            return None
        destino, resumo, antes, depois = copia
        chave = (depois.st_size, depois.st_mtime_ns)
        problema = None
        if (antes.st_size, antes.st_mtime_ns) != chave or destino.stat().st_size != depois.st_size:
            problema = 'arquivo mudou durante a leitura'
        else:
            problema = _valida(caminho, destino)
        ultimo = (destino, resumo, depois.st_size, chave, problema)
        if problema is None:
            return ultimo
        if tentativa < tentativas - 1:
            destino.unlink(missing_ok=True)
            time.sleep(0.2 * (tentativa + 1))
    return ultimo


def _escrever_pacote(root: Path, pacote: tarfile.TarFile, incluir_segredos: bool, trabalho: Path | None = None) -> dict:
    """One streaming pass: every data file is copied to a stable temporary copy, hashed and added; the manifest
    (with the hash of each file) goes last. Reads only; never writes under `root`."""
    pastas = _pastas(incluir_segredos)
    incluidas = [p for p in pastas if (root / p).is_dir()]
    dono_tmp = trabalho is None
    trabalho = Path(tempfile.mkdtemp(prefix='vlado-backup-')) if dono_tmp else Path(trabalho)
    trabalho.mkdir(parents=True, exist_ok=True)
    arquivos, avisos, chaves, ignorados = {}, [], {}, []
    avisos += [f'pasta de preparo abandonada, fora do backup: {a}' for a in _inspecionar_marcadores(root, pastas)[1]]
    try:
        for relativo, caminho, eh_dir in _entradas(root, pastas):
            if relativo is None:
                ignorados = caminho
                break
            if eh_dir:
                info = pacote.gettarinfo(str(caminho), arcname=relativo)
                info.uid = info.gid = 0
                info.uname = info.gname = ''
                pacote.addfile(info)
                continue
            copia = _copia_estavel(caminho, trabalho)
            if copia is None:
                continue  # removed while the backup ran: not part of this state
            destino, resumo, tamanho, chave, problema = copia
            try:
                info = pacote.gettarinfo(str(destino), arcname=relativo)
                info.mode = caminho.stat().st_mode & 0o777
                info.uid = info.gid = 0
                info.uname = info.gname = ''
                with open(destino, 'rb') as stream:
                    pacote.addfile(info, stream)
            finally:
                destino.unlink(missing_ok=True)
            arquivos[relativo] = {'sha256': resumo, 'bytes': tamanho}
            chaves[relativo] = chave
            if problema:
                avisos.append(f'{relativo}: {problema}')
        mudou = 0
        for relativo, caminho, eh_dir in _entradas(root, pastas):
            if relativo is None:
                break
            if not eh_dir:
                try:
                    atual = caminho.stat()
                except FileNotFoundError:
                    mudou += 1
                    continue
                if relativo not in chaves or chaves[relativo] != (atual.st_size, atual.st_mtime_ns):
                    mudou += 1
        manifesto = {'versao_manifesto': 2, 'criado_em_utc': _agora().strftime('%Y-%m-%dT%H:%M:%SZ'),
                     'pastas': incluidas, 'segredos_incluidos': SEGREDOS in incluidas,
                     'ambiente': os.environ.get('VLADO_AMBIENTE', '').strip() or None,
                     'arquivos': arquivos, 'ignorados_nao_regulares': ignorados,
                     'mudancas_apos_a_leitura': mudou, 'avisos': avisos}
        dados = json.dumps(manifesto, indent=2, ensure_ascii=False).encode('utf-8')
        info = tarfile.TarInfo(MANIFESTO)
        info.size = len(dados)
        info.mtime = int(time.time())
        pacote.addfile(info, io.BytesIO(dados))
        return manifesto
    finally:
        if dono_tmp:
            shutil.rmtree(trabalho, ignore_errors=True)


def _gravar(root: Path, pacote: tarfile.TarFile, incluir_segredos: bool, trabalho: Path | None = None) -> dict:
    return _escrever_pacote(root, pacote, incluir_segredos, trabalho)


# --- age (encryption to public keys) ---------------------------------------------------------------------

_AGE_PUBLICA = re.compile(r'^age1[0-9a-z]{58}$')


def _destinatarios(valor: str | None) -> list[str]:
    """Public recipients from a value that is either the keys themselves (spaces, commas or lines) or a file of
    them. A private key is refused: it must never reach a server."""
    if not valor or not valor.strip():
        return []
    texto = valor.strip()
    if '\n' not in texto and len(texto) < 400 and not texto.startswith(('age1', 'ssh-')) and Path(texto).is_file():
        texto = Path(texto).read_text(encoding='utf-8')
    if 'AGE-SECRET-KEY' in texto:
        raise ValueError('O valor dos destinatários contém uma chave PRIVADA do age. Use só a chave pública (age1...); '
                         'a privada fica com o dono, fora do servidor.')
    chaves = []
    for linha in texto.replace(',', '\n').splitlines():
        linha = linha.split('#', 1)[0].strip()
        for item in ([linha] if linha.startswith('ssh-') else linha.split()):
            if not item:
                continue
            if not (_AGE_PUBLICA.fullmatch(item) or item.startswith('ssh-')):
                raise ValueError('Destinatário inválido: esperava uma chave pública age1... (nada foi cifrado).')
            chaves.append(item)
    return chaves


def _age(args: list[str], **opcoes) -> subprocess.Popen:
    exe = shutil.which('age')
    if not exe:
        raise ValueError('O programa `age` não está instalado aqui; use a imagem de backup do Compose.')
    return subprocess.Popen([exe, *args], **opcoes)


def _cifrar_para(destinatarios: list[str], saida) -> subprocess.Popen:
    argumentos = []
    for chave in destinatarios:
        argumentos += ['-r', chave]
    return _age(argumentos, stdin=subprocess.PIPE, stdout=saida, stderr=subprocess.PIPE)


def _decifrar(origem: Path, identidade: Path, destino: Path) -> None:
    processo = _age(['-d', '-i', str(identidade), '-o', str(destino), str(origem)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    _, erro = processo.communicate()
    if processo.returncode != 0:
        destino.unlink(missing_ok=True)
        raise ValueError('Não foi possível decifrar o backup (chave errada, arquivo adulterado ou truncado): '
                         + erro.decode('utf-8', 'replace').strip()[:200])


def _novo_arquivo(destino: Path, nome: str) -> int:
    destino.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Reporting material and password hashes: owner-only from the first byte, whatever the umask.
    return os.open(destino / nome, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0), 0o600)


def _nome(ambiente: str | None, cifrado: bool) -> str:
    carimbo = _agora().strftime('%Y%m%dT%H%M%S%fZ')
    if ambiente is None:
        return f'{PREFIXO}-dados-{carimbo}' + (SUFIXO_CIFRADO if cifrado else '.tar.gz')
    return f'{PREFIXO}-{ambiente}-{carimbo}' + SUFIXO_CIFRADO


def _gravar_arquivo(root: Path, destino: Path, nome: str, incluir_segredos: bool, destinatarios: list[str],
                    trabalho: Path | None, espera: float = 0.0, tentativas: int = 3):
    """Write one backup file (encrypted when there are recipients). Starts over when a work-in-progress
    sentinel shows up during the copy. Returns (path, manifest)."""
    pastas = _pastas(incluir_segredos)
    ultimo = []
    for _ in range(tentativas):
        _aguardar_ociosidade(root, pastas, espera)
        antes = _assinatura_casos(root)
        descritor = _novo_arquivo(destino, nome)
        arquivo = destino / nome
        try:
            with os.fdopen(descritor, 'wb') as saida:
                if destinatarios:
                    processo = _cifrar_para(destinatarios, saida)
                    try:
                        with tarfile.open(fileobj=processo.stdin, mode='w|gz') as pacote:
                            manifesto = _escrever_pacote(root, pacote, incluir_segredos, trabalho)
                    finally:
                        processo.stdin.close()
                        erro = processo.stderr.read()
                        processo.stderr.close()
                        processo.wait()
                    if processo.returncode != 0:
                        raise ValueError('Falha ao cifrar o backup: ' + erro.decode('utf-8', 'replace').strip()[:200])
                else:
                    with tarfile.open(fileobj=saida, mode='w:gz') as pacote:
                        manifesto = _escrever_pacote(root, pacote, incluir_segredos, trabalho)
        except BaseException:
            arquivo.unlink(missing_ok=True)
            raise
        ultimo = _marcadores(root, pastas)
        if not ultimo and 'casos' in pastas and _assinatura_casos(root) != antes:
            ultimo = [f'casos/{TRAVA_CADASTRO} (uma operação terminou durante a cópia)']
        if not ultimo:
            _restrito(arquivo)
            return arquivo, manifesto
        arquivo.unlink(missing_ok=True)
    raise BackupOcupado('Operação em andamento durante a cópia (' + ', '.join(ultimo[:3]) + '); backup descartado.')


def criar(root: Path, destino: Path, incluir_segredos: bool = False, destinatarios: list[str] | None = None) -> Path:
    cifra = list(destinatarios or [])
    arquivo, _ = _gravar_arquivo(Path(root), Path(destino), _nome(None, bool(cifra)), incluir_segredos, cifra, None)
    return arquivo


def _conferir(membro: tarfile.TarInfo) -> None:
    if membro.name == MANIFESTO and membro.isfile():
        return
    caminho = PurePosixPath(membro.name)
    if (any(c in membro.name for c in PROIBIDOS) or caminho.is_absolute() or '..' in caminho.parts
            or not caminho.parts or caminho.parts[0] not in PASTAS + (SEGREDOS,)
            or not (membro.isfile() or membro.isdir())):
        raise ValueError(f'O backup contém um item fora das pastas de dados: {membro.name!r}. Nada foi restaurado.')


def _restrito(caminho: Path) -> None:
    try:
        os.chmod(caminho, 0o600)
    except OSError:
        pass


def _encerrar_sessoes_restauradas(arquivo: Path) -> None:
    """Sessions in a backup are stale: everyone signs in again after a restore."""
    if not arquivo.is_file():
        return
    try:
        dados = json.loads(arquivo.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return  # the server reports an unreadable store on its own
    if isinstance(dados, dict) and dados.get('sessoes'):
        dados['sessoes'] = {}
        arquivo.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        _restrito(arquivo)


def _extrair(pacote: tarfile.TarFile, membros, destino: Path, raiz: str | None = None) -> None:
    """Write members under `destino`; with `raiz`, members of that data folder land without the folder prefix."""
    for membro in membros:
        if membro.name == MANIFESTO:
            continue
        partes = PurePosixPath(membro.name).parts
        relativo = PurePosixPath(*partes[1:]) if raiz is not None else PurePosixPath(membro.name)
        if raiz is not None and not partes[1:]:
            continue  # the data folder itself
        alvo = destino / relativo
        if not alvo.resolve().is_relative_to(destino.resolve()):
            raise ValueError(f'O backup contém um item fora das pastas de dados: {membro.name!r}. Nada foi restaurado.')
        if membro.isdir():
            alvo.mkdir(parents=True, exist_ok=True)
            continue
        alvo.parent.mkdir(parents=True, exist_ok=True)
        with pacote.extractfile(membro) as origem, alvo.open('xb') as saida:
            shutil.copyfileobj(origem, saida)
        if raiz in ('acesso', SEGREDOS):
            _restrito(alvo)  # password hashes and keys: owner only, whatever the umask


def _conferir_ambiente(pacote: tarfile.TarFile, membros, outro_ambiente: bool) -> None:
    """An editorial backup must not land in a demo volume (or the reverse) by mistake."""
    atual = os.environ.get('VLADO_AMBIENTE', '').strip() or None
    manifesto = next((m for m in membros if m.name == MANIFESTO and m.isfile()), None)
    try:
        origem = json.loads(pacote.extractfile(manifesto).read()).get('ambiente') if manifesto else None
    except (ValueError, AttributeError):
        origem = None
    if origem and atual and origem != atual and not outro_ambiente:
        raise ValueError(f'Este backup é do ambiente {origem!r} e o destino é {atual!r}. Nada foi restaurado; '
                         'use --outro-ambiente só se a troca for intencional.')


def _restaurar_pacote(root: Path, pacote: tarfile.TarFile, substituir: bool, outro_ambiente: bool = False) -> list[str]:
    """Extract into a staging folder, then swap the CONTENT of each data folder; any failure restores the previous data.

    The data folders themselves are never renamed or removed: in Docker they are volume mount points
    (renaming one fails with "device busy"), and a new, empty volume must simply receive the files."""
    membros = pacote.getmembers()
    for membro in membros:
        _conferir(membro)
    _conferir_ambiente(pacote, membros, outro_ambiente)
    _verificar_manifesto(pacote, membros)
    pastas = sorted({PurePosixPath(m.name).parts[0] for m in membros if m.name != MANIFESTO})
    ocupadas = [p for p in pastas if (root / p).exists() and any((root / p).iterdir())]
    if ocupadas and not substituir:
        raise ValueError(f'O destino já contém dados em {", ".join(ocupadas)}. Use --substituir para trocar por este backup.')
    root.mkdir(parents=True, exist_ok=True)
    marca = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    # Staging and the previous content both live INSIDE each data folder (same volume, and the
    # application root may be read-only in the container): moves are cheap renames.
    pastas_info = []  # (data folder, staging, holding folder, created by this restore)
    try:
        for pasta in pastas:
            destino = root / pasta
            criada = not destino.exists()
            destino.mkdir(parents=True, exist_ok=True)
            pastas_info.append((destino, destino / f'.restaurando-{marca}', destino / f'.antiga-{marca}', criada))
        for destino, preparo, _, _ in pastas_info:
            preparo.mkdir()
            nome = destino.name
            _extrair(pacote, [m for m in membros if m.name != MANIFESTO and PurePosixPath(m.name).parts[0] == nome],
                     preparo, raiz=nome)
        trocadas = []
        try:
            for destino, preparo, guarda, _ in pastas_info:
                guarda.mkdir()
                trocadas.append((destino, preparo, guarda))
                for item in list(destino.iterdir()):
                    if item not in (guarda, preparo):
                        shutil.move(str(item), str(guarda / item.name))
                for item in list(preparo.iterdir()):
                    shutil.move(str(item), str(destino / item.name))
        except BaseException:
            for destino, preparo, guarda in reversed(trocadas):
                for item in list(destino.iterdir()):
                    if item not in (guarda, preparo):
                        shutil.rmtree(item) if item.is_dir() and not item.is_symlink() else item.unlink()
                for item in list(guarda.iterdir()):
                    shutil.move(str(item), str(destino / item.name))
                guarda.rmdir()
            raise
    except BaseException:
        for destino, preparo, _, criada in pastas_info:
            shutil.rmtree(preparo, ignore_errors=True)
            if criada and destino.exists() and not any(destino.iterdir()):
                destino.rmdir()
        raise
    for _, preparo, guarda, _ in pastas_info:
        shutil.rmtree(preparo, ignore_errors=True)
        shutil.rmtree(guarda, ignore_errors=True)
    if 'acesso' in pastas:
        _encerrar_sessoes_restauradas(root / 'acesso' / 'acesso.json')
    return pastas


def _ler_manifesto(pacote: tarfile.TarFile, membros) -> dict | None:
    membro = next((m for m in membros if m.name == MANIFESTO and m.isfile()), None)
    if membro is None:
        return None
    try:
        dados = json.loads(pacote.extractfile(membro).read())
    except (ValueError, AttributeError):
        return None
    return dados if isinstance(dados, dict) else None


def _verificar_manifesto(pacote: tarfile.TarFile, membros) -> dict | None:
    """Backups with a file manifest (version 2) are checked before anything is written: every file must be
    there, with the recorded SHA-256, and nothing extra. Older backups have no hashes and are accepted."""
    manifesto = _ler_manifesto(pacote, membros)
    if not manifesto or not isinstance(manifesto.get('arquivos'), dict):
        return manifesto
    esperados = manifesto['arquivos']
    presentes = {m.name: m for m in membros if m.isfile() and m.name != MANIFESTO}
    faltando = sorted(set(esperados) - set(presentes))
    sobrando = sorted(set(presentes) - set(esperados))
    if faltando or sobrando:
        raise ValueError(f'Backup incompleto ou adulterado: {len(faltando)} arquivo(s) faltando, {len(sobrando)} fora do '
                         'manifesto. Nada foi restaurado.')
    for nome, membro in presentes.items():
        resumo = hashlib.sha256()
        with pacote.extractfile(membro) as stream:
            for bloco in iter(lambda: stream.read(1 << 20), b''):
                resumo.update(bloco)
        if resumo.hexdigest() != esperados[nome].get('sha256'):
            raise ValueError(f'Backup corrompido: o hash de {nome!r} não confere. Nada foi restaurado.')
    return manifesto


def restaurar(root: Path, arquivo, substituir: bool = False, outro_ambiente: bool = False,
              identidade: Path | None = None, trabalho: Path | None = None) -> list[str]:
    root = Path(root)
    if arquivo == '-':
        with tarfile.open(fileobj=io.BytesIO(sys.stdin.buffer.read()), mode='r:gz') as pacote:
            return _restaurar_pacote(root, pacote, substituir, outro_ambiente)
    arquivo = Path(arquivo)
    if arquivo.name.endswith('.age'):
        with _aberto_decifrado(arquivo, identidade, trabalho) as pacote:
            return _restaurar_pacote(root, pacote, substituir, outro_ambiente)
    with tarfile.open(arquivo, 'r:gz') as pacote:
        return _restaurar_pacote(root, pacote, substituir, outro_ambiente)


class _aberto_decifrado:
    """Context manager: decrypts an .age backup into a private temporary file, opens it as a tar, and removes
    the plaintext on exit."""

    def __init__(self, arquivo: Path, identidade: Path | None, trabalho: Path | None):
        if identidade is None:
            raise ValueError('Backup cifrado: informe a chave privada com --identidade (ou '
                             'VLADO_BACKUP_IDENTIDADE_ARQUIVO). Ela não fica no servidor.')
        self.arquivo, self.identidade, self.trabalho = Path(arquivo), Path(identidade), trabalho

    def __enter__(self) -> tarfile.TarFile:
        if self.trabalho:
            Path(self.trabalho).mkdir(parents=True, exist_ok=True)
        self.pasta = Path(tempfile.mkdtemp(prefix='vlado-restauracao-', dir=self.trabalho))
        os.chmod(self.pasta, 0o700)
        self.plano = self.pasta / 'dados.tar.gz'
        _decifrar(self.arquivo, self.identidade, self.plano)
        self.pacote = tarfile.open(self.plano, 'r:gz')
        return self.pacote

    def __exit__(self, *_):
        try:
            self.pacote.close()
        finally:
            shutil.rmtree(self.pasta, ignore_errors=True)


# --- scheduled service ------------------------------------------------------------------------------------


def _parse_retencao(texto: str | None) -> dict:
    """`diarios=7,semanais=4,mensais=6`: every backup of the last N days, plus the newest of each of the last N
    weeks and N months. The newest backup is always kept."""
    valores = {'diarios': 7, 'semanais': 4, 'mensais': 6}
    for parte in (texto or RETENCAO_PADRAO).split(','):
        if not parte.strip():
            continue
        chave, _, numero = parte.partition('=')
        chave = chave.strip()
        if chave not in valores or not numero.strip().isdigit():
            raise ValueError(f'Retenção inválida ({parte.strip()!r}); use {RETENCAO_PADRAO}.')
        valores[chave] = int(numero)
    if valores['diarios'] < 1:
        raise ValueError('Retenção inválida: diarios precisa ser pelo menos 1.')
    return valores


def selecionar_descartes(itens: list[tuple[str, datetime]], agora: datetime, retencao: dict) -> list[str]:
    """Names to delete. Pure function: same inputs, same answer; never returns the newest item."""
    if not itens:
        return []
    ordenados = sorted(itens, key=lambda i: i[1], reverse=True)
    manter = {ordenados[0][0]}
    semanas, meses = set(), set()
    for nome, data in ordenados:  # newest first, so the first of each week/month is its newest
        idade = agora - data
        if idade < timedelta(days=retencao['diarios']):
            manter.add(nome)
        semana = data.isocalendar()[:2]
        if idade <= timedelta(days=7 * retencao['semanais']) and semana not in semanas:
            semanas.add(semana)
            manter.add(nome)
        mes = (data.year, data.month)
        if idade <= timedelta(days=31 * retencao['mensais']) and mes not in meses:
            meses.add(mes)
            manter.add(nome)
    return [nome for nome, _ in ordenados if nome not in manter]


def _data_do_nome(nome: str, ambiente: str) -> datetime | None:
    achado = re.fullmatch(re.escape(f'{PREFIXO}-{ambiente}-') + r'(\d{8}T\d{12})Z' + re.escape(SUFIXO_CIFRADO), nome)
    if not achado:
        return None
    return datetime.strptime(achado[1], '%Y%m%dT%H%M%S%f').replace(tzinfo=timezone.utc)


def _configuracao(env=None) -> dict:
    env = os.environ if env is None else env

    def numero(nome, padrao):
        valor = env.get(nome, '').strip()
        if not valor:
            return padrao
        try:
            return float(valor)
        except ValueError:
            raise ValueError(f'{nome} precisa ser um número.') from None

    horario = env.get('VLADO_BACKUP_HORARIO_UTC', '06:30').strip() or '06:30'
    if not re.fullmatch(r'([01]\d|2[0-3]):[0-5]\d', horario):
        raise ValueError('VLADO_BACKUP_HORARIO_UTC precisa estar no formato HH:MM (UTC).')
    arquivo_chaves = env.get('VLADO_BACKUP_DESTINATARIOS_ARQUIVO', '').strip()
    return {
        'destino': env.get('VLADO_BACKUP_DESTINO', '').strip(),
        'destinatarios_bruto': env.get('VLADO_BACKUP_DESTINATARIOS', '').strip() or arquivo_chaves,
        'ambiente': env.get('VLADO_AMBIENTE', '').strip() or 'sem-ambiente',
        'horario': horario,
        'retencao': _parse_retencao(env.get('VLADO_BACKUP_RETENCAO')),
        'incluir_segredos': env.get('VLADO_BACKUP_INCLUIR_SEGREDOS', '0').strip() == '1',
        'espera': numero('VLADO_BACKUP_ESPERA_S', 900.0),
        'trabalho': Path(env.get('VLADO_BACKUP_TRABALHO', '/trabalho')),
        'ping': env.get('VLADO_BACKUP_PING_URL', '').strip(),
        'ao_iniciar': env.get('VLADO_BACKUP_AO_INICIAR', '0').strip() == '1',
        'idade_maxima_h': numero('VLADO_BACKUP_IDADE_MAX_H', 30.0),
        'repetir_min': numero('VLADO_BACKUP_REPETIR_MIN', 60.0),
    }


def _problemas(cfg: dict) -> list[str]:
    problemas = []
    if not cfg['destino']:
        problemas.append('VLADO_BACKUP_DESTINO não definido (destino fora do servidor).')
    try:
        if not _destinatarios(cfg['destinatarios_bruto']):
            problemas.append('VLADO_BACKUP_DESTINATARIOS não definido (chave pública age do dono).')
    except ValueError as exc:
        problemas.append(str(exc))
    return problemas


def _log(mensagem: str) -> None:
    print(f'{_agora().strftime("%Y-%m-%dT%H:%M:%SZ")} backup: {mensagem}', flush=True)


def _estado_caminho(cfg: dict) -> Path:
    return cfg['trabalho'] / 'estado.json'


def _ler_estado(cfg: dict) -> dict:
    try:
        return json.loads(_estado_caminho(cfg).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def _gravar_estado(cfg: dict, **campos) -> dict:
    estado = _ler_estado(cfg)
    estado.update(campos)
    caminho = _estado_caminho(cfg)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_suffix('.tmp')
    temporario.write_text(json.dumps(estado, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    os.replace(temporario, caminho)
    return estado


def _rclone(argumentos: list[str], timeout: int = 6 * 3600) -> subprocess.CompletedProcess:
    exe = shutil.which('rclone')
    if not exe:
        raise ValueError('O programa `rclone` não está instalado aqui; use a imagem de backup do Compose.')
    processo = subprocess.run([exe, '--retries', '3', '--low-level-retries', '5', *argumentos],
                              capture_output=True, timeout=timeout)
    if processo.returncode != 0:
        raise ValueError('rclone falhou: ' + processo.stderr.decode('utf-8', 'replace').strip()[-300:])
    return processo


def _remoto(destino: str, nome: str = '') -> str:
    base = destino.rstrip('/')
    if base.endswith(':'):
        return base + nome
    return f'{base}/{nome}' if nome else base


def _listar_remoto(destino: str, ambiente: str) -> list[tuple[str, datetime, int]]:
    saida = _rclone(['lsjson', '--files-only', _remoto(destino)]).stdout
    itens = []
    for entrada in json.loads(saida or b'[]'):
        data = _data_do_nome(entrada['Name'], ambiente)
        if data is not None:
            itens.append((entrada['Name'], data, int(entrada.get('Size', -1))))
    return sorted(itens, key=lambda i: i[1])


def _enviar(destino: str, arquivo: Path) -> None:
    _rclone(['copyto', str(arquivo), _remoto(destino, arquivo.name)])
    saida = _rclone(['lsjson', '--files-only', '--include', arquivo.name, _remoto(destino)]).stdout
    achados = [e for e in json.loads(saida or b'[]') if e['Name'] == arquivo.name]
    if len(achados) != 1 or int(achados[0].get('Size', -1)) != arquivo.stat().st_size:
        raise ValueError('O arquivo enviado não confere com o local (tamanho diferente ou ausente no destino).')


def _aplicar_retencao(cfg: dict, enviado: str) -> list[str]:
    itens = _listar_remoto(cfg['destino'], cfg['ambiente'])
    descartes = selecionar_descartes([(n, d) for n, d, _ in itens], _agora(), cfg['retencao'])
    descartes = [n for n in descartes if n != enviado]
    for nome in descartes:
        _rclone(['deletefile', _remoto(cfg['destino'], nome)])
    return descartes


def _avisar(cfg: dict, sucesso: bool) -> None:
    if not cfg['ping']:
        return
    url = cfg['ping'] if sucesso else cfg['ping'].rstrip('/') + '/fail'
    try:
        urllib.request.urlopen(urllib.request.Request(url, method='GET'), timeout=10).read(64)
    except Exception as exc:  # noqa: BLE001 - a missing alert must not fail the backup
        _log(f'aviso de monitoramento não enviado ({type(exc).__name__}).')


def rodada(cfg: dict, root: Path | None = None) -> dict:
    """One scheduled backup: snapshot, encrypt, upload, verify, prune. Raises on any failure (the file is not
    kept as a good backup unless the upload was confirmed)."""
    root = Path(root or ROOT)
    problemas = _problemas(cfg)
    if problemas:
        raise ValueError(' '.join(problemas))
    destinatarios = _destinatarios(cfg['destinatarios_bruto'])
    spool, tmp = cfg['trabalho'] / 'spool', cfg['trabalho'] / 'tmp'
    for pasta in (spool, tmp):  # leftovers of an interrupted run
        shutil.rmtree(pasta, ignore_errors=True)
        pasta.mkdir(parents=True, mode=0o700, exist_ok=True)
    nome = _nome(cfg['ambiente'], True)
    inicio = time.monotonic()
    arquivo, manifesto = _gravar_arquivo(root, spool, nome, cfg['incluir_segredos'], destinatarios, tmp, cfg['espera'])
    try:
        tamanho = arquivo.stat().st_size
        _enviar(cfg['destino'], arquivo)
    finally:
        arquivo.unlink(missing_ok=True)
        shutil.rmtree(tmp, ignore_errors=True)
    aviso_retencao = None
    try:
        descartados = _aplicar_retencao(cfg, nome)
    except ValueError as exc:
        descartados, aviso_retencao = [], str(exc)
    resultado = {'arquivo': nome, 'bytes': tamanho, 'arquivos_no_backup': len(manifesto['arquivos']),
                 'segredos_incluidos': manifesto['segredos_incluidos'], 'descartados': descartados,
                 'avisos': manifesto['avisos'] + ([aviso_retencao] if aviso_retencao else []),
                 'mudancas_apos_a_leitura': manifesto['mudancas_apos_a_leitura'],
                 'duracao_s': round(time.monotonic() - inicio, 1)}
    return resultado


def _executar_rodada(cfg: dict) -> bool:
    _gravar_estado(cfg, ultima_tentativa_utc=_agora().isoformat(timespec='seconds'))
    try:
        resultado = rodada(cfg)
    except (ValueError, OSError, tarfile.TarError, subprocess.SubprocessError) as exc:
        _gravar_estado(cfg, erro=str(exc)[:400])
        _log(f'FALHOU: {str(exc)[:400]}')
        _avisar(cfg, False)
        return False
    _gravar_estado(cfg, erro=None, ultimo_sucesso_utc=_agora().isoformat(timespec='seconds'), ultimo=resultado)
    _log(f'ok: {resultado["arquivo"]} ({resultado["bytes"]} bytes, {resultado["arquivos_no_backup"]} arquivos, '
         f'{len(resultado["descartados"])} descartado(s) pela retenção, {len(resultado["avisos"])} aviso(s))')
    _avisar(cfg, True)
    return True


def _proxima(agora: datetime, horario: str) -> datetime:
    hora, minuto = (int(x) for x in horario.split(':'))
    alvo = agora.replace(hour=hora, minute=minuto, second=0, microsecond=0)
    return alvo if alvo > agora else alvo + timedelta(days=1)


def agendado(cfg: dict) -> int:
    parar = []
    for sinal in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sinal, lambda *_: parar.append(True))
    _gravar_estado(cfg, iniciado_em_utc=_agora().isoformat(timespec='seconds'), horario_utc=cfg['horario'],
                   retencao=cfg['retencao'], destino_configurado=bool(cfg['destino']))
    problemas = _problemas(cfg)
    if problemas:
        _gravar_estado(cfg, erro='backup NÃO configurado: ' + ' '.join(problemas))
        _log('NÃO CONFIGURADO: ' + ' '.join(problemas) + ' Nenhum backup será feito até corrigir.')
        while not parar:
            time.sleep(1)
        return 0
    _log(f'agendado para {cfg["horario"]} UTC; destino fora do servidor configurado; retenção {cfg["retencao"]}.')
    proxima = _agora() if cfg['ao_iniciar'] else _proxima(_agora(), cfg['horario'])
    while not parar:
        if _agora() >= proxima:
            if _executar_rodada(cfg):
                proxima = _proxima(_agora(), cfg['horario'])
            else:
                proxima = _agora() + timedelta(minutes=cfg['repetir_min'])
        time.sleep(1)
    _log('encerrado.')
    return 0


def saude(cfg: dict) -> int:
    estado = _ler_estado(cfg)
    if estado.get('destino_configurado') is False or (estado.get('erro') or '').startswith('backup NÃO configurado'):
        print(estado.get('erro') or 'backup não configurado')
        return 1
    limite = timedelta(hours=cfg['idade_maxima_h'])
    referencia = estado.get('ultimo_sucesso_utc') or estado.get('iniciado_em_utc')
    if not referencia:
        print('sem estado do backup')
        return 1
    idade = _agora() - datetime.fromisoformat(referencia)
    if idade > limite:
        print(f'último backup bem-sucedido há mais de {cfg["idade_maxima_h"]:g} h ({referencia})')
        return 1
    print('ok' + (f' (último sucesso {referencia})' if estado.get('ultimo_sucesso_utc') else ' (aguardando o primeiro)'))
    return 0


def _resolver_origem(cfg: dict, valor: str | None, do_destino: str | None, pasta: Path) -> Path:
    """A local backup file, or one downloaded from the destination (`ultimo` or a file name)."""
    if valor:
        return Path(valor)
    if not do_destino:
        raise ValueError('Informe o arquivo do backup ou --do-destino ultimo|NOME.')
    if not cfg['destino']:
        raise ValueError('VLADO_BACKUP_DESTINO não definido; não sei onde buscar o backup.')
    nome = do_destino
    if do_destino == 'ultimo':
        itens = _listar_remoto(cfg['destino'], cfg['ambiente'])
        if not itens:
            raise ValueError('Nenhum backup deste ambiente no destino.')
        nome = itens[-1][0]
    elif '/' in nome or '\\' in nome or _data_do_nome(nome, cfg['ambiente']) is None:
        raise ValueError(f'Nome de backup inválido para o ambiente {cfg["ambiente"]!r}: {nome!r}.')
    pasta.mkdir(parents=True, exist_ok=True)
    local = pasta / nome
    _rclone(['copyto', _remoto(cfg['destino'], nome), str(local)])
    _log(f'baixado {nome} ({local.stat().st_size} bytes)')
    return local


def _identidade(args) -> tuple[Path | None, Path | None]:
    """(identity file, temp file to delete). Path from --identidade or VLADO_BACKUP_IDENTIDADE_ARQUIVO; or the key
    text from the environment variable named by --identidade-env (written to a private temp file)."""
    if getattr(args, 'identidade_env', None):
        texto = os.environ.get(args.identidade_env, '')
        if not texto.strip():
            raise ValueError(f'A variável {args.identidade_env} está vazia.')
        descritor, nome = tempfile.mkstemp(prefix='identidade-')
        with os.fdopen(descritor, 'w', encoding='utf-8') as saida:
            saida.write(texto.strip() + '\n')
        return Path(nome), Path(nome)
    caminho = getattr(args, 'identidade', None) or os.environ.get('VLADO_BACKUP_IDENTIDADE_ARQUIVO')
    if caminho and not Path(caminho).is_file():
        raise ValueError('Arquivo de chave privada não encontrado.')
    return (Path(caminho) if caminho else None), None


def verificar(origem: Path, identidade: Path | None, trabalho: Path | None = None) -> dict:
    """Decrypt (if needed) and check every hash of a backup without writing any data folder."""
    if str(origem).endswith('.age'):
        with _aberto_decifrado(origem, identidade, trabalho) as pacote:
            membros = pacote.getmembers()
            for membro in membros:
                _conferir(membro)
            return _resumo(_verificar_manifesto(pacote, membros), membros)
    with tarfile.open(origem, 'r:gz') as pacote:
        membros = pacote.getmembers()
        for membro in membros:
            _conferir(membro)
        return _resumo(_verificar_manifesto(pacote, membros), membros)


def _resumo(manifesto: dict | None, membros) -> dict:
    return {'arquivos': sum(1 for m in membros if m.isfile() and m.name != MANIFESTO),
            'criado_em_utc': (manifesto or {}).get('criado_em_utc'), 'ambiente': (manifesto or {}).get('ambiente'),
            'pastas': (manifesto or {}).get('pastas'), 'segredos_incluidos': (manifesto or {}).get('segredos_incluidos'),
            'hashes_conferidos': bool(manifesto and isinstance(manifesto.get('arquivos'), dict))}


def _principal() -> int:
    parser = argparse.ArgumentParser(description='Backup dos dados da Mesa de apuração.')
    sub = parser.add_subparsers(dest='comando', required=True)
    cria = sub.add_parser('criar')
    cria.add_argument('--destino', required=True, help='Pasta de destino, ou - para enviar o arquivo à saída padrão')
    cria.add_argument('--incluir-segredos', action='store_true', help='Inclui as chaves de API salvas')
    cria.add_argument('--cifrar-para', help='Chave(s) pública(s) age1... ou arquivo delas: grava .tar.gz.age')
    restaura = sub.add_parser('restaurar')
    restaura.add_argument('arquivo', nargs='?', help='Arquivo .tar.gz ou .tar.gz.age, ou - para ler da entrada padrão')
    restaura.add_argument('--do-destino', help='Baixa do destino configurado: ultimo ou o nome do arquivo')
    restaura.add_argument('--substituir', action='store_true', help='Troca os dados atuais pelos do backup')
    restaura.add_argument('--outro-ambiente', action='store_true',
                          help='Aceita backup de outro VLADO_AMBIENTE (ex.: ensaio de restauração)')
    verifica = sub.add_parser('verificar', help='Decifra e confere os hashes sem restaurar')
    verifica.add_argument('arquivo', nargs='?')
    verifica.add_argument('--do-destino')
    for subparser in (restaura, verifica):
        subparser.add_argument('--identidade', help='Arquivo da chave PRIVADA age (fora do servidor)')
        subparser.add_argument('--identidade-env', help='Nome da variável de ambiente com o texto da chave privada')
    for nome in ('rodada', 'agendado', 'listar', 'saude'):
        sub.add_parser(nome)
    args = parser.parse_args()
    if args.comando == 'criar':
        destinatarios = _destinatarios(args.cifrar_para)
        if args.destino == '-':
            if destinatarios:
                raise ValueError('--cifrar-para não vale com --destino -; grave em uma pasta.')
            with tarfile.open(fileobj=sys.stdout.buffer, mode='w|gz') as pacote:
                _gravar(ROOT, pacote, args.incluir_segredos)
        else:
            if not destinatarios:
                print('Aviso: backup SEM cifra. Guarde-o cifrado e fora do servidor (--cifrar-para).', file=sys.stderr)
            print(criar(ROOT, Path(args.destino), args.incluir_segredos, destinatarios))
        return 0
    cfg = _configuracao()
    if args.comando == 'agendado':
        return agendado(cfg)
    if args.comando == 'saude':
        return saude(cfg)
    if args.comando == 'rodada':
        return 0 if _executar_rodada(cfg) else 1
    if args.comando == 'listar':
        for nome, data, tamanho in _listar_remoto(cfg['destino'], cfg['ambiente']):
            print(f'{nome}\t{tamanho}')
        return 0
    identidade, apagar = _identidade(args)
    origem = None
    try:
        if args.arquivo == '-' and args.comando == 'restaurar':
            origem = '-'
        else:
            origem = _resolver_origem(cfg, args.arquivo, args.do_destino, cfg['trabalho'] / 'baixado')
        if args.comando == 'verificar':
            print(json.dumps(verificar(Path(origem), identidade, cfg['trabalho'] / 'tmp'), ensure_ascii=False, indent=2))
        else:
            print('Restaurado:', ', '.join(restaurar(ROOT, origem, args.substituir, args.outro_ambiente, identidade,
                                                   cfg['trabalho'] / 'tmp')), file=sys.stderr)
    finally:
        if apagar:
            apagar.unlink(missing_ok=True)
        if origem != '-' and args.do_destino:
            shutil.rmtree(cfg['trabalho'] / 'baixado', ignore_errors=True)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(_principal())
    except (ValueError, OSError, tarfile.TarError, subprocess.SubprocessError) as exc:
        print(f'Erro: {exc}', file=sys.stderr)
        raise SystemExit(1)
