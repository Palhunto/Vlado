"""Freeze authorized inputs for a new round without invoking a model."""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import re
import shutil
from comum import (ROOT, arquivos_do_corpus, arquivos_do_cadastro, carregar_corpus, conferir_projeto,
                   escrever_json, sha256, VERSAO_PROMPTS, pasta_preparacao)
from cadastrar_documentos import _trava
from fontes_web import arquivos_web, modo_do_caso


@contextmanager
def preparar_pasta_rodada(destino: Path):
    if destino.exists():
        raise FileExistsError(f'Rodada ja existe e nao sera sobrescrita: {destino.name}')
    # Both initial questions and follow-ups stage on the same volume without
    # repeating the case ID. Publish only after the caller finishes the snapshot.
    with pasta_preparacao(destino.parent.parent, '.r_') as staging:
        work = staging / destino.name
        work.mkdir()
        yield work
        work.rename(destino)


def criar_rodada(root: Path, identifier: str, question: str, *, tipo='piloto', modelo=None, indice=None, caso=None):
    with _trava(root):
        return _criar_rodada(root, identifier, question, tipo=tipo, modelo=modelo, indice=indice, caso=caso)


def _criar_rodada(root: Path, identifier: str, question: str, *, tipo='piloto', modelo=None, indice=None, caso=None):
    if not re.fullmatch(r'R[0-9]{3,6}', identifier):
        raise ValueError('Usar ID de R001 a R999999, com pelo menos tres digitos.')
    if not question.strip():
        raise ValueError('Pergunta vazia; nao iniciar apuracao.')
    if tipo not in ('piloto', 'principal'):
        raise ValueError('Tipo de rodada desconhecido.')
    if caso is None:
        conferir_projeto(root)
    else:
        from comum import conferir_prompts
        conferir_prompts(root)
    if caso is None:
        config, manifest_path, manifest = carregar_corpus(root)
    else:
        from comum import dentro, ler_json
        if not isinstance(caso, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', caso):
            raise ValueError('Identificador de caso invalido.')
        config = ler_json(root / 'configuracao.json')
        config = {**config, 'caso_ativo': caso, 'manifesto_ativo': f'casos/{caso}/manifesto.json'}
        manifest_path = dentro(root, config['manifesto_ativo'])
        manifest = ler_json(manifest_path)
        if manifest.get('caso_id') != caso or not manifest.get('documentos'):
            raise ValueError('Manifesto vazio ou de outro caso.')
        if len(manifest['documentos']) > config['maximo_documentos_inicial']:
            raise ValueError('Corpus excede o limite configurado.')
    usar_indice = config.get('indice_sqlite', False) if indice is None else indice
    protocol = manifest.get('protocolo', {})
    if tipo == 'principal' and not (protocol.get('piloto_estabilizado') and protocol.get('teste_principal_autorizado')):
        raise ValueError('Teste principal exige piloto estabilizado e autorizacao registrada na configuracao.')
    case_id = manifest['caso_id']
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', case_id):
        raise ValueError('Identificador de caso invalido.')
    parent = root / 'execucoes' / case_id
    parent.mkdir(parents=True, exist_ok=True)
    destination = parent / identifier
    with preparar_pasta_rodada(destination) as work:
        inputs = work / 'entradas'
        inputs.mkdir(parents=True)
        paths = list(arquivos_do_corpus(root, manifest))
        paths += list(arquivos_do_cadastro(root, manifest))
        # Web captures exist only in cases created in the "documentos + web" mode.
        web = list(arquivos_web(root, manifest))
        paths += web
        paths += [(str(manifest_path.relative_to(root)), manifest_path)]
        paths += [('AGENTS.md', root / 'AGENTS.md'), ('configuracao.json', root / 'configuracao.json')]
        if (root / 'README.md').is_file():
            paths += [('README.md', root / 'README.md')]
        paths += [(f'prompts/{p.name}', p) for p in sorted((root / 'prompts').glob('*.md'))]
        paths += [('prompts/manifesto_prompts.json', root / 'prompts' / 'manifesto_prompts.json')]
        frozen = []
        for relative, source in paths:
            target = inputs / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            if sha256(target) != sha256(source):
                raise ValueError(f'Falha na copia do snapshot: {relative}')
            frozen.append({'arquivo': f'entradas/{relative}', 'sha256': sha256(target)})
        if caso is not None:
            # Explicit UI selection is frozen without changing the global active case.
            escrever_json(inputs / 'configuracao.json', config)
            next(x for x in frozen if x['arquivo'] == 'entradas/configuracao.json')['sha256'] = sha256(inputs / 'configuracao.json')
        (work / '00_pergunta_original.md').write_text(question, encoding='utf-8')
        frozen.append({'arquivo':'00_pergunta_original.md', 'sha256':sha256(work / '00_pergunta_original.md')})
        (work / 'saidas').mkdir()
        record = {
            'caso_id':case_id, 'rodada': identifier, 'tipo': tipo, 'estado': 'entradas_congeladas_sem_geracao',
            'criada_em_utc': datetime.now(timezone.utc).isoformat(),
            'corpus_id': manifest['corpus_id'], 'versao_prompts': VERSAO_PROMPTS,
            'modelo_informado': modelo, 'modelo_observado_pelo_agente': None,
            'ferramentas_usadas': [], 'web_usada': False,  # live navigation; frozen captures are counted below
            'modo_fontes': modo_do_caso(manifest)['modo'],
            'dominio_permitido': modo_do_caso(manifest).get('dominio_permitido'),
            'capturas_web_congeladas': len(manifest.get('capturas_web', [])),
            'conferencia_humana': 'nao_realizada',
            'etapas_concluidas': [], 'contaminacao_conhecida': None,
            'observacao': 'Snapshot de arquivos; nao captura automaticamente a conversa nem comprova inferencia.',
        }
        escrever_json(work / 'snapshot.json', frozen)
        escrever_json(work / 'registro.json', record)
        if usar_indice:
            from indice_sqlite import construir_snapshot
            construir_snapshot(work, case_id, identifier)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--id', required=True)
    parser.add_argument('--pergunta-arquivo', required=True)
    parser.add_argument('--tipo', choices=['piloto', 'principal'], default='piloto')
    parser.add_argument('--modelo', default=None, help='Nome efetivamente exibido/informado; opcional.')
    parser.add_argument('--sem-indice', action='store_true', help='Congelar sem SQLite; registrar motivo no inventario.')
    args = parser.parse_args()
    question = Path(args.pergunta_arquivo).read_text(encoding='utf-8-sig')
    print(criar_rodada(ROOT, args.id, question, tipo=args.tipo, modelo=args.modelo,
                       indice=False if args.sem_indice else None))


if __name__ == '__main__':
    main()
