'use strict';
// Quadro vazio deixa criar o primeiro item (defeito achado nos casos reais: o estado vazio só tinha "Fazer uma pergunta", então "Nova hipótese", nova
// entidade e nova tabela nunca apareciam num caso com rodadas e achados publicados, mas sem itens nem sugestões). O estado vazio traz as duas ações,
// criar o primeiro item (principal) e fazer uma pergunta; o formulário abre no painel do quadro. Dados sintéticos.
const test = require('node:test');
const assert = require('node:assert/strict');
const {criarMesa, PILHA} = require('./dom_minimo.cjs');

const VAZIOS = {
  'hipoteses-quadro': {caso: 'alpha', total: 0, divergentes: [], aviso: '', hipoteses: []},
  'mapa-ver': {caso: 'alpha', aviso: '', homonimos: [], relacoes: [], entidades: []},
  'linha-tempo-listar': {caso: 'alpha', total: 0, divergencias: [], fontes_indisponiveis: [], divergentes: [], tipos_data: {fato: 'Data do fato (ocorrência)'}, aviso: '', entradas: []},
  'tabelas-listar': {caso: 'alpha', total: 0, divergentes: [], aviso: '', tabelas: []},
  'sugestoes-listar': {caso: 'alpha', quadro: 'x', contagem: {}, sugestoes: []}};
function montar({rodadas = [{id: 'R001', geracoes: ['g1']}], permissao = true} = {}) {
  const m = criarMesa({scripts: [...PILHA, 'quadros.js', 'sugestoes.js', 'formularios.js', 'analise.js', 'indicador_salvamento.js'], desktop: true,
    catalogo: [{id: 'alpha', titulo: 'Alfa', rodadas}],
    api: operacao => VAZIOS[operacao] ?? {},
    preparar: janela => {
      const original = janela.fetch;
      janela.fetch = async (rota, opcoes) => String(rota) === '/api/integracao' ? {ok: true, json: async () => ({quadros_evidencia: true, tabelas_apuracao: true})} : original(rota, opcoes);
    }});
  m.avaliar('window.contextoCaso = () => "alpha";');
  if (!permissao) m.avaliar('window.Sessao = {pode: () => false, pronta: Promise.resolve()};');
  return m;
}
const espera = async m => { await new Promise(r => setTimeout(r, 12)); await m.esperar(10); };
const texto = no => no.textContent.replace(/\s+/g, ' ').trim();
async function abrirAba(m, aba) { m.$('ver-quadros').click(); await espera(m); m.$(`quadros-aba-${aba}`).click(); await espera(m); }
const acoes = painel => [...painel.querySelectorAll('.estado-bloco .estado-acoes button')];

const CASOS = [['hipoteses', 'Nenhuma hipótese ainda', 'Criar a primeira hipótese', /Nova hipótese|Hipótese/], ['mapa', 'Nenhuma ligação ainda', 'Criar a primeira entidade', /Nova entidade/],
  ['tempo', 'Nenhum acontecimento com data ainda', 'Adicionar acontecimento', /Novo acontecimento/], ['tabelas', 'Nenhuma tabela ainda', 'Criar a primeira tabela', /Nova tabela/]];

for (const [aba, titulo, criar, formulario] of CASOS) {
  test(`${aba}: o estado vazio traz criar o primeiro item (principal) e fazer uma pergunta, e o formulário abre`, async () => {
    const m = montar(); await abrirAba(m, aba);
    const painel = m.$(`quadros-${aba}`);
    assert.match(texto(painel.querySelector('.estado-titulo')), new RegExp(titulo));
    const botoes = acoes(painel);
    assert.deepEqual(botoes.map(texto), [criar, 'Fazer uma pergunta'], 'as duas ações, a de criar primeiro');
    assert.ok(!botoes[0].classList.contains('secondary'), 'criar é a ação principal');
    assert.ok(botoes[1].classList.contains('secondary'), 'perguntar é a secundária');
    botoes[0].click(); await espera(m);
    assert.ok(painel.querySelector('.form-quadro'), 'o formulário abre no painel do quadro');
    assert.match(texto(painel.querySelector('.form-titulo')), formulario);
    assert.deepEqual(m.erros, []);
  });

  test(`${aba}: sem a capacidade de criar, o estado vazio fica só com "Fazer uma pergunta"`, async () => {
    const m = montar({permissao: false}); await abrirAba(m, aba);
    assert.deepEqual(acoes(m.$(`quadros-${aba}`)).map(texto), ['Fazer uma pergunta']);
  });
}

test('linha do tempo: sem análise na apuração não há de onde ligar evidência, então só "Fazer uma pergunta"', async () => {
  const m = montar({rodadas: []}); await abrirAba(m, 'tempo');
  assert.deepEqual(acoes(m.$('quadros-tempo')).map(texto), ['Fazer uma pergunta']);
});

test('o quadro vazio de hipóteses e de tabelas cria sem análise (o enunciado e o título bastam)', async () => {
  for (const aba of ['hipoteses', 'tabelas']) {
    const m = montar({rodadas: []}); await abrirAba(m, aba);
    assert.equal(acoes(m.$(`quadros-${aba}`)).length, 2, aba);
  }
});
