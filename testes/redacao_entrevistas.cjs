'use strict';
// Phase 08 screens (interface/redacao.js): claim review of the story text and interview/request
// preparation, mounted as tabs of window.Quadros. A stub of the phase 06 board helpers keeps this
// test independent of quadros.js. Checks: both screens mount, claims keep their positions, English
// texts exist for every string, no human review happens without an explicit click by an account
// (nothing preselected, local mode cannot review) and phones move focus to the claim panel.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {criarMesa} = require('./dom_minimo.cjs');

const TEXTO = 'A fonte declara valor 12. O valor é 14.';
const VISAO = {caso: 'alfa', id: 'C' + 'a'.repeat(32), sha256: 'b'.repeat(64), titulo: 'Reportagem sintética', texto: TEXTO, versao: 1,
  resumo: {total: 2, por_estado: {sem_suporte: 0, suporte_parcial: 1, suportada: 1, revisada_por_humano: 0}, com_sinais: 1, reabertas: 0},
  versoes: [], aviso: 'Sinais de exagero são regras fixas sobre o texto extraído, para conferência humana; não julgam a reportagem. Só uma conta autenticada registra revisão humana; a IA não revisa.',
  afirmacoes: [
    {id: 'F' + '1'.repeat(32), texto: 'A fonte declara valor 12.', inicio: 0, fim: 25, estado: 'suportada', estado_automatico: 'suportada',
     sinais: [], reaberta: false, revisao_humana: null,
     evidencias: [{estado: 'conferida', evidencia: {trecho: 'A fonte declara valor 12.'}, referencia: {tipo: 'ia'}}]},
    {id: 'F' + '2'.repeat(32), texto: 'O valor é 14.', inicio: 26, fim: 39, estado: 'suporte_parcial', estado_automatico: 'suporte_parcial',
     sinais: [{tipo: 'numero_divergente', trecho: '14', posicao: 10}, {tipo: 'certeza_sem_atribuicao', trecho: null, posicao: null}],
     reaberta: false, revisao_humana: null,
     evidencias: [{estado: 'conferida', evidencia: {trecho: 'A fonte declara valor 12.'}, referencia: {tipo: 'ia'}}]}]};
const PERGUNTA = {id: 'J' + 'c'.repeat(32), sha256: 'd'.repeat(64), pergunta: 'Pode documentar a ordem bancária?', situacao: 'aberta',
  origem: {tipo: 'hipotese'}, motivo: {lacuna: 'Ordem bancária do pagamento.', contexto: 'O valor foi pago.', origem_lacuna: 'registrada'},
  evidencias: [], respostas: [], diligencia: {disponivel: true, tipo: 'pedido_lai', destinatario: 'Prefeitura', prazo: '2026-12-01', estado: 'a_solicitar'}};
const LACUNAS = {caso: 'alfa', aviso: 'Lacunas do quadro de hipóteses e afirmações sem suporte; a pergunta é um rascunho a revisar.', lacunas: [
  {origem: {tipo: 'hipotese', hipotese_id: 'H1'}, motivo: {lacuna: 'Contrato assinado.', contexto: 'O valor foi pago.', origem_lacuna: 'registrada'},
   evidencias: [], pergunta_id: null, situacao: null}]};

// Board helpers of quadros.js (phase 06), reduced to what redacao.js calls.
function quadrosFalso(janela) {
  const doc = janela.document, abas = [];
  const el = (tag, texto, classe) => { const n = doc.createElement(tag); if (texto !== undefined) n.textContent = texto; if (classe) n.className = classe; return n; };
  janela.Quadros = {
    t: (texto, vars) => janela.I18N ? janela.I18N.t(texto, vars) : texto,
    dado: (tag, texto, classe) => { const n = el(tag, texto, classe); n.setAttribute('translate', 'no'); return n; },
    botao: (rotulo, classe = 'secondary') => { const b = el('button', rotulo, classe); b.type = 'button'; return b; },
    estado: (alvo, tipo, texto) => { const p = el('p', texto, 'quadro-estado'); p.dataset.estado = tipo; alvo.replaceChildren(p); return p; },
    evidencia: (_, v, tag = 'li') => el(tag, v.evidencia?.trecho || 'indisponível', 'quadro-evidencia'),
    quadro: (chave, carregar) => async (painel, caso) => { janela.chavesAnunciadas.push(chave); await carregar(painel, caso, () => true); },
    registrarAba: registro => abas.push(registro),
  };
  janela.abas = abas; janela.chavesAnunciadas = [];
}

async function abrir({modo = 'local', desktop = true, idioma = 'pt', respostas = {}} = {}) {
  const api = async (op, dados) => {
    if (op in respostas) return typeof respostas[op] === 'function' ? respostas[op](dados) : structuredClone(respostas[op]);
    if (op === 'redacao-listar') return {caso: 'alfa', textos: [{id: VISAO.id, titulo: VISAO.titulo, versao: 1, resumo: VISAO.resumo}], divergentes: []};
    if (op === 'redacao-conferir' || op === 'redacao-revisar') return structuredClone(VISAO);
    if (op === 'entrevistas-lacunas') return structuredClone(LACUNAS);
    if (op === 'entrevistas-listar') return {caso: 'alfa', perguntas: [structuredClone(PERGUNTA)], divergentes: []};
    if (op === 'entrevistas-exportar') return {caso: 'alfa', formato: dados.formato, nome_arquivo: 'pedido.md', markdown: '# Pedido via LAI\n\n1. Pergunta'};
    return {};
  };
  const mesa = criarMesa({modo, desktop, idioma, api, armazenamento: {'vlado-idioma': idioma},
    scripts: ['i18n_en.js', 'i18n.js', 'leitura.js', 'app.js', 'redacao.js'], preparar: quadrosFalso});
  await mesa.esperar(8);
  const montar = async id => {
    const aba = mesa.janela.abas.find(a => a.id === id), painel = mesa.doc.createElement('div');
    mesa.doc.body.append(painel);
    await aba.carregar(painel, 'alfa'); await mesa.esperar(4);
    return painel;
  };
  const conferir = async () => {
    const painel = await montar('redacao');
    painel.querySelector('.redacao-textos button').click(); await mesa.esperar(6);
    return painel;
  };
  const chamadas = op => mesa.chamadas.filter(c => c.operacao === op);
  return {mesa, montar, conferir, chamadas};
}

test('as duas telas se registram como abas dos quadros e anunciam o recurso do servidor', async () => {
  const f = await abrir();
  assert.deepEqual(f.mesa.janela.abas.map(a => [a.id, a.rotulo]), [['redacao', 'Conferência do texto'], ['entrevistas', 'Entrevistas e pedidos']]);
  await f.montar('redacao'); await f.montar('entrevistas');
  assert.deepEqual(f.mesa.janela.chavesAnunciadas, ['conferencia_redacao', 'entrevistas']);
  assert.deepEqual(f.mesa.erros, []);
});

test('sem window.Quadros (página antiga) o script não quebra nada', () => {
  const mesa = criarMesa({scripts: ['i18n_en.js', 'i18n.js', 'leitura.js', 'app.js', 'redacao.js']});
  assert.equal(mesa.janela.Quadros, undefined);
  assert.deepEqual(mesa.erros, []);
});

test('texto com cada afirmação destacada pelo estado, nas posições do servidor; painel de suporte e sinais', async () => {
  const f = await abrir();
  const painel = await f.conferir();
  const texto = painel.querySelector('.redacao-texto');
  assert.equal(texto.textContent, TEXTO, 'o texto fica íntegro, só com as afirmações marcadas');
  assert.equal(texto.getAttribute('translate'), 'no');
  const trechos = painel.querySelectorAll('.redacao-afirmacao');
  assert.deepEqual(trechos.map(b => [b.textContent, b.dataset.estado]), [['A fonte declara valor 12.', 'suportada'], ['O valor é 14.', 'suporte_parcial']]);
  assert.ok(trechos.every(b => b.localName === 'button' && b.type === 'button'), 'cada afirmação é focável pelo teclado');
  trechos[1].click(); await f.mesa.esperar(2);
  assert.equal(trechos[1].getAttribute('aria-pressed'), 'true');
  const detalhe = painel.querySelector('.redacao-painel');
  assert.match(detalhe.textContent, /Sinais de exagero \(2\)/);
  assert.match(detalhe.textContent, /Número ou data diferente da fonte/);
  assert.match(detalhe.textContent, /Certeza onde a fonte só atribui/);
  assert.equal(detalhe.querySelectorAll('.quadro-evidencia').length, 1);
  assert.equal(painel.querySelectorAll('.redacao-legenda li').length, 4);
});

test('modo local: não há botão de revisão humana, só o aviso de que exige conta', async () => {
  const f = await abrir({modo: 'local'});
  const painel = await f.conferir();
  painel.querySelector('.redacao-afirmacao').click(); await f.mesa.esperar(2);
  assert.equal(painel.querySelectorAll('.redacao-revisao button').length, 0);
  assert.match(painel.querySelector('.redacao-revisao').textContent, /exige uma conta autenticada/);
  assert.equal(f.chamadas('redacao-revisar').length, 0);
});

test('com conta: nada pré-marcado, nada enviado sem escolha e clique; o clique envia só a decisão escolhida', async () => {
  const f = await abrir({modo: 'piloto'});
  const painel = await f.conferir();
  painel.querySelector('.redacao-afirmacao').click(); await f.mesa.esperar(2);
  const caixa = painel.querySelector('.redacao-revisao');
  const form = caixa.querySelector('form'), decisao = form.querySelector('select'), enviar = form.querySelector('button[type="submit"]');
  assert.equal(form.hidden, true, 'o formulário só abre por ação da pessoa');
  assert.equal(decisao.value, '', 'nenhuma decisão pré-selecionada');
  assert.equal(enviar.disabled, true);
  form.requestSubmit(); await f.mesa.esperar(4);
  assert.equal(f.chamadas('redacao-revisar').length, 0, 'enviar sem decisão não registra nada');
  await f.mesa.esperar(10);
  assert.equal(f.chamadas('redacao-revisar').length, 0, 'nada é aprovado sozinho com o tempo');
  caixa.querySelector('button[aria-expanded]').click();
  assert.equal(form.hidden, false);
  decisao.value = 'precisa_de_ajuste'; decisao.dispatchEvent(new (f.mesa.janela.Event)('change'));
  assert.equal(enviar.disabled, false);
  enviar.click(); form.requestSubmit(); await f.mesa.esperar(8);
  const [chamada] = f.chamadas('redacao-revisar');
  assert.equal(f.chamadas('redacao-revisar').length, 1);
  assert.equal(chamada.dados.decisao, 'precisa_de_ajuste');
  assert.equal(chamada.dados.afirmacao_id, VISAO.afirmacoes[0].id);
  assert.equal(chamada.dados.anterior_sha256, VISAO.sha256);
});

test('revisão humana já registrada aparece com decisão e responsável, sem novo envio', async () => {
  const revisada = structuredClone(VISAO);
  Object.assign(revisada.afirmacoes[0], {estado: 'revisada_por_humano', revisao_humana: {decisao: 'conferida_no_original', responsavel: 'Editora C',
    em_utc: '2026-11-19T10:00:00+00:00', observacao: 'Conferi a linha 1.', conta_id: 'k1'}});
  const f = await abrir({modo: 'piloto', respostas: {'redacao-conferir': revisada}});
  const painel = await f.conferir();
  painel.querySelector('.redacao-afirmacao').click(); await f.mesa.esperar(2);
  const caixa = painel.querySelector('.redacao-revisao');
  assert.match(caixa.textContent, /Revisão humana: Conferida no original/);
  assert.match(caixa.textContent, /Editora C/);
  assert.equal(f.chamadas('redacao-revisar').length, 0);
});

test('celular: escolher uma afirmação leva o foco ao painel; no desktop o foco fica no texto', async () => {
  for (const [desktop, esperado] of [[false, true], [true, false]]) {
    const f = await abrir({desktop});
    const painel = await f.conferir();
    const trecho = painel.querySelector('.redacao-afirmacao');
    trecho.focus(); trecho.click(); await f.mesa.esperar(2);
    const ativo = f.mesa.doc.activeElement;
    assert.equal(ativo?.classList.contains('redacao-painel'), esperado, desktop ? 'desktop' : 'celular');
  }
});

test('entrevistas: lacunas, pergunta com diligência ligada, formulário fechado e exportação só com seleção', async () => {
  const f = await abrir({modo: 'piloto'});
  const painel = await f.montar('entrevistas');
  assert.match(painel.querySelector('.redacao-lacunas').textContent, /Contrato assinado\./);
  const preparar = painel.querySelector('.redacao-lacunas form');
  assert.equal(preparar.hidden, true);
  assert.equal(preparar.querySelector('select').value, '', 'tipo de contato não vem pré-escolhido');
  const pergunta = painel.querySelector('.redacao-pergunta');
  assert.match(pergunta.textContent, /Pode documentar a ordem bancária\?/);
  assert.match(pergunta.textContent, /Pedido via LAI/);
  assert.match(pergunta.textContent, /prazo 2026-12-01/);
  assert.equal(pergunta.querySelector('form').querySelector('select').value, '', 'situação da resposta não vem pré-escolhida');
  const [pauta, pedido] = painel.querySelectorAll('.redacao-exportar button');
  pedido.click(); await f.mesa.esperar(4);
  assert.equal(f.chamadas('entrevistas-exportar').length, 0, 'sem pergunta marcada nada é exportado');
  const marcar = pergunta.querySelector('input[type="checkbox"]');
  marcar.checked = true; marcar.dispatchEvent(new (f.mesa.janela.Event)('change'));
  pedido.click(); await f.mesa.esperar(4);
  assert.deepEqual(f.chamadas('entrevistas-exportar')[0].dados, {caso: 'alfa', ids: [PERGUNTA.id], formato: 'pedido'});
  const saida = painel.querySelector('.redacao-markdown');
  assert.equal(saida.hidden, false);
  assert.equal(saida.getAttribute('translate'), 'no');
  assert.match(saida.textContent, /^# Pedido via LAI/);
  assert.ok(pauta);
  assert.equal(f.chamadas('entrevistas-responder').length, 0);
});

test('M3: cada exportação libera a URL do arquivo anterior antes de criar a nova', async () => {
  const f = await abrir({modo: 'piloto'});
  const criadas = [], liberadas = [];
  f.mesa.janela.URL.createObjectURL = () => { const url = `blob:teste-${criadas.length + 1}`; criadas.push(url); return url; };
  f.mesa.janela.URL.revokeObjectURL = url => liberadas.push(url);
  const painel = await f.montar('entrevistas');
  const marcar = painel.querySelector('.redacao-pergunta input[type="checkbox"]');
  marcar.checked = true; marcar.dispatchEvent(new (f.mesa.janela.Event)('change'));
  const [pauta, pedido] = painel.querySelectorAll('.redacao-exportar button');
  pauta.click(); await f.mesa.esperar(4);
  assert.deepEqual(liberadas, [], 'a primeira exportação não tem o que liberar');
  pedido.click(); await f.mesa.esperar(4);
  pauta.click(); await f.mesa.esperar(4);
  assert.deepEqual(criadas, ['blob:teste-1', 'blob:teste-2', 'blob:teste-3']);
  assert.deepEqual(liberadas, ['blob:teste-1', 'blob:teste-2'], 'só a URL da exportação vigente continua viva');
  assert.equal(painel.querySelector('.redacao-exportar a').href, 'blob:teste-3');
});

test('M4: com conta o pedido de pergunta não leva nome de autor; no modo local leva o nome informado', async () => {
  for (const [modo, esperado] of [['piloto', ''], ['local', 'Repórter Local']]) {
    const f = await abrir({modo});
    const painel = await f.montar('entrevistas');
    const form = painel.querySelector('.redacao-lacunas form');
    const [tipo] = form.querySelectorAll('select'), campos = form.querySelectorAll('input');
    tipo.value = 'entrevista';
    campos[0].value = 'Secretaria de Obras'; campos[1].value = 'Responsável Fulano';
    assert.equal(form.querySelectorAll('input').length, modo === 'local' ? 4 : 3, 'campo "Seu nome" só no modo local');
    if (modo === 'local') campos[3].value = 'Repórter Local';
    form.requestSubmit(); await f.mesa.esperar(6);
    const [chamada] = f.chamadas('entrevistas-preparar');
    assert.equal(chamada.dados.autor, esperado, modo);
    assert.equal(chamada.dados.responsavel, 'Responsável Fulano');
  }
});

test('em inglês as duas telas aparecem traduzidas', async () => {
  const f = await abrir({idioma: 'en', modo: 'piloto'});
  assert.deepEqual(f.mesa.janela.abas.map(a => a.rotulo), ['Claim review', 'Interviews and requests']);
  const painel = await f.conferir();
  painel.querySelectorAll('.redacao-afirmacao')[1].click(); await f.mesa.esperar(2);
  assert.match(painel.textContent, /Overstatement signals \(2\)/);
  assert.match(painel.textContent, /Record human review/);
  const entrevistas = await f.montar('entrevistas');
  assert.match(entrevistas.textContent, /Questions and requests \(1\)/);
  assert.match(entrevistas.textContent, /Access-to-information \(LAI\) request/);
});

test('todo texto de interface de redacao.js tem tradução, e o dicionário não repete chaves', () => {
  const fonte = fs.readFileSync(path.join(__dirname, '..', 'interface', 'redacao.js'), 'utf8');
  const literais = new Set([...fonte.matchAll(/\bt\('((?:[^'\\]|\\.)*)'/g)].map(m => m[1]));
  for (const bloco of fonte.matchAll(/const (?:ESTADOS|DECISOES|SINAIS|TIPOS|SITUACOES|ORIGENS) = \{([^}]*)\}/g))
    for (const m of bloco[1].matchAll(/: '([^']*)'/g)) literais.add(m[1]);
  for (const m of fonte.matchAll(/(?:rotulado|opcoes\([A-Z{][^,]*,)\s*\(?'([^']*)'/g)) literais.add(m[1]);
  const mesa = criarMesa({scripts: ['i18n_en.js']});
  const textos = mesa.janela.VLADO_I18N_EN.textos;
  const ausentes = [...literais].filter(l => !(l in textos));
  assert.ok(literais.size > 60, `literais lidos: ${literais.size}`);
  assert.deepEqual(ausentes, []);
  const dicionario = fs.readFileSync(path.join(__dirname, '..', 'interface', 'i18n_en.js'), 'utf8');
  const chaves = [...dicionario.matchAll(/^\s+("(?:[^"\\]|\\.)*"):/gm)].map(m => m[1]);
  const repetidas = chaves.filter((c, i) => chaves.indexOf(c) !== i);
  assert.deepEqual(repetidas.filter(c => literais.has(JSON.parse(c))), [], 'nenhuma chave da fase 08 repetida');
});
