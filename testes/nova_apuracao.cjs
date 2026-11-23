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

function abrir({idioma = 'pt', casos = [ALFA], url = 'http://127.0.0.1:8765/'} = {}) {
  const pedidos = [];
  class XHR {
    constructor() { this.ouvintes = {}; this.upload = {addEventListener() {}}; pedidos.push(this); }
    open() {} setRequestHeader() {} addEventListener(tipo, f) { this.ouvintes[tipo] = f; } send(corpo) { this.corpo = corpo; }
    responder(status, corpo) { this.status = status; this.responseText = JSON.stringify(corpo); this.ouvintes.load(); }
  }
  const catalogo = [...casos];
  const mesa = criarMesa({idioma, armazenamento: idioma === 'en' ? {'vlado-idioma': 'en'} : {}, catalogo, url,
    api: operacao => ({inventario: {caso_id: CASO_NOVO, corpus_id: 'c1', total_documentos: 1, documentos: []}, 'codex-listar': {conversas: []}}[operacao] || {}),
    preparar: janela => {
      janela.XMLHttpRequest = XHR; janela.TextEncoder = TextEncoder;
      janela.setTimeout = (funcao, ms, ...resto) => (ms === 1500 ? setImmediate(funcao) : setTimeout(funcao, ms, ...resto));
      const original = janela.fetch;
      janela.fetch = async (endereco, opcoes) => {
        if (String(endereco) === '/api/integracao') return {ok: true, json: async () => ({envio_fluxo: true})};
        if (String(endereco) === '/api/catalogo') return {ok: true, json: async () => ({casos: catalogo})};
        if (String(endereco).startsWith('/api/fila?lote=')) {
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
  assert.equal(area(mesa), 'nova'); assert.equal(mesa.$('area-nova').hidden, false); assert.equal(mesa.$('area-cadastro').hidden, true, 'a área antiga não abre');
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
