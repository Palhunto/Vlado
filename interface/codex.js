'use strict';
(() => {
  let conversation = '', cursor = 0, view = 0, active = false, submitting = false;
  let inventoryVersion = 0, catalogVersion = 0, sourceMap = new Map(), messageMap = new Map();
  const sourceChats = new Map();
  let conversationList = [];
  let currentStage = '';
  let currentGroup = null, currentRound = '', liveInventory = null, authenticated = null;
  let pendingFeedback = null;
  let pendingCorpus = null;
  let pendingNotebook = null;
  let pendingDiligences = null;
  const groups = new Map(), frozenInventories = new Map();
  const drafts = new Map();
  let draftContext = {caso:'', conversa:''}, trackingFailed = false, trackingPending = false;
  const draftKey = context => JSON.stringify([context.caso, context.conversa]);
  // Durable copy of the question in preparation (localStorage + server), see continuidade.js.
  let rascunhoPergunta = null;
  function saveDraft() {
    if (!draftContext.caso) return;
    const text = $('codex-pergunta').value;
    if (text) drafts.set(draftKey(draftContext), text);
    else drafts.delete(draftKey(draftContext));
  }
  function switchDraft(caso, conversa) {
    saveDraft();
    draftContext = {caso, conversa};
    $('codex-pergunta').value = drafts.get(draftKey(draftContext)) || '';
    destination();
    rascunhoPergunta?.abrir();
  }
  rascunhoPergunta = window.Rascunhos?.registrar({origem: $('codex-pergunta'), ancora: $('codex-pergunta').closest('label'),
    alvo: () => draftContext.caso ? {caso: draftContext.caso, tela: draftContext.conversa ? `pergunta/${draftContext.conversa}` : 'pergunta'} : null,
    ler: () => ({pergunta: $('codex-pergunta').value}),
    aplicar: conteudo => { $('codex-pergunta').value = typeof conteudo.pergunta === 'string' ? conteudo.pergunta : ''; saveDraft(); }});
  function destination() {
    const title = $('codex-caso').selectedOptions[0]?.textContent;
    const selected = [...$('codex-conversa').options].find(option => option.value === conversation);
    const chat = conversation ? selected?.dataset.titulo || selected?.textContent || conversation : '';
    const message = draftContext.caso ? `Destino da pergunta: ${title || draftContext.caso} · ${chat || 'Nova conversa'}` : 'Escolha uma apuração para escrever a pergunta.';
    if ($('codex-destino').dataset.mensagem === message) return;
    $('codex-destino').dataset.mensagem = message;
    if (!draftContext.caso) { $('codex-destino').textContent = message; return; }
    // Label and "New conversation" are chrome; case and conversation titles are data.
    const data = text => { const span = element('span', text); span.setAttribute('translate', 'no'); return span; };
    $('codex-destino').replaceChildren(element('span', 'Destino da pergunta: '), data(title || draftContext.caso),
      element('span', ' · '), chat ? data(chat) : element('span', 'Nova conversa'));
  }
  // Composite progress lines mix a run state with a stage; both words are translated as they are written.
  const t = (text, vars) => window.I18N ? window.I18N.t(text, vars)
    : Object.entries(vars || {}).reduce((result, [name, value]) => result.split(`{${name}}`).join(String(value)), text);
  const stageLabels = {inventario:'Conferindo o acervo',plano:'Planejando',busca:'Buscando e lendo fontes',
    geracao_inicial:'Registrando a geração inicial',revisao:'Revisando o suporte',sintese:'Preparando a síntese',comparacao:'Comparando com a análise anterior'};
  const busyStates = new Set(['preparando','executando','aguardando_aprovacao','cancelando','publicando']);
  const names = {preparando:'Preparando os documentos e a busca', executando:'IA trabalhando',
    aguardando_aprovacao:'Aguardando sua resposta', cancelando:'Cancelamento solicitado',
    concluido:'Execução concluída', interrompido:'Execução interrompida · saídas parciais preservadas',
    erro:'Execução com erro · confira a mensagem', pronto:'Pronto'};
  names.publicando = 'Publicando e verificando os achados';
  names.incompleto = 'Fluxo incompleto · saídas preservadas, publicação final não confirmada';
  // Run status of the selected conversation: badge, the question's stages and "Tentar novamente".
  const badges = {em_andamento:'Em execução', cancelando:'Cancelando…', concluido:'Concluída', cancelado:'Cancelada por você',
    sem_cota:'Limite de uso atingido', interrompido:'Interrompida', erro:'Falhou', incompleto:'Incompleta'};
  const stageNames = {inventario:'Inventário do acervo', plano:'Plano da apuração', busca:'Busca e leitura das fontes',
    geracao_inicial:'Geração inicial dos achados', revisao:'Revisão do suporte', sintese:'Síntese',
    comparacao:'Comparação com a análise anterior', publicacao:'Publicação'};
  const stepStates = {aceita:'aceita', proxima:'próxima', pendente:'pendente'};
  const guest = () => document.body?.dataset.papel === 'convidado';
  let run = null, retrying = false, resumed = null;
  // Network loss while following a run: the server keeps executing; the poll retries with
  // backoff (or as soon as the browser is back online) from the same cursor.
  const RECONNECT_MS = [1000, 2000, 4000, 8000, 15000, 30000];
  let reconnecting = false, wake = null;
  const offline = () => typeof navigator !== 'undefined' && navigator.onLine === false;
  window.addEventListener('online', () => wake?.());
  window.addEventListener('offline', () => {
    if (!reconnecting) return;
    $('codex-status').textContent = connectionTexts.offline;
    controls();
  });
  function pause(ms) {
    return new Promise(resolve => {
      const done = () => { clearTimeout(timer); if (wake === done) wake = null; resolve(); };
      const timer = setTimeout(done, ms);
      wake = done;
    });
  }
  const connectionTexts = {
    rede: 'Conexão perdida — a execução continua no servidor; reconectando…',
    offline: 'Sem conexão neste aparelho — a execução continua no servidor; reconectando quando a rede voltar…',
    andamento: 'Em andamento — acompanhando a execução.',
    retomavel: 'Interrompida — retomar com o botão abaixo.'};
  function connection(current) {
    const line = $('codex-conexao-estado');
    if (!line) return;
    const running = current && ['em_andamento', 'cancelando'].includes(current.codigo);
    const mode = !current ? '' : reconnecting ? (offline() ? 'offline' : 'rede') : running ? 'andamento'
      : run?.retomavel === true && current.causa !== 'contexto' ? 'retomavel' : '';
    if (line.dataset.conexao === mode) return;
    line.dataset.conexao = mode;
    $('codex-execucao').dataset.conexao = mode;
    // Always rendered (an empty line has no height) so screen readers announce changes; the
    // routine "in progress" state is shown without being announced again.
    line.setAttribute('aria-live', mode === 'andamento' ? 'off' : 'polite');
    line.textContent = mode ? connectionTexts[mode] : '';
  }
  // Conversations saved before `situacao` existed carry only `estado`.
  function situation(record) {
    if (record?.situacao?.codigo) return record.situacao;
    const code = {concluido:'concluido', erro:'erro', interrompido:'interrompido', incompleto:'incompleto', cancelando:'cancelando'}[record?.estado]
      || (busyStates.has(record?.estado) ? 'em_andamento' : null);
    return code ? {codigo:code, mensagem:'', causa:null} : null;
  }
  function badge(record) {
    const current = situation(record);
    return current ? t(badges[current.codigo] || current.codigo) : t(names[record?.estado] || record?.estado || '');
  }
  function causeHint(current) {
    if (current.causa === 'reinicio') return t('Causa: o servidor foi reiniciado.');
    if (current.causa === 'contexto') return t('Abra uma nova conversa para continuar.');
    if (current.causa === 'autenticacao') return guest() ? t('A API recusou a chave. Avise a administração.')
      : t('Confira a chave da API em Conexão e opções antes de tentar de novo.');
    if (current.codigo === 'sem_cota' && ['limite_consulta', 'limite_dia'].includes(current.causa)) {
      return t('A nova tentativa pode ser recusada até o limite ser ajustado ou até o dia seguinte (UTC).');
    }
    return '';
  }
  const stageName = stage => t(stageNames[stage] || stage);
  function resumeText(data) {
    return data.etapa === 'publicacao' ? t('Retomada na publicação final.')
      : t('Retomada da etapa {numero} de {total}: {etapa}.', {numero:data.numero, total:data.total, etapa:stageName(data.etapa)});
  }
  function runSteps(progress) {
    const list = $('codex-execucao-etapas');
    list.hidden = !progress?.etapas?.length;
    list.replaceChildren(...(progress?.etapas || []).map(stage => {
      const status = progress.aceitas.includes(stage) ? 'aceita' : stage === progress.proxima ? 'proxima' : 'pendente';
      const item = element('li', undefined, 'run-step');
      item.dataset.estado = status;
      const mark = element('span', undefined, 'run-step-mark'); mark.setAttribute('aria-hidden', 'true');
      item.append(mark, element('span', stageName(stage), 'run-step-name'), element('span', ` (${t(stepStates[status])})`, 'sr-only'));
      return item;
    }));
  }
  function runBlock() {
    const current = conversation ? situation(run) : null;
    $('codex-execucao').hidden = !current || current.codigo === 'concluido';
    connection($('codex-execucao').hidden ? null : current);
    if ($('codex-execucao').hidden) return;
    $('codex-execucao-selo').textContent = t(badges[current.codigo] || current.codigo);
    $('codex-execucao-selo').className = 'run-badge run-' + current.codigo;
    const question = run.pergunta_atual || conversationList.find(c => c.id === conversation)?.pergunta;
    $('codex-execucao-pergunta').textContent = question || t('Execução desta conversa');
    $('codex-execucao-pergunta').setAttribute('translate', question ? 'no' : 'yes');
    $('codex-execucao-mensagem').textContent = current.mensagem ? t(current.mensagem) : '';
    $('codex-execucao-mensagem').hidden = !current.mensagem;
    const hint = causeHint(current);
    $('codex-execucao-causa').textContent = hint; $('codex-execucao-causa').hidden = !hint;
    runSteps(run.progresso);
    const running = ['em_andamento', 'cancelando'].includes(current.codigo);
    $('codex-execucao-aviso').textContent = running && resumed ? resumeText(resumed) : '';
    $('codex-execucao-aviso').hidden = !(running && resumed);
    const idle = !active && !submitting && !trackingPending && !trackingFailed && !reconnecting;
    const button = $('codex-retomar'), next = run.progresso ? run.progresso.proxima : undefined;
    button.hidden = run.retomavel !== true || current.causa === 'contexto' || !(idle || retrying);
    button.disabled = retrying;
    button.textContent = retrying ? t('Retomando…') : next === null ? t('Concluir publicação')
      : next ? t('Tentar novamente a partir de «{etapa}»', {etapa:stageName(next)}) : t('Tentar novamente');
    $('codex-retomar-cota').hidden = button.hidden || !guest();
  }
  function fail(message = '') {
    $('codex-erro').textContent = message;
    $('codex-erro').hidden = !message;
  }
  function controls() {
    const blocked = active || submitting || trackingPending || retrying || reconnecting;
    $('codex-enviar').disabled = blocked || trackingFailed || !$('codex-caso').value;
    $('codex-pergunta').disabled = submitting || !$('codex-caso').value;
    $('codex-cancelar').disabled = !conversation || !(active || trackingFailed || trackingPending);
    $('codex-reconectar').hidden = !trackingFailed;
    $('codex-reconectar').disabled = trackingPending || submitting || !conversation;
    $('codex-reconectar').textContent = trackingPending ? 'Reconectando acompanhamento…' : 'Reconectar acompanhamento';
    $('codex-caso').disabled = blocked;
    $('codex-conversa').disabled = blocked;
    $('codex-nova').disabled = blocked;
    $('codex-atualizar').disabled = blocked;
    $('codex-excluir').disabled = blocked || trackingFailed || !conversation;
    $('codex-observacoes-remover').disabled = blocked || trackingFailed;
    $('codex-continuar-documentos').disabled = blocked || trackingFailed || !conversation;
    $('codex-corpus-retirar').disabled = blocked || trackingFailed;
    $('codex-caderno-retirar').disabled = blocked || trackingFailed;
    $('codex-diligencias-retirar').disabled = blocked || trackingFailed;
    destination();
    runBlock();
  }
  function feedbackPreview() {
    $('codex-observacoes').hidden = !pendingFeedback;
    $('codex-observacoes-lista').replaceChildren();
    if (pendingFeedback) window.mostrarObservacoes($('codex-observacoes-lista'),
      pendingFeedback.preview.conteudo, pendingFeedback.request);
  }
  function corpusPreview() {
    $('codex-corpus-novo').hidden = !pendingCorpus;
    $('codex-corpus-previa').replaceChildren();
    if (pendingCorpus) window.mostrarCorpusNovo($('codex-corpus-previa'),pendingCorpus);
  }
  function notebookPreview(){
    $('codex-caderno').hidden=!pendingNotebook;$('codex-caderno-lista').replaceChildren();
    if(pendingNotebook)window.mostrarRegistrosCaderno($('codex-caderno-lista'),pendingNotebook.preview.conteudo);
  }
  function diligencePreview(){
    $('codex-diligencias').hidden=!pendingDiligences;$('codex-diligencias-lista').replaceChildren();
    if(pendingDiligences)window.mostrarDiligencias($('codex-diligencias-lista'),pendingDiligences.preview.conteudo);
  }
  window.estadoConversa = () => ({caso:$('codex-caso').value,conversa:conversation,ocupada:active||submitting||trackingPending||trackingFailed||reconnecting,
    atualizar_corpus:pendingCorpus?structuredClone(pendingCorpus.solicitacao):null});
  window.selecionarCorpusNovo = preview => {
    if (active||submitting||preview.conversa!==conversation||preview.caso_id!==$('codex-caso').value) throw new Error('A conversa mudou. Abra a continuação novamente.');
    pendingCorpus=structuredClone(preview);corpusPreview();
    if (!$('codex-pergunta').value.trim()) $('codex-pergunta').value='O que os novos documentos acrescentam ou alteram na apuração? Reexamine as pendências e compare com a análise anterior.';
    saveDraft();
    window.abrirComposicaoMesa?.();$('codex-form').scrollIntoView({block:'start'});$('codex-pergunta').focus();
  };
  window.abrirAchadosDaRodada = async (scope, identifier=null) => {
    await loadCatalog(); $('caso').value=scope.caso; $('caso').dispatchEvent(new Event('change'));
    $('rodada').value=scope.rodada; $('rodada').dispatchEvent(new Event('change'));
    showArea('achados'); await loadFindingsCatalog();
    $('achados-revisao').value=scope.revisao; $('achados-revisao').dispatchEvent(new Event('change'));
    const generations=[...$('achados-geracao').options].filter(option=>option.value);
    const generation=generations.find(option=>option.value===scope.geracao)?.value||generations[0]?.value;
    if(!generation)throw new Error('Não há índice disponível para esta revisão do achado.');
    $('achados-geracao').value=generation;
    const query={...findingScope(),filtros:{},limite:Number($('achados-limite').value),deslocamento:0};
    await searchFindings(query);
    if(identifier){const detail=await api('achados-detalhe',{...query,achado_id:identifier});selectFinding(detail.achado,query,findingEpoch,true);}
  };
  function state(value) {
    active = busyStates.has(value);
    $('codex-status').textContent = value === 'executando' && currentStage ? `${t(names[value])} · ${currentStage}` : names[value] || value;
    if (value === 'concluido') {
      for (const group of new Set(groups.values())) group.updates.open = false;
      $('codex-andamento').open = false;
      $('codex-acervo').open = false;
    }
    controls();
  }
  function clear() {
    saveDraft();
    pendingFeedback = null; feedbackPreview();
    pendingCorpus = null; corpusPreview();
    pendingNotebook = null; notebookPreview();
    pendingDiligences = null; diligencePreview();
    ++view; conversation = ''; cursor = 0; active = false;
    trackingFailed = false; trackingPending = false; reconnecting = false; wake?.();
    run = null; resumed = null; retrying = false;
    switchDraft($('codex-caso').value, '');
    currentStage = '';
    currentGroup = null; currentRound = ''; groups.clear(); frozenInventories.clear();
    sourceMap.clear(); sourceChats.clear(); messageMap.clear();
    $('codex-conversa').value = '';
    for (const id of ['codex-mensagens','codex-fontes','codex-atividades']) $(id).replaceChildren();
    $('codex-versao-editorial').textContent='Nova conversa: os documentos atuais serão preservados ao enviar a pergunta.';
    if($('codex-recibo-alerta'))$('codex-recibo-alerta').hidden=true;
    $('codex-escopo').textContent = 'Nova conversa · o corpus será congelado após a pergunta.';
    fail(); state('pronto');
    $('codex-acervo').open = true;
    heading();
    limitations();
  }
  function heading() {
    destination();
    const selected = $('codex-caso').value;
    const title = selected ? $('codex-caso').selectedOptions[0]?.textContent : '';
    if (!title) { $('codex-acervo-resumo').textContent = 'Escolher apuração e conversa'; return; }
    const name = element('span', title); name.setAttribute('translate', 'no');
    $('codex-acervo-resumo').replaceChildren(name, element('span', ' · '), element('span', 'conversas e documentos'));
  }
  async function status() {
    try {
      const data = await api('codex-status', {});
      const provider = {anthropic:'Anthropic', openai:'OpenAI'}[data.provedor] || data.provedor || 'API';
      $('codex-conta').textContent = data.autenticado
        ? `Conectado à API · ${provider} · ${data.modelo || 'modelo não informado'}`
        : 'Chave de API ausente no servidor';
      $('codex-conta').classList.toggle('connected', data.autenticado);
      if (authenticated !== data.autenticado) $('codex-conexao').open = !data.autenticado;
      authenticated = data.autenticado;
      $('codex-conexao-tecnica').replaceChildren(Leitura.tecnicos(`Integração: ${data.versao || 'versão não informada'} · Provedor: ${provider} · Modelo configurado: ${data.modelo || 'não informado'}`));
    } catch (error) { $('codex-conta').textContent = 'API indisponível.'; fail(error.message); }
  }
  async function catalogs() {
    const version = ++catalogVersion;
    try {
      const response = await fetch('/api/catalogo');
      const data = await response.json();
      if (!response.ok) throw new Error(data.erro || 'Falha ao listar casos.');
      if (version !== catalogVersion) return;
      const selected = window.contextoCaso?.() ?? $('codex-caso').value;
      $('codex-caso').replaceChildren(new Option('Selecione um caso', ''),
        ...data.casos.map(c => new Option(c.titulo, c.id)));
      if (data.casos.some(c => c.id === selected)) $('codex-caso').value = selected;
      else if (selected) clear();
      heading();
      controls();
    } catch (error) { if (version === catalogVersion) fail(error.message); }
  }
  // An option holds plain text: the conversation title (data) and its state, written in the interface language.
  function conversationOptions() {
    const selected = $('codex-conversa').value;
    $('codex-conversa').replaceChildren(new Option('Nova conversa', ''),
      ...conversationList.map(c => {
        const option = new Option(`${c.titulo} · ${badge(c)}`, c.id);
        option.dataset.titulo = c.titulo;
        return option;
      }));
    if (conversationList.some(c => c.id === selected)) $('codex-conversa').value = selected;
  }
  async function conversations() {
    const caseId = $('codex-caso').value, version = ++inventoryVersion;
    if (!caseId) {
      conversationList = [];
      $('codex-conversa').replaceChildren(new Option('Nova conversa', ''));
      $('codex-inventario').textContent = 'Escolha uma apuração para conferir seus documentos.';
      return;
    }
    try {
      const list = await api('codex-listar', {caso:caseId});
      if (version !== inventoryVersion || caseId !== $('codex-caso').value) return;
      heading();
      conversationList = list.conversas; conversationOptions();
      if (list.conversas.some(c => c.id === conversation)) $('codex-conversa').value = conversation;
      else if (conversation && !active && !submitting) clear();
      destination();
      // Guests have no access to the documents (the server refuses the inventory): ask nothing and show no document panel.
      if (guest()) return;
      // A problem in the current inventory must not hide frozen conversations.
      const inventory = await api('inventario', {caso:caseId});
      if (version !== inventoryVersion || caseId !== $('codex-caso').value) return;
      liveInventory = inventory;
      const items = element('ul', undefined, 'document-list');
      for (const doc of inventory.documentos) {
        const entry = element('li', Leitura.nome(doc));
        if (doc.extracao_pdf) entry.append(element('p', `${doc.extracao_pdf.paginas_com_texto} de ${doc.extracao_pdf.paginas_pdf ?? '?'} páginas com texto`, 'small'));
        entry.append(Leitura.tecnicos(element('pre', JSON.stringify(doc, null, 2), 'raw-briefing')));
        items.append(entry);
      }
      $('codex-inventario').replaceChildren(element('p', Leitura.quantidade(inventory.total_documentos, 'documento')), items,
        Leitura.tecnicos(`Corpus: ${inventory.corpus_id} · Apuração: ${inventory.caso_id}`));
      limitations();
    } catch (error) { if (version === inventoryVersion) fail(error.message); }
  }
  function limitations() {
    const inventory = currentRound ? frozenInventories.get(currentRound)
      : liveInventory?.caso_id === $('codex-caso').value ? liveInventory : null;
    const messages = new Set();
    if (inventory?.indisponivel) messages.add(inventory.mensagem);
    for (const doc of inventory?.documentos || []) for (const warning of Leitura.lacunas(doc)) messages.add(`${Leitura.nome(doc)}: ${warning}`);
    let pending = 0;
    for (const record of messageMap.values()) if (record.final) pending += record.pending?.size || 0;
    if (pending) messages.add(`${pending} ${pending === 1 ? 'referência da resposta não foi recuperada' : 'referências das respostas não foram recuperadas'} na própria rodada. Confira as marcações “Fonte pendente”; essas citações não oferecem suporte verificável nesta tela.`);
    $('codex-limitacoes-lista').replaceChildren(...[...messages].map(message => element('li', message)));
    $('codex-limitacoes').hidden = !messages.size;
  }
  function group(question = '') {
    const root = element('section', undefined, 'codex-round'), user = element('article', undefined, 'codex-message codex-user');
    const asked = element('p', question, 'codex-text'); asked.setAttribute('translate', 'no');
    user.append(element('h3', 'Sua pergunta'), asked);
    const answers = element('div', undefined, 'codex-answers'), actions = element('div', undefined, 'actions');
    const updates = element('details', undefined, 'codex-updates'); updates.open = true;
    const progress = element('div', undefined, 'codex-updates-body');
    progress.tabIndex = 0; progress.setAttribute('role', 'region');
    progress.setAttribute('aria-label', 'Atualizações de andamento da IA');
    updates.append(element('summary', 'Atualizações de andamento'), progress);
    root.append(user, answers, actions, updates); $('codex-mensagens').append(root);
    currentGroup = {root, answers, actions, updates, progress};
    groups.set('pergunta-' + groups.size, currentGroup);
    return currentGroup;
  }
  function messageText(record) {
    record.pending = new Set();
    Leitura.markdown(record.body, record.text, reference => {
      const hit = sourceMap.get(reference);
      if (!hit || hit.rodada !== record.round) {
        record.pending.add(reference);
        const pending = element('span', 'Fonte pendente', 'codex-pendente');
        pending.title = 'Esta referência não foi recuperada nesta rodada.'; pending.setAttribute('translate', 'yes');
        return pending;
      }
      // The citation opens the cited page itself; the side card stays open for context.
      const page = Leitura.pagina(hit);
      const chip = element('button', page ? `p. ${page}` : Leitura.localizador(hit), 'source-citation');
      chip.type = 'button'; chip.setAttribute('translate', 'yes');
      const label = `${Leitura.rotuloOriginal(page)}: ${Leitura.nome(hit)}`;
      chip.setAttribute('aria-label', label); chip.title = label;
      chip.addEventListener('click', () => {
        const card = document.getElementById('fonte-' + reference);
        if (card) { if ($('codex-painel-fontes')) $('codex-painel-fontes').open = true; card.open = true; }
        openOriginal(hit, chip);
      });
      return chip;
    });
    record.raw.textContent = JSON.stringify({...record.metadata, rodada:record.round, texto_preservado:record.text}, null, 2);
  }
  function agentMessage(id, text, delta = false, phase = '', round = '', metadata = {}) {
    let record = messageMap.get(id);
    const owner = record?.owner || groups.get(round) || currentGroup || group();
    const followUpdates = owner.progress.scrollHeight - owner.progress.clientHeight - owner.progress.scrollTop < 48;
    if (!record) {
      const card = element('article', undefined, 'panel codex-message');
      const label = element('h3', 'IA · em andamento');
      const body = element('div', '', 'markdown-body'), raw = element('pre', '', 'raw-briefing');
      card.append(label, body, Leitura.tecnicos(raw)); owner.progress.append(card);
      record = {card, body, raw, label, owner, text:'', round, metadata:{}}; messageMap.set(id, record);
    }
    record.text = delta ? record.text + text : text;
    record.metadata = {...record.metadata, ...metadata};
    record.final = Boolean(metadata.publicada || phase === 'final_answer');
    record.label.textContent = record.final ? 'Resposta' : 'Atualização de andamento';
    if (record.final) { record.owner.answers.append(record.card); record.card.classList.add('codex-answer'); }
    messageText(record); limitations();
    if (!record.final && followUpdates) owner.progress.scrollTop = owner.progress.scrollHeight;
  }
  async function openOriginal(hit, trigger) {
    trigger.disabled = true;
    try {
      const blob = await api('codex-original', {conversa:sourceChats.get(hit.referencia), referencia:hit.referencia}, true);
      await window.abrirOriginal(blob, hit.original.split('/').pop(), Leitura.pagina(hit), hit.trecho);
    } catch (error) { fail(error.message); }
    finally { trigger.disabled = false; }
  }
  function source(hit, chatId) {
    if (sourceMap.has(hit.referencia)) return;
    const doc = frozenInventories.get(hit.rodada)?.documentos?.find(d => d.id === hit.documento_id);
    hit = {...hit, nome_documento:hit.nome_documento || doc?.nome_recebido || hit.original};
    sourceMap.set(hit.referencia, hit); sourceChats.set(hit.referencia, chatId);
    const card = element('details', undefined, 'codex-source');
    card.id = 'fonte-' + hit.referencia; card.tabIndex = -1;
    const quote = element('blockquote', hit.trecho); quote.tabIndex = -1;
    card.append(element('summary', Leitura.fonte(hit)), quote);
    const button = element('button', Leitura.rotuloOriginal(Leitura.pagina(hit)));
    button.type = 'button';
    button.addEventListener('click', () => openOriginal(hit, button));
    const notebook=element('button','Registrar trecho com fonte','secondary');notebook.type='button';
    const caseId=$('codex-caso').value;
    notebook.addEventListener('click',()=>window.abrirRegistroCaderno({caso:caseId,rodada:hit.rodada,
      documento_id:hit.documento_id,pagina_pdf:hit.pagina_pdf,
      localizador:Leitura.localizador(hit,'pt'),
      trecho:window.trechoSelecionadoCaderno(quote,hit.trecho)}));
    card.append(button,notebook,Leitura.tecnicos(element('pre', JSON.stringify(hit, null, 2), 'raw-briefing')));
    $('codex-fontes').append(card);
    for (const record of messageMap.values()) messageText(record);
    limitations();
  }
  function event(event, chatId) {
    const data = event.dados;
    if (event.tipo === 'pergunta') {
      group(data.texto);
    } else if (event.tipo === 'observacoes_humanas') {
      const owner = currentGroup || group(), details = element('details',undefined,'feedback-history');
      details.append(element('summary', Leitura.quantidade(data.quantidade, 'observação humana anexada', 'observações humanas anexadas') + ' à pergunta'));
      const content = element('div');
      window.mostrarObservacoes(content, data, {caso:$('codex-caso').value,
        rodada:data.rodada_origem, revisao:data.revisao_origem});
      details.append(content); owner.root.insertBefore(details,owner.answers);
    } else if (event.tipo === 'diligencias_recebidas') {
      const owner=currentGroup||group(),details=element('details',undefined,'feedback-history');details.append(element('summary','Diligências humanas anexadas a esta pergunta'));
      const body=element('div');window.mostrarDiligencias(body,data);details.append(body);owner.root.insertBefore(details,owner.answers);
    } else if (event.tipo === 'contribuicoes_caderno') {
      const owner=currentGroup||group(),details=element('details',undefined,'feedback-history');
      details.append(element('summary',Leitura.quantidade(data.quantidade,'contribuição humana anexada','contribuições humanas anexadas')+' do caderno'));
      const content=element('div');window.mostrarRegistrosCaderno(content,data);details.append(content);owner.root.insertBefore(details,owner.answers);
    } else if (event.tipo === 'evolucao_corpus') {
      const owner=currentGroup||group(), details=element('details',undefined,'feedback-history');
      details.append(element('summary','Documentos incorporados nesta análise'));
      const content=element('div');window.mostrarCorpusNovo(content,data);details.append(content);
      owner.root.insertBefore(details,owner.answers);
    } else if (event.tipo === 'comparativo') {
      const owner=groups.get(data.rodada_atual)||currentGroup||group();
      const panel=element('section',undefined,'panel corpus-comparison');
      window.mostrarComparativo(panel,data,chatId);owner.answers.append(panel);
    } else if (event.tipo === 'delta') agentMessage(data.item, data.texto, true, '', data.rodada);
    else if (event.tipo === 'resposta') {
      agentMessage(data.item, data.texto, false, data.fase, data.rodada,
        {publicada:data.publicada, arquivo:data.arquivo, sha256:data.sha256, etapa:data.etapa});
      $('codex-anuncio').textContent=matchMedia('(min-width:1024px)').matches && !(data.publicada || data.fase === 'final_answer')
        ? 'Atualização de andamento disponível. A análise continua.'
        : 'Resposta disponível. Confira a análise e as fontes consultadas.';
    }
    else if (event.tipo === 'fonte') source(data, chatId);
    else if (event.tipo === 'erro') {
      fail(data.mensagem);
      $('codex-atividades').append(element('li', `Erro: ${data.mensagem}${data.codigo ? ' · ' + data.codigo : ''}`));
    } else if (event.tipo === 'escopo') {
      currentRound = data.rodada;
      $('codex-versao-editorial').textContent=`Documentos desta conversa: versão ${data.corpus_id} · análise ${data.rodada}.`;
      if (currentGroup) groups.set(currentRound, currentGroup);
      $('codex-escopo').textContent = `${data.caso} / ${data.rodada} · corpus ${data.corpus_id} · modelo informado pela API: ${data.modelo || 'desconhecido'}`;
    } else if (event.tipo === 'ferramenta') {
      $('codex-atividades').append(element('li', `${data.acao}${data.etapa ? ' · ' + data.etapa : ''}${data.retornados !== null && data.retornados !== undefined ? ' · ' + data.retornados + ' trecho(s)' : ''} · ${data.arquivo}`));
    } else if (event.tipo === 'etapa') {
      currentStage = t(stageLabels[data.etapa] || data.etapa);
      $('codex-atividades').append(element('li', `${data.numero}/${data.total} · ${currentStage}${data.tentativa > 1 ? ' · nova tentativa automática' : ''}`));
    } else if (event.tipo === 'publicacao') {
      $('codex-atividades').append(element('li', `Achados publicados e verificados: ${data.caso} / ${data.rodada} · ${data.achados} achado(s). Conferência humana não realizada.`));
      const link = element('button','Consultar achados desta análise','secondary'); link.type = 'button';
      link.addEventListener('click', async () => {
        try {
          await window.abrirAchadosDaRodada(data);
        } catch (error) { fail(error.message); }
      });
      (groups.get(data.rodada) || currentGroup)?.actions.append(link);
    } else if (event.tipo === 'uso') {
      const tokens = (uso) => `entrada ${uso.entrada || 0}, saída ${uso.saida || 0}, cache ${uso.cache_leitura || 0}`;
      $('codex-atividades').append(element('li', `Uso da API${data.etapa ? ' · ' + data.etapa : ''}: ${tokens(data.uso || {})} tokens · total da análise: ${tokens(data.total || {})}`));
    } else if (event.tipo === 'retomada') {
      resumed = data;
      $('codex-atividades').append(element('li', resumeText(data)));
    } else if (event.tipo === 'aviso') $('codex-atividades').append(element('li', data.mensagem));
  }
  function watch() {
    if (!conversation || trackingPending) return;
    trackingPending = true; controls();
    // Invalidate any older observer; retain the cursor and the rendered conversation.
    poll(++view);
  }
  async function lostConnection(attempt) {
    reconnecting = true; trackingPending = false;
    $('codex-status').textContent = offline() ? connectionTexts.offline : connectionTexts.rede;
    controls();
    await pause(offline() ? RECONNECT_MS.at(-1) : RECONNECT_MS[Math.min(attempt, RECONNECT_MS.length) - 1]);
  }
  async function poll(version) {
    const chatId = conversation;
    let attempt = 0;
    while (version === view && conversation === chatId) {
      try {
        const data = await api('codex-eventos', {conversa:chatId, cursor, espera:20});
        if (version !== view) return;
        if (trackingPending) fail();
        if (reconnecting) $('codex-anuncio').textContent = 'Conexão restabelecida. Acompanhamento retomado.';
        trackingPending = false; trackingFailed = false; reconnecting = false; attempt = 0;
        for (const [round, inventory] of Object.entries(data.acervos || {})) frozenInventories.set(round, inventory);
        // One event that fails to render must not hold the cursor back: the next poll (or a
        // reconnection) would then replay, and duplicate, the events already on screen.
        let renderFailure = null;
        for (const entry of data.eventos) { try { event(entry, chatId); } catch (failure) { renderFailure ??= failure; } }
        cursor = data.cursor;
        run = data.conversa;
        state(data.conversa.estado);
        limitations();
        if (renderFailure) throw renderFailure;
        if (!active && data.eventos.length < 100) { await conversations(); return; }
      } catch (error) {
        if (version !== view) return;
        if (error.rede) { await lostConnection(++attempt); continue; }
        reconnecting = false;
        trackingPending = false; trackingFailed = true;
        fail(`Falha ao acompanhar a execução: ${error.message} A execução pode continuar. Use “Reconectar acompanhamento” para voltar a observá-la.`);
        $('codex-status').textContent = 'Conexão da interface interrompida';
        // Keep cancellation available; an HTTP failure is not a completed turn.
        controls();
        return;
      }
    }
  }
  $('codex-reconectar').addEventListener('click', () => { if (trackingFailed) watch(); });
  // Same frozen round, from the first stage not yet accepted. Guests send only the conversation.
  $('codex-retomar').addEventListener('click', async () => {
    if (retrying || active || submitting || trackingPending || trackingFailed || !conversation || run?.retomavel !== true) return;
    const chatId = conversation;
    retrying = true; fail(); controls();
    try {
      const result = await api('codex-retomar', {conversa:chatId});
      if (chatId !== conversation) return;
      run = {...run, retomavel:false, situacao:{codigo:'em_andamento', mensagem:'Em execução.', causa:null}};
      resumed = null; retrying = false;
      state(result.estado);
      watch();
    } catch (error) { if (chatId === conversation) fail(error.message); }
    finally { retrying = false; controls(); }
  });
  $('codex-conectar').addEventListener('click', status);
  $('codex-desligar').addEventListener('click', async () => {
    if (!window.confirm(window.I18N.t('Encerrar o serviço local? As execuções ativas serão interrompidas. As saídas já salvas serão preservadas; será necessário abrir a Mesa novamente para continuar.'))) return;
    try {
      await api('codex-desligar', {});
      ++view; active = false;
      $('codex-status').textContent = 'Serviço encerrado. Para voltar, abra o Vlado de novo.';
      for (const id of ['codex-enviar','codex-cancelar','codex-conectar','codex-desligar']) $(id).disabled = true;
    } catch (error) { fail(error.message); }
  });
  $('codex-atualizar').addEventListener('click', async () => { await catalogs(); await conversations(); });
  $('codex-caso').addEventListener('change', async () => { clear(); await conversations(); });
  $('codex-nova').addEventListener('click', () => { clear(); $('codex-conversa').value = ''; });
  $('codex-conversa').addEventListener('change', () => {
    const selected = $('codex-conversa').value; clear(); conversation = selected;
    $('codex-conversa').value = selected;
    switchDraft($('codex-caso').value, selected);
    controls();
    if (selected) watch();
  });
  $('codex-excluir').addEventListener('click', async () => {
    if (active || submitting || !conversation) return;
    submitting = true; controls();
    try {
      const removed = await window.excluirItem({tipo:'conversa', caso:$('codex-caso').value, conversa:conversation},
        $('codex-conversa').selectedOptions[0]?.textContent || 'Conversa');
      if (removed) $('codex-status').textContent = 'Conversa movida para a lixeira. Você pode restaurá-la em Apurações e lixeira.';
    } catch (error) { fail(error.message); }
    finally { submitting = false; controls(); }
  });
  window.addEventListener('acervo-alterado', async ({detail}) => {
    const item = detail.item;
    if (detail.estado === 'excluido' && item.caso === $('codex-caso').value &&
        (item.tipo === 'caso' || item.conversa === conversation)) clear();
    await catalogs();
    await conversations();
  });
  $('codex-cancelar').addEventListener('click', async () => {
    $('codex-status').textContent = 'Cancelamento solicitado…';
    try { await api('codex-cancelar', {conversa:conversation}); }
    catch (error) { fail(error.message); }
  });
  $('codex-observacoes-remover').addEventListener('click', () => {
    if (active || submitting) return;
    pendingFeedback = null; feedbackPreview();
  });
  $('codex-corpus-retirar').addEventListener('click',()=>{if(active||submitting)return;pendingCorpus=null;corpusPreview();});
  $('codex-caderno-retirar').addEventListener('click',()=>{if(active||submitting)return;pendingNotebook=null;notebookPreview();});
  $('codex-diligencias-retirar').addEventListener('click',()=>{if(active||submitting)return;pendingDiligences=null;diligencePreview();});
  async function levarContribuicoes(preview, request, kind) {
    if (active || submitting || trackingPending || trackingFailed) throw new Error('Aguarde a execução ou reconecte o acompanhamento antes de levar observações.');
    const keepDraft = $('codex-caso').value === preview.caso && conversation === (preview.conversa || '');
    const corpusDraft = keepDraft ? pendingCorpus : null;
    const feedbackDraft = keepDraft ? pendingFeedback : null;
    const notebookDraft = keepDraft ? pendingNotebook : null;
    const diligenceDraft = keepDraft ? pendingDiligences : null;
    submitting = true; controls();
    try {
      await catalogs();
      if (![...$('codex-caso').options].some(option => option.value === preview.caso)) throw new Error('A apuração não está mais disponível.');
      clear(); $('codex-caso').value = preview.caso;
      await conversations();
      if (preview.conversa && ![...$('codex-conversa').options].some(option => option.value === preview.conversa)) throw new Error('A conversa de origem não está mais disponível.');
      conversation = preview.conversa || ''; $('codex-conversa').value = conversation;
      switchDraft(preview.caso, conversation);
      const captured={preview:structuredClone(preview),request:structuredClone(request)};
      pendingFeedback=kind==='observacoes'?captured:feedbackDraft;
      pendingNotebook=kind==='caderno'?captured:notebookDraft;
      pendingDiligences=kind==='diligencias'?captured:diligenceDraft;
      pendingCorpus = preview.corpus_novo || corpusDraft; corpusPreview();
      notebookPreview();
      diligencePreview();
      feedbackPreview(); showArea('codex'); heading();
      $('codex-acervo').open = false;
      $('codex-pergunta').value = $('codex-pergunta').value || (kind==='diligencias'?'Retome a questão da diligência selecionada. Confira as respostas documentais, explique o que esclarecem e quais pendências permanecem.':kind==='caderno'?'Considere as contribuições humanas selecionadas no caderno. Reabra os originais, examine os cruzamentos e distinga o que as fontes sustentam das interpretações dos autores.':'Reexamine os achados selecionados considerando estas observações. Confira as fontes e explique as correções ou divergências que permanecerem.');
      saveDraft();
      if (conversation) watch();
      await status();
      window.abrirComposicaoMesa?.();$('codex-form').scrollIntoView({block:'start'}); $('codex-pergunta').focus();
    } finally { submitting = false; controls(); }
  }
  window.continuarComObservacoes=(preview,request)=>levarContribuicoes(preview,request,'observacoes');
  window.continuarComCaderno=(preview,request)=>levarContribuicoes(preview,request,'caderno');
  window.continuarComDiligencias=(preview,request)=>levarContribuicoes(preview,request,'diligencias');
  $('codex-form').addEventListener('submit', async e => {
    e.preventDefault(); if (active || submitting || trackingPending || trackingFailed) return;
    if (draftContext.caso !== $('codex-caso').value || draftContext.conversa !== conversation) {
      fail('O destino da pergunta mudou. Selecione novamente a apuração e a conversa antes de enviar.'); return;
    }
    saveDraft();
    fail(); submitting = true; controls();
    try {
      const request = pendingFeedback?.request;
      const result = await api('codex-perguntar', {caso:$('codex-caso').value,
        conversa:conversation || null, pergunta:$('codex-pergunta').value,
        ...(pendingCorpus ? {atualizar_corpus:pendingCorpus.solicitacao} : {}),
        ...(pendingNotebook ? {registros_caderno:pendingNotebook.request.selecoes} : {}),
        ...(pendingDiligences ? {diligencias:pendingDiligences.request.selecoes} : {}),
        ...(request ? {observacoes_humanas:Object.fromEntries(['rodada','revisao','geracao_achados','selecoes'].map(key => [key,request[key]]))} : {})});
      drafts.delete(draftKey(draftContext)); rascunhoPergunta?.concluir();
      conversation = result.conversa;
      draftContext = {caso:$('codex-caso').value, conversa:conversation};
      pendingDiligences=null;diligencePreview();
      if(pendingNotebook){window.limparSelecaoCaderno(pendingNotebook.preview.caso);pendingNotebook=null;notebookPreview();}
      pendingCorpus=null;corpusPreview();
      if (pendingFeedback) { pendingFeedback = null; feedbackPreview(); window.limparObservacoes(); }
      $('codex-acervo').open = false;
      $('codex-pergunta').value = ''; rascunhoPergunta?.abrir();
      state(result.estado);
      watch();
    } catch (error) { fail(error.message); }
    finally { submitting = false; controls(); }
  });
  $('codex-pergunta').addEventListener('input', saveDraft);
  window.addEventListener('beforeunload', event => {
    saveDraft();
    if ([...drafts.values()].some(text => text.trim())) { event.preventDefault(); event.returnValue = ''; }
  });
  window.addEventListener('codex-abrir', async () => { await catalogs(); await status(); });
  // Locator words follow the interface language; rebuild source titles and citations on a switch.
  window.addEventListener('vlado-idioma', () => {
    for (const [reference, hit] of sourceMap) {
      const summary = document.getElementById('fonte-' + reference)?.querySelector('summary');
      if (summary) summary.textContent = Leitura.fonte(hit);
    }
    for (const record of messageMap.values()) messageText(record);
    conversationOptions();
    runBlock();
  });
  controls();
})();
