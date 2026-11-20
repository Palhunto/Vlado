"""Capturas das telas da fase 06 (quadros de evidência) com dados sintéticos, desktop e celular.

Monta um caso sintético pela demonstração do Core (scripts/demo_evidencias.py: hipóteses, linha do
tempo, comparação e mapa), acrescenta uma tabela de apuração com uma correção manual e abre a Mesa
num servidor local. Sem rede externa e sem modelo. O navegador vem do Playwright em --modulos-node:

    python testes/qa_quadros.py --modulos-node .ferramentas/node/node_modules --saida SAIDA [--chrome CAMINHO]

Sem Playwright, os dados são montados e conferidos, e o script termina com código 3 explicando o que falta.
As capturas não são documentos da apuração.
"""
import argparse
import contextlib
import io
import os
from pathlib import Path
import subprocess
import sys
import threading
import uuid

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / 'scripts'))
sys.path.insert(0, str(RAIZ / 'testes'))
import demo_evidencias as demo  # noqa: E402
from fixture_achados import Ambiente  # noqa: E402
from interface_pesquisa import Servidor  # noqa: E402
import tabelas_apuracao as tabelas  # noqa: E402


def tabela_sintetica(root, ia):
    vinculo = {'referencia': ia('E001'), 'papel': 'suporte', 'suporte': 'sustentado', 'natureza': 'declaracao_documental',
               'justificativa': 'Trecho sintético que traz o valor.'}
    base = lambda **campos: {'caso': demo.CASO, 'requisicao_id': uuid.uuid4().hex, 'autor': 'Editora sintética', **campos}
    criada = tabelas.salvar(root, base(
        titulo='Pagamentos sintéticos', evidencias=[vinculo],
        colunas=[{'id': 'mes', 'nome': 'Mês', 'tipo': 'data'}, {'id': 'valor', 'nome': 'Valor pago', 'tipo': 'monetario', 'moeda': 'BRL'}],
        linhas=[{'celulas': {'mes': {'valor': '2024-01', 'fonte': 0}, 'valor': {'valor': '1200.00', 'fonte': 0}}},
                {'celulas': {'mes': {'valor': '2024-02', 'fonte': 0}, 'valor': {'valor': '1154.50', 'fonte': 0}}},
                {'celulas': {'mes': {'valor': '2024-03'}}}],
        calculos=[{'id': 'total', 'nome': 'Total pago', 'operacao': 'soma', 'coluna': 'valor', 'linhas': ['L0001', 'L0002']}]), 'criar')
    tabelas.corrigir(root, base(id=criada['id'], anterior_sha256=criada['sha256'],
                                correcoes=[{'linha': 'L0002', 'coluna': 'valor', 'valor': '1145.50', 'justificativa': 'Dígitos trocados na transcrição.'}]))
    return tabelas.tabela(root, demo.CASO, criada['id'])


def montar(env):
    """Caso sintético com os cinco quadros; devolve um resumo do que foi gravado."""
    with contextlib.redirect_stdout(io.StringIO()):
        ia, humana = demo.preparar(env)
        quadro = demo.demo_hipoteses(env.root, ia, humana)
        linha = demo.demo_linha(env.root, ia, humana)
        comparacao = demo.demo_comparacao(env.root, env.root / 'origem_comparacao')
        mapa = demo.demo_mapa(env.root, ia, humana)
    tabela = tabela_sintetica(env.root, ia)
    return {'hipoteses': quadro['total'], 'eventos': linha['total'], 'alteracoes': comparacao['total_alteracoes'],
            'entidades': len(mapa['entidades']), 'celulas_corrigidas': tabela['celulas_por_estado']['corrigido_manual']}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--modulos-node', required=True)
    parser.add_argument('--saida', required=True)
    parser.add_argument('--chrome', default='')
    parser.add_argument('--tema', choices=('escuro', 'claro'), default='escuro',
                        help='tema da Mesa nas capturas; o claro acrescenta "-claro" aos nomes dos arquivos')
    args = parser.parse_args()
    saida = Path(args.saida).resolve(); saida.mkdir(parents=True, exist_ok=True)
    env = Ambiente(); server = None
    try:
        resumo = montar(env)
        print(f'Dados sintéticos: {resumo}')
        node_env = {**os.environ, 'NODE_PATH': str(Path(args.modulos_node).resolve())}
        tem = subprocess.run(['node', '-e', "require.resolve('playwright')"], env=node_env, capture_output=True)
        if tem.returncode:
            print(f'Playwright não encontrado em {args.modulos_node}; nenhuma captura foi feita.', file=sys.stderr)
            return 3
        server = Servidor(('127.0.0.1', 0), env.root)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return subprocess.run(['node', str(Path(__file__).with_suffix('.cjs')), server.origin, str(saida), demo.CASO,
                               demo.CASO_COMPARACAO, args.chrome, args.tema], env=node_env).returncode
    finally:
        if server:
            server.shutdown(); server.server_close()
        env.cleanup()


if __name__ == '__main__':
    raise SystemExit(main())
