---
type: reference
title: Pranchas derivadas da Onda 3 (aprovadas pelo dono em 21/11/2026)
created: 2026-11-21
tags: [design, derivado, onda-3]
related: ['[[componentes]]', '[[referencia/README]]', '[[mudancas-de-token]]']
---

# Pranchas derivadas da Onda 3

**Derivado, aprovado pelo dono em 21/11/2026.** As 27 pranchas foram aprovadas e regeneradas com as decisões P11 e P12 (`../componentes.md`, "Decisões do dono"): grade de 4 px, 12 px nos cartões, ameixa no órgão público, altura mínima, gaveta abaixo de 1280 px, verde cheio no item ativo do escuro; depois, a barra lateral de 256 px (P15.7). Cada imagem traz, abaixo, a faixa "Derivado · aprovado pelo dono em 21/11/2026". Elas passam a valer como referência ao lado de `../referencia/`.

A especificação está em [`../componentes.md`](../componentes.md), seções [Diálogo de confirmação](../componentes.md#dialogo) e [Telas derivadas](../componentes.md#telas-derivadas).

## Como foram feitas

- `ferramentas/decisoes.cjs`: aplica as decisões do dono (grade de 4 px, raio de 12 px, ameixa, altura mínima) a toda prancha antes de renderizar, inclusive às que partem do HTML do canvas.
- `fonte/base.css`: os tokens semânticos de `interface/tokens.css`, com os valores do canvas e as propostas de `mudancas-de-token.md`. Nenhuma cor fora deles, exceto a faixa de marcação.
- `ferramentas/gerar_novas.cjs`: monta as pranchas HTML em `fonte/` e as renderiza em `telas/` pelo mesmo processo da referência (Chromium do Playwright do projeto, fontes da Mesa, escala 1×, rede bloqueada).
- O escuro das telas de desktop parte do HTML do próprio canvas (`referencia/canvas/`), trocando cada cor do claro pelo valor escuro do mesmo token.
- Os textos dos diálogos são os da Mesa de hoje (`interface/index.html:275-290`, `interface/piloto.js:143`, `interface/gerenciar.js`). Os dados são os sintéticos do canvas.

```
NODE_PATH=.ferramentas/node/node_modules node docs/design/novas/ferramentas/gerar_novas.cjs
```

## Pranchas

| Tema | Pranchas (`telas/`) | Largura |
|---|---|---|
| Diálogo simples | `dialogo-simples-claro-1440`, `-escuro-1440`, `-claro-390`, `-escuro-390` | 1440 e 390 |
| Diálogo destrutivo com o nome do item | `dialogo-destrutivo-claro-1440`, `-escuro-1440`, `-claro-390`, `-escuro-390` | 1440 e 390 |
| Diálogo com campo | `dialogo-campo-claro-1440`, `-escuro-1440`, `-claro-390`, `-escuro-390` | 1440 e 390 |
| Escuro no desktop | `conferir-achado-escuro-1440`, `visao-geral-escuro-1440`, `design-system-revisado-escuro-1440` | 1440 |
| Tablet | `conferir-achado-claro-1024`, `-escuro-1024`; `conferir-achado-gaveta-aberta-claro-1024`, `-escuro-1024`; `visao-geral-claro-1024`, `-escuro-1024` | 1024 |
| Celular | `conferir-achado-claro-390`, `-escuro-390`; `conferir-achado-original-claro-390`, `-escuro-390`; `visao-geral-claro-390`, `-escuro-390` | 390 |

Alturas: as pranchas de 1440 têm a altura das telas do canvas (900 px; o design system, 1000 px); as de tablet e celular têm a altura do conteúdo, no mínimo 768 e 844 px. A faixa de marcação soma 40 px abaixo de cada uma.
