"""ONE real, paid question through the hosted Mesa, installed from the delivery ZIP.

Consumes provider credits (authorised budget: a single question). Steps:
  1. extract the ZIP into a temporary folder and run the server FROM THERE (install check);
  2. spend caps in configuracao.json; provider choice in ajustes/inferencia.json (no key);
  3. synthetic case registered with the package's own CLI (native text + scanned PDF, local OCR);
  4. first admin created with the package CLI; the activation link goes to a 0600 file and is
     used once by the browser on /ativar (the password is generated here and never printed);
  5. HTTPS test front, sign-in, the question, waiting for the result;
  6. model, time and token use recorded from the server's own files in resultado.json.
The API key is read by the server from VLADO_SEGREDOS (never by this script).

  python testes/qa_pergunta_real.py --zip dist/vlado-XXXX.zip --segredos E:/Vlado/Vlado/segredos/chaves.json \
      --modulos-node .ferramentas/node/node_modules --saida %TEMP%/pergunta_real --chrome "C:/Program Files/Google/Chrome/Application/chrome.exe"
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from proxy_tls_teste import ProxyTLS  # noqa: E402
import dados_sinteticos  # noqa: E402

PERGUNTA = ('Segundo os documentos, qual é o valor global do contrato 041/2025, quanto já havia sido pago '
            'até a medição nº 3, e quem são os sócios da Construtora Horizonte Azul?')
LIMITES = {'tokens_por_consulta': 1_000_000, 'tokens_por_dia': 1_200_000}
CASO = 'vila_serena_sintetico'


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def _esperar(porta: int, segundos: int = 60) -> None:
    fim = time.time() + segundos
    while time.time() < fim:
        try:
            with socket.create_connection(('127.0.0.1', porta), timeout=1):
                return
        except OSError:
            time.sleep(0.5)
    raise SystemExit('O servidor do pacote não abriu a porta.')


def _uso(raiz: Path) -> dict:
    """Sum every integer counter of the per-call usage files written by the server."""
    total, chamadas = {}, 0
    for arquivo in sorted(raiz.glob(f'execucoes/{CASO}/*/saidas/api_uso_*.json')):
        chamadas += 1
        for chave, valor in (json.loads(arquivo.read_text(encoding='utf-8')).get('uso') or {}).items():
            total[chave] = total.get(chave, 0) + valor
    return {'chamadas': chamadas, **total}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--zip', required=True, type=Path)
    parser.add_argument('--segredos', required=True, type=Path)
    parser.add_argument('--modulos-node', required=True)
    parser.add_argument('--saida', required=True, type=Path)
    parser.add_argument('--chrome', default='')
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    saida = args.saida.resolve()
    saida.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='vlado_pacote_') as pasta:
        pasta = Path(pasta)
        with zipfile.ZipFile(args.zip) as zf:
            zf.extractall(pasta)
        raiz = next(p for p in pasta.iterdir() if p.is_dir())
        config = json.loads((raiz / 'configuracao.json').read_text(encoding='utf-8'))
        config['limites'] = LIMITES
        (raiz / 'configuracao.json').write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
        (raiz / 'ajustes').mkdir(exist_ok=True)
        (raiz / 'ajustes/inferencia.json').write_text('{"provedor": "openai", "modelo_preferido": null}', encoding='utf-8')
        env = {**os.environ, 'VLADO_SEGREDOS': str(args.segredos.resolve()), 'VLADO_AMBIENTE': 'homologacao',
               'PYTHONIOENCODING': 'utf-8'}
        for chave in ('VLADO_ACESSO', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY'):
            env.pop(chave, None)
        python = sys.executable
        lotes = dados_sinteticos.gerar(pasta / 'corpus')
        subprocess.run([python, str(raiz / 'scripts/criar_caso.py'), '--id', CASO, '--titulo', 'Vila Serena (sintética)',
                        '--natureza', 'sinteticos', '--documentos', *map(str, lotes['lote1'])],
                       cwd=raiz, env=env, check=True, capture_output=True)
        proxy = ProxyTLS(pasta, 0)
        porta = _porta_livre()
        proxy.destino = ('127.0.0.1', porta)
        link = pasta / 'link.txt'
        subprocess.run([python, str(raiz / 'scripts/acesso.py'), 'criar-admin', '--nome', 'Admin homologação',
                        '--login', 'admin.homolog', '--origem', proxy.origem, '--saida', str(link)],
                       cwd=raiz, env=env, check=True, capture_output=True)
        servidor = subprocess.Popen([python, str(raiz / 'scripts/interface_pesquisa.py'), '--modo', 'piloto',
                                     '--host', '127.0.0.1', '--porta', str(porta), '--sem-abrir', '--origem', proxy.origem],
                                    cwd=raiz, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        inicio = time.time()
        try:
            _esperar(porta)
            node_env = {**os.environ, 'NODE_PATH': args.modulos_node, 'VLADO_QA_LINK': link.read_text(encoding='utf-8').strip(),
                        'VLADO_QA_SENHA': secrets.token_urlsafe(18), 'VLADO_QA_PERGUNTA': PERGUNTA}
            resultado = subprocess.run(['node', str(Path(__file__).with_suffix('.cjs')), proxy.origem, str(saida),
                                        args.chrome, CASO], env=node_env)
            duracao = round(time.time() - inicio, 1)
        finally:
            servidor.terminate()
            servidor.wait(20)
            proxy.fechar()
        uso = _uso(raiz)
        conversas = [json.loads(p.read_text(encoding='utf-8')) for p in raiz.glob('conversas/*/conversa.json')]
        meta = conversas[0] if conversas else {}
        relatorio = {'pacote': args.zip.name, 'instalado_do_pacote': True, 'provedor': 'openai',
                     'modelo_registrado_na_conversa': meta.get('modelo'), 'modelos_informados_pela_api': meta.get('modelos_informados'),
                     'uso_tokens_conversa': meta.get('uso_tokens'), 'estado_final': meta.get('estado'),
                     'situacao': meta.get('situacao'), 'duracao_total_s': duracao, 'uso_tokens': uso,
                     'limites': LIMITES, 'pergunta': PERGUNTA, 'node_saida': resultado.returncode}
        navegador = saida / 'resultado_navegador.json'
        if navegador.is_file():
            relatorio['navegador'] = json.loads(navegador.read_text(encoding='utf-8'))
        (saida / 'resultado.json').write_text(json.dumps(relatorio, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({k: relatorio[k] for k in ('modelo_registrado_na_conversa', 'modelos_informados_pela_api', 'estado_final', 'duracao_total_s',
                                                    'uso_tokens', 'node_saida')}, ensure_ascii=False, indent=2))
        return resultado.returncode


if __name__ == '__main__':
    raise SystemExit(main())
