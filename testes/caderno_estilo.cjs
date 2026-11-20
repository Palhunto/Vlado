'use strict';
// interface/caderno.css: the Caderno's own sheet. It loads after style.css, every rule stays inside
// the Caderno (so the checkbox fix cannot leak into application forms), colours come only from the
// theme tokens and text sizes only from the type scale.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const raiz = path.join(__dirname, '..', 'interface');
const css = fs.readFileSync(path.join(raiz, 'caderno.css'), 'utf8').replace(/\/\*[\s\S]*?\*\//g, '');
const html = fs.readFileSync(path.join(raiz, 'index.html'), 'utf8');

// Selectors of every style rule, including those nested in @media/@supports.
function seletores(texto) {
  const lista = [];
  let i = 0;
  while (i < texto.length) {
    const abre = texto.indexOf('{', i);
    if (abre < 0) break;
    const cabeca = texto.slice(i, abre).trim();
    if (cabeca.startsWith('@')) { i = abre + 1; continue; }
    const fecha = texto.indexOf('}', abre);
    // Split on top-level commas only (not inside :is()/:has()).
    let nivel = 0, parte = '';
    for (const c of cabeca + ',') {
      if (c === ',' && !nivel) { if (parte.trim()) lista.push(parte.trim()); parte = ''; continue; }
      if (c === '(') nivel++; if (c === ')') nivel--;
      parte += c;
    }
    i = fecha + 1;
    while (texto[i] === '}' || /\s/.test(texto[i] || '')) i++;
  }
  return lista;
}

test('caderno.css é carregado pelo index.html depois de style.css', () => {
  const estilo = html.indexOf('href="/style.css"'), caderno = html.indexOf('href="/caderno.css"');
  assert.ok(caderno > 0, 'link para /caderno.css');
  assert.ok(caderno > estilo, 'depois de style.css');
});

test('toda regra fica restrita ao Caderno', () => {
  const fora = seletores(css).filter(s => !/^(:root(\[data-theme=dark\])?\s+)?#area-apuracao\b/.test(s));
  assert.deepEqual(fora, []);
});

test('cores só por tokens e tamanhos de texto só pela escala', () => {
  assert.deepEqual(css.match(/#[0-9a-f]{3,8}\b/gi) || [], [], 'hexadecimal solto');
  assert.deepEqual(css.match(/rgba?\(|hsla?\(/gi) || [], [], 'cor literal');
  assert.deepEqual(css.match(/var\(--theme-[\w-]+\s*,/g) || [], [], 'reserva em var()');
  const fixos = css.match(/font(?:-size)?\s*:[^;}]*?\d+(px|rem|pt)[^;}]*/g) || [];
  assert.deepEqual(fixos, [], 'tamanho de texto fora da escala');
});

test('checkbox da lista de tarefas: alvo de 44 px e sem herdar largura de campo', () => {
  const regra = /#area-apuracao[^{]*\.vditor-task[^{]*input[^{]*\{([^}]*)\}/.exec(css);
  assert.ok(regra, 'regra para a caixa das tarefas');
  assert.match(regra[1], /width:\s*44px/);
  assert.match(regra[1], /height:\s*44px/);
  assert.match(regra[1], /min-height:\s*0/);
});
