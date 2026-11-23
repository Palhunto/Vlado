"""Prova da faixa que rola para o lado (Q5 da Coruja, docs/design/componentes.md#faixa-que-rola) e medida de rolagem por dentro.

A WCAG 1.4.10 (reflow) pede que a página não role em duas direções. A medida antiga olhava só a página (`documentElement.scrollWidth`); um elemento que
rola por dentro (a linha de etapas, as pílulas dos Quadros, as abas do Caderno e de Documentos) passava sem ser visto, e o item ativo podia ficar
cortado. Aqui cada elemento visível com `overflow-x` auto ou scroll é medido e julgado.

    python testes/regressao_visual_faixa.py provar   # captura Caderno, Documentos e Quadros a 320, 390 e 430 px nos dois temas e julga as faixas
    python testes/regressao_visual_faixa.py gerar    # igual, e grava as 18 capturas em testes/referencias_visuais/<plataforma>_faixa/
    python testes/regressao_visual_faixa.py comparar # captura de novo e compara com essas referências

O que reprova (função `julgar`, testável sem navegador):
  - o item ativo (aria-current, aria-selected ou aria-pressed) fora da faixa que o contém, ou fora da janela;
  - a faixa de componentes.md (`#mesa-etapas`, `.quadros-abas`, `.mesa-tabs`, `.notebook-tabs`) com `data-rola` que não bate com a posição da rolagem, ou sem
    máscara quando o atributo existe;
  - o elemento que rola por dentro e não é faixa nem tabela, com o item ativo cortado.
O que só é avisado (vai ao manifesto em `rolagem_interna`): elemento que rola por dentro e não é faixa nem tabela, mesmo com o ativo à vista (uma faixa nova
que o desktop.js ainda não conheça). Tabela de dados fica de fora: a WCAG 1.4.10 a isenta.
`troca` (Q5d, o ativo agora vem no quadro seguinte): clica em cada item das faixas de abas que rolam e confere o ativo dois quadros depois.
O custo da faixa numa conversa longa (Q5d) é medido por `regressao_visual_custo.py`.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

TELAS_FAIXA = ('caderno', 'documentos', 'quadros')
CENARIOS_FAIXA = {
    '320': {'viewport': {'width': 320, 'height': 640}, 'escala': 1},
    '390': {'viewport': {'width': 390, 'height': 844}, 'escala': 1},
    '430': {'viewport': {'width': 430, 'height': 932}, 'escala': 1},
}
# As faixas de interface/desktop.js: a linha de etapas, as pílulas dos Quadros e (Q5a, 2803276) as abas de Documentos, do Caderno e de Minha conta.
SELETOR_FAIXA = '#mesa-etapas,.quadros-abas,.mesa-tabs,.notebook-tabs'
SELETOR_TABELA = 'table,.markdown-table,.mesa-table-wrap'
SELETOR_ATIVO = '[aria-current],[aria-selected="true"],[aria-pressed="true"]'
TOLERANCIA = 0.6   # px: a subpixel do layout

# Mede todo elemento visível que rola na horizontal. Devolve uma lista de objetos simples (sem nós do DOM).
JS_ROLAGEM_INTERNA = """([seletorFaixa, seletorTabela, seletorAtivo]) => {
  const nome = e => e.id ? '#' + e.id : e.tagName.toLowerCase() + (e.classList.length ? '.' + [...e.classList].join('.') : '');
  const saida = [];
  for (const e of document.querySelectorAll('body *')) {
    const s = getComputedStyle(e);
    if (s.overflowX !== 'auto' && s.overflowX !== 'scroll') continue;
    const r = e.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0 || s.visibility === 'hidden' || s.display === 'none') continue;
    const faixa = e.matches(seletorFaixa), tabela = e.matches(seletorTabela) || !!e.closest('table');
    const ativo = e.querySelector(seletorAtivo);
    const a = ativo ? ativo.getBoundingClientRect() : null;
    const mascara = s.maskImage || s.webkitMaskImage || 'none';
    saida.push({
      nome: nome(e), tipo: faixa ? 'faixa' : tabela ? 'tabela' : 'outro',
      scrollWidth: e.scrollWidth, clientWidth: e.clientWidth, scrollLeft: Math.round(e.scrollLeft * 10) / 10,
      dataRola: e.getAttribute('data-rola'), mascara: mascara !== 'none',
      faixaEsq: r.left, faixaDir: r.right, janela: innerWidth,
      ativo: a ? {texto: (ativo.textContent || '').trim().slice(0, 40), esq: a.left, dir: a.right} : null,
    });
  }
  return saida;
}"""


def medir(pagina) -> list:
    return pagina.evaluate(JS_ROLAGEM_INTERNA, [SELETOR_FAIXA, SELETOR_TABELA, SELETOR_ATIVO])


def lado_esperado(m: dict) -> str:
    """O valor que `data-rola` deveria ter: '' sem estouro, 'fim', 'inicio' ou 'ambos' (a mesma regra de interface/desktop.js)."""
    resto = m['scrollWidth'] - m['clientWidth']
    if resto <= 1:
        return ''
    if m['scrollLeft'] <= 1:
        return 'fim'
    if m['scrollLeft'] >= resto - 1:
        return 'inicio'
    return 'ambos'


def julgar(nome: str, medidas: list) -> tuple[list, list]:
    """Devolve (reprovações, avisos) das medidas de uma captura. `nome` é o da captura, só para a mensagem."""
    reprovacoes, avisos = [], []
    for m in medidas:
        onde = f"{nome}: {m['nome']}"
        rola = m['scrollWidth'] - m['clientWidth'] > 1
        ativo = m.get('ativo')
        if ativo is not None and (rola or m['tipo'] == 'faixa'):
            dentro = ativo['esq'] >= m['faixaEsq'] - TOLERANCIA and ativo['dir'] <= m['faixaDir'] + TOLERANCIA
            na_janela = ativo['esq'] >= -TOLERANCIA and ativo['dir'] <= m['janela'] + TOLERANCIA
            if not (dentro and na_janela):
                reprovacoes.append(f"{onde}: o item ativo {ativo['texto']!r} não cabe inteiro (item {ativo['esq']:.1f}–{ativo['dir']:.1f}, "
                                   f"faixa {m['faixaEsq']:.1f}–{m['faixaDir']:.1f}, janela {m['janela']})")
        if m['tipo'] == 'faixa':
            esperado = lado_esperado(m)
            if (m['dataRola'] or '') != esperado:
                reprovacoes.append(f"{onde}: data-rola={m['dataRola']!r}, esperado {esperado!r} (scrollLeft {m['scrollLeft']}, "
                                   f"{m['scrollWidth']} de {m['clientWidth']} px)")
            elif esperado and not m['mascara']:
                reprovacoes.append(f"{onde}: data-rola={esperado!r} sem mask-image (o esmaecido da borda não aparece)")
        elif m['tipo'] == 'outro' and rola:
            avisos.append(f"{onde}: rola por dentro ({m['scrollWidth']} de {m['clientWidth']} px) e não é faixa nem tabela")
    return reprovacoes, avisos


def resumo_interno(medidas: list) -> list:
    """O que vai ao manifesto: só o que de fato rola (ou é faixa), sem as coordenadas, que variam com a fonte."""
    return [{'nome': m['nome'], 'tipo': m['tipo'], 'scrollWidth': m['scrollWidth'], 'clientWidth': m['clientWidth']}
            for m in medidas if m['tipo'] == 'faixa' or m['scrollWidth'] - m['clientWidth'] > 1]


def pasta_faixa() -> Path:
    import regressao_visual as rv
    return rv.REFERENCIAS / f'{rv.plataforma()}_faixa'


def _selecao(args):
    import regressao_visual as rv
    temas = [t.strip() for t in args.temas.split(',')] if args.temas else list(rv.TEMAS)
    cenarios = [c.strip() for c in args.cenarios.split(',')] if args.cenarios else list(CENARIOS_FAIXA)
    invalidas = [t for t in temas if t not in rv.TEMAS] + [c for c in cenarios if c not in CENARIOS_FAIXA]
    if invalidas:
        raise SystemExit(f'Seleção inválida: {invalidas}')
    return list(TELAS_FAIXA), cenarios, temas


def novas_internas(manifesto: dict, meta: dict, nomes=None) -> dict:
    """Capturas cuja lista de elementos que rolam por dentro difere da referência: {captura: [elementos novos]}. Sem a chave no manifesto, nada a comparar."""
    if 'rolagem_interna' not in manifesto:
        return {}
    antes, agora = manifesto['rolagem_interna'], meta['rolagem_interna']
    achados = {}
    for nome, itens in agora.items():
        if nomes is not None and nome not in nomes:
            continue
        conhecidos = {(i['nome'], i['tipo']) for i in antes.get(nome, [])}
        novos = sorted(i['nome'] for i in itens if (i['nome'], i['tipo']) not in conhecidos)
        if novos:
            achados[nome] = novos
    return achados


def _capturar(args, selecao, pasta: Path):
    import regressao_visual as rv
    import regressao_visual_extras as ex
    telas, cenarios, temas = selecao
    nomes = ex.nomes_esperados(telas, cenarios, temas)
    with rv.Servidores(rv.python_do_servidor(args.python_servidor)) as servidores:
        print(f'Capturando {len(nomes)} imagens...', flush=True)
        meta = ex.capturar(servidores, pasta, telas, cenarios, temas, aviso=lambda m: print(m, flush=True))
    meta['cenarios'] = {k: {**v['viewport'], 'escala': v['escala']} for k, v in CENARIOS_FAIXA.items()}
    return meta, nomes


def _avisar(meta: dict) -> None:
    for nome, avisos in sorted(meta['avisos_rolagem_interna'].items()):
        for aviso in avisos:
            print(f'  AVISO {aviso}')


def provar(args, selecao) -> int:
    """Captura e julga, sem gravar nada como referência. As reprovações saem de `capturar` (SystemExit) com a lista."""
    import tempfile
    with tempfile.TemporaryDirectory(prefix='vlado_visual_faixa_') as tmp:
        meta, nomes = _capturar(args, selecao, Path(tmp))
    _avisar(meta)
    print(f'Faixa que rola: {len(nomes)} capturas, o item ativo cabe inteiro em todas as faixas.')
    return 0


def gerar(args, selecao) -> int:
    import shutil
    import tempfile
    import regressao_visual as rv
    import regressao_visual_extras as ex
    destino = pasta_faixa()
    with tempfile.TemporaryDirectory(prefix='vlado_visual_faixa_') as tmp:
        bruto, novo = Path(tmp) / 'bruto', Path(tmp) / 'novo'
        meta, nomes = _capturar(args, selecao, bruto)
        novo.mkdir()
        for nome in nomes:
            rv.otimizar(bruto / f'{nome}.png', novo / f'{nome}.png')
        ex._escrever_manifesto(novo, meta, sorted(nomes))
        if destino.exists():
            shutil.rmtree(destino)
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(novo, destino)
    _avisar(meta)
    print(f'Referências da faixa em {destino}: {len(nomes)} capturas, {sum(p.stat().st_size for p in destino.glob("*.png")) / 1e6:.2f} MB.')
    return 0


JS_ITENS_DA_FAIXA = """(seletor) => [...document.querySelectorAll(seletor)].filter(f => f.getBoundingClientRect().width > 0 && f.scrollWidth - f.clientWidth > 1)
  .map((f, i) => { f.setAttribute('data-prova-faixa', String(i)); return {indice: i, itens: f.querySelectorAll('button,[role=tab]').length}; })"""
JS_DOIS_QUADROS = "new Promise(ok => requestAnimationFrame(() => requestAnimationFrame(ok)))"
# Faixas cujos itens trocam de aba por clique (a linha de etapas navega, fica de fora).
SELETOR_FAIXAS_DE_ABA = '.quadros-abas,.mesa-tabs,.notebook-tabs'


def troca(args, selecao) -> int:
    """Q5d: o ativo agora é trazido no quadro seguinte. Em cada faixa de abas que rola, clica em cada item e, dois quadros depois, o ativo tem de caber inteiro."""
    from playwright.sync_api import sync_playwright
    import regressao_visual as rv
    telas, cenarios, temas = selecao
    reprovacoes, cliques = [], 0
    with rv.Servidores(rv.python_do_servidor(args.python_servidor)) as servidores, sync_playwright() as pw:
        navegador = pw.chromium.launch(args=rv.ARGS_CHROMIUM)
        try:
            for cenario in cenarios:
                for tema in temas:
                    contexto = navegador.new_context(viewport=CENARIOS_FAIXA[cenario]['viewport'], locale='pt-BR', timezone_id='UTC', color_scheme=rv.TEMAS[tema],
                                                     reduced_motion='reduce', service_workers='block')
                    contexto.add_init_script(f"try{{localStorage.setItem('{rv.CHAVE_TEMA}','{rv.TEMAS[tema]}');localStorage.setItem('{rv.CHAVE_IDIOMA}','pt');}}catch(e){{}}")
                    for tela in telas:
                        pagina = contexto.new_page()
                        atividade = rv.AtividadeDeRede(pagina)
                        url, seletor = rv.destino(servidores, tela)
                        pagina.goto(url, wait_until='load')
                        pagina.wait_for_selector(seletor, state='visible', timeout=30000)
                        atividade.esperar_quieta(pagina)
                        for faixa_ in pagina.evaluate(JS_ITENS_DA_FAIXA, SELETOR_FAIXAS_DE_ABA):
                            marca = f"[data-prova-faixa='{faixa_['indice']}']"
                            for n in range(faixa_['itens']):
                                item = pagina.locator(f'{marca} :is(button,[role=tab])').nth(n)
                                item.click()
                                pagina.evaluate(JS_DOIS_QUADROS)
                                cliques += 1
                                nome = f'{tela}__{cenario}__{tema}__troca{n + 1}'
                                rep, _ = julgar(nome, medir(pagina))
                                reprovacoes += rep
                        pagina.close()
                    contexto.close()
        finally:
            navegador.close()
    for r in reprovacoes:
        print('  REPROVADA', r)
    print(f'Troca de aba: {cliques} clique(s) em faixas que rolam, {len(reprovacoes)} reprovação(ões).')
    return 1 if reprovacoes or not cliques else 0


def comparar(args, selecao) -> int:
    import shutil
    import regressao_visual as rv
    import regressao_visual_comparador as comparador
    referencias = pasta_faixa()
    if not (referencias / 'manifesto.json').is_file():
        print(f'Sem referências da faixa para {rv.plataforma()} em {referencias}. Rode `gerar` nesta plataforma.', file=sys.stderr)
        return 2
    manifesto = json.loads((referencias / 'manifesto.json').read_text(encoding='utf-8'))
    relatorio = Path(args.relatorio) if args.relatorio else rv.RAIZ / 'tmp' / 'regressao_visual_faixa'
    if relatorio.exists():
        shutil.rmtree(relatorio)
    atuais = relatorio / 'atuais'
    meta, nomes = _capturar(args, selecao, atuais)
    ref_filtradas = relatorio / 'referencias'
    ref_filtradas.mkdir()
    for nome in nomes:
        if (referencias / f'{nome}.png').is_file():
            shutil.copy2(referencias / f'{nome}.png', ref_filtradas / f'{nome}.png')
    resultados = comparador.comparar_pastas(ref_filtradas, atuais, relatorio / 'diferencas', esperados=nomes)
    pagina = comparador.escrever_relatorio(resultados, relatorio, ref_filtradas, atuais)
    r = comparador.resumo(resultados)
    novas = novas_internas(manifesto, meta, nomes)
    for nome, quais in novas.items():
        print(f"  REPROVADA {nome}: rolagem por dentro nova em {', '.join(quais)}")
    for res in resultados:
        if not res.aprovado:
            extra = f' ({res.diferentes} px, {res.percentual:.4f}%)' if res.estado == 'diferente' else ''
            print(f'  REPROVADA {res.nome}: {res.estado}{extra}')
    _avisar(meta)
    print(f"{r['aprovadas']}/{r['total']} capturas da faixa dentro da tolerância; {len(novas)} rolagem(ns) por dentro nova(s). Relatório: {pagina}")
    return 0 if not r['reprovadas'] and not novas else 1


COMANDOS = {'provar': provar, 'gerar': gerar, 'comparar': comparar, 'troca': troca}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('comando', choices=('provar', 'gerar', 'comparar', 'troca'))
    parser.add_argument('--cenarios', help='320,390,430 (padrão: os três)')
    parser.add_argument('--temas', help='claro,escuro (padrão: ambos)')
    parser.add_argument('--python-servidor', help='Python do projeto (padrão: .venv do projeto)')
    parser.add_argument('--relatorio', help='pasta do relatório (padrão: tmp/regressao_visual_faixa)')
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding='utf-8')
    return COMANDOS[args.comando](args, _selecao(args))


if __name__ == '__main__':
    raise SystemExit(main())
