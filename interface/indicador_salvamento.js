'use strict';
// Integration point with the drafts module (continuidade.js, owned by the Salvamento front), kept
// apart so neither file edits the other. Two pieces:
//  - header indicator: Rascunhos.indicador.assinar(fn) and the `vlado:rascunho-estado` event on
//    document, both with {tipo, hora, telas}; only the status is shown, never draft text;
//  - resume summary at the entry of the evidence boards: Continuidade.montar(alvo, caso), shown only
//    when /api/integracao announces `continuidade_resumo` and the account is not a guest.
// Without those APIs (older continuidade.js or server) both stay hidden.
window.IndicadorSalvamento = (() => {
  const t = (texto, vars) => window.Quadros ? window.Quadros.t(texto, vars) : texto;
  const TEXTOS = {salvando: 'Salvando rascunho…', salvo: 'Rascunho salvo às {hora}', sem_rede: 'Sem conexão — rascunho salvo neste navegador',
    erro: 'Rascunho não enviado ao servidor — salvo neste navegador', sem_chave: 'Rascunho não guardado: retire a chave, senha ou token do texto',
    decidir: 'Escolha qual rascunho manter'};
  let indicador = null, desligar = null;
  function criar() {
    if (indicador) return indicador;
    indicador = element('p', '', 'save-indicator');
    indicador.id = 'mesa-salvamento';
    indicador.setAttribute('role', 'status'); indicador.setAttribute('aria-live', 'polite'); indicador.hidden = true;
    const cabecalho = document.querySelector('.app-header');
    const nota = cabecalho?.querySelector('.header-note');
    if (nota) nota.before(indicador); else cabecalho?.append(indicador);
    return indicador;
  }
  // {tipo, hora, telas} -> text of the indicator; `ocioso` (nothing pending) hides it.
  function mostrar(dados) {
    const alvo = criar();
    const tipo = dados?.tipo;
    if (!tipo || tipo === 'ocioso' || !TEXTOS[tipo] || (tipo === 'salvo' && !dados.hora)) { alvo.hidden = true; alvo.textContent = ''; alvo.removeAttribute('data-tipo'); return; }
    alvo.dataset.tipo = tipo;
    const telas = Number(dados.telas) > 1 ? ` · ${t('{n} telas', {n: dados.telas})}` : '';
    alvo.textContent = t(TEXTOS[tipo], {hora: String(dados.hora || '')}) + telas;
    alvo.hidden = false;
  }
  function ligar() {
    criar();
    desligar?.(); desligar = null;
    const api = window.Rascunhos?.indicador;
    if (typeof api?.assinar === 'function') desligar = api.assinar(mostrar);
  }
  document.addEventListener('vlado:rascunho-estado', evento => mostrar(evento.detail));

  // Resume summary at the top of the evidence boards (collapsed, admins only).
  async function retomada() {
    const area = $('area-quadros');
    if (!area || document.body.dataset.papel === 'convidado' || typeof window.Continuidade?.montar !== 'function') return;
    let caixa = $('quadros-retomada');
    const caso = window.contextoCaso?.() || '';
    const anunciado = window.Quadros ? await window.Quadros.disponivel('continuidade_resumo') : false;
    if (!anunciado || !caso) { if (caixa) caixa.hidden = true; return; }
    if (!caixa) {
      caixa = element('details', undefined, 'quadros-retomada'); caixa.id = 'quadros-retomada';
      caixa.append(element('summary', t('O que já foi feito e o que falta nesta apuração')), element('div'));
      $('quadros-abas').before(caixa);
    }
    caixa.hidden = false;
    await window.Continuidade.montar(caixa.lastChild, caso);
  }
  window.addEventListener('quadros-abrir', retomada);
  window.addEventListener('mesa-contexto-alterado', () => { if (!$('area-quadros')?.hidden) retomada(); });
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', ligar); else ligar();
  return {ligar, mostrar, retomada};
})();
