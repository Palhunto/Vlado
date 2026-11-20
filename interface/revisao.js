'use strict';
(() => {
  const dialog = $('revisao-dialogo');
  let session = null, sequence = 0, saving = false, ready = false;
  // "Checked in the original" waits until each cited original was opened in this page. The server
  // checks the same thing (in memory, per page session); keeping an existing mark needs no reopening.
  const openedOriginals = new Set();
  const evidenceKey = (scope, id) => [scope.caso, scope.rodada, scope.revisao, id].join('/');
  function guard() {
    const option = $('revisao-estado').querySelector('[value="conferida_no_original"]');
    const missing = session ? session.evidences.filter(e => !openedOriginals.has(evidenceKey(session.scope, e.id))).length : 0;
    const kept = session?.mark.estado === 'conferida_no_original' && !session.refused;
    option.disabled = !kept && (!session?.sourcesReady || missing > 0);
    $('revisao-guarda').hidden = kept || !session?.sourcesReady || !missing;
    $('revisao-guarda').textContent = `Para marcar “Conferida no original”, abra o original de cada trecho citado (${missing === 1 ? 'falta 1' : `faltam ${missing}`}).`;
  }
  // Excerpts the server still counts as unopened stand out until their original is opened again.
  function markPending(id, pending) {
    const block = $('revisao-fontes').querySelector(`[data-evidencia="${id}"]`);
    if (!block) return;
    block.classList.toggle('review-evidence-pendente', pending);
    block.querySelector('.review-pendente')?.remove();
    if (pending) block.querySelector('h4').after(element('p', 'Abra este original antes de marcar “Conferida no original”.', 'review-pendente'));
  }
  window.registrarOriginalConferido = (scope, evidenceId) => {
    openedOriginals.add(evidenceKey(scope, evidenceId));
    if (session) { markPending(evidenceId, false); guard(); }
  };
  function fail(message = '') {
    $('revisao-erro').textContent = message; $('revisao-erro').hidden = !message;
  }
  function controls() {
    for (const control of $('revisao-form').elements) control.disabled = saving || !ready;
    $('revisao-fechar').disabled = saving;
  }
  function describe() {
    $('revisao-significado').textContent = humanReviewStates[$('revisao-estado').value][1];
    $('revisao-caracteres').textContent = `${$('revisao-observacao').value.length} de 500 caracteres`;
  }
  function history(mark) {
    const list = element('div');
    for (const event of mark.historico || []) {
      const author = event.responsavel ? ' · ' + Leitura.autoria(event.responsavel, event.origem) : '';
      list.append(element('p', `${new Date(event.em_utc).toLocaleString('pt-BR')} · ${humanReviewStates[event.estado][0]}${event.observacao ? ' · ' + event.observacao : ''}${author}`, 'small human-review-note'));
    }
    const pilot = document.body.dataset.modo !== 'local';
    $('revisao-historico').replaceChildren(Leitura.tecnicos(
      element('p', pilot ? 'No piloto, cada marcação leva o nome da conta da Mesa que a registrou.'
        : 'As marcações são declarações registradas pela interface, sem autenticação individual do jornalista.', 'small'),
      list, element('pre', JSON.stringify(mark, null, 2), 'raw-briefing')));
  }
  window.conferirAchado = async (item, scope, version) => {
    if (saving) return;
    const request = ++sequence;
    ready = false; session = null; fail(); controls(); guard();
    $('revisao-afirmacao').textContent = item.redacao;
    $('revisao-fontes').replaceChildren(element('p', 'Abrindo os trechos citados…', 'small'));
    $('revisao-situacao').textContent = 'Carregando a marcação atual e as fontes.';
    $('revisao-historico').replaceChildren();
    $('revisao-estado').value = 'pendente'; $('revisao-observacao').value = ''; describe();
    if (!dialog.open) dialog.showModal();
    try {
      const detail = await api('achados-detalhe', {...scope, achado_id:item.id});
      if (request !== sequence || !dialog.open) return;
      const claim = detail.achado, mark = claim.revisao_humana;
      const evidences = claim.evidencias.filter(e => claim.vinculos.some(link => link.evidencia_id === e.id));
      session = {scope:{...scope}, version, item:claim, mark, hash:detail.registros_sha256, evidences, sourcesReady:false};
      $('revisao-afirmacao').textContent = claim.redacao;
      $('revisao-estado').value = mark.estado; $('revisao-observacao').value = mark.observacao;
      describe(); history(mark);
      $('revisao-fontes').replaceChildren();
      if (!evidences.length) $('revisao-fontes').append(element('p', 'Este achado não tem trechos vinculados nesta revisão. Você pode registrar uma pendência, um ajuste ou suporte insuficiente.', 'notice'));
      const loaded = await Promise.allSettled(evidences.map(async evidence => {
        const block = element('article', undefined, 'review-evidence');
        block.dataset.evidencia = evidence.id;
        const roles = claim.vinculos.filter(link => link.evidencia_id === evidence.id).map(link => pretty(link.papel));
        block.append(element('h4', Leitura.fonte({...evidence, ...evidence.localizador})),
          element('p', roles.join(' · '), 'small'),
          element('blockquote', evidence.trecho || 'Leitura visual registrada; consulte o original.'),
          element('p', evidence.contexto, 'small'));
        const feedback = element('p', '', 'small'); feedback.setAttribute('role', 'status');
        const page = Leitura.pagina(evidence);
        const original = element('button', Leitura.rotuloOriginal(page)); original.type = 'button';
        original.addEventListener('click', async () => {
          original.disabled = true;
          try {
            const blob = await api('achados-original', {...scope, evidencia_id:evidence.id}, true);
            await window.abrirOriginal(blob, evidence.original.split('/').pop(), page, claim.redacao + '\n\n' + (evidence.trecho || 'Fonte visual: confira o original.'));
            window.registrarOriginalConferido(scope, evidence.id);
          } catch (error) { feedback.textContent = error.message; }
          finally { original.disabled = false; }
        });
        block.append(original, feedback); $('revisao-fontes').append(block);
        try {
          const result = await api('achados-evidencia', {...scope, evidencia_id:evidence.id});
          if (result.contexto) {
            const context = element('details', undefined, 'review-context');
            const text = element('div', undefined, 'context');
            for (const line of result.contexto) text.append(element('p', line.texto));
            context.append(element('summary', 'Ler contexto da fonte'), text); block.append(context);
          } else block.append(element('p', 'Fonte visual: confira a página no original.', 'small'));
          block.append(Leitura.tecnicos(element('pre', JSON.stringify(result.evidencia, null, 2), 'raw-briefing')));
        } catch (error) {
          block.append(element('p', `Não foi possível recuperar esta fonte: ${error.message}`, 'notice'));
          throw error;
        }
      }));
      if (request !== sequence || !dialog.open) return;
      ready = true; controls();
      session.sourcesReady = evidences.length > 0 && loaded.every(result => result.status === 'fulfilled');
      guard();
      $('revisao-situacao').textContent = 'A marcação vale para este achado, nesta revisão. O texto da IA será preservado.';
    } catch (error) {
      if (request === sequence && dialog.open) { fail(error.message); $('revisao-situacao').textContent = 'Não foi possível abrir a conferência.'; }
    }
  };
  $('revisao-estado').addEventListener('change', describe);
  $('revisao-observacao').addEventListener('input', describe);
  $('revisao-fechar').addEventListener('click', () => { if (!saving) dialog.close(); });
  dialog.addEventListener('cancel', event => { if (saving) event.preventDefault(); });
  dialog.addEventListener('close', () => { ++sequence; session = null; ready = false; guard(); });
  $('revisao-form').addEventListener('submit', async event => {
    event.preventDefault(); if (!session || !ready || saving) return;
    const captured = session;
    saving = true; controls(); fail(); $('revisao-situacao').textContent = 'Salvando sua marcação…';
    try {
      const result = await api('achados-revisao-salvar', {...captured.scope,
        achado_id:captured.item.id, achado_versao:captured.item.versao,
        registros_sha256:captured.hash, anterior:captured.mark.evento_id,
        estado:$('revisao-estado').value, observacao:$('revisao-observacao').value});
      dialog.close();
      // Marks belong to case/round/revision (any index generation). Refresh the list, its badges and the
      // "N of M reviewed" counter even when the dialog was opened from the briefing, a conversation or an
      // older listing; a list that is not on screen is refreshed the next time Achados opens.
      const current = findingQuery;
      const saved = `Marcação salva: ${humanReviewStates[result.revisao_humana.estado][0]}. O texto original da IA foi preservado.`;
      if (current && ['caso','rodada','revisao'].every(key => current[key] === captured.scope[key])) {
        await searchFindings({...current});
      } else {
        window.achadosDesatualizados = true;
      }
      $('achados-revisao-feedback').textContent = saved;
    } catch (error) {
      fail(error.message); $('revisao-situacao').textContent = 'A marcação não foi confirmada. Sua observação continua no formulário.';
      if (error.result?.codigo === 'conferencia_sem_original' && session === captured) {
        captured.refused = true;
        for (const id of error.result.faltam || []) { openedOriginals.delete(evidenceKey(captured.scope, id)); markPending(id, true); }
        $('revisao-fontes').querySelector('.review-evidence-pendente')?.scrollIntoView({block:'nearest'});
      }
    } finally { saving = false; controls(); guard(); }
  });
  $('achados-marcacao').addEventListener('change', () => {
    $('achados-so-pendentes').setAttribute('aria-pressed', String($('achados-marcacao').value === 'pendente'));
    if ($('achados-geracao').value) searchFindings({...findingScope(), filtros:findingFilters(), limite:Number($('achados-limite').value), deslocamento:0});
  });
  $('achados-so-pendentes').addEventListener('click', () => {
    $('achados-marcacao').value = $('achados-marcacao').value === 'pendente' ? '' : 'pendente';
    $('achados-marcacao').dispatchEvent(new Event('change'));
  });
})();
