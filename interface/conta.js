'use strict';
// A página das contas (docs/design/componentes.md#contas, W08 e W09): a moldura com as abas Minha conta, Equipe e Configurações, e a Minha conta.
// A página vive na área "configuracoes" da Mesa: o perfil da barra lateral abre a aba Minha conta; Equipe (equipe.js) e Configurações só aparecem
// para quem as capacidades de GET /api/sessao alcançam, nunca pelo nome do papel. Tudo que a Mesa mostra aqui vem do servidor como texto
// (nome, e-mail, aparelho, endereço): entra na tela por textContent, nunca como HTML (contrato de contas, seção 9).
//
//   Conta.abrir(aba)                      abre a página na aba 'conta', 'equipe' ou 'configuracoes'
//   Conta.registrarAba(id, {rotulo, capacidade, montar(painel), abrir()})   usado por equipe.js
//   Conta.estado(texto, {erro})           a linha de estado logo abaixo das abas (role=status; erro: role=alert)
//   Conta.sensivel({operacao, dados, dialogo, pedirAntes, gatilho})   operação que pede a senha (#dialogo-senha); devolve o resultado ou null
//   Conta.no, Conta.cartao, Conta.carregar, Conta.data, Conta.reais, Conta.capacidade, Conta.rotuloPapel   peças comuns às duas telas
(() => {
  if (document.body.dataset.modo === 'local') return;  // sem contas não há perfil, Minha conta nem Equipe
  const area = document.getElementById('area-configuracoes');
  if (!area) return;
  const t = (pt, vars) => (window.I18N ? window.I18N.t(pt, vars) : String(pt).replace(/\{(\w+)\}/g, (todo, nome) => vars?.[nome] ?? todo));
  const CHAVE_TEMA = 'apuracao:tema';

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
  const dado = (texto, etiqueta = 'span') => { const elemento = no(etiqueta, '', texto); elemento.setAttribute('translate', 'no'); return elemento; };
  const lingua = () => (window.I18N?.idioma?.() === 'en' ? 'en' : 'pt');

  // Papéis por extenso: o servidor manda o nome interno ('dono', 'reporter'); a barra e esta página mostram o rótulo.
  const PAPEIS = {dono: 'Dono', admin: 'Dono', editor: 'Editor', reporter: 'Repórter', leitor: 'Leitor', convidado: 'Convidado (perfil antigo)'};
  const rotuloPapel = papel => t(PAPEIS[papel] || String(papel || ''));

  // Datas (nesta página e na Equipe): "agora" no primeiro minuto; "hoje, 14h32"; "ontem, 21h10"; "18 de nov., 09h05"; de outro ano, "18 de nov. de 2025".
  const MESES = ['jan.', 'fev.', 'mar.', 'abr.', 'mai.', 'jun.', 'jul.', 'ago.', 'set.', 'out.', 'nov.', 'dez.'];
  const MESES_EN = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const doisDigitos = n => String(n).padStart(2, '0');
  function data(iso, agora = new Date()) {
    const quando = new Date(iso);
    if (!iso || Number.isNaN(quando.getTime())) return '';
    const hora = `${doisDigitos(quando.getHours())}${lingua() === 'en' ? ':' : 'h'}${doisDigitos(quando.getMinutes())}`;
    const dia = d => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
    const diferenca = Math.round((dia(agora) - dia(quando)) / 86400000);
    if (agora - quando >= 0 && agora - quando < 60000) return t('agora');
    if (diferenca === 0) return t('hoje, {hora}', {hora});
    if (diferenca === 1) return t('ontem, {hora}', {hora});
    const mes = (lingua() === 'en' ? MESES_EN : MESES)[quando.getMonth()];
    const diaDoMes = quando.getDate(), outroAno = quando.getFullYear() !== agora.getFullYear();
    if (lingua() === 'en') return outroAno ? `${mes} ${diaDoMes}, ${quando.getFullYear()}` : `${mes} ${diaDoMes}, ${hora}`;
    return outroAno ? `${diaDoMes} de ${mes} de ${quando.getFullYear()}` : `${diaDoMes} de ${mes}, ${hora}`;
  }
  // Reais: gasto sempre com centavos; teto sem centavos quando inteiro (W08, regra 7: nunca em tokens).
  function reais(valor, {centavos = true} = {}) {
    const numero = Number(valor);
    if (!Number.isFinite(numero)) return '—';
    const inteiro = Number.isInteger(numero);
    return `R$ ${new Intl.NumberFormat('pt-BR', {minimumFractionDigits: centavos || !inteiro ? 2 : 0, maximumFractionDigits: 2}).format(numero)}`;
  }

  // --- a sessão: quem é a pessoa, a redação e o que o servidor lhe permite ---------------------------------------------------------------
  let promessaDaSessao = null;
  function sessao(recarregar = false) {
    if (!promessaDaSessao || recarregar) {
      promessaDaSessao = Promise.resolve(window.fetch('/api/sessao', {headers: {Accept: 'application/json'}, credentials: 'same-origin'}))
        .then(resposta => (resposta?.ok ? resposta.json() : null)).catch(() => null);
    }
    return promessaDaSessao;
  }
  let dadosDaSessao = null;
  const capacidade = nome => !!dadosDaSessao?.capacidades?.includes(nome);

  // --- a moldura: abas, linha de estado e um painel por aba -----------------------------------------------------------------------------
  const legado = [...area.children];  // o que Configurações já tinha: vira o painel da aba Configurações
  const abas = no('nav', 'mesa-tabs conta-abas'); abas.setAttribute('aria-label', 'Conta'); abas.hidden = true;
  const linhaDeEstado = no('p', 'conta-estado'); linhaDeEstado.setAttribute('role', 'status'); linhaDeEstado.setAttribute('aria-live', 'polite'); linhaDeEstado.hidden = true;
  const registro = new Map();  // id -> {rotulo, capacidade, painel, botao, montado, montar, abrir}
  function definirAba(id, config) {
    const painel = no('div', 'conta-painel'); painel.id = `conta-painel-${id}`; painel.hidden = true;
    const controle = botao(config.rotulo, '', () => abrir(id)); controle.id = `conta-aba-${id}`; controle.setAttribute('aria-pressed', 'false');
    controle.setAttribute('aria-controls', painel.id);
    registro.set(id, {...config, painel, botao: controle, montado: false});
    abas.append(controle);
    return painel;
  }
  const painelDaConta = definirAba('conta', {rotulo: 'Minha conta', montar: montarMinhaConta, abrir: recarregarMinhaConta});
  const painelDeConfiguracoes = definirAba('configuracoes', {rotulo: 'Configurações', capacidade: 'ia-config'});
  painelDeConfiguracoes.append(...legado);
  area.replaceChildren(abas, linhaDeEstado, ...[...registro.values()].map(aba => aba.painel));
  let abaAtual = 'conta';

  function registrarAba(id, config) {
    const painel = definirAba(id, config);
    // A ordem das abas é a do desenho: Minha conta, Equipe, Configurações.
    const configuracoes = registro.get('configuracoes');
    abas.insertBefore(registro.get(id).botao, configuracoes.botao);
    area.insertBefore(painel, configuracoes.painel);
    atualizarAbas();
  }
  function abasVisiveis() { return [...registro].filter(([id, aba]) => id === 'conta' || !aba.capacidade || capacidade(aba.capacidade)); }
  function atualizarAbas() {
    const visiveis = abasVisiveis();
    for (const [id, aba] of registro) aba.botao.hidden = !visiveis.some(([outro]) => outro === id);
    abas.hidden = visiveis.length < 2;  // quem só tem Minha conta não vê a linha de abas
  }
  function estado(texto, {erro = false} = {}) {
    linhaDeEstado.replaceChildren();
    linhaDeEstado.hidden = !texto;
    linhaDeEstado.dataset.tom = erro ? 'erro' : 'ok';
    linhaDeEstado.setAttribute('role', erro ? 'alert' : 'status');
    if (texto) linhaDeEstado.append(...(erro ? [] : [no('span', 'conta-estado-marca', '✓'), ' ']), no('span', '', texto));
  }
  function titulo(texto, descricao = '', dadoDeFora = false) {
    const cabeca = document.getElementById('area-titulo'), apoio = document.getElementById('area-descricao');
    if (!cabeca) return;
    cabeca.textContent = texto;
    if (dadoDeFora) cabeca.setAttribute('translate', 'no'); else cabeca.removeAttribute('translate');
    if (apoio) { apoio.removeAttribute('translate'); apoio.textContent = descricao; apoio.hidden = !descricao; }
  }
  function tituloDaAba() {
    const aba = registro.get(abaAtual);
    if (aba?.titulo) return aba.titulo();
    titulo(t(abaAtual === 'conta' ? 'Minha conta' : 'Configurações'));
  }
  async function abrir(id = abaAtual) {
    dadosDaSessao = await sessao();
    atualizarAbas();
    if (!abasVisiveis().some(([outro]) => outro === id)) id = 'conta';
    abaAtual = id;
    for (const [outro, aba] of registro) { aba.painel.hidden = outro !== id; aba.botao.setAttribute('aria-pressed', String(outro === id)); }
    estado('');
    const aba = registro.get(id);
    if (!aba.montado && aba.montar) { aba.montado = true; aba.montar(aba.painel); }
    aba.abrir?.();
    tituloDaAba();
    marcarPerfil(true);
  }
  // O perfil da barra leva a página; com ela aberta, ele (e só ele) leva aria-current, e nenhum item de área fica selecionado.
  function marcarPerfil(aberta) {
    const perfil = document.getElementById('ver-configuracoes');
    if (!perfil) return;
    if (aberta) perfil.setAttribute('aria-current', 'page'); else perfil.removeAttribute('aria-current');
  }
  registrarGanchoArea({depois: nome => { if (nome === 'configuracoes') abrir(abaAtual); else marcarPerfil(false); }});
  window.addEventListener('mesa-contexto-alterado', () => { if (!area.hidden) tituloDaAba(); });
  window.addEventListener('catalogo-carregado', () => { if (!area.hidden) tituloDaAba(); });
  window.addEventListener('vlado-idioma', () => { if (!area.hidden) tituloDaAba(); });
  // O perfil sempre abre Minha conta. No navegador o ouvinte de captura roda antes do da barra; sem isso, o segundo `abrir` corrige a aba.
  document.getElementById('ver-configuracoes')?.addEventListener('click', () => {
    const outra = abaAtual !== 'conta';
    abaAtual = 'conta';
    if (outra && !area.hidden) abrir('conta');
  }, true);

  // --- peças dos cartões -------------------------------------------------------------------------------------------------------------------
  // Cartão: o bloco base de estados (fundo, borda, raio 12, preenchimento 16), com o título em <h2>.
  function cartao(rotulo, classe = '') {
    const raiz = no('section', `conta-cartao ${classe}`.trim());
    const cabeca = no('h2', 'conta-cartao-titulo', t(rotulo)); cabeca.id = `conta-cartao-${++sequencia}`;
    raiz.setAttribute('aria-labelledby', cabeca.id);
    const corpo = no('div', 'conta-cartao-corpo');
    raiz.append(cabeca, corpo);
    return {raiz, corpo, titulo: cabeca};
  }
  let sequencia = 0;
  // Cada cartão carrega sozinho: esqueleto enquanto espera; se falha, o erro do serviço de estados no lugar dele, e os outros seguem.
  async function carregar(cartaoAlvo, buscar, desenhar) {
    const espera = window.Estados?.esqueleto(cartaoAlvo.corpo, {atraso: 300});
    try {
      const resultado = await buscar();
      espera?.parar();
      desenhar(resultado);
    } catch (falha) {
      espera?.parar();
      if (falha?.rede || falha?.result?.codigo === 'sessao_expirada') { /* a Mesa trata a sessão vencida em outro lugar */ }
      window.Estados.erro(cartaoAlvo.corpo, {titulo: 'Não deu para carregar.', texto: falha?.message,
        acoes: [{rotulo: 'Tentar de novo', aoClicar: () => carregar(cartaoAlvo, buscar, desenhar)}]});
    }
  }
  const linha = (...filhos) => { const l = no('div', 'conta-linha'); l.append(...filhos); return l; };
  const apoio = texto => no('p', 'conta-apoio', t(texto));

  // --- o diálogo com senha (#dialogo-senha): a variante e o reenvio com `senha` estão em dialogo.js (Dialogo.comSenha) ---------------------------
  const sensivel = opcoes => window.Dialogo.comSenha(opcoes);
  const recusaDaSenha = (falha, opcoes) => window.Dialogo.recusaDaSenha(falha, opcoes);

  // --- Minha conta (W08) ---------------------------------------------------------------------------------------------------------------
  const nuvem = {};  // os cartões montados
  let perfilAtual = null;
  function montarMinhaConta(painel) {
    nuvem.perfil = cartao('Perfil');
    nuvem.seguranca = cartao('Entrada e segurança');
    nuvem.sessoes = cartao('Onde sua conta está aberta');
    nuvem.uso = cartao('Seu uso neste mês', 'conta-cartao-uso');
    nuvem.dados = cartao('Seus dados');
    nuvem.perfil.raiz.dataset.cartao = 'perfil'; nuvem.seguranca.raiz.dataset.cartao = 'seguranca'; nuvem.sessoes.raiz.dataset.cartao = 'sessoes';
    nuvem.uso.raiz.dataset.cartao = 'uso'; nuvem.dados.raiz.dataset.cartao = 'dados';
    const grade = no('div', 'conta-grade');
    const esquerda = no('div', 'conta-coluna'), direita = no('div', 'conta-coluna');
    esquerda.append(nuvem.perfil.raiz, nuvem.seguranca.raiz, nuvem.dados.raiz);
    direita.append(nuvem.sessoes.raiz, nuvem.uso.raiz);
    grade.append(esquerda, direita);
    painel.append(grade);
  }
  function recarregarMinhaConta() {
    carregar(nuvem.perfil, () => api('conta-ver', {}), desenharPerfilESeguranca);
    carregarSessoes();
    carregarUso();
    desenharDados();
  }

  // Perfil e Entrada e segurança vêm da mesma resposta (`conta-ver`).
  function desenharPerfilESeguranca(resposta) {
    perfilAtual = resposta;
    desenharPerfil(resposta);
    desenharSeguranca(resposta);
  }
  function desenharPerfil(resposta, editando = false) {
    const {conta, organizacao} = resposta;
    const corpo = nuvem.perfil.corpo;
    const nomeLinha = no('div', 'conta-linha');
    if (editando) {
      const rotulo = no('label', 'conta-campo', t('Nome'));
      const entrada = document.createElement('input'); entrada.type = 'text'; entrada.maxLength = 120; entrada.value = conta.nome || '';
      entrada.autocomplete = 'name'; entrada.setAttribute('translate', 'no');
      rotulo.append(entrada);
      const salvar = botao('Salvar', '', async () => {
        const nome = entrada.value.trim();
        if (!nome) { window.Estados.erroCampo(entrada, 'Falta o nome. Escreva o seu nome.'); return; }
        const restaurar = window.Estados.ocupado(salvar, 'Salvando…');
        try {
          const nova = await api('conta-atualizar', {nome});
          restaurar();
          desenharPerfilESeguranca(nova);
          atualizarBarra(nova.conta);
          estado(t('Nome atualizado.'));
        } catch (falha) { restaurar(); window.Estados.erroCampo(entrada, falha.message); }
      });
      const cancelar = botao('Cancelar', 'secondary', () => { desenharPerfil(resposta); nuvem.perfil.corpo.querySelector('.conta-mudar-nome')?.focus(); });
      entrada.addEventListener('keydown', evento => { if (evento.key === 'Enter') { evento.preventDefault(); salvar.click(); } });
      const acoes = no('div', 'conta-acoes'); acoes.append(salvar, cancelar);
      nomeLinha.append(rotulo);
      corpo.replaceChildren(nomeLinha, acoes);
      entrada.focus();
      return;
    }
    const mudar = botao('Mudar nome', 'secondary conta-mudar-nome', () => desenharPerfil(resposta, true));
    nomeLinha.append(dado(conta.nome, 'strong'), mudar);
    let contato;
    if (conta.email) { contato = dado(conta.email, 'p'); contato.className = 'conta-texto'; }
    else { contato = no('p', 'conta-apoio'); contato.append(t('login'), ' ', dado(conta.login || '')); }
    const papel = no('p', 'conta-apoio'); papel.append(rotuloPapel(conta.papel), ' · ', dado(organizacao?.nome || ''));
    corpo.replaceChildren(nomeLinha, contato, papel, preferencias(conta));
  }
  // Idioma muda o idioma da Mesa e grava o da conta; Tema fica só neste navegador (contrato, 2.3).
  function preferencias(conta) {
    const grupo = no('div', 'conta-preferencias');
    const idioma = document.createElement('select'); idioma.id = 'conta-idioma';
    idioma.append(new Option('Português', 'pt'), new Option('English', 'en'));
    idioma.value = lingua();
    const rotuloIdioma = no('label', 'conta-campo', t('Idioma')); rotuloIdioma.append(idioma);
    const apoioIdioma = no('p', 'conta-apoio', t('Também é o idioma dos e-mails do Vlado.')); apoioIdioma.id = 'conta-idioma-apoio';
    idioma.setAttribute('aria-describedby', apoioIdioma.id);
    idioma.addEventListener('change', async () => {
      const nova = idioma.value;
      window.Estados.limparErroCampo(idioma);
      await window.I18N?.definir?.(nova);
      try { await api('conta-atualizar', {idioma: nova}); estado(t('Idioma da conta salvo.')); }
      catch (falha) { window.Estados.erroCampo(idioma, falha.message, {foco: false}); }
    });
    window.addEventListener('vlado-idioma', () => { idioma.value = lingua(); });
    const tema = document.createElement('select'); tema.id = 'conta-tema';
    tema.append(new Option(t('Do sistema'), 'sistema'), new Option(t('Claro'), 'light'), new Option(t('Escuro'), 'dark'));
    const guardado = () => { try { return localStorage.getItem(CHAVE_TEMA); } catch (_) { return null; } };
    const lerTema = () => (['light', 'dark'].includes(guardado()) ? guardado() : 'sistema');
    tema.value = lerTema();
    const rotuloTema = no('label', 'conta-campo', t('Tema')); rotuloTema.append(tema);
    tema.addEventListener('change', () => {
      // O mesmo estado do botão "Modo escuro" do cabeçalho (desktop.js): a chave guardada e o aviso aos ouvintes.
      try { if (tema.value === 'sistema') localStorage.removeItem(CHAVE_TEMA); else localStorage.setItem(CHAVE_TEMA, tema.value); } catch (_) { /* a troca vale mesmo assim */ }
      const aviso = new Event('storage'); aviso.key = CHAVE_TEMA; aviso.newValue = tema.value === 'sistema' ? null : tema.value;
      window.dispatchEvent(aviso);
    });
    document.getElementById('mesa-tema')?.addEventListener('click', () => { tema.value = lerTema(); });
    grupo.append(...[rotuloIdioma, rotuloTema].map(r => { const celula = no('div', 'conta-preferencia'); celula.append(r); return celula; }));
    grupo.firstChild.append(apoioIdioma);
    return grupo;
  }
  // O perfil da barra acompanha o nome novo.
  function atualizarBarra(conta) {
    const perfil = document.getElementById('ver-configuracoes');
    if (!perfil || !conta?.nome) return;
    const nome = String(conta.nome).trim();
    const iniciais = nome.split(/\s+/).filter(Boolean).slice(0, 2).map(parte => parte[0].toUpperCase()).join('');
    const avatar = perfil.querySelector('.mesa-avatar'), rotulo = perfil.querySelector('.mesa-perfil-nome');
    if (avatar) avatar.textContent = iniciais;
    if (rotulo) rotulo.textContent = nome;
  }

  function desenharSeguranca(resposta) {
    const {conta} = resposta;
    const rotulo = no('div', 'conta-rotulo');
    rotulo.append(no('span', 'conta-texto', t('Senha')));
    const definida = conta.senha_definida_em ? new Date(conta.senha_definida_em) : null;
    if (definida && !Number.isNaN(definida.getTime())) {
      const agora = new Date(), dia = d => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
      const dias = Math.max(0, Math.round((dia(agora) - dia(definida)) / 86400000));
      rotulo.append(no('span', 'conta-apoio', dias === 0 ? t('definida hoje') : dias === 1 ? t('definida há 1 dia') : t('definida há {n} dias', {n: dias})));
    }
    const trocar = botao('Trocar senha', 'secondary conta-trocar-senha', () => trocarSenha(trocar));
    nuvem.seguranca.corpo.replaceChildren(linha(rotulo, trocar));
  }

  // O diálogo "Trocar senha": a variante com senha, com três campos e a conferência antes de enviar (W08, regra 2).
  async function trocarSenha(gatilho) {
    let resultado = null;
    const confirmado = await window.Dialogo.confirmar({
      variante: 'simples', titulo: 'Trocar senha', texto: 'As outras sessões desta conta serão encerradas. Esta continua aberta.',
      acao: 'Trocar senha', ocupado: 'Trocando…', gatilho,
      campos: [
        {id: 'atual', rotulo: 'Senha atual', autocomplete: 'current-password'},
        {id: 'nova', rotulo: 'Nova senha', autocomplete: 'new-password', apoio: 'De 12 a 256 caracteres. Pode colar ou usar o gerenciador de senhas.'},
        {id: 'repita', rotulo: 'Repita a nova senha', autocomplete: 'new-password'},
      ],
      validar(valores) {
        const recusas = {};
        if (!valores.atual) recusas.atual = 'Falta a senha atual. Digite a senha com que você entra hoje.';
        if (valores.nova.length < 12 || valores.nova.length > 256) recusas.nova = 'A senha deve ter de 12 a 256 caracteres.';
        else if (valores.nova !== valores.repita) recusas.repita = 'As duas senhas não coincidem. Digite a mesma senha nos dois campos.';
        return recusas;
      },
      async executar(ctx) {
        const valores = ctx.valores();
        try { resultado = await api('conta-senha-trocar', {senha_atual: valores.atual, senha_nova: valores.nova}); }
        catch (falha) { throw recusaDaSenha(falha, {campo: 'atual', incorreta: 'Senha atual incorreta. Confira e tente de novo.'}); }
      },
    });
    if (!confirmado || !resultado) return;
    const n = Number(resultado.sessoes_encerradas) || 0;
    estado(`${t('Senha trocada.')} ${n === 0 ? t('Nenhuma outra sessão estava aberta.') : n === 1 ? t('1 outra sessão foi encerrada.') : t('{n} outras sessões foram encerradas.', {n})}`);
    carregarSessoes();
    carregar(nuvem.perfil, () => api('conta-ver', {}), desenharPerfilESeguranca);
  }

  // Onde sua conta está aberta: a sessão em uso primeiro, sem botão; as outras com "Encerrar" (imediato, sem diálogo: W08, regra 5).
  function carregarSessoes() {
    carregar(nuvem.sessoes, () => api('conta-sessoes', {}), resposta => desenharSessoes(resposta.sessoes || []));
  }
  function desenharSessoes(lista) {
    const ordenada = [...lista.filter(s => s.atual), ...lista.filter(s => !s.atual)];
    const corpo = nuvem.sessoes.corpo;
    const itens = no('ul', 'conta-sessoes');
    for (const item of ordenada) {
      const texto = no('div', 'conta-rotulo');
      texto.append(dado(item.aparelho || '', 'span'));
      texto.firstChild.className = 'conta-texto';
      const quando = [data(item.ultimo_uso || item.criada_em), item.ip].filter(Boolean);
      const detalhe = no('span', 'conta-apoio'); detalhe.append(quando[0] || '', ...(item.ip ? [' · ', dado(item.ip)] : []));
      texto.append(detalhe);
      const direita = item.atual ? no('span', 'conta-esta-sessao', t('Esta sessão')) : botao('Encerrar', 'secondary', evento => encerrar(item, evento.currentTarget));
      if (!item.atual) direita.setAttribute('aria-label', `${t('Encerrar')}: ${item.aparelho || ''}`);
      const linhaDaSessao = no('li', 'conta-sessao'); linhaDaSessao.dataset.sessao = item.id;
      linhaDaSessao.append(linha(texto, direita));
      itens.append(linhaDaSessao);
    }
    const partes = [itens];
    if (lista.length >= 2) {
      const todas = botao('Encerrar todas as outras', 'secondary conta-encerrar-outras', () => encerrarOutras(todas));
      partes.push(todas, apoio('Encerrar vale na próxima ação daquele aparelho.'));
    }
    corpo.replaceChildren(...partes);
  }
  async function encerrar(item, controle) {
    const restaurar = window.Estados.ocupado(controle, 'Encerrando…');
    try {
      const resposta = await api('conta-sessao-encerrar', {sessao: item.id});
      desenharSessoes(resposta.sessoes || []);
      estado(t('Sessão encerrada: {aparelho}.', {aparelho: item.aparelho || ''}));
    } catch (falha) {
      restaurar();
      if (falha?.result?.erro === 'Sessão não encontrada.') { carregarSessoes(); return; }  // já tinha acabado: a lista recarrega, sem erro
      const aviso = no('p', 'campo-erro', falha.message); aviso.setAttribute('role', 'alert');
      controle.closest('.conta-sessao')?.append(aviso);
    }
  }
  async function encerrarOutras(controle) {
    const restaurar = window.Estados.ocupado(controle, 'Encerrando…');
    try {
      const resposta = await api('conta-sessoes-encerrar-outras', {});
      desenharSessoes(resposta.sessoes || []);
      const n = Number(resposta.encerradas) || 0;
      estado(n === 1 ? t('1 sessão encerrada.') : t('{n} sessões encerradas.', {n}));
    } catch (falha) {
      restaurar();
      const aviso = no('p', 'campo-erro', falha.message); aviso.setAttribute('role', 'alert'); controle.after(aviso);
    }
  }

  // Seu uso neste mês: o gasto da conta contra o teto, sempre em reais. Sem a rota, o cartão some.
  async function carregarUso() {
    nuvem.uso.raiz.hidden = true;
    try {
      const resposta = await window.fetch('/api/cota', {headers: {Accept: 'application/json'}, credentials: 'same-origin'});
      if (!resposta?.ok) return;
      const bloco = (await resposta.json())?.conta;
      const gasto = Number(bloco?.gasto_brl), teto = Number(bloco?.teto_brl);
      if (!bloco || !Number.isFinite(gasto) || !Number.isFinite(teto) || teto <= 0) return;
      const esgotada = !!bloco.esgotada, pct = Math.min(100, Math.round(gasto / teto * 100));
      const valor = t('{gasto} de {teto}', {gasto: reais(gasto), teto: reais(teto, {centavos: false})});
      const medidor = no('div', 'mesa-medidor'); medidor.setAttribute('role', 'img'); medidor.style.setProperty('--uso', `${esgotada ? 100 : pct}%`);
      medidor.setAttribute('aria-label', esgotada ? t('Cota do mês esgotada: {valor}', {valor}) : t('{pct}% da cota usada', {pct}));
      const rotulo = no('div', 'conta-linha');
      rotulo.append(no('span', 'conta-texto', esgotada ? `! ${t('Cota esgotada')}` : t('Gasto com IA')), no('strong', 'conta-valor', valor));
      nuvem.uso.raiz.dataset.esgotada = String(esgotada);
      nuvem.uso.corpo.replaceChildren(rotulo, medidor, apoio('O teto é definido pelo dono da redação.'));
      nuvem.uso.raiz.hidden = false;
    } catch (_) { /* sem a rota, o cartão some */ }
  }

  // Seus dados: o caminho por pessoa; exportar e excluir ainda não existem (exceções declaradas).
  function desenharDados() {
    const dono = perfilAtual?.conta?.papel === 'dono' || dadosDaSessao?.conta?.papel === 'dono';
    nuvem.dados.corpo.replaceChildren(no('p', 'conta-texto', t(dono
      ? 'Exportar seus dados e excluir sua conta ainda não estão na Mesa. Para pedir, fale com quem administra o serviço.'
      : 'Exportar seus dados e excluir sua conta ainda não estão na Mesa. Para pedir, fale com o dono da redação.')));
  }

  window.Conta = {abrir, registrarAba, estado, titulo, sensivel, recusaDaSenha, no, botao, dado, apoio, cartao, carregar, linha, data, reais, rotuloPapel,
    capacidade, sessao, atualizarAbas};

  // O perfil da barra aparece para qualquer conta (não só para o dono) e leva a Minha conta.
  sessao().then(dados => {
    dadosDaSessao = dados;
    if (!dados?.conta?.id) return;
    const perfil = document.getElementById('ver-configuracoes');
    if (perfil) perfil.hidden = false;
    atualizarAbas();
  });
})();
