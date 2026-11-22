'use strict';
// Caderno: notes (left), editor with autosave (center), sources of the open note (right). On a
// phone the note stays in front and the other two open as drawers.
// Each note has its own revision; autosave sends one request at a time, resends a request lost
// to the network with the same requisicao_id, and stops on a conflict without overwriting.
// Unconfirmed text is also kept as a draft in this tab's sessionStorage (contract, section 3).
(() => {
  const PAUSE = 1500, FIRST_RETRY = 2000, LAST_RETRY = 30000, DRAFT_PREFIX = 'vlado:rascunho:';
  const LEGACY = ['h1', 'h4', 'h5', 'h6'];
  const t = (text, vars) => window.I18N ? window.I18N.t(text, vars) : text;
  const uid = () => crypto.randomUUID().replaceAll('-', '');
  const dialog = $('apuracao-adicionar-dialogo');
  const SAVE_TEXT = {pendente:'Alterações não salvas', salvando:'Salvando…',
    rede:'Sem conexão. Rascunho guardado nesta aba; tentando de novo…',
    conflito:'Conflito: a nota foi alterada em outra aba', sessao:'Sessão expirada. Entre de novo; o rascunho continua nesta aba.',
    titulo:'Dê um título à nota para salvar', erro:'Alterações não salvas'};
  let caseId = '', notes = [], current = null, sources = [], loading = false, sequence = 0, noteSequence = 0;
  let dirty = false, edits = 0, timer = null, retryTimer = null, retryDelay = FIRST_RETRY;
  let inflight = null, retryPayload = null, conflict = false, copied = false, sessionLost = false, saveState = {kind:'', at:null};
  let creating = false, createRequest = null, pendingInsert = null, inserting = false, dialogSequence = 0, highlightTimer = null;
  let offeredDraft = null, query = '', drawer = null, drawerOpener = null, originReturn = null, inflightPayload = null;
  // Set when the writer signs out: nothing is saved or kept in this tab after that.
  let signedOut = false;

  // Drafts: this tab only (sessionStorage), never localStorage, IndexedDB or cookies. A note may
  // hold unpublished reporting, so nothing outlives the tab; logout clears them too.
  const drafts = (() => {
    const store = () => { try { return window.sessionStorage || null; } catch { return null; } };
    let account = document.body.dataset.conta || (document.body.dataset.modo === 'local' ? 'local' : 'sessao');
    const key = (caso, nota) => `${DRAFT_PREFIX}${account}:${caso}:${nota}`;
    function read(caso, nota) {
      try {
        const value = JSON.parse(store()?.getItem(key(caso, nota)) || 'null');
        const valid = value && typeof value.texto === 'string' && typeof value.titulo === 'string' && Number.isInteger(value.revisao_base);
        return valid ? value : null;
      } catch { return null; }
    }
    function write(caso, nota, data) {
      if (signedOut) return;
      try { store()?.setItem(key(caso, nota), JSON.stringify({...data, em:new Date().toISOString()})); } catch { /* full or blocked: autosave goes on */ }
    }
    function remove(caso, nota) { try { store()?.removeItem(key(caso, nota)); } catch { /* nothing to clear */ } }
    function clearAll() {
      try {
        const area = store(), keys = [];
        if (!area) return;
        for (let i = 0; i < area.length; i++) { const name = area.key(i); if (name?.startsWith(DRAFT_PREFIX)) keys.push(name); }
        for (const name of keys) area.removeItem(name);
      } catch { /* storage blocked: nothing was kept */ }
    }
    return {read, write, remove, clearAll, account: id => { if (id) account = String(id); }};
  })();
  // The Sair button calls this before ending the session.
  window.limparRascunhosCaderno = () => { stopEverything(); drafts.clearAll(); };
  // Before signing out: save what can be saved; if something is left, ask. True means "go on".
  window.prepararSaidaCaderno = async () => {
    if (await flush() || !pending() || await Dialogo.confirmar({variante:'destrutivo', titulo:'Sair sem salvar?', texto:'Há alterações não salvas no Caderno.', acao:'Sair sem salvar'})) { stopEverything(); return true; }
    return false;
  };
  const accountReady = document.body.dataset.modo === 'local' || document.body.dataset.conta ? Promise.resolve()
    : fetch('/api/sessao').then(response => response.ok ? response.json() : null)
      .then(data => drafts.account(data?.conta?.id)).catch(() => {});

  // If editor_notas.js itself failed to load, the Markdown field still edits and saves.
  function plainEditor(onInput) {
    $('apuracao-texto').addEventListener('input', onInput);
    $('apuracao-vditor').hidden = true; $('apuracao-texto-alternativo').hidden = false;
    $('apuracao-editor-aviso').textContent = 'O editor visual não carregou. Você pode editar e salvar o Markdown abaixo.';
    $('apuracao-editor-aviso').hidden = false;
    return {open(text) { $('apuracao-texto').value = text; }, flush() {}, disabled() {}};
  }
  const editor = window.EditorNotas ? new window.EditorNotas(changed, styleBar) : plainEditor(changed);

  const locale = () => (window.I18N?.idioma?.() === 'en' ? 'en' : 'pt-BR');
  const clock = iso => new Date(iso).toLocaleTimeString(locale(), {hour:'2-digit', minute:'2-digit'});
  function updated(iso) {
    if (!iso) return '';
    const date = new Date(iso);
    return date.toDateString() === new Date().toDateString() ? t('Atualizada às {hora}', {hora:clock(iso)})
      : t('Atualizada em {data}', {data:date.toLocaleDateString(locale())});
  }
  const sourceCount = count => count === 1 ? t('1 fonte') : t('{n} fontes', {n:count});
  const fold = text => String(text).normalize('NFD').replace(/\p{M}/gu, '').toLowerCase();
  // Widths where each panel is a drawer (caderno.css): the list below 1280px, the sources below 901px.
  const DRAWER_WIDTH = {notas:'(max-width: 1279px)', fontes:'(max-width: 1023px)'};
  const asDrawer = name => !!window.matchMedia?.(DRAWER_WIDTH[name]).matches;
  function error(message = '') { $('apuracao-erro').textContent = message; $('apuracao-erro').hidden = !message; }
  function dialogError(message = '') { $('apuracao-adicionar-erro').textContent = message; $('apuracao-adicionar-erro').hidden = !message; }
  function indicator(kind, at = null) { saveState = {kind, at}; renderIndicator(); }
  function renderIndicator() {
    const target = $('apuracao-salvamento');
    target.dataset.estado = saveState.kind;
    target.textContent = saveState.kind === 'salvo' ? t('Nota salva às {hora}', {hora:clock(saveState.at)})
      : saveState.kind ? t(SAVE_TEXT[saveState.kind]) : '';
  }
  function controls() {
    const ready = !!caseId && !loading;
    $('apuracao-caso').disabled = loading;
    $('apuracao-nova').disabled = !ready || creating;
    $('apuracao-nova-lista').disabled = !ready || creating;
    $('apuracao-inserir').disabled = !ready;
    $('apuracao-atualizar').disabled = loading;
    $('apuracao-exportar').disabled = !ready || !notes.length;
    $('apuracao-excluir').disabled = !current || loading;
  }
  // "n de m tarefas concluídas", read from the Markdown that is saved.
  function taskCount() {
    let total = 0, done = 0;
    for (const match of $('apuracao-texto').value.matchAll(/^[ \t]*(?:[-*+]|\d+[.)])[ \t]+\[([ xX])\]/gm)) { total++; if (match[1] !== ' ') done++; }
    const target = $('apuracao-tarefas');
    target.hidden = !current || !total;
    target.textContent = total ? t('{n} de {m} tarefas concluídas', {n:done, m:total}) : '';
  }

  // Style bar: shows the block style at the caret; legacy levels keep their real name.
  function styleBar(state) {
    const bar = $('apuracao-formatar'), select = $('apuracao-estilo');
    bar.hidden = !state.ready;
    if (!state.ready) return;
    for (const option of [...select.options]) if (LEGACY.includes(option.value) && option.value !== state.style) option.remove();
    if (LEGACY.includes(state.style) && ![...select.options].some(option => option.value === state.style)) {
      select.append(new Option(t('Cabeçalho {n} (legado)', {n:state.style.slice(1)}), state.style));
    }
    const markdown = state.mode === 'sv';
    if (state.style) select.value = state.style;
    select.disabled = markdown || state.locked;
    select.title = markdown ? t('No modo Markdown, escreva ## para título da seção e ### para subtítulo.') : '';
    for (const button of bar.querySelectorAll('[data-comando]')) button.disabled = state.locked;
    $('apuracao-mais').setAttribute('aria-controls', 'apuracao-vditor-barra');
  }

  // Left column: lightweight summaries, most recent first, filtered by the search box.
  function summary(note) {
    return {id:note.id, titulo:note.titulo, atualizado_em_utc:note.atualizado_em_utc || note.criado_em_utc, criado_em_utc:note.criado_em_utc,
      revisao:note.revisao || 0, fontes:(note.fontes || []).length, autor:(note.atualizado_por || note.criado_por || {}).nome || null};
  }
  function remember(note) {
    notes = [summary(note), ...notes.filter(item => item.id !== note.id)]
      .sort((a, b) => String(b.atualizado_em_utc).localeCompare(String(a.atualizado_em_utc)));
    renderList();
  }
  function renderList() {
    const wanted = fold(query.trim()), shown = wanted ? notes.filter(note => fold(note.titulo).includes(wanted)) : notes;
    $('apuracao-notas').replaceChildren(...shown.map(note => {
      const item = element('li'), button = element('button', undefined, 'note-item');
      button.type = 'button'; button.dataset.nota = note.id;
      button.setAttribute('aria-current', String(note.id === current?.id));
      const title = element('span', note.titulo, 'note-item-title'); title.setAttribute('translate', 'no');
      button.append(title, element('span', [updated(note.atualizado_em_utc), sourceCount(note.fontes)].filter(Boolean).join(' · '), 'note-item-meta'));
      if (note.autor) button.append(element('span', t('Autor: {nome}', {nome:note.autor}), 'note-item-author'));
      button.addEventListener('click', () => openNote(note.id));
      item.append(button);
      return item;
    }));
    $('apuracao-busca-status').textContent = !wanted ? '' : shown.length ? t('{n} de {m} notas', {n:shown.length, m:notes.length})
      : t('Nenhuma nota com “{busca}”.', {busca:query.trim()});
    $('apuracao-notas-vazio').hidden = !caseId || loading || notes.length > 0;
    $('apuracao-busca').closest('label').hidden = notes.length < 2 && !wanted;
    $('apuracao-notas').closest('.notebook-workspace').classList.toggle('is-empty', !current);
    drawerLabels();
  }
  function drawerLabels() {
    const count = (label, n) => [t(label), ' ', element('span', String(n), 'caderno-contagem')];
    $('apuracao-ver-notas').replaceChildren(...count('Notas', notes.length));
    $('apuracao-ver-fontes').replaceChildren(...count('Fontes da nota', sources.length));
    $('apuracao-ver-fontes').hidden = !current;
  }

  // Phones: the note stays in front; the list and the sources open as drawers.
  const DRAWERS = {notas:['apuracao-lista-painel', 'apuracao-ver-notas'], fontes:['apuracao-fontes-painel', 'apuracao-ver-fontes']};
  function setDrawer(name, {focus = true} = {}) {
    if (name && !asDrawer(name)) return;
    const previous = drawer;
    drawer = name;
    for (const [key, [panel, button]] of Object.entries(DRAWERS)) {
      $(panel).classList.toggle('is-aberta', key === name);
      $(button).setAttribute('aria-expanded', String(key === name));
    }
    $('apuracao-gaveta-fundo').hidden = !name;
    $('area-apuracao').classList.toggle('caderno-com-gaveta', !!name);
    if (name && focus) { drawerOpener = document.activeElement; $(DRAWERS[name][0]).querySelector('.caderno-fechar')?.focus(); }
    else if (!name && previous && focus) { if (!editor.resume?.()) drawerOpener?.focus?.(); drawerOpener = null; }
  }

  // Right column: sources resolved by the server, with the original one click away.
  function sourceDocument(doc) {
    const block = element('div', undefined, 'note-source-doc');
    const name = element('p', Leitura.nome(doc), 'note-source-doc-name'); name.setAttribute('translate', 'no');
    const where = [doc.pagina_pdf ? t('Página PDF {n}', {n:doc.pagina_pdf}) : '', t(doc.localizador || '')].filter(Boolean).join(' · ');
    const button = element('button', t(Leitura.rotuloOriginal(Leitura.pagina(doc))), 'secondary');
    button.type = 'button';
    block.append(name, element('p', where, 'small'), button);
    if (!doc.disponivel) {
      button.disabled = true;
      const reason = element('p', t('Original indisponível (apuração na lixeira ou arquivo ausente)'), 'small');
      reason.id = `apuracao-indisponivel-${doc.abrir?.fonte_id}-${doc.indice}`;
      button.setAttribute('aria-describedby', reason.id);
      block.append(reason);
      return block;
    }
    button.addEventListener('click', async () => {
      button.disabled = true;
      // Closing the original brings the writer back to the same caret and scroll in the note.
      originReturn = {scroll:window.scrollY || 0};
      try {
        const {operacao, ...scope} = doc.abrir;
        await window.abrirOriginal(await api('apuracao-original', scope, true), doc.nome_documento, doc.pagina_pdf);
      } catch (failure) { originReturn = null; error(failure.message); }
      finally { button.disabled = false; }
    });
    return block;
  }
  function renderSources() {
    const target = $('apuracao-fontes');
    drawerLabels();
    if (!sources.length) { target.replaceChildren(element('p', t('Esta nota ainda não tem fontes. Use Inserir trecho com fonte.'), 'small')); return; }
    target.replaceChildren(...sources.map(source => {
      const card = element('article', undefined, 'note-source');
      card.id = 'apuracao-fonte-' + source.numero; card.tabIndex = -1;
      const marker = element('span', source.marcador, 'note-source-marker'); marker.setAttribute('translate', 'no');
      const heading = element('h4'); heading.append(marker, ' · ', t(source.tipo === 'ia' ? 'Achado da IA' : 'Pesquisa documental'));
      const details = [t('Rodada {rodada}', {rodada:source.rodada}), source.adicionada_por ? t('Adicionada por {nome}', {nome:source.adicionada_por}) : ''];
      card.append(heading, element('blockquote', source.texto_selecionado), element('p', details.filter(Boolean).join(' · '), 'small'));
      if (!source.documentos.length) card.append(element('p', t('Achado sem evidência documental vinculada.'), 'small'));
      for (const doc of source.documentos) card.append(sourceDocument(doc));
      return card;
    }));
  }
  function highlight(number) {
    const card = $('apuracao-fonte-' + number);
    if (!card) return;
    if (asDrawer('fontes')) setDrawer('fontes', {focus:false});
    for (const other of $('apuracao-fontes').querySelectorAll('.note-source')) other.classList.remove('is-highlighted');
    card.classList.add('is-highlighted');
    card.scrollIntoView({block:'nearest', behavior:'smooth'});
    clearTimeout(highlightTimer);
    highlightTimer = setTimeout(() => card.classList.remove('is-highlighted'), 2500);
  }
  function markerAt(text, position) {
    for (const match of String(text).matchAll(/\[Fonte (\d+)\]/g)) {
      if (position >= match.index && position <= match.index + match[0].length) return Number(match[1]);
    }
    return null;
  }
  // The preview turns each [Fonte n] into a button that shows that source.
  function preview() {
    const target = $('apuracao-previa');
    Leitura.markdown(target, $('apuracao-texto').value);
    const walker = document.createTreeWalker(target, NodeFilter.SHOW_TEXT), found = [];
    for (let node = walker.nextNode(); node; node = walker.nextNode()) if (/\[Fonte \d+\]/.test(node.data)) found.push(node);
    for (const node of found) {
      node.replaceWith(...node.data.split(/(\[Fonte \d+\])/).filter(Boolean).map(part => {
        const match = /^\[Fonte (\d+)\]$/.exec(part);
        if (!match) return part;
        const chip = element('button', part, 'source-citation'); chip.type = 'button';
        chip.addEventListener('click', () => highlight(Number(match[1])));
        return chip;
      }));
    }
  }
  function authorship(note) {
    const who = note?.atualizado_por || note?.criado_por;
    $('apuracao-autoria').textContent = who?.nome ? Leitura.autoria(who.nome, who.origem) : '';
    $('apuracao-autoria').hidden = !who?.nome;
  }

  // Draft of the open note: kept on every unconfirmed change, with the base revision. While a save
  // is on its way, the text sent goes along, so a reload after that save landed is not a conflict.
  // Vditor ends the Markdown with a newline; that alone is not an unsaved change.
  const sameText = (a, b) => String(a).replace(/\s+$/, '') === String(b).replace(/\s+$/, '');
  const asSaved = (titulo, texto, note) => !!note && titulo === note.titulo && sameText(texto, note.texto);
  function keepDraft() {
    if (!current) return;
    const titulo = $('apuracao-nota-titulo').value, texto = $('apuracao-texto').value;
    // A late editor callback that only repeats the saved text leaves no draft behind.
    if (asSaved(titulo, texto, current.nota) && !retryPayload && !inflightPayload) { drafts.remove(caseId, current.id); return; }
    const sent = (retryPayload || inflightPayload)?.body;
    drafts.write(caseId, current.id, {titulo, texto,
      revisao_base:current.base ?? current.revisao, ...(sent ? {enviado:{titulo:sent.titulo, texto:sent.texto}} : {})});
  }
  function lockEditing(locked) {
    $('apuracao-nota-titulo').readOnly = locked; $('apuracao-texto').readOnly = locked;
    editor.disabled(locked);
  }
  function offerDraft(draft) {
    offeredDraft = draft;
    $('apuracao-rascunho-texto').textContent = t('Esta nota tem um rascunho não salvo nesta aba, de {hora}. Restaure para continuar dele ou descarte para ficar com a versão salva.', {hora:clock(draft.em)});
    $('apuracao-rascunho').hidden = false;
    lockEditing(true);
  }
  function closeDraftOffer() { offeredDraft = null; $('apuracao-rascunho').hidden = true; lockEditing(false); }
  // On opening: no draft, an identical one (dropped), one over the same base (offer) or one over
  // an older base (the note changed elsewhere: conflict, with the local text on screen to copy).
  function checkDraft(note) {
    const draft = drafts.read(caseId, note.id);
    if (!draft) return;
    if (asSaved(draft.titulo, draft.texto, note)) { drafts.remove(caseId, note.id); return; }
    const ownSave = draft.enviado && note.revisao === draft.revisao_base + 1 && draft.enviado.texto === note.texto && draft.enviado.titulo === note.titulo;
    if (draft.revisao_base === note.revisao || ownSave) { offerDraft(draft); return; }
    $('apuracao-nota-titulo').value = draft.titulo; $('apuracao-texto').value = draft.texto;
    editor.open(draft.texto);
    // The text on screen was written over the old revision: later drafts keep that base, so a
    // reload still treats it as a conflict instead of offering to save over the other tab.
    current.base = draft.revisao_base;
    dirty = true; preview(); taskCount();
    showConflict();
  }

  function stopTimers() { clearTimeout(timer); timer = null; clearTimeout(retryTimer); retryTimer = null; }
  function showNote(note, resolved) {
    stopTimers();
    current = {id:note.id, revisao:note.revisao || 0, nota:note};
    sources = resolved || [];
    dirty = false; edits = 0; conflict = false; copied = false; sessionLost = false; retryPayload = null; retryDelay = FIRST_RETRY;
    if (offeredDraft) closeDraftOffer();
    $('apuracao-conflito').hidden = true; $('apuracao-conflito-status').textContent = '';
    $('apuracao-editor').hidden = false; $('apuracao-fontes-painel').hidden = false;
    $('apuracao-nota-titulo').value = note.titulo; $('apuracao-texto').value = note.texto;
    editor.open(note.texto);
    authorship(note); preview(); renderSources(); renderList(); controls(); taskCount();
    indicator('');
    checkDraft(note);
  }
  function clearEditor() {
    stopTimers();
    current = null; sources = []; dirty = false; conflict = false; retryPayload = null; sessionLost = false;
    if (offeredDraft) closeDraftOffer();
    $('apuracao-editor').hidden = true; $('apuracao-fontes-painel').hidden = true; $('apuracao-conflito').hidden = true;
    indicator(''); renderList(); controls(); taskCount(); setDrawer(null, {focus:false});
  }
  function showConflict() {
    conflict = true; copied = false; stopTimers();
    indicator('conflito');
    $('apuracao-conflito').hidden = false; $('apuracao-conflito-texto').hidden = true;
    $('apuracao-conflito-status').textContent = '';
  }

  function schedule() { clearTimeout(timer); timer = setTimeout(() => { timer = null; save(); }, PAUSE); }
  function changed() {
    if (!current || offeredDraft || signedOut) return;
    dirty = true; edits++; copied = false; preview(); taskCount(); keepDraft();
    if (conflict) { indicator('conflito'); return; }
    if (sessionLost) { indicator('sessao'); return; }
    if (inflight || retryPayload) return;  // the running save reschedules when it ends
    indicator('pendente'); schedule();
  }
  function retry() {
    retryTimer = setTimeout(() => { retryTimer = null; save(); }, retryDelay);
    retryDelay = Math.min(retryDelay * 2, LAST_RETRY);
  }
  function save() {
    clearTimeout(timer); timer = null;
    if (inflight) return inflight;
    if (!current || conflict || sessionLost || offeredDraft || signedOut) return Promise.resolve();
    let payload = retryPayload;
    if (!payload) {
      if (!dirty) return Promise.resolve();
      editor.flush();
      const titulo = $('apuracao-nota-titulo').value;
      if (!titulo.trim()) { indicator('titulo'); return Promise.resolve(); }
      payload = {edits, body:{caso:caseId, requisicao_id:uid(), titulo, texto:$('apuracao-texto').value,
        nota_id:current.id, revisao_nota:current.revisao}};
    }
    clearTimeout(retryTimer); retryTimer = null;
    const noteId = current.id, noteCase = caseId;
    indicator('salvando');
    inflightPayload = payload;
    inflight = (async () => {
      try {
        const result = await api('apuracao-nota-salvar', payload.body);
        retryPayload = null; retryDelay = FIRST_RETRY;
        remember(result.nota);
        if (current?.id !== noteId || caseId !== noteCase) { settleLeftDraft(noteCase, noteId, payload.body, result.nota.revisao); return; }
        current.revisao = result.nota.revisao; current.nota = result.nota;
        authorship(result.nota); error();
        // "Nota salva" only now, after the server confirmed the new revision.
        if (edits === payload.edits) { dirty = false; drafts.remove(noteCase, noteId); indicator('salvo', result.salvo_em_utc); }
        else { inflightPayload = null; keepDraft(); indicator('pendente'); schedule(); }
      } catch (failure) {
        if (current?.id !== noteId || caseId !== noteCase) return;
        if (failure.result?.codigo === 'conflito') { retryPayload = null; showConflict(); }
        else if (failure.result?.estado === 'sem_sessao' || failure.result?.codigo === 'sem_sessao') {
          // The page token is gone; the draft stays in this tab until the next sign-in.
          retryPayload = null; sessionLost = true; stopTimers(); indicator('sessao');
        } else if (failure.rede) {
          // No answer: resend the very same request, so a save that did land is not applied twice.
          retryPayload = payload; inflightPayload = null; keepDraft(); indicator('rede'); retry();
        } else { retryPayload = null; indicator('erro'); error(failure.message); }  // refused (413, 500…): no endless resend
      } finally { inflight = null; inflightPayload = null; }
    })();
    return inflight;
  }
  // A save that ends after the writer left the note: the draft goes only if it holds exactly what
  // was saved; newer text stays, now over the revision just confirmed.
  function settleLeftDraft(caso, nota, body, revisao) {
    const draft = drafts.read(caso, nota);
    if (!draft) return;
    if (draft.titulo === body.titulo && sameText(draft.texto, body.texto)) { drafts.remove(caso, nota); return; }
    const {enviado, em, ...rest} = draft;
    drafts.write(caso, nota, {...rest, revisao_base:revisao});
  }
  // Save now (switching notes, exporting, inserting). True when nothing is left unsaved.
  async function flush() {
    editor.sync?.();  // a change the editor has not reported yet (task box, toolbar) counts too
    for (let attempt = 0; attempt < 4; attempt++) {
      if (inflight) { await inflight; continue; }
      if (conflict || sessionLost || !current || (!dirty && !retryPayload)) break;
      await save();
      if (retryPayload || saveState.kind === 'titulo' || saveState.kind === 'erro') break;
    }
    return !dirty && !retryPayload && !conflict;
  }
  const discard = () => Dialogo.confirmar({variante:'destrutivo', titulo:'Descartar alterações?', texto:'Há alterações não salvas.', acao:'Descartar alterações'});
  // The writer chose to drop the open note's unsaved text: its draft goes too.
  function dropDraft() { if (current) drafts.remove(caseId, current.id); }
  const pending = () => dirty || !!retryPayload;
  // A confirmed discard: no pending retry may send the dropped text later, and no draft stays.
  function abandon() { stopTimers(); retryPayload = null; dirty = false; dropDraft(); }
  function stopEverything() { signedOut = true; stopTimers(); retryPayload = null; dirty = false; }

  async function openNote(id, {force = false} = {}) {
    if (!force && current?.id === id) { setDrawer(null); return; }
    if (!force && current) {
      if (!(await flush()) && pending()) { if (!(await discard())) return; abandon(); }
      else if (!pending() && !offeredDraft) dropDraft();  // all confirmed; an offered draft waits for a choice
    }
    const ticket = ++noteSequence, captured = caseId;
    // Nothing typed while the next note loads can land in the note being left.
    loading = true; controls(); error(); lockEditing(true);
    try {
      const result = await api('apuracao-nota', {caso:captured, nota_id:id});
      if (ticket !== noteSequence || captured !== caseId) return;
      loading = false;
      setDrawer(null, {focus:false});
      showNote(result.nota, result.fontes);
      remember(result.nota);
    } catch (failure) { if (ticket === noteSequence) error(failure.message); }
    finally { if (ticket === noteSequence) { loading = false; if (!offeredDraft) lockEditing(false); controls(); } }
  }
  async function load(selected, preferred = current?.id) {
    const ticket = ++sequence;
    // Reopening the same case keeps the list on screen until the new one arrives (no flicker).
    if ((selected || '') !== caseId) notes = [];
    caseId = selected || ''; loading = true; clearEditor(); error();
    if (!caseId) { loading = false; renderList(); controls(); $('apuracao-status').textContent = ''; return; }
    try {
      await accountReady;
      const result = await api('apuracao-notas', {caso:caseId});
      if (ticket !== sequence) return;
      notes = result.notas; loading = false; renderList();
      const target = notes.some(note => note.id === preferred) ? preferred : notes[0]?.id;
      if (target) await openNote(target, {force:true});
    } catch (failure) { if (ticket === sequence) { error(failure.message); notes = []; } }
    finally { if (ticket === sequence) { loading = false; renderList(); controls(); } }
  }
  async function catalog() {
    if (dirty || inflight) return;
    try {
      const response = await fetch('/api/catalogo'), data = await response.json();
      if (!response.ok) throw new Error(data.erro || 'Falha ao listar apurações.');
      const selected = window.contextoCaso?.() ?? ($('apuracao-caso').value || $('caso').value || '');
      $('apuracao-caso').replaceChildren(new Option('Selecione uma apuração', ''), ...data.casos.map(c => new Option(c.titulo, c.id)));
      if (data.casos.some(c => c.id === selected)) $('apuracao-caso').value = selected;
      await load($('apuracao-caso').value);
    } catch (failure) { error(failure.message); }
  }

  $('apuracao-caso').addEventListener('change', async () => {
    const target = $('apuracao-caso').value;
    if (current && !(await flush()) && pending()) {
      if (!(await discard())) { $('apuracao-caso').value = caseId; return; }
      abandon();
    }
    load(target, null);
  });
  $('apuracao-atualizar').addEventListener('click', async () => {
    if ((await flush()) || !pending() || await discard()) { if (pending()) abandon(); catalog(); }
  });
  $('apuracao-nota-titulo').addEventListener('input', changed);
  $('apuracao-form').addEventListener('submit', event => { event.preventDefault(); flush(); });
  $('apuracao-texto').addEventListener('click', () => {
    const number = markerAt($('apuracao-texto').value, $('apuracao-texto').selectionStart);
    if (number) highlight(number);
  });
  $('apuracao-vditor').addEventListener('click', () => {
    const selection = window.getSelection?.(), node = selection?.anchorNode;
    const number = node?.nodeType === 3 ? markerAt(node.data, selection.anchorOffset) : null;
    if (number) highlight(number);
  });
  $('apuracao-busca').addEventListener('input', () => { query = $('apuracao-busca').value; renderList(); });
  $('apuracao-estilo').addEventListener('change', () => editor.setStyle?.($('apuracao-estilo').value));
  for (const button of $('apuracao-formatar').querySelectorAll('[data-comando]')) {
    button.addEventListener('click', () => (button.dataset.comando === 'check' ? editor.insertTask?.() : editor.command?.(button.dataset.comando)));
  }
  $('apuracao-mais').addEventListener('click', () => $('apuracao-mais').setAttribute('aria-expanded', String(!!editor.toggleMore?.())));
  $('apuracao-rascunho-restaurar').addEventListener('click', () => {
    const draft = offeredDraft;
    if (!draft || !current) return;
    closeDraftOffer();
    $('apuracao-nota-titulo').value = draft.titulo; $('apuracao-texto').value = draft.texto;
    editor.open(draft.texto);
    changed();
  });
  $('apuracao-rascunho-descartar').addEventListener('click', () => {
    if (!offeredDraft || !current) return;
    drafts.remove(caseId, current.id); closeDraftOffer();
  });
  $('apuracao-ver-notas').addEventListener('click', () => setDrawer(drawer === 'notas' ? null : 'notas'));
  $('apuracao-ver-fontes').addEventListener('click', () => setDrawer(drawer === 'fontes' ? null : 'fontes'));
  $('apuracao-fechar-notas').addEventListener('click', () => setDrawer(null));
  // Phones: the toolbar sits under the note, so the list drawer also offers a new note.
  $('apuracao-nova-lista').addEventListener('click', () => { setDrawer(null, {focus:false}); $('apuracao-nova').click(); });
  $('apuracao-fechar-fontes').addEventListener('click', () => setDrawer(null));
  $('apuracao-gaveta-fundo').addEventListener('click', () => setDrawer(null));
  $('area-apuracao').addEventListener('keydown', event => { if (event.key === 'Escape' && drawer) { event.preventDefault(); setDrawer(null); } });
  $('original-dialogo')?.addEventListener('close', () => {
    if (!originReturn) return;
    const back = originReturn; originReturn = null;
    setDrawer(null, {focus:false});
    setTimeout(() => { window.scrollTo?.({top:back.scroll, behavior:'instant'}); editor.resume?.(); }, 0);
  });
  $('apuracao-nova').addEventListener('click', async () => {
    if (!caseId || creating) return;
    if (!(await flush()) && pending()) { if (!(await discard())) return; abandon(); }
    // A lost answer is resent with the same id, so the note is not created twice.
    if (createRequest?.caso !== caseId) createRequest = {caso:caseId, id:uid(), titulo:t('Nova nota')};
    const request = createRequest;
    // While the new note is created, nothing typed can land in the note being left.
    creating = true; controls(); error(); indicator('salvando'); lockEditing(true);
    try {
      const result = await api('apuracao-nota-salvar', {caso:request.caso, requisicao_id:request.id, titulo:request.titulo, texto:''});
      createRequest = null;
      if (request.caso !== caseId) return;
      remember(result.nota); showNote(result.nota, []); indicator('salvo', result.salvo_em_utc);
      $('apuracao-nota-titulo').focus(); $('apuracao-nota-titulo').select();
    } catch (failure) {
      if (failure.result) createRequest = null;
      indicator(''); error(failure.message);
    } finally { creating = false; if (!offeredDraft) lockEditing(false); controls(); }
  });
  $('apuracao-excluir').addEventListener('click', async () => {
    if (!current || !(await Dialogo.confirmar({variante:'destrutivo', titulo:'Excluir {item}?', item:current.titulo, texto:'As fontes serão preservadas.', acao:'Excluir nota', gatilho:$('apuracao-excluir')}))) return;
    await flush();
    const target = current;
    loading = true; controls(); error();
    try {
      await api('apuracao-nota-excluir', {caso:caseId, requisicao_id:uid(), nota_id:target.id, revisao_nota:target.revisao});
      drafts.remove(caseId, target.id);
      notes = notes.filter(note => note.id !== target.id);
      clearEditor(); loading = false;
      $('apuracao-status').textContent = t('Nota excluída. As fontes continuam preservadas.');
      if (notes.length) await openNote(notes[0].id, {force:true});
    } catch (failure) {
      if (failure.result?.codigo === 'conflito') showConflict(); else error(failure.message);
    } finally { loading = false; renderList(); controls(); }
  });
  $('apuracao-exportar').addEventListener('click', async () => {
    if (!caseId) return;
    if (!(await flush()) && dirty) { error(t('Salve a nota aberta antes de exportar.')); return; }
    loading = true; controls(); error();
    const format = $('apuracao-formato').value;
    try {
      download(await api('apuracao-exportar', {caso:caseId, formato:format}, true), `caderno_${caseId}.${format}`);
      $('apuracao-status').textContent = t('Caderno exportado com as referências de cada nota.');
    } catch (failure) { error(failure.message); }
    finally { loading = false; controls(); }
  });
  $('apuracao-inserir').addEventListener('click', () => {
    const panel = $('apuracao-inserir-ajuda'), open = panel.hidden;
    panel.hidden = !open; $('apuracao-inserir').setAttribute('aria-expanded', String(open));
  });
  $('apuracao-ir-documentos').addEventListener('click', () => showArea('documentos'));
  $('apuracao-ir-achados').addEventListener('click', () => showArea('achados'));
  $('apuracao-copiar').addEventListener('click', async () => {
    editor.flush();
    const text = `${$('apuracao-nota-titulo').value}\n\n${$('apuracao-texto').value}`;
    try {
      await navigator.clipboard.writeText(text);
      copied = true;
      $('apuracao-conflito-status').textContent = t('Texto copiado. Agora você pode recarregar a nota.');
    } catch {
      const area = $('apuracao-conflito-texto');
      area.value = text; area.hidden = false; area.focus(); area.select();
      $('apuracao-conflito-status').textContent = t('Não foi possível copiar automaticamente. Selecione o texto abaixo e copie.');
    }
  });
  $('apuracao-recarregar').addEventListener('click', async () => {
    if (!current) return;
    if (!copied && !(await Dialogo.confirmar({variante:'destrutivo', titulo:'Recarregar a nota?', texto:'Recarregar descarta o texto deste editor.', acao:'Recarregar e descartar', gatilho:$('apuracao-recarregar')}))) return;
    abandon();
    await openNote(current.id, {force:true});
  });

  // "Inserir em nota" in search results and findings: choose the note, then insert with its revision.
  function dialogControls() {
    $('apuracao-adicionar-salvar').disabled = !pendingInsert || inserting;
    $('apuracao-adicionar-fechar').disabled = inserting;
  }
  window.botaoAdicionarApuracao = (scope, container, fallback) => {
    const button = element('button', 'Inserir em nota', 'secondary'); button.type = 'button'; let selected = '';
    const selection = () => {
      const value = window.getSelection();
      return value && !value.isCollapsed && container?.contains(value.anchorNode) && container.contains(value.focusNode) ? value.toString() : fallback;
    };
    // Capture before the button changes focus; keyboard activation also uses the current selection.
    button.addEventListener('pointerdown', () => { selected = selection(); });
    button.addEventListener('click', async event => {
      if (inserting) return;
      const text = event.detail ? selected || selection() : selection(), ticket = ++dialogSequence;
      selected = ''; dialogError(); pendingInsert = null; dialogControls();
      $('apuracao-adicionar-origem').textContent = `${scope.caso} / ${scope.rodada} · ${scope.tipo === 'ia' ? 'Achado da IA' : 'Pesquisa documental'}`;
      $('apuracao-adicionar-texto').textContent = text;
      dialog.showModal();
      try {
        const saved = await api('apuracao-notas', {caso:scope.caso});
        if (!dialog.open || ticket !== dialogSequence) return;
        pendingInsert = {scope:{...scope, texto:text}, notes:saved.notas, key:null, request:null};
        $('apuracao-destino').replaceChildren(new Option('Criar nova nota', ''), ...saved.notas.map(note => new Option(note.titulo, note.id)));
        if (caseId === scope.caso && current) $('apuracao-destino').value = current.id;
        dialogControls();
      } catch (failure) { dialogError(failure.message); }
    });
    return button;
  };
  $('apuracao-adicionar-fechar').addEventListener('click', () => { if (!inserting) dialog.close(); });
  dialog.addEventListener('close', () => { ++dialogSequence; pendingInsert = null; });
  dialog.addEventListener('cancel', event => { if (inserting) event.preventDefault(); });
  $('apuracao-adicionar-form').addEventListener('submit', async event => {
    event.preventDefault();
    const captured = pendingInsert;
    if (!captured || inserting) return;
    const target = $('apuracao-destino').value;
    const open = !!target && caseId === captured.scope.caso && current?.id === target;
    // The open note is saved first whatever the destination: the insertion then reopens a note.
    inserting = true; dialogControls(); dialogError(); lockEditing(true);
    try {
      if (current && !(await flush()) && pending()) {
        if (open) throw new Error(t('Não foi possível salvar a nota aberta. Tente de novo antes de inserir o trecho.'));
        if (!(await discard())) throw new Error(t('A nota aberta tem alterações não salvas. Salve ou descarte antes de inserir o trecho.'));
        abandon();
      }
      const revision = open ? current.revisao : captured.notes.find(note => note.id === target)?.revisao;
      const body = {caso:captured.scope.caso, origem:captured.scope, ...(target ? {nota_id:target, revisao_nota:revision} : {})};
      const key = JSON.stringify(body);
      if (captured.key !== key) { captured.key = key; captured.request = uid(); }
      const result = await api('apuracao-nota-inserir', {...body, requisicao_id:captured.request});
      inserting = false; dialog.close();
      if (caseId === captured.scope.caso) { remember(result.nota); await openNote(result.nota_id, {force:current?.id === result.nota_id}); }
      $('experiencia-status').textContent = t('Trecho inserido na nota com suas referências. Continue aqui ou abra o Caderno.');
    } catch (failure) {
      if (failure.result?.codigo === 'conflito') {
        if (open) showConflict();
        dialogError(t('A nota mudou em outra aba. Confira o destino e insira de novo.'));
        try { captured.notes = (await api('apuracao-notas', {caso:captured.scope.caso})).notas; } catch { /* keep the list shown */ }
      } else dialogError(failure.message);
    } finally { inserting = false; if (!offeredDraft) lockEditing(false); dialogControls(); }
  });

  window.addEventListener('beforeunload', event => {
    if (signedOut) return;
    editor.sync?.();
    if (dirty || inflight || retryPayload) { save(); event.preventDefault(); event.returnValue = ''; }
  });
  // Back online: the pending request goes again at once instead of waiting for its interval.
  window.addEventListener('online', () => {
    if (!retryPayload || inflight) return;
    clearTimeout(retryTimer); retryTimer = null; retryDelay = FIRST_RETRY; save();
  });
  // Leaving the page (tab hidden, app sent to background, page discarded): save what is pending.
  function saveOnLeave() { if (signedOut) return; editor.sync?.(); if (dirty && !conflict) save(); }
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') saveOnLeave(); });
  window.addEventListener('pagehide', saveOnLeave);
  window.addEventListener('apuracao-abrir', catalog);
  window.addEventListener('acervo-alterado', () => { if (!$('area-apuracao').hidden) catalog(); });
  window.addEventListener('vlado-idioma', () => { renderList(); renderSources(); renderIndicator(); authorship(current?.nota); taskCount(); });
  // Switching the investigation waits for a save that is running or about to run.
  // The change itself is synchronous for the caller; with unsaved text the answer comes from the dialog, so this returns false and,
  // once the writer confirms, `retomar` repeats the switch.
  window.prepararTrocaApuracao = retomar => {
    editor.sync?.();
    if (inflight || timer) {
      save(); $('experiencia-status').textContent = t('Aguarde o salvamento da nota.'); return false;
    }
    if (pending()) {
      discard().then(ok => { if (ok) { abandon(); retomar?.(); } });
      return false;
    }
    return true;
  };
  controls(); drawerLabels();
})();
