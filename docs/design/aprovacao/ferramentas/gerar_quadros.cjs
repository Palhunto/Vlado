// Propostas dos quadros para aprovação do dono (docs/design/aprovacao/quadros): hipóteses (W05), linha do tempo e
// mapa (telas finais do canvas, com escuro e 390 derivados), tabelas (W06), comparador (W07) e pedidos e prazos
// (a aba "Entrevistas e pedidos" de hoje, sem wireframe). Tokens de docs/design/novas/fonte/base.css.
// Uso: NODE_PATH=.ferramentas/node/node_modules node docs/design/aprovacao/ferramentas/gerar_quadros.cjs
const {chromium} = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const url = require('node:url');
const {aplicarDecisoes} = require(path.join(__dirname, '..', '..', 'novas', 'ferramentas', 'decisoes.cjs'));

const aprovacao = path.resolve(__dirname, '..');
const design = path.resolve(aprovacao, '..');
const destino = path.join(aprovacao, 'quadros');
const fonteDir = path.join(__dirname, 'fonte');
fs.mkdirSync(fonteDir, {recursive: true});
const rel = alvo => path.relative(fonteDir, alvo).split(path.sep).join('/');
const FD = rel(path.resolve(design, '..', '..', 'interface', 'fonts'));
const BASE = rel(path.join(design, 'novas', 'fonte', 'base.css'));
const icones = Object.fromEntries(JSON.parse(fs.readFileSync(path.join(design, 'icones', 'ferramentas', 'icones.json'), 'utf8')).icones.map(i => [i.nome, i.d]));
const svg = (d, tam, traco = 2) => `<svg aria-hidden="true" width="${tam}" height="${tam}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="${traco}" stroke-linecap="round" stroke-linejoin="round" style="flex:none"><path d="${d}"/></svg>`;
const CHECK = 'M5 12l5 5L20 7', MENU = 'M4 7h16M4 12h16M4 17h16';
const FAIXA_DERIVADO = '<div class="faixa-derivado">Derivado · aguarda aprovação do dono</div>';
const FAIXA_CANVAS = '<div class="faixa-derivado" style="background:#1e4d3e">Tela final do canvas, com as decisões do dono de 21/11/2026</div>';
const VOLTA = `<a href="#" class="bt bt-s" style="gap:6px;padding:0 12px">${svg('M15 6l-6 6 6 6', 18)}Apuração</a>`;  // P11.7: caminho de volta visível
const VOLTA_CANVAS = '<a href="#" style="display: flex; align-items: center; gap: 6px; height: 44px; padding: 0 12px; border-radius: 8px; border: 1px solid #74837a; background: #fffefa; color: #202c29; text-decoration: none; font-size: 16px"><svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#202c29" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 6l-6 6 6 6"/></svg>Apuração</a>';
const CSS = `.col{background:var(--theme-reading);border-radius:12px;padding:14px 16px;display:flex;flex-direction:column;gap:10px}
.ev{background:var(--theme-surface);border:1px solid var(--theme-line);border-radius:8px;padding:10px 12px;display:flex;flex-direction:column;gap:2px;color:var(--theme-text);text-decoration:none}
.abas{display:flex;gap:4px}.pr .abas a{height:44px;padding:0 14px;border-radius:8px;display:flex;align-items:center;text-decoration:none;color:var(--theme-text);white-space:nowrap}
.pr .abas a[aria-current]{background:var(--theme-soft);color:var(--theme-accent);font-weight:600}
.abas-cel{display:flex;gap:8px;overflow:hidden;padding:12px 16px;border-bottom:1px solid var(--theme-line);background:var(--theme-surface)}
.pr .abas-cel a{flex:none;height:40px;padding:0 14px;border-radius:999px;border:1px solid var(--theme-input-line);display:flex;align-items:center;text-decoration:none;color:var(--theme-text);white-space:nowrap}
.pr .abas-cel a[aria-current]{background:var(--theme-accent);border-color:var(--theme-accent);color:var(--theme-on-primary);font-weight:600}
table.dados{width:100%;border-collapse:collapse}table.dados th,table.dados td{padding:12px 14px;border-bottom:1px solid var(--theme-line);text-align:left;vertical-align:top}
table.dados th{font-size:14px;color:var(--theme-muted);font-weight:600;background:var(--theme-reading)}table.dados td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.rem{background:var(--theme-danger-bg);color:var(--theme-danger);text-decoration:line-through;border-radius:4px;padding:0 4px}
.inc{background:var(--theme-soft);color:var(--theme-accent);font-weight:600;border-radius:4px;padding:0 4px}
.campo select,.campo textarea{min-height:44px;padding:8px 12px;border-radius:8px;border:1px solid var(--theme-input-line);background:var(--theme-surface);font:inherit;font-weight:400;color:var(--theme-text)}`;
const pagina = (tema, corpo, faixa) => `<!doctype html><html lang="pt-BR" data-theme="${tema}"><head><meta charset="utf-8"><style>@font-face{font-family:"Source Serif 4";src:url('${FD}/SourceSerif4-Roman.ttf') format('truetype');font-weight:200 900}
@font-face{font-family:"Source Sans 3";src:url('${FD}/SourceSans3-Upright.otf') format('opentype');font-weight:200 900}${CSS}</style><link rel="stylesheet" href="${BASE}"></head><body><div id="prancha" style="display:inline-block;vertical-align:top">${corpo}${faixa}</div></body></html>`;

// ---------- cabeçalhos ----------
const ABAS = ['Hipóteses', 'Linha do tempo', 'Mapa de relações', 'Tabelas', 'Comparador'];
const cab1440 = (ativa, acoes) => `<header style="height:72px;flex:none;padding:0 32px;display:flex;align-items:center;gap:24px;background:var(--theme-surface);border-bottom:1px solid var(--theme-line)">
${VOLTA}<h1 class="serifa" style="margin:0;font-size:28px;font-weight:600">Quadros</h1><nav class="abas" aria-label="Quadros">${ABAS.map(n => `<a href="#"${n === ativa ? ' aria-current="page"' : ''}>${n}</a>`).join('')}</nav>
<div style="margin-left:auto;display:flex;gap:12px">${acoes}</div></header>`;
const topoCel = `<header class="topo"><button type="button" class="bt-ic" aria-label="Voltar à apuração">${svg('M15 6l-6 6 6 6', 22)}</button><div class="duas-linhas"><span class="p14 sec">Quadros</span><span class="nome">Vila Serena</span></div><span class="p14 sec" style="margin-left:auto;padding-right:4px;white-space:nowrap">R$ 18,40 de 50</span></header>`;
const cab390 = ativa => `${topoCel}<nav class="abas-cel" aria-label="Quadros">${['Hipóteses', 'Linha do tempo', 'Mapa', 'Tabelas', 'Comparador'].map(n => `<a href="#"${n === ativa ? ' aria-current="page"' : ''}>${n}</a>`).join('')}</nav>`;
const raiz = (w, conteudo, alto = true) => `<div class="pr" style="width:${w}px;${w === 390 ? 'min-height:844px' : (alto ? 'height:900px' : 'min-height:900px')};display:flex;flex-direction:column">${conteudo}</div>`;

// ---------- Hipóteses (W05) ----------
const ev = (txt, fonte) => `<a href="#" class="ev"><span>${txt}</span><span class="p14 sec">${fonte} · abrir o original</span></a>`;
const colunas = movel => `<div style="display:grid;grid-template-columns:${movel ? '1fr' : 'repeat(3,minmax(0,1fr))'};gap:${movel ? 12 : 16}px;align-items:start">
<div class="col" style="border-top:3px solid var(--theme-accent)"><span class="b" style="color:var(--theme-accent);display:flex;align-items:center;gap:6px">${svg(CHECK, 16, 2.5)}Sustenta</span>${ev('Aditivo acresce 22,4%', 'Aditivo 1, p. 2')}${ev('Valor original de R$ 8,75 mi', 'Contrato, p. 1')}<a href="#" class="b">+ Ligar evidência</a></div>
<div class="col" style="border-top:3px solid var(--theme-danger)"><span class="b" style="color:var(--theme-danger);display:flex;align-items:center;gap:6px">${svg(icones['sinal-sem-suporte'], 16, 2.2)}Contraria</span>${ev('Parecer cita limite de 25%', 'Parecer jurídico, p. 3')}<a href="#" class="b">+ Ligar evidência</a></div>
<div class="col" style="border-top:3px dashed var(--theme-warning)"><span class="b" style="color:var(--theme-warning);display:flex;align-items:center;gap:6px">${svg(icones.lacuna, 16, 2)}Falta</span>
<div class="ev" style="border:1px dashed var(--theme-warning);background:var(--theme-warning-bg)"><span>Qual lei rege este contrato</span><span class="p14 b" style="color:var(--theme-warning)">sem documento</span></div>
<button type="button" class="bt" style="border:1px solid var(--theme-warning);background:var(--theme-surface);color:var(--theme-warning);padding:0 14px">Virar pergunta ou pedido</button></div></div>`;
const fechada = (t, c) => `<button type="button" class="cartao" style="width:100%;text-align:left;padding:16px 20px;display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 16px;color:var(--theme-text)"><span class="serifa" style="font-size:18px">${t}</span><span class="p14 sec" style="margin-left:auto">${c}</span></button>`;
const hipCorpo = movel => `<div style="display:flex;align-items:baseline;gap:12px"><h2 class="serifa" style="margin:0;font-size:22px;font-weight:600">Hipóteses</h2><span class="p14 sec">3 hipóteses</span></div>
<section class="cartao" style="border:2px solid var(--theme-accent);box-shadow:var(--sombra-flutuante);padding:${movel ? 16 : '20px 24px'}${movel ? 'px' : ''};display:flex;flex-direction:column;gap:16px">
<div style="display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 16px"><h3 class="serifa" style="margin:0;font-size:18px;font-weight:600">O aditivo ultrapassa o limite legal de acréscimo</h3><span class="p14 sec" style="margin-left:auto">2 sustentam · 1 contraria · 1 falta</span><a href="#" class="b">Editar</a></div>${colunas(movel)}</section>
${fechada('A medição nº 3 foi paga antes da conclusão do trecho', '0 sustentam · 0 contrariam · 2 faltam')}${fechada('Sócios da construtora têm vínculo com a secretaria', '1 sustenta · 0 contrariam · 1 falta')}`;
const comoLer = `<span class="rubrica sec">Como ler</span>
<span style="display:flex;align-items:center;gap:10px;color:var(--theme-accent)">${svg(CHECK, 18, 2.5)}<span style="color:var(--theme-text)">Sustenta: evidência conferida a favor</span></span>
<span style="display:flex;align-items:center;gap:10px;color:var(--theme-danger)">${svg(icones['sinal-sem-suporte'], 18, 2.2)}<span style="color:var(--theme-text)">Contraria: evidência conferida contra</span></span>
<span style="display:flex;align-items:center;gap:10px;color:var(--theme-warning)">${svg(icones.lacuna, 18, 2)}<span style="color:var(--theme-text)">Falta: o que nenhum documento responde ainda</span></span>
<span class="p14 sec">A contagem não é placar: o quadro organiza as evidências, não decide se a hipótese é verdadeira.</span>`;
const novaHip = `<form class="cartao" style="padding:20px 24px;display:flex;flex-direction:column;gap:12px"><span class="b">Nova hipótese</span><label class="campo"><span>Escreva como afirmação que os documentos possam sustentar ou contrariar</span><input type="text"></label><div class="acoes" style="padding-top:0"><button type="button" class="bt bt-s">Cancelar</button><button type="button" class="bt bt-p">Criar</button></div></form>`;
const hip1440 = () => raiz(1440, `${cab1440('Hipóteses', '<button type="button" class="bt bt-p">Nova hipótese</button>')}<div style="flex:1;min-height:0;display:flex">
<main style="flex:1;min-width:0;padding:28px 40px;display:flex;flex-direction:column;gap:16px">${hipCorpo(false)}<div style="margin-top:auto">${novaHip}</div></main>
<aside aria-label="Como ler" style="width:360px;flex:none;background:var(--theme-surface);border-left:1px solid var(--theme-line);padding:28px 24px;display:flex;flex-direction:column;gap:14px">${comoLer}</aside></div>`);
const hip390 = () => raiz(390, `${cab390('Hipóteses')}<main style="padding:20px 16px;display:flex;flex-direction:column;gap:14px"><button type="button" class="bt bt-p bt-g bt-cheio">Nova hipótese</button>${hipCorpo(true)}</main>`);

// ---------- Tabelas (W06) ----------
const linhas = movel => [
  ['Medição nº 1', '30/04/2025', '1.200.000,00', '', 'Medição 1, p. 1'],
  ['Medição nº 2', '30/06/2025', '1.450.000,00', '', 'Medição 2, p. 1'],
  ['Medição nº 3', '31/08/2025', '1.250.000,00', 'corr', 'Medição 3, p. 1 · OCR'],
  ['Medição nº 4', '—', '', 'pend', ''],
].map(([m, d, v, e, f]) => `<tr${e === 'corr' ? ' style="background:var(--theme-active)"' : ''}><td>${m}</td><td>${d}</td><td class="num">${e === 'pend' ? '<span class="sec">○ a conferir</span>' : e === 'corr' ? `<span style="display:inline-flex;align-items:center;gap:6px;color:var(--theme-warning);font-weight:600${movel ? '' : ';outline:3px solid var(--theme-focus);outline-offset:4px;border-radius:2px'}">${svg(icones['sinal-corrigido'], 16, 2)}<span style="color:var(--theme-text)">${v}</span></span>` : v}</td><td>${f ? `<a href="#">${f}</a>` : '<span class="sec">sem fonte ainda</span>'}</td></tr>`).join('');
const tabela = movel => `<div style="display:flex;flex-wrap:wrap;align-items:baseline;gap:8px 12px"><h2 class="serifa" style="margin:0;font-size:22px;font-weight:600">Pagamentos do contrato 041/2025</h2><span class="p14 sec">4 linhas · 1 corrigida</span></div>
<div class="cartao" style="overflow:${movel ? 'hidden' : 'visible'}"><div style="${movel ? 'width:560px' : ''}"><table class="dados"><thead><tr><th scope="col">Medição</th><th scope="col">Data</th><th scope="col" style="text-align:right">Valor (R$)</th><th scope="col">Fonte</th></tr></thead><tbody>${linhas(movel)}</tbody></table></div></div>
${movel ? '<span class="p14 sec">A tabela rola para o lado dentro da caixa.</span>' : ''}
<div class="cartao" style="padding:14px 18px;display:flex;flex-wrap:wrap;align-items:center;gap:8px 12px"><span class="b">Cálculo</span><button type="button" class="bt bt-s" style="height:40px;padding:0 12px">Soma ▾</button><span>de Valor, linhas 1 a 3</span><span class="b serifa" style="font-size:18px">= R$ 3.900.000,00</span><a href="#" class="b" style="margin-left:auto">ver a conta</a></div>
<span class="p14 sec">A linha 4 fica fora da soma porque não tem valor conferido. Sem conversão entre moedas ou unidades.</span>`;
const celula = `<span class="rubrica" style="color:var(--theme-accent)">Célula selecionada</span><span class="p14 sec">Medição nº 3 · Valor (R$)</span>
<div style="display:flex;flex-direction:column;gap:4px"><span class="p14 sec">Lido pelo OCR</span><s class="serifa" style="font-size:18px;color:var(--theme-muted)">1.260.000,00</s><span class="p14 sec" style="margin-top:6px">Corrigido por você</span><span class="serifa b" style="font-size:18px">1.250.000,00</span></div>
<label class="campo"><span>Por que corrigiu (obrigatório)</span><textarea rows="3">Conferido no original: o 5 foi lido como 6.</textarea></label>
<div style="display:flex;gap:8px"><button type="button" class="bt bt-s" style="flex:1">Abrir original</button><button type="button" class="bt bt-p" style="flex:1">Salvar</button></div><a href="#" class="b">Histórico desta célula (2)</a>`;
const tab1440 = () => raiz(1440, `${cab1440('Tabelas', '<button type="button" class="bt bt-s">Exportar CSV</button><button type="button" class="bt bt-p">Adicionar linha</button>')}<div style="flex:1;min-height:0;display:flex">
<main style="flex:1;min-width:0;padding:28px 40px;display:flex;flex-direction:column;gap:16px">${tabela(false)}</main>
<aside aria-label="Célula selecionada" style="width:360px;flex:none;background:var(--theme-surface);border-left:1px solid var(--theme-line);padding:28px 24px;display:flex;flex-direction:column;gap:14px">${celula}</aside></div>`);
const tab390 = () => raiz(390, `${cab390('Tabelas')}<main style="padding:20px 16px;display:flex;flex-direction:column;gap:14px"><div style="display:flex;gap:8px"><button type="button" class="bt bt-s" style="flex:1">Exportar CSV</button><button type="button" class="bt bt-p" style="flex:1">Adicionar linha</button></div>${tabela(true)}<section class="cartao" style="padding:16px;display:flex;flex-direction:column;gap:12px">${celula}</section></main>`);

// ---------- Comparador (W07) ----------
const lado = (rot, doc, a, b, fonte) => `<section class="cartao" style="padding:18px 20px;display:flex;flex-direction:column;gap:12px;flex:1;min-width:0"><span class="p14 b sec">${rot}</span><button type="button" class="bt bt-s bt-cheio" style="justify-content:space-between"><span>${doc}</span><span aria-hidden="true">▾</span></button>
<p class="serifa" style="margin:0;font-size:18px;line-height:1.8">O valor global do presente contrato ${a[0]} ${a[1]}, a ser pago conforme medições mensais, com prazo de execução de ${b} contados da ordem de serviço.</p><span class="p14 sec">${fonte} · <a href="#">abrir original</a></span></section>`;
const ladoA = lado('Lado A', 'Contrato 041/2025 · cláusula 3ª', ['é de', '<span class="rem"><span aria-hidden="true">− </span>R$ 8.750.000,00</span>'], '<span class="rem"><span aria-hidden="true">− </span>12 meses</span>', 'Contrato, p. 1');
const ladoB = lado('Lado B', 'Termo aditivo nº 1 · cláusula 1ª', ['passa a ser de', '<span class="inc"><span aria-hidden="true">+ </span>R$ 10.710.000,00</span>'], '<span class="inc"><span aria-hidden="true">+ </span>16 meses</span>', 'Aditivo 1, p. 2');
const conta = `<section class="cartao" style="padding:18px 20px;display:flex;flex-wrap:wrap;align-items:center;gap:8px 16px"><span class="b">Diferença de valor</span><span class="serifa" style="font-size:18px">10.710.000 − 8.750.000 = <strong>R$ 1.960.000,00</strong> (22,4%)</span><button type="button" class="bt bt-p" style="margin-left:auto">Guardar como achado a conferir</button></section>
<span class="p14 sec">O comparador mostra o que mudou. Não diz se a mudança é irregular.</span>`;
const topoComp = movel => `<div style="display:flex;flex-wrap:wrap;align-items:center;gap:8px 12px"><h2 class="serifa" style="margin:0;font-size:22px;font-weight:600">Comparador</h2><span class="p14 sec">3 diferenças: 2 de valor · 1 de data</span>${movel ? '' : '<div style="margin-left:auto;display:flex;gap:8px"><button type="button" class="bt bt-s">Anterior</button><button type="button" class="bt bt-s">Próxima</button></div>'}</div>`;
const comp1440 = () => raiz(1440, `${cab1440('Comparador', '')}<main style="flex:1;padding:28px 40px;display:flex;flex-direction:column;gap:16px">${topoComp(false)}<div style="display:flex;gap:16px">${ladoA}${ladoB}</div>${conta}</main>`);
const difs = [['Valor global', 'R$ 8.750.000,00', 'R$ 10.710.000,00'], ['Prazo de execução', '12 meses', '16 meses'], ['Data de início', '3 de março de 2025', '1º de outubro de 2025']];
const comp390 = () => raiz(390, `${cab390('Comparador')}<main style="padding:20px 16px;display:flex;flex-direction:column;gap:14px">${topoComp(true)}
<div style="display:flex;flex-direction:column;gap:8px"><button type="button" class="bt bt-s bt-cheio" style="justify-content:space-between"><span><span class="sec">A:</span> Contrato 041/2025 · cl. 3ª</span><span aria-hidden="true">▾</span></button><button type="button" class="bt bt-s bt-cheio" style="justify-content:space-between"><span><span class="sec">B:</span> Termo aditivo nº 1 · cl. 1ª</span><span aria-hidden="true">▾</span></button></div>
<ol style="margin:0;padding:0;list-style:none;display:flex;flex-direction:column;gap:10px">${difs.map(([n, a, b], i) => `<li class="cartao" style="padding:14px 16px;display:flex;flex-direction:column;gap:6px${i === 0 ? ';border:2px solid var(--theme-accent)' : ''}"><span class="p14 b sec">${i + 1} de 3 · ${n}</span><span><span class="rem"><span aria-hidden="true">− </span>${a}</span></span><span><span class="inc"><span aria-hidden="true">+ </span>${b}</span></span>${i === 0 ? '<span class="p14">10.710.000 − 8.750.000 = <strong>R$ 1.960.000,00</strong> (22,4%)</span>' : ''}</li>`).join('')}</ol>
<button type="button" class="bt bt-p bt-g bt-cheio">Guardar como achado a conferir</button><span class="p14 sec">O comparador mostra o que mudou. Não diz se a mudança é irregular.</span></main>`);

// ---------- Pedidos e prazos (hoje: aba "Entrevistas e pedidos"; sem wireframe) ----------
const lateral = `<nav class="lateral" aria-label="Áreas" style="flex:none"><div class="marca" style="padding:0 8px">Vlado<span>.</span></div><div class="areas">${[['Visão geral'], ['Documentos', '<span class="cont sec">12</span>'], ['Perguntar'], ['Conferir', '<span class="cont cont-pilula">4</span>'], ['Quadros'], ['Caderno'], ['Pedidos e prazos', '<span class="cont cont-pilula" style="color:var(--theme-warning)">1 vence</span>']].map(([n, x = '']) => `<a href="#"${n === 'Pedidos e prazos' ? ' aria-current="page"' : ''}>${n} ${x}</a>`).join('')}</div>
<div style="margin-top:auto;display:flex;flex-direction:column;gap:12px"><div class="cota"><div style="display:flex;justify-content:space-between;gap:8px;font-size:14px"><span class="sec">Cota do mês</span><span class="b">R$ 18,40 de R$ 50</span></div><div class="medidor" role="img" aria-label="37% da cota usada"><div style="width:37%"></div></div></div>
<a href="#" class="perfil"><span class="avatar" aria-hidden="true">AL</span><span class="duas-linhas"><span class="b">Ana Lima</span><span class="p14 sec">Repórter · Redação Serena</span></span></a></div></nav>`;
const selo = (txt, cor) => `<span class="selo" style="color:var(--theme-${cor});background:var(--theme-${cor === 'accent' ? 'soft' : cor === 'warning' ? 'warning-bg' : 'surface'});border-color:var(--theme-${cor === 'accent' ? 'accent-line' : cor === 'warning' ? 'warning-line' : 'input-line'})">${txt}</span>`;
const pedido = (tipo, cor, titulo, dest, prazo, situ, evs, aberto) => `<article class="cartao" style="padding:16px 20px;display:flex;flex-direction:column;gap:10px${aberto ? ';border:2px solid var(--theme-accent);box-shadow:var(--sombra-flutuante)' : ''}">
<div style="display:flex;flex-wrap:wrap;align-items:center;gap:8px">${selo(tipo, 'text')}${prazo}<span class="p14 sec" style="margin-left:auto">${situ}</span></div>
<span class="serifa" style="font-size:18px">${titulo}</span><span class="p14 sec">${dest} · ${evs}</span>
${aberto ? '<div style="display:flex;flex-wrap:wrap;gap:8px"><button type="button" class="bt bt-p">Registrar resposta recebida</button><button type="button" class="bt bt-s">Exportar texto do pedido</button></div>' : ''}</article>`;
const listaPedidos = `${pedido('Pedido via LAI', 'text', 'Quem são os sócios da Construtora Alfa Ltda. e desde quando?', 'Destinatário: Prefeitura de Vila Serena, serviço de informação ao cidadão', selo('! vence em 5 dias · 2 de dezembro', 'warning'), 'Situação: aguardando resposta', '2 evidências motivam a pergunta', true)}
${pedido('Entrevista', 'text', 'Qual lei rege o limite de acréscimo deste contrato?', 'Destinatário: Secretaria de Obras, assessoria', '<span class="p14 sec">sem prazo</span>', 'Situação: pergunta preparada', '1 evidência motiva a pergunta', false)}
${pedido('Pedido de informação', 'text', 'Houve medição entre setembro e outubro de 2025?', 'Destinatário: Secretaria de Obras', selo('✓ respondido', 'accent'), 'Resposta: Ofício 88/2025, p. 1', '1 evidência motiva a pergunta', false)}`;
const lacunas = `<span class="rubrica sec">Lacunas que pedem contato</span>${[['Qual lei rege este contrato', 'Hipótese: o aditivo ultrapassa o limite legal'], ['Cerca de um mês sem nenhum documento', 'Linha do tempo: setembro a outubro de 2025'], ['Sócios da construtora', 'Achado: lacuna na conferência']].map(([t, o]) => `<div class="ev" style="border:1px dashed var(--theme-warning);background:var(--theme-warning-bg)"><span>${t}</span><span class="p14 sec">${o}</span></div>`).join('')}<button type="button" class="bt bt-s bt-cheio">Preparar pergunta</button>
<span class="p14 sec">A pauta interna exportada não vai para a fonte: o texto do pedido sai só com as perguntas.</span>`;
const ped1440 = () => raiz(1440, `<div style="flex:1;display:flex">${lateral}<div style="flex:1;min-width:0;display:flex;flex-direction:column">
<header style="height:64px;flex:none;padding:0 32px;display:flex;align-items:center;gap:16px;background:var(--theme-surface);border-bottom:1px solid var(--theme-line)"><div class="duas-linhas"><span class="p14 sec">Apuração</span><span class="b">Vila Serena — contrato de pavimentação (sintética)</span></div><button type="button" class="bt bt-s" style="margin-left:auto">Exportar pauta interna</button><button type="button" class="bt bt-p">Nova pergunta</button></header>
<div style="flex:1;min-height:0;display:flex"><main style="flex:1;min-width:0;padding:28px 32px;display:flex;flex-direction:column;gap:14px"><div style="display:flex;align-items:baseline;gap:12px"><h1 class="serifa" style="margin:0;font-size:28px;font-weight:600;line-height:1.2">Pedidos e prazos</h1><span class="p14 sec">3 perguntas · 1 vence em 5 dias</span></div>${listaPedidos}</main>
<aside aria-label="Lacunas" style="width:360px;flex:none;background:var(--theme-surface);border-left:1px solid var(--theme-line);padding:28px 24px;display:flex;flex-direction:column;gap:12px">${lacunas}</aside></div></div></div>`);
const ped390 = () => raiz(390, `${topoCel.replace('Quadros', 'Apuração').replace('aria-label="Voltar à apuração">' + svg('M15 6l-6 6 6 6', 22), 'aria-label="Abrir menu">' + svg(MENU, 22))}<main style="padding:20px 16px;display:flex;flex-direction:column;gap:14px"><div style="display:flex;flex-direction:column;gap:2px"><h1 class="serifa" style="margin:0;font-size:28px;font-weight:600;line-height:1.2">Pedidos e prazos</h1><span class="p14 sec">3 perguntas · 1 vence em 5 dias</span></div><button type="button" class="bt bt-p bt-g bt-cheio">Nova pergunta</button>${listaPedidos}<section class="cartao" style="padding:16px;display:flex;flex-direction:column;gap:10px">${lacunas}</section></main>`);

// ---------- Linha do tempo e mapa: telas finais do canvas; escuro pela troca de tokens; 390 derivado ----------
const CLARO_ESCURO = {'#f6f5f0': '#171d1a', '#fffefa': '#202823', '#efefe8': '#121714', '#202c29': '#eae9df', '#5f6a63': '#a8b3a9', '#1e4d3e': '#a8c79d', '#2e604c': '#bad8af', '#ffffff': '#172315', '#dddfd6': '#3c4940', '#74837a': '#8a9c8f', '#7f9685': '#88a57f', '#8a5a12': '#e6bc7a', '#e8eee6': '#2c3c2e', '#f1f2e9': '#28322c', '#8e4b28': '#e6bc7a', '#f7ecdf': '#372e21', '#c58b55': '#aa8754', '#87342c': '#e7a097', '#f8e9e5': '#382725', '#b06a5c': '#a76e66', '#1d8058': '#3fa877', '#5b5fb8': '#8487e6', 'rgba(23,63,41,0.06)': 'rgba(0,0,0,0.2)', 'rgba(23,63,41,0.08)': 'rgba(0,0,0,0.4)', 'rgba(23,63,41,0.10)': 'rgba(0,0,0,0.4)'};
const escurecer = h => h.replace(/(style|stroke|fill)="([^"]*)"/g, (m, a, s) => `${a}="${s.replace(/#[0-9a-fA-F]{6}\b|rgba\(23,63,41,0\.\d+\)/g, c => CLARO_ESCURO[c.toLowerCase()] || c)}"`)
  .replace(/<style>([\s\S]*?)<\/style>/g, (m, s) => `<style>${s.replace(/#[0-9a-fA-F]{6}\b/g, c => CLARO_ESCURO[c.toLowerCase()] || c)}</style>`);
function telaCanvas(nome, escuro) {
  const raw = fs.readFileSync(path.join(design, 'referencia', 'canvas', `${nome}.dc.html`), 'utf8');
  let inner = raw.match(/<x-dc>([\s\S]*)<\/x-dc>/)[1];
  const helmet = (inner.match(/<helmet>([\s\S]*?)<\/helmet>/) || ['', ''])[1].replace(/<link[^>]*fonts\.googleapis[^>]*>/g, '');
  inner = `<style>${helmet.replace(/<\/?style>/g, '')}</style>` + inner.replace(/<helmet>[\s\S]*?<\/helmet>/, '').replace(/(<h1[^>]*>Quadros<\/h1>)/, VOLTA_CANVAS + '$1');
  return escuro ? escurecer(inner) : inner;
}
const evento = (data, qual, cheio, icone, titulo, meta, fonte, alerta) => `<li style="display:flex;gap:12px"><span aria-hidden="true" style="flex:none;width:32px;height:32px;border-radius:999px;display:flex;align-items:center;justify-content:center;margin-top:2px;${cheio ? 'background:var(--theme-accent);color:var(--theme-on-primary)' : 'border:2px solid var(--theme-accent);color:var(--theme-accent)'}">${svg(icone, 16, 2)}</span>
<div class="cartao" style="flex:1;min-width:0;padding:12px 14px;display:flex;flex-direction:column;gap:4px"><span class="p14"><span class="b">${data}</span> · <span style="${alerta === 'data' ? 'color:var(--theme-warning);font-weight:600' : 'color:var(--theme-muted)'}">${qual}</span></span><span class="serifa" style="font-size:18px">${titulo}</span><span class="p14" style="${alerta === 'ocr' ? 'color:var(--theme-warning);font-weight:600' : 'color:var(--theme-muted)'}">${meta}</span><a href="#" class="p14 b" style="align-self:flex-start;background:var(--theme-soft);border-radius:999px;padding:4px 12px;text-decoration:none">${fonte}</a></div></li>`;
const tempo390 = () => raiz(390, `${cab390('Linha do tempo')}<main style="padding:20px 16px;display:flex;flex-direction:column;gap:14px">
<div style="display:flex;gap:8px;overflow:hidden">${['Tudo', 'Pagamentos', 'Contratos', 'Pedidos'].map((n, i) => `<button type="button" class="bt" style="flex:none;border-radius:999px;padding:0 14px;${i === 0 ? 'border:0;background:var(--theme-accent);color:var(--theme-on-primary);font-weight:600' : 'border:1px solid var(--theme-input-line);background:var(--theme-surface);color:var(--theme-text)'}">${n}</button>`).join('')}</div>
<div style="display:flex;align-items:baseline;gap:12px"><span class="serifa" style="font-size:36px;font-weight:600;line-height:1">2025</span><span class="p14 sec">6 acontecimentos · 5 com documento</span></div>
<ol style="margin:0;padding:0;list-style:none;display:flex;flex-direction:column;gap:12px">
${evento('3 mar', 'data exata', true, icones.contrato, 'Prefeitura assina o contrato 041/2025 com a Construtora Alfa', 'Assinatura · R$ 8.750.000,00', 'Contrato, p. 1')}
${evento('31 ago', 'data exata', true, icones.pagamento, 'Medição nº 3 eleva o acumulado pago a R$ 3.900.000,00', 'Pagamento · página lida por OCR, confira o número', 'Medição 3, p. 1', 'ocr')}
<li class="cartao" style="padding:12px 14px;display:flex;flex-direction:column;gap:10px;background:var(--theme-warning-bg);border:1px dashed var(--theme-warning)"><span class="b" style="color:var(--theme-warning)">Cerca de um mês sem nenhum documento</span><button type="button" class="bt" style="border:1px solid var(--theme-warning);background:var(--theme-surface);color:var(--theme-warning)">Virar pergunta ou pedido</button></li>
${evento('out', 'dia não informado', false, icones['evento-aditivo'], 'Termo aditivo nº 1 acresce R$ 1.960.000,00 ao contrato', 'Aditivo · o documento traz só mês e ano', 'Aditivo 1, p. 2', 'data')}
${evento('12 nov', 'data exata', true, icones['evento-pedido'], 'Pedido de LAI sobre os sócios da construtora é protocolado', 'Pedido de informação · resposta devida até 2 de dezembro', 'Protocolo, p. 1')}</ol>
<span class="p14 sec">Só entra na linha o que tem documento ou foi marcado por você como a confirmar.</span></main>`);
const ligacao = (icone, txt, alvo, fonte, confirmar) => `<li style="display:flex;gap:10px;align-items:flex-start;padding:10px 0;border-top:1px solid var(--theme-line)"><span style="display:flex;margin-top:3px;color:${confirmar ? 'var(--theme-warning)' : 'var(--theme-text)'}">${svg(icone, 16, 2.2)}</span><span style="display:flex;flex-direction:column;gap:2px"><span><span class="b"${confirmar ? ' style="color:var(--theme-warning)"' : ''}>${txt}</span> ${alvo}</span><span class="p14 sec">${fonte}</span></span></li>`;
const entidade = (forma, cor, icone, nome, tipo, ligs) => `<section class="cartao" style="padding:14px 16px;display:flex;flex-direction:column;gap:8px"><div style="display:flex;align-items:center;gap:10px"><svg aria-hidden="true" width="36" height="36" viewBox="0 0 36 36">${forma === 'c' ? `<circle cx="18" cy="18" r="18" fill="var(--theme-${cor})"/>` : `<rect width="36" height="36" rx="${forma === 'q' ? 9 : 3}" fill="${cor.startsWith('#') ? cor : `var(--theme-${cor})`}"/>`}<g transform="translate(6 6)" fill="none" stroke="var(--theme-on-primary)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="${icone}"/></g></svg><span class="duas-linhas"><span class="b">${nome}</span><span class="p14 sec">${tipo}</span></span></div><ul style="margin:0;padding:0;list-style:none">${ligs}</ul></section>`;
const mapa390 = escuro => raiz(390, `${cab390('Mapa')}<main style="padding:20px 16px;display:flex;flex-direction:column;gap:12px">
<div style="display:flex;align-items:center;gap:8px"><span class="p14 sec">No celular, o mapa abre como lista de ligações.</span></div>
${entidade('q', 'entidade-organizacao', icones.empresa, 'Construtora Alfa Ltda.', 'Empresa · 9 documentos', ligacao(icones.contrato, 'Contratada pela', 'Prefeitura de Vila Serena', 'Contrato 041/2025 · ✓ 2 evidências conferidas') + ligacao(icones['relacao-socio'], 'Sócio:', 'João Prado', 'Contrato social, p. 2') + ligacao(icones['relacao-socio'], 'Sócia:', 'Marta Reis', 'Contrato social, p. 2') + ligacao(icones.contrato, 'Subcontratou', 'Pavimenta Sul S.A.', 'Subcontrato, p. 1'))}
${entidade('c', 'entidade-pessoa', icones.pessoa, 'João Prado', 'Pessoa · 3 documentos', ligacao(icones['relacao-parentesco'], 'Irmãos? A confirmar:', 'Carlos Prado', 'sem documento', true))}
${entidade('r', '#3d4a45', icones['orgao-publico'], 'Prefeitura de Vila Serena', 'Órgão público', ligacao(icones['relacao-vinculo'], 'Vinculada:', 'Secretaria de Obras', 'Lei municipal 1.204, art. 3'))}
<div class="aviso" style="display:flex;flex-direction:column;gap:6px;font-size:16px"><span class="b" style="color:var(--theme-warning)">Possível homônimo</span><span class="p14">“João Prado” aparece em dois documentos sem CPF. O Vlado não funde pessoas sozinho: confira antes de tratar como a mesma.</span></div>
<button type="button" class="bt bt-p bt-g bt-cheio">Adicionar ligação</button><span class="p14 sec">O mapa organiza o que os documentos dizem. Ele não avalia se é verdade.</span></main>`);

// ---------- montagem ----------
const lista = [];
for (const [tema, nome] of [['light', 'claro'], ['dark', 'escuro']]) {
  const escuro = tema === 'dark';
  for (const [sub, f1440, f390] of [['hipoteses', hip1440, hip390], ['tabelas', tab1440, tab390], ['comparador', comp1440, comp390], ['pedidos-e-prazos', ped1440, ped390]]) {
    lista.push({arq: `proposta-${sub}-${nome}-1440`, tema, corpo: f1440(), faixa: FAIXA_DERIVADO});
    lista.push({arq: `proposta-${sub}-${nome}-390`, tema, corpo: f390(), faixa: FAIXA_DERIVADO});
  }
  lista.push({arq: `proposta-linha-do-tempo-${nome}-1440`, tema, corpo: telaCanvas('Tempo', escuro), faixa: escuro ? FAIXA_DERIVADO : FAIXA_CANVAS});
  lista.push({arq: `proposta-linha-do-tempo-${nome}-390`, tema, corpo: tempo390(), faixa: FAIXA_DERIVADO});
  lista.push({arq: `proposta-mapa-${nome}-1440`, tema, corpo: telaCanvas('Mapa', escuro), faixa: escuro ? FAIXA_DERIVADO : FAIXA_CANVAS});
  lista.push({arq: `proposta-mapa-${nome}-390`, tema, corpo: mapa390(escuro), faixa: FAIXA_DERIVADO});
}

(async () => {
  const browser = await chromium.launch({headless: true, executablePath: chromium.executablePath()});
  for (const {arq, tema, corpo, faixa} of lista) {
    const html = path.join(fonteDir, `quadros-${arq}.html`);
    fs.writeFileSync(html, aplicarDecisoes(pagina(tema, corpo, faixa), {escuro: tema === 'dark'}));
    const page = await browser.newPage({viewport: {width: +arq.match(/(\d+)$/)[1], height: 900}, deviceScaleFactor: 1});
    await page.route('**/*', r => r.request().url().startsWith('file:') ? r.continue() : r.abort());
    await page.goto(url.pathToFileURL(html).href);
    await page.evaluate(() => document.fonts.ready);
    await page.locator('#prancha').screenshot({path: path.join(destino, `${arq}.png`)});
    const caixa = await page.locator('#prancha').boundingBox();
    console.log(arq, Math.round(caixa.width), '×', Math.round(caixa.height));
    await page.close();
  }
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
