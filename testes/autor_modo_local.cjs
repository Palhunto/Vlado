'use strict';
// Modo local (o padrão da Mesa no Windows): sem conta, o servidor exige o nome de quem grava ("Autor: informe texto válido, até 120 caracteres.", 400) em toda gravação
// dos quadros, das tabelas e das decisões sobre sugestões. Achado pela Coruja na cópia dos casos reais: nenhum item de quadro salvava pela tela, porque os formulários não
// mandavam autor e os testes de rota sempre o mandavam à mão. Aqui o servidor simulado RECUSA o pedido sem autor válido, como o real, e o nome só entra por onde a pessoa o
// digita (o campo "Autor"); o teste nunca põe um autor no corpo.
const test = require('node:test');
const assert = require('node:assert/strict');
const {criarMesa, Evento, PILHA} = require('./dom_minimo.cjs');

const HID = 'H' + '1'.repeat(32), GID = 'G' + '9'.repeat(32), ALFA = 'P' + 'a'.repeat(32), TID = 'Q' + '1'.repeat(32);
const referencia = n => ({tipo: 'ia', caso_id: 'alpha', rodada: 'R002', revisao: 'r3_sintese', registros_sha256: '7'.repeat(64), evidencia_id: `E00${n}`});
const IA = {rodada: 'R002', revisao: 'r3_sintese', registros_sha256: '7'.repeat(64), achado_id: 'A002', versao: 1, papel: 'suporte', suporte: 'sustentado', natureza: 'declaracao_documental', destino: 'incluido'};
const salvoV = {referencia: referencia(3), papel: 'suporte', suporte: 'sustentado', natureza: 'declaracao_documental', justificativa: 'O contrato social lista Marta Reis.'};
const resolvida = {referencia: referencia(3), estado: 'conferida', documento: {documento_id: 'D002', nome: 'contrato_social_alfa.pdf'}, localizador: {legivel: 'D002 · página PDF 1', pagina_pdf: 1},
  trecho: 'Marta Reis, sócia-administradora…', revisao_ia: IA, conferencia_humana: null};
const sugestao = (n, tipo, quadro, campos, extra = {}) => ({id: 'S' + String(n).repeat(32), tipo, quadro, campos: {...campos, evidencias: [salvoV]}, evidencias: [resolvida],
  achado: {id: 'A002', versao: 1, redacao: 'Marta Reis é sócia da Construtora Alfa.', natureza: 'declaracao_documental', suporte_ia: 'sustentado', destino: 'incluido', motivo_destino: '', versao_atual: 1},
  analise: {caso: 'alpha', rodada: 'R002', em_utc: '2026-11-26T17:32:00', pergunta: 'Quem são os sócios?'}, estado: 'aberta', decisao: null, descartada_antes: null, bloqueio: null, avisos: [], ...extra});
const celula = (valor, estado, fonte) => ({valor, fonte, estado, fonte_legivel: fonte === null ? null : 'D003 · B2', fonte_conferida: fonte !== null, ultima_correcao: null});

// o servidor real: sem conta, toda gravação precisa do nome (caderno.autoria → _texto(..., 'Autor', 120))
const SALVA = /^(hipoteses|linha-tempo|mapa-entidade|mapa-relacao|tabelas)-(criar|atualizar|corrigir)$|^sugestoes-(confirmar|corrigir|descartar|restaurar)$|^diligencias-criar$|^redacao-vincular$/;
const autorValido = a => typeof a === 'string' && a.trim().length >= 1 && a.length <= 120;

function montar({modo = 'local'} = {}) {
  const gravados = [], decididas = new Map();
  let sugestoes = [sugestao(1, 'hipotese', 'hipoteses', {enunciado: 'A sócia assinou também como testemunha.', situacao: 'em_aberto', lacunas: []}),
    sugestao(2, 'organizacao', 'mapa', {tipo: 'organizacao', nome: 'Construtora Alfa Ltda.', variantes: [], identificadores: []}),
    sugestao(3, 'pessoa', 'mapa', {tipo: 'pessoa', nome: 'Marta Reis', variantes: [], identificadores: []}, {estado: 'descartada'})];
  let criouHipotese = false;
  const m = criarMesa({modo, scripts: [...PILHA, 'quadros.js', 'sugestoes.js', 'formularios.js', 'analise.js', 'indicador_salvamento.js'], desktop: true,
    catalogo: [{id: 'alpha', titulo: 'Alfa', rodadas: [{id: 'R002', geracoes: ['g1']}]}],
    api: (operacao, dados) => {
      if (SALVA.test(operacao)) {
        if (modo === 'local' && !autorValido(dados.autor)) throw Object.assign(new Error('Autor: informe texto válido, até 120 caracteres.'), {status: 400});
        gravados.push([operacao, dados]);
      }
      if (operacao === 'hipoteses-quadro') return {caso: 'alpha', total: 1, divergentes: [], aviso: '', hipoteses: [{id: HID, enunciado: 'A dispensa seguiu o rito legal.', situacao: 'em_aberto', condicao: 'pendencia', natureza: null,
        situacao_sem_base: false, sustentam: [], contrariam: [], contexto: [], indisponiveis: [], faltam: [{origem: 'registrada', descricao: 'Parecer jurídico.', diligencia_id: null, diligencia_estado: null}]}]};
      if (operacao === 'hipoteses-detalhe') return {id: HID, sha256: 'e'.repeat(64), estado: {enunciado: 'A dispensa seguiu o rito legal.', situacao: 'em_aberto', evidencias: [], lacunas: [{descricao: 'Parecer jurídico.', diligencia_id: null}]}, evidencias: []};
      if (operacao === 'mapa-ver') return {caso: 'alpha', aviso: '', homonimos: [], relacoes: [], entidades: [{id: ALFA, nome: 'Construtora Alfa Ltda.', tipo: 'organizacao', situacao: 'com_evidencia', identificadores: []}]};
      if (operacao === 'tabelas-listar') return {caso: 'alpha', total: 1, divergentes: [], aviso: '', tabelas: [{id: TID, titulo: 'Pagamentos', total_linhas: 1}]};
      if (operacao === 'tabelas-detalhe') return {caso: 'alpha', id: TID, sha256: 'e'.repeat(64), versao: {sequencia: 1}, titulo: 'Pagamentos', descricao: '', aviso: '', colunas: [{id: 'valor', nome: 'Valor', tipo: 'monetario', moeda: 'BRL', unidade: null}],
        linhas: [{id: 'L0001', celulas: {valor: celula('1200.00', 'pendente', null)}}], evidencias: [], calculos: [], celulas_por_estado: {extraido: 0, corrigido_manual: 0, pendente: 1}, retirado: false, motivo_retirada: '', historico: []};
      if (operacao === 'sugestoes-listar') {
        const lista = sugestoes.filter(s => s.quadro === dados.quadro && (dados.incluir_decididas || s.estado !== 'confirmada'));
        return {caso: 'alpha', quadro: dados.quadro, contagem: {}, sugestoes: lista};
      }
      if (/^sugestoes-(confirmar|corrigir|descartar|restaurar)$/.test(operacao)) {
        const acao = operacao.split('-')[1], alvo = sugestoes.find(s => s.id === dados.id);
        alvo.estado = {confirmar: 'confirmada', corrigir: 'confirmada', descartar: 'descartada', restaurar: 'aberta'}[acao];
        if (acao === 'confirmar' || acao === 'corrigir') alvo.decisao = {acao, por: dados.autor, conta_id: null, em_utc: '2026-11-27T10:05:00', item_id: ALFA, quadro: alvo.quadro};
        return {sugestao: alvo, item: alvo.decisao ? {id: ALFA} : null};
      }
      if (operacao === 'diligencias-criar') return {caso: 'alpha', id: GID, diligencia: {estado: 'a_solicitar'}};
      if (/-(criar|atualizar|corrigir)$/.test(operacao)) { criouHipotese ||= operacao === 'hipoteses-criar'; return {id: HID, sha256: 'f'.repeat(64)}; }
      if (operacao === 'evidencia-buscar') return {caso: 'alpha', analise: null, analises: [], total: 0, resultados: []};
      return {};
    },
    preparar: janela => {
      const original = janela.fetch;
      janela.fetch = async (rota, opcoes) => String(rota) === '/api/integracao' ? {ok: true, json: async () => ({quadros_evidencia: true, tabelas_apuracao: true})} : original(rota, opcoes);
    }});
  m.avaliar('window.contextoCaso = () => "alpha";');
  return {...m, gravados};
}
const espera = async m => { await new Promise(r => setTimeout(r, 12)); await m.esperar(10); };
const texto = no => no.textContent.replace(/\s+/g, ' ').trim();
const digitar = (no, valor) => { no.value = valor; no.dispatchEvent(new Evento('input', {bubbles: true})); };
const clicar = async (m, no) => { no.click(); await espera(m); };
const por = (raiz, seletor, rotulo) => [...raiz.querySelectorAll(seletor)].find(b => texto(b) === rotulo);
async function abrirAba(m, aba) { m.$('ver-quadros').click(); await espera(m); m.$(`quadros-aba-${aba}`).click(); await espera(m); }
// o campo "Autor" do painel ou do formulário: o único lugar por onde o nome entra
const autor = raiz => [...(raiz.querySelector('.form-quadro') || raiz).querySelectorAll('.form-campo')].find(c => texto(c.querySelector('.form-rotulo') || c).startsWith('Autor'))?.querySelector('input');

test('hipótese: no modo local o formulário pede o Autor, não envia sem ele e salva com o nome digitado; o nome fica lembrado', async () => {
  const m = montar(); await abrirAba(m, 'hipoteses');
  const painel = m.$('quadros-hipoteses');
  await clicar(m, por(painel, 'button', '+ Nova hipótese'));
  assert.ok(autor(painel), 'o campo Autor existe no modo local');
  assert.equal(autor(painel).value, '', 'sem nome lembrado, vazio');
  digitar(painel.querySelector('textarea'), 'A sócia assinou como testemunha.');
  await clicar(m, por(painel, 'button', 'Salvar'));
  assert.equal(m.gravados.length, 0, 'sem o nome nada é enviado');
  assert.match(texto(painel.querySelector('.form-erro-geral')), /Escreva o seu nome em Autor para salvar\./);
  assert.ok(m.doc.activeElement === autor(painel), 'o foco vai ao campo');
  digitar(autor(painel), 'Ana Lima');
  await clicar(m, por(painel, 'button', 'Salvar'));
  assert.equal(m.gravados.length, 1, texto(painel));
  assert.equal(m.gravados[0][0], 'hipoteses-criar'); assert.equal(m.gravados[0][1].autor, 'Ana Lima');
  // o segundo formulário já chega com o último nome usado
  await clicar(m, por(painel, 'button', '+ Nova hipótese'));
  assert.equal(autor(painel).value, 'Ana Lima');
  assert.deepEqual(m.erros, []);
});

test('o nome tem até 120 caracteres, e Retirar… também leva o Autor (sem ele, a retirada não sai)', async () => {
  const m = montar(); await abrirAba(m, 'tabelas');
  const painel = m.$('quadros-tabelas');
  await clicar(m, por(painel, 'button', 'Editar'));
  assert.equal(autor(painel).maxLength, 120);
  await clicar(m, por(painel, 'button', 'Retirar…'));
  digitar(painel.querySelector('.form-retirada textarea'), 'Tabela duplicada.');
  const antes = m.gravados.length;
  await clicar(m, por(painel, '.form-retirada button', 'Retirar'));
  assert.equal(m.gravados.length, antes, 'sem o nome, a retirada não sai');
  assert.match(texto(painel.querySelector('.form-retirada')), /Escreva o seu nome em Autor para salvar\./);
  digitar(autor(painel), 'Ana Lima');
  await clicar(m, por(painel, '.form-retirada button', 'Retirar'));
  const [operacao, dados] = m.gravados.at(-1);
  assert.equal(operacao, 'tabelas-atualizar'); assert.equal(dados.retirado, true); assert.equal(dados.autor, 'Ana Lima');
});

test('tabela: criar, e corrigir uma célula pelo painel, levam o Autor digitado', async () => {
  const m = montar(); await abrirAba(m, 'tabelas');
  const painel = m.$('quadros-tabelas');
  await clicar(m, por(painel, 'button', 'Editar'));
  digitar(autor(painel), 'Ana Lima');
  await clicar(m, por(painel, 'button', 'Salvar'));
  assert.equal(m.gravados.at(-1)[0], 'tabelas-atualizar'); assert.equal(m.gravados.at(-1)[1].autor, 'Ana Lima');
  await abrirAba(m, 'tabelas');
  const painel2 = m.$('quadros-tabelas');
  painel2.querySelectorAll('td.tabela-celula')[0].dispatchEvent(new Evento('focus'));
  const lateral = painel2.querySelector('#tabela-fonte');
  await clicar(m, por(lateral, 'button', 'Corrigir esta célula'));
  assert.equal(autor(lateral).value, 'Ana Lima', 'o nome lembrado');
  digitar(autor(lateral), '');
  digitar(lateral.querySelector('.form-celula input[type=text]'), '1.300,00'); digitar(lateral.querySelector('textarea'), 'Conferido na planilha.');
  const antes = m.gravados.length;
  await clicar(m, por(lateral, 'button', 'Salvar correção'));
  assert.equal(m.gravados.length, antes, 'sem o nome, nada é enviado');
  digitar(autor(lateral), 'Carlos Prado');
  await clicar(m, por(lateral, 'button', 'Salvar correção'));
  assert.equal(m.gravados.at(-1)[0], 'tabelas-corrigir'); assert.equal(m.gravados.at(-1)[1].autor, 'Carlos Prado');
});

test('sugestões: confirmar, descartar e restaurar levam o Autor, e "Confirmado por" mostra esse nome', async () => {
  const m = montar(); await abrirAba(m, 'mapa');
  const painel = m.$('quadros-mapa');
  const abrir = [...painel.querySelectorAll('.sugestao-abrir')].find(b => /Construtora Alfa/.test(texto(b)));
  await clicar(m, abrir);
  const lateral = painel.querySelector('.quadro-lateral');
  assert.ok(autor(lateral), 'o painel da sugestão tem o campo Autor');
  const antes = m.gravados.length;
  await clicar(m, por(lateral, 'button', 'Confirmar'));
  assert.equal(m.gravados.length, antes, 'sem o nome, nada é enviado');
  assert.match(texto(lateral), /Escreva o seu nome\./);
  digitar(autor(lateral), 'Ana Lima');
  await clicar(m, por(lateral, 'button', 'Confirmar'));
  assert.equal(m.gravados.at(-1)[0], 'sugestoes-confirmar'); assert.equal(m.gravados.at(-1)[1].autor, 'Ana Lima');
  // restaurar a descartada: o campo Autor fica em Descartadas, com o nome lembrado
  const descartadas = m.$('quadros-mapa').querySelector('.sugestoes-descartadas');
  assert.equal(autor(descartadas), undefined, 'fechada, a lista não deixa campo escondido na tela');
  descartadas.open = true; descartadas.dispatchEvent(new Evento('toggle'));
  assert.ok(descartadas && autor(descartadas), 'Descartadas tem o campo Autor');
  assert.equal(autor(descartadas).value, 'Ana Lima');
  await clicar(m, por(descartadas, 'button', 'Restaurar'));
  assert.equal(m.gravados.at(-1)[0], 'sugestoes-restaurar'); assert.equal(m.gravados.at(-1)[1].autor, 'Ana Lima');
  // "Confirmado por" mostra o nome guardado na decisão
  assert.match(texto(m.$('quadros-mapa')), /Confirmado por Ana Lima em 27\/11, às 10h05, a partir de sugestão da IA/);
  assert.deepEqual(m.erros, []);
});

test('Corrigir sugestão: o formulário chega com o nome lembrado e salva por sugestoes-corrigir com ele', async () => {
  const m = montar(); await abrirAba(m, 'hipoteses');
  const painel = m.$('quadros-hipoteses');
  const abrir = painel.querySelector('.sugestao-abrir'); await clicar(m, abrir);
  const lateral = painel.querySelector('.quadro-lateral');
  digitar(autor(lateral), 'Ana Lima');
  await clicar(m, por(lateral, 'button', 'Corrigir'));
  assert.equal(autor(lateral).value, 'Ana Lima', 'o formulário de correção já traz o nome');
  assert.ok(lateral.querySelector('.form-quadro'));
  await clicar(m, por(lateral, 'button', 'Salvar'));
  const [operacao, dados] = m.gravados.at(-1);
  assert.equal(operacao, 'sugestoes-corrigir'); assert.equal(dados.autor, 'Ana Lima');
});

test('virar pedido: a diligência e a ligação à lacuna levam o Autor', async () => {
  const m = montar(); await abrirAba(m, 'hipoteses');
  const painel = m.$('quadros-hipoteses');
  const lacuna = painel.querySelector('.quadro-lacuna');
  assert.equal(lacuna.querySelectorAll('input').length, 0, 'antes de aberto, o formulário de virar pedido não tem campo nenhum (nem Autor escondido)');
  await clicar(m, por(lacuna, 'button', 'Virar pergunta ou pedido'));
  const sel = lacuna.querySelector('.lacuna-virar-form select'); sel.value = 'entrevista'; sel.dispatchEvent(new Evento('change', {bubbles: true}));
  const campos = [...lacuna.querySelectorAll('.lacuna-virar-form input[type=text]')];
  digitar(campos[0], 'Comissão'); digitar(campos[1], 'Ana Lima'); digitar(autor(lacuna), 'Carlos Prado');
  await clicar(m, por(lacuna, 'button', 'Virar pedido'));
  assert.deepEqual(m.gravados.map(g => [g[0], g[1].autor]), [['diligencias-criar', 'Carlos Prado'], ['hipoteses-atualizar', 'Carlos Prado']]);
});

test('com conta (fora do modo local) o campo Autor não existe e nenhum autor é enviado', async () => {
  const m = montar({modo: 'conta'}); await abrirAba(m, 'hipoteses');
  const painel = m.$('quadros-hipoteses');
  await clicar(m, por(painel, 'button', '+ Nova hipótese'));
  assert.equal(autor(painel), undefined);
  digitar(painel.querySelector('textarea'), 'A sócia assinou como testemunha.');
  await clicar(m, por(painel, 'button', 'Salvar'));
  assert.equal(m.gravados.length, 1); assert.ok(!('autor' in m.gravados[0][1]), 'o servidor usa a conta');
});
