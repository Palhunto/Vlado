'use strict';
// Sign-in (/entrar), set-password (/ativar/<token>), invitation (/aceitar/<token>), reset (/redefinir/<token>) and e-mail (/confirmar-email/<token>) pages. No external resources, no case data.
// The server decides everything; messages here stay generic on purpose.
(() => {
  const $ = id => document.getElementById(id);
  const TEXTOS = {
    pt: {
      titulo_pagina: 'Entrar · Vlado', titulo_entrar: 'Entrar',
      intro_entrar: 'Use o login e a senha da sua conta.', rotulo_login: 'Login', rotulo_senha: 'Senha',
      mostrar: 'Mostrar', ocultar: 'Ocultar', botao_entrar: 'Entrar', entrando: 'Entrando…',
      titulo_ativar: 'Definir sua senha',
      intro_ativar: 'Este link vale uma única vez. Escolha uma senha com pelo menos 12 caracteres.',
      rotulo_nova: 'Nova senha', rotulo_confirmar: 'Repita a nova senha',
      dica_senha: 'De 12 a 256 caracteres. Uma frase longa é mais fácil de lembrar.',
      botao_ativar: 'Definir senha', salvando: 'Salvando…', ir_entrar: 'Entrar com a nova senha',
      idioma: 'English', idioma_rotulo: 'Switch to English',
      tema_claro: 'Modo claro', tema_escuro: 'Modo escuro',
      erro_credenciais: 'E-mail ou login e senha não conferem. Confira e tente de novo.',
      erro_bloqueado: 'Muitas tentativas. Aguarde alguns minutos e tente de novo.',
      rotulo_email_login: 'E-mail ou login',
      erro_login_vazio: 'Falta o e-mail ou o login. Escreva o e-mail da sua conta (ou o login, se ela é antiga).',
      erro_senha_vazia: 'Falta a senha. Use a senha da sua conta.',
      erro_nome_vazio: 'Falta o nome. Escreva o seu nome.',
      erro_login_regra: 'Login inválido. Use de 3 a 64 caracteres: letras minúsculas, números, ponto, hífen ou sublinhado, começando por letra ou número.',
      erro_ativacao: 'Este link de ativação é inválido, já foi usado ou expirou. Peça um novo link à administração.',
      erro_senha_tamanho: 'A senha deve ter de 12 a 256 caracteres.',
      erro_senha_diferente: 'As duas senhas não coincidem. Digite a mesma senha nos dois campos.',
      erro_indisponivel: 'O acesso está indisponível no momento. Avise a administração.',
      erro_rede: 'Sem conexão com o servidor. Verifique a rede e tente de novo.',
      erro_geral: 'Não foi possível concluir. Recarregue a página e tente de novo.',
      senha_definida: 'Senha definida. Agora entre com seu login e a nova senha.',
      titulo_primeiro: 'Criar administrador', rotulo_nome: 'Nome',
      intro_primeiro: 'Primeira abertura do Vlado neste computador. Crie a conta de administração; depois, a Mesa sempre pedirá login e senha.',
      dica_login: 'De 3 a 64 letras minúsculas, números, ponto, hífen ou sublinhado.',
      rotulo_confirmar_senha: 'Repita a senha', botao_primeiro: 'Criar administrador', criando: 'Criando…',
      ir_entrar_conta: 'Entrar com a nova conta', erro_nome_login: 'Informe nome e login válidos.',
      erro_primeiro_encerrado: 'A conta de administração já existe. Entre com login e senha.',
      erro_primeiro_local: 'Esta tela só funciona no próprio computador, em http://127.0.0.1.',
      admin_criado: 'Administrador criado. Agora entre com o login e a senha.',
      esqueci: 'Esqueceu a senha? Fale com quem administra o serviço.',
      esqueci_link: 'Esqueci a senha',
      frase_marca: 'Apuração documental com a fonte de cada afirmação à vista.',
      teste_titulo: 'O Vlado está em teste com redações convidadas',
      teste_texto: 'O acesso chega por convite, no e-mail da sua redação. Recebeu um? Abra o link do convite para criar a conta.',
      rodape_texto: 'Use só documentos públicos. Trechos são enviados ao provedor de IA para análise.',
      carregando: 'Carregando…',
      rubrica_convite: 'CONVITE',
      titulo_aceitar: 'Entre na {redacao}',
      convite_antes: '{quem} convidou ',
      convite_depois: ' como {papel}.',
      convite_validade: 'Convite válido até {data}',
      papel_dono: 'Dono',
      papel_editor: 'Editor',
      papel_reporter: 'Repórter',
      papel_leitor: 'Leitor',
      papel_convidado: 'Convidado',
      rotulo_seu_nome: 'Seu nome',
      rotulo_crie_senha: 'Crie uma senha',
      dica_senha_convite: 'De 12 a 256 caracteres. Pode colar ou usar o gerenciador de senhas.',
      termos_antes: 'Li e aceito os ', termos_uso: 'termos de uso', termos_e: ' e a ', termos_priv: 'política de privacidade', termos_fim: ' do teste.',
      botao_aceitar: 'Criar conta e entrar',
      criando_conta: 'Criando a conta…',
      aviso_titulo: 'Antes de começar',
      aviso_teste: 'O Vlado está em teste. Use só documentos públicos: trechos são enviados ao provedor de IA.',
      erro_termos: 'Falta aceitar os termos. Marque a caixa para continuar.',
      erro_registro: 'Registro de acesso indisponível. Avise a administração.',
      convite_sem_efeito: 'Este convite não vale mais',
      convite_sem_efeito_texto: 'Convite inválido, cancelado ou vencido. Peça um novo a quem convidou.',
      ir_entrada: 'Ir para a entrada',
      esqueci_titulo: 'Criar uma senha nova',
      rotulo_email: 'E-mail',
      botao_enviar_link: 'Enviar link',
      enviando: 'Enviando…',
      voltar_entrada: 'Voltar para a entrada',
      esqueci_enviado: 'Se houver uma conta com esse e-mail, enviamos um link para criar uma senha nova. Ele vale por 1 hora e uma única vez. Confira também a caixa de spam.',
      esqueci_nota: 'Entra com um login antigo, sem e-mail? Fale com quem administra o serviço.',
      erro_email_vazio: 'Falta o e-mail. Escreva o e-mail da sua conta.',
      titulo_redefinir: 'Crie uma senha nova',
      rotulo_senha_nova: 'Senha nova',
      botao_redefinir: 'Salvar a senha nova',
      titulo_redefinido: 'Senha nova salva',
      redefinido: 'As sessões abertas desta conta foram encerradas. Entre com a senha nova.',
      nova_aba: 'abre em nova aba',
      link_sem_efeito: 'Este link não vale mais',
      link_sem_efeito_texto: 'Link inválido, usado ou vencido. Peça outro em Esqueci a senha.',
      pedir_outro: 'Pedir outro link',
      titulo_email: 'E-mail confirmado',
      email_confirmado: 'O e-mail da sua conta foi trocado. Use o novo e-mail para entrar.',
      email_link_texto: 'Link inválido, usado ou vencido. Peça outro em Minha conta.',
      ir_mesa: 'Ir para a Mesa',
      titulo_confirmar: 'Confirmar o e-mail',
    },
    en: {
      titulo_pagina: 'Sign in · Vlado', titulo_entrar: 'Sign in',
      intro_entrar: 'Use your account login and password.', rotulo_login: 'Login', rotulo_senha: 'Password',
      mostrar: 'Show', ocultar: 'Hide', botao_entrar: 'Sign in', entrando: 'Signing in…',
      titulo_ativar: 'Set your password',
      intro_ativar: 'This link works only once. Choose a password with at least 12 characters.',
      rotulo_nova: 'New password', rotulo_confirmar: 'Repeat the new password',
      dica_senha: '12 to 256 characters. A long phrase is easier to remember.',
      botao_ativar: 'Set password', salvando: 'Saving…', ir_entrar: 'Sign in with the new password',
      idioma: 'Português', idioma_rotulo: 'Mudar para português',
      tema_claro: 'Light mode', tema_escuro: 'Dark mode',
      erro_credenciais: 'E-mail or login and password do not match. Check and try again.',
      erro_bloqueado: 'Too many attempts. Wait a few minutes and try again.',
      rotulo_email_login: 'E-mail or login',
      erro_login_vazio: 'The e-mail or login is missing. Write the e-mail of your account (or the login, if it is an old one).',
      erro_senha_vazia: 'The password is missing. Use the password of your account.',
      erro_nome_vazio: 'The name is missing. Write your name.',
      erro_login_regra: 'Invalid login. Use 3 to 64 characters: lowercase letters, numbers, dot, hyphen or underscore, starting with a letter or number.',
      erro_ativacao: 'This activation link is invalid, already used or expired. Ask the administrators for a new one.',
      erro_senha_tamanho: 'The password must have 12 to 256 characters.',
      erro_senha_diferente: 'The two passwords do not match. Type the same password in both fields.',
      erro_indisponivel: 'Access is unavailable right now. Tell the administrators.',
      erro_rede: 'No connection to the server. Check the network and try again.',
      erro_geral: 'Could not finish. Reload the page and try again.',
      senha_definida: 'Password set. Now sign in with your login and the new password.',
      titulo_primeiro: 'Create administrator', rotulo_nome: 'Name',
      intro_primeiro: 'First time Vlado opens on this computer. Create the administrator account; from then on the desk always asks for login and password.',
      dica_login: '3 to 64 lowercase letters, digits, dot, hyphen or underscore.',
      rotulo_confirmar_senha: 'Repeat the password', botao_primeiro: 'Create administrator', criando: 'Creating…',
      ir_entrar_conta: 'Sign in with the new account', erro_nome_login: 'Enter a valid name and login.',
      erro_primeiro_encerrado: 'The administrator account already exists. Sign in with login and password.',
      erro_primeiro_local: 'This screen only works on this computer, at http://127.0.0.1.',
      admin_criado: 'Administrator created. Now sign in with the login and password.',
      esqueci: 'Forgot your password? Talk to whoever runs the service.',
      esqueci_link: 'Forgot password',
      frase_marca: 'Documentary reporting with the source of every claim in sight.',
      teste_titulo: 'Vlado is in trial with invited newsrooms',
      teste_texto: 'Access comes by invitation, at your newsroom e-mail. Got one? Open the invitation link to create the account.',
      rodape_texto: 'Use public documents only. Excerpts are sent to the AI provider for analysis.',
      carregando: 'Loading…',
      rubrica_convite: 'INVITATION',
      titulo_aceitar: 'Join {redacao}',
      convite_antes: '{quem} invited ',
      convite_depois: ' as {papel}.',
      convite_validade: 'Invitation valid until {data}',
      papel_dono: 'Owner',
      papel_editor: 'Editor',
      papel_reporter: 'Reporter',
      papel_leitor: 'Reader',
      papel_convidado: 'Guest',
      rotulo_seu_nome: 'Your name',
      rotulo_crie_senha: 'Create a password',
      dica_senha_convite: '12 to 256 characters. You can paste or use a password manager.',
      termos_antes: 'I have read and accept the ', termos_uso: 'terms of use', termos_e: ' and the ', termos_priv: 'privacy policy', termos_fim: ' of the trial.',
      botao_aceitar: 'Create account and sign in',
      criando_conta: 'Creating the account…',
      aviso_titulo: 'Before you start',
      aviso_teste: 'Vlado is in trial. Use public documents only: excerpts are sent to the AI provider.',
      erro_termos: 'The terms are not accepted. Tick the box to continue.',
      erro_registro: 'The access record is unavailable. Tell the administrators.',
      convite_sem_efeito: 'This invitation is no longer valid',
      convite_sem_efeito_texto: 'Invalid, cancelled or expired invitation. Ask whoever invited you for a new one.',
      ir_entrada: 'Go to sign in',
      esqueci_titulo: 'Create a new password',
      rotulo_email: 'E-mail',
      botao_enviar_link: 'Send link',
      enviando: 'Sending…',
      voltar_entrada: 'Back to sign in',
      esqueci_enviado: 'If an account has this e-mail, we sent a link to create a new password. It works for 1 hour and only once. Check your spam folder too.',
      esqueci_nota: 'Sign in with an old login, without e-mail? Talk to whoever runs the service.',
      erro_email_vazio: 'The e-mail is missing. Write the e-mail of your account.',
      titulo_redefinir: 'Create a new password',
      rotulo_senha_nova: 'New password',
      botao_redefinir: 'Save the new password',
      titulo_redefinido: 'New password saved',
      redefinido: 'The open sessions of this account were ended. Sign in with the new password.',
      nova_aba: 'opens in a new tab',
      link_sem_efeito: 'This link is no longer valid',
      link_sem_efeito_texto: 'Invalid, used or expired link. Ask for another one in Forgot password.',
      pedir_outro: 'Ask for another link',
      titulo_email: 'E-mail confirmed',
      email_confirmado: 'The e-mail of your account was changed. Use the new e-mail to sign in.',
      email_link_texto: 'Invalid, used or expired link. Ask for another one in My account.',
      ir_mesa: 'Go to the desk',
      titulo_confirmar: 'Confirm the e-mail',
    },
  };
  const CHAVE_IDIOMA = 'vlado-idioma';  // shared with i18n.js
  const CHAVE_TEMA = 'apuracao:tema';   // shared with desktop.js
  const ler = chave => { try { return localStorage.getItem(chave) || ''; } catch (_) { return ''; } };
  const gravar = (chave, valor) => { try { localStorage.setItem(chave, valor); } catch (_) { /* Still switches. */ } };
  let lingua = ler(CHAVE_IDIOMA) === 'en' ? 'en' : 'pt';
  let ultimaMensagem = null;
  let redesenhar = null;   // o texto montado em JS da seção aberta (convite, estados); refeito ao trocar o idioma
  const t = chave => TEXTOS[lingua][chave] || TEXTOS.pt[chave] || chave;

  function aplicarIdioma() {
    document.documentElement.lang = lingua === 'en' ? 'en' : 'pt-BR';
    document.title = t('titulo_pagina');
    document.querySelectorAll('[data-t]').forEach(no => {
      const chave = no.classList.contains('entrar-mostrar') && no.getAttribute('aria-pressed') === 'true' ? 'ocultar' : no.dataset.t;
      no.textContent = t(chave);
    });
    // Link que abre em outra aba diz isso no nome acessível.
    document.querySelectorAll('[data-nova-aba]').forEach(link => link.setAttribute('aria-label', `${link.textContent} (${t('nova_aba')})`));
    const botao = $('entrar-idioma');
    botao.textContent = t('idioma');
    botao.setAttribute('aria-label', t('idioma_rotulo'));
    if (ultimaMensagem?.campo) { if (ultimaMensagem.campo._estadoErro) mostrarNoCampo(ultimaMensagem.chave, ultimaMensagem.campo, false); }
    else if (ultimaMensagem) mostrar(ultimaMensagem.chave, ultimaMensagem.ok, false);
    redesenhar?.();
    aplicarTema(document.documentElement.dataset.theme);
  }
  function aplicarTema(valor) {
    const escuro = valor ? valor === 'dark' : !!(window.matchMedia && matchMedia('(prefers-color-scheme: dark)').matches);
    document.documentElement.dataset.theme = escuro ? 'dark' : 'light';
    $('entrar-tema').textContent = t(escuro ? 'tema_claro' : 'tema_escuro');
    const fundo = getComputedStyle(document.documentElement).getPropertyValue('--theme-background').trim();
    const meta = document.querySelector('meta[name="theme-color"]');
    if (fundo && meta) meta.content = fundo;
  }
  // Erro de preenchimento junto ao campo (W11 regra 5; Estados.erroCampo): mensagem logo depois do campo, aria-invalid, aria-describedby e foco.
  // A mensagem do servidor (senha errada, bloqueio, rede) continua na caixa de aviso: ela não diz qual dos dois campos está errado.
  function mostrarNoCampo(chave, campo, focar = true) {
    mostrar(null);
    const aviso = window.Estados.erroCampo(campo, t(chave), {foco: focar});
    (campo.closest('.entrar-campo') || campo.closest('label'))?.after(aviso);   // fora do <label>, para não entrar no nome do campo
    ultimaMensagem = {chave, campo};
  }
  function mostrar(chave, ok = false, focar = true) {
    const caixa = $('entrar-mensagem');
    if (ultimaMensagem?.campo) window.Estados.limparErroCampo(ultimaMensagem.campo);
    ultimaMensagem = chave ? {chave, ok} : null;
    caixa.textContent = chave ? t(chave) : '';
    caixa.hidden = !chave;
    caixa.classList.toggle('ok', ok);
    caixa.setAttribute('role', ok ? 'status' : 'alert');
    if (chave && focar) caixa.focus();
  }
  async function enviar(operacao, dados) {
    const resposta = await fetch(`/api/${operacao}`, {method: 'POST', credentials: 'same-origin',
      headers: {'Content-Type': 'application/json'}, body: JSON.stringify(dados)});
    let corpo = {};
    try { corpo = await resposta.json(); } catch (_) { /* Empty or non-JSON answer. */ }
    return {status: resposta.status, corpo};
  }
  function erroPara(status, corpo) {
    if (status === 429 || corpo.codigo === 'bloqueado') return 'erro_bloqueado';
    if (status === 401 || corpo.codigo === 'credenciais') return 'erro_credenciais';
    if (status === 503) return 'erro_indisponivel';
    if (corpo.codigo === 'ativacao_invalida') return 'erro_ativacao';
    if (corpo.codigo === 'senha_invalida') return 'erro_senha_tamanho';
    if (corpo.codigo === 'senha_diferente') return 'erro_senha_diferente';
    if (corpo.codigo === 'primeiro_acesso_encerrado') return 'erro_primeiro_encerrado';
    if (corpo.codigo === 'dados_invalidos') return 'erro_nome_login';
    if (status === 403) return 'erro_primeiro_local';
    return 'erro_geral';
  }
  function ocupado(botao, ativo, chave) {
    botao.disabled = ativo;
    botao.setAttribute('aria-busy', String(ativo));
    botao.textContent = t(ativo ? chave : botao.dataset.t);
  }
  document.querySelectorAll('.entrar-mostrar').forEach(botao => botao.addEventListener('click', () => {
    const campo = $(botao.getAttribute('aria-controls'));
    const visivel = campo.type === 'password';
    campo.type = visivel ? 'text' : 'password';
    botao.setAttribute('aria-pressed', String(visivel));
    botao.textContent = t(visivel ? 'ocultar' : 'mostrar');
    campo.focus();
  }));

  async function iniciarEntrar() {
    $('entrar-secao').hidden = false; $('entrar-teste').hidden = false;
    try {  // Already signed in: go straight to the desk.
      const sessao = await fetch('/api/sessao', {credentials: 'same-origin'});
      if (sessao.ok) { window.location.replace('/'); return; }
    } catch (_) { /* Offline: the form still shows. */ }
    try {  // "Esqueci a senha" só existe com envio de e-mail de verdade; sem ele (ou se a leitura falhar) fica o texto.
      const entrada = await fetch('/api/entrada', {credentials: 'same-origin'});
      const ligado = entrada.ok && (await entrada.json()).esqueci_senha === true;
      $('entrar-esqueci').hidden = !ligado; $('entrar-esqueci-texto').hidden = ligado;
    } catch (_) { /* O texto continua. */ }
    $('entrar-login').focus();
    $('entrar-form').addEventListener('submit', async evento => {
      evento.preventDefault();
      const login = $('entrar-login').value.trim(), senha = $('entrar-senha').value;
      if (!login) { mostrarNoCampo('erro_login_vazio', $('entrar-login')); return; }   // com os dois em branco, a mensagem vai no login
      if (!senha) { mostrarNoCampo('erro_senha_vazia', $('entrar-senha')); return; }
      const botao = $('entrar-enviar');
      ocupado(botao, true, 'entrando');
      try {
        const {status, corpo} = await enviar('entrar', {login, senha, cliente: 'web'});
        if (status === 200) {
          const destino = typeof corpo.destino === 'string' && /^\/(?![/\\])/.test(corpo.destino) ? corpo.destino : '/';
          window.location.replace(destino);
          return;
        }
        $('entrar-senha').value = '';
        mostrar(erroPara(status, corpo));
      } catch (_) {
        mostrar('erro_rede');
      }
      ocupado(botao, false);
    });
  }

  async function iniciarAtivar(token) {
    $('ativar-secao').hidden = false;
    const botao = $('ativar-enviar');
    try {
      const {status, corpo} = await enviar('ativacao-consultar', {token});
      if (status !== 200) { $('ativar-form').hidden = true; mostrar(erroPara(status, corpo)); $('ativar-pronto').hidden = false; return; }
      $('ativar-login').value = corpo.login;
    } catch (_) { mostrar('erro_rede'); }
    $('ativar-senha').focus();
    $('ativar-form').addEventListener('submit', async evento => {
      evento.preventDefault();
      const senha = $('ativar-senha').value;
      if (senha.length < 12 || senha.length > 256) { mostrarNoCampo('erro_senha_tamanho', $('ativar-senha')); return; }
      if (senha !== $('ativar-confirmar').value) { mostrarNoCampo('erro_senha_diferente', $('ativar-confirmar')); return; }
      ocupado(botao, true, 'salvando');
      try {
        const {status, corpo} = await enviar('ativar', {token, senha});
        if (status === 200) {
          $('ativar-form').hidden = true;
          $('ativar-pronto').hidden = false;
          mostrar('senha_definida', true);
          return;
        }
        mostrar(erroPara(status, corpo));
      } catch (_) {
        mostrar('erro_rede');
      }
      ocupado(botao, false);
    });
  }

  function iniciarPrimeiro() {
    $('primeiro-secao').hidden = false;
    const botao = $('primeiro-enviar');
    $('primeiro-nome').focus();
    $('primeiro-form').addEventListener('submit', async evento => {
      evento.preventDefault();
      const nome = $('primeiro-nome').value.trim(), login = $('primeiro-login').value.trim().toLowerCase();
      const senha = $('primeiro-senha').value, confirmacao = $('primeiro-confirmar').value;
      if (!nome) { mostrarNoCampo('erro_nome_vazio', $('primeiro-nome')); return; }
      if (!/^[a-z0-9][a-z0-9._-]{2,63}$/.test(login)) { mostrarNoCampo('erro_login_regra', $('primeiro-login')); return; }
      if (senha.length < 12 || senha.length > 256) { mostrarNoCampo('erro_senha_tamanho', $('primeiro-senha')); return; }
      if (senha !== confirmacao) { mostrarNoCampo('erro_senha_diferente', $('primeiro-confirmar')); return; }
      ocupado(botao, true, 'criando');
      try {
        const {status, corpo} = await enviar('primeiro-admin', {nome, login, senha, confirmacao});
        if (status === 200) {
          $('primeiro-form').hidden = true;
          $('primeiro-pronto').hidden = false;
          mostrar('admin_criado', true);
          return;
        }
        if (status === 410) { $('primeiro-form').hidden = true; $('primeiro-pronto').hidden = false; }
        mostrar(erroPara(status, corpo));
      } catch (_) {
        mostrar('erro_rede');
      }
      ocupado(botao, false);
    });
  }

  // --- Seções do convite, da senha esquecida e do e-mail (docs/design/componentes.md#aceitar-convite) -------------------------------------------
  // O servidor decide tudo; texto digitado por alguém (redação, quem convidou, e-mail) entra só por textContent, nunca como HTML nem como link.
  const MESES = {pt: ['jan.', 'fev.', 'mar.', 'abr.', 'mai.', 'jun.', 'jul.', 'ago.', 'set.', 'out.', 'nov.', 'dez.'],
    en: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']};
  function dataCurta(iso) {
    const dia = new Date(iso);
    if (!iso || Number.isNaN(dia.getTime())) return '';
    return lingua === 'en' ? `${MESES.en[dia.getMonth()]} ${dia.getDate()}` : `${dia.getDate()} de ${MESES.pt[dia.getMonth()]}`;
  }
  const modelo = (chave, valores) => t(chave).replace(/\{(\w+)\}/g, (todo, nome) => (nome in valores ? valores[nome] : todo));
  function secao(id) {
    for (const outra of document.querySelectorAll('main > section')) outra.hidden = outra.id !== id;
    $('entrar-teste').hidden = id !== 'entrar-secao';   // o aviso de teste é só da entrada
  }
  const destinoSeguro = destino => (typeof destino === 'string' && /^\/(?![/\\])/.test(destino) ? destino : '/');
  // Esconde o token do endereço e do histórico: fica só na memória desta página.
  function esconderToken(caminho) { try { history.replaceState(null, '', caminho); } catch (_) { /* Old browsers keep the address. */ } }
  const campoVazio = nome => !nome.trim();

  // Esqueci a senha: a resposta é sempre a mesma; sem transporte de e-mail (`tela`) o link nem aparece (GET /api/entrada).
  function abrirEsqueci() {
    secao('esqueci-secao'); mostrar(null);
    $('esqueci-form').hidden = false; $('esqueci-enviado').hidden = true;
    $('esqueci-email').focus();
  }
  $('entrar-esqueci').addEventListener('click', abrirEsqueci);
  $('esqueci-voltar').addEventListener('click', evento => {
    if (!['/entrar', '/'].includes(window.location.pathname)) return;  // em outra página o link é navegação comum
    evento.preventDefault(); mostrar(null); secao('entrar-secao'); $('entrar-login').focus();
  });
  $('esqueci-form').addEventListener('submit', async evento => {
    evento.preventDefault();
    const email = $('esqueci-email').value.trim();
    if (!email) { mostrarNoCampo('erro_email_vazio', $('esqueci-email')); return; }
    const botao = $('esqueci-enviar');
    ocupado(botao, true, 'enviando');
    try {
      const {status, corpo} = await enviar('senha-esqueci', {email});
      if (status === 200) {
        mostrar(null);
        $('esqueci-form').hidden = true; $('esqueci-enviado').hidden = false;
        $('esqueci-resposta').tabIndex = -1; $('esqueci-resposta').focus();
        ocupado(botao, false);
        return;
      }
      if (corpo.codigo === 'transporte_indisponivel') mostrar('esqueci');  // o mesmo texto de quando o link nem aparece
      else mostrar(status === 503 ? 'erro_registro' : erroPara(status, corpo));
    } catch (_) {
      mostrar('erro_rede');
    }
    ocupado(botao, false);
  });

  // Aceitar convite (/aceitar/<token>): consulta, mostra o convite e cria a conta com a primeira sessão.
  function semEfeitoConvite() {
    $('aceitar-form').hidden = true; $('aceitar-rubrica').hidden = true; $('aceitar-validade').hidden = true;
    $('aceitar-sair').hidden = false; $('aceitar-cartao').hidden = false;
    redesenhar = () => {
      $('aceitar-titulo').textContent = t('convite_sem_efeito');
      $('aceitar-texto').textContent = t('convite_sem_efeito_texto');
    };
    redesenhar(); $('aceitar-titulo').tabIndex = -1; $('aceitar-titulo').focus();
  }
  async function iniciarAceitar(token) {
    secao('aceitar-secao');
    if (!token) { semEfeitoConvite(); return; }   // recarregada depois de o token sair do endereço
    esconderToken('/aceitar');
    const espera = window.Estados.esqueleto($('aceitar-espera'), {rotulo: t('carregando')});
    let convite = null;
    try {
      const {status, corpo} = await enviar('convite-consultar', {token});
      espera.parar();
      if (status === 200) convite = corpo;
      else if (corpo.codigo === 'convite_invalido') { semEfeitoConvite(); return; }
      else { $('aceitar-form').hidden = true; $('aceitar-cartao').hidden = false; $('aceitar-sair').hidden = false; mostrar(status === 503 ? 'erro_registro' : erroPara(status, corpo)); return; }
    } catch (_) {
      espera.parar(); $('aceitar-cartao').hidden = false; $('aceitar-form').hidden = true; $('aceitar-sair').hidden = false; mostrar('erro_rede'); return;
    }
    if (convite.idioma === 'en' || convite.idioma === 'pt') { lingua = convite.idioma; }   // a página fala o idioma do convite
    const email = document.createElement('strong'); email.textContent = convite.email; email.setAttribute('translate', 'no');
    redesenhar = () => {
      $('aceitar-titulo').textContent = modelo('titulo_aceitar', {redacao: String(convite.redacao ?? '')});
      const quem = String(convite.convidado_por ?? ''), papel = t(`papel_${convite.papel}`);
      $('aceitar-texto').replaceChildren(modelo('convite_antes', {quem}), email, modelo('convite_depois', {papel}));
      $('aceitar-validade').textContent = convite.expira_em ? modelo('convite_validade', {data: dataCurta(convite.expira_em)}) : '';
      $('aceitar-validade').hidden = !convite.expira_em;
    };
    $('aceitar-email').value = convite.email;
    $('aceitar-termos-rotulo').hidden = convite.termos_versao === null || convite.termos_versao === undefined;
    $('aceitar-cartao').hidden = false;
    aplicarIdioma();
    $('aceitar-nome').focus();
    $('aceitar-form').addEventListener('submit', async evento => {
      evento.preventDefault();
      const nome = $('aceitar-nome').value.trim(), senha = $('aceitar-senha').value;
      const comTermos = !$('aceitar-termos-rotulo').hidden;
      if (campoVazio(nome)) { mostrarNoCampo('erro_nome_vazio', $('aceitar-nome')); return; }
      if (senha.length < 12 || senha.length > 256) { mostrarNoCampo('erro_senha_tamanho', $('aceitar-senha')); return; }
      if (comTermos && !$('aceitar-termos').checked) { mostrarNoCampo('erro_termos', $('aceitar-termos')); return; }
      const botao = $('aceitar-enviar');
      ocupado(botao, true, 'criando_conta');
      try {
        const dados = {token, nome, senha, cliente: 'web'};
        if (comTermos) dados.termos_versao = convite.termos_versao;
        const {status, corpo} = await enviar('convite-aceitar', dados);
        if (status === 200) { window.location.replace(destinoSeguro(corpo.destino)); return; }
        if (corpo.codigo === 'convite_invalido') { semEfeitoConvite(); return; }
        if (corpo.codigo === 'senha_invalida') mostrarNoCampo('erro_senha_tamanho', $('aceitar-senha'));
        else if (status === 400 && /nome/i.test(String(corpo.erro || ''))) mostrarNoCampo('erro_nome_vazio', $('aceitar-nome'));
        else mostrar(status === 503 ? 'erro_registro' : erroPara(status, corpo));
      } catch (_) {
        mostrar('erro_rede');
      }
      ocupado(botao, false);
    });
  }

  // Redefinir a senha (/redefinir/<token>): não abre sessão; a pessoa entra depois, pelo Entrar.
  function semEfeitoRedefinir() {
    $('redefinir-form').hidden = true; $('redefinir-pronto').hidden = true; $('redefinir-sem-efeito').hidden = false;
    $('redefinir-titulo').dataset.t = 'link_sem_efeito'; $('redefinir-titulo').textContent = t('link_sem_efeito');
    $('redefinir-titulo').tabIndex = -1; $('redefinir-titulo').focus();
  }
  $('redefinir-outro').addEventListener('click', evento => { evento.preventDefault(); abrirEsqueci(); });
  $('redefinir-entrar').addEventListener('click', () => window.location.assign('/entrar'));
  function iniciarRedefinir(token) {
    secao('redefinir-secao');
    if (!token) { semEfeitoRedefinir(); return; }
    esconderToken('/redefinir');
    $('redefinir-senha').focus();
    $('redefinir-form').addEventListener('submit', async evento => {
      evento.preventDefault();
      const senha = $('redefinir-senha').value;
      if (senha.length < 12 || senha.length > 256) { mostrarNoCampo('erro_senha_tamanho', $('redefinir-senha')); return; }
      const botao = $('redefinir-enviar');
      ocupado(botao, true, 'salvando');
      try {
        const {status, corpo} = await enviar('senha-redefinir', {token, senha});
        if (status === 200) {
          $('redefinir-senha').value = '';
          mostrar(null); $('redefinir-form').hidden = true; $('redefinir-pronto').hidden = false;
          $('redefinir-titulo').dataset.t = 'titulo_redefinido'; $('redefinir-titulo').textContent = t('titulo_redefinido');
          $('redefinir-entrar').focus();
          return;
        }
        if (corpo.codigo === 'link_invalido') { semEfeitoRedefinir(); return; }
        if (corpo.codigo === 'senha_invalida') mostrarNoCampo('erro_senha_tamanho', $('redefinir-senha'));
        else mostrar(status === 503 ? 'erro_registro' : erroPara(status, corpo));
      } catch (_) {
        mostrar('erro_rede');
      }
      ocupado(botao, false);
    });
  }

  // Confirmar o e-mail novo (/confirmar-email/<token>): o link é o próprio pedido; a sessão aberta continua.
  async function iniciarConfirmar(token) {
    secao('confirmar-secao');
    const mostrarResultado = (ok, destino, chaveDestino) => {
      $('confirmar-cartao').hidden = false;
      redesenhar = () => {
        $('confirmar-titulo').textContent = t(ok === null ? 'titulo_confirmar' : ok ? 'titulo_email' : 'link_sem_efeito');
        $('confirmar-texto').textContent = ok === null ? '' : t(ok ? 'email_confirmado' : 'email_link_texto');
        $('confirmar-destino').textContent = t(chaveDestino);
      };
      $('confirmar-destino').href = destino;
      redesenhar(); $('confirmar-titulo').tabIndex = -1; $('confirmar-titulo').focus();
    };
    if (!token) { mostrarResultado(false, '/entrar', 'ir_entrada'); return; }
    esconderToken('/confirmar-email');
    const espera = window.Estados.esqueleto($('confirmar-espera'), {rotulo: t('carregando')});
    try {
      const {status, corpo} = await enviar('email-confirmar', {token});
      espera.parar();
      if (status === 200) { mostrarResultado(true, '/', 'ir_mesa'); return; }
      if (corpo.codigo === 'link_invalido') { mostrarResultado(false, '/entrar', 'ir_entrada'); return; }
      mostrarResultado(null, '/entrar', 'ir_entrada');
      mostrar(status === 503 ? 'erro_registro' : erroPara(status, corpo));
    } catch (_) {
      espera.parar(); mostrarResultado(null, '/entrar', 'ir_entrada'); mostrar('erro_rede');
    }
  }

  $('entrar-idioma').addEventListener('click', () => {
    lingua = lingua === 'en' ? 'pt' : 'en';
    gravar(CHAVE_IDIOMA, lingua);
    aplicarIdioma();
  });
  $('entrar-tema').addEventListener('click', () => {
    const tema = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    gravar(CHAVE_TEMA, tema);
    aplicarTema(tema);
  });
  aplicarTema(ler(CHAVE_TEMA));
  aplicarIdioma();
  const rotaConvite = window.location.pathname.match(/^\/(aceitar|redefinir|confirmar-email)(?:\/([A-Za-z0-9_-]{1,100}))?$/);
  const ativacao = window.location.pathname.match(/^\/ativar\/([A-Za-z0-9_-]{1,100})$/);
  if (window.location.pathname === '/ativar') {  // reloaded after the token was removed from the address
    $('ativar-secao').hidden = false;
    $('ativar-form').hidden = true;
    $('ativar-pronto').hidden = false;
    mostrar('erro_ativacao', false, false);
  } else if (window.location.pathname === '/primeiro-acesso') {
    iniciarPrimeiro();
  } else if (rotaConvite) {
    const [, rota, token] = rotaConvite;
    if (rota === 'aceitar') iniciarAceitar(token);
    else if (rota === 'redefinir') iniciarRedefinir(token);
    else iniciarConfirmar(token);
  } else if (ativacao) {
    // The token leaves the address bar and the history right away; it stays only in this page's memory.
    try { history.replaceState(null, '', '/ativar'); } catch (_) { /* Old browsers keep the address. */ }
    iniciarAtivar(ativacao[1]);
  } else {
    iniciarEntrar();
  }
})();
