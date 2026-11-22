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
          [{text:'Excluir', kind:'danger', blocked, run:button => window.excluirItem({tipo:'conversa', caso:selected.id, conversa:chat.id}, chat.titulo, button)}], chat));
      }
      const owned = new Set(data.conversas.flatMap(c => c.rodadas || []));
      for (const round of selected.rodadas.filter(r => !owned.has(r.id))) {
        const title = `Rodada ${parseInt(round.id.slice(1), 10)}`;
        $('gerenciar-rodadas').append(row(title, selected.titulo,
          [{text:'Excluir', kind:'danger', blocked:active, run:button => window.excluirItem({tipo:'rodada', caso:selected.id, rodada:round.id}, title, button)}], round));
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

  // Permanent delete (Dialogo, variante com campo, modo executar): shows the server's scope, requires the exact name, sends its token.
  // The server answers fast and removes the files in the background, so the wait is short and cannot be cancelled.
  let deleting = false;
  const locale = () => (window.I18N?.idioma?.() === 'en' ? 'en' : 'pt-BR');
  const number = (value, digits = 0) => new Intl.NumberFormat(locale(), {minimumFractionDigits:digits, maximumFractionDigits:digits}).format(value);
  function size(bytes) {
    // No-break space: the number and its unit never split across lines.
    if (bytes < 1024) return `${number(bytes)}\u00a0B`;
    if (bytes < 1024 ** 2) return `${number(Math.round(bytes / 1024))}\u00a0KB`;
    if (bytes < 1024 ** 3) return `${number(bytes / 1024 ** 2, 1)}\u00a0MB`;
    return `${number(bytes / 1024 ** 3, 1)}\u00a0GB`;
  }
  const files = count => (count === 1 ? t('1 arquivo') : t('{n} arquivos', {n:number(count)})).replace(' ', '\u00a0');
  // What leaves the project: a table by category with the total, the rounds kept for other conversations and the backup notice.
  function scopeNodes(scope) {
    const table = element('table', undefined, 'dialogo-tabela');
    table.append(element('caption', t('O que será apagado'), 'sr-only'));
    const head = element('thead'), headRow = element('tr');
    for (const title of ['Categoria', 'Arquivos', 'Tamanho']) { const th = element('th', t(title)); th.scope = 'col'; headRow.append(th); }
    head.append(headRow);
    const body = element('tbody');
    for (const [name, info] of Object.entries(scope.categorias)) {
      const line = element('tr'), label = element('th', t(categories[name] || name));
      label.scope = 'row'; line.append(label, element('td', number(info.arquivos)), element('td', size(info.bytes)));
      body.append(line);
    }
    const foot = element('tfoot'), total = element('tr'), totalLabel = element('th', t('Total')), totalValue = element('td', `${files(scope.totais.arquivos)}, ${size(scope.totais.bytes)}`);
    totalLabel.scope = 'row'; totalValue.colSpan = 2; total.append(totalLabel, totalValue); foot.append(total);
    table.append(head, body, foot);
    const nodes = [table], kept = scope.rodadas_preservadas || [];
    if (kept.length) nodes.push(element('p', t('Estas rodadas continuam porque são usadas por outras conversas: {rodadas}', {rodadas:kept.join(', ')}), 'dialogo-nota'));
    if (scope.aviso_backup) nodes.push(element('p', t(scope.aviso_backup), 'dialogo-nota'));
    return nodes;
  }
  async function openDelete(item, title, opener) {
    if (busy || deleting) return;
    deleting = true;
    let scope = null, failed = false, result = null;
    const loadScope = async ctx => {
      scope = null; ctx.nome(null); ctx.corpo.replaceChildren(); ctx.estado('Calculando o que será apagado…');
      try {
        const found = await api('lixeira-alcance', {item:item.id});
        if (ctx.fechou()) return;
        scope = found; ctx.corpo.replaceChildren(...scopeNodes(found)); ctx.estado(''); ctx.nome(found.nome_para_confirmar);
      } catch (error) { if (ctx.fechou()) return; ctx.estado(''); ctx.erro(error.message); }
    };
    try {
      const deleted = await window.Dialogo.confirmar({
        variante:'campo', titulo:'Apagar definitivamente', linha:[labels[item.tipo], item.tipo === 'rodada' ? item.rodada : item.titulo],
        texto:'Os arquivos listados saem do projeto. A Mesa não consegue recuperá-los depois.',
        acao:'Apagar definitivamente', ocupado:'Apagando…', gatilho:opener,
        preparar:loadScope,
        aoIdioma:ctx => { if (scope) ctx.corpo.replaceChildren(...scopeNodes(scope)); },
        executar:async ctx => {
          try { result = await api('lixeira-apagar', {item:item.id, nome:ctx.valor(), confirmacao:scope.confirmacao}); }
          catch (error) {
            failed = true;
            // Stable code from the server (8f03d9c); the PT text is only a fallback for older servers.
            if (error.result?.codigo === 'alcance_alterado' || /mudou desde a conferência/.test(error.result?.erro || '')) {
              ctx.limparCampo(); await loadScope(ctx);
              throw new Error('O conteúdo mudou desde a conferência. Confira o alcance atualizado e digite o nome de novo.');
            }
            throw error;   // any other refusal stays in the dialog, with the server's own text
          }
        },
      });
      if (deleted) {
        const totals = result.totais || scope.totais;
        $('gerenciar-status').textContent = [t('Apagado definitivamente: {arquivos} ({tamanho}).', {arquivos:files(totals.arquivos), tamanho:size(totals.bytes)}),
          result.aviso_backup ? t(result.aviso_backup) : ''].filter(Boolean).join(' ');
        window.dispatchEvent(new CustomEvent('acervo-alterado', {detail:result}));
        await load();
      } else if (failed) await load();   // a refusal may have changed what is in the trash
    } finally { deleting = false; }
  }

  // Move to the trash (Dialogo, destructive variant, executar mode): the answer of the server stays in the dialog if it refuses.
  let moving = false;
  window.excluirItem = async (scope, title, opener) => {
    if (busy || moving) return false;
    moving = true;
    let failed = false;
    const effect = scope.tipo === 'caso' ? 'A apuração, suas conversas e rodadas sairão das listas.'
      : scope.tipo === 'conversa' ? 'A conversa, suas perguntas complementares e rodadas sairão das listas.'
      : 'Esta rodada e seus achados sairão das consultas.';
    try {
      const moved = await window.Dialogo.confirmar({
        variante:'destrutivo', rubrica:'Mover para a lixeira', titulo:'Mover {item} para a lixeira?', item:title, texto:effect,
        nota:'Você poderá restaurar em Apurações e lixeira. Documentos e registros serão preservados.',
        acao:'Mover para a lixeira', ocupado:'Movendo…', gatilho:opener,
        executar:async () => {
          try { if (!await mutate('excluir', scope)) throw new Error('Há outra operação em andamento. Aguarde e tente de novo.'); }
          catch (error) { failed = true; throw error; }
        },
      });
      if (!moved && failed) await load();   // a refusal may have changed what is on the lists
      return moved;
    } finally { moving = false; }
  };
  $('gerenciar-excluir-caso').addEventListener('click', async () => {
    const selected = data?.casos.find(c => c.id === $('gerenciar-caso').value);
    if (!selected) return;
    try { await window.excluirItem({tipo:'caso', caso:selected.id}, selected.titulo, $('gerenciar-excluir-caso')); }
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
