'use strict';
// "Ligar outra evidência" no painel da afirmação da conferência do texto (P47; componentes.md#seletor-evidencia): o seletor comum abre no painel, com "Voltar à afirmação",
// a fonte do caderno pede a natureza antes de "Ligar", e ligar substitui os vínculos da afirmação pelos de agora mais o novo (redacao-vincular). Dados sintéticos.
const test = require('node:test');
const assert = require('node:assert/strict');
const {criarMesa, PILHA} = require('./dom_minimo.cjs');

const REF = n => ({tipo: 'ia', caso_id: 'alfa', rodada: 'R001', revisao: 'r3_sintese', registros_sha256: '7'.repeat(64), evidencia_id: `E00${n}`});
const HUMANA = {tipo: 'humana', caso_id: 'alfa', registro_id: 'N' + 'b'.repeat(32), sha256: 'c'.repeat(64), fonte: 1};
const VISAO = {caso: 'alfa', id: 'C' + 'a'.repeat(32), sha256: 'b'.repeat(64), titulo: 'Reportagem sintética', texto: 'A fonte declara valor 12.', versao: 1,
  resumo: {total: 1, por_estado: {sem_suporte: 0, suporte_parcial: 0, suportada: 1, revisada_por_humano: 0}, com_sinais: 0, reabertas: 0}, versoes: [], aviso: 'Sinais.',
  afirmacoes: [{id: 'F' + '1'.repeat(32), texto: 'A fonte declara valor 12.', inicio: 0, fim: 25, estado: 'suportada', estado_automatico: 'suportada', sinais: [], reaberta: false, revisao_humana: null,
    evidencias: [{referencia: REF(1), papel: 'suporte', suporte: 'sustentado', natureza: 'declaracao_documental', justificativa: 'Declara.', estado: 'conferida', evidencia: {trecho: 'A fonte declara valor 12.'}}]}]};
const BUSCA = {caso: 'alfa', analise: {rodada: 'R001', em_utc: '2026-11-26T17:32:00+00:00', pergunta: '?'}, analises: [], total: 1, resultados: [
  {origem: 'caderno', tipo_fonte: 'trecho', texto: 'Anotação sobre o valor.', trecho: 'Valor 12 confirmado.', documento: {documento_id: 'D001', nome: 'nota.txt'}, localizador: {legivel: 'D001 · linha 3'},
   achado: null, revisao_ia: null, conferencia_humana: null, estado: 'conferida', vinculo_sugerido: {referencia: HUMANA, papel: 'suporte', suporte: 'nao_revisado', natureza: null, justificativa: ''}, ja_ligado: false}]};

function montar({vincularFalha = null} = {}) {
  const m = criarMesa({scripts: [...PILHA, 'quadros.js', 'sugestoes.js', 'redacao.js'], desktop: true,
    api: (op, dados) => {
      if (op === 'redacao-listar') return {caso: 'alfa', textos: [{id: VISAO.id, titulo: VISAO.titulo, versao: 1, resumo: VISAO.resumo}], divergentes: []};
      if (op === 'redacao-conferir') return structuredClone(VISAO);
      if (op === 'evidencia-buscar') return structuredClone(BUSCA);
      if (op === 'redacao-vincular') { if (vincularFalha) throw new Error(vincularFalha); return structuredClone(VISAO); }
      return {};
    },
    preparar: janela => {
      const original = janela.fetch;
      janela.fetch = async (rota, opcoes) => String(rota) === '/api/integracao' ? {ok: true, json: async () => ({quadros_evidencia: true, conferencia_redacao: true})} : original(rota, opcoes);
    }});
  m.avaliar('window.contextoCaso = () => "alfa";');
  return m;
}
const espera = async m => { await new Promise(r => setTimeout(r, 12)); await m.esperar(10); };
const texto = no => no.textContent.replace(/\s+/g, ' ').trim();
const por = (raiz, seletor, rotulo) => [...raiz.querySelectorAll(seletor)].find(b => texto(b) === rotulo);
async function abrirAfirmacao(m) {
  m.$('ver-quadros').click(); await espera(m);
  const aba = [...m.$('quadros-abas').querySelectorAll('[role=tab]')].find(b => /conferência do texto|redação/i.test(b.textContent));
  aba.click(); await espera(m);
  const painel = m.$(aba.getAttribute('aria-controls'));
  painel.querySelector('.redacao-textos button').click(); await espera(m);
  painel.querySelector('.redacao-afirmacao').click(); await espera(m);
  return painel;
}

test('o painel da afirmação oferece "Ligar outra evidência" e o seletor abre no lugar dele, com "Voltar à afirmação"', async () => {
  const m = montar(); const painel = await abrirAfirmacao(m);
  const ligar = por(painel, 'button', '+ Ligar outra evidência');
  assert.ok(ligar, 'botão no painel da afirmação');
  ligar.click(); await espera(m);
  assert.ok(painel.querySelector('.seletor-evidencia'), 'seletor aberto');
  assert.ok(!painel.querySelector('.redacao-painel'), 'no lugar do painel');
  assert.match(texto(painel.querySelector('.seletor-voltar')), /Voltar à afirmação/);
  painel.querySelector('.seletor-voltar').click(); await espera(m);
  assert.ok(painel.querySelector('.redacao-painel'), 'volta ao painel da afirmação');
});

test('fonte do caderno: a natureza é escolhida antes de "Ligar"; ligar manda os vínculos de agora mais o novo para redacao-vincular', async () => {
  const m = montar(); const painel = await abrirAfirmacao(m);
  por(painel, 'button', '+ Ligar outra evidência').click(); await espera(m);
  painel.querySelector('.seletor-resultado').click(); await espera(m);
  const ligarBtn = por(painel, '.seletor-aberto button', 'Ligar');
  assert.ok(ligarBtn.disabled === true, 'sem natureza, Ligar não habilita');
  assert.match(texto(painel.querySelector('.seletor-aberto')), /Falta a natureza\. Escolha o que a fonte é: declaração documental, alegação atribuída, inferência ou pendência\./);
  const sel = painel.querySelector('.seletor-natureza'); sel.value = 'alegacao_atribuida'; sel.dispatchEvent(new (require('./dom_minimo.cjs').Evento)('change', {bubbles: true}));
  assert.ok(ligarBtn.disabled === false);
  ligarBtn.click(); await espera(m);
  const chamada = m.chamadas.find(c => c.operacao === 'redacao-vincular');
  assert.ok(chamada, 'redacao-vincular');
  const d = chamada.dados;
  assert.equal(d.caso, 'alfa'); assert.equal(d.id, VISAO.id); assert.equal(d.anterior_sha256, VISAO.sha256); assert.equal(d.afirmacao_id, 'F' + '1'.repeat(32));
  assert.match(d.requisicao_id, /^[0-9a-f]{32}$/);
  assert.equal(d.evidencias.length, 2);
  assert.equal(JSON.stringify(d.evidencias[0]), JSON.stringify({referencia: REF(1), papel: 'suporte', suporte: 'sustentado', natureza: 'declaracao_documental', justificativa: 'Declara.'}));
  assert.equal(JSON.stringify(d.evidencias[1]), JSON.stringify({referencia: HUMANA, papel: 'suporte', suporte: 'nao_revisado', natureza: 'alegacao_atribuida', justificativa: ''}));
  assert.ok(painel.querySelector('.redacao-painel'), 'recarregou a afirmação');
});

test('ligar recusado pelo servidor: volta à afirmação com o erro', async () => {
  const m = montar({vincularFalha: 'O registro mudou. Atualize antes de salvar.'}); const painel = await abrirAfirmacao(m);
  por(painel, 'button', '+ Ligar outra evidência').click(); await espera(m);
  painel.querySelector('.seletor-resultado').click(); await espera(m);
  const sel = painel.querySelector('.seletor-natureza'); sel.value = 'pendencia'; sel.dispatchEvent(new (require('./dom_minimo.cjs').Evento)('change', {bubbles: true}));
  por(painel, '.seletor-aberto button', 'Ligar').click(); await espera(m);
  assert.ok(painel.querySelector('.redacao-painel'));
  assert.match(texto(painel), /Não deu para ligar: O registro mudou\. Atualize antes de salvar\./);
});
