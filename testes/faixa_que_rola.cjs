'use strict';
// Faixa que rola para o lado (docs/design/componentes.md#faixa-que-rola, Q5d): só as faixas e a moldura de Configurações são observadas, nunca a página inteira,
// e as mudanças de uma faixa viram um recálculo por quadro. DOM sintético com observadores que registram o que observam (o dom_minimo não tem layout: a medida é do navegador).
const test = require('node:test');
const assert = require('node:assert/strict');
const {criarMesa} = require('./dom_minimo.cjs');

const SELETOR = ['#mesa-etapas', '.quadros-abas', '.mesa-tabs', '.notebook-tabs'];
async function abrir() {
  const observadores = [];
  const mesa = criarMesa({desktop: true, modo: 'piloto', papel: 'admin', url: 'http://127.0.0.1:8765/?area=inicio',
    preparar: janela => {
      // só os observadores que o desktop.js cria (o i18n.js, por exemplo, observa a página para traduzir)
      janela.MutationObserver = class { constructor(funcao) { this.funcao = funcao; this.doDesktop = /desktop\.js/.test(new Error().stack); observadores.push(this); } observe(alvo, opcoes) { this.alvo = alvo; this.opcoes = opcoes; } disconnect() {} };
    }});
  await mesa.esperar(10);
  return {mesa, observadores};
}
const doDesktop = observadores => observadores.filter(o => o.alvo && o.doDesktop);
const passar = () => new Promise(ok => setTimeout(ok, 25));

test('só as faixas (com os itens) e a moldura de Configurações (filhos diretos) são observadas; nem a página nem a conversa', async () => {
  const {mesa, observadores} = await abrir();
  const alvos = doDesktop(observadores);
  assert.ok(alvos.some(o => o.alvo.id === 'mesa-etapas'), 'a linha de etapas é observada');
  assert.ok(alvos.some(o => o.alvo.classList.contains('mesa-tabs')), 'as abas de Documentos são observadas');
  const conversa = mesa.$('area-codex');
  for (const o of alvos) {
    assert.ok(o.alvo !== mesa.doc.body && o.alvo !== mesa.doc.documentElement, 'nada observa a página inteira');
    assert.ok(o.alvo !== conversa && !o.alvo.contains(conversa), 'nada observa a área da conversa nem um ancestral dela');
    const faixa = SELETOR.some(s => o.alvo.matches(s));
    if (o.alvo.id === 'area-configuracoes') assert.ok(o.opcoes.childList && !o.opcoes.subtree, 'a moldura só nos filhos diretos');
    else if (faixa) assert.ok(o.opcoes.attributes && o.opcoes.attributeFilter.includes('aria-pressed'), 'a faixa observa o item ativo');
  }
});

test('numa conversa com 500 mensagens nenhum nó acrescentado passa pela busca das faixas', async () => {
  const {mesa} = await abrir();
  const consultas = [];
  const original = mesa.doc.querySelectorAll.bind(mesa.doc);
  mesa.doc.querySelectorAll = seletor => { consultas.push(seletor); return original(seletor); };
  const conversa = mesa.$('area-codex');
  for (let i = 0; i < 500; i++) { const mensagem = mesa.doc.createElement('div'); mensagem.textContent = `mensagem ${i}`; conversa.append(mensagem); }
  await passar();
  assert.deepEqual(consultas, [], 'nenhuma varredura da página por nó acrescentado');
});

test('cem mudanças na mesma faixa no mesmo quadro viram um recálculo só', async () => {
  const {mesa, observadores} = await abrir();
  const faixa = mesa.$('mesa-etapas'), observador = doDesktop(observadores).find(o => o.alvo === faixa);
  assert.ok(observador, 'a linha de etapas tem observador');
  let buscas = 0, quadros = 0;
  const buscar = faixa.querySelector.bind(faixa);
  faixa.querySelector = seletor => { buscas += 1; return buscar(seletor); };
  const pedir = mesa.janela.requestAnimationFrame;
  mesa.janela.requestAnimationFrame = funcao => { quadros += 1; return pedir(funcao); };
  for (let i = 0; i < 100; i++) observador.funcao([{type: 'attributes'}]);
  await passar();
  assert.equal(quadros, 1, 'um quadro pedido');
  assert.equal(buscas, 1, 'um recálculo');
  observador.funcao([{type: 'attributes'}]); await passar();
  assert.equal(buscas, 2, 'o quadro seguinte volta a recalcular');
});
