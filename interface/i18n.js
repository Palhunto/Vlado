'use strict';
// Bilingual UI (pt/en). Translates UI chrome only: data (answers, excerpts, notes)
// is skipped. Strings are matched exactly (trimmed) or by registered patterns,
// and the original Portuguese is kept so switching back restores it.
(() => {
  const ATRIBUTOS = ['title', 'placeholder', 'aria-label', 'alt'];
  // Data containers. A textarea's text is its value, so only its attributes are chrome.
  const DADOS = '[translate="no"], blockquote, pre, code, .markdown-body, .vditor, [contenteditable="true"], script, style';
  const IGNORAR = DADOS + ', textarea';
  const CHAVE = 'vlado-idioma';
  const fonte = window.VLADO_I18N_EN || {textos: {}, padroes: []};
  const textos = fonte.textos || {};
  const padroes = (fonte.padroes || []).map(([re, en]) => [new RegExp(re), en]);
  const nos = new WeakMap();        // Text node -> {orig, en}
  const atributos = new WeakMap();  // Element -> {attr: {orig, en}}
  let lingua = 'pt';

  function traduzir(pt) {
    const chave = String(pt).trim();
    if (!chave) return null;
    let en = textos[chave];
    if (en === undefined) {
      const regra = padroes.find(([re]) => re.test(chave));
      if (regra) en = chave.replace(regra[0], regra[1]);
    }
    if (en === undefined) return null;
    const inicio = String(pt).match(/^\s*/)[0], fim = String(pt).match(/\s*$/)[0];
    return inicio + en + fim;
  }
  function t(pt, vars) {
    let texto = lingua === 'en' ? (traduzir(pt) ?? pt) : pt;
    for (const [nome, valor] of Object.entries(vars || {})) texto = texto.split(`{${nome}}`).join(String(valor));
    return texto;
  }
  // Chrome placed inside data (a citation inside an answer) opts back in with translate="yes".
  function ignorado(el, seletor = IGNORAR) {
    if (!el || !el.closest) return true;
    const dado = el.closest(seletor);
    if (!dado) return false;
    const ilha = el.closest('[translate="yes"]');
    return !(ilha && ilha !== dado && dado.contains(ilha));
  }
  function texto(no) {
    if (ignorado(no.parentElement)) return;
    const registro = nos.get(no);
    if (lingua === 'en') {
      const orig = registro && no.data === registro.en ? registro.orig : no.data;
      const en = traduzir(orig);
      if (en === null) { nos.delete(no); return; }
      nos.set(no, {orig, en});
      if (no.data !== en) no.data = en;
    } else if (registro && no.data === registro.en) {
      no.data = registro.orig;
      nos.delete(no);
    }
  }
  function atributo(el, nome) {
    if (!el.hasAttribute(nome) || ignorado(el, DADOS)) return;
    const mapa = atributos.get(el) || {}, registro = mapa[nome], atual = el.getAttribute(nome);
    if (lingua === 'en') {
      const orig = registro && atual === registro.en ? registro.orig : atual;
      const en = traduzir(orig);
      if (en === null) { delete mapa[nome]; return; }
      mapa[nome] = {orig, en}; atributos.set(el, mapa);
      if (atual !== en) el.setAttribute(nome, en);
    } else if (registro && atual === registro.en) {
      el.setAttribute(nome, registro.orig);
      delete mapa[nome];
    }
  }
  function aplicar(raiz = document.body) {
    if (!raiz) return;
    if (raiz.nodeType === 3) { texto(raiz); return; }
    if (raiz.nodeType !== 1) return;
    for (const nome of ATRIBUTOS) atributo(raiz, nome);
    const walker = document.createTreeWalker(raiz, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
    for (let no = walker.nextNode(); no; no = walker.nextNode()) {
      if (no.nodeType === 3) texto(no);
      else for (const nome of ATRIBUTOS) atributo(no, nome);
    }
  }
  // Message for a failed API answer: the server's Portuguese as is, or English by its stable code.
  function erro(resposta) {
    const original = resposta?.erro || 'Não foi possível completar a operação.';
    if (lingua !== 'en') return original;
    const modelo = (fonte.erros || {})[resposta?.codigo];
    if (!modelo || resposta.codigo === 'erro') return `${fonte.erroGenerico || 'The server refused the operation.'} (${original})`;
    const vars = {...(resposta.parametros || {}), ...(Array.isArray(resposta.faltam) ? {faltam: resposta.faltam.join(', ')} : {})};
    return Object.entries(vars).reduce((texto, [nome, valor]) => texto.split(`{${nome}}`).join(String(valor)), modelo);
  }
  function idioma() { return lingua; }
  function definir(nova) {
    lingua = nova === 'en' ? 'en' : 'pt';
    document.documentElement.lang = lingua === 'en' ? 'en' : 'pt-BR';
    try { localStorage.setItem(CHAVE, lingua); } catch (_) { /* Storage may be blocked; the switch still works. */ }
    aplicar(document.body);
    const botao = document.getElementById('mesa-idioma');
    if (botao) {
      botao.textContent = lingua === 'en' ? 'Português' : 'English';
      botao.setAttribute('aria-label', lingua === 'en' ? 'Mudar para português' : 'Switch to English');
    }
    window.dispatchEvent(new CustomEvent('vlado-idioma', {detail: lingua}));
  }
  let salvo = '';
  try { salvo = localStorage.getItem(CHAVE) || ''; } catch (_) { /* Default language below. */ }
  const padrao = document.body && document.body.dataset.idiomaPadrao;
  lingua = ['pt', 'en'].includes(salvo) ? salvo : (padrao === 'en' ? 'en' : 'pt');
  window.I18N = {t, idioma, definir, aplicar, traduzir, erro};
  if (typeof MutationObserver === 'function' && document.documentElement) {
    new MutationObserver(registros => {
      if (lingua !== 'en') return;
      for (const r of registros) {
        if (r.type === 'childList') r.addedNodes.forEach(n => aplicar(n));
        else if (r.type === 'characterData') texto(r.target);
        else if (r.type === 'attributes') atributo(r.target, r.attributeName);
      }
    }).observe(document.documentElement, {subtree: true, childList: true, characterData: true,
      attributes: true, attributeFilter: ATRIBUTOS});
  }
  const iniciar = () => {
    const botao = document.getElementById('mesa-idioma');
    if (botao) botao.addEventListener('click', () => definir(lingua === 'en' ? 'pt' : 'en'));
    definir(lingua);
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar);
  else iniciar();
})();
