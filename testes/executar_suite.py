"""Executor das suítes de teste do VLADO (QUAL-03).

    python testes/executar_suite.py              # rápida: a cada commit
    python testes/executar_suite.py --lenta      # só os módulos de suite_lenta.txt: antes de merge
    python testes/executar_suite.py --completa   # tudo; é o que o portão de integração exige
    python testes/executar_suite.py --tempos     # roda módulo a módulo e lista a duração, do mais lento ao mais rápido

Use o Python do `.venv`. `python -m unittest discover -s testes` continua rodando tudo.
"""
import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import unittest

TESTES = Path(__file__).resolve().parent
RAIZ = TESTES.parent
LENTOS = TESTES / 'suite_lenta.txt'


def modulos_lentos():
    if not LENTOS.exists():
        return set()
    linhas = (l.strip() for l in LENTOS.read_text(encoding='utf-8').splitlines())
    return {l for l in linhas if l and not l.startswith('#')}


def modulos():
    return sorted(p.stem for p in TESTES.glob('test_*.py'))


def folhas(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from folhas(item)
        else:
            yield item


def modulo_de(teste):
    """Nome do módulo pelo id do teste; `_FailedTest` de módulo que não importa leva o nome do módulo."""
    if type(teste).__name__ == '_FailedTest':
        return teste._testMethodName.split('.')[0]
    return teste.id().split('.')[0]


def pulos_de_navegador(pulados):
    """Dos `(teste, motivo)` pulados, os que pularam por falta de navegador (Playwright ou Chromium)."""
    return [(teste.id(), motivo) for teste, motivo in pulados if re.search(r'playwright|chromium', motivo, re.I)]


class SelecaoInvalida(Exception):
    pass


def montar(selecao):
    lentos = modulos_lentos()
    desconhecidos = sorted(lentos - set(modulos()))
    if desconhecidos:
        raise SelecaoInvalida('suite_lenta.txt cita módulos sem test_*.py: ' + ', '.join(desconhecidos))
    sys.path.insert(0, str(TESTES))
    todos = unittest.defaultTestLoader.discover(str(TESTES), top_level_dir=str(TESTES))
    suite = unittest.TestSuite()
    por_modulo = {}
    for teste in folhas(todos):
        modulo = modulo_de(teste)
        por_modulo[modulo] = por_modulo.get(modulo, 0) + 1
        if selecao == 'completa' or (selecao == 'lenta') == (modulo in lentos):
            suite.addTest(teste)
    vazios = sorted(m for m in lentos if not por_modulo.get(m))
    if vazios:
        raise SelecaoInvalida('módulos de suite_lenta.txt sem nenhum teste descoberto: ' + ', '.join(vazios))
    if suite.countTestCases() == 0:
        raise SelecaoInvalida(f'a seleção "{selecao}" ficou vazia; um portão sem testes não pode passar.')
    return suite


def medir():
    py = sys.executable
    tempos = []
    for nome in modulos():
        inicio = time.monotonic()
        r = subprocess.run([py, '-m', 'unittest', 'discover', '-s', str(TESTES), '-p', nome + '.py'],
                           cwd=RAIZ, capture_output=True, text=True, encoding='utf-8')
        tempos.append((time.monotonic() - inicio, nome, r.returncode))
    for segundos, nome, codigo in sorted(tempos, reverse=True):
        print(f'{segundos:8.1f}s  {nome}{"  FALHOU" if codigo else ""}')
    print(f'{sum(t[0] for t in tempos):8.1f}s  total')
    return 1 if any(t[2] for t in tempos) else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group()
    g.add_argument('--rapida', action='store_true', help='padrão')
    g.add_argument('--lenta', action='store_true')
    g.add_argument('--completa', action='store_true')
    g.add_argument('--tempos', action='store_true')
    a = ap.parse_args()
    sys.stderr.reconfigure(encoding='utf-8')
    if a.tempos:
        return medir()
    selecao = 'completa' if a.completa else 'lenta' if a.lenta else 'rapida'
    if selecao in ('completa', 'lenta'):
        # Portões de merge: sem Node o teste falha. O pulo fica só para a execução avulsa e a rápida local.
        os.environ.setdefault('VLADO_EXIGIR_NODE', '1')
    try:
        suite = montar(selecao)
    except SelecaoInvalida as erro:
        print(f'ERRO: {erro}', file=sys.stderr)
        return 2
    resultado = unittest.TextTestRunner(verbosity=1).run(suite)
    if os.environ.get('VLADO_EXIGIR_PLAYWRIGHT') == '1':
        # Rede de segurança do CI: teste de navegador que pulou, por qualquer caminho, reprova a execução.
        pulos = pulos_de_navegador(resultado.skipped)
        if pulos:
            print('ERRO: com VLADO_EXIGIR_PLAYWRIGHT=1 nenhum teste de navegador pode pular:', file=sys.stderr)
            for teste, motivo in pulos:
                print(f'  {teste}: {motivo}', file=sys.stderr)
            return 1
    return 0 if resultado.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(main())
