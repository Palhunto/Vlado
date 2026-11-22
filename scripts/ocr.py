"""OCR local para paginas de PDF sem texto nativo e, so quando pedido, imagens avulsas.
Nenhum arquivo sai desta maquina.

Motores, em ordem de preferencia (VLADO_OCR_MOTOR=auto):
1. OCRmyPDF (+ Tesseract + Ghostscript), restrito as paginas pedidas, com rotacao automatica; as paginas
   que a leitura dupla decide girar vao giradas numa copia temporaria (o original nao muda);
2. alternativa: PyMuPDF renderiza a pagina e a CLI do Tesseract reconhece o texto (OSD corrige giro).
Orientacao, igual nos dois: com confianca do OSD >= CONFIANCA_OSD_MINIMA a pagina gira como ele diz;
abaixo disso, se ele sugere giro, a pagina e lida nas duas orientacoes e fica a leitura de maior
confianca media das palavras (_orientar_pagina); a decisao e a medida vao para o recibo.

Configuracao por variaveis de ambiente: VLADO_OCR=0 desliga; VLADO_OCR_IDIOMAS (padrao por+eng);
VLADO_TESSERACT (executavel); VLADO_TESSDATA (pasta de idiomas); VLADO_OCR_MOTOR
(auto|ocrmypdf|tesseract); VLADO_OCR_TIMEOUT (segundos por pagina). Subprocessos nao abrem janelas.
Nao chama modelos de linguagem nem rede.

Paralelismo e progresso (fila de extracao, CONF-02): dentro de ``execucao(paralelo=N, progresso=f)``
a conferencia de orientacao e o motor Tesseract direto leem ate N paginas ao mesmo tempo, o
OCRmyPDF recebe ``--jobs N`` e ``f(fase, feitas, total)`` recebe o andamento. Fora desse bloco
tudo continua como antes: uma pagina por vez, sem ``--jobs``. O PyMuPDF nao aceita duas threads
ao mesmo tempo: renderizar e girar paginas passam por ``_PYMUPDF``; so o Tesseract roda em
paralelo.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import contextvars
from functools import lru_cache
import importlib.util
import importlib.metadata
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading

from comum import sha256

IDIOMAS_PADRAO = 'por+eng'
TESSERACT_WINDOWS = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
TIMEOUT_PAGINA_PADRAO = 180
TIMEOUT_VERSAO = 20
DPI_RENDERIZACAO = 300
LADO_MAXIMO_PX = 7000
# Minimum OSD orientation confidence to rotate a page, the same for both engines: OCRmyPDF's own
# default (14). A low value turns UPRIGHT pages upside down: measured on Tesseract 5.3, OSD asks
# for 180 deg on upright pages in capitals (20 lines 8.71, 3 lines 5.29, 1 line 2.96) and on a
# blurred table of numbers (2.21); with 2.0 those pages lost all their text, and the direct
# Tesseract engine turned 29 of 200 upright pages the wrong way, none with 8 to 14. Short pages
# scanned sideways also measure below 14 (1 to 3 lines: 4 to 12); for them, see _orientar_pagina.
CONFIANCA_OSD_MINIMA = 14.0
# Below the threshold the page is read as it is and as the OSD suggests; the suggested turn wins
# only when its mean word confidence (0 to 100) beats the original reading by MARGEM_LEITURA_DUPLA
# points and reaches MEDIDA_MINIMA_GIRADA. Calibrated on 600 synthetic pages (24 kinds x 6
# degradations x 4 turns, Tesseract 5.3 and 5.5): 0 of 36 upright pages turned, 0 of 63 wrong suggestions
# followed, every 180-degree page with text straightened. Upright symmetric digits read 94 as they
# are and 86 turned (the margin); an upright grid with no readable text read 0 and 25.6 turned
# (the minimum); real text turned the right way read 62 to 99.
MARGEM_LEITURA_DUPLA = 10.0
MEDIDA_MINIMA_GIRADA = 50.0
_DESLIGADO = {'0', 'false', 'nao', 'não', 'no', 'off'}
_SALTO = re.compile(r'^\[OCR skipped on page\(s\) (\d+)(?:-(\d+))?\]$')
# PyMuPDF is not thread-safe: every render and page turn goes through this lock.
_PYMUPDF = threading.RLock()
_EXECUCAO = contextvars.ContextVar('vlado_ocr_execucao', default=None)


@contextmanager
def execucao(paralelo=None, progresso=None):
    """Pages read at the same time (None: one, as before) and a progress callback for this block.

    ``progresso(fase, feitas, total)``: ``fase`` is ``orientacao`` (pages checked before the
    OCRmyPDF), ``reconhecimento`` (OCRmyPDF over the pages, reported at start and end) or
    ``paginas`` (pages read by the direct Tesseract engine). Errors in the callback are ignored.
    """
    marca = _EXECUCAO.set({'paralelo': max(1, int(paralelo)) if paralelo else None, 'progresso': progresso})
    try:
        yield
    finally:
        _EXECUCAO.reset(marca)


def _paralelo() -> int | None:
    opcoes = _EXECUCAO.get()
    return opcoes['paralelo'] if opcoes else None


def _avisar(fase, feitas, total, opcoes=None):
    opcoes = opcoes or _EXECUCAO.get()
    if opcoes and opcoes['progresso']:
        try:
            opcoes['progresso'](fase, feitas, total)
        except Exception:  # noqa: BLE001 - progress never breaks the reading
            pass


def _por_pagina(paginas, ler, fase):
    """``[ler(n) for n in paginas]``, up to ``_paralelo()`` pages at a time, in page order.

    The context of ``execucao`` is read here, in the caller's thread (worker threads do not
    inherit it); ``ler`` must not raise (each caller turns a page's error into its result).
    """
    opcoes = _EXECUCAO.get()
    largura = min(_paralelo() or 1, len(paginas)) if paginas else 1
    feitas, trava = [0], threading.Lock()

    def uma(numero):
        try:
            return ler(numero)
        finally:
            with trava:
                feitas[0] += 1
                contagem = feitas[0]
            _avisar(fase, contagem, len(paginas), opcoes)

    if largura <= 1:
        return [uma(n) for n in paginas]
    with ThreadPoolExecutor(max_workers=largura, thread_name_prefix='vlado_ocr') as grupo:
        return list(grupo.map(uma, paginas))


class OcrIndisponivel(RuntimeError):
    """OCR desligado ou sem motor utilizavel; o cadastro segue sem OCR."""


class OcrFalha(RuntimeError):
    """Falha de um motor ao processar o lote de paginas."""


def configuracao() -> dict:
    env = os.environ
    idiomas = (env.get('VLADO_OCR_IDIOMAS') or IDIOMAS_PADRAO).strip()
    if not re.fullmatch(r'[A-Za-z0-9_]{2,16}(\+[A-Za-z0-9_]{2,16}){0,5}', idiomas):
        raise ValueError('VLADO_OCR_IDIOMAS invalido: use codigos separados por +, como por+eng.')
    executavel = (env.get('VLADO_TESSERACT') or '').strip() or shutil.which('tesseract')
    if not executavel and os.name == 'nt' and os.path.isfile(TESSERACT_WINDOWS):
        executavel = TESSERACT_WINDOWS
    tessdata = (env.get('VLADO_TESSDATA') or '').strip() or None
    if not tessdata and env.get('LOCALAPPDATA'):
        candidato = Path(env['LOCALAPPDATA']) / 'vlado' / 'tessdata'
        tessdata = str(candidato) if candidato.is_dir() else None
    motor = (env.get('VLADO_OCR_MOTOR') or 'auto').strip().lower()
    if motor not in ('auto', 'ocrmypdf', 'tesseract'):
        raise ValueError('VLADO_OCR_MOTOR invalido: auto, ocrmypdf ou tesseract.')
    try:
        timeout = max(10, int(env.get('VLADO_OCR_TIMEOUT') or TIMEOUT_PAGINA_PADRAO))
    except ValueError as exc:
        raise ValueError('VLADO_OCR_TIMEOUT deve ser um numero inteiro de segundos.') from exc
    return {'habilitado': (env.get('VLADO_OCR') or '1').strip().lower() not in _DESLIGADO,
            'idiomas': idiomas, 'tesseract': executavel, 'tessdata': tessdata,
            'motor': motor, 'timeout_pagina': timeout}


def _executar(args, *, timeout, env=None):
    """Run a child process without a console window, capturing output, with a timeout."""
    opcoes = {'capture_output': True, 'timeout': timeout, 'env': env, 'check': False}
    if os.name == 'nt':
        opcoes['creationflags'] = subprocess.CREATE_NO_WINDOW
    return subprocess.run(args, **opcoes)


def _ambiente(config) -> dict:
    env = dict(os.environ)
    if config.get('tessdata'):
        env['TESSDATA_PREFIX'] = config['tessdata']
    if config.get('tesseract'):
        pasta = str(Path(config['tesseract']).parent)
        env['PATH'] = pasta + os.pathsep + env.get('PATH', '')
    gs = (env.get('VLADO_GHOSTSCRIPT') or '').strip()
    if gs and os.path.isfile(gs):
        env['PATH'] = str(Path(gs).parent) + os.pathsep + env.get('PATH', '')
    return env


def _ambiente_tesseract(config) -> dict:
    """Environment for direct Tesseract runs: one OpenMP thread unless OMP_THREAD_LIMIT is set.

    Tesseract's OpenMP threads busy-wait for each other; with two OCR jobs at once on 4 cores a
    page went from 3 s to 100-250 s and calls hit the timeout, while one thread read it in 3-4 s
    with byte-identical txt, tsv and OSD output (Tesseract 5.3 and 5.5). OCRmyPDF sets its own
    limit (up to 3 threads per page on short PDFs) and is left as it is.
    """
    env = _ambiente(config)
    if not env.get('OMP_THREAD_LIMIT', '').strip().isdigit():
        env['OMP_THREAD_LIMIT'] = '1'
    return env


def _texto(processo) -> str:
    return (processo.stdout or b'').decode('utf-8', errors='replace')


def _erro_curto(processo) -> str:
    detalhe = (processo.stderr or b'').decode('utf-8', errors='replace').strip()
    return detalhe[-500:] or f'codigo de saida {processo.returncode}'


def _tesseract_ok(config) -> bool:
    return bool(config.get('tesseract')) and os.path.isfile(config['tesseract'])


@lru_cache(maxsize=8)
def _versao_tesseract(executavel):
    try:
        saida = _texto(_executar([executavel, '--version'], timeout=TIMEOUT_VERSAO))
        # Tesseract 5 escreve a versao em stdout ou stderr conforme a plataforma.
        return saida.splitlines()[0].replace('tesseract', '').strip() if saida.strip() else None
    except (OSError, subprocess.SubprocessError):
        return None


@lru_cache(maxsize=8)
def _idiomas_instalados(executavel, tessdata, ambiente_chave):
    config = {'tesseract': executavel, 'tessdata': tessdata}
    args = [executavel, '--list-langs'] + (['--tessdata-dir', tessdata] if tessdata else [])
    try:
        processo = _executar(args, timeout=TIMEOUT_VERSAO, env=_ambiente(config))
    except (OSError, subprocess.SubprocessError):
        return ()
    linhas = (_texto(processo) + (processo.stderr or b'').decode('utf-8', errors='replace')).splitlines()
    return tuple(l.strip() for l in linhas if re.fullmatch(r'[A-Za-z0-9_]+', l.strip()) and l.strip() != 'List')


def _tesseract_disponivel(config=None) -> bool:
    config = config or configuracao()
    if not _tesseract_ok(config):
        return False
    return not _idiomas_ausentes(config)


def _idiomas_ausentes(config):
    instalados = _idiomas_instalados(config['tesseract'], config['tessdata'], os.environ.get('TESSDATA_PREFIX'))
    return [i for i in config['idiomas'].split('+') if i not in instalados]


def _ghostscript():
    proprio = (os.environ.get('VLADO_GHOSTSCRIPT') or '').strip()
    if proprio and os.path.isfile(proprio):
        return proprio  # bundled copy (Windows installer); no system PATH needed
    for nome in (('gswin64c', 'gswin32c', 'gs') if os.name == 'nt' else ('gs',)):
        encontrado = shutil.which(nome)
        if encontrado:
            return encontrado
    return None


def _ocrmypdf_disponivel(config=None) -> bool:
    config = config or configuracao()
    return (importlib.util.find_spec('ocrmypdf') is not None and _ghostscript() is not None
            and _tesseract_disponivel(config))


def _pymupdf_disponivel() -> bool:
    return importlib.util.find_spec('pymupdf') is not None


@lru_cache(maxsize=4)
def _versao_ghostscript(executavel):
    try:
        return _texto(_executar([executavel, '--version'], timeout=TIMEOUT_VERSAO)).strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def _versao_pymupdf():
    try:
        return importlib.metadata.version('pymupdf')
    except importlib.metadata.PackageNotFoundError:
        return None


def _versoes(config, motor) -> dict:
    """Versions actually in use by the engine, for the receipt; unknown stays None."""
    versoes = {'tesseract': _versao_tesseract(config['tesseract']) if config.get('tesseract') else None}
    if motor == 'ocrmypdf':
        try:
            versoes['ocrmypdf'] = importlib.metadata.version('ocrmypdf')
        except importlib.metadata.PackageNotFoundError:
            versoes['ocrmypdf'] = None
        gs = _ghostscript()
        versoes['ghostscript'] = _versao_ghostscript(gs) if gs else None
    else:
        versoes['pymupdf'] = _versao_pymupdf()
    return versoes


def _motores(config) -> list:
    """Engines to try, in order."""
    if config['motor'] == 'ocrmypdf':
        return ['ocrmypdf'] if _ocrmypdf_disponivel(config) else []
    if config['motor'] == 'tesseract':
        return ['tesseract'] if _tesseract_alternativa(config) else []
    ordem = []
    if _ocrmypdf_disponivel(config):
        ordem.append('ocrmypdf')
    if _tesseract_alternativa(config):
        ordem.append('tesseract')
    return ordem


def _tesseract_alternativa(config) -> bool:
    return _pymupdf_disponivel() and _tesseract_disponivel(config)


def diagnostico() -> dict:
    """Describe OCR availability without processing any document."""
    try:
        config = configuracao()
    except ValueError as exc:
        return {'disponivel': False, 'motivo': str(exc), 'motor': None,
                'tesseract': {'disponivel': False}, 'ocrmypdf': {'disponivel': False}}
    tesseract = {'disponivel': _tesseract_ok(config), 'caminho': config['tesseract'],
                 'versao': _versao_tesseract(config['tesseract']) if _tesseract_ok(config) else None,
                 'tessdata': config['tessdata'], 'idiomas': config['idiomas']}
    if tesseract['disponivel']:
        ausentes = _idiomas_ausentes(config)
        if ausentes:
            tesseract.update(disponivel=False, idiomas_ausentes=ausentes)
    resultado = {'habilitado': config['habilitado'], 'tesseract': tesseract,
                 'ocrmypdf': {'disponivel': importlib.util.find_spec('ocrmypdf') is not None
                              and _ghostscript() is not None and tesseract['disponivel'],
                              'ghostscript': _ghostscript()},
                 'pymupdf': {'disponivel': _pymupdf_disponivel()}}
    if not config['habilitado']:
        return {**resultado, 'disponivel': False, 'motor': None, 'motivo': 'OCR desabilitado (VLADO_OCR=0).'}
    motores = _motores(config) if tesseract['disponivel'] else []
    if not motores:
        motivo = ('Tesseract ou idiomas ausentes (' + ', '.join(tesseract.get('idiomas_ausentes', [])) + ').'
                  if not tesseract['disponivel'] else 'Nenhum motor completo: instalar OCRmyPDF com Ghostscript ou PyMuPDF.')
        return {**resultado, 'disponivel': False, 'motor': None, 'motivo': motivo.replace(' ().', '.')}
    return {**resultado, 'disponivel': True, 'motor': motores[0], 'motivo': None}


def _limpar(texto: str) -> str:
    texto = texto.replace('\r\n', '\n').replace('\r', '\n').replace('\f', '\n')
    texto = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', texto)
    return '\n'.join(l.rstrip() for l in texto.split('\n') if l.strip())


def _paginas_do_sidecar(texto: str, total: int) -> dict:
    """Map OCRmyPDF sidecar chunks (form feed per page, skipped ranges collapsed) to pages."""
    paginas, atual = {}, 1
    for pedaco in texto.split('\f'):
        salto = _SALTO.fullmatch(pedaco.strip())
        if salto:
            atual = int(salto[2] or salto[1]) + 1
            continue
        if atual <= total:
            paginas[atual] = pedaco.strip()
        atual += 1
    return paginas


def _motor_ocrmypdf(pdf: Path, paginas: list, total: int, config: dict) -> dict:
    # OCRmyPDF reads every page. The direct reading (PyMuPDF render + Tesseract) tears tables in
    # Courier and grids apart, which OCRmyPDF reads whole, so it only serves the decision. Pages
    # with OSD >= threshold go as they are (OCRmyPDF turns them with the same threshold). Pages
    # the double reading decided to turn go turned, in a temporary copy of the PDF (the original
    # is never changed): below the threshold OCRmyPDF would not turn them. If the copy cannot be
    # made, those pages keep the direct reading of the double reading.
    diretas, registros, avisos_orientacao = _orientar_antes(pdf, paginas, config)
    giros = {n: d['orientacao']['giro_aplicado'] for n, d in diretas.items()}
    giradas_antes, lidas_direto = [], []
    resultado = {}
    with tempfile.TemporaryDirectory(prefix='vlado_ocr_') as pasta:
        fonte = pdf
        if giros:
            try:
                fonte = _copia_girada(pdf, giros, Path(pasta) / 'girado.pdf')
                giradas_antes = sorted(giros)
            except Exception as exc:  # noqa: BLE001 - keep the direct reading of those pages, say why
                lidas_direto = sorted(giros)
                for n in lidas_direto:
                    avisos_orientacao.setdefault(n, f'Copia girada nao criada ({type(exc).__name__}: '
                                                    f'{str(exc)[:150]}); texto da leitura direta do Tesseract.')
        restantes = [n for n in paginas if n not in lidas_direto]
        reconhecido = _sidecar_ocrmypdf(fonte, restantes, max(total, max(paginas)), config) if restantes else {}
    for n in restantes:
        resultado[n] = ({'texto': _limpar(reconhecido[n])} if n in reconhecido
                        else {'erro': 'OCRmyPDF nao processou esta pagina.'})
        registro = diretas[n]['orientacao'] if n in diretas else registros.get(n)
        if registro and 'texto' in resultado[n]:
            resultado[n]['orientacao'] = {**registro, 'texto_de': 'ocrmypdf'}
    for n in lidas_direto:
        resultado[n] = diretas[n]
    for n, aviso in avisos_orientacao.items():
        resultado[n]['aviso_orientacao'] = aviso
    versoes = (_versoes(config, 'ocrmypdf') if restantes
               else {'tesseract': _versao_tesseract(config['tesseract']) if config.get('tesseract') else None})
    if giros:
        versoes['pymupdf'] = _versao_pymupdf()
    return {'motor': 'ocrmypdf', 'versoes': versoes, 'idiomas': config['idiomas'],
            'paginas': {n: resultado[n] for n in paginas}, 'paginas_giradas_antes': giradas_antes,
            'paginas_tesseract_direto': lidas_direto,
            'avisos': [f'pagina {n}: {a}' for n, a in sorted(avisos_orientacao.items())]}


def _copia_girada(pdf: Path, giros: dict, destino: Path) -> Path:
    """Temporary copy of the PDF with pages {number: degrees clockwise} turned, for OCRmyPDF."""
    import pymupdf
    documento = pymupdf.open(str(pdf))
    try:
        if documento.needs_pass and not documento.authenticate(''):
            raise OcrFalha('PDF protegido por senha.')
        for numero, giro in giros.items():
            pagina = documento[numero - 1]
            pagina.set_rotation((pagina.rotation + giro) % 360)
        documento.save(str(destino))
    finally:
        documento.close()
    return destino


def _sidecar_ocrmypdf(pdf: Path, paginas: list, total: int, config: dict) -> dict:
    with tempfile.TemporaryDirectory(prefix='vlado_ocr_') as pasta:
        lado = Path(pasta) / 'texto.txt'
        # --force-ocr nas paginas ja classificadas sem texto util: ignora camadas de texto residuais.
        # A saida PDF e descartada (--output-type none); o original nunca e reescrito.
        # Saida '-': no Windows os.devnull ('nul') e aberto pelo OCRmyPDF como PDF danificado e o motor falha.
        args = [sys.executable, '-m', 'ocrmypdf', '--quiet', '--force-ocr', '--rotate-pages',
                '--rotate-pages-threshold', str(CONFIANCA_OSD_MINIMA),
                '-l', config['idiomas'], '--pages', ','.join(str(p) for p in paginas),
                '--output-type', 'none', '--sidecar', str(lado), str(pdf), '-']
        if _paralelo():
            # Inside the extraction queue: the pages this file may use; outside it, OCRmyPDF's default.
            args[3:3] = ['--jobs', str(_paralelo())]
        timeout = config['timeout_pagina'] * len(paginas) + 60
        _avisar('reconhecimento', 0, len(paginas))
        try:
            processo = _executar(args, timeout=timeout, env=_ambiente(config))
        except subprocess.TimeoutExpired as exc:
            raise OcrFalha(f'OCRmyPDF excedeu {timeout}s.') from exc
        except OSError as exc:
            raise OcrFalha(f'OCRmyPDF nao executou: {exc}') from exc
        if processo.returncode != 0:
            raise OcrFalha(f'OCRmyPDF falhou: {_erro_curto(processo)}')
        if not lado.is_file():
            raise OcrFalha('OCRmyPDF nao gerou o texto lateral (sidecar).')
        _avisar('reconhecimento', len(paginas), len(paginas))
        return _paginas_do_sidecar(lado.read_text(encoding='utf-8', errors='replace'), total)


def _orientar_antes(pdf: Path, paginas: list, config: dict) -> tuple:
    """Before OCRmyPDF: every page gets the same orientation decision as in the direct engine.

    Returns ({page: direct reading and record} for pages the double reading turned, which go to
    OCRmyPDF turned, the direct reading only kept for when the turned copy fails; {page: record}
    for the other pages with a suggested turn; {page: warning} for pages whose check failed).
    Without PyMuPDF, or if it cannot open the PDF, every page goes to OCRmyPDF without a record.
    """
    diretas, registros, avisos = {}, {}, {}
    if not _pymupdf_disponivel():
        return diretas, registros, avisos
    import pymupdf
    try:
        documento = pymupdf.open(str(pdf))
        if documento.needs_pass and not documento.authenticate(''):
            documento.close()
            return diretas, registros, avisos
    except Exception:  # noqa: BLE001 - OCRmyPDF reads it on its own
        return diretas, registros, avisos
    total = len(documento)

    def ler(numero):
        if not 1 <= numero <= total:
            return numero, None, None, None
        try:
            with _PYMUPDF:
                pagina = documento[numero - 1]
            texto, registro = _pagina_orientada(pagina, numero, config, motor_direto=False)
        except Exception as exc:  # noqa: BLE001 - OCRmyPDF reads the page, say why
            return numero, None, None, f'Orientacao nao conferida: {type(exc).__name__}: {str(exc)[:200]}'
        return numero, texto, registro, None

    try:
        # Up to the queue's page budget at a time (ressalva 27: this check used to run one page at a time).
        for numero, texto, registro, aviso in _por_pagina(paginas, ler, 'orientacao'):
            if aviso:
                avisos[numero] = aviso
            elif texto is not None:
                diretas[numero] = {'texto': texto, 'orientacao': {**registro, 'texto_de': 'tesseract'}}
            elif registro:
                registros[numero] = registro
    finally:
        with _PYMUPDF:
            documento.close()
    return diretas, registros, avisos


def _pagina_orientada(pagina, numero: int, config, *, motor_direto: bool) -> tuple:
    """Render one page in its own temporary folder, decide its orientation, delete the files."""
    with tempfile.TemporaryDirectory(prefix='vlado_ocr_') as pasta:
        imagem = Path(pasta) / f'p{numero}.png'
        _renderizar(pagina, imagem)
        return _orientar_pagina(pagina, imagem, config, motor_direto=motor_direto)


def _renderizar(pagina, destino: Path):
    import pymupdf
    with _PYMUPDF:
        zoom = DPI_RENDERIZACAO / 72
        maior = max(pagina.rect.width, pagina.rect.height)
        if maior * zoom > LADO_MAXIMO_PX:
            zoom = LADO_MAXIMO_PX / maior
        pixmap = pagina.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), colorspace=pymupdf.csGRAY, alpha=False)
        pixmap.save(str(destino))
        del pixmap


def _opcoes_tessdata(config):
    return ['--tessdata-dir', config['tessdata']] if config.get('tessdata') else []


def _osd(imagem: Path, config) -> tuple:
    """(degrees clockwise the OSD asks for, its confidence); (0, None) when OSD is unavailable."""
    args = [config['tesseract'], str(imagem), 'stdout', '--psm', '0'] + _opcoes_tessdata(config)
    try:
        processo = _executar(args, timeout=config['timeout_pagina'], env=_ambiente_tesseract(config))
    except (OSError, subprocess.SubprocessError):
        return 0, None
    saida = _texto(processo) + (processo.stderr or b'').decode('utf-8', errors='replace')
    giro, confianca = re.search(r'Rotate:\s*(\d+)', saida), re.search(r'Orientation confidence:\s*([0-9.]+)', saida)
    if processo.returncode != 0 or not giro or not confianca or int(giro[1]) % 90:
        return 0, None
    return int(giro[1]) % 360, float(confianca[1])


def _giro_osd(imagem: Path, config) -> int:
    """Degrees clockwise needed to make the page upright; 0 when OSD is unavailable or unsure."""
    giro, confianca = _osd(imagem, config)
    return giro if confianca is not None and confianca >= CONFIANCA_OSD_MINIMA else 0


def _reconhecer_imagem(imagem: Path, config) -> str:
    args = [config['tesseract'], str(imagem), 'stdout', '-l', config['idiomas'], '--psm', '3'] + _opcoes_tessdata(config)
    try:
        processo = _executar(args, timeout=config['timeout_pagina'], env=_ambiente_tesseract(config))
    except subprocess.TimeoutExpired as exc:
        raise OcrFalha(f'Tesseract excedeu {config["timeout_pagina"]}s.') from exc
    except OSError as exc:
        raise OcrFalha(f'Tesseract nao executou: {exc}') from exc
    if processo.returncode != 0:
        raise OcrFalha(f'Tesseract falhou: {_erro_curto(processo)}')
    return _limpar(_texto(processo))


def _medida_tsv(tsv: str) -> tuple:
    """(mean word confidence weighted by alphanumeric characters, 0-100; words counted)."""
    soma = peso = palavras = 0
    for linha in tsv.splitlines()[1:]:
        campos = linha.split('\t')
        if len(campos) < 12 or campos[0] != '5':
            continue
        try:
            confianca = float(campos[10])
        except ValueError:
            continue
        caracteres = sum(1 for c in campos[11] if c.isalnum())
        if confianca < 0 or not caracteres:
            continue
        soma, peso, palavras = soma + confianca * caracteres, peso + caracteres, palavras + 1
    return (round(soma / peso, 1) if peso else 0.0), palavras


def _ler_com_medida(imagem: Path, config) -> tuple:
    """Text plus its quality measure (None when Tesseract wrote no .tsv) from one Tesseract run.

    The outputs are asked with -c variables, not with the `txt`/`tsv` config files, which live in
    tessdata/configs and are missing from a folder holding only the .traineddata files.
    """
    base = imagem.with_name(imagem.stem + '_leitura')
    args = ([config['tesseract'], str(imagem), str(base), '-l', config['idiomas'], '--psm', '3']
            + _opcoes_tessdata(config) + ['-c', 'tessedit_create_txt=1', '-c', 'tessedit_create_tsv=1'])
    try:
        processo = _executar(args, timeout=config['timeout_pagina'], env=_ambiente_tesseract(config))
    except subprocess.TimeoutExpired as exc:
        raise OcrFalha(f'Tesseract excedeu {config["timeout_pagina"]}s.') from exc
    except OSError as exc:
        raise OcrFalha(f'Tesseract nao executou: {exc}') from exc
    if processo.returncode != 0:
        raise OcrFalha(f'Tesseract falhou: {_erro_curto(processo)}')
    txt, tsv = Path(f'{base}.txt'), Path(f'{base}.tsv')
    texto = (_limpar(txt.read_text(encoding='utf-8', errors='replace')) if txt.is_file()
             else _reconhecer_imagem(imagem, config))
    if not tsv.is_file():
        return texto, None, 0
    medida, palavras = _medida_tsv(tsv.read_text(encoding='utf-8', errors='replace'))
    return texto, medida, palavras


def _orientar_pagina(pagina, imagem: Path, config, *, motor_direto=True):
    """Decide one rendered page's orientation. Returns (text or None, record or None).

    OSD at or above CONFIANCA_OSD_MINIMA: rotate as it says. Below it the OSD is often wrong (it
    asks to turn upright pages in capitals or blurred tables upside down), so the page is read in
    both orientations and the reading with the higher word confidence wins; the suggested turn
    must beat the original by MARGEM_LEITURA_DUPLA and reach MEDIDA_MINIMA_GIRADA, otherwise the
    page stays as it is. Without a .tsv there is no measure and the page stays as it is.
    With `motor_direto` False (OCRmyPDF engine) the text is None unless the double reading turned
    the page: OCRmyPDF keeps its own reading (and turns OSD >= threshold pages itself).
    The rotation only happens in memory: the PDF is never saved or changed.
    """
    giro, confianca = _osd(imagem, config)
    if not giro:
        return (_reconhecer_imagem(imagem, config) if motor_direto else None), None
    registro = {'osd_giro': giro, 'osd_confianca': confianca, 'limiar': CONFIANCA_OSD_MINIMA}
    if confianca >= CONFIANCA_OSD_MINIMA:
        registro.update(decisao='osd', giro_aplicado=giro)
        return (_reconhecer_imagem(_girar(pagina, imagem, giro), config) if motor_direto else None), registro
    texto_original, medida_original, palavras_original = _ler_com_medida(imagem, config)
    texto_girado, medida_girada, palavras_girada = _ler_com_medida(_girar(pagina, imagem, giro), config)
    vence_girada = (medida_original is not None and medida_girada is not None
                    and medida_girada >= medida_original + MARGEM_LEITURA_DUPLA
                    and medida_girada >= MEDIDA_MINIMA_GIRADA)
    registro.update(decisao='leitura_dupla', giro_aplicado=giro if vence_girada else 0,
                    medida='confianca_media_das_palavras', margem=MARGEM_LEITURA_DUPLA,
                    minimo_girada=MEDIDA_MINIMA_GIRADA,
                    original={'medida': medida_original, 'palavras': palavras_original},
                    girada={'medida': medida_girada, 'palavras': palavras_girada})
    if medida_original is None or medida_girada is None:
        registro['aviso'] = 'Tesseract nao gerou o .tsv; sem medida, a pagina fica como esta.'
    if vence_girada:
        return texto_girado, registro
    return (texto_original if motor_direto else None), registro


def _girar(pagina, imagem: Path, giro: int) -> Path:
    """Render the page turned `giro` degrees next to `imagem`; the page itself is put back."""
    girada = imagem.with_name(imagem.stem + f'_g{giro}.png')
    with _PYMUPDF:
        original = pagina.rotation
        pagina.set_rotation((original + giro) % 360)
        try:
            _renderizar(pagina, girada)
        finally:
            pagina.set_rotation(original)
    return girada


def _motor_tesseract(pdf: Path, paginas: list, config: dict) -> dict:
    import pymupdf
    try:
        documento = pymupdf.open(str(pdf))
        if documento.needs_pass and not documento.authenticate(''):
            raise OcrFalha('PDF protegido por senha.')
    except OcrFalha:
        raise
    except Exception as exc:
        raise OcrFalha(f'PyMuPDF nao abriu o PDF: {type(exc).__name__}: {str(exc)[:300]}') from exc
    total = len(documento)

    def ler(numero):
        try:
            if numero < 1 or numero > total:
                raise OcrFalha('Pagina inexistente no PDF.')
            with _PYMUPDF:
                pagina = documento[numero - 1]
            texto, orientacao = _pagina_orientada(pagina, numero, config, motor_direto=True)
            return numero, {'texto': texto, **({'orientacao': {**orientacao, 'texto_de': 'tesseract'}}
                                               if orientacao else {})}
        except Exception as exc:
            return numero, {'erro': f'{type(exc).__name__}: {str(exc)[:500]}'}

    try:
        resultado = dict(_por_pagina(paginas, ler, 'paginas'))
    finally:
        with _PYMUPDF:
            documento.close()
    return {'motor': 'tesseract', 'versoes': _versoes(config, 'tesseract'), 'idiomas': config['idiomas'],
            'paginas': resultado, 'avisos': []}


def reconhecer(pdf: Path, paginas) -> dict:
    """OCR the given 1-based pages. Returns engine, versions and per-page text or error.

    Raises OcrIndisponivel when OCR is disabled or no engine works, so callers can register
    the limitation without failing the batch.
    """
    config = configuracao()
    if not config['habilitado']:
        raise OcrIndisponivel('OCR desabilitado (VLADO_OCR=0).')
    paginas = sorted(set(int(p) for p in paginas))
    if not paginas:
        raise ValueError('Nenhuma pagina para reconhecer.')
    motores = _motores(config)
    if not motores:
        raise OcrIndisponivel(diagnostico().get('motivo') or 'Nenhum motor de OCR disponivel.')
    avisos = []
    for indice, motor in enumerate(motores):
        try:
            resultado = (_motor_ocrmypdf(Path(pdf), paginas, max(paginas), config) if motor == 'ocrmypdf'
                         else _motor_tesseract(Path(pdf), paginas, config))
        except OcrFalha as exc:
            avisos.append(f'{motor}: {exc}')
            if indice == len(motores) - 1:
                raise
            continue
        return {**resultado, 'avisos': avisos + resultado.get('avisos', [])}
    raise OcrIndisponivel('Nenhum motor de OCR disponivel.')


EXTENSOES_IMAGEM = ('.png', '.jpg', '.jpeg')


def reconhecer_imagem(imagem: Path) -> dict:
    """OCR one standalone PNG/JPEG with the local Tesseract CLI; only on explicit request.

    The image is read in place and never rewritten. Raises OcrIndisponivel when OCR is
    disabled or Tesseract/its languages are missing (the image stays pending), and
    OcrFalha when the engine fails on this file.
    """
    imagem = Path(imagem)
    if imagem.suffix.lower() not in EXTENSOES_IMAGEM:
        raise ValueError('OCR de imagem avulsa aceita somente PNG ou JPEG.')
    config = configuracao()
    if not config['habilitado']:
        raise OcrIndisponivel('OCR desabilitado (VLADO_OCR=0).')
    if not _tesseract_ok(config):
        raise OcrIndisponivel('Tesseract nao encontrado nesta maquina: instale o Tesseract OCR '
                              'ou indique o executavel em VLADO_TESSERACT.')
    ausentes = _idiomas_ausentes(config)
    if ausentes:
        raise OcrIndisponivel('Idiomas do Tesseract ausentes: ' + ', '.join(ausentes)
                              + ' (instalar os dados de idioma ou ajustar VLADO_OCR_IDIOMAS).')
    giro, confianca = _osd(imagem, config)
    texto = _reconhecer_imagem(imagem, config)
    avisos = []
    if giro:
        # Below the threshold the OSD is often wrong (upright capitals, blurred tables): say how sure it was.
        duvida = (f' Confianca abaixo de {CONFIANCA_OSD_MINIMA:g}: pode ser alarme falso, comum em '
                  'maiusculas e tabelas.' if confianca < CONFIANCA_OSD_MINIMA else '')
        avisos.append(f'A imagem parece girada {giro} graus (OSD, confianca {confianca:g}); o OCR nao '
                      f'corrigiu a rotacao. Conferir no original.{duvida}')
    return {'motor': 'tesseract', 'versoes': {'tesseract': _versao_tesseract(config['tesseract'])},
            'idiomas': config['idiomas'], 'texto': texto, 'avisos': avisos}


SEM_TEXTO_IMAGEM = '[SEM TEXTO RECONHECIDO NA IMAGEM]'
AVISO_OCR_IMAGEM = ('Texto de reconhecimento automatico (OCR), sujeito a erros; '
                    'conferir no original antes de usar como evidencia.')


def ocr_imagem(source: Path, identifier: str, target: Path) -> dict:
    """Write the located OCR working copy of a standalone image and return an explicit outcome.

    `estado`: extraido | sem_texto | pendente (OCR unavailable; nothing written) | erro
    (engine failure; nothing written). The original image is never modified.
    """
    source, target = Path(source), Path(target)
    if target.exists():
        raise FileExistsError('Nao sobrescrever OCR existente; usar nova versao.')
    result = {'estado': 'erro', 'origem': 'ocr', 'motor': None, 'versoes': {}, 'idiomas': None,
              'linhas': 0, 'metodo': None, 'mensagem': None, 'avisos': [],
              'aviso_conferencia': AVISO_OCR_IMAGEM, 'conferencia_humana': 'nao_realizada'}
    try:
        lido = reconhecer_imagem(source)
    except (OcrIndisponivel, ValueError) as exc:
        return {**result, 'estado': 'pendente',
                'mensagem': f'OCR da imagem nao executado: {exc} A imagem fica pendente; o original esta preservado.'}
    except OcrFalha as exc:
        return {**result, 'mensagem': f'Falha do OCR nesta imagem: {exc} O original esta preservado.'}
    versao = lido['versoes'].get('tesseract') or 'versao nao informada'
    metodo = (f'OCR local de imagem avulsa, pedido explicitamente: Tesseract {versao}; idiomas {lido["idiomas"]}; '
              'sem envio externo, sem modelo e sem correcao editorial.')
    linhas = [line for line in lido['texto'].splitlines() if line.strip()]
    result.update(estado='extraido' if linhas else 'sem_texto', motor=lido['motor'], versoes=lido['versoes'],
                  idiomas=lido['idiomas'], linhas=len(linhas), metodo=metodo, avisos=lido['avisos'])
    header = [f'# {identifier} - copia textual de trabalho', '',
              f'Original: {source.name}', f'SHA-256 do original: {sha256(source)}',
              'Formato: imagem', 'Origem: ocr', f'Metodo: {metodo}', f'Aviso: {AVISO_OCR_IMAGEM}',
              *[f'Aviso: {aviso}' for aviso in lido['avisos']],
              'Copia de trabalho, nao o original; conferir o original antes de usar como evidencia.', '',
              f'## {identifier} - imagem', '']
    body = [f'[L{numero:04d}] {line}' for numero, line in enumerate(linhas, 1)] or [SEM_TEXTO_IMAGEM]
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write('\n'.join(header + body) + '\n')
    return result
