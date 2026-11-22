'use strict';
// Contract section 3: visible save states and the per-tab draft in sessionStorage.
// "Nota salva" appears only after the server's 200; the draft survives a network failure and a
// reload of the tab, is offered back when the note reopens, and is cleared on a confirmed save
// and on logout. Nothing goes to localStorage.
const test = require('node:test');
const assert = require('node:assert/strict');
const {criarMesa, PILHA, Evento} = require('./dom_minimo.cjs');

const ALFA = {id: 'alfa', titulo: 'Pauta Alfa', rodadas: []};
const CONTA = {origem: 'conta_autenticada_da_mesa', conta_id: 'k1', nome: 'Ana Lima'};
const SALVO_EM = '2026-11-13T14:05:00+00:00';
const CHAVE = 'vlado:rascunho:local:alfa:n1';

const nota = (over = {}) => ({id: 'n1', titulo: 'Contratos', texto: 'Texto salvo.', fontes: [], revisao: 3,
  criado_em_utc: SALVO_EM, atualizado_em_utc: SALVO_EM, criado_por: CONTA, atualizado_por: CONTA, ...over});
const resumo = n => ({id: n.id, titulo: n.titulo, atualizado_em_utc: n.atualizado_em_utc, criado_em_utc: n.criado_em_utc,
  revisao: n.revisao, fontes: n.fontes.length, autor: n.atualizado_por?.nome || null});

function memoria(inicial = {}) {
  const dados = new Map(Object.entries(inicial));
  return {dados, getItem: k => dados.get(k) ?? null, setItem: (k, v) => dados.set(k, String(v)), removeItem: k => dados.delete(k),
    key: i => [...dados.keys()][i] ?? null, get length() { return dados.size; }};
}

// Fetch with status codes; `salvar` may throw TypeError (dropped connection) or return {__status}.
async function abrir({salvar, notaServidor = nota(), outras = [], sessao = {}, modo = 'local', papel = 'admin', catalogo = [ALFA]} = {}) {
  const chamadas = [], relogio = [], armazenamento = memoria(sessao), local = memoria();
  let banco = structuredClone(notaServidor);
  const responder = async (op, dados) => {
    if (op === 'apuracao-notas') return {caso: dados.caso, revisao_caderno: 9, notas: dados.caso === 'alfa' ? [resumo(banco), ...outras.map(resumo)] : []};
    if (op === 'apuracao-nota') return {caso: 'alfa', revisao_caderno: 9, nota: structuredClone(outras.find(n => n.id === dados.nota_id) || banco), fontes: []};
    if (op === 'apuracao-nota-salvar') {
      if (salvar) { const r = await salvar(dados, banco); if (r?.nota) banco = structuredClone(r.nota); return r; }
      if (dados.revisao_nota !== banco.revisao) return {__status: 409, corpo: {estado: 'erro', codigo: 'conflito', erro: 'Conflito.'}};
      banco = {...banco, titulo: dados.titulo, texto: dados.texto, revisao: banco.revisao + 1, atualizado_em_utc: SALVO_EM};
      return {estado: 'salvo', revisao_caderno: 10, nota_id: 'n1', nota: structuredClone(banco), salvo_em_utc: SALVO_EM};
    }
    if (op === 'apuracao-nota-inserir') {
      const nova = nota({id: 'n9', titulo: 'Seleção documental', texto: '> Trecho.\n\n[Fonte 1]', revisao: 1, atualizado_em_utc: '2026-11-14T10:00:00+00:00'});
      outras.push(nova);
      return {estado: 'salvo', revisao_caderno: 11, nota_id: 'n9', nota: structuredClone(nova), salvo_em_utc: nova.atualizado_em_utc};
    }
    if (op === 'inventario') return {caso_id: 'alfa', corpus_id: 'c1', documentos: [], total_documentos: 0};
    if (op === 'codex-listar') return {conversas: []};
    return {};
  };
  const mesa = criarMesa({modo, papel, catalogo, scripts: PILHA.filter(nome => !['editor_notas.js', 'dialogo.js'].includes(nome)),
    url: 'http://127.0.0.1:8765/?area=apuracao&caso=alfa',
    preparar: janela => {
      janela.sessionStorage = armazenamento;
      janela.localStorage = local;
      janela.setTimeout = (funcao, ms, ...args) => {
        if ((ms || 0) < 1000) return setTimeout(funcao, ms, ...args);
        const item = {funcao, args, ms}; relogio.push(item); return item;
      };
      janela.clearTimeout = item => { const i = relogio.indexOf(item); if (i >= 0) relogio.splice(i, 1); else clearTimeout(item); };
      let uuid = 0;
      janela.crypto = {randomUUID: () => `00000000-0000-4000-8000-${String(++uuid).padStart(12, '0')}`};
      janela.getSelection = () => null;
      janela.confirmar = true; janela.confirmacoes = 0;
      janela.Dialogo = {confirmar: async opcoes => { janela.confirmacoes++; janela.ultimaConfirmacao = opcoes; return janela.confirmar; }};
      janela.navigator = {clipboard: {writeText: async () => {}}};
      janela.fetch = async (rota, opcoes = {}) => {
        if (String(rota) === '/api/catalogo') return {ok: true, json: async () => ({casos: catalogo})};
        const op = String(rota).replace(/^\/api\//, ''), dados = opcoes.body ? JSON.parse(opcoes.body) : {};
        chamadas.push({op, dados});
        const resposta = await responder(op, dados);
        if (resposta?.__status) return {ok: false, status: resposta.__status, json: async () => { if (resposta.semJson) throw new SyntaxError('html'); return resposta.corpo; }};
        return {ok: true, status: 200, json: async () => resposta, blob: async () => resposta};
      };
    }});
  await mesa.esperar(16);
  const avancar = async () => { for (const item of relogio.splice(0)) item.funcao(...item.args); await mesa.esperar(10); };
  const escrever = async texto => {
    mesa.$('apuracao-texto').value = texto;
    mesa.$('apuracao-texto').dispatchEvent(new Evento('input', {bubbles: true}));
    await mesa.esperar(2);
  };
  const salvamentos = () => chamadas.filter(c => c.op === 'apuracao-nota-salvar');
  const estado = () => [mesa.$('apuracao-salvamento').dataset.estado, mesa.$('apuracao-salvamento').textContent];
  const rascunho = () => { const v = armazenamento.getItem(CHAVE); return v && JSON.parse(v); };
  return {mesa, chamadas, avancar, escrever, salvamentos, estado, rascunho, armazenamento, local, banco: () => banco};
}
const hora = iso => new Date(iso).toLocaleTimeString('pt-BR', {hour: '2-digit', minute: '2-digit'});

test('estados do contrato: pendente → salvando → "Nota salva às HH:MM" só depois do 200', async () => {
  let liberar;
  const f = await abrir({salvar: (dados, banco) => new Promise(ok => { liberar = () => ok({estado: 'salvo', revisao_caderno: 10, nota_id: 'n1',
    nota: {...banco, texto: dados.texto, revisao: 4}, salvo_em_utc: SALVO_EM}); })});
  await f.escrever('Versão nova');
  assert.deepEqual(f.estado(), ['pendente', 'Alterações não salvas']);
  await f.avancar();
  assert.deepEqual(f.estado(), ['salvando', 'Salvando…']);
  liberar(); await f.mesa.esperar(10);
  assert.deepEqual(f.estado(), ['salvo', `Nota salva às ${hora(SALVO_EM)}`]);
});

test('cada mudança guarda rascunho só na sessionStorage, com base e hora; salvamento confirmado apaga', async () => {
  const f = await abrir();
  await f.escrever('Rascunho em andamento');
  const guardado = f.rascunho();
  assert.equal(guardado.texto, 'Rascunho em andamento');
  assert.equal(guardado.titulo, 'Contratos');
  assert.equal(guardado.revisao_base, 3);
  assert.ok(!Number.isNaN(Date.parse(guardado.em)), 'hora do rascunho');
  assert.deepEqual([...f.local.dados.keys()].filter(k => k.includes('rascunho')), [], 'nada em localStorage');
  assert.ok(![...f.local.dados.values()].some(v => v.includes('Rascunho em andamento')), 'texto da nota fora do localStorage');
  await f.avancar();
  assert.equal(f.estado()[0], 'salvo');
  assert.equal(f.rascunho(), null, 'apagado após o 200');
});

test('título também entra no rascunho', async () => {
  const f = await abrir();
  f.mesa.$('apuracao-nota-titulo').value = 'Título novo';
  f.mesa.$('apuracao-nota-titulo').dispatchEvent(new Evento('input', {bubbles: true}));
  await f.mesa.esperar(2);
  assert.equal(f.rascunho().titulo, 'Título novo');
});

test('falha de rede: estado "rede", rascunho mantido; reconexão volta a salvando e confirma', async () => {
  let online = false;
  const f = await abrir({salvar: (dados, banco) => {
    if (!online) throw new TypeError('Failed to fetch');
    return {estado: 'salvo', revisao_caderno: 10, nota_id: 'n1', nota: {...banco, texto: dados.texto, revisao: 4}, salvo_em_utc: SALVO_EM};
  }});
  await f.escrever('Texto que não pode sumir');
  await f.avancar();
  assert.deepEqual(f.estado(), ['rede', 'Sem conexão. Rascunho guardado nesta aba; tentando de novo…']);
  assert.equal(f.rascunho().texto, 'Texto que não pode sumir');
  online = true;
  f.mesa.janela.dispatchEvent(new Evento('online'));
  await f.mesa.esperar(10);
  assert.equal(f.estado()[0], 'salvo', 'o evento online tenta de novo sem esperar o intervalo');
  assert.equal(f.rascunho(), null);
});

test('sessão expirada: estado "sessao", sem novas tentativas, rascunho continua na aba', async () => {
  const f = await abrir({salvar: () => ({__status: 401, corpo: {estado: 'sem_sessao', erro: 'Sessão expirada.'}})});
  await f.escrever('Escrito antes de expirar');
  await f.avancar();
  assert.deepEqual(f.estado(), ['sessao', 'Sessão expirada. Entre de novo; o rascunho continua nesta aba.']);
  await f.avancar();
  assert.equal(f.salvamentos().length, 1, 'não insiste com a sessão expirada');
  assert.equal(f.rascunho().texto, 'Escrito antes de expirar');
});

test('ao reabrir com rascunho mais novo sobre a mesma base, oferece restaurar; restaurar salva', async () => {
  const sessao = {[CHAVE]: JSON.stringify({titulo: 'Contratos', texto: 'Rascunho recuperado', revisao_base: 3, em: '2026-11-13T15:00:00Z'})};
  const f = await abrir({sessao});
  assert.equal(f.mesa.$('apuracao-rascunho').hidden, false);
  assert.match(f.mesa.$('apuracao-rascunho-texto').textContent, /rascunho não salvo/);
  assert.equal(f.mesa.$('apuracao-texto').value, 'Texto salvo.', 'nada muda antes da escolha');
  assert.equal(f.mesa.$('apuracao-nota-titulo').readOnly, true, 'edição espera a escolha');
  f.mesa.$('apuracao-rascunho-restaurar').click();
  await f.mesa.esperar(4);
  assert.equal(f.mesa.$('apuracao-texto').value, 'Rascunho recuperado');
  assert.equal(f.mesa.$('apuracao-rascunho').hidden, true);
  assert.equal(f.mesa.$('apuracao-nota-titulo').readOnly, false);
  await f.avancar();
  assert.equal(f.salvamentos().at(-1).dados.texto, 'Rascunho recuperado');
  assert.equal(f.salvamentos().at(-1).dados.revisao_nota, 3);
  assert.equal(f.estado()[0], 'salvo');
  assert.equal(f.rascunho(), null);
});

test('descartar o rascunho oferecido apaga e mantém o texto do servidor', async () => {
  const sessao = {[CHAVE]: JSON.stringify({titulo: 'Contratos', texto: 'Rascunho velho', revisao_base: 3, em: '2026-11-13T15:00:00Z'})};
  const f = await abrir({sessao});
  f.mesa.$('apuracao-rascunho-descartar').click();
  await f.mesa.esperar(4);
  assert.equal(f.rascunho(), null);
  assert.equal(f.mesa.$('apuracao-texto').value, 'Texto salvo.');
  assert.equal(f.salvamentos().length, 0);
});

test('rascunho igual ao que está no servidor é apagado sem perguntar (salvamento chegou, resposta perdida)', async () => {
  const sessao = {[CHAVE]: JSON.stringify({titulo: 'Contratos', texto: 'Texto salvo.', revisao_base: 2, em: '2026-11-13T15:00:00Z'})};
  const f = await abrir({sessao});
  assert.equal(f.mesa.$('apuracao-rascunho').hidden, true);
  assert.equal(f.mesa.$('apuracao-conflito').hidden, true);
  assert.equal(f.rascunho(), null);
});

test('rascunho sobre base antiga (nota mudou no servidor) vira conflito, sem sobrescrever', async () => {
  const sessao = {[CHAVE]: JSON.stringify({titulo: 'Contratos', texto: 'Meu rascunho antigo', revisao_base: 1, em: '2026-11-13T15:00:00Z'})};
  const f = await abrir({sessao});
  assert.equal(f.estado()[0], 'conflito');
  assert.equal(f.mesa.$('apuracao-conflito').hidden, false);
  assert.equal(f.mesa.$('apuracao-texto').value, 'Meu rascunho antigo', 'o texto local fica na tela para copiar');
  await f.avancar();
  assert.equal(f.salvamentos().length, 0, 'conflito não grava');
  assert.equal(f.rascunho().texto, 'Meu rascunho antigo', 'rascunho preservado até recarregar');
  f.mesa.$('apuracao-copiar').click(); await f.mesa.esperar(4);
  f.mesa.$('apuracao-recarregar').click(); await f.mesa.esperar(12);
  assert.equal(f.mesa.$('apuracao-texto').value, 'Texto salvo.');
  assert.equal(f.rascunho(), null, 'recarregar a pedido descarta o rascunho');
});

test('conflito 409 ao salvar mantém o rascunho na aba', async () => {
  const f = await abrir({salvar: () => ({__status: 409, corpo: {estado: 'erro', codigo: 'conflito', erro: 'Conflito.'}})});
  await f.escrever('Texto local');
  await f.avancar();
  assert.equal(f.estado()[0], 'conflito');
  assert.equal(f.rascunho().texto, 'Texto local');
});

test('limparRascunhosCaderno() apaga só os rascunhos do caderno (logout)', async () => {
  const f = await abrir({sessao: {'outra-chave': 'x'}});
  await f.escrever('Rascunho');
  f.armazenamento.setItem('vlado:rascunho:local:beta:n9', '{}');
  assert.equal(typeof f.mesa.janela.limparRascunhosCaderno, 'function');
  f.mesa.janela.limparRascunhosCaderno();
  assert.deepEqual([...f.armazenamento.dados.keys()], ['outra-chave']);
});

test('sem sessionStorage disponível o caderno continua salvando', async () => {
  const f = await abrir();
  Object.defineProperty(f.mesa.janela, 'sessionStorage', {get() { throw new Error('bloqueado'); }});
  await f.escrever('Sem armazenamento');
  await f.avancar();
  assert.equal(f.estado()[0], 'salvo');
  assert.deepEqual(f.mesa.erros, []);
});

test('excluir a nota apaga o rascunho dela', async () => {
  const f = await abrir({salvar: () => { throw new TypeError('Failed to fetch'); }});
  await f.escrever('Vai ser excluída');
  assert.ok(f.rascunho());
  f.mesa.$('apuracao-excluir').click();
  await f.mesa.esperar(12);
  assert.equal(f.mesa.janela.ultimaConfirmacao.item, f.mesa.$('apuracao-nota-titulo').value, 'o diálogo de excluir nomeia a nota (e não "Excluir ?")');
  assert.ok(f.mesa.janela.ultimaConfirmacao.item, 'a nota tem título');
  assert.ok(f.chamadas.some(c => c.op === 'apuracao-nota-excluir'));
  assert.equal(f.rascunho(), null);
});

test('contagem de tarefas na barra da nota: "n de m tarefas concluídas"', async () => {
  const f = await abrir({notaServidor: nota({texto: '- [x] Ligar\n- [ ] Conferir\n* [X] Pedir\n- item comum'})});
  assert.equal(f.mesa.$('apuracao-tarefas').hidden, false);
  assert.equal(f.mesa.$('apuracao-tarefas').textContent, '2 de 3 tarefas concluídas');
  await f.escrever('Sem tarefas');
  assert.equal(f.mesa.$('apuracao-tarefas').hidden, true);
});

test('busca de notas filtra a lista pelo título, sem acentos nem caixa', async () => {
  const f = await abrir();
  const busca = f.mesa.$('apuracao-busca');
  busca.value = 'CONTRATO';
  busca.dispatchEvent(new Evento('input', {bubbles: true}));
  assert.equal(f.mesa.$('apuracao-notas').querySelectorAll('button').length, 1);
  busca.value = 'inexistente';
  busca.dispatchEvent(new Evento('input', {bubbles: true}));
  assert.equal(f.mesa.$('apuracao-notas').querySelectorAll('button').length, 0);
  assert.match(f.mesa.$('apuracao-busca-status').textContent, /Nenhuma nota/);
});

test('eco tardio do editor com o texto já salvo não deixa rascunho; trocar de nota depois de salvar limpa', async () => {
  const f = await abrir();
  await f.escrever('Texto salvo.\n');  // Vditor's late callback: the saved Markdown plus a final newline
  assert.equal(f.rascunho(), null);
  await f.escrever('Mudança real');
  assert.equal(f.rascunho().texto, 'Mudança real');
  await f.avancar();
  assert.equal(f.rascunho(), null);
});

test('rascunho oferecido e ainda não decidido sobrevive a olhar outra nota', async () => {
  const sessao = {[CHAVE]: JSON.stringify({titulo: 'Contratos', texto: 'Rascunho pendente', revisao_base: 3, em: '2026-11-13T15:00:00Z'})};
  const outra = nota({id: 'n2', titulo: 'Pagamentos', texto: 'Outra.', atualizado_em_utc: '2026-01-01T00:00:00+00:00'});
  const f = await abrir({sessao, outras: [outra]});
  assert.equal(f.mesa.$('apuracao-rascunho').hidden, false);
  f.mesa.$('apuracao-notas').querySelectorAll('button')[1].click();
  await f.mesa.esperar(12);
  assert.equal(f.mesa.$('apuracao-nota-titulo').value, 'Pagamentos');
  assert.equal(f.rascunho().texto, 'Rascunho pendente');
});

test('trocar de apuração com alteração pendente salva antes de carregar a outra', async () => {
  const BETA = {id: 'beta', titulo: 'Pauta Beta', rodadas: []};
  const f = await abrir({catalogo: [ALFA, BETA]});
  await f.escrever('Escrito antes de trocar');
  const select = f.mesa.$('apuracao-caso');
  select.value = 'beta';
  select.dispatchEvent(new Evento('change', {bubbles: true}));
  await f.mesa.esperar(16);
  assert.equal(f.salvamentos().length, 1, 'salvou a nota antes de trocar');
  assert.equal(f.salvamentos()[0].dados.texto, 'Escrito antes de trocar');
  assert.equal(f.rascunho(), null);
});

// Review (H1–H3, M2, M3, L4) regressions.
async function inserirEm(f, destino) {
  const botao = f.mesa.janela.botaoAdicionarApuracao({caso: 'alfa', rodada: 'R1', geracao: 'v1', tipo: 'pesquisa', referencia: 'P1'}, null, 'Trecho.');
  botao.click();
  await f.mesa.esperar(10);
  f.mesa.$('apuracao-destino').value = destino;
  f.mesa.$('apuracao-adicionar-form').requestSubmit();
  await f.mesa.esperar(20);
}

test('inserir em outra nota salva antes a nota aberta', async () => {
  const f = await abrir();
  await f.escrever('Pendente antes de inserir');
  await inserirEm(f, '');
  const ops = f.chamadas.map(c => c.op).filter(op => /salvar|inserir/.test(op));
  assert.deepEqual(ops, ['apuracao-nota-salvar', 'apuracao-nota-inserir']);
  assert.equal(f.salvamentos()[0].dados.texto, 'Pendente antes de inserir');
  assert.equal(f.mesa.$('apuracao-nota-titulo').value, 'Seleção documental');
});

test('inserir em outra nota sem conseguir salvar: recusar o descarte mantém tudo', async () => {
  const f = await abrir({salvar: () => { throw new TypeError('Failed to fetch'); }});
  await f.escrever('Texto sem rede');
  f.mesa.janela.confirmar = false;
  await inserirEm(f, '');
  assert.equal(f.chamadas.filter(c => c.op === 'apuracao-nota-inserir').length, 0, 'não insere');
  assert.equal(f.mesa.$('apuracao-texto').value, 'Texto sem rede');
  assert.equal(f.rascunho().texto, 'Texto sem rede');
  assert.equal(f.mesa.$('apuracao-adicionar-erro').hidden, false);
});

test('descartar com reenvio pendente: o texto descartado não é enviado quando a rede volta', async () => {
  let online = false;
  const outra = nota({id: 'n2', titulo: 'Pagamentos', texto: 'Outra.', atualizado_em_utc: '2026-01-01T00:00:00+00:00'});
  const f = await abrir({outras: [outra], salvar: (dados, banco) => {
    if (!online) throw new TypeError('Failed to fetch');
    return {estado: 'salvo', revisao_caderno: 10, nota_id: dados.nota_id, nota: {...banco, texto: dados.texto, revisao: 4}, salvo_em_utc: SALVO_EM};
  }});
  await f.escrever('Texto que será descartado');
  await f.avancar();
  assert.equal(f.estado()[0], 'rede');
  f.mesa.$('apuracao-notas').querySelectorAll('button')[1].click();   // confirm() = true: discard
  await f.mesa.esperar(16);
  assert.equal(f.mesa.$('apuracao-nota-titulo').value, 'Pagamentos');
  const antes = f.salvamentos().length;
  online = true;
  f.mesa.janela.dispatchEvent(new Evento('online'));
  await f.avancar();
  assert.equal(f.salvamentos().length, antes, 'nenhum reenvio do texto descartado');
  assert.equal(f.rascunho(), null);
});

test('Sair: com alteração que não salva, pergunta; recusar mantém, aceitar para tudo e não regrava rascunho', async () => {
  const f = await abrir({salvar: () => { throw new TypeError('Failed to fetch'); }});
  await f.escrever('Rascunho na saída');
  f.mesa.janela.confirmar = false;
  assert.equal(await f.mesa.janela.prepararSaidaCaderno(), false);
  assert.equal(f.rascunho().texto, 'Rascunho na saída');
  f.mesa.janela.confirmar = true;
  assert.equal(await f.mesa.janela.prepararSaidaCaderno(), true);
  f.mesa.janela.limparRascunhosCaderno();
  assert.equal(f.rascunho(), null);
  const antes = f.salvamentos().length;
  await f.escrever('Depois de sair');
  f.mesa.janela.dispatchEvent(new Evento('online'));
  f.mesa.janela.dispatchEvent(new Evento('pagehide'));
  await f.avancar();
  assert.equal(f.rascunho(), null, 'nada é regravado depois do logout');
  assert.equal(f.salvamentos().length, antes, 'nem reenviado');
});

test('Sair sem pendências salva e segue sem perguntar', async () => {
  const f = await abrir();
  await f.escrever('Salvo na saída');
  assert.equal(await f.mesa.janela.prepararSaidaCaderno(), true);
  assert.equal(f.mesa.janela.confirmacoes, 0);
  assert.equal(f.salvamentos().at(-1).dados.texto, 'Salvo na saída');
});

test('copiar só conta quando a cópia funcionou e uma edição depois volta a pedir confirmação', async () => {
  const f = await abrir({salvar: () => ({__status: 409, corpo: {estado: 'erro', codigo: 'conflito', erro: 'Conflito.'}})});
  await f.escrever('Local');
  await f.avancar();
  f.mesa.janela.navigator.clipboard.writeText = async () => { throw new Error('negado'); };
  f.mesa.$('apuracao-copiar').click(); await f.mesa.esperar(4);
  f.mesa.janela.confirmar = false;
  f.mesa.$('apuracao-recarregar').click(); await f.mesa.esperar(8);
  assert.equal(f.mesa.janela.confirmacoes, 1, 'cópia falhou: pede confirmação');
  assert.equal(f.mesa.$('apuracao-texto').value, 'Local');
  f.mesa.janela.navigator.clipboard.writeText = async () => {};
  f.mesa.$('apuracao-copiar').click(); await f.mesa.esperar(4);
  await f.escrever('Local, editado depois de copiar');
  f.mesa.$('apuracao-recarregar').click(); await f.mesa.esperar(8);
  assert.equal(f.mesa.janela.confirmacoes, 2, 'editar depois de copiar volta a pedir');
});

test('erro do servidor sem JSON (500) vai a "erro" com mensagem e não reenvia', async () => {
  const f = await abrir({salvar: () => ({__status: 500, semJson: true})});
  await f.escrever('Texto');
  await f.avancar();
  assert.equal(f.estado()[0], 'erro');
  assert.equal(f.mesa.$('apuracao-erro').hidden, false);
  await f.avancar(); await f.avancar();
  assert.equal(f.salvamentos().length, 1, 'sem reenvio automático');
  assert.equal(f.rascunho().texto, 'Texto', 'o rascunho fica');
});

test('pagehide salva o que está pendente', async () => {
  const f = await abrir();
  await f.escrever('Saindo da página');
  f.mesa.janela.dispatchEvent(new Evento('pagehide'));
  await f.mesa.esperar(10);
  assert.equal(f.salvamentos().length, 1);
  assert.equal(f.estado()[0], 'salvo');
});
