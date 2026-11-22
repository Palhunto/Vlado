'use strict';
// UX-19: com conversas guardadas atrás do campo de pergunta e nenhuma aberta, o campo nasce recolhido (não cobre a lista). Digitar, focar o
// campo ou ter contribuição pendente mantém aberto; trocar de apuração refaz a decisão; o botão "Escrever pergunta" alcança o campo.
const test = require('node:test');
const assert = require('node:assert/strict');
const {criarMesa} = require('./dom_minimo.cjs');

const ALFA = {id: 'alfa', titulo: 'Pauta Alfa', rodadas: []};
const CONVERSAS = [{id: 'chat1', titulo: 'Merenda', estado: 'concluido'}, {id: 'chat2', titulo: 'Transporte', estado: 'concluido'}];

async function abrir({conversas = CONVERSAS, papel = 'admin', desktop = true} = {}) {
  const observadores = [];
  const mesa = criarMesa({desktop, papel, catalogo: [ALFA], url: 'http://127.0.0.1:8765/?area=codex&caso=alfa',
    api: operacao => ({'codex-listar': {conversas}, inventario: {caso_id: 'alfa', corpus_id: 'c1', documentos: [], total_documentos: 0}}[operacao] || {}),
    preparar: janela => { janela.MutationObserver = class { constructor(funcao) { observadores.push(funcao); } observe() {} disconnect() {} }; }});
  await mesa.esperar(12);
  mesa.mutar = () => observadores.forEach(funcao => funcao([]));
  mesa.mutar();
  return mesa;
}
const fechado = mesa => mesa.$('codex-form').classList.contains('desktop-composer-closed');

for (const desktop of [true, false]) {
  const largura = desktop ? 'desktop' : 'celular e tablet';
  test(`conversas guardadas e nenhuma aberta: o campo nasce recolhido e "Escrever pergunta" o abre (${largura})`, async () => {
    const mesa = await abrir({desktop});
    assert.equal(mesa.$('codex-conversa').options.length, 3, 'Nova conversa mais as duas guardadas');
    assert.equal(fechado(mesa), true, 'recolhido por padrão');
    assert.equal(mesa.$('desktop-composicao').hidden, true);
    const alternar = mesa.$('desktop-composicao-alternar');
    assert.equal(alternar.textContent, 'Escrever pergunta');
    alternar.click();
    assert.equal(fechado(mesa), false);
    assert.ok(mesa.doc.activeElement === mesa.$('codex-pergunta'), 'o foco vai para o campo');
  });
}

test('sem conversas guardadas o campo continua aberto: é a ação principal da tela', async () => {
  const mesa = await abrir({conversas: []});
  assert.equal(fechado(mesa), false);
});

test('texto digitado, foco num controle do campo ou contribuição pendente mantêm o campo aberto ao trocar de apuração', async () => {
  const contexto = mesa => mesa.janela.dispatchEvent(new mesa.janela.Event('mesa-contexto-alterado'));
  const digitado = await abrir();
  digitado.$('desktop-composicao-alternar').click();
  digitado.$('codex-pergunta').value = 'Quanto foi pago?';
  digitado.$('contexto-caso').focus();
  contexto(digitado);
  assert.equal(fechado(digitado), false, 'com texto digitado não recolhe');
  const focado = await abrir();
  focado.$('desktop-composicao-alternar').click();
  focado.$('codex-enviar').focus();
  contexto(focado);
  assert.equal(fechado(focado), false, 'com o foco num controle do campo não recolhe, e o foco não some');
  assert.ok(focado.doc.activeElement === focado.$('codex-enviar'));
  const pendente = await abrir();
  pendente.$('desktop-composicao-alternar').click();
  const painel = pendente.doc.querySelector('#desktop-composicao .feedback-preview');
  assert.ok(painel, 'painel de contribuição do campo');
  painel.hidden = false;
  pendente.$('contexto-caso').focus();
  contexto(pendente);
  assert.equal(fechado(pendente), false, 'com contribuição pendente não recolhe');
});

test('trocar de apuração refaz a decisão: o campo aberto à mão volta a recolher se houver conversas guardadas', async () => {
  const mesa = await abrir();
  assert.equal(fechado(mesa), true);
  mesa.$('desktop-composicao-alternar').click();
  assert.equal(fechado(mesa), false);
  mesa.mutar();
  assert.equal(fechado(mesa), false, 'sem troca de apuração a escolha da pessoa vale');
  mesa.$('contexto-caso').focus();   // a troca vem do seletor do cabeçalho
  mesa.janela.dispatchEvent(new mesa.janela.Event('mesa-contexto-alterado'));
  assert.equal(fechado(mesa), true, 'trocou de apuração: decide de novo');
});

test('o convidado passa pelo mesmo caminho: campo recolhido, "Escrever pergunta" alcança o campo e o foco fica no botão ao recolher', async () => {
  const mesa = await abrir({papel: 'convidado'});
  assert.equal(fechado(mesa), true);
  const alternar = mesa.$('desktop-composicao-alternar');
  assert.equal(alternar.hidden, false);
  alternar.click();
  assert.equal(fechado(mesa), false);
  assert.ok(mesa.doc.activeElement === mesa.$('codex-pergunta'));
  alternar.click();
  assert.equal(fechado(mesa), true);
  assert.ok(mesa.doc.activeElement === alternar, 'ao recolher à mão, o foco volta ao botão');
});
