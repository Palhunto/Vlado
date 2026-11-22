// Captura a Mesa como está hoje, só com dados sintéticos, numa porta local (127.0.0.1).
// Uma captura por vez, recortada na janela (1440 × 900 ou 390 × 844), nos temas claro e escuro.
// Uso: NODE_PATH=.ferramentas/node/node_modules node docs/design/aprovacao/ferramentas/capturar_mesa.cjs <porta> <saída> <area[:caso]>...
//   ex.: ... 55598 docs/design/aprovacao apuracao:vila_serena_sintetico quadros:vila_serena_sintetico
const {chromium} = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const [porta, saida, ...alvos] = process.argv.slice(2);
const JANELAS = [{nome: '1440', width: 1440, height: 900}, {nome: '390', width: 390, height: 844, mobile: true}];
const TEMAS = ['light', 'dark'];
const NOME_TEMA = {light: 'claro', dark: 'escuro'};

(async () => {
  const browser = await chromium.launch({headless: true, executablePath: chromium.executablePath()});
  for (const alvo of alvos) {
    const [area, caso, pasta = area] = alvo.split(':');
    const destino = path.join(saida, pasta);
    fs.mkdirSync(destino, {recursive: true});
    for (const janela of JANELAS) {
      for (const tema of TEMAS) {
        const contexto = await browser.newContext({viewport: {width: janela.width, height: janela.height}, deviceScaleFactor: 1, isMobile: !!janela.mobile, hasTouch: !!janela.mobile});
        await contexto.addInitScript(t => { try { localStorage.setItem('apuracao:tema', t); } catch (_) {} }, tema);
        const page = await contexto.newPage();
        await page.route('**/*', r => r.request().url().startsWith(`http://127.0.0.1:${porta}/`) ? r.continue() : r.abort());
        const url = `http://127.0.0.1:${porta}/?area=${area}${caso ? `&caso=${caso}` : ''}`;
        await page.goto(url, {waitUntil: 'load'});
        await page.evaluate(() => document.fonts.ready);
        await page.waitForTimeout(1500);  // algumas áreas consultam o servidor sem parar; espera fixa
        const arquivo = path.join(destino, `atual-${NOME_TEMA[tema]}-${janela.nome}.png`);
        await page.screenshot({path: arquivo, fullPage: false});
        const titulo = await page.evaluate(() => (document.querySelector('main h1, h1') || {}).textContent || '');
        console.log(path.relative(saida, arquivo), '·', titulo.trim().slice(0, 60));
        await contexto.close();
      }
    }
  }
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
