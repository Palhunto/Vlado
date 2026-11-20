"""Clean, reproducible delivery ZIP.

Takes only files tracked by git at a commit (never the working tree), so credentials,
newsroom files, accounts, sessions, histories, local databases, logs and backups cannot
enter by accident; a deny list double-checks it. Optionally adds the signed classroom APK.
Same commit + same APK = byte-identical ZIP (fixed timestamps, order and permissions).

  python scripts/empacotar_entrega.py --commit HEAD --apk android/saidas/vlado-sala.apk --saida dist/
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DATA_FIXA = (1980, 1, 1, 0, 0, 0)
# Defence in depth: none of these may ever be packaged, even if tracked by mistake.
PROIBIDOS = [
    r'(^|/)\.env$', r'(^|/)\.env\.(?!example$)[^/]*$', r'^deploy/ambientes/[^/]+\.env$',
    r'^segredos/', r'^acesso/', r'^ajustes/', r'^conversas/', r'^lixeira/', r'^validacao/',
    r'^casos/(?!README\.md$|catalogo\.json$)', r'^execucoes/(?!README\.md$)', r'^entrada/(?!README\.md$)',
    r'\.(sqlite3?|db|sqlite-wal|sqlite-shm|log|pem|key|p12|jks|keystore|tar\.gz|bak)$',
    r'(^|/)keystore\.properties$', r'^android/saidas/', r'^\.ferramentas/', r'^\.worktrees/',
    r'^docs/(qa|entregas|auditorias)', r'(^|/)__pycache__/',
    r'^referencia_original/', r'^transferencia/', r'^distribuicao/', r'^\.claude-flow/', r'(^|/)backups?/',
    r'^manifesto_distribuicao\.json$', r'^docs/VLADO_HANDOFF\.md$', r'^docs/VLADO_GUIA_TECNICO_DEPLOY\.md$',
    r'\.jsonl$', r'^dist/',
    # Agent working folders, at any level and in any letter case.
    r'(?i)(^|/)\.(claude|maestri|codex|agents|cursor)/',
    # The evidence contracts stay: code and docs of the delivery cite them. The exception is the
    # .gitignore rule `!/.maestro/equipe/CONTRATO_*.md` (root only, any name without "/"), so a
    # contract git versions never makes the whole delivery refuse; other spellings are barred.
    r'^(?!\.maestro/equipe/CONTRATO_[^/]*\.md$)(?i:(.*/)?\.maestro/)',
]
# Windows launchers belong to the local single-user install, not to this delivery.
FORA_DA_ENTREGA = [r'^Abrir mesa\.vbs$', r'^Iniciar pesquisa\.cmd$', r'^Preparar notebook\.cmd$']


def _git(*args: str) -> bytes:
    return subprocess.run(['git', '-C', str(ROOT), *args], check=True, capture_output=True).stdout


def arquivos(commit: str) -> list[str]:
    nomes = _git('ls-tree', '-r', '-z', '--name-only', commit).decode('utf-8').split('\0')
    return sorted(n for n in nomes if n and not any(re.search(p, n) for p in FORA_DA_ENTREGA))


def _ler_blobs(sha: str, nomes: list[str]) -> dict[str, bytes]:
    """Read every blob in one `git cat-file --batch` process (one `git show` per file is slow on Windows)."""
    pedido = ''.join(f'{sha}:{n}\n' for n in nomes).encode('utf-8')
    saida = subprocess.run(['git', '-C', str(ROOT), 'cat-file', '--batch'], input=pedido,
                           check=True, capture_output=True).stdout
    conteudo, pos = {}, 0
    for nome in nomes:
        fim = saida.index(b'\n', pos)
        cabecalho = saida[pos:fim].split()
        if len(cabecalho) != 3 or cabecalho[1] != b'blob':
            raise SystemExit(f'Objeto inesperado no git para {nome}.')
        tamanho = int(cabecalho[2])
        conteudo[nome] = saida[fim + 1:fim + 1 + tamanho]
        pos = fim + 1 + tamanho + 1
    return conteudo


def proibidos(nomes: list[str]) -> list[str]:
    return [n for n in nomes if any(re.search(p, n) for p in PROIBIDOS)]


def _entrada(nome: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(nome, DATA_FIXA)
    info.external_attr = 0o644 << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    return info


def empacotar(commit: str, saida: Path, apk: Path | None = None) -> dict:
    sha = _git('rev-parse', commit).decode().strip()
    nomes = arquivos(sha)
    ruins = proibidos(nomes)
    if ruins:
        raise SystemExit('Arquivos proibidos rastreados pelo git: ' + ', '.join(ruins))
    raiz = PurePosixPath(f'vlado-{sha[:12]}')
    conteudo = _ler_blobs(sha, nomes)
    if json.loads(conteudo.get('casos/catalogo.json', b'{"casos": []}')).get('casos') != []:
        raise SystemExit('O catálogo versionado não está vazio: o pacote não pode levar casos.')
    if apk is not None:
        conteudo[f'apk/{apk.name}'] = apk.read_bytes()
    manifesto = {'commit': sha, 'arquivos': [{'caminho': n, 'bytes': len(b), 'sha256': hashlib.sha256(b).hexdigest()}
                                            for n, b in sorted(conteudo.items())]}
    conteudo['MANIFESTO.json'] = (json.dumps(manifesto, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    conteudo['SHA256SUMS'] = ''.join(f"{a['sha256']}  {a['caminho']}\n" for a in manifesto['arquivos']).encode('utf-8')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as zf:
        for nome in sorted(conteudo):
            zf.writestr(_entrada(str(raiz / nome)), conteudo[nome], compresslevel=9)
    saida.mkdir(parents=True, exist_ok=True)
    destino = saida / f'{raiz}.zip'
    destino.write_bytes(buffer.getvalue())
    digest = hashlib.sha256(buffer.getvalue()).hexdigest()
    (saida / f'{raiz}.zip.sha256').write_text(f'{digest}  {destino.name}\n', encoding='utf-8')
    return {'zip': str(destino), 'sha256': digest, 'arquivos': len(conteudo), 'commit': sha}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--commit', default='HEAD')
    parser.add_argument('--apk', type=Path)
    parser.add_argument('--saida', type=Path, default=ROOT / 'dist')
    args = parser.parse_args()
    if args.apk is not None and not args.apk.is_file():
        raise SystemExit(f'APK não encontrado: {args.apk}')
    print(json.dumps(empacotar(args.commit, args.saida, args.apk), ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
