'use strict';
// "Apagar definitivamente…" em Apurações e lixeira, no diálogo da Mesa (dialogo.js, modo executar): alcance primeiro, nome digitado, token,
// nada de surpresas. A tabela do que sai e a linha do item seguem a prancha dialogo-campo (docs/design/componentes.md#dialogo).
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
const SUCESSO = {estado: 'apagado', item: ALCANCE.item, categorias: ALCANCE.categorias, totais: ALCANCE.totais};
const QUARENTENA = 'Parte do item não pôde ser removida agora e volta à lixeira na próxima partida da Mesa. Até lá, não restaure nem apague este item de novo.';

// Every lixeira call can be held open to observe the in-flight state. The trash list follows what the server "deleted".
function abrir({idioma = 'pt', apagar = () => SUCESSO, alcance = () => structuredClone(ALCANCE)} = {}) {
  const pendentes = [];
  const estado = {apagado: false};
  const segurar = resposta => new Promise((resolve, reject) => pendentes.push({resolve: () => {
    try { resolve(resposta()); } catch (erro) { reject(erro); }
  }}));
  const mesa = criarMesa({idioma, armazenamento: idioma === 'en' ? {'vlado-idioma': 'en'} : {}, catalogo: [ALFA],
    url: 'http://127.0.0.1:8765/?area=gerenciar&caso=alfa', api: operacao => {
      if (operacao === 'gerenciar-listar') return {casos: [ALFA], conversas: [], lixeira: estado.apagado ? [] : [structuredClone(ITEM)]};
      if (operacao === 'lixeira-alcance') return segurar(alcance);
      if (operacao === 'lixeira-apagar') return segurar(() => { const resposta = apagar(); estado.apagado = true; return resposta; });
      if (operacao === 'inventario') return {caso_id: 'alfa', corpus_id: 'c1', documentos: [], total_documentos: 0};
      return {};
    }});
  return {mesa, pendentes, liberar: async () => { pendentes.shift().resolve(); await mesa.esperar(8); }};
}
const botaoApagar = mesa => [...mesa.$('gerenciar-lixeira').querySelectorAll('button')].find(b => /^Apagar definitivamente|^Delete permanently/.test(b.textContent));
const dialogo = mesa => mesa.doc.querySelector('dialog.dialogo');
const campo = mesa => dialogo(mesa).querySelector('input');
const botoes = mesa => [...dialogo(mesa).querySelectorAll('.dialogo-acoes button')];
const erro = mesa => dialogo(mesa).querySelector('.dialogo-erro');
const estadoDoAlcance = mesa => dialogo(mesa).querySelector('.dialogo-nota[role="status"]');
async function abrirDialogo(opcoes) {
  const f = abrir(opcoes);
  await f.mesa.esperar(12);
  botaoApagar(f.mesa).click();
  await f.mesa.esperar(4);
  return f;
}
function digitar(mesa, texto) {
  campo(mesa).value = texto;
  campo(mesa).dispatchEvent(new Evento('input', {bubbles: true}));
}
const tecla = (mesa, alvo, key) => { const evento = new Evento('keydown', {key, bubbles: true, cancelable: true}); alvo.dispatchEvent(evento); return evento; };

test('item da lixeira oferece “Apagar definitivamente…” ao lado de Restaurar', async () => {
  const {mesa} = abrir();
  await mesa.esperar(12);
  assert.deepEqual(mesa.erros, []);
  const textos = [...mesa.$('gerenciar-lixeira').querySelectorAll('button')].map(b => b.textContent);
  assert.deepEqual(textos, ['Restaurar', 'Apagar definitivamente…']);
  assert.ok(botaoApagar(mesa).classList.contains('danger'));
});

test('o diálogo abre com a linha do item, calcula o alcance e só então libera o campo, que recebe o foco', async () => {
  const {mesa, liberar} = await abrirDialogo();
  const dlg = dialogo(mesa);
  assert.equal(dlg.open, true);
  assert.equal(dlg.getAttribute('role'), 'alertdialog');
  assert.equal(dlg.querySelector('.dialogo-titulo').textContent, 'Apagar definitivamente');
  assert.equal(dlg.querySelector('.dialogo-linha').textContent, 'Conversa · Conversa velha', 'a linha do item: tipo da interface, título como dado');
  assert.equal(dlg.querySelector('.dialogo-linha span').getAttribute('translate'), 'no');
  assert.match(dlg.textContent, /Os arquivos listados saem do projeto\. A Mesa não consegue recuperá-los depois\./);
  assert.equal(estadoDoAlcance(mesa).textContent, 'Calculando o que será apagado…');
  assert.equal(estadoDoAlcance(mesa).getAttribute('aria-live'), 'polite');
  assert.equal(dlg.querySelector('table'), null, 'sem a tabela antes do alcance');
  assert.equal(campo(mesa).disabled, true);
  assert.equal(botoes(mesa)[1].disabled, true);
  assert.ok(mesa.doc.activeElement === botoes(mesa)[0], 'enquanto o alcance não chega, o foco fica em Cancelar');
  assert.deepEqual(mesa.chamadas.find(c => c.operacao === 'lixeira-alcance').dados, {item: ITEM.id});
  await liberar();
  const linhas = [...dlg.querySelectorAll('tbody tr')].map(tr => [...tr.querySelectorAll('th,td')].map(c => c.textContent));
  assert.deepEqual(linhas, [['Conversas', '2', '512\u00a0KB'], ['misterio', '1', '10\u00a0B'], ['Rodadas de análise', '1', '1,0\u00a0MB']]);
  assert.deepEqual([...dlg.querySelectorAll('thead th')].map(c => c.textContent), ['Categoria', 'Arquivos', 'Tamanho']);
  assert.equal(dlg.querySelector('tfoot').textContent, '4\u00a0arquivos, 1,5\u00a0MB'.replace(/^/, 'Total'));
  assert.match(dlg.textContent, /Estas rodadas continuam porque são usadas por outras conversas: R001/);
  assert.match(dlg.textContent, new RegExp(ALCANCE.aviso_backup.slice(0, 40)));
  assert.match(dlg.querySelector('label').textContent, /Digite «Conversa velha» para confirmar/);
  assert.equal(estadoDoAlcance(mesa).hidden, true);
  assert.equal(campo(mesa).disabled, false);
  assert.ok(mesa.doc.activeElement === campo(mesa), 'com o nome conhecido, o foco passa ao campo (o foco inicial da variante com campo)');
});

test('a ação só habilita quando o nome digitado coincide, ignorando espaços nas pontas e caixa; Enter respeita isso', async () => {
  const {mesa, liberar} = await abrirDialogo();
  await liberar();
  const [, confirmar] = botoes(mesa);
  digitar(mesa, 'Conversa');
  assert.equal(confirmar.disabled, true);
  digitar(mesa, 'Conversa velhas');
  assert.equal(confirmar.disabled, true);
  tecla(mesa, campo(mesa), 'Enter');
  await mesa.esperar(4);
  assert.equal(mesa.chamadas.some(c => c.operacao === 'lixeira-apagar'), false, 'nome errado não chama o servidor, nem com Enter');
  digitar(mesa, '  CONVERSA VELHA  ');
  assert.equal(confirmar.disabled, false);
});

test('Esc, o clique no véu e Cancelar não apagam; Cancelar devolve o foco ao botão da lista', async () => {
  const {mesa, liberar} = await abrirDialogo();
  await liberar();
  digitar(mesa, 'conversa velha');
  dialogo(mesa).click();   // o véu é a própria caixa de diálogo: clicar nele não fecha
  assert.equal(dialogo(mesa).open, true, 'o véu não fecha');
  const esc = tecla(mesa, dialogo(mesa), 'Escape');
  assert.equal(esc.defaultPrevented, true);
  assert.equal(dialogo(mesa), null, 'Esc fecha como Cancelar');
  assert.equal(mesa.chamadas.some(c => c.operacao === 'lixeira-apagar'), false);
  await mesa.esperar(2);
  botaoApagar(mesa).click();
  await mesa.esperar(4);
  await liberar();
  digitar(mesa, 'conversa velha');
  botoes(mesa)[0].click();
  assert.equal(dialogo(mesa), null);
  assert.equal(mesa.chamadas.some(c => c.operacao === 'lixeira-apagar'), false, 'nada foi apagado');
  assert.ok(mesa.doc.activeElement === botaoApagar(mesa), 'o foco volta ao botão que abriu o diálogo');
});

test('o envio mostra “Apagando…”, trava Cancelar e Esc e, no sucesso, fecha, avisa e tira o item da lista', async () => {
  const {mesa, liberar} = await abrirDialogo({apagar: () => ({...SUCESSO, aviso_backup: 'As cópias em backups não são apagadas.'})});
  await liberar();
  digitar(mesa, 'Conversa velha ');
  const [cancelar, confirmar] = botoes(mesa);
  confirmar.click();
  await mesa.esperar(4);
  assert.equal(confirmar.textContent, 'Apagando…');
  assert.equal(confirmar.getAttribute('aria-disabled'), 'true');
  assert.equal(cancelar.disabled, true, 'a espera é curta e não se cancela');
  assert.equal(dialogo(mesa).getAttribute('aria-busy'), 'true');
  tecla(mesa, dialogo(mesa), 'Escape');
  assert.equal(dialogo(mesa).open, true, 'Esc não fecha durante o apagamento');
  assert.deepEqual(mesa.chamadas.find(c => c.operacao === 'lixeira-apagar').dados, {item: ITEM.id, nome: 'Conversa velha ', confirmacao: ALCANCE.confirmacao});
  const listagens = mesa.chamadas.filter(c => c.operacao === 'gerenciar-listar').length;
  await liberar();
  assert.equal(dialogo(mesa), null);
  assert.equal(mesa.$('gerenciar-status').textContent, 'Apagado definitivamente: 4\u00a0arquivos (1,5\u00a0MB). As cópias em backups não são apagadas.', 'o aviso de backup da resposta aparece');
  assert.ok(mesa.chamadas.filter(c => c.operacao === 'gerenciar-listar').length > listagens, 'lista recarregada');
  assert.equal(botaoApagar(mesa), undefined, 'o item saiu da lixeira');
  assert.equal(mesa.$('gerenciar-lixeira').querySelectorAll('li.manage-empty').length, 1);
});

test('conteúdo alterado desde a conferência recarrega o alcance, limpa o campo e pede nova confirmação', async () => {
  // Recognised by the server's stable code, whatever the message language.
  const alterado = () => { throw Object.assign(new Error('Contents changed (server text)'),
    {result: {estado: 'erro', codigo: 'alcance_alterado', erro: 'Texto diferente do servidor.'}}); };
  const {mesa, liberar} = await abrirDialogo({apagar: alterado});
  await liberar();
  digitar(mesa, 'conversa velha');
  botoes(mesa)[1].click();
  await mesa.esperar(4);
  await liberar();      // a resposta de lixeira-apagar (recusa)
  assert.equal(mesa.chamadas.filter(c => c.operacao === 'lixeira-alcance').length, 2, 'alcance pedido de novo');
  await liberar();      // o novo alcance
  assert.ok(dialogo(mesa), 'o diálogo continua aberto');
  assert.match(erro(mesa).textContent, /conteúdo mudou desde a conferência/i);
  assert.equal(erro(mesa).hidden, false);
  assert.equal(campo(mesa).value, '');
  assert.equal(botoes(mesa)[1].disabled, true);
  assert.equal(botoes(mesa)[1].textContent, 'Apagar definitivamente');
  assert.equal(botoes(mesa)[0].disabled, false);
  assert.ok(mesa.doc.activeElement === campo(mesa), 'o foco fica no campo, para digitar o nome de novo');
});

test('outra recusa fica no diálogo, com o texto inteiro do servidor, e libera os botões; o texto da quarentena não é trocado', async () => {
  for (const recusa of ['Há uma execução em andamento. Cancele-a e aguarde o encerramento antes de apagar definitivamente.', QUARENTENA]) {
    const {mesa, liberar} = await abrirDialogo({apagar: () => { throw new Error(recusa); }});
    await liberar();
    digitar(mesa, 'conversa velha');
    botoes(mesa)[1].click();
    await mesa.esperar(4);
    await liberar();
    assert.ok(dialogo(mesa), 'o diálogo fica aberto');
    assert.equal(erro(mesa).textContent, recusa, 'a mensagem inteira, sem trocar o texto');
    assert.equal(erro(mesa).getAttribute('role'), 'alert');
    assert.equal(botoes(mesa)[1].disabled, false);
    assert.equal(botoes(mesa)[0].disabled, false);
    // A recusa pode ter mudado a lixeira (parte do item voltou): fechar recarrega a lista.
    const listagens = mesa.chamadas.filter(c => c.operacao === 'gerenciar-listar').length;
    botoes(mesa)[0].click();
    await mesa.esperar(8);
    assert.ok(mesa.chamadas.filter(c => c.operacao === 'gerenciar-listar').length > listagens, 'a lista é relida depois de uma recusa');
  }
});

test('falha ao calcular o alcance aparece no diálogo e a ação continua desabilitada', async () => {
  const {mesa, liberar} = await abrirDialogo({alcance: () => { throw new Error('Item não encontrado na lixeira.'); }});
  await liberar();
  assert.equal(erro(mesa).textContent, 'Item não encontrado na lixeira.');
  assert.equal(estadoDoAlcance(mesa).hidden, true);
  assert.equal(campo(mesa).disabled, true);
  assert.equal(botoes(mesa)[1].disabled, true);
});

test('em inglês o diálogo, as categorias, o total e a linha do item vêm traduzidos', async () => {
  const {mesa, liberar} = await abrirDialogo({idioma: 'en'});
  assert.equal(estadoDoAlcance(mesa).textContent, 'Working out what will be deleted…');
  await liberar();
  mesa.janela.I18N.aplicar(mesa.doc.body);
  const dlg = dialogo(mesa);
  assert.equal(dlg.querySelector('.dialogo-titulo').textContent, 'Delete permanently');
  assert.equal(dlg.querySelector('.dialogo-linha').textContent, 'Conversation · Conversa velha', 'tipo traduzido, título como dado');
  assert.equal(dlg.querySelector('tbody th').textContent, 'Conversations');
  assert.equal(dlg.querySelector('tfoot').textContent, 'Total4\u00a0files, 1.5\u00a0MB');
  assert.match(dlg.querySelector('label').textContent, /Type “Conversa velha” to confirm/);
  assert.equal(botoes(mesa)[0].textContent, 'Cancel');
  assert.match(dlg.textContent, /Copies already in backups/);
});

const PENDENTE = 'Um apagamento definitivo desta apuração ficou pela metade e só se resolve na próxima partida da Mesa. Até lá, não é possível restaurar nem apagar este item; feche os programas que usem esses arquivos e reinicie a Mesa.';

test('item com apagamento pela metade: Restaurar e Apagar desabilitados e o texto do servidor junto ao item', async () => {
  const mesa = criarMesa({catalogo: [ALFA], url: 'http://127.0.0.1:8765/?area=gerenciar&caso=alfa', api: operacao => {
    if (operacao === 'gerenciar-listar') return {casos: [ALFA], conversas: [], lixeira: [{...structuredClone(ITEM), apagamento_pendente: true}, {...structuredClone(ITEM), id: 'b'.repeat(32), titulo: 'Outra', apagamento_pendente: false}]};
    return {};
  }});
  await mesa.esperar(12);
  const itens = [...mesa.$('gerenciar-lixeira').querySelectorAll('li')];
  assert.equal(itens.length, 2);
  const pendente = itens.find(li => /Conversa velha/.test(li.textContent)), normal = itens.find(li => /Outra/.test(li.textContent));
  assert.deepEqual([...pendente.querySelectorAll('button')].map(b => [b.textContent, b.disabled]), [['Restaurar', true], ['Apagar definitivamente…', true]]);
  assert.equal(pendente.querySelector('.notice').textContent, PENDENTE, 'o texto do servidor, inteiro');
  assert.deepEqual([...normal.querySelectorAll('button')].map(b => b.disabled), [false, false]);
  assert.equal(normal.querySelector('.notice'), null);
});

test('alcance de um item com apagamento pela metade: o texto aparece no diálogo e o campo e a ação ficam desabilitados', async () => {
  const {mesa, liberar} = await abrirDialogo({alcance: () => ({...structuredClone(ALCANCE), apagamento_pendente: true})});
  await liberar();
  assert.equal(estadoDoAlcance(mesa).textContent, PENDENTE, 'a razão, em texto de estado e não em cor de erro');
  assert.equal(erro(mesa).hidden, true);
  assert.equal(campo(mesa).disabled, true);
  assert.equal(botoes(mesa)[1].disabled, true);
  assert.equal(dialogo(mesa).querySelector('table'), null, 'sem tabela: não há o que confirmar');
});
