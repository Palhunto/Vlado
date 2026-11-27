'use strict';
// "Virar pergunta ou pedido" na lacuna da hipótese (componentes.md, ação de lacuna; interface/formularios.js, quadros.js): a pergunta vai ao campo de Perguntar;
// o pedido de contato (entrevista, pedido de informação, pedido via LAI) cria uma diligência (diligencias-criar) e, na lacuna registrada, fica ligado a ela
// (hipoteses-atualizar com o diligencia_id). Dados sintéticos; o servidor simulado registra cada chamada com o corpo que receberia.
const test = require('node:test');
const assert = require('node:assert/strict');
const {criarMesa, Evento, PILHA} = require('./dom_minimo.cjs');

const HID = 'H' + '1'.repeat(32), GID = 'G' + '9'.repeat(32);
const H2 = 'H' + '2'.repeat(32);
const QUADRO = (duas = false) => ({caso: 'alpha', total: 1, divergentes: [], aviso: '', hipoteses: [...(duas ? [{id: H2, enunciado: 'A segunda hipótese.', situacao: 'em_aberto', condicao: 'pendencia', natureza: null, situacao_sem_base: false, sustentam: [], contrariam: [], contexto: [], indisponiveis: [],
  faltam: [{origem: 'automatica', descricao: 'Nenhuma evidência sustentada nos dois sentidos.', diligencia_id: null, diligencia_estado: null}]}] : []), {id: HID, enunciado: 'A dispensa seguiu o rito legal.', situacao: 'em_aberto', condicao: 'pendencia', natureza: null,
  situacao_sem_base: false, sustentam: [], contrariam: [], contexto: [], indisponiveis: [],
  faltam: [{origem: 'registrada', descricao: 'Parecer jurídico da dispensa.', diligencia_id: null, diligencia_estado: null},
    {origem: 'automatica', descricao: 'Nenhuma evidência sustentada nos dois sentidos.', diligencia_id: null, diligencia_estado: null},
    {origem: 'registrada', descricao: 'Ata da comissão.', diligencia_id: 'G' + '8'.repeat(32), diligencia_estado: 'em_andamento'}]}]});
const DETALHE = () => ({id: HID, sha256: 'e'.repeat(64), estado: {enunciado: 'A dispensa seguiu o rito legal.', situacao: 'em_aberto', evidencias: [], lacunas: [{descricao: 'Parecer jurídico da dispensa.', diligencia_id: null},
  {descricao: 'Ata da comissão.', diligencia_id: 'G' + '8'.repeat(32)}]}, evidencias: []});

function montar({permissao = true, modo = 'conta', falhaLigar = false, detalhe = DETALHE, falhasCriar = 0, falhasLigar = 0, duas = false} = {}) {
  let criar = 0, ligar = 0;
  const chamadas = [];
  const m = criarMesa({scripts: [...PILHA, 'quadros.js', 'sugestoes.js', 'formularios.js', 'analise.js', 'indicador_salvamento.js'], desktop: true,
    api: (operacao, dados) => {
      if (operacao === 'hipoteses-quadro') return QUADRO(duas);
      if (operacao === 'sugestoes-listar') return {sugestoes: []};
      if (operacao === 'hipoteses-detalhe') { chamadas.push([operacao, dados]); return detalhe(); }
      if (operacao === 'diligencias-criar') { chamadas.push([operacao, dados]); if (++criar <= falhasCriar) throw new Error('Sem resposta do servidor.'); return {caso: 'alpha', id: GID, diligencia: {estado: 'a_solicitar'}}; }
      if (operacao === 'hipoteses-atualizar') { chamadas.push([operacao, dados]); if (falhaLigar || ++ligar <= falhasLigar) throw new Error('A hipótese mudou.'); return {id: HID, sha256: 'f'.repeat(64)}; }
      return {};
    },
    preparar: janela => {
      const original = janela.fetch;
      janela.fetch = async (rota, opcoes) => String(rota) === '/api/integracao' ? {ok: true, json: async () => ({quadros_evidencia: true})} : original(rota, opcoes);
    }});
  m.avaliar('window.contextoCaso = () => "alpha";');
  m.avaliar(`document.body.dataset.modo = ${JSON.stringify(modo)};`);
  if (!permissao) m.avaliar('window.Sessao = {pode: op => op !== "diligencias-criar", pronta: Promise.resolve()};');
  return {...m, chamadas, gravadas: () => chamadas.filter(c => c[0] === 'diligencias-criar' || c[0] === 'hipoteses-atualizar')};
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
  assert.equal(m.gravadas().length, 0, 'faltam destinatário e responsável');
  assert.match(texto(lacuna.querySelector('.lacuna-virar-form')), /Escreva o destinatário\./);
  assert.match(texto(lacuna.querySelector('.lacuna-virar-form')), /Escreva quem fica responsável\./);
  preencher(lacuna, 'entrevista', 'Comissão de licitação', 'Ana Lima');
  digitar(lacuna.querySelector('.lacuna-virar-form input[type=date]'), '2026-12-15');
  await clicar(m, por(lacuna, 'button', 'Virar pedido'));
  assert.equal(m.gravadas().length, 2, JSON.stringify(m.chamadas) + texto(lacuna));
  const [[op1, criar], [op2, ligar]] = m.gravadas();
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
  assert.deepEqual(m.gravadas().map(c => c[0]), ['diligencias-criar']);
  assert.equal(m.gravadas()[0][1].tipo, 'pedido_lai'); assert.equal(m.gravadas()[0][1].prazo, null);
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
  assert.equal(m.gravadas().length, 0);
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
  assert.equal(local.gravadas().length, 0); assert.match(texto(lac.querySelector('.lacuna-virar-form')), /Escreva o seu nome\./);
  digitar(campos[2], 'Ana Lima'); await clicar(local, por(lac, 'button', 'Virar pedido'));
  assert.equal(local.gravadas()[0][1].autor, 'Ana Lima');
});

const lacunaDe = painel => painel.querySelectorAll('.quadro-lacuna')[0];
async function preencherEEnviar(m, lacuna, destino = 'entrevista') {
  if (!lacuna.querySelector('.lacuna-virar-form')) await clicar(m, por(lacuna, 'button', 'Virar pergunta ou pedido'));
  preencher(lacuna, destino, 'Comissão de licitação', 'Ana Lima');
  await clicar(m, por(lacuna, 'button', 'Virar pedido'));
}
const SEM_PEDIDO = /nenhum pedido foi criado/;

test('B1: lacuna que mudou, já foi ligada ou foi apagada desde que o quadro abriu: nenhum pedido é criado e a tela avisa', async () => {
  const situacoes = {
    mudou: () => ({...DETALHE(), estado: {...DETALHE().estado, lacunas: [{descricao: 'Parecer jurídico revisado.', diligencia_id: null}]}}),
    'já ligada': () => ({...DETALHE(), estado: {...DETALHE().estado, lacunas: [{descricao: 'Parecer jurídico da dispensa.', diligencia_id: 'G' + '7'.repeat(32)}]}}),
    apagada: () => ({...DETALHE(), estado: {...DETALHE().estado, lacunas: []}}),
  };
  for (const [nome, detalhe] of Object.entries(situacoes)) {
    const m = montar({detalhe}); const painel = await abrir(m); const lacuna = lacunaDe(painel);
    await preencherEEnviar(m, lacuna);
    assert.deepEqual(m.gravadas(), [], `${nome}: nada é criado`);
    assert.match(texto(lacuna.querySelector('.lacuna-virar-erro')), SEM_PEDIDO, nome);
    assert.equal(lacuna.querySelector('.lacuna-virar-erro').hidden, false);
    assert.doesNotMatch(texto(m.$('quadros-anuncio') || {textContent: ''}), /Pedido criado/, `${nome}: não anuncia sucesso`);
  }
});

test('N1: depois de "não ficou ligado", o segundo clique só tenta ligar de novo; não cria outra diligência', async () => {
  const m = montar({falhasLigar: 1}); const painel = await abrir(m); const lacuna = lacunaDe(painel);
  await preencherEEnviar(m, lacuna);
  assert.match(texto(lacuna.querySelector('.lacuna-virar-erro')), /O pedido foi criado, mas não ficou ligado a esta lacuna/);
  assert.ok(por(lacuna, 'button', 'Ligar à lacuna'), 'o botão do formulário agora é Ligar à lacuna');
  await clicar(m, por(lacuna, 'button', 'Ligar à lacuna'));
  assert.deepEqual(m.gravadas().map(c => c[0]), ['diligencias-criar', 'hipoteses-atualizar', 'hipoteses-atualizar'], 'uma diligência, duas tentativas de ligar');
  const ligacoes = m.gravadas().filter(c => c[0] === 'hipoteses-atualizar');
  assert.equal(ligacoes[0][1].requisicao_id, ligacoes[1][1].requisicao_id, 'a mesma tentativa de ligar');
  assert.equal(ligacoes[1][1].lacunas[0].diligencia_id, GID);
  assert.ok(por(lacuna, 'button', 'Ver pedido'), 'ligado: o botão vira Ver pedido');
  assert.match(texto(m.$('quadros-anuncio')), /Pedido criado\./);
});

test('N2: depois de criado, o botão vira "Ver pedido" e leva a Pedidos e prazos; um segundo clique não cria outro', async () => {
  const m = montar(); const painel = await abrir(m); const lacuna = lacunaDe(painel);
  m.avaliar('window.__ida = []; window.areaMesa = Object.freeze({ir: nome => window.__ida.push(nome), nucleo() {}});');
  await preencherEEnviar(m, lacuna);
  assert.equal(m.gravadas().length, 2);
  assert.equal(por(lacuna, 'button', 'Virar pergunta ou pedido'), undefined);
  await clicar(m, por(lacuna, 'button', 'Ver pedido'));
  await clicar(m, por(lacuna, 'button', 'Ver pedido'));
  assert.equal(m.gravadas().length, 2, 'nenhum pedido novo');
  assert.ok(m.janela.__ida.length >= 2 && m.janela.__ida.every(n => n === 'diligencias'), 'leva a Pedidos e prazos');
});

test('N2: lacuna automática: o pedido criado vira "Ver pedido" e continua assim depois de o quadro recarregar', async () => {
  const m = montar(); const painel = await abrir(m);
  const automatica = painel.querySelectorAll('.quadro-lacuna')[1];
  await preencherEEnviar(m, automatica, 'pedido_lai');
  assert.deepEqual(m.gravadas().map(c => c[0]), ['diligencias-criar']);
  assert.ok(por(automatica, 'button', 'Ver pedido'));
  m.avaliar("window.Quadros.selecionar('hipoteses', true)"); await espera(m);
  const depois = m.$('quadros-hipoteses').querySelectorAll('.quadro-lacuna')[1];
  assert.ok(por(depois, 'button', 'Ver pedido'), 'recarregado, a lacuna automática não oferece criar de novo');
  assert.equal(por(depois, 'button', 'Virar pergunta ou pedido'), undefined);
});

test('o mesmo conteúdo reenviado após uma falha leva o mesmo requisicao_id; outro conteúdo, outro', async () => {
  const m = montar({falhasCriar: 1}); const painel = await abrir(m); const lacuna = lacunaDe(painel);
  const contar = "let __n = 0; Object.defineProperty(globalThis, 'crypto', {value: {randomUUID: () => 'a1b2c3d4-' + String(++__n).padStart(4, '0') + '-4000-8000-000000000000'}, configurable: true});";
  m.avaliar(contar);
  await preencherEEnviar(m, lacuna);
  assert.match(texto(lacuna.querySelector('.lacuna-virar-erro')), /Não deu para criar o pedido: Sem resposta do servidor\./);
  await clicar(m, por(lacuna, 'button', 'Virar pedido'));       // o mesmo conteúdo
  const criar = m.gravadas().filter(c => c[0] === 'diligencias-criar');
  assert.equal(criar.length, 2); assert.equal(criar[0][1].requisicao_id, criar[1][1].requisicao_id, 'o mesmo conteúdo é a mesma tentativa');
  const m2 = montar({falhasCriar: 1}); const lac2 = lacunaDe(await abrir(m2));
  m2.avaliar(contar);
  await preencherEEnviar(m2, lac2);
  const campos = [...lac2.querySelectorAll('.lacuna-virar-form input[type=text]')]; digitar(campos[0], 'Outra comissão');
  await clicar(m2, por(lac2, 'button', 'Virar pedido'));
  const c2 = m2.gravadas().filter(c => c[0] === 'diligencias-criar');
  assert.notEqual(c2[0][1].requisicao_id, c2[1][1].requisicao_id, 'outro conteúdo é outra tentativa: ' + JSON.stringify(c2.map(c => [c[1].requisicao_id, c[1].destinatario])));
});

test('R1 da Coruja: a mesma frase automática em duas hipóteses: virar a de uma não deixa a da outra em "Ver pedido", e cada uma cria o seu pedido', async () => {
  const m = montar({duas: true}); const painel = await abrir(m);
  m.avaliar("let __n = 0; Object.defineProperty(globalThis, 'crypto', {value: {randomUUID: () => 'a1b2c3d4-' + String(++__n).padStart(4, '0') + '-4000-8000-000000000000'}, configurable: true});");
  const automaticas = () => [...m.$('quadros-hipoteses').querySelectorAll('.quadro-hipotese')].map(h => [...h.querySelectorAll('.quadro-lacuna')].find(l => /Nenhuma evidência sustentada/.test(texto(l))));
  let [daH2, daH1] = automaticas();          // a ordem do quadro: H2 primeiro, H1 depois
  assert.equal(automaticas().length, 2);
  await preencherEEnviar(m, daH1, 'pedido_lai');
  assert.deepEqual(m.gravadas().map(c => c[0]), ['diligencias-criar']);
  assert.ok(por(daH1, 'button', 'Ver pedido'), 'a lacuna virada está em Ver pedido');
  [daH2, daH1] = automaticas();
  assert.ok(por(daH2, 'button', 'Virar pergunta ou pedido'), 'a mesma frase em outra hipótese continua oferecendo o pedido');
  assert.equal(por(daH2, 'button', 'Ver pedido'), undefined);
  await preencherEEnviar(m, daH2, 'pedido_lai');
  assert.deepEqual(m.gravadas().map(c => c[0]), ['diligencias-criar', 'diligencias-criar'], 'cada hipótese cria o seu pedido');
  const rids = m.gravadas().map(c => c[1].requisicao_id);
  assert.notEqual(rids[0], rids[1], 'tentativas distintas');
  // recarregado, as duas seguem em Ver pedido, cada uma pelo seu
  m.avaliar("window.Quadros.selecionar('hipoteses', true)"); await espera(m);
  assert.deepEqual(automaticas().map(l => !!por(l, 'button', 'Ver pedido')), [true, true]);
});
