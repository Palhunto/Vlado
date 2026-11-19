'use strict';
// Evidence boards screen (interface/quadros.js) on the real index.html with the minimal DOM.
// Synthetic answers follow CONTRATO_EVIDENCIA §5.2 (hipoteses-quadro) and §5.3 (linha-tempo-listar).
const test = require('node:test');
const assert = require('node:assert/strict');
const {criarMesa, Evento, PILHA} = require('./dom_minimo.cjs');

const REF_IA = {tipo: 'ia', caso_id: 'alpha', rodada: 'R001', revisao: 'r2', registros_sha256: 'a'.repeat(64), evidencia_id: 'E001'};
const REF_HUMANA = {tipo: 'humana', caso_id: 'alpha', registro_id: 'N' + 'b'.repeat(32), sha256: 'c'.repeat(64), fonte: 2};
const evidencia = (ref, trecho, pagina = null) => ({
  referencia: ref, papel: 'suporte', suporte: 'sustentado', natureza: 'declaracao_documental', justificativa: 'A passagem declara o valor.',
  documento_id: 'D001', original_sha256: 'd'.repeat(64), estado: 'conferida', erro: null,
  localizador: {tipo: pagina ? 'pagina' : 'linhas', pagina_pdf: pagina, linha_inicio: 3, linha_fim: 3, descricao: '', legivel: pagina ? `D001 · p. ${pagina}` : 'D001 · linha 3'},
  evidencia: {documento: {documento_id: 'D001', nome: pagina ? 'contrato.pdf' : 'nota.txt'}, trecho,
    localizador: {pagina_pdf: pagina, legivel: pagina ? `D001 · p. ${pagina}` : 'D001 · linha 3'}},
});
const QUADRO = {caso: 'alpha', total: 1, divergentes: [], aviso: 'Situações declaradas por pessoas; o quadro não avalia veracidade.',
  hipoteses: [{id: 'H' + '1'.repeat(32), enunciado: 'O valor declarado na fonte é 12.', situacao: 'em_aberto', condicao: 'com_evidencia',
    natureza: 'declaracao_documental', situacao_sem_base: false,
    sustentam: [evidencia(REF_IA, 'A fonte declara valor 12.', 4)],
    contrariam: [{...evidencia(REF_HUMANA, 'Outra nota indica 15.'), papel: 'contradicao'}],
    contexto: [], indisponiveis: [{...evidencia(REF_IA, ''), estado: 'indisponivel', evidencia: null, erro: 'Rodada na lixeira.'}],
    faltam: [{origem: 'registrada', descricao: 'Comprovante de pagamento.', diligencia_id: null, diligencia_estado: null},
      {origem: 'automatica', descricao: 'Há evidências sustentadas nos dois sentidos; conferir antes de concluir.', diligencia_id: null, diligencia_estado: null}]}]};
const TIPOS = {fato: 'Data do fato (ocorrência)', assinatura: 'Data de assinatura', publicacao: 'Data de publicação'};
const entrada = (id, tipo, valor, precisao) => ({evento_id: id, sha256: 'e'.repeat(64), descricao: `Evento ${id}`,
  data: {tipo, valor, precisao, aproximada: false, fonte: 0, observacao: '', rotulo: TIPOS[tipo]},
  fonte_da_data: evidencia(REF_IA, `Trecho de ${id}`), fonte_conferida: true, evidencias: [], divergente: false, divergencia: null, retirado: false, motivo_retirada: ''});
const RETIRADO = {...entrada('T3', 'publicacao', '2021-05', 'mes'), retirado: true, motivo_retirada: 'Fonte duplicada.'};
const LINHA = {caso: 'alpha', total: 2, divergencias: [], fontes_indisponiveis: [], divergentes: [], tipos_data: TIPOS,
  aviso: 'Ordem por data registrada; datas parciais vão para o início do período.',
  entradas: [entrada('T1', 'assinatura', '2021', 'ano'), entrada('T2', 'fato', '2021-03-12', 'dia')]};

const SCRIPTS = [...PILHA, 'quadros.js', 'analise.js', 'indicador_salvamento.js'];
function mesa({integracao = {quadros_evidencia: true}, caso = 'alpha', api, papel = 'admin'} = {}) {
  const abertos = [];
  const m = criarMesa({
    scripts: SCRIPTS, papel,
    api: api || ((operacao, dados) => {
      if (operacao === 'hipoteses-quadro') return QUADRO;
      if (operacao === 'linha-tempo-listar') return {...LINHA, entradas: LINHA.entradas.filter(e => !dados.tipos || dados.tipos.includes(e.data.tipo))};
      if (operacao.endsWith('-original')) return 'bytes';
      return {};
    }),
    preparar: janela => {
      const original = janela.fetch;
      janela.fetch = async (rota, opcoes) => String(rota) === '/api/integracao' ? {ok: true, json: async () => integracao} : original(rota, opcoes);
    },
  });
  m.avaliar(`window.contextoCaso = () => ${JSON.stringify(caso)}; window.abrirOriginal = async (...args) => { window.__abertos.push(args); };`);
  m.janela.__abertos = abertos;
  return {...m, abertos};
}
async function abrir(m) { m.$('ver-quadros').click(); await m.esperar(8); }

test('hipóteses em três colunas, com localizador e selo de suporte em texto', async () => {
  const m = await mesa(); await abrir(m);
  assert.equal(m.$('area-quadros').hidden, false);
  const cartao = m.doc.querySelector('.quadro-hipotese');
  assert.ok(cartao, 'cartão da hipótese');
  const colunas = cartao.querySelectorAll('.quadro-coluna');
  assert.deepEqual(colunas.map(c => c.querySelector('h4').textContent), ['Sustenta', 'Contraria', 'Falta']);
  assert.match(colunas[0].textContent, /D001 · p\. 4/);
  assert.match(colunas[0].textContent, /A fonte declara valor 12\./);
  assert.match(colunas[0].textContent, /Sustentado/);
  assert.equal(colunas[0].querySelector('blockquote').getAttribute('translate'), 'no');
  assert.match(colunas[1].textContent, /Outra nota indica 15\./);
  assert.equal(colunas[2].querySelectorAll('.quadro-lacuna').length, 2);
  assert.match(colunas[2].textContent, /Lacuna registrada por pessoa/);
  assert.match(cartao.querySelector('.quadro-indisponiveis').textContent, /Rodada na lixeira/);
  assert.doesNotMatch(cartao.textContent, /fraude|culpa/i);
  assert.deepEqual(m.erros, []);
});

test('evidência abre o original pela rota da sua origem, na página citada', async () => {
  const m = await mesa(); await abrir(m);
  const [sustenta, contraria] = m.doc.querySelectorAll('.quadro-coluna');
  const botaoIa = sustenta.querySelector('button');
  assert.equal(botaoIa.textContent, 'Ver página 4 no original');
  botaoIa.click(); await m.esperar();
  assert.deepEqual(m.chamadas.at(-1), {operacao: 'achados-original', dados: {caso: 'alpha', rodada: 'R001', revisao: 'r2', evidencia_id: 'E001'}});
  assert.deepEqual(Array.from(m.abertos.at(-1).slice(1)), ['contrato.pdf', 4, 'A fonte declara valor 12.']);
  contraria.querySelector('button').click(); await m.esperar();
  assert.deepEqual(m.chamadas.at(-1), {operacao: 'caderno-original',
    dados: {caso: 'alpha', registro_id: REF_HUMANA.registro_id, sha256: REF_HUMANA.sha256, fonte_indice: 2}});
});

test('linha do tempo: filtro por tipo de data e distinção entre data exata e parcial', async () => {
  const m = await mesa(); await abrir(m);
  m.$('quadros-aba-tempo').click(); await m.esperar(8);
  const eventos = () => m.$('quadros-tempo').querySelectorAll('.tempo-evento');
  assert.equal(eventos().length, 2);
  const [parcial, exata] = eventos();
  assert.ok(parcial.classList.contains('marco-parcial'));
  assert.match(parcial.textContent, /2021 · Data parcial: ano/);
  assert.ok(exata.classList.contains('marco-exato'));
  assert.match(exata.textContent, /12\/03\/2021 · Data exata/);
  assert.equal(exata.querySelector('time').getAttribute('datetime'), '2021-03-12');
  const caixas = m.$('quadros-tempo').querySelectorAll('.tempo-filtro input');
  assert.deepEqual(caixas.map(c => c.value), ['fato', 'assinatura', 'publicacao']);
  caixas[1].checked = false; caixas[1].dispatchEvent(new Evento('change', {bubbles: true})); await m.esperar(8);
  assert.deepEqual(m.chamadas.at(-1), {operacao: 'linha-tempo-listar', dados: {caso: 'alpha', tipos: ['fato', 'publicacao']}});
  assert.equal(eventos().length, 1);
  assert.equal(m.$('quadros-tempo').querySelector('#tempo-tipo-assinatura').checked, false, 'a escolha continua marcada');
  eventos()[0].querySelector('button').click(); await m.esperar();
  assert.equal(m.chamadas.at(-1).operacao, 'achados-original', 'cada evento abre a evidência da sua data');
});

test('evento retirado mostra o motivo como dado, fora da tradução', async () => {
  const m = await mesa({api: operacao => operacao === 'linha-tempo-listar' ? {...LINHA, entradas: [RETIRADO]} : QUADRO}); await abrir(m);
  m.$('quadros-aba-tempo').click(); await m.esperar(8);
  const aviso = m.$('quadros-tempo').querySelector('.tempo-evento .notice');
  assert.match(aviso.textContent, /^Evento retirado: Fonte duplicada\.$/);
  assert.equal(aviso.querySelector('[translate=no]').textContent, 'Fonte duplicada.');
});

test('abas por teclado: setas, Home e End; só a aba ativa fica na ordem de Tab', async () => {
  const m = await mesa(); await abrir(m);
  const hip = m.$('quadros-aba-hipoteses'), tempo = m.$('quadros-aba-tempo');
  assert.equal(m.$('quadros-abas').getAttribute('role'), 'tablist');
  assert.equal(hip.getAttribute('aria-selected'), 'true');
  assert.equal(tempo.getAttribute('tabindex'), '-1');
  hip.dispatchEvent(new Evento('keydown', {key: 'ArrowRight', bubbles: true, cancelable: true})); await m.esperar(8);
  assert.equal(tempo.getAttribute('aria-selected'), 'true');
  assert.equal(m.doc.activeElement, tempo);
  assert.equal(m.$('quadros-hipoteses').hidden, true);
  assert.equal(m.$('quadros-tempo').hidden, false);
  assert.equal(m.$('quadros-tempo').getAttribute('aria-labelledby'), 'quadros-aba-tempo');
  tempo.dispatchEvent(new Evento('keydown', {key: 'Home', bubbles: true, cancelable: true}));
  assert.equal(hip.getAttribute('aria-selected'), 'true');
  hip.dispatchEvent(new Evento('keydown', {key: 'End', bubbles: true, cancelable: true}));
  assert.equal(m.$('quadros-aba-mapa').getAttribute('aria-selected'), 'true', 'End vai à última aba');
  m.$('quadros-aba-mapa').dispatchEvent(new Evento('keydown', {key: 'ArrowRight', bubbles: true, cancelable: true}));
  assert.equal(hip.getAttribute('aria-selected'), 'true', 'a seta volta ao início');
});

test('estados: sem apuração, servidor sem os quadros e erro da rota', async () => {
  const semCaso = await mesa({caso: ''}); await abrir(semCaso);
  assert.equal(semCaso.$('quadros-hipoteses').querySelector('.quadro-estado').dataset.estado, 'vazio');
  const antigo = await mesa({integracao: {}}); await abrir(antigo);
  const aviso = antigo.$('quadros-hipoteses').querySelector('.quadro-estado');
  assert.equal(aviso.getAttribute('role'), 'alert');
  assert.match(aviso.textContent, /não está disponível neste servidor/);
  assert.equal(antigo.chamadas.filter(c => c.operacao === 'hipoteses-quadro').length, 0);
  const falha = await mesa({api: () => { throw new Error('Apuração não encontrada.'); }}); await abrir(falha);
  assert.match(falha.$('quadros-hipoteses').textContent, /Apuração não encontrada\./);
});

test('indicador de salvamento no cabeçalho segue Rascunhos.indicador e o evento vlado:rascunho-estado', async () => {
  const m = await mesa();
  const indicador = m.$('mesa-salvamento');
  assert.ok(indicador.closest('.app-header'), 'no cabeçalho');
  assert.equal(indicador.getAttribute('role'), 'status');
  assert.equal(indicador.hidden, true, 'sem a API do salvamento, nada aparece');
  m.avaliar(`window.Rascunhos = window.Rascunhos || {}; window.Rascunhos.indicador = {assinar(fn) { window.__avisar = fn; fn({tipo: 'salvo', hora: '14:05', telas: 1}); return () => {}; }};
    window.IndicadorSalvamento.ligar();`);
  assert.equal(indicador.hidden, false);
  assert.equal(indicador.textContent, 'Rascunho salvo às 14:05');
  m.avaliar("window.__avisar({tipo: 'sem_rede', hora: '14:05', telas: 2})");
  assert.equal(indicador.dataset.tipo, 'sem_rede');
  assert.equal(indicador.textContent, 'Sem conexão — rascunho salvo neste navegador · 2 telas');
  m.avaliar("window.__avisar({tipo: 'ocioso', hora: null, telas: 0})");
  assert.equal(indicador.hidden, true);
  m.doc.dispatchEvent(new Evento('vlado:rascunho-estado', {detail: {tipo: 'salvando', hora: null, telas: 1}}));
  assert.equal(indicador.textContent, 'Salvando rascunho…');
  assert.doesNotMatch(indicador.textContent, /conteudo|texto do rascunho/);
});

test('resumo de retomada nos quadros só aparece com continuidade_resumo anunciado e para administração', async () => {
  const montar = "window.Continuidade = {montar: async (alvo, caso) => { window.__resumo = caso; alvo.textContent = 'Pendente: 2 hipóteses'; }};";
  const com = await mesa({integracao: {quadros_evidencia: true, continuidade_resumo: true}}); com.avaliar(montar); await abrir(com);
  assert.equal(com.$('quadros-retomada').hidden, false);
  assert.match(com.$('quadros-retomada').textContent, /Pendente: 2 hipóteses/);
  assert.equal(com.janela.__resumo, 'alpha');
  const sem = await mesa(); sem.avaliar(montar); await abrir(sem);
  assert.equal(sem.$('quadros-retomada'), null, 'servidor sem continuidade_resumo');
  const convidado = await mesa({integracao: {quadros_evidencia: true, continuidade_resumo: true}, papel: 'convidado'}); convidado.avaliar(montar);
  convidado.janela.dispatchEvent(new Evento('quadros-abrir')); await convidado.esperar(8);
  assert.equal(convidado.$('quadros-retomada'), null);
});

test('textos da tela têm tradução para o inglês', async () => {
  const m = criarMesa({scripts: SCRIPTS, idioma: 'en'});
  const textos = m.janela.VLADO_I18N_EN.textos;
  for (const chave of ['Quadros de evidência', 'Hipóteses', 'Linha do tempo', 'Sustenta', 'Contraria', 'Falta', 'Tipos de data', 'Data exata',
    'Data parcial: ano', 'Data parcial: mês', 'Evidência da data', '{n} itens', 'Carregando…', 'Situação declarada: {situacao}',
    'Escolha uma apuração no topo da Mesa para ver este quadro.', 'Este quadro ainda não está disponível neste servidor. Atualize a Mesa para a versão mais recente.']) {
    assert.ok(textos[chave], `tradução de “${chave}”`);
  }
});
