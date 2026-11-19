'use strict';
// Automatic drafts (continuidade.js): the question in preparation and the panel forms go to
// localStorage at once and to the server (rascunhos-*) after a short pause, on visibilitychange
// and on pagehide. Opening a screen with a newer draft offers to restore or discard it; without a
// connection the status says the draft stayed in this browser. Keys are never kept.
const test = require('node:test');
const assert = require('node:assert/strict');
const {criarMesa, Evento} = require('./dom_minimo.cjs');

const ALFA = {id: 'alfa', titulo: 'Pauta Alfa', rodadas: [{id: 'R002', geracoes: []}]};
const PREFIXO = 'vlado:rascunho-tela:local:alfa:';

function memoria(inicial = {}) {
  const dados = new Map(Object.entries(inicial));
  return {dados, getItem: k => dados.get(k) ?? null, setItem: (k, v) => dados.set(k, String(v)), removeItem: k => dados.delete(k),
    key: i => [...dados.keys()][i] ?? null, get length() { return dados.size; }};
}

// In-memory server with the same version rule as scripts/rascunhos.py.
function servidorRascunhos(inicial = {}) {
  const telas = new Map(Object.entries(inicial));
  const publico = (tela, d) => d ? {caso: 'alfa', tela, versao: d.versao, conteudo: d.conteudo, descartado: !!d.descartado,
    atualizado_em_utc: d.em, bytes: 1} : {caso: 'alfa', tela, versao: 0, conteudo: null, descartado: false, atualizado_em_utc: null, bytes: 0};
  const conflito = (tela, d) => { const erro = new Error('Conflito'); erro.result = {estado: 'erro', codigo: 'rascunho_conflito', erro: 'O rascunho mudou.', atual: publico(tela, d)}; throw erro; };
  return {telas, responder(op, dados) {
    const atual = telas.get(dados.tela), gravada = atual ? atual.versao : 0;
    if (op === 'rascunhos-ler') return publico(dados.tela, atual);
    if (op === 'rascunhos-salvar') {
      if (dados.versao !== gravada) return conflito(dados.tela, atual);
      const novo = {versao: gravada + 1, conteudo: dados.conteudo, descartado: false, em: '2026-11-19T14:05:00Z'};
      telas.set(dados.tela, novo); return publico(dados.tela, novo);
    }
    if (op === 'rascunhos-descartar') {
      if (dados.versao !== gravada) return conflito(dados.tela, atual);
      const novo = {versao: gravada + 1, conteudo: null, descartado: true, em: '2026-11-19T14:06:00Z'};
      telas.set(dados.tela, novo); return publico(dados.tela, novo);
    }
    return null;
  }};
}

async function abrir({rascunhos = servidorRascunhos(), local = memoria(), semRede = () => false} = {}) {
  const relogio = [], envios = [];
  const mesa = criarMesa({catalogo: [ALFA], url: 'http://127.0.0.1:8765/?area=codex&caso=alfa',
    api: (op, dados) => {
      const resposta = op.startsWith('rascunhos-') ? rascunhos.responder(op, dados) : null;
      if (resposta) return resposta;
      if (op === 'codex-listar') return {conversas: []};
      if (op === 'codex-status') return {autenticado: true, provedor: 'anthropic', modelo: 'modelo-x'};
      if (op === 'inventario') return {caso_id: 'alfa', corpus_id: 'c1', documentos: [], total_documentos: 0};
      if (op === 'codex-perguntar') return {conversa: 'c'.repeat(32), estado: 'preparando'};
      if (op === 'codex-eventos') return new Promise(() => {});
      return {};
    },
    preparar: janela => {
      janela.localStorage = local;
      // Only the draft pause (>= 1 s) is held; the test runs it with avancar().
      janela.setTimeout = (funcao, ms, ...args) => {
        if ((ms || 0) < 1000) return setTimeout(funcao, ms, ...args);
        const item = {funcao, args, ms}; relogio.push(item); return item;
      };
      janela.clearTimeout = item => { const i = relogio.indexOf(item); if (i >= 0) relogio.splice(i, 1); else clearTimeout(item); };
      const original = janela.fetch;
      janela.fetch = async (rota, opcoes = {}) => {
        if (String(rota).startsWith('/api/rascunhos-')) {
          envios.push({op: String(rota).slice(5), dados: JSON.parse(opcoes.body), keepalive: !!opcoes.keepalive});
          if (semRede()) throw new TypeError('Failed to fetch');
        }
        return original(rota, opcoes);
      };
    }});
  await mesa.esperar(16);
  const avancar = async () => { for (const item of relogio.splice(0).filter(i => i.ms === 1200)) item.funcao(...item.args); await mesa.esperar(10); };
  const escrever = async texto => {
    mesa.$('codex-pergunta').value = texto;
    mesa.$('codex-pergunta').dispatchEvent(new Evento('input', {bubbles: true}));
    await mesa.esperar(6);
  };
  const estado = () => mesa.doc.querySelector('.rascunho-estado');
  const oferta = () => mesa.doc.querySelector('.rascunho-oferta');
  const botao = rotulo => oferta().querySelectorAll('button').find(b => b.textContent === rotulo);
  const salvamentos = () => envios.filter(e => e.op === 'rascunhos-salvar');
  return {mesa, avancar, escrever, estado, oferta, botao, envios, salvamentos, local, rascunhos, relogio};
}

test('salva no navegador a cada digitação e no servidor depois da pausa curta', async () => {
  const t = await abrir();
  assert.deepEqual(t.mesa.erros, []);
  assert.ok(t.envios.some(e => e.op === 'rascunhos-ler' && e.dados.tela === 'pergunta'), 'lê o rascunho ao abrir a pergunta');
  await t.escrever('Quanto custou a merenda?');
  const copia = JSON.parse(t.local.getItem(PREFIXO + 'pergunta'));
  assert.equal(copia.conteudo.pergunta, 'Quanto custou a merenda?');
  assert.equal(copia.pendente, true);
  assert.equal(t.salvamentos().length, 0, 'ainda dentro da pausa');
  await t.avancar();
  assert.deepEqual(t.salvamentos().map(e => e.dados), [{caso: 'alfa', tela: 'pergunta', versao: 0, conteudo: {pergunta: 'Quanto custou a merenda?'}}]);
  assert.match(t.estado().textContent, /^Salvo às \d{2}:\d{2}$/);
  assert.equal(JSON.parse(t.local.getItem(PREFIXO + 'pergunta')).pendente, false);
  await t.escrever('Quanto custou a merenda em 2024?');
  await t.avancar();
  assert.equal(t.salvamentos()[1].dados.versao, 1, 'a próxima gravação leva a versão recebida');
});

test('pagehide e troca de aba enviam na hora, sem esperar a pausa', async () => {
  const t = await abrir();
  await t.escrever('Primeira versão');
  t.mesa.janela.dispatchEvent(new Evento('pagehide'));
  await t.mesa.esperar(10);
  assert.equal(t.salvamentos().length, 1);
  assert.equal(t.salvamentos()[0].keepalive, true, 'o pedido sobrevive ao fechamento da página');
  assert.equal(t.relogio.filter(i => i.ms === 1200).length, 0, 'a pausa pendente foi cancelada');
  await t.escrever('Segunda versão');
  t.mesa.doc.visibilityState = 'hidden';
  t.mesa.doc.dispatchEvent(new Evento('visibilitychange'));
  await t.mesa.esperar(10);
  assert.equal(t.salvamentos().length, 2);
  assert.deepEqual(t.salvamentos()[1].dados.conteudo, {pergunta: 'Segunda versão'});
});

test('ao reabrir oferece restaurar o rascunho do servidor', async () => {
  const rascunhos = servidorRascunhos({pergunta: {versao: 4, conteudo: {pergunta: 'Pergunta guardada'}, em: '2026-11-19T13:00:00Z'}});
  const t = await abrir({rascunhos});
  assert.equal(t.oferta().hidden, false);
  assert.match(t.oferta().textContent, /Há um rascunho de \d{2}:\d{2} que não foi enviado\. Restaurar\?/);
  assert.equal(t.mesa.$('codex-pergunta').value, '');
  t.botao('Restaurar rascunho').click();
  await t.mesa.esperar(10);
  assert.equal(t.mesa.$('codex-pergunta').value, 'Pergunta guardada');
  assert.equal(t.oferta().hidden, true);
  assert.equal(t.salvamentos().at(-1).dados.versao, 4);
});

test('descartar apaga a cópia do navegador e marca o rascunho do servidor', async () => {
  const rascunhos = servidorRascunhos({pergunta: {versao: 2, conteudo: {pergunta: 'Velha'}, em: '2026-11-19T13:00:00Z'}});
  const local = memoria({[PREFIXO + 'pergunta']: JSON.stringify({conteudo: {pergunta: 'Velha'}, versao: 2, em: '2026-11-19T13:00:00Z', pendente: false})});
  const t = await abrir({rascunhos, local});
  t.botao('Descartar rascunho').click();
  await t.mesa.esperar(10);
  assert.deepEqual(t.envios.filter(e => e.op === 'rascunhos-descartar').map(e => e.dados), [{caso: 'alfa', tela: 'pergunta', versao: 2}]);
  assert.equal(t.local.getItem(PREFIXO + 'pergunta'), null);
  assert.equal(rascunhos.telas.get('pergunta').descartado, true);
  assert.equal(t.mesa.$('codex-pergunta').value, '');
});

test('sem conexão: avisa que ficou neste navegador e oferece a cópia local ao reabrir', async () => {
  let offline = true;
  const local = memoria();
  const t = await abrir({local, semRede: () => offline});
  await t.escrever('Texto escrito sem rede');
  await t.avancar();
  assert.equal(t.estado().textContent, 'Sem conexão — salvo neste navegador');
  assert.equal(JSON.parse(local.getItem(PREFIXO + 'pergunta')).pendente, true);
  // The page closes; a new one opens in the same browser, still offline.
  const outra = await abrir({local, semRede: () => offline});
  assert.equal(outra.oferta().hidden, false);
  assert.equal(outra.estado().textContent, 'Sem conexão — salvo neste navegador');
  outra.botao('Restaurar rascunho').click();
  await outra.mesa.esperar(10);
  assert.equal(outra.mesa.$('codex-pergunta').value, 'Texto escrito sem rede');
  offline = false;
  outra.mesa.janela.dispatchEvent(new Evento('online'));
  await outra.mesa.esperar(10);
  assert.match(outra.estado().textContent, /^Salvo às/);
});

test('conflito com outra aba: nada é sobrescrito e quem escreve escolhe', async () => {
  const rascunhos = servidorRascunhos();
  const t = await abrir({rascunhos});
  // Another tab saves first.
  rascunhos.telas.set('pergunta', {versao: 1, conteudo: {pergunta: 'Da outra aba'}, em: '2026-11-19T14:00:00Z'});
  await t.escrever('Desta aba');
  await t.avancar();
  assert.equal(rascunhos.telas.get('pergunta').conteudo.pergunta, 'Da outra aba', 'a gravação atrasada não sobrescreve');
  assert.match(t.oferta().textContent, /mudou em outra aba ou janela/);
  await t.escrever('Desta aba, mais');
  assert.equal(t.relogio.filter(i => i.ms === 1200).length, 0, 'nada é gravado enquanto a escolha está aberta');
  t.botao('Manter o desta aba').click();
  await t.mesa.esperar(10);
  assert.equal(rascunhos.telas.get('pergunta').conteudo.pergunta, 'Desta aba, mais');
  assert.equal(rascunhos.telas.get('pergunta').versao, 2);
});

test('usar a versão da outra aba substitui o campo', async () => {
  const rascunhos = servidorRascunhos();
  const t = await abrir({rascunhos});
  rascunhos.telas.set('pergunta', {versao: 1, conteudo: {pergunta: 'Da outra aba'}, em: '2026-11-19T14:00:00Z'});
  await t.escrever('Desta aba');
  await t.avancar();
  t.botao('Usar o da outra aba').click();
  await t.mesa.esperar(10);
  assert.equal(t.mesa.$('codex-pergunta').value, 'Da outra aba');
  assert.equal(JSON.parse(t.local.getItem(PREFIXO + 'pergunta')).conteudo.pergunta, 'Da outra aba');
});

test('texto com forma de chave de API não vai para o navegador nem para o servidor', async () => {
  const t = await abrir();
  await t.escrever('use sk-ant-' + 'a'.repeat(30));
  await t.avancar();
  assert.equal(t.local.getItem(PREFIXO + 'pergunta'), null);
  assert.equal(t.salvamentos().length, 0);
  assert.match(t.estado().textContent, /Rascunho não guardado/);
});

test('enviar a pergunta descarta o rascunho', async () => {
  const t = await abrir();
  await t.escrever('Pergunta final');
  await t.avancar();
  t.mesa.$('codex-form').requestSubmit();
  await t.mesa.esperar(16);
  assert.ok(t.mesa.chamadas.some(c => c.operacao === 'codex-perguntar'));
  assert.deepEqual(t.envios.filter(e => e.op === 'rascunhos-descartar').map(e => e.dados), [{caso: 'alfa', tela: 'pergunta', versao: 1}]);
  assert.equal(t.local.getItem(PREFIXO + 'pergunta'), null);
});

test('formulário de quadro guarda o rascunho e o fechamento o descarta', async () => {
  const t = await abrir();
  const dialogo = t.mesa.$('diligencias-dialogo');
  dialogo.showModal();
  t.mesa.$('diligencias-acao').dispatchEvent(new Evento('focusin', {bubbles: true}));
  await t.mesa.esperar(6);
  t.mesa.$('diligencias-acao').value = 'Pedir contrato à prefeitura';
  t.mesa.$('diligencias-acao').dispatchEvent(new Evento('input', {bubbles: true}));
  await t.mesa.esperar(6);
  await t.avancar();
  const salvo = t.salvamentos().find(e => e.dados.tela === 'quadro-diligencias');
  assert.ok(salvo, 'o quadro tem a própria tela de rascunho');
  assert.equal(salvo.dados.conteudo.diligencias_acao, 'Pedir contrato à prefeitura');
  assert.ok(Object.keys(salvo.dados.conteudo).every(nome => !/chave|key|senha|token|api/i.test(nome)));
  dialogo.close();
  await t.mesa.esperar(10);
  assert.ok(t.envios.some(e => e.op === 'rascunhos-descartar' && e.dados.tela === 'quadro-diligencias'));
  assert.equal(t.local.getItem(PREFIXO + 'quadro-diligencias'), null);
});

test('Sair apaga deste navegador os rascunhos das telas', async () => {
  const local = memoria({[PREFIXO + 'pergunta']: '{}', 'vlado:rascunho-tela:k1:beta:pergunta': '{}', 'vlado-idioma': 'pt'});
  const t = await abrir({local});
  t.mesa.janela.Rascunhos.limparTudo();
  assert.deepEqual([...local.dados.keys()].filter(k => k.startsWith('vlado:rascunho-tela:')), []);
  assert.equal(local.getItem('vlado-idioma'), 'pt', 'preferências que não são rascunho ficam');
  await t.escrever('Depois de sair');
  assert.equal(local.getItem(PREFIXO + 'pergunta'), null, 'depois de sair nada é gravado');
});
