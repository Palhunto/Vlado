'use strict';
// The AI's support verdict must never read as a human check: prefix, shape and fill differ,
// and both themes keep text at 4.5:1 and shapes at 3:1.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {criarMesa} = require('./dom_minimo.cjs');
const {blocos} = require('./tokens_tema.cjs');

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

// Forma do selo (docs/design/componentes.md#selo): o veredito da IA é pílula sem fundo e com borda TRACEJADA;
// os selos humanos têm fundo e borda contínua, com sinal.
test('folha de estilos separa forma: veredito da IA tracejado, conferência humana com fundo e borda contínua', () => {
  for (const regra of [/\.support-badge\.ai-support\{[^}]*background:transparent[^}]*border:1px dashed var\(--muted\)[^}]*border-radius:(?:999px|var\(--raio-pilula\))/,
    /\.human-review-badge\.human-conferida_no_original\{[^}]*background:var\(--theme-soft\)[^}]*color:var\(--theme-accent\)[^}]*border-color:var\(--theme-accent-line\)/,
    /\.human-review-badge\.human-pendente\{[^}]*background:var\(--white\)[^}]*border-color:var\(--theme-input-line\)/]) assert.ok(regra.test(css), `regra ausente: ${regra}`);
  // Os dois sentidos travados, em todas as regras do seletor (variações, estados e media queries): humano nunca tracejado, IA nunca contínua.
  const humanos = blocos(css).filter(r => /human-(?:review-badge|pendente|conferida_no_original|precisa_de_ajuste|sem_suporte_suficiente)/.test(r.seletor));
  assert.ok(humanos.length >= 4, 'regras dos selos humanos lidas');
  for (const r of humanos) assert.doesNotMatch(r.corpo, /dashed/, `selo humano nunca tracejado: ${r.seletor}`);
  const ia = blocos(css).filter(r => /ai-support/.test(r.seletor) && !/badge-origin/.test(r.seletor));
  assert.ok(ia.some(r => /border:\s*1px dashed/.test(r.corpo)), 'o veredito da IA exige borda tracejada');
  for (const r of ia) assert.doesNotMatch(r.corpo, /border:\s*1px solid/, `veredito da IA nunca com borda contínua: ${r.seletor}`);
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
    ['texto pendente', 'theme-text', 'white', 4.5], ['borda pendente', 'theme-input-line', 'white', 3],
    ['texto conferida', 'theme-accent', 'theme-soft', 4.5],
    ['precisa de ajuste', 'warning', 'warning-bg', 4.5], ['sem suporte', 'theme-danger', 'theme-danger-bg', 4.5],
  ];
  for (const [nome, tema] of Object.entries(temas())) {
    for (const [rotulo, frente, fundo, minimo] of pares) {
      const razao = contraste(tema(frente), tema(fundo));
      assert.ok(razao >= minimo, `${nome}: ${rotulo} ${tema(frente)} sobre ${tema(fundo)} = ${razao.toFixed(2)} < ${minimo}`);
    }
  }
});
