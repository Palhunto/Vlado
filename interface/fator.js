'use strict';
// O segundo fator (E4a de Contas; docs/design/componentes.md#segundo-fator): o código QR e o cadastro em três passos, que servem ao diálogo de Minha conta e à página da
// pendência (/conta/segundo-fator). Não depende de dialogo.js nem de estados.js (a página da pendência é a do Entrar e não os carrega); o texto passa por I18N quando ele existe.
//
//   Fator.cadastro({alvo, trocar, chamar, aoCancelar, aoConcluir, travar})   os três passos dentro de `alvo`; devolve {parar()}
//   Fator.vistaDosCodigos(codigos, {aoGuardar})                               o passo 3 (e o de "Gerar novos códigos"): o bloco dos códigos, Copiar, Baixar e "Já guardei"
//   Fator.qrSvg(texto)                                                        o código QR como SVG em linha (carrega vendor/qrcodegen sob demanda)
//   Fator.pagina(alvo, {chamar, sair, abrirMesa})                             o conteúdo do cartão da página da pendência
//   Fator.chamadorDaSessao()                                                  `chamar` para quem não tem o `api` da Mesa: usa a sessão aberta e o token CSRF de GET /api/sessao
//
// O que o servidor manda uma vez só (a chave, o endereço otpauth, os códigos de reserva) fica na memória da tela e some quando ela some: nada vai para localStorage, histórico nem registro.
(() => {
  const t = (pt, vars) => (window.I18N ? window.I18N.t(pt, vars) : String(pt).replace(/\{(\w+)\}/g, (todo, nome) => vars?.[nome] ?? todo));
  const CAMINHO_DO_QR = '/vendor/qrcodegen/qrcodegen.js';
  const TEXTO_BLOQUEIO_DE_SENHA = 'Muitas senhas erradas seguidas. Por 15 minutos, as ações que pedem a senha ficam bloqueadas para a sua conta; o resto da Mesa continua.';
  const TEXTO_BLOQUEIO_DE_CODIGO = 'Muitos códigos errados seguidos. Por 15 minutos, as ações que pedem o código ficam bloqueadas para a sua conta.';
  const TEXTO_CODIGO_INCORRETO = 'Código incorreto. Confira no aplicativo e digite o código que aparece agora.';
  const COMECE_DE_NOVO = 'Comece de novo o cadastro do segundo fator.';
  const ARQUIVO_DOS_CODIGOS = 'vlado-codigos-de-reserva.txt';

  function no(etiqueta, classe, texto) {
    const elemento = document.createElement(etiqueta);
    if (classe) elemento.className = classe;
    if (texto !== undefined && texto !== null) elemento.textContent = texto;
    return elemento;
  }
  function botao(rotulo, classe, aoClicar) {
    const controle = no('button', classe, t(rotulo)); controle.type = 'button';
    if (aoClicar) controle.addEventListener('click', aoClicar);
    return controle;
  }

  // --- o código QR, sem biblioteca de fora: o gerador do Project Nayuki (MIT), do próprio servidor --------------------------------------------------------------
  let carregandoOQr = null;
  function carregarOQr() {
    if (window.qrcodegen) return Promise.resolve(window.qrcodegen);
    if (!carregandoOQr) {
      carregandoOQr = new Promise((resolver, falhar) => {
        const arquivo = document.createElement('script');
        arquivo.src = CAMINHO_DO_QR;
        arquivo.onload = () => (window.qrcodegen ? resolver(window.qrcodegen) : falhar(new Error('O gerador do código QR não carregou.')));
        arquivo.onerror = () => { carregandoOQr = null; falhar(new Error('O gerador do código QR não carregou.')); };
        document.head.append(arquivo);
      });
    }
    return carregandoOQr;
  }
  // SVG em linha: um <path> só, módulos quadrados de tamanho inteiro (crispEdges) e zona de silêncio de 4 módulos; escuro sobre claro nos dois temas (exceção aos tokens: o leitor do
  // celular precisa disso). O quadrado cabe em 200 px; o tamanho do módulo é o maior inteiro que cabe.
  async function qrSvg(texto, caixa = 200) {
    const qrcodegen = await carregarOQr();
    const qr = qrcodegen.QrCode.encodeText(texto, qrcodegen.QrCode.Ecc.MEDIUM);
    const borda = 4, modulos = qr.size + 2 * borda, lado = Math.max(1, Math.floor(caixa / modulos)) * modulos;
    const partes = [];
    for (let y = 0; y < qr.size; y++) for (let x = 0; x < qr.size; x++) if (qr.getModule(x, y)) partes.push(`M${x + borda},${y + borda}h1v1h-1z`);
    const NS = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('viewBox', `0 0 ${modulos} ${modulos}`); svg.setAttribute('width', String(lado)); svg.setAttribute('height', String(lado));
    svg.setAttribute('shape-rendering', 'crispEdges'); svg.setAttribute('role', 'img'); svg.setAttribute('class', 'fator-qr');
    svg.setAttribute('aria-label', t('Código QR para o aplicativo autenticador. Se não puder ler, use a chave em texto abaixo.'));
    const fundo = document.createElementNS(NS, 'rect');
    fundo.setAttribute('width', String(modulos)); fundo.setAttribute('height', String(modulos)); fundo.setAttribute('fill', '#ffffff');
    const caminho = document.createElementNS(NS, 'path');
    caminho.setAttribute('d', partes.join('')); caminho.setAttribute('fill', '#000000');
    svg.append(fundo, caminho);
    return svg;
  }

  // --- peças dos passos ---------------------------------------------------------------------------------------------------------------------------------------
  function campoDeTexto({rotulo, autocomplete = 'off', inputmode, maximo, apoio}) {
    const grupo = no('div', 'fator-campo');
    const nome = no('label', '', t(rotulo));
    const entrada = document.createElement('input'); entrada.type = 'text'; entrada.autocomplete = autocomplete; entrada.setAttribute('translate', 'no');
    entrada.setAttribute('spellcheck', 'false'); entrada.setAttribute('autocapitalize', 'none');
    if (inputmode) entrada.setAttribute('inputmode', inputmode);
    if (maximo) entrada.maxLength = maximo;
    const erro = no('p', 'fator-erro'); erro.hidden = true; erro.setAttribute('role', 'alert');
    entrada.setAttribute('aria-describedby', (erro.id = `fator-erro-${++sequencia}`));
    grupo.append(nome, entrada, erro);
    if (apoio) grupo.append(no('p', 'fator-apoio', t(apoio)));
    return {grupo, entrada, mostrarErro(mensagem) { erro.textContent = mensagem ? t(mensagem) : ''; erro.hidden = !mensagem; if (mensagem) entrada.setAttribute('aria-invalid', 'true'); else entrada.removeAttribute('aria-invalid'); }};
  }
  let sequencia = 0;
  function campoDeSenha(rotulo = 'Sua senha') {
    const base = campoDeTexto({rotulo, autocomplete: 'current-password', maximo: 256, apoio: 'A senha com que você entra na Mesa.'});
    base.entrada.type = 'password';
    const linha = no('div', 'fator-senha-linha');
    const mostrar = botao('Mostrar', 'secondary fator-mostrar', () => {
      const visivel = base.entrada.type === 'password';
      base.entrada.type = visivel ? 'text' : 'password'; mostrar.setAttribute('aria-pressed', String(visivel)); mostrar.textContent = t(visivel ? 'Ocultar' : 'Mostrar');
    });
    mostrar.setAttribute('aria-pressed', 'false');
    base.entrada.replaceWith(linha); linha.append(base.entrada, mostrar);
    // o erro vem antes do apoio, a 4 px do campo
    const erro = base.grupo.querySelector('.fator-erro'), apoio = base.grupo.querySelector('.fator-apoio');
    if (apoio && erro) base.grupo.insertBefore(erro, apoio);
    return base;
  }
  const chaveEmGrupos = segredo => (String(segredo).replace(/\s+/g, '').match(/.{1,4}/g) || []).join(' ');

  // O passo 3 e o de "Gerar novos códigos": os códigos aparecem uma vez; só "Já guardei" fecha.
  function vistaDosCodigos(codigos, {aoGuardar, texto: aviso, semGuardei = false} = {}) {
    const raiz = no('div', 'fator-passo');
    raiz.append(no('p', 'fator-texto', t(aviso || 'Cada código entra uma vez, se você perder o celular. Eles não aparecem de novo.')));
    const bloco = no('ul', 'fator-codigos');
    for (const codigo of codigos) { const item = no('li', 'fator-codigo', codigo); item.setAttribute('translate', 'no'); bloco.append(item); }
    const estado = no('p', 'fator-apoio'); estado.setAttribute('role', 'status');
    const copiar = botao('Copiar', 'secondary', async () => {
      try { await navigator.clipboard.writeText(codigos.join('\n')); estado.textContent = t('Códigos copiados.'); }
      catch (_) { estado.textContent = t('Não deu para copiar. Selecione os códigos e copie à mão.'); }
    });
    const baixar = botao('Baixar', 'secondary', () => {
      // Gerado no navegador, sem rede: um arquivo de texto com um código por linha.
      const arquivo = new Blob([`${codigos.join('\n')}\n`], {type: 'text/plain'});
      const endereco = URL.createObjectURL(arquivo), ancora = document.createElement('a');
      ancora.href = endereco; ancora.download = ARQUIVO_DOS_CODIGOS; ancora.rel = 'noopener';
      document.body.append(ancora); ancora.click(); ancora.remove();
      setTimeout(() => URL.revokeObjectURL(endereco), 1000);
      estado.textContent = t('Arquivo baixado.');
    });
    const acoes = no('div', 'fator-acoes'); acoes.append(copiar, baixar);
    raiz.append(bloco, acoes, estado);
    if (!semGuardei) {
      const guardei = botao('Já guardei', 'fator-guardei', () => aoGuardar?.());
      const fim = no('div', 'fator-acoes fator-acoes-fim'); fim.append(guardei);
      raiz.append(fim); raiz.guardei = guardei;
    }
    return raiz;
  }

  // --- o cadastro em três passos ---------------------------------------------------------------------------------------------------------------------------------
  function cadastro({alvo, trocar = false, chamar, aoCancelar, aoConcluir, travar}) {
    let vivo = true;
    const mostrar = (passo, ...conteudo) => {
      if (!vivo) return;
      const rubrica = no('p', 'fator-rubrica', t('PASSO {n} DE 3', {n: passo}));
      alvo.replaceChildren(rubrica, ...conteudo);
    };
    const acoesDoPasso = (...controles) => { const caixa = no('div', 'fator-acoes fator-acoes-fim'); caixa.append(...controles); return caixa; };
    const cancelar = () => (aoCancelar ? botao('Cancelar', 'secondary', () => aoCancelar()) : null);

    function passoDaSenha(aviso) {
      const texto = no('p', 'fator-texto', t('Confirme a sua senha para começar.'));
      const senha = campoDeSenha();
      const atual = trocar ? campoDeTexto({rotulo: 'Código do aparelho atual', autocomplete: 'one-time-code', maximo: 24, apoio: 'O aparelho atual vale até o novo ser confirmado.'}) : null;
      const erroGeral = no('p', 'fator-erro'); erroGeral.hidden = true; erroGeral.setAttribute('role', 'alert');
      const estado = no('p', 'fator-apoio'); estado.setAttribute('role', 'status'); estado.textContent = aviso ? t(aviso) : '';
      const continuar = botao('Continuar', 'fator-principal', async () => {
        senha.mostrarErro(''); atual?.mostrarErro(''); erroGeral.hidden = true;
        if (atual && !atual.entrada.value.trim()) { atual.mostrarErro('Falta o código do aparelho atual. Digite o código do aplicativo ou um código de reserva.'); atual.entrada.focus(); return; }
        continuar.disabled = true; continuar.textContent = t('Continuando…');
        try {
          const resposta = await chamar('conta-fator-iniciar', {senha: senha.entrada.value, ...(atual ? {codigo: atual.entrada.value.trim()} : {})});
          senha.entrada.value = '';  // a senha não fica na tela
          passoDoCodigo(resposta);
        } catch (falha) {
          continuar.textContent = t('Continuar'); continuar.disabled = !senha.entrada.value;
          const codigo = falha?.result?.codigo;
          if (codigo === 'senha_atual_incorreta') { senha.entrada.value = ''; senha.mostrarErro('Senha incorreta. Confira e tente de novo.'); senha.entrada.focus(); continuar.disabled = true; }
          else if (codigo === 'codigo_invalido' && atual) { atual.mostrarErro(TEXTO_CODIGO_INCORRETO); atual.entrada.focus(); }
          else if (codigo === 'bloqueado') { erroGeral.textContent = t(TEXTO_BLOQUEIO_DE_SENHA); erroGeral.hidden = false; continuar.disabled = true; }
          else { senha.entrada.value = ''; continuar.disabled = true; erroGeral.textContent = falha?.message || t('Não deu para concluir. Tente de novo.'); erroGeral.hidden = false; }
        }
      });
      continuar.disabled = true;
      senha.entrada.addEventListener('input', () => { continuar.disabled = !senha.entrada.value; });
      for (const campo of [senha, atual].filter(Boolean)) campo.entrada.addEventListener('keydown', evento => { if (evento.key === 'Enter' && !continuar.disabled) { evento.preventDefault(); continuar.click(); } });
      mostrar(1, texto, senha.grupo, ...(atual ? [atual.grupo] : []), erroGeral, estado, acoesDoPasso(...[cancelar(), continuar].filter(Boolean)));
      senha.entrada.focus();
    }

    async function passoDoCodigo({segredo, otpauth}) {
      const texto = no('p', 'fator-texto', t('Abra o aplicativo autenticador do celular e leia o código abaixo. Se não puder ler, digite a chave.'));
      const quadro = no('div', 'fator-qr-quadro');
      try { quadro.append(await qrSvg(otpauth)); }
      catch (_) { quadro.append(no('p', 'fator-apoio', t('Não deu para desenhar o código QR. Digite a chave abaixo no aplicativo.'))); }  // a chave em texto é a alternativa, e basta
      const rotuloDaChave = no('p', 'fator-chave-rotulo', t('Chave'));
      const chave = no('p', 'fator-chave', chaveEmGrupos(segredo)); chave.setAttribute('translate', 'no');
      const avisoDaChave = no('p', 'fator-apoio'); avisoDaChave.setAttribute('role', 'status');
      const copiar = botao('Copiar chave', 'secondary', async () => {
        try { await navigator.clipboard.writeText(String(segredo).replace(/\s+/g, '')); avisoDaChave.textContent = t('Chave copiada.'); }
        catch (_) { avisoDaChave.textContent = t('Não deu para copiar. Selecione a chave e copie à mão.'); }
      });
      const codigo = campoDeTexto({rotulo: 'Código de 6 dígitos', autocomplete: 'one-time-code', inputmode: 'numeric', maximo: 6, apoio: 'Este cadastro vale por 15 minutos. Depois, comece de novo.'});
      const erroGeral = no('p', 'fator-erro'); erroGeral.hidden = true; erroGeral.setAttribute('role', 'alert');
      const confirmar = botao('Confirmar', 'fator-principal', async () => {
        codigo.mostrarErro(''); erroGeral.hidden = true;
        confirmar.disabled = true; confirmar.textContent = t('Confirmando…');
        try {
          const resposta = await chamar('conta-fator-confirmar', {codigo: codigo.entrada.value.replace(/\s+/g, '')});
          passoDosCodigos(resposta.codigos_de_reserva || []);
        } catch (falha) {
          confirmar.textContent = t('Confirmar'); confirmar.disabled = !codigo.entrada.value;
          const aqui = falha?.result?.codigo;
          if (aqui === 'codigo_invalido') { codigo.mostrarErro(TEXTO_CODIGO_INCORRETO); codigo.entrada.select?.(); codigo.entrada.focus(); }
          else if (aqui === 'bloqueado') { erroGeral.textContent = t(TEXTO_BLOQUEIO_DE_CODIGO); erroGeral.hidden = false; confirmar.disabled = true; }
          else if ((falha?.result?.erro || falha?.message) === COMECE_DE_NOVO) { passoDaSenha(COMECE_DE_NOVO); }  // o cadastro passou de 15 minutos: volta ao passo 1
          else { erroGeral.textContent = falha?.message || t('Não deu para concluir. Tente de novo.'); erroGeral.hidden = false; }
        }
      });
      confirmar.disabled = true;
      codigo.entrada.addEventListener('input', () => { confirmar.disabled = !codigo.entrada.value.trim(); });
      codigo.entrada.addEventListener('keydown', evento => { if (evento.key === 'Enter' && !confirmar.disabled) { evento.preventDefault(); confirmar.click(); } });
      const bloco = no('div', 'fator-chave-bloco'); bloco.append(rotuloDaChave, chave, copiar, avisoDaChave);
      mostrar(2, texto, quadro, bloco, codigo.grupo, erroGeral, acoesDoPasso(...[cancelar(), confirmar].filter(Boolean)));
      codigo.entrada.focus();
    }

    function passoDosCodigos(codigos) {
      travar?.(true);  // neste passo Esc não fecha e não há Cancelar: os códigos não voltam
      const titulo = no('h3', 'fator-titulo', t('Guarde os códigos de reserva'));
      const vista = vistaDosCodigos(codigos, {aoGuardar: () => { travar?.(false); vivo = false; aoConcluir?.(); }});
      mostrar(3, titulo, vista);
      vista.guardei.focus();
    }

    passoDaSenha();
    return {parar() { vivo = false; }};
  }

  // --- a página da pendência: o cadastro dentro do cartão do Entrar, sem diálogo -------------------------------------------------------------------------------
  function chamadorDaSessao() {
    let token = null;
    return async (operacao, dados) => {
      if (!token) {
        const sessao = await fetch('/api/sessao', {headers: {Accept: 'application/json'}, credentials: 'same-origin'});
        if (!sessao.ok) throw Object.assign(new Error(t('Sessão expirada ou encerrada. Entre novamente.')), {result: {codigo: 'sessao_expirada'}});
        token = (await sessao.json()).csrf;
      }
      const resposta = await fetch(`/api/${operacao}`, {method: 'POST', credentials: 'same-origin', headers: {'Content-Type': 'application/json', 'X-Session-Token': token}, body: JSON.stringify(dados)});
      let corpo = {};
      try { corpo = await resposta.json(); } catch (_) { /* sem corpo */ }
      if (!resposta.ok) throw Object.assign(new Error(window.I18N?.erro ? window.I18N.erro(corpo) : (corpo.erro || t('Não foi possível completar a operação.'))), {result: corpo});
      return corpo;
    };
  }
  function pagina(alvo, {chamar = chamadorDaSessao(), sair, abrirMesa} = {}) {
    alvo.classList.add('fator-pagina');
    const rubrica = no('p', 'fator-rubrica-pagina', t('ANTES DE CONTINUAR'));
    const titulo = no('h1', 'fator-titulo-pagina', t('Proteja a conta com um segundo passo'));
    const texto = no('p', 'fator-texto', t('Para quem é dono ou editor, o Vlado pede, além da senha, um código do aplicativo autenticador. Cadastre agora para abrir a Mesa.'));
    const passos = no('div', 'fator-passos');
    const sairDaConta = botao('Sair', 'fator-link', async () => { try { await chamar('sessao-sair', {}); } catch (_) { /* a sessão cai de qualquer jeito */ } sair?.(); });
    const rodape = no('p', 'fator-rodape'); rodape.append(sairDaConta);
    alvo.replaceChildren(rubrica, titulo, texto, passos, rodape);
    cadastro({alvo: passos, chamar, aoConcluir() {
      const pronto = no('div', 'fator-pronto');
      const aviso = no('p', 'fator-texto', t('Segundo fator ativado.')); aviso.setAttribute('role', 'status');
      const abrir = botao('Abrir a Mesa', 'fator-principal', () => abrirMesa?.());
      pronto.append(aviso, acoesFim(abrir));
      passos.replaceChildren(pronto); abrir.focus();
    }});
    function acoesFim(...controles) { const caixa = no('div', 'fator-acoes fator-acoes-fim'); caixa.append(...controles); return caixa; }
  }

  window.Fator = {cadastro, vistaDosCodigos, qrSvg, pagina, chamadorDaSessao, chaveEmGrupos};
})();
