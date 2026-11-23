'use strict';
// Todo texto de interface das telas de Contas (conta.js, equipe.js, fator.js e o diálogo com senha de dialogo.js) tem a tradução em inglês em i18n_en.js, sem depender de chave herdada
// de outra tela (a "Recuperar acesso" da tela antiga de Contas de acesso sumiu com ela e derrubou um teste em inglês). O teste lê o fonte atrás das formas em que a Mesa passa um texto à
// interface (t('…'), botao('…'), titulo/texto/acao/ocupado/rotulo/apoio: '…', mensagens de erro de campo) e as frases da atividade da Equipe, e exige a chave no dicionário.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {criarMesa} = require('./dom_minimo.cjs');

const INTERFACE = path.join(__dirname, '..', 'interface');
const CONTEUDO = arquivo => fs.readFileSync(path.join(INTERFACE, arquivo), 'utf8');
const dicionario = () => {
  const janela = {};
  vm.runInNewContext(CONTEUDO('i18n_en.js'), {window: janela});
  return janela.VLADO_I18N_EN;
};
const LITERAL = String.raw`'((?:[^'\\\n]|\\.)*)'`;
const desescapar = texto => texto.replace(/\\(.)/g, '$1');
// Formas em que o fonte entrega um texto à interface; cada uma captura o literal em português.
const FORMAS = [
  new RegExp(String.raw`\bt\(\s*${LITERAL}`, 'g'),
  new RegExp(String.raw`\bbotao\(\s*${LITERAL}`, 'g'),
  new RegExp(String.raw`\bapoio\(\s*${LITERAL}`, 'g'),
  new RegExp(String.raw`\b(?:titulo|texto|acao|ocupado|rotulo|apoio|cancelar|etapaInicial|incorreta):\s*${LITERAL}`, 'g'),
  new RegExp(String.raw`\berroCampo\([^,()]*,\s*${LITERAL}`, 'g'),
  new RegExp(String.raw`\bmostrarErro\(\s*${LITERAL}`, 'g'),
];
// Textos que não são de interface (identificadores, nomes de operação, formatos) e que a regra acima pode apanhar.
const NAO_E_TEXTO = new Set(['Conta', 'login']);  // 'Conta' é o aria-label do <nav> das abas; 'login' é o rótulo curto traduzido igual em inglês
const ehTexto = literal => /[A-Za-zÀ-ú]/.test(literal) && !/^[a-z0-9_:\-./]+$/.test(literal) && !/^#?[0-9a-f]{3,8}$/i.test(literal);

function literaisDe(arquivo) {
  const fonte = CONTEUDO(arquivo), achados = new Map();
  for (const forma of FORMAS) for (const m of fonte.matchAll(forma)) {
    const texto = desescapar(m[1]);
    if (ehTexto(texto) && !NAO_E_TEXTO.has(texto)) achados.set(texto, (fonte.slice(0, m.index).match(/\n/g) || []).length + 1);
  }
  return achados;
}
const ARQUIVOS = ['conta.js', 'equipe.js', 'fator.js'];

test('todo texto de interface de conta.js, equipe.js e fator.js tem a tradução em inglês no dicionário', () => {
  const textos = dicionario().textos;
  const faltam = [];
  for (const arquivo of ARQUIVOS) for (const [texto, linha] of literaisDe(arquivo)) {
    if (!(texto in textos)) faltam.push(`${arquivo}:${linha}  ${texto}`);
  }
  assert.deepEqual(faltam, [], `faltam em i18n_en.js:\n${faltam.join('\n')}`);
});

test('as frases da atividade da Equipe e as do diálogo com senha também estão traduzidas', () => {
  const textos = dicionario().textos;
  const mesa = criarMesa({scripts: [], modo: 'piloto'});
  // o dicionário é lido do fonte: as frases estão em FRASES (equipe.js) e os textos fixos do diálogo com senha em dialogo.js
  const frases = [...CONTEUDO('equipe.js').matchAll(/FRASES = \{([\s\S]*?)\n  \};/g)].flatMap(m => [...m[1].matchAll(new RegExp(String.raw`:\s*${LITERAL}`, 'g'))].map(x => desescapar(x[1])));
  assert.ok(frases.length > 30, `as frases foram achadas (${frases.length})`);
  const faltam = frases.filter(f => !(f in textos));
  const dialogo = ['Sua senha', 'A senha com que você entra na Mesa.', 'Senha incorreta. Confira e tente de novo.', 'Mostrar', 'Ocultar', 'Enviando…',
    'Muitas senhas erradas seguidas. Por 15 minutos, as ações que pedem a senha ficam bloqueadas para a sua conta; o resto da Mesa continua.'].filter(f => !(f in textos));
  assert.deepEqual([...faltam, ...dialogo], [], 'frases sem tradução');
  assert.ok(mesa);
});
