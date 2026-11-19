'use strict';
// Reads interface/tokens.css for the style contract tests: rule blocks, custom properties, the
// light and dark token tables and the var() chain down to the primitive value. No tests here.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const raiz = path.join(__dirname, '..', 'interface');
const ler = nome => fs.readFileSync(path.join(raiz, nome), 'utf8');
const semComentarios = texto => texto.replace(/\/\*[\s\S]*?\*\//g, '');
const tokens = ler('tokens.css');

// WCAG relative luminance contrast (alpha ignored: only opaque colours are compared).
const canal = c => { c /= 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; };
const luminancia = hex => { const n = parseInt(hex.slice(1, 7), 16); return 0.2126 * canal(n >> 16) + 0.7152 * canal((n >> 8) & 255) + 0.0722 * canal(n & 255); };
const contraste = (a, b) => { const [x, y] = [luminancia(a), luminancia(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };

// Innermost rule blocks, comments removed: {seletor, corpo}.
const blocos = texto => [...semComentarios(texto).matchAll(/([^{}]+)\{([^{}]*)\}/g)].map(m => ({seletor: m[1].trim(), corpo: m[2]}));
const propriedades = corpo => [...corpo.matchAll(/(--[\w-]+)\s*:\s*([^;]+)/g)].map(m => [m[1], m[2].trim()]);
// Declarations of every block opened by exactly this selector, later blocks winning.
function declaracoes(seletor, texto = tokens) {
  return Object.fromEntries(blocos(texto).filter(b => b.seletor === seletor).flatMap(b => propriedades(b.corpo)));
}
const claro = declaracoes(':root');
const escuro = {...claro, ...declaracoes(':root[data-theme=dark]')};
// Follows var() aliases down to the primitive value.
function resolver(tema, nome, visitados = new Set()) {
  const valor = tema[nome];
  assert.ok(valor !== undefined, `${nome} sem definição`);
  assert.ok(!visitados.has(nome), `${nome}: referência circular`);
  visitados.add(nome);
  const apelido = /^var\((--[\w-]+)\)$/.exec(valor);
  return apelido ? resolver(tema, apelido[1], visitados) : valor;
}
// A colour by semantic short name ("muted" means --theme-muted) or by full name ("--white").
const cor = (tema, nome) => {
  const valor = resolver(tema, nome.startsWith('--') ? nome : `--theme-${nome}`);
  assert.match(String(valor), /^#[0-9a-f]{6}([0-9a-f]{2})?$/i, `${nome} precisa resolver para uma cor`);
  return valor;
};

module.exports = {raiz, ler, semComentarios, tokens, blocos, propriedades, declaracoes, claro, escuro, resolver, cor, contraste};
