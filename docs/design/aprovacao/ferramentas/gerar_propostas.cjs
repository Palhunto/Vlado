// Proposta derivada do caderno (W04), aprovada pelo dono em 21/11/2026 (docs/design/aprovacao/caderno),
// na linguagem do canvas, com os tokens de docs/design/novas/fonte/base.css. Gera o HTML em fonte/ e o PNG em cada pasta.
// Uso: NODE_PATH=.ferramentas/node/node_modules node docs/design/aprovacao/ferramentas/gerar_propostas.cjs
const {chromium} = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const url = require('node:url');

const aprovacao = path.resolve(__dirname, '..');
const design = path.resolve(aprovacao, '..');
const fonteDir = path.join(__dirname, 'fonte');
fs.mkdirSync(fonteDir, {recursive: true});
const rel = alvo => path.relative(fonteDir, alvo).split(path.sep).join('/');
const FD = rel(path.resolve(design, '..', '..', 'interface', 'fonts'));
const BASE = rel(path.join(design, 'novas', 'fonte', 'base.css'));
const icones = Object.fromEntries(JSON.parse(fs.readFileSync(path.join(design, 'icones', 'ferramentas', 'icones.json'), 'utf8')).icones.map(i => [i.nome, i.d]));
const svg = (d, tam, traco = 2) => `<svg aria-hidden="true" width="${tam}" height="${tam}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="${traco}" stroke-linecap="round" stroke-linejoin="round" style="flex:none"><path d="${d}"/></svg>`;
const CHECK = 'M5 12l5 5L20 7';
const FAIXA = '<div class="faixa-derivado" style="background:#1e4d3e">Derivado · aprovado pelo dono em 21/11/2026</div>';
const pagina = (tema, corpo) => `<!doctype html><html lang="pt-BR" data-theme="${tema}"><head><meta charset="utf-8"><style>@font-face{font-family:"Source Serif 4";src:url('${FD}/SourceSerif4-Roman.ttf') format('truetype');font-weight:200 900}
@font-face{font-family:"Source Sans 3";src:url('${FD}/SourceSans3-Upright.otf') format('opentype');font-weight:200 900}
.af{text-decoration:none;color:inherit;padding:1px 0;text-underline-offset:6px;text-decoration-thickness:2px;text-decoration-line:underline}
.af-ok{text-decoration-color:var(--theme-accent)}.af-ex{text-decoration-style:dashed;text-decoration-color:var(--theme-warning)}.af-sf{text-decoration-style:dotted;text-decoration-color:var(--theme-input-line)}
.af-sel{outline:2px solid var(--theme-accent);outline-offset:3px;border-radius:4px;background:var(--theme-warning-bg)}
.marca-af{font:600 14px/1 var(--sans);white-space:nowrap;margin-left:6px;display:inline-flex;align-items:center;gap:4px;vertical-align:2px}
.col{background:var(--theme-reading);border-radius:12px;padding:14px 16px;display:flex;flex-direction:column;gap:10px}
.ev{background:var(--theme-surface);border:1px solid var(--theme-line);border-radius:8px;padding:10px 12px;display:flex;flex-direction:column;gap:2px;color:var(--theme-text);text-decoration:none}
</style><link rel="stylesheet" href="${BASE}"></head><body><div id="prancha" style="display:inline-block;vertical-align:top">${corpo}${FAIXA}</div></body></html>`;

// Barra lateral do canvas, com a área ativa variável.
const lateral = ativa => `<nav class="lateral" aria-label="Áreas" style="flex:none">
<div class="marca" style="padding:0 8px">Vlado<span>.</span></div>
<div class="areas">${[['Visão geral'], ['Documentos', '<span class="cont sec">12</span>'], ['Perguntar'], ['Conferir', '<span class="cont cont-pilula">4</span>'], ['Quadros'], ['Caderno'], ['Pedidos e prazos', '<span class="cont b" style="color:var(--theme-warning)">1 vence</span>']]
  .map(([n, x = '']) => `<a href="#"${n === ativa ? ' aria-current="page"' : ''}>${n} ${x}</a>`).join('')}</div>
<div style="margin-top:auto;display:flex;flex-direction:column;gap:12px">
<div class="cota"><div style="display:flex;justify-content:space-between;gap:8px;font-size:14px"><span class="sec">Cota do mês</span><span class="b">R$ 18,40 de R$ 50</span></div><div class="medidor" role="img" aria-label="37% da cota usada"><div style="width:37%"></div></div></div>
<a href="#" class="perfil"><span class="avatar" aria-hidden="true">AL</span><span class="duas-linhas"><span class="b">Ana Lima</span><span class="p14 sec">Repórter · Redação Serena</span></span></a></div></nav>`;

// ---------- Caderno (W04: notas à esquerda, texto com afirmações no centro, afirmação selecionada à direita) ----------
const caderno = () => `<div class="pr" style="width:1440px;height:900px;display:flex">${lateral('Caderno')}
<div style="flex:1;min-width:0;display:flex;flex-direction:column">
<header style="height:64px;flex:none;padding:0 32px;display:flex;align-items:center;gap:16px;background:var(--theme-surface);border-bottom:1px solid var(--theme-line)"><div class="duas-linhas"><span class="p14 sec">Apuração</span><span class="b">Vila Serena — contrato de pavimentação (sintética)</span></div><span class="p14 sec" style="margin-left:auto;display:flex;align-items:center;gap:8px;white-space:nowrap"><span style="color:var(--theme-accent);display:flex">${svg(CHECK, 16, 2.5)}</span>Salvo às 14h32</span></header>
<main style="flex:1;min-height:0;display:flex">
<section aria-label="Notas" style="width:224px;flex:none;padding:28px 16px 28px 32px;display:flex;flex-direction:column;gap:12px">
<button type="button" class="bt bt-s bt-cheio">Nova nota</button>
<div style="display:flex;flex-direction:column;gap:4px">
<a href="#" aria-current="page" style="display:flex;flex-direction:column;gap:2px;padding:10px 12px;border-radius:8px;background:var(--theme-soft);color:var(--theme-text);text-decoration:none"><span class="b">Texto da reportagem</span><span class="p14 sec">versão 3 · 2 a resolver</span></a>
<a href="#" style="padding:10px 12px;border-radius:8px;color:var(--theme-text);text-decoration:none">Pauta Vila Serena</a>
<a href="#" style="padding:10px 12px;border-radius:8px;color:var(--theme-text);text-decoration:none">Perguntas para a prefeitura</a></div></section>
<section aria-label="Texto da nota" style="flex:1;min-width:0;padding:28px 32px;display:flex;flex-direction:column;gap:20px;border-left:1px solid var(--theme-line)">
<div style="display:flex;align-items:center;gap:12px"><h1 class="serifa" style="margin:0;font-size:28px;font-weight:600;line-height:1.2">Texto da reportagem</h1>
<button type="button" class="bt bt-s" style="margin-left:auto">Nova versão</button><button type="button" class="bt bt-s">Exportar</button></div>
<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap"><button type="button" class="bt" aria-pressed="true" style="border-radius:999px;padding:0 14px;border:0;background:var(--theme-accent);color:var(--theme-on-primary);font-weight:600">Conferir afirmações</button><button type="button" class="bt bt-s" aria-pressed="false" style="border-radius:999px;padding:0 14px">Escrever</button>
<span class="p14 sec" style="margin-left:auto">5 afirmações: 3 com fonte · 1 exagero · 1 sem fonte</span></div>
<div class="serifa" style="font-size:18px;line-height:1.9;max-width:70ch;display:flex;flex-direction:column;gap:14px">
<p style="margin:0"><a href="#" class="af af-ok">A prefeitura contratou a Construtora Alfa por R$ 8,75 milhões.</a><span class="marca-af" style="color:var(--theme-accent)">✓ com fonte</span></p>
<p style="margin:0"><a href="#" class="af af-ok">Até agosto, R$ 3,9 milhões haviam sido pagos.</a><span class="marca-af" style="color:var(--theme-accent)">✓ com fonte</span></p>
<p style="margin:0"><a href="#" class="af af-ex af-sel">O aditivo fez o custo da obra disparar.</a><span class="marca-af" style="color:var(--theme-warning)">! exagero</span></p>
<p style="margin:0"><a href="#" class="af af-sf">Os sócios da construtora são próximos do secretário.</a><span class="marca-af sec">○ sem fonte</span></p></div></section>
<aside aria-label="Afirmação selecionada" style="width:360px;flex:none;background:var(--theme-surface);border-left:1px solid var(--theme-line);padding:28px;display:flex;flex-direction:column;gap:18px">
<span class="rubrica" style="color:var(--theme-accent)">Afirmação selecionada</span>
<p class="serifa" style="margin:0;font-size:18px">“O aditivo fez o custo da obra disparar.”</p>
<div class="aviso" style="display:flex;flex-direction:column;gap:6px;font-size:16px"><span class="b" style="color:var(--theme-warning)">! Mais forte que a fonte</span><span class="p14">A fonte diz "acresce 22,4%". "Disparar" é avaliação sua.</span></div>
<div style="display:flex;flex-direction:column;gap:6px"><span class="p14 b sec">Evidência ligada</span>
<a href="#" style="display:flex;flex-direction:column;gap:2px;padding:12px 0;border-top:1px solid var(--theme-line);border-bottom:1px solid var(--theme-line);color:var(--theme-text);text-decoration:none"><span class="serifa">“O primeiro termo aditivo acresce R$ 1.960.000,00 ao valor do contrato.”</span><span class="p14 sec">Aditivo 1, p. 2 · abrir o original</span></a></div>
<div style="margin-top:auto;display:flex;flex-direction:column;gap:10px"><button type="button" class="bt bt-s bt-cheio">Ligar outra evidência</button><button type="button" class="bt bt-s bt-cheio">Reescrever a frase</button><button type="button" class="bt bt-p bt-cheio">Marcar como revisada por mim</button></div></aside>
</main></div></div>`;


// Cabeçalho do celular do canvas (Celular.dc.html) e o caderno em 390 px: a afirmação selecionada sobe num painel no pé.
const MENU = 'M4 7h16M4 12h16M4 17h16';
const topoCelular = `<header class="topo"><button type="button" class="bt-ic" aria-label="Abrir menu">${svg(MENU, 22)}</button><div class="duas-linhas"><span class="p14 sec">Apuração</span><span class="nome">Vila Serena</span></div><span class="p14 sec" style="margin-left:auto;padding-right:4px;white-space:nowrap">R$ 18,40 de 50</span></header>`;
const caderno390 = () => `<div class="pr" style="width:390px;height:844px;overflow:hidden;position:relative;display:flex;flex-direction:column">${topoCelular}
<main style="padding:16px 16px 0;display:flex;flex-direction:column;gap:14px">
<button type="button" class="bt bt-s bt-cheio" style="justify-content:space-between;height:48px"><span>Nota: <strong>Texto da reportagem</strong></span><span aria-hidden="true">▾</span></button>
<div style="display:flex;flex-direction:column;gap:2px"><h1 class="serifa" style="margin:0;font-size:28px;font-weight:600;line-height:1.2">Texto da reportagem</h1><span class="p14 sec" style="display:flex;align-items:center;gap:6px">versão 3 · 2 a resolver · <span style="color:var(--theme-accent);display:flex">${svg(CHECK, 14, 2.5)}</span>salvo às 14h32</span></div>
<div style="display:flex;gap:8px"><button type="button" class="bt" aria-pressed="true" style="flex:1;border-radius:999px;border:0;background:var(--theme-accent);color:var(--theme-on-primary);font-weight:600">Conferir afirmações</button><button type="button" class="bt bt-s" aria-pressed="false" style="border-radius:999px;padding:0 14px">Escrever</button></div>
<span class="p14 sec">5 afirmações: 3 com fonte · 1 exagero · 1 sem fonte</span>
<div class="serifa" style="font-size:18px;line-height:1.9;display:flex;flex-direction:column;gap:10px">
<p style="margin:0"><a href="#" class="af af-ok">A prefeitura contratou a Construtora Alfa por R$ 8,75 milhões.</a><span class="marca-af" style="color:var(--theme-accent)">✓ com fonte</span></p>
<p style="margin:0"><a href="#" class="af af-ok">Até agosto, R$ 3,9 milhões haviam sido pagos.</a><span class="marca-af" style="color:var(--theme-accent)">✓ com fonte</span></p>
<p style="margin:0"><a href="#" class="af af-ex af-sel">O aditivo fez o custo da obra disparar.</a><span class="marca-af" style="color:var(--theme-warning)">! exagero</span></p></div></main>
<section aria-label="Afirmação selecionada" style="position:absolute;left:0;right:0;bottom:0;background:var(--theme-surface);border-top:1px solid var(--theme-line);border-radius:12px 12px 0 0;box-shadow:var(--sombra-dialogo);padding:16px 16px 20px;display:flex;flex-direction:column;gap:12px">
<div style="display:flex;align-items:center"><span class="rubrica" style="color:var(--theme-accent)">Afirmação selecionada</span><button type="button" class="bt-ic" aria-label="Fechar" style="margin-left:auto">${svg(icones['sinal-sem-suporte'], 20, 2)}</button></div>
<div class="aviso" style="display:flex;flex-direction:column;gap:4px;font-size:16px"><span class="b" style="color:var(--theme-warning)">! Mais forte que a fonte</span><span class="p14">A fonte diz "acresce 22,4%". "Disparar" é avaliação sua.</span></div>
<a href="#" class="p14" style="color:var(--theme-text)"><span class="b">Evidência ligada:</span> Aditivo 1, p. 2 · abrir o original</a>
<button type="button" class="bt bt-p bt-g bt-cheio">Marcar como revisada por mim</button>
<div style="display:flex;gap:8px"><button type="button" class="bt bt-s bt-g" style="flex:1">Ligar evidência</button><button type="button" class="bt bt-s bt-g" style="flex:1">Reescrever</button></div></section></div>`;

const lista = [];
for (const [tema, nome] of [['light', 'claro'], ['dark', 'escuro']]) {
  lista.push({pasta: 'caderno', arquivo: `proposta-${nome}-1440`, tema, corpo: caderno()});
  lista.push({pasta: 'caderno', arquivo: `proposta-${nome}-390`, tema, corpo: caderno390()});
}

(async () => {
  const browser = await chromium.launch({headless: true, executablePath: chromium.executablePath()});
  for (const {pasta, arquivo, tema, corpo} of lista) {
    const html = path.join(fonteDir, `${pasta}-${arquivo}.html`);
    fs.writeFileSync(html, pagina(tema, corpo));
    const page = await browser.newPage({viewport: {width: +arquivo.match(/(\d+)$/)[1], height: 900}, deviceScaleFactor: 1});
    await page.route('**/*', r => r.request().url().startsWith('file:') ? r.continue() : r.abort());
    await page.goto(url.pathToFileURL(html).href);
    await page.evaluate(() => document.fonts.ready);
    await page.locator('#prancha').screenshot({path: path.join(aprovacao, pasta, `${arquivo}.png`)});
    console.log(pasta, arquivo);
    await page.close();
  }
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
