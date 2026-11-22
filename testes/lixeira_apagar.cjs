'use strict';
// "Apagar definitivamente…" in Apurações e lixeira: scope first, typed name, token, no surprises.
const test = require('node:test');
const assert = require('node:assert/strict');
const {criarMesa, Evento} = require('./dom_minimo.cjs');

const ALFA = {id: 'alfa', titulo: 'Pauta Alfa', rodadas: [{id: 'R001', geracoes: []}]};
const ITEM = {id: 'a'.repeat(32), tipo: 'conversa', caso: 'alfa', titulo: 'Conversa velha', conversa: 'c'.repeat(32),
  rodadas: ['R001', 'R002'], excluido_em_utc: '2026-11-10T12:00:00+00:00'};
const ALCANCE = {item: {id: ITEM.id, tipo: 'conversa', caso: 'alfa', titulo: 'Conversa velha', conversa: ITEM.conversa, rodada: null},
  nome_para_confirmar: 'Conversa velha',
  // Server order: dict(sorted(...)).
  categorias: {conversas: {arquivos: 2, bytes: 524288}, misterio: {arquivos: 1, bytes: 10}, rodadas: {arquivos: 1, bytes: 1048576}},
  totais: {arquivos: 4, pastas: 3, bytes: 1572874}, raizes: [], conversas: [ITEM.conversa], rodadas: ['R002'],
  rodadas_preservadas: ['R001'], registros: {catalogo: 0, lixeira: 1},
  aviso_backup: 'Cópias que já estejam em backups feitos com scripts/backup.py não são apagadas por esta ação. Elas permanecem até expirar conforme a retenção de backups definida pelo operador.',
  confirmacao: 'f'.repeat(64)};
const MUDOU = 'O conteúdo do item mudou desde a conferência. Revise o alcance e confirme novamente.';

// Every lixeira call can be held open to observe the in-flight state.
function abrir({idioma = 'pt', apagar = () => ({estado: 'apagado', item: ALCANCE.item, categorias: ALCANCE.categorias, totais: ALCANCE.totais}),
  alcance = () => structuredClone(ALCANCE)} = {}) {
  const pendentes = [];
  const segurar = resposta => new Promise((resolve, reject) => pendentes.push({resolve: () => {
    try { resolve(resposta()); } catch (erro) { reject(erro); }
  }}));
  const mesa = criarMesa({idioma, armazenamento: idioma === 'en' ? {'vlado-idioma': 'en'} : {}, catalogo: [ALFA],
    url: 'http://127.0.0.1:8765/?area=gerenciar&caso=alfa', api: operacao => {
      if (operacao === 'gerenciar-listar') return {casos: [ALFA], conversas: [], lixeira: [structuredClone(ITEM)]};
      if (operacao === 'lixeira-alcance') return segurar(alcance);
      if (operacao === 'lixeira-apagar') return segurar(apagar);
      if (operacao === 'inventario') return {caso_id: 'alfa', corpus_id: 'c1', documentos: [], total_documentos: 0};
      return {};
    }});
  return {mesa, pendentes, liberar: async () => { pendentes.shift().resolve(); await mesa.esperar(8); }};
}
const botaoApagar = mesa => [...mesa.$('gerenciar-lixeira').querySelectorAll('button')].find(b => /^Apagar definitivamente|^Delete permanently/.test(b.textContent));
async function abrirDialogo(opcoes) {
  const f = abrir(opcoes);
  await f.mesa.esperar(12);
  botaoApagar(f.mesa).click();
  await f.mesa.esperar(4);
  return f;
}
function digitar(mesa, texto) {
  mesa.$('apagar-nome').value = texto;
  mesa.$('apagar-nome').dispatchEvent(new Evento('input', {bubbles: true}));
}

test('item da lixeira oferece “Apagar definitivamente…” ao lado de Restaurar', async () => {
  const {mesa} = abrir();
  await mesa.esperar(12);
  assert.deepEqual(mesa.erros, []);
  const textos = [...mesa.$('gerenciar-lixeira').querySelectorAll('button')].map(b => b.textContent);
  assert.deepEqual(textos, ['Restaurar', 'Apagar definitivamente…']);
  assert.ok(botaoApagar(mesa).classList.contains('danger'));
});

test('diálogo de alerta abre com foco em Cancelar e calcula o alcance antes de mostrar o campo', async () => {
  const {mesa, liberar} = await abrirDialogo();
  const dialogo = mesa.$('apagar-dialogo');
  assert.equal(dialogo.open, true);
  assert.equal(dialogo.getAttribute('role'), 'alertdialog');
  assert.equal(mesa.doc.activeElement, mesa.$('apagar-cancelar'));
  assert.equal(mesa.$('apagar-status').textContent, 'Calculando o que será apagado…');
  assert.equal(mesa.$('apagar-status').getAttribute('aria-live'), 'polite');
  assert.equal(mesa.$('apagar-item').textContent, 'Conversa · Conversa velha');
  assert.equal(mesa.$('apagar-alcance').hidden, true);
  assert.equal(mesa.$('apagar-confirmar').disabled, true);
  assert.deepEqual(mesa.chamadas.find(c => c.operacao === 'lixeira-alcance').dados, {item: ITEM.id});
  await liberar();
  assert.equal(mesa.$('apagar-alcance').hidden, false);
  const linhas = [...mesa.$('apagar-categorias').querySelectorAll('tr')].map(tr => [...tr.querySelectorAll('th,td')].map(c => c.textContent));
  assert.deepEqual(linhas, [['Conversas', '2', '512 KB'], ['misterio', '1', '10 B'], ['Rodadas de análise', '1', '1,0 MB']]);
  assert.equal(mesa.$('apagar-total').textContent, '4 arquivos, 1,5 MB');
  assert.match(mesa.$('apagar-preservadas').textContent, /^Estas rodadas continuam porque são usadas por outras conversas: R001/);
  assert.equal(mesa.$('apagar-preservadas').hidden, false);
  assert.equal(mesa.$('apagar-backup').textContent, ALCANCE.aviso_backup);
  assert.equal(mesa.$('apagar-nome-rotulo').textContent, 'Digite «Conversa velha» para confirmar');
});

test('botão só habilita quando o nome digitado coincide, ignorando espaços nas pontas e caixa', async () => {
  const {mesa, liberar} = await abrirDialogo();
  await liberar();
  const confirmar = mesa.$('apagar-confirmar');
  digitar(mesa, 'Conversa');
  assert.equal(confirmar.disabled, true);
  digitar(mesa, 'Conversa velhas');
  assert.equal(confirmar.disabled, true);
  digitar(mesa, '  CONVERSA VELHA  ');
  assert.equal(confirmar.disabled, false);
});

test('Esc e Cancelar fecham sem apagar', async () => {
  const {mesa, liberar} = await abrirDialogo();
  await liberar();
  digitar(mesa, 'conversa velha');
  const esc = new Evento('cancel', {cancelable: true});
  mesa.$('apagar-dialogo').dispatchEvent(esc);
  if (!esc.defaultPrevented) mesa.$('apagar-dialogo').close();
  assert.equal(mesa.$('apagar-dialogo').open, false);
  botaoApagar(mesa).click();
  await mesa.esperar(4);
  await liberar();
  mesa.$('apagar-cancelar').click();
  assert.equal(mesa.$('apagar-dialogo').open, false);
  assert.equal(mesa.chamadas.some(c => c.operacao === 'lixeira-apagar'), false);
});

test('envio mostra “Apagando…”, bloqueia os botões e, no sucesso, fecha, avisa e recarrega a lista', async () => {
  const {mesa, liberar} = await abrirDialogo();
  await liberar();
  digitar(mesa, 'Conversa velha ');
  mesa.$('apagar-confirmar').click();
  await mesa.esperar(4);
  assert.equal(mesa.$('apagar-confirmar').textContent, 'Apagando…');
  assert.equal(mesa.$('apagar-confirmar').disabled, true);
  assert.equal(mesa.$('apagar-cancelar').disabled, true);
  const esc = new Evento('cancel', {cancelable: true});
  mesa.$('apagar-dialogo').dispatchEvent(esc);
  assert.equal(esc.defaultPrevented, true, 'Esc não fecha durante o apagamento');
  assert.deepEqual(mesa.chamadas.find(c => c.operacao === 'lixeira-apagar').dados,
    {item: ITEM.id, nome: 'Conversa velha ', confirmacao: ALCANCE.confirmacao});
  const listagens = mesa.chamadas.filter(c => c.operacao === 'gerenciar-listar').length;
  await liberar();
  assert.equal(mesa.$('apagar-dialogo').open, false);
  assert.equal(mesa.$('gerenciar-status').textContent, 'Apagado definitivamente: 4 arquivos (1,5 MB).');
  assert.ok(mesa.chamadas.filter(c => c.operacao === 'gerenciar-listar').length > listagens, 'lista recarregada');
});

test('conteúdo alterado desde a conferência recarrega o alcance e pede nova confirmação', async () => {
  // Recognised by the server's stable code, whatever the message language.
  const alterado = () => { throw Object.assign(new Error('Contents changed (server text)'),
    {result: {estado: 'erro', codigo: 'alcance_alterado', erro: 'Texto diferente do servidor.'}}); };
  const {mesa, liberar} = await abrirDialogo({apagar: alterado});
  await liberar();
  digitar(mesa, 'conversa velha');
  mesa.$('apagar-confirmar').click();
  await mesa.esperar(4);
  await liberar();
  assert.equal(mesa.$('apagar-dialogo').open, true);
  assert.equal(mesa.chamadas.filter(c => c.operacao === 'lixeira-alcance').length, 2, 'alcance pedido de novo');
  assert.match(mesa.$('apagar-erro').textContent, /conteúdo mudou desde a conferência/i);
  assert.equal(mesa.$('apagar-erro').hidden, false);
  await liberar();
  assert.equal(mesa.$('apagar-nome').value, '');
  assert.equal(mesa.$('apagar-confirmar').disabled, true);
  assert.equal(mesa.$('apagar-confirmar').textContent, 'Apagar definitivamente');
  assert.equal(mesa.$('apagar-cancelar').disabled, false);
});

test('outra recusa fica no diálogo, com a mensagem, e libera os botões', async () => {
  const recusa = 'Há uma execução em andamento. Cancele-a e aguarde o encerramento antes de apagar definitivamente.';
  const {mesa, liberar} = await abrirDialogo({apagar: () => { throw new Error(recusa); }});
  await liberar();
  digitar(mesa, 'conversa velha');
  mesa.$('apagar-confirmar').click();
  await mesa.esperar(4);
  await liberar();
  assert.equal(mesa.$('apagar-dialogo').open, true);
  assert.equal(mesa.$('apagar-erro').textContent, recusa);
  assert.equal(mesa.$('apagar-erro').getAttribute('role'), 'alert');
  assert.equal(mesa.$('apagar-confirmar').disabled, false);
  assert.equal(mesa.$('apagar-cancelar').disabled, false);
});

test('em inglês o diálogo, as categorias e o total vêm traduzidos', async () => {
  const {mesa, liberar} = await abrirDialogo({idioma: 'en'});
  assert.equal(mesa.$('apagar-status').textContent, 'Working out what will be deleted…');
  await liberar();
  mesa.janela.I18N.aplicar(mesa.doc.body);
  assert.equal(mesa.$('apagar-titulo').textContent, 'Delete permanently');
  assert.equal(mesa.$('apagar-item').textContent, 'Conversation · Conversa velha', 'tipo traduzido, título como dado');
  assert.equal(mesa.$('apagar-categorias').querySelector('tr').querySelector('th').textContent, 'Conversations');
  assert.equal(mesa.$('apagar-total').textContent, '4 files, 1.5 MB');
  assert.equal(mesa.$('apagar-nome-rotulo').textContent, 'Type “Conversa velha” to confirm');
  assert.equal(mesa.$('apagar-cancelar').textContent, 'Cancel');
  assert.match(mesa.$('apagar-backup').textContent, /^Copies already in backups/);
});
