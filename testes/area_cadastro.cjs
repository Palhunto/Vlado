'use strict';
// Cadastrar arquivos saiu (R4, passo 3): o aviso do extrator de PDF e o envio moram só em Documentos. Abrir Documentos (por qualquer caminho, inclusive o endereço
// antigo ?area=cadastro) reverifica o ambiente de PDF; sem o envio por arquivo no servidor, a própria Documentos envia em JSON para a apuração escolhida (F3 da
// Coruja). DOM sintético (dom_minimo), sem rede.
const test = require('node:test');
const assert = require('node:assert/strict');
const {criarMesa, Evento} = require('./dom_minimo.cjs');

const ALFA = {id: 'alfa', titulo: 'Pauta Alfa', rodadas: []};

async function abrir(ambiente, {fluxo = true, cadastrar = null} = {}) {
  const chamadas = [];
  const mesa = criarMesa({desktop: false, modo: 'local', idioma: 'pt', url: 'http://127.0.0.1:8765/?area=inicio&caso=alfa', catalogo: [ALFA],
    preparar: janela => {
      const original = janela.fetch;
      janela.fetch = async (endereco, opcoes) => {
        if (String(endereco) === '/api/integracao') return {ok: true, json: async () => (fluxo ? {envio_fluxo: true} : {})};
        return original(endereco, opcoes);
      };
    },
    api: (operacao, dados) => {
      if (operacao === 'ambiente') { chamadas.push(operacao); return ambiente(); }
      if (operacao === 'cadastrar' && cadastrar) return cadastrar(dados);
      return ({inventario: {caso_id: 'alfa', corpus_id: 'c1', documentos: [], total_documentos: 0}, 'diligencias-listar': {resultados: []}}[operacao] || {});
    }});
  await mesa.esperar(12);
  return {mesa, chamadas};
}

test('abrir Documentos reverifica o extrator de PDF e mostra o aviso quando ele ficou indisponível', async () => {
  let disponivel = true;
  const {mesa, chamadas} = await abrir(() => ({extracao_pdf: {disponivel}, ocr: {disponivel: true}}));
  mesa.janela.showArea('documentos');
  await mesa.esperar(6);
  assert.equal(mesa.$('docs-pdf-ambiente').hidden, true, 'com o extrator disponível, sem aviso');
  const antes = chamadas.length;
  disponivel = false;
  mesa.janela.showArea('inicio');
  mesa.janela.showArea('documentos');
  await mesa.esperar(6);
  assert.ok(chamadas.length > antes, 'o ambiente é consultado de novo ao abrir Documentos');
  assert.equal(mesa.$('docs-pdf-ambiente').hidden, false, 'o aviso aparece');
  assert.match(mesa.$('docs-pdf-ambiente-texto').textContent, /extrator de PDF está indisponível/);
});

test('só Documentos consulta o ambiente; o endereço antigo ?area=cadastro abre Documentos, e a área e o item da barra não existem mais', async () => {
  const {mesa, chamadas} = await abrir(() => ({extracao_pdf: {disponivel: true}, ocr: {disponivel: true}}));
  const base = chamadas.length;
  mesa.janela.showArea('inicio');
  await mesa.esperar(4);
  assert.equal(chamadas.length, base, 'outra área não consulta');
  mesa.janela.showArea('cadastro');
  await mesa.esperar(6);
  assert.equal(chamadas.length, base + 1, 'o endereço antigo abre Documentos');
  assert.equal(mesa.$('area-documentos').hidden, false);
  assert.equal(mesa.$('area-cadastro'), null); assert.equal(mesa.$('ver-cadastro'), null); assert.equal(mesa.$('cadastro'), null);
});

test('F3: sem o envio por arquivo no servidor, a Documentos de uma apuração existente envia em JSON (caso, novo:false), mostra o recibo e atualiza o inventário', async () => {
  let pedido = null;
  const {mesa} = await abrir(() => ({extracao_pdf: {disponivel: true}, ocr: {disponivel: true}}), {fluxo: false,
    cadastrar: dados => { pedido = dados; return {caso_id: 'alfa', corpus_id: 'c1', recebidos: 1, novos: 1, duplicados: 0, total_documentos: 1, arquivos: [{nome: 'novo.pdf', estado: 'pronto'}], inventario: {}}; }});
  mesa.janela.FileReader = class { readAsDataURL() { this.result = 'data:;base64,AAAA'; this.onload(); } };
  mesa.janela.showArea('documentos');
  await mesa.esperar(6);
  const evento = new Evento('drop', {bubbles: true, cancelable: true});
  evento.dataTransfer = {files: [{name: 'novo.pdf', size: 1024}]};
  mesa.$('documentos-zona').dispatchEvent(evento);
  await mesa.esperar(30);
  assert.ok(pedido, 'o envio em JSON saiu');
  assert.equal(pedido.caso, 'alfa'); assert.equal(pedido.novo, false);
  assert.deepEqual(pedido.arquivos, [{nome: 'novo.pdf', base64: 'AAAA'}]);
  assert.match(mesa.$('documentos-recibo').textContent, /Recibo do lote: 1 de 1 arquivos/);
  assert.equal(mesa.$('documentos-recibo').hidden, false);
  assert.match(mesa.$('mesa-acervo-status').textContent, /Documentos registrados\. Aguardando sua pergunta\./);
});

test('F3: o envio em JSON acima de 50 MB é recusado antes de sair, com a mesma frase de sempre', async () => {
  let saiu = false;
  const {mesa} = await abrir(() => ({extracao_pdf: {disponivel: true}, ocr: {disponivel: true}}), {fluxo: false, cadastrar: () => { saiu = true; return {}; }});
  mesa.janela.showArea('documentos');
  await mesa.esperar(6);
  const evento = new Evento('drop', {bubbles: true, cancelable: true});
  evento.dataTransfer = {files: [{name: 'enorme.pdf', size: 60 * 1024 * 1024}]};
  mesa.$('documentos-zona').dispatchEvent(evento);
  await mesa.esperar(10);
  assert.equal(saiu, false);
  assert.match(mesa.$('mesa-acervo-status').textContent, /O lote excede 50 MB\. Divida o envio em lotes menores; nenhum arquivo foi enviado\./);
});

test('o recibo do último envio acompanha "Perguntar aos documentos" (W02, regra 8): recolhido, sem ids repetidos, só se houve envio na visita, e some ao trocar de apuração', async () => {
  const BETA = {id: 'beta', titulo: 'Pauta Beta', rodadas: []};
  const mesa = criarMesa({desktop: false, modo: 'local', idioma: 'pt', url: 'http://127.0.0.1:8765/?area=documentos&caso=alfa', catalogo: [ALFA, BETA],
    preparar: janela => {
      const original = janela.fetch;
      janela.fetch = async (endereco, opcoes) => (String(endereco) === '/api/integracao' ? {ok: true, json: async () => ({})} : original(endereco, opcoes));
      janela.FileReader = class { readAsDataURL() { this.result = 'data:;base64,AAAA'; this.onload(); } };
    },
    api: operacao => ({'cadastrar': {caso_id: 'alfa', corpus_id: 'c1', recebidos: 1, novos: 1, duplicados: 0, total_documentos: 1, arquivos: [{nome: 'novo.pdf', estado: 'pronto'}], inventario: {}},
      inventario: {caso_id: 'alfa', corpus_id: 'c1', documentos: [], total_documentos: 0}, 'codex-listar': {conversas: []}}[operacao] || {})});
  await mesa.esperar(12);
  const alerta = mesa.$('codex-recibo-alerta');
  mesa.$('mesa-perguntar').click(); await mesa.esperar(6);
  assert.equal(alerta.hidden, true, 'sem envio na visita, a Pergunta abre sem o recibo');
  const evento = new Evento('drop', {bubbles: true, cancelable: true}); evento.dataTransfer = {files: [{name: 'novo.pdf', size: 1024}]};
  mesa.$('documentos-zona').dispatchEvent(evento);
  await mesa.esperar(30);
  mesa.janela.showArea('documentos');
  mesa.$('mesa-perguntar').click(); await mesa.esperar(6);
  assert.equal(alerta.hidden, false); assert.ok(!alerta.open, 'recolhido');
  assert.equal(alerta.querySelector('summary').textContent, 'Recibo do último envio · confira as limitações antes de perguntar');
  assert.match(alerta.textContent, /Recibo do lote: 1 de 1 arquivos/);
  assert.equal(alerta.querySelectorAll('[id]').length, 0, 'sem ids repetidos');
  assert.ok(mesa.$('documentos-recibo'), 'o recibo da Documentos continua');
  mesa.janela.definirContextoCaso('beta', {force: true}); await mesa.esperar(10);
  assert.equal(alerta.hidden, true, 'trocar de apuração tira o recibo');
  assert.equal(mesa.$('documentos-recibo').hidden, true);
});
