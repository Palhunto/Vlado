"""Register selected documents as a separate case. No inference or network."""
from __future__ import annotations
import argparse
from pathlib import Path
import re
from comum import ROOT, dentro, ler_json, sha256

EXTENSOES = {'.pdf','.png','.jpg','.jpeg','.txt','.md','.csv','.tsv','.xlsx','.docx'}


def criar_caso(root: Path, case_id: str, title: str, sources: list[Path], natureza='nao_informada',
               modo_fontes=None, dominio_web=None):
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}',case_id):
        raise ValueError('ID do caso: letras minusculas, numeros, hifen ou underscore; ate 64 caracteres.')
    if not title.strip():
        raise ValueError('Informar titulo da apuracao.')
    if natureza not in ('publicos','sinteticos','nao_informada'):
        raise ValueError('Natureza documental desconhecida.')
    config = ler_json(root/'configuracao.json')
    if not sources or len(sources) > config['maximo_documentos_inicial']:
        raise ValueError('Quantidade de documentos fora do limite inicial configurado.')
    resolved = [p.resolve() for p in sources]
    if any(not p.is_file() or p.suffix.lower() not in EXTENSOES for p in resolved):
        raise ValueError('Arquivo ausente ou formato nao cadastravel.')
    hashes = [sha256(p) for p in resolved]
    if len(set(hashes)) != len(hashes):
        raise ValueError('Arquivos identicos nao devem ser cadastrados como fontes independentes.')
    cases = root/'casos'
    cases.mkdir(exist_ok=True)
    destination = dentro(root, f'casos/{case_id}')
    catalog_path = cases/'catalogo.json'
    catalog = ler_json(catalog_path) if catalog_path.exists() else {'casos':[]}
    if destination.exists() or any(x['id']==case_id for x in catalog['casos']):
        raise FileExistsError('Caso ja existe; usar nova versao sem sobrescrever.')
    # Keep the legacy validation contract, but all entry points share extraction,
    # receipts, locking and transactional publication with the current registrar.
    from cadastrar_documentos import cadastrar
    cadastrar(root, case_id, resolved, titulo=title, natureza=natureza, novo=True,
              modo_fontes=modo_fontes, dominio_web=dominio_web)
    return destination


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--id',required=True)
    parser.add_argument('--titulo',required=True)
    parser.add_argument('--documentos',nargs='+',required=True)
    parser.add_argument('--natureza',choices=['publicos','sinteticos','nao_informada'],default='nao_informada')
    parser.add_argument('--modo-fontes',choices=['somente_documentos','documentos_e_web'],default=None)
    parser.add_argument('--dominio-web',help='Dominio unico permitido no modo documentos_e_web.')
    args=parser.parse_args()
    print(criar_caso(ROOT,args.id,args.titulo,[Path(p) for p in args.documentos],args.natureza,
                     args.modo_fontes,args.dominio_web))
    print('Caso cadastrado e inativo; selecionar explicitamente antes de apurar.')


if __name__=='__main__':
    main()
