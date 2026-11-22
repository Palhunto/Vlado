---
type: reference
title: Mudanças de token que o canvas traz
created: 2026-11-21
tags: [design, tokens, contraste, wcag]
related: ['[[design-system]]', '[[componentes]]', '[[referencia/README]]']
---

# Mudanças de token que o canvas traz

Este documento compara o canvas "Vlado — Mesa ideal" (referência exportada em `referencia/`) com `interface/tokens.css` como está na base `b3b6935`. Ele **não altera** `tokens.css`: o plano exige as capturas de regressão do QA antes de qualquer mudança visual (Onda 3, parte A). Os blocos de CSS abaixo são proposta, para a fase em que o Design aplicar as mudanças.

Onde o canvas e os tokens divergem, vale o canvas (`PLANO_LANCAMENTO.md`, "Referência visual aprovada"). Onde o próprio canvas se contradiz, a divergência está marcada e vira pergunta ao dono no fim.

## Resumo

Decisões do dono de 21/11/2026 (P11 e P12) já incorporadas; a lista completa está em `componentes.md`, "Decisões do dono". Arredondamento para a grade de 4 px (P11.8): preenchimento, intervalo e margem fora da grade sobem para o múltiplo de 4 seguinte.

| # | O quê | Hoje (`tokens.css` / CSS) | Canvas | Origem no canvas |
|---|---|---|---|---|
| 1 | Cor do foco, tema claro | `--theme-focus` → `verde-500` `#53886c` | `#8a5a12` (ocre escuro) | "Foco · novo", `Tokens.dc.html`; `:focus-visible` de todas as telas claras |
| 2 | Afastamento do anel de foco | `outline:3px`, `outline-offset:4px` (`style.css:118`) | `outline:3px`, `outline-offset:2px` | `<style>` de todas as telas |
| 3 | Borda de campo, tema escuro | `--theme-input-line` → `tinta-550` `#64786a` | `#8a9c8f` | "Borda · nova", `Tokens.dc.html`; campo do `Celular.dc.html` |
| 4 | Piso e degraus do texto | 7 degraus, 12 a 28 px (`--text-xs` 12, `--text-sm` 13) | 6 degraus: 14, 16, 18, 22, 28, 36 | "Tipografia · seis degraus, piso de 14 px" |
| 5 | Raios | controle 6, cartão 8, painel 10, pílula 999 | controle 8, cartão 12, pílula | "Espaço e raio" |
| 6 | Larguras de quebra | 19 larguras distintas nas regras | 720, 1024 e 1280 px | nota em "Espaço e raio" |
| 7 | Largura da barra lateral | `--mesa-sidebar:224px`, 245 px a partir de 1550 px e 205 px até 1190 px (`style.css:139-140`) | 256 px (o canvas desenha 232; P15.7) | `nav` de `Main` e `Inicio` |
| 8 | Contador no item da barra lateral | não existe | pílula com o número (ou "1 vence") à direita do rótulo | `Main` e `Inicio` |
| 9 | Contorno do trecho citado no PDF | `--pdf-trecho-borda` `#c478008c` (55 % de opacidade) | `#c47800` opaco, 2 px | célula "Acumulado pago", `Main` |
| 10 | Cor do órgão público no mapa | não existe | `#3d4a45` | ícone do órgão, `Mapa.dc.html` |
| 11 | Sombras | `--sombra-cartao` e `--sombra-flutuante` com alfa 0,063 | alfa 0,06, 0,08 e 0,10 | cartões de `Inicio`, `Main`, `Mapa`, `Tempo` |
| 12 | Família da fonte | 64 literais de `font-family` (UX-12) | Source Serif 4 (títulos, leitura) e Source Sans 3 (interface) | todas as telas |

Os 1 a 6 são os que o plano lista. Os 7 a 12 o canvas também traz e o plano não listou; ficam aqui para não sumirem.

Nenhuma outra cor muda. As 12 amostras do tema claro e as 6 do escuro em `Tokens.dc.html` conferem com os primitivos atuais, com exceção do foco (1) e da borda (3).

## 1. Foco no tema claro: `#8a5a12`

O foco atual, `#53886c`, dá de 3,33:1 a 4,08:1 sobre os fundos claros e tem o mesmo matiz do item selecionado (UX-02). O ocre escuro dá de 5,01:1 a 5,86:1 sobre os mesmos fundos e se separa do verde pelo matiz e pela luminosidade. No escuro, o foco já é ocre (`#e6bc7a`); os dois temas passam a ter o foco da mesma família.

```css
/* proposta: primitivo novo e semântico do claro */
--vlado-ocre-700:#8a5a12;
:root{ --theme-focus:var(--vlado-ocre-700); }   /* escuro continua --vlado-ocre-300 */
```

Ao lado do botão principal o anel só funciona com afastamento: ocre sobre verde dá 1,62:1 (C36 na tabela). Com `outline-offset:2px` o anel encosta no fundo da página, não no botão, e o par que conta é ocre sobre fundo (5,42:1). Por isso o item 2 não é opcional.

## 2. Anel de foco: 3 px com afastamento de 2 px

O canvas desenha `outline:3px solid <foco>; outline-offset:2px` em todas as telas. Hoje a regra geral é `outline-offset:3px` (`style.css:5`), sobrescrita por `4px` (`style.css:118`).

```css
/* proposta */
--foco-largura:3px; --foco-afastamento:2px;
:focus-visible{ outline:var(--foco-largura) solid var(--theme-focus); outline-offset:var(--foco-afastamento); }
```

Contêiner com corte (`overflow:hidden`), como a lista de achados e a barra do PDF (UX-01): o canvas não desenha esse caso. A proposta é o anel interno, `outline-offset:calc(-1 * var(--foco-largura) - 2px)`, que deixa 2 px do fundo do próprio elemento entre a borda e o anel. Num botão verde isso pintaria ocre sobre verde (1,62:1); por isso o anel interno só vale para elementos de fundo claro (linha de lista, cartão, página do PDF), nunca para botão principal. Esse caso precisa de captura e entra na conferência do Frontend.

## 3. Borda de campo no escuro: `#8a9c8f`

Hoje `#64786a` dá 3,19:1 sobre a superfície e cai para 2,80:1 sobre a área de leitura (E36) e 2,47:1 sobre o verde suave `#2c3c2e` (E52), abaixo dos 3:1 do WCAG 1.4.11 (UX-17). O valor do canvas dá 4,03:1 no pior fundo (verde suave, E53) e 5,21:1 sobre a superfície (E37). A nota do canvas ("sobe de 2,5:1 para mais de 4:1") confere com essas medidas no pior caso.

```css
/* proposta */
--vlado-tinta-400:#8a9c8f;
:root[data-theme=dark]{ --theme-input-line:var(--vlado-tinta-400); }
```

Efeito colateral a conferir: `--tabela-pendente` aponta para `--theme-input-line` e fica mais clara no escuro junto. Continua acima de 3:1.

## 4. Texto: piso de 14 px e seis degraus

O canvas declara seis degraus: 36 (título da apuração), 28 (título de área), 22 (título de seção), 18 (resposta da IA e leitura, até 70 caracteres por linha), 16 (interface, botões e campos; campo nunca abaixo de 16) e 14 (apoio, fonte citada e rótulos; "substitui 12 e 13 px").

Hoje: `--text-xs` 12 (97 ocorrências de `var(--text-xs)` em `style.css` e 4 em `caderno.css`) e `--text-sm` 13 (64 em `style.css`, 1 em `caderno.css` e 2 em `entrar.css`) estão abaixo do piso; não existe 36 na escala de interface (`--text-brand` 36 é a marca).

```css
/* proposta: os nomes que já existem ficam, para não reescrever regra à toa */
--text-md:14px; --text-base:16px; --text-lg:18px; --text-xl:22px; --text-2xl:28px;
--text-3xl:36px;                       /* novo: título da apuração */
--text-xs:var(--text-md); --text-sm:var(--text-md);   /* só durante a migração; depois saem */
```

O canvas usa também tamanhos fora dos seis degraus. Decisão do dono (P11.2): tokens de exceção só para 24, 32 e 40 px:

| Tamanho | Onde | Proposta de nome |
|---|---|---|
| 24 px, serifa | frase do cartão "Seu próximo passo" (`Inicio`) | `--text-destaque` |
| 32 px, serifa 600 | número dos cartões de contagem (`Inicio`); marca "Vlado." na barra lateral | `--text-numero` |
| 40 px, serifa 600 | marca "Vlado." no Entrar | `--text-marca` (hoje `--text-brand` 36) |
| 20 px | sinais "−" e "+" dos botões de zoom (`Main`) | some quando os sinais virarem ícone SVG |
| 15 px, serifa | texto da página do documento no leitor (`Main`) | não é interface: é o documento simulado; o leitor real mostra o PDF |

Entrelinha: o canvas usa 1,5 no corpo (igual à regra de `body` que vale hoje, `font:var(--text-base)/1.5` em `style.css:118`), 1,55 nos parágrafos de resposta no celular, 1,2 no título de área e 1,15 no título da apuração.

O teste `testes/estilo_tokens.cjs:136-142` exige de 6 a 7 degraus e piso de 12 px; precisa subir para 14 px quando a mudança for aplicada. O arquivo é do QA.

## 5. Raios: 8, 12 e pílula

```css
/* proposta */
--raio-controle:var(--vlado-raio-3);  /* 8 px: botão, campo, item de navegação, aba */
--raio-cartao:var(--vlado-raio-5);    /* 12 px: cartão, painel, bloco de aviso */
--raio-pilula:var(--vlado-raio-pilula);
/* --raio-painel (10 px) sai; --quadro-raio passa a apontar para --raio-cartao */
```

Decisão do dono (P11.3): 12 px em todos os cartões e 4 px só na folha e no topo das barras (`--raio-folha:4px`, novo). Registro da divergência que levou à pergunta: a tela "Conferir achado" (`Main.dc.html`) desenha os cartões de achado, a caixa "Sua pergunta" e o cartão da cota com 10 px, e "Visão geral" desenha o cartão da cota com 10 px, enquanto o design system revisado e as demais telas usam 12 px. A especificação segue os 12 px declarados ("Três raios no lugar de doze") e leva a diferença ao dono (pergunta 3). Outro raio que o canvas usa: 4 px na folha do documento e no topo das barras do gráfico (pergunta 3).

## 6. Larguras de quebra: 720, 1024 e 1280 px

Hoje há 19 larguras distintas nas regras de `interface/*.css` (360, 380, 480, 600, 700, 720, 721, 760, 900, 950, 1050, 1051, 1100, 1190, 1200, 1279, 1439, 1450 e 1550 px), confirmando UX-12. O canvas fixa três.

Variável CSS não funciona dentro de `@media`, então as três larguras não viram `var()`. Proposta: ficam documentadas aqui e em `componentes.md`, e um teste do QA conta as larguras distintas nas regras (no máximo estas três, em `max-width` de 719, 1023 e 1279 px ou `min-width` de 720, 1024 e 1280 px).

| Faixa | Nome | O que o plano já define |
|---|---|---|
| até 719 px | celular | uma coluna; barra lateral vira gaveta; campo de 16 px; alvo de 44 px |
| 720 a 1023 px | tablet | barra lateral ainda em gaveta (UX-11: "Gaveta até 1024 px") |
| 1024 a 1279 px | desktop compacto | barra lateral em gaveta (decisão do dono, P12.1: gaveta abaixo de 1280 px) |
| 1280 px ou mais | desktop | como as telas finais de 1440 px |

O canvas só desenha 390 e 1440 px. O comportamento nas faixas do meio está na lista do que o Design ainda desenha.

## 7. Barra lateral com 256 px

**Decisões do dono:** sem ícones nos itens (P11.6); gaveta abaixo de 1280 px (P12.1); **256 px no lugar dos 232 do canvas (P15.7, 21/11/2026)**, mudança no canvas aprovado autorizada pelo dono (regra 6 do contrato).

`--mesa-sidebar` passa de 224 px para 256 px. O canvas desenha o `nav` de `Main` e `Inicio` com 232 px. As duas variações por largura de tela (245 px a partir de 1550 px e 205 px até 1190 px, `style.css:139-140`) saem: há uma largura só, e abaixo de 1280 px a barra vira gaveta com a mesma largura (item 6, P12.1).

**Por que 256 e não 232.** Medido com as fontes da Mesa (Source Sans 3) nas pranchas: com 232 px, o item tem 175 px úteis (232 − 2 × 16 da barra − 1 da borda − 2 × 12 do item). O item ativo "Pedidos e prazos" com a pílula "1 vence" precisa de 188 px: rótulo em 600 com 115, intervalo de 12 e pílula com 61 (45 de texto e 2 × 8 de preenchimento). O rótulo e a pílula quebravam em duas linhas, e o dono pôs como condição da P15.7 que não quebrem. Nenhum ajuste de espaçamento dentro da grade de 4 px fechava os 13 px que faltavam. Com 256 px sobram 199: o item cabe com 11 px de folga e, pelo mesmo motivo, "Cota do mês R$ 18,40 de R$ 50" (precisa de 218 px na caixa, com 199 disponíveis em 232) e "Repórter · Redação Serena" no perfil (213 px) deixam de quebrar linha. A P11.5 (altura mínima) continua valendo para nomes mais longos. O conteúdo perde 24 px: em 1280 px, a área ao lado da barra fica com 1024 px.

Regra que acompanha: rótulo e contador do item não quebram linha (`white-space: nowrap`, contador `flex: none`). Ao gravar no `tokens.css`, o Frontend confere que nenhum item da barra transborda com os rótulos reais.

**Quando entra no código:** fase 2 dos tokens, com os demais valores do canvas (ordem de aplicação, passo 2). Na fase 1, a do Lume (só adições com os valores de hoje), a largura não muda.

## 8. Contador no item da barra lateral

**Decisão do dono (P12.2):** no escuro, o item ativo também é verde cheio (`#a8c79d`) com texto `#172315`; o padrão de hoje (`style.css:174`) sai.

A cor do item ativo não muda no claro: `.areas>a[aria-current=page]` já tem fundo `--green` e peso 600 (`style.css:118`); o texto usa `--white` (`#fffefa`, 9,52:1), e o canvas usa branco puro (`#ffffff`, 9,61:1), diferença que não se vê. No escuro, hoje o item ativo tem fundo `--theme-active`, texto verde e uma barra interna de 3 px à esquerda (`style.css:174`); o canvas não desenha a barra lateral no escuro, então isso fica como está.

O que o canvas acrescenta é o contador à direita do rótulo, em 14 px, nestas formas:

| Situação | Aparência | Onde |
|---|---|---|
| item comum com quantidade | texto secundário, sem fundo ("12") | Documentos |
| item comum com quantidade, na página atual | pílula branca, texto verde 600 ("12"), como a de Conferir (P16.4) | Documentos ativo (prancha de documentos) |
| item com pendência, fora da página atual | pílula verde cheia, texto branco 600 ("4") | Conferir em `Inicio` |
| item com pendência, na página atual | pílula branca, texto verde 600 ("4") | Conferir em `Main` |
| prazo vencendo | texto de aviso 600, sem fundo ("1 vence") | Pedidos e prazos |
| prazo vencendo, na página atual | pílula clara com texto de aviso 600 (claro 6,59:1, C65; escuro `#e6bc7a` sobre `#172315`, 9,19:1, E58), inteira e na mesma linha do rótulo (P15.7) | Pedidos e prazos ativo (prancha dos quadros) |

Rótulo e contador não quebram linha (`white-space: nowrap`; contador com `flex: none`). O item mais longo, "Pedidos e prazos" ativo com "1 vence", ocupa 188 px e cabe nos 199 úteis da barra de 256 px (item 7).

```css
/* proposta de tokens de componente */
--nav-contador-fundo:var(--theme-accent); --nav-contador-texto:var(--theme-on-primary);
--nav-contador-ativo-fundo:var(--vlado-branco); --nav-contador-ativo-texto:var(--theme-accent);
--aba-ativa-fundo:var(--theme-soft); --aba-ativa-texto:var(--theme-accent);
```

As abas dos quadros (Hipóteses, Linha do tempo, Mapa de relações, Tabelas) usam o verde suave com texto verde (8,14:1), não o verde cheio.

## 9. Trecho citado no PDF: contorno opaco

O canvas pinta a célula citada com fundo `#ffe9a8` e contorno de 2 px `#c47800`. Os tokens atuais usam fundo `#ffc4006b` e contorno `#c478008c`, translúcidos.

- **Fundo:** fica translúcido. O leitor real pinta o realce por cima da página renderizada do PDF; um fundo opaco esconderia o texto do documento. Sobre a página branca, `#ffc4006b` compõe `#ffe694` (luminosidade L\* 91,7 contra 92,7 do `#ffe9a8` do canvas), e o texto sobre ele dá 11,69:1. É exceção registrada pelo Design (regra 5 do contrato): mesma aparência, por razão técnica.
- **Contorno:** passa a opaco, como no canvas. Translúcido, ele compõe `#dfb573` sobre o branco (1,91:1); opaco, dá 3,48:1.

```css
/* proposta */
--vlado-pdf-trecho-borda:#c47800;
```

## 10. Órgão público: terceira cor do mapa

**Decisão do dono (P11.4): opção (b), a ameixa validada** — `--vlado-ameixa-600:#b0508a` (claro) e `--vlado-ameixa-400:#d46a9c` (escuro), com `--theme-entidade-orgao` e `--mapa-orgao` apontando para elas. O texto abaixo é o registro da análise.

O mapa do canvas tem três tipos de entidade: pessoa (círculo esmeralda `#1d8058`), empresa (quadrado de canto arredondado anil `#5b5fb8`) e órgão público (quadrado de canto vivo `#3d4a45`). A terceira cor não existe nos tokens e não tem par no escuro.

A skill `dataviz` foi rodada sobre o trio, contra o fundo claro `#f6f5f0`:

```
node scripts/validate_palette.js "#1d8058,#5b5fb8,#3d4a45" --mode light
[FAIL] Lightness band   #3d4a45 fora da faixa (L 0,396)
[FAIL] Chroma floor     #3d4a45 abaixo do piso (croma 0,019: lê como cinza)
[PASS] CVD separation   pior par #5b5fb8↔#1d8058 ΔE 17,0
[PASS] Normal-vision    pior par #3d4a45↔#5b5fb8 ΔE 19,5
[PASS] Contrast         os 3 ≥ 3:1
```

O `#3d4a45` é um cinza-esverdeado, não uma cor categórica. O plano diz que tipo novo de entidade "pede cor categórica validada pela skill `dataviz`". O mapa não depende só da cor (forma, ícone e rótulo distinguem os três tipos), mas a regra do plano não fica cumprida. Duas saídas, para o dono decidir (pergunta 4):

- **(a) manter `#3d4a45`** como "neutro" declarado, apoiado na forma e no ícone; precisa de par escuro (proposta `#a8b3a9`, o secundário do escuro, que dá 6,97:1 sobre a superfície escura);
- **(b) trocar por uma cor categórica validada.** Encontrada uma que passa nas cinco checagens nos dois temas: ameixa, claro `#b0508a` (ΔE normal 16,0; daltonismo 7,9, no limite legal com codificação secundária, que o mapa tem) e escuro `#d46a9c` (passa sobre `#171d1a` e `#202823`). É mudança de cor numa tela aprovada, então só com aval.

Os ícones brancos sobre as cores do mapa passam no claro. No escuro, branco sobre a esmeralda `#3fa877` dá 2,97:1 (E44); a especificação usa traço escuro (`--theme-on-primary`, `#172315`) nos ícones do escuro, que dá 5,50:1 e 5,12:1.

## 11. Sombras

| Uso no canvas | Valor | Token hoje | Proposta |
|---|---|---|---|
| cartão "Seu próximo passo", formulário do Entrar | `0 1px 2px rgba(23,63,41,.06)` | `--sombra-cartao` (alfa 0,063) | sem mudança |
| folha do documento | `0 1px 2px rgba(23,63,41,.08)` | — | `--sombra-folha` |
| achado selecionado, evento selecionado | `0 4px 18px rgba(23,63,41,.08)` | `--sombra-flutuante` (alfa 0,063) | alfa 0,08: primitivo `--vlado-sombra-verde-media:#173f2914` |
| nó selecionado no mapa | `0 4px 18px rgba(23,63,41,.10)` | — | `--sombra-no-selecionado`, primitivo `#173f291a` |
| diálogo e gaveta (pranchas derivadas da fase 3, sem desenho no canvas) | `0 12px 40px rgba(23,63,41,.18)`; escuro `#00000099` | — | `--sombra-dialogo` |

No escuro as sombras continuam as da noite (`--vlado-sombra-noite*`); o canvas não desenha sombra no escuro.

## 12. Famílias de fonte

```css
/* proposta */
--fonte-titulo:"Source Serif 4",Georgia,serif;      /* títulos, marca, resposta da IA, citação, números */
--fonte-interface:"Source Sans 3",system-ui,sans-serif;  /* todo o resto */
```

Sinais dos selos e marcas de estado. A tabela `cmap` das fontes da Mesa (lida direto dos arquivos) mostra:

| Sinal | Onde no canvas | Source Sans 3 | Source Serif 4 |
|---|---|---|---|
| ✓ U+2713 | selo "Conferido", W02, W04 | tem | tem |
| ○ U+25CB | selo "A conferir", W02, W04, W06 | tem | não tem |
| ✕ U+2715 | selo "Sem suporte", erros de W11 | **não tem** | **não tem** |
| ✎ U+270E | célula corrigida (W06) | **não tem** | **não tem** |
| ◐ U+25D0 | leitura por OCR (W02), etapa em andamento (W03), convite pendente (W09) | **não tem** | **não tem** |
| − U+2212, … U+2026, ▾ U+25BE | comparador, reticências, seletores | tem | ▾ não tem |

Consequências: (a) na referência exportada, ✕, ✎ e ◐ foram desenhados por uma fonte do sistema (o Chromium no Windows), então o desenho desses três depende do aparelho; (b) o subconjunto latino em WOFF2 (UX-04) precisa incluir U+2212, U+2026, U+25BE, U+25CB e U+2713, ou esses sinais também passam a depender do sistema. Proposta: incluir esses cinco no subconjunto e trocar ✕, ✎ e ◐ por ícones SVG do conjunto do Vlado (parte E), com o mesmo tamanho do texto: `icones/sinal-sem-suporte.svg`, `icones/sinal-corrigido.svg` e `icones/sinal-parcial.svg`, derivados aprovados pelo dono em 21/11/2026 (`componentes.md`, "Conjunto de ícones do Vlado"). Até lá, a conferência de tela aceita diferença de desenho nesses três sinais, nunca a falta deles.

Pesos usados no canvas: 400 e 600 nas duas famílias; 700 no sinal "?" da lacuna e nos `<strong>`/`<b>` (valores destacados na resposta, nome do nó no mapa). As fontes continuam servidas pela Mesa, em WOFF2 com subconjunto latino (UX-04), como o próprio canvas anota.

## Tokens da parte A (aprovados pelo Design em 21/11/2026)

Pedido do Lume (Frontend) para a Onda 3, parte A: só adições em `interface/tokens.css`, na camada dos nomes curtos (a mesma de `--text-*` e `--raio-*`), com os valores de hoje, para trocar literais sem mudar nenhum pixel (conferido pelo comparar da Sonda). Quem grava é o Lume, na branch dele, no mesmo commit da troca; o Design aprova os nomes e a escala. Nomes aprovados:

| Grupo | Token | Valor de hoje |
|---|---|---|
| Fontes | `--fonte-titulo` | `"Source Serif 4", Georgia, serif` |
| | `--fonte-interface` | `"Source Sans 3", "Segoe UI", Arial, sans-serif` |
| | `--fonte-mono` | `monospace` |
| Foco | `--foco-largura` | `3px` |
| | `--foco-afastamento` | `4px` (o efetivo de hoje; os 2 px do canvas entram na fase 2, item 2) |
| Movimento | `--duracao-rapida`, `--duracao-media`, `--duracao-lenta` | `.15s`, `.2s`, `.25s` |
| | `--curva-padrao`, `--curva-saida` | `ease`, `ease-out` |
| Camadas | `--camada-base`, `--camada-acima`, `--camada-fixo`, `--camada-barra`, `--camada-barra-alta`, `--camada-gaveta`, `--camada-sobreposicao`, `--camada-sobreposicao-alta`, `--camada-modal` | 0, 1, 10, 20, 25, 30, 50, 55, 60 |
| | `--camada-caderno-1`, `--camada-caderno-2` | 6, 7 (provisórios; a escala de camadas fecha na fase 2) |

Ficam para a fase 2, com os valores do canvas: `--text-3xl`, `--text-destaque`, `--text-numero`, `--text-marca`, `--raio-folha`, as sombras novas (`--sombra-folha`, `--sombra-dialogo`, `--sombra-no-selecionado`) e `--nav-*` / `--aba-*`.

## Contraste medido

Razão de contraste WCAG 2.x (luminância relativa), calculada por `referencia/ferramentas/contraste.py` com as cores exatas do canvas. Mínimos: 4,5:1 para texto (WCAG 1.4.3) e 3:1 para borda de controle, anel de foco e marca gráfica que carrega informação (WCAG 1.4.11). "Passa" quer dizer acima do mínimo do par; os que não passam estão explicados logo depois da tabela, e nenhum deles é dado como aprovado.

### Tema claro

| Par | Uso | Cores (frente / fundo) | Razão | Mínimo | Resultado |
|---|---|---|---|---|---|
| C01 | texto / fundo da página | `#202c29` / `#f6f5f0` | 13.23:1 | 4.5:1 | passa |
| C02 | texto / superfície (cartões, cabeçalho) | `#202c29` / `#fffefa` | 14.31:1 | 4.5:1 | passa |
| C03 | texto / barra lateral e painel do original | `#202c29` / `#efefe8` | 12.51:1 | 4.5:1 | passa |
| C04 | texto / caixa "Sua pergunta" (leitura) | `#202c29` / `#f1f2e9` | 12.81:1 | 4.5:1 | passa |
| C05 | texto / fundo de aviso (lacuna, cartão LAI) | `#202c29` / `#f7ecdf` | 12.39:1 | 4.5:1 | passa |
| C06 | texto / verde suave (aviso de teste no Entrar) | `#202c29` / `#e8eee6` | 12.25:1 | 4.5:1 | passa |
| C07 | texto / realce do trecho citado no original | `#202c29` / `#ffe9a8` | 12.02:1 | 4.5:1 | passa |
| C08 | secundário / fundo | `#5f6a63` / `#f6f5f0` | 5.16:1 | 4.5:1 | passa |
| C09 | secundário / superfície | `#5f6a63` / `#fffefa` | 5.58:1 | 4.5:1 | passa |
| C10 | secundário / barra lateral; botão indisponível | `#5f6a63` / `#efefe8` | 4.88:1 | 4.5:1 | passa |
| C11 | secundário / leitura ("Sua pergunta") | `#5f6a63` / `#f1f2e9` | 4.99:1 | 4.5:1 | passa |
| C12 | secundário / item ativo (tema atual) | `#5f6a63` / `#e4e9dc` | 4.56:1 | 4.5:1 | passa |
| C13 | secundário / verde suave | `#5f6a63` / `#e8eee6` | 4.78:1 | 4.5:1 | passa |
| C14 | verde / superfície (links, "Conferido no original") | `#1e4d3e` / `#fffefa` | 9.52:1 | 4.5:1 | passa |
| C15 | verde / fundo (links) | `#1e4d3e` / `#f6f5f0` | 8.80:1 | 4.5:1 | passa |
| C16 | verde / verde suave (selo "Conferido", aba ativa, selo de fonte) | `#1e4d3e` / `#e8eee6` | 8.14:1 | 4.5:1 | passa |
| C17 | branco / verde (botão principal, item ativo da barra) | `#ffffff` / `#1e4d3e` | 9.61:1 | 4.5:1 | passa |
| C18 | branco / verde ao passar o mouse | `#ffffff` / `#2e604c` | 7.26:1 | 4.5:1 | passa |
| C19 | verde / branco (contador no item ativo) | `#1e4d3e` / `#ffffff` | 9.61:1 | 4.5:1 | passa |
| C20 | aviso / fundo de aviso (lacuna, "Lida por OCR") | `#8e4b28` / `#f7ecdf` | 5.65:1 | 4.5:1 | passa |
| C21 | aviso / barra lateral ("1 vence") | `#8e4b28` / `#efefe8` | 5.70:1 | 4.5:1 | passa |
| C22 | aviso / superfície (nota de OCR, "1 sem evidência") | `#8e4b28` / `#fffefa` | 6.53:1 | 4.5:1 | passa |
| C23 | aviso / fundo ("dia não informado") | `#8e4b28` / `#f6f5f0` | 6.04:1 | 4.5:1 | passa |
| C24 | branco / aviso (sinal "?" da lacuna) | `#ffffff` / `#8e4b28` | 6.59:1 | 4.5:1 | passa |
| C25 | erro / superfície (botão destrutivo, erro de campo) | `#87342c` / `#fffefa` | 8.14:1 | 4.5:1 | passa |
| C26 | erro / fundo de erro (selo "Sem suporte") | `#87342c` / `#f8e9e5` | 6.95:1 | 4.5:1 | passa |
| C30 | foco novo / fundo | `#8a5a12` / `#f6f5f0` | 5.42:1 | 3:1 | passa |
| C31 | foco novo / superfície | `#8a5a12` / `#fffefa` | 5.86:1 | 3:1 | passa |
| C32 | foco novo / barra lateral | `#8a5a12` / `#efefe8` | 5.12:1 | 3:1 | passa |
| C33 | foco novo / leitura | `#8a5a12` / `#f1f2e9` | 5.24:1 | 3:1 | passa |
| C34 | foco novo / verde suave | `#8a5a12` / `#e8eee6` | 5.01:1 | 3:1 | passa |
| C35 | foco novo / fundo de aviso | `#8a5a12` / `#f7ecdf` | 5.07:1 | 3:1 | passa |
| C36 | foco novo / verde (anel junto ao botão principal) | `#8a5a12` / `#1e4d3e` | 1.62:1 | 3:1 | **não passa** |
| C37 | foco atual / fundo (comparação) | `#53886c` / `#f6f5f0` | 3.77:1 | 3:1 | passa |
| C38 | foco atual / superfície (comparação) | `#53886c` / `#fffefa` | 4.08:1 | 3:1 | passa |
| C39 | foco atual / barra lateral (comparação) | `#53886c` / `#efefe8` | 3.56:1 | 3:1 | passa |
| C40 | foco atual / item ativo (comparação) | `#53886c` / `#e4e9dc` | 3.33:1 | 3:1 | passa |
| C41 | borda de campo / superfície | `#74837a` / `#fffefa` | 3.95:1 | 3:1 | passa |
| C42 | borda de campo / fundo | `#74837a` / `#f6f5f0` | 3.65:1 | 3:1 | passa |
| C43 | borda de botão secundário / painel do original | `#74837a` / `#efefe8` | 3.45:1 | 3:1 | passa |
| C44 | borda de campo com erro (2 px) / superfície | `#87342c` / `#fffefa` | 8.14:1 | 3:1 | passa |
| C45 | borda do botão destrutivo / superfície | `#b06a5c` / `#fffefa` | 4.11:1 | 3:1 | passa |
| C46 | pessoa / superfície | `#1d8058` / `#fffefa` | 4.86:1 | 3:1 | passa |
| C47 | empresa / superfície | `#5b5fb8` / `#fffefa` | 5.51:1 | 3:1 | passa |
| C48 | órgão público / superfície | `#3d4a45` / `#fffefa` | 9.19:1 | 3:1 | passa |
| C49 | ícone branco / pessoa | `#ffffff` / `#1d8058` | 4.91:1 | 3:1 | passa |
| C50 | ícone branco / empresa | `#ffffff` / `#5b5fb8` | 5.56:1 | 3:1 | passa |
| C51 | ícone branco / órgão público | `#ffffff` / `#3d4a45` | 9.28:1 | 3:1 | passa |
| C52 | ligação do mapa / fundo | `#5f6a63` / `#f6f5f0` | 5.16:1 | 3:1 | passa |
| C53 | ligação selecionada (4 px), marco cheio / fundo | `#1e4d3e` / `#f6f5f0` | 8.80:1 | 3:1 | passa |
| C54 | ligação a confirmar e intervalo sem documento, tracejados / fundo | `#8e4b28` / `#f6f5f0` | 6.04:1 | 3:1 | passa |
| C55 | trilho da linha do tempo; barra do gráfico / fundo | `#7f9685` / `#f6f5f0` | 2.91:1 | 3:1 | **não passa** |
| C56 | barra de progresso / trilha | `#1e4d3e` / `#dddfd6` | 7.14:1 | 3:1 | passa |
| C57 | trilha da barra de progresso / superfície | `#dddfd6` / `#fffefa` | 1.33:1 | 3:1 | **não passa** |
| C58 | contorno do realce / realce | `#c47800` / `#ffe9a8` | 2.90:1 | 3:1 | **não passa** |
| C59 | contorno do realce / página branca | `#c47800` / `#ffffff` | 3.48:1 | 3:1 | passa |
| C60 | borda de cartão / fundo | `#dddfd6` / `#f6f5f0` | 1.23:1 | 3:1 | **não passa** |
| C61 | borda de aviso / fundo de aviso | `#c58b55` / `#f7ecdf` | 2.50:1 | 3:1 | **não passa** |
| C62 | borda do selo "Conferido" / verde suave | `#7f9685` / `#e8eee6` | 2.70:1 | 3:1 | **não passa** |
| C63 | proposta "ameixa" para órgão público / superfície | `#b0508a` / `#fffefa` | 4.77:1 | 3:1 | passa |
| C64 | ícone branco / proposta "ameixa" | `#ffffff` / `#b0508a` | 4.82:1 | 3:1 | passa |
| C65 | prazo vencendo no item ativo da barra (pílula clara) | `#8e4b28` / `#ffffff` | 6.59:1 | 4.5:1 | passa |

### Tema escuro

| Par | Uso | Cores (frente / fundo) | Razão | Mínimo | Resultado |
|---|---|---|---|---|---|
| E01 | texto / fundo | `#eae9df` / `#171d1a` | 14.03:1 | 4.5:1 | passa |
| E02 | texto / superfície (rodapé do celular) | `#eae9df` / `#202823` | 12.40:1 | 4.5:1 | passa |
| E03 | texto / barra lateral e cabeçalho do celular | `#eae9df` / `#121714` | 14.87:1 | 4.5:1 | passa |
| E04 | texto / leitura | `#eae9df` / `#28322c` | 10.88:1 | 4.5:1 | passa |
| E05 | texto / verde suave (balão da pergunta) | `#eae9df` / `#2c3c2e` | 9.60:1 | 4.5:1 | passa |
| E06 | texto / fundo de aviso (lacuna) | `#eae9df` / `#372e21` | 10.93:1 | 4.5:1 | passa |
| E07 | secundário / fundo | `#a8b3a9` / `#171d1a` | 7.89:1 | 4.5:1 | passa |
| E08 | secundário / superfície (rodapé) | `#a8b3a9` / `#202823` | 6.97:1 | 4.5:1 | passa |
| E09 | secundário / cabeçalho | `#a8b3a9` / `#121714` | 8.36:1 | 4.5:1 | passa |
| E10 | secundário / verde suave | `#a8b3a9` / `#2c3c2e` | 5.40:1 | 4.5:1 | passa |
| E11 | verde / fundo (links) | `#a8c79d` / `#171d1a` | 9.23:1 | 4.5:1 | passa |
| E12 | verde / verde suave (selo de fonte) | `#a8c79d` / `#2c3c2e` | 6.31:1 | 4.5:1 | passa |
| E13 | verde / superfície | `#a8c79d` / `#202823` | 8.15:1 | 4.5:1 | passa |
| E14 | texto sobre verde (botão principal) | `#172315` / `#a8c79d` | 8.79:1 | 4.5:1 | passa |
| E15 | texto sobre verde ao passar o mouse | `#172315` / `#bad8af` | 10.51:1 | 4.5:1 | passa |
| E16 | aviso / fundo de aviso ("Lacuna.") | `#e6bc7a` / `#372e21` | 7.52:1 | 4.5:1 | passa |
| E17 | aviso / fundo | `#e6bc7a` / `#171d1a` | 9.65:1 | 4.5:1 | passa |
| E18 | sinal "?" sobre ocre | `#172315` / `#e6bc7a` | 9.19:1 | 4.5:1 | passa |
| E19 | erro / superfície | `#e7a097` / `#202823` | 7.11:1 | 4.5:1 | passa |
| E20 | erro / fundo de erro | `#e7a097` / `#382725` | 6.65:1 | 4.5:1 | passa |
| E30 | foco / fundo | `#e6bc7a` / `#171d1a` | 9.65:1 | 3:1 | passa |
| E31 | foco / superfície | `#e6bc7a` / `#202823` | 8.52:1 | 3:1 | passa |
| E32 | foco / cabeçalho e barra lateral | `#e6bc7a` / `#121714` | 10.22:1 | 3:1 | passa |
| E33 | foco / verde suave | `#e6bc7a` / `#2c3c2e` | 6.60:1 | 3:1 | passa |
| E34 | borda de campo atual / superfície | `#64786a` / `#202823` | 3.19:1 | 3:1 | passa |
| E35 | borda de campo atual / fundo | `#64786a` / `#171d1a` | 3.62:1 | 3:1 | passa |
| E36 | borda de campo atual / leitura | `#64786a` / `#28322c` | 2.80:1 | 3:1 | **não passa** |
| E37 | borda de campo nova / superfície (lado de fora, rodapé) | `#8a9c8f` / `#202823` | 5.21:1 | 3:1 | passa |
| E38 | borda de campo nova / fundo (lado de dentro do campo) | `#8a9c8f` / `#171d1a` | 5.89:1 | 3:1 | passa |
| E39 | borda de campo nova / barra lateral | `#8a9c8f` / `#121714` | 6.24:1 | 3:1 | passa |
| E40 | borda de campo nova / leitura | `#8a9c8f` / `#28322c` | 4.57:1 | 3:1 | passa |
| E52 | borda de campo atual / verde suave (item ativo) | `#64786a` / `#2c3c2e` | 2.47:1 | 3:1 | **não passa** |
| E53 | borda de campo nova / verde suave (item ativo) | `#8a9c8f` / `#2c3c2e` | 4.03:1 | 3:1 | passa |
| E54 | ícone escuro / órgão público no escuro, opção (a) | `#172315` / `#a8b3a9` | 7.52:1 | 3:1 | passa |
| E55 | borda do botão destrutivo no escuro / superfície (fase 3) | `#a76e66` / `#202823` | 3.65:1 | 3:1 | passa |
| E56 | barra de progresso no escuro / trilha (fase 3) | `#a8c79d` / `#3c4940` | 5.10:1 | 3:1 | passa |
| E57 | contador no item ativo da barra, escuro (fase 3) | `#a8c79d` / `#172315` | 8.79:1 | 4.5:1 | passa |
| E58 | prazo vencendo no item ativo da barra, escuro (pílula) | `#e6bc7a` / `#172315` | 9.19:1 | 4.5:1 | passa |
| E41 | borda de aviso / fundo de aviso | `#aa8754` / `#372e21` | 4.00:1 | 3:1 | passa |
| E42 | pessoa / superfície | `#3fa877` / `#202823` | 5.10:1 | 3:1 | passa |
| E43 | empresa / superfície | `#8487e6` / `#202823` | 4.74:1 | 3:1 | passa |
| E44 | ícone branco / pessoa | `#ffffff` / `#3fa877` | 2.97:1 | 3:1 | **não passa** |
| E45 | ícone branco / empresa | `#ffffff` / `#8487e6` | 3.19:1 | 3:1 | passa |
| E46 | ícone escuro / pessoa | `#172315` / `#3fa877` | 5.50:1 | 3:1 | passa |
| E47 | ícone escuro / empresa | `#172315` / `#8487e6` | 5.12:1 | 3:1 | passa |
| E48 | ligação do mapa / fundo do mapa | `#a8b3a9` / `#28322c` | 6.12:1 | 3:1 | passa |
| E49 | proposta "ameixa" escura / superfície | `#d46a9c` / `#202823` | 4.56:1 | 3:1 | passa |
| E50 | ícone escuro / proposta "ameixa" escura | `#172315` / `#d46a9c` | 4.92:1 | 3:1 | passa |
| E51 | divisória / fundo | `#3c4940` / `#171d1a` | 1.81:1 | 3:1 | **não passa** |

### Os que não passam, um a um

| Par | Razão | Situação |
|---|---|---|
| C36 foco ocre sobre o verde do botão | 1,62:1 | Não ocorre com o afastamento de 2 px do canvas: o anel encosta no fundo (C30, 5,42:1). Vira regra: anel interno nunca em botão principal (item 2). |
| C55 trilho da linha do tempo e barras do gráfico (`#7f9685`) sobre o fundo | 2,91:1 | O trilho liga marcos e não carrega informação sozinho; cada marco é verde cheio (8,80:1) ou vazado com borda verde. As barras do gráfico têm o valor escrito em cima de cada uma ("1,2", "2,65", "3,9"), então a informação não depende da barra. **Ressalva**, não bloqueio. Sobre a superfície (`#fffefa`) o mesmo verde dá 3,15:1. |
| C57 trilha da barra de progresso sobre a superfície | 1,33:1 | A informação é o preenchimento contra a trilha (C56, 7,14:1) e o texto "Lendo a página 2 de 5". Não exigido. |
| C58 contorno do realce sobre o próprio realce | 2,90:1 | O realce é reconhecido pelo fundo amarelo e pelo contorno contra a página branca (C59, 3,48:1). Ressalva. |
| C60 borda de cartão sobre o fundo | 1,23:1 | Cartão não é controle: é reconhecido pelo texto e pela superfície. Onde o cartão é botão (achado "a conferir"), o alvo é identificado pelo texto, que passa. Não exigido. |
| C61 borda de aviso sobre o fundo de aviso | 2,50:1 | O bloco de aviso é reconhecido pelo fundo, pelo sinal "?" e pelo texto "Lacuna". Não exigido. |
| C62 borda do selo "Conferido" sobre o verde suave | 2,70:1 | Selo não é controle e tem sinal "✓" mais texto. Não exigido. |
| E36 borda de campo atual sobre leitura, no escuro | 2,80:1 | É o defeito UX-17. Resolvido pelo item 3 (E40, 4,57:1). |
| E52 borda de campo atual sobre o verde suave, no escuro | 2,47:1 | Também é UX-17. Resolvido pelo item 3 (E53, 4,03:1). |
| E44 ícone branco sobre a esmeralda, no escuro | 2,97:1 | A especificação usa traço escuro no escuro (E46, 5,50:1). |
| E51 divisória sobre o fundo, no escuro | 1,81:1 | Divisória decorativa. Não exigido. |

## Ordem de aplicação (fase futura)

1. QA entrega as capturas de regressão em 375, 768, 1024 e 1440 px nos dois temas.
2. Design aplica 1, 2, 3, 7 e 9 em `tokens.css` (cor e medida, sem renomear nada).
3. QA ajusta `testes/estilo_tokens.cjs` (piso de 14 px, raios, quebras) e o Design aplica 4, 5, 11 e 12.
4. Frontend migra as regras por componente (parte A), usando `componentes.md`.
5. Item 10 já decidido (P11.4, ameixa).
