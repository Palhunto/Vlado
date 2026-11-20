'use strict';
// All source/model text enters the page as text nodes. No HTML or remote media.
window.Leitura = (() => {
  const node = (tag, text, className) => {
    const item = document.createElement(tag);
    if (text !== undefined) item.textContent = text;
    if (className) item.className = className;
    return item;
  };
  function nome(doc) {
    if (doc.titulo_documento) return doc.titulo_documento;
    const raw = doc.titulo_documento || doc.nome_documento || doc.nome_recebido || doc.original || doc.arquivo || 'Documento';
    let title = raw.split(/[\\/]/).pop().replace(/^D\d+[_ -]+/, '')
      .replace(/\.(pdf|txt|md|csv|tsv|docx|xlsx|png|jpe?g)$/i, '').replace(/_/g, ' ').replace(/\s+/g, ' ').trim();
    // Only reformat an explicit date in the filename; never infer a document date.
    title = title.replace(/\b(20\d{2})[ .-](\d{2})[ .-](\d{2})\b/g, '$3/$2/$1')
      .replace(/\b(\d{2})[ .-](\d{2})[ .-](20\d{2})\b/g, '$1/$2/$3');
    title = title.replace(/^fatos? relevantes?\s*(?:de\s+)?(\d{2}\/\d{2}\/\d{4})$/i, 'Fato relevante de $1');
    return title || 'Documento';
  }
  const quantidade = (n, singular, plural = singular + 's') => `${n} ${n === 1 ? singular : plural}`;
  // Locator words follow the interface language; the values come from the record unchanged.
  const PALAVRAS = {
    pt: {pagina: 'p.', linhas: 'linhas', linha: 'linha', ausente: 'localizador não informado',
      planilha: 'planilha', aba: 'aba', tabela: 'tabela', celula: 'célula', intervalo: 'intervalo', regiao: 'região', secao: 'seção'},
    en: {pagina: 'page', linhas: 'lines', linha: 'line', ausente: 'locator not given',
      planilha: 'sheet', aba: 'tab', tabela: 'table', celula: 'cell', intervalo: 'range', regiao: 'region', secao: 'section'},
  };
  function localizador(hit, lingua = window.I18N?.idioma?.() || 'pt') {
    const words = PALAVRAS[lingua] || PALAVRAS.pt;
    const text = value => typeof value === 'string' ? value.trim() : typeof value === 'number' && Number.isFinite(value) ? String(value) : '';
    const loc = hit.localizador && typeof hit.localizador === 'object' ? hit.localizador : {};
    const page = text(hit.pagina_pdf) || text(loc.pagina_pdf);
    if (page) return `${words.pagina} ${page}`;
    const first = text(hit.linha_inicio) || text(loc.linha_inicio), last = text(hit.linha_fim) || text(loc.linha_fim);
    if (first) return last && last !== first ? `${words.linhas} ${first}–${last}` : `${words.linha} ${first}`;
    const description = text(hit.localizador) || text(loc.descricao) || text(hit.descricao);
    if (description) return description;
    const parts = [];
    for (const key of ['planilha','aba','tabela','celula','intervalo','regiao','secao']) {
      const value = text(loc[key]) || text(hit[key]);
      if (value) parts.push(`${words[key]} ${value}`);
    }
    return parts.join(' · ') || words.ausente;
  }
  function fonte(hit, lingua) {
    return `${nome(hit)} · ${localizador(hit, lingua)}`;
  }
  // PDF page cited by a source, when the record states one; never inferred.
  function pagina(hit) {
    const loc = hit.localizador && typeof hit.localizador === 'object' ? hit.localizador : {};
    const page = Number(hit.pagina_pdf ?? loc.pagina_pdf);
    return Number.isSafeInteger(page) && page > 0 ? page : null;
  }
  // One label for the action that opens the original, wherever it appears.
  const rotuloOriginal = page => page ? `Ver página ${page} no original` : 'Abrir original';
  // Author of a human record: the pilot account signs it; otherwise the name was typed by the user.
  const CONTA = new Set(['humana_autenticada_pela_conta_da_mesa', 'conta_autenticada_da_mesa']);
  function autoria(nome, origem) {
    const t = (texto, vars) => window.I18N ? window.I18N.t(texto, vars) : texto.replace('{nome}', vars?.nome ?? '').replace('{origem}', vars?.origem ?? '');
    return t('Autor: {nome} · {origem}', {nome, origem:t(CONTA.has(origem) ? 'autenticado pela conta da Mesa' : 'declarado pelo usuário')});
  }
  function tecnicos(...content) {
    const details = node('details', undefined, 'technical');
    details.append(node('summary', 'Detalhes técnicos'));
    for (const item of content) details.append(typeof item === 'string' ? node('p', item, 'small path') : item);
    return details;
  }
  function lacunas(doc) {
    const info = doc.extracao_pdf, messages = [];
    if (info?.paginas_sem_texto?.length) messages.push(`Sem texto extraível: páginas ${info.paginas_sem_texto.join(', ')}. Consulte essas páginas no original; a busca textual não as cobre.`);
    if (info?.paginas_com_erro?.length) messages.push(`Falha de extração nas páginas ${info.paginas_com_erro.map(p => p.pagina_pdf).join(', ')}. O original foi preservado.`);
    if (info?.paginas_ocr?.length) messages.push(`Páginas ${info.paginas_ocr.join(', ')} vieram de OCR automático e podem conter erros. Confira essas páginas no original.`);
    if (info?.protegido) messages.push('PDF protegido por senha: o texto não foi extraído. Consulte o original.');
    else if (info?.estado === 'erro' && !info.paginas_com_erro?.length) messages.push('Não foi possível extrair o texto deste PDF. Consulte o original.');
    if (!info && /\.pdf$/i.test(doc.nome_recebido || doc.nome_documento || doc.arquivo || doc.original || '')) messages.push('PDF sem extração textual registrada. Consulte o original.');
    return messages;
  }
  function inline(parent, text, citation, depth = 0) {
    if (depth > 8) { parent.append(document.createTextNode(text)); return; }
    let i = 0, buffer = '';
    const flush = () => { if (buffer) { parent.append(document.createTextNode(buffer)); buffer = ''; } };
    while (i < text.length) {
      if (text[i] === '\\' && i + 1 < text.length && /[\\`*_[\]{}()#+.!>-]/.test(text[i + 1])) {
        buffer += text[i + 1]; i += 2; continue;
      }
      if (text.startsWith('[fonte:', i)) {
        const match = /^\[fonte:([^\]\n]{1,200})\]/.exec(text.slice(i));
        if (match && citation) {
          flush(); const cited = citation(match[1]); i += match[0].length;
          // Punctuation right after a citation stays on its line.
          const tail = /^[,.;:!?)\]»”]+/.exec(text.slice(i));
          if (tail) { const keep = node('span', undefined, 'citation-keep'); keep.append(cited, node('span', tail[0])); parent.append(keep); i += tail[0].length; }
          else parent.append(cited);
          continue;
        }
      }
      if (text[i] === '`') {
        const marker = /^`+/.exec(text.slice(i))[0], end = text.indexOf(marker, i + marker.length);
        if (end >= 0) { flush(); parent.append(node('code', text.slice(i + marker.length, end))); i = end + marker.length; continue; }
      }
      const marker = text.startsWith('**', i) || text.startsWith('__', i) ? text.slice(i, i + 2)
        : text[i] === '*' || (text[i] === '_' && !/[\p{L}\p{N}]/u.test(text[i - 1] || ' ')) ? text[i] : '';
      if (marker) {
        const end = text.indexOf(marker, i + marker.length);
        if (end > i + marker.length) {
          flush(); const emphasis = node(marker.length === 2 ? 'strong' : 'em');
          inline(emphasis, text.slice(i + marker.length, end), citation, depth + 1);
          parent.append(emphasis); i = end + marker.length; continue;
        }
      }
      if (text[i] === '[' && text[i - 1] !== '!') {
        const match = /^\[([^\]\n]+)\]\(([^\s)]+)\)/.exec(text.slice(i));
        if (match && /^(https?:\/\/|#[A-Za-z0-9_-])/.test(match[2])) {
          flush(); const link = node('a'); link.href = match[2];
          if (/^https?:/.test(match[2])) { link.target = '_blank'; link.rel = 'noopener noreferrer'; }
          inline(link, match[1], null, depth + 1); parent.append(link); i += match[0].length; continue;
        }
      }
      buffer += text[i++];
    }
    flush();
  }
  function markdown(target, text, citation) {
    target.setAttribute('translate', 'no');  // model/human text keeps its own language
    const fragment = document.createDocumentFragment(), lines = String(text).replace(/\r\n?/g, '\n').split('\n');
    const appendInline = (tag, value, parent = fragment) => {
      const item = node(tag); inline(item, value, citation); parent.append(item); return item;
    };
    const cells = line => line.trim().replace(/^\||\|$/g, '').split(/(?<!\\)\|/).map(c => c.trim().replace(/\\\|/g, '|'));
    const separator = line => line.includes('|') && cells(line).every(c => /^:?-{3,}:?$/.test(c));
    let i = 0;
    while (i < lines.length) {
      const line = lines[i];
      if (!line.trim()) { i++; continue; }
      const fence = /^\s*(`{3,}|~{3,})(.*)$/.exec(line);
      if (fence) {
        const body = []; i++;
        while (i < lines.length && !new RegExp('^\\s*' + fence[1][0] + '{' + fence[1].length + ',}\\s*$').test(lines[i])) body.push(lines[i++]);
        if (i < lines.length) i++;
        const pre = node('pre'); pre.append(node('code', body.join('\n'))); fragment.append(pre); continue;
      }
      const heading = /^(#{1,6})\s+(.+?)\s*#*\s*$/.exec(line);
      if (heading) { appendInline('h' + Math.min(heading[1].length + 2, 6), heading[2]); i++; continue; }
      if (i + 1 < lines.length && line.includes('|') && separator(lines[i + 1])) {
        const wrapper = node('div', undefined, 'markdown-table'), table = node('table'), head = node('thead'), row = node('tr');
        for (const value of cells(line)) { const cell = appendInline('th', value, row); cell.scope = 'col'; }
        head.append(row); table.append(head); const body = node('tbody'); i += 2;
        while (i < lines.length && lines[i].trim() && lines[i].includes('|')) {
          const tr = node('tr'); for (const value of cells(lines[i++])) appendInline('td', value, tr); body.append(tr);
        }
        table.append(body); wrapper.append(table); fragment.append(wrapper); continue;
      }
      const list = /^\s*(?:([-+*])|\d+[.)])\s+(.+)$/.exec(line);
      if (list) {
        const ordered = !list[1], container = node(ordered ? 'ol' : 'ul');
        if (ordered) container.start = parseInt(line.trim(), 10);
        while (i < lines.length) {
          const item = /^\s*(?:([-+*])|\d+[.)])\s+(.+)$/.exec(lines[i]);
          if (!item || Boolean(!item[1]) !== ordered) break;
          appendInline('li', item[2], container); i++;
        }
        fragment.append(container); continue;
      }
      if (/^>\s?/.test(line)) {
        const quote = [];
        while (i < lines.length && /^>\s?/.test(lines[i])) quote.push(lines[i++].replace(/^>\s?/, ''));
        appendInline('blockquote', quote.join('\n')); continue;
      }
      if (/^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/.test(line)) { fragment.append(node('hr')); i++; continue; }
      const paragraph = [line]; i++;
      while (i < lines.length && lines[i].trim() && !/^(?:#{1,6}\s|\s*[-+*]\s|\s*\d+[.)]\s|>|\s*`{3,}|\s*~{3,})/.test(lines[i]) && !(i + 1 < lines.length && separator(lines[i + 1]))) paragraph.push(lines[i++]);
      appendInline('p', paragraph.join('\n'));
    }
    target.replaceChildren(fragment);
  }
  return {nome, fonte, localizador, pagina, rotuloOriginal, autoria, tecnicos, lacunas, markdown, quantidade};
})();
