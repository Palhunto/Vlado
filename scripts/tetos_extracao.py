"""Tetos da extração de documentos recebidos (SEG-01): páginas, pixels, memória, CPU e núcleos.

Documentos de fontes são entrada não confiável. Dois níveis de proteção:

- **Dentro da extração** (este módulo; vale na linha de comando, nas threads da Mesa e no processo
  de extração): teto de páginas por PDF, conferido na contagem declarada antes de percorrer a
  árvore de páginas; teto de pixels por página rasterizada a 300 dpi e por imagem declarada no PDF
  (XObject, também dentro de formulários, e imagem embutida no conteúdo), conferido antes de
  qualquer renderização ou OCR; teto de pixels da imagem avulsa antes do Tesseract. A extração de
  Office tem os tetos próprios de pacote (``extrair_office``).
- **No processo de extração** (``trabalhador_extracao.aplicar_limites``): memória, CPU por
  arquivo, núcleos, prioridade e rede, pelo sistema operacional. O tempo de relógio é da fila
  (``VLADO_EXTRACAO_TEMPO_MAXIMO``).

Arquivo que estoura um teto do arquivo inteiro (páginas, pixels da imagem avulsa, memória, CPU,
tempo) fica em ``falha`` na fila, com o motivo, e o original é cadastrado com a extração em erro.
Página que estoura o teto de pixels fica com erro e motivo; as outras páginas seguem.

Configuração (variáveis de ambiente; padrões pensados para 4 vCPU e 8 GB, com dois arquivos ao
mesmo tempo, ``VLADO_EXTRACAO_PROCESSOS=2``):

- ``VLADO_EXTRACAO_TETO_PAGINAS`` (3000): páginas por PDF;
- ``VLADO_EXTRACAO_TETO_MEGAPIXELS`` (150): megapixels por página a 300 dpi (A0 cabe) e por imagem;
- ``VLADO_EXTRACAO_TETO_MEMORIA_MB`` (2048): memória do processo de extração (Windows: dele e dos
  filhos somados; Linux: por processo, cada filho com o seu);
- ``VLADO_EXTRACAO_TETO_CPU_S`` (7200): segundos de CPU por arquivo;
- ``VLADO_EXTRACAO_NUCLEOS`` (CPUs menos um, mínimo um): núcleos que a extração usa; o núcleo 0
  fica para a Mesa quando há mais de um.
"""
from __future__ import annotations

import os
from pathlib import Path

PADROES = {'paginas': 3000, 'megapixels': 150, 'memoria_mb': 2048, 'cpu_s': 7200}
FAIXAS = {'paginas': (1, 1_000_000), 'megapixels': (1, 10_000), 'memoria_mb': (64, 1_048_576),
          'cpu_s': (1, 30 * 24 * 3600), 'nucleos': (1, 4096)}
VARIAVEIS = {'paginas': 'VLADO_EXTRACAO_TETO_PAGINAS', 'megapixels': 'VLADO_EXTRACAO_TETO_MEGAPIXELS',
             'memoria_mb': 'VLADO_EXTRACAO_TETO_MEMORIA_MB', 'cpu_s': 'VLADO_EXTRACAO_TETO_CPU_S',
             'nucleos': 'VLADO_EXTRACAO_NUCLEOS'}
DPI_PAGINA = 300  # the resolution OCR rasterizes a page at
LADO_VISUAL = 2000  # pixels of the longest side of a page image sent to the model
PROFUNDIDADE_FORMULARIOS = 8


def configuracao() -> dict:
    """Tetos from the environment; ValueError names the variable with a bad value."""
    cpus = os.cpu_count() or 1
    padroes = {**PADROES, 'nucleos': max(1, cpus - 1)}
    config = {}
    for chave, variavel in VARIAVEIS.items():
        bruto = (os.environ.get(variavel) or '').strip()
        try:
            valor = int(bruto) if bruto else padroes[chave]
        except ValueError as exc:
            raise ValueError(f'{variavel} deve ser um número inteiro.') from exc
        minimo, maximo = FAIXAS[chave]
        config[chave] = max(minimo, min(maximo, valor))
    config['nucleos'] = min(config['nucleos'], cpus)
    return config


def _mp(pixels) -> str:
    return f'{pixels / 1_000_000:.1f}'.rstrip('0').rstrip('.')


# --- páginas -----------------------------------------------------------------------------------

def paginas_declaradas(reader):
    """The page count the PDF declares (root /Pages /Count), read without walking the page tree."""
    try:
        valor = reader.trailer['/Root'].get_object()['/Pages'].get_object().get('/Count')
        return int(valor) if valor is not None else None
    except Exception:  # noqa: BLE001 - a broken tree is read (and capped) by the normal path
        return None


def teto_paginas(paginas, config=None):
    """Message when ``paginas`` is over the cap, else None."""
    config = config or configuracao()
    if paginas is not None and paginas > config['paginas']:
        return (f'PDF com {paginas} páginas, acima do teto de {config["paginas"]} páginas por arquivo '
                f'(VLADO_EXTRACAO_TETO_PAGINAS). O original está preservado; o texto não foi extraído.')
    return None


# --- pixels ------------------------------------------------------------------------------------

def teto_pixels(largura, altura, o_que, config=None):
    """Message when ``largura`` x ``altura`` pixels is over the cap, else None."""
    config = config or configuracao()
    try:
        pixels = int(largura) * int(altura)
    except (TypeError, ValueError):
        return None
    limite = config['megapixels'] * 1_000_000
    if pixels > limite:
        return (f'{o_que} com {int(largura)} x {int(altura)} pixels ({_mp(pixels)} megapixels), acima do teto '
                f'de {config["megapixels"]} megapixels (VLADO_EXTRACAO_TETO_MEGAPIXELS).')
    return None


def _numero(valor):
    try:
        return float(valor.get_object() if hasattr(valor, 'get_object') else valor)
    except (TypeError, ValueError, AttributeError):
        return None


def _imagens_xobject(recursos, profundidade, vistos):
    """(width, height) of image XObjects in a resources dictionary, forms included (pypdf objects)."""
    try:
        objetos = recursos.get('/XObject') if recursos is not None else None
        objetos = objetos.get_object() if objetos is not None else None
    except Exception:  # noqa: BLE001
        return
    if not objetos:
        return
    for nome in list(objetos.keys()):
        try:
            referencia = objetos.raw_get(nome) if hasattr(objetos, 'raw_get') else objetos[nome]
            chave = getattr(referencia, 'idnum', None)
            objeto = objetos[nome].get_object()
        except Exception:  # noqa: BLE001
            continue
        if chave is not None:
            if chave in vistos:
                continue
            vistos.add(chave)
        subtipo = objeto.get('/Subtype')
        if subtipo == '/Image':
            yield _numero(objeto.get('/Width')), _numero(objeto.get('/Height'))
        elif subtipo == '/Form' and profundidade < PROFUNDIDADE_FORMULARIOS:
            yield from _imagens_xobject(objeto.get('/Resources'), profundidade + 1, vistos)


def _imagens_embutidas(pagina):
    """(width, height) of inline images (BI ... ID ... EI) in the page content."""
    try:
        conteudo = pagina.get_contents()  # decoded by pypdf, within its own output cap
        if conteudo is None or b'BI' not in conteudo.get_data():
            return
        operacoes = conteudo.operations
    except Exception:  # noqa: BLE001 - unreadable content is the extractor's business
        return
    for operandos, operador in operacoes:
        if operador == b'INLINE IMAGE' and isinstance(operandos, dict):
            ajustes = operandos.get('settings', {})
            yield (_numero(ajustes.get('/W', ajustes.get('/Width'))),
                   _numero(ajustes.get('/H', ajustes.get('/Height'))))


def teto_pagina(pagina, numero, config=None):
    """Message when page ``numero`` (a pypdf page) is over the pixel cap at 300 dpi or declares an
    image over it; checked before any render or OCR. None when it is within the caps."""
    config = config or configuracao()
    try:
        caixa = pagina.mediabox
        largura, altura = abs(float(caixa.width)), abs(float(caixa.height))
    except Exception:  # noqa: BLE001
        largura = altura = None
    if largura and altura:
        mensagem = teto_pixels(round(largura * DPI_PAGINA / 72), round(altura * DPI_PAGINA / 72),
                               f'Página {numero} a {DPI_PAGINA} dpi', config)
        if mensagem:
            return mensagem + ' A página não foi enviada ao OCR.'
    try:
        recursos = pagina.get('/Resources')
        recursos = recursos.get_object() if recursos is not None else None
    except Exception:  # noqa: BLE001
        recursos = None
    for origem, imagens in (('Imagem', _imagens_xobject(recursos, 0, set())), ('Imagem embutida', _imagens_embutidas(pagina))):
        for largura_img, altura_img in imagens:
            mensagem = teto_pixels(largura_img, altura_img, f'{origem} na página {numero}', config)
            if mensagem:
                return mensagem + ' A página não foi enviada ao OCR.'
    return None


def paginas_acima_do_teto(pdf: Path, paginas, config=None) -> dict:
    """{page: message} for the pages of ``pdf`` over the pixel caps (pypdf, metadata only)."""
    config = config or configuracao()
    try:
        import pypdf
        reader = pypdf.PdfReader(str(pdf))
        if reader.is_encrypted:
            reader.decrypt('')
        total = len(reader.pages)
    except Exception:  # noqa: BLE001 - the OCR engine reports an unreadable PDF itself
        return {}
    recusadas = {}
    for numero in paginas:
        if 1 <= numero <= total:
            try:
                mensagem = teto_pagina(reader.pages[numero - 1], numero, config)
            except Exception:  # noqa: BLE001
                mensagem = None
            if mensagem:
                recusadas[numero] = mensagem
    return recusadas


def teto_imagem_arquivo(caminho: Path, config=None):
    """Message when a standalone PNG/JPEG declares more pixels than the cap (header only)."""
    config = config or configuracao()
    try:
        from PIL import Image
    except ImportError:
        return None
    anterior = Image.MAX_IMAGE_PIXELS
    try:
        Image.MAX_IMAGE_PIXELS = None  # read the declared size only; our cap decides
        with Image.open(caminho) as imagem:
            largura, altura = imagem.size
    except Exception:  # noqa: BLE001 - Tesseract reports an unreadable image itself
        return None
    finally:
        Image.MAX_IMAGE_PIXELS = anterior
    mensagem = teto_pixels(largura, altura, 'Imagem', config)
    return mensagem + ' A imagem não foi enviada ao OCR.' if mensagem else None


# --- página como imagem (leitura visual da apuração) ---------------------------------------------

def renderizar_png(pdf: Path, numero: int, config=None, lado=LADO_VISUAL) -> bytes:
    """PNG of one PDF page for the model's visual reading, within the pixel caps.

    The page and its declared images are checked first; the render is scaled so the longest
    side has at most ``lado`` pixels (never above zoom 1.5). ValueError with the reason.
    """
    config = config or configuracao()
    try:
        import pypdf
        reader = pypdf.PdfReader(str(pdf))
        if reader.is_encrypted:
            reader.decrypt('')
        declaradas = paginas_declaradas(reader)
        if declaradas is not None and numero > declaradas:
            raise ValueError('Página fora do PDF.')
        total = len(reader.pages)
        if numero > total:
            raise ValueError('Página fora do PDF.')
        mensagem = teto_pagina(reader.pages[numero - 1], numero, config)
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f'PDF ilegível para leitura visual: {type(exc).__name__}.') from exc
    if mensagem:
        raise ValueError(mensagem.replace(' A página não foi enviada ao OCR.', '')
                         + ' Consulte o original na interface.')
    try:
        import fitz
    except ImportError as exc:
        raise ValueError('Leitura visual de PDF exige PyMuPDF opcional. Consulte o original na interface; '
                         'não presuma tabela conferida.') from exc
    with fitz.open(str(pdf)) as documento:
        if numero > len(documento):
            raise ValueError('Página fora do PDF.')
        pagina = documento[numero - 1]
        maior = max(pagina.rect.width, pagina.rect.height) or 1
        zoom = min(1.5, lado / maior)
        return pagina.get_pixmap(matrix=fitz.Matrix(zoom, zoom)).tobytes('png')
