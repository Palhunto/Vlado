'use strict';
// Cartão da cota do mês na barra lateral (GET /api/cota, docs/design/componentes.md#barra-lateral): valor em reais e medidor com texto
// acessível; esgotada nunca só pela cor (rótulo "Cota esgotada", aria-label por extenso); sem a rota o cartão não aparece. DOM sintético.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {criarMesa} = require('./dom_minimo.cjs');
const {blocos} = require('./tokens_tema.cjs');

const ALFA = {id: 'alfa', titulo: 'Pauta Alfa', rodadas: []};

async function abrir(cota, idioma = 'pt') {
  const mesa = criarMesa({desktop: true, modo: 'piloto', papel: 'admin', idioma, url: 'http://127.0.0.1:8765/?area=inicio&caso=alfa', catalogo: [ALFA],
    api: operacao => {
      if (operacao === 'cota') { if (cota instanceof Error) throw cota; return typeof cota === 'function' ? cota() : cota; }
      return ({inventario: {caso_id: 'alfa', corpus_id: 'c1', documentos: [], total_documentos: 0}, 'diligencias-listar': {resultados: []}}[operacao] || {});
    }});
  await mesa.esperar(20);
  return mesa;
}
const conta = (gasto, teto, esgotada = false) => ({mes: '2026-11', moeda: 'BRL', conta: {gasto_brl: gasto, teto_brl: teto, saldo_brl: '0.00', esgotada}});

test('cota normal: valor em reais, teto sem centavos quando inteiro e medidor com aria-label', async () => {
  const mesa = await abrir(conta('18.40', '50.00'));
  assert.equal(mesa.$('mesa-cota').hidden, false);
  assert.equal(mesa.$('mesa-cota-rotulo').textContent, 'Cota do mês');
  assert.equal(mesa.$('mesa-cota-valor').textContent, 'R$ 18,40 de R$ 50');
  assert.equal(mesa.$('mesa-cota-medidor').getAttribute('aria-label'), '37% da cota usada');
  assert.equal(mesa.$('mesa-cota').dataset.esgotada, 'false');
});

test('cota esgotada: rótulo, valor e aria-label dizem, não só a cor; medidor cheio', async () => {
  const mesa = await abrir(conta('50.00', '50.00', true));
  assert.equal(mesa.$('mesa-cota').dataset.esgotada, 'true');
  assert.equal(mesa.$('mesa-cota-rotulo').textContent, 'Cota esgotada');
  assert.equal(mesa.$('mesa-cota-valor').textContent, 'R$ 50,00 de R$ 50');
  assert.equal(mesa.$('mesa-cota-medidor').getAttribute('aria-label'), 'Cota do mês esgotada: R$ 50,00 de R$ 50');
});

test('sem a rota ou com resposta sem conta, o cartão não aparece', async () => {
  assert.equal((await abrir(new Error('403'))).$('mesa-cota').hidden, true);
  assert.equal((await abrir({})).$('mesa-cota').hidden, true);
});

test('em inglês o rótulo e o aria-label da cota esgotada são traduzidos', async () => {
  const mesa = await abrir(conta('50.00', '50.00', true), 'en');
  mesa.janela.I18N.aplicar(mesa.$('mesa-sidebar'));   // o observador do navegador faz isto sozinho; o DOM sintético não tem
  assert.equal(mesa.$('mesa-cota-rotulo').textContent, 'Quota used up');
  assert.equal(mesa.$('mesa-cota-valor').textContent, 'R$ 50,00 of R$ 50');
  assert.equal(mesa.$('mesa-cota-medidor').getAttribute('aria-label'), 'Monthly quota used up: R$ 50,00 of R$ 50');
});

test('folha de estilos: esgotada troca fundo, borda, texto, sinal "!" e medidor para os tokens de aviso', () => {
  const css = fs.readFileSync(path.join(__dirname, '..', 'interface', 'style.css'), 'utf8');
  const esgotada = blocos(css).filter(r => /mesa-cota\[data-esgotada=true\]/.test(r.seletor));
  const corpos = esgotada.map(r => r.corpo).join(';');
  assert.match(corpos, /background:var\(--theme-warning-bg\)/);
  assert.match(corpos, /border-color:var\(--theme-warning-line\)/);
  assert.match(corpos, /color:var\(--theme-warning\)/);
  assert.ok(esgotada.some(r => /rotulo::before/.test(r.seletor) && /content:'! '/.test(r.corpo)), 'sinal ! antes do rótulo');
  assert.ok(esgotada.some(r => /medidor::before/.test(r.seletor) && /var\(--theme-warning\)/.test(r.corpo)), 'medidor de aviso');
});

// Administrador também recebe a cota da instalação: o cartão mostra a mais apertada (a de menor saldo).
const comOrganizacao = (conta_, organizacao) => ({mes: '2026-11', moeda: 'BRL', conta: conta_, organizacao});
const bloco = (gasto, teto, saldo, esgotada = false) => ({gasto_brl: gasto, teto_brl: teto, saldo_brl: saldo, esgotada});

test('administrador: se a instalação tem menos saldo que a conta, o cartão mostra a da instalação', async () => {
  const mesa = await abrir(comOrganizacao(bloco('10.00', '50.00', '40.00'), bloco('99.00', '100.00', '1.00')));
  assert.equal(mesa.$('mesa-cota-rotulo').textContent, 'Cota da instalação');
  assert.equal(mesa.$('mesa-cota-valor').textContent, 'R$ 99,00 de R$ 100');
  assert.equal(mesa.$('mesa-cota-medidor').getAttribute('aria-label'), '99% da cota da instalação usada');
});

test('administrador: instalação esgotada vira o estado esgotado, com o rótulo da instalação', async () => {
  const mesa = await abrir(comOrganizacao(bloco('10.00', '50.00', '40.00'), bloco('100.00', '100.00', '0.00', true)));
  assert.equal(mesa.$('mesa-cota').dataset.esgotada, 'true');
  assert.equal(mesa.$('mesa-cota-rotulo').textContent, 'Cota da instalação esgotada');
  assert.equal(mesa.$('mesa-cota-medidor').getAttribute('aria-label'), 'Cota da instalação esgotada: R$ 100,00 de R$ 100');
});

test('administrador: se a conta tem menos saldo que a instalação, o cartão segue na conta', async () => {
  const mesa = await abrir(comOrganizacao(bloco('45.00', '50.00', '5.00'), bloco('60.00', '500.00', '440.00')));
  assert.equal(mesa.$('mesa-cota-rotulo').textContent, 'Cota do mês');
  assert.equal(mesa.$('mesa-cota-valor').textContent, 'R$ 45,00 de R$ 50');
});

test('ao terminar uma pergunta, codex.js atualiza o cartão: atualizarCotaBarra(true) pede a rota de novo', async () => {
  let atual = conta('10.00', '50.00');
  const mesa = await abrir(() => atual);
  assert.equal(mesa.$('mesa-cota-valor').textContent, 'R$ 10,00 de R$ 50');
  atual = conta('12.30', '50.00');
  mesa.janela.atualizarCotaBarra(true);
  await mesa.esperar(6);
  assert.equal(mesa.$('mesa-cota-valor').textContent, 'R$ 12,30 de R$ 50');
});

test('codex.js avisa o cartão quando a pergunta termina (o acompanhamento para de esperar eventos)', () => {
  const codigo = fs.readFileSync(path.join(__dirname, '..', 'interface', 'codex.js'), 'utf8');
  assert.match(codigo, /if \(!active && data\.eventos\.length < 100\) \{ window\.atualizarCotaBarra\?\.\(true\);/);
});

test('P40 (b): o que a chave própria pagou é parte do valor da cota ("dos quais R$ 3,25 com a chave própria", 14 muted abaixo do medidor); o dono vê também o total da redação; R$ 0,00 sem gasto; some sem o campo', async () => {
  const comChave = (gasto, propria, redacao) => ({...conta(gasto, '50.00'), chave_propria: {conta_brl: propria, ...(redacao ? {organizacao_brl: redacao} : {})}});
  const pessoa = await abrir(comChave('18.40', '3.25'));
  assert.equal(pessoa.$('mesa-cota-valor').textContent, 'R$ 18,40 de R$ 50', 'a cota do serviço segue como estava');
  assert.equal(pessoa.$('mesa-cota-chave').hidden, false);
  assert.equal(pessoa.$('mesa-cota-chave').textContent, 'dos quais R$ 3,25 com a chave própria');
  assert.equal(pessoa.$('mesa-cota-medidor').getAttribute('aria-label'), '37% da cota usada, dos quais R$ 3,25 com a chave própria');
  assert.equal(pessoa.$('mesa-cota-chave-redacao').hidden, true, 'a pessoa não vê o total da redação');
  const dono = await abrir(comChave('18.40', '3.25', '12.00'));
  assert.equal(dono.$('mesa-cota-chave-redacao').hidden, false);
  assert.equal(dono.$('mesa-cota-chave-redacao').querySelector('.mesa-cota-rotulo').textContent, 'Chave própria da redação');
  assert.equal(dono.$('mesa-cota-chave-redacao-valor').textContent, 'R$ 12,00');
  const zero = await abrir(comChave('0.00', '0.00', '0.00'));
  assert.equal(zero.$('mesa-cota-chave').textContent, 'dos quais R$ 0,00 com a chave própria', 'R$ 0,00 se ainda não houve gasto, com o total da redação junto (a redação tem chave)');
  // B1 da Coruja: a forma real que o servidor mandou a quem NÃO tem chave própria; o campo veio, mas sem a chave a linha não aparece
  const falso = await abrir({...conta('18.40', '50.00'), chave_propria: {conta_brl: '0.00'}});
  assert.equal(falso.$('mesa-cota-chave').hidden, true, 'conta_brl 0.00 sem o total da redação: sem chave própria, a linha some');
  assert.equal(falso.$('mesa-cota-chave').textContent, ''); assert.equal(falso.$('mesa-cota-chave-redacao').hidden, true);
  assert.equal(falso.$('mesa-cota-medidor').getAttribute('aria-label'), '37% da cota usada');
  const sem = await abrir(conta('18.40', '50.00'));
  assert.equal(sem.$('mesa-cota-chave').hidden, true, 'sem chave própria, a linha some'); assert.equal(sem.$('mesa-cota-chave-redacao').hidden, true);
  assert.equal(sem.$('mesa-cota-medidor').getAttribute('aria-label'), '37% da cota usada');
  const esgotada = await abrir({...comChave('50.00', '8.00'), conta: {gasto_brl: '50.00', teto_brl: '50.00', saldo_brl: '0.00', esgotada: true}});
  assert.equal(esgotada.$('mesa-cota-medidor').getAttribute('aria-label'), 'Cota do mês esgotada: R$ 50,00 de R$ 50, dos quais R$ 8,00 com a chave própria');
  const ingles = await abrir(comChave('18.40', '3.25', '12.00'), 'en');
  ingles.janela.I18N.aplicar(ingles.$('mesa-sidebar'));
  assert.equal(ingles.$('mesa-cota-chave').textContent, "of which R$ 3,25 on the newsroom’s own key");
  assert.equal(ingles.$('mesa-cota-medidor').getAttribute('aria-label'), "37% of the quota used, of which R$ 3,25 on the newsroom’s own key");
  assert.equal(ingles.$('mesa-cota-chave-redacao').querySelector('.mesa-cota-rotulo').textContent, "Newsroom’s own key");
});

test('quando o cartão mostra a cota da instalação (ela não inclui a chave própria), a linha "dos quais" não aparece; o dono segue vendo o total da redação', async () => {
  const org = {...conta('10.00', '50.00'), conta: {gasto_brl: '10.00', teto_brl: '50.00', saldo_brl: '40.00', esgotada: false},
    organizacao: {gasto_brl: '45.00', teto_brl: '50.00', saldo_brl: '5.00', esgotada: false}, chave_propria: {conta_brl: '3.25', organizacao_brl: '12.00'}};
  const mesa = await abrir(org);
  assert.equal(mesa.$('mesa-cota-rotulo').textContent, 'Cota da instalação');
  assert.equal(mesa.$('mesa-cota-chave').hidden, true);
  assert.equal(mesa.$('mesa-cota-chave-redacao').hidden, false);
});

test('folha de estilos: "dos quais" em 14 px muted logo abaixo do medidor (8 px do cartão), e a linha do total da redação sem quebra no rótulo', () => {
  const estilo = fs.readFileSync(path.join(__dirname, '..', 'interface', 'style.css'), 'utf8');
  assert.ok(estilo.includes('.mesa-cota-dos-quais{margin:0;font-size:var(--text-md);line-height:1.25;color:var(--muted)}'));
  assert.ok(estilo.includes('#mesa-cota-chave-redacao .mesa-cota-rotulo{white-space:nowrap}'));
});
