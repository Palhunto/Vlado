// Renderiza as sete telas finais do canvas com as decisões do dono de 21/11/2026 aplicadas (novas/ferramentas/decisoes.cjs),
// em docs/design/referencia/com-decisoes/, ao lado das originais de telas/ (que continuam sendo o registro do canvas).
// Uso: NODE_PATH=.ferramentas/node/node_modules node docs/design/referencia/ferramentas/renderizar_com_decisoes.cjs
const {chromium} = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const url = require('node:url');
const {aplicarDecisoes, caminhoDeVolta} = require(path.join(__dirname, '..', '..', 'novas', 'ferramentas', 'decisoes.cjs'));

const referencia = path.resolve(__dirname, '..');
const canvas = path.join(referencia, 'canvas');
const saida = path.join(referencia, 'com-decisoes');
fs.mkdirSync(saida, {recursive: true});
const fontes = path.relative(saida, path.resolve(referencia, '..', '..', '..', 'interface', 'fonts')).split(path.sep).join('/');
const TELAS = {
  Main: '01-conferir-achado-1440', Inicio: '02-visao-geral-1440', Tokens: '03-design-system-revisado-1440',
  Celular: '04-pergunta-celular-escuro-390', Entrar: '05-entrar-390', Mapa: '06-mapa-de-relacoes-1440', Tempo: '07-linha-do-tempo-1440',
};

(async () => {
  const browser = await chromium.launch({headless: true, executablePath: chromium.executablePath()});
  for (const [nome, arq] of Object.entries(TELAS)) {
    const raw = fs.readFileSync(path.join(canvas, `${nome}.dc.html`), 'utf8');
    const prev = JSON.parse(raw.match(/data-props='([^']*)'/)[1]).$preview;
    let inner = raw.match(/<x-dc>([\s\S]*)<\/x-dc>/)[1];
    const helmet = (inner.match(/<helmet>([\s\S]*?)<\/helmet>/) || ['', ''])[1].replace(/<link[^>]*fonts\.googleapis[^>]*>/g, '');
    inner = caminhoDeVolta(inner.replace(/<helmet>[\s\S]*?<\/helmet>/, ''));
    // Entrar: o conteúdo passa da moldura de 844 px (P11.5); a versão com decisões mostra a página inteira.
    if (nome === 'Entrar') inner = inner.replace('height: 844px;', 'min-height: 844px;');
    const html = aplicarDecisoes(`<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><style>@font-face{font-family:"Source Serif 4";src:url('${fontes}/SourceSerif4-Roman.ttf') format('truetype');font-weight:200 900}
@font-face{font-family:"Source Sans 3";src:url('${fontes}/SourceSans3-Upright.otf') format('opentype');font-weight:200 900}</style>${helmet}</head><body>${inner}</body></html>`, {escuro: nome === 'Celular'});
    const tmp = path.join(saida, '_tmp.html');
    fs.writeFileSync(tmp, html);
    const page = await browser.newPage({viewport: {width: prev.width, height: prev.height}, deviceScaleFactor: 1});
    await page.route('**/*', r => r.request().url().startsWith('file:') ? r.continue() : r.abort());
    await page.goto(url.pathToFileURL(tmp).href);
    await page.evaluate(() => document.fonts.ready);
    await page.locator('body > div').first().screenshot({path: path.join(saida, `${arq}.png`)});
    console.log(arq);
    await page.close();
  }
  fs.unlinkSync(path.join(saida, '_tmp.html'));
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
