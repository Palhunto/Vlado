const {chromium}=require('playwright');
const {enviarArquivos}=require('./qa_navegacao.cjs');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:chromium.executablePath()});
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[];page.on('pageerror',e=>{errors.push(e.message);console.error('PAGE:',e.stack);});
  page.on('console',message=>{if(message.type()==='error')console.error('CONSOLE:',message.text());});
  // A pesquisa no conteúdo (rodada, geração, consulta) é a aba "Pesquisar no conteúdo" da tela Documentos.
  const irParaPesquisa=async()=>{await page.click('#ver-documentos');await page.click('#mesa-aba-pesquisa');};
  try {
    await page.goto(process.argv[2]);
    await page.locator('#area-inicio').waitFor({state:'visible'});
    await page.selectOption('#contexto-caso','beta');
    await page.click('#inicio-adicionar');   // leva a Documentos com a apuração escolhida (a área Cadastrar arquivos saiu, R4)
    await page.locator('#area-documentos:not([hidden])').waitFor();
    await enviarArquivos(page,{name:'lote_sintetico.txt',mimeType:'text/plain',buffer:Buffer.from('Documento sintético adicional para teste de cadastro.')});
    await page.click('#mesa-perguntar');
    await page.locator('#area-codex:not([hidden])').waitFor();
    // O alerta do recibo ao lado da pergunta (#codex-recibo-alerta) era do botão Perguntar sobre estes documentos, da área que saiu: Documentos leva
    // a Perguntar por #mesa-perguntar, sem ele. Quando o Design decidir se o recibo acompanha a pergunta, a conferência volta aqui.
    await page.evaluate(()=>document.getElementById('codex-mensagens').append(document.createTextNode('Histórico sintético longo. '.repeat(2500))));
    await page.locator('#codex-mensagens').scrollIntoViewIfNeeded();
    const composer=await page.locator('#codex-pergunta').boundingBox();
    assert.ok(composer.y>=0 && composer.y+composer.height<=1000,'A composição deve continuar visível durante a leitura do histórico.');
    await page.evaluate(()=>document.getElementById('codex-mensagens').replaceChildren());
    await page.click('#ver-inicio');
    await page.click('#inicio-retomar');
    assert.equal(await page.inputValue('#codex-caso'),'beta');
    await page.click('#ver-diligencias');
    await page.click('#diligencias-nova');
    await page.fill('#diligencias-acao','Solicitar documento sintético');
    await page.fill('#diligencias-responsavel','Repórter de teste');
    await page.fill('#diligencias-autor','Editora de teste');
    await page.fill('#diligencias-prazo','2020-01-02');
    await page.click('#diligencias-salvar');
    await page.locator('.diligence-entry').waitFor();
    assert.match(await page.locator('.diligence-entry').innerText(),/02\/01\/2020.*vencida/);
    await page.selectOption('#contexto-caso','alpha');
    await irParaPesquisa();
    await page.selectOption('#rodada','R001');
    await page.selectOption('#geracao','v1');
    await page.locator('#buscar:not([disabled])').waitFor();
    await page.fill('#consulta','valor');await page.click('#buscar');
    await page.locator('#resultados .result').first().waitFor();
    await page.locator('#resultados .result').first().getByRole('button',{name:/^(Abrir original|Ver página \d+ no original)$/}).click();
    await page.locator('#original-dialogo[open]').waitFor();
    assert.match(await page.locator('#original-conteudo').innerText(),/valor/);
    await page.click('#original-fechar');
    const [md]=await Promise.all([page.waitForEvent('download'),page.click('#exportar')]);assert.match(md.suggestedFilename(),/\.md$/);
    const exported=await fs.readFile(await md.path(),'utf8');assert.match(exported,/Referência:.*alpha.*R001/);assert.ok(!exported.includes('<script>'));
    const route=page.url();await page.reload();
    await page.locator('#resultados .result').first().waitFor();
    assert.equal(await page.inputValue('#consulta'),'valor');assert.equal(page.url(),route);
    await page.click('#ver-diligencias');await page.goBack();
    await page.locator('#area-documentos').waitFor({state:'visible'});
    await page.locator('#resultados .result').first().waitFor();
    assert.equal(await page.inputValue('#consulta'),'valor');
    await page.click('#ver-apuracao');
    await page.locator('#apuracao-nova:not([disabled])').waitFor();
    await page.click('#apuracao-nova');await page.fill('#apuracao-nota-titulo','Não perder esta nota');
    page.once('dialog',d=>d.dismiss());await page.selectOption('#contexto-caso','beta');
    assert.equal(await page.inputValue('#contexto-caso'),'alpha');
    assert.equal(await page.inputValue('#apuracao-nota-titulo'),'Não perder esta nota');
    await irParaPesquisa();
    await page.locator('#resultados .result').first().getByRole('button',{name:'Registrar trecho com fonte',exact:true}).click();
    await page.locator('#caderno-trecho:not([disabled])').waitFor();
    await page.fill('#caderno-titulo-input','Texto não salvo');
    page.once('dialog',d=>d.dismiss());await page.click('#caderno-fechar');
    assert.equal(await page.locator('#caderno-dialogo').getAttribute('open'),'');
    page.once('dialog',d=>d.accept());await page.click('#caderno-fechar');
    // The original viewer opens PDF on the cited physical page and never executes source HTML.
    await page.evaluate(async()=>{
      const docs=await api('caderno-documentos',{caso:'alpha'}),doc=docs.documentos.find(d=>d.formato==='.pdf');
      const blob=await api('caderno-original',{caso:'alpha',origem_id:docs.origem_id,documento_id:doc.documento_id,documento_sha256:doc.sha256},true);
      await window.abrirOriginal(blob,doc.nome_recebido,1,'Afirmação sintética para conferência lado a lado.');
    });
    // pdf.js (frente C) draws the cited page in a canvas; the iframe stays only as a fallback.
    await page.locator('#original-conteudo .pdf-status').filter({hasText:'Página 1 de 1'}).waitFor({timeout:20000});
    assert.equal(await page.locator('#original-pdf-pagina').inputValue(),'1');
    await page.waitForTimeout(1200);
    await fs.mkdir('docs/qa_experiencia',{recursive:true});
    await page.screenshot({path:'docs/qa_experiencia/leitor.png'});
    await page.click('#original-fechar');
    await page.setViewportSize({width:390,height:844});
    await page.evaluate(()=>scrollTo(0,0));
    await page.screenshot({path:'docs/qa_experiencia/mobile.png',fullPage:true});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    await page.click('#ver-achados');
    await page.selectOption('#achados-revisao','r2');await page.selectOption('#achados-geracao','g2');
    await page.locator('.finding-open').first().waitFor();
    await page.locator('.finding-open').first().click();
    await page.locator('#achados-inspecao').waitFor({state:'visible'});
    assert.equal(await page.locator('#achados-resultados').isVisible(),false);
    await page.locator('#achados-inspecao').getByRole('button',{name:'Voltar à lista de achados',exact:true}).click();
    assert.equal(await page.locator('#achados-resultados').isVisible(),true);
    await page.locator('.finding-open').first().click();
    await page.locator('#achados-inspecao').getByRole('button',{name:'Conferir',exact:true}).click();
    await page.locator('#revisao-observacao:not([disabled])').waitFor();
    await page.fill('#revisao-observacao','Observação que deve ser preservada.');
    page.once('dialog',d=>d.dismiss());await page.click('#revisao-fechar');
    assert.equal(await page.locator('#revisao-dialogo').getAttribute('open'),'');
    page.once('dialog',d=>d.accept());await page.click('#revisao-fechar');
    // Close an unsaved note only when the test browser exits.
    assert.deepEqual(errors,[]);
    console.log('OK: contexto único, diligência livre, prazo, leitor, exportação, URL, proteção de rascunho e largura móvel.');
  } catch(error) {
    console.error(await page.locator('body').innerText()); throw error;
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
