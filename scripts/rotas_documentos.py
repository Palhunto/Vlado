"""Recepção de lotes enviados pela Mesa e catálogo das apurações.

Separado de ``interface_pesquisa`` sem mudar comportamento. ``receber_documentos`` grava o
lote numa pasta temporária e entrega os caminhos a ``cadastrar_documentos.cadastrar``; o
cliente nunca envia caminhos. ``catalogo`` lê só metadados e nomes de pastas, sem abrir
documentos de casos inativos. O servidor chama as duas dentro da trava de cadastro.
"""
from __future__ import annotations

import base64
from pathlib import Path
from pathlib import PureWindowsPath
import re
import tempfile
import uuid

from comum import dentro, ler_json
from cadastrar_documentos import cadastrar
import lixeira
from indice_sqlite import ID_CASO, ID_RODADA, ID_GERACAO

MAX_UPLOAD = 50 * 1024 * 1024


def receber_documentos(root, data):
    files = data.get('arquivos')
    if not isinstance(files, list) or not 1 <= len(files) <= 100:
        raise ValueError('Envie de 1 a 100 arquivos por lote, até 50 MB no total.')
    if type(data.get('novo', False)) is not bool:
        raise ValueError('Indicação de novo caso inválida.')
    with tempfile.TemporaryDirectory(prefix='envio_documental_') as folder:
        sources, total = [], 0
        for number, item in enumerate(files):
            if not isinstance(item, dict):
                raise ValueError('Arquivo enviado inválido; lote não cadastrado.')
            name = item.get('nome')
            if (not isinstance(name, str) or not name or len(name) > 255
                    or PureWindowsPath(name).name != name or PureWindowsPath(name).is_reserved()
                    or name.endswith(('.', ' '))
                    or any(ord(c) < 32 or c in ':\\/<>"|?*' for c in name)):
                raise ValueError('Nome de arquivo inválido; lote não cadastrado.')
            encoded = item.get('base64')
            if not isinstance(encoded, str):
                raise ValueError('Conteúdo de arquivo inválido; lote não cadastrado.')
            content = base64.b64decode(encoded, validate=True)
            total += len(content)
            if total > MAX_UPLOAD:
                raise ValueError('O lote excede 50 MB; nenhum arquivo cadastrado.')
            source = Path(folder) / str(number) / name
            source.parent.mkdir()
            source.write_bytes(content)
            sources.append(source)
        case = data.get('caso')
        if data.get('novo') and not case:
            case = 'apuracao_' + uuid.uuid4().hex
        return cadastrar(root, case, sources, titulo=data.get('titulo'),
                         natureza=data.get('natureza', 'nao_informada'), novo=data.get('novo', False),
                         modo_fontes=data.get('modo_fontes'), dominio_permitido=data.get('dominio_permitido'))


def catalogo(root):
    """Read catalog metadata and directory names only; do not read inactive documents."""
    path = root / 'casos/catalogo.json'
    cases = ler_json(path)['casos'] if path.is_file() else []
    result = []
    removed = lixeira.ativos(root)
    for case in cases:
        identifier = case['id']
        if not re.fullmatch(ID_CASO, identifier):
            continue
        if lixeira.excluido(root, identifier, itens=removed):
            continue
        rounds = []
        folder = dentro(root, f'execucoes/{identifier}')
        try:
            runs = sorted(folder.iterdir()) if folder.is_dir() else []
        except PermissionError:
            result.append({'id': identifier, 'titulo': case.get('titulo', identifier),
                           'rodadas': [], 'aviso': 'Sem permissão para listar rodadas deste caso.'})
            continue
        for run in runs:
            if not re.fullmatch(ID_RODADA, run.name) or not run.is_dir():
                continue
            if lixeira.excluido(root, identifier, rodada=run.name, itens=removed):
                continue
            run = dentro(root, f'execucoes/{identifier}/{run.name}')
            index = dentro(run, 'indice')
            try:
                generations = [item.name for item in sorted(index.iterdir())
                               if re.fullmatch(ID_GERACAO, item.name)
                               and dentro(index, item.name).is_dir()
                               and dentro(index, f'{item.name}/manifesto.json').is_file()
                               and dentro(index, f'{item.name}/apuracao.sqlite').is_file()] if index.is_dir() else []
                rounds.append({'id': run.name, 'geracoes': generations})
            except PermissionError:
                rounds.append({'id': run.name, 'geracoes': [],
                               'aviso': 'Sem permissão para listar índices desta rodada.'})
        result.append({'id': identifier, 'titulo': case.get('titulo', identifier), 'rodadas': rounds})
    return {'casos': result}
