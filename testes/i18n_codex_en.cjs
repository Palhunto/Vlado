'use strict';
// Renders "Ask the AI" in English with a real conversation and fails on any visible
// Portuguese chrome. Data (answers, excerpts, the question, case titles) is excluded.
const test = require('node:test');
const assert = require('node:assert/strict');
const {criarMesa} = require('./dom_minimo.cjs');

const ALFA = {id: 'alfa', titulo: 'Pauta Alfa', rodadas: [{id: 'R001', geracoes: []}]};
const PORTUGUES = /[ãõçáàâêéíóôú]|\b(não|uma|para|com|sua|seu|você|pergunta|perguntas|apuração|apurações|conversa|conversas|documento|documentos|fonte|fontes|selecione|escolha|nenhum|nenhuma|enviar|conferir|página|achado|achados|rodada|análise|linhas?|resposta|andamento|consultar|pronto|das|dos|da|de)\b/i;
const DADOS = '[translate="no"], blockquote, pre, code, .markdown-body, .vditor, [contenteditable="true"], textarea, script, style';
const PERMITIDOS = new Set(['Vlado', 'Anthropic (Claude)', 'OpenAI (GPT)']);

function eventos() {
  return [
    {tipo: 'pergunta', dados: {texto: 'Quanto custou a merenda escolar?'}},
    {tipo: 'escopo', dados: {caso: 'alfa', rodada: 'R001', corpus_id: 'c1', modelo: 'modelo-x'}},
    {tipo: 'etapa', dados: {numero: 1, total: 3, etapa: 'busca', tentativa: 1}},
    {tipo: 'ferramenta', dados: {acao: 'buscar', etapa: 'busca', retornados: 2, arquivo: 'log.jsonl'}},
    {tipo: 'fonte', dados: {referencia: 'R1', rodada: 'R001', documento_id: 'D1', original: 'casos/alfa/D1_contrato.pdf', pagina_pdf: 12, trecho: 'Valor global de R$ 10 mil.'}},
    {tipo: 'fonte', dados: {referencia: 'R2', rodada: 'R001', documento_id: 'D2', original: 'casos/alfa/D2_planilha.csv', linha_inicio: 4, linha_fim: 9, trecho: 'Linha da planilha.'}},
    {tipo: 'resposta', dados: {item: 'm0', texto: 'Lendo as fontes.', fase: 'commentary', rodada: 'R001'}},
    {tipo: 'resposta', dados: {item: 'm1', texto: 'O contrato vale R$ 10 mil [fonte:R1], pago em parcelas [fonte:R2]; o aditivo não aparece [fonte:R9].', fase: 'final_answer', rodada: 'R001', publicada: true}},
    {tipo: 'uso', dados: {etapa: 'busca', uso: {entrada: 10, saida: 5, cache_leitura: 0}, total: {entrada: 10, saida: 5, cache_leitura: 0}}},
    {tipo: 'publicacao', dados: {caso: 'alfa', rodada: 'R001', revisao: 'r2', geracao: 'g1', achados: 3}},
  ];
}

async function mesaEmIngles(desktop) {
  let entregue = false;
  const mesa = criarMesa({idioma: 'en', armazenamento: {'vlado-idioma': 'en'}, desktop, catalogo: [ALFA],
    url: 'http://127.0.0.1:8765/?area=codex&caso=alfa', api: operacao => {
      if (operacao === 'codex-listar') return {conversas: [{id: 'chat1', titulo: 'Merenda', estado: 'concluido'}]};
      if (operacao === 'codex-status') return {autenticado: true, provedor: 'anthropic', modelo: 'modelo-x', versao: 'v1'};
      if (operacao === 'inventario') return {caso_id: 'alfa', corpus_id: 'c1', total_documentos: 1,
        documentos: [{id: 'D1', nome_recebido: 'D1_contrato.pdf', extracao_pdf: {estado: 'parcial', paginas_pdf: 14, paginas_com_texto: 13, paginas_sem_texto: [7]}}]};
      if (operacao === 'codex-eventos') {
        const resposta = {conversa: {estado: 'concluido'}, cursor: 10, eventos: entregue ? [] : eventos(), acervos: {}};
        entregue = true; return resposta;
      }
      return {};
    }});
  await mesa.esperar(12);
  mesa.$('codex-conversa').value = 'chat1';
  mesa.$('codex-conversa').dispatchEvent(new mesa.janela.Event('change'));
  await mesa.esperar(12);
  mesa.janela.I18N.aplicar(mesa.doc.body); // the DOM double does not model MutationObserver
  return mesa;
}

function visivel(no) {
  let anterior = null;
  for (let el = no.nodeType === 3 ? no.parentElement : no; el; anterior = el, el = el.parentElement) {
    if (el.hidden || el.classList.contains('context-adapter')) return false;
    if (el.localName === 'details' && !el.open && anterior?.localName !== 'summary') return false;
    if (el.localName === 'dialog' && !el.open) return false;
  }
  return true;
}
function dado(el) {
  const container = el.closest(DADOS), ilha = el.closest('[translate="yes"]');
  return !!container && !(ilha && ilha !== container && container.contains(ilha));
}
function restosEmPortugues(mesa, raizes) {
  const restos = new Set();
  for (const raiz of raizes.map(s => mesa.doc.querySelector(s))) {
    const walker = mesa.doc.createTreeWalker(raiz, 1 | 4);
    for (let no = walker.nextNode(); no; no = walker.nextNode()) {
      if (!visivel(no)) continue;
      if (no.nodeType === 3) {
        const texto = no.data.trim();
        if (texto && !PERMITIDOS.has(texto) && !dado(no.parentElement) && PORTUGUES.test(texto)) restos.add(texto);
      } else if (!dado(no)) {
        for (const nome of ['placeholder', 'title', 'aria-label']) {
          const valor = no.getAttribute(nome);
          if (valor && PORTUGUES.test(valor)) restos.add(`${nome}: ${valor}`);
        }
      }
    }
  }
  return [...restos];
}

for (const desktop of [true, false]) {
  test(`Perguntar à IA em inglês não mostra textos de interface em português (${desktop ? 'desktop' : 'celular'})`, async () => {
    const mesa = await mesaEmIngles(desktop);
    assert.deepEqual(mesa.erros, []);
    assert.ok(mesa.$('codex-mensagens').querySelector('.source-citation'), 'a resposta foi renderizada');
    assert.deepEqual(restosEmPortugues(mesa, ['.app-header', '#mesa-sidebar', '.intro', '#mesa-etapas', '#area-codex']), []);
    // Every disclosure a reader can open: connection, sources, progress and technical details.
    for (const detalhe of mesa.$('area-codex').querySelectorAll('details')) detalhe.open = true;
    mesa.janela.I18N.aplicar(mesa.doc.body);
    assert.deepEqual(restosEmPortugues(mesa, ['#area-codex']), []);
  });
}

test('dados continuam no idioma original: pergunta, resposta, trecho e título da apuração', async () => {
  const mesa = await mesaEmIngles(true);
  assert.equal(mesa.$('codex-mensagens').querySelector('.codex-user .codex-text').textContent, 'Quanto custou a merenda escolar?');
  assert.match(mesa.$('codex-mensagens').querySelector('.codex-answer .markdown-body').textContent, /O contrato vale R\$ 10 mil/);
  assert.equal(mesa.$('fonte-R1').querySelector('blockquote').textContent, 'Valor global de R$ 10 mil.');
  assert.equal(mesa.$('area-descricao').textContent, 'Pauta Alfa');
});

test('localizadores seguem o idioma: “page 12” e “lines 4–9” em inglês', async () => {
  const mesa = await mesaEmIngles(true);
  assert.equal(mesa.$('fonte-R1').querySelector('summary').textContent, 'contrato · page 12');
  assert.equal(mesa.$('fonte-R2').querySelector('summary').textContent, 'planilha · lines 4–9');
  const chip = mesa.$('codex-mensagens').querySelector('.source-citation');
  assert.equal(chip.getAttribute('aria-label'), 'Open page 12 in the original: contrato');
  assert.equal(mesa.$('codex-mensagens').querySelector('.codex-pendente').textContent, 'Source pending');
});

test('voltar ao português refaz citações e localizadores da conversa', async () => {
  const mesa = await mesaEmIngles(true);
  mesa.janela.I18N.definir('pt');
  assert.equal(mesa.$('fonte-R1').querySelector('summary').textContent, 'contrato · p. 12');
  assert.equal(mesa.$('codex-mensagens').querySelector('.source-citation').getAttribute('aria-label'), 'Ver página 12 no original: contrato');
  assert.equal(mesa.$('codex-mensagens').querySelector('.codex-pendente').textContent, 'Fonte pendente');
});

test('placeholder da pergunta é traduzido sem tocar no texto digitado', async () => {
  const mesa = await mesaEmIngles(true);
  const campo = mesa.$('codex-pergunta');
  assert.equal(campo.getAttribute('placeholder'), 'What do the documents allow us to state about…?');
  campo.value = 'Texto digitado pelo jornalista';
  mesa.janela.I18N.aplicar(mesa.doc.body);
  assert.equal(campo.value, 'Texto digitado pelo jornalista');
});
