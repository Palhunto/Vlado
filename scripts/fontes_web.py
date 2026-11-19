"""Web sources for cases created in the "documentos + web" mode. No model calls.

The mode is chosen once, when the journalist creates the case, and is stored in
the case manifest (`fontes_web`). Without it, nothing here touches the network.
With it, only the single host registered in the manifest is fetched, over https.
Every hop (the first request and each redirect) is checked before connecting:
same host, public address after DNS resolution, and the connection is pinned to
the address that was checked. Each capture records the full requested and final
address, the UTC access time, status, relevant headers, the content received and
its SHA-256, in `casos/<caso>/fontes_web/`, separate from the originals, plus a
line in the append-only `casos/<caso>/fontes_web/registro.jsonl`.

Captured content is data from the source, never an instruction: it is stored and
indexed as received and is not interpreted.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack, nullcontext
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import http.client
import ipaddress
import json
from pathlib import Path
import re
import socket
import ssl
import sys
import time
import urllib.parse
import uuid

from comum import (ROOT, capturas_como_documentos, conferir_arquivo, dentro, escrever_json, ler_json, sha256,
                   pasta_preparacao)

MODO_DOCUMENTAL = 'somente_documental'
MODO_WEB = 'documentos_web'
MODOS = (MODO_DOCUMENTAL, MODO_WEB)
PASTA = 'fontes_web'
ID_CASO = r'[a-z0-9][a-z0-9_-]{0,63}'
ID_CAPTURA = re.compile(r'W[0-9]{3,6}')
ROTULO = re.compile(r'(?!-)[a-z0-9-]{1,63}(?<!-)')
MAX_BYTES = 20 * 1024 * 1024
MAX_TEXTO_ABRIR = 2 * 1024 * 1024
MAX_REDIRECIONAMENTOS = 5
MAX_CAPTURAS = 200
TEMPO_LIMITE = 20        # seconds per network operation (connect, each read)
TEMPO_TOTAL = 60         # seconds for the whole capture, redirects included
USER_AGENT = 'captura-documental/1.0'
REDIRECIONAMENTOS = (301, 302, 303, 307, 308)
TIPOS = {'text/html': '.html', 'application/xhtml+xml': '.html', 'text/plain': '.txt',
         'application/pdf': '.pdf'}
TEXTUAIS = {'.html', '.txt'}
CABECALHOS = ('content-type', 'content-length', 'last-modified', 'etag', 'date', 'content-language')

# Explicit test switch. Off in operation; tests turn it on to reach their http.server on
# 127.0.0.1 (http and loopback are accepted only for that exact address). Not read from
# configuration, environment or requests.
TESTE_LOCAL = False
HOST_TESTE = '127.0.0.1'


class DominioRecusado(ValueError):
    """The address (or a redirect) leaves the single domain registered for the case."""


class EnderecoRecusado(ValueError):
    """The host resolves to a non-public address (private, loopback, link-local, reserved...)."""


def normalizar_dominio(value) -> str:
    """Accept a bare host name or IP literal; refuse schemes, paths, ports and wildcards."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Informe o domínio permitido para as fontes web (ex.: www.exemplo.gov.br).')
    host = value.strip().lower().rstrip('.')
    if any(c in host for c in '/:@?#*\\ '):
        raise ValueError('Domínio permitido: informe só o nome do site, sem http://, caminho, porta ou curinga.')
    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        pass
    try:
        host = host.encode('idna').decode('ascii')
    except UnicodeError as exc:
        raise ValueError('Domínio permitido inválido.') from exc
    if len(host) > 253 or not all(ROTULO.fullmatch(label) for label in host.split('.')):
        raise ValueError('Domínio permitido inválido.')
    return host


def definir_modo(modo=None, dominio=None) -> dict:
    """Build the manifest block at case creation. Default: documents only."""
    modo = modo or MODO_DOCUMENTAL
    if modo not in MODOS:
        raise ValueError('Modo de fontes desconhecido: use somente_documental ou documentos_web.')
    if modo == MODO_DOCUMENTAL:
        if dominio:
            raise ValueError('Domínio permitido só pode ser informado no modo documentos_web.')
        return {'modo': MODO_DOCUMENTAL, 'dominio_permitido': None}
    return {'modo': MODO_WEB, 'dominio_permitido': normalizar_dominio(dominio),
            'definido_em_utc': datetime.now(timezone.utc).isoformat(),
            'definido_por': 'jornalista_na_criacao_do_caso'}


def modo_do_caso(manifest: dict) -> dict:
    """Manifests created before this version are documents-only."""
    block = manifest.get('fontes_web') or {'modo': MODO_DOCUMENTAL, 'dominio_permitido': None}
    if block.get('modo') not in MODOS:
        raise ValueError('Modo de fontes do manifesto desconhecido.')
    if block['modo'] == MODO_WEB:
        if normalizar_dominio(block.get('dominio_permitido')) != block['dominio_permitido']:
            raise ValueError('Domínio permitido do manifesto não está normalizado.')
    elif block.get('dominio_permitido') is not None or manifest.get('capturas_web'):
        raise ValueError('Caso somente documental não pode ter domínio ou capturas web.')
    return block


def _host(url) -> str:
    host = (urllib.parse.urlsplit(url).hostname or '').rstrip('.')
    try:
        return host.encode('idna').decode('ascii').lower()
    except UnicodeError:
        return host.lower()


def conferir_url(url, dominio: str) -> str:
    """Return the URL unchanged if it is https (or test-mode http) on exactly the permitted host."""
    if not isinstance(url, str) or not url.strip() or len(url) > 4096:
        raise ValueError('Informe o endereço completo da página (https://).')
    url = url.strip()
    if any(ord(c) < 33 or c in '\\' for c in url):
        raise ValueError('Endereço com espaço, barra invertida ou caractere de controle não é aceito.')
    parts = urllib.parse.urlsplit(url)
    try:
        parts.port
    except ValueError as exc:
        raise ValueError('Porta inválida no endereço.') from exc
    if parts.scheme not in ('http', 'https') or not parts.hostname:
        raise ValueError('Endereço deve começar com https://.')
    if parts.username is not None or parts.password is not None:
        raise ValueError('Endereço com usuário ou senha não é aceito.')
    host = _host(url)
    if host != dominio:
        raise DominioRecusado(f'Domínio recusado: {host or "(vazio)"}. Este caso só permite {dominio}.')
    if parts.scheme == 'http' and not (TESTE_LOCAL and host == HOST_TESTE):
        raise ValueError('Endereço deve começar com https://; http sem criptografia não é aceito.')
    return url


def conferir_ip(value) -> str:
    """Refuse every non-public address. Loopback 127.0.0.1 only with the explicit test switch."""
    try:
        ip = ipaddress.ip_address(str(value).split('%', 1)[0])
    except ValueError as exc:
        raise EnderecoRecusado('Endereço de rede inválido; captura não realizada.') from exc
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if TESTE_LOCAL and ip == ipaddress.ip_address(HOST_TESTE):
        return str(ip)
    if (not ip.is_global or ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
            or ip.is_reserved or ip.is_unspecified
            or (isinstance(ip, ipaddress.IPv6Address) and (ip.sixtofour is not None or ip.teredo is not None))):
        raise EnderecoRecusado('O site aponta para um endereço de rede interno ou reservado; captura não realizada.')
    return str(ip)


def resolver(host: str, port: int) -> str:
    """Resolve once and check every address returned; the connection uses the first one."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError, OSError) as exc:
        raise ValueError('Não foi possível resolver o nome do site; captura não realizada.') from exc
    addresses = [info[4][0] for info in infos]
    if not addresses:
        raise ValueError('Não foi possível resolver o nome do site; captura não realizada.')
    checked = [conferir_ip(address) for address in addresses]
    return checked[0]


class _HTTPFixada(http.client.HTTPConnection):
    """Connect to the already checked address; Host header keeps the site name."""

    def __init__(self, host, port, ip, timeout):
        super().__init__(host, port, timeout=timeout)
        self._ip = ip

    def connect(self):
        self.sock = socket.create_connection((self._ip, self.port), self.timeout)


class _HTTPSFixada(http.client.HTTPSConnection):
    """TLS to the already checked address, with certificate and SNI for the site name."""

    def __init__(self, host, port, ip, timeout):
        super().__init__(host, port, timeout=timeout, context=ssl.create_default_context())
        self._ip = ip

    def connect(self):
        sock = socket.create_connection((self._ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def _restante(prazo):
    left = prazo - time.monotonic()
    if left <= 0:
        raise ValueError('Tempo limite da captura esgotado; captura não realizada.')
    return min(TEMPO_LIMITE, left)


def _ler(response, prazo):
    chunks, total = [], 0
    while True:
        _restante(prazo)
        chunk = response.read(64 * 1024)
        if not chunk:
            return b''.join(chunks)
        total += len(chunk)
        if total > MAX_BYTES:
            raise ValueError('Página excede 20 MB; captura não realizada.')
        chunks.append(chunk)


def _baixar(url, dominio):
    """GET with manual redirects. Each hop: same host, public IP, pinned connection."""
    prazo = time.monotonic() + TEMPO_TOTAL
    cadeia, atual = [], url
    while True:
        conferir_url(atual, dominio)
        parts = urllib.parse.urlsplit(atual)
        https = parts.scheme == 'https'
        port = parts.port or (443 if https else 80)
        ip = resolver(parts.hostname, port)
        connection = (_HTTPSFixada if https else _HTTPFixada)(parts.hostname, port, ip, _restante(prazo))
        target = (parts.path or '/') + (f'?{parts.query}' if parts.query else '')
        try:
            connection.request('GET', target, headers={'User-Agent': USER_AGENT, 'Accept': '*/*',
                                                       'Accept-Encoding': 'identity'})
            response = connection.getresponse()
            status = response.status
            if status in REDIRECIONAMENTOS:
                location = response.getheader('Location')
                if not location:
                    raise ValueError(f'O site respondeu {status} sem destino; captura não realizada.')
                if len(cadeia) >= MAX_REDIRECIONAMENTOS:
                    raise ValueError('Redirecionamentos demais; captura não realizada.')
                novo = urllib.parse.urljoin(atual, location.strip())
                conferir_url(novo, dominio)
                cadeia.append({'de': atual, 'para': novo, 'status_http': status})
                atual = novo
                continue
            if status != 200:
                raise ValueError(f'O site respondeu {status}; captura não realizada.')
            kind = response.msg.get_content_type()
            if kind not in TIPOS:
                raise ValueError(f'Tipo de conteúdo não aceito ({kind}): só HTML, texto ou PDF.')
            encoding = (response.getheader('Content-Encoding') or 'identity').strip().lower()
            if encoding != 'identity':
                raise ValueError('Conteúdo comprimido não aceito; captura não realizada.')
            declared = response.getheader('Content-Length')
            if declared and declared.strip().isdigit() and int(declared) > MAX_BYTES:
                raise ValueError('Página excede 20 MB; captura não realizada.')
            content = _ler(response, prazo)
            headers = {k.lower(): v for k, v in response.getheaders() if k.lower() in CABECALHOS}
            return {'url_final': atual, 'status_http': status, 'cabecalhos': headers,
                    'redirecionamentos': cadeia, 'conteudo': content, 'tipo_conteudo': kind,
                    'charset': response.msg.get_content_charset(), 'endereco_ip': ip}
        except (OSError, http.client.HTTPException) as exc:
            raise ValueError(f'Não foi possível acessar o endereço ({type(exc).__name__}); '
                             'captura não realizada.') from exc
        finally:
            connection.close()


class _Texto(HTMLParser):
    BLOCOS = {'p', 'div', 'br', 'li', 'tr', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'section',
              'article', 'header', 'footer', 'table', 'ul', 'ol', 'dt', 'dd', 'blockquote', 'pre'}
    OCULTOS = {'script', 'style', 'noscript', 'template', 'svg'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.partes, self.oculto, self.titulo, self._no_titulo = [], 0, None, False

    def handle_starttag(self, tag, attrs):
        if tag in self.OCULTOS:
            self.oculto += 1
        elif tag == 'title':
            self._no_titulo = True
        elif tag in self.BLOCOS or tag in ('td', 'th'):
            self.partes.append('\n' if tag in self.BLOCOS else ' | ')

    def handle_endtag(self, tag):
        if tag in self.OCULTOS:
            self.oculto = max(0, self.oculto - 1)
        elif tag == 'title':
            self._no_titulo = False
        elif tag in self.BLOCOS:
            self.partes.append('\n')

    def handle_data(self, data):
        if self._no_titulo:
            self.titulo = ((self.titulo or '') + data.strip())[:500]
        elif not self.oculto:
            self.partes.append(data)


def _charset_html(content: bytes):
    match = re.search(rb'<meta[^>]+charset\s*=\s*["\']?([A-Za-z0-9_-]+)', content[:4096], re.I)
    return match[1].decode('ascii') if match else None


def _decodificar(content, charset):
    for candidate in (charset, 'utf-8'):
        if candidate:
            try:
                return content.decode(candidate), candidate, False
            except (LookupError, UnicodeDecodeError):
                continue
    return content.decode('utf-8', errors='replace'), 'utf-8', True


def texto_da_captura(content: bytes, extensao: str, charset=None):
    """Plain UTF-8 working copy; lines are the observable locator. Not an editorial reading."""
    if extensao == '.html':
        charset = charset or _charset_html(content)
    text, used, replaced = _decodificar(content, charset)
    title = None
    if extensao == '.html':
        parser = _Texto()
        parser.feed(text)
        parser.close()
        title = parser.titulo
        text = ''.join(parser.partes)
    lines = [re.sub(r'[ \t\r\f\v]+', ' ', line).strip() for line in text.splitlines()]
    compact = []
    for line in lines:
        if line or (compact and compact[-1]):
            compact.append(line)
    while compact and not compact[-1]:
        compact.pop()
    return '\n'.join(compact) + '\n', {'charset_usado': used, 'caracteres_substituidos': replaced,
                                      'titulo_pagina': title}


def _novo_id(manifest):
    used = {c['id'] for c in manifest.get('capturas_web', [])}
    number = 1
    while f'W{number:03d}' in used:
        number += 1
    return f'W{number:03d}'


def _manifesto_web(root, caso):
    """Read and check the case manifest and its captures; return (path, bytes, manifest, block)."""
    from lixeira import conferir_disponivel
    conferir_disponivel(root, caso)
    manifest_path = dentro(root, f'casos/{caso}/manifesto.json')
    before = manifest_path.read_bytes()
    manifest = ler_json(manifest_path)
    if manifest.get('caso_id') != caso:
        raise ValueError('Manifesto pertence a outro caso.')
    block = modo_do_caso(manifest)
    list(arquivos_web(root, manifest))
    return manifest_path, before, manifest, block


def _travas(root, trava):
    from cadastrar_documentos import _trava
    stack = ExitStack()
    stack.enter_context(trava or nullcontext())
    stack.enter_context(_trava(root))
    return stack


def capturar(root, caso, url, *, observacao=None, trava=None, _baixar_fn=None):
    """Fetch one page of the case's permitted domain and publish it as a new capture.

    The network fetch runs outside the locks; `trava` is an optional outer lock (the Mesa's
    cadastro lock) taken together with the project lock to check and to publish.
    """
    from cadastrar_documentos import _atomico, _bytes
    if not isinstance(caso, str) or not re.fullmatch(ID_CASO, caso):
        raise ValueError('Identificador de caso inválido.')
    if observacao is not None and (not isinstance(observacao, str) or len(observacao) > 500):
        raise ValueError('Observação da captura: texto de até 500 caracteres.')
    with _travas(root, trava):
        _, _, manifest, block = _manifesto_web(root, caso)
        if block['modo'] != MODO_WEB:
            raise ValueError('Este caso foi criado como apuração somente documental; '
                             'fontes web não são permitidas. O modo só é escolhido na criação.')
        if len(manifest.get('capturas_web', [])) >= MAX_CAPTURAS:
            raise ValueError(f'Limite de {MAX_CAPTURAS} capturas web por caso atingido.')
        dominio = block['dominio_permitido']
        url = conferir_url(url, dominio)
    acessado = datetime.now(timezone.utc).isoformat()
    got = (_baixar_fn or _baixar)(url, dominio)
    concluido = datetime.now(timezone.utc).isoformat()
    ext = TIPOS.get(got['tipo_conteudo'])
    if ext is None:
        raise ValueError('Tipo de conteúdo não aceito: só HTML, texto ou PDF.')
    content = got['conteudo']
    digest = hashlib.sha256(content).hexdigest()
    with _travas(root, trava):
        manifest_path, manifest_before, manifest, block = _manifesto_web(root, caso)
        if block['modo'] != MODO_WEB or block['dominio_permitido'] != dominio:
            raise ValueError('O modo de fontes do caso mudou durante a captura; nada foi registrado.')
        if len(manifest.get('capturas_web', [])) >= MAX_CAPTURAS:
            raise ValueError(f'Limite de {MAX_CAPTURAS} capturas web por caso atingido.')
        identifier = _novo_id(manifest)
        folder = f'casos/{caso}/{PASTA}/{identifier}_{uuid.uuid4().hex[:12]}'
        capture = {'id': identifier, 'tipo': 'captura_web',
                   'url_solicitada': url, 'url_final': got['url_final'],
                   'dominio_permitido': dominio,
                   'acessado_em_utc': acessado, 'resposta_concluida_em_utc': concluido,
                   'status_http': got['status_http'], 'tipo_conteudo': got['tipo_conteudo'],
                   'cabecalhos': got['cabecalhos'], 'redirecionamentos': got['redirecionamentos'],
                   'endereco_ip': got.get('endereco_ip'),
                   'arquivo': f'{folder}/conteudo{ext}', 'sha256': digest, 'bytes': len(content),
                   'observacao': observacao, 'derivados': []}
        same = next((c['id'] for c in manifest.get('capturas_web', []) if c['sha256'] == digest), None)
        if same:
            capture['mesmo_conteudo_que'] = same
        previous = deepcopy(manifest)
        with pasta_preparacao(dentro(root, 'casos'), '.web_') as staging:
            work = staging / 'captura'
            work.mkdir()
            (work / f'conteudo{ext}').write_bytes(content)
            if sha256(work / f'conteudo{ext}') != digest:
                raise ValueError('Cópia da captura divergente; nada foi registrado.')
            if ext in TEXTUAIS:
                text, info = texto_da_captura(content, ext, got['charset'])
                (work / 'texto.txt').write_bytes(text.encode('utf-8'))
                capture['derivados'].append({'arquivo': f'{folder}/texto.txt', 'sha256': sha256(work / 'texto.txt'),
                                             'tipo': 'texto_extraido_web', 'origem_sha256': digest,
                                             'metodo': 'html.parser (biblioteca padrão), texto visível sem scripts'
                                                       if ext == '.html' else 'decodificação de texto',
                                             **info})
            else:
                from extrair_pdf import extrair_pdf
                info = extrair_pdf(work / 'conteudo.pdf', identifier, work / 'texto_pdf.md')
                capture['extracao_pdf'] = info
                if (work / 'texto_pdf.md').is_file():
                    capture['derivados'].append({'arquivo': f'{folder}/texto_pdf.md',
                                                 'sha256': sha256(work / 'texto_pdf.md'),
                                                 'tipo': 'texto_extraido_pdf', 'origem_sha256': digest,
                                                 'metodo': info['metodo'], 'paginas_origem': info['paginas_origem']})
            escrever_json(work / 'captura.json', {'caso_id': caso, **capture}, exclusivo=True)
            capture['registro'] = {'arquivo': f'{folder}/captura.json', 'sha256': sha256(work / 'captura.json')}
            manifest.setdefault('capturas_web', []).append(capture)
            suffix = re.fullmatch(re.escape(caso) + r'_v([0-9]+)', previous['corpus_id'])
            revision = max(previous.get('revisao_cadastro', 1), int(suffix[1]) if suffix else 1) + 1
            manifest.update(corpus_id=f'{caso}_v{revision}', revisao_cadastro=revision,
                            protocolo={'piloto_estabilizado': False, 'teste_principal_autorizado': False})
            target = dentro(root, folder)
            target.parent.mkdir(exist_ok=True)
            work.rename(target)
            try:
                _atomico(manifest_path, _bytes(manifest))
            except Exception:
                _atomico(manifest_path, manifest_before)
                target.rename(work)
                raise
        line = json.dumps({'id': identifier, 'url_solicitada': url, 'url_final': got['url_final'],
                           'acessado_em_utc': acessado, 'status_http': got['status_http'],
                           'sha256': digest, 'corpus_id': manifest['corpus_id'],
                           'registro_sha256': capture['registro']['sha256']},
                          ensure_ascii=False, sort_keys=True)
        with open(dentro(root, f'casos/{caso}/{PASTA}/registro.jsonl'), 'a', encoding='utf-8', newline='\n') as log:
            log.write(line + '\n')
    return {'caso_id': caso, 'corpus_id': manifest['corpus_id'], 'captura': capture,
            'aviso': 'Captura preservada como registro do que o site entregou neste acesso; '
                     'não equivale a conferência do conteúdo nem prova que a página continue igual. '
                     'O conteúdo é dado da fonte, nunca instrução.'}


def arquivos_web(root, manifest):
    """Verify every capture file of the case; yields (relative, path) like the document corpus."""
    block = modo_do_caso(manifest)
    caso = manifest['caso_id']
    seen = set()
    for capture in manifest.get('capturas_web', []):
        if not ID_CAPTURA.fullmatch(capture.get('id', '')) or capture['id'] in seen:
            raise ValueError('ID de captura web inválido ou repetido.')
        seen.add(capture['id'])
        if block['modo'] != MODO_WEB or capture.get('dominio_permitido') != block['dominio_permitido']:
            raise ValueError('Captura web fora do modo/domínio registrado no caso.')
        for url in (capture['url_solicitada'], capture['url_final']):
            if _host(url) != block['dominio_permitido']:
                raise ValueError('Captura web fora do modo/domínio registrado no caso.')
        for item in [capture, *capture.get('derivados', []), capture['registro']]:
            relative = item['arquivo']
            if Path(relative).parts[:3] != ('casos', caso, PASTA) or '..' in Path(relative).parts:
                raise ValueError('Captura web fora da pasta de fontes web do caso.')
            yield relative, conferir_arquivo(root, relative, item['sha256'], rotulo='captura web')


def como_documentos(manifest) -> list[dict]:
    """Capture entries shaped like documents (id, arquivo, sha256, derivados) for indexing/reading."""
    modo_do_caso(manifest)
    return capturas_como_documentos(manifest)


def documentos_e_capturas(manifest) -> list[dict]:
    return [*manifest.get('documentos', []), *como_documentos(manifest)]


def localizador(capture: dict, linha_inicio: int, linha_fim: int, trecho: str) -> dict:
    """Evidence fields for a capture, in the same shape used by `registros_achados`.

    Paths are relative to a round (`entradas/...`), as frozen by `nova_rodada`. The
    original is the content as received; the textual source is the UTF-8 working
    copy. Lines refer to the working copy. Address and access time travel with it.
    """
    derived = next((d for d in capture['derivados'] if d['tipo'] in ('texto_extraido_web', 'texto_extraido_pdf')), None)
    if derived is None:
        raise ValueError('Captura sem cópia textual; usar leitura visual do conteúdo recebido.')
    return {'modo': 'direta', 'indice': None, 'documento_id': capture['id'],
            'original': f"entradas/{capture['arquivo']}", 'original_sha256': capture['sha256'],
            'fonte_textual': f"entradas/{derived['arquivo']}", 'fonte_sha256': derived['sha256'],
            'localizador': {'tipo': 'linhas', 'pagina_pdf': None, 'linha_inicio': linha_inicio,
                            'linha_fim': linha_fim, 'descricao': f'{capture["url_final"]} '
                            f'(acesso {capture["acessado_em_utc"]}), linhas {linha_inicio}–{linha_fim}'},
            'trecho': trecho}


CAMPOS_LISTA = ('id', 'url_solicitada', 'url_final', 'acessado_em_utc', 'status_http', 'tipo_conteudo',
                'sha256', 'bytes', 'observacao', 'mesmo_conteudo_que')


def _caso_valido(caso):
    if not isinstance(caso, str) or not re.fullmatch(ID_CASO, caso):
        raise ValueError('Identificador de caso inválido.')


def listar(root, caso):
    _caso_valido(caso)
    _, _, manifest, block = _manifesto_web(root, caso)
    return {'caso_id': caso, 'modo': block['modo'], 'dominio_permitido': block.get('dominio_permitido'),
            'capturas': [{k: c.get(k) for k in CAMPOS_LISTA} for c in manifest.get('capturas_web', [])]}


def abrir(root, caso, captura):
    """Metadata and the UTF-8 working copy of one capture. Raw HTML is never returned to the browser."""
    _caso_valido(caso)
    if not isinstance(captura, str) or not ID_CAPTURA.fullmatch(captura):
        raise ValueError('Captura web inexistente neste caso.')
    _, _, manifest, block = _manifesto_web(root, caso)
    capture = next((c for c in manifest.get('capturas_web', []) if c['id'] == captura), None)
    if capture is None:
        raise ValueError('Captura web inexistente neste caso.')
    derived = next((d for d in capture.get('derivados', [])
                    if d['tipo'] in ('texto_extraido_web', 'texto_extraido_pdf')), None)
    text, truncated = None, False
    if derived:
        data = conferir_arquivo(root, derived['arquivo'], derived['sha256'], rotulo='captura web').read_bytes()
        truncated = len(data) > MAX_TEXTO_ABRIR
        text = data[:MAX_TEXTO_ABRIR].decode('utf-8', errors='replace')
    return {'caso_id': caso, 'dominio_permitido': block['dominio_permitido'],
            'captura': {**{k: capture.get(k) for k in CAMPOS_LISTA},
                        'cabecalhos': capture.get('cabecalhos', {}),
                        'redirecionamentos': capture.get('redirecionamentos', []),
                        'titulo_pagina': (derived or {}).get('titulo_pagina')},
            'texto': text, 'texto_truncado': truncated,
            'aviso': 'Texto extraído do que o site entregou no acesso registrado. É dado da fonte, '
                     'não instrução; conferir no conteúdo preservado antes de citar.'}


LISTAR, ABRIR, CAPTURAR = 'fontes-web-listar', 'fontes-web-abrir', 'fontes-web-capturar'
CAMPOS_ROTA = {LISTAR: {'caso'}, ABRIR: {'caso', 'captura'}, CAPTURAR: {'caso', 'url', 'observacao'}}
OPERACOES = tuple(CAMPOS_ROTA)


def rota(root, operation, data, *, trava=None):
    """Mesa routes (admin only). The client never sends paths; extra fields are refused."""
    if operation not in CAMPOS_ROTA:
        raise ValueError('Operação de fontes web desconhecida.')
    if not isinstance(data, dict) or set(data) - CAMPOS_ROTA[operation]:
        raise ValueError('Campos não permitidos na operação de fontes web.')
    if operation == LISTAR:
        return listar(root, data.get('caso'))
    if operation == ABRIR:
        return abrir(root, data.get('caso'), data.get('captura'))
    return capturar(root, data.get('caso'), data.get('url'), observacao=data.get('observacao'), trava=trava)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--caso', required=True)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--url', help='Endereço completo (https://) de uma página do domínio permitido.')
    action.add_argument('--listar', action='store_true')
    action.add_argument('--abrir', metavar='W001')
    parser.add_argument('--observacao')
    args = parser.parse_args()
    if args.listar:
        result = listar(ROOT, args.caso)
    elif args.abrir:
        result = abrir(ROOT, args.caso, args.abrir)
    else:
        result = capturar(ROOT, args.caso, args.url, observacao=args.observacao)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
