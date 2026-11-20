'use strict';
// Vditor (about 4 MB) loads only when the notebook editor opens; failures leave the
// Markdown field usable and offer a retry.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {criarMesa, PILHA, Evento} = require('./dom_minimo.cjs');

const ALFA = {id: 'alfa', titulo: 'Pauta Alfa', rodadas: []};
const NOTA = {id: 'n1', titulo: 'Nota um', texto: 'Texto **salvo**', fontes: [], revisao: 1, criado_em_utc: '2026-11-01T10:00:00+00:00'};
const api = operacao => ({
  'apuracao-notas': {caso: 'alfa', revisao_caderno: 1, notas: [{id: 'n1', titulo: 'Nota um', revisao: 1, fontes: 0, autor: null,
    atualizado_em_utc: NOTA.criado_em_utc, criado_em_utc: NOTA.criado_em_utc}]},
  'apuracao-nota': {caso: 'alfa', revisao_caderno: 1, nota: NOTA, fontes: []},
  inventario: {caso_id: 'alfa', corpus_id: 'c1', documentos: [], total_documentos: 0}}[operacao] || {});
const VERSAO = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'interface', 'vendor', 'vditor', 'manifesto.json'), 'utf8')).version;
const vditorScripts = mesa => mesa.doc.head.querySelectorAll('script').filter(s => s.src.startsWith('/vendor/vditor/'));

async function abrirCaderno(opcoes = {}) {
  const mesa = criarMesa({api, catalogo: [ALFA], url: 'http://127.0.0.1:8765/?area=apuracao&caso=alfa', ...opcoes});
  await mesa.esperar(12);
  return mesa;
}
function vditorFalso(janela) {
  janela.criados = [];
  janela.Vditor = class {
    constructor(host, opcoes) { this.opcoes = opcoes; janela.criados.push(this); setTimeout(() => opcoes.after(), 0); }
    setValue(valor) { this.valor = valor; } getValue() { return this.valor; } disabled() {} enable() {}
  };
  janela.Lute = {}; janela.VditorI18n = {};
}

test('a página não carrega o Vditor no início', () => {
  const html = fs.readFileSync(path.join(__dirname, '..', 'interface', 'index.html'), 'utf8');
  assert.ok(!/\/vendor\/vditor\//.test(html), 'index.html ainda referencia /vendor/vditor/');
});

test('outras áreas não pedem o editor; o caderno pede e mostra o carregamento', async () => {
  const codex = await abrirCaderno({url: 'http://127.0.0.1:8765/?area=codex&caso=alfa'});
  assert.equal(vditorScripts(codex).length, 0);
  const mesa = await abrirCaderno();
  assert.deepEqual(mesa.erros, []);
  // Every file carries the Vditor version, so the server can cache it as immutable.
  const v = `?v=${VERSAO}`;
  assert.deepEqual(vditorScripts(mesa).map(s => s.src), [`/vendor/vditor/dist/index.min.js${v}`, `/vendor/vditor/dist/js/lute/lute.min.js${v}`,
    `/vendor/vditor/dist/js/i18n/pt_BR.js${v}`, `/vendor/vditor/dist/js/icons/ant.js${v}`]);
  assert.deepEqual(mesa.doc.head.querySelectorAll('link').filter(l => l.href.startsWith('/vendor/')).map(l => l.href),
    [`/vendor/vditor/dist/index.css${v}`, `/vendor/vditor/dist/css/content-theme/light.css${v}`]);
  assert.equal(mesa.$('vditorLuteScript').src, `/vendor/vditor/dist/js/lute/lute.min.js${v}`, 'ids reconhecidos pelo próprio Vditor');
  assert.equal(mesa.$('vditorContentTheme').href, `/vendor/vditor/dist/css/content-theme/light.css${v}`);
  assert.equal(mesa.$('apuracao-editor-aviso').hidden, false);
  assert.equal(mesa.$('apuracao-editor-aviso').textContent, 'Carregando o editor de notas…');
  vditorFalso(mesa.janela);
  for (const tag of vditorScripts(mesa)) tag.dispatchEvent(new Evento('load'));
  await mesa.esperar(8);
  assert.equal(mesa.janela.criados.length, 1);
  assert.equal(mesa.janela.criados[0].opcoes.value, 'Texto **salvo**');
  // Vditor would add the content theme without the version; the page already loaded it.
  assert.deepEqual(JSON.parse(JSON.stringify(mesa.janela.criados[0].opcoes.preview.theme)), {current: '', path: ''});
  assert.equal(mesa.$('apuracao-editor-aviso').hidden, true);
  assert.equal(mesa.$('apuracao-texto-alternativo').hidden, true);
});

test('falha ao carregar deixa o Markdown editável e oferece nova tentativa', async () => {
  const mesa = await abrirCaderno();
  vditorScripts(mesa)[1].dispatchEvent(new Evento('error'));
  await mesa.esperar(8);
  assert.match(mesa.$('apuracao-editor-aviso').textContent, /não carregou/);
  assert.equal(mesa.$('apuracao-texto-alternativo').hidden, false);
  assert.equal(mesa.$('apuracao-texto').value, 'Texto **salvo**');
  assert.equal(mesa.$('apuracao-editor-tentar').hidden, false);
  mesa.$('apuracao-editor-tentar').click();
  await mesa.esperar(4);
  assert.equal(mesa.$('apuracao-editor-aviso').textContent, 'Carregando o editor de notas…');
  assert.equal(mesa.$('apuracao-editor-tentar').hidden, true);
  vditorFalso(mesa.janela);
  for (const tag of vditorScripts(mesa)) tag.dispatchEvent(new Evento('load'));
  await mesa.esperar(8);
  assert.equal(mesa.janela.criados.length, 1);
  assert.equal(mesa.$('apuracao-texto-alternativo').hidden, true);
});

test('sem editor_notas.js o caderno não quebra e usa o campo Markdown', async () => {
  const mesa = await abrirCaderno({scripts: PILHA.filter(nome => nome !== 'editor_notas.js')});
  assert.deepEqual(mesa.erros, []);
  assert.equal(mesa.$('apuracao-texto').value, 'Texto **salvo**');
  assert.equal(mesa.$('apuracao-texto-alternativo').hidden, false);
  assert.equal(mesa.$('apuracao-editor-aviso').hidden, false);
});
