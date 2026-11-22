const editor=require('./editor_notas.cjs');
'use strict';
const {chromium}=require('playwright');
const {irParaNovaApuracao} = require('./qa_navegacao.cjs');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
const [origin,out,chat]=process.argv.slice(2);
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:chromium.executablePath()});
 const page=await browser.newPage({viewport:{width:1440,height:1040},acceptDownloads:true});
 const result={checks:[],errors:[],external:[],trace:[]};
 page.on('request',r=>{if(/\/api\/(buscar|cobertura|catalogo)$/.test(r.url()))result.trace.push(r.url().split('/').pop());});
 page.on('pageerror',e=>result.errors.push(e.stack||e.message));
 page.on('request',r=>{if(!r.url().startsWith(origin)&&!r.url().startsWith('blob:'))result.external.push(r.url());});
 const shot=async name=>{await page.evaluate(()=>document.fonts.ready);await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:path.join(out,name+'.png')});};
 const go=async area=>{if((await page.viewportSize()).width<=720&&await page.locator('#mesa-menu').getAttribute('aria-expanded')!=='true')await page.locator('#mesa-menu').click();await page.locator('#ver-'+area).click();};
 const open=async id=>{if(!await page.locator('#'+id).evaluate(el=>el.open))await page.locator('#'+id+'>summary').click();};
 try{
  await page.goto(origin);await page.locator('#area-inicio').waitFor({state:'visible'});
  assert.equal(await page.locator('html').getAttribute('data-theme'),'dark');
  assert.equal(await page.locator('body').evaluate(el=>getComputedStyle(el).color),'rgb(234, 233, 223)');
  await shot('tema-escuro');
  await page.getByRole('button',{name:'Ativar modo claro',exact:true}).click();
  assert.equal(await page.locator('html').getAttribute('data-theme'),'light');
  await shot('tema-claro');
  await page.reload();await page.locator('#area-inicio').waitFor({state:'visible'});
  assert.equal(await page.locator('html').getAttribute('data-theme'),'light');
  await page.getByRole('button',{name:'Ativar modo escuro',exact:true}).click();
  await page.reload();await page.locator('#area-inicio').waitFor({state:'visible'});
  assert.equal(await page.locator('html').getAttribute('data-theme'),'dark');
  result.checks.push('Modo escuro inicial, alternância claro/escuro e preferência preservada após recarregar.');
  assert.equal(await page.locator('#contexto-caso').inputValue(),'');
  assert.doesNotMatch(await page.locator('#mesa-retomada').innerText(),/Transporte escolar|12 meses/);
  await shot('inicio-vazio');
  await page.selectOption('#contexto-caso','alpha');await page.locator('#mesa-versao').filter({hasText:'alpha'}).waitFor();
  assert.match(await page.locator('#mesa-retomada').innerText(),/3 documentos/);await shot('inicio');
  result.checks.push('Início vazio e retomada usam somente o contexto escolhido e o inventário real.');
  await go('documentos');await page.locator('#mesa-acervo-lista tbody tr').first().waitFor();assert.equal(await page.locator('#mesa-acervo-lista tbody tr').count(),3);
  await shot('documentos');await page.fill('#mesa-filtrar-documento','texto');assert.equal(await page.locator('#mesa-acervo-lista tbody tr').count(),1);
  await page.locator('.mesa-document-name').click();await page.locator('#original-dialogo[open]').waitFor();assert.match(await page.locator('#original-conteudo').innerText(),/A fonte declara valor 12/);assert.equal(await page.evaluate(()=>window.INJETADO),undefined);await page.keyboard.press('Escape');
  await page.fill('#mesa-filtrar-documento','');await page.selectOption('#mesa-filtrar-leitura','limitacoes');assert.equal(await page.locator('#mesa-acervo-lista tbody tr').count(),1);
  result.checks.push('Acervo filtra nome/cobertura e abre o original com identidade e hash, sem executar HTML documental.');
  await page.click('#mesa-aba-pesquisa');await page.selectOption('#rodada','R001');await page.selectOption('#geracao','v1');await page.locator('#buscar:not([disabled])').waitFor();
  await page.evaluate(()=>{window.qaSubmits=0;window.qaClicks=[];for(const ev of ['mousedown','mouseup','click'])document.addEventListener(ev,e=>window.qaClicks.push([ev,e.target.id,e.defaultPrevented]),true);document.getElementById('pesquisa').addEventListener('submit',()=>window.qaSubmits++);});await page.fill('#consulta','valor');await page.click('#buscar');await page.locator('#resultados .result').first().waitFor({timeout:8000});await shot('pesquisa');
  result.searchRoute=page.url();await page.reload();await page.locator('#resultados .result').first().waitFor();assert.equal(await page.inputValue('#documentos-aba'),'pesquisa');
  const legacy=new URL(page.url());legacy.searchParams.delete('documentos-aba');await page.goto(legacy.href);await page.locator('#resultados .result').first().waitFor();assert.equal(await page.inputValue('#documentos-aba'),'pesquisa');
  const mdPromise=page.waitForEvent('download');await page.click('#exportar');const md=await mdPromise;assert.match(await fs.readFile(await md.path(),'utf8'),/alpha.*R001/);
  result.checks.push('Pesquisa e aba sobrevivem a reload; exportação preserva o caso e a rodada.');
  await go('codex');await open('codex-acervo');await page.selectOption('#codex-conversa',chat);await page.locator('.codex-answer').waitFor();await page.locator('.codex-source').first().waitFor();assert.equal(await page.locator('#codex-painel-fontes').evaluate(el=>el.open),true);await shot('conversa');
  await page.locator('.source-citation').first().click();await page.locator('#codex-painel-fontes').waitFor({state:'visible'});
  result.checks.push('Conversa real de fixture mantém resposta e fontes acessíveis lado a lado, sem inferência.');
  await go('achados');await open('acervo-escolha');await page.selectOption('#rodada','R001');await open('achados-versoes');await page.selectOption('#achados-revisao','r2');await page.selectOption('#achados-geracao','g2');await page.locator('.finding-open').first().waitFor();
  await shot('achados');await page.locator('.finding-open').first().click();await page.locator('#achados-inspecao').getByRole('button',{name:'Conferir',exact:true}).click();await page.locator('#revisao-estado:not([disabled])').waitFor();await page.selectOption('#revisao-estado','conferida_no_original');await page.fill('#revisao-observacao','Conferência sintética de interface.');await shot('conferencia');await page.locator('#revisao-form').getByRole('button',{name:/Salvar/}).click();await page.locator('#revisao-dialogo').waitFor({state:'hidden'});
  await page.locator('#achados-progresso-texto').filter({hasText:'1 de 32'}).waitFor();
  result.checks.push('Conferência humana grava avaliação separada e atualiza o progresso.');
  await go('apuracao');await page.locator('#apuracao-nova:not([disabled])').waitFor();await page.click('#apuracao-nova');await page.fill('#apuracao-nota-titulo','Nota de interface sintética');await editor.write(page,'Redação sintética para conferir o editor, o salvamento e a exportação.');await page.click('#apuracao-salvar');await page.locator('#apuracao-status').filter({hasText:'Nota salva'}).waitFor();await shot('caderno');
  const notePromise=page.waitForEvent('download');await page.click('#apuracao-exportar');assert.match((await notePromise).suggestedFilename(),/\.md$/);
  await go('inicio');await go('apuracao');assert.equal((await editor.read(page)).trim(),'Redação sintética para conferir o editor, o salvamento e a exportação.');result.checks.push('Caderno salva, reabre e exporta uma nota real da fixture.');
  await editor.mode(page,'wysiwyg');
  assert.equal(await page.locator('#apuracao-vditor .vditor-reset[contenteditable=true]:visible').evaluate(el=>getComputedStyle(el).color),'rgb(234, 233, 223)');
  await page.getByRole('button',{name:'Ativar modo claro',exact:true}).click();
  assert.equal((await editor.read(page)).trim(),'Redação sintética para conferir o editor, o salvamento e a exportação.');
  await page.getByRole('button',{name:'Ativar modo escuro',exact:true}).click();
  result.checks.push('Editor visual acompanha o tema e preserva o texto ao alternar.');
  await editor.write(page,'Rascunho que não deve se perder.');page.once('dialog',dialog=>dialog.dismiss());await page.selectOption('#contexto-caso','');assert.equal(await page.inputValue('#contexto-caso'),'alpha');assert.equal((await editor.read(page)).trim(),'Rascunho que não deve se perder.');await page.click('#apuracao-salvar');await page.locator('#apuracao-status').filter({hasText:'Nota salva'}).waitFor();result.checks.push('Troca de apuração respeita o aviso de rascunho não salvo.');
  await go('diligencias');await page.click('#diligencias-nova');await page.fill('#diligencias-acao','Solicitar comprovante sintético');await page.fill('#diligencias-responsavel','Repórter de teste');await page.fill('#diligencias-autor','Autoria de teste');await page.click('#diligencias-salvar');await page.locator('.diligence-entry').first().waitFor();assert.equal(await page.locator('.mesa-diligence-column').count(),3);await shot('diligencias');result.checks.push('Diligência salva aparece na coluna correspondente ao estado real.');
  await irParaNovaApuracao(page);await page.fill('#cadastro-titulo-input','Caso de interface — lote sintético');await page.setInputFiles('#cadastro-arquivos',{name:'fonte_visual.txt',mimeType:'text/plain',buffer:Buffer.from('Arquivo sintético para cadastro e recibo, sem pergunta editorial.')});await shot('cadastro');await page.click('#enviar-documentos');await page.locator('#cadastro-perguntar:not([hidden])').waitFor();const newCase=await page.inputValue('#cadastro-caso');assert.match(newCase,/^apuracao_/);await shot('recibo');
  const metadata=await page.evaluate(async id=>(await (await fetch('/api/catalogo')).json()).casos.find(c=>c.id===id),newCase);assert.equal(metadata.rodadas.length,0);result.checks.push('Cadastro e recibo reais preservam o lote antes da pergunta, sem criar rodada.');
  await go('gerenciar');await page.locator('#gerenciar-excluir-caso').waitFor({state:'visible'});await shot('gerenciar');await page.click('#gerenciar-excluir-caso');await page.locator('#excluir-dialogo button[value=excluir]').click();await page.locator('#gerenciar-lixeira button').first().waitFor();await page.locator('#gerenciar-lixeira button').first().click();await page.locator('#gerenciar-lixeira .manage-empty').waitFor();result.checks.push('Exclusão confirmada e restauração preservadas no gerenciador.');
  await page.selectOption('#contexto-caso','alpha');
  for(const width of [1440,1024,768,390,320]){
   await page.setViewportSize({width,height:844});
   for(const area of ['inicio','documentos','cadastro','codex','achados','apuracao','diligencias','gerenciar']){
    await go(area);await page.evaluate(()=>document.fonts.ready);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,area+' transborda em '+width+'px');
    if(width===390)await shot(area+'-mobile');
   }
   result.checks.push('Oito áreas sem transbordamento horizontal em '+width+'px.');
  }
  await page.setViewportSize({width:390,height:844});await page.click('#mesa-menu');assert.equal(await page.getAttribute('#mesa-menu','aria-expanded'),'true');await page.keyboard.press('Escape');assert.equal(await page.getAttribute('#mesa-menu','aria-expanded'),'false');result.checks.push('Menu móvel abre, fecha ao navegar e responde a Escape.');
  assert.deepEqual(result.errors,[]);assert.deepEqual(result.external,[]);result.ok=true;
 }catch(error){result.failure=error.stack;result.state=await page.evaluate(()=>({url:location.href,notice:$('experiencia-status').textContent,status:$('status').textContent,query:$('consulta').value,busy:$('buscar').disabled,submits:window.qaSubmits,epoch,searchSequence,formValid:$('pesquisa').checkValidity(),buttonForm:$('buscar').form?.id,buttonType:$('buscar').type,clicks:window.qaClicks}));await page.screenshot({path:path.join(out,'falha.png'),fullPage:true});throw error;}
 finally{await fs.writeFile(path.join(out,'resultado.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result,null,2));await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
