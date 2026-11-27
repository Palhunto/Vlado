'use strict';
// Suporte só da IA (componentes.md#suporte-so-da-ia; CONTRATO_QUADROS_ONDA4.md, seção 3.2): nada no quadro usa a aparência da conferência humana quando o suporte
// vem só da revisão da IA (`suporte_so_da_ia`). Dados sintéticos (Vila Serena, Construtora Alfa, Marta Reis).
const test = require('node:test');
const assert = require('node:assert/strict');
const {criarMesa, Evento, PILHA} = require('./dom_minimo.cjs');

const ALFA = 'P' + 'a'.repeat(32), MARTA = 'P' + 'b'.repeat(32);
const ref = n => ({tipo: 'ia', caso_id: 'alpha', rodada: 'R002', revisao: 'r3_sintese', registros_sha256: '7'.repeat(64), evidencia_id: `E00${n}`});
const vinculo = (n, extra = {}) => ({referencia: ref(n), papel: 'suporte', suporte: 'sustentado', natureza: 'declaracao_documental', justificativa: 'Lista Marta Reis como sócia.', documento_id: 'D002', estado: 'conferida', erro: null,
  localizador: {legivel: 'D002 · p. 1'}, evidencia: {documento: {documento_id: 'D002', nome: 'contrato_social_alfa.pdf'}, trecho: `Trecho ${n}`, localizador: {legivel: 'D002 · p. 1', pagina_pdf: 1}},
  revisao_ia: {suporte: 'sustentado', natureza: 'declaracao_documental', destino: 'incluido'}, alteracoes: {}, conferencia_humana: null, suporte_so_da_ia: true, ...extra});
const SO_IA = n => vinculo(n);
const HUMANO = n => vinculo(n, {suporte_so_da_ia: false, conferencia_humana: {estado: 'conferida_no_original', por: 'Ana Lima', em_utc: '2026-11-26T19:10:00+00:00'}});
const hip = (id, sustentam, extra = {}) => ({id, enunciado: `Hipótese ${id}`, situacao: 'em_aberto', condicao: 'com_evidencia', natureza: 'declaracao_documental', situacao_sem_base: false, sustentam, contrariam: [], faltam: [], contexto: [], indisponiveis: [], ...extra});

function montar({hipoteses = [], relacoes = []} = {}) {
  const m = criarMesa({scripts: [...PILHA, 'quadros.js', 'sugestoes.js', 'formularios.js', 'analise.js', 'indicador_salvamento.js'], desktop: true,
    api: operacao => {
      if (operacao === 'hipoteses-quadro') return {caso: 'alpha', total: hipoteses.length, divergentes: [], aviso: '', hipoteses};
      if (operacao === 'mapa-ver') return {caso: 'alpha', aviso: '', homonimos: [], relacoes, entidades: [
        {id: ALFA, nome: 'Construtora Alfa Ltda.', tipo: 'organizacao', situacao: 'com_evidencia', identificadores: []}, {id: MARTA, nome: 'Marta Reis', tipo: 'pessoa', situacao: 'com_evidencia', identificadores: []}]};
      return {};
    },
    preparar: janela => {
      const original = janela.fetch;
      janela.fetch = async (rota, opcoes) => String(rota) === '/api/integracao' ? {ok: true, json: async () => ({quadros_evidencia: true})} : original(rota, opcoes);
    }});
  m.avaliar('window.contextoCaso = () => "alpha";');
  return m;
}
const espera = async m => { await new Promise(r => setTimeout(r, 12)); await m.esperar(10); };
const texto = no => no.textContent.replace(/\s+/g, ' ').trim();
async function abrirAba(m, aba) { m.$('ver-quadros').click(); await espera(m); m.$(`quadros-aba-${aba}`).click(); await espera(m); }
const relacao = evidencias => ({id: 'L' + 'c'.repeat(32), sha256: 'd'.repeat(64), origem: MARTA, destino: ALFA, tipo: 'sócia', descricao: '', evidencias, situacao: 'documentada', entidades_disponiveis: true, retirado: false, motivo_retirada: ''});

test('hipótese: base só da IA diz "Com evidência sustentada pela revisão da IA" na pílula da P20a; com base humana, "Com evidência conferida"', async () => {
  const m = montar({hipoteses: [hip('H1', [SO_IA(1)]), hip('H2', [HUMANO(2)]), hip('H3', [SO_IA(3), HUMANO(4)])]}); await abrirAba(m, 'hipoteses');
  const cartoes = [...m.$('quadros-hipoteses').querySelectorAll('.quadro-hipotese')];
  const condicao = c => c.querySelector('.quadro-condicao');
  assert.match(texto(condicao(cartoes[0])), /^Com evidência sustentada pela revisão da IA$/);
  assert.ok(condicao(cartoes[0]).classList.contains('ai-support'), 'forma da P20a (tracejado, sem fundo)');
  assert.doesNotMatch(texto(cartoes[0].querySelector('.quadro-meta')), /Com evidência conferida/);
  assert.match(texto(condicao(cartoes[1])), /^Com evidência conferida$/);
  assert.match(texto(condicao(cartoes[2])), /^Com evidência conferida$/, 'havendo base humana, vale a condição de sempre');
});

test('a coluna da hipótese mostra "IA · sustentado" no suporte só da IA e o selo da avaliação no resto', async () => {
  const m = montar({hipoteses: [hip('H1', [SO_IA(1), HUMANO(2)])]}); await abrirAba(m, 'hipoteses');
  const itens = [...m.$('quadros-hipoteses').querySelectorAll('.coluna-sustenta .quadro-evidencia')];
  assert.match(texto(itens[0]), /IA · sustentado/); assert.doesNotMatch(texto(itens[0]), /Avaliação: sustentado/);
  assert.equal(itens[0].querySelector('.quadro-selo.suporte-sustentado'), null);
  assert.match(texto(itens[1]), /Avaliação: sustentado/);
});

test('painel da ligação: "✓ n evidências conferidas no original" só para o que pessoa conferiu; o resto na pílula "IA · n sustentadas"; havendo as duas, as duas', async () => {
  const m = montar({relacoes: [relacao([SO_IA(1), SO_IA(2), HUMANO(3)])]}); await abrirAba(m, 'mapa');
  m.$('quadros-mapa').querySelector('.mapa-ligacao').dispatchEvent(new Evento('click', {bubbles: true}));
  const selos = m.$('quadros-mapa').querySelector('.mapa-selos');
  assert.ok(selos, 'selos do painel');
  const [humano, ia] = [...selos.children];
  assert.match(texto(humano), /^✓ 1 evidência conferida no original$/);
  assert.ok(humano.classList.contains('human-review-badge'));
  assert.match(texto(ia), /^IA · 2 evidências sustentadas$/);
  assert.ok(ia.classList.contains('ai-support'), 'sem fundo, borda tracejada, sem sinal');
});

test('painel da ligação só com suporte da IA: nenhuma marca de conferência humana', async () => {
  const m = montar({relacoes: [relacao([SO_IA(1), SO_IA(2)])]}); await abrirAba(m, 'mapa');
  m.$('quadros-mapa').querySelector('.mapa-ligacao').dispatchEvent(new Evento('click', {bubbles: true}));
  const detalhe = m.$('quadros-mapa').querySelector('.mapa-detalhe');
  assert.match(texto(detalhe.querySelector('.mapa-selos')), /^IA · 2 evidências sustentadas$/);
  assert.doesNotMatch(texto(detalhe), /conferid[ao]s? no original|✓/);
  assert.equal(detalhe.querySelector('.human-review-badge'), null);
});

test('um só vínculo só da IA: singular', async () => {
  const m = montar({relacoes: [relacao([SO_IA(1)])]}); await abrirAba(m, 'mapa');
  m.$('quadros-mapa').querySelector('.mapa-ligacao').dispatchEvent(new Evento('click', {bubbles: true}));
  assert.match(texto(m.$('quadros-mapa').querySelector('.mapa-selos')), /^IA · 1 sustentada$/);
});
