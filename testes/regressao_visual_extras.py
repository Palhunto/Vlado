"""Capturas adicionais da regressão visual (Onda 3, R6 do Traço): celular deitado, 430 px e texto a 200%.

    python testes/regressao_visual_extras.py gerar      # refaz testes/referencias_visuais/<plataforma>_extras/
    python testes/regressao_visual_extras.py comparar   # captura de novo e compara; relatório em tmp/regressao_visual_extras/

São referências ADICIONAIS: nada aqui troca as 130 capturas de `regressao_visual.py` (375, 768, 1024 e 1440 px). As telas são as mesmas da linha de
base (as 11 áreas, as duas abas de `quadros` e `entrar`; sem os focos), nos temas claro e escuro, na mesma Mesa sintética e com o mesmo método de
determinismo (relógio fixo, fuso UTC, movimento reduzido, fontes da Mesa, duas leituras iguais, nenhum pedido a endereço externo).

Cenários (nome da captura: `<tela>__<cenário>__<tema>.png`):
  paisagem  812 x 375 px: o celular deitado (a altura curta é o que costuma quebrar cabeçalho, gaveta e diálogos).
  430       430 x 932 px: o celular grande em pé (entre os 375 da linha de base e os 768).
  zoom200   página a 200%: janela de 1280 px com a página ampliada a 200%, ou seja, 640 px de largura em CSS com fator de escala 2 (a imagem sai
            com 1280 px). É o "redimensionar texto até 200%" da WCAG 1.4.4 como o navegador o faz. A CSP da Mesa não deixa injetar CSS para ampliar só a fonte,
            e esta é a forma que a pessoa de verdade usa (Ctrl +).

Rolagem horizontal (a página mais larga que a janela) NÃO reprova a geração: entra no manifesto (`rolagem_horizontal`) e é avisada. No `comparar`, só
reprova rolagem horizontal que a referência não tinha, além das diferenças de imagem e de qualquer pedido a endereço externo.
"""
from __future__ import annotations

import argparse
import contextlib
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import regressao_visual as rv  # noqa: E402
import regressao_visual_comparador as comparador  # noqa: E402

CENARIOS = {
    'paisagem': {'viewport': {'width': 812, 'height': 375}, 'escala': 1},
    '430': {'viewport': {'width': 430, 'height': 932}, 'escala': 1},
    'zoom200': {'viewport': {'width': 640, 'height': 450}, 'escala': 2},
}
TELAS = tuple(rv.TELAS) + tuple(rv.VARIANTES) + (rv.TELA_ENTRAR,)


def nome_captura(tela: str, cenario: str, tema: str) -> str:
    return f'{tela}__{cenario}__{tema}'


def nomes_esperados(telas, cenarios, temas) -> list:
    return [nome_captura(t, c, k) for t in telas for c in cenarios for k in temas]


def pasta_extras() -> Path:
    return rv.REFERENCIAS / f'{rv.plataforma()}_extras'


def capturar(servidores, saida: Path, telas, cenarios, temas, aviso=print) -> dict:
    """Captura tudo em `saida` e devolve o manifesto. Instabilidade, tela errada e pedido externo levantam SystemExit; rolagem horizontal só é registrada."""
    from playwright.sync_api import Error as ErroPlaywright, sync_playwright
    saida.mkdir(parents=True, exist_ok=True)
    problemas, externos, rolagem, avisos_navegador = [], [], {}, {}
    metadados = {'reinicios_do_navegador': 0}
    permitidos = (servidores.origem_mesa, servidores.origem_entrar)

    def filtrar(rota):
        url = rota.request.url
        if url.startswith(permitidos) or url.startswith(('data:', 'blob:', 'about:')):
            rota.continue_()
        else:
            externos.append(url)
            rota.abort()

    def uma_tela(contexto, tela, cenario, tema):
        nome = nome_captura(tela, cenario, tema)
        pagina = contexto.new_page()
        erros = []
        atividade = rv.AtividadeDeRede(pagina)
        pagina.on('pageerror', lambda e: erros.append('pageerror: ' + str(e)))
        pagina.on('console', lambda m: erros.append('console.error: ' + m.text) if m.type == 'error' else None)
        try:
            url, seletor = rv.destino(servidores, tela)
            pagina.goto(url, wait_until='load')
            pagina.wait_for_selector(seletor, state='visible', timeout=30000)
            atividade.esperar_quieta(pagina)
            rv.esperar_pronta(pagina, atividade, nome, problemas)
            pagina.evaluate('document.fonts.ready.then(() => 0)')
            esperada = rv.VARIANTES[tela][0] if tela in rv.VARIANTES else tela
            if esperada != rv.TELA_ENTRAR:
                ativa = pagina.evaluate("new URL(location.href).searchParams.get('area') || 'inicio'")
                if ativa != esperada:
                    problemas.append(f'{nome}: a Mesa abriu a área {ativa!r}, não {esperada!r}')
            if tela in rv.VARIANTES:
                aba = pagina.get_by_role('tab', name=rv.VARIANTES[tela][1], exact=True)
                aba.click()
                if aba.get_attribute('aria-selected') != 'true':
                    problemas.append(f'{nome}: a aba {rv.VARIANTES[tela][1]!r} não ficou selecionada')
                rv.esperar_pronta(pagina, atividade, nome, problemas)
            pagina.evaluate(rv.JS_MASCARAR, list(rv.mascaras()))
            pagina.evaluate('window.scrollTo(0, 0)')
            pagina.mouse.move(0, 0)
            pagina.evaluate("document.activeElement && document.activeElement.blur && document.activeElement.blur()")
            rv.esperar_pronta(pagina, atividade, nome, problemas)
            largura_da_pagina = pagina.evaluate('document.documentElement.scrollWidth')
            largura_da_janela = pagina.evaluate('innerWidth')
            if largura_da_pagina > largura_da_janela:
                rolagem[nome] = {'pagina': largura_da_pagina, 'janela': largura_da_janela}
            png = rv.estavel(pagina)
            if png is None:
                problemas.append(f'{nome}: não estabilizou em {rv.ESPERA_ESTAVEL_MAX} leituras (captura não determinística)')
            else:
                (saida / f'{nome}.png').write_bytes(png)
        finally:
            erros = [e for e in erros if 'favicon' not in e.lower() and not (tela == rv.TELA_ENTRAR and 'status of 401' in e)]
            if erros:
                avisos_navegador[nome] = sorted({rv.normalizar_erro(e) for e in erros})
            with contextlib.suppress(ErroPlaywright):
                pagina.close()

    with sync_playwright() as pw:
        for cenario in cenarios:
            config = CENARIOS[cenario]
            for tema in temas:
                pendentes = list(telas)
                tentativas = 0
                while pendentes:
                    navegador = pw.chromium.launch(args=rv.ARGS_CHROMIUM)
                    metadados['navegador'] = 'chromium ' + navegador.version
                    try:
                        contexto = navegador.new_context(
                            viewport=config['viewport'], device_scale_factor=config['escala'], locale='pt-BR', timezone_id='UTC',
                            color_scheme=rv.TEMAS[tema], reduced_motion='reduce', service_workers='block', accept_downloads=False)
                        contexto.clock.set_fixed_time(rv.RELOGIO)
                        contexto.add_init_script(
                            f"try{{localStorage.setItem('{rv.CHAVE_TEMA}','{rv.TEMAS[tema]}');localStorage.setItem('{rv.CHAVE_IDIOMA}','pt');}}catch(e){{}}")
                        contexto.route('**/*', filtrar)
                        while pendentes:
                            tela = pendentes[0]
                            try:
                                uma_tela(contexto, tela, cenario, tema)
                            except ErroPlaywright as exc:
                                if 'closed' in str(exc).lower() and tentativas < 3:   # o navegador caiu
                                    tentativas += 1
                                    metadados['reinicios_do_navegador'] += 1
                                    aviso(f'  (Chromium caiu em {tela}; reiniciando, tentativa {tentativas})')
                                    break
                                problemas.append(f'{nome_captura(tela, cenario, tema)}: {type(exc).__name__}: {str(exc)[:300]}')
                            except Exception as exc:   # noqa: BLE001 - qualquer falha de captura reprova a rodada
                                problemas.append(f'{nome_captura(tela, cenario, tema)}: {type(exc).__name__}: {str(exc)[:300]}')
                            pendentes.pop(0)
                            aviso(f'  {nome_captura(tela, cenario, tema)}')
                    finally:
                        with contextlib.suppress(Exception):
                            navegador.close()
    if externos:
        problemas.append('pedidos a endereços externos (abortados): ' + ', '.join(sorted(set(externos))[:5]))
    if problemas:
        raise SystemExit('Rodada reprovada, nada foi gravado como referência:\n - ' + '\n - '.join(problemas))
    import playwright
    return {'navegador': metadados['navegador'], 'reinicios_do_navegador': metadados['reinicios_do_navegador'],
            'playwright': getattr(playwright, '__version__', '?'), 'plataforma': rv.plataforma(),
            'relogio_fixo_utc': rv.RELOGIO.isoformat(), 'cenarios': {k: {**v['viewport'], 'escala': v['escala']} for k, v in CENARIOS.items()},
            'argumentos_chromium': rv.ARGS_CHROMIUM, 'rolagem_horizontal': dict(sorted(rolagem.items())),
            'erros_do_navegador': avisos_navegador}


def _selecao(args):
    telas = [t.strip() for t in args.telas.split(',')] if args.telas else list(TELAS)
    cenarios = [c.strip() for c in args.cenarios.split(',')] if args.cenarios else list(CENARIOS)
    temas = [t.strip() for t in args.temas.split(',')] if args.temas else list(rv.TEMAS)
    invalidas = [t for t in telas if t not in TELAS] + [c for c in cenarios if c not in CENARIOS] + [t for t in temas if t not in rv.TEMAS]
    if invalidas:
        raise SystemExit(f'Seleção inválida: {invalidas}')
    return telas, cenarios, temas


def _capturas_em(pasta: Path, args):
    telas, cenarios, temas = _selecao(args)
    nomes = nomes_esperados(telas, cenarios, temas)
    with rv.Servidores(rv.python_do_servidor(args.python_servidor)) as servidores:
        print(f'Capturando {len(nomes)} imagens...', flush=True)
        meta = capturar(servidores, pasta, telas, cenarios, temas, aviso=lambda m: print(m, flush=True))
    return meta, nomes


def _escrever_manifesto(pasta: Path, meta: dict, nomes) -> None:
    from PIL import Image
    capturas = {}
    for nome in sorted(nomes):
        arquivo = pasta / f'{nome}.png'
        with Image.open(arquivo) as imagem:
            capturas[nome] = {'largura': imagem.width, 'altura': imagem.height, 'bytes': arquivo.stat().st_size,
                              'sha256': hashlib.sha256(arquivo.read_bytes()).hexdigest()}
    manifesto = {**meta, 'gerado_em_utc': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                 'tolerancia': {'canal': comparador.TOLERANCIA_CANAL, 'pixels': comparador.TOLERANCIA_PIXELS},
                 'total_bytes': sum(c['bytes'] for c in capturas.values()), 'capturas': capturas}
    (pasta / 'manifesto.json').write_text(json.dumps(manifesto, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def gerar(args) -> int:
    parcial = bool(args.telas or args.cenarios or args.temas)
    destino = pasta_extras()
    with tempfile.TemporaryDirectory(prefix='vlado_visual_extras_') as tmp:
        bruto = Path(tmp) / 'bruto'
        meta, nomes = _capturas_em(bruto, args)
        novo = Path(tmp) / 'novo'
        novo.mkdir()
        if parcial and destino.is_dir():
            for antiga in destino.glob('*.png'):
                shutil.copy2(antiga, novo / antiga.name)
            anterior = json.loads((destino / 'manifesto.json').read_text(encoding='utf-8')) if (destino / 'manifesto.json').is_file() else {}
            meta['rolagem_horizontal'] = {**{n: v for n, v in anterior.get('rolagem_horizontal', {}).items() if n not in nomes}, **meta['rolagem_horizontal']}
            meta['erros_do_navegador'] = {**{n: e for n, e in anterior.get('erros_do_navegador', {}).items() if n not in nomes}, **meta['erros_do_navegador']}
        for nome in nomes:
            rv.otimizar(bruto / f'{nome}.png', novo / f'{nome}.png')
        todas = sorted(p.stem for p in novo.glob('*.png'))
        _escrever_manifesto(novo, meta, todas)
        if destino.exists():
            shutil.rmtree(destino)
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(novo, destino)
    total = sum(p.stat().st_size for p in destino.glob('*.png'))
    print(f'Referências extras em {destino}: {len(todas)} capturas, {total / 1e6:.2f} MB.')
    for nome, v in sorted(meta['rolagem_horizontal'].items()):
        print(f"  AVISO rolagem horizontal em {nome}: página com {v['pagina']} px numa janela de {v['janela']} px")
    return 0


def comparar(args) -> int:
    referencias = pasta_extras()
    if not (referencias / 'manifesto.json').is_file():
        print(f'Sem referências extras para {rv.plataforma()} em {referencias}. Rode `gerar` nesta plataforma.', file=sys.stderr)
        return 2
    manifesto = json.loads((referencias / 'manifesto.json').read_text(encoding='utf-8'))
    relatorio = Path(args.relatorio) if args.relatorio else rv.RAIZ / 'tmp' / 'regressao_visual_extras'
    if relatorio.exists():
        shutil.rmtree(relatorio)
    atuais = relatorio / 'atuais'
    meta, nomes = _capturas_em(atuais, args)
    parcial = bool(args.telas or args.cenarios or args.temas)
    ref_filtradas = relatorio / 'referencias'
    ref_filtradas.mkdir()
    for nome in (nomes if parcial else sorted(manifesto['capturas'])):
        if (referencias / f'{nome}.png').is_file():
            shutil.copy2(referencias / f'{nome}.png', ref_filtradas / f'{nome}.png')
    resultados = comparador.comparar_pastas(ref_filtradas, atuais, relatorio / 'diferencas', esperados=nomes)
    pagina = comparador.escrever_relatorio(resultados, relatorio, ref_filtradas, atuais)
    r = comparador.resumo(resultados)
    novas = sorted(n for n in meta['rolagem_horizontal'] if n not in manifesto.get('rolagem_horizontal', {}))
    for nome in novas:
        v = meta['rolagem_horizontal'][nome]
        print(f"  REPROVADA {nome}: rolagem horizontal nova (página com {v['pagina']} px numa janela de {v['janela']} px)")
    for res in resultados:
        if not res.aprovado:
            extra = f' ({res.diferentes} px, {res.percentual:.4f}%)' if res.estado == 'diferente' else ''
            print(f'  REPROVADA {res.nome}: {res.estado}{extra}')
    print(f"{r['aprovadas']}/{r['total']} capturas extras dentro da tolerância; {len(novas)} rolagem(ns) horizontal(is) nova(s). Relatório: {pagina}")
    return 0 if not r['reprovadas'] and not novas else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('comando', choices=('gerar', 'comparar'))
    parser.add_argument('--telas', help='lista separada por vírgula (padrão: as 14 da linha de base, sem os focos)')
    parser.add_argument('--cenarios', help='paisagem,430,zoom200 (padrão: os três)')
    parser.add_argument('--temas', help='claro,escuro (padrão: ambos)')
    parser.add_argument('--python-servidor', help='Python do projeto (padrão: .venv do projeto)')
    parser.add_argument('--relatorio', help='pasta do relatório de `comparar` (padrão: tmp/regressao_visual_extras)')
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding='utf-8')
    return gerar(args) if args.comando == 'gerar' else comparar(args)


if __name__ == '__main__':
    raise SystemExit(main())
