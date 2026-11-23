'use strict';
// Cabeçalho do celular (docs/design/componentes.md#cabecalho-celular): abaixo de 720 px "Configurações" vai para a gaveta, como a primeira do grupo, e a cota curta
// ("R$ 18,40 de 50", "! Cota esgotada") aparece à direita; a partir de 720 px os botões voltam ao cabeçalho na ordem de sempre. A medida (reticências, largura) é do navegador.
const test = require('node:test');
const assert = require('node:assert/strict');
const {criarMesa} = require('./dom_minimo.cjs');

const ALFA = {id: 'alfa', titulo: 'Pauta Alfa', rodadas: []};
async function abrir({desktop, cota, idioma = 'pt'}) {
  const mesa = criarMesa({desktop, modo: 'piloto', papel: 'admin', idioma, url: 'http://127.0.0.1:8765/?area=inicio&caso=alfa', catalogo: [ALFA],
    api: operacao => {
      if (operacao === 'cota') { if (cota instanceof Error) throw cota; return cota; }
      return ({inventario: {caso_id: 'alfa', corpus_id: 'c1', documentos: [], total_documentos: 0}, 'diligencias-listar': {resultados: []}}[operacao] || {});
    }});
  await mesa.esperar(20);
  return mesa;
}
const conta = (gasto, teto, esgotada = false) => ({mes: '2026-11', moeda: 'BRL', conta: {gasto_brl: gasto, teto_brl: teto, saldo_brl: '0.00', esgotada}});
const ids = no => [...no.children].map(filho => filho.id);

test('no celular Configurações abre a gaveta, antes de idioma, Sair e tema, e sai do cabeçalho', async () => {
  const mesa = await abrir({desktop: false, cota: conta('18.40', '50.00')});
  const gaveta = mesa.doc.querySelector('.mesa-drawer-controls');
  assert.deepEqual(ids(gaveta), ['mesa-configuracoes', 'mesa-idioma', 'mesa-sair', 'mesa-tema']);
  const cabecalho = mesa.doc.querySelector('.app-header');
  for (const id of ['mesa-configuracoes', 'mesa-idioma', 'mesa-sair', 'mesa-tema']) assert.ok(!ids(cabecalho).includes(id), `${id} fora do cabeçalho`);
  assert.equal(mesa.$('mesa-configuracoes').getAttribute('data-requer'), 'ia-config', 'continua dependendo da capacidade');
});

test('a partir de 720 px os botões voltam ao cabeçalho na ordem de sempre e a gaveta fica sem eles', async () => {
  const mesa = await abrir({desktop: true, cota: conta('18.40', '50.00')});
  const cabecalho = ids(mesa.doc.querySelector('.app-header'));
  assert.deepEqual(cabecalho.slice(-4), ['mesa-idioma', 'mesa-configuracoes', 'mesa-sair', 'mesa-tema']);
  assert.equal(mesa.doc.querySelector('.mesa-drawer-controls'), null);
});

test('a cota curta no cabeçalho: "R$ 18,40 de 50", "! Cota esgotada" no teto, em inglês, e some sem a rota', async () => {
  const normal = await abrir({desktop: false, cota: conta('18.40', '50.00')});
  const curta = normal.$('mesa-cota-cabecalho');
  assert.equal(curta.hidden, false); assert.equal(curta.textContent, 'R$ 18,40 de 50');
  assert.equal(curta.getAttribute('aria-label'), '37% da cota usada', 'o nome acessível diz do que é o número');
  const esgotada = await abrir({desktop: false, cota: conta('50.00', '50.00', true)});
  assert.equal(esgotada.$('mesa-cota-cabecalho').textContent, '! Cota esgotada');
  const fracionado = await abrir({desktop: false, cota: conta('3.10', '12.50')});
  assert.equal(fracionado.$('mesa-cota-cabecalho').textContent, 'R$ 3,10 de 12,50');
  const ingles = await abrir({desktop: false, cota: conta('18.40', '50.00'), idioma: 'en'});
  ingles.janela.I18N.aplicar(ingles.$('mesa-cota-cabecalho'));
  assert.equal(ingles.$('mesa-cota-cabecalho').textContent, 'R$ 18,40 of 50');
  // o mesmo bloco do cartão (C1 da Coruja): o administrador cuja instalação tem o menor saldo vê a da instalação, no formato curto e sem a parte da chave própria
  const instalacao = {...conta('10.00', '50.00'), conta: {gasto_brl: '10.00', teto_brl: '50.00', saldo_brl: '40.00', esgotada: false},
    organizacao: {gasto_brl: '160.00', teto_brl: '200.00', saldo_brl: '40.00', esgotada: false}, chave_propria: {conta_brl: '3.25', organizacao_brl: '12.00'}};
  instalacao.organizacao.saldo_brl = '30.00';
  const adm = await abrir({desktop: false, cota: instalacao});
  assert.equal(adm.$('mesa-cota-rotulo').textContent, 'Cota da instalação');
  assert.equal(adm.$('mesa-cota-cabecalho').textContent, 'Cota da instalação R$ 160,00 de 200', 'o número do cabeçalho é o do cartão');
  assert.equal(adm.$('mesa-cota-valor').textContent, 'R$ 160,00 de R$ 200');
  assert.ok(!/dos quais|chave/i.test(adm.$('mesa-cota-cabecalho').textContent + adm.$('mesa-cota-cabecalho').getAttribute('aria-label')), 'a chave própria fica só no cartão');
  assert.equal(adm.$('mesa-cota-cabecalho').getAttribute('aria-label'), '80% da cota da instalação usada');
  const instalacaoEsgotada = await abrir({desktop: false, cota: {...instalacao, organizacao: {gasto_brl: '200.00', teto_brl: '200.00', saldo_brl: '0.00', esgotada: true}}});
  assert.equal(instalacaoEsgotada.$('mesa-cota-cabecalho').textContent, '! Cota da instalação esgotada');
  const pessoaComChave = await abrir({desktop: false, cota: {...conta('18.40', '50.00'), chave_propria: {conta_brl: '3.25'}}});
  assert.equal(pessoaComChave.$('mesa-cota-cabecalho').textContent, 'R$ 18,40 de 50');
  assert.equal(pessoaComChave.$('mesa-cota-cabecalho').getAttribute('aria-label'), '37% da cota usada', 'sem a parte da chave própria');
  const instalacaoEn = await abrir({desktop: false, cota: instalacao, idioma: 'en'});
  instalacaoEn.janela.I18N.aplicar(instalacaoEn.$('mesa-cota-cabecalho'));
  assert.equal(instalacaoEn.$('mesa-cota-cabecalho').textContent, 'Installation quota R$ 160,00 of 200');
  const sem = await abrir({desktop: false, cota: new Error('sem rota')});
  assert.equal(sem.$('mesa-cota-cabecalho').hidden, true, 'sem a rota, sem cota no cabeçalho como no cartão');
  assert.equal(sem.$('mesa-cota').hidden, true);
});
