'use strict';
// A tela do convidado só pede o que o papel pode fazer: toda operação recusada vira uma linha `operacao_negada` no registro de acessos, e o
// cabeçalho dele não pode virar "Acervo indisponível" porque o inventário foi recusado. Lista conferida com OPERACOES_CONVIDADO em
// scripts/rotas_contas.py. DOM sintético (dom_minimo), sem rede.
const test = require('node:test');
const assert = require('node:assert/strict');
const {criarMesa} = require('./dom_minimo.cjs');

const ALFA = {id: 'alfa', titulo: 'Pauta Alfa', rodadas: []};
const SO_ADMINISTRADOR = ['ambiente', 'ia-config', 'analises', 'gerenciar-listar', 'inventario', 'apuracao-notas', 'diligencias-listar', 'caderno-listar'];

async function abrir(papel, desktop) {
  const operacoes = [];
  const respostas = {'codex-listar': {conversas: []}, 'codex-status': {autenticado: true, provedor: 'anthropic', modelo: 'modelo-teste'},
    inventario: {caso_id: 'alfa', corpus_id: 'c1', documentos: [], total_documentos: 0}, ambiente: {}, 'diligencias-listar': {resultados: []}};
  const mesa = criarMesa({papel, modo: 'piloto', idioma: 'pt', desktop, url: 'http://127.0.0.1:8765/?area=codex&caso=alfa', catalogo: [ALFA],
    api: operacao => { operacoes.push(operacao); return respostas[operacao] || {}; }});
  await mesa.esperar(30);
  return {mesa, operacoes};
}

for (const desktop of [false, true]) {
  test(`convidado não pede operações que o servidor recusa na carga (${desktop ? 'desktop' : 'celular'}) e o cabeçalho segue o de sempre`, async () => {
    const {mesa, operacoes} = await abrir('convidado', desktop);
    assert.deepEqual(operacoes.filter(op => SO_ADMINISTRADOR.includes(op)), [], 'pedidos que o papel não pode fazer');
    assert.ok(operacoes.includes('codex-listar'), 'a conversa continua carregando');
    assert.equal(mesa.$('mesa-versao').textContent, 'Documentos, achados e fontes');
  });
}

test('administrador segue pedindo inventário e a lista de diligências', async () => {
  const {operacoes} = await abrir('admin', true);
  assert.ok(operacoes.includes('inventario'));
  assert.ok(operacoes.includes('diligencias-listar'));
});
