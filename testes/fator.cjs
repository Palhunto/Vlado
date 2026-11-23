'use strict';
// O segundo fator em Minha conta (E4a; docs/design/componentes.md#segundo-fator): a linha em Entrada e segurança, o cadastro em três passos com o código QR, trocar de aparelho, gerar novos
// códigos e remover (só com a capacidade). O código de reserva tem 19 caracteres (ABCD-EFGH-JKLM-NPQR) e a Mesa mostra o que o servidor manda, sem limitar o formato.
const test = require('node:test');
const assert = require('node:assert/strict');
const {abrir, esperar, texto, digitar, botaoPorTexto, dialogo, dados, tecla, recusa, contaVer, sessaoDe} = require('./contas_apoio.cjs');

const estado = mesa => mesa.doc.querySelector('.conta-estado');
const seguranca = mesa => mesa.doc.querySelector('[data-cartao="seguranca"]');
const SEMENTE = 'JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP';
const OTPAUTH = `otpauth://totp/Vlado:ana?secret=${SEMENTE}&issuer=Vlado&digits=6&period=30`;
const CODIGOS = Array.from({length: 10}, (_, i) => `ABCD-EFGH-JKL${i}-NPQR`);
const fatorLigado = (extra = {}) => ({ativo: true, ativado_em: new Date(Date.now() - 10 * 86400000).toISOString(), codigos_restantes: 8, ...extra});
const comFator = fator => op => (op === 'conta-ver' ? {...contaVer('dono'), segundo_fator: fator} : undefined);
const comRemocao = papel => ({...sessaoDe(papel), capacidades: [...sessaoDe(papel).capacidades, 'conta-fator-remover']});
const botaoDoDialogo = (mesa, rotulo) => botaoPorTexto(dialogo(mesa), rotulo);
const campos = mesa => [...dialogo(mesa).querySelectorAll('input')];
async function abrirMinhaConta(opcoes = {}) {
  const f = abrir(opcoes);
  await esperar(f.mesa);
  f.mesa.executar('vendor/qrcodegen/qrcodegen.js');  // o carregamento sob demanda (o servidor publica o arquivo) é trocado pela carga direta, sem rede
  return f;
}

test('a linha: desligado mostra o texto, "Cadastrar" e, sem a capacidade de remover, o aviso de que não se remove no papel; não diz que o fator é obrigatório', async () => {
  const {mesa} = await abrirMinhaConta();
  const linha = seguranca(mesa).querySelector('.conta-fator');
  const conteudo = texto(linha);
  assert.ok(conteudo.includes('○ Segundo fator desligado') && conteudo.includes('Um código do aplicativo autenticador, além da senha, na entrada.'));
  assert.ok(conteudo.includes('Depois de cadastrado, o segundo fator não pode ser removido no seu papel.'));
  assert.ok(!/obrigat/i.test(texto(seguranca(mesa))), 'a tela não diz que é obrigatório (B1 da Coruja)');
  assert.deepEqual([...linha.querySelectorAll('button')].map(b => b.textContent), ['Cadastrar']); assert.ok(linha.querySelector('button').className.includes('secondary'));
  const livre = await abrirMinhaConta({sessao: comRemocao('reporter'), papel: 'reporter'});
  assert.ok(!texto(seguranca(livre.mesa)).includes('não pode ser removido no seu papel'), 'com a capacidade, sem o aviso');
});

test('a linha: ligado mostra "✓ Código do autenticador ativo", desde quando e quantos códigos; Gerar e Trocar (secundários); Remover (destrutivo) só com a capacidade', async () => {
  const {mesa} = await abrirMinhaConta({api: comFator(fatorLigado())});
  const linha = seguranca(mesa).querySelector('.conta-fator');
  assert.ok(texto(linha).includes('✓ Código do autenticador ativo') && texto(linha).includes('8 códigos de reserva'));
  assert.ok(texto(linha).includes(`desde ${mesa.janela.Conta.dia(fatorLigado().ativado_em)}`));
  assert.deepEqual([...linha.querySelectorAll('button')].map(b => b.textContent), ['Gerar novos códigos', 'Trocar de aparelho']);
  assert.ok([...linha.querySelectorAll('button')].every(b => b.className.includes('secondary')));
  const com = await abrirMinhaConta({api: comFator(fatorLigado()), sessao: comRemocao('reporter'), papel: 'reporter'});
  const botoes = [...seguranca(com.mesa).querySelectorAll('.conta-fator button')];
  assert.deepEqual(botoes.map(b => b.textContent), ['Gerar novos códigos', 'Trocar de aparelho', 'Remover']); assert.ok(botoes[2].className.includes('danger'));
  const um = await abrirMinhaConta({api: comFator(fatorLigado({codigos_restantes: 1}))});
  assert.ok(texto(seguranca(um.mesa)).includes('1 código de reserva'));
});

test('com 3 códigos ou menos a linha avisa em cores de aviso: "! Restam 2 códigos de reserva. Gere novos."', async () => {
  for (const [restantes, frase] of [[3, '! Restam 3 códigos de reserva. Gere novos.'], [2, '! Restam 2 códigos de reserva. Gere novos.'], [1, '! Resta 1 código de reserva. Gere novos.'], [0, '! Não restam códigos de reserva. Gere novos.']]) {
    const {mesa} = await abrirMinhaConta({api: comFator(fatorLigado({codigos_restantes: restantes}))});
    const aviso = seguranca(mesa).querySelector('.conta-fator-aviso');
    assert.equal(texto(aviso), frase);
  }
  const bom = await abrirMinhaConta({api: comFator(fatorLigado({codigos_restantes: 4}))});
  assert.ok(seguranca(bom.mesa).querySelector('.conta-fator-aviso') === null, 'com 4 ou mais, sem aviso');
});

// --- o cadastro em três passos ---
async function comecar(f, rotulo = 'Cadastrar') {
  botaoPorTexto(seguranca(f.mesa), rotulo).click(); await esperar(f.mesa);
}
async function passoUm(f, senha = 'minha-senha') {
  digitar(campos(f.mesa)[0], senha); botaoDoDialogo(f.mesa, 'Continuar').click(); await esperar(f.mesa);
}
const respostaDoInicio = {segredo: SEMENTE, otpauth: OTPAUTH};

test('passo 1: rubrica "PASSO 1 DE 3", a senha com Mostrar, "Continuar" que espera a senha; o servidor recebe só a senha; a senha não fica na tela', async () => {
  const f = await abrirMinhaConta({api: op => (op === 'conta-fator-iniciar' ? respostaDoInicio : undefined)});
  await comecar(f);
  const caixa = dialogo(f.mesa);
  assert.equal(caixa.querySelector('.dialogo-titulo').textContent, 'Cadastrar o segundo fator'); assert.equal(caixa.querySelector('.dialogo-acoes').hidden, true, 'o diálogo não tem botões próprios');
  assert.equal(texto(caixa.querySelector('.fator-rubrica')), 'PASSO 1 DE 3'); assert.ok(texto(caixa).includes('Confirme a sua senha para começar.'));
  const [senha] = campos(f.mesa);
  assert.equal(senha.type, 'password'); assert.equal(senha.autocomplete, 'current-password'); assert.ok(f.mesa.doc.activeElement === senha);
  assert.ok(botaoDoDialogo(f.mesa, 'Continuar').disabled);
  botaoDoDialogo(f.mesa, 'Mostrar').click(); assert.equal(senha.type, 'text'); botaoDoDialogo(f.mesa, 'Ocultar').click(); assert.equal(senha.type, 'password');
  await passoUm(f);
  assert.deepEqual(dados(f.mesa.chamadas.find(c => c.operacao === 'conta-fator-iniciar').dados), {senha: 'minha-senha'});
  assert.ok(!f.mesa.doc.body.textContent.includes('minha-senha'), 'a senha não fica na página');
  assert.equal(texto(dialogo(f.mesa).querySelector('.fator-rubrica')), 'PASSO 2 DE 3');
});

test('passo 1: senha incorreta vai ao campo; o bloqueio deixa a ação indisponível com o texto da senha', async () => {
  let resposta = recusa('senha_atual_incorreta', 'Senha incorreta.', 'proibido');
  const f = await abrirMinhaConta({api: op => (op === 'conta-fator-iniciar' ? resposta : undefined)});
  await comecar(f); await passoUm(f, 'errada');
  assert.equal(texto(dialogo(f.mesa).querySelector('.fator-erro:not([hidden])')), 'Senha incorreta. Confira e tente de novo.');
  assert.equal(campos(f.mesa)[0].value, '', 'a senha errada sai do campo'); assert.ok(f.mesa.doc.activeElement === campos(f.mesa)[0]);
  resposta = recusa('bloqueado', 'Muitas tentativas.', 'bloqueado');
  await passoUm(f, 'outra');
  assert.ok(texto(dialogo(f.mesa).querySelector('.fator-erro[role="alert"]:not([hidden])')).startsWith('Muitas senhas erradas seguidas.')); assert.ok(botaoDoDialogo(f.mesa, 'Continuar').disabled);
});

test('passo 2: o código QR (SVG, role=img), a chave em grupos de 4 com Copiar, o campo de 6 dígitos (numérico, one-time-code, foco) e o apoio dos 15 minutos', async () => {
  const f = await abrirMinhaConta({api: op => (op === 'conta-fator-iniciar' ? respostaDoInicio : undefined)});
  const copiados = [];
  f.mesa.janela.navigator.clipboard.writeText = async valor => { copiados.push(valor); };
  await comecar(f); await passoUm(f);
  const caixa = dialogo(f.mesa);
  assert.ok(texto(caixa).includes('Abra o aplicativo autenticador do celular e leia o código abaixo. Se não puder ler, digite a chave.'));
  const svg = caixa.querySelector('svg.fator-qr');
  assert.ok(svg && svg.getAttribute('role') === 'img' && svg.getAttribute('aria-label').startsWith('Código QR para o aplicativo autenticador'));
  assert.equal(texto(caixa.querySelector('.fator-chave-rotulo')), 'Chave');
  assert.equal(texto(caixa.querySelector('.fator-chave')), 'JBSW Y3DP EHPK 3PXP JBSW Y3DP EHPK 3PXP'); assert.equal(caixa.querySelector('.fator-chave').getAttribute('translate'), 'no');
  botaoDoDialogo(f.mesa, 'Copiar chave').click(); await esperar(f.mesa);
  assert.deepEqual(copiados, [SEMENTE], 'copia a chave sem os espaços'); assert.ok(texto(caixa).includes('Chave copiada.'));
  const [codigo] = campos(f.mesa);
  assert.equal(codigo.getAttribute('inputmode'), 'numeric'); assert.equal(codigo.autocomplete, 'one-time-code'); assert.equal(codigo.maxLength, 6); assert.ok(f.mesa.doc.activeElement === codigo);
  assert.ok(texto(caixa).includes('Este cadastro vale por 15 minutos. Depois, comece de novo.'));
  assert.ok(botaoDoDialogo(f.mesa, 'Confirmar').disabled, 'sem o código a ação espera');
  assert.ok(botaoDoDialogo(f.mesa, 'Cancelar'), 'até o passo 2 dá para cancelar');
});

test('passo 2: código incorreto no campo; bloqueio com o texto dos códigos; cadastro vencido volta ao passo 1 com o aviso; a chave não é guardada em lugar nenhum', async () => {
  let resposta = recusa('codigo_invalido', 'Código incorreto.', 'proibido');
  const f = await abrirMinhaConta({api: op => (op === 'conta-fator-iniciar' ? respostaDoInicio : op === 'conta-fator-confirmar' ? resposta : undefined)});
  await comecar(f); await passoUm(f);
  digitar(campos(f.mesa)[0], '123 456'); botaoDoDialogo(f.mesa, 'Confirmar').click(); await esperar(f.mesa);
  assert.deepEqual(dados(f.mesa.chamadas.find(c => c.operacao === 'conta-fator-confirmar').dados), {codigo: '123456'}, 'espaços saem');
  assert.equal(texto(dialogo(f.mesa).querySelector('.fator-erro:not([hidden])')), 'Código incorreto. Confira no aplicativo e digite o código que aparece agora.');
  assert.ok(f.mesa.doc.activeElement === campos(f.mesa)[0]);
  resposta = recusa('bloqueado', 'Muitas tentativas.', 'bloqueado');
  botaoDoDialogo(f.mesa, 'Confirmar').click(); await esperar(f.mesa);
  assert.ok(texto(dialogo(f.mesa).querySelector('.fator-erro[role="alert"]:not([hidden])')).startsWith('Muitos códigos errados seguidos. Por 15 minutos')); assert.ok(botaoDoDialogo(f.mesa, 'Confirmar').disabled);
  const vencido = await abrirMinhaConta({api: op => (op === 'conta-fator-iniciar' ? respostaDoInicio : op === 'conta-fator-confirmar' ? recusa('requisicao_invalida', 'Comece de novo o cadastro do segundo fator.') : undefined)});
  await comecar(vencido); await passoUm(vencido);
  digitar(campos(vencido.mesa)[0], '123456'); botaoDoDialogo(vencido.mesa, 'Confirmar').click(); await esperar(vencido.mesa);
  assert.equal(texto(dialogo(vencido.mesa).querySelector('.fator-rubrica')), 'PASSO 1 DE 3'); assert.ok(texto(dialogo(vencido.mesa)).includes('Comece de novo o cadastro do segundo fator.'));
  assert.ok(![...f.mesa.guardado.values()].some(v => v.includes(SEMENTE)), 'a chave não vai para localStorage');
});

test('passo 3: os dez códigos de reserva (19 caracteres, como o servidor manda), Copiar, Baixar e "Já guardei"; Esc não fecha e não há Cancelar; ao fechar, "✓ Segundo fator ativado."', async () => {
  let ativo = false;
  const f = await abrirMinhaConta({api: op => {
    if (op === 'conta-fator-iniciar') return respostaDoInicio;
    if (op === 'conta-fator-confirmar') { ativo = true; return {estado: 'fator_ativado', codigos_de_reserva: CODIGOS}; }
    if (op === 'conta-ver') return {...contaVer('dono'), segundo_fator: ativo ? fatorLigado({codigos_restantes: 10}) : {ativo: false}};
    return undefined;
  }});
  const copiados = [], baixados = [];
  f.mesa.janela.navigator.clipboard.writeText = async valor => { copiados.push(valor); };
  f.mesa.janela.URL.createObjectURL = blob => { baixados.push(blob); return 'blob:teste'; };
  await comecar(f); await passoUm(f);
  digitar(campos(f.mesa)[0], '123456'); botaoDoDialogo(f.mesa, 'Confirmar').click(); await esperar(f.mesa);
  const caixa = dialogo(f.mesa);
  assert.equal(texto(caixa.querySelector('.fator-rubrica')), 'PASSO 3 DE 3'); assert.equal(texto(caixa.querySelector('.fator-titulo')), 'Guarde os códigos de reserva');
  assert.ok(texto(caixa).includes('Cada código entra uma vez, se você perder o celular. Eles não aparecem de novo.'));
  const itens = [...caixa.querySelectorAll('.fator-codigo')];
  assert.equal(itens.length, 10); assert.deepEqual(itens.map(i => texto(i)), CODIGOS); assert.ok(itens.every(i => i.getAttribute('translate') === 'no' && texto(i).length === 19));
  assert.ok(botaoPorTexto(caixa.querySelector('.dialogo-corpo'), 'Cancelar') === undefined && caixa.querySelector('.dialogo-acoes').hidden, 'sem Cancelar nem botões do diálogo');
  tecla(caixa, 'Escape'); await esperar(f.mesa);
  assert.ok(dialogo(f.mesa), 'Esc não fecha: os códigos não voltam');
  botaoDoDialogo(f.mesa, 'Copiar').click(); await esperar(f.mesa);
  assert.deepEqual(copiados, [CODIGOS.join('\n')]);
  botaoDoDialogo(f.mesa, 'Baixar').click(); await esperar(f.mesa);
  assert.equal(baixados.length, 1); assert.equal(await baixados[0].text(), `${CODIGOS.join('\n')}\n`, 'um arquivo de texto gerado no navegador, um código por linha');
  assert.ok(texto(dialogo(f.mesa)).includes('Arquivo baixado.'));
  botaoDoDialogo(f.mesa, 'Já guardei').click(); await esperar(f.mesa);
  assert.ok(dialogo(f.mesa) === null);
  assert.equal(texto(estado(f.mesa)), '✓ Segundo fator ativado.');
  assert.ok(!f.mesa.doc.body.textContent.includes(CODIGOS[0]), 'os códigos somem da página ao fechar');
  assert.ok(texto(seguranca(f.mesa)).includes('✓ Código do autenticador ativo'), 'a linha passa a mostrar o fator ligado');
});

test('Trocar de aparelho: o passo 1 também pede o "Código do aparelho atual" (aplicativo ou reserva) e diz que o atual vale até o novo ser confirmado; em branco é recusado antes de enviar', async () => {
  let resposta = respostaDoInicio;
  const f = await abrirMinhaConta({api: op => (op === 'conta-fator-iniciar' ? resposta : comFator(fatorLigado())(op))});
  await comecar(f, 'Trocar de aparelho');
  const caixa = dialogo(f.mesa);
  assert.equal(caixa.querySelector('.dialogo-titulo').textContent, 'Trocar de aparelho'); assert.ok(texto(caixa).includes('O aparelho atual vale até o novo ser confirmado.'));
  const [senha, atual] = campos(f.mesa);
  assert.equal(atual.autocomplete, 'one-time-code'); assert.ok(texto(caixa).includes('Código do aparelho atual'));
  assert.ok(atual.getAttribute('inputmode') === null, 'aceita também o código de reserva: sem teclado só numérico'); assert.ok(atual.maxLength >= 19, 'cabe o código de reserva de 19 caracteres');
  digitar(senha, 'minha-senha'); botaoDoDialogo(f.mesa, 'Continuar').click(); await esperar(f.mesa);
  assert.ok(texto(caixa.querySelector('.fator-erro:not([hidden])')).startsWith('Falta o código do aparelho atual.'));
  assert.equal(f.mesa.chamadas.filter(c => c.operacao === 'conta-fator-iniciar').length, 0);
  digitar(atual, 'ABCD-EFGH-JKLM-NPQR'); botaoDoDialogo(f.mesa, 'Continuar').click(); await esperar(f.mesa);
  assert.deepEqual(dados(f.mesa.chamadas.find(c => c.operacao === 'conta-fator-iniciar').dados), {senha: 'minha-senha', codigo: 'ABCD-EFGH-JKLM-NPQR'});
  assert.equal(texto(dialogo(f.mesa).querySelector('.fator-rubrica')), 'PASSO 2 DE 3');
  botaoDoDialogo(f.mesa, 'Cancelar').click(); await esperar(f.mesa);
  assert.ok(dialogo(f.mesa) === null, 'cancelar fecha e nada muda');
});

test('Trocar de aparelho: código do aparelho atual incorreto vai ao campo do código', async () => {
  const f = await abrirMinhaConta({api: op => (op === 'conta-fator-iniciar' ? recusa('codigo_invalido', 'Código incorreto.', 'proibido') : comFator(fatorLigado())(op))});
  await comecar(f, 'Trocar de aparelho');
  const [senha, atual] = campos(f.mesa);
  digitar(senha, 'minha-senha'); digitar(atual, '000000'); botaoDoDialogo(f.mesa, 'Continuar').click(); await esperar(f.mesa);
  assert.equal(texto(dialogo(f.mesa).querySelector('.fator-erro:not([hidden])')), 'Código incorreto. Confira no aplicativo e digite o código que aparece agora.');
});

test('Gerar novos códigos: senha e "Código do aplicativo"; sem o código recusa antes de enviar; código errado no campo; a resposta abre o passo dos códigos, que só "Já guardei" fecha', async () => {
  let ok = false;
  const f = await abrirMinhaConta({api: (op, d) => {
    if (op === 'conta-fator-codigos') return ok ? {estado: 'codigos_gerados', codigos_de_reserva: CODIGOS} : recusa('codigo_invalido', 'Código incorreto.', 'proibido');
    return comFator(fatorLigado())(op);
  }});
  botaoPorTexto(seguranca(f.mesa), 'Gerar novos códigos').click(); await esperar(f.mesa);
  const caixa = dialogo(f.mesa);
  assert.equal(caixa.querySelector('.dialogo-titulo').textContent, 'Gerar novos códigos de reserva?'); assert.ok(texto(caixa).includes('Os códigos atuais param de valer.'));
  assert.equal(botaoDoDialogo(f.mesa, 'Gerar códigos').textContent, 'Gerar códigos');
  const [codigo, senha] = campos(f.mesa);
  assert.ok(texto(caixa).includes('Código do aplicativo')); assert.equal(codigo.autocomplete, 'one-time-code'); assert.equal(senha.type, 'password');
  digitar(senha, 'minha-senha'); botaoDoDialogo(f.mesa, 'Gerar códigos').click(); await esperar(f.mesa);
  assert.ok(texto(caixa.querySelector('.campo-erro')).startsWith('Falta o código.')); assert.equal(f.mesa.chamadas.filter(c => c.operacao === 'conta-fator-codigos').length, 0);
  digitar(codigo, '000000'); botaoDoDialogo(f.mesa, 'Gerar códigos').click(); await esperar(f.mesa);
  assert.equal(texto(caixa.querySelector('.campo-erro')), 'Código incorreto. Confira no aplicativo e digite o código que aparece agora.');
  ok = true; digitar(senha, 'minha-senha'); botaoDoDialogo(f.mesa, 'Gerar códigos').click(); await esperar(f.mesa);
  assert.deepEqual(dados(f.mesa.chamadas.filter(c => c.operacao === 'conta-fator-codigos').at(-1).dados), {senha: 'minha-senha', codigo: '000000'});
  assert.equal(texto(dialogo(f.mesa).querySelector('.dialogo-titulo')), 'Guarde os códigos de reserva'); assert.equal([...dialogo(f.mesa).querySelectorAll('.fator-codigo')].length, 10);
  tecla(dialogo(f.mesa), 'Escape'); await esperar(f.mesa);
  assert.ok(dialogo(f.mesa), 'Esc não fecha');
  assert.deepEqual([...dialogo(f.mesa).querySelectorAll('.dialogo-acoes button')].filter(b => !b.hidden).map(b => b.textContent), ['Já guardei']);
  botaoDoDialogo(f.mesa, 'Já guardei').click(); await esperar(f.mesa);
  assert.ok(dialogo(f.mesa) === null); assert.equal(texto(estado(f.mesa)), '✓ Novos códigos de reserva gerados.');
});

test('Remover: só com a capacidade; variante com senha destrutiva ("Remover segundo fator"); resultado "✓ Segundo fator removido."', async () => {
  let removido = false;
  const f = await abrirMinhaConta({sessao: comRemocao('reporter'), papel: 'reporter', api: (op, d) => {
    if (op === 'conta-fator-remover') { removido = true; return {estado: 'fator_removido'}; }
    return comFator(removido ? {ativo: false} : fatorLigado())(op);
  }});
  botaoPorTexto(seguranca(f.mesa), 'Remover').click(); await esperar(f.mesa);
  const caixa = dialogo(f.mesa);
  assert.equal(caixa.querySelector('.dialogo-titulo').textContent, 'Remover o segundo fator?'); assert.equal(caixa.dataset.variante, 'destrutivo');
  assert.ok(texto(caixa).includes('A entrada volta a pedir só a senha. Você pode cadastrar de novo quando quiser.'));
  assert.equal(botaoDoDialogo(f.mesa, 'Remover segundo fator').textContent, 'Remover segundo fator');
  digitar(campos(f.mesa)[0], 'minha-senha'); botaoDoDialogo(f.mesa, 'Remover segundo fator').click(); await esperar(f.mesa);
  assert.deepEqual(dados(f.mesa.chamadas.find(c => c.operacao === 'conta-fator-remover').dados), {senha: 'minha-senha'});
  assert.equal(texto(estado(f.mesa)), '✓ Segundo fator removido.');
  assert.ok(texto(seguranca(f.mesa)).includes('○ Segundo fator desligado'));
});

test('em inglês: a linha, o passo 1, o QR e os códigos saem em inglês', async () => {
  const f = await abrirMinhaConta({idioma: 'en', api: op => (op === 'conta-fator-iniciar' ? respostaDoInicio : undefined)});
  await esperar(f.mesa);
  assert.ok(texto(seguranca(f.mesa)).includes('○ Second factor off'));
  botaoPorTexto(seguranca(f.mesa), 'Set up').click(); await esperar(f.mesa);
  assert.equal(texto(dialogo(f.mesa).querySelector('.fator-rubrica')), 'STEP 1 OF 3'); assert.ok(texto(dialogo(f.mesa)).includes('Confirm your password to start.'));
  digitar(campos(f.mesa)[0], 'x'); botaoDoDialogo(f.mesa, 'Continue').click(); await esperar(f.mesa);
  assert.ok(texto(dialogo(f.mesa)).includes('Open the authenticator app on your phone and scan the code below.'));
  assert.ok(dialogo(f.mesa).querySelector('svg.fator-qr').getAttribute('aria-label').startsWith('QR code for the authenticator app'));
});

// --- a página da pendência (/conta/segundo-fator): o mesmo cadastro, no cartão do Entrar, sem diálogo ---
const {criarMesa} = require('./dom_minimo.cjs');
function paginaDaPendencia({api = () => undefined, chamar} = {}) {
  const sair = [], abrir = [];
  const mesa = criarMesa({scripts: ['fator.js'], api: (op, d) => { const r = api(op, d); if (r instanceof Error) throw r; return r ?? {}; }});
  mesa.executar('vendor/qrcodegen/qrcodegen.js');
  const alvo = mesa.doc.createElement('div'); mesa.doc.body.append(alvo);
  mesa.janela.Fator.pagina(alvo, {chamar: chamar || ((op, d) => mesa.janela.fetch(`/api/${op}`, {method: 'POST', body: JSON.stringify(d)}).then(async r => { const j = await r.json(); if (!r.ok) throw Object.assign(new Error(j.erro), {result: j}); return j; })),
    sair: () => sair.push(1), abrirMesa: () => abrir.push(1)});
  return {mesa, alvo, sair, abrir};
}

test('a página da pendência: rubrica, título, texto, os passos no próprio cartão (sem Cancelar) e "Sair" no pé', async () => {
  const p = paginaDaPendencia({api: op => (op === 'conta-fator-iniciar' ? respostaDoInicio : undefined)});
  assert.equal(texto(p.alvo.querySelector('.fator-rubrica-pagina')), 'ANTES DE CONTINUAR'); assert.equal(texto(p.alvo.querySelector('h1')), 'Proteja a conta com um segundo passo');
  assert.ok(texto(p.alvo).includes('Para quem é dono ou editor, o Vlado pede, além da senha, um código do aplicativo autenticador. Cadastre agora para abrir a Mesa.'));
  assert.equal(texto(p.alvo.querySelector('.fator-rubrica')), 'PASSO 1 DE 3'); assert.ok(botaoPorTexto(p.alvo, 'Cancelar') === undefined, 'a pendência não se cancela: só Sair');
  assert.ok(p.mesa.doc.querySelector('dialog.dialogo') === null, 'sem diálogo: o cadastro é do próprio cartão');
  assert.ok(botaoPorTexto(p.alvo.querySelector('.fator-rodape'), 'Sair'));
  assert.ok(!/nome|papel/i.test(texto(p.alvo.querySelector('.fator-rodape'))), 'o texto não leva nome nem papel');
});

test('a página da pendência: os três passos até "Abrir a Mesa", que leva à Mesa; "Sair" chama sessao-sair e a saída', async () => {
  const p = paginaDaPendencia({api: op => (op === 'conta-fator-iniciar' ? respostaDoInicio : op === 'conta-fator-confirmar' ? {estado: 'fator_ativado', codigos_de_reserva: CODIGOS} : undefined)});
  const em = (rotulo, raiz = p.alvo) => botaoPorTexto(raiz, rotulo);
  const campo = () => p.alvo.querySelector('input');
  digitar(campo(), 'minha-senha'); em('Continuar').click(); await esperar(p.mesa);
  assert.equal(texto(p.alvo.querySelector('.fator-rubrica')), 'PASSO 2 DE 3'); assert.ok(p.alvo.querySelector('svg.fator-qr'));
  digitar(campo(), '123456'); em('Confirmar').click(); await esperar(p.mesa);
  assert.equal(texto(p.alvo.querySelector('.fator-rubrica')), 'PASSO 3 DE 3'); assert.equal(p.alvo.querySelectorAll('.fator-codigo').length, 10);
  em('Já guardei').click(); await esperar(p.mesa);
  assert.ok(texto(p.alvo).includes('Segundo fator ativado.')); assert.ok(!p.mesa.doc.body.textContent.includes(CODIGOS[0]), 'os códigos somem');
  em('Abrir a Mesa').click(); assert.equal(p.abrir.length, 1);
  const q = paginaDaPendencia();
  botaoPorTexto(q.alvo.querySelector('.fator-rodape'), 'Sair').click(); await esperar(q.mesa);
  assert.ok(q.mesa.chamadas.some(c => c.operacao === 'sessao-sair')); assert.equal(q.sair.length, 1);
});

test('Fator.chamadorDaSessao: lê o token CSRF de GET /api/sessao e o manda em X-Session-Token, com a sessão aberta (cookie); sem sessão, sessao_expirada', async () => {
  const pedidos = [];
  const mesa = criarMesa({scripts: ['fator.js'], preparar: janela => {
    janela.fetch = async (endereco, opcoes = {}) => { pedidos.push({endereco, opcoes}); return endereco === '/api/sessao' ? {ok: true, json: async () => ({csrf: 'token-da-sessao'})} : {ok: true, json: async () => ({estado: 'ok'})}; };
  }});
  const chamar = mesa.janela.Fator.chamadorDaSessao();
  assert.deepEqual(dados(await chamar('conta-fator-iniciar', {senha: 'x'})), {estado: 'ok'});
  await chamar('conta-fator-confirmar', {codigo: '123456'});
  assert.equal(pedidos.filter(p => p.endereco === '/api/sessao').length, 1, 'o token é lido uma vez');
  const post = pedidos.find(p => p.endereco === '/api/conta-fator-iniciar');
  assert.equal(post.opcoes.headers['X-Session-Token'], 'token-da-sessao'); assert.equal(post.opcoes.credentials, 'same-origin'); assert.equal(post.opcoes.method, 'POST');
  const sem = criarMesa({scripts: ['fator.js'], preparar: janela => { janela.fetch = async () => ({ok: false, json: async () => ({})}); }});
  await assert.rejects(sem.janela.Fator.chamadorDaSessao()('conta-fator-iniciar', {}), erro => erro.result.codigo === 'sessao_expirada');
});

test('a Mesa volta à página da pendência quando uma operação responde 403 pendencia_de_conta (e não entra em laço dentro dela)', async () => {
  const trocas = [];
  const mesa = criarMesa({scripts: require('./contas_apoio.cjs').SCRIPTS, modo: 'piloto', api: op => (op === 'conta-ver' ? recusa('pendencia_de_conta', 'Há uma pendência.', 'proibido') : undefined),
    preparar: janela => { janela.location.replace = destino => trocas.push(destino); }});
  await esperar(mesa);
  mesa.janela.fetch = async () => ({ok: false, json: async () => ({estado: 'proibido', codigo: 'pendencia_de_conta', pendencias: ['segundo_fator'], erro: 'Há uma pendência.'})});
  await assert.rejects(mesa.avaliar("api('inventario', {caso: 'x'})"));
  assert.deepEqual(trocas, ['/conta/segundo-fator']);
});
