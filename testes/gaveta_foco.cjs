'use strict';
// Gaveta da barra lateral abaixo de 1280 px (docs/design/componentes.md#tablet): com ela aberta, o conteúdo atrás fica `inert`, o foco
// fica preso nela (Tab no último item volta ao primeiro, Shift+Tab no primeiro vai ao último) e, ao fechar, o foco volta ao botão de menu.
// DOM sintético (dom_minimo), sem rede.
const test = require('node:test');
const assert = require('node:assert/strict');
const {criarMesa} = require('./dom_minimo.cjs');

const ALFA = {id: 'alfa', titulo: 'Pauta Alfa', rodadas: []};
const api = operacao => ({
  'codex-listar': {conversas: []}, inventario: {caso_id: 'alfa', corpus_id: 'c1', documentos: [], total_documentos: 0},
  'codex-status': {autenticado: true, provedor: 'anthropic', modelo: 'modelo-teste'}, ambiente: {}, 'diligencias-listar': {resultados: []},
}[operacao] || {});

async function abrir() {
  const mesa = criarMesa({api, desktop: false, modo: 'local', idioma: 'pt', url: 'http://127.0.0.1:8765/?area=documentos&caso=alfa', catalogo: [ALFA]});
  await mesa.esperar(12);
  return mesa;
}
const atras = mesa => [mesa.$('conteudo'), mesa.doc.querySelector('.app-header'), mesa.doc.querySelector('.skip-link')];
const itens = mesa => mesa.doc.querySelector('.areas').children.filter(no => ['A', 'BUTTON'].includes(no.tagName) && !no.hidden);
const tecla = (mesa, alvo, key, extra = {}) => {
  const evento = new mesa.janela.Event('keydown', {key, bubbles: true, cancelable: true, ...extra});
  alvo.dispatchEvent(evento);
  return evento;
};

test('gaveta aberta: conteúdo atrás inerte e foco no primeiro item; fechada: tudo volta', async () => {
  const mesa = await abrir();
  assert.ok(atras(mesa).every(no => !no.inert), 'nada inerte com a gaveta fechada');
  mesa.$('mesa-menu').click();
  assert.equal(mesa.doc.body.classList.contains('mesa-menu-open'), true);
  assert.ok(atras(mesa).every(no => no.inert), 'conteúdo, cabeçalho e atalho de pular ficam inertes');
  assert.equal(mesa.$('mesa-sidebar').inert, false);
  assert.equal(mesa.doc.activeElement, itens(mesa)[0], 'o foco vai para o primeiro item');
  tecla(mesa, mesa.doc, 'Escape');
  assert.equal(mesa.doc.body.classList.contains('mesa-menu-open'), false);
  assert.ok(atras(mesa).every(no => !no.inert), 'ao fechar, o conteúdo volta');
  assert.equal(mesa.doc.activeElement, mesa.$('mesa-menu'), 'o foco volta ao botão de menu');
});

test('gaveta aberta: Tab no último item volta ao primeiro e Shift+Tab no primeiro vai ao último', async () => {
  const mesa = await abrir();
  mesa.$('mesa-menu').click();
  const lista = itens(mesa), primeiro = lista[0], ultimo = lista[lista.length - 1];
  assert.ok(lista.length >= 7);
  ultimo.focus();
  const adiante = tecla(mesa, ultimo, 'Tab');
  assert.equal(adiante.defaultPrevented, true, 'o Tab não deixa o foco sair da gaveta');
  assert.equal(mesa.doc.activeElement, primeiro);
  const atrasEv = tecla(mesa, primeiro, 'Tab', {shiftKey: true});
  assert.equal(atrasEv.defaultPrevented, true);
  assert.equal(mesa.doc.activeElement, ultimo);
  // No meio da lista o Tab segue o curso normal do navegador.
  lista[2].focus();
  assert.equal(tecla(mesa, lista[2], 'Tab').defaultPrevented, false);
});

test('escolher um item fecha a gaveta, devolve o conteúdo e leva o foco ao botão de menu', async () => {
  const mesa = await abrir();
  mesa.$('mesa-menu').click();
  mesa.$('ver-codex').click();
  await mesa.esperar(4);
  assert.equal(mesa.doc.body.classList.contains('mesa-menu-open'), false);
  assert.ok(atras(mesa).every(no => !no.inert));
  assert.equal(mesa.doc.activeElement, mesa.$('mesa-menu'));
});
