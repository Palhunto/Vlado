'use strict';
// Tela Documentos (interface/documentos.js, docs/design/componentes.md#documentos, W02): estados de leitura, lista, área de envio, e a
// ligação com o envio por arquivo. DOM sintético (dom_minimo).
const test = require('node:test');
const assert = require('node:assert/strict');
const {criarMesa, Evento, PILHA} = require('./dom_minimo.cjs');

const ALFA = {id: 'alfa', titulo: 'Pauta Alfa', rodadas: []}, BETA = {id: 'beta', titulo: 'Pauta Beta', rodadas: []};
const doc = (id, nome, extracao_pdf) => ({id, nome_recebido: nome, sha256: id.toLowerCase().padEnd(64, 'a'), bytes: 2048, ...(extracao_pdf ? {extracao_pdf} : {})});
const INVENTARIO = {caso_id: 'alfa', titulo: 'Pauta Alfa', corpus_id: 'c1', total_documentos: 6, documentos: [
  doc('D001', 'contrato_041.pdf', {paginas_pdf: 8, paginas_sem_texto: [], paginas_ocr: [], paginas_com_erro: []}),
  doc('D002', 'medicao_03.pdf', {paginas_pdf: 1, paginas_sem_texto: [], paginas_ocr: [1], paginas_com_erro: []}),
  doc('D003', 'foto_canteiro.jpg'),
  doc('D004', 'digitalizado.pdf', {paginas_pdf: 3, paginas_sem_texto: [2], paginas_ocr: [], paginas_com_erro: []}),
  doc('D005', 'protegido.pdf', {paginas_pdf: 2, protegido: true, paginas_sem_texto: [], paginas_ocr: [], paginas_com_erro: []}),
  doc('D006', 'planilha.xlsx')]};

function abrir({fluxo = true, papel = 'admin', desktop = true} = {}) {
  const pedidos = [];
  class XHR {
    constructor() { this.ouvintes = {}; this.upload = {addEventListener() {}}; pedidos.push(this); }
    open() {} setRequestHeader() {} addEventListener(tipo, f) { this.ouvintes[tipo] = f; } send(corpo) { this.corpo = corpo; }
    responder(status, corpo) { this.status = status; this.responseText = JSON.stringify(corpo); this.ouvintes.load(); }
  }
  const mesa = criarMesa({papel, desktop, catalogo: [ALFA, BETA], url: 'http://127.0.0.1:8765/?area=documentos&caso=alfa',
    api: operacao => ({inventario: INVENTARIO, 'codex-listar': {conversas: []}}[operacao] || {}),
    preparar: janela => {
      janela.XMLHttpRequest = XHR; janela.TextEncoder = TextEncoder;
      janela.DataTransfer = class { constructor() { const itens = []; this.items = {add: arquivo => itens.push(arquivo)}; this.files = itens; } };
      janela.setTimeout = (funcao, ms, ...resto) => (ms === 1500 ? setImmediate(funcao) : setTimeout(funcao, ms, ...resto));
      const original = janela.fetch;
      janela.fetch = async (endereco, opcoes) => {
        if (String(endereco) === '/api/integracao') {
          const resposta = {ok: true, json: async () => (fluxo ? {envio_fluxo: true} : {})};
          return janela.__segurar ? janela.__segurar.then(() => resposta) : resposta;
        }
        if (String(endereco).startsWith('/api/fila?lote=')) {
          return {ok: true, json: async () => ({lote: {lote: 'L1', caso: 'alfa', estado: 'publicado', recibo: {recebidos: 1, novos: 1, duplicados: 0, corpus_id: 'c2'},
            arquivos: [{indice: 0, estado: 'pronto', extracao: 'extraido', paginas: 2}]}})};
        }
        return original(endereco, opcoes);
      };
    }});
  mesa.pedidos = pedidos;
  return mesa;
}
const linhas = mesa => mesa.$('mesa-acervo-lista').querySelectorAll('tbody tr');

test('estados de leitura: três da prancha mais "em parte" e "não foi lido", sempre com texto e sinal (regra 5)', async () => {
  const mesa = abrir();
  await mesa.esperar(12);
  const {Documentos} = mesa.janela;
  const [contrato, medicao, foto, digitalizado, protegido, planilha] = INVENTARIO.documentos.map(d => Documentos.leitura(d));
  assert.equal(contrato.chave, 'texto'); assert.equal(contrato.texto, 'Texto do próprio arquivo'); assert.equal(contrato.marca, '✓');
  assert.equal(medicao.chave, 'ocr'); assert.equal(medicao.texto, 'Lida por OCR: confira números'); assert.equal(medicao.sinal, 'parcial'); assert.equal(medicao.tom, 'aviso');
  assert.equal(foto.chave, 'sem-leitura'); assert.equal(foto.texto, 'Imagem sem leitura'); assert.equal(foto.marca, '○');
  assert.equal(digitalizado.chave, 'parcial'); assert.equal(digitalizado.texto, 'Lida em parte: confira as páginas sem texto');
  assert.equal(protegido.chave, 'erro'); assert.equal(protegido.texto, 'Não foi lido. O original ficou guardado.'); assert.equal(protegido.sinal, 'sem-suporte'); assert.equal(protegido.tom, 'erro');
  assert.equal(planilha.chave, 'texto', 'outros formatos entram com o texto do arquivo');
  assert.equal(Documentos.leitura(doc('D9', 'imagem.png', {paginas_pdf: 1, paginas_sem_texto: [1]})).chave, 'sem-leitura', 'todas as páginas sem texto = sem leitura');
});

test('lista: uma tabela com Documento, Páginas, Leitura e a ação; hash e identificador só em Detalhes técnicos (regras 5 e 7)', async () => {
  const mesa = abrir();
  await mesa.esperar(12);
  assert.equal(mesa.$('mesa-acervo').hidden, false);
  assert.equal(linhas(mesa).length, 6);
  const cabecas = mesa.$('mesa-acervo-lista').querySelectorAll('thead th').map(th => th.textContent);
  assert.equal(JSON.stringify(cabecas), JSON.stringify(['Documento', 'Páginas', 'Leitura', 'Ação']));
  const [contrato, medicao, foto] = linhas(mesa);
  assert.match(contrato.textContent, /contrato 041/);
  assert.match(contrato.querySelector('.docs-paginas').textContent, /8 páginas/);
  assert.equal(contrato.querySelector('.docs-leitura').dataset.tom, 'ok');
  assert.match(medicao.querySelector('.docs-leitura').textContent, /Lida por OCR: confira números/);
  assert.ok(medicao.querySelector('.docs-leitura svg.estado-sinal'), 'sinal parcial em SVG');
  assert.match(foto.querySelector('.docs-leitura').textContent, /○Imagem sem leitura|○ ?Imagem sem leitura/);
  // O que não é para a lista: identificador e hash ficam em "Detalhes técnicos".
  const visivel = contrato.cloneNode(true); visivel.querySelectorAll('details').forEach(d => d.remove());
  assert.doesNotMatch(visivel.textContent, /D001|aaaa/, 'hash e identificador fora da lista');
  const detalhes = contrato.querySelector('details');
  assert.match(detalhes.querySelector('summary').textContent, /Detalhes técnicos/);
  assert.match(detalhes.textContent, /D001/); assert.match(detalhes.textContent, /d001a{4}/);
  assert.equal(contrato.querySelector('.docs-abrir').textContent, 'Abrir original');
  assert.match(mesa.$('docs-contagem').textContent, /6 documentos/);
  assert.equal(mesa.$('mesa-aba-recibo'), null, 'a aba "Cadastro e recibo" saiu (regra 1)');
  assert.equal(mesa.$('mesa-adicionar'), null, 'o banner "Adicionar documentos" saiu: a área de envio faz isso');
});

test('filtros: por nome e "com limitações"; sem resultado, estado vazio que diz o que fazer', async () => {
  const mesa = abrir();
  await mesa.esperar(12);
  mesa.$('mesa-filtrar-documento').value = 'planilha';
  mesa.$('mesa-filtrar-documento').dispatchEvent(new Evento('input', {bubbles: true}));
  assert.equal(linhas(mesa).length, 1);
  mesa.$('mesa-filtrar-documento').value = 'xyz';
  mesa.$('mesa-filtrar-documento').dispatchEvent(new Evento('input', {bubbles: true}));
  assert.equal(linhas(mesa).length, 0);
  assert.match(mesa.$('mesa-acervo-lista').textContent, /Nenhum documento nesta seleção/);
  mesa.$('mesa-filtrar-documento').value = '';
  mesa.$('mesa-filtrar-leitura').value = 'limitacoes';
  mesa.$('mesa-filtrar-leitura').dispatchEvent(new Evento('change', {bubbles: true}));
  assert.ok(linhas(mesa).length >= 1 && linhas(mesa).length < 6, 'só os com limitação de extração');
});

test('área de envio: arrastar ou escolher; "Escolher arquivos" no celular; a zona reage ao arrastar', async () => {
  const mesa = abrir();
  await mesa.esperar(12);
  const zona = mesa.$('documentos-zona');
  assert.match(zona.textContent, /Arraste arquivos para cá ou escolha no computador/);
  assert.match(zona.textContent, /PDF, DOCX, XLSX, CSV, TXT e imagens · até 50 MB por arquivo/);
  assert.equal(zona.querySelector('.docs-escolher-celular').textContent, 'Escolher arquivos');
  zona.dispatchEvent(new Evento('dragenter', {bubbles: true, cancelable: true}));
  assert.equal(zona.classList.contains('docs-zona-ativa'), true);
  zona.dispatchEvent(new Evento('dragleave', {bubbles: true}));
  assert.equal(zona.classList.contains('docs-zona-ativa'), false);
});

test('soltar arquivos envia para a apuração escolhida, sem natureza, e recarrega o acervo e o recibo', async () => {
  const mesa = abrir();
  await mesa.esperar(12);
  const antes = mesa.chamadas.filter(c => c.operacao === 'inventario').length;
  const soltar = new Evento('drop', {bubbles: true, cancelable: true});
  soltar.dataTransfer = {files: [{name: 'novo.pdf', size: 500}]};
  mesa.$('documentos-zona').dispatchEvent(soltar);
  assert.equal(soltar.defaultPrevented, true);
  await mesa.esperar(8);
  assert.equal(mesa.pedidos.length, 1);
  const manifesto = JSON.parse(Buffer.from(mesa.pedidos[0].corpo.partes[0]).toString('utf8'));
  assert.equal(manifesto.caso, 'alfa'); assert.equal(manifesto.novo, false); assert.equal('natureza' in manifesto, false, 'o servidor usa a natureza do caso');
  assert.equal(mesa.$('documentos-envio').querySelectorAll('.envio-arquivo').length, 1);
  mesa.pedidos[0].responder(200, {estado: 'enfileirado', lote: {lote: 'L1', caso: 'alfa', estado: 'enfileirado', arquivos: []}});
  await mesa.esperar(30);
  assert.equal(mesa.$('documentos-recibo').hidden, false);
  assert.match(mesa.$('documentos-recibo').textContent, /Recibo do lote: 1 de 1 arquivos/);
  assert.ok(mesa.chamadas.filter(c => c.operacao === 'inventario').length > antes, 'o acervo é lido de novo');
  assert.match(mesa.$('mesa-acervo-status').textContent, /Documentos registrados\. Aguardando sua pergunta\./);
});

test('sem o envio em fluxo no servidor, a área de envio leva à tela de Nova apuração (envio em JSON)', async () => {
  const mesa = abrir({fluxo: false});
  await mesa.esperar(12);
  const soltar = new Evento('drop', {bubbles: true, cancelable: true});
  soltar.dataTransfer = {files: [{name: 'novo.pdf', size: 500}]};
  mesa.$('documentos-zona').dispatchEvent(soltar);
  await mesa.esperar(8);
  assert.equal(mesa.pedidos.length, 0);
  assert.equal(mesa.$('area-cadastro').hidden, false);
  assert.equal(mesa.$('cadastro-arquivos').files.length, 1, 'os arquivos escolhidos seguem para a Nova apuração, sem escolher de novo');
  assert.equal(mesa.$('cadastro-arquivos').files[0].name, 'novo.pdf');
});

test('o convidado não vê a área de envio', async () => {
  const mesa = abrir({papel: 'convidado'});
  await mesa.esperar(12);
  assert.equal(mesa.$('documentos-zona').hidden, true);
});

test('a contagem aparece uma vez só, no topo; a nota do acervo e o pé da tabela não a repetem', async () => {
  const mesa = abrir();
  await mesa.esperar(12);
  assert.match(mesa.$('docs-contagem').textContent, /^6 documentos$/);
  assert.equal(mesa.$('mesa-acervo-status').textContent, 'Os originais estão preservados; a extração não substitui a conferência.');
  assert.equal(mesa.$('mesa-acervo-lista').querySelector('.mesa-table-foot'), null);
  assert.doesNotMatch(mesa.$('mesa-acervo').textContent.replace(mesa.$('docs-contagem').textContent, ''), /\d+ documentos? (cadastrado|nesta seleção)/);
});

test('soltar arquivos duas vezes enquanto a Mesa consulta o servidor manda o lote uma vez só (B1 da Coruja)', async () => {
  const mesa = abrir();
  await mesa.esperar(12);
  mesa.janela.__segurar = new Promise(resolver => { mesa.liberar = resolver; });
  const soltar = () => { const e = new Evento('drop', {bubbles: true, cancelable: true}); e.dataTransfer = {files: [{name: 'novo.pdf', size: 500}]}; mesa.$('documentos-zona').dispatchEvent(e); };
  soltar(); soltar();
  await mesa.esperar(4);
  mesa.liberar(); await mesa.esperar(8);
  assert.equal(mesa.pedidos.length, 1);
});

test('durante um envio em Documentos não se troca de apuração: o lote iria para a apuração errada', async () => {
  const mesa = abrir();
  await mesa.esperar(12);
  const soltar = new Evento('drop', {bubbles: true, cancelable: true});
  soltar.dataTransfer = {files: [{name: 'novo.pdf', size: 500}]};
  mesa.$('documentos-zona').dispatchEvent(soltar);
  await mesa.esperar(8);
  assert.equal(mesa.janela.Documentos.ocupado(), true);
  assert.equal(mesa.janela.definirContextoCaso('beta'), false, 'trocar de apuração espera o envio');
  assert.match(mesa.$('mesa-aviso')?.textContent || mesa.doc.body.textContent, /Aguarde o recibo deste envio antes de trocar de apuração\./);
  mesa.pedidos[0].responder(200, {estado: 'enfileirado', lote: {lote: 'L1', caso: 'alfa', estado: 'enfileirado', arquivos: []}});
  await mesa.esperar(30);
  assert.equal(mesa.janela.Documentos.ocupado(), false);
  assert.equal(mesa.janela.definirContextoCaso('beta'), true, 'depois do recibo a troca é permitida');
});
