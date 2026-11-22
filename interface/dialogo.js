'use strict';
// Diálogo de confirmação da Mesa (docs/design/componentes.md#dialogo, UX-16, W11 regra 8). Substitui o confirm() do navegador.
//
//   const ok = await Dialogo.confirmar({variante, rubrica, titulo, linha, texto, nota, acao, cancelar, item, nome, gatilho,
//                                       ocupado, executar, longa, preparar, aoIdioma});
//
// Variantes (todas aprovadas pelo dono em 21/11/2026):
//   'simples'    a ação é o botão principal e recebe o foco;
//   'destrutivo' a ação é o botão de contorno de erro e o foco inicial fica em "Cancelar";
//   'campo'      destrutivo, com a ação desabilitada até a pessoa digitar `nome`; o foco inicial é o campo.
// `titulo` pode levar {item}: o nome do item entra entre aspas e marcado translate="no" (é dado, não texto da interface).
// Sem `executar`, devolve true ao confirmar e false ao cancelar (Cancelar, Esc). Com `executar(ctx)`, o diálogo fica aberto
// enquanto a função roda: a ação vira o gerúndio de `ocupado` e o diálogo recebe aria-busy; se a função lança, a mensagem aparece
// junto das ações (role="alert") e a pessoa pode tentar de novo; se termina, o diálogo fecha e a promessa devolve true.
// Com `longa: true` a espera é a longa de W11 (regra 3): barra com etapa, aviso de que dá para sair da tela e "Cancelar" ativo;
// `ctx.etapa(texto, fracao)` atualiza a barra e `ctx.sinal` (AbortSignal) avisa o cancelamento.
// `linha: [rotulo, dado]` é a linha do item sob o título ("Apuração · nome": o rótulo é da interface, o dado não se traduz).
// `preparar(ctx)` roda depois de aberto, para o que vem do servidor: ctx.corpo (onde entra o conteúdo, como a tabela do que sai),
// ctx.estado(texto) (linha de estado, role=status), ctx.nome(valor) (o nome a digitar; sem ele o campo e a ação ficam desabilitados),
// ctx.limparCampo(), ctx.erro(mensagem), ctx.valor() e ctx.fechou(). `executar(ctx)` recebe o mesmo ctx, mais etapa e sinal.
// `aoIdioma(ctx)` é chamado se a língua mudar com o diálogo aberto (o conteúdo de `corpo` é montado por quem chamou).
// Clique no véu não fecha (decisão do dono, P12.5). Esc fecha como "Cancelar". O foco fica preso e, ao fechar, volta a `gatilho`.
(() => {
  const t = (pt, vars) => (window.I18N ? window.I18N.t(pt, vars) : String(pt).replace(/\{(\w+)\}/g, (todo, nome) => vars?.[nome] ?? todo));
  const comparavel = valor => String(valor ?? '').trim().toUpperCase().toLowerCase();
  const FOCAVEIS = 'a[href],button,input,select,textarea,summary,[tabindex]';
  let fila = Promise.resolve();
  let sequencia = 0;

  function no(etiqueta, classe, texto) {
    const elemento = document.createElement(etiqueta);
    if (classe) elemento.className = classe;
    if (texto !== undefined && texto !== null) elemento.textContent = texto;
    return elemento;
  }
  // Título com o nome do item no lugar de {item}.
  function preencherTitulo(destino, titulo, item) {
    const [antes, depois] = String(titulo).split('{item}');
    if (depois === undefined || !item) { destino.textContent = String(titulo).replace('{item}', item ?? ''); return; }
    const nome = no('span', 'dialogo-item', `“${item}”`);
    nome.setAttribute('translate', 'no');
    destino.replaceChildren(antes, nome, depois);
  }
  const focaveis = caixa => [...caixa.querySelectorAll(FOCAVEIS)]
    .filter(controle => !controle.disabled && controle.getAttribute('tabindex') !== '-1' && !controle.closest('[hidden]'));

  function abrir(opcoes) {
    return new Promise(resolver => {
      const variante = ['simples', 'destrutivo', 'campo'].includes(opcoes.variante) ? opcoes.variante : 'simples';
      const destrutivo = variante !== 'simples';
      const gatilho = opcoes.gatilho || document.activeElement;
      const id = `dialogo-${++sequencia}`;
      const caixa = no('dialog', 'dialogo');
      caixa.dataset.variante = variante;
      caixa.setAttribute('role', 'alertdialog');
      caixa.setAttribute('aria-modal', 'true');
      caixa.setAttribute('aria-labelledby', `${id}-titulo`);

      const titulo = no('h2', 'dialogo-titulo'); titulo.id = `${id}-titulo`;
      preencherTitulo(titulo, t(opcoes.titulo || ''), opcoes.item);
      const texto = no('p', 'dialogo-texto', opcoes.texto ? t(opcoes.texto) : ''); texto.id = `${id}-texto`;
      const partes = [];
      if (opcoes.rubrica) partes.push(no('p', 'dialogo-rubrica', t(opcoes.rubrica)));
      partes.push(titulo);
      if (opcoes.linha) {
        const linha = no('p', 'dialogo-linha');
        const dado = no('span', '', opcoes.linha[1]); dado.setAttribute('translate', 'no');
        linha.append(t(opcoes.linha[0]), ' · ', dado);
        partes.push(linha);
      }
      if (opcoes.texto) { partes.push(texto); caixa.setAttribute('aria-describedby', texto.id); }
      if (opcoes.nota) partes.push(no('p', 'dialogo-nota', t(opcoes.nota)));
      const corpo = no('div', 'dialogo-corpo');
      const linhaEstado = no('p', 'dialogo-nota'); linhaEstado.hidden = true; linhaEstado.setAttribute('role', 'status'); linhaEstado.setAttribute('aria-live', 'polite');
      if (opcoes.preparar) partes.push(corpo, linhaEstado);

      let campo = null, nomeEsperado = opcoes.nome ?? null, fraseDoCampo = null;
      if (variante === 'campo') {
        const rotulo = no('label', 'dialogo-campo');
        fraseDoCampo = no('span');
        campo = document.createElement('input');
        campo.type = 'text'; campo.maxLength = 300; campo.autocomplete = 'off';
        campo.setAttribute('spellcheck', 'false'); campo.setAttribute('translate', 'no');
        rotulo.append(fraseDoCampo, campo);
        partes.push(rotulo);
      }
      // "Digite «nome» para confirmar": o nome é dado e não se traduz; sem nome ainda (vem do servidor), só a frase.
      function rotularCampo() {
        if (!fraseDoCampo) return;
        const [antes, depois] = t('Digite «{nome}» para confirmar').split('{nome}');
        const nome = no('strong', '', nomeEsperado ?? ''); nome.setAttribute('translate', 'no');
        fraseDoCampo.replaceChildren(antes, nome, depois ?? '');
      }
      rotularCampo();

      const progresso = no('div', 'dialogo-progresso'); progresso.hidden = true;
      progresso.setAttribute('role', 'status');
      const etapaTexto = no('p', 'dialogo-etapa');
      const barra = no('div', 'medidor-progresso'); barra.setAttribute('role', 'progressbar');
      barra.setAttribute('aria-valuemin', '0'); barra.setAttribute('aria-valuemax', '100');
      barra.setAttribute('aria-label', t('Progresso'));
      const aviso = no('p', 'dialogo-nota', t('Você pode sair desta tela. A operação continua.'));
      progresso.append(etapaTexto, barra, aviso);
      const erro = no('p', 'dialogo-erro'); erro.hidden = true; erro.setAttribute('role', 'alert');
      partes.push(progresso, erro);

      const botaoCancelar = no('button', 'secondary', t(opcoes.cancelar || 'Cancelar')); botaoCancelar.type = 'button';
      const botaoAcao = no('button', destrutivo ? 'danger' : '', t(opcoes.acao || 'Confirmar')); botaoAcao.type = 'button';
      const acoes = no('div', 'dialogo-acoes');
      acoes.append(botaoCancelar, botaoAcao);
      partes.push(acoes);
      caixa.append(...partes);

      let estado = 'aberto';       // aberto | ocupado | cancelando | fechado
      let controlador = null;
      const fechamento = new AbortController();
      let interagiu = false;
      let tarefa = null;
      const inertes = [];

      const nomeConfere = () => !campo || (nomeEsperado !== null && comparavel(campo.value) === comparavel(nomeEsperado));
      function atualizar() {
        const livre = estado === 'aberto';
        // Na espera nada recebe `disabled` onde há foco: o campo fica só leitura e a ação, aria-disabled; assim o foco não vai para o corpo da
        // página (o Tab e o Esc continuam presos no diálogo) e o clique na ação é ignorado por `confirmar`.
        if (campo) { campo.readOnly = !livre; campo.disabled = nomeEsperado === null; }
        botaoAcao.disabled = livre && !nomeConfere();
        botaoAcao.setAttribute('aria-disabled', String(!livre));
        botaoCancelar.disabled = estado === 'cancelando' || (estado === 'ocupado' && !opcoes.longa);
        botaoAcao.textContent = t(estado === 'ocupado' && opcoes.ocupado ? opcoes.ocupado : (opcoes.acao || 'Confirmar'));
        if (estado === 'ocupado' || estado === 'cancelando') caixa.setAttribute('aria-busy', 'true'); else caixa.removeAttribute('aria-busy');
        progresso.hidden = !(opcoes.longa && (estado === 'ocupado' || estado === 'cancelando'));
        const ativo = document.activeElement;
        if (!livre && (!caixa.contains(ativo) || ativo.disabled)) (botaoCancelar.disabled ? botaoAcao : botaoCancelar).focus();
      }
      function mostrarErro(mensagem) {
        erro.textContent = mensagem ? t(mensagem) : '';
        erro.hidden = !mensagem;
      }
      function etapa(textoEtapa, fracao) {
        if (textoEtapa !== undefined) etapaTexto.textContent = t(textoEtapa);
        if (typeof fracao === 'number' && Number.isFinite(fracao)) {
          const pct = Math.max(0, Math.min(100, Math.round(fracao * 100)));
          barra.style.setProperty('--uso', `${pct}%`);
          barra.setAttribute('aria-valuenow', String(pct));
        }
      }
      function fechar(valor) {
        if (estado === 'fechado') return;
        estado = 'fechado';
        fechamento.abort();
        window.removeEventListener('vlado-idioma', aoMudarIdioma);
        caixa.removeEventListener('keydown', aoTeclar);
        caixa.removeEventListener('cancel', aoCancelarNativo);
        try { caixa.close(); } catch (falha) { /* já fechado */ }
        caixa.remove();
        for (const [elemento, antes] of inertes) elemento.inert = antes;
        if (gatilho && gatilho.isConnected && typeof gatilho.focus === 'function') gatilho.focus();
        resolver(valor);
      }
      // O que `preparar`, `executar` e `aoIdioma` recebem.
      const ctx = {
        corpo,
        estado(texto) { linhaEstado.textContent = texto ? t(texto) : ''; linhaEstado.hidden = !texto; },
        nome(valor) {
          nomeEsperado = valor ?? null; rotularCampo(); atualizar();
          // O nome chegou: o campo é o foco inicial (aprovado pelo Design), se a pessoa ainda não mexeu em nada.
          if (campo && nomeEsperado !== null && !interagiu && estado === 'aberto') campo.focus();
        },
        limparCampo() { if (campo) campo.value = ''; atualizar(); },
        erro: mostrarErro,
        valor: () => (campo ? campo.value : ''),
        fechou: () => estado === 'fechado',
        sinalFechado: fechamento.signal,
      };
      function aoMudarIdioma() { rotularCampo(); opcoes.aoIdioma?.(ctx); }
      async function confirmar() {
        if (estado !== 'aberto' || !nomeConfere()) return;
        if (!opcoes.executar) { fechar(true); return; }
        estado = 'ocupado'; mostrarErro('');
        controlador = new AbortController();
        etapa(opcoes.longa ? (opcoes.etapaInicial || 'Começando…') : undefined, 0);
        atualizar();
        tarefa = Promise.resolve().then(() => opcoes.executar({...ctx, etapa, sinal: controlador.signal}));
        try {
          await tarefa;
          fechar(true);
        } catch (falha) {
          if (estado === 'cancelando') { fechar(false); return; }
          estado = 'aberto';
          mostrarErro(falha?.message || 'Não deu para concluir. Tente de novo.');
          atualizar();
          (campo && !campo.disabled ? campo : botaoAcao).focus();
        }
      }
      function cancelar() {
        if (estado === 'aberto') { fechar(false); return; }
        if (estado === 'ocupado' && opcoes.longa) {
          // A espera longa se cancela; a tarefa recebe o sinal e, ao terminar, fecha. Se acabou mesmo assim, vale o resultado.
          estado = 'cancelando'; controlador.abort(); etapa('Cancelando…'); atualizar();
        }
      }
      function aoTeclar(evento) {
        interagiu = true;
        if (evento.key === 'Escape') { evento.preventDefault(); evento.stopPropagation(); cancelar(); return; }
        if (evento.key === 'Enter' && evento.target === campo) { evento.preventDefault(); confirmar(); return; }
        if (evento.key !== 'Tab') return;
        const lista = focaveis(caixa);
        if (!lista.length) { evento.preventDefault(); return; }
        const primeiro = lista[0], ultimo = lista[lista.length - 1], ativo = document.activeElement;
        if (evento.shiftKey && (ativo === primeiro || !caixa.contains(ativo))) { evento.preventDefault(); ultimo.focus(); }
        else if (!evento.shiftKey && (ativo === ultimo || !caixa.contains(ativo))) { evento.preventDefault(); primeiro.focus(); }
      }
      // O navegador dispara "cancel" no Esc; o tratamento acima já cuida, e aqui só se impede o fechamento nativo.
      function aoCancelarNativo(evento) { evento.preventDefault(); cancelar(); }

      botaoCancelar.addEventListener('click', () => { interagiu = true; cancelar(); });
      botaoAcao.addEventListener('click', confirmar);
      window.addEventListener('vlado-idioma', aoMudarIdioma);
      if (campo) campo.addEventListener('input', atualizar);
      caixa.addEventListener('keydown', aoTeclar);
      caixa.addEventListener('cancel', aoCancelarNativo);

      document.body.append(caixa);
      // Com showModal() o navegador já isola a página; o inert explícito vale também onde o isolamento nativo não chega.
      for (const irmao of document.body.children) {
        if (irmao === caixa || irmao.localName === 'script') continue;
        inertes.push([irmao, !!irmao.inert]); irmao.inert = true;
      }
      atualizar();
      // Se o navegador recusar o showModal, a página não pode ficar inerte: desfaz tudo e devolve "cancelado".
      try { caixa.showModal(); } catch (falha) { caixa.remove(); for (const [elemento, antes] of inertes) elemento.inert = antes; estado = 'fechado'; resolver(false); return; }
      // Com campo: o campo, se já puder receber o nome; senão "Cancelar" até o nome chegar (então o foco passa ao campo).
      const inicial = variante === 'simples' ? botaoAcao : variante === 'campo' && !campo.disabled ? campo : botaoCancelar;
      inicial.focus();
      if (opcoes.preparar) {
        Promise.resolve().then(() => opcoes.preparar(ctx)).catch(falha => { if (estado !== 'fechado') mostrarErro(falha?.message || 'Não deu para concluir. Tente de novo.'); });
      }
    });
  }

  // Uma confirmação por vez: se outra chamada chegar com o diálogo aberto, espera a vez.
  function confirmar(opcoes = {}) {
    const gatilho = opcoes.gatilho || document.activeElement;
    const execucao = fila.then(() => abrir({...opcoes, gatilho}));
    fila = execucao.catch(() => {});
    return execucao;
  }

  window.Dialogo = {confirmar};
})();
