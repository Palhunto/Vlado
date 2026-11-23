'use strict';
// A Nova apuração de ponta a ponta num navegador de verdade, contra uma Mesa local de verdade (dados sintéticos; sobe quem chama): passo 1, passo 2, o primeiro
// envio que cria a apuração, o passo 3 (recibo) e a Documentos comum com "Páginas de <domínio>". Uso: node qa_nova_apuracao.cjs <porta> [pasta-das-capturas]
// Sem argumento não faz nada. Com a pasta, grava um PNG por estado, em 375 e 1440 px, nos dois temas.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

if (!process.argv[2]) process.exit(0);
const porta = process.argv[2], pastaCapturas = process.argv[3];
const {chromium} = require(path.join(__dirname, '..', '.ferramentas', 'node', 'node_modules', 'playwright'));
const BASE = `http://127.0.0.1:${porta}`;
const TELAS = [['375', {width: 375, height: 812}], ['1440', {width: 1440, height: 900}]];

(async () => {
  const pasta = fs.mkdtempSync(path.join(os.tmpdir(), 'nova_apuracao_'));
  const arquivo = path.join(pasta, 'relatorio_sintetico.txt');
  fs.writeFileSync(arquivo, 'Relatório sintético da obra. Valor 123.\n');
  const browser = await chromium.launch();
  const resultado = {};
  try {
    for (const [rotulo, tela] of TELAS) for (const tema of ['light', 'dark']) {
      const marca = `${rotulo}-${tema}`;
      const ctx = await browser.newContext({viewport: tela, colorScheme: tema, locale: 'pt-BR'});
      await ctx.addInitScript(t => { try { localStorage.setItem('apuracao:tema', t); localStorage.setItem('vlado-idioma', 'pt'); } catch (_) { /* sem armazenamento */ } }, tema);
      const page = await ctx.newPage();
      // Esta Mesa pode ser de uma branch que ainda não anuncia o envio em fluxo (envio_fluxo em /api/integracao, que as branches de integração anunciam):
      // o servidor o aceita, então o roteiro o anuncia.
      await page.route('**/*', async rota => {
        const url = rota.request().url();
        if (!url.startsWith(`${BASE}/`)) return rota.abort();
        if (url === `${BASE}/api/integracao`) { const resposta = await rota.fetch(); return rota.fulfill({response: resposta, json: {...(await resposta.json()), envio_fluxo: true}}); }
        return rota.continue();
      });
      const erros = [];
      page.on('pageerror', erro => erros.push(erro.message));
      const capturar = async nome => { if (pastaCapturas) { fs.mkdirSync(pastaCapturas, {recursive: true}); await page.screenshot({path: path.join(pastaCapturas, `${nome}-${marca}.png`), fullPage: true}); } };
      const titulo = `Obra da escola ${marca} ${Date.now()}`;

      await page.goto(`${BASE}/?area=inicio`, {waitUntil: 'load'});
      await page.waitForSelector('#inicio-nova', {timeout: 20000});
      await page.click('#inicio-nova');
      await page.waitForSelector('#area-nova:not([hidden])');
      assert.equal((await page.textContent('#area-titulo')).trim(), 'Nova apuração');
      assert.equal(await page.evaluate(() => document.activeElement?.id), 'nova-nome', 'o nome tem o foco');
      await capturar('nova-passo1', );

      // erros junto ao campo
      await page.click('#nova-continuar');
      assert.equal((await page.textContent('.campo-erro')).trim(), 'Falta o nome. Dê um nome à apuração.');
      await capturar('nova-erro-nome');
      await page.fill('#nova-nome', titulo);
      await page.check('input[name="nova-fontes"][value="documentos_web"]');
      await page.waitForSelector('#nova-site-campo:not([hidden])');
      await page.click('#nova-continuar');
      assert.equal((await page.textContent('.campo-erro')).trim(), 'Falta o site. Escreva o domínio, por exemplo prefeitura.sp.gov.br.');
      await page.fill('#nova-site', 'https://prefeitura.sp.gov.br/x');
      await page.click('#nova-continuar');
      assert.match(await page.textContent('.campo-erro'), /Site inválido\. Use só o domínio/);
      await capturar('nova-erro-site');
      await page.fill('#nova-site', 'prefeitura.sp.gov.br');

      // passo 2: Documentos por criar
      await page.click('#nova-continuar');
      await page.waitForSelector('#area-documentos:not([hidden])');
      assert.equal((await page.textContent('#area-titulo')).trim(), 'Nova apuração');
      assert.equal((await page.textContent('#area-descricao')).trim(), titulo);
      assert.equal(await page.isVisible('#nova-aviso'), true);
      assert.equal(await page.isVisible('#mesa-aba-acervo'), false, 'sem abas');
      assert.equal(await page.isVisible('#mesa-filtrar-leitura'), false, 'sem a barra Leitura');
      await capturar('nova-passo2');

      // voltar ao passo 1 e continuar de novo: os campos continuam preenchidos
      await page.click('#nova-voltar');
      assert.equal(await page.inputValue('#nova-nome'), titulo); assert.equal(await page.inputValue('#nova-site'), 'prefeitura.sp.gov.br');
      await page.click('#nova-continuar');
      await page.waitForSelector('#area-documentos:not([hidden])');

      // o primeiro envio cria a apuração: o servidor escolhe o id e a tela vira a Documentos comum
      await page.setInputFiles('#documentos-zona input[type="file"]', arquivo);
      await page.waitForFunction(() => /^apuracao_[0-9a-f]{32}$/.test(window.contextoCaso?.() || ''), null, {timeout: 60000});
      const caso = await page.evaluate(() => window.contextoCaso());
      await page.waitForSelector('#documentos-envio .envio-arquivo', {timeout: 30000});
      await page.waitForFunction(() => document.querySelector('#nova-etapas-2 [aria-current="step"]')?.textContent.includes('3'), null, {timeout: 90000});
      assert.equal((await page.textContent('#area-titulo')).trim(), 'Documentos');
      assert.equal((await page.textContent('#area-descricao')).trim(), titulo);
      assert.equal(await page.evaluate(() => document.body.dataset.nova), undefined, 'a tela vira a Documentos comum');
      await capturar('nova-passo3');
      const ver = page.locator('#documentos-envio a', {hasText: 'Ver recibo'});
      await ver.click();
      assert.equal(await page.isVisible('#nova-etapas-2'), false, 'recibo conferido: a linha de etapas sai');
      await page.waitForSelector('#fontes-web:not([hidden])', {timeout: 30000});
      assert.match((await page.textContent('#fontes-web-titulo')).trim(), /^Páginas de\s*prefeitura\.sp\.gov\.br$/);
      await capturar('documentos-paginas-do-site');

      // o servidor: uma apuração só, com o título e o site
      const catalogo = await page.evaluate(async () => (await fetch('/api/catalogo')).json());
      const feitas = catalogo.casos.filter(c => c.titulo === titulo);
      assert.equal(feitas.length, 1, 'uma apuração só'); assert.equal(feitas[0].id, caso);
      assert.deepEqual(erros, []);
      resultado[marca] = caso;
      await ctx.close();
    }
  } finally {
    await browser.close();
    fs.rmSync(pasta, {recursive: true, force: true});
  }
  console.log(JSON.stringify(resultado));
})().catch(erro => { console.error(erro.stack || erro); process.exit(1); });
