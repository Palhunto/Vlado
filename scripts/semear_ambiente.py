"""Seed a synthetic environment (homologation or classroom demo) with fictitious data.

Creates two synthetic cases, three accounts (one admin, two guests with different
cases) and a starting note in the notebook. Refuses the editorial environment.
Activation links go only to a 0600 file given by --saida, never to stdout or logs.

  VLADO_AMBIENTE=demonstracao python scripts/semear_ambiente.py --origem https://demo.exemplo --saida /caminho/links.txt
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import tempfile
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
import acesso  # noqa: E402
import apuracao  # noqa: E402
from cadastrar_documentos import cadastrar  # noqa: E402
from comum import ROOT, ler_json  # noqa: E402
import dados_sinteticos  # noqa: E402

AMBIENTES_SINTETICOS = ('homologacao', 'demonstracao')
CASO_A, CASO_B = 'vila_serena_sintetico', 'campo_verde_aditivo_sintetico'
CONTAS = (('Admin da demonstração', 'demo.admin', 'admin', ()),
          ('Convidado 1 (sintético)', 'demo.convidado1', 'convidado', (CASO_A,)),
          ('Convidado 2 (sintético)', 'demo.convidado2', 'convidado', (CASO_B,)))
NOTA = ('## Pauta\n\nContrato 041/2025 de pavimentação em Vila Serena (dados fictícios).\n\n'
        '### Conferir\n\n- [ ] Conferir medição nº 3 no original digitalizado\n'
        '- [ ] Comparar valor do aditivo com o contrato\n')


def _casos_existentes(root: Path) -> set[str]:
    catalogo = root / 'casos/catalogo.json'
    return {c['id'] for c in ler_json(catalogo)['casos']} if catalogo.is_file() else set()


def _conferir_destino_sintetico(root: Path) -> None:
    """VLADO_AMBIENTE can be set wrongly: also refuse any install that already holds non-synthetic data."""
    catalogo = root / 'casos/catalogo.json'
    for caso in (ler_json(catalogo)['casos'] if catalogo.is_file() else []):
        manifesto = root / caso.get('manifesto', f"casos/{caso['id']}/manifesto.json")
        natureza = ler_json(manifesto).get('natureza_informada') if manifesto.is_file() else None
        if natureza != 'sinteticos':
            raise SystemExit(f"Recusado: o caso {caso['id']!r} não é sintético; isto parece um ambiente real.")
    alheias = [c['login'] for c in acesso.listar(root) if not c['login'].startswith('demo.')]
    if alheias:
        raise SystemExit('Recusado: há contas que não são de demonstração; isto parece um ambiente real.')


def semear(root: Path, ambiente: str, origem: str, saida: Path) -> dict:
    if ambiente not in AMBIENTES_SINTETICOS:
        raise SystemExit('Recusado: só semeia os ambientes homologacao e demonstracao, nunca o editorial.')
    root = Path(root)
    _conferir_destino_sintetico(root)
    feitos = {'casos': [], 'contas': [], 'nota': None}
    existentes = _casos_existentes(root)
    with tempfile.TemporaryDirectory(prefix='vlado_sintetico_') as pasta:
        lotes = dados_sinteticos.gerar(Path(pasta))
        for caso, titulo, arquivos in ((CASO_A, 'Vila Serena (sintética)', lotes['lote1']),
                                       (CASO_B, 'Aditivo Campo Verde (sintético)', lotes['lote2'])):
            if caso not in existentes:
                cadastrar(root, caso, arquivos, titulo=titulo, natureza='sinteticos', novo=True)
                feitos['casos'].append(caso)
    logins = {c['login']: c for c in acesso.listar(root)}
    links = []
    for nome, login, papel, casos in CONTAS:
        if login in logins:
            continue
        registro, token = acesso.criar_conta(root, nome, login, papel=papel, casos=list(casos), por='semeador')
        links.append(f'{login}\t{origem.rstrip("/")}/ativar/{token}')
        feitos['contas'].append(login)
        logins[login] = registro
    if links:
        descritor = os.open(saida, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descritor, 'w', encoding='utf-8') as arquivo:
            arquivo.write('\n'.join(links) + '\n')
    admin = logins['demo.admin']
    if not apuracao.listar_notas(root, CASO_A)['notas']:
        resultado = apuracao.executar(root, 'apuracao-nota-salvar', {
            'caso': CASO_A, 'requisicao_id': uuid.uuid4().hex, 'titulo': 'Pauta Vila Serena', 'texto': NOTA},
            {'id': admin['id'], 'nome': admin['nome']})
        feitos['nota'] = resultado['nota_id']
    return feitos


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--origem', required=True, help='Endereço HTTPS deste ambiente (para os links).')
    parser.add_argument('--saida', required=True, type=Path, help='Arquivo 0600 que recebe os links de ativação.')
    args = parser.parse_args()
    feitos = semear(ROOT, os.environ.get('VLADO_AMBIENTE', ''), args.origem, args.saida)
    print(f"Casos criados: {feitos['casos'] or 'nenhum'}; contas criadas: {feitos['contas'] or 'nenhuma'}; "
          f"links em {args.saida}" if feitos['contas'] else f"Casos criados: {feitos['casos'] or 'nenhum'}; contas já existiam.")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
