// Mede o que passa da moldura de cada prancheta e, quando passa, captura a página inteira.
const {chromium} = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const url = require('node:url');
const [src, out, fontsDir] = process.argv.slice(2);
const FD = fontsDir.split(String.fromCharCode(92)).join('/');
const fontCss = `@font-face{font-family:"Source Serif 4";src:url('file:///${FD}/SourceSerif4-Roman.ttf') format('truetype');font-weight:200 900}
@font-face{font-family:"Source Sans 3";src:url('file:///${FD}/SourceSans3-Upright.otf') format('opentype');font-weight:200 900}`;
const boards = JSON.parse(fs.readFileSync(path.join(src, 'canvas.json'), 'utf8')).boards;
(async () => {
  const browser = await chromium.launch({headless: true, executablePath: chromium.executablePath()});
  for (const file of Object.keys(boards)) {
    const raw = fs.readFileSync(path.join(src, file), 'utf8');
    const prev = JSON.parse(raw.match(/data-props='([^']*)'/)[1]).$preview;
    let inner = raw.match(/<x-dc>([\s\S]*)<\/x-dc>/)[1];
    const helmet = (inner.match(/<helmet>([\s\S]*?)<\/helmet>/) || ['', ''])[1].replace(/<link[^>]*fonts\.googleapis[^>]*>/g, '');
    inner = inner.replace(/<helmet>[\s\S]*?<\/helmet>/, '');
    const html = `<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><style>${fontCss}</style>${helmet}</head><body>${inner}</body></html>`;
    const page = await browser.newPage({viewport: {width: prev.width, height: 3000}, deviceScaleFactor: 1});
    await page.route('**/*', r => r.request().url().startsWith('file:') ? r.continue() : r.abort());
    const tmp = path.join(out, '_tmp.html');
    fs.writeFileSync(tmp, html);
    await page.goto(url.pathToFileURL(tmp).href);
    await page.evaluate(() => document.fonts.ready);
    const info = await page.evaluate(() => {
      const root = document.body.firstElementChild;
      const rb = root.getBoundingClientRect();
      let fundo = rb.bottom;
      const cortes = [];
      for (const el of root.querySelectorAll('*')) {
        const b = el.getBoundingClientRect();
        if (b.width && b.height) fundo = Math.max(fundo, b.bottom);
        const cs = getComputedStyle(el);
        if (el.children.length === 0 && el.textContent.trim() && (el.scrollHeight > el.clientHeight + 2) && cs.overflow === 'visible' && el.clientHeight) cortes.push(el.textContent.trim().slice(0, 40));
      }
      // texto que passa da caixa do pai com altura fixa
      for (const el of root.querySelectorAll('div,span,a,button')) {
        const st = el.getAttribute('style') || '';
        if (/(^|;|\s)height:\s*\d+px/.test(st) && el.scrollHeight > el.clientHeight + 2) cortes.push('caixa: ' + el.textContent.trim().replace(/\s+/g, ' ').slice(0, 50));
      }
      return {altura: rb.height, fundo: Math.ceil(fundo), cortes: [...new Set(cortes)]};
    });
    console.log(file, JSON.stringify(info));
    if (info.fundo > info.altura + 1) {
      await page.screenshot({path: path.join(out, file.replace('.dc.html', '') + '-inteira.png'), clip: {x: 0, y: 0, width: prev.width, height: info.fundo}});
    }
    await page.close();
  }
  fs.unlinkSync(path.join(out, '_tmp.html'));
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
