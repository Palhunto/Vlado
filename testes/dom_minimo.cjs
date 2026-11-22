'use strict';
// Minimal DOM for vm-based contract tests. It parses the real index.html and runs the
// production scripts unchanged. No layout, no CSS cascade, no network: only the tree,
// attributes, selectors and events the interface scripts rely on.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const RAIZ = path.resolve(__dirname, '..', 'interface');
const VAZIOS = new Set(['area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'source', 'track', 'wbr']);
const TEXTO_BRUTO = new Set(['script', 'style', 'textarea', 'title']);
const BOOLEANOS = ['hidden', 'disabled', 'required', 'open', 'multiple', 'checked', 'inert', 'readOnly', 'autofocus', 'selected'];
const TEXTOS = ['id', 'title', 'name', 'placeholder', 'href', 'src', 'rel', 'target', 'lang', 'autocomplete', 'role', 'alt', 'min', 'max', 'step'];
const ENTIDADES = {amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' '};
const decodificar = texto => texto.replace(/&(#x?[0-9a-f]+|[a-z]+);/gi, (todo, nome) => {
  if (nome[0] === '#') return String.fromCodePoint(nome[1] === 'x' || nome[1] === 'X' ? parseInt(nome.slice(2), 16) : Number(nome.slice(1)));
  return ENTIDADES[nome.toLowerCase()] ?? todo;
});

class Evento {
  constructor(type, init = {}) {
    this.type = type; this.bubbles = !!init.bubbles; this.cancelable = !!init.cancelable;
    this.detail = init.detail; this.defaultPrevented = false; this.target = null; this.currentTarget = null;
    this._parar = false; this._pararJa = false;
    for (const [chave, valor] of Object.entries(init)) if (!(chave in this)) this[chave] = valor;
  }
  preventDefault() { this.defaultPrevented = true; }
  stopPropagation() { this._parar = true; }
  stopImmediatePropagation() { this._parar = true; this._pararJa = true; }
}

class No {
  constructor(tipo, doc) { this.nodeType = tipo; this.ownerDocument = doc; this.parentNode = null; this.childNodes = []; this._ouvintes = []; }
  get parentElement() { return this.parentNode && this.parentNode.nodeType === 1 ? this.parentNode : null; }
  get nextSibling() { const irmaos = this.parentNode?.childNodes || []; return irmaos[irmaos.indexOf(this) + 1] || null; }
  get previousSibling() { const irmaos = this.parentNode?.childNodes || []; return irmaos[irmaos.indexOf(this) - 1] || null; }
  get firstChild() { return this.childNodes[0] || null; }
  get lastChild() { return this.childNodes.at(-1) || null; }
  get isConnected() { let no = this; while (no.parentNode) no = no.parentNode; return no.nodeType === 9; }
  remove() { if (this.parentNode) { const irmaos = this.parentNode.childNodes; irmaos.splice(irmaos.indexOf(this), 1); this.parentNode = null; } }
  _normalizar(itens) {
    const lista = [];
    for (const item of itens) {
      if (item === null || item === undefined) continue;
      if (typeof item === 'string' || typeof item === 'number') lista.push(this.ownerDocument.createTextNode(String(item)));
      else if (item.nodeType === 11) { lista.push(...item.childNodes); }
      else lista.push(item);
    }
    for (const item of lista) item.remove();
    return lista;
  }
  _inserir(itens, indice) {
    const lista = this._normalizar(itens);
    for (const item of lista) item.parentNode = this;
    this.childNodes.splice(indice, 0, ...lista);
    return lista;
  }
  append(...itens) { this._inserir(itens, this.childNodes.length); }
  prepend(...itens) { this._inserir(itens, 0); }
  appendChild(item) { this.append(item); return item; }
  insertBefore(item, referencia) {
    if (!referencia) { this.append(item); return item; }
    const lista = this._normalizar([item]);
    for (const novo of lista) novo.parentNode = this;
    this.childNodes.splice(this.childNodes.indexOf(referencia), 0, ...lista);
    return item;
  }
  removeChild(item) { item.remove(); return item; }
  replaceChildren(...itens) { for (const filho of [...this.childNodes]) filho.remove(); this.append(...itens); }
  before(...itens) { const pai = this.parentNode; if (!pai) return; const lista = pai._normalizar(itens); for (const item of lista) item.parentNode = pai; pai.childNodes.splice(pai.childNodes.indexOf(this), 0, ...lista); }
  after(...itens) { const pai = this.parentNode; if (!pai) return; const lista = pai._normalizar(itens); for (const item of lista) item.parentNode = pai; pai.childNodes.splice(pai.childNodes.indexOf(this) + 1, 0, ...lista); }
  replaceWith(...itens) { const pai = this.parentNode; if (!pai) return; this.before(...itens); this.remove(); }
  contains(outro) { for (let no = outro; no; no = no.parentNode) if (no === this) return true; return false; }
  get textContent() { return this.childNodes.map(n => n.nodeType === 8 ? '' : n.textContent).join(''); }
  set textContent(valor) { this.replaceChildren(); if (valor !== '' && valor !== null && valor !== undefined) this.append(String(valor)); }
  addEventListener(tipo, funcao, opcoes) { if (funcao) this._ouvintes.push({tipo, funcao, captura: opcoes === true || !!opcoes?.capture}); }
  removeEventListener(tipo, funcao) { this._ouvintes = this._ouvintes.filter(o => o.tipo !== tipo || o.funcao !== funcao); }
  dispatchEvent(evento) {
    evento.target = this;
    const caminho = []; for (let no = this.parentNode; no; no = no.parentNode) caminho.push(no);
    if (this.ownerDocument?._janela && caminho.at(-1)?.nodeType === 9) caminho.push(this.ownerDocument._janela);
    const chamar = (no, fase) => {
      for (const ouvinte of [...no._ouvintes]) {
        if (ouvinte.tipo !== evento.type || evento._pararJa) continue;
        if (fase === 'captura' && !ouvinte.captura) continue;
        if (fase === 'bolha' && ouvinte.captura) continue;
        evento.currentTarget = no;
        const resultado = ouvinte.funcao.call(no, evento);
        if (resultado && typeof resultado.catch === 'function') resultado.catch(erro => this.ownerDocument._erros.push(erro));
      }
    };
    for (const no of [...caminho].reverse()) { if (evento._parar) break; chamar(no, 'captura'); }
    if (!evento._parar) chamar(this, 'alvo');
    if (evento.bubbles) for (const no of caminho) { if (evento._parar) break; chamar(no, 'bolha'); }
    return !evento.defaultPrevented;
  }
}

class Texto extends No {
  constructor(data, doc) { super(3, doc); this.data = data; }
  get textContent() { return this.data; }
  set textContent(valor) { this.data = String(valor); }
  get nodeValue() { return this.data; }
  cloneNode() { return new Texto(this.data, this.ownerDocument); }
}

class Comentario extends No {
  constructor(data, doc) { super(8, doc); this.data = data; }
  get textContent() { return ''; }
  cloneNode() { return new Comentario(this.data, this.ownerDocument); }
}

class Fragmento extends No {
  constructor(doc) { super(11, doc); }
  querySelectorAll(seletor) { return consultar(this, seletor); }
  querySelector(seletor) { return consultar(this, seletor, true)[0] || null; }
}

// Selector engine: lists, descendant/child combinators, tag, #id, .class, [attr], [attr=v],
// [attr^=v], [attr*=v], :not(...), :is(...), :checked and :scope.
function dividir(texto, separador) {
  const partes = []; let profundidade = 0, atual = '', aspas = '';
  for (const caractere of texto) {
    if (aspas) { atual += caractere; if (caractere === aspas) aspas = ''; continue; }
    if (caractere === '"' || caractere === "'") { aspas = caractere; atual += caractere; continue; }
    if (caractere === '(' || caractere === '[') profundidade++;
    if (caractere === ')' || caractere === ']') profundidade--;
    if (caractere === separador && profundidade === 0) { partes.push(atual); atual = ''; continue; }
    atual += caractere;
  }
  partes.push(atual);
  return partes.map(p => p.trim()).filter(Boolean);
}
function compostos(seletor) {
  const tokens = []; let atual = '', profundidade = 0, aspas = '';
  const fechar = () => { if (atual.trim()) tokens.push(atual.trim()); atual = ''; };
  for (const caractere of seletor.trim()) {
    if (aspas) { atual += caractere; if (caractere === aspas) aspas = ''; continue; }
    if (caractere === '"' || caractere === "'") { aspas = caractere; atual += caractere; continue; }
    if (caractere === '(' || caractere === '[') profundidade++;
    if (caractere === ')' || caractere === ']') profundidade--;
    if (profundidade === 0 && caractere === '>') { fechar(); tokens.push('>'); continue; }
    if (profundidade === 0 && /\s/.test(caractere)) { fechar(); continue; }
    atual += caractere;
  }
  fechar();
  const resultado = [];
  for (const token of tokens) {
    if (token === '>') resultado.push({combinador: '>'});
    else { if (resultado.length && !resultado.at(-1).combinador) resultado.push({combinador: ' '}); resultado.push({composto: token}); }
  }
  return resultado;
}
function casaComposto(el, composto, escopo) {
  let resto = composto;
  const tag = /^[a-z][a-z0-9-]*|^\*/i.exec(resto);
  if (tag) { if (tag[0] !== '*' && el.localName !== tag[0].toLowerCase()) return false; resto = resto.slice(tag[0].length); }
  while (resto) {
    let m;
    if ((m = /^#([\w-]+)/.exec(resto))) { if (el.getAttribute('id') !== m[1]) return false; }
    else if ((m = /^\.([\w-]+)/.exec(resto))) { if (!el.classList.contains(m[1])) return false; }
    else if ((m = /^\[([\w-]+)(?:([\^*]?=)(?:"([^"]*)"|'([^']*)'|([^\]]*)))?\]/.exec(resto))) {
      if (!el.hasAttribute(m[1])) return false;
      const esperado = m[3] ?? m[4] ?? m[5], valor = el.getAttribute(m[1]);
      if (m[2] === '=' && valor !== esperado) return false;
      if (m[2] === '^=' && !valor.startsWith(esperado)) return false;
      if (m[2] === '*=' && !valor.includes(esperado)) return false;
    } else if ((m = /^:(not|is)\(/.exec(resto))) {
      let profundidade = 1, i = m[0].length;
      for (; i < resto.length && profundidade; i++) { if (resto[i] === '(') profundidade++; if (resto[i] === ')') profundidade--; }
      const interno = resto.slice(m[0].length, i - 1), casa = dividir(interno, ',').some(s => casaComplexo(el, s, escopo));
      if (m[1] === 'not' ? casa : !casa) return false;
      m = [resto.slice(0, i)];
    } else if ((m = /^:checked/.exec(resto))) { if (!el.checked) return false; }
    else if ((m = /^:scope/.exec(resto))) { if (el !== escopo) return false; }
    else throw new Error(`Seletor não suportado pelo DOM mínimo: ${composto}`);
    resto = resto.slice(m[0].length);
  }
  return true;
}
function casaComplexo(el, seletor, escopo) {
  const partes = compostos(seletor);
  const casar = (no, indice) => {
    if (!casaComposto(no, partes[indice].composto, escopo)) return false;
    if (indice === 0) return true;
    const combinador = partes[indice - 1].combinador;
    if (combinador === '>') return !!no.parentElement && casar(no.parentElement, indice - 2);
    for (let pai = no.parentElement; pai; pai = pai.parentElement) if (casar(pai, indice - 2)) return true;
    return false;
  };
  return casar(el, partes.length - 1);
}
const casa = (el, seletor, escopo) => dividir(seletor, ',').some(s => casaComplexo(el, s, escopo));
function* descendentes(raiz) {
  for (const filho of raiz.childNodes) if (filho.nodeType === 1) { yield filho; yield* descendentes(filho); }
}
function consultar(raiz, seletor, primeiro = false) {
  const lista = [], id = /^#([\w-]+)$/.exec(seletor.trim());
  for (const el of descendentes(raiz)) {
    if (id ? el._atributos.get('id') === id[1] : casa(el, seletor, raiz)) { lista.push(el); if (primeiro) break; }
  }
  return lista;
}

class Elemento extends No {
  constructor(nome, doc) {
    super(1, doc); this.localName = nome.toLowerCase(); this.tagName = nome.toUpperCase();
    this._atributos = new Map(); this._valor = undefined; this.style = {setProperty() {}, removeProperty() {}};
    const el = this;
    this.dataset = new Proxy({}, {
      get: (_, chave) => typeof chave === 'string' ? el.getAttribute('data-' + chave.replace(/[A-Z]/g, c => '-' + c.toLowerCase())) ?? undefined : undefined,
      set: (_, chave, valor) => { el.setAttribute('data-' + chave.replace(/[A-Z]/g, c => '-' + c.toLowerCase()), valor); return true; },
      deleteProperty: (_, chave) => { el.removeAttribute('data-' + chave.replace(/[A-Z]/g, c => '-' + c.toLowerCase())); return true; },
      has: (_, chave) => el.hasAttribute('data-' + String(chave).replace(/[A-Z]/g, c => '-' + c.toLowerCase())),
      ownKeys: () => [...el._atributos.keys()].filter(k => k.startsWith('data-')).map(k => k.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase())),
      getOwnPropertyDescriptor: () => ({enumerable: true, configurable: true}),
    });
    this.classList = {
      contains: nome => (el.getAttribute('class') || '').split(/\s+/).includes(nome),
      add: (...nomes) => { const atual = new Set((el.getAttribute('class') || '').split(/\s+/).filter(Boolean)); nomes.forEach(n => atual.add(n)); el.setAttribute('class', [...atual].join(' ')); },
      remove: (...nomes) => { const atual = (el.getAttribute('class') || '').split(/\s+/).filter(n => n && !nomes.includes(n)); el.setAttribute('class', atual.join(' ')); },
      toggle: (nome, forcar) => { const ter = forcar === undefined ? !el.classList.contains(nome) : !!forcar; if (ter) el.classList.add(nome); else el.classList.remove(nome); return ter; },
    };
  }
  getAttribute(nome) { return this._atributos.has(nome.toLowerCase()) ? this._atributos.get(nome.toLowerCase()) : null; }
  setAttribute(nome, valor) { this._atributos.set(nome.toLowerCase(), String(valor)); }
  removeAttribute(nome) { this._atributos.delete(nome.toLowerCase()); }
  hasAttribute(nome) { return this._atributos.has(nome.toLowerCase()); }
  toggleAttribute(nome, forcar) { const ter = forcar === undefined ? !this.hasAttribute(nome) : !!forcar; if (ter) this.setAttribute(nome, ''); else this.removeAttribute(nome); return ter; }
  get attributes() { return [...this._atributos].map(([name, value]) => ({name, value})); }
  get className() { return this.getAttribute('class') || ''; }
  set className(valor) { this.setAttribute('class', valor); }
  get tabIndex() { const valor = this.getAttribute('tabindex'); return valor === null ? -1 : Number(valor); }
  set tabIndex(valor) { this.setAttribute('tabindex', valor); }
  get type() { return this.getAttribute('type') || (this.localName === 'button' ? 'submit' : this.localName === 'input' ? 'text' : ''); }
  set type(valor) { this.setAttribute('type', valor); }
  get children() { return this.childNodes.filter(n => n.nodeType === 1); }
  get firstElementChild() { return this.children[0] || null; }
  get lastElementChild() { return this.children.at(-1) || null; }
  get previousElementSibling() { const irmaos = this.parentNode?.childNodes.filter(n => n.nodeType === 1) || []; return irmaos[irmaos.indexOf(this) - 1] || null; }
  get nextElementSibling() { const irmaos = this.parentNode?.childNodes.filter(n => n.nodeType === 1) || []; return irmaos[irmaos.indexOf(this) + 1] || null; }
  get innerText() { return this.textContent; }
  get options() { return consultar(this, 'option'); }
  get selectedOptions() { return this.options.filter(o => o === this._selecionada()); }
  get selectedIndex() { return this.options.indexOf(this._selecionada()); }
  get elements() { return consultar(this, 'input,select,textarea,button'); }
  get form() { let no = this.parentElement; while (no && no.localName !== 'form') no = no.parentElement; return no; }
  _selecionada() {
    const opcoes = this.options;
    if (this._valor !== undefined) return opcoes.find(o => o.value === this._valor) || null;
    return opcoes.find(o => o.hasAttribute('selected')) || opcoes[0] || null;
  }
  get value() {
    if (this.localName === 'select') return this._selecionada()?.value ?? '';
    if (this.localName === 'option') return this.getAttribute('value') ?? this.textContent;
    if (this.localName === 'textarea') return this._valor ?? this.textContent;
    return this._valor ?? this.getAttribute('value') ?? '';
  }
  set value(valor) {
    if (this.localName === 'option') { this.setAttribute('value', valor); return; }
    if (this.localName === 'select') { this._valor = this.options.some(o => o.value === String(valor)) ? String(valor) : '\u0000nenhuma'; return; }
    this._valor = String(valor ?? '');
  }
  closest(seletor) { for (let no = this; no && no.nodeType === 1; no = no.parentNode) if (casa(no, seletor, no)) return no; return null; }
  matches(seletor) { return casa(this, seletor, this); }
  querySelectorAll(seletor) { return consultar(this, seletor); }
  querySelector(seletor) { return consultar(this, seletor, true)[0] || null; }
  getElementsByTagName(nome) { return consultar(this, nome); }
  focus() { this.ownerDocument.activeElement = this; }
  blur() { if (this.ownerDocument.activeElement === this) this.ownerDocument.activeElement = this.ownerDocument.body; }
  click() { if (this.disabled) return; this.dispatchEvent(new Evento('click', {bubbles: true, cancelable: true, button: 0, detail: 1})); }
  scrollIntoView() {}
  select() {}
  getBoundingClientRect() { return {top: 0, left: 0, width: 0, height: 0, right: 0, bottom: 0}; }
  showModal() { this.open = true; }
  show() { this.open = true; }
  close() { if (!this.open) return; this.open = false; this.dispatchEvent(new Evento('close')); }
  requestSubmit() { this.dispatchEvent(new Evento('submit', {bubbles: true, cancelable: true})); }
  reset() { for (const campo of this.elements) campo._valor = undefined; }
  replaceChildren(...itens) {
    // A new option list resets the selection, as in browsers.
    if (this.localName === 'select') this._valor = undefined;
    super.replaceChildren(...itens);
  }
  cloneNode(profundo = false) {
    const copia = new Elemento(this.localName, this.ownerDocument);
    for (const [nome, valor] of this._atributos) copia._atributos.set(nome, valor);
    if (profundo) copia.append(...this.childNodes.map(n => n.cloneNode(true)));
    return copia;
  }
}
for (const nome of BOOLEANOS) {
  Object.defineProperty(Elemento.prototype, nome, {
    get() { return this.hasAttribute(nome); },
    set(valor) { this.toggleAttribute(nome, !!valor); },
  });
}
for (const nome of TEXTOS) {
  Object.defineProperty(Elemento.prototype, nome, {
    get() { return this.getAttribute(nome) ?? ''; },
    set(valor) { this.setAttribute(nome, valor); },
  });
}

class Documento extends No {
  constructor() { super(9, null); this.ownerDocument = this; this._erros = []; this.readyState = 'complete'; this.activeElement = null; }
  createElement(nome) { return new Elemento(nome, this); }
  createElementNS(_, nome) { return new Elemento(nome, this); }
  createTextNode(texto) { return new Texto(texto, this); }
  createComment(texto) { return new Comentario(texto, this); }
  createDocumentFragment() { return new Fragmento(this); }
  get documentElement() { return this.childNodes.find(n => n.nodeType === 1) || null; }
  get head() { return this.documentElement?.querySelector('head') || null; }
  get body() { return this.documentElement?.querySelector('body') || null; }
  getElementById(id) { return consultar(this, `#${id}`, true)[0] || null; }
  querySelectorAll(seletor) { return consultar(this, seletor); }
  querySelector(seletor) { return consultar(this, seletor, true)[0] || null; }
  createTreeWalker(raiz, mostrar = 0xffffffff) {
    const lista = [];
    const visitar = no => { for (const filho of no.childNodes) { if ((filho.nodeType === 1 && mostrar & 1) || (filho.nodeType === 3 && mostrar & 4)) lista.push(filho); if (filho.nodeType === 1) visitar(filho); } };
    visitar(raiz);
    let indice = -1;
    return {currentNode: raiz, nextNode() { indice++; this.currentNode = lista[indice] || null; return this.currentNode; }};
  }
}

function analisar(html, doc) {
  const pilha = [doc];
  const topo = () => pilha.at(-1);
  let i = 0;
  while (i < html.length) {
    if (html.startsWith('<!--', i)) { const fim = html.indexOf('-->', i); topo().append(doc.createComment(html.slice(i + 4, fim))); i = fim + 3; continue; }
    if (html.startsWith('<!', i)) { i = html.indexOf('>', i) + 1; continue; }
    if (html.startsWith('</', i)) {
      const fim = html.indexOf('>', i), nome = html.slice(i + 2, fim).trim().toLowerCase();
      for (let p = pilha.length - 1; p > 0; p--) if (pilha[p].localName === nome) { pilha.length = p; break; }
      i = fim + 1; continue;
    }
    if (html[i] === '<' && /[a-z]/i.test(html[i + 1] || '')) {
      const etiqueta = /^<([a-z][a-z0-9-]*)/i.exec(html.slice(i));
      const el = doc.createElement(etiqueta[1]); i += etiqueta[0].length;
      const atributo = /^\s*([^\s"'>\/=]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?/;
      for (;;) {
        const resto = html.slice(i, i + 4000);
        const fechar = /^\s*(\/?)>/.exec(resto);
        if (fechar) { i += fechar[0].length; break; }
        const m = atributo.exec(resto);
        if (!m) throw new Error(`HTML inesperado perto de: ${resto.slice(0, 40)}`);
        el.setAttribute(m[1], decodificar(m[2] ?? m[3] ?? m[4] ?? ''));
        i += m[0].length;
      }
      topo().append(el);
      if (VAZIOS.has(el.localName)) continue;
      if (TEXTO_BRUTO.has(el.localName)) {
        const fim = html.toLowerCase().indexOf(`</${el.localName}`, i);
        const conteudo = html.slice(i, fim);
        if (conteudo) el.append(doc.createTextNode(el.localName === 'textarea' || el.localName === 'title' ? decodificar(conteudo) : conteudo));
        i = html.indexOf('>', fim) + 1; continue;
      }
      pilha.push(el); continue;
    }
    const proximo = html.indexOf('<', i + 1), fim = proximo < 0 ? html.length : proximo;
    topo().append(doc.createTextNode(decodificar(html.slice(i, fim))));
    i = fim;
  }
  return doc;
}

// Builds a window around index.html. `scripts` run in order in one shared realm, like
// deferred <script> tags. `api` answers POST /api/* and `catalogo` answers /api/catalogo.
const PILHA = ['i18n_en.js', 'i18n.js', 'leitura.js', 'dialogo.js', 'estados.js', 'envio.js', 'documentos.js', 'app.js', 'fontes_web.js', 'revisao.js', 'observacoes.js', 'continuidade.js', 'caderno.js',
  'editor_notas.js', 'apuracao.js', 'diligencias.js', 'codex.js', 'configuracao_ia.js', 'piloto.js', 'gerenciar.js',
  'experiencia.js', 'desktop.js'];

function criarMesa({url = 'http://127.0.0.1:8765/', papel = 'admin', modo = 'local', idioma = 'pt', desktop = true,
  catalogo = [], api = () => ({}), scripts = PILHA, armazenamento = {}, html, preparar = () => {}} = {}) {
  const doc = new Documento();
  analisar(html ?? fs.readFileSync(path.join(RAIZ, 'index.html'), 'utf8')
    .replace('__SESSION_TOKEN__', 'teste').replace('__PAPEL__', papel).replace('__MODO__', modo)
    .replace('__IDIOMA_PADRAO__', idioma), doc);
  const guardado = new Map(Object.entries(armazenamento));
  class URLMesa extends URL { static createObjectURL() { return 'blob:teste'; } static revokeObjectURL() {} }
  const chamadas = [];
  const localizacao = new URL(url);
  const janela = {
    document: doc, console, Map, Set, WeakMap, Promise, JSON, Math, Date, Intl, URL: URLMesa, URLSearchParams, Proxy, Reflect, Symbol, Array, Object,
    String, Number, Boolean, RegExp, Error, TypeError, structuredClone, setTimeout, clearTimeout, setInterval, clearInterval,
    queueMicrotask, Blob: class { constructor(partes = [], opcoes = {}) { this.partes = partes; this.type = opcoes.type || ''; } async text() { return this.partes.join(''); } },
    Event: Evento, CustomEvent: Evento, NodeFilter: {SHOW_ELEMENT: 1, SHOW_TEXT: 4},
    Option: function (texto = '', valor) { const op = doc.createElement('option'); op.textContent = texto; if (valor !== undefined) op.value = valor; return op; },
    MutationObserver: class { observe() {} disconnect() {} },
    ResizeObserver: class { observe() {} disconnect() {} },
    matchMedia: consulta => ({matches: /min-width:\s*1024px/.test(consulta) ? desktop : /max-width/.test(consulta) ? !desktop : false,
      media: consulta, addEventListener() {}, removeEventListener() {}}),
    localStorage: {getItem: chave => guardado.get(chave) ?? null, setItem: (chave, valor) => guardado.set(chave, String(valor)), removeItem: chave => guardado.delete(chave)},
    history: {
      pushState: (_, __, destino) => { localizacao.href = new URL(destino, localizacao.href).href; },
      replaceState: (_, __, destino) => { localizacao.href = new URL(destino, localizacao.href).href; },
    },
    location: localizacao,
    navigator: {clipboard: {writeText: async () => {}}},
    crypto: {randomUUID: () => '00000000-0000-4000-8000-000000000000'},
    confirm: () => true, alert: () => {}, scrollTo: () => {},
    requestAnimationFrame: funcao => setTimeout(funcao, 0),
    getComputedStyle: () => ({getPropertyValue: () => ''}),
    fetch: async (endereco, opcoes = {}) => {
      const rota = String(endereco);
      if (rota === '/api/catalogo') return {ok: true, json: async () => ({casos: catalogo})};
      if (rota === '/api/integracao') return {ok: true, json: async () => ({})};
      const operacao = rota.replace(/^\/api\//, ''), dados = opcoes.body ? JSON.parse(opcoes.body) : {};
      chamadas.push({operacao, dados});
      try {
        const resposta = await api(operacao, dados);
        return {ok: true, blob: async () => resposta, json: async () => resposta};
      } catch (erro) {
        // Like the real server: an error body may carry a stable `codigo` besides `erro`.
        return {ok: false, json: async () => (erro.result || {erro: erro.message})};
      }
    },
  };
  janela.window = janela; janela.self = janela; janela.globalThis = janela;
  janela._ouvintes = [];
  janela.addEventListener = No.prototype.addEventListener.bind(janela);
  janela.removeEventListener = No.prototype.removeEventListener.bind(janela);
  janela.dispatchEvent = evento => {
    evento.target = janela;
    for (const ouvinte of [...janela._ouvintes]) if (ouvinte.tipo === evento.type) {
      const resultado = ouvinte.funcao.call(janela, evento);
      if (resultado && typeof resultado.catch === 'function') resultado.catch(erro => doc._erros.push(erro));
    }
    return !evento.defaultPrevented;
  };
  doc._janela = janela;
  doc.defaultView = janela;
  vm.createContext(janela);
  preparar(janela);
  const executar = nome => vm.runInContext(fs.readFileSync(path.join(RAIZ, nome), 'utf8'), janela, {filename: nome});
  for (const nome of scripts) executar(nome);
  const esperar = async (voltas = 4) => { for (let v = 0; v < voltas; v++) await new Promise(setImmediate); };
  return {janela, doc, $: id => doc.getElementById(id), executar, esperar, chamadas, guardado, erros: doc._erros,
    avaliar: codigo => vm.runInContext(codigo, janela)};
}

module.exports = {criarMesa, Evento, PILHA};
