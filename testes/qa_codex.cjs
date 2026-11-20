const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const [origin,output,chrome] = process.argv.slice(2);
(async () => {
  await fs.mkdir(output,{recursive:true});
  const browser = await chromium.launch({headless:true,...(chrome ? {executablePath:chrome} : {})});
  const page = await browser.newPage({viewport:{width:1365,height:1000},acceptDownloads:true});
  const errors = [];
  page.on('pageerror',e => errors.push(e.message));
  try {
    await page.goto(origin);
    await page.click('#ver-codex');
    await page.locator('#codex-conta').filter({hasText:'Conectado à API'}).waitFor();
    assert.equal(await page.locator('#codex-login').count(),0);
    await page.selectOption('#codex-caso','alpha');
    await page.locator('#codex-inventario').locator('..').locator('summary').click();
    await page.locator('#codex-inventario').filter({hasText:'1 documento'}).waitFor();
    await page.fill('#codex-pergunta','Pergunta técnica com corpus sintético.');
    await page.click('#codex-enviar');
    await page.locator('#codex-status').filter({hasText:'Execução concluída'}).waitFor();
    await page.locator('#codex-fontes>details').first().waitFor();
    assert.match(await page.locator('#codex-mensagens').innerText(),/valor 123/);
    assert.equal(await page.evaluate(() => window.INJETADO_CODEX),undefined);
    assert.equal(await page.locator('#codex-mensagens a').count(),1);
    assert.equal(await page.locator('#codex-cancelar').isDisabled(),true);
    const download = page.waitForEvent('download');
    await page.locator('#codex-fontes>details>summary').first().click();
    await page.locator('#codex-fontes button').first().click();
    const saved = await download;
    assert.match(await fs.readFile(await saved.path(),'utf8'),/Alfabeto/);
    await page.screenshot({path:path.join(output,'conversa-desktop.png'),fullPage:true});
    const chatId = await page.locator('#codex-conversa').inputValue();
    assert.match(chatId,/^[a-f0-9]{32}$/);
    await page.getByRole('button',{name:'Consultar achados desta rodada'}).first().click();
    await page.locator('#area-achados:not([hidden])').waitFor();
    await page.locator('#achados-resultados article').first().waitFor();
    assert.equal(await page.locator('#achados-revisao').inputValue(),'r3_sintese');
    assert.equal(await page.locator('#achados-geracao').inputValue(),'g1');
    assert.equal(await page.locator('#achados-resultados article').count(),1);
    await page.click('#ver-codex');
    await page.fill('#codex-pergunta','Complemento técnico sintético.');
    await page.click('#codex-enviar');
    await page.locator('#codex-escopo').filter({hasText:'R002'}).waitFor({state:'attached'});
    await page.locator('#codex-status').filter({hasText:'Execução concluída'}).waitFor();
    assert.equal(await page.locator('#codex-mensagens .codex-user').count(),2);
    await page.reload();
    await page.click('#ver-codex');
    await page.selectOption('#codex-caso','alpha');
    await page.locator(`#codex-conversa option[value="${chatId}"]`).waitFor({state:'attached'});
    await page.selectOption('#codex-conversa',chatId);
    await page.locator('#codex-mensagens').filter({hasText:'Complemento técnico sintético.'}).waitFor();
    for (const width of [1365,736,390,320]) {
      await page.setViewportSize({width,height:900});
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth),false,`overflow ${width}`);
    }
    await page.screenshot({path:path.join(output,'conversa-mobile.png'),fullPage:true});
    await page.setViewportSize({width:1365,height:1000});
    await page.fill('#codex-pergunta','AGUARDAR para testar cancelamento.');
    await page.click('#codex-enviar');
    await page.locator('#codex-escopo').filter({hasText:'R003'}).waitFor({state:'attached'});
    await page.click('#codex-cancelar');
    await page.locator('#codex-status').filter({hasText:'Execução interrompida'}).waitFor();
    await page.fill('#codex-pergunta','LIMITE sintético.');
    await page.click('#codex-enviar');
    await page.locator('#codex-erro').filter({hasText:'Limite de uso sintético'}).waitFor();
    await page.locator('#codex-status').filter({hasText:'Execução com erro'}).waitFor();
    await page.locator('#codex-acervo>summary').click();
    await page.selectOption('#codex-caso','beta');
    await page.locator('#codex-inventario').filter({hasText:'beta_v1'}).waitFor({state:'attached'});
    assert.equal(await page.locator('#codex-mensagens article').count(),0);
    assert.equal(await page.locator('#codex-conversa option').count(),1);
    assert.deepEqual(errors,[]);
    await fs.writeFile(path.join(output,'resultado.json'), JSON.stringify({
      estado:'ok',natureza:'sintético; app-server simulado; sem inferência',
      verificacoes:['status da API sem login nem chave no navegador','conexão e seleção explícita','pergunta e ferramentas via protocolo','referência clicável e original',
        'HTML documental inerte','complemento em nova rodada','recarga e recuperação da conversa',
        'consulta automática dos achados publicados na revisão final','320–1365 px sem transbordamento','cancelamento','erro de limite','separação de casos'],erros_js:errors},null,2));
    console.log('QA Codex: OK');
  } finally { await browser.close(); }
})().catch(e => {console.error(e);process.exitCode=1;});
