'use strict';
// Work areas open with a compact heading: the area name and the investigation in context.
const test = require('node:test');
const assert = require('node:assert/strict');
const {criarMesa} = require('./dom_minimo.cjs');

const ALFA = {id: 'alfa', titulo: 'Pauta Alfa', rodadas: []};
const api = operacao => ({'codex-listar': {conversas: []}, inventario: {caso_id: 'alfa', corpus_id: 'c1', documentos: [], total_documentos: 0}}[operacao] || {});

async function abrir(url, desktop = true) {
  const mesa = criarMesa({api, desktop, catalogo: [ALFA], url: `http://127.0.0.1:8765/${url}`});
  await mesa.esperar(12);
  return mesa;
}

for (const desktop of [true, false]) {
  test(`cabeçalho mostra a área como título e a apuração como contexto (${desktop ? 'desktop' : 'celular'})`, async () => {
    const mesa = await abrir('?area=codex&caso=alfa', desktop);
    assert.deepEqual(mesa.erros, []);
    assert.equal(mesa.doc.querySelectorAll('h1').length, 1);
    assert.equal(mesa.$('area-titulo').textContent, 'Perguntar à IA');
    assert.equal(mesa.$('area-descricao').textContent, 'Pauta Alfa');
    assert.equal(mesa.$('area-descricao').getAttribute('translate'), 'no');
    assert.equal(mesa.$('area-etiqueta'), null, 'sem sobretítulo');
    mesa.janela.showArea('diligencias');
    assert.equal(mesa.$('area-titulo').textContent, 'Diligências');
    assert.equal(mesa.$('area-descricao').textContent, 'Pauta Alfa');
    mesa.janela.definirContextoCaso('', {force: true});
    assert.equal(mesa.$('area-descricao').textContent, 'Nenhuma apuração selecionada');
    assert.equal(mesa.$('area-descricao').hasAttribute('translate'), false);
  });
}

test('no celular, idioma, tema e saída vão para a gaveta e o seletor de apuração fica no cabeçalho', async () => {
  const celular = await abrir('?area=codex', false);
  for (const id of ['mesa-idioma', 'mesa-sair', 'mesa-tema']) {
    assert.ok(celular.$(id).closest('#mesa-sidebar .mesa-drawer-controls'), `${id} na gaveta`);
  }
  assert.ok(celular.$('contexto-caso').closest('.app-header'));
  const desktop = await abrir('?area=codex', true);
  for (const id of ['mesa-idioma', 'mesa-sair', 'mesa-tema']) assert.ok(desktop.$(id).closest('.app-header'), `${id} no cabeçalho`);
});

test('troca de apuração não repete o nome acima do título', async () => {
  const mesa = await abrir('?area=documentos');
  mesa.janela.definirContextoCaso('alfa');
  assert.equal(mesa.$('area-descricao').textContent, 'Pauta Alfa');
  assert.ok(mesa.$('experiencia-status').classList.contains('sr-only'), 'aviso de troca fica para leitores de tela');
});

test('visão geral troca a ilustração por um painel simples de primeiro passo', async () => {
  const mesa = await abrir('?area=inicio');
  assert.equal(mesa.$('area-titulo').textContent, 'Visão geral');
  assert.equal(mesa.doc.querySelector('.mesa-hero-art'), null);
  assert.equal(mesa.doc.querySelector('.mesa-paper'), null);
  assert.ok(mesa.$('inicio-nova').closest('.panel'));
  assert.equal(mesa.$('area-inicio').querySelectorAll('.eyebrow').length, 0);
});
