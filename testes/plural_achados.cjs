'use strict';
// R7 da pré-entrega do Design: "3 achado(s) nesta seleção" passa a concordar ("1 achado", "3 achados"), no total da lista, na exportação e no recibo da
// conversa; e o inglês acompanha. O texto do total vem de Leitura.quantidade (app.js e codex.js).
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {criarMesa} = require('./dom_minimo.cjs');

const fonte = nome => fs.readFileSync(path.join(__dirname, '..', 'interface', nome), 'utf8');

test('nenhum texto da tela escreve "achado(s)": o plural concorda', () => {
  for (const nome of ['app.js', 'codex.js', 'experiencia.js', 'desktop.js']) assert.ok(!/achado\(s\)/.test(fonte(nome)), `${nome} sem "achado(s)"`);
  assert.ok(fonte('app.js').includes("Leitura.quantidade(result.total_correspondencias, 'achado')"));
});

test('a concordância em português e em inglês', async () => {
  const pt = criarMesa({});
  assert.equal(pt.janela.Leitura.quantidade(1, 'achado'), '1 achado');
  assert.equal(pt.janela.Leitura.quantidade(0, 'achado'), '0 achados');
  assert.equal(pt.janela.Leitura.quantidade(3, 'achado'), '3 achados');
  const en = criarMesa({idioma: 'en', armazenamento: {'vlado-idioma': 'en'}});
  await en.esperar(6);
  const {t} = en.janela.I18N;
  assert.equal(t('1 achado nesta seleção'), '1 finding in this selection');
  assert.equal(t('3 achados nesta seleção'), '3 findings in this selection');
  assert.equal(t('Achados publicados e verificados: alfa / R001 · 1 achado. Conferência humana não realizada.'), 'Findings published and verified: alfa / R001 · 1 finding(s). Human checking not done.');
});
