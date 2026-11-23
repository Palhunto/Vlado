"""Contraste WCAG AA nos dois temas (Onda 3, portão "WCAG AA comprovado por captura").

    python testes/contraste_wcag.py medir                       # 14 telas x 375/1440 px x claro/escuro
    python testes/contraste_wcag.py medir --telas cadastro --larguras 375 --temas escuro

Abre as telas da linha de base da regressão visual (mesmos servidores sintéticos, mesma pasta semeada, mesmo
navegador, mesmo relógio; nada de rede externa e nenhum dado real) e, em cada uma, mede:

  * texto: o contraste de todo texto visível (nós de texto, valor e placeholder de campos, texto SVG do mapa) contra
    o fundo que de fato está atrás dele. Mínimo 4,5:1; 3:1 para texto grande (>= 24 px, ou >= 18,66 px em negrito).
  * foco: percorre a tela inteira com Tab e mede o contorno de cada elemento focado contra o que o cerca. Mínimo 3:1.
    Sem contorno nem sombra de foco, o que muda no foco (borda ou fundo) é medido do mesmo jeito; se nada muda, reprova.
  * campo: a borda de cada campo (input, select, textarea) contra o fundo vizinho, ou o fundo do próprio campo contra o
    vizinho. Mínimo 3:1 (componente de interface, WCAG 1.4.11).

O fundo vem da pilha de elementos no ponto do texto (`elementsFromPoint`), compondo cor de fundo, opacidade e SVG de cima
para baixo até ficar opaco; gradiente é medido nas cores de cada parada (vale a pior); foto ou imagem de fundo não dá para
medir e entra em "não medidos", assim como texto coberto por outro elemento. Controles desativados são isentos (WCAG 1.4.3 e
1.4.11) e só contados. Só as telas carregadas: diálogos, menus abertos, hover e estados de erro não entram.

Saída: tmp/contraste_wcag/relatorio.md (reprovações tela por tela), relatorio.json e relatorio.html. Código de saída 1 se algo
reprovar; 2 se a rodada em si falhar (tela que não abriu, pedido externo).

Dois Pythons, como em regressao_visual.py: este precisa de Playwright (`testes/requirements-teste.txt`); o servidor roda no
Python do projeto (`.venv`).
"""
from __future__ import annotations

import argparse
import contextlib
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import shutil
import sys

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
sys.path.insert(0, str(AQUI))

LARGURAS_PADRAO = (375, 1440)
MINIMO_TEXTO, MINIMO_TEXTO_GRANDE, MINIMO_COMPONENTE = 4.5, 3.0, 3.0


# ---------------------------------------------------------------- matemática (sem navegador)

def parse_hex(cor: str) -> tuple:
    cor = cor.lstrip('#')
    return tuple(int(cor[i:i + 2], 16) for i in (0, 2, 4))


def luminancia(rgb) -> float:
    def canal(v):
        v = v / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (canal(v) for v in rgb[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def razao(a, b) -> float:
    la, lb = luminancia(a), luminancia(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def texto_grande(px: float, peso: int) -> bool:
    """WCAG: 18 pt (24 px) ou 14 pt (18,66 px) em negrito."""
    return px >= 24 or (px >= 18.66 and peso >= 700)


def minimo_do_texto(px: float, peso: int) -> float:
    return MINIMO_TEXTO_GRANDE if texto_grande(px, peso) else MINIMO_TEXTO


def arredondar(valor: float) -> float:
    """Para baixo, em duas casas: 4,499 nunca vira 4,50."""
    return int(valor * 100) / 100


# ---------------------------------------------------------------- JavaScript da página

# Instala `window.__vc` (cores, pilha de fundos, descrição de elementos). Roda uma vez por página.
JS_PREPARO = r"""() => {
  if (window.__vc) return true;
  const cache = new Map();
  const cv = document.createElement('canvas'); cv.width = cv.height = 1;
  const cx = cv.getContext('2d', {willReadFrequently: true});
  function cor(s) {
    if (cache.has(s)) return cache.get(s);
    let r = null;
    const m = /^rgba?\(\s*([\d.]+)[ ,]+([\d.]+)[ ,]+([\d.]+)(?:\s*[,/]\s*([\d.]+%?))?\s*\)$/.exec(s);
    if (m) {
      const a = m[4] === undefined ? 1 : (m[4].endsWith('%') ? parseFloat(m[4]) / 100 : parseFloat(m[4]));
      r = [+m[1], +m[2], +m[3], a];
    } else {
      cx.clearRect(0, 0, 1, 1); cx.fillStyle = '#123456'; cx.fillStyle = s;
      if (cx.fillStyle !== '#123456' || s.trim().toLowerCase() === '#123456') {
        cx.fillRect(0, 0, 1, 1); const d = cx.getImageData(0, 0, 1, 1).data; r = [d[0], d[1], d[2], d[3] / 255];
      }
    }
    cache.set(s, r); return r;
  }
  const lum = (c) => { const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); };
  const razao = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  const hex = (c) => '#' + c.slice(0, 3).map(v => Math.round(v).toString(16).padStart(2, '0')).join('');
  const sobre = (f, b) => {   // f sobre b (ambos [r,g,b,a])
    const a = f[3] + b[3] * (1 - f[3]); if (a <= 0) return [0, 0, 0, 0];
    return [0, 1, 2].map(i => (f[i] * f[3] + b[i] * b[3] * (1 - f[3])) / a).concat([a]);
  };
  function opacidade(el) {
    let o = 1;
    for (let n = el; n && n.nodeType === 1; n = n.parentElement || (n.getRootNode && n.getRootNode().host)) {
      const v = parseFloat(getComputedStyle(n).opacity); if (!isNaN(v)) o *= v;
    }
    return o;
  }
  const OPACOS = ['IMG', 'VIDEO', 'CANVAS', 'IFRAME', 'OBJECT', 'EMBED', 'PICTURE'];
  function camadas(e) {   // da frente para trás; 'desconhecido' quando não dá para medir (foto)
    const cs = getComputedStyle(e), op = opacidade(e), saida = [];
    if (e instanceof SVGElement) {
      if (e.tagName.toLowerCase() === 'svg') return saida;
      const f = cs.fill;
      if (f && f.startsWith('url')) { saida.push('desconhecido'); return saida; }
      if (f && f !== 'none') { const c = cor(f); if (c) saida.push([[c[0], c[1], c[2], c[3] * parseFloat(cs.fillOpacity) * op]]); }
      return saida;
    }
    if (OPACOS.includes(e.tagName)) { saida.push('desconhecido'); return saida; }
    const bi = cs.backgroundImage;
    if (bi && bi !== 'none') {
      if (/gradient/.test(bi) && !/url\(/.test(bi)) {
        const toks = bi.match(/rgba?\([^)]*\)|color\([^)]*\)|oklab\([^)]*\)|oklch\([^)]*\)|lab\([^)]*\)|lch\([^)]*\)/g) || [];
        const alts = toks.map(cor).filter(Boolean).map(c => [c[0], c[1], c[2], c[3] * op]);
        saida.push(alts.length ? alts : 'desconhecido');
      } else saida.push('desconhecido');
    }
    const bc = cor(cs.backgroundColor);
    if (bc && bc[3] > 0) saida.push([[bc[0], bc[1], bc[2], bc[3] * op]]);
    return saida;
  }
  function base() {
    const esquema = getComputedStyle(document.documentElement).colorScheme || '';
    return /dark/.test(esquema) && !/light/.test(esquema) ? [18, 18, 18, 1] : [255, 255, 255, 1];
  }
  function compor(lista) {   // -> {cand: [[r,g,b,a]...], desconhecido, semFundo}
    let res = [[0, 0, 0, 0]], desconhecido = false;
    for (const L of lista) {
      if (res.every(r => r[3] >= 0.999)) break;
      if (L === 'desconhecido') { desconhecido = true; break; }
      const novo = [];
      for (const r of res) { if (r[3] >= 0.999) { novo.push(r); continue; } for (const alt of L) novo.push(sobre(r, alt)); }
      res = novo.slice(0, 32);
    }
    const opaco = res.every(r => r[3] >= 0.999);
    if (desconhecido && !opaco) return {cand: [], desconhecido: true, semFundo: false};
    return {cand: res.map(r => sobre(r, base())), desconhecido: false, semFundo: !opaco};
  }
  // Fundo no ponto (x, y). Com `el`, começa no elemento (o fundo dele conta) e recusa se algo que não é descendente o cobre.
  function fundoNoPonto(x, y, el, incluirEl) {
    const pilha = document.elementsFromPoint(x, y);
    let i = 0, ancestrais = false;
    if (el) {
      i = pilha.findIndex(e => e === el || e.contains(el));
      if (i < 0) ancestrais = true;
      else if (!pilha.slice(0, i).every(e => el.contains(e))) return {coberto: true, cand: [], desconhecido: false, semFundo: false};
    }
    let seq;
    if (ancestrais) { seq = []; for (let n = el; n; n = n.parentElement) seq.push(n); }
    else seq = pilha.slice(i);
    const lista = [];
    for (const e of seq) {
      if (el && e === el && el instanceof SVGElement) continue;   // o preenchimento do texto/forma SVG é o primeiro plano, não o fundo
      lista.push(...camadas(e));
    }
    return compor(lista);
  }
  function desc(e) {
    const um = (n) => { let s = n.tagName.toLowerCase(); if (n.id) s += '#' + n.id;
      else if (typeof n.className === 'string' && n.className.trim()) s += '.' + n.className.trim().split(/\s+/).slice(0, 2).join('.'); return s; };
    let s = um(e), pai = e.parentElement;
    while (pai && !pai.id) pai = pai.parentElement;
    return pai && pai !== e ? '#' + pai.id + ' ' + s : s;
  }
  const visivel = (e) => { try { return e.checkVisibility({checkOpacity: true, checkVisibilityCSS: true}); } catch (x) { return true; } };
  const snap = (e) => { const c = getComputedStyle(e), b = {};
    for (const l of ['Top', 'Right', 'Bottom', 'Left']) b[l] = [c['border' + l + 'Color'], c['border' + l + 'Width'], c['border' + l + 'Style']];
    return {bg: c.backgroundColor, bordas: b, deco: c.textDecorationLine, cor: c.color, sombra: c.boxShadow}; };
  window.__vc = {snap, cor, razao, hex, sobre, opacidade, camadas, compor, fundoNoPonto, desc, visivel, lum, base};
  return true;
}"""

# Exceções declaradas pelo dono ao contorno de campo (WCAG 1.4.11 pede 3:1 do que IDENTIFICA o componente): id do campo -> referência.
# Hoje só o seletor de apuração do topo, sem caixa por decisão P34 (22/11/2026): identificam-no o texto e a seta. Em vez da borda, mede-se
# o texto (já medido como qualquer texto) e a seta, que o Chromium desenha na cor do texto.
EXCECOES_CAMPO = {'contexto-caso': 'P34'}
EXPLICACAO_EXCECAO = {'P34': 'Seletor de apuração do topo (select#contexto-caso) sem caixa, por decisão do dono (P34, 22/11/2026): pela WCAG 1.4.11 '
                             'o que precisa de 3:1 é o que identifica o componente, o texto e a seta. Mede-se o texto e a seta contra o fundo, não a borda.'}

# Mede todo texto visível e os campos. Devolve {itens, nao_medidos, isentos, nos}.
JS_TEXTO = r"""(excecoes = {}) => {
  const vc = window.__vc, itens = [], naoMedidos = [], porMotivo = {};
  let isentos = 0, nos = 0;
  const motivo = (m, e, t) => { porMotivo[m] = (porMotivo[m] || 0) + 1; if (naoMedidos.length < 400) naoMedidos.push({motivo: m, s: vc.desc(e), t: (t || '').slice(0, 50)}); };
  const SALTAR = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'OPTION', 'OPTGROUP', 'TEXTAREA', 'TITLE', 'HEAD']);
  const desativado = (e) => !!e.closest(':disabled, [aria-disabled="true"]');
  function medir(e, rect, txt, categoria, forcarCor) {
    if (!rect) return;
    const cs = getComputedStyle(e);
    const svg = e instanceof SVGElement;
    let c, alfa;
    if (forcarCor) { c = vc.cor(forcarCor); alfa = c ? c[3] : 0; }
    else if (svg) { const f = cs.fill; if (!f || f === 'none' || f.startsWith('url')) return motivo('preenchimento SVG indefinido', e, txt);
      c = vc.cor(f); alfa = c ? c[3] * parseFloat(cs.fillOpacity) : 0; }
    else { c = vc.cor(cs.webkitTextFillColor || cs.color); alfa = c ? c[3] : 0; }
    if (!c) return motivo('cor do texto não interpretada', e, txt);
    alfa *= vc.opacidade(e);
    if (alfa < 0.02) return motivo('texto transparente', e, txt);
    let x = rect.left + rect.width / 2, y = rect.top + rect.height / 2;
    if (x < 0 || y < 0 || x >= innerWidth || y >= innerHeight) {
      e.scrollIntoView({block: 'center', inline: 'center', behavior: 'instant'});
      return null;   // o chamador refaz a medida com o retângulo novo
    }
    const f = vc.fundoNoPonto(x, y, e, true);
    if (f.coberto) return motivo('coberto por outro elemento', e, txt);
    if (f.desconhecido) return motivo('fundo com imagem', e, txt);
    const px = parseFloat(cs.fontSize), peso = parseInt(cs.fontWeight, 10) || 400;
    const grande = px >= 24 || (px >= 18.66 && peso >= 700);
    let pior = 1e9, piorBg = null, piorFg = null;
    for (const bg of f.cand) {
      const fg = vc.sobre([c[0], c[1], c[2], alfa], bg);
      const r = vc.razao(fg, bg);
      if (r < pior) { pior = r; piorBg = bg; piorFg = fg; }
    }
    itens.push({cat: categoria, s: vc.desc(e), t: txt.slice(0, 60), fg: vc.hex(piorFg), bg: vc.hex(piorBg), r: pior,
                min: grande ? 3 : 4.5, grande, px, peso, grad: f.cand.length > 1, semFundo: f.semFundo, excecao: excecoes[e.id] || null});
    return true;
  }
  const raiz = document.body;
  const it = document.createTreeWalker(raiz, NodeFilter.SHOW_TEXT);
  const lista = [], vistos = new Set();
  for (let n = it.nextNode(); n; n = it.nextNode()) {
    const el = n.parentElement;
    if (!el || SALTAR.has(el.tagName) || !n.nodeValue.trim()) continue;
    if (el.closest('script,style,noscript,template,textarea,option,optgroup,title')) continue;
    if (!vc.visivel(el)) continue;
    const chave = el;   // um por elemento: o texto direto de um elemento tem uma cor só
    if (vistos.has(chave)) continue;
    vistos.add(chave); lista.push(n);
  }
  const retangulo = (n) => { const r = document.createRange(); r.selectNodeContents(n);
    return [...r.getClientRects()].find(q => q.width >= 1 && q.height >= 1) || null; };
  for (const n of lista) {
    const el = n.parentElement; nos++;
    let rect = retangulo(n);
    if (!rect) continue;   // não renderizado (recortado a zero)
    if (desativado(el)) { isentos++; continue; }
    let r = medir(el, rect, n.nodeValue.trim(), 'texto');
    if (r === null) { rect = retangulo(n); r = rect ? medir(el, rect, n.nodeValue.trim(), 'texto') : undefined; if (r === null) motivo('fora da área visível', el, n.nodeValue.trim()); }
  }
  // Campos: valor, placeholder e contorno.
  const TIPOS_SEM_TEXTO = new Set(['hidden', 'checkbox', 'radio', 'file', 'range', 'color', 'image', 'reset']);
  for (const e of document.querySelectorAll('input, textarea, select')) {
    if (e.tagName === 'INPUT' && TIPOS_SEM_TEXTO.has((e.type || '').toLowerCase())) continue;
    if (!vc.visivel(e)) continue;
    let rect = e.getBoundingClientRect();
    if (rect.width < 1 || rect.height < 1) continue;
    if (desativado(e)) { isentos++; continue; }
    const pronto = () => { rect = e.getBoundingClientRect(); return rect.left >= 0 && rect.top >= 0 && rect.right <= innerWidth && rect.bottom <= innerHeight; };
    if (!pronto()) { e.scrollIntoView({block: 'center', inline: 'center', behavior: 'instant'}); pronto(); }
    const tipoBotao = e.tagName === 'INPUT' && ['button', 'submit'].includes((e.type || '').toLowerCase());
    let rotulo = e.tagName === 'SELECT' ? (e.selectedOptions[0] ? e.selectedOptions[0].text : '') : (e.value || '');
    nos++;
    if (rotulo) medir(e, rect, rotulo, tipoBotao ? 'texto' : 'campo-texto');
    else if (e.placeholder) {
      const ph = getComputedStyle(e, '::placeholder');
      medir(e, rect, e.placeholder, 'placeholder', ph.color);
    }
    if (tipoBotao) continue;
    // Contorno do campo (WCAG 1.4.11): a borda ou o fundo do campo contra o que o cerca.
    const cs = getComputedStyle(e), lados = ['Top', 'Bottom', 'Left', 'Right'];
    if (excecoes[e.id]) {
      // Exceção declarada: sem caixa. Mede a seta (cor do texto, no ponto da seta) contra o fundo, em vez da borda.
      const ponto = vc.fundoNoPonto(Math.min(rect.right - 12, innerWidth - 1), rect.top + rect.height / 2, e, true);
      const cor = vc.cor(cs.color);
      if (ponto.coberto || ponto.desconhecido || !cor) { motivo('seta do seletor sem fundo medível', e, rotulo); continue; }
      let pior = 1e9, piorBg = null, piorFg = null;
      for (const bg of ponto.cand) { const fg = vc.sobre([cor[0], cor[1], cor[2], cor[3] * vc.opacidade(e)], bg), r = vc.razao(fg, bg);
        if (r < pior) { pior = r; piorBg = bg; piorFg = fg; } }
      itens.push({cat: 'seta', s: vc.desc(e), t: rotulo.slice(0, 60), fg: vc.hex(piorFg), bg: vc.hex(piorBg), r: pior, min: 3, grande: false,
                  px: parseFloat(cs.fontSize), peso: 400, excecao: excecoes[e.id], detalhe: 'seta do seletor, na cor do texto; sem caixa por ' + excecoes[e.id]});
      continue;
    }
    const lado = lados.find(l => cs['border' + l + 'Style'] !== 'none' && parseFloat(cs['border' + l + 'Width']) > 0);
    const cx = rect.left + rect.width / 2;
    const ptos = [[cx, rect.top - 3], [cx, rect.bottom + 3]].filter(([x, y]) => y >= 0 && y < innerHeight);
    const proprio = vc.fundoNoPonto(rect.left + rect.width / 2, rect.top + rect.height / 2, e, true);
    if (proprio.coberto || proprio.desconhecido || !ptos.length) { motivo('contorno de campo sem fundo medível', e, rotulo || e.placeholder || ''); continue; }
    let pior = 1e9, info = null;
    for (const [x, y] of ptos) {
      const v = vc.fundoNoPonto(x, y, null, false);
      if (v.desconhecido || !v.cand.length) continue;
      for (const vz of v.cand) for (const pr of proprio.cand) {
        const bordaCor = lado ? vc.cor(cs['border' + lado + 'Color']) : null;
        const borda = bordaCor ? vc.sobre([bordaCor[0], bordaCor[1], bordaCor[2], bordaCor[3] * vc.opacidade(e)], pr) : null;
        const rBorda = borda ? vc.razao(borda, vz) : 0, rFundo = vc.razao(pr, vz);
        const melhor = Math.max(rBorda, rFundo);
        if (melhor < pior) { pior = melhor; info = {fg: borda ? vc.hex(borda) : vc.hex(pr), bg: vc.hex(vz), borda: rBorda, fundo: rFundo}; }
      }
    }
    if (info) itens.push({cat: 'campo', s: vc.desc(e), t: (rotulo || e.placeholder || e.getAttribute('aria-label') || '').slice(0, 60),
                          fg: info.fg, bg: info.bg, r: pior, min: 3, grande: false, px: parseFloat(cs.fontSize), peso: 400,
                          detalhe: 'borda ' + info.borda.toFixed(2) + ' · fundo ' + info.fundo.toFixed(2)});
  }
  return {itens, nao_medidos: naoMedidos, por_motivo: porMotivo, isentos, nos};
}"""

# Mede o foco atual. Devolve também `adj` (fundos vizinhos) para o caminho sem contorno medido em Python.
JS_FOCO = r"""async () => {
  const vc = window.__vc, e = document.activeElement;
  if (!e || e === document.body || e === document.documentElement) return {corpo: true};
  vc.visto = vc.visto || new WeakSet();
  if (vc.visto.has(e)) return {repetido: true};
  vc.visto.add(e); vc.alvo = e;
  await Promise.race([Promise.all(document.getAnimations().map(a => a.finished.catch(() => 0))), new Promise(r => setTimeout(r, 600))]);
  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  const rect = e.getBoundingClientRect();
  const rot = (e.getAttribute('aria-label') || e.innerText || e.value || e.title || e.id || '').trim().replace(/\s+/g, ' ').slice(0, 50);
  const base = {cat: 'foco', s: vc.desc(e), t: rot};
  if (rect.width < 1 || rect.height < 1 || !vc.visivel(e)) return {...base, invisivel: true};
  if (e.closest(':disabled, [aria-disabled="true"]')) return {...base, isento: true};
  const cs = getComputedStyle(e), op = vc.opacidade(e);
  let ind = null;
  if (cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) > 0) {
    const c = vc.cor(cs.outlineColor);
    if (c && c[3] * op > 0.02) ind = {tipo: cs.outlineStyle === 'auto' ? 'anel padrão do navegador' : 'outline', cor: [c[0], c[1], c[2], c[3] * op],
                                       largura: parseFloat(cs.outlineWidth), desloc: parseFloat(cs.outlineOffset) || 0, padrao: cs.outlineStyle === 'auto'};
  }
  if (!ind && cs.boxShadow && cs.boxShadow !== 'none') {
    const partes = cs.boxShadow.split(/,(?![^(]*\))/).map(s => s.trim());
    for (const p of partes) {
      if (/inset/.test(p)) continue;
      const m = p.match(/(rgba?\([^)]*\)|color\([^)]*\))/); if (!m) continue;
      const nums = p.replace(m[1], '').match(/-?[\d.]+px/g) || [];
      const espalha = nums.length >= 4 ? parseFloat(nums[3]) : 0, desfoque = nums.length >= 3 ? parseFloat(nums[2]) : 0;
      const c = vc.cor(m[1]);
      if (c && c[3] > 0 && espalha > 0) { ind = {tipo: 'sombra', cor: [c[0], c[1], c[2], c[3] * op], largura: espalha, desloc: 0}; break; }
      if (c && c[3] > 0 && desfoque > 0 && !ind) ind = {tipo: 'sombra', cor: [c[0], c[1], c[2], c[3] * op], largura: desfoque / 2, desloc: 0};
    }
  }
  // fundos vizinhos
  const cx = rect.left + rect.width / 2, cy = rect.top + rect.height / 2;
  // O anel ocupa de `desloc` a `desloc + largura` para fora da borda. Inteiro para dentro (desloc + largura <= 0): só o fundo do
  // próprio elemento é vizinho dele. Senão, o que há logo depois da borda externa do anel.
  const dentroTodo = !!ind && ind.desloc + ind.largura <= 0;
  const d = ind ? Math.max(ind.desloc + ind.largura, 0) + 1 : 4;
  const pontos = dentroTodo ? [] : [[cx, rect.top - d], [cx, rect.bottom + d], [rect.left - d, cy], [rect.right + d, cy]]
    .filter(([x, y]) => x >= 0 && y >= 0 && x < innerWidth && y < innerHeight);
  const vizinhos = [];
  let semMedida = false;
  for (const [x, y] of pontos) {
    const f = vc.fundoNoPonto(x, y, null, false);
    if (f.desconhecido || !f.cand.length) { semMedida = true; continue; }
    vizinhos.push(...f.cand);
  }
  const proprio = (cx >= 0 && cy >= 0 && cx < innerWidth && cy < innerHeight) ? vc.fundoNoPonto(cx, cy, e, true) : {cand: []};
  const dentro = !!ind && ind.desloc < 0;
  const alvos = vizinhos.slice(0, 16).concat(dentro ? proprio.cand.slice(0, 8) : []);
  if (!alvos.length && proprio.cand.length) alvos.push(...proprio.cand.slice(0, 8));
  if (!ind) return {...base, semIndicador: true, snap: vc.snap(e), adj: vizinhos.slice(0, 8).map(vc.hex), proprio: proprio.cand.slice(0, 4).map(vc.hex),
                    semMedida, x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height)};
  if (!alvos.length) return {...base, tipo: ind.tipo, sem_fundo: true};
  let pior = 1e9, piorBg = null, piorFg = null;
  for (const bg of alvos) {
    const fg = vc.sobre(ind.cor, bg), r = vc.razao(fg, bg);
    if (r < pior) { pior = r; piorBg = bg; piorFg = fg; }
  }
  return {...base, tipo: ind.tipo, largura: ind.largura, desloc: ind.desloc, fg: vc.hex(piorFg), bg: vc.hex(piorBg), r: pior, min: 3,
          padrao: !!ind.padrao};
}"""

JS_SNAP_ALVO = r"""() => { const e = window.__vc.alvo; return e ? window.__vc.snap(e) : null; }"""
JS_FOCAR_ALVO = "() => { const e = window.__vc && window.__vc.alvo; if (e) { e.blur(); } return !!e; }"
JS_REFOCAR_ALVO = "() => { const e = window.__vc && window.__vc.alvo; if (e) { e.focus({focusVisible: true}); } return !!e; }"
JS_COR = "(s) => { const c = window.__vc.cor(s); return c ? [c[0], c[1], c[2], c[3]] : null; }"


def indicador_alternativo(item: dict, snap_foco: dict, snap_sem: dict | None, cor_em_hex) -> dict:
    """Foco sem contorno nem sombra: o que mudou entre focado e não focado (borda, fundo, sublinhado) e o contraste disso.
    `cor_em_hex(texto_css)` -> '#rrggbb' ou None (conversão feita no navegador)."""
    resultado = dict(item)
    resultado.pop('semIndicador', None)
    resultado['min'] = MINIMO_COMPONENTE
    if not snap_sem:
        resultado.update(falha_tipo='sem contorno de foco', r=0.0, fg='', bg='', tipo='nenhum')
        return resultado
    vizinhos = [parse_hex(h) for h in item.get('adj', [])] or [parse_hex(h) for h in item.get('proprio', [])]
    lados_borda = []   # lados em que a borda existe no foco e é diferente de sem foco
    for lado, (cor_f, larg_f, est_f) in snap_foco['bordas'].items():
        if est_f == 'none' or larg_f in ('0px', ''):
            continue
        if snap_sem['bordas'][lado] != [cor_f, larg_f, est_f]:
            lados_borda.append(cor_f)
    mudou_fundo = snap_foco['bg'] != snap_sem['bg']
    mudou_deco = snap_foco['deco'] != snap_sem['deco'] and 'underline' in snap_foco['deco']
    candidatos = []
    for css in dict.fromkeys(lados_borda):
        hexa = cor_em_hex(css)
        if hexa and vizinhos:
            pior = min(vizinhos, key=lambda v: razao(parse_hex(hexa), v))
            candidatos.append(('borda', hexa, razao(parse_hex(hexa), pior), pior))
    if mudou_fundo:
        novo, velho = cor_em_hex(snap_foco['bg']), cor_em_hex(snap_sem['bg'])
        if novo and velho:
            candidatos.append(('fundo', novo, razao(parse_hex(novo), parse_hex(velho)), parse_hex(velho)))
    if mudou_deco:
        candidatos.append(('sublinhado', '', 21.0, None))
    if not candidatos:
        resultado.update(falha_tipo='sem contorno de foco', r=0.0, fg='', bg='', tipo='nenhum')
        return resultado
    tipo, fg, r, bg = max(candidatos, key=lambda c: c[2])
    resultado.update(tipo=f'{tipo} (sem contorno)', fg=fg, bg='#%02x%02x%02x' % tuple(bg) if bg else '', r=r)
    return resultado


# ---------------------------------------------------------------- rodada

def medir_tela(pagina, nome: str, problemas: list, maximo_tab: int = 250) -> dict:
    pagina.evaluate(JS_PREPARO)
    pagina.evaluate('window.scrollTo(0, 0)')
    texto = pagina.evaluate(JS_TEXTO, EXCECOES_CAMPO)
    pagina.evaluate('window.scrollTo(0, 0)')
    pagina.evaluate("document.activeElement && document.activeElement.blur && document.activeElement.blur()")
    focos, invisiveis, isentos_foco, em_corpo = [], 0, 0, 0
    for _ in range(maximo_tab):
        pagina.keyboard.press('Tab')
        r = pagina.evaluate(JS_FOCO)
        if r.get('repetido'):
            break
        if r.get('corpo'):
            em_corpo += 1
            if focos and em_corpo >= 2:
                break
            continue
        if r.get('invisivel'):
            invisiveis += 1
            continue
        if r.get('isento'):
            isentos_foco += 1
            continue
        if r.get('semIndicador'):
            snap_foco = r['snap']
            pagina.evaluate(JS_FOCAR_ALVO)
            pagina.wait_for_timeout(450)
            snap_sem = pagina.evaluate(JS_SNAP_ALVO)
            pagina.evaluate(JS_REFOCAR_ALVO)
            pagina.wait_for_timeout(150)
            r = indicador_alternativo(r, snap_foco, snap_sem, lambda css: _hex_no_navegador(pagina, css))
        focos.append(r)
    else:
        problemas.append(f'{nome}: o percurso por Tab passou de {maximo_tab} paradas sem fechar o ciclo')
    return {'texto': texto, 'focos': focos, 'focos_invisiveis': invisiveis, 'focos_isentos': isentos_foco}


def _hex_no_navegador(pagina, css: str):
    c = pagina.evaluate(JS_COR, css)
    if not c:
        return None
    if c[3] < 0.999:   # translúcido: compõe sobre branco só para ter uma cor; casos assim são raros e ficam visíveis no relatório
        c = [round(c[i] * c[3] + 255 * (1 - c[3])) for i in range(3)]
    return '#%02x%02x%02x' % tuple(round(v) for v in c[:3])


def reprovado(item: dict) -> bool:
    if item.get('falha_tipo'):
        return True
    if item.get('sem_fundo'):
        return False
    return arredondar(item['r']) < item['min']


def medir_tudo(args) -> dict:
    import regressao_visual as rv
    from playwright.sync_api import Error as ErroPlaywright, sync_playwright

    telas = [t.strip() for t in args.telas.split(',')] if args.telas else list(rv.TELAS) + list(rv.VARIANTES) + [rv.TELA_ENTRAR]
    larguras = [int(w) for w in args.larguras.split(',')] if args.larguras else list(LARGURAS_PADRAO)
    temas = [t.strip() for t in args.temas.split(',')] if args.temas else list(rv.TEMAS)
    invalidas = [t for t in telas if t not in rv.TELAS and t not in rv.VARIANTES and t != rv.TELA_ENTRAR] \
        + [w for w in larguras if w not in rv.VIEWPORTS] + [t for t in temas if t not in rv.TEMAS]
    if invalidas:
        raise SystemExit(f'Seleção inválida: {invalidas}')
    resultados, problemas, externos = {}, [], []
    navegador_versao = ''
    with rv.Servidores(rv.python_do_servidor(args.python_servidor)) as servidores:
        permitidos = (servidores.origem_mesa, servidores.origem_entrar)

        def filtrar(rota):
            url = rota.request.url
            if url.startswith(permitidos) or url.startswith(('data:', 'blob:', 'about:')):
                rota.continue_()
            else:
                externos.append(url)
                rota.abort()

        def uma_tela(contexto, tela, largura, tema):
            nome = rv.nome_captura(tela, largura, tema)
            pagina = contexto.new_page()
            atividade = rv.AtividadeDeRede(pagina)
            try:
                url, seletor = rv.destino(servidores, tela)
                pagina.goto(url, wait_until='load')
                pagina.wait_for_selector(seletor, state='visible', timeout=30000)
                atividade.esperar_quieta(pagina)
                rv.esperar_pronta(pagina, atividade, nome, problemas)
                pagina.evaluate('document.fonts.ready.then(() => 0)')
                esperada = rv.VARIANTES[tela][0] if tela in rv.VARIANTES else tela
                if esperada != rv.TELA_ENTRAR:
                    ativa = pagina.evaluate("new URL(location.href).searchParams.get('area') || 'inicio'")
                    if ativa != esperada:
                        problemas.append(f'{nome}: a Mesa abriu a área {ativa!r}, não {esperada!r}')
                if tela in rv.VARIANTES:
                    aba = pagina.get_by_role('tab', name=rv.VARIANTES[tela][1], exact=True)
                    aba.click()
                    if aba.get_attribute('aria-selected') != 'true':
                        problemas.append(f'{nome}: a aba {rv.VARIANTES[tela][1]!r} não ficou selecionada')
                    rv.esperar_pronta(pagina, atividade, nome, problemas)
                pagina.mouse.move(0, 0)
                resultados[nome] = {'tela': tela, 'largura': largura, 'tema': tema, **medir_tela(pagina, nome, problemas)}
            finally:
                with contextlib.suppress(ErroPlaywright):
                    pagina.close()

        with sync_playwright() as pw:
            for largura in larguras:
                for tema in temas:
                    pendentes = list(telas)
                    tentativas = 0
                    while pendentes:
                        navegador = pw.chromium.launch(args=rv.ARGS_CHROMIUM)
                        navegador_versao = 'chromium ' + navegador.version
                        try:
                            contexto = navegador.new_context(
                                viewport={'width': largura, 'height': rv.VIEWPORTS[largura]}, device_scale_factor=1,
                                locale='pt-BR', timezone_id='UTC', color_scheme=rv.TEMAS[tema], reduced_motion='reduce',
                                service_workers='block', accept_downloads=False)
                            contexto.clock.set_fixed_time(rv.RELOGIO)
                            contexto.add_init_script(
                                f"try{{localStorage.setItem('{rv.CHAVE_TEMA}','{rv.TEMAS[tema]}');"
                                f"localStorage.setItem('{rv.CHAVE_IDIOMA}','pt');}}catch(e){{}}")
                            contexto.route('**/*', filtrar)
                            while pendentes:
                                tela = pendentes[0]
                                try:
                                    uma_tela(contexto, tela, largura, tema)
                                except ErroPlaywright as exc:
                                    if 'closed' in str(exc).lower() and tentativas < 3:
                                        tentativas += 1
                                        print(f'  (Chromium caiu em {tela}; reiniciando, tentativa {tentativas})', flush=True)
                                        break
                                    problemas.append(f'{rv.nome_captura(tela, largura, tema)}: {type(exc).__name__}: {str(exc)[:300]}')
                                except Exception as exc:   # noqa: BLE001 - qualquer falha de medida reprova a rodada
                                    problemas.append(f'{rv.nome_captura(tela, largura, tema)}: {type(exc).__name__}: {str(exc)[:300]}')
                                pendentes.pop(0)
                                nome = rv.nome_captura(tela, largura, tema)
                                if nome in resultados:
                                    r = resultados[nome]
                                    itens = r['texto']['itens'] + r['focos']
                                    print(f'  {nome}: {len(itens)} medidas, {sum(reprovado(i) for i in itens)} reprovadas', flush=True)
                        finally:
                            with contextlib.suppress(Exception):
                                navegador.close()
    if externos:
        problemas.append('pedidos a endereços externos (abortados): ' + ', '.join(sorted(set(externos))[:5]))
    return {'navegador': navegador_versao, 'resultados': resultados, 'problemas': problemas,
            'gerado_em_utc': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}


# ---------------------------------------------------------------- relatório

def agrupar(itens: list) -> list:
    """Funde medidas iguais (mesmo seletor, cores e razão) numa linha com contagem."""
    grupos = {}
    for i in itens:
        chave = (i['cat'], i['s'], i.get('fg'), i.get('bg'), round(i['r'], 2), i['min'], i.get('tipo'), i.get('falha_tipo'))
        if chave in grupos:
            grupos[chave]['n'] += 1
            if len(grupos[chave]['amostras']) < 3 and i['t'] not in grupos[chave]['amostras']:
                grupos[chave]['amostras'].append(i['t'])
        else:
            grupos[chave] = {**i, 'n': 1, 'amostras': [i['t']]}
    return sorted(grupos.values(), key=lambda g: (g['r'], g['s']))


def resumir(dados: dict) -> dict:
    por_tela, totais = {}, {'medidas': 0, 'reprovadas': 0, 'texto': 0, 'texto_reprovado': 0, 'foco': 0, 'foco_reprovado': 0,
                            'campo': 0, 'campo_reprovado': 0, 'isentos': 0, 'nao_medidos': 0}
    for nome, r in sorted(dados['resultados'].items()):
        itens = r['texto']['itens']
        excecoes_da_tela = [i for i in itens if i.get('excecao')]
        textos = [i for i in itens if i['cat'] in ('texto', 'campo-texto', 'placeholder')]
        campos = [i for i in itens if i['cat'] in ('campo', 'seta')]
        focos = r['focos']
        falhas = [i for i in itens + focos if reprovado(i)]
        nao = sum(r['texto']['por_motivo'].values())
        por_tela[nome] = {'textos': len(textos), 'textos_reprovados': sum(reprovado(i) for i in textos),
                          'campos': len(campos), 'campos_reprovados': sum(reprovado(i) for i in campos),
                          'focos': len(focos), 'focos_reprovados': sum(reprovado(i) for i in focos),
                          'excecoes': excecoes_da_tela, 'isentos': r['texto']['isentos'] + r['focos_isentos'], 'nao_medidos': nao, 'nao_medidos_detalhe': r['texto']['nao_medidos'],
                          'motivos': r['texto']['por_motivo'], 'falhas': agrupar(falhas)}
        totais['medidas'] += len(itens) + len(focos)
        totais['reprovadas'] += len(falhas)
        totais['texto'] += len(textos); totais['texto_reprovado'] += por_tela[nome]['textos_reprovados']
        totais['foco'] += len(focos); totais['foco_reprovado'] += por_tela[nome]['focos_reprovados']
        totais['campo'] += len(campos); totais['campo_reprovado'] += por_tela[nome]['campos_reprovados']
        totais['isentos'] += por_tela[nome]['isentos']
        totais['nao_medidos'] += nao
    return {'por_tela': por_tela, 'totais': totais}


def _linha_falha(g: dict) -> str:
    amostra = ' / '.join(a for a in g['amostras'] if a)
    if g['cat'] == 'foco':
        if g.get('falha_tipo'):
            return f"{g['s']} «{g['t']}»: {g['falha_tipo']}"
        return (f"{g['s']} «{g['t']}»: contorno {g.get('tipo')} {g.get('fg')} sobre {g.get('bg')} = {arredondar(g['r']):.2f}:1 "
                f"(mínimo {g['min']:g}:1)")
    extra = f" · {g['detalhe']}" if g.get('detalhe') else ''
    tam = 'grande' if g.get('grande') else 'comum'
    esp = f" ({g['px']:g}px, peso {g['peso']}, texto {tam})" if g['cat'] != 'campo' else ''
    n = f" ×{g['n']}" if g['n'] > 1 else ''
    return (f"{g['s']}{n} «{amostra}»: {g['cat']} {g.get('fg')} sobre {g.get('bg')} = {arredondar(g['r']):.2f}:1 "
            f"(mínimo {g['min']:g}:1){esp}{extra}")


def escrever_relatorio(dados: dict, pasta: Path) -> Path:
    resumo = resumir(dados)
    t = resumo['totais']
    pasta.mkdir(parents=True, exist_ok=True)
    linhas = ['# Contraste WCAG AA, linha de base da Onda 3', '',
              f"Gerado em {dados['gerado_em_utc']} · {dados['navegador']} · {len(dados['resultados'])} telas.", '',
              f"**{t['reprovadas']} reprovações em {t['medidas']} medidas** — texto {t['texto_reprovado']}/{t['texto']}, "
              f"foco {t['foco_reprovado']}/{t['foco']}, campo {t['campo_reprovado']}/{t['campo']}; "
              f"{t['isentos']} controles desativados isentos; {t['nao_medidos']} não medidos (imagem de fundo, coberto ou fora da área).", '',
              'Limites: 4,5:1 texto comum; 3:1 texto grande (≥ 24 px, ou ≥ 18,66 px em negrito), contorno de foco e contorno de campo.', '']
    if dados['problemas']:
        linhas += ['## Problemas da rodada', ''] + [f'- {p}' for p in dados['problemas']] + ['']
    linhas += ['## Resumo por tela', '', '| Tela | Texto | Foco | Campo | Isentos | Não medidos |', '|---|---|---|---|---|---|']
    for nome, r in resumo['por_tela'].items():
        linhas.append(f"| {nome} | {r['textos_reprovados']}/{r['textos']} | {r['focos_reprovados']}/{r['focos']} | "
                      f"{r['campos_reprovados']}/{r['campos']} | {r['isentos']} | {r['nao_medidos']} |")
    linhas += ['', '(reprovadas/medidas em cada coluna)', '', '## Reprovações tela por tela', '']
    algum = False
    for nome, r in resumo['por_tela'].items():
        if not r['falhas']:
            continue
        algum = True
        linhas += [f"### {nome}", ''] + [f'- {_linha_falha(g)}' for g in r['falhas']] + ['']
    if not algum:
        linhas += ['Nenhuma reprovação.', '']
    decl = {}
    for nome, r in resumo['por_tela'].items():
        for i in r['excecoes']:
            d = decl.setdefault(i['excecao'], {'medidas': 0, 'reprovadas': 0, 'piores': {}})
            d['medidas'] += 1
            d['reprovadas'] += reprovado(i)
            chave = i['cat']
            if chave not in d['piores'] or i['r'] < d['piores'][chave][0]:
                d['piores'][chave] = (i['r'], nome, i.get('fg'), i.get('bg'), i['min'])
    if decl:
        linhas += ['## Exceções declaradas', '']
        for ref, d in sorted(decl.items()):
            linhas.append(f"- **{ref}**: {EXPLICACAO_EXCECAO.get(ref, '')} {d['medidas']} medidas, {d['reprovadas']} reprovadas.")
            for cat, (r, nome, fg, bg, minimo) in sorted(d['piores'].items()):
                rotulo = 'seta' if cat == 'seta' else 'texto'
                linhas.append(f"  - pior {rotulo}: {arredondar(r):.2f}:1 ({fg} sobre {bg}, mínimo {minimo:g}:1) em {nome}")
        linhas.append('')
    nao = [(n, r['motivos']) for n, r in resumo['por_tela'].items() if r['motivos']]
    if nao:
        linhas += ['## Não medidos', '', 'Texto que não tem como ser medido pelo fundo (o que não entra nas reprovações acima):', '']
        linhas += [f"- {n}: " + ', '.join(f'{m} ({c})' for m, c in sorted(mot.items())) for n, mot in nao] + ['']
        unicos = {}
        for r in resumo['por_tela'].values():
            for d in r['nao_medidos_detalhe']:
                unicos.setdefault((d['motivo'], d['s'], d['t']), 0)
                unicos[(d['motivo'], d['s'], d['t'])] += 1
        linhas += ['Quais são (únicos em todas as telas, com o número de telas em que aparecem):', '']
        linhas += [f"- {m}: {s} «{x}» ×{c}" for (m, s, x), c in sorted(unicos.items())][:60] + ['']
    md = pasta / 'relatorio.md'
    md.write_text('\n'.join(linhas) + '\n', encoding='utf-8')
    (pasta / 'relatorio.json').write_text(json.dumps({**{k: v for k, v in dados.items() if k != 'resultados'}, 'resumo': resumo},
                                                       ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    corpo = ''.join(f'<h3>{html.escape(n)}</h3><ul>' + ''.join(f'<li>{html.escape(_linha_falha(g))}</li>' for g in r['falhas']) + '</ul>'
                    for n, r in resumo['por_tela'].items() if r['falhas']) or '<p>Nenhuma reprovação.</p>'
    (pasta / 'relatorio.html').write_text(
        '<!doctype html><meta charset="utf-8"><title>Contraste WCAG</title><body style="font:14px sans-serif;max-width:60rem;margin:2rem auto">'
        f"<h1>Contraste WCAG AA</h1><p><b>{t['reprovadas']}</b> reprovações em {t['medidas']} medidas.</p>{corpo}</body>", encoding='utf-8')
    return md


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('comando', choices=('medir',))
    parser.add_argument('--telas', help='lista separada por vírgula (padrão: as 14 da linha de base, sem os focos)')
    parser.add_argument('--larguras', help='ex.: 375,1440 (padrão)')
    parser.add_argument('--temas', help='claro,escuro (padrão: ambos)')
    parser.add_argument('--python-servidor', help='Python do projeto (padrão: .venv do projeto)')
    parser.add_argument('--relatorio', help='pasta do relatório (padrão: tmp/contraste_wcag)')
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding='utf-8')
    pasta = Path(args.relatorio) if args.relatorio else RAIZ / 'tmp' / 'contraste_wcag'
    if pasta.exists():
        shutil.rmtree(pasta)
    dados = medir_tudo(args)
    md = escrever_relatorio(dados, pasta)
    t = resumir(dados)['totais']
    print(f"{t['reprovadas']} reprovações em {t['medidas']} medidas (texto {t['texto_reprovado']}/{t['texto']}, foco "
          f"{t['foco_reprovado']}/{t['foco']}, campo {t['campo_reprovado']}/{t['campo']}). Relatório: {md}")
    if dados['problemas']:
        print('Rodada com problemas:\n - ' + '\n - '.join(dados['problemas']), file=sys.stderr)
        return 2
    return 1 if t['reprovadas'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
