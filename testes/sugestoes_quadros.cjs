'use strict';
// Sugestões da IA nos quadros (P45, componentes.md#sugestao-ia; interface/sugestoes.js, analise.js, quadros.js), com dados sintéticos
// (Vila Serena, Construtora Alfa, Marta Reis) no formato de CONTRATO_QUADROS_ONDA4.md, seção 2.1. O servidor é simulado: o estado das sugestões muda
// com confirmar, descartar e restaurar, como mudaria no servidor.
const test = require('node:test');
const assert = require('node:assert/strict');
const {criarMesa, Evento, PILHA} = require('./dom_minimo.cjs');

const ALFA = 'P' + 'a'.repeat(32);
const SID = n => 'S' + String(n).repeat(32);
const ANALISE = {caso: 'alpha', rodada: 'R002', revisao: 'r3_sintese', registros_sha256: '7'.repeat(64), em_utc: '2026-11-26T17:32:00+00:00', pergunta: 'Quem são os sócios da contratada?'};
const ACHADO = {id: 'A002', versao: 1, redacao: 'Marta Reis é sócia-administradora da Construtora Alfa.', natureza: 'declaracao_documental', suporte_ia: 'sustentado', destino: 'incluido', motivo_destino: '', versao_atual: 1};
const referencia = n => ({tipo: 'ia', caso_id: 'alpha', rodada: 'R002', revisao: 'r3_sintese', registros_sha256: '7'.repeat(64), evidencia_id: `E00${n}`});
const salvo = n => ({referencia: referencia(n), papel: 'suporte', suporte: 'sustentado', natureza: 'declaracao_documental', justificativa: 'O contrato social lista Marta Reis como sócia-administradora.'});
const resolvida = (n, extra = {}) => ({referencia: referencia(n), estado: 'conferida', documento: {documento_id: 'D002', nome: 'contrato_social_alfa.pdf'},
  localizador: {tipo: 'linhas', pagina_pdf: 1, linha_inicio: 12, linha_fim: 14, descricao: '', legivel: 'D002 · página PDF 1 · linhas 12–14'}, trecho: 'Marta Reis, sócia-administradora…',
  revisao_ia: {suporte: 'sustentado', natureza: 'declaracao_documental', papel: 'suporte', destino: 'incluido'}, conferencia_humana: null, ...extra});
const base = (n, tipo, quadro, campos, extra = {}) => ({id: SID(n), tipo, quadro, campos: {...campos, evidencias: [salvo(3)]}, evidencias: [resolvida(3)], achado: ACHADO, analise: ANALISE,
  estado: 'aberta', decisao: null, descartada_antes: null, bloqueio: null, avisos: [], ...extra});
const PESSOA = () => base(1, 'pessoa', 'mapa', {tipo: 'pessoa', nome: 'Marta Reis', variantes: [], identificadores: []});
const LIGACAO = () => base(2, 'ligacao', 'mapa', {origem: null, destino: ALFA, tipo: 'sócia', descricao: 'Sócia-administradora.'},
  {pontas: {origem: {sugestao_id: SID(1), estado: 'aberta', item_id: null, nome: 'Marta Reis'}, destino: {sugestao_id: SID(0), estado: 'confirmada', item_id: ALFA, nome: 'Construtora Alfa Ltda.'}}, bloqueio: 'ponta_ainda_sugestao'});
const EVENTO = () => base(3, 'acontecimento', 'linha_tempo', {descricao: 'Assinatura do Contrato 041/2025', datas: [{tipo: 'assinatura', valor: '2025-03-03', aproximada: false, fonte: 0, observacao: ''}],
  retirado: false, motivo_retirada: ''});
const HIPOTESE = () => base(4, 'hipotese', 'hipoteses', {enunciado: 'A sócia da contratada assinou o contrato também como testemunha.', situacao: 'em_aberto', lacunas: []});

const TIPOS = {assinatura: 'Data de assinatura', fato: 'Data do fato (ocorrência)'};
const entrada = (id, tipo, valor, precisao) => ({evento_id: id, sha256: 'e'.repeat(64), descricao: `Evento ${id}`, data: {tipo, valor, precisao, aproximada: false, fonte: 0, observacao: '', rotulo: TIPOS[tipo]},
  fonte_da_data: null, fonte_conferida: false, evidencias: [], divergente: false, divergencia: null, retirado: false, motivo_retirada: ''});
const MAPA = {caso: 'alpha', aviso: '', homonimos: [], relacoes: [], entidades: [{id: ALFA, nome: 'Construtora Alfa Ltda.', tipo: 'organizacao', situacao: 'com_evidencia', identificadores: []}]};
const hip = (id, situacao) => ({id, enunciado: `Hipótese ${id}`, situacao, condicao: 'pendencia', natureza: null, situacao_sem_base: false, sustentam: [], contrariam: [], faltam: [], contexto: [], indisponiveis: []});

function montar({sugestoes, quando = {}, permissao = true, listarFalha = false, confirmarFalha = null} = {}) {
  const estado = sugestoes.map(s => ({...s}));
  const m = criarMesa({scripts: [...PILHA, 'quadros.js', 'sugestoes.js', 'analise.js', 'indicador_salvamento.js'], desktop: true,
    api: (operacao, dados) => {
      if (operacao === 'mapa-ver') return MAPA;
      if (operacao === 'linha-tempo-listar') return {caso: 'alpha', total: 2, divergencias: [], fontes_indisponiveis: [], divergentes: [], tipos_data: TIPOS, aviso: '',
        entradas: [entrada('T1', 'fato', '2025-02-10', 'dia'), entrada('T2', 'fato', '2025-06-01', 'dia')]};
      if (operacao === 'hipoteses-quadro') return {caso: 'alpha', total: 2, divergentes: [], aviso: '', hipoteses: [hip('H1', 'sustentada'), hip('H2', 'em_aberto')]};
      if (operacao === 'sugestoes-listar') {
        if (listarFalha) throw Object.assign(new Error('Operação desconhecida.'), {result: {erro: 'Operação desconhecida.', codigo: 'operacao_desconhecida'}});
        const lista = estado.filter(s => s.quadro === dados.quadro && s.estado !== 'confirmada');
        return {caso: 'alpha', quadro: dados.quadro, contagem: {abertas: lista.filter(s => s.estado === 'aberta').length, descartadas: lista.filter(s => s.estado === 'descartada').length}, sugestoes: lista};
      }
      const alvo = estado.find(s => s.id === dados.id);
      if (operacao === 'sugestoes-confirmar') {
        if (confirmarFalha) throw Object.assign(new Error(confirmarFalha.erro), {result: confirmarFalha});
        alvo.estado = 'confirmada'; return {sugestao: alvo, item: {id: alvo.tipo === 'pessoa' ? 'P' + 'f'.repeat(32) : 'T' + 'f'.repeat(32)}};
      }
      if (operacao === 'sugestoes-descartar') { alvo.estado = 'descartada'; return {sugestao: alvo, item: null}; }
      if (operacao === 'sugestoes-restaurar') { alvo.estado = 'aberta'; return {sugestao: alvo, item: null}; }
      return {};
    },
    preparar: janela => {
      const original = janela.fetch;
      janela.fetch = async (rota, opcoes) => String(rota) === '/api/integracao' ? {ok: true, json: async () => ({quadros_evidencia: true})} : original(rota, opcoes);
    }});
  m.avaliar('window.contextoCaso = () => "alpha";');
  if (!permissao) m.avaliar('window.Sessao = {pode: () => false, pronta: Promise.resolve()};');
  return m;
}
const espera = async m => { await new Promise(r => setTimeout(r, 10)); await m.esperar(10); };
async function abrirAba(m, aba) { m.$('ver-quadros').click(); await espera(m); if (aba) { m.$(`quadros-aba-${aba}`).click(); await espera(m); } }
const texto = no => no.textContent.replace(/\s+/g, ' ').trim();

test('mapa: a sugestão entra no desenho com os três sinais, fora da contagem de itens, e a legenda e a lista a trazem', async () => {
  const m = montar({sugestoes: [PESSOA(), LIGACAO()]}); await abrirAba(m, 'mapa');
  const painel = m.$('quadros-mapa');
  const no = painel.querySelector('.mapa-no.is-sugestao');
  assert.ok(no, 'nó tracejado da sugestão');
  assert.ok(no.classList.contains('pessoa'));
  assert.equal(no.getAttribute('aria-label'), 'Sugestão da IA: Marta Reis, pessoa', 'o nome acessível começa pela origem');
  assert.ok(no.querySelector('.selo-sugestao'), 'selo "IA · sugestão" dentro do nó');
  assert.equal(no.querySelector('.selo-sugestao').getAttribute('aria-hidden'), 'true', 'o selo não repete na leitura');
  assert.match(no.querySelector('.selo-sugestao').textContent, /IA · sugestão/);
  const ligacao = painel.querySelector('.mapa-ligacao.is-sugestao');
  assert.ok(ligacao, 'ligação tracejada entre a sugestão e a entidade já no mapa');
  assert.equal(ligacao.getAttribute('aria-label'), 'Sugestão da IA: Marta Reis — sócia — Construtora Alfa Ltda.');
  assert.match(texto(painel.querySelector('.mapa-pilula.is-sugestao')), /IA · sócia/);
  assert.match(texto(painel.querySelector('.mapa-legenda')), /Sugestão da IA/);
  const conta = texto(painel.querySelector('.quadro-conta'));
  assert.match(conta, /1 pessoa ou organização · 0 ligações/, 'a contagem não inclui sugestões');
  assert.match(conta, /, 2 sugestões da IA/);
  const itens = [...painel.querySelectorAll('.sugestoes-secao .sugestao-abrir')];
  assert.equal(itens.length, 2, 'lista das sugestões (a leitura abaixo de 1024 px)');
  assert.deepEqual(m.erros, []);
});

test('mapa: o painel diz o que a IA propõe, com a evidência e a origem, e nada o apresenta como conferido', async () => {
  const m = montar({sugestoes: [PESSOA()]}); await abrirAba(m, 'mapa');
  m.$('quadros-mapa').querySelector('.mapa-no.is-sugestao').dispatchEvent(new Evento('click', {bubbles: true}));
  const p = m.$('quadros-mapa').querySelector('.sugestao-painel');
  assert.ok(p, 'painel aberto');
  assert.match(texto(p), /Sugestão da IA/);
  assert.match(texto(p.querySelector('.sugestao-titulo')), /^Marta Reis · pessoa$/);
  assert.match(texto(p), /Marta Reis, sócia-administradora…/);
  assert.match(texto(p), /contrato_social_alfa\.pdf, D002 · página PDF 1 · linhas 12–14/);
  assert.match(texto(p), /IA · sustentado/);
  assert.match(texto(p), /Declaração documental/);
  assert.match(texto(p), /Da análise de \d\d\/\d\d, às \d+h\d\d/);
  assert.match(texto(p), /Ver a pergunta/);
  assert.match(texto(p), /Confirmar põe a sugestão no quadro\. A conferência no original continua no achado\./);
  assert.doesNotMatch(texto(p), /Conferido no original|✓/);
  assert.equal(p.querySelector('blockquote').getAttribute('translate'), 'no');
  const botoes = [...p.querySelectorAll('.sugestao-acoes button')].map(b => b.textContent);
  assert.deepEqual(botoes, ['Confirmar', 'Descartar'], 'Corrigir entra com os formulários');
});

test('ligação com uma ponta ainda sugestão: Confirmar fica indisponível, com a razão ligada por aria-describedby', async () => {
  const m = montar({sugestoes: [PESSOA(), LIGACAO()]}); await abrirAba(m, 'mapa');
  m.$('quadros-mapa').querySelector('.mapa-ligacao.is-sugestao').dispatchEvent(new Evento('click', {bubbles: true}));
  const p = m.$('quadros-mapa').querySelector('.sugestao-painel');
  const confirmar = [...p.querySelectorAll('.sugestao-acoes button')].find(b => b.textContent === 'Confirmar');
  assert.ok(confirmar.disabled === true);
  const razao = m.doc.getElementById(confirmar.getAttribute('aria-describedby'));
  assert.match(texto(razao), /Confirme antes Marta Reis, a outra ponta da ligação\./);
  const descartar = [...p.querySelectorAll('.sugestao-acoes button')].find(b => b.textContent === 'Descartar');
  assert.ok(descartar.disabled === false, 'Descartar continua ativo');
});

test('confirmar chama a rota com requisicao_id, recarrega o quadro e anuncia; a sugestão sai da lista', async () => {
  const m = montar({sugestoes: [PESSOA()]}); await abrirAba(m, 'mapa');
  m.$('quadros-mapa').querySelector('.mapa-no.is-sugestao').dispatchEvent(new Evento('click', {bubbles: true}));
  [...m.$('quadros-mapa').querySelectorAll('.sugestao-acoes button')].find(b => b.textContent === 'Confirmar').click();
  await espera(m);
  const chamada = m.chamadas.find(c => c.operacao === 'sugestoes-confirmar');
  assert.ok(chamada, 'rota de confirmar');
  assert.equal(chamada.dados.id, SID(1)); assert.equal(chamada.dados.caso, 'alpha');
  assert.match(chamada.dados.requisicao_id, /^[0-9a-f]{32}$/);
  assert.equal(m.$('quadros-mapa').querySelectorAll('.mapa-no.is-sugestao').length, 0, 'a sugestão deixou o desenho');
  assert.match(texto(m.$('quadros-anuncio')), /Sugestão confirmada: Marta Reis entrou no quadro\./);
  assert.equal(m.$('quadros-anuncio').getAttribute('role'), 'status');
});

test('confirmar recusado: o erro aparece no painel com role=alert e a sugestão continua aberta', async () => {
  const m = montar({sugestoes: [PESSOA()], confirmarFalha: {erro: 'A evidência não está mais publicada.', codigo: 'evidencia_indisponivel'}}); await abrirAba(m, 'mapa');
  m.$('quadros-mapa').querySelector('.mapa-no.is-sugestao').dispatchEvent(new Evento('click', {bubbles: true}));
  const confirmar = () => [...m.$('quadros-mapa').querySelectorAll('.sugestao-acoes button')].find(b => b.textContent === 'Confirmar');
  confirmar().click(); await espera(m);
  const erro = m.$('quadros-mapa').querySelector('.sugestao-erro');
  assert.equal(erro.getAttribute('role'), 'alert'); assert.ok(erro.hidden === false);
  assert.match(texto(erro), /Não deu para confirmar: A evidência não está mais publicada\./);
  assert.equal(m.$('quadros-mapa').querySelectorAll('.mapa-no.is-sugestao').length, 1, 'continua sugestão');
  assert.ok(confirmar().disabled === false, 'o botão volta a funcionar');
});

test('descartar vai para "Descartadas (n)" e Restaurar a devolve como sugestão', async () => {
  const m = montar({sugestoes: [PESSOA()]}); await abrirAba(m, 'mapa');
  m.$('quadros-mapa').querySelector('.mapa-no.is-sugestao').dispatchEvent(new Evento('click', {bubbles: true}));
  [...m.$('quadros-mapa').querySelectorAll('.sugestao-acoes button')].find(b => b.textContent === 'Descartar').click();
  await espera(m);
  assert.equal(m.$('quadros-mapa').querySelectorAll('.mapa-no.is-sugestao').length, 0);
  assert.match(texto(m.$('quadros-anuncio')), /Sugestão descartada\. Ela fica em Descartadas, com Restaurar\./);
  const caixa = m.$('quadros-mapa').querySelector('details.sugestoes-descartadas');
  assert.ok(caixa, 'Descartadas no pé do quadro');
  assert.ok(!caixa.open, 'fechada');
  assert.match(texto(caixa.querySelector('summary')), /Descartadas \(1\)/);
  caixa.querySelector('li button').click(); await espera(m);
  assert.equal(m.$('quadros-mapa').querySelectorAll('.mapa-no.is-sugestao').length, 1, 'voltou como sugestão, não como item');
  assert.equal(m.$('quadros-mapa').querySelector('details.sugestoes-descartadas'), null);
  assert.match(texto(m.$('quadros-anuncio')), /Sugestão restaurada\./);
});

test('sem permissão de editar o quadro: as ações ficam indisponíveis, com a razão, e a pessoa continua vendo a sugestão', async () => {
  const m = montar({sugestoes: [PESSOA()], permissao: false}); await abrirAba(m, 'mapa');
  m.$('quadros-mapa').querySelector('.mapa-no.is-sugestao').dispatchEvent(new Evento('click', {bubbles: true}));
  const p = m.$('quadros-mapa').querySelector('.sugestao-painel');
  const botoes = [...p.querySelectorAll('.sugestao-acoes button')];
  assert.ok(botoes.length > 0 && botoes.every(b => b.disabled));
  assert.match(texto(m.doc.getElementById(botoes[0].getAttribute('aria-describedby'))), /Só repórter e editor mudam os quadros\./);
  assert.match(texto(p), /Marta Reis/);
});

test('servidor sem a rota de sugestões: o mapa abre como sempre', async () => {
  const m = montar({sugestoes: [PESSOA()], listarFalha: true}); await abrirAba(m, 'mapa');
  assert.equal(m.$('quadros-mapa').querySelectorAll('.mapa-no').length, 1);
  assert.equal(m.$('quadros-mapa').querySelectorAll('.is-sugestao').length, 0);
  assert.doesNotMatch(texto(m.$('quadros-mapa')), /sugestões? da IA/i);
  assert.deepEqual(m.erros, []);
});

test('linha do tempo: a sugestão fica na ordem das datas, com marco e cartão tracejados, e não entra na contagem do ano', async () => {
  const m = montar({sugestoes: [EVENTO()]}); await abrirAba(m, 'tempo');
  const painel = m.$('quadros-tempo');
  const eventos = [...painel.querySelectorAll('.tempo-evento')];
  assert.equal(eventos.length, 3);
  assert.ok(eventos[1].classList.contains('is-sugestao'), 'entre 10/02 e 01/06 pela data de 03/03/2025');
  const abrir = eventos[1].querySelector('.tempo-abrir');
  assert.equal(abrir.getAttribute('aria-label'), 'Sugestão da IA: Assinatura do Contrato 041/2025, 3 mar 2025, data exata');
  assert.equal(eventos[1].querySelector('.selo-sugestao').getAttribute('aria-hidden'), 'true');
  assert.match(texto(painel.querySelector('.tempo-ano-conta')), /^2 acontecimentos · 0 com documento$/, 'a sugestão não entra na contagem do ano');
  assert.match(texto(painel.querySelector('.quadro-conta')), /2 acontecimentos, 1 sugestão da IA/);
  assert.match(texto(painel.querySelector('.tempo-como-ler')), /Sugestão da IA: marco e cartão tracejados/);
  abrir.click();
  assert.match(texto(painel.querySelector('.tempo-sugestao-painel .sugestao-titulo')), /Assinatura do Contrato 041\/2025 · 3 mar 2025, data exata/);
  assert.equal(abrir.getAttribute('aria-pressed'), 'true');
});

test('linha do tempo sem sugestões: nada muda (sem selo, sem contagem extra, sem "Descartadas")', async () => {
  const m = montar({sugestoes: []}); await abrirAba(m, 'tempo');
  assert.equal(m.$('quadros-tempo').querySelectorAll('.is-sugestao').length, 0);
  assert.doesNotMatch(texto(m.$('quadros-tempo')), /sugestões? da IA|Descartadas/i);
  assert.doesNotMatch(texto(m.$('quadros-tempo').querySelector('.tempo-como-ler')), /Sugestão/);
});

test('hipóteses: grupo "Sugestões da IA (n)" entre a hipótese em aberto e as fechadas', async () => {
  const m = montar({sugestoes: [HIPOTESE()]}); await abrirAba(m, 'hipoteses');
  const filhos = [...m.$('quadros-hipoteses').children].map(no => no.className || no.tagName);
  const iAberta = filhos.findIndex((c, i) => /quadro-hipotese/.test(c) && /Hipótese H2/.test(texto(m.$('quadros-hipoteses').children[i])));
  const iGrupo = filhos.findIndex(c => /sugestoes-secao/.test(c));
  const iFechada = filhos.findIndex((c, i) => /quadro-hipotese/.test(c) && /Hipótese H1/.test(texto(m.$('quadros-hipoteses').children[i])));
  assert.ok(iAberta >= 0 && iGrupo > iAberta && iFechada > iGrupo, `ordem: aberta ${iAberta}, grupo ${iGrupo}, fechada ${iFechada}`);
  const cartao = m.$('quadros-hipoteses').querySelector('.hipotese-sugestoes .sugestao-abrir');
  assert.match(texto(cartao), /A sócia da contratada assinou o contrato também como testemunha\./);
  assert.match(texto(cartao), /contrato_social_alfa\.pdf, D002/);
  assert.equal(cartao.getAttribute('aria-label'), 'Sugestão da IA: A sócia da contratada assinou o contrato também como testemunha.');
  cartao.click();
  assert.ok(m.$('quadros-hipoteses').querySelector('.hipotese-sugestao-painel .sugestao-painel'));
  assert.match(texto(m.$('quadros-hipoteses').querySelector('.sugestoes-titulo')), /Sugestões da IA \(1\)/);
});
