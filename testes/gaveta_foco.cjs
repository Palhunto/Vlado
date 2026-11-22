'use strict';
// Gaveta da barra lateral abaixo de 1280 px (docs/design/componentes.md#tablet): com ela aberta, o conteúdo atrás fica `inert`, o foco
// fica preso nela (Tab no último controle volta ao primeiro, Shift+Tab no primeiro vai ao último) e, ao fechar, o foco volta ao botão de menu.
// No celular a gaveta também guarda idioma, tema e sair, que entram na ordem de Tab. DOM sintético (dom_minimo), sem rede; o stub de
// matchMedia só distingue largura de celular/tablet (<1280) de desktop, então 390 e 683 px caem no mesmo caso.
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
// Todo controle focável e visível da gaveta, na ordem do documento (a mesma regra do desktop.js).
const focaveis = mesa => mesa.$('mesa-sidebar').querySelectorAll('a[href],button,input,select,textarea,summary,[tabindex]')
  .filter(no => !no.disabled && no.getAttribute('tabindex') !== '-1' && !no.closest('[hidden]'));
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
  assert.ok(mesa.doc.activeElement === itens(mesa)[0], 'o foco vai para o primeiro item');
  tecla(mesa, mesa.doc, 'Escape');
  assert.equal(mesa.doc.body.classList.contains('mesa-menu-open'), false);
  assert.ok(atras(mesa).every(no => !no.inert), 'ao fechar, o conteúdo volta');
  assert.ok(mesa.doc.activeElement === mesa.$('mesa-menu'), 'o foco volta ao botão de menu');
});

test('gaveta aberta: Tab no último controle volta ao primeiro e Shift+Tab no primeiro vai ao último', async () => {
  const mesa = await abrir();
  mesa.$('mesa-menu').click();
  const lista = focaveis(mesa), primeiro = lista[0], ultimo = lista[lista.length - 1];
  assert.ok(lista.length >= 9);
  ultimo.focus();
  const adiante = tecla(mesa, ultimo, 'Tab');
  assert.equal(adiante.defaultPrevented, true, 'o Tab não deixa o foco sair da gaveta');
  assert.ok(mesa.doc.activeElement === primeiro, 'foco no controle esperado');
  const atrasEv = tecla(mesa, primeiro, 'Tab', {shiftKey: true});
  assert.equal(atrasEv.defaultPrevented, true);
  assert.ok(mesa.doc.activeElement === ultimo, 'foco no controle esperado');
  // No meio da lista o Tab segue o curso normal do navegador.
  lista[3].focus();
  assert.equal(tecla(mesa, lista[3], 'Tab').defaultPrevented, false);
});

test('celular: idioma, sair e tema fazem parte do ciclo de Tab da gaveta, depois do último item da barra', async () => {
  const mesa = await abrir();
  mesa.$('mesa-sair').hidden = false;   // com sessão de contas o botão Sair aparece
  mesa.$('mesa-menu').click();
  const ids = focaveis(mesa).map(no => no.id).filter(Boolean);
  const pos = id => ids.indexOf(id);
  for (const id of ['mesa-idioma', 'mesa-sair', 'mesa-tema']) assert.ok(pos(id) >= 0, `${id} precisa estar na gaveta e ser focável`);
  assert.ok(pos('ver-diligencias') < pos('mesa-idioma') && pos('mesa-idioma') < pos('mesa-sair') && pos('mesa-sair') < pos('mesa-tema'), 'ordem do documento');
  // O Tab passa de um controle ao outro sem ser desviado, e só o último (tema) volta ao começo.
  mesa.$('mesa-idioma').focus();
  assert.equal(tecla(mesa, mesa.$('mesa-idioma'), 'Tab').defaultPrevented, false, 'idioma não é o fim do ciclo');
  mesa.$('mesa-sair').focus();
  assert.equal(tecla(mesa, mesa.$('mesa-sair'), 'Tab').defaultPrevented, false);
  mesa.$('mesa-tema').focus();
  assert.equal(tecla(mesa, mesa.$('mesa-tema'), 'Tab').defaultPrevented, true, 'tema é o último');
  // Shift+Tab no primeiro controle cai no tema, o último do ciclo.
  const primeiro = focaveis(mesa)[0];
  primeiro.focus();
  tecla(mesa, primeiro, 'Tab', {shiftKey: true});
  assert.ok(mesa.doc.activeElement === mesa.$('mesa-tema'), 'foco no controle esperado');
});

test('escolher um item fecha a gaveta, devolve o conteúdo e leva o foco ao botão de menu', async () => {
  const mesa = await abrir();
  mesa.$('mesa-menu').click();
  mesa.$('ver-codex').click();
  await mesa.esperar(4);
  assert.equal(mesa.doc.body.classList.contains('mesa-menu-open'), false);
  assert.ok(atras(mesa).every(no => !no.inert));
  assert.ok(mesa.doc.activeElement === mesa.$('mesa-menu'), 'foco no controle esperado');
});
