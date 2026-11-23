"""Homologação ponta a ponta da Mesa em MODO HOSPEDADO (login real), no navegador, sem inferência paga.

    python testes/qa_homologacao.py --modulos-node .ferramentas/node/node_modules --saida PASTA_TEMPORARIA \
        --chrome "C:/Program Files/Google/Chrome/Application/chrome.exe" [--capturas docs/capturas/homologacao]

Monta, numa raiz temporária: servidor `modo='piloto'` atrás de um proxy TLS de teste (certificado
autoassinado, aceito só neste contexto por `ignoreHTTPSErrors`), `VLADO_AMBIENTE=homologacao`,
contas reais pela API de `scripts/acesso.py` (admin, convidado A com o caso `alpha`, convidado B com o
caso `beta`) e o corpus sintético de `scripts/dados_sinteticos.py` (lote 1: PDF com texto + PDF
digitalizado que passa por OCR local; lote 2: aditivo). A IA é o provedor simulado (`BrowserFake`).

As senhas são geradas na hora e chegam ao Node só pelo ambiente do processo filho; nunca são impressas
nem gravadas. O roteiro do navegador (`qa_homologacao.cjs`) pede conferências ao Python por um canal de
linhas (`@@PY {json}` na saída do Node, resposta JSON na entrada), por exemplo os SHA-256 da rodada
anterior antes e depois do segundo lote. O resultado fica em `PASTA/resultado.json`.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
import threading

TESTES = Path(__file__).resolve().parent
RAIZ_REPO = TESTES.parent
sys.path.insert(0, str(RAIZ_REPO / 'scripts'))
sys.path.insert(0, str(TESTES))
from test_codex_integracao import CodexIntegrationTest  # noqa: E402
from qa_codex import BrowserFake  # noqa: E402
from proxy_tls_teste import ProxyTLS  # noqa: E402
from interface_pesquisa import Servidor  # noqa: E402
from comum import sha256, ler_json  # noqa: E402
import acesso  # noqa: E402
import correio  # noqa: E402
import apuracao  # noqa: E402
import ocr  # noqa: E402
import dados_sinteticos  # noqa: E402

# Search terms tried, in order, when the fixture's default term finds nothing in the selected corpus.
TERMOS_ALTERNATIVOS = ('Horizonte', 'Construtora', 'contrato')


class BrowserHomologacao(BrowserFake):
    """BrowserFake with one provider thread per conversation (several accounts ask in parallel) and
    a search stage that also finds a passage in the synthetic newsroom PDFs."""

    def __init__(self, root, callback):
        super().__init__(root, callback)
        self.threads = 0
        self.turnos: dict[str, str] = {}  # turn id -> thread id
        self.local = threading.local()

    def call(self, method, params=None):
        if method == 'thread/start':
            result = super().call(method, params)
            self.threads += 1
            return {**result, 'thread': {'id': f'thread-qa-{self.threads}'}}
        if method == 'thread/resume':
            return {**super().call(method, params), 'thread': {'id': params['threadId']}}
        if method == 'turn/interrupt':
            self.calls.append((method, params))
            super().emit('turn/completed', {'threadId': params['threadId'],
                                            'turn': {'id': params['turnId'], 'status': 'interrupted'}})
            return {}
        if method == 'turn/start':
            with self.answers:
                self.turnos[f'turn-{self.turn_number + 1}'] = params['threadId']
        return super().call(method, params)

    def drive(self, text, turn_id):
        self.local.thread = self.turnos[turn_id]
        super().drive(text, turn_id)

    def emit(self, method, params=None, request=None):
        thread = getattr(self.local, 'thread', None)
        if thread and 'threadId' not in (params or {}):
            params = {'threadId': thread, **(params or {})}
        if method == 'item/tool/call' and (params or {}).get('arguments', {}).get('acao') == 'buscar':
            return self._buscar_com_alternativas(params, request)
        return super().emit(method, params, request)

    def _buscar_com_alternativas(self, params, request):
        for termo in (params['arguments']['consulta'], *TERMOS_ALTERNATIVOS):
            super().emit('item/tool/call', {**params, 'arguments': {**params['arguments'], 'consulta': termo}},
                         request=request)
            resposta = self.answer(request)['result']
            if not resposta['success'] or json.loads(resposta['contentItems'][0]['text']).get('retornados'):
                return None
            with self.answers:  # discard the empty answer and ask again with the same request id
                self.sent = [m for m in self.sent if m.get('id') != request]
        return None


def _senha() -> str:
    return secrets.token_urlsafe(24)


def _conta(root: Path, nome: str, login: str, papel: str, casos=(), email: str | None = None) -> dict:
    registro, token = acesso.criar_conta(root, nome, login, papel=papel, casos=list(casos), por='qa_homologacao')
    senha = _senha()
    acesso.ativar(root, token, senha)
    if email:   # a Equipe só recupera por e-mail quem tem um: o endereço entra pelo mesmo caminho de Minha conta (pedido + link de confirmação)
        acesso.confirmar_email(root, acesso.pedir_troca_de_email(root, registro['id'], email, senha)['token'])
    return {'id': registro['id'], 'login': login, 'senha': senha, 'nome': nome, 'email': email}


def _arquivos(pasta: Path) -> dict[str, str]:
    if not pasta.is_dir():
        return {}
    return {p.relative_to(pasta).as_posix(): sha256(p) for p in sorted(pasta.rglob('*')) if p.is_file()}


class Canal:
    """Answers the browser script's requests for checks that only Python can do."""

    def __init__(self, root: Path):
        self.root = root
        self.instantaneos: dict[str, tuple[Path, dict]] = {}

    def responder(self, pedido: dict) -> dict:
        cmd = pedido.get('cmd')
        if cmd == 'instantaneo':
            caso, rodada = pedido['caso'], pedido['rodada']
            if not re.fullmatch(r'[a-z0-9_-]{1,64}', caso) or not re.fullmatch(r'R\d{3}', rodada):
                raise ValueError('escopo inválido')
            pasta = self.root / 'execucoes' / caso / rodada
            self.instantaneos[pedido['nome']] = (pasta, _arquivos(pasta))
            return {'arquivos': len(self.instantaneos[pedido['nome']][1])}
        if cmd == 'link_recuperacao':   # o link da mensagem de recuperação que a Equipe mandou a essa pessoa; vai só ao roteiro, que o abre e não o grava
            enviadas = [m for m in correio.caixa() if m['tipo'] == 'recuperacao' and m['para'] == pedido['para']]
            if not enviadas:
                raise ValueError('nenhuma mensagem de recuperação para essa pessoa')
            return {'link': enviadas[-1]['link']}
        if cmd == 'comparar':
            pasta, antes = self.instantaneos[pedido['nome']]
            depois = _arquivos(pasta)
            return {'total': len(antes), 'alterados': [k for k, v in antes.items() if depois.get(k, v) != v],
                    'removidos': [k for k in antes if k not in depois]}
        if cmd == 'conversa':
            meta = ler_json(self.root / 'conversas' / pedido['id'] / 'conversa.json')
            return {'caso': meta.get('caso'), 'dono': meta.get('dono'), 'rodadas': meta.get('rodadas')}
        if cmd == 'contas':
            return {'contas': {c['login']: {'situacao': c['situacao'], 'casos': c.get('casos')}
                               for c in acesso.listar(self.root)}}
        raise ValueError('comando desconhecido')


def _rodar_node(args, origem: str, saida: Path, capturas: Path, contas: dict, esperado: dict, canal: Canal) -> int:
    env = {**os.environ, 'NODE_PATH': str(Path(args.modulos_node).resolve()),
           'VLADO_QA_CONTAS': json.dumps(contas), 'VLADO_QA_ESPERADO': json.dumps(esperado)}
    processo = subprocess.Popen(['node', str(Path(__file__).with_suffix('.cjs')), origem, str(saida), str(capturas),
                                 args.chrome], env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                text=True, encoding='utf-8', errors='replace', bufsize=1)
    vigia = threading.Timer(1500, processo.kill)
    vigia.start()
    try:
        for linha in processo.stdout:
            if not linha.startswith('@@PY '):
                sys.stdout.write(linha)
                sys.stdout.flush()
                continue
            try:
                resposta = {'ok': True, **canal.responder(json.loads(linha[5:]))}
            except (ValueError, KeyError, OSError) as exc:
                resposta = {'ok': False, 'erro': f'{type(exc).__name__}: {exc}'}
            processo.stdin.write(json.dumps(resposta) + '\n')
            processo.stdin.flush()
        return processo.wait()
    finally:
        vigia.cancel()
        if processo.poll() is None:
            processo.kill()


def _conferencias_finais(root: Path, contas: dict, saida: Path) -> list[str]:
    """Checks on the server state after the browser script, appended to resultado.json."""
    feitas = []
    por_login = {c['login']: c for c in acesso.listar(root)}
    assert por_login[contas['b']['login']]['situacao'] == 'desativada', por_login[contas['b']['login']]
    assert por_login[contas['a']['login']]['casos'] == ['beta'], por_login[contas['a']['login']]
    assert por_login[contas['a']['login']]['situacao'] == 'ativa', por_login[contas['a']['login']]
    feitas.append('Registro de acesso: B desativado e A só com o caso beta, ativa com a senha nova depois de usar o link de recuperação.')
    registro = (saida / 'resultado.json')
    dados = ler_json(registro)
    conversas_a = [p for p in (root / 'conversas').glob('*/conversa.json')
                   if ler_json(p).get('dono') == contas['a']['id']]
    assert conversas_a and all(ler_json(p)['caso'] == 'alpha' for p in conversas_a)
    feitas.append(f'{len(conversas_a)} conversa(s) do convidado A gravadas com dono = conta A e caso alpha.')
    caso = dados['caso_reportagem']
    notas = apuracao.listar(root, caso)['notas']
    assert any('[Fonte' in n['texto'] or n.get('fontes') for n in notas), notas
    feitas.append('Nota do Caderno gravada no servidor com a fonte inserida.')
    texto = registro.read_text(encoding='utf-8')
    for conta in contas.values():
        assert conta['senha'] not in texto, 'senha vazou no resultado'
    for arquivo in saida.rglob('*'):
        if arquivo.is_file() and arquivo.suffix in ('.json', '.txt', '.log'):
            conteudo = arquivo.read_text(encoding='utf-8', errors='replace')
            assert '/ativar/' not in conteudo and not any(c['senha'] in conteudo for c in contas.values()), arquivo
    feitas.append('Nenhuma senha nem link de ativação nos artefatos da saída.')
    dados['verificacoes_python'] = feitas
    registro.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding='utf-8')
    return feitas


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--modulos-node', required=True)
    parser.add_argument('--saida', required=True)
    parser.add_argument('--chrome', default='')
    parser.add_argument('--capturas', default=str(RAIZ_REPO / 'docs' / 'capturas' / 'homologacao'))
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    saida = Path(args.saida).resolve()
    saida.mkdir(parents=True, exist_ok=True)
    capturas = Path(args.capturas).resolve()
    capturas.mkdir(parents=True, exist_ok=True)
    fx = CodexIntegrationTest()
    fx.setUp()
    root = fx.root
    externo = tempfile.TemporaryDirectory(prefix='vlado_homolog_')
    ambiente_antes = {k: os.environ.get(k) for k in ('VLADO_ACESSO', 'VLADO_AMBIENTE')}
    os.environ['VLADO_ACESSO'] = str(root / 'acesso' / 'acesso.json')
    os.environ['VLADO_AMBIENTE'] = 'homologacao'
    acesso.limpar_limites()
    # O correio é o simulado (em memória): a recuperação de acesso manda um link por e-mail e só o Python o lê, a pedido do roteiro (nunca é impresso).
    pilha = contextlib.ExitStack()
    pilha.enter_context(correio.usar('simulado'))
    correio.limpar_caixa()
    server = proxy = thread = None
    try:
        lotes = dados_sinteticos.gerar(Path(externo.name) / 'corpus')
        esperado = {'lotes': {lote: [{'caminho': str(p), 'nome': p.name, 'sha256': sha256(p)} for p in arquivos]
                              for lote, arquivos in lotes.items()},
                    'digitalizado': lotes['lote1'][1].name,
                    # Sem Tesseract e os idiomas, o PDF digitalizado fica "Sem texto lido": o roteiro não exige OCR, e diz que pulou.
                    'ocr_disponivel': bool(ocr._tesseract_disponivel())}
        contas = {'admin': _conta(root, 'Administração QA', 'admin.qa', 'admin'),
                  'a': _conta(root, 'Convidada A', 'convidada.a', 'convidado', ['alpha'], email='convidada.a@exemplo.org'),
                  'b': _conta(root, 'Convidado B', 'convidado.b', 'convidado', ['beta'])}
        # The proxy needs the server port and the server needs the proxy origin: open the proxy first,
        # with its destination filled in once the server is bound (it is read per connection).
        tls = Path(externo.name) / 'tls'
        tls.mkdir()
        proxy = ProxyTLS(tls, 0)
        server = Servidor(('127.0.0.1', 0), root, modo='piloto', origem=proxy.origem)
        proxy.destino = ('127.0.0.1', server.server_port)
        server.conversas.factory = BrowserHomologacao
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        codigo = _rodar_node(args, proxy.origem, saida, capturas, contas, esperado, Canal(root))
        if codigo:
            return codigo
        for linha in _conferencias_finais(root, contas, saida):
            print('Python:', linha)
        print('QA homologação: OK')
        return 0
    finally:
        if server:
            server.shutdown()
            server.server_close()
        if thread:
            thread.join(3)
        if proxy:
            proxy.fechar()
        pilha.close()
        for chave, valor in ambiente_antes.items():
            if valor is None:
                os.environ.pop(chave, None)
            else:
                os.environ[chave] = valor
        externo.cleanup()
        fx.doCleanups()


if __name__ == '__main__':
    raise SystemExit(main())
