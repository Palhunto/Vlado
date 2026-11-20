"""Arquivos da interface servidos por ``GET`` (lista fechada; nenhum caminho vem do cliente).

Separado de ``interface_pesquisa`` sem mudar comportamento. Só os caminhos de ``ARQUIVOS``
são publicados; licenças, manifestos e demais arquivos de ``interface/`` não são rotas.
``index.html`` leva o token da sessão e por isso nunca vai para cache; os demais revalidam
por ETag, e os pacotes de terceiros pedidos com versão (``?v=…``) ficam em cache imutável.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

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
            '/quadros.js': ('quadros.js', 'text/javascript; charset=utf-8'),
            '/analise.js': ('analise.js', 'text/javascript; charset=utf-8'),
            '/indicador_salvamento.js': ('indicador_salvamento.js', 'text/javascript; charset=utf-8')}


class RotasEstaticas:
    """Mixin of the request handler: uses its ``_send``, ``_json``, ``_principal`` and ``server``."""

    def _estatico(self, path):
        if path not in ARQUIVOS:
            self._json(404, {'erro': 'Página não encontrada.'})
            return
        name, content_type = ARQUIVOS[path]
        content = (ASSETS / name).read_bytes()
        if name == 'index.html':
            principal = self._principal()
            piloto = self.server.modo == 'piloto'
            content = (content.replace(b'__SESSION_TOKEN__', principal['csrf'].encode('ascii'))
                       .replace(b'__IDIOMA_PADRAO__', b'en' if piloto else b'pt')
                       .replace(b'__PAPEL__', principal['papel'].encode('ascii'))
                       .replace(b'__MODO__', self.server.modo.encode('ascii')))
            extra = ({} if self.server.com_contas
                     else {'Set-Cookie': f'apuracao_session={self.server.token}; HttpOnly; SameSite=Strict; Path=/'})
            self._send(200, content, content_type, extra)
        else:
            # Static files revalidate on every load (no stale code after an update) but skip the
            # download when unchanged; index.html stays no-store because it carries session tokens.
            etag = '"' + hashlib.sha256(content).hexdigest()[:32] + '"'
            # Third-party bundles requested with their version (?v=…) never change under that URL.
            versionado = name.startswith('vendor/') and re.fullmatch(r'v=[0-9A-Za-z._-]{1,40}', urlsplit(self.path).query)
            cache = 'public, max-age=31536000, immutable' if versionado else 'no-cache'
            if self.headers.get('If-None-Match') == etag:
                self._send(304, b'', content_type, {'ETag': etag}, cache=cache)
            else:
                self._send(200, content, content_type, {'ETag': etag}, cache=cache)
