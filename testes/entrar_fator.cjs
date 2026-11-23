'use strict';
// Segundo fator no Entrar (docs/design/componentes.md#entrar-fator; servidor: test_fator_contas.py): o passo 2 depois da senha certa (código do aplicativo ou de reserva), as respostas de
// cada código, e o código pedido na redefinição da senha quando a conta tem o fator. DOM sintético (dom_minimo); test_entrar_fator_navegador.py repete o roteiro contra o servidor.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {criarMesa, Evento} = require('./dom_minimo.cjs');

const HTML = fs.readFileSync(path.join(__dirname, '..', 'interface', 'entrar.html'), 'utf8');
const TOKEN = 'T'.repeat(43);
const recusa = (codigo, erro, estado = 'erro') => Object.assign(new Error(erro), {result: {estado, codigo, erro}});
const STATUS = {erro: 400, bloqueado: 429, indisponivel: 503, credenciais: 401, proibido: 403};

async function abrir({url = 'http://127.0.0.1:8765/entrar', idioma = 'pt', api = () => undefined} = {}) {
  const pedidos = [], destinos = [];
  const mesa = criarMesa({html: HTML, url, armazenamento: {'vlado-idioma': idioma}, scripts: ['estados.js', 'entrar.js'],
    preparar: janela => {
      janela.location.replace = destino => destinos.push(destino);
      janela.location.assign = destino => destinos.push(destino);
      const original = janela.fetch;
      janela.fetch = async (endereco, opcoes) => {
        const resposta = await original(endereco, opcoes);
        resposta.status = resposta.ok ? 200 : STATUS[(await resposta.json()).estado] || 400;
        return resposta;
      };
    },
    api: (operacao, dados) => {
      pedidos.push({operacao, dados: {...dados}});
      const propria = api(operacao, dados);
      if (propria !== undefined) { if (propria instanceof Error) throw propria; return propria; }
      if (operacao === 'sessao') throw recusa('sem_sessao', 'sem sessão');
      return {};
    }});
  await mesa.esperar(10);
  return {mesa, pedidos, destinos, chamadas: operacao => pedidos.filter(p => p.operacao === operacao)};
}
const digitar = (entrada, texto) => { entrada.value = texto; entrada.dispatchEvent(new Evento('input', {bubbles: true})); };
const enviar = async (mesa, id) => { mesa.$(id).dispatchEvent(new Evento('submit', {bubbles: true, cancelable: true})); await mesa.esperar(10); };
const avisos = mesa => [...mesa.doc.querySelectorAll('.campo-erro')];
const visivel = (mesa, id) => !mesa.$(id).hidden;
const DESTINO = '/?area=codex&caso=alfa';

// o servidor: a senha certa de uma conta com o fator responde só `segundo_fator`
const comFator = (resposta2 = {conta: {id: 'x'}, csrf: 'c', destino: DESTINO}) => (operacao, dados) => {
  if (operacao === 'entrar') return {estado: 'segundo_fator'};
  if (operacao === 'entrar-segundo-fator') return typeof resposta2 === 'function' ? resposta2(dados) : resposta2;
  return undefined;
};
async function ate2(opcoes = {}) {
  const abrirOpcoes = {api: comFator(opcoes.resposta), idioma: opcoes.idioma};
  const aberto = await abrir(abrirOpcoes);
  digitar(aberto.mesa.$('entrar-login'), 'ana@redacao.org'); digitar(aberto.mesa.$('entrar-senha'), 'uma senha certa e longa');
  await enviar(aberto.mesa, 'entrar-form');
  return aberto;
}

test('senha certa de conta com o fator: o cartão troca para o passo 2, sem entrar, com a senha limpa e o foco no código', async () => {
  const {mesa, destinos, chamadas} = await ate2();
  assert.deepEqual(mesa.erros, []);
  assert.equal(visivel(mesa, 'fator-secao'), true); assert.equal(visivel(mesa, 'entrar-secao'), false);
  assert.deepEqual(destinos, [], 'ainda não há sessão: a página não sai');
  assert.deepEqual(chamadas('entrar').map(p => p.dados), [{login: 'ana@redacao.org', senha: 'uma senha certa e longa', cliente: 'web'}]);
  assert.equal(mesa.$('entrar-senha').value, '', 'a senha não fica na tela');
  assert.equal(mesa.$('fator-titulo').textContent, 'Confirme que é você');
  assert.equal(mesa.$('fator-texto').textContent, 'Digite o código de 6 dígitos do aplicativo autenticador.');
  assert.equal(mesa.$('fator-rotulo').textContent, 'Código do aplicativo');
  const campo = mesa.$('fator-codigo');
  assert.equal(campo.getAttribute('inputmode'), 'numeric'); assert.equal(campo.getAttribute('autocomplete'), 'one-time-code');
  assert.ok(mesa.doc.activeElement === campo, 'o foco vai para o campo');
  assert.equal(mesa.$('fator-reserva').textContent, 'Usar um código de reserva');
  assert.match(mesa.$('fator-form').textContent, /Você tem 5 minutos para digitar o código\./);
  assert.equal(mesa.$('fator-enviar').textContent, 'Entrar'); assert.equal(mesa.$('fator-outra').textContent, 'Entrar com outra conta');
  assert.equal(visivel(mesa, 'entrar-teste'), false, 'o aviso de teste é só da entrada');
});

test('o código do aplicativo vai a entrar-segundo-fator e a página segue para o destino', async () => {
  const {mesa, destinos, chamadas} = await ate2();
  await enviar(mesa, 'fator-form');
  assert.equal(avisos(mesa)[0].textContent, 'Falta o código. Digite o código do aplicativo.'); assert.equal(chamadas('entrar-segundo-fator').length, 0);
  digitar(mesa.$('fator-codigo'), '  123456 ');
  await enviar(mesa, 'fator-form');
  assert.deepEqual(chamadas('entrar-segundo-fator').map(p => p.dados), [{codigo: '123456'}]);
  assert.deepEqual(destinos, [DESTINO]);
});

test('"Usar um código de reserva" troca o rótulo, o texto, o inputmode e o link, e aceita espaço, hífen e minúsculas; "Usar o código do aplicativo" volta', async () => {
  const {mesa, chamadas, destinos} = await ate2();
  mesa.$('fator-reserva').click(); await mesa.esperar(3);
  assert.equal(mesa.$('fator-rotulo').textContent, 'Código de reserva'); assert.equal(mesa.$('fator-codigo').getAttribute('inputmode'), 'text');
  assert.equal(mesa.$('fator-texto').textContent, 'Digite um dos códigos de reserva que você guardou. Cada um vale uma vez.');
  assert.equal(mesa.$('fator-reserva').textContent, 'Usar o código do aplicativo');
  assert.ok(mesa.doc.activeElement === mesa.$('fator-codigo'));
  digitar(mesa.$('fator-codigo'), ' abcd-efgh-jklm-npqr ');
  await enviar(mesa, 'fator-form');
  assert.deepEqual(chamadas('entrar-segundo-fator').map(p => p.dados), [{codigo: 'abcd-efgh-jklm-npqr'}], 'vai como a pessoa digitou (sem as bordas); o servidor normaliza');
  assert.deepEqual(destinos, [DESTINO]);
  const outra = await ate2();
  outra.mesa.$('fator-reserva').click(); await outra.mesa.esperar(2); outra.mesa.$('fator-reserva').click(); await outra.mesa.esperar(2);
  assert.equal(outra.mesa.$('fator-rotulo').textContent, 'Código do aplicativo'); assert.equal(outra.mesa.$('fator-codigo').getAttribute('inputmode'), 'numeric');
  assert.equal(outra.mesa.$('fator-reserva').textContent, 'Usar um código de reserva');
});

test('código errado: erro no campo (do aplicativo ou de reserva), o campo limpo e a entrada continua no passo 2', async () => {
  const errado = recusa('codigo_invalido', 'Código inválido.', 'proibido');
  const {mesa, destinos} = await ate2({resposta: () => errado});
  digitar(mesa.$('fator-codigo'), '000000');
  await enviar(mesa, 'fator-form');
  assert.equal(avisos(mesa)[0].textContent, 'Código incorreto. Confira no aplicativo e tente de novo.');
  assert.equal(mesa.$('fator-codigo').getAttribute('aria-invalid'), 'true'); assert.equal(mesa.$('fator-codigo').value, '');
  assert.equal(visivel(mesa, 'fator-secao'), true); assert.deepEqual(destinos, []); assert.equal(mesa.$('fator-enviar').disabled, false);
  mesa.$('fator-reserva').click(); digitar(mesa.$('fator-codigo'), 'ABCD-EFGH');
  await enviar(mesa, 'fator-form');
  assert.equal(avisos(mesa)[0].textContent, 'Código incorreto. Confira o código de reserva e tente de novo.');
});

test('a entrada expirou (cinco minutos ou cinco códigos errados): volta ao login com o aviso, sem a senha', async () => {
  const {mesa} = await ate2({resposta: () => recusa('entrada_expirada', 'A entrada expirou.', 'credenciais')});
  digitar(mesa.$('fator-codigo'), '123456');
  await enviar(mesa, 'fator-form');
  assert.equal(visivel(mesa, 'entrar-secao'), true); assert.equal(visivel(mesa, 'fator-secao'), false);
  assert.equal(mesa.$('entrar-mensagem').textContent, 'A entrada expirou. Digite o login e a senha de novo.');
  assert.equal(mesa.$('entrar-senha').value, ''); assert.equal(mesa.$('fator-codigo').value, '');
  assert.ok(mesa.doc.activeElement === mesa.$('entrar-login'));
  assert.equal(visivel(mesa, 'entrar-teste'), true);
});

test('429 e 503: caixa de aviso; "Entrar com outra conta" volta ao formulário', async () => {
  const bloqueado = await ate2({resposta: () => recusa('bloqueado', 'Muitas tentativas.', 'bloqueado')});
  digitar(bloqueado.mesa.$('fator-codigo'), '123456');
  await enviar(bloqueado.mesa, 'fator-form');
  assert.equal(bloqueado.mesa.$('entrar-mensagem').textContent, 'Muitas tentativas. Aguarde alguns minutos e tente de novo.');
  const fora = await ate2({resposta: () => recusa('fator_indisponivel', 'O código do aplicativo não pode ser conferido neste servidor agora.', 'indisponivel')});
  digitar(fora.mesa.$('fator-codigo'), '123456');
  await enviar(fora.mesa, 'fator-form');
  assert.equal(fora.mesa.$('entrar-mensagem').hidden, false);
  fora.mesa.$('fator-outra').click(); await fora.mesa.esperar(3);
  assert.equal(visivel(fora.mesa, 'entrar-secao'), true); assert.equal(visivel(fora.mesa, 'fator-secao'), false);
  assert.equal(fora.mesa.$('entrar-login').value, 'ana@redacao.org', 'o login continua; a senha não');
  assert.equal(fora.mesa.$('entrar-senha').value, '');
});

test('o passo 2 em inglês', async () => {
  const {mesa} = await ate2({idioma: 'en'});
  assert.equal(mesa.$('fator-titulo').textContent, 'Confirm it is you');
  assert.equal(mesa.$('fator-rotulo').textContent, 'App code');
  mesa.$('fator-reserva').click(); await mesa.esperar(2);
  assert.equal(mesa.$('fator-rotulo').textContent, 'Reserve code'); assert.equal(mesa.$('fator-reserva').textContent, 'Use the app code');
});

// --- Redefinir a senha com segundo fator --------------------------------------------------------------------------------------------------------
const URL_REDEFINIR = `http://127.0.0.1:8765/redefinir/${TOKEN}`;
test('redefinir: a conta com o fator responde 403 sem código; a senha fica no campo, aparece o código com o texto e o foco, e a ação reenvia com o código', async () => {
  const {mesa, chamadas} = await abrir({url: URL_REDEFINIR, api: (operacao, dados) => {
    if (operacao !== 'senha-redefinir') return undefined;
    if (!dados.codigo) return recusa('fator_necessario', 'Digite o código do aplicativo.', 'proibido');
    if (dados.codigo !== '123456') return recusa('codigo_invalido', 'Código inválido.', 'proibido');
    return {estado: 'senha_redefinida'};
  }});
  assert.equal(visivel(mesa, 'redefinir-codigo-campo'), false);
  digitar(mesa.$('redefinir-senha'), 'uma senha nova e longa');
  await enviar(mesa, 'redefinir-form');
  assert.deepEqual(chamadas('senha-redefinir').map(p => p.dados), [{token: TOKEN, senha: 'uma senha nova e longa'}]);
  assert.equal(visivel(mesa, 'redefinir-codigo-campo'), true);
  assert.equal(mesa.$('redefinir-senha').value, 'uma senha nova e longa', 'a senha continua no campo');
  assert.match(mesa.$('redefinir-codigo-campo').textContent, /Esta conta tem segundo fator\. Digite o código do aplicativo ou um código de reserva\./);
  assert.equal(mesa.$('redefinir-codigo-campo').querySelector('span').textContent, 'Código do aplicativo ou de reserva');
  assert.ok(mesa.doc.activeElement === mesa.$('redefinir-codigo'), 'o foco vai para o campo novo');
  assert.equal(visivel(mesa, 'redefinir-form'), true, 'ainda não é a tela de sucesso');
  await enviar(mesa, 'redefinir-form');
  assert.equal(avisos(mesa)[0].textContent, 'Falta o código. Digite o código do aplicativo ou um código de reserva.'); assert.equal(chamadas('senha-redefinir').length, 1);
  digitar(mesa.$('redefinir-codigo'), '999999');
  await enviar(mesa, 'redefinir-form');
  assert.equal(avisos(mesa)[0].textContent, 'Código incorreto. Confira e tente de novo.'); assert.equal(mesa.$('redefinir-codigo').getAttribute('aria-invalid'), 'true');
  digitar(mesa.$('redefinir-codigo'), ' 123456 ');
  await enviar(mesa, 'redefinir-form');
  assert.deepEqual(chamadas('senha-redefinir').at(-1).dados, {token: TOKEN, senha: 'uma senha nova e longa', codigo: '123456'});
  assert.equal(visivel(mesa, 'redefinir-pronto'), true); assert.equal(mesa.$('redefinir-titulo').textContent, 'Senha nova salva');
});

test('redefinir: sem segundo fator o campo do código nunca aparece; o codigo_invalido sem código enviado (forma da especificação) também o pede', async () => {
  const sem = await abrir({url: URL_REDEFINIR, api: operacao => (operacao === 'senha-redefinir' ? {estado: 'senha_redefinida'} : undefined)});
  digitar(sem.mesa.$('redefinir-senha'), 'uma senha nova e longa');
  await enviar(sem.mesa, 'redefinir-form');
  assert.equal(visivel(sem.mesa, 'redefinir-codigo-campo'), false); assert.equal(visivel(sem.mesa, 'redefinir-pronto'), true);
  const spec = await abrir({url: URL_REDEFINIR, api: operacao => (operacao === 'senha-redefinir' ? recusa('codigo_invalido', 'Código inválido.', 'proibido') : undefined)});
  digitar(spec.mesa.$('redefinir-senha'), 'uma senha nova e longa');
  await enviar(spec.mesa, 'redefinir-form');
  assert.equal(visivel(spec.mesa, 'redefinir-codigo-campo'), true);
});
