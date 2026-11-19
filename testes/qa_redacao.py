"""Capturas das telas da fase 08 (conferência do texto e entrevistas) com dados sintéticos, desktop e celular.

Monta um caso sintético pela demonstração do Core (hipóteses com lacunas), acrescenta um texto em
conferência com evidências vinculadas e uma pergunta preparada, e abre a Mesa num servidor local.
Sem rede externa e sem modelo. O navegador vem do Playwright em --modulos-node:

    python testes/qa_redacao.py --modulos-node .ferramentas/node/node_modules --saida SAIDA [--chrome CAMINHO]

Sem Playwright, os dados são montados e conferidos, e o script termina com código 3. As capturas
não são documentos da apuração. O modo local não tem conta: a tela mostra o aviso no lugar do botão
de revisão humana, como deve.
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
import conferencia_redacao as redacao  # noqa: E402
import demo_evidencias as demo  # noqa: E402
import entrevistas  # noqa: E402
from fixture_achados import Ambiente  # noqa: E402
from interface_pesquisa import Servidor  # noqa: E402

TEXTO = ('A fonte declara valor 12. Segundo a fonte, todos os contratos provocaram o atraso. '
         'O valor foi pago em 2021.\nA obra parou em março por causa da chuva.')


def montar(env):
    """Caso sintético com um texto em conferência e uma pergunta; devolve um resumo do que foi gravado."""
    with contextlib.redirect_stdout(io.StringIO()):
        ia, _ = demo.preparar(env)
        demo.demo_hipoteses(env.root, ia, _)
    base = lambda **campos: {'caso': demo.CASO, 'requisicao_id': uuid.uuid4().hex, 'autor': 'Repórter sintética', **campos}
    vinculo = lambda eid, suporte='sustentado': {'referencia': ia(eid), 'papel': 'suporte', 'suporte': suporte,
                                                 'natureza': 'declaracao_documental', 'justificativa': 'Vínculo sintético.'}
    texto = redacao.criar(env.root, base(titulo='Reportagem sintética sobre o contrato', texto=TEXTO))
    for indice, eid in ((0, 'E001'), (1, 'E001')):
        claim = texto['estado']['afirmacoes'][indice]
        texto = redacao.vincular(env.root, base(id=texto['id'], anterior_sha256=texto['sha256'], afirmacao_id=claim['id'],
                                                evidencias=[vinculo(eid)]))
    lacuna = next(r for r in entrevistas.lacunas(env.root, demo.CASO)['lacunas'] if r['origem']['tipo'] == 'hipotese')
    entrevistas.preparar(env.root, base(origem=lacuna['origem'], tipo='pedido_lai', destinatario='Prefeitura sintética',
                                        responsavel='Repórter sintética', prazo='2026-12-01'))
    visao = redacao.conferencia(env.root, demo.CASO, texto['id'])
    return {'afirmacoes': visao['resumo']['total'], 'por_estado': visao['resumo']['por_estado'],
            'lacunas': entrevistas.lacunas(env.root, demo.CASO)['total'],
            'perguntas': entrevistas.listar(env.root, demo.CASO)['total']}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--modulos-node', required=True)
    parser.add_argument('--saida', required=True)
    parser.add_argument('--chrome', default='')
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
                               args.chrome], env=node_env).returncode
    finally:
        if server:
            server.shutdown(); server.server_close()
        env.cleanup()


if __name__ == '__main__':
    raise SystemExit(main())
