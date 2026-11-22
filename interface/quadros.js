'use strict';
// Evidence boards (Core routes, CONTRATO_EVIDENCIA §5.2–5.3): hypotheses in three columns
// (supports, contradicts, missing) and a vertical timeline filtered by date type. Every
// evidence shows its locator and opens the original through the existing hash-checked routes
// (achados-original / caderno-original) and window.abrirOriginal. All source text enters as
// text nodes marked translate="no"; the boards only organise, they never judge.
// window.Quadros also offers the tab strip and helpers to analise.js (comparator, tables, map).
window.Quadros = (() => {
  const t = (texto, vars) => window.I18N ? window.I18N.t(texto, vars)
    : Object.entries(vars || {}).reduce((fim, [nome, valor]) => fim.split(`{${nome}}`).join(String(valor)), texto);
  const dado = (tag, texto, classe) => { const no = element(tag, texto, classe); no.setAttribute('translate', 'no'); return no; };
  const botao = (rotulo, classe = 'secondary') => { const b = element('button', rotulo, classe); b.type = 'button'; return b; };
  const SUPORTE = {nao_revisado: 'Suporte não revisado', sustentado: 'Sustentado', parcial: 'Suporte parcial',
    nao_sustentado: 'Não sustentado', ilegivel: 'Ilegível'};
  const NATUREZA = {declaracao_documental: 'Declaração documental', alegacao_atribuida: 'Alegação atribuída',
    inferencia: 'Inferência', pendencia: 'Pendência'};
  const SITUACAO = {em_aberto: 'Em aberto', sustentada: 'Sustentada', contrariada: 'Contrariada',
    inconclusiva: 'Inconclusiva', descartada: 'Descartada'};
  const caso = () => window.contextoCaso?.() || '';

  // Loading, empty and error states share one element so a screen reader hears each change.
  // With estados.js (W11): esqueleto for waiting, block with what the thing is and an action for empty, three-part block for errors.
  // `extra`: {titulo, acao: {rotulo, aoClicar}} for empty; {titulo, acoes} for errors.
  function estado(alvo, tipo, texto, extra = {}) {
    const E = window.Estados;
    let bloco;
    if (E && tipo === 'carregando') { E.esqueleto(alvo, {rotulo: texto}); return alvo.firstChild; }
    if (E && tipo === 'vazio') bloco = E.vazio(alvo, {titulo: extra.titulo, texto, acao: extra.acao});
    else if (E && tipo === 'erro') bloco = E.erro(alvo, {titulo: extra.titulo || t('Não deu para abrir este quadro.'), texto, acoes: extra.acoes});
    else {
      bloco = element('p', texto, `${tipo === 'erro' ? 'notice' : 'small'}`);
      bloco.dataset.estado = tipo;
      bloco.setAttribute('role', tipo === 'erro' ? 'alert' : 'status');
      alvo.replaceChildren(bloco);
    }
    bloco.classList.add('quadro-estado');
    return bloco;
  }
  // Empty states lead somewhere that exists: another area of the desk.
  const irPara = area => () => window.areaMesa?.ir(area);
  const perguntar = () => ({rotulo: t('Fazer uma pergunta'), aoClicar: irPara('codex')});

  // The server announces each board in /api/integracao; an older server keeps the screen honest.
  let integracao = null;
  function disponivel(chave) {
    integracao ||= fetch('/api/integracao').then(r => r.ok ? r.json() : {}).catch(() => ({}));
    return integracao.then(dados => dados?.[chave] === true);
  }

  // Original of a saved link, through the route of its origin (IA evidence or notebook source).
  async function abrirOriginal(casoId, vinculo, gatilho, retorno) {
    const ref = vinculo.referencia || {}, ev = vinculo.evidencia || {};
    gatilho.disabled = true; retorno.textContent = '';
    try {
      const blob = ref.tipo === 'ia'
        ? await api('achados-original', {caso: casoId, rodada: ref.rodada, revisao: ref.revisao, evidencia_id: ref.evidencia_id}, true)
        : await api('caderno-original', {caso: casoId, registro_id: ref.registro_id, sha256: ref.sha256, fonte_indice: ref.fonte}, true);
      const loc = ev.localizador || vinculo.localizador || {};
      await window.abrirOriginal(blob, ev.documento?.nome || 'original', loc.pagina_pdf || 1, ev.trecho || '');
    } catch (erro) { retorno.textContent = erro.message; }
    finally { gatilho.disabled = false; }
  }

  // One saved link (CONTRATO §3.2, with `estado`/`evidencia` from conferir_vinculos).
  function evidencia(casoId, vinculo, tag = 'li') {
    const item = element(tag, undefined, 'quadro-evidencia');
    const ev = vinculo.evidencia, loc = ev?.localizador || vinculo.localizador || {};
    const nome = ev?.documento?.nome ? Leitura.nome({nome_documento: ev.documento.nome}) : (vinculo.documento_id || t('Documento'));
    item.append(dado('p', `${nome} · ${loc.legivel || Leitura.localizador(loc)}`, 'small quadro-localizador'));
    if (vinculo.estado === 'indisponivel' || !ev) {
      item.classList.add('is-indisponivel');
      item.append(element('p', t('Fonte indisponível: {erro}', {erro: vinculo.erro || t('o original não pôde ser conferido.')}), 'notice'));
      return item;
    }
    item.append(dado('blockquote', ev.trecho || t('Fonte visual: consulte o original.')));
    const selos = element('p', undefined, 'quadro-selos small');
    // The seal is the assessment of this link, also in the "contradicts" column: say so.
    selos.append(element('span', t('Avaliação: {s}', {s: t(SUPORTE[vinculo.suporte] || vinculo.suporte).toLowerCase()}), `quadro-selo suporte-${vinculo.suporte}`),
      element('span', t(NATUREZA[vinculo.natureza] || vinculo.natureza), 'quadro-selo'));
    item.append(selos);
    if (vinculo.justificativa) item.append(dado('p', vinculo.justificativa, 'quadro-justificativa'));
    const abrir = botao(Leitura.rotuloOriginal(Leitura.pagina(loc))), retorno = element('p', '', 'small');
    retorno.setAttribute('role', 'status');
    abrir.setAttribute('aria-label', `${abrir.textContent}: ${nome} · ${loc.legivel || ''}`.trim());
    abrir.addEventListener('click', () => abrirOriginal(casoId, vinculo, abrir, retorno));
    item.append(abrir, retorno);
    return item;
  }

  // Tab strip (WAI-ARIA tabs): arrows, Home and End move between tabs; only the active one is in the Tab order.
  const abas = [];
  function registrarAba({id, rotulo, carregar}) {
    const lista = $('quadros-abas'), paineis = $('quadros-paineis');
    const aba = botao(rotulo, 'quadros-aba'); aba.id = `quadros-aba-${id}`;
    aba.setAttribute('role', 'tab'); aba.setAttribute('aria-controls', `quadros-${id}`);
    const painel = element('div', undefined, 'quadros-painel'); painel.id = `quadros-${id}`;
    painel.setAttribute('role', 'tabpanel'); painel.setAttribute('aria-labelledby', aba.id); painel.tabIndex = 0;
    lista.append(aba); paineis.append(painel);
    const registro = {id, aba, painel, carregar, carregado: null};
    abas.push(registro);
    aba.addEventListener('click', () => selecionar(id));
    aba.addEventListener('keydown', evento => {
      const i = abas.indexOf(registro), n = abas.length;
      const destino = {ArrowRight: (i + 1) % n, ArrowLeft: (i - 1 + n) % n, Home: 0, End: n - 1}[evento.key];
      if (destino === undefined) return;
      evento.preventDefault(); selecionar(abas[destino].id); abas[destino].aba.focus();
    });
    marcar(abas[0].id);
    return registro;
  }
  let ativa = null;
  function marcar(id) {
    ativa = id;
    for (const r of abas) {
      const sim = r.id === id;
      r.aba.setAttribute('aria-selected', String(sim)); r.aba.tabIndex = sim ? 0 : -1; r.painel.hidden = !sim;
    }
  }
  function selecionar(id, forcar = false) {
    marcar(id);
    const r = abas.find(a => a.id === id), atual = caso();
    if (r && (forcar || r.carregado !== atual)) { r.carregado = atual; r.carregar(r.painel, atual); }
  }
  const aberta = () => !$('area-quadros').hidden;
  window.addEventListener('quadros-abrir', () => selecionar(ativa, true));
  window.addEventListener('mesa-contexto-alterado', () => { for (const r of abas) r.carregado = null; if (aberta()) selecionar(ativa); });

  // Common opening of a board: availability, chosen case, loading state, stale answers dropped.
  function quadro(chave, carregar) {
    let sequencia = 0;
    return async (painel, casoId) => {
      const pedido = ++sequencia;
      if (!casoId) { estado(painel, 'vazio', t('Escolha uma apuração no topo da Mesa para ver este quadro.'), {titulo: t('Nenhuma apuração escolhida'), acao: {rotulo: t('Escolher apuração'), aoClicar: () => document.getElementById('contexto-caso')?.focus()}}); return; }
      estado(painel, 'carregando', t('Carregando…'));
      try {
        if (!await disponivel(chave)) { if (pedido === sequencia) estado(painel, 'erro', t('Este quadro ainda não está disponível neste servidor. Atualize a Mesa para a versão mais recente.')); return; }
        await carregar(painel, casoId, () => pedido === sequencia);
      } catch (erro) { if (pedido === sequencia) estado(painel, 'erro', erro.message); }
    };
  }
  // Ícones do Vlado (docs/design/icones/*.svg, traço único de 1,6 em 24 x 24, na cor do texto). A tabela é gerada dos SVG do Design;
  // icone() devolve um <svg> embutido (a CSP da Mesa não aceita imagem data:) e CAMINHOS serve ao desenho do mapa, que os põe dentro do SVG.
  const CAMINHOS = {
    'contrato': 'M7 3h7l4 4v14H7zM14 3v4h4M10 12h5M10 16h5',
    'data': 'M4 5h16v15H4zM4 10h16M8 3v4M16 3v4',
    'documento': 'M8 3h8l4 4v14H8zM16 3v5h4M4 7v14M11 12h6M11 16h6',
    'empresa': 'M5 21V7l7-3v17M12 9h7v12M3 21h18M8 9h1M8 13h1M15 13h1M15 17h1',
    'evento-aditivo': 'M7 3h7l4 4v14H7zM14 3v4h4M12 11v6M9 14h6',
    'evento-pedido': 'M4 6h16v12H4zM4 7l8 6 8-6',
    'lacuna': 'M21 12a9 9 0 11-18 0 9 9 0 0118 0zM9.6 9.4a2.5 2.5 0 114 2c-.9.5-1.6 1.1-1.6 2v.4M12 16.8v.2',
    'orgao-publico': 'M3 10l9-5 9 5M5 10v8M10 10v8M14 10v8M19 10v8M3 20h18',
    'pagamento': 'M20 12a8 8 0 11-16 0 8 8 0 0116 0zM12 8v8M14.5 10c-.3-.7-1.2-1-2.5-1-1.5 0-2.5.6-2.5 1.5S10.5 12 12 12s2.5.6 2.5 1.5S13.5 15 12 15c-1.3 0-2.2-.3-2.5-1',
    'pessoa': 'M12 12a4 4 0 100-8 4 4 0 000 8zM4 21c0-4 4-6 8-6s8 2 8 6',
    'relacao-cargo': 'M4 8h16v11H4zM9 8V5h6v3M4 13h16',
    'relacao-parentesco': 'M8 11a3 3 0 100-6 3 3 0 000 6zM16 11a3 3 0 100-6 3 3 0 000 6zM3 19c0-3 2-5 5-5s5 2 5 5M14 14.3c.6-.2 1.3-.3 2-.3 3 0 5 2 5 5',
    'relacao-socio': 'M9 15l6-6M10 6l1-1a4 4 0 016 6l-1 1M14 18l-1 1a4 4 0 01-6-6l1-1',
    'relacao-vinculo': 'M12 4v6M6 20v-5h12v5M12 10v5',
    'sinal-corrigido': 'M5 19l1-4L16 5l3 3L9 18zM14 7l3 3',
    'sinal-parcial': 'M20 12a8 8 0 11-16 0 8 8 0 0116 0zM12 4v16M12 8h3M12 12h4M12 16h3',
    'sinal-sem-suporte': 'M7 7l10 10M17 7L7 17',
  };
  function icone(nome, classe = 'icone-vlado') {
    const no = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    no.setAttribute('viewBox', '0 0 24 24'); no.setAttribute('aria-hidden', 'true'); no.setAttribute('class', classe);
    const caminho = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    caminho.setAttribute('d', CAMINHOS[nome] || CAMINHOS.documento); no.append(caminho);
    return no;
  }
  return {t, dado, botao, estado, irPara, perguntar, evidencia, abrirOriginal, disponivel, registrarAba, selecionar, quadro, SUPORTE, NATUREZA, caso, icone, CAMINHOS};
})();

// Hypotheses: three columns per hypothesis; the declared situation is a person's, never the board's.
(() => {
  const Q = window.Quadros, {t} = Q;
  const COLUNAS = [['sustentam', 'Sustenta', 'sustenta'], ['contrariam', 'Contraria', 'contraria'], ['faltam', 'Falta', 'falta']];
  function coluna(casoId, h, [campo, titulo, classe]) {
    const secao = element('section', undefined, `quadro-coluna coluna-${classe}`);
    const cabeca = element('h4', t(titulo));
    const itens = h[campo] || [];
    const contagem = t(itens.length === 1 ? '{n} item' : '{n} itens', {n: itens.length});
    secao.setAttribute('aria-label', `${t(titulo)}: ${contagem}`);
    secao.append(cabeca, element('p', contagem, 'small quadro-contagem'));
    const lista = element('ul', undefined, 'quadro-lista');
    if (campo === 'faltam') {
      for (const lacuna of itens) {
        const li = element('li', undefined, 'quadro-lacuna');
        li.append(lacuna.origem === 'automatica' ? element('p', t(lacuna.descricao)) : Q.dado('p', lacuna.descricao),
          element('p', lacuna.origem === 'automatica' ? t('Lacuna apontada pelo quadro') : t('Lacuna registrada por pessoa'), 'small'));
        if (lacuna.diligencia_id) li.append(element('p', t('Diligência ligada: {estado}', {estado: lacuna.diligencia_estado || t('sem estado')}), 'small'));
        lista.append(li);
      }
    } else for (const vinculo of itens) lista.append(Q.evidencia(casoId, vinculo));
    if (!itens.length) lista.append(element('li', campo === 'faltam' ? t('Nenhuma lacuna registrada.') : t('Nenhuma evidência conferida nesta coluna.'), 'small quadro-vazio'));
    secao.append(lista);
    return secao;
  }
  function hipotese(casoId, h) {
    const cartao = element('article', undefined, 'quadro-hipotese');
    cartao.dataset.hipotese = h.id;
    const titulo = Q.dado('h3', h.enunciado); titulo.id = `hipotese-${h.id}`;
    cartao.setAttribute('aria-labelledby', titulo.id);
    const meta = element('p', undefined, 'small quadro-meta');
    meta.append(element('span', t('Situação declarada: {situacao}', {situacao: t({em_aberto: 'Em aberto', sustentada: 'Sustentada', contrariada: 'Contrariada', inconclusiva: 'Inconclusiva', descartada: 'Descartada'}[h.situacao] || h.situacao)})),
      element('span', h.condicao === 'com_evidencia' ? t('Com evidência conferida') : t('Pendente de evidência conferida'), `quadro-condicao condicao-${h.condicao}`));
    cartao.append(titulo, meta);
    if (h.situacao_sem_base) cartao.append(element('p', t('A situação declarada perdeu a evidência que a fundamentava. Confira antes de usar.'), 'notice'));
    const grade = element('div', undefined, 'quadro-colunas');
    for (const c of COLUNAS) grade.append(coluna(casoId, h, c));
    cartao.append(grade);
    if (h.contexto?.length) {
      const extra = element('details', undefined, 'quadro-contexto');
      extra.append(element('summary', t('Contexto ({n})', {n: h.contexto.length})));
      const lista = element('ul', undefined, 'quadro-lista');
      for (const v of h.contexto) lista.append(Q.evidencia(casoId, v));
      extra.append(lista); cartao.append(extra);
    }
    if (h.indisponiveis?.length) {
      const extra = element('details', undefined, 'quadro-indisponiveis');
      extra.append(element('summary', t('Fontes indisponíveis ({n})', {n: h.indisponiveis.length})));
      const lista = element('ul', undefined, 'quadro-lista');
      for (const v of h.indisponiveis) lista.append(Q.evidencia(casoId, v));
      extra.append(lista); cartao.append(extra);
    }
    return cartao;
  }
  Q.registrarAba({id: 'hipoteses', rotulo: t('Hipóteses'), carregar: Q.quadro('quadros_evidencia', async (painel, casoId, vigente) => {
    const dados = await api('hipoteses-quadro', {caso: casoId});
    if (!vigente()) return;
    if (!dados.hipoteses?.length) { Q.estado(painel, 'vazio', t('Uma hipótese é uma afirmação que os documentos podem sustentar ou contrariar.'), {titulo: t('Nenhuma hipótese ainda'), acao: Q.perguntar()}); return; }
    const corpo = [element('p', t(dados.aviso || ''), 'small quadro-aviso')];
    for (const h of dados.hipoteses) corpo.push(hipotese(casoId, h));
    if (dados.divergentes?.length) corpo.push(element('p', t('{n} registros com histórico divergente ficaram de fora.', {n: dados.divergentes.length}), 'notice'));
    painel.replaceChildren(...corpo);
  })});
})();

// Timeline: vertical list (the same list on phones), filter by date type, exact vs partial dates.
(() => {
  const Q = window.Quadros, {t} = Q;
  const PRECISAO = {dia: 'Data exata', mes: 'Data parcial: mês', ano: 'Data parcial: ano'};
  const formatar = data => {
    const [a, m, d] = String(data.valor).split('-');
    return data.precisao === 'dia' ? `${d}/${m}/${a}` : data.precisao === 'mes' ? `${m}/${a}` : a;
  };
  // Linha do tempo (componentes.md#linha-do-tempo): ano como cabeçalho, dia e mês na coluna da data, marco cheio (data exata) ou vazado (parcial)
  // com o ícone do tipo de data, cartão com o acontecimento e o selo da fonte.
  const MESES = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'];
  const ICONE_TIPO = {assinatura: 'contrato', emissao_documento: 'documento', publicacao: 'documento', registro: 'documento', declarada_por_fonte: 'documento',
    pagamento: 'pagamento', recebimento: 'data', fato: 'data', vigencia_inicio: 'data', vigencia_fim: 'data'};
  const quandoCurto = data => {
    const [a, m, d] = String(data.valor).split('-');
    return data.precisao === 'dia' ? `${Number(d)} ${MESES[Number(m) - 1]}` : data.precisao === 'mes' ? MESES[Number(m) - 1] : a;
  };
  const anoDe = data => String(data.valor).slice(0, 4);
  let tipos = null, escolhidos = null, filtroAberto = null;
  // The filter sits in a <details>: open on wide screens, closed on phones (it would push the events
  // a screen down); the summary says how many types are chosen, and the choice survives reloads.
  function filtro(painel, casoId, carregar) {
    const gaveta = element('details', undefined, 'tempo-filtro-caixa');
    filtroAberto ??= !window.matchMedia?.('(max-width:719px)').matches;
    gaveta.open = filtroAberto;
    gaveta.addEventListener('toggle', () => { filtroAberto = gaveta.open; });
    const total = Object.keys(tipos).length;
    gaveta.append(element('summary', escolhidos ? t('Tipos de data: {n} de {total}', {n: escolhidos.length, total}) : t('Tipos de data: todos ({total})', {total})));
    const campo = element('fieldset', undefined, 'tempo-filtro'); campo.dataset.todos = String(!escolhidos);
    gaveta.append(campo);
    campo.append(element('legend', t('Tipos de data')));
    const tudo = element('button', t('Tudo'), 'tempo-tudo'); tudo.type = 'button'; tudo.setAttribute('aria-pressed', String(!escolhidos));
    tudo.addEventListener('click', () => { escolhidos = null; carregar(painel, casoId); });
    campo.append(tudo);
    for (const [tipo, rotulo] of Object.entries(tipos)) {
      const caixa = element('input'); caixa.type = 'checkbox'; caixa.value = tipo; caixa.id = `tempo-tipo-${tipo}`;
      caixa.checked = !escolhidos || escolhidos.includes(tipo);
      const etiqueta = element('label', undefined, 'tempo-opcao'); etiqueta.setAttribute('for', caixa.id);
      etiqueta.append(caixa, element('span', t(rotulo)));
      caixa.addEventListener('change', () => {
        const marcados = [...campo.querySelectorAll('input')].filter(c => c.checked).map(c => c.value);
        escolhidos = marcados.length === Object.keys(tipos).length ? null : marcados;
        carregar(painel, casoId);
      });
      campo.append(etiqueta);
    }
    return gaveta;
  }
  function entrada(casoId, e) {
    const li = element('li', undefined, 'tempo-evento');
    const exata = e.data.precisao === 'dia' && !e.data.aproximada;
    li.dataset.precisao = e.data.precisao; li.dataset.tipo = e.data.tipo;
    li.classList.add(exata ? 'marco-exato' : 'marco-parcial');
    // Coluna da data: dia e mês em destaque; o qualificador diz o que não se sabe (nunca só pela cor).
    const quando = element('p', undefined, 'tempo-data');
    const hora = element('time', quandoCurto(e.data)); hora.setAttribute('datetime', e.data.valor); hora.setAttribute('title', formatar(e.data));
    const qualificador = e.data.precisao === 'dia' ? (e.data.aproximada ? t('data aproximada') : t('data exata'))
      : e.data.precisao === 'mes' ? t('dia não informado') : t('mês e dia não informados');
    quando.append(hora, element('span', qualificador, `tempo-qualificador${exata ? '' : ' is-parcial'}`));
    // Marco: círculo cheio para data exata, vazado para parcial, com o ícone do tipo de data.
    const marco = element('span', undefined, 'tempo-marco'); marco.setAttribute('aria-hidden', 'true'); marco.append(Q.icone(ICONE_TIPO[e.data.tipo] || 'data', 'tempo-marco-icone'));
    // Cartão: o acontecimento em serifa, o tipo de data e a observação, e o selo da fonte à direita.
    const cartao = element('div', undefined, 'tempo-cartao');
    const texto = element('div', undefined, 'tempo-cartao-texto');
    texto.append(Q.dado('h4', e.descricao), element('p', t(e.data.rotulo || e.data.tipo), 'small tempo-tipo'));
    if (e.data.observacao) texto.append(Q.dado('p', e.data.observacao, 'small'));
    if (e.divergente) texto.append(element('p', t('Há datas divergentes do mesmo tipo neste evento. O quadro não escolhe uma: confira as fontes.'), 'notice'));
    if (e.retirado) { const aviso = element('p', `${t('Evento retirado:')} `, 'notice'); aviso.append(Q.dado('span', e.motivo_retirada)); texto.append(aviso); }
    cartao.append(texto);
    const fonte = element('div', undefined, 'tempo-fonte');
    if (e.fonte_da_data) {
      const v = e.fonte_da_data, ev = v.evidencia, loc = ev?.localizador || v.localizador || {};
      const nome = ev?.documento?.nome ? Leitura.nome({nome_documento: ev.documento.nome}) : (v.documento_id || t('Documento'));
      const selo = Q.botao(`${nome}, ${loc.legivel || Leitura.localizador(loc)}`, 'tempo-selo'); selo.setAttribute('translate', 'no');
      const retorno = element('p', '', 'small'); retorno.setAttribute('role', 'status');
      selo.setAttribute('aria-label', `${t('Abrir o original')}: ${nome} · ${loc.legivel || ''}`.trim());
      selo.addEventListener('click', () => Q.abrirOriginal(casoId, v, selo, retorno));
      fonte.append(selo, retorno);
      // A evidência inteira (trecho, avaliação, justificativa) segue a um clique, recolhida.
      const detalhe = element('details', undefined, 'tempo-evidencia');
      detalhe.append(element('summary', t('Evidência da data')), Q.evidencia(casoId, e.fonte_da_data, 'div'));
      texto.append(detalhe);
    } else fonte.append(element('p', t('Data sem fonte vinculada.'), 'notice'));
    cartao.append(fonte);
    li.append(quando, marco, cartao);
    return li;
  }
  // Agrupa por ano: cabeçalho com o ano e a contagem ("6 acontecimentos · 5 com documento"), e a lista do ano.
  function porAno(casoId, entradas) {
    const anos = new Map();
    for (const e of entradas) { const ano = anoDe(e.data); if (!anos.has(ano)) anos.set(ano, []); anos.get(ano).push(e); }
    return [...anos].map(([ano, lista]) => {
      const secao = element('section', undefined, 'tempo-ano'); secao.setAttribute('aria-labelledby', `tempo-ano-${ano}`);
      const cab = element('header', undefined, 'tempo-ano-cab');
      const titulo = element('h3', ano, 'tempo-ano-titulo'); titulo.id = `tempo-ano-${ano}`;
      const com = lista.filter(e => e.fonte_da_data).length;
      cab.append(titulo, element('span', undefined, 'tempo-ano-filete'),
        element('span', t(lista.length === 1 ? '1 acontecimento · {c} com documento' : '{n} acontecimentos · {c} com documento', {n: lista.length, c: com}), 'tempo-ano-conta'));
      const ol = element('ol', undefined, 'tempo-lista');
      ol.setAttribute('aria-label', t('Acontecimentos de {ano}', {ano}));
      for (const e of lista) ol.append(entrada(casoId, e));
      secao.append(cab, ol);
      return secao;
    });
  }
  const carregar = Q.quadro('quadros_evidencia', async (painel, casoId, vigente) => {
    const pedido = {caso: casoId};
    if (escolhidos) pedido.tipos = escolhidos;
    const dados = await api('linha-tempo-listar', pedido);
    if (!vigente()) return;
    tipos = dados.tipos_data || tipos || {};
    const corpo = [filtro(painel, casoId, carregar), element('p', t(dados.aviso || ''), 'small quadro-aviso')];
    if (!dados.entradas?.length) corpo.push(escolhidos ? Q.estado(element('div'), 'vazio', t('Nenhum acontecimento tem os tipos de data escolhidos.'), {titulo: t('Nenhum acontecimento com esses tipos de data'), acao: {rotulo: t('Mostrar tudo'), aoClicar: () => { escolhidos = null; carregar(painel, casoId); }}})
      : Q.estado(element('div'), 'vazio', t('A linha do tempo reúne os acontecimentos datados que os documentos registram.'), {titulo: t('Nenhum acontecimento com data ainda'), acao: Q.perguntar()}));
    else {
      const linha = element('div', undefined, 'tempo-linha');
      linha.setAttribute('role', 'group'); linha.setAttribute('aria-label', t('Linha do tempo: {n} eventos', {n: dados.entradas.length}));
      linha.append(...porAno(casoId, dados.entradas));
      corpo.push(linha);
    }
    if (dados.fontes_indisponiveis?.length) corpo.push(element('p', t('{n} fontes de data estão indisponíveis.', {n: dados.fontes_indisponiveis.length}), 'notice'));
    painel.replaceChildren(...corpo);
  });
  window.addEventListener('mesa-contexto-alterado', () => { tipos = null; escolhidos = null; });
  Q.registrarAba({id: 'tempo', rotulo: t('Linha do tempo'), carregar});
})();
