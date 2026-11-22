'use strict';
// "Contas de acesso" (piloto.js) com a senha de quem age: criar dono, recuperar e desativar dono pedem a senha (403 senha_necessaria sem ela);
// o diálogo (Dialogo.comSenha, dialogo.js) reenvia o MESMO pedido com `senha`. Contrato de contas, 5.15.
const test = require('node:test');
const assert = require('node:assert/strict');
const {criarMesa, Evento} = require('./dom_minimo.cjs');

const falha = (codigo, erro = 'texto do servidor', estado = 'proibido') => Object.assign(new Error(erro), {result: {estado, codigo, erro}});
const DONO = {id: 'c1', nome: 'Ana Lima', login: 'ana', papel: 'dono', ativa: true, situacao: 'ativa'};
const CONVIDADO = {id: 'c2', nome: 'Bia Souza', login: 'bia', papel: 'convidado', ativa: true, situacao: 'ativa', casos: [], cota_diaria: 20};

// `exigem`: operações que respondem senha_necessaria enquanto o pedido não trouxer `senha`; `certa`: a senha que o servidor aceita.
async function abrir({exigem = ['contas-recuperar'], certa = 'senha-certa', contas = [DONO, CONVIDADO], extra = {}} = {}) {
  const pedidos = [];
  const api = (operacao, dados) => {
    pedidos.push({operacao, dados: {...dados}});
    if (operacao === 'contas-listar') return {contas};
    if (extra[operacao]) return extra[operacao](dados);
    if (exigem.includes(operacao)) {
      if (!dados.senha) throw falha('senha_necessaria', 'Digite a sua senha para confirmar.');
      if (dados.senha !== certa) throw falha('senha_atual_incorreta', 'Senha incorreta.');
    }
    if (operacao === 'contas-recuperar' || operacao === 'contas-criar') return {conta: {nome: 'Bia Souza', login: 'bia'}, link: 'http://127.0.0.1/ativar?t=abc'};
    return {estado: 'ok'};
  };
  const mesa = criarMesa({api, modo: 'piloto', papel: 'admin', idioma: 'pt'});
  await mesa.esperar(12);
  const chamadas = operacao => pedidos.filter(p => p.operacao === operacao);
  return {mesa, pedidos, chamadas};
}
const dialogo = mesa => mesa.doc.querySelector('dialog.dialogo');
const campo = mesa => dialogo(mesa).querySelector('input');
const botoes = mesa => [...dialogo(mesa).querySelectorAll('.dialogo-acoes button')];
function digitar(entrada, texto) { entrada.value = texto; entrada.dispatchEvent(new Evento('input', {bubbles: true})); }
const linha = (mesa, login) => [...mesa.$('acesso-lista').querySelectorAll('li')].find(li => li.textContent.includes(login));
const botaoDa = (mesa, login, rotulo) => [...linha(mesa, login).querySelectorAll('button')].find(b => b.textContent === rotulo);

test('Recuperar acesso: o diálogo da senha abre direto (sem confirmação antes) e o pedido vai uma vez, com `senha`', async () => {
  const {mesa, chamadas} = await abrir();
  assert.deepEqual(mesa.erros, []);
  const gatilho = botaoDa(mesa, 'bia', 'Recuperar acesso');
  gatilho.click(); await mesa.esperar(3);
  assert.ok(dialogo(mesa), 'o diálogo abre');
  assert.equal(chamadas('contas-recuperar').length, 0, 'nada vai ao servidor antes da senha');
  assert.equal(dialogo(mesa).querySelector('.dialogo-titulo').textContent, 'Gerar novo link de ativação?');
  assert.equal(campo(mesa).type, 'password');
  digitar(campo(mesa), 'senha-certa'); botoes(mesa)[1].click(); await mesa.esperar(6);
  assert.deepEqual(chamadas('contas-recuperar').map(p => p.dados), [{id: 'c2', senha: 'senha-certa'}]);
  assert.equal(dialogo(mesa), null, 'o diálogo fecha');
  assert.equal(mesa.$('acesso-link-caixa').hidden, false, 'o link novo aparece');
  assert.equal(mesa.$('acesso-mensagem').textContent, 'Novo link de ativação gerado.');
  assert.ok(!gatilho.disabled, 'o botão não fica travado');
});

test('Recuperar acesso: senha incorreta fica no campo do diálogo e a conta não muda; cancelar não envia nem avisa', async () => {
  const {mesa, chamadas} = await abrir();
  botaoDa(mesa, 'bia', 'Recuperar acesso').click(); await mesa.esperar(3);
  digitar(campo(mesa), 'errada'); botoes(mesa)[1].click(); await mesa.esperar(6);
  assert.ok(dialogo(mesa), 'o diálogo continua aberto');
  assert.ok([...dialogo(mesa).querySelectorAll('.dialogo-erro-campo')].some(p => !p.hidden && p.textContent.startsWith('Senha incorreta')));
  assert.equal(mesa.$('acesso-link-caixa').hidden, true);
  botoes(mesa)[0].click(); await mesa.esperar(4);
  assert.equal(dialogo(mesa), null);
  assert.equal(chamadas('contas-recuperar').length, 1, 'só a tentativa errada foi enviada');
  assert.equal(mesa.$('acesso-mensagem').textContent, '', 'cancelar não mostra mensagem');
  assert.ok(!botaoDa(mesa, 'bia', 'Recuperar acesso').disabled);
});

test('Desativar um dono: o diálogo da senha substitui a confirmação, destrutivo, com o login no título', async () => {
  const {mesa, chamadas} = await abrir({exigem: ['contas-desativar']});
  botaoDa(mesa, 'ana', 'Desativar').click(); await mesa.esperar(3);
  assert.ok(dialogo(mesa)); assert.equal(dialogo(mesa).dataset.variante, 'destrutivo');
  assert.equal(dialogo(mesa).querySelector('.dialogo-titulo').textContent, 'Desativar ana?');
  assert.equal(chamadas('contas-desativar').length, 0);
  digitar(campo(mesa), 'senha-certa'); botoes(mesa)[1].click(); await mesa.esperar(6);
  assert.deepEqual(chamadas('contas-desativar').map(p => p.dados), [{id: 'c1', senha: 'senha-certa'}]);
  assert.equal(mesa.$('acesso-mensagem').textContent, 'Conta desativada.');
});

test('Desativar quem não é dono: confirma como antes e envia sem senha; se o servidor pedir, o diálogo abre e reenvia o mesmo pedido', async () => {
  const sem = await abrir({exigem: []});
  botaoDa(sem.mesa, 'bia', 'Desativar').click(); await sem.mesa.esperar(3);
  assert.equal(campo(sem.mesa), null, 'a confirmação simples não tem campo de senha');
  botoes(sem.mesa)[1].click(); await sem.mesa.esperar(6);
  assert.deepEqual(sem.chamadas('contas-desativar').map(p => p.dados), [{id: 'c2'}]);
  assert.equal(dialogo(sem.mesa), null);

  const com = await abrir({exigem: ['contas-desativar']});
  botaoDa(com.mesa, 'bia', 'Desativar').click(); await com.mesa.esperar(3);
  botoes(com.mesa)[1].click(); await com.mesa.esperar(6);   // confirma; o servidor responde senha_necessaria
  assert.ok(campo(com.mesa), 'abre o diálogo da senha');
  digitar(campo(com.mesa), 'senha-certa'); botoes(com.mesa)[1].click(); await com.mesa.esperar(6);
  assert.deepEqual(com.chamadas('contas-desativar').map(p => p.dados), [{id: 'c2'}, {id: 'c2', senha: 'senha-certa'}]);
});

test('Criar conta de administração (dono): o pedido segue primeiro e, se o servidor pedir a senha, o diálogo abre e reenvia; criar convidado envia direto', async () => {
  const dono = await abrir({exigem: ['contas-criar']});
  dono.mesa.$('acesso-papel').value = 'admin';
  dono.mesa.$('acesso-nome').value = 'Caio Reis'; dono.mesa.$('acesso-login').value = 'Caio';
  dono.mesa.$('acesso-form').dispatchEvent(new Evento('submit', {bubbles: true, cancelable: true})); await dono.mesa.esperar(3);
  assert.ok(campo(dono.mesa), 'o diálogo da senha abre quando o servidor pede');
  digitar(campo(dono.mesa), 'senha-certa'); botoes(dono.mesa)[1].click(); await dono.mesa.esperar(6);
  const [primeiro, segundo] = dono.chamadas('contas-criar');
  assert.equal(dono.chamadas('contas-criar').length, 2);
  assert.equal(primeiro.dados.senha, undefined, 'o primeiro pedido vai sem senha');
  assert.equal(segundo.dados.papel, 'admin'); assert.equal(segundo.dados.login, 'caio'); assert.equal(segundo.dados.senha, 'senha-certa');
  assert.deepEqual({...segundo.dados, senha: undefined}, {...primeiro.dados, senha: undefined}, 'o MESMO pedido, só com a senha a mais');
  assert.equal(dono.mesa.$('acesso-mensagem').textContent, 'Conta criada. Envie o link de ativação.');
  assert.equal(dono.mesa.$('acesso-nome').value, '', 'o formulário é limpo depois de criar');

  const convidado = await abrir({exigem: []});
  convidado.mesa.$('acesso-nome').value = 'Dora'; convidado.mesa.$('acesso-login').value = 'dora';
  convidado.mesa.$('acesso-form').dispatchEvent(new Evento('submit', {bubbles: true, cancelable: true})); await convidado.mesa.esperar(6);
  assert.equal(dialogo(convidado.mesa), null); assert.equal(convidado.chamadas('contas-criar')[0].dados.senha, undefined);
});

test('Criar conta de dono: cancelar o diálogo não reenvia, não mostra mensagem de sucesso e mantém o formulário; uma recusa do servidor aparece na tela sem diálogo', async () => {
  const {mesa, chamadas} = await abrir({exigem: ['contas-criar']});
  mesa.$('acesso-papel').value = 'admin';
  mesa.$('acesso-nome').value = 'Caio Reis'; mesa.$('acesso-login').value = 'caio';
  mesa.$('acesso-form').dispatchEvent(new Evento('submit', {bubbles: true, cancelable: true})); await mesa.esperar(3);
  botoes(mesa)[0].click(); await mesa.esperar(4);
  assert.equal(chamadas('contas-criar').length, 1, 'só o primeiro pedido, sem senha');
  assert.equal(mesa.$('acesso-mensagem').textContent, '');
  assert.equal(mesa.$('acesso-login').value, 'caio', 'o que foi digitado continua no formulário');

  const recusada = await abrir({extra: {'contas-criar': () => { throw falha('operacao_proibida', 'Neste serviço, as contas novas são criadas por quem o administra.'); }}});
  recusada.mesa.$('acesso-papel').value = 'admin';
  recusada.mesa.$('acesso-nome').value = 'Caio Reis'; recusada.mesa.$('acesso-login').value = 'caio';
  recusada.mesa.$('acesso-form').dispatchEvent(new Evento('submit', {bubbles: true, cancelable: true})); await recusada.mesa.esperar(6);
  assert.equal(dialogo(recusada.mesa), null, 'outra recusa não abre o diálogo da senha');
  assert.ok(recusada.mesa.$('acesso-mensagem').textContent.includes('contas novas'));
});

test('Alterar apurações (contas-atualizar): sem exigência segue direto; com senha_necessaria abre o diálogo e reenvia', async () => {
  const {mesa, chamadas} = await abrir({exigem: ['contas-atualizar']});
  botaoDa(mesa, 'bia', 'Alterar apurações').click(); await mesa.esperar(2);
  const formulario = linha(mesa, 'bia').querySelector('form');
  formulario.dispatchEvent(new Evento('submit', {bubbles: true, cancelable: true})); await mesa.esperar(4);
  assert.ok(campo(mesa), 'o diálogo da senha abre quando o servidor pede');
  digitar(campo(mesa), 'senha-certa'); botoes(mesa)[1].click(); await mesa.esperar(6);
  const envios = chamadas('contas-atualizar').map(p => p.dados);
  assert.equal(envios.length, 2); assert.equal(envios[0].senha, undefined); assert.equal(envios[1].senha, 'senha-certa');
  assert.equal(envios[1].id, 'c2');
});

test('a senha não aparece na tela nem fica guardada depois do pedido', async () => {
  const {mesa} = await abrir();
  botaoDa(mesa, 'bia', 'Recuperar acesso').click(); await mesa.esperar(3);
  digitar(campo(mesa), 'senha-certa'); botoes(mesa)[1].click(); await mesa.esperar(6);
  assert.ok(!mesa.doc.body.textContent.includes('senha-certa'));
  assert.ok(![...mesa.guardado.values()].some(valor => String(valor).includes('senha-certa')));
});
