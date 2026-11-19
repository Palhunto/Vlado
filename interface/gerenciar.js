'use strict';
(() => {
  const labels = {caso:'Apuração', conversa:'Conversa', rodada:'Rodada'};
  const running = new Set(['preparando','executando','aguardando_aprovacao','cancelando','publicando']);
  // Server categories of a permanent delete; unknown ones keep their raw name.
  const categories = {originais:'Originais recebidos', derivados:'Textos extraídos dos originais', corpus:'Cadastro e versões do acervo',
    rodadas:'Rodadas de análise', indice_documental:'Índice da busca documental', indice_achados:'Índice dos achados',
    registros_achados:'Registros dos achados', revisoes_humanas:'Conferências humanas', conversas:'Conversas',
    caderno:'Trechos com fonte', diligencias:'Diligências', notas:'Notas do caderno',
    quadros_evidencia:'Quadros de evidência', fontes_web:'Fontes web capturadas', rascunhos:'Rascunhos'};
  const admin = document.body.dataset.papel !== 'convidado';
  const t = (text, vars) => window.I18N ? window.I18N.t(text, vars) : text;
  let data = null, sequence = 0, busy = false;
  function fail(message = '') {
    $('gerenciar-erro').textContent = message;
    $('gerenciar-erro').hidden = !message;
  }
  function controls() {
    for (const control of $('area-gerenciar').querySelectorAll('button, select')) {
      control.disabled = busy || control.dataset.blocked === 'true';
    }
  }
  // actions: [{text, kind, run, blocked}]
  function row(title, description, actions, metadata = null) {
    const item = element('li'), text = element('div');
    text.append(element('h4', title), element('p', description, 'small'));
    if (metadata) text.append(Leitura.tecnicos(element('pre', JSON.stringify(metadata, null, 2), 'raw-briefing')));
    const buttons = element('div', undefined, 'manage-actions');
    for (const action of actions) {
      const button = element('button', action.text, action.kind);
      button.type = 'button'; button.disabled = !!action.blocked || busy;
      button.dataset.blocked = String(!!action.blocked);
      button.setAttribute('aria-label', `${action.text} ${title}`);
      button.addEventListener('click', async () => {
        try { await action.run(button); } catch (error) { fail(error.message); }
      });
      buttons.append(button);
    }
    item.append(text, buttons);
    return item;
  }
  function emptyList(id, message) {
    if (!$(id).children.length) $(id).append(element('li', message, 'manage-empty'));
  }
  function trashTitle(item) {
    return item.tipo === 'rodada' ? `Rodada ${parseInt(item.rodada.slice(1), 10)}` : `${labels[item.tipo]} · ${item.titulo}`;
  }
  function render() {
    const selected = data.casos.find(c => c.id === $('gerenciar-caso').value);
    $('gerenciar-selecao').hidden = !selected;
    $('gerenciar-conversas').replaceChildren(); $('gerenciar-rodadas').replaceChildren();
    if (selected) {
      $('gerenciar-nome').textContent = selected.titulo;
      $('gerenciar-resumo').textContent = `${Leitura.quantidade(data.conversas.length, 'conversa')} · ${Leitura.quantidade(selected.rodadas.length, 'rodada')}`;
      $('gerenciar-tecnicos').replaceChildren(Leitura.tecnicos(`Identificador: ${selected.id}`));
      const active = data.conversas.some(c => running.has(c.estado));
      $('gerenciar-excluir-caso').dataset.blocked = String(active);
      $('gerenciar-excluir-caso').title = active ? 'Aguarde o encerramento das execuções deste caso.' : '';
      for (const chat of data.conversas) {
        const rounds = chat.rodadas || [], blocked = running.has(chat.estado);
        $('gerenciar-conversas').append(row(chat.titulo,
          `${Leitura.quantidade(rounds.length, 'rodada')}${blocked ? ' · Execução em andamento' : ''}`,
          [{text:'Excluir', kind:'danger', blocked, run:() => window.excluirItem({tipo:'conversa', caso:selected.id, conversa:chat.id}, chat.titulo)}], chat));
      }
      const owned = new Set(data.conversas.flatMap(c => c.rodadas || []));
      for (const round of selected.rodadas.filter(r => !owned.has(r.id))) {
        const title = `Rodada ${parseInt(round.id.slice(1), 10)}`;
        $('gerenciar-rodadas').append(row(title, selected.titulo,
          [{text:'Excluir', kind:'danger', blocked:active, run:() => window.excluirItem({tipo:'rodada', caso:selected.id, rodada:round.id}, title)}], round));
      }
      emptyList('gerenciar-conversas', 'Nenhuma conversa nesta apuração.');
      emptyList('gerenciar-rodadas', 'Nenhuma análise avulsa nesta apuração.');
    }
    $('gerenciar-lixeira').replaceChildren();
    $('lixeira-contagem').textContent = `${data.lixeira.length} ${data.lixeira.length === 1 ? 'item' : 'itens'}`;
    for (const item of [...data.lixeira].reverse()) {
      const date = new Date(item.excluido_em_utc).toLocaleString('pt-BR');
      const blocked = item.tipo !== 'caso' && data.lixeira.some(i => i.tipo === 'caso' && i.caso === item.caso);
      const title = trashTitle(item);
      const caseTitle = data.casos.find(c => c.id === item.caso)?.titulo || data.lixeira.find(c => c.tipo === 'caso' && c.caso === item.caso)?.titulo || 'Apuração preservada';
      const actions = [{text:'Restaurar', kind:'secondary', blocked, run:() => mutate('restaurar', {item:item.id})}];
      if (admin) actions.push({text:'Apagar definitivamente…', kind:'danger', run:button => openDelete(item, title, button)});
      $('gerenciar-lixeira').append(row(title,
        `${caseTitle} · Excluído em ${date}${blocked ? ' · Restaure a apuração primeiro' : ''}`, actions, item));
    }
    emptyList('gerenciar-lixeira', 'A lixeira está vazia.');
    controls();
  }
  async function load() {
    const version = ++sequence, selected = window.contextoCaso?.() ?? $('gerenciar-caso').value;
    fail();
    try {
      const result = await api('gerenciar-listar', {caso:selected || null});
      if (version !== sequence) return;
      data = result;
      $('gerenciar-caso').replaceChildren(new Option('Selecione uma apuração', ''),
        ...data.casos.map(c => new Option(c.titulo, c.id)));
      if (data.casos.some(c => c.id === selected)) $('gerenciar-caso').value = selected;
      render();
    } catch (error) { if (version === sequence) fail(error.message); }
  }
  async function mutate(operation, scope) {
    if (busy) return false;
    busy = true; controls(); fail();
    try {
      const result = await api(operation, scope);
      $('gerenciar-status').textContent = result.estado === 'restaurado'
        ? `${labels[result.item.tipo]} restaurada: ${result.item.titulo}.`
        : `${labels[result.item.tipo]} movida para a lixeira: ${result.item.titulo}.`;
      window.dispatchEvent(new CustomEvent('acervo-alterado', {detail:result}));
      await load();
      return true;
    } finally { busy = false; controls(); }
  }

  // Permanent delete: show the server's scope, require the exact name, send its token.
  const deleteDialog = $('apagar-dialogo');
  let pending = null;
  const locale = () => (window.I18N?.idioma?.() === 'en' ? 'en' : 'pt-BR');
  const number = (value, digits = 0) => new Intl.NumberFormat(locale(), {minimumFractionDigits:digits, maximumFractionDigits:digits}).format(value);
  function size(bytes) {
    if (bytes < 1024) return `${number(bytes)} B`;
    if (bytes < 1024 ** 2) return `${number(Math.round(bytes / 1024))} KB`;
    if (bytes < 1024 ** 3) return `${number(bytes / 1024 ** 2, 1)} MB`;
    return `${number(bytes / 1024 ** 3, 1)} GB`;
  }
  const files = count => count === 1 ? t('1 arquivo') : t('{n} arquivos', {n:number(count)});
  // Python's casefold() after strip(), as the server compares it.
  const comparable = value => String(value ?? '').trim().toUpperCase().toLowerCase();
  function deleteError(message = '') {
    $('apagar-erro').textContent = message ? t(message) : '';
    $('apagar-erro').hidden = !message;
  }
  function deleteControls() {
    const working = !pending || pending.busy;
    const ready = !!pending?.scope && !working;
    $('apagar-nome').disabled = !ready;
    $('apagar-cancelar').disabled = !!pending?.busy;
    $('apagar-confirmar').disabled = !ready || comparable($('apagar-nome').value) !== comparable(pending.scope.nome_para_confirmar);
    $('apagar-confirmar').textContent = pending?.busy ? t('Apagando…') : t('Apagar definitivamente');
  }
  function renderScope(scope) {
    $('apagar-categorias').replaceChildren(...Object.entries(scope.categorias).map(([name, info]) => {
      const line = element('tr'), label = element('th', t(categories[name] || name));
      label.scope = 'row'; line.append(label, element('td', number(info.arquivos)), element('td', size(info.bytes)));
      return line;
    }));
    $('apagar-total').textContent = `${files(scope.totais.arquivos)}, ${size(scope.totais.bytes)}`;
    const kept = scope.rodadas_preservadas || [];
    $('apagar-preservadas').textContent = kept.length ? t('Estas rodadas continuam porque são usadas por outras conversas: {rodadas}', {rodadas:kept.join(', ')}) : '';
    $('apagar-preservadas').hidden = !kept.length;
    $('apagar-backup').textContent = t(scope.aviso_backup || '');
    $('apagar-backup').hidden = !scope.aviso_backup;
    const [before, after] = t('Digite «{nome}» para confirmar').split('{nome}');
    const name = element('strong', scope.nome_para_confirmar); name.setAttribute('translate', 'no');
    $('apagar-nome-rotulo').replaceChildren(before, name, after ?? '');
    $('apagar-nome').value = '';
    $('apagar-alcance').hidden = false;
  }
  async function loadScope() {
    const captured = pending;
    captured.scope = null; captured.ticket = (captured.ticket || 0) + 1;
    const ticket = captured.ticket;
    $('apagar-alcance').hidden = true;
    $('apagar-status').textContent = t('Calculando o que será apagado…');
    deleteControls();
    try {
      const scope = await api('lixeira-alcance', {item:captured.item.id});
      if (pending !== captured || ticket !== captured.ticket) return;
      captured.scope = scope; renderScope(scope);
      $('apagar-status').textContent = '';
    } catch (error) {
      if (pending !== captured || ticket !== captured.ticket) return;
      $('apagar-status').textContent = ''; deleteError(error.message);
    } finally { if (pending === captured) deleteControls(); }
  }
  // The item type is interface text; its title or round id is data.
  function renderItem(item) {
    const name = element('span', item.tipo === 'rodada' ? item.rodada : item.titulo);
    name.setAttribute('translate', 'no');
    $('apagar-item').replaceChildren(t(labels[item.tipo]), ' · ', name);
  }
  async function openDelete(item, title, opener) {
    if (busy || deleteDialog.open) return;
    pending = {item, title, opener, scope:null, busy:false};
    renderItem(item);
    deleteError(); $('apagar-nome').value = '';
    deleteControls();
    deleteDialog.showModal();
    $('apagar-cancelar').focus();
    await loadScope();
  }
  async function confirmDelete() {
    const captured = pending;
    if (!captured?.scope || captured.busy || $('apagar-confirmar').disabled) return;
    captured.busy = true; deleteError(); deleteControls();
    try {
      const result = await api('lixeira-apagar', {item:captured.item.id, nome:$('apagar-nome').value, confirmacao:captured.scope.confirmacao});
      captured.busy = false;
      deleteDialog.close();
      const totals = result.totais || captured.scope.totais;
      $('gerenciar-status').textContent = t('Apagado definitivamente: {arquivos} ({tamanho}).', {arquivos:files(totals.arquivos), tamanho:size(totals.bytes)});
      window.dispatchEvent(new CustomEvent('acervo-alterado', {detail:result}));
      await load();
    } catch (error) {
      captured.busy = false;
      if (pending !== captured) return;
      // Stable code from the server (8f03d9c); the PT text is only a fallback for older servers.
      if (error.result?.codigo === 'alcance_alterado' || /mudou desde a conferência/.test(error.result?.erro || '')) {
        deleteError('O conteúdo mudou desde a conferência. Confira o alcance atualizado e digite o nome de novo.');
        await loadScope();
      } else { deleteError(error.message); deleteControls(); }
    }
  }
  $('apagar-nome').addEventListener('input', deleteControls);
  $('apagar-nome').addEventListener('keydown', event => { if (event.key === 'Enter') { event.preventDefault(); confirmDelete(); } });
  $('apagar-confirmar').addEventListener('click', confirmDelete);
  $('apagar-cancelar').addEventListener('click', () => { if (!pending?.busy) deleteDialog.close(); });
  deleteDialog.addEventListener('cancel', event => { if (pending?.busy) event.preventDefault(); });
  deleteDialog.addEventListener('close', () => {
    const opener = pending?.opener; pending = null;
    if (opener?.isConnected) opener.focus();
  });
  // List rows are Portuguese text the i18n observer translates; only the dialog builds translated text.
  window.addEventListener('vlado-idioma', () => {
    if (pending) { renderItem(pending.item); deleteControls(); if (pending.scope) { const typed = $('apagar-nome').value; renderScope(pending.scope); $('apagar-nome').value = typed; deleteControls(); } }
  });

  window.excluirItem = async (scope, title) => {
    const dialog = $('excluir-dialogo');
    if (dialog.open || busy) return false;
    $('excluir-titulo').textContent = `Excluir ${labels[scope.tipo].toLowerCase()}?`;
    const effect = scope.tipo === 'caso' ? 'A apuração, suas conversas e rodadas sairão das listas.'
      : scope.tipo === 'conversa' ? 'A conversa, suas perguntas complementares e rodadas sairão das listas.'
      : 'Esta rodada e seus achados sairão das consultas.';
    $('excluir-descricao').textContent = `“${title}” — ${effect}`;
    dialog.returnValue = '';
    const answer = new Promise(resolve => dialog.addEventListener('close', () => resolve(dialog.returnValue), {once:true}));
    dialog.showModal();
    if (await answer !== 'excluir') return false;
    return mutate('excluir', scope);
  };
  $('gerenciar-excluir-caso').addEventListener('click', async () => {
    const selected = data?.casos.find(c => c.id === $('gerenciar-caso').value);
    if (!selected) return;
    try { await window.excluirItem({tipo:'caso', caso:selected.id}, selected.titulo); }
    catch (error) { fail(error.message); }
  });
  $('gerenciar-atualizar').addEventListener('click', load);
  $('gerenciar-caso').addEventListener('change', () => {
    // Do not leave actions for the previous case available during the request.
    $('gerenciar-selecao').hidden = true;
    load();
  });
  window.addEventListener('gerenciar-abrir', load);
})();
