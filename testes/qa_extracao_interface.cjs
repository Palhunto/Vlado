const {chromium} = require('playwright');
const {irParaDocumentos, criarApuracao, enviarArquivos} = require('./qa_navegacao.cjs');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const [origin, output, chrome, pdf] = process.argv.slice(2);
(async () => {
  await fs.mkdir(output, {recursive:true});
  const browser = await chromium.launch({headless:true, ...(chrome ? {executablePath:chrome} : {})});
  const page = await browser.newPage({viewport:{width:1365, height:1000}});
  const errors = [], checks = [];
  page.on('pageerror', error => errors.push(error.message));
  try {
    await page.goto(origin);
    // A área Cadastrar arquivos saiu (R4): o aviso do extrator e o preparo de PDFs vivem no topo de Documentos (#docs-pdf-*), e uma apuração
    // nova nasce pela Nova apuração; o primeiro lote enviado em Documentos a cria.
    const escolherCaso = async caso => {
      await page.locator(`#contexto-caso option[value="${caso}"]`).waitFor({state:'attached'});
      await page.selectOption('#contexto-caso', caso);
    };
    await irParaDocumentos(page);
    await page.locator('#docs-pdf-ambiente-tecnico details').waitFor({state:'attached'});
    assert.equal(await page.locator('#docs-pdf-ambiente').isVisible(), false);
    await criarApuracao(page, {nome:'Extração sintética pelo navegador'});
    await enviarArquivos(page, {name:'PDF recebido.pdf', mimeType:'application/pdf', buffer:await fs.readFile(pdf)});
    assert.match(await page.locator('#documentos-recibo').innerText(), /Recibo do lote: 1 de 1 arquivos/);
    await page.locator('#mesa-acervo-lista tbody tr').first().waitFor();
    assert.equal(await page.locator('#mesa-acervo-lista .docs-leitura').first().getAttribute('data-leitura'), 'texto');
    assert.match(await page.locator('#mesa-acervo-lista tbody tr').first().innerText(), /1 página/);
    assert.equal(await page.locator('#docs-pdf-preparo').isVisible(), false);
    checks.push('Envio pela tela Documentos extrai texto real de PDF sintético: recibo do lote, "Texto do próprio arquivo" e 1 página na lista.');
    await page.screenshot({path:path.join(output, 'upload-pdf.png'), fullPage:true});
    await escolherCaso('gamma');
    await page.locator('#docs-pdf-preparo:not([hidden])').waitFor();
    await page.locator('#docs-pdf-preparar:not([disabled])').waitFor();
    assert.match(await page.locator('#mesa-acervo-lista').innerText(), /Não foi lido/);
    await page.click('#docs-pdf-preparar');
    await page.locator('#mesa-acervo-status').filter({hasText:/PDF preparado/}).waitFor();
    assert.equal(await page.locator('#mesa-acervo-lista .docs-leitura').first().getAttribute('data-leitura'), 'texto');
    assert.match(await page.locator('#mesa-acervo-lista tbody tr').first().innerText(), /1 página/);
    assert.equal(await page.locator('#docs-pdf-preparo').isVisible(), false);
    checks.push('Preparar PDFs pendentes recupera falha de dependência sem seleção ou reenvio de arquivos.');
    await page.screenshot({path:path.join(output, 'preparacao-recuperada.png'), fullPage:true});
    await page.reload();
    await irParaDocumentos(page);
    await escolherCaso('gamma');
    await page.locator('#mesa-acervo-lista tbody tr').first().waitFor();
    assert.match(await page.locator('#mesa-acervo-lista').innerText(), /Texto do próprio arquivo/);
    assert.match(await page.locator('#mesa-acervo-lista').textContent(), /gamma_v2/);
    checks.push('Derivado e nova versão persistem após recarga; enviar e preparar não inicia pergunta ou rodada.');
    await page.route('**/api/ambiente', route => route.fulfill({status:200, contentType:'application/json', body:JSON.stringify({python:'python-simulado', extracao_pdf:{disponivel:false}, pronto:false})}));
    await page.reload();
    await irParaDocumentos(page);
    await page.locator('#docs-pdf-ambiente:not([hidden])').waitFor();
    await escolherCaso('delta');
    await page.locator('#docs-pdf-preparo:not([hidden])').waitFor();
    assert.equal(await page.locator('#docs-pdf-preparar').isDisabled(), true);
    assert.match(await page.locator('#docs-pdf-ambiente-texto').innerText(), /extrator.*indisponível/);
    assert.doesNotMatch(await page.locator('#mesa-acervo-lista').innerText(), /pip|requirements|pypdf/);
    checks.push('Instância sem extrator mostra orientação única antes do envio e bloqueia repetição inútil da preparação.');
    for (const width of [1365,390,320]) {
      await page.setViewportSize({width,height:950});
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    }
    await page.screenshot({path:path.join(output, 'aviso-mobile.png'), fullPage:true});
    assert.deepEqual(errors, []);
    await fs.writeFile(path.join(output, 'resultado.json'), JSON.stringify({estado:'ok', natureza:'PDFs sintéticos; extração real; sem modelo', checks, errors}, null, 2));
    console.log('QA extração: OK (' + checks.length + ' verificações)');
  } catch (error) {
    await page.screenshot({path:path.join(output, 'falha.png'), fullPage:true}).catch(() => {});
    throw error;
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
