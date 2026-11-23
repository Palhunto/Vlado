// Homologação ponta a ponta em modo hospedado (login real), headless Chrome atrás do proxy TLS de teste.
// Invocado por qa_homologacao.py; as senhas chegam só por VLADO_QA_CONTAS e nunca são gravadas.
const {chromium, request} = require('playwright');
const {criarApuracao, enviarArquivos} = require('./qa_navegacao.cjs');
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

const verificacoes = [], erros = [], pulados = [];
const marcar = (fluxo, texto) => { verificacoes.push({fluxo, verificacao: texto}); console.log(`ok [${fluxo}] ${texto}`); };
const ocultar = texto => Object.values(contas).reduce((t, c) => t.split(c.senha).join('***'), String(texto)).replace(/\/(ativar|redefinir)\/[A-Za-z0-9_-]+/g, '/$1/***');
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
// --- segundo fator (contas-o2 9e79e25): no piloto, dono e editor entram numa página da pendência até cadastrar o fator ----------------------------
// O código do aplicativo é calculado aqui, a partir da chave que a tela mostra (RFC 6238: HMAC-SHA1, passo de 30 s, 6 dígitos), como faria a pessoa com o celular.
function totp(segredo, desvio = 0) {
  const alfabeto = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
  let bits = '';
  for (const c of segredo.replace(/=+$/, '')) bits += alfabeto.indexOf(c).toString(2).padStart(5, '0');
  const bytes = Buffer.from(bits.match(/.{8}/g).map(b => parseInt(b, 2)));
  const contador = Buffer.alloc(8); contador.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 1000 / 30) + desvio));
  const h = crypto.createHmac('sha1', bytes).update(contador).digest();
  const o = h[19] & 0xf;
  return String(((h[o] & 0x7f) << 24 | h[o + 1] << 16 | h[o + 2] << 8 | h[o + 3]) % 1000000).padStart(6, '0');
}
const fatores = new Map();   // login -> {segredo, codigos}: o que a tela mostrou no cadastro, para os logins seguintes
// Depois de entrar: se o servidor levou à página da pendência (/conta/segundo-fator), faz os três passos do cadastro. Devolve true se cadastrou.
async function cadastrarFatorSeExigido(page, conta) {
  const exigido = await page.waitForURL(url => url.pathname === '/conta/segundo-fator', {timeout: 10000}).then(() => true, () => false);
  if (!exigido) return false;
  const secao = '#pendencia-secao';
  await page.locator(`${secao}:not([hidden]) h1`).waitFor();
  await page.fill(`${secao} input[type="password"]`, conta.senha);
  await page.click(`${secao} .fator-principal`);
  await page.locator(`${secao} svg`).waitFor();
  const segredo = (await page.textContent(`${secao} .fator-chave`)).replace(/\s+/g, '');
  assert.match(segredo, /^[A-Z2-7]{32}$/);
  await page.fill(`${secao} input[type="text"]`, totp(segredo));
  await page.click(`${secao} .fator-principal`);
  await page.locator(`${secao} .fator-codigos`).waitFor();
  const codigos = await page.locator(`${secao} .fator-codigo`).allTextContents();
  assert.equal(codigos.length, 10);
  fatores.set(conta.login, {segredo, codigos});
  await page.click(`${secao} .fator-guardei`);
  await page.locator(secao).filter({hasText: 'Segundo fator ativado.'}).waitFor();
  await Promise.all([page.waitForURL(url => url.pathname !== '/conta/segundo-fator', {timeout: 20000}), page.getByRole('button', {name: 'Abrir a Mesa'}).click()]);
  return true;
}
// `fator`: a conta ainda não tem o segundo fator e o piloto o exige (dono e editor): cadastra pela página da pendência. Com o fator já cadastrado,
// o Entrar pede o código do aplicativo num segundo passo (#fator-codigo), calculado da chave guardada no cadastro (a janela seguinte, como o teste do Vitral).
async function entrar(page, conta, {fator = false} = {}) {
  await page.goto(origin + '/entrar');
  await formularioPronto(page);
  await page.fill('#entrar-login', conta.login);
  await page.fill('#entrar-senha', conta.senha);
  await page.click('#entrar-enviar');
  const passo = await Promise.race([
    page.waitForURL(url => !url.pathname.startsWith('/entrar'), {timeout: 30000}).then(() => 'entrou', () => 'nada'),
    page.locator('#fator-secao:not([hidden])').waitFor({timeout: 30000}).then(() => 'codigo', () => 'nada')]);
  if (passo === 'codigo') {
    const guardado = fatores.get(conta.login);
    assert.ok(guardado, 'o Entrar pediu o código do aplicativo de uma conta que o roteiro não cadastrou: ' + conta.login);
    await page.fill('#fator-codigo', totp(guardado.segredo, 1));
    await Promise.all([page.waitForURL(url => !url.pathname.startsWith('/entrar'), {timeout: 30000}), page.click('#fator-enviar')]);
  } else assert.equal(passo, 'entrou', 'o login não terminou em 30 s');
  if (fator) await cadastrarFatorSeExigido(page, conta);
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
  // O campo de pergunta fica recolhido atrás de "Escrever pergunta" (no celular e com uma resposta na tela): abre quando está escondido.
  const alternar = page.locator('#desktop-composicao-alternar');
  if (!await page.locator('#codex-pergunta').isVisible() && await alternar.isVisible()) await alternar.click();
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

// --- Equipe (Minha conta > Equipe) ------------------------------------------------------------------------------------------------------------
async function abrirEquipe(page) {
  await page.goto(origin + '/?area=configuracoes');
  await page.locator('#conta-aba-equipe').waitFor({timeout: 30000});
  await page.click('#conta-aba-equipe');
  await page.locator('tr', {hasText: 'Gerenciar'}).first().waitFor({timeout: 30000});
}
// Abre o painel "Gerenciar" da pessoa (apurações, teto e acesso; #equipe-gerenciar-<id da conta>) e o devolve.
async function gerenciar(page, conta) {
  const painel = page.locator('#equipe-gerenciar-' + conta.id);
  if (!await painel.count()) await page.locator('tr', {hasText: conta.nome}).getByRole('button', {name: 'Gerenciar'}).click();
  await painel.waitFor();
  return painel;
}
// As operações sensíveis pedem a senha de quem age num diálogo (#dialogo-senha de conta.js): preenche e confirma, se ele aparecer.
async function confirmarSeSenhaPedida(page, senha) {
  const caixa = page.locator('dialog.dialogo[open]').last();
  if (!await caixa.waitFor({timeout: 5000}).then(() => true, () => false)) return false;
  const campo = caixa.locator('input[type="password"]');
  if (await campo.count()) await campo.fill(senha);
  await caixa.locator('.dialogo-acoes button:not(.secondary)').click();
  await caixa.waitFor({state: 'hidden'});
  return true;
}
// A coluna "Apurações" da linha da pessoa passa a ter (e a não ter) os casos pedidos.
async function esperarApuracoesDa(page, nome, {tem, naoTem}) {
  await page.waitForFunction(([nome, tem, naoTem]) => {
    const linha = [...document.querySelectorAll('tr')].find(l => l.innerText.includes(nome));
    const texto = linha ? linha.innerText : '';
    return texto.includes('Caso sintético ' + tem) && !texto.includes('Caso sintético ' + naoTem);
  }, [nome, tem, naoTem], {timeout: 30000});
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

    await entrar(admin, contas.admin, {fator: true});
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
    // Lote 1: Visão geral > Nova apuração (passo 1) > Continuar para documentos (passo 2), e o primeiro lote enviado cria a apuração.
    await criarApuracao(admin, {nome: 'Reportagem sintética — Vila Serena', natureza: 'sinteticos'});
    await enviarArquivos(admin, esperado.lotes.lote1.map(a => a.caminho), {timeout: LONGO});
    const textoRecibo = await admin.locator('#documentos-recibo').innerText();
    const caso = await admin.locator('#contexto-caso').inputValue();
    assert.match(caso, /^apuracao_[0-9a-f]{32}$/);
    assert.match(textoRecibo, /Recibo do lote: 2 de 2 arquivos/);
    assert.match(textoRecibo, /2 novos/);
    // O recibo do lote só conta; hash, identificador e leitura de cada documento estão na lista de Documentos (W02, regra 7).
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
    marcar('reportagem', 'Lote 1 enviado pela Nova apuração (o primeiro lote cria a apuração); recibo do lote "2 de 2 arquivos, 2 novos"; Documentos lista D001 e D002 com SHA-256 iguais aos calculados em Python.');
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
    await enviarArquivos(admin, esperado.lotes.lote2.map(a => a.caminho), {timeout: LONGO});
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

    // ---------------------------------------------------------------- 4. Equipe (Minha conta > Equipe): o dono retira, desativa e recupera
    // A tela "Contas de acesso" saiu (P30); o que ela fazia vive na Equipe (W09). As operações sensíveis pedem a senha de quem age (#dialogo-senha).
    atual = admin;
    await abrirEquipe(admin);
    let painel = await gerenciar(admin, contas.a);
    await painel.getByRole('button', {name: 'Incluir', exact: true}).click();
    await admin.locator('tr', {hasText: 'Convidada A'}).filter({hasText: 'Caso sintético beta'}).waitFor();
    painel = await gerenciar(admin, contas.a);
    await painel.locator('li, div', {hasText: 'Caso sintético alpha'}).getByRole('button', {name: 'Retirar'}).first().click();
    await confirmarSeSenhaPedida(admin, contas.admin.senha);
    await esperarApuracoesDa(admin, 'Convidada A', {tem: 'beta', naoTem: 'alpha'});
    const depoisDeRetirar = {
      'codex-eventos da conversa do caso X': await chamar(a, 'codex-eventos', {conversa: conversaA, cursor: 0}),
      'codex-original da conversa do caso X': await chamar(a, 'codex-original', {conversa: conversaA, referencia: referenciaA}),
      'codex-perguntar no caso X': await chamar(a, 'codex-perguntar', {caso: 'alpha', pergunta: 'Ainda posso?'}),
    };
    for (const [nome, r] of Object.entries(depoisDeRetirar)) assert.ok([400, 403, 404].includes(r.status), `${nome}: ${JSON.stringify(r)}`);
    assert.equal(depoisDeRetirar['codex-perguntar no caso X'].status, 404);
    assert.equal(depoisDeRetirar['codex-perguntar no caso X'].codigo, 'caso_indisponivel');
    assert.equal(depoisDeRetirar['codex-eventos da conversa do caso X'].codigo, 'conversa_indisponivel');
    resultado.recusas_apos_retirar_caso = depoisDeRetirar;
    await a.reload();
    await a.locator('#codex-caso option[value="beta"]').waitFor({state: 'attached'});
    assert.equal(await a.locator('#codex-caso option[value="alpha"]').count(), 0);
    marcar('papeis', 'Dono retira o caso X de A pela Equipe (Gerenciar > Retirar); a próxima ação de A no caso X (eventos, original, pergunta) é recusada e o caso some da lista.');

    painel = await gerenciar(admin, contas.b);
    await painel.getByRole('button', {name: 'Desativar', exact: true}).click();
    assert.match(await admin.locator('dialog.dialogo[open] .dialogo-titulo').innerText(), /Desativar a conta de Convidado B\?/);
    await confirmarSeSenhaPedida(admin, contas.admin.senha);
    await admin.locator('tr', {hasText: 'Convidado B'}).filter({hasText: /desativad/i}).waitFor();
    const bDepois = await chamar(b, 'codex-listar', {caso: 'beta'});
    assert.ok([401, 403].includes(bDepois.status), JSON.stringify(bDepois));
    assert.equal(await sessao(b), 401);
    marcar('papeis', `Dono desativa B pela Equipe (com a senha dele); a próxima requisição de B recebe ${bDepois.status} e /api/sessao 401.`);

    // Recuperar acesso (Gerenciar > Acesso): pede a senha de quem age e manda à pessoa, por e-mail, um link para criar a senha nova; nada muda na conta
    // até ela usar o link (contas sem e-mail só se recuperam pelo terminal, e a Equipe diz isso). O link vem do correio simulado, só pelo Python.
    painel = await gerenciar(admin, contas.a);
    await painel.getByRole('button', {name: 'Recuperar acesso'}).click();
    assert.match(await admin.locator('dialog.dialogo[open] .dialogo-titulo').innerText(), /Recuperar o acesso de Convidada A\?/);
    await confirmarSeSenhaPedida(admin, contas.admin.senha);
    const {link} = await py({cmd: 'link_recuperacao', para: contas.a.email});
    assert.match(link, /\/redefinir\/[A-Za-z0-9_-]{20,}$/);
    assert.equal(await sessao(a), 200, 'pedir a recuperação não encerra as sessões: nada muda até o link ser usado');
    assert.equal(await sessao(cel), 200);
    await admin.screenshot({path: path.join(shots, 'equipe-admin.png'), fullPage: true});
    const ctxRec = await contexto(browser);
    const rec = atual = await pagina(ctxRec, 'recuperação de A');
    abertas.push(rec);
    await rec.goto(link);
    await rec.locator('#redefinir-form:not([hidden])').waitFor();
    const senhaNovaA = 'nova-' + crypto.randomBytes(12).toString('hex');
    contas.a_nova = {senha: senhaNovaA};   // para o ocultar() também cobrir a senha nova
    await rec.fill('#redefinir-senha', senhaNovaA);
    await rec.click('#redefinir-enviar');
    await rec.locator('#redefinir-pronto:not([hidden])').waitFor();
    assert.equal(await sessao(a), 401);
    assert.equal(await sessao(cel), 401);
    await a.reload();
    await a.waitForURL(url => url.pathname === '/entrar');
    marcar('papeis', 'Dono pede a recuperação de A pela Equipe (com a senha dele); nada muda até A usar o link do e-mail; ao usá-lo, as sessões abertas de A (desktop e celular) caem (401) e o recarregamento leva A para /entrar.');
    await entrar(a, {login: contas.a.login, senha: senhaNovaA});
    assert.equal(await sessao(a), 200);
    marcar('papeis', 'A entra com a senha nova.');
    atual = admin;

    assert.deepEqual(erros, []);
    Object.assign(resultado, {estado: 'aprovado', caso_reportagem: caso, verificacoes, erros_js: erros, pulados});
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
