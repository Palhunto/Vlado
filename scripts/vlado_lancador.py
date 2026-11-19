"""Vlado.exe: Windows launcher for the installed desk (PyInstaller, --noconsole).

- Never opens a console window: stdout/stderr go to a log file in the data folder.
- Data live in %LOCALAPPDATA%\\Vlado (VLADO_DADOS overrides): cases, conversations, runs, accounts,
  sessions and segredos/chaves.json. Program files are only read.
- Bundled Tesseract and Ghostscript are wired through VLADO_TESSERACT / VLADO_TESSDATA /
  VLADO_GHOSTSCRIPT, never through the system PATH.
- One instance per Windows user (named mutex): a second start only opens the browser.
- Serves the desk in mode "local-contas" on a free 127.0.0.1 port and opens the default browser.
  "Encerrar serviço" in the desk stops the server and this process.
- `Vlado.exe -m ocrmypdf ...` runs the OCRmyPDF CLI (ocr.py starts it as `sys.executable -m ocrmypdf`).
"""
from __future__ import annotations

import json
import multiprocessing
import os
from pathlib import Path
import shutil
import socket
import sys

NOME_MUTEX = 'Local\\VladoMesaDeApuracao'
PORTA_PREFERIDA = 8765
# Copied only when missing: they hold the user's own state or settings.
MODELOS_DADOS = ('configuracao.json', 'casos/catalogo.json', 'casos/README.md', 'execucoes/README.md',
                 'entrada/README.md')
# Refreshed on every start: method and templates that come with the program version.
MODELOS_PROGRAMA = ('AGENTS.md', 'README.md', 'prompts', 'modelos')


def pasta_programa() -> Path:
    return Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1]


def pasta_pacote() -> Path:
    """Read-only files bundled by PyInstaller (sys._MEIPASS) or the repository in a dev run."""
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))


def pasta_dados() -> Path:
    proprio = os.environ.get('VLADO_DADOS', '').strip()
    if proprio:
        return Path(proprio)
    base = os.environ.get('LOCALAPPDATA') or str(Path.home() / 'AppData' / 'Local')
    return Path(base) / 'Vlado'


def _mensagem(texto: str) -> None:
    if os.name == 'nt' and os.environ.get('VLADO_SEM_JANELAS') != '1':
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, texto, 'Vlado', 0x10)


def _redirecionar_saidas(dados: Path) -> None:
    """--noconsole leaves sys.stdout/stderr as None; anything printed would crash the server."""
    pasta = dados / 'logs'
    pasta.mkdir(parents=True, exist_ok=True)
    log = open(pasta / 'vlado.log', 'a', encoding='utf-8', buffering=1)  # noqa: SIM115 - process lifetime
    sys.stdout = log
    sys.stderr = log


def configurar_ocr(programa: Path) -> None:
    """Point OCR at the bundled engines when present (an explicit environment value wins)."""
    tesseract = programa / 'tesseract' / 'tesseract.exe'
    tessdata = programa / 'tesseract' / 'tessdata'
    ghostscript = programa / 'ghostscript' / 'bin' / 'gswin64c.exe'
    if tesseract.is_file():
        os.environ.setdefault('VLADO_TESSERACT', str(tesseract))
    if tessdata.is_dir():
        os.environ.setdefault('VLADO_TESSDATA', str(tessdata))
    if ghostscript.is_file():
        os.environ.setdefault('VLADO_GHOSTSCRIPT', str(ghostscript))
    os.environ.setdefault('VLADO_OCR_IDIOMAS', 'por+eng')


def preparar_dados(dados: Path, modelo: Path) -> None:
    """Create the data folder from the bundled template. Never overwrites user state."""
    dados.mkdir(parents=True, exist_ok=True)
    for pasta in ('casos', 'conversas', 'execucoes', 'entrada', 'lixeira', 'acesso', 'segredos', 'logs'):
        (dados / pasta).mkdir(exist_ok=True)
    for relativo in MODELOS_DADOS:
        origem, destino = modelo / relativo, dados / relativo
        if origem.is_file() and not destino.exists():
            destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origem, destino)
    for relativo in MODELOS_PROGRAMA:
        origem, destino = modelo / relativo, dados / relativo
        if origem.is_dir():
            shutil.copytree(origem, destino, dirs_exist_ok=True)
        elif origem.is_file():
            shutil.copy2(origem, destino)


class InstanciaUnica:
    """Named mutex per Windows session; released when the process ends."""

    def __init__(self) -> None:
        self.handle = None
        self.primeira = True
        if os.name != 'nt':
            return
        import ctypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateMutexW.restype = ctypes.c_void_p
        self.handle = kernel.CreateMutexW(None, False, NOME_MUTEX)
        self.primeira = ctypes.get_last_error() != 183  # ERROR_ALREADY_EXISTS

    def liberar(self) -> None:
        if self.handle and os.name == 'nt':
            import ctypes
            ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(self.handle))
            self.handle = None


def _estado(dados: Path) -> Path:
    return dados / 'logs' / 'servidor.json'


def _porta_livre(porta: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as teste:
        if os.name == 'nt':
            teste.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            teste.bind(('127.0.0.1', porta))
            return True
        except OSError:
            return False


def escolher_porta(dados: Path) -> int:
    """Last port used (activation links keep working), else 8765, else any free port."""
    try:
        anterior = int(json.loads(_estado(dados).read_text(encoding='utf-8'))['porta'])
    except (OSError, ValueError, KeyError, TypeError):
        anterior = None
    for porta in (anterior, PORTA_PREFERIDA):
        if porta and 1024 < porta < 65536 and _porta_livre(porta):
            return porta
    return 0


def abrir_navegador(endereco: str) -> None:
    if os.environ.get('VLADO_SEM_NAVEGADOR') == '1':
        return
    import webbrowser
    webbrowser.open(endereco)


def reabrir_instancia(dados: Path) -> int:
    try:
        porta = int(json.loads(_estado(dados).read_text(encoding='utf-8'))['porta'])
    except (OSError, ValueError, KeyError, TypeError):
        _mensagem('O Vlado já está aberto, mas não foi possível localizar o endereço. '
                  'Feche o Vlado pelo botão "Encerrar serviço" e abra de novo.')
        return 1
    abrir_navegador(f'http://127.0.0.1:{porta}/')
    return 0


def servir(dados: Path) -> int:
    from interface_pesquisa import Servidor
    with Servidor(('127.0.0.1', escolher_porta(dados)), root=dados, modo='local-contas') as server:
        _estado(dados).write_text(json.dumps({'porta': server.server_port, 'pid': os.getpid()}), encoding='utf-8')
        print(f'Vlado: {server.origin}', flush=True)
        abrir_navegador(server.origin + '/')
        server.serve_forever()
        print('Vlado encerrado.', flush=True)
    return 0


def _ocrmypdf(argumentos: list[str]) -> int:
    from ocrmypdf.__main__ import run
    sys.argv = ['ocrmypdf', *argumentos]
    return int(run() or 0)


def _verificar_https() -> int:
    """Exercise the packaged clients' TLS initialization without making requests."""
    from inferencia_api import Inferencia, criar_provedor_padrao

    for codigo, nome in enumerate(('openai', 'anthropic'), start=1):
        try:
            provedor = criar_provedor_padrao(Inferencia(nome, 'verificacao', 1), 'vlado-build-test-key')
            provedor.cliente.close()
        except Exception:
            return codigo
    return 0


def principal(argv: list[str]) -> int:
    if argv == ['--verificar-https']:
        return _verificar_https()
    if argv[:2] == ['-m', 'ocrmypdf']:
        return _ocrmypdf(argv[2:])
    dados = pasta_dados()
    _redirecionar_saidas(dados)
    configurar_ocr(pasta_programa())
    instancia = InstanciaUnica()
    if not instancia.primeira:
        return reabrir_instancia(dados)
    try:
        preparar_dados(dados, pasta_pacote() / 'modelo_dados')
        return servir(dados)
    except OSError as exc:
        _mensagem(f'Não foi possível iniciar o Vlado.\n{exc}')
        return 1
    finally:
        instancia.liberar()


if __name__ == '__main__':
    multiprocessing.freeze_support()  # OCRmyPDF workers re-enter this executable
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(principal(sys.argv[1:]))
