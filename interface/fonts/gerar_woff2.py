"""Gera os WOFF2 com subconjunto latino das fontes da Mesa (Onda 3, parte C, UX-04).

    python interface/fonts/gerar_woff2.py            # grava interface/fonts/*-latin.woff2
    python interface/fonts/gerar_woff2.py --conferir # nao grava; falha se faltar glifo usado na interface

Ferramenta de desenvolvimento, fora do runtime da Mesa e da imagem: precisa de ``fonttools`` e ``brotli``
(``pip install fonttools brotli``, de preferencia num ambiente a parte). As fontes de origem seguem em
``interface/fonts`` e a licenca em LICENSE-*.md. O subconjunto cobre o latim da Mesa (basico, latim-1 e
latim estendido A), a pontuacao geral e os sinais que a interface usa; o script le o texto da interface
(HTML, JS e CSS) e acrescenta qualquer outro caractere que a fonte de origem tenha.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

RAIZ = Path(__file__).resolve().parents[2]
INTERFACE = RAIZ / 'interface'
FONTES = INTERFACE / 'fonts'
# origem -> destino
FONTES_DA_MESA = {'SourceSans3-Upright.otf': 'SourceSans3-latin.woff2', 'SourceSerif4-Roman.ttf': 'SourceSerif4-latin.woff2'}
# Latim da Mesa: ASCII, latim-1, latim estendido A, pontuacao geral, setas, matematica e formas usadas pela interface.
FAIXAS = [(0x20, 0x7E), (0xA0, 0xFF), (0x100, 0x17F), (0x2010, 0x2027), (0x2030, 0x203A), (0x2044, 0x2044), (0x20AC, 0x20AC),
          (0x2122, 0x2122), (0x2190, 0x2193), (0x2212, 0x2212), (0x2022, 0x2022), (0x25CB, 0x25CB), (0x25BE, 0x25BE), (0x2713, 0x2713)]
SUFIXOS = ('.html', '.js', '.css')


def caracteres_da_interface() -> set[int]:
    usados: set[int] = set()
    for caminho in INTERFACE.iterdir():
        if caminho.suffix in SUFIXOS and caminho.is_file():
            usados |= {ord(c) for c in caminho.read_text(encoding='utf-8', errors='ignore') if ord(c) > 0x7E}
    return usados


def unicodes(origem: Path, usados: set[int]) -> list[int]:
    from fontTools.ttLib import TTFont
    cmap = set(TTFont(origem).getBestCmap())
    base = {c for ini, fim in FAIXAS for c in range(ini, fim + 1)}
    return sorted((base | usados) & cmap)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--conferir', action='store_true', help='nao grava; so lista os caracteres usados que a fonte nao tem')
    args = ap.parse_args(argv)
    try:
        from fontTools import subset
        from fontTools.ttLib import TTFont
        import brotli  # noqa: F401  (exigido pelo flavor woff2)
    except ImportError as erro:
        print(f'faltam fonttools e brotli ({erro}); veja o topo deste arquivo', file=sys.stderr)
        return 2
    usados = caracteres_da_interface()
    for origem, destino in FONTES_DA_MESA.items():
        caminho = FONTES / origem
        pontos = unicodes(caminho, usados)
        cobertos = set(pontos)
        faltam = sorted(c for c in usados if c not in cobertos and c > 0x7E)
        print(f'{origem}: {len(pontos)} glifos no subconjunto; usados na interface e ausentes da fonte: '
              + (' '.join(f'U+{c:04X}' for c in faltam) or 'nenhum'))
        if args.conferir:
            continue
        opcoes = subset.Options()
        opcoes.flavor = 'woff2'
        opcoes.layout_features = ['*']           # kern, liga, ccmp, tnum, onum... como na fonte de origem
        opcoes.name_IDs = ['*']
        opcoes.notdef_outline = True
        opcoes.drop_tables += ['DSIG']
        # A Mesa usa pesos de 400 a 800 (corpo 400, rotulos 500 a 650, titulos 600, negrito 700 e a marca 800): o eixo wght e
        # recortado a essa faixa, o que tira peso do arquivo sem mudar nenhum peso usado.
        from fontTools.varLib import instancer
        import io
        recortada = instancer.instantiateVariableFont(TTFont(caminho), {'wght': (400, 800)})
        memoria = io.BytesIO()
        recortada.save(memoria)
        memoria.seek(0)
        fonte = subset.load_font(memoria, opcoes)
        sub = subset.Subsetter(opcoes)
        sub.populate(unicodes=pontos)
        sub.subset(fonte)
        subset.save_font(fonte, str(FONTES / destino), opcoes)
        print(f'  {origem} {caminho.stat().st_size // 1024} KB -> {destino} {(FONTES / destino).stat().st_size // 1024} KB')
    return 0


if __name__ == '__main__':
    sys.exit(main())
