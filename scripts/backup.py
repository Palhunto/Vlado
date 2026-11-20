"""Backup and restore of the Mesa's data folders (cases, conversations, rounds, access, settings).

Keys in segredos/ are left out unless --incluir-segredos is given: a pasted key can
be pasted again, and a backup file is easier to leak than a server volume.

  python scripts/backup.py criar --destino backups/
  python scripts/backup.py criar --destino -  > vlado-dados.tar.gz      (stream, e.g. from a container)
  python scripts/backup.py restaurar vlado-dados-AAAAMMDDTHHMMSSZ.tar.gz [--substituir]
  python scripts/backup.py restaurar - [--substituir] < vlado-dados.tar.gz
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
PASTAS = ('casos', 'conversas', 'execucoes', 'lixeira', 'entrada', 'acesso', 'ajustes')
SEGREDOS = 'segredos'
MANIFESTO = 'manifesto_backup.json'
PROIBIDOS = (chr(92), ':', chr(0))  # backslash (Windows separator), drive letter, NUL


def _pastas(incluir_segredos: bool) -> tuple[str, ...]:
    return PASTAS + ((SEGREDOS,) if incluir_segredos else ())


def _gravar(root: Path, pacote: tarfile.TarFile, incluir_segredos: bool) -> None:
    incluidas = [p for p in _pastas(incluir_segredos) if (root / p).is_dir()]
    for pasta in incluidas:
        pacote.add(root / pasta, arcname=pasta)
    manifesto = json.dumps({'criado_em_utc': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                            'pastas': incluidas, 'segredos_incluidos': incluir_segredos,
                            'ambiente': os.environ.get('VLADO_AMBIENTE', '').strip() or None}, indent=2).encode('utf-8')
    info = tarfile.TarInfo(MANIFESTO)
    info.size = len(manifesto)
    pacote.addfile(info, io.BytesIO(manifesto))


def criar(root: Path, destino: Path, incluir_segredos: bool = False) -> Path:
    destino = Path(destino)
    destino.mkdir(mode=0o700, parents=True, exist_ok=True)
    arquivo = destino / f'vlado-dados-{datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")}.tar.gz'
    # Reporting material and password hashes: owner-only from the first byte, whatever the umask.
    descritor = os.open(arquivo, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0), 0o600)
    with os.fdopen(descritor, 'wb') as saida, tarfile.open(fileobj=saida, mode='w:gz') as pacote:
        _gravar(Path(root), pacote, incluir_segredos)
    _restrito(arquivo)
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


def restaurar(root: Path, arquivo, substituir: bool = False, outro_ambiente: bool = False) -> list[str]:
    root = Path(root)
    if arquivo == '-':
        with tarfile.open(fileobj=io.BytesIO(sys.stdin.buffer.read()), mode='r:gz') as pacote:
            return _restaurar_pacote(root, pacote, substituir, outro_ambiente)
    with tarfile.open(arquivo, 'r:gz') as pacote:
        return _restaurar_pacote(root, pacote, substituir, outro_ambiente)


def _principal() -> int:
    parser = argparse.ArgumentParser(description='Backup dos dados da Mesa de apuração.')
    sub = parser.add_subparsers(dest='comando', required=True)
    cria = sub.add_parser('criar')
    cria.add_argument('--destino', required=True, help='Pasta de destino, ou - para enviar o arquivo à saída padrão')
    cria.add_argument('--incluir-segredos', action='store_true', help='Inclui as chaves de API salvas')
    restaura = sub.add_parser('restaurar')
    restaura.add_argument('arquivo', help='Arquivo .tar.gz, ou - para ler da entrada padrão')
    restaura.add_argument('--substituir', action='store_true', help='Troca os dados atuais pelos do backup')
    restaura.add_argument('--outro-ambiente', action='store_true',
                          help='Aceita backup de outro VLADO_AMBIENTE (ex.: ensaio de restauração)')
    args = parser.parse_args()
    if args.comando == 'criar':
        if args.destino == '-':
            with tarfile.open(fileobj=sys.stdout.buffer, mode='w|gz') as pacote:
                _gravar(ROOT, pacote, args.incluir_segredos)
        else:
            print(criar(ROOT, Path(args.destino), args.incluir_segredos))
    else:
        print('Restaurado:', ', '.join(restaurar(ROOT, args.arquivo, args.substituir, args.outro_ambiente)), file=sys.stderr)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(_principal())
    except (ValueError, OSError, tarfile.TarError) as exc:
        print(f'Erro: {exc}', file=sys.stderr)
        raise SystemExit(1)
