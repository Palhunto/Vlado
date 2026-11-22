'use strict';
// O DOM mínimo precisa errar onde o navegador erra: querySelectorAll devolve um NodeList, que NÃO tem filter, map, some,
// find, includes nem indexOf (um Array escondia o TypeError que o Chromium lança no Tab do diálogo).
const test = require('node:test');
const assert = require('node:assert/strict');
const {criarMesa} = require('./dom_minimo.cjs');

const lista = () => criarMesa({scripts: [], html: '<main><ul id="u"><li>a</li><li>b</li><li>c</li></ul></main>'}).doc.querySelectorAll('li');

test('querySelectorAll devolve um NodeList: length, item(), índices e iteração', () => {
  const nos = lista();
  assert.equal(nos.length, 3);
  assert.equal(nos[1].textContent, 'b');
  assert.equal(nos.item(2).textContent, 'c');
  assert.equal(nos.item(3), null);
  assert.equal(Object.prototype.toString.call(nos), '[object NodeList]');
  assert.deepEqual([...nos].map(n => n.textContent), ['a', 'b', 'c']);
  assert.deepEqual(Array.from(nos, n => n.textContent), ['a', 'b', 'c']);
  const vistos = [];
  nos.forEach((no, i) => vistos.push(`${i}${no.textContent}`));
  assert.deepEqual(vistos, ['0a', '1b', '2c']);
  assert.deepEqual([...nos.keys()], [0, 1, 2]);
  assert.deepEqual([...nos.values()].map(n => n.textContent), ['a', 'b', 'c']);
  assert.deepEqual([...nos.entries()].map(([i, n]) => `${i}${n.textContent}`), ['0a', '1b', '2c']);
});

test('querySelectorAll não tem os métodos de Array', () => {
  const nos = lista();
  for (const metodo of ['filter', 'map', 'some', 'every', 'find', 'findIndex', 'includes', 'indexOf', 'reduce', 'slice', 'flatMap', 'concat', 'at']) {
    assert.equal(typeof nos[metodo], 'undefined', `${metodo} existe no NodeList do DOM mínimo`);
    assert.throws(() => nos[metodo](() => true), TypeError);
  }
});

test('lista vazia continua sendo um NodeList vazio', () => {
  const nos = criarMesa({scripts: [], html: '<main></main>'}).doc.querySelectorAll('li');
  assert.equal(nos.length, 0);
  assert.equal(nos[0], undefined);
  assert.equal(nos.item(0), null);
  assert.deepEqual([...nos], []);
});
