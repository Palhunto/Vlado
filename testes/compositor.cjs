'use strict';
// The question composer can be collapsed at every width and keeps the draft.
const test = require('node:test');
const assert = require('node:assert/strict');
const {criarMesa} = require('./dom_minimo.cjs');

const ALFA = {id: 'alfa', titulo: 'Pauta Alfa', rodadas: []};
const respostas = {'codex-listar': {conversas: []}, inventario: {caso_id: 'alfa', corpus_id: 'c1', documentos: [], total_documentos: 0}};

async function abrir({desktop = false, idioma = 'pt'} = {}) {
  const observadores = [];
  const mesa = criarMesa({desktop, idioma, armazenamento: {'vlado-idioma': idioma}, catalogo: [ALFA],
    api: operacao => respostas[operacao] || {}, url: 'http://127.0.0.1:8765/?area=codex&caso=alfa',
    preparar: janela => { janela.MutationObserver = class { constructor(funcao) { observadores.push(funcao); } observe() {} disconnect() {} }; }});
  await mesa.esperar(12);
  return {...mesa, mutar: () => observadores.forEach(funcao => funcao([]))};
}
function conversaNaTela(mesa) {
  const pergunta = mesa.doc.createElement('div'); pergunta.className = 'codex-user';
  mesa.$('codex-mensagens').append(pergunta);
  mesa.mutar();
}

for (const desktop of [false, true]) {
  const largura = desktop ? 'desktop' : 'celular e tablet';
  test(`pergunta abre expandida sem conversa e recolhe pelo botão, mantendo o rascunho (${largura})`, async () => {
    const mesa = await abrir({desktop});
    assert.deepEqual(mesa.erros, []);
    const alternar = mesa.$('desktop-composicao-alternar'), corpo = mesa.$('desktop-composicao');
    assert.ok(alternar, 'botão de recolher existe');
    assert.equal(alternar.localName, 'button');
    assert.equal(alternar.getAttribute('aria-controls'), 'desktop-composicao');
    assert.equal(alternar.getAttribute('aria-expanded'), 'true');
    assert.equal(corpo.hidden, false);
    assert.equal(alternar.textContent, 'Recolher pergunta');
    mesa.$('codex-pergunta').value = 'O que os contratos permitem afirmar?';
    alternar.click();
    assert.equal(corpo.hidden, true);
    assert.equal(alternar.getAttribute('aria-expanded'), 'false');
    assert.equal(alternar.textContent, 'Escrever pergunta');
    assert.match(mesa.$('codex-form').textContent, /Rascunho preservado/);
    assert.equal(mesa.$('codex-pergunta').value, 'O que os contratos permitem afirmar?');
    alternar.click();
    assert.equal(corpo.hidden, false);
    assert.equal(mesa.$('codex-pergunta').value, 'O que os contratos permitem afirmar?');
    assert.equal(mesa.doc.activeElement, mesa.$('codex-pergunta'), 'foco volta ao campo');
  });
}

test('no celular, a pergunta recolhe sozinha quando a conversa aparece', async () => {
  const mesa = await abrir();
  conversaNaTela(mesa);
  assert.equal(mesa.$('desktop-composicao').hidden, true);
  assert.equal(mesa.$('desktop-composicao-alternar').getAttribute('aria-expanded'), 'false');
  mesa.janela.abrirComposicaoMesa();
  assert.equal(mesa.$('desktop-composicao').hidden, false, 'ações que levam à pergunta reabrem o campo');
});

test('no celular, um rascunho mantém a pergunta aberta quando a conversa aparece', async () => {
  const mesa = await abrir();
  mesa.$('codex-pergunta').value = 'Rascunho em andamento';
  conversaNaTela(mesa);
  assert.equal(mesa.$('desktop-composicao').hidden, false);
});

test('no desktop, a pergunta só recolhe sozinha quando chega uma resposta', async () => {
  const mesa = await abrir({desktop: true});
  conversaNaTela(mesa);
  assert.equal(mesa.$('desktop-composicao').hidden, false);
  const resposta = mesa.doc.createElement('div'); resposta.className = 'codex-answer';
  mesa.$('codex-mensagens').append(resposta);
  mesa.mutar();
  assert.equal(mesa.$('desktop-composicao').hidden, true);
});

test('em inglês o botão de recolher sai traduzido', async () => {
  const mesa = await abrir({idioma: 'en'});
  mesa.janela.I18N.aplicar(mesa.doc.body);
  assert.equal(mesa.$('desktop-composicao-alternar').textContent, 'Collapse question');
});
