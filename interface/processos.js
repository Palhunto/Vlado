'use strict';
// Comparação entre processos (L9; componentes.md#comparar-processos; CONTRATO_QUADROS_ONDA4.md, seção 5). A análise procura o mesmo fundamento (documento, parecer)
// em mais de um processo e compara os desfechos; a revisão confere se o fundamento é de fato o mesmo e se os desfechos são comparáveis. A tela mostra o que o
// servidor devolve e nunca reconstrói a tabela do texto livre. A diferença de desfecho não prova irregularidade: aparece em cor neutra, nunca nas cores de erro.
// "=" na identidade é a comparação de hash feita pela Mesa; as seis linhas da conferência são da revisão da IA e vêm na forma da P20a.
window.Quadros.processos = (() => {
  const Q = window.Quadros, {t, dado, botao, linkBotao} = Q;
  const PODE_EDITAR = 'Só repórter e editor mudam os quadros.';
  const LINHAS = [
    ['versao', {mesmo: 'mesma versão', a_conferir: 'versão a conferir', diferente: 'versões diferentes'}],
    ['data', {mesmo: 'mesma data', a_conferir: 'data a conferir', diferente: 'datas diferentes'}],
    ['emissor', {mesmo: 'mesmo emissor', a_conferir: 'emissor a conferir', diferente: 'emissores diferentes'}],
    ['trecho', {mesmo: 'mesmo trecho', a_conferir: 'trecho a conferir', diferente: 'trechos diferentes'}],
    ['questao', {mesmo: 'mesma questão decidida', a_conferir: 'questão a conferir', diferente: 'questões diferentes'}],
    ['fase', {mesmo: 'mesma fase', a_conferir: 'fase a conferir', diferente: 'fases diferentes: {a} e {b}'}],
  ];
  const igual = (a, b) => String(a || '').trim().toLowerCase() === String(b || '').trim().toLowerCase();
  const pendentes = lista => lista.filter(c => c.pendente).length;

  function evidenciaDoLado(casoId, ev, rotulo) {
    const bloco = element('div', undefined, 'processo-evidencia');
    if (!ev || ev.estado === 'indisponivel') { bloco.append(element('p', t('A evidência não está mais disponível. O vínculo fica no registro, mas não abre o original.'), 'small')); return bloco; }
    const loc = ev.localizador?.legivel || '', nome = ev.documento?.nome || '';
    bloco.append(dado('blockquote', ev.trecho || t('Fonte visual: consulte o original.')));
    const linha = element('p', undefined, 'small processo-localizador'), abrir = linkBotao(t('abrir o original'), 'processo-abrir'), retorno = element('p', '', 'small'); retorno.setAttribute('role', 'status');
    abrir.setAttribute('aria-label', `${t('Abrir o original')}: ${nome} · ${loc}`.trim());
    abrir.addEventListener('click', () => Q.abrirOriginal(casoId, {referencia: ev.referencia, evidencia: {documento: ev.documento, trecho: ev.trecho, localizador: ev.localizador}, localizador: ev.localizador}, abrir, retorno));
    linha.append(dado('span', `${nome ? nome + ', ' : ''}${loc} · `), abrir); bloco.append(linha, retorno);
    return bloco;
  }
  function selosDaConferencia(c) {
    const lista = element('ul', undefined, 'processo-conferencia-lista');
    for (const [chave, textos] of LINHAS) {
      const estado = c.conferencias?.[chave] || 'a_conferir';
      const [a, b] = c.lados.map(l => l[chave === 'questao' ? 'questao' : chave === 'fase' ? 'fase' : ''] || '');
      const texto = t(textos[estado] || textos.a_conferir, {a, b});
      const li = element('li'); const pilula = element('span', `IA · ${texto}`, `support-badge ai-support processo-selo estado-${estado}`);
      li.append(pilula); lista.append(li);
    }
    return lista;
  }
  function tabelaOQueMuda(c) {
    const [A, B] = c.lados;
    const linhas = [['Questão decidida', A.questao, B.questao], ['Fase', A.fase, B.fase], ['Desfecho', A.desfecho, B.desfecho]];
    const tab = element('table', undefined, 'processo-muda'); tab.append(element('caption', t('O que muda'), 'sr-only'));
    const cab = element('tr'); for (const h of ['', 'Processo A', 'Processo B', 'Comparação']) { const th = element('th', h ? t(h) : '', ''); th.setAttribute('scope', 'col'); cab.append(th); }
    tab.append(element('thead')); tab.firstChild.append(cab);
    const corpo = element('tbody');
    for (const [rotulo, a, b] of linhas) {
      const tr = element('tr'); const th = element('th', t(rotulo)); th.setAttribute('scope', 'row');
      const ig = igual(a, b), cmp = element('td', undefined, 'processo-comparacao'); const sinal = element('span', ig ? '=' : '≠'); sinal.setAttribute('aria-hidden', 'true');
      cmp.append(sinal, ' ', element('span', t(ig ? 'igual' : 'diferente')));
      tr.append(th, dado('td', a), dado('td', b), cmp); corpo.append(tr);
    }
    tab.append(corpo);
    // Em 375: um cartão por linha, com A e B um abaixo do outro e "igual" ou "diferente" no título.
    const cartoes = element('div', undefined, 'processo-muda-cartoes');
    for (const [rotulo, a, b] of linhas) {
      const ig = igual(a, b), cartao = element('article', undefined, 'processo-muda-cartao');
      const h = element('h5'); h.append(element('span', t(rotulo)), ' · ', element('span', t(ig ? 'igual' : 'diferente')));
      cartao.append(h, element('p', t('Processo A'), 'small'), dado('p', a), element('p', t('Processo B'), 'small'), dado('p', b)); cartoes.append(cartao);
    }
    const caixa = element('div', undefined, 'processo-muda-caixa'); caixa.append(tab, cartoes);
    return caixa;
  }
  function comparacao(casoId, c, ctx) {
    const raiz = element('article', undefined, 'processo-comparacao-cartao'); raiz.dataset.achado = c.achado?.id || '';
    const [A, B] = c.lados;
    // Fundamento comum.
    const fund = element('section', undefined, 'processo-fundamento');
    fund.append(element('p', t('Fundamento comum'), 'processo-rubrica'), dado('h4', `${c.chave?.identificador || ''}${c.chave?.emissor ? ` · ${c.chave.emissor}` : ''}`, 'processo-fundamento-titulo'));
    const dl = element('dl', undefined, 'processo-chave');
    for (const [rot, val] of [['Identificador', c.chave?.identificador], ['Data', c.chave?.data], ['Emissor', c.chave?.emissor], ['Versão', c.chave?.versao]]) dl.append(element('dt', t(rot)), dado('dd', val || '—'));
    fund.append(dl);
    const identidade = element('p', undefined, 'processo-identidade');
    if (c.mesmo_arquivo) { const sinal = element('span', '='); sinal.setAttribute('aria-hidden', 'true'); identidade.append(sinal, ' ', element('span', t('Mesmo arquivo nos dois processos (mesmo hash)'))); identidade.classList.add('is-igual'); }
    else {
      identidade.append(element('span', `○ ${t('Mesmo fundamento a conferir: versões ou trechos diferentes')}`)); identidade.classList.add('is-a-conferir');
      if (ctx.aoComparar) { const ligar = linkBotao(t('Comparar os dois trechos'), 'processo-comparar-trechos'); ligar.addEventListener('click', () => ctx.aoComparar(c)); identidade.append(' ', ligar); }
    }
    fund.append(identidade);
    // Processo A e B.
    const lados = element('div', undefined, 'processo-lados');
    [[A, 'Processo A'], [B, 'Processo B']].forEach(([lado, rotulo]) => {
      const cartao = element('section', undefined, 'processo-lado');
      cartao.append(element('p', t(rotulo), 'processo-rubrica'), dado('p', lado.processo, 'processo-nome'), evidenciaDoLado(casoId, lado.fundamento),
        element('p', t('Desfecho'), 'processo-rubrica'), dado('p', lado.desfecho, 'processo-desfecho'));
      if (lado.desfecho_evidencia) cartao.append(evidenciaDoLado(casoId, lado.desfecho_evidencia));
      lados.append(cartao);
    });
    raiz.append(fund, lados, tabelaOQueMuda(c));
    // Conferência da comparação: veredito da IA e as seis linhas, sem a cor da conferência humana.
    const conf = element('section', undefined, 'processo-conferencia');
    conf.append(element('p', t('Conferência da comparação'), 'processo-rubrica'));
    if (c.revisao_ia?.suporte) conf.append(Q.seloIA(c.revisao_ia.suporte));
    conf.append(selosDaConferencia(c)); raiz.append(conf);
    if (c.pendente) {
      raiz.classList.add('is-pendente');
      const aviso = element('p', `! ${t('Comparação pendente: falta conferir que o fundamento e os desfechos são comparáveis.')}`, 'processo-pendente'); aviso.setAttribute('role', 'status'); raiz.append(aviso);
      // ação de lacuna: a comparação pendente vira pergunta ou pedido (a diligência não guarda vínculo com a comparação; o texto diz de qual se trata)
      const virar = Q.formularios?.virarPedido({casoId, texto: `${t('Conferir se o fundamento e os desfechos são comparáveis')}: ${c.chave?.identificador || ''}${c.chave?.emissor ? ` · ${c.chave.emissor}` : ''} (${A.processo} e ${B.processo})`, origemId: `comparacao|${c.achado?.id || ''}|${A.processo}|${B.processo}`}); if (virar) raiz.append(virar);
    }
    raiz.append(element('p', t('A diferença de desfecho não prova irregularidade.'), 'processo-pe'));
    // Ações.
    const acoes = element('div', undefined, 'processo-acoes');
    const abrir = botao(t('Abrir o achado para conferir'), ''); abrir.addEventListener('click', () => Q.irPara('achados')());
    const podeEditar = !window.Sessao?.pode || window.Sessao.pode('hipoteses-criar');
    const criar = botao(t('Criar hipótese com esta comparação')); criar.disabled = !podeEditar;
    if (!podeEditar) { const razao = element('p', t(PODE_EDITAR), 'small processo-razao'); razao.id = `processo-razao-${raiz.dataset.achado}`; criar.setAttribute('aria-describedby', razao.id); acoes.append(razao); }
    criar.addEventListener('click', () => ctx.criarHipotese?.(c));
    acoes.append(abrir, criar); raiz.append(acoes);
    return raiz;
  }

  // ctx: {criarHipotese(comparacao), aoComparar(comparacao)}. Devolve a vista inteira (com Anterior e Próxima); `carregar` busca as comparações do servidor.
  async function montar(casoId, ctx = {}) {
    const raiz = element('section', undefined, 'processos-vista');
    Q.estado(raiz, 'carregando', t('Carregando…'));
    let dados;
    try { dados = await api('comparar-processos', {caso: casoId, rodada: null}); }
    catch (erro) { Q.estado(raiz, 'erro', erro.message, {titulo: t('Não deu para abrir a comparação.')}); return raiz; }
    const lista = dados.comparacoes || [];
    if (!lista.length) {
      Q.estado(raiz, 'vazio', t('A análise compara processos quando o acervo tem mais de um sobre a mesma matéria e o mesmo fundamento aparece em mais de um deles.'), {titulo: t('Nenhuma comparação entre processos'), acao: Q.perguntar()});
      return raiz;
    }
    let atual = 0;
    const topo = element('div', undefined, 'processos-topo'), titulo = element('h3', t('Comparação entre processos'), 'processos-titulo'), conta = element('p', undefined, 'small processos-conta');
    const anterior = botao(t('Anterior')), proxima = botao(t('Próxima')), palco = element('div', undefined, 'processos-palco'); palco.setAttribute('aria-live', 'polite');
    const pintar = () => {
      conta.textContent = `${t(lista.length === 1 ? '{n} comparação' : '{n} comparações', {n: lista.length})}${pendentes(lista) ? ` · ${t(pendentes(lista) === 1 ? '{n} pendente' : '{n} pendentes', {n: pendentes(lista)})}` : ''} · ${atual + 1}/${lista.length}`;
      anterior.disabled = atual === 0; proxima.disabled = atual === lista.length - 1;
      palco.replaceChildren(comparacao(casoId, lista[atual], ctx));
    };
    anterior.addEventListener('click', () => { if (atual > 0) { atual -= 1; pintar(); } });
    proxima.addEventListener('click', () => { if (atual < lista.length - 1) { atual += 1; pintar(); } });
    const nav = element('div', undefined, 'processos-nav'); nav.append(anterior, proxima);
    topo.append(titulo, conta, nav);
    raiz.replaceChildren(topo, palco); pintar();
    return raiz;
  }
  return {montar, comparacao};
})();
