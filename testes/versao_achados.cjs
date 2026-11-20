'use strict';
// Achados opens on the latest analysis, step and results version, shows the selection as a
// chip that reopens the selectors, and still honours an address that names a version.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {criarMesa} = require('./dom_minimo.cjs');

const ALFA = {id: 'alfa', titulo: 'Pauta Alfa', rodadas: [{id: 'R001', geracoes: ['v1']}, {id: 'R003', geracoes: ['v1']}]};
const VAZIA = {id: 'beta', titulo: 'Pauta Beta', rodadas: []};
const busca = {resultados: [], documentos: [], artefatos: [], total_correspondencias: 0, retornados: 0, deslocamento: 0,
  proximo_deslocamento: null, estado: 'disponivel', revisoes_sucessoras: [], registros_sha256: 'sintetico'};
const respostas = {
  'codex-listar': {conversas: []},
  inventario: {caso_id: 'alfa', corpus_id: 'c1', documentos: [], total_documentos: 0},
  analises: {analises: [{id: 'R001', data: '2026-11-02T15:00:00Z', pergunta: 'Primeira pergunta', documentos: 2},
    {id: 'R003', data: '2026-11-12T15:00:00Z', pergunta: 'Terceira pergunta', documentos: 3}]},
  // The synthesis step has no results version yet, so the latest usable step is r2.
  'achados-catalogo': {estado: 'disponivel', revisoes: ['r1', 'r2', 'r3_sintese'],
    indices: [{revisao: 'r1', geracao: 'g1'}, {revisao: 'r2', geracao: 'g1'}, {revisao: 'r2', geracao: 'g2'}]},
  'achados-buscar': busca,
};

async function abrir(consulta, {desktop = true, idioma = 'pt'} = {}) {
  const mesa = criarMesa({desktop, idioma, armazenamento: {'vlado-idioma': idioma}, catalogo: [ALFA, VAZIA],
    api: operacao => respostas[operacao] || {}, url: `http://127.0.0.1:8765/${consulta}`});
  mesa.assentar = async () => { await new Promise(resolve => setTimeout(resolve, 250)); await mesa.esperar(12); };
  await mesa.assentar();
  mesa.buscas = () => mesa.chamadas.filter(c => c.operacao === 'achados-buscar').map(c => [c.dados.rodada, c.dados.revisao, c.dados.geracao_achados].join('/'));
  return mesa;
}

for (const desktop of [true, false]) {
  test(`abre na análise, etapa e versão mais recentes e mostra o chip (${desktop ? 'desktop' : 'celular'})`, async () => {
    const mesa = await abrir('?area=achados&caso=alfa', {desktop});
    assert.deepEqual(mesa.erros, []);
    assert.equal(mesa.$('rodada').value, 'R003');
    assert.equal(mesa.$('achados-revisao').value, 'r2');
    assert.equal(mesa.$('achados-geracao').value, 'g2');
    assert.deepEqual(mesa.buscas(), ['R003/r2/g2']);
    const chip = mesa.$('achados-versao-chip');
    assert.equal(chip.hidden, false);
    assert.equal(chip.localName, 'button');
    assert.equal(chip.textContent, 'Análise R003 · 12/11 · Revisão do suporte · trocar');
    assert.equal(chip.getAttribute('aria-expanded'), 'false');
    assert.ok(mesa.$('achados-versoes').classList.contains('versao-recolhida'));
    assert.ok(mesa.$('selecao-acervo').classList.contains('versao-recolhida'));
  });
}

test('o chip reabre os seletores; trocar de análise volta a escolher o mais recente dela', async () => {
  const mesa = await abrir('?area=achados&caso=alfa');
  const chip = mesa.$('achados-versao-chip');
  chip.click();
  assert.equal(chip.getAttribute('aria-expanded'), 'true');
  assert.equal(mesa.$('achados-versoes').classList.contains('versao-recolhida'), false);
  assert.equal(mesa.$('selecao-acervo').classList.contains('versao-recolhida'), false);
  assert.match(chip.textContent, /· fechar$/);
  mesa.$('rodada').value = 'R001';
  mesa.$('rodada').dispatchEvent(new mesa.janela.Event('change'));
  await mesa.assentar();
  assert.deepEqual(mesa.buscas().at(-1), 'R001/r2/g2');
  assert.equal(chip.textContent, 'Análise R001 · 02/11 · Revisão do suporte · trocar');
  assert.equal(chip.getAttribute('aria-expanded'), 'false');
});

test('fora de Achados o painel de análise não fica recolhido', async () => {
  const mesa = await abrir('?area=achados&caso=alfa');
  mesa.janela.showArea('documentos');
  assert.equal(mesa.$('selecao-acervo').classList.contains('versao-recolhida'), false);
});

for (const desktop of [true, false]) {
  test(`endereço com análise, etapa e versão prevalece sobre o padrão (${desktop ? 'desktop' : 'celular'})`, async () => {
    const mesa = await abrir('?area=achados&caso=alfa&rodada=R001&achados-revisao=r1&achados-geracao=g1', {desktop});
    assert.deepEqual(mesa.erros, []);
    assert.equal(mesa.$('rodada').value, 'R001');
    assert.equal(mesa.$('achados-revisao').value, 'r1');
    assert.equal(mesa.$('achados-geracao').value, 'g1');
    // The default never runs a search of its own when the address names the version.
    assert.deepEqual([...new Set(mesa.buscas())], ['R001/r1/g1']);
    assert.equal(mesa.$('achados-versao-chip').textContent, 'Análise R001 · 02/11 · Análise inicial · trocar');
  });
}

test('apuração sem análise mostra o que fazer, sem chip', async () => {
  const mesa = await abrir('?area=achados&caso=beta');
  assert.equal(mesa.$('achados-versao-chip').hidden, true);
  assert.deepEqual(mesa.buscas(), []);
  assert.equal(mesa.$('achados-status').textContent, 'Esta apuração ainda não tem análises. Faça uma pergunta em Perguntar à IA.');
});

test('em inglês o chip e os seletores saem traduzidos', async () => {
  const mesa = await abrir('?area=achados&caso=alfa', {idioma: 'en'});
  mesa.janela.I18N.aplicar(mesa.doc.body);
  assert.equal(mesa.$('achados-versao-chip').textContent, 'Analysis R003 · 12/11 · Support review · change');
  assert.equal(mesa.janela.I18N.traduzir('Revisão do suporte (r2)'), 'Support review (r2)');
  for (const texto of ['Selecione uma análise', 'Selecione a etapa', 'Selecione a versão', 'fechar',
    'Esta apuração ainda não tem análises. Faça uma pergunta em Perguntar à IA.']) assert.notEqual(mesa.janela.I18N.traduzir(texto), null, texto);
});

test('a interface não pede rodada, revisão ou geração', () => {
  const raiz = path.join(__dirname, '..', 'interface');
  const fonte = ['index.html', 'app.js'].map(nome => fs.readFileSync(path.join(raiz, nome), 'utf8')).join('\n');
  for (const jargao of ['Selecione uma rodada', 'Selecione a revisão', 'Selecione a geração', 'Selecione caso e rodada', 'Escolha uma rodada']) {
    assert.equal(fonte.includes(jargao), false, jargao);
  }
});
