'use strict';
// Carga da Mesa (Onda 3, parte C): fontes WOFF2 latinas e cache por hash. As páginas pedem cada CSS, script e fonte com ?v=__V:<nome>__ (o servidor
// troca pelo hash do arquivo e serve com cache imutável), e todo marcador aponta para um arquivo que a rota lista e que existe no disco.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const raiz = path.join(__dirname, '..');
const ler = relativo => fs.readFileSync(path.join(raiz, relativo), 'utf8');
const rotas = ler('scripts/rotas_estaticas.py');
const listados = new Map([...rotas.matchAll(/^\s+'(\/[^']+)': \('([^']+)', '([^']+)'\)/gm)].map(m => [m[1], {arquivo: m[2], tipo: m[3]}]));
const nomeCurto = caminho => caminho.split('/').pop();
const naInterface = nome => path.join(raiz, 'interface', nome);

test('index.html e entrar.html pedem todo CSS e script da Mesa com ?v=__V:nome__ e o nome existe na rota e no disco', () => {
  for (const pagina of ['index.html', 'entrar.html']) {
    const html = ler(`interface/${pagina}`);
    const pedidos = [...html.matchAll(/<link rel="stylesheet" href="([^"]+)"|<script src="([^"]+)"/g)].map(m => m[1] || m[2]);
    assert.ok(pedidos.length >= 4, `${pagina}: ${pedidos.length} pedidos`);
    for (const pedido of pedidos) {
      const m = pedido.match(/^(\/[^?]+)\?v=__V:([^_]+(?:_[^_]+)*?)__$/);
      assert.ok(m, `${pagina}: ${pedido} deve levar ?v=__V:nome__`);
      assert.equal(m[2], nomeCurto(m[1]), `${pagina}: o marcador de ${m[1]} leva o nome do arquivo`);
      assert.ok(listados.has(m[1]), `${pagina}: a rota lista ${m[1]}`);
      assert.ok(fs.existsSync(naInterface(listados.get(m[1]).arquivo)), `${pagina}: ${m[1]} existe em interface/`);
    }
  }
});

test('as fontes são WOFF2 latinas, com a mesma URL versionada no @font-face e no preload, e o meta traz as versões para o que carrega sob demanda', () => {
  const css = ler('interface/style.css'), html = ler('interface/index.html');
  const faces = [...css.matchAll(/@font-face\{[^}]*\}/g)].map(m => m[0]);
  assert.equal(faces.length, 2, 'duas faces: Source Sans 3 e Source Serif 4');
  for (const face of faces) {
    assert.match(face, /format\('woff2'\)/, 'formato woff2');
    assert.match(face, /font-weight:400 800/, 'a declaração diz o mesmo que o arquivo: eixo de peso recortado a 400-800');
    assert.match(face, /font-display:swap/);
    const url = face.match(/url\('([^']+)'\)/)[1];
    assert.match(url, /^\/fonts\/Source(Sans3|Serif4)-latin\.woff2\?v=__V:Source(Sans3|Serif4)-latin\.woff2__$/);
    assert.ok(listados.has(url.split('?')[0]), 'a rota lista a fonte');
    assert.equal(listados.get(url.split('?')[0]).tipo, 'font/woff2');
    const tamanho = fs.statSync(naInterface(`fonts/${nomeCurto(url.split('?')[0])}`)).size;
    assert.ok(tamanho < 200 * 1024, `${url}: ${tamanho} bytes (a fonte inteira passava de 500 KB)`);
    const preload = [...html.matchAll(/<link rel="preload" href="([^"]+)" as="font" type="font\/woff2" crossorigin>/g)].map(m => m[1]);
    assert.ok(preload.includes(url), `o preload usa a mesma URL do @font-face: ${url}`);
  }
  // Nenhum peso fora da faixa do arquivo (200 ou 900 sairiam sintetizados).
  const pesos = [...css.replace(/@font-face\{[^}]*\}/g, '').matchAll(/font-weight:\s*(\d{3})/g)].map(m => Number(m[1]));
  assert.ok(pesos.length > 20 && pesos.every(p => p >= 400 && p <= 800), `pesos usados em style.css: ${[...new Set(pesos)].join(', ')}`);
  assert.doesNotMatch(css, /\.(ttf|otf)/, 'o CSS não pede mais a fonte inteira');
  assert.match(html, /<meta name="vlado-versoes" content='__VERSOES__'>/);
});
