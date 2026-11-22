'use strict';
// The cited page of the original is one click away, and the human mark waits for it.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {criarMesa} = require('./dom_minimo.cjs');

const INTERFACE = path.join(__dirname, '..', 'interface');
const ALFA = {id: 'alfa', titulo: 'Pauta Alfa', rodadas: [{id: 'R001', geracoes: []}]};
const ESCOPO = {caso: 'alfa', rodada: 'R001', revisao: 'r2', geracao_achados: 'g1'};
const EVIDENCIA = {id: 'E1', documento_id: 'D1', original: 'casos/alfa/D1_contrato.pdf', original_sha256: 'h1',
  trecho: 'Valor global de R$ 10 mil.', localizador: {tipo: 'linhas', pagina_pdf: 12, linha_inicio: 3, linha_fim: 4},
  modo: 'texto', atribuicao: 'Prefeitura', contexto: 'Cláusula 2'};
const ACHADO = {id: 'A001', versao: 1, redacao: 'O contrato vale R$ 10 mil.', natureza: 'declaracao_documental',
  suporte: 'sustentado', destino: 'incluido', subquestao: 'Quanto custa?', limitacoes: '',
  verificacao_externa: {estado: 'nao_realizada', limitacao: 'Sem consulta externa.'},
  revisao_humana: {estado: 'pendente', observacao: '', evento_id: null, historico: []}, conferencia_humana: 'nao_realizada',
  historico: {conferencias_humanas: [], versoes: [], revisoes_assistidas: [], destinos: []}, briefing: null,
  vinculos: [{evidencia_id: 'E1', papel: 'suporte', justificativa: 'Cláusula com o valor.'}], evidencias: [EVIDENCIA]};

function abrir(respostas = {}) {
  let eventosEntregues = false;
  return criarMesa({catalogo: [ALFA], url: 'http://127.0.0.1:8765/?area=codex&caso=alfa', api: operacao => {
    if (operacao in respostas) return typeof respostas[operacao] === 'function' ? respostas[operacao]() : respostas[operacao];
    if (operacao === 'codex-listar') return {conversas: [{id: 'chat1', titulo: 'Conversa 1', estado: 'concluido'}]};
    if (operacao === 'codex-eventos') {
      const eventos = eventosEntregues ? [] : [
        {tipo: 'escopo', dados: {caso: 'alfa', rodada: 'R001', corpus_id: 'c1'}},
        {tipo: 'fonte', dados: {referencia: 'R1', rodada: 'R001', documento_id: 'D1', original: 'casos/alfa/D1_contrato.pdf', pagina_pdf: 12, trecho: 'Valor global.'}},
        {tipo: 'resposta', dados: {item: 'm1', texto: 'O valor é R$ 10 mil [fonte:R1].', fase: 'final_answer', rodada: 'R001', publicada: true}}];
      eventosEntregues = true;
      return {conversa: {estado: 'concluido'}, cursor: 3, eventos, acervos: {}};
    }
    if (operacao === 'inventario') return {caso_id: 'alfa', corpus_id: 'c1', documentos: [], total_documentos: 0};
    if (/original$/.test(operacao)) return {type: 'application/pdf'};
    if (operacao === 'achados-detalhe') return {achado: structuredClone(ACHADO), registros_sha256: 'hash'};
    if (operacao === 'achados-evidencia') return {contexto: [{linha: 3, texto: 'Valor global.'}], evidencia: {}};
    return {};
  }});
}
const botoes = raiz => [...raiz.querySelectorAll('button')];

test('citação da resposta mostra a página e abre o original nela, com um clique', async () => {
  const mesa = abrir();
  await mesa.esperar(12);
  mesa.$('codex-conversa').value = 'chat1';
  mesa.$('codex-conversa').dispatchEvent(new mesa.janela.Event('change'));
  await mesa.esperar(12);
  const chip = mesa.$('codex-mensagens').querySelector('.source-citation');
  assert.ok(chip, 'a resposta deve ter uma citação');
  assert.equal(chip.tagName, 'BUTTON');
  assert.equal(chip.textContent, 'p. 12');
  assert.equal(chip.getAttribute('aria-label'), 'Ver página 12 no original: contrato');
  assert.equal(chip.parentElement.className, 'citation-keep', 'a pontuação seguinte não começa a linha sozinha');
  assert.equal(chip.parentElement.textContent, 'p. 12.');
  chip.click();
  await mesa.esperar(8);
  const pedido = mesa.chamadas.find(c => c.operacao === 'codex-original');
  assert.deepEqual(pedido?.dados, {conversa: 'chat1', referencia: 'R1'});
  assert.equal(mesa.$('original-dialogo').open, true);
  assert.match(mesa.$('original-localizacao').textContent, /Página física 12/);
  assert.equal(mesa.$('fonte-R1').open, true, 'o cartão lateral continua disponível e aberto');
  assert.equal(botoes(mesa.$('fonte-R1'))[0].textContent, 'Ver página 12 no original');
});

test('achado põe trecho e localizador antes dos metadados, com o original como ação principal', async () => {
  const mesa = abrir();
  await mesa.esperar(12);
  const card = mesa.avaliar('renderFinding')(structuredClone(ACHADO), ESCOPO, mesa.avaliar('findingEpoch'));
  const ordem = card.childNodes;
  const evidencia = ordem.findIndex(no => no.classList?.contains('evidence'));
  const metadado = ordem.findIndex(no => /^Pergunta relacionada/.test(no.textContent));
  assert.ok(evidencia > 0 && metadado > evidencia, `evidência (${evidencia}) antes dos metadados (${metadado})`);
  const bloco = ordem[evidencia];
  assert.equal(bloco.querySelector('blockquote').textContent, 'Valor global de R$ 10 mil.');
  const principal = botoes(bloco)[0];
  assert.equal(principal.textContent, 'Ver página 12 no original');
  assert.equal(principal.classList.contains('secondary'), false);
});

test('“Conferida no original” só libera depois de abrir o original do trecho citado', async () => {
  const mesa = abrir();
  await mesa.esperar(12);
  const opcao = () => mesa.$('revisao-estado').querySelector('[value="conferida_no_original"]');
  await mesa.janela.conferirAchado(structuredClone(ACHADO), ESCOPO, mesa.avaliar('findingEpoch'));
  await mesa.esperar(6);
  assert.equal(opcao().disabled, true);
  assert.equal(mesa.$('revisao-guarda').hidden, false);
  assert.match(mesa.$('revisao-guarda').textContent, /abra o original/);
  const original = botoes(mesa.$('revisao-fontes')).find(b => b.textContent === 'Ver página 12 no original');
  assert.ok(original, 'o diálogo oferece o original na página citada');
  original.click();
  await mesa.esperar(8);
  assert.equal(mesa.$('original-dialogo').open, true);
  assert.equal(opcao().disabled, false);
  assert.equal(mesa.$('revisao-guarda').hidden, true);
});

test('original aberto pelo achado já libera a marcação ao abrir a conferência', async () => {
  const mesa = abrir();
  await mesa.esperar(12);
  const card = mesa.avaliar('renderFinding')(structuredClone(ACHADO), ESCOPO, mesa.avaliar('findingEpoch'));
  botoes(card.querySelector('.evidence'))[0].click();
  await mesa.esperar(8);
  mesa.$('original-dialogo').close();
  await mesa.janela.conferirAchado(structuredClone(ACHADO), ESCOPO, mesa.avaliar('findingEpoch'));
  await mesa.esperar(6);
  assert.equal(mesa.$('revisao-estado').querySelector('[value="conferida_no_original"]').disabled, false);
  assert.equal(mesa.$('revisao-guarda').hidden, true);
});

test('rótulos do original são os mesmos em todas as telas, nas duas línguas', () => {
  const html = fs.readFileSync(path.join(INTERFACE, 'index.html'), 'utf8');
  assert.match(html, /id="original-fechar"[^>]*>Fechar original</);
  assert.doesNotMatch(html, /Voltar à fonte|Baixar original para conferir/);
  for (const nome of ['app.js', 'codex.js', 'revisao.js', 'caderno.js', 'desktop.js', 'apuracao.js']) {
    assert.doesNotMatch(fs.readFileSync(path.join(INTERFACE, nome), 'utf8'), /'Conferir original|Abrir fonte original/, nome);
  }
  const mesa = criarMesa({idioma: 'en', armazenamento: {'vlado-idioma': 'en'}, scripts: ['i18n_en.js', 'i18n.js', 'leitura.js']});
  const t = mesa.janela.I18N.t;
  assert.equal(t('Ver página 12 no original'), 'Open page 12 in the original');
  assert.equal(t('Abrir original'), 'Open original');
  assert.equal(t('Fechar original'), 'Close original');
  assert.equal(t('Ver página 3 no original: Contrato'), 'Open page 3 in the original: Contrato');
  assert.equal(mesa.janela.Leitura.rotuloOriginal(7), 'Ver página 7 no original');
  assert.equal(mesa.janela.Leitura.rotuloOriginal(null), 'Abrir original');
});
