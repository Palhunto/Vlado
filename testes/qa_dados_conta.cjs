'use strict';
// Seus dados em Minha conta, num navegador de verdade contra o servidor de verdade (test_dados_conta_navegador.py o chama): os termos de uso, "Exportar meus dados" e "Excluir a conta"
// (contrato de contas, 12, entrega 4b; docs/design/componentes.md#minha-conta e #excluir-conta).
// Uso: node qa_dados_conta.cjs '<json>'   com {porta, origem, senha, versao, endereco, reporter: {login, nome}, dono: {login, nome}, capturas?}. Sem argumento não faz nada.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

if (!process.argv[2]) process.exit(0);
const args = JSON.parse(process.argv[2]);
const {chromium} = require(path.join(__dirname, '..', '.ferramentas', 'node', 'node_modules', 'playwright'));

const texto = async (page, seletor) => (await page.textContent(seletor)).replace(/\s+/g, ' ').trim();
const DIALOGO = 'dialog.dialogo[open]';
const CARTAO = '[data-cartao="dados"]';
const ACAO = `${DIALOGO} .dialogo-acoes button:last-child`;

async function contexto(browser, {largura = 1440, tema = 'light'} = {}) {
  const ctx = await browser.newContext({viewport: {width: largura, height: largura < 700 ? 800 : 900}, locale: 'pt-BR', acceptDownloads: true});
  await ctx.addInitScript(tema => { try { localStorage.setItem('vlado-idioma', 'pt'); localStorage.setItem('apuracao:tema', tema); } catch (_) { /* sem armazenamento */ } }, tema);
  // O servidor fala HTTP e se apresenta como a origem https (o Origin e o Host que ele confere).
  await ctx.route(`${args.origem}/**`, async rota => { try {
    const pedido = rota.request(), endereco = new URL(pedido.url());
    const resposta = await rota.fetch({url: `http://127.0.0.1:${args.porta}${endereco.pathname}${endereco.search}`, headers: {...pedido.headers(), host: new URL(args.origem).host}, maxRedirects: 0});
    if (process.env.QA_DEPURAR) console.error("rota", endereco.pathname, resposta.status(), resposta.headers().location || "", endereco.pathname === "/api/entrar" ? (await resposta.text()).slice(0, 300) + " " + (resposta.headers()["set-cookie"] || "").slice(0, 120) : "");
    await rota.fulfill({response: resposta});
  } catch (erro) { if (process.env.QA_DEPURAR) console.error("rota:", String(erro).slice(0, 300)); } });
  return ctx;
}
// `codigo`: um código de reserva, para a conta que tem o segundo fator (a dona, no piloto). A página do Entrar desta branch ainda não tem o passo 2 (é do Lume), então o segundo passo
// vai pela API, como a página faz, com o bilhete que o servidor põe no cookie.
async function entrar(page, login, codigo) {
  await page.goto(`${args.origem}/entrar`);
  if (codigo) {
    const resultado = await page.evaluate(async ({login, senha, codigo}) => {
      const enviar = async (caminho, corpo) => fetch(`/api/${caminho}`, {method: 'POST', credentials: 'same-origin', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(corpo)});
      let resposta = await enviar('entrar', {login, senha}), corpo = await resposta.json();
      if (corpo.estado === 'segundo_fator') { resposta = await enviar('entrar-segundo-fator', {codigo}); corpo = await resposta.json(); }
      return {status: resposta.status, estado: corpo.estado};
    }, {login, senha: args.senha, codigo});
    assert.equal(resultado.status, 200, JSON.stringify(resultado));
  } else {
    await page.fill('#entrar-login', login); await page.fill('#entrar-senha', args.senha);
    await Promise.all([page.waitForURL(url => url.pathname === '/' || url.pathname === '/index.html', {timeout: 20000}), page.click('#entrar-enviar')]);
  }
  await page.goto(`${args.origem}/?area=configuracoes`);
  await page.waitForSelector(`${CARTAO} .conta-exportar`, {timeout: 20000});
}
const capturar = async (page, nome) => { if (args.capturas && nome.startsWith('seus-dados')) await page.locator(CARTAO).scrollIntoViewIfNeeded(); if (args.capturas) await page.screenshot({path: path.join(args.capturas, `${nome}.png`), fullPage: false}); };
async function abrirExcluir(page) {
  await page.click(`${CARTAO} .conta-excluir`);
  await page.waitForSelector(`${DIALOGO} input[type="password"]`);
  assert.equal(await texto(page, `${DIALOGO} .dialogo-titulo`), 'Excluir a sua conta?');
}

(async () => {
  const browser = await chromium.launch();
  const resultado = {};
  const erros = [];
  try {
    // 1. a repórter: os termos, o arquivo e a exclusão
    let ctx = await contexto(browser), page = await ctx.newPage();
    page.on('pageerror', erro => erros.push(erro.message));
    await entrar(page, args.reporter.login);
    const linha = await texto(page, `${CARTAO} .conta-termos`);
    assert.ok(linha.startsWith(`Termos de uso: versão ${args.versao}, aceita em `), linha);
    assert.equal(await page.getAttribute(`${CARTAO} .conta-termos a`, 'href'), args.endereco);
    assert.equal(await page.getAttribute(`${CARTAO} .conta-termos a`, 'target'), '_blank');
    const [arquivo] = await Promise.all([page.waitForEvent('download'), page.click(`${CARTAO} .conta-exportar`)]);
    assert.match(arquivo.suggestedFilename(), /^vlado-meus-dados-\d{4}-\d{2}-\d{2}\.json$/);
    const conteudo = JSON.parse(fs.readFileSync(await arquivo.path(), 'utf8'));
    assert.equal(conteudo.formato, 'vlado-meus-dados'); assert.equal(conteudo.versao, 1);
    assert.ok(!JSON.stringify(conteudo).includes(args.senha), 'a senha não está no arquivo');
    await page.waitForFunction(() => /Arquivo baixado\./.test(document.querySelector('.conta-estado')?.textContent || ''), null, {timeout: 15000});
    assert.equal(await texto(page, '.conta-estado'), '✓ Arquivo baixado. Ainda não traz: conversas criadas antes de 22 de nov. de 2026.');
    resultado.exportado = {nome: arquivo.suggestedFilename(), incompleto: conteudo.incompleto};

    // excluir: a senha errada fica no campo da senha; o nome certo e a senha certa saem da Mesa
    await abrirExcluir(page);
    assert.ok(await page.isDisabled(ACAO), 'a ação espera o nome e a senha');
    await page.fill(`${DIALOGO} input[type="text"]`, args.reporter.nome); await page.fill(`${DIALOGO} input[type="password"]`, 'senha-errada-de-teste');
    await page.click(ACAO);
    try { await page.waitForSelector(`${DIALOGO} .dialogo-erro-campo:not([hidden])`, {timeout: 8000}); }
    catch (erro) { throw new Error(`sem erro junto à senha; o diálogo diz: ${await texto(page, DIALOGO)}`); }
    assert.ok((await texto(page, `${DIALOGO} .dialogo-erro-campo:not([hidden])`)).startsWith('Senha incorreta'), await texto(page, `${DIALOGO} .dialogo-erro-campo:not([hidden])`));
    assert.ok(await page.isVisible(DIALOGO), 'o diálogo continua');
    await page.fill(`${DIALOGO} input[type="password"]`, args.senha);
    await Promise.all([page.waitForURL(url => url.pathname === '/entrar' && url.searchParams.get('aviso') === 'conta_excluida', {timeout: 20000}), page.click(ACAO)]);
    // sem sessão: a Mesa já não abre
   
    assert.equal(await page.evaluate(async () => (await fetch('/api/sessao', {headers: {Accept: 'application/json'}, credentials: 'same-origin'})).status), 401, 'sem sessão');
    assert.equal((await ctx.cookies()).filter(c => c.name === 'vlado_sessao' && c.value).length, 0, 'o cookie da sessão foi apagado');
    await ctx.close();

    // 2. a única dona da redação: o nome certo recebe do servidor a razão do último dono; o nome que não confere (pedido à mão) é recusado antes da senha
    ctx = await contexto(browser); page = await ctx.newPage(); page.on('pageerror', erro => erros.push(erro.message));
    await entrar(page, args.dono.login, args.dono.codigos.shift());
    await abrirExcluir(page);
    const divergente = await page.evaluate(async senha => { try { await api('conta-excluir', {senha, nome: 'Outra Pessoa'}); return 'excluiu'; } catch (erro) { return {status: erro.result?.estado, codigo: erro.result?.codigo}; } }, args.senha);
    assert.equal(divergente.codigo, 'nome_confirmacao_divergente', JSON.stringify(divergente));
    await page.fill(`${DIALOGO} input[type="text"]`, args.dono.nome); await page.fill(`${DIALOGO} input[type="password"]`, args.senha);
    await page.click(ACAO);
    await page.waitForFunction(() => /A redação precisa de ao menos um dono ativo/.test(document.querySelector('dialog.dialogo[open]')?.textContent || ''), null, {timeout: 15000});
    assert.ok((await texto(page, DIALOGO)).includes('A redação precisa de ao menos um dono ativo. Antes de excluir a sua conta, torne outra pessoa dono na Equipe.'), await texto(page, DIALOGO));
    assert.ok(await page.isVisible(DIALOGO), 'o diálogo continua: a conta não saiu');
    await capturar(page, 'excluir-ultimo-dono-1440-light');
    await ctx.close();

    // 3. as capturas para o Design: dois temas, 375 e 1440 px
    if (args.capturas) {
      for (const tema of ['light', 'dark']) {
        for (const largura of [375, 1440]) {
          const c = await contexto(browser, {largura, tema}); const p = await c.newPage();
          await entrar(p, args.dono.login, args.dono.codigos.shift());
          await capturar(p, `seus-dados-${largura}-${tema}`);
          await abrirExcluir(p);
          await capturar(p, `excluir-${largura}-${tema}`);
          await c.close();
        }
      }
    }
    assert.deepEqual(erros, [], `erros de página: ${erros.join('; ')}`);
  } finally { await browser.close(); }
  console.log(JSON.stringify(resultado));
})().catch(erro => { console.error(erro); process.exit(1); });
