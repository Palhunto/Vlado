// Gera os SVGs do conjunto de ícones do Vlado a partir de icones.json, a prancha de conferência
// (claro e escuro, 16/24/32 px) e a comparação pixel a pixel com a geometria do canvas.
// Uso: NODE_PATH=.ferramentas/node/node_modules node docs/design/icones/ferramentas/gerar_icones.cjs
const {chromium} = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const url = require('node:url');

const raiz = path.resolve(__dirname, '..');
const fontes = path.resolve(raiz, '..', '..', '..', 'interface', 'fonts');
const dados = JSON.parse(fs.readFileSync(path.join(__dirname, 'icones.json'), 'utf8'));
const G = dados.grade;

const svgArquivo = d => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${G.viewBox}" fill="none" stroke="currentColor" stroke-width="${G.traco}" stroke-linecap="round" stroke-linejoin="round"><path d="${d}"/></svg>\n`;
const svgEmLinha = (d, tam, traco = G.traco, extra = '') => `<svg viewBox="${G.viewBox}" width="${tam}" height="${tam}" fill="none" stroke="currentColor" stroke-width="${traco}" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"${extra}><path d="${d}"/></svg>`;

for (const i of dados.icones) fs.writeFileSync(path.join(raiz, `${i.nome}.svg`), svgArquivo(i.d));

const porNome = Object.fromEntries(dados.icones.map(i => [i.nome, i]));
const FD = fontes.split(path.sep).join('/');
const temas = {
  claro: {fundo: '#fffefa', texto: '#202c29', sec: '#5f6a63', linha: '#dddfd6', verde: '#1e4d3e', sobre: '#ffffff', suave: '#e8eee6', borda: '#74837a',
    pessoa: '#1d8058', empresa: '#5b5fb8', orgao: '#b0508a', aviso: '#8e4b28', avisoFundo: '#f7ecdf'},
  escuro: {fundo: '#202823', texto: '#eae9df', sec: '#a8b3a9', linha: '#3c4940', verde: '#a8c79d', sobre: '#172315', suave: '#2c3c2e', borda: '#8a9c8f',
    pessoa: '#3fa877', empresa: '#8487e6', orgao: '#d46a9c', aviso: '#e6bc7a', avisoFundo: '#372e21'},
};

function painel(nome, t) {
  const linhas = dados.icones.map(i => `<tr><td class="n">${i.nome}<br><span>${i.origem}</span></td>${[16, 24, 32].map(s => `<td>${svgEmLinha(i.d, s)}</td>`).join('')}</tr>`).join('');
  const no = (nomeIcone, forma, cor) => {
    const shape = forma === 'circulo' ? `<circle cx="18" cy="18" r="18" fill="${cor}"/>` : `<rect width="36" height="36" rx="${forma === 'quadrado' ? 9 : 3}" fill="${cor}"/>`;
    const c = porNome[nomeIcone].canvas;
    return `<svg width="36" height="36" viewBox="0 0 36 36" aria-hidden="true">${shape}<g transform="translate(${-c.dx} ${-c.dy})" fill="none" stroke="${t.sobre}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="${porNome[nomeIcone].d}"/></g></svg>`;
  };
  const rotulo = (n, txt) => `<span class="pilula">${svgEmLinha(porNome[n].d, 14, 2.2)}${txt}</span>`;
  const marco = (n, cheio) => `<span class="marco${cheio ? '' : ' vazado'}">${svgEmLinha(porNome[n].d, 18, 2)}</span>`;
  return `<section style="background:${t.fundo};color:${t.texto};--sec:${t.sec};--linha:${t.linha};--verde:${t.verde};--sobre:${t.sobre};--borda:${t.borda}">
<h2>Tema ${nome}</h2>
<table><thead><tr><th></th><th>16</th><th>24</th><th>32</th></tr></thead><tbody>${linhas}</tbody></table>
<h3>No contexto do canvas</h3>
<div class="ctx">${no('pessoa', 'circulo', t.pessoa)}${no('empresa', 'quadrado', t.empresa)}${no('orgao-publico', 'reto', t.orgao)}</div>
<div class="ctx">${rotulo('relacao-socio', 'Sócio')}${rotulo('contrato', 'Contrato')}${rotulo('relacao-parentesco', 'Parentesco')}${rotulo('relacao-cargo', 'Cargo')}${rotulo('relacao-vinculo', 'Vinculada')}${rotulo('pagamento', 'Pagamento')}</div>
<div class="ctx">${marco('contrato', true)}${marco('pagamento', true)}${marco('evento-aditivo', false)}${marco('evento-pedido', true)}${marco('data', true)}<span class="lac" style="color:${t.aviso};background:${t.avisoFundo}">${svgEmLinha(porNome.lacuna.d, 24)}</span></div>
</section>`;
}

const css = `@font-face{font-family:"Source Sans 3";src:url('file:///${FD}/SourceSans3-Upright.otf') format('opentype');font-weight:200 900}
@font-face{font-family:"Source Serif 4";src:url('file:///${FD}/SourceSerif4-Roman.ttf') format('truetype');font-weight:200 900}
body{margin:0;font-family:"Source Sans 3",sans-serif;font-size:14px}main{display:flex;width:960px}
section{flex:1;padding:24px 28px}h2{font:600 22px "Source Serif 4",serif;margin:0 0 12px}h3{font-size:14px;font-weight:600;letter-spacing:.6px;text-transform:uppercase;color:var(--sec);margin:20px 0 10px}
table{border-collapse:collapse;width:100%}th{font-weight:600;color:var(--sec);text-align:left;padding:4px 8px;border-bottom:1px solid var(--linha)}
td{padding:6px 8px;border-bottom:1px solid var(--linha);vertical-align:middle;height:34px}td svg{display:block}.n{line-height:1.2}.n span{color:var(--sec)}
.ctx{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:10px}
.pilula{display:inline-flex;align-items:center;gap:6px;height:28px;padding:0 10px;border:1px solid var(--borda);border-radius:999px;font-weight:600}
.marco{width:36px;height:36px;border-radius:999px;background:var(--verde);color:var(--sobre);display:flex;align-items:center;justify-content:center}
.marco.vazado{background:transparent;border:2px solid var(--verde);color:var(--verde);box-sizing:border-box}
.lac{width:36px;height:36px;border-radius:8px;display:flex;align-items:center;justify-content:center}`;

const html = `<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><style>${css}</style></head><body><main>${painel('claro', temas.claro)}${painel('escuro', temas.escuro)}</main></body></html>`;

(async () => {
  const browser = await chromium.launch({headless: true, executablePath: chromium.executablePath()});
  const page = await browser.newPage({viewport: {width: 960, height: 800}, deviceScaleFactor: 1});
  await page.route('**/*', r => r.request().url().startsWith('file:') || r.request().url().startsWith('data:') ? r.continue() : r.abort());
  const tmp = path.join(__dirname, '_prancha.html');
  fs.writeFileSync(tmp, html);
  await page.goto(url.pathToFileURL(tmp).href);
  await page.evaluate(() => document.fonts.ready);
  await page.locator('main').screenshot({path: path.join(raiz, 'prancha-icones.png')});
  fs.unlinkSync(tmp);

  // Comparação: geometria do canvas (com a translação registrada) contra o arquivo, 96 px, traço 2.
  const pares = dados.icones.filter(i => i.canvas).map(i => {
    const c = i.canvas;
    const circ = c.circulo ? `<circle cx="${c.circulo[0]}" cy="${c.circulo[1]}" r="${c.circulo[2]}"/>` : '';
    const original = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${-c.dx} ${-c.dy} 24 24" width="96" height="96" fill="none" stroke="#000" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${circ}<path d="${c.d}"/></svg>`;
    const novo = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="96" height="96" fill="none" stroke="#000" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="${i.d}"/></svg>`;
    return {nome: i.nome, original, novo};
  });
  const resultado = await page.evaluate(async pares => {
    const desenhar = svg => new Promise(res => {
      const img = new Image();
      img.onload = () => { const cv = document.createElement('canvas'); cv.width = cv.height = 96; const cx = cv.getContext('2d'); cx.drawImage(img, 0, 0); res(cx.getImageData(0, 0, 96, 96).data); };
      img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
    });
    const saida = [];
    for (const p of pares) {
      const a = await desenhar(p.original), b = await desenhar(p.novo);
      // pixelsDiferentes: alfa difere mais de 8/255 (inclui suavização de borda);
      // pixelsForaDaForma: difere mais de 100/255 (um lado tem traço e o outro não).
      let dif = 0, fora = 0, maior = 0, tinta = 0;
      for (let i = 3; i < a.length; i += 4) { const d = Math.abs(a[i] - b[i]); if (d > 8) dif++; if (d > 100) fora++; maior = Math.max(maior, d); if (a[i] > 0) tinta++; }
      saida.push({nome: p.nome, pixelsDiferentes: dif, pixelsForaDaForma: fora, maiorDiferencaAlfa: maior, pixelsComTinta: tinta});
    }
    return saida;
  }, pares);
  fs.writeFileSync(path.join(__dirname, 'comparacao-canvas.json'), JSON.stringify(resultado, null, 1) + '\n');
  console.table(resultado);
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
