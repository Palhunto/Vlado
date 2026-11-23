'use strict';
// O gerador de código QR vendorizado (interface/vendor/qrcodegen, Project Nayuki 1.8.0, MIT) e o desenho em SVG de interface/fator.js: o arquivo confere com o manifesto, o servidor o publica e
// o QR de um endereço otpauth tem a estrutura que o leitor do celular espera (marcas de canto, tempo, módulo escuro, informação de formato com a correção BCH). A leitura por um decodificador de
// verdade foi conferida à mão com o Chromium e o ZXing-C++ (ver o README da pasta); aqui ficam as invariantes que não dependem de um decodificador.
const test = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {criarMesa} = require('./dom_minimo.cjs');

const RAIZ = path.join(__dirname, '..');
const PASTA = path.join(RAIZ, 'interface', 'vendor', 'qrcodegen');
const sha = arquivo => crypto.createHash('sha256').update(fs.readFileSync(arquivo)).digest('hex');
const OTPAUTH = 'otpauth://totp/Vlado:ana.lima%40redacaoserena.org?secret=JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP&issuer=Vlado&algorithm=SHA1&digits=6&period=30';

function carregarGerador() {
  const contexto = vm.createContext({});
  vm.runInContext(fs.readFileSync(path.join(PASTA, 'qrcodegen.js'), 'utf8'), contexto, {filename: 'qrcodegen.js'});
  return vm.runInContext('qrcodegen', contexto);
}
const modulos = qr => Array.from({length: qr.size}, (_, y) => Array.from({length: qr.size}, (_, x) => qr.getModule(x, y)));

test('o arquivo vendorizado confere com o manifesto (hash, versão fixa, licença MIT ao lado) e consta nos avisos de licença', () => {
  const manifesto = JSON.parse(fs.readFileSync(path.join(PASTA, 'manifesto.json'), 'utf8'));
  assert.equal(manifesto.version, '1.8.0'); assert.equal(manifesto.license, 'MIT'); assert.match(manifesto.commit, /^[0-9a-f]{40}$/);
  for (const [arquivo, esperado] of Object.entries(manifesto.files)) assert.equal(sha(path.join(PASTA, arquivo)), esperado, `${arquivo} confere com o manifesto`);
  assert.match(fs.readFileSync(path.join(PASTA, 'LICENSE'), 'utf8'), /Copyright \(c\) Project Nayuki\. \(MIT License\)/);
  assert.match(fs.readFileSync(path.join(RAIZ, 'docs', 'AVISOS_DE_LICENCA.md'), 'utf8'), /QR Code generator library 1\.8\.0 \(Project Nayuki\) \| MIT \| `interface\/vendor\/qrcodegen\/LICENSE`/);
  const fonte = fs.readFileSync(path.join(PASTA, 'qrcodegen.js'), 'utf8');
  assert.ok(!/\beval\s*\(|new Function|XMLHttpRequest|\bfetch\s*\(|importScripts/.test(fonte), 'o gerador não usa rede nem eval');
});

test('o servidor publica o gerador e o fator.js (CSP script-src self: nada de CDN)', () => {
  const rotas = fs.readFileSync(path.join(RAIZ, 'scripts', 'rotas_estaticas.py'), 'utf8');
  assert.match(rotas, /'\/vendor\/qrcodegen\/qrcodegen\.js': \('vendor\/qrcodegen\/qrcodegen\.js'/); assert.match(rotas, /'\/fator\.js': \('fator\.js'/);
  const indice = fs.readFileSync(path.join(RAIZ, 'interface', 'index.html'), 'utf8');
  assert.match(indice, /<script src="\/fator\.js[^"]*" defer><\/script>/); assert.ok(!/cdn|unpkg|jsdelivr/i.test(fs.readFileSync(path.join(RAIZ, 'interface', 'fator.js'), 'utf8')), 'fator.js não busca nada de fora');
});

test('o QR de um endereço otpauth: versão compatível, marcas de canto, linhas de tempo, módulo escuro e informação de formato válida', () => {
  const {QrCode} = carregarGerador();
  const qr = QrCode.encodeText(OTPAUTH, QrCode.Ecc.MEDIUM);
  assert.ok(qr.version >= 6 && qr.version <= 10, `versão ${qr.version}: o endereço de uns 150 caracteres cabe na 7 ou 8`);
  assert.equal(qr.size, 4 * qr.version + 17); assert.equal(qr.errorCorrectionLevel.ordinal, QrCode.Ecc.MEDIUM.ordinal);
  const m = modulos(qr), n = qr.size;
  // marca de canto: anel escuro de 7×7, anel claro, núcleo escuro de 3×3; nos três cantos
  for (const [cx, cy] of [[0, 0], [n - 7, 0], [0, n - 7]]) {
    for (let y = 0; y < 7; y++) for (let x = 0; x < 7; x++) {
      const borda = x === 0 || x === 6 || y === 0 || y === 6, nucleo = x >= 2 && x <= 4 && y >= 2 && y <= 4;
      assert.equal(m[cy + y][cx + x], borda || nucleo, `marca de canto em (${cx},${cy}) módulo ${x},${y}`);
    }
  }
  for (let i = 8; i < n - 8; i++) { assert.equal(m[6][i], i % 2 === 0, `tempo horizontal ${i}`); assert.equal(m[i][6], i % 2 === 0, `tempo vertical ${i}`); }
  assert.equal(m[n - 8][8], true, 'o módulo escuro fixo');
  // informação de formato: 15 bits (nível, máscara, BCH) lidos em duas cópias, que precisam coincidir e ser um código BCH(15,5) válido, com a máscara 0x5412
  const copiaA = []; for (let i = 0; i <= 5; i++) copiaA.push(m[i][8]); copiaA.push(m[7][8], m[8][8], m[8][7]); for (let i = 9; i < 15; i++) copiaA.push(m[8][14 - i]);
  const copiaB = []; for (let i = 0; i < 8; i++) copiaB.push(m[8][n - 1 - i]); for (let i = 8; i < 15; i++) copiaB.push(m[n - 15 + i][8]);
  const bits = copia => copia.reduce((acc, b, i) => acc | (b ? 1 << i : 0), 0);
  assert.equal(bits(copiaA), bits(copiaB), 'as duas cópias da informação de formato coincidem');
  const formato = bits(copiaA) ^ 0x5412, dados = formato >>> 10;
  let resto = dados; for (let i = 0; i < 10; i++) resto = (resto << 1) ^ ((resto >>> 9) * 0x537);
  assert.equal(((dados << 10) | (resto & 0x3ff)), formato, 'o BCH da informação de formato é válido');
  assert.equal(dados >>> 3, 0, 'nível de correção M (código 00)'); assert.equal(dados & 7, qr.mask);
});

test('é determinístico: o mesmo endereço dá os mesmos módulos, e endereços diferentes dão matrizes diferentes', () => {
  const {QrCode} = carregarGerador();
  const resumo = texto => crypto.createHash('sha256').update(JSON.stringify(modulos(QrCode.encodeText(texto, QrCode.Ecc.MEDIUM)))).digest('hex');
  assert.equal(resumo(OTPAUTH), resumo(OTPAUTH)); assert.notEqual(resumo(OTPAUTH), resumo(OTPAUTH.replace('JBSWY', 'JBSWZ')));
});

test('Fator.qrSvg: SVG em linha, um <path> só com módulos quadrados inteiros, zona de silêncio de 4 módulos, escuro sobre claro, role=img e aria-label', async () => {
  const mesa = criarMesa({scripts: ['fator.js']});
  mesa.executar(path.join('vendor', 'qrcodegen', 'qrcodegen.js'));
  const svg = await mesa.janela.Fator.qrSvg(OTPAUTH);
  const {QrCode} = carregarGerador();
  const qr = QrCode.encodeText(OTPAUTH, QrCode.Ecc.MEDIUM), total = qr.size + 8;
  assert.equal(svg.getAttribute('viewBox'), `0 0 ${total} ${total}`); assert.equal(svg.getAttribute('shape-rendering'), 'crispEdges'); assert.equal(svg.getAttribute('role'), 'img');
  assert.equal(svg.getAttribute('aria-label'), 'Código QR para o aplicativo autenticador. Se não puder ler, use a chave em texto abaixo.');
  const lado = Number(svg.getAttribute('width'));
  assert.equal(lado, Number(svg.getAttribute('height'))); assert.ok(lado <= 200 && lado % total === 0, `lado ${lado}: múltiplo inteiro de ${total} módulos, cabe em 200 px`);
  const filhos = [...svg.childNodes]; assert.equal(filhos.length, 2);
  assert.equal(filhos[0].getAttribute('fill'), '#ffffff'); assert.equal(filhos[1].getAttribute('fill'), '#000000');
  const escuros = (filhos[1].getAttribute('d').match(/M/g) || []).length;
  assert.equal(escuros, modulos(qr).flat().filter(Boolean).length, 'um quadrado por módulo escuro');
  assert.ok(/^M4,4/.test(filhos[1].getAttribute('d')) || /M4,4h1v1h-1z/.test(filhos[1].getAttribute('d')), 'os módulos começam depois da zona de silêncio de 4');
  assert.ok(![...mesa.doc.querySelectorAll('*')].some(e => /localStorage|sessionStorage/.test(e.outerHTML || '')), 'nada guardado');
});

test('o manifesto traz o comando exato da compilação (compilador e opções) e os passos para refazê-la e conferir os hashes', () => {
  const manifesto = JSON.parse(fs.readFileSync(path.join(PASTA, 'manifesto.json'), 'utf8'));
  assert.equal(manifesto.build.compilador, 'typescript@5.6.3 (npm)');
  assert.equal(manifesto.build.comando, 'npx --yes -p typescript@5.6.3 tsc --strict --lib DOM,DOM.Iterable,ES6 --target ES6 --outDir saida qrcodegen.ts');
  assert.ok(manifesto.build.passos.some(p => p.includes(manifesto.commit)), 'o download é do commit fixo');
  assert.ok(manifesto.build.passos.some(p => p.includes('sha256sum')), 'os passos mandam conferir os hashes');
  assert.match(manifesto.source_sha256, /^[0-9a-f]{64}$/);
});
