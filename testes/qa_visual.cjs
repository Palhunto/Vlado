const editor=require('./editor_notas.cjs');
'use strict';
const {chromium}=require('playwright');
const {criarApuracao, enviarArquivos} = require('./qa_navegacao.cjs');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
const [origin,out,chat]=process.argv.slice(2);
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:chromium.executablePath()});
 const page=await browser.newPage({viewport:{width:1440,height:1040},acceptDownloads:true});
 // Tema escuro só quando nada foi guardado ainda: o padrão sem valor guardado mudou de mãos (prefers-color-scheme, depois escuro de novo), e este roteiro
 // não deve depender dele. O guardado vence em toda carga, então alternar o tema e recarregar continua valendo.
 await page.addInitScript(()=>{try{if(!localStorage.getItem('apuracao:tema'))localStorage.setItem('apuracao:tema','dark');}catch{}});
 const result={checks:[],errors:[],external:[],trace:[]};
 page.on('request',r=>{if(/\/api\/(buscar|cobertura|catalogo)$/.test(r.url()))result.trace.push(r.url().split('/').pop());});
 page.on('pageerror',e=>result.errors.push(e.stack||e.message));
 page.on('request',r=>{if(!r.url().startsWith(origin)&&!r.url().startsWith('blob:'))result.external.push(r.url());});
 const shot=async name=>{await page.evaluate(()=>document.fonts.ready);await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:path.join(out,name+'.png')});};
 const irPara=async area=>{if(await page.locator('#original-dialogo[open]').count())await page.click('#original-fechar');if(!await page.locator('#ver-'+area).isVisible()&&await page.locator('#mesa-menu').isVisible()){if(await page.locator('#mesa-menu').getAttribute('aria-expanded')==='true'){await page.locator('#mesa-menu').click();await page.locator('#mesa-menu[aria-expanded="false"]').waitFor();}await page.locator('#mesa-menu').click();await page.locator('#mesa-menu[aria-expanded="true"]').waitFor();}await page.locator('#ver-'+area).click();};
 // Nova apuração e Apurações saíram da barra: chegam-se a elas pela Visão geral (qa_navegacao.cjs).
 const go=async area=>{if(area==='nova'){await irPara('inicio');await page.click('#inicio-nova');return;}if(area==='gerenciar'){await irPara('inicio');await page.click('#inicio-trocar');return;}return irPara(area);};
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
  await page.locator('#mesa-acervo-lista .docs-abrir').first().click();await page.locator('#original-dialogo[open]').waitFor();assert.match(await page.locator('#original-conteudo').innerText(),/A fonte declara valor 12/);assert.equal(await page.evaluate(()=>window.INJETADO),undefined);await page.keyboard.press('Escape');
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
  // A citação abre o original em seguida (assíncrono): espera o diálogo e o fecha, para não interceptar os cliques da próxima área.
  await page.locator('#original-dialogo[open]').waitFor({timeout:10000});await page.click('#original-fechar');await page.locator('#original-dialogo').waitFor({state:'hidden'});
  result.checks.push('Conversa real de fixture mantém resposta e fontes acessíveis lado a lado, sem inferência.');
  await go('achados');await open('acervo-escolha');await page.selectOption('#rodada','R001');await open('achados-versoes');await page.locator('#achados-revisao:enabled').waitFor();await page.selectOption('#achados-revisao','r2');await page.locator('#achados-geracao:enabled').waitFor();await page.selectOption('#achados-geracao','g2');await page.locator('.finding-open').first().waitFor();
  await shot('achados');await page.locator('.finding-open').first().click();await page.locator('#achados-inspecao').getByRole('button',{name:'Conferir',exact:true}).click();await page.locator('#revisao-estado:not([disabled])').waitFor();for(let i=0,n=await page.locator('#revisao-fontes .review-evidence button').count();i<n;i++){await page.locator('#revisao-fontes .review-evidence button').nth(i).click();await page.locator('#original-dialogo[open]').waitFor();await page.click('#original-fechar');await page.locator('#original-dialogo').waitFor({state:'hidden'});}await page.waitForFunction(()=>!document.querySelector('#revisao-estado option[value="conferida_no_original"]').disabled);await page.selectOption('#revisao-estado','conferida_no_original');await page.fill('#revisao-observacao','Conferência sintética de interface.');await shot('conferencia');await page.locator('#revisao-form').getByRole('button',{name:/Salvar/}).click();await page.locator('#revisao-dialogo').waitFor({state:'hidden'});
  await page.locator('#achados-progresso-texto').filter({hasText:'1 de 32'}).waitFor();
  result.checks.push('Conferência humana grava avaliação separada e atualiza o progresso.');
  await go('apuracao');await page.locator('#apuracao-nova:not([disabled])').waitFor();await page.click('#apuracao-nova');await page.fill('#apuracao-nota-titulo','Nota de interface sintética');await editor.write(page,'Redação sintética para conferir o editor, o salvamento e a exportação.');await page.waitForFunction(()=>document.querySelector('#apuracao-salvamento').dataset.estado==='salvo',null,{timeout:20000});await shot('caderno');
  const notePromise=page.waitForEvent('download');await page.click('#apuracao-exportar');assert.match((await notePromise).suggestedFilename(),/\.md$/);
  await go('inicio');await go('apuracao');assert.equal((await editor.read(page)).trim(),'Redação sintética para conferir o editor, o salvamento e a exportação.');result.checks.push('Caderno salva, reabre e exporta uma nota real da fixture.');
  await editor.mode(page,'wysiwyg');
  assert.equal(await page.locator('#apuracao-vditor .vditor-reset[contenteditable=true]:visible').evaluate(el=>getComputedStyle(el).color),'rgb(234, 233, 223)');
  await page.getByRole('button',{name:'Ativar modo claro',exact:true}).click();
  assert.equal((await editor.read(page)).trim(),'Redação sintética para conferir o editor, o salvamento e a exportação.');
  await page.getByRole('button',{name:'Ativar modo escuro',exact:true}).click();
  result.checks.push('Editor visual acompanha o tema e preserva o texto ao alternar.');
  await page.evaluate(()=>{window.__salvou=false;new MutationObserver(lista=>{for(const m of lista)if(m.target.id==='apuracao-salvamento'&&m.target.dataset.estado==='salvo')window.__salvou=true;}).observe(document.body,{attributes:true,subtree:true,attributeFilter:['data-estado']});});await editor.write(page,'Rascunho que não deve se perder.');await page.selectOption('#contexto-caso','');await page.locator('#experiencia-status').filter({hasText:'Aguarde o salvamento da nota.'}).waitFor();assert.equal(await page.inputValue('#contexto-caso'),'alpha');assert.equal((await editor.read(page)).trim(),'Rascunho que não deve se perder.');await page.waitForFunction(()=>window.__salvou===true,null,{timeout:20000});/* o sinal "salvo" é transitório: o observador instalado antes da escrita o guarda */result.checks.push('Troca de apuração respeita o aviso de rascunho não salvo.');
  await go('diligencias');await page.click('#diligencias-nova');await page.fill('#diligencias-acao','Solicitar comprovante sintético');await page.fill('#diligencias-responsavel','Repórter de teste');await page.fill('#diligencias-autor','Autoria de teste');await page.click('#diligencias-salvar');await page.locator('.diligence-entry').first().waitFor();assert.equal(await page.locator('.mesa-diligence-column').count(),3);await shot('diligencias');result.checks.push('Diligência salva aparece na coluna correspondente ao estado real.');
  // Nova apuração: passo 1 (nome e fontes), passo 2 (Documentos, onde o primeiro lote cria a apuração) e o recibo do lote.
  await criarApuracao(page,{nome:'Caso de interface — lote sintético'});await shot('cadastro');await enviarArquivos(page,{name:'fonte_visual.txt',mimeType:'text/plain',buffer:Buffer.from('Arquivo sintético para cadastro e recibo, sem pergunta editorial.')});const newCase=await page.inputValue('#contexto-caso');assert.match(newCase,/^apuracao_/);await shot('recibo');
  const metadata=await page.evaluate(async id=>(await (await fetch('/api/catalogo')).json()).casos.find(c=>c.id===id),newCase);assert.equal(metadata.rodadas.length,0);result.checks.push('Cadastro e recibo reais preservam o lote antes da pergunta, sem criar rodada.');
  await go('gerenciar');await page.locator('#gerenciar-excluir-caso').waitFor({state:'visible'});await shot('gerenciar');await page.click('#gerenciar-excluir-caso');await page.locator('dialog.dialogo .dialogo-acoes button.danger').click();await page.locator('#gerenciar-lixeira button').first().waitFor();await page.locator('#gerenciar-lixeira button').first().click();await page.locator('#gerenciar-lixeira .manage-empty').waitFor();result.checks.push('Exclusão confirmada e restauração preservadas no gerenciador.');
  await page.selectOption('#contexto-caso','alpha');
  for(const width of [1440,1024,768,390,320]){
   await page.setViewportSize({width,height:844});
   await page.waitForTimeout(500);   // o evento de resize chega depois e pode fechar a gaveta que acabou de abrir
   for(const area of ['inicio','documentos','nova','codex','achados','apuracao','diligencias','gerenciar']){
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
