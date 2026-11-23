'use strict';
// Configurações em todos os modos (P43, docs/design/componentes.md#configuracoes): o <form id="ia-config"> mora só na página Configurações, o mesmo elemento em qualquer modo;
// Perguntar > Conexão e opções ficou com a linha do que está em uso e o link "Alterar em Configurações". No modo local, sem contas, o botão do cabeçalho existe, mas não há
// perfil, Sair nem abas. Com contas, dono, editor, repórter e leitor têm o botão e o perfil; o convidado só o perfil (Minha conta). DOM sintético.
const test = require('node:test');
const assert = require('node:assert/strict');
const {criarMesa, Evento} = require('./dom_minimo.cjs');

const ESTADO = {provedor: 'anthropic', modelo_preferido: null, modelos_padrao: {anthropic: 'claude-sonnet-5-5', openai: 'gpt'}, chaves: {anthropic: {configurada: false}, openai: {configurada: false}}};
async function abrir(modo, papel, {ia = ESTADO, idioma = 'pt'} = {}) {
  const mesa = criarMesa({desktop: true, modo, papel, idioma, url: 'http://127.0.0.1:8765/?area=inicio', api: operacao => (operacao === 'ia-config' ? ia : {})});
  await mesa.esperar(10);
  return mesa;
}

test('o formulário da chave de IA mora só em Configurações, em todos os modos, e Perguntar ficou com a linha e o link', async () => {
  for (const [modo, papel] of [['local', 'admin'], ['local-contas', 'admin'], ['piloto', 'dono']]) {
    const mesa = await abrir(modo, papel);
    const form = mesa.$('ia-config');
    assert.ok(form && !form.hidden, `${modo}: o formulário existe`);
    assert.ok(mesa.$('area-configuracoes').contains(form), `${modo}: dentro de Configurações`);
    assert.ok(!mesa.$('area-codex').contains(form), `${modo}: fora de Perguntar`);
    assert.equal(mesa.$('ia-titulo').textContent, 'Provedor e chave da IA');
    assert.ok(mesa.$('ia-painel').contains(mesa.$('ia-titulo')) && mesa.$('ia-painel').contains(form));
    assert.equal(mesa.$('ia-resumo').textContent, 'IA: Anthropic (Claude), modelo padrão.');
    assert.ok(mesa.$('codex-conexao').contains(mesa.$('ia-alterar')) && mesa.$('ia-alterar').getAttribute('data-requer') === 'ia-config');
    assert.ok(!/Perguntar, em Conexão e opções/.test(mesa.$('area-configuracoes').textContent), 'sai o texto que mandava para Perguntar');
  }
});

test('a linha de Perguntar diz o provedor e o modelo salvos, e em inglês', async () => {
  const salvo = await abrir('local', 'admin', {ia: {...ESTADO, provedor: 'openai', modelo_preferido: 'gpt-x'}});
  assert.equal(salvo.$('ia-resumo').textContent, 'IA: OpenAI (GPT), modelo gpt-x.');
  const ingles = await abrir('local', 'admin', {idioma: 'en'});
  ingles.janela.I18N.aplicar(ingles.$('codex-conexao'));
  assert.equal(ingles.$('ia-resumo').textContent, 'AI: Anthropic (Claude), default model.');
  assert.equal(ingles.$('ia-alterar').textContent, 'Change in Settings');
});

test('modo local: o botão Configurações existe, sem perfil, Sair nem abas; abre a página e fica com aria-pressed', async () => {
  const mesa = await abrir('local', 'admin');
  const botao = mesa.$('mesa-configuracoes');
  assert.equal(botao.hidden, false);
  assert.equal(botao.getAttribute('aria-pressed'), 'false');
  assert.equal(mesa.$('ver-configuracoes').hidden, true, 'sem perfil');
  assert.equal(mesa.$('mesa-sair').hidden, true, 'sem Sair');
  assert.equal(mesa.$('area-configuracoes').querySelector('nav'), null, 'sem abas');
  botao.click(); await mesa.esperar(5);
  assert.equal(mesa.$('area-configuracoes').hidden, false);
  assert.equal(botao.getAttribute('aria-pressed'), 'true');
  assert.equal(mesa.doc.querySelectorAll('.areas [aria-pressed="true"]').length, 0, 'nenhum item da barra fica selecionado');
  mesa.$('ver-inicio').click(); await mesa.esperar(5);
  assert.equal(botao.getAttribute('aria-pressed'), 'false');
});

test('"Alterar em Configurações" abre a página com o foco no título do painel', async () => {
  const mesa = await abrir('local', 'admin');
  const evento = new Evento('click', {bubbles: true, cancelable: true});
  mesa.$('ia-alterar').dispatchEvent(evento);
  await mesa.esperar(8);
  assert.equal(evento.defaultPrevented, true);
  assert.equal(mesa.$('area-configuracoes').hidden, false);
  assert.ok(mesa.doc.activeElement === mesa.$('ia-titulo'), 'o foco vai ao título do painel');
});

test('modos com contas: dono, editor, repórter e leitor têm o botão do cabeçalho e o perfil; o convidado só o perfil', async () => {
  for (const modo of ['local-contas', 'piloto']) {
    for (const papel of ['admin', 'dono', 'editor', 'reporter', 'leitor']) {
      const mesa = await abrir(modo, papel);
      assert.equal(mesa.$('mesa-configuracoes').hidden, false, `${modo}/${papel}: botão do cabeçalho`);
      assert.equal(mesa.$('ver-configuracoes').hidden, false, `${modo}/${papel}: perfil`);
      assert.equal(mesa.$('mesa-sair').hidden, false, `${modo}/${papel}: Sair`);
    }
    const convidado = await abrir(modo, 'convidado');
    assert.equal(convidado.$('mesa-configuracoes').hidden, true, `${modo}/convidado: sem botão`);
    assert.equal(convidado.$('ver-configuracoes').hidden, false, `${modo}/convidado: Minha conta`);
  }
});
