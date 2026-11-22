'use strict';
// A aba Equipe (docs/design/componentes.md#equipe, W09): só para quem tem `equipe-listar`, isto é, o dono. A tabela da redação (cartões abaixo de
// 1024 px) com papel, apurações e uso do mês; "Gerenciar" abre apurações, teto mensal e acesso da pessoa; abaixo, o gasto da redação e a atividade.
// Os dados vêm de equipe-listar, equipe-atividade, caso-* e /api/catalogo. A Mesa não decide pelo nome do papel e não aceita HTML: nomes e
// e-mails entram como texto. A senha das operações sensíveis vai pelo diálogo com senha de conta.js (#dialogo-senha). "Convidar pessoa" não existe
// ainda (exceção declarada, P30): o convite por e-mail vem com a E3 de Contas.
(() => {
  if (!window.Conta) return;
  const {no, botao, dado, apoio, carregar, data, reais, rotuloPapel, estado, sensivel} = window.Conta;
  const t = (pt, vars) => (window.I18N ? window.I18N.t(pt, vars) : String(pt).replace(/\{(\w+)\}/g, (todo, nome) => vars?.[nome] ?? todo));
  const ID_CONTA = /^[0-9a-f]{16}$/;
  const PAPEIS_ESCOLHA = ['dono', 'editor', 'reporter', 'leitor'];

  let lista = null, catalogo = [], quemSou = null, aberto = new Set();
  let atividade = {eventos: [], proximo: null}, atividadePronta = false;
  const raiz = {};  // os contêineres montados
  const desktop = typeof matchMedia === 'function' ? matchMedia('(min-width:1024px)') : {matches: true, addEventListener() {}};
  let ultimoLayout = null;

  const pessoas = () => lista?.pessoas || [];
  const tituloDoCaso = id => (catalogo.find(c => c.id === id) || {titulo: id}).titulo;

  // --- montagem -----------------------------------------------------------------------------------------------------------------------------
  function montar(painel) {
    raiz.aviso = no('div', 'equipe-aviso'); raiz.aviso.hidden = true;
    raiz.tabela = no('section', 'conta-cartao conta-cartao-tabela'); raiz.tabela.setAttribute('aria-label', t('Pessoas da redação'));
    raiz.corpoTabela = no('div', 'conta-cartao-corpo'); raiz.tabela.append(raiz.corpoTabela);
    // Enquanto 'Contas de acesso' existir em Configurações (P30), é lá que o dono inclui alguém; o texto leva à aba. Com mais de uma redação o servidor
    // recusa contas-criar, mas as capacidades não dizem isso: a Mesa não distingue e mostra sempre este texto (decisão do Design).
    raiz.convite = no('p', 'conta-apoio equipe-convite');
    const [antesDoLink, depoisDoLink] = t('Para incluir alguém, crie uma conta em Configurações, {link}.').split('{link}');
    const irParaContas = botao('Contas de acesso', 'equipe-link equipe-link-texto', () => window.Conta.abrir('configuracoes'));
    raiz.convite.append(antesDoLink, irParaContas, depoisDoLink ?? '');
    raiz.gasto = window.Conta.cartao('Gasto com IA neste mês');
    raiz.atividade = window.Conta.cartao('Atividade recente', 'equipe-atividade-cartao');
    raiz.gasto.raiz.dataset.cartao = 'gasto'; raiz.atividade.raiz.dataset.cartao = 'atividade';
    const abaixo = no('div', 'conta-grade equipe-abaixo');
    abaixo.append(raiz.gasto.raiz, raiz.atividade.raiz);
    painel.append(raiz.aviso, raiz.tabela, raiz.convite, abaixo);
    desktop.addEventListener?.('change', () => { if (lista) desenharLista(); });
  }
  async function abrir() {
    quemSou = (await window.Conta.sessao())?.conta?.id || null;
    await recarregar();
    carregarAtividade();
  }
  function titulo() {
    const n = pessoas().length;
    window.Conta.titulo(lista?.redacao?.nome || t('Equipe'), n ? (n === 1 ? t('1 pessoa') : t('{n} pessoas', {n})) : '', !!lista?.redacao?.nome);
  }
  async function buscarCatalogo() {
    try {
      const resposta = await window.fetch('/api/catalogo', {headers: {Accept: 'application/json'}, credentials: 'same-origin'});
      catalogo = resposta?.ok ? ((await resposta.json())?.casos || []) : [];
    } catch (_) { catalogo = []; }
  }
  async function recarregar() {
    await carregar({corpo: raiz.corpoTabela}, async () => { const [equipe] = await Promise.all([api('equipe-listar', {}), buscarCatalogo()]); return equipe; },
      resposta => { lista = resposta; desenharLista(); desenharGasto(); titulo(); });
  }

  // --- a lista de pessoas -------------------------------------------------------------------------------------------------------------------
  function desenharLista() {
    const todas = pessoas();
    const antigos = todas.filter(p => p.papel === 'convidado').length;
    raiz.aviso.replaceChildren();
    raiz.aviso.hidden = !antigos;
    if (antigos) {
      const aviso = no('div', 'notice'); aviso.setAttribute('role', 'status');
      aviso.append(no('p', '', antigos === 1
        ? t('1 pessoa ainda tem o perfil antigo de convidado: pergunta só nas apurações liberadas e vê só as próprias conversas. Escolha um papel para ela ou remova da redação.')
        : t('{n} pessoas ainda têm o perfil antigo de convidado: perguntam só nas apurações liberadas e veem só as próprias conversas. Escolha um papel para cada uma ou remova da redação.', {n: antigos})));
      raiz.aviso.append(aviso);
    }
    ultimoLayout = desktop.matches ? 'tabela' : 'cartoes';
    raiz.corpoTabela.dataset.layout = ultimoLayout;
    raiz.corpoTabela.replaceChildren(ultimoLayout === 'tabela' ? tabela(todas) : cartoes(todas));
  }
  const ehEu = pessoa => !!quemSou && pessoa.id === quemSou;

  function celulaPessoa(pessoa) {
    const bloco = no('div', 'equipe-pessoa');
    const primeira = no('p', 'equipe-pessoa-nome');
    primeira.append(dado(pessoa.nome || '', 'span'));
    if (ehEu(pessoa)) primeira.append(' ', no('span', 'conta-apoio', t('(você)')));
    bloco.append(primeira);
    const contato = pessoa.email || (pessoa.login ? `${t('login')} ${pessoa.login}` : '');
    if (contato) { const c = no('p', 'conta-apoio', contato); c.setAttribute('translate', 'no'); bloco.append(c); }
    const situacao = pessoa.situacao === 'desativada' || pessoa.ativa === false ? '○ Desativada'
      : pessoa.situacao === 'aguardando_senha' ? (pessoa.ativacao_vencida ? '◐ Link de ativação vencido' : '◐ Aguardando a senha') : '';
    if (situacao) bloco.append(no('p', 'conta-apoio equipe-situacao', t(situacao)));
    return bloco;
  }
  function celulaPapel(pessoa) {
    if (ehEu(pessoa)) return no('span', 'conta-texto', rotuloPapel(pessoa.papel));
    const caixa = document.createElement('select'); caixa.className = 'equipe-papel';
    caixa.setAttribute('aria-label', t('Papel de {nome}', {nome: pessoa.nome || ''}));
    if (pessoa.papel === 'convidado') {
      const antigo = new Option(t('Convidado (perfil antigo)'), 'convidado'); antigo.disabled = true; caixa.append(antigo);
    }
    for (const papel of PAPEIS_ESCOLHA) caixa.append(new Option(rotuloPapel(papel), papel));
    caixa.value = pessoa.papel;
    caixa.addEventListener('change', () => mudarPapel(pessoa, caixa));
    return caixa;
  }
  function celulaApuracoes(pessoa) {
    if (pessoa.casos === null || pessoa.papel === 'dono') return no('span', 'conta-texto', t('Todas'));
    const ids = pessoa.casos || [];
    if (!ids.length) return no('span', 'conta-apoio', t('Nenhuma'));
    const visiveis = ids.slice(0, 3).map(tituloDoCaso), mais = ids.length - visiveis.length;
    const celula = no('span', 'conta-texto'); celula.append(dado(visiveis.join(', ')));
    if (mais > 0) celula.append(' ', t(mais === 1 ? 'e mais 1' : 'e mais {n}', {n: mais}));
    return celula;
  }
  function celulaUso(pessoa) {
    const bloco = no('div', 'equipe-uso');
    const gasto = pessoa.gasto;
    if (!gasto) { bloco.append(no('span', 'conta-texto', '—')); return bloco; }
    const valor = reais(gasto.gasto_brl);
    if (gasto.esgotada) bloco.append(no('span', 'equipe-uso-esgotada', `! ${valor} · ${t('esgotada')}`));
    else bloco.append(no('span', 'conta-texto', valor));
    if (pessoa.teto_mensal_brl) bloco.append(no('span', 'conta-apoio', t('teto {valor}', {valor: reais(pessoa.teto_mensal_brl, {centavos: false})})));
    return bloco;
  }
  function botaoGerenciar(pessoa) {
    if (ehEu(pessoa)) return null;
    const painelId = `equipe-gerenciar-${pessoa.id}`;
    const controle = botao('Gerenciar', 'equipe-gerenciar-botao', () => alternarGerenciar(pessoa, controle));
    controle.setAttribute('aria-expanded', String(aberto.has(pessoa.id))); controle.setAttribute('aria-controls', painelId);
    controle.setAttribute('aria-label', `${t('Gerenciar')}: ${pessoa.nome || ''}`);
    return controle;
  }
  function alternarGerenciar(pessoa, controle) {
    if (aberto.has(pessoa.id)) aberto.delete(pessoa.id); else aberto.add(pessoa.id);
    desenharLista();
    document.querySelector(`[aria-controls="equipe-gerenciar-${pessoa.id}"]`)?.focus();
  }

  function tabela(todas) {
    const quadro = document.createElement('table'); quadro.className = 'equipe-tabela';
    const cabeca = document.createElement('thead'), cabecaLinha = document.createElement('tr');
    for (const [rotulo, leitor] of [['Pessoa', false], ['Papel', false], ['Apurações', false], ['Uso no mês', false], ['Ações', true]]) {
      const th = document.createElement('th'); th.scope = 'col';
      if (leitor) th.append(no('span', 'sr-only', t(rotulo))); else th.textContent = t(rotulo);
      cabecaLinha.append(th);
    }
    cabeca.append(cabecaLinha); quadro.append(cabeca);
    const corpo = document.createElement('tbody');
    for (const pessoa of todas) {
      const tr = document.createElement('tr'); tr.dataset.conta = pessoa.id;
      [celulaPessoa(pessoa), celulaPapel(pessoa), celulaApuracoes(pessoa), celulaUso(pessoa), botaoGerenciar(pessoa)].forEach((conteudo, indice) => {
        const td = document.createElement('td');
        if (indice === 0) td.className = 'equipe-celula-pessoa';  // o e-mail não quebra no meio da palavra
        if (indice === 1) td.className = 'equipe-celula-papel';  // a caixa de papel mantém a largura com ou sem a linha de Gerenciar aberta
        if (conteudo) td.append(conteudo);
        tr.append(td);
      });
      corpo.append(tr);
      if (aberto.has(pessoa.id) && !ehEu(pessoa)) {
        const extra = document.createElement('tr'); extra.className = 'equipe-gerenciar-linha';
        const celula = document.createElement('td'); celula.colSpan = 5; celula.append(painelGerenciar(pessoa)); extra.append(celula); corpo.append(extra);
      }
    }
    quadro.append(corpo);
    const rolagem = no('div', 'equipe-rolagem'); rolagem.append(quadro);
    return rolagem;
  }
  function cartoes(todas) {
    const itens = no('ul', 'equipe-cartoes');
    for (const pessoa of todas) {
      const item = no('li', 'equipe-cartao'); item.dataset.conta = pessoa.id;
      const papel = no('label', 'conta-campo');
      papel.append(t('Papel'), celulaPapel(pessoa));
      const apuracoes = no('p', 'conta-apoio'); apuracoes.append(`${t('Apurações')}: `, celulaApuracoes(pessoa));
      const uso = no('p', 'conta-apoio'); uso.append(`${t('Uso no mês')}: `, celulaUso(pessoa));
      const gerenciar = botaoGerenciar(pessoa); if (gerenciar) gerenciar.className = 'secondary equipe-gerenciar-botao';
      item.append(celulaPessoa(pessoa), ...(ehEu(pessoa) ? [] : [papel]), ...(ehEu(pessoa) ? [] : [apuracoes, uso]), ...(gerenciar ? [gerenciar] : []));
      if (ehEu(pessoa)) item.append(no('p', 'conta-texto', rotuloPapel(pessoa.papel)));
      if (aberto.has(pessoa.id) && !ehEu(pessoa)) item.append(painelGerenciar(pessoa));
      itens.append(item);
    }
    return itens;
  }

  // --- mudar o papel ----------------------------------------------------------------------------------------------------------------------
  async function mudarPapel(pessoa, caixa) {
    const antigo = pessoa.papel, novo = caixa.value;
    if (novo === antigo) return;
    const voltar = () => { caixa.value = antigo; caixa.disabled = false; };
    let recusou = false;
    caixa.disabled = true;
    try {
      if (antigo === 'convidado') {  // a leitura nova é decisão de quem converte (princípio 9 do contrato)
        const converter = await window.Dialogo.confirmar({variante: 'simples', gatilho: caixa, item: pessoa.nome, itemAspas: false,
          titulo: t('Converter {item} em {papel}?', {papel: rotuloPapel(novo)}),
          texto: 'Leitor lê também o caderno, os achados e o texto das apurações de que participa.', acao: 'Converter'});
        if (!converter) { voltar(); return; }
      }
      let resultado;
      if (antigo === 'dono' || novo === 'dono') {
        const tornar = novo === 'dono';
        resultado = await sensivel({operacao: 'equipe-papel', dados: {conta: pessoa.id, papel: novo}, gatilho: caixa, dialogo: {
          titulo: tornar ? 'Tornar {item} dono da redação?' : t('Mudar o papel de {item} para {papel}?', {papel: rotuloPapel(novo)}), item: pessoa.nome,
          texto: tornar ? t('Dono vê todas as apurações da redação, administra a equipe e apaga de vez. Vale na próxima ação de {nome}.', {nome: pessoa.nome})
            : t('{nome} deixa de administrar a redação e passa a ver só as apurações de que participa. Vale na próxima ação.', {nome: pessoa.nome}),
          acao: tornar ? 'Tornar dono' : 'Mudar papel', ocupado: 'Mudando…', destrutiva: !tornar, aoRecusar: () => { recusou = true; }}});
        if (!resultado) { voltar(); if (recusou) recarregar(); return; }
      } else {
        resultado = await api('equipe-papel', {conta: pessoa.id, papel: novo});
      }
      estado(t('{nome} agora é {papel}. Vale na próxima ação.', {nome: pessoa.nome, papel: rotuloPapel(novo)}));
      await recarregar(); carregarAtividade();
    } catch (falha) {
      voltar();
      estado(falha.message, {erro: true});  // ultimo_dono e as demais recusas: o texto do servidor, em tom de erro
    }
  }

  // --- Gerenciar: apurações, teto mensal e acesso -------------------------------------------------------------------------------------------
  function bloco(rotulo) {
    const caixa = no('div', 'equipe-bloco'); caixa.append(no('h3', 'equipe-bloco-titulo', t(rotulo)));
    return caixa;
  }
  function painelGerenciar(pessoa) {
    const painel = no('div', 'equipe-gerenciar'); painel.id = `equipe-gerenciar-${pessoa.id}`;
    painel.append(blocoApuracoes(pessoa), blocoTeto(pessoa), blocoAcesso(pessoa));
    return painel;
  }
  function blocoApuracoes(pessoa) {
    const caixa = bloco('APURAÇÕES');
    if (pessoa.papel === 'dono') { caixa.append(no('p', 'conta-texto', t('Todas as apurações da redação.'))); return caixa; }
    const ids = pessoa.casos || [], responsavel = new Set(pessoa.responsavel_de || []);
    const itens = no('ul', 'equipe-casos');
    for (const id of ids) {
      const item = no('li', 'equipe-caso'); item.dataset.caso = id;
      const nome = no('span', 'conta-texto'); nome.append(dado(tituloDoCaso(id)));
      let direita;
      if (responsavel.has(id)) direita = no('span', 'conta-apoio', t('responsável'));
      else direita = botao('Retirar', 'secondary', async evento => {
        const controle = evento.currentTarget, restaurar = window.Estados.ocupado(controle, 'Retirando…');
        try { await api('caso-retirar', {caso: id, conta: pessoa.id}); estado(t('{nome} não participa mais de {caso}.', {nome: pessoa.nome, caso: tituloDoCaso(id)})); await recarregar(); carregarAtividade(); }
        catch (falha) { restaurar(); estado(falha.message, {erro: true}); }
      });
      if (!responsavel.has(id)) direita.setAttribute('aria-label', `${t('Retirar')}: ${tituloDoCaso(id)}`);
      item.append(window.Conta.linha(nome, direita)); itens.append(item);
    }
    if (!ids.length) itens.append(no('li', 'conta-apoio', t('Nenhuma')));
    caixa.append(itens);
    if ([...responsavel].some(id => ids.includes(id))) caixa.append(apoio('Quem é responsável não sai da apuração por aqui.'));
    const livres = catalogo.filter(c => !ids.includes(c.id));
    if (livres.length) {
      const escolha = document.createElement('select'); escolha.className = 'equipe-incluir-em';
      for (const c of livres) escolha.append(new Option(c.titulo, c.id));
      const rotulo = no('label', 'conta-campo', t('Incluir em')); rotulo.append(escolha);
      const incluir = botao('Incluir', 'secondary', async () => {
        const restaurar = window.Estados.ocupado(incluir, 'Incluindo…');
        try { await api('caso-incluir', {caso: escolha.value, conta: pessoa.id}); estado(t('{nome} agora participa de {caso}.', {nome: pessoa.nome, caso: tituloDoCaso(escolha.value)})); await recarregar(); carregarAtividade(); }
        catch (falha) { restaurar(); estado(falha.message, {erro: true}); }
      });
      const acoes = no('div', 'conta-acoes'); acoes.append(incluir);
      caixa.append(rotulo, acoes);
    }
    return caixa;
  }
  // O teto é enviado como texto com ponto ("30.50"), nunca como número, e null para voltar ao padrão.
  const textoDoTeto = bruto => String(bruto).trim().replace(',', '.');
  function campoDeTeto(valorInicial, rotulo) {
    const campo = document.createElement('input'); campo.type = 'text'; campo.setAttribute('inputmode', 'decimal'); campo.className = 'equipe-teto-campo';
    campo.autocomplete = 'off'; campo.value = valorInicial ?? '';
    const caixa = no('label', 'conta-campo', t(rotulo)); caixa.append(campo);
    return {campo, caixa};
  }
  const valorEditavel = bruto => (bruto ? String(bruto).replace(/\.00$/, '').replace('.', ',') : '');
  function blocoTeto(pessoa) {
    const caixa = bloco('TETO MENSAL');
    const {campo, caixa: rotulo} = campoDeTeto(valorEditavel(pessoa.teto_mensal_brl), 'Teto de gasto com IA, em reais');
    const padrao = lista?.redacao?.teto_por_pessoa_brl;
    const salvar = botao('Salvar', 'secondary', async () => {
      if (!campo.value.trim()) { window.Estados.erroCampo(campo, 'Falta o teto. Escreva o valor em reais ou use o padrão.'); return; }
      const restaurar = window.Estados.ocupado(salvar, 'Salvando…');
      try {
        await api('equipe-teto', {conta: pessoa.id, teto_brl: textoDoTeto(campo.value)});
        estado(t('Teto de {nome} salvo.', {nome: pessoa.nome})); await recarregar(); carregarAtividade();
      } catch (falha) { restaurar(); window.Estados.erroCampo(campo, falha.message); }
    });
    campo.addEventListener('keydown', evento => { if (evento.key === 'Enter') { evento.preventDefault(); salvar.click(); } });
    const acoes = no('div', 'conta-acoes'); acoes.append(salvar);
    if (pessoa.teto_mensal_brl) {
      const usarPadrao = botao('Usar o padrão', 'equipe-link', async () => {
        try { await api('equipe-teto', {conta: pessoa.id, teto_brl: null}); estado(t('{nome} volta a usar o teto padrão.', {nome: pessoa.nome})); await recarregar(); carregarAtividade(); }
        catch (falha) { window.Estados.erroCampo(campo, falha.message); }
      });
      acoes.append(usarPadrao);
    }
    caixa.append(rotulo, acoes, no('p', 'conta-apoio', `${padrao ? t('Padrão da redação: {valor}.', {valor: reais(padrao, {centavos: false})}) : t('Padrão da instalação.')} ${t('Não passa do teto da redação.')}`));
    return caixa;
  }
  function blocoAcesso(pessoa) {
    const caixa = bloco('ACESSO');
    const acoes = no('div', 'conta-acoes');
    const desativada = pessoa.situacao === 'desativada' || pessoa.ativa === false;
    if (desativada) {
      const reativar = botao('Reativar', 'secondary', async () => {
        const restaurar = window.Estados.ocupado(reativar, 'Reativando…');
        try { await api('equipe-reativar', {conta: pessoa.id}); estado(t('A conta de {nome} foi reativada.', {nome: pessoa.nome})); await recarregar(); carregarAtividade(); }
        catch (falha) { restaurar(); estado(falha.message, {erro: true}); }
      });
      acoes.append(reativar);
    } else {
      acoes.append(botao('Desativar', 'danger', evento => desativar(pessoa, evento.currentTarget)));
    }
    acoes.append(botao('Remover da redação', 'danger', evento => remover(pessoa, evento.currentTarget)));
    caixa.append(acoes, apoio('Desativar encerra as sessões e para as perguntas em curso; as apurações ficam. Remover exclui a conta.'));
    return caixa;
  }
  const TEXTO_DESATIVAR = 'A pessoa sai na próxima ação e as perguntas em curso dessa conta param. As apurações e os registros ficam; reativar devolve o acesso.';
  async function desativar(pessoa, gatilho) {
    let recusou = false;
    const aoRecusar = () => { recusou = true; };
    try {
      let resultado;
      if (pessoa.papel === 'dono') {
        resultado = await sensivel({operacao: 'equipe-desativar', dados: {conta: pessoa.id}, gatilho,
          dialogo: {titulo: 'Desativar a conta de {item}?', item: pessoa.nome, texto: TEXTO_DESATIVAR, acao: 'Desativar conta', ocupado: 'Desativando…', destrutiva: true, aoRecusar}});
      } else {  // sem ser dono, a destrutiva sem senha de P12.6; se o servidor pedir a senha mesmo assim, o diálogo com senha abre
        const ok = await window.Dialogo.confirmar({variante: 'destrutivo', titulo: 'Desativar a conta de {item}?', item: pessoa.nome, itemAspas: false,
          texto: TEXTO_DESATIVAR, acao: 'Desativar conta', gatilho});
        if (!ok) return;
        resultado = await sensivel({operacao: 'equipe-desativar', dados: {conta: pessoa.id}, pedirAntes: false, gatilho,
          dialogo: {titulo: 'Desativar a conta de {item}?', item: pessoa.nome, texto: TEXTO_DESATIVAR, acao: 'Desativar conta', ocupado: 'Desativando…', destrutiva: true, aoRecusar}});
      }
      if (!resultado) { if (recusou) recarregar(); return; }
      estado(t('A conta de {nome} foi desativada.', {nome: pessoa.nome})); await recarregar(); carregarAtividade();
    } catch (falha) { estado(falha.message, {erro: true}); }
  }
  async function remover(pessoa, gatilho) {
    let recusou = false;
    try {
      const resultado = await sensivel({operacao: 'equipe-remover', dados: {conta: pessoa.id}, gatilho, dialogo: {
        titulo: 'Remover {item} da redação?', item: pessoa.nome, acao: 'Remover da redação', ocupado: 'Removendo…', destrutiva: true,
        texto: 'A conta é excluída: a pessoa perde o acesso, sai de todas as apurações e não pode ser reativada. Notas, revisões e conversas ficam com a redação. O nome continua nos registros já gravados e nos backups, que não podem ser reescritos.', aoRecusar: () => { recusou = true; }}});
      if (!resultado) { if (recusou) recarregar(); return; }
      aberto.delete(pessoa.id);
      estado(t('{nome} não faz mais parte da redação.', {nome: pessoa.nome})); await recarregar(); carregarAtividade();
    } catch (falha) { estado(falha.message, {erro: true}); }
  }

  // --- gasto da redação e teto padrão -------------------------------------------------------------------------------------------------------
  function desenharGasto() {
    const gasto = lista?.gasto;
    const partes = [];
    if (gasto && Number.isFinite(Number(gasto.gasto_brl)) && Number(gasto.teto_brl) > 0) {
      const usado = Number(gasto.gasto_brl), teto = Number(gasto.teto_brl), pct = Math.min(100, Math.round(usado / teto * 100)), esgotada = !!gasto.esgotada;
      const valor = t('{gasto} de {teto}', {gasto: reais(usado), teto: reais(teto, {centavos: false})});
      const medidor = no('div', 'mesa-medidor'); medidor.setAttribute('role', 'img'); medidor.style.setProperty('--uso', `${esgotada ? 100 : pct}%`);
      medidor.setAttribute('aria-label', esgotada ? t('Cota do mês esgotada: {valor}', {valor}) : t('{pct}% da cota usada', {pct}));
      partes.push(no('strong', 'conta-valor', valor), medidor, apoio('Cota da redação, definida por quem administra o serviço.'));
    } else {
      partes.push(apoio('O gasto da redação aparece aqui quando o serviço passar a contá-lo por redação. O de cada pessoa está na tabela.'));
    }
    const {campo, caixa} = campoDeTeto(valorEditavel(lista?.redacao?.teto_por_pessoa_brl), 'Teto padrão por pessoa, em reais');
    campo.id = 'equipe-teto-padrao';
    const salvar = botao('Salvar', 'secondary', async () => {
      const restaurar = window.Estados.ocupado(salvar, 'Salvando…');
      try {
        await api('equipe-teto', {teto_brl: campo.value.trim() ? textoDoTeto(campo.value) : null});  // vazio: o teto da instalação
        estado(t('Teto padrão salvo.')); await recarregar(); carregarAtividade();
      } catch (falha) { restaurar(); window.Estados.erroCampo(campo, falha.message); }
    });
    campo.addEventListener('keydown', evento => { if (evento.key === 'Enter') { evento.preventDefault(); salvar.click(); } });
    const acoes = no('div', 'conta-acoes'); acoes.append(salvar);
    partes.push(caixa, acoes, apoio('Vazio quer dizer o teto da instalação.'));
    raiz.gasto.corpo.replaceChildren(...partes);
  }

  // --- atividade recente ----------------------------------------------------------------------------------------------------------------
  // "Fulano" é `por_nome` e "Beltrano" é `conta_nome`. Sem nome (conta removida): "uma conta removida"; sem conta em `por` (operador, migração): "Quem
  // administra o serviço". Os nomes entram como texto marcado translate="no".
  const FRASES = {
    papel_alterado: '{por} mudou o papel de {conta}',
    conta_desativada: '{por} desativou a conta de {conta}', conta_reativada: '{por} reativou a conta de {conta}',
    conta_excluida: '{por} removeu {conta} da redação', conta_criada: '{por} criou a conta de {conta}',
    participacao_incluida: '{por} incluiu {conta} numa apuração', participacao_retirada: '{por} retirou {conta} de uma apuração',
    responsavel_alterado: '{por} mudou o responsável de uma apuração', teto_alterado: '{por} mudou um teto de gasto',
    senha_trocada: '{conta} trocou a senha', senha_definida: '{conta} definiu a senha',
    sessao_encerrada_a_distancia: '{conta} encerrou sessões em outros aparelhos', conta_atualizada: '{conta} atualizou o perfil',
    recuperacao_emitida: '{por} gerou um novo link de ativação para {conta}',
    login_bloqueado: 'A entrada de {conta} foi bloqueada por muitas tentativas',
    // Os que o servidor também grava e o desenho não previa (ressalva D1 da Coruja): cada tipo com a sua frase.
    sessao_encerrada: '{conta} saiu da Mesa', acesso_alterado: '{por} mudou o acesso de {conta}',
    caso_atribuido: '{por} atribuiu uma apuração a uma pessoa', caso_criado: '{conta} criou uma apuração',
    primeiro_admin: 'A redação foi criada, com {conta} como dono', migracao_contas: 'As contas foram migradas para o novo modelo de acesso',
    redacao_criada: 'A redação foi criada', redacao_suspensa: 'A redação foi suspensa por quem administra o serviço',
    redacao_reativada: 'A redação foi reativada por quem administra o serviço', redacao_encerrada: 'A redação foi encerrada por quem administra o serviço',
  };
  function nomeDe(evento, lado) {
    const nome = evento[`${lado}_nome`], id = evento[lado];
    if (nome) return dado(nome);
    if (lado === 'por' && !(typeof id === 'string' && ID_CONTA.test(id))) return t('Quem administra o serviço');
    return t('uma conta removida');
  }
  function frase(evento) {
    const modelo = FRASES[evento.tipo];
    const alvo = no('span', 'equipe-frase');
    if (!modelo) { alvo.textContent = t('Ação de administração'); return alvo; }
    // Quando as duas pontas são a mesma conta, a frase usa só o nome dela.
    for (const pedaco of t(modelo).split(/(\{por\}|\{conta\})/)) {
      if (pedaco === '{por}') alvo.append(nomeDe(evento, 'por'));
      else if (pedaco === '{conta}') alvo.append(nomeDe(evento, 'conta'));
      else if (pedaco) alvo.append(pedaco);
    }
    return alvo;
  }
  function desenharAtividade() {
    const corpo = raiz.atividade.corpo;
    if (!atividade.eventos.length) { corpo.replaceChildren(no('p', 'conta-texto', t('Nenhuma ação registrada ainda.'))); return; }
    const itens = no('ul', 'equipe-atividade');
    for (const evento of atividade.eventos) {
      const item = no('li', 'equipe-atividade-item'); item.dataset.tipo = evento.tipo;
      item.append(frase(evento), no('span', 'conta-apoio', data(evento.em)));
      itens.append(item);
    }
    const partes = [itens];
    if (atividade.proximo !== null && atividade.proximo !== undefined) {
      const mais = botao('Mostrar mais', 'secondary equipe-mostrar-mais', async () => {
        const restaurar = window.Estados.ocupado(mais, 'Carregando…');
        try {
          const pagina = await api('equipe-atividade', {limite: 50, antes: atividade.proximo});  // o cursor é opaco: volta como veio
          atividade = {eventos: [...atividade.eventos, ...(pagina.eventos || [])], proximo: pagina.proximo ?? null};
          desenharAtividade();
        } catch (falha) { restaurar(); mais.after(Object.assign(no('p', 'campo-erro', falha.message), {role: 'alert'})); }
      });
      partes.push(mais);
    }
    corpo.replaceChildren(...partes);
  }
  function carregarAtividade() {
    return carregar(raiz.atividade, () => api('equipe-atividade', {limite: 5}), pagina => {
      atividade = {eventos: pagina.eventos || [], proximo: pagina.proximo ?? null}; atividadePronta = true; desenharAtividade();
    });
  }

  window.Conta.registrarAba('equipe', {rotulo: 'Equipe', capacidade: 'equipe-listar', montar, abrir, titulo});
  window.Equipe = {frase, FRASES};
})();
