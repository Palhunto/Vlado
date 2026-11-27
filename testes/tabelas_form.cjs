'use strict';
// Formulário da tabela (componentes.md#formularios-quadros, "Tabela"; interface/formularios.js) e correção de célula no painel "Célula selecionada" (P15.3),
// com dados sintéticos (Pagamentos 2024, Construtora Alfa). O servidor simulado registra cada salvamento com o corpo que receberia, na forma real de
// tabelas-detalhe (colunas, linhas com células {valor, fonte, estado} e evidencias resolvidas).
const test = require('node:test');
const assert = require('node:assert/strict');
const {criarMesa, Evento, PILHA} = require('./dom_minimo.cjs');

const referencia = n => ({tipo: 'ia', caso_id: 'alpha', rodada: 'R002', revisao: 'r3_sintese', registros_sha256: '7'.repeat(64), evidencia_id: `E00${n}`});
const IA = {rodada: 'R002', revisao: 'r3_sintese', registros_sha256: '7'.repeat(64), achado_id: 'A002', versao: 1, papel: 'suporte', suporte: 'sustentado', natureza: 'declaracao_documental', destino: 'incluido'};
const RESULTADO = {origem: 'ia', tipo_fonte: 'achado_ia', texto: 'Pagamento de R$ 1.200,00 em janeiro de 2024.', trecho: 'Pagamento de R$ 1.200,00…',
  documento: {documento_id: 'D003', nome: 'pagamentos_2024.xlsx'}, localizador: {legivel: 'D003 · Pagamentos!B2', pagina_pdf: null},
  achado: {id: 'A002', versao: 1, destino: 'incluido'}, revisao_ia: IA, conferencia_humana: null, estado: 'conferida',
  vinculo_sugerido: {referencia: referencia(3), papel: 'suporte', suporte: 'sustentado', natureza: 'declaracao_documental', justificativa: 'A planilha traz o pagamento.'}, ja_ligado: false};
const ID = 'Q' + '1'.repeat(32), SHA = 'e'.repeat(64);
const vinculoSalvo = (extra = {}) => ({referencia: referencia(3), papel: 'suporte', suporte: 'sustentado', natureza: 'declaracao_documental', justificativa: 'A planilha traz o pagamento.', documento_id: 'D003', estado: 'conferida',
  evidencia: {documento: {documento_id: 'D003', nome: 'pagamentos_2024.xlsx'}, trecho: 'Pagamento de R$ 1.200,00…', localizador: {legivel: 'D003 · Pagamentos!B2'}}, localizador: {legivel: 'D003 · Pagamentos!B2'},
  revisao_ia: IA, preenchimento_ia: {papel: 'suporte', suporte: 'sustentado', natureza: 'declaracao_documental', destino: 'incluido'}, alteracoes: {}, conferencia_humana: null, ...extra});
const celula = (valor, estado, fonte, extra = {}) => ({valor, fonte, estado, fonte_legivel: fonte === null ? null : 'D003 · Pagamentos!B2', fonte_conferida: fonte !== null, ultima_correcao: null, ...extra});
const TABELA = () => ({caso: 'alpha', id: ID, sha256: SHA, versao: {sequencia: 1, sha256: SHA}, titulo: 'Pagamentos 2024', descricao: 'Pagamentos à Construtora Alfa.', aviso: 'Valores como registrados nas fontes.',
  colunas: [{id: 'data', nome: 'Data', tipo: 'data', moeda: null, unidade: null}, {id: 'valor', nome: 'Valor', tipo: 'monetario', moeda: 'BRL', unidade: null}],
  linhas: [{id: 'L0001', celulas: {data: celula('2024-01', 'extraido', 0), valor: celula('1200.00', 'extraido', 0)}},
    {id: 'L0002', celulas: {data: celula(null, 'pendente', null), valor: celula('1145.50', 'pendente', null)}}],
  evidencias: [vinculoSalvo()], calculos: [], celulas_por_estado: {extraido: 2, corrigido_manual: 0, pendente: 2}, retirado: false, motivo_retirada: '', historico: []});

function montar({permissao = true, tabelas = [], detalhe = TABELA()} = {}) {
  const salvos = [];
  const m = criarMesa({scripts: [...PILHA, 'quadros.js', 'sugestoes.js', 'formularios.js', 'analise.js', 'indicador_salvamento.js'], desktop: true,
    api: (operacao, dados) => {
      if (operacao === 'tabelas-listar') return {caso: 'alpha', total: tabelas.length, divergentes: [], aviso: '', tabelas: tabelas.map(id => ({id, titulo: detalhe.titulo, total_linhas: detalhe.linhas.length}))};
      if (operacao === 'tabelas-detalhe') return detalhe;
      if (operacao === 'sugestoes-listar') return {caso: 'alpha', quadro: dados.quadro, contagem: {}, sugestoes: []};
      if (operacao === 'evidencia-buscar') return {caso: 'alpha', analise: {rodada: 'R002', em_utc: '2026-11-26T17:32:00+00:00', pergunta: 'Quanto foi pago?'}, analises: [], total: 1, resultados: [RESULTADO]};
      if (/^tabelas-(criar|atualizar|corrigir)$/.test(operacao)) { salvos.push({operacao, dados}); return {id: ID, sha256: 'f'.repeat(64)}; }
      return {};
    },
    preparar: janela => {
      const original = janela.fetch;
      janela.fetch = async (rota, opcoes) => String(rota) === '/api/integracao' ? {ok: true, json: async () => ({quadros_evidencia: true, tabelas_apuracao: true})} : original(rota, opcoes);
    }});
  m.avaliar('window.contextoCaso = () => "alpha";');
  if (!permissao) m.avaliar('window.Sessao = {pode: () => false, pronta: Promise.resolve()};');
  return {...m, salvos};
}
const espera = async m => { await new Promise(r => setTimeout(r, 12)); await m.esperar(10); };
const texto = no => no.textContent.replace(/\s+/g, ' ').trim();
async function abrirAba(m) { m.$('ver-quadros').click(); await espera(m); m.$('quadros-aba-tabelas').click(); await espera(m); }
const por = (raiz, seletor, rotulo) => [...raiz.querySelectorAll(seletor)].find(b => texto(b) === rotulo);
const digitar = (no, valor) => { no.value = valor; no.dispatchEvent(new Evento('input', {bubbles: true})); };
const escolher = (sel, v) => { sel.value = v; sel.dispatchEvent(new Evento('change', {bubbles: true})); };
const clicar = async (m, no) => { no.click(); await espera(m); };
async function ligarEvidencia(m, painel) {
  await clicar(m, por(painel, 'button', '+ Ligar evidência'));
  await clicar(m, painel.querySelector('.seletor-resultado'));
  await clicar(m, por(painel, '.seletor-aberto button', 'Ligar'));
  assert.ok(painel.querySelector('.form-quadro'), 'de volta ao formulário');
}
const justificar = painel => { for (const a of painel.querySelectorAll('.vinculo-cartao textarea')) if (!a.value) digitar(a, 'A planilha traz o pagamento.'); };

test('nova tabela: colunas por tipo, linha com valores em notação brasileira e fonte por célula; salva por tabelas-criar', async () => {
  const m = montar(); await abrirAba(m);
  const painel = m.$('quadros-tabelas');
  assert.match(texto(painel), /Nenhuma tabela ainda/);
  await clicar(m, por(painel, 'button', '+ Nova tabela'));
  assert.equal(texto(painel.querySelector('.form-titulo')), 'Nova tabela');
  digitar(painel.querySelector('.form-campo input[type=text]'), 'Pagamentos 2025');
  digitar(painel.querySelector('.form-coluna input[type=text]'), 'Descrição');
  await clicar(m, por(painel, 'button', '+ Coluna'));
  await clicar(m, por(painel, 'button', '+ Coluna'));
  let colunas = () => [...painel.querySelectorAll('.form-coluna')];
  digitar(colunas()[1].querySelector('input[type=text]'), 'Valor pago');
  escolher(colunas()[1].querySelector('select'), 'monetario'); await espera(m);
  digitar(colunas()[2].querySelector('input[type=text]'), 'Quantidade');
  escolher(colunas()[2].querySelector('select'), 'numero'); await espera(m);
  assert.equal(colunas()[1].querySelectorAll('input[type=text]')[1].value, 'BRL', 'moeda sugerida para valor monetário');
  await ligarEvidencia(m, painel); justificar(painel);
  await clicar(m, por(painel, 'button', '+ Adicionar linha'));
  const novas = () => [...painel.querySelectorAll('.form-linha-nova input[type=text]')];
  digitar(novas()[0], 'Pagamento de janeiro'); digitar(novas()[1], '8.750.000,50'); digitar(novas()[2], '12');
  escolher([...painel.querySelectorAll('.form-linha-nova select')][1], '0');
  // número exige a unidade: a mensagem aparece no campo, nada é enviado
  await clicar(m, por(painel, 'button', 'Salvar'));
  assert.equal(m.salvos.length, 0);
  assert.match(texto(painel.querySelector('.form-erro-geral')), /Falta a unidade|Número exige a unidade/);
  digitar(colunas()[2].querySelectorAll('input[type=text]')[1], 'itens');
  await clicar(m, por(painel, 'button', 'Salvar'));
  assert.equal(m.salvos.length, 1, texto(painel.querySelector('.form-erro-geral') || painel));
  const {operacao, dados} = m.salvos[0];
  assert.equal(operacao, 'tabelas-criar'); assert.equal(dados.caso, 'alpha');
  assert.match(dados.requisicao_id, /^[0-9a-f]{32}$/);
  assert.equal(dados.titulo, 'Pagamentos 2025'); assert.equal(dados.descricao, '');
  assert.deepEqual(JSON.parse(JSON.stringify(dados.colunas)), [{id: 'descricao', nome: 'Descrição', tipo: 'texto', moeda: null, unidade: null},
    {id: 'valor_pago', nome: 'Valor pago', tipo: 'monetario', moeda: 'BRL', unidade: null}, {id: 'quantidade', nome: 'Quantidade', tipo: 'numero', moeda: null, unidade: 'itens'}]);
  assert.deepEqual(JSON.parse(JSON.stringify(dados.linhas)), [{celulas: {descricao: {valor: 'Pagamento de janeiro', fonte: null}, valor_pago: {valor: '8750000.50', fonte: 0}, quantidade: {valor: '12', fonte: null}}}],
    'o número vai com ponto decimal e sem milhar; a célula sem fonte vai com fonte nula (○ a conferir)');
  assert.deepEqual(JSON.parse(JSON.stringify(dados.evidencias)), [{referencia: referencia(3), achado_id: 'A002', papel: 'suporte', suporte: 'sustentado', natureza: 'declaracao_documental', justificativa: 'A planilha traz o pagamento.'}]);
});

test('nova tabela: título e número inválido apontam o campo, e a data vai no formato do servidor', async () => {
  const m = montar(); await abrirAba(m);
  const painel = m.$('quadros-tabelas');
  await clicar(m, por(painel, 'button', '+ Nova tabela'));
  await clicar(m, por(painel, 'button', 'Salvar'));
  assert.match(texto(painel.querySelector('.form-erro-geral')), /Escreva o título da tabela\./);
  assert.equal(m.salvos.length, 0);
  digitar(painel.querySelector('.form-campo input[type=text]'), 'Datas');
  digitar(painel.querySelector('.form-coluna input[type=text]'), 'Assinatura');
  escolher(painel.querySelector('.form-coluna select'), 'data'); await espera(m);
  await clicar(m, por(painel, 'button', '+ Adicionar linha'));
  digitar(painel.querySelector('.form-linha-nova input[type=text]'), '31/02/20');
  await clicar(m, por(painel, 'button', 'Salvar'));
  assert.equal(m.salvos.length, 0);
  assert.match(texto(painel.querySelector('.form-linha-nova')), /Use ano, mês e ano ou dia completo/);
  digitar(painel.querySelector('.form-linha-nova input[type=text]'), '03/03/2025');
  await clicar(m, por(painel, 'button', 'Salvar'));
  assert.equal(m.salvos.length, 1);
  assert.deepEqual(JSON.parse(JSON.stringify(m.salvos[0].dados.linhas)), [{celulas: {assinatura: {valor: '2025-03-03', fonte: null}}}]);
});

test('editar tabela: as linhas e colunas registradas voltam como estão salvas; só acrescenta coluna e linha; salva por tabelas-atualizar com anterior_sha256', async () => {
  const m = montar({tabelas: [ID]}); await abrirAba(m);
  const painel = m.$('quadros-tabelas');
  await clicar(m, por(painel, 'button', 'Editar'));
  assert.equal(texto(painel.querySelector('.form-titulo')), 'Editar tabela');
  assert.match(texto(painel), /2 linhas já registradas\. Para corrigir uma célula, escolha-a na tabela/);
  assert.match(texto(painel.querySelector('.form-coluna')), /já registrada: só o nome muda/);
  assert.equal(painel.querySelectorAll('.form-coluna select').length, 0, 'tipo e unidade de coluna registrada não se editam');
  await clicar(m, por(painel, 'button', '+ Coluna'));
  digitar([...painel.querySelectorAll('.form-coluna')].pop().querySelector('input[type=text]'), 'Observação');
  await clicar(m, por(painel, 'button', '+ Adicionar linha'));
  const novas = [...painel.querySelectorAll('.form-linha-nova input[type=text]')];
  assert.equal(novas.length, 3, 'a linha nova tem uma célula por coluna');
  digitar(novas[0], '03/2024'); digitar(novas[1], '980,00');
  await clicar(m, por(painel, 'button', 'Salvar'));
  assert.equal(m.salvos.length, 1, texto(painel.querySelector('.form-erro-geral') || painel));
  const {operacao, dados} = m.salvos[0];
  assert.equal(operacao, 'tabelas-atualizar'); assert.equal(dados.id, ID); assert.equal(dados.anterior_sha256, SHA);
  const d = JSON.parse(JSON.stringify(dados));
  assert.deepEqual(d.colunas, [{id: 'data', nome: 'Data', tipo: 'data', moeda: null, unidade: null}, {id: 'valor', nome: 'Valor', tipo: 'monetario', moeda: 'BRL', unidade: null},
    {id: 'observacao', nome: 'Observação', tipo: 'texto', moeda: null, unidade: null}]);
  assert.deepEqual(d.linhas[0], {id: 'L0001', celulas: {data: {valor: '2024-01', fonte: 0, estado: 'extraido'}, valor: {valor: '1200.00', fonte: 0, estado: 'extraido'}}},
    'a linha registrada volta exatamente como o servidor a guardou, sem a coluna nova');
  assert.deepEqual(d.linhas[1], {id: 'L0002', celulas: {data: {valor: null, fonte: null, estado: 'pendente'}, valor: {valor: '1145.50', fonte: null, estado: 'pendente'}}});
  assert.deepEqual(d.linhas[2], {celulas: {data: {valor: '2024-03', fonte: null}, valor: {valor: '980.00', fonte: null}, observacao: {valor: null, fonte: null}}});
  assert.equal(d.evidencias.length, 1); assert.equal(d.evidencias[0].justificativa, 'A planilha traz o pagamento.');
});

test('a evidência que é a fonte de uma célula não se desliga (o servidor recusaria): a tela diz antes', async () => {
  const m = montar({tabelas: [ID]}); await abrirAba(m);
  const painel = m.$('quadros-tabelas');
  await clicar(m, por(painel, 'button', 'Editar'));
  await clicar(m, por(painel, 'button', 'Desligar'));
  assert.equal(painel.querySelectorAll('.vinculo-cartao').length, 1, 'continua ligada');
  assert.match(texto(painel.querySelector('.form-erro-geral')), /Esta evidência é a fonte de uma célula\. Troque a fonte da célula antes de desligá-la\./);
});

test('corrigir uma célula: justificativa obrigatória ao mudar o que existia, valor anterior guardado pelo servidor; preencher o que faltava não pede', async () => {
  const m = montar({tabelas: [ID]}); await abrirAba(m);
  const painel = m.$('quadros-tabelas');
  const celulas = painel.querySelectorAll('td.tabela-celula');
  celulas[1].dispatchEvent(new Evento('focus'));
  const fonte = painel.querySelector('#tabela-fonte');
  await clicar(m, por(fonte, 'button', 'Corrigir esta célula'));
  assert.equal(texto(fonte.querySelector('.form-titulo')), 'Corrigir a célula');
  celulas[3].dispatchEvent(new Evento('mouseenter'));
  assert.match(texto(fonte), /Corrigir a célula/, 'o painel não troca de célula enquanto o formulário está aberto');
  const campo = () => fonte.querySelector('.form-celula input[type=text]');
  assert.equal(campo().value, '1200,00', 'o campo chega com o valor registrado, em notação brasileira');
  await clicar(m, por(fonte, 'button', 'Salvar correção'));
  assert.match(texto(fonte.querySelector('.form-erro-geral')), /Mude o valor ou a fonte/);
  digitar(campo(), '1.020,00');
  await clicar(m, por(fonte, 'button', 'Salvar correção'));
  assert.equal(m.salvos.length, 0);
  assert.match(texto(fonte), /Escreva a justificativa da correção\./);
  digitar(fonte.querySelector('textarea'), 'A planilha original traz 1.020,00.');
  await clicar(m, por(fonte, 'button', 'Salvar correção'));
  assert.equal(m.salvos.length, 1, texto(fonte));
  assert.equal(m.salvos[0].operacao, 'tabelas-corrigir');
  assert.deepEqual(JSON.parse(JSON.stringify(m.salvos[0].dados)), {caso: 'alpha', requisicao_id: m.salvos[0].dados.requisicao_id, id: ID, anterior_sha256: SHA,
    correcoes: [{linha: 'L0001', coluna: 'valor', valor: '1020.00', fonte: 0, justificativa: 'A planilha original traz 1.020,00.'}]});
  // célula pendente: preencher a fonte e o valor que faltavam não é correção
  m.salvos.length = 0;
  const outras = painel.querySelectorAll('td.tabela-celula');
  outras[2].dispatchEvent(new Evento('focus'));
  const fonte2 = painel.querySelector('#tabela-fonte');
  await clicar(m, por(fonte2, 'button', 'Corrigir esta célula'));
  digitar(fonte2.querySelector('.form-celula input[type=text]'), '02/2024');
  escolher(fonte2.querySelector('.form-celula select'), '0');
  await clicar(m, por(fonte2, 'button', 'Salvar correção'));
  assert.equal(m.salvos.length, 1, texto(fonte2));
  assert.deepEqual(JSON.parse(JSON.stringify(m.salvos[0].dados.correcoes)), [{linha: 'L0002', coluna: 'data', valor: '2024-02', fonte: 0, justificativa: ''}]);
  assert.deepEqual(m.erros, []);
});

test('sem a capacidade de atualizar tabelas, nem "Nova tabela", nem "Editar", nem "Corrigir esta célula" aparecem', async () => {
  const m = montar({tabelas: [ID], permissao: false}); await abrirAba(m);
  const painel = m.$('quadros-tabelas');
  assert.ok(!por(painel, 'button', 'Editar'));
  assert.ok(!por(painel, 'button', '+ Nova tabela'));
  painel.querySelectorAll('td.tabela-celula')[0].dispatchEvent(new Evento('focus'));
  assert.ok(!por(painel.querySelector('#tabela-fonte'), 'button', 'Corrigir esta célula'));
});

test('R1 da Coruja: número no formato brasileiro, o ponto é milhar e a vírgula é decimal; ponto ambíguo é recusado, nunca adivinhado', async () => {
  const m = montar();
  const ler = texto => JSON.parse(m.avaliar(`JSON.stringify(window.Quadros.formularios.numeroDoTexto(${JSON.stringify(texto)}))`));
  for (const [entrada, valor] of [['1.500', '1500'], ['8.750.000', '8750000'], ['1.500,25', '1500.25'], ['0,5', '0.5'], ['12', '12'], ['8.750.000,50', '8750000.50'], ['-1.200,00', '-1200.00'], ['  1 500 ', null], ['1500,5', '1500.5']]) {
    if (valor === null) continue;
    assert.deepEqual(ler(entrada), {valor}, entrada);
  }
  assert.deepEqual(ler(''), {vazio: true});
  for (const ambiguo of ['1.5', '8.75', '1.50', '0.500', '1.5000', '1.500.5', '1.5,2']) assert.match(ler(ambiguo).erro, /O ponto separa milhares/, `${ambiguo} é ambíguo: recusa`);
  for (const invalido of ['abc', '1,2,3', '12,', '1e3', '1,5a']) assert.match(ler(invalido).erro, /Escreva só o número, com vírgula decimal/, `${invalido} não é número`);
});

test('R1 da Coruja: na célula, "1.500" vai como 1500 e "1.5" fica no campo com a mensagem, sem enviar', async () => {
  const m = montar(); await abrirAba(m);
  const painel = m.$('quadros-tabelas');
  await clicar(m, por(painel, 'button', '+ Nova tabela'));
  digitar(painel.querySelector('.form-campo input[type=text]'), 'Valores');
  digitar(painel.querySelector('.form-coluna input[type=text]'), 'Valor');
  escolher(painel.querySelector('.form-coluna select'), 'monetario'); await espera(m);
  await clicar(m, por(painel, 'button', '+ Adicionar linha'));
  const celula = () => painel.querySelector('.form-linha-nova input[type=text]');
  digitar(celula(), '1.5');
  await clicar(m, por(painel, 'button', 'Salvar'));
  assert.equal(m.salvos.length, 0);
  assert.match(texto(painel.querySelector('.form-linha-nova')), /O ponto separa milhares/);
  digitar(celula(), '1.500');
  await clicar(m, por(painel, 'button', 'Salvar'));
  assert.equal(m.salvos.length, 1, texto(painel.querySelector('.form-erro-geral') || painel));
  assert.deepEqual(JSON.parse(JSON.stringify(m.salvos[0].dados.linhas)), [{celulas: {valor: {valor: '1500', fonte: null}}}]);
});

test('R1 da Coruja: a correção de célula usa a mesma regra ("8.750.000" vai como 8750000; "8.75" é recusado no campo)', async () => {
  const m = montar({tabelas: [ID]}); await abrirAba(m);
  const painel = m.$('quadros-tabelas');
  painel.querySelectorAll('td.tabela-celula')[1].dispatchEvent(new Evento('focus'));
  const fonte = painel.querySelector('#tabela-fonte');
  await clicar(m, por(fonte, 'button', 'Corrigir esta célula'));
  const campo = () => fonte.querySelector('.form-celula input[type=text]');
  digitar(campo(), '8.75'); digitar(fonte.querySelector('textarea'), 'Conferido na planilha.');
  await clicar(m, por(fonte, 'button', 'Salvar correção'));
  assert.equal(m.salvos.length, 0);
  assert.match(texto(fonte), /O ponto separa milhares/);
  digitar(campo(), '8.750.000');
  await clicar(m, por(fonte, 'button', 'Salvar correção'));
  assert.equal(m.salvos.length, 1, texto(fonte));
  assert.equal(m.salvos[0].dados.correcoes[0].valor, '8750000');
});
