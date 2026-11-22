'use strict';
// Salvar e remover a chave de IA com a senha, num navegador de verdade contra o servidor de verdade (test_ia_senha_navegador.py o chama).
// Uso: node qa_ia_senha.cjs '<json>'   com {porta, origem, login, senha, capturas?}. Sem argumento não faz nada.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

if (!process.argv[2]) process.exit(0);
const args = JSON.parse(process.argv[2]);
const {chromium} = require(path.join(__dirname, '..', '.ferramentas', 'node', 'node_modules', 'playwright'));

const TELAS = [['375', {width: 375, height: 812}], ['1440', {width: 1440, height: 900}]];
const CHAVE = 'sk-ant-teste-' + 'a'.repeat(30);

async function contexto(browser, tela, tema) {
  const ctx = await browser.newContext({viewport: tela, colorScheme: tema, locale: 'pt-BR'});
  await ctx.addInitScript(() => { try { localStorage.setItem('vlado-idioma', 'pt'); } catch (_) { /* sem armazenamento: o padrão do servidor */ } });
  // O servidor fala HTTP e se apresenta como a origem https (o Origin e o Host que ele confere).
  await ctx.route(`${args.origem}/**`, async rota => { try {
    const pedido = rota.request(), endereco = new URL(pedido.url());
    const resposta = await rota.fetch({url: `http://127.0.0.1:${args.porta}${endereco.pathname}${endereco.search}`,
      headers: {...pedido.headers(), host: new URL(args.origem).host}, maxRedirects: 0});
    await rota.fulfill({response: resposta});
  } catch (_) { /* a página fechou com o pedido em voo */ } });
  return ctx;
}
async function capturar(page, nome, tela, tema) {
  if (!args.capturas) return;
  fs.mkdirSync(args.capturas, {recursive: true});
  await page.screenshot({path: path.join(args.capturas, `${nome}-${tela}-${tema}.png`)});
}
const texto = async (page, seletor) => (await page.textContent(seletor)).replace(/\s+/g, ' ').trim();
const DIALOGO = 'dialog.dialogo[open]';
// Espera o diálogo; se não vier, o erro traz o que a tela dizia (ajuda a ver a recusa do servidor).
async function esperarDialogo(page) {
  try { await page.waitForSelector(DIALOGO, {timeout: 15000}); }
  catch (erro) {
    const estado = await page.evaluate(() => ({mensagem: document.getElementById('ia-config-mensagem')?.textContent, dialogos: document.querySelectorAll('dialog').length,
      abertos: document.querySelectorAll('dialog[open]').length, chave: document.getElementById('ia-chave')?.value?.length, url: location.href,
      salvar: document.getElementById('ia-salvar')?.disabled, formulario: document.getElementById('ia-config')?.hidden}));
    throw new Error(`o diálogo não abriu: ${JSON.stringify(estado)}`);
  }
}

(async () => {
  const browser = await chromium.launch();
  const resultado = {};
  try {
    for (const [rotuloTela, tela] of TELAS) for (const tema of ['light', 'dark']) {
      const marca = `${rotuloTela}-${tema}`;
      const ctx = await contexto(browser, tela, tema);
      const page = await ctx.newPage();
      const erros = [];
      page.on('pageerror', erro => erros.push(erro.message));
      await page.goto(`${args.origem}/entrar`);
      await page.fill('#entrar-login', args.login);
      await page.fill('#entrar-senha', args.senha);
      await Promise.all([page.waitForURL(url => url.pathname === '/' || url.pathname === '/index.html'), page.click('#entrar-enviar')]);
      await page.goto(`${args.origem}/?area=codex`);
      await page.waitForSelector('#codex-conexao summary');
      await page.evaluate(() => { document.getElementById('codex-conexao').open = true; });
      await page.waitForSelector('#ia-config:not([hidden]) #ia-salvar', {timeout: 15000});

      // 1. salvar a chave: o servidor pede a senha, o diálogo reenvia o mesmo pedido
      await page.fill('#ia-chave', CHAVE);
      await page.click('#ia-salvar', {force: true});
      await esperarDialogo(page);
      assert.equal(await texto(page, `${DIALOGO} .dialogo-titulo`), 'Salvar a configuração da IA?');
      assert.equal(await page.getAttribute(`${DIALOGO} input`, 'type'), 'password');
      await capturar(page, 'ia-senha-pedida', rotuloTela, tema);
      await page.fill(`${DIALOGO} input`, 'senha-errada-de-teste');
      await page.click(`${DIALOGO} .dialogo-acoes button:last-child`);
      await page.waitForSelector(`${DIALOGO} .dialogo-erro-campo:not([hidden])`, {timeout: 15000});
      assert.ok((await texto(page, `${DIALOGO} .dialogo-erro-campo`)).startsWith('Senha incorreta'));
      await capturar(page, 'ia-senha-incorreta', rotuloTela, tema);
      await page.fill(`${DIALOGO} input`, args.senha);
      await page.click(`${DIALOGO} .dialogo-acoes button:last-child`);
      await page.waitForSelector(DIALOGO, {state: 'detached', timeout: 15000});
      await page.waitForFunction(() => document.getElementById('ia-config-mensagem').textContent === 'Configuração salva.', null, {timeout: 15000});
      assert.ok((await texto(page, '#ia-chave-estado')).includes('termina em'), 'a chave foi salva');
      assert.equal(await page.inputValue('#ia-chave'), '', 'a chave digitada saiu do campo');
      assert.ok(!(await page.content()).includes(args.senha), 'a senha não aparece na página');
      assert.ok(!(await page.content()).includes(CHAVE), 'a chave não volta à página');

      // 2. cancelar o diálogo: nada é enviado nem anunciado
      await page.evaluate(() => { document.getElementById('codex-conexao').open = true; });   // a verificação de conexão pode fechar o painel
      await page.fill('#ia-modelo', '');
      await page.click('#ia-salvar', {force: true});
      await esperarDialogo(page);
      await page.click(`${DIALOGO} .dialogo-acoes button:first-child`);
      await page.waitForSelector(DIALOGO, {state: 'detached', timeout: 15000});
      assert.equal(await texto(page, '#ia-config-mensagem'), '', 'cancelar não anuncia nada');
      assert.equal(await page.isDisabled('#ia-salvar'), false);

      // 3. remover a chave salva: diálogo destrutivo, mesma senha
      await page.evaluate(() => { document.getElementById('codex-conexao').open = true; });
      await page.click('#ia-remover', {force: true});
      await esperarDialogo(page);
      assert.equal(await page.getAttribute(DIALOGO, 'data-variante'), 'destrutivo');
      assert.equal(await texto(page, `${DIALOGO} .dialogo-titulo`), 'Remover a chave de IA?');
      await capturar(page, 'ia-remover-senha', rotuloTela, tema);
      await page.fill(`${DIALOGO} input`, args.senha);
      await page.click(`${DIALOGO} .dialogo-acoes button:last-child`);
      await page.waitForFunction(() => document.getElementById('ia-config-mensagem').textContent === 'Chave removida.', null, {timeout: 15000});
      assert.equal(await texto(page, '#ia-chave-estado'), 'Nenhuma chave configurada.');
      assert.deepEqual(erros, [], 'nenhum erro de JavaScript');
      resultado[marca] = 'ok';
      await ctx.close();
    }
  } finally {
    await browser.close();
  }
  console.log(JSON.stringify(resultado));
})().catch(erro => { console.error(erro.stack || erro); process.exit(1); });
