// Homologação ponta a ponta em modo hospedado (login real), headless Chrome atrás do proxy TLS de teste.
// Invocado por qa_homologacao.py; as senhas chegam só por VLADO_QA_CONTAS e nunca são gravadas.
const {chromium, request} = require('playwright');
const {irParaCadastro, irParaGerenciar} = require('./qa_navegacao.cjs');
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

const verificacoes = [], erros = [];
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
async function entrar(page, conta) {
  await page.goto(origin + '/entrar');
  await page.locator('#entrar-secao:not([hidden])').waitFor();
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
function contaNaLista(page, nome) {
  return page.locator('#acesso-lista>li').filter({has: page.getByRole('heading', {name: nome, exact: true})});
}

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
    await admin.locator('#entrar-secao:not([hidden])').waitFor();
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
    assert.equal(erroSenha, 'Login ou senha incorretos.');
    assert.equal(await admin.locator('#entrar-mensagem').innerText(), erroSenha);
    assert.equal(new URL(admin.url()).pathname, '/entrar');
    marcar('acesso', 'Senha errada e login inexistente mostram o mesmo erro genérico ("Login ou senha incorretos.").');

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
    await irParaCadastro(admin);
    await admin.locator('#area-cadastro:not([hidden])').waitFor();
    await admin.selectOption('#cadastro-caso', '');
    await admin.selectOption('#cadastro-natureza', 'sinteticos');
    await admin.fill('#cadastro-titulo-input', 'Reportagem sintética — Vila Serena');
    await admin.setInputFiles('#cadastro-arquivos', esperado.lotes.lote1.map(a => a.caminho));
    await admin.click('#enviar-documentos');
    await admin.locator('#cadastro-recibo:not([hidden])').waitFor({timeout: LONGO});
    const recibo = await admin.locator('#cadastro-recibo pre').evaluateAll(els => els.map(el => JSON.parse(el.textContent)));
    const textoRecibo = await admin.locator('#cadastro-recibo').innerText();
    const caso = await admin.locator('#cadastro-caso').inputValue();
    assert.match(caso, /^apuracao_[0-9a-f]{32}$/);
    assert.equal(recibo.length, 2);
    assert.match(textoRecibo, /Envio conferido: 2 de 2 arquivo/);
    for (const [i, arquivo] of esperado.lotes.lote1.entries()) {
      const item = recibo.find(r => r.nome_recebido === arquivo.nome);
      assert.ok(item, 'arquivo no recibo: ' + arquivo.nome);
      assert.equal(item.documento_id, `D00${i + 1}`);
      assert.equal(item.sha256, arquivo.sha256, 'SHA-256 do recibo = SHA-256 calculado em Python');
      assert.equal(item.estado, 'cadastrado');
    }
    const digitalizado = recibo.find(r => r.nome_recebido === esperado.digitalizado);
    assert.deepEqual(digitalizado.extracao_pdf.paginas_ocr, [1]);
    assert.deepEqual(digitalizado.extracao_pdf.paginas_texto_nativo, []);
    assert.deepEqual(recibo.find(r => r.documento_id === 'D001').extracao_pdf.paginas_ocr, []);
    assert.match(textoRecibo, /Reconhecidas por OCR: página\(s\) 1/);
    assert.match(textoRecibo, /Páginas: 1 com texto nativo · 1 por OCR · 0 sem texto · 0 com falha/);
    marcar('reportagem', 'Lote 1 cadastrado pela interface num caso novo; recibo lista 2 arquivos (D001, D002) com SHA-256 iguais aos calculados em Python.');
    marcar('reportagem', 'Recibo mostra o PDF digitalizado com a página 1 reconhecida por OCR local e o PDF com texto nativo sem OCR.');
    await admin.locator('#cadastro-recibo').screenshot({path: path.join(shots, 'recibo-ocr.png')});

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
    await irParaCadastro(admin);
    await admin.locator('#area-cadastro:not([hidden])').waitFor();
    assert.equal(await admin.locator('#cadastro-caso').inputValue(), caso, 'destino do envio = caso aberto');
    await admin.setInputFiles('#cadastro-arquivos', esperado.lotes.lote2.map(a => a.caminho));
    await admin.click('#enviar-documentos');
    await admin.locator('#cadastro-recibo:not([hidden])').waitFor({timeout: LONGO});
    const recibo2 = await admin.locator('#cadastro-recibo pre').evaluateAll(els => els.map(el => JSON.parse(el.textContent)));
    assert.equal(recibo2.length, 1);
    assert.equal(recibo2[0].documento_id, 'D003');
    assert.equal(recibo2[0].sha256, esperado.lotes.lote2[0].sha256);
    assert.match(await admin.locator('#cadastro-recibo').innerText(), /3 documento\(s\) no caso/);
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
    assert.equal(await a.locator('#acesso-painel').isVisible(), false);
    await a.locator('#codex-caso option[value="alpha"]').waitFor({state: 'attached'});
    assert.deepEqual(await a.locator('#codex-caso option').evaluateAll(os => os.map(o => o.value).filter(Boolean)), ['alpha']);
    marcar('papeis', 'Convidada A entra direto em Perguntar à IA, vê só o caso X (alpha) e não vê cadastro, Caderno, achados nem contas.');
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
    await cel.locator('#entrar-secao:not([hidden])').waitFor();
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
    assert.equal(recusas['codex-listar alpha'].codigo, 'caso_nao_liberado');
    for (const nome of ['codex-eventos', 'codex-original']) assert.equal(recusas[nome].codigo, 'conversa_indisponivel', nome);
    const permitido = await chamar(b, 'codex-listar', {caso: 'beta'});
    assert.equal(permitido.status, 200, 'controle: a mesma chamada no caso liberado funciona');
    resultado.recusas_convidado_b = recusas;
    marcar('papeis', 'Convidado B não vê o caso X nem a conversa de A; fetch direto a codex-eventos/codex-original com a conversa de A, codex-listar do caso X, apuracao-exportar e apuracao-notas são recusados.');
    await b.screenshot({path: path.join(shots, 'convidado-b.png')});

    atual = admin;
    await irParaGerenciar(admin);
    await admin.locator('#acesso-painel:not([hidden])').waitFor();
    const linhaA = contaNaLista(admin, contas.a.nome);
    await linhaA.getByRole('button', {name: 'Alterar apurações'}).click();
    await linhaA.locator('form select').selectOption(['beta']);
    await linhaA.getByRole('button', {name: 'Salvar alterações'}).click();
    await admin.locator('#acesso-mensagem').filter({hasText: 'Acesso alterado'}).waitFor();
    const depoisDeRetirar = {
      'codex-eventos da conversa do caso X': await chamar(a, 'codex-eventos', {conversa: conversaA, cursor: 0}),
      'codex-original da conversa do caso X': await chamar(a, 'codex-original', {conversa: conversaA, referencia: referenciaA}),
      'codex-perguntar no caso X': await chamar(a, 'codex-perguntar', {caso: 'alpha', pergunta: 'Ainda posso?'}),
    };
    for (const [nome, r] of Object.entries(depoisDeRetirar)) assert.ok([400, 403].includes(r.status), `${nome}: ${JSON.stringify(r)}`);
    assert.equal(depoisDeRetirar['codex-perguntar no caso X'].codigo, 'caso_nao_liberado');
    assert.equal(depoisDeRetirar['codex-eventos da conversa do caso X'].codigo, 'conversa_indisponivel');
    resultado.recusas_apos_retirar_caso = depoisDeRetirar;
    await a.reload();
    await a.locator('#codex-caso option[value="beta"]').waitFor({state: 'attached'});
    assert.equal(await a.locator('#codex-caso option[value="alpha"]').count(), 0);
    marcar('papeis', 'Admin retira o caso X de A pela interface de contas; a próxima ação de A no caso X (eventos, original, pergunta) é recusada e o caso some da lista.');

    await contaNaLista(admin, contas.b.nome).getByRole('button', {name: 'Desativar'}).click();
    await admin.locator('#acesso-mensagem').filter({hasText: 'Conta desativada'}).waitFor();
    const bDepois = await chamar(b, 'codex-listar', {caso: 'beta'});
    assert.ok([401, 403].includes(bDepois.status), JSON.stringify(bDepois));
    assert.equal(await sessao(b), 401);
    marcar('papeis', `Admin desativa B pela interface; a próxima requisição de B recebe ${bDepois.status} e /api/sessao 401.`);

    await contaNaLista(admin, contas.a.nome).getByRole('button', {name: 'Recuperar acesso'}).click();
    await admin.locator('#acesso-link-caixa:not([hidden])').waitFor();
    await admin.click('#acesso-link-fechar');  // the activation link is never captured nor recorded
    assert.equal(await admin.locator('#acesso-link').inputValue(), '');
    assert.equal(await sessao(a), 401);
    assert.equal(await sessao(cel), 401);
    await a.reload();
    await a.waitForURL(url => url.pathname === '/entrar');
    marcar('papeis', 'Recuperar acesso de A encerra as sessões abertas (desktop e celular: 401) e o recarregamento leva A para /entrar.');
    await admin.screenshot({path: path.join(shots, 'contas-admin.png')});

    assert.deepEqual(erros, []);
    Object.assign(resultado, {estado: 'aprovado', caso_reportagem: caso, verificacoes, erros_js: erros});
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
