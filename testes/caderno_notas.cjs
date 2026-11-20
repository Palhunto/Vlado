'use strict';
// Caderno in three columns: notes, editor with autosave, sources. Autosave sends one request at a
// time, retries a network failure with the same requisicao_id and stops on a 409 conflict.
const test = require('node:test');
const assert = require('node:assert/strict');
const {criarMesa, PILHA, Evento} = require('./dom_minimo.cjs');

const ALFA = {id: 'alfa', titulo: 'Pauta Alfa', rodadas: [{id: 'R002', geracoes: []}]};
const AGORA = new Date().toISOString();
const ANTIGA = '2026-01-05T15:00:00+00:00';
const CONTA = {origem: 'conta_autenticada_da_mesa', conta_id: 'k1', nome: 'Ana Lima'};
const FONTE = {id: 'F1', numero: 1, marcador: '[Fonte 1]', tipo: 'ia', caso: 'alfa', rodada: 'R002', referencia: 'A001', achado_versao: 1,
  texto_selecionado: 'O contrato vale R$ 10 mil.', adicionada_por: 'Ana Lima',
  documentos: [{indice: 0, documento_id: 'D1', nome_documento: 'D1_contrato.pdf', pagina_pdf: 12, localizador: 'Linhas 3–4',
    original_sha256: 'h', disponivel: true, abrir: {operacao: 'apuracao-original', caso: 'alfa', nota_id: 'n1', fonte_id: 'F1', documento_indice: 0}},
  {indice: 1, documento_id: 'D2', nome_documento: 'D2_planilha.csv', pagina_pdf: null, localizador: 'Linhas 8–9',
    original_sha256: 'h2', disponivel: false, abrir: {operacao: 'apuracao-original', caso: 'alfa', nota_id: 'n1', fonte_id: 'F1', documento_indice: 1}}]};

function nota(id, over = {}) {
  return {id, titulo: id === 'n1' ? 'Contratos' : 'Pagamentos', texto: id === 'n1' ? 'Valor citado.\n\n> O contrato vale R$ 10 mil.\n\n[Fonte 1]' : 'Sem fonte.',
    fontes: id === 'n1' ? [{id: 'F1'}] : [], criado_em_utc: ANTIGA, atualizado_em_utc: id === 'n1' ? AGORA : ANTIGA, revisao: 3,
    criado_por: CONTA, atualizado_por: CONTA, ...over};
}
const resumo = n => ({id: n.id, titulo: n.titulo, atualizado_em_utc: n.atualizado_em_utc, criado_em_utc: n.criado_em_utc,
  revisao: n.revisao, fontes: n.fontes.length, autor: n.atualizado_por?.nome || null});

// Own fetch: answers with status codes, rejects like a dropped connection, and a clock for timers >= 1 s.
async function abrir({salvar, inserir, notas = [nota('n1'), nota('n2')], modo = 'local', idioma = 'pt'} = {}) {
  const chamadas = [], relogio = [];
  const banco = new Map(notas.map(n => [n.id, structuredClone(n)]));
  const responder = async (op, dados) => {
    if (op === 'apuracao-notas') return {caso: 'alfa', revisao_caderno: 9, notas: [...banco.values()].map(resumo)};
    if (op === 'apuracao-nota') { const n = banco.get(dados.nota_id); return {caso: 'alfa', revisao_caderno: 9, nota: structuredClone(n), fontes: n.id === 'n1' ? [structuredClone(FONTE)] : []}; }
    if (op === 'apuracao-nota-salvar') {
      if (salvar) return salvar(dados, banco);
      const atual = banco.get(dados.nota_id) || {id: 'E' + dados.requisicao_id, fontes: [], criado_em_utc: AGORA, revisao: 0, criado_por: CONTA};
      const quando = dados.nota_id ? '2026-11-13T14:05:00+00:00' : new Date(Date.now() + 60000).toISOString();
      const salva = {...atual, titulo: dados.titulo, texto: dados.texto, revisao: atual.revisao + 1, atualizado_em_utc: quando, atualizado_por: CONTA};
      banco.set(salva.id, salva);
      return {estado: 'salvo', revisao_caderno: 10, nota_id: salva.id, nota: structuredClone(salva), salvo_em_utc: salva.atualizado_em_utc};
    }
    if (op === 'apuracao-nota-inserir') return inserir(dados, banco);
    if (op === 'apuracao-original') return {type: 'application/pdf'};
    if (op === 'inventario') return {caso_id: 'alfa', corpus_id: 'c1', documentos: [], total_documentos: 0};
    if (op === 'codex-listar') return {conversas: []};
    return {};
  };
  const mesa = criarMesa({modo, idioma, armazenamento: idioma === 'en' ? {'vlado-idioma': 'en'} : {}, catalogo: [ALFA],
    scripts: PILHA.filter(nome => nome !== 'editor_notas.js'), url: 'http://127.0.0.1:8765/?area=apuracao&caso=alfa',
    preparar: janela => {
      janela.setTimeout = (funcao, ms, ...args) => {
        if ((ms || 0) < 1000) return setTimeout(funcao, ms, ...args);
        const item = {funcao, args, ms}; relogio.push(item); return item;
      };
      janela.clearTimeout = item => { const i = relogio.indexOf(item); if (i >= 0) relogio.splice(i, 1); else clearTimeout(item); };
      let uuid = 0;
      janela.crypto = {randomUUID: () => `00000000-0000-4000-8000-${String(++uuid).padStart(12, '0')}`};
      janela.getSelection = () => null;
      janela.copiado = null;
      janela.navigator = {clipboard: {writeText: async texto => { janela.copiado = texto; }}};
      janela.fetch = async (rota, opcoes = {}) => {
        if (String(rota) === '/api/catalogo') return {ok: true, json: async () => ({casos: [ALFA]})};
        const op = String(rota).replace(/^\/api\//, ''), dados = opcoes.body ? JSON.parse(opcoes.body) : {};
        chamadas.push({op, dados});
        const resposta = await responder(op, dados);   // a TypeError here is a dropped connection
        if (resposta?.__status) return {ok: false, status: resposta.__status, json: async () => resposta.corpo};
        return {ok: true, status: 200, blob: async () => resposta, json: async () => resposta};
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
  return {mesa, chamadas, relogio, banco, avancar, escrever, salvamentos};
}
function deferido() {
  let resolve, reject;
  const promessa = new Promise((ok, erro) => { resolve = ok; reject = erro; });
  return {promessa, resolve, reject};
}
const hora = iso => new Date(iso).toLocaleTimeString('pt-BR', {hour: '2-digit', minute: '2-digit'});
const itens = mesa => mesa.$('apuracao-notas').querySelectorAll('button');

test('coluna Notas: título, quando foi atualizada, fontes e autor; a mais recente abre destacada', async () => {
  const {mesa, chamadas} = await abrir();
  assert.deepEqual(mesa.erros, []);
  const [primeira, segunda] = itens(mesa);
  assert.equal(primeira.querySelector('.note-item-title').textContent, 'Contratos');
  assert.equal(primeira.querySelector('.note-item-meta').textContent, `Atualizada às ${hora(AGORA)} · 1 fonte`);
  assert.equal(primeira.querySelector('.note-item-author').textContent, 'Autor: Ana Lima');
  assert.equal(segunda.querySelector('.note-item-meta').textContent, 'Atualizada em 05/01/2026 · 0 fontes');
  assert.equal(primeira.getAttribute('aria-current'), 'true');
  assert.deepEqual(chamadas.find(c => c.op === 'apuracao-nota').dados, {caso: 'alfa', nota_id: 'n1'});
  assert.equal(mesa.$('apuracao-nota-titulo').value, 'Contratos');
  assert.equal(mesa.$('apuracao-autoria').textContent, 'Autor: Ana Lima · autenticado pela conta da Mesa');
});

test('caderno vazio pede a primeira nota', async () => {
  const {mesa} = await abrir({notas: []});
  assert.equal(mesa.$('apuracao-notas-vazio').hidden, false);
  assert.equal(mesa.$('apuracao-notas-vazio').textContent, 'Nenhuma nota ainda. Use Nova nota.');
  assert.equal(mesa.$('apuracao-editor').hidden, true);
});

test('coluna Fontes: marcador, trecho, tipo, rodada e original na página; indisponível explica o motivo', async () => {
  const {mesa, chamadas} = await abrir();
  const cartao = mesa.$('apuracao-fontes').querySelector('.note-source');
  assert.equal(cartao.querySelector('h4').textContent, '[Fonte 1] · Achado da IA');
  assert.equal(cartao.querySelector('blockquote').textContent, 'O contrato vale R$ 10 mil.');
  assert.match(cartao.textContent, /Rodada R002/);
  const [pdf, planilha] = cartao.querySelectorAll('.note-source-doc');
  assert.match(pdf.textContent, /contrato/);
  assert.match(pdf.textContent, /Página PDF 12 · Linhas 3–4/);
  const abrirPdf = pdf.querySelector('button');
  assert.equal(abrirPdf.textContent, 'Ver página 12 no original');
  abrirPdf.click();
  await mesa.esperar(8);
  assert.deepEqual(chamadas.find(c => c.op === 'apuracao-original').dados, {caso: 'alfa', nota_id: 'n1', fonte_id: 'F1', documento_indice: 0});
  assert.equal(mesa.$('original-dialogo').open, true);
  assert.match(mesa.$('original-localizacao').textContent, /Página física 12/);
  const indisponivel = planilha.querySelector('button');
  assert.equal(indisponivel.disabled, true);
  assert.match(planilha.textContent, /Original indisponível \(apuração na lixeira ou arquivo ausente\)/);
  itens(mesa)[1].click();
  await mesa.esperar(10);
  assert.equal(mesa.$('apuracao-fontes').textContent, 'Esta nota ainda não tem fontes. Use Inserir trecho com fonte.');
});

test('Nova nota grava “Nova nota” vazia e abre para escrever', async () => {
  const {mesa, salvamentos} = await abrir();
  mesa.$('apuracao-nova').click();
  await mesa.esperar(12);
  const pedido = salvamentos()[0].dados;
  assert.equal(pedido.titulo, 'Nova nota');
  assert.equal(pedido.texto, '');
  assert.equal('nota_id' in pedido, false);
  assert.match(pedido.requisicao_id, /^[0-9a-f]{32}$/);
  assert.equal(mesa.$('apuracao-nota-titulo').value, 'Nova nota');
  assert.equal(itens(mesa)[0].querySelector('.note-item-title').textContent, 'Nova nota');
});

test('salvamento automático: uma gravação por vez, revisão mais recente e nova requisicao_id', async () => {
  const primeira = deferido();
  let n = 0;
  const f = await abrir({salvar: (dados, banco) => {
    n++;
    const resposta = () => {
      const salva = {...banco.get('n1'), texto: dados.texto, revisao: dados.revisao_nota + 1, atualizado_em_utc: '2026-11-13T14:05:00+00:00'};
      banco.set('n1', salva);
      return {estado: 'salvo', revisao_caderno: 10, nota_id: 'n1', nota: structuredClone(salva), salvo_em_utc: salva.atualizado_em_utc};
    };
    return n === 1 ? primeira.promessa.then(resposta) : resposta();
  }});
  const {mesa} = f;
  await f.escrever('Versão um');
  assert.equal(mesa.$('apuracao-salvamento').textContent, 'Alterações não salvas');
  assert.equal(mesa.$('apuracao-salvamento').getAttribute('aria-live'), 'polite');
  assert.equal(f.salvamentos().length, 0, 'espera a pausa na digitação');
  await f.avancar();
  assert.equal(f.salvamentos().length, 1);
  assert.equal(mesa.$('apuracao-salvamento').textContent, 'Salvando…');
  assert.deepEqual({...f.salvamentos()[0].dados, requisicao_id: 'x'},
    {caso: 'alfa', requisicao_id: 'x', titulo: 'Contratos', texto: 'Versão um', nota_id: 'n1', revisao_nota: 3});
  await f.escrever('Versão dois');
  await f.avancar();
  assert.equal(f.salvamentos().length, 1, 'não dispara outra gravação com uma em andamento');
  primeira.resolve();
  await mesa.esperar(10);
  await f.avancar();
  assert.equal(f.salvamentos().length, 2);
  const segunda = f.salvamentos()[1].dados;
  assert.equal(segunda.texto, 'Versão dois');
  assert.equal(segunda.revisao_nota, 4, 'usa a revisão devolvida pela gravação anterior');
  assert.notEqual(segunda.requisicao_id, f.salvamentos()[0].dados.requisicao_id);
  assert.equal(mesa.$('apuracao-salvamento').textContent, `Nota salva às ${hora('2026-11-13T14:05:00+00:00')}`);
});

test('erro de rede preserva o texto e reenvia a mesma requisicao_id', async () => {
  let n = 0;
  const f = await abrir({salvar: dados => {
    n++;
    if (n === 1) throw new TypeError('Failed to fetch');
    return {estado: 'ja_registrado', revisao_caderno: 10, nota_id: 'n1', nota: {...nota('n1'), texto: dados.texto, revisao: 4},
      salvo_em_utc: '2026-11-13T14:06:00+00:00'};
  }});
  const {mesa} = f;
  await f.escrever('Texto que não pode sumir');
  await f.avancar();
  assert.equal(mesa.$('apuracao-salvamento').textContent, 'Sem conexão. Rascunho guardado nesta aba; tentando de novo…');
  assert.equal(mesa.$('apuracao-texto').value, 'Texto que não pode sumir');
  await f.avancar();
  const [primeiro, segundo] = f.salvamentos().map(c => c.dados);
  assert.deepEqual(segundo, primeiro, 'mesmo corpo, mesma requisicao_id');
  assert.equal(mesa.$('apuracao-salvamento').textContent, `Nota salva às ${hora('2026-11-13T14:06:00+00:00')}`);
});

test('409 para o salvamento automático, não sobrescreve e oferece copiar e depois recarregar', async () => {
  const conflito = {__status: 409, corpo: {estado: 'erro', codigo: 'conflito', erro: 'Conflito: a nota foi alterada em outra aba.',
    atual: {nota_id: 'n1', revisao: 5, atualizado_em_utc: AGORA}}};
  const f = await abrir({salvar: () => conflito});
  const {mesa} = f;
  await f.escrever('Meu texto local');
  await f.avancar();
  assert.equal(mesa.$('apuracao-salvamento').textContent, 'Conflito: a nota foi alterada em outra aba');
  assert.equal(mesa.$('apuracao-conflito').hidden, false);
  await f.escrever('Meu texto local, mais');
  await f.avancar();
  assert.equal(f.salvamentos().length, 1, 'nenhuma nova gravação depois do conflito');
  mesa.$('apuracao-copiar').click();
  await mesa.esperar(4);
  assert.equal(mesa.janela.copiado, 'Contratos\n\nMeu texto local, mais');
  f.banco.set('n1', nota('n1', {texto: 'Texto da outra aba', revisao: 5}));
  mesa.$('apuracao-recarregar').click();
  await mesa.esperar(12);
  assert.equal(mesa.$('apuracao-texto').value, 'Texto da outra aba');
  assert.equal(mesa.$('apuracao-conflito').hidden, true);
  await f.escrever('Depois de recarregar');
  await f.avancar();
  assert.equal(f.salvamentos().at(-1).dados.revisao_nota, 5);
});

test('clicar em [Fonte 1] no texto rola e destaca a fonte', async () => {
  const {mesa} = await abrir();
  const campo = mesa.$('apuracao-texto');
  campo.selectionStart = campo.value.indexOf('[Fonte 1]') + 3;
  campo.dispatchEvent(new Evento('click', {bubbles: true}));
  assert.ok(mesa.$('apuracao-fonte-1').classList.contains('is-highlighted'));
  const chip = mesa.$('apuracao-previa').querySelector('.source-citation');
  assert.equal(chip.textContent, '[Fonte 1]');
});

test('Inserir em nota usa a nota aberta e sua revisão, depois recarrega editor e fontes', async () => {
  const f = await abrir({inserir: (dados, banco) => {
    const salva = {...banco.get('n1'), texto: banco.get('n1').texto + '\n\n> Novo trecho.\n\n[Fonte 2]', revisao: 4};
    banco.set('n1', salva);
    return {estado: 'salvo', revisao_caderno: 10, nota_id: 'n1', nota: structuredClone(salva), salvo_em_utc: AGORA};
  }});
  const {mesa} = f;
  const botao = mesa.janela.botaoAdicionarApuracao({caso: 'alfa', rodada: 'R002', geracao: 'v1', tipo: 'pesquisa', referencia: 'P1'}, null, 'Novo trecho.');
  botao.click();
  await mesa.esperar(10);
  assert.equal(mesa.$('apuracao-destino').value, 'n1', 'a nota aberta é o destino sugerido');
  mesa.$('apuracao-adicionar-form').requestSubmit();
  await mesa.esperar(16);
  const pedido = f.chamadas.find(c => c.op === 'apuracao-nota-inserir').dados;
  assert.equal(pedido.nota_id, 'n1');
  assert.equal(pedido.revisao_nota, 3);
  assert.deepEqual(pedido.origem, {caso: 'alfa', rodada: 'R002', geracao: 'v1', tipo: 'pesquisa', referencia: 'P1', texto: 'Novo trecho.'});
  assert.equal(mesa.$('apuracao-adicionar-dialogo').open, false);
  assert.match(mesa.$('apuracao-texto').value, /\[Fonte 2\]$/);
});

test('autoria: conta da Mesa ou declarada pelo usuário, nas duas línguas', async () => {
  const {mesa} = await abrir();
  const autoria = mesa.janela.Leitura.autoria;
  assert.equal(autoria('Ana', 'humana_autenticada_pela_conta_da_mesa'), 'Autor: Ana · autenticado pela conta da Mesa');
  assert.equal(autoria('Ana', 'conta_autenticada_da_mesa'), 'Autor: Ana · autenticado pela conta da Mesa');
  assert.equal(autoria('Ana', 'humana_declarada_na_interface'), 'Autor: Ana · declarado pelo usuário');
  assert.equal(autoria('Ana', undefined), 'Autor: Ana · declarado pelo usuário');
  mesa.janela.I18N.definir('en');
  assert.equal(autoria('Ana', 'conta_autenticada_da_mesa'), 'Author: Ana · authenticated by the Mesa account');
  assert.equal(autoria('Ana', 'declaracao_do_usuario_na_interface'), 'Author: Ana · declared by the user');
});

test('modo piloto não pede autor nos formulários; local continua pedindo', async () => {
  const piloto = await abrir({modo: 'piloto'});
  for (const id of ['caderno-autor', 'diligencias-autor', 'diligencias-resposta-autor']) {
    assert.equal(piloto.mesa.$(id).required, false, id);
    assert.equal(piloto.mesa.$(id).closest('label').hidden, true, id);
  }
  const local = await abrir();
  assert.equal(local.mesa.$('caderno-autor').required, true);
  assert.equal(local.mesa.$('caderno-autor').closest('label').hidden, false);
});

test('em inglês o caderno mostra rótulos traduzidos', async () => {
  const {mesa} = await abrir({idioma: 'en'});
  mesa.janela.I18N.aplicar(mesa.doc.body);
  assert.equal(mesa.$('apuracao-nova').textContent, 'New note');
  assert.equal(mesa.$('apuracao-inserir').textContent, 'Insert sourced excerpt');
  assert.match(itens(mesa)[0].querySelector('.note-item-meta').textContent, /^Updated at .+ · 1 source$/);
  assert.equal(mesa.$('apuracao-fontes').querySelector('h4').textContent, '[Fonte 1] · AI finding');
  assert.match(mesa.$('apuracao-fontes').querySelector('.note-source-doc').textContent, /PDF page 12 · Lines 3–4/);
  assert.equal(mesa.$('apuracao-fontes-titulo').textContent, 'Note sources');
});
