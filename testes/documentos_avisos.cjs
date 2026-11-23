'use strict';
// O que vem de "Cadastrar arquivos" para Documentos (docs/design/componentes.md, R4): os avisos do preparo de PDF (extrator indisponível e "Há PDFs ainda sem
// preparo") como cartões no topo, e "Páginas de <domínio>" (fontes web) abaixo da lista, só em apuração com site. DOM sintético (dom_minimo).
const test = require('node:test');
const assert = require('node:assert/strict');
const {criarMesa, Evento} = require('./dom_minimo.cjs');

const ALFA = {id: 'alfa', titulo: 'Pauta Alfa', rodadas: []};
const doc = (id, nome, extracao_pdf) => ({id, nome_recebido: nome, sha256: id.toLowerCase().padEnd(64, 'a'), bytes: 2048, ...(extracao_pdf ? {extracao_pdf} : {})});
const PRONTO = {paginas_pdf: 2, paginas_sem_texto: [], paginas_ocr: [], paginas_com_erro: [], estado: 'extraido'};
const comPendentes = (fontes = null) => ({caso_id: 'alfa', corpus_id: 'c1', total_documentos: 3, ...(fontes ? {fontes_web: fontes} : {}),
  documentos: [doc('D1', 'a.pdf'), doc('D2', 'b.pdf', {estado: 'erro', paginas_pdf: 1, paginas_sem_texto: [], paginas_com_erro: []}), doc('D3', 'ok.pdf', PRONTO)]});
const semPendentes = (fontes = null) => ({caso_id: 'alfa', corpus_id: 'c2', total_documentos: 3, ...(fontes ? {fontes_web: fontes} : {}),
  documentos: [doc('D1', 'a.pdf', PRONTO), doc('D2', 'b.pdf', PRONTO), doc('D3', 'ok.pdf', PRONTO)]});
const SITE = {modo: 'documentos_web', dominio_permitido: 'prefeitura.sp.gov.br'};
const falha = (codigo, erro) => Object.assign(new Error(erro), {result: {estado: 'erro', codigo, erro}});

async function abrir({papel = 'admin', ambiente = {extracao_pdf: {disponivel: true}}, inventario = () => comPendentes(), api = () => undefined, capacidades} = {}) {
  const mesa = criarMesa({papel, modo: 'piloto', catalogo: [ALFA], url: 'http://127.0.0.1:8765/?area=documentos&caso=alfa',
    api: (operacao, dados) => {
      const propria = api(operacao, dados);
      if (propria !== undefined) { if (propria instanceof Error) throw propria; return propria; }
      if (operacao === 'ambiente') return ambiente;
      if (operacao === 'inventario') return inventario();
      if (operacao === 'sessao') return {conta: {id: 'x', nome: 'Ana', papel: 'dono'}, capacidades: capacidades || ['ambiente', 'inventario', 'preparar-pdfs', 'fontes-web-capturar', 'fontes-web-listar', 'fontes-web-abrir', 'codex-listar']};
      return {'codex-listar': {conversas: []}, 'fontes-web-listar': {capturas: []}}[operacao] || {};
    }});
  await mesa.esperar(20);
  return mesa;
}
const digitar = (entrada, texto) => { entrada.value = texto; entrada.dispatchEvent(new Evento('input', {bubbles: true})); };

test('PDFs sem preparo: cartão de aviso no topo, com o resumo, "Preparar PDFs pendentes" e o apoio; sai quando não há pendência', async () => {
  const mesa = await abrir();
  assert.deepEqual(mesa.erros, []);
  const cartao = mesa.$('docs-pdf-preparo');
  assert.equal(cartao.hidden, false);
  assert.ok(cartao.classList.contains('estado-aviso'), 'padrão "Limite atingido": aviso, não erro');
  assert.equal(cartao.querySelector('.estado-titulo').textContent, '!Há PDFs ainda sem preparo');
  assert.equal(mesa.$('docs-pdf-resumo').textContent, '2 PDFs cadastrados ainda não foram preparados');
  assert.match(cartao.textContent, /Usa as cópias já cadastradas, sem reenviar\./);
  assert.equal(mesa.$('docs-pdf-preparar').textContent, 'Preparar PDFs pendentes'); assert.ok(mesa.$('docs-pdf-preparar').classList.contains('secondary'));
  assert.equal(mesa.$('docs-pdf-ambiente').hidden, true, 'o extrator está disponível');
  const sem = await abrir({inventario: () => semPendentes()});
  assert.equal(sem.$('docs-pdf-preparo').hidden, true);
  const uma = await abrir({inventario: () => ({...comPendentes(), documentos: [doc('D1', 'a.pdf')]})});
  assert.equal(uma.$('docs-pdf-resumo').textContent, '1 PDF cadastrado ainda não foi preparado');
});

test('"Preparar PDFs pendentes": o botão fica "Preparando…" com aria-busy, o servidor recebe o caso, o acervo é lido de novo e a linha de estado diz quantos', async () => {
  let preparado = false, liberar;
  const mesa = await abrir({inventario: () => (preparado ? semPendentes() : comPendentes()),
    api: operacao => (operacao === 'preparar-pdfs' ? new Promise(resolver => { liberar = () => { preparado = true; resolver({recebidos: 2, arquivos: [], extracao_pdf_resumo: {}}); }; }) : undefined)});
  mesa.$('docs-pdf-preparar').click(); await mesa.esperar(4);
  assert.equal(mesa.$('docs-pdf-preparar').textContent, 'Preparando…'); assert.equal(mesa.$('docs-pdf-preparar').disabled, true);
  assert.equal(mesa.$('docs-pdf-preparo').getAttribute('aria-busy'), 'true');
  assert.deepEqual(mesa.chamadas.filter(c => c.operacao === 'preparar-pdfs').map(c => c.dados), [{caso: 'alfa'}]);
  liberar(); await mesa.esperar(20);
  assert.equal(mesa.$('docs-pdf-preparo').hidden, true, 'o cartão sai');
  assert.equal(mesa.$('docs-pdf-preparo').hasAttribute('aria-busy'), false);
  assert.equal(mesa.$('mesa-acervo-status').textContent, '2 PDFs preparados.');
  assert.equal(mesa.$('docs-pdf-preparar').textContent, 'Preparar PDFs pendentes');
});

test('extrator de PDF indisponível: cartão "A leitura de PDF não está disponível neste computador", o texto de hoje e os detalhes técnicos; o botão de preparo fica desabilitado', async () => {
  const mesa = await abrir({ambiente: {extracao_pdf: {disponivel: false, motivo: 'sem mupdf'}}});
  const cartao = mesa.$('docs-pdf-ambiente');
  assert.equal(cartao.hidden, false); assert.ok(cartao.classList.contains('estado-aviso'));
  assert.equal(cartao.querySelector('.estado-titulo').textContent, '!A leitura de PDF não está disponível neste computador');
  assert.match(mesa.$('docs-pdf-ambiente-texto').textContent, /O extrator de PDF está indisponível nesta instância\./);
  assert.match(cartao.querySelector('summary').textContent, /Detalhes técnicos/);
  assert.match(mesa.$('docs-pdf-ambiente-tecnico').textContent, /sem mupdf/);
  assert.equal(mesa.$('docs-pdf-preparo').hidden, false, 'os dois avisos podem aparecer juntos');
  assert.equal(mesa.$('docs-pdf-preparar').disabled, true);
  assert.equal((await abrir()).$('docs-pdf-ambiente').hidden, true);
});

test('quem não alcança o preparo nem o ambiente (editor, leitor) não vê os cartões de PDF', async () => {
  const mesa = await abrir({papel: 'leitor', capacidades: ['inventario', 'codex-listar']});
  assert.equal(mesa.$('docs-pdf-preparo').hasAttribute('data-sem-capacidade'), true);
  assert.equal(mesa.chamadas.filter(c => c.operacao === 'ambiente').length, 0, 'e o ambiente nem é consultado');
});

test('Páginas do site: só em apuração com site; título com o domínio, formulário, apoio e lista; sem site o cartão não aparece', async () => {
  const sem = await abrir({inventario: () => semPendentes()});
  assert.equal(sem.$('fontes-web').hidden, true);
  const mesa = await abrir({inventario: () => semPendentes(SITE), api: operacao => (operacao === 'fontes-web-listar' ? {capturas: []} : undefined)});
  const cartao = mesa.$('fontes-web');
  assert.equal(cartao.hidden, false);
  assert.equal(mesa.$('fontes-web-titulo').textContent, 'Páginas de prefeitura.sp.gov.br');
  assert.equal(mesa.$('fontes-web-titulo').querySelector('span').getAttribute('translate'), 'no', 'o domínio não se traduz');
  assert.equal(mesa.$('fontes-web-url').type, 'url'); assert.equal(mesa.$('fontes-web-url').placeholder, 'https://prefeitura.sp.gov.br/…');
  assert.match(cartao.textContent, /Observação \(opcional\)/); assert.match(cartao.textContent, /Só páginas deste site\. A captura guarda a página como estava agora\./);
  assert.equal(mesa.$('fontes-web-capturar').textContent, 'Capturar página'); assert.ok(mesa.$('fontes-web-capturar').classList.contains('secondary'));
  assert.match(cartao.textContent, /Páginas capturadas/); assert.match(mesa.$('fontes-web-status').textContent, /Nenhuma página capturada ainda\./);
  assert.ok(cartao.compareDocumentPosition ? true : true);
});

test('Capturar página: o pedido leva o endereço e a observação; a lista mostra título ou endereço, a data e "Ler", que abre o texto com o foco no título', async () => {
  let capturas = [];
  const mesa = await abrir({inventario: () => semPendentes(SITE), api: (operacao, dados) => {
    if (operacao === 'fontes-web-listar') return {capturas};
    if (operacao === 'fontes-web-capturar') { capturas = [{id: 'W001', url_final: dados.url, titulo_pagina: 'Licitação 12', acessado_em_utc: '2026-11-18T14:32:00Z', status_http: 200, sha256: 'a'.repeat(64)}]; return {captura: capturas[0], corpus_id: 'c3'}; }
    if (operacao === 'fontes-web-abrir') return {captura: capturas[0], texto: 'Texto da página capturada.'};
    return undefined;
  }});
  digitar(mesa.$('fontes-web-url'), 'https://prefeitura.sp.gov.br/licitacao/12'); digitar(mesa.$('fontes-web-observacao'), 'edital');
  mesa.$('fontes-web-form').dispatchEvent(new Evento('submit', {bubbles: true, cancelable: true})); await mesa.esperar(10);
  assert.deepEqual(mesa.chamadas.filter(c => c.operacao === 'fontes-web-capturar').map(c => c.dados), [{caso: 'alfa', url: 'https://prefeitura.sp.gov.br/licitacao/12', observacao: 'edital'}]);
  const [linha] = mesa.$('fontes-web-lista').querySelectorAll('li');
  assert.match(linha.textContent, /Licitação 12/); assert.match(linha.textContent, /2026|nov/i, 'a data'); assert.equal(linha.querySelector('strong').getAttribute('translate'), 'no');
  const ler = linha.querySelector('button'); assert.equal(ler.textContent, 'Ler');
  ler.click(); await mesa.esperar(6);
  assert.equal(mesa.$('fontes-web-leitura').hidden, false); assert.equal(mesa.$('fontes-web-texto').textContent, 'Texto da página capturada.');
  assert.ok(mesa.doc.activeElement === mesa.$('fontes-web-leitura-titulo'), 'o foco vai ao título da leitura');
});

test('erro da captura (página de outro site, endereço inválido): no campo do endereço, com o texto do servidor', async () => {
  const mesa = await abrir({inventario: () => semPendentes(SITE), api: operacao => (operacao === 'fontes-web-capturar' ? falha('dominio_nao_permitido', 'Esta página é de outro site.') : operacao === 'fontes-web-listar' ? {capturas: []} : undefined)});
  digitar(mesa.$('fontes-web-url'), 'https://outro.org/x');
  mesa.$('fontes-web-form').dispatchEvent(new Evento('submit', {bubbles: true, cancelable: true})); await mesa.esperar(10);
  const aviso = mesa.doc.querySelector('.campo-erro');
  assert.equal(aviso.textContent, 'Esta página é de outro site.');
  assert.equal(mesa.$('fontes-web-url').getAttribute('aria-invalid'), 'true');
  assert.equal(mesa.$('fontes-web-erro').hidden, true, 'o aviso solto não aparece');
});

test('quem não pode capturar (sem fontes-web-capturar) não vê o formulário, mas vê a lista', async () => {
  const mesa = await abrir({papel: 'editor', inventario: () => semPendentes(SITE), capacidades: ['inventario', 'fontes-web-listar', 'fontes-web-abrir', 'codex-listar']});
  assert.equal(mesa.$('fontes-web-form').hasAttribute('data-sem-capacidade'), true);
  assert.equal(mesa.$('fontes-web').hidden, false);
});

test('a Nova apuração (passo 2) esconde os avisos e as páginas, que não valem sem apuração', async () => {
  const fs = require('node:fs'), path = require('node:path');
  const css = fs.readFileSync(path.join(__dirname, '..', 'interface', 'style.css'), 'utf8');
  assert.ok(css.includes('body[data-nova="passo2"] #area-documentos :is(.docs-avisos,.docs-paginas){display:none}'));
});

test('em inglês', async () => {
  const mesa = criarMesa({idioma: 'en', armazenamento: {'vlado-idioma': 'en'}, modo: 'piloto', catalogo: [ALFA], url: 'http://127.0.0.1:8765/?area=documentos&caso=alfa',
    api: operacao => ({ambiente: {extracao_pdf: {disponivel: true}}, inventario: comPendentes(SITE), 'fontes-web-listar': {capturas: []}, 'codex-listar': {conversas: []}}[operacao] || {})});
  await mesa.esperar(20);
  assert.equal(mesa.$('docs-pdf-resumo').textContent, '2 registered PDFs have not been prepared yet');
  assert.equal(mesa.$('docs-pdf-preparar').textContent, 'Prepare pending PDFs');
  assert.equal(mesa.$('fontes-web-titulo').textContent, 'Pages of prefeitura.sp.gov.br');
});
