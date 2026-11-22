'use strict';
// Dicionário em inglês sob demanda (Onda 3, parte C, UX-14): em português a página não baixa o i18n_en.js (~120 KB); ao passar para o inglês
// i18n.js injeta o <script>, espera o carregamento e só então traduz; sem o dicionário a tela segue em português; o hash do arquivo vem do
// <meta name="vlado-versoes">. DOM sintético (dom_minimo): o teste faz o papel do navegador (define VLADO_I18N_EN e chama onload).
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {criarMesa} = require('./dom_minimo.cjs');

const DICIONARIO = {textos: {'Visão geral': 'Overview'}, padroes: [], erros: {}};
const scriptsDoDicionario = mesa => mesa.doc.querySelectorAll('script').filter(no => String(no.src || no.getAttribute?.('src') || '').includes('i18n_en.js'));

async function abrir(idioma = 'pt') {
  const mesa = criarMesa({idioma, scripts: ['i18n.js'], url: 'http://127.0.0.1:8765/?area=inicio'});
  await mesa.esperar(6);
  return mesa;
}

test('em português a página não pede o dicionário em inglês', async () => {
  const mesa = await abrir('pt');
  assert.equal(scriptsDoDicionario(mesa).length, 0);
  assert.equal(mesa.janela.I18N.idioma(), 'pt');
});

test('ao passar para o inglês, injeta o script, espera o carregamento e então traduz', async () => {
  const mesa = await abrir('pt');
  const rotulo = mesa.doc.createElement('span'); rotulo.textContent = 'Visão geral'; mesa.doc.body.append(rotulo);
  const promessa = mesa.janela.I18N.definir('en');
  assert.ok(promessa && typeof promessa.then === 'function', 'definir devolve uma promessa enquanto o dicionário não chegou');
  const tags = scriptsDoDicionario(mesa);
  assert.equal(tags.length, 1, 'um script injetado');
  assert.match(tags[0].src, /^\/i18n_en\.js(\?v=.+)?$/);
  assert.equal(mesa.janela.I18N.idioma(), 'pt', 'ainda em português até o dicionário chegar');
  mesa.janela.VLADO_I18N_EN = DICIONARIO;   // o que o i18n_en.js faz ao executar
  tags[0].onload();
  await promessa;
  assert.equal(mesa.janela.I18N.idioma(), 'en');
  assert.equal(rotulo.textContent, 'Overview');
  // Voltar e ir de novo não baixa outra vez.
  mesa.janela.I18N.definir('pt');
  mesa.janela.I18N.definir('en');
  assert.equal(scriptsDoDicionario(mesa).length, 1);
});

test('se o dicionário não carregar, a tela segue em português e não trava', async () => {
  const mesa = await abrir('pt');
  const rotulo = mesa.doc.createElement('span'); rotulo.textContent = 'Visão geral'; mesa.doc.body.append(rotulo);
  const promessa = mesa.janela.I18N.definir('en');
  scriptsDoDicionario(mesa)[0].onerror();
  await promessa;
  assert.equal(rotulo.textContent, 'Visão geral');
});

test('a URL do dicionário leva o hash do <meta name="vlado-versoes"> quando o servidor o informa', async () => {
  const mesa = await abrir('pt');
  const meta = mesa.doc.createElement('meta'); meta.setAttribute('name', 'vlado-versoes'); meta.setAttribute('content', JSON.stringify({'i18n_en.js': 'abc123def456'}));
  mesa.doc.head.append(meta);
  mesa.janela.I18N.definir('en');
  assert.equal(scriptsDoDicionario(mesa)[0].src, '/i18n_en.js?v=abc123def456');
});

test('index.html não carrega mais o i18n_en.js e o corpo em inglês espera o dicionário, com saída de segurança', () => {
  const raiz = path.join(__dirname, '..', 'interface');
  const html = fs.readFileSync(path.join(raiz, 'index.html'), 'utf8');
  assert.doesNotMatch(html, /<script[^>]+i18n_en\.js/);
  const css = fs.readFileSync(path.join(raiz, 'style.css'), 'utf8');
  assert.match(css, /body\[data-idioma-padrao=en\]:not\(\[data-i18n-pronto\]\)\{[^}]*visibility:hidden[^}]*animation:vlado-mostrar 0s 3s forwards/);
});
