'use strict';
// Regressions from the integrated review that touch the Caderno's neighbours: the original viewer
// (a slower, older opening must not overwrite a newer one, and every blob URL is released) and the
// conversation event loop (an event that fails to render must not hold the cursor back).
const test = require('node:test');
const assert = require('node:assert/strict');
const {criarMesa} = require('./dom_minimo.cjs');

const ALFA = {id: 'alfa', titulo: 'Pauta Alfa', rodadas: [{id: 'R001', geracoes: []}]};

async function mesaOriginal() {
  const revogados = [];
  let criados = 0;
  const mesa = criarMesa({catalogo: [ALFA], url: 'http://127.0.0.1:8765/?area=apuracao&caso=alfa',
    api: op => (op === 'apuracao-notas' ? {caso: 'alfa', revisao_caderno: 1, notas: []} : {}),
    preparar: janela => {
      janela.URL.createObjectURL = () => `blob:teste-${++criados}`;
      janela.URL.revokeObjectURL = url => revogados.push(url);
    }});
  await mesa.esperar(12);
  return {mesa, revogados, criados: () => criados};
}

test('original de texto: abertura antiga e lenta não sobrescreve a nova e libera sua URL', async () => {
  const {mesa, revogados} = await mesaOriginal();
  let liberar;
  const lento = {type: 'text/plain', text: () => new Promise(ok => { liberar = () => ok('TEXTO ANTIGO'); })};
  const rapido = {type: 'text/plain', text: async () => 'TEXTO NOVO'};
  const primeira = mesa.janela.abrirOriginal(lento, 'a.txt');
  await mesa.janela.abrirOriginal(rapido, 'b.txt');
  liberar(); await primeira;
  assert.equal(mesa.$('original-conteudo').textContent, 'TEXTO NOVO');
  assert.deepEqual(revogados, ['blob:teste-1'], 'a URL da primeira abertura é liberada');
  mesa.$('original-dialogo').close?.();
  mesa.janela.fecharOriginal();
  assert.ok(revogados.includes('blob:teste-2'));
});

test('original que falha ao ler libera a URL e avisa quem chamou', async () => {
  const {mesa, revogados} = await mesaOriginal();
  const quebrado = {type: 'text/plain', text: async () => { throw new Error('leitura falhou'); }};
  await assert.rejects(mesa.janela.abrirOriginal(quebrado, 'c.txt'), /leitura falhou/);
  assert.deepEqual(revogados, ['blob:teste-1']);
});

test('evento que falha ao desenhar não segura o cursor: a reconexão não repete eventos', async () => {
  const cursores = [];
  let rodada = 0;
  const mesa = criarMesa({catalogo: [ALFA], url: 'http://127.0.0.1:8765/?area=codex&caso=alfa', api: (op, dados) => {
    if (op === 'codex-listar') return {conversas: [{id: 'chat1', titulo: 'Conversa', estado: 'em_andamento'}]};
    if (op === 'codex-eventos') {
      cursores.push(dados.cursor);
      rodada++;
      if (rodada === 1) return {conversa: {id: 'chat1', estado: 'concluido'}, cursor: 2, acervos: {},
        eventos: [{tipo: 'pergunta', dados: {texto: 'Quanto custou?'}}, {tipo: 'fonte', dados: null}]};
      return {conversa: {id: 'chat1', estado: 'concluido'}, cursor: 2, acervos: {}, eventos: []};
    }
    if (op === 'inventario') return {caso_id: 'alfa', corpus_id: 'c1', documentos: [], total_documentos: 0};
    return {};
  }});
  await mesa.esperar(12);
  mesa.$('codex-conversa').value = 'chat1';
  mesa.$('codex-conversa').dispatchEvent(new mesa.janela.Event('change'));
  await mesa.esperar(20);
  assert.equal(mesa.$('codex-reconectar').hidden, false, 'a falha de desenho aparece como falha de acompanhamento');
  mesa.$('codex-reconectar').click();
  await mesa.esperar(20);
  assert.ok(cursores.length >= 2, 'reconectou');
  assert.equal(cursores.at(-1), 2, 'segue do cursor depois dos eventos já recebidos');
});
