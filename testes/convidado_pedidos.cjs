'use strict';
// A tela do convidado só pede o que o papel pode fazer: toda operação recusada vira uma linha `operacao_negada` no registro de acessos, e o
// cabeçalho dele não pode virar "Acervo indisponível" porque o inventário foi recusado. Lista conferida com OPERACOES_CONVIDADO em
// scripts/rotas_contas.py. DOM sintético (dom_minimo), sem rede.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {criarMesa} = require('./dom_minimo.cjs');

const ALFA = {id: 'alfa', titulo: 'Pauta Alfa', rodadas: []};
const SO_ADMINISTRADOR = ['ambiente', 'ia-config', 'analises', 'gerenciar-listar', 'inventario', 'apuracao-notas', 'diligencias-listar', 'caderno-listar'];

async function abrir(papel, desktop) {
  const operacoes = [];
  const respostas = {'codex-listar': {conversas: []}, 'codex-status': {autenticado: true, provedor: 'anthropic', modelo: 'modelo-teste'},
    inventario: {caso_id: 'alfa', corpus_id: 'c1', documentos: [], total_documentos: 0}, ambiente: {}, 'diligencias-listar': {resultados: []}};
  const mesa = criarMesa({papel, modo: 'piloto', idioma: 'pt', desktop, url: 'http://127.0.0.1:8765/?area=codex&caso=alfa', catalogo: [ALFA],
    api: operacao => { operacoes.push(operacao); return respostas[operacao] || {}; }});
  await mesa.esperar(30);
  return {mesa, operacoes};
}

for (const desktop of [false, true]) {
  test(`convidado não pede operações que o servidor recusa na carga (${desktop ? 'desktop' : 'celular'}) e o cabeçalho segue o de sempre`, async () => {
    const {mesa, operacoes} = await abrir('convidado', desktop);
    assert.deepEqual(operacoes.filter(op => SO_ADMINISTRADOR.includes(op)), [], 'pedidos que o papel não pode fazer');
    assert.ok(operacoes.includes('codex-listar'), 'a conversa continua carregando');
    assert.equal(mesa.$('mesa-versao').textContent, 'Documentos, achados e fontes');
  });
}

for (const desktop of [false, true]) {
  test(`convidado abre Perguntar sem erro no banner e sem o painel de documentos (${desktop ? 'desktop' : 'celular'})`, async () => {
    const {mesa} = await abrir('convidado', desktop);
    assert.equal(mesa.$('area-codex').hidden, false, 'o convidado está em Perguntar');
    assert.equal(mesa.$('codex-erro').hidden, true, 'a recusa do inventário não pode aparecer como erro da conversa');
    assert.equal(mesa.$('codex-erro').textContent, '');
    const css = fs.readFileSync(path.join(__dirname, '..', 'interface', 'style.css'), 'utf8');
    assert.match(css, /data-papel="convidado"\] #codex-inventario-detalhes/, 'o painel de documentos é escondido para o convidado');
  });
}

test('administrador segue pedindo inventário e a lista de diligências', async () => {
  const {operacoes} = await abrir('admin', true);
  assert.ok(operacoes.includes('inventario'));
  assert.ok(operacoes.includes('diligencias-listar'));
});

// A lista de operações que a tela não pede ao convidado mora em dois lugares: SO_ADMINISTRADOR em interface/app.js e OPERACOES_CONVIDADO
// (as permitidas) em scripts/rotas_contas.py, com as de rascunho em scripts/rascunhos.py. Este teste as amarra: se divergirem, falha.
const lerArquivo = (...partes) => fs.readFileSync(path.join(__dirname, '..', ...partes), 'utf8');
const aspas = texto => [...texto.matchAll(/'([a-z][a-z0-9-]*)'/g)].map(m => m[1]);

test('as operações que app.js nega ao convidado nunca coincidem com as que o servidor permite, e todas existem no servidor', () => {
  const app = lerArquivo('interface', 'app.js');
  const bloco = /const SO_ADMINISTRADOR = new Set\(\[([^\]]*)\]\)/.exec(app);
  assert.ok(bloco, 'SO_ADMINISTRADOR lido de app.js');
  const clienteNega = aspas(bloco[1]);
  assert.deepEqual([...clienteNega].sort(), [...SO_ADMINISTRADOR].sort(), 'a lista do teste de carga é a mesma de app.js');
  const rotas = lerArquivo('scripts', 'rotas_contas.py');
  const permitidasTexto = /OPERACOES_CONVIDADO = \(([\s\S]*?)\)\n/.exec(rotas);
  assert.ok(permitidasTexto, 'OPERACOES_CONVIDADO lido de rotas_contas.py');
  const rascunhos = lerArquivo('scripts', 'rascunhos.py');
  const camposPedido = /CAMPOS_PEDIDO = \{([\s\S]*?)\n\}/.exec(rascunhos);
  assert.ok(camposPedido, 'CAMPOS_PEDIDO lido de rascunhos.py');
  const permitidas = new Set([...aspas(permitidasTexto[1]), ...[...camposPedido[1].matchAll(/^\s+'([a-z-]+)':/gm)].map(m => m[1])]);
  assert.ok(permitidas.has('codex-listar') && permitidas.has('rascunhos-ler'), 'as permitidas incluem as de conversa e de rascunho');
  const conflito = clienteNega.filter(op => permitidas.has(op));
  assert.deepEqual(conflito, [], 'app.js bloquearia uma operação que o servidor permite ao convidado');
  // Cada operação negada existe de fato no servidor (um erro de digitação deixaria a recusa local sem efeito).
  const servidor = fs.readdirSync(path.join(__dirname, '..', 'scripts')).filter(nome => nome.endsWith('.py'))
    .map(nome => lerArquivo('scripts', nome)).join(' ');
  const inexistentes = clienteNega.filter(op => !servidor.includes(`'${op}'`) && !servidor.includes(`"${op}"`));
  assert.deepEqual(inexistentes, [], 'operação negada que o servidor desconhece');
});
