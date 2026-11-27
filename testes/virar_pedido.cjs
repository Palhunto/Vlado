'use strict';
// "Virar pergunta ou pedido" na lacuna da hipótese (componentes.md, ação de lacuna; interface/formularios.js, quadros.js): a pergunta vai ao campo de Perguntar;
// o pedido de contato (entrevista, pedido de informação, pedido via LAI) cria uma diligência (diligencias-criar) e, na lacuna registrada, fica ligado a ela
// (hipoteses-atualizar com o diligencia_id). Dados sintéticos; o servidor simulado registra cada chamada com o corpo que receberia.
const test = require('node:test');
const assert = require('node:assert/strict');
const {criarMesa, Evento, PILHA} = require('./dom_minimo.cjs');

const HID = 'H' + '1'.repeat(32), GID = 'G' + '9'.repeat(32);
const QUADRO = () => ({caso: 'alpha', total: 1, divergentes: [], aviso: '', hipoteses: [{id: HID, enunciado: 'A dispensa seguiu o rito legal.', situacao: 'em_aberto', condicao: 'pendencia', natureza: null,
  situacao_sem_base: false, sustentam: [], contrariam: [], contexto: [], indisponiveis: [],
  faltam: [{origem: 'registrada', descricao: 'Parecer jurídico da dispensa.', diligencia_id: null, diligencia_estado: null},
    {origem: 'automatica', descricao: 'Nenhuma evidência sustentada nos dois sentidos.', diligencia_id: null, diligencia_estado: null},
    {origem: 'registrada', descricao: 'Ata da comissão.', diligencia_id: 'G' + '8'.repeat(32), diligencia_estado: 'em_andamento'}]}]});
const DETALHE = () => ({id: HID, sha256: 'e'.repeat(64), estado: {enunciado: 'A dispensa seguiu o rito legal.', situacao: 'em_aberto', evidencias: [], lacunas: [{descricao: 'Parecer jurídico da dispensa.', diligencia_id: null},
  {descricao: 'Ata da comissão.', diligencia_id: 'G' + '8'.repeat(32)}]}, evidencias: []});

function montar({permissao = true, modo = 'conta', falhaLigar = false} = {}) {
  const chamadas = [];
  const m = criarMesa({scripts: [...PILHA, 'quadros.js', 'sugestoes.js', 'formularios.js', 'analise.js', 'indicador_salvamento.js'], desktop: true,
    api: (operacao, dados) => {
      if (operacao === 'hipoteses-quadro') return QUADRO();
      if (operacao === 'sugestoes-listar') return {sugestoes: []};
      if (operacao === 'hipoteses-detalhe') return DETALHE();
      if (operacao === 'diligencias-criar') { chamadas.push([operacao, dados]); return {caso: 'alpha', id: GID, diligencia: {estado: 'a_solicitar'}}; }
      if (operacao === 'hipoteses-atualizar') { if (falhaLigar) throw new Error('A hipótese mudou.'); chamadas.push([operacao, dados]); return {id: HID, sha256: 'f'.repeat(64)}; }
      return {};
    },
    preparar: janela => {
      const original = janela.fetch;
      janela.fetch = async (rota, opcoes) => String(rota) === '/api/integracao' ? {ok: true, json: async () => ({quadros_evidencia: true})} : original(rota, opcoes);
    }});
  m.avaliar('window.contextoCaso = () => "alpha";');
  m.avaliar(`document.body.dataset.modo = ${JSON.stringify(modo)};`);
  if (!permissao) m.avaliar('window.Sessao = {pode: op => op !== "diligencias-criar", pronta: Promise.resolve()};');
  return {...m, chamadas};
}
const espera = async m => { await new Promise(r => setTimeout(r, 12)); await m.esperar(10); };
const texto = no => no.textContent.replace(/\s+/g, ' ').trim();
const digitar = (no, valor) => { no.value = valor; no.dispatchEvent(new Evento('input', {bubbles: true})); };
const escolher = (sel, v) => { sel.value = v; sel.dispatchEvent(new Evento('change', {bubbles: true})); };
const clicar = async (m, no) => { no.click(); await espera(m); };
const por = (raiz, seletor, rotulo) => [...raiz.querySelectorAll(seletor)].find(b => texto(b) === rotulo);
async function abrir(m) { m.$('ver-quadros').click(); await espera(m); return m.$('quadros-hipoteses'); }
const preencher = (lacuna, destino, destinatario, responsavel) => {
  escolher(lacuna.querySelector('.lacuna-virar-form select'), destino);
  const campos = [...lacuna.querySelectorAll('.lacuna-virar-form input[type=text]')];
  digitar(campos[0], destinatario); digitar(campos[1], responsavel);
  return campos;
};

test('a lacuna sem diligência ganha "Virar pergunta ou pedido"; a que já tem diligência ligada, não', async () => {
  const m = montar(); const painel = await abrir(m);
  const lacunas = [...painel.querySelectorAll('.quadro-lacuna')];
  assert.equal(lacunas.length, 3);
  assert.deepEqual(lacunas.map(l => !!por(l, 'button', 'Virar pergunta ou pedido')), [true, true, false]);
});

test('entrevista: pede destinatário e responsável antes de enviar, cria a diligência com o texto da lacuna e a liga à lacuna registrada', async () => {
  const m = montar(); const painel = await abrir(m);
  const lacuna = painel.querySelectorAll('.quadro-lacuna')[0];
  await clicar(m, por(lacuna, 'button', 'Virar pergunta ou pedido'));
  escolher(lacuna.querySelector('.lacuna-virar-form select'), 'entrevista');
  await clicar(m, por(lacuna, 'button', 'Virar pedido'));
  assert.equal(m.chamadas.length, 0, 'faltam destinatário e responsável');
  assert.match(texto(lacuna.querySelector('.lacuna-virar-form')), /Escreva o destinatário\./);
  assert.match(texto(lacuna.querySelector('.lacuna-virar-form')), /Escreva quem fica responsável\./);
  preencher(lacuna, 'entrevista', 'Comissão de licitação', 'Ana Lima');
  digitar(lacuna.querySelector('.lacuna-virar-form input[type=date]'), '2026-12-15');
  await clicar(m, por(lacuna, 'button', 'Virar pedido'));
  assert.equal(m.chamadas.length, 2, JSON.stringify(m.chamadas) + texto(lacuna));
  const [[op1, criar], [op2, ligar]] = m.chamadas;
  assert.equal(op1, 'diligencias-criar');
  assert.deepEqual({...criar, requisicao_id: 'x'}, {caso: 'alpha', requisicao_id: 'x', origem: null, acao: 'Parecer jurídico da dispensa.', responsavel: 'Ana Lima', prazo: '2026-12-15', tipo: 'entrevista', destinatario: 'Comissão de licitação'});
  assert.match(criar.requisicao_id, /^[0-9a-f]{32}$/);
  assert.equal(op2, 'hipoteses-atualizar');
  assert.deepEqual({...ligar, requisicao_id: 'x'}, {caso: 'alpha', id: HID, anterior_sha256: 'e'.repeat(64), requisicao_id: 'x',
    lacunas: [{descricao: 'Parecer jurídico da dispensa.', diligencia_id: GID}, {descricao: 'Ata da comissão.', diligencia_id: 'G' + '8'.repeat(32)}]});
  assert.match(texto(m.$('quadros-anuncio')), /Pedido criado\. Ele aparece em Pedidos e prazos\./);
  assert.deepEqual(m.erros, []);
});

test('lacuna automática: cria a diligência e não mexe na hipótese (não há onde guardar o vínculo)', async () => {
  const m = montar(); const painel = await abrir(m);
  const lacuna = painel.querySelectorAll('.quadro-lacuna')[1];
  await clicar(m, por(lacuna, 'button', 'Virar pergunta ou pedido'));
  preencher(lacuna, 'pedido_lai', 'Prefeitura (e-SIC)', 'Ana Lima');
  await clicar(m, por(lacuna, 'button', 'Virar pedido'));
  assert.deepEqual(m.chamadas.map(c => c[0]), ['diligencias-criar']);
  assert.equal(m.chamadas[0][1].tipo, 'pedido_lai'); assert.equal(m.chamadas[0][1].prazo, null);
});

test('se a diligência foi criada mas a ligação à lacuna falhou, a tela diz as duas coisas', async () => {
  const m = montar({falhaLigar: true}); const painel = await abrir(m);
  const lacuna = painel.querySelectorAll('.quadro-lacuna')[0];
  await clicar(m, por(lacuna, 'button', 'Virar pergunta ou pedido'));
  preencher(lacuna, 'pedido_informacao', 'Secretaria', 'Ana Lima');
  await clicar(m, por(lacuna, 'button', 'Virar pedido'));
  assert.match(texto(lacuna.querySelector('.lacuna-virar-erro')), /O pedido foi criado, mas não ficou ligado a esta lacuna: A hipótese mudou\./);
});

test('pergunta à IA: o texto da lacuna vai ao campo de Perguntar, sem criar nada, e o que já estava lá fica', async () => {
  const m = montar(); const painel = await abrir(m);
  const pergunta = m.$('codex-pergunta'); assert.ok(pergunta, 'campo de Perguntar');
  digitar(pergunta, 'Quem assinou o contrato?');
  const lacuna = painel.querySelectorAll('.quadro-lacuna')[0];
  await clicar(m, por(lacuna, 'button', 'Virar pergunta ou pedido'));
  assert.equal(lacuna.querySelector('.lacuna-virar-form select').value, 'ia', 'a pergunta à IA é o padrão');
  await clicar(m, por(lacuna, 'button', 'Abrir em Perguntar'));
  await new Promise(r => setTimeout(r, 450));
  assert.equal(pergunta.value, 'Quem assinou o contrato?\n\nParecer jurídico da dispensa.');
  assert.equal(m.chamadas.length, 0);
});

test('sem a capacidade de criar diligência, só a pergunta à IA; no modo local, pede o nome de quem cria', async () => {
  const m = montar({permissao: false}); const painel = await abrir(m);
  const lacuna = painel.querySelectorAll('.quadro-lacuna')[0];
  await clicar(m, por(lacuna, 'button', 'Virar pergunta ou pedido'));
  assert.deepEqual([...lacuna.querySelectorAll('.lacuna-virar-form option')].map(o => o.value), ['ia']);
  const local = montar({modo: 'local'}); const painel2 = await abrir(local);
  const lac = painel2.querySelectorAll('.quadro-lacuna')[0];
  await clicar(local, por(lac, 'button', 'Virar pergunta ou pedido'));
  const campos = preencher(lac, 'entrevista', 'Comissão', 'Ana Lima');
  await clicar(local, por(lac, 'button', 'Virar pedido'));
  assert.equal(local.chamadas.length, 0); assert.match(texto(lac.querySelector('.lacuna-virar-form')), /Escreva o seu nome\./);
  digitar(campos[2], 'Ana Lima'); await clicar(local, por(lac, 'button', 'Virar pedido'));
  assert.equal(local.chamadas[0][1].autor, 'Ana Lima');
});
