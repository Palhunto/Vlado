// Pontos que ficaram abertos no caderno aprovado (P14.2 a P14.4), para nova aprovação do dono:
// onde ficam "Trechos com fonte e contribuições", o modo "Escrever" e o quarto sinal, "revisada".
// Uso: NODE_PATH=.ferramentas/node/node_modules node docs/design/aprovacao/ferramentas/gerar_caderno_aberto.cjs
const {chromium} = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const url = require('node:url');
const {aplicarDecisoes} = require(path.join(__dirname, '..', '..', 'novas', 'ferramentas', 'decisoes.cjs'));

const aprovacao = path.resolve(__dirname, '..');
const design = path.resolve(aprovacao, '..');
const destino = path.join(aprovacao, 'caderno');
const fonteDir = path.join(__dirname, 'fonte');
const rel = alvo => path.relative(fonteDir, alvo).split(path.sep).join('/');
const FD = rel(path.resolve(design, '..', '..', 'interface', 'fonts'));
const BASE = rel(path.join(design, 'novas', 'fonte', 'base.css'));
const svg = (d, tam, traco = 2) => `<svg aria-hidden="true" width="${tam}" height="${tam}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="${traco}" stroke-linecap="round" stroke-linejoin="round" style="flex:none"><path d="${d}"/></svg>`;
const CHECK = 'M5 12l5 5L20 7', MENU = 'M4 7h16M4 12h16M4 17h16';
const FAIXA = '<div class="faixa-derivado" style="background:#1e4d3e">Derivado · aprovado pelo dono em 21/11/2026</div>';
const CSS = `.af{text-decoration:none;color:inherit;padding:1px 0;text-underline-offset:6px;text-decoration-thickness:2px;text-decoration-line:underline}
.af-ok{text-decoration-color:var(--theme-accent)}.af-ex{text-decoration-style:dashed;text-decoration-color:var(--theme-warning)}.af-sf{text-decoration-style:dotted;text-decoration-color:var(--theme-input-line)}
.af-rev{text-decoration-style:double;text-decoration-color:var(--theme-accent);text-decoration-thickness:1.5px}
.marca-af{font:600 14px/1 var(--sans);white-space:nowrap;margin-left:6px;display:inline-flex;align-items:center;gap:4px;vertical-align:2px}
.seg{display:flex;padding:4px;gap:4px;border-radius:12px;background:var(--theme-reading)}.seg button{flex:1;height:40px;border:0;border-radius:8px;background:transparent;color:var(--theme-text)}
.seg button[aria-pressed=true]{background:var(--theme-surface);box-shadow:var(--sombra-cartao);font-weight:600}
.trecho{background:var(--theme-surface);border:1px solid var(--theme-line);border-radius:12px;padding:12px 14px;display:flex;gap:10px;align-items:flex-start}
.trecho input{width:20px;height:20px;margin:2px 0 0;accent-color:var(--theme-accent);flex:none}
.ferr{display:flex;align-items:center;gap:4px;padding:8px 12px;border-bottom:1px solid var(--theme-line);flex-wrap:wrap}
.ferr button{height:40px;min-width:40px;padding:0 10px;border-radius:8px;border:0;background:transparent;color:var(--theme-text)}
.fonte-chip{font:600 14px/1 var(--sans);background:var(--theme-soft);color:var(--theme-accent);border-radius:999px;padding:2px 8px;text-decoration:none;vertical-align:2px}`;
const pagina = (tema, corpo) => `<!doctype html><html lang="pt-BR" data-theme="${tema}"><head><meta charset="utf-8"><style>@font-face{font-family:"Source Serif 4";src:url('${FD}/SourceSerif4-Roman.ttf') format('truetype');font-weight:200 900}
@font-face{font-family:"Source Sans 3";src:url('${FD}/SourceSans3-Upright.otf') format('opentype');font-weight:200 900}${CSS}</style><link rel="stylesheet" href="${BASE}"></head><body><div id="prancha" style="display:inline-block;vertical-align:top">${corpo}${FAIXA}</div></body></html>`;

const lateral = `<nav class="lateral" aria-label="Áreas" style="flex:none"><div class="marca" style="padding:0 8px">Vlado<span>.</span></div><div class="areas">${[['Visão geral'], ['Documentos', '<span class="cont sec">12</span>'], ['Perguntar'], ['Conferir', '<span class="cont cont-pilula">4</span>'], ['Quadros'], ['Caderno'], ['Pedidos e prazos', '<span class="cont b" style="color:var(--theme-warning)">1 vence</span>']].map(([n, x = '']) => `<a href="#"${n === 'Caderno' ? ' aria-current="page"' : ''}>${n} ${x}</a>`).join('')}</div>
<div style="margin-top:auto;display:flex;flex-direction:column;gap:12px"><div class="cota"><div style="display:flex;justify-content:space-between;gap:8px;font-size:14px"><span class="sec">Cota do mês</span><span class="b">R$ 18,40 de R$ 50</span></div><div class="medidor" role="img" aria-label="37% da cota usada"><div style="width:37%"></div></div></div>
<a href="#" class="perfil"><span class="avatar" aria-hidden="true">AL</span><span class="duas-linhas"><span class="b">Ana Lima</span><span class="p14 sec">Repórter · Redação Serena</span></span></a></div></nav>`;
const cabecalho = `<header style="height:64px;flex:none;padding:0 32px;display:flex;align-items:center;gap:16px;background:var(--theme-surface);border-bottom:1px solid var(--theme-line)"><div class="duas-linhas"><span class="p14 sec">Apuração</span><span class="b">Vila Serena — contrato de pavimentação (sintética)</span></div><span class="p14 sec" style="margin-left:auto;display:flex;align-items:center;gap:8px;white-space:nowrap"><span style="color:var(--theme-accent);display:flex">${svg(CHECK, 16, 2.5)}</span>Salvo às 14h32</span></header>`;
const notas = `<div style="display:flex;flex-direction:column;gap:4px">
<a href="#" aria-current="page" style="display:flex;flex-direction:column;gap:2px;padding:10px 12px;border-radius:8px;background:var(--theme-soft);color:var(--theme-text);text-decoration:none"><span class="b">Texto da reportagem</span><span class="p14 sec">versão 3 · 2 a resolver</span></a>
<a href="#" style="padding:10px 12px;border-radius:8px;color:var(--theme-text);text-decoration:none">Pauta Vila Serena</a><a href="#" style="padding:10px 12px;border-radius:8px;color:var(--theme-text);text-decoration:none">Perguntas para a prefeitura</a></div>`;
const seg = trechos => `<div class="seg" role="group" aria-label="Lista do caderno"><button type="button" aria-pressed="${!trechos}">Notas</button><button type="button" aria-pressed="${trechos}">Trechos (4)</button></div>`;
const TRECHOS = [
  [true, 'Trecho', '“Valor global: R$ 8.750.000,00.”', 'Contrato 041/2025, p. 1 · Ana Lima'],
  [true, 'Trecho', '“O primeiro termo aditivo acresce R$ 1.960.000,00 ao valor do contrato.”', 'Aditivo 1, p. 2 · Ana Lima'],
  [false, 'Achado do jornalista', 'Medições 1 a 3 somam R$ 3,9 milhões; conferi a soma no boletim.', 'Medição 3, p. 1 · Ana Lima'],
  [false, 'Anotação', 'Perguntar à secretaria se houve medição em setembro.', 'sem fonte · Bia Nunes'],
];
const listaTrechos = movel => `<div role="list" style="display:flex;flex-direction:column;gap:8px${movel ? '' : ';flex:1;min-height:0;overflow:hidden;mask-image:linear-gradient(#000 85%,transparent)'}">${TRECHOS.map(([sel, tipo, txt, fonte]) => `<label class="trecho"${sel ? ' style="border-color:var(--theme-accent)"' : ''}><input type="checkbox"${sel ? ' checked' : ''}><span style="display:flex;flex-direction:column;gap:4px;min-width:0"><span class="p14 b sec">${tipo}</span><span class="serifa" style="font-size:${movel ? 16 : 16}px">${txt}</span><span class="p14 sec">${fonte}</span></span></label>`).join('')}</div>
<span class="p14 sec">2 selecionados (até 20)</span>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px"><button type="button" class="bt bt-s" style="grid-column:1 / -1">Inserir no texto</button><button type="button" class="bt bt-s">Cruzar</button><button type="button" class="bt bt-s">Perguntar</button></div>
<button type="button" class="bt bt-p bt-cheio">Registrar trecho com fonte</button>
${movel ? '<span class="p14 sec">Material de autoria humana, separado dos resultados da IA.</span>' : ''}`;
const frases = rev => `<div class="serifa" style="font-size:18px;line-height:1.9;max-width:70ch;display:flex;flex-direction:column;gap:14px">
<p style="margin:0"><a href="#" class="af ${rev ? 'af-rev' : 'af-ok'}">A prefeitura contratou a Construtora Alfa por R$ 8,75 milhões.</a><span class="marca-af" style="color:var(--theme-accent)">✓ com fonte${rev ? ' · revisada por você' : ''}</span></p>
<p style="margin:0"><a href="#" class="af af-ok">Até agosto, R$ 3,9 milhões haviam sido pagos.</a><span class="marca-af" style="color:var(--theme-accent)">✓ com fonte</span></p>
<p style="margin:0"><a href="#" class="af af-ex">O aditivo fez o custo da obra disparar.</a><span class="marca-af" style="color:var(--theme-warning)">! exagero</span></p>
<p style="margin:0"><a href="#" class="af af-sf">Os sócios da construtora são próximos do secretário.</a><span class="marca-af sec">○ sem fonte</span></p></div>`;
const legenda = `<div class="cartao" style="padding:14px 18px;display:flex;flex-wrap:wrap;gap:8px 20px;font-size:14px">
<span><span class="af af-rev">texto</span> <span class="b" style="color:var(--theme-accent)">✓ revisada</span>: conferida por uma pessoa logada</span>
<span><span class="af af-ok">texto</span> <span class="b" style="color:var(--theme-accent)">✓ com fonte</span></span>
<span><span class="af af-ex">texto</span> <span class="b" style="color:var(--theme-warning)">! exagero</span></span>
<span><span class="af af-sf">texto</span> <span class="b sec">○ sem fonte</span></span></div>`;
const pilulas = escrever => `<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap"><button type="button" class="bt" aria-pressed="${!escrever}" style="border-radius:999px;padding:0 14px;${!escrever ? 'border:0;background:var(--theme-accent);color:var(--theme-on-primary);font-weight:600' : 'border:1px solid var(--theme-input-line);background:var(--theme-surface);color:var(--theme-text)'}">Conferir afirmações</button><button type="button" class="bt" aria-pressed="${escrever}" style="border-radius:999px;padding:0 14px;${escrever ? 'border:0;background:var(--theme-accent);color:var(--theme-on-primary);font-weight:600' : 'border:1px solid var(--theme-input-line);background:var(--theme-surface);color:var(--theme-text)'}">Escrever</button>
${escrever ? '<span class="p14 sec" style="margin-left:auto">As notas são salvas enquanto você escreve.</span>' : '<span class="p14 sec" style="margin-left:auto">5 afirmações: 3 com fonte · 1 revisada · 1 exagero · 1 sem fonte</span>'}</div>`;
const editor = `<div class="cartao" style="display:flex;flex-direction:column;flex:1;min-height:0">
<div class="ferr" role="toolbar" aria-label="Formatação"><button type="button" class="bt-s" style="border:1px solid var(--theme-input-line)!important;background:var(--theme-surface)">Texto normal ▾</button><button type="button" aria-label="Negrito"><strong>N</strong></button><button type="button" aria-label="Itálico"><em class="serifa">I</em></button><button type="button">• Lista</button><button type="button">☐ Tarefas</button><button type="button" class="b" style="color:var(--theme-accent)">+ Trecho com fonte</button><button type="button" style="margin-left:auto">Mais</button></div>
<div class="serifa" style="padding:20px 24px;font-size:18px;line-height:1.7;display:flex;flex-direction:column;gap:12px;max-width:70ch">
<h2 style="margin:0;font-size:22px;font-weight:600">Contrato de pavimentação em Vila Serena</h2>
<p style="margin:0">A prefeitura contratou a Construtora Alfa por R$ 8,75 milhões <a href="#" class="fonte-chip">Fonte 1</a>. Até agosto, R$ 3,9 milhões haviam sido pagos <a href="#" class="fonte-chip">Fonte 2</a>.</p>
<p style="margin:0">O primeiro aditivo acresce R$ 1,96 milhão ao valor original <a href="#" class="fonte-chip">Fonte 3</a><span style="border-left:2px solid var(--theme-text);margin-left:2px"></span></p></div></div>`;
const fontesNota = `<span class="rubrica" style="color:var(--theme-accent)">Fontes da nota</span>
${[['1', '“Valor global: R$ 8.750.000,00.”', 'Contrato 041/2025, p. 1'], ['2', '“Acumulado pago: R$ 3.900.000,00.”', 'Medição 3, p. 1 · lida por OCR'], ['3', '“…acresce R$ 1.960.000,00 ao valor do contrato.”', 'Aditivo 1, p. 2']].map(([n, c, f]) => `<a href="#" style="display:flex;gap:10px;padding:12px 0;border-top:1px solid var(--theme-line);color:var(--theme-text);text-decoration:none"><span class="fonte-chip" style="align-self:flex-start">${n}</span><span style="display:flex;flex-direction:column;gap:2px"><span class="serifa">${c}</span><span class="p14 sec">${f} · abrir o original</span></span></a>`).join('')}
<button type="button" class="bt bt-s bt-cheio" style="margin-top:auto">Inserir trecho com fonte</button>`;

const tela1440 = (esquerda, centro, direita) => `<div class="pr" style="width:1440px;height:900px;display:flex">${lateral}<div style="flex:1;min-width:0;display:flex;flex-direction:column">${cabecalho}<main style="flex:1;min-height:0;display:flex">
<section aria-label="Notas e trechos" style="width:272px;flex:none;padding:28px 16px 28px 32px;display:flex;flex-direction:column;gap:12px;overflow:hidden">${esquerda}</section>
<section aria-label="Texto da nota" style="flex:1;min-width:0;padding:28px 32px;display:flex;flex-direction:column;gap:20px;border-left:1px solid var(--theme-line)">
<div style="display:flex;align-items:center;gap:12px"><h1 class="serifa" style="margin:0;font-size:28px;font-weight:600;line-height:1.2">Texto da reportagem</h1><button type="button" class="bt bt-s" style="margin-left:auto">Nova versão</button><button type="button" class="bt bt-s">Exportar</button></div>${centro}</section>
<aside style="width:340px;flex:none;background:var(--theme-surface);border-left:1px solid var(--theme-line);padding:28px;display:flex;flex-direction:column;gap:16px">${direita}</aside></main></div></div>`;
const painelRevisada = `<span class="rubrica" style="color:var(--theme-accent)">Afirmação selecionada</span><p class="serifa" style="margin:0;font-size:18px">“A prefeitura contratou a Construtora Alfa por R$ 8,75 milhões.”</p>
<div class="cartao" style="padding:12px 16px;display:flex;flex-direction:column;gap:4px;background:var(--theme-soft);border-color:var(--theme-accent-line)"><span class="b" style="color:var(--theme-accent)">✓ Com fonte · revisada por você</span><span class="p14">Ana Lima marcou como revisada hoje, às 14h40. Só pessoa logada marca "revisada" (W04).</span></div>
<span class="p14 b sec">Evidência ligada</span><a href="#" style="display:flex;flex-direction:column;gap:2px;padding:12px 0;border-top:1px solid var(--theme-line);border-bottom:1px solid var(--theme-line);color:var(--theme-text);text-decoration:none"><span class="serifa">“Valor global: R$ 8.750.000,00.”</span><span class="p14 sec">Contrato 041/2025, p. 1 · abrir o original</span></a>`;

const trechos1440 = () => tela1440(`${seg(true)}${listaTrechos(false)}`, `${pilulas(false)}${frases(true)}${legenda}`, painelRevisada);
const escrever1440 = () => tela1440(`<button type="button" class="bt bt-s bt-cheio">Nova nota</button>${seg(false)}${notas}`, `${pilulas(true)}${editor}`, fontesNota);

const topo = `<header class="topo"><button type="button" class="bt-ic" aria-label="Abrir menu">${svg(MENU, 22)}</button><div class="duas-linhas"><span class="p14 sec">Apuração</span><span class="nome">Vila Serena</span></div><span class="p14 sec" style="margin-left:auto;padding-right:4px;white-space:nowrap">R$ 18,40 de 50</span></header>`;
const trechos390 = () => `<div class="pr" style="width:390px;min-height:844px;display:flex;flex-direction:column">${topo}<main style="padding:16px;display:flex;flex-direction:column;gap:12px">${seg(true)}${listaTrechos(true)}
<div style="border-top:1px solid var(--theme-line);padding-top:12px;display:flex;flex-direction:column;gap:8px"><span class="p14 b sec">Sinais no texto</span>${legenda}</div></main></div>`;
const escrever390 = () => `<div class="pr" style="width:390px;min-height:844px;display:flex;flex-direction:column">${topo}<main style="padding:16px;display:flex;flex-direction:column;gap:12px">
<button type="button" class="bt bt-s bt-cheio" style="justify-content:space-between;height:48px"><span>Nota: <strong>Texto da reportagem</strong></span><span aria-hidden="true">▾</span></button>
<div style="display:flex;gap:8px"><button type="button" class="bt bt-s" aria-pressed="false" style="flex:1;border-radius:999px">Conferir</button><button type="button" class="bt" aria-pressed="true" style="flex:1;border-radius:999px;border:0;background:var(--theme-accent);color:var(--theme-on-primary);font-weight:600">Escrever</button></div>
${editor.replace('padding:20px 24px', 'padding:16px')}
<span class="p14 sec">Toque numa fonte, como "Fonte 1", para ver o trecho e abrir o original.</span></main></div>`;

(async () => {
  const browser = await chromium.launch({headless: true, executablePath: chromium.executablePath()});
  for (const [tema, nome] of [['light', 'claro'], ['dark', 'escuro']]) {
    for (const [sub, w, f] of [['trechos', 1440, trechos1440], ['trechos', 390, trechos390], ['escrever', 1440, escrever1440], ['escrever', 390, escrever390]]) {
      const arq = `proposta-${sub}-${nome}-${w}`;
      const html = path.join(fonteDir, `caderno-${arq}.html`);
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
