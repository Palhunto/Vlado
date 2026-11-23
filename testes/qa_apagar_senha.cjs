'use strict';
// Apagar definitivamente com a senha, num navegador de verdade contra o servidor de verdade (test_apagar_senha_navegador.py o chama).
// Uso: node qa_apagar_senha.cjs '<json>'   com {porta, origem, login, senha, capturas?}. Sem argumento não faz nada.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

if (!process.argv[2]) process.exit(0);
const args = JSON.parse(process.argv[2]);
const {chromium} = require(path.join(__dirname, '..', '.ferramentas', 'node', 'node_modules', 'playwright'));

const TELAS = [['375', {width: 375, height: 812}], ['1440', {width: 1440, height: 900}]];
const DIALOGO = 'dialog.dialogo[open]';
const ERRADA = 'senha-errada-de-teste';

async function contexto(browser, tela, tema) {
  const ctx = await browser.newContext({viewport: tela, colorScheme: tema, locale: 'pt-BR'});
  await ctx.addInitScript(modo => { try { localStorage.setItem('vlado-idioma', 'pt'); localStorage.setItem('apuracao:tema', modo); } catch (_) { /* sem armazenamento */ } }, tema);
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
const botaoApagar = page => page.locator('#gerenciar-lixeira button', {hasText: 'Apagar definitivamente'}).first();
const itensNaLista = page => page.locator('#gerenciar-lixeira li').count();

// Abre o diálogo do primeiro item da lixeira e espera o alcance (o campo do nome habilitado).
async function abrirDialogo(page) {
  await botaoApagar(page).click();
  await page.waitForSelector(DIALOGO, {timeout: 15000});
  await page.waitForFunction(() => { const campo = document.querySelector('dialog.dialogo[open] input[type="text"]'); return campo && !campo.disabled; }, null, {timeout: 15000});
  return texto(page, `${DIALOGO} .dialogo-campo strong`);
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
      await page.goto(`${args.origem}/?area=gerenciar`);
      await page.waitForSelector('#gerenciar-lixeira li', {timeout: 20000});
      const antes = await itensNaLista(page);
      assert.ok(antes >= 1, 'há item na lixeira');

      // 1. o diálogo: nome e senha, a ação espera os dois
      const nome = await abrirDialogo(page);
      const entradas = await page.locator(`${DIALOGO} input`).evaluateAll(l => l.map(e => ({tipo: e.type, auto: e.autocomplete})));
      assert.deepEqual(entradas.map(e => e.tipo), ['text', 'password'], 'o nome primeiro, a senha abaixo');
      assert.equal(entradas[1].auto, 'current-password');
      assert.ok(await page.isDisabled(`${DIALOGO} .dialogo-acoes button:last-child`), 'a ação espera o nome e a senha');
      await capturar(page, 'apagar-senha-pedida', rotuloTela, tema);
      await page.fill(`${DIALOGO} input[type="text"]`, nome);
      assert.ok(await page.isDisabled(`${DIALOGO} .dialogo-acoes button:last-child`), 'só o nome: ainda falta a senha');

      // 2. senha errada: o erro vai ao campo da senha, o nome fica, o servidor não apagou
      await page.fill(`${DIALOGO} input[type="password"]`, ERRADA);
      await page.click(`${DIALOGO} .dialogo-acoes button:last-child`);
      await page.waitForSelector(`${DIALOGO} .dialogo-erro-campo:not([hidden])`, {timeout: 15000});
      assert.ok((await texto(page, `${DIALOGO} .dialogo-erro-campo`)).startsWith('Senha incorreta'));
      assert.equal(await page.inputValue(`${DIALOGO} input[type="password"]`), '', 'a senha errada sai do campo');
      assert.equal(await page.inputValue(`${DIALOGO} input[type="text"]`), nome, 'o nome digitado fica');
      assert.ok(await page.evaluate(() => document.activeElement === document.querySelector('dialog.dialogo[open] input[type="password"]')), 'o foco volta à senha');
      await capturar(page, 'apagar-senha-incorreta', rotuloTela, tema);

      // 3. Cancelar não apaga nada
      await page.click(`${DIALOGO} .dialogo-acoes button:first-child`);
      await page.waitForSelector(DIALOGO, {state: 'detached', timeout: 15000});
      assert.equal(await itensNaLista(page), antes, 'cancelar não tira o item da lista');

      // 4. nome errado (pelo servidor, que confere o nome ANTES da senha) não conta tentativa: seis pedidos com nome errado e senha errada não bloqueiam a conta
      const divergencias = await page.evaluate(async () => {
        const item = (await api('gerenciar-listar', {})).lixeira[0].id;  // o mesmo item que o diálogo abriu (o primeiro da lixeira)
        const alcance = await api('lixeira-alcance', {item});
        const codigos = [];
        for (let i = 0; i < 6; i++) {
          try { await api('lixeira-apagar', {item, nome: 'nome-que-nao-confere', confirmacao: alcance.confirmacao, senha: 'senha-errada-de-teste'}); codigos.push('apagou'); }
          catch (erro) { codigos.push(erro.result?.codigo || erro.message); }
        }
        return codigos;
      });
      assert.deepEqual(divergencias, Array(6).fill('nome_confirmacao_divergente'), 'nome errado responde como sempre e não conta tentativa');

      // 5. a senha certa conclui (e prova que a conta não foi bloqueada pelas seis tentativas de nome errado)
      const nomeDeNovo = await abrirDialogo(page);
      await page.fill(`${DIALOGO} input[type="text"]`, nomeDeNovo);
      await page.fill(`${DIALOGO} input[type="password"]`, args.senha);
      await page.click(`${DIALOGO} .dialogo-acoes button:last-child`);
      await page.waitForSelector(DIALOGO, {state: 'detached', timeout: 20000});
      await page.waitForFunction(() => /^Apagado definitivamente/.test(document.getElementById('gerenciar-status').textContent), null, {timeout: 20000});
      assert.ok(!(await page.content()).includes(args.senha), 'a senha não aparece na página');
      await page.waitForFunction(antesDoApagar => document.querySelectorAll('#gerenciar-lixeira li').length < antesDoApagar || document.querySelectorAll('#gerenciar-lixeira li.manage-empty').length === 1,
        antes, {timeout: 20000});
      await capturar(page, 'apagar-concluido', rotuloTela, tema);
      assert.deepEqual(erros, [], `erros de página: ${erros.join('; ')}`);
      resultado[marca] = 'ok';
      await ctx.close();
    }
  } finally { await browser.close(); }
  console.log(JSON.stringify(Object.keys(resultado)));
})().catch(erro => { console.error(erro); process.exit(1); });
