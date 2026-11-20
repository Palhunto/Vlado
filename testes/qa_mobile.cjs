'use strict';
// Mesa em tela estreita: rolagem horizontal, alvos de toque, voltar, conexão do acompanhamento,
// faixa de ambiente, teclado virtual, página citada do PDF (pdf.js) e capturas.
// Dados, conversa e PDF sintéticos; sem inferência (o acompanhamento ao vivo é simulado).
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const [origin, output, chrome, chat, capturas] = process.argv.slice(2);
// 683 px = 1365 px at 200 % browser zoom (WCAG 1.4.4 / 1.4.10).
const WIDTHS = [320, 360, 390, 683, 768, 1024, 1365];
const AREAS = ['inicio', 'documentos', 'cadastro', 'codex', 'achados', 'apuracao', 'diligencias', 'gerenciar'];
const PHONE = {width: 390, height: 844};
const CITED = 'Empresa Sintetica Ltda. recebeu R$ 12.400,00 em marco.';

// Waits for finite animations only (an infinite one, such as a progress pulse, never finishes).
const settle = page => page.evaluate(async () => {
  const finite = document.getAnimations().filter(a => Number.isFinite(a.effect?.getComputedTiming().endTime));
  await Promise.race([Promise.all(finite.map(a => a.finished.catch(() => {}))), new Promise(r => setTimeout(r, 1500))]);
  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
});
async function go(page, area) {
  const narrow = page.viewportSize().width <= 720;
  if (narrow && await page.locator('#mesa-menu').getAttribute('aria-expanded') !== 'true') {
    await page.locator('#mesa-menu').click();
    await settle(page);
  }
  await page.locator('#ver-' + area).click();
  await page.locator('#area-' + area).waitFor({state: area === 'documentos' ? 'attached' : 'visible'});
  await page.waitForTimeout(narrow ? 260 : 60);
  await settle(page);
}
// Elements sticking out of the viewport without a clipping/scrolling ancestor that contains them.
// The closed navigation drawer is off-screen by design (it slides in from the left).
function overflowProbe() {
  const width = document.documentElement.clientWidth;
  const offenders = [];
  const drawerClosed = !document.body.classList.contains('mesa-menu-open') && width <= 720;
  const clipped = el => {
    for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
      const style = getComputedStyle(p);
      if (/(auto|scroll|hidden|clip)/.test(style.overflowX) && p.getBoundingClientRect().right <= width + 1) return true;
    }
    return false;
  };
  for (const el of document.querySelectorAll('body *')) {
    if (el.closest('[hidden],dialog:not([open]),.sr-only')) continue;
    if (drawerClosed && el.closest('#mesa-sidebar')) continue;
    if (getComputedStyle(el).visibility === 'hidden') continue;
    const rect = el.getBoundingClientRect();
    if (!rect.width || !rect.height) continue;
    if ((rect.right > width + 1 || rect.left < -1) && !clipped(el)) {
      offenders.push(`${el.tagName.toLowerCase()}${el.id ? '#' + el.id : ''}${typeof el.className === 'string' && el.className ? '.' + el.className.trim().split(/\s+/).join('.') : ''} [${Math.round(rect.left)}–${Math.round(rect.right)}]`);
    }
  }
  return {scroll: document.documentElement.scrollWidth, width, offenders: offenders.slice(0, 8)};
}
// Visible controls smaller than 44 × 44 CSS px (links inside running text are exempt).
function targetProbe() {
  const small = [];
  for (const el of document.querySelectorAll('button,select,input:not([type=hidden]):not([type=checkbox]):not([type=radio]),summary,a[href]')) {
    if (el.closest('[hidden],dialog:not([open]),.sr-only,.vditor,p,li>a') || el.classList.contains('skip-link')) continue;
    const rect = el.getBoundingClientRect(), style = getComputedStyle(el);
    if (!rect.width || !rect.height || style.visibility === 'hidden') continue;
    if (rect.height < 43.5 || rect.width < 43.5) small.push(`${el.tagName.toLowerCase()}#${el.id || ''} «${el.textContent.trim().slice(0, 24)}» ${Math.round(rect.width)}×${Math.round(rect.height)}`);
  }
  return small.slice(0, 12);
}
const noOverflow = async (page, label) => {
  const probe = await page.evaluate(overflowProbe);
  assert.ok(probe.scroll <= probe.width && !probe.offenders.length, `${label}: ${JSON.stringify(probe)}`);
};

(async () => {
  await fs.mkdir(output, {recursive: true});
  if (capturas) await fs.mkdir(capturas, {recursive: true});
  const browser = await chromium.launch({headless: true, ...(chrome ? {executablePath: chrome} : {})});
  const result = {checks: [], overflow: [], targets: [], errors: [], external: []};
  const context = await browser.newContext({viewport: PHONE, hasTouch: true, isMobile: true, deviceScaleFactor: 2, acceptDownloads: true});
  let page = null;
  const watch = target => {
  target.on('pageerror', e => result.errors.push(e.stack || e.message));
  target.on('console', m => {
    // Other fronts' stylesheets (caderno.css) may not be served yet; that is not this front's error.
    if (m.type() === 'error' && !/Failed to load resource|ERR_INTERNET_DISCONNECTED|ERR_FAILED|caderno\.css/.test(m.text())) result.errors.push('console: ' + m.text());
  });
  target.on('request', r => { const u = r.url(); if (!u.startsWith(origin) && !/^(blob|data):/.test(u)) result.external.push(u); });
  };
  page = await context.newPage();
  watch(page);
  const shot = async name => {
    if (!capturas) return;
    await page.evaluate(() => document.fonts.ready);
    await settle(page);
    await page.screenshot({path: path.join(capturas, name + '.png')});
  };
  const theme = async value => {
    if (await page.locator('html').getAttribute('data-theme') !== value) await page.evaluate(() => document.getElementById('mesa-tema').click());
  };
  const openScope = async () => { if (!await page.locator('#codex-acervo').evaluate(el => el.open)) await page.locator('#codex-acervo>summary').click(); };
  const openChat = async () => {
    await openScope();
    if (await page.inputValue('#codex-conversa') !== chat) await page.selectOption('#codex-conversa', chat);
    await page.locator('.codex-answer').waitFor();
  };
  try {
    await page.goto(origin);
    await page.locator('#area-inicio').waitFor({state: 'visible'});
    assert.equal(await page.locator('#mesa-ambiente').isHidden(), true, 'modo local: sem faixa de ambiente');
    result.checks.push('Modo local (sem /api/sessao): nenhuma faixa de ambiente.');
    await page.selectOption('#contexto-caso', 'alpha');
    await page.waitForFunction(() => /alpha/.test(document.getElementById('mesa-versao').textContent));

    const step = name => process.stderr.write(`[qa_mobile] ${name}
`);
    step('larguras');
    // 1. No horizontal scroll at any reference width, in every area; touch targets on phones.
    // QA_MOBILE_RAPIDO=1 skips the width sweep while debugging the later steps.
    for (const width of process.env.QA_MOBILE_RAPIDO ? [] : WIDTHS) {
      await page.setViewportSize({width, height: width < 800 ? 844 : 900});
      for (const area of AREAS) {
        await go(page, area);
        if (area === 'codex') await openChat();
        if (area === 'achados') await page.locator('#achados-resultados article').first().waitFor({timeout: 15000});
        const probe = await page.evaluate(overflowProbe);
        if (probe.scroll > probe.width || probe.offenders.length) result.overflow.push({width, area, ...probe});
        if (width <= 390) {
          const small = await page.evaluate(targetProbe);
          if (small.length) result.targets.push({width, area, small});
        }
      }
    }
    // Landscape phone.
    await page.setViewportSize({width: 844, height: 390});
    for (const area of ['codex', 'achados', 'documentos']) {
      await go(page, area);
      const probe = await page.evaluate(overflowProbe);
      if (probe.scroll > probe.width || probe.offenders.length) result.overflow.push({width: '844x390', area, ...probe});
    }
    assert.deepEqual(result.overflow, [], 'rolagem horizontal');
    if (!process.env.QA_MOBILE_RAPIDO) result.checks.push(`Sem rolagem horizontal em ${WIDTHS.join(', ')} px (683 = 1365 a 200 %) e em paisagem 844×390, nas áreas ${AREAS.join(', ')}.`);
    assert.deepEqual(result.targets, [], 'alvos de toque menores que 44 px');
    if (!process.env.QA_MOBILE_RAPIDO) result.checks.push('Alvos de toque com pelo menos 44 × 44 px em 320, 360 e 390 px.');

    step('voltar');
    // The later steps run in a fresh tab: the sweep's long history and pdf.js workers stay behind.
    await page.close();
    page = await context.newPage();
    watch(page);
    await page.setViewportSize(PHONE);
    await page.goto(origin + '/?area=documentos&caso=alpha');
    await page.waitForFunction(() => /alpha/.test(document.getElementById('mesa-versao').textContent));
    // A long session reaches the browser's 50-entry history cap (as after the width sweep).
    if (process.env.QA_MOBILE_HISTORICO) for (let i = 0; i < 60; i++) await page.evaluate(i => showArea(i % 2 ? 'codex' : 'documentos'), i);
    // 2. Back button: area, drawer, original and finding detail.
    await page.setViewportSize(PHONE);
    await go(page, 'documentos');
    await go(page, 'codex');
    await page.goBack();
    await page.locator('#area-documentos').waitFor({state: 'attached'});
    await page.waitForFunction(() => new URL(location.href).searchParams.get('area') === 'documentos');
    assert.equal(await page.locator('#area-codex').isHidden(), true);
    await page.locator('#mesa-menu').click();
    assert.equal(await page.locator('#mesa-menu').getAttribute('aria-expanded'), 'true');
    const before = page.url();
    await page.goBack();
    await page.waitForFunction(() => document.getElementById('mesa-menu').getAttribute('aria-expanded') === 'false');
    assert.equal(page.url(), before);
    await page.evaluate(() => document.getElementById('mesa-aba-acervo').click());
    await page.locator('.mesa-document-name').first().click();
    await page.locator('#original-dialogo[open]').waitFor();
    await page.goBack();
    await page.locator('#original-dialogo').waitFor({state: 'hidden'});
    assert.equal(new URL(page.url()).searchParams.get('area'), 'documentos', 'voltar fecha o original e fica na área');
    await go(page, 'achados');
    await page.locator('#achados-resultados .finding-open').first().click();
    await page.locator('#mesa-achados.detail-open').waitFor({state: 'attached'});
    await shot('mesa-390-escuro-achado');
    await page.goBack();
    await page.waitForFunction(() => !document.getElementById('mesa-achados').classList.contains('detail-open'));
    assert.equal(new URL(page.url()).searchParams.get('area'), 'achados');
    result.checks.push('Voltar: área anterior, fecha o menu, o original e o detalhe do achado sem sair da área.');

    step('acompanhamento');
    // 3. Run tracking: in progress → connection lost → offline → back online → interrupted.
    await go(page, 'codex');
    let mode = 'real';
    const cursors = [];
    await page.route('**/api/codex-eventos', async route => {
      const body = JSON.parse(route.request().postData() || '{}');
      cursors.push(body.cursor);
      // The mode is read once per request: a request in flight keeps the answer it started with.
      const requestMode = mode === 'abort' ? 'abort' : mode;
      if (requestMode === 'abort') { await new Promise(r => setTimeout(r, 150)); return route.abort('internetdisconnected'); }
      const response = await route.fetch();
      const data = await response.json();
      if (requestMode === 'executando' || (requestMode !== 'interrompido' && mode === 'abort')) {
        await new Promise(r => setTimeout(r, 400));
        data.conversa = {...data.conversa, estado: 'executando', situacao: {codigo: 'em_andamento', mensagem: 'Em execução.', causa: null}, retomavel: false};
      } else if (requestMode === 'interrompido') {
        data.conversa = {...data.conversa, estado: 'interrompido', rodada_pergunta: data.conversa.rodada, retomavel: true,
          situacao: {codigo: 'interrompido', mensagem: 'Interrompida antes de terminar. O que já foi concluído foi preservado.', causa: 'reinicio'}};
      }
      return route.fulfill({response, json: data});
    });
    mode = 'executando';
    await openScope();
    await page.selectOption('#codex-conversa', '');
    await page.selectOption('#codex-conversa', chat);
    await page.locator('#codex-conexao-estado').filter({hasText: 'Em andamento'}).waitFor();
    const delivered = await page.locator('#codex-fontes>details').count();
    // The live poll must be running (a second request) before the network drops.
    const waitPolls = async n => { const end = Date.now() + 10000; while (cursors.length < n && Date.now() < end) await page.waitForTimeout(100); };
    await waitPolls(2);
    cursors.length = 0;
    mode = 'abort';
    await page.locator('#codex-conexao-estado').filter({hasText: 'Conexão perdida — a execução continua no servidor; reconectando'}).waitFor().catch(async failure => {
      throw new Error(`${failure.message}
linha=${await page.textContent('#codex-conexao-estado')} status=${await page.textContent('#codex-status')} erro=${await page.textContent('#codex-erro')} cursores=${cursors}`);
    });
    assert.equal(await page.locator('#codex-reconectar').isHidden(), true);
    assert.equal(await page.locator('#codex-erro').isHidden(), true);
    await theme('light');
    await page.locator('#codex-execucao').scrollIntoViewIfNeeded();
    await shot('mesa-390-claro-reconectando');
    await context.setOffline(true);
    await page.locator('#codex-conexao-estado').filter({hasText: 'Sem conexão neste aparelho'}).waitFor({timeout: 10000});
    mode = 'executando';
    await context.setOffline(false);
    await page.locator('#codex-conexao-estado').filter({hasText: 'Em andamento'}).waitFor({timeout: 10000});
    assert.match(await page.textContent('#codex-anuncio'), /Conexão restabelecida/);
    assert.ok(cursors.length >= 2 && cursors.every(value => value === cursors[0]), `cursor preservado: ${cursors}`);
    assert.equal(await page.locator('#codex-fontes>details').count(), delivered, 'nenhum evento duplicado ou perdido');
    mode = 'interrompido';
    await page.locator('#codex-conexao-estado').filter({hasText: 'Interrompida — retomar'}).waitFor();
    assert.equal(await page.locator('#codex-retomar').isVisible(), true);
    await page.locator('#codex-execucao').scrollIntoViewIfNeeded();
    await shot('mesa-390-claro-interrompida');
    await page.unroute('**/api/codex-eventos');
    result.checks.push(`Acompanhamento: “Em andamento”, “Conexão perdida… reconectando” (falha de rede), “Sem conexão neste aparelho” (offline), retomada automática no mesmo cursor (${cursors[0]}) sem duplicar eventos, e “Interrompida — retomar”.`);

    step('teclado');
    // 4. Virtual keyboard: the focused field stays visible when the viewport shrinks.
    await page.selectOption('#codex-conversa', '');
    await page.selectOption('#codex-conversa', chat);
    await page.locator('.codex-answer').waitFor();
    await page.evaluate(() => window.abrirComposicaoMesa?.());
    await page.locator('#codex-pergunta').focus();
    await page.setViewportSize({width: 390, height: 420});
    await page.waitForTimeout(600);
    const box = await page.locator('#codex-pergunta').boundingBox();
    assert.ok(box && box.y >= 0 && box.y + Math.min(box.height, 60) <= 420, `campo visível com teclado: ${JSON.stringify(box)}`);
    await page.setViewportSize(PHONE);
    result.checks.push('Teclado virtual simulado (altura 420 px): o campo da pergunta continua visível.');

    step('pdf');
    // 5. Cited page of a PDF on the phone (pdf.js in canvas, page 2 of 3, excerpt highlighted).
    const b64 = (await fs.readFile(path.join(output, 'citado.pdf.b64'), 'utf8')).trim();
    const openPdf = (reference = CITED) => page.evaluate(async ([data, cited]) => {
      const bytes = Uint8Array.from(atob(data), c => c.charCodeAt(0));
      await window.abrirOriginal(new Blob([bytes], {type: 'application/pdf'}), 'relatorio_sintetico.pdf', 2, cited);
    }, [b64, reference]);
    const cited = () => page.locator('#original-conteudo .pdf-status').filter({hasText: 'Página 2 de 3'}).waitFor({timeout: 20000});
    for (const value of ['light', 'dark']) {
      await theme(value);
      await openPdf();
      await cited();
      await page.locator('#original-conteudo canvas').waitFor();
      assert.match(await page.textContent('#original-conteudo .pdf-status'), /Trecho citado destacado/);
      assert.ok(await page.locator('.pdf-trecho').count() >= 1);
      await noOverflow(page, 'PDF 390');
      await shot(`mesa-390-${value === 'light' ? 'claro' : 'escuro'}-pagina-citada`);
      step('pdf: voltar ' + value);
      const estado = () => Promise.race([page.evaluate(() => JSON.stringify({camadas: window.camadaMesa.abertas(), estado: history.state, n: history.length, url: location.href, aberto: document.getElementById('original-dialogo').open})),
        new Promise(r => setTimeout(() => r('página sem resposta'), 5000))]);
      await Promise.race([page.evaluate(() => { history.back(); }), new Promise((_, reject) => setTimeout(() => reject(new Error('history.back sem resposta')), 10000))]);
      await page.locator('#original-dialogo').waitFor({state: 'hidden', timeout: 10000}).catch(async failure => { throw new Error(failure.message + ' ' + await estado()); });
    }
    await openPdf();
    await cited();
    await page.getByRole('button', {name: 'Próxima página'}).click();
    await page.locator('#original-conteudo .pdf-status').filter({hasText: 'Página 3 de 3'}).waitFor();
    await page.getByRole('button', {name: 'Aumentar zoom'}).click();
    await page.locator('.pdf-zoom-level').filter({hasText: '125%'}).waitFor();
    await noOverflow(page, 'PDF ampliado');
    assert.equal(await page.locator('#original-baixar').isVisible(), true);
    await page.setViewportSize({width: 844, height: 390});
    await page.waitForTimeout(400);
    await page.locator('#original-conteudo .pdf-status').filter({hasText: 'Página 3 de 3'}).waitFor();
    await noOverflow(page, 'PDF em paisagem');
    await page.setViewportSize(PHONE);
    await page.locator('#original-fechar').click();
    // An excerpt that is not on the cited page is never reported as highlighted (no false match
    // on short shared words such as "de", "para", "valor").
    await openPdf('Este valor de referencia para a rota nao aparece nesta pagina.');
    await page.locator('#original-conteudo .pdf-status').filter({hasText: 'não foi localizado automaticamente'}).waitFor({timeout: 20000});
    assert.equal(await page.locator('.pdf-trecho').count(), 0);
    await page.locator('#original-fechar').click();
    result.checks.push('Página citada do PDF no celular: pdf.js em canvas abre na página 2 de 3 com o trecho destacado; navegação, zoom, paisagem e Baixar original; voltar fecha; trecho ausente não é dado como destacado.');

    step('faixa');
    // 6. Hosted environment banner (homologação), simulated /api/sessao.
    await page.route('**/api/sessao', route => route.fulfill({json: {ambiente: 'homologacao', conta: {id: 'x', nome: 'Pessoa sintética', papel: 'admin', casos: null}}}));
    await page.goto(origin + '/?area=inicio&caso=alpha');
    await page.locator('#mesa-ambiente').filter({hasText: 'Homologação — dados sintéticos'}).waitFor();
    await settle(page);
    const banner = await page.locator('#mesa-ambiente').boundingBox();
    const header = await page.locator('.app-header').boundingBox();
    assert.ok(header.y >= banner.y + banner.height - 1, `o cabeçalho começa abaixo da faixa: ${JSON.stringify({banner, header})}`);
    await noOverflow(page, 'faixa 390');
    await theme('dark');
    await shot('mesa-390-escuro-faixa-homologacao');
    await page.unroute('**/api/sessao');
    result.checks.push('Faixa “Homologação — dados sintéticos” fixa acima do cabeçalho quando /api/sessao informa o ambiente.');

    step('capturas');
    // 7. Screenshots: 390 and 1365, light and dark.
    await page.goto(origin + '/?area=inicio&caso=alpha');
    await page.locator('#area-inicio').waitFor({state: 'visible'});
    for (const [width, height] of [[390, 844], [1365, 900]]) {
      await page.setViewportSize({width, height});
      for (const value of ['light', 'dark']) {
        const name = `mesa-${width}-${value === 'light' ? 'claro' : 'escuro'}`;
        await theme(value);
        await go(page, 'inicio'); await shot(name + '-inicio');
        await go(page, 'codex'); await openChat(); await shot(name + '-conversa');
        await go(page, 'achados'); await page.locator('#achados-resultados article').first().waitFor(); await shot(name + '-achados');
        if (width === 390) {
          await page.locator('#mesa-menu').click(); await settle(page); await shot(name + '-menu');
          await page.goBack(); await page.waitForFunction(() => !document.body.classList.contains('mesa-menu-open'));
        }
      }
      await theme('light');
      await openPdf();
      await cited();
      if (width === 1365) await shot('mesa-1365-claro-pagina-citada');
      await page.locator('#original-fechar').click();
    }
    result.checks.push('Capturas em 390 e 1365 px, claro e escuro.');
    assert.deepEqual(result.errors, []);
    assert.deepEqual(result.external, []);
    await fs.writeFile(path.join(output, 'resultado.json'), JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result, null, 2));
  } catch (failure) {
    result.failure = failure.stack || String(failure);
    result.url = page.url();
    await page.screenshot({path: path.join(output, 'falha.png')}).catch(() => {});
    await fs.writeFile(path.join(output, 'resultado.json'), JSON.stringify(result, null, 2));
    console.error(JSON.stringify(result, null, 2));
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
})();
