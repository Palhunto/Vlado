const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const [origin, output, chrome] = process.argv.slice(2);
(async () => {
  await fs.mkdir(output, {recursive:true});
  const browser = await chromium.launch({headless:true, ...(chrome ? {executablePath:chrome} : {})});
  const page = await browser.newPage({viewport:{width:1440, height:1100}, acceptDownloads:true});
  const errors = [], external = [], checks = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => { if (!request.url().startsWith(origin)) external.push(request.url()); });
  // The investigation is chosen in the header; each area's own case selector is a hidden adapter.
  async function conversation() {
    await page.locator('#contexto-caso option[value="fontes"]').waitFor({state:'attached'});
    await page.selectOption('#contexto-caso', 'fontes');
    if (!await page.locator('#codex-acervo').evaluate(el => el.open)) await page.locator('#codex-acervo>summary').click();
    await page.locator('#codex-conversa option[value="' + 'a'.repeat(32) + '"]').waitFor({state:'attached'});
    await page.selectOption('#codex-conversa', 'a'.repeat(32));
    await page.locator('.codex-answer').waitFor();
    await page.locator('#codex-status').filter({hasText:'Execução concluída'}).waitFor();
    assert.equal(await page.locator('#codex-acervo').evaluate(el => el.open), false);
  }
  try {
    await page.goto(origin);
    await page.click('#ver-cadastro');
    assert.equal(await page.locator('#cadastro-id').count(), 0);
    await page.fill('#cadastro-titulo-input', 'Minha apuração legível');
    await page.setInputFiles('#cadastro-arquivos', {name:'Documento sintético.txt', mimeType:'text/plain', buffer:Buffer.from('Cadastro de interface, sem pergunta editorial.')});
    await page.click('#enviar-documentos');
    await page.locator('#cadastro-status').filter({hasText:'Documentos registrados. Aguardando sua pergunta.'}).waitFor();
    assert.match(await page.locator('#cadastro-caso').inputValue(), /^apuracao_[a-f0-9]{32}$/);
    assert.equal(await page.locator('#contexto-caso option:checked').textContent(), 'Minha apuração legível');
    assert.equal(await page.locator('#area-descricao').innerText(), 'Minha apuração legível');
    assert.doesNotMatch(await page.locator('#cadastro-recibo').innerText(), /apuracao_|SHA-256/);
    checks.push('Cadastro apenas por nome, ID interno automático, recibo sem identificadores expostos.');
    await page.click('#ver-codex');
    await page.locator('#codex-conta').filter({hasText:'Conectado à API'}).waitFor();
    assert.equal(await page.locator('#codex-conexao').evaluate(el => el.open), false);
    assert.equal(await page.locator('#contexto-caso option[value="fontes"]').textContent(), 'Americanas — fatos relevantes');
    await conversation();
    assert.equal(await page.locator('#area-titulo').innerText(), 'Perguntar à IA');
    // With an answer on screen the question composer folds away and keeps its toggle.
    assert.equal(await page.locator('#desktop-composicao-alternar').getAttribute('aria-expanded'), 'false');
    assert.equal(await page.locator('#desktop-composicao-alternar').innerText(), 'Escrever pergunta');
    assert.equal(await page.locator('.codex-updates').evaluate(el => el.open), false);
    assert.equal(await page.locator('#codex-andamento').evaluate(el => el.open), false);
    assert.equal(await page.locator('.codex-answer>.technical').evaluate(el => el.open), false);
    assert.equal(await page.locator('.codex-answer .markdown-body strong').first().innerText(), 'Valor documentado:');
    assert.equal(await page.locator('.codex-answer table th').count(), 2);
    assert.equal(await page.locator('.codex-answer table td').count(), 2);
    assert.match(await page.locator('.codex-answer pre code').first().innerText(), /\*\*texto literal em código\*\*/);
    assert.equal(await page.locator('.markdown-body script,.markdown-body img,.markdown-body a[href^="javascript:"]').count(), 0);
    assert.equal(await page.evaluate(() => window.INJETADO_POLIMENTO), undefined);
    checks.push('Conexão compacta; resposta destacada; atualizações e registros recolhidos; Markdown e tabelas renderizados com HTML inerte.');
    const limitation = await page.locator('#codex-limitacoes').innerText();
    assert.match(limitation, /páginas 2/);
    assert.match(limitation, /1 referência/);
    assert.doesNotMatch(limitation, /[a-f0-9]{64}/);
    assert.equal(await page.locator('.codex-answer .codex-pendente').count(), 1);
    // The citation is a chip with the page; one click opens that page of the original and its source card.
    const citation = page.locator('.codex-answer button.source-citation');
    assert.equal(await citation.innerText(), 'p. 1');
    assert.equal(await citation.getAttribute('aria-label'), 'Ver página 1 no original: Fato relevante de 11/01/2023');
    await citation.click();
    await page.locator('#original-dialogo[open]').waitFor();
    assert.match(await page.locator('#original-localizacao').innerText(), /Página física 1 do PDF/);
    assert.match(await page.locator('#original-referencia').innerText(), /Valor sintetico 123/);
    const downloaded = page.waitForEvent('download');
    await page.click('#original-baixar');
    assert.equal((await fs.readFile(await (await downloaded).path())).subarray(0,4).toString(), '%PDF');
    await page.click('#original-fechar');
    const source = page.locator('#codex-fontes>.codex-source').first();
    assert.equal(await page.locator('#codex-painel-fontes').evaluate(el => el.open), true);
    assert.equal(await source.evaluate(el => el.open), true);
    assert.match(await source.locator('blockquote').innerText(), /Valor sintetico 123/);
    assert.equal(await source.getByRole('button', {name:'Ver página 1 no original'}).count(), 1);
    assert.doesNotMatch(await source.innerText(), /[a-f0-9]{64}/);
    await source.locator('.technical>summary').click();
    assert.match(await source.locator('.technical').innerText(), /[a-f0-9]{64}/);
    await source.locator('.technical>summary').click();
    checks.push('Citação com a página abre o original nessa página, a um clique, e o trecho ao lado; hashes recolhidos; original baixável.');
    checks.push('Alertas específicos: página sem texto e fonte pendente, sem exibição de hashes.');
    await page.evaluate(() => document.fonts.ready);
    assert.equal(await page.evaluate(() => document.fonts.check('16px "Source Sans 3"') && document.fonts.check('28px "Source Serif 4"')), true);
    // One type scale: nothing visible is set below 12px.
    const tiny = () => page.evaluate(() => [...document.querySelectorAll('body *')].filter(el => el.offsetParent && [...el.childNodes].some(n => n.nodeType === 3 && n.data.trim()) && parseFloat(getComputedStyle(el).fontSize) < 12).map(el => el.tagName + '.' + el.className));
    assert.deepEqual(await tiny(), []);
    await page.screenshot({path:path.join(output, 'resposta-desktop.png'), fullPage:true});
    for (const width of [320,390,736,1440]) {
      await page.setViewportSize({width, height:950});
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, 'overflow ' + width);
      if (width === 390) {
        // On a phone the composer is collapsible too, and keeps a 44px toggle.
        assert.deepEqual(await tiny(), []);
        assert.equal(await page.locator('#desktop-composicao-alternar').isVisible(), true);
        assert.ok((await page.locator('#desktop-composicao-alternar').boundingBox()).height >= 44);
        assert.ok((await page.locator('#codex-form').boundingBox()).height < 90, 'pergunta recolhida');
        await page.screenshot({path:path.join(output, 'resposta-mobile.png'), fullPage:true});
      }
    }
    await page.reload();
    await page.click('#ver-codex');
    await conversation();
    assert.match(await page.locator('#codex-limitacoes').innerText(), /páginas 2/);
    await page.selectOption('#contexto-caso', 'alpha');
    await page.locator('#codex-inventario').filter({hasText:'1 documento'}).waitFor({state:'attached'});
    assert.equal(await page.locator('#codex-limitacoes').isVisible(), false);
    assert.equal(await page.locator('.codex-answer').count(), 0);
    checks.push('Recarga preserva apresentação e limitações; troca para acervo sem lacunas remove os alertas.');
    checks.push('Fontes locais e layout sem transbordamento de 320 a 1440 px.');
    assert.deepEqual(external, []);
    assert.deepEqual(errors, []);
    await fs.writeFile(path.join(output, 'resultado.json'), JSON.stringify({estado:'ok', natureza:'arquivos e eventos sintéticos; login simulado; sem inferência', checks, errors, external}, null, 2));
    console.log('QA polimento: OK (' + checks.length + ' verificações)');
  } catch (error) {
    await page.screenshot({path:path.join(output, 'falha.png'), fullPage:true}).catch(() => {});
    throw error;
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
