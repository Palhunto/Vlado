'use strict';
// Onde está Configurações em cada modo (piloto.js; desde 29aeafa o botão do cabeçalho é só das instalações com contas). No modo local, sem contas, não há botão nem perfil:
// a chave e o provedor da IA ficam em Perguntar > Conexão e opções (#ia-config, que o administrador local sempre alcança). Com contas, dono, editor, repórter e leitor têm o botão
// e o perfil; o convidado só o perfil (Minha conta). DOM sintético; a medida nas duas larguras foi feita no Chromium contra uma Mesa --modo local.
const test = require('node:test');
const assert = require('node:assert/strict');
const {criarMesa} = require('./dom_minimo.cjs');

async function abrir(modo, papel) {
  const mesa = criarMesa({desktop: true, modo, papel, url: 'http://127.0.0.1:8765/?area=inicio'});
  await mesa.esperar(10);
  return mesa;
}

test('modo local: sem botão Configurações nem perfil, e o formulário da chave de IA está em Perguntar > Conexão e opções', async () => {
  const mesa = await abrir('local', 'admin');
  assert.equal(mesa.$('mesa-configuracoes').hidden, true);
  assert.equal(mesa.$('ver-configuracoes').hidden, true);
  const form = mesa.$('ia-config');
  assert.ok(form && !form.hidden, 'o formulário da chave não é escondido pelo modo');
  assert.ok(mesa.$('codex-conexao').contains(form), 'fica dentro de Conexão e opções, que o Perguntar abre');
  assert.ok(mesa.$('area-codex').contains(mesa.$('codex-conexao')));
});

test('modos com contas: dono, editor, repórter e leitor têm o botão do cabeçalho e o perfil; o convidado só o perfil', async () => {
  for (const modo of ['local-contas', 'piloto']) {
    for (const papel of ['admin', 'dono', 'editor', 'reporter', 'leitor']) {
      const mesa = await abrir(modo, papel);
      assert.equal(mesa.$('mesa-configuracoes').hidden, false, `${modo}/${papel}: botão do cabeçalho`);
      assert.equal(mesa.$('ver-configuracoes').hidden, false, `${modo}/${papel}: perfil`);
    }
    const convidado = await abrir(modo, 'convidado');
    assert.equal(convidado.$('mesa-configuracoes').hidden, true, `${modo}/convidado: sem botão`);
    assert.equal(convidado.$('ver-configuracoes').hidden, false, `${modo}/convidado: Minha conta`);
  }
});
