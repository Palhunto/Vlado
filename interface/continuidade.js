'use strict';
// Automatic drafts for the question and the panel forms. Each keystroke goes to localStorage at
// once (the copy in this browser) and, after a short pause, to the server (the durable copy,
// POST /api/rascunhos-*). Leaving the tab (visibilitychange) or the page (pagehide) sends at once.
// The notebook (Caderno) keeps its own drafts: sessionStorage plus the server's note save,
// because contract section 3 keeps note text out of localStorage.
// Drafts never hold keys: password fields and key-like names or values are not kept anywhere.
window.Rascunhos = (() => {
  const PREFIXO = 'vlado:rascunho-tela:';
  const PAUSA = 1200;
  // keepalive bodies are capped by browsers (64 KB); larger drafts stay in this browser on pagehide.
  const KEEPALIVE = 60000;
  const VALOR_DE_CHAVE = /\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{20,}|ANTHROPIC_API_KEY|OPENAI_API_KEY|ANTHROPIC_AUTH_TOKEN/;
  const CAMPO_PROIBIDO = /chave|key|senha|password|passwd|token|secret|segredo|credencia|api/i;
  const CAMPO = /^[a-z][a-z0-9_]{0,39}$/;
  const SEM_CHAVE = 'Rascunho não guardado: retire a chave de API, senha ou token do texto.';
  const SEM_REDE = 'Sem conexão — salvo neste navegador';
  // Templates with {name}, translated by i18n.js (keys in i18n_en.js), like the notebook's.
  const preencher = (texto, vars) => window.I18N ? window.I18N.t(texto, vars)
    : Object.entries(vars || {}).reduce((fim, [nome, valor]) => fim.split(`{${nome}}`).join(String(valor)), texto);
  const controles = new Set();
  let encerrado = false;
  // Aggregate status for the header (Rascunhos.indicador). Each screen's line maps to one kind;
  // the most urgent kind across screens wins. Consumers render the text themselves.
  const TIPOS = {'': 'ocioso', 'Salvando…': 'salvando', 'Salvo às {hora}': 'salvo', [SEM_REDE]: 'sem_rede',
    [SEM_CHAVE]: 'sem_chave', 'Escolha acima qual rascunho manter para continuar salvando.': 'decidir',
    'Não foi possível guardar no servidor — salvo neste navegador. {erro}': 'erro'};
  const URGENCIA = ['decidir', 'sem_chave', 'erro', 'sem_rede', 'salvando', 'salvo', 'ocioso'];
  const situacoes = new Map(), ouvintes = new Set();
  let ultimaHora = null;
  function agregado() {
    let tipo = 'ocioso', telas = 0;
    for (const [controle, s] of situacoes) {
      const atual = controle.estado().decidir ? 'decidir' : s;
      if (URGENCIA.indexOf(atual) < URGENCIA.indexOf(tipo)) tipo = atual;
      if (['salvando', 'sem_rede', 'erro'].includes(atual) || controle.estado().pendente) telas++;
    }
    return {tipo, hora: ultimaHora, telas};
  }
  function notificar() {
    const dados = agregado();
    for (const fn of ouvintes) { try { fn(dados); } catch { /* A consumer error never stops saving. */ } }
    try { document.dispatchEvent(new CustomEvent('vlado:rascunho-estado', {detail: dados})); } catch { /* Old engines. */ }
  }
  const indicador = {
    estado: agregado,
    assinar(fn) { if (typeof fn !== 'function') return () => {}; ouvintes.add(fn); fn(agregado()); return () => ouvintes.delete(fn); },
  };
  // The account that owns the copies in this browser. In the modes with accounts (piloto,
  // local-contas) it comes from /api/sessao, like the notebook's; until it is known nothing is read
  // from or written to localStorage, so one account never sees another account's unsent text.
  const CONTA = /^[a-z0-9]{1,64}$/;
  let contaSessao = null, pedidoConta = null;
  const conta = () => document.body.dataset.conta || (document.body.dataset.modo === 'local' ? 'local' : contaSessao);
  function contaPronta() {
    if (conta()) return Promise.resolve(conta());
    if (!pedidoConta) {
      pedidoConta = fetch('/api/sessao').then(resposta => resposta.ok ? resposta.json() : null)
        .then(dados => { const id = dados?.conta?.id; if (typeof id === 'string' && CONTA.test(id)) contaSessao = id; })
        .catch(() => { /* Unknown account: this browser keeps no copy; the server copy goes on. */ })
        .finally(() => { pedidoConta = null; });
    }
    return pedidoConta.then(conta);
  }
  const area = () => { try { return window.localStorage || null; } catch { return null; } };
  const chave = alvo => conta() ? `${PREFIXO}${conta()}:${alvo.caso}:${alvo.tela}` : null;
  const plano = valor => valor === null || ['string', 'number', 'boolean'].includes(typeof valor);
  function valido(conteudo) {
    return !!conteudo && typeof conteudo === 'object' && !Array.isArray(conteudo)
      && Object.entries(conteudo).every(([nome, valor]) => CAMPO.test(nome) && plano(valor));
  }
  function temChave(conteudo) {
    return Object.entries(conteudo).some(([nome, valor]) => CAMPO_PROIBIDO.test(nome) || (typeof valor === 'string' && VALOR_DE_CHAVE.test(valor)));
  }
  const vazio = conteudo => !conteudo || Object.entries(conteudo).every(([nome, valor]) => nome === 'contexto' || valor === null || valor === false || valor === '');
  const ordenado = conteudo => JSON.stringify(Object.keys(conteudo || {}).sort().map(nome => [nome, conteudo[nome]]));
  const igual = (a, b) => ordenado(a) === ordenado(b);
  function lerLocal(alvo) {
    try {
      const nome = chave(alvo);
      const dados = nome ? JSON.parse(area()?.getItem(nome) || 'null') : null;
      return dados && valido(dados.conteudo) && Number.isInteger(dados.versao) && typeof dados.em === 'string' ? dados : null;
    } catch { return null; }
  }
  function gravarLocal(alvo, dados) {
    const nome = chave(alvo);
    if (encerrado || !nome) return;
    try { area()?.setItem(nome, JSON.stringify(dados)); } catch { /* Full or blocked: the server copy goes on. */ }
  }
  function removerLocal(alvo) { const nome = chave(alvo); if (!nome) return; try { area()?.removeItem(nome); } catch { /* Nothing kept. */ } }
  function hora(iso) {
    const data = new Date(iso);
    return Number.isNaN(data.getTime()) ? '' : `${String(data.getHours()).padStart(2, '0')}:${String(data.getMinutes()).padStart(2, '0')}`;
  }
  // UTF-8 size (keepalive caps bytes, not characters).
  const bytes = texto => encodeURIComponent(texto).replace(/%[0-9A-F]{2}/g, '.').length;
  // Same as api(), plus keepalive so a save started on pagehide survives the page.
  async function pedir(operacao, dados, manter = false) {
    const corpo = manter ? JSON.stringify(dados) : '';
    // Too big for keepalive: a normal request (may not finish if the page closes; the copy in
    // this browser stays pending and is offered on the next opening).
    if (!manter || bytes(corpo) > KEEPALIVE) return api(operacao, dados);
    let resposta;
    try {
      resposta = await fetch(`/api/${operacao}`, {method: 'POST', keepalive: true,
        headers: {'Content-Type': 'application/json', 'X-Session-Token': token}, body: corpo});
    } catch (causa) { throw Object.assign(new Error('Sem conexão com o servidor.'), {rede: true, cause: causa}); }
    let resultado;
    try { resultado = await resposta.json(); } catch (causa) { throw Object.assign(new Error('Sem conexão com o servidor.'), {rede: true, cause: causa}); }
    if (!resposta.ok) throw Object.assign(new Error(resultado.erro || ''), {result: resultado});
    return resultado;
  }

  // `alvo()` -> {caso, tela} or null; `ler()` -> flat fields; `aplicar(conteudo)` puts them back.
  // `ancora` is where the status line and the restore offer appear (right after it).
  // `compativel(conteudo)` may refuse a draft written for another item of the same screen.
  function registrar({origem, ancora, alvo, ler, aplicar, compativel = () => true}) {
    const estado = element('p', '', 'small rascunho-estado');
    estado.setAttribute('role', 'status'); estado.setAttribute('aria-live', 'polite'); estado.hidden = true;
    const oferta = element('div', undefined, 'rascunho-oferta notice'); oferta.hidden = true;
    ancora.after(estado, oferta);
    let controle = null, atual = null, versao = 0, timer = null, emVoo = null, denovo = false, decidir = false, sequencia = 0, semRede = false, abrindo = null;
    // `ultimo`: the fields last read for the current target. Leaving a target sends this, not
    // ler(), because the caller may already have put another target's text in the field.
    // `alheio`: the server holds a draft of another item of this screen; closing does not discard it.
    let ultimo = null, alheio = false;
    const concluidos = new Map();  // targets finished while a save was in flight -> content sent
    const nomeAlvo = a => `${a.caso}\n${a.tela}`;
    const mesmo = a => !!a && !!atual && a.caso === atual.caso && a.tela === atual.tela;
    function mostrar(texto, vars) {
      estado.textContent = texto ? preencher(texto, vars) : ''; estado.hidden = !texto;
      const tipo = TIPOS[texto || ''] || 'erro';
      if (tipo === 'salvo' && vars?.hora) ultimaHora = vars.hora;
      if (controle) { situacoes.set(controle, tipo); notificar(); }
    }
    function fecharOferta() { decidir = false; oferta.hidden = true; oferta.replaceChildren(); }
    function perguntar(texto, vars, opcoes) {
      decidir = true; oferta.replaceChildren(element('p', preencher(texto, vars)));
      const acoes = element('div', undefined, 'actions');
      for (const [rotulo, acao, classe] of opcoes) {
        const botao = element('button', rotulo, classe); botao.type = 'button';
        botao.addEventListener('click', () => { fecharOferta(); acao(); });
        acoes.append(botao);
      }
      oferta.append(acoes); oferta.hidden = false;
    }
    function parar() { clearTimeout(timer); timer = null; }
    function agendar() { parar(); timer = setTimeout(() => { timer = null; enviar(); }, PAUSA); }
    // Copy in this browser at once, then the server after the pause. While a restore or conflict
    // choice is on screen nothing is written, so the older draft cannot be overwritten silently.
    function mudou() {
      if (encerrado) return;
      const alvoAgora = alvo();
      if (!alvoAgora) return;
      // First keystroke on a target not opened yet: open it (may offer a draft), then save.
      if (!mesmo(alvoAgora)) { abrir().then(() => { if (mesmo(alvoAgora) && !decidir) mudou(); }); return; }
      if (decidir) { mostrar('Escolha acima qual rascunho manter para continuar salvando.'); return; }
      const conteudo = ler();
      if (temChave(conteudo)) { parar(); removerLocal(atual); ultimo = null; mostrar(SEM_CHAVE); return; }
      ultimo = conteudo; alheio = false;
      gravarLocal(atual, {conteudo, versao, em: new Date().toISOString(), pendente: true});
      agendar();
    }
    async function enviar(manter = false, fixo = null) {
      // The version comes from the server read in abrir(): never save before it answers.
      if (abrindo && !manter) await abrindo;
      if (encerrado || decidir || !atual) return;
      if (emVoo) { denovo = true; return emVoo; }
      const alvoEnvio = atual, conteudo = fixo || ler();
      if (temChave(conteudo)) return;
      if (vazio(conteudo)) { removerLocal(alvoEnvio); if (versao) await descartarServidor(alvoEnvio, ultimo); mostrar(''); return; }
      mostrar('Salvando…');
      emVoo = (async () => {
        try {
          const resultado = await pedir('rascunhos-salvar', {caso: alvoEnvio.caso, tela: alvoEnvio.tela, versao, conteudo}, manter);
          if (!mesmo(alvoEnvio)) {
            if (concluidos.has(nomeAlvo(alvoEnvio))) {
              concluidos.delete(nomeAlvo(alvoEnvio));
              api('rascunhos-descartar', {caso: alvoEnvio.caso, tela: alvoEnvio.tela, versao: resultado.versao}).catch(() => {});
            }
            return;
          }
          versao = resultado.versao; semRede = false;
          const local = lerLocal(alvoEnvio);
          if (local) gravarLocal(alvoEnvio, {...local, versao, pendente: !igual(local.conteudo, conteudo)});
          mostrar('Salvo às {hora}', {hora: hora(resultado.atualizado_em_utc || new Date().toISOString())});
        } catch (erro) {
          if (!mesmo(alvoEnvio)) return;
          if (erro.rede) { semRede = true; mostrar(SEM_REDE); return; }
          const resposta = erro.result || {};
          if (resposta.codigo === 'rascunho_conflito' && resposta.atual) { conflito(resposta.atual, conteudo); return; }
          if (resposta.codigo === 'rascunho_com_chave') { removerLocal(alvoEnvio); mostrar(SEM_CHAVE); return; }
          mostrar('Não foi possível guardar no servidor — salvo neste navegador. {erro}', {erro: erro.message});
        }
      })();
      try { await emVoo; } finally {
        emVoo = null;
        if (denovo) { denovo = false; if (!manter && !decidir) agendar(); }
      }
    }
    // Another tab or window wrote first: nothing was overwritten; the writer chooses.
    function conflito(servidor, meu) {
      versao = servidor.versao;
      if (servidor.conteudo && igual(servidor.conteudo, meu)) {
        const local = lerLocal(atual);
        if (local) gravarLocal(atual, {...local, versao, pendente: !igual(local.conteudo, meu)});
        mostrar('Salvo às {hora}', {hora: hora(servidor.atualizado_em_utc)}); return;
      }
      mostrar('');
      perguntar('Este rascunho mudou em outra aba ou janela. Qual versão manter?', {}, [
        ['Manter o desta aba', () => enviar(), ''],
        ['Usar o da outra aba', () => {
          aplicar(servidor.conteudo || {});
          gravarLocal(atual, {conteudo: ler(), versao, em: servidor.atualizado_em_utc || new Date().toISOString(), pendente: false});
          mostrar(servidor.conteudo ? 'Salvo às {hora}' : '', {hora: hora(servidor.atualizado_em_utc)});
        }, 'secondary']]);
    }
    // On a conflict, another tab wrote after this one: its draft stays unless it is what this tab knew.
    async function descartarServidor(alvoDescarte, conhecido) {
      let versaoDescarte = versao;
      for (let tentativa = 0; tentativa < 2; tentativa++) {
        try { const r = await api('rascunhos-descartar', {caso: alvoDescarte.caso, tela: alvoDescarte.tela, versao: versaoDescarte}); if (mesmo(alvoDescarte)) versao = r.versao; return; }
        catch (erro) {
          const resposta = erro.result || {};
          if (resposta.codigo !== 'rascunho_conflito' || !resposta.atual) return;
          if (mesmo(alvoDescarte)) versao = resposta.atual.versao;
          if (resposta.atual.descartado || !conhecido || !igual(resposta.atual.conteudo, conhecido)) return;
          versaoDescarte = resposta.atual.versao;
        }
      }
    }
    // Leaving the tab or page: send at once what is still only in this browser.
    function despedir() {
      if (!atual || decidir) return;
      const local = lerLocal(atual);
      const conteudo = ultimo || (local?.pendente ? local.conteudo : null);
      if ((timer || local?.pendente) && conteudo) { parar(); enviar(true, conteudo).catch(() => {}); }
    }
    // Called when the screen opens or its target changes: offers a newer draft back.
    function abrir() {
      const novo = alvo();
      if (novo && mesmo(novo)) return abrindo || Promise.resolve();
      despedir(); fecharOferta(); mostrar('');
      atual = novo ? {caso: novo.caso, tela: novo.tela} : null; versao = 0; semRede = false; ultimo = null; alheio = false;
      const pedido = ++sequencia;
      if (!atual || encerrado) { abrindo = null; return Promise.resolve(); }
      const promessa = carregar(novo, pedido).finally(() => { if (pedido === sequencia) abrindo = null; });
      abrindo = promessa;
      return promessa;
    }
    async function carregar(novo, pedido) {
      await contaPronta();
      if (pedido !== sequencia || !mesmo(novo)) return;
      const local = lerLocal(atual);
      let servidor = null;
      try { servidor = await api('rascunhos-ler', {caso: atual.caso, tela: atual.tela}); } catch (erro) { if (erro.rede) semRede = true; }
      if (pedido !== sequencia || !mesmo(novo)) return;
      versao = servidor ? servidor.versao : (local?.versao || 0);
      alheio = !!(servidor?.conteudo && !servidor.descartado && valido(servidor.conteudo) && !compativel(servidor.conteudo));
      const candidatos = [];
      if (servidor?.conteudo && !servidor.descartado && valido(servidor.conteudo)) candidatos.push({conteudo: servidor.conteudo, em: servidor.atualizado_em_utc || ''});
      // The local copy counts while unsent, or when the server could not answer.
      if (local && (local.pendente || !servidor) && !(servidor?.descartado && local.versao < servidor.versao)) candidatos.push({conteudo: local.conteudo, em: local.em});
      candidatos.sort((a, b) => (Date.parse(b.em) || 0) - (Date.parse(a.em) || 0));
      const melhor = candidatos.find(c => !vazio(c.conteudo) && compativel(c.conteudo));
      if (servidor?.descartado && !local?.pendente) removerLocal(atual);
      if (semRede) mostrar(SEM_REDE);
      if (!melhor || igual(melhor.conteudo, ler())) return;
      perguntar('Há um rascunho de {hora} que não foi enviado. Restaurar?', {hora: hora(melhor.em)}, [
        ['Restaurar rascunho', () => {
          aplicar(melhor.conteudo);
          ultimo = ler();
          gravarLocal(atual, {conteudo: ultimo, versao, em: new Date().toISOString(), pendente: true});
          enviar();
        }, ''],
        ['Descartar rascunho', () => { removerLocal(atual); if (versao) descartarServidor(atual, melhor.conteudo); mostrar(''); }, 'secondary']]);
    }
    // The text was sent or saved for real: the draft is no longer needed.
    function concluir() {
      parar(); fecharOferta(); mostrar('');
      if (!atual) return;
      const feito = atual;
      if (!alheio) {
        removerLocal(feito);
        if (emVoo) concluidos.set(nomeAlvo(feito), true);
        else if (versao) descartarServidor(feito, ultimo);
      }
      atual = null; versao = 0; abrindo = null; ultimo = null; alheio = false; ++sequencia;
    }
    // Forget the target without discarding (the next abrir() reads it again).
    function soltar() { despedir(); parar(); fecharOferta(); mostrar(''); atual = null; versao = 0; ultimo = null; alheio = false; ++sequencia; }
    origem.addEventListener('input', mudou);
    origem.addEventListener('change', mudou);
    controle = {abrir, concluir, soltar, enviar, despedir, parar, estado: () => ({alvo: atual, versao, pendente: !!timer, semRede, decidir})};
    controles.add(controle);
    return controle;
  }
  // Flat fields of a form, by id (dashes become underscores). Password, file and key-like
  // fields are never read.
  function campos(forms) {
    return forms.flatMap(form => [...form.querySelectorAll('input[id], textarea[id], select[id]')]).filter(el => {
      const nome = el.id.replace(/-/g, '_');
      return !['password', 'file', 'hidden', 'submit', 'button'].includes(el.type) && CAMPO.test(nome) && !CAMPO_PROIBIDO.test(nome);
    }).slice(0, 49);
  }
  const marcavel = el => el.type === 'checkbox' || el.type === 'radio';
  function lerFormulario(forms) {
    const dados = {};
    for (const el of campos(forms)) dados[el.id.replace(/-/g, '_')] = marcavel(el) ? !!el.checked : String(el.value ?? '');
    return dados;
  }
  function aplicarFormulario(forms, conteudo) {
    for (const el of campos(forms)) {
      const nome = el.id.replace(/-/g, '_');
      if (!(nome in conteudo)) continue;
      if (marcavel(el)) el.checked = !!conteudo[nome]; else el.value = conteudo[nome] ?? '';
      el.dispatchEvent(new Event('input', {bubbles: true}));  // counters and "unsaved" checks follow
    }
  }
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') for (const c of controles) c.despedir(); });
  window.addEventListener('pagehide', () => { for (const c of controles) c.despedir(); });
  window.addEventListener('online', () => { for (const c of controles) if (c.estado().semRede) c.enviar(); });
  // Sign-out: stop saving and leave nothing of these drafts in this browser.
  function limparTudo() {
    encerrado = true;
    for (const c of controles) c.parar();
    try {
      const armazenamento = area(), nomes = [];
      if (!armazenamento) return;
      for (let i = 0; i < armazenamento.length; i++) { const nome = armazenamento.key(i); if (nome?.startsWith(PREFIXO)) nomes.push(nome); }
      for (const nome of nomes) armazenamento.removeItem(nome);
    } catch { /* Storage blocked: nothing was kept. */ } finally { situacoes.clear(); ultimaHora = null; notificar(); }
  }
  // Stable short id of an item's identity text, so each item of a screen has its own draft
  // (tela `quadro-revisao/<id>`). Two 32-bit FNV-1a variants: 16 hex digits.
  function idItem(texto) {
    let a = 0x811c9dc5, b = 0x9e3779b9;
    for (const letra of String(texto)) { const n = letra.codePointAt(0); a = Math.imul(a ^ n, 16777619); b = Math.imul(b ^ n, 2246822507); }
    return (a >>> 0).toString(16).padStart(8, '0') + (b >>> 0).toString(16).padStart(8, '0');
  }
  return {registrar, lerFormulario, aplicarFormulario, limparTudo, indicador, idItem, PREFIXO, PAUSA};
})();
(() => {
  const dialog=$('continuidade-dialogo');
  let scope=null, preview=null, busy=false, sequence=0;
  function fail(message='') { $('continuidade-erro').textContent=message; $('continuidade-erro').hidden=!message; }
  function controls() {
    for(const control of $('continuidade-cadastro').elements) control.disabled=busy;
    $('continuidade-fechar').disabled=busy; $('continuidade-atualizar').disabled=busy;
    $('continuidade-usar').disabled=busy||!preview;
  }
  window.mostrarCorpusNovo=(target,data)=>{
    target.replaceChildren(element('p',`${Leitura.quantidade(data.documentos_novos.length,'documento novo','documentos novos')} · ${data.total_documentos} no total.`));
    const list=element('ul',undefined,'document-list');
    for(const doc of data.documentos_novos){
      const row=element('li',Leitura.nome(doc));
      for(const warning of Leitura.lacunas(doc)) row.append(element('p',warning,'notice'));
      list.append(row);
    }
    target.append(list,element('p',data.rodada_atual?'Versão incorporada nesta rodada. As conferências anteriores foram preservadas; os novos achados começam pendentes.':'O comparativo usará a última resposta concluída desta conversa. As conferências anteriores serão preservadas; os novos achados começarão pendentes.','small'),
      Leitura.tecnicos(`${data.corpus_anterior} → ${data.corpus_novo} · comparação com ${data.rodada_anterior}`));
  };
  async function refresh(version=sequence){
    preview=null; $('continuidade-previa').hidden=true; controls();
    const result=await api('codex-corpus-previa',scope);
    if(version!==sequence||!dialog.open) return;
    preview=result; window.mostrarCorpusNovo($('continuidade-documentos'),result);
    $('continuidade-previa').hidden=false; controls();
  }
  $('codex-continuar-documentos').addEventListener('click',()=>{
    const current=window.estadoConversa(); if(current.ocupada||!current.conversa)return;
    scope={caso:current.caso,conversa:current.conversa}; preview=null; ++sequence;
    $('continuidade-cadastro').reset(); $('continuidade-previa').hidden=true;
    $('continuidade-recibo').hidden=true; $('continuidade-recibo').replaceChildren();
    $('continuidade-status').textContent='O cadastro registra os arquivos antes da próxima pergunta; não inicia a análise.';
    fail(); controls(); dialog.showModal();
  });
  $('continuidade-fechar').addEventListener('click',()=>{if(!busy)dialog.close();});
  dialog.addEventListener('cancel',e=>{if(busy)e.preventDefault();});
  dialog.addEventListener('close',()=>{++sequence;scope=null;preview=null;});
  $('continuidade-atualizar').addEventListener('click',async()=>{
    if(busy||!scope)return;busy=true;controls();fail();
    try{await refresh();$('continuidade-status').textContent='Confira a versão antes de usá-la na próxima pergunta.';}
    catch(error){fail(error.message);}finally{busy=false;controls();}
  });
  $('continuidade-cadastro').addEventListener('submit',async event=>{
    event.preventDefault();if(busy||!scope)return;
    const files=[...$('continuidade-arquivos').files]; if(!files.length)return;
    if(files.reduce((n,f)=>n+f.size,0)>50*1024*1024){fail('O lote excede 50 MB. Divida os arquivos em lotes menores.');return;}
    busy=true;preview=null;controls();fail();$('continuidade-previa').hidden=true;
    $('continuidade-status').textContent='Cadastrando os arquivos e conferindo o recibo…';
    try{
      const arquivos=await Promise.all(files.map(encodeFile));
      const result=await api('codex-documentos-cadastrar',{...scope,arquivos,natureza:$('continuidade-natureza').value});
      if(result.recebidos!==files.length||result.arquivos.length!==files.length)throw new Error('Recibo incompleto; confira o cadastro antes de continuar.');
      const receipt=$('continuidade-recibo');receipt.replaceChildren(element('h3','Recibo do lote'),
        element('p',`${result.recebidos} recebidos · ${result.novos} novos · ${result.duplicados} duplicados.`));
      for(const file of result.arquivos){
        receipt.append(element('p',`${file.nome_recebido} · ${file.estado}`));
        if(file.extracao_pdf) receipt.append(element('p',`${file.extracao_pdf.paginas_com_texto} de ${file.extracao_pdf.paginas_pdf??'?'} páginas com texto. Estado: ${file.extracao_pdf.estado}.`,'small'));
      }
      receipt.append(Leitura.tecnicos(element('pre',JSON.stringify(result,null,2),'raw-briefing')));receipt.hidden=false;
      $('continuidade-arquivos').value='';$('continuidade-status').textContent='Lote cadastrado. A conversa ainda não mudou de versão.';
      try{await refresh();}catch(error){fail(error.message);}
    }catch(error){fail(error.message);$('continuidade-status').textContent='O recebimento não foi confirmado nesta tela. Confira os documentos cadastrados; reenvios identificam duplicatas.';}
    finally{busy=false;controls();}
  });
  $('continuidade-usar').addEventListener('click',()=>{
    if(busy||!preview)return;
    try{window.selecionarCorpusNovo(preview);dialog.close();}catch(error){fail(error.message);}
  });
  window.mostrarComparativo=(target,data,chat)=>{
    const scope={caso:data.caso_id,rodada:data.rodada_atual,revisao:data.revisao_atual,geracao:'g1'};
    target.append(element('h3','O que mudou com os novos documentos'),element('p',data.limitacao,'small'));
    function section(title){const block=element('section',undefined,'comparison-section');block.append(element('h4',title));target.append(block);return block;}
    function openClaim(claim){
      const button=element('button','Ver achado e fontes','secondary');button.type='button';
      button.addEventListener('click',()=>window.abrirAchadosDaRodada(scope,claim.id).catch(error=>{button.after(element('p',error.message,'notice'));}));
      return button;
    }
    const evidence=section('Evidências novas');
    if(!data.evidencias_novas.length)evidence.append(element('p','Nenhuma evidência dos novos documentos foi publicada como suporte nesta rodada.','small'));
    for(const item of data.evidencias_novas){
      const block=element('article',undefined,'feedback-item');
      block.append(element('p',Leitura.fonte({...item,...item.localizador})),element('blockquote',item.trecho||'Fonte visual: consulte o original.'));
      const source=element('a','Abrir fonte lida nesta rodada');source.href='#fonte-'+item.referencia_atual;
      source.addEventListener('click',event=>{event.preventDefault();const card=$('fonte-'+item.referencia_atual);if(card){$('codex-painel-fontes').open=true;card.open=true;card.scrollIntoView({block:'center'});card.querySelector('blockquote').focus();}});
      const original=element('button','Baixar original','secondary');original.type='button';
      original.addEventListener('click',async()=>{
        original.disabled=true;try{download(await api('codex-original',{conversa:chat,referencia:item.referencia_atual},true),item.original.split('/').pop());}
        catch(error){block.append(element('p',error.message,'notice'));}finally{original.disabled=false;}
      });block.append(source,original);evidence.append(block);
    }
    for(const [kind,title]of [['alterada','Conclusões alteradas'],['pendencia_respondida','Pendências respondidas'],['nova','Achados novos'],['mantida','Conclusões mantidas'],['nao_retomada','Achados não retomados']]){
      const block=section(title),entries=data.comparacoes.filter(e=>e.tipo===kind);
      if(!entries.length)block.append(element('p','Nenhum registro nesta categoria.','small'));
      for(const entry of entries){
        const card=element('article',undefined,'feedback-item');
        for(const claim of entry.anteriores)card.append(element('p',`Antes · ${claim.redacao}`),Leitura.tecnicos(`${data.rodada_anterior} · ${claim.id}@v${claim.versao}`));
        for(const claim of entry.atuais)card.append(element('p',`Agora · ${claim.redacao}`),element('p',`Suporte da IA: ${pretty(claim.suporte)}`,'small'),openClaim(claim));
        card.append(element('p',`Avaliação da IA: ${entry.justificativa}`,'small'));block.append(card);
      }
    }
    const review=section('Achados para nova conferência');
    review.append(element('p','Todos os achados da nova rodada começam pendentes. Estes se destacam por serem novos, alterados ou terem evidência de documento novo.','small'));
    if(!data.nova_conferencia.length)review.append(element('p','Nenhum achado destacado nesta rodada.','small'));
    for(const claim of data.nova_conferencia)review.append(element('p',claim.redacao),openClaim(claim));
    if(data.documentos_novos_sem_leitura_registrada.length)target.append(element('p',`Há documentos novos sem leitura registrada: ${data.documentos_novos_sem_leitura_registrada.map(id=>Leitura.nome(data.documentos_novos.find(d=>d.id===id))).join(', ')}. A comparação não cobre seu conteúdo.`,'notice'));
    const exportButton=element('button','Exportar comparativo · texto com referências','secondary');exportButton.type='button';
    exportButton.addEventListener('click',()=>window.exportarEditorial(data,`comparativo_${data.rodada_anterior}_${data.rodada_atual}`));
    const jsonButton=element('button','Dados técnicos · JSON','secondary');jsonButton.type='button';jsonButton.addEventListener('click',()=>window.exportarEditorial(data,`comparativo_${data.rodada_anterior}_${data.rodada_atual}`,'json'));target.append(jsonButton);
    target.append(exportButton,Leitura.tecnicos(element('pre',JSON.stringify(data,null,2),'raw-briefing')));
  };
})();
// Resume summary at the case entry (POST /api/continuidade-resumo): what is finished and what is
// still open, each pending item linked to the Mesa area that resolves it. Metadata only: draft
// text never leaves the drafts module. Other screens use Continuidade.resumo / renderResumo.
window.Continuidade = (() => {
  const t = (texto, vars) => window.I18N ? window.I18N.t(texto, vars)
    : Object.entries(vars || {}).reduce((fim, [nome, valor]) => fim.split(`{${nome}}`).join(String(valor)), texto);
  const ETAPAS = {inventario: 'inventário', plano: 'plano', busca: 'busca', geracao_inicial: 'geração inicial',
    revisao: 'revisão', sintese: 'síntese'};
  const MOTIVOS = {sem_extracao: 'PDF sem extração textual registrada: {nome}', protegido: 'PDF protegido por senha: {nome}',
    falha_extracao: 'Falha na extração do texto: {nome}', paginas_com_erro: 'Páginas com falha de extração: {nome}',
    paginas_sem_texto: 'Páginas sem texto extraível: {nome}'};
  const QUADROS = {hipoteses: ['Hipóteses em aberto: {n}', 'Não foi possível ler o quadro de hipóteses.'],
    diligencias: ['Diligências em andamento: {n}', 'Não foi possível ler as diligências.'],
    tabelas: ['Tabelas com células pendentes: {n}', 'Não foi possível ler as tabelas.']};
  const TELAS = [['pergunta', 'Pergunta em preparo guardada às {hora}'], ['quadro-revisao', 'Revisão de achado guardada às {hora}'],
    ['quadro-caderno', 'Seleção para o caderno guardada às {hora}'], ['quadro-diligencias-resposta', 'Resposta de diligência guardada às {hora}'],
    ['quadro-diligencias', 'Diligência em preparo guardada às {hora}'], ['caderno', 'Nota do caderno guardada às {hora}']];
  const etapa = nome => ETAPAS[nome] ? t(ETAPAS[nome]) : String(nome);
  const hora = iso => { const d = new Date(iso || ''); return Number.isNaN(d.getTime()) ? '--:--' : `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`; };
  const rotuloTela = r => t((TELAS.find(([p]) => r.tela === p || r.tela.startsWith(p + '/')) || [null, 'Rascunho guardado às {hora}'])[1], {hora: hora(r.atualizado_em_utc)});
  const sequencias = new WeakMap();  // container -> number of its latest montar() call
  const resumo = caso => api('continuidade-resumo', {caso});
  // The server announces the route in /api/integracao; an older server, or one that fails, hides the summary.
  let anuncio = null;
  const disponivel = () => (anuncio ||= fetch('/api/integracao').then(r => r.ok ? r.json() : {}).catch(() => ({})))
    .then(dados => dados?.continuidade_resumo === true);
  function ligacao(texto, area) {
    const item = element('li'), link = element('a', texto);
    link.href = window.enderecoAreaMesa ? window.enderecoAreaMesa(area) : `?area=${encodeURIComponent(area)}`;
    link.dataset.area = area;
    link.addEventListener('click', evento => {
      if (evento.ctrlKey || evento.metaKey || evento.shiftKey || evento.altKey || evento.button) return;
      evento.preventDefault(); showArea(area);
    });
    item.append(link); return item;
  }
  function concluidos(dados) {
    const itens = [Leitura.quantidade(dados.documentos.cadastrados, 'documento cadastrado', 'documentos cadastrados')];
    const r = dados.rodada;
    if (r && r.concluida) itens.push(t('Análise {id} concluída: todas as etapas aceitas.', {id: r.id}));
    else if (r && r.etapa_concluida) itens.push(t('Análise {id}: concluída até a etapa «{etapa}».', {id: r.id, etapa: etapa(r.etapa_concluida)}));
    for (const q of dados.quadros) if (!q.erro && q.total && !q.pendentes) itens.push(t({hipoteses: 'Hipóteses sem pendência: {n}', diligencias: 'Diligências encerradas: {n}', tabelas: 'Tabelas sem célula pendente: {n}'}[q.quadro], {n: q.total}));
    return itens;
  }
  function pendentes(dados) {
    const itens = [];
    for (const d of dados.documentos.pendentes) itens.push(ligacao(t(MOTIVOS[d.motivo] || 'Documento com limitação: {nome}', {nome: d.nome}), 'documentos'));
    const r = dados.rodada;
    if (r && !r.concluida) itens.push(ligacao(r.estado_legivel ? t('Análise {id}: próxima etapa «{etapa}»', {id: r.id, etapa: etapa(r.proxima_etapa)})
      : t('Análise {id}: não foi possível ler o progresso.', {id: r.id}), 'codex'));
    for (const c of dados.conversas_interrompidas) itens.push(ligacao(t('Conversa interrompida, pronta para retomar: {titulo}', {titulo: c.titulo || c.id}), c.area));
    for (const q of dados.quadros) {
      const [texto, erro] = QUADROS[q.quadro] || ['{n}', ''];
      if (q.erro) itens.push(ligacao(t(erro), q.area)); else if (q.pendentes) itens.push(ligacao(t(texto, {n: q.pendentes}), q.area));
    }
    for (const r2 of dados.rascunhos) itens.push(ligacao(rotuloTela(r2), r2.area));
    return itens;
  }
  // Pure rendering, for any container: two lists, "Concluído" and "Pendente".
  function renderResumo(alvo, dados) {
    const caixa = element('section', undefined, 'continuidade-resumo');
    caixa.setAttribute('aria-label', 'Retomada da apuração');
    const feito = element('div', undefined, 'mesa-resume-done'), falta = element('div', undefined, 'mesa-resume-pending');
    const listaFeito = element('ul', undefined, 'mesa-resume-list');
    for (const texto of concluidos(dados)) listaFeito.append(element('li', texto));
    const itens = pendentes(dados), listaFalta = element('ul', undefined, 'mesa-resume-list');
    if (itens.length) listaFalta.append(...itens); else listaFalta.append(element('li', 'Nada pendente nesta apuração.'));
    feito.append(element('p', 'CONCLUÍDO', 'eyebrow'), listaFeito);
    falta.append(element('p', 'PENDENTE', 'eyebrow'), listaFalta);
    caixa.append(feito, falta, element('p', dados.aviso, 'small'));
    caixa.dataset.caso = dados.caso;
    alvo.replaceChildren(caixa);
    return caixa;
  }
  // Fetch and render into `alvo`; a newer call on the same container drops its older answer.
  // The sequence is per container: two screens (home card and boards) can mount at the same time.
  async function montar(alvo, caso) {
    const pedido = (sequencias.get(alvo) || 0) + 1;
    sequencias.set(alvo, pedido);
    alvo.replaceChildren(element('p', 'Verificando o que falta…', 'small'));
    try {
      const dados = await resumo(caso);
      if (pedido !== sequencias.get(alvo) || !alvo.isConnected) return null;
      return renderResumo(alvo, dados);
    } catch (erro) {
      if (pedido === sequencias.get(alvo)) alvo.replaceChildren(element('p', 'Não foi possível montar o resumo agora.', 'notice'));
      return null;
    }
  }
  return {resumo, renderResumo, montar, disponivel};
})();
