'use strict';
// Analysis boards (interface/analise.js) on the real index.html with the minimal DOM. Synthetic
// answers follow CONTRATO_EVIDENCIA §5.4 (comparar-documentos), §5.7 (tabelas-*) and §5.5 (mapa-ver).
const test = require('node:test');
const assert = require('node:assert/strict');
const {criarMesa, Evento, PILHA} = require('./dom_minimo.cjs');

const REF = {tipo: 'ia', caso_id: 'alpha', rodada: 'R001', revisao: 'r2', registros_sha256: 'a'.repeat(64), evidencia_id: 'E002'};
const VINCULO = {referencia: REF, papel: 'suporte', suporte: 'sustentado', natureza: 'declaracao_documental', justificativa: 'Ata registra a função.',
  documento_id: 'D002', original_sha256: 'd'.repeat(64), estado: 'conferida', erro: null,
  localizador: {tipo: 'linhas', pagina_pdf: null, linha_inicio: 7, linha_fim: 7, legivel: 'D002 · linha 7'},
  evidencia: {documento: {nome: 'ata.txt'}, trecho: 'Lúcia Prates, fiscal do contrato.', localizador: {legivel: 'D002 · linha 7'}}};
const COMPARACAO = {caso: 'alpha', rodada: 'R001', identicos: false, semelhanca: 0.8, total_alteracoes: 1, truncado: false,
  a: {documento_id: 'D001', paginas_sem_texto: []}, b: {documento_id: 'D002', paginas_sem_texto: [3]},
  alteracoes: [{operacao: 'substituido', classe: 'valor', a: 'Valor global: R$ 8.750.000,00.', b: 'Valor global: R$ 10.937.500,00.',
    localizador_a: {pagina_pdf: null, linha_inicio: 6, linha_fim: 6}, localizador_b: {pagina_pdf: null, linha_inicio: 6, linha_fim: 6},
    contexto_a: [{pagina_pdf: null, linha: 5, texto: 'Objeto: pavimentação de 12,4 km.'}], contexto_b: [{pagina_pdf: null, linha: 5, texto: 'Objeto: pavimentação de 12,4 km.'}],
    calculo: {operacao: 'b - a', unidade: 'R$', diferenca: '2187500', motivo: null},
    palavras: {segmentos: [{operacao: 'igual', a: 'Valor global:', b: 'Valor global:'}, {operacao: 'substituido', a: 'R$ 8.750.000,00.', b: 'R$ 10.937.500,00.'}]}}],
  marcas: {}, aviso: 'Comparação do texto extraído (nativo ou OCR); conferir no original nomes, valores e tabelas.'};
const celula = (valor, estado, fonte, extra = {}) => ({valor, fonte, estado, fonte_legivel: fonte === null ? null : 'D003 · Pagamentos!B2', fonte_conferida: fonte !== null, ultima_correcao: null, ...extra});
const TABELA = {caso: 'alpha', id: 'Q' + '1'.repeat(32), titulo: 'Pagamentos 2024', descricao: '', aviso: 'Valores como registrados nas fontes.',
  colunas: [{id: 'data', nome: 'Data', tipo: 'data', moeda: null, unidade: null}, {id: 'valor', nome: 'Valor', tipo: 'monetario', moeda: 'BRL', unidade: null}],
  linhas: [{id: 'L0001', celulas: {data: celula('2024-01', 'extraido', 0), valor: celula('1200.00', 'extraido', 0)}},
    {id: 'L0002', celulas: {data: celula('2024-02', 'extraido', 0), valor: celula('1145.50', 'corrigido_manual', 0,
      {ultima_correcao: {sequencia: 2, em_utc: '2026-11-19T10:00:00+00:00', autor: 'Ana', valor_anterior: '1154.50', justificativa: 'Dígitos trocados na transcrição.'}})}},
    {id: 'L0003', celulas: {data: celula(null, 'pendente', null), valor: celula(null, 'pendente', null)}}],
  evidencias: [], celulas_por_estado: {extraido: 3, corrigido_manual: 1, pendente: 2},
  calculos: [{id: 'total', nome: 'Total pago', operacao: 'soma', estado: 'com_fonte', expressao: '1200.00 + 1145.50', resultado: '2345.50',
    grandeza: {tipo: 'monetario', moeda: 'BRL', unidade: null}, arredondamento: null,
    celulas: [{linha: 'L0001', coluna: 'valor', nome_coluna: 'Valor', valor: '1200.00', fonte_legivel: 'D003 · Pagamentos!B2'},
      {linha: 'L0002', coluna: 'valor', nome_coluna: 'Valor', valor: '1145.50', fonte_legivel: 'D003 · Pagamentos!B3'}]}]};
const MAPA = {caso: 'alpha', divergentes: [], aviso: 'Ligações registradas por pessoas a partir de evidências; não indicam culpa nem causalidade.',
  entidades: [
    {id: 'P1', tipo: 'pessoa', nome: 'Lúcia Prates', identificadores: [{tipo: 'matricula', fonte: 0, valor_exibicao: '7781'}], situacao: 'com_evidencia', evidencias: []},
    {id: 'P2', tipo: 'pessoa', nome: 'Lucia  PRATES', identificadores: [], situacao: 'sem_evidencia', evidencias: []},
    {id: 'P3', tipo: 'organizacao', nome: 'Construtora Exemplo Ltda.', identificadores: [{tipo: 'cnpj', fonte: 0, valor_exibicao: '12.***.***/0001-**'}], situacao: 'com_evidencia', evidencias: []}],
  relacoes: [{id: 'L1', origem: 'P1', destino: 'P3', tipo: 'fiscal de contrato com', descricao: '', evidencias: [VINCULO], situacao: 'documentada', entidades_disponiveis: true},
    {id: 'L2', origem: 'P2', destino: 'P3', tipo: 'citada por', descricao: '', evidencias: [VINCULO], situacao: 'inferida', entidades_disponiveis: true}],
  homonimos: [{entidades: ['P2', 'P1'], nomes: ['Lucia  PRATES', 'Lúcia Prates'], motivo: 'nome_igual', identificadores_comuns: [], identificadores_divergentes: ['matricula'],
    conferencias: [], situacao: 'pendente', aviso: 'Sugestão para conferência humana; as entidades não foram fundidas.'}]};

function mesa({integracao = {quadros_evidencia: true, tabelas_apuracao: true}} = {}) {
  const m = criarMesa({
    scripts: [...PILHA, 'quadros.js', 'analise.js'],
    catalogo: [{id: 'alpha', titulo: 'Alfa', rodadas: [{id: 'R001', geracoes: ['g1']}]}],
    api: (operacao, dados) => ({
      inventario: {caso_id: 'alpha', documentos: [{id: 'D001', nome_recebido: 'contrato_v1.txt', arquivo: 'a'}, {id: 'D002', nome_recebido: 'contrato_v2.txt', arquivo: 'b'}]},
      'comparar-documentos': COMPARACAO, 'tabelas-listar': {caso: 'alpha', tabelas: [{id: TABELA.id, titulo: TABELA.titulo, total_linhas: 3}], total: 1},
      'tabelas-detalhe': TABELA, 'mapa-ver': MAPA, 'achados-original': 'bytes',
    })[operacao] ?? {},
    preparar: janela => {
      const original = janela.fetch;
      janela.fetch = async (rota, opcoes) => String(rota) === '/api/integracao' ? {ok: true, json: async () => integracao} : original(rota, opcoes);
    },
  });
  m.avaliar("window.contextoCaso = () => 'alpha'; window.abrirOriginal = async () => {};");
  return m;
}
async function aba(m, id) { m.$('ver-quadros').click(); await m.esperar(8); m.$(`quadros-aba-${id}`).click(); await m.esperar(10); return m.$(`quadros-${id}`); }

test('as abas do comparador, das tabelas e do mapa entram na mesma lista de abas', async () => {
  const m = mesa(); m.$('ver-quadros').click(); await m.esperar(8);
  assert.deepEqual(m.$('quadros-abas').querySelectorAll('[role=tab]').map(b => b.id),
    ['quadros-aba-hipoteses', 'quadros-aba-tempo', 'quadros-aba-comparador', 'quadros-aba-tabelas', 'quadros-aba-mapa']);
});

test('comparador destaca a diferença com o contexto dos dois lados, sem rótulo de culpa', async () => {
  const m = mesa(); const painel = await aba(m, 'comparador');
  assert.deepEqual(painel.querySelector('#comparar-documento-a').options.map(o => o.value), ['D001', 'D002']);
  assert.equal(painel.querySelector('#comparar-documento-b').value, 'D002');
  painel.querySelector('form').requestSubmit(); await m.esperar(8);
  assert.deepEqual(m.chamadas.at(-1), {operacao: 'comparar-documentos', dados: {caso: 'alpha', rodada: 'R001', documento_a: 'D001', documento_b: 'D002', contexto: 2}});
  const alt = painel.querySelector('.comparar-alteracao');
  assert.match(alt.querySelector('h4').textContent, /Diferença de valor/);
  assert.equal(alt.querySelector('del').textContent, 'R$ 8.750.000,00.');
  assert.equal(alt.querySelector('ins').textContent, 'R$ 10.937.500,00.');
  assert.equal(alt.querySelectorAll('.comparar-contexto').length, 2, 'linha anterior nos dois lados');
  assert.match(alt.textContent, /linha 6/);
  assert.match(alt.textContent, /Diferença calculada \(b - a\): 2187500 R\$/);
  assert.match(painel.textContent, /páginas sem texto \(3\)/);
  assert.doesNotMatch(painel.textContent, /fraude|culpa|irregular/i);
});

test('tabela conferível: fonte da célula no foco, célula corrigida marcada e navegação por setas', async () => {
  const m = mesa(); const painel = await aba(m, 'tabelas');
  const celulas = painel.querySelectorAll('td.tabela-celula');
  assert.equal(celulas.length, 6);
  assert.equal(celulas[0].getAttribute('tabindex'), '0');
  assert.equal(celulas[1].getAttribute('tabindex'), '-1');
  const corrigida = celulas[3];
  assert.ok(corrigida.classList.contains('estado-corrigido_manual'));
  assert.match(corrigida.textContent, /corrigida manualmente/);
  corrigida.dispatchEvent(new Evento('focus'));
  const fonte = painel.querySelector('#tabela-fonte');
  assert.match(fonte.textContent, /D003 · Pagamentos!B2/);
  assert.match(fonte.textContent, /Corrigida por Ana/);
  assert.match(fonte.textContent, /Valor anterior: 1154\.50/);
  assert.match(fonte.textContent, /Dígitos trocados/);
  assert.deepEqual(fonte.querySelectorAll('[translate=no]').map(n => n.textContent).filter(x => ['Ana', '1154.50'].includes(x)), ['Ana', '1154.50'],
    'autor e valor anterior são dados, fora da tradução');
  assert.match(celulas[4].textContent, /pendente/);
  let anuncios = 0; celulas[2].addEventListener('focus', () => anuncios++);
  celulas[0].dispatchEvent(new Evento('keydown', {key: 'ArrowDown', cancelable: true}));
  assert.equal(m.doc.activeElement, celulas[2]);
  assert.equal(anuncios, 0, 'a seta só move o foco; o navegador dispara o focus uma vez');
  assert.equal(celulas[2].getAttribute('tabindex'), '0');
  celulas[2].dispatchEvent(new Evento('keydown', {key: 'ArrowRight', cancelable: true}));
  assert.equal(m.doc.activeElement, celulas[3]);
});

test('painel de cálculo mostra operação, células usadas e resultado, e destaca as células', async () => {
  const m = mesa(); const painel = await aba(m, 'tabelas');
  const calc = painel.querySelector('.tabela-calculo');
  assert.match(calc.textContent, /Operação: Soma/);
  assert.match(calc.textContent, /1200\.00 \+ 1145\.50 = 2345\.50 BRL/);
  assert.equal(calc.querySelectorAll('.tabela-usadas li').length, 2);
  calc.querySelector('button').click();
  const usadas = painel.querySelectorAll('td.is-usada').map(td => `${td.dataset.linha}|${td.dataset.coluna}`);
  assert.deepEqual(usadas, ['L0001|valor', 'L0002|valor']);
});

test('mapa: SVG sem biblioteca, forma por tipo, traço por situação e evidência em cada ligação', async () => {
  const m = mesa(); const painel = await aba(m, 'mapa');
  const desenho = painel.querySelector('svg.mapa-svg');
  assert.ok(desenho);
  assert.equal(desenho.querySelectorAll('.mapa-no.pessoa circle').length, 2);
  assert.equal(desenho.querySelectorAll('.mapa-no.organizacao rect').length, 1);
  const [documentada, inferida] = desenho.querySelectorAll('.mapa-ligacao');
  assert.ok(documentada.classList.contains('traco-solido'));
  assert.ok(inferida.classList.contains('traco-tracejado'));
  assert.equal(documentada.getAttribute('tabindex'), '0');
  const detalhe = painel.querySelector('.mapa-detalhe');
  documentada.dispatchEvent(new Evento('focus'));
  assert.match(detalhe.textContent, /Escolha uma ligação/, 'o foco só destaca; o painel ao vivo não muda');
  documentada.dispatchEvent(new Evento('keydown', {key: 'Enter', cancelable: true}));
  assert.match(detalhe.textContent, /Lúcia Prates — fiscal de contrato com — Construtora Exemplo Ltda\./);
  assert.match(detalhe.textContent, /Lúcia Prates, fiscal do contrato\./);
  detalhe.querySelector('button').click(); await m.esperar();
  assert.equal(m.chamadas.at(-1).operacao, 'achados-original');
  assert.match(painel.querySelector('.mapa-legenda').textContent, /Pessoa \(círculo\)/);
  assert.doesNotMatch(painel.textContent, /fraude|culpado/i);
});

test('mapa em lista acessível e lista lateral de homônimos, sem fundir entidades', async () => {
  const m = mesa(); const painel = await aba(m, 'mapa');
  const lista = painel.querySelector('.mapa-lista');
  assert.equal(lista.querySelectorAll('.mapa-entidade').length, 3, 'as duas grafias continuam no mapa');
  const lucia = lista.querySelectorAll('.mapa-entidade')[0];
  assert.match(lucia.textContent, /fiscal de contrato com Construtora Exemplo Ltda\./);
  assert.match(lucia.textContent, /MATRICULA 7781/);
  lucia.querySelector('button').click();
  assert.match(painel.querySelector('.mapa-detalhe').textContent, /Ata registra a função\./);
  const hom = painel.querySelector('.mapa-homonimos');
  assert.match(hom.textContent, /Lucia {2}PRATES · Lúcia Prates/);
  assert.match(hom.textContent, /Motivo: Nome igual/);
  assert.match(hom.textContent, /Conferência pendente/);
  assert.match(hom.textContent, /Nada é fundido/);
  assert.ok(hom.querySelectorAll('[translate=no]').some(n => n.textContent === 'matricula'), 'identificadores divergentes fora da tradução');
});

test('tabelas ficam atrás da verificação de disponibilidade da rota', async () => {
  const m = mesa({integracao: {quadros_evidencia: true}}); const painel = await aba(m, 'tabelas');
  assert.match(painel.textContent, /não está disponível neste servidor/);
  assert.equal(m.chamadas.filter(c => c.operacao.startsWith('tabelas-')).length, 0);
});

test('textos das telas de análise têm tradução para o inglês', () => {
  const m = mesa();
  const textos = m.janela.VLADO_I18N_EN.textos;
  for (const chave of ['Comparador', 'Tabelas', 'Mapa de relações', 'Diferença de valor', 'Comparar', 'Documento A', 'Documento B', 'Cálculos declarados',
    'Possíveis homônimos para conferência', 'Pessoa (círculo)', 'Organização (quadrado)', 'Ver evidências', 'Conferência pendente', 'Destacar células usadas',
    'Leve o foco a uma célula para ver a fonte, o estado e a última correção.', 'Lista de pessoas e organizações']) {
    assert.ok(textos[chave], `tradução de “${chave}”`);
  }
});
