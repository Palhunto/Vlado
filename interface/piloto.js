'use strict';
// Hosted mode: guests stay in "Ask the AI"; administrators manage individual accounts.
// The server enforces every rule; this script only shapes the screen.
(() => {
  const body = document.body;
  if (body.dataset.modo === 'local') return;  // piloto and local-contas have accounts
  const t = (texto, vars) => (window.I18N ? window.I18N.t(texto, vars) : texto);
  const sair = document.getElementById('mesa-sair');
  sair.hidden = false;
  sair.addEventListener('click', async () => {
    // The Caderno saves what it can first and asks before dropping unsaved text; from then on it
    // neither saves nor keeps drafts, so nothing is rewritten while the session ends.
    if (window.prepararSaidaCaderno && !(await window.prepararSaidaCaderno())) return;
    try { await api('sessao-sair', {}); } catch (_) { /* The session is dropped either way. */ }
    // Unsaved notebook drafts may hold unpublished reporting: never leave them behind on sign-out.
    try { window.limparRascunhosCaderno?.(); } catch (_) { /* Storage blocked: nothing was kept. */ }
    try { window.Rascunhos?.limparTudo(); } catch (_) { /* Same for the question and panel drafts. */ }
    window.location.replace('/entrar');
  });

  if (body.dataset.papel === 'convidado') {
    // O perfil antigo só pergunta: toda troca de área mostra a conversa, salvo a página da própria conta
    // (Minha conta, W08, que toda pessoa com conta tem). O `name` que os demais ganchos recebem continua sendo o pedido (comportamento de antes).
    registrarGanchoArea({forcar: nome => (nome === 'configuracoes' ? 'configuracoes' : 'codex')});
    const abrir = () => mostrarAreaBase('codex');
    if (document.readyState === 'complete') abrir(); else window.addEventListener('load', abrir);
    return;
  }

  // Dono, editor, repórter e leitor: toda pessoa com conta tem o perfil, que abre Minha conta (conta.js). As áreas, as abas e os botões aparecem
  // pelas capacidades da sessão (Sessao, app.js); o servidor recusa o resto. O botão "Configurações" do cabeçalho (só com `ia-config`) abre a aba.
  $('ver-configuracoes').hidden = false;
  const configuracoes = $('mesa-configuracoes');
  configuracoes.hidden = false;
  configuracoes.addEventListener('click', () => { showArea('configuracoes'); window.Conta?.abrir('configuracoes'); });
  // A tela antiga de contas de acesso fica em Configurações, só para quem administra as contas (P30: sai com a E3 de Contas).
  window.Sessao.pronta.then(() => { if (window.Sessao.administra()) iniciarAdministracao(); });

  function iniciarAdministracao() {
    const painel = $('acesso-painel');
    painel.hidden = false;
    const situacoes = {ativa: 'Ativa', desativada: 'Desativada', aguardando_senha: 'Aguardando senha'};
    const papeis = {admin: 'Administração', convidado: 'Convidado'};
    let catalogoCasos = [];

    function mensagem(texto = '') { $('acesso-mensagem').textContent = texto; }
    function mostrarLink(conta, link) {
      $('acesso-link-quem').textContent = `${conta.nome} (${conta.login})`;
      $('acesso-link').value = link;
      $('acesso-link-caixa').hidden = false;
      $('acesso-link').focus();
      $('acesso-link').select();
    }
    function esconderLink() {
      $('acesso-link').value = '';  // the link is never kept on screen longer than needed
      $('acesso-link-caixa').hidden = true;
    }
    $('acesso-copiar').addEventListener('click', async () => {
      const campo = $('acesso-link');
      try {
        await navigator.clipboard.writeText(campo.value);
        mensagem(t('Link copiado.'));
      } catch (_) {
        campo.select();
        mensagem(t('Selecione o link e copie manualmente.'));
      }
    });
    $('acesso-link-fechar').addEventListener('click', esconderLink);

    function papelAlterado() {
      const convidado = $('acesso-papel').value === 'convidado';
      $('acesso-casos-rotulo').hidden = !convidado;
      $('acesso-cota-rotulo').hidden = !convidado;
    }
    $('acesso-papel').addEventListener('change', papelAlterado);
    papelAlterado();

    const opcoesCasos = selecionados => catalogoCasos.map(c => {
      const opcao = new Option(c.titulo, c.id);
      opcao.selected = (selecionados || []).includes(c.id);
      return opcao;
    });
    async function casos() {
      try {
        const resposta = await fetch('/api/catalogo');
        const dados = await resposta.json();
        if (!resposta.ok) throw new Error(window.I18N?.erro ? window.I18N.erro(dados) : dados.erro);
        catalogoCasos = dados.casos || [];
        $('acesso-casos').replaceChildren(...opcoesCasos([]));
      } catch (error) { mensagem(error.message); }
    }

    // As operações sensíveis (criar dono, recuperar, desativar dono...) pedem a senha de quem age: o servidor responde 403 senha_necessaria e o diálogo
    // reenvia o mesmo pedido com `senha`. O botão só fica desabilitado enquanto um pedido está no ar, para o foco voltar a ele quando o diálogo fecha.
    function comSenha(botao, operacao, dados, opcoes) {
      const enviar = async (nome, corpo) => {
        botao.disabled = true;
        try { return await api(nome, corpo); } finally { botao.disabled = false; }
      };
      return Dialogo.comSenha({operacao, dados, gatilho: botao, enviar, ...opcoes});
    }
    async function agir(botao, operacao, dados, sucesso, senha) {
      if (!senha) botao.disabled = true;
      try {
        const resultado = senha ? await comSenha(botao, operacao, dados, senha) : await api(operacao, dados);
        if (resultado === null) return;  // a pessoa cancelou o diálogo da senha: nada foi enviado
        if (resultado.link) mostrarLink(resultado.conta, resultado.link);
        mensagem(t(sucesso));
        await listar();
      } catch (error) { mensagem(error.message); botao.disabled = false; }
    }
    function botao(texto, classe, aoClicar) {
      const novo = element('button', t(texto), classe);
      novo.type = 'button';
      novo.addEventListener('click', () => aoClicar(novo));
      return novo;
    }
    function editorCasos(conta, linha) {
      const formulario = element('form', undefined, 'ia-config');
      const lista = element('select');
      lista.multiple = true; lista.size = 4;
      lista.append(...opcoesCasos(conta.casos));
      const rotulo = element('label', t('Apurações liberadas')); rotulo.append(lista);
      const cota = element('input'); cota.type = 'number'; cota.min = '1'; cota.max = '500';
      cota.value = String(conta.cota_diaria || 20);
      const rotuloCota = element('label', t('Consultas por dia')); rotuloCota.append(cota);
      const salvar = element('button', t('Salvar alterações')); salvar.type = 'submit';
      const acoes = element('div', undefined, 'actions');
      acoes.append(salvar, botao('Cancelar', 'secondary', () => formulario.remove()));
      formulario.append(rotulo, rotuloCota, acoes);
      formulario.addEventListener('submit', event => {
        event.preventDefault();
        agir(salvar, 'contas-atualizar', {id: conta.id, casos: [...lista.selectedOptions].map(o => o.value),
          cota_diaria: Number(cota.value)}, 'Acesso alterado. Vale a partir da próxima ação da pessoa.',
        {pedirAntes: false, dialogo: {titulo: 'Confirme com a sua senha', texto: 'Esta ação pede a sua senha.', acao: 'Salvar alterações'}});
      });
      linha.append(formulario);
      lista.focus();
    }
    function item(conta) {
      const linha = element('li');
      const texto = element('div');
      const titulo = element('h4'); titulo.textContent = conta.nome; titulo.translate = false;
      const detalhes = [conta.login, t(papeis[conta.papel] || conta.papel), t(situacoes[conta.situacao] || conta.situacao)];
      if (conta.situacao === 'aguardando_senha' && conta.ativacao_vencida) detalhes.push(t('link vencido'));
      const meta = element('p', detalhes.join(' · '), 'small');
      texto.append(titulo, meta);
      if (conta.papel === 'convidado') {
        const nomes = (conta.casos || []).map(id => (catalogoCasos.find(c => c.id === id) || {titulo: id}).titulo);
        texto.append(element('p', `${t('Apurações')}: ${nomes.join(', ') || '—'} · ${t('Consultas por dia')}: ${conta.cota_diaria}`, 'small'));
      }
      const acoes = element('div', undefined, 'inline-actions');
      if (conta.ativa) {
        acoes.append(botao('Desativar', 'danger', async alvo => {
          const texto = {titulo: 'Desativar {item}?', item: conta.login, texto: 'A pessoa sai na próxima ação.', acao: 'Desativar conta'};
          // Desativar um dono pede a senha: o diálogo da senha já é a confirmação. As demais contas só confirmam (e, se o servidor pedir, o diálogo abre).
          const dono = conta.papel === 'dono' || conta.papel === 'admin';
          if (!dono && !(await Dialogo.confirmar({variante: 'destrutivo', ...texto, gatilho: alvo}))) return;
          agir(alvo, 'contas-desativar', {id: conta.id}, 'Conta desativada.', {pedirAntes: dono, dialogo: {...texto, destrutiva: true}});
        }));
      } else {
        acoes.append(botao('Reativar', 'secondary', alvo => agir(alvo, 'contas-reativar', {id: conta.id}, 'Conta reativada.')));
      }
      // Toda recuperação pede a senha de quem age: o diálogo da senha traz o mesmo texto da confirmação de antes e a substitui.
      acoes.append(botao('Recuperar acesso', 'secondary', alvo => agir(alvo, 'contas-recuperar', {id: conta.id}, 'Novo link de ativação gerado.',
        {pedirAntes: true, dialogo: {titulo: 'Gerar novo link de ativação?', texto: 'A senha atual deixa de valer e as sessões abertas são encerradas.',
          acao: 'Gerar novo link'}})));
      if (conta.papel === 'convidado') acoes.append(botao('Alterar apurações', 'secondary', () => editorCasos(conta, linha)));
      linha.append(texto, acoes);
      return linha;
    }
    async function listar() {
      try {
        const {contas} = await api('contas-listar', {});
        $('acesso-lista').replaceChildren(...(contas.length ? contas.map(item)
          : [element('li', t('Nenhuma conta criada.'), 'manage-empty')]));
      } catch (error) { mensagem(error.message); }
    }
    $('acesso-form').addEventListener('submit', async event => {
      event.preventDefault();
      const papel = $('acesso-papel').value;
      const dados = {nome: $('acesso-nome').value.trim(), login: $('acesso-login').value.trim().toLowerCase(), papel,
        horas: Number($('acesso-horas').value)};
      if (papel === 'convidado') {
        dados.casos = [...$('acesso-casos').selectedOptions].map(o => o.value);
        dados.cota_diaria = Number($('acesso-cota').value);
      }
      const enviar = event.submitter || $('acesso-form').querySelector('button[type="submit"]');
      try {
        // Criar uma conta de administração (dono) pede a senha, mas o servidor pode recusar a criação por outro motivo (operacao_proibida): por isso o
        // pedido segue primeiro e o diálogo só abre se o servidor pedir a senha.
        const resultado = await comSenha(enviar, 'contas-criar', dados, {pedirAntes: false,
          dialogo: {titulo: 'Confirme com a sua senha', texto: 'Esta ação pede a sua senha.', acao: 'Criar conta'}});
        if (resultado === null) return;  // cancelou o diálogo da senha: nada foi criado
        mostrarLink(resultado.conta, resultado.link);
        $('acesso-nome').value = ''; $('acesso-login').value = '';
        mensagem(t('Conta criada. Envie o link de ativação.'));
        await listar();
      } catch (error) { mensagem(error.message); }
    });
    casos().then(listar);
  }
})();
