'use strict';
// Appearance belongs to this browser, independently of the selected case.
(() => {
  const key = 'apuracao:tema';
  const button = document.getElementById('mesa-tema');
  const meta = document.querySelector('meta[name="theme-color"]');
  function apply(value) {
    // "claro" e "escuro" valem como estão; "sistema" ("Do sistema", em Minha conta, gravado como as outras escolhas) segue a preferência do sistema; sem valor
    // guardado a Mesa abre no escuro, como sempre abriu.
    const theme = value === 'light' || value === 'dark' ? value
      : value === 'sistema' && typeof matchMedia === 'function' && matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
    document.documentElement.dataset.theme = theme;
    const label = theme === 'dark' ? 'Modo claro' : 'Modo escuro';
    button.textContent = label;
    button.setAttribute('aria-label', `Ativar ${label.toLowerCase()}`);
    // The browser chrome follows the page background token of the applied theme.
    const background = getComputedStyle(document.documentElement).getPropertyValue('--theme-background').trim();
    if (background) meta.content = background;
  }
  let saved;
  try { saved = localStorage.getItem(key); } catch (_) { /* Storage may be blocked. */ }
  apply(saved);
  button.addEventListener('click', () => {
    const theme = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    apply(theme);
    try { localStorage.setItem(key, theme); } catch (_) { /* Switching still works. */ }
  });
  window.addEventListener('storage', event => {
    if (event.key === key || event.key === null) apply(event.newValue);
  });
})();
// Adaptive operational controls. The approved editorial shell follows below.
(() => {
  const desktop = matchMedia('(min-width:1024px)');
  const form = $('codex-form'), header = document.querySelector('.app-header');
  const navigation = [...document.querySelectorAll('.areas button:not([hidden])')].map(button => ({button,id:button.id,link:null}));
  const metadata = new Map();
  let body = null, toolbar = null, toggle = null, caption = null, collapsed = false, hadAnswer = false, defaultDecided = false;
  let findingControls = null, findingFormNodes = null;
  let findingSearchPosition = null;
  let appliedDesktop = null;
  const activeArea = () => window.enderecoAreaMesa().searchParams.get('area');
  function navigationState() {
    if (!desktop.matches) return;
    const area = activeArea();
    for (const item of navigation) {
      if (!item.link) continue;
      const target = item.id.replace('ver-','');
      item.link.href = window.enderecoAreaMesa(target);
      item.link.removeAttribute('aria-pressed');
      if (target === area || target === 'apuracao' && area === 'caderno') item.link.setAttribute('aria-current','page');
      else item.link.removeAttribute('aria-current');
    }
  }
  function geometry() {
    // The composer height keeps anchored content clear of the sticky form at every width.
    document.documentElement.style.setProperty('--mesa-composer-height',`${form.getBoundingClientRect().height}px`);
    if (!desktop.matches) return;
    document.documentElement.style.setProperty('--mesa-header-height',`${header.getBoundingClientRect().height}px`);
  }
  const resize = new ResizeObserver(geometry);
  resize.observe(header);resize.observe(form);
  function renderComposer() {
    if (!body) return;
    if (body.hidden !== collapsed) body.hidden = collapsed;
    form.classList.toggle('desktop-composer-closed',collapsed);
    toggle.setAttribute('aria-expanded',String(!collapsed));
    const label = collapsed ? 'Escrever pergunta' : 'Recolher pergunta';
    if (toggle.textContent !== label) toggle.textContent = label;
    const text = collapsed ? ($('codex-pergunta').value.trim() ? 'Rascunho preservado' : 'Continue a conversa com os documentos') : 'Sua pergunta';
    if (caption.textContent !== text) caption.textContent = text;
  }
  window.abrirComposicaoMesa = () => {
    if (!body) return;
    collapsed = false;renderComposer();
  };
  // The composer folds at every width. On a desktop it gives way to an answer; on a narrow
  // screen, where it would hold a third of the viewport, it gives way to the conversation.
  function buildComposer() {
    body = element('div');body.id = 'desktop-composicao';
    body.append(...form.childNodes);
    toolbar = element('div',undefined,'desktop-composer-toolbar');
    caption = element('span','Sua pergunta','small');
    toggle = element('button','Recolher pergunta','secondary');toggle.type = 'button';
    toggle.id = 'desktop-composicao-alternar';toggle.setAttribute('aria-controls',body.id);
    toggle.addEventListener('click',() => {
      collapsed = !collapsed;renderComposer();
      if (!collapsed) $('codex-pergunta').focus();
      else toggle.focus();
    });
    toolbar.append(caption,toggle);form.append(toolbar,body);
  }
  function composerState() {
    if (!body) return;
    const hasAnswer = !!$('codex-mensagens').querySelector(desktop.matches ? '.codex-answer' : '.codex-user,.codex-answer');
    const hasPending = [...body.querySelectorAll('.feedback-preview')].some(panel => !panel.hidden);
    // Saved conversations (or an answer) behind the field: it starts folded, so it does not cover them (UX-19). Decided once per case;
    // typed text, focus in the field or a pending contribution keep it open.
    const saved = $('codex-conversa').options.length > 1;
    if (!defaultDecided && (saved || hasAnswer)) {
      defaultDecided = true;
      if (!hasPending && !$('codex-pergunta').value.trim() && !body.contains(document.activeElement)) collapsed = true;
    }
    if (hasPending) collapsed = false;
    else if (hasAnswer && !hadAnswer && !$('codex-pergunta').value.trim() && document.activeElement !== $('codex-pergunta')) collapsed = true;
    else if (!hasAnswer && hadAnswer) collapsed = false;
    hadAnswer = hasAnswer;
    renderComposer();
  }
  function compactFindings() {
    // The version chip (app.js) folds the analysis selectors at every width.
    if (!desktop.matches || activeArea() !== 'achados' || !findingResult) return;
    if (findingControls) findingControls.open = false;
  }
  function feedbackState() {
    if (!desktop.matches) return;
    document.querySelector('.feedback-selection').classList.toggle('desktop-no-selection',$('observacoes-limpar').disabled && $('observacoes-continuar').disabled);
  }
  function activate() {
    // Media-query notifications may be queued for an already applied layout.
    if (appliedDesktop === desktop.matches) return;
    appliedDesktop = desktop.matches;
    if (desktop.matches) {
      for (const item of navigation) {
        const link = element('a',item.button.textContent);
        link.id = item.id;link.className = item.button.className;
        link.setAttribute('aria-controls',item.button.getAttribute('aria-controls'));
        link.addEventListener('click',event => {
          if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.button !== 0) return;
          event.preventDefault();item.button.click();
        });
        // Keep the original node and all its action listeners for mobile and resize.
        item.button.removeAttribute('id');item.button.replaceWith(link);item.link = link;
      }
      window.limitarNavegacaoConvidado?.();
      const findingsForm = $('achados-form');
      findingFormNodes = [...findingsForm.childNodes];
      findingControls = element('details',undefined,'desktop-finding-filters');
      findingControls.append(element('summary','Pesquisar e filtrar achados'));
      const fields = element('div',undefined,'desktop-finding-fields');
      for (const child of [...findingsForm.children]) {
        if (child.classList.contains('human-review-toolbar') || child.classList.contains('actions') || child.id === 'achados-filtros-ativos') continue;
        fields.append(child);
      }
      const search=$('achados-buscar');
      findingSearchPosition={button:search,parent:search.parentNode,next:search.nextSibling};
      fields.append(search);findingControls.append(fields);
      findingsForm.querySelector('.human-review-toolbar').after(findingControls);
      for (const field of document.querySelectorAll('input[id],textarea[id],select[id]')) {
        metadata.set(field,{name:field.getAttribute('name'),autocomplete:field.getAttribute('autocomplete')});
        if (!field.hasAttribute('name')) field.name = field.id;
        if (!field.hasAttribute('autocomplete') && !['file','checkbox'].includes(field.type) && field.tagName !== 'SELECT') field.autocomplete = 'off';
      }
      compactFindings();feedbackState();navigationState();geometry();window.barraMesa?.aplicar();
    } else {
      for (const item of navigation) {
        if (!item.link) continue;
        item.button.id = item.id;
        item.button.setAttribute('aria-pressed',String(item.link.getAttribute('aria-current') === 'page'));
        item.link.replaceWith(item.button);item.link = null;
      }
      window.barraMesa?.aplicar();
      if (findingSearchPosition) {
        const {button,parent,next}=findingSearchPosition;parent.insertBefore(button,next);
        findingSearchPosition=null;
      }
      if (findingFormNodes) $('achados-form').replaceChildren(...findingFormNodes);
      findingControls = null;findingFormNodes = null;
      document.querySelector('.feedback-selection').classList.remove('desktop-no-selection');
      for (const [field,attrs] of metadata) for (const [name,value] of Object.entries(attrs)) {
        if (value === null) field.removeAttribute(name);else field.setAttribute(name,value);
      }
      metadata.clear();
      document.documentElement.style.removeProperty('--mesa-header-height');
    }
    composerState();geometry();
  }
  registrarGanchoArea({depois: () => {navigationState();geometry();}});
  window.addEventListener('mesa-rota-alterada',navigationState);
  window.addEventListener('mesa-consulta',event => {if (event.detail.area === 'achados') compactFindings();});
  new MutationObserver(composerState).observe($('codex-mensagens'),{childList:true,subtree:true});
  new MutationObserver(composerState).observe($('codex-conversa'),{childList:true});
  window.addEventListener('mesa-contexto-alterado',() => {defaultDecided = false;composerState();});
  new MutationObserver(composerState).observe(form,{attributes:true,attributeFilter:['hidden'],subtree:true});
  new MutationObserver(feedbackState).observe($('observacoes-contagem'),{childList:true});
  $('codex-pergunta').addEventListener('input',() => {if (body) renderComposer();});
  desktop.addEventListener('change',activate);
  buildComposer();
  activate();
})();

// Phones: language, theme and sign-out move into the navigation drawer, leaving the
// header to the menu and the investigation selector.
(() => {
  const phone = matchMedia('(max-width:719px)');
  const header = document.querySelector('.app-header');
  const controls = ['mesa-idioma','mesa-sair','mesa-tema'].map(id => $(id));
  const drawer = element('div', undefined, 'mesa-drawer-controls');
  function place() {
    if (phone.matches) { drawer.append(...controls); $('mesa-sidebar').querySelector('.areas').after(drawer); }
    else { header.append(...controls); drawer.remove(); }
  }
  phone.addEventListener('change', place);
  place();
})();

'use strict';
// Presentation layer. Operational modules keep ownership of scope, writes and evidence.
(() => {
  // The sidebar has no icons (P11.6); only the drawer button keeps one.
  const icons = {menu:'M4 6h16M4 12h16M4 18h16'};
  // Sidebar labels (componentes.md#barra-lateral): shorter than the area headings in app.js, in the canvas order.
  const labels={inicio:'Visão geral',documentos:'Documentos',codex:'Perguntar',achados:'Conferir',quadros:'Quadros',apuracao:'Caderno',diligencias:'Pedidos e prazos'};
  // Counters beside the labels: only with real data, hidden at zero. forma = quantidade | pendencia | aviso.
  const contagens={};
  function aplicarBarra(){
    for(const [name,label] of Object.entries(labels)){
      const node=$('ver-'+name);if(!node)continue;
      if(!node.querySelector('.mesa-nav-rotulo'))node.replaceChildren(element('span',label,'mesa-nav-rotulo'),element('span',undefined,'mesa-nav-contador'));
      const contador=node.querySelector('.mesa-nav-contador'),dado=contagens[name];
      contador.hidden=!dado;contador.textContent=dado?dado.texto:'';
      if(dado)contador.dataset.forma=dado.forma;else delete contador.dataset.forma;
    }
  }
  window.barraMesa={aplicar:aplicarBarra,definir(nome,texto,forma='quantidade'){
    if(texto)contagens[nome]={texto,forma};else delete contagens[nome];
    aplicarBarra();
  }};
  let inventory=null, loadedCase=null, sequence=0, loading=false;
  const scopePanel=$('selecao-acervo');
  const svg=name=>{const s=document.createElementNS('http://www.w3.org/2000/svg','svg');s.setAttribute('viewBox','0 0 24 24');s.setAttribute('aria-hidden','true');s.classList.add('mesa-icon');const p=document.createElementNS(s.namespaceURI,'path');p.setAttribute('d',icons[name]||icons.documentos);s.append(p);return s;};
  const text=(id,value)=>{if($(id).textContent!==value)$(id).textContent=value;};
  const active=()=>new URL(location.href).searchParams.get('area')||'inicio';
  const current=()=>window.contextoCaso?.()||'';
  const navigate=name=>showArea(name);
  // Drawer (below 1280 px, docs/design/componentes.md#tablet): while it is open everything behind it is inert and Tab cycles inside it.
  const behindDrawer=()=>[document.querySelector('.skip-link'),$('mesa-ambiente'),document.querySelector('.app-header'),$('conteudo')].filter(Boolean);
  // Every visible focusable control inside the drawer, in document order: on phones language, theme and sign-out live there too.
  const drawerItems=()=>[...$('mesa-sidebar').querySelectorAll('a[href],button,input,select,textarea,summary,[tabindex]')]
    .filter(node=>!node.disabled&&node.getAttribute('tabindex')!=='-1'&&!node.closest('[hidden]'));
  function closeMenu(restoreFocus){
    const wasOpen=document.body.classList.contains('mesa-menu-open');
    document.body.classList.remove('mesa-menu-open');$('mesa-menu').setAttribute('aria-expanded','false');$('mesa-menu').setAttribute('aria-label','Abrir navegação');
    for(const node of behindDrawer())node.inert=false;
    window.camadaMesa?.fechada('menu');
    if(wasOpen&&restoreFocus===true)$('mesa-menu').focus();
  }
  function openMenu(){
    document.body.classList.add('mesa-menu-open');$('mesa-menu').setAttribute('aria-expanded','true');$('mesa-menu').setAttribute('aria-label','Fechar navegação');
    for(const node of behindDrawer())node.inert=true;
    // Back closes the drawer (Android); focus moves into it for keyboard and screen readers.
    window.camadaMesa?.abrir('menu',()=>{closeMenu();$('mesa-menu').focus();return true;});
    $('mesa-sidebar').querySelector('.areas button:not([hidden]),.areas a:not([hidden])')?.focus();
  }
  function navigation(){
    aplicarBarra();
    for(const name of Object.keys(labels)){
      const node=$('ver-'+name);if(!node)continue;
      const selected=active()===name||name==='apuracao'&&active()==='caderno';
      // aria-pressed remains owned by legacy buttons; anchors use aria-current.
      if(node.tagName==='A'){if(selected)node.setAttribute('aria-current','page');else node.removeAttribute('aria-current');}
      else node.setAttribute('aria-pressed',String(selected));
    }
    document.querySelectorAll('a[data-mesa-area]').forEach(a=>a.href=window.enderecoAreaMesa(a.dataset.mesaArea));
  }
  function tab(){
    const search=$('documentos-aba').value==='pesquisa';
    $('mesa-acervo').hidden=search;$('mesa-pesquisa').hidden=!search;
    $('mesa-aba-acervo').setAttribute('aria-pressed',String(!search));$('mesa-aba-pesquisa').setAttribute('aria-pressed',String(search));
    if(active()==='documentos'){if(scopePanel.parentElement!==$('mesa-pesquisa'))$('mesa-pesquisa').prepend(scopePanel);scopePanel.hidden=!search;}
    else if(scopePanel.parentElement===$('mesa-pesquisa')){$('area-documentos').before(scopePanel);scopePanel.hidden=active()!=='achados';}
  }
  function chooseTab(value){$('documentos-aba').value=value;$('documentos-aba').dispatchEvent(new Event('change'));tab();}
  // First run: with an empty catalog there is nothing to continue, only one first step.
  function firstRun(){
    const empty=catalogLoaded&&!cases.length;
    $('mesa-continuar').hidden=empty;$('inicio-trocar').hidden=empty;
    text('mesa-primeiro-titulo',empty?'Comece sua primeira apuração':'Nova apuração');
    text('mesa-primeiro-texto',empty?'Dê um nome à pauta e envie os arquivos. Cada um recebe um recibo, e você já pode perguntar à IA sobre eles.'
      :'Cadastre os documentos da pauta, pergunte à IA e confira cada achado na página do original.');
  }
  function home(){
    firstRun();
    const target=$('mesa-retomada'),caseData=cases.find(c=>c.id===current());target.replaceChildren();
    if(!caseData){target.append(element('h3','Escolha sua próxima história.'),element('p','Selecione uma apuração no topo da mesa para retomar seu trabalho.'));return;}
    const info=element('div'),next=element('div',undefined,'mesa-resume-next');
    info.append(element('p','APURAÇÃO SELECIONADA','eyebrow'),element('h3',caseData.titulo));
    const counts=[inventory?Leitura.quantidade(inventory.total_documentos,'documento'):'Documentos aguardando conferência',Leitura.quantidade(caseData.rodadas.length,'análise')];
    info.append(element('p',counts.join(' · '),'small'));
    next.append(element('p','SUA PRÓXIMA AÇÃO','eyebrow'),element('p',caseData.rodadas.length?'Retome a conversa e confira as fontes antes de avançar.':'Confira o recebimento dos documentos e faça sua primeira pergunta.'));
    const button=element('button','Retomar trabalho →');button.type='button';button.addEventListener('click',()=>$('inicio-retomar').click());next.append(button);target.append(info,next);
    // Resume summary (continuidade.js): done and pending items, each linked to its area. Admin only.
    // Shown only when /api/integracao announces `continuidade_resumo` (Continuidade.disponivel).
    if(window.Continuidade?.disponivel&&window.Sessao.pode('continuidade-resumo')){
      const slot=element('div',undefined,'mesa-resume-progress'),caso=caseData.id;target.append(slot);
      window.Continuidade.disponivel().then(ok=>{if(!ok){slot.remove();return;}if(slot.isConnected&&current()===caso)window.Continuidade.montar(slot,caso);});
    }
  }
  function formatBytes(n){if(!Number.isFinite(n))return '';return new Intl.NumberFormat('pt-BR',{maximumFractionDigits:1}).format(n>=1048576?n/1048576:n/1024)+(n>=1048576?' MB':' KB');}
  function documentTable(){
    const target=$('mesa-acervo-lista');target.replaceChildren();text('docs-contagem','');
    if(!inventory){const empty=element('div',undefined,'empty');empty.append(element('h2',current()?'O acervo ainda não está disponível.':'Escolha uma apuração para ver seus documentos.'),element('p',current()?'Use Atualizar acervo para tentar novamente.':'Você também pode começar uma nova apuração e cadastrar seu primeiro lote.'));target.append(empty);return;}
    const list=window.Documentos.lista(target,inventory,{consulta:$('mesa-filtrar-documento').value,limitacoes:$('mesa-filtrar-leitura').value==='limitacoes',abrir:openDocument});
    text('docs-contagem',Leitura.quantidade(inventory.documentos.length,'documento'));
  }
  async function openDocument(doc,button){
    const caseId=current(),ticket=sequence;button.disabled=true;$('mesa-acervo-erro').hidden=true;
    try{
      const bundle=await api('caderno-documentos',{caso:caseId});if(ticket!==sequence||caseId!==current())return;
      const found=bundle.documentos.find(d=>d.documento_id===doc.id&&d.sha256===doc.sha256);
      if(!found)throw new Error('O conjunto de documentos mudou. Atualize o acervo antes de abrir o original.');
      const blob=await api('caderno-original',{caso:caseId,origem_id:bundle.origem_id,documento_id:doc.id,documento_sha256:doc.sha256},true);
      if(ticket===sequence&&caseId===current())await window.abrirOriginal(blob,doc.nome_recebido);
    }catch(error){if(ticket===sequence){$('mesa-acervo-erro').textContent=error.message;$('mesa-acervo-erro').hidden=false;}}
    finally{button.disabled=false;}
  }
  async function loadInventory(force=false){
    // The guest has no access to the inventory (403): ask nothing and leave the header as it is.
    if(!window.Sessao.pode('inventario')){window.barraMesa.definir('documentos','');return;}
    const caseId=current();if(!force&&loadedCase===caseId)return;
    if(loadedCase!==caseId){$('documentos-recibo').hidden=true;$('documentos-recibo').replaceChildren();$('codex-recibo-alerta').hidden=true;}   // o recibo é de uma apuração só
    const ticket=++sequence;loadedCase=caseId;inventory=null;loading=!!caseId;$('mesa-acervo-erro').hidden=true;window.barraMesa.definir('documentos','');
    $('mesa-atualizar-acervo').disabled=loading;
    $('mesa-filtrar-documento').value='';$('mesa-filtrar-leitura').value='todos';documentTable();home();
    window.PreparoDePdf.atualizar(null);window.FontesWeb?.mostrar(null);
    if(!caseId){text('mesa-acervo-status','Selecione a apuração no topo da mesa.');text('mesa-versao','Documentos, achados e fontes');return;}
    text('mesa-acervo-status','Conferindo os documentos cadastrados…');text('mesa-versao','Conferindo acervo…');
    try{
      const result=await api('inventario',{caso:caseId});if(ticket!==sequence||caseId!==current())return;
      inventory=result;documentTable();home();window.PreparoDePdf.atualizar(result);window.FontesWeb?.mostrar(result);window.barraMesa.definir('documentos',result.total_documentos?String(result.total_documentos):'');text('mesa-versao',`Versão dos documentos: ${result.corpus_id}`);text('mesa-acervo-status','Os originais estão preservados; a extração não substitui a conferência.');
    }catch(error){if(ticket===sequence){$('mesa-acervo-erro').textContent=error.message;$('mesa-acervo-erro').hidden=false;text('mesa-acervo-status','A conferência do acervo falhou. Isso não equivale a um acervo vazio.');text('mesa-versao','Acervo indisponível');}}
    finally{if(ticket===sequence){loading=false;$('mesa-atualizar-acervo').disabled=false;}}
  }
  // "Pedidos e prazos": open requests whose deadline is today or has passed (same rule as "hoje" and "vencida" on the Diligências screen).
  let deadlineTicket=0;
  async function countDeadlines(){
    const caseId=current();
    if(!caseId||!window.Sessao.pode('diligencias-listar')){deadlineTicket++;window.barraMesa.definir('diligencias','','aviso');return;}
    const ticket=++deadlineTicket;
    try{
      const result=await api('diligencias-listar',{caso:caseId});
      if(ticket!==deadlineTicket||caseId!==current())return;
      const today=new Date(),limit=[today.getFullYear(),String(today.getMonth()+1).padStart(2,'0'),String(today.getDate()).padStart(2,'0')].join('-');
      const n=result.resultados.filter(({diligencia:d})=>d?.prazo&&!['concluida','cancelada'].includes(d.estado)&&d.prazo<=limit).length;
      window.barraMesa.definir('diligencias',n?(n===1?'1 vence':`${n} vencem`):'','aviso');
    }catch(_){if(ticket===deadlineTicket)window.barraMesa.definir('diligencias','','aviso');}
  }
  // Month's quota card (GET /api/cota, in reais): this account's spend against its ceiling. Without the endpoint or a session there is no card.
  let quotaAt=0;
  async function loadQuota(force=false){
    if(!force&&Date.now()-quotaAt<30000)return;quotaAt=Date.now();
    const card=$('mesa-cota');
    try{
      const res=await window.fetch?.('/api/cota');if(!res?.ok)throw new Error('sem cota');
      const data=await res.json(),account=data?.conta;if(!account)throw new Error('sem cota');
      // Administrators also get the installation's quota: the card shows the tighter of the two (smaller balance), so it never shows a
      // balance that the installation's ceiling has already taken away. A guest only gets its own account.
      const org=data.organizacao,block=org&&Number(org.saldo_brl)<Number(account.saldo_brl)?org:account,scope=block===org?'instalação':'';
      const used=Number(block.gasto_brl),cap=Number(block.teto_brl);if(!Number.isFinite(used)||!Number.isFinite(cap)||cap<=0)throw new Error('sem cota');
      const money=(value,full)=>new Intl.NumberFormat('pt-BR',{minimumFractionDigits:full?2:0,maximumFractionDigits:2}).format(value);
      const pct=Math.min(100,Math.round(used/cap*100));
      const value=`R$ ${money(used,true)} de R$ ${money(cap,!Number.isInteger(cap))}`,spent=Boolean(block.esgotada);
      // Used up is never shown by colour alone (W11, rules 6 and 7): the label changes, a "!" comes first and the aria-label says it.
      $('mesa-cota-rotulo').textContent=scope?(spent?'Cota da instalação esgotada':'Cota da instalação'):(spent?'Cota esgotada':'Cota do mês');
      $('mesa-cota-valor').textContent=value;
      $('mesa-cota-medidor').style.setProperty('--uso',(spent?100:pct)+'%');
      $('mesa-cota-medidor').setAttribute('aria-label',scope?(spent?`Cota da instalação esgotada: ${value}`:`${pct}% da cota da instalação usada`):(spent?`Cota do mês esgotada: ${value}`:`${pct}% da cota usada`));
      // P40 (b): o gasto com a chave de IA própria da redação, em linha separada: não entra na cota do serviço acima. A pessoa vê o que pagou por ela; o dono vê também o da redação.
      const chave=data.chave_propria,reais=raw=>{const n=Number(raw);return raw!=null&&Number.isFinite(n)?`R$ ${money(n,true)}`:'';};
      // O que a chave própria da redação pagou já está no valor da cota da pessoa: é parte ("dos quais R$ 3,25 com a chave própria"), não acréscimo. Aparece com o gasto mandado
      // pelo servidor (R$ 0,00 se a redação tem chave e ainda não houve gasto) e some sem chave própria; o dono vê também o total da redação, que não entra na cota do serviço.
      // O servidor só manda `chave_propria` no piloto e com chave salva ou gasto no mês (GET /api/cota, Viga b03a919): sem o campo, nenhuma das duas linhas.
      const dela=reais(chave?.conta_brl),inteira=reais(chave?.organizacao_brl),mostraParte=!scope&&!!dela;
      $('mesa-cota-chave').textContent=mostraParte?`dos quais ${dela} com a chave própria`:'';$('mesa-cota-chave').hidden=!mostraParte;
      $('mesa-cota-chave-redacao-valor').textContent=inteira;$('mesa-cota-chave-redacao').hidden=!inteira;
      if(mostraParte)$('mesa-cota-medidor').setAttribute('aria-label',`${$('mesa-cota-medidor').getAttribute('aria-label')}, dos quais ${dela} com a chave própria`);
      card.dataset.esgotada=String(spent);card.hidden=false;
    }catch(_){card.hidden=true;}
  }
  window.recarregarAcervo=force=>loadInventory(force);window.definirEstadoAcervo=mensagem=>text('mesa-acervo-status',mensagem);
  window.atualizarCotaBarra=force=>loadQuota(force);   // codex.js chama ao terminar cada pergunta
  loadQuota(true);
  window.addEventListener('focus',()=>loadQuota());
  // Profile in the sidebar footer: name and role from the session; it opens Configurações (shown only when piloto.js allows it).
  const ROLES={admin:'Administrador',dono:'Dono',editor:'Editor',reporter:'Repórter',leitor:'Leitor',convidado:'Convidado'};
  Promise.resolve(window.fetch?.('/api/sessao')).then(res=>res?.ok?res.json():null).then(data=>{
    const account=data?.conta;if(!account?.nome)return;
    const name=String(account.nome).trim(),initials=name.split(/\s+/).filter(Boolean).slice(0,2).map(part=>part[0].toUpperCase()).join('');
    const button=$('ver-configuracoes');
    button.querySelector('.mesa-avatar').textContent=initials;button.querySelector('.mesa-perfil-nome').textContent=name;
    button.querySelector('.mesa-perfil-papel').textContent=ROLES[account.papel]||account.papel||'';
  }).catch(()=>{});
  function sync(){
    const area=active();
    document.body.dataset.mesaArea=area;navigation();tab();
    const stages=[['documentos','Documentos'],['codex','Pergunta'],['achados','Conferência'],['apuracao','Caderno']],stage={documentos:0,codex:1,achados:2,apuracao:3,caderno:3}[area];
    // Guests only ask questions; every other step is closed to them.
    $('mesa-etapas').hidden=stage===undefined||document.body.dataset.papel==='convidado';
    if(stage!==undefined&&$('mesa-etapas').dataset.stage!==String(stage)){$('mesa-etapas').dataset.stage=String(stage);$('mesa-etapas').replaceChildren(...stages.map(([name,label],i)=>{const a=element('a');a.href=window.enderecoAreaMesa(name);a.dataset.mesaArea=name;a.append(element('span',String(i+1)),document.createTextNode(label));if(i===stage)a.setAttribute('aria-current','step');return a;}));}
    closeMenu(true);loadInventory();countDeadlines();loadQuota();
  }
  $('mesa-menu').replaceChildren(svg('menu'));
  $('mesa-menu').addEventListener('click',()=>{if(document.body.classList.contains('mesa-menu-open'))closeMenu();else openMenu();});
  document.addEventListener('keydown',event=>{
    if(!document.body.classList.contains('mesa-menu-open'))return;
    if(event.key==='Escape'){closeMenu(true);return;}
    if(event.key!=='Tab')return;
    // Focus stays in the drawer: Tab on the last item goes to the first, Shift+Tab on the first to the last.
    const items=drawerItems(),first=items[0],last=items[items.length-1],current=document.activeElement;
    if(!first)return;
    if(!items.includes(current)){event.preventDefault();first.focus();}
    else if(event.shiftKey&&current===first){event.preventDefault();last.focus();}
    else if(!event.shiftKey&&current===last){event.preventDefault();first.focus();}
  });
  // Widening the window past 1280 px turns the drawer back into the fixed bar: nothing may stay inert.
  matchMedia('(min-width:1280px)').addEventListener?.('change',event=>{if(event.matches)closeMenu();});
  document.addEventListener('click',event=>{
    const link=event.target.closest('a[data-mesa-area]');
    if(link&&!event.ctrlKey&&!event.metaKey&&!event.shiftKey&&!event.altKey&&event.button===0){event.preventDefault();navigate(link.dataset.mesaArea);}
    if(document.body.classList.contains('mesa-menu-open')&&!event.target.closest('.sidebar,#mesa-menu'))closeMenu(true);
  });
  // "Trocar de apuração" opens the list of investigations (and the trash), which left the sidebar.
  $('inicio-trocar').addEventListener('click',()=>navigate('gerenciar'));
  // Área de envio de Documentos (W02): envia para a apuração escolhida. Sem o envio em fluxo no servidor, o caminho é a tela de Nova apuração.
  if(document.body.dataset.papel==='convidado')$('documentos-zona').hidden=true;
  else window.Documentos.zona($('documentos-zona'),{aoEscolher:files=>{
    // Passo 2 da Nova apuração: o primeiro envio cria a apuração (cadastrar com novo: true, sem caso) e a tela passa a ela.
    if(window.NovaApuracao.ativa()){window.NovaApuracao.enviar(files,{aoConcluir:async()=>{await loadInventory(true);text('mesa-acervo-status','Documentos registrados. Aguardando sua pergunta.');},
      depoisDeCriar:async()=>{await loadInventory(true);}});return;}
    if(!current()){$('contexto-caso').focus();text('mesa-acervo-status','Escolha uma apuração para enviar documentos.');return;}
    window.Documentos.enviar(files,{caso:current(),alvo:$('documentos-envio'),alvoRecibo:$('documentos-recibo'),
      aoConcluir:async()=>{await loadInventory(true);if(typeof loadCatalog==='function')await loadCatalog();text('mesa-acervo-status','Documentos registrados. Aguardando sua pergunta.');},
      aoIndisponivel:async files=>{
        // Sem o envio em fluxo no servidor, a própria Documentos envia em JSON (um lote de até 50 MB) para a apuração escolhida (F3 da Coruja).
        const caso=current(),resultado=await window.EnvioJson.enviar(files,{escopo:{novo:false,caso}});
        if(!resultado)return;
        window.Envio.renderRecibo($('documentos-recibo'),resultado);
        await loadInventory(true);if(typeof loadCatalog==='function')await loadCatalog();
        text('mesa-acervo-status','Documentos registrados. Aguardando sua pergunta.');}});
  }});
  // O recibo do último envio desta visita acompanha a pergunta, recolhido acima da caixa; sem envio, a Pergunta abre sem ele.
  function reciboJuntoDaPergunta(){
    const alerta=$('codex-recibo-alerta'),recibo=$('documentos-recibo');
    if(!recibo||recibo.hidden||!recibo.childNodes.length){alerta.hidden=true;alerta.replaceChildren();return;}
    const copia=recibo.cloneNode(true);copia.hidden=false;copia.removeAttribute('tabindex');copia.removeAttribute('id');
    for(const filho of copia.querySelectorAll('[id]'))filho.removeAttribute('id');
    alerta.replaceChildren(element('summary','Recibo do último envio · confira as limitações antes de perguntar'),copia);
    alerta.open=false;alerta.hidden=false;
  }
  $('mesa-perguntar').addEventListener('click',()=>{if(!current()){$('contexto-caso').focus();return;}reciboJuntoDaPergunta();navigate('codex');window.abrirComposicaoMesa?.();});
  $('mesa-aba-acervo').addEventListener('click',()=>chooseTab('acervo'));
  $('mesa-aba-pesquisa').addEventListener('click',()=>chooseTab('pesquisa'));
  $('documentos-aba').addEventListener('change',tab);
  $('mesa-filtrar-documento').addEventListener('input',documentTable);$('mesa-filtrar-leitura').addEventListener('change',documentTable);
  $('mesa-atualizar-acervo').addEventListener('click',()=>loadInventory(true));
  window.addEventListener('mesa-rota-alterada',sync);
  window.addEventListener('catalogo-carregado',()=>{home();sync();});
  window.addEventListener('acervo-alterado',()=>{loadedCase=null;if(['inicio','documentos'].includes(active()))loadInventory(true);});
  $('contexto-caso').addEventListener('change',()=>{loadedCase=null;loadInventory();});
  const preview=$('apuracao-previa'),previewHeading=preview.previousElementSibling;
  const previewDetails=element('details',undefined,'mesa-note-preview');
  previewDetails.append(element('summary','Pré-visualizar a redação'));previewHeading.replaceWith(previewDetails);previewDetails.append(preview);
  const notebookActions=$('apuracao-nova').parentElement;
  notebookActions.append($('apuracao-atualizar'));
  const diligenceHeading=element('div',undefined,'section-heading');
  $('diligencias-titulo').before(diligenceHeading);diligenceHeading.append($('diligencias-titulo'),$('diligencias-nova'));
  const diligenceFilters=element('details',undefined,'mesa-diligence-options');
  diligenceFilters.id='mesa-diligencias-filtros';diligenceFilters.append(element('summary','Filtrar diligências'));
  $('diligencias-filtros').before(diligenceFilters);diligenceFilters.append($('diligencias-filtros'));
  const diligenceResume=element('details',undefined,'mesa-diligence-options');
  diligenceResume.id='mesa-diligencias-retomada';diligenceResume.append(element('summary','Conversa e documentos para retomar a questão'));
  const resumeLabel=$('diligencias-conversa').closest('label');resumeLabel.before(diligenceResume);diligenceResume.append(resumeLabel,$('diligencias-incorporar').closest('label'));
  let hadSources=false;
  new MutationObserver(()=>{const hasSources=!!$('codex-fontes').children.length;if(hasSources&&!hadSources&&matchMedia('(min-width:1024px)').matches)$('codex-painel-fontes').open=true;hadSources=hasSources;}).observe($('codex-fontes'),{childList:true});
  // Refresh the adopted navigation nodes after desktop.js restores them on resize.
  matchMedia('(min-width:1024px)').addEventListener('change',navigation);
  for(const field of document.querySelectorAll('input[id],textarea[id],select[id]')){if(!field.name)field.name=field.id;if(!field.hasAttribute('autocomplete')&&['text','search'].includes(field.type))field.autocomplete='off';}
  const params=new URL(location.href).searchParams;if(!params.has('documentos-aba')&&['consulta','geracao','rodada'].some(k=>params.has(k)))$('documentos-aba').value='pesquisa';
  sync();
})();

// Keyboard shortcuts. Ctrl/Cmd+Enter sends the question; J and K (or Alt+↓ and Alt+↑) move
// between findings. Both are listed under "Como começar" in the sidebar.
(() => {
  const announce = message => { $('codex-anuncio').textContent = window.I18N.t(message); };
  $('codex-pergunta').addEventListener('keydown', event => {
    if (event.key !== 'Enter' || !(event.ctrlKey || event.metaKey) || event.altKey || event.shiftKey || event.isComposing) return;
    event.preventDefault();
    // The button carries every reason sending may be blocked: no case, a run in progress, lost tracking.
    if ($('codex-enviar').disabled) { announce('O envio não está disponível agora.'); return; }
    if (!$('codex-pergunta').value.trim()) { announce('Escreva a pergunta antes de enviar.'); return; }
    announce('Pergunta enviada.');
    $('codex-form').requestSubmit();
  });

  const typing = target => Boolean(target?.closest?.('input,textarea,select,[contenteditable="true"],.vditor'));
  function findingStep(event) {
    if (event.ctrlKey || event.metaKey || event.shiftKey) return 0;
    if (event.altKey) return event.key === 'ArrowDown' ? 1 : event.key === 'ArrowUp' ? -1 : 0;
    return event.key === 'j' ? 1 : event.key === 'k' ? -1 : 0;
  }
  document.addEventListener('keydown', event => {
    const step = findingStep(event);
    if (!step || event.defaultPrevented || event.isComposing || typing(event.target)) return;
    if ($('area-achados').hidden || $('mesa-achados').hidden || document.querySelector('dialog[open]')) return;
    const findings = [...$('achados-resultados').querySelectorAll('.finding-open')];
    if (!findings.length) return;
    const current = findings.findIndex(button => button.getAttribute('aria-pressed') === 'true');
    const next = Math.min(findings.length - 1, Math.max(0, current + step));
    event.preventDefault();
    if (next === current) return;
    // The button's own handler opens the finding and moves focus to its heading.
    findings[next].click();
    findings[next].scrollIntoView({block: 'nearest'});
  });
})();

// Faixa que rola para o lado (docs/design/componentes.md#faixa-que-rola, Q5): a linha de etapas, as pílulas dos quadros e as abas do Caderno, de Documentos e de Minha conta, quando passam da largura. Só a faixa rola (scrollLeft,
// nunca a página), sem animação, até o item ativo caber inteiro com a folga de --espaco-4; `data-rola` (fim, inicio, ambos) diz de que lado ainda há conteúdo e o CSS esmaece
// esse lado; sem estouro, sem atributo. O item ativo é o que a faixa já marca (aria-current, aria-selected ou aria-pressed): ela é observada, então quem a desenha ou troca o item não muda.
(() => {
  const ativo = '[aria-current],[aria-selected="true"],[aria-pressed="true"]';
  const faixas = new WeakSet();
  const folgaDe = faixa => { const valor = parseFloat(getComputedStyle(faixa).getPropertyValue('--espaco-4')); return Number.isFinite(valor) ? valor : 16; };
  function marcar(faixa) {
    const resto = faixa.scrollWidth - faixa.clientWidth, esq = faixa.scrollLeft;
    const lado = resto <= 1 ? '' : esq <= 1 ? 'fim' : esq >= resto - 1 ? 'inicio' : 'ambos';
    if (lado) { if (faixa.dataset.rola !== lado) faixa.dataset.rola = lado; } else if (faixa.hasAttribute('data-rola')) faixa.removeAttribute('data-rola');
  }
  function trazerOAtivo(faixa) {
    const item = faixa.querySelector(ativo);
    if (item && faixa.clientWidth > 0 && faixa.scrollWidth > faixa.clientWidth) {
      const dentro = faixa.getBoundingClientRect(), caixa = item.getBoundingClientRect(), folga = folgaDe(faixa);
      if (caixa.left < dentro.left + folga) faixa.scrollLeft += caixa.left - dentro.left - folga;
      else if (caixa.right > dentro.right - folga) faixa.scrollLeft += caixa.right - dentro.right + folga;
    }
    marcar(faixa);
  }
  function observar(faixa) {
    if (!faixa || faixas.has(faixa)) return;
    faixas.add(faixa);
    let largura = 0;
    faixa.addEventListener('scroll', () => marcar(faixa), {passive: true});
    if (typeof MutationObserver === 'function') new MutationObserver(() => trazerOAtivo(faixa)).observe(faixa, {childList: true, subtree: true, attributes: true, attributeFilter: ['aria-current', 'aria-selected', 'aria-pressed']});
    // Ao aparecer (a área estava escondida) ou ao mudar de largura a faixa recalcula; só ao aparecer ela traz o ativo de novo.
    if (typeof ResizeObserver === 'function') new ResizeObserver(() => { const apareceu = largura === 0; largura = faixa.clientWidth; if (apareceu) trazerOAtivo(faixa); else marcar(faixa); }).observe(faixa);
    trazerOAtivo(faixa);
  }
  const SELETOR = '#mesa-etapas,.quadros-abas,.mesa-tabs,.notebook-tabs';
  document.querySelectorAll(SELETOR).forEach(observar);
  // As abas de Minha conta nascem depois (conta.js): quem entra na página com a classe das abas também é observado.
  if (typeof MutationObserver === 'function' && document.body) {
    new MutationObserver(registros => registros.forEach(r => r.addedNodes.forEach(no => {
      if (no.nodeType !== 1) return;
      if (no.matches(SELETOR)) observar(no);
      no.querySelectorAll?.(SELETOR).forEach(observar);
    }))).observe(document.body, {childList: true, subtree: true});
  }
})();
