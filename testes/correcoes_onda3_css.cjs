'use strict';
// R1 e R2 da pré-entrega do Design (docs/design/aprovacao/onda3/pre-entrega.md). A prova visual é a medida no Chromium (cartão de achado em 1440 e 1024 nos dois
// temas, e a cor do botão desabilitado do Caderno); aqui ficam as regras que a garantem, para ninguém tirá-las sem ver a captura.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const css = nome => fs.readFileSync(path.join(__dirname, '..', 'interface', nome), 'utf8');

test('R1: o cartão de achado não encolhe na coluna com altura máxima e rolagem (o pé com o "Conferir" cresce com o conteúdo)', () => {
  const estilo = css('style.css');
  assert.ok(estilo.includes('.findings-list>.finding-choice{flex:none}'));
  assert.ok(estilo.includes('.finding-choice .human-review-actions button{min-height:44px;padding:0 var(--espaco-4)}'), 'o botão secundário do desenho: 44 de altura, 0 16');
  const lista = /@media \(min-width:1024px\) \{\s*\.findings-list\{[^}]*max-height:[^}]*overflow-y:auto/.exec(estilo);
  assert.ok(lista, 'a coluna com altura máxima e rolagem continua (é ela que fazia o cartão encolher)');
});

test('R2: o desabilitado tem o texto do token --theme-disabled-text, mais apagado que o muted no escuro e igual a ele no claro', () => {
  const tokens = css('tokens.css'), estilo = css('style.css');
  const claro = /--theme-muted:var\(--vlado-tinta-600\);--theme-disabled-text:var\(--vlado-tinta-600\)/.test(tokens);
  const escuro = /--theme-muted:var\(--vlado-tinta-300\);--theme-disabled-text:var\(--vlado-tinta-500\)/.test(tokens);
  assert.ok(claro && escuro, 'o token existe nos dois temas');
  assert.ok(/button:disabled,button:disabled:hover\{background:var\(--theme-sidebar\);border-color:var\(--line\);color:var\(--theme-disabled-text\)/.test(estilo));
});

test('AA: o painel de busca e substituição do Vditor tem o mesmo anel da barra (botões e campos)', () => {
  const estilo = css('style.css');
  assert.ok(estilo.includes('#apuracao-vditor :is(.vditor-toolbar,.vditor-panel) :is(button,.vditor-tooltipped):focus-visible,#apuracao-vditor .vditor-panel input:focus-visible{outline:var(--foco-largura) solid var(--theme-focus);outline-offset:0}'));
});

test('B1 do Traço (#segundo-fator): o código de reserva nunca quebra; a grade só tem duas colunas quando cada uma cabe um código inteiro', () => {
  const estilo = css('componentes_o3.css');
  assert.ok(estilo.includes('.fator-codigo{white-space:nowrap;'), 'cada código em uma linha');
  assert.ok(estilo.includes('grid-template-columns:repeat(auto-fit,minmax(min(100%,15rem),1fr))'), 'uma coluna num cartão estreito, como o da pendência (440 px)');
});

test('F1 da Coruja: a linha do estado da chave tem altura reservada, para o painel Conexão e opções não se mexer quando o texto chega', () => {
  assert.ok(css('style.css').includes('.ia-config #ia-chave-estado{min-height:1.65em}'));
});
