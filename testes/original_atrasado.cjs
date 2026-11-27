'use strict';
// Original que chega atrasado (revisao.js): o original pedido na conferência de um achado não abre por cima de outra conferência, nem é registrado como "conferido",
// se a pessoa fechou ou trocou a conferência enquanto o servidor respondia. O mesmo id de evidência (E001) existe em várias rodadas e revisões, então registrar com o
// escopo anterior marcaria como aberto o original de outro achado. Dados sintéticos; o servidor é uma promessa que o teste resolve quando quiser.
const test = require('node:test');
const assert = require('node:assert/strict');
const {criarMesa} = require('./dom_minimo.cjs');

const ALFA = {id: 'alfa', titulo: 'Pauta Alfa', rodadas: [{id: 'R001', geracoes: []}, {id: 'R002', geracoes: []}]};
const ESCOPO_A = {caso: 'alfa', rodada: 'R001', revisao: 'r2', geracao_achados: 'g1'};
const ESCOPO_B = {caso: 'alfa', rodada: 'R002', revisao: 'r2', geracao_achados: 'g1'};
const evidencia = id => ({id, documento_id: 'D1', original: 'casos/alfa/D1_contrato.pdf', original_sha256: 'h1', trecho: `Trecho ${id}.`,
  localizador: {tipo: 'linhas', pagina_pdf: 12, linha_inicio: 3, linha_fim: 4}, modo: 'texto', contexto: ''});
const achado = redacao => ({id: 'A001', versao: 1, redacao, natureza: 'declaracao_documental', suporte: 'sustentado',
  revisao_humana: {estado: 'pendente', observacao: '', evento_id: null, historico: []}, vinculos: [{evidencia_id: 'E001', papel: 'suporte'}], evidencias: [evidencia('E001')]});
const adiada = () => { let resolver; const promessa = new Promise(r => { resolver = r; }); return {promessa, resolver}; };

async function montar() {
  const originais = [];   // uma promessa por pedido de achados-original, na ordem em que a tela os faz
  const mesa = criarMesa({catalogo: [ALFA], url: 'http://127.0.0.1:8765/?area=achados&caso=alfa', preparar: janela => {
    janela.fetch = async (rota, opcoes = {}) => {
      if (String(rota) === '/api/catalogo') return {ok: true, json: async () => ({casos: [ALFA]})};
      const op = String(rota).replace(/^\/api\//, ''), dados = opcoes.body ? JSON.parse(opcoes.body) : {};
      if (op === 'achados-detalhe') return {ok: true, status: 200, json: async () => ({achado: achado(dados.rodada === 'R002' ? 'Achado da rodada B.' : 'Achado da rodada A.'), registros_sha256: 'hash'})};
      if (op === 'achados-evidencia') return {ok: true, status: 200, json: async () => ({contexto: [{linha: 3, texto: 'Contexto.'}], evidencia: {}})};
      if (op === 'achados-original') { const d = adiada(); originais.push(d); await d.promessa; return {ok: true, status: 200, blob: async () => ({type: 'application/pdf'})}; }
      if (op === 'inventario') return {ok: true, status: 200, json: async () => ({caso_id: 'alfa', corpus_id: 'c1', documentos: [], total_documentos: 0})};
      return {ok: true, status: 200, json: async () => ({})};
    };
  }});
  await mesa.esperar(12);
  const abrir = async escopo => { await mesa.janela.conferirAchado(achado('x'), escopo, mesa.avaliar('findingEpoch')); await mesa.esperar(8); };
  return {mesa, originais, abrir};
}
const bloco = mesa => mesa.$('revisao-fontes').querySelector('[data-evidencia="E001"]');
const opcao = mesa => mesa.$('revisao-estado').querySelector('[value="conferida_no_original"]');

test('conferência trocada enquanto o original vinha: nada abre por cima da outra e a outra continua exigindo o original', async () => {
  const {mesa, originais, abrir} = await montar();
  await abrir(ESCOPO_A);
  bloco(mesa).querySelector('button').click(); await mesa.esperar(8);
  assert.equal(originais.length, 1, 'o pedido do original da conferência A está em espera');
  await abrir(ESCOPO_B);                       // a pessoa abre outro achado (a mesma E001, em outra rodada)
  assert.match(mesa.$('revisao-afirmacao').textContent, /rodada B/);
  originais[0].resolver(); await mesa.esperar(10);
  assert.equal(mesa.$('original-dialogo').open, false, 'o original da conferência A não abre por cima da B');
  assert.equal(opcao(mesa).disabled, true, 'a conferência B ainda exige abrir o próprio original');
  assert.match(mesa.$('revisao-guarda').textContent, /falta 1/);
  assert.deepEqual(mesa.erros, []);
});

test('conferência fechada enquanto o original vinha: o original não abre', async () => {
  const {mesa, originais, abrir} = await montar();
  await abrir(ESCOPO_A);
  bloco(mesa).querySelector('button').click(); await mesa.esperar(8);
  mesa.$('revisao-dialogo').open = false;
  originais[0].resolver(); await mesa.esperar(10);
  assert.equal(mesa.$('original-dialogo').open, false);
});

test('sem troca, o original abre e a conferência libera "Conferida no original"', async () => {
  const {mesa, originais, abrir} = await montar();
  await abrir(ESCOPO_A);
  assert.equal(opcao(mesa).disabled, true);
  bloco(mesa).querySelector('button').click(); await mesa.esperar(8);
  originais[0].resolver(); await mesa.esperar(10);
  assert.equal(mesa.$('original-dialogo').open, true, 'abriu');
  assert.equal(opcao(mesa).disabled, false, 'o original aberto foi registrado');
});
