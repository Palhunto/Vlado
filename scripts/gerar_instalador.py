"""Build Vlado-Setup.exe (Windows, per-user installer) reproducibly.

Steps: download the pinned dependencies of instalador/dependencias.json (SHA-256 checked, cached in
.ferramentas/downloads), extract Tesseract and Ghostscript from their NSIS installers with 7-Zip
(never running them), assemble the payload and the license notices, freeze scripts/vlado_lancador.py
with PyInstaller (instalador/vlado.spec, --noconsole) and compile instalador/vlado.iss with Inno Setup.
Verify TLS initialization in the frozen executable before compiling. Every child process runs without a console window.

  .venv\\Scripts\\python.exe scripts/gerar_instalador.py
Output: dist/Vlado-Setup.exe and dist/Vlado-Setup.exe.sha256
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request

RAIZ = Path(__file__).resolve().parents[1]
DEPENDENCIAS = RAIZ / 'instalador' / 'dependencias.json'
FERRAMENTAS = RAIZ / '.ferramentas'
DOWNLOADS = FERRAMENTAS / 'downloads'
BUILD = RAIZ / 'build' / 'instalador'
PAYLOAD = BUILD / 'payload'
SAIDA = RAIZ / 'dist'
SEM_JANELA = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0


def sha256(caminho: Path) -> str:
    digest = hashlib.sha256()
    with caminho.open('rb') as fluxo:
        for bloco in iter(lambda: fluxo.read(1024 * 1024), b''):
            digest.update(bloco)
    return digest.hexdigest()


def executar(args: list, **opcoes) -> str:
    processo = subprocess.run([str(a) for a in args], capture_output=True, creationflags=SEM_JANELA, check=False,
                              **opcoes)
    saida = (processo.stdout or b'').decode('utf-8', 'replace') + (processo.stderr or b'').decode('utf-8', 'replace')
    if processo.returncode != 0:
        raise SystemExit(f'Falhou ({processo.returncode}): {" ".join(map(str, args))}\n{saida[-4000:]}')
    return saida


def baixar(item: dict) -> Path:
    destino = DOWNLOADS / item['url'].rsplit('/', 1)[1]
    if destino.is_file() and sha256(destino) == item['sha256']:
        return destino
    DOWNLOADS.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_suffix(destino.suffix + '.parcial')
    print(f'Baixando {item["url"]}', flush=True)
    with urllib.request.urlopen(item['url'], timeout=300) as resposta, temporario.open('wb') as arquivo:
        shutil.copyfileobj(resposta, arquivo)
    obtido = sha256(temporario)
    if obtido != item['sha256']:
        temporario.unlink()
        raise SystemExit(f'SHA-256 divergente para {item["url"]}: {obtido} (esperado {item["sha256"]})')
    temporario.replace(destino)
    return destino


def sete_zip(deps: dict) -> Path:
    """7zr.exe opens the full 7-Zip package; only the full 7z.exe extracts NSIS installers."""
    pasta = FERRAMENTAS / '7zip'
    exe = pasta / '7z.exe'
    if not exe.is_file():
        zr = baixar(deps['7zr'])
        pacote = baixar(deps['7zip'])
        executar([zr, 'x', '-y', f'-o{pasta}', pacote])
    return exe


def extrair(sete: Path, instalador: Path, destino: Path) -> Path:
    if destino.exists():
        shutil.rmtree(destino)
    executar([sete, 'x', '-y', f'-o{destino}', instalador])
    return destino


def _copiar_licencas(origem: Path, destino: Path) -> None:
    destino.mkdir(parents=True, exist_ok=True)
    for arquivo in origem.rglob('*'):
        nome = arquivo.name.upper()
        if arquivo.is_file() and (nome.startswith(('LICENSE', 'COPYING')) or nome in ('NOTICE', 'NOTICE.TXT')):
            shutil.copy2(arquivo, destino / (arquivo.parent.name + '_' + arquivo.name))


def montar_tesseract(deps: dict, sete: Path) -> None:
    bruto = extrair(sete, baixar(deps['tesseract']), BUILD / 'extraido' / 'tesseract')
    alvo = PAYLOAD / 'tesseract'
    shutil.rmtree(alvo, ignore_errors=True)
    (alvo / 'tessdata').mkdir(parents=True)
    shutil.copy2(bruto / 'tesseract.exe', alvo)
    for dll in bruto.glob('*.dll'):
        shutil.copy2(dll, alvo)
    for sub in ('configs', 'tessconfigs'):
        if (bruto / 'tessdata' / sub).is_dir():
            shutil.copytree(bruto / 'tessdata' / sub, alvo / 'tessdata' / sub)
    if (bruto / 'tessdata' / 'pdf.ttf').is_file():
        shutil.copy2(bruto / 'tessdata' / 'pdf.ttf', alvo / 'tessdata')
    for idioma in ('por', 'eng', 'osd'):
        shutil.copy2(baixar(deps[f'tessdata_{idioma}']), alvo / 'tessdata' / f'{idioma}.traineddata')
    _copiar_licencas(bruto, PAYLOAD / 'licencas' / 'tesseract')


def montar_ghostscript(deps: dict, sete: Path) -> None:
    bruto = extrair(sete, baixar(deps['ghostscript']), BUILD / 'extraido' / 'ghostscript')
    alvo = PAYLOAD / 'ghostscript'
    shutil.rmtree(alvo, ignore_errors=True)
    (alvo / 'bin').mkdir(parents=True)
    for nome in ('gswin64c.exe', 'gsdll64.dll'):
        shutil.copy2(bruto / 'bin' / nome, alvo / 'bin')
    licencas = PAYLOAD / 'licencas' / 'ghostscript'
    _copiar_licencas(bruto, licencas)
    item = deps['ghostscript']
    (licencas / 'CODIGO_FONTE.txt').write_text(
        f'Ghostscript {item["versao"]} - GNU Affero General Public License v3 (AGPL-3.0)\n'
        f'Distribuído sem modificação, como programa externo usado pelo OCRmyPDF.\n'
        f'Código-fonte correspondente: {item["codigo_fonte"]}\n'
        f'Binário original: {item["url"]} (SHA-256 {item["sha256"]})\n'
        'Texto completo da licença: arquivos LICENSE/COPYING nesta pasta e https://www.gnu.org/licenses/agpl-3.0.html\n',
        encoding='utf-8')


def montar_avisos() -> None:
    destino = PAYLOAD / 'licencas'
    destino.mkdir(parents=True, exist_ok=True)
    texto = (RAIZ / 'docs' / 'AVISOS_DE_LICENCA.md').read_text(encoding='utf-8')
    (destino / 'AVISOS_DE_LICENCA.txt').write_text(texto, encoding='utf-8-sig')


def icone() -> None:
    from PIL import Image
    BUILD.mkdir(parents=True, exist_ok=True)
    imagem = Image.open(RAIZ / 'interface' / 'icones' / 'vlado-512.png').convert('RGBA')
    imagem.save(BUILD / 'vlado.ico', sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


def pyinstaller(deps: dict) -> None:
    import PyInstaller
    esperado = deps['python']['pyinstaller']
    if PyInstaller.__version__ != esperado:
        raise SystemExit(f'PyInstaller {PyInstaller.__version__} instalado; use {esperado} (pip install pyinstaller=={esperado}).')
    print('Congelando Vlado.exe (PyInstaller)…', flush=True)
    executar([sys.executable, '-m', 'PyInstaller', RAIZ / 'instalador' / 'vlado.spec', '--noconfirm', '--clean',
              '--distpath', BUILD / 'pyinstaller', '--workpath', BUILD / 'trabalho'], cwd=RAIZ)


def iscc(deps: dict) -> Path:
    pasta = FERRAMENTAS / 'innosetup'
    exe = pasta / 'ISCC.exe'
    if not exe.is_file():
        instalador = baixar(deps['innosetup'])
        executar([instalador, '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', '/CURRENTUSER',
                  '/NOICONS', f'/DIR={pasta}', '/TASKS='])
    return exe


def compilar(deps: dict, versao: str) -> Path:
    print('Compilando Vlado-Setup.exe (Inno Setup)…', flush=True)
    executar([iscc(deps), '/Q', f'/DVersao={versao}', f'/DOrigem={BUILD}', RAIZ / 'instalador' / 'vlado.iss'])
    gerado = BUILD / 'saida' / 'Vlado-Setup.exe'
    SAIDA.mkdir(exist_ok=True)
    final = SAIDA / 'Vlado-Setup.exe'
    shutil.copy2(gerado, final)
    digest = sha256(final)
    (SAIDA / 'Vlado-Setup.exe.sha256').write_text(f'{digest} *Vlado-Setup.exe\n', encoding='ascii')
    return final


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--pular-pyinstaller', action='store_true', help='Reusa build/instalador/pyinstaller')
    args = parser.parse_args()
    config = json.loads(DEPENDENCIAS.read_text(encoding='utf-8'))
    deps = {**config['downloads'], 'python': config['python']}
    sete = sete_zip(deps)
    montar_avisos()
    montar_tesseract(deps, sete)
    montar_ghostscript(deps, sete)
    icone()
    if not args.pular_pyinstaller:
        pyinstaller(deps)
    print('Verificando clientes HTTPS no Vlado.exe (1: OpenAI, 2: Anthropic)…', flush=True)
    pasta_executavel = BUILD / 'pyinstaller' / 'Vlado'
    executar([pasta_executavel / 'Vlado.exe', '--verificar-https'], cwd=pasta_executavel, timeout=60)
    final = compilar(deps, config['versao_vlado'])
    tamanho = final.stat().st_size
    print(json.dumps({'arquivo': str(final), 'bytes': tamanho, 'mb': round(tamanho / 1024 / 1024, 1),
                      'sha256': sha256(final)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
