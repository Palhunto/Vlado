'use strict';
// Formulários de criar e editar dos quadros (componentes.md#formularios-quadros, P45 e P47): hipótese, acontecimento, entidade e ligação do mapa.
// Cada formulário vive num `host` (o painel do quadro, a camada de tela cheia no celular), monta os campos do servidor com os limites dele, mostra as
// regras do modelo antes do envio, liga evidências pelo seletor comum (quadros.js) e salva por `<quadro>-criar` ou `<quadro>-atualizar`; com `sugestao`,
// salva por `sugestoes-corrigir` (o item nasce com "alterado por pessoa" em cada campo mudado, que o servidor calcula).
// O vínculo mostra de onde veio o valor (a revisão da IA) e o que uma pessoa mudou; nada aqui afirma que o vínculo foi conferido no original.
window.Quadros.formularios = (() => {
  const Q = window.Quadros, {t, dado, botao, linkBotao} = Q;
  const PAPEIS = [['suporte', 'Suporte'], ['contradicao', 'Contradição'], ['contexto', 'Contexto']];
  const SUPORTES = [['nao_revisado', 'Não revisado'], ['sustentado', 'Sustentado'], ['parcial', 'Parcial'], ['nao_sustentado', 'Não sustentado'], ['ilegivel', 'Ilegível']];
  const NATUREZAS = [['declaracao_documental', 'Declaração documental'], ['alegacao_atribuida', 'Alegação atribuída'], ['inferencia', 'Inferência'], ['pendencia', 'Pendência']];
  const DOCUMENTAIS = ['declaracao_documental', 'alegacao_atribuida'];
  const SITUACOES = [['em_aberto', 'Em aberto'], ['sustentada', 'Sustentada'], ['contrariada', 'Contrariada'], ['inconclusiva', 'Inconclusiva'], ['descartada', 'Descartada']];
  const TIPOS_ID = [['cpf', 'CPF'], ['cnpj', 'CNPJ'], ['registro_profissional', 'Registro profissional'], ['matricula', 'Matrícula'], ['outro', 'Outro']];
  const MAX_VINCULOS = 100;
  const rotulo = (lista, chave) => (lista.find(([k]) => k === chave) || [])[1] || chave || '';
  let contador = 0; const novoId = prefixo => `${prefixo}-${++contador}`;
  const podeCriar = quadro => !window.Sessao?.pode || window.Sessao.pode(`${quadro}-criar`) || window.Sessao.pode(`${quadro}-atualizar`);
  const podeAtualizar = quadro => !window.Sessao?.pode || window.Sessao.pode(`${quadro}-atualizar`);
  const requisicao = () => Q.sugestoes.requisicao();
  const diaHora = iso => { const d = new Date(iso); return Number.isNaN(d.getTime()) ? '' : t('{dia}, às {hora}', {dia: `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')}`, hora: `${d.getHours()}h${String(d.getMinutes()).padStart(2, '0')}`}); };

  // ---------- Campos ----------
  // Rótulo acima, controle, apoio e erro no campo (role=alert). O contador só aparece nos últimos 10% do limite.
  function campo(rotuloTexto, controle, {ajuda = '', maximo = 0} = {}) {
    const caixa = element('div', undefined, 'form-campo');
    const etiqueta = element('label', t(rotuloTexto), 'form-rotulo'); controle.id ||= novoId('campo'); etiqueta.setAttribute('for', controle.id);
    const erro = element('p', undefined, 'form-erro'); erro.setAttribute('role', 'alert'); erro.hidden = true; erro.id = novoId('erro');
    const apoio = element('p', ajuda ? t(ajuda) : '', 'small form-ajuda'); apoio.id = novoId('ajuda');
    controle.setAttribute('aria-describedby', `${apoio.id} ${erro.id}`);
    caixa.append(etiqueta, controle, apoio);
    if (maximo) {
      const conta = element('p', undefined, 'small form-contador'); conta.hidden = true;
      const atualizar = () => { const n = controle.value.length; conta.hidden = n < maximo * 0.9; conta.textContent = t('{n} de {max}', {n: n.toLocaleString('pt-BR'), max: maximo.toLocaleString('pt-BR')}); };
      controle.addEventListener('input', atualizar); atualizar(); caixa.append(conta);
    }
    caixa.append(erro);
    caixa.erro = mensagem => { erro.textContent = mensagem ? t(mensagem) : ''; erro.hidden = !mensagem; if (mensagem) controle.setAttribute('aria-invalid', 'true'); else controle.removeAttribute('aria-invalid'); };
    caixa.ajuda = texto => { apoio.textContent = texto ? t(texto) : ''; };
    caixa.controle = controle;
    return caixa;
  }
  const texto1 = (valor, aoMudar, maximo = 0) => { const i = element('input'); i.type = 'text'; i.value = valor || ''; if (maximo) i.maxLength = maximo + 50; i.addEventListener('input', () => aoMudar(i.value)); return i; };
  const area = (valor, aoMudar, linhas = 3) => { const a = element('textarea'); a.rows = linhas; a.value = valor || ''; a.addEventListener('input', () => aoMudar(a.value)); return a; };
  function selecao(opcoes, valor, aoMudar, vazio = '') {
    const s = element('select');
    if (vazio) { const o = element('option', t(vazio)); o.value = ''; s.append(o); }
    for (const [chave, texto] of opcoes) { const o = element('option', t(texto)); o.value = chave; s.append(o); }
    s.value = valor ?? ''; s.addEventListener('change', () => aoMudar(s.value)); return s;
  }
  // Seletor segmentado (aria-pressed), como o do caderno.
  function segmentado(rotuloGrupo, opcoes, valor, aoMudar, desabilitado = false) {
    const grupo = element('div', undefined, 'form-segmentado'); grupo.setAttribute('role', 'group'); grupo.setAttribute('aria-label', t(rotuloGrupo));
    const botoes = opcoes.map(([chave, texto]) => {
      const b = botao(t(texto), 'form-segmento'); b.dataset.valor = chave; b.setAttribute('aria-pressed', String(chave === valor)); b.disabled = desabilitado;
      b.addEventListener('click', () => { for (const o of botoes) o.setAttribute('aria-pressed', String(o === b)); aoMudar(chave); }); grupo.append(b); return b;
    });
    return grupo;
  }
  // Lista de textos (variantes, "O que falta"): cada item um campo, com "+ rótulo" e remover.
  function listaTextos(titulo, itens, {maximo, maximoItem, adicionar, rotuloItem, aoMudar}) {
    const raiz = element('div', undefined, 'form-lista');
    const desenhar = () => {
      raiz.replaceChildren();
      if (titulo) raiz.append(element('p', t(titulo), 'form-rotulo'));
      itens.forEach((item, i) => {
        const linha = element('div', undefined, 'form-linha');
        const c = campo(rotuloItem, texto1(item.valor, v => { item.valor = v; aoMudar(); }), {maximo: maximoItem});
        const remover = linkBotao(t('Remover'), 'form-remover'); remover.setAttribute('aria-label', `${t('Remover')}: ${item.valor || t(rotuloItem)}`);
        remover.addEventListener('click', () => { itens.splice(i, 1); aoMudar(); desenhar(); raiz.querySelector('.form-mais')?.focus(); });
        linha.append(c, remover); raiz.append(linha);
      });
      const mais = linkBotao(`+ ${t(adicionar)}`, 'form-mais'); mais.disabled = itens.length >= maximo;
      mais.addEventListener('click', () => { itens.push({valor: ''}); aoMudar(); desenhar(); const ult = raiz.querySelectorAll('input'); ult[ult.length - 1]?.focus(); });
      raiz.append(mais);
    };
    desenhar();
    return raiz;
  }

  // ---------- Vínculos ----------
  // Forma comum do vínculo no formulário: o que se envia (referencia, achado_id, papel, suporte, natureza, justificativa) e o que só se mostra (vista).
  function vinculoDeItem(item) {
    const ev = item.evidencia, loc = ev?.localizador || item.localizador || {}, ia = item.revisao_ia || null;
    return {referencia: item.referencia, achado_id: item.achado_id || ia?.achado_id || null, papel: item.papel, suporte: item.suporte, natureza: item.natureza, justificativa: item.justificativa || '',
      inicial: {papel: item.papel, suporte: item.suporte, natureza: item.natureza},
      vista: {indisponivel: item.estado === 'indisponivel' || !ev, erro: item.erro, nome: ev?.documento?.nome || item.documento_id || '', legivel: loc.legivel || '', trecho: ev?.trecho || '',
        origem: item.referencia?.tipo === 'ia' ? 'ia' : 'caderno', ia, preenchimentoIA: item.preenchimento_ia || null, alteracoes: item.alteracoes || {}, conferencia: item.conferencia_humana || null, versaoNova: item.versao_nova || null,
        destinoAtual: item.destino_atual || ia?.destino || null, original: {referencia: item.referencia, evidencia: ev, localizador: loc}}};
  }
  function vinculoDeResultado(r) {
    const b = r.bruto || {}, sug = r.preenchimento || {}, ia = b.revisao_ia || null;
    return {referencia: sug.referencia, achado_id: sug.achado_id || b.achado?.id || null, papel: sug.papel || 'suporte', suporte: sug.suporte || 'nao_revisado', natureza: sug.natureza || '', justificativa: sug.justificativa || '',
      inicial: {papel: sug.papel || 'suporte', suporte: sug.suporte || 'nao_revisado', natureza: sug.natureza || ''},
      vista: {indisponivel: r.indisponivel, erro: '', nome: b.documento?.nome || '', legivel: b.localizador?.legivel || '', trecho: b.trecho || b.texto || '', origem: b.origem, ia, alteracoes: {},
        preenchimentoIA: b.origem === 'ia' && ia ? {papel: sug.papel, suporte: sug.suporte, natureza: sug.natureza, destino: ia.destino || b.achado?.destino || null} : null,
        conferencia: b.conferencia_humana || null, versaoNova: null, destinoAtual: b.achado?.destino || ia?.destino || null,
        original: {referencia: sug.referencia, evidencia: {documento: b.documento, trecho: b.trecho, localizador: b.localizador}, localizador: b.localizador}}};
  }
  function vinculoDeSugestao(sug, i) {
    const salvo = sug.campos?.evidencias?.[i] || {}, ev = sug.evidencias?.[i] || {};
    return vinculoDeItem({...salvo, preenchimento_ia: ev.revisao_ia ? {papel: salvo.papel, suporte: salvo.suporte, natureza: salvo.natureza, destino: sug.achado?.destino || null} : null, estado: ev.estado, erro: ev.erro, evidencia: ev.estado === 'indisponivel' ? null : {documento: ev.documento, trecho: ev.trecho, localizador: ev.localizador}, localizador: ev.localizador,
      revisao_ia: ev.revisao_ia ? {...ev.revisao_ia, achado_id: sug.achado?.id} : null, conferencia_humana: ev.conferencia_humana, destino_atual: sug.achado?.destino});
  }
  const camposDoVinculo = v => ({referencia: v.referencia, ...(v.achado_id ? {achado_id: v.achado_id} : {}), papel: v.papel, suporte: v.suporte, natureza: v.natureza, justificativa: v.justificativa});

  // O campo foi mudado por uma pessoa? Salvo (alteracoes, do servidor) ou nesta edição (valor diferente do preenchimento).
  function marca(v, campoNome) {
    const salva = v.vista.alteracoes?.[campoNome];
    if (v.inicial[campoNome] !== undefined && (v[campoNome] || '') !== (v.inicial[campoNome] || '')) return {por: t('você'), salva: false};
    return salva ? {por: salva.por, salva: true, anterior: salva.anterior, quando: salva.em_utc} : null;
  }
  const algumaMarca = v => ['papel', 'suporte', 'natureza'].some(c => marca(v, c));
  const comRevisaoHumana = v => Object.keys(v.vista.alteracoes || {}).length > 0 || (v.vista.origem === 'caderno' && v.suporte !== 'nao_revisado');

  // Apagar revisão humana (componentes.md#apagar-revisao): o diálogo destrutivo diz o que muda; o foco inicial fica em Cancelar.
  async function confirmarApagar(v, {versaoNova = false} = {}) {
    const alt = Object.entries(v.vista.alteracoes || {})[0];
    const por = alt?.[1]?.por || t('uma pessoa');
    const quando = alt ? diaHora(alt[1].em_utc) : '';
    const nomeCampo = {papel: 'o papel', suporte: 'o suporte', natureza: 'a natureza'};
    let texto;
    if (v.vista.origem === 'caderno') texto = t('{por} escolheu o suporte “{valor}” em {quando}. Desligar apaga essa escolha; o trecho continua no caderno.', {por, valor: t(rotulo(SUPORTES, v.suporte)).toLowerCase(), quando});
    else if (versaoNova) texto = t('O vínculo passa à versão nova do achado e volta ao que a revisão dela disse: papel, suporte e natureza. A mudança de {por} (“{valor}”, em {quando}) deixa de valer.', {por, valor: t(rotulo(SUPORTES, alt?.[1]?.valor || v.suporte)).toLowerCase(), quando});
    else texto = t('{por} mudou {campo} de “{de}” (da revisão da IA) para “{para}” em {quando}. O vínculo volta ao que a revisão da IA disse.',
      {por, campo: t(nomeCampo[alt?.[0]] || 'o valor'), de: t(rotulo(SUPORTES.concat(NATUREZAS, PAPEIS), v.vista.preenchimentoIA?.[alt?.[0]])).toLowerCase(), para: t(rotulo(SUPORTES.concat(NATUREZAS, PAPEIS), alt?.[1]?.valor)).toLowerCase(), quando});
    const propria = por === t('você'), acao = versaoNova ? 'Ligar a versão nova' : v.vista.origem === 'caderno' ? 'Desligar' : 'Apagar a revisão';
    return window.Dialogo.confirmar({variante: 'destrutivo', rubrica: t('Apagar revisão'), titulo: propria ? t('Apagar a sua revisão?') : t('Apagar a revisão de {por}?', {por}), texto, acao: t(acao), cancelar: t('Cancelar')});
  }

  // Cartão do vínculo (componentes.md#cartao-vinculo).
  function cartaoVinculo(v, ctx) {
    const raiz = element('li', undefined, 'vinculo-cartao'); raiz.dataset.origem = v.vista.origem;
    const cabeca = element('div', undefined, 'vinculo-cabeca');
    cabeca.append(element('span', t(v.vista.origem === 'ia' ? 'Achado da IA' : 'Trecho do caderno'), 'vinculo-tipo'));
    if (algumaMarca(v)) { const m = ['papel', 'suporte', 'natureza'].map(c => marca(v, c)).find(Boolean); cabeca.append(sinalAlterado(m.por === t('você') ? t('Alterado por você') : t('Alterado por pessoa'))); }
    raiz.append(cabeca);
    // Avisos do vínculo: em linha, nunca nas cores de erro.
    const aviso = texto => { const p = element('p', undefined, 'notice vinculo-aviso'); p.setAttribute('role', 'status'); p.append(typeof texto === 'string' ? element('span', texto) : texto); return p; };
    if (v.vista.avisoTroca) raiz.append(aviso(v.vista.avisoTroca));
    if (v.vista.indisponivel) raiz.append(aviso(t('A evidência não está mais disponível. O vínculo fica no registro, mas não abre o original.')));
    else if (v.vista.origem === 'ia' && !v.vista.ia) raiz.append(aviso(t('Esta análise não passou pela revisão de suporte. O vínculo começa em “não revisado”.')));
    if (v.vista.destinoAtual === 'retirado' && v.vista.origem === 'ia') raiz.append(aviso(t('A revisão da IA retirou este achado. Ele pode continuar ligado, com o suporte em “não revisado”: só sustenta o item se uma pessoa escolher.')));
    if (v.vista.versaoNova?.preenchimento) {
      const p = aviso(t('Há uma versão mais nova deste achado.')); const ligar = linkBotao(t('Ligar a versão nova'), 'vinculo-versao-nova');
      ligar.addEventListener('click', async () => {
        if (comRevisaoHumana(v) && !await confirmarApagar(v, {versaoNova: true})) return;
        // R2 da Coruja: as mudanças desta edição ainda não salvas (papel, suporte, natureza) são trocadas pelo que a revisão da versão nova disse; a tela avisa.
        const vivas = ['papel', 'suporte', 'natureza'].filter(c => { const m = marca(v, c); return m && !m.salva; }).map(c => t({papel: 'papel', suporte: 'suporte', natureza: 'natureza'}[c]));
        v.vista.avisoTroca = vivas.length ? t('Ligar a versão nova trocou as mudanças desta edição ainda não salvas ({campos}) pelo que a revisão da nova versão disse.', {campos: vivas.join(', ')}) : '';
        const n = v.vista.versaoNova, p = n.preenchimento;
        v.referencia = n.referencia; v.achado_id = n.achado_id || v.achado_id; v.papel = p.papel; v.suporte = p.suporte; v.natureza = p.natureza;
        v.inicial = {papel: v.papel, suporte: v.suporte, natureza: v.natureza}; v.vista.alteracoes = {}; v.vista.versaoNova = null; v.vista.ia = n.revisao_ia || null;
        v.vista.preenchimentoIA = p; v.vista.destinoAtual = p.destino || v.vista.destinoAtual; ctx.mudou(); ctx.redesenhar();
      });
      p.append(' ', ligar); raiz.append(p);
    }
    if (!v.vista.indisponivel) {
      const cit = dado('blockquote', v.vista.trecho || t('Fonte visual: consulte o original.'), 'vinculo-citacao');
      raiz.append(cit);
      if ((v.vista.trecho || '').length > 220) { cit.classList.add('is-curta'); const mostrar = linkBotao(t('Mostrar tudo'), 'vinculo-mostrar'); mostrar.addEventListener('click', () => { cit.classList.toggle('is-curta'); mostrar.textContent = t(cit.classList.contains('is-curta') ? 'Mostrar tudo' : 'Mostrar menos'); }); raiz.append(mostrar); }
      const linha = element('p', undefined, 'small vinculo-localizador'); const abrir = linkBotao(t('abrir o original'), 'vinculo-abrir'), retorno = element('p', '', 'small'); retorno.setAttribute('role', 'status');
      abrir.setAttribute('aria-label', `${t('Abrir o original')}: ${v.vista.nome} · ${v.vista.legivel}`.trim());
      abrir.addEventListener('click', () => Q.abrirOriginal(ctx.casoId, v.vista.original, abrir, retorno));
      linha.append(dado('span', `${v.vista.nome ? v.vista.nome + ', ' : ''}${v.vista.legivel} · `), abrir); raiz.append(linha, retorno);
    }
    // Papel, suporte, natureza e justificativa, com as regras do modelo antes do envio.
    const papel = segmentado('Papel', PAPEIS, v.papel, valor => { v.papel = valor; if (valor === 'contexto') v.suporte = 'nao_revisado'; ctx.mudou(); ctx.redesenhar(); });
    const suporteSel = selecao(SUPORTES.filter(([k]) => !(v.natureza === 'pendencia' && k === 'sustentado')), v.suporte, valor => { v.suporte = valor; ctx.mudou(); ctx.redesenhar(); });
    const natSel = selecao(NATUREZAS, v.natureza, valor => { v.natureza = valor; if (valor === 'pendencia' && v.suporte === 'sustentado') v.suporte = 'nao_revisado'; ctx.mudou(); ctx.redesenhar(); }, v.natureza ? '' : 'Escolha a natureza');
    const campoPapel = element('div', undefined, 'form-campo'); campoPapel.append(element('p', t('Papel'), 'form-rotulo'), papel);
    const campoSup = campo('Suporte', suporteSel), campoNat = campo('Natureza', natSel);
    if (v.papel === 'contexto') { suporteSel.disabled = true; campoSup.ajuda('Evidência de contexto não recebe suporte.'); }
    else if (v.natureza === 'pendencia') campoSup.ajuda('Uma pendência nunca é sustentada.');
    for (const [nome, caixa, rot] of [['papel', campoPapel, 'Papel'], ['suporte', campoSup, 'Suporte'], ['natureza', campoNat, 'Natureza']]) {
      const m = marca(v, nome); if (!m) continue;
      const sinal = sinalAlterado(m.por === t('você') ? t('alterado por você') : t('alterado por {por}', {por: m.por}));
      const alvoIA = v.vista.preenchimentoIA?.[nome];
      caixa.append(sinal);
      if (v.vista.origem === 'ia' && alvoIA) {
        const voltar = linkBotao(t('Voltar ao da IA'), 'vinculo-voltar'); voltar.setAttribute('aria-label', `${t('Voltar ao da IA')}: ${t(rot).toLowerCase()}`);
        voltar.addEventListener('click', async () => {
          if (m.salva && !await confirmarApagar(v)) return;
          v[nome] = alvoIA; if (m.salva) delete v.vista.alteracoes[nome]; v.inicial[nome] = alvoIA;
          ctx.mudou(); ctx.redesenhar();
        });
        caixa.append(voltar);
      }
    }
    const just = campo('Justificativa', area(v.justificativa, valor => { v.justificativa = valor; if (valor.trim()) just.erro(''); ctx.mudou(); }, 2), {maximo: 2000});
    // o envio confere cada cartão e aponta o que falta (campo com erro e foco), em vez de deixar o servidor recusar sem dizer qual
    v.vista.campos = {justificativa: just, natureza: campoNat};
    raiz.append(campoPapel, campoSup, campoNat);
    if (v.vista.ia) {
      const linhaIA = element('p', undefined, 'small vinculo-ia'); linhaIA.append(t('Da revisão da IA:') + ' ', Q.seloIA(v.vista.ia.suporte), ' ', element('span', t(rotulo(NATUREZAS, v.vista.ia.natureza)).toLowerCase()));
      if (v.vista.ia.destino === 'retirado' || v.vista.destinoAtual === 'retirado') linhaIA.append(' · ', element('span', t('retirado')));
      raiz.append(linhaIA);
      if (v.vista.destinoAtual === 'fora_do_briefing') raiz.append(element('p', t('Fora do briefing (sustentado): a revisão sustentou o achado, mas ele não entrou no briefing.'), 'small vinculo-nota'));
    }
    raiz.append(just);
    const desligar = botao(t('Desligar'), 'vinculo-desligar'); desligar.setAttribute('aria-label', `${t('Desligar')}: ${v.vista.nome} · ${v.vista.legivel}`.trim());
    desligar.addEventListener('click', async () => {
      if (comRevisaoHumana(v) && !await confirmarApagar(v)) return;
      ctx.remover(v);
    });
    raiz.append(desligar);
    return raiz;
  }
  function sinalAlterado(texto) {
    const s = element('span', undefined, 'sinal-alterado'); s.append(Q.icone('sinal-corrigido', 'icone-vlado sinal-alterado-icone'), element('span', texto)); return s;
  }

  // Seção "Evidências": um cartão por evidência e "+ Ligar evidência" (abre o seletor no lugar do formulário).
  function secaoEvidencias(ctx) {
    const raiz = element('section', undefined, 'form-evidencias');
    const titulo = element('h4', t('Evidências'), 'form-rubrica'); raiz.append(titulo);
    const lista = element('ul', undefined, 'vinculo-lista');
    for (const v of ctx.estado.vinculos) lista.append(cartaoVinculo(v, {casoId: ctx.casoId, mudou: ctx.mudou, redesenhar: ctx.redesenhar, remover: ctx.removerVinculo}));
    raiz.append(lista);
    const cheio = ctx.estado.vinculos.length >= MAX_VINCULOS;
    const ligar = linkBotao('+ ' + t('Ligar evidência'), 'form-ligar'); ligar.disabled = cheio;
    ligar.addEventListener('click', () => ctx.abrirSeletor());
    raiz.append(ligar);
    if (cheio) { const razao = element('p', t('Este item já tem 100 evidências, o limite.'), 'small form-ajuda'); razao.id = novoId('razao'); ligar.setAttribute('aria-describedby', razao.id); raiz.append(razao); }
    return raiz;
  }

  // ---------- Os quatro formulários ----------
  // Cada um recebe `ctx` (estado, mudou, redesenhar, casoId, extras) e devolve {nos, coletar(), validar()}; `validar` marca o erro no campo e devolve a mensagem do primeiro.
  const temEvidencia = (vs, papel) => vs.some(v => v.papel === papel && v.suporte === 'sustentado' && DOCUMENTAIS.includes(v.natureza));

  function formHipotese(ctx) {
    const e = ctx.estado, nos = [];
    const enunciado = campo('Hipótese', area(e.enunciado, v => { e.enunciado = v; ctx.mudou(); }, 3), {maximo: 1000, ajuda: 'Escreva como afirmação que os documentos possam sustentar ou contrariar.'});
    const sit = element('fieldset', undefined, 'form-campo form-situacao'); sit.append(element('legend', t('Situação'), 'form-rotulo'));
    const razoes = {sustentada: t('Sustentada pede ao menos uma evidência de suporte sustentada e documental.'), contrariada: t('Contrariada pede ao menos uma evidência de contradição sustentada e documental.')};
    const pode = {sustentada: temEvidencia(e.vinculos, 'suporte'), contrariada: temEvidencia(e.vinculos, 'contradicao')};
    for (const [chave, texto] of SITUACOES) {
      const id = novoId('sit'), r = element('input'); r.type = 'radio'; r.name = 'situacao'; r.value = chave; r.id = id; r.checked = e.situacao === chave;
      const bloqueada = (chave === 'sustentada' || chave === 'contrariada') && !pode[chave] && e.situacao !== chave;
      r.disabled = bloqueada; r.addEventListener('change', () => { e.situacao = chave; ctx.mudou(); });
      const l = element('label', undefined, 'form-opcao'); l.setAttribute('for', id); l.append(r, element('span', t(texto)));
      if (bloqueada) { const razao = element('span', razoes[chave], 'small form-ajuda'); razao.id = novoId('razao'); r.setAttribute('aria-describedby', razao.id); l.append(razao); }
      sit.append(l);
    }
    const falta = listaTextos('O que falta', e.lacunas, {maximo: 50, maximoItem: 1000, adicionar: 'O que falta', rotuloItem: 'O que falta', aoMudar: ctx.mudou});
    nos.push(enunciado, sit, falta);
    return {nos, coletar: () => ({enunciado: e.enunciado.trim(), situacao: e.situacao, lacunas: e.lacunas.filter(l => l.valor.trim()).map(l => ({descricao: l.valor.trim(), diligencia_id: l.diligencia_id || null})), evidencias: e.vinculos.map(camposDoVinculo)}),
      validar: () => { enunciado.erro(e.enunciado.trim() ? '' : 'Escreva a hipótese.'); return e.enunciado.trim() ? '' : 'Escreva a hipótese.'; }};
  }

  function precisaoTexto(valor) { const v = String(valor || '').trim(); if (!/^\d{4}(-\d{2}(-\d{2})?)?$/.test(v)) return ''; return t('Precisão: {p}', {p: t({4: 'ano', 7: 'mês', 10: 'dia'}[v.length])}); }
  // "03/03/2025", "03/2025" ou "2025" viram o valor do servidor; o que já está em AAAA-MM-DD fica.
  function normalizaData(texto) {
    const v = String(texto || '').trim(), br = v.match(/^(\d{2})\/(\d{2})\/(\d{4})$/), mes = v.match(/^(\d{2})\/(\d{4})$/);
    return br ? `${br[3]}-${br[2]}-${br[1]}` : mes ? `${mes[2]}-${mes[1]}` : v;
  }
  const mostraData = valor => { const [a, m, d] = String(valor || '').split('-'); return d ? `${d}/${m}/${a}` : m ? `${m}/${a}` : a || ''; };
  function formAcontecimento(ctx) {
    const e = ctx.estado, tipos = Object.entries(ctx.tiposData || {});
    const descricao = campo('Acontecimento', area(e.descricao, v => { e.descricao = v; ctx.mudou(); }, 3), {maximo: 1000});
    const datas = element('div', undefined, 'form-datas'); datas.append(element('p', t('Datas'), 'form-rotulo'));
    const campos = [];
    e.datas.forEach((d, i) => {
      const bloco = element('div', undefined, 'form-data');
      const tipo = campo('Tipo de data', selecao(tipos, d.tipo, v => { d.tipo = v; ctx.mudou(); ctx.redesenhar(); }));
      const valor = campo('Data', texto1(d.texto, v => { d.texto = v; ctx.mudou(); precisao.ajuda(precisaoTexto(normalizaData(v))); }), {ajuda: 'Ano, mês e ano ou dia completo, como o documento traz: 2025, 03/2025 ou 03/03/2025'});
      const precisao = element('p', precisaoTexto(normalizaData(d.texto)), 'small form-precisao'); precisao.ajuda = x => { precisao.textContent = x; };
      const aprox = element('input'); aprox.type = 'checkbox'; aprox.checked = !!d.aproximada; aprox.id = novoId('aprox'); aprox.addEventListener('change', () => { d.aproximada = aprox.checked; ctx.mudou(); });
      const rotAprox = element('label', undefined, 'form-opcao'); rotAprox.setAttribute('for', aprox.id); rotAprox.append(aprox, element('span', t('Data aproximada')));
      const fontes = e.vinculos.map((v, k) => [String(k), `${v.vista.nome ? v.vista.nome + ', ' : ''}${v.vista.legivel}`]);
      const fonte = campo('Fonte da data', selecao(fontes, e.vinculos.includes(d.fonteVinculo) ? String(e.vinculos.indexOf(d.fonteVinculo)) : '', v => { d.fonteVinculo = e.vinculos[Number(v)]; ctx.mudou(); }, 'Escolha a evidência'));
      const obs = campo('Observação', texto1(d.observacao, v => { d.observacao = v; ctx.mudou(); }, 500), {maximo: 500});
      const remover = linkBotao(t('Remover'), 'form-remover'); remover.disabled = e.datas.length <= 1;
      remover.addEventListener('click', () => { e.datas.splice(i, 1); ctx.mudou(); ctx.redesenhar(); });
      bloco.append(tipo, valor, precisao, rotAprox, fonte, obs, remover); datas.append(bloco); campos.push({d, valor, fonte});
    });
    const mais = linkBotao('+ ' + t('Data'), 'form-mais'); mais.disabled = e.datas.length >= 10;
    mais.addEventListener('click', () => { e.datas.push({tipo: tipos[0]?.[0] || 'fato', texto: '', aproximada: false, fonteVinculo: e.vinculos[0] || null, observacao: ''}); ctx.mudou(); ctx.redesenhar(); });
    datas.append(mais);
    // Duas datas do mesmo tipo e diferentes não são erro: ficam as duas, com o aviso.
    const avisos = element('div', undefined, 'form-avisos');
    const porTipo = new Map();
    for (const d of e.datas) { const k = normalizaData(d.texto); if (k) porTipo.set(d.tipo, [...(porTipo.get(d.tipo) || []), k]); }
    for (const [tipo, lista] of porTipo) if (new Set(lista).size > 1) { const p = element('p', undefined, 'notice'); p.setAttribute('role', 'status'); p.textContent = t('Duas datas de {tipo} diferentes: {datas}. As duas ficam na linha do tempo; confira no original.', {tipo: t(ctx.tiposData?.[tipo] || tipo).toLowerCase(), datas: lista.map(mostraData).join(' e ')}); avisos.append(p); }
    const semSuporte = !e.vinculos.some(v => v.papel === 'suporte');
    return {nos: [descricao, datas, avisos], coletar: () => ({descricao: e.descricao.trim(),
      datas: e.datas.map(d => ({tipo: d.tipo, valor: normalizaData(d.texto), aproximada: !!d.aproximada, fonte: Math.max(0, e.vinculos.indexOf(d.fonteVinculo)), observacao: (d.observacao || '').trim()})), evidencias: e.vinculos.map(camposDoVinculo)}),
      validar: () => {
        const falhas = [];
        descricao.erro(e.descricao.trim() ? '' : 'Escreva o acontecimento.'); if (!e.descricao.trim()) falhas.push('Escreva o acontecimento.');
        if (semSuporte) falhas.push('Falta a evidência. Ligue ao menos um documento que registre o acontecimento.');
        for (const {d, valor, fonte} of campos) {
          const ok = /^\d{4}(-\d{2}(-\d{2})?)?$/.test(normalizaData(d.texto)); valor.erro(ok ? '' : 'Use ano, mês e ano ou dia completo: 2025, 03/2025 ou 03/03/2025.'); if (!ok) falhas.push('Data inválida.');
          const fOk = e.vinculos.includes(d.fonteVinculo); fonte.erro(fOk ? '' : 'Escolha a evidência que documenta esta data.'); if (!fOk) falhas.push('Falta a fonte da data.');
        }
        return falhas[0] || '';
      }};
  }

  function formEntidade(ctx) {
    const e = ctx.estado;
    const nome = campo('Nome', texto1(e.nome, v => { e.nome = v; ctx.mudou(); }, 300), {maximo: 300});
    const tipoCampo = element('div', undefined, 'form-campo'); tipoCampo.append(element('p', t('Tipo'), 'form-rotulo'), segmentado('Tipo', [['pessoa', 'Pessoa'], ['organizacao', 'Organização']], e.tipo, v => { e.tipo = v; ctx.mudou(); }, !!ctx.edicao));
    if (ctx.edicao) tipoCampo.append(element('p', t('O tipo da entidade não muda; registre uma nova entidade.'), 'small form-ajuda'));
    const variantes = listaTextos('Variantes de nome', e.variantes, {maximo: 20, maximoItem: 300, adicionar: 'Variante', rotuloItem: 'Variante de nome', aoMudar: ctx.mudou});
    const ids = element('div', undefined, 'form-identificadores'); ids.append(element('p', t('Identificadores'), 'form-rotulo'));
    const camposId = [];
    e.identificadores.forEach((id, i) => {
      const bloco = element('div', undefined, 'form-identificador');
      const tipo = campo('Tipo de identificador', selecao(TIPOS_ID, id.tipo, v => { id.tipo = v; ctx.mudou(); }));
      const valor = campo('Valor', texto1(id.valor, v => { id.valor = v; ctx.mudou(); }, 100), {maximo: 100});
      const fontes = e.vinculos.map((v, k) => [String(k), `${v.vista.nome ? v.vista.nome + ', ' : ''}${v.vista.legivel}`]);
      const fonte = campo('Fonte', selecao(fontes, e.vinculos.includes(id.fonteVinculo) ? String(e.vinculos.indexOf(id.fonteVinculo)) : '', v => { id.fonteVinculo = e.vinculos[Number(v)]; ctx.mudou(); }, 'Escolha a evidência'));
      const remover = linkBotao(t('Remover'), 'form-remover'); remover.addEventListener('click', () => { e.identificadores.splice(i, 1); ctx.mudou(); ctx.redesenhar(); });
      bloco.append(tipo, valor, fonte, remover); ids.append(bloco); camposId.push({id, valor, fonte});
    });
    const mais = linkBotao('+ ' + t('Identificador'), 'form-mais'); mais.disabled = e.identificadores.length >= 20;
    mais.addEventListener('click', () => { e.identificadores.push({tipo: 'cpf', valor: '', fonteVinculo: e.vinculos[0] || null}); ctx.mudou(); ctx.redesenhar(); }); ids.append(mais);
    return {nos: [nome, tipoCampo, variantes, ids], coletar: () => ({tipo: e.tipo, nome: e.nome.trim(), variantes: e.variantes.map(v => v.valor.trim()).filter(Boolean),
      identificadores: e.identificadores.map(i => ({tipo: i.tipo, valor: i.valor.trim(), fonte: Math.max(0, e.vinculos.indexOf(i.fonteVinculo))})), evidencias: e.vinculos.map(camposDoVinculo)}),
      validar: () => {
        const falhas = [];
        nome.erro(e.nome.trim() ? '' : 'Escreva o nome.'); if (!e.nome.trim()) falhas.push('Escreva o nome.');
        for (const {id, valor, fonte} of camposId) {
          const digitos = id.valor.replace(/\D/g, ''), esperado = id.tipo === 'cpf' ? 11 : id.tipo === 'cnpj' ? 14 : 0;
          const ok = id.valor.trim() && (!esperado || digitos.length === esperado);
          valor.erro(ok ? '' : id.tipo === 'cpf' ? 'CPF tem 11 dígitos. Confira o número no documento.' : id.tipo === 'cnpj' ? 'CNPJ tem 14 dígitos. Confira o número no documento.' : 'Escreva o identificador.'); if (!ok) falhas.push('Identificador inválido.');
          const fOk = e.vinculos.includes(id.fonteVinculo); fonte.erro(fOk ? '' : 'Escolha a evidência em que o identificador aparece.'); if (!fOk) falhas.push('Falta a fonte do identificador.');
        }
        return falhas[0] || '';
      }};
  }

  const TIPOS_RELACAO = ['sócio', 'irmão', 'cargo', 'contrato', 'pagamento'];
  function formLigacao(ctx) {
    const e = ctx.estado, entidades = (ctx.entidades || []).map(x => [x.id, x.nome]);
    const de = campo('De', selecao(entidades, e.origem, v => { e.origem = v; ctx.mudou(); }, 'Escolha a entidade'));
    const para = campo('Para', selecao(entidades, e.destino, v => { e.destino = v; ctx.mudou(); }, 'Escolha a entidade'));
    const tipoIn = texto1(e.tipo, v => { e.tipo = v; ctx.mudou(); }, 120); const lista = element('datalist'); lista.id = novoId('tipos'); for (const x of TIPOS_RELACAO) lista.append(Object.assign(element('option'), {value: x})); tipoIn.setAttribute('list', lista.id);
    const tipo = campo('Tipo de relação', tipoIn, {maximo: 120}); tipo.append(lista);
    const descricao = campo('Descrição', area(e.descricao, v => { e.descricao = v; ctx.mudou(); }, 2), {maximo: 2000});
    const nota = element('p', t('A linha fica contínua só com evidência de suporte sustentada. Sem ela, fica pontilhada.'), 'small form-ajuda');
    return {nos: [de, para, tipo, descricao, nota], coletar: () => ({origem: e.origem || null, destino: e.destino || null, tipo: e.tipo.trim(), descricao: e.descricao.trim(), evidencias: e.vinculos.map(camposDoVinculo)}),
      validar: () => {
        const falhas = [];
        const mesma = e.origem && e.origem === e.destino;
        de.erro(e.origem ? '' : 'Escolha a entidade.'); para.erro(!e.destino ? 'Escolha a entidade.' : mesma ? 'A ligação precisa de duas entidades diferentes. Troque uma das pontas.' : '');
        if (!e.origem || !e.destino || mesma) falhas.push('Escolha duas entidades diferentes.');
        tipo.erro(e.tipo.trim() ? '' : 'Escreva o tipo de relação.'); if (!e.tipo.trim()) falhas.push('Escreva o tipo de relação.');
        if (!e.vinculos.some(v => v.papel === 'suporte')) falhas.push('Falta a evidência. Ligue ao menos um documento que sustente a ligação.');
        return falhas[0] || '';
      }};
  }

  // Tabela (componentes.md#formularios-quadros, "Tabela"): título, descrição, colunas e linhas novas, cada célula com valor e fonte (uma evidência de suporte ligada).
  // A tabela só acrescenta: colunas já registradas só mudam de nome, linhas já registradas voltam como estão (corrigir uma célula é no painel "Célula selecionada").
  const TIPOS_COLUNA = [['texto', 'Texto'], ['data', 'Data'], ['monetario', 'Monetário'], ['numero', 'Número']];
  const MAX_COLUNAS = 30, MAX_LINHAS = 500, MAX_CELULAS = 5000;
  const semAcento = s => String(s || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '');
  function idDaColuna(nome, usados) {
    let base = semAcento(nome).toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 36) || 'coluna';
    if (!/^[a-z]/.test(base)) base = `c_${base}`;
    let id = base, n = 2; while (usados.has(id)) id = `${base.slice(0, 36)}_${n++}`;
    return id;
  }
  // Número como a pessoa escreve, no formato brasileiro: o ponto separa milhares e a vírgula, os decimais. "1.500" é 1500, "8.750.000" é 8750000, "1.500,25" é 1500.25,
  // "0,5" é 0.5 e "12" é 12 (o texto do servidor tem ponto decimal e nenhum milhar). Ponto que não é milhar ("1.5", "8.75") é ambíguo: a tela recusa e pede a vírgula,
  // em vez de adivinhar, porque um valor em reais lido errado muda a conta. Devolve {vazio}, {valor} ou {erro: mensagem}.
  const NUMERO_INVALIDO = 'Escreva só o número, com vírgula decimal: 8.750.000,00.';
  const NUMERO_AMBIGUO = 'O ponto separa milhares (8.750 é oito mil setecentos e cinquenta). Para decimais, use vírgula: 8,75.';
  function numeroDoTexto(texto) {
    const bruto = String(texto || '').trim().replace(/\s/g, '');
    if (!bruto) return {vazio: true};
    const negativo = bruto.startsWith('-'), v = negativo ? bruto.slice(1) : bruto;
    const [inteiro, decimal, resto] = v.split(',');
    if (resto !== undefined || (decimal !== undefined && !/^\d{1,12}$/.test(decimal))) return {erro: NUMERO_INVALIDO};
    let digitos;
    if (/^\d+$/.test(inteiro)) digitos = inteiro;
    else if (/^[1-9]\d{0,2}(\.\d{3})+$/.test(inteiro)) digitos = inteiro.replace(/\./g, '');
    else return {erro: /^[\d.]+$/.test(inteiro) ? NUMERO_AMBIGUO : NUMERO_INVALIDO};
    if (digitos.length > 30) return {erro: NUMERO_INVALIDO};
    return {valor: `${negativo ? '-' : ''}${digitos}${decimal !== undefined ? `.${decimal}` : ''}`};
  }
  const rotuloColuna = c => { const g = [c.moeda, c.unidade].filter(Boolean).join(' '); return g ? `${c.nome} (${g})` : c.nome; };
  function formTabela(ctx) {
    const e = ctx.estado, nos = [];
    const titulo = campo('Título da tabela', texto1(e.titulo, v => { e.titulo = v; ctx.mudou(); }, 300), {maximo: 300});
    const descricao = campo('Descrição', area(e.descricao, v => { e.descricao = v; ctx.mudou(); }, 2), {maximo: 2000});
    const fontes = e.vinculos.filter(v => v.papel === 'suporte');
    const nomeFonte = v => `${v.vista.nome ? v.vista.nome + ', ' : ''}${v.vista.legivel}`.trim() || t('a evidência');
    // Colunas
    const colunas = element('div', undefined, 'form-colunas'); colunas.append(element('p', t('Colunas'), 'form-rotulo'));
    const camposColuna = [];
    e.colunas.forEach((c, i) => {
      const bloco = element('div', undefined, 'form-coluna');
      const nome = campo('Nome da coluna', texto1(c.nome, v => { c.nome = v; ctx.mudou(); }, 120), {maximo: 120});
      const partes = [nome];
      let moeda = null, unidade = null;
      if (c.fixa) partes.push(element('p', [t(rotulo(TIPOS_COLUNA, c.tipo)), ...[c.moeda, c.unidade].filter(Boolean)].join(' · ') + ' · ' + t('já registrada: só o nome muda'), 'small form-ajuda'));
      else {
        partes.push(campo('Tipo', selecao(TIPOS_COLUNA, c.tipo, v => { c.tipo = v; if (v === 'monetario' && !c.moeda) c.moeda = 'BRL'; if (v === 'texto' || v === 'data') c.unidade = ''; ctx.mudou(); ctx.redesenhar(); })));
        if (c.tipo === 'monetario') { moeda = campo('Moeda', texto1(c.moeda, v => { c.moeda = v.toUpperCase(); ctx.mudou(); }, 3), {ajuda: 'Código de três letras: BRL, USD, EUR'}); partes.push(moeda); }
        if (c.tipo === 'monetario' || c.tipo === 'numero') {
          unidade = campo(c.tipo === 'numero' ? 'Unidade' : 'Escala (opcional)', texto1(c.unidade, v => { c.unidade = v; ctx.mudou(); }, 30), {maximo: 30, ajuda: c.tipo === 'numero' ? 'kg, km, %, pessoas…' : 'mil, milhões, como a fonte declara'});
          partes.push(unidade);
        }
        const remover = linkBotao(t('Remover'), 'form-remover'); remover.setAttribute('aria-label', `${t('Remover')}: ${c.nome || t('Nome da coluna')}`);
        remover.addEventListener('click', () => { e.colunas.splice(i, 1); for (const l of e.linhas) delete l.celulas[c.chave]; ctx.mudou(); ctx.redesenhar(); });
        partes.push(remover);
      }
      bloco.append(...partes); colunas.append(bloco); camposColuna.push({c, nome, moeda, unidade});
    });
    const maisColuna = linkBotao('+ ' + t('Coluna'), 'form-mais'); maisColuna.disabled = e.colunas.length >= MAX_COLUNAS;
    maisColuna.addEventListener('click', () => { e.colunas.push({id: null, chave: novoId('coluna'), nome: '', tipo: 'texto', moeda: '', unidade: '', fixa: false}); ctx.mudou(); ctx.redesenhar(); });
    colunas.append(maisColuna);
    // Linhas: as já registradas só contam; as novas têm uma célula por coluna, com valor e fonte.
    const linhas = element('div', undefined, 'form-linhas'); linhas.append(element('p', t('Linhas'), 'form-rotulo'));
    const registradas = e.linhas.filter(l => l.fixa).length;
    if (registradas) linhas.append(element('p', t(registradas === 1 ? '{n} linha já registrada. Para corrigir uma célula, escolha-a na tabela: o painel “Célula selecionada” guarda o valor anterior e a justificativa.' : '{n} linhas já registradas. Para corrigir uma célula, escolha-a na tabela: o painel “Célula selecionada” guarda o valor anterior e a justificativa.', {n: registradas}), 'small form-ajuda'));
    const camposCelula = [];
    e.linhas.forEach((l, i) => {
      if (l.fixa) return;
      const bloco = element('fieldset', undefined, 'form-linha-nova'); bloco.append(element('legend', t('Linha nova {n}', {n: i + 1}), 'form-rotulo'));
      for (const c of e.colunas) {
        const cel = l.celulas[c.chave] ||= {texto: '', fonteVinculo: null};
        const dica = c.tipo === 'data' ? 'Ano, mês e ano ou dia completo: 2025, 03/2025 ou 03/03/2025' : c.tipo === 'texto' ? '' : 'Com vírgula decimal, como no documento: 8.750.000,00';
        const valor = campo(rotuloColuna(c) || 'Valor', texto1(cel.texto, v => { cel.texto = v; ctx.mudou(); }, c.tipo === 'texto' ? 2000 : 0), {ajuda: dica, maximo: c.tipo === 'texto' ? 2000 : 0});
        if (c.tipo === 'monetario' || c.tipo === 'numero') valor.controle.setAttribute('inputmode', 'decimal');
        const opcoes = fontes.map(v => [String(e.vinculos.indexOf(v)), nomeFonte(v)]);
        const fonte = campo(`${t('Fonte da célula')}: ${rotuloColuna(c) || t('Valor')}`, selecao(opcoes, cel.fonteVinculo && fontes.includes(cel.fonteVinculo) ? String(e.vinculos.indexOf(cel.fonteVinculo)) : '', v => { cel.fonteVinculo = v === '' ? null : e.vinculos[Number(v)]; ctx.mudou(); }, 'Sem fonte (○ a conferir)'));
        bloco.append(valor, fonte); camposCelula.push({l, c, cel, valor, fonte});
      }
      const remover = linkBotao(t('Remover'), 'form-remover'); remover.setAttribute('aria-label', `${t('Remover')}: ${t('Linha nova {n}', {n: i + 1})}`);
      remover.addEventListener('click', () => { e.linhas.splice(i, 1); ctx.mudou(); ctx.redesenhar(); });
      bloco.append(remover); linhas.append(bloco);
    });
    const maisLinha = linkBotao('+ ' + t('Adicionar linha'), 'form-mais'); maisLinha.disabled = !e.colunas.length || e.linhas.length >= MAX_LINHAS || (e.linhas.length + 1) * e.colunas.length > MAX_CELULAS;
    maisLinha.addEventListener('click', () => { e.linhas.push({id: null, fixa: false, celulas: {}}); ctx.mudou(); ctx.redesenhar(); });
    linhas.append(maisLinha);
    const nota = element('p', t('Célula sem fonte nasce “○ a conferir”. A tabela só acrescenta: linhas e colunas já registradas não se apagam.'), 'small form-ajuda');
    nos.push(titulo, descricao, colunas, linhas, nota);
    const indice = v => v ? e.vinculos.indexOf(v) : null;
    return {nos, coletar: () => {
      const usados = new Set(e.colunas.filter(c => c.fixa).map(c => c.id));
      for (const c of e.colunas) if (!c.fixa) { c.id = idDaColuna(c.nome, usados); usados.add(c.id); }
      const antigas = e.colunas.filter(c => c.fixa);
      const valorNovo = (c, cel) => c.tipo === 'data' ? (normalizaData(cel.texto) || null) : c.tipo === 'texto' ? (cel.texto.trim() || null) : (numeroDoTexto(cel.texto).valor ?? null);
      return {titulo: e.titulo.trim(), descricao: e.descricao.trim(),
        colunas: e.colunas.map(c => c.fixa ? {id: c.id, nome: c.nome.trim(), tipo: c.tipo, moeda: c.moeda || null, unidade: c.unidade || null}
          : {id: c.id, nome: c.nome.trim(), tipo: c.tipo, moeda: c.tipo === 'monetario' ? (c.moeda || '').trim() || null : null, unidade: (c.tipo === 'numero' || c.tipo === 'monetario') ? ((c.unidade || '').trim() || null) : null}),
        linhas: e.linhas.map(l => l.fixa
          ? {id: l.id, celulas: Object.fromEntries(antigas.map(c => [c.id, {valor: l.celulas[c.chave].valor, fonte: indice(l.celulas[c.chave].fonteVinculo), estado: l.celulas[c.chave].estado}]))}
          : {celulas: Object.fromEntries(e.colunas.map(c => { const cel = l.celulas[c.chave] || {texto: '', fonteVinculo: null}; return [c.id, {valor: valorNovo(c, cel), fonte: indice(cel.fonteVinculo)}]; }))}),
        evidencias: e.vinculos.map(camposDoVinculo)};
    }, validar: () => {
      const falhas = [];
      titulo.erro(e.titulo.trim() ? '' : 'Escreva o título da tabela.'); if (!e.titulo.trim()) falhas.push('Escreva o título da tabela.');
      if (!e.colunas.length) falhas.push('Registre ao menos uma coluna.');
      for (const {c, nome, moeda, unidade} of camposColuna) {
        nome.erro(c.nome.trim() ? '' : 'Escreva o nome da coluna.'); if (!c.nome.trim()) falhas.push('Escreva o nome da coluna.');
        if (moeda) { const ok = /^[A-Z]{3}$/.test((c.moeda || '').trim()); moeda.erro(ok ? '' : 'A moeda leva três letras maiúsculas: BRL, USD, EUR.'); if (!ok) falhas.push('Moeda inválida.'); }
        if (unidade && c.tipo === 'numero') { const ok = !!(c.unidade || '').trim(); unidade.erro(ok ? '' : 'Número exige a unidade: kg, km, %, pessoas…'); if (!ok) falhas.push('Falta a unidade.'); }
      }
      for (const {c, cel, valor} of camposCelula) {
        let msg = '';
        if (c.tipo === 'data') msg = !cel.texto.trim() || /^\d{4}(-\d{2}(-\d{2})?)?$/.test(normalizaData(cel.texto)) ? '' : 'Use ano, mês e ano ou dia completo: 2025, 03/2025 ou 03/03/2025.';
        else if (c.tipo !== 'texto') msg = numeroDoTexto(cel.texto).erro || '';
        valor.erro(msg); if (msg) falhas.push(msg);
      }
      // uma célula só tem como fonte uma evidência de suporte ligada a esta tabela
      for (const l of e.linhas) for (const c of e.colunas) { const f = l.celulas[c.chave]?.fonteVinculo; if (f && (!e.vinculos.includes(f) || f.papel !== 'suporte')) falhas.push('Uma célula usa como fonte uma evidência que não é de suporte. Troque o papel da evidência ou a fonte da célula.'); }
      if (e.linhas.length * e.colunas.length > MAX_CELULAS) falhas.push('Tabela grande demais: até 500 linhas e 5.000 células.');
      return falhas[0] || '';
    }, vinculoEmUso: v => e.linhas.some(l => Object.values(l.celulas).some(cel => cel.fonteVinculo === v))};
  }

  // Corrigir uma célula (componentes.md#formularios-quadros, "Tabela"; P15.3): novo valor e/ou nova fonte, com justificativa obrigatória quando muda o que já existia;
  // o servidor guarda o valor anterior (tabelas-corrigir). Vive no painel "Célula selecionada", não no formulário da tabela.
  function corrigirCelula({tabela, linha, coluna, celula, casoId, aoSalvar, aoCancelar}) {
    const raiz = element('form', undefined, 'form-celula'); raiz.noValidate = true;
    const h = element('h4', t('Corrigir a célula'), 'form-titulo'); h.tabIndex = -1;
    const numerica = ['numero', 'monetario'].includes(coluna.tipo);
    const atual = celula.valor === null || celula.valor === undefined ? '' : coluna.tipo === 'data' ? mostraData(celula.valor) : numerica ? String(celula.valor).replace('.', ',') : String(celula.valor);
    let texto = atual, fonteTexto = celula.fonte === null || celula.fonte === undefined ? '' : String(celula.fonte), justificativa = '', ocupado = false;
    const valor = campo(t('Novo valor: {coluna}', {coluna: rotuloColuna(coluna)}), texto1(texto, v => { texto = v; }, coluna.tipo === 'texto' ? 2000 : 0), {ajuda: coluna.tipo === 'data' ? 'Ano, mês e ano ou dia completo: 2025, 03/2025 ou 03/03/2025' : numerica ? 'Com vírgula decimal, como no documento: 8.750.000,00' : '', maximo: coluna.tipo === 'texto' ? 2000 : 0});
    if (numerica) valor.controle.setAttribute('inputmode', 'decimal');
    const opcoes = (tabela.evidencias || []).map((ev, i) => [String(i), ev]).filter(([i, ev]) => i === fonteTexto || (ev.papel === 'suporte' && ev.estado === 'conferida'))
      .map(([i, ev]) => [i, `${ev.evidencia?.documento?.nome ? ev.evidencia.documento.nome + ', ' : ''}${ev.localizador?.legivel || ev.evidencia?.localizador?.legivel || ''}`.trim() || t('a evidência')]);
    const fonte = campo('Fonte da célula', selecao(opcoes, fonteTexto, v => { fonteTexto = v; }, 'Sem fonte (○ a conferir)'));
    const just = campo('Justificativa', area('', v => { justificativa = v; if (v.trim()) just.erro(''); }, 2), {maximo: 2000, ajuda: 'Obrigatória ao mudar um valor ou uma fonte que já existiam. O valor anterior fica guardado.'});
    const erroGeral = element('p', undefined, 'form-erro form-erro-geral'); erroGeral.setAttribute('role', 'alert'); erroGeral.hidden = true;
    const pe = element('div', undefined, 'form-pe'), cancelar = botao(t('Cancelar')), salvar = botao(t('Salvar correção'));
    pe.append(cancelar, salvar);
    cancelar.addEventListener('click', () => { if (!ocupado) aoCancelar?.(); });
    raiz.addEventListener('submit', ev => ev.preventDefault());
    salvar.addEventListener('click', async () => {
      if (ocupado) return;
      erroGeral.hidden = true; valor.erro(''); just.erro('');
      let novo;
      if (coluna.tipo === 'data') { novo = normalizaData(texto) || null; if (novo && !/^\d{4}(-\d{2}(-\d{2})?)?$/.test(novo)) { valor.erro('Use ano, mês e ano ou dia completo: 2025, 03/2025 ou 03/03/2025.'); valor.controle.focus(); return; } }
      else if (numerica) { const n = numeroDoTexto(texto); if (n.erro) { valor.erro(n.erro); valor.controle.focus(); return; } novo = n.valor ?? null; }
      else novo = texto.trim() || null;
      const novaFonte = fonteTexto === '' ? null : Number(fonteTexto), antes = celula.valor ?? null, fonteAntes = celula.fonte ?? null;
      if (novo === antes && novaFonte === fonteAntes) { erroGeral.textContent = t('Mude o valor ou a fonte para corrigir a célula.'); erroGeral.hidden = false; valor.controle.focus(); return; }
      // mudar o que já existia é correção e pede justificativa; preencher o que faltava, não
      if (((antes !== null && novo !== antes) || (fonteAntes !== null && novaFonte !== fonteAntes)) && !justificativa.trim()) { just.erro('Escreva a justificativa da correção.'); just.controle.focus(); return; }
      ocupado = true; salvar.textContent = t('Salvando…'); salvar.disabled = cancelar.disabled = true; raiz.setAttribute('aria-busy', 'true');
      try {
        await api('tabelas-corrigir', {caso: casoId, requisicao_id: requisicao(), id: tabela.id, anterior_sha256: tabela.sha256, correcoes: [{linha, coluna: coluna.id, valor: novo, fonte: novaFonte, justificativa: justificativa.trim()}]});
        await aoSalvar?.();
      } catch (falha) {
        ocupado = false; salvar.textContent = t('Salvar correção'); salvar.disabled = cancelar.disabled = false; raiz.removeAttribute('aria-busy');
        erroGeral.textContent = `${t('Não deu para salvar:')} ${falha.message}`; erroGeral.hidden = false;
      }
    });
    raiz.append(h, valor, fonte, just, erroGeral, pe);
    return raiz;
  }

  const QUADROS = {
    hipotese: {prefixo: 'hipoteses', operacaoDetalhe: 'hipoteses-detalhe', construir: formHipotese, detalhe: (c, id) => api('hipoteses-detalhe', {caso: c, id}), rotuloNovo: 'Nova hipótese', rotuloEditar: 'Editar hipótese', vazio: () => ({enunciado: '', situacao: 'em_aberto', lacunas: [], vinculos: []}),
      deDetalhe: d => ({enunciado: d.estado.enunciado, situacao: d.estado.situacao, lacunas: (d.estado.lacunas || []).map(l => ({valor: l.descricao, diligencia_id: l.diligencia_id})), vinculos: (d.evidencias || []).map(vinculoDeItem)}),
      deSugestao: s => ({enunciado: s.campos.enunciado, situacao: 'em_aberto', lacunas: [], vinculos: (s.evidencias || []).map((_, i) => vinculoDeSugestao(s, i))})},
    acontecimento: {prefixo: 'linha-tempo', operacaoDetalhe: 'linha-tempo-detalhe', construir: formAcontecimento, detalhe: (c, id) => api('linha-tempo-detalhe', {caso: c, id}), rotuloNovo: 'Novo acontecimento', rotuloEditar: 'Editar acontecimento', retirada: {de: 'da linha do tempo', nome: e => e.descricao},
      vazio: () => ({descricao: '', datas: [{tipo: 'fato', texto: '', aproximada: false, fonteVinculo: null, observacao: ''}], vinculos: []}),
      deDetalhe: d => { const vinculos = (d.evidencias || []).map(vinculoDeItem); return {descricao: d.estado.descricao, vinculos, datas: d.estado.datas.map(x => ({tipo: x.tipo, texto: mostraData(x.valor), aproximada: x.aproximada, fonteVinculo: vinculos[x.fonte] || null, observacao: x.observacao || ''}))}; },
      deSugestao: s => { const vinculos = (s.evidencias || []).map((_, i) => vinculoDeSugestao(s, i)); return {descricao: s.campos.descricao, vinculos, datas: (s.campos.datas || []).map(x => ({tipo: x.tipo, texto: mostraData(x.valor), aproximada: !!x.aproximada, fonteVinculo: vinculos[x.fonte || 0] || null, observacao: x.observacao || ''}))}; }},
    entidade: {prefixo: 'mapa-entidade', operacaoDetalhe: 'mapa-entidade-detalhe', construir: formEntidade, detalhe: (c, id) => api('mapa-entidade-detalhe', {caso: c, id}), rotuloNovo: 'Nova entidade', rotuloEditar: 'Editar entidade', retirada: {de: 'do mapa', nome: e => e.nome}, vazio: () => ({tipo: 'pessoa', nome: '', variantes: [], identificadores: [], vinculos: []}),
      deDetalhe: d => { const vinculos = (d.evidencias || []).map(vinculoDeItem); return {tipo: d.estado.tipo, nome: d.estado.nome, variantes: (d.estado.variantes || []).map(valor => ({valor})), vinculos,
        identificadores: (d.estado.identificadores || []).map(i => ({tipo: i.tipo, valor: i.valor, fonteVinculo: vinculos[i.fonte] || null}))}; },
      deSugestao: s => ({tipo: s.campos.tipo, nome: s.campos.nome, variantes: (s.campos.variantes || []).map(valor => ({valor})), identificadores: [], vinculos: (s.evidencias || []).map((_, i) => vinculoDeSugestao(s, i))})},
    ligacao: {prefixo: 'mapa-relacao', operacaoDetalhe: 'mapa-relacao-detalhe', construir: formLigacao, detalhe: async (c, id) => { const m = await api('mapa-ver', {caso: c}); const r = m.relacoes.find(x => x.id === id); if (!r) throw new Error(t('A ligação não existe mais.')); return {id: r.id, sha256: r.sha256, estado: r, evidencias: r.evidencias}; }, rotuloNovo: 'Nova ligação', rotuloEditar: 'Editar ligação', retirada: {de: 'do mapa', nome: e => e.tipo}, vazio: () => ({origem: '', destino: '', tipo: '', descricao: '', vinculos: []}),
      deDetalhe: d => ({origem: d.estado.origem, destino: d.estado.destino, tipo: d.estado.tipo, descricao: d.estado.descricao || '', vinculos: (d.evidencias || []).map(vinculoDeItem)}),
      deSugestao: s => ({origem: s.campos.origem || '', destino: s.campos.destino || '', tipo: s.campos.tipo, descricao: s.campos.descricao || '', vinculos: (s.evidencias || []).map((_, i) => vinculoDeSugestao(s, i))})},
    tabela: {prefixo: 'tabelas', operacaoDetalhe: 'tabelas-detalhe', construir: formTabela, detalhe: async (c, id) => { const d = await api('tabelas-detalhe', {caso: c, id}); return {...d, estado: {titulo: d.titulo, descricao: d.descricao, colunas: d.colunas, linhas: d.linhas}}; }, rotuloNovo: 'Nova tabela', rotuloEditar: 'Editar tabela', retirada: {de: 'das tabelas', nome: e => e.titulo},
      vazio: () => ({titulo: '', descricao: '', colunas: [{id: null, chave: novoId('coluna'), nome: '', tipo: 'texto', moeda: '', unidade: '', fixa: false}], linhas: [], vinculos: []}),
      deDetalhe: d => { const vinculos = (d.evidencias || []).map(vinculoDeItem); return {titulo: d.titulo, descricao: d.descricao || '', vinculos,
        colunas: d.colunas.map(c => ({id: c.id, chave: c.id, nome: c.nome, tipo: c.tipo, moeda: c.moeda || '', unidade: c.unidade || '', fixa: true})),
        linhas: d.linhas.map(l => ({id: l.id, fixa: true, celulas: Object.fromEntries(Object.entries(l.celulas).map(([k, x]) => [k, {valor: x.valor, estado: x.estado, fonteVinculo: x.fonte === null || x.fonte === undefined ? null : vinculos[x.fonte] || null}]))}))}; }},
  };

  // Abre o formulário no `host`. `item` (detalhe do servidor, com estado, sha256 e evidencias) edita; `sugestao` corrige uma sugestão da IA; sem os dois, cria.
  // opcoes: {tipo, casoId, host, item, sugestao, entidades, tiposData, aoSalvar(resposta), aoCancelar(), aoRetirar(item)}
  function abrir(opcoes) {
    const def = QUADROS[opcoes.tipo], {casoId, host, item = null, sugestao = null} = opcoes;
    const estado = item ? def.deDetalhe(item) : sugestao ? def.deSugestao(sugestao) : (opcoes.inicial || def.vazio());
    const inicial = JSON.stringify(serializar(estado));
    let sujo = false, ocupado = false, seletor = null, corpoAtual = null;
    const titulo = sugestao ? t('Corrigir sugestão da IA') : t(item ? def.rotuloEditar : def.rotuloNovo);
    const mudou = () => { sujo = JSON.stringify(serializar(estado)) !== inicial; };
    // O estado guarda objetos (vínculos); o instantâneo só compara o que a pessoa vê.
    function serializar(x) { return JSON.parse(JSON.stringify(x, (k, v) => (k === 'vista' || k === 'fonteVinculo' ? undefined : v))); }
    const ctx = {estado, casoId, mudou, entidades: opcoes.entidades, tiposData: opcoes.tiposData, edicao: !!item};
    ctx.removerVinculo = v => { if (corpoAtual?.vinculoEmUso?.(v)) { const g = host.querySelector('.form-erro-geral'); if (g) { g.textContent = t('Esta evidência é a fonte de uma célula. Troque a fonte da célula antes de desligá-la.'); g.hidden = false; } return; } const i = estado.vinculos.indexOf(v); if (i >= 0) estado.vinculos.splice(i, 1); for (const d of estado.datas || []) if (d.fonteVinculo === v) d.fonteVinculo = null; for (const d of estado.identificadores || []) if (d.fonteVinculo === v) d.fonteVinculo = null; mudou(); desenhar(); host.querySelector('.form-ligar')?.focus(); };
    ctx.redesenhar = () => desenhar();
    ctx.abrirSeletor = () => {
      const lim = () => ({atingido: estado.vinculos.length >= MAX_VINCULOS, razao: 'Este item já tem 100 evidências, o limite.'});
      const quadroDoItem = {hipotese: 'hipoteses', acontecimento: 'linha_tempo', entidade: 'entidades', ligacao: 'relacoes'}[opcoes.tipo], itemRef = item && quadroDoItem ? {quadro: quadroDoItem, id: item.id} : null;
      seletor = Q.seletorEvidencia({buscar: Q.buscaEvidencias(casoId, itemRef), limite: lim, rotuloVoltar: 'Voltar ao formulário', aoVoltar: () => { seletor = null; desenhar(); host.querySelector('.form-ligar')?.focus(); },
        aoAbrirOriginal: (r, gatilho, retorno) => Q.abrirOriginal(casoId, vinculoDeResultado(r).vista.original, gatilho, retorno),
        aoLigar: r => {
          const v = vinculoDeResultado(r);
          if (!v.referencia) return;
          estado.vinculos.push(v); mudou(); seletor = null; desenhar();
          const cartoes = host.querySelectorAll('.vinculo-cartao'); const ultimo = cartoes[cartoes.length - 1]; if (ultimo) { ultimo.tabIndex = -1; ultimo.focus(); }
          Q.sugestoes.anunciar(t('Evidência ligada.'));
        }});
      host.replaceChildren(seletor); seletor.foco();
    };
    function desenhar() {
      const corpo = corpoAtual = def.construir(ctx);
      const raiz = element('form', undefined, 'form-quadro'); raiz.noValidate = true; raiz.setAttribute('aria-labelledby', 'form-quadro-titulo');
      const voltar = linkBotao('‹ ' + t('Voltar'), 'form-voltar'); voltar.addEventListener('click', () => cancelar());
      const h = element('h3', titulo, 'form-titulo'); h.id = 'form-quadro-titulo'; h.tabIndex = -1;
      const erroGeral = element('p', undefined, 'form-erro form-erro-geral'); erroGeral.setAttribute('role', 'alert'); erroGeral.hidden = true;
      const pe = element('div', undefined, 'form-pe');
      const cancelarB = botao(t('Cancelar')), salvar = botao(t('Salvar'));
      if (item && def.retirada) { const retirar = botao(t('Retirar…'), 'form-retirar'); retirar.addEventListener('click', () => pedirRetirada(raiz, pe, retirar)); pe.append(retirar); }
      pe.append(cancelarB, salvar);
      cancelarB.addEventListener('click', () => cancelar());
      raiz.append(voltar, h, ...corpo.nos, secaoEvidencias({...ctx, abrirSeletor: ctx.abrirSeletor, removerVinculo: ctx.removerVinculo}), erroGeral, pe);
      raiz.addEventListener('submit', ev => ev.preventDefault());
      salvar.addEventListener('click', async () => {
        if (ocupado) return;
        erroGeral.hidden = true;
        const falha = corpo.validar();
        const onde = v => `${v.vista.nome ? v.vista.nome + ', ' : ''}${v.vista.legivel}`.trim() || t('a evidência');
        const semNatureza = estado.vinculos.find(v => !v.natureza), semJustificativa = estado.vinculos.find(v => !String(v.justificativa || '').trim());
        if (!falha && semNatureza) {
          erroGeral.textContent = `${t('Falta a natureza. Escolha o que a fonte é: declaração documental, alegação atribuída, inferência ou pendência.')} (${onde(semNatureza)})`; erroGeral.hidden = false;
          semNatureza.vista.campos?.natureza.erro('Escolha a natureza.'); semNatureza.vista.campos?.natureza.controle.focus(); return;
        }
        if (!falha && semJustificativa) {
          erroGeral.textContent = t('Falta a justificativa de {onde}. Escreva por que esta evidência entra neste item.', {onde: onde(semJustificativa)}); erroGeral.hidden = false;
          semJustificativa.vista.campos?.justificativa.erro('Escreva a justificativa.'); semJustificativa.vista.campos?.justificativa.controle.focus(); return;
        }
        if (falha) { erroGeral.textContent = t(falha); erroGeral.hidden = false; raiz.querySelector('[aria-invalid="true"]')?.focus(); return; }
        ocupado = true; salvar.textContent = t('Salvando…'); salvar.disabled = cancelarB.disabled = true; raiz.setAttribute('aria-busy', 'true');
        try {
          const campos = corpo.coletar();
          let resposta;
          if (sugestao) resposta = await api('sugestoes-corrigir', {caso: casoId, id: sugestao.id, requisicao_id: requisicao(), campos});
          else if (item) resposta = await api(`${def.prefixo}-atualizar`, {caso: casoId, id: item.id, anterior_sha256: item.sha256, requisicao_id: requisicao(), ...campos});
          else resposta = await api(`${def.prefixo}-criar`, {caso: casoId, requisicao_id: requisicao(), ...campos});
          sujo = false; await opcoes.aoSalvar?.(resposta);
        } catch (falhaServidor) {
          ocupado = false; salvar.textContent = t('Salvar'); salvar.disabled = cancelarB.disabled = false; raiz.removeAttribute('aria-busy');
          erroGeral.textContent = `${t('Não deu para salvar:')} ${falhaServidor.message}`; erroGeral.hidden = false;
          // vinculo_sem_justificativa traz a posição do cartão no pedido (a ordem de estado.vinculos): a tela aponta o campo e leva o foco até ele.
          const r = falhaServidor.result;
          if (r?.codigo === 'vinculo_sem_justificativa') {
            const alvo = estado.vinculos[Number(r.parametros?.posicao) - 1]?.vista.campos?.justificativa;
            if (alvo) { alvo.erro('Revise a justificativa: vazia ou longa demais.'); alvo.controle.focus(); }
          }
        }
      });
      host.replaceChildren(raiz);
    }
    // Retirar (componentes.md#formularios-quadros, "Retirar"): o item sai da vista e fica no registro, com o motivo, que é obrigatório. A ação só se habilita com o motivo.
    function pedirRetirada(raiz, pe, gatilho) {
      raiz.querySelector('.form-retirada')?.remove();
      const bloco = element('section', undefined, 'form-retirada'); bloco.setAttribute('role', 'group');
      const nome = def.retirada.nome(item.estado), h = element('h4'); h.append(t('Retirar “'), dado('span', nome), t('” {de}?', {de: t(def.retirada.de)})); h.id = novoId('retirar'); bloco.setAttribute('aria-labelledby', h.id);
      const motivo = campo('Motivo (obrigatório)', area('', () => { confirmar.disabled = !motivo.controle.value.trim() || ocupadoRet; }, 2), {maximo: 1000});
      const erro = element('p', undefined, 'form-erro'); erro.setAttribute('role', 'alert'); erro.hidden = true;
      const acoesRet = element('div', undefined, 'form-pe'), cancelarR = botao(t('Cancelar')), confirmar = botao(t('Retirar'), 'danger'); confirmar.disabled = true;
      let ocupadoRet = false;
      cancelarR.addEventListener('click', () => { bloco.remove(); gatilho.focus?.(); });
      confirmar.addEventListener('click', async () => {
        const texto = motivo.controle.value.trim(); if (!texto) return;
        ocupadoRet = true; confirmar.disabled = cancelarR.disabled = true; confirmar.textContent = t('Retirando…'); erro.hidden = true;
        try {
          const resposta = await api(`${def.prefixo}-atualizar`, {caso: casoId, id: item.id, anterior_sha256: item.sha256, requisicao_id: requisicao(), retirado: true, motivo_retirada: texto});
          sujo = false; await opcoes.aoSalvar?.(resposta, {retirado: true});
        } catch (falha) { ocupadoRet = false; confirmar.textContent = t('Retirar'); cancelarR.disabled = false; confirmar.disabled = false; erro.textContent = `${t('Não deu para retirar:')} ${falha.message}`; erro.hidden = false; }
      });
      acoesRet.append(cancelarR, confirmar); bloco.append(h, motivo, erro, acoesRet); pe.before(bloco); motivo.controle.focus();
    }
    async function cancelar() {
      if (ocupado) return;
      if (sujo && !await window.Dialogo.confirmar({variante: 'destrutivo', titulo: t('Descartar alterações?'), texto: t('Há alterações não salvas.'), acao: t('Descartar alterações')})) return;
      opcoes.aoCancelar?.();
    }
    desenhar();
    host.querySelector('.form-titulo')?.focus();
    return {cancelar, sujo: () => sujo};
  }
  // O formulário ocupa o painel da aba do quadro (a camada de tela cheia abaixo de 1024 px é o mesmo painel); ao salvar ou cancelar, a aba recarrega
  // e o foco volta ao que abriu o formulário (`gatilho`) ou ao título do quadro. `carregar` busca o detalhe de um item existente.
  async function abrirNoPainel({tipo, abaId, casoId, itemId = null, sugestao = null, entidades = [], tiposData = null, gatilho = null, inicial = null}) {
    const painel = document.getElementById(`quadros-${abaId}`); if (!painel) return null;
    const def = QUADROS[tipo], host = element('div', undefined, 'form-host'), L = painel.__lateral;
    let item = null;
    if (itemId) {
      try { item = await def.detalhe(casoId, itemId); }
      catch (erro) { Q.sugestoes.anunciar(`${t('Não deu para abrir:')} ${erro.message}`); return null; }
    }
    if (!tiposData && tipo === 'acontecimento') { try { tiposData = (await api('linha-tempo-listar', {caso: casoId})).tipos_data || {}; } catch (_) { tiposData = {}; } }
    // a resposta de uma apuração que já não é a selecionada não abre formulário no painel da outra
    const atual = window.contextoCaso?.(); if (atual && atual !== casoId) return null;
    // O formulário abre no painel da direita (em 1440) ou na camada de tela cheia (abaixo de 1024 px); o quadro continua à vista. Aberto a partir de uma sugestão,
    // "Cancelar" volta à sugestão intacta; senão, fecha o painel e devolve o foco a quem abriu.
    if (L) L.abrir([host], {empilhar: !!sugestao, origem: gatilho}); else painel.replaceChildren(host);
    const voltar = async () => { if (L) L.voltar(); else { await Q.selecionar(abaId, true); (gatilho && document.contains(gatilho) ? gatilho : painel.querySelector('h3,h4'))?.focus?.(); } };
    return abrir({tipo, casoId, host, item, sugestao, entidades, tiposData, inicial, aoCancelar: voltar,
      aoSalvar: async (resposta, extra = {}) => { if (tipo === 'tabela') Q.tabelaEscolhida = itemId || resposta?.id || null; await Q.selecionar(abaId, true); Q.sugestoes.anunciar(t(extra.retirado ? 'Retirado. O item fica no registro, com o motivo.' : sugestao ? 'Sugestão corrigida e confirmada.' : item ? 'Alterações salvas.' : 'Salvo.')); painel.querySelector('h3,h4')?.focus?.(); }});
  }
  // A apuração tem análise (rodada com achados publicados)? Acontecimento e ligação só se criam com evidência, que vem dessas análises.
  const temAnalise = casoId => (typeof cases !== 'undefined' ? cases : []).find(c => c.id === casoId)?.rodadas?.length > 0;
  // "+ Nova ..." no topo do quadro e "Editar" em cada item só para quem pode mudar o quadro (o servidor continua sendo a barreira).
  // `rotulo`: o texto do botão no estado vazio do quadro ("Criar a primeira hipótese"), sem o "+"; sem ele, "+ Nova hipótese".
  const botaoNovo = (tipo, abaId, casoId, extra = () => ({}), rotulo = '') => {
    const def = QUADROS[tipo]; if (!podeCriar(def.prefixo)) return null;
    const b = botao(rotulo ? t(rotulo) : '+ ' + t(def.rotuloNovo), 'quadro-novo'); b.dataset.tipo = tipo;
    b.addEventListener('click', () => abrirNoPainel({tipo, abaId, casoId, gatilho: b, ...extra()})); return b;
  };
  const botaoEditar = (tipo, abaId, casoId, itemId, nomeItem, extra = () => ({})) => {
    const def = QUADROS[tipo]; if (!podeAtualizar(def.prefixo)) return null;
    const b = botao(t('Editar'), 'quadro-editar'); b.setAttribute('aria-label', `${t('Editar')}: ${nomeItem}`);
    b.addEventListener('click', () => abrirNoPainel({tipo, abaId, casoId, itemId, gatilho: b, ...extra()})); return b;
  };
  // Hipótese a partir de uma comparação entre processos (componentes.md#comparar-processos): enunciado em branco, situação "em aberto" e as evidências dos dois lados
  // ligadas com o que o servidor entrega em cada evidência (achado_id, revisao_ia e preenchimento da P47, a9264ac/785cfec): a tela não fixa papel nem suporte.
  function hipoteseDaComparacao(c) {
    const vistos = new Set(), vinculos = [];
    for (const lado of c.lados || []) for (const ev of [lado.fundamento, lado.desfecho_evidencia]) {
      if (!ev || ev.estado === 'indisponivel') continue;
      const chave = JSON.stringify(ev.referencia); if (vistos.has(chave)) continue; vistos.add(chave);
      const p = ev.preenchimento || null, achadoId = ev.achado_id || c.achado?.id || null, ia = ev.revisao_ia ? {...ev.revisao_ia, achado_id: achadoId} : null;
      // sem preenchimento (servidor antigo) o vínculo nasce "não revisado" e a pessoa preenche; com ele, vale o valor do servidor, e "Voltar ao da IA" também.
      vinculos.push(vinculoDeItem({referencia: ev.referencia, achado_id: achadoId, papel: p?.papel || 'suporte', suporte: p?.suporte || 'nao_revisado', natureza: p?.natureza || '', justificativa: ev.justificativa_ia || '', estado: ev.estado,
        evidencia: {documento: ev.documento, trecho: ev.trecho, localizador: ev.localizador}, localizador: ev.localizador, revisao_ia: ia, conferencia_humana: ev.conferencia_humana, destino_atual: p?.destino || c.achado?.destino,
        preenchimento_ia: p}));
    }
    return {enunciado: '', situacao: 'em_aberto', lacunas: [], vinculos};
  }
  return {abrir, abrirNoPainel, hipoteseDaComparacao, temAnalise, botaoNovo, botaoEditar, podeCriar, podeAtualizar, corrigirCelula, numeroDoTexto, QUADROS, campo, segmentado, cartaoVinculo, vinculoDeItem, vinculoDeResultado, vinculoDeSugestao, normalizaData, mostraData, confirmarApagar, algumaMarca, marca};
})();
