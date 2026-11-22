'use strict';
// showArea e seus ganchos (app.js): os ganchos de "forçar" rodam todos, na ordem de registro, e os de "depois" (rota, abas) recebem o nome
// já forçado, para o endereço (?area=), as abas e a tela mostrada nunca divergirem. DOM sintético (dom_minimo), sem rede.
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
const rota = mesa => new URL(mesa.janela.location.href).searchParams.get('area');
const telaVisivel = mesa => ['inicio', 'documentos', 'codex', 'achados', 'apuracao', 'diligencias', 'quadros'].filter(nome => !mesa.$('area-' + nome).hidden);

test('o gancho de forçar troca a tela e o endereço acompanha a tela mostrada', async () => {
  const mesa = await abrir();
  mesa.janela.registrarGanchoArea({forcar: () => 'codex'});
  mesa.janela.showArea('apuracao');
  await mesa.esperar(4);
  assert.deepEqual(telaVisivel(mesa), ['codex']);
  assert.equal(rota(mesa), 'codex', 'o endereço não pode seguir o nome pedido');
  assert.equal(mesa.$('caderno-abas').hidden, true, 'as abas do caderno não aparecem na conversa');
});

test('dois ganchos de forçar valem os dois, na ordem de registro, e os de depois recebem o nome final', async () => {
  const mesa = await abrir();
  const vistos = [];
  mesa.janela.registrarGanchoArea({forcar: nome => (nome === 'apuracao' ? 'diligencias' : nome)});
  mesa.janela.registrarGanchoArea({forcar: nome => (nome === 'diligencias' ? 'quadros' : nome)});
  mesa.janela.registrarGanchoArea({depois: nome => vistos.push(nome)});
  mesa.janela.showArea('apuracao');
  assert.deepEqual(telaVisivel(mesa), ['quadros'], 'o segundo gancho ainda enxerga o resultado do primeiro');
  assert.deepEqual(vistos, ['quadros']);
});

test('sem gancho de forçar, a tela e o endereço seguem o pedido', async () => {
  const mesa = await abrir();
  mesa.janela.showArea('diligencias');
  await mesa.esperar(4);
  assert.deepEqual(telaVisivel(mesa), ['diligencias']);
  assert.equal(rota(mesa), 'diligencias');
});
