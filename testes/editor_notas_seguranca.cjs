'use strict';
// S6 (fase 09): o editor de notas é o único ponto com innerHTML montado a partir de texto do usuário.
// O Vditor inteiro não carrega no DOM mínimo dos testes (ele precisa de um parser de HTML real),
// então o teste exercita a mesma limpeza que o editor usa: o Lute do próprio Vditor, com
// sanitize ligado como em interface/editor_notas.js, sobre Markdown com <script>, onerror e
// javascript:. Confere também que a CSP da Mesa barra o que a limpeza deixa passar (iframe e
// imagem externos) e que nenhum script embutido roda. Sem navegador, rede ou modelo.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const raiz = path.resolve(__dirname, '..');
const lido = relativo => fs.readFileSync(path.join(raiz, relativo), 'utf8');

function lute() {
  const ctx = {console, setTimeout, clearTimeout, TextEncoder, TextDecoder, Uint8Array, performance, executou: false};
  ctx.window = ctx; ctx.self = ctx; ctx.globalThis = ctx;
  ctx.alert = () => { ctx.executou = true; };
  vm.createContext(ctx);
  vm.runInContext(lido('interface/vendor/vditor/dist/js/lute/lute.min.js'), ctx);
  const motor = ctx.Lute.New();
  motor.SetSanitize(true);
  return {motor, ctx};
}

const ATAQUES = [
  '<script>alert(1)</script>',
  '<img src=x onerror=alert(1)>',
  '<svg onload=alert(1)>',
  '<a href="javascript:alert(1)">link</a>',
  '[link](javascript:alert(1))',
  '<p onclick="alert(1)">clique</p>',
  'Texto <b onmouseover=alert(1)>negrito</b> **e mais**',
];

test('o editor liga a limpeza do Markdown e não carrega pré-visualização de mídia', () => {
  const fonte = lido('interface/editor_notas.js');
  assert.match(fonte, /markdown:\{sanitize:true/);
  assert.match(fonte, /render:\{media:\{enable:false\}\}/);
  assert.match(fonte, /image:\{isPreview:false\}/);
});

test('script, atributos on* e javascript: saem do HTML gerado nas duas vistas do editor', () => {
  const {motor, ctx} = lute();
  for (const md of ATAQUES) {
    for (const [vista, html] of [['previa', motor.Md2HTML(md)], ['visual', motor.Md2VditorDOM(md)]]) {
      // Na vista visual o HTML bruto aparece como código escapado (&lt;script&gt;), nunca como marcação viva.
      const vivo = html.replace(/<code[^>]*>[\s\S]*?<\/code>/g, '');
      assert.doesNotMatch(vivo, /<script/i, `${vista}: ${md}`);
      assert.doesNotMatch(vivo, /\son[a-z]+\s*=/i, `${vista}: ${md}`);
      assert.doesNotMatch(vivo, /javascript:/i, `${vista}: ${md}`);
    }
  }
  assert.equal(ctx.executou, false, 'nenhum script do texto rodou ao gerar o HTML');
});

test('o texto comum continua formatado depois da limpeza', () => {
  const {motor} = lute();
  assert.equal(motor.Md2HTML('**negrito** e [link](https://exemplo.org)').trim(),
               '<p><strong>negrito</strong> e <a href="https://exemplo.org">link</a></p>');
});

// O Lute que o editor usa de fato: editor_notas.js carregado no mesmo contexto embrulha Lute.New.
function luteDoEditor() {
  const {ctx} = lute();
  vm.runInContext(lido('interface/editor_notas.js'), ctx);
  ctx.protegerLuteGlobal();
  ctx.protegerLuteGlobal();  // repetir não embrulha duas vezes
  const motor = ctx.Lute.New();
  motor.SetSanitize(true);
  return {motor, ctx};
}

const EMBUTIDOS = [
  '<iframe src="/api/integracao"></iframe>',
  '<iframe src="https://externo.example"></iframe>',
  '<iframe srcdoc="<b>x</b>"></iframe>',
  '<object data="/vendor/x.pdf"></object>',
  '<embed src="/vendor/x.swf">',
  'Antes <IFRAME SRC=/ width=1></IFRAME> depois',
];
const METODOS = ['Md2HTML', 'Md2VditorDOM', 'Md2VditorIRDOM', 'Md2VditorSVDOM'];

test('iframe, object e embed somem de todo HTML do editor, inclusive com endereço da própria Mesa', () => {
  const {motor: cru} = lute();
  assert.match(cru.Md2HTML('<iframe src="/api/integracao"></iframe>'), /<iframe/, 'sem o editor, o Lute mantém o iframe');
  const {motor} = luteDoEditor();
  for (const md of EMBUTIDOS) {
    for (const metodo of METODOS) {
      const vivo = motor[metodo](md).replace(/<code[^>]*>[\s\S]*?<\/code>/g, '');
      assert.doesNotMatch(vivo, /<\/?(?:iframe|object|embed)\b/i, `${metodo}: ${md}`);
    }
  }
  assert.match(motor.Md2HTML('Antes <iframe src="/"></iframe> depois'), /Antes\s+depois/);
  assert.equal(motor.Md2HTML('**negrito**').trim(), '<p><strong>negrito</strong></p>');
});

test('a etapa transform do editor também retira os embutidos', () => {
  const {ctx} = luteDoEditor();
  assert.equal(ctx.semEmbutidos('<p>a</p><iframe src="/"></iframe><object data="/x"></object><embed src="/y">'), '<p>a</p>');
  assert.equal(ctx.semEmbutidos('&lt;iframe src="/"&gt;'), '&lt;iframe src="/"&gt;', 'texto escapado continua texto');
  assert.match(lido('interface/editor_notas.js'), /return window\.semEmbutidos\(template\.innerHTML\)/);
  assert.match(lido('interface/editor_notas.js'), /protegerLuteGlobal\(\);\s*this\.instance=new Vditor/);
});

test('a CSP da Mesa barra o que escapar da limpeza: iframe e imagem externos, script embutido', () => {
  const csp = lido('scripts/interface_pesquisa.py').match(/'Content-Security-Policy', "([^"]+)"/)[1];
  const diretivas = Object.fromEntries(csp.split(';').map(d => d.trim().split(/\s+/)).map(([nome, ...v]) => [nome, v]));
  assert.deepEqual(diretivas['script-src'], ["'self'"], 'sem unsafe-inline: atributos on* e <script> embutido não rodam');
  assert.deepEqual(diretivas['frame-src'], ["'self'", 'blob:'], 'iframe de outra origem é bloqueado');
  assert.deepEqual(diretivas['img-src'], ["'self'", 'blob:'], 'imagem de outra origem não é buscada');
  assert.deepEqual(diretivas['object-src'], ["'none'"]);
  assert.deepEqual(diretivas['base-uri'], ["'none'"]);
});
