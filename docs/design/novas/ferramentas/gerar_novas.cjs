// Gera as pranchas derivadas da fase 3 (docs/design/novas): HTML com os tokens em fonte/ e PNG em telas/.
// Diálogo próprio (UX-16), escuro das telas de desktop do canvas, tablet de 1024 px e celular de 390 px.
// Uso: NODE_PATH=.ferramentas/node/node_modules node docs/design/novas/ferramentas/gerar_novas.cjs
const {chromium} = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const url = require('node:url');

const novas = path.resolve(__dirname, '..');
const design = path.resolve(novas, '..');
const raizProjeto = path.resolve(design, '..', '..');
const canvas = path.join(design, 'referencia', 'canvas');
const fontes = path.join(raizProjeto, 'interface', 'fonts');
const fonteDir = path.join(novas, 'fonte');
const telasDir = path.join(novas, 'telas');
fs.mkdirSync(telasDir, {recursive: true});

const icones = Object.fromEntries(JSON.parse(fs.readFileSync(path.join(design, 'icones', 'ferramentas', 'icones.json'), 'utf8')).icones.map(i => [i.nome, i.d]));
const FD = path.relative(fonteDir, fontes).split(path.sep).join('/');  // relativo: as pranchas não guardam caminho da máquina
const fontFace = `@font-face{font-family:"Source Serif 4";src:url('${FD}/SourceSerif4-Roman.ttf') format('truetype');font-weight:200 900}
@font-face{font-family:"Source Sans 3";src:url('${FD}/SourceSans3-Upright.otf') format('opentype');font-weight:200 900}`;
const FAIXA = '<div class="faixa-derivado">Derivado · aguarda aprovação do dono</div>';
const moldura = conteudo => `<div id="prancha" style="display:inline-block;vertical-align:top">${conteudo}${FAIXA}</div>`;
const svg = (d, tam, traco = 2) => `<svg aria-hidden="true" width="${tam}" height="${tam}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="${traco}" stroke-linecap="round" stroke-linejoin="round"><path d="${d}"/></svg>`;
const MENU = 'M4 7h16M4 12h16M4 17h16';            // canvas, Celular.dc.html
const CHECK = 'M5 12l5 5L20 7';                    // canvas, Main.dc.html
const pagina = (tema, corpo) => `<!doctype html><html lang="pt-BR" data-theme="${tema}"><head><meta charset="utf-8"><style>${fontFace}</style><link rel="stylesheet" href="base.css"></head><body>${corpo}</body></html>`;

// ---------- fragmentos (estrutura e textos do canvas) ----------
const lateral = () => `<nav class="lateral" aria-label="Áreas">
<div class="marca" style="padding:0 8px">Vlado<span>.</span></div>
<div class="areas">
<a href="#">Visão geral</a><a href="#">Documentos <span class="cont sec">12</span></a><a href="#">Perguntar</a>
<a href="#" aria-current="page">Conferir <span class="cont cont-pilula">4</span></a><a href="#">Quadros</a><a href="#">Caderno</a>
<a href="#">Pedidos e prazos <span class="cont b" style="color:var(--theme-warning)">1 vence</span></a></div>
<div style="margin-top:auto;display:flex;flex-direction:column;gap:12px">
<div class="cota"><div style="display:flex;justify-content:space-between;gap:8px;font-size:14px"><span class="sec">Cota do mês</span><span class="b">R$ 18,40 de R$ 50</span></div><div class="medidor" role="img" aria-label="37% da cota usada"><div style="width:37%"></div></div></div>
<a href="#" class="perfil"><span class="avatar" aria-hidden="true">AL</span><span class="duas-linhas"><span class="b">Ana Lima</span><span class="p14 sec">Repórter · Redação Serena</span></span></a></div></nav>`;

const achados = movel => `<div style="display:flex;flex-direction:column;gap:12px">
<button type="button" class="achado"><span class="sinal ok" aria-hidden="true">${svg(CHECK, 16, 2.5)}</span><span style="display:flex;flex-direction:column;gap:6px"><span>O valor global do contrato 041/2025 é de R$ 8.750.000,00.</span><span class="p14 b" style="color:var(--theme-accent)">Conferido no original · Contrato 041/2025, p. 1</span></span></button>
<div class="achado aberto"><div style="display:flex;gap:14px;align-items:flex-start"><span class="sinal vazio" aria-hidden="true"></span><div style="display:flex;flex-direction:column;gap:6px"><span>Até a medição nº 3, o acumulado pago soma <strong>R$ 3.900.000,00</strong>, o que corresponde a 44,6% do valor global.</span><span class="p14 sec">Medição nº 3, p. 1 · página digitalizada, lida por OCR · cálculo: 3.900.000 ÷ 8.750.000</span></div></div>
${movel
    ? `<div style="display:flex;flex-direction:column;gap:8px"><a href="#" class="bt bt-s bt-g bt-cheio">Ver o trecho no original</a><button type="button" class="bt bt-p bt-g bt-cheio">Confere com o original</button><button type="button" class="bt bt-s bt-g bt-cheio">Precisa de ajuste</button><button type="button" class="bt bt-r bt-g bt-cheio">Sem suporte</button></div>`
    : `<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding-left:42px"><button type="button" class="bt bt-p">Confere com o original</button><button type="button" class="bt bt-s">Precisa de ajuste</button><button type="button" class="bt bt-r">Sem suporte</button></div>`}
</div>
<button type="button" class="achado"><span class="sinal vazio" aria-hidden="true"></span><span style="display:flex;flex-direction:column;gap:6px"><span>O primeiro aditivo acresce R$ 1.960.000,00, ou 22,4% do valor original.</span><span class="p14 sec">Termo aditivo nº 1, p. 2 · a conferir</span></span></button>
<button type="button" class="achado lacuna"><span class="sinal lac" aria-hidden="true">?</span><span style="display:flex;flex-direction:column;gap:6px"><span>Os sócios da construtora não foram localizados nos documentos.</span><span class="p14 b" style="color:var(--theme-warning)">Lacuna · a busca não encontrou; isso não prova ausência</span></span></button></div>`;

const cabecalhoConferir = movel => `<div style="display:flex;align-items:baseline;gap:12px;flex-wrap:wrap"><h1 class="serifa" style="margin:0;font-size:28px;font-weight:600;line-height:1.2">Conferir achados</h1><span class="p14 sec">2 de 6 conferidos</span></div>
<div class="caixa-pergunta"><span class="p14 sec">Sua pergunta</span><span class="serifa" style="font-size:18px">Quanto do contrato já foi pago e o aditivo respeita o limite legal?</span></div>`;

const folha = pad => `<div class="folha" style="padding:${pad}"><div style="text-align:center;font-weight:600;letter-spacing:.5px">PREFEITURA DE VILA SERENA<br>BOLETIM DE MEDIÇÃO Nº 3</div>
<div>Contrato nº 041/2025 — Pavimentação de vias urbanas.<br>Período de referência: 1º a 31 de agosto de 2025.</div>
<table><tr><td>Medição nº 1</td><td>R$ 1.200.000,00</td></tr><tr><td>Medição nº 2</td><td>R$ 1.450.000,00</td></tr><tr><td>Medição nº 3</td><td>R$ 1.250.000,00</td></tr><tr class="realce"><td>Acumulado pago</td><td>R$ 3.900.000,00</td></tr></table>
<div style="font-size:14px;color:#5f6a63">Documento fictício para demonstração.</div></div>`;

const topoOriginal = `<div style="display:flex;align-items:center;gap:12px"><div class="duas-linhas"><span class="b">Medição nº 3</span><span class="p14 sec">Página 1 de 1 · original preservado</span></div><span class="selo selo-ocr" style="margin-left:auto">Lida por OCR</span></div>`;
const zoom = `<div style="display:flex;align-items:center;gap:8px"><button type="button" class="bt bt-s" aria-label="Diminuir zoom" style="width:44px;padding:0;font-size:20px">−</button><button type="button" class="bt bt-s" aria-label="Aumentar zoom" style="width:44px;padding:0;font-size:20px">+</button><a href="#" class="b" style="margin-left:auto">Abrir o original em nova aba</a></div>`;

const botaoMenu = `<button type="button" class="bt-ic" aria-label="Abrir menu">${svg(MENU, 22)}</button>`;

// ---------- páginas ----------
const P = {};
P['conferir-achado-1024'] = (gaveta = false) => `<div class="pr" style="position:relative;width:1024px;min-height:768px;display:flex;flex-direction:column">
<header class="topo topo-tablet">${botaoMenu}<div class="duas-linhas"><span class="p14 sec">Apuração</span><span class="nome">Vila Serena — contrato de pavimentação (sintética)</span></div>
<span class="p14 sec" style="margin-left:auto;display:flex;align-items:center;gap:8px;white-space:nowrap"><span style="color:var(--theme-accent);display:flex">${svg(CHECK, 16, 2.5)}</span>Salvo às 14h32</span><button type="button" class="bt bt-s">Exportar apuração</button></header>
<main style="flex:1;display:flex"${gaveta ? ' inert' : ''}>
<section aria-label="Resposta da IA" style="flex:1;min-width:0;padding:28px 32px;display:flex;flex-direction:column;gap:20px">${cabecalhoConferir(false)}${achados(false)}</section>
<aside aria-label="Original citado" style="width:440px;flex:none;background:var(--theme-sidebar);border-left:1px solid var(--theme-line);padding:20px 24px;display:flex;flex-direction:column;gap:14px">${topoOriginal}${folha('32px 36px')}${zoom}</aside></main>
${gaveta ? `<div style="position:absolute;inset:0;background:var(--theme-backdrop)"></div><div role="dialog" aria-modal="true" aria-label="Áreas" style="position:absolute;top:0;bottom:0;left:0;display:flex;box-shadow:var(--sombra-dialogo)">${lateral()}</div>` : ''}</div>`;

P['visao-geral-1024'] = () => `<div class="pr" style="position:relative;width:1024px;min-height:768px;display:flex;flex-direction:column">
<header class="topo topo-tablet">${botaoMenu}<div class="marca" style="font-size:28px;line-height:1">Vlado<span>.</span></div><span class="p14 sec" style="margin-left:auto">Cota do mês <span class="b" style="color:var(--theme-text)">R$ 18,40 de R$ 50</span></span></header>
<main style="padding:32px;display:flex;flex-direction:column;gap:24px">${visaoGeralCorpo(false)}</main></div>`;

function visaoGeralCorpo(movel) {
  const tit = movel ? 28 : 36;
  const contagens = `<div style="display:grid;grid-template-columns:repeat(${movel ? 2 : 4},minmax(0,1fr));gap:${movel ? 12 : 16}px">
<div class="cartao" style="padding:20px 22px;display:flex;flex-direction:column;gap:4px"><span class="p14 sec">Documentos</span><span class="serifa" style="font-size:32px;font-weight:600;line-height:1.1">12</span><span class="p14 sec">3 páginas lidas por OCR</span></div>
<div class="cartao" style="padding:20px 22px;display:flex;flex-direction:column;gap:4px"><span class="p14 sec">Achados conferidos</span><span class="serifa" style="font-size:32px;font-weight:600;line-height:1.1">2 <span class="sec" style="font-size:18px;font-weight:400">de 6</span></span><div class="medidor" role="img" aria-label="2 de 6" style="margin-top:6px"><div style="width:33%"></div></div></div>
<div class="cartao" style="padding:20px 22px;display:flex;flex-direction:column;gap:4px"><span class="p14 sec">Hipóteses</span><span class="serifa" style="font-size:32px;font-weight:600;line-height:1.1">3</span><span class="p14 b" style="color:var(--theme-warning)">1 sem evidência ainda</span></div>
<div class="cartao" style="padding:20px 22px;display:flex;flex-direction:column;gap:4px;background:var(--theme-warning-bg);border-color:var(--theme-warning-line)"><span class="p14 b" style="color:var(--theme-warning)">Pedido de LAI</span><span class="serifa" style="font-size:32px;font-weight:600;line-height:1.1">5 dias</span><span class="p14">para a resposta da prefeitura</span></div></div>`;
  const perguntas = `<section class="cartao" style="padding:22px 24px;display:flex;flex-direction:column;gap:14px"><div style="display:flex;align-items:baseline"><h2 class="serifa" style="margin:0;font-size:22px;font-weight:600">Últimas perguntas</h2><a href="#" class="b" style="margin-left:auto">Ver todas</a></div>
${[['Quanto do contrato já foi pago e o aditivo respeita o limite legal?', 'Hoje, 14h10 · 6 achados · R$ 1,32'], ['Quem assina as medições e em que datas?', 'Ontem · 4 achados, todos conferidos · R$ 0,97'], ['O edital previa o trecho da Rua das Acácias?', '18 de novembro · 2 achados · R$ 1,05']].map(([q, m]) => `<a href="#" style="display:flex;flex-direction:column;gap:2px;padding:12px 0;border-top:1px solid var(--theme-line);color:var(--theme-text);text-decoration:none"><span>${q}</span><span class="p14 sec">${m}</span></a>`).join('')}</section>`;
  const marco = (cheio, data, txt, ultimo) => `<div style="position:relative;padding:6px 0 ${ultimo ? 0 : 14}px"><span aria-hidden="true" style="position:absolute;left:${cheio ? -27 : -28}px;top:${cheio ? 12 : 11}px;width:${cheio ? 12 : 10}px;height:${cheio ? 12 : 10}px;border-radius:999px;${cheio ? 'background:var(--theme-accent)' : 'background:var(--theme-surface);border:2px solid var(--theme-accent)'}"></span><span class="p14 sec">${data}</span><br>${txt}</div>`;
  const tempo = `<section class="cartao" style="padding:22px 24px;display:flex;flex-direction:column;gap:14px"><h2 class="serifa" style="margin:0;font-size:22px;font-weight:600">Linha do tempo documentada</h2><div style="border-left:2px solid var(--theme-accent-line);margin-left:6px;padding-left:20px">${marco(true, '3 de março de 2025', 'Assinatura do contrato 041/2025')}${marco(true, '31 de agosto de 2025', 'Medição nº 3: acumulado de R$ 3,9 milhões')}${marco(false, 'Outubro de 2025 · dia não informado', 'Termo aditivo nº 1', true)}</div></section>`;
  return `<div style="display:flex;${movel ? 'flex-direction:column;gap:12px' : 'align-items:flex-end;gap:16px'}"><div style="display:flex;flex-direction:column;gap:4px"><span class="p14 sec">Apuração · criada em 12 de novembro</span><h1 class="serifa" style="margin:0;font-size:${tit}px;font-weight:600;line-height:${movel ? 1.2 : 1.15};letter-spacing:-.4px">Vila Serena — contrato de pavimentação</h1></div>
<div style="display:flex;gap:8px;${movel ? '' : 'margin-left:auto'}"><button type="button" class="bt bt-s"${movel ? ' style="flex:1"' : ''}>Trocar de apuração</button><button type="button" class="bt bt-p"${movel ? ' style="flex:1"' : ''}>Nova apuração</button></div></div>
<div class="cartao" style="padding:${movel ? '20px' : '28px 32px'};display:flex;${movel ? 'flex-direction:column;align-items:stretch;gap:16px' : 'align-items:center;gap:32px'};box-shadow:var(--sombra-cartao)"><div style="flex:1;display:flex;flex-direction:column;gap:8px"><span class="rubrica" style="color:var(--theme-accent)">Seu próximo passo</span><span class="serifa" style="font-size:24px;line-height:1.3">Quatro achados esperam conferência no original.</span><span class="sec">Um deles vem de página digitalizada: confira o número com atenção.</span></div><a href="#" class="bt bt-p" style="height:${movel ? 48 : 52}px;padding:0 24px;font-size:18px">Conferir agora</a></div>
${contagens}
<div style="display:grid;grid-template-columns:${movel ? '1fr' : 'repeat(2,minmax(0,1fr))'};gap:${movel ? 12 : 16}px">${perguntas}${tempo}</div>`;
}

const topoCelular = `<header class="topo">${botaoMenu}<div class="duas-linhas"><span class="p14 sec">Apuração</span><span class="nome">Vila Serena</span></div><span class="p14 sec" style="margin-left:auto;padding-right:4px;white-space:nowrap">R$ 18,40 de 50</span></header>`;
P['conferir-achado-390'] = (extra = '') => `<div class="pr" style="position:relative;width:390px;${extra ? 'height:844px;overflow:hidden' : 'min-height:844px'};display:flex;flex-direction:column">${topoCelular}
<main style="padding:20px 16px;display:flex;flex-direction:column;gap:16px">${cabecalhoConferir(true)}${achados(true)}</main>${extra}</div>`;
P['conferir-achado-390-original'] = () => `<div class="pr" style="position:relative;width:390px;min-height:844px;display:flex;flex-direction:column;background:var(--theme-sidebar)">
<header class="topo"><a href="#" class="bt bt-s" style="gap:6px;padding:0 12px"><svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 6l-6 6 6 6"/></svg>Achados</a><span class="selo selo-ocr" style="margin-left:auto">Lida por OCR</span></header>
<main style="padding:16px;display:flex;flex-direction:column;gap:14px;flex:1"><div class="duas-linhas"><span class="b">Medição nº 3</span><span class="p14 sec">Página 1 de 1 · original preservado</span></div>${folha('24px 20px')}${zoom}
<div class="achado aberto" style="box-shadow:none"><span class="p14 sec">Achado em conferência</span><span>Até a medição nº 3, o acumulado pago soma <strong>R$ 3.900.000,00</strong>.</span><div style="display:flex;flex-direction:column;gap:8px"><button type="button" class="bt bt-p bt-g bt-cheio">Confere com o original</button><div style="display:flex;gap:8px"><button type="button" class="bt bt-s bt-g" style="flex:1">Precisa de ajuste</button><button type="button" class="bt bt-r bt-g" style="flex:1">Sem suporte</button></div></div></div></main></div>`;
P['visao-geral-390'] = () => `<div class="pr" style="position:relative;width:390px;min-height:844px;display:flex;flex-direction:column">${topoCelular}
<main style="padding:20px 16px;display:flex;flex-direction:column;gap:16px">${visaoGeralCorpo(true)}</main></div>`;

// ---------- diálogos (textos reais da Mesa: piloto.js:143, index.html:275-290, gerenciar.js) ----------
const DIALOGOS = {
  simples: `<div class="dialogo" role="alertdialog" aria-modal="true" aria-labelledby="d1t" aria-describedby="d1d"><h2 id="d1t">Gerar novo link de ativação?</h2><p id="d1d">A senha atual deixa de valer e as sessões abertas são encerradas.</p>
<div class="acoes"><button type="button" class="bt bt-s">Cancelar</button><button type="button" class="bt bt-p foco">Gerar novo link</button></div></div>`,
  destrutivo: `<div class="dialogo" role="alertdialog" aria-modal="true" aria-labelledby="d2t" aria-describedby="d2d"><span class="rubrica sec">Mover para a lixeira</span><h2 id="d2t">Mover “Vila Serena — contrato de pavimentação” para a lixeira?</h2><p id="d2d" class="p14 sec">Você poderá restaurar em Apurações e lixeira. Documentos e registros serão preservados.</p>
<div class="acoes"><button type="button" class="bt bt-s foco">Cancelar</button><button type="button" class="bt bt-d">Mover para a lixeira</button></div></div>`,
  campo: `<div class="dialogo" role="alertdialog" aria-modal="true" aria-labelledby="d3t" aria-describedby="d3d"><h2 id="d3t">Apagar definitivamente</h2><p class="b">Apuração · Vila Serena — contrato de pavimentação</p><p id="d3d">Os arquivos listados saem do projeto. A Mesa não consegue recuperá-los depois.</p>
<table class="tabela-alcance"><caption style="position:absolute;left:-9999px">O que será apagado</caption><thead><tr><th scope="col">Categoria</th><th scope="col" style="text-align:right">Arquivos</th><th scope="col" style="text-align:right">Tamanho</th></tr></thead><tbody><tr><th scope="row">Originais recebidos</th><td>12</td><td>48,2 MB</td></tr><tr><th scope="row">Textos extraídos dos originais</th><td>12</td><td>3,1 MB</td></tr><tr><th scope="row">Rodadas de análise</th><td>4</td><td>1,2 MB</td></tr></tbody><tfoot><tr><th scope="row">Total</th><td colspan="2">28 arquivos, 52,5 MB</td></tr></tfoot></table>
<label class="campo"><span style="font-weight:400">Digite «<strong>Vila Serena — contrato de pavimentação</strong>» para confirmar</span><input type="text" value="Vila Serena —" class="foco" autocomplete="off" spellcheck="false"></label>
<div class="acoes"><button type="button" class="bt bt-s">Cancelar</button><button type="button" class="bt bt-x" disabled>Apagar definitivamente</button></div></div>`,
};

// ---------- escuro das telas de desktop do canvas: cada cor do claro vira o mesmo token no escuro ----------
const CLARO_ESCURO = {
  '#f6f5f0': '#171d1a', '#fffefa': '#202823', '#efefe8': '#121714', '#202c29': '#eae9df', '#5f6a63': '#a8b3a9',
  '#1e4d3e': '#a8c79d', '#2e604c': '#bad8af', '#ffffff': '#172315', '#dddfd6': '#3c4940', '#74837a': '#8a9c8f',
  '#7f9685': '#88a57f', '#8a5a12': '#e6bc7a', '#e8eee6': '#2c3c2e', '#f1f2e9': '#28322c', '#8e4b28': '#e6bc7a',
  '#f7ecdf': '#372e21', '#c58b55': '#aa8754', '#87342c': '#e7a097', '#f8e9e5': '#382725', '#b06a5c': '#a76e66',
  '#1d8058': '#3fa877', '#5b5fb8': '#8487e6',
  'rgba(23,63,41,0.06)': 'rgba(0,0,0,0.2)', 'rgba(23,63,41,0.08)': 'rgba(0,0,0,0.4)', 'rgba(23,63,41,0.10)': 'rgba(0,0,0,0.4)',
};
function escurecer(html, preservar) {
  const trocar = s => s.replace(/#[0-9a-fA-F]{6}\b|rgba\(23,63,41,0\.\d+\)/g, c => CLARO_ESCURO[c.toLowerCase()] || c);
  // Trechos preservados: a folha do documento (papel branco nos dois temas) e as amostras de cor do design system.
  const guardados = [];
  for (const re of preservar) html = html.replace(re, m => { guardados.push(m); return `\u0000${guardados.length - 1}\u0000`; });
  html = html.replace(/(style|stroke|fill)="([^"]*)"/g, (m, a, s) => `${a}="${trocar(s)}"`).replace(/<style>([\s\S]*?)<\/style>/g, (m, s) => `<style>${trocar(s)}</style>`);
  return html.replace(/\u0000(\d+)\u0000/g, (m, i) => guardados[+i]);
}
function telaCanvas(nome, tema, extra = '') {
  const raw = fs.readFileSync(path.join(canvas, `${nome}.dc.html`), 'utf8');
  let inner = raw.match(/<x-dc>([\s\S]*)<\/x-dc>/)[1];
  const helmet = (inner.match(/<helmet>([\s\S]*?)<\/helmet>/) || ['', ''])[1].replace(/<link[^>]*fonts\.googleapis[^>]*>/g, '');
  inner = inner.replace(/<helmet>[\s\S]*?<\/helmet>/, '');
  let corpo = `<style>${helmet.replace(/<\/?style>/g, '')}</style>` + moldura(`<div style="position:relative;display:inline-block;vertical-align:top">${inner}${extra}</div>`);
  if (tema === 'dark') corpo = escurecer(corpo, [
    /<div style="flex: 1; min-height: 0; background: #ffffff;[\s\S]*?Documento fictício para demonstração\.<\/div>\s*<\/div>/,
    /<div style="height: 64px; border-radius: 8px; background: [^"]*"><\/div>/g,
    /<div style="background: #171d1a; border-radius: 12px; padding: 18px;[^"]*">/,
  ]);
  return corpo;
}

// ---------- montagem e renderização ----------
const lista = [];
const add = (arquivo, tema, corpo) => lista.push({arquivo, tema, corpo});
for (const [tema, sufixo] of [['light', 'claro'], ['dark', 'escuro']]) {
  for (const [tipo, html] of Object.entries(DIALOGOS)) {
    add(`dialogo-${tipo}-${sufixo}-1440`, tema, telaCanvas('Main', tema, `<div class="veu">${html}</div>`));
    add(`dialogo-${tipo}-${sufixo}-390`, tema, moldura(P['conferir-achado-390'](`<div class="veu">${html}</div>`)));
  }
  add(`conferir-achado-${sufixo}-1024`, tema, moldura(P['conferir-achado-1024']()));
  add(`conferir-achado-gaveta-aberta-${sufixo}-1024`, tema, moldura(P['conferir-achado-1024'](true)));
  add(`visao-geral-${sufixo}-1024`, tema, moldura(P['visao-geral-1024']()));
  add(`conferir-achado-${sufixo}-390`, tema, moldura(P['conferir-achado-390']()));
  add(`conferir-achado-original-${sufixo}-390`, tema, moldura(P['conferir-achado-390-original']()));
  add(`visao-geral-${sufixo}-390`, tema, moldura(P['visao-geral-390']()));
}
for (const [nome, arq] of [['Main', 'conferir-achado'], ['Inicio', 'visao-geral'], ['Tokens', 'design-system-revisado']]) add(`${arq}-escuro-1440`, 'dark', telaCanvas(nome, 'dark'));

(async () => {
  const browser = await chromium.launch({headless: true, executablePath: chromium.executablePath()});
  for (const {arquivo, tema, corpo} of lista) {
    const html = pagina(tema, corpo);
    const fonteArq = path.join(fonteDir, `${arquivo}.html`);
    fs.writeFileSync(fonteArq, html);
    const largura = +arquivo.match(/(\d+)$/)[1];
    const page = await browser.newPage({viewport: {width: largura, height: 900}, deviceScaleFactor: 1});
    await page.route('**/*', r => r.request().url().startsWith('file:') ? r.continue() : r.abort());
    await page.goto(url.pathToFileURL(fonteArq).href);
    await page.evaluate(() => document.fonts.ready);
    await page.locator('#prancha').screenshot({path: path.join(telasDir, `${arquivo}.png`)});
    const caixa = await page.locator('#prancha').boundingBox();
    console.log(arquivo, Math.round(caixa.width), '×', Math.round(caixa.height));
    await page.close();
  }
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
