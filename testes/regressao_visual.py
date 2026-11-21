"""Regressão visual da Mesa (Onda 3, parte A): rede de segurança antes de qualquer mudança de tela.

    python testes/regressao_visual.py gerar     # refaz a linha de base em testes/referencias_visuais/<plataforma>/
    python testes/regressao_visual.py comparar  # captura de novo e compara com a linha de base; relatório em tmp/

Captura 11 telas (inicio, documentos, cadastro, codex, achados, apuracao, diligencias, quadros, gerenciar,
caderno, configuracoes) em 375, 768, 1024 e 1440 px, nos temas claro e escuro, e a tela de entrar. Só
dados sintéticos: uma pasta temporária semeada por `vlado_lancador.preparar_dados` + `semear_ambiente.semear`
(casos vila_serena_sintetico e campo_verde_aditivo_sintetico), que nunca é a do projeto. O servidor sobe
em 127.0.0.1 (o servidor recusa `localhost`) e todo pedido a outro endereço é abortado e reprova a rodada.

Dois Pythons: este script precisa de Playwright e Pillow (`testes/requirements-teste.txt`, fora da imagem); o
servidor e o semeador rodam no Python do projeto (`.venv`, ou --python-servidor, ou VLADO_PYTHON_SERVIDOR).

Determinismo: relógio do navegador fixo, fuso UTC, idioma pt-BR, movimento reduzido, animações e
transições concluídas pelo Playwright (`animations='disabled'`; a CSP da Mesa não deixa injetar CSS), cursor de texto invisível, fontes só as da Mesa (esperadas por `document.fonts.ready`),
barras de rolagem ocultas, suavização de fonte sem subpixel, dimensão fixa por largura e dados da mesma
semente. Texto que o servidor grava com a hora real (`MASCARAS`) é trocado por um marcador antes da
captura; nada além disso é mascarado. Cada captura só vale depois de dar o mesmo resultado em duas
leituras seguidas; se não estabilizar, a rodada falha (captura não determinística nunca entra).
"""
from __future__ import annotations

import argparse
import contextlib
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
sys.path.insert(0, str(AQUI))
import regressao_visual_comparador as comparador  # noqa: E402

REFERENCIAS = AQUI / 'referencias_visuais'
TELAS = ('inicio', 'documentos', 'cadastro', 'codex', 'achados', 'apuracao', 'diligencias', 'quadros',
         'gerenciar', 'caderno', 'configuracoes')
TELA_ENTRAR = 'entrar'
# Foco de teclado: pressiona Tab até o alvo ficar focado e captura com o anel de foco visível.
# nome -> (tela de base, seletor do alvo, larguras em que o alvo é alcançável por Tab).
FOCOS = {'foco_entrar_campo': ('entrar', '#entrar-login', (375, 1440)),
         'foco_entrar_botao': ('entrar', '#entrar-enviar', (375, 1440)),
         'foco_mesa_botao': ('cadastro', '#enviar-documentos', (375, 1440)),
         'foco_mesa_campo': ('cadastro', '#cadastro-natureza', (375, 1440)),
         'foco_mesa_barra': ('cadastro', '#ver-cadastro', (1440,))}   # a barra lateral só existe em tela larga
TODAS = TELAS + (TELA_ENTRAR,) + tuple(FOCOS)
CASO = 'vila_serena_sintetico'
VIEWPORTS = {375: 812, 768: 1024, 1024: 768, 1440: 900}   # largura -> altura
TEMAS = {'claro': 'light', 'escuro': 'dark'}
RELOGIO = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
CHAVE_TEMA, CHAVE_IDIOMA = 'apuracao:tema', 'vlado-idioma'   # localStorage, como em desktop.js e i18n.js
ARGS_CHROMIUM = ['--lang=en-US', '--force-color-profile=srgb', '--font-render-hinting=none', '--disable-lcd-text',
                 '--disable-font-subpixel-positioning', '--hide-scrollbars', '--disable-gpu']
# Texto gravado pelo servidor com a hora real (varia a cada semeadura); trocado por um marcador na DOM.
# Cada entrada é um padrão de regex; o que casa vira '‹data›'. Nada mais é mascarado.
MASCARAS = (r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?',    # ISO 8601
            r'\d{2}/\d{2}/\d{4}(?:,?\s+\d{2}:\d{2}(?::\d{2})?)?',                       # toLocale(Date)String('pt-BR')
            r'(?<=às )\d{2}:\d{2}(?::\d{2})?')                                           # "Salvo às 17:02"
ESPERA_ESTAVEL_MAX = 10


def nome_captura(tela: str, largura: int, tema: str) -> str:
    return f'{tela}__{largura}__{tema}'


def larguras_da_tela(tela, larguras):
    return [w for w in larguras if tela not in FOCOS or w in FOCOS[tela][2]]


def nomes_esperados(telas, larguras, temas) -> list:
    return [nome_captura(t, w, k) for t in telas for w in larguras_da_tela(t, larguras) for k in temas]


def plataforma() -> str:
    return {'win32': 'windows', 'darwin': 'macos'}.get(sys.platform, 'linux')


def pasta_referencia() -> Path:
    return REFERENCIAS / plataforma()


def python_do_servidor(escolhido: str | None) -> str:
    if escolhido:
        return escolhido
    if os.environ.get('VLADO_PYTHON_SERVIDOR'):
        return os.environ['VLADO_PYTHON_SERVIDOR']
    for candidato in (RAIZ / '.venv/Scripts/python.exe', RAIZ / '.venv/bin/python'):
        if candidato.is_file():
            return str(candidato)
    return sys.executable


def porta_livre() -> int:
    with contextlib.closing(socket.socket()) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def encerrar(processo: subprocess.Popen) -> None:
    """No Windows o python do venv é um lançador: sem `/T` o servidor-filho continuaria de pé."""
    if processo.poll() is not None:
        return
    if os.name == 'nt':
        subprocess.run(['taskkill', '/F', '/T', '/PID', str(processo.pid)], capture_output=True)
    else:
        processo.terminate()
    with contextlib.suppress(Exception):
        processo.wait(timeout=15)


def ambiente_do_projeto() -> dict:
    """Ambiente do semeador e dos servidores: sem chave de API (a Mesa mostra "chave ausente" e nunca chama um
    provedor) e sem OCR (VLADO_OCR=0), para a linha de base não depender do que há instalado na máquina."""
    env = {k: v for k, v in os.environ.items() if k not in ('ANTHROPIC_API_KEY', 'OPENAI_API_KEY')}
    env.update(PYTHONUTF8='1', PYTHONIOENCODING='utf-8', VLADO_OCR='0')
    return env


class Servidores:
    """Pasta de dados sintética + um servidor `local` (Mesa) e um `local-contas` (tela de entrar)."""

    def __init__(self, python: str):
        self.python = python
        self.tmp = Path(tempfile.mkdtemp(prefix='vlado_visual_'))
        self.dados = self.tmp / 'dados'
        self.processos = []
        self.origem_mesa = self.origem_entrar = ''

    def __enter__(self):
        try:
            self._semear()
            self._subir()
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *exc):
        for p in self.processos:
            encerrar(p)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _semear(self) -> None:
        r = subprocess.run([self.python, str(AQUI / 'regressao_visual_semear.py'), str(self.dados)], env=ambiente_do_projeto(),
                           capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=600)
        if r.returncode:
            raise SystemExit('Falha ao semear os dados sintéticos:\n' + (r.stdout + r.stderr)[-2000:])

    def _subir(self) -> None:
        env = ambiente_do_projeto()
        for modo, atributo in (('local', 'origem_mesa'), ('local-contas', 'origem_entrar')):
            porta = porta_livre()
            log = open(self.tmp / f'servidor-{modo}.log', 'wb')
            self.processos.append(subprocess.Popen(
                [self.python, str(RAIZ / 'scripts/interface_pesquisa.py'), '--modo', modo, '--porta', str(porta),
                 '--sem-abrir', '--dados', str(self.dados)], cwd=RAIZ, env=env, stdout=log, stderr=subprocess.STDOUT))
            setattr(self, atributo, f'http://127.0.0.1:{porta}')
        limite = time.monotonic() + 240
        for origem, processo in zip((self.origem_mesa, self.origem_entrar), self.processos):
            while True:
                if processo.poll() is not None:
                    raise SystemExit(f'O servidor de {origem} encerrou ao subir (veja {self.tmp}).')
                try:
                    with urllib.request.urlopen(origem + '/saude', timeout=3) as resposta:
                        if resposta.status == 200:
                            break
                except OSError:
                    pass
                if time.monotonic() > limite:
                    raise SystemExit(f'O servidor de {origem} não respondeu em 240 s.')
                time.sleep(0.5)


JS_MASCARAR = """(padroes) => {
  const regs = padroes.map(p => new RegExp(p, 'g'));
  const raiz = document.body;
  const it = document.createTreeWalker(raiz, NodeFilter.SHOW_TEXT);
  let n = 0;
  for (let no = it.nextNode(); no; no = it.nextNode()) {
    const antes = no.nodeValue; let depois = antes;
    for (const r of regs) depois = depois.replace(r, '‹data›');
    if (depois !== antes) { no.nodeValue = depois; n++; }
  }
  for (const el of raiz.querySelectorAll('[value],[title],[placeholder]')) {
    for (const a of ['title', 'placeholder']) {
      const v = el.getAttribute(a); if (!v) continue;
      let w = v; for (const r of regs) w = w.replace(r, '‹data›');
      if (w !== v) { el.setAttribute(a, w); n++; }
    }
  }
  return n;
}"""


def capturar(servidores: Servidores, saida: Path, telas, larguras, temas, aviso=print) -> dict:
    """Captura tudo em `saida` e devolve o manifesto. Qualquer instabilidade levanta SystemExit."""
    from playwright.sync_api import sync_playwright
    saida.mkdir(parents=True, exist_ok=True)
    problemas, externos, mascaradas, avisos_navegador = [], [], {}, {}
    metadados = {}
    with sync_playwright() as pw:
        navegador = pw.chromium.launch(args=ARGS_CHROMIUM)
        metadados['navegador'] = 'chromium ' + navegador.version
        for largura in larguras:
            for tema in temas:
                contexto = navegador.new_context(
                    viewport={'width': largura, 'height': VIEWPORTS[largura]}, device_scale_factor=1,
                    locale='pt-BR', timezone_id='UTC', color_scheme=TEMAS[tema], reduced_motion='reduce',
                    service_workers='block', accept_downloads=False)
                contexto.clock.set_fixed_time(RELOGIO)
                contexto.add_init_script(
                    f"try{{localStorage.setItem('{CHAVE_TEMA}','{TEMAS[tema]}');localStorage.setItem('{CHAVE_IDIOMA}','pt');}}catch(e){{}}")
                permitidos = (servidores.origem_mesa, servidores.origem_entrar)

                def filtrar(rota):
                    url = rota.request.url
                    if url.startswith(permitidos) or url.startswith(('data:', 'blob:', 'about:')):
                        rota.continue_()
                    else:
                        externos.append(url)
                        rota.abort()
                contexto.route('**/*', filtrar)
                for tela in telas:
                    if largura not in larguras_da_tela(tela, [largura]):
                        continue
                    nome = nome_captura(tela, largura, tema)
                    pagina = contexto.new_page()
                    erros = []
                    pagina.on('pageerror', lambda e, erros=erros: erros.append('pageerror: ' + str(e)))
                    pagina.on('console', lambda m, erros=erros: erros.append('console.error: ' + m.text) if m.type == 'error' else None)
                    try:
                        url, seletor = destino(servidores, FOCOS[tela][0] if tela in FOCOS else tela)
                        pagina.goto(url, wait_until='load')
                        pagina.wait_for_selector(seletor, state='visible', timeout=30000)
                        with contextlib.suppress(Exception):
                            pagina.wait_for_load_state('networkidle', timeout=3000)   # a área codex mantém um pedido aberto
                        pagina.evaluate('document.fonts.ready.then(() => 0)')
                        # A tela esperada precisa ser a que aparece (nunca uma página de erro que sai igual para sempre).
                        base = FOCOS[tela][0] if tela in FOCOS else tela
                        if base != TELA_ENTRAR:
                            ativa = pagina.evaluate("new URL(location.href).searchParams.get('area') || 'inicio'")
                            if ativa != base:
                                problemas.append(f'{nome}: a Mesa abriu a área {ativa!r}, não {base!r}')
                        mascaradas[nome] = pagina.evaluate(JS_MASCARAR, list(MASCARAS))
                        pagina.evaluate('window.scrollTo(0, 0)')
                        pagina.mouse.move(0, 0)
                        if tela in FOCOS:
                            alvo = FOCOS[tela][1]
                            if not focar_com_tab(pagina, alvo):
                                problemas.append(f'{nome}: o foco de teclado (Tab) não chegou a {alvo}')
                        else:
                            pagina.evaluate("document.activeElement && document.activeElement.blur && document.activeElement.blur()")
                        png = estavel(pagina)
                        if png is not None and tela in FOCOS and not foco_pintado(pagina, FOCOS[tela][1]):
                            # O foco se perdeu durante a captura (a página mexeu depois do Tab): refaz o foco e a captura.
                            png = None
                            if focar_com_tab(pagina, FOCOS[tela][1]):
                                png = estavel(pagina)
                                if png is not None and not foco_pintado(pagina, FOCOS[tela][1]):
                                    png = None
                        if png is None:
                            problemas.append(f'{nome}: não estabilizou em {ESPERA_ESTAVEL_MAX} leituras (captura não determinística)')
                        else:
                            (saida / f'{nome}.png').write_bytes(png)
                    except Exception as exc:   # noqa: BLE001 - qualquer falha de captura reprova a rodada
                        problemas.append(f'{nome}: {type(exc).__name__}: {str(exc)[:300]}')
                    finally:
                        # A CSP da Mesa (style-src 'self') proíbe injetar CSS: animações saem por `animations='disabled'`.
                        # Na tela de entrar, o 401 de /api/sessao sem sessão é esperado.
                        erros = [e for e in erros if 'favicon' not in e.lower()
                                 and not (tela == TELA_ENTRAR and 'status of 401' in e)]
                        if erros:   # estado atual da Mesa: registra no manifesto, não reprova (ver `comparar`)
                            avisos_navegador[nome] = sorted({normalizar_erro(e) for e in erros})
                        pagina.close()
                    aviso(f'  {nome}')
                contexto.close()
        navegador.close()
    if externos:
        problemas.append('pedidos a endereços externos (abortados): ' + ', '.join(sorted(set(externos))[:5]))
    if problemas:
        raise SystemExit('Rodada reprovada, nada foi gravado como referência:\n - ' + '\n - '.join(problemas))
    import playwright
    return {'navegador': metadados['navegador'], 'playwright': getattr(playwright, '__version__', '?'),
            'plataforma': plataforma(), 'python': platform.python_version(),
            'relogio_fixo_utc': RELOGIO.isoformat(), 'viewports': {str(k): v for k, v in VIEWPORTS.items()},
            'argumentos_chromium': ARGS_CHROMIUM, 'mascaras': list(MASCARAS),
            'erros_do_navegador': avisos_navegador}


def normalizar_erro(texto: str) -> str:
    """Tira hashes e números que variam entre execuções, para comparar mensagens de erro."""
    return re.sub(r'(sha256|nonce)-[A-Za-z0-9+/=_-]+', r'-…', texto)[:400]


def destino(servidores: Servidores, tela: str):
    if tela == TELA_ENTRAR:
        return servidores.origem_entrar + '/entrar', '#entrar-secao:not([hidden])'
    seletor = '#area-documentos' if tela == 'documentos' else f'#area-{tela}'
    return f'{servidores.origem_mesa}/?area={tela}&caso={CASO}', seletor


JS_FOCO_PINTADO = """([s]) => {
  const e = document.activeElement;
  if (!e || !e.matches(s) || !e.matches(':focus-visible')) return null;
  const c = getComputedStyle(e);
  if (c.outlineStyle === 'none' || !(parseFloat(c.outlineWidth) > 0) || c.outlineColor === 'rgba(0, 0, 0, 0)') return null;
  const r = e.getBoundingClientRect();
  return [r.x, r.y, r.width, r.height].map(v => Math.round(v * 100) / 100).join(',');
}"""
JS_DOIS_QUADROS = "new Promise(ok => requestAnimationFrame(() => requestAnimationFrame(ok)))"


def foco_pintado(pagina, seletor: str):
    """Retângulo do alvo se ele tem o foco, `:focus-visible` e um contorno realmente pintado; senão None."""
    return pagina.evaluate(JS_FOCO_PINTADO, [seletor])


def focar_com_tab(pagina, seletor: str, maximo: int = 80) -> bool:
    """Tab a partir do início da página até o alvo ficar focado com o anel de teclado pintado e ASSENTADO:
    depois de dois quadros e uma pausa o alvo continua focado, com contorno e no mesmo lugar (a barra lateral
    e outros blocos terminam de se desenhar depois do carregamento e podem tirar o foco ou mexer o alvo)."""
    for _ in range(5):
        pagina.evaluate("document.activeElement && document.activeElement.blur && document.activeElement.blur()")
        for _ in range(maximo):
            pagina.keyboard.press('Tab')
            antes = foco_pintado(pagina, seletor)
            if antes:
                pagina.evaluate(JS_DOIS_QUADROS)
                pagina.wait_for_timeout(500)
                pagina.evaluate(JS_DOIS_QUADROS)
                if foco_pintado(pagina, seletor) == antes:
                    return True
                break
    return False


def estavel(pagina):
    """Duas leituras seguidas iguais; devolve os bytes, ou None se não estabilizar."""
    anterior = None
    for _ in range(ESPERA_ESTAVEL_MAX):
        atual = pagina.screenshot(full_page=True, animations='disabled', caret='hide')
        if atual == anterior:
            return atual
        anterior = atual
        pagina.wait_for_timeout(300)
    return None


def otimizar(origem: Path, destino_: Path) -> None:
    """PNG sem perda e sem metadados, para a referência ocupar pouco; os pixels são idênticos."""
    from PIL import Image
    with Image.open(origem) as imagem:
        imagem.convert('RGB').save(destino_, optimize=True)


def escrever_manifesto(pasta: Path, meta: dict, nomes) -> None:
    capturas = {}
    for nome in sorted(nomes):
        arquivo = pasta / f'{nome}.png'
        from PIL import Image
        with Image.open(arquivo) as imagem:
            capturas[nome] = {'largura': imagem.width, 'altura': imagem.height,
                              'bytes': arquivo.stat().st_size,
                              'sha256': hashlib.sha256(arquivo.read_bytes()).hexdigest()}
    manifesto = {**meta, 'gerado_em_utc': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                 'tolerancia': {'canal': comparador.TOLERANCIA_CANAL, 'pixels': comparador.TOLERANCIA_PIXELS},
                 'total_bytes': sum(c['bytes'] for c in capturas.values()), 'capturas': capturas}
    (pasta / 'manifesto.json').write_text(json.dumps(manifesto, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def selecao(args):
    telas = [t.strip() for t in args.telas.split(',')] if args.telas else list(TODAS)
    larguras = [int(w) for w in args.larguras.split(',')] if args.larguras else list(VIEWPORTS)
    temas = [t.strip() for t in args.temas.split(',')] if args.temas else list(TEMAS)
    invalidas = [t for t in telas if t not in TODAS] + [w for w in larguras if w not in VIEWPORTS] \
        + [t for t in temas if t not in TEMAS]
    if invalidas:
        raise SystemExit(f'Seleção inválida: {invalidas}')
    return telas, larguras, temas


def _capturas_em(pasta: Path, args):
    telas, larguras, temas = selecao(args)
    with Servidores(python_do_servidor(args.python_servidor)) as servidores:
        print(f'Capturando {len(nomes_esperados(telas, larguras, temas))} imagens...', flush=True)
        meta = capturar(servidores, pasta, telas, larguras, temas, aviso=lambda m: print(m, flush=True))
    return meta, nomes_esperados(telas, larguras, temas)


def gerar(args) -> int:
    parcial = bool(args.telas or args.larguras or args.temas)
    destino_ref = pasta_referencia()
    with tempfile.TemporaryDirectory(prefix='vlado_visual_ger_') as tmp:
        bruto = Path(tmp) / 'bruto'
        meta, nomes = _capturas_em(bruto, args)
        novo = Path(tmp) / 'novo'
        novo.mkdir()
        if parcial and destino_ref.is_dir():           # só substitui as capturas pedidas
            for antiga in destino_ref.glob('*.png'):
                shutil.copy2(antiga, novo / antiga.name)
            anterior = json.loads((destino_ref / 'manifesto.json').read_text(encoding='utf-8')).get('erros_do_navegador', {})
            meta['erros_do_navegador'] = {**{n: e for n, e in anterior.items() if n not in nomes}, **meta['erros_do_navegador']}
        for nome in nomes:
            otimizar(bruto / f'{nome}.png', novo / f'{nome}.png')
        todas = sorted(p.stem for p in novo.glob('*.png'))
        escrever_manifesto(novo, meta, todas)
        if destino_ref.exists():
            shutil.rmtree(destino_ref)
        destino_ref.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(novo, destino_ref)
    total = sum(p.stat().st_size for p in destino_ref.glob('*.png'))
    print(f'Linha de base em {destino_ref}: {len(todas)} capturas, {total / 1e6:.2f} MB.')
    return 0


def comparar(args) -> int:
    referencias = pasta_referencia()
    if not (referencias / 'manifesto.json').is_file():
        print(f'Sem linha de base para {plataforma()} em {referencias}. Rode `gerar` nesta plataforma.', file=sys.stderr)
        return 2
    manifesto = json.loads((referencias / 'manifesto.json').read_text(encoding='utf-8'))
    relatorio = Path(args.relatorio) if args.relatorio else RAIZ / 'tmp' / 'regressao_visual'
    if relatorio.exists():
        shutil.rmtree(relatorio)
    atuais = relatorio / 'atuais'
    meta, nomes = _capturas_em(atuais, args)
    parcial = bool(args.telas or args.larguras or args.temas)
    # Referências de fora da seleção não entram na comparação parcial; numa completa, a que faltar reprova.
    ref_filtradas = relatorio / 'referencias'
    ref_filtradas.mkdir()
    for nome in (nomes if parcial else sorted(manifesto['capturas'])):
        if (referencias / f'{nome}.png').is_file():
            shutil.copy2(referencias / f'{nome}.png', ref_filtradas / f'{nome}.png')
    resultados = comparador.comparar_pastas(ref_filtradas, atuais, relatorio / 'diferencas', esperados=nomes)
    pagina = comparador.escrever_relatorio(resultados, relatorio, ref_filtradas, atuais)
    r = comparador.resumo(resultados)
    novos = {n: sorted(set(e) - set(manifesto.get('erros_do_navegador', {}).get(n, [])))
             for n, e in meta['erros_do_navegador'].items()}
    for nome, erros in sorted(novos.items()):
        if erros:
            print(f'  AVISO {nome}: erro novo no navegador (não reprova): ' + ' | '.join(erros))
    if manifesto.get('navegador') != meta['navegador']:
        print(f"AVISO: navegador da linha de base {manifesto.get('navegador')} ≠ atual {meta['navegador']}; "
              'diferenças de renderização podem ser do navegador, não da tela.')
    for res in resultados:
        if not res.aprovado:
            extra = f' ({res.diferentes} px, {res.percentual:.4f}%)' if res.estado == 'diferente' else ''
            print(f'  REPROVADA {res.nome}: {res.estado}{extra}')
    print(f"{r['aprovadas']}/{r['total']} capturas dentro da tolerância (canal ≤ {comparador.TOLERANCIA_CANAL}, "
          f'≤ {comparador.TOLERANCIA_PIXELS} px). Relatório: {pagina}')
    return 0 if not r['reprovadas'] else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('comando', choices=('gerar', 'comparar'))
    parser.add_argument('--telas', help='lista separada por vírgula (padrão: todas)')
    parser.add_argument('--larguras', help='ex.: 375,1440 (padrão: 375,768,1024,1440)')
    parser.add_argument('--temas', help='claro,escuro (padrão: ambos)')
    parser.add_argument('--python-servidor', help='Python do projeto (padrão: .venv do projeto)')
    parser.add_argument('--relatorio', help='pasta do relatório de `comparar` (padrão: tmp/regressao_visual)')
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding='utf-8')
    return gerar(args) if args.comando == 'gerar' else comparar(args)


if __name__ == '__main__':
    raise SystemExit(main())
