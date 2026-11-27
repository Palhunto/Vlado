'use strict';
// "Confirmado por Ana Lima em 27/11, às 10h05, a partir de sugestão da IA" no painel do item (componentes.md#sugestao-ia; interface/sugestoes.js, quadros.js, analise.js),
// com dados sintéticos. O servidor simulado devolve as sugestões confirmadas só quando o pedido manda incluir_decididas (CONTRATO_QUADROS_ONDA4.md, 2.1).
const test = require('node:test');
const assert = require('node:assert/strict');
const {criarMesa, PILHA} = require('./dom_minimo.cjs');

const ALFA = 'P' + 'a'.repeat(32), MARTA = 'P' + 'b'.repeat(32), REL = 'R' + 'c'.repeat(32);
const decisao = (acao, item, quadro, por = 'Ana Lima') => ({acao, por, conta_id: 'c1', em_utc: '2026-11-27T10:05:00', item_id: item, quadro, ...(acao === 'corrigir' ? {alterados: ['nome']} : {})});
const confirmada = (n, tipo, quadro, d) => ({id: 'S' + String(n).repeat(32), tipo, quadro, campos: {}, evidencias: [], achado: {id: 'A002', versao: 1, destino: 'incluido', versao_atual: 1}, analise: {rodada: 'R002', pergunta: 'Quem?'},
  estado: 'confirmada', decisao: d, descartada_antes: null, bloqueio: null, avisos: []});
const SUGESTOES = [confirmada(1, 'hipotese', 'hipoteses', decisao('confirmar', 'H1', 'hipoteses')), confirmada(2, 'acontecimento', 'linha_tempo', decisao('confirmar', 'T1', 'linha_tempo')),
  confirmada(3, 'organizacao', 'mapa', decisao('corrigir', ALFA, 'mapa')), confirmada(4, 'ligacao', 'mapa', decisao('confirmar', REL, 'mapa', 'Carlos Prado'))];
const TIPOS = {fato: 'Data do fato (ocorrência)'};
const hip = id => ({id, enunciado: `Hipótese ${id}`, situacao: 'em_aberto', condicao: 'pendencia', natureza: null, situacao_sem_base: false, sustentam: [], contrariam: [], faltam: [], contexto: [], indisponiveis: []});
const ev = id => ({evento_id: id, sha256: 'e'.repeat(64), descricao: `Evento ${id}`, data: {tipo: 'fato', valor: '2025-02-10', precisao: 'dia', aproximada: false, fonte: 0, observacao: '', rotulo: TIPOS.fato},
  fonte_da_data: null, fonte_conferida: false, evidencias: [], divergente: false, divergencia: null, retirado: false, motivo_retirada: ''});
const MAPA = {caso: 'alpha', aviso: '', homonimos: [], entidades: [{id: ALFA, nome: 'Construtora Alfa Ltda.', tipo: 'organizacao', situacao: 'com_evidencia', identificadores: []}, {id: MARTA, nome: 'Marta Reis', tipo: 'pessoa', situacao: 'com_evidencia', identificadores: []}],
  relacoes: [{id: REL, origem: MARTA, destino: ALFA, tipo: 'sócia', descricao: '', evidencias: [], situacao: 'documentada', entidades_disponiveis: true}]};

function montar({incluirDecididas = true} = {}) {
  const pedidos = [];
  const m = criarMesa({scripts: [...PILHA, 'quadros.js', 'sugestoes.js', 'analise.js', 'indicador_salvamento.js'], desktop: true,
    api: (operacao, dados) => {
      if (operacao === 'mapa-ver') return MAPA;
      if (operacao === 'linha-tempo-listar') return {caso: 'alpha', total: 2, divergencias: [], fontes_indisponiveis: [], divergentes: [], tipos_data: TIPOS, aviso: '', entradas: [ev('T1'), ev('T2')]};
      if (operacao === 'hipoteses-quadro') return {caso: 'alpha', total: 2, divergentes: [], aviso: '', hipoteses: [hip('H1'), hip('H2')]};
      if (operacao === 'sugestoes-listar') {
        pedidos.push(dados);
        const lista = SUGESTOES.filter(s => s.quadro === dados.quadro && (dados.incluir_decididas || s.estado !== 'confirmada'));
        return {caso: 'alpha', quadro: dados.quadro, contagem: {abertas: 0, descartadas: 0}, sugestoes: incluirDecididas ? lista : []};
      }
      return {};
    },
    preparar: janela => {
      const original = janela.fetch;
      janela.fetch = async (rota, opcoes) => String(rota) === '/api/integracao' ? {ok: true, json: async () => ({quadros_evidencia: true})} : original(rota, opcoes);
    }});
  m.avaliar('window.contextoCaso = () => "alpha";');
  return {...m, pedidos};
}
const espera = async m => { await new Promise(r => setTimeout(r, 10)); await m.esperar(10); };
async function abrirAba(m, aba) { m.$('ver-quadros').click(); await espera(m); m.$(`quadros-aba-${aba}`).click(); await espera(m); }
const texto = no => no.textContent.replace(/\s+/g, ' ').trim();

test('hipótese e acontecimento nascidos de sugestão levam a nota de quem decidiu; os demais não', async () => {
  const m = montar();
  await abrirAba(m, 'hipoteses');
  const cartoes = [...m.$('quadros-hipoteses').querySelectorAll('.quadro-hipotese')];
  const notas = [...m.$('quadros-hipoteses').querySelectorAll('.sugestao-origem')];
  assert.equal(notas.length, 1, cartoes.length + ' hipóteses, uma nasceu de sugestão');
  assert.equal(texto(notas[0]), 'Confirmado por Ana Lima em 27/11, às 10h05, a partir de sugestão da IA');
  assert.equal(notas[0].querySelector('[translate=no]').textContent, 'Ana Lima', 'o nome da pessoa é dado, fora da tradução');
  assert.ok(m.pedidos.every(p => p.incluir_decididas === true), 'o pedido traz as confirmadas');
  await abrirAba(m, 'tempo');
  const tempo = [...m.$('quadros-tempo').querySelectorAll('.sugestao-origem')];
  assert.equal(tempo.length, 1);
  assert.match(texto(tempo[0]), /^Confirmado por Ana Lima em 27\/11, às 10h05/);
  assert.deepEqual(m.erros, []);
});

test('mapa: a entidade corrigida na confirmação diz "Corrigido por"; a ligação mostra a nota no painel dela', async () => {
  const m = montar();
  await abrirAba(m, 'mapa');
  const painel = m.$('quadros-mapa');
  const notas = [...painel.querySelectorAll('.mapa-entidade .sugestao-origem')];
  assert.equal(notas.length, 1);
  assert.equal(texto(notas[0]), 'Corrigido por Ana Lima em 27/11, às 10h05, a partir de sugestão da IA');
  const ver = painel.querySelector('button[data-relacao]');
  assert.ok(ver, 'a ligação tem o botão Ver evidências');
  ver.click(); await espera(m);
  assert.match(texto(painel.querySelector('.mapa-detalhe')), /Confirmado por Carlos Prado em 27\/11, às 10h05, a partir de sugestão da IA/);
  assert.deepEqual(m.erros, []);
});

test('servidor sem sugestões confirmadas (ou antigo): nenhum item ganha a nota', async () => {
  const m = montar({incluirDecididas: false});
  await abrirAba(m, 'hipoteses');
  assert.equal(m.$('quadros-hipoteses').querySelectorAll('.sugestao-origem').length, 0);
});
