'use strict';
// Bilingual UI engine and dictionary coverage for the guest-facing area. No browser needed.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const raiz = path.resolve(__dirname, '..', 'interface');

function carregar({padrao = '', salvo = null, armazenamentoBloqueado = false} = {}) {
  const guardado = new Map(salvo ? [['vlado-idioma', salvo]] : []);
  const storage = {
    getItem(chave) { if (armazenamentoBloqueado) throw new Error('bloqueado'); return guardado.get(chave) ?? null; },
    setItem(chave, valor) { if (armazenamentoBloqueado) throw new Error('bloqueado'); guardado.set(chave, valor); },
  };
  const document = {
    readyState: 'complete', documentElement: {lang: ''},
    body: {dataset: padrao ? {idiomaPadrao: padrao} : {}},
    getElementById: () => null,
    createTreeWalker: () => ({nextNode: () => null}),
  };
  const window = {dispatchEvent() {}};
  const contexto = {window, document, localStorage: storage, NodeFilter: {SHOW_TEXT: 4, SHOW_ELEMENT: 1},
    CustomEvent: class { constructor(tipo, init) { this.type = tipo; this.detail = init && init.detail; } }};
  vm.createContext(contexto);
  for (const nome of ['i18n_en.js', 'i18n.js']) vm.runInContext(fs.readFileSync(path.join(raiz, nome), 'utf8'), contexto);
  return {I18N: window.I18N, document, guardado};
}

test('português é o padrão e t() devolve o texto original', () => {
  const {I18N, document} = carregar();
  assert.equal(I18N.idioma(), 'pt');
  assert.equal(I18N.t('Enviar pergunta'), 'Enviar pergunta');
  assert.equal(document.documentElement.lang, 'pt-BR');
});

test('padrão do servidor em inglês traduz textos exatos, padrões e variáveis', () => {
  const {I18N, document} = carregar({padrao: 'en'});
  assert.equal(I18N.idioma(), 'en');
  assert.equal(document.documentElement.lang, 'en');
  assert.equal(I18N.t('Enviar pergunta'), 'Send question');
  assert.equal(I18N.t('Conectado à API · Anthropic · claude-sonnet-5-5'), 'Connected to API · Anthropic · claude-sonnet-5-5');
  assert.equal(I18N.t('Padrão: {m}', {m: 'gpt-6.1-sol'}), 'Default: gpt-6.1-sol');
  assert.equal(I18N.t('  Fonte pendente  '), '  Source pending  ');
  assert.equal(I18N.t('Texto que não está no dicionário'), 'Texto que não está no dicionário');
});

test('escolha salva prevalece sobre o padrão e troca de idioma é persistida', () => {
  const {I18N, guardado} = carregar({padrao: 'en', salvo: 'pt'});
  assert.equal(I18N.idioma(), 'pt');
  I18N.definir('en');
  assert.equal(guardado.get('vlado-idioma'), 'en');
  assert.equal(I18N.t('Nova conversa'), 'New conversation');
});

test('armazenamento bloqueado não impede o uso nem a troca de idioma', () => {
  const {I18N} = carregar({padrao: 'en', armazenamentoBloqueado: true});
  assert.equal(I18N.idioma(), 'en');
  I18N.definir('pt');
  assert.equal(I18N.t('Nova conversa'), 'Nova conversa');
});

function textosDoTrecho(html) {
  const sem = html.replace(/<script[\s\S]*?<\/script>/g, '').replace(/<style[\s\S]*?<\/style>/g, '')
    .replace(/<[^>]*translate="no"[^>]*>[^<]*</g, '<');
  const textos = [...sem.matchAll(/>([^<>]+)</g)].map(m => m[1].replace(/\s+/g, ' ').trim());
  const atributos = [...sem.matchAll(/\s(?:title|placeholder|aria-label|alt)="([^"]+)"/g)].map(m => m[1].trim());
  return [...textos, ...atributos].filter(t => /[A-Za-zÀ-ú]/.test(t));
}

test('cabeçalho, navegação e área Perguntar à IA estão completamente traduzidos', () => {
  const {I18N} = carregar({padrao: 'en'});
  const html = fs.readFileSync(path.join(raiz, 'index.html'), 'utf8');
  const inicioCodex = html.indexOf('<section id="area-codex"');
  const fimCodex = html.indexOf('<section id="area-', inicioCodex + 10);
  const trechos = [html.slice(html.indexOf('<header'), html.indexOf('</aside>')), html.slice(inicioCodex, fimCodex)];
  const ausentes = [...new Set(trechos.flatMap(textosDoTrecho))]
    .filter(t => !['Vlado', 'English', 'Anthropic (Claude)', 'OpenAI (GPT)'].includes(t) && I18N.traduzir(t) === null);
  assert.deepEqual(ausentes, []);
});
