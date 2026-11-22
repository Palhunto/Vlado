'use strict';
// O tema antes da primeira pintura, para a Mesa não piscar ao abrir (UX-07): sem defer, no <head>. "claro" e "escuro" guardados valem como estão; "sistema"
// ("Do sistema", em Minha conta, gravado como as outras escolhas) segue a preferência do sistema; sem nada guardado a Mesa abre no escuro, como sempre abriu.
// O desktop.js assume daí (botão do cabeçalho, avisos de outras abas).
(() => {
  let guardado = null;
  try { guardado = localStorage.getItem('apuracao:tema'); } catch (_) { /* armazenamento bloqueado: o escuro de sempre */ }
  const claro = guardado === 'light' || (guardado === 'sistema' && typeof matchMedia === 'function' && matchMedia('(prefers-color-scheme: light)').matches);
  document.documentElement.dataset.theme = claro ? 'light' : 'dark';
})();
