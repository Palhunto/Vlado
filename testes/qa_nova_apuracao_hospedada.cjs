'use strict';
// A Nova apuração no modo hospedado, num navegador de verdade contra o servidor de verdade (test_nova_apuracao_navegador.py o chama): a repórter entra, cria a apuração
// pelo passo 1 e o primeiro envio, e o cabeçalho (seletor do topo e subtítulo) diz o NOME da apuração em cada momento do passo 3, nunca o identificador.
// Uso: node qa_nova_apuracao_hospedada.cjs '<json>' com {porta, origem, login, senha, capturas?}. Sem argumento não faz nada.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

if (!process.argv[2]) process.exit(0);
const args = JSON.parse(process.argv[2]);
const {chromium} = require(path.join(__dirname, '..', '.ferramentas', 'node', 'node_modules', 'playwright'));

(async () => {
  const pasta = fs.mkdtempSync(path.join(os.tmpdir(), 'nova_hospedada_'));
  const arquivo = path.join(pasta, 'relatorio_sintetico.txt');
  fs.writeFileSync(arquivo, 'Relatório sintético da obra. Valor 123.\n');
  const browser = await chromium.launch();
  const resultado = {};
  try {
    const ctx = await browser.newContext({viewport: {width: 1440, height: 900}, locale: 'pt-BR'});
    await ctx.addInitScript(() => { try { localStorage.setItem('vlado-idioma', 'pt'); } catch (_) { /* sem armazenamento */ } });
    // O servidor fala HTTP e se apresenta como a origem https; esta branch ainda não anuncia o envio em fluxo (as de integração anunciam), e o servidor o aceita.
    await ctx.route(`${args.origem}/**`, async rota => { try {
      const pedido = rota.request(), endereco = new URL(pedido.url());
      const resposta = await rota.fetch({url: `http://127.0.0.1:${args.porta}${endereco.pathname}${endereco.search}`, headers: {...pedido.headers(), host: new URL(args.origem).host}, maxRedirects: 0});
      if (endereco.pathname === '/api/integracao') return await rota.fulfill({response: resposta, json: {...(await resposta.json()), envio_fluxo: true}});
      await rota.fulfill({response: resposta});
    } catch (_) { /* a página fechou com o pedido em voo */ } });
    const page = await ctx.newPage();
    const erros = []; page.on('pageerror', erro => erros.push(erro.message));
    await page.goto(`${args.origem}/entrar`);
    await page.fill('#entrar-login', args.login); await page.fill('#entrar-senha', args.senha);
    await Promise.all([page.waitForURL(url => url.pathname === '/' || url.pathname === '/index.html'), page.click('#entrar-enviar')]);
    await page.waitForSelector('#inicio-nova', {timeout: 20000});
    const titulo = `Obra da escola ${Date.now()}`;
    await page.evaluate(() => document.getElementById('inicio-nova').click());
    await page.waitForSelector('#area-nova:not([hidden])');
    await page.fill('#nova-nome', titulo);
    await page.click('#nova-continuar');
    await page.waitForSelector('#area-documentos:not([hidden])');
    // o cabeçalho enquanto o envio não começou, e a cada passo depois do primeiro lote aceito
    const cabecalho = () => page.evaluate(() => {
      const seletor = document.getElementById('contexto-caso');
      return {seletor: seletor.selectedOptions[0]?.textContent?.trim() || '', valor: seletor.value, subtitulo: document.getElementById('area-descricao').textContent.trim(),
        titulo: document.getElementById('area-titulo').textContent.trim(), etapa: document.querySelector('#nova-etapas-2 [aria-current="step"]')?.textContent.trim() || ''};
    });
    assert.equal((await cabecalho()).subtitulo, titulo, 'no passo 2 o subtítulo é o nome digitado');
    // observa o cabeçalho durante todo o envio: em nenhum momento o seletor ou o subtítulo podem mostrar o identificador cru ou "Nenhuma apuração selecionada"
    await page.evaluate(() => {
      window.__cabecalhos = [];
      const registrar = () => { const s = document.getElementById('contexto-caso'); window.__cabecalhos.push([s.value, s.selectedOptions[0]?.textContent?.trim() || '', document.getElementById('area-descricao').textContent.trim(), document.body.dataset.nova || '']); };
      new MutationObserver(registrar).observe(document.getElementById('area-descricao'), {childList: true, characterData: true, subtree: true});
      new MutationObserver(registrar).observe(document.getElementById('contexto-caso'), {childList: true, attributes: true, subtree: true});
    });
    await page.setInputFiles('#documentos-zona input[type="file"]', arquivo);
    await page.waitForFunction(() => /^apuracao_[0-9a-f]{32}$/.test(window.contextoCaso?.() || ''), null, {timeout: 60000});
    await page.waitForFunction(() => document.querySelector('#nova-etapas-2 [aria-current="step"]')?.textContent.includes('3'), null, {timeout: 120000});
    await page.waitForTimeout(1500);
    const passo3 = await cabecalho();
    assert.equal(passo3.seletor, titulo, `o seletor do topo diz o nome da apuração, não o identificador: ${JSON.stringify(passo3)}`);
    assert.equal(passo3.subtitulo, titulo, 'o subtítulo é o nome da apuração');
    assert.equal(passo3.titulo, 'Documentos');
    const historico = await page.evaluate(() => window.__cabecalhos);
    const ruins = historico.filter(([valor, texto, sub]) => valor && (texto === valor || /^apuracao_[0-9a-f]{32}$/.test(texto) || sub === 'Nenhuma apuração selecionada'));
    assert.deepEqual(ruins, [], `o cabeçalho nunca mostrou o identificador nem "Nenhuma apuração selecionada" depois de criada: ${JSON.stringify(ruins)}`);
    // o recibo conferido e, depois, sair e voltar: o nome continua
    await page.locator('#documentos-envio a', {hasText: 'Ver recibo'}).click();
    await page.evaluate(() => document.getElementById('ver-inicio').click());
    await page.evaluate(() => document.getElementById('ver-documentos').click());
    await page.waitForTimeout(800);
    const depois = await cabecalho();
    assert.equal(depois.seletor, titulo); assert.equal(depois.subtitulo, titulo);
    assert.deepEqual(erros, []);
    resultado.ok = titulo;
    await ctx.close();
  } finally {
    await browser.close();
    fs.rmSync(pasta, {recursive: true, force: true});
  }
  console.log(JSON.stringify(resultado));
})().catch(erro => { console.error(erro.stack || erro); process.exit(1); });
