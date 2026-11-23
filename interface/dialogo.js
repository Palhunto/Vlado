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
// `titulo` pode levar {item}: o nome do item entra entre aspas (sem elas com `itemAspas: false`) e marcado translate="no" (é dado, não texto da interface).
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
// `campos: [{id, rotulo, apoio, autocomplete, exigido}]` acrescenta campos de senha ("com senha", docs/design/componentes.md#dialogo-senha) entre o
// texto e as ações: type="password", com "Mostrar", aceitando colar. Com `exigido`, a ação só se habilita com o campo preenchido; Enter em qualquer campo
// envia. `validar(valores)` devolve {id: mensagem} e, se houver erro, nada é enviado: cada mensagem vai junto ao seu campo, e o foco, ao primeiro.
// Se `executar` lançar uma falha com `falha.campo` (id de um campo), a mensagem vai junto àquele campo, ele é limpo e recebe o foco; a senha
// `falha.bloqueado` deixa a ação indisponível (sobra "Cancelar"); a senha nunca fica guardada: os campos são limpos quando o diálogo fecha. ctx.valores() devolve {id: valor}; ctx.erroCampo(id, mensagem) e ctx.limparCampos().
// `campos[i].oculto` esconde um campo até `ctx.campoVisivel(id, true)` (o campo "Sua senha" só vale com o papel Dono, no convite); um campo oculto não é exigido e
// seu valor nunca vai em ctx.valores(). `validar(valores, ctx)` pode devolver `false` quando já mostrou os próprios erros (campos que não são de senha): nada é
// enviado e nada é limpo. Uma falha com `silencioso: true` não mostra mensagem do diálogo (quem lançou já a pôs junto ao campo).
// `ctx.trocarPor({titulo, texto, acao, semCancelar, montar(corpo)})`, chamado de `executar`, troca o formulário por outra vista sem fechar (o link do convite, que
// só aparece uma vez): a ação fecha (devolve true), Esc também, e `semCancelar` tira o botão de cancelar; o que a vista mostrou some quando o diálogo fecha.
// `rotuloDoNome` troca a frase "Digite «{nome}» para confirmar" do campo do nome (variante 'campo'); uma falha com `campoNome: true` põe a mensagem junto ao campo do nome, que recebe o foco
// (o nome que não confere em "Excluir a conta"; o servidor o confere antes da senha).
// `semAcoes: true` tira os botões do diálogo (quem o usa traz os próprios, como o cadastro do segundo fator, em vários passos): `ctx.fechar(valor)` o fecha e `ctx.travar(true)` faz o Esc
// deixar de fechar (o passo dos códigos de reserva, que não voltam).
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
  // Um e-mail só quebra de linha depois do @ ou antes de um ponto (<wbr> nesses lugares), nunca no meio da palavra; o texto não muda (wbr não tem texto).
  function quebraveis(texto) {
    const alvo = document.createDocumentFragment();
    String(texto).split(/(\S+@\S+)/).forEach((pedaco, indice) => {
      if (indice % 2 === 0) { if (pedaco) alvo.append(pedaco); return; }
      pedaco.split(/(?<=@)|(?=\.[A-Za-z0-9])/).forEach((parte, ordem) => { if (ordem) alvo.append(document.createElement('wbr')); if (parte) alvo.append(parte); });
    });
    return alvo;
  }
  // Título com o nome do item no lugar de {item}.
  function preencherTitulo(destino, titulo, item, aspas = true) {
    const [antes, depois] = String(titulo).split('{item}');
    if (depois === undefined || !item) { destino.textContent = String(titulo).replace('{item}', item ?? ''); return; }
    const nome = no('span', 'dialogo-item'); nome.append(quebraveis(aspas ? `“${item}”` : item));
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
      preencherTitulo(titulo, t(opcoes.titulo || ''), opcoes.item, opcoes.itemAspas !== false);
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

      let campo = null, nomeEsperado = opcoes.nome ?? null, fraseDoCampo = null, erroDoNome = null;
      if (variante === 'campo') {
        const rotulo = no('label', 'dialogo-campo');
        fraseDoCampo = no('span');
        campo = document.createElement('input');
        campo.type = 'text'; campo.maxLength = 300; campo.autocomplete = 'off';
        campo.setAttribute('spellcheck', 'false'); campo.setAttribute('translate', 'no');
        rotulo.append(fraseDoCampo, campo);
        partes.push(rotulo);
        erroDoNome = no('p', 'dialogo-erro-nome'); erroDoNome.hidden = true; erroDoNome.id = `${id}-erro-nome`;
        campo.setAttribute('aria-describedby', erroDoNome.id);
        partes.push(erroDoNome);
      }
      // "Digite «nome» para confirmar": o nome é dado e não se traduz; sem nome ainda (vem do servidor), só a frase.
      function rotularCampo() {
        if (!fraseDoCampo) return;
        const [antes, depois] = t(opcoes.rotuloDoNome || 'Digite «{nome}» para confirmar').split('{nome}');
        const nome = no('strong', '', nomeEsperado ?? ''); nome.setAttribute('translate', 'no');
        fraseDoCampo.replaceChildren(antes, nome, depois ?? '');
      }
      rotularCampo();

      // Campos de senha: cada um com rótulo, apoio, "Mostrar" e a mensagem de erro própria, ligada por aria-describedby.
      const entradas = new Map();
      for (const [indice, def] of (opcoes.campos || []).entries()) {
        const base = `${id}-campo-${indice}`;
        const grupo = no('div', 'dialogo-campo dialogo-campo-senha');
        const rotuloDoCampo = no('label', '', t(def.rotulo)); rotuloDoCampo.htmlFor = `${base}-entrada`;
        const linha = no('div', 'dialogo-senha-linha');
        const entrada = document.createElement('input');
        entrada.id = `${base}-entrada`; entrada.type = 'password'; entrada.maxLength = 256;
        entrada.autocomplete = def.autocomplete || 'current-password';
        entrada.setAttribute('spellcheck', 'false'); entrada.setAttribute('autocapitalize', 'none'); entrada.setAttribute('translate', 'no');
        const mostrar = no('button', 'secondary dialogo-mostrar', t('Mostrar')); mostrar.type = 'button';
        mostrar.setAttribute('aria-pressed', 'false'); mostrar.setAttribute('aria-controls', entrada.id);
        mostrar.addEventListener('click', () => {
          const visivel = entrada.type === 'password';
          entrada.type = visivel ? 'text' : 'password';
          mostrar.setAttribute('aria-pressed', String(visivel)); mostrar.textContent = t(visivel ? 'Ocultar' : 'Mostrar');
        });
        linha.append(entrada, mostrar);
        const apoio = def.apoio ? no('p', 'dialogo-nota', t(def.apoio)) : null;
        const mensagemDoCampo = no('p', 'dialogo-erro dialogo-erro-campo'); mensagemDoCampo.id = `${base}-erro`; mensagemDoCampo.hidden = true;
        const ligacoes = [];
        if (apoio) { apoio.id = `${base}-apoio`; ligacoes.push(apoio.id); }
        entrada.setAttribute('aria-describedby', [mensagemDoCampo.id, ...ligacoes].join(' '));
        // O erro vem primeiro, a 4 px do campo, e o apoio depois (#dialogo-senha).
        grupo.append(rotuloDoCampo, linha, mensagemDoCampo, ...(apoio ? [apoio] : []));
        partes.push(grupo);
        if (def.oculto) grupo.hidden = true;
        entradas.set(def.id, {def, entrada, mostrar, mensagem: mensagemDoCampo, grupo});
      }

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
      if (opcoes.semAcoes) acoes.hidden = true;
      partes.push(acoes);
      caixa.append(...partes);

      let estado = 'aberto';       // aberto | ocupado | cancelando | fechado
      let travado = false;         // o Esc não fecha (ctx.travar)
      let bloqueado = false;       // recusa que não passa com nova tentativa (bloqueio por senhas erradas): sobra "Cancelar"
      let controlador = null;
      const fechamento = new AbortController();
      let interagiu = false;
      let tarefa = null;
      const inertes = [];

      const nomeConfere = () => !campo || (nomeEsperado !== null && comparavel(campo.value) === comparavel(nomeEsperado));
      const camposCompletos = () => [...entradas.values()].every(({def, entrada, grupo}) => !def.exigido || grupo.hidden || entrada.value !== '');
      const valores = () => Object.fromEntries([...entradas].map(([chave, {entrada, grupo}]) => [chave, grupo.hidden ? '' : entrada.value]));
      function atualizar() {
        if (estado === 'resultado') return;  // a vista de resultado (trocarPor) cuida dos próprios botões
        const livre = estado === 'aberto';
        // Na espera nada recebe `disabled` onde há foco: o campo fica só leitura e a ação, aria-disabled; assim o foco não vai para o corpo da
        // página (o Tab e o Esc continuam presos no diálogo) e o clique na ação é ignorado por `confirmar`.
        if (campo) { campo.readOnly = !livre; campo.disabled = nomeEsperado === null; }
        for (const {entrada} of entradas.values()) entrada.readOnly = !livre;
        botaoAcao.disabled = livre && (bloqueado || !(nomeConfere() && camposCompletos()));
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
      function erroCampo(chave, mensagem, {limpar = false, foco = true} = {}) {
        const item = entradas.get(chave);
        if (!item) return;
        item.mensagem.textContent = mensagem ? t(mensagem) : ''; item.mensagem.hidden = !mensagem;
        if (mensagem) item.entrada.setAttribute('aria-invalid', 'true'); else item.entrada.removeAttribute('aria-invalid');
        if (limpar) item.entrada.value = '';
        if (mensagem && foco) item.entrada.focus();
        atualizar();
      }
      function limparErrosDeCampo() { for (const chave of entradas.keys()) erroCampo(chave, '', {foco: false}); }
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
        for (const {entrada} of entradas.values()) entrada.value = '';  // a senha não fica guardada em lugar nenhum
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
      // A vista de resultado: o formulário some, entra o texto e o que `montar` puser; a ação fecha. O que foi mostrado sai da página com o diálogo.
      function trocarPor({titulo: novoTitulo, texto: novoTexto, acao: novaAcao, semCancelar = false, travada = false, montar, item, itemAspas = false} = {}) {
        travado = !!travada;  // os códigos de reserva: nem o Esc fecha, só "Já guardei"
        for (const filho of [...caixa.children]) if (filho !== titulo && filho !== acoes) filho.hidden = true;
        preencherTitulo(titulo, t(novoTitulo || ''), item, itemAspas);
        const vista = no('div', 'dialogo-resultado');
        if (novoTexto) vista.append(no('p', 'dialogo-texto', t(novoTexto)));
        montar?.(vista);
        caixa.insertBefore(vista, acoes);
        estado = 'resultado';
        caixa.removeAttribute('aria-busy'); caixa.removeAttribute('aria-describedby');
        botaoCancelar.hidden = !!semCancelar;
        botaoAcao.disabled = false; botaoAcao.setAttribute('aria-disabled', 'false'); botaoAcao.className = ''; botaoAcao.textContent = t(novaAcao || 'Fechar');
        return vista;
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
        valores,
        erroCampo,
        campoVisivel(chave, visivel) {
          const item = entradas.get(chave);
          if (!item) return;
          item.grupo.hidden = !visivel;
          if (!visivel) { item.entrada.value = ''; erroCampo(chave, '', {foco: false}); }
          atualizar();
        },
        trocarPor,
        fechar: valor => fechar(valor ?? false),
        travar: valor => { travado = !!valor; },
        limparCampos() { for (const {entrada} of entradas.values()) entrada.value = ''; limparErrosDeCampo(); },
        fechou: () => estado === 'fechado',
        sinalFechado: fechamento.signal,
      };
      function aoMudarIdioma() { rotularCampo(); opcoes.aoIdioma?.(ctx); }
      async function confirmar() {
        if (estado === 'resultado') { fechar(true); return; }
        if (estado !== 'aberto' || bloqueado || !nomeConfere() || !camposCompletos()) return;  // bloqueado: nem o Enter no campo envia mais um pedido
        limparErrosDeCampo();
        if (erroDoNome) { erroDoNome.hidden = true; campo.removeAttribute('aria-invalid'); }
        const brutas = opcoes.validar ? opcoes.validar(valores(), ctx) : {};
        if (brutas === false) return;  // quem validou já mostrou os próprios erros
        const recusas = Object.entries(brutas || {}).filter(([chave]) => entradas.has(chave));
        if (recusas.length) {
          for (const [chave, mensagem] of recusas) erroCampo(chave, mensagem, {foco: false});
          entradas.get(recusas[0][0])?.entrada.focus();
          return;
        }
        if (!opcoes.executar) { fechar(true); return; }
        estado = 'ocupado'; mostrarErro('');
        controlador = new AbortController();
        etapa(opcoes.longa ? (opcoes.etapaInicial || 'Começando…') : undefined, 0);
        atualizar();
        tarefa = Promise.resolve().then(() => opcoes.executar({...ctx, etapa, sinal: controlador.signal}));
        try {
          await tarefa;
          if (estado === 'resultado') { botaoAcao.focus(); return; }  // a vista de resultado segue aberta
          fechar(true);
        } catch (falha) {
          if (estado === 'cancelando') { fechar(false); return; }
          estado = 'aberto';
          if (falha?.bloqueado) bloqueado = true;
          atualizar();
          if (falha?.silencioso) return;  // quem lançou já pôs a mensagem junto ao campo
          // Recusa de um campo (senha incorreta): a mensagem vai junto ao campo, que é limpo e recebe o foco; as demais vão junto às ações.
          if (falha?.campoNome && campo) {  // o nome que não confere: a mensagem junto ao campo do nome, que recebe o foco
            erroDoNome.textContent = falha.message ? t(falha.message) : ''; erroDoNome.hidden = !falha.message; campo.setAttribute('aria-invalid', 'true'); campo.focus(); return;
          }
          if (falha?.campo && entradas.has(falha.campo)) { erroCampo(falha.campo, falha.message || 'Não deu para concluir. Tente de novo.', {limpar: true}); return; }
          // Qualquer outra recusa também leva a senha embora: ela não fica no campo entre uma tentativa e outra.
          for (const {entrada} of entradas.values()) entrada.value = '';
          atualizar();
          mostrarErro(falha?.message || 'Não deu para concluir. Tente de novo.');
          if (bloqueado) { botaoCancelar.focus(); return; }
          (campo && !campo.disabled ? campo : [...entradas.values()][0]?.entrada || botaoAcao).focus();
        }
      }
      function cancelar() {
        if (travado) return;
        if (estado === 'resultado') { fechar(true); return; }  // Esc na vista de resultado fecha como a ação
        if (estado === 'aberto') { fechar(false); return; }
        if (estado === 'ocupado' && opcoes.longa) {
          // A espera longa se cancela; a tarefa recebe o sinal e, ao terminar, fecha. Se acabou mesmo assim, vale o resultado.
          estado = 'cancelando'; controlador.abort(); etapa('Cancelando…'); atualizar();
        }
      }
      function aoTeclar(evento) {
        interagiu = true;
        if (evento.key === 'Escape') { evento.preventDefault(); evento.stopPropagation(); cancelar(); return; }
        if (evento.key === 'Enter' && (evento.target === campo || [...entradas.values()].some(({entrada}) => entrada === evento.target))) { evento.preventDefault(); confirmar(); return; }
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
      for (const {entrada} of entradas.values()) entrada.addEventListener('input', atualizar);
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
      const primeiraSenha = [...entradas.values()][0]?.entrada;
      const inicial = variante === 'campo' && !campo.disabled ? campo : primeiraSenha ? primeiraSenha : variante === 'simples' ? botaoAcao : botaoCancelar;
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

  // --- Operação que pede a senha (docs/design/componentes.md#dialogo-senha, contrato de contas 5.15) ----------------------------------------------
  const TEXTO_BLOQUEADO = 'Muitas senhas erradas seguidas. Por 15 minutos, as ações que pedem a senha ficam bloqueadas para a sua conta; o resto da Mesa continua.';
  // As recusas da senha, na forma que o diálogo entende: erro no campo (senha incorreta: o campo é limpo e recebe o foco), bloqueio (só sobra
  // "Cancelar") ou o texto do servidor (senha_necessaria, ultimo_dono e as demais), que fica no erro do diálogo.
  function recusaDaSenha(falha, {campo = 'senha', incorreta = 'Senha incorreta. Confira e tente de novo.'} = {}) {
    const codigo = falha?.result?.codigo;
    if (codigo === 'senha_atual_incorreta') { const recusa = new Error(t(incorreta)); recusa.campo = campo; return recusa; }
    if (codigo === 'bloqueado') { const recusa = new Error(t(TEXTO_BLOQUEADO)); recusa.bloqueado = true; return recusa; }
    return falha;
  }
  // Envia `operacao` e, quando ela pede a senha, abre o diálogo com o campo "Sua senha" e reenvia o MESMO pedido com `senha`. Com `pedirAntes`, a Mesa
  // sabe que a operação pede e abre o diálogo antes de enviar; sem ele, envia primeiro e o diálogo só abre se o servidor responder 403 senha_necessaria.
  // A senha vai só naquele pedido: nunca é guardada nem reenviada sozinha (cada tentativa pede o que a pessoa digitou). `dialogo`: {titulo, item, texto,
  // acao, ocupado, destrutiva, campo (padrão 'senha'), aoRecusar(falha)}. `enviar(operacao, dados)` troca o `api` global. Devolve o resultado do servidor,
  // ou null se a pessoa cancelou. Outras falhas do primeiro envio sobem como vieram.
  async function comSenha({operacao, dados = {}, dialogo = {}, pedirAntes = true, gatilho, enviar} = {}) {
    const chamar = enviar || ((nome, corpo) => api(nome, corpo));
    const nomeDoCampo = dialogo.campo || 'senha';
    // O pedido é copiado aqui: quem chamou pode mexer no objeto enquanto o diálogo está aberto, e o reenvio tem de ser o MESMO pedido.
    const original = JSON.parse(JSON.stringify(dados));
    if (!pedirAntes) {
      try { return await chamar(operacao, JSON.parse(JSON.stringify(original))); }
      catch (falha) { if (falha?.result?.codigo !== 'senha_necessaria') throw falha; }
    }
    let resultado = null;
    const confirmado = await confirmar({
      variante: dialogo.destrutiva ? 'destrutivo' : 'simples', titulo: dialogo.titulo, item: dialogo.item, itemAspas: false, texto: dialogo.texto,
      acao: dialogo.acao, ocupado: dialogo.ocupado || 'Enviando…', gatilho,
      campos: [{id: nomeDoCampo, rotulo: 'Sua senha', apoio: 'A senha com que você entra na Mesa.', autocomplete: 'current-password', exigido: true}],
      async executar(ctx) {
        try { resultado = await chamar(operacao, {...JSON.parse(JSON.stringify(original)), [nomeDoCampo]: ctx.valores()[nomeDoCampo]}); }
        catch (falha) { dialogo.aoRecusar?.(falha); throw recusaDaSenha(falha, {campo: nomeDoCampo}); }
      },
    });
    return confirmado ? resultado : null;
  }

  window.Dialogo = {confirmar, comSenha, recusaDaSenha, quebraveis};
})();
