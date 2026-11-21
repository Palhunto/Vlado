// Proposta de Documentos (W02: acervo, envio e busca numa tela só, que absorve "Cadastrar arquivos") para
// aprovação do dono, na linguagem do canvas, com os tokens de docs/design/novas/fonte/base.css.
// Uso: NODE_PATH=.ferramentas/node/node_modules node docs/design/aprovacao/ferramentas/gerar_documentos.cjs
const {chromium} = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const url = require('node:url');
const {aplicarDecisoes} = require(path.join(__dirname, '..', '..', 'novas', 'ferramentas', 'decisoes.cjs'));

const aprovacao = path.resolve(__dirname, '..');
const design = path.resolve(aprovacao, '..');
const destino = path.join(aprovacao, 'documentos');
const fonteDir = path.join(__dirname, 'fonte');
const rel = alvo => path.relative(fonteDir, alvo).split(path.sep).join('/');
const FD = rel(path.resolve(design, '..', '..', 'interface', 'fonts'));
const BASE = rel(path.join(design, 'novas', 'fonte', 'base.css'));
const icones = Object.fromEntries(JSON.parse(fs.readFileSync(path.join(design, 'icones', 'ferramentas', 'icones.json'), 'utf8')).icones.map(i => [i.nome, i.d]));
const svg = (d, tam, traco = 2) => `<svg aria-hidden="true" width="${tam}" height="${tam}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="${traco}" stroke-linecap="round" stroke-linejoin="round" style="flex:none"><path d="${d}"/></svg>`;
const CHECK = 'M5 12l5 5L20 7', MENU = 'M4 7h16M4 12h16M4 17h16';
const FAIXA = '<div class="faixa-derivado">Derivado · aguarda aprovação do dono</div>';
const CSS = `.estado{display:inline-flex;align-items:center;gap:6px}
table.dados{width:100%;border-collapse:collapse}table.dados th,table.dados td{padding:12px 16px;border-bottom:1px solid var(--theme-line);text-align:left;vertical-align:middle}
table.dados th{font-size:14px;color:var(--theme-muted);font-weight:600;background:var(--theme-reading)}table.dados tr:last-child td{border-bottom:0}
.busca{height:44px;padding:0 12px;border-radius:8px;border:1px solid var(--theme-input-line);background:var(--theme-surface);font:inherit;color:var(--theme-text)}
.busca::placeholder{color:var(--theme-muted)}`;
const pagina = (tema, corpo) => `<!doctype html><html lang="pt-BR" data-theme="${tema}"><head><meta charset="utf-8"><style>@font-face{font-family:"Source Serif 4";src:url('${FD}/SourceSerif4-Roman.ttf') format('truetype');font-weight:200 900}
@font-face{font-family:"Source Sans 3";src:url('${FD}/SourceSans3-Upright.otf') format('opentype');font-weight:200 900}${CSS}</style><link rel="stylesheet" href="${BASE}"></head><body><div id="prancha" style="display:inline-block;vertical-align:top">${corpo}${FAIXA}</div></body></html>`;

const lateral = `<nav class="lateral" aria-label="Áreas" style="flex:none"><div class="marca" style="padding:0 8px">Vlado<span>.</span></div><div class="areas">${[['Visão geral'], ['Documentos', '<span class="cont cont-pilula">12</span>'], ['Perguntar'], ['Conferir', '<span class="cont cont-pilula">4</span>'], ['Quadros'], ['Caderno'], ['Pedidos e prazos', '<span class="cont b" style="color:var(--theme-warning)">1 vence</span>']].map(([n, x = '']) => `<a href="#"${n === 'Documentos' ? ' aria-current="page"' : ''}>${n} ${x}</a>`).join('')}</div>
<div style="margin-top:auto;display:flex;flex-direction:column;gap:12px"><div class="cota"><div style="display:flex;justify-content:space-between;gap:8px;font-size:14px"><span class="sec">Cota do mês</span><span class="b">R$ 18,40 de R$ 50</span></div><div class="medidor" role="img" aria-label="37% da cota usada"><div style="width:37%"></div></div></div>
<a href="#" class="perfil"><span class="avatar" aria-hidden="true">AL</span><span class="duas-linhas"><span class="b">Ana Lima</span><span class="p14 sec">Repórter · Redação Serena</span></span></a></div></nav>`;

// Três estados de leitura, sempre com sinal e texto (W02, regra 5); ◐ e ✕ vêm do conjunto de ícones, ✓ e ○ são texto.
const leitura = {
  arquivo: `<span class="estado" style="color:var(--theme-accent)">${svg(CHECK, 16, 2.5)}<span>Texto do próprio arquivo</span></span>`,
  ocr: `<span class="estado b" style="color:var(--theme-warning)">${svg(icones['sinal-parcial'], 16, 2)}<span>Lida por OCR: confira números</span></span>`,
  sem: '<span class="estado sec">○ Imagem sem leitura</span>',
};
const docs = [['Contrato 041/2025', '8', 'arquivo', '<a href="#" class="b">Abrir original</a>'], ['Medição nº 3', '1', 'ocr', '<a href="#" class="b">Abrir original</a>'], ['Foto do canteiro.jpg', '1', 'sem', '<button type="button" class="bt bt-s">Ler com OCR</button>']];
const barra = (pct, cor = 'var(--theme-accent)') => `<div class="medidor" role="img" aria-label="${pct}% enviado" style="height:8px;flex:1;min-width:120px"><div style="width:${pct}%;height:8px;background:${cor}"></div></div>`;
const envio = movel => `<section class="cartao" aria-busy="true" style="background:var(--theme-background);padding:16px 20px;display:flex;flex-direction:column;gap:12px">
<div style="display:flex;align-items:baseline;gap:8px;flex-wrap:wrap"><span class="b">Enviando 3 arquivos</span><span class="p14 sec">Você pode continuar trabalhando e sair desta tela.</span></div>
${[['edital_2025.pdf', barra(100), `<span class="estado" style="color:var(--theme-accent)">${svg(CHECK, 16, 2.5)}Pronto, 14 pág.</span>`], ['medicao_04_digitalizada.pdf', barra(40), '<span class="sec">Lendo pág. 2 de 5</span>']]
    .map(([n, b, e]) => `<div style="display:${movel ? 'grid;grid-template-columns:1fr;gap:6px' : 'grid;grid-template-columns:260px 1fr 200px;gap:16px;align-items:center'}"><span>${n}</span>${b}${e}</div>`).join('')}
<div style="display:${movel ? 'flex;flex-direction:column;gap:8px' : 'grid;grid-template-columns:260px 1fr auto;gap:16px;align-items:center'}"><span>planilha.xlsm</span><span class="estado b" style="color:var(--theme-danger)">${svg(icones['sinal-sem-suporte'], 16, 2.2)}Tem macro e não foi lida. O original ficou guardado.</span><button type="button" class="bt bt-s"${movel ? ' style="align-self:flex-start"' : ''}>O que fazer</button></div>
<div style="display:flex;align-items:baseline;gap:8px;flex-wrap:wrap;border-top:1px solid var(--theme-line);padding-top:12px"><span class="p14">Recibo do lote: <strong>2 de 3 cadastrados</strong>, 1 pendente. É conferido antes da primeira pergunta.</span><a href="#" class="p14 b" style="margin-left:auto">Ver recibo</a></div></section>`;
const zona = movel => movel
  ? `<div style="display:flex;flex-direction:column;gap:6px"><button type="button" class="bt bt-p bt-g bt-cheio">Escolher arquivos</button><span class="p14 sec" style="text-align:center">PDF, DOCX, XLSX, CSV, TXT e imagens · até 50 MB por arquivo</span></div>`
  : `<div style="border:2px dashed var(--theme-input-line);border-radius:12px;padding:24px;display:flex;flex-direction:column;align-items:center;gap:4px;background:var(--theme-surface)"><span><strong>Arraste arquivos para cá</strong> ou <a href="#" class="b">escolha no computador</a></span><span class="p14 sec">PDF, DOCX, XLSX, CSV, TXT e imagens · até 50 MB por arquivo</span></div>`;
const busca = '<label style="display:flex;flex-direction:column;gap:4px;flex:1;max-width:420px"><span class="p14 b sec">Buscar no texto dos documentos</span><input class="busca" type="search" placeholder="Ex.: medição, aditivo, Construtora Alfa"></label>';

const d1440 = () => `<div class="pr" style="width:1440px;height:900px;display:flex">${lateral}<div style="flex:1;min-width:0;display:flex;flex-direction:column">
<header style="height:64px;flex:none;padding:0 32px;display:flex;align-items:center;gap:16px;background:var(--theme-surface);border-bottom:1px solid var(--theme-line)"><div class="duas-linhas"><span class="p14 sec">Apuração</span><span class="b">Vila Serena — contrato de pavimentação (sintética)</span></div></header>
<main style="flex:1;min-height:0;padding:28px 32px;display:flex;flex-direction:column;gap:16px">
<div style="display:flex;align-items:flex-end;gap:16px"><div style="display:flex;align-items:baseline;gap:12px"><h1 class="serifa" style="margin:0;font-size:28px;font-weight:600;line-height:1.2">Documentos</h1><span class="p14 sec">12 de 60</span></div><div style="margin-left:auto;display:flex;flex:1;justify-content:flex-end">${busca}</div></div>
${zona(false)}${envio(false)}
<div class="cartao" style="overflow:hidden"><table class="dados"><thead><tr><th scope="col">Documento</th><th scope="col">Páginas</th><th scope="col">Leitura</th><th scope="col"><span class="sr-only" style="position:absolute;left:-9999px">Ação</span></th></tr></thead>
<tbody>${docs.map(([n, p, l, a]) => `<tr><td>${n}</td><td>${p}</td><td>${leitura[l]}</td><td style="text-align:right">${a}</td></tr>`).join('')}</tbody></table></div>
<span class="p14 sec">Hash, identificador e versão de cada documento ficam em "Detalhes técnicos", ao abrir o documento.</span></main></div></div>`;
const d390 = () => `<div class="pr" style="width:390px;min-height:844px;display:flex;flex-direction:column"><header class="topo"><button type="button" class="bt-ic" aria-label="Abrir menu">${svg(MENU, 22)}</button><div class="duas-linhas"><span class="p14 sec">Apuração</span><span class="nome">Vila Serena</span></div><span class="p14 sec" style="margin-left:auto;padding-right:4px;white-space:nowrap">R$ 18,40 de 50</span></header>
<main style="padding:20px 16px;display:flex;flex-direction:column;gap:14px"><div style="display:flex;align-items:baseline;gap:12px"><h1 class="serifa" style="margin:0;font-size:28px;font-weight:600;line-height:1.2">Documentos</h1><span class="p14 sec">12 de 60</span></div>
${busca.replace('max-width:420px', '')}${zona(true)}${envio(true)}
<ul style="margin:0;padding:0;list-style:none;display:flex;flex-direction:column;gap:10px">${docs.map(([n, p, l, a]) => `<li class="cartao" style="padding:14px 16px;display:flex;flex-direction:column;gap:6px"><span class="b">${n}</span><span class="p14 sec">${p} ${p === '1' ? 'página' : 'páginas'}</span>${leitura[l]}<div>${a}</div></li>`).join('')}</ul></main></div>`;

(async () => {
  const browser = await chromium.launch({headless: true, executablePath: chromium.executablePath()});
  for (const [tema, nome] of [['light', 'claro'], ['dark', 'escuro']]) {
    for (const [w, f] of [[1440, d1440], [390, d390]]) {
      const arq = `proposta-${nome}-${w}`;
      const html = path.join(fonteDir, `documentos-${arq}.html`);
      fs.writeFileSync(html, aplicarDecisoes(pagina(tema, f()), {escuro: tema === 'dark'}));
      const page = await browser.newPage({viewport: {width: w, height: 900}, deviceScaleFactor: 1});
      await page.route('**/*', r => r.request().url().startsWith('file:') ? r.continue() : r.abort());
      await page.goto(url.pathToFileURL(html).href);
      await page.evaluate(() => document.fonts.ready);
      await page.locator('#prancha').screenshot({path: path.join(destino, `${arq}.png`)});
      const caixa = await page.locator('#prancha').boundingBox();
      console.log(arq, Math.round(caixa.width), '×', Math.round(caixa.height));
      await page.close();
    }
  }
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
