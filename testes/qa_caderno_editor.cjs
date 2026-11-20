// Caderno editor in headless Chrome against a local synthetic server (see qa_caderno_editor.py).
const {chromium}=require('playwright');
const fs=require('node:fs/promises');
const path=require('node:path');
const assert=require('node:assert/strict');
const [origin,output,shots,chrome]=process.argv.slice(2);
const DRAFT_PREFIX='vlado:rascunho:';
const BOX='#apuracao-vditor .vditor-wysiwyg .vditor-task>input[type=checkbox]';
const EDIT='#apuracao-vditor .vditor-wysiwyg>.vditor-reset';

(async()=>{
  const browser=await chromium.launch({headless:true,...(chrome?{executablePath:chrome}:{})});
  const checks=[],errors=[],external=[];
  async function newPage(context,theme){
    const page=await context.newPage();
    await page.addInitScript(theme=>{try{localStorage.setItem('apuracao:tema',theme);}catch{}},theme);
    page.on('pageerror',e=>errors.push(e.stack||e.message));
    page.on('request',r=>{if(!r.url().startsWith(origin)&&!/^(blob|data):/.test(r.url()))external.push(r.url());});
    page.on('dialog',d=>d.accept().catch(()=>{}));
    return page;
  }
  const state=page=>page.locator('#apuracao-salvamento').getAttribute('data-estado');
  const markdown=page=>page.locator('#apuracao-texto').inputValue();
  async function waitSaved(page){await page.waitForFunction(()=>document.querySelector('#apuracao-salvamento').dataset.estado==='salvo',null,{timeout:20000});}
  async function openCaderno(page){
    await page.goto(origin+'/?area=apuracao&caso=alpha');
    await page.locator('#apuracao-vditor .vditor-toolbar').waitFor({state:'attached',timeout:30000});
    await page.locator('#apuracao-formatar:not([hidden])').waitFor();
  }
  async function openNote(page,title){
    const wide=await page.evaluate(()=>innerWidth>=1280);
    if(!wide&&await page.locator('#apuracao-ver-notas').isVisible())await page.click('#apuracao-ver-notas');
    await page.locator('#apuracao-notas button').filter({hasText:title}).first().click();
    await page.waitForFunction(title=>document.querySelector('#apuracao-nota-titulo').value===title,title);
    await page.waitForTimeout(250);
  }
  // Caret (or selection) inside the text node that contains `text`, at character offsets.
  async function caret(page,text,start,end=start){
    await page.evaluate(([sel,text,start,end])=>{
      const root=document.querySelector(sel),walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);
      while(walker.nextNode()){const node=walker.currentNode,at=node.data.indexOf(text);
        if(at>=0){root.focus();const range=document.createRange();range.setStart(node,at+start);range.setEnd(node,at+end);const s=getSelection();s.removeAllRanges();s.addRange(range);return;}}
      throw new Error('texto não encontrado: '+text);
    },[EDIT,text,start,end]);
  }
  // Caret as (block text, offset in the block): Vditor may split text nodes at the caret on re-render.
  const selectionInfo=page=>page.evaluate(()=>{
    const s=getSelection();if(!s.rangeCount)return {text:'',offset:-1,selected:'',inEditor:false};
    const node=s.anchorNode,el=node.nodeType===3?node.parentElement:node,block=el.closest('p,li,h1,h2,h3,h4,h5,h6')||el;
    const before=document.createRange();before.setStart(block,0);before.setEnd(node,s.anchorOffset);
    return {text:block.textContent,offset:before.toString().length,selected:s.toString(),inEditor:!!document.querySelector('#apuracao-vditor').contains(node)};
  });
  async function noOverflow(page,width){
    await page.setViewportSize({width,height:860});await page.waitForTimeout(150);
    const ok=await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth);
    assert.equal(ok,true,`rolagem horizontal em ${width}px`);
  }

  const context=await browser.newContext({viewport:{width:1365,height:900}});
  const page=await newPage(context,'light');
  try{
    await openCaderno(page);
    await page.locator(BOX).first().waitFor();

    // 1. Checkbox layout: 44px target, box beside the first line, text hanging aligned.
    const layout=await page.evaluate(sel=>[...document.querySelectorAll(sel)].map(box=>{
      const li=box.parentElement,r=box.getBoundingClientRect(),text=[...li.childNodes].find(n=>n.nodeType===3&&n.data.trim());
      const range=document.createRange();range.selectNodeContents(text);const rects=[...range.getClientRects()].filter(x=>x.width>1);
      const first=rects[0],last=rects.at(-1),cs=getComputedStyle(box);
      return {w:r.width,h:r.height,boxMid:r.top+r.height/2,lineMid:first.top+first.height/2,boxInnerRight:r.left+12+20,textLeft:first.left,
        lastLeft:last.left,lines:new Set(rects.map(x=>Math.round(x.top))).size,liWidth:li.getBoundingClientRect().width,padLeft:parseFloat(cs.paddingLeft)};
    }),BOX);
    assert.equal(layout.length,3);
    for(const item of layout){
      assert.equal(item.w,44,'alvo de 44px');assert.equal(item.h,44,'alvo de 44px');
      assert.ok(Math.abs(item.boxMid-item.lineMid)<=3,`caixa alinhada à primeira linha (${item.boxMid} × ${item.lineMid})`);
      assert.ok(item.textLeft>=item.boxInnerRight,'texto ao lado da caixa');
      assert.ok(item.liWidth>200,'o item não é ocupado pela caixa');
    }
    const long=layout[2];
    assert.ok(long.lines>=2,'item longo quebra em várias linhas');
    assert.ok(Math.abs(long.lastLeft-long.textLeft)<=2,'linhas seguintes alinhadas ao texto, não à caixa');
    checks.push('Caixa da tarefa com alvo de 44 px, alinhada à primeira linha e com o texto em recuo pendente, inclusive em item de várias linhas (antes: a caixa herdava largura de campo e ocupava a linha).');
    await page.screenshot({path:path.join(output,'tarefas-desktop.png')});

    // 2. Click the box without typing: selection kept, Markdown updated, saved, count updated.
    await caret(page,'Parágrafo final',3);
    await page.locator(BOX).first().click();
    await page.waitForFunction(()=>/- \[x\] Ligar para a assessoria/.test(document.querySelector('#apuracao-texto').value));
    let sel=await selectionInfo(page);
    assert.ok(sel.inEditor&&sel.text.startsWith('Parágrafo final')&&sel.offset===3,'cursor preservado depois do clique: '+JSON.stringify(sel));
    await waitSaved(page);
    assert.equal(await page.locator('#apuracao-tarefas').innerText(),'2 de 3 tarefas concluídas');
    assert.match(await page.locator('#apuracao-salvamento').innerText(),/^Nota salva às \d{2}:\d{2}$/);
    await page.reload();await page.locator(BOX).first().waitFor();
    assert.equal(await page.locator(BOX).first().isChecked(),true,'continua marcada depois de recarregar');
    assert.match(await markdown(page),/^- \[x\] Ligar para a assessoria fictícia$/m);
    checks.push('Marcar a caixa sem digitar atualiza o Markdown ("- [x]"), passa pelo salvamento automático, mostra "Nota salva às HH:MM" e continua marcada depois de recarregar; o cursor fica onde estava.');

    // 3. Keyboard: Space on the focused box, and Space right after the box.
    await page.locator(BOX).nth(0).focus();await page.keyboard.press('Space');
    await page.waitForFunction(()=>/^- \[ \] Ligar/m.test(document.querySelector('#apuracao-texto').value));
    await waitSaved(page);
    await caret(page,'Ligar para a assessoria',0);await page.keyboard.press('Space');
    await page.waitForFunction(()=>/^- \[x\] Ligar/m.test(document.querySelector('#apuracao-texto').value));
    assert.doesNotMatch(await markdown(page),/\[x\]\s{2,}Ligar/,'Espaço não foi digitado no texto');
    await waitSaved(page);
    checks.push('Teclado: Espaço na caixa focada e Espaço no início do item marcam e desmarcam, sem inserir espaço no texto.');

    // 4. "Lista de tarefas" inserts an unchecked item at the writing point, ready for typing.
    await caret(page,'Conferir o contrato sintético','Conferir o contrato sintético'.length);
    await page.click('#apuracao-tarefa');
    await page.keyboard.type('Tarefa nova sintética');
    await page.waitForFunction(()=>/^- \[ \] Tarefa nova sintética$/m.test(document.querySelector('#apuracao-texto').value),null,{timeout:5000});
    const lines=(await markdown(page)).split('\n');
    assert.equal(lines.indexOf('- [ ] Tarefa nova sintética'),lines.findIndex(l=>l.includes('Conferir o contrato'))+1,'novo item logo depois do item do cursor');
    await waitSaved(page);
    assert.equal(await page.locator('#apuracao-tarefas').innerText(),'2 de 4 tarefas concluídas');
    checks.push('Botão "Lista de tarefas" insere item desmarcado depois do item do cursor, pronto para digitar; a contagem passa a "2 de 4".');

    // 5. Visual ↔ Markdown keeps the structure.
    const before=await markdown(page);
    await page.click('#apuracao-mais');assert.equal(await page.locator('#apuracao-mais').getAttribute('aria-expanded'),'true');
    await page.locator('#apuracao-vditor button[data-type="edit-mode"]').click();await page.locator('#apuracao-vditor button[data-mode="sv"]').click();
    await page.locator('#apuracao-vditor .vditor-sv').waitFor();
    // In this Vditor build the Markdown mode is a textarea.
    await page.waitForFunction(()=>/- \[[xX]\] Ligar/.test(document.querySelector('#apuracao-vditor .vditor-sv').value),null,{timeout:8000});
    assert.equal(await page.locator('#apuracao-estilo').isDisabled(),true,'estilos desativados no Markdown');
    await page.locator('#apuracao-vditor button[data-type="edit-mode"]').click();await page.locator('#apuracao-vditor button[data-mode="wysiwyg"]').click();
    await page.locator(BOX).first().waitFor();
    assert.equal(await page.locator(BOX).count(),4);assert.equal(await page.locator(`${BOX}:checked`).count(),2);
    await page.waitForTimeout(1000);
    assert.equal((await markdown(page)).trim(),before.trim(),'ida e volta não altera o Markdown');
    await page.click('#apuracao-mais');
    checks.push('Troca visual → Markdown → visual (em Mais) conserva tarefas, estado das caixas e o Markdown.');
    await page.evaluate(()=>scrollTo(0,0));
    await page.screenshot({path:path.join(shots,'caderno-desktop-1365-claro.png')});

    // 6. Styles: three named styles, selection kept; legacy levels named and preserved.
    await openNote(page,'Estilos');
    await caret(page,'Primeiro parágrafo',2,8);
    await page.waitForFunction(()=>document.querySelector('#apuracao-estilo').value==='p');
    for(const [value,prefix] of [['h2','## '],['h3','### '],['p','']]){
      await page.selectOption('#apuracao-estilo',value);
      await page.waitForFunction(prefix=>document.querySelector('#apuracao-texto').value.startsWith(prefix+'Primeiro parágrafo'),prefix,{timeout:5000});
      sel=await selectionInfo(page);
      // Subtítulo is shown in capitals by CSS, and Selection.toString() follows the rendering.
      assert.equal(sel.selected.toLowerCase(),'imeiro','seleção preservada ao trocar o estilo');
      assert.equal(await page.locator('#apuracao-estilo').inputValue(),value);
    }
    assert.doesNotMatch(await markdown(page),/^#/m,'Texto normal volta a parágrafo');
    assert.deepEqual(await page.locator('#apuracao-estilo option').allInnerTexts(),['Texto normal','Título da seção','Subtítulo']);
    await waitSaved(page);
    await openNote(page,'Nota legada');
    await caret(page,'Título antigo',3);
    await page.waitForFunction(()=>document.querySelector('#apuracao-estilo').value==='h1');
    assert.equal(await page.locator('#apuracao-estilo option:checked').innerText(),'Cabeçalho 1 (legado)');
    await caret(page,'Detalhe antigo',2);
    await page.waitForFunction(()=>document.querySelector('#apuracao-estilo').value==='h4');
    assert.equal(await page.locator('#apuracao-estilo option:checked').innerText(),'Cabeçalho 4 (legado)');
    assert.match(await markdown(page),/^# Título antigo$/m);assert.match(await markdown(page),/^#### Detalhe antigo$/m);
    await caret(page,'Título antigo',3);await page.selectOption('#apuracao-estilo','p');
    await page.waitForFunction(()=>document.querySelector('#apuracao-texto').value.startsWith('Título antigo'));
    await waitSaved(page);
    assert.match(await markdown(page),/^#### Detalhe antigo$/m,'nível legado não tocado continua');
    checks.push('Seletor: Texto normal, Título da seção (##) e Subtítulo (###) com a seleção preservada; h1/h4 legados aparecem como "Cabeçalho n (legado)" e só mudam quando o usuário troca.');

    // 7. Draft: network failure → reload → draft offered → restored → saved.
    await openNote(page,'Rascunho');
    await page.route('**/api/apuracao-nota-salvar',route=>route.abort('internetdisconnected'));
    await caret(page,'Texto salvo da nota de rascunho.','Texto salvo da nota de rascunho.'.length);
    await page.keyboard.type(' Escrito sem conexão.');
    await page.waitForFunction(()=>document.querySelector('#apuracao-salvamento').dataset.estado==='rede',null,{timeout:20000});
    assert.equal(await page.locator('#apuracao-salvamento').innerText(),'Sem conexão. Rascunho guardado nesta aba; tentando de novo…');
    const stored=await page.evaluate(prefix=>Object.keys(sessionStorage).filter(k=>k.startsWith(prefix)).map(k=>[k,JSON.parse(sessionStorage.getItem(k))]),DRAFT_PREFIX);
    assert.equal(stored.length,1);assert.match(stored[0][0],/^vlado:rascunho:local:alpha:E[0-9a-f]+$/);
    assert.match(stored[0][1].texto,/Escrito sem conexão\./);
    assert.equal(await page.evaluate(()=>Object.values(localStorage).some(v=>v.includes('Escrito sem conexão'))),false,'nada em localStorage');
    // The network stays down through the reload (the last save attempt on unload fails too).
    await page.reload();await page.locator('#apuracao-formatar').waitFor({state:'attached'});
    await openNote(page,'Rascunho');
    await page.locator('#apuracao-rascunho:not([hidden])').waitFor();
    assert.doesNotMatch(await markdown(page),/Escrito sem conexão/,'nada muda antes da escolha');
    assert.equal(await page.locator('#apuracao-nota-titulo').getAttribute('readonly'),'','edição espera a escolha');
    await page.unroute('**/api/apuracao-nota-salvar');
    await page.click('#apuracao-rascunho-restaurar');
    await waitSaved(page);
    assert.match(await markdown(page),/Escrito sem conexão\./);
    assert.equal(await page.evaluate(prefix=>Object.keys(sessionStorage).some(k=>k.startsWith(prefix)),DRAFT_PREFIX),false,'rascunho apagado depois do 200');
    checks.push('Falha de rede simulada: estado "Sem conexão…", rascunho só na sessionStorage da aba; recarregar a aba oferece o rascunho, restaurar salva no servidor e apaga o rascunho.');

    // 8. Conflict between two tabs.
    const second=await newPage(context,'light');
    await openCaderno(second);await openNote(second,'Rascunho');
    await caret(second,'Texto salvo',0);await second.keyboard.type('Outra aba. ');await waitSaved(second);
    await caret(page,'Texto salvo',0);await page.keyboard.type('Esta aba. ');
    await page.waitForFunction(()=>document.querySelector('#apuracao-salvamento').dataset.estado==='conflito',null,{timeout:20000});
    assert.equal(await page.locator('#apuracao-conflito').isVisible(),true);
    assert.match(await markdown(page),/Esta aba\./,'texto local continua na tela');
    assert.equal(await page.evaluate(prefix=>Object.keys(sessionStorage).some(k=>k.startsWith(prefix)),DRAFT_PREFIX),true,'rascunho guardado no conflito');
    await page.click('#apuracao-copiar');await page.click('#apuracao-recarregar');
    await page.waitForFunction(()=>/Outra aba\./.test(document.querySelector('#apuracao-texto').value));
    assert.doesNotMatch(await markdown(page),/Esta aba\./);
    await second.close();
    checks.push('Duas abas: a segunda gravação com revisão antiga vira conflito, para o salvamento, mantém o texto local e o rascunho; recarregar traz a versão da outra aba.');

    // 9. Open the original from a source and come back to the same caret and scroll.
    await openNote(page,'Fonte e retorno');
    await caret(page,'Parágrafo sintético 12 ',5);
    await page.evaluate(()=>{document.querySelector('#apuracao-vditor').scrollIntoView({block:'start'});scrollBy(0,500);});
    const scrollBefore=await page.evaluate(()=>scrollY);
    await page.locator('#apuracao-fontes .note-source-doc button').first().click();
    await page.locator('#original-dialogo[open]').waitFor();
    await page.keyboard.press('Escape');await page.locator('#original-dialogo').waitFor({state:'hidden'});await page.waitForTimeout(200);
    sel=await selectionInfo(page);
    assert.ok(sel.inEditor&&sel.text.includes('Parágrafo sintético 12 ')&&sel.offset===5,'cursor de volta ao ponto: '+JSON.stringify(sel));
    assert.ok(Math.abs(await page.evaluate(()=>scrollY)-scrollBefore)<=4,'rolagem preservada');
    checks.push('Abrir o original pela fonte e fechar devolve o cursor e a rolagem ao mesmo ponto da nota.');

    // 10. Phones (320 and 390) and both themes: no horizontal scroll, drawers, captures.
    for(const theme of ['light','dark']){
      const phone=await browser.newContext({viewport:{width:390,height:860},deviceScaleFactor:2,isMobile:true,hasTouch:true});
      const mobile=await newPage(phone,theme);
      await openCaderno(mobile);
      assert.equal(await mobile.evaluate(()=>document.documentElement.dataset.theme),theme);
      await openNote(mobile,'Tarefas da pauta');await mobile.locator(BOX).first().waitFor();
      for(const width of [320,390]){
        await noOverflow(mobile,width);
        assert.equal(await mobile.locator('#apuracao-lista-painel').isVisible(),false,'lista em gaveta fechada');
        const box=await mobile.locator(BOX).first().boundingBox();assert.ok(box.width>=44&&box.height>=44,'alvo de toque');
      }
      await mobile.locator(BOX).nth(1).tap();
      await mobile.waitForFunction(()=>/^- \[ \] Conferir/m.test(document.querySelector('#apuracao-texto').value));
      await waitSaved(mobile);
      await mobile.locator(BOX).nth(1).tap();await waitSaved(mobile);
      await mobile.evaluate(()=>scrollTo(0,0));
      await mobile.screenshot({path:path.join(shots,`caderno-celular-390-${theme==='light'?'claro':'escuro'}.png`)});
      await mobile.click('#apuracao-ver-notas');await mobile.locator('#apuracao-lista-painel.is-aberta').waitFor();
      await mobile.waitForTimeout(300);
      assert.equal(await mobile.locator('#apuracao-busca').isVisible(),true);
      await noOverflow(mobile,390);
      await mobile.screenshot({path:path.join(shots,`caderno-celular-390-notas-${theme==='light'?'claro':'escuro'}.png`)});
      await mobile.fill('#apuracao-busca','fonte');
      assert.equal(await mobile.locator('#apuracao-notas button').count(),1);
      await mobile.locator('#apuracao-notas button').first().click();
      await mobile.waitForFunction(()=>document.querySelector('#apuracao-nota-titulo').value==='Fonte e retorno');
      await mobile.locator('#apuracao-lista-painel.is-aberta').waitFor({state:'detached'});
      await mobile.click('#apuracao-ver-fontes');await mobile.locator('#apuracao-fontes-painel.is-aberta').waitFor();await mobile.waitForTimeout(300);
      await noOverflow(mobile,320);
      await mobile.keyboard.press('Escape');await mobile.locator('#apuracao-fontes-painel.is-aberta').waitFor({state:'detached'});
      if(theme==='dark'){
        const desk=await newPage(context,'dark');await openCaderno(desk);await openNote(desk,'Tarefas da pauta');await desk.locator(BOX).first().waitFor();
        await desk.evaluate(()=>scrollTo(0,0));await desk.screenshot({path:path.join(shots,'caderno-desktop-1365-escuro.png')});await desk.close();
      }
      await phone.close();
    }
    checks.push('Celular (320 e 390 px), claro e escuro: sem rolagem horizontal, nota em primeiro plano, lista com busca e fontes em gavetas, toque na caixa salva; capturas em desktop 1365 e celular 390.');

    assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
    await fs.writeFile(path.join(output,'resultado.json'),JSON.stringify({estado:'aprovado',natureza:'notas sintéticas, servidor local, sem inferência',checks,erros:errors,requisicoes_externas:external},null,2));
    console.log(`QA caderno editor: OK (${checks.length} verificações)`);
  }catch(error){
    await page.screenshot({path:path.join(output,'falha.png'),fullPage:true}).catch(()=>{});
    await fs.writeFile(path.join(output,'falha.json'),JSON.stringify({erro:String(error),stack:error.stack,checks,errors,external,
      editor:await page.locator('#apuracao-vditor .vditor-content').innerText().catch(()=>''),markdown:await markdown(page).catch(()=>'')},null,2));
    throw error;
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
