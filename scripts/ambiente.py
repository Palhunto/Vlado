"""Check the actual interpreter before launching the UI; no installs or models."""
from __future__ import annotations

import argparse
import importlib
import json
import os
import sqlite3
import sys


def diagnostico():
    result = {'python': sys.executable, 'versao_python': sys.version.split()[0],
              'python_compativel': sys.version_info >= (3, 12), 'sqlite_fts5': False,
              'extracao_pdf': {'disponivel': False, 'versao': None}}
    try:
        with sqlite3.connect(':memory:') as con:
            con.execute('CREATE VIRTUAL TABLE teste USING fts5(texto)')
        result['sqlite_fts5'] = True
    except sqlite3.Error as exc:
        result['erro_sqlite'] = str(exc)
    try:
        package = importlib.import_module('pypdf')
        if not callable(getattr(package, 'PdfReader', None)):
            raise ImportError('pypdf sem PdfReader disponível.')
        result['extracao_pdf'] = {'disponivel': True, 'versao': getattr(package, '__version__', None)}
    except Exception as exc:
        result['extracao_pdf']['erro'] = str(exc)
    # OCR local e informativo: nao entra em `pronto` (PDFs nativos funcionam sem ele).
    try:
        import ocr
        detalhe = ocr.diagnostico()
        result['ocr'] = {'disponivel': detalhe['disponivel'], 'motor': detalhe.get('motor'),
                         'motivo': detalhe.get('motivo'),
                         'tesseract': detalhe['tesseract'].get('versao'),
                         'ghostscript': bool(detalhe['ocrmypdf'].get('ghostscript'))}
    except Exception as exc:
        result['ocr'] = {'disponivel': False, 'motivo': str(exc)[:300]}
    result['exportacao_apuracao'] = {}
    for package, format in (('docx', 'docx'), ('reportlab', 'pdf')):
        try:
            imported = importlib.import_module(package)
            result['exportacao_apuracao'][format] = {'disponivel': True, 'versao': getattr(imported, '__version__', None)}
        except Exception as exc:
            result['exportacao_apuracao'][format] = {'disponivel': False, 'erro': str(exc)}
    # Key presence only (True/False); values never leave the server environment.
    result['inferencia_api'] = {'sdks': {}, 'chaves': {nome: bool(os.environ.get(nome, '').strip())
                                                       for nome in ('ANTHROPIC_API_KEY', 'OPENAI_API_KEY')}}
    for package in ('anthropic', 'openai'):
        try:
            imported = importlib.import_module(package)
            result['inferencia_api']['sdks'][package] = {'disponivel': True, 'versao': getattr(imported, '__version__', None)}
        except Exception as exc:
            result['inferencia_api']['sdks'][package] = {'disponivel': False, 'erro': str(exc)}
    result['pronto'] = (result['python_compativel'] and result['sqlite_fts5'] and result['extracao_pdf']['disponivel']
                       and all(v['disponivel'] for v in result['exportacao_apuracao'].values())
                       and all(v['disponivel'] for v in result['inferencia_api']['sdks'].values()))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--silencioso', action='store_true')
    args = parser.parse_args()
    result = diagnostico()
    if not args.silencioso:
        print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result['pronto'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
