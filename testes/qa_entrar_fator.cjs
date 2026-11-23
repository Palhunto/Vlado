'use strict';
// Segundo fator no Entrar e na redefinição, num navegador de verdade contra o servidor de verdade (test_entrar_fator_navegador.py o chama).
// Uso: node qa_entrar_fator.cjs '<json>' com {porta, origem, senha, app: {email, segredo}, reserva: {email, codigo}, redefinir: {token, segredo, senha_nova}, capturas?}
// O código do aplicativo é calculado aqui (RFC 6238: HMAC-SHA1, passo de 30 s, 6 dígitos). Sem argumento não faz nada.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');

if (!process.argv[2]) process.exit(0);
const args = JSON.parse(process.argv[2]);
const {chromium} = require(path.join(__dirname, '..', '.ferramentas', 'node', 'node_modules', 'playwright'));

// O cadastro do fator já usou o código do passo atual (um código não vale duas vezes): o roteiro usa o do passo seguinte, que o servidor aceita na janela.
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
async function contexto(browser) {
  const ctx = await browser.newContext({viewport: {width: 1440, height: 900}, locale: 'pt-BR'});
  await ctx.addInitScript(() => { try { localStorage.setItem('vlado-idioma', 'pt'); } catch (_) { /* sem armazenamento */ } });
  await ctx.route(`${args.origem}/**`, async rota => { try {
    const pedido = rota.request(), endereco = new URL(pedido.url());
    const resposta = await rota.fetch({url: `http://127.0.0.1:${args.porta}${endereco.pathname}${endereco.search}`, headers: {...pedido.headers(), host: new URL(args.origem).host}, maxRedirects: 0});
    await rota.fulfill({response: resposta});
  } catch (_) { /* a página fechou com o pedido em voo */ } });
  return ctx;
}
async function entrarAte2(page, email, senha) {
  await page.goto(`${args.origem}/entrar`);
  await page.waitForSelector('#entrar-secao:not([hidden])');
  await page.fill('#entrar-login', email); await page.fill('#entrar-senha', senha);
  await page.click('#entrar-enviar');
  await page.waitForSelector('#fator-secao:not([hidden])', {timeout: 15000});
}

(async () => {
  const browser = await chromium.launch();
  const resultado = {};
  try {
    // 1. código do aplicativo: errado (erro no campo, continua no passo 2) e certo (entra)
    let ctx = await contexto(browser), page = await ctx.newPage();
    const erros = []; page.on('pageerror', erro => erros.push(erro.message));
    await entrarAte2(page, args.app.email, args.senha);
    assert.equal(await texto(page, '#fator-titulo'), 'Confirme que é você');
    assert.equal(await page.inputValue('#entrar-senha'), '', 'a senha não fica na tela');
    assert.equal(await page.evaluate(() => document.activeElement.id), 'fator-codigo');
    const sessaoAntes = await page.evaluate(async () => (await fetch('/api/sessao')).status);
    assert.equal(sessaoAntes, 401, 'com o bilhete do segundo passo ainda não há sessão');
    if (args.capturas) { fs.mkdirSync(args.capturas, {recursive: true}); await page.screenshot({path: path.join(args.capturas, 'entrar-fator-1440.png'), fullPage: true}); }
    await page.fill('#fator-codigo', '000000');
    await page.click('#fator-enviar');
    await page.waitForSelector('.campo-erro');
    assert.equal(await texto(page, '.campo-erro'), 'Código incorreto. Confira no aplicativo e tente de novo.');
    await page.fill('#fator-codigo', totp(args.app.segredo, 1));
    await Promise.all([page.waitForURL(url => !['/entrar'].includes(url.pathname), {timeout: 15000}), page.click('#fator-enviar')]).catch(async falha => { throw new Error(`não entrou com o código certo: url ${page.url()}, aviso ${JSON.stringify(await page.textContent('#entrar-mensagem'))}, campo ${JSON.stringify(await page.textContent('.campo-erro').catch(() => null))}; ${falha.message.split('\n')[0]}`); });
    const sessao = await page.evaluate(async () => (await fetch('/api/sessao')).json());
    assert.equal(sessao.conta.email, args.app.email, 'a sessão abriu com o código certo');
    resultado.app = 'ok';
    await ctx.close();

    // 2. código de reserva (com minúsculas e sem hífens como a pessoa os digita) entra uma vez; o mesmo código de novo não entra
    ctx = await contexto(browser); page = await ctx.newPage(); page.on('pageerror', erro => erros.push(erro.message));
    await entrarAte2(page, args.reserva.email, args.senha);
    await page.click('#fator-reserva');
    assert.equal(await texto(page, '#fator-rotulo'), 'Código de reserva');
    await page.fill('#fator-codigo', args.reserva.codigo.toLowerCase());
    await Promise.all([page.waitForURL(url => url.pathname !== '/entrar'), page.click('#fator-enviar')]);
    assert.equal((await page.evaluate(async () => (await fetch('/api/sessao')).json())).conta.email, args.reserva.email);
    await ctx.close();
    ctx = await contexto(browser); page = await ctx.newPage();
    await entrarAte2(page, args.reserva.email, args.senha);
    await page.click('#fator-reserva');
    await page.fill('#fator-codigo', args.reserva.codigo);
    await page.click('#fator-enviar');
    await page.waitForSelector('.campo-erro');
    assert.equal(await texto(page, '.campo-erro'), 'Código incorreto. Confira o código de reserva e tente de novo.', 'o código de reserva vale uma vez');
    await ctx.close();
    resultado.reserva = 'ok';

    // 3. "Entrar com outra conta" volta ao formulário com o login e sem a senha
    ctx = await contexto(browser); page = await ctx.newPage();
    await entrarAte2(page, args.app.email, args.senha);
    await page.click('#fator-outra');
    await page.waitForSelector('#entrar-secao:not([hidden])');
    assert.equal(await page.inputValue('#entrar-login'), args.app.email); assert.equal(await page.inputValue('#entrar-senha'), '');
    await ctx.close();

    // 4. redefinir a senha de conta com segundo fator: a senha, o pedido do código, o código errado e o certo
    ctx = await contexto(browser); page = await ctx.newPage(); page.on('pageerror', erro => erros.push(erro.message));
    await page.goto(`${args.origem}/redefinir/${args.redefinir.token}`);
    await page.waitForSelector('#redefinir-form:not([hidden])');
    await page.fill('#redefinir-senha', args.redefinir.senha_nova);
    await page.click('#redefinir-enviar');
    await page.waitForSelector('#redefinir-codigo-campo:not([hidden])', {timeout: 15000});
    assert.equal(await page.inputValue('#redefinir-senha'), args.redefinir.senha_nova, 'a senha continua no campo');
    assert.equal(await page.evaluate(() => document.activeElement.id), 'redefinir-codigo');
    assert.match(await texto(page, '#redefinir-codigo-campo'), /Esta conta tem segundo fator\./);
    if (args.capturas) await page.screenshot({path: path.join(args.capturas, 'redefinir-fator-1440.png'), fullPage: true});
    await page.fill('#redefinir-codigo', '000000');
    await page.click('#redefinir-enviar');
    await page.waitForSelector('.campo-erro');
    assert.equal(await texto(page, '.campo-erro'), 'Código incorreto. Confira e tente de novo.');
    await page.fill('#redefinir-codigo', totp(args.redefinir.segredo, 1));
    await page.click('#redefinir-enviar');
    await page.waitForSelector('#redefinir-pronto:not([hidden])', {timeout: 15000});
    assert.equal(await texto(page, '#redefinir-titulo'), 'Senha nova salva');
    resultado.redefinir = 'ok';
    assert.deepEqual(erros, []);
    await ctx.close();

    // 4b. a página da pendência (/conta/segundo-fator): o servidor ainda não marca a pendência nem serve o caminho, então o roteiro faz as duas coisas por fora
    // (o caminho serve o entrar.html de verdade; GET /api/sessao ganha `pendencias`) e o resto, a sessão, o token e o início do cadastro, é do servidor de verdade.
    ctx = await contexto(browser); page = await ctx.newPage(); page.on('pageerror', erro => erros.push(erro.message));
    let pendente = false;
    await ctx.route(`${args.origem}/conta/segundo-fator`, async rota => {
      const resposta = await rota.fetch({url: `http://127.0.0.1:${args.porta}/entrar`, headers: {...rota.request().headers(), host: new URL(args.origem).host}});
      await rota.fulfill({response: resposta});
    });
    await ctx.route(`${args.origem}/api/sessao`, async rota => {
      const resposta = await rota.fetch({url: `http://127.0.0.1:${args.porta}/api/sessao`, headers: {...rota.request().headers(), host: new URL(args.origem).host}});
      if (!pendente || resposta.status() !== 200) return rota.fulfill({response: resposta});
      await rota.fulfill({response: resposta, json: {...(await resposta.json()), pendencias: ['segundo_fator']}});
    });
    await page.goto(`${args.origem}/entrar`);
    await page.waitForSelector('#entrar-secao:not([hidden])');
    await page.fill('#entrar-login', args.pendente.email); await page.fill('#entrar-senha', args.senha);
    await Promise.all([page.waitForURL(url => url.pathname !== '/entrar', {timeout: 15000}), page.click('#entrar-enviar')]);
    pendente = true;
    await page.goto(`${args.origem}/conta/segundo-fator`);
    await page.waitForSelector('#pendencia-secao:not([hidden]) h1', {timeout: 15000});
    assert.equal(await texto(page, '#pendencia-secao h1'), 'Proteja a conta com um segundo passo');
    assert.equal(await page.isHidden('#entrar-secao'), true, 'o Entrar comum não aparece');
    assert.match(await texto(page, '#pendencia-secao'), /ANTES DE CONTINUAR/);
    assert.match(await texto(page, '#pendencia-secao'), /PASSO 1 DE 3/);
    if (args.capturas) await page.screenshot({path: path.join(args.capturas, 'pendencia-passo1-1440.png'), fullPage: true});
    await page.fill('#pendencia-secao input[type="password"]', args.senha);
    await page.click('#pendencia-secao .fator-principal');
    await page.waitForSelector('#pendencia-secao svg', {timeout: 15000});   // o QR do passo 2, com a chave que o servidor acabou de gerar
    assert.match(await texto(page, '#pendencia-secao'), /PASSO 2 DE 3/);
    if (args.capturas) await page.screenshot({path: path.join(args.capturas, 'pendencia-passo2-1440.png'), fullPage: true});
    await Promise.all([page.waitForURL(url => url.pathname === '/entrar', {timeout: 15000}), page.click('#pendencia-secao .fator-link')]);   // Sair
    pendente = false;
    resultado.pendencia = 'ok';
    await ctx.close();

    // 5. capturas do Design (só com `capturas`): cada estado em 375 e 1440 px, nos dois temas; o aviso de entrada expirada só no tema claro
    if (args.capturas && args.extras) {
      fs.mkdirSync(args.capturas, {recursive: true});
      let i = -1;
      for (const [rotulo, largura, altura] of [['375', 375, 812], ['1440', 1440, 900]]) for (const tema of ['light', 'dark']) {
        i += 1;
        const conta = args.extras[i], marca = `${rotulo}-${tema}`;
        const c = await browser.newContext({viewport: {width: largura, height: altura}, locale: 'pt-BR', colorScheme: tema});
        await c.addInitScript(t => { try { localStorage.setItem('vlado-idioma', 'pt'); localStorage.setItem('apuracao:tema', t); } catch (_) { /* sem armazenamento */ } }, tema);
        await c.route(`${args.origem}/**`, async rota => { try {
          const pedido = rota.request(), endereco = new URL(pedido.url());
          if (endereco.pathname === '/api/entrar-segundo-fator' && c.__expirar) return await rota.fulfill({status: 401, contentType: 'application/json', body: JSON.stringify({estado: 'credenciais', codigo: 'entrada_expirada', erro: 'A entrada expirou.'})});
          const resposta = await rota.fetch({url: `http://127.0.0.1:${args.porta}${endereco.pathname}${endereco.search}`, headers: {...pedido.headers(), host: new URL(args.origem).host}, maxRedirects: 0});
          await rota.fulfill({response: resposta});
        } catch (_) { /* a página fechou com o pedido em voo */ } });
        const pagina = await c.newPage();
        const foto = nome => pagina.screenshot({path: path.join(args.capturas, `${nome}-${marca}.png`), fullPage: true});
        await entrarAte2(pagina, conta.email, args.senha);
        await foto('fator-1-codigo-do-aplicativo');
        await pagina.click('#fator-reserva');
        await foto('fator-2-codigo-de-reserva');
        await pagina.click('#fator-reserva');
        await pagina.fill('#fator-codigo', '000000'); await pagina.click('#fator-enviar'); await pagina.waitForSelector('.campo-erro');
        await foto('fator-3-codigo-incorreto');
        if (tema === 'light') {
          c.__expirar = true;
          await pagina.fill('#fator-codigo', '123456'); await pagina.click('#fator-enviar');
          await pagina.waitForSelector('#entrar-secao:not([hidden])'); await pagina.waitForSelector('#entrar-mensagem:not([hidden])');
          await foto('fator-4-entrada-expirada');
        }
        await pagina.goto(`${args.origem}/redefinir/${args.redefinires[i]}`);
        await pagina.waitForSelector('#redefinir-form:not([hidden])');
        await pagina.fill('#redefinir-senha', args.redefinir.senha_nova); await pagina.click('#redefinir-enviar');
        await pagina.waitForSelector('#redefinir-codigo-campo:not([hidden])');
        await foto('fator-5-redefinir-com-codigo');
        await c.close();
      }
    }
  } finally {
    await browser.close();
  }
  console.log(JSON.stringify(resultado));
})().catch(erro => { console.error(erro.stack || erro); process.exit(1); });
