'use strict';
// "Tentar novamente": a failed or interrupted question resumes in the same round from the
// first stage not yet accepted. The button follows the server's retomavel flag and progress.
const test = require('node:test');
const assert = require('node:assert/strict');
const {criarMesa} = require('./dom_minimo.cjs');

const ALFA = {id: 'alfa', titulo: 'Pauta Alfa', rodadas: [{id: 'R002', geracoes: []}]};
const ETAPAS = ['inventario', 'plano', 'busca', 'geracao_inicial', 'revisao', 'sintese'];
const INTERROMPIDA = {codigo: 'interrompido', mensagem: 'Interrompida antes de terminar. O que já foi concluído foi preservado.',
  causa: 'reinicio', em_utc: '2026-11-12T10:00:00+00:00'};

function conversa(over = {}) {
  return {id: 'chat1', caso: 'alfa', titulo: 'Merenda', estado: 'interrompido', situacao: INTERROMPIDA, retomavel: true,
    pergunta_atual: 'Quanto custou a merenda escolar?', rodada: 'R002', rodadas: ['R002'],
    progresso: {etapas: ETAPAS, aceitas: ['inventario', 'plano'], proxima: 'busca', rodada: 'R002'}, ...over};
}
function deferido() {
  let resolve, reject;
  const promessa = new Promise((ok, erro) => { resolve = ok; reject = erro; });
  return {promessa, resolve, reject};
}

// codex-eventos answers from a queue; an empty queue holds the request (a long poll).
async function abrir({estado = conversa(), papel = 'admin', modo = 'local', idioma = 'pt', retomar} = {}) {
  const fila = [{conversa: estado, eventos: [], cursor: 0, acervos: {}}];
  const espera = [];
  const mesa = criarMesa({papel, modo, idioma, armazenamento: idioma === 'en' ? {'vlado-idioma': 'en'} : {}, catalogo: [ALFA],
    url: 'http://127.0.0.1:8765/?area=codex&caso=alfa', api: (operacao, dados) => {
      if (operacao === 'codex-listar') return {conversas: [{id: 'chat1', titulo: 'Merenda', estado: estado.estado, situacao: estado.situacao,
        retomavel: estado.retomavel, pergunta: estado.pergunta_atual, rodada: 'R002', rodadas: ['R002']}]};
      if (operacao === 'codex-status') return {autenticado: true, provedor: 'anthropic', modelo: 'modelo-x'};
      if (operacao === 'inventario') return {caso_id: 'alfa', corpus_id: 'c1', documentos: [], total_documentos: 0};
      if (operacao === 'codex-eventos') {
        if (fila.length) return fila.shift();
        const pedido = deferido(); espera.push(pedido); return pedido.promessa;
      }
      if (operacao === 'codex-retomar') return retomar ? retomar(dados) : {conversa: 'chat1', estado: 'preparando', rodada: 'R002', retomada_da_etapa: 'busca'};
      return {};
    }});
  await mesa.esperar(12);
  mesa.$('codex-conversa').value = 'chat1';
  mesa.$('codex-conversa').dispatchEvent(new mesa.janela.Event('change'));
  await mesa.esperar(12);
  const entregar = async resposta => { if (espera.length) espera.shift().resolve(resposta); else fila.push(resposta); await mesa.esperar(12); };
  return {mesa, entregar};
}
const botao = mesa => mesa.$('codex-retomar');
const etapas = mesa => mesa.$('codex-execucao-etapas').querySelectorAll('li').map(li => [li.dataset.estado, li.querySelector('.run-step-name').textContent]);

test('conversa interrompida mostra selo, mensagem, causa, etapas e o botão com a próxima etapa', async () => {
  const {mesa} = await abrir();
  assert.deepEqual(mesa.erros, []);
  assert.equal(mesa.$('codex-execucao').hidden, false);
  assert.equal(mesa.$('codex-execucao-selo').textContent, 'Interrompida');
  assert.equal(mesa.$('codex-execucao-pergunta').textContent, 'Quanto custou a merenda escolar?');
  assert.equal(mesa.$('codex-execucao-pergunta').getAttribute('translate'), 'no');
  assert.equal(mesa.$('codex-execucao-mensagem').textContent, INTERROMPIDA.mensagem);
  assert.equal(mesa.$('codex-execucao-causa').textContent, 'Causa: o servidor foi reiniciado.');
  assert.deepEqual(etapas(mesa), [['aceita', 'Inventário do acervo'], ['aceita', 'Plano da apuração'], ['proxima', 'Busca e leitura das fontes'],
    ['pendente', 'Geração inicial dos achados'], ['pendente', 'Revisão do suporte'], ['pendente', 'Síntese']]);
  assert.equal(botao(mesa).hidden, false);
  assert.equal(botao(mesa).disabled, false);
  assert.equal(botao(mesa).textContent, 'Tentar novamente a partir de «Busca e leitura das fontes»');
  assert.equal(mesa.$('codex-conversa').selectedOptions[0].textContent, 'Merenda · Interrompida');
});

test('sem etapa pendente o botão conclui a publicação', async () => {
  const {mesa} = await abrir({estado: conversa({progresso: {etapas: ETAPAS, aceitas: ETAPAS, proxima: null, rodada: 'R002'}})});
  assert.equal(botao(mesa).textContent, 'Concluir publicação');
  assert.ok(etapas(mesa).every(([estado]) => estado === 'aceita'));
});

test('sem o botão quando o servidor diz que não é retomável', async () => {
  const {mesa} = await abrir({estado: conversa({estado: 'erro', retomavel: false,
    situacao: {codigo: 'erro', mensagem: 'A conversa excedeu a janela de contexto do modelo. Abra uma nova conversa.', causa: 'contexto'}})});
  assert.equal(mesa.$('codex-execucao-selo').textContent, 'Falhou');
  assert.equal(botao(mesa).hidden, true);
  assert.equal(mesa.$('codex-execucao-causa').textContent, 'Abra uma nova conversa para continuar.');
});

test('sem o botão enquanto a execução corre, com a lista de etapas visível', async () => {
  const {mesa} = await abrir({estado: conversa({estado: 'executando', retomavel: true,
    situacao: {codigo: 'em_andamento', mensagem: 'Em execução.', causa: null}})});
  assert.equal(mesa.$('codex-execucao').hidden, false);
  assert.equal(mesa.$('codex-execucao-selo').textContent, 'Em execução');
  assert.equal(botao(mesa).hidden, true);
  assert.equal(etapas(mesa).length, 6);
});

test('conversa concluída não mostra o bloco de execução', async () => {
  const {mesa} = await abrir({estado: conversa({estado: 'concluido', retomavel: false,
    situacao: {codigo: 'concluido', mensagem: 'Concluída e publicada.', causa: null}})});
  assert.equal(mesa.$('codex-execucao').hidden, true);
});

test('conversa antiga sem situação deriva o selo do estado', async () => {
  const {mesa} = await abrir({estado: conversa({estado: 'erro', situacao: null, retomavel: false, progresso: undefined, pergunta_atual: null})});
  assert.equal(mesa.$('codex-execucao-selo').textContent, 'Falhou');
  assert.equal(mesa.$('codex-execucao-etapas').hidden, true);
  assert.equal(botao(mesa).hidden, true);
});

test('clique envia só a conversa, mostra “Retomando…” e segue o acompanhamento com o aviso da retomada', async () => {
  const pedido = deferido();
  const {mesa, entregar} = await abrir({retomar: () => pedido.promessa});
  const consultas = () => mesa.chamadas.filter(c => c.operacao === 'codex-eventos').length;
  const antes = consultas();
  botao(mesa).click();
  await mesa.esperar(4);
  assert.deepEqual(mesa.chamadas.find(c => c.operacao === 'codex-retomar').dados, {conversa: 'chat1'});
  assert.equal(botao(mesa).textContent, 'Retomando…');
  assert.equal(botao(mesa).disabled, true);
  assert.equal(botao(mesa).hidden, false);
  pedido.resolve({conversa: 'chat1', estado: 'preparando', rodada: 'R002', retomada_da_etapa: 'busca'});
  await mesa.esperar(12);
  assert.equal(botao(mesa).hidden, true, 'nada de novo botão com a execução ativa');
  assert.ok(consultas() > antes, 'voltou a acompanhar os eventos');
  await entregar({conversa: conversa({estado: 'executando', retomavel: false, situacao: {codigo: 'em_andamento', mensagem: 'Em execução.', causa: null}}),
    eventos: [{tipo: 'retomada', dados: {etapa: 'busca', rodada: 'R002', numero: 3, total: 6, etapas_aceitas: ['inventario', 'plano'],
      situacao_anterior: 'interrompido', tentativa_retomada: 1}}], cursor: 1, acervos: {}});
  assert.equal(mesa.$('codex-execucao-aviso').textContent, 'Retomada da etapa 3 de 6: Busca e leitura das fontes.');
  assert.equal(mesa.$('codex-execucao-aviso').hidden, false);
  assert.equal(mesa.chamadas.some(c => c.operacao === 'codex-perguntar'), false, 'nenhuma pergunta nova');
});

test('recusa mostra o alerta com a mensagem e mantém o botão', async () => {
  const recusa = 'Esta conversa não tem uma execução interrompida para retomar.';
  const {mesa} = await abrir({retomar: () => { throw new Error(recusa); }});
  botao(mesa).click();
  await mesa.esperar(8);
  assert.equal(mesa.$('codex-erro').hidden, false);
  assert.equal(mesa.$('codex-erro').textContent, recusa);
  assert.equal(botao(mesa).hidden, false);
  assert.equal(botao(mesa).disabled, false);
  assert.equal(botao(mesa).textContent, 'Tentar novamente a partir de «Busca e leitura das fontes»');
});

test('convidado envia só a conversa e é lembrado de que a nova tentativa usa a cota', async () => {
  const {mesa} = await abrir({papel: 'convidado', modo: 'piloto'});
  assert.equal(mesa.$('codex-retomar-cota').hidden, false);
  botao(mesa).click();
  await mesa.esperar(8);
  assert.deepEqual(mesa.chamadas.find(c => c.operacao === 'codex-retomar').dados, {conversa: 'chat1'});
  const admin = await abrir();
  assert.equal(admin.mesa.$('codex-retomar-cota').hidden, true);
});

test('limite diário avisa que a nova tentativa pode ser recusada', async () => {
  const {mesa} = await abrir({estado: conversa({estado: 'erro', situacao: {codigo: 'sem_cota',
    mensagem: 'Limite diário de tokens da instalação atingido (1000). Novas perguntas voltam amanhã (UTC).', causa: 'limite_dia'}})});
  assert.equal(mesa.$('codex-execucao-selo').textContent, 'Limite de uso atingido');
  assert.equal(mesa.$('codex-execucao-causa').textContent,
    'A nova tentativa pode ser recusada até o limite ser ajustado ou até o dia seguinte (UTC).');
  assert.equal(botao(mesa).hidden, false);
});

test('em inglês o bloco de execução e o botão saem traduzidos', async () => {
  const {mesa} = await abrir({idioma: 'en'});
  mesa.janela.I18N.aplicar(mesa.doc.body);
  assert.equal(mesa.$('codex-execucao-selo').textContent, 'Interrupted');
  assert.equal(mesa.$('codex-execucao-mensagem').textContent, 'Interrupted before finishing. Work already completed was kept.');
  assert.equal(mesa.$('codex-execucao-causa').textContent, 'Cause: the server was restarted.');
  assert.equal(botao(mesa).textContent, 'Try again from “Searching and reading the sources”');
  assert.deepEqual(etapas(mesa).map(([, nome]) => nome), ['Archive inventory', 'Investigation plan', 'Searching and reading the sources',
    'Initial findings', 'Support review', 'Synthesis']);
  mesa.janela.I18N.definir('pt');
  assert.equal(botao(mesa).textContent, 'Tentar novamente a partir de «Busca e leitura das fontes»');
  assert.equal(mesa.$('codex-execucao-selo').textContent, 'Interrompida');
});
