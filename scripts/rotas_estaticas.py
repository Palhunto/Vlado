"""Arquivos da interface servidos por ``GET`` (lista fechada; nenhum caminho vem do cliente).

Separado de ``interface_pesquisa`` sem mudar comportamento. ``_estatico`` publica só os
caminhos de ``ARQUIVOS``; licenças, manifestos e demais arquivos de ``interface/`` não são
rotas. Fora desta lista, ``do_GET`` serve ``entrar.html`` em ``/entrar`` e ``/ativar/<token>``
(modos com contas) e em ``/primeiro-acesso`` (só ``local-contas``), e responde ``/saude`` e
``/api/*`` em JSON.
``index.html`` leva o token da sessão e por isso nunca vai para cache; os demais revalidam
por ETag, e os pacotes de terceiros pedidos com versão (``?v=…``) ficam em cache imutável.

**Cache imutável por hash, sem passo de build** (combinado com o Lume, parte C):

- ``versao(nome)`` são os 12 primeiros hex do sha256 do arquivo como é servido. Um arquivo pedido
  com ``?v=<versao>`` vai com ``public, max-age=31536000, immutable``; sem ``v``, ou com um ``v``
  que não bate com o conteúdo atual, revalida por ETag (``no-cache``), como antes.
- Nos arquivos ``.css`` e ``.html`` servidos (``index.html`` e ``entrar.html`` incluídos), o servidor
  troca ``__V:<nome>__`` pela versão desse arquivo. ``<nome>`` é o nome em ``ARQUIVOS`` (o caminho
  sem a barra inicial, ``fonts/SourceSerif4-latin.woff2``) ou só o nome do arquivo, quando ele é
  único (``SourceSerif4-latin.woff2``). A versão de um CSS é a do conteúdo já trocado: as fontes
  entram no hash do CSS, e o CSS no do ``index.html``. Um nome que não está na lista fica como está.
- ``__VERSOES__`` (no ``index.html`` e no ``entrar.html``) vira o JSON ``{nome: versão}`` de todos os
  arquivos listados que existem, para montar a URL do que se carrega sob demanda.
- Arquivo listado que ainda não existe no disco responde 404.
- Compressão: com ``Accept-Encoding`` que aceita gzip, texto, JavaScript, JSON, SVG e manifesto vão
  com ``Content-Encoding: gzip`` e ``Vary: Accept-Encoding``, comprimidos uma vez por versão e
  guardados em memória; fontes e imagens nunca. O ETag é o do conteúdo sem comprimir. As páginas com
  o token da sessão (``index.html``) não são comprimidas.
"""
from __future__ import annotations

from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys
import threading
from urllib.parse import urlsplit

import autorizacao

# Inside the PyInstaller bundle the interface lives next to the frozen modules (sys._MEIPASS).
ASSETS = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1])) / 'interface'
ARQUIVOS = {'/': ('index.html', 'text/html; charset=utf-8'),
            '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
            '/codex.js': ('codex.js', 'text/javascript; charset=utf-8'),
            '/i18n.js': ('i18n.js', 'text/javascript; charset=utf-8'),
            '/i18n_en.js': ('i18n_en.js', 'text/javascript; charset=utf-8'),
            '/configuracao_ia.js': ('configuracao_ia.js', 'text/javascript; charset=utf-8'),
            '/piloto.js': ('piloto.js', 'text/javascript; charset=utf-8'),
            '/entrar.js': ('entrar.js', 'text/javascript; charset=utf-8'),
            '/entrar.css': ('entrar.css', 'text/css; charset=utf-8'),
            '/gerenciar.js': ('gerenciar.js', 'text/javascript; charset=utf-8'),
            '/tema.js': ('tema.js', 'text/javascript; charset=utf-8'),
            '/fator.js': ('fator.js', 'text/javascript; charset=utf-8'),
            '/conta.js': ('conta.js', 'text/javascript; charset=utf-8'),
            '/equipe.js': ('equipe.js', 'text/javascript; charset=utf-8'),
            '/leitura.js': ('leitura.js', 'text/javascript; charset=utf-8'),
            '/experiencia.js': ('experiencia.js', 'text/javascript; charset=utf-8'),
            '/desktop.js': ('desktop.js', 'text/javascript; charset=utf-8'),
            '/revisao.js': ('revisao.js', 'text/javascript; charset=utf-8'),
            '/diligencias.js': ('diligencias.js', 'text/javascript; charset=utf-8'),
            '/observacoes.js': ('observacoes.js', 'text/javascript; charset=utf-8'),
            '/continuidade.js': ('continuidade.js', 'text/javascript; charset=utf-8'),
            '/fontes_web.js': ('fontes_web.js', 'text/javascript; charset=utf-8'),
            '/caderno.js': ('caderno.js', 'text/javascript; charset=utf-8'),
            '/apuracao.js': ('apuracao.js', 'text/javascript; charset=utf-8'),
            '/editor_notas.js': ('editor_notas.js', 'text/javascript; charset=utf-8'),
            '/redacao.js': ('redacao.js', 'text/javascript; charset=utf-8'),
            '/redacao.css': ('redacao.css', 'text/css; charset=utf-8'),
            '/vendor/vditor/dist/index.min.js': ('vendor/vditor/dist/index.min.js', 'text/javascript; charset=utf-8'),
            '/vendor/vditor/dist/index.css': ('vendor/vditor/dist/index.css', 'text/css; charset=utf-8'),
            '/vendor/vditor/dist/js/lute/lute.min.js': ('vendor/vditor/dist/js/lute/lute.min.js', 'text/javascript; charset=utf-8'),
            '/vendor/vditor/dist/js/i18n/pt_BR.js': ('vendor/vditor/dist/js/i18n/pt_BR.js', 'text/javascript; charset=utf-8'),
            '/vendor/vditor/dist/js/icons/ant.js': ('vendor/vditor/dist/js/icons/ant.js', 'text/javascript; charset=utf-8'),
            '/vendor/vditor/dist/css/content-theme/light.css': ('vendor/vditor/dist/css/content-theme/light.css', 'text/css; charset=utf-8'),
            '/fonts/SourceSerif4-Roman.ttf': ('fonts/SourceSerif4-Roman.ttf', 'font/ttf'),
            '/fonts/SourceSans3-Upright.otf': ('fonts/SourceSans3-Upright.otf', 'font/otf'),
            '/vendor/qrcodegen/qrcodegen.js': ('vendor/qrcodegen/qrcodegen.js', 'text/javascript; charset=utf-8'),
            '/vendor/pdfjs/legacy/build/pdf.min.mjs': ('vendor/pdfjs/legacy/build/pdf.min.mjs', 'text/javascript; charset=utf-8'),
            '/vendor/pdfjs/legacy/build/pdf.worker.min.mjs': ('vendor/pdfjs/legacy/build/pdf.worker.min.mjs', 'text/javascript; charset=utf-8'),
            '/manifest.webmanifest': ('manifest.webmanifest', 'application/manifest+json; charset=utf-8'),
            '/icones/vlado.svg': ('icones/vlado.svg', 'image/svg+xml'),
            '/icones/vlado-192.png': ('icones/vlado-192.png', 'image/png'),
            '/icones/vlado-512.png': ('icones/vlado-512.png', 'image/png'),
            '/icones/vlado-maskable-512.png': ('icones/vlado-maskable-512.png', 'image/png'),
            '/tokens.css': ('tokens.css', 'text/css; charset=utf-8'),
            '/style.css': ('style.css', 'text/css; charset=utf-8'),
            '/caderno.css': ('caderno.css', 'text/css; charset=utf-8'),
            '/componentes_o3.css': ('componentes_o3.css', 'text/css; charset=utf-8'),
            '/dialogo.js': ('dialogo.js', 'text/javascript; charset=utf-8'),
            '/estados.js': ('estados.js', 'text/javascript; charset=utf-8'),
            '/envio.js': ('envio.js', 'text/javascript; charset=utf-8'),
            '/documentos.js': ('documentos.js', 'text/javascript; charset=utf-8'),
            '/quadros.js': ('quadros.js', 'text/javascript; charset=utf-8'),
            '/analise.js': ('analise.js', 'text/javascript; charset=utf-8'),
            '/indicador_salvamento.js': ('indicador_salvamento.js', 'text/javascript; charset=utf-8'),
            # Fonts cut to Latin (the Lume's part C).
            '/fonts/SourceSerif4-latin.woff2': ('fonts/SourceSerif4-latin.woff2', 'font/woff2'),
            '/fonts/SourceSans3-latin.woff2': ('fonts/SourceSans3-latin.woff2', 'font/woff2')}

MARCADOR = re.compile(rb'__V:([0-9A-Za-z_./-]{1,160})__')
VERSOES = b'__VERSOES__'
COMPRIMIVEIS = ('text/javascript', 'application/javascript', 'application/json', 'image/svg+xml',
                'application/manifest+json')
_trava = threading.Lock()
_lidos = {}  # name -> ((mtime_ns, size), bytes, hash of the bytes)
_comprimidos = {}  # name -> (version, gzip bytes)


def _ler(nome):
    """(bytes, sha256 hex) of an interface file, read again only when it changes on disk."""
    caminho = ASSETS / nome
    estado = caminho.stat()
    chave = (estado.st_mtime_ns, estado.st_size)
    with _trava:
        guardado = _lidos.get(nome)
    if guardado is not None and guardado[0] == chave:
        return guardado[1], guardado[2]
    dados = caminho.read_bytes()
    resumo = hashlib.sha256(dados).hexdigest()
    with _trava:
        _lidos[nome] = (chave, dados, resumo)
    return dados, resumo


def _nomes():
    """Marker name -> name in ARQUIVOS: the name itself, and its file name when that is unique."""
    nomes = {nome: nome for nome, _ in ARQUIVOS.values()}
    vezes = Counter(Path(nome).name for nome in nomes)
    for nome in list(nomes):
        if vezes[Path(nome).name] == 1:
            nomes.setdefault(Path(nome).name, nome)
    return nomes


def _com_marcadores(nome):
    return nome.endswith(('.css', '.html'))


def conteudo(nome, _pilha=()):
    """The file as served: in CSS and HTML, each __V:<nome>__ replaced by that file's version and
    __VERSOES__ by the versions of all listed files. FileNotFoundError when it is not on disk."""
    dados, _ = _ler(nome)
    if not _com_marcadores(nome):
        return dados
    pilha, nomes = (*_pilha, nome), _nomes()

    def trocar(achado):
        alvo = nomes.get(achado.group(1).decode('ascii'))
        if alvo is None or alvo in pilha:
            return achado.group(0)
        try:
            return versao(alvo, pilha).encode('ascii')
        except OSError:
            return achado.group(0)
    dados = MARCADOR.sub(trocar, dados)
    if VERSOES in dados:
        dados = dados.replace(VERSOES, json.dumps(versoes(pilha), separators=(',', ':'), sort_keys=True).encode('ascii'))
    return dados


def versao(nome, _pilha=()):
    """12 hex of the sha256 of the file as served."""
    if not _com_marcadores(nome):
        return _ler(nome)[1][:12]
    return hashlib.sha256(conteudo(nome, _pilha)).hexdigest()[:12]


def versoes(_pilha=()):
    """{name: version} of every listed file on disk (the pages with the session token apart)."""
    resultado = {}
    for nome, _ in ARQUIVOS.values():
        if nome.endswith('.html') or nome in _pilha:
            continue
        try:
            resultado[nome] = versao(nome, _pilha)
        except OSError:
            pass
    return resultado


def _comprimivel(tipo):
    tipo = tipo.split(';')[0].strip().lower()
    return tipo.startswith('text/') or tipo in COMPRIMIVEIS


def _aceita_gzip(cabecalho):
    for parte in (cabecalho or '').split(','):
        token, *parametros = [p.strip() for p in parte.split(';')]
        if token.lower() not in ('gzip', '*'):
            continue
        qualidade = 1.0
        for parametro in parametros:
            if parametro.lower().startswith('q='):
                try:
                    qualidade = float(parametro[2:])
                except ValueError:
                    qualidade = 0.0
        if qualidade > 0:
            return True
    return False


def _gzip(nome, versao_atual, dados):
    with _trava:
        guardado = _comprimidos.get(nome)
    if guardado is not None and guardado[0] == versao_atual:
        return guardado[1]
    comprimido = gzip.compress(dados, compresslevel=6, mtime=0)
    with _trava:
        _comprimidos[nome] = (versao_atual, comprimido)
    return comprimido


class RotasEstaticas:
    """Mixin of the request handler: uses its ``_send``, ``_json``, ``_principal`` and ``server``."""

    def _estatico(self, path):
        if path not in ARQUIVOS:
            self._json(404, {'erro': 'Página não encontrada.'})
            return
        name, content_type = ARQUIVOS[path]
        try:
            content = conteudo(name)
        except FileNotFoundError:
            self._json(404, {'erro': 'Página não encontrada.'})
            return
        if name == 'index.html':
            principal = self._principal()
            piloto = self.server.modo == 'piloto'
            content = (content.replace(b'__SESSION_TOKEN__', principal['csrf'].encode('ascii'))
                       .replace(b'__IDIOMA_PADRAO__', b'en' if piloto else b'pt')
                       .replace(b'__PAPEL__', autorizacao.papel_para_interface(principal).encode('ascii'))
                       .replace(b'__MODO__', self.server.modo.encode('ascii')))
            extra = ({} if self.server.com_contas
                     else {'Set-Cookie': f'apuracao_session={self.server.token}; HttpOnly; SameSite=Strict; Path=/'})
            self._send(200, content, content_type, extra)
        else:
            # Static files revalidate on every load (no stale code after an update) but skip the
            # download when unchanged; index.html stays no-store because it carries session tokens.
            resumo = hashlib.sha256(content).hexdigest()
            etag = '"' + resumo[:32] + '"'
            consulta = urlsplit(self.path).query
            # Third-party bundles requested with their version (?v=…), and any file requested with the
            # hash of its content (?v=<versao>), never change under that URL.
            versionado = ((name.startswith('vendor/') and re.fullmatch(r'v=[0-9A-Za-z._-]{1,40}', consulta))
                          or consulta == 'v=' + resumo[:12])
            cache = 'public, max-age=31536000, immutable' if versionado else 'no-cache'
            extra = {'ETag': etag}
            comprimivel = _comprimivel(content_type)
            if comprimivel:
                extra['Vary'] = 'Accept-Encoding'
            if self.headers.get('If-None-Match') == etag:
                self._send(304, b'', content_type, extra, cache=cache)
            elif comprimivel and _aceita_gzip(self.headers.get('Accept-Encoding')):
                self._send(200, _gzip(name, resumo, content), content_type, {**extra, 'Content-Encoding': 'gzip'},
                           cache=cache)
            else:
                self._send(200, content, content_type, extra, cache=cache)
