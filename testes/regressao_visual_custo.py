"""Custo da faixa que rola numa conversa longa (Q5d da Coruja): quantas vezes o recálculo roda quando chegam 200 mensagens.

    ~/.cache/vlado-visual-venv/Scripts/python.exe testes/regressao_visual_custo.py [--mensagens 200]

(O Python do ambiente visual tem o Playwright; o `.venv` do projeto não tem.)

Abre a área Perguntar à IA a 390 px, instrumenta o `MutationObserver` e as consultas de seletor das faixas antes de qualquer script da página e, com a
conversa aberta, acrescenta as mensagens em `#codex-mensagens` de duas formas: todas de uma vez e uma por tarefa (como o andamento de uma resposta). Imprime,
por observador, as chamadas, os registros, os nós novos e o tempo, e as consultas de seletor de faixa feitas por nó que entrou na página.

Reprova só o que não depende da máquina: observador cujos alvos são todos faixas e que acorda por causa de mensagem (mensagem nova nunca é conteúdo de
faixa). O observador do corpo (que pega as abas de Minha conta, que nascem depois) é custo, não reprovação: o número vai ao relatório para o Design e o
Lume compararem antes e depois do Q5d. Nada aqui grava referência.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

FAIXAS = '#mesa-etapas,.quadros-abas,.mesa-tabs,.notebook-tabs'

# Antes de qualquer script da página: conta, por observador, as chamadas, os registros, os nós novos e o tempo; e as consultas de seletor de faixa.
JS_INSTRUMENTO = """(() => {
  const faixas = '#mesa-etapas,.quadros-abas,.mesa-tabs,.notebook-tabs';
  const custo = window.__custoFaixa = {ligado: false, observadores: [], consultas: 0};
  const nomeDe = n => n === document ? 'document' : n === document.body ? 'body' : n === document.documentElement ? 'html'
    : (n.id ? '#' + n.id : String(n.tagName || '?').toLowerCase() + (n.classList && n.classList.length ? '.' + [...n.classList].join('.') : ''));
  const Original = window.MutationObserver;
  window.MutationObserver = class extends Original {
    constructor(chamada) {
      const reg = {alvos: [], chamadas: 0, registros: 0, nos: 0, ms: 0};
      super(function (registros, observador) {
        if (!custo.ligado) return chamada.call(this, registros, observador);
        const t = performance.now();
        reg.chamadas++; reg.registros += registros.length;
        for (const r of registros) reg.nos += r.addedNodes.length;
        try { return chamada.call(this, registros, observador); } finally { reg.ms += performance.now() - t; }
      });
      this.__reg = reg;
      custo.observadores.push(reg);
    }
    observe(alvo, opcoes) {
      let faixa = false;
      try { faixa = alvo.nodeType === 1 && alvo.matches(faixas); } catch (e) { /* alvo sem matches */ }
      this.__reg.alvos.push({nome: nomeDe(alvo), faixa});
      return super.observe(alvo, opcoes);
    }
  };
  // Q5d: o recálculo vai para o quadro seguinte (requestAnimationFrame) e começa lendo o estilo da faixa; contar os dois mostra quantas vezes ele de fato roda.
  const casa = Element.prototype.matches;
  custo.raf = 0; custo.estilos = 0;
  const pedirQuadro = window.requestAnimationFrame;
  window.requestAnimationFrame = function (chamada) { if (custo.ligado) custo.raf++; return pedirQuadro.call(this, chamada); };
  const estilo = window.getComputedStyle;
  window.getComputedStyle = function (e, ...resto) { if (custo.ligado && e && e.nodeType === 1 && casa.call(e, faixas)) custo.estilos++; return estilo.call(this, e, ...resto); };
  const conta = (proto, nome) => {
    const original = proto[nome];
    proto[nome] = function (seletor, ...resto) {
      if (custo.ligado && typeof seletor === 'string' && /mesa-etapas|quadros-abas|mesa-tabs|notebook-tabs/.test(seletor)) custo.consultas++;
      return original.call(this, seletor, ...resto);
    };
  };
  conta(Element.prototype, 'matches'); conta(Element.prototype, 'querySelectorAll'); conta(Element.prototype, 'closest');
})();"""

# As rodadas como o codex.js as desenha (pergunta, resposta, ações e andamento), no fim de #codex-mensagens.
JS_CHEGAM_MENSAGENS = """async ([quantas, umaPorTarefa]) => {
  const alvo = document.getElementById('codex-mensagens');
  const custo = window.__custoFaixa;
  const rodada = n => {
    const raiz = document.createElement('section'); raiz.className = 'codex-round';
    const usuario = document.createElement('article'); usuario.className = 'codex-message codex-user';
    usuario.innerHTML = '<h3>Sua pergunta</h3><p class="codex-text">Pergunta sintética ' + n + '</p>';
    const respostas = document.createElement('div'); respostas.className = 'codex-answers';
    respostas.innerHTML = '<article class="codex-message"><p class="codex-text">Resposta sintética ' + n + ', com um parágrafo de tamanho razoável para a conversa ficar longa.</p></article>';
    const acoes = document.createElement('div'); acoes.className = 'actions';
    const andamento = document.createElement('details'); andamento.className = 'codex-updates';
    andamento.innerHTML = '<summary>Atualizações de andamento</summary><div class="codex-updates-body" tabindex="0" role="region" aria-label="Atualizações de andamento da IA"></div>';
    raiz.append(usuario, respostas, acoes, andamento);
    return raiz;
  };
  const antes = alvo.children.length;
  custo.observadores.forEach(o => { o.chamadas = 0; o.registros = 0; o.nos = 0; o.ms = 0; });
  custo.consultas = 0; custo.raf = 0; custo.estilos = 0; custo.ligado = true;
  const inicio = performance.now();
  if (umaPorTarefa) { for (let i = 0; i < quantas; i++) { alvo.append(rodada(i)); await new Promise(ok => setTimeout(ok, 0)); } }
  else { for (let i = 0; i < quantas; i++) alvo.append(rodada(i)); await new Promise(ok => setTimeout(ok, 0)); }
  await new Promise(ok => requestAnimationFrame(() => requestAnimationFrame(ok)));
  custo.ligado = false;
  // Os dois requestAnimationFrame de cima são desta medida, não da página.
  return {total_ms: performance.now() - inicio, consultas_de_faixa: custo.consultas, quadros_pedidos: Math.max(0, custo.raf - 2), estilos_de_faixa: custo.estilos,
          novas: alvo.children.length - antes,
          observadores: custo.observadores.filter(o => o.chamadas).map(o => ({alvos: o.alvos, chamadas: o.chamadas, registros: o.registros, nos: o.nos, ms: o.ms}))};
}"""


def julgar_custo(modo: str, medida: dict) -> list:
    """Reprovações de uma medida. Observador cujos alvos são só faixas não deve acordar com a chegada de mensagem; o resto é custo, vai para o relatório."""
    reprovacoes = []
    for o in medida['observadores']:
        if o['alvos'] and all(a['faixa'] for a in o['alvos']):
            reprovacoes.append(f"({modo}) o observador da faixa {', '.join(a['nome'] for a in o['alvos'])} recalculou {o['chamadas']} vez(es) com a chegada das mensagens")
    if medida.get('novas') is not None and medida['novas'] <= 0:
        reprovacoes.append(f'({modo}) nenhuma mensagem chegou à conversa: a medida não vale')
    return reprovacoes


def relatorio(modo: str, quantas: int, m: dict) -> list:
    linhas = [f"{quantas} mensagens, {modo}: {m['total_ms']:.0f} ms no total, {m['consultas_de_faixa']} consulta(s) de seletor de faixa, "
              f"{m.get('quadros_pedidos', 0)} quadro(s) pedido(s), {m.get('estilos_de_faixa', 0)} leitura(s) de estilo de faixa (o recálculo), "
              f"{len(m['observadores'])} observador(es) acordaram"]
    for o in sorted(m['observadores'], key=lambda o: -o['ms']):
        alvos = ', '.join(a['nome'] + ('*' if a['faixa'] else '') for a in o['alvos'])
        linhas.append(f"    [{alvos}] {o['chamadas']} chamada(s), {o['registros']} registro(s), {o['nos']} nó(s) novos, {o['ms']:.1f} ms")
    return linhas


def medir(args) -> int:
    from playwright.sync_api import sync_playwright
    import regressao_visual as rv
    reprovacoes, linhas = [], []
    with rv.Servidores(rv.python_do_servidor(args.python_servidor)) as servidores, sync_playwright() as pw:
        for uma_por_tarefa in (False, True):
            modo = 'uma por tarefa' if uma_por_tarefa else 'todas de uma vez'
            navegador = pw.chromium.launch(args=rv.ARGS_CHROMIUM)
            try:
                contexto = navegador.new_context(viewport={'width': 390, 'height': 844}, locale='pt-BR', timezone_id='UTC', color_scheme='light',
                                                 reduced_motion='reduce', service_workers='block')
                contexto.add_init_script(JS_INSTRUMENTO)
                contexto.add_init_script(f"try{{localStorage.setItem('{rv.CHAVE_TEMA}','light');localStorage.setItem('{rv.CHAVE_IDIOMA}','pt');}}catch(e){{}}")
                pagina = contexto.new_page()
                atividade = rv.AtividadeDeRede(pagina)
                url, seletor = rv.destino(servidores, 'codex')
                pagina.goto(url, wait_until='load')
                pagina.wait_for_selector(seletor, state='visible', timeout=30000)
                atividade.esperar_quieta(pagina)
                medida = pagina.evaluate(JS_CHEGAM_MENSAGENS, [args.mensagens, uma_por_tarefa])
            finally:
                navegador.close()
            reprovacoes += julgar_custo(modo, medida)
            linhas += relatorio(modo, args.mensagens, medida)
    print('\n'.join(linhas))
    print('(* = alvo é uma faixa que rola)')
    for r in reprovacoes:
        print('  REPROVADA', r)
    return 1 if reprovacoes else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--mensagens', type=int, default=200, help='quantas rodadas chegam à conversa (padrão: 200)')
    parser.add_argument('--python-servidor', help='Python do projeto (padrão: .venv do projeto)')
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding='utf-8')
    return medir(args)


if __name__ == '__main__':
    raise SystemExit(main())
