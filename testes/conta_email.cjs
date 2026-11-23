'use strict';
// Trocar o próprio e-mail em Minha conta (E3; docs/design/componentes.md#minha-conta): o botão à direita da linha do e-mail (ou "Cadastrar e-mail" na conta migrada), o diálogo com
// senha e o campo "E-mail novo", os erros antes do envio, a resposta única e o link só com o transporte `tela`.
const test = require('node:test');
const assert = require('node:assert/strict');
const {abrir, esperar, texto, digitar, botaoPorTexto, dialogo, dados, recusa, contaVer} = require('./contas_apoio.cjs');

const estado = mesa => mesa.doc.querySelector('.conta-estado');
const acoes = mesa => [...dialogo(mesa).querySelectorAll('.dialogo-acoes button')];
const perfil = mesa => mesa.doc.querySelector('[data-cartao="perfil"]');
const campos = mesa => ({email: dialogo(mesa).querySelector('input[type="email"]'), senha: dialogo(mesa).querySelector('input[type="password"]')});
async function abrirDialogo(opcoes = {}) {
  const f = abrir(opcoes);
  await esperar(f.mesa);
  botaoPorTexto(perfil(f.mesa), opcoes.rotulo || 'Trocar e-mail').click(); await esperar(f.mesa);
  return f;
}

test('"Trocar e-mail" (secundário) fica à direita da linha do e-mail; na conta migrada sem e-mail o botão é "Cadastrar e-mail"', async () => {
  const f = abrir(); await esperar(f.mesa);
  const botao = botaoPorTexto(perfil(f.mesa), 'Trocar e-mail');
  assert.ok(botao && botao.className.includes('secondary'));
  assert.ok(botao.closest('.conta-linha').textContent.includes('ana@redacaoserena.org') || botao.closest('.conta-linha').textContent.includes('ana@redacao.org'), 'na mesma linha do e-mail');
  const migrada = abrir({api: op => (op === 'conta-ver' ? contaVer('dono', {email: null, login: 'ana.lima'}) : undefined)}); await esperar(migrada.mesa);
  assert.equal(botaoPorTexto(perfil(migrada.mesa), 'Trocar e-mail'), undefined); assert.ok(botaoPorTexto(perfil(migrada.mesa), 'Cadastrar e-mail'));
});

test('o diálogo: título, texto, E-mail novo (email, autocomplete=email, foco) e Sua senha; a ação "Enviar confirmação" espera a senha', async () => {
  const f = await abrirDialogo();
  const caixa = dialogo(f.mesa), c = campos(f.mesa);
  assert.equal(caixa.querySelector('.dialogo-titulo').textContent, 'Trocar o e-mail da conta');
  assert.ok(texto(caixa).includes('Enviamos um link ao e-mail novo. O e-mail atual continua valendo, inclusive para entrar, até você abrir o link.'));
  assert.equal(c.email.autocomplete, 'email'); assert.ok(f.mesa.doc.activeElement === c.email, 'o foco inicial é o e-mail novo');
  assert.equal(c.senha.autocomplete, 'current-password'); assert.ok(texto(caixa).includes('E-mail novo') && texto(caixa).includes('Sua senha'));
  assert.equal(acoes(f.mesa)[1].textContent, 'Enviar confirmação'); assert.ok(acoes(f.mesa)[1].disabled, 'sem a senha a ação espera');
  acoes(f.mesa)[0].click(); await esperar(f.mesa);
});

test('antes do envio: em branco e sem a forma de endereço são recusados junto ao campo, sem enviar nada', async () => {
  const f = await abrirDialogo();
  const c = campos(f.mesa);
  digitar(c.senha, 'minha-senha'); acoes(f.mesa)[1].click(); await esperar(f.mesa);
  assert.equal(texto(dialogo(f.mesa).querySelector('.campo-erro')), 'Falta o e-mail novo. Escreva o endereço que quer usar.');
  digitar(c.email, 'ana-sem-arroba'); acoes(f.mesa)[1].click(); await esperar(f.mesa);
  assert.equal(texto(dialogo(f.mesa).querySelector('.campo-erro')), 'E-mail inválido. Confira o endereço, por exemplo ana@redacao.org.');
  assert.equal(f.mesa.chamadas.filter(x => x.operacao === 'conta-email-trocar').length, 0); assert.equal(c.senha.value, 'minha-senha', 'a validação local não leva a senha embora');
  acoes(f.mesa)[0].click(); await esperar(f.mesa);
});

test('envio: manda email e senha; a resposta única fecha o diálogo e a linha de estado diz "Confirmação enviada ao e-mail novo. Abra o link em até 60 minutos."', async () => {
  const f = await abrirDialogo({api: op => (op === 'conta-email-trocar' ? {estado: 'confirmacao_enviada'} : undefined)});
  const c = campos(f.mesa);
  digitar(c.email, '  nova@redacao.org '); digitar(c.senha, 'minha-senha'); acoes(f.mesa)[1].click(); await esperar(f.mesa);
  assert.deepEqual(dados(f.mesa.chamadas.find(x => x.operacao === 'conta-email-trocar').dados), {email: 'nova@redacao.org', senha: 'minha-senha'});
  assert.equal(dialogo(f.mesa), null);
  assert.equal(texto(estado(f.mesa)), '✓ Confirmação enviada ao e-mail novo. Abra o link em até 60 minutos.');
  assert.ok(!texto(estado(f.mesa)).includes('nova@redacao.org'), 'a tela não repete o endereço: não conta se ele já tem conta');
});

test('com o transporte `tela` a resposta traz o link e o diálogo o mostra como no convite (uma vez, Copiar link, Já enviei, sem Cancelar); o link sai da página ao fechar', async () => {
  const LINK = 'http://127.0.0.1:8765/confirmar-email/' + 'm'.repeat(43);
  const f = await abrirDialogo({api: op => (op === 'conta-email-trocar' ? {estado: 'confirmacao_enviada', link: LINK} : undefined)});
  const c = campos(f.mesa);
  digitar(c.email, 'nova@redacao.org'); digitar(c.senha, 'minha-senha'); acoes(f.mesa)[1].click(); await esperar(f.mesa);
  const caixa = dialogo(f.mesa);
  assert.ok(caixa, 'o diálogo segue aberto'); assert.equal(caixa.querySelector('.dialogo-titulo').textContent, 'Confirme o e-mail nova@redacao.org');
  assert.equal(caixa.querySelector('.convite-link').value, LINK); assert.deepEqual(acoes(f.mesa).filter(b => !b.hidden).map(b => b.textContent), ['Já enviei']);
  acoes(f.mesa)[1].click(); await esperar(f.mesa);
  assert.equal(dialogo(f.mesa), null); assert.ok(!f.mesa.doc.body.textContent.includes('m'.repeat(43)));
});

test('senha incorreta vai ao campo da senha; bloqueio deixa só Cancelar; um pedido a cada 5 minutos fica no erro do diálogo', async () => {
  let resposta = recusa('senha_atual_incorreta', 'Senha incorreta.', 'proibido');
  const f = await abrirDialogo({api: op => (op === 'conta-email-trocar' ? resposta : undefined)});
  const c = campos(f.mesa);
  digitar(c.email, 'nova@redacao.org'); digitar(c.senha, 'errada'); acoes(f.mesa)[1].click(); await esperar(f.mesa);
  assert.equal(texto(dialogo(f.mesa).querySelector('.dialogo-erro-campo')), 'Senha incorreta. Confira e tente de novo.'); assert.equal(c.email.value, 'nova@redacao.org', 'o e-mail fica');
  resposta = recusa('requisicao_invalida', 'Você pediu essa troca há pouco. Espere alguns minutos para pedir de novo.');
  digitar(c.senha, 'certa'); acoes(f.mesa)[1].click(); await esperar(f.mesa);
  assert.equal(texto(dialogo(f.mesa).querySelector('.dialogo-erro[role="alert"]')), 'Você pediu essa troca há pouco. Espere alguns minutos para pedir de novo.');
  resposta = recusa('bloqueado', 'Muitas tentativas.', 'bloqueado');
  digitar(c.senha, 'x'); acoes(f.mesa)[1].click(); await esperar(f.mesa);
  assert.ok(texto(dialogo(f.mesa).querySelector('.dialogo-erro[role="alert"]')).startsWith('Muitas senhas erradas seguidas.')); assert.ok(acoes(f.mesa)[1].disabled);
  acoes(f.mesa)[0].click(); await esperar(f.mesa);
});

test('em inglês: botão, diálogo e linha de estado saem em inglês', async () => {
  const f = abrir({idioma: 'en', api: op => (op === 'conta-email-trocar' ? {estado: 'confirmacao_enviada'} : undefined)}); await esperar(f.mesa);
  botaoPorTexto(perfil(f.mesa), 'Change email').click(); await esperar(f.mesa);
  assert.equal(dialogo(f.mesa).querySelector('.dialogo-titulo').textContent, 'Change the account email');
  assert.ok(texto(dialogo(f.mesa)).includes('We send a link to the new email. The current email stays valid, including for signing in, until you open the link.') && texto(dialogo(f.mesa)).includes('New email'));
  assert.equal(acoes(f.mesa)[1].textContent, 'Send confirmation');
  const c = campos(f.mesa);
  digitar(c.email, 'nova@redacao.org'); digitar(c.senha, 'x'); acoes(f.mesa)[1].click(); await esperar(f.mesa);
  assert.equal(texto(estado(f.mesa)), '✓ Confirmation sent to the new email. Open the link within 60 minutes.');
});
