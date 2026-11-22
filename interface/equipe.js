'use strict';
// A aba Equipe (docs/design/componentes.md#equipe, W09): só para quem tem `equipe-listar`, isto é, o dono. A tabela da redação (cartões abaixo de
// 1024 px) com papel, apurações e uso do mês; "Gerenciar" abre apurações, teto mensal e acesso da pessoa; abaixo, o gasto da redação e a atividade.
// Os dados vêm de equipe-listar, equipe-atividade, caso-* e /api/catalogo. A Mesa não decide pelo nome do papel e não aceita HTML: nomes e
// e-mails entram como texto. A senha das operações sensíveis vai pelo diálogo com senha de conta.js (#dialogo-senha). "Convidar pessoa" não existe
// mais: com a E3 de Contas, "Convidar pessoa" e os convites pendentes (Reenviar, Cancelar) entram aqui (#convites), e "Recuperar acesso" (#recuperar), que
// sempre envolve duas partes e pede a senha de quem age; os pedidos à espera de confirmação de um terceiro dono ficam num cartão acima da tabela.
(() => {
  if (!window.Conta) return;
  const {no, botao, dado, apoio, carregar, data, dia, reais, rotuloPapel, estado, sensivel, textoDoServidor} = window.Conta;
  const t = (pt, vars) => (window.I18N ? window.I18N.t(pt, vars) : String(pt).replace(/\{(\w+)\}/g, (todo, nome) => vars?.[nome] ?? todo));
  const ID_CONTA = /^[0-9a-f]{16}$/;
  const PAPEIS_ESCOLHA = ['dono', 'editor', 'reporter', 'leitor'];

  let lista = null, catalogo = [], quemSou = null, modo = null, aberto = new Set();
  let atividade = {eventos: [], proximo: null}, atividadePronta = false;
  const raiz = {};  // os contêineres montados
  const desktop = typeof matchMedia === 'function' ? matchMedia('(min-width:1024px)') : {matches: true, addEventListener() {}};
  let ultimoLayout = null;

  const pessoas = () => lista?.pessoas || [];
  const tituloDoCaso = id => (catalogo.find(c => c.id === id) || {titulo: id}).titulo;

  // --- montagem -----------------------------------------------------------------------------------------------------------------------------
  function montar(painel) {
    raiz.aviso = no('div', 'equipe-aviso'); raiz.aviso.hidden = true;
    raiz.recuperacoes = no('section', 'conta-cartao equipe-recuperacoes'); raiz.recuperacoes.hidden = true;
    raiz.tabela = no('section', 'conta-cartao conta-cartao-tabela'); raiz.tabela.setAttribute('aria-label', t('Pessoas da redação'));
    raiz.corpoTabela = no('div', 'conta-cartao-corpo'); raiz.tabela.append(raiz.corpoTabela);
    // "Convidar pessoa" (botão principal no título, #convites): com o convite por e-mail a exceção do texto abaixo da tabela deixou de valer.
    raiz.convidar = botao('Convidar pessoa', 'equipe-acao-titulo', evento => convidar(evento.currentTarget));
    raiz.convidar.hidden = true;
    raiz.gasto = window.Conta.cartao('Gasto com IA neste mês');
    raiz.atividade = window.Conta.cartao('Atividade recente', 'equipe-atividade-cartao');
    raiz.gasto.raiz.dataset.cartao = 'gasto'; raiz.atividade.raiz.dataset.cartao = 'atividade';
    const abaixo = no('div', 'conta-grade equipe-abaixo');
    abaixo.append(raiz.gasto.raiz, raiz.atividade.raiz);
    painel.append(raiz.aviso, raiz.recuperacoes, raiz.tabela, abaixo);
    desktop.addEventListener?.('change', () => { if (lista) desenharLista(); });
  }
  async function abrir() {
    const sessaoAtual = await window.Conta.sessao();
    quemSou = sessaoAtual?.conta?.id || null;
    modo = sessaoAtual?.modo || null;  // 'local-contas' é a Mesa instalada: lá a recuperação mostra o link na tela (P33)
    await recarregar();
    carregarAtividade();
  }
  const convites = () => lista?.convites || [];
  function titulo() {
    const n = pessoas().length, p = convites().length;
    const contagem = n ? (n === 1 ? t('1 pessoa') : t('{n} pessoas', {n})) : '';
    const pendentes = p ? (p === 1 ? t('1 convite pendente') : t('{n} convites pendentes', {n: p})) : '';
    raiz.convidar.hidden = !window.Conta.capacidade('equipe-convidar');
    window.Conta.titulo(lista?.redacao?.nome || t('Equipe'), [contagem, pendentes].filter(Boolean).join(' · '), !!lista?.redacao?.nome, raiz.convidar.hidden ? null : raiz.convidar);
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
    desenharRecuperacoes();
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
    if (contato) { const c = dado(contato, 'p'); c.className = 'conta-apoio'; bloco.append(c); }
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
    for (const convite of convites()) {
      const tr = document.createElement('tr'); tr.dataset.convite = convite.id;
      [celulaConvite(convite), no('span', 'conta-texto', rotuloPapel(convite.papel)), celulaApuracoes({papel: convite.papel, casos: convite.casos}), no('span', 'conta-texto', '—'), acoesDoConvite(convite)]
        .forEach((conteudo, indice) => {
          const td = document.createElement('td');
          if (indice === 0) td.className = 'equipe-celula-pessoa';
          if (indice === 1) td.className = 'equipe-celula-papel';
          if (indice === 4) td.className = 'equipe-celula-acoes';  // Reenviar e Cancelar convite lado a lado, com intervalo de 16
          td.append(conteudo); tr.append(td);
        });
      corpo.append(tr);
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
    for (const convite of convites()) {
      const item = no('li', 'equipe-cartao equipe-cartao-convite'); item.dataset.convite = convite.id;
      const papel = no('p', 'conta-apoio'); papel.append(`${t('Papel')}: `, rotuloPapel(convite.papel));
      const apuracoes = no('p', 'conta-apoio'); apuracoes.append(`${t('Apurações')}: `, celulaApuracoes({papel: convite.papel, casos: convite.casos}));
      item.append(celulaConvite(convite), papel, apuracoes, acoesDoConvite(convite, true));
      itens.append(item);
    }
    return itens;
  }

  // --- convites pendentes (#convites) --------------------------------------------------------------------------------------------------------
  // "há 2 dias", "há 3 h", "há 5 min"; e o prazo: "vence em 5 dias", "vence hoje" no último dia.
  function haQuanto(iso, agora = new Date()) {
    const ms = agora - new Date(iso);
    if (!iso || Number.isNaN(ms) || ms < 60000) return t('agora há pouco');
    const minutos = Math.floor(ms / 60000), horas = Math.floor(minutos / 60), dias = Math.floor(horas / 24);
    if (dias >= 1) return dias === 1 ? t('há 1 dia') : t('há {n} dias', {n: dias});
    if (horas >= 1) return t('há {n} h', {n: horas});
    return t('há {n} min', {n: minutos});
  }
  function venceEm(iso, agora = new Date()) {
    const restante = new Date(iso) - agora;
    if (Number.isNaN(restante)) return '';
    if (restante < 86400000) return t('vence hoje');
    const dias = Math.ceil(restante / 86400000);
    return dias === 1 ? t('vence em 1 dia') : t('vence em {n} dias', {n: dias});
  }
  function celulaConvite(convite) {
    const bloco = no('div', 'equipe-pessoa');
    const email = no('p', 'equipe-pessoa-nome'); email.append(dado(convite.email || '')); bloco.append(email);
    const situacao = convite.envio === 'falha'
      ? no('p', 'conta-apoio equipe-situacao equipe-convite-falha', t('! O e-mail não saiu · reenvie'))
      : no('p', 'conta-apoio equipe-situacao', t(convite.envio === 'tela' ? '◐ Link criado {quando} · {vence}' : '◐ Convite enviado {quando} · {vence}',
        {quando: haQuanto(convite.enviado_em), vence: venceEm(convite.expira_em)}));
    bloco.append(situacao);
    return bloco;
  }
  function acoesDoConvite(convite, celular = false) {
    const grupo = no('div', celular ? 'equipe-convite-acoes equipe-convite-acoes-celular' : 'equipe-convite-acoes');
    const classe = celular ? 'secondary' : 'equipe-link';
    const reenviar = botao('Reenviar', classe, () => reenviarConvite(convite, reenviar));
    reenviar.setAttribute('aria-label', `${t('Reenviar')}: ${convite.email}`);
    const cancelar = botao('Cancelar convite', classe, () => cancelarConvite(convite, cancelar));
    cancelar.setAttribute('aria-label', `${t('Cancelar convite')}: ${convite.email}`);
    grupo.append(reenviar, cancelar);
    return grupo;
  }
  const AVISO_DE_ENVIO = '! O e-mail para {email} não saiu. O convite está entre os pendentes; reenvie quando quiser.';
  // A vista do link do convite com o transporte `tela`: mostrada uma vez, no diálogo, e não fica na página depois.
  function vistaDoLink({titulo: tituloDoLink, email, link, expiraEm, texto: textoPronto}) {
    return {titulo: tituloDoLink, item: email, itemAspas: false, acao: 'Já enviei', semCancelar: true,
      texto: textoPronto || t('Mande por um canal seguro, pessoalmente ou por mensageiro cifrado. O link vale até {dia}, uma única vez, e não será mostrado de novo.', {dia: dia(expiraEm)}),
      montar(vista) {
        const campoDoLink = document.createElement('input'); campoDoLink.type = 'text'; campoDoLink.readOnly = true; campoDoLink.value = link;
        campoDoLink.className = 'convite-link'; campoDoLink.setAttribute('translate', 'no'); campoDoLink.setAttribute('aria-label', t('Link do convite'));
        const aviso = no('p', 'conta-apoio'); aviso.setAttribute('role', 'status');
        const copiar = botao('Copiar link', 'secondary', async () => {
          try { await navigator.clipboard.writeText(campoDoLink.value); aviso.textContent = t('Link copiado.'); }
          catch (_) { campoDoLink.select(); aviso.textContent = t('Selecione o link e copie manualmente.'); }
        });
        const linha = no('div', 'convite-link-linha'); linha.append(campoDoLink, copiar);
        vista.append(linha, aviso);
        Promise.resolve().then(() => { campoDoLink.focus(); campoDoLink.select?.(); });
      }};
  }
  function mostrarLink({titulo: tituloDoLink, email, link, expiraEm, gatilho}) {
    return window.Dialogo.confirmar({variante: 'simples', titulo: tituloDoLink, acao: 'Já enviei', gatilho,
      preparar: ctx => ctx.trocarPor(vistaDoLink({titulo: tituloDoLink, email, link, expiraEm}))});
  }
  // Depois de convidar ou reenviar: o que a tela faz depende de como o convite saiu (`envio`).
  async function resultadoDoEnvio(resposta, {reenvio, gatilho}) {
    const convite = resposta.convite || {};
    if (convite.envio === 'falha') estado(t(AVISO_DE_ENVIO, {email: convite.email}), {aviso: true});
    else if (convite.envio === 'tela' && resposta.link) {
      await mostrarLink({titulo: reenvio ? 'Novo link para {item}' : 'Envie o link a {item}', email: convite.email, link: resposta.link, expiraEm: convite.expira_em, gatilho});
    } else estado(reenvio ? t('Convite reenviado para {email}. O link anterior deixou de valer.', {email: convite.email}) : t('Convite enviado para {email}.', {email: convite.email}));
  }
  async function reenviarConvite(convite, controle) {
    const restaurar = window.Estados.ocupado(controle, 'Reenviando…');
    try {
      const resposta = await api('equipe-convite-reenviar', {convite: convite.id});
      restaurar();
      await resultadoDoEnvio(resposta, {reenvio: true, gatilho: controle});
      await recarregar(); carregarAtividade();
    } catch (falha) {
      restaurar();
      if (falha?.result?.erro === 'Convite não encontrado.') { await recarregar(); return; }  // já não existe: a lista recarrega, sem erro
      estado(textoDoServidor(falha), {erro: true});  // inclusive o limite de uma hora (429 limite_de_convites)
    }
  }
  async function cancelarConvite(convite, gatilho) {
    let jaNaoExiste = false;
    const ok = await window.Dialogo.confirmar({variante: 'destrutivo', titulo: 'Cancelar o convite de {item}?', item: convite.email, itemAspas: false, gatilho,
      texto: 'O link deixa de valer. Dá para convidar o mesmo e-mail de novo, mas cada endereço recebe no máximo três convites da redação por hora, contando os cancelados.',
      acao: 'Cancelar convite', cancelar: 'Manter convite', ocupado: 'Cancelando…',
      async executar() {
        try { await api('equipe-convite-cancelar', {convite: convite.id}); }
        catch (falha) { if (falha?.result?.erro === 'Convite não encontrado.') { jaNaoExiste = true; return; } throw falha; }
      }});
    if (!ok) return;
    if (!jaNaoExiste) estado(t('Convite de {email} cancelado.', {email: convite.email}));
    await recarregar(); carregarAtividade();
  }

  // --- Convidar pessoa ------------------------------------------------------------------------------------------------------------------------
  const PAPEIS_DO_CONVITE = ['leitor', 'reporter', 'editor', 'dono'];
  const O_QUE_O_PAPEL_FAZ = {leitor: 'Lê e pergunta.', reporter: 'Cria apurações e envia documentos.', editor: 'Confere e revisa o texto.',
    dono: 'Administra a redação e vê todas as apurações.'};
  const FORMA_DE_EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  async function convidar(gatilho) {
    let resposta = null;
    const form = {};
    const ok = await window.Dialogo.confirmar({
      variante: 'simples', titulo: 'Convidar pessoa', acao: 'Convidar', ocupado: 'Convidando…', gatilho,
      campos: [{id: 'senha', rotulo: 'Sua senha', apoio: 'A senha com que você entra na Mesa.', autocomplete: 'current-password', exigido: true, oculto: true}],
      preparar(ctx) {
        const corpo = ctx.corpo; corpo.classList.add('convite-form');
        const email = document.createElement('input'); email.type = 'email'; email.autocomplete = 'off'; email.setAttribute('translate', 'no'); email.maxLength = 254;
        email.setAttribute('spellcheck', 'false'); email.setAttribute('autocapitalize', 'none');
        const rotuloEmail = no('label', 'conta-campo', t('E-mail')); rotuloEmail.append(email);
        const papel = document.createElement('select');
        for (const valor of PAPEIS_DO_CONVITE) papel.append(new Option(rotuloPapel(valor), valor));
        papel.value = 'leitor';
        const rotuloPapelCampo = no('label', 'conta-campo', t('Papel')); rotuloPapelCampo.append(papel);
        const oQueFaz = no('p', 'conta-apoio', t(O_QUE_O_PAPEL_FAZ.leitor)); oQueFaz.setAttribute('aria-live', 'polite');
        const conjunto = document.createElement('fieldset'); conjunto.className = 'convite-apuracoes';
        conjunto.append(no('legend', 'conta-campo', t('Apurações')));
        const grupo = no('div', 'convite-casos'); if (catalogo.length >= 6) grupo.dataset.rolagem = 'true';
        const marcas = [];
        for (const caso of catalogo) {
          const marca = document.createElement('input'); marca.type = 'checkbox'; marca.value = caso.id; marcas.push(marca);
          const rotulo = no('label', 'convite-caso'); rotulo.append(marca, ' ', dado(caso.titulo));
          grupo.append(rotulo);
        }
        if (!catalogo.length) grupo.append(no('p', 'conta-apoio', t('A redação ainda não tem apurações.')));
        conjunto.append(grupo);
        const todasAsApuracoes = no('p', 'conta-apoio', t('Dono alcança todas as apurações da redação.')); todasAsApuracoes.hidden = true;
        const idioma = document.createElement('select');
        idioma.append(new Option('Português', 'pt'), new Option('English', 'en')); idioma.value = window.I18N?.idioma?.() === 'en' ? 'en' : 'pt';
        const rotuloIdioma = no('label', 'conta-campo', t('Idioma do convite')); rotuloIdioma.append(idioma);
        papel.addEventListener('change', () => {
          const dono = papel.value === 'dono';
          oQueFaz.textContent = t(O_QUE_O_PAPEL_FAZ[papel.value]);
          conjunto.hidden = dono; todasAsApuracoes.hidden = !dono;
          ctx.campoVisivel('senha', dono);  // só com o papel Dono pede a senha (contrato, 5.15)
        });
        corpo.append(rotuloEmail, rotuloPapelCampo, oQueFaz, conjunto, todasAsApuracoes, rotuloIdioma);
        Object.assign(form, {email, papel, marcas, idioma});
        email.focus();
      },
      validar() {
        window.Estados.limparErroCampo(form.email);
        const texto = form.email.value.trim();
        if (!texto) { window.Estados.erroCampo(form.email, 'Falta o e-mail. Escreva o e-mail da pessoa.'); return false; }
        if (!FORMA_DE_EMAIL.test(texto)) { window.Estados.erroCampo(form.email, 'E-mail inválido. Confira o endereço, por exemplo ana@redacao.org.'); return false; }
        return {};
      },
      async executar(ctx) {
        const dono = form.papel.value === 'dono';
        const dados = {email: form.email.value.trim(), papel: form.papel.value, idioma: form.idioma.value, casos: dono ? [] : form.marcas.filter(m => m.checked).map(m => m.value)};
        if (dono) dados.senha = ctx.valores().senha;
        try { resposta = await api('equipe-convidar', dados); }
        catch (falha) {
          if (falha?.result?.codigo === 'convite_duplicado') {  // o texto do servidor, abaixo do campo E-mail
            window.Estados.erroCampo(form.email, textoDoServidor(falha));
            throw Object.assign(new Error(falha.message), {silencioso: true});
          }
          // limite_de_convites e as demais recusas: o texto do servidor no erro do diálogo; a senha, como na variante com senha
          const recusa = window.Dialogo.recusaDaSenha(falha);
          throw recusa === falha ? new Error(textoDoServidor(falha)) : recusa;
        }
        const convite = resposta.convite || {};
        if (convite.envio === 'tela' && resposta.link) {
          ctx.trocarPor(vistaDoLink({titulo: 'Envie o link a {item}', email: convite.email, link: resposta.link, expiraEm: convite.expira_em}));
        }
      },
    });
    if (!ok || !resposta) return;
    const convite = resposta.convite || {};
    if (convite.envio !== 'tela') await resultadoDoEnvio(resposta, {reenvio: false, gatilho});
    await recarregar(); carregarAtividade();
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
    // "Recuperar acesso": secundário, só para conta ativa (a desativada é reativada antes) e para quem pode (equipe-recuperar).
    const recuperavel = !desativada && window.Conta.capacidade('equipe-recuperar');
    if (recuperavel) acoes.append(botao('Recuperar acesso', 'secondary', evento => recuperar(pessoa, evento.currentTarget)));
    acoes.append(botao('Remover da redação', 'danger', evento => remover(pessoa, evento.currentTarget)));
    caixa.append(acoes, apoio('Desativar encerra as sessões e para as perguntas em curso; as apurações ficam. Remover exclui a conta.'));
    if (recuperavel) {
      caixa.append(apoio('Recuperar manda à pessoa um link para criar uma senha nova; nada muda na conta até ela usar o link.'));
      if (pessoa.papel === 'dono') caixa.append(apoio('Para um dono, outro dono precisa confirmar em até 24 horas.'));
    }
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

  // --- Recuperar o acesso de outra pessoa (#recuperar) ---------------------------------------------------------------------------------------
  const TEXTO_DO_LINK_DE_RECUPERACAO = 'Mande por um canal seguro. O link vale 24 horas, uma única vez, e não será mostrado de novo. Nada muda na conta até ele ser usado.';
  // O que a tela faz com a resposta (a mesma em equipe-recuperar e em equipe-recuperar-confirmar): `confirmada` com link troca o formulário pelo link; as outras
  // fecham o diálogo e deixam uma linha de estado. Devolve o que dizer depois que o diálogo fechar.
  function tratarRecuperacao(resposta, nome, ctx) {
    if (resposta.estado === 'confirmada' && resposta.link) {
      ctx.trocarPor(vistaDoLink({titulo: 'Entregue o link a {item}', email: nome, link: resposta.link, texto: t(TEXTO_DO_LINK_DE_RECUPERACAO)}));
      return null;
    }
    if (resposta.estado === 'enviada') {
      return resposta.envio === 'falha' ? {texto: t('! O e-mail para {nome} não saiu. Peça de novo em alguns minutos.', {nome}), aviso: true}
        : {texto: t('Link de recuperação enviado para {nome}. Vale 24 horas.', {nome})};
    }
    if (resposta.estado === 'aguardando_confirmacao') {
      return {texto: t('Pedido registrado. Outro dono precisa confirmar a recuperação de {nome} até {quando}.', {nome, quando: data(resposta.recuperacao?.expira_em)})};
    }
    return null;
  }
  async function dialogoDeRecuperacao({titulo: tituloDoDialogo, item, texto, acao, ocupado, operacao, dados, nome, gatilho}) {
    let depois = null, recusou = false;
    const ok = await window.Dialogo.confirmar({variante: 'simples', titulo: tituloDoDialogo, item, itemAspas: false, texto, acao, ocupado, gatilho,
      campos: [{id: 'senha', rotulo: 'Sua senha', apoio: 'A senha com que você entra na Mesa.', autocomplete: 'current-password', exigido: true}],
      async executar(ctx) {
        let resposta;
        try { resposta = await api(operacao, {...dados, senha: ctx.valores().senha}); }
        catch (falha) {
          recusou = true;
          // recuperacao_pelo_operador: não há terceiro dono, ou o link não tem como chegar à pessoa. Não é erro de quem pediu: a ação sai de cena e sobra Cancelar.
          if (falha?.result?.codigo === 'recuperacao_pelo_operador') throw Object.assign(new Error(textoDoServidor(falha)), {bloqueado: true});
          const recusa = window.Dialogo.recusaDaSenha(falha);
          throw recusa === falha ? new Error(textoDoServidor(falha)) : recusa;
        }
        depois = tratarRecuperacao(resposta, nome, ctx);
      }});
    if (recusou) await recarregar();  // o pedido pode ter vencido, ou a situação mudado: a lista recarrega
    if (!ok) return;
    if (depois) estado(depois.texto, depois.aviso ? {aviso: true} : {});
    await recarregar(); carregarAtividade();
  }
  function recuperar(pessoa, gatilho) {
    const nome = pessoa.nome || '';
    const texto = pessoa.papel === 'dono' ? t('{nome} é dono. O pedido espera até 24 horas que outro dono, que não seja você, o confirme. Só então sai o link.', {nome})
      : modo === 'local-contas' ? t('A Mesa mostra a você um link para {nome} criar uma senha nova. Entregue por um canal seguro. O link vale 24 horas.', {nome})
      : t('{nome} recebe por e-mail um link para criar uma senha nova. O link vale 24 horas. Nada muda na conta até ele ser usado.', {nome});
    return dialogoDeRecuperacao({titulo: 'Recuperar o acesso de {item}?', item: nome, texto, acao: 'Recuperar acesso', ocupado: 'Recuperando…',
      operacao: 'equipe-recuperar', dados: {conta: pessoa.id}, nome, gatilho});
  }
  function confirmarRecuperacao(pedido, gatilho) {
    const nome = pedido.conta_nome || t('essa pessoa'), por = pedido.pedida_por_nome || t('um dono');
    const segunda = modo === 'local-contas' ? t('Ao confirmar, a Mesa mostra a você o link para entregar a {nome}.', {nome})
      : t('Ao confirmar, {nome} recebe por e-mail um link para criar uma senha nova, válido por 24 horas.', {nome});
    return dialogoDeRecuperacao({titulo: 'Confirmar a recuperação do acesso de {item}?', item: nome, texto: `${t('{por} pediu em {quando}.', {por, quando: data(pedido.pedida_em)})} ${segunda}`,
      acao: 'Confirmar recuperação', ocupado: 'Confirmando…', operacao: 'equipe-recuperar-confirmar', dados: {recuperacao: pedido.id}, nome, gatilho});
  }
  // O cartão "Recuperações à espera de confirmação": só quando há pedidos. "Confirmar" só para um terceiro dono; para quem pediu e para a própria pessoa, "Aguardando outro dono".
  function modelar(modelo, valores) {
    const alvo = document.createDocumentFragment();
    for (const pedaco of String(modelo).split(/(\{\w+\})/)) {
      const chave = /^\{(\w+)\}$/.exec(pedaco)?.[1];
      if (chave && chave in valores) alvo.append(valores[chave]); else if (pedaco) alvo.append(pedaco);
    }
    return alvo;
  }
  function desenharRecuperacoes() {
    const pedidos = lista?.recuperacoes || [];
    raiz.recuperacoes.hidden = !pedidos.length;
    if (!pedidos.length) { raiz.recuperacoes.replaceChildren(); return; }
    const cabeca = no('h2', 'conta-cartao-titulo', t('Recuperações à espera de confirmação'));
    const itens = no('ul', 'equipe-recuperacoes-lista');
    for (const pedido of pedidos) {
      const item = no('li', 'equipe-recuperacao'); item.dataset.recuperacao = pedido.id;
      const texto = no('div', 'conta-rotulo');
      const nome = no('span', 'conta-texto'); nome.append(pedido.conta_nome ? dado(pedido.conta_nome) : t('uma conta removida'));
      const detalhe = no('span', 'conta-apoio');
      detalhe.append(modelar(t('pedido por {por} em {pedida} · vence em {vence}'), {por: pedido.pedida_por_nome ? dado(pedido.pedida_por_nome) : t('um dono'), pedida: data(pedido.pedida_em), vence: data(pedido.expira_em)}));
      texto.append(nome, detalhe);
      const parte = !!quemSou && (pedido.pedida_por === quemSou || pedido.conta === quemSou);
      let acao;
      if (parte || !window.Conta.capacidade('equipe-recuperar-confirmar')) acao = no('span', 'conta-apoio', t('Aguardando outro dono'));
      else { acao = botao('Confirmar', 'secondary', evento => confirmarRecuperacao(pedido, evento.currentTarget)); acao.setAttribute('aria-label', `${t('Confirmar')}: ${pedido.conta_nome || ''}`); }
      item.append(window.Conta.linha(texto, acao));
      itens.append(item);
    }
    raiz.recuperacoes.replaceChildren(cabeca, itens);
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
    // Convites (E3): a atividade não leva o e-mail, que é dado de quem ainda não é da redação.
    convite_enviado: '{por} convidou um e-mail', convite_reenviado: '{por} reenviou um convite', convite_cancelado: '{por} cancelou um convite',
    convite_aceito: '{conta} aceitou o convite e entrou na redação', convite_expirado: 'Um convite venceu',
    // Recuperação do acesso, link de senha e troca do e-mail (frases do Design, #recuperar; nenhuma leva endereço de e-mail).
    recuperacao_pedida: '{por} pediu a recuperação do acesso de {conta}', recuperacao_confirmada: '{por} confirmou a recuperação do acesso de {conta}',
    senha_redefinida: '{conta} criou uma senha nova pelo link', redefinicao_pedida: '{conta} pediu um link para criar uma senha nova',
    email_troca_pedida: '{conta} pediu para trocar o e-mail', email_trocado: '{conta} trocou o e-mail',
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
