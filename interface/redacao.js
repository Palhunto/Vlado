'use strict';
// Phase 08 screens on the evidence boards (CONTRATO_EVIDENCIA §5.9): the story text with each claim
// highlighted by its state, the support and overstatement panel, the human review button, and the
// interview/request preparation (gaps, questions, linked follow-up, answers, Markdown export).
// Tabs register in window.Quadros (quadros.js, phase 06) and reuse its helpers. Source and user text
// enter as text nodes marked translate="no". Human review: only an explicit action of an
// authenticated account; nothing is preselected, nothing is approved automatically, and the
// server refuses it in local mode (no account) anyway.
(() => {
  const iniciar = () => {
    const Q = window.Quadros;
    if (!Q || typeof Q.registrarAba !== 'function') return;  // older page without the boards
    const {t} = Q;
    const ESTADOS = {sem_suporte: 'Sem suporte', suporte_parcial: 'Suporte parcial', suportada: 'Suportada',
      revisada_por_humano: 'Revisada por pessoa'};
    const DECISOES = {conferida_no_original: 'Conferida no original', precisa_de_ajuste: 'Precisa de ajuste',
      sem_suporte_suficiente: 'Sem suporte suficiente'};
    const SINAIS = {numero_divergente: 'Número ou data diferente da fonte', quantificador_mais_forte: 'Quantificador mais forte que a fonte',
      causalidade_sem_suporte: 'Causalidade sem suporte', certeza_sem_atribuicao: 'Certeza onde a fonte só atribui'};
    const TIPOS = {entrevista: 'Entrevista', pedido_informacao: 'Pedido de informação', pedido_lai: 'Pedido via LAI'};
    const SITUACOES = {aberta: 'Aberta', respondida: 'Respondida', parcial: 'Respondida em parte', sem_resposta: 'Sem resposta'};
    const ORIGENS = {registrada: 'Lacuna registrada por pessoa', automatica: 'Lacuna apontada pelo quadro',
      afirmacao_sem_suporte: 'Afirmação sem suporte no texto'};
    const comConta = () => document.body.dataset.modo !== 'local';
    const celular = () => !!window.matchMedia?.('(max-width: 1050px)').matches;
    const rid = () => window.crypto.randomUUID().replace(/-/g, '').slice(0, 32);
    const opcoes = (mapa, vazio) => {
      const campo = element('select');
      campo.append(new Option(t(vazio), ''), ...Object.entries(mapa).map(([valor, rotulo]) => new Option(t(rotulo), valor)));
      return campo;
    };
    const rotulado = (rotulo, controle) => { const l = element('label'); l.append(element('span', t(rotulo)), controle); return l; };
    const aviso = (alvo, texto, erro = false) => {
      alvo.textContent = texto || ''; alvo.className = erro ? 'notice' : 'small'; alvo.setAttribute('role', erro ? 'alert' : 'status');
    };

    // --- Item 8: claim-by-claim review of the story text ------------------------------------
    function textoMarcado(visao, escolher) {
      const corpo = element('div', undefined, 'redacao-texto');
      corpo.setAttribute('translate', 'no');
      let pos = 0;
      for (const a of [...visao.afirmacoes].sort((x, y) => x.inicio - y.inicio)) {
        if (a.inicio > pos) corpo.append(visao.texto.slice(pos, a.inicio));
        const trecho = element('button', visao.texto.slice(a.inicio, a.fim), `redacao-afirmacao estado-${a.estado}`);
        trecho.type = 'button'; trecho.dataset.afirmacao = a.id; trecho.dataset.estado = a.estado;
        trecho.setAttribute('aria-label', `${t(ESTADOS[a.estado] || a.estado)}${a.sinais.length ? ` · ${t('{n} sinais', {n: a.sinais.length})}` : ''}: ${a.texto}`);
        trecho.addEventListener('click', () => escolher(a, trecho));
        corpo.append(trecho);
        pos = Math.max(pos, a.fim);
      }
      if (pos < visao.texto.length) corpo.append(visao.texto.slice(pos));
      return corpo;
    }
    function legenda() {
      const lista = element('ul', undefined, 'redacao-legenda small');
      lista.setAttribute('aria-label', t('Legenda dos estados'));
      for (const [estado, rotulo] of Object.entries(ESTADOS)) {
        const item = element('li', undefined, `estado-${estado}`); item.append(element('span', t(rotulo))); lista.append(item);
      }
      return lista;
    }
    function formRevisao(casoId, visao, a, recarregar) {
      const caixa = element('div', undefined, 'redacao-revisao');
      if (a.revisao_humana) {
        const r = a.revisao_humana;
        caixa.append(element('p', t('Revisão humana: {decisao}', {decisao: t(DECISOES[r.decisao] || r.decisao)}), 'redacao-revisada'),
          Q.dado('p', `${r.responsavel} · ${new Date(r.em_utc).toLocaleString()}`, 'small'));
        if (r.observacao) caixa.append(Q.dado('p', r.observacao, 'small'));
      } else caixa.append(element('p', t('Esta afirmação ainda não tem revisão humana.'), 'small'));
      if (!comConta()) {
        caixa.append(element('p', t('A revisão humana exige uma conta autenticada da Mesa. Neste modo local ela não pode ser registrada.'), 'notice'));
        return caixa;
      }
      const abrir = Q.botao(t('Registrar revisão humana'));
      const form = element('form', undefined, 'redacao-form'); form.hidden = true;
      const decisao = opcoes(DECISOES, 'Escolha a sua decisão'); decisao.required = true;
      const obs = element('textarea'); obs.maxLength = 500; obs.rows = 3;
      const enviar = element('button', t('Registrar minha revisão')); enviar.type = 'submit'; enviar.disabled = true;
      const retorno = element('p', '', 'small');
      decisao.addEventListener('change', () => { enviar.disabled = !decisao.value; });
      form.append(rotulado('Decisão', decisao), rotulado('Observação (opcional)', obs), enviar, retorno);
      abrir.setAttribute('aria-expanded', 'false');
      abrir.addEventListener('click', () => { form.hidden = !form.hidden; abrir.setAttribute('aria-expanded', String(!form.hidden)); if (!form.hidden) decisao.focus(); });
      form.addEventListener('submit', async evento => {
        evento.preventDefault();
        if (!decisao.value) { aviso(retorno, t('Escolha a sua decisão antes de registrar.'), true); return; }
        enviar.disabled = true; aviso(retorno, t('Registrando…'));
        try {
          const nova = await api('redacao-revisar', {caso: casoId, requisicao_id: rid(), autor: '', id: visao.id,
            anterior_sha256: visao.sha256, afirmacao_id: a.id, decisao: decisao.value, observacao_revisao: obs.value});
          recarregar(nova, a.id);
        } catch (erro) { aviso(retorno, erro.message, true); enviar.disabled = false; }
      });
      caixa.append(abrir, form);
      return caixa;
    }
    function painelAfirmacao(casoId, visao, a, recarregar) {
      const painel = element('section', undefined, 'redacao-painel');
      painel.tabIndex = -1;
      const titulo = element('h4', t('Afirmação selecionada')); titulo.id = `redacao-painel-${a.id}`;
      painel.setAttribute('aria-labelledby', titulo.id);
      painel.append(titulo, Q.dado('blockquote', a.texto));
      const meta = element('p', undefined, 'quadro-selos small');
      meta.append(element('span', t(ESTADOS[a.estado] || a.estado), `quadro-selo estado-${a.estado}`));
      if (a.estado === 'revisada_por_humano')
        meta.append(element('span', t('Estado automático: {estado}', {estado: t(ESTADOS[a.estado_automatico] || a.estado_automatico)}), 'quadro-selo'));
      if (a.reaberta) meta.append(element('span', t('Reaberta após mudança'), 'quadro-selo'));
      painel.append(meta);
      const sinais = element('section', undefined, 'redacao-sinais');
      sinais.append(element('h5', t('Sinais de exagero ({n})', {n: a.sinais.length})));
      if (a.sinais.length) {
        const lista = element('ul', undefined, 'quadro-lista');
        for (const s of a.sinais) {
          const li = element('li', undefined, `redacao-sinal sinal-${s.tipo}`);
          li.append(element('strong', t(SINAIS[s.tipo] || s.tipo)));
          if (s.trecho) li.append(' ', Q.dado('span', `“${s.trecho}”`));
          lista.append(li);
        }
        sinais.append(lista, element('p', t('Sinais são regras fixas para conferência humana; não julgam o texto.'), 'small'));
      } else sinais.append(element('p', t('Nenhum sinal de exagero em relação às evidências de suporte.'), 'small'));
      const suporte = element('section', undefined, 'redacao-suporte');
      suporte.append(element('h5', t('Evidências vinculadas ({n})', {n: a.evidencias.length})));
      const lista = element('ul', undefined, 'quadro-lista');
      for (const v of a.evidencias) lista.append(Q.evidencia(casoId, v));
      if (!a.evidencias.length) lista.append(element('li', t('Nenhuma evidência vinculada a esta afirmação.'), 'small quadro-vazio'));
      suporte.append(lista);
      painel.append(sinais, suporte, formRevisao(casoId, visao, a, recarregar));
      return painel;
    }
    function conferencia(painel, casoId, visao, focoInicial) {
      const lado = element('div', undefined, 'redacao-detalhe');
      const vazio = element('p', t('Escolha uma afirmação no texto para ver o suporte e os sinais.'), 'small redacao-dica');
      lado.append(vazio);
      const recarregar = (nova, foco) => conferencia(painel, casoId, nova, foco);
      const escolher = a => {
        for (const b of painel.querySelectorAll('.redacao-afirmacao')) b.setAttribute('aria-pressed', String(b.dataset.afirmacao === a.id));
        const detalhe = painelAfirmacao(casoId, visao, a, recarregar);
        lado.replaceChildren(detalhe);
        if (celular()) { detalhe.focus(); detalhe.scrollIntoView?.(); }  // on phones the panel sits below the text
      };
      const cabeca = element('header', undefined, 'redacao-cabeca');
      const voltar = Q.botao(t('Todos os textos')); voltar.addEventListener('click', () => lista(painel, casoId));
      const r = visao.resumo.por_estado;
      cabeca.append(voltar, Q.dado('h3', visao.titulo),
        element('p', t('Versão {versao} · {total} afirmações · {sem} sem suporte · {parcial} parciais · {suportadas} suportadas · {revisadas} revisadas por pessoa',
          {versao: visao.versao, total: visao.resumo.total, sem: r.sem_suporte, parcial: r.suporte_parcial, suportadas: r.suportada,
            revisadas: r.revisada_por_humano}), 'small'));
      const grade = element('div', undefined, 'redacao-grade');
      grade.append(textoMarcado(visao, escolher), lado);
      painel.replaceChildren(cabeca, element('p', t(visao.aviso), 'small quadro-aviso'), legenda(), grade);
      const alvo = focoInicial && visao.afirmacoes.find(a => a.id === focoInicial);
      if (alvo) escolher(alvo);
    }
    function formNovo(painel, casoId) {
      const form = element('form', undefined, 'redacao-form');
      const titulo = element('input'); titulo.required = true; titulo.maxLength = 300;
      const texto = element('textarea'); texto.required = true; texto.rows = 8; texto.maxLength = 50000;
      const autor = element('input'); autor.maxLength = 120;
      const enviar = element('button', t('Conferir este texto')); enviar.type = 'submit';
      const retorno = element('p', '', 'small');
      form.append(element('h4', t('Novo texto para conferir')), rotulado('Título', titulo), rotulado('Texto da reportagem', texto));
      if (!comConta()) { autor.required = true; form.append(rotulado('Seu nome', autor)); }
      form.append(enviar, retorno);
      form.addEventListener('submit', async evento => {
        evento.preventDefault(); enviar.disabled = true; aviso(retorno, t('Dividindo o texto em afirmações…'));
        try {
          const visao = await api('redacao-criar', {caso: casoId, requisicao_id: rid(), autor: autor.value, titulo: titulo.value, texto: texto.value});
          conferencia(painel, casoId, visao);
        } catch (erro) { aviso(retorno, erro.message, true); enviar.disabled = false; }
      });
      return form;
    }
    async function lista(painel, casoId, vigente = () => true) {
      const dados = await api('redacao-listar', {caso: casoId});
      if (!vigente()) return;
      const corpo = [];
      if (dados.textos.length) {
        const ul = element('ul', undefined, 'quadro-lista redacao-textos');
        for (const item of dados.textos) {
          const li = element('li'), abrir = Q.botao(item.titulo);
          abrir.setAttribute('translate', 'no');
          abrir.addEventListener('click', async () => {
            Q.estado(painel, 'carregando', t('Carregando…'));
            try { conferencia(painel, casoId, await api('redacao-conferir', {caso: casoId, id: item.id})); }
            catch (erro) { Q.estado(painel, 'erro', erro.message); }
          });
          li.append(abrir, element('p', t('Versão {versao} · {total} afirmações', {versao: item.versao, total: item.resumo.total}), 'small'));
          ul.append(li);
        }
        corpo.push(ul);
      } else corpo.push(Q.estado(element('div'), 'vazio', t('Nenhum texto em conferência nesta apuração.')));
      if (dados.divergentes?.length) corpo.push(element('p', t('{n} registros com histórico divergente ficaram de fora.', {n: dados.divergentes.length}), 'notice'));
      painel.replaceChildren(...corpo, formNovo(painel, casoId));
    }
    Q.registrarAba({id: 'redacao', rotulo: t('Conferência do texto'), carregar: Q.quadro('conferencia_redacao', lista)});

    // --- Item 9: interviews and information requests -----------------------------------------
    function formPreparar(casoId, lacuna, recarregar) {
      const form = element('form', undefined, 'redacao-form'); form.hidden = true;
      const tipo = opcoes(TIPOS, 'Escolha o tipo de contato'); tipo.required = true;
      const destinatario = element('input'); destinatario.required = true; destinatario.maxLength = 200;
      const responsavel = element('input'); responsavel.required = true; responsavel.maxLength = 120;
      const prazo = element('input'); prazo.type = 'date';
      const autor = element('input'); autor.maxLength = 120;
      const enviar = element('button', t('Preparar pergunta')); enviar.type = 'submit';
      const retorno = element('p', '', 'small');
      form.append(rotulado('Tipo de contato', tipo), rotulado('Destinatário', destinatario), rotulado('Responsável pelo contato', responsavel),
        rotulado('Prazo (opcional)', prazo));
      if (!comConta()) { autor.required = true; form.append(rotulado('Seu nome', autor)); }
      form.append(enviar, retorno);
      form.addEventListener('submit', async evento => {
        evento.preventDefault(); enviar.disabled = true; aviso(retorno, t('Preparando…'));
        try {
          await api('entrevistas-preparar', {caso: casoId, requisicao_id: rid(), autor: autor.value || responsavel.value, origem: lacuna.origem,
            tipo: tipo.value, destinatario: destinatario.value, responsavel: responsavel.value, prazo: prazo.value || null});
          recarregar();
        } catch (erro) { aviso(retorno, erro.message, true); enviar.disabled = false; }
      });
      return form;
    }
    function itemLacuna(casoId, lacuna, recarregar) {
      const li = element('li', undefined, 'quadro-lacuna');
      li.append(Q.dado('p', lacuna.motivo.lacuna), element('p', t(ORIGENS[lacuna.motivo.origem_lacuna] || lacuna.motivo.origem_lacuna), 'small'),
        Q.dado('p', lacuna.motivo.contexto, 'small'),
        element('p', t('{n} evidências motivam esta lacuna', {n: lacuna.evidencias.length}), 'small'));
      if (lacuna.pergunta_id) li.append(element('p', t('Pergunta preparada · {situacao}', {situacao: t(SITUACOES[lacuna.situacao] || lacuna.situacao)}), 'quadro-selo'));
      else {
        const form = formPreparar(casoId, lacuna, recarregar), abrir = Q.botao(t('Preparar pergunta'));
        abrir.setAttribute('aria-expanded', 'false');
        abrir.addEventListener('click', () => { form.hidden = !form.hidden; abrir.setAttribute('aria-expanded', String(!form.hidden)); });
        li.append(abrir, form);
      }
      return li;
    }
    function formResposta(casoId, pergunta, recarregar) {
      const form = element('form', undefined, 'redacao-form'); form.hidden = true;
      const situacao = opcoes({respondida: SITUACOES.respondida, parcial: SITUACOES.parcial, sem_resposta: SITUACOES.sem_resposta}, 'Escolha a situação');
      situacao.required = true;
      const fonte = element('fieldset', undefined, 'redacao-fonte');
      const documento = element('select'), localizador = element('input'), trecho = element('textarea'), pagina = element('input');
      const manual = element('input'); manual.type = 'checkbox';
      pagina.type = 'number'; pagina.min = '1'; trecho.rows = 4; localizador.maxLength = 300;
      const marca = element('label', undefined, 'tempo-opcao'); marca.append(manual, element('span', t('Transcrição manual conferida no original')));
      fonte.append(element('legend', t('Trecho do documento da resposta')), rotulado('Documento já cadastrado', documento),
        rotulado('Página do PDF (se for PDF)', pagina), rotulado('Localização no documento', localizador), rotulado('Trecho', trecho), marca);
      fonte.hidden = true;
      const obs = element('textarea'); obs.rows = 2; obs.maxLength = 2000;
      const autor = element('input'); autor.maxLength = 120;
      const enviar = element('button', t('Registrar resposta')); enviar.type = 'submit';
      const retorno = element('p', '', 'small');
      let origem = null;
      situacao.addEventListener('change', async () => {
        fonte.hidden = !['respondida', 'parcial'].includes(situacao.value);
        if (!fonte.hidden && !origem) {
          try {
            const docs = await api('caderno-documentos', {caso: casoId});
            origem = docs.origem_id;
            documento.replaceChildren(new Option(t('Escolha o documento'), ''),
              ...docs.documentos.map(d => new Option(d.nome_recebido, `${d.documento_id}|${d.sha256}`)));
          } catch (erro) { aviso(retorno, erro.message, true); }
        }
      });
      form.append(rotulado('Situação da resposta', situacao), fonte, rotulado('Observação (opcional)', obs));
      if (!comConta()) { autor.required = true; form.append(rotulado('Seu nome', autor)); }
      form.append(enviar, retorno);
      form.addEventListener('submit', async evento => {
        evento.preventDefault();
        if (!situacao.value) { aviso(retorno, t('Escolha a situação da resposta.'), true); return; }
        const pedido = {caso: casoId, requisicao_id: rid(), autor: autor.value, id: pergunta.id, anterior_sha256: pergunta.sha256,
          situacao: situacao.value, observacao_resposta: obs.value};
        if (!fonte.hidden) {
          const [documento_id, documento_sha256] = documento.value.split('|');
          pedido.resposta = {origem_id: origem, documento_id, documento_sha256, pagina_pdf: pagina.value ? Number(pagina.value) : null,
            localizador: localizador.value, trecho: trecho.value, transcricao_manual: !!manual.checked};
        }
        enviar.disabled = true; aviso(retorno, t('Registrando…'));
        try { await api('entrevistas-responder', pedido); recarregar(); }
        catch (erro) { aviso(retorno, erro.message, true); enviar.disabled = false; }
      });
      return form;
    }
    function itemPergunta(casoId, p, selecionadas, recarregar) {
      const li = element('li', undefined, 'redacao-pergunta');
      li.dataset.pergunta = p.id;
      const marcar = element('input'); marcar.type = 'checkbox'; marcar.value = p.id;
      marcar.addEventListener('change', () => { if (marcar.checked) selecionadas.add(p.id); else selecionadas.delete(p.id); });
      const escolha = element('label', undefined, 'tempo-opcao'); escolha.append(marcar, element('span', t('Incluir na exportação')));
      const d = p.diligencia;
      li.append(Q.dado('h4', p.pergunta),
        element('p', t('Situação: {situacao}', {situacao: t(SITUACOES[p.situacao] || p.situacao)}), `quadro-selo situacao-${p.situacao}`));
      if (d.disponivel) {
        const contato = element('p', undefined, 'small');
        contato.append(element('span', `${t(TIPOS[d.tipo] || 'Diligência')} · `), Q.dado('span', d.destinatario || ''),
          element('span', ` · ${d.prazo ? t('prazo {prazo}', {prazo: d.prazo}) : t('sem prazo')}`));
        li.append(contato);
      } else li.append(element('p', t('Diligência indisponível: {erro}', {erro: d.erro}), 'notice'));
      li.append(Q.dado('p', p.motivo.lacuna, 'small'));
      if (p.evidencias.length) {
        const ev = element('details'); ev.append(element('summary', t('Evidências que motivam a pergunta ({n})', {n: p.evidencias.length})));
        const lista = element('ul', undefined, 'quadro-lista'); for (const v of p.evidencias) lista.append(Q.evidencia(casoId, v));
        ev.append(lista); li.append(ev);
      }
      for (const r of p.respostas) {
        const caixa = element('div', undefined, 'redacao-resposta');
        caixa.append(element('p', t('Resposta: {situacao}', {situacao: t(SITUACOES[r.situacao] || r.situacao)}), 'small'));
        if (r.observacao) caixa.append(Q.dado('p', r.observacao, 'small'));
        if (r.fonte) caixa.append(Q.evidencia(casoId, {referencia: r.referencia, estado: r.fonte.estado, evidencia: r.fonte.evidencia,
          erro: r.fonte.erro, suporte: 'nao_revisado', natureza: 'pendencia', localizador: r.fonte.evidencia?.localizador || {}}, 'div'));
        li.append(caixa);
      }
      const form = formResposta(casoId, p, recarregar), abrir = Q.botao(t('Registrar resposta recebida'));
      abrir.setAttribute('aria-expanded', 'false');
      abrir.addEventListener('click', () => { form.hidden = !form.hidden; abrir.setAttribute('aria-expanded', String(!form.hidden)); });
      li.append(escolha, abrir, form);
      return li;
    }
    function exportacao(casoId, selecionadas) {
      const caixa = element('section', undefined, 'redacao-exportar');
      const retorno = element('p', '', 'small'), saida = element('pre', '', 'redacao-markdown'); saida.hidden = true;
      saida.setAttribute('translate', 'no');
      const link = element('a', t('Baixar o arquivo Markdown')); link.hidden = true;
      const exportar = async formato => {
        if (!selecionadas.size) { aviso(retorno, t('Marque ao menos uma pergunta para exportar.'), true); return; }
        try {
          const dados = await api('entrevistas-exportar', {caso: casoId, ids: [...selecionadas], formato});
          saida.textContent = dados.markdown; saida.hidden = false;
          link.href = URL.createObjectURL(new Blob([dados.markdown], {type: 'text/markdown'})); link.download = dados.nome_arquivo; link.hidden = false;
          aviso(retorno, formato === 'pauta' ? t('Pauta interna gerada: não envie à fonte.') : t('Pedido gerado só com as perguntas.'));
        } catch (erro) { aviso(retorno, erro.message, true); }
      };
      const pauta = Q.botao(t('Exportar pauta interna')), pedido = Q.botao(t('Exportar texto do pedido'));
      pauta.addEventListener('click', () => exportar('pauta')); pedido.addEventListener('click', () => exportar('pedido'));
      caixa.append(element('h4', t('Exportar em Markdown')), pauta, pedido, retorno, link, saida);
      return caixa;
    }
    async function entrevistas(painel, casoId, vigente = () => true) {
      const [lacunas, perguntas] = await Promise.all([api('entrevistas-lacunas', {caso: casoId}), api('entrevistas-listar', {caso: casoId})]);
      if (!vigente()) return;
      const recarregar = () => entrevistas(painel, casoId);
      const blocoLacunas = element('section', undefined, 'redacao-lacunas');
      blocoLacunas.append(element('h3', t('Lacunas ({n})', {n: lacunas.lacunas.length})), element('p', t(lacunas.aviso), 'small quadro-aviso'));
      const ul = element('ul', undefined, 'quadro-lista');
      for (const l of lacunas.lacunas) ul.append(itemLacuna(casoId, l, recarregar));
      if (!lacunas.lacunas.length) ul.append(element('li', t('Nenhuma lacuna aberta nesta apuração.'), 'small quadro-vazio'));
      blocoLacunas.append(ul);
      const selecionadas = new Set();
      const blocoPerguntas = element('section', undefined, 'redacao-perguntas');
      blocoPerguntas.append(element('h3', t('Perguntas e pedidos ({n})', {n: perguntas.perguntas.length})));
      const lista = element('ul', undefined, 'quadro-lista');
      for (const p of perguntas.perguntas) lista.append(itemPergunta(casoId, p, selecionadas, recarregar));
      if (!perguntas.perguntas.length) lista.append(element('li', t('Nenhuma pergunta preparada ainda.'), 'small quadro-vazio'));
      blocoPerguntas.append(lista);
      if (perguntas.perguntas.length) blocoPerguntas.append(exportacao(casoId, selecionadas));
      painel.replaceChildren(blocoLacunas, blocoPerguntas);
    }
    Q.registrarAba({id: 'entrevistas', rotulo: t('Entrevistas e pedidos'), carregar: Q.quadro('entrevistas', entrevistas)});
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar);
  else iniciar();
})();
