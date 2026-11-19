'use strict';
// Browser part of qa_quadros.py: opens each evidence board on desktop (1440×1000) and phone
// (390×844), checks the screen loaded without page errors or external requests, and saves one
// capture per board and size. Synthetic data only; the captures are not investigation documents.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs/promises');
const [origem, saida, caso, casoComparacao, chrome] = process.argv.slice(2);

(async () => {
  const browser = await chromium.launch({headless: true, ...(chrome ? {executablePath: chrome} : {})});
  const resultado = {capturas: [], erros: [], externos: []};
  try {
    for (const [nome, viewport] of [['desktop', {width: 1440, height: 1000}], ['celular', {width: 390, height: 844}]]) {
      const page = await browser.newPage({viewport});
      page.on('pageerror', e => resultado.erros.push(`${nome}: ${e.message}`));
      page.on('request', r => { if (!r.url().startsWith(origem) && !r.url().startsWith('blob:') && !r.url().startsWith('data:')) resultado.externos.push(r.url()); });
      const ir = async () => {
        if (viewport.width <= 720 && await page.locator('#mesa-menu').getAttribute('aria-expanded') !== 'true') await page.locator('#mesa-menu').click();
        await page.locator('#ver-quadros').click();
        await page.locator('#area-quadros').waitFor({state: 'visible'});
      };
      // Full-page captures start at the top: otherwise the sticky header is drawn mid-page.
      const foto = async rotulo => { await page.evaluate(() => scrollTo(0, 0)); const arquivo = path.join(saida, `${rotulo}-${nome}.png`); await page.screenshot({path: arquivo, fullPage: true}); resultado.capturas.push(arquivo); };
      const aba = async id => { await page.locator(`#quadros-aba-${id}`).click(); await page.locator(`#quadros-${id}`).waitFor({state: 'visible'}); await page.waitForLoadState('networkidle'); };
      await page.goto(origem); await page.locator('#area-inicio').waitFor({state: 'visible'});
      await page.selectOption('#contexto-caso', caso);
      await ir();
      await aba('hipoteses'); await page.locator('.quadro-hipotese').first().waitFor(); await foto('hipoteses');
      await aba('tempo'); await page.locator('.tempo-evento').first().waitFor(); await foto('linha-do-tempo');
      await aba('tabelas'); await page.locator('td.tabela-celula').first().waitFor();
      await page.locator('td.estado-corrigido_manual').first().focus(); await foto('tabela');
      await aba('mapa'); await page.locator('.mapa-lista').waitFor();
      if (viewport.width > 720) {
        assert.equal(await page.locator('svg.mapa-svg').isVisible(), true);
        // Real keyboard path: from the active tab, Tab until a link of the map has focus (focus-visible).
        await page.locator('#quadros-aba-mapa').focus();
        let chegou = false;
        for (let i = 0; i < 40 && !chegou; i++) { await page.keyboard.press('Tab'); chegou = await page.evaluate(() => !!document.activeElement?.closest?.('.mapa-ligacao')); }
        assert.ok(chegou, 'Tab chega a uma ligação do mapa');
        const foco = await page.evaluate(() => {
          const g = document.activeElement, linha = g.querySelector('.mapa-linha'), halo = g.querySelector('.mapa-alvo');
          const s = getComputedStyle(g), l = getComputedStyle(linha), h = getComputedStyle(halo);
          return {focusVisible: g.matches(':focus-visible'), outline: s.outlineStyle, linha: [l.stroke, l.strokeWidth], halo: [h.stroke, h.strokeOpacity, h.strokeWidth],
            painel: document.querySelector('.mapa-detalhe').textContent.trim()};
        });
        resultado.foco_mapa = foco;
        assert.equal(foco.focusVisible, true);
        assert.equal(foco.outline, 'none', 'sem o retângulo do contorno padrão');
        assert.equal(foco.linha[1], '4px', 'linha destacada no foco');
        assert.match(foco.painel, /Escolha uma ligação/, 'o foco não troca o painel ao vivo');
        const arquivo = path.join(saida, 'mapa-foco-teclado-desktop.png');
        await page.locator('.mapa-visual').screenshot({path: arquivo}); resultado.capturas.push(arquivo);
      }
      else assert.equal(await page.locator('svg.mapa-svg').isVisible(), false, 'no celular o mapa é a lista');
      await foto('mapa');
      await page.selectOption('#contexto-caso', casoComparacao);
      await ir(); await aba('comparador'); await page.locator('.comparar-form').waitFor();
      await page.locator('.comparar-form button[type=submit]').click(); await page.locator('.comparar-alteracao').first().waitFor();
      await foto('comparador');
      await page.close();
    }
    assert.deepEqual(resultado.erros, []);
    assert.deepEqual(resultado.externos, [], 'nenhuma requisição fora da Mesa');
  } finally {
    await fs.writeFile(path.join(saida, 'qa_quadros.json'), JSON.stringify(resultado, null, 2));
    await browser.close();
  }
  console.log(`${resultado.capturas.length} capturas em ${saida}`);
})().catch(e => { console.error(e); process.exit(1); });
