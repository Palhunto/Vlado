'use strict';
// Web sources per case ("documentos + web" mode). The mode and the single allowed site are
// chosen when the case is created. Captured text is shown as data (textContent in <pre>),
// never as HTML; the raw page is never rendered in the browser.
(() => {
  const el = id => document.getElementById(id);
  const t = (texto, vars) => (window.I18N ? window.I18N.t(texto, vars) : texto.replace(/\{(\w+)\}/g, (_, k) => vars?.[k] ?? ''));
  const MODO_WEB = 'documentos_web';
  let caso = '', sequencia = 0, ocupado = false;

  function erro(mensagem = '') {
    el('fontes-web-erro').textContent = mensagem;
    el('fontes-web-erro').hidden = !mensagem;
  }

  function alternarDominio() {
    const web = el('cadastro-modo-fontes').value === MODO_WEB && !el('cadastro-modo-fontes').disabled;
    el('cadastro-dominio-campo').hidden = !web;
    el('cadastro-dominio').required = web;
    el('cadastro-dominio').disabled = !web;
  }

  function alternarNovo(novo) {
    el('cadastro-modo-fontes').disabled = !novo;
    alternarDominio();
    if (novo) { caso = ''; el('fontes-web').hidden = true; }
  }

  function escopoNovo() {
    const modo = el('cadastro-modo-fontes').value;
    return modo === MODO_WEB
      ? {modo_fontes: modo, dominio_permitido: el('cadastro-dominio').value.trim()}
      : {modo_fontes: 'somente_documental'};
  }

  function linhaCaptura(item) {
    const row = document.createElement('li');
    const titulo = document.createElement('strong');
    titulo.textContent = `${item.id} · ${item.url_final}`;
    titulo.setAttribute('translate', 'no');
    const meta = document.createElement('span');
    meta.className = 'small';
    meta.textContent = ' ' + t('Acesso em {data} · HTTP {status} · SHA-256 {hash}…',
      {data: item.acessado_em_utc, status: item.status_http, hash: String(item.sha256).slice(0, 12)});
    const abrir = document.createElement('button');
    abrir.type = 'button';
    abrir.className = 'secondary';
    abrir.textContent = t('Abrir texto capturado');
    abrir.setAttribute('aria-label', t('Abrir texto capturado de {id}', {id: item.id}));
    abrir.addEventListener('click', () => ler(item.id));
    row.append(titulo, meta, ' ', abrir);
    return row;
  }

  async function listar() {
    const atual = ++sequencia, alvo = caso;
    try {
      const data = await api('fontes-web-listar', {caso: alvo});
      if (atual !== sequencia || alvo !== caso) return;
      el('fontes-web-lista').replaceChildren(...data.capturas.map(linhaCaptura));
      el('fontes-web-status').textContent = data.capturas.length
        ? t('{n} página(s) capturada(s) nesta apuração.', {n: data.capturas.length})
        : t('Nenhuma página capturada ainda.');
    } catch (failure) { if (atual === sequencia) erro(failure.message); }
  }

  async function ler(id) {
    erro();
    try {
      const data = await api('fontes-web-abrir', {caso, captura: id});
      const c = data.captura;
      el('fontes-web-leitura-titulo').textContent = c.titulo_pagina ? `${c.id} · ${c.titulo_pagina}` : c.id;
      el('fontes-web-leitura-meta').textContent = `${c.url_final} · ${c.acessado_em_utc} · SHA-256 ${c.sha256}`;
      el('fontes-web-texto').textContent = data.texto ?? t('Captura sem cópia textual; confira o conteúdo preservado.');
      el('fontes-web-leitura').hidden = false;
      el('fontes-web-leitura-titulo').focus?.();
    } catch (failure) { erro(failure.message); }
  }

  function mostrar(inventario) {
    const bloco = inventario?.fontes_web;
    if (!bloco || bloco.modo !== MODO_WEB) { el('fontes-web').hidden = true; caso = ''; return; }
    if (caso !== inventario.caso_id) el('fontes-web-leitura').hidden = true;
    caso = inventario.caso_id;
    el('fontes-web-dominio').textContent = t('Site permitido: {dominio}. Páginas de outros sites são recusadas.',
      {dominio: bloco.dominio_permitido});
    el('fontes-web').hidden = false;
    erro();
    listar();
  }

  function iniciar() {
    if (!el('fontes-web') || !el('cadastro-modo-fontes')) return;
    el('cadastro-modo-fontes').addEventListener('change', alternarDominio);
    el('fontes-web-form').addEventListener('submit', async event => {
      event.preventDefault();
      if (ocupado || !caso) return;
      erro();
      ocupado = true;
      el('fontes-web-capturar').disabled = true;
      el('fontes-web-status').textContent = t('Capturando a página…');
      try {
        const observacao = el('fontes-web-observacao').value.trim();
        const data = await api('fontes-web-capturar', {caso, url: el('fontes-web-url').value.trim(),
          ...(observacao ? {observacao} : {})});
        el('fontes-web-url').value = '';
        el('fontes-web-observacao').value = '';
        await listar();
        el('fontes-web-status').textContent = t('Captura {id} registrada. Corpus: {corpus}.',
          {id: data.captura.id, corpus: data.corpus_id});
      } catch (failure) {
        erro(failure.message);
        el('fontes-web-status').textContent = t('Nada foi registrado.');
      } finally {
        ocupado = false;
        el('fontes-web-capturar').disabled = false;
      }
    });
    alternarDominio();
  }

  window.FontesWeb = {alternarNovo, escopoNovo, mostrar};
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar);
  else iniciar();
})();
