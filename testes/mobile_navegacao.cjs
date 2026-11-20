'use strict';
// Mesa em tela estreita: voltar (history/popstate) por área e por camada aberta, estados de
// conexão do acompanhamento e faixa de ambiente. DOM sintético (dom_minimo), sem rede.
const test = require('node:test');
const assert = require('node:assert/strict');
const {criarMesa} = require('./dom_minimo.cjs');

const ALFA = {id: 'alfa', titulo: 'Pauta Alfa', rodadas: [{id: 'R001', geracoes: []}]};

// Browser-like history: entries with state, back() fires popstate asynchronously.
function historico(janela) {
  const entradas = [{state: null, href: janela.location.href}];
  let indice = 0;
  const ir = href => { janela.location.href = href; };
  janela.history = {
    get state() { return entradas[indice].state; },
    get length() { return entradas.length; },
    pushState(state, _, url) {
      entradas.splice(indice + 1);
      entradas.push({state: structuredClone(state ?? null), href: new URL(url ?? janela.location.href, janela.location.href).href});
      indice++; ir(entradas[indice].href);
    },
    replaceState(state, _, url) {
      entradas[indice] = {state: structuredClone(state ?? null), href: new URL(url ?? janela.location.href, janela.location.href).href};
      ir(entradas[indice].href);
    },
    back() {
      if (indice === 0) return;
      indice--; ir(entradas[indice].href);
      setTimeout(() => janela.dispatchEvent(new janela.Event('popstate')), 0);
    },
    get indice() { return indice; },
  };
}

function abrir({url = 'http://127.0.0.1:8765/?area=documentos&caso=alfa', api, preparar, sessao} = {}) {
  return criarMesa({desktop: false, catalogo: [ALFA], url, preparar: janela => {
    historico(janela);
    preparar?.(janela);
  }, api: (operacao, dados) => {
    if (operacao === 'sessao') { if (sessao instanceof Error) throw sessao; return sessao || {}; }
    if (operacao === 'inventario') return {caso_id: 'alfa', corpus_id: 'c1', documentos: [], total_documentos: 0};
    if (operacao === 'codex-status') return {autenticado: true, provedor: 'anthropic', modelo: 'modelo-x'};
    return api ? api(operacao, dados) : {};
  }});
}
const visivel = (mesa, id) => !mesa.$(id).hidden;
// Back pops asynchronously (a task), like browsers.
async function voltar(mesa) {
  mesa.janela.history.back();
  await new Promise(resolve => setTimeout(resolve, 20));
  await mesa.esperar(16);
}

test('voltar fecha o original aberto sem trocar de área nem perder o endereço', async () => {
  const mesa = abrir();
  await mesa.esperar(12);
  const endereco = mesa.janela.location.href, antes = mesa.janela.history.indice;
  await mesa.janela.abrirOriginal(new mesa.janela.Blob(['Texto sintético.'], {type: 'text/plain'}), 'nota.txt');
  assert.equal(mesa.$('original-dialogo').open, true);
  assert.equal(mesa.janela.history.indice, antes + 1, 'o original ganha uma entrada no histórico');
  const chamadas = mesa.chamadas.length;
  await voltar(mesa);
  assert.equal(mesa.$('original-dialogo').open, false);
  assert.equal(mesa.janela.location.href, endereco);
  assert.equal(visivel(mesa, 'area-documentos'), true);
  assert.equal(mesa.chamadas.length, chamadas, 'voltar de uma camada não recarrega a área');
});

test('fechar o original pelo botão remove a entrada que ele criou', async () => {
  const mesa = abrir();
  await mesa.esperar(12);
  const antes = mesa.janela.history.indice;
  await mesa.janela.abrirOriginal(new mesa.janela.Blob(['Texto.'], {type: 'text/plain'}), 'nota.txt');
  mesa.$('original-fechar').click();
  await mesa.esperar(12);
  assert.equal(mesa.$('original-dialogo').open, false);
  assert.equal(mesa.janela.history.indice, antes, 'o próximo voltar sai da área, não reabre nada');
});

test('voltar retorna à área anterior', async () => {
  const mesa = abrir();
  await mesa.esperar(12);
  mesa.$('ver-codex').click();
  await mesa.esperar(12);
  assert.equal(visivel(mesa, 'area-codex'), true);
  mesa.$('ver-achados').click();
  await mesa.esperar(12);
  assert.equal(visivel(mesa, 'area-achados'), true);
  await voltar(mesa);
  assert.equal(visivel(mesa, 'area-codex'), true);
  assert.equal(visivel(mesa, 'area-achados'), false);
  assert.equal(new URL(mesa.janela.location.href).searchParams.get('area'), 'codex');
});

test('menu: voltar fecha a navegação; escolher uma área não deixa entrada extra', async () => {
  const mesa = abrir();
  await mesa.esperar(12);
  const base = mesa.janela.history.indice;
  mesa.$('mesa-menu').click();
  assert.equal(mesa.doc.body.classList.contains('mesa-menu-open'), true);
  assert.equal(mesa.$('mesa-menu').getAttribute('aria-expanded'), 'true');
  await voltar(mesa);
  assert.equal(mesa.doc.body.classList.contains('mesa-menu-open'), false);
  assert.equal(mesa.$('mesa-menu').getAttribute('aria-expanded'), 'false');
  assert.equal(mesa.janela.history.indice, base);
  mesa.$('mesa-menu').click();
  mesa.$('ver-codex').click();
  await mesa.esperar(12);
  assert.equal(mesa.doc.body.classList.contains('mesa-menu-open'), false);
  assert.equal(mesa.janela.history.indice, base + 1, 'a entrada do menu vira a da área escolhida');
  await voltar(mesa);
  assert.equal(visivel(mesa, 'area-documentos'), true);
});

test('diálogo com texto não salvo: voltar pergunta e, se o usuário mantiver, continua aberto', async () => {
  let confirmar = false;
  const mesa = abrir({preparar: janela => { janela.confirm = () => confirmar; }});
  await mesa.esperar(12);
  mesa.$('diligencias-dialogo').showModal();
  mesa.$('diligencias-acao').value = 'Pedir contrato';
  mesa.$('diligencias-form').dispatchEvent(new mesa.janela.Event('input'));
  await voltar(mesa);
  assert.equal(mesa.$('diligencias-dialogo').open, true, 'o texto não é descartado sem confirmação');
  confirmar = true;
  await voltar(mesa);
  assert.equal(mesa.$('diligencias-dialogo').open, false);
});

// Conversation in progress, then network loss and recovery, all on the same cursor.
function conversaEmCurso() {
  const fila = [];
  const espera = [];
  let rede = true;
  const mesa = abrir({url: 'http://127.0.0.1:8765/?area=codex&caso=alfa', preparar: janela => {
    const original = janela.fetch;
    janela.fetch = async (rota, opcoes) => {
      if (!rede && String(rota) === '/api/codex-eventos') throw new TypeError('Failed to fetch');
      return original(rota, opcoes);
    };
  }, api: operacao => {
    if (operacao === 'codex-listar') return {conversas: [{id: 'chat1', titulo: 'Merenda', estado: 'executando'}]};
    if (operacao === 'codex-eventos') {
      if (fila.length) return fila.shift();
      return new Promise(resolve => espera.push(resolve));
    }
    return {};
  }});
  const entregar = async resposta => { if (espera.length) espera.shift()(resposta); else fila.push(resposta); await mesa.esperar(12); };
  const lote = (estado, cursor, extra = {}) => ({conversa: {id: 'chat1', caso: 'alfa', estado,
    situacao: {codigo: estado === 'executando' ? 'em_andamento' : estado, mensagem: '', causa: extra.causa ?? null},
    retomavel: extra.retomavel ?? false, rodada: 'R001', rodada_pergunta: 'R001'}, eventos: extra.eventos || [], cursor, acervos: {}});
  return {mesa, entregar, lote, cair: () => { rede = false; }, voltar: () => { rede = true; }};
}

test('acompanhamento: em andamento, conexão perdida com nova tentativa e retomada no mesmo cursor', async () => {
  const {mesa, entregar, lote, cair, voltar} = conversaEmCurso();
  await mesa.esperar(12);
  mesa.$('codex-conversa').value = 'chat1';
  mesa.$('codex-conversa').dispatchEvent(new mesa.janela.Event('change'));
  await mesa.esperar(12);
  cair();
  await entregar(lote('executando', 3, {eventos: [{seq: 1, tipo: 'aviso', dados: {mensagem: 'Evento sintético'}}]}));
  const linha = mesa.$('codex-conexao-estado');
  await mesa.esperar(12);
  assert.match(linha.textContent, /Conexão perdida — a execução continua no servidor; reconectando/);
  assert.equal(linha.hidden, false);
  assert.match(mesa.$('codex-status').textContent, /Conexão perdida/);
  assert.equal(mesa.$('codex-reconectar').hidden, true, 'a reconexão é automática');
  assert.equal(mesa.$('codex-erro').hidden, true, 'perder a rede não é um erro da execução');
  assert.equal(mesa.$('codex-enviar').disabled, true);
  voltar();
  mesa.janela.dispatchEvent(new mesa.janela.Event('online'));
  await mesa.esperar(12);
  await entregar(lote('executando', 4));
  assert.match(linha.textContent, /^Em andamento/);
  assert.match(mesa.$('codex-anuncio').textContent, /Conexão restabelecida/);
  const cursores = mesa.chamadas.filter(c => c.operacao === 'codex-eventos').map(c => c.dados.cursor);
  assert.deepEqual(cursores.slice(0, 3), [0, 3, 4], 'retoma do cursor já recebido, sem perder eventos');
  assert.equal(mesa.$('codex-atividades').children.length, 1, 'evento entregue uma única vez');
  assert.equal(mesa.chamadas.some(c => c.operacao === 'codex-perguntar'), false);
});

test('acompanhamento: execução interrompida e retomável aparece como “Interrompida — retomar”', async () => {
  const {mesa, entregar, lote} = conversaEmCurso();
  await mesa.esperar(12);
  mesa.$('codex-conversa').value = 'chat1';
  mesa.$('codex-conversa').dispatchEvent(new mesa.janela.Event('change'));
  await mesa.esperar(12);
  await entregar(lote('interrompido', 2, {retomavel: true, causa: 'reinicio'}));
  assert.match(mesa.$('codex-conexao-estado').textContent, /^Interrompida — retomar/);
  assert.equal(mesa.$('codex-retomar').hidden, false);
});

test('faixa de ambiente: homologação e demonstração mostram a faixa; editorial e ausência não', async () => {
  for (const [sessao, esperado] of [[{ambiente: 'homologacao'}, 'Homologação — dados sintéticos'],
    [{ambiente: 'demonstracao'}, 'Demonstração — dados sintéticos'], [{ambiente: 'editorial'}, null],
    [new Error('Página não encontrada.'), null]]) {
    const mesa = abrir({sessao});
    await mesa.esperar(12);
    const faixa = mesa.$('mesa-ambiente');
    if (esperado) { assert.equal(faixa.hidden, false); assert.equal(faixa.textContent, esperado); }
    else { assert.equal(faixa.hidden, true); assert.equal(faixa.textContent, ''); }
  }
});
