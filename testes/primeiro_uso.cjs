'use strict';
// With no investigation registered, the overview shows one first step instead of "continue".
const test = require('node:test');
const assert = require('node:assert/strict');
const {criarMesa} = require('./dom_minimo.cjs');

const ALFA = {id: 'alfa', titulo: 'Pauta Alfa', rodadas: []};
const api = operacao => ({'codex-listar': {conversas: []}, inventario: {caso_id: 'alfa', corpus_id: 'c1', documentos: [], total_documentos: 0}}[operacao] || {});
const TITULO = 'Comece sua primeira apuração';
const PROXIMO = 'Dê um nome à pauta e envie os arquivos. Cada um recebe um recibo, e você já pode perguntar à IA sobre eles.';

async function abrir(catalogo, {desktop = true, idioma = 'pt'} = {}) {
  const mesa = criarMesa({api, desktop, idioma, armazenamento: {'vlado-idioma': idioma}, catalogo, url: 'http://127.0.0.1:8765/'});
  await mesa.esperar(12);
  return mesa;
}

for (const desktop of [true, false]) {
  test(`sem apurações, a visão geral mostra o primeiro passo e esconde "continue" (${desktop ? 'desktop' : 'celular'})`, async () => {
    const mesa = await abrir([], {desktop});
    assert.deepEqual(mesa.erros, []);
    assert.equal(mesa.$('area-inicio').hidden, false);
    assert.equal(mesa.$('mesa-continuar').hidden, true);
    assert.equal(mesa.$('mesa-primeiro-titulo').textContent, TITULO);
    assert.equal(mesa.$('mesa-primeiro-texto').textContent, PROXIMO);
    const visiveis = mesa.$('area-inicio').querySelectorAll('button').filter(botao => !botao.closest('[hidden]'));
    assert.deepEqual(visiveis.map(botao => botao.id), ['inicio-nova'], 'uma única ação');
    assert.equal(mesa.$('inicio-nova').classList.contains('secondary'), false);
    mesa.$('inicio-nova').click();
    assert.equal(mesa.$('area-cadastro').hidden, false);
    assert.equal(mesa.doc.activeElement, mesa.$('cadastro-titulo-input'));
  });
}

test('com apurações, "continue de onde parou" aparece e o primeiro passo volta ao texto comum', async () => {
  const mesa = await abrir([ALFA]);
  assert.equal(mesa.$('mesa-continuar').hidden, false);
  assert.equal(mesa.$('mesa-primeiro-titulo').textContent, 'Nova apuração');
  assert.notEqual(mesa.$('mesa-primeiro-texto').textContent, PROXIMO);
});

test('antes de o catálogo carregar, a tela não afirma que não há apurações', () => {
  const mesa = criarMesa({api, catalogo: [], url: 'http://127.0.0.1:8765/'});
  assert.equal(mesa.$('mesa-primeiro-titulo').textContent, 'Nova apuração');
  assert.equal(mesa.$('mesa-continuar').hidden, false);
});

test('em inglês o primeiro passo sai traduzido', async () => {
  const mesa = await abrir([], {idioma: 'en'});
  mesa.janela.I18N.aplicar(mesa.doc.body);
  assert.equal(mesa.$('mesa-primeiro-titulo').textContent, 'Start your first investigation');
  assert.notEqual(mesa.janela.I18N.traduzir(PROXIMO), null);
});
