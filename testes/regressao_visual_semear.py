"""Prepara a pasta de dados SINTÉTICOS da regressão visual (roda no Python do projeto, com as dependências).

    python testes/regressao_visual_semear.py <pasta de dados nova>

Usa só `vlado_lancador.preparar_dados` e `semear_ambiente.semear` (casos vila_serena_sintetico e
campo_verde_aditivo_sintetico, de `dados_sinteticos.py`). Nunca toca em `casos/` do projeto: recusa uma
pasta que já exista e não esteja vazia, e confere ao final que só há os dois casos sintéticos.
Os links de ativação das contas de demonstração vão para um arquivo ao lado da pasta e são apagados.
Depois grava a rodada sintética completa de `regressao_visual_rodada.py` (sem chamada de modelo).
"""
import json
from pathlib import Path
import sys

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))


def main(argv):
    if len(argv) != 2:
        raise SystemExit(__doc__)
    pasta = Path(argv[1]).resolve()
    if pasta == RAIZ or RAIZ in pasta.parents and pasta.name in ('casos', 'execucoes'):
        raise SystemExit('Recusado: a pasta de dados da regressão visual não pode ser a do projeto.')
    if pasta.exists() and any(pasta.iterdir()):
        raise SystemExit(f'Recusado: {pasta} já existe e não está vazia.')
    import semear_ambiente
    import vlado_lancador
    vlado_lancador.preparar_dados(pasta, RAIZ)
    links = pasta.parent / (pasta.name + '.links.txt')
    try:
        feitos = semear_ambiente.semear(pasta, 'demonstracao', 'http://127.0.0.1:1', links)
    finally:
        links.unlink(missing_ok=True)
    catalogo = json.loads((pasta / 'casos/catalogo.json').read_text(encoding='utf-8'))['casos']
    ids = sorted(c['id'] for c in catalogo)
    esperados = sorted((semear_ambiente.CASO_A, semear_ambiente.CASO_B))
    if ids != esperados:
        raise SystemExit(f'Casos inesperados na pasta semeada: {ids}')
    import regressao_visual_rodada
    resumo = regressao_visual_rodada.semear_rodada(pasta)
    print(json.dumps({'casos': ids, 'contas': feitos['contas'], 'rodada': resumo}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
