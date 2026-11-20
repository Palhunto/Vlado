"""Optional loopback search UI. Uses existing snapshot/index validation and raw logs.

Routes live in the ``rotas_*`` modules (accounts and sessions, conversation, management,
downloads, static files, notebook, findings, evidence boards, tables, story review); this
file keeps the server, request reading, origin/CSRF checks, the dispatch and ``main``.
Route modules never import this one: it also runs as ``__main__``.
"""
from __future__ import annotations

import argparse
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import socket
import sys
import threading
from urllib.parse import urlsplit
import webbrowser

from comum import ROOT, dentro, ler_json, sha256
from cadastrar_documentos import inventario, preparar_pdfs
from ambiente import diagnostico
import fontes_web
import revisao_humana
import apuracao
import rotas_achados
import rotas_caderno
import rotas_conversa
import rotas_downloads
import rotas_evidencia
import rotas_gestao
import rotas_redacao
import rotas_tabelas
import rascunhos
import erros
from codex_apuracao import Conversas
import acesso
import lixeira
from indice_sqlite import ID_CASO, caminho_rodada, cobertura, ler_passagem, pesquisar
# Names also imported from here by the launcher, the tests and older callers.
from rotas_caderno import CADERNO_OPERACOES, DILIGENCIAS_OPERACOES
from rotas_contas import (RotasContas, CONTAS_OPERACOES, OPERACOES_CONVIDADO, OPERACOES_CONVERSA,  # noqa: F401
                          OPERACOES_PUBLICAS, AMBIENTES, SEM_SESSAO, OPERACOES_COM_COTA, ATIVOS_CONVERSA,
                          COOKIE_PILOTO)
from rotas_conversa import RotasConversa, RESPONDIDO, CAMPOS_INTERNOS_CONVERSA, _sem_internos  # noqa: F401
from rotas_documentos import MAX_UPLOAD, catalogo, receber_documentos  # noqa: F401
from rotas_downloads import RotasDownloads
from rotas_estaticas import ASSETS, RotasEstaticas
from rotas_gestao import IA_OPERACOES, RotasGestao

# local: single operator without sign-in; local-contas: accounts over plain HTTP on 127.0.0.1
# (installed Windows desk); piloto: accounts behind an HTTPS reverse proxy.
MODOS = ('local', 'local-contas', 'piloto')
MAXIMO_SESSOES_ORIGINAIS = 5000
# Case data answered by ``executar`` (frozen analyses, intake, search index).
CONSULTA_OPERACOES = ('analises', 'buscar', 'ler', 'cobertura', 'original', 'cadastrar', 'inventario', 'preparar-pdfs')
# Every POST operation behind a session; anything else is 404 before the body is parsed.
OPERACOES_API = (*rotas_conversa.OPERACOES, *apuracao.OPERACOES, *apuracao.OPERACOES_NOTAS, *CADERNO_OPERACOES,
                 *DILIGENCIAS_OPERACOES, *rotas_evidencia.OPERACOES, *rotas_tabelas.OPERACOES, *rotas_redacao.OPERACOES,
                 *rascunhos.OPERACOES, *fontes_web.OPERACOES, *rotas_gestao.OPERACOES, *CONTAS_OPERACOES, 'sessao-sair',
                 *rotas_achados.OPERACOES, *CONSULTA_OPERACOES)


def executar(root, operation, data, conta=None, originais_abertos=None, casos=None):
    """`conta` is the authenticated pilot account ({'id', 'nome'}); None in local mode.

    `casos` limits the evidence boards to the account's investigations (None: all, as for admins).
    """
    if operation == 'analises':
        case = data.get('caso')
        if not isinstance(case, str) or not re.fullmatch(ID_CASO, case):
            raise ValueError('Selecione uma apuração válida.')
        selected = next((c for c in catalogo(root)['casos'] if c['id'] == case), None)
        if selected is None:
            raise ValueError('Apuração indisponível.')
        result = []
        for item in selected['rodadas']:
            run = caminho_rodada(root, case, item['id'])
            try:
                record = ler_json(dentro(run, 'registro.json'))
                if record['caso_id'] != case or record['rodada'] != item['id']:
                    raise ValueError('Identidade da análise divergente.')
                question = dentro(run, '00_pergunta_original.md')
                frozen = ler_json(dentro(run, 'snapshot.json'))
                expected = next(x['sha256'] for x in frozen if x['arquivo'] == '00_pergunta_original.md')
                if sha256(question) != expected:
                    raise ValueError('Pergunta preservada divergente.')
                result.append({**item, 'pergunta': question.read_text(encoding='utf-8'),
                    'data': record.get('criada_em_utc'), 'documentos': record.get('corpus_id')})
            except (ValueError, OSError, KeyError, StopIteration, TypeError) as exc:
                result.append({**item, 'aviso': str(exc)})
        return {'caso': case, 'analises': result}
    if operation.startswith(rotas_caderno.PREFIXOS):
        # Investigation notebook, notes, follow-ups and the human notebook (rotas_caderno).
        return rotas_caderno.executar(root, operation, data, conta)
    if operation in rotas_evidencia.OPERACOES:
        # Evidence boards: field whitelist and case checks live in rotas_evidencia; no model or network.
        return rotas_evidencia.executar(root, operation, data, conta, casos)
    if operation in rotas_tabelas.OPERACOES:
        # Investigation tables: cells point to evidence; same case checks as the boards; no model or network.
        return rotas_tabelas.executar(root, operation, data, conta, casos)
    if operation in rotas_redacao.OPERACOES:
        # Claim-by-claim review of the story text: human review only with the server's account; no model or network.
        return rotas_redacao.executar(root, operation, data, conta, casos)
    if operation in rascunhos.OPERACOES:
        # Unconfirmed drafts per account, case and screen; guests (casos is a list) keep only the question.
        return rascunhos.executar(root, operation, data, conta, casos, convidado=casos is not None)
    if operation == 'cadastrar':
        return receber_documentos(root, data)
    if operation == 'inventario':
        return inventario(root, data.get('caso'))
    if operation in fontes_web.OPERACOES:
        # Network access only for cases created in the "documentos + web" mode, on their single domain.
        return fontes_web.rota(root, operation, data)
    if operation == 'preparar-pdfs':
        if not diagnostico()['extracao_pdf']['disponivel']:
            raise ValueError('O extrator de PDF não está disponível nesta instância. Encerre a Mesa e abra pelo iniciador atualizado.')
        return preparar_pdfs(root, data.get('caso'))
    case, run = data.get('caso'), data.get('rodada')
    lixeira.conferir_disponivel(root, case, rodada=run)
    if operation.startswith('achados-'):
        return rotas_achados.executar(root, operation, data, conta, case, run, originais_abertos)
    generation = data.get('geracao', 'v1')
    if not all(isinstance(value, str) for value in (case, run, generation)):
        raise ValueError('Selecione caso, rodada e geração.')
    if operation == 'cobertura':
        return cobertura(root, case, run, generation)
    if operation in ('ler', 'original'):
        reference = data.get('referencia')
        if not isinstance(reference, str) or not re.fullmatch(r'[a-f0-9]{64}', reference):
            raise ValueError('Referência de passagem inválida.')
        return ler_passagem(root, case, run, reference, geracao=generation)
    if operation == 'buscar':
        documents = data.get('documentos')
        if documents is not None and (not isinstance(documents, list)
                                     or not all(isinstance(x, str) for x in documents)):
            raise ValueError('Filtro de documentos inválido.')
        for key in ('limite', 'deslocamento', 'pagina'):
            value = data.get(key)
            if value is not None and type(value) is not int:
                raise ValueError('Página, limite e deslocamento devem ser números inteiros.')
        return pesquisar(root, case, run, data.get('consulta'), modo=data.get('modo', 'comum'),
                         documentos=documents, pagina=data.get('pagina'),
                         limite=data.get('limite', 10), deslocamento=data.get('deslocamento', 0),
                         geracao=generation)
    raise ValueError('Operação desconhecida.')


class Servidor(ThreadingHTTPServer):
    daemon_threads = True
    # A page load opens many parallel requests; the default backlog (5) refuses some on Windows.
    request_queue_size = 64
    allow_reuse_address = False

    def server_bind(self):
        # SO_REUSEADDR permits multiple independent Windows servers on one port.
        # Each browser request could then hit a different backend version.
        if os.name == 'nt':
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def __init__(self, address, root=ROOT, modo='local', origem=None):
        if modo not in MODOS:
            raise ValueError('Modo inválido: use local, local-contas ou piloto.')
        if modo == 'piloto':
            partes = urlsplit(origem or '')
            if partes.scheme != 'https' or not partes.netloc or partes.path not in ('', '/') or partes.query:
                raise ValueError('No modo piloto informe --origem com o endereço público HTTPS, ex.: https://vlado.example.org')
        self.modo = modo
        self.origem_publica = (origem or '').rstrip('/')
        self.root = Path(root).resolve()
        self.token = secrets.token_urlsafe(32)
        self.ambiente = diagnostico()
        self.cadastro_lock = threading.Lock()
        self.conversas = Conversas(self.root)
        # Originals opened per page session and frozen revision (memory only; a restart asks to reopen).
        self._originais = OrderedDict()
        self._originais_lock = threading.Lock()
        super().__init__(address, Handler)

    def registrar_original(self, chave, evidencia_id):
        with self._originais_lock:
            self._originais.setdefault(chave, set()).add(evidencia_id)
            self._originais.move_to_end(chave)
            while len(self._originais) > MAXIMO_SESSOES_ORIGINAIS:
                self._originais.popitem(last=False)

    def originais_abertos(self, chave):
        with self._originais_lock:
            return frozenset(self._originais.get(chave, ()))

    def server_close(self):
        self.conversas.close()
        super().server_close()

    @property
    def origin(self):
        return self.origem_publica if self.modo == 'piloto' else f'http://127.0.0.1:{self.server_port}'

    @property
    def host_permitido(self):
        return urlsplit(self.origem_publica).netloc if self.modo == 'piloto' else f'127.0.0.1:{self.server_port}'

    @property
    def com_contas(self):
        return self.modo != 'local'

    def atributos_cookie(self):
        """HttpOnly + SameSite=Strict always; Secure only over HTTPS (a browser drops Secure cookies on HTTP)."""
        return 'HttpOnly; ' + ('Secure; ' if self.modo == 'piloto' else '') + 'SameSite=Strict; Path=/'


class Handler(RotasContas, RotasConversa, RotasGestao, RotasDownloads, RotasEstaticas, BaseHTTPRequestHandler):
    timeout = 60  # seconds per socket operation; long polls answer within 20 s
    def _send(self, status, content, content_type='application/json; charset=utf-8', extra=None, cache='no-store'):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', cache)
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; worker-src 'self'; manifest-src 'self'; frame-src 'self' blob:; img-src 'self' blob:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.send_header('Referrer-Policy', 'no-referrer')
        if self.server.modo == 'piloto':
            self.send_header('Strict-Transport-Security', 'max-age=31536000')
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        try:
            self.end_headers()
            self.wfile.write(content)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            # Reloading/closing a tab may abandon an in-flight poll. Do not try
            # to send a second error response over the already closed socket.
            self.close_connection = True

    def _json(self, status, value, exc=None):
        if status >= 400 and isinstance(value, dict) and 'erro' in value and 'codigo' not in value:
            codigo, parametros = erros.codigo_de(str(value['erro']), exc)
            value = {**value, 'codigo': codigo, **({'parametros': parametros} if parametros else {})}
        self._send(status, json.dumps(value, ensure_ascii=False).encode('utf-8'))

    def _chave_originais(self, principal, data):
        """Per page session (never the raw token) and per frozen revision."""
        sessao = hashlib.sha256(principal['csrf'].encode('ascii')).hexdigest()[:24]
        return (sessao, *(v if isinstance(v, str) else None for v in (data.get('caso'), data.get('rodada'), data.get('revisao'))))

    def _allowed(self):
        if urlsplit(self.path).path == '/saude':
            return True  # container healthcheck reaches the server by its internal address
        if self.headers.get('Host') != self.server.host_permitido:
            self._json(403, {'erro': 'Endereço não autorizado.'})
            return False
        return True

    def _descartar_corpo_pequeno(self, limite=32768):
        """Discard (never parse) a small anonymous body before answering and closing.

        On Windows, closing a socket with unread bytes sends a TCP reset that can destroy the
        response before the client reads it. Larger or invalid lengths are still never read.
        """
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            return
        if 0 < length <= limite:
            try:
                self.rfile.read(length)
            except OSError:
                pass

    def do_GET(self):
        self.__dict__.pop('_principal_requisicao', None)  # one account lookup per request, even with keep-alive
        if not self._allowed():
            return
        path = urlsplit(self.path).path
        if path == '/saude':
            self._json(200, {'ok': True})
            return
        if path == '/api/sessao':
            self._sessao_atual()
            return
        if self.server.modo == 'local-contas':
            if path == '/api/primeiro-acesso':
                self._json(200, {'disponivel': self._primeiro_acesso()})
                return
            primeiro = path in ('/', '/entrar', '/primeiro-acesso') and self._primeiro_acesso()
            if path == '/primeiro-acesso' and primeiro:
                self._send(200, (ASSETS / 'entrar.html').read_bytes(), 'text/html; charset=utf-8')
                return
            if path == '/primeiro-acesso' or (primeiro and path in ('/', '/entrar')):
                self._send(303, b'', 'text/plain; charset=utf-8',
                           {'Location': '/primeiro-acesso' if primeiro else '/entrar'})
                return
        if self.server.com_contas:
            if path.startswith('/convite/'):
                self._convite_antigo()
                return
            if path == '/entrar' or re.fullmatch(r'/ativar(/[A-Za-z0-9_-]{1,100})?', path):
                # Static page without case data; the token stays in the path, read by entrar.js.
                self._send(200, (ASSETS / 'entrar.html').read_bytes(), 'text/html; charset=utf-8')
                return
            if path in ('/', '/api/catalogo', '/api/integracao') and self._principal() is None:
                self._sem_principal(api=path != '/')
                return
        if path == '/api/integracao':
            self._json(200, {'codex': True, 'protocolo_interface': 1, 'gerenciamento': True,
                             'apresentacao_editorial': True, 'preparacao_pdfs': True,
                             'revisao_humana': True, 'continuar_observacoes': True, 'continuar_documentos': True, 'caderno_humano': True, 'diligencias': True, 'quadros_evidencia': True,
                             'tabelas_apuracao': True, 'continuidade_resumo': True, 'conferencia_redacao': True, 'entrevistas': True,
                             'fontes_web': True,
                             'extracao_pdf': self.server.ambiente['extracao_pdf']})
            return
        if path == '/api/catalogo':
            try:
                dados, principal = catalogo(self.server.root), self._principal()
                if principal['casos'] is not None:
                    dados = {'casos': [c for c in dados['casos'] if c['id'] in principal['casos']]}
                self._json(200, dados)
            except (ValueError, OSError, KeyError) as exc:
                self._json(400, {'erro': str(exc)})
            return
        self._estatico(path)

    def do_POST(self):
        self.__dict__.pop('_principal_requisicao', None)
        if self.server.com_contas:
            # Never read (up to 72 MB of) a body for anonymous or foreign-host requests.
            if not self._allowed():
                self.close_connection = True
                return
            if urlsplit(self.path).path.removeprefix('/api/') in OPERACOES_PUBLICAS:
                self._publico(urlsplit(self.path).path.removeprefix('/api/'))
                return
            if self._principal() is None:
                self.close_connection = True
                self._descartar_corpo_pequeno()
                self._sem_principal(api=True)
                return
        # Consume bounded bodies even for rejected requests, avoiding TCP resets on Windows.
        try:
            try:
                length = int(self.headers.get('Content-Length', '0'))
            except ValueError as exc:
                raise ValueError('Requisição vazia ou muito grande.') from exc
            operation = urlsplit(self.path).path.removeprefix('/api/')
            principal = self._principal()
            # Guests only call small JSON operations: never read a large body before the role check.
            maximum = (32768 if principal is not None and principal['papel'] != 'admin'
                       else 72 * 1024 * 1024 if operation in ('cadastrar', 'codex-documentos-cadastrar')
                       else 2 * 1024 * 1024 if operation in (*apuracao.OPERACOES, *apuracao.OPERACOES_NOTAS,
                                                             *rotas_tabelas.SALVAR, *rascunhos.SALVAR)
                       else rotas_redacao.LIMITE_CORPO_TEXTO if operation in rotas_redacao.TEXTO
                       else 128 * 1024 if operation in ('caderno-salvar', 'diligencias-criar', 'diligencias-atualizar', 'diligencias-responder',
                                                     *rotas_evidencia.SALVAR, *rotas_redacao.SALVAR) else 32768)
            if not 0 < length <= maximum:
                raise ValueError('Requisição vazia ou muito grande.')
            body = self.rfile.read(length)
        except ValueError as exc:
            self._json(400, {'erro': str(exc)})
            return
        if not self._allowed():
            return
        principal = self._principal()
        if principal is None:
            self._sem_principal(api=True)
            return
        # Pilot mode requires an explicit Origin; local mode keeps accepting same-origin requests without it.
        origem = self.headers.get('Origin', None if self.server.com_contas else self.server.origin)
        if (origem != self.server.origin
                or not secrets.compare_digest(self.headers.get('X-Session-Token', '').encode('utf-8'), principal['csrf'].encode('ascii'))
                or self.headers.get_content_type() != 'application/json'):
            self._json(403, {'erro': 'Origem ou sessão não autorizada. Recarregue a página.'})
            return
        operation = urlsplit(self.path).path.removeprefix('/api/')
        # Operation names keep the historical "codex-" prefix; inference now goes through the API adapter.
        if operation not in OPERACOES_API:
            self._json(404, {'erro': 'Operação não encontrada.'})
            return
        try:
            data = json.loads(body)
            if not isinstance(data, dict):
                raise ValueError('Requisição deve ser um objeto JSON.')
            negado = self._negado(operation, data, principal)
            if negado:
                self._proibido(*negado)
                return
            convidado = principal['papel'] != 'admin'
            dono = principal['conta'] if convidado else None
            # A guest reaches its own conversations only while their case is still released (re-read each request).
            casos_liberados = (principal['casos'] or []) if convidado else None
            if operation == 'sessao-sair':
                self._sair()
                return
            if operation in CONTAS_OPERACOES:
                self._json(200, self._contas(operation, data, principal))
                return
            consulta_contada = False
            if operation in OPERACOES_COM_COTA and dono is not None:
                acesso.registrar_consulta(self.server.root, dono)
                consulta_contada = True
            if operation in rotas_downloads.OPERACOES:
                self._baixar(operation, data, principal)
                return
            elif operation == fontes_web.CAPTURAR:
                # The fetch runs outside the cadastro lock; checking and publishing take it.
                result = fontes_web.rota(self.server.root, operation, data, trava=self.server.cadastro_lock)
            elif operation in rotas_gestao.OPERACOES:
                result = self._gestao(operation, data, principal)
            elif operation in rotas_conversa.OPERACOES:
                result = self._conversa(operation, data, dono, casos_liberados, consulta_contada)
                if result is RESPONDIDO:
                    return
            else:
                conta = ({'id': principal['conta'], 'nome': principal['nome']}
                         if self.server.com_contas else None)
                abertos = (self.server.originais_abertos(self._chave_originais(principal, data))
                           if operation == 'achados-revisao-salvar' else None)
                with self.server.cadastro_lock:
                    result = executar(self.server.root, operation, data, conta, abertos, casos=principal['casos'])
            if operation in rotas_downloads.ORIGINAIS_PASSAGEM:
                self._enviar_original(operation, data, result, principal)
            else:
                self._json(400 if result.get('estado') == 'erro_consulta' else 200, result)
        except revisao_humana.OriginalNaoConferido as exc:
            self._json(400, {'estado': 'erro', 'codigo': 'conferencia_sem_original', 'erro': str(exc), 'faltam': exc.faltam})
        except apuracao.ConflitoNota as exc:
            self._json(409, {'estado': 'erro', 'codigo': 'conflito', 'erro': str(exc), 'atual': exc.atual})
        except rascunhos.ConflitoRascunho as exc:
            self._json(409, {'estado': 'erro', 'codigo': 'rascunho_conflito', 'erro': str(exc), 'atual': exc.atual})
        except (ValueError, OSError, KeyError, TypeError, sqlite3.Error) as exc:
            convidado = principal['papel'] != 'admin'
            # Guests get user-facing ValueError messages only; internal errors stay generic.
            mensagem = ('Falha ao processar a requisição no servidor.'
                        if convidado and not isinstance(exc, ValueError) else str(exc))
            self._json(400, {'estado': 'erro', 'erro': mensagem}, exc)

    def log_message(self, format, *args):
        # Do not print queries, source content or token to the terminal.
        return


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--porta', type=int, default=8765)
    parser.add_argument('--sem-abrir', action='store_true')
    parser.add_argument('--modo', choices=MODOS, default='local',
                        help='local-contas: login e senha em http://127.0.0.1 (Mesa instalada no Windows); '
                             'piloto: contas atrás de um proxy HTTPS (ver docs/GUIA_TECNICO_IMPLANTACAO.md)')
    parser.add_argument('--host', default='127.0.0.1', help='Endereço de escuta; no contêiner use 0.0.0.0')
    parser.add_argument('--origem', help='Endereço público HTTPS do piloto, ex.: https://vlado.example.org')
    parser.add_argument('--dados', help='Pasta de dados (casos, conversas, contas); padrão: a pasta do projeto')
    args = parser.parse_args()
    if args.modo != 'piloto' and args.host != '127.0.0.1':
        raise SystemExit('Nos modos locais o servidor escuta somente em 127.0.0.1.')
    with Servidor((args.host, args.porta), root=Path(args.dados) if args.dados else ROOT,
                  modo=args.modo, origem=args.origem) as server:
        print(f'Mesa de apuração ({args.modo}): {server.origin}', flush=True)
        print('Encerre com Ctrl+C.', flush=True)
        if args.modo != 'piloto' and not args.sem_abrir:
            webbrowser.open(server.origin)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    try:
        main()
    except OSError as exc:
        if os.name == 'nt' and os.environ.get('APURACAO_OCULTO') == '1':
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, f'Não foi possível iniciar a Mesa de apuração.\n{exc}\nSe a porta 8765 estiver ocupada, encerre o servidor anterior.', 'Mesa de apuração', 16)
        else:
            raise
