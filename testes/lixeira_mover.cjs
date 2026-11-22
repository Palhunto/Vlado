'use strict';
// "Mover para a lixeira" em Apurações e lixeira, no diálogo da Mesa (dialogo.js, variante destrutiva, modo executar): Esc, véu e Cancelar não movem;
// a recusa do servidor fica no diálogo; o sucesso tira o item da lista. Segue a prancha dialogo-destrutivo (docs/design/componentes.md#dialogo).
const test = require('node:test');
const assert = require('node:assert/strict');
const {criarMesa, Evento} = require('./dom_minimo.cjs');

const ALFA = {id: 'alfa', titulo: 'Pauta Alfa', rodadas: [{id: 'R001', geracoes: []}]};
const CONVERSA = {id: 'c'.repeat(32), titulo: 'Conversa velha', estado: 'concluido', rodadas: ['R001']};

function abrir({excluir = () => ({estado: 'excluido', item: {tipo: 'conversa', titulo: 'Conversa velha'}})} = {}) {
  const pendentes = [];
  const estado = {movida: false};
  const segurar = resposta => new Promise((resolve, reject) => pendentes.push({resolve: () => {
    try { resolve(resposta()); } catch (erro) { reject(erro); }
  }}));
  const mesa = criarMesa({catalogo: [ALFA], url: 'http://127.0.0.1:8765/?area=gerenciar&caso=alfa', api: operacao => {
    if (operacao === 'gerenciar-listar') return {casos: [ALFA], conversas: estado.movida ? [] : [structuredClone(CONVERSA)], lixeira: []};
    if (operacao === 'excluir') return segurar(() => { const resposta = excluir(); estado.movida = true; return resposta; });
    if (operacao === 'inventario') return {caso_id: 'alfa', corpus_id: 'c1', documentos: [], total_documentos: 0};
    return {};
  }});
  return {mesa, liberar: async () => { pendentes.shift().resolve(); await mesa.esperar(8); }};
}
const dialogo = mesa => mesa.doc.querySelector('dialog.dialogo');
const botoes = mesa => [...dialogo(mesa).querySelectorAll('.dialogo-acoes button')];
const erro = mesa => dialogo(mesa).querySelector('.dialogo-erro');
const botaoExcluir = mesa => [...mesa.$('gerenciar-conversas').querySelectorAll('button')].find(b => b.textContent === 'Excluir');
const tecla = (alvo, key) => { const evento = new Evento('keydown', {key, bubbles: true, cancelable: true}); alvo.dispatchEvent(evento); return evento; };
async function abrirDialogo(opcoes) {
  const f = abrir(opcoes);
  await f.mesa.esperar(12);
  botaoExcluir(f.mesa).click();
  await f.mesa.esperar(4);
  return f;
}

test('o diálogo nomeia o item, diz o efeito e o que fica, e abre com o foco em Cancelar (variante destrutiva)', async () => {
  const {mesa} = await abrirDialogo();
  assert.deepEqual(mesa.erros, []);
  const dlg = dialogo(mesa);
  assert.equal(dlg.getAttribute('role'), 'alertdialog');
  assert.equal(dlg.querySelector('.dialogo-rubrica').textContent, 'Mover para a lixeira');
  assert.equal(dlg.querySelector('.dialogo-titulo').textContent, 'Mover “Conversa velha” para a lixeira?');
  assert.equal(dlg.querySelector('.dialogo-titulo [translate="no"]').textContent, '“Conversa velha”', 'o nome é dado, não se traduz');
  assert.match(dlg.querySelector('.dialogo-texto').textContent, /A conversa, suas perguntas complementares e rodadas sairão das listas\./);
  assert.match(dlg.textContent, /Você poderá restaurar em Apurações e lixeira\. Documentos e registros serão preservados\./);
  const [cancelar, mover] = botoes(mesa);
  assert.equal(mover.textContent, 'Mover para a lixeira');
  assert.ok(mover.classList.contains('danger'));
  assert.ok(mesa.doc.activeElement === cancelar, 'foco inicial em Cancelar');
  assert.equal(mesa.chamadas.some(c => c.operacao === 'excluir'), false);
});

test('Esc, o clique no véu e Cancelar não movem nada, e o foco volta ao botão da lista', async () => {
  const {mesa} = await abrirDialogo();
  dialogo(mesa).click();
  assert.equal(dialogo(mesa).open, true, 'o véu não fecha');
  assert.equal(tecla(dialogo(mesa), 'Escape').defaultPrevented, true);
  assert.equal(dialogo(mesa), null, 'Esc fecha como Cancelar');
  await mesa.esperar(2);
  botaoExcluir(mesa).click();
  await mesa.esperar(4);
  botoes(mesa)[0].click();
  assert.equal(dialogo(mesa), null);
  assert.equal(mesa.chamadas.some(c => c.operacao === 'excluir'), false, 'nada foi movido');
  assert.ok(mesa.doc.activeElement === botaoExcluir(mesa), 'o foco volta ao botão que abriu o diálogo');
});

test('mover mostra “Movendo…”, trava Cancelar e Esc e, no sucesso, fecha, avisa e tira o item da lista', async () => {
  const {mesa, liberar} = await abrirDialogo();
  const [cancelar, mover] = botoes(mesa);
  mover.click();
  await mesa.esperar(4);
  assert.equal(mover.textContent, 'Movendo…');
  assert.equal(mover.getAttribute('aria-disabled'), 'true');
  assert.equal(cancelar.disabled, true);
  tecla(dialogo(mesa), 'Escape');
  assert.equal(dialogo(mesa).open, true, 'Esc não fecha durante o pedido');
  assert.deepEqual(mesa.chamadas.find(c => c.operacao === 'excluir').dados, {tipo: 'conversa', caso: 'alfa', conversa: CONVERSA.id});
  const listagens = mesa.chamadas.filter(c => c.operacao === 'gerenciar-listar').length;
  await liberar();
  assert.equal(dialogo(mesa), null);
  assert.match(mesa.$('gerenciar-status').textContent, /Conversa movida para a lixeira: Conversa velha\./);
  assert.ok(mesa.chamadas.filter(c => c.operacao === 'gerenciar-listar').length > listagens, 'lista recarregada');
  assert.equal(botaoExcluir(mesa), undefined, 'a conversa saiu da lista');
});

test('a recusa do servidor fica no diálogo, com o texto inteiro, libera os botões e deixa tentar de novo', async () => {
  const recusa = 'Há uma execução em andamento nesta conversa. Cancele-a e aguarde o encerramento antes de excluir.';
  let tentativas = 0;
  const {mesa, liberar} = await abrirDialogo({excluir: () => { tentativas++; if (tentativas === 1) throw new Error(recusa); return {estado: 'excluido', item: {tipo: 'conversa', titulo: 'Conversa velha'}}; }});
  botoes(mesa)[1].click();
  await mesa.esperar(4);
  await liberar();
  assert.ok(dialogo(mesa), 'o diálogo continua aberto');
  assert.equal(erro(mesa).textContent, recusa);
  assert.equal(erro(mesa).getAttribute('role'), 'alert');
  assert.equal(botoes(mesa)[0].disabled, false);
  assert.equal(botoes(mesa)[1].disabled, false);
  assert.equal(botoes(mesa)[1].textContent, 'Mover para a lixeira');
  botoes(mesa)[1].click();
  await mesa.esperar(4);
  await liberar();
  assert.equal(dialogo(mesa), null, 'na segunda tentativa deu certo');
  assert.equal(tentativas, 2);
});

test('excluir a apuração inteira também passa pelo diálogo, com o efeito da apuração', async () => {
  const {mesa} = abrir();
  await mesa.esperar(12);
  mesa.$('gerenciar-caso').value = 'alfa';
  mesa.$('gerenciar-caso').dispatchEvent(new Evento('change', {bubbles: true}));
  await mesa.esperar(8);
  mesa.$('gerenciar-excluir-caso').click();
  await mesa.esperar(4);
  assert.equal(dialogo(mesa).querySelector('.dialogo-titulo').textContent, 'Mover “Pauta Alfa” para a lixeira?');
  assert.match(dialogo(mesa).querySelector('.dialogo-texto').textContent, /A apuração, suas conversas e rodadas sairão das listas\./);
  botoes(mesa)[0].click();
  assert.equal(mesa.chamadas.some(c => c.operacao === 'excluir'), false);
});

test('depois de uma recusa, ao fechar o diálogo a lista é relida (ressalva da Coruja)', async () => {
  const {mesa, liberar} = await abrirDialogo({excluir: () => { throw new Error('Recusado pelo servidor.'); }});
  botoes(mesa)[1].click();
  await mesa.esperar(4);
  await liberar();
  assert.equal(erro(mesa).textContent, 'Recusado pelo servidor.');
  const listagens = mesa.chamadas.filter(c => c.operacao === 'gerenciar-listar').length;
  botoes(mesa)[0].click();
  await mesa.esperar(8);
  assert.ok(mesa.chamadas.filter(c => c.operacao === 'gerenciar-listar').length > listagens, 'a lista é relida depois da recusa');
});

test('cancelar sem ter pedido nada não relê a lista', async () => {
  const {mesa} = await abrirDialogo();
  const listagens = mesa.chamadas.filter(c => c.operacao === 'gerenciar-listar').length;
  botoes(mesa)[0].click();
  await mesa.esperar(8);
  assert.equal(mesa.chamadas.filter(c => c.operacao === 'gerenciar-listar').length, listagens);
});
