'use strict';
// Sign-in (/entrar) and set-password (/ativar/<token>) pages. No external resources, no case data.
// The server decides everything; messages here stay generic on purpose.
(() => {
  const $ = id => document.getElementById(id);
  const TEXTOS = {
    pt: {
      titulo_pagina: 'Entrar · Vlado', titulo_entrar: 'Entrar na Mesa de apuração',
      intro_entrar: 'Use o login e a senha da sua conta.', rotulo_login: 'Login', rotulo_senha: 'Senha',
      mostrar: 'Mostrar', ocultar: 'Ocultar', botao_entrar: 'Entrar', entrando: 'Entrando…',
      esqueci: 'Esqueceu a senha? Peça à administração um novo link de acesso.',
      titulo_ativar: 'Definir sua senha',
      intro_ativar: 'Este link vale uma única vez. Escolha uma senha com pelo menos 12 caracteres.',
      rotulo_nova: 'Nova senha', rotulo_confirmar: 'Repita a nova senha',
      dica_senha: 'De 12 a 256 caracteres. Uma frase longa é mais fácil de lembrar.',
      botao_ativar: 'Definir senha', salvando: 'Salvando…', ir_entrar: 'Entrar com a nova senha',
      idioma: 'English', idioma_rotulo: 'Switch to English',
      tema_claro: 'Modo claro', tema_escuro: 'Modo escuro',
      erro_credenciais: 'Login ou senha incorretos.',
      erro_bloqueado: 'Muitas tentativas. Aguarde alguns minutos e tente de novo.',
      erro_login_vazio: 'Falta o login. Use o login da sua conta.',
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
    },
    en: {
      titulo_pagina: 'Sign in · Vlado', titulo_entrar: 'Sign in to the investigation desk',
      intro_entrar: 'Use your account login and password.', rotulo_login: 'Login', rotulo_senha: 'Password',
      mostrar: 'Show', ocultar: 'Hide', botao_entrar: 'Sign in', entrando: 'Signing in…',
      esqueci: 'Forgot your password? Ask the administrators for a new access link.',
      titulo_ativar: 'Set your password',
      intro_ativar: 'This link works only once. Choose a password with at least 12 characters.',
      rotulo_nova: 'New password', rotulo_confirmar: 'Repeat the new password',
      dica_senha: '12 to 256 characters. A long phrase is easier to remember.',
      botao_ativar: 'Set password', salvando: 'Saving…', ir_entrar: 'Sign in with the new password',
      idioma: 'Português', idioma_rotulo: 'Mudar para português',
      tema_claro: 'Light mode', tema_escuro: 'Dark mode',
      erro_credenciais: 'Incorrect login or password.',
      erro_bloqueado: 'Too many attempts. Wait a few minutes and try again.',
      erro_login_vazio: 'The login is missing. Use the login of your account.',
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
    },
  };
  const CHAVE_IDIOMA = 'vlado-idioma';  // shared with i18n.js
  const CHAVE_TEMA = 'apuracao:tema';   // shared with desktop.js
  const ler = chave => { try { return localStorage.getItem(chave) || ''; } catch (_) { return ''; } };
  const gravar = (chave, valor) => { try { localStorage.setItem(chave, valor); } catch (_) { /* Still switches. */ } };
  let lingua = ler(CHAVE_IDIOMA) === 'en' ? 'en' : 'pt';
  let ultimaMensagem = null;
  const t = chave => TEXTOS[lingua][chave] || TEXTOS.pt[chave] || chave;

  function aplicarIdioma() {
    document.documentElement.lang = lingua === 'en' ? 'en' : 'pt-BR';
    document.title = t('titulo_pagina');
    document.querySelectorAll('[data-t]').forEach(no => {
      const chave = no.classList.contains('entrar-mostrar') && no.getAttribute('aria-pressed') === 'true' ? 'ocultar' : no.dataset.t;
      no.textContent = t(chave);
    });
    const botao = $('entrar-idioma');
    botao.textContent = t('idioma');
    botao.setAttribute('aria-label', t('idioma_rotulo'));
    if (ultimaMensagem?.campo) { if (ultimaMensagem.campo._estadoErro) mostrarNoCampo(ultimaMensagem.chave, ultimaMensagem.campo, false); }
    else if (ultimaMensagem) mostrar(ultimaMensagem.chave, ultimaMensagem.ok, false);
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
    campo.closest('label')?.after(aviso);   // fora do <label>, para não entrar no nome do campo
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
    $('entrar-secao').hidden = false;
    try {  // Already signed in: go straight to the desk.
      const sessao = await fetch('/api/sessao', {credentials: 'same-origin'});
      if (sessao.ok) { window.location.replace('/'); return; }
    } catch (_) { /* Offline: the form still shows. */ }
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
  const ativacao = window.location.pathname.match(/^\/ativar\/([A-Za-z0-9_-]{1,100})$/);
  if (window.location.pathname === '/ativar') {  // reloaded after the token was removed from the address
    $('ativar-secao').hidden = false;
    $('ativar-form').hidden = true;
    $('ativar-pronto').hidden = false;
    mostrar('erro_ativacao', false, false);
  } else if (window.location.pathname === '/primeiro-acesso') {
    iniciarPrimeiro();
  } else if (ativacao) {
    // The token leaves the address bar and the history right away; it stays only in this page's memory.
    try { history.replaceState(null, '', '/ativar'); } catch (_) { /* Old browsers keep the address. */ }
    iniciarAtivar(ativacao[1]);
  } else {
    iniciarEntrar();
  }
})();
