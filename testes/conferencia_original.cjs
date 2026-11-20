'use strict';
// "Conferida no original": the server refuses it when this page session did not open every cited
// original (it keeps that only in memory). The screen then marks those excerpts as pending again.
const test = require('node:test');
const assert = require('node:assert/strict');
const {criarMesa} = require('./dom_minimo.cjs');

const ALFA = {id: 'alfa', titulo: 'Pauta Alfa', rodadas: [{id: 'R001', geracoes: []}]};
const ESCOPO = {caso: 'alfa', rodada: 'R001', revisao: 'r2', geracao_achados: 'g1'};
const evidencia = (id, pagina) => ({id, documento_id: 'D1', original: 'casos/alfa/D1_contrato.pdf', original_sha256: 'h1',
  trecho: `Trecho ${id}.`, localizador: {tipo: 'linhas', pagina_pdf: pagina, linha_inicio: 3, linha_fim: 4}, modo: 'texto', contexto: ''});
function achado(estado = 'pendente') {
  return {id: 'A001', versao: 1, redacao: 'O contrato vale R$ 10 mil.', natureza: 'declaracao_documental', suporte: 'sustentado',
    revisao_humana: {estado, observacao: '', evento_id: estado === 'pendente' ? null : 'e'.repeat(32), historico: []},
    vinculos: [{evidencia_id: 'E001', papel: 'suporte'}, {evidencia_id: 'E002', papel: 'suporte'}],
    evidencias: [evidencia('E001', 12), evidencia('E002', 13)]};
}
const RECUSA = {estado: 'erro', codigo: 'conferencia_sem_original',
  erro: 'Para marcar “Conferida no original”, abra antes o original de cada trecho citado (faltam: E001, E002).', faltam: ['E001', 'E002']};

async function abrir({estado = 'pendente', salvar} = {}) {
  const chamadas = [];
  const mesa = criarMesa({catalogo: [ALFA], url: 'http://127.0.0.1:8765/?area=achados&caso=alfa', preparar: janela => {
    janela.fetch = async (rota, opcoes = {}) => {
      if (String(rota) === '/api/catalogo') return {ok: true, json: async () => ({casos: [ALFA]})};
      const op = String(rota).replace(/^\/api\//, ''), dados = opcoes.body ? JSON.parse(opcoes.body) : {};
      chamadas.push({op, dados});
      let resposta = {};
      if (op === 'achados-detalhe') resposta = {achado: achado(estado), registros_sha256: 'hash'};
      if (op === 'achados-evidencia') resposta = {contexto: [{linha: 3, texto: 'Contexto.'}], evidencia: {}};
      if (op === 'achados-original') resposta = {type: 'application/pdf'};
      if (op === 'achados-revisao-salvar') resposta = salvar ? salvar(dados) : {estado: 'registrado', revisao_humana: {estado: dados.estado}};
      if (op === 'inventario') resposta = {caso_id: 'alfa', corpus_id: 'c1', documentos: [], total_documentos: 0};
      if (resposta.estado === 'erro') return {ok: false, status: 400, json: async () => resposta};
      return {ok: true, status: 200, blob: async () => resposta, json: async () => resposta};
    };
  }});
  await mesa.esperar(12);
  await mesa.janela.conferirAchado(achado(estado), ESCOPO, mesa.avaliar('findingEpoch'));
  await mesa.esperar(8);
  return {mesa, chamadas};
}
const bloco = (mesa, id) => mesa.$('revisao-fontes').querySelector(`[data-evidencia="${id}"]`);
const opcao = mesa => mesa.$('revisao-estado').querySelector('[value="conferida_no_original"]');
async function abrirOriginais(mesa) {
  for (const id of ['E001', 'E002']) {
    bloco(mesa, id).querySelector('button').click();
    await mesa.esperar(8);
    mesa.$('original-dialogo').close();
  }
}

test('recusa do servidor marca de novo como pendentes os trechos listados em faltam', async () => {
  const {mesa} = await abrir({salvar: () => RECUSA});
  await abrirOriginais(mesa);
  assert.equal(opcao(mesa).disabled, false, 'a trava da tela libera depois de abrir os originais');
  mesa.$('revisao-estado').value = 'conferida_no_original';
  mesa.$('revisao-form').requestSubmit();
  await mesa.esperar(8);
  assert.equal(mesa.$('revisao-erro').hidden, false);
  assert.equal(mesa.$('revisao-erro').textContent, RECUSA.erro);
  for (const id of ['E001', 'E002']) {
    assert.ok(bloco(mesa, id).classList.contains('review-evidence-pendente'), id);
    assert.match(bloco(mesa, id).querySelector('.review-pendente').textContent, /Abra este original/);
  }
  assert.equal(opcao(mesa).disabled, true, 'volta a exigir os originais');
  assert.match(mesa.$('revisao-guarda').textContent, /faltam 2/);
  assert.equal(mesa.$('revisao-dialogo').open, true);
  bloco(mesa, 'E001').querySelector('button').click();
  await mesa.esperar(8);
  assert.equal(bloco(mesa, 'E001').classList.contains('review-evidence-pendente'), false, 'abrir de novo tira o destaque');
  assert.equal(bloco(mesa, 'E001').querySelector('.review-pendente'), null);
});

test('achado já conferido: editar só a observação não exige reabrir os originais', async () => {
  const {mesa, chamadas} = await abrir({estado: 'conferida_no_original'});
  assert.equal(mesa.$('revisao-estado').value, 'conferida_no_original');
  assert.equal(opcao(mesa).disabled, false);
  assert.equal(mesa.$('revisao-guarda').hidden, true);
  mesa.$('revisao-observacao').value = 'Valor confere com a cláusula 2.';
  mesa.$('revisao-form').requestSubmit();
  await mesa.esperar(8);
  const pedido = chamadas.find(c => c.op === 'achados-revisao-salvar').dados;
  assert.equal(pedido.estado, 'conferida_no_original');
  assert.equal(pedido.observacao, 'Valor confere com a cláusula 2.');
});
