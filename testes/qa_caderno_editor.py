"""Caderno editor acceptance in a real browser (frente B), on synthetic notes in a temporary folder.

Covers the task-list checkbox (layout, click/keyboard, saved without typing, reload, visual and
Markdown round trip), the style selector (three styles and legacy levels), the per-tab draft after a
simulated network failure and reload, a conflict between two tabs, the return to the writing point
after opening an original, 320/390 px without horizontal scroll, and light and dark themes.

    python testes/qa_caderno_editor.py --modulos-node .ferramentas/node/node_modules \
        --saida %TEMP%/qa_caderno_editor [--capturas docs/capturas/caderno] [--chrome CAMINHO]

Local mode only (127.0.0.1), no login, no model calls and no external navigation.
"""
import argparse
import os
from pathlib import Path
import subprocess
import threading
import uuid

from fixture_achados import Ambiente
from interface_pesquisa import Servidor
from indice_sqlite import pesquisar
import apuracao

TAREFAS = ('Lista de checagem da pauta sintética:\n\n'
           '- [ ] Ligar para a assessoria fictícia\n'
           '- [x] Conferir o contrato sintético\n'
           '- [ ] Item longo que ocupa várias linhas para conferir o alinhamento da caixa com o texto '
           'quando a linha quebra em telas estreitas e também em telas largas do computador\n\n'
           'Parágrafo final da nota sintética.')
LEGADA = '# Título antigo\n\nTexto de uma nota anterior ao seletor.\n\n#### Detalhe antigo\n\nMais texto sintético.'
ESTILOS = 'Primeiro parágrafo sintético para estilos.\n\nSegundo parágrafo sintético.'
RASCUNHO = 'Texto salvo da nota de rascunho.'
LONGO = '\n\n'.join(f'Parágrafo sintético {n} com texto de preenchimento para a nota ficar longa e exigir rolagem.'
                    for n in range(1, 25))


class ServidorQA(Servidor):
    # Chrome opens many connections at once; the default backlog of 5 refuses some on Windows.
    request_queue_size = 128


def salvar(root, titulo, texto, **extra):
    data = {'caso': 'alpha', 'requisicao_id': uuid.uuid4().hex, 'titulo': titulo, 'texto': texto, **extra}
    return apuracao.alterar_nota(root, 'apuracao-salvar', data)


def semear(root):
    salvar(root, 'Fonte e retorno', LONGO)
    hit = pesquisar(root, 'alpha', 'R001', 'valor')['resultados'][0]
    nota = apuracao.listar_notas(root, 'alpha')['notas'][0]
    apuracao.alterar_nota(root, 'apuracao-adicionar', {
        'caso': 'alpha', 'requisicao_id': uuid.uuid4().hex, 'nota_id': nota['id'], 'revisao_nota': nota['revisao'],
        'origem': {'tipo': 'pesquisa', 'rodada': 'R001', 'geracao': 'v1', 'referencia': hit['referencia'], 'texto': 'valor 12.'}})
    salvar(root, 'Nota legada', LEGADA)
    salvar(root, 'Estilos', ESTILOS)
    salvar(root, 'Rascunho', RASCUNHO)
    salvar(root, 'Tarefas da pauta', TAREFAS)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--node', default='node'); parser.add_argument('--modulos-node', required=True)
    parser.add_argument('--saida', required=True); parser.add_argument('--capturas', default='')
    parser.add_argument('--chrome', default='')
    args = parser.parse_args()
    output = Path(args.saida).resolve(); output.mkdir(parents=True, exist_ok=True)
    shots = Path(args.capturas).resolve() if args.capturas else output / 'capturas'
    shots.mkdir(parents=True, exist_ok=True)
    fx = Ambiente()
    server = None
    try:
        semear(fx.root)
        server = ServidorQA(('127.0.0.1', 0), fx.root)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        result = subprocess.run([args.node, str(Path(__file__).with_suffix('.cjs')), server.origin, str(output), str(shots), args.chrome],
                                env={**os.environ, 'NODE_PATH': str(Path(args.modulos_node).resolve())}, timeout=600)
        if result.returncode:
            return result.returncode
        notas = {n['titulo']: n for n in apuracao.listar(fx.root, 'alpha')['notas']}
        texto = notas['Tarefas da pauta']['texto']
        assert '- [x] Ligar para a assessoria fictícia' in texto, texto
        assert '- [ ] Tarefa nova sintética' in texto, texto
        assert 'Escrito sem conexão.' in notas['Rascunho']['texto'], notas['Rascunho']['texto']
        assert notas['Nota legada']['texto'].startswith('Título antigo'), notas['Nota legada']['texto']
        assert '#### Detalhe antigo' in notas['Nota legada']['texto']
        return 0
    finally:
        if server:
            server.shutdown(); server.server_close(); thread.join(3)
        fx.cleanup()


if __name__ == '__main__':
    raise SystemExit(main())
