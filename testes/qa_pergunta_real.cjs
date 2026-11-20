// Browser half of qa_pergunta_real.py: activation page, sign-in, ONE real question.
const {chromium} = require('playwright');
const fs = require('node:fs/promises');
const path = require('node:path');
const [origin, output, chrome, caso] = process.argv.slice(2);
const link = process.env.VLADO_QA_LINK, senha = process.env.VLADO_QA_SENHA, pergunta = process.env.VLADO_QA_PERGUNTA;
const LONGO = 25 * 60 * 1000;
(async () => {
  const browser = await chromium.launch({headless: true, ...(chrome ? {executablePath: chrome} : {})});
  // ignoreHTTPSErrors only here: the test front uses a throw-away self-signed certificate.
  const ctx = await browser.newContext({ignoreHTTPSErrors: true, viewport: {width: 1365, height: 1000}});
  await ctx.addInitScript(() => { try { localStorage.setItem('vlado-idioma', 'pt'); } catch { /* blocked storage */ } });
  const page = await ctx.newPage();
  const erros = [], etapas = [];
  page.on('pageerror', e => erros.push(e.message));
  page.on('dialog', d => d.accept().catch(() => {}));
  const marcar = texto => { etapas.push(texto); console.log('ok:', texto); };
  try {
    await page.goto(link);
    await page.locator('#ativar-secao:not([hidden])').waitFor();
    await page.fill('#ativar-senha', senha);
    await page.fill('#ativar-confirmar', senha);
    await page.click('#ativar-enviar');
    await page.locator('#ativar-pronto:not([hidden])').waitFor();
    marcar('ativação pelo link de uso único');
    await page.goto(origin + '/entrar');
    await page.fill('#entrar-login', 'admin.homolog');
    await page.fill('#entrar-senha', senha);
    await page.click('#entrar-enviar');
    await page.waitForURL(url => !url.pathname.startsWith('/entrar'), {timeout: 30000});
    marcar('login com a senha definida');
    await page.click('#ver-codex');
    await page.locator(`#contexto-caso option[value="${caso}"]`).waitFor({state: 'attached'});
    if (await page.locator('#contexto-caso').inputValue() !== caso) await page.selectOption('#contexto-caso', caso);
    await page.waitForFunction(c => document.querySelector('#codex-caso').value === c, caso);
    await page.locator('#codex-conta').filter({hasText: 'Conectado à API'}).waitFor({timeout: 30000});
    const conexao = (await page.locator('#codex-conta').innerText()).trim();
    marcar('conexão: ' + conexao);
    await page.fill('#codex-pergunta', pergunta);
    const inicio = Date.now();
    await page.click('#codex-enviar');
    const fim = page.locator('#codex-status').filter({hasText: /Execução (concluída|com erro|interrompida)/});
    await fim.waitFor({timeout: LONGO});
    const status = (await page.locator('#codex-status').innerText()).trim();
    const segundos = Math.round((Date.now() - inicio) / 1000);
    marcar(`estado: ${status} em ${segundos} s`);
    const resposta = (await page.locator('#codex-mensagens').innerText()).trim();
    const citacoes = await page.locator('#codex-mensagens .source-citation').count();
    await page.screenshot({path: path.join(output, 'pergunta-real.png'), fullPage: true});
    await fs.writeFile(path.join(output, 'resposta.txt'), resposta, 'utf8');
    await fs.writeFile(path.join(output, 'resultado_navegador.json'), JSON.stringify(
      {estado: status, segundos_ate_o_fim: segundos, conexao, citacoes_clicaveis: citacoes, etapas, erros_js: erros}, null, 2));
    process.exitCode = /concluída/.test(status) ? 0 : 2;
  } catch (erro) {
    await page.screenshot({path: path.join(output, 'falha.png'), fullPage: true}).catch(() => {});
    console.error('QA pergunta real falhou:', String(erro.message || erro).replaceAll(senha, '***'));
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
})();
