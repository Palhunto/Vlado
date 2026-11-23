'use strict';
// Idioma do Entrar (P42): a escolha guardada neste navegador ('vlado-idioma') vence; sem ela vale o idioma que o servidor pôs em data-idioma-padrao do <body>
// (conta, Accept-Language, padrão do servidor: test_idioma_pagina.py), o mesmo da Mesa; um valor que não é pt nem en cai em português.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {criarMesa} = require('./dom_minimo.cjs');

const HTML = fs.readFileSync(path.join(__dirname, '..', 'interface', 'entrar.html'), 'utf8');
const abrir = async (padrao, guardado) => {
  const mesa = criarMesa({html: HTML.replace('__IDIOMA_PADRAO__', padrao), url: 'http://127.0.0.1:8765/entrar', scripts: ['estados.js', 'entrar.js'],
    armazenamento: guardado ? {'vlado-idioma': guardado} : {}, api: () => { const erro = new Error('sem sessão'); erro.result = {estado: 'sem_sessao', codigo: 'sem_sessao', erro: 'sem sessão'}; throw erro; }});
  await mesa.esperar(8);
  return mesa;
};
const idioma = mesa => mesa.doc.documentElement.lang;

test('o entrar.html leva o marcador que o servidor troca pelo idioma da página', () => {
  assert.match(HTML, /<body class="entrar-pagina" data-idioma-padrao="__IDIOMA_PADRAO__">/);
});

test('sem escolha no navegador vale o idioma do servidor (pt ou en); valor estranho cai em português', async () => {
  assert.equal(idioma(await abrir('en')), 'en');
  assert.equal(idioma(await abrir('pt')), 'pt-BR');
  assert.equal(idioma(await abrir('__IDIOMA_PADRAO__')), 'pt-BR', 'página servida sem troca (teste, arquivo aberto à mão)');
  assert.equal(idioma(await abrir('fr')), 'pt-BR');
});

test('a escolha guardada no navegador vence o idioma do servidor, nos dois sentidos', async () => {
  assert.equal(idioma(await abrir('en', 'pt')), 'pt-BR');
  assert.equal(idioma(await abrir('pt', 'en')), 'en');
});
