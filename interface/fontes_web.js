'use strict';
// Web sources per case ("documentos + web" mode). The mode and the single allowed site are
// chosen when the case is created. Captured text is shown as data (textContent in <pre>),
// never as HTML; the raw page is never rendered in the browser.
(() => {
  const el = id => document.getElementById(id);
  const t = (texto, vars) => (window.I18N ? window.I18N.t(texto, vars) : texto.replace(/\{(\w+)\}/g, (_, k) => vars?.[k] ?? ''));
  const MODO_WEB = 'documentos_web';
  let caso = '', sequencia = 0, ocupado = false;

  // O erro da captura (página de outro site, endereço inválido) vai ao campo do endereço, com o texto do servidor; a leitura de uma captura usa o aviso solto.
  function erro(mensagem = '', campo = false) {
    if (el('fontes-web-url')._estadoErro) window.Estados?.limparErroCampo(el('fontes-web-url'));
    if (campo && mensagem && window.Estados) {
      el('fontes-web-erro').hidden = true;
      el('fontes-web-url').closest('label').after(window.Estados.erroCampo(el('fontes-web-url'), mensagem));
      return;
    }
    el('fontes-web-erro').textContent = mensagem;
    el('fontes-web-erro').hidden = !mensagem;
  }

  // A data da captura, no idioma da Mesa e na hora de quem lê (o servidor guarda em UTC).
  function dataDa(iso) {
    const quando = new Date(iso);
    if (!iso || Number.isNaN(quando.getTime())) return '';
    try { return new Intl.DateTimeFormat(window.I18N?.idioma?.() === 'en' ? 'en' : 'pt-BR', {dateStyle: 'medium', timeStyle: 'short'}).format(quando); } catch { return String(iso); }
  }
  // Uma linha por captura: o título ou o endereço, a data e "Ler", que abre o texto logo abaixo.
  function linhaCaptura(item) {
    const row = document.createElement('li');
    const titulo = document.createElement('strong');
    titulo.textContent = item.titulo_pagina || item.url_final;
    titulo.setAttribute('translate', 'no');
    const meta = document.createElement('span');
    meta.className = 'small';
    meta.textContent = ` ${dataDa(item.acessado_em_utc)}`;
    const abrir = document.createElement('button');
    abrir.type = 'button';
    abrir.className = 'docs-ler';
    abrir.textContent = t('Ler');
    abrir.setAttribute('aria-label', t('Ler a página {id}', {id: item.titulo_pagina || item.url_final}));
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
      el('fontes-web-status').textContent = data.capturas.length ? '' : t('Nenhuma página capturada ainda.');
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
    // "Páginas de prefeitura.sp.gov.br": o domínio é dado da apuração e não se traduz.
    const dominio = document.createElement('span'); dominio.textContent = bloco.dominio_permitido; dominio.setAttribute('translate', 'no');
    el('fontes-web-titulo').replaceChildren(t('Páginas de'), ' ', dominio);
    el('fontes-web').hidden = false;
    erro();
    listar();
  }

  function iniciar() {
    if (!el('fontes-web')) return;
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
        erro(failure.message, true);
        el('fontes-web-status').textContent = t('Nada foi registrado.');
      } finally {
        ocupado = false;
        el('fontes-web-capturar').disabled = false;
      }
    });
  }

  window.FontesWeb = {mostrar};
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar);
  else iniciar();
})();
