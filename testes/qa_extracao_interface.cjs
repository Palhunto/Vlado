const {chromium} = require('playwright');
const {irParaCadastro} = require('./qa_navegacao.cjs');
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
    await irParaCadastro(page);
    await page.locator('#pdf-ambiente-tecnico details').waitFor({state:'attached'});
    assert.equal(await page.locator('#pdf-ambiente-aviso').isVisible(), false);
    await page.fill('#cadastro-titulo-input', 'Extração sintética pelo navegador');
    await page.setInputFiles('#cadastro-arquivos', {name:'PDF recebido.pdf', mimeType:'application/pdf', buffer:await fs.readFile(pdf)});
    await page.click('#enviar-documentos');
    await page.locator('#cadastro-status').filter({hasText:'Aguardando sua pergunta'}).waitFor();
    assert.match(await page.locator('#cadastro-recibo').innerText(), /Texto extraído.*1 de 1/);
    assert.equal(await page.locator('#cadastro-preparacao').isVisible(), false);
    checks.push('Upload pelo formulário extrai texto real de PDF sintético e confere as páginas no recibo.');
    await page.screenshot({path:path.join(output, 'upload-pdf.png'), fullPage:true});
    await page.selectOption('#cadastro-caso', 'gamma');
    await page.locator('#cadastro-preparar:not([disabled])').waitFor();
    assert.match(await page.locator('#cadastro-inventario').innerText(), /Falha na extração/);
    await page.click('#cadastro-preparar');
    await page.locator('#cadastro-status').filter({hasText:'PDFs preparados'}).waitFor();
    assert.match(await page.locator('#cadastro-recibo').innerText(), /Preparação conferida: 1 PDF/);
    assert.match(await page.locator('#cadastro-recibo').innerText(), /Texto extraído.*1 de 1/);
    assert.equal(await page.locator('#cadastro-arquivos').inputValue(), '');
    assert.equal(await page.locator('#cadastro-preparacao').isVisible(), false);
    checks.push('Preparar PDFs pendentes recupera falha de dependência sem seleção ou reenvio de arquivos.');
    await page.screenshot({path:path.join(output, 'preparacao-recuperada.png'), fullPage:true});
    await page.reload();
    await irParaCadastro(page);
    await page.locator('#cadastro-caso option[value="gamma"]').waitFor({state:'attached'});
    await page.selectOption('#cadastro-caso', 'gamma');
    await page.locator('#cadastro-inventario:not([hidden])').waitFor();
    assert.match(await page.locator('#cadastro-inventario').innerText(), /Texto extraído.*1 de 1/);
    assert.match(await page.locator('#cadastro-inventario').textContent(), /gamma_v2/);
    checks.push('Derivado e nova versão persistem após recarga; cadastro não inicia pergunta ou rodada.');
    await page.route('**/api/ambiente', route => route.fulfill({status:200, contentType:'application/json', body:JSON.stringify({python:'python-simulado', extracao_pdf:{disponivel:false}, pronto:false})}));
    await irParaCadastro(page);
    await page.locator('#pdf-ambiente-aviso').waitFor();
    await page.selectOption('#cadastro-caso', 'delta');
    await page.locator('#cadastro-preparacao:not([hidden])').waitFor();
    assert.equal(await page.locator('#cadastro-preparar').isDisabled(), true);
    assert.match(await page.locator('#pdf-ambiente-aviso').innerText(), /extrator.*indisponível/);
    assert.doesNotMatch(await page.locator('#cadastro-inventario').innerText(), /pip|requirements|pypdf/);
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
