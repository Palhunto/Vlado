'use strict';
(() => {
  const dialog=$('caderno-dialogo'), chosen=new Map();
  let session=null, ready=false, saving=false, loading=false, offset=0, next=null, version=0, dialogVersion=0, catalogVersion=0, lastAuthor='';
  // In the pilot the server signs records with the account name and ignores a typed author.
  if(document.body.dataset.modo!=='local'){
    $('caderno-autor').required=false;$('caderno-autor').closest('label').hidden=true;
    $('caderno-autoria-ajuda').textContent='A autoria vem da sua conta da Mesa. Registrar uma anotação não aprova conclusões da IA.';
    $('caderno-descricao').textContent='Trechos, achados e cruzamentos de autoria humana, separados dos resultados da IA. Neste piloto, a autoria vem da conta da Mesa que salva.';
  }
  function error(message=''){$('caderno-erro').textContent=message;$('caderno-erro').hidden=!message;}
  function formError(message=''){$('caderno-form-erro').textContent=message;$('caderno-form-erro').hidden=!message;}
  function counts(){
    const blocked=loading||saving;
    $('caderno-contagem').textContent=chosen.size?Leitura.quantidade(chosen.size,'registro selecionado','registros selecionados')+'.':'Nenhum registro selecionado.';
    $('caderno-cruzar').disabled=blocked||chosen.size<2;
    for(const id of ['caderno-exportar','caderno-perguntar','caderno-limpar'])$(id).disabled=blocked||!chosen.size;
    $('caderno-novo').disabled=blocked||!$('caderno-caso').value;
    $('caderno-buscar').disabled=blocked||!$('caderno-caso').value;
  }
  function sourceDoc(){return session?.documents?.documentos.find(d=>d.documento_id===$('caderno-documento').value);}
  function formControls(){
    const cross=session?.mode==='cruzamento';
    for(const control of $('caderno-form').elements)control.disabled=saving||!ready||(cross&&$('caderno-fonte-form').contains(control));
    $('caderno-fechar').disabled=saving;
    const pdf=sourceDoc()?.formato==='.pdf';
    $('caderno-pagina-label').hidden=cross||!pdf;
    $('caderno-pagina').disabled=saving||!ready||cross||!pdf;
    $('caderno-pagina').required=!cross&&pdf;
    $('caderno-localizador').required=!cross&&!pdf;
    $('caderno-anotacao').required=cross||$('caderno-tipo').value==='achado';
  }
  window.trechoSelecionadoCaderno=(container,fallback='')=>{
    const selected=window.getSelection();
    return selected&&!selected.isCollapsed&&container?.contains(selected.anchorNode)&&container.contains(selected.focusNode)?selected.toString().trim():fallback;
  };
  window.mostrarRegistrosCaderno=(target,bundle,selectable=false)=>{
    target.replaceChildren();
    for(const item of bundle.registros){
      const entry=item.registro,card=element('article',undefined,'panel notebook-entry');
      card.dataset.registro=entry.id;
      card.append(element('p',entry.tipo==='cruzamento'?'Cruzamento humano':entry.tipo==='achado'?'Achado humano':'Trecho selecionado pelo jornalista','eyebrow'),
        element('h3',entry.titulo),element('p',Leitura.autoria(entry.autor,entry.origem_autoria),'notebook-author'),
        element('p',new Date(entry.criado_em_utc).toLocaleString('pt-BR'),'small'));
      if(entry.anotacao)card.append(element('p',entry.anotacao,'human-review-note'));
      for(const [index,source]of entry.fontes.entries()){
        const block=element('section',undefined,'notebook-source');
        block.append(element('h4',`${Leitura.nome(source)} · ${source.localizador}`),element('blockquote',source.trecho),
          element('p',source.conferencia_textual==='literal_localizado'?'Trecho localizado no texto. Isso não valida a interpretação.':'Transcrição humana: o trecho não foi validado automaticamente pelo extrator.','small'));
        const original=element('button',Leitura.rotuloOriginal(Leitura.pagina(source)),'secondary'),feedback=element('p','','small');original.type='button';feedback.setAttribute('role','status');
        original.addEventListener('click',async()=>{original.disabled=true;try{const blob=await api('caderno-original',{caso:bundle.caso_id,registro_id:entry.id,sha256:item.sha256,fonte_indice:index},true);const atual=window.contextoCaso?.();if(atual&&atual!==bundle.caso_id)return;await window.abrirOriginal(blob,source.nome_documento,source.pagina_pdf);}catch(failure){feedback.textContent=failure.message;}finally{original.disabled=false;}});
        block.append(original,feedback);card.append(block);
      }
      if(entry.vinculos.length){const parents=element('details');parents.append(element('summary','Contribuições humanas relacionadas'));for(const parent of entry.vinculos)parents.append(element('p',`${parent.titulo} · autoria: ${parent.autor}`));card.append(parents);}
      card.append(Leitura.tecnicos(element('pre',JSON.stringify(item,null,2),'raw-briefing')));
      if(selectable){const followup=element('button','Criar diligência','secondary');followup.type='button';
        followup.addEventListener('click',()=>window.abrirDiligencia({caso:bundle.caso_id,redacao:entry.titulo,
          origem:{tipo:'humana',registro_id:entry.id,sha256:item.sha256}}));card.append(followup);}
      if(selectable){
        const label=element('label',undefined,'feedback-choice'),input=element('input');input.type='checkbox';input.checked=chosen.has(entry.id);input.setAttribute('aria-label',`Selecionar contribuição humana: ${entry.titulo}`);
        input.addEventListener('change',()=>{error();if(input.checked){if(chosen.size>=20){input.checked=false;error('Selecione até 20 registros por operação.');return;}chosen.set(entry.id,{registro_id:entry.id,sha256:item.sha256});}else chosen.delete(entry.id);counts();});
        label.append(input,element('span','Selecionar para cruzamento ou pergunta'));card.append(label);
      }
      target.append(card);
    }
  };
  async function conversations(){
    const caseId=$('caderno-caso').value;
    $('caderno-conversa').replaceChildren(new Option('Nova conversa com os documentos cadastrados',''));
    if(!caseId)return;
    const result=await api('codex-listar',{caso:caseId});
    if(caseId!==$('caderno-caso').value)return;
    for(const chat of result.conversas){const option=new Option(chat.titulo,chat.id);option.disabled=['preparando','executando','publicando','cancelando','aguardando_aprovacao'].includes(chat.estado);$('caderno-conversa').append(option);}
    const current=window.estadoConversa?.();
    if(current?.caso===caseId&&!current.ocupada&&[...$('caderno-conversa').options].some(o=>o.value===current.conversa))$('caderno-conversa').value=current.conversa;
  }
  async function search(start=0){
    const sequence=++version,caseId=$('caderno-caso').value;if(!caseId)return;
    loading=true;counts();error();$('caderno-anterior').disabled=true;$('caderno-proximo').disabled=true;
    $('caderno-status').textContent='Conferindo os registros humanos e suas fontes…';
    try{
      const result=await api('caderno-listar',{caso:caseId,texto:$('caderno-texto').value,limite:20,deslocamento:start});
      if(sequence!==version||caseId!==$('caderno-caso').value)return;
      offset=result.deslocamento;next=result.proximo_deslocamento;
      window.mostrarRegistrosCaderno($('caderno-resultados'),{caso_id:caseId,registros:result.resultados},true);
      $('caderno-status').textContent=result.total?`${Leitura.quantidade(result.total,'contribuição humana','contribuições humanas')} nesta pesquisa.`:'Nenhum registro humano nesta pesquisa. Adicione um trecho ou achado.';
      if(result.origem_autoria==='mista')$('caderno-status').textContent+=' '+window.I18N.t('Autoria mista: parte autenticada pela conta da Mesa, parte declarada pelo usuário.');
      $('caderno-intervalo').textContent=result.total?`${start+1}–${start+result.resultados.length} de ${result.total}`:'0 registros';
      $('caderno-anterior').disabled=!offset;$('caderno-proximo').disabled=next===null;
      window.registrarPaginaMesa?.('caderno', offset);
    }catch(failure){if(sequence===version){error(failure.message);$('caderno-status').textContent='A consulta falhou. Uma falha de registro ou fonte não equivale a caderno vazio.';}}
    finally{if(sequence===version){loading=false;counts();}}
  }
  async function catalog(){
    const selected=window.contextoCaso?.() ?? $('caderno-caso').value,request=++catalogVersion;
    loading=true;counts();
    if(matchMedia('(min-width:1024px)').matches){$('caderno-anterior').disabled=true;$('caderno-proximo').disabled=true;}
    try{const response=await fetch('/api/catalogo'),data=await response.json();if(!response.ok)throw new Error(data.erro||'Falha ao listar apurações.');if(request!==catalogVersion||selected!==$('caderno-caso').value)return;$('caderno-caso').replaceChildren(new Option('Selecione uma apuração',''),...data.casos.map(c=>new Option(c.titulo,c.id)));if(data.casos.some(c=>c.id===selected))$('caderno-caso').value=selected;else if(selected){chosen.clear();$('caderno-resultados').replaceChildren();}await conversations();if($('caderno-caso').value)await search(0);counts();}catch(failure){if(request===catalogVersion)error(failure.message);}
    finally{if(request===catalogVersion){loading=false;counts();}}
  }
  async function loadDocuments(prefill={},keep=false){
    const captured=session,sequence=++dialogVersion;ready=false;formControls();
    const data=await api('caderno-documentos',captured.scope);
    if(sequence!==dialogVersion||session!==captured||!dialog.open)return;
    captured.documents=data;
    const selected=keep?$('caderno-documento').value:prefill.documento_id;
    $('caderno-documento').replaceChildren(...data.documentos.map(d=>new Option(Leitura.nome(d),d.documento_id)));
    if(selected&&data.documentos.some(d=>d.documento_id===selected))$('caderno-documento').value=selected;
    if(!data.documentos.length)throw new Error('Cadastre um documento antes de registrar uma passagem.');
    if(!keep){$('caderno-trecho').value=prefill.trecho||'';$('caderno-pagina').value=prefill.pagina_pdf||'';$('caderno-localizador').value=prefill.localizador||'';$('caderno-titulo-input').value=Leitura.nome(sourceDoc())+' · trecho';originalLabel();}
    $('caderno-escopo').textContent=`Apuração selecionada · ${data.corpus_id}${data.rodada?' · fonte da rodada '+data.rodada:' · documentos cadastrados'}`;
    ready=true;formControls();
  }
  window.abrirRegistroCaderno=async prefill=>{
    if(saving)return;prefill=prefill||{};
    if(!prefill.caso){error('Selecione uma apuração.');return;}
    session={mode:'fonte',scope:{caso:prefill.caso,...(prefill.rodada?{rodada:prefill.rodada}:{})},request:crypto.randomUUID().replaceAll('-','')};
    ready=false;$('caderno-form').reset();$('caderno-autor').value=lastAuthor;
    $('caderno-fonte-form').hidden=false;$('caderno-cruzamento-fontes').hidden=true;
    $('caderno-dialogo-titulo').textContent='Registrar trecho com fonte';$('caderno-form-status').textContent='Abrindo os documentos autorizados…';
    formError();if(!dialog.open)dialog.showModal();formControls();
    try{await loadDocuments(prefill);$('caderno-form-status').textContent='Confira a passagem no original, identifique a autoria humana e salve.';}
    catch(failure){formError(failure.message);}
  };
  $('caderno-fechar').addEventListener('click',()=>{if(!saving)dialog.close();});
  dialog.addEventListener('cancel',event=>{if(saving)event.preventDefault();});
  dialog.addEventListener('close',()=>{++dialogVersion;session=null;ready=false;});
  // The original opens at the page typed in the form; the label says which.
  function originalLabel(){$('caderno-original').textContent=Leitura.rotuloOriginal(Leitura.pagina({pagina_pdf:$('caderno-pagina').value}));}
  $('caderno-pagina').addEventListener('input',originalLabel);
  $('caderno-documento').addEventListener('change',()=>{$('caderno-trecho').value='';$('caderno-pagina').value='';$('caderno-localizador').value='';$('caderno-manual').checked=false;originalLabel();formControls();});
  $('caderno-tipo').addEventListener('change',formControls);
  $('caderno-fontes-atualizar').addEventListener('click',async()=>{formError();try{await loadDocuments({},true);}catch(failure){formError(failure.message);}});
  $('caderno-original').addEventListener('click',async()=>{
    const doc=sourceDoc();if(!session||!doc)return;
    try{const scope=session.scope,blob=await api('caderno-original',{...scope,origem_id:session.documents.origem_id,documento_id:doc.documento_id,documento_sha256:doc.sha256},true);const atual=window.contextoCaso?.();if(atual&&scope.caso&&atual!==scope.caso)return;await window.abrirOriginal(blob,doc.nome_recebido,$('caderno-pagina').value);}
    catch(failure){formError(failure.message);}
  });
  $('caderno-form').addEventListener('submit',async event=>{
    event.preventDefault();if(!session||!ready||saving)return;
    const captured=session,cross=captured.mode==='cruzamento',doc=sourceDoc();
    const base={caso:captured.scope.caso,requisicao_id:captured.request,titulo:$('caderno-titulo-input').value,anotacao:$('caderno-anotacao').value,autor:$('caderno-autor').value};
    const body=cross?{...base,selecoes:captured.choices}:{...base,...captured.scope,origem_id:captured.documents.origem_id,documento_id:doc.documento_id,documento_sha256:doc.sha256,pagina_pdf:doc.formato==='.pdf'?Number($('caderno-pagina').value):null,localizador:$('caderno-localizador').value,trecho:$('caderno-trecho').value,tipo:$('caderno-tipo').value,transcricao_manual:$('caderno-manual').checked};
    saving=true;formControls();counts();formError();$('caderno-form-status').textContent='Salvando a contribuição humana e seus vínculos…';
    try{
      const result=await api(cross?'caderno-cruzar':'caderno-salvar',body);lastAuthor=result.registro.autor;dialog.close();
      if($('caderno-caso').value!==captured.scope.caso)chosen.clear();
      if(![...$('caderno-caso').options].some(option=>option.value===captured.scope.caso))$('caderno-caso').append(new Option(captured.scope.caso,captured.scope.caso));
      $('caderno-caso').value=captured.scope.caso;
      $('experiencia-status').textContent='Trecho com fonte registrado no Caderno. Continue aqui ou abra as contribuições.';if(!$('area-caderno').hidden)search(0);
    }catch(failure){formError(failure.message);$('caderno-form-status').textContent='Salvamento não confirmado nesta tela. O formulário foi preservado; reenviar a mesma tentativa não duplica o registro.';}
    finally{saving=false;formControls();counts();}
  });
  $('caderno-caso').addEventListener('change',async()=>{++version;++catalogVersion;chosen.clear();$('caderno-resultados').replaceChildren();$('caderno-texto').value='';error();counts();try{await conversations();if($('caderno-caso').value)await search(0);}catch(failure){error(failure.message);}});
  $('caderno-atualizar').addEventListener('click',catalog);
  $('caderno-pesquisa').addEventListener('submit',event=>{event.preventDefault();search(window.paginaRestauradaMesa?.('caderno') || 0);});
  $('caderno-anterior').addEventListener('click',()=>search(Math.max(0,offset-20)));
  $('caderno-proximo').addEventListener('click',()=>{if(next!==null)search(next);});
  window.limparSelecaoCaderno=caseId=>{if(caseId&&caseId!==$('caderno-caso').value)return;chosen.clear();for(const input of $('caderno-resultados').querySelectorAll('input[type=checkbox]'))input.checked=false;counts();};
  $('caderno-limpar').addEventListener('click',()=>window.limparSelecaoCaderno());
  $('caderno-novo').addEventListener('click',()=>window.abrirRegistroCaderno({caso:$('caderno-caso').value}));
  $('caderno-exportar').addEventListener('click',async()=>{try{const result=await api('caderno-exportar',{caso:$('caderno-caso').value,selecoes:[...chosen.values()]});window.exportarEditorial(result,'caderno_humano',$('caderno-formato').value);}catch(failure){error(failure.message);}});
  $('caderno-cruzar').addEventListener('click',async()=>{
    if(chosen.size<2||saving)return;const caseId=$('caderno-caso').value,choices=[...chosen.values()];
    try{const bundle=await api('caderno-exportar',{caso:caseId,selecoes:choices});session={mode:'cruzamento',scope:{caso:caseId},choices,request:crypto.randomUUID().replaceAll('-','')};$('caderno-form').reset();$('caderno-autor').value=lastAuthor;$('caderno-fonte-form').hidden=true;$('caderno-cruzamento-fontes').hidden=false;window.mostrarRegistrosCaderno($('caderno-cruzamento-fontes'),bundle);$('caderno-dialogo-titulo').textContent='Criar cruzamento humano';$('caderno-escopo').textContent=`${choices.length} contribuições humanas serão relacionadas, preservando suas autorias e fontes.`;$('caderno-form-status').textContent='Descreva o cruzamento com suas palavras e identifique sua autoria.';ready=true;formError();formControls();dialog.showModal();}catch(failure){error(failure.message);}
  });
  $('caderno-perguntar').addEventListener('click',async()=>{
    if(!chosen.size||loading)return;loading=true;counts();error();
    const scope={caso:$('caderno-caso').value,conversa:$('caderno-conversa').value||null,selecoes:[...chosen.values()]};
    const current=window.estadoConversa?.();if(current?.caso===scope.caso&&current.conversa===scope.conversa&&current.atualizar_corpus)scope.atualizar_corpus=current.atualizar_corpus;
    try{const preview=await api('codex-caderno-previa',scope);await window.continuarComCaderno(preview,scope);}
    catch(failure){error(failure.message);}finally{loading=false;counts();}
  });
  window.addEventListener('caderno-abrir',catalog);
  window.addEventListener('acervo-alterado',()=>{if(!$('area-caderno').hidden)catalog();});
  counts();
})();
