'use strict';
// Estados de tela da Mesa (docs/design/componentes.md#estados, W11 regras 1 a 6 e 9; UX-08, UX-15, UX-18).
//
//   Estados.vazio(alvo, {titulo, texto, acao: {rotulo, aoClicar}})   o que é a coisa e uma ação (regra 1)
//   Estados.esqueleto(alvo, {atraso, rotulo})                        espera curta: esqueleto só depois de `atraso` ms (padrão 300)
//   Estados.espera(alvo, {etapa, aoCancelar})                        espera longa: etapa por extenso, barra, aviso e Cancelar (regras 2 e 3)
//   Estados.erro(alvo, {titulo, texto, preservado, acoes, detalhes}) erro em três partes, nas cores de erro (regras 4 e 6)
//   Estados.erroCampo(campo, mensagem) / Estados.limparErroCampo(campo)  erro junto ao campo, com aria-invalid e foco (regra 5)
//   Estados.ocupado(botao, gerundio)                                 botão ocupado: gerúndio, largura mantida, aria-busy; devolve restaurar()
//
// Só dois padrões de "ocupado": esqueleto (curto) e barra com etapa (longo), ambos com aria-busy. Mudança de estado é anunciada:
// role="status" para vazio, ocupado e concluído; role="alert" para erro (regra 9).
(() => {
  const t = (pt, vars) => (window.I18N ? window.I18N.t(pt, vars) : String(pt).replace(/\{(\w+)\}/g, (todo, nome) => vars?.[nome] ?? todo));
  const SVG = 'http://www.w3.org/2000/svg';
  let sequencia = 0;

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
  // O ✕ não existe nas fontes da Mesa e a CSP não aceita imagem data:; o sinal é SVG criado aqui (docs/design/icones/sinal-sem-suporte.svg).
  function sinalErro() {
    const svg = document.createElementNS(SVG, 'svg');
    svg.setAttribute('viewBox', '0 0 24 24'); svg.setAttribute('aria-hidden', 'true'); svg.setAttribute('class', 'estado-sinal');
    const caminho = document.createElementNS(SVG, 'path'); caminho.setAttribute('d', 'M7 7l10 10M17 7L7 17');
    svg.append(caminho);
    return svg;
  }

  function vazio(alvo, {titulo, texto, acao} = {}) {
    const bloco = no('div', 'estado-bloco'); bloco.dataset.estado = 'vazio'; bloco.setAttribute('role', 'status');
    if (titulo) bloco.append(no('p', 'estado-titulo', t(titulo)));
    if (texto) bloco.append(no('p', 'estado-texto', t(texto)));
    if (acao) {
      const acoes = no('div', 'estado-acoes');
      acoes.append(botao(acao.rotulo, '', acao.aoClicar));
      bloco.append(acoes);
    }
    alvo.replaceChildren(bloco);
    return bloco;
  }

  // Espera curta. O marcador entra já, com o texto para leitor de tela; o esqueleto aparece só se a espera passar de `atraso` ms e o
  // marcador ainda estiver na tela (quem recebe o conteúdo troca os filhos do alvo, e o marcador sai junto). aria-busy no alvo.
  function esqueleto(alvo, {atraso = 300, rotulo = 'Carregando…'} = {}) {
    const marcador = no('div', 'estado-espera-curta'); marcador.dataset.estado = 'carregando'; marcador.setAttribute('role', 'status');
    marcador.append(no('span', 'sr-only', t(rotulo)));
    alvo.replaceChildren(marcador);
    alvo.setAttribute('aria-busy', 'true');
    let observador = null;
    const encerrar = () => { observador?.disconnect(); observador = null; alvo.removeAttribute('aria-busy'); };
    const mostrar = () => {
      if (marcador.parentNode !== alvo) { alvo.removeAttribute('aria-busy'); return; }
      const barras = no('div', 'estado-esqueleto'); barras.setAttribute('aria-hidden', 'true');
      for (let i = 0; i < 3; i++) barras.append(no('span'));
      marcador.append(barras);
      if (typeof MutationObserver === 'function') {
        observador = new MutationObserver(() => { if (marcador.parentNode !== alvo) encerrar(); });
        observador.observe(alvo, {childList: true});
      }
    };
    const relogio = setTimeout(mostrar, atraso);
    return {parar() { clearTimeout(relogio); observador?.disconnect(); if (marcador.parentNode === alvo) marcador.remove(); alvo.removeAttribute('aria-busy'); }};
  }

  // Espera longa (OCR, IA): etapa por extenso, barra, aviso de que dá para sair da tela e Cancelar.
  function espera(alvo, {etapa = '', aoCancelar} = {}) {
    const bloco = no('div', 'estado-bloco'); bloco.dataset.estado = 'ocupado'; bloco.setAttribute('role', 'status'); bloco.setAttribute('aria-busy', 'true');
    const texto = no('p', 'estado-titulo', t(etapa));
    const barra = no('div', 'medidor-progresso'); barra.setAttribute('role', 'progressbar');
    barra.setAttribute('aria-valuemin', '0'); barra.setAttribute('aria-valuemax', '100'); barra.setAttribute('aria-label', t('Progresso'));
    bloco.append(texto, barra, no('p', 'estado-nota', t('Você pode sair desta tela. A operação continua.')));
    let cancelar = null;
    if (aoCancelar) { cancelar = botao('Cancelar', 'secondary', aoCancelar); const acoes = no('div', 'estado-acoes'); acoes.append(cancelar); bloco.append(acoes); }
    alvo.replaceChildren(bloco);
    return {
      bloco,
      etapa(novoTexto, fracao) {
        if (novoTexto !== undefined) texto.textContent = t(novoTexto);
        if (typeof fracao === 'number' && Number.isFinite(fracao)) {
          const pct = Math.max(0, Math.min(100, Math.round(fracao * 100)));
          barra.style.setProperty('--uso', `${pct}%`); barra.setAttribute('aria-valuenow', String(pct));
        }
      },
      parar() { bloco.removeAttribute('aria-busy'); bloco.remove(); },
    };
  }

  // Erro em três partes: o que houve (título), o que foi preservado e o que fazer (texto/ações). O código interno vai em "Detalhes".
  function erro(alvo, {titulo, texto, preservado, acoes = [], detalhes} = {}) {
    const bloco = no('div', 'estado-bloco estado-erro'); bloco.dataset.estado = 'erro'; bloco.setAttribute('role', 'alert');
    const cabeca = no('p', 'estado-titulo'); cabeca.append(sinalErro(), no('span', '', t(titulo || 'Não deu para concluir.')));
    bloco.append(cabeca);
    if (texto) bloco.append(no('p', 'estado-texto', t(texto)));
    if (preservado) bloco.append(no('p', 'estado-texto', t(preservado)));
    if (acoes.length) {
      const grupo = no('div', 'estado-acoes');
      acoes.forEach((acao, indice) => grupo.append(botao(acao.rotulo, indice === 0 && acao.principal !== false ? '' : 'secondary', acao.aoClicar)));
      bloco.append(grupo);
    }
    if (detalhes) {
      const caixa = no('details', 'estado-detalhes');
      const codigo = no('code', '', String(detalhes)); codigo.setAttribute('translate', 'no');
      caixa.append(no('summary', '', t('Detalhes')), codigo);
      bloco.append(caixa);
    }
    alvo.replaceChildren(bloco);
    return bloco;
  }

  // Erro de campo (W11 regra 5): mensagem logo depois do campo, ligada por aria-describedby, aria-invalid e foco no campo.
  function mensagemDe(campo) { return campo._estadoErro || null; }
  function limparErroCampo(campo) {
    const mensagem = mensagemDe(campo);
    if (!mensagem) return;
    const ids = (campo.getAttribute('aria-describedby') || '').split(/\s+/).filter(id => id && id !== mensagem.id);
    if (ids.length) campo.setAttribute('aria-describedby', ids.join(' ')); else campo.removeAttribute('aria-describedby');
    campo.removeAttribute('aria-invalid');
    mensagem.remove(); campo._estadoErro = null;
  }
  function erroCampo(campo, mensagem, {foco = true} = {}) {
    limparErroCampo(campo);
    const aviso = no('p', 'campo-erro', t(mensagem)); aviso.id = `campo-erro-${++sequencia}`;
    campo.after(aviso);
    campo.setAttribute('aria-invalid', 'true');
    campo.setAttribute('aria-describedby', [campo.getAttribute('aria-describedby'), aviso.id].filter(Boolean).join(' '));
    campo._estadoErro = aviso;
    // Some quando a pessoa volta a digitar.
    const aoDigitar = () => { limparErroCampo(campo); campo.removeEventListener('input', aoDigitar); };
    campo.addEventListener('input', aoDigitar);
    if (foco) campo.focus();
    return aviso;
  }

  // Botão ocupado: o rótulo vira o gerúndio da ação, a largura se mantém e cliques novos são ignorados (aria-disabled, sem perder o foco).
  function ocupado(controle, gerundio) {
    const rotulo = controle.textContent;
    const largura = controle.getBoundingClientRect?.().width;
    if (largura) controle.style.minWidth = `${Math.round(largura)}px`;
    const bloquear = evento => { evento.preventDefault(); evento.stopImmediatePropagation(); };
    controle.addEventListener('click', bloquear, true);
    controle.textContent = t(gerundio);
    controle.setAttribute('aria-busy', 'true'); controle.setAttribute('aria-disabled', 'true');
    return function restaurar() {
      controle.removeEventListener('click', bloquear, true);
      controle.textContent = rotulo;
      controle.removeAttribute('aria-busy'); controle.removeAttribute('aria-disabled');
      controle.style.minWidth = '';
    };
  }

  window.Estados = {vazio, esqueleto, espera, erro, erroCampo, limparErroCampo, ocupado};
})();
