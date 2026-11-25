'use strict';
// P48: o destino editorial "fora_do_briefing" (achado sustentado que não coube no texto do briefing, nunca retirado) aparece na Mesa com o rótulo
// "Fora do briefing (sustentado)", tem opção no filtro de destino e, no inglês, "Outside the briefing (supported)". O selo do achado é o de sustentado
// (vem da revisão), nunca o de retirado, e o cartão não diz "Incluído no briefing.".
const test = require('node:test');
const assert = require('node:assert/strict');
const {criarMesa} = require('./dom_minimo.cjs');

const ALFA = {id: 'alfa', titulo: 'Pauta Alfa', rodadas: [{id: 'R001', geracoes: ['v1']}]};
const FORA = {id: 'A002', versao: 1, natureza: 'declaracao_documental', redacao: 'O contrato foi aditado duas vezes.', suporte: 'sustentado',
  vinculos: [], evidencias: [], limitacoes: '', subquestao: 'Pergunta', destino: 'fora_do_briefing', briefing: 'briefing.md', conferencia_humana: 'nao_realizada',
  verificacao_externa: {estado: 'nao_realizada', limitacao: ''},
  historico: {versoes: [], revisoes_assistidas: [], conferencias_humanas: [],
    destinos: [{versao: 1, destino: 'fora_do_briefing', motivo: 'Não coube no texto principal.', briefing: 'briefing.md'}]}};
const INCLUIDO = {...FORA, id: 'A001', redacao: 'O contrato foi assinado em 2024.', destino: 'incluido',
  historico: {...FORA.historico, destinos: [{versao: 1, destino: 'incluido', motivo: 'Cabe no texto.', briefing: 'briefing.md'}]}};
const respostas = {
  'codex-listar': {conversas: []},
  inventario: {caso_id: 'alfa', corpus_id: 'c1', documentos: [], total_documentos: 0},
  analises: {analises: []},
  'achados-catalogo': {estado: 'disponivel', revisoes: ['r1'], indices: [{revisao: 'r1', geracao: 'g1'}]},
  'achados-buscar': {resultados: [INCLUIDO, FORA], documentos: [], artefatos: [{tipo: 'briefing', arquivo: 'briefing.md', sha256: 'abc'}],
    total_correspondencias: 2, retornados: 2, deslocamento: 0, proximo_deslocamento: null, estado: 'disponivel', revisoes_sucessoras: [], registros_sha256: 'sintetico'},
  'codex-eventos': {conversa: {estado: 'concluido'}, eventos: [], cursor: 0},
};

async function abrir(idioma) {
  const mesa = criarMesa({idioma, armazenamento: {'vlado-idioma': idioma}, catalogo: [ALFA], api: operacao => respostas[operacao] || {},
    url: 'http://127.0.0.1:8765/?area=achados&caso=alfa'});
  await new Promise(resolve => setTimeout(resolve, 200));
  await mesa.esperar(12);
  return mesa;
}
async function abrirFora(mesa) {
  const botoes = [...mesa.$('achados-resultados').querySelectorAll('.finding-open')];
  assert.equal(botoes.length, 2);
  botoes[1].click();
  await mesa.esperar(4);
  return mesa.$('achados-inspecao');
}

test('em português: rótulo, selo de sustentado e nenhuma marca de retirado ou de incluído', async () => {
  const mesa = await abrir('pt');
  assert.deepEqual(mesa.erros, []);
  const lista = mesa.$('achados-resultados').querySelectorAll('.finding-choice')[1];
  assert.ok(lista.querySelector('.support-badge.support-sustentado'), 'selo de sustentado na lista');
  const cartao = await abrirFora(mesa);
  const texto = cartao.textContent;
  assert.ok(texto.includes('Destino editorial: Fora do briefing (sustentado)'), texto);
  assert.ok(cartao.querySelector('.support-badge.support-sustentado'), 'selo de sustentado no cartão');
  assert.ok(!cartao.querySelector('.support-nao_sustentado'), 'não é o selo de não sustentado');
  assert.ok(!/retirad/i.test(texto), 'não é marcado como retirado');
  assert.ok(!texto.includes('Incluído no briefing.'), 'não diz que está incluído');
  assert.ok(texto.includes('Sustentado, fora do texto do briefing'), texto);
  assert.ok(texto.includes('Destino · v1 · Fora do briefing (sustentado)'), 'o histórico usa o mesmo rótulo');
  assert.ok([...cartao.querySelectorAll('button')].some(b => b.textContent === 'Ver briefing e referências'), 'o briefing continua acessível');
});

test('o achado incluído continua dizendo "Incluído no briefing."', async () => {
  const mesa = await abrir('pt');
  const botoes = [...mesa.$('achados-resultados').querySelectorAll('.finding-open')];
  botoes[0].click(); await mesa.esperar(4);
  const texto = mesa.$('achados-inspecao').textContent;
  assert.ok(texto.includes('Incluído no briefing.') && !texto.includes('Fora do briefing'), texto);
});

test('o filtro de destino tem a opção e o filtro "no briefing" segue só com o incluído', () => {
  const mesa = criarMesa({catalogo: [ALFA]});
  const opcoes = [...mesa.$('achados-destino').querySelectorAll('option')].map(o => [o.value, o.textContent]);
  assert.deepEqual(opcoes.find(([valor]) => valor === 'fora_do_briefing'), ['fora_do_briefing', 'Fora do briefing (sustentado)']);
  assert.deepEqual([...mesa.$('achados-briefing').querySelectorAll('option')].map(o => o.value), ['', 'sim', 'nao']);
});

test('em inglês: "Outside the briefing (supported)" para o rótulo, a opção do filtro e a linha do cartão', async () => {
  const mesa = await abrir('en');
  await mesa.esperar(6);
  const {t} = mesa.janela.I18N;
  assert.equal(t('Fora do briefing (sustentado)'), 'Outside the briefing (supported)');
  assert.equal(t('Sustentado, fora do texto do briefing; consta na lista de outros achados sustentados.'),
    'Supported, outside the briefing text; listed among the other supported findings.');
  // os textos que a tela realmente escreve são chaves da tradução
  const cartao = await abrirFora(mesa);
  const rotulo = [...cartao.querySelectorAll('p')].find(p => p.textContent.startsWith('Destino editorial:'));
  assert.ok(rotulo.textContent.endsWith('Fora do briefing (sustentado)'));
  const opcao = [...mesa.$('achados-destino').querySelectorAll('option')].find(o => o.value === 'fora_do_briefing');
  assert.equal(t(opcao.textContent), 'Outside the briefing (supported)');
  assert.ok(!/'/.test('Outside the briefing (supported)'), 'sem apóstrofo reto no inglês');
});

test('em inglês: o achado incluído diz "Included in the briefing."', async () => {
  const mesa = await abrir('en');
  await mesa.esperar(6);
  const botoes = [...mesa.$('achados-resultados').querySelectorAll('.finding-open')];
  botoes[0].click(); await mesa.esperar(4);
  const linha = [...mesa.$('achados-inspecao').querySelectorAll('p')].find(p => p.textContent === 'Incluído no briefing.');
  assert.ok(linha, 'a frase em português é a chave que a tela escreve');
  assert.equal(mesa.janela.I18N.t(linha.textContent), 'Included in the briefing.');
});
