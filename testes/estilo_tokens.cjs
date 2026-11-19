'use strict';
// Design system contracts that need no browser (docs/design/design-system.md). Colours live only in
// interface/tokens.css, in three layers: primitives (--vlado-*), semantic (--theme-* and the short
// names, one set per theme) and components. Rules never use primitives or colour literals; text
// pairs reach 4.5:1 and control borders 3:1 (WCAG AA) in both themes; text sizes come from one scale.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {raiz, ler, semComentarios, tokens, blocos, propriedades, claro, escuro, cor, contraste} = require('./tokens_tema.cjs');

const css = ler('style.css');
// Sheets whose rules paint the Mesa: none may hold a colour value of its own.
const FOLHAS = ['style.css', 'caderno.css', 'entrar.css'];

test('tokens.css é carregado antes das folhas da Mesa e da página de entrada', () => {
  for (const pagina of ['index.html', 'entrar.html']) {
    const html = ler(pagina), base = html.indexOf('href="/tokens.css"'), estilo = html.indexOf('href="/style.css"');
    assert.ok(base > 0, `${pagina}: link para /tokens.css`);
    assert.ok(base < estilo, `${pagina}: tokens.css antes de style.css`);
  }
});

test('três camadas: primitivos com valor, semânticos e componentes só por referência', () => {
  const definidos = blocos(tokens).flatMap(b => propriedades(b.corpo).map(([nome, valor]) => ({seletor: b.seletor, nome, valor})));
  const primitivos = definidos.filter(d => d.nome.startsWith('--vlado-'));
  assert.ok(primitivos.length >= 40, `${primitivos.length} primitivos`);
  assert.deepEqual([...new Set(primitivos.map(d => d.seletor))], [':root'], 'primitivos não mudam por tema');
  for (const d of definidos.filter(d => !d.nome.startsWith('--vlado-'))) {
    assert.doesNotMatch(d.valor, /#[0-9a-f]{3,8}\b|rgba?\(|hsla?\(/i, `${d.nome} deve citar um primitivo, não um valor`);
  }
});

test('nenhuma regra usa cor literal nem primitivo: só tokens semânticos ou de componente', () => {
  // Colour tokens are always defined: a fallback would hide a missing one. Layout measures
  // set at run time (--mesa-header-height) keep theirs.
  const cores = Object.keys(escuro).filter(n => !/^--(text|espaco|raio|mesa)-/.test(n)).map(n => n.slice(2)).join('|');
  for (const nome of FOLHAS) {
    const texto = semComentarios(ler(nome));
    assert.deepEqual(texto.match(/#[0-9a-f]{3,8}\b/gi) || [], [], `${nome}: hexadecimal solto`);
    assert.deepEqual(texto.match(/rgba?\(|hsla?\(/gi) || [], [], `${nome}: cor literal`);
    assert.deepEqual(texto.match(/:\s*(white|black)\s*[;}!]/gi) || [], [], `${nome}: nome de cor`);
    assert.deepEqual(texto.match(/var\(--vlado-[\w-]+\)/g) || [], [], `${nome}: primitivo usado direto`);
    assert.deepEqual(texto.match(new RegExp(`var\\(--(?:${cores})\\s*,`, 'g')) || [], [], `${nome}: var() de cor com reserva`);
    assert.deepEqual(blocos(texto).filter(b => propriedades(b.corpo).some(([n]) => /^--(theme|vlado)-/.test(n))).map(b => b.seletor), [],
      `${nome}: token definido fora de tokens.css`);
  }
  assert.deepEqual(ler('desktop.js').match(/#[0-9a-f]{6}\b/gi) || [], [], 'cor fixa em desktop.js');
  for (const script of ['quadros.js', 'analise.js'].filter(n => fs.existsSync(path.join(raiz, n)))) {
    assert.deepEqual(ler(script).match(/#[0-9a-f]{6}\b|rgba?\(/gi) || [], [], `cor fixa em ${script}`);
  }
});

test('todo token usado nas folhas está definido', () => {
  for (const nome of [...FOLHAS, 'tokens.css']) {
    const texto = semComentarios(ler(nome));
    // A sheet may define its own layout measures (--faixa-ambiente); colours come from tokens.css.
    const definidos = new Set([...Object.keys(escuro), ...blocos(texto).flatMap(b => propriedades(b.corpo).map(([n]) => n))]);
    const usados = [...new Set([...texto.matchAll(/var\((--[\w-]+)\)/g)].map(m => m[1]))];
    // Custom properties set at run time by scripts or the PDF reader are not design tokens.
    const faltam = usados.filter(n => !definidos.has(n) && !/^--(total-scale-factor|scale-factor|min-font-size|text-scale-factor|font-height|scale-x|rotate|min-font-size-inv|user-unit|mesa-[\w-]+)$/.test(n));
    assert.deepEqual(faltam, [], `${nome}: tokens usados sem definição`);
  }
});

test('cada tema tem um único conjunto de tokens semânticos, com os mesmos nomes', () => {
  const nomesTema = b => propriedades(b.corpo).map(([n]) => n).filter(n => n.startsWith('--theme-')).sort();
  const temas = blocos(tokens).filter(b => nomesTema(b).length);
  assert.deepEqual(temas.map(b => b.seletor), [':root', ':root[data-theme=dark]']);
  assert.deepEqual(nomesTema(temas[0]), nomesTema(temas[1]));
});

test('pares de texto e fundo passam no contraste AA (4,5:1) nos dois temas', () => {
  const textos = ['text', 'muted', 'accent', 'warning', 'danger'];
  const fundos = ['background', 'surface', 'reading', 'soft', 'sidebar', 'active'];
  const pares = [...textos.flatMap(t => fundos.map(f => [t, f])),
    ['on-primary', 'accent'], ['on-primary', 'primary-hover'], ['warning', 'warning-bg'], ['danger', 'danger-bg'], ['text', 'warning-bg'], ['text', 'danger-bg'],
    ['--comparar-removido-texto', '--comparar-removido-fundo'], ['--comparar-incluido-texto', '--comparar-incluido-fundo']];
  for (const [nome, tema] of [['claro', claro], ['escuro', escuro]]) {
    for (const [frente, fundo] of pares) {
      const razao = contraste(cor(tema, frente), cor(tema, fundo));
      assert.ok(razao >= 4.5, `${nome}: ${frente} ${cor(tema, frente)} sobre ${fundo} ${cor(tema, fundo)} = ${razao.toFixed(2)} < 4.5`);
    }
  }
});

test('bordas de controles, foco e marcas do mapa alcançam 3:1 nos dois temas', () => {
  const pares = [
    ['claro', claro, 'input-line', ['surface', 'background', 'soft', 'reading']],
    ['claro', claro, 'danger-line', ['surface', 'reading']],
    ['claro', claro, 'accent-line', ['surface']],
    ['claro', claro, 'focus', ['background', 'surface']],
    ['claro', claro, 'entidade-pessoa', ['surface', 'background']],
    ['claro', claro, 'entidade-organizacao', ['surface', 'background']],
    ['escuro', escuro, 'input-line', ['surface', 'background']],
    ['escuro', escuro, 'danger-line', ['surface']],
    ['escuro', escuro, 'accent-line', ['surface']],
    ['escuro', escuro, 'focus', ['background', 'surface']],
    ['escuro', escuro, 'entidade-pessoa', ['surface', 'background']],
    ['escuro', escuro, 'entidade-organizacao', ['surface', 'background']],
  ];
  for (const [nome, tema, borda, fundos] of pares) {
    for (const fundo of fundos) {
      const razao = contraste(cor(tema, borda), cor(tema, fundo));
      assert.ok(razao >= 3, `${nome}: ${borda} ${cor(tema, borda)} sobre ${fundo} ${cor(tema, fundo)} = ${razao.toFixed(2)} < 3`);
    }
  }
});

test('marcas do mapa e o foco delas alcançam 3:1 sobre o fundo do próprio mapa', () => {
  // The SVG sits on --quadro-coluna-fundo (reading), not on the page surface.
  for (const [nome, tema] of [['claro', claro], ['escuro', escuro]]) {
    for (const marca of ['--mapa-ligacao', '--mapa-ligacao-destaque', '--mapa-pessoa', '--mapa-organizacao']) {
      const razao = contraste(cor(tema, marca), cor(tema, '--quadro-coluna-fundo'));
      assert.ok(razao >= 3, `${nome}: ${marca} sobre o fundo do mapa = ${razao.toFixed(2)} < 3`);
    }
  }
});

test('campos e botões secundários usam a borda de controle, sem cor fixa', () => {
  assert.match(css, /input,select,textarea\{[^}]*border-color:var\(--theme-input-line\)/);
  assert.match(css, /\.secondary\{[^}]*border-color:var\(--theme-input-line\)/);
  assert.match(css, /\.danger\{[^}]*border-color:var\(--theme-danger-line\)/);
});

test('texto usa uma escala curta e nunca fica abaixo de 12px', t => {
  const escala = Object.entries(claro).filter(([nome]) => nome.startsWith('--text-'));
  const interface_ = escala.filter(([nome]) => !['--text-quote', '--text-brand'].includes(nome));
  assert.ok(interface_.length >= 6 && interface_.length <= 7, `${interface_.length} degraus de interface`);
  for (const [nome, valor] of escala) {
    assert.match(valor, /^\d+px$/, nome);
    assert.ok(parseInt(valor, 10) >= 12, `${nome}: ${valor}`);
  }
  const fixos = blocos(css).flatMap(r => (r.corpo.match(/font(?:-size)?\s*:[^;]*?\d+px[^;]*/g) || []).map(d => `${r.seletor} { ${d} }`));
  assert.deepEqual(fixos, [], 'tamanho de texto fora da escala');
  t.diagnostic(`escala: ${escala.map(([nome, valor]) => `${nome.slice(7)} ${valor}`).join(', ')}`);
});
