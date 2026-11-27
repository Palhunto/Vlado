'use strict';
// Sugestões da IA nos quadros (P45; componentes.md#sugestao-ia; contrato CONTRATO_QUADROS_ONDA4.md, seção 2). A IA sugere candidatos presos a uma
// evidência publicada; uma pessoa confirma, corrige ou descarta. Confirmar põe o item no quadro; conferir no original continua no achado.
// Este arquivo só monta o painel e as ações; mapa, linha do tempo e hipóteses (analise.js, quadros.js) decidem onde a sugestão aparece.
// Todo texto de fonte entra como nó de texto marcado translate="no". Nada aqui afirma que a sugestão foi conferida.
window.Quadros.sugestoes = (() => {
  const Q = window.Quadros, {t, dado, botao} = Q;
  const CAPACIDADE = {pessoa: 'mapa-entidade-criar', organizacao: 'mapa-entidade-criar', ligacao: 'mapa-relacao-criar',
    acontecimento: 'linha-tempo-criar', hipotese: 'hipoteses-criar'};
  const TIPO = {pessoa: 'Pessoa', organizacao: 'Organização', ligacao: 'Ligação', acontecimento: 'Acontecimento', hipotese: 'Hipótese'};
  const PODE_EDITAR = 'Só repórter e editor mudam os quadros.';
  const vazio = {sugestoes: [], abertas: [], descartadas: [], erro: null};

  // Sem a lista de capacidades (servidor antigo, teste), a Mesa deixa o servidor decidir.
  const pode = sug => !window.Sessao?.pode || window.Sessao.pode(CAPACIDADE[sug.tipo]);

  // Lista as sugestões de um quadro. Falha ou servidor sem a rota: o quadro abre como sempre, sem sugestões.
  async function listar(casoId, quadro) {
    try {
      const dados = await api('sugestoes-listar', {caso: casoId, quadro});
      const todas = dados.sugestoes || [];
      return {sugestoes: todas, abertas: todas.filter(s => s.estado === 'aberta'), descartadas: todas.filter(s => s.estado === 'descartada'), erro: null};
    } catch (erro) { return {...vazio, erro}; }
  }
  const contagemTexto = n => !n ? '' : t(n === 1 ? ', {n} sugestão da IA' : ', {n} sugestões da IA', {n});

  const requisicao = () => (globalThis.crypto?.randomUUID?.() || Array.from({length: 32}, () => Math.floor(Math.random() * 16).toString(16)).join('')).replace(/-/g, '');
  const dia = iso => { const d = new Date(iso); return Number.isNaN(d.getTime()) ? '' : `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')}`; };
  const hora = iso => { const d = new Date(iso); return Number.isNaN(d.getTime()) ? '' : `${d.getHours()}h${String(d.getMinutes()).padStart(2, '0')}`; };
  const MESES = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'];
  // AAAA, AAAA-MM ou AAAA-MM-DD, como o documento traz; a precisão vem do que foi escrito.
  function precisaoDe(valor) { const v = String(valor || ''); return v.length >= 10 ? 'dia' : v.length >= 7 ? 'mes' : 'ano'; }
  function dataLegivel(data) {
    const [a, m, d] = String(data.valor).split('-'), p = precisaoDe(data.valor);
    const texto = p === 'dia' ? `${Number(d)} ${MESES[Number(m) - 1]} ${a}` : p === 'mes' ? `${MESES[Number(m) - 1]} ${a}` : a;
    const qual = p === 'dia' ? (data.aproximada ? t('data aproximada') : t('data exata')) : p === 'mes' ? t('dia não informado') : t('mês e dia não informados');
    return `${texto}, ${qual}`;
  }

  // O vínculo no formato que Q.evidencia e Q.abrirOriginal já entendem: o salvo (campos) junto com o resolvido (evidencias).
  function vinculo(sug, i) {
    const salvo = sug.campos?.evidencias?.[i] || {}, ev = sug.evidencias?.[i] || {};
    return {referencia: ev.referencia || salvo.referencia, papel: salvo.papel, suporte: salvo.suporte, natureza: salvo.natureza, justificativa: salvo.justificativa || '',
      estado: ev.estado, erro: ev.erro, localizador: ev.localizador,
      evidencia: ev.estado === 'indisponivel' ? null : {documento: ev.documento, trecho: ev.trecho, localizador: ev.localizador}, revisao_ia: ev.revisao_ia, conferencia_humana: ev.conferencia_humana};
  }
  const nomeDa = (sug, ponta) => sug.pontas?.[ponta]?.nome || '';

  // O que a IA propõe, numa linha (painel, nome acessível, lista de descartadas).
  function proposta(sug) {
    const c = sug.campos || {};
    if (sug.tipo === 'pessoa' || sug.tipo === 'organizacao') return `${c.nome} · ${t(TIPO[sug.tipo]).toLowerCase()}`;
    if (sug.tipo === 'ligacao') return `${nomeDa(sug, 'origem')} — ${c.tipo} — ${nomeDa(sug, 'destino')}`;
    if (sug.tipo === 'acontecimento') return `${c.descricao}${c.datas?.[0] ? ` · ${dataLegivel(c.datas[0])}` : ''}`;
    return c.enunciado || '';
  }
  // Nome acessível: começa pela origem (P45).
  function rotuloAcessivel(sug) {
    const c = sug.campos || {};
    if (sug.tipo === 'pessoa' || sug.tipo === 'organizacao') return t('Sugestão da IA: {nome}, {tipo}', {nome: c.nome, tipo: t(TIPO[sug.tipo]).toLowerCase()});
    if (sug.tipo === 'ligacao') return t('Sugestão da IA: {a} — {tipo} — {b}', {a: nomeDa(sug, 'origem'), tipo: c.tipo, b: nomeDa(sug, 'destino')});
    if (sug.tipo === 'acontecimento') return t('Sugestão da IA: {descricao}, {data}', {descricao: c.descricao, data: c.datas?.[0] ? dataLegivel(c.datas[0]) : ''});
    return t('Sugestão da IA: {enunciado}', {enunciado: c.enunciado});
  }

  // Por que "Confirmar" está indisponível (componentes.md#sugestao-ia, tabela "Quando Confirmar fica indisponível").
  function razaoBloqueio(sug) {
    const ponta = ['origem', 'destino'].map(p => sug.pontas?.[p]).find(p => p && p.estado !== 'confirmada' && !p.item_id);
    switch (sug.bloqueio) {
      case 'ponta_ainda_sugestao': return t('Confirme antes {nome}, a outra ponta da ligação.', {nome: ponta?.nome || ''});
      case 'ponta_descartada': return t('{nome}, a outra ponta, está em Descartadas. Restaure-o ou troque a ponta em Corrigir.', {nome: ponta?.nome || ''});
      case 'achado_retirado': return t('A revisão da IA retirou este achado. Corrija com outra evidência ou descarte.');
      case 'versao_substituida': return t('Há uma versão mais nova deste achado. Corrija para ligar a nova versão.');
      case 'nao_sustentado': return t('A revisão da IA não sustentou esta evidência. Corrija com outra evidência ou descarte.');
      case 'ilegivel': return t('A revisão da IA não conseguiu ler esta evidência. Confira no original e corrija, ou descarte.');
      case 'evidencia_indisponivel': return t('A evidência não está mais disponível. Descarte ou corrija com outra.');
      default: return sug.bloqueio ? t('Não é possível confirmar esta sugestão agora.') : '';
    }
  }
  // Avisos do vínculo (componentes.md#avisos-vinculo): aviso em linha, nunca nas cores de erro.
  function avisos(sug) {
    const texto = {analise_sem_revisao: t('Esta análise não passou pela revisão de suporte. O vínculo começa em “não revisado”.'),
      achado_retirado: t('A revisão da IA retirou este achado: «{motivo}». Ele pode continuar ligado, com o suporte em “não revisado”: só sustenta o item se uma pessoa escolher.', {motivo: sug.achado?.motivo_destino || ''}),
      versao_substituida: t('Há uma versão mais nova deste achado.'),
      evidencia_indisponivel: t('A evidência não está mais disponível. O vínculo fica no registro, mas não abre o original.')};
    return (sug.avisos || []).filter(codigo => texto[codigo]).map(codigo => {
      const aviso = element('p', undefined, 'notice sugestao-aviso'); aviso.setAttribute('role', 'status');
      aviso.append(codigo === 'achado_retirado' ? dado('span', texto[codigo]) : element('span', texto[codigo])); return aviso;
    });
  }

  function evidencias(casoId, sug) {
    const lista = element('div', undefined, 'sugestao-evidencias');
    (sug.evidencias || []).forEach((ev, i) => {
      const v = vinculo(sug, i), bloco = element('div', undefined, 'sugestao-evidencia');
      if (ev.estado === 'indisponivel') { bloco.append(element('p', t('A evidência não está mais disponível. O vínculo fica no registro, mas não abre o original.'), 'small')); lista.append(bloco); return; }
      const loc = ev.localizador?.legivel || '', nome = ev.documento?.nome || '';
      bloco.append(dado('blockquote', ev.trecho || t('Fonte visual: consulte o original.')));
      const linha = element('p', undefined, 'small sugestao-localizador');
      const abrir = botao(t('abrir o original'), 'link-botao'), retorno = element('p', '', 'small'); retorno.setAttribute('role', 'status');
      abrir.setAttribute('aria-label', `${t('Abrir o original')}: ${nome} · ${loc}`.trim());
      abrir.addEventListener('click', () => Q.abrirOriginal(casoId, v, abrir, retorno));
      linha.append(dado('span', `${nome ? nome + ', ' : ''}${loc} · `), abrir);
      bloco.append(linha, retorno);
      const ia = ev.revisao_ia || v.revisao_ia;
      if (ia) {
        const veredito = element('p', undefined, 'small sugestao-veredito');
        veredito.append(Q.seloIA(ia.suporte), ' ', element('span', t(Q.NATUREZA[ia.natureza] || ia.natureza || ''), 'sugestao-natureza'));
        bloco.append(veredito);
      }
      lista.append(bloco);
    });
    if (sug.achado?.destino === 'fora_do_briefing') {
      lista.append(element('p', t('Fora do briefing (sustentado): a revisão sustentou o achado, mas ele não entrou no briefing.'), 'small sugestao-nota'));
    }
    return lista;
  }

  // Painel da sugestão (componentes.md#painel-sugestao). ctx: {casoId, recarregar(item), anunciar(texto), corrigir(sug)?}.
  function painel(sug, ctx) {
    const raiz = element('section', undefined, 'sugestao-painel'); raiz.dataset.sugestao = sug.id; raiz.tabIndex = -1;
    const titulo = dado('h4', proposta(sug), 'sugestao-titulo'); titulo.id = `sugestao-${sug.id}`;
    raiz.setAttribute('aria-labelledby', titulo.id);
    raiz.append(element('p', t('Sugestão da IA'), 'sugestao-rubrica'), titulo, evidencias(ctx.casoId, sug));
    const a = sug.analise;
    if (a) {
      const origem = element('p', t('Da análise de {dia}, às {hora}', {dia: dia(a.em_utc), hora: hora(a.em_utc)}), 'small sugestao-origem');
      raiz.append(origem);
      if (a.pergunta) { const d = element('details', undefined, 'sugestao-pergunta'); d.append(element('summary', t('Ver a pergunta')), dado('p', a.pergunta, 'small')); raiz.append(d); }
    }
    raiz.append(...avisos(sug));
    const permitido = pode(sug), bloqueio = permitido ? razaoBloqueio(sug) : '';
    const erro = element('p', undefined, 'sugestao-erro'); erro.setAttribute('role', 'alert'); erro.hidden = true;
    const acoes = element('div', undefined, 'sugestao-acoes');
    const confirmar = botao(t('Confirmar'), ''), descartar = botao(t('Descartar')), corrigir = ctx.corrigir ? botao(t('Corrigir')) : null;
    const todos = [confirmar, corrigir, descartar].filter(Boolean);
    acoes.append(...todos);
    const razao = !permitido ? t(PODE_EDITAR) : bloqueio;
    if (razao) {
      const nota = element('p', razao, 'small sugestao-razao'); nota.id = `sugestao-razao-${sug.id}`;
      if (!permitido) for (const b of todos) { b.disabled = true; b.setAttribute('aria-describedby', nota.id); }
      else { confirmar.disabled = true; confirmar.setAttribute('aria-describedby', nota.id); }
      raiz.append(erro, nota, acoes);
    } else raiz.append(erro, acoes);
    raiz.append(element('p', t('Confirmar põe a sugestão no quadro. A conferência no original continua no achado.'), 'small sugestao-pe'));

    // Ocupado: o botão escolhido no gerúndio, os outros desabilitados até a resposta (W11, regra 2). O erro fica no painel e a sugestão continua aberta.
    async function executar(botaoAtivo, rotuloOcupado, operacao, aoConcluir) {
      const rotulo = botaoAtivo.textContent;
      raiz.setAttribute('aria-busy', 'true'); erro.hidden = true; erro.textContent = '';
      for (const b of todos) b.disabled = true;
      botaoAtivo.textContent = rotuloOcupado;
      try {
        const resposta = await api(operacao, {caso: ctx.casoId, id: sug.id, requisicao_id: requisicao()});
        await aoConcluir(resposta);
      } catch (falha) {
        raiz.removeAttribute('aria-busy'); botaoAtivo.textContent = rotulo;
        for (const b of todos) b.disabled = (!permitido) || (b === confirmar && !!bloqueio);
        erro.textContent = `${t(operacao === 'sugestoes-confirmar' ? 'Não deu para confirmar:' : 'Não deu para descartar:')} ${falha.message}`; erro.hidden = false;
      }
    }
    confirmar.addEventListener('click', () => executar(confirmar, t('Confirmando…'), 'sugestoes-confirmar', async resposta => {
      const nome = sug.tipo === 'ligacao' ? t('a ligação') : (sug.campos?.nome || sug.campos?.descricao || sug.campos?.enunciado || '');
      await ctx.recarregar({item: resposta.item?.id || resposta.sugestao?.decisao?.item_id || null, proxima: null});
      ctx.anunciar(sug.tipo === 'ligacao' ? t('Sugestão confirmada: a ligação entrou no mapa.') : t('Sugestão confirmada: {nome} entrou no quadro.', {nome}));
    }));
    descartar.addEventListener('click', () => executar(descartar, t('Descartando…'), 'sugestoes-descartar', async () => {
      await ctx.recarregar({item: null, proxima: sug.id});
      ctx.anunciar(t('Sugestão descartada. Ela fica em Descartadas, com Restaurar.'));
    }));
    if (corrigir) corrigir.addEventListener('click', () => ctx.corrigir(sug));
    return raiz;
  }

  // "Descartadas (n)": <details> fechado no pé do quadro. Restaurar devolve a sugestão como sugestão, nunca como item.
  function descartadas(lista, ctx) {
    if (!lista.length) return null;
    const caixa = element('details', undefined, 'sugestoes-descartadas');
    caixa.append(element('summary', t('Descartadas ({n})', {n: lista.length})));
    const ul = element('ul', undefined, 'quadro-lista');
    for (const sug of lista) {
      const li = element('li', undefined, 'sugestao-descartada'); li.dataset.sugestao = sug.id;
      const texto = element('div', undefined, 'sugestao-descartada-texto');
      texto.append(dado('span', proposta(sug)));
      if (sug.descartada_antes) texto.append(element('span', t('já descartada em {dia}', {dia: dia(sug.descartada_antes.em_utc)}), 'small sugestao-nota'));
      const restaurar = botao(t('Restaurar')); restaurar.setAttribute('aria-label', `${t('Restaurar')}: ${proposta(sug)}`);
      if (window.Sessao?.pode && !pode(sug)) restaurar.disabled = true;
      const erro = element('p', undefined, 'small sugestao-erro'); erro.setAttribute('role', 'alert'); erro.hidden = true;
      restaurar.addEventListener('click', async () => {
        restaurar.disabled = true; restaurar.textContent = t('Restaurando…'); erro.hidden = true;
        try {
          await api('sugestoes-restaurar', {caso: ctx.casoId, id: sug.id, requisicao_id: requisicao()});
          await ctx.recarregar({item: null, proxima: sug.id});
          ctx.anunciar(t('Sugestão restaurada. Ela voltou a ser uma sugestão, não um item.'));
        } catch (falha) { restaurar.disabled = false; restaurar.textContent = t('Restaurar'); erro.textContent = `${t('Não deu para restaurar:')} ${falha.message}`; erro.hidden = false; }
      });
      li.append(texto, restaurar, erro); ul.append(li);
    }
    caixa.append(ul);
    return caixa;
  }
  const fonteCurta = sug => { const ev = sug.evidencias?.[0]; return ev && ev.estado !== 'indisponivel' ? `${ev.documento?.nome ? ev.documento.nome + ', ' : ''}${ev.localizador?.legivel || ''}` : t('Evidência indisponível'); };
  // A mesma sugestão numa lista de botões: é a leitura do quadro abaixo de 1024 px e o caminho pelo teclado em qualquer largura. `abrir(sug, botao)` mostra o painel.
  function secao(abertas, abrir, classe = '') {
    if (!abertas.length) return null;
    const caixa = element('section', undefined, `sugestoes-secao ${classe}`.trim());
    const titulo = element('h3', t('Sugestões da IA ({n})', {n: abertas.length}), 'sugestoes-titulo'); titulo.tabIndex = -1;
    caixa.append(titulo);
    const ul = element('ul', undefined, 'quadro-lista');
    for (const sug of abertas) {
      const li = element('li'), b = botao('', 'sugestao-abrir'); b.dataset.sugestao = sug.id; b.dataset.tipo = sug.tipo; b.setAttribute('aria-pressed', 'false');
      b.setAttribute('aria-label', rotuloAcessivel(sug));
      const selo = Q.seloSugestao(); selo.setAttribute('aria-hidden', 'true');
      b.append(selo, dado('span', proposta(sug), 'sugestao-texto'), dado('span', fonteCurta(sug), 'sugestao-fonte'));
      b.addEventListener('click', () => { for (const o of caixa.querySelectorAll('.sugestao-abrir')) o.setAttribute('aria-pressed', String(o === b)); abrir(sug, b); });
      li.append(b); ul.append(li);
    }
    caixa.append(ul);
    return caixa;
  }
  // Anúncio para leitor de tela que sobrevive à recarga do quadro: um só elemento, fora dos painéis das abas.
  function anunciar(texto) {
    const area = document.getElementById('area-quadros'); if (!area) return;
    let no = document.getElementById('quadros-anuncio');
    if (!no) { no = element('p', '', 'sr-only'); no.id = 'quadros-anuncio'; no.setAttribute('role', 'status'); area.append(no); }
    no.textContent = ''; no.textContent = texto;
  }
  // Contexto de um quadro para o painel: recarrega a aba e leva o foco ao item novo (confirmar) ou à próxima sugestão (descartar e restaurar).
  function contexto(casoId, abaId, extra = {}) {
    return {casoId, anunciar, ...extra, async recarregar({item = null, proxima = null} = {}) {
      await Q.selecionar(abaId, true);
      const painelAba = document.getElementById(`quadros-${abaId}`); if (!painelAba) return;
      let alvo = null;
      if (item) alvo = painelAba.querySelector(`[data-entidade="${item}"],[data-relacao="${item}"],[data-item="${item}"]`);
      if (!alvo && proxima) alvo = painelAba.querySelector('.sugestao-abrir:not([data-sugestao="' + proxima + '"])');
      alvo ||= painelAba.querySelector('.sugestoes-titulo') || painelAba;
      if (!alvo.hasAttribute('tabindex') && !/^(BUTTON|A|INPUT)$/.test(alvo.tagName)) alvo.tabIndex = -1;
      alvo.focus?.();
    }};
  }
  return {secao, fonteCurta, contexto, anunciar, listar, contagemTexto, painel, descartadas, proposta, rotuloAcessivel, vinculo, dataLegivel, precisaoDe, pode, requisicao, TIPO};
})();
