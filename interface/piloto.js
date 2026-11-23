'use strict';
// Hosted mode: guests stay in "Ask the AI"; everyone else gets the profile (Minha conta) and the Configurações button.
// The server enforces every rule; this script only shapes the screen.
(() => {
  const body = document.body;
  if (body.dataset.modo === 'local') return;  // local mode has no accounts: no sign-out, profile or Configurações button
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
    // O perfil abre Minha conta também para ele, só com o que o papel dele alcança (as abas vêm das capacidades da sessão, em conta.js).
    $('ver-configuracoes').hidden = false;
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
})();
