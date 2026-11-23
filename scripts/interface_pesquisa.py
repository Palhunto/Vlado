"""Optional loopback search UI. Uses existing snapshot/index validation and raw logs."""
# The docstring above is also the --help description. Routes live in the ``rotas_*`` modules
# (accounts and sessions, conversation, management, downloads, static files, notebook,
# findings, evidence boards, tables, story review); this file keeps the server, request
# reading, origin/CSRF checks, the dispatch and ``main``. Route modules never import this
# one: it also runs as ``__main__``.
from __future__ import annotations

import argparse
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import io
import json
import os
from pathlib import Path
import re
import secrets
import selectors
import signal
import sqlite3
import queue
import socket
import sys
import threading
import time
from urllib.parse import parse_qs, urlsplit
import webbrowser

from comum import ROOT, dentro, ler_json, sha256
from cadastrar_documentos import inventario, preparar_pdfs
from ambiente import diagnostico
import fontes_web
import revisao_humana
import apuracao
import autorizacao
import correio
import rotas_achados
import rotas_caderno
import rotas_conversa
import rotas_downloads
import rotas_equipe
import rotas_evidencia
import rotas_gestao
import rotas_redacao
import rotas_tabelas
import rascunhos
import erros
import fila_extracao
from codex_apuracao import Conversas
import acesso
import proxies_confiaveis
import apagamento
import registro_acesso
import lixeira
import trava_cadastro
from indice_sqlite import ID_CASO, caminho_rodada, cobertura, ler_passagem, pesquisar
# Names also imported from here by the launcher, the tests and older callers.
from rotas_caderno import CADERNO_OPERACOES, DILIGENCIAS_OPERACOES
from rotas_contas import (RotasContas, OPERACOES_CONVIDADO, OPERACOES_CONVERSA,  # noqa: F401
                          OPERACOES_PUBLICAS, AMBIENTES, SEM_SESSAO, OPERACOES_COM_COTA, ATIVOS_CONVERSA,
                          COOKIE_PILOTO, CONTA_PROPRIA)
from rotas_conversa import RotasConversa, RESPONDIDO, CAMPOS_INTERNOS_CONVERSA, _sem_internos  # noqa: F401
import rotas_documentos
from rotas_documentos import MAX_UPLOAD, catalogo, receber_documentos  # noqa: F401
from rotas_downloads import RotasDownloads
import rotas_estaticas
from rotas_estaticas import ASSETS, RotasEstaticas  # noqa: F401
from rotas_gestao import IA_OPERACOES, RotasGestao

# local: single operator without sign-in; local-contas: accounts over plain HTTP on 127.0.0.1
# (installed Windows desk); piloto: accounts behind an HTTPS reverse proxy.
MODOS = ('local', 'local-contas', 'piloto')
MAXIMO_SESSOES_ORIGINAIS = 5000
# After SIGTERM (docker stop sends SIGKILL 10 s later), Ctrl+C or "Encerrar Mesa": seconds for
# executions to stop and for operations holding the cadastro lock to finish.
PRAZO_ENCERRAMENTO = 8.0
PRAZO_FECHAR_FILA = 5.0  # server_close without encerrar(): the extraction queue's coordinator stops
# Connections answered at the same time (CONF-03): one thread each; past it, 503 at once (no thread).
# Long polls of the events hold one for up to 20 s: room for some tens of open pages.
MAXIMO_CONEXOES = int(os.environ.get('VLADO_MAXIMO_CONEXOES') or 96)
RESPOSTA_503 = (b'HTTP/1.1 503 Service Unavailable' + bytes([13, 10]) + b'Retry-After: 2' + bytes([13, 10])
                + b'Content-Length: 0' + bytes([13, 10]) + b'Connection: close' + bytes([13, 10]) * 2)
# A refused connection gets its 503 at once; then it is read for at most PRAZO_RECUSA seconds and
# TETO_BYTES_RECUSA bytes before closing (closing with unread bytes is a reset on Windows, and the
# client would not see the 503). Up to MAXIMO_RECUSAS are read at once; past it, closed after the 503.
PRAZO_RECUSA = 2.0
TETO_BYTES_RECUSA = 1 << 20
MAXIMO_RECUSAS = 128
# Seconds, in all, for a request line and its headers, a kept-alive connection waiting for the next
# request included: a client sending a byte at a time, or nothing, holds its thread this long at most.
PRAZO_CABECALHOS = 10.0
# A request body must keep coming (CONF-03): PRAZO_CORPO seconds, plus one more for each
# TAXA_MINIMA_CORPO bytes received (a minimum rate); a body sent a byte at a time no longer holds
# its thread, and a large upload has the time its size needs at that rate. 8 KiB/s is about
# 64 kbit/s: a reporter on weak 3G or EDGE still sends (32 KiB/s cut below about 256 kbit/s). A
# client that keeps that rate holds its slot as long as its size needs (50 MB: under 2 hours), and
# pays the bandwidth; MAXIMO_POR_IP keeps it from holding many.
PRAZO_CORPO = 10.0
TAXA_MINIMA_CORPO = 8 * 1024
# A refused streamed upload: what already arrived is read for at most this long after the answer,
# then the connection closes (the slot is not held for the rest of the body).
PRAZO_DRENO = 0.5
# Requests in course from one client address at a time, in pilot mode (CONF-03): past it, 429 at
# once, without reading the body, so one client cannot take all MAXIMO_CONEXOES. The address is the
# one the trusted proxies of SEG-05 give (VLADO_PROXIES_CONFIAVEIS): the TCP peer whenever it is not a
# trusted proxy, with or without X-Forwarded-For (a header the client writes never chooses its
# bucket; the old VLADO_CONFIAR_PROXY trusts anyone, so it does not count here). Behind a proxy not on
# the list every request counts for the proxy: list it (deploy/MONITORAMENTO.md). Half the connections
# by default: a newsroom behind one NAT shares an address. Only VLADO_MAXIMO_POR_IP=0 turns it off.
MAXIMO_POR_IP = int(os.environ.get('VLADO_MAXIMO_POR_IP') or max(1, MAXIMO_CONEXOES // 2))
MENSAGEM_POR_IP = 'Muitas requisições ao mesmo tempo deste endereço. Aguarde alguns segundos e tente de novo.'
# Case data answered by ``executar`` (frozen analyses, intake, search index).
CONSULTA_OPERACOES = ('analises', 'buscar', 'ler', 'cobertura', 'original', 'cadastrar', 'inventario', 'preparar-pdfs')
# Answered by the extraction queue in do_POST, outside cadastro_lock (executar still serves direct calls).
CADASTRO_NA_FILA = ('cadastrar', 'preparar-pdfs')
ROTAS_GET_COM_PARAMETROS = ('/api/catalogo', '/api/fila', '/api/cota')  # each one calls the gate where it is served
# Every POST operation behind a session; anything else is 404 before the body is parsed.
OPERACOES_API = (*rotas_conversa.OPERACOES, *apuracao.OPERACOES, *apuracao.OPERACOES_NOTAS, *CADERNO_OPERACOES,
                 *DILIGENCIAS_OPERACOES, *rotas_evidencia.OPERACOES, *rotas_tabelas.OPERACOES, *rotas_redacao.OPERACOES,
                 *rascunhos.OPERACOES, *fontes_web.OPERACOES, *rotas_gestao.OPERACOES, 'sessao-sair',
                 *rotas_achados.OPERACOES, *CONSULTA_OPERACOES, *rotas_equipe.OPERACOES, *CONTA_PROPRIA)
registro_acesso.permitir_operacoes((*OPERACOES_API, *OPERACOES_PUBLICAS))  # SEG-02: o registro só aceita nomes que existem


def executar(root, operation, data, conta=None, originais_abertos=None, casos=None, restrito=False):
    """`conta` is the authenticated account ({'id', 'nome'}); None in local mode.

    `casos` is the account's reach (None only in the local mode, where the single operator reaches everything):
    the gate (`autorizacao.conferir`) already checked the case, and it is checked again here, so a failure of the
    gate still does not open a case. `restrito`: reader or guest, who keep only the draft of the question.
    """
    if casos is not None and data.get('caso') not in casos:
        raise ValueError('Apuração não liberada para esta conta.')
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
        return rascunhos.executar(root, operation, data, conta, casos, convidado=restrito)
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


class _EmCurso:
    """POST requests being answered, for the orderly shutdown to wait for."""

    def __init__(self):
        self.total = 0
        self.mudou = threading.Condition()

    def entrar(self):
        with self.mudou:
            self.total += 1

    def sair(self):
        with self.mudou:
            self.total -= 1
            self.mudou.notify_all()

    def aguardar(self, prazo):
        with self.mudou:
            return self.mudou.wait_for(lambda: self.total == 0, timeout=prazo)


class Servidor(ThreadingHTTPServer):
    daemon_threads = True
    # A page load opens many parallel requests; the default backlog (5) refuses some on Windows.
    request_queue_size = 64
    allow_reuse_address = False

    def process_request(self, request, client_address):
        """A thread per connection, up to MAXIMO_CONEXOES (CONF-03); past it, a 503 from one thread."""
        if not self._vagas.acquire(blocking=False):
            self._recusar(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._vagas.release()
            raise

    def _recusar(self, request):
        """The 503 right here, without waiting: what the client already sent is read, the answer fits
        the empty send buffer of a new connection, and the end of the answer goes with it. Then the
        refusing thread reads what still comes, for a bounded time, and closes in order."""
        try:
            request.setblocking(False)
            try:
                request.recv(65536)
            except (BlockingIOError, InterruptedError):
                pass
            if request.send(RESPOSTA_503) != len(RESPOSTA_503):
                raise OSError('resposta 503 incompleta')
            request.shutdown(socket.SHUT_WR)
        except OSError:
            self.shutdown_request(request)
            return
        if not self._recusas_vagas.acquire(blocking=False):
            self.shutdown_request(request)  # too many being read already: the 503 went, close now
            return
        with self._recusas_trava:
            if self._recusadora is None:
                self._recusadora = threading.Thread(target=self._laco_de_recusas, daemon=True, name='vlado_503')
                self._recusadora.start()
        self._recusas.put((request, time.monotonic() + PRAZO_RECUSA))

    def _laco_de_recusas(self):
        """Read the refused connections all at once, each until the client closes it, PRAZO_RECUSA has
        passed or TETO_BYTES_RECUSA was read, then close it: a slow client holds back no other (B1)."""
        seletor = selectors.DefaultSelector()
        abertas = {}  # socket -> [deadline, bytes read]

        def fechar(request):
            try:
                seletor.unregister(request)
            except (KeyError, ValueError, OSError):
                pass
            abertas.pop(request, None)
            self.shutdown_request(request)
            self._recusas_vagas.release()
        while True:
            try:  # waits here only with nothing to read
                request, prazo = self._recusas.get(block=not abertas)
            except queue.Empty:
                pass
            else:
                abertas[request] = [prazo, 0]
                try:
                    seletor.register(request, selectors.EVENT_READ)
                except (OSError, ValueError):
                    fechar(request)
            agora = time.monotonic()
            for request in [r for r, (prazo, _) in abertas.items() if prazo <= agora]:
                fechar(request)
            if not abertas:
                continue
            espera = min(0.05, max(0.0, min(prazo for prazo, _ in abertas.values()) - agora))
            for chave, _ in seletor.select(espera):
                request = chave.fileobj
                try:
                    lido = request.recv(65536)
                except (BlockingIOError, InterruptedError):
                    continue
                except OSError:
                    lido = b''
                abertas[request][1] += len(lido)
                if not lido or abertas[request][1] > TETO_BYTES_RECUSA:
                    fechar(request)

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._vagas.release()

    def server_bind(self):
        # SO_REUSEADDR permits multiple independent Windows servers on one port.
        # Each browser request could then hit a different backend version.
        if os.name == 'nt':
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def __init__(self, address, root=ROOT, modo='local', origem=None, extracao=None):
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
        self.requisicoes = _EmCurso()
        self._vagas = threading.BoundedSemaphore(max(1, MAXIMO_CONEXOES))
        self._recusas = queue.Queue()
        self._recusas_vagas = threading.BoundedSemaphore(max(1, MAXIMO_RECUSAS))
        self._por_ip, self._por_ip_trava = {}, threading.Lock()  # requests in course per client address
        self._recusas_trava = threading.Lock()
        self._recusadora = None
        # Extraction and OCR of uploads (CONF-02): 'processos' runs them in separate processes
        # (main); 'local' in threads of this process (tests, the frozen Windows desk).
        self.fila = fila_extracao.Fila(self.root, modo=extracao or 'local')
        self.conversas.renderizar_pagina = self.fila.renderizar_pagina  # page images too (SEG-01)
        super().__init__(address, Handler)

    def serve_forever(self, poll_interval=0.5):
        # Batches left by a stop or a crash are finished once serving starts: after servir()'s
        # start-up cleanup of the cadastro lock, which the publication would otherwise hold.
        if fila_extracao.pendentes(self.root):
            self.fila.iniciar()
        super().serve_forever(poll_interval)

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
        # After encerrar() the threads already had their time: do not wait again. Otherwise the
        # queue's coordinator gets a few seconds, so nothing writes in casos/.fila after the close.
        encerrado = getattr(self, '_encerrado', False)
        self.fila.encerrar(0 if encerrado else PRAZO_FECHAR_FILA)
        self.conversas.close(prazo=0 if encerrado else None)
        super().server_close()

    def pedir_encerramento(self):
        """Ask ``serve_forever`` to return; safe inside a signal handler (main thread)."""
        if not getattr(self, '_encerramento_pedido', False):
            self._encerramento_pedido = True
            threading.Thread(target=self.shutdown, daemon=True).start()

    def encerrar(self, prazo=PRAZO_ENCERRAMENTO):
        """Orderly stop once ``serve_forever`` returned. True when no operation was cut short.

        No new connections; waiting operations give up the cadastro lock; executions are told
        to stop (``Conversas.close``); operations already holding the cadastro lock get the rest
        of ``prazo`` to finish. Whatever is still running after that is cut when the process
        exits: the system releases the lock and the next start cleans up (``trava_cadastro``).
        """
        limite = time.monotonic() + prazo
        self._encerrado = True
        trava_cadastro.encerrar(self.root)
        try:
            self.socket.close()
        except OSError:
            pass
        # Files being read go back to the queue (no attempt counted); a publication in course ends.
        self.fila.encerrar(prazo=max(0.0, limite - time.monotonic()))
        self.conversas.close(prazo=max(0.0, limite - time.monotonic()))
        livre = trava_cadastro.aguardar_livre(self.root, max(0.0, limite - time.monotonic()))
        # Then the answers of the requests that were running (a finished cadastro reaches the browser).
        return self.requisicoes.aguardar(max(0.0, limite - time.monotonic())) and livre

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


# SEG-02: operations that hand a file to the caller. Those that answer with an attachment are recorded in ``_send``;
# the three below answer JSON that the browser turns into a file.
EXPORTACOES_EM_JSON = ('achados-exportar', 'caderno-exportar', 'entrevistas-exportar')
DOWNLOADS = frozenset({*rotas_downloads.OPERACOES, *rotas_downloads.ORIGINAIS_PASSAGEM, 'codex-original',
                       *EXPORTACOES_EM_JSON})


class _LeituraComPrazo(socket.SocketIO):
    """The reading side of a connection. While ``prazo`` is set (request line and headers), each read
    waits only for what is left of it, so the deadline holds in all, however slowly the bytes come;
    when it passes with nothing received (a kept-alive connection gone idle), it reads as the end."""
    prazo = None
    espera = None  # the per-operation timeout of the handler, the most a read waits
    recebido = 0
    corpo_desde = None  # while the body is read: when it began (after the headers)
    corpo_lido = 0

    def readinto(self, b):
        if self.prazo is None:
            return super().readinto(b) if self.corpo_desde is None else self._ler_corpo(b)
        resta = self.prazo - time.monotonic()
        try:
            if resta <= 0:
                raise TimeoutError('prazo da linha do pedido e dos cabeçalhos esgotado')
            self._sock.settimeout(min(resta, self.espera) if self.espera else resta)
            lido = super().readinto(b)
        except TimeoutError:
            if self.recebido:
                raise
            return 0
        self.recebido += lido or 0
        return lido

    def _ler_corpo(self, b):
        """A body read: within PRAZO_CORPO plus the time its bytes so far need at TAXA_MINIMA_CORPO."""
        resta = self.corpo_desde + PRAZO_CORPO + self.corpo_lido / TAXA_MINIMA_CORPO - time.monotonic()
        if resta <= 0:
            raise TimeoutError('corpo do pedido chegando abaixo da taxa mínima')
        self._sock.settimeout(min(resta, self.espera) if self.espera else resta)
        try:
            lido = super().readinto(b)
        finally:
            self._sock.settimeout(self.espera)  # the answer keeps the per-operation timeout
        self.corpo_lido += lido or 0
        return lido


class Handler(RotasContas, RotasConversa, RotasGestao, RotasDownloads, RotasEstaticas, BaseHTTPRequestHandler):
    timeout = 60  # seconds per socket operation; long polls answer within 20 s

    def setup(self):
        super().setup()
        original, self._leitura = self.rfile, _LeituraComPrazo(self.connection, 'rb')
        self._leitura.espera = self.timeout
        self.rfile = io.BufferedReader(self._leitura)
        original.close()

    def handle_one_request(self):
        """Request line and headers within PRAZO_CABECALHOS in all (CONF-03); the body and the answer
        keep the per-operation timeout."""
        self._leitura.prazo, self._leitura.recebido = time.monotonic() + PRAZO_CABECALHOS, 0
        self._leitura.corpo_desde = None
        try:
            super().handle_one_request()
        finally:
            self._leitura.corpo_desde = None
            self._sem_prazo()
            self._sair_do_teto_por_ip()

    def parse_request(self):
        try:
            aceito = super().parse_request()  # reads the headers
        finally:
            self._sem_prazo()
            self._leitura.corpo_desde, self._leitura.corpo_lido = time.monotonic(), 0  # the body's minimum rate
        return aceito and self._dentro_do_teto_por_ip()

    def _dentro_do_teto_por_ip(self):
        """Count this request for its client address (pilot mode), or answer 429 past MAXIMO_POR_IP."""
        self._ip_contado = None
        if self.server.modo != 'piloto' or MAXIMO_POR_IP <= 0:
            return True
        par, redes = self.client_address[0], proxies_confiaveis.do_ambiente()
        ip = (proxies_confiaveis.ip_do_cliente(par, ','.join(self.headers.get_all('X-Forwarded-For') or []), redes)
              if redes else par)
        with self.server._por_ip_trava:
            em_curso = self.server._por_ip.get(ip, 0)
            if em_curso < MAXIMO_POR_IP:
                self.server._por_ip[ip], self._ip_contado = em_curso + 1, ip
                return True
        self._auditar_pedido_recusado(ip)
        self.close_connection = True
        self._descartar_corpo_pequeno()
        self._send(429, json.dumps({'erro': MENSAGEM_POR_IP}, ensure_ascii=False).encode('utf-8'),
                   extra={'Retry-After': '2'})
        return False

    def _auditar_pedido_recusado(self, ip):
        """SEG-02: the 429 goes to the audit log as ONE line per address and minute with the count (anonymous class: an
        address that floods never costs the log its sign-in or administration events). Never raises."""
        registro_acesso.iniciar_requisicao(raiz=self.server.root)  # the audit folder follows the data root
        try:
            registro_acesso.registrar_limite_ip('pedido_recusado', ip, acesso._rede(ip))
        finally:
            registro_acesso.encerrar_requisicao()

    def _sair_do_teto_por_ip(self):
        ip = self.__dict__.pop('_ip_contado', None)
        if ip is not None:
            with self.server._por_ip_trava:
                restam = self.server._por_ip.get(ip, 1) - 1
                if restam > 0:
                    self.server._por_ip[ip] = restam
                else:
                    self.server._por_ip.pop(ip, None)

    def finish(self):
        """An upload refused before its files were read: the answer is sent, the end of it goes (SHUT_WR),
        and what already arrived is dropped for at most PRAZO_DRENO, then the connection closes: closing
        with unread bytes is a reset on Windows that could destroy the answer, but the slot is not held
        for the rest of the body."""
        fluxo = self.__dict__.get('_fluxo')
        if fluxo is not None and fluxo.restante > 0:
            fim = time.monotonic() + PRAZO_DRENO
            self._leitura.corpo_desde = None
            try:
                self.wfile.flush()
                self.connection.shutdown(socket.SHUT_WR)
                lidos = 0
                while lidos < rotas_documentos.LIMITE_DRENO and (resta := fim - time.monotonic()) > 0:
                    self.connection.settimeout(resta)
                    lido = self.connection.recv(65536)
                    if not lido:
                        break
                    lidos += len(lido)
            except OSError:
                pass
        super().finish()

    def _sem_prazo(self):
        if self._leitura.prazo is not None:
            self._leitura.prazo = None
            try:
                self.connection.settimeout(self.timeout)
            except OSError:
                pass

    def send_response(self, code, message=None):
        # SEG-06: like the base class, but without the `Server` header (it carried "BaseHTTP/0.6 Python/3.x"). Error
        # pages from send_error go through here too, so no answer names the software or its version.
        self.log_request(code)
        self.send_response_only(code, message)
        self.send_header('Date', self.date_time_string())

    def _send(self, status, content, content_type='application/json; charset=utf-8', extra=None, cache='no-store'):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', cache)
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; worker-src 'self'; manifest-src 'self'; frame-src 'self' blob:; img-src 'self' blob:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.send_header('Referrer-Policy', 'no-referrer')
        if self.server.modo == 'piloto':
            # One year, subdomains included; no `preload` (hard to undo: see deploy/MONITORAMENTO.md).
            self.send_header('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
        for key, value in (extra or {}).items():
            for cada in (value if isinstance(value, (list, tuple)) else (value,)):  # more than one Set-Cookie
                self.send_header(key, cada)
        baixando = status == 200 and str((extra or {}).get('Content-Disposition', '')).startswith('attachment')
        try:
            self.end_headers()
            self.wfile.write(content)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            # Reloading/closing a tab may abandon an in-flight poll. Do not try
            # to send a second error response over the already closed socket.
            self.close_connection = True
            if baixando:
                self._auditar_download('interrompido', len(content))
            return
        if baixando:
            self._auditar_download('ok', len(content))

    def _auditar_download(self, resultado, tamanho=None):
        """SEG-02: who downloaded what kind of file, when and from where; never the name, the case or the content."""
        if getattr(self, '_download_registrado', False):
            return
        self._download_registrado = True
        operacao = registro_acesso.valor_do_contexto('operacao') or ''
        registro_acesso.registrar('download', resultado, registro_acesso.valor_do_contexto('conta'),
                                  tipo='original' if operacao.endswith('original') else 'exportacao', bytes=tamanho)

    def _json(self, status, value, exc=None):
        if status >= 400 and isinstance(value, dict) and 'erro' in value and 'codigo' not in value:
            codigo, parametros = erros.codigo_de(str(value['erro']), exc)
            value = {**value, 'codigo': codigo, **({'parametros': parametros} if parametros else {})}
        self._send(status, json.dumps(value, ensure_ascii=False).encode('utf-8'))

    def _chave_originais(self, principal, data):
        """Per page session (never the raw token) and per frozen revision."""
        sessao = hashlib.sha256(principal['csrf'].encode('ascii')).hexdigest()[:24]
        return (sessao, *(v if isinstance(v, str) else None for v in (data.get('caso'), data.get('rodada'), data.get('revisao'))))

    def _allowed(self, descartar=False):
        if urlsplit(self.path).path == '/saude':
            return True  # container healthcheck reaches the server by its internal address
        if self.headers.get('Host') != self.server.host_permitido:
            if descartar:  # POST refused before its body was read: drop a small one, answer and close
                self.close_connection = True
                self._descartar_corpo_pequeno()
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
        registro_acesso.iniciar_requisicao(self._ip, raiz=self.server.root)
        try:
            self._atender_get()
        finally:
            registro_acesso.encerrar_requisicao()

    def _atender_get(self):
        self.__dict__.pop('_principal_requisicao', None)  # one account lookup per request, even with keep-alive
        if not self._allowed():
            return
        path = urlsplit(self.path).path
        if path == '/saude':
            self._json(200, {'ok': True})
            return
        if 'GET:' + path in autorizacao.MATRIZ and path not in ROTAS_GET_COM_PARAMETROS and self._principal() is not None:
            # The page, the session and the server's capabilities pass through the gate too: a suspended
            # newsroom gets none of them (the three listings below ask the gate themselves, with their parameters).
            try:
                autorizacao.conferir(self.server.root, self.server.modo, self._principal(), 'GET:' + path, {})
            except autorizacao.Recusa as recusa:
                self._recusado(recusa, self._principal(), pagina=path == '/')
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
                self._send(200, rotas_estaticas.conteudo('entrar.html'), 'text/html; charset=utf-8')
                return
            if path == '/primeiro-acesso' or (primeiro and path in ('/', '/entrar')):
                self._send(303, b'', 'text/plain; charset=utf-8',
                           {'Location': '/primeiro-acesso' if primeiro else '/entrar'})
                return
        if self.server.com_contas:
            if path.startswith('/convite/'):
                self._convite_antigo()
                return
            if path == '/api/entrada':
                # Public, before any session: what the sign-in page may offer. Nothing of any account.
                self._json(200, {'esqueci_senha': self._esqueci_ligado()})
                return
            if path == '/entrar' or re.fullmatch(r'/ativar(/[A-Za-z0-9_-]{1,100})?|/(aceitar|redefinir|confirmar-email)/[A-Za-z0-9_-]{1,100}', path):
                # Static page without case data; the token stays in the path, read by entrar.js. Like every answer,
                # it goes with `Cache-Control: no-store` and `Referrer-Policy: no-referrer` (`_send`).
                self._send(200, rotas_estaticas.conteudo('entrar.html'), 'text/html; charset=utf-8')
                return
            if path in ('/', '/api/catalogo', '/api/integracao', '/api/fila', '/api/cota') and self._principal() is None:
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
        if path == '/api/fila':
            self._estado_da_fila()
            return
        if path == '/api/cota':
            self._cota()
            return
        if path == '/api/catalogo':
            principal = self._principal()
            try:
                autorizacao.conferir(self.server.root, self.server.modo, principal, 'GET:/api/catalogo', {})
                self._json(200, autorizacao.filtrar(self.server.root, self.server.modo, principal, 'GET:/api/catalogo',
                                                    catalogo(self.server.root)))
            except autorizacao.Recusa as recusa:
                self._recusado(recusa, principal)
            except (ValueError, OSError, KeyError) as exc:
                self._json(400, {'erro': str(exc)})
            return
        self._estatico(path)

    def do_POST(self):
        # Counted for the orderly shutdown, which waits for these answers; the events long poll
        # (up to 20 s, nothing to lose) is not.
        contar = urlsplit(self.path).path != '/api/codex-eventos'
        if contar:
            self.server.requisicoes.entrar()
        registro_acesso.iniciar_requisicao(self._ip, raiz=self.server.root)
        try:
            self._atender_post()
        finally:
            registro_acesso.encerrar_requisicao()
            if contar:
                self.server.requisicoes.sair()

    def _atender_post(self):
        self.__dict__.pop('_principal_requisicao', None)
        self.__dict__.pop('_download_registrado', None)
        self.__dict__.pop('_fluxo', None)
        if self.server.com_contas:
            # Never read (up to 72 MB of) a body for anonymous or foreign-host requests.
            if not self._allowed(descartar=True):
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
            # A batch streamed to disk (CONF-03): the manifest line now, the files' bytes by the route.
            em_fluxo = operation in rotas_documentos.EM_FLUXO and self.headers.get_content_type() == rotas_documentos.TIPO_LOTE
            # Guests only call small JSON operations: never read a large body before the role check.
            maximum = (32768 if principal is not None and (autorizacao.restrito(principal) or not autorizacao.corpo_grande(
                           self.server.modo, principal, operation))
                       else MAX_UPLOAD + rotas_documentos.LIMITE_MANIFESTO if em_fluxo
                       else 72 * 1024 * 1024 if operation in ('cadastrar', 'codex-documentos-cadastrar')
                       else 2 * 1024 * 1024 if operation in (*apuracao.OPERACOES, *apuracao.OPERACOES_NOTAS,
                                                             *rotas_tabelas.SALVAR, *rascunhos.SALVAR)
                       else rotas_redacao.LIMITE_CORPO_TEXTO if operation in rotas_redacao.TEXTO
                       else 128 * 1024 if operation in ('caderno-salvar', 'diligencias-criar', 'diligencias-atualizar', 'diligencias-responder',
                                                     *rotas_evidencia.SALVAR, *rotas_redacao.SALVAR) else 32768)
            if not 0 < length <= maximum:
                raise ValueError('Requisição vazia ou muito grande.')
            if em_fluxo:
                self.close_connection = True  # one upload per connection: what is left is never read as a request
                self._fluxo = rotas_documentos.Fluxo(self.rfile, length)
                body = rotas_documentos.ler_manifesto(self.rfile, length)
                self._fluxo.restante -= len(body)
            else:
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
        # The newsroom goes in every audit line of this request (its id only; none in the local mode).
        registro_acesso.definir(conta=principal.get('conta'), organizacao=(principal.get('organizacao') or {}).get('id'))
        # Pilot mode requires an explicit Origin; local mode keeps accepting same-origin requests without it.
        origem = self.headers.get('Origin', None if self.server.com_contas else self.server.origin)
        if (origem != self.server.origin
                or not secrets.compare_digest(self.headers.get('X-Session-Token', '').encode('utf-8'), principal['csrf'].encode('ascii'))
                or self.headers.get_content_type() != (rotas_documentos.TIPO_LOTE if em_fluxo else 'application/json')):
            self._json(403, {'erro': 'Origem ou sessão não autorizada. Recarregue a página.'})
            return
        operation = urlsplit(self.path).path.removeprefix('/api/')
        # Operation names keep the historical "codex-" prefix; inference now goes through the API adapter.
        if operation not in OPERACOES_API:
            self._json(404, {'erro': 'Operação não encontrada.'})
            return
        caso_novo = None  # a case whose ownership this request registered, undone if the creation is refused
        try:
            data = json.loads(body)
            if not isinstance(data, dict):
                raise ValueError('Requisição deve ser um objeto JSON.')
            registro_acesso.definir(operacao=operation)
            registro_acesso.referenciar_caso(data.get('caso'))  # só uma referência com chave: o nome do caso não vai ao registro
            # The gate: role, newsroom and participation, in one place (scripts/autorizacao.py), before any route.
            try:
                concedido = autorizacao.conferir(self.server.root, self.server.modo, principal, operation, data)
            except autorizacao.Recusa as recusa:
                self._recusado(recusa, principal)
                return
            # `dono`: the account, when it only reaches its own conversations. `casos_liberados`: its reach,
            # re-read on each request (None only in the local mode).
            data, dono, casos_liberados = concedido.dados, concedido.dono, principal['casos']
            if concedido.novo:
                data = autorizacao.registrar_novo(self.server.root, principal, data)
                caso_novo = data['caso']
            if operation == 'sessao-sair':
                self._sair()
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
            elif operation in CADASTRO_NA_FILA:
                # Through the extraction queue: no lock is held while files are read (CONF-02).
                result = self._cadastro_na_fila(operation, data)
            elif operation in rotas_gestao.OPERACOES:
                result = self._gestao(operation, data, principal, concedido)
            elif operation in rotas_equipe.OPERACOES or operation in CONTA_PROPRIA:
                result = self._equipe(operation, data, principal)
            elif operation in rotas_conversa.OPERACOES:
                result = self._conversa(operation, data, dono, casos_liberados, consulta_contada,
                                        conta=principal['conta'])
                if result is RESPONDIDO:
                    return
            else:
                conta = ({'id': principal['conta'], 'nome': principal['nome']}
                         if self.server.com_contas else None)
                abertos = (self.server.originais_abertos(self._chave_originais(principal, data))
                           if operation == 'achados-revisao-salvar' else None)
                with self.server.cadastro_lock:
                    result = executar(self.server.root, operation, data, conta, abertos, casos=principal['casos'],
                                      restrito=concedido.restrito)
                    if operation in rotas_downloads.ORIGINAIS_PASSAGEM:
                        # Read where it was validated; the slow part (sending) runs after the lock.
                        conteudo = self._ler_original(operation, data, result)
            if operation in rotas_downloads.ORIGINAIS_PASSAGEM:
                self._enviar_original(operation, data, conteudo, principal)
            else:
                result = autorizacao.filtrar(self.server.root, self.server.modo, principal, operation, result)
                estado = 400 if result.get('estado') == 'erro_consulta' else 200
                if operation in EXPORTACOES_EM_JSON and estado == 200:
                    self._auditar_download('ok')  # recorded before answering: the answer is the delivery
                self._json(estado, result)
        except revisao_humana.OriginalNaoConferido as exc:
            self._json(400, {'estado': 'erro', 'codigo': 'conferencia_sem_original', 'erro': str(exc), 'faltam': exc.faltam})
        except apuracao.ConflitoNota as exc:
            self._json(409, {'estado': 'erro', 'codigo': 'conflito', 'erro': str(exc), 'atual': exc.atual})
        except rascunhos.ConflitoRascunho as exc:
            self._json(409, {'estado': 'erro', 'codigo': 'rascunho_conflito', 'erro': str(exc), 'atual': exc.atual})
        except acesso.Bloqueado as exc:  # too many wrong passwords on a sensitive operation
            self._json(429, {'estado': 'bloqueado', 'codigo': 'bloqueado', 'erro': str(exc)})
        except acesso.Recusada as exc:  # a refusal with its own status and code (password asked again, last dono)
            self._json(exc.status, {'estado': 'proibido' if exc.status == 403 else 'erro', 'codigo': exc.codigo,
                                    'erro': str(exc)})
        except (ValueError, OSError, KeyError, TypeError, sqlite3.Error) as exc:
            if operation in DOWNLOADS:
                self._auditar_download('falha')
            if caso_novo:
                autorizacao.desfazer_novo(self.server.root, caso_novo)
            convidado = autorizacao.restrito(principal)
            # Guests get user-facing ValueError messages only; internal errors stay generic.
            mensagem = ('Falha ao processar a requisição no servidor.'
                        if convidado and not isinstance(exc, ValueError) else str(exc))
            self._json(400, {'estado': 'erro', 'erro': mensagem}, exc)

    def _recusado(self, recusa, principal, pagina=False):
        """Answer a refusal of the gate. The real reason goes to the audit log only (`acesso_negado`, with
        `motivo`), never to the browser."""
        registro_acesso.registrar('acesso_negado', 'negado', (principal or {}).get('conta'), codigo=recusa.codigo,
                                  motivo=recusa.motivo,
                                  organizacao=((principal or {}).get('organizacao') or {}).get('id'))
        if pagina:
            self._pagina_recusada(recusa)
        else:
            self._json(recusa.status, recusa.corpo)

    def _cadastro_na_fila(self, operation, data):
        """Upload or PDF preparation through `server.fila`: the receipt, or the queue state if asynchronous."""
        if operation == 'cadastrar':
            return receber_documentos(self.server.root, data, fila=self.server.fila, fluxo=self.__dict__.get('_fluxo'))
        if not diagnostico()['extracao_pdf']['disponivel']:
            raise ValueError('O extrator de PDF não está disponível nesta instância. Encerre a Mesa e abra pelo iniciador atualizado.')
        if type(data.get('assincrono', False)) is not bool:
            raise ValueError('Indicação de envio assíncrono inválida.')
        lote = self.server.fila.preparar_pdfs(data.get('caso'))
        if data.get('assincrono'):
            return {'estado': 'enfileirado', **self.server.fila.consultar(lote=lote)}
        return self.server.fila.aguardar(lote)

    def _estado_da_fila(self):
        """`GET /api/fila?lote=<id>` or `?caso=<id>`: state of the extraction queue.

        Read only, no case content; the contract of each batch is in `fila_extracao`. Whoever reaches a
        case sees its batches, for the progress of an upload (UX-05): ``?caso=`` of a case within reach,
        ``?lote=`` of a batch of one of them, or no parameter for the batches of every case within reach.
        A batch of a case out of reach reads as not found (its existence is not told), and outside the
        local mode the receipt goes without its file path (`autorizacao.filtrar`).
        """
        principal = self._principal()
        if principal is None:
            self._proibido()
            return
        consulta = parse_qs(urlsplit(self.path).query)
        lote, caso = (consulta.get(k, [None])[0] for k in ('lote', 'caso'))
        try:
            autorizacao.conferir(self.server.root, self.server.modo, principal, 'GET:/api/fila',
                                 {k: v for k, v in (('lote', lote), ('caso', caso)) if v is not None})
            self._json(200, autorizacao.filtrar(self.server.root, self.server.modo, principal, 'GET:/api/fila',
                                                self.server.fila.consultar(lote=lote, caso=caso)))
        except autorizacao.Recusa as recusa:
            self._recusado(recusa, principal)
        except ValueError as exc:
            self._json(400, {'erro': str(exc)})

    def log_message(self, format, *args):
        # Do not print queries, source content or token to the terminal. The audit trail (scripts/registro_acesso.py)
        # is separate: events without content, never the request line.
        return


def servir(server, prazo=PRAZO_ENCERRAMENTO):
    """Run the Mesa: clean what a dead process left, serve, and stop in order.

    Stops on SIGTERM (``docker stop``; the Compose ``init`` forwards it), SIGBREAK
    (Ctrl+Break on Windows), Ctrl+C and "Encerrar Mesa" (``codex-desligar``).
    """
    try:
        resumo = trava_cadastro.recuperar(server.root)
    except OSError as exc:  # the Mesa still starts: an abandoned lock is also recovered on first use
        print(f'Partida: limpeza da trava de cadastro não concluída ({exc.strerror or exc}).', file=sys.stderr, flush=True)
        resumo = {}
    if resumo.get('abandonada') or resumo.get('antiga_removida') or resumo.get('preparo_removido'):
        print('Partida: trava de cadastro recuperada de uma execução interrompida.', flush=True)
    try:  # a permanent deletion cut by a crash: back to the trash, whole, or concluded (in the background)
        apagados = apagamento.retomar(server.root, segundo_plano=True)
    except OSError as exc:
        print(f'Partida: apagamento definitivo interrompido não retomado ({exc.strerror or exc}).', file=sys.stderr, flush=True)
    else:
        if apagados['desfeitos'] or apagados['concluidos']:
            print('Partida: apagamento definitivo interrompido retomado.', flush=True)
    anteriores = {}
    if threading.current_thread() is threading.main_thread():
        for nome in ('SIGTERM', 'SIGBREAK'):
            numero = getattr(signal, nome, None)
            if numero is not None:
                anteriores[numero] = signal.signal(numero, lambda *_: server.pedir_encerramento())
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        for numero, anterior in anteriores.items():
            signal.signal(numero, anterior)
        completo = server.encerrar(prazo)
        print('Mesa encerrada.' if completo else
              'Mesa encerrada antes do fim de uma operação; a próxima partida limpa o que ficou.', flush=True)


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
    try:
        proxies_confiaveis.validar_ambiente()  # lista de proxies inválida: não sobe, com a mensagem
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    if args.modo != 'local':
        ambiente = os.environ.get('VLADO_AMBIENTE', '').strip()
        try:  # with real data the hosted service does not start without real e-mail delivery (decision 12)
            correio.conferir_partida(args.modo, ambiente if ambiente in AMBIENTES else 'homologacao')
        except ValueError as exc:
            raise SystemExit(str(exc)) from None
    # Extraction and OCR in separate processes; VLADO_EXTRACAO=local keeps them in threads.
    with Servidor((args.host, args.porta), root=Path(args.dados) if args.dados else ROOT,
                  modo=args.modo, origem=args.origem,
                  extracao=os.environ.get('VLADO_EXTRACAO') or 'processos') as server:
        if server.com_contas:
            try:  # the daily sweep also runs at the start: invitations past their date, old activity
                acesso.manutencao(server.root)
            except (ValueError, OSError):
                pass  # an unreadable store answers 503 to each request; it does not stop the start
        print(f'Mesa de apuração ({args.modo}): {server.origin}', flush=True)
        print('Encerre com Ctrl+C.', flush=True)
        if args.modo != 'piloto' and not args.sem_abrir:
            webbrowser.open(server.origin)
        servir(server)


if __name__ == '__main__':
    try:
        main()
    except OSError as exc:
        if os.name == 'nt' and os.environ.get('APURACAO_OCULTO') == '1':
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, f'Não foi possível iniciar a Mesa de apuração.\n{exc}\nSe a porta 8765 estiver ocupada, encerre o servidor anterior.', 'Mesa de apuração', 16)
        else:
            raise
