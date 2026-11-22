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
  function estado(alvo, tipo, texto) {
    const p = element('p', texto, `quadro-estado ${tipo === 'erro' ? 'notice' : 'small'}`);
    p.dataset.estado = tipo;
    p.setAttribute('role', tipo === 'erro' ? 'alert' : 'status');
    alvo.replaceChildren(p);
    return p;
  }

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
      if (!casoId) { estado(painel, 'vazio', t('Escolha uma apuração no topo da Mesa para ver este quadro.')); return; }
      estado(painel, 'carregando', t('Carregando…'));
      try {
        if (!await disponivel(chave)) { if (pedido === sequencia) estado(painel, 'erro', t('Este quadro ainda não está disponível neste servidor. Atualize a Mesa para a versão mais recente.')); return; }
        await carregar(painel, casoId, () => pedido === sequencia);
      } catch (erro) { if (pedido === sequencia) estado(painel, 'erro', erro.message); }
    };
  }
  return {t, dado, botao, estado, evidencia, abrirOriginal, disponivel, registrarAba, selecionar, quadro, SUPORTE, NATUREZA, caso};
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
    if (!dados.hipoteses?.length) { Q.estado(painel, 'vazio', t('Nenhuma hipótese registrada nesta apuração.')); return; }
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
    const campo = element('fieldset', undefined, 'tempo-filtro');
    gaveta.append(campo);
    campo.append(element('legend', t('Tipos de data')));
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
    const quando = element('p', undefined, 'tempo-data');
    const hora = element('time', formatar(e.data)); hora.setAttribute('datetime', e.data.valor);
    quando.append(hora, element('span', ` · ${t(PRECISAO[e.data.precisao] || e.data.precisao)}${e.data.aproximada ? ` · ${t('aproximada')}` : ''}`, 'small'));
    li.append(quando, element('p', t(e.data.rotulo || e.data.tipo), 'small tempo-tipo'), Q.dado('h3', e.descricao));
    if (e.data.observacao) li.append(Q.dado('p', e.data.observacao, 'small'));
    if (e.divergente) li.append(element('p', t('Há datas divergentes do mesmo tipo neste evento. O quadro não escolhe uma: confira as fontes.'), 'notice'));
    if (e.retirado) { const aviso = element('p', `${t('Evento retirado:')} `, 'notice'); aviso.append(Q.dado('span', e.motivo_retirada)); li.append(aviso); }
    const fonte = element('div', undefined, 'tempo-fonte');
    fonte.append(element('p', t('Evidência da data'), 'eyebrow'));
    if (e.fonte_da_data) fonte.append(Q.evidencia(casoId, e.fonte_da_data, 'div'));
    else fonte.append(element('p', t('Data sem fonte vinculada.'), 'notice'));
    li.append(fonte);
    return li;
  }
  const carregar = Q.quadro('quadros_evidencia', async (painel, casoId, vigente) => {
    const pedido = {caso: casoId};
    if (escolhidos) pedido.tipos = escolhidos;
    const dados = await api('linha-tempo-listar', pedido);
    if (!vigente()) return;
    tipos = dados.tipos_data || tipos || {};
    const corpo = [filtro(painel, casoId, carregar), element('p', t(dados.aviso || ''), 'small quadro-aviso')];
    const lista = element('ol', undefined, 'tempo-lista');
    lista.setAttribute('aria-label', t('Linha do tempo: {n} eventos', {n: dados.entradas?.length || 0}));
    for (const e of dados.entradas || []) lista.append(entrada(casoId, e));
    if (!dados.entradas?.length) corpo.push(Q.estado(element('div'), 'vazio', escolhidos ? t('Nenhum evento com os tipos de data escolhidos.') : t('Nenhum evento registrado na linha do tempo.')));
    else corpo.push(lista);
    if (dados.fontes_indisponiveis?.length) corpo.push(element('p', t('{n} fontes de data estão indisponíveis.', {n: dados.fontes_indisponiveis.length}), 'notice'));
    painel.replaceChildren(...corpo);
  });
  window.addEventListener('mesa-contexto-alterado', () => { tipos = null; escolhidos = null; });
  Q.registrarAba({id: 'tempo', rotulo: t('Linha do tempo'), carregar});
})();
