'use strict';
// O tema antes da primeira pintura, para a Mesa não piscar ao abrir (UX-07): sem defer, no <head>. Com "claro" ou "escuro" guardado, vale o guardado; sem nada
// guardado ("Do sistema", em Minha conta), vale a preferência do sistema. O desktop.js assume daí (botão do cabeçalho, avisos de outras abas).
(() => {
  let guardado = null;
  try { guardado = localStorage.getItem('apuracao:tema'); } catch (_) { /* armazenamento bloqueado: segue o sistema */ }
  const claro = guardado === 'light' || (guardado !== 'dark' && typeof matchMedia === 'function' && matchMedia('(prefers-color-scheme: light)').matches);
  document.documentElement.dataset.theme = claro ? 'light' : 'dark';
})();
