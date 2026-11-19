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

// Same shape as continuidade.resumo_caso (scripts/continuidade.py).
const RESUMO = {esquema: 1, caso: 'alfa', titulo: 'Pauta Alfa',
  documentos: {cadastrados: 3, pendentes: [{id: 'D002', nome: 'visual.pdf', motivo: 'paginas_sem_texto'}]},
  rodada: {id: 'R002', total_rodadas: 2, etapas: ['inventario', 'plano', 'busca', 'geracao_inicial', 'revisao', 'sintese'],
    aceitas: ['inventario', 'plano'], etapa_concluida: 'plano', proxima_etapa: 'busca', concluida: false, estado_legivel: true},
  conversas_interrompidas: [{id: 'c'.repeat(32), titulo: 'Contratos da merenda', rodada: 'R002', area: 'codex'}],
  quadros: [{quadro: 'hipoteses', pendentes: 2, total: 3, area: 'apuracao', erro: null},
    {quadro: 'diligencias', pendentes: 0, total: 1, area: 'diligencias', erro: null},
    {quadro: 'tabelas', pendentes: null, total: null, area: 'apuracao', erro: 'ilegivel'}],
  rascunhos: [{tela: 'pergunta', versao: 3, atualizado_em_utc: '2026-11-19T13:00:00Z', area: 'codex'}],
  pendencias: [], aviso: 'Resumo dos registros da apuração; não confere conteúdo nem substitui a leitura dos originais.'};

async function abrir({rascunhos = servidorRascunhos(), local = memoria(), semRede = () => false,
  area = 'codex', resumo = RESUMO, papel = 'admin', modo = 'local', sessao = {}} = {}) {
  const relogio = [], envios = [];
  const mesa = criarMesa({catalogo: [ALFA], url: `http://127.0.0.1:8765/?area=${area}&caso=alfa`, papel, modo,
    api: (op, dados) => {
      if (op === 'sessao') return sessao;
      if (op === 'continuidade-resumo') { if (resumo instanceof Error) throw resumo; return resumo; }
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

test('trocar de conversa na pausa envia o texto da conversa que ficou, sem apagá-lo', async () => {
  const t = await abrir({semRede: () => true});
  await t.escrever('Pergunta da conversa nova');
  const outra = 'd'.repeat(32), opcao = t.mesa.doc.createElement('option');
  opcao.value = outra; opcao.textContent = 'Outra conversa'; t.mesa.$('codex-conversa').append(opcao);
  t.mesa.$('codex-conversa').value = outra;
  t.mesa.$('codex-conversa').dispatchEvent(new Evento('change', {bubbles: true}));
  await t.mesa.esperar(10);
  const daNova = t.salvamentos().filter(e => e.dados.tela === 'pergunta');
  assert.deepEqual(daNova.map(e => e.dados.conteudo), [{pergunta: 'Pergunta da conversa nova'}], 'o texto enviado é o da tela que ficou');
  assert.ok(!t.salvamentos().some(e => e.dados.tela === 'pergunta' && e.dados.conteudo.pergunta !== 'Pergunta da conversa nova'));
  assert.ok(!t.envios.some(e => e.op === 'rascunhos-descartar'), 'nada é descartado na troca');
  assert.equal(JSON.parse(t.local.getItem(PREFIXO + 'pergunta')).conteudo.pergunta, 'Pergunta da conversa nova');
});

test('cada item de um quadro tem o próprio rascunho; fechar outro item não o apaga', async () => {
  const rascunhos = servidorRascunhos(), local = memoria();
  const abrirItem = async (t, achado) => {
    t.mesa.$('revisao-afirmacao').textContent = achado;
    t.mesa.$('revisao-dialogo').showModal();
    t.mesa.$('revisao-observacao').dispatchEvent(new Evento('focusin', {bubbles: true}));
    await t.mesa.esperar(8);
  };
  const ofertaQuadro = t => t.mesa.$('revisao-dialogo').querySelector('.rascunho-oferta');
  const primeira = await abrir({rascunhos, local});
  await abrirItem(primeira, 'Achado F1: o contrato custou R$ 10 mil.');
  primeira.mesa.$('revisao-observacao').value = 'Conferir a página 3 do contrato';
  primeira.mesa.$('revisao-observacao').dispatchEvent(new Evento('input', {bubbles: true}));
  await primeira.mesa.esperar(6);
  await primeira.avancar();
  const telaF1 = primeira.salvamentos()[0].dados.tela;
  assert.match(telaF1, /^quadro-revisao\/[0-9a-f]{16}$/);
  // The page closes; another finding is opened and closed without typing.
  const segunda = await abrir({rascunhos, local});
  await abrirItem(segunda, 'Achado F2: a obra atrasou.');
  assert.equal(ofertaQuadro(segunda).hidden, true, 'o rascunho de F1 não é oferecido em F2');
  segunda.mesa.$('revisao-dialogo').close();
  await segunda.mesa.esperar(10);
  assert.ok(!segunda.envios.some(e => e.op === 'rascunhos-descartar' && e.dados.tela === telaF1));
  assert.equal(rascunhos.telas.get(telaF1).conteudo.revisao_observacao, 'Conferir a página 3 do contrato');
  // F1 again: its own draft is offered.
  const terceira = await abrir({rascunhos, local});
  await abrirItem(terceira, 'Achado F1: o contrato custou R$ 10 mil.');
  assert.equal(ofertaQuadro(terceira).hidden, false);
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

test('com contas, a cópia deste navegador é de cada conta: B não recebe o rascunho de A', async () => {
  const local = memoria();
  // Account A writes offline and the window closes without Sair (session expired).
  const a = await abrir({local, modo: 'piloto', sessao: {conta: {id: 'aaaa1111'}}, semRede: () => true});
  await a.escrever('Pauta não publicada de A');
  assert.equal(JSON.parse(local.getItem('vlado:rascunho-tela:aaaa1111:alfa:pergunta')).conteudo.pergunta, 'Pauta não publicada de A');
  assert.deepEqual([...local.dados.keys()].filter(k => k.includes(':sessao:')), [], 'nenhuma chave comum a todas as contas');
  // Account B signs in on the same browser: no offer, and A's copy is not touched.
  const b = await abrir({local, modo: 'piloto', sessao: {conta: {id: 'bbbb2222'}}, semRede: () => true});
  assert.equal(b.oferta().hidden, true);
  await b.escrever('Texto de B');
  assert.equal(JSON.parse(local.getItem('vlado:rascunho-tela:aaaa1111:alfa:pergunta')).conteudo.pergunta, 'Pauta não publicada de A');
  assert.equal(JSON.parse(local.getItem('vlado:rascunho-tela:bbbb2222:alfa:pergunta')).conteudo.pergunta, 'Texto de B');
  // A comes back: the offer is A's own text.
  const deNovo = await abrir({local, modo: 'piloto', sessao: {conta: {id: 'aaaa1111'}}, semRede: () => true});
  assert.equal(deNovo.oferta().hidden, false);
  deNovo.botao('Restaurar rascunho').click();
  await deNovo.mesa.esperar(10);
  assert.equal(deNovo.mesa.$('codex-pergunta').value, 'Pauta não publicada de A');
});

test('com contas e sessão desconhecida, nada vai para o navegador', async () => {
  const local = memoria({'vlado:rascunho-tela:sessao:alfa:pergunta': JSON.stringify({conteudo: {pergunta: 'antigo'}, versao: 0, em: '2026-11-19T10:00:00Z', pendente: true})});
  const t = await abrir({local, modo: 'piloto', sessao: {}});
  assert.equal(t.oferta().hidden, true, 'chave sem conta conhecida não é oferecida');
  await t.escrever('Sem conta conhecida');
  assert.deepEqual([...local.dados.keys()].filter(k => k.startsWith('vlado:rascunho-tela:')), ['vlado:rascunho-tela:sessao:alfa:pergunta']);
  await t.avancar();
  assert.equal(t.salvamentos().length, 1, 'a cópia do servidor continua');
});

// Header indicator (Rascunhos.indicador): the Interface consumes it without editing continuidade.js.
test('indicador agregado: salvando, salvo às HH:MM e sem conexão, por assinatura e por evento', async () => {
  let offline = false;
  const t = await abrir({semRede: () => offline});
  const indicador = t.mesa.janela.Rascunhos.indicador;
  const vistos = [], eventos = [];
  const cancelar = indicador.assinar(estado => vistos.push(estado));
  t.mesa.doc.addEventListener('vlado:rascunho-estado', e => eventos.push(e.detail));
  assert.equal(vistos[0].tipo, 'ocioso', 'a assinatura recebe o estado atual na hora');
  await t.escrever('Quanto custou a merenda?');
  await t.avancar();
  assert.ok(vistos.some(v => v.tipo === 'salvando'));
  assert.equal(indicador.estado().tipo, 'salvo');
  assert.match(indicador.estado().hora, /^\d{2}:\d{2}$/);
  assert.equal(eventos.at(-1).tipo, 'salvo');
  offline = true;
  await t.escrever('Sem rede agora');
  await t.avancar();
  assert.equal(indicador.estado().tipo, 'sem_rede');
  assert.equal(indicador.estado().telas, 1, 'uma tela com envio pendente');
  cancelar();
  const total = vistos.length;
  await t.escrever('Depois de cancelar');
  await t.avancar();
  assert.equal(vistos.length, total, 'quem cancelou não recebe mais avisos');
});

test('indicador mostra a escolha pendente num conflito entre abas', async () => {
  const rascunhos = servidorRascunhos();
  const t = await abrir({rascunhos});
  rascunhos.telas.set('pergunta', {versao: 1, conteudo: {pergunta: 'Da outra aba'}, em: '2026-11-19T14:00:00Z'});
  await t.escrever('Desta aba');
  await t.avancar();
  assert.equal(t.mesa.janela.Rascunhos.indicador.estado().tipo, 'decidir');
});

// Resume summary at the case entry (Continuidade.montar, called by the home card).
test('entrada do caso mostra concluído e pendente com links para cada pendência', async () => {
  const t = await abrir({area: 'inicio'});
  await t.mesa.esperar(10);
  assert.ok(t.mesa.chamadas.some(c => c.operacao === 'continuidade-resumo' && c.dados.caso === 'alfa'));
  const caixa = t.mesa.doc.querySelector('.continuidade-resumo');
  assert.ok(caixa, 'o resumo aparece na entrada do caso');
  const feito = caixa.querySelector('.mesa-resume-done').textContent;
  assert.match(feito, /3 documentos cadastrados/);
  assert.match(feito, /Análise R002: concluída até a etapa «plano»/);
  assert.match(feito, /Diligências encerradas: 1/);
  const links = caixa.querySelector('.mesa-resume-pending').querySelectorAll('a');
  const textos = links.map(a => a.textContent);
  assert.deepEqual(textos, ['Páginas sem texto extraível: visual.pdf', 'Análise R002: próxima etapa «busca»',
    'Conversa interrompida, pronta para retomar: Contratos da merenda', 'Hipóteses em aberto: 2',
    'Não foi possível ler as tabelas.', textos.at(-1)]);
  assert.match(textos.at(-1), /^Pergunta em preparo guardada às \d{2}:\d{2}$/);
  assert.deepEqual(links.map(a => a.dataset.area), ['documentos', 'codex', 'codex', 'apuracao', 'apuracao', 'codex']);
  assert.match(links[0].href, /area=documentos/);
  links[0].click();
  await t.mesa.esperar(6);
  assert.equal(t.mesa.$('area-documentos').hidden, false, 'o link abre a área da pendência');
});

test('resumo sem pendências e falha do servidor têm mensagens próprias', async () => {
  const vazio = {...RESUMO, documentos: {cadastrados: 1, pendentes: []}, rodada: null, conversas_interrompidas: [],
    quadros: [], rascunhos: []};
  const t = await abrir({area: 'inicio', resumo: vazio});
  await t.mesa.esperar(10);
  assert.match(t.mesa.doc.querySelector('.mesa-resume-pending').textContent, /Nada pendente nesta apuração\./);
  const falha = await abrir({area: 'inicio', resumo: new Error('Apuração indisponível.')});
  await falha.mesa.esperar(10);
  assert.match(falha.mesa.doc.querySelector('.mesa-resume-progress').textContent, /Não foi possível montar o resumo agora\./);
});

test('convidado não pede o resumo de retomada', async () => {
  const t = await abrir({area: 'inicio', papel: 'convidado'});
  await t.mesa.esperar(10);
  assert.ok(!t.mesa.chamadas.some(c => c.operacao === 'continuidade-resumo'));
});
