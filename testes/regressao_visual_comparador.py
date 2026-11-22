"""Comparação de capturas da regressão visual (Onda 3, parte A). Só Pillow; sem navegador.

A comparação é por pixel, com tolerância declarada abaixo. Duas capturas do mesmo estado, no mesmo
navegador e na mesma máquina, saem idênticas; a tolerância só absorve ruído de borda de glifo e de
compressão de cor, e é apertada de propósito: trocar uma palavra, uma cor de token ou mover um
elemento em 1 px precisa reprovar. Mudança de tamanho da imagem, captura ausente e captura nova
reprovam sempre.

Tolerância (constantes, repetidas no relatório):
  TOLERANCIA_CANAL     um pixel só conta como diferente se algum canal (R, G, B) variar mais do que isto (0..255);
  TOLERANCIA_PIXELS    quantos pixels diferentes uma captura aceita (absoluto);
  TOLERANCIA_REGIAO    maior aglomerado (caixa de células de CELULA px) aceito com diferença, em células.
"""
from __future__ import annotations

import html
import json
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

TOLERANCIA_CANAL = 4
TOLERANCIA_PIXELS = 8
CELULA = 16


@dataclass
class Resultado:
    nome: str
    estado: str                      # igual | dentro_da_tolerancia | diferente | tamanho | ausente | nova
    diferentes: int = 0
    total: int = 0
    maior_canal: int = 0
    regioes: list = field(default_factory=list)   # [(x0, y0, x1, y1)] em pixels, aglomerados de células
    tamanho_referencia: tuple | None = None
    tamanho_atual: tuple | None = None
    caminho_diff: str | None = None

    @property
    def aprovado(self) -> bool:
        return self.estado in ('igual', 'dentro_da_tolerancia')

    @property
    def percentual(self) -> float:
        return 100.0 * self.diferentes / self.total if self.total else 0.0


def _abrir(caminho: Path) -> Image.Image:
    with Image.open(caminho) as imagem:
        return imagem.convert('RGB')


def mascara_diferencas(a: Image.Image, b: Image.Image, tolerancia_canal: int = TOLERANCIA_CANAL) -> Image.Image:
    """Máscara 'L' (255 onde algum canal varia mais do que a tolerância). Exige imagens do mesmo tamanho."""
    dif = ImageChops.difference(a, b)
    r, g, bl = dif.split()
    maior = ImageChops.lighter(ImageChops.lighter(r, g), bl)
    return maior.point(lambda v: 255 if v > tolerancia_canal else 0)


def _regioes(mascara: Image.Image, celula: int = CELULA) -> list:
    """Aglomera as células com diferença em caixas conexas (vizinhança de 8) e devolve as caixas em pixels."""
    largura, altura = mascara.size
    colunas, linhas = -(-largura // celula), -(-altura // celula)
    pequena = mascara.resize((colunas, linhas), Image.Resampling.BOX).point(lambda v: 255 if v > 0 else 0)
    pixels = pequena.load()
    visto = set()
    caixas = []
    for y in range(linhas):
        for x in range(colunas):
            if pixels[x, y] and (x, y) not in visto:
                pilha, minx, miny, maxx, maxy = [(x, y)], x, y, x, y
                visto.add((x, y))
                while pilha:
                    cx, cy = pilha.pop()
                    minx, miny, maxx, maxy = min(minx, cx), min(miny, cy), max(maxx, cx), max(maxy, cy)
                    for dx in (-1, 0, 1):
                        for dy in (-1, 0, 1):
                            nx, ny = cx + dx, cy + dy
                            if 0 <= nx < colunas and 0 <= ny < linhas and pixels[nx, ny] and (nx, ny) not in visto:
                                visto.add((nx, ny))
                                pilha.append((nx, ny))
                caixas.append((minx * celula, miny * celula, min((maxx + 1) * celula, largura), min((maxy + 1) * celula, altura)))
    return sorted(caixas, key=lambda c: (c[1], c[0]))


def comparar_imagens(referencia: Path, atual: Path, nome: str, pasta_diff: Path | None = None,
                     tolerancia_canal: int = TOLERANCIA_CANAL, tolerancia_pixels: int = TOLERANCIA_PIXELS) -> Resultado:
    a, b = _abrir(referencia), _abrir(atual)
    if a.size != b.size:
        return Resultado(nome, 'tamanho', total=max(a.width * a.height, b.width * b.height),
                         tamanho_referencia=a.size, tamanho_atual=b.size)
    total = a.width * a.height
    bruto = ImageChops.difference(a, b)
    maior = max(max(banda.getextrema()) for banda in bruto.split())
    if maior == 0:
        return Resultado(nome, 'igual', total=total, tamanho_referencia=a.size, tamanho_atual=b.size)
    mascara = mascara_diferencas(a, b, tolerancia_canal)
    diferentes = mascara.histogram()[255]
    estado = 'dentro_da_tolerancia' if diferentes <= tolerancia_pixels else 'diferente'
    resultado = Resultado(nome, estado, diferentes=diferentes, total=total, maior_canal=maior,
                          regioes=_regioes(mascara) if diferentes else [],
                          tamanho_referencia=a.size, tamanho_atual=b.size)
    if estado == 'diferente' and pasta_diff is not None:
        pasta_diff.mkdir(parents=True, exist_ok=True)
        resultado.caminho_diff = str(pasta_diff / f'{nome}.diff.png')
        _desenhar_diff(a, b, mascara, resultado.regioes).save(resultado.caminho_diff, optimize=True)
    return resultado


def _desenhar_diff(a: Image.Image, b: Image.Image, mascara: Image.Image, regioes: list) -> Image.Image:
    """Atual esmaecida, pixels diferentes em vermelho e caixas ao redor dos aglomerados."""
    base = Image.blend(b, Image.new('RGB', b.size, (255, 255, 255)), 0.55)
    vermelho = Image.new('RGB', b.size, (230, 20, 20))
    base.paste(vermelho, mask=mascara.filter(ImageFilter.MaxFilter(3)))
    desenho = ImageDraw.Draw(base)
    for x0, y0, x1, y1 in regioes:
        desenho.rectangle((x0, y0, x1 - 1, y1 - 1), outline=(230, 20, 20), width=2)
    return base


def comparar_pastas(referencias: Path, atuais: Path, pasta_diff: Path | None = None,
                    esperados: list | None = None) -> list:
    """Compara por nome. `esperados` (nomes sem extensão) torna ausente/nova captura uma falha explícita."""
    ref = {p.stem: p for p in referencias.glob('*.png')}
    atu = {p.stem: p for p in atuais.glob('*.png')}
    nomes = sorted(set(ref) | set(atu) | set(esperados or ()))
    resultados = []
    for nome in nomes:
        if nome not in atu:
            resultados.append(Resultado(nome, 'ausente'))
        elif nome not in ref:
            resultados.append(Resultado(nome, 'nova'))
        else:
            resultados.append(comparar_imagens(ref[nome], atu[nome], nome, pasta_diff))
    return resultados


def resumo(resultados: list) -> dict:
    contagem = {}
    for r in resultados:
        contagem[r.estado] = contagem.get(r.estado, 0) + 1
    return {'total': len(resultados), 'aprovadas': sum(r.aprovado for r in resultados),
            'reprovadas': sum(not r.aprovado for r in resultados), 'por_estado': contagem,
            'tolerancia': {'canal': TOLERANCIA_CANAL, 'pixels': TOLERANCIA_PIXELS, 'celula_px': CELULA}}


def escrever_relatorio(resultados: list, pasta: Path, referencias: Path, atuais: Path) -> Path:
    """Relatório HTML com referência, atual e diferença lado a lado (só as capturas reprovadas) e relatorio.json."""
    pasta.mkdir(parents=True, exist_ok=True)
    resumo_ = resumo(resultados)
    (pasta / 'relatorio.json').write_text(json.dumps({
        'resumo': resumo_,
        'capturas': [{'nome': r.nome, 'estado': r.estado, 'pixels_diferentes': r.diferentes,
                      'percentual': round(r.percentual, 5), 'maior_variacao_de_canal': r.maior_canal,
                      'regioes': r.regioes, 'tamanho_referencia': r.tamanho_referencia,
                      'tamanho_atual': r.tamanho_atual} for r in resultados]}, ensure_ascii=False, indent=2),
        encoding='utf-8')
    linhas = []
    for r in resultados:
        if r.aprovado:
            continue
        celulas = ''
        if r.estado in ('diferente', 'tamanho'):
            ref_src = Path(Path(referencias).resolve(), r.nome + '.png').as_uri()
            atu_src = Path(Path(atuais).resolve(), r.nome + '.png').as_uri()
            celulas = f'<img src="{ref_src}" alt="referência"><img src="{atu_src}" alt="atual">'
            if r.caminho_diff:
                celulas += f'<img src="{Path(r.caminho_diff).resolve().as_uri()}" alt="diferença">'
        detalhe = ''
        if r.estado == 'diferente':
            detalhe = (f'{r.diferentes} de {r.total} pixels ({r.percentual:.4f}%), maior variação de canal '
                       f'{r.maior_canal}; {len(r.regioes)} região(ões): '
                       + '; '.join(f'({x0},{y0})-({x1},{y1})' for x0, y0, x1, y1 in r.regioes[:12]))
        elif r.estado == 'tamanho':
            detalhe = f'referência {r.tamanho_referencia} × atual {r.tamanho_atual}'
        elif r.estado == 'ausente':
            detalhe = 'há referência, mas a captura não foi feita'
        elif r.estado == 'nova':
            detalhe = 'captura sem referência: gere a linha de base se a tela é nova'
        linhas.append(f'<section><h2>{html.escape(r.nome)} — {r.estado}</h2><p>{html.escape(detalhe)}</p>'
                      f'<div class="trio">{celulas}</div></section>')
    cabecalho = (f"{resumo_['aprovadas']} de {resumo_['total']} capturas dentro da tolerância "
                 f"(canal ≤ {TOLERANCIA_CANAL}, ≤ {TOLERANCIA_PIXELS} pixels); {resumo_['reprovadas']} reprovada(s).")
    corpo = ''.join(linhas) or '<p>Nenhuma diferença acima da tolerância.</p>'
    (pasta / 'relatorio.html').write_text(
        '<!doctype html><meta charset="utf-8"><title>Regressão visual</title>'
        '<style>body{font:14px system-ui;margin:1rem}.trio{display:flex;gap:8px;flex-wrap:wrap}'
        '.trio img{max-width:32%;border:1px solid #888}</style>'
        f'<h1>Regressão visual</h1><p>{html.escape(cabecalho)}</p>{corpo}', encoding='utf-8')
    return pasta / 'relatorio.html'
