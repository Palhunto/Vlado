'use strict';
// The AI's support verdict must never read as a human check: prefix, shape and fill differ,
// and both themes keep text at 4.5:1 and shapes at 3:1.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {criarMesa} = require('./dom_minimo.cjs');

const css = fs.readFileSync(path.join(__dirname, '..', 'interface', 'style.css'), 'utf8');

function mesa(idioma = 'pt') {
  return criarMesa({idioma, armazenamento: {'vlado-idioma': idioma}, scripts: ['i18n_en.js', 'i18n.js', 'leitura.js', 'app.js']});
}

test('selo da IA traz o prefixo “IA ·”; conferência humana traz ✓ em texto', () => {
  const {avaliar} = mesa();
  const ia = avaliar('supportBadge')({suporte: 'sustentado'});
  assert.equal(ia.textContent, 'IA · sustentado');
  assert.ok(ia.classList.contains('ai-support'));
  assert.equal(ia.title, 'Suporte documental avaliado pela IA');
  const humano = avaliar('humanReviewBadge')({revisao_humana: {estado: 'conferida_no_original'}});
  assert.equal(humano.textContent, '✓ Conferida no original');
  assert.ok(humano.classList.contains('human-conferida_no_original'));
  const pendente = avaliar('humanReviewBadge')({});
  assert.equal(pendente.textContent, 'Pendente');
  assert.ok(pendente.classList.contains('human-pendente'));
});

test('em inglês os selos dizem “AI ·” e “Checked against the original”', () => {
  const {avaliar, janela} = mesa('en');
  const ia = avaliar('supportBadge')({suporte: 'nao_sustentado'});
  const humano = avaliar('humanReviewBadge')({revisao_humana: {estado: 'conferida_no_original'}});
  const caixa = janela.document.createElement('div'); caixa.append(ia, humano); janela.document.body.append(caixa);
  janela.I18N.aplicar(caixa);
  assert.equal(ia.textContent, 'AI · not supported');
  assert.equal(humano.textContent, '✓ Checked against the original');
});

test('folha de estilos separa forma: pílula contornada (IA), preenchido (conferida), tracejado (pendente)', () => {
  for (const regra of [/\.support-badge\.ai-support\{[^}]*background:transparent[^}]*border:1px solid var\(--muted\)[^}]*border-radius:999px/,
    /\.human-review-badge\.human-conferida_no_original\{[^}]*background:var\(--green\)[^}]*color:var\(--theme-on-primary/,
    /\.human-review-badge\.human-pendente\{[^}]*border:1px dashed var\(--muted\)/]) assert.ok(regra.test(css), `regra ausente: ${regra}`);
});

// WCAG relative luminance contrast.
const canal = c => { c /= 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; };
const luminancia = hex => { const n = parseInt(hex.slice(1, 7), 16); return 0.2126 * canal(n >> 16) + 0.7152 * canal((n >> 8) & 255) + 0.0722 * canal(n & 255); };
const contraste = (a, b) => { const [x, y] = [luminancia(a), luminancia(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };

function temas() {
  // Theme tokens live in tokens.css (primitives, then one semantic set per theme); aliases resolve to the primitive.
  const {claro, escuro, resolver} = require('./tokens_tema.cjs');
  return {claro: nome => resolver(claro, `--${nome}`), escuro: nome => resolver(escuro, `--${nome}`)};
}

test('selos mantêm contraste nos dois temas', () => {
  const pares = [
    ['texto IA sobre cartão', 'ink', 'white', 4.5], ['texto IA sobre item ativo', 'ink', 'theme-active', 4.5],
    ['contorno IA', 'muted', 'white', 3], ['texto IA com ressalva', 'warning', 'white', 4.5],
    ['texto pendente', 'muted', 'white', 4.5], ['tracejado pendente', 'muted', 'white', 3],
    ['texto conferida', 'theme-on-primary', 'green', 4.5], ['preenchimento conferida', 'green', 'white', 3],
    ['precisa de ajuste', 'warning', 'warning-bg', 4.5], ['sem suporte', 'theme-danger', 'theme-danger-bg', 4.5],
  ];
  for (const [nome, tema] of Object.entries(temas())) {
    for (const [rotulo, frente, fundo, minimo] of pares) {
      const razao = contraste(tema(frente), tema(fundo));
      assert.ok(razao >= minimo, `${nome}: ${rotulo} ${tema(frente)} sobre ${tema(fundo)} = ${razao.toFixed(2)} < ${minimo}`);
    }
  }
});
