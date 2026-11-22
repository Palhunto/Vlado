'use strict';
// A tela antiga "Contas de acesso" saiu de Configurações (P30), junto com as operações `contas-*` (a Tranca as retirou do servidor: respondem 404).
// Quem inclui pessoas é o Convidar da Equipe; quem recupera o acesso, a Equipe. Aqui se prova que nenhuma tela chama `contas-*`: nem o código, nem a
// Mesa aberta em cada área, aba e botão, para cada papel; e que o painel e as peças que só serviam a ele não existem mais.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {abrir, esperar} = require('./contas_apoio.cjs');

const INTERFACE = path.join(__dirname, '..', 'interface');
const ARQUIVOS = fs.readdirSync(INTERFACE).filter(nome => /\.(js|html)$/.test(nome));

test('nenhum arquivo da interface nomeia uma operação contas-* (a tela e o fallback de senha saíram)', () => {
  const achados = [];
  for (const nome of ARQUIVOS) {
    const linhas = fs.readFileSync(path.join(INTERFACE, nome), 'utf8').split('\n');
    linhas.forEach((linha, i) => { if (/['"`]contas-[a-z]/.test(linha) || /api\(['"`]contas-/.test(linha)) achados.push(`${nome}:${i + 1}: ${linha.trim().slice(0, 80)}`); });
  }
  assert.deepEqual(achados, []);
});

test('o painel "Contas de acesso" e tudo que só servia a ele saíram da página', () => {
  const html = fs.readFileSync(path.join(INTERFACE, 'index.html'), 'utf8');
  assert.ok(!/id="acesso-/.test(html), 'nenhum id acesso-*');
  assert.ok(!html.includes('Contas de acesso') && !html.includes('Nova conta') && !html.includes('link de ativação'));
  assert.ok(!html.includes('Adicione contas para outras pessoas'), 'o texto de Configurações não fala de contas que não aparecem (R7)');
  const piloto = fs.readFileSync(path.join(INTERFACE, 'piloto.js'), 'utf8');
  assert.ok(!/acesso-|ativac|Dialogo\.comSenha|contas/i.test(piloto), 'piloto.js só cuida de sair, do perfil e do botão Configurações');
  const css = fs.readFileSync(path.join(INTERFACE, 'style.css'), 'utf8');
  assert.ok(!css.includes('#acesso-'));
  const app = fs.readFileSync(path.join(INTERFACE, 'app.js'), 'utf8');
  assert.ok(!/administra\(|administra,/.test(app) && !app.includes('Sessao.administra'), 'Sessao.administra só servia à tela antiga');
});

for (const papel of ['dono', 'editor', 'reporter', 'leitor']) {
  test(`${papel}: abrir cada área, aba e botão não faz nenhuma chamada contas-*`, async () => {
    const {mesa} = abrir({papel, url: 'http://127.0.0.1:8765/'});
    await esperar(mesa);
    assert.deepEqual(mesa.erros, []);
    assert.equal(mesa.$('acesso-painel'), null);
    const ids = ['ver-inicio', 'ver-documentos', 'ver-codex', 'ver-achados', 'ver-quadros', 'ver-apuracao', 'ver-diligencias', 'ver-gerenciar',
      'ver-cadastro', 'ver-configuracoes', 'mesa-configuracoes'];
    for (const id of ids) {
      const no = mesa.$(id);
      if (no && !no.hidden && !no.hasAttribute('data-sem-capacidade')) { no.click(); await mesa.esperar(6); }
    }
    for (const aba of ['conta-aba-conta', 'conta-aba-equipe', 'conta-aba-configuracoes']) {
      const no = mesa.$(aba);
      if (no && !no.hidden) { no.click(); await mesa.esperar(6); }
    }
    const operacoes = mesa.chamadas.map(c => c.operacao);
    assert.ok(operacoes.length > 3, `a Mesa fez chamadas (${operacoes.length}): o teste não é vazio`);
    assert.deepEqual(operacoes.filter(op => op.startsWith('contas-')), [], 'nenhuma operação contas-*');
    assert.ok(!mesa.doc.body.textContent.includes('Contas de acesso'));
  });
}

test('o dono ainda abre Minha conta, Equipe e Configurações (a página das contas continua inteira)', async () => {
  const {mesa} = abrir({papel: 'dono'});
  await esperar(mesa);
  for (const aba of ['conta', 'equipe', 'configuracoes']) assert.ok(!mesa.$(`conta-aba-${aba}`).hidden, aba);
  assert.ok(mesa.chamadas.some(c => c.operacao === 'conta-ver'), 'Minha conta fala com conta-ver, no singular');
});
