"""Junta a captura da Mesa de hoje e a proposta derivada, lado a lado, numa imagem por tema e largura.

Uso (com o Python do .venv):
  python docs/design/aprovacao/ferramentas/montar_comparativo.py <pasta da área> <prefixo da proposta>
  ex.: ... docs/design/aprovacao/caderno proposta
       ... docs/design/aprovacao/quadros proposta-hipoteses
       ... docs/design/aprovacao/cadastro proposta docs/design/aprovacao/documentos  (proposta de outra pasta)
Gera <pasta>/comparativo-<tema>-<largura>.png a partir de atual-<tema>-<largura>.png e <prefixo>-<tema>-<largura>.png.
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

RAIZ = Path(__file__).resolve().parents[4]
FONTE = RAIZ / 'interface' / 'fonts' / 'SourceSans3-Upright.otf'
CORES = {'claro': ('#f6f5f0', '#202c29'), 'escuro': ('#171d1a', '#eae9df')}


def montar(pasta: Path, prefixo: str, origem_proposta: Path | None = None) -> None:
    fonte = ImageFont.truetype(str(FONTE), 22)
    for tema in ('claro', 'escuro'):
        for largura in ('1440', '390'):
            atual = pasta / f'atual-{tema}-{largura}.png'
            proposta = (origem_proposta or pasta) / f'{prefixo}-{tema}-{largura}.png'
            if not (atual.is_file() and proposta.is_file()):
                continue
            a, b = Image.open(atual).convert('RGB'), Image.open(proposta).convert('RGB')
            margem, topo = 24, 56
            w = a.width + b.width + 3 * margem
            h = max(a.height, b.height) + topo + margem
            fundo, texto = CORES[tema]
            tela = Image.new('RGB', (w, h), fundo)
            d = ImageDraw.Draw(tela)
            d.text((margem, 16), 'Atual (Mesa hoje)', font=fonte, fill=texto)
            d.text((2 * margem + a.width, 16), 'Proposta (derivado)', font=fonte, fill=texto)
            tela.paste(a, (margem, topo))
            tela.paste(b, (2 * margem + a.width, topo))
            saida = pasta / f'comparativo-{prefixo.replace("proposta", "").strip("-") + "-" if prefixo != "proposta" else ""}{tema}-{largura}.png'
            tela.save(saida, 'PNG', optimize=True)
            print(saida.name, tela.size)


if __name__ == '__main__':
    montar(Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3]) if len(sys.argv) > 3 else None)
