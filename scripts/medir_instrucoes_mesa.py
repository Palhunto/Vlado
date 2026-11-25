"""Mede, sem chamar nenhuma API, o que a Mesa manda ao modelo em cada etapa: no modo legado e no modo mesa.

Os dois lados chamam de verdade ``codex_apuracao.Conversas._instructions`` (a instrução de sistema) e
``fluxo_codex.Fluxo.prompt`` (cada turno de etapa), sobre uma pasta de rodada temporária que congela os arquivos
do projeto como a ``nova_rodada`` faz: AGENTS.md, README.md, configuracao.json, todo ``prompts/*.md`` e o
``manifesto_prompts.json``. Nada do projeto é gravado. O modo sai do manifesto congelado (``instrucoes_mesa``):

- ``antes`` (legado): o manifesto sem a chave ``mesa``, como numa rodada de antes da 1.5.0. A instrução é AGENTS.md,
  prompts/FLUXO_COMPLETO.md, README.md, a adaptação de transporte e o JSON da rodada; o formato da etapa é o do Python.
- ``depois`` (mesa): o manifesto do projeto, com a chave ``mesa``. A instrução é o bloco ``mesa:sistema`` mais o
  mesmo JSON da rodada, e cada turno leva o bloco ``mesa:controle`` preenchido e o ``mesa:formato:<etapa>``.

Nos dois casos entram a descrição da ferramenta ``consultar_acervo`` (igual nos dois) e, no turno, os dados
das etapas anteriores, que aqui estão vazios: eles crescem igual nos dois fluxos e ficam fora da comparação.

Os tokens são ESTIMADOS por caracteres (``CARACTERES_POR_TOKEN``, com a faixa de ``FAIXA``): a contagem exata
depende do tokenizador de cada provedor e só sai pela API de contagem, que este script não chama.

Uso: python scripts/medir_instrucoes_mesa.py [--json] [--chamadas N]
"""
from __future__ import annotations

import argparse
from decimal import Decimal, ROUND_HALF_UP
import json
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comum import ROOT, escrever_json, ler_json  # noqa: E402
from instrucoes_mesa import BLOCO, ETAPAS, blocos_mesa  # noqa: E402,F401  (BLOCO e blocos_mesa: nomes de antes)

CARACTERES_POR_TOKEN = 3.5  # estimativa central para português com JSON e Markdown
FAIXA = (4.0, 3.0)  # menos tokens (4 caracteres por token) e mais tokens (3 por token)
# Chamadas ao modelo numa pergunta medida de ponta a ponta (docs/VERIFICACAO.md, pergunta real de 15/11/2026).
CHAMADAS_POR_PERGUNTA = 22
MODELOS = ('claude-sonnet-5-5', 'gpt-6.1-sol')  # os permitidos no orçamento padrão de precos_modelos.json
PERGUNTA = 'Qual foi o valor pago pelo contrato e quem assinou o aditivo?'


def tokens(caracteres: int, por_token: float = CARACTERES_POR_TOKEN) -> int:
    return int(Decimal(caracteres / por_token).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _medida(texto: str) -> dict:
    n = len(texto)
    return {'caracteres': n, 'tokens_estimados': tokens(n),
            'faixa_tokens': [tokens(n, FAIXA[0]), tokens(n, FAIXA[1])]}


def _rodada_temporaria(root: Path, pasta: Path, manifesto: dict) -> tuple[Path, dict]:
    """Pasta de rodada com o que ``nova_rodada`` congela em ``entradas/`` (sem o corpus, que a medida não lê)."""
    run = pasta / 'execucoes' / 'caso-medida' / 'R001'
    entradas = run / 'entradas'
    (entradas / 'prompts').mkdir(parents=True)
    (run / 'saidas').mkdir()
    for relativo in ('AGENTS.md', 'README.md', 'configuracao.json'):
        if (root / relativo).is_file():
            shutil.copyfile(root / relativo, entradas / relativo)
    for arquivo in sorted((root / 'prompts').glob('*.md')):
        shutil.copyfile(arquivo, entradas / 'prompts' / arquivo.name)
    escrever_json(entradas / 'prompts' / 'manifesto_prompts.json', manifesto)
    meta = {'caso': 'caso-medida', 'rodada': 'R001', 'corpus_id': 'c' * 64, 'modelo': None}
    return run, meta


def _textos(root: Path, run: Path, meta: dict, pergunta: str) -> dict:
    import codex_apuracao
    from fluxo_codex import Fluxo
    falso = SimpleNamespace(contexts={'medida': {'meta': meta}})
    fluxo = Fluxo(root, run, meta, references={})  # the mode comes from the frozen manifest of the round
    turnos = {}
    for etapa in ETAPAS:
        fluxo.stage, fluxo.attempt = etapa, 1  # sem begin(): nada é gravado no estado do fluxo
        turnos[etapa] = fluxo.prompt(pergunta)
    return {'modo': fluxo.instrucoes['modo'], 'sistema': codex_apuracao.Conversas._instructions(falso, 'medida', run),
            'ferramentas': json.dumps(codex_apuracao.TOOLS, ensure_ascii=False), 'turnos': turnos}


def montar(root: Path = ROOT, pergunta: str = PERGUNTA) -> dict:
    """Os textos de cada modo: {'antes'|'depois': {'modo', 'sistema', 'ferramentas', 'turnos': {etapa: texto}}}."""
    manifesto = ler_json(root / 'prompts' / 'manifesto_prompts.json')
    legado = {k: v for k, v in manifesto.items() if k != 'mesa'}
    textos = {}
    for lado, congelado in (('antes', legado), ('depois', manifesto)):
        with tempfile.TemporaryDirectory(prefix='vlado-medida-') as pasta:
            run, meta = _rodada_temporaria(root, Path(pasta), congelado)
            textos[lado] = _textos(root, run, meta, pergunta)
    return textos


def _usd(tokens_por_chamada: int, chamadas: int, preco: dict) -> dict:
    """Dólares da parte fixa (sistema + ferramenta) numa pergunta: sem cache e com 1 escrita + leituras."""
    escrita = next(v for k, v in sorted(preco.items()) if k.startswith('cache_escrita'))
    milhao = Decimal(1_000_000)
    sem = Decimal(str(preco['entrada'])) * tokens_por_chamada * chamadas / milhao
    com = (Decimal(str(escrita)) * tokens_por_chamada
           + Decimal(str(preco['cache_leitura'])) * tokens_por_chamada * (chamadas - 1)) / milhao
    q = Decimal('0.0001')
    return {'sem_cache': str(sem.quantize(q)), 'com_cache': str(com.quantize(q))}


def medir(root: Path = ROOT, pergunta: str = PERGUNTA, chamadas: int = CHAMADAS_POR_PERGUNTA) -> dict:
    textos = montar(root, pergunta)
    precos = {m: p for prov in ler_json(root / 'precos_modelos.json')['modelos'].values()
              for m, p in prov.items() if m in MODELOS}
    resultado = {'estimativa': {'caracteres_por_token': CARACTERES_POR_TOKEN, 'faixa': list(FAIXA),
                                'chamadas_por_pergunta': chamadas}}
    for lado, t in textos.items():
        fixa = len(t['sistema']) + len(t['ferramentas'])
        resultado[lado] = {
            'modo': t['modo'], 'sistema': _medida(t['sistema']), 'ferramentas': _medida(t['ferramentas']),
            'turnos': {e: _medida(x) for e, x in t['turnos'].items()},
            'parte_fixa_por_chamada': _medida('x' * fixa),
            'parte_fixa_por_pergunta_usd': {m: _usd(tokens(fixa), chamadas, p) for m, p in precos.items()}}
    a, d = resultado['antes'], resultado['depois']
    resultado['reducao_parte_fixa'] = {
        'caracteres': a['parte_fixa_por_chamada']['caracteres'] - d['parte_fixa_por_chamada']['caracteres'],
        'percentual': round(100 * (1 - d['parte_fixa_por_chamada']['caracteres']
                                   / a['parte_fixa_por_chamada']['caracteres']), 1)}
    return resultado


def _tabela(r: dict) -> str:
    linhas = [f"Estimativa: {r['estimativa']['caracteres_por_token']} caracteres por token "
              f"(faixa {r['estimativa']['faixa'][0]} a {r['estimativa']['faixa'][1]}); "
              f"{r['estimativa']['chamadas_por_pergunta']} chamadas por pergunta.", '',
              f"{'parte':<28}{'antes (car.)':>14}{'tokens':>9}{'depois (car.)':>15}{'tokens':>9}"]
    a, d = r['antes'], r['depois']
    pares = [('sistema', a['sistema'], d['sistema']), ('ferramenta', a['ferramentas'], d['ferramentas']),
             ('fixa por chamada', a['parte_fixa_por_chamada'], d['parte_fixa_por_chamada'])]
    pares += [(f'turno {e}', a['turnos'][e], d['turnos'][e]) for e in ETAPAS]
    for nome, x, y in pares:
        linhas.append(f"{nome:<28}{x['caracteres']:>14}{x['tokens_estimados']:>9}"
                      f"{y['caracteres']:>15}{y['tokens_estimados']:>9}")
    linhas += ['', f"Redução da parte fixa: {r['reducao_parte_fixa']['caracteres']} caracteres "
                   f"({r['reducao_parte_fixa']['percentual']}%).", '',
               'Parte fixa por pergunta, em US$ (sem cache / com 1 escrita e as demais leituras de cache):']
    for modelo in a['parte_fixa_por_pergunta_usd']:
        x, y = a['parte_fixa_por_pergunta_usd'][modelo], d['parte_fixa_por_pergunta_usd'][modelo]
        linhas.append(f"  {modelo}: antes {x['sem_cache']} / {x['com_cache']}; depois {y['sem_cache']} / {y['com_cache']}")
    return '\n'.join(linhas)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--json', action='store_true', help='saída em JSON')
    parser.add_argument('--chamadas', type=int, default=CHAMADAS_POR_PERGUNTA,
                        help='chamadas ao modelo por pergunta (padrão: a medida de docs/VERIFICACAO.md)')
    args = parser.parse_args(argv)
    if args.chamadas < 1:
        parser.error('--chamadas deve ser ao menos 1.')
    resultado = medir(chamadas=args.chamadas)
    print(json.dumps(resultado, ensure_ascii=False, indent=2) if args.json else _tabela(resultado))


if __name__ == '__main__':
    main()
