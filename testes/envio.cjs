'use strict';
// Envio por arquivo (interface/envio.js, docs/design/componentes.md#documentos, W02 regras 2, 3, 5, 6 e 8; UX-05). DOM sintético com um
// XMLHttpRequest de teste: o formato em fluxo (manifesto + bytes), a barra por arquivo, o estado da fila, a falha de um sem derrubar os outros.
const test = require('node:test');
const assert = require('node:assert/strict');
const {criarMesa} = require('./dom_minimo.cjs');

const HTML = '<!doctype html><html><head><meta name="session-token" content="csrf-teste"></head><body data-idioma-padrao="pt"><main id="conteudo"><div id="alvo"></div><div id="cadastro-recibo" hidden></div></main></body></html>';
const MB = 1024 * 1024;
const arquivo = (name, size = 1000) => ({name, size});

// XMLHttpRequest de teste: guarda o pedido e deixa o teste disparar progresso e resposta.
function abrir({fila = () => ({})} = {}) {
  const pedidos = [];
  class XHR {
    constructor() { this.ouvintes = {}; this.upload = {ouvintes: {}, addEventListener: (tipo, f) => { this.upload.ouvintes[tipo] = f; }}; this.cabecalhos = {}; pedidos.push(this); }
    open(metodo, url) { this.metodo = metodo; this.url = url; }
    setRequestHeader(nome, valor) { this.cabecalhos[nome] = valor; }
    addEventListener(tipo, f) { this.ouvintes[tipo] = f; }
    send(corpo) { this.corpo = corpo; }
    abort() { this.ouvintes.abort?.(); }
    progresso(loaded) { this.upload.ouvintes.progress({loaded, total: 0}); }
    responder(status, corpo) { this.status = status; this.responseText = JSON.stringify(corpo); this.ouvintes.load(); }
    falharRede() { this.ouvintes.error(); }
  }
  const mesa = criarMesa({scripts: ['i18n_en.js', 'i18n.js', 'estados.js', 'envio.js'], html: HTML,
    api: () => ({}),
    preparar: janela => {
      janela.XMLHttpRequest = XHR; janela.TextEncoder = TextEncoder;
      janela.setTimeout = funcao => setImmediate(funcao);
    }});
  const original = mesa.janela.fetch;
  mesa.janela.fetch = async (endereco, opcoes) => {
    if (String(endereco).startsWith('/api/fila?lote=')) { const lote = fila(String(endereco).split('=')[1]); return {ok: true, json: async () => ({lote})}; }
    return original(endereco, opcoes);
  };
  mesa.pedidos = pedidos;
  return mesa;
}
const linhas = mesa => mesa.$('alvo').querySelectorAll('.envio-arquivo');
const resultado = li => li.querySelector('.envio-resultado').textContent;
const livre = mesa => mesa.esperar(6);

test('recusa antes do envio: nome que a Mesa não aceita e arquivo acima de 50 MB; os demais seguem (regra 2)', async () => {
  const mesa = abrir();
  const {Envio} = mesa.janela;
  assert.match(Envio.recusa(arquivo('relatório?.pdf')), /nome do arquivo/);
  assert.match(Envio.recusa(arquivo('nul.txt')), /nome do arquivo/);
  assert.match(Envio.recusa(arquivo('termina com ponto.')), /nome do arquivo/);
  assert.match(Envio.recusa(arquivo('grande.pdf', 51 * MB)), /Passa de 50 MB/);
  assert.equal(Envio.recusa(arquivo('contrato.pdf', 10 * MB)), null);
  const promessa = Envio.enviar({escopo: {caso: 'alfa', natureza: 'publicos'}, arquivos: [arquivo('bom.pdf'), arquivo('ruim:nome.pdf'), arquivo('enorme.pdf', 60 * MB)], alvo: mesa.$('alvo')});
  await livre(mesa);
  assert.equal(mesa.pedidos.length, 1, 'só o arquivo bom foi enviado');
  const [bom, ruim, enorme] = linhas(mesa);
  assert.match(resultado(ruim), /Renomeie/);
  assert.match(resultado(enorme), /Passa de 50 MB/);
  assert.equal(ruim.querySelector('svg.estado-sinal') !== null, true, 'a recusa leva sinal, não só cor');
  assert.equal(ruim.querySelector('[role="progressbar"]').hidden, true, 'linha recusada não tem medidor');
  mesa.pedidos[0].responder(200, {estado: 'enfileirado', lote: {lote: 'L1', estado: 'publicado', arquivos: [{indice: 0, estado: 'pronto', extracao: 'extraido', paginas: 3}], recibo: {recebidos: 1, novos: 1, duplicados: 0, corpus_id: 'c1'}}});
  const final = await promessa;
  assert.equal(final.recusados, 2);
  assert.equal(final.recebidos, 1);
  assert.equal(final.pendentes, 2); assert.equal(final.naoCadastrados, 2); assert.equal(final.aConferir, 0);
  assert.match(resultado(bom), /Pronto, 3 pág\./);
  assert.match(mesa.$('alvo').querySelector('.envio-recibo').textContent, /Recibo do lote: 1 de 3 cadastrados, 2 não cadastrados\. É conferido antes da primeira pergunta\./);
});

test('formato em fluxo: tipo, token, manifesto de uma linha com nome e tamanho, assincrono, e os bytes depois', async () => {
  const mesa = abrir();
  const a = arquivo('a.pdf', 10), b = arquivo('b.docx', 20);
  mesa.janela.Envio.enviar({escopo: {novo: true, caso: 'apuracao_x', titulo: 'Minha apuração', natureza: 'publicos'}, arquivos: [a, b], alvo: mesa.$('alvo')});
  await livre(mesa);
  const pedido = mesa.pedidos[0];
  assert.equal(pedido.metodo, 'POST'); assert.equal(pedido.url, '/api/cadastrar');
  assert.equal(pedido.cabecalhos['Content-Type'], 'application/vnd.vlado.lote');
  assert.equal(pedido.cabecalhos['X-Session-Token'], 'csrf-teste');
  const [linha, ...bytes] = pedido.corpo.partes;
  const texto = Buffer.from(linha).toString('utf8');
  assert.ok(texto.endsWith('\n') && texto.indexOf('\n') === texto.length - 1, 'o manifesto é uma linha só');
  assert.deepEqual(JSON.parse(texto), {novo: true, caso: 'apuracao_x', titulo: 'Minha apuração', natureza: 'publicos', assincrono: true,
    arquivos: [{nome: 'a.pdf', tamanho: 10}, {nome: 'b.docx', tamanho: 20}]});
  assert.deepEqual(bytes, [a, b], 'os arquivos vão como estão, na ordem do manifesto');
});

test('barra por arquivo: bytes enviados repartidos na ordem; depois a etapa de leitura e a página de cada um; aria-busy e anúncio (regras 2 e 9)', async () => {
  let estado = {lote: 'L1', estado: 'processando', arquivos: [
    {indice: 0, estado: 'pronto', extracao: 'extraido', pagina: null, paginas: 14},
    {indice: 1, estado: 'ocr', etapa: 'reconhecimento', pagina: 2, paginas: 5, extracao: null}]};
  const mesa = abrir({fila: () => estado});
  const promessa = mesa.janela.Envio.enviar({escopo: {caso: 'alfa'}, arquivos: [arquivo('um.pdf', 100), arquivo('dois.pdf', 100)], alvo: mesa.$('alvo')});
  await livre(mesa);
  const pedido = mesa.pedidos[0], manifesto = pedido.corpo.partes[0].length;
  const cartao = mesa.$('alvo').querySelector('.envio-cartao');
  assert.equal(cartao.getAttribute('aria-busy'), 'true');
  assert.match(cartao.textContent, /Enviando 2 arquivos/);
  assert.match(cartao.textContent, /Você pode continuar trabalhando e sair desta tela\./);
  pedido.progresso(manifesto + 150);   // o primeiro inteiro e metade do segundo
  const [um, dois] = linhas(mesa);
  assert.equal(um.querySelector('[role="progressbar"]').getAttribute('aria-valuenow'), '100');
  assert.equal(dois.querySelector('[role="progressbar"]').getAttribute('aria-valuenow'), '50');
  assert.match(resultado(dois), /Enviando… 50%/);
  pedido.responder(200, {estado: 'enfileirado', lote: {lote: 'L1', estado: 'enfileirado', arquivos: [{indice: 0, estado: 'enfileirado'}, {indice: 1, estado: 'enfileirado'}]}});
  await livre(mesa);
  // A fila responde "processando": o primeiro pronto, o segundo lendo por OCR, página 2 de 5.
  assert.match(resultado(um), /Pronto, 14 pág\./);
  assert.match(resultado(dois), /Lendo por OCR, pág\. 2 de 5/);
  assert.equal(dois.querySelector('[role="progressbar"]').getAttribute('aria-valuenow'), '40');
  assert.equal(cartao.getAttribute('aria-busy'), 'true');
  estado = {lote: 'L1', estado: 'publicado', arquivos: [estado.arquivos[0], {indice: 1, estado: 'pronto', extracao: 'extraido', paginas: 5}], recibo: {recebidos: 2, novos: 2, duplicados: 0, corpus_id: 'c9'}};
  const final = await promessa;
  assert.equal(cartao.getAttribute('aria-busy'), 'false');
  assert.equal(final.recebidos, 2); assert.equal(final.corpus_id, 'c9');
  assert.match(mesa.$('alvo').querySelector('[role="status"]').textContent, /2 de 2 arquivos concluídos/);
  assert.match(mesa.$('alvo').querySelector('.envio-recibo').textContent, /2 de 2 cadastrados, 1 com leitura a conferir\. É conferido/);
});

test('a falha de um arquivo não derruba os outros: resultado com sinal e texto, o que foi preservado e "O que fazer" (regras 2, 5 e 6)', async () => {
  const mesa = abrir({fila: () => ({lote: 'L1', estado: 'publicado', recibo: {recebidos: 3, novos: 3, duplicados: 0}, arquivos: [
    {indice: 0, estado: 'pronto', extracao: 'extraido', paginas: 2},
    {indice: 1, estado: 'pronto', extracao: 'erro', motivo: null},
    {indice: 2, estado: 'pronto', extracao: 'parcial', paginas: 8}]})});
  const promessa = mesa.janela.Envio.enviar({escopo: {caso: 'alfa'}, arquivos: [arquivo('a.pdf'), arquivo('planilha.xlsx'), arquivo('c.pdf')], alvo: mesa.$('alvo')});
  await livre(mesa);
  mesa.pedidos[0].responder(200, {estado: 'enfileirado', lote: {lote: 'L1', estado: 'enfileirado', arquivos: []}});
  const final = await promessa;
  const [ok, erro, parcial] = linhas(mesa);
  assert.match(resultado(ok), /✓ Pronto, 2 pág\./);
  assert.match(resultado(erro), /Não foi possível ler este arquivo\. O original ficou guardado\./);
  assert.equal(erro.querySelector('.envio-resultado').dataset.tom, 'erro');
  assert.ok(erro.querySelector('svg.estado-sinal'));
  assert.equal(erro.querySelector('.envio-ajuda').hidden, false, '"O que fazer" aparece só onde há erro');
  assert.equal(erro.querySelector('.envio-ajuda').className.includes('secondary'), true, '"O que fazer" é botão secundário');
  assert.equal(ok.querySelector('.envio-ajuda').hidden, true);
  assert.equal(erro.querySelector('[role="progressbar"]').hidden, true, 'linha que falhou não tem medidor: a barra cheia leria como sucesso');
  assert.equal(erro.dataset.falha, 'true');
  assert.equal(ok.querySelector('[role="progressbar"]').hidden, false);
  const explicacao = erro.querySelector('.envio-explicacao'), ajuda = erro.querySelector('.envio-ajuda');
  assert.equal(explicacao.hidden, true);
  ajuda.click();
  assert.equal(explicacao.hidden, false); assert.equal(ajuda.getAttribute('aria-expanded'), 'true');
  assert.match(explicacao.textContent, /O original está guardado no caso/);
  const link = mesa.$('alvo').querySelector('.envio-recibo a');
  assert.equal(link.textContent, 'Ver recibo'); assert.equal(link.localName, 'a', '"Ver recibo" é link, não botão');
  assert.equal(mesa.$('alvo').querySelector('.envio-cabeca').children.length, 2, 'título e aviso na mesma linha');
  assert.match(resultado(parcial), /Lida em parte/);
  assert.equal(parcial.querySelector('.envio-resultado').dataset.tom, 'aviso', 'aviso nas cores de aviso, nunca de erro (regra 6)');
  assert.equal(final.aConferir, 2, 'o com erro e o lido em parte têm leitura a conferir; os três estão cadastrados');
  assert.equal(final.naoCadastrados, 0);
  assert.match(mesa.$('alvo').querySelector('.envio-recibo').textContent, /3 de 3 cadastrados, 2 com leitura a conferir\./);
});

test('texto que passou pelo OCR vira "Lida por OCR: confira números", com sinal parcial e cor de aviso', async () => {
  let estado = {lote: 'L1', estado: 'processando', arquivos: [{indice: 0, estado: 'ocr', etapa: 'reconhecimento', pagina: 1, paginas: 3, extracao: null}]};
  const mesa = abrir({fila: () => estado});
  const promessa = mesa.janela.Envio.enviar({escopo: {caso: 'alfa'}, arquivos: [arquivo('digitalizado.pdf')], alvo: mesa.$('alvo')});
  await livre(mesa);
  mesa.pedidos[0].responder(200, {estado: 'enfileirado', lote: {lote: 'L1', estado: 'enfileirado', arquivos: []}});
  await livre(mesa);
  estado = {lote: 'L1', estado: 'publicado', recibo: {recebidos: 1, novos: 1, duplicados: 0}, arquivos: [{indice: 0, estado: 'pronto', extracao: 'extraido', paginas: 3}]};
  await promessa;
  const li = linhas(mesa)[0];
  assert.match(resultado(li), /Lida por OCR: confira números/);
  assert.equal(li.querySelector('.envio-resultado').dataset.tom, 'aviso');
  assert.ok(li.querySelector('svg.estado-sinal'));
});

test('lotes: mais de 50 MB somados ou 100 arquivos viram mais de um lote, em ordem', () => {
  const {Envio} = abrir().janela;
  const f = (n, mb) => ({nome: n, bytes: mb * MB});
  assert.equal(JSON.stringify(Envio.planejar([f('a', 30), f('b', 15), f('c', 10), f('d', 49)]).map(l => l.map(x => x.nome))), '[["a","b"],["c"],["d"]]');
  const cento = Array.from({length: 101}, (_, i) => ({nome: String(i), bytes: 1}));
  assert.equal(JSON.stringify(Envio.planejar(cento).map(l => l.length)), '[100,1]');
});

test('segundo lote de uma apuração nova entra na mesma apuração: novo vira falso depois do primeiro publicado', async () => {
  const mesa = abrir({fila: id => ({lote: id, estado: 'publicado', recibo: {recebidos: 1, novos: 1, duplicados: 0}, arquivos: [{indice: 0, estado: 'pronto', extracao: 'extraido'}]})});
  const promessa = mesa.janela.Envio.enviar({escopo: {novo: true, caso: 'apuracao_x', titulo: 'T'}, arquivos: [arquivo('a.pdf', 40 * MB), arquivo('b.pdf', 40 * MB)], alvo: mesa.$('alvo')});
  await livre(mesa);
  assert.equal(mesa.pedidos.length, 1, 'o segundo lote espera o primeiro');
  mesa.pedidos[0].responder(200, {estado: 'enfileirado', lote: {lote: 'L1', estado: 'enfileirado', arquivos: []}});
  await livre(mesa); await livre(mesa);
  assert.equal(mesa.pedidos.length, 2);
  const manifesto = JSON.parse(Buffer.from(mesa.pedidos[1].corpo.partes[0]).toString('utf8'));
  assert.equal(manifesto.novo, false); assert.equal(manifesto.caso, 'apuracao_x');
  mesa.pedidos[1].responder(200, {estado: 'enfileirado', lote: {lote: 'L2', estado: 'enfileirado', arquivos: []}});
  const final = await promessa;
  assert.equal(final.recebidos, 2); assert.equal(final.lotes.length, 2);
});

test('erro de rede no envio: o arquivo fica "não enviado" com a razão e o resultado traz o erro; nada vira cadastrado', async () => {
  const mesa = abrir();
  const promessa = mesa.janela.Envio.enviar({escopo: {caso: 'alfa'}, arquivos: [arquivo('a.pdf')], alvo: mesa.$('alvo')});
  await livre(mesa);
  mesa.pedidos[0].falharRede();
  const final = await promessa;
  assert.match(resultado(linhas(mesa)[0]), /Sem conexão com o servidor\./);
  assert.equal(final.recebidos, 0); assert.ok(final.erro);
  assert.equal(final.pendentes, 1);
});

test('erro do servidor (400) mostra a mensagem do servidor junto ao arquivo; lote em falha na fila também', async () => {
  const mesa = abrir({fila: () => ({lote: 'L1', estado: 'falha', motivo: 'O limite de documentos desta apuração foi atingido.', arquivos: []})});
  const promessa = mesa.janela.Envio.enviar({escopo: {caso: 'alfa'}, arquivos: [arquivo('a.pdf')], alvo: mesa.$('alvo')});
  await livre(mesa);
  mesa.pedidos[0].responder(200, {estado: 'enfileirado', lote: {lote: 'L1', estado: 'enfileirado', arquivos: []}});
  const final = await promessa;
  assert.match(resultado(linhas(mesa)[0]), /limite de documentos/);
  assert.equal(final.recebidos, 0);
  const outra = abrir();
  const p2 = outra.janela.Envio.enviar({escopo: {caso: 'alfa'}, arquivos: [arquivo('a.pdf')], alvo: outra.$('alvo')});
  await livre(outra);
  outra.pedidos[0].responder(400, {erro: 'O lote excede 50 MB; nenhum arquivo cadastrado.'});
  await p2;
  assert.match(resultado(linhas(outra)[0]), /excede 50 MB/);
});

test('cancelar durante o envio: o pedido é abortado, os arquivos ficam cancelados e o resultado diz que foi cancelado', async () => {
  const mesa = abrir();
  const promessa = mesa.janela.Envio.enviar({escopo: {caso: 'alfa'}, arquivos: [arquivo('a.pdf')], alvo: mesa.$('alvo')});
  await livre(mesa);
  const cancelar = [...mesa.$('alvo').querySelectorAll('button')].find(b => b.textContent === 'Cancelar envio');
  assert.ok(cancelar, 'há "Cancelar envio" enquanto os bytes sobem (regra 3 de W11)');
  cancelar.click();
  const final = await promessa;
  assert.equal(final.cancelado, true);
  assert.match(resultado(linhas(mesa)[0]), /Envio cancelado\. Nada deste arquivo foi cadastrado\./);
  assert.equal([...mesa.$('alvo').querySelectorAll('button')].some(b => b.textContent === 'Cancelar envio'), false, 'o botão some depois');
});

// A tela Cadastrar (app.js) com o envio em fluxo: só quando o servidor o anuncia em /api/integracao.
async function abrirCadastro({fluxo}) {
  const pedidos = [];
  class XHR {
    constructor() { this.ouvintes = {}; this.upload = {addEventListener() {}}; pedidos.push(this); }
    open() {} setRequestHeader() {} addEventListener(tipo, f) { this.ouvintes[tipo] = f; } send(corpo) { this.corpo = corpo; }
    responder(status, corpo) { this.status = status; this.responseText = JSON.stringify(corpo); this.ouvintes.load(); }
  }
  const lote = {lote: 'L1', caso: 'alfa', estado: 'publicado', recibo: {recebidos: 2, novos: 2, duplicados: 0, corpus_id: 'c1'},
    arquivos: [{indice: 0, estado: 'pronto', extracao: 'extraido', paginas: 4}, {indice: 1, estado: 'pronto', extracao: 'sem_texto'}]};
  const mesa = criarMesa({url: 'http://127.0.0.1:8765/?area=cadastro&caso=alfa', catalogo: [{id: 'alfa', titulo: 'Pauta Alfa', rodadas: []}],
    api: operacao => ({inventario: {caso_id: 'alfa', corpus_id: 'c1', documentos: [], total_documentos: 2}, 'codex-listar': {conversas: []}}[operacao] || {}),
    preparar: janela => {
      janela.XMLHttpRequest = XHR; janela.TextEncoder = TextEncoder;
      janela.setTimeout = (funcao, ms, ...resto) => (ms === 1500 ? setImmediate(funcao) : setTimeout(funcao, ms, ...resto));   // o intervalo da fila
      const original = janela.fetch;   // o /api/integracao é lido no carregamento: a troca vem antes dos scripts
      janela.fetch = async (endereco, opcoes) => {
        if (String(endereco) === '/api/integracao') return {ok: true, json: async () => (fluxo ? {envio_fluxo: true} : {})};
        if (String(endereco).startsWith('/api/fila?lote=')) return {ok: true, json: async () => ({lote})};
        return original(endereco, opcoes);
      };
    }});
  await mesa.esperar(12);
  mesa.pedidos = pedidos;
  return mesa;
}

test('Cadastrar com o servidor em fluxo: o submit usa o envio por arquivo, mostra o cartão, o recibo e o inventário', async () => {
  const mesa = await abrirCadastro({fluxo: true});
  Object.defineProperty(mesa.$('cadastro-arquivos'), 'files', {value: [arquivo('a.pdf', 100), arquivo('b.png', 200)]});
  mesa.$('cadastro-caso').value = 'alfa';
  mesa.$('cadastro').requestSubmit();
  await mesa.esperar(8);
  assert.equal(mesa.pedidos.length, 1, 'um pedido em fluxo');
  assert.equal(mesa.$('cadastro-envio').querySelectorAll('.envio-arquivo').length, 2);
  mesa.pedidos[0].responder(200, {estado: 'enfileirado', lote: {lote: 'L1', caso: 'alfa', estado: 'enfileirado', arquivos: []}});
  await mesa.esperar(20);
  assert.equal(mesa.$('cadastro-recibo').hidden, false);
  assert.match(mesa.$('cadastro-recibo').textContent, /Recibo do lote: 2 de 2 arquivos/);
  assert.ok(mesa.chamadas.some(c => c.operacao === 'inventario'), 'o inventário é relido depois do envio');
  assert.match(mesa.$('cadastro-status').textContent, /Confira as limitações de extração no recibo antes da pergunta/, 'arquivo sem texto pede conferência');
  assert.equal(mesa.$('cadastro-perguntar').hidden, false);
  assert.equal(mesa.$('enviar-documentos').disabled, false, 'o formulário volta a ficar livre');
  assert.equal(mesa.$('cadastro-arquivos').disabled, false);
});

test('Cadastrar com um servidor sem envio em fluxo não cria pedido em fluxo (o envio em JSON de antes continua)', async () => {
  const mesa = await abrirCadastro({fluxo: false});
  Object.defineProperty(mesa.$('cadastro-arquivos'), 'files', {value: [arquivo('a.pdf', 100)]});
  mesa.$('cadastro-caso').value = 'alfa';
  mesa.$('cadastro').requestSubmit();
  await mesa.esperar(8);
  assert.equal(mesa.pedidos.length, 0);
  assert.equal(mesa.$('cadastro-envio').childNodes.length, 0);
});

test('recibo conferido: só a contagem do lote e Detalhes técnicos, plural concordado e sem repetir o resultado de cada arquivo', () => {
  const mesa = abrir();
  const destino = mesa.$('cadastro-recibo');
  const lote = (novos, duplicados, nomes) => ({caso_id: 'alfa', corpus_id: 'c1', recebidos: novos + duplicados, novos, duplicados, arquivos: nomes.map(nome => ({nome, estado: 'pronto', extracao: 'extraido'}))});
  mesa.janela.Envio.renderRecibo(destino, lote(3, 0, ['a.pdf', 'b.pdf', 'c.pdf']));
  assert.equal(destino.hidden, false);
  assert.equal(destino.querySelector('h3').textContent, 'Recibo do lote: 3 de 3 arquivos');
  assert.equal(destino.querySelectorAll('p')[0].textContent, '3 novos · nenhum duplicado');
  assert.equal(destino.querySelectorAll('li').length, 0, 'sem a lista de arquivos: o cartão de envio já a mostra');
  assert.match(destino.querySelector('details').textContent, /Apuração: alfa · Corpus: c1/);
  mesa.janela.Envio.renderRecibo(destino, lote(1, 1, ['a.pdf', 'b.pdf']));
  assert.equal(destino.querySelectorAll('p')[0].textContent, '1 novo · 1 duplicado');
  mesa.janela.Envio.renderRecibo(destino, lote(0, 2, ['a.pdf', 'b.pdf']));
  assert.equal(destino.querySelectorAll('p')[0].textContent, 'nenhum novo · 2 duplicados');
});
