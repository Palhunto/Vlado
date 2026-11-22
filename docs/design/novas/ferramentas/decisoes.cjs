// Decisões do dono de 21/11/2026 aplicadas a qualquer prancha HTML (canvas ou derivada), antes de renderizar.
// P11.8: preenchimento, intervalo e margem fora da grade de 4 px arredondam para cima (6→8, 10→12, 14→16, 18→20, 22→24).
// P11.3: raio de 12 px em todo cartão; 4 px só na folha do documento e no topo das barras (os demais raios não mudam).
// P11.4: órgão público em ameixa (#b0508a no claro, #d46a9c no escuro) no lugar de #3d4a45.
// P11.5: altura mínima no lugar de altura fixa onde o texto não cabia (nó do mapa, perfil da barra lateral).
// P11.7: caminhoDeVolta() põe "‹ Apuração" antes do título "Quadros" nas telas do canvas.
// P15.7: barra lateral de 256 px no lugar de 232 (mudança no canvas autorizada pelo dono em 21/11/2026), para o item ativo,
// a cota e o perfil caberem numa linha; rótulo e contador do item não quebram.
const PROPS = /^(padding|padding-top|padding-right|padding-bottom|padding-left|margin|margin-top|margin-right|margin-bottom|margin-left|gap|row-gap|column-gap)$/;
const arredonda = v => v.replace(/(-?\d+(?:\.\d+)?)px/g, (m, n) => {
  const x = Math.abs(parseFloat(n));
  if (x === 0 || x % 4 === 0) return m;
  return `${Math.sign(parseFloat(n)) * Math.ceil(x / 4) * 4}px`;
});
function declaracoes(css) {
  return css.replace(/([a-z-]+)\s*:\s*([^;"}]+)/g, (m, prop, valor) => {
    if (PROPS.test(prop)) return `${prop}:${arredonda(valor)}`;
    if (prop === 'border-radius' && /^\s*10px\s*$/.test(valor)) return `${prop}:12px`;
    return m;
  });
}
function aplicarDecisoes(html, {escuro = false} = {}) {
  const ameixa = escuro ? '#d46a9c' : '#b0508a';
  return html
    .replace(/gap: 10px; height: 44px; padding: 0 8px/g, 'gap: 10px; min-height: 44px; padding: 0 8px')  // P11.5: perfil da barra lateral
    .replace(/(<nav aria-label="Áreas" style="width: )232px/g, '$1256px')  // P15.7: barra lateral de 256 px
    .replace(/style="([^"]*)"/g, (m, s) => `style="${declaracoes(s)}"`)
    .replace(/<style>([\s\S]*?)<\/style>/g, (m, s) => `<style>${declaracoes(s)}</style>`)
    .replace(/#3d4a45/gi, ameixa)
    .replace(/width: 200px; height: 72px/g, 'width: 200px; min-height: 72px');
}
const VOLTA = '<a href="#" style="display: flex; align-items: center; gap: 6px; height: 44px; padding: 0 12px; border-radius: 8px; border: 1px solid #74837a; background: #fffefa; color: #202c29; text-decoration: none; font-size: 16px"><svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#202c29" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 6l-6 6 6 6"/></svg>Apuração</a>';
const caminhoDeVolta = html => html.replace(/(<h1[^>]*>Quadros<\/h1>)/, VOLTA + '$1');
module.exports = {aplicarDecisoes, arredonda, caminhoDeVolta};
