// Homologação ponta a ponta em modo hospedado (login real), headless Chrome atrás do proxy TLS de teste.
// Invocado por qa_homologacao.py; as senhas chegam só por VLADO_QA_CONTAS e nunca são gravadas.
const {chromium, request} = require('playwright');
const {irParaNovaApuracao} = require('./qa_navegacao.cjs');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs/promises');
const path = require('node:path');
const readline = require('node:readline');

const [origin, output, shots, chrome] = process.argv.slice(2);
const contas = JSON.parse(process.env.VLADO_QA_CONTAS);
const esperado = JSON.parse(process.env.VLADO_QA_ESPERADO);
const LONGO = 180000;

// Line channel to the Python harness (hash snapshots and server-side checks).
const linhas = readline.createInterface({input: process.stdin});
const aguardando = [];
linhas.on('line', linha => aguardando.shift()?.(JSON.parse(linha)));
function py(pedido) {
  return new Promise((resolve, reject) => {
    aguardando.push(resposta => resposta.ok ? resolve(resposta) : reject(new Error('Python: ' + resposta.erro)));
    process.stdout.write('@@PY ' + JSON.stringify(pedido) + '\n');
  });
}

const verificacoes = [], erros = [], bloqueios = [], pulados = [];
const marcar = (fluxo, texto) => { verificacoes.push({fluxo, verificacao: texto}); console.log(`ok [${fluxo}] ${texto}`); };
const ocultar = texto => Object.values(contas).reduce((t, c) => t.split(c.senha).join('***'), String(texto)).replace(/\/ativar\/[A-Za-z0-9_-]+/g, '/ativar/***');
const sha = async arquivo => crypto.createHash('sha256').update(await fs.readFile(arquivo)).digest('hex');
const semRolagem = page => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth);

async function contexto(browser, opcoes = {}) {
  // ignoreHTTPSErrors only here: the test proxy uses a throw-away self-signed certificate.
  const ctx = await browser.newContext({ignoreHTTPSErrors: true, acceptDownloads: true,
    viewport: {width: 1365, height: 1000}, ...opcoes});
  await ctx.addInitScript(() => { try { localStorage.setItem('vlado-idioma', 'pt'); } catch { /* blocked storage */ } });
  return ctx;
}
async function pagina(ctx, nome) {
  const page = await ctx.newPage();
  page.on('pageerror', e => erros.push(`${nome}: ${e.message}`));
  page.on('dialog', d => d.accept().catch(() => {}));
  return page;
}
// O formulário só tem o envio ligado depois das leituras de /api/entrada, e o entrar.js dá o foco ao e-mail logo em seguida: antes disso,
// um clique em "Entrar" vira envio nativo e recarrega a página vazia.
async function formularioPronto(page) {
  await page.locator('#entrar-secao:not([hidden])').waitFor();
  await page.waitForFunction(() => document.activeElement && document.activeElement.id === 'entrar-login', null, {timeout: 30000});
}
async function entrar(page, conta) {
  await page.goto(origin + '/entrar');
  await formularioPronto(page);
  await page.fill('#entrar-login', conta.login);
  await page.fill('#entrar-senha', conta.senha);
  await page.click('#entrar-enviar');
  await page.waitForURL(url => !url.pathname.startsWith('/entrar'), {timeout: 30000});
}
// Same-origin call with the page's own CSRF token: what any script in that browser could do.
const chamar = (page, operacao, dados) => page.evaluate(async ([operacao, dados]) => {
  const token = document.querySelector('meta[name="session-token"]')?.content || '';
  const r = await fetch('/api/' + operacao, {method: 'POST', credentials: 'same-origin',
    headers: {'Content-Type': 'application/json', 'X-Session-Token': token}, body: JSON.stringify(dados)});
  let corpo = {};
  try { corpo = await r.json(); } catch { /* binary or empty */ }
  return {status: r.status, codigo: corpo.codigo || null, erro: corpo.erro || null};
}, [operacao, dados]);
const sessao = page => page.evaluate(async () => (await fetch('/api/sessao', {credentials: 'same-origin'})).status);

// The desk's case lives in the header ("Apuração atual"); per-area selectors follow it.
async function escolherCaso(page, caso) {
  await page.locator(`#contexto-caso option[value="${caso}"]`).waitFor({state: 'attached'});
  if (await page.locator('#contexto-caso').inputValue() !== caso) await page.selectOption('#contexto-caso', caso);
  await page.waitForFunction(caso => document.querySelector('#codex-caso').value === caso, caso);
}
async function perguntar(page, caso, texto) {
  await escolherCaso(page, caso);
  await page.locator('#codex-pergunta:not([disabled])').waitFor();
  await page.fill('#codex-pergunta', texto);
  await page.locator('#codex-enviar:not([disabled])').waitFor();
  await page.click('#codex-enviar');
  await page.locator('#codex-status').filter({hasText: 'Execução concluída'}).waitFor({timeout: LONGO});
  await page.locator('#codex-fontes>details').first().waitFor({state: 'attached'});  // a drawer on phones
  // A lista de conversas é relida depois de "Execução concluída": o seletor passa a apontar para a conversa nova só então.
  await page.waitForFunction(() => /^[a-f0-9]{32}$/.test(document.querySelector('#codex-conversa').value), null, {timeout: 30000});
  const conversa = await page.locator('#codex-conversa').inputValue();
  assert.match(conversa, /^[a-f0-9]{32}$/);
  return conversa;
}
async function abrirFonte(page) {
  const fonte = page.locator('#codex-fontes>details').first();
  if (!await fonte.evaluate(el => el.open)) await fonte.locator(':scope>summary').click();
  const referencia = (await fonte.getAttribute('id')).replace(/^fonte-/, '');
  await fonte.locator(':scope>button').first().click();
  await page.locator('#original-dialogo[open]').waitFor();
  return referencia;
}
async function fecharOriginal(page) {
  await page.click('#original-fechar');
  await page.locator('#original-dialogo').waitFor({state: 'hidden'});
}

// Lista de Documentos: um objeto por linha (arquivo, identificador, SHA-256, estado de leitura), lido dos "Detalhes técnicos" da tabela.
const documentosDaLista = page => page.locator('#mesa-acervo-lista tbody tr').evaluateAll(linhas => linhas.map(l => {
  const dado = rotulo => [...l.querySelectorAll('.docs-tecnicos-dados dt')].find(dt => dt.textContent.trim() === rotulo)?.nextElementSibling?.textContent.trim() || '';
  const celula = l.querySelector('.docs-leitura');
  return {arquivo: dado('Arquivo recebido'), identificador: dado('Identificador'), sha256: dado('Hash (SHA-256)'),
    leitura: celula?.dataset.leitura || '', texto: celula?.textContent.trim() || ''};
}));

(async () => {
  await fs.mkdir(output, {recursive: true});
  await fs.mkdir(shots, {recursive: true});
  const browser = await chromium.launch({headless: true, ...(chrome ? {executablePath: chrome} : {})});
  const abertas = [];
  let atual = null;
  const resultado = {estado: 'falhou', natureza: 'dados sintéticos; provedor de IA simulado; sem chamada paga; modo hospedado com TLS de teste'};
  try {
    // ---------------------------------------------------------------- 1. Acesso
    const ctxAdmin = await contexto(browser);
    const admin = atual = await pagina(ctxAdmin, 'admin');
    abertas.push(admin);
    await admin.goto(origin + '/');
    assert.equal(new URL(admin.url()).pathname, '/entrar');
    await formularioPronto(admin);
    marcar('acesso', '"/" sem sessão redireciona para /entrar.');
    await admin.screenshot({path: path.join(shots, 'entrar.png')});

    await admin.fill('#entrar-login', contas.admin.login);
    await admin.fill('#entrar-senha', contas.admin.senha + 'x');
    await admin.click('#entrar-enviar');
    await admin.locator('#entrar-mensagem:not([hidden])').waitFor();
    const erroSenha = await admin.locator('#entrar-mensagem').innerText();
    await admin.fill('#entrar-login', 'login.inexistente');
    await admin.fill('#entrar-senha', 'qualquer-coisa-longa');
    await admin.click('#entrar-enviar');
    await admin.locator('#entrar-enviar:not([disabled])').waitFor();
    assert.equal(erroSenha, 'E-mail ou login e senha não conferem. Confira e tente de novo.');
    assert.equal(await admin.locator('#entrar-mensagem').innerText(), erroSenha);
    assert.equal(new URL(admin.url()).pathname, '/entrar');
    marcar('acesso', 'Senha errada e login inexistente mostram o mesmo erro genérico ("E-mail ou login e senha não conferem. Confira e tente de novo.").');

    await entrar(admin, contas.admin);
    await admin.locator('#mesa-ambiente:not([hidden])').waitFor();
    assert.equal(await admin.locator('#mesa-ambiente').innerText(), 'Homologação — dados sintéticos');
    assert.equal(await admin.locator('body').getAttribute('data-papel'), 'admin');
    marcar('acesso', 'Login do admin abre a Mesa com a faixa "Homologação — dados sintéticos" visível.');
    await admin.screenshot({path: path.join(shots, 'mesa-admin-faixa.png')});

    const antiga = (await ctxAdmin.cookies()).find(c => c.name === 'vlado_sessao');
    assert.ok(antiga && antiga.httpOnly && antiga.secure, 'cookie de sessão HttpOnly e Secure');
    await admin.locator('#mesa-sair:not([hidden])').click();
    await admin.waitForURL(url => url.pathname === '/entrar');
    const cliente = await request.newContext({ignoreHTTPSErrors: true, baseURL: origin,
      extraHTTPHeaders: {Cookie: `vlado_sessao=${antiga.value}`}});
    const reuso = await cliente.get('/api/sessao');
    const reusoCatalogo = await cliente.get('/api/catalogo');
    await cliente.dispose();
    assert.equal(reuso.status(), 401);
    assert.equal(reusoCatalogo.status(), 401);
    marcar('acesso', 'Sair volta para /entrar; o cookie da sessão antiga reapresentado recebe 401 (/api/sessao e /api/catalogo).');

    // ---------------------------------------------------------------- 2. Reportagem sintética (admin)
    await entrar(admin, contas.admin);
    // Lote 1 vai pela tela "Nova apuração" (Visão geral > Nova apuração): a área de envio de Documentos só serve a uma apuração que já existe.
    await irParaNovaApuracao(admin);
    await admin.locator('#area-cadastro:not([hidden])').waitFor();
    await admin.selectOption('#cadastro-caso', '');
    await admin.selectOption('#cadastro-natureza', 'sinteticos');
    await admin.fill('#cadastro-titulo-input', 'Reportagem sintética — Vila Serena');
    await admin.setInputFiles('#cadastro-arquivos', esperado.lotes.lote1.map(a => a.caminho));
    await admin.click('#enviar-documentos');
    const desfecho = await Promise.race([
      admin.locator('#cadastro-recibo:not([hidden])').waitFor({timeout: LONGO}).then(() => 'recibo', () => 'nada'),
      admin.locator('#cadastro-erro:not([hidden])').waitFor({timeout: LONGO}).then(() => 'erro', () => 'nada')]);
    let caso;
    if (desfecho === 'recibo') {
      const textoRecibo = await admin.locator('#cadastro-recibo').innerText();
      caso = await admin.locator('#cadastro-caso').inputValue();
      assert.match(caso, /^apuracao_[0-9a-f]{32}$/);
      assert.match(textoRecibo, /Recibo do lote: 2 de 2 arquivos/);
      assert.match(textoRecibo, /2 novos/);
    } else {
      const erroTela = desfecho === 'erro' ? (await admin.locator('#cadastro-erro').innerText()).trim() : 'sem recibo nem erro em ' + LONGO / 1000 + ' s';
      await admin.screenshot({path: path.join(shots, 'bloqueio-nova-apuracao.png'), fullPage: true});
      // Só a recusa conhecida vira bloqueio e deixa os demais passos rodarem; qualquer outro erro derruba a rodada aqui.
      if (!/identificador de uma apuração nova é escolhido pelo servidor/.test(erroTela)) throw new Error('Nova apuração: ' + erroTela);
      bloqueios.push({passo: 'Nova apuração pela interface (envio em fluxo, modo hospedado)', erro: erroTela,
        origem: 'a tela manda um identificador de apuração nova e o portão (scripts/autorizacao.py) o recusa'});
      console.log('BLOQUEIO [reportagem] Nova apuração pela interface: ' + erroTela);
      // Para os passos seguintes rodarem, o lote 1 é cadastrado pelo mesmo caminho do servidor, sem a tela: /api/cadastrar sem identificador.
      const arquivos = await Promise.all(esperado.lotes.lote1.map(async a => ({nome: a.nome, base64: (await fs.readFile(a.caminho)).toString('base64')})));
      const cadastro = await admin.evaluate(async ([titulo, arquivos]) => {
        const token = document.querySelector('meta[name="session-token"]')?.content || '';
        const r = await fetch('/api/cadastrar', {method: 'POST', credentials: 'same-origin',
          headers: {'Content-Type': 'application/json', 'X-Session-Token': token},
          body: JSON.stringify({novo: true, titulo, natureza: 'sinteticos', arquivos})});
        return {status: r.status, corpo: await r.json().catch(() => ({}))};
      }, ['Reportagem sintética — Vila Serena', arquivos]);
      assert.equal(cadastro.status, 200, 'cadastro do lote 1 pela API: ' + JSON.stringify(cadastro.corpo).slice(0, 300));
      caso = cadastro.corpo.caso_id;
      assert.match(caso, /^apuracao_[0-9a-f]{32}$/);
      await admin.goto(origin + '/?area=documentos');
      await admin.locator('#area-documentos:not([hidden])').waitFor();
      await admin.locator(`#contexto-caso option[value="${caso}"]`).waitFor({state: 'attached'});
      await admin.selectOption('#contexto-caso', caso);
    }
    // O recibo do lote só conta; hash, identificador e leitura de cada documento estão na lista de Documentos (W02, regra 7).
    await admin.click('#ver-documentos');
    await admin.locator('#mesa-acervo-lista tbody tr').first().waitFor({timeout: 30000});
    const docs = await documentosDaLista(admin);
    assert.equal(docs.length, 2);
    for (const [i, arquivo] of esperado.lotes.lote1.entries()) {
      const item = docs.find(d => d.arquivo === arquivo.nome);
      assert.ok(item, 'arquivo na lista de Documentos: ' + arquivo.nome);
      assert.equal(item.identificador, `D00${i + 1}`);
      assert.equal(item.sha256, arquivo.sha256, 'SHA-256 de Documentos = SHA-256 calculado em Python');
    }
    const digitalizado = docs.find(d => d.arquivo === esperado.digitalizado);
    if (esperado.ocr_disponivel) {
      assert.equal(digitalizado.leitura, 'ocr', 'o PDF digitalizado aparece como lido por OCR');
      assert.match(digitalizado.texto, /Lida por OCR/);
    } else {   // sem Tesseract e os idiomas nesta máquina: o PDF sem página com texto é "Sem texto lido"
      assert.equal(digitalizado.leitura, 'sem-texto', 'sem OCR, o PDF digitalizado aparece como "Sem texto lido"');
      pulados.push('OCR local: Tesseract ou idiomas ausentes nesta máquina; o PDF digitalizado saiu "Sem texto lido" e a leitura por OCR não foi verificada');
      console.log('PULADO [reportagem] ' + pulados[pulados.length - 1]);
    }
    assert.equal(docs.find(d => d.identificador === 'D001').leitura, 'texto', 'o PDF com texto nativo aparece como texto do próprio arquivo');
    marcar('reportagem', (desfecho === 'recibo' ? 'Lote 1 cadastrado pela interface num caso novo; recibo do lote "2 de 2 arquivos, 2 novos"; ' : 'Lote 1 cadastrado pela API (a tela de Nova apuração está bloqueada, ver bloqueios); ') + 'Documentos lista D001 e D002 com SHA-256 iguais aos calculados em Python.');
    marcar('reportagem', (esperado.ocr_disponivel ? 'Documentos mostra o PDF digitalizado como "Lida por OCR: confira números"' : 'Sem OCR na máquina, Documentos mostra o PDF digitalizado como "Sem texto lido"') + ' e o PDF com texto nativo como "Texto do próprio arquivo".');
    await admin.locator('#mesa-acervo-lista').screenshot({path: path.join(shots, 'recibo-ocr.png')});

    await admin.click('#ver-codex');
    const conversaAdmin = await perguntar(admin, caso, 'Qual é o valor global do contrato sintético e quem é a contratada?');
    assert.match(await admin.locator('#codex-mensagens').innerText(), /valor 123/);
    assert.ok(await admin.locator('#codex-mensagens .source-citation').count() >= 1, 'citação clicável na resposta');
    marcar('reportagem', 'Pergunta pelo provedor simulado termina "Execução concluída" com resposta e fonte citada.');
    await admin.screenshot({path: path.join(shots, 'resposta-com-fonte.png'), fullPage: true});
    await abrirFonte(admin);
    await admin.locator('#original-conteudo .pdf-text-layer').filter({hasText: 'Horizonte Azul'}).waitFor({timeout: 30000});
    const baixado = admin.waitForEvent('download');
    await admin.click('#original-baixar');
    const contrato = esperado.lotes.lote1[0];
    assert.equal(await sha(await (await baixado).path()), contrato.sha256);
    await admin.screenshot({path: path.join(shots, 'original-citado.png')});
    await fecharOriginal(admin);
    marcar('reportagem', 'Original citado abre no visualizador de PDF com o texto do contrato; o download tem o SHA-256 do arquivo enviado.');

    await admin.getByRole('button', {name: 'Consultar achados desta análise'}).first().click();
    await admin.locator('#area-achados:not([hidden])').waitFor();
    await admin.locator('#achados-resultados .finding-choice').first().waitFor({timeout: 30000});
    await admin.locator('#achados-resultados .human-review-actions button').first().click();
    await admin.locator('#revisao-dialogo[open]').waitFor();
    await admin.locator('#revisao-salvar:not([disabled])').waitFor();
    assert.equal(await admin.locator('#revisao-estado option[value="conferida_no_original"]').evaluate(el => el.disabled), true,
      '"Conferida no original" bloqueada antes de abrir o original');
    await admin.locator('#revisao-fontes .review-evidence button').first().click();
    await admin.locator('#original-dialogo[open]').waitFor();
    await fecharOriginal(admin);
    await admin.waitForFunction(() => !document.querySelector('#revisao-estado option[value="conferida_no_original"]').disabled);
    await admin.selectOption('#revisao-estado', 'conferida_no_original');
    await admin.fill('#revisao-observacao', 'Valor conferido no PDF sintético durante a homologação.');
    await admin.click('#revisao-salvar');
    await admin.locator('#revisao-dialogo').waitFor({state: 'hidden'});
    await admin.locator('#achados-revisao-feedback').filter({hasText: 'Marcação salva: Conferida no original'}).waitFor();
    marcar('reportagem', 'Conferência de achado: "Conferida no original" só libera depois de abrir o original; avaliação salva.');

    await admin.locator('#achados-resultados .finding-open').first().click();
    await admin.locator('#achados-inspecao:not([hidden])').waitFor();
    await admin.locator('#achados-inspecao .evidence').getByRole('button', {name: 'Inserir em nota'}).first().click();
    await admin.locator('#apuracao-adicionar-dialogo[open]').waitFor();
    await admin.locator('#apuracao-adicionar-salvar:not([disabled])').waitFor();
    const trechoInserido = (await admin.locator('#apuracao-adicionar-texto').innerText()).trim();
    assert.ok(trechoInserido.length > 5, 'trecho com fonte para inserir');
    await admin.click('#apuracao-adicionar-salvar');
    await admin.locator('#apuracao-adicionar-dialogo').waitFor({state: 'hidden'});
    await admin.click('#ver-apuracao');
    await admin.locator('#area-apuracao:not([hidden])').waitFor();
    await admin.locator('#apuracao-notas button').first().waitFor();
    await admin.locator('#apuracao-notas button').first().click();
    await admin.locator('#apuracao-vditor .vditor-wysiwyg>.vditor-reset').waitFor({timeout: 30000});
    await admin.waitForFunction(t => document.querySelector('#apuracao-texto').value.includes(t.slice(0, 20)), trechoInserido);
    assert.match(await admin.locator('#apuracao-texto').inputValue(), /\[Fonte/);
    await admin.locator('#apuracao-fontes .note-source-doc').first().waitFor({state: 'attached'});
    await admin.locator('#apuracao-vditor .vditor-wysiwyg>.vditor-reset').click();
    await admin.keyboard.press('Control+End');
    await admin.keyboard.type(' Conferido na homologação.');
    await admin.waitForFunction(() => document.querySelector('#apuracao-salvamento').dataset.estado === 'salvo', null, {timeout: 20000});
    assert.match(await admin.locator('#apuracao-salvamento').innerText(), /^Nota salva às \d{2}:\d{2}$/);
    marcar('reportagem', 'Trecho com fonte inserido numa nota do Caderno; edição salva com "Nota salva às HH:MM".');
    await admin.screenshot({path: path.join(shots, 'caderno-nota-com-fonte.png')});

    await py({cmd: 'instantaneo', nome: 'r001', caso, rodada: 'R001'});
    // Lote 2 no mesmo caso: pela área de envio da tela Documentos, que manda para a apuração escolhida no cabeçalho.
    await admin.click('#ver-documentos');
    await admin.locator('#area-documentos:not([hidden])').waitFor();
    assert.equal(await admin.locator('#contexto-caso').inputValue(), caso, 'destino do envio = caso aberto');
    await admin.setInputFiles('#documentos-zona input[type=file]', esperado.lotes.lote2.map(a => a.caminho));
    await admin.locator('#documentos-recibo:not([hidden])').waitFor({timeout: LONGO});
    assert.match(await admin.locator('#documentos-recibo').innerText(), /Recibo do lote: 1 de 1 arquivos/);
    await admin.waitForFunction(() => document.querySelectorAll('#mesa-acervo-lista tbody tr').length === 3, null, {timeout: 30000});
    const docs2 = await documentosDaLista(admin);
    const d3 = docs2.find(d => d.identificador === 'D003');
    assert.ok(d3, 'D003 na lista de Documentos');
    assert.equal(d3.sha256, esperado.lotes.lote2[0].sha256);
    assert.equal(d3.arquivo, esperado.lotes.lote2[0].nome);
    const comparacao = await py({cmd: 'comparar', nome: 'r001'});
    assert.ok(comparacao.total > 0);
    assert.deepEqual(comparacao.alterados, []);
    assert.deepEqual(comparacao.removidos, []);
    await admin.click('#ver-codex');
    await escolherCaso(admin, caso);
    await admin.locator(`#codex-conversa option[value="${conversaAdmin}"]`).waitFor({state: 'attached'});
    if (!await admin.locator('#codex-acervo').evaluate(el => el.open)) await admin.click('#codex-acervo>summary');
    await admin.selectOption('#codex-conversa', conversaAdmin);
    await admin.locator('#codex-mensagens').filter({hasText: 'Qual é o valor global do contrato sintético'}).waitFor();
    await admin.locator('#codex-fontes>details').first().waitFor();
    marcar('reportagem', `Lote 2 no mesmo caso (D003, SHA-256 conferido); a conversa anterior continua listada e abre; ${comparacao.total} arquivos da rodada R001 com SHA-256 inalterado.`);

    // ---------------------------------------------------------------- 3. Papéis
    const ctxA = await contexto(browser);
    const a = atual = await pagina(ctxA, 'convidada A');
    abertas.push(a);
    await entrar(a, contas.a);
    assert.match(a.url(), /area=codex/);
    assert.equal(await a.locator('body').getAttribute('data-papel'), 'convidado');
    for (const area of ['#ver-cadastro', '#ver-apuracao', '#ver-gerenciar', '#ver-achados', '#ver-documentos']) {
      assert.equal(await a.locator(area).isVisible(), false, 'área de admin visível: ' + area);
    }
    await a.locator('#codex-caso option[value="alpha"]').waitFor({state: 'attached'});
    assert.deepEqual(await a.locator('#codex-caso option').evaluateAll(os => os.map(o => o.value).filter(Boolean)), ['alpha']);
    marcar('papeis', 'Convidada A entra direto em Perguntar à IA, vê só o caso X (alpha) e não vê cadastro, Caderno nem achados.');
    const conversaA = await perguntar(a, 'alpha', 'O que declara o documento sintético do caso X?');
    const referenciaA = await abrirFonte(a);
    await a.locator('#original-conteudo pre').filter({hasText: 'Alfabeto'}).waitFor();
    await fecharOriginal(a);
    assert.equal((await py({cmd: 'conversa', id: conversaA})).dono, contas.a.id);
    marcar('papeis', 'Convidada A pergunta no caso X e abre a fonte citada na própria conversa (original com o texto do documento).');
    await a.screenshot({path: path.join(shots, 'convidada-a.png'), fullPage: true});

    // 4. 390 px: login and one pass through the question, with no horizontal scroll.
    const ctxCel = await contexto(browser, {viewport: {width: 390, height: 844}, isMobile: true, hasTouch: true, deviceScaleFactor: 2});
    const cel = atual = await pagina(ctxCel, 'celular');
    abertas.push(cel);
    await cel.goto(origin + '/');
    await formularioPronto(cel);
    assert.equal(await semRolagem(cel), true, 'rolagem horizontal na página de entrada (390 px)');
    await cel.screenshot({path: path.join(shots, 'celular-390-entrar.png')});
    await entrar(cel, contas.a);
    await cel.locator('#area-codex:not([hidden])').waitFor();
    assert.equal(await semRolagem(cel), true, 'rolagem horizontal na Mesa (390 px)');
    await perguntar(cel, 'alpha', 'Pergunta sintética feita no celular.');
    assert.equal(await semRolagem(cel), true, 'rolagem horizontal depois da resposta (390 px)');
    await cel.screenshot({path: path.join(shots, 'celular-390-pergunta.png'), fullPage: true});
    marcar('celular', 'Em 390 px: entrada, Mesa e pergunta concluída sem rolagem horizontal.');

    const ctxB = await contexto(browser);
    const b = atual = await pagina(ctxB, 'convidado B');
    abertas.push(b);
    await entrar(b, contas.b);
    await b.locator('#codex-caso option[value="beta"]').waitFor({state: 'attached'});
    assert.deepEqual(await b.locator('#codex-caso option').evaluateAll(os => os.map(o => o.value).filter(Boolean)), ['beta']);
    assert.equal(await b.locator(`#codex-conversa option[value="${conversaA}"]`).count(), 0);
    const recusas = {
      'codex-eventos': await chamar(b, 'codex-eventos', {conversa: conversaA, cursor: 0}),
      'codex-original': await chamar(b, 'codex-original', {conversa: conversaA, referencia: referenciaA}),
      'codex-listar alpha': await chamar(b, 'codex-listar', {caso: 'alpha'}),
      'apuracao-exportar': await chamar(b, 'apuracao-exportar', {caso: 'beta', formato: 'md'}),
      'apuracao-notas': await chamar(b, 'apuracao-notas', {caso: 'beta'}),
    };
    for (const [nome, r] of Object.entries(recusas)) assert.ok([400, 403, 404].includes(r.status), `${nome} deveria ser recusado: ${JSON.stringify(r)}`);
    assert.equal(recusas['apuracao-exportar'].status, 403);
    assert.equal(recusas['apuracao-notas'].status, 403);
    // O portão único (scripts/autorizacao.py) responde 404 "caso_indisponivel" igual para caso alheio e caso inexistente: não revela que o caso existe.
    assert.equal(recusas['codex-listar alpha'].status, 404);
    assert.equal(recusas['codex-listar alpha'].codigo, 'caso_indisponivel');
    for (const nome of ['codex-eventos', 'codex-original']) assert.equal(recusas[nome].codigo, 'conversa_indisponivel', nome);
    const permitido = await chamar(b, 'codex-listar', {caso: 'beta'});
    assert.equal(permitido.status, 200, 'controle: a mesma chamada no caso liberado funciona');
    resultado.recusas_convidado_b = recusas;
    marcar('papeis', 'Convidado B não vê o caso X nem a conversa de A; fetch direto a codex-eventos/codex-original com a conversa de A, codex-listar do caso X, apuracao-exportar e apuracao-notas são recusados.');
    await b.screenshot({path: path.join(shots, 'convidado-b.png')});

    // A tela "Contas de acesso" e as chamadas contas-* saíram (P30; Tranca 1be9d53, Lume 599e9e2). Os passos que dependiam
    // dela (retirar o caso X de A, desativar B, recuperar o acesso de A e ver as sessões caírem) voltam pela Equipe e pelo
    // Convidar do Vitral quando entrarem; até lá a homologação cobre só o lado de quem recebe o acesso (A e B acima).
    // As sessões de A, B e do celular terminam sem passo de encerramento: cada contexto se fecha com o navegador.

    assert.deepEqual(erros, []);
    Object.assign(resultado, {estado: bloqueios.length ? 'bloqueado' : 'aprovado', caso_reportagem: caso, verificacoes, erros_js: erros, bloqueios, pulados});
    if (bloqueios.length) {
      await fs.writeFile(path.join(output, 'resultado.json'), JSON.stringify(resultado, null, 2));
      throw new Error('Homologação com bloqueios: ' + bloqueios.map(b => b.passo + ' → ' + b.erro).join(' | '));
    }
    await fs.writeFile(path.join(output, 'resultado.json'), JSON.stringify(resultado, null, 2));
    console.log(`QA homologação (navegador): OK (${verificacoes.length} verificações)`);
  } catch (error) {
    if (atual) await atual.screenshot({path: path.join(output, 'falha.png'), fullPage: true}).catch(() => {});
    Object.assign(resultado, {erro: ocultar(error && error.stack || error), verificacoes, erros_js: erros});
    await fs.writeFile(path.join(output, 'resultado.json'), JSON.stringify(resultado, null, 2));
    throw error;
  } finally {
    linhas.close();
    await browser.close();
  }
})().catch(error => { console.error(ocultar(error && error.stack || error)); process.exitCode = 1; });
