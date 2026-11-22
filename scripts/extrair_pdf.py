"""Extract a PDF to page/line text: native text first, local OCR only for pages without usable text."""
import argparse
from pathlib import Path
from comum import sha256
import ocr
import tetos_extracao as tetos

SEM_TEXTO = '[SEM TEXTO EXTRAIVEL NESTA PAGINA]'
ERRO_TEXTO = '[ERRO DE EXTRACAO NESTA PAGINA]'
# Pages with fewer alphanumeric characters than this (e.g. only a stamped page number) are
# treated as lacking usable native text and become OCR candidates.
MINIMO_ALFANUMERICOS_NATIVO = 10


def _alfanumericos(texto: str) -> int:
    return sum(1 for c in texto if c.isalnum())


def _tentar_ocr(source: Path, candidatas: list, result: dict) -> dict:
    """Run OCR on candidate pages; never raises. Returns {pagina: {'texto'|'erro'}}.

    Pages over the pixel caps (``tetos_extracao``: the page at 300 dpi, or an image it declares)
    are never rendered nor sent to the engine: they get an error with the reason.
    """
    recusadas = tetos.paginas_acima_do_teto(source, candidatas)
    if recusadas:
        result['paginas_acima_do_teto'] = sorted(recusadas)
    lidas = _ocr_das_paginas(source, [n for n in candidatas if n not in recusadas], result)
    return {**lidas, **{numero: {'erro': mensagem} for numero, mensagem in recusadas.items()}}


def _ocr_das_paginas(source: Path, candidatas: list, result: dict) -> dict:
    if not candidatas:
        return {}
    try:
        disponibilidade = ocr.diagnostico()
        if not disponibilidade['disponivel']:
            result['ocr_indisponivel'] = disponibilidade.get('motivo') or 'OCR indisponivel.'
            return {}
        reconhecido = ocr.reconhecer(source, candidatas)
    except ocr.OcrIndisponivel as exc:
        result['ocr_indisponivel'] = str(exc)
        return {}
    except Exception as exc:
        result['ocr_tentado'] = True
        erro = f'{type(exc).__name__}: {str(exc)[:500]}'
        return {numero: {'erro': erro} for numero in candidatas}
    result['ocr_tentado'] = True
    result['ocr_motor'] = {'motor': reconhecido['motor'], 'versoes': reconhecido['versoes'],
                           'idiomas': reconhecido['idiomas'], 'avisos': reconhecido.get('avisos', []),
                           'paginas_giradas_antes': reconhecido.get('paginas_giradas_antes', []),
                           'paginas_tesseract_direto': reconhecido.get('paginas_tesseract_direto', [])}
    return reconhecido['paginas']


def _orientacao_resumo(registro: dict) -> str:
    giro = registro.get('giro_aplicado', 0)
    lida = f'girada {giro} graus' if giro else 'como esta'
    texto_de = f'; texto de {registro["texto_de"]}' if registro.get('texto_de') else ''
    if registro.get('decisao') == 'leitura_dupla':
        original, girada = registro['original']['medida'], registro['girada']['medida']
        medidas = ('sem medida (Tesseract nao gerou o .tsv)' if original is None or girada is None
                   else f'confianca media das palavras {original} como esta e {girada} girada')
        return (f'{lida} (OSD sugeriu {registro["osd_giro"]} com confianca {registro["osd_confianca"]}; '
                f'leitura dupla, {medidas}{texto_de})')
    return f'{lida} (OSD, confianca {registro["osd_confianca"]}{texto_de})'


def _metodo(pypdf_version: str, result: dict) -> str:
    base = f'pypdf {pypdf_version}; extract_text por pagina'
    motor = result.get('ocr_motor')
    if result['paginas_ocr'] and motor:
        versoes = ', '.join(f'{k} {v}' for k, v in motor['versoes'].items() if v)
        nome = motor['motor']
        if nome == 'ocrmypdf':
            # Pages the double reading turned: PyMuPDF turned them in a temporary copy for OCRmyPDF or,
            # if that copy failed, Tesseract read the PyMuPDF render directly instead of OCRmyPDF.
            giradas = [n for n in motor.get('paginas_giradas_antes', []) if n in result['paginas_ocr']]
            diretas = [n for n in motor.get('paginas_tesseract_direto', []) if n in result['paginas_ocr']]
            if giradas:
                nome += ('; paginas ' + ', '.join(map(str, giradas)) + ' giradas pelo PyMuPDF numa copia '
                         'temporaria antes do OCRmyPDF (leitura dupla)')
            if diretas:
                nome += ('; paginas ' + ', '.join(map(str, diretas)) + ' lidas pelo Tesseract direto sobre a '
                         'renderizacao do PyMuPDF, sem o OCRmyPDF')
        return (f'{base}; OCR local ({nome}; {versoes}; idiomas {motor["idiomas"]}) somente nas '
                'paginas sem texto nativo; reconhecimento automatico sujeito a erros; sem correcao editorial.')
    if result['ocr_tentado']:
        return f'{base}; OCR local tentado nas paginas sem texto nativo, sem texto reconhecido; sem correcao editorial.'
    return f'{base}; sem OCR ou correcao editorial.'


def extrair_pdf(source: Path, identifier: str, target: Path, *, ocr_ativo: bool = True) -> dict:
    """Return an explicit extraction outcome; storage failures still abort registration."""
    if target.exists():
        raise FileExistsError('Nao sobrescrever extracao existente; usar nova versao.')
    result = {'estado': 'erro', 'paginas_pdf': None, 'paginas_com_texto': 0,
              'paginas_texto_nativo': [], 'paginas_ocr': [],
              'paginas_sem_texto': [], 'paginas_com_erro': [], 'ocr': False, 'ocr_tentado': False,
              'ocr_motor': None, 'protegido': False, 'paginas_origem': {},
              'conferencia_humana': 'nao_realizada', 'metodo': None}
    # Catch PDF/dependency errors only. Do not disguise a failed write as a readable original.
    try:
        import pypdf
        pypdf_version = pypdf.__version__
        result['metodo'] = f'pypdf {pypdf_version}; extract_text por pagina; sem OCR ou correcao editorial.'
        reader = pypdf.PdfReader(source)
        if reader.is_encrypted and not reader.decrypt(''):
            result['protegido'] = True
            raise ValueError('PDF protegido por senha; texto nao extraido.')
        # The declared count first: a page tree with millions of entries is never walked.
        declaradas = tetos.paginas_declaradas(reader)
        teto = tetos.teto_paginas(declaradas)
        count = None if teto else len(reader.pages)
        teto = teto or tetos.teto_paginas(count)
        if teto:
            result.update(paginas_pdf=count if count is not None else declaradas, mensagem=teto, teto=teto)
            return result
        if count == 0:
            raise ValueError('PDF sem paginas; texto nao extraido.')
        result['paginas_pdf'] = count
    except ImportError:
        result['mensagem'] = 'pypdf indisponivel neste Python; instalar as dependencias de requirements.txt ou usar o runtime do Codex.'
        return result
    except Exception as exc:
        result['mensagem'] = f'{type(exc).__name__}: {str(exc)[:1000]}'
        return result

    native, native_errors = {}, {}
    for number in range(1, count + 1):
        try:
            native[number] = reader.pages[number - 1].extract_text() or ''
        except Exception as exc:
            native[number] = ''
            native_errors[number] = f'{type(exc).__name__}: {str(exc)[:1000]}'
        ocr._avisar('texto', number, count)  # progress for the extraction queue (ocr.execucao); no-op outside it
    candidates = [n for n in range(1, count + 1)
                  if _alfanumericos(native[n]) < MINIMO_ALFANUMERICOS_NATIVO]
    recognized = _tentar_ocr(source, candidates, result) if candidates and ocr_ativo else {}
    if candidates and not ocr_ativo:
        result['ocr_indisponivel'] = 'OCR nao solicitado para esta extracao.'

    body = []
    for number in range(1, count + 1):
        body.extend([f'## {identifier} - pagina PDF {number}', ''])
        outcome = recognized.get(number, {})
        ocr_text = outcome.get('texto', '')
        use_ocr = _alfanumericos(ocr_text) > _alfanumericos(native[number])
        if use_ocr:
            lines, origin = ocr_text.splitlines(), 'ocr'
            if outcome.get('orientacao'):
                # Which way the page was read and the measure that decided it (ocr._orientar_pagina).
                result.setdefault('ocr_orientacao', {})[str(number)] = outcome['orientacao']
        elif native[number].strip():
            lines, origin = native[number].splitlines(), 'texto_nativo'
        else:
            lines, origin = [], None
        if outcome.get('aviso_orientacao'):
            # The orientation check failed (e.g. timeout): the page kept the OCRmyPDF reading unchecked.
            result.setdefault('ocr_avisos_orientacao', {})[str(number)] = outcome['aviso_orientacao']
        if origin:
            result['paginas_com_texto'] += 1
            result['paginas_texto_nativo' if origin == 'texto_nativo' else 'paginas_ocr'].append(number)
            result['paginas_origem'][str(number)] = origin
            body.extend(f'[L{line:04d}] {content}' for line, content in enumerate(lines, 1))
        elif number in native_errors or 'erro' in outcome:
            stage = 'extracao' if number in native_errors else 'ocr'
            result['paginas_com_erro'].append({'pagina_pdf': number, 'etapa': stage,
                                              'erro': native_errors.get(number) or outcome['erro']})
            body.append(ERRO_TEXTO)
        else:
            result['paginas_sem_texto'].append(number)
            body.append(SEM_TEXTO)
        body.append('')
    result['ocr'] = bool(result['paginas_ocr'])
    result['metodo'] = _metodo(pypdf_version, result)
    if result['paginas_com_erro']:
        result['estado'] = 'parcial' if result['paginas_com_texto'] else 'erro'
    elif result['paginas_sem_texto']:
        result['estado'] = 'parcial' if result['paginas_com_texto'] else 'sem_texto'
    else:
        result['estado'] = 'extraido'
    origins = '; '.join(f'{n}={o}' for n, o in result['paginas_origem'].items()) or 'nenhuma pagina com texto'
    header = [f'# {identifier} - copia textual de trabalho', '',
              f'Original: {source.name}', f'SHA-256 do PDF: {sha256(source)}',
              f'Metodo: {result["metodo"]}',
              f'Origem do texto por pagina (texto_nativo ou ocr): {origins}',
              'Pagina = posicao fisica no PDF. Linhas = copia de trabalho, nao o original.']
    if result['paginas_ocr']:
        header.append('Paginas com origem ocr foram reconhecidas automaticamente e podem conter erros; conferir o original.')
    if result.get('ocr_orientacao'):
        header.append('Orientacao do OCR por pagina: ' + '; '.join(
            f'{n}={_orientacao_resumo(o)}' for n, o in result['ocr_orientacao'].items()))
    if result.get('ocr_avisos_orientacao'):
        header.append('Aviso do OCR por pagina: ' + '; '.join(
            f'{n}={aviso}' for n, aviso in result['ocr_avisos_orientacao'].items()))
    header.append('')
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write('\n'.join(header + body))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdf', required=True)
    parser.add_argument('--id', required=True)
    parser.add_argument('--saida', required=True)
    parser.add_argument('--sem-ocr', action='store_true', help='Nao aplicar OCR as paginas sem texto nativo.')
    args = parser.parse_args()
    source, target = Path(args.pdf), Path(args.saida)
    import json
    result = extrair_pdf(source, args.id, target, ocr_ativo=not args.sem_ocr)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result['estado'] == 'erro' else 0


if __name__ == '__main__':
    raise SystemExit(main())
