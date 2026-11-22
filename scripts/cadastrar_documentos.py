"""Register each explicitly supplied batch before a question; never start a round.

PDFs, DOCX and XLSX get a located working copy (derivative) recorded with hash, origin
and method in the manifest. Standalone images get OCR only with the explicit
`--ocr-imagens` option (off by default). No model calls, no network.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time
import uuid

from comum import ROOT, arquivos_do_corpus, dentro, escrever_json, ler_json, sha256, pasta_preparacao
from criar_caso import EXTENSOES
import ocr
from extrair_office import EXTENSOES as EXTENSOES_OFFICE, EXTENSOES_MACRO, extrair_office, formato_office
from extrair_pdf import extrair_pdf
from lixeira import conferir_disponivel
import fontes_web as fontes_web_mod
import trava_cadastro

# Macro-enabled Office files are kept as originals with a readable pending extraction.
ACEITOS = EXTENSOES | EXTENSOES_MACRO
OFFICE = set(EXTENSOES_OFFICE) | EXTENSOES_MACRO


def _trava(root, **opcoes):
    """Project cadastro lock, shared by every process (server and CLI): see ``trava_cadastro``.

    Waits up to ``trava_cadastro.ESPERA`` seconds when busy; a holder that died is recognized
    and its half-done staging removed. Options: ``espera``, ``operacao``, ``cancelar``.
    """
    return trava_cadastro.trava(root, **opcoes)


def _atomico(path, content):
    """Publish a metadata file without exposing partial JSON."""
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temp = Path(stream.name)
        stream.write(content)
    try:
        # Windows refuses os.replace while another writer or an antivirus scan holds the
        # destination for a moment; retry briefly instead of failing the whole operation.
        for tentativa in range(40):
            try:
                os.replace(temp, path)
                break
            except PermissionError:
                if tentativa == 39:
                    raise
                time.sleep(0.025)
    finally:
        temp.unlink(missing_ok=True)


def _bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def inventario(root, caso):
    if not isinstance(caso, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', caso):
        raise ValueError('Identificador de caso inválido.')
    conferir_disponivel(root, caso)
    manifest = ler_json(dentro(root, f'casos/{caso}/manifesto.json'))
    if manifest['caso_id'] != caso:
        raise ValueError('Manifesto pertence a outro caso.')
    list(arquivos_do_corpus(root, manifest))
    return {'caso_id': caso, 'titulo': manifest['titulo'], 'corpus_id': manifest['corpus_id'],
            'total_documentos': len(manifest['documentos']),
            'documentos': [{'id': d['id'], 'nome_recebido': d.get('nome_recebido', Path(d['arquivo']).name),
                            'arquivo': d['arquivo'], 'sha256': d['sha256'], 'bytes': d.get('bytes'),
                            'derivados': len(d.get('derivados', [])),
                            'extracao_pdf': d.get('extracao_pdf'),
                            'extracao_office': d.get('extracao_office'),
                            'ocr_imagem': d.get('ocr_imagem')} for d in manifest['documentos']],
            'recibos': manifest.get('registros_cadastro', []),
            'fontes_web': fontes_web_mod.modo_do_caso(manifest),
            'capturas_web': len(manifest.get('capturas_web', [])),
            'estado': 'cadastrado_aguardando_pergunta'}


def validar_pedido(caso, natureza, sources, novo, modo_fontes, dominio_permitido):
    """Checks of a cadastro request that need neither files nor the case; returns the web mode."""
    if not isinstance(caso, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', caso):
        raise ValueError('ID do caso: letras minúsculas, números, hífen ou underscore; até 64 caracteres.')
    if natureza not in ('publicos', 'sinteticos', 'nao_informada'):
        raise ValueError('Natureza documental inválida.')
    if not sources:
        raise ValueError('Envie pelo menos um arquivo.')
    if not novo and (modo_fontes or dominio_permitido):
        raise ValueError('O modo de fontes (somente documentos ou documentos + web) só é escolhido na criação do caso.')
    return fontes_web_mod.definir_modo(modo_fontes, dominio_permitido) if novo else None


def cadastrar(root, caso, sources, *, titulo=None, natureza='nao_informada', novo=False, ocr_imagens=False,
              modo_fontes=None, dominio_permitido=None):
    """Register a batch. `ocr_imagens=True` explicitly asks for local OCR of standalone images.

    `modo_fontes`/`dominio_permitido` are accepted only with `novo=True` (source mode is chosen at creation).
    Extraction and OCR run in this process before the cadastro lock is taken; only the publication
    holds it. The Mesa sends its uploads through ``fila_extracao`` instead (separate processes)."""
    fontes_web = validar_pedido(caso, natureza, sources, novo, modo_fontes, dominio_permitido)
    plano = planejar(root, caso, sources, titulo=titulo, natureza=natureza, novo=novo,
                     ocr_imagens=bool(ocr_imagens), fontes_web=fontes_web)
    return executar_plano(root, plano)


def plano_preparar_pdfs(root, caso):
    """Plan to enrich this case's preserved PDFs; never inspect inactive cases or old rounds."""
    if not isinstance(caso, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', caso):
        raise ValueError('Identificador de caso inválido.')
    conferir_disponivel(root, caso)
    manifest = ler_json(dentro(root, f'casos/{caso}/manifesto.json'))
    sources = [dentro(root, d['arquivo']) for d in manifest['documentos']
               if Path(d['arquivo']).suffix.lower() == '.pdf']
    if not sources:
        raise ValueError('Este caso não tem PDFs cadastrados para preparar.')
    return planejar(root, caso, sources, natureza=manifest['natureza_informada'],
                    operacao='preparacao_pdfs_cadastrados')


def preparar_pdfs(root, caso):
    """Enrich this case's preserved PDFs (OCR included) with a new corpus version."""
    return executar_plano(root, plano_preparar_pdfs(root, caso))


def executar_plano(root, plano):
    """Copy, extract (in this process, outside the lock) and publish (under the lock) a plan."""
    with tempfile.TemporaryDirectory(prefix='vlado_cadastro_') as pasta:
        trabalho = Path(pasta)
        preparar_copias(plano, trabalho)
        resultados = {item['indice']: extrair_item(tarefa(root, plano, item, trabalho), base=trabalho)
                      for item in plano['itens'] if item['extrair']}
        operacao = 'preparacao_pdfs' if plano['operacao'] == 'preparacao_pdfs_cadastrados' else 'cadastro'
        with _trava(root, operacao=operacao):
            # Copies, not hard links: a temporary folder carries a private ACL on Windows.
            return publicar(root, plano, trabalho, resultados, ligar=False)


def _precisa_reprocessar_ocr(info):
    """A prepared PDF still lacks OCR it could now receive (never attempted, or pages that failed)."""
    if not info or info.get('estado') == 'erro' or not ocr.diagnostico()['disponivel']:
        return False
    falhou = any(p.get('etapa') == 'ocr' for p in info.get('paginas_com_erro', []))
    return falhou or (bool(info.get('paginas_sem_texto')) and not info.get('ocr_tentado'))


def _resumo_pdfs(pdfs, processed):
    infos = [d['extracao_pdf'] for d in pdfs.values()]
    return {'pdfs': len(pdfs), 'processados_agora': processed,
            **{state: sum(i['estado'] == state for i in infos) for state in ('extraido', 'parcial', 'sem_texto', 'erro')},
            'paginas_texto_nativo': sum(len(i['paginas_texto_nativo']) if 'paginas_texto_nativo' in i
                                        else i.get('paginas_com_texto', 0) for i in infos),
            'paginas_ocr': sum(len(i.get('paginas_ocr', [])) for i in infos),
            'paginas_sem_texto': sum(len(i.get('paginas_sem_texto', [])) for i in infos),
            'paginas_com_erro': sum(len(i.get('paginas_com_erro', [])) for i in infos),
            'protegidos': sum(bool(i.get('protegido')) for i in infos)}


def _resumo_office(offices, processed):
    infos = [d['extracao_office'] for d in offices.values()]

    def total(key):
        return sum(i.get('contagens', {}).get(key, 0) for i in infos)
    refused = {}
    for info in infos:
        if info.get('recusa'):
            refused[info['recusa']] = refused.get(info['recusa'], 0) + 1
    return {'documentos': len(offices), 'processados_agora': processed,
            'docx': sum(i['formato'] == 'docx' for i in infos), 'xlsx': sum(i['formato'] == 'xlsx' for i in infos),
            **{state: sum(i['estado'] == state for i in infos) for state in ('extraido', 'parcial', 'sem_texto', 'erro')},
            'paragrafos': total('paragrafos'), 'tabelas': total('tabelas'), 'celulas_tabela': total('celulas_tabela'),
            'abas': total('abas'), 'celulas': total('celulas'), 'formulas': total('formulas'),
            'falhas': sum(len(i.get('falhas', [])) for i in infos), 'recusados': refused}


def _resumo_imagens(images, processed, requested):
    infos = [d.get('ocr_imagem') for d in images.values()]
    summary = {'solicitado': requested, 'imagens': len(images), 'processadas_agora': processed,
               **{state: sum(bool(i) and i['estado'] == state for i in infos)
                  for state in ('extraido', 'sem_texto', 'pendente', 'erro')},
               'sem_ocr': sum(not i for i in infos)}
    if summary['extraido']:
        summary['aviso'] = ocr.AVISO_OCR_IMAGEM
    return summary


def _substituir_derivado(doc, entry):
    """A new version replaces the prior working copy of the same type; old rounds keep theirs."""
    old = [d for d in doc.get('derivados', []) if d.get('tipo') == entry['tipo']]
    doc['derivados'] = [d for d in doc.get('derivados', []) if d.get('tipo') != entry['tipo']]
    if old:
        entry['substitui_sha256'] = old[-1]['sha256']
    doc['derivados'].append(entry)


def _tipo(sufixo):
    sufixo = sufixo.lower()
    if sufixo == '.pdf':
        return 'pdf'
    if sufixo in OFFICE:
        return 'office'
    if sufixo in ocr.EXTENSOES_IMAGEM:
        return 'imagem'
    return 'texto'


def _radical(stem):
    return ''.join(c if c.isalnum() or c in '-_' else '_' for c in stem)[:80] or 'documento'


def _precisa_extrair(tipo, doc, operacao, ocr_imagens):
    """Whether the working copy of a file is (re)made: the rules ``publicar`` applies again."""
    if tipo == 'pdf':
        # A repeated successful/empty/partial extraction is not silently replaced.
        # Re-sending an errored PDF explicitly permits another attempt in a new batch.
        existing = doc.get('extracao_pdf') if doc else None
        reprocess = operacao == 'preparacao_pdfs_cadastrados' and _precisa_reprocessar_ocr(existing)
        return not (existing and existing['estado'] != 'erro' and not reprocess)
    if tipo == 'office':
        # Same rule as PDF: a readable result is kept; re-sending a refused/failed file retries it.
        existing = doc.get('extracao_office') if doc else None
        return not (existing and existing['estado'] != 'erro')
    if tipo == 'imagem' and ocr_imagens:
        # OCR of standalone images only on explicit request; pending/failed attempts may be retried.
        existing = doc.get('ocr_imagem') if doc else None
        return not (existing and existing['estado'] not in ('pendente', 'erro'))
    return False


def _caso_vazio(destination, *, remover=False):
    """No case there: the folder is absent, or only the empty ``cadastros/`` that an interrupted
    publication of a new case leaves behind (it has no manifest and is in no catalog)."""
    if not destination.exists():
        return True
    try:
        itens = list(destination.iterdir())
    except OSError:
        return False
    sobra = itens == [] or (len(itens) == 1 and itens[0].name == 'cadastros' and itens[0].is_dir()
                            and not itens[0].is_symlink() and not any(itens[0].iterdir()))
    if sobra and remover:
        for item in itens:
            item.rmdir()
        destination.rmdir()
    return sobra


def _contexto(root, caso, new, title, *, remover_sobra=False):
    """Catalog, catalog entry and manifest of the case, with the checks of every batch."""
    conferir_disponivel(root, caso)
    destination = dentro(root, f'casos/{caso}')
    catalog_path = dentro(root, 'casos/catalogo.json')
    catalog_before = catalog_path.read_bytes() if catalog_path.exists() else None
    catalog = ler_json(catalog_path) if catalog_before else {'casos': []}
    entry = next((c for c in catalog['casos'] if c['id'] == caso), None)
    manifest_path = dentro(root, f'casos/{caso}/manifesto.json')
    manifest_before = manifest = None
    if new:
        if entry or not _caso_vazio(destination, remover=remover_sobra):
            raise ValueError('Caso já existe; selecione-o para acrescentar um lote.')
        if not isinstance(title, str) or not title.strip():
            raise ValueError('Informe o título do novo caso.')
    else:
        if not entry or not destination.is_dir():
            raise ValueError('Caso inexistente; não cadastrar em outro caso automaticamente.')
        manifest_before = manifest_path.read_bytes()
        manifest = ler_json(manifest_path)
        if manifest.get('caso_id') != caso or entry['manifesto'] != f'casos/{caso}/manifesto.json':
            raise ValueError('Catálogo e manifesto não correspondem ao caso.')
    return {'destination': destination, 'catalog_path': catalog_path, 'catalog_before': catalog_before,
            'catalog': catalog, 'entry': entry, 'manifest_path': manifest_path,
            'manifest_before': manifest_before, 'manifest': manifest}


def planejar(root, caso, sources, *, titulo=None, natureza='nao_informada', novo=False,
             operacao='recepcao_documentos', ocr_imagens=False, fontes_web=None):
    """Check a batch and decide what to extract, without the cadastro lock. JSON-serializable.

    Same checks and messages as before (formats, limit, case); ``publicar`` repeats them under
    the lock against the manifest of that moment, so a plan never publishes a stale decision.
    Each file gets a provisional identifier for its working copy, replaced by the final one
    (D001, D002...) when it is published.
    """
    ctx = _contexto(root, caso, novo, titulo)
    manifest = ctx['manifest']
    if manifest is not None:
        list(arquivos_do_corpus(root, manifest))
    known = {d['sha256']: d for d in manifest['documentos']} if manifest else {}
    vistos, itens = set(), []
    for indice, item in enumerate(sources):
        source = Path(item).resolve()
        if not source.is_file() or source.suffix.lower() not in ACEITOS:
            raise ValueError(f'Lote não cadastrado: arquivo ausente ou formato não aceito: {source.name}. Nenhum arquivo deste lote foi confirmado.')
        digest = sha256(source)
        doc, primeira = known.get(digest), digest not in vistos
        vistos.add(digest)
        tipo = _tipo(source.suffix)
        itens.append({'indice': indice, 'nome': source.name, 'origem': str(source), 'sha256': digest,
                      'bytes': source.stat().st_size, 'sufixo': source.suffix.lower(),
                      'radical': _radical(source.stem), 'tipo': tipo,
                      'novo': doc is None and primeira,
                      'extrair': primeira and _precisa_extrair(tipo, doc, operacao, ocr_imagens),
                      'leitura': doc['arquivo'] if doc else None, 'copia': None,
                      'provisorio': 'PROVISORIO' + uuid.uuid4().hex.upper()})
    maximum = ler_json(root / 'configuracao.json')['maximo_documentos_inicial']
    if len(known) + sum(item['novo'] for item in itens) > maximum:
        raise ValueError(f'Lote não cadastrado: ultrapassaria o limite de {maximum} documentos. Nenhum arquivo deste lote foi confirmado.')
    return {'esquema': 1, 'lote': uuid.uuid4().hex, 'caso': caso, 'novo': bool(novo),
            'titulo': titulo, 'natureza': natureza, 'operacao': operacao, 'ocr_imagens': bool(ocr_imagens),
            'fontes_web': fontes_web, 'recebido_em_utc': datetime.now(timezone.utc).isoformat(),
            'manifesto_sha256': hashlib.sha256(ctx['manifest_before']).hexdigest() if ctx['manifest_before'] else None,
            'itens': itens}


def preparar_copias(plano, trabalho, *, mover=False):
    """Stage each new original in ``trabalho`` (named with its provisional identifier) and check it.

    ``mover``: the source already lives in ``trabalho`` (a Mesa upload in the queue): rename it.
    """
    trabalho = Path(trabalho)
    for item in plano['itens']:
        if not item['novo']:
            continue
        relativo = f'originais/{item["indice"]}/{item["provisorio"]}_{item["radical"]}{item["sufixo"]}'
        target = trabalho / relativo
        target.parent.mkdir(parents=True, exist_ok=True)
        if mover:
            os.replace(item['origem'], target)
        else:
            shutil.copyfile(item['origem'], target)
        if sha256(target) != item['sha256']:
            raise ValueError('Lote não cadastrado: cópia divergente; nenhum arquivo confirmado.')
        item['copia'] = relativo


def tarefa(root, plano, item, trabalho):
    """What the extraction of one file needs (paths only; it never reads the manifest)."""
    origem = Path(trabalho) / item['copia'] if item['copia'] else dentro(root, item['leitura'])
    tipo = item['tipo']
    sufixo = Path(item['leitura']).suffix if item['leitura'] else item['sufixo']
    nome = {'pdf': 'texto_pdf', 'imagem': 'texto_ocr'}.get(tipo) or f'texto_{formato_office(sufixo)}'
    destino = Path(trabalho) / f'derivados/{item["indice"]}/{item["provisorio"]}_{nome}.md'
    return {'lote': plano['lote'], 'indice': item['indice'], 'tipo': tipo, 'origem': str(origem),
            'destino': str(destino), 'identificador': item['provisorio']}


def extrair_item(tarefa, *, base=None, paralelo=None, progresso=None):
    """Make the working copy of one file: the only extraction step, in whatever process runs it.

    Runs in the command line's own process, in a thread of the Mesa (local queue) or in
    ``trabalhador_extracao`` (separate process). Never touches the manifest or the lock.
    Returns ``{'resultado': outcome, 'derivado': path of the copy relative to base, or None}``.
    """
    origem, destino = Path(tarefa['origem']), Path(tarefa['destino'])
    destino.parent.mkdir(parents=True, exist_ok=True)
    with ocr.execucao(paralelo=paralelo, progresso=progresso):
        if tarefa['tipo'] == 'pdf':
            resultado = extrair_pdf(origem, tarefa['identificador'], destino)
        elif tarefa['tipo'] == 'office':
            resultado = extrair_office(origem, tarefa['identificador'], destino)
        elif tarefa['tipo'] == 'imagem':
            resultado = ocr.ocr_imagem(origem, tarefa['identificador'], destino)
        else:
            raise ValueError('Tipo de extração desconhecido.')
    derivado = None
    if destino.is_file():
        derivado = destino.relative_to(base).as_posix() if base else str(destino)
    return {'resultado': resultado, 'derivado': derivado}


def resultado_sem_extracao(tipo, sufixo, mensagem):
    """Outcome recorded when a file's extraction could not run (the original stays preserved)."""
    if tipo == 'pdf':
        return {'estado': 'erro', 'paginas_pdf': None, 'paginas_com_texto': 0, 'paginas_texto_nativo': [],
                'paginas_ocr': [], 'paginas_sem_texto': [], 'paginas_com_erro': [], 'ocr': False,
                'ocr_tentado': False, 'ocr_motor': None, 'protegido': False, 'paginas_origem': {},
                'conferencia_humana': 'nao_realizada', 'metodo': None, 'mensagem': mensagem}
    if tipo == 'office':
        from extrair_office import _resultado_base
        return {**_resultado_base(formato_office(sufixo)), 'mensagem': mensagem}
    return {'estado': 'erro', 'origem': 'ocr', 'motor': None, 'versoes': {}, 'idiomas': None, 'linhas': 0,
            'metodo': None, 'mensagem': mensagem, 'avisos': [], 'aviso_conferencia': ocr.AVISO_OCR_IMAGEM,
            'conferencia_humana': 'nao_realizada'}


def _trazer(origem, destino, ligar):
    """Put a staged file in the batch: hard link inside the same volume, else a copy."""
    if ligar:
        try:
            os.link(origem, destino)
            return
        except OSError:
            pass
    shutil.copyfile(origem, destino)


def _extracao(item, resultados, trabalho, tipo, sufixo, identifier):
    """(outcome, derivative text) for a document; the provisional identifier becomes the final one."""
    if item is None or item['indice'] not in resultados:
        # The manifest changed during the processing (another batch, a reprocessing) in a way
        # the plan did not foresee: register the original and say why its copy is missing.
        return resultado_sem_extracao(tipo, sufixo, 'Extração não executada neste lote: o acervo mudou durante o '
                                      'processamento. O original está preservado; envie o arquivo de novo.'), None
    obtido = resultados[item['indice']]
    resultado = json.loads(json.dumps(obtido['resultado'], ensure_ascii=False).replace(item['provisorio'], identifier))
    texto = None
    if obtido.get('derivado'):
        # Bytes, not text: the copy keeps exactly the bytes the extractor wrote.
        texto = (Path(trabalho) / obtido['derivado']).read_bytes().replace(item['provisorio'].encode('ascii'),
                                                                           identifier.encode('ascii'))
    return resultado, texto


def _gravar_derivado(target, dados):
    target.parent.mkdir(exist_ok=True)
    with target.open('xb') as stream:
        stream.write(dados)


def publicar(root, plano, trabalho, resultados, *, ligar=False):
    """Publish a planned batch; the caller holds the cadastro lock. All of it or none.

    New or duplicate, final IDs and whether a document takes the working copy made for it are
    decided here, against the manifest of this moment, with the same rules as always: a batch
    planned while another one was published stays consistent. ``resultados[indice]`` are the
    working copies made outside the lock (``extrair_item``); ``ligar`` hard-links the staged
    files into the batch (queue, same volume) instead of copying them.
    """
    caso, new, nature, operacao = plano['caso'], plano['novo'], plano['natureza'], plano['operacao']
    ctx = _contexto(root, caso, new, plano['titulo'], remover_sobra=True)
    destination, catalog_path, catalog_before = ctx['destination'], ctx['catalog_path'], ctx['catalog_before']
    catalog, entry, manifest_path, manifest_before = ctx['catalog'], ctx['entry'], ctx['manifest_path'], ctx['manifest_before']
    if new:
        manifest = {'versao': '1.0.0', 'caso_id': caso, 'titulo': plano['titulo'].strip(),
                    'natureza_informada': nature, 'corpus_id': f'{caso}_v1',
                    'fontes_web': plano.get('fontes_web') or fontes_web_mod.definir_modo(),
                    'estado': 'preparado_sem_piloto_de_apuracao',
                    'protocolo': {'piloto_estabilizado': False, 'teste_principal_autorizado': False},
                    'documentos': [], 'registros_cadastro': []}
    else:
        manifest = ctx['manifest']
        if hashlib.sha256(manifest_before).hexdigest() != plano.get('manifesto_sha256'):
            list(arquivos_do_corpus(root, manifest))  # changed since the plan: check the corpus again
    previous = deepcopy(manifest)
    known = {d['sha256']: d for d in manifest['documentos']}
    used = {d['id'] for d in manifest['documentos']}
    batch = plano['lote']
    prefix = f'casos/{caso}/cadastros/{batch}'
    incoming, receipts, fontes = [], [], {}
    pdfs, offices, images = {}, {}, {}
    for item in plano['itens']:
        digest = item['sha256']
        if digest in known:
            doc, status = known[digest], 'duplicado'
        else:
            if not item.get('copia'):
                raise ValueError('Lote não cadastrado: o acervo mudou durante o processamento; envie os arquivos de novo.')
            number = 1
            while f'D{number:03d}' in used:
                number += 1
            identifier = f'D{number:03d}'
            used.add(identifier)
            doc = {'id': identifier, 'arquivo': f'{prefix}/originais/{identifier}_{item["radical"]}{item["sufixo"]}',
                   'sha256': digest, 'bytes': item['bytes'], 'nome_recebido': item['nome'],
                   'origem_informada': None, 'natureza_informada': nature, 'paginas_pdf': None, 'derivados': []}
            incoming.append((item, doc))
            manifest['documentos'].append(doc)
            known[digest] = doc
            status = 'cadastrado'
        receipts.append({'nome_recebido': doc.get('nome_recebido', item['nome']) if operacao == 'preparacao_pdfs_cadastrados' else item['nome'],
                         'documento_id': doc['id'], 'sha256': digest,
                         'bytes': item['bytes'], 'estado': status})
        if item['indice'] in resultados:
            fontes.setdefault(doc['id'], item)  # the item whose working copy this document may take
        if item['tipo'] == 'pdf':
            pdfs[doc['id']] = doc
        elif item['tipo'] == 'office':
            offices[doc['id']] = doc
        elif item['tipo'] == 'imagem':
            images[doc['id']] = doc
    maximum = ler_json(root / 'configuracao.json')['maximo_documentos_inicial']
    if len(manifest['documentos']) > maximum:
        raise ValueError(f'Lote não cadastrado: ultrapassaria o limite de {maximum} documentos. Nenhum arquivo deste lote foi confirmado.')
    with pasta_preparacao(root / 'casos', '.lote_') as temp:
        work = Path(temp) / 'lote'
        work.mkdir()
        for item, doc in incoming:
            target = work / 'originais' / Path(doc['arquivo']).name
            target.parent.mkdir(exist_ok=True)
            _trazer(Path(trabalho) / item['copia'], target, ligar)
            if sha256(target) != doc['sha256']:
                raise ValueError('Lote não cadastrado: cópia divergente; nenhum arquivo confirmado.')
        processed = 0
        for identifier, doc in pdfs.items():
            existing = doc.get('extracao_pdf')
            reprocess = operacao == 'preparacao_pdfs_cadastrados' and _precisa_reprocessar_ocr(existing)
            if existing and existing['estado'] != 'erro' and not reprocess:
                continue
            doc['extracao_pdf'], texto = _extracao(fontes.get(identifier), resultados, trabalho, 'pdf', '.pdf', identifier)
            doc['paginas_pdf'] = doc['extracao_pdf']['paginas_pdf']
            if texto is not None:
                target = work / 'derivados' / f'{identifier}_texto_pdf.md'
                _gravar_derivado(target, texto)
                _substituir_derivado(doc, {'arquivo': f'{prefix}/derivados/{target.name}', 'sha256': sha256(target),
                                           'tipo': 'texto_extraido_pdf', 'origem_sha256': doc['sha256'],
                                           'metodo': doc['extracao_pdf']['metodo'],
                                           'paginas_origem': doc['extracao_pdf']['paginas_origem']})
            processed += 1
        office_processed = 0
        for identifier, doc in offices.items():
            existing = doc.get('extracao_office')
            if existing and existing['estado'] != 'erro':
                continue
            sufixo = Path(doc['arquivo']).suffix
            kind = formato_office(sufixo)
            doc['extracao_office'], texto = _extracao(fontes.get(identifier), resultados, trabalho, 'office', sufixo, identifier)
            if texto is not None:
                target = work / 'derivados' / f'{identifier}_texto_{kind}.md'
                _gravar_derivado(target, texto)
                info = doc['extracao_office']
                _substituir_derivado(doc, {'arquivo': f'{prefix}/derivados/{target.name}', 'sha256': sha256(target),
                                           'tipo': f'texto_extraido_{kind}', 'origem': info['origem'],
                                           'versao_extrator': info['versao_extrator'],
                                           'origem_sha256': doc['sha256'], 'metodo': info['metodo']})
            office_processed += 1
        image_processed = 0
        ocr_imagens = plano['ocr_imagens']
        for identifier, doc in (images.items() if ocr_imagens else ()):
            existing = doc.get('ocr_imagem')
            if existing and existing['estado'] not in ('pendente', 'erro'):
                continue
            doc['ocr_imagem'], texto = _extracao(fontes.get(identifier), resultados, trabalho, 'imagem', '.png', identifier)
            if texto is not None:
                target = work / 'derivados' / f'{identifier}_texto_ocr.md'
                _gravar_derivado(target, texto)
                info = doc['ocr_imagem']
                _substituir_derivado(doc, {'arquivo': f'{prefix}/derivados/{target.name}', 'sha256': sha256(target),
                                           'tipo': 'texto_ocr_imagem', 'origem': 'ocr',
                                           'origem_sha256': doc['sha256'], 'metodo': info['metodo'],
                                           'motor': info['motor'], 'versoes': info['versoes'],
                                           'idiomas': info['idiomas'], 'aviso': ocr.AVISO_OCR_IMAGEM})
            image_processed += 1
        changed = manifest['documentos'] != previous['documentos']
        if changed:
            suffix = re.fullmatch(re.escape(caso) + r'_v([0-9]+)', previous['corpus_id'])
            previous_revision = max(previous.get('revisao_cadastro', 1), int(suffix[1]) if suffix else 1)
            revision = 1 if new else previous_revision + 1
            manifest.update(corpus_id=f'{caso}_v{revision}', revisao_cadastro=revision,
                            protocolo={'piloto_estabilizado': False, 'teste_principal_autorizado': False})
            if manifest['natureza_informada'] != nature:
                manifest['natureza_informada'] = 'nao_informada'
        for item in receipts:
            doc = known[item['sha256']]
            if doc['id'] in pdfs:
                item['extracao_pdf'] = deepcopy(doc['extracao_pdf'])
                item['derivados'] = deepcopy(doc['derivados'])
            elif doc['id'] in offices:
                item['extracao_office'] = deepcopy(doc['extracao_office'])
                item['derivados'] = deepcopy(doc['derivados'])
            elif doc['id'] in images and doc.get('ocr_imagem'):
                item['ocr_imagem'] = deepcopy(doc['ocr_imagem'])
                item['derivados'] = deepcopy(doc['derivados'])
        summary = _resumo_pdfs(pdfs, processed)
        receipt = {'lote_id': batch, 'caso_id': caso, 'corpus_id': manifest['corpus_id'],
                   'operacao': operacao, 'recebido_em_utc': datetime.now(timezone.utc).isoformat(),
                   'recebidos': len(receipts), 'novos': len(incoming),
                   'duplicados': len(receipts) - len(incoming), 'total_documentos': len(manifest['documentos']),
                   'arquivos': receipts, 'extracao_pdf_resumo': summary,
                   'extracao_office_resumo': _resumo_office(offices, office_processed),
                   'ocr_imagens_resumo': _resumo_imagens(images, image_processed, ocr_imagens),
                   'estado': 'cadastrado_aguardando_pergunta'}
        escrever_json(work / 'recibo.json', receipt, exclusivo=True)
        receipt_record = {'arquivo': f'{prefix}/recibo.json', 'sha256': sha256(work / 'recibo.json')}
        manifest.setdefault('registros_cadastro', []).append(receipt_record)
        if manifest_before:
            (work / 'manifesto_anterior.json').write_bytes(manifest_before)
        escrever_json(work / 'manifesto_cadastrado.json', manifest, exclusivo=True)
        batch_path = dentro(root, prefix)
        batch_path.parent.mkdir(parents=True, exist_ok=True)
        published = False
        try:
            work.rename(batch_path)
            published = True
            _atomico(manifest_path, _bytes(manifest))
            if new:
                catalog['casos'].append({'id': caso, 'titulo': manifest['titulo'],
                                        'manifesto': f'casos/{caso}/manifesto.json',
                                        'exemplo': False, 'documentos': len(manifest['documentos'])})
            else:
                entry['documentos'] = len(manifest['documentos'])
            _atomico(catalog_path, _bytes(catalog))
        except BaseException:
            # Also on Ctrl+C or SystemExit in the middle of publishing: all of the batch or none.
            if manifest_before is not None:
                _atomico(manifest_path, manifest_before)
            else:
                manifest_path.unlink(missing_ok=True)
            if catalog_before is not None:
                _atomico(catalog_path, catalog_before)
            else:
                catalog_path.unlink(missing_ok=True)
            if published:
                batch_path.rename(work)
            if new:
                batch_path.parent.rmdir()
                destination.rmdir()
            raise
    return {**receipt, 'arquivo_recibo': receipt_record['arquivo'], 'inventario': inventario(root, caso)}


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--caso', required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--documentos', nargs='+')
    mode.add_argument('--preparar-pdfs', action='store_true',
                      help='Preparar os PDFs já preservados no caso, sem reenviar nem criar rodada.')
    parser.add_argument('--novo', action='store_true')
    parser.add_argument('--titulo')
    parser.add_argument('--natureza', choices=['publicos', 'sinteticos', 'nao_informada'], default='nao_informada')
    parser.add_argument('--ocr-imagens', action='store_true',
                        help='Aplicar OCR local (Tesseract) às imagens avulsas do lote; desligado por padrão. '
                             'O texto reconhecido precisa ser conferido no original.')
    parser.add_argument('--modo-fontes', choices=fontes_web_mod.MODOS, default=None,
                        help='Só com --novo: somente_documental (padrão) ou documentos_web.')
    parser.add_argument('--dominio-permitido', help='Só com --modo-fontes documentos_web: domínio único permitido.')
    args = parser.parse_args()
    if args.preparar_pdfs:
        if args.novo or args.titulo or args.ocr_imagens:
            parser.error('--preparar-pdfs é para caso existente, sem --novo, --titulo ou --ocr-imagens.')
        result = preparar_pdfs(ROOT, args.caso)
    else:
        result = cadastrar(ROOT, args.caso, [Path(p) for p in args.documentos], titulo=args.titulo,
                           natureza=args.natureza, novo=args.novo, ocr_imagens=args.ocr_imagens,
                           modo_fontes=args.modo_fontes, dominio_permitido=args.dominio_permitido)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
