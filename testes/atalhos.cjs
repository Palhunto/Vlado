'use strict';
// Keyboard shortcuts: Ctrl/Cmd+Enter sends the question only when sending is enabled;
// J/K (or Alt+↓/↑) move between findings unless the focus is in a text field.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {criarMesa, Evento} = require('./dom_minimo.cjs');

const ALFA = {id: 'alfa', titulo: 'Pauta Alfa', rodadas: [{id: 'R001', geracoes: ['v1']}]};
const achado = numero => ({id: `A00${numero}`, versao: 1, natureza: 'declaracao_documental', redacao: `Afirmação ${numero}`, suporte: 'sustentado',
  vinculos: [], evidencias: [], limitacoes: '', subquestao: 'Pergunta', destino: 'incluido', briefing: null, conferencia_humana: 'nao_realizada',
  verificacao_externa: {estado: 'nao_realizada', limitacao: ''},
  historico: {versoes: [], revisoes_assistidas: [], destinos: [], conferencias_humanas: []}});
const respostas = {
  'codex-listar': {conversas: []},
  inventario: {caso_id: 'alfa', corpus_id: 'c1', documentos: [], total_documentos: 0},
  analises: {analises: []},
  'achados-catalogo': {estado: 'disponivel', revisoes: ['r1'], indices: [{revisao: 'r1', geracao: 'g1'}]},
  'achados-buscar': {resultados: [1, 2, 3].map(achado), documentos: [], artefatos: [], total_correspondencias: 3, retornados: 3, deslocamento: 0,
    proximo_deslocamento: null, estado: 'disponivel', revisoes_sucessoras: [], registros_sha256: 'sintetico'},
  'codex-perguntar': {conversa: 'chat1', estado: 'executando'},
  // A finished run ends the tracking loop, so the test process can exit.
  'codex-eventos': {conversa: {estado: 'concluido'}, eventos: [], cursor: 0},
};

async function abrir(consulta, {idioma = 'pt', desktop = true} = {}) {
  const mesa = criarMesa({desktop, idioma, armazenamento: {'vlado-idioma': idioma}, catalogo: [ALFA],
    api: operacao => respostas[operacao] || {}, url: `http://127.0.0.1:8765/${consulta}`});
  await new Promise(resolve => setTimeout(resolve, 200));
  await mesa.esperar(12);
  return mesa;
}
function tecla(alvo, init) {
  const evento = new Evento('keydown', {bubbles: true, cancelable: true, ...init});
  alvo.dispatchEvent(evento);
  return evento;
}
const perguntas = mesa => mesa.chamadas.filter(c => c.operacao === 'codex-perguntar').length;
const selecionado = mesa => [...mesa.$('achados-resultados').querySelectorAll('.finding-open')].findIndex(botao => botao.getAttribute('aria-pressed') === 'true');

test('Ctrl+Enter e Cmd+Enter enviam a pergunta e anunciam o envio', async () => {
  for (const modificador of ['ctrlKey', 'metaKey']) {
    const mesa = await abrir('?area=codex&caso=alfa');
    mesa.$('codex-pergunta').value = 'O que os contratos permitem afirmar?';
    const evento = tecla(mesa.$('codex-pergunta'), {key: 'Enter', [modificador]: true});
    await mesa.esperar(8);
    assert.deepEqual(mesa.erros, []);
    assert.equal(evento.defaultPrevented, true);
    assert.equal(perguntas(mesa), 1, modificador);
    assert.equal(mesa.$('codex-anuncio').textContent, 'Pergunta enviada.');
  }
});

test('Ctrl+Enter não envia com o envio desativado e avisa pelo anúncio', async () => {
  const mesa = await abrir('?area=codex');
  assert.equal(mesa.$('codex-enviar').disabled, true);
  mesa.$('codex-pergunta').value = 'Pergunta sem apuração';
  tecla(mesa.$('codex-pergunta'), {key: 'Enter', ctrlKey: true});
  await mesa.esperar(8);
  assert.equal(perguntas(mesa), 0);
  assert.equal(mesa.$('codex-anuncio').textContent, 'O envio não está disponível agora.');
});

test('Ctrl+Enter não envia pergunta vazia; Enter sozinho continua quebrando a linha', async () => {
  const mesa = await abrir('?area=codex&caso=alfa');
  mesa.$('codex-pergunta').value = '   ';
  tecla(mesa.$('codex-pergunta'), {key: 'Enter', ctrlKey: true});
  await mesa.esperar(8);
  assert.equal(perguntas(mesa), 0);
  assert.equal(mesa.$('codex-anuncio').textContent, 'Escreva a pergunta antes de enviar.');
  mesa.$('codex-pergunta').value = 'Linha um';
  const simples = tecla(mesa.$('codex-pergunta'), {key: 'Enter'});
  await mesa.esperar(8);
  assert.equal(simples.defaultPrevented, false);
  assert.equal(perguntas(mesa), 0);
});

test('J e K, ou Alt+↓ e Alt+↑, passam ao achado seguinte e ao anterior', async () => {
  const mesa = await abrir('?area=achados&caso=alfa');
  assert.deepEqual(mesa.erros, []);
  assert.equal(selecionado(mesa), 0);
  const corpo = mesa.doc.body;
  assert.equal(tecla(corpo, {key: 'j'}).defaultPrevented, true);
  assert.equal(selecionado(mesa), 1);
  tecla(corpo, {key: 'j'}); tecla(corpo, {key: 'j'});
  assert.equal(selecionado(mesa), 2, 'para no último');
  tecla(corpo, {key: 'k'});
  assert.equal(selecionado(mesa), 1);
  tecla(corpo, {key: 'ArrowUp', altKey: true});
  assert.equal(selecionado(mesa), 0);
  tecla(corpo, {key: 'k'});
  assert.equal(selecionado(mesa), 0, 'para no primeiro');
  tecla(corpo, {key: 'ArrowDown', altKey: true});
  assert.equal(selecionado(mesa), 1);
  assert.match(mesa.$('achados-inspecao').textContent, /Afirmação 2/);
});

test('J e K são ignorados em campos de texto, com modificador, em diálogo e fora de Achados', async () => {
  const mesa = await abrir('?area=achados&caso=alfa');
  for (const campo of ['achados-texto', 'achados-marcacao']) {
    const evento = tecla(mesa.$(campo), {key: 'j'});
    assert.equal(evento.defaultPrevented, false, campo);
    assert.equal(selecionado(mesa), 0, campo);
  }
  tecla(mesa.doc.body, {key: 'j', ctrlKey: true});
  tecla(mesa.doc.body, {key: 'ArrowDown'});
  assert.equal(selecionado(mesa), 0);
  mesa.$('revisao-dialogo').open = true;
  tecla(mesa.doc.body, {key: 'j'});
  assert.equal(selecionado(mesa), 0, 'diálogo aberto');
  mesa.$('revisao-dialogo').open = false;
  mesa.janela.showArea('documentos');
  tecla(mesa.doc.body, {key: 'j'});
  assert.equal(selecionado(mesa), 0, 'outra área');
});

test('os atalhos estão documentados em "Como começar" e traduzidos', async () => {
  const html = fs.readFileSync(path.join(__dirname, '..', 'interface', 'index.html'), 'utf8');
  const linha = 'Atalhos: Ctrl+Enter (⌘+Enter no Mac) envia a pergunta. Em Conferir achados, J e K (ou Alt+↓ e Alt+↑) passam ao achado seguinte e ao anterior.';
  assert.ok(html.slice(html.indexOf('<details class="first-use">'), html.indexOf('</details>', html.indexOf('<details class="first-use">'))).includes(linha));
  const mesa = await abrir('?area=codex&caso=alfa', {idioma: 'en'});
  for (const texto of [linha, 'Pergunta enviada.', 'O envio não está disponível agora.', 'Escreva a pergunta antes de enviar.']) {
    assert.notEqual(mesa.janela.I18N.traduzir(texto), null, texto);
  }
  mesa.$('codex-pergunta').value = 'What do the contracts support?';
  tecla(mesa.$('codex-pergunta'), {key: 'Enter', ctrlKey: true});
  assert.equal(mesa.$('codex-anuncio').textContent, 'Question sent.');
});
