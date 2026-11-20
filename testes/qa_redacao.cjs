'use strict';
// Browser part of qa_redacao.py: opens the phase 08 tabs (claim review and interviews) on desktop
// (1440×1000) and phone (390×844), checks there are no page errors or external requests, reaches a
// claim with the real keyboard (Tab) and saves the captures. Synthetic data only.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs/promises');
const [origem, saida, caso, chrome] = process.argv.slice(2);

(async () => {
  const browser = await chromium.launch({headless: true, ...(chrome ? {executablePath: chrome} : {})});
  const resultado = {capturas: [], erros: [], externos: [], foco_afirmacao: null, revisao_local: null};
  try {
    for (const [nome, viewport] of [['desktop', {width: 1440, height: 1000}], ['celular', {width: 390, height: 844}]]) {
      const page = await browser.newPage({viewport});
      page.on('pageerror', e => resultado.erros.push(`${nome}: ${e.message}`));
      page.on('request', r => { if (!r.url().startsWith(origem) && !r.url().startsWith('blob:') && !r.url().startsWith('data:')) resultado.externos.push(r.url()); });
      const foto = async rotulo => { await page.evaluate(() => scrollTo(0, 0)); const arquivo = path.join(saida, `${rotulo}-${nome}.png`); await page.screenshot({path: arquivo, fullPage: true}); resultado.capturas.push(arquivo); };
      const aba = async id => { await page.locator(`#quadros-aba-${id}`).click(); await page.locator(`#quadros-${id}`).waitFor({state: 'visible'}); await page.waitForLoadState('networkidle'); };
      await page.goto(origem); await page.locator('#area-inicio').waitFor({state: 'visible'});
      await page.selectOption('#contexto-caso', caso);
      if (viewport.width <= 720 && await page.locator('#mesa-menu').getAttribute('aria-expanded') !== 'true') await page.locator('#mesa-menu').click();
      await page.locator('#ver-quadros').click(); await page.locator('#area-quadros').waitFor({state: 'visible'});
      await aba('redacao'); await page.locator('.redacao-textos button').first().click();
      await page.locator('.redacao-afirmacao').first().waitFor();
      await foto('conferencia-texto');
      if (viewport.width > 720) {
        // Real keyboard path: from the active tab, Tab until a claim of the text has focus (focus-visible).
        await page.locator('#quadros-aba-redacao').focus();
        let chegou = false;
        for (let i = 0; i < 40 && !chegou; i++) { await page.keyboard.press('Tab'); chegou = await page.evaluate(() => !!document.activeElement?.classList?.contains('redacao-afirmacao')); }
        assert.ok(chegou, 'Tab chega a uma afirmação do texto');
        resultado.foco_afirmacao = await page.evaluate(() => {
          const b = document.activeElement, s = getComputedStyle(b);
          return {focusVisible: b.matches(':focus-visible'), outline: [s.outlineStyle, s.outlineWidth, s.outlineColor], estado: b.dataset.estado};
        });
        assert.equal(resultado.foco_afirmacao.focusVisible, true);
        assert.notEqual(resultado.foco_afirmacao.outline[0], 'none', 'foco visível na afirmação');
        const arquivo = path.join(saida, 'conferencia-foco-teclado-desktop.png');
        await page.locator('.redacao-texto').screenshot({path: arquivo}); resultado.capturas.push(arquivo);
        await page.keyboard.press('Enter');
      } else await page.locator('.redacao-afirmacao').nth(1).click();
      await page.locator('.redacao-painel').waitFor();
      const local = await page.evaluate(() => ({botoes: document.querySelectorAll('.redacao-revisao button').length,
        aviso: document.querySelector('.redacao-revisao')?.textContent || ''}));
      assert.equal(local.botoes, 0, 'modo local: sem botão de revisão humana');
      assert.match(local.aviso, /exige uma conta autenticada/);
      resultado.revisao_local = local;
      await foto('conferencia-painel');
      await aba('entrevistas'); await page.locator('.redacao-pergunta').first().waitFor();
      await foto('entrevistas');
      await page.close();
    }
    assert.deepEqual(resultado.erros, []);
    assert.deepEqual(resultado.externos, [], 'nenhuma requisição fora da Mesa');
  } finally {
    await fs.writeFile(path.join(saida, 'qa_redacao.json'), JSON.stringify(resultado, null, 2));
    await browser.close();
  }
  console.log(`${resultado.capturas.length} capturas em ${saida}`);
})().catch(e => { console.error(e); process.exit(1); });
