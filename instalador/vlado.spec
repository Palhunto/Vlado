# PyInstaller spec for Vlado.exe (onedir, --noconsole). Run through scripts/gerar_instalador.py.
# Paths are relative to the repository root (SPECPATH is this folder).
from pathlib import Path
import ssl

from PyInstaller.utils.hooks import collect_all, collect_submodules

RAIZ = Path(SPECPATH).resolve().parent
SCRIPTS = RAIZ / 'scripts'
ICONE = RAIZ / 'build' / 'instalador' / 'vlado.ico'

datas = [(str(RAIZ / 'interface'), 'interface')]
# Some Python distributions load this distrust list from beside ssl.py on every TLS context.
lista_ssl = Path(ssl.__file__).with_name('codex-rejected-cas.pem')
if lista_ssl.is_file():
    datas.append((str(lista_ssl), '.'))

# Template of the data folder (%LOCALAPPDATA%\Vlado); copied by the launcher, never over user state.
for relativo in ('AGENTS.md', 'README.md', 'configuracao.json', 'casos/catalogo.json', 'casos/README.md',
                 'execucoes/README.md', 'entrada/README.md'):
    datas.append((str(RAIZ / relativo), str(Path('modelo_dados') / Path(relativo).parent)))
for pasta in ('prompts', 'modelos'):
    datas.append((str(RAIZ / pasta), str(Path('modelo_dados') / pasta)))

binaries, hiddenimports = [], []
# Every project module: the server imports several of them lazily.
hiddenimports += [p.stem for p in SCRIPTS.glob('*.py') if p.stem not in ('gerar_instalador',)]
for pacote in ('ocrmypdf', 'pikepdf', 'pymupdf', 'pypdf', 'reportlab', 'docx', 'anthropic', 'openai',
               'argon2', 'pluggy', 'pdfminer', 'img2pdf', 'PIL', 'lxml', 'certifi'):
    try:
        d, b, h = collect_all(pacote)
    except Exception:  # noqa: BLE001 - optional package absent in this environment
        continue
    datas += d
    binaries += b
    hiddenimports += h
hiddenimports += collect_submodules('ocrmypdf.builtin_plugins')

a = Analysis(
    [str(SCRIPTS / 'vlado_lancador.py')],
    pathex=[str(SCRIPTS)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=['tkinter', 'matplotlib', 'IPython', 'pytest', 'notebook'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Vlado',
    console=False,  # GUI subsystem: never opens a console window
    disable_windowed_traceback=False,
    icon=str(ICONE),
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name='Vlado', upx=False)
