"""Web sources for cases created in the "documentos + web" mode. No model calls.

The mode is chosen once, when the journalist creates the case, and is stored in
the case manifest (`fontes_web`). Without it, nothing here touches the network.
With it, only the single host registered in the manifest is fetched; redirects
or URLs to any other host are refused before any byte is stored. Each capture
records the full requested and final address, the UTC access time, the content
received and its SHA-256, in `casos/<caso>/web/`, separate from the originals.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import ipaddress
import json
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

from comum import ROOT, conferir_arquivo, dentro, escrever_json, ler_json, sha256, pasta_preparacao

MODO_DOCUMENTAL = 'somente_documentos'
MODO_WEB = 'documentos_e_web'
MODOS = (MODO_DOCUMENTAL, MODO_WEB)
ID_CASO = r'[a-z0-9][a-z0-9_-]{0,63}'
ID_CAPTURA = re.compile(r'W[0-9]{3,6}')
ROTULO = re.compile(r'(?!-)[a-z0-9-]{1,63}(?<!-)')
MAX_BYTES = 20 * 1024 * 1024
MAX_REDIRECIONAMENTOS = 5
MAX_CAPTURAS = 200
TEMPO_LIMITE = 30
USER_AGENT = 'Vlado-apuracao/1.0 (captura documental)'
EXTENSOES = {'text/html': '.html', 'application/xhtml+xml': '.html', 'text/plain': '.txt',
             'application/json': '.json', 'text/csv': '.csv', 'application/pdf': '.pdf',
             'application/xml': '.xml', 'text/xml': '.xml'}
TEXTUAIS = {'.html', '.txt', '.json', '.csv', '.xml'}


class DominioRecusado(ValueError):
    """The address (or a redirect) leaves the single domain registered for the case."""


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
        raise ValueError('Modo de fontes desconhecido: use somente_documentos ou documentos_e_web.')
    if modo == MODO_DOCUMENTAL:
        if dominio:
            raise ValueError('Domínio web só pode ser informado no modo documentos_e_web.')
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
    """Return the URL unchanged if it is http(s) on exactly the permitted host."""
    if not isinstance(url, str) or not url.strip() or len(url) > 4096:
        raise ValueError('Informe o endereço completo da página (http:// ou https://).')
    url = url.strip()
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ('http', 'https') or not parts.hostname:
        raise ValueError('Endereço deve começar com http:// ou https://.')
    if parts.username or parts.password:
        raise ValueError('Endereço com usuário ou senha não é aceito.')
    host = _host(url)
    if host != dominio:
        raise DominioRecusado(f'Domínio recusado: {host or "(vazio)"}. Este caso só permite {dominio}.')
    return url


class _Redirecionamentos(urllib.request.HTTPRedirectHandler):
    """Check every hop against the permitted host before following it."""

    def __init__(self, dominio, cadeia):
        self.dominio, self.cadeia = dominio, cadeia

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        newurl = urllib.parse.urljoin(req.full_url, newurl)
        if len(self.cadeia) >= MAX_REDIRECIONAMENTOS:
            raise ValueError('Redirecionamentos demais; captura não realizada.')
        conferir_url(newurl, self.dominio)
        self.cadeia.append({'de': req.full_url, 'para': newurl, 'status_http': code})
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _baixar(url, dominio):
    cadeia = []
    handlers = [_Redirecionamentos(dominio, cadeia)]
    host = _host(url)
    try:
        loopback = host == 'localhost' or ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = False
    if loopback:
        handlers.append(urllib.request.ProxyHandler({}))  # never send local addresses to a proxy
    opener = urllib.request.build_opener(*handlers)
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept': '*/*'})
    try:
        response = opener.open(request, timeout=TEMPO_LIMITE)
    except urllib.error.HTTPError as exc:
        raise ValueError(f'O site respondeu {exc.code}; captura não realizada.') from exc
    except (urllib.error.URLError, OSError) as exc:
        reason = getattr(exc, 'reason', exc)
        if isinstance(reason, ValueError):
            raise reason
        raise ValueError(f'Não foi possível acessar o endereço: {reason}') from exc
    with response:
        final = response.geturl()
        conferir_url(final, dominio)
        content = response.read(MAX_BYTES + 1)
        if len(content) > MAX_BYTES:
            raise ValueError('Página excede 20 MB; captura não realizada.')
        headers = {k.lower(): v for k, v in response.headers.items()
                   if k.lower() in ('content-type', 'last-modified', 'etag', 'date', 'content-language')}
        return {'url_final': final, 'status_http': response.status, 'cabecalhos': headers,
                'redirecionamentos': cadeia, 'conteudo': content,
                'tipo_conteudo': response.headers.get_content_type(),
                'charset': response.headers.get_content_charset()}


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
            self.titulo = (self.titulo or '') + data.strip()
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


def capturar(root, caso, url, *, observacao=None, _baixar_fn=None):
    """Fetch one page of the case's permitted domain and publish it as a new capture."""
    from cadastrar_documentos import _atomico, _bytes, _trava
    from lixeira import conferir_disponivel
    if not isinstance(caso, str) or not re.fullmatch(ID_CASO, caso):
        raise ValueError('Identificador de caso inválido.')
    if observacao is not None and (not isinstance(observacao, str) or len(observacao) > 500):
        raise ValueError('Observação da captura: texto de até 500 caracteres.')
    with _trava(root):
        conferir_disponivel(root, caso)
        manifest_path = dentro(root, f'casos/{caso}/manifesto.json')
        manifest_before = manifest_path.read_bytes()
        manifest = ler_json(manifest_path)
        if manifest.get('caso_id') != caso:
            raise ValueError('Manifesto pertence a outro caso.')
        block = modo_do_caso(manifest)
        if block['modo'] != MODO_WEB:
            raise ValueError('Este caso foi criado como apuração somente documental; '
                             'fontes web não são permitidas. O modo só é escolhido na criação.')
        list(arquivos_web(root, manifest))
        if len(manifest.get('capturas_web', [])) >= MAX_CAPTURAS:
            raise ValueError(f'Limite de {MAX_CAPTURAS} capturas web por caso atingido.')
        dominio = block['dominio_permitido']
        url = conferir_url(url, dominio)
        acessado = datetime.now(timezone.utc).isoformat()
        got = (_baixar_fn or _baixar)(url, dominio)
        concluido = datetime.now(timezone.utc).isoformat()
        identifier = _novo_id(manifest)
        folder = f'casos/{caso}/web/{identifier}_{uuid.uuid4().hex[:12]}'
        ext = EXTENSOES.get(got['tipo_conteudo'], '.bin')
        content = got['conteudo']
        digest = hashlib.sha256(content).hexdigest()
        capture = {'id': identifier, 'tipo': 'captura_web',
                   'url_solicitada': url, 'url_final': got['url_final'],
                   'dominio_permitido': dominio,
                   'acessado_em_utc': acessado, 'resposta_concluida_em_utc': concluido,
                   'status_http': got['status_http'], 'tipo_conteudo': got['tipo_conteudo'],
                   'cabecalhos': got['cabecalhos'], 'redirecionamentos': got['redirecionamentos'],
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
            elif ext == '.pdf':
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
    return {'caso_id': caso, 'corpus_id': manifest['corpus_id'], 'captura': capture,
            'aviso': 'Captura preservada como registro do que o site entregou neste acesso; '
                     'não equivale a conferência do conteúdo nem prova que a página continue igual.'}


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
            conferir_url(url, block['dominio_permitido'])
        for item in [capture, *capture.get('derivados', []), capture['registro']]:
            relative = item['arquivo']
            if Path(relative).parts[:3] != ('casos', caso, 'web'):
                raise ValueError('Captura web fora da pasta web do caso.')
            yield relative, conferir_arquivo(root, relative, item['sha256'], rotulo='captura web')


def como_documentos(manifest) -> list[dict]:
    """Capture entries shaped like documents (id, arquivo, sha256, derivados) for indexing/reading."""
    modo_do_caso(manifest)
    return [{'id': c['id'], 'arquivo': c['arquivo'], 'sha256': c['sha256'],
             'nome_recebido': c['url_final'], 'tipo_fonte': 'captura_web',
             'origem_informada': {'url_solicitada': c['url_solicitada'], 'url_final': c['url_final'],
                                  'acessado_em_utc': c['acessado_em_utc']},
             'derivados': c.get('derivados', [])} for c in manifest.get('capturas_web', [])]


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


def listar(root, caso):
    if not isinstance(caso, str) or not re.fullmatch(ID_CASO, caso):
        raise ValueError('Identificador de caso inválido.')
    from lixeira import conferir_disponivel
    conferir_disponivel(root, caso)
    manifest = ler_json(dentro(root, f'casos/{caso}/manifesto.json'))
    if manifest.get('caso_id') != caso:
        raise ValueError('Manifesto pertence a outro caso.')
    block = modo_do_caso(manifest)
    list(arquivos_web(root, manifest))
    return {'caso_id': caso, 'modo': block['modo'], 'dominio_permitido': block.get('dominio_permitido'),
            'capturas': [{k: c.get(k) for k in ('id', 'url_solicitada', 'url_final', 'acessado_em_utc',
                                                'status_http', 'tipo_conteudo', 'sha256', 'bytes', 'arquivo',
                                                'observacao', 'mesmo_conteudo_que')}
                         for c in manifest.get('capturas_web', [])]}


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--caso', required=True)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--url', help='Endereço completo de uma página do domínio permitido.')
    action.add_argument('--listar', action='store_true')
    parser.add_argument('--observacao')
    args = parser.parse_args()
    result = (listar(ROOT, args.caso) if args.listar
              else capturar(ROOT, args.caso, args.url, observacao=args.observacao))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
