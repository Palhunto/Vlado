'use strict';
// Every HTTP error carries a stable `codigo`. In English the screen shows a message per code
// (with `parametros`); unknown codes and 'erro' fall back to generic English plus the original.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {criarMesa} = require('./dom_minimo.cjs');

function mesaCom(idioma, corpo, status = 400) {
  return criarMesa({idioma, armazenamento: {'vlado-idioma': idioma}, scripts: ['i18n_en.js', 'i18n.js', 'leitura.js', 'app.js'],
    preparar: janela => {
      janela.fetch = async rota => String(rota) === '/api/catalogo'
        ? {ok: true, json: async () => ({casos: []})}
        : {ok: false, status, json: async () => corpo};
    }});
}
async function falha(idioma, corpo, status) {
  const mesa = mesaCom(idioma, corpo, status);
  try { await mesa.avaliar('api')('qualquer', {}); } catch (erro) { return erro; }
  assert.fail('api() deveria rejeitar');
}

test('código conhecido aparece em inglês, com os parâmetros', async () => {
  const corpo = {estado: 'erro', erro: 'Limite diário de 3 pergunta(s) atingido. Tente novamente amanhã.', codigo: 'cota_diaria_esgotada', parametros: {cota: 3}};
  const erro = await falha('en', corpo);
  assert.equal(erro.message, 'Daily limit of 3 question(s) reached. Try again tomorrow.');
  assert.deepEqual(erro.result, corpo, 'a resposta original continua disponível para a tela');
});

test('falha do provedor (ia_*) e a trava do original também têm texto em inglês', async () => {
  assert.equal((await falha('en', {erro: 'A conversa excedeu a janela de contexto do modelo. Abra uma nova conversa.', codigo: 'ia_contexto'})).message,
    "The conversation went past the model's context window. Open a new conversation.");
  const trava = await falha('en', {erro: 'Para marcar “Conferida no original”, abra antes o original de cada trecho citado (faltam: E001, E002).',
    codigo: 'conferencia_sem_original', faltam: ['E001', 'E002']});
  assert.equal(trava.message, 'To mark “Checked against the original”, first open the original of each cited excerpt (missing: E001, E002).');
});

test('código desconhecido ou genérico cai no texto genérico com a mensagem original', async () => {
  const pt = 'Mensagem nova que o dicionário ainda não conhece.';
  assert.equal((await falha('en', {erro: pt, codigo: 'algo_novo'})).message, `The server refused the operation. (${pt})`);
  assert.equal((await falha('en', {erro: pt, codigo: 'erro'})).message, `The server refused the operation. (${pt})`);
  assert.equal((await falha('en', {erro: pt})).message, `The server refused the operation. (${pt})`);
});

test('em português a mensagem do servidor aparece como veio', async () => {
  const corpo = {erro: 'Limite diário de 3 pergunta(s) atingido. Tente novamente amanhã.', codigo: 'cota_diaria_esgotada', parametros: {cota: 3}};
  assert.equal((await falha('pt', corpo)).message, corpo.erro);
});

test('o dicionário cobre todos os códigos de scripts/erros.py e as falhas do provedor', () => {
  const fonte = fs.readFileSync(path.join(__dirname, '..', 'scripts', 'erros.py'), 'utf8');
  const codigos = [...fonte.matchAll(/^\s+\('([a-z_]+)', r'/gm)].map(m => m[1]);
  const ia = ['autenticacao', 'limite', 'cobranca', 'conexao', 'servidor', 'max_tokens', 'contexto', 'recusa', 'filtro', 'incompleta',
    'passos', 'ocupado', 'historico', 'tempo_etapa'].map(c => 'ia_' + c);
  const mesa = criarMesa({scripts: ['i18n_en.js']});
  const erros = mesa.janela.VLADO_I18N_EN.erros;
  const ausentes = [...codigos, ...ia, 'json_invalido', 'conflito'].filter(c => !erros[c]);
  assert.ok(codigos.length > 30, 'lista de códigos lida de erros.py');
  assert.deepEqual(ausentes, []);
});
