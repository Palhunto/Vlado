'use strict';
// Nova apuração (W01; docs/design/componentes.md#nova-apuracao; R4 da pré-entrega): o passo 1 como página, a tela Documentos no modo "apuração por criar" (passo 2), o
// primeiro envio que cria a apuração (cadastrar com novo: true, sem caso) e a linha de etapas até o recibo ser conferido. DOM sintético (dom_minimo).
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {criarMesa, Evento} = require('./dom_minimo.cjs');

const ALFA = {id: 'alfa', titulo: 'Pauta Alfa', rodadas: []};
const CASO_NOVO = 'apuracao_' + 'a'.repeat(32);

function abrir({idioma = 'pt', casos = [ALFA], url = 'http://127.0.0.1:8765/', fluxo = true, lote = null, api = () => undefined, postar = null} = {}) {
  const pedidos = [];
  class XHR {
    constructor() { this.ouvintes = {}; this.upload = {addEventListener() {}}; pedidos.push(this); }
    open() {} setRequestHeader() {} addEventListener(tipo, f) { this.ouvintes[tipo] = f; } send(corpo) { this.corpo = corpo; }
    responder(status, corpo) { this.status = status; this.responseText = JSON.stringify(corpo); this.ouvintes.load(); }
  }
  const catalogo = [...casos];
  const mesa = criarMesa({idioma, armazenamento: idioma === 'en' ? {'vlado-idioma': 'en'} : {}, catalogo, url,
    api: (operacao, dados) => { const propria = api(operacao, dados); if (propria !== undefined) return propria; return ({inventario: {caso_id: CASO_NOVO, corpus_id: 'c1', total_documentos: 1, documentos: []}, 'codex-listar': {conversas: []}}[operacao] || {}); },
    preparar: janela => {
      janela.XMLHttpRequest = XHR; janela.TextEncoder = TextEncoder;
      janela.setTimeout = (funcao, ms, ...resto) => (ms === 1500 ? setImmediate(funcao) : setTimeout(funcao, ms, ...resto));
      const original = janela.fetch;
      janela.fetch = async (endereco, opcoes) => {
        if (String(endereco) === '/api/integracao') return {ok: true, json: async () => (fluxo ? {envio_fluxo: true} : {})};
        if (postar && String(endereco) === '/api/cadastrar') return postar();   // a resposta HTTP (status) ou a queda de rede do envio em JSON
        if (String(endereco) === '/api/catalogo') return {ok: true, json: async () => ({casos: catalogo})};
        if (String(endereco).startsWith('/api/fila?lote=')) {
          if (lote) return {ok: true, json: async () => ({lote})};
          return {ok: true, json: async () => ({lote: {lote: 'L1', caso: CASO_NOVO, estado: 'publicado', recibo: {recebidos: 1, novos: 1, duplicados: 0, corpus_id: 'c1'},
            arquivos: [{indice: 0, estado: 'pronto', extracao: 'extraido', paginas: 2}]}})};
        }
        return original(endereco, opcoes);
      };
    }});
  mesa.pedidos = pedidos; mesa.catalogo = catalogo;
  return mesa;
}
const area = mesa => mesa.avaliar('currentArea');
const digitar = (entrada, texto) => { entrada.value = texto; entrada.dispatchEvent(new Evento('input', {bubbles: true})); };
const enviar = async mesa => { mesa.$('nova-form').dispatchEvent(new Evento('submit', {bubbles: true, cancelable: true})); await mesa.esperar(6); };
const avisos = mesa => [...mesa.doc.querySelectorAll('.campo-erro')];
const dialogo = mesa => mesa.doc.querySelector('dialog.dialogo');
const botoes = mesa => [...dialogo(mesa).querySelectorAll('.dialogo-acoes button')];
const manifestoDe = pedido => JSON.parse(Buffer.from(pedido.corpo.partes[0]).toString('utf8'));
const soltar = async (mesa, nome = 'primeiro.pdf') => {
  const evento = new Evento('drop', {bubbles: true, cancelable: true});
  evento.dataTransfer = {files: [{name: nome, size: 500}]};
  mesa.$('documentos-zona').dispatchEvent(evento);
  await mesa.esperar(8);
};
async function passo2(mesa, {nome = 'Transporte escolar', web = false} = {}) {
  mesa.$('inicio-nova').click(); await mesa.esperar(4);
  digitar(mesa.$('nova-nome'), nome);
  if (web) { mesa.$('nova-site-campo'); const opcoes = [...mesa.doc.querySelectorAll('input[name="nova-fontes"]')], opcao = opcoes[1]; opcoes[0].checked = false; opcao.checked = true; opcao.dispatchEvent(new Evento('change', {bubbles: true})); digitar(mesa.$('nova-site'), 'Prefeitura.SP.gov.br'); }
  await enviar(mesa);
}

test('"Nova apuração" da Visão geral abre o passo 1: título, linha de etapas, nome com foco e as opções do desenho', async () => {
  const mesa = abrir();
  await mesa.esperar(12);
  assert.deepEqual(mesa.erros, []);
  mesa.$('inicio-nova').click(); await mesa.esperar(4);
  assert.equal(area(mesa), 'nova'); assert.equal(mesa.$('area-nova').hidden, false); assert.equal(mesa.$('area-cadastro'), null, 'a área antiga não existe mais');
  assert.equal(mesa.$('area-titulo').textContent, 'Nova apuração');
  assert.equal(mesa.$('area-descricao').hidden, true, 'sem a descrição da apuração escolhida');
  const etapas = mesa.$('nova-etapas-1');
  assert.equal(etapas.hidden, false);
  assert.match(etapas.textContent, /1 Nome e fontes\s*2 Documentos\s*3 Conferir recibo/);
  assert.equal(etapas.querySelector('[aria-current="step"]').textContent.trim(), '1 Nome e fontes');
  assert.ok(mesa.doc.activeElement === mesa.$('nova-nome'), 'o nome recebe o foco');
  assert.equal(mesa.$('nova-nome').getAttribute('maxlength'), '200');
  assert.match(mesa.$('nova-nome-dica').textContent, /Ex\.: Transporte escolar em Vila Serena/);
  assert.deepEqual([...mesa.$('nova-natureza').options].map(o => o.textContent), ['Documentos públicos', 'Materiais sintéticos']);
  assert.equal(mesa.$('area-nova').querySelector('legend').textContent, 'De onde vêm as fontes?');
  const [somente, web] = [...mesa.doc.querySelectorAll('input[name="nova-fontes"]')];
  assert.equal(somente.checked, true); assert.equal(web.checked, false);
  assert.match(somente.closest('label').textContent, /Só documentos\s*Padrão\. Nada é buscado na internet\./);
  assert.match(web.closest('label').textContent, /Documentos e um site\s*Você indica o site; o Vlado só captura páginas dele, a seu pedido\./);
  assert.equal(mesa.$('nova-site-campo').hidden, true, 'o site só aparece com a opção escolhida');
  assert.equal(mesa.$('nova-cancelar').textContent, 'Cancelar'); assert.equal(mesa.$('nova-continuar').textContent, 'Continuar para documentos');
  assert.equal(mesa.chamadas.filter(c => c.operacao === 'cadastrar').length, 0, 'nada é criado ainda');
});

test('com a opção "Documentos e um site" aparece o endereço, com a dica e o apoio; sem ela some', async () => {
  const mesa = abrir(); await mesa.esperar(10);
  mesa.$('inicio-nova').click(); await mesa.esperar(3);
  const [somente, web] = [...mesa.doc.querySelectorAll('input[name="nova-fontes"]')];
  web.checked = true; somente.checked = false; web.dispatchEvent(new Evento('change', {bubbles: true}));
  assert.equal(mesa.$('nova-site-campo').hidden, false);
  assert.equal(mesa.$('nova-site').placeholder, 'prefeitura.sp.gov.br'); assert.equal(mesa.$('nova-site').getAttribute('translate'), 'no');
  assert.match(mesa.$('nova-site-campo').textContent, /Só o domínio, exato\. Escolhido só agora: depois de criada, a apuração não troca de site\./);
  somente.checked = true; web.checked = false; somente.dispatchEvent(new Evento('change', {bubbles: true}));
  assert.equal(mesa.$('nova-site-campo').hidden, true);
});

test('erros junto ao campo: nome em branco, site em branco, e site inválido (esquema, caminho, interno, número, espaço)', async () => {
  const mesa = abrir(); await mesa.esperar(10);
  mesa.$('inicio-nova').click(); await mesa.esperar(3);
  await enviar(mesa);
  assert.equal(avisos(mesa)[0].textContent, 'Falta o nome. Dê um nome à apuração.');
  assert.equal(mesa.$('nova-nome').getAttribute('aria-invalid'), 'true'); assert.ok(mesa.doc.activeElement === mesa.$('nova-nome'));
  assert.equal(area(mesa), 'nova', 'não avança');
  const filhos = [...mesa.$('nova-form').children], rotulo = mesa.$('nova-nome').closest('label');
  assert.deepEqual([filhos.indexOf(avisos(mesa)[0]) - filhos.indexOf(rotulo), filhos.indexOf(mesa.$('nova-nome-dica')) - filhos.indexOf(avisos(mesa)[0])], [1, 1], 'o erro vem logo depois do campo e o apoio depois do erro');
  digitar(mesa.$('nova-nome'), 'Transporte escolar');
  const [somenteDocs, web] = [...mesa.doc.querySelectorAll('input[name="nova-fontes"]')];
  somenteDocs.checked = false; web.checked = true; web.dispatchEvent(new Evento('change', {bubbles: true}));
  await enviar(mesa);
  assert.equal(avisos(mesa)[0].textContent, 'Falta o site. Escreva o domínio, por exemplo prefeitura.sp.gov.br.');
  assert.equal(mesa.$('nova-site').getAttribute('aria-invalid'), 'true');
  const interno = [...mesa.$('nova-site-campo').children];
  assert.deepEqual(interno.map(no => no.tagName.toLowerCase() + (no.classList.contains('campo-erro') ? '.erro' : '')), ['label', 'p.erro', 'p'], 'no site também: campo, erro, apoio');
  for (const invalido of ['https://prefeitura.sp.gov.br', 'prefeitura.sp.gov.br/transporte', 'localhost', '10.0.0.5', 'prefeitura sp.gov.br', 'prefeitura.sp.gov.br:8080', '.gov.br']) {
    digitar(mesa.$('nova-site'), invalido);
    await enviar(mesa);
    assert.equal(avisos(mesa).length, 1, invalido);
    assert.equal(avisos(mesa)[0].textContent, 'Site inválido. Use só o domínio, sem https:// nem caminho, por exemplo prefeitura.sp.gov.br.', invalido);
    assert.equal(area(mesa), 'nova', invalido);
  }
  assert.equal(mesa.chamadas.filter(c => c.operacao === 'cadastrar').length, 0);
});

test('Continuar para documentos: o passo 2 é a tela Documentos, com o nome no topo, a linha em "2 Documentos", o aviso e o link de volta; nada é criado', async () => {
  const mesa = abrir(); await mesa.esperar(10);
  await passo2(mesa, {nome: 'Transporte escolar em Vila Serena'});
  assert.equal(area(mesa), 'documentos'); assert.equal(mesa.$('area-documentos').hidden, false);
  assert.equal(mesa.doc.body.dataset.nova, 'passo2');
  assert.equal(mesa.$('area-titulo').textContent, 'Nova apuração');
  assert.equal(mesa.$('area-descricao').textContent, 'Transporte escolar em Vila Serena'); assert.equal(mesa.$('area-descricao').hidden, false);
  assert.equal(mesa.$('area-descricao').getAttribute('translate'), 'no', 'o nome é dado de quem digitou');
  assert.equal(mesa.$('nova-etapas-2').hidden, false);
  assert.equal(mesa.$('nova-etapas-2').querySelector('[aria-current="step"]').textContent.trim(), '2 Documentos');
  assert.equal(mesa.doc.body.dataset.novaEtapas, '1', 'a linha da Nova apuração toma o lugar da linha de Documentos, Pergunta, Conferência e Caderno');
  assert.equal(mesa.$('nova-aviso').hidden, false);
  assert.match(mesa.$('nova-aviso').textContent, /A apuração é criada no primeiro envio\. Antes disso, nada fica guardado\./);
  assert.equal(mesa.$('nova-voltar').textContent, '‹ Nome e fontes');
  assert.equal(mesa.janela.contextoCaso(), '', 'sem apuração escolhida: ela nasce no primeiro envio');
  assert.equal(mesa.chamadas.filter(c => c.operacao === 'cadastrar').length, 0); assert.equal(mesa.pedidos.length, 0);
  const css = fs.readFileSync(path.join(__dirname, '..', 'interface', 'style.css'), 'utf8');
  assert.ok(css.includes('body[data-nova="passo2"] #area-documentos :is(.mesa-tabs,.docs-topo,.mesa-acervo-toolbar,#mesa-acervo-lista,.mesa-acervo-next'), 'sem abas, busca nem barra Leitura');
});

test('"‹ Nome e fontes" volta ao passo 1 com os campos preenchidos, inclusive o site', async () => {
  const mesa = abrir(); await mesa.esperar(10);
  await passo2(mesa, {nome: 'Obra da escola', web: true});
  assert.equal(mesa.janela.NovaApuracao.dados().dominio_permitido, 'prefeitura.sp.gov.br', 'o domínio vai em minúsculas');
  mesa.$('nova-voltar').click(); await mesa.esperar(4);
  assert.equal(area(mesa), 'nova'); assert.equal(mesa.$('nova-nome').value, 'Obra da escola');
  assert.equal(mesa.$('nova-site-campo').hidden, false); assert.equal(mesa.$('nova-site').value, 'prefeitura.sp.gov.br');
  assert.equal(mesa.$('nova-etapas-1').querySelector('[aria-current="step"]').textContent.trim(), '1 Nome e fontes');
});

test('o primeiro envio cria a apuração: novo:true sem caso, com nome, natureza e fontes; o servidor devolve o caso e a tela vira a Documentos comum', async () => {
  const mesa = abrir(); await mesa.esperar(10);
  await passo2(mesa, {nome: 'Obra da escola', web: true});
  await soltar(mesa);
  assert.equal(mesa.pedidos.length, 1);
  const manifesto = manifestoDe(mesa.pedidos[0]);
  assert.equal(manifesto.novo, true); assert.ok(!('caso' in manifesto), 'a tela não escolhe o identificador');
  assert.equal(manifesto.titulo, 'Obra da escola'); assert.equal(manifesto.natureza, 'publicos');
  assert.equal(manifesto.modo_fontes, 'documentos_web'); assert.equal(manifesto.dominio_permitido, 'prefeitura.sp.gov.br');
  assert.equal(mesa.$('nova-etapas-2').querySelector('[aria-current="step"]').textContent.trim(), '2 Documentos', 'ainda no passo 2 até o lote ser aceito');
  mesa.catalogo.push({id: CASO_NOVO, titulo: 'Obra da escola', rodadas: []});   // o servidor criou a apuração
  mesa.pedidos[0].responder(200, {estado: 'enfileirado', lote: {lote: 'L1', caso: CASO_NOVO, estado: 'enfileirado', arquivos: []}});
  await mesa.esperar(30);
  assert.equal(mesa.janela.contextoCaso(), CASO_NOVO, 'o seletor do topo passa à apuração criada');
  assert.equal(mesa.doc.body.dataset.nova, undefined, 'a tela vira a Documentos comum'); assert.equal(mesa.$('nova-aviso').hidden, true);
  assert.equal(mesa.$('area-titulo').textContent, 'Documentos');
  assert.equal(mesa.$('area-descricao').textContent, 'Obra da escola');
  assert.equal(mesa.janela.NovaApuracao.ativa(), false);
});

test('passo 3: com o recibo pronto a linha marca "3 Conferir recibo"; "Ver recibo" conferido, a linha sai', async () => {
  const mesa = abrir(); await mesa.esperar(10);
  await passo2(mesa);
  await soltar(mesa);
  mesa.catalogo.push({id: CASO_NOVO, titulo: 'Transporte escolar', rodadas: []});
  mesa.pedidos[0].responder(200, {estado: 'enfileirado', lote: {lote: 'L1', caso: CASO_NOVO, estado: 'enfileirado', arquivos: []}});
  await mesa.esperar(40);
  assert.equal(mesa.$('nova-etapas-2').hidden, false);
  assert.equal(mesa.$('nova-etapas-2').querySelector('[aria-current="step"]').textContent.trim(), '3 Conferir recibo');
  assert.match(mesa.$('documentos-recibo').textContent, /Recibo do lote: 1 de 1 arquivos/);
  const ver = [...mesa.$('documentos-envio').querySelectorAll('a')].find(a => a.textContent === 'Ver recibo');
  ver.click(); await mesa.esperar(3);
  assert.equal(mesa.$('nova-etapas-2').hidden, true, 'depois do recibo conferido, a linha de etapas sai');
  assert.equal(mesa.doc.body.dataset.novaEtapas, undefined, 'e a linha de sempre volta');
});

test('sair no meio: com o formulário preenchido pede "Sair sem criar a apuração?"; vazio, sai sem pergunta; Cancelar e a barra lateral seguem a regra', async () => {
  const vazio = abrir(); await vazio.esperar(10);
  vazio.$('inicio-nova').click(); await vazio.esperar(3);
  vazio.$('nova-cancelar').click(); await vazio.esperar(4);
  assert.equal(dialogo(vazio), null, 'sem nada digitado, nenhuma pergunta'); assert.equal(area(vazio), 'inicio');

  const mesa = abrir(); await mesa.esperar(10);
  mesa.$('inicio-nova').click(); await mesa.esperar(3);
  digitar(mesa.$('nova-nome'), 'Algo');
  mesa.$('nova-cancelar').click(); await mesa.esperar(4);
  assert.ok(dialogo(mesa), 'pergunta antes de sair');
  assert.equal(dialogo(mesa).querySelector('.dialogo-titulo').textContent, 'Sair sem criar a apuração?');
  assert.equal(botoes(mesa)[1].textContent, 'Sair');
  botoes(mesa)[0].click(); await mesa.esperar(4);   // Cancelar: continua no formulário
  assert.equal(area(mesa), 'nova'); assert.equal(mesa.$('nova-nome').value, 'Algo');
  mesa.$('ver-codex').click(); await mesa.esperar(4);   // um item da barra lateral
  assert.ok(dialogo(mesa), 'a barra lateral também pergunta'); assert.equal(area(mesa), 'nova', 'a área só muda depois da confirmação');
  botoes(mesa)[1].click(); await mesa.esperar(8);
  assert.equal(area(mesa), 'codex', 'confirmada a saída, o clique segue'); assert.equal(mesa.janela.NovaApuracao.ativa(), false);
  mesa.$('inicio-nova').click?.();
  assert.equal(mesa.chamadas.filter(c => c.operacao === 'cadastrar').length, 0, 'nada ficou guardado');
});

test('Adicionar documentos da Visão geral leva a Documentos com a apuração escolhida, sem os passos; sem apuração escolhida, avisa', async () => {
  const mesa = abrir({url: 'http://127.0.0.1:8765/?caso=alfa'}); await mesa.esperar(12);
  mesa.avaliar("showArea('inicio')");
  mesa.$('inicio-adicionar').click(); await mesa.esperar(4);
  assert.equal(area(mesa), 'documentos'); assert.equal(mesa.janela.contextoCaso(), 'alfa');
  assert.equal(mesa.doc.body.dataset.nova, undefined); assert.equal(mesa.$('nova-etapas-2').hidden, true);
  const sem = abrir(); await sem.esperar(10);
  sem.$('inicio-adicionar').click(); await sem.esperar(3);
  assert.notEqual(area(sem), 'documentos'); assert.match(sem.$('experiencia-status').textContent, /Escolha a apuração que deseja receber os documentos\./);
});

test('a Nova apuração em inglês e a área só para quem pode cadastrar', async () => {
  const en = abrir({idioma: 'en'}); await en.esperar(12);
  en.$('inicio-nova').click(); await en.esperar(4);
  assert.equal(en.$('area-titulo').textContent, 'New investigation');
  assert.match(en.$('nova-etapas-1').textContent, /1 Name and sources\s*2 Documents\s*3 Check receipt/);
  await enviar(en);
  assert.equal(avisos(en)[0].textContent, 'The name is missing. Give the investigation a name.');
  assert.equal(en.$('nova-continuar').textContent, 'Continue to documents');
  const leitor = criarMesa({modo: 'piloto', papel: 'leitor', api: () => ({})});
  await leitor.esperar(8);
  assert.equal(leitor.$('inicio-nova').hasAttribute('data-sem-capacidade') || leitor.avaliar("Sessao.areaPermitida('nova')") === true, true);
});

test('B1 da Coruja: com o primeiro envio no ar o link "‹ Nome e fontes" fica indisponível; voltar, corrigir e continuar não cria uma segunda apuração', async () => {
  const mesa = abrir(); await mesa.esperar(10);
  await passo2(mesa, {nome: 'Obra da escola'});
  await soltar(mesa);
  assert.equal(mesa.pedidos.length, 1, 'o envio está no ar (segurado: ainda sem resposta)');
  assert.equal(mesa.$('nova-voltar').disabled, true); assert.equal(mesa.$('nova-voltar').getAttribute('aria-disabled'), 'true');
  mesa.$('nova-voltar').click(); await mesa.esperar(4);
  assert.equal(area(mesa), 'documentos', 'o clique não leva ao passo 1');
  assert.equal(mesa.doc.body.dataset.nova, 'passo2');
  mesa.janela.NovaApuracao.abrir(); await mesa.esperar(3);
  assert.equal(area(mesa), 'documentos', 'nem por outro caminho');
  await soltar(mesa, 'segundo.pdf');
  assert.equal(mesa.pedidos.length, 1, 'e um segundo envio não sai enquanto o primeiro está no ar');
  mesa.catalogo.push({id: CASO_NOVO, titulo: 'Obra da escola', rodadas: []});
  mesa.pedidos[0].responder(200, {estado: 'enfileirado', lote: {lote: 'L1', caso: CASO_NOVO, estado: 'enfileirado', arquivos: []}});
  await mesa.esperar(40);
  assert.equal(mesa.janela.contextoCaso(), CASO_NOVO); assert.equal(mesa.$('nova-voltar').disabled, false, 'criada a apuração, o link volta ao normal (e some com o aviso)');
  assert.equal(mesa.chamadas.filter(c => c.operacao === 'cadastrar').length, 0);
  assert.equal(mesa.pedidos.length, 1, 'uma apuração só');
});

test('B1: se o envio falha sem criar nada, o link volta e a pessoa pode corrigir o nome', async () => {
  const mesa = abrir(); await mesa.esperar(10);
  await passo2(mesa, {nome: 'Obra da escola'});
  await soltar(mesa);
  assert.equal(mesa.$('nova-voltar').disabled, true);
  mesa.pedidos[0].responder(400, {estado: 'erro', erro: 'O nome do arquivo tem caracteres que a Mesa não aceita.'});
  await mesa.esperar(20);
  assert.equal(mesa.$('nova-voltar').disabled, false, 'nada nasceu: dá para voltar');
  mesa.$('nova-voltar').click(); await mesa.esperar(4);
  assert.equal(area(mesa), 'nova'); assert.equal(mesa.$('nova-nome').value, 'Obra da escola');
});

// --- N1 a N4 da Coruja ------------------------------------------------------------------------------------------------------------------------
test('N1: sem o envio por arquivo no servidor a própria Nova apuração envia em JSON (novo:true, sem caso), cria a apuração e segue ao passo 3, sem a área antiga', async () => {
  const mesa = abrir({fluxo: false, api: (operacao, dados) => (operacao === 'cadastrar'
    ? {caso_id: CASO_NOVO, corpus_id: 'c1', recebidos: 1, novos: 1, duplicados: 0, total_documentos: 1, arquivos: [{nome: 'primeiro.pdf', estado: 'pronto'}], inventario: {}} : undefined)});
  await mesa.esperar(10);
  mesa.janela.FileReader = class { readAsDataURL() { this.result = 'data:;base64,AAAA'; this.onload(); } };
  await passo2(mesa, {nome: 'Obra da escola', web: true});
  await soltar(mesa);
  await mesa.esperar(20);
  const [pedido] = mesa.chamadas.filter(c => c.operacao === 'cadastrar');
  assert.ok(pedido, 'o envio em JSON saiu');
  assert.equal(pedido.dados.novo, true); assert.ok(!('caso' in pedido.dados), 'sem caso escolhido pela tela');
  assert.equal(pedido.dados.titulo, 'Obra da escola'); assert.equal(pedido.dados.modo_fontes, 'documentos_web'); assert.equal(pedido.dados.dominio_permitido, 'prefeitura.sp.gov.br');
  assert.deepEqual(pedido.dados.arquivos, [{nome: 'primeiro.pdf', base64: 'AAAA'}]);
  assert.equal(mesa.janela.contextoCaso(), CASO_NOVO); assert.equal(mesa.doc.body.dataset.nova, undefined);
  assert.equal(mesa.$('nova-etapas-2').querySelector('[aria-current="step"]').textContent.trim(), '3 Conferir recibo');
  assert.match(mesa.$('documentos-recibo').textContent, /Recibo do lote: 1 de 1 arquivos/);
  assert.equal(mesa.$('nova-voltar').disabled, false);
});

test('N1: o envio em JSON acima de 50 MB é recusado antes, e uma falha do servidor volta ao passo 2 sem criar nada', async () => {
  const grande = abrir({fluxo: false}); await grande.esperar(10);
  await passo2(grande);
  const evento = new Evento('drop', {bubbles: true, cancelable: true}); evento.dataTransfer = {files: [{name: 'enorme.pdf', size: 60 * 1024 * 1024}]};
  grande.$('documentos-zona').dispatchEvent(evento); await grande.esperar(10);
  assert.equal(grande.chamadas.filter(c => c.operacao === 'cadastrar').length, 0);
  assert.match(grande.$('mesa-acervo-status').textContent, /O lote excede 50 MB/); assert.equal(grande.$('nova-voltar').disabled, false);
  const falha = abrir({fluxo: false, api: operacao => { if (operacao === 'cadastrar') throw Object.assign(new Error('Nome inválido.'), {result: {erro: 'Nome inválido.'}}); return undefined; }});
  await falha.esperar(10);
  falha.janela.FileReader = class { readAsDataURL() { this.result = 'data:;base64,AAAA'; this.onload(); } };
  await passo2(falha); await soltar(falha); await falha.esperar(15);
  assert.equal(falha.janela.NovaApuracao.ativa(), true, 'a apuração continua por criar'); assert.match(falha.$('mesa-acervo-status').textContent, /Nome inválido\./);
  assert.equal(falha.$('nova-voltar').disabled, false);
});

test('N3: primeiro lote aceito e depois falho na fila: a tela sai da apuração que não existe e pede para recomeçar a Nova apuração', async () => {
  const mesa = abrir({lote: {lote: 'L1', caso: CASO_NOVO, estado: 'falha', motivo: 'Não foi possível ler os arquivos.', arquivos: []}});
  await mesa.esperar(10);
  await passo2(mesa, {nome: 'Obra da escola'});
  await soltar(mesa);
  mesa.pedidos[0].responder(200, {estado: 'enfileirado', lote: {lote: 'L1', caso: CASO_NOVO, estado: 'enfileirado', arquivos: []}});
  await mesa.esperar(40);
  assert.equal(mesa.janela.contextoCaso(), '', 'o seletor não fica numa apuração que não existe');
  assert.equal(mesa.$('nova-incerto').hidden, false);
  assert.equal(mesa.$('nova-incerto').textContent, 'Esta apuração não chegou a ser criada: o primeiro envio falhou. Recomece a Nova apuração.');
  assert.ok(!mesa.catalogo.some(c => c.id === CASO_NOVO));
  // B1 do Traço: continua sendo o passo 2 da Nova apuração, não a Documentos comum
  assert.equal(mesa.doc.body.dataset.nova, 'passo2'); assert.equal(mesa.$('area-titulo').textContent, 'Nova apuração'); assert.equal(mesa.$('area-descricao').textContent, 'Obra da escola');
  assert.equal(mesa.$('nova-aviso').hidden, false); assert.equal(mesa.$('nova-recomecar-linha').hidden, false);
  assert.equal(mesa.$('nova-recomecar').textContent, 'Recomeçar'); assert.ok(mesa.$('nova-recomecar').classList.contains('secondary'));
  assert.equal(mesa.$('nova-etapas-2').querySelector('[aria-current="step"]').textContent.trim(), '2 Documentos');
  mesa.$('nova-recomecar').click(); await mesa.esperar(4);
  assert.equal(mesa.$('area-nova').hidden, false, 'volta ao passo 1'); assert.equal(mesa.$('nova-nome').value, 'Obra da escola', 'com os campos preenchidos');
  assert.equal(mesa.$('nova-recomecar-linha').hidden, true); assert.equal(mesa.$('nova-incerto').hidden, true); assert.equal(mesa.doc.body.dataset.nova, undefined);
});

test('N4: com o envio no ar, sair pela barra diz a verdade (a apuração está sendo criada; sair não cancela) e oferece Ficar ou Sair e encontrá-la depois', async () => {
  const mesa = abrir(); await mesa.esperar(10);
  await passo2(mesa, {nome: 'Obra da escola'});
  await soltar(mesa);
  assert.equal(mesa.pedidos.length, 1, 'o envio está no ar (segurado)');
  mesa.$('ver-codex').click(); await mesa.esperar(4);
  const d = dialogo(mesa);
  assert.ok(d, 'pede confirmação');
  assert.equal(d.querySelector('.dialogo-titulo').textContent, 'A apuração está sendo criada');
  assert.ok(d.textContent.includes('Sair não cancela o envio: a apuração nasce assim mesmo, e você a encontra depois na Visão geral.'));
  assert.ok(!d.textContent.includes('Nada foi criado'), 'não diz que nada foi criado');
  assert.deepEqual(botoes(mesa).map(b => b.textContent), ['Ficar', 'Sair e encontrá-la depois']);
  botoes(mesa)[0].click(); await mesa.esperar(4);   // Ficar
  assert.equal(area(mesa), 'documentos'); assert.equal(mesa.janela.NovaApuracao.ativa(), true);
  mesa.$('ver-codex').click(); await mesa.esperar(4);
  botoes(mesa)[1].click(); await mesa.esperar(8);   // Sair e encontrá-la depois
  assert.equal(area(mesa), 'codex', 'saiu');
  mesa.catalogo.push({id: CASO_NOVO, titulo: 'Obra da escola', rodadas: []});
  mesa.pedidos[0].responder(200, {estado: 'enfileirado', lote: {lote: 'L1', caso: CASO_NOVO, estado: 'enfileirado', arquivos: []}});
  await mesa.esperar(40);
  assert.equal(area(mesa), 'codex', 'a apuração nasceu, mas a página em que a pessoa está não muda');
  assert.equal(mesa.janela.contextoCaso(), '', 'e o contexto dela não é trocado por trás');
  assert.ok([...mesa.$('contexto-caso').options].some(o => o.value === CASO_NOVO), 'a apuração está no seletor (e na Visão geral)');
  assert.equal(mesa.pedidos.length, 1, 'uma apuração só');
});

// --- B1 da Coruja (d25b20d..db4124d): o envio em JSON não cria a apuração duas vezes ----------------------------------------------------------------
test('B1 (a): com o lote em JSON ainda no ar, um segundo arquivo não manda outro cadastrar, Voltar fica desativado e a trava só solta no fim', async () => {
  let soltar = null, cadastros = 0;
  const mesa = abrir({fluxo: false, api: operacao => {
    if (operacao !== 'cadastrar') return undefined;
    cadastros += 1;
    return new Promise(resolver => { soltar = () => resolver({caso_id: CASO_NOVO, corpus_id: 'c1', recebidos: 1, novos: 1, duplicados: 0, total_documentos: 1, arquivos: [{nome: 'primeiro.pdf', estado: 'pronto'}], inventario: {}}); });
  }});
  await mesa.esperar(10);
  mesa.janela.FileReader = class { readAsDataURL() { this.result = 'data:;base64,AAAA'; this.onload(); } };
  await passo2(mesa, {nome: 'Obra da escola'});
  await soltar_arquivo(mesa, 'primeiro.pdf');
  await mesa.esperar(10);
  assert.equal(cadastros, 1, 'o primeiro lote está no ar');
  assert.equal(mesa.$('nova-voltar').disabled, true, 'Voltar fica desativado');
  assert.equal(mesa.janela.NovaApuracao.ocupado(), true); assert.equal(mesa.janela.Documentos.ocupado(), true, 'as duas travas seguem ativas');
  await soltar_arquivo(mesa, 'segundo.pdf');
  await mesa.esperar(10);
  assert.equal(cadastros, 1, 'o segundo arquivo não manda outro cadastrar com novo:true');
  soltar(); await mesa.esperar(30);
  assert.equal(mesa.janela.NovaApuracao.ocupado(), false); assert.equal(mesa.janela.Documentos.ocupado(), false);
  assert.equal(mesa.janela.contextoCaso(), CASO_NOVO);
});

test('B1 (b): o primeiro lote em JSON que termina em rede, 500, 502 ou 504 é incerto: aviso, e o reenvio pede confirmação antes de poder criar outra apuração', async () => {
  const respostas = {rede: () => { throw new TypeError('Failed to fetch'); }, 500: () => ({ok: false, status: 500, json: async () => ({estado: 'erro', erro: 'Falha interna.'})}),
    502: () => ({ok: false, status: 502, json: async () => { throw new SyntaxError('html'); }}), 504: () => ({ok: false, status: 504, json: async () => ({estado: 'erro', erro: 'Tempo esgotado.'})})};
  for (const [nome, resposta] of Object.entries(respostas)) {
    let cadastros = 0;
    const mesa = abrir({fluxo: false, postar: () => { cadastros += 1; return resposta(); }});
    await mesa.esperar(10);
    mesa.janela.FileReader = class { readAsDataURL() { this.result = 'data:;base64,AAAA'; this.onload(); } };
    await passo2(mesa, {nome: 'Obra da escola'});
    await soltar_arquivo(mesa, 'primeiro.pdf'); await mesa.esperar(20);
    assert.equal(cadastros, 1, nome);
    assert.equal(mesa.$('nova-incerto').hidden, false, nome);
    assert.equal(mesa.$('nova-incerto').textContent, 'Não sabemos se a apuração foi criada: a resposta do servidor não chegou. Confira a apuração na Visão geral antes de enviar de novo.', nome);
    assert.equal(mesa.$('nova-voltar').disabled, false, nome);
    await soltar_arquivo(mesa, 'primeiro.pdf'); await mesa.esperar(10);
    const d = dialogo(mesa);
    assert.ok(d, `${nome}: o reenvio pede confirmação`);
    assert.equal(d.querySelector('.dialogo-titulo').textContent, 'Enviar de novo pode criar outra apuração', nome);
    assert.equal(cadastros, 1, `${nome}: nada saiu antes da confirmação`);
    botoes(mesa)[0].click(); await mesa.esperar(8);   // Cancelar
    assert.equal(cadastros, 1, `${nome}: cancelar não envia`);
    await soltar_arquivo(mesa, 'primeiro.pdf'); await mesa.esperar(10);
    botoes(mesa)[1].click(); await mesa.esperar(20);   // Enviar mesmo assim
    assert.equal(cadastros, 2, `${nome}: confirmado, o reenvio sai`);
  }
  // uma recusa clara (400) não é incerta
  const claro = abrir({fluxo: false, postar: () => ({ok: false, status: 400, json: async () => ({estado: 'erro', erro: 'Nome inválido.'})})});
  await claro.esperar(10);
  claro.janela.FileReader = class { readAsDataURL() { this.result = 'data:;base64,AAAA'; this.onload(); } };
  await passo2(claro); await soltar_arquivo(claro, 'primeiro.pdf'); await claro.esperar(20);
  assert.equal(claro.$('nova-incerto').hidden, true); assert.match(claro.$('mesa-acervo-status').textContent, /Nome inválido\./);
});

function soltar_arquivo(mesa, nome) {
  const evento = new Evento('drop', {bubbles: true, cancelable: true});
  evento.dataTransfer = {files: [{name: nome, size: 500}]};
  mesa.$('documentos-zona').dispatchEvent(evento);
  return Promise.resolve();
}
