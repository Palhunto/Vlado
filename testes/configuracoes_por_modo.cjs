'use strict';
// Configurações em todos os modos (P43, docs/design/componentes.md#configuracoes): o <form id="ia-config"> mora só na página Configurações, o mesmo elemento em qualquer modo;
// Perguntar > Conexão e opções ficou com a linha do que está em uso e o link "Alterar em Configurações". No modo local, sem contas, o botão do cabeçalho existe, mas não há
// perfil, Sair nem abas. Com contas, dono, editor, repórter e leitor têm o botão e o perfil; o convidado só o perfil (Minha conta). DOM sintético.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {criarMesa, Evento} = require('./dom_minimo.cjs');

// As capacidades de cada papel são as do servidor de verdade (testes/fixtures/capacidades_por_papel.json, conferida por test_capacidades_fixture.py): quem não tem `ia-config` não vê o botão.
const CAPACIDADES = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures', 'capacidades_por_papel.json'), 'utf8'));
const sessaoDe = papel => ({conta: {id: 'a'.repeat(16), nome: 'Ana Lima', email: 'ana@redacao.org', login: 'ana.lima', papel, casos: papel === 'dono' ? null : ['alfa']},
  organizacao: {id: 'o1', nome: 'Redação Serena'}, pendencias: [], capacidades: CAPACIDADES[papel], csrf: 'x', ambiente: 'homologacao', modo: 'piloto', expira_em: null});
const recusa = (codigo, erro) => Object.assign(new Error(erro), {result: {estado: 'proibido', codigo, erro}});

const ESTADO = {provedor: 'anthropic', modelo_preferido: null, modelos_padrao: {anthropic: 'claude-sonnet-5-5', openai: 'gpt'}, chaves: {anthropic: {configurada: false}, openai: {configurada: false}}};
// `capacidades`: com contas a sessão traz a lista do papel, como o servidor; o modo local não a manda (nada se esconde). `status`: a resposta de codex-status.
async function abrir(modo, papel, {ia = ESTADO, idioma = 'pt', capacidades = false, status = {}} = {}) {
  const proprio = capacidades ? papel : null;
  const mesa = criarMesa({desktop: true, modo, papel: papel === 'dono' ? 'admin' : papel, idioma, url: 'http://127.0.0.1:8765/?area=inicio',
    api: operacao => {
      if (operacao === 'sessao' && proprio) return sessaoDe(proprio);
      if (operacao === 'ia-config') { if (proprio && !CAPACIDADES[proprio].includes('ia-config')) throw recusa('operacao_proibida', 'Operação não permitida para este acesso.'); return ia; }
      if (operacao === 'codex-status') return status;
      return {};
    }});
  await mesa.esperar(12);
  return mesa;
}
// Perguntar abre: o codex.js lê o codex-status (provedor e modelo reais, para qualquer papel).
const abrirPerguntar = async mesa => { mesa.janela.dispatchEvent(new Evento('codex-abrir')); await mesa.esperar(12); return mesa; };

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

test('com contas cada papel vê o que as capacidades reais dão: só quem tem ia-config vê o botão e o link; todos têm o perfil, Sair e a linha de Perguntar', async () => {
  for (const modo of ['local-contas', 'piloto']) {
    for (const papel of ['dono', 'editor', 'reporter', 'leitor']) {
      const tem = CAPACIDADES[papel].includes('ia-config');
      const mesa = await abrirPerguntar(await abrir(modo, papel, {capacidades: true, status: {autenticado: true, provedor: 'anthropic', modelo: 'claude-sonnet-5-5', versao: '1'}}));
      assert.equal(mesa.$('mesa-configuracoes').hasAttribute('data-sem-capacidade'), !tem, `${modo}/${papel}: botão do cabeçalho ${tem ? 'aparece' : 'some'}`);
      assert.equal(mesa.$('ia-alterar').hasAttribute('data-sem-capacidade'), !tem, `${modo}/${papel}: link de Perguntar ${tem ? 'aparece' : 'some'}`);
      assert.equal(mesa.$('ver-configuracoes').hidden, false, `${modo}/${papel}: perfil`);
      assert.equal(mesa.$('mesa-sair').hidden, false, `${modo}/${papel}: Sair`);
      assert.equal(mesa.$('ia-resumo-linha').hidden, false, `${modo}/${papel}: a linha do que está em uso aparece`);
    }
    const convidado = await abrir(modo, 'convidado', {capacidades: true});
    assert.equal(convidado.$('mesa-configuracoes').hidden, true, `${modo}/convidado: sem botão`);
    assert.equal(convidado.$('ver-configuracoes').hidden, false, `${modo}/convidado: Minha conta`);
  }
  assert.ok(CAPACIDADES.dono.includes('ia-config') && !CAPACIDADES.editor.includes('ia-config'), 'o fixture diferencia os papéis (o teste não é vazio)');
});

test('P1 da Coruja: quem não tem ia-config vê o provedor e o modelo reais pelo codex-status, e sem eles a linha fica escondida (nunca um texto fixo)', async () => {
  const real = await abrirPerguntar(await abrir('piloto', 'editor', {capacidades: true, status: {autenticado: true, provedor: 'openai', modelo: 'gpt-x', versao: '1'}}));
  assert.equal(real.$('ia-resumo-linha').hidden, false);
  assert.equal(real.$('ia-resumo').textContent, 'IA: OpenAI (GPT), modelo gpt-x.');
  assert.ok(real.$('ia-alterar').hasAttribute('data-sem-capacidade'), 'sem o link');
  const ingles = await abrirPerguntar(await abrir('piloto', 'editor', {capacidades: true, idioma: 'en', status: {autenticado: true, provedor: 'anthropic', modelo: 'claude-sonnet-5-5'}}));
  ingles.janela.I18N.aplicar(ingles.$('codex-conexao'));
  assert.equal(ingles.$('ia-resumo').textContent, 'AI: Anthropic (Claude), model claude-sonnet-5-5.');
  const sem = await abrirPerguntar(await abrir('piloto', 'leitor', {capacidades: true, status: {autenticado: true}}));
  assert.equal(sem.$('ia-resumo-linha').hidden, true, 'sem provedor e modelo, a linha não aparece');
  assert.equal(sem.$('ia-resumo').textContent, '');
  const dono = await abrirPerguntar(await abrir('piloto', 'dono', {capacidades: true, status: {autenticado: true, provedor: 'openai', modelo: 'gpt-x'}}));
  assert.equal(dono.$('ia-resumo').textContent, 'IA: Anthropic (Claude), modelo padrão.', 'quem pode mudar vê o que a configuração diz');
});
