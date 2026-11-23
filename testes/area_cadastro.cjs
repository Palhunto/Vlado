'use strict';
// Abrir a área Cadastrar arquivos (por qualquer caminho: aba de Documentos, Visão geral, trilha de etapas) reverifica o ambiente de PDF e atualiza
// o aviso #pdf-ambiente-aviso; o item da barra que antes disparava isso saiu da barra. DOM sintético (dom_minimo), sem rede.
const test = require('node:test');
const assert = require('node:assert/strict');
const {criarMesa} = require('./dom_minimo.cjs');

const ALFA = {id: 'alfa', titulo: 'Pauta Alfa', rodadas: []};

async function abrir(ambiente) {
  const chamadas = [];
  const mesa = criarMesa({desktop: false, modo: 'local', idioma: 'pt', url: 'http://127.0.0.1:8765/?area=inicio&caso=alfa', catalogo: [ALFA],
    api: operacao => {
      if (operacao === 'ambiente') { chamadas.push(operacao); return ambiente(); }
      return ({inventario: {caso_id: 'alfa', corpus_id: 'c1', documentos: [], total_documentos: 0}, 'diligencias-listar': {resultados: []}}[operacao] || {});
    }});
  await mesa.esperar(12);
  return {mesa, chamadas};
}

test('abrir Cadastro reverifica o extrator de PDF e mostra o aviso quando ele ficou indisponível', async () => {
  let disponivel = true;
  const {mesa, chamadas} = await abrir(() => ({extracao_pdf: {disponivel}, ocr: {disponivel: true}}));
  assert.equal(mesa.$('pdf-ambiente-aviso').hidden, true, 'com o extrator disponível, sem aviso');
  const antes = chamadas.length;
  disponivel = false;
  mesa.janela.showArea('cadastro');
  await mesa.esperar(6);
  assert.ok(chamadas.length > antes, 'o ambiente é consultado de novo ao abrir Cadastro');
  assert.equal(mesa.$('pdf-ambiente-aviso').hidden, false, 'o aviso aparece');
  assert.match(mesa.$('pdf-ambiente-aviso').textContent, /extrator de PDF está indisponível/);
});

test('cada abertura de Cadastro e de Documentos consulta o ambiente (o aviso do extrator mora nas duas), e as outras áreas não', async () => {
  const {mesa, chamadas} = await abrir(() => ({extracao_pdf: {disponivel: true}, ocr: {disponivel: true}}));
  const base = chamadas.length;
  mesa.janela.showArea('inicio');
  await mesa.esperar(4);
  assert.equal(chamadas.length, base, 'outra área não consulta');
  mesa.janela.showArea('documentos');
  await mesa.esperar(4);
  assert.equal(chamadas.length, base + 1, 'Documentos tem o cartão do extrator (R4)');
  mesa.janela.showArea('cadastro');
  await mesa.esperar(4);
  mesa.janela.showArea('inicio');
  mesa.janela.showArea('cadastro');
  await mesa.esperar(4);
  assert.equal(chamadas.length, base + 3);
});
