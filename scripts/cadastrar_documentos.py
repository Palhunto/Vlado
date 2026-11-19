"""Register each explicitly supplied batch before a question; never start a round."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
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
from extrair_pdf import extrair_pdf
from lixeira import conferir_disponivel
import fontes_web as fontes_web_mod


@contextmanager
def _trava(root):
    cases = dentro(root, 'casos')
    cases.mkdir(exist_ok=True)
    lock = dentro(cases, '.cadastro.lock')
    try:
        lock.mkdir()
    except FileExistsError as exc:
        raise ValueError('Há um cadastro ou congelamento em andamento; tente novamente após sua conclusão.') from exc
    try:
        yield
    finally:
        lock.rmdir()


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
                            'extracao_pdf': d.get('extracao_pdf')} for d in manifest['documentos']],
            'recibos': manifest.get('registros_cadastro', []),
            'fontes_web': fontes_web_mod.modo_do_caso(manifest),
            'capturas_web': len(manifest.get('capturas_web', [])),
            'estado': 'cadastrado_aguardando_pergunta'}


def cadastrar(root, caso, sources, *, titulo=None, natureza='nao_informada', novo=False,
              modo_fontes=None, dominio_web=None):
    if not isinstance(caso, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', caso):
        raise ValueError('ID do caso: letras minúsculas, números, hífen ou underscore; até 64 caracteres.')
    if natureza not in ('publicos', 'sinteticos', 'nao_informada'):
        raise ValueError('Natureza documental inválida.')
    if not sources:
        raise ValueError('Envie pelo menos um arquivo.')
    if not novo and (modo_fontes or dominio_web):
        raise ValueError('O modo de fontes (somente documentos ou documentos + web) só é escolhido na criação do caso.')
    fontes_web = fontes_web_mod.definir_modo(modo_fontes, dominio_web) if novo else None
    with _trava(root):
        return _cadastrar(root, caso, sources, titulo, natureza, novo, fontes_web=fontes_web)


def preparar_pdfs(root, caso):
    """Enrich this case's preserved PDFs; never inspect inactive cases or old rounds."""
    if not isinstance(caso, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', caso):
        raise ValueError('Identificador de caso inválido.')
    with _trava(root):
        conferir_disponivel(root, caso)
        manifest = ler_json(dentro(root, f'casos/{caso}/manifesto.json'))
        sources = [dentro(root, d['arquivo']) for d in manifest['documentos']
                   if Path(d['arquivo']).suffix.lower() == '.pdf']
        if not sources:
            raise ValueError('Este caso não tem PDFs cadastrados para preparar.')
        return _cadastrar(root, caso, sources, None, manifest['natureza_informada'], False,
                          operacao='preparacao_pdfs_cadastrados')


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


def _cadastrar(root, caso, sources, title, nature, new, *, operacao='recepcao_documentos', fontes_web=None):
    conferir_disponivel(root, caso)
    destination = dentro(root, f'casos/{caso}')
    catalog_path = dentro(root, 'casos/catalogo.json')
    catalog_before = catalog_path.read_bytes() if catalog_path.exists() else None
    catalog = ler_json(catalog_path) if catalog_before else {'casos': []}
    entry = next((c for c in catalog['casos'] if c['id'] == caso), None)
    manifest_path = dentro(root, f'casos/{caso}/manifesto.json')
    if new:
        if destination.exists() or entry:
            raise ValueError('Caso já existe; selecione-o para acrescentar um lote.')
        if not isinstance(title, str) or not title.strip():
            raise ValueError('Informe o título do novo caso.')
        manifest_before = None
        manifest = {'versao': '1.0.0', 'caso_id': caso, 'titulo': title.strip(),
                    'natureza_informada': nature, 'corpus_id': f'{caso}_v1',
                    'fontes_web': fontes_web or fontes_web_mod.definir_modo(),
                    'estado': 'preparado_sem_piloto_de_apuracao',
                    'protocolo': {'piloto_estabilizado': False, 'teste_principal_autorizado': False},
                    'documentos': [], 'registros_cadastro': []}
    else:
        if not entry or not destination.is_dir():
            raise ValueError('Caso inexistente; não cadastrar em outro caso automaticamente.')
        manifest_before = manifest_path.read_bytes()
        manifest = ler_json(manifest_path)
        if manifest.get('caso_id') != caso or entry['manifesto'] != f'casos/{caso}/manifesto.json':
            raise ValueError('Catálogo e manifesto não correspondem ao caso.')
        list(arquivos_do_corpus(root, manifest))
    previous = deepcopy(manifest)
    known = {d['sha256']: d for d in manifest['documentos']}
    used = {d['id'] for d in manifest['documentos']}
    batch = uuid.uuid4().hex
    prefix = f'casos/{caso}/cadastros/{batch}'
    incoming, receipts = [], []
    pdfs = {}
    for item in sources:
        source = Path(item).resolve()
        if not source.is_file() or source.suffix.lower() not in EXTENSOES:
            raise ValueError(f'Lote não cadastrado: arquivo ausente ou formato não aceito: {source.name}. Nenhum arquivo deste lote foi confirmado.')
        digest = sha256(source)
        if digest in known:
            doc, status = known[digest], 'duplicado'
        else:
            number = 1
            while f'D{number:03d}' in used:
                number += 1
            identifier = f'D{number:03d}'
            used.add(identifier)
            stem = ''.join(c if c.isalnum() or c in '-_' else '_' for c in source.stem)[:80] or 'documento'
            doc = {'id': identifier, 'arquivo': f'{prefix}/originais/{identifier}_{stem}{source.suffix.lower()}',
                   'sha256': digest, 'bytes': source.stat().st_size, 'nome_recebido': source.name,
                   'origem_informada': None, 'natureza_informada': nature, 'paginas_pdf': None, 'derivados': []}
            incoming.append((source, doc))
            manifest['documentos'].append(doc)
            known[digest] = doc
            status = 'cadastrado'
        receipts.append({'nome_recebido': doc.get('nome_recebido', source.name) if operacao == 'preparacao_pdfs_cadastrados' else source.name,
                         'documento_id': doc['id'], 'sha256': digest,
                         'bytes': source.stat().st_size, 'estado': status})
        if source.suffix.lower() == '.pdf':
            pdfs[doc['id']] = doc
    maximum = ler_json(root / 'configuracao.json')['maximo_documentos_inicial']
    if len(manifest['documentos']) > maximum:
        raise ValueError(f'Lote não cadastrado: ultrapassaria o limite de {maximum} documentos. Nenhum arquivo deste lote foi confirmado.')
    with pasta_preparacao(root / 'casos', '.lote_') as temp:
        work = Path(temp) / 'lote'
        work.mkdir()
        for source, doc in incoming:
            target = work / 'originais' / Path(doc['arquivo']).name
            target.parent.mkdir(exist_ok=True)
            shutil.copyfile(source, target)
            if sha256(target) != doc['sha256']:
                raise ValueError('Lote não cadastrado: cópia divergente; nenhum arquivo confirmado.')
        copied = {doc['id'] for _, doc in incoming}
        processed = 0
        for identifier, doc in pdfs.items():
            # A repeated successful/empty/partial extraction is not silently replaced.
            # Re-sending an errored PDF explicitly permits another attempt in a new batch.
            existing = doc.get('extracao_pdf')
            reprocess = operacao == 'preparacao_pdfs_cadastrados' and _precisa_reprocessar_ocr(existing)
            if existing and existing['estado'] != 'erro' and not reprocess:
                continue
            source = (work / 'originais' / Path(doc['arquivo']).name if identifier in copied
                      else dentro(root, doc['arquivo']))
            target = work / 'derivados' / f'{identifier}_texto_pdf.md'
            doc['extracao_pdf'] = extrair_pdf(source, identifier, target)
            doc['paginas_pdf'] = doc['extracao_pdf']['paginas_pdf']
            if target.is_file():
                # A new version replaces the prior working copy of this PDF; old rounds keep theirs.
                old = [d for d in doc.get('derivados', []) if d.get('tipo') == 'texto_extraido_pdf']
                doc['derivados'] = [d for d in doc.get('derivados', []) if d.get('tipo') != 'texto_extraido_pdf']
                entry_pdf = {'arquivo': f'{prefix}/derivados/{target.name}', 'sha256': sha256(target),
                             'tipo': 'texto_extraido_pdf', 'origem_sha256': doc['sha256'],
                             'metodo': doc['extracao_pdf']['metodo'],
                             'paginas_origem': doc['extracao_pdf']['paginas_origem']}
                if old:
                    entry_pdf['substitui_sha256'] = old[-1]['sha256']
                doc['derivados'].append(entry_pdf)
            processed += 1
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
        summary = _resumo_pdfs(pdfs, processed)
        receipt = {'lote_id': batch, 'caso_id': caso, 'corpus_id': manifest['corpus_id'],
                   'operacao': operacao, 'recebido_em_utc': datetime.now(timezone.utc).isoformat(),
                   'recebidos': len(receipts), 'novos': len(incoming),
                   'duplicados': len(receipts) - len(incoming), 'total_documentos': len(manifest['documentos']),
                   'arquivos': receipts, 'extracao_pdf_resumo': summary,
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
        except Exception:
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
    parser.add_argument('--modo-fontes', choices=fontes_web_mod.MODOS, default=None,
                        help='Só com --novo: somente_documentos (padrão) ou documentos_e_web.')
    parser.add_argument('--dominio-web', help='Só com --modo-fontes documentos_e_web: domínio único permitido.')
    args = parser.parse_args()
    if args.preparar_pdfs:
        if args.novo or args.titulo:
            parser.error('--preparar-pdfs é para caso existente, sem --novo ou --titulo.')
        result = preparar_pdfs(ROOT, args.caso)
    else:
        result = cadastrar(ROOT, args.caso, [Path(p) for p in args.documentos], titulo=args.titulo,
                           natureza=args.natureza, novo=args.novo,
                           modo_fontes=args.modo_fontes, dominio_web=args.dominio_web)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
