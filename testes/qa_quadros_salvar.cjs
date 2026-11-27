'use strict';
// Salvar cada quadro pela tela, num navegador de verdade contra o servidor de verdade (test_quadros_salvar_navegador.py o chama).
// Para os modos `local` e `piloto`: abre hipótese, acontecimento, entidade, ligação e tabela pelo botão "Nova ...", preenche o formulário como uma pessoa faria
// (nenhum corpo é montado à mão, de modo que falta de campo na tela aparece aqui como erro do servidor), salva, confere que o item aparece no quadro,
// e confirma uma sugestão da IA e descarta outra. A autoria gravada se confere no teste Python, que lê os registros.
// Uso: node qa_quadros_salvar.cjs '<json>' com {porta, origem, modo, caso, autor?, login?, senha?}. Sem argumento não faz nada. Dados sintéticos, sem rede.
const assert = require('node:assert/strict');
const path = require('node:path');

if (!process.argv[2]) process.exit(0);
const args = JSON.parse(process.argv[2]);
const {chromium} = require(path.join(__dirname, '..', '.ferramentas', 'node', 'node_modules', 'playwright'));

const NOMES = {hipotese: 'Hipótese salva pela tela (QA).', acontecimento: 'Assinatura sintética salva pela tela (QA).', pessoa: 'Pessoa Teste Um', organizacao: 'Empresa Teste Dois',
  tabela: 'Pagamentos salvos pela tela (QA)', celula: 'Pagamento de janeiro (QA)'};

(async () => {
  const browser = await chromium.launch();
  const resultado = {modo: args.modo, salvos: [], decisoes: []};
  try {
    const ctx = await browser.newContext({viewport: {width: 1440, height: 1000}, locale: 'pt-BR'});
    await ctx.addInitScript(() => { try { localStorage.setItem('vlado-idioma', 'pt'); } catch (_) { /* sem armazenamento */ } });
    if (args.modo === 'piloto') {
      // O servidor fala HTTP e se apresenta como a origem https (o modo piloto exige): a rota leva o pedido à porta de verdade.
      await ctx.route(`${args.origem}/**`, async rota => { try {
        const pedido = rota.request(), endereco = new URL(pedido.url());
        const resposta = await rota.fetch({url: `http://127.0.0.1:${args.porta}${endereco.pathname}${endereco.search}`, headers: {...pedido.headers(), host: new URL(args.origem).host}, maxRedirects: 0});
        await rota.fulfill({response: resposta});
      } catch (_) { /* a página fechou com o pedido em voo */ } });
    }
    const page = await ctx.newPage();
    const erros = [], respostas = [];
    page.on('pageerror', erro => erros.push(erro.message));
    page.on('response', async r => {
      if (r.request().method() !== 'POST' || !r.url().includes('/api/')) return;
      const operacao = r.url().split('/api/')[1].split('?')[0];
      if (/^(hipoteses|linha-tempo|mapa-entidade|mapa-relacao|tabelas)-(criar|atualizar)$|^sugestoes-(confirmar|descartar)$/.test(operacao)) {
        respostas.push({operacao, status: r.status(), corpo: r.status() >= 400 ? (await r.text().catch(() => '')).slice(0, 300) : ''});
      }
    });

    if (args.modo === 'piloto') {
      await page.goto(`${args.origem}/entrar`);
      await page.fill('#entrar-login', args.login); await page.fill('#entrar-senha', args.senha);
      await Promise.all([page.waitForURL(url => url.pathname === '/' || url.pathname === '/index.html'), page.click('#entrar-enviar')]);
    } else await page.goto(args.origem);
    await page.locator('#area-inicio').waitFor({state: 'visible', timeout: 20000});
    await page.selectOption('#contexto-caso', args.caso);
    await page.locator('#ver-quadros').click();
    await page.locator('#area-quadros').waitFor({state: 'visible'});

    const ate = async procurar => { for (let i = 0; i < 100; i++) { const v = procurar(); if (v) return v; await page.waitForTimeout(100); } return undefined; };
    const aba = async id => { await page.locator(`#quadros-aba-${id}`).click(); await page.locator(`#quadros-${id}`).waitFor({state: 'visible'}); await page.waitForLoadState('networkidle'); };
    // Autoria: só o modo local pede o nome (no hospedado vem da conta). Preenche o campo "Autor" onde a tela o oferece; onde não oferece, segue sem ele,
    // e é o servidor que diz se faltou (400 de autor), que é justamente o que este teste existe para pegar.
    const autor = async escopo => {
      const campo = escopo.getByLabel(/^Autor/i).first();
      if (args.modo === 'local' && await campo.count() && await campo.isVisible()) await campo.fill(args.autor);
    };
    const salvar = async (painel, rotulo) => {
      const antes = respostas.length;
      await autor(painel);
      await painel.locator('.form-pe button', {hasText: /^Salvar$/}).click();
      // ou o formulário some (salvou), ou o erro aparece no formulário
      await page.waitForFunction(() => !document.querySelector('.form-quadro') || (document.querySelector('.form-erro-geral') && !document.querySelector('.form-erro-geral').hidden), null, {timeout: 20000});
      const erroTela = await painel.locator('.form-erro-geral:not([hidden])').allInnerTexts();
      assert.deepEqual(erroTela, [], `${rotulo}: o formulário não salvou (${args.modo}): ${erroTela.join(' | ')} ${JSON.stringify(respostas.slice(antes))}`);
      const resposta = await ate(() => respostas.slice(antes).find(x => /-criar$/.test(x.operacao)));
      assert.ok(resposta && resposta.status === 200, `${rotulo}: o servidor respondeu ${JSON.stringify(resposta)}`);
      resultado.salvos.push(rotulo);
      await page.waitForLoadState('networkidle');
    };
    const ligarEvidencia = async painel => {
      await painel.locator('.form-ligar').click();
      await page.locator('.seletor-resultado[data-origem="ia"][data-chave$=":suporte"]').first().click();
      await page.locator('.seletor-aberto button', {hasText: /^Ligar$/}).click();
      await painel.locator('.vinculo-cartao').first().waitFor();
    };
    const novo = async (painel, tipo) => { await painel.locator(`.quadro-novo[data-tipo="${tipo}"]`).click(); await painel.locator('.form-quadro').waitFor(); };

    // 1. Hipótese
    await aba('hipoteses');
    let painel = page.locator('#quadros-hipoteses');
    await novo(painel, 'hipotese');
    await painel.getByLabel('Hipótese', {exact: true}).fill(NOMES.hipotese);
    await salvar(painel, 'hipótese');
    await painel.locator('.quadro-hipotese', {hasText: NOMES.hipotese}).waitFor({timeout: 10000});

    // 2. Acontecimento (pede uma evidência de suporte e a fonte da data)
    await aba('tempo');
    painel = page.locator('#quadros-tempo');
    await novo(painel, 'acontecimento');
    await painel.getByLabel('Acontecimento', {exact: true}).fill(NOMES.acontecimento);
    await ligarEvidencia(painel);
    await painel.getByLabel('Data', {exact: true}).fill('03/03/2025');
    await painel.getByLabel('Fonte da data').selectOption('0');
    await salvar(painel, 'acontecimento');
    await painel.locator('.tempo-evento', {hasText: NOMES.acontecimento}).waitFor({timeout: 10000});

    // 3. Entidades (duas, para a ligação) e 4. ligação
    await aba('mapa');
    painel = page.locator('#quadros-mapa');
    for (const [tipo, nome] of [['pessoa', NOMES.pessoa], ['organizacao', NOMES.organizacao]]) {
      await novo(painel, 'entidade');
      await painel.getByLabel('Nome', {exact: true}).fill(nome);
      if (tipo === 'organizacao') await painel.locator('.form-segmento[data-valor="organizacao"]').click();
      await salvar(painel, `entidade ${tipo}`);
      await painel.locator('.mapa-lista', {hasText: nome}).waitFor({timeout: 10000});
    }
    await novo(painel, 'ligacao');
    await painel.getByLabel('De', {exact: true}).selectOption({label: NOMES.pessoa});
    await painel.getByLabel('Para', {exact: true}).selectOption({label: NOMES.organizacao});
    await painel.getByLabel('Tipo de relação').fill('sócio');
    await ligarEvidencia(painel);
    await salvar(painel, 'ligação');
    await painel.locator('.mapa-lista', {hasText: 'sócio'}).first().waitFor({timeout: 10000});

    // 5. Tabela: uma coluna, uma linha nova, com a evidência como fonte da célula
    await aba('tabelas');
    painel = page.locator('#quadros-tabelas');
    await novo(painel, 'tabela');
    await painel.getByLabel('Título da tabela').fill(NOMES.tabela);
    await ligarEvidencia(painel);
    // a tabela nova já traz uma coluna; só acrescenta outra se não trouxer
    if (!await painel.getByLabel('Nome da coluna', {exact: true}).count()) await painel.locator('.form-mais', {hasText: /Coluna/}).click();
    await painel.getByLabel('Nome da coluna', {exact: true}).first().fill('Descrição');
    await painel.locator('.form-mais', {hasText: /Adicionar linha/}).click();
    await painel.getByLabel('Descrição', {exact: true}).last().fill(NOMES.celula);
    await painel.getByLabel(/^Fonte da célula/).selectOption({index: 1});
    await salvar(painel, 'tabela');
    await painel.locator('td.tabela-celula', {hasText: NOMES.celula}).first().waitFor({timeout: 10000});

    // Sugestões da IA (semeadas pelo teste): confirmar a da hipótese, descartar a do acontecimento
    const decidir = async (abaId, tipo, botao) => {
      await aba(abaId);
      const p = page.locator(`#quadros-${abaId}`);
      await p.locator(`.sugestao-abrir`).first().click();
      const sugestao = page.locator('.sugestao-painel').first();
      await sugestao.waitFor();
      await autor(sugestao);
      const antes = respostas.length;
      const decisao = page.waitForResponse(r => r.request().method() === 'POST' && /\/api\/sugestoes-(confirmar|descartar)/.test(r.url()), {timeout: 20000});
      await sugestao.getByRole('button', {name: botao, exact: true}).click();
      await decisao;
      await page.waitForLoadState('networkidle');
      const resposta = await ate(() => respostas.slice(antes).find(x => /^sugestoes-/.test(x.operacao)));
      const erroTela = await page.locator('.sugestao-erro:not([hidden])').allInnerTexts();
      assert.ok(resposta && resposta.status === 200 && !erroTela.length, `${botao} a sugestão (${tipo}, ${args.modo}): ${JSON.stringify(resposta)} ${erroTela.join(' | ')}`);
      resultado.decisoes.push(`${botao}:${tipo}`);
      return p;
    };
    let p = await decidir('hipoteses', 'hipotese', 'Confirmar');
    await p.locator('.quadro-hipotese', {hasText: 'A Construtora Alfa declarou valor 12'}).first().waitFor({timeout: 10000});
    p = await decidir('tempo', 'acontecimento', 'Descartar');
    await p.locator('.sugestoes-descartadas').waitFor({timeout: 10000});

    assert.deepEqual(erros, [], 'nenhum erro de página');
    assert.deepEqual(respostas.filter(x => x.status >= 400), [], 'nenhuma resposta de erro do servidor');
  } finally {
    await browser.close();
  }
  console.log(JSON.stringify(resultado));
})().catch(e => { console.error(e); process.exit(1); });
