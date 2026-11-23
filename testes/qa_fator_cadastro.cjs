'use strict';
// O cadastro do segundo fator em Minha conta, num navegador de verdade contra o servidor de verdade (test_fator_cadastro_navegador.py o chama).
// Uso: node qa_fator_cadastro.cjs '<json>'   com {porta, origem, senha, reporter: {login}, dono: {login}, capturas?}. Sem argumento não faz nada.
// O código do aplicativo é calculado aqui (RFC 6238: HMAC-SHA1, passo de 30 s, 6 dígitos) a partir da chave que a própria tela mostra, como faria uma pessoa com o celular.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');

if (!process.argv[2]) process.exit(0);
const args = JSON.parse(process.argv[2]);
const {chromium} = require(path.join(__dirname, '..', '.ferramentas', 'node', 'node_modules', 'playwright'));

function totp(segredo, desvio = 0) {
  const alfabeto = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
  let bits = '';
  for (const c of segredo.replace(/=+$/, '')) bits += alfabeto.indexOf(c).toString(2).padStart(5, '0');
  const bytes = Buffer.from(bits.match(/.{8}/g).map(b => parseInt(b, 2)));
  const passo = Math.floor(Date.now() / 1000 / 30) + desvio;
  const contador = Buffer.alloc(8); contador.writeBigUInt64BE(BigInt(passo));
  const h = crypto.createHmac('sha1', bytes).update(contador).digest();
  const o = h[19] & 0xf;
  return String(((h[o] & 0x7f) << 24 | h[o + 1] << 16 | h[o + 2] << 8 | h[o + 3]) % 1000000).padStart(6, '0');
}
const texto = async (page, seletor) => (await page.textContent(seletor)).replace(/\s+/g, ' ').trim();
const DIALOGO = 'dialog.dialogo[open]';
const FORMA_DO_CODIGO = /^[A-Z0-9]{4}(-[A-Z0-9]{4}){3}$/;  // 19 caracteres: ABCD-EFGH-JKLM-NPQR

// Entrar de outro navegador, só pela API: a senha (que deve pedir o segundo passo) e o código de reserva. Devolve o que o servidor respondeu a cada passo.
async function entrarComReserva(browser, login, codigo) {
  const ctx = await contexto(browser), page = await ctx.newPage();
  try {
    await page.goto(`${args.origem}/entrar`);
    return await page.evaluate(async ({login, senha, codigo}) => {
      const enviar = async (caminho, corpo) => fetch(`/api/${caminho}`, {method: 'POST', credentials: 'same-origin', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(corpo)});
      const primeira = await enviar('entrar', {login, senha}), corpo = await primeira.json();
      if (corpo.estado !== 'segundo_fator') return {aposASenha: corpo.estado, status: null};
      const segunda = await enviar('entrar-segundo-fator', {codigo});
      return {aposASenha: corpo.estado, status: segunda.status};
    }, {login, senha: args.senha, codigo});
  } finally { await ctx.close(); }
}
async function contexto(browser) {
  const ctx = await browser.newContext({viewport: {width: 1440, height: 900}, locale: 'pt-BR', acceptDownloads: true});
  await ctx.addInitScript(() => { try { localStorage.setItem('vlado-idioma', 'pt'); localStorage.setItem('apuracao:tema', 'light'); } catch (_) { /* sem armazenamento */ } });
  // O servidor fala HTTP e se apresenta como a origem https (o Origin e o Host que ele confere).
  await ctx.route(`${args.origem}/**`, async rota => { try {
    const pedido = rota.request(), endereco = new URL(pedido.url());
    const resposta = await rota.fetch({url: `http://127.0.0.1:${args.porta}${endereco.pathname}${endereco.search}`, headers: {...pedido.headers(), host: new URL(args.origem).host}, maxRedirects: 0});
    await rota.fulfill({response: resposta});
  } catch (_) { /* a página fechou com o pedido em voo */ } });
  return ctx;
}
// `codigo`: um código de reserva, para a conta que já tem o segundo fator (a dona: no piloto ele é obrigatório para dono e editor, e o cenário a cadastra). O segundo passo vai pela API,
// como a página do Entrar faz, com o bilhete que o servidor põe no cookie.
async function entrar(page, login, codigo) {
  await page.goto(`${args.origem}/entrar`);
  if (codigo) {
    const resultado = await page.evaluate(async ({login, senha, codigo}) => {
      const enviar = async (caminho, corpo) => fetch(`/api/${caminho}`, {method: 'POST', credentials: 'same-origin', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(corpo)});
      let resposta = await enviar('entrar', {login, senha}), corpo = await resposta.json();
      const aposASenha = corpo.estado;
      if (aposASenha === 'segundo_fator') { resposta = await enviar('entrar-segundo-fator', {codigo}); corpo = await resposta.json(); }
      return {aposASenha, status: resposta.status, estado: corpo.estado};
    }, {login, senha: args.senha, codigo});
    assert.equal(resultado.aposASenha, 'segundo_fator', `a senha sozinha não abre a sessão de quem tem o fator: ${JSON.stringify(resultado)}`);  // V2 da Coruja
    assert.equal(resultado.status, 200, JSON.stringify(resultado));
  } else {
    await page.fill('#entrar-login', login); await page.fill('#entrar-senha', args.senha);
    await Promise.all([page.waitForURL(url => url.pathname === '/' || url.pathname === '/index.html', {timeout: 20000}), page.click('#entrar-enviar')]);
  }
  await page.goto(`${args.origem}/?area=configuracoes`);
  await page.waitForSelector('[data-cartao="seguranca"] .conta-fator', {timeout: 20000});
}
// Tudo que não pode ficar na página nem no armazenamento do navegador depois que o diálogo fecha.
async function semRastro(page, segredos) {
  const html = await page.content();
  const guardado = await page.evaluate(() => JSON.stringify([Object.entries(localStorage), Object.entries(sessionStorage)]));
  for (const segredo of segredos) {
    assert.ok(!html.includes(segredo), `${segredo.slice(0, 6)}… não está na página`);
    assert.ok(!guardado.includes(segredo), `${segredo.slice(0, 6)}… não está no armazenamento`);
  }
}
// O cadastro inteiro pela tela. Devolve {segredo, codigos}.
async function cadastrar(page, erros) {
  await page.click('.conta-fator-cadastrar');
  await page.waitForSelector(`${DIALOGO} input[type="password"]`);
  assert.equal(await texto(page, `${DIALOGO} .fator-rubrica`), 'PASSO 1 DE 3');
  assert.ok(await page.isDisabled(`${DIALOGO} .fator-principal`), 'a ação espera a senha');
  // senha errada: o erro vai ao campo, a chave não foi dada
  await page.fill(`${DIALOGO} input[type="password"]`, 'senha-errada-de-teste');
  await page.click(`${DIALOGO} .fator-principal`);
  await page.waitForSelector(`${DIALOGO} .fator-erro:not([hidden])`);
  assert.ok((await texto(page, `${DIALOGO} .fator-erro:not([hidden])`)).startsWith('Senha incorreta'));
  assert.equal(await page.inputValue(`${DIALOGO} input[type="password"]`), '', 'a senha errada sai do campo');
  // senha certa: o passo 2, com o QR e a chave
  await page.fill(`${DIALOGO} input[type="password"]`, args.senha);
  await page.click(`${DIALOGO} .fator-principal`);
  await page.waitForSelector(`${DIALOGO} svg.fator-qr`, {timeout: 20000});
  assert.equal(await texto(page, `${DIALOGO} .fator-rubrica`), 'PASSO 2 DE 3');
  assert.ok(!(await page.content()).includes(args.senha), 'a senha não fica na página');
  const segredo = (await texto(page, `${DIALOGO} .fator-chave`)).replace(/\s+/g, '');
  assert.match(segredo, /^[A-Z2-7]{32}$/);
  const lado = await page.evaluate(() => { const r = document.querySelector('dialog.dialogo[open] svg.fator-qr').getBoundingClientRect(); return [r.width, r.height]; });
  assert.ok(lado[0] > 100 && lado[0] <= 200 && lado[0] === lado[1], `o QR desenhado tem ${lado} px`);
  // código errado no campo; o certo passa
  await page.fill(`${DIALOGO} input[type="text"]`, '000000');
  await page.click(`${DIALOGO} .fator-principal`);
  await page.waitForSelector(`${DIALOGO} .fator-erro:not([hidden])`);
  assert.equal(await texto(page, `${DIALOGO} .fator-erro:not([hidden])`), 'Código incorreto. Confira no aplicativo e digite o código que aparece agora.');
  await page.fill(`${DIALOGO} input[type="text"]`, totp(segredo));
  await page.click(`${DIALOGO} .fator-principal`);
  await page.waitForSelector(`${DIALOGO} .fator-codigos`, {timeout: 20000});
  assert.equal(await texto(page, `${DIALOGO} .fator-rubrica`), 'PASSO 3 DE 3');
  const codigos = await page.locator(`${DIALOGO} .fator-codigo`).allTextContents();
  assert.equal(codigos.length, 10); assert.equal(new Set(codigos).size, 10);
  for (const codigo of codigos) { assert.equal(codigo.length, 19); assert.match(codigo, FORMA_DO_CODIGO); }
  // Esc não fecha; não há Cancelar
  await page.keyboard.press('Escape');
  assert.ok(await page.isVisible(DIALOGO), 'Esc não fecha o passo dos códigos');
  assert.equal(await page.locator(`${DIALOGO} .dialogo-corpo button`, {hasText: 'Cancelar'}).count(), 0);
  // Baixar: o arquivo gerado no navegador traz os dez códigos
  const [arquivo] = await Promise.all([page.waitForEvent('download'), page.click(`${DIALOGO} button:has-text("Baixar")`)]);
  assert.equal(arquivo.suggestedFilename(), 'vlado-codigos-de-reserva.txt');
  assert.equal(fs.readFileSync(await arquivo.path(), 'utf8'), `${codigos.join('\n')}\n`);
  // Já guardei fecha; os códigos e a chave somem da página e do armazenamento
  await page.click(`${DIALOGO} .fator-guardei`);
  await page.waitForSelector(DIALOGO, {state: 'detached'});
  await page.waitForFunction(() => /^✓ Segundo fator ativado\./.test(document.querySelector('.conta-estado')?.textContent || ''), null, {timeout: 15000});
  await semRastro(page, [...codigos, segredo]);
  await page.waitForSelector('.conta-fator-ativo', {timeout: 15000});
  assert.ok((await texto(page, '[data-cartao="seguranca"] .conta-fator')).includes('10 códigos de reserva'));
  assert.deepEqual(erros, [], `erros de página: ${erros.join('; ')}`);
  return {segredo, codigos};
}

(async () => {
  const browser = await chromium.launch();
  const resultado = {};
  try {
    // 1. quem pode remover o próprio fator (repórter): cadastra, gera novos códigos e remove
    let ctx = await contexto(browser), page = await ctx.newPage();
    const erros = []; page.on('pageerror', erro => erros.push(erro.message));
    await entrar(page, args.reporter.login);
    assert.ok((await texto(page, '[data-cartao="seguranca"] .conta-fator')).includes('○ Segundo fator desligado'));
    assert.ok(!(await texto(page, '[data-cartao="seguranca"] .conta-fator')).includes('não pode ser removido'), 'o repórter pode remover: sem o aviso');
    const feito = await cadastrar(page, erros);
    resultado.reporter = {segredo: feito.segredo, codigos: feito.codigos};
    // gerar novos códigos: a senha e um código do aplicativo (o do passo seguinte: o do atual já foi gasto no cadastro)
    await page.click('.conta-fator-codigos');
    await page.waitForSelector(`${DIALOGO} input[type="password"]`);
    assert.equal(await texto(page, `${DIALOGO} .dialogo-titulo`), 'Gerar novos códigos de reserva?');
    await page.fill(`${DIALOGO} input[type="text"]`, '000000'); await page.fill(`${DIALOGO} input[type="password"]`, args.senha);
    await page.click(`${DIALOGO} .dialogo-acoes button:last-child`);
    await page.waitForSelector(`${DIALOGO} .campo-erro`);
    assert.equal(await texto(page, `${DIALOGO} .campo-erro`), 'Código incorreto. Confira no aplicativo e digite o código que aparece agora.');
    await page.fill(`${DIALOGO} input[type="text"]`, totp(feito.segredo, 1)); await page.fill(`${DIALOGO} input[type="password"]`, args.senha);
    await page.click(`${DIALOGO} .dialogo-acoes button:last-child`);
    await page.waitForSelector(`${DIALOGO} .fator-codigos`, {timeout: 20000});
    const novos = await page.locator(`${DIALOGO} .fator-codigo`).allTextContents();
    assert.equal(novos.length, 10); assert.ok(novos.every(c => FORMA_DO_CODIGO.test(c))); assert.ok(novos.every(c => !feito.codigos.includes(c)), 'os códigos novos são outros');
    await page.keyboard.press('Escape');
    assert.ok(await page.isVisible(DIALOGO), 'Esc não fecha: só "Já guardei"');
    await page.click(`${DIALOGO} .dialogo-acoes button:last-child`);
    await page.waitForSelector(DIALOGO, {state: 'detached'});
    await semRastro(page, [...novos, ...feito.codigos]);
    resultado.reporter.novos = novos;
    // Os códigos que a tela mostrou são os do servidor e valem uma vez (V3 da Coruja): um dos novos entra, o mesmo não entra de novo, e um dos antigos, que a geração invalidou, também não.
    const primeiraEntrada = await entrarComReserva(browser, args.reporter.login, novos[0]);
    assert.deepEqual(primeiraEntrada, {aposASenha: 'segundo_fator', status: 200}, 'um código de reserva novo, o que a tela mostrou, entra');
    const repetida = await entrarComReserva(browser, args.reporter.login, novos[0]);
    assert.equal(repetida.aposASenha, 'segundo_fator'); assert.ok(repetida.status >= 400, `o mesmo código não entra de novo (${repetida.status})`);
    const antigo = await entrarComReserva(browser, args.reporter.login, feito.codigos[0]);
    assert.equal(antigo.aposASenha, 'segundo_fator'); assert.ok(antigo.status >= 400, `um código anterior à geração dos novos não entra (${antigo.status})`);
    const outro = await entrarComReserva(browser, args.reporter.login, novos[1]);
    assert.deepEqual(outro, {aposASenha: 'segundo_fator', status: 200}, 'e outro dos novos segue valendo');
    resultado.reporter.usados = [novos[0], novos[1]];
    // remover: o repórter tem a capacidade
    assert.ok(await page.isVisible('.conta-fator-remover'), 'o repórter vê Remover');
    await page.click('.conta-fator-remover');
    await page.waitForSelector(`${DIALOGO} input[type="password"]`);
    assert.equal(await texto(page, `${DIALOGO} .dialogo-titulo`), 'Remover o segundo fator?');
    await page.fill(`${DIALOGO} input[type="password"]`, args.senha);
    await page.click(`${DIALOGO} .dialogo-acoes button:last-child`);
    await page.waitForSelector(DIALOGO, {state: 'detached'});
    await page.waitForSelector('.conta-fator-cadastrar', {timeout: 15000});
    assert.equal(await texto(page, '.conta-estado'), '✓ Segundo fator removido.');
    await ctx.close();

    // 2. quem não pode remover (dono): o fator já vem do cenário (no piloto é obrigatório para ele); a tela o mostra ativo, sem Remover, e o servidor recusa o pedido feito à mão
    ctx = await contexto(browser); page = await ctx.newPage(); page.on('pageerror', erro => erros.push(erro.message));
    await entrar(page, args.dono.login, args.dono.codigos[0]);
    await page.waitForSelector('.conta-fator-ativo', {timeout: 20000});
    const linhaDoDono = await texto(page, '[data-cartao="seguranca"] .conta-fator');
    assert.ok(linhaDoDono.includes('✓ Código do autenticador ativo'), linhaDoDono);
    assert.ok(!/obrigat/i.test(await texto(page, '[data-cartao="seguranca"]')), 'a tela não diz que o fator é obrigatório');
    resultado.dono = {};
    assert.equal(await page.locator('.conta-fator-remover').count(), 0, 'o dono não vê Remover');
    const recusa = await page.evaluate(async senha => { try { await api('conta-fator-remover', {senha}); return 'removeu'; } catch (erro) { return {status: erro.result?.estado, codigo: erro.result?.codigo}; } }, args.senha);
    assert.deepEqual(recusa, {status: 'proibido', codigo: 'operacao_proibida'}, 'o servidor recusa o pedido feito à mão: o papel não tem a capacidade');
    await page.reload();
    await page.waitForSelector('.conta-fator-ativo', {timeout: 20000});
    await ctx.close();
  } finally { await browser.close(); }
  console.log(JSON.stringify(resultado));
})().catch(erro => { console.error(erro); process.exit(1); });
