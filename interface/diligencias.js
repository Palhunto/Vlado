'use strict';
(() => {
  const dialog=$('diligencias-dialogo'), responseDialog=$('diligencias-resposta-dialogo');
  let session=null, response=null, documents=null, busy=false, version=0, lastAuthor='';
  const requestId=()=>crypto.randomUUID().replaceAll('-','');
  // In the pilot the server records the account name as the author and ignores a typed one.
  if(document.body.dataset.modo!=='local')for(const id of ['diligencias-autor','diligencias-resposta-autor']){$(id).required=false;$(id).closest('label').hidden=true;}
  function deadline(value,state){const [y,m,d]=value.split('-');const today=new Date();const local=[today.getFullYear(),String(today.getMonth()+1).padStart(2,'0'),String(today.getDate()).padStart(2,'0')].join('-');return `prazo ${d}/${m}/${y}${!['concluida','cancelada'].includes(state)&&value<local?' · vencida':value===local?' · hoje':''}`;}
  $('diligencias-nova').addEventListener('click',()=>{const caso=window.contextoCaso?.() || $('diligencias-caso').value;if(!caso){fail('diligencias-erro','Escolha uma apuração no topo da mesa.');return;}window.abrirDiligencia({caso});});
  function fail(id,message=''){$(id).textContent=message;$(id).hidden=!message;}
  function controls(){
    for(const id of ['diligencias-form','diligencias-upload','diligencias-resposta-form'])
      for(const field of $(id).elements)field.disabled=busy;
    $('diligencias-fechar').disabled=busy;$('diligencias-resposta-fechar').disabled=busy;
    $('diligencias-vincular').disabled=busy||!documents;
    $('diligencias-buscar').disabled=busy;
  }
  async function caseSelected(){
    const caseId=$('diligencias-caso').value,sequence=++version;
    $('diligencias-resultados').replaceChildren();$('diligencias-conversa').replaceChildren(new Option('Nova conversa com os documentos cadastrados',''));
    $('diligencias-incorporar').checked=false;fail('diligencias-erro');
    if(!caseId){$('diligencias-status').textContent='Selecione uma apuração.';return;}
    try{
      const chats=await api('codex-listar',{caso:caseId});if(sequence!==version)return;
      for(const chat of chats.conversas){const option=new Option(chat.titulo,chat.id);option.disabled=['preparando','executando','publicando','cancelando','aguardando_aprovacao'].includes(chat.estado);$('diligencias-conversa').append(option);}
      const current=window.estadoConversa?.();if(current?.caso===caseId&&!current.ocupada&&[...$('diligencias-conversa').options].some(o=>o.value===current.conversa))$('diligencias-conversa').value=current.conversa;
      await search();
    }catch(error){if(sequence===version)fail('diligencias-erro',error.message);}
  }
  async function catalog(){
    const selected=window.contextoCaso?.() ?? $('diligencias-caso').value,sequence=++version;
    $('diligencias-resultados').replaceChildren();$('diligencias-status').textContent='Atualizando apurações e diligências…';
    try{const res=await fetch('/api/catalogo'),data=await res.json();if(!res.ok)throw new Error(data.erro||'Falha ao listar apurações.');if(sequence!==version)return;
      $('diligencias-caso').replaceChildren(new Option('Selecione uma apuração',''),...data.casos.map(c=>new Option(c.titulo,c.id)));
      if(data.casos.some(c=>c.id===selected))$('diligencias-caso').value=selected;
      await caseSelected();
    }catch(error){fail('diligencias-erro',error.message);}
  }
  window.mostrarDiligencias=(target,bundle)=>{
    target.replaceChildren();
    for(const item of bundle.diligencias){
      const block=element('article',undefined,'feedback-item');
      block.append(element('h4',item.acao),element('p',`Questão de origem: ${item.origem.redacao}`),
        element('p',`Responsável declarado: ${item.responsavel} · ${pretty(item.estado)}${item.prazo?' · prazo '+item.prazo:''}`,'small'));
      for(const reply of item.respostas){block.append(element('p',`Resposta registrada por ${reply.autor}: ${reply.observacao}`));for(const doc of reply.documentos)block.append(element('p',`Documento: ${Leitura.nome(doc)}`,'small'));}
      target.append(block);
    }
  };
  async function resume(item){
    const scope={caso:item.caso,conversa:$('diligencias-conversa').value||null,selecoes:[{diligencia_id:item.id,sha256:item.sha256}]};
    try{
      const current=window.estadoConversa?.();let corpus=null;
      if(scope.conversa&&$('diligencias-incorporar').checked){corpus=await api('codex-corpus-previa',scope);scope.atualizar_corpus=corpus.solicitacao;}
      else if(current?.caso===scope.caso&&current.conversa===scope.conversa&&current.atualizar_corpus)scope.atualizar_corpus=current.atualizar_corpus;
      const preview=await api('codex-diligencias-previa',scope);
      if(corpus)preview.corpus_novo=corpus;
      await window.continuarComDiligencias(preview,scope);
    }catch(error){fail('diligencias-erro',error.message);}
  }
  function render(item){
    const state=item.diligencia,card=element('article',undefined,'panel diligence-entry');card.dataset.diligencia=item.id;
    card.append(element('p','DILIGÊNCIA DO JORNALISTA','eyebrow'),element('h3',state.acao),
      element('p',`Pendência: ${state.origem.redacao}`),element('p',`Origem: ${state.origem.identidade.tipo==='livre'?'ação livre':state.origem.identidade.tipo==='ia'?'achado da IA':'contribuição humana · '+state.origem.autor}`,'small'),
      element('p',`Estado: ${pretty(state.estado)}`,'support-badge'),element('p',`Responsável declarado: ${state.responsavel}${state.prazo?' · '+deadline(state.prazo,state.estado):''}`));
    const actions=element('div',undefined,'actions');
    for(const [label,handler]of [['Assumir / atualizar',()=>openUpdate(item)],['Anexar resposta',()=>openResponse(item)],['Retomar esta questão',()=>resume(item)]]){
      const button=element('button',label,'secondary');button.type='button';button.addEventListener('click',handler);actions.append(button);
    }
    const origin=element('button','Ver achado de origem','secondary');origin.type='button';
    origin.addEventListener('click',async()=>{try{
      const link=state.origem.identidade;
      if(link.tipo==='ia')await window.abrirAchadosDaRodada({caso:item.caso,rodada:link.rodada,revisao:link.revisao,geracao:'g1'},link.achado_id);
      else{const note=await api('caderno-detalhe',{caso:item.caso,registro_id:link.registro_id,sha256:link.sha256});const details=element('details');details.open=true;details.append(element('summary','Registro humano de origem'));const body=element('div');window.mostrarRegistrosCaderno(body,{caso_id:item.caso,registros:[note]});details.append(body);origin.after(details);origin.disabled=true;}
    }catch(error){fail('diligencias-erro',error.message);}});if(state.origem.identidade.tipo!=='livre')actions.append(origin);card.append(actions);
    for(const [r,reply]of state.respostas.entries()){
      const block=element('section',undefined,'notebook-source');block.append(element('h4','Resposta recebida'),element('p',reply.observacao),element('p',`${Leitura.autoria(reply.autor,reply.origem_autoria)} · ${new Date(reply.recebida_em_utc).toLocaleString('pt-BR')}`,'small'));
      for(const [d,doc]of reply.documentos.entries()){
        const button=element('button',`Baixar ${Leitura.nome(doc)}`,'secondary');button.type='button';button.addEventListener('click',async()=>{button.disabled=true;try{download(await api('diligencias-original',{caso:item.caso,diligencia_id:item.id,sha256:item.sha256,resposta_indice:r,documento_indice:d},true),doc.nome_recebido);}catch(error){fail('diligencias-erro',error.message);}finally{button.disabled=false;}});block.append(button);
      }card.append(block);
    }
    const history=element('details');history.append(element('summary','Histórico de responsáveis e estados'));
    for(const event of item.historico)history.append(element('p',`${new Date(event.em_utc).toLocaleString('pt-BR')} · ${Leitura.autoria(event.autor,event.origem_autoria)} · ${pretty(event.diligencia.estado)} · responsável: ${event.diligencia.responsavel}${event.diligencia.prazo?' · '+deadline(event.diligencia.prazo,event.diligencia.estado):''} · ${event.observacao||'Diligência criada.'}`));
    card.append(history,Leitura.tecnicos(element('pre',JSON.stringify(item,null,2),'raw-briefing')));return card;
  }
  function renderBoard(items){
    const board=element('div',undefined,'mesa-diligence-board');
    const groups=[['A FAZER',['a_solicitar','em_andamento']],['AGUARDANDO RESPOSTA',['aguardando_resposta']],['RESPOSTAS E CONCLUSÕES',['resposta_recebida','concluida','cancelada']]];
    for(const [label,states]of groups){
      const column=element('section',undefined,'mesa-diligence-column'),entries=items.filter(item=>states.includes(item.diligencia.estado));
      column.append(element('h3',`${label} · ${entries.length}`));
      if(entries.length)column.append(...entries.map(render));
      else column.append(element('p','Nenhuma diligência nesta seleção.','mesa-column-empty'));
      board.append(column);
    }
    $('diligencias-resultados').replaceChildren(board);
  }
  async function search(){
    const caseId=$('diligencias-caso').value,sequence=++version;if(!caseId)return;
    fail('diligencias-erro');$('diligencias-status').textContent='Conferindo diligências e respostas documentais…';
    try{const result=await api('diligencias-listar',{caso:caseId,estado:$('diligencias-estado-filtro').value,responsavel:$('diligencias-responsavel-filtro').value,texto:$('diligencias-texto').value});if(sequence!==version||caseId!==$('diligencias-caso').value)return;
      renderBoard(result.resultados);$('diligencias-status').textContent=result.total?Leitura.quantidade(result.total,'diligência','diligências')+'.':'Nenhuma diligência nesta seleção.';
    }catch(error){if(sequence===version){fail('diligencias-erro',error.message);$('diligencias-status').textContent='Consulta não concluída. Falha não equivale a lista vazia.';}}
  }
  window.abrirDiligencia=prefill=>{
    if(busy)return;session={caso:prefill.caso,origem:prefill.origem?structuredClone(prefill.origem):null,operation:'criar',request:requestId()};
    $('diligencias-form').reset();$('diligencias-autor').value=lastAuthor;$('diligencias-origem').textContent=prefill.origem?`Achado de origem: ${prefill.redacao}`:'Ação livre nesta apuração. O vínculo com um achado é opcional.';
    $('diligencias-dialogo-titulo').textContent='Criar diligência';$('diligencias-estado-label').hidden=true;$('diligencias-observacao').required=false;fail('diligencias-form-erro');controls();dialog.showModal();
  };
  function openUpdate(item){
    if(busy)return;session={caso:item.caso,item,operation:'atualizar',request:requestId()};
    $('diligencias-form').reset();$('diligencias-acao').value=item.diligencia.acao;$('diligencias-responsavel').value=item.diligencia.responsavel;$('diligencias-prazo').value=item.diligencia.prazo||'';
    $('diligencias-estado').value=item.diligencia.estado;$('diligencias-autor').value=lastAuthor;$('diligencias-origem').textContent=`Achado de origem: ${item.diligencia.origem.redacao}`;
    $('diligencias-dialogo-titulo').textContent='Assumir ou atualizar diligência';$('diligencias-estado-label').hidden=false;$('diligencias-observacao').required=true;fail('diligencias-form-erro');controls();dialog.showModal();
  }
  async function showCase(caseId){
    if(![...$('diligencias-caso').options].some(o=>o.value===caseId))$('diligencias-caso').append(new Option(caseId,caseId));
    $('diligencias-caso').value=caseId;$('diligencias-estado-filtro').value='';$('diligencias-responsavel-filtro').value='';$('diligencias-texto').value='';showArea('diligencias');
  }
  $('diligencias-form').addEventListener('submit',async event=>{
    event.preventDefault();if(busy||!session)return;busy=true;controls();fail('diligencias-form-erro');const captured=session;
    const data={caso:captured.caso,requisicao_id:captured.request,autor:$('diligencias-autor').value,observacao:$('diligencias-observacao').value,
      acao:$('diligencias-acao').value,responsavel:$('diligencias-responsavel').value,prazo:$('diligencias-prazo').value};
    if(captured.operation==='criar')data.origem=captured.origem;
    else Object.assign(data,{diligencia_id:captured.item.id,anterior_sha256:captured.item.sha256,estado:$('diligencias-estado').value});
    try{await api('diligencias-'+captured.operation,data);lastAuthor=data.autor;dialog.close();await showCase(captured.caso);}catch(error){fail('diligencias-form-erro',error.message);}finally{busy=false;controls();}
  });
  async function responseDocuments(selected=[]){
    documents=null;controls();const captured=response;
    const result=await api('caderno-documentos',{caso:captured.item.caso});if(response!==captured||!responseDialog.open)return;
    documents=result;$('diligencias-documentos').replaceChildren();
    for(const doc of result.documentos){const label=element('label',undefined,'feedback-choice'),input=element('input');input.type='checkbox';input.value=doc.documento_id;input.checked=selected.includes(doc.documento_id);label.append(input,element('span',Leitura.nome(doc)));$('diligencias-documentos').append(label);}controls();
  }
  async function openResponse(item){
    if(busy)return;response={item,request:requestId()};documents=null;$('diligencias-upload').reset();$('diligencias-resposta-form').reset();$('diligencias-resposta-autor').value=lastAuthor;
    $('diligencias-resposta-origem').textContent=item.diligencia.acao;$('diligencias-recibo').hidden=true;$('diligencias-recibo').replaceChildren();$('diligencias-documentos').replaceChildren();fail('diligencias-resposta-erro');controls();responseDialog.showModal();
    try{await responseDocuments();}catch(error){fail('diligencias-resposta-erro',error.message);}
  }
  $('diligencias-upload').addEventListener('submit',async event=>{
    event.preventDefault();if(busy||!response)return;const files=[...$('diligencias-arquivos').files];if(!files.length)return;
    if(files.reduce((n,f)=>n+f.size,0)>50*1024*1024){fail('diligencias-resposta-erro','O lote excede 50 MB. Divida-o antes de cadastrar.');return;}
    busy=true;controls();fail('diligencias-resposta-erro');
    try{const arquivos=await Promise.all(files.map(encodeFile));const result=await api('cadastrar',{caso:response.item.caso,arquivos,natureza:$('diligencias-natureza').value});
      const receipt=$('diligencias-recibo');receipt.replaceChildren(element('h3','Recibo do cadastro'),element('p',`${result.recebidos} recebidos · ${result.novos} novos · ${result.duplicados} duplicados.`));
      for(const file of result.arquivos){receipt.append(element('p',`${file.nome_recebido} · ${file.estado}`));if(file.extracao_pdf)receipt.append(element('p',`${file.extracao_pdf.paginas_com_texto} de ${file.extracao_pdf.paginas_pdf??'?'} páginas com texto · ${file.extracao_pdf.estado}`,'small'));}
      receipt.append(Leitura.tecnicos(element('pre',JSON.stringify(result,null,2),'raw-briefing')));receipt.hidden=false;
      if(result.recebidos!==files.length||result.arquivos.length!==files.length)throw new Error('Recibo incompleto. Confira todos os arquivos antes de vincular.');
      $('diligencias-arquivos').value='';await responseDocuments([...new Set(result.arquivos.map(d=>d.documento_id))]);
    }catch(error){fail('diligencias-resposta-erro',error.message+' O vínculo ainda não foi confirmado; confira o cadastro antes de reenviar.');}finally{busy=false;controls();}
  });
  $('diligencias-documentos-atualizar').addEventListener('click',async()=>{if(busy||!response)return;busy=true;controls();fail('diligencias-resposta-erro');try{await responseDocuments();}catch(error){fail('diligencias-resposta-erro',error.message);}finally{busy=false;controls();}});
  $('diligencias-resposta-form').addEventListener('submit',async event=>{
    event.preventDefault();if(busy||!response||!documents)return;const ids=[...$('diligencias-documentos').querySelectorAll('input:checked')].map(input=>input.value);
    if(!ids.length){fail('diligencias-resposta-erro','Selecione ao menos um documento cadastrado da resposta.');return;}
    const captured=response;busy=true;controls();fail('diligencias-resposta-erro');
    try{const author=$('diligencias-resposta-autor').value;await api('diligencias-responder',{caso:captured.item.caso,diligencia_id:captured.item.id,anterior_sha256:captured.item.sha256,requisicao_id:captured.request,
        autor:author,observacao:$('diligencias-resposta-nota').value,origem_id:documents.origem_id,documentos:documents.documentos.filter(d=>ids.includes(d.documento_id)).map(d=>({documento_id:d.documento_id,sha256:d.sha256}))});
      lastAuthor=author;responseDialog.close();await search();
    }catch(error){fail('diligencias-resposta-erro',error.message);}finally{busy=false;controls();}
  });
  $('diligencias-fechar').addEventListener('click',()=>{if(!busy)dialog.close();});$('diligencias-resposta-fechar').addEventListener('click',()=>{if(!busy)responseDialog.close();});
  for(const modal of [dialog,responseDialog])modal.addEventListener('cancel',event=>{if(busy)event.preventDefault();});
  dialog.addEventListener('close',()=>{session=null;});responseDialog.addEventListener('close',()=>{response=null;documents=null;});
  $('diligencias-caso').addEventListener('change',caseSelected);$('diligencias-filtros').addEventListener('submit',event=>{event.preventDefault();search();});
  window.addEventListener('diligencias-abrir',catalog);window.addEventListener('acervo-alterado',()=>{if(!$('area-diligencias').hidden)catalog();});
})();
