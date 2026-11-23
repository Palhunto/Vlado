'use strict';
// Provedor e chave da IA com a senha de quem faz (configuracao_ia.js; contrato de contas, 5.15; servidor em test_senha_gestao.py): salvar e remover a chave
// seguem primeiro; se o servidor responder 403 senha_necessaria, o diálogo pede "Sua senha" e reenvia o MESMO pedido com `senha`.
const test = require('node:test');
const assert = require('node:assert/strict');
const {criarMesa, Evento} = require('./dom_minimo.cjs');

const falha = (codigo, erro, estado = 'proibido') => Object.assign(new Error(erro), {result: {estado, codigo, erro}});
const ESTADO = {provedor: 'anthropic', modelo_preferido: null, modelos_padrao: {anthropic: 'modelo-a', openai: 'modelo-o'},
  chaves: {anthropic: {configurada: true, origem: 'salva', final: '1234'}, openai: {configurada: false}}};

async function abrir({exigeSenha = true, certa = 'senha-certa'} = {}) {
  const pedidos = [];
  const mesa = criarMesa({modo: 'piloto', papel: 'admin', api: (operacao, dados) => {
    if (operacao === 'ia-config') return ESTADO;
    if (operacao === 'ia-config-salvar') {
      pedidos.push({...dados});
      if (exigeSenha) {
        if (!dados.senha) throw falha('senha_necessaria', 'Digite a sua senha para confirmar.');
        if (dados.senha !== certa) throw falha('senha_atual_incorreta', 'Senha incorreta.');
      }
      return {...ESTADO, provedor: dados.provedor, modelo_preferido: dados.modelo_preferido,
        chaves: {...ESTADO.chaves, anthropic: dados.remover_chave ? {configurada: false} : {configurada: true, origem: 'salva', final: '9999'}}};
    }
    return {};
  }});
  await mesa.esperar(12);
  return {mesa, pedidos};
}
const dialogo = mesa => mesa.doc.querySelector('dialog.dialogo');
const campo = mesa => dialogo(mesa).querySelector('input');
const botoes = mesa => [...dialogo(mesa).querySelectorAll('.dialogo-acoes button')];
const digitar = (entrada, texto) => { entrada.value = texto; entrada.dispatchEvent(new Evento('input', {bubbles: true})); };
const salvar = async mesa => { mesa.$('ia-config').dispatchEvent(new Evento('submit', {bubbles: true, cancelable: true})); await mesa.esperar(8); };

test('salvar: o pedido segue sem senha; o servidor pede; o diálogo reenvia o mesmo pedido com a senha e a tela guarda o resultado', async () => {
  const {mesa, pedidos} = await abrir();
  mesa.$('ia-modelo').value = 'modelo-x'; mesa.$('ia-chave').value = '  chave-nova-123 ';
  await salvar(mesa);
  assert.deepEqual(pedidos.map(p => p.senha), [undefined], 'o primeiro pedido vai sem senha');
  assert.ok(dialogo(mesa), 'o diálogo abre');
  assert.equal(dialogo(mesa).querySelector('.dialogo-titulo').textContent, 'Salvar a configuração da IA?');
  assert.equal(campo(mesa).type, 'password');
  digitar(campo(mesa), 'senha-certa'); botoes(mesa)[1].click(); await mesa.esperar(8);
  assert.equal(pedidos.length, 2);
  assert.deepEqual({...pedidos[1], senha: undefined}, {...pedidos[0], senha: undefined}, 'o MESMO pedido, só com a senha a mais');
  assert.equal(pedidos[1].senha, 'senha-certa'); assert.equal(pedidos[1].chave, 'chave-nova-123');
  assert.equal(dialogo(mesa), null);
  assert.equal(mesa.$('ia-config-mensagem').textContent, 'Configuração salva.');
  assert.equal(mesa.$('ia-chave').value, '', 'a chave digitada sai do campo');
  assert.equal(mesa.$('ia-chave-estado').textContent, 'Chave salva · termina em 9999');
  assert.ok(!mesa.doc.body.textContent.includes('senha-certa') && !mesa.doc.body.textContent.includes('chave-nova-123'), 'nem a senha nem a chave aparecem na tela');
  assert.equal(mesa.$('ia-salvar').disabled, false); assert.equal(mesa.$('ia-remover').disabled, false);
});

test('senha incorreta fica no campo do diálogo e nada é salvo; cancelar não envia mais nada, não mostra sucesso e devolve os botões', async () => {
  const {mesa, pedidos} = await abrir();
  await salvar(mesa);
  digitar(campo(mesa), 'errada'); botoes(mesa)[1].click(); await mesa.esperar(8);
  assert.ok(dialogo(mesa), 'continua aberto');
  assert.ok([...dialogo(mesa).querySelectorAll('.dialogo-erro-campo')].some(p => !p.hidden && p.textContent.startsWith('Senha incorreta')));
  assert.equal(mesa.$('ia-chave-estado').textContent, 'Chave salva · termina em 1234', 'nada mudou');
  botoes(mesa)[0].click(); await mesa.esperar(6);
  assert.equal(dialogo(mesa), null);
  assert.equal(pedidos.length, 2, 'o sem senha e a tentativa errada, nada além');
  assert.equal(mesa.$('ia-config-mensagem').textContent, '', 'cancelar não anuncia nada');
  assert.equal(mesa.$('ia-salvar').disabled, false);
});

test('remover a chave salva pede a senha no diálogo destrutivo e reenvia remover_chave com ela', async () => {
  const {mesa, pedidos} = await abrir();
  assert.equal(mesa.$('ia-remover').hidden, false);
  mesa.$('ia-remover').click(); await mesa.esperar(8);
  assert.equal(dialogo(mesa).dataset.variante, 'destrutivo');
  assert.equal(dialogo(mesa).querySelector('.dialogo-titulo').textContent, 'Remover a chave de IA?');
  digitar(campo(mesa), 'senha-certa'); botoes(mesa)[1].click(); await mesa.esperar(8);
  assert.deepEqual(pedidos.map(p => [p.remover_chave, p.senha]), [[true, undefined], [true, 'senha-certa']]);
  assert.equal(mesa.$('ia-config-mensagem').textContent, 'Chave removida.');
  assert.equal(mesa.$('ia-chave-estado').textContent, 'Nenhuma chave configurada.');
});

test('sem contas (o servidor não pede senha) o diálogo nem abre e a chave é salva direto', async () => {
  const {mesa, pedidos} = await abrir({exigeSenha: false});
  mesa.$('ia-chave').value = 'chave-nova-123';
  await salvar(mesa);
  assert.equal(dialogo(mesa), null);
  assert.equal(pedidos.length, 1); assert.equal(pedidos[0].senha, undefined);
  assert.equal(mesa.$('ia-config-mensagem').textContent, 'Configuração salva.');
});

test('em inglês o diálogo da chave fala inglês', async () => {
  const mesa = criarMesa({modo: 'piloto', papel: 'admin', idioma: 'en', armazenamento: {'vlado-idioma': 'en'}, api: (operacao, dados) => {
    if (operacao === 'ia-config') return ESTADO;
    if (operacao === 'ia-config-salvar' && !dados.senha) throw falha('senha_necessaria', 'x');
    return {};
  }});
  await mesa.esperar(12);
  await salvar(mesa);
  assert.equal(dialogo(mesa).querySelector('.dialogo-titulo').textContent, 'Save the AI configuration?');
  assert.ok(dialogo(mesa).textContent.includes('Your password confirms that it is you changing the AI connection.'));
  assert.equal(botoes(mesa)[1].textContent, 'Save');
});
