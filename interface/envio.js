'use strict';
// Envio de arquivos com progresso por arquivo (docs/design/componentes.md#documentos, W02 regras 2, 3, 5, 6 e 8; UX-05, W11 regra 3).
//
//   const resultado = await Envio.enviar({escopo, arquivos, alvo});
//
// `escopo` são as opções de /api/cadastrar sem os arquivos ({novo, caso, titulo, natureza, ...}); `arquivos` são os File escolhidos; `alvo` é
// o elemento onde o cartão de envio aparece. Cada arquivo tem a própria barra e o próprio resultado, e a falha de um não derruba os outros.
// O envio usa o formato em fluxo da Mesa (application/vnd.vlado.lote: uma linha de manifesto JSON e os bytes crus, em um Blob), com
// "assincrono": a barra do envio é a dos bytes enviados; depois, o estado da fila (GET /api/fila?lote=) dá a etapa de leitura de cada arquivo.
// Um lote tem até 50 MB somados e 100 arquivos: mais que isso vira mais de um lote, enviados em sequência. Arquivo maior que 50 MB, ou com
// nome que a Mesa não aceita, é recusado antes do envio, sem derrubar os demais.
// Resolve com {caso_id, lotes, enviados, recebidos, novos, duplicados, pendentes, recusados, cancelado}.
(() => {
  const t = (pt, vars) => (window.I18N ? window.I18N.t(pt, vars) : String(pt).replace(/\{(\w+)\}/g, (todo, nome) => vars?.[nome] ?? todo));
  const LIMITE_LOTE = 50 * 1024 * 1024, LIMITE_ARQUIVOS = 100, INTERVALO_FILA = 1500;
  const NOME_RUIM = /[\\/:*?"<>|\x00-\x1f]/;
  const RESERVADO = /^(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?$/i;
  const TIPO_LOTE = 'application/vnd.vlado.lote';
  let sequencia = 0;
  const sessao = () => document.querySelector('meta[name="session-token"]')?.getAttribute('content') || '';
  const esperar = ms => new Promise(resolver => setTimeout(resolver, ms));

  function no(etiqueta, classe, texto) {
    const elemento = document.createElement(etiqueta);
    if (classe) elemento.className = classe;
    if (texto !== undefined && texto !== null) elemento.textContent = texto;
    return elemento;
  }
  const mensagemDe = corpo => (window.I18N?.erro ? window.I18N.erro(corpo) : corpo?.erro) || t('Não foi possível completar a operação.');
  function erroDeRede() { const falha = new Error(t('Sem conexão com o servidor.')); falha.rede = true; return falha; }

  // Recusa antes do envio: a mesma regra de nomes do servidor e o teto por arquivo.
  function recusa(arquivo) {
    const nome = arquivo.name;
    if (arquivo.size > LIMITE_LOTE) return t('Passa de 50 MB. Divida o arquivo ou reduza o tamanho e envie de novo.');
    if (!nome || nome.length > 255 || NOME_RUIM.test(nome) || /[. ]$/.test(nome) || RESERVADO.test(nome)) {
      return t('O nome do arquivo tem caracteres que a Mesa não aceita. Renomeie o arquivo e envie de novo.');
    }
    return null;
  }
  // Lotes em ordem: até 50 MB somados e 100 arquivos cada.
  function planejar(linhas) {
    const lotes = [];
    let atual = [], bytes = 0;
    for (const linha of linhas) {
      if (atual.length && (bytes + linha.bytes > LIMITE_LOTE || atual.length >= LIMITE_ARQUIVOS)) { lotes.push(atual); atual = []; bytes = 0; }
      atual.push(linha); bytes += linha.bytes;
    }
    if (atual.length) lotes.push(atual);
    return lotes;
  }

  // O resultado de cada arquivo depois da leitura: sinal e texto, nunca só a cor (W02, regra 5).
  function resultadoPronto(linha) {
    const paginas = linha.paginas ? t('{n} pág.', {n: linha.paginas}) : '';
    if (linha.extracao === 'parcial') return {tom: 'aviso', sinal: 'parcial', texto: t('Lida em parte: confira as páginas sem texto no original.')};
    if (linha.extracao === 'sem_texto') return {tom: 'aviso', sinal: 'parcial', texto: t('Sem texto lido. O original ficou guardado.')};
    if (linha.extracao === 'erro') return {tom: 'erro', sinal: 'sem-suporte', semMedidor: true, ajuda: true,
      texto: linha.motivo ? mensagemDe({erro: linha.motivo}) : t('Não foi possível ler este arquivo. O original ficou guardado.')};
    if (linha.extracao === 'pendente') return {tom: 'aviso', sinal: 'parcial', texto: t('Leitura pendente. O original ficou guardado.')};
    // O texto veio do OCR: o reconhecimento automático erra números e nomes (W02, regra 5).
    if (linha.passouPorOcr) return {tom: 'aviso', sinal: 'parcial', texto: t('Lida por OCR: confira números')};
    return {tom: 'ok', texto: paginas ? `✓ ${t('Pronto, {paginas}', {paginas})}` : `✓ ${t('Pronto')}`};
  }
  function descrever(linha) {
    switch (linha.estado) {
      case 'aguardando': return {tom: 'neutro', texto: t('Aguardando a vez')};
      case 'enviando': return {tom: 'neutro', texto: t('Enviando… {pct}%', {pct: Math.round(linha.fracao * 100)})};
      case 'enfileirado': return {tom: 'neutro', texto: t('Na fila para leitura')};
      case 'extraindo': return {tom: 'neutro', texto: linha.pagina && linha.paginas ? t('Lendo pág. {n} de {m}', {n: linha.pagina, m: linha.paginas}) : t('Lendo o texto')};
      case 'ocr': return {tom: 'neutro', texto: linha.pagina && linha.paginas ? t('Lendo por OCR, pág. {n} de {m}', {n: linha.pagina, m: linha.paginas}) : t('Lendo por OCR')};
      case 'pronto': return resultadoPronto(linha);
      case 'falha': return {tom: 'erro', sinal: 'sem-suporte', semMedidor: true, texto: linha.motivo ? mensagemDe({erro: linha.motivo}) : t('A leitura parou. O original foi cadastrado e a falha está no recibo.'), ajuda: true};
      case 'recusado': return {tom: 'erro', sinal: 'sem-suporte', semMedidor: true, texto: linha.motivo, ajuda: false};
      case 'cancelado': return {tom: 'aviso', sinal: 'parcial', semMedidor: true, texto: t('Envio cancelado. Nada deste arquivo foi cadastrado.')};
      case 'sem-acompanhamento': return {tom: 'aviso', sinal: 'parcial', semMedidor: true, texto: t('Recebido. Não foi possível acompanhar a leitura; confira em Documentos.')};
      case 'nao-enviado': return {tom: 'erro', sinal: 'sem-suporte', semMedidor: true, texto: linha.motivo || t('Não foi enviado. Tente de novo.'), ajuda: false};
      default: return {tom: 'neutro', texto: ''};
    }
  }
  function fracaoDe(linha) {
    if (['pronto', 'falha'].includes(linha.estado)) return 1;
    if (linha.estado === 'enviando') return linha.fracao;
    if (['extraindo', 'ocr'].includes(linha.estado) && linha.pagina && linha.paginas) return linha.pagina / linha.paginas;
    return 0;
  }

  // O cartão de envio: título, uma linha por arquivo, recibo do lote. aria-busy enquanto houver arquivo em andamento.
  function cartao(alvo, ctx) {
    const raiz = no('div', 'envio-cartao'); raiz.dataset.estado = 'ocupado';
    const cabeca = no('div', 'envio-cabeca');
    const titulo = no('p', 'envio-titulo');
    const aviso = no('p', 'estado-nota', t('Você pode continuar trabalhando e sair desta tela.'));
    cabeca.append(titulo, aviso);
    const lista = no('ul', 'envio-lista');
    const recibo = no('div', 'envio-recibo'); recibo.hidden = true;
    const acoes = no('div', 'estado-acoes'); acoes.hidden = true;
    const anuncio = no('p', 'sr-only'); anuncio.setAttribute('role', 'status');
    raiz.append(cabeca, lista, recibo, acoes, anuncio);
    alvo.replaceChildren(raiz);
    const itens = new Map();
    let ultimoAnuncio = '';

    function linhaDe(linha) {
      let item = itens.get(linha);
      if (item) return item;
      const li = no('li', 'envio-arquivo');
      const nome = no('span', 'envio-nome', linha.nome); nome.setAttribute('translate', 'no');
      const barra = no('div', 'medidor-progresso'); barra.setAttribute('role', 'progressbar');
      barra.setAttribute('aria-valuemin', '0'); barra.setAttribute('aria-valuemax', '100'); barra.setAttribute('aria-label', t('Progresso de {nome}', {nome: linha.nome}));
      const resultado = no('span', 'envio-resultado');
      const ajuda = no('button', 'secondary envio-ajuda', t('O que fazer')); ajuda.type = 'button'; ajuda.hidden = true;
      const explicacao = no('p', 'envio-explicacao estado-texto',
        t('O original está guardado no caso. Abra o recibo para ver o que a Mesa registrou ou envie uma cópia corrigida, por exemplo sem macro e sem senha.'));
      explicacao.hidden = true; explicacao.id = `envio-explicacao-${++sequencia}`;
      ajuda.setAttribute('aria-expanded', 'false'); ajuda.setAttribute('aria-controls', explicacao.id);
      ajuda.addEventListener('click', () => { explicacao.hidden = !explicacao.hidden; ajuda.setAttribute('aria-expanded', String(!explicacao.hidden)); });
      li.append(nome, barra, resultado, ajuda, explicacao);
      lista.append(li);
      item = {li, barra, resultado, ajuda, explicacao};
      itens.set(linha, item);
      return item;
    }
    function desenhar() {
      const linhas = ctx.linhas;
      const ativos = linhas.filter(l => ['aguardando', 'enviando', 'enfileirado', 'extraindo', 'ocr'].includes(l.estado)).length;
      raiz.setAttribute('aria-busy', String(ativos > 0));
      raiz.dataset.estado = ativos ? 'ocupado' : 'concluido';
      titulo.textContent = ativos ? t('Enviando {n} arquivos', {n: linhas.length}) : t('Envio de {n} arquivos', {n: linhas.length});
      if (linhas.length === 1) titulo.textContent = ativos ? t('Enviando 1 arquivo') : t('Envio de 1 arquivo');
      aviso.hidden = !ativos;
      for (const linha of linhas) {
        const item = linhaDe(linha), situacao = descrever(linha);
        const pct = Math.round(fracaoDe(linha) * 100);
        item.barra.style.setProperty('--uso', `${pct}%`); item.barra.setAttribute('aria-valuenow', String(pct));
        item.li.dataset.estado = linha.estado; item.resultado.dataset.tom = situacao.tom;
        // Linha que falhou não tem medidor: o texto do erro ocupa o lugar da barra (a barra cheia leria como sucesso).
        item.barra.hidden = !!situacao.semMedidor; item.li.dataset.falha = String(!!situacao.semMedidor);
        const partes = [];
        if (situacao.sinal) partes.push(window.Estados.sinal(situacao.sinal));
        partes.push(situacao.texto);
        item.resultado.replaceChildren(...partes);
        item.ajuda.hidden = !situacao.ajuda;
        if (!situacao.ajuda) item.explicacao.hidden = true;
      }
      // Só as mudanças de estado são anunciadas, não cada passo da barra.
      const resumo = `${linhas.filter(l => ['pronto', 'falha', 'recusado', 'cancelado', 'nao-enviado', 'sem-acompanhamento'].includes(l.estado)).length}/${linhas.length}`;
      if (resumo !== ultimoAnuncio) {
        ultimoAnuncio = resumo;
        anuncio.textContent = t('{feitos} de {total} arquivos concluídos.', {feitos: resumo.split('/')[0], total: linhas.length});
      }
    }
    function mostrarRecibo(resumo) {
      recibo.hidden = !resumo;
      if (!resumo) return;
      const forte = no('strong', '', t('{n} de {total} cadastrados', {n: resumo.recebidos, total: resumo.total}));
      const partes = [];
      if (resumo.naoCadastrados) partes.push(resumo.naoCadastrados === 1 ? t('1 não cadastrado') : t('{n} não cadastrados', {n: resumo.naoCadastrados}));
      if (resumo.aConferir) partes.push(resumo.aConferir === 1 ? t('1 com leitura a conferir') : t('{n} com leitura a conferir', {n: resumo.aConferir}));
      const pendentes = partes.length ? `, ${partes.join(', ')}` : '';
      const texto = no('span');
      texto.append(`${t('Recibo do lote')}: `, forte, `${pendentes}. ${t('É conferido antes da primeira pergunta.')}`);
      const ver = no('a', 'envio-link', t('Ver recibo')); ver.href = '#cadastro-recibo';
      ver.addEventListener('click', evento => { evento.preventDefault(); ctx.aoVerRecibo?.(); window.dispatchEvent(new Event('envio-recibo-visto')); });
      recibo.replaceChildren(texto, ver);
    }
    function mostrarAcoes(lista_) {
      acoes.replaceChildren(...lista_.map(({rotulo, aoClicar, principal}) => {
        const botao = no('button', principal ? '' : 'secondary', rotulo); botao.type = 'button'; botao.addEventListener('click', aoClicar); return botao;
      }));
      acoes.hidden = !lista_.length;
    }
    return {desenhar, mostrarRecibo, mostrarAcoes};
  }

  // Um lote em uma requisição: o progresso de envio sai do próprio XMLHttpRequest, em bytes, e é repartido entre os arquivos na ordem.
  function postarLote(corpoManifesto, linhas, ctx) {
    const linhaManifesto = new TextEncoder().encode(`${JSON.stringify(corpoManifesto)}\n`);
    const arquivos = linhas.map(l => l.arquivo);
    return new Promise((resolver, rejeitar) => {
      const pedido = new XMLHttpRequest();
      ctx.cancelarEnvio = () => pedido.abort();
      pedido.open('POST', '/api/cadastrar');
      pedido.setRequestHeader('Content-Type', TIPO_LOTE);
      pedido.setRequestHeader('X-Session-Token', sessao());
      pedido.upload.addEventListener('progress', evento => {
        // O corpo é a linha do manifesto e depois os arquivos, em ordem: os bytes enviados dizem até onde cada um foi.
        let enviados = Math.max(0, evento.loaded - linhaManifesto.length);
        for (const linha of linhas) {
          const parte = Math.min(Math.max(enviados, 0), linha.bytes);
          linha.fracao = linha.bytes ? parte / linha.bytes : 1; enviados -= linha.bytes;
        }
        ctx.redesenhar();
      });
      pedido.addEventListener('load', () => {
        let corpo = {};
        try { corpo = JSON.parse(pedido.responseText || '{}'); } catch { /* corpo vazio ou não JSON */ }
        if (pedido.status >= 200 && pedido.status < 300 && corpo.lote) { resolver(corpo.lote); return; }
        const falha = new Error(pedido.status === 429 || pedido.status === 503
          ? t('A Mesa está atendendo muitos envios agora. Aguarde alguns segundos e tente de novo.')
          : mensagemDe(corpo));
        falha.status = pedido.status; falha.corpo = corpo; falha.codigo = corpo?.codigo; rejeitar(falha);
      });
      pedido.addEventListener('error', () => rejeitar(erroDeRede()));
      pedido.addEventListener('abort', () => { const falha = new Error('abortado'); falha.abortado = true; rejeitar(falha); });
      pedido.send(new Blob([linhaManifesto, ...arquivos]));
    });
  }
  async function consultarLote(id) {
    let resposta;
    try { resposta = await fetch(`/api/fila?lote=${encodeURIComponent(id)}`, {headers: {'X-Session-Token': sessao()}}); }
    catch { throw erroDeRede(); }
    let corpo = {};
    try { corpo = await resposta.json(); } catch { /* sem corpo */ }
    if (!resposta.ok) throw new Error(mensagemDe(corpo));
    return corpo.lote;
  }
  function aplicarEstado(linhas, lote) {
    for (const arquivo of lote.arquivos || []) {
      const linha = linhas[arquivo.indice];
      if (!linha) continue;
      Object.assign(linha, {estado: arquivo.estado, pagina: arquivo.pagina, paginas: arquivo.paginas, extracao: arquivo.extracao, motivo: arquivo.motivo});
      if (arquivo.estado === 'ocr' || ['orientacao', 'reconhecimento'].includes(arquivo.etapa)) linha.passouPorOcr = true;
    }
  }

  async function enviar({escopo, arquivos, alvo, alvoRecibo, aoCriar, aoTerminar}) {
    const ctx = {linhas: [], cancelado: false, cancelarEnvio: null, redesenhar: () => ui.desenhar(), aoVerRecibo: null};
    ctx.linhas = Array.from(arquivos).map(arquivo => ({arquivo, nome: arquivo.name, bytes: arquivo.size, estado: 'aguardando', fracao: 0}));
    for (const linha of ctx.linhas) {
      const motivo = recusa(linha.arquivo);
      if (motivo) { linha.estado = 'recusado'; linha.motivo = motivo; }
    }
    const ui = cartao(alvo, ctx);
    // Apuração nova: o primeiro lote vai com `novo: true` e SEM `caso`, porque o servidor escolhe o identificador (contrato de contas, 4.4); o `caso_id`
    // da resposta vale para os lotes seguintes. Uma apuração que já existe traz o `caso` desde o início.
    const resultado = {caso_id: escopo.caso ?? null, lotes: [], enviados: 0, recebidos: 0, novos: 0, duplicados: 0, pendentes: 0, avisos: [], recusados: ctx.linhas.filter(l => l.estado === 'recusado').length, cancelado: false};
    ui.desenhar();

    let casoAceito = null;   // o identificador que o servidor escolheu para a apuração nova, assim que aceita o primeiro lote
    const lotesPlanejados = planejar(ctx.linhas.filter(l => l.estado === 'aguardando'));
    const fazer = async lotes => {
      for (const linhas of lotes) {
        if (ctx.cancelado) break;
        for (const linha of linhas) { linha.estado = 'enviando'; linha.fracao = 0; }
        ui.mostrarAcoes([{rotulo: t('Cancelar envio'), aoClicar: () => { ctx.cancelado = true; ctx.cancelarEnvio?.(); }}]);
        ui.desenhar();
        // O primeiro lote cria a apuração nova; os seguintes entram nela, com o identificador que o servidor devolveu na ACEITAÇÃO do lote (não na
        // publicação): se o primeiro for aceito e depois falhar ou sumir da fila, o segundo ainda vai ao mesmo caso, e não cria outra apuração.
        const manifesto = {...escopo, ...(resultado.lotes.length ? {novo: false} : {}), ...(casoAceito ? {novo: false, caso: casoAceito} : {}), assincrono: true,
          arquivos: linhas.map(l => ({nome: l.nome, tamanho: l.bytes}))};
        let lote;
        try {
          lote = await postarLote(manifesto, linhas, ctx);
        } catch (falha) {
          const cancelou = falha.abortado || ctx.cancelado;
          // O pedido do primeiro lote de uma apuração nova terminou em erro de rede ou 502/504: a tela não sabe se o servidor aceitou (e criou a apuração).
          // Para os lotes seguintes e avisa para conferir a Visão geral antes de enviar de novo, porque um reenvio pode criar OUTRA apuração.
          const incerto = !cancelou && !!escopo.novo && !escopo.caso && !casoAceito && (falha.rede === true || [500, 502, 504].includes(falha.status));
          // Só a recusa que diz que a apuração nova não existe (o primeiro lote não chegou a criá-la): para e avisa. Outra recusa não diz isso. O código é
          // do servidor (erros.py: caso_inexistente, "Caso inexistente; não cadastrar em outro caso automaticamente."; ou caso_indisponivel, do portão).
          const semApuracao = !cancelou && !!casoAceito && !resultado.lotes.length && [400, 404].includes(falha.status)
            && ['caso_inexistente', 'caso_indisponivel'].includes(falha.codigo);
          // N3: o primeiro lote de uma apuração nova foi aceito e depois falhou na fila; a tela já passou à apuração, e o reenvio ao caso responde "inexistente".
          const casoPerdido = !cancelou && !escopo.novo && falha.codigo === 'caso_inexistente';
          const parada = incerto ? t('Não sabemos se a apuração foi criada: a resposta do servidor não chegou. Confira a apuração na Visão geral antes de enviar de novo.')
            : semApuracao ? t('A apuração nova não foi criada: o primeiro envio não terminou. Envie de novo.')
            : casoPerdido ? t('Esta apuração não chegou a ser criada: o primeiro envio falhou. Recomece a Nova apuração.') : '';
          for (const linha of linhas) { linha.estado = cancelou ? 'cancelado' : 'nao-enviado'; linha.motivo = cancelou ? '' : parada || falha.message; }
          ui.desenhar();
          if (cancelou) { ctx.cancelado = true; break; }
          if (incerto || semApuracao || casoPerdido) {
            resultado.erro = falha; if (incerto) { resultado.incerto = true; resultado.aviso_incerto = parada; }
            for (const resto of lotes.slice(lotes.indexOf(linhas) + 1).flat()) { resto.estado = 'nao-enviado'; resto.motivo = parada; }
            ui.desenhar(); break;
          }
          resultado.erro = falha;
          continue;
        }
        ctx.cancelarEnvio = null;
        if (lote.caso) { resultado.caso_id = lote.caso; if (escopo.novo && !escopo.caso && !casoAceito) { casoAceito = lote.caso; try { await aoCriar?.(casoAceito); } catch { /* a tela que quer saber da criação não derruba o envio */ } } }   // o identificador que o servidor escolheu
        ui.mostrarAcoes([]);
        for (const linha of linhas) linha.fracao = 1;
        const dosArquivos = linhas;   // o índice do lote é a posição no manifesto
        aplicarEstado(dosArquivos, lote); ui.desenhar();
        // Depois do envio, a leitura corre no servidor; a pessoa pode sair da tela, e este laço segue enquanto a página estiver aberta.
        let atual = lote, perdido = false;
        while (!['publicado', 'falha'].includes(atual.estado)) {
          await esperar(INTERVALO_FILA);
          try { atual = await consultarLote(lote.lote); } catch (falha) {
            if (falha.rede) continue;
            perdido = true; break;   // a fila não conhece mais o lote: não dá para acompanhar, e a pessoa confere em Documentos
          }
          aplicarEstado(dosArquivos, atual); ui.desenhar();
        }
        if (perdido) {
          for (const linha of dosArquivos) { linha.estado = 'sem-acompanhamento'; }
          ui.desenhar(); continue;
        }
        if (atual.estado === 'falha') {
          for (const linha of dosArquivos) { linha.estado = 'nao-enviado'; linha.motivo = atual.motivo ? mensagemDe({erro: atual.motivo}) : t('Nada foi cadastrado. Tente de novo.'); }
          ui.desenhar();
          resultado.erro = new Error(atual.motivo || t('Nada foi cadastrado.'));
          continue;
        }
        resultado.lotes.push(atual);
        resultado.caso_id = atual.caso ?? atual.recibo?.caso_id ?? resultado.caso_id;
        // Aviso do servidor sobre a natureza dos documentos (informada diferente da apuração): vai para o recibo, como aviso e não como erro.
        const aviso = atual.recibo?.aviso_natureza;
        if (aviso && !resultado.avisos.includes(aviso)) resultado.avisos.push(aviso);
        resultado.enviados += dosArquivos.length;
        resultado.recebidos += atual.recibo?.recebidos ?? dosArquivos.length;
        resultado.novos += atual.recibo?.novos ?? 0;
        resultado.duplicados += atual.recibo?.duplicados ?? 0;
        resultado.corpus_id = atual.recibo?.corpus_id ?? resultado.corpus_id;
      }
    };
    await fazer(lotesPlanejados);
    ui.mostrarAcoes([]);
    resultado.cancelado = ctx.cancelado;
    try { aoTerminar?.(resultado); } catch { /* a tela que quer saber do fim não derruba o envio */ }
    resultado.naoCadastrados = ctx.linhas.filter(l => ['nao-enviado', 'cancelado', 'recusado', 'falha', 'sem-acompanhamento'].includes(l.estado)).length;
    resultado.aConferir = ctx.linhas.filter(l => l.estado === 'pronto' && (['erro', 'sem_texto', 'pendente', 'parcial'].includes(l.extracao) || l.passouPorOcr)).length;
    resultado.pendentes = resultado.naoCadastrados + resultado.aConferir;
    resultado.arquivos = ctx.linhas;
    ui.mostrarRecibo(resultado.enviados || resultado.recusados ? {recebidos: resultado.recebidos, total: ctx.linhas.length, naoCadastrados: resultado.naoCadastrados, aConferir: resultado.aConferir} : null);
    ctx.aoVerRecibo = () => { const detalhe = alvoRecibo || document.getElementById('cadastro-recibo'); if (detalhe && !detalhe.hidden) { detalhe.scrollIntoView({block: 'start'}); detalhe.focus?.(); } };
    ui.desenhar();
    return resultado;
  }

  // Recibo do lote em detalhe (o "Ver recibo" do cartão): só o que o cartão de envio ainda não diz, a contagem do lote e, em "Detalhes técnicos",
  // o que não é para a lista (apuração e versão, W02 regra 7). O resultado de cada arquivo já está no cartão.
  const plural = (n, um, varios, nenhum) => (n === 0 ? nenhum : n === 1 ? `1 ${um}` : `${n} ${varios}`);
  function renderRecibo(destino, resultado) {
    const tecnicos = no('details', 'estado-detalhes');
    const linhaTecnica = no('p', '', `${t('Apuração')}: ${resultado.caso_id} · ${t('Corpus')}: ${resultado.corpus_id || '—'}`); linhaTecnica.setAttribute('translate', 'no');
    tecnicos.append(no('summary', '', t('Detalhes técnicos')), linhaTecnica);
    const contagem = [plural(resultado.novos, t('novo'), t('novos'), t('nenhum novo')), plural(resultado.duplicados, t('duplicado'), t('duplicados'), t('nenhum duplicado'))].join(' · ');
    const avisos = (resultado.avisos || []).map(texto => {
      const linha = no('p', 'docs-aviso'); linha.setAttribute('role', 'status');
      linha.append(window.Estados.sinal('parcial'), t(texto));
      return linha;
    });
    destino.replaceChildren(no('h3', 'docs-recibo-titulo', t('Recibo do lote: {n} de {total} arquivos', {n: resultado.recebidos, total: resultado.arquivos.length})),
      no('p', '', contagem), ...avisos, tecnicos);
    destino.hidden = false;
  }
  // O que pede conferência antes da pergunta: leitura com erro, em parte ou sem texto.
  const comLimitacao = resultado => resultado.arquivos.some(l => l.estado === 'pronto' && ['erro', 'parcial', 'sem_texto'].includes(l.extracao));

  // O servidor anuncia o envio em fluxo em /api/integracao (envio_fluxo); um servidor mais antigo fica com o envio em JSON.
  let integracao = null;
  function disponivel() {
    integracao ||= fetch('/api/integracao').then(r => r.ok ? r.json() : {}).catch(() => ({}));
    return integracao.then(dados => dados?.envio_fluxo === true);
  }

  window.Envio = {enviar, planejar, recusa, renderRecibo, comLimitacao, disponivel, LIMITE_LOTE, LIMITE_ARQUIVOS};
})();
