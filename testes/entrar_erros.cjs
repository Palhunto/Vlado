'use strict';
// Erros de preenchimento da página de entrada junto ao campo (W11 regra 5, via Estados.erroCampo): mensagem depois do campo (fora do <label>),
// aria-invalid, aria-describedby e foco; some ao digitar; a resposta do servidor segue na caixa de aviso, que não diz qual campo errou.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {criarMesa, Evento} = require('./dom_minimo.cjs');

const HTML = fs.readFileSync(path.join(__dirname, '..', 'interface', 'entrar.html'), 'utf8');

async function abrir({url = 'http://127.0.0.1:8765/entrar', idioma = 'pt', api} = {}) {
  const resposta = (status, corpo) => { const erro = new Error(corpo.erro || 'erro'); erro.result = corpo; return erro; };
  const mesa = criarMesa({html: HTML, url, armazenamento: {'vlado-idioma': idioma}, scripts: ['estados.js', 'entrar.js'],
    api: api || (operacao => { throw resposta(401, {erro: 'sem sessao'}); })});
  await mesa.esperar(8);
  return mesa;
}
const enviar = async (mesa, form) => { mesa.$(form).dispatchEvent(new Evento('submit', {bubbles: true, cancelable: true})); await mesa.esperar(8); };
const avisos = mesa => [...mesa.doc.querySelectorAll('.campo-erro')];

test('entrar sem login: o erro vai para o campo do login, com o texto do login, aria-invalid, aria-describedby e foco, e fora do <label>', async () => {
  const mesa = await abrir();
  mesa.$('entrar-senha').value = 'alguma-senha-longa';
  await enviar(mesa, 'entrar-form');
  const campo = mesa.$('entrar-login'), [aviso] = avisos(mesa);
  assert.equal(avisos(mesa).length, 1);
  assert.equal(aviso.textContent, 'Falta o login. Use o login da sua conta.');
  assert.equal(campo.getAttribute('aria-invalid'), 'true');
  assert.ok((campo.getAttribute('aria-describedby') || '').split(/\s+/).includes(aviso.id));
  assert.ok(!campo.closest('label').contains(aviso), 'a mensagem não entra no nome do campo');
  assert.ok(mesa.doc.activeElement === campo, 'o foco vai para o campo');
  assert.equal(mesa.$('entrar-mensagem').hidden, true, 'a caixa de aviso fica escondida');
});

test('com login e sem senha o erro vai para a senha, com o texto da senha (nunca "login e senha"); digitar tira o erro e o aria-invalid', async () => {
  const mesa = await abrir();
  mesa.$('entrar-login').value = 'ana';
  await enviar(mesa, 'entrar-form');
  const senha = mesa.$('entrar-senha');
  assert.equal(senha.getAttribute('aria-invalid'), 'true');
  assert.equal(avisos(mesa).length, 1);
  assert.equal(avisos(mesa)[0].textContent, 'Falta a senha. Use a senha da sua conta.');
  assert.equal(mesa.$('entrar-login').getAttribute('aria-invalid'), null);
  senha.value = 'x'; senha.dispatchEvent(new Evento('input', {bubbles: true}));
  assert.equal(avisos(mesa).length, 0);
  assert.equal(senha.getAttribute('aria-invalid'), null);
  assert.equal(senha.getAttribute('aria-describedby'), null);
});

test('o erro junto ao campo troca de idioma sem voltar depois de a pessoa digitar', async () => {
  const mesa = await abrir();
  await enviar(mesa, 'entrar-form');
  assert.equal(avisos(mesa)[0].textContent, 'Falta o login. Use o login da sua conta.', 'com os dois em branco, a mensagem vai no login');
  assert.equal(mesa.$('entrar-login').getAttribute('aria-invalid'), 'true');
  assert.equal(mesa.$('entrar-senha').getAttribute('aria-invalid'), null);
  mesa.$('entrar-idioma').click(); await mesa.esperar(4);
  assert.equal(avisos(mesa).length, 1, 'continua um só aviso');
  assert.equal(avisos(mesa)[0].textContent, 'The login is missing. Use the login of your account.');
  const campo = mesa.$('entrar-login');
  campo.value = 'a'; campo.dispatchEvent(new Evento('input', {bubbles: true}));
  mesa.$('entrar-idioma').click(); await mesa.esperar(4);
  assert.equal(avisos(mesa).length, 0, 'o erro que a pessoa já resolveu não volta');
});

test('resposta do servidor (senha errada) segue na caixa de aviso, sem marcar campo', async () => {
  const mesa = await abrir({api: operacao => {
    if (operacao === 'sessao') { const e = new Error('sem sessao'); e.result = {erro: 'sem sessao'}; throw e; }
    const e = new Error('credenciais'); e.result = {codigo: 'credenciais', erro: 'x'}; throw e;
  }});
  mesa.$('entrar-login').value = 'ana'; mesa.$('entrar-senha').value = 'senha-errada-qualquer';
  await enviar(mesa, 'entrar-form');
  assert.equal(avisos(mesa).length, 0);
  assert.equal(mesa.$('entrar-mensagem').hidden, false);
  assert.equal(mesa.$('entrar-mensagem').textContent, 'Login ou senha incorretos.');
  assert.equal(mesa.$('entrar-login').getAttribute('aria-invalid'), null);
});

test('primeiro acesso: um texto por campo (nome em branco, login fora da regra, senha curta, confirmação diferente)', async () => {
  const mesa = await abrir({url: 'http://127.0.0.1:8765/primeiro-acesso'});
  await enviar(mesa, 'primeiro-form');
  assert.equal(mesa.$('primeiro-nome').getAttribute('aria-invalid'), 'true');
  assert.equal(avisos(mesa)[0].textContent, 'Falta o nome. Escreva o seu nome.');
  mesa.$('primeiro-nome').value = 'Ana Souza'; mesa.$('primeiro-login').value = '!!';
  await enviar(mesa, 'primeiro-form');
  assert.equal(mesa.$('primeiro-login').getAttribute('aria-invalid'), 'true');
  assert.equal(avisos(mesa)[0].textContent, 'Login inválido. Use de 3 a 64 caracteres: letras minúsculas, números, ponto, hífen ou sublinhado, começando por letra ou número.');
  mesa.$('primeiro-login').value = 'ana.souza'; mesa.$('primeiro-senha').value = 'curta';
  await enviar(mesa, 'primeiro-form');
  assert.equal(avisos(mesa).length, 1, 'o erro anterior sai quando aparece outro');
  assert.equal(mesa.$('primeiro-senha').getAttribute('aria-invalid'), 'true');
  assert.equal(mesa.$('primeiro-login').getAttribute('aria-invalid'), null);
  assert.equal(avisos(mesa)[0].textContent, 'A senha deve ter de 12 a 256 caracteres.');
  mesa.$('primeiro-senha').value = 'uma-senha-bem-longa'; mesa.$('primeiro-confirmar').value = 'outra-senha-bem-longa';
  await enviar(mesa, 'primeiro-form');
  assert.equal(mesa.$('primeiro-confirmar').getAttribute('aria-invalid'), 'true');
  assert.equal(avisos(mesa)[0].textContent, 'As duas senhas não coincidem. Digite a mesma senha nos dois campos.');
});

test('a mensagem de campo fica a 4 px do campo: a folha desconta o intervalo do formulário (regra de .campo-erro)', () => {
  const css = fs.readFileSync(path.join(__dirname, '..', 'interface', 'entrar.css'), 'utf8');
  assert.match(css, /\.entrar-cartao form\{[^}]*--entrar-intervalo:18px[^}]*gap:var\(--entrar-intervalo\)/);
  assert.match(css, /\.entrar-cartao form>\.campo-erro\{margin-top:calc\(var\(--espaco-1\) - var\(--entrar-intervalo\)\)\}/);
  assert.doesNotMatch(css, /\.entrar-senha-linha\{flex-direction:column\}/, 'no celular o botão Mostrar não empurra a mensagem para longe da senha');
});
