'use strict';
// Tela Documentos (docs/design/componentes.md#documentos, W02, P16): área de envio e lista de documentos com os estados de leitura.
//
//   Documentos.zona(alvo, {aoEscolher})            área de envio: arrastar ou escolher; "Escolher arquivos" no celular
//   Documentos.lista(alvo, inventario, opcoes)     tabela no desktop e cartões no celular (P16.3); opcoes: {consulta, limitacoes, abrir}
//   Documentos.leitura(doc)                        {chave, tom, sinal, texto, paginas}: os estados de leitura de um documento
//   Documentos.enviar(arquivos, contexto)          envio por arquivo para a apuração escolhida (envio.js)
//
// Três estados de leitura, sempre com sinal e texto (W02, regra 5): "✓ Texto do próprio arquivo", "Lida por OCR: confira números" e
// "○ Imagem sem leitura". Dois a mais, aprovados pelo Design: "Lida em parte" (páginas sem texto) e "Não foi lido" (erro ou PDF protegido).
// Hash, identificador e versão ficam em "Detalhes técnicos" de cada documento, nunca na lista (regra 7).
(() => {
  const t = (pt, vars) => (window.I18N ? window.I18N.t(pt, vars) : String(pt).replace(/\{(\w+)\}/g, (todo, nome) => vars?.[nome] ?? todo));
  const IMAGEM = /\.(png|jpe?g|gif|tiff?|bmp|webp)$/i;

  function no(etiqueta, classe, texto) {
    const elemento = document.createElement(etiqueta);
    if (classe) elemento.className = classe;
    if (texto !== undefined && texto !== null) elemento.textContent = texto;
    return elemento;
  }

  // Estado de leitura de um documento do inventário. `extracao_pdf` só existe nos PDFs; os demais formatos entram com o texto do arquivo.
  function leitura(doc) {
    const info = doc.extracao_pdf;
    const nome = doc.nome_recebido || doc.nome_documento || '';
    const total = info?.paginas_pdf ?? null;
    const semTexto = info?.paginas_sem_texto?.length || 0, comErro = info?.paginas_com_erro?.length || 0, viaOcr = info?.paginas_ocr?.length || 0;
    const base = {paginas: total};
    if (info?.protegido || (info?.estado === 'erro' && !comErro)) return {...base, chave: 'erro', tom: 'erro', sinal: 'sem-suporte', texto: t('Não foi lido. O original ficou guardado.')};
    if (info) {
      if (total && semTexto >= total) return {...base, chave: 'sem-leitura', tom: 'neutro', marca: '○', texto: t('Imagem sem leitura')};
      if (semTexto || comErro) return {...base, chave: 'parcial', tom: 'aviso', sinal: 'parcial', texto: t('Lida em parte: confira as páginas sem texto')};
      if (viaOcr) return {...base, chave: 'ocr', tom: 'aviso', sinal: 'parcial', texto: t('Lida por OCR: confira números')};
      return {...base, chave: 'texto', tom: 'ok', marca: '✓', texto: t('Texto do próprio arquivo')};
    }
    if (IMAGEM.test(nome)) return {...base, chave: 'sem-leitura', tom: 'neutro', marca: '○', texto: t('Imagem sem leitura')};
    if (/\.pdf$/i.test(nome)) return {...base, chave: 'erro', tom: 'erro', sinal: 'sem-suporte', texto: t('Não foi lido. O original ficou guardado.')};
    return {...base, chave: 'texto', tom: 'ok', marca: '✓', texto: t('Texto do próprio arquivo')};
  }

  function celulaLeitura(estado) {
    const celula = no('span', 'docs-leitura'); celula.dataset.tom = estado.tom; celula.dataset.leitura = estado.chave;
    if (estado.sinal) celula.append(window.Estados.sinal(estado.sinal));
    else if (estado.marca) { const marca = no('span', 'docs-marca', estado.marca); marca.setAttribute('aria-hidden', 'true'); celula.append(marca); }
    celula.append(estado.texto);
    return celula;
  }

  function tecnicos(doc, inventario) {
    const caixa = no('details', 'docs-tecnicos');
    caixa.append(no('summary', '', t('Detalhes técnicos')));
    const dados = no('dl', 'docs-tecnicos-dados');
    const linhas = [[t('Identificador'), doc.id], [t('Arquivo recebido'), doc.nome_recebido], [t('Hash (SHA-256)'), doc.sha256], [t('Versão dos documentos'), inventario.corpus_id]];
    for (const [rotulo, valor] of linhas) {
      if (!valor) continue;
      const termo = no('dt', '', rotulo), definicao = no('dd', '', String(valor)); definicao.setAttribute('translate', 'no');
      dados.append(termo, definicao);
    }
    caixa.append(dados);
    return caixa;
  }

  // Tabela no desktop; no celular a mesma marcação vira um cartão por documento (CSS). A coluna da ação tem rótulo só para leitor de tela.
  function lista(alvo, inventario, {consulta = '', limitacoes = false, abrir} = {}) {
    const nomeDe = doc => (window.Leitura ? window.Leitura.nome(doc) : doc.nome_recebido);
    const consultaNorm = consulta.toLocaleLowerCase('pt-BR');
    const docs = inventario.documentos.filter(doc => nomeDe(doc).toLocaleLowerCase('pt-BR').includes(consultaNorm)
      && (!limitacoes || window.Leitura.lacunas(doc).length));
    const moldura = no('div', 'docs-tabela');
    const tabela = no('table', 'docs-lista');
    tabela.append(no('caption', 'sr-only', `${inventario.titulo || ''} · ${inventario.corpus_id || ''}`));
    const cabeca = no('thead'), linhaCabeca = no('tr');
    for (const [rotulo, leitor] of [[t('Documento'), false], [t('Páginas'), false], [t('Leitura'), false], [t('Ação'), true]]) {
      const th = no('th'); th.scope = 'col';
      th.append(leitor ? no('span', 'sr-only', rotulo) : rotulo);
      linhaCabeca.append(th);
    }
    cabeca.append(linhaCabeca); tabela.append(cabeca);
    const corpo = no('tbody');
    for (const doc of docs) {
      const estado = leitura(doc);
      const linha = no('tr'); linha.dataset.leitura = estado.chave;
      const colNome = no('td', 'docs-nome'), colPaginas = no('td', 'docs-paginas'), colLeitura = no('td'), colAcao = no('td', 'docs-acao');
      const titulo = no('span', 'docs-titulo', nomeDe(doc)); titulo.setAttribute('translate', 'no');
      colNome.append(titulo, tecnicos(doc, inventario));
      colPaginas.dataset.rotulo = t('Páginas');
      colPaginas.textContent = estado.paginas != null ? (estado.paginas === 1 ? t('1 página') : t('{n} páginas', {n: estado.paginas})) : '—';
      colLeitura.append(celulaLeitura(estado));
      const botao = no('button', 'docs-abrir', t('Abrir original')); botao.type = 'button';
      botao.setAttribute('aria-label', `${t('Abrir original')}: ${nomeDe(doc)}`);
      botao.addEventListener('click', () => abrir?.(doc, botao));
      colAcao.append(botao);
      linha.append(colNome, colPaginas, colLeitura, colAcao);
      corpo.append(linha);
    }
    tabela.append(corpo); moldura.append(tabela);
    if (!docs.length) {
      alvo.replaceChildren();
      if (inventario.documentos.length) window.Estados.vazio(alvo, {titulo: 'Nenhum documento nesta seleção', texto: 'Tente outro nome ou remova o filtro.'});
      else window.Estados.vazio(alvo, {titulo: 'Nenhum documento nesta apuração ainda', texto: 'Envie os primeiros arquivos na área acima. Cada um recebe um resultado e o lote recebe um recibo.'});
      return docs;
    }
    alvo.replaceChildren(moldura);
    return docs;
  }

  // Área de envio (W02): arrastar ou escolher. No celular, o botão principal "Escolher arquivos". `aoEscolher(File[])` recebe os arquivos.
  function zona(alvo, {aoEscolher}) {
    const entrada = document.createElement('input');
    entrada.type = 'file'; entrada.multiple = true; entrada.hidden = true; entrada.setAttribute('aria-label', t('Escolher arquivos'));
    const chamada = no('p', 'docs-zona-chamada');
    const escolher = no('button', 'docs-escolher', t('escolha no computador')); escolher.type = 'button';
    chamada.append(no('strong', '', t('Arraste arquivos para cá')), ` ${t('ou')} `, escolher);
    const celular = no('button', 'docs-escolher-celular', t('Escolher arquivos')); celular.type = 'button';
    const formatos = no('p', 'docs-formatos', t('PDF, DOCX, XLSX, CSV, TXT e imagens · até 50 MB por arquivo'));
    alvo.classList.add('docs-zona');
    alvo.replaceChildren(chamada, celular, formatos, entrada);
    const abrirSeletor = () => entrada.click();
    escolher.addEventListener('click', abrirSeletor); celular.addEventListener('click', abrirSeletor);
    entrada.addEventListener('change', () => {
      const arquivos = Array.from(entrada.files || []);
      entrada.value = '';
      if (arquivos.length) aoEscolher(arquivos);
    });
    let dentro = 0;
    const ativa = valor => alvo.classList.toggle('docs-zona-ativa', valor);
    alvo.addEventListener('dragenter', evento => { evento.preventDefault(); dentro++; ativa(true); });
    alvo.addEventListener('dragover', evento => { evento.preventDefault(); });
    alvo.addEventListener('dragleave', () => { dentro = Math.max(0, dentro - 1); if (!dentro) ativa(false); });
    alvo.addEventListener('drop', evento => {
      evento.preventDefault(); dentro = 0; ativa(false);
      const arquivos = Array.from(evento.dataTransfer?.files || []);
      if (arquivos.length) aoEscolher(arquivos);
    });
    return {escolher: abrirSeletor};
  }

  // Envio por arquivo para a apuração escolhida. Sem o envio em fluxo no servidor, o caminho é a tela de Nova apuração (envio em JSON).
  let ocupado = false;
  async function enviar(arquivos, {caso, alvo, alvoRecibo, aoConcluir, aoIndisponivel}) {
    if (ocupado) return null;
    ocupado = true;   // antes de qualquer espera: um segundo clique durante a consulta ao servidor não manda o lote duas vezes
    try {
      if (!window.Envio || !(await window.Envio.disponivel())) { aoIndisponivel?.(); return null; }
      // Sem "natureza": o servidor usa a que a apuração já tem.
      const resultado = await window.Envio.enviar({escopo: {novo: false, caso}, arquivos, alvo, alvoRecibo});
      if (resultado.recebidos) { window.Envio.renderRecibo(alvoRecibo, resultado); await aoConcluir?.(resultado); }
      return resultado;
    } finally { ocupado = false; }
  }

  window.Documentos = {zona, lista, leitura, enviar};
})();
