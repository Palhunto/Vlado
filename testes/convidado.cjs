'use strict';
// Guest path: the invite lands on "Ask the AI" with the guest's own investigation selected.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {criarMesa} = require('./dom_minimo.cjs');

const ALFA = {id: 'alfa', titulo: 'Pauta Alfa', rodadas: []};
const BETA = {id: 'beta', titulo: 'Pauta Beta', rodadas: []};
const api = operacao => ({
  'codex-listar': {conversas: []}, inventario: {caso_id: 'alfa', corpus_id: 'c1', documentos: [], total_documentos: 0},
  'codex-status': {autenticado: true, provedor: 'anthropic', modelo: 'modelo-teste'}, ambiente: {},
}[operacao] || {});

async function abrir(opcoes) {
  const mesa = criarMesa({api, modo: 'piloto', idioma: 'en', ...opcoes});
  await mesa.esperar(12);
  return mesa;
}
const rota = mesa => new URL(mesa.janela.location.href).searchParams;
const navegacao = mesa => mesa.doc.querySelector('.areas').children.filter(no => ['A', 'BUTTON'].includes(no.tagName));

test('convidado com uma apuração entra com ela selecionada no cabeçalho e na conversa', async () => {
  const mesa = await abrir({papel: 'convidado', url: 'http://127.0.0.1:8765/?area=codex', catalogo: [ALFA]});
  assert.deepEqual(mesa.erros, []);
  assert.equal(mesa.janela.contextoCaso(), 'alfa');
  assert.equal(mesa.$('contexto-caso').value, 'alfa');
  assert.equal(mesa.$('codex-caso').value, 'alfa');
  assert.equal(rota(mesa).get('caso'), 'alfa');
  assert.equal(rota(mesa).get('area'), 'codex');
});

test('convidado com várias apurações respeita ?caso= do convite, mesmo sem área', async () => {
  const comArea = await abrir({papel: 'convidado', url: 'http://127.0.0.1:8765/?area=codex&caso=beta', catalogo: [ALFA, BETA]});
  assert.equal(comArea.janela.contextoCaso(), 'beta');
  const semArea = await abrir({papel: 'convidado', url: 'http://127.0.0.1:8765/?caso=beta', catalogo: [ALFA, BETA]});
  assert.equal(semArea.janela.contextoCaso(), 'beta');
  assert.equal(rota(semArea).get('area'), 'codex');
  const semEscolha = await abrir({papel: 'convidado', url: 'http://127.0.0.1:8765/?area=codex', catalogo: [ALFA, BETA]});
  assert.equal(semEscolha.janela.contextoCaso(), '');
});

test('administrador com uma apuração mantém a escolha explícita', async () => {
  const mesa = await abrir({papel: 'admin', modo: 'local', idioma: 'pt', url: 'http://127.0.0.1:8765/?area=codex', catalogo: [ALFA]});
  assert.equal(mesa.janela.contextoCaso(), '');
  assert.equal(mesa.$('contexto-caso').value, '');
});

for (const desktop of [false, true]) {
  test(`convidado só vê Perguntar à IA na navegação (${desktop ? 'links de desktop' : 'botões'}), sem etapas`, async () => {
    const mesa = await abrir({papel: 'convidado', desktop, url: 'http://127.0.0.1:8765/?area=codex', catalogo: [ALFA]});
    // A link added later (desktop swaps buttons for links) is limited the same way.
    const link = mesa.doc.createElement('a'); link.id = 'ver-achados-link'; mesa.doc.querySelector('.areas').append(link);
    mesa.janela.limitarNavegacaoConvidado();
    const itens = navegacao(mesa);
    assert.ok(itens.length >= 9);
    assert.equal(mesa.$('ver-codex').tagName, desktop ? 'A' : 'BUTTON');
    const visiveis = itens.filter(no => !no.hidden).map(no => no.id);
    assert.deepEqual(visiveis, ['ver-codex']);
    assert.equal(mesa.$('mesa-etapas').hidden, true);
    // Navigation to any other area keeps the guest on the conversation.
    mesa.janela.showArea('gerenciar');
    assert.equal(rota(mesa).get('area'), 'codex');
    assert.equal(mesa.$('area-gerenciar').hidden, true);
    assert.equal(mesa.$('area-codex').hidden, false);
  });
}

test('administrador mantém navegação completa e as etapas', async () => {
  const mesa = await abrir({papel: 'admin', modo: 'local', idioma: 'pt', desktop: true, url: 'http://127.0.0.1:8765/?area=codex', catalogo: [ALFA]});
  // A barra tem os sete itens do canvas (Visão geral, Documentos, Perguntar, Conferir, Quadros, Caderno, Pedidos e prazos);
  // Cadastrar, Trechos e Apurações e lixeira seguem no DOM, ocultos.
  assert.equal(navegacao(mesa).filter(no => !no.hidden).length, 7);
  assert.equal(mesa.$('mesa-etapas').hidden, false);
});

test('folha de estilos não esconde o seletor de apuração do convidado e cobre botões e links', () => {
  const css = fs.readFileSync(path.join(__dirname, '..', 'interface', 'style.css'), 'utf8');
  assert.doesNotMatch(css, /data-papel="convidado"\][^{]*\.persistent-context/);
  assert.match(css, /data-papel="convidado"\] \.areas :is\(button,a\):not\(#ver-codex\)/);
  assert.match(css, /data-papel="convidado"\] #mesa-etapas/);
});
