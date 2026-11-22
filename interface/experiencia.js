'use strict';
// Shared editorial context. Internal selectors remain as adapters for each module.
(() => {
  const caseSelects = ['caso','codex-caso','apuracao-caso','caderno-caso','diligencias-caso','gerenciar-caso'];
  const routeIds = ['documentos-aba','rodada','geracao','achados-revisao','achados-geracao','codex-conversa','consulta','modo','documento','pagina','limite',
    'achados-texto','achados-documento','achados-natureza','achados-suporte','achados-humana','achados-destino','achados-briefing','achados-marcacao','achados-limite',
    'caderno-texto','diligencias-texto','diligencias-estado-filtro','diligencias-responsavel-filtro'];
  let current = '', area = 'inicio', restoring = false, revision = 0;
  const desktop = matchMedia('(min-width:1024px)');
  // Guests work only in "Ask the AI"; the server enforces access, this keeps the screen honest.
  const guest = document.body.dataset.papel === 'convidado';
  window.limitarNavegacaoConvidado = () => {
    if (!guest) return;
    for (const item of document.querySelector('.areas').children) {
      if (['A','BUTTON'].includes(item.tagName) && item.id !== 'ver-codex') item.hidden = true;
    }
  };
  window.limitarNavegacaoConvidado();
  const pageOffsets = {documentos:0, achados:0, caderno:0};
  let restoredOffset = 0;
  window.restaurandoMesa = () => desktop.matches && restoring;
  window.restaurandoRota = () => restoring;
  window.paginaRestauradaMesa = name => desktop.matches && restoring && area === name ? restoredOffset : 0;
  window.registrarPaginaMesa = (name, offset) => {
    if (!desktop.matches) return;
    pageOffsets[name] = offset;
    writeRoute();
    window.dispatchEvent(new CustomEvent('mesa-consulta', {detail:{area:name}}));
  };
  const defaults = Object.fromEntries(routeIds.map(id=>[id,$(id).value]));
  // Visible notices explain a refusal; a case switch is only announced, since the heading shows it.
  const notice = (message, visible = true) => {
    $('experiencia-status').classList.toggle('sr-only', !visible);
    $('experiencia-status').textContent = message;
  };
  window.contextoCaso = () => current;
  function adapt(id, value) {
    const select = $(id);
    if (value && ![...select.options].some(o => o.value === value)) {
      select.append(new Option(cases.find(c => c.id === value)?.titulo || value, value));
    }
    select.value = value;
  }
  function canSwitch(value) {
    if(cadastroBusy){notice('Aguarde o recibo deste envio antes de trocar de apuração.');return false;}
    if (window.estadoConversa?.().ocupada) {
      notice('Aguarde a execução ou reconecte o acompanhamento antes de trocar de apuração.'); return false;
    }
    return window.prepararTrocaApuracao?.(() => window.definirContextoCaso(value, {force:true})) !== false;
  }
  window.definirContextoCaso = (value, {force = false} = {}) => {
    if (value === current) return true;
    if (!force && !canSwitch(value)) return false;
    current = value;
    for (const name of Object.keys(pageOffsets)) pageOffsets[name] = 0;
    adapt('contexto-caso', value);
    for (const id of caseSelects) {
      if ($(id).value !== value) { adapt(id,value); $(id).dispatchEvent(new Event('change')); }
    }
    // Upload destination follows the desk; starting a new case is always explicit.
    adapt('cadastro-caso', value); toggleNewCase();
    try { localStorage.setItem('mesa-apuracao', value); } catch {}
    notice(value ? `Apuração: ${cases.find(c => c.id === value)?.titulo || value}.` : 'Escolha uma apuração ou comece uma nova.', false);
    window.dispatchEvent(new Event('mesa-contexto-alterado'));
    writeRoute(); return true;
  };
  $('contexto-caso').addEventListener('change', () => {
    const value = $('contexto-caso').value;
    if (!window.definirContextoCaso(value)) $('contexto-caso').value = current;
  });
  for (const id of caseSelects) {
    $(id).closest('label')?.classList.add('context-adapter');
    $(id).addEventListener('change', () => {
      // Programmatic navigation to a cited case must also update the shared context.
      if ($(id).value !== current) window.definirContextoCaso($(id).value);
    });
  }
  function routeFor(target = area) {
    const url = new URL(location.href); url.search = '';
    if (desktop.matches) url.hash = '';
    url.searchParams.set('area',target);
    if (current) url.searchParams.set('caso',current);
    for (const id of routeIds) {
      const relevant = id.startsWith('achados-') ? target === 'achados'
        : id.startsWith('codex-') ? target === 'codex'
        : id.startsWith('caderno-') ? target === 'caderno'
        : id.startsWith('diligencias-') ? target === 'diligencias'
        : ['rodada','geracao'].includes(id) ? ['documentos','achados'].includes(target) : target === 'documentos';
      if (relevant && $(id).value) url.searchParams.set(id,$(id).value);
    }
    if (desktop.matches && pageOffsets[target]) url.searchParams.set('deslocamento',pageOffsets[target]);
    return url;
  }
  window.enderecoAreaMesa = routeFor;
  // Back button. Each area is one history entry; an open overlay (dialog, navigation menu,
  // finding detail on a narrow screen) adds one entry at the same address, so the Android or
  // browser Back closes the overlay before leaving the area. `renderedHref` is the address the
  // screen shows: a pop that lands on it only closes overlays and never reloads the area.
  const layers = [];
  let layerSeq = 0, skipPops = 0, skipTimer = null, renderedHref = location.href;
  // After a reload no overlay is open: an overlay entry left in history is cleared.
  if (history.state?.vladoCamada) {
    try { const {vladoCamada, ...rest} = history.state; history.replaceState(rest, '', location.href); } catch { /* History unavailable. */ }
  }
  const layerOnTop = () => Number(history.state?.vladoCamada) || 0;
  function pushLayerEntry(seq, href = location.href) {
    try { history.pushState({...(history.state || {}), vladoCamada: seq}, '', href); } catch { /* History may be unavailable (sandbox). */ }
  }
  window.camadaMesa = {
    abrir(id, fechar) {
      if (layers.some(layer => layer.id === id)) return;
      const seq = ++layerSeq;
      layers.push({id, seq, fechar});
      pushLayerEntry(seq);
    },
    // Closed from the interface (button, Escape, save): drop its history entry if it is the current one.
    fechada(id) {
      const index = layers.findIndex(layer => layer.id === id);
      if (index < 0) return;
      const [layer] = layers.splice(index, 1);
      if (layerOnTop() === layer.seq && typeof history.back === 'function') {
        skipPops++; history.back();
        // If there was nothing to go back to, no popstate comes: do not swallow a later Back.
        clearTimeout(skipTimer); skipTimer = setTimeout(() => { skipPops = 0; }, 800);
      }
    },
    abertas: () => layers.map(layer => layer.id),
  };
  function closeLayersAbove(seq) {
    while (layers.length && layers.at(-1).seq > seq) {
      const layer = layers.pop();
      // An overlay may refuse (unsaved text kept by the user): it stays open with its entry back.
      if (layer.fechar() === false) { layers.push(layer); pushLayerEntry(layer.seq, renderedHref); return false; }
    }
    return true;
  }
  function writeRoute(replace = false) {
    if (restoring) return;
    const url = routeFor();
    // Navigating from an overlay entry replaces it, so Back does not stop at a closed menu.
    if (url.href !== location.href) history[replace || layerOnTop() ? 'replaceState' : 'pushState']({},'',url);
    renderedHref = location.href;
    window.dispatchEvent(new Event('mesa-rota-alterada'));
  }
  registrarGanchoArea({
    antes: name => {
      if (!$('area-' + name)) name = 'inicio';
      if (guest) name = 'codex';
      area = name;
      return name;
    },
    depois: name => {
      area = name;  // o nome já passou pelos ganchos de forçar: rota e tela dizem o mesmo
      $('caderno-abas').hidden = !['apuracao','caderno'].includes(name);
      $('caderno-aba-notas').setAttribute('aria-pressed',String(name === 'apuracao'));
      $('caderno-aba-trechos').setAttribute('aria-pressed',String(name === 'caderno'));
      if (name === 'caderno') $('ver-apuracao').setAttribute('aria-pressed','true');
      $('area-titulo').tabIndex = -1; $('area-titulo').focus({preventScroll:true});
      writeRoute();
    }
  });
  $('caderno-aba-notas').addEventListener('click',()=>showArea('apuracao'));
  $('caderno-aba-trechos').addEventListener('click',()=>showArea('caderno'));
  $('achados-texto').closest('label').after($('achados-documento').closest('label'));
  $('inicio-nova').addEventListener('click',()=>{
    showArea('cadastro'); $('cadastro-caso').value=''; toggleNewCase(); $('cadastro-titulo-input').focus();
  });
  $('inicio-adicionar').addEventListener('click',()=>{showArea('cadastro');$('cadastro-arquivos').focus();});
  $('inicio-retomar').addEventListener('click',()=>{
    if (!current) { notice('Escolha a apuração que deseja retomar.'); $('contexto-caso').focus(); }
    else showArea('codex');
  });
  $('cadastro-perguntar').addEventListener('click',()=>{
    const caseId = $('cadastro-perguntar').dataset.caso;
    if (!window.definirContextoCaso(caseId)) return;
    $('codex-recibo-alerta').replaceChildren(element('summary','Recibo dos documentos enviados · confira as limitações antes de perguntar'),$('cadastro-recibo').cloneNode(true));
    // Avoid duplicated DOM IDs when preserving the receipt alongside the question.
    for (const child of $('codex-recibo-alerta').querySelectorAll('[id]')) child.removeAttribute('id');
    $('codex-recibo-alerta').hidden=false; showArea('codex'); window.abrirComposicaoMesa?.(); $('codex-pergunta').focus();
  });
  for (const id of routeIds) $(id).addEventListener('change',()=>writeRoute());
  for (const form of ['pesquisa','achados-form','caderno-pesquisa','diligencias-filtros']) $(form).addEventListener('submit',()=>writeRoute());
  async function waitFor(test) {
    const start = Date.now();
    while (!test()) { if (Date.now()-start > 8000) throw new Error('A seleção salva ainda não está disponível. Confira a versão antes de continuar.'); await new Promise(r=>setTimeout(r,40)); }
  }
  async function restore() {
    const ticket = ++revision, params = new URL(location.href).searchParams;
    restoring = true;
    try {
      const value = params.get('caso') || '';
      if (value && !cases.some(c=>c.id===value)) throw new Error('A apuração deste endereço não está disponível. Nenhuma outra foi selecionada.');
      if (!window.definirContextoCaso(value)) { restoring=false; writeRoute(true); return; }
      const target = params.get('area') || 'inicio';
      const offset = Number(params.get('deslocamento') || 0);
      restoredOffset = desktop.matches && Number.isSafeInteger(offset) && offset >= 0 ? offset : 0;
      showArea(target);
      for (const id of routeIds) {
        if (ticket !== revision) return;
        const value = params.get(id);
        if (value === null) {
          if (id === 'documentos-aba') {
            $(id).value = target === 'documentos' && ['consulta','rodada','geracao'].some(key=>params.has(key)) ? 'pesquisa' : defaults[id];
            $(id).dispatchEvent(new Event('change'));
            continue;
          }
          if (!['rodada','geracao','achados-revisao','achados-geracao','codex-conversa'].includes(id)) $(id).value = defaults[id];
          continue;
        }
        const select = $(id);
        if (desktop.matches && id === 'achados-documento') {
          if (value && ![...select.options].some(o=>o.value===value)) select.append(new Option(value,value));
        } else if (select.tagName === 'SELECT') await waitFor(()=>!select.disabled && [...select.options].some(o=>o.value===value));
        if (ticket !== revision) return;
        select.value=value; select.dispatchEvent(new Event('change'));
      }
      if (target==='documentos' && params.has('consulta')) {
        await waitFor(()=>!$('buscar').disabled); $('pesquisa').requestSubmit();
      }
      if (target==='achados' && params.has('achados-geracao')) {
        if (desktop.matches) await searchFindings({...findingScope(), filtros:findingFilters(), limite:Number($('achados-limite').value), deslocamento:restoredOffset});
        else {await waitFor(()=>!$('achados-buscar').disabled); $('achados-form').requestSubmit();}
      }
      if(target==='caderno' && (params.has('caderno-texto') || restoredOffset)) {
        await waitFor(()=>!$('caderno-buscar').disabled); $('caderno-pesquisa').requestSubmit();
      }
      if(target==='diligencias' && ['diligencias-texto','diligencias-estado-filtro','diligencias-responsavel-filtro'].some(id=>params.has(id))) {
        $('diligencias-filtros').requestSubmit();
      }
    } catch (failure) { notice(failure.message); }
    finally { if(ticket===revision) {restoring=false;if (desktop.matches) writeRoute(true); renderedHref=location.href;} }
  }
  // A guest invited to a single investigation lands with it selected; admins choose explicitly.
  function selectOnlyCase(params) {
    if (guest && !current && !params.get('caso') && cases.length === 1) window.definirContextoCaso(cases[0].id);
  }
  let initialized = false;
  window.addEventListener('catalogo-carregado',()=>{
    $('contexto-caso').replaceChildren(new Option('Escolha uma apuração',''),...cases.map(c=>new Option(c.titulo,c.id)));
    adapt('contexto-caso',current);
    const params = new URL(location.href).searchParams;
    if (!initialized) {
      initialized=true;
      if (!params.has('area') && !params.has('caso')) {
        let saved=''; try { saved=localStorage.getItem('mesa-apuracao') || ''; } catch {}
        if(cases.some(c=>c.id===saved)) window.definirContextoCaso(saved);
        showArea('inicio');
      } else restore();
      selectOnlyCase(params);
    } else {
      if(current && !cases.some(c=>c.id===current)) window.definirContextoCaso('',{force:true});
      selectOnlyCase(new URLSearchParams());
    }
  });
  window.addEventListener('popstate',()=>{
    if (skipPops) { skipPops--; return; }
    if (!closeLayersAbove(layerOnTop())) return;
    if (location.href === renderedHref) return;
    restore();
  });
  // Every dialog is an overlay for Back. Closing through Back goes through `cancel`, so the
  // unsaved-text confirmation below still applies.
  for (const dialog of document.querySelectorAll('dialog')) {
    const showModal = dialog.showModal.bind(dialog);
    dialog.showModal = () => {
      showModal();
      window.camadaMesa.abrir('dialogo:' + dialog.id, () => {
        if (!dialog.open) return true;
        const cancel = new Event('cancel', {cancelable: true});
        if (!dialog.dispatchEvent(cancel)) return false;
        dialog.close();
        return true;
      });
    };
    // `close` fires in a later task: a dialog reopened meanwhile keeps its layer.
    dialog.addEventListener('close', () => { if (!dialog.open) window.camadaMesa.fechada('dialogo:' + dialog.id); });
  }
  if (catalogLoaded) window.dispatchEvent(new Event('catalogo-carregado'));
  // In a narrow viewport the detail is a dedicated screen; the list position survives.
  const back=element('button','Voltar à lista de achados','secondary'); back.type='button';
  back.id='achados-voltar-lista'; $('achados-inspecao').before(back); back.hidden=true;
  let returnTo=null;
  function closeDetail(){
    if(!$('mesa-achados').classList.contains('detail-open'))return true;
    $('mesa-achados').classList.remove('detail-open');back.hidden=true;returnTo?.focus();
    return true;
  }
  $('achados-resultados').addEventListener('click',event=>{
    if(!event.target.closest('.finding-open') || !matchMedia('(max-width:1023px)').matches)return;
    returnTo=event.target.closest('.finding-open'); $('mesa-achados').classList.add('detail-open'); back.hidden=false;
    window.camadaMesa.abrir('achado',closeDetail);
    const heading=$('achados-inspecao').querySelector('h3'); if(heading){heading.tabIndex=-1;heading.focus();}
  });
  back.addEventListener('click',()=>{closeDetail();window.camadaMesa.fechada('achado');});
  // Discard checks cover close, Escape and page reload; saved programmatic closes remain allowed.
  for(const [dialogId,formIds]of [['revisao-dialogo',['revisao-form']],['caderno-dialogo',['caderno-form']],['diligencias-dialogo',['diligencias-form']],['diligencias-resposta-dialogo',['diligencias-upload','diligencias-resposta-form']]]) {
    const dialog=$(dialogId); let dirty=false;
    for(const formId of formIds) {
      $(formId).addEventListener('input',()=>{dirty=true;}); $(formId).addEventListener('change',()=>{dirty=true;});
    }
    const close=dialog.querySelector('.section-heading button');
    // The answer comes from the confirmation dialog, so a dirty form always cancels the event first and, once discarding is confirmed, closes.
    let discarding=false;
    const discard=finish=>{
      window.Dialogo.confirmar({variante:'destrutivo',titulo:'Descartar e fechar?',texto:'Há texto ou alterações não salvas.',acao:'Descartar e fechar'}).then(ok=>{
        if(!ok)return; discarding=true; try{finish();}finally{discarding=false;}
      });
    };
    close.addEventListener('click',event=>{if(dirty&&!discarding){event.preventDefault();event.stopImmediatePropagation();discard(()=>close.click());}},true);
    dialog.addEventListener('cancel',event=>{if(dirty&&!discarding){event.preventDefault();discard(()=>dialog.close());}},true);
    dialog.addEventListener('close',()=>{dirty=false;});
    window.addEventListener('beforeunload',event=>{if(dialog.open&&dirty){event.preventDefault();event.returnValue='';}});
    // Automatic draft of the form (continuidade.js). Closing saves or discards for real, so the
    // draft goes too; closing the page keeps it, and the next opening of the same item offers it.
    const forms=formIds.map(id=>$(id)), heading=dialog.querySelector('.section-heading');
    // The item on screen (finding under review, notebook scope, diligence origin) names the draft.
    const contexto=()=>String(dialog.querySelector('[id*="-afirmacao"],[id*="-escopo"],[id*="-origem"]')?.textContent||'').replace(/\s+/g,' ').trim().slice(0,500);
    const tela=()=>{const nome='quadro-'+dialogId.replace(/-dialogo$/,''),item=contexto();return item?`${nome}/${window.Rascunhos.idItem(item)}`:nome;};
    const rascunho=window.Rascunhos?.registrar({origem:dialog,ancora:heading||forms[0],
      alvo:()=>dialog.open&&window.contextoCaso?.()?{caso:window.contextoCaso(),tela:tela()}:null,
      ler:()=>({...window.Rascunhos.lerFormulario(forms),contexto:contexto()}),
      aplicar:conteudo=>window.Rascunhos.aplicarFormulario(forms,conteudo),
      compativel:conteudo=>conteudo.contexto===contexto()});
    if(rascunho){dialog.addEventListener('focusin',()=>{if(dialog.open)rascunho.abrir();});dialog.addEventListener('close',()=>rascunho.concluir());}
  }
})();

// Hosted environments that are not the newsroom carry a fixed banner. The local mode has no
// /api/sessao (404) and the editorial environment returns no banner: nothing is shown.
(() => {
  const banners = {homologacao:'Homologação — dados sintéticos', demonstracao:'Demonstração — dados sintéticos'};
  (async () => {
    try {
      const response = await fetch('/api/sessao', {headers:{Accept:'application/json'}, credentials:'same-origin'});
      if (!response.ok) return;
      const text = banners[(await response.json())?.ambiente];
      if (!text) return;
      const banner = $('mesa-ambiente');
      banner.textContent = text; banner.hidden = false;
      document.body.dataset.ambiente = Object.keys(banners).find(key => banners[key] === text);
      // The fixed banner may wrap (large text): the header and drawer start below its real height.
      const measure = () => document.documentElement.style.setProperty('--faixa-ambiente', `${Math.ceil(banner.getBoundingClientRect().height)}px`);
      measure();
      if (typeof ResizeObserver === 'function') new ResizeObserver(measure).observe(banner);
    } catch { /* No session endpoint or no network: the banner stays hidden. */ }
  })();
})();

// Virtual keyboard: a focused field scrolls back into the visible part of the screen when the
// keyboard (or the browser bar) shrinks the visual viewport. Desktop layouts are not affected.
(() => {
  const narrow = matchMedia('(max-width:1023px)');
  const typing = node => node?.matches?.('input:not([type=checkbox]):not([type=radio]):not([type=file]),textarea,select,[contenteditable="true"]');
  let timer = null;
  function keepVisible() {
    const field = document.activeElement;
    if (!narrow.matches || !typing(field)) return;
    const viewport = window.visualViewport, rect = field.getBoundingClientRect();
    const top = viewport ? viewport.offsetTop : 0, bottom = viewport ? viewport.offsetTop + viewport.height : window.innerHeight;
    if (rect.top < top + 8 || rect.bottom > bottom - 8) field.scrollIntoView({block:'center', inline:'nearest'});
  }
  const later = () => { clearTimeout(timer); timer = setTimeout(keepVisible, 250); };
  document.addEventListener('focusin', later);
  window.visualViewport?.addEventListener('resize', later);
  window.addEventListener('orientationchange', later);
})();

// PDF originals render with pdf.js (loaded on demand, like the notebook editor): mobile browsers
// and the Android WebView do not show a PDF inside an iframe. The cited page opens first.
const LeitorPdf = (() => {
  const BASE = '/vendor/pdfjs/legacy/build/';
  const ZOOMS = [0.5, 0.75, 1, 1.25, 1.5, 2, 3, 4];
  const MAX_PIXELS = 12e6; // canvas memory cap for phones
  let library = null;
  function load() {
    if (!library) library = import(BASE + 'pdf.min.mjs').then(lib => {
      lib.GlobalWorkerOptions.workerSrc = BASE + 'pdf.worker.min.mjs';
      return lib;
    }).catch(failure => { library = null; throw failure; });
    return library;
  }
  const fold = text => String(text || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLocaleLowerCase('pt-BR').replace(/\s+/g, ' ').trim();
  const button = (label, text, action) => {
    const node = element('button', text, 'secondary'); node.type = 'button';
    if (label) node.setAttribute('aria-label', label);
    node.addEventListener('click', action);
    return node;
  };
  // `current()` turns false when the dialog closed or another original replaced this one.
  async function open(container, blob, name, page, reference, current = () => true) {
    const stale = () => { throw Object.assign(new Error('Original substituído.'), {name: 'AbortError'}); };
    const lib = await load();
    if (!current()) stale();
    const data = new Uint8Array(await blob.arrayBuffer());
    if (!current()) stale();
    const task = lib.getDocument({data, isEvalSupported:false, enableXfa:false, disableAutoFetch:true});
    let doc;
    try { doc = await task.promise; }
    catch (failure) { task.destroy(); throw failure; }
    if (!current()) { task.destroy(); stale(); }
    const total = doc.numPages;
    const state = {page:Math.min(Math.max(1, Number(page) || 1), total), zoom:1, render:null, ticket:0, closed:false};
    const cited = Math.min(Math.max(1, Number(page) || 1), total);
    const root = element('div', undefined, 'pdf-viewer');
    const bar = element('div', undefined, 'pdf-toolbar');
    bar.setAttribute('role', 'group'); bar.setAttribute('aria-label', 'Página e zoom do PDF');
    const previous = button('Página anterior', '‹', () => show(state.page - 1));
    const next = button('Próxima página', '›', () => show(state.page + 1));
    const field = element('input'); field.type = 'number'; field.min = '1'; field.max = String(total);
    field.inputMode = 'numeric'; field.id = 'original-pdf-pagina'; field.setAttribute('enterkeyhint', 'go');
    const fieldLabel = element('label', undefined, 'pdf-page-field');
    fieldLabel.append(element('span', 'Página'), field, element('span', `de ${total}`));
    field.addEventListener('change', () => show(Number(field.value)));
    const zoomOut = button('Diminuir zoom', '−', () => zoom(-1));
    const level = element('output', '100%', 'pdf-zoom-level'); level.setAttribute('aria-live', 'off');
    const zoomIn = button('Aumentar zoom', '+', () => zoom(1));
    const fit = button('', 'Ajustar à largura', () => { state.zoom = 1; show(state.page); });
    const pages = element('div', undefined, 'pdf-pages'); pages.append(previous, fieldLabel, next);
    const zooms = element('div', undefined, 'pdf-zooms'); zooms.append(zoomOut, level, zoomIn, fit);
    bar.append(pages, zooms);
    const status = element('p', 'Carregando a página do PDF…', 'small pdf-status');
    status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite');
    const stage = element('div', undefined, 'pdf-stage'); stage.tabIndex = 0;
    stage.setAttribute('role', 'region'); stage.setAttribute('aria-label', `Página do PDF ${name}`);
    root.append(bar, status, stage);
    container.replaceChildren(root);
    function zoom(step) {
      const index = ZOOMS.indexOf(state.zoom);
      state.zoom = ZOOMS[Math.min(ZOOMS.length - 1, Math.max(0, (index < 0 ? 2 : index) + step))];
      show(state.page);
    }
    // Marks only spans holding a long piece of the cited excerpt (or all of it), and reports a
    // highlight only when they cover most of the excerpt: short common words never count.
    function highlight(layer) {
      const target = fold(reference);
      if (target.length < 8) return 0;
      const spans = [...layer.querySelectorAll('span')].filter(span => {
        const text = fold(span.textContent);
        return text.length >= Math.min(12, target.length) && (target.includes(text) || text.includes(target));
      });
      const covered = spans.reduce((sum, span) => sum + Math.min(fold(span.textContent).length, target.length), 0);
      if (covered < target.length * 0.6) return 0;
      for (const span of spans) span.classList.add('pdf-trecho');
      return spans.length;
    }
    const say = text => { if (status.textContent !== text) status.textContent = text; };
    let scrolledToExcerpt = false;
    function show(number) {
      const ticket = state.ticket + 1;
      return draw(number).catch(() => { if (!state.closed && ticket === state.ticket) say('Não foi possível desenhar esta página. Use Baixar original.'); });
    }
    async function draw(number) {
      if (state.closed || !Number.isFinite(number)) return;
      state.page = Math.min(Math.max(1, Math.trunc(number)), total);
      const ticket = ++state.ticket;
      state.render?.cancel();
      field.value = String(state.page);
      const focused = document.activeElement;
      previous.disabled = state.page <= 1; next.disabled = state.page >= total;
      zoomOut.disabled = state.zoom <= ZOOMS[0]; zoomIn.disabled = state.zoom >= ZOOMS.at(-1);
      // A control that just became disabled would drop keyboard focus: move it to its pair.
      const pair = new Map([[previous, next], [next, previous], [zoomIn, zoomOut], [zoomOut, zoomIn]]);
      if (focused?.disabled && pair.has(focused)) pair.get(focused).focus();
      level.textContent = `${Math.round(state.zoom * 100)}%`;
      const pdfPage = await doc.getPage(state.page);
      if (ticket !== state.ticket) return;
      const natural = pdfPage.getViewport({scale:1});
      const width = Math.max(200, stage.clientWidth - 2);
      const scale = width / natural.width * state.zoom;
      const viewport = pdfPage.getViewport({scale});
      const ratio = Math.min(window.devicePixelRatio || 1, Math.sqrt(MAX_PIXELS / (viewport.width * viewport.height)));
      const sheet = element('div', undefined, 'pdf-page');
      sheet.style.width = `${Math.floor(viewport.width)}px`; sheet.style.height = `${Math.floor(viewport.height)}px`;
      sheet.style.setProperty('--total-scale-factor', String(scale));
      sheet.style.setProperty('--scale-factor', String(scale));
      const canvas = element('canvas');
      canvas.width = Math.floor(viewport.width * ratio); canvas.height = Math.floor(viewport.height * ratio);
      canvas.style.width = `${Math.floor(viewport.width)}px`; canvas.style.height = `${Math.floor(viewport.height)}px`;
      // The text layer carries the readable text; the region names the page.
      canvas.setAttribute('aria-hidden', 'true');
      stage.setAttribute('aria-label', `Página ${state.page} de ${total} do PDF ${name}`);
      const layer = element('div', undefined, 'textLayer pdf-text-layer');
      sheet.append(canvas, layer);
      state.render = pdfPage.render({canvasContext:canvas.getContext('2d'), viewport, transform:ratio === 1 ? null : [ratio, 0, 0, ratio, 0, 0]});
      try { await state.render.promise; } catch (failure) { if (failure?.name === 'RenderingCancelledException') return; throw failure; }
      if (ticket !== state.ticket) return;
      stage.replaceChildren(sheet);
      let marked = 0;
      try {
        const text = new lib.TextLayer({textContentSource:await pdfPage.getTextContent(), container:layer, viewport});
        await text.render();
        layer.style.width = sheet.style.width; layer.style.height = sheet.style.height;
        if (state.page === cited) marked = highlight(layer);
      } catch { /* The page stays visible without the selectable text layer. */ }
      if (ticket !== state.ticket) return;
      const where = `Página ${state.page} de ${total}${state.page === cited ? ' · página citada' : ''}.`;
      say(state.page !== cited || !reference ? where
        : marked ? `${where} Trecho citado destacado.` : `${where} O trecho não foi localizado automaticamente; confira na imagem da página.`);
      // Scroll to the excerpt once; later zooms and redraws keep the reader's position.
      const first = layer.querySelector('.pdf-trecho');
      if (first && !scrolledToExcerpt) { scrolledToExcerpt = true; stage.scrollTop = Math.max(0, first.offsetTop - stage.clientHeight / 3); }
      pdfPage.cleanup();
    }
    let lastWidth = 0;
    const resize = new ResizeObserver(() => {
      const width = stage.clientWidth;
      if (Math.abs(width - lastWidth) > 24) { lastWidth = width; show(state.page); }
    });
    lastWidth = stage.clientWidth; show(state.page);
    resize.observe(stage);
    return () => { state.closed = true; state.render?.cancel(); resize.disconnect(); task.destroy(); };
  }
  return {open};
})();

// The original is fetched by the existing hash/scope-validated endpoints.
// Each opening gets a ticket; an older one that resumes after an await stops there.
let originalSequence = 0;
window.abrirOriginal = async (blob, name, page = 1, reference = '') => {
  const dialog=$('original-dialogo'), body=$('original-conteudo');
  window.fecharOriginal?.();
  const ticket = ++originalSequence;
  const pdf = /\.pdf$/i.test(name) || blob.type === 'application/pdf';
  const imageFile = /\.(png|jpe?g|gif|webp)$/i.test(name);
  const safeImageType = {'png':'image/png','jpg':'image/jpeg','jpeg':'image/jpeg','gif':'image/gif','webp':'image/webp'}[name.split('.').pop().toLowerCase()];
  const url = URL.createObjectURL(pdf ? new Blob([blob],{type:'application/pdf'}) : imageFile ? new Blob([blob],{type:safeImageType}) : blob);
  const cited = Math.max(1, Number(page) || 1);
  let closeViewer = null, closed = false;
  // Registered before any await, so a newer original or closing the dialog always releases this URL.
  window.fecharOriginal=()=>{closed=true;closeViewer?.();URL.revokeObjectURL(url);body.replaceChildren();};
  try {
  $('original-titulo').textContent=name;
  $('original-referencia').textContent=reference;
  $('original-referencia').hidden=!reference;
  $('original-localizacao').textContent=pdf ? `Página física ${cited} do PDF. Confira tabelas e elementos visuais no original.` : 'Original preservado. Confira o localizador indicado na fonte.';
  body.replaceChildren();
  // Without pdf.js (blocked or failed), the browser's own viewer remains, as before.
  const frame = () => { const node=element('iframe');node.title=`Original: ${name}`;node.src=url+'#page='+cited;body.replaceChildren(node,element('p','Se a página não aparecer neste aparelho, use Baixar original.','small')); };
  if(pdf) {
    body.append(element('p','Carregando a página do PDF…','small pdf-status'));
    LeitorPdf.open(body, blob, name, cited, reference, () => !closed)
      .then(close => { if (closed) close(); else closeViewer = close; })
      .catch(failure => { if (!closed && failure?.name !== 'AbortError') frame(); });
  }
  else if(imageFile) { const img=element('img');img.src=url;img.alt=`Original: ${name}`;body.append(img); }
  else if(/\.(txt|md|csv|tsv|json)$/i.test(name)) {
    const text = await blob.text();
    if (closed || ticket !== originalSequence) return;
    body.append(element('pre',text));
  }
  else body.append(element('p','Este formato precisa de um aplicativo compatível. Baixe o original para conferir.'));
  $('original-baixar').onclick=()=>download(blob,name);
  if(!dialog.open)dialog.showModal();
  } catch (failure) {
    // Nothing was shown: release the URL (closing is idempotent) and report to the caller.
    if (!closed) window.fecharOriginal?.();
    throw failure;
  }
};
$('original-fechar').addEventListener('click',()=>$('original-dialogo').close());
$('original-dialogo').addEventListener('close',()=>window.fecharOriginal?.());

// Markdown exports retain every field and exact reference; JSON stays available.
window.exportarEditorial = (data, name, format = 'md') => {
  if(format === 'json') { download(new Blob([JSON.stringify(data,null,2)],{type:'application/json;charset=utf-8'}),name+'.json'); return; }
  const lines=['# Registro da apuração','', 'Análise da IA e registros humanos devem ser conferidos nas fontes.',''];
  const safe = value => String(value ?? '').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
  const paragraph = value => {if(value)lines.push(safe(value),'');};
  const quote = value => {if(value)lines.push(...safe(value).split('\n').map(line=>'> '+line),'');};
  const scope=[data.caso_id || data.caso,data.rodada || data.rodada_atual,data.revisao || data.revisao_atual,data.geracao || data.geracao_achados].filter(Boolean).join(' / ');
  paragraph('Apuração e versão: '+scope);
  function source(item) {
    // Exported records keep one language (Portuguese), whatever the screen shows.
    lines.push('### '+safe(Leitura.fonte(item,'pt')),'');quote(item.trecho);
    paragraph('Referência: '+[scope,item.documento_id,item.referencia || item.referencia_atual || item.id,Leitura.localizador(item,'pt')].filter(Boolean).join(' · '));
    paragraph('Original: '+(item.original || item.nome_documento || item.nome_recebido || 'Consulte o registro da fonte'));
    if(item.original_sha256)paragraph('SHA-256 do original: '+item.original_sha256);
    paragraph(item.contexto);paragraph(item.limitacoes);
  }
  if(Array.isArray(data.resultados) || Array.isArray(data.registros)) {
    const items=data.resultados || data.registros;
    paragraph(`${items.length} registro(s) nesta exportação.`);
    for(const [index,raw]of items.entries()) {
      const item=raw.registro || raw;
      lines.push('## '+safe(`${index+1}. ${item.redacao || item.titulo || Leitura.fonte(item,'pt')}`),'');
      if(item.redacao || item.titulo) {
        if(item.autor)paragraph('Autoria: '+item.autor);
        if(item.suporte)paragraph('Suporte avaliado pela IA: '+pretty(item.suporte));
        if(item.revisao_humana)paragraph('Conferência humana: '+pretty(item.revisao_humana.estado));
        paragraph(item.anotacao);paragraph(item.limitacoes);
        paragraph([item.id,item.versao?'versão '+item.versao:'',raw.sha256?'SHA-256 '+raw.sha256:''].filter(Boolean).join(' · '));
        for(const evidence of item.evidencias || item.fontes || []) source(evidence);
      } else source(item);
    }
    download(new Blob([lines.join('\n')],{type:'text/markdown;charset=utf-8'}),name+'.md');return;
  }
  if(Array.isArray(data.comparacoes)) {
    paragraph(data.limitacao);
    for(const comparison of data.comparacoes) {
      lines.push('## '+safe(pretty(comparison.tipo)),'');
      for(const previous of comparison.anteriores || [])paragraph('Antes: '+previous.redacao);
      for(const current of comparison.atuais || [])paragraph('Agora: '+current.redacao);
      paragraph('Avaliação da IA: '+comparison.justificativa);
    }
    lines.push('## Evidências novas','');
    for(const evidence of data.evidencias_novas || [])source(evidence);
    download(new Blob([lines.join('\n')],{type:'text/markdown;charset=utf-8'}),name+'.md');return;
  }
  function render(value,depth=0) {
    if(value===null||value===undefined)return 'Não informado';
    if(typeof value!=='object')return String(value);
    for(const [key,item]of Object.entries(value)) {
      if(item && typeof item==='object') {lines.push('', '#'.repeat(Math.min(6,depth+2))+' '+key.replaceAll('_',' '),''); render(item,depth+1);}
      else lines.push(`**${key.replaceAll('_',' ')}:** ${safe(item ?? 'Não informado')}`, '');
    }
    return '';
  }
  render(data);download(new Blob([lines.join('\n')],{type:'text/markdown;charset=utf-8'}),name+'.md');
};
