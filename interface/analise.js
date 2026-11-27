'use strict';
// Analysis boards on top of window.Quadros (quadros.js): document comparator (CONTRATO §5.4),
// verifiable tables with a source per cell (§5.7) and the people/organisation map (§5.5).
// Differences are shown with their context and never labelled as fraud or guilt; the map never
// merges entities and every link carries its evidence. The map and the timeline also exist as
// plain lists, which are what phones and screen readers use.
(() => {
  const Q = window.Quadros, {t, dado, botao} = Q;
  const SVG = 'http://www.w3.org/2000/svg';
  const svg = (tag, atributos = {}) => { const no = document.createElementNS(SVG, tag); for (const [k, v] of Object.entries(atributos)) no.setAttribute(k, v); return no; };
  const campo = (rotulo, controle) => { const l = element('label'); l.append(element('span', rotulo), controle); return l; };
  // Número decimal vindo do Core (ponto decimal) em notação pt-BR: milhar com ponto, decimal com vírgula. Outros valores passam como estão.
  const formatarNumero = valor => {
    const m = /^(-?)(\d+)(?:\.(\d+))?$/.exec(String(valor));
    if (!m) return String(valor);
    return `${m[1]}${m[2].replace(/\B(?=(\d{3})+(?!\d))/g, '.')}${m[3] !== undefined ? `,${m[3]}` : ''}`;
  };
  const lugar = loc => loc?.pagina_pdf ? t('p. {p}, linha {l}', {p: loc.pagina_pdf, l: loc.linha_inicio}) : t('linha {l}', {l: loc?.linha_inicio ?? '?'});

  // ---------- Comparator: two documents of a round, differences with context ----------
  const CLASSE = {valor: 'Diferença de valor', data: 'Diferença de data', valor_e_data: 'Diferença de valor e de data', conteudo: 'Diferença de conteúdo'};
  const MOTIVO = {unidades_incompativeis: 'Unidades diferentes: sem cálculo.', pareamento_ambiguo: 'Mais de um valor no trecho: sem cálculo.'};
  // Word segments: removed words are <del>, added are <ins> (strikethrough/underline, not colour only).
  function linhaMarcada(segmentos, lado) {
    const p = dado('p', undefined, 'comparar-linha');
    for (const s of segmentos || []) {
      const texto = s[lado];
      if (!texto) continue;
      if (s.operacao === 'igual') p.append(`${texto} `);
      else { p.append(element(lado === 'a' ? 'del' : 'ins', texto, lado === 'a' ? 'comparar-removido' : 'comparar-incluido'), ' '); }
    }
    return p;
  }
  function ladoAlteracao(alt, lado, rotulo) {
    const col = element('div', undefined, `comparar-lado lado-${lado}`);
    col.append(element('p', `${rotulo} · ${lugar(alt[`localizador_${lado}`])}`, 'small comparar-local'));
    const contexto = alt[`contexto_${lado}`] || [];
    const antes = Array.isArray(contexto) ? contexto.filter(l => l.linha < (alt[`localizador_${lado}`]?.linha_inicio ?? 0)) : [];
    const depois = Array.isArray(contexto) ? contexto.filter(l => l.linha > (alt[`localizador_${lado}`]?.linha_fim ?? Infinity)) : [];
    for (const l of antes) col.append(dado('p', l.texto, 'comparar-contexto small'));
    if (alt.palavras?.segmentos) col.append(linhaMarcada(alt.palavras.segmentos, lado));
    else if (alt[lado]) col.append(dado('p', alt[lado], `comparar-linha ${lado === 'a' ? 'comparar-removido' : 'comparar-incluido'}`));
    else col.append(element('p', lado === 'a' ? t('(sem trecho correspondente)') : t('(trecho ausente nesta versão)'), 'small'));
    for (const l of depois) col.append(dado('p', l.texto, 'comparar-contexto small'));
    return col;
  }
  function alteracao(alt, i, nomes) {
    const art = element('article', undefined, `comparar-alteracao classe-${alt.classe}`);
    art.append(element('h4', `${i + 1}. ${t(CLASSE[alt.classe] || alt.classe)}`));
    const lados = element('div', undefined, 'comparar-lados');
    lados.append(ladoAlteracao(alt, 'a', nomes.a), ladoAlteracao(alt, 'b', nomes.b));
    art.append(lados);
    const c = alt.calculo;
    if (c?.diferenca !== undefined && c?.diferenca !== null) art.append(element('p', t('Diferença calculada ({operacao}): {diferenca} {unidade}', {operacao: c.operacao, diferenca: formatarNumero(c.diferenca), unidade: c.unidade || ''}).trim(), 'small comparar-calculo'));
    else if (c?.motivo) art.append(element('p', t(MOTIVO[c.motivo] || c.motivo), 'small comparar-calculo'));
    return art;
  }
  function resultadoComparacao(dados, nomes) {
    const caixa = element('div', undefined, 'comparar-resultado');
    caixa.setAttribute('aria-live', 'polite');
    caixa.append(element('p', dados.identicos ? t('Os textos são idênticos.') : t('{n} diferenças · semelhança de {s}%', {n: dados.total_alteracoes ?? dados.alteracoes.length, s: Math.round((dados.semelhanca || 0) * 100)}), 'comparar-resumo'),
      element('p', t(dados.aviso || ''), 'small quadro-aviso'));
    if (dados.truncado) caixa.append(element('p', t('Há mais diferenças do que as mostradas. Compare trechos menores.'), 'notice'));
    for (const lado of ['a', 'b']) if (dados[lado]?.paginas_sem_texto?.length) caixa.append(element('p', t('{doc}: páginas sem texto ({p}) não entram na comparação; confira no original.', {doc: nomes[lado], p: dados[lado].paginas_sem_texto.join(', ')}), 'notice'));
    dados.alteracoes.forEach((alt, i) => caixa.append(alteracao(alt, i, nomes)));
    return caixa;
  }
  // Modo do Comparador (componentes.md#comparar-processos): "Documentos | Processos". Documentos é o comparador de sempre; Processos é a vista da comparação entre processos.
  function comModos(casoId, docs) {
    if (!Q.processos) return [docs];
    const proc = element('div', undefined, 'comparar-procs'); proc.hidden = true;
    const grupo = element('div', undefined, 'form-segmentado comparar-modos'); grupo.setAttribute('role', 'group'); grupo.setAttribute('aria-label', t('Comparar'));
    const bd = botao(t('Documentos'), 'form-segmento'), bp = botao(t('Processos'), 'form-segmento'); grupo.append(bd, bp);
    let carregado = false;
    const mostrar = async modo => {
      bd.setAttribute('aria-pressed', String(modo === 'documentos')); bp.setAttribute('aria-pressed', String(modo === 'processos'));
      docs.hidden = modo !== 'documentos'; proc.hidden = modo !== 'processos';
      if (modo === 'processos' && !carregado) {
        carregado = true;
        proc.replaceChildren(await Q.processos.montar(casoId, {aoComparar: () => mostrar('documentos'),
          criarHipotese: c => Q.formularios?.abrirNoPainel({tipo: 'hipotese', abaId: 'comparador', casoId, inicial: Q.formularios.hipoteseDaComparacao(c)})}));
      }
    };
    bd.addEventListener('click', () => mostrar('documentos')); bp.addEventListener('click', () => mostrar('processos'));
    bd.setAttribute('aria-pressed', 'true'); bp.setAttribute('aria-pressed', 'false');
    return [grupo, docs, proc];
  }
  Q.registrarAba({id: 'comparador', rotulo: t('Comparador'), carregar: Q.quadro('quadros_evidencia', async (painel, casoId, vigente) => {
    const inventario = await api('inventario', {caso: casoId});
    if (!vigente()) return;
    const rodadas = (typeof cases !== 'undefined' ? cases : []).find(c => c.id === casoId)?.rodadas || [];
    if (!rodadas.length) { const vazio = element('div'); Q.estado(vazio, 'vazio', t('Esta apuração ainda não tem análise com documentos preservados para comparar.'), {titulo: t('Nada para comparar ainda'), acao: Q.perguntar()}); Q.montarQuadro(painel, comModos(casoId, vazio)); return; }
    const form = element('form', undefined, 'comparar-form');
    const rodada = element('select'); rodada.id = 'comparar-rodada';
    rodada.replaceChildren(...rodadas.map(r => new Option(t('Análise {id}', {id: r.id}), r.id))); rodada.value = rodadas.at(-1).id;
    const escolha = id => { const s = element('select'); s.id = id; s.replaceChildren(...inventario.documentos.map(d => { const o = new Option(`${d.id} · ${Leitura.nome(d)}`, d.id); o.setAttribute('translate', 'no'); return o; })); return s; };
    const docA = escolha('comparar-documento-a'), docB = escolha('comparar-documento-b');
    if (inventario.documentos[1]) docB.value = inventario.documentos[1].id;
    const contexto = element('input'); contexto.id = 'comparar-contexto'; contexto.type = 'number'; contexto.min = '0'; contexto.max = '10'; contexto.value = '2';
    const enviar = botao(t('Comparar'), ''); enviar.type = 'submit';
    form.append(campo(t('Análise'), rodada), campo(t('Documento A'), docA), campo(t('Documento B'), docB), campo(t('Linhas de contexto'), contexto), enviar);
    const saida = element('div', undefined, 'comparar-saida');
    form.addEventListener('submit', async evento => {
      evento.preventDefault();
      if (docA.value === docB.value) { Q.estado(saida, 'erro', t('Escolha dois documentos diferentes.')); return; }
      enviar.disabled = true; Q.estado(saida, 'carregando', t('Comparando…'));
      try {
        const dados = await api('comparar-documentos', {caso: casoId, rodada: rodada.value, documento_a: docA.value, documento_b: docB.value,
          contexto: Math.max(0, Math.min(10, parseInt(contexto.value, 10) || 0))});
        const nome = id => { const d = inventario.documentos.find(x => x.id === id); return d ? `${id} · ${Leitura.nome(d)}` : id; };
        saida.replaceChildren(resultadoComparacao(dados, {a: nome(docA.value), b: nome(docB.value)}));
      } catch (erro) { Q.estado(saida, 'erro', erro.message); }
      finally { enviar.disabled = false; }
    });
    const docs = element('div', undefined, 'comparar-docs'); docs.append(element('p', t('Compara o texto extraído de dois documentos da mesma análise. As diferenças aparecem com o contexto de cada lado; confira valores e tabelas no original.'), 'small'), form, saida);
    Q.montarQuadro(painel, comModos(casoId, docs));
  })});

  // ---------- Verifiable tables: a source per cell, corrected cells, calculation panel ----------
  const ESTADO_CELULA = {extraido: 'com fonte', corrigido_manual: 'corrigida manualmente', pendente: 'pendente'};
  const unidadeColuna = c => [c.moeda, c.unidade].filter(Boolean).join(' ');
  // Values stay as recorded; only numeric columns are shown in pt-BR notation (the stored text does not change).
  const valorCelula = (coluna, valor) => ['numero', 'monetario'].includes(coluna?.tipo) ? formatarNumero(valor) : String(valor);
  // The calculation is rebuilt from its cell values (the same terms as tabelas_apuracao._termo), so only
  // values get pt-BR notation; any other number in the text (an ID such as E1234, a count, the divisor)
  // stays as recorded. Counting and unexpected shapes show the Core's expression unchanged.
  const termo = valor => String(valor).startsWith('-') ? `(${formatarNumero(valor)})` : formatarNumero(valor);
  function contaFormatada(calc) {
    const valores = (calc.celulas || []).map(c => c.valor);
    const montar = {soma: t => t.join(' + '), diferenca: t => t.length === 2 ? `${t[0]} - ${t[1]}` : null, media: t => `(${t.join(' + ')}) / ${t.length}`}[calc.operacao];
    const expressao = montar && valores.length && valores.every(v => v !== null && v !== undefined) ? montar(valores.map(termo)) : null;
    if (!expressao) return {expressao: String(calc.expressao), resultado: String(calc.resultado)};
    return {expressao, resultado: formatarNumero(calc.resultado)};
  }
  function detalheCelula(saida, linha, coluna, celula, ctx = {}) {
    if (saida.dataset.editando) return;
    saida.replaceChildren(element('p', t('Célula {linha} · {coluna}', {linha, coluna: coluna.nome}), 'eyebrow'));
    saida.append(dado('p', celula.valor === null ? t('(vazia)') : `${valorCelula(coluna, celula.valor)}${unidadeColuna(coluna) ? ' ' + unidadeColuna(coluna) : ''}`, 'tabela-valor'),
      element('p', t('Estado: {estado}', {estado: t(ESTADO_CELULA[celula.estado] || celula.estado)}), 'small'));
    if (celula.fonte === null) saida.append(element('p', t('Sem fonte vinculada.'), 'notice'));
    else saida.append(dado('p', t('Fonte: {fonte}', {fonte: celula.fonte_legivel || ''}), 'small'),
      element('p', celula.fonte_conferida ? t('Fonte conferida no original.') : t('Fonte indisponível: confira o original antes de usar.'), celula.fonte_conferida ? 'small' : 'notice'));
    const c = celula.ultima_correcao;
    if (c) {
      // Author and previous value are data: they keep their own language (translate="no").
      const linha = element('p', `${t('Corrigida por')} `, 'small');
      linha.append(dado('span', c.autor), ` ${t('em {quando}. Valor anterior:', {quando: new Date(c.em_utc).toLocaleString('pt-BR')})} `,
        c.valor_anterior === null || c.valor_anterior === undefined ? element('span', t('(vazio)')) : dado('span', valorCelula(coluna, c.valor_anterior)), '.');
      saida.append(linha, dado('p', t('Justificativa: {j}', {j: c.justificativa}), 'small'));
    }
    // Corrigir a célula: só para quem pode mudar a tabela; o painel fica travado enquanto o formulário está aberto.
    if (ctx.tabela && Q.formularios?.podeAtualizar('tabelas')) {
      const corrigir = botao(t('Corrigir esta célula'), 'tabela-corrigir'); corrigir.setAttribute('aria-label', `${t('Corrigir esta célula')}: ${linha} · ${coluna.nome}`);
      corrigir.addEventListener('click', () => {
        saida.dataset.editando = '1';
        const fechar = () => { delete saida.dataset.editando; detalheCelula(saida, linha, coluna, celula, ctx); saida.querySelector('.tabela-corrigir')?.focus(); };
        const form = Q.formularios.corrigirCelula({tabela: ctx.tabela, linha, coluna, celula, casoId: ctx.casoId, aoCancelar: fechar,
          aoSalvar: async () => { delete saida.dataset.editando; Q.sugestoes?.anunciar(t('Correção salva. O valor anterior fica guardado.')); await ctx.recarregar?.(); }});
        saida.replaceChildren(form); form.querySelector('.form-titulo')?.focus();
      });
      saida.append(corrigir);
    }
  }
  function grade(tabela, saida, ctx = {}) {
    const wrap = element('div', undefined, 'tabela-rolagem');
    const tab = element('table', undefined, 'tabela-conferivel');
    const legenda = dado('caption', tabela.titulo); tab.append(legenda);
    const cab = element('thead'), lc = element('tr');
    const canto = element('th', t('Linha')); canto.setAttribute('scope', 'col'); lc.append(canto);
    for (const c of tabela.colunas) { const th = dado('th', unidadeColuna(c) ? `${c.nome} (${unidadeColuna(c)})` : c.nome); th.setAttribute('scope', 'col'); lc.append(th); }
    cab.append(lc); tab.append(cab);
    const corpo = element('tbody'), celulas = [];
    tabela.linhas.forEach((linha, i) => {
      const tr = element('tr'), th = element('th', linha.id); th.setAttribute('scope', 'row'); tr.append(th);
      tabela.colunas.forEach((coluna, j) => {
        const cel = linha.celulas[coluna.id], td = element('td', undefined, `tabela-celula estado-${cel.estado}`);
        td.tabIndex = (i === 0 && j === 0) ? 0 : -1; td.dataset.linha = linha.id; td.dataset.coluna = coluna.id;
        td.append(dado('span', cel.valor === null ? '—' : valorCelula(coluna, cel.valor)));
        if (cel.estado !== 'extraido') td.append(element('span', ` (${t(ESTADO_CELULA[cel.estado])})`, 'tabela-marca'));
        const mostrar = () => detalheCelula(saida, linha.id, coluna, cel, {...ctx, tabela});
        td.addEventListener('focus', mostrar); td.addEventListener('mouseenter', mostrar); td.addEventListener('click', () => td.focus());
        td.addEventListener('keydown', evento => {
          const passo = {ArrowRight: [0, 1], ArrowLeft: [0, -1], ArrowDown: [1, 0], ArrowUp: [-1, 0]}[evento.key];
          if (!passo) return;
          const alvo = celulas[i + passo[0]]?.[j + passo[1]];
          if (!alvo) return;
          evento.preventDefault(); td.tabIndex = -1; alvo.tabIndex = 0; alvo.focus();
        });
        (celulas[i] ||= [])[j] = td; tr.append(td);
      });
      corpo.append(tr);
    });
    tab.append(corpo); wrap.append(tab);
    return {wrap, celulas};
  }
  function painelCalculo(tabela, celulas) {
    const secao = element('section', undefined, 'tabela-calculos');
    secao.append(element('h4', t('Cálculos declarados')));
    if (!tabela.calculos.length) { secao.append(element('p', t('Nenhum cálculo declarado nesta tabela.'), 'small')); return secao; }
    const OPER = {soma: 'Soma', diferenca: 'Diferença', contagem: 'Contagem', media: 'Média'};
    for (const calc of tabela.calculos) {
      const art = element('article', undefined, `tabela-calculo estado-${calc.estado}`);
      art.append(dado('h5', calc.nome || calc.id), element('p', t('Operação: {op}', {op: t(OPER[calc.operacao] || calc.operacao)}), 'small'));
      if (calc.estado === 'recusado') { art.append(element('p', t('Cálculo recusado: {erro}', {erro: calc.erro}), 'notice')); secao.append(art); continue; }
      const g = calc.grandeza || {};
      const conta = contaFormatada(calc);
      art.append(dado('p', `${conta.expressao} = ${conta.resultado}${[g.moeda, g.unidade].filter(Boolean).length ? ' ' + [g.moeda, g.unidade].filter(Boolean).join(' ') : ''}`, 'tabela-expressao'));
      if (calc.arredondamento) art.append(element('p', t('Arredondado para {casas} casas.', {casas: calc.arredondamento.casas}), 'small'));
      art.append(element('p', calc.estado === 'com_fonte' ? t('Todas as células têm fonte.') : t('Há células pendentes ou fontes indisponíveis: resultado provisório.'), calc.estado === 'com_fonte' ? 'small' : 'notice'));
      const lista = element('ul', undefined, 'tabela-usadas');
      for (const c of calc.celulas || []) {
        const coluna = tabela.colunas.find(col => col.id === c.coluna);
        lista.append(dado('li', `${c.linha} · ${c.nome_coluna || c.coluna}: ${c.valor === null || c.valor === undefined ? '—' : valorCelula(coluna, c.valor)} · ${c.fonte_legivel || t('sem fonte')}`, 'small'));
      }
      const ver = botao(t('Destacar células usadas'));
      ver.setAttribute('aria-pressed', 'false');
      ver.addEventListener('click', () => {
        const ligar = ver.getAttribute('aria-pressed') !== 'true';
        ver.setAttribute('aria-pressed', String(ligar));
        const usadas = new Set((calc.celulas || []).map(c => `${c.linha}|${c.coluna}`));
        for (const td of celulas.flat()) td.classList.toggle('is-usada', ligar && usadas.has(`${td.dataset.linha}|${td.dataset.coluna}`));
      });
      art.append(element('p', t('Células usadas ({n})', {n: (calc.celulas || []).length}), 'small'), lista, ver);
      secao.append(art);
    }
    return secao;
  }
  Q.registrarAba({id: 'tabelas', rotulo: t('Tabelas'), carregar: Q.quadro('tabelas_apuracao', async (painel, casoId, vigente) => {
    const lista = await api('tabelas-listar', {caso: casoId});
    if (!vigente()) return;
    const nova = Q.formularios?.botaoNovo('tabela', 'tabelas', casoId);
    if (!lista.tabelas.length) {
      const vazio = element('div'); Q.estado(vazio, 'vazio', t('Uma tabela conferível reúne números tirados dos documentos, cada um com a sua fonte.'), {titulo: t('Nenhuma tabela ainda'), acao: Q.perguntar()});
      Q.montarQuadro(painel, [...(nova ? [nova] : []), vazio]); return;
    }
    const escolha = element('select'); escolha.id = 'tabelas-escolha';
    escolha.replaceChildren(...lista.tabelas.map(tb => { const o = new Option(`${tb.titulo} · ${t('{n} linhas', {n: tb.total_linhas})}`, tb.id); o.setAttribute('translate', 'no'); return o; }));
    const area = element('div', undefined, 'tabela-area');
    // duas escolhas seguidas com o servidor lento: só a última resposta é pintada
    let pedidoAbrir = 0;
    async function abrir() {
      const pedido = ++pedidoAbrir;
      Q.estado(area, 'carregando', t('Carregando…'));
      try {
        const tabela = await api('tabelas-detalhe', {caso: casoId, id: escolha.value});
        if (pedido !== pedidoAbrir || !vigente()) return;
        const fonte = element('aside', undefined, 'tabela-fonte'); fonte.setAttribute('aria-live', 'polite'); fonte.id = 'tabela-fonte';
        fonte.append(element('p', t('Leve o foco a uma célula para ver a fonte, o estado e a última correção.'), 'small'));
        const {wrap, celulas} = grade(tabela, fonte, {casoId, recarregar: abrir});
        const n = tabela.celulas_por_estado || {};
        const contar = (q, um, varios) => t(q === 1 ? um : varios, {n: q});
        area.replaceChildren(element('p', [contar(n.extraido || 0, '{n} com fonte', '{n} com fonte'), contar(n.corrigido_manual || 0, '{n} corrigida', '{n} corrigidas'),
          contar(n.pendente || 0, '{n} pendente', '{n} pendentes')].join(' · '), 'small'),
          element('p', t('Use as setas para andar pelas células.'), 'small'), element('div', undefined, 'tabela-layout'));
        area.lastChild.append(wrap, fonte);
        area.append(painelCalculo(tabela, celulas), element('p', t(tabela.aviso || ''), 'small quadro-aviso'));
      } catch (erro) { if (pedido === pedidoAbrir && vigente()) Q.estado(area, 'erro', erro.message); }
    }
    if (Q.tabelaEscolhida && lista.tabelas.some(tb => tb.id === Q.tabelaEscolhida)) escolha.value = Q.tabelaEscolhida;
    Q.tabelaEscolhida = null;
    const editar = element('div', undefined, 'quadro-acoes'); if (nova) editar.append(nova);
    const editarAtual = () => { editar.querySelector('.quadro-editar')?.remove(); const b = Q.formularios?.botaoEditar('tabela', 'tabelas', casoId, escolha.value, escolha.selectedOptions?.[0]?.textContent || ''); if (b) editar.append(b); };
    escolha.addEventListener('change', () => { editarAtual(); abrir(); });
    editarAtual();
    Q.montarQuadro(painel, [campo(t('Tabela'), escolha), ...(editar.children.length ? [editar] : []), area]);
    await abrir();
  })});

  // ---------- Relationship map: SVG drawing plus the same links as a list ----------
  const SIT_RELACAO = {documentada: 'Documentada', inferida: 'Inferida', suporte_parcial: 'Suporte parcial', suporte_nao_revisado: 'Suporte não revisado',
    sem_suporte_sustentado: 'Sem suporte sustentado', fonte_indisponivel: 'Fonte indisponível'};
  const MOTIVO_HOM = {nome_igual: 'Nome igual', mesmas_palavras: 'Mesmas palavras em outra ordem', nome_contido: 'Um nome contido no outro',
    grafia_parecida: 'Grafia parecida', identificador_igual: 'Identificador igual'};
  const SIT_HOM = {pendente: 'Conferência pendente', mesma_entidade: 'Decidido: mesma entidade (as duas continuam no mapa)', entidade_distinta: 'Decidido: entidades distintas',
    indeterminado: 'Indeterminado', decisoes_divergentes: 'Decisões divergentes'};
  const traco = sit => sit === 'documentada' ? 'solido' : sit === 'inferida' ? 'tracejado' : sit === 'sugestao' ? 'sugestao' : 'pontilhado';
  // Sugestões da IA abertas entram no desenho no lugar que teriam como item (P45): pessoa e organização viram nós; a ligação só se desenha quando as duas
  // pontas existem (item confirmado ou outra sugestão aberta), senão fica na lista de sugestões. O rótulo começa por "IA ·".
  function comSugestoes(mapa, abertas) {
    const entidades = [...mapa.entidades], relacoes = [...mapa.relacoes], ids = new Set(entidades.map(e => e.id));
    for (const sug of abertas) if (sug.tipo === 'pessoa' || sug.tipo === 'organizacao') { entidades.push({id: sug.id, nome: sug.campos.nome, tipo: sug.tipo, sugestao: sug}); ids.add(sug.id); }
    for (const sug of abertas) if (sug.tipo === 'ligacao') {
      const origem = sug.campos.origem || sug.pontas?.origem?.sugestao_id, destino = sug.campos.destino || sug.pontas?.destino?.sugestao_id;
      if (ids.has(origem) && ids.has(destino) && origem !== destino) relacoes.push({id: sug.id, origem, destino, tipo: `IA · ${sug.campos.tipo}`, situacao: 'sugestao', sugestao: sug});
    }
    return {...mapa, entidades, relacoes};
  }
  function detalheRelacao(casoId, saida, r, nomes) {
    saida.replaceChildren(dado('h4', `${nomes[r.origem]} — ${r.tipo} — ${nomes[r.destino]}`),
      element('p', t('Situação: {s}', {s: t(SIT_RELACAO[r.situacao] || r.situacao)}), 'small'));
    if (r.descricao) saida.append(dado('p', r.descricao, 'small'));
    const origem = Q.sugestoes?.nota('mapa', r.id); if (origem) saida.append(origem);
    // Suporte só da IA (componentes.md#suporte-so-da-ia): "✓ n evidências conferidas no original" fica para o que uma pessoa conferiu; o suporte que veio só da revisão
    // da IA vai na pílula da P20a ("IA · n evidências sustentadas"), sem a cor nem o sinal da conferência humana. Havendo as duas coisas, as duas pílulas.
    const evs = r.evidencias || [], conferidas = evs.filter(v => v.conferencia_humana?.estado === 'conferida_no_original').length;
    const soIA = evs.filter(v => v.suporte_so_da_ia === true && v.suporte === 'sustentado').length;
    if (conferidas || soIA) {
      const selos = element('p', undefined, 'mapa-selos small');
      if (conferidas) selos.append(element('span', `✓ ${t(conferidas === 1 ? '{n} evidência conferida no original' : '{n} evidências conferidas no original', {n: conferidas})}`, 'human-review-badge human-conferida_no_original'));
      if (soIA) selos.append(element('span', t(soIA === 1 ? 'IA · {n} sustentada' : 'IA · {n} evidências sustentadas', {n: soIA}), 'support-badge ai-support'));
      saida.append(selos);
    }
    const lista = element('ul', undefined, 'quadro-lista');
    for (const v of evs) lista.append(Q.evidencia(casoId, v));
    saida.append(lista);
    const editar = r.sugestao ? null : Q.formularios?.botaoEditar('ligacao', 'mapa', casoId, r.id, `${nomes[r.origem]} — ${r.tipo}`, () => ({entidades: Object.entries(nomes).filter(([id]) => id[0] === 'P').map(([id, nome]) => ({id, nome}))}));
    if (editar) saida.append(editar);
  }
  // Ícone do tipo de relação, pelo texto livre do tipo (sócio, parentesco, cargo, pagamento, contrato); o rótulo sempre leva o texto também.
  const semAcento = texto => String(texto || '').normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase();
  function iconeRelacao(tipo) {
    const x = semAcento(tipo);
    if (/soci/.test(x)) return 'relacao-socio';
    if (/irma|\bpai\b|\bmae\b|filh|conjuge|espos|marido|parent|primo|\btio\b|\btia\b|sobrinh|neto|\bavo|genro|nora|cunhad/.test(x)) return 'relacao-parentesco';
    if (/cargo|servidor|diretor|secretari|nomead|president|gerente|funcionari|cedid|lotad/.test(x)) return 'relacao-cargo';
    if (/pagou|pagamento|\bpago|repass|empenh|recebeu/.test(x)) return 'pagamento';
    if (/contrat|licit|convenio|aditiv/.test(x)) return 'contrato';
    return 'relacao-vinculo';
  }
  Q.iconeRelacao = iconeRelacao;   // exposto para o teste do mapeamento
  const iconeNo = e => (e.tipo === 'organizacao' ? 'empresa' : 'pessoa');   // órgão público: pede um campo de natureza no Core (hoje só pessoa ou organização)
  const cortar = (texto, max) => { const x = String(texto || ''); return x.length > max ? `${x.slice(0, max - 1).trimEnd()}…` : x; };
  // Ícone dentro do SVG do mapa: o caminho do Design, na escala pedida, em torno do ponto (cx, cy).
  function icone(nome, cx, cy, tamanho, classe) {
    const g = svg('g', {class: classe, transform: `translate(${cx - tamanho / 2} ${cy - tamanho / 2}) scale(${tamanho / 24})`, 'aria-hidden': 'true'});
    g.append(svg('path', {d: Q.CAMINHOS[nome] || Q.CAMINHOS['relacao-vinculo']}));
    return g;
  }
  // Disposição do mapa (componentes.md#mapa, "Rótulo não cobre nó nem outra ligação"): a entidade mais ligada vai ao centro e as demais ao anel; a
  // ordem no anel e o ponto de cada rótulo na sua ligação são escolhidos para que nenhuma pílula cubra um nó nem outra ligação, e as ligações
  // se cruzem o mínimo. Determinística (mesma entrada, mesmo desenho), de modo que o teste confere o custo.
  const NO_L = 200, NO_A = 80, PILULA_A = 28, GRANDE_MAPA = 8, ORCAMENTO_MS = 150, PARTE_RAPIDA = 0.45;
  const agora = () => (typeof performance !== 'undefined' && performance.now ? performance.now() : Date.now());
  const larguraPilula = texto => Math.round(34 + cortar(texto, 22).length * 7.8);
  const retNo = ([x, y]) => [x - NO_L / 2, y - NO_A / 2, x + NO_L / 2, y + NO_A / 2];
  // Segmento (a→b) contra retângulo [x0,y0,x1,y1]: método de Liang–Barsky.
  function cortaRet(a, b, [x0, y0, x1, y1]) {
    let t0 = 0, t1 = 1; const dx = b[0] - a[0], dy = b[1] - a[1];
    for (const [p, q] of [[-dx, a[0] - x0], [dx, x1 - a[0]], [-dy, a[1] - y0], [dy, y1 - a[1]]]) {
      if (p === 0) { if (q < 0) return false; continue; }
      const r = q / p;
      if (p < 0) { if (r > t1) return false; if (r > t0) t0 = r; } else { if (r < t0) return false; if (r < t1) t1 = r; }
    }
    return true;
  }
  const cruza = (a, b, c, d) => {
    const o = (p, q, r) => Math.sign((q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0]));
    return o(a, b, c) !== o(a, b, d) && o(c, d, a) !== o(c, d, b);
  };
  const sobrepoe = (r1, r2) => r1[0] < r2[2] && r2[0] < r1[2] && r1[1] < r2[3] && r2[1] < r1[3];
  function dispor(mapa, opcoes = {}) {
    const n = mapa.entidades.length, grau = {};
    for (const r of mapa.relacoes) { grau[r.origem] = (grau[r.origem] || 0) + 1; grau[r.destino] = (grau[r.destino] || 0) + 1; }
    const centro = n >= 3 ? [...mapa.entidades].sort((a, b) => (grau[b.id] || 0) - (grau[a.id] || 0))[0] : null;
    const anel = mapa.entidades.filter(e => e !== centro), m = anel.length;
    // Os nós têm 200 de largura, então o anel vira duas fileiras (acima e abaixo do centro, até três por fileira): as ligações descem ou sobem
    // com bastante espaço vertical para o rótulo, que seria espremido entre dois nós vizinhos na horizontal.
    const L = 760, D1 = 170, D2 = 140, niveis = m <= 5 ? 2 : Math.ceil(m / 2);
    const A = 2 * (D1 + (Math.ceil(niveis / 2) - 1) * D2 + NO_A / 2 + 24), cx = L / 2, cy = A / 2;
    const contagem = Array.from({length: niveis}, (_, j) => Math.max(0, Math.ceil((m - j) / niveis)));
    const lugares = [];
    for (let rank = 0; lugares.length < m; rank += 1) for (let j = 0; j < niveis; j += 1) {
      if (rank >= contagem[j]) continue;
      const k = contagem[j], dx = k === 1 ? 0 : k === 2 ? (rank ? 1 : -1) * 210 : (rank - 1) * (NO_L + 40);
      lugares.push([cx + dx, cy + (j % 2 ? 1 : -1) * (D1 + Math.floor(j / 2) * D2)]);
    }
    const fracoes = [0.5, 0.62, 0.38, 0.72, 0.28, 0.8, 0.2, 0.88, 0.12, 0.56, 0.44, 0.68, 0.32, 0.52, 0.48, 0.58, 0.42, 0.66, 0.34, 0.76, 0.24, 0.84, 0.16, 0.92, 0.08];
    const rels = mapa.relacoes, larguras = rels.map(r => larguraPilula(r.tipo));
    const avaliar = pos => {
      let custo = 0;
      const seg = rels.map(r => [pos[r.origem] || [cx, cy], pos[r.destino] || [cx, cy]]);
      const nos = mapa.entidades.map(e => retNo(pos[e.id]));
      for (let i = 0; i < nos.length; i += 1) for (let j = i + 1; j < nos.length; j += 1) if (sobrepoe(nos[i], nos[j])) custo += 100000;
      for (const [k, r] of rels.entries()) {
        const [p, q] = seg[k];
        for (const [i, e] of mapa.entidades.entries()) if (e.id !== r.origem && e.id !== r.destino && cortaRet(p, q, nos[i])) custo += 400;   // a linha atravessa um nó que não é dela
        for (let o = k + 1; o < rels.length; o += 1) {
          const outra = rels[o];
          if (outra.origem !== r.origem && outra.origem !== r.destino && outra.destino !== r.origem && outra.destino !== r.destino && cruza(p, q, seg[o][0], seg[o][1])) custo += 60;
        }
      }
      // Cada rótulo escolhe o ponto da própria ligação que não cobre nó, outra ligação nem outro rótulo; duas passadas, a segunda já sabendo
      // onde ficaram todos os outros.
      const pilulas = {}, postas = [];
      const escolher = (r, k) => {
        const [p, q] = seg[k], doCentro = centro && r.destino === centro.id ? [q, p] : [p, q], meia = larguras[k] / 2 + 2;
        let melhor = null;
        for (const [f, fr] of fracoes.entries()) {
          if (melhor && melhor.c <= f) break;   // o custo de uma fração é no mínimo o seu índice: as seguintes não vencem
          const mx = Math.round(doCentro[0][0] + (doCentro[1][0] - doCentro[0][0]) * fr), my = Math.round(doCentro[0][1] + (doCentro[1][1] - doCentro[0][1]) * fr);
          const ret = [mx - meia, my - PILULA_A / 2 - 2, mx + meia, my + PILULA_A / 2 + 2];
          let c = f;   // desempate: a primeira fração (mais perto do meio ou do ponto preferido)
          for (const rn of nos) if (sobrepoe(ret, rn)) c += 5000;
          for (let o = 0; o < rels.length; o += 1) if (o !== k && cortaRet(seg[o][0], seg[o][1], ret)) c += 3000;
          for (let o = 0; o < rels.length; o += 1) if (o !== k && postas[o] && sobrepoe(ret, postas[o].ret)) c += 5000;
          if (!melhor || c < melhor.c) melhor = {c, mx, my, ret};
        }
        postas[k] = pilulas[r.id] = {x: melhor.mx, y: melhor.my, largura: larguras[k], ret: melhor.ret, c: melhor.c};
      };
      for (let passada = 0; passada < 2; passada += 1) for (const [k, r] of rels.entries()) escolher(r, k);
      for (const r of rels) custo += pilulas[r.id].c;
      return {custo, pilulas};
    };
    const montar = ordem => {
      const pos = {}; if (centro) pos[centro.id] = [cx, cy]; else if (n === 1) pos[mapa.entidades[0].id] = [cx, cy];
      ordem.forEach((e, i) => { pos[e.id] = lugares[i].map(Math.round); });
      return pos;
    };
    // Orçamento de tempo: a busca por trocas custa muito com o número de entidades (28 entidades e 40 ligações levavam 50 s com a avaliação inteira
    // a cada troca). Ela roda em qualquer tamanho, mas para ao estourar o orçamento e fica com a melhor disposição até ali. Até GRANDE_MAPA entidades
    // a avaliação inteira cabe no orçamento; acima disso a busca usa a avaliação rápida (só o que muda com a troca) e a inteira vale para o resultado.
    // Com `completa` não há orçamento: é a referência do teste, a busca que o orçamento aproxima.
    const prazo = opcoes.completa ? Infinity : (opcoes.orcamento ?? ORCAMENTO_MS), inicioBusca = agora();
    const estourou = (parte = 1) => agora() - inicioBusca > prazo * parte;
    const porGrau = [...anel].sort((a, b) => (grau[b.id] || 0) - (grau[a.id] || 0));
    let melhor = null;
    const ordemRapida = () => {
      const idx = new Map(mapa.entidades.map((e, i) => [e.id, i])), R = mapa.relacoes.length, extra = mapa.entidades.length;
      const U = mapa.relacoes.map(r => idx.get(r.origem) ?? extra), V = mapa.relacoes.map(r => idx.get(r.destino) ?? extra);
      const ci = centro ? idx.get(centro.id) : -1;
      const px = new Array(extra + 1).fill(cx), py = new Array(extra + 1).fill(cy), meia = larguraPilula;
      const largura = mapa.relacoes.map(r => meia(r.tipo));
      const incide = Array.from({length: extra + 1}, () => []);
      for (let r = 0; r < R; r += 1) { incide[U[r]].push(r); if (V[r] !== U[r]) incide[V[r]].push(r); }
      const colocar = ordem => ordem.forEach((e, i) => { const k = idx.get(e.id); px[k] = Math.round(lugares[i][0]); py[k] = Math.round(lugares[i][1]); });
      // Um rótulo vale a primeira fração livre de nó (as frações seguem a ordem de preferência); cada nó coberto custa 5000.
      const rotulo = r => {
        const [p, q] = ci >= 0 && V[r] === ci ? [V[r], U[r]] : [U[r], V[r]], dx = largura[r] / 2 + 102;
        let melhorC = Infinity;
        for (let k = 0; k < fracoes.length && melhorC > k; k += 1) {
          const mx = Math.round(px[p] + (px[q] - px[p]) * fracoes[k]), my = Math.round(py[p] + (py[q] - py[p]) * fracoes[k]);
          let c = k;
          for (let e = 0; e < extra; e += 1) if (Math.abs(mx - px[e]) < dx && Math.abs(my - py[e]) < 56) c += 5000;
          if (c < melhorC) melhorC = c;
        }
        return melhorC;
      };
      const noCortado = r => {
        let c = 0; const a = [px[U[r]], py[U[r]]], b = [px[V[r]], py[V[r]]];
        for (let e = 0; e < extra; e += 1) if (e !== U[r] && e !== V[r] && cortaRet(a, b, [px[e] - NO_L / 2, py[e] - NO_A / 2, px[e] + NO_L / 2, py[e] + NO_A / 2])) c += 400;
        return c;
      };
      const marca = new Uint8Array(R);
      // Custo do conjunto S de ligações com as posições atuais: rótulo, nó atravessado e cruzamento com qualquer outra (um par de S conta uma vez).
      const custo = S => {
        let c = 0; for (const r of S) marca[r] = 1;
        for (const r of S) {
          c += rotulo(r) + noCortado(r);
          const a = [px[U[r]], py[U[r]]], b = [px[V[r]], py[V[r]]];
          for (let o = 0; o < R; o += 1) {
            if (o === r || (marca[o] && o < r) || U[o] === U[r] || U[o] === V[r] || V[o] === U[r] || V[o] === V[r]) continue;
            if (cruza(a, b, [px[U[o]], py[U[o]]], [px[V[o]], py[V[o]]])) c += 60;
          }
        }
        for (const r of S) marca[r] = 0;
        return c;
      };
      const todas = Array.from({length: R}, (_, r) => r);
      let melhorOrdem = null, melhorCusto = Infinity;
      // Sobe por trocas (a primeira que melhora fica) até não haver troca que melhore ou acabar o prazo da busca rápida.
      const subir = ordem => {
        colocar(ordem);
        for (let volta = 0; volta < 30 && m > 1 && !estourou(PARTE_RAPIDA); volta += 1) {
          let mudou = false;
          for (let i = 0; i < m && !estourou(PARTE_RAPIDA); i += 1) for (let j = i + 1; j < m; j += 1) {
            const a = idx.get(ordem[i].id), b = idx.get(ordem[j].id), S = [...new Set([...incide[a], ...incide[b]])], antes = custo(S);
            [px[a], px[b]] = [px[b], px[a]]; [py[a], py[b]] = [py[b], py[a]];
            if (custo(S) < antes) { [ordem[i], ordem[j]] = [ordem[j], ordem[i]]; mudou = true; } else { [px[a], px[b]] = [px[b], px[a]]; [py[a], py[b]] = [py[b], py[a]]; }
            if (estourou(PARTE_RAPIDA)) break;
          }
          if (!mudou) break;
        }
        const total = custo(todas);
        if (total < melhorCusto) { melhorCusto = total; melhorOrdem = [...ordem]; }
      };
      const larguraDe = e => Math.max(0, ...mapa.relacoes.filter(r => r.origem === e.id || r.destino === e.id).map(r => larguraPilula(r.tipo)));
      const porRotulo = [...anel].sort((a, b) => larguraDe(a) - larguraDe(b));   // rótulo curto nos lugares perto do centro, onde a ligação é curta
      for (const inicio of [porGrau, porRotulo, anel, [...anel].reverse()]) if (!melhorOrdem || !estourou(PARTE_RAPIDA)) subir([...inicio]);
      // Sobrou prazo e ainda há rótulo sobre nó (custo de 5000 ou mais): recomeça do melhor com três trocas ao acaso (sequência fixa, o resultado se repete).
      let semente = 20251122;
      const acaso = limite => { semente = (semente * 1103515245 + 12345) % 2147483648; return semente % limite; };
      while (m > 2 && melhorCusto >= 5000 && !estourou(PARTE_RAPIDA)) {
        const ordem = [...melhorOrdem];
        for (let k = 0; k < 3; k += 1) { const i = acaso(m), j = acaso(m); [ordem[i], ordem[j]] = [ordem[j], ordem[i]]; }
        subir(ordem);
      }
      return melhorOrdem;
    };
    // Mapa pequeno (ou `completa`): a avaliação inteira a cada troca, de três pontos de partida. Mapa grande: a busca rápida escolhe a ordem e a avaliação inteira a refina no que sobrar do orçamento.
    const rapida = n > GRANDE_MAPA && !opcoes.completa;
    // Pares de lugares a trocar: todos, ou (mapa grande) só os que mexem com uma entidade de ligação cujo rótulo ainda não achou lugar livre.
    const pares = (ordem, atual) => {
      const lista = [];
      const quentes = new Set();
      if (rapida) for (const r of mapa.relacoes) if (atual.pilulas[r.id].c >= 3000) for (const id of [r.origem, r.destino]) { const k = ordem.findIndex(e => e.id === id); if (k >= 0) quentes.add(k); }
      for (let i = 0; i < m; i += 1) for (let j = i + 1; j < m; j += 1) if (!rapida || quentes.has(i) || quentes.has(j)) lista.push([i, j]);
      return lista;
    };
    for (const inicio of rapida ? [ordemRapida()] : [anel, [...anel].reverse(), porGrau]) {
      if (melhor && estourou()) break;
      let ordem = [...inicio], atual = avaliar(montar(ordem));
      for (let volta = 0; volta < (rapida ? 60 : 12) && m > 1 && !estourou(); volta += 1) {
        let mudou = false;
        for (const [i, j] of pares(ordem, atual)) {
          const troca = [...ordem]; [troca[i], troca[j]] = [troca[j], troca[i]];
          const c = avaliar(montar(troca));
          if (c.custo < atual.custo) { ordem = troca; atual = c; mudou = true; if (rapida) break; }
          if (estourou()) break;
        }
        if (!mudou) break;
      }
      if (!melhor || atual.custo < melhor.custo) melhor = {...atual, pos: montar(ordem)};
    }
    return {L, A, pos: melhor.pos, pilulas: melhor.pilulas, custo: melhor.custo, centro};
  }
  Q.dispor = dispor;   // exposto para o teste: nenhuma pílula cobre nó nem outra ligação
  function diagrama(casoId, mapa, nomes, saida, abrirSugestao) {
    const {L, A, pos, pilulas} = Q.dispor(mapa), LARG = NO_L, ALT = NO_A;
    const desenho = svg('svg', {viewBox: `0 0 ${L} ${A}`, class: 'mapa-svg', role: 'group', 'aria-label': t('Diagrama do mapa. A lista ao lado traz as mesmas ligações.')});
    const rotulos = [];
    for (const r of mapa.relacoes) {
      const [x1, y1] = pos[r.origem] || [cx, cy], [x2, y2] = pos[r.destino] || [cx, cy];
      const g = svg('g', {class: `mapa-ligacao traco-${traco(r.situacao)}${r.sugestao ? ' is-sugestao' : ''}`, tabindex: '0', role: 'button', 'aria-pressed': 'false',
        'aria-label': r.sugestao ? Q.sugestoes.rotuloAcessivel(r.sugestao) : `${nomes[r.origem]} — ${r.tipo} — ${nomes[r.destino]}: ${t(SIT_RELACAO[r.situacao] || r.situacao)}`});
      g.dataset.relacao = r.id;
      g.append(svg('line', {x1, y1, x2, y2, class: 'mapa-linha'}), svg('line', {x1, y1, x2, y2, class: 'mapa-alvo'}));
      // Rótulo da ligação: pílula com o ícone do tipo e o texto do tipo, no meio da linha; segue a ligação (ativa, foco).
      const texto = cortar(r.tipo, 22), {x: mx, y: my, largura} = pilulas[r.id];
      const pilula = svg('g', {class: `mapa-pilula traco-${traco(r.situacao)}${r.sugestao ? ' is-sugestao' : ''}`, transform: `translate(${mx - largura / 2} ${my - 14})`, 'aria-hidden': 'true'});
      pilula.append(svg('rect', {width: largura, height: 28, rx: 14, class: 'mapa-pilula-fundo'}), icone(iconeRelacao(r.tipo), 17, 14, 14, 'mapa-pilula-icone'));
      const rotuloTexto = svg('text', {x: 30, y: 19, class: 'mapa-pilula-texto', translate: 'no'}); rotuloTexto.textContent = texto; pilula.append(rotuloTexto);
      const abrir = () => {
        for (const outro of desenho.querySelectorAll('.mapa-ligacao')) { outro.classList.remove('is-ativa'); outro.setAttribute('aria-pressed', 'false'); }
        for (const outra of desenho.querySelectorAll('.mapa-pilula')) outra.classList.remove('is-ativa');
        g.classList.add('is-ativa'); pilula.classList.add('is-ativa'); g.setAttribute('aria-pressed', 'true');
        if (r.sugestao) abrirSugestao(r.sugestao, g); else detalheRelacao(casoId, saida, r, nomes);
      };
      pilula.addEventListener('click', abrir);
      // Focus only highlights the line (CSS); the live detail panel changes on Enter, Space or click.
      g.addEventListener('click', abrir);
      g.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); abrir(); } });
      desenho.append(g); rotulos.push(pilula);
    }
    // Nós por cima das linhas e abaixo dos rótulos: caixa em HTML (o texto quebra e corta com reticências), ícone do tipo na forma do tipo.
    for (const e of mapa.entidades) {
      const [x, y] = pos[e.id], g = svg('g', {class: `mapa-no ${e.tipo}${e.sugestao ? ' is-sugestao' : ''}`});
      g.dataset.entidade = e.id;
      const fo = svg('foreignObject', {x: x - LARG / 2, y: y - ALT / 2, width: LARG, height: ALT});
      const cartao = element('div', undefined, 'mapa-cartao');
      const forma = element('span', undefined, 'mapa-ico'); forma.setAttribute('aria-hidden', 'true'); forma.append(Q.icone(iconeNo(e), 'mapa-ico-svg'));
      const textos = element('span', undefined, 'mapa-cartao-texto');
      // Sugestão: o selo "IA · sugestão" vai no lugar de "Pessoa · 3 documentos"; o tipo e a origem ficam no nome acessível e no painel.
      const sub = e.sugestao ? Q.seloSugestao() : element('span', e.tipo === 'organizacao' ? t('Organização') : t('Pessoa'), 'mapa-sub');
      if (e.sugestao) sub.setAttribute('aria-hidden', 'true');
      textos.append(dado('b', e.nome, 'mapa-nome'), sub);
      cartao.append(forma, textos); fo.append(cartao); g.append(fo, svg('title'));
      g.lastChild.textContent = e.sugestao ? Q.sugestoes.rotuloAcessivel(e.sugestao) : e.nome;
      if (e.sugestao) {
        g.setAttribute('tabindex', '0'); g.setAttribute('role', 'button'); g.setAttribute('aria-pressed', 'false'); g.setAttribute('aria-label', Q.sugestoes.rotuloAcessivel(e.sugestao));
        const abrir = () => {
          for (const o of desenho.querySelectorAll('.mapa-ligacao,.mapa-no.is-sugestao')) { o.classList.remove('is-ativa'); if (o.hasAttribute('aria-pressed')) o.setAttribute('aria-pressed', 'false'); }
          for (const o of desenho.querySelectorAll('.mapa-pilula')) o.classList.remove('is-ativa');
          g.classList.add('is-ativa'); g.setAttribute('aria-pressed', 'true'); abrirSugestao(e.sugestao, g);
        };
        g.addEventListener('click', abrir);
        g.addEventListener('keydown', ev => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); abrir(); } });
      }
      desenho.append(g);
    }
    // Os rótulos das ligações vão por cima dos nós (as linhas ficam por baixo, saindo do centro de cada um).
    for (const pilula of rotulos) desenho.append(pilula);
    return desenho;
  }
  function listaMapa(casoId, mapa, nomes, saida) {
    const lista = element('ul', undefined, 'mapa-lista');
    lista.setAttribute('aria-label', t('Pessoas e organizações, com as ligações de cada uma'));
    for (const e of mapa.entidades) {
      const li = element('li', undefined, `mapa-entidade ${e.tipo}`);
      li.append(dado('h4', e.nome), element('p', `${e.tipo === 'organizacao' ? t('Organização') : t('Pessoa')} · ${t({com_evidencia: 'Com evidência', evidencia_indisponivel: 'Evidência indisponível', sem_evidencia: 'Sem evidência'}[e.situacao] || e.situacao)}`, 'small'));
      if (e.identificadores?.length) li.append(dado('p', e.identificadores.map(i => `${i.tipo.toUpperCase()} ${i.valor_exibicao}`).join(' · '), 'small'));
      const origem = e.sugestao ? null : Q.sugestoes?.nota('mapa', e.id); if (origem) li.append(origem);
      const ligacoes = mapa.relacoes.filter(r => r.origem === e.id || r.destino === e.id);
      const sub = element('ul', undefined, 'mapa-ligacoes');
      for (const r of ligacoes) {
        const item = element('li');
        // The link reads the same from both ends: origin — type — destination, as it was recorded.
        item.append(dado('span', `${nomes[r.origem]} — ${r.tipo} — ${nomes[r.destino]} `), element('span', `· ${t(SIT_RELACAO[r.situacao] || r.situacao)} `, 'small'));
        const ver = botao(t('Ver evidências')); ver.dataset.relacao = r.id;
        ver.addEventListener('click', () => { detalheRelacao(casoId, saida, r, nomes); saida.focus?.(); });
        item.append(ver); sub.append(item);
      }
      if (!ligacoes.length) sub.append(element('li', t('Sem ligações registradas.'), 'small'));
      li.append(sub);
      const editar = Q.formularios?.botaoEditar('entidade', 'mapa', casoId, e.id, e.nome); if (editar) li.append(editar);
      lista.append(li);
    }
    return lista;
  }
  function homonimos(mapa) {
    const secao = element('aside', undefined, 'mapa-homonimos');
    secao.append(element('h4', t('Possíveis homônimos para conferência')),
      element('p', t('Sugestões por semelhança de nome ou identificador. Nada é fundido: a decisão é de uma pessoa, com fonte.'), 'small'));
    const lista = element('ul', undefined, 'quadro-lista');
    for (const h of mapa.homonimos || []) {
      const li = element('li', undefined, 'mapa-homonimo');
      li.append(dado('p', h.nomes.join(' · '), 'mapa-homonimo-nomes'), element('p', t('Motivo: {m}', {m: t(MOTIVO_HOM[h.motivo] || h.motivo)}), 'small'),
        element('p', t(SIT_HOM[h.situacao] || h.situacao), `small homonimo-${h.situacao}`));
      if (h.identificadores_comuns?.length) li.append(dado('p', t('Identificadores iguais: {i}', {i: h.identificadores_comuns.map(i => `${i.tipo.toUpperCase()} ${i.valor_exibicao}`).join(', ')}), 'small'));
      if (h.identificadores_divergentes?.length) {
        const linha = element('p', `${t('Identificadores diferentes:')} `, 'small');
        linha.append(dado('span', h.identificadores_divergentes.join(', '))); li.append(linha);
      }
      lista.append(li);
    }
    if (!mapa.homonimos?.length) lista.append(element('li', t('Nenhum possível homônimo encontrado.'), 'small quadro-vazio'));
    secao.append(lista);
    return secao;
  }
  // Legenda no pé do mapa (componentes.md#mapa): o que o mapa usa, e "Suporte parcial ou não revisado" só se houver ligação pontilhada.
  function legenda(mapa) {
    const l = element('ul', undefined, 'mapa-legenda');
    l.setAttribute('aria-label', t('Legenda'));
    const itens = [['pessoa', 'Pessoa'], ['organizacao', 'Organização'], ['traco-solido', 'Ligação com documento'], ['traco-tracejado', 'A confirmar, sem documento']];
    if (mapa.relacoes.some(r => traco(r.situacao) === 'pontilhado')) itens.push(['traco-pontilhado', 'Suporte parcial ou não revisado']);
    if (mapa.entidades.some(e => e.sugestao) || mapa.relacoes.some(r => r.sugestao)) itens.push(['sugestao', 'Sugestão da IA']);
    for (const [classe, texto] of itens) l.append(element('li', t(texto), `legenda-${classe}`));
    return l;
  }
  Q.registrarAba({id: 'mapa', rotulo: t('Mapa de relações'), carregar: Q.quadro('quadros_evidencia', async (painel, casoId, vigente) => {
    const mapa = await api('mapa-ver', {caso: casoId});
    const S = Q.sugestoes ? await Q.sugestoes.listar(casoId, 'mapa') : {abertas: [], descartadas: []};
    if (!vigente()) return;
    if (!mapa.entidades.length && !S.abertas.length && !S.descartadas.length) { Q.estado(painel, 'vazio', t('O mapa mostra as pessoas e organizações que os documentos citam e como elas se ligam.'), {titulo: t('Nenhuma ligação ainda'), acao: Q.perguntar()}); return; }
    const visual_ = comSugestoes(mapa, S.abertas);
    const nomes = Object.fromEntries(visual_.entidades.map(e => [e.id, e.nome]));
    const saida = element('section', undefined, 'mapa-detalhe'); saida.tabIndex = -1; saida.setAttribute('aria-live', 'polite');
    saida.append(element('p', t('Escolha uma ligação para ver as evidências.'), 'small'));
    // Nomes das pontas de uma sugestão de ligação: o item confirmado ou a outra sugestão, nunca um id.
    for (const sug of S.abertas) if (sug.tipo === 'ligacao') for (const ponta of ['origem', 'destino']) if (sug.pontas?.[ponta]) sug.pontas[ponta].nome ||= nomes[sug.campos[ponta]] || '';
    const reais = () => ({entidades: mapa.entidades.map(e => ({id: e.id, nome: e.nome}))});
    const ctx = Q.sugestoes ? Q.sugestoes.contexto(casoId, 'mapa', Q.formularios ? {corrigir: sug => Q.formularios.abrirNoPainel({tipo: sug.tipo === 'ligacao' ? 'ligacao' : 'entidade', abaId: 'mapa', casoId, sugestao: sug, ...reais()})} : {}) : null;
    const abrirSugestao = (sug, origem) => painel.__lateral.abrir([Q.sugestoes.painel(sug, ctx)], {origem});
    const layout = element('div', undefined, 'mapa-layout');
    const visual = element('div', undefined, 'mapa-visual');
    // O desenho só existe de 1024 px para cima (abaixo, o mapa se lê como a lista): não se calcula a disposição com ele oculto, e ele se monta
    // se a janela passar a ser larga.
    const consulta = window.matchMedia?.('(min-width:1024px)');
    const desenhar = () => { if (visual.dataset.pronto) return; visual.dataset.pronto = 'sim'; visual.append(diagrama(casoId, visual_, nomes, saida, abrirSugestao), legenda(visual_)); };
    if (!consulta || consulta.matches) desenhar();
    else consulta.addEventListener?.('change', evento => { if (evento.matches) desenhar(); });
    const lado = element('div', undefined, 'mapa-lateral');
    lado.append(element('h4', t('Lista de pessoas e organizações')), listaMapa(casoId, mapa, nomes, saida));
    const secao = Q.sugestoes?.secao(S.abertas, abrirSugestao, 'mapa-sugestoes');
    if (secao) lado.append(secao);
    lado.append(homonimos(mapa));
    layout.append(visual, lado);
    const conta = element('p', undefined, 'small quadro-conta');
    const np = mapa.entidades.length, nr = mapa.relacoes.length;
    conta.append(`${t(np === 1 ? '{n} pessoa ou organização' : '{n} pessoas e organizações', {n: np})} · ${t(nr === 1 ? '{n} ligação' : '{n} ligações', {n: nr})}`);
    if (S.abertas.length) conta.append(element('span', Q.sugestoes.contagemTexto(S.abertas.length), 'quadro-conta-sugestoes'));
    const novos = ['entidade', 'ligacao'].map(tp => Q.formularios?.botaoNovo(tp, 'mapa', casoId, reais)).filter(Boolean);
    const corpo = [...(novos.length ? [element('div', undefined, 'quadro-acoes')] : []), element('p', t(mapa.aviso || ''), 'small quadro-aviso'), conta, layout, saida];
    if (novos.length) corpo[0].append(...novos);
    const descartadas = Q.sugestoes?.descartadas(S.descartadas, ctx);
    if (descartadas) corpo.push(descartadas);
    Q.montarQuadro(painel, corpo);
  })});
})();
