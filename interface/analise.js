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
  Q.registrarAba({id: 'comparador', rotulo: t('Comparador'), carregar: Q.quadro('quadros_evidencia', async (painel, casoId, vigente) => {
    const inventario = await api('inventario', {caso: casoId});
    if (!vigente()) return;
    const rodadas = (typeof cases !== 'undefined' ? cases : []).find(c => c.id === casoId)?.rodadas || [];
    if (!rodadas.length) { Q.estado(painel, 'vazio', t('Esta apuração ainda não tem análise com documentos preservados para comparar.')); return; }
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
    painel.replaceChildren(element('p', t('Compara o texto extraído de dois documentos da mesma análise. As diferenças aparecem com o contexto de cada lado; confira valores e tabelas no original.'), 'small'), form, saida);
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
  function detalheCelula(saida, linha, coluna, celula) {
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
  }
  function grade(tabela, saida) {
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
        const mostrar = () => detalheCelula(saida, linha.id, coluna, cel);
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
    if (!lista.tabelas.length) { Q.estado(painel, 'vazio', t('Nenhuma tabela de apuração nesta apuração.')); return; }
    const escolha = element('select'); escolha.id = 'tabelas-escolha';
    escolha.replaceChildren(...lista.tabelas.map(tb => { const o = new Option(`${tb.titulo} · ${t('{n} linhas', {n: tb.total_linhas})}`, tb.id); o.setAttribute('translate', 'no'); return o; }));
    const area = element('div', undefined, 'tabela-area');
    async function abrir() {
      Q.estado(area, 'carregando', t('Carregando…'));
      try {
        const tabela = await api('tabelas-detalhe', {caso: casoId, id: escolha.value});
        const fonte = element('aside', undefined, 'tabela-fonte'); fonte.setAttribute('aria-live', 'polite'); fonte.id = 'tabela-fonte';
        fonte.append(element('p', t('Leve o foco a uma célula para ver a fonte, o estado e a última correção.'), 'small'));
        const {wrap, celulas} = grade(tabela, fonte);
        const n = tabela.celulas_por_estado || {};
        const contar = (q, um, varios) => t(q === 1 ? um : varios, {n: q});
        area.replaceChildren(element('p', [contar(n.extraido || 0, '{n} com fonte', '{n} com fonte'), contar(n.corrigido_manual || 0, '{n} corrigida', '{n} corrigidas'),
          contar(n.pendente || 0, '{n} pendente', '{n} pendentes')].join(' · '), 'small'),
          element('p', t('Use as setas para andar pelas células.'), 'small'), element('div', undefined, 'tabela-layout'));
        area.lastChild.append(wrap, fonte);
        area.append(painelCalculo(tabela, celulas), element('p', t(tabela.aviso || ''), 'small quadro-aviso'));
      } catch (erro) { Q.estado(area, 'erro', erro.message); }
    }
    escolha.addEventListener('change', abrir);
    painel.replaceChildren(campo(t('Tabela'), escolha), area);
    await abrir();
  })});

  // ---------- Relationship map: SVG drawing plus the same links as a list ----------
  const SIT_RELACAO = {documentada: 'Documentada', inferida: 'Inferida', suporte_parcial: 'Suporte parcial', suporte_nao_revisado: 'Suporte não revisado',
    sem_suporte_sustentado: 'Sem suporte sustentado', fonte_indisponivel: 'Fonte indisponível'};
  const MOTIVO_HOM = {nome_igual: 'Nome igual', mesmas_palavras: 'Mesmas palavras em outra ordem', nome_contido: 'Um nome contido no outro',
    grafia_parecida: 'Grafia parecida', identificador_igual: 'Identificador igual'};
  const SIT_HOM = {pendente: 'Conferência pendente', mesma_entidade: 'Decidido: mesma entidade (as duas continuam no mapa)', entidade_distinta: 'Decidido: entidades distintas',
    indeterminado: 'Indeterminado', decisoes_divergentes: 'Decisões divergentes'};
  const traco = sit => sit === 'documentada' ? 'solido' : sit === 'inferida' ? 'tracejado' : 'pontilhado';
  function detalheRelacao(casoId, saida, r, nomes) {
    saida.replaceChildren(dado('h4', `${nomes[r.origem]} — ${r.tipo} — ${nomes[r.destino]}`),
      element('p', t('Situação: {s}', {s: t(SIT_RELACAO[r.situacao] || r.situacao)}), 'small'));
    if (r.descricao) saida.append(dado('p', r.descricao, 'small'));
    const lista = element('ul', undefined, 'quadro-lista');
    for (const v of r.evidencias || []) lista.append(Q.evidencia(casoId, v));
    saida.append(lista);
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
  function diagrama(casoId, mapa, nomes, saida) {
    const n = mapa.entidades.length, L = 640, A = 520, LARG = 184, ALT = 68, cx = L / 2, cy = A / 2;
    const rx = Math.max(0, cx - LARG / 2 - 10), ry = Math.max(0, cy - ALT / 2 - 30);
    // A entidade mais ligada vai ao centro e as demais ao redor, para as ligações saírem dela como raios e os rótulos não caírem sobre os nós.
    const grau = {}; for (const r of mapa.relacoes) { grau[r.origem] = (grau[r.origem] || 0) + 1; grau[r.destino] = (grau[r.destino] || 0) + 1; }
    const centro = n >= 3 ? [...mapa.entidades].sort((a, b) => (grau[b.id] || 0) - (grau[a.id] || 0))[0] : null;
    const anel = mapa.entidades.filter(e => e !== centro);
    const pos = Object.fromEntries(mapa.entidades.map(e => {
      if (e === centro || n === 1) return [e.id, [cx, cy]];
      const i = anel.indexOf(e), ang = -Math.PI / 2 + (2 * Math.PI * i) / Math.max(anel.length, 1);
      return [e.id, [Math.round(cx + rx * Math.cos(ang)), Math.round(cy + ry * Math.sin(ang))]];
    }));
    const desenho = svg('svg', {viewBox: `0 0 ${L} ${A}`, class: 'mapa-svg', role: 'group', 'aria-label': t('Diagrama do mapa. A lista ao lado traz as mesmas ligações.')});
    const rotulos = [];
    for (const r of mapa.relacoes) {
      const [x1, y1] = pos[r.origem] || [cx, cy], [x2, y2] = pos[r.destino] || [cx, cy];
      const g = svg('g', {class: `mapa-ligacao traco-${traco(r.situacao)}`, tabindex: '0', role: 'button', 'aria-pressed': 'false',
        'aria-label': `${nomes[r.origem]} — ${r.tipo} — ${nomes[r.destino]}: ${t(SIT_RELACAO[r.situacao] || r.situacao)}`});
      g.dataset.relacao = r.id;
      g.append(svg('line', {x1, y1, x2, y2, class: 'mapa-linha'}), svg('line', {x1, y1, x2, y2, class: 'mapa-alvo'}));
      // Rótulo da ligação: pílula com o ícone do tipo e o texto do tipo, no meio da linha; segue a ligação (ativa, foco).
      const texto = cortar(r.tipo, 20), largura = Math.round(34 + texto.length * 7.4);
      // Ligação que sai da entidade central: o rótulo fica a 62% do caminho, longe do nó do centro; as demais, no meio.
      const doCentro = centro && r.origem === centro.id ? 1 : centro && r.destino === centro.id ? 2 : 0, f = doCentro ? 0.62 : 0.5;
      const [bx, by, ex, ey] = doCentro === 2 ? [x2, y2, x1, y1] : [x1, y1, x2, y2], mx = Math.round(bx + (ex - bx) * f), my = Math.round(by + (ey - by) * f);
      const pilula = svg('g', {class: `mapa-pilula traco-${traco(r.situacao)}`, transform: `translate(${mx - largura / 2} ${my - 14})`, 'aria-hidden': 'true'});
      pilula.append(svg('rect', {width: largura, height: 28, rx: 14, class: 'mapa-pilula-fundo'}), icone(iconeRelacao(r.tipo), 16, 14, 14, 'mapa-pilula-icone'));
      const rotuloTexto = svg('text', {x: 28, y: 19, class: 'mapa-pilula-texto', translate: 'no'}); rotuloTexto.textContent = texto; pilula.append(rotuloTexto);
      const abrir = () => {
        for (const outro of desenho.querySelectorAll('.mapa-ligacao')) { outro.classList.remove('is-ativa'); outro.setAttribute('aria-pressed', 'false'); }
        for (const outra of desenho.querySelectorAll('.mapa-pilula')) outra.classList.remove('is-ativa');
        g.classList.add('is-ativa'); pilula.classList.add('is-ativa'); g.setAttribute('aria-pressed', 'true'); detalheRelacao(casoId, saida, r, nomes);
      };
      pilula.addEventListener('click', abrir);
      // Focus only highlights the line (CSS); the live detail panel changes on Enter, Space or click.
      g.addEventListener('click', abrir);
      g.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); abrir(); } });
      desenho.append(g); rotulos.push(pilula);
    }
    // Nós por cima das linhas e abaixo dos rótulos: caixa em HTML (o texto quebra e corta com reticências), ícone do tipo na forma do tipo.
    for (const e of mapa.entidades) {
      const [x, y] = pos[e.id], g = svg('g', {class: `mapa-no ${e.tipo}`});
      const fo = svg('foreignObject', {x: x - LARG / 2, y: y - ALT / 2, width: LARG, height: ALT});
      const cartao = element('div', undefined, 'mapa-cartao');
      const forma = element('span', undefined, 'mapa-ico'); forma.setAttribute('aria-hidden', 'true'); forma.append(Q.icone(iconeNo(e), 'mapa-ico-svg'));
      const textos = element('span', undefined, 'mapa-cartao-texto');
      textos.append(dado('b', e.nome, 'mapa-nome'), element('span', e.tipo === 'organizacao' ? t('Organização') : t('Pessoa'), 'mapa-sub'));
      cartao.append(forma, textos); fo.append(cartao); g.append(fo, svg('title'));
      g.lastChild.textContent = e.nome;
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
      li.append(sub); lista.append(li);
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
  function legenda() {
    const l = element('ul', undefined, 'mapa-legenda');
    l.setAttribute('aria-label', t('Legenda'));
    for (const [classe, texto] of [['pessoa', 'Pessoa (círculo)'], ['organizacao', 'Organização (quadrado)'], ['traco-solido', 'Ligação documentada (linha contínua)'],
      ['traco-tracejado', 'Ligação inferida (linha tracejada)'], ['traco-pontilhado', 'Suporte parcial, não revisado ou indisponível (pontilhada)']]) {
      l.append(element('li', t(texto), `legenda-${classe}`));
    }
    return l;
  }
  Q.registrarAba({id: 'mapa', rotulo: t('Mapa de relações'), carregar: Q.quadro('quadros_evidencia', async (painel, casoId, vigente) => {
    const mapa = await api('mapa-ver', {caso: casoId});
    if (!vigente()) return;
    if (!mapa.entidades.length) { Q.estado(painel, 'vazio', t('Nenhuma pessoa ou organização registrada nesta apuração.')); return; }
    const nomes = Object.fromEntries(mapa.entidades.map(e => [e.id, e.nome]));
    const saida = element('section', undefined, 'mapa-detalhe'); saida.tabIndex = -1; saida.setAttribute('aria-live', 'polite');
    saida.append(element('p', t('Escolha uma ligação para ver as evidências.'), 'small'));
    const layout = element('div', undefined, 'mapa-layout');
    const visual = element('div', undefined, 'mapa-visual');
    visual.append(legenda(), diagrama(casoId, mapa, nomes, saida));
    const lado = element('div', undefined, 'mapa-lateral');
    lado.append(element('h4', t('Lista de pessoas e organizações')), listaMapa(casoId, mapa, nomes, saida), homonimos(mapa));
    layout.append(visual, lado);
    painel.replaceChildren(element('p', t(mapa.aviso || ''), 'small quadro-aviso'), layout, saida);
  })});
})();
