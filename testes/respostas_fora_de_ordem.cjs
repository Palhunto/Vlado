'use strict';
// Respostas fora de ordem nos quadros: com o servidor lento, a resposta da apuração anterior chega depois da troca e não pode ser pintada, e o painel
// "O que já foi feito e o que falta nesta apuração" é um só. Defeito achado pelo dono ao trocar de uma apuração para outra (11 documentos da primeira
// no painel da segunda, que tem 14, e um painel preso em "Verificando o que falta…"). Dados sintéticos; cada leitura do servidor é uma promessa que o teste resolve na ordem que quiser.
const test = require('node:test');
const assert = require('node:assert/strict');
const {criarMesa, Evento, PILHA} = require('./dom_minimo.cjs');

const SCRIPTS = [...PILHA, 'quadros.js', 'sugestoes.js', 'formularios.js', 'analise.js', 'indicador_salvamento.js'];
const adiada = () => { let resolver; const promessa = new Promise(r => { resolver = r; }); return {promessa, resolver}; };
const texto = no => no.textContent.replace(/\s+/g, ' ').trim();
const espera = async m => { await new Promise(r => setTimeout(r, 12)); await m.esperar(10); };
const resumo = (caso, n) => ({caso, documentos: {cadastrados: n, pendentes: []}, rodada: null, conversas_interrompidas: [], quadros: [], rascunhos: [], aviso: 'Metadados.'});
const hip = (id, enunciado) => ({id, enunciado, situacao: 'em_aberto', condicao: 'pendencia', natureza: null, situacao_sem_base: false, sustentam: [], contrariam: [], faltam: [], contexto: [], indisponiveis: []});

// `respostas`: operacao -> caso -> promessa (ou valor); `pedidos` registra as chamadas.
function montar({respostas, integracao = {quadros_evidencia: true, continuidade_resumo: true, tabelas_apuracao: true}} = {}) {
  const pedidos = [];
  const m = criarMesa({scripts: SCRIPTS, desktop: true,
    api: (operacao, dados) => {
      pedidos.push([operacao, dados.caso]);
      const r = respostas[operacao]?.[dados.caso] ?? respostas[operacao]?.[dados.id];
      if (r !== undefined) return r;
      if (operacao === 'sugestoes-listar') return {caso: dados.caso, quadro: dados.quadro, contagem: {}, sugestoes: []};
      return {};
    },
    preparar: janela => {
      const original = janela.fetch;
      janela.fetch = async (rota, opcoes) => String(rota) === '/api/integracao' ? {ok: true, json: async () => integracao} : original(rota, opcoes);
    }});
  m.avaliar('window.__caso = "sinfra"; window.contextoCaso = () => window.__caso;');
  const trocar = caso => { m.avaliar(`window.__caso = ${JSON.stringify(caso)};`); m.janela.dispatchEvent(new Evento('mesa-contexto-alterado')); };
  return {...m, pedidos, trocar};
}

test('painel de retomada: um só, e a resposta da apuração anterior, chegando depois da troca, não é pintada', async () => {
  const sinfra = adiada(), parana = adiada();
  const m = montar({respostas: {'continuidade-resumo': {sinfra: sinfra.promessa, paranaita: parana.promessa}}});
  m.$('ver-quadros').click();   // abre os quadros e, na sequência, a pessoa troca de apuração
  m.trocar('paranaita');
  await espera(m);
  // a resposta nova chega primeiro; a antiga, depois (fora de ordem)
  parana.resolver(resumo('paranaita', 14)); await espera(m);
  sinfra.resolver(resumo('sinfra', 11)); await espera(m);
  const paineis = m.doc.querySelectorAll('#quadros-retomada, .quadros-retomada');
  assert.equal(m.doc.querySelectorAll('.quadros-retomada').length, 1, 'o painel é um só, substituído');
  assert.equal(paineis.length >= 1, true);
  const corpo = texto(m.$('quadros-retomada'));
  assert.match(corpo, /14 documentos cadastrados/);
  assert.doesNotMatch(corpo, /11 documentos/, 'o número da apuração anterior não aparece');
  assert.doesNotMatch(corpo, /Verificando o que falta/, 'nada fica preso em "Verificando"');
  assert.equal(m.doc.querySelectorAll('.continuidade-resumo').length, 1);
  assert.deepEqual(m.erros, []);
});

test('painel de retomada: respostas na mesma ordem das trocas também valem a última apuração', async () => {
  const sinfra = adiada(), parana = adiada();
  const m = montar({respostas: {'continuidade-resumo': {sinfra: sinfra.promessa, paranaita: parana.promessa}}});
  m.$('ver-quadros').click(); m.trocar('paranaita'); await espera(m);
  sinfra.resolver(resumo('sinfra', 11)); await espera(m);
  parana.resolver(resumo('paranaita', 14)); await espera(m);
  assert.equal(m.doc.querySelectorAll('.quadros-retomada').length, 1);
  assert.match(texto(m.$('quadros-retomada')), /14 documentos cadastrados/);
});

test('hipóteses, linha do tempo e mapa: a leitura da apuração anterior, chegando depois, não pinta o quadro da nova', async () => {
  for (const [aba, painel, operacao, velha, nova] of [
    ['hipoteses', 'quadros-hipoteses', 'hipoteses-quadro', {caso: 'sinfra', total: 1, divergentes: [], aviso: '', hipoteses: [hip('H1', 'Hipótese da Sinfra')]}, {caso: 'paranaita', total: 1, divergentes: [], aviso: '', hipoteses: [hip('H2', 'Hipótese de Paranaíta')]}],
    ['mapa', 'quadros-mapa', 'mapa-ver', {caso: 'sinfra', aviso: '', homonimos: [], relacoes: [], entidades: [{id: 'P' + 'a'.repeat(32), nome: 'Entidade da Sinfra', tipo: 'pessoa', situacao: 'com_evidencia', identificadores: []}]},
      {caso: 'paranaita', aviso: '', homonimos: [], relacoes: [], entidades: [{id: 'P' + 'b'.repeat(32), nome: 'Entidade de Paranaíta', tipo: 'pessoa', situacao: 'com_evidencia', identificadores: []}]}],
    ['tempo', 'quadros-tempo', 'linha-tempo-listar', {caso: 'sinfra', total: 1, divergencias: [], fontes_indisponiveis: [], divergentes: [], tipos_data: {fato: 'Data do fato'}, aviso: '', entradas: [{evento_id: 'T1', sha256: 'e'.repeat(64), descricao: 'Evento da Sinfra', data: {tipo: 'fato', valor: '2025-02-10', precisao: 'dia', aproximada: false, fonte: 0, observacao: '', rotulo: 'Data do fato'}, fonte_da_data: null, fonte_conferida: false, evidencias: [], divergente: false, divergencia: null, retirado: false, motivo_retirada: ''}]},
      {caso: 'paranaita', total: 1, divergencias: [], fontes_indisponiveis: [], divergentes: [], tipos_data: {fato: 'Data do fato'}, aviso: '', entradas: [{evento_id: 'T2', sha256: 'e'.repeat(64), descricao: 'Evento de Paranaíta', data: {tipo: 'fato', valor: '2025-03-10', precisao: 'dia', aproximada: false, fonte: 0, observacao: '', rotulo: 'Data do fato'}, fonte_da_data: null, fonte_conferida: false, evidencias: [], divergente: false, divergencia: null, retirado: false, motivo_retirada: ''}]}]]) {
    const a = adiada(), b = adiada();
    const m = montar({respostas: {[operacao]: {sinfra: a.promessa, paranaita: b.promessa}}});
    m.$('ver-quadros').click(); await espera(m);
    m.$(`quadros-aba-${aba}`).click(); await espera(m);
    m.trocar('paranaita'); await espera(m);
    b.resolver(nova); await espera(m);
    a.resolver(velha); await espera(m);
    const corpo = texto(m.$(painel));
    assert.match(corpo, /Paranaíta/, `${aba}: mostra a apuração selecionada`);
    assert.doesNotMatch(corpo, /Sinfra/, `${aba}: a resposta da apuração anterior não é pintada`);
    assert.deepEqual(m.erros, [], aba);
  }
});

test('tabelas: duas escolhas seguidas com o servidor lento pintam só a última', async () => {
  const T1 = 'Q' + '1'.repeat(32), T2 = 'Q' + '2'.repeat(32);
  const tabela = (id, titulo) => ({caso: 'sinfra', id, sha256: 'e'.repeat(64), versao: {sequencia: 1}, titulo, descricao: '', aviso: '', colunas: [{id: 'c', nome: 'Valor', tipo: 'texto', moeda: null, unidade: null}],
    linhas: [{id: 'L0001', celulas: {c: {valor: titulo, fonte: null, estado: 'pendente', fonte_legivel: null, fonte_conferida: false, ultima_correcao: null}}}], evidencias: [], calculos: [], celulas_por_estado: {extraido: 0, corrigido_manual: 0, pendente: 1}, retirado: false, motivo_retirada: '', historico: []});
  const d1 = adiada(), d2 = adiada(), d3 = adiada();
  let n = 0;
  const m = montar({respostas: {'tabelas-listar': {sinfra: {caso: 'sinfra', total: 2, divergentes: [], aviso: '', tabelas: [{id: T1, titulo: 'Primeira', total_linhas: 1}, {id: T2, titulo: 'Segunda', total_linhas: 1}]}},
    'tabelas-detalhe': {[T1]: tabela(T1, 'Primeira'), [T2]: tabela(T2, 'Segunda')}}});
  // o servidor responde cada leitura de detalhe quando o teste manda: a primeira abertura (T1), depois T2 e T1 de novo, trocadas de ordem
  const original = m.janela.fetch;
  const fila = [d1, d2, d3];
  m.janela.fetch = async (rota, opcoes) => {
    if (String(rota) === '/api/tabelas-detalhe') { const dados = JSON.parse(opcoes.body), espera_ = fila[n++]; const corpo = await espera_.promessa; return {ok: true, json: async () => corpo(dados.id)}; }
    return original(rota, opcoes);
  };
  m.$('ver-quadros').click(); await espera(m);
  m.$('quadros-aba-tabelas').click(); await espera(m);
  const escolha = m.$('tabelas-escolha');
  d1.resolver(id => tabela(id, 'Primeira')); await espera(m);
  escolha.value = T2; escolha.dispatchEvent(new Evento('change', {bubbles: true})); await espera(m);
  escolha.value = T1; escolha.dispatchEvent(new Evento('change', {bubbles: true})); await espera(m);
  // a leitura de T1 (a última escolha) chega antes da de T2 (a penúltima)
  d3.resolver(id => tabela(id, 'Primeira')); await espera(m);
  d2.resolver(id => tabela(id, 'Segunda')); await espera(m);
  const celulas = [...m.$('quadros-tabelas').querySelectorAll('td.tabela-celula')].map(texto);
  assert.deepEqual(celulas.map(c => c.replace(/\s*\(.*\)$/, '')), ['Primeira'], 'só a última escolha é pintada');
});

test('formulário aberto por uma apuração que já não é a selecionada não abre no painel da outra', async () => {
  const T1 = 'Q' + '1'.repeat(32);
  const detalhe = adiada();
  const tabela = {caso: 'sinfra', id: T1, sha256: 'e'.repeat(64), versao: {sequencia: 1}, titulo: 'Da Sinfra', descricao: '', aviso: '', colunas: [{id: 'c', nome: 'Valor', tipo: 'texto', moeda: null, unidade: null}],
    linhas: [], evidencias: [], calculos: [], celulas_por_estado: {extraido: 0, corrigido_manual: 0, pendente: 0}, retirado: false, motivo_retirada: '', historico: []};
  const m = montar({respostas: {'tabelas-listar': {sinfra: {caso: 'sinfra', total: 1, divergentes: [], aviso: '', tabelas: [{id: T1, titulo: 'Da Sinfra', total_linhas: 0}]}, paranaita: {caso: 'paranaita', total: 0, divergentes: [], aviso: '', tabelas: []}}}});
  let chamadas = 0; const original = m.janela.fetch;
  m.janela.fetch = async (rota, opcoes) => {
    if (String(rota) === '/api/tabelas-detalhe' && ++chamadas === 2) { const corpo = await detalhe.promessa; return {ok: true, json: async () => corpo}; }
    if (String(rota) === '/api/tabelas-detalhe') return {ok: true, json: async () => tabela};
    return original(rota, opcoes);
  };
  m.$('ver-quadros').click(); await espera(m);
  m.$('quadros-aba-tabelas').click(); await espera(m);
  const editar = [...m.$('quadros-tabelas').querySelectorAll('button')].find(b => texto(b) === 'Editar');
  assert.ok(editar, 'Editar da tabela da Sinfra');
  editar.click(); await espera(m);       // pede o detalhe e fica esperando
  m.trocar('paranaita'); await espera(m);
  detalhe.resolver(tabela); await espera(m);
  assert.equal(m.$('quadros-tabelas').querySelectorAll('.form-quadro').length, 0, 'nenhum formulário da outra apuração');
  assert.deepEqual(m.erros, []);
});

test('N1 da Coruja: o original pedido numa apuração não abre por cima de outra se a pessoa trocou enquanto o servidor respondia', async () => {
  const REF = {tipo: 'ia', caso_id: 'sinfra', rodada: 'R001', revisao: 'r2', registros_sha256: 'a'.repeat(64), evidencia_id: 'E001'};
  const evidencia = {referencia: REF, papel: 'suporte', suporte: 'sustentado', natureza: 'declaracao_documental', justificativa: 'A passagem declara o valor.', documento_id: 'D001', original_sha256: 'd'.repeat(64),
    estado: 'conferida', erro: null, localizador: {tipo: 'pagina', pagina_pdf: 4, linha_inicio: 3, linha_fim: 3, descricao: '', legivel: 'D001 · p. 4'},
    evidencia: {documento: {documento_id: 'D001', nome: 'contrato.pdf'}, trecho: 'A fonte declara valor 12.', localizador: {pagina_pdf: 4, legivel: 'D001 · p. 4'}}};
  const quadro = {caso: 'sinfra', total: 1, divergentes: [], aviso: '', hipoteses: [{...hip('H' + '1'.repeat(32), 'Hipótese da Sinfra'), condicao: 'com_evidencia', sustentam: [evidencia]}]};
  const vazio = {caso: 'paranaita', total: 0, divergentes: [], aviso: '', hipoteses: []};
  for (const trocou of [true, false]) {
    const original = adiada();
    const m = montar({respostas: {'hipoteses-quadro': {sinfra: quadro, paranaita: vazio}, 'achados-original': {sinfra: original.promessa}}});
    m.avaliar('window.__abertos = []; window.abrirOriginal = async (...args) => { window.__abertos.push(args); };');
    m.$('ver-quadros').click(); await espera(m);
    const botao = [...m.$('quadros-hipoteses').querySelectorAll('.quadro-evidencia button')].find(b => /original/i.test(texto(b)));
    assert.ok(botao, 'botão Abrir o original');
    botao.click(); await espera(m);
    if (trocou) m.trocar('paranaita');
    await espera(m);
    original.resolver('bytes'); await espera(m);
    assert.equal(m.janela.__abertos.length, trocou ? 0 : 1, trocou ? 'a resposta da apuração anterior não abre nada' : 'sem troca, o original abre');
    assert.deepEqual(m.erros, []);
  }
});
