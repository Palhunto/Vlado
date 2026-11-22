'use strict';
// Diálogo de confirmação da Mesa (interface/dialogo.js, docs/design/componentes.md#dialogo): variantes, foco inicial, foco preso,
// Esc, clique no véu, foco de volta ao gatilho, espera curta e longa. DOM sintético (dom_minimo), sem rede.
const test = require('node:test');
const assert = require('node:assert/strict');
const {criarMesa, Evento} = require('./dom_minimo.cjs');

function abrir(idioma = 'pt') {
  const mesa = criarMesa({scripts: ['i18n_en.js', 'i18n.js', 'dialogo.js'], idioma, armazenamento: idioma === 'en' ? {'vlado-idioma': 'en'} : {},
    html: '<!doctype html><html><head></head><body data-idioma-padrao="pt"><main id="conteudo"><button id="gatilho">Excluir</button></main></body></html>',
    preparar: janela => { janela.AbortController = AbortController; }});
  return mesa;
}
const caixa = mesa => mesa.doc.querySelector('dialog.dialogo');
const botoes = mesa => caixa(mesa).querySelectorAll('button');
const tecla = (mesa, alvo, key, extra = {}) => {
  const evento = new Evento('keydown', {key, bubbles: true, cancelable: true, ...extra});
  alvo.dispatchEvent(evento);
  return evento;
};
const digitar = (campo, valor) => { campo.value = valor; campo.dispatchEvent(new Evento('input', {bubbles: true})); };

test('simples: foco na ação, atributos de alertdialog e Cancelar devolve false', async () => {
  const mesa = abrir();
  mesa.$('gatilho').focus();
  const promessa = mesa.janela.Dialogo.confirmar({titulo: 'Gerar novo link de ativação?', texto: 'A senha atual deixa de valer.', acao: 'Gerar novo link'});
  await mesa.esperar();
  const dlg = caixa(mesa), [cancelar, acao] = botoes(mesa);
  assert.equal(dlg.open, true);
  assert.equal(dlg.getAttribute('role'), 'alertdialog');
  assert.equal(dlg.getAttribute('aria-modal'), 'true');
  assert.equal(mesa.doc.getElementById(dlg.getAttribute('aria-labelledby')).textContent, 'Gerar novo link de ativação?');
  assert.equal(mesa.doc.getElementById(dlg.getAttribute('aria-describedby')).textContent, 'A senha atual deixa de valer.');
  assert.equal(acao.textContent, 'Gerar novo link');
  assert.ok(!acao.className.includes('danger'), 'a ação simples é o botão principal');
  assert.ok(mesa.doc.activeElement === acao, 'simples: o foco inicial é a ação');
  assert.equal(mesa.$('conteudo').inert, true, 'a página atrás fica inerte');
  cancelar.click();
  assert.equal(await promessa, false);
  assert.equal(caixa(mesa), null, 'o diálogo sai da página');
  assert.equal(mesa.$('conteudo').inert, false, 'a página volta');
  assert.ok(mesa.doc.activeElement === mesa.$('gatilho'), 'o foco volta ao controle que abriu');
});

test('destrutivo: foco em Cancelar, nome do item no título marcado como dado e ação de contorno de erro', async () => {
  const mesa = abrir();
  mesa.$('gatilho').focus();
  const promessa = mesa.janela.Dialogo.confirmar({variante: 'destrutivo', rubrica: 'Mover para a lixeira',
    titulo: 'Mover {item} para a lixeira?', item: 'Vila Serena — contrato de pavimentação', acao: 'Mover para a lixeira'});
  await mesa.esperar();
  const [cancelar, acao] = botoes(mesa);
  assert.ok(mesa.doc.activeElement === cancelar, 'destrutivo: o foco inicial é "Cancelar"');
  assert.ok(acao.className.includes('danger'));
  const titulo = caixa(mesa).querySelector('.dialogo-titulo');
  assert.equal(titulo.textContent, 'Mover “Vila Serena — contrato de pavimentação” para a lixeira?');
  assert.equal(titulo.querySelector('[translate="no"]').textContent, '“Vila Serena — contrato de pavimentação”');
  acao.click();
  assert.equal(await promessa, true);
});

test('Esc cancela, o clique no véu não fecha e o foco volta ao gatilho', async () => {
  const mesa = abrir();
  mesa.$('gatilho').focus();
  const promessa = mesa.janela.Dialogo.confirmar({variante: 'destrutivo', titulo: 'Descartar?', acao: 'Descartar alterações'});
  await mesa.esperar();
  caixa(mesa).click();   // clique na própria caixa/véu: nada acontece
  assert.equal(caixa(mesa).open, true, 'clique no véu não fecha');
  const evento = tecla(mesa, caixa(mesa), 'Escape');
  assert.equal(evento.defaultPrevented, true);
  assert.equal(await promessa, false, 'Esc vale como Cancelar');
  assert.ok(mesa.doc.activeElement === mesa.$('gatilho'));
});

test('o evento cancel nativo (Esc no navegador) não fecha sozinho: passa pelo Cancelar', async () => {
  const mesa = abrir();
  const promessa = mesa.janela.Dialogo.confirmar({titulo: 'Sair?', acao: 'Sair'});
  await mesa.esperar();
  const nativo = new Evento('cancel', {cancelable: true});
  caixa(mesa).dispatchEvent(nativo);
  assert.equal(nativo.defaultPrevented, true);
  assert.equal(await promessa, false);
});

test('foco preso: Tab no último volta ao primeiro e Shift+Tab no primeiro vai ao último', async () => {
  const mesa = abrir();
  mesa.janela.Dialogo.confirmar({variante: 'destrutivo', titulo: 'Excluir?', acao: 'Excluir nota'});
  await mesa.esperar();
  const [cancelar, acao] = botoes(mesa);
  acao.focus();
  assert.equal(tecla(mesa, acao, 'Tab').defaultPrevented, true);
  assert.ok(mesa.doc.activeElement === cancelar);
  assert.equal(tecla(mesa, cancelar, 'Tab', {shiftKey: true}).defaultPrevented, true);
  assert.ok(mesa.doc.activeElement === acao);
});

test('com campo: a ação só habilita quando o nome confere e Enter no campo respeita isso', async () => {
  const mesa = abrir();
  const promessa = mesa.janela.Dialogo.confirmar({variante: 'campo', titulo: 'Apagar definitivamente', nome: 'Conversa velha', acao: 'Apagar definitivamente'});
  await mesa.esperar();
  const campo = caixa(mesa).querySelector('input'), [, acao] = botoes(mesa);
  assert.ok(mesa.doc.activeElement === campo, 'com campo: o foco inicial é o campo');
  assert.equal(acao.disabled, true);
  assert.match(caixa(mesa).querySelector('label').textContent, /Digite «Conversa velha» para confirmar/);
  assert.equal(campo.getAttribute('translate'), 'no');
  digitar(campo, 'outra coisa');
  tecla(mesa, campo, 'Enter');
  assert.equal(caixa(mesa).open, true, 'Enter com o nome errado não confirma');
  digitar(campo, '  CONVERSA VELHA ');
  assert.equal(acao.disabled, false, 'compara sem diferença de caixa e espaços, como o servidor');
  tecla(mesa, campo, 'Enter');
  assert.equal(await promessa, true);
});

test('espera curta: ação no gerúndio, aria-busy, Cancelar desabilitado; erro volta com role=alert e permite nova tentativa', async () => {
  const mesa = abrir();
  let liberar, tentativa = 0;
  const promessa = mesa.janela.Dialogo.confirmar({variante: 'destrutivo', titulo: 'Excluir?', acao: 'Excluir nota', ocupado: 'Excluindo…',
    executar: () => { tentativa++; return new Promise((resolve, reject) => { liberar = {resolve, reject}; }); }});
  await mesa.esperar();
  const [cancelar, acao] = botoes(mesa);
  acao.click();
  await mesa.esperar();
  assert.equal(caixa(mesa).getAttribute('aria-busy'), 'true');
  assert.equal(acao.textContent, 'Excluindo…');
  assert.equal(acao.disabled, true);
  assert.equal(cancelar.disabled, true, 'na espera curta não se cancela');
  tecla(mesa, caixa(mesa), 'Escape');
  assert.equal(caixa(mesa).open, true, 'Esc também espera a resposta');
  liberar.reject(new Error('Não deu para excluir. Tente de novo.'));
  await mesa.esperar();
  const erro = caixa(mesa).querySelector('.dialogo-erro');
  assert.equal(erro.hidden, false);
  assert.equal(erro.getAttribute('role'), 'alert');
  assert.equal(erro.textContent, 'Não deu para excluir. Tente de novo.');
  assert.equal(caixa(mesa).getAttribute('aria-busy'), null);
  assert.equal(acao.disabled, false);
  acao.click(); await mesa.esperar();
  liberar.resolve();
  assert.equal(await promessa, true);
  assert.equal(tentativa, 2);
});

test('espera longa: barra com etapa e porcentagem, aviso de que pode sair e Cancelar aborta o sinal', async () => {
  const mesa = abrir();
  let sinal, etapa;
  const promessa = mesa.janela.Dialogo.confirmar({variante: 'campo', titulo: 'Apagar definitivamente', nome: 'x', acao: 'Apagar definitivamente',
    ocupado: 'Apagando…', longa: true,
    executar: ctx => { sinal = ctx.sinal; etapa = ctx.etapa; return new Promise((_, reject) => ctx.sinal.addEventListener('abort', () => reject(new Error('cancelado')))); }});
  await mesa.esperar();
  digitar(caixa(mesa).querySelector('input'), 'x');
  const [cancelar, acao] = botoes(mesa);
  acao.click();
  await mesa.esperar();
  const progresso = caixa(mesa).querySelector('.dialogo-progresso');
  assert.equal(progresso.hidden, false);
  assert.equal(progresso.getAttribute('role'), 'status');
  etapa('Apagando a pasta 2 de 5', 0.4);
  assert.match(progresso.textContent, /Apagando a pasta 2 de 5/);
  assert.match(progresso.textContent, /Você pode sair desta tela/);
  const barra = progresso.querySelector('[role="progressbar"]');
  assert.equal(barra.getAttribute('aria-valuenow'), '40');
  assert.equal(cancelar.disabled, false, 'na espera longa o Cancelar fica ativo');
  cancelar.click();
  assert.equal(sinal.aborted, true);
  assert.equal(await promessa, false);
  assert.equal(caixa(mesa), null);
});

test('várias chamadas esperam a vez: um diálogo por vez', async () => {
  const mesa = abrir();
  const primeira = mesa.janela.Dialogo.confirmar({titulo: 'Primeira?', acao: 'Sim'});
  const segunda = mesa.janela.Dialogo.confirmar({titulo: 'Segunda?', acao: 'Sim'});
  await mesa.esperar();
  assert.equal(mesa.doc.querySelectorAll('dialog.dialogo').length, 1);
  assert.equal(caixa(mesa).querySelector('.dialogo-titulo').textContent, 'Primeira?');
  botoes(mesa)[0].click();
  assert.equal(await primeira, false);
  await mesa.esperar();
  assert.equal(caixa(mesa).querySelector('.dialogo-titulo').textContent, 'Segunda?');
  botoes(mesa)[1].click();
  assert.equal(await segunda, true);
});

test('em inglês, os textos fixos e os da chamada passam pelo dicionário', async () => {
  const mesa = abrir('en');
  mesa.janela.Dialogo.confirmar({variante: 'destrutivo', titulo: 'Descartar e fechar?', acao: 'Descartar e fechar'});
  await mesa.esperar();
  assert.equal(botoes(mesa)[0].textContent, 'Cancel');
});

test('a interface não usa mais o confirm() do navegador (UX-16, W11 regra 8)', () => {
  const fs = require('node:fs'), path = require('node:path');
  const pasta = path.resolve(__dirname, '..', 'interface');
  const usos = fs.readdirSync(pasta).filter(nome => nome.endsWith('.js') && nome !== 'dialogo.js')
    .filter(nome => /\b(window\.)?confirm\(/.test(fs.readFileSync(path.join(pasta, nome), 'utf8').replace(/\bDialogo\.confirmar\(/g, '')));
  assert.deepEqual(usos, [], 'troque por Dialogo.confirmar');
});
