---
type: reference
title: Especificação por componente da Mesa
created: 2026-11-21
tags: [design, componentes, contrato-visual, acessibilidade]
related: ['[[design-system]]', '[[mudancas-de-token]]', '[[referencia/README]]']
---

# Especificação por componente da Mesa

Esta especificação transforma o canvas "Vlado — Mesa ideal" em componentes que o Frontend constrói e o Design confere. As imagens de referência estão em [`referencia/`](referencia/README.md); as mudanças de token, com o contraste medido de cada par, em [`mudancas-de-token.md`](mudancas-de-token.md).

## Por que um arquivo só

Um índice com seções, e não um arquivo por componente, porque:

- os componentes dividem os mesmos tokens e os mesmos seis estados; separados, cada arquivo repetiria a tabela de foco, ocupado e erro, e uma correção num deles deixaria os outros para trás;
- o portão de cada tela (regra 5 do contrato) confere vários componentes de uma vez, e a busca por um token (`--theme-warning`, por exemplo) num arquivo só mostra todos os lugares em que ele aparece;
- a revisão vê numa leitura a especificação inteira contra o canvas.

Cada componente tem uma âncora própria, para os critérios de aceite apontarem direto para a seção.

## Como ler

- **Medidas** em px de CSS, iguais às do canvas. Onde duas telas do canvas usam medidas diferentes para o mesmo componente, as duas aparecem, com a tela de cada uma, e a diferença vai para as [perguntas ao dono](#perguntas-para-o-dono). A especificação não arredonda nada sozinha.
- **Cores** pelo token semântico. O valor está em `design-system.md` e, para o que muda, em `mudancas-de-token.md`. Token marcado *(novo)* é proposta daquele documento e ainda não existe em `tokens.css`.
- **Estados.** Os seis do pedido: padrão, foco, ocupado, erro, desabilitado e vazio, mais "ao passar o mouse" e "selecionado" quando existem. A coluna *Origem* diz de onde vem cada linha:
  - **canvas**: desenhado numa tela final;
  - **wireframe Wnn**: regra ou estrutura de um wireframe, sem cor desenhada; a aparência sai dos tokens;
  - **derivado**: o canvas não desenha; a especificação propõe a partir dos tokens e das regras de W11. Não é divergência do canvas, é lacuna dele, e o Frontend pode construir; se o dono quiser outro desenho, vale o dele.
  - **não se aplica**.
- **Tema escuro.** O canvas só desenha no escuro a pergunta no celular. Para as demais telas, o escuro é o mesmo componente com os tokens do escuro; as exceções estão anotadas.

## Fundamentos

### Tipografia

| Papel | Família | Tamanho / peso / entrelinha | Token |
|---|---|---|---|
| Título da apuração | serifa | 36 / 600 / 1,15, espaçamento −0,4 px | `--text-3xl` *(novo)* |
| Título de área | serifa | 28 / 600 / 1,2 | `--text-2xl` |
| Título de seção | serifa | 22 / 600 | `--text-xl` |
| Resposta da IA, leitura, citação | serifa | 18 / 400 (1,55 no celular) | `--text-lg` |
| Interface, botões, campos | sem serifa | 16 / 400 ou 600 / 1,5 | `--text-base` |
| Apoio, fonte citada, rótulos | sem serifa | 14 / 400 ou 600 | `--text-md` |
| Rubrica ("SEU PRÓXIMO PASSO", "LIGAÇÃO SELECIONADA", "MOSTRAR", "COMO LER") | sem serifa | 14 / 600, maiúsculas, espaçamento 0,6 px | `--text-md` |
| Frase de destaque ("Seu próximo passo") | serifa | 24 / 400 / 1,3 | `--text-destaque` *(novo)* |
| Número de contagem | serifa | 32 / 600 / 1,1 | `--text-numero` *(novo)* |
| Marca na barra lateral | serifa | 32 / 600 / 1,5 (herdada do corpo), espaçamento −0,5 px | `--text-numero` *(novo)* |
| Marca no Entrar | serifa | 40 / 600 / 1 | `--text-marca` *(novo)* |

Serifa = `--fonte-titulo` *(novo)*, Source Serif 4. Sem serifa = `--fonte-interface` *(novo)*, Source Sans 3. Nenhum texto de interface abaixo de 14 px; nenhum campo abaixo de 16 px. Texto de leitura com até 70 caracteres por linha (UX-10).

<a id="apostrofo"></a>

**Apóstrofo e aspas no inglês** (decisão do Design, 23/11/2026, sobre o cruzamento do Lume com o Vitral no ensaio da nona rodada). O texto em inglês da interface (`i18n_en.js`, em textos e em padrões) usa o apóstrofo curvo `’` (U+2019), como as aspas curvas “ ” que o arquivo já usa no lugar das «» do português. O apóstrofo reto `'` fica só em código, identificador e valor de atributo. "Chave própria da redação" é "Newsroom’s own key", e "dos quais {valor} com a chave própria" é "of which {valor} with the newsroom’s own key". O "with" é porque a chave paga o gasto. "On" leria como gasto com a compra da chave. As variantes do mesmo texto (com a cota usada e com a cota esgotada) seguem igual.

### Espaço, raio e alvo

- Espaços do canvas: 4, 8, 12, 16, 24, 32 e 48 px na escala. **Decisão do dono (P11.8):** preenchimento, intervalo e margem fora da grade de 4 px arredondam para cima na implementação: 6 → 8, 10 → 12, 14 → 16, 18 → 20, 22 → 24 (e 2 → 4, 42 → 44). As tabelas desta especificação mostram a medida do canvas; o Frontend aplica o arredondamento, e a conferência aceita essa diferença como regra, não como divergência.
- Raios: controle 8 px (`--raio-controle`), cartão 12 px (`--raio-cartao`), pílula (`--raio-pilula`). **Decisão do dono (P11.3):** 12 px em todos os cartões, inclusive os que o canvas desenha com 10 px (achados, caixa da pergunta, cota); 4 px só na folha do documento e no topo das barras (`--raio-folha`).
- Alvo de toque: 44 px de altura no mínimo, em toda largura; 48 px nos controles principais do celular e do Entrar. Controle principal é a ação que conclui a tarefa da tela: o botão principal, as ações empilhadas do achado aberto, "Conferir agora", "Escolher arquivos". Navegação dentro da tela, como as abas em pílula do celular (P20b), não é controle principal e fica no mínimo de 44 px.

### Foco

Todo elemento interativo: `outline: 3px solid var(--theme-focus); outline-offset: 2px` (`--foco-largura`, `--foco-afastamento`, *novos*). Claro: ocre `#8a5a12`; escuro: ocre `#e6bc7a`. Nunca removido, nunca trocado por mudança só de cor. Dentro de contêiner com corte, anel interno (ver `mudancas-de-token.md`, item 2), nunca em botão principal. Origem: canvas (`:focus-visible` de todas as telas e o botão "Em foco" do design system).

<a id="foco-aa"></a>

**Decisões do portão AA** *(derivado, 22/11/2026, sobre o medidor de contraste da Sonda em `lancamento/qa-o3` `1ac811d`)*. Contrastes medidos com os tokens de `b5874ad`, claro / escuro.

| Grupo | Decisão | Contraste depois |
|---|---|---|
| (a) Anel da barra lateral e das abas encostando no item ativo vizinho (ocre sobre `--theme-accent`: 1,62 / 1,05) | Nos itens da [barra lateral](#barra-lateral) e das [abas](#abas), inclusive as abas de Minha conta, Equipe e Configurações e as pílulas do celular, o anel de quem **não** é o item selecionado entra 1 px na borda do próprio item: `outline: var(--foco-largura) solid var(--theme-focus); outline-offset: -1px`. Com o intervalo de 4 px entre itens, sobram 2 px do fundo entre o anel e o vizinho, o bastante para o medidor da Sonda, que lê a 1 px do anel, ver só o fundo (ressalva A1 da Coruja sobre `0750504..38ae70d`; a primeira versão, com afastamento 0, deixava 1 px). Do lado de dentro, o anel encosta no fundo do próprio item, que não é verde. Conferido com a Sonda (`testes/contraste_wcag.py:335-337` em `1ac811d`): o medidor lê a `max(afastamento + largura, 0) + 1` px da borda, aqui a 3 px, sobre o fundo da barra, com 1 px de folga antes do vizinho. **O intervalo de 4 px entre itens é condição:** com 3 px ou menos, a leitura cai no vizinho ativo e volta a reprovar. O item selecionado (`aria-current="page"`) mantém o afastamento de 2 px (`--foco-afastamento`), porque o anel dele cai sobre o fundo da barra e nunca há dois selecionados lado a lado. O intervalo de 4 px do canvas não muda | ocre sobre `--theme-sidebar` 5,12 / 10,22; sobre `--theme-soft` (item sob o mouse) 5,01 / 6,60; sobre `--theme-surface` (abas dos quadros) 5,86 / 8,52; sobre `--theme-background` 5,42 / 9,65 |
| (b) Editor do Caderno (Vditor) sem contorno de foco | Área de edição (`pre.vditor-reset`): anel interno, `outline: var(--foco-largura) solid var(--theme-focus); outline-offset: calc(-1 * var(--foco-largura) - 2px)` (`mudancas-de-token.md`, item 2), porque ela ocupa o cartão inteiro e o cartão corta. Botões da barra do editor: o anel padrão (3 px, afastamento 2); se a barra cortar o anel, afastamento 0. Campo de texto do editor (`input`): o anel padrão e a borda 1 px `--theme-input-line` do [campo](#campo). Nenhum desses fica sobre fundo verde | ocre sobre `--theme-surface` 5,86 / 8,52; borda do campo sobre `--theme-surface` 3,95 / 5,21 |
| (c) Seletor de apuração do topo (`select#contexto-caso`) sem borda, no fundo da página (1,00:1) | **Sem caixa, como no canvas: decisão do dono, P34 (22/11/2026).** O seletor fica como o canvas desenha ("Apuração" sobre o nome, com a seta ⌄). Pelo WCAG 1.4.11, o que precisa de 3:1 é o que identifica o controle, o texto e a seta, não uma borda. Aqui, o que identifica são o rótulo "Apuração", o nome em 16/600 e a seta, todos em `--theme-text`. Para a exceção valer: a seta é sempre `--theme-text` (nunca `--theme-muted`) e tem 16 px; o foco é o anel padrão; ao passar o mouse, o fundo vira `--theme-soft`, só como reforço, sem levar informação. A Sonda anota a exceção no medidor, para ele não cobrar a borda deste controle | seta e texto sobre `--theme-background` acima de 13:1 nos dois temas |
| (d) Título da nota no Caderno (`input#apuracao-nota-titulo`) com sublinhado da cor do fundo | Sublinhado sempre visível: `border-bottom: 1px solid var(--theme-input-line)`, sem as outras bordas. No foco, o anel padrão. O rótulo "Título da nota" continua visível acima | `--theme-input-line` sobre `--theme-surface` 3,95 / 5,21 |

Com (a), (b) e (d) corrigidos e (c) decidido pelo dono (P34), os grupos foco e campo do medidor ficam zerados, com (c) anotado no medidor.

### Quebras

720, 1024 e 1280 px (`mudancas-de-token.md`, item 6). O canvas desenha 390 e 1440 px; as pranchas derivadas da fase 3 desenham 1024 e 390 px de duas telas ([Telas derivadas](#telas-derivadas)). A faixa de 720 a 1023 px ainda será desenhada.

### Movimento

O canvas é estático. Derivado de W11 e UX-08: transição de cor e fundo em 150 ms; o esqueleto não pulsa, em nenhum modo (derivado, 22/11/2026); com `prefers-reduced-motion: reduce`, nenhuma animação: a barra fica parada e o texto de etapa continua mudando.

---

## Componentes

<a id="botao"></a>

### Botão

Onde: todas as telas. Elemento `<button type="button">` (ou `<a>` quando leva a outra página, como "Conferir agora").

| Variante | Altura | Preenchimento | Fundo | Borda | Texto | Onde no canvas |
|---|---|---|---|---|---|---|
| Principal | 44 | 0 16 (0 18 em Visão geral e no design system) | `--theme-accent` | nenhuma | `--theme-on-primary`, 16/600 | "Confere com o original", "Nova apuração", "Adicionar ligação" |
| Secundário | 44 | 0 16 (0 18 em Visão geral e no design system; 0 14 nos botões do alerta de homônimo) | `--theme-surface` | 1 px `--theme-input-line` | `--theme-text`, 16/400 | "Exportar apuração", "Precisa de ajuste", "Ver como lista" |
| Destrutivo | 44 | 0 18 | `--theme-surface` | 1 px `--theme-danger-line` | `--theme-danger`, 16/400 | "Destrutivo" no design system |
| Recusa na conferência | 44 | 0 16 | `--theme-surface` | 1 px `--theme-input-line` | `--theme-danger`, 16/400 | "Sem suporte" em Conferir achado |
| Sobre aviso | 44 | 0 14 | `--theme-surface` | 1 px `--theme-warning` | `--theme-warning`, 16/400 | "Virar pergunta ou pedido" na linha do tempo |
| Grande (celular e Entrar) | 48 | largura cheia | como o principal ou o secundário | idem | principal no Entrar em 18/600 | "Entrar", "Entrar com chave de acesso", "Conferir os 4 achados no original" |
| Chamada da Visão geral | 52 | 0 24 | `--theme-accent` | nenhuma | `--theme-on-primary`, 18/600 | "Conferir agora" (é `<a>`) |
| Contorno verde | 44 | largura cheia | `--theme-surface` | 1 px `--theme-accent` | `--theme-accent` (cor de link), 16/600 | "Minha redação quer participar" (é `<a>`) |
| Só ícone | 44 × 44 | — | `--theme-surface` (zoom) ou transparente (menu) | 1 px `--theme-input-line` (zoom) ou nenhuma (menu) | sinal 20 px ou ícone 22 px | "Diminuir zoom", "Aumentar zoom", "Abrir menu"; sempre com `aria-label` |
| Enviar (celular) | 48 × 48 | — | `--theme-accent` | nenhuma | ícone seta 22 px, traço 2,5, `--theme-on-primary` | "Enviar pergunta", com `aria-label` |
| Filtro em pílula | 44 | 0 14 | ligado: `--theme-accent`; desligado: `--theme-surface` | ligado: nenhuma; desligado: 1 px `--theme-input-line` | ligado: `--theme-on-primary` 16/600; desligado: `--theme-text` 16/400 | "Tudo", "Pagamentos", "Contratos", "Pedidos"; raio pílula; intervalo de 8 px, com quebra de linha |

Raio 8 px em todas, menos o filtro (pílula).

| Estado | Aparência | Origem |
|---|---|---|
| Padrão | tabela acima | canvas |
| Ao passar o mouse | principal: fundo `--theme-primary-hover`; secundário e destrutivo: fundo `--theme-soft` | derivado (o canvas só define a cor de link ao passar, `#2e604c`, que é `--theme-primary-hover`) |
| Pressionado | desce 1 px (`transform: translateY(1px)`), sem mudar a cor | derivado (UX-08: não há `:active`) |
| Foco | anel de foco com afastamento de 2 px | canvas ("Em foco") |
| Ocupado | rótulo troca pelo verbo da ação no gerúndio ("Conferindo…"), largura mantida, `aria-busy="true"`, `aria-disabled="true"`; sem rodinha | derivado de W11 (regra 2) |
| Erro | o botão não muda; o erro aparece junto ao que falhou (campo ou cartão) | wireframe W11 (regras 4 e 5) |
| Desabilitado | fundo `--theme-sidebar`, borda 1 px `--theme-line`, texto `--theme-disabled-text` 16/400 (no claro, igual a `--theme-muted`; no escuro, mais apagado, `mudancas-de-token.md`, item 13) | canvas ("Indisponível"); token do escuro de 22/11/2026 |
| Vazio | não se aplica | — |

<a id="link"></a>

### Link

Texto `--theme-accent`; ao passar o mouse, `--theme-primary-hover`. Sublinhado quando está no meio do texto ou sozinho ("Abrir o original em nova aba", "Esqueci a senha", "Termos de uso"); sem sublinhado quando é item de lista ou de navegação. "Ver todas" e "Abrir o original em nova aba" em 600. Foco: anel. Origem: canvas (`a{color}` e `a:hover{color}` de todas as telas).

<a id="campo"></a>

### Campo de texto

Onde: design system ("Nome da apuração", "E-mail"), Entrar, compositor do celular, W01, W05, W06, W10.

| Parte | Medida e token |
|---|---|
| Rótulo | acima do campo, 16/600 `--theme-text`, intervalo de 6 px; no celular 14/400 `--theme-muted`, intervalo de 4 px |
| Campo de uma linha | altura 44 (design system) ou 48 (Entrar); preenchimento 0 12; raio 8; borda 1 px `--theme-input-line`; fundo `--theme-surface`; texto 16/400 `--theme-text` |
| Área de texto (celular) | 2 linhas, sem redimensionar; preenchimento 10 12; raio 8; borda 1 px `--theme-input-line` (escuro: `#8a9c8f`); fundo `--theme-background`; texto 16 |
| Senha | campo mais botão secundário "Mostrar" de 48 px, preenchimento 0 14, intervalo de 8 px; "Esqueci a senha" na linha do rótulo, à direita, 14/600 |
| Mensagem de erro | abaixo do campo, 14/400 `--theme-danger`, formato "o que houve. o que fazer" ("Falta o domínio. Exemplo: ana@redacao.org") |

| Estado | Aparência | Origem |
|---|---|---|
| Padrão | tabela acima | canvas |
| Foco | anel de foco; a borda continua a mesma | canvas (`textarea:focus-visible` no celular) |
| Ocupado | não se aplica ao campo; o formulário inteiro recebe `aria-busy` | derivado |
| Erro | borda 2 px `--theme-danger`, `aria-invalid="true"`, mensagem ligada por `aria-describedby`, foco vai para o primeiro campo com erro | canvas (campo "E-mail") e W11 (regra 5) |
| Desabilitado | fundo `--theme-sidebar`, borda `--theme-line`, texto `--theme-muted` | derivado do botão "Indisponível" |
| Vazio | dica em `--theme-muted` ("exemplo.gov.br" em W01); a dica nunca substitui o rótulo | wireframe W01 |

<a id="selo"></a>

### Selo de estado

Onde: design system, Conferir achado, mapa. `<span>` 14/600, preenchimento 4 12, raio pílula, borda 1 px. Sempre com sinal e texto.

| Selo | Texto | Fundo | Borda | Sinal |
|---|---|---|---|---|
| Conferido no original | `--theme-accent` | `--theme-soft` | `--theme-accent-line` | ✓ |
| A conferir | `--theme-text` | `--theme-surface` | `--theme-input-line` | ○ |
| Lacuna | `--theme-warning` | `--theme-warning-bg` | `--theme-warning-line` | ? |
| Sem suporte | `--theme-danger` | `--theme-danger-bg` | `--theme-danger-line` | ✕ |
| Lida por OCR | `--theme-warning` | `--theme-warning-bg` | `--theme-warning-line` | nenhum (o texto basta) |
| Precisa de ajuste *(derivado)* | `--theme-warning` | `--theme-warning-bg` | `--theme-warning-line` | ! |

**Veredito da IA (derivado, aprovado pelo dono em 22/11/2026, P20a).** O canvas só desenha os selos da conferência humana (tabela acima). O veredito da IA sobre o suporte de um achado é o mesmo selo, com raio pílula, mas a forma o separa da pessoa por três sinais juntos, nunca só pela cor:

- sem fundo (transparente);
- borda 1 px **tracejada**, como em tudo o que ainda espera confirmação na Mesa ("a confirmar" do mapa, item a resolver);
- texto começando por "IA ·" ("IA · sustentado", "AI · not supported"), sem sinal.

| Veredito da IA | Texto | Borda tracejada |
|---|---|---|
| Sustentado | `--theme-text` | `--theme-muted` |
| Parcial ou ilegível | `--theme-warning` | `--theme-warning` |
| Não sustentado | `--theme-danger` | `--theme-danger` |

Os selos humanos têm sempre fundo, borda contínua e o sinal da tabela. Nenhum selo usa o raio de folha (4 px), que fica só na folha do documento e no topo das barras (P11.3).

Estados: só padrão (canvas). Não é interativo: sem foco, sem passar o mouse. Ocupado, erro, desabilitado e vazio não se aplicam.

<a id="selo-fonte"></a>

### Selo de fonte

A fonte citada ao lado de um número ou de um evento. É `<a>` e abre o original na página citada (W03, regra 5).

| Variante | Medida | Cores | Onde |
|---|---|---|---|
| Em linha, no meio do texto | 14/600, preenchimento 2 8, raio pílula, sem quebra de linha | fundo `--theme-soft`, texto `--theme-accent` | resposta no celular ("Contrato, p. 1") |
| Isolado, no fim do cartão | 14/600, preenchimento 6 12, raio pílula | fundo `--theme-soft`, texto `--theme-accent` | linha do tempo ("Medição 3, p. 1") |

Estados: padrão (canvas); foco com anel (derivado); ao passar o mouse, sublinhado (derivado). Ocupado, erro, desabilitado e vazio não se aplicam. Sem fonte, não há selo: o texto diz "sem fonte ainda" (W06).

<a id="barra-lateral"></a>

### Barra lateral

Onde: Conferir achado, Visão geral. `<nav aria-label="Áreas">`.

| Parte | Medida e token |
|---|---|
| Contêiner | largura 256 (`--mesa-sidebar`; o canvas desenha 232, decisão do dono P15.7, ver `mudancas-de-token.md`, item 7); fundo `--theme-sidebar`; borda direita 1 px `--theme-line`; preenchimento 24 16; coluna com intervalo de 24 |
| Marca | "Vlado" e um ponto em `--theme-accent`; serifa 32/600, entrelinha 1,5 (herdada do corpo), espaçamento −0,5 px; preenchimento 0 8 |
| Lista de áreas | coluna, intervalo de 4. Ordem: Visão geral, Documentos, Perguntar, Conferir, Quadros, Caderno, Pedidos e prazos |
| Item | `<a>`, altura 44, preenchimento 0 12, raio 8, texto 16 `--theme-text`, sem sublinhado; rótulo numa linha só (`white-space: nowrap`) |
| Contador | à direita (`margin-left:auto`), 14 px, sem encolher nem quebrar (`flex: none`, `white-space: nowrap`); as formas estão em `mudancas-de-token.md`, item 8. No item ativo, o contador vira pílula clara (P15.7 e P16.4): "12" em Documentos, "4" em Conferir e "1 vence" em Pedidos e prazos, sempre inteira e na mesma linha do rótulo |
| Cartão da cota | no rodapé (`margin-top:auto`); fundo `--theme-surface`, borda 1 px `--theme-line`, raio 12 (P11.3; o canvas desenha 10), preenchimento 12 14, intervalo de 6; linha "Cota do mês" (14 `--theme-muted`) e valor ("R$ 18,40 de R$ 50", 14/600), numa linha com 256 px de barra; [medidor](#medidor) |
| Perfil | `<a>` altura 44, preenchimento 0 8, intervalo de 10; avatar de 32 px, círculo `--theme-accent`, iniciais 14/600 `--theme-on-primary`, `aria-hidden`; nome 16/600; papel e redação 14 `--theme-muted`, entrelinha 1,25 ("Repórter · Redação Serena" cabe numa linha com 256 px). Abre "Minha conta" (W08, regra 1) |

| Estado | Aparência | Origem |
|---|---|---|
| Padrão | tabela acima | canvas |
| Selecionado (página atual) | `aria-current="page"`; fundo `--theme-accent`, texto `--theme-on-primary` 600 | canvas |
| Ao passar o mouse | item comum: fundo `--theme-soft` | derivado |
| Foco | anel de foco | canvas (regra geral) |
| Ocupado, erro, desabilitado | não se aplicam | — |
| Vazio | contador some quando é zero | derivado |
| Cota esgotada (gasto igual ou acima do teto) | o cartão da cota vira aviso, nunca só pela cor: fundo `--theme-warning-bg`, borda 1 px `--theme-warning-line`; a primeira linha troca "Cota do mês" por "! Cota esgotada" em 14/600 `--theme-warning`, e o valor vem na linha de baixo, porque os dois não cabem juntos em 256 px (P11.5) ("R$ 50,00 de R$ 50": gasto sempre com centavos, teto sem centavos quando inteiro; 14/600 `--theme-warning`); o medidor fica cheio, com preenchimento `--theme-warning`; `aria-label` "Cota do mês esgotada: R$ 50,00 de R$ 50". O bloco "Limite atingido" ([estados](#estados)) aparece onde a ação para (pergunta, envio), não na barra | derivado de W11 (regras 6 e 7), 22/11/2026 |
| Sem cota | sem a rota ou sem sessão, o cartão some; o perfil sobe para o lugar dele | derivado |
| Cota da instalação | para o administrador, quando o orçamento da instalação é mais apertado que o da conta, o cartão mostra esse orçamento, no mesmo desenho: "Cota da instalação" e, esgotada, "! Cota da instalação esgotada". Também aparece no modo local, onde o teto vale. A trilha vazia do medidor e a borda do cartão em `--theme-line` (1,3:1) são decorativas: o valor e o `aria-label` dizem tudo | derivado, 22/11/2026 |
| Gasto na chave própria da redação (P40 b) | o teto da pessoa vale para as duas chaves, então o valor da cota da pessoa ("R$ 18,40 de R$ 50") já inclui o que a chave própria pagou. Por isso a parte paga pela chave vem como parte do valor de cima, e não como acréscimo: logo abaixo do medidor, em 14 `--theme-muted`, "dos quais R$ 3,25 com a chave própria". Só para o dono, uma linha a mais, no estilo da linha da cota (rótulo 14 `--theme-muted`, valor 14/600): "Chave própria da redação" com o total da redação, que não entra na cota do serviço. As linhas aparecem quando o servidor manda o gasto na chave ("R$ 0,00" se ainda não houve) e somem sem chave própria. No cartão de 223 px, "dos quais…" quebra em duas linhas como frase, e na linha do dono o valor desce para baixo do rótulo, alinhado à esquerda, como na cota esgotada (altura mínima, P11.5). Os textos não encurtam, para não perder o sentido de parte do valor (aceito em 23/11/2026 sobre `8956e0c`). O `aria-label` do medidor ganha ", dos quais R$ 3,25 com a chave própria", também na cota esgotada. Quando o cartão mostra a cota da instalação (para o administrador), "dos quais" não aparece, porque essa cota é só a paga pelo serviço; a linha do total da redação, para o dono, continua (decisão do Lume, aceita). | derivado, 23/11/2026; ressalva da Coruja sobre `e965f75` e `913da30`, que tratavam a linha como acréscimo |
| Abaixo de 1280 px | vira gaveta: o conteúdo fica `inert` com ela aberta, e ela abre pelo botão de menu do cabeçalho ([tablet](#tablet)) | plano (UX-11, UX-17) e derivado; limite de 1280 px decidido pelo dono (P12.1) |

Sem ícones nos itens da barra, como no canvas (decisão do dono, P11.6). Rótulo e contador dos itens nunca quebram linha (P15.7); a largura de 256 px foi medida para o item mais longo, "Pedidos e prazos" ativo com "1 vence" (188 px de 199 úteis). Perfil e cota cabem numa linha com os textos das pranchas; para nome de redação ou valor mais longo, vale a altura mínima no lugar de altura fixa (P11.5). Área nova na barra pede nova medida.

<a id="medidor"></a>

### Medidor

Barra fina de proporção: cota usada, achados conferidos. Altura 6, raio pílula, trilha `--theme-line`, preenchimento `--theme-accent`. `role="img"` com `aria-label` por extenso ("37% da cota usada", "2 de 6"). Na barra de progresso de envio (design system) e no ocupado longo (W11): altura 8, mesma cor. Estados: padrão (canvas); quando a cota passa do teto, ver [estados](#estados), "Limite atingido".

<a id="cabecalhos"></a>

### Cabeçalhos

| Cabeçalho | Medida e token | Conteúdo | Onde |
|---|---|---|---|
| Da apuração | altura 64; preenchimento 0 32; intervalo de 16; fundo `--theme-surface`; borda inferior 1 px `--theme-line` | "Apuração" (14 `--theme-muted`) sobre o nome (16/600); à direita, estado de salvamento (ícone ✓ de 16 px em `--theme-accent`, traço 2,5, e "Salvo às 14h32" em 14 `--theme-muted`) e botão secundário "Exportar apuração" | Conferir achado |
| Da Visão geral | sem barra; no topo do conteúdo, alinhado pela base, intervalo de 16 | "Apuração · criada em 12 de novembro" (14 `--theme-muted`) sobre o título (serifa 36/600); à direita, "Trocar de apuração" (secundário) e "Nova apuração" (principal) | Visão geral |
| Dos quadros | altura 72; preenchimento 0 32; intervalo de 24; fundo `--theme-surface`; borda inferior 1 px `--theme-line` | caminho de volta (botão secundário "‹ Apuração", 44 px; decisão do dono, P11.7: os quadros não têm barra lateral de propósito), "Quadros" (serifa 28/600), [abas](#abas) e ações à direita | as cinco abas dos quadros |
| Do celular | altura 60; preenchimento 0 12; intervalo de 8; fundo `--theme-sidebar`; borda inferior 1 px `--theme-line` | botão de menu (só ícone), "Apuração" (14 `--theme-muted`) sobre o nome (16/600, cortado com reticências), cota à direita ("R$ 18,40 de 50", 14 `--theme-muted`) | Pergunta no celular |

O estado de salvamento é anunciado a leitor de tela quando muda (W11, regra 9). Erro ao salvar: derivado, troca o ícone por ✕ em `--theme-danger` e o texto por "Não salvou. Tentando de novo".

<a id="abas"></a>

### Abas

Onde: cabeçalho dos quadros. Linha com intervalo de 4. Cada aba é `<a>`: altura 44, preenchimento 0 14, raio 8, texto 16 `--theme-text`. Ativa: `aria-current="page"`, fundo `--theme-soft`, texto `--theme-accent` 600. Foco: anel. Ao passar o mouse (derivado): fundo `--theme-soft`. Ocupado, erro, desabilitado e vazio não se aplicam. Ordem: Hipóteses, Linha do tempo, Mapa de relações, Tabelas, Comparador (cinco abas, decisão do dono P15.1; "Conferência do texto" foi para o caderno e "Entrevistas e pedidos" virou a área Pedidos e prazos). Rótulo sem quebra de linha. É o único padrão de aba da Mesa (UX-17 aponta três). No celular, as abas viram pílulas que rolam para o lado: altura 44 (o canvas desenha 40; decisão do dono P20b, 22/11/2026, pelo alvo de toque), preenchimento 0 16, raio pílula, borda 1 px `--theme-input-line`; ativa verde cheio (`--theme-accent`, texto `--theme-on-primary` 600); "Mapa" no lugar de "Mapa de relações"; faixa com preenchimento 12 16, fundo `--theme-surface` e borda inferior 1 px `--theme-line`.

<a id="faixa-que-rola"></a>

**Faixa que rola para o lado** (Q5 da Coruja, 23/11/2026). Vale, abaixo de 720 px, para as quatro faixas da Mesa que rolam por dentro: a linha de etapas (`#mesa-etapas`, item ativo por `aria-current="step"`), as pílulas dos Quadros (`.quadros-abas`, por `aria-selected="true"`), as abas de Documentos (`.mesa-tabs`, "Acervo cadastrado" e "Pesquisar no conteúdo") e as do Caderno (`.notebook-tabs`, "Notas e redação" e "Trechos com fonte e contribuições"), as duas últimas por `aria-pressed="true"` (escopo completado pela T1 da Coruja sobre `bb83992`; a 320 px, "Pesquisar no conteúdo" fica cortada). A 320 px, a linha de etapas do Caderno deixava o passo atual, "4 Caderno", fora da vista. Nos Quadros, apareciam duas das cinco pílulas, cortadas na divisa entre elas, e a faixa parecia completa. Quando o conteúdo passa da largura da faixa:

- **O item ativo fica à vista.** Ao desenhar a faixa e ao trocar de item, só a faixa rola (`scrollLeft`, nunca a página) até o item ativo caber inteiro, com 32 px de folga do lado de onde veio (`--espaco-8`, a mesma largura do esmaecido, para o ativo nunca parar sob a máscara; o `scroll-padding-inline` das pílulas também é `--espaco-8`; decisão do Maestro, código em `4e7c77f`). A rolagem é instantânea, sem animação.
- **Esmaecido na borda.** Do lado em que ainda há conteúdo, os últimos 32 px da faixa esmaecem até sumir. O esmaecido é uma máscara (`mask-image` com gradiente de opaco a transparente), e não uma cor, para valer nos dois temas sem token novo. O lado vem de `data-rola` (`fim`, `inicio` ou `ambos`), recalculado ao rolar e ao redimensionar. Sem estouro, a faixa fica sem o atributo e sem máscara. A máscara vai no próprio elemento que rola. Nenhuma das quatro faixas tem fundo próprio no CSS (as pílulas dos Quadros ficam sobre o fundo do painel), então o esmaecido revela o fundo de trás. Se alguma ganhar fundo, ele passa ao elemento pai, para não esmaecer junto.
- **Nada além disso.** Sem setas e sem barra de rolagem à vista (a linha de etapas já a esconde). Pelo teclado, o navegador já traz à vista o item que recebe o foco. Como não há animação, `prefers-reduced-motion` não muda nada aqui.
- **Prova:** capturas a 320, 390 e 430 px do Caderno (etapas e abas), de Documentos (etapas e abas, com "Pesquisar no conteúdo" ativa) e dos Quadros, nos dois temas, com o item ativo inteiro dentro da faixa. A medida de reflow passa a conferir também os elementos que rolam por dentro, além da página.

<a id="achado"></a>

### Cartão de achado

Onde: Conferir achado. Coluna com intervalo de 12, abaixo do título "Conferir achados" (serifa 28/600) com o progresso ao lado ("2 de 6 conferidos", 14 `--theme-muted`, alinhado pela base, intervalo de 12). A coluna tem preenchimento 28 32 e intervalo de 20 entre título, pergunta e lista.

Estrutura comum: sinal de 28 px à esquerda, texto do achado (16, entrelinha 1,5) e, abaixo, a linha de fonte (14), com intervalo de 6; intervalo de 14 entre sinal e texto; preenchimento 16 18; raio 12 (P11.3; o canvas desenha 10).

| Variante | Elemento | Fundo e borda | Sinal | Linha de fonte |
|---|---|---|---|---|
| Conferido | `<button>` | `--theme-surface`, 1 px `--theme-line` | círculo `--theme-soft` com ✓ de 16 px em `--theme-accent`, traço 2,5 | 14/600 `--theme-accent`: "Conferido no original · Contrato 041/2025, p. 1" |
| A conferir | `<button>` | `--theme-surface`, 1 px `--theme-line` | círculo vazio, borda 2 px `--theme-input-line` | 14 `--theme-muted`: "Termo aditivo nº 1, p. 2 · a conferir" |
| Em conferência (aberto) | `<div>` | `--theme-surface`, 2 px `--theme-accent`, sombra 0 4 18 alfa 0,08 | círculo vazio | 14 `--theme-muted`: fonte, forma de leitura ("página digitalizada, lida por OCR") e a conta ("cálculo: 3.900.000 ÷ 8.750.000"); valor citado em `<strong>` |
| Lacuna | `<button>` | `--theme-warning-bg`, 1 px `--theme-warning-line` | círculo `--theme-warning` com "?" 700 em `--theme-on-primary` | 14/600 `--theme-warning`: "Lacuna · a busca não encontrou; isso não prova ausência" |

Ações do cartão aberto: linha com recuo de 42 px, intervalo de 8, quebra de linha: principal "Confere com o original", secundário "Precisa de ajuste", recusa "Sem suporte" (texto `--theme-danger`).

| Estado | Aparência | Origem |
|---|---|---|
| Padrão | tabela acima | canvas |
| Selecionado | variante "Em conferência" | canvas |
| Foco | anel de foco no cartão-botão; dentro da lista com corte, anel interno (UX-01) | canvas (regra geral) e plano |
| Ocupado | depois de escolher uma ação: `aria-busy` no cartão, os três botões em estado ocupado, o escolhido com o rótulo no gerúndio | derivado |
| Erro | mensagem abaixo das ações, 14 `--theme-danger`, "o que houve, o que fazer" ("Não deu para registrar. Tente de novo."); o cartão continua aberto | derivado de W11 (regra 4) |
| Desabilitado | leitor sem permissão de conferir: o cartão abre, os botões ficam no estado desabilitado com a razão em 14 `--theme-muted` ("Só repórter e editor conferem") | derivado de W09 (regra 1) |
| Vazio | bloco de [estado vazio](#estados): "Nenhum achado para conferir" e a ação "Fazer uma pergunta" | derivado de W11 (regra 1) |

<a id="caixa-pergunta"></a>

### Caixa da pergunta

Onde: Conferir achado. Fundo `--theme-reading`, raio 12 (P11.3; o canvas desenha 10), preenchimento 14 18, intervalo de 4. Rótulo "Sua pergunta" (14 `--theme-muted`) sobre a pergunta (serifa 18). Só leitura: um estado (canvas).

<a id="painel-original"></a>

### Painel do original

Onde: Conferir achado, à direita. `<aside aria-label="Original citado">`.

| Parte | Medida e token |
|---|---|
| Contêiner | largura 520; fundo `--theme-sidebar`; borda esquerda 1 px `--theme-line`; preenchimento 20 24; coluna com intervalo de 14 |
| Topo | nome do documento (16/600) sobre "Página 1 de 1 · original preservado" (14 `--theme-muted`); à direita, selo "Lida por OCR" quando a página veio de OCR |
| Folha | fundo `--pdf-pagina` (branco nos dois temas); borda 1 px `--theme-line`; raio 4 (P11.3); sombra 0 1 2 alfa 0,08 (`--sombra-folha`, *nova*); ocupa a altura disponível |
| Trecho citado | fundo `--pdf-trecho` (translúcido; exceção registrada em `mudancas-de-token.md`, item 9) e contorno de 2 px `--pdf-trecho-borda` |
| Rodapé | "Diminuir zoom" e "Aumentar zoom" (só ícone, 44 × 44), intervalo de 8; "Abrir o original em nova aba" à direita (link 600) |

| Estado | Aparência | Origem |
|---|---|---|
| Padrão | tabela acima | canvas |
| Foco | anel interno na folha (`outline-offset` negativo), porque o painel corta o conteúdo | plano (UX-01) |
| Ocupado | esqueleto do tamanho da folha enquanto a página carrega | derivado de W11 (regra 2) |
| Erro | dentro da folha: "Não deu para mostrar esta página. O original está guardado." e o link "Abrir o original em nova aba" | derivado de W11 (regra 4) |
| Desabilitado | não se aplica | — |
| Vazio | sem achado escolhido: "Escolha um achado para ver o trecho no original." em 14 `--theme-muted`, centralizado na folha | derivado de W11 (regra 1) |

Abaixo de 1280 px o painel não cabe ao lado da lista; o desenho dessa faixa está pendente.

<a id="proximo-passo"></a>

### Cartão "Seu próximo passo"

Onde: Visão geral. Fundo `--theme-surface`, borda 1 px `--theme-line`, raio 12, preenchimento 28 32, intervalo de 32, itens centralizados, sombra 0 1 2 alfa 0,06 (`--sombra-cartao`). À esquerda, coluna com intervalo de 8: rubrica "SEU PRÓXIMO PASSO" em `--theme-accent`; a frase (serifa 24, entrelinha 1,3); o apoio (16 `--theme-muted`). À direita, a chamada "Conferir agora" (botão de 52 px).

Estados: padrão (canvas). Vazio (derivado): sem pendência, a frase vira "Nada esperando conferência." e a chamada vira "Fazer uma pergunta". Ocupado (derivado): esqueleto de três linhas. Foco: só na chamada.

<a id="contagem"></a>

### Cartão de contagem

Onde: Visão geral, em grade de 4 colunas iguais, intervalo de 16. Fundo `--theme-surface`, borda 1 px `--theme-line`, raio 12, preenchimento 20 22, coluna com intervalo de 4. Rótulo (14 `--theme-muted`), número (serifa 32/600, entrelinha 1,1; complemento "de 6" em 18/400 `--theme-muted`), apoio (14 `--theme-muted`, ou 14/600 `--theme-warning` quando é pendência: "1 sem evidência ainda"). Opcional: [medidor](#medidor) com 6 px de margem acima.

Variante de aviso ("Pedido de LAI", "5 dias"): fundo `--theme-warning-bg`, borda `--theme-warning-line`, rótulo 14/600 `--theme-warning`, apoio 14 `--theme-text`.

Estados: padrão (canvas). Ocupado: esqueleto (derivado). Vazio: número "0" e apoio com a ação ("Enviar documentos"), derivado de W11 (regra 1). O cartão não é clicável no canvas; se virar link, recebe foco e passar o mouse do [link](#link).

<a id="perguntas-recentes"></a>

### Lista de perguntas recentes

Onde: Visão geral, metade esquerda da grade de 2 colunas (intervalo de 16). Seção com fundo `--theme-surface`, borda 1 px `--theme-line`, raio 12, preenchimento 22 24, intervalo de 14. Título "Últimas perguntas" (serifa 22/600) com "Ver todas" à direita. Cada item é `<a>` com preenchimento 12 0, borda superior 1 px `--theme-line`, intervalo de 2: a pergunta (16 `--theme-text`) e a linha de apoio (14 `--theme-muted`: "Hoje, 14h10 · 6 achados · R$ 1,32").

Estados: padrão (canvas); foco no item (anel); ao passar o mouse, a pergunta em `--theme-accent` (derivado); vazio: "Nenhuma pergunta ainda" com a ação "Fazer a primeira pergunta" (derivado de W11, regra 1).

<a id="tempo-resumida"></a>

### Linha do tempo resumida

Onde: Visão geral, metade direita. Mesma seção da lista acima, título "Linha do tempo documentada". Trilho: borda esquerda de 2 px `--tempo-trilho`, 6 px de recuo, 20 px de preenchimento. Cada item: preenchimento 6 0 14; marco à esquerda sobre o trilho, de 12 px cheio em `--tempo-marco-exato` (data exata) ou de 10 px com borda 2 px `--tempo-marco-exato` e fundo `--tempo-marco-parcial` (data parcial); data em 14 `--theme-muted` ("Outubro de 2025 · dia não informado"); acontecimento em 16. Estados: padrão (canvas); vazio derivado ("Nenhum acontecimento com data ainda").

<a id="resposta-celular"></a>

### Resposta no celular

Onde: Pergunta no celular (escuro). Conteúdo com preenchimento 20 16 e intervalo de 16.

| Parte | Medida e token |
|---|---|
| Pergunta da pessoa | à direita, largura máxima 300, fundo `--theme-soft`, raio 12, preenchimento 12 14 |
| Linha de execução | 14 `--theme-muted`, ✓ de 16 px em `--theme-accent`, intervalo de 8: "Leu 12 documentos em 1 min 48 s · R$ 1,32" |
| Parágrafo da resposta | serifa 18, entrelinha 1,55; valores em `<strong>`; [selo de fonte em linha](#selo-fonte) logo depois de cada número |
| Bloco de lacuna | fundo `--theme-warning-bg`, borda 1 px `--theme-warning-line`, raio 12, preenchimento 12 14, intervalo de 10; sinal "?" em círculo de 24 px `--theme-warning` com texto `--theme-on-primary` 14/700; texto 14, entrelinha 1,45, começando por "Lacuna." em `<strong>` `--theme-warning` |
| Chamada | botão grande de 48 px, largura cheia, principal: "Conferir os 4 achados no original" |

| Estado | Aparência | Origem |
|---|---|---|
| Padrão | tabela acima | canvas |
| Ocupado | barra com etapa, as seis etapas nomeadas e o gasto até agora, com "Parar" | wireframe W03 (regra 4) e W11 (ocupado longo) |
| Erro | bloco de erro do serviço (ver [estados](#estados)) no lugar da resposta | wireframe W11 |
| Vazio | sem pergunta ainda: só o compositor, com uma linha de apoio ("Pergunte sobre os documentos desta apuração") | derivado de W11 (regra 1) |
| Foco, desabilitado | nos elementos interativos (selos, chamada), como no componente de cada um | — |

<a id="compositor"></a>

### Compositor de pergunta

Onde: rodapé do celular; W03 no desktop. Rodapé com fundo `--theme-surface`, borda superior 1 px `--theme-line`, preenchimento 12 16 20, coluna com intervalo de 8. Linha com o [campo](#campo) (área de texto, rótulo "Nova pergunta ou complemento") e o botão "Enviar" de 48 × 48, alinhados pela base, intervalo de 8. Abaixo, o custo em 14 `--theme-muted`: "Custo estimado: R$ 0,90 a 1,40 · trechos vão ao provedor de IA".

Regras que vêm dos wireframes: nunca cobre o conteúdo (W03, regra 2; UX-19: recolhido quando há conteúdo atrás); estimativa antes, gasto durante, valor depois, em reais (W03, regra 3); "rascunho salvo" (W03).

| Estado | Aparência | Origem |
|---|---|---|
| Padrão | acima | canvas |
| Foco | anel de foco na área de texto (escuro: ocre `#e6bc7a`) | canvas |
| Ocupado | o compositor não muda: continua com "Enviar" e com "rascunho salvo" na linha de custo; o "Parar" fica no bloco de progresso da resposta, junto do gasto até agora (ver [resposta no celular](#resposta-celular)) | wireframe W03 |
| Erro | mensagem de campo abaixo ("Falta a pergunta. Escreva o que quer saber dos documentos.") | derivado de W11 (regra 5) |
| Desabilitado | cota acabou: campo e botão desabilitados, com o bloco "Limite atingido" acima | wireframe W11 |
| Vazio | botão "Enviar" desabilitado até haver texto | derivado |

<a id="entrar"></a>

### Formulário de entrada

Onde: Entrar (celular). Página com fundo `--theme-background`, preenchimento 48 24 24, coluna com intervalo de 28.

| Parte | Medida e token |
|---|---|
| Marca | "Vlado." em serifa 40/600, entrelinha 1; abaixo, "Apuração documental com a fonte de cada afirmação à vista." em serifa 18 `--theme-muted` |
| Cartão | `<form>`; fundo `--theme-surface`, borda 1 px `--theme-line`, raio 12, preenchimento 24 20, coluna com intervalo de 18, sombra 0 1 2 alfa 0,06 |
| Título | "Entrar", serifa 22/600 |
| Campos | E-mail e Senha, de 48 px (ver [campo](#campo)) |
| Ações | principal grande "Entrar" (18/600); separador "ou" (14 `--theme-muted` entre duas linhas de 1 px `--theme-line`, intervalo de 12); secundário grande "Entrar com chave de acesso"; nota 14 `--theme-muted` sobre o código do autenticador |
| Aviso de teste | fundo `--theme-soft`, raio 12, preenchimento 16 18, intervalo de 10: título 16/600, texto 14, botão de contorno verde "Minha redação quer participar" |
| Rodapé | no fim da página, 14 `--theme-muted`, intervalo de 6: "Use só documentos públicos. Trechos são enviados ao provedor de IA para análise." e os links "Termos de uso · Privacidade · English" |

| Estado | Aparência | Origem |
|---|---|---|
| Padrão | acima | canvas |
| Foco | anel em cada campo, link e botão | canvas |
| Ocupado | "Entrar" vira "Entrando…" em estado ocupado; campos continuam legíveis | derivado |
| Erro | credencial errada: mensagem junto ao campo de senha, sem dizer qual dos dois está errado ("E-mail ou senha não conferem. Confira e tente de novo."); campo com borda de erro | derivado de W11 (regras 4 e 5) |
| Desabilitado | não se aplica | — |
| Vazio | campos vazios com rótulo visível | derivado |

O conteúdo passa da moldura de 844 px; a página rola (ver `referencia/README.md`).

<a id="mapa"></a>

### Mapa de relações

Onde: Mapa de relações. Área do mapa de 960 × 828 à esquerda; painel da ligação selecionada à direita, ocupando o resto. O mapa é SVG com nós em HTML; a lista de adjacência ("Ver como lista") é a leitura acessível.

**Nó**

| Parte | Medida e token |
|---|---|
| Caixa | largura 200, altura mínima 72 (P11.5: o nome pode ocupar duas linhas e a caixa cresce); preenchimento 10 12; intervalo de 10; fundo `--theme-surface`; borda 1 px `--theme-input-line`; raio 12 |
| Ícone do tipo | 36 × 36, `aria-hidden`. Pessoa: círculo `--mapa-pessoa`. Empresa: quadrado com raio 9 em `--mapa-organizacao`. Órgão público: quadrado com raio 3 em `--mapa-orgao` *(novo: ameixa, `#b0508a` no claro e `#d46a9c` no escuro; decisão do dono, P11.4)*. Desenho interno em traço 2, `--theme-on-primary` (branco no claro; escuro: `#172315`, ver `mudancas-de-token.md`, item 10) |
| Texto | nome em `<b>` 16/700; abaixo, tipo e contagem em 14 `--theme-muted` ("Pessoa · 3 documentos", "Órgão público") |

| Estado do nó | Aparência | Origem |
|---|---|---|
| Padrão | acima | canvas |
| Selecionado | borda 2 px `--theme-accent`, sombra 0 4 18 alfa 0,10 (`--sombra-no-selecionado`, *nova*) | canvas ("Construtora Alfa Ltda.") |
| A confirmar | fundo `--theme-warning-bg`, borda 1 px tracejada `--theme-warning`, apoio em `--theme-warning` ("Pessoa · a confirmar") | canvas ("Carlos Prado") |
| Foco | anel de foco na caixa | canvas (regra geral) |
| Ocupado | esqueleto da área inteira enquanto o mapa monta | derivado |
| Erro, desabilitado | não se aplicam ao nó | — |
| Vazio | mapa sem entidades: [estado vazio](#estados) "Nenhuma ligação ainda" com "Adicionar ligação" | derivado de W11 (regra 1) |

**Ligação e rótulo**

| Parte | Padrão | Selecionada | A confirmar, sem documento |
|---|---|---|---|
| Linha | traço 2 px `--mapa-ligacao`, ponta arredondada | traço 4 px `--theme-accent` | traço 2 px `--theme-warning`, tracejado 6 6 |
| Rótulo | pílula de 28 px de altura; fundo `--mapa-rotulo-fundo`; borda 1 px `--theme-input-line`; 14/600 `--theme-text`; ícone de 14 px, traço 2,2; intervalo de 6 | fundo `--theme-accent`, sem borda, texto e ícone `--theme-on-primary` | fundo `--theme-warning-bg`, borda 1 px tracejada `--theme-warning`, texto e ícone `--theme-warning` |

Cada linha é `role="img"` com `aria-label` em frase ("Marta Reis é sócia da Construtora Alfa"). O rótulo leva o tipo da relação e, quando existe, o documento ("Contrato 041/2025", "Servidora até 2023", "Irmãos? A confirmar"). Foco na ligação: traço `--mapa-ligacao-destaque` de 4 px e halo de 14 px (comportamento atual do mapa, mantido).

**Legenda**: faixa de 880 px no pé do mapa, fundo `--theme-surface`, borda 1 px `--theme-line`, raio 12, preenchimento 14 18, intervalo de 24, 14 px; cada item com a marca e o texto, intervalo de 8: Pessoa, Empresa, Órgão público, Ligação com documento, A confirmar, sem documento.

**Painel da ligação selecionada** (`<aside aria-label="Ligação selecionada">`): fundo `--theme-surface`, borda esquerda 1 px `--theme-line`, preenchimento 28, intervalo de 18. Rubrica "LIGAÇÃO SELECIONADA" em `--theme-accent`; título da ligação em serifa 22/600, entrelinha 1,25; selo "✓ 2 evidências conferidas no original"; lista de evidências, cada uma `<a>` com preenchimento 12 0 e bordas de 1 px `--theme-line` entre elas: a citação em serifa 16 e a fonte em 14 `--theme-muted` ("Contrato 041/2025, p. 1 · abrir o original"). Abaixo, o alerta de homônimo: fundo `--theme-warning-bg`, borda 1 px `--theme-warning-line`, raio 12, preenchimento 14 16, intervalo de 8; título 16/600 `--theme-warning`; texto 14; dois secundários de 44 px (preenchimento 0 14, intervalo de 8). No pé (`margin-top:auto`, intervalo de 10): secundário de largura cheia "Anexar outra evidência" e a nota "O mapa organiza o que os documentos dizem. Ele não avalia se é verdade." em 14 `--theme-muted`.

Ações do cabeçalho: "Ver como lista" (secundário) e "Adicionar ligação" (principal). O formulário de "Adicionar ligação" é da Onda 4 (PROD-01) e está em [Formulários dos quadros](#formularios-quadros); as sugestões da IA no mapa, em [Sugestão da IA](#sugestao-ia).

**Enquanto os dados não distinguem empresa de órgão público** *(derivado, 22/11/2026)*. A Mesa só sabe se a entidade é pessoa ou organização. Toda organização usa a forma e a cor de empresa (quadrado de raio 9, `--mapa-organizacao`), mas o texto diz "Organização" (no nó, "Organização · 3 documentos"; na legenda, "Organização"): chamar de empresa um órgão público seria afirmar o que os documentos não dizem. Nada é deduzido do nome. A forma ameixa do órgão público fica pronta e entra, com "Empresa" e "Órgão público" na legenda, quando Produto acrescentar a natureza da organização. Até lá, a legenda é: Pessoa, Organização, Ligação com documento, A confirmar, sem documento, e, se houver ligação pontilhada, "Suporte parcial ou não revisado"; sem descrição da marca entre parênteses. O raio do quadrado da organização é o token de 8 px (`--raio-controle`), o mais perto dos 9 do canvas.

**Rótulo não cobre nó nem outra ligação** *(derivado do canvas, 22/11/2026)*: cada pílula fica sobre o trecho livre da própria ligação, e duas ligações não se cruzam por cima de um rótulo. Se a disposição automática não conseguir, a entidade vai para outra posição do anel.

**Escala e largura** *(derivado, 22/11/2026)*: o mapa é desenhado em escala 1, para o texto nunca ficar abaixo de 14 px. Enquanto os quadros ficam no cartão com abas, o desenho tem 760 px de largura e ocupa a largura do cartão, com a legenda logo abaixo e a lista de pessoas e organizações depois dela. Abaixo de 1024 px o mapa se lê como a lista de ligações, como no celular ([Mapa, 390](#quadros)). O nó tem 200 × 80, o que cabe duas linhas de nome em 16.

**Ícone da ligação pelo tipo livre** *(derivado, 22/11/2026)*: sócio → `relacao-socio`; irmão, pai, mãe, filho, cônjuge → `relacao-parentesco`; cargo, servidor, diretor → `relacao-cargo`; contrato → `contrato`; pagamento → `pagamento`; o resto → `relacao-vinculo`. O texto do tipo fica sempre ao lado e o ícone é `aria-hidden`.

<a id="linha-do-tempo"></a>

### Linha do tempo

Onde: Linha do tempo. Conteúdo com preenchimento 28 40; painel de filtros de 360 px à direita. Continua lista, não gráfico.

| Parte | Medida e token |
|---|---|
| Cabeçalho do ano | "2025" em serifa 36/600, entrelinha 1, espaçamento −0,4; filete de 1 px `--theme-line` até a contagem; contagem em 14 `--theme-muted` ("6 acontecimentos · 5 com documento") |
| Linha do evento | três colunas com intervalo de 20: data (96 px, alinhada à direita, 14 px de recuo no topo, entrelinha 1,2), marco (36 px) e cartão |
| Data | dia e mês em 16/600 ("3 mar"); qualificador em 14 `--theme-muted` ("data exata") ou 14/600 `--theme-warning` ("dia não informado") |
| Marco, data exata | círculo de 36 px `--tempo-marco-exato` com ícone do tipo de 18 px, traço 2, `--theme-on-primary`; 8 px de recuo no topo |
| Marco, data parcial | círculo de 36 px com fundo `--tempo-marco-parcial`, borda 2 px `--tempo-marco-exato` e ícone em `--theme-accent` |
| Trilho | 2 px `--tempo-trilho`, do marco ao próximo evento |
| Cartão do evento | fundo `--theme-surface`, borda 1 px `--theme-line`, raio 12, preenchimento 14 18, intervalo de 16, itens centralizados; 16 px de espaço abaixo. Acontecimento em serifa 18; abaixo, tipo e detalhe em 14 `--theme-muted` ("Pagamento · dois boletins"), ou 14/600 `--theme-warning` quando há alerta de leitura ("Pagamento · página lida por OCR, confira o número"); [selo de fonte isolado](#selo-fonte) à direita |
| Intervalo sem documento | trilho tracejado de 2 px `--theme-warning`; cartão com fundo `--theme-warning-bg`, borda 1 px tracejada `--theme-warning`, raio 12, preenchimento 10 18; texto 16/600 `--theme-warning` ("Cerca de um mês sem nenhum documento"); botão sobre aviso "Virar pergunta ou pedido" |

Ícones de tipo de acontecimento no canvas: documento (assinatura), moeda (pagamento), documento com "+" (aditivo), envelope (pedido de informação).

**Enquanto os dados da Mesa não trazem o que o canvas supõe** *(derivado, 22/11/2026)*:

- Filtro: em vez de Tudo, Pagamentos, Contratos e Pedidos, grupos que não existem nos dados, "Tudo" e uma pílula por tipo de data presente no quadro (fato, emissão, assinatura, publicação, registro, início e fim de vigência, pagamento, recebimento, declarada por fonte), com a mesma medida e `aria-pressed`.
- Ícone do marco pelo tipo de data: assinatura → `contrato`; emissão, publicação, registro e declarada por fonte → `documento`; pagamento → `pagamento`; recebimento, fato e vigência → `data`. O envelope fica só para pedido de informação, para não querer dizer duas coisas.
- O intervalo sem documento não aparece: a lista tem só acontecimentos com data, e um vão entre eles não prova um vão de documentos. Volta quando Produto entregar os documentos do acervo por data; até lá, a linha "Intervalo sem documento" de "COMO LER" também sai.
- O gráfico "Pago ao longo do tempo" não aparece: os acontecimentos não têm valor em reais estruturado, só texto. Volta com esse dado.
- Enquanto os quadros ficam no cartão com abas, "Tipos de data" (rubrica), as pílulas e "COMO LER" (só as duas linhas de marco) ficam acima da lista, e não num painel à direita. As pílulas aparecem sempre, sem ficar recolhidas.
- "Tudo" ligado quer dizer nenhum tipo escolhido: as pílulas dos tipos ficam desligadas. Ligar um tipo desliga "Tudo"; desligar o último volta a "Tudo". Só há as duas aparências do [filtro em pílula](#botao), ligada e desligada.

| Estado do evento | Aparência | Origem |
|---|---|---|
| Padrão | acima | canvas |
| Selecionado | borda 2 px `--theme-accent`, sombra 0 4 18 alfa 0,08 | canvas (pedido de LAI) |
| Foco | anel no cartão quando ele é focável; no selo de fonte sempre | canvas (regra geral) |
| Ocupado | esqueleto de três cartões | derivado de W11 (regra 2) |
| Erro | não se aplica ao evento; falha ao carregar a lista usa o bloco de erro do serviço | derivado |
| Desabilitado | não se aplica | — |
| Vazio | "Nenhum acontecimento com data ainda" e "Adicionar acontecimento" (até a Onda 4, "Fazer uma pergunta"); com filtro ligado, "Nenhum acontecimento com esses tipos de data" e "Mostrar tudo" ([textos](#estados-vazios)) | derivado de W11 (regra 1) |

**Painel de filtros e resumo** (`<aside aria-label="Filtros e resumo">`): largura 360, fundo `--theme-surface`, borda esquerda 1 px `--theme-line`, preenchimento 28 24, intervalo de 20.

- "MOSTRAR" (rubrica `--theme-muted`) e os [filtros em pílula](#botao): Tudo, Pagamentos, Contratos, Pedidos. Um ligado por vez; `aria-pressed`.
- "COMO LER": três linhas com intervalo de 10 entre marca e texto: círculo cheio de 20 px ("Data exata no documento"), círculo vazado de 20 px com borda 2 px ("Data parcial: só mês ou ano"), traço tracejado de 20 px em `--theme-warning` ("Intervalo sem documento").
- Gráfico "Pago ao longo do tempo": caixa com fundo `--theme-background`, raio 12, preenchimento 16 18, intervalo de 6; título 16/600; barras numa faixa de 96 px (8 px de recuo no topo, intervalo de 10), cada uma com o valor escrito em cima (14; o mais recente em 600), raio 4 4 0 0, as anteriores em `--theme-accent-line` e a mais recente em `--theme-accent`; meses abaixo em 14 `--theme-muted`; nota "Em milhões de reais, somados das medições. Cada valor abre o boletim de origem." em 14 `--theme-muted`. O gráfico inteiro é `role="img"` com `aria-label` por extenso ("Pagamentos acumulados: 1,2 milhão em abril, 2,65 milhões em junho e 3,9 milhões em agosto"). Contraste das barras: ver `mudancas-de-token.md`, C55.
- Nota final em 14 `--theme-muted`: "Só entra na linha o que tem documento ou foi marcado por você como a confirmar."

<a id="estados"></a>

### Estados de tela

Onde: toda a Mesa (W11). O wireframe fixa a estrutura e o texto; a aparência abaixo sai dos tokens (o canvas não tem tela final de W11). Bloco base: fundo `--theme-surface`, borda 1 px `--theme-line`, raio 12, preenchimento 16, coluna com intervalo de 8; rubrica em 14 `--theme-muted`; título 16/600; texto 16; ações no pé.

| Estado | Estrutura (W11) | Cores |
|---|---|---|
| Vazio | o que é a coisa e uma ação ("Nenhuma hipótese ainda", "Uma hipótese é uma afirmação que os documentos podem sustentar ou contrariar.", "Criar a primeira"); enquanto o formulário de criar não existe (Onda 4), a ação leva a um destino que existe e diz aonde vai ([textos](#estados-vazios)) | bloco base; ação principal |
| Ocupado, curto (até 10 s) | esqueleto no lugar do conteúdo, que não aparece se a resposta chega em menos de 0,3 s; `aria-busy` | barras de 14 px de altura, raio 4, fundo `--theme-line`, larguras 70 %, 90 % e 50 % |
| Ocupado, longo (OCR, IA) | etapa por extenso ("Lendo a página 2 de 5"), barra, aviso de que pode sair da tela, "Cancelar"; `aria-busy` | barra como o [medidor](#medidor) de 8 px; "Cancelar" secundário |
| Erro que a pessoa resolve | "✕" e o que houve; o que fazer e o que foi preservado; duas ações | fundo `--theme-danger-bg`, borda 1 px `--theme-danger-line`, título `--theme-danger`; ações principal e secundária |
| Erro do serviço | "✕" e o que houve; o que foi guardado e o que não foi cobrado; "Retomar de onde parou" e "Detalhes" (o código interno fica lá) | como o anterior; "Detalhes" abre o código num `<details>`, e o `summary` tem cara de [link](#link): 14/600 `--theme-accent`, sublinhado, altura mínima 44 |
| Limite atingido | "!" e o limite; o que continua funcionando; "Pedir mais ao dono da redação" | fundo `--theme-warning-bg`, borda 1 px `--theme-warning-line`, título `--theme-warning`; ação secundária |
| Redação suspensa *(derivado, 22/11/2026; contrato de contas, 4.3)* | qualquer pedido responde 403 `redacao_suspensa`: o conteúdo da área dá lugar a "! Redação suspensa", "Ninguém desta redação usa a Mesa enquanto a suspensão durar. Nada foi apagado: apurações, documentos e registros continuam guardados." e "Fale com quem administra o serviço."; ação "Sair". Ao abrir a página, quem responde é o aviso simples do próprio servidor | como "Limite atingido": não é erro de ninguém; "Sair" secundário |

<a id="estados-vazios"></a>

**Textos dos vazios dos quadros** *(derivado, 22/11/2026)*. Título no bloco base, texto abaixo, uma ação principal.

| Onde | Título | Texto | Ação até a Onda 4 | Ação depois |
|---|---|---|---|---|
| Hipóteses | Nenhuma hipótese ainda | Uma hipótese é uma afirmação que os documentos podem sustentar ou contrariar. | Fazer uma pergunta | Criar a primeira |
| Tabelas | Nenhuma tabela ainda | Uma tabela conferível reúne números tirados dos documentos, cada um com a sua fonte. | Fazer uma pergunta | Adicionar linha |
| Mapa | Nenhuma ligação ainda | O mapa mostra as pessoas e organizações que os documentos citam e como elas se ligam. | Fazer uma pergunta | Adicionar ligação |
| Linha do tempo | Nenhum acontecimento com data ainda | A linha do tempo reúne os acontecimentos datados que os documentos registram. | Fazer uma pergunta | Adicionar acontecimento |
| Linha do tempo, com filtro | Nenhum acontecimento com esses tipos de data | Nenhum acontecimento tem os tipos de data escolhidos. | Mostrar tudo | a mesma |
| Comparador | Nada para comparar ainda | Esta apuração ainda não tem análise com documentos preservados para comparar. | Fazer uma pergunta | a mesma |
| Conferência do texto | Nenhum texto em conferência | Nenhum texto desta apuração foi enviado para conferência. | Abrir o caderno | a mesma |
| Qualquer quadro, sem apuração | Nenhuma apuração escolhida | Escolha uma apuração no topo da Mesa para ver este quadro. | Escolher apuração | a mesma |

Erro de campo segue o [campo](#campo): 14/400 `--theme-danger`, no formato "o que houve. o que fazer". Pergunta em branco: "Falta a pergunta. Escreva o que quer saber dos documentos." A mensagem fica a 4 px do campo, mesmo quando o campo está dentro de um `<label>` e a mensagem fica fora dele. Cada mensagem fala do campo em que está. Entrada, ativação e primeiro acesso *(derivado, 22/11/2026)*: login em branco, "Falta o login. Use o login da sua conta."; senha em branco, "Falta a senha. Use a senha da sua conta."; nome em branco, "Falta o nome. Escreva o seu nome."; login fora da regra, "Login inválido. Use de 3 a 64 caracteres: letras minúsculas, números, ponto, hífen ou sublinhado, começando por letra ou número."; senha fora do tamanho, "A senha deve ter de 12 a 256 caracteres."; confirmação diferente, "As duas senhas não coincidem. Digite a mesma senha nos dois campos." A resposta do servidor (senha errada, bloqueio, rede) fica na caixa de aviso do formulário.

Erro usa as cores de erro e aviso usa as de aviso, nunca trocadas (W11, regra 6). Mudança de estado é anunciada a leitor de tela (`role="status"` para ocupado e concluído, `role="alert"` para erro; W11, regra 9).

<a id="dialogo"></a>

### Diálogo de confirmação

> **Derivado, aprovado pelo dono em 21/11/2026.** O canvas não desenha diálogo; W11 (regra 8) e UX-16 pedem um. Pranchas em [`novas/telas/`](novas/telas/): `dialogo-simples-*`, `dialogo-destrutivo-*` e `dialogo-campo-*`, em claro e escuro, 1440 e 390 px. A tela atrás do véu é só contexto.

Substitui os oito `confirm()` nativos (UX-16) e segue os dois diálogos que a Mesa já tem para a lixeira (`interface/index.html:275-290`): rubrica, título, texto, "Cancelar" com `autofocus` e a ação.

| Parte | Medida e token |
|---|---|
| Elemento | `<dialog>` aberto com `showModal()`; `role="alertdialog"`, `aria-modal="true"`, `aria-labelledby` no título e `aria-describedby` no texto |
| Véu | tela inteira em `--theme-backdrop`; a página atrás fica `inert` |
| Caixa | largura 480 (no celular, a largura da tela menos 16 px de cada lado: 358 em 390); centrada nos dois eixos; fundo `--theme-surface`; raio 12; preenchimento 24; coluna com intervalo de 16; sombra `--sombra-dialogo` *(nova: `0 12px 40px` alfa 0,18 no claro; `#00000099` no escuro)* |
| Rubrica (opcional) | 14/600, maiúsculas, `--theme-muted` ("MOVER PARA A LIXEIRA", como hoje) |
| Título | serifa 22/600, entrelinha 1,25; nomeia a ação, e o item quando há um |
| Texto | 16; a nota de consequência em 14 `--theme-muted` |
| Ações | à direita, intervalo de 8, com quebra de linha, 8 px de folga acima; "Cancelar" (secundário) antes da ação |

| Variante | Ação | Foco inicial e botão padrão (Enter) | Exemplo na prancha |
|---|---|---|---|
| Simples | principal | a ação | "Gerar novo link de ativação?" (`piloto.js:143`) |
| Destrutiva, com o nome do item | variante destrutiva do canvas (contorno e texto de erro) | "Cancelar" | "Mover “Vila Serena — contrato de pavimentação” para a lixeira?" (`index.html:275-277`) |
| Com campo | destrutiva, desabilitada até o nome digitado conferir | o campo; Enter só confirma com a ação habilitada | "Apagar definitivamente", com a tabela do que sai e "Digite «nome» para confirmar" (`index.html:278-290`, `gerenciar.js:154-156`) |

Comportamento: o foco fica preso no diálogo (Tab e Shift+Tab circulam entre os controles); Esc fecha como "Cancelar"; ao fechar, o foco volta ao controle que abriu o diálogo; clique no véu não fecha (decisão do dono, P12.5).

| Estado | Aparência | Origem |
|---|---|---|
| Padrão | acima | derivado |
| Foco | anel de foco do canvas no controle focado; nas pranchas, na ação (simples), em "Cancelar" (destrutiva) e no campo (com campo) | canvas (anel) e derivado |
| Ocupado | a ação troca o rótulo pelo gerúndio ("Apagando…", como `gerenciar.js:140`), `aria-busy` no diálogo, "Cancelar" desabilitado até a resposta. Decisão do dono (P12.5): se "Apagar definitivamente" puder demorar, vira espera longa de W11 (barra com etapa, "Cancelar" ativo, regra 3) | derivado |
| Erro | mensagem em 14 `--theme-danger` acima das ações, com `role="alert"` (o `#apagar-erro` de hoje), no formato de W11 | wireframe W11 (regra 4) |
| Desabilitado | a ação destrutiva da variante com campo, até o nome conferir (variante "Indisponível" do botão) | canvas (botão) |
| Vazio | não se aplica | — |

Os oito `confirm()` de hoje e a variante de cada um (rótulos de ação aprovados pelo dono, P12.6):

| Onde | Texto de hoje | Variante | Ação proposta |
|---|---|---|---|
| `apuracao.js:57` | "Há alterações não salvas no Caderno. Sair sem salvar?" | destrutiva | "Sair sem salvar" |
| `apuracao.js:413` | "Há alterações não salvas. Descartar essas alterações?" | destrutiva | "Descartar alterações" |
| `apuracao.js:542` | "Excluir esta nota do caderno? As fontes serão preservadas." | destrutiva, com o nome da nota | "Excluir nota" |
| `apuracao.js:589` | "Recarregar descarta o texto deste editor. Continuar?" | destrutiva | "Recarregar e descartar" |
| `codex.js:582` | "Encerrar o serviço local? As execuções ativas serão interrompidas. …" | destrutiva | "Encerrar o serviço" |
| `experiencia.js:298` | "Há texto ou alterações não salvas. Descartar e fechar?" | destrutiva | "Descartar e fechar" |
| `piloto.js:135` | "Desativar esta conta? A pessoa sai na próxima ação." | destrutiva, com o nome da pessoa | "Desativar conta" |
| `piloto.js:143` | "Gerar novo link de ativação? A senha atual deixa de valer e as sessões abertas são encerradas." | simples | "Gerar novo link" |

**"Apagar definitivamente" na Mesa** *(derivado, 22/11/2026)*: antes da tabela, enquanto o alcance chega, "Calculando o que será apagado…" em 14 `--theme-muted`; quando ele chega, o foco passa de "Cancelar" ao campo. Abaixo da tabela, o aviso de backup que o servidor manda, em 14 `--theme-muted`. "Digite «nome» para confirmar" em 16/400, só o nome em 600; o texto do campo em 16/400. Na tabela, número e unidade nunca se separam ("52,3 MB", "28 arquivos"); no celular, o nome da categoria pode quebrar. Recusa do servidor: o texto inteiro no lugar do erro, e o foco volta ao campo. A resposta é rápida (a quarentena do servidor), então o ocupado é o curto, "Apagando…", sem "Cancelar" ativo; a espera longa de P12.5 não se aplica. Apagamento pela metade (o servidor marca o item como pendente): na lixeira, "Restaurar" e "Apagar definitivamente…" ficam indisponíveis e o texto do servidor aparece inteiro junto ao item, no aviso em linha da Mesa (`.notice`: fundo `--theme-warning-bg`, filete esquerdo `--theme-notice-line`, texto `--theme-warning`, `role=status`), o mesmo de "Limitações das fontes"; no diálogo, a razão vem como linha de estado em 14 `--theme-muted`, sem tabela, com o campo e a ação indisponíveis. Não é erro: nunca nas cores de erro.

"Desfazer quando possível" (W11, regra 8): excluir nota hoje não oferece desfazer (UX-16). Decisão do dono (P12.7): sem "Desfazer" por enquanto.

<a id="dialogo-senha"></a>

**Com senha: operações sensíveis** *(derivado, 22/11/2026; contrato de contas, 5.15)*. Quarta variante do diálogo, com as mesmas partes, o mesmo foco preso, Esc e véu. Entre o texto e as ações vem um campo:

| Parte | Medida e token |
|---|---|
| Rótulo | "Sua senha", 16/600 |
| Campo | o [campo de senha](#campo), com "Mostrar": 44 px no desktop, 48 no celular; `type="password"`, `autocomplete="current-password"`; aceita colar e gerenciador de senhas (W08, regra 4) |
| Apoio | abaixo do campo, 14 `--theme-muted`: "A senha com que você entra na Mesa." Quando há erro, a mensagem de erro vem primeiro, a 4 px do campo, e o apoio depois dela (ressalva sobre `b5b389c`) |
| Ação | desabilitada com o campo vazio; Enter envia quando ela está habilitada |

Foco inicial no campo. A senha vai só naquele pedido (campo `senha`; `senha_atual` na troca de senha): a Mesa não a guarda, nem entre tentativas, e limpa o campo ao fechar o diálogo. Respostas:

| Resposta | O que a tela faz |
|---|---|
| 403 `senha_atual_incorreta` | erro no campo, "Senha incorreta. Confira e tente de novo."; o campo é limpo e recebe o foco |
| 403 `senha_necessaria` | não deveria chegar com o diálogo aberto; se chegar, o diálogo continua aberto com o texto do servidor ("Digite a sua senha para confirmar.") no lugar do erro |
| 429 `bloqueado` | erro do diálogo, `role="alert"`: "Muitas senhas erradas seguidas. Por 15 minutos, as ações que pedem a senha ficam bloqueadas para a sua conta; o resto da Mesa continua." A ação fica indisponível; sobra "Cancelar" |
| 400 `ultimo_dono` e as demais recusas | o texto do servidor no erro do diálogo ("A redação precisa de ao menos um dono ativo.", "Conta não encontrada."); ao fechar, a lista recarrega |

A Mesa pede a senha antes de enviar quando sabe que a operação pede (tabela abaixo). Se uma operação responder 403 `senha_necessaria` sem a Mesa ter pedido, o diálogo abre com o título da tabela e reenvia o mesmo pedido com a senha. A Mesa nunca reenvia sozinha uma senha digitada antes.

| Operação | Onde | A Mesa pede antes quando | Título | Ação |
|---|---|---|---|---|
| `conta-senha-trocar` | Minha conta | sempre: é o campo "Senha atual" do diálogo [Trocar senha](#minha-conta) | Trocar senha | "Trocar senha" (principal) |
| `equipe-papel` | Equipe, papel da pessoa | o papel atual ou o novo é dono | "Tornar Ana Lima dono da redação?" ou "Mudar o papel de Rui Castro para Editor?" | "Tornar dono" (principal) ou "Mudar papel" (destrutiva) |
| `equipe-desativar` | Equipe, Gerenciar | a pessoa é dono; sem ser dono, é a destrutiva sem senha de P12.6, "Desativar conta" | "Desativar a conta de Rui Castro?" | "Desativar conta" (destrutiva) |
| `equipe-remover` | Equipe, Gerenciar | sempre | "Remover Ana Lima da redação?" | "Remover da redação" (destrutiva) |
| `ia-config-salvar` | Configurações | a sessão tem conta e o pedido grava ou remove a chave; trocar só provedor ou modelo nos modos locais segue como hoje | "Salvar a chave de IA?" ou "Remover a chave de IA?" | "Salvar chave" (principal) ou "Remover chave" (destrutiva) |
| `lixeira-apagar` | Apagar definitivamente | sempre, no mesmo diálogo: o campo "Sua senha" fica abaixo do campo do nome, e a ação só se habilita com o nome conferido e a senha preenchida. Senha errada põe o erro no campo da senha e o foco nele; o nome digitado fica | o de hoje | "Apagar definitivamente" |

Textos: tornar dono, "Dono vê todas as apurações da redação, administra a equipe e apaga de vez. Vale na próxima ação de Ana Lima."; rebaixar dono, "Rui Castro deixa de administrar a redação e passa a ver só as apurações de que participa. Vale na próxima ação."; desativar, "A pessoa sai na próxima ação e as perguntas em curso dessa conta param. As apurações e os registros ficam; reativar devolve o acesso."; remover, "A conta é excluída: a pessoa perde o acesso, sai de todas as apurações e não pode ser reativada. Notas, revisões e conversas ficam com a redação. O nome continua nos registros já gravados e nos backups, que não podem ser reescritos." (decisão 10 do contrato); salvar a chave, "A chave fica guardada no servidor. A Mesa mostra só os quatro últimos caracteres."; remover a chave, "Sem ela, as perguntas deixam de usar esta chave."

Com a E3 de Contas entram mais quatro, cada uma na sua seção: `equipe-convidar` como dono ([convites](#convites)), `equipe-recuperar` e `equipe-recuperar-confirmar` ([recuperar](#recuperar)) e `conta-email-trocar` ([Minha conta](#minha-conta)). As que ainda não existem (`conta-fator-*`, `conta-excluir`) ficam fora da tela até existirem ([exceções](#contas-excecoes)).

<a id="icones"></a>

### Ícones

Os ícones do canvas são SVG em linha, `viewBox="0 0 24 24"`, sem preenchimento, pontas e junções arredondadas, `aria-hidden="true"` (o texto ao lado diz o que é):

| Ícone | Traço | Tamanho | Onde |
|---|---|---|---|
| ✓ (conferido, salvo, leitura concluída) | 2,5 | 16 | Conferir achado, celular |
| Menu (três linhas) | 2 | 22 | celular |
| Seta para cima (enviar) | 2,5 | 22 | celular |
| Documento, moeda, documento com "+", envelope | 2 | 18 | linha do tempo |
| Elo (sócio), maleta (cargo), ramificação (vinculada), duas pessoas (parentesco), documento (contrato) | 2,2 | 14 | rótulos do mapa |
| Pessoa, prédio (empresa), fachada com colunas (órgão público) | 2, em `viewBox` 36 | 36 | nós do mapa |

Os ícones atuais da Mesa (`interface/desktop.js:198-214`) usam traço 1,6 em 18 px, e 15 px em alguns lugares (`.mesa-icon` em `style.css`). Os outros ícones do canvas (✓, menu, seta de enviar) ficam como estão desenhados; o conjunto do Vlado, abaixo, cobre as entidades, os documentos, os tipos de relação e de acontecimento e os três sinais de estado que não existem nas fontes da Mesa.

<a id="conjunto-de-icones"></a>

### Conjunto de ícones do Vlado

Arquivos em [`icones/`](icones/), um SVG por ícone; prancha de conferência em [`icones/prancha-icones.png`](icones/prancha-icones.png) (claro e escuro, 16, 24 e 32 px, mais os ícones nos contextos do canvas). Não integrados em `interface/`: quem integra é o Frontend.

**Desenho**, igual ao dos ícones atuais da Mesa:

- grade de 24 × 24 (`viewBox="0 0 24 24"` fixo), desenho dentro da área de 3 a 21;
- um único `<path>` por ícone, sem `<circle>` nem `<rect>`: o `d` entra direto no mapa `icons` de `desktop.js`, que cria um só `path` por ícone;
- traço único, `stroke="currentColor"`, `fill="none"`, pontas e junções arredondadas;
- traço de 1,6 no arquivo, o mesmo de `.mesa-icon`; o traço fica no `<svg>`, então o CSS do contexto pode trocá-lo;
- sem texto embutido, sem `<title>`, sem metadados, sem cor fixa.

**Espessura por contexto** (decisão do dono em 21/11/2026, P11.9: traço variável por contexto). O arquivo traz 1,6 (o peso dos ícones atuais). Onde o canvas desenha o ícone, vale o traço do canvas, aplicado pelo CSS daquele contexto:

| Contexto | Tamanho | Traço | Peso na tela | Origem |
|---|---|---|---|---|
| Ícone de interface (lista, botão, cabeçalho) | 16 ou 18 | 1,6 | 1,1 a 1,2 px | Mesa atual |
| Rótulo de ligação no mapa | 14 | 2,2 | 1,3 px | canvas |
| Marco da linha do tempo (dentro do círculo de 36 px) | 18 | 2 | 1,5 px | canvas |
| Ícone de entidade dentro do nó do mapa (forma de 36 px) | 24 | 2 | 2 px | canvas |

**Os ícones**

| Ícone | Arquivo | Uso | Tamanhos | Rótulo acessível quando está sozinho | Origem |
|---|---|---|---|---|---|
| Pessoa | `pessoa.svg` | nó de pessoa no mapa; legenda; listas de entidades | 24 no nó; 16 a 24 fora dele | "Pessoa" | canvas (`Mapa.dc.html`, grade de 36 transladada em −6, −6) |
| Empresa | `empresa.svg` | nó de empresa; legenda | 24 no nó; 16 a 24 | "Empresa" | canvas (transladada em −6, −6) |
| Órgão público | `orgao-publico.svg` | nó de órgão público; legenda | 24 no nó; 16 a 24 | "Órgão público" | canvas (transladada em −6, −6) |
| Documento | `documento.svg` | área Documentos; listas de documentos | 16 a 18 | "Documento" | Mesa atual (`desktop.js:201`, `documentos`) |
| Contrato | `contrato.svg` | ligação de contrato e de subcontrato no mapa; acontecimento de assinatura | 14 no mapa; 18 no marco; 16 a 24 | "Contrato" | canvas (`Mapa.dc.html`, `Tempo.dc.html`) |
| Pagamento | `pagamento.svg` | acontecimento de pagamento; ligação de pagamento no mapa | 18 no marco; 14 no mapa | "Pagamento" | canvas (`Tempo.dc.html`; o círculo virou arco, ver abaixo) |
| Data | `data.svg` | campo de data; acontecimento sem tipo; filtro por período | 16 a 18 | "Data" | **derivado, aprovado pelo dono em 21/11/2026** |
| Lacuna | `lacuna.svg` | lacuna onde o canvas não desenha o sinal (listas, legenda, quadros) | 16 a 24 | "Lacuna" | **derivado, aprovado pelo dono em 21/11/2026** (do sinal "?" do canvas) |
| Sem suporte | `sinal-sem-suporte.svg` | no lugar do caractere ✕: selo "Sem suporte", título de erro (W11), arquivo não lido (W02) | do tamanho do texto (14 a 16) | "Sem suporte" ou "Erro", conforme o lugar | **derivado, aprovado pelo dono em 21/11/2026** (do ✕ do canvas) |
| Corrigido | `sinal-corrigido.svg` | no lugar do caractere ✎: célula corrigida (W06) | do tamanho do texto | "Corrigido por você" | **derivado, aprovado pelo dono em 21/11/2026** (do ✎ do canvas) |
| Parcial | `sinal-parcial.svg` | no lugar do caractere ◐: leitura por OCR (W02), etapa em andamento (W03), convite pendente (W09) | do tamanho do texto | "Lida por OCR", "Em andamento" ou "Pendente", conforme o lugar | **derivado, aprovado pelo dono em 21/11/2026** (do ◐ do canvas) |
| Sócio | `relacao-socio.svg` | ligação societária no mapa | 14 | "Sócio" ou "Sócia" | canvas |
| Parentesco | `relacao-parentesco.svg` | ligação de parentesco no mapa | 14 | "Parentesco" | canvas |
| Cargo | `relacao-cargo.svg` | ligação de cargo ou emprego ("Servidora até 2023") | 14 | "Cargo" | canvas |
| Vínculo | `relacao-vinculo.svg` | ligação institucional ("Vinculada") | 14 | "Vínculo institucional" | canvas |
| Aditivo | `evento-aditivo.svg` | acontecimento de termo aditivo | 18 no marco | "Aditivo" | canvas |
| Pedido de informação | `evento-pedido.svg` | acontecimento de pedido de LAI ou protocolo | 18 no marco | "Pedido de informação" | canvas |

Tipos de relação pedidos e o ícone de cada um: sócio → `relacao-socio`; contrato → `contrato`; pagamento → `pagamento`; parentesco → `relacao-parentesco`. O canvas usa ainda cargo e vínculo, que também estão no conjunto. Tipos de acontecimento do canvas: assinatura → `contrato`; pagamento → `pagamento`; aditivo → `evento-aditivo`; pedido de informação → `evento-pedido`.

**Rótulo acessível.** Ao lado de texto que já diz o tipo (rótulo da ligação, nome do nó com "Pessoa · 3 documentos", legenda), o ícone leva `aria-hidden="true"`. Sozinho, sem texto visível, leva `role="img"` e o `aria-label` da tabela, e o elemento que o contém tem nome acessível. O ícone nunca é o único sinal de um tipo: no mapa somam-se a forma, a cor e o rótulo (parte E do plano).

**Composições do canvas**, conferidas na prancha:

- **Nó de entidade:** forma de 36 px (pessoa: círculo; empresa: quadrado com raio 9; órgão público: quadrado com raio 3) na cor do tipo, com o ícone de 24 px centrado (6 px de margem nos quatro lados, `transform: translate(6px, 6px)` num `<g>` ou um `<svg>` de 24 px posicionado em 6, 6), traço 2, em `--theme-on-primary`. Assim o desenho fica exatamente onde o canvas o põe: os três ícones foram transladados em −6, −6 a partir da grade de 36 do canvas.
- **Rótulo de ligação:** ícone de 14 px, traço 2,2, na cor do texto do rótulo.
- **Marco da linha do tempo:** ícone de 18 px, traço 2: em `--theme-on-primary` no marco cheio; em `--theme-accent` no marco vazado.
- **Lacuna no achado e no celular:** fica o sinal do canvas (círculo cheio com "?" em texto 700). `lacuna.svg` é para os lugares sem desenho.

**Fidelidade ao canvas**, medida por `icones/ferramentas/gerar_icones.cjs` (resultado em `icones/ferramentas/comparacao-canvas.json`): cada ícone que o canvas desenha foi rasterizado em 96 px, com traço 2, no original do canvas (com a translação registrada) e no arquivo novo.

- **Contrato, sócio, parentesco, cargo, vínculo, aditivo, pedido, pessoa, empresa e órgão público:** 0 pixel diferente.
- **Pagamento:** 344 pixels diferem só na suavização da borda; nenhum passa de 83/255 de diferença de alfa, e nenhum tem traço num lado e não no outro (`pixelsForaDaForma: 0`). A causa é o `<circle>` do canvas ter virado arco dentro do único `path`. Três escritas diferentes do arco dão o mesmo resultado entre si, e só o primitivo `<circle>` é rasterizado de outro jeito.

**Derivados, aprovados pelo dono em 21/11/2026 (P11.10):** `data` (calendário: corpo de 16 × 15, linha de cabeçalho e duas argolas); `lacuna` (círculo de raio 9 com o ponto de interrogação em traço, versão vetorial do sinal "?" do canvas); `sinal-sem-suporte` (✕ em dois traços de 10 × 10), `sinal-corrigido` (lápis) e `sinal-parcial` (círculo de raio 8 com metade hachurada), que substituem os caracteres ✕, ✎ e ◐: nenhum dos três existe nas fontes da Mesa (`mudancas-de-token.md`, item 12), e na referência eles saíram de uma fonte do sistema. Os sinais ✓ e ○ existem no Source Sans 3 e continuam como texto. Os três derivados de sinal vão ao lado do texto, então levam `aria-hidden="true"`; o rótulo da tabela vale só quando aparecem sozinhos. `documento` não é derivado: é o ícone `documentos` da Mesa atual, sem mudança.

**Tema escuro.** Os ícones herdam a cor do texto (`currentColor`) e passam com ela (texto sobre superfície: 12,40:1). Nas formas coloridas do mapa, o ícone usa `--theme-on-primary` (`#172315`): branco sobre a esmeralda do escuro daria 2,97:1 (`mudancas-de-token.md`, E44). A forma do órgão público é a ameixa (decisão do dono, P11.4): ícone branco sobre `#b0508a` no claro dá 4,82:1 (C64); ícone escuro sobre `#d46a9c` no escuro dá 4,92:1 (E50).

---

<a id="telas-derivadas"></a>

## Telas derivadas (fase 3)

> **Derivado, aprovado pelo dono em 21/11/2026** (as 27 pranchas da fase 3). Pranchas em [`novas/`](novas/README.md), renderizadas pelo mesmo processo da referência, com a faixa "Derivado · aprovado pelo dono em 21/11/2026" abaixo de cada uma, já com as decisões P11 e P12 aplicadas. Os componentes são os da especificação acima; esta seção diz só o que muda em cada largura e tema.

<a id="escuro-desktop"></a>

### Tema escuro no desktop

Pranchas: `conferir-achado-escuro-1440`, `visao-geral-escuro-1440`, `design-system-revisado-escuro-1440`.

Método: a mesma prancha do canvas, com cada cor do claro trocada pelo valor escuro do mesmo token semântico (a tabela está em `novas/ferramentas/gerar_novas.cjs`, `CLARO_ESCURO`, e segue `design-system.md` e `mudancas-de-token.md`). Estrutura, texto e medida não mudam. Ficam como estão:

- a folha do documento no painel do original: papel branco com o texto do documento, nos dois temas (como `--pdf-pagina`);
- as amostras de cor do design system: mostram a paleta, então mantêm as cores que nomeiam.

O que o escuro decide e o canvas não mostra:

| Elemento | Escuro | Contraste | Observação |
|---|---|---|---|
| Item ativo da barra lateral | fundo `--theme-accent` (`#a8c79d`), texto `--theme-on-primary` (`#172315`) | 8,79:1 | Segue o botão principal do celular escuro do canvas. Decisão do dono (P12.2): verde cheio. O CSS de hoje usa fundo `--theme-active`, texto verde e uma barra interna de 3 px (`style.css:174`), que o Frontend troca. |
| Contador no item ativo | pílula `#172315` com texto `#a8c79d` | 8,79:1 | Token `--nav-contador-ativo-fundo` no escuro. |
| "1 vence" na barra lateral | `--theme-warning` (`#e6bc7a`) sobre `#121714` | 10,22:1 | |
| Botão destrutivo | borda `#a76e66` sobre `#202823` | 3,65:1 | Mínimo de 3:1 para borda de controle. |
| Barra de progresso | `#a8c79d` sobre a trilha `#3c4940` | 5,10:1 | |
| Sombras | `#00000033` e `#00000066` (sombras da noite) | — | |

Os pares das pranchas estão na tabela de contraste de `mudancas-de-token.md`; os medidos para elas são E55 a E57, que passam. Dos pares do escuro que não passam naquela tabela, só a divisória (E51, decorativa) aparece nestas pranchas: a borda de campo antiga (E36, E52) e o ícone branco sobre a esmeralda (E44) não são usados.

<a id="tablet"></a>

### Tablet, 1024 px

Pranchas: `conferir-achado-{claro,escuro}-1024`, `conferir-achado-gaveta-aberta-{claro,escuro}-1024`, `visao-geral-{claro,escuro}-1024`.

**Gaveta (UX-11).** A barra lateral sai da tela e vira gaveta. Fechada por padrão. O cabeçalho ganha, no início, o botão "Abrir menu" (só ícone, 44 × 44, ícone de menu do canvas). Aberta, a gaveta é a barra lateral inteira (256 px, P15.7; mesmos itens, cota e perfil), sobre o conteúdo, com o véu `--theme-backdrop` e sombra `--sombra-dialogo`; o conteúdo atrás fica `inert`; o foco vai para o primeiro item; Esc ou um item escolhido fecham a gaveta e devolvem o foco ao botão. A prancha mostra a estrutura; o movimento de abrir não está desenhado.

Por que gaveta em 1024 px: com a barra fixa de 232 px, a tela de conferir ficaria com 272 px para a lista de achados ao lado do painel do original (com 256 px, 248). Isso muda a faixa de 1024 a 1279 px da tabela de quebras (`mudancas-de-token.md`, item 6), que dizia "barra lateral fixa". Decisão do dono (P12.1): gaveta em toda largura abaixo de 1280 px.

**Conferir achado, 1024.** Cabeçalho de 64 px: "Abrir menu", "Apuração" sobre o nome, "Salvo às 14h32" e "Exportar apuração" (o cabeçalho da apuração do canvas, mais o botão de menu). Lista com o preenchimento do desktop (28 32). Painel do original com 440 px (no lugar de 520) e folha com preenchimento 32 36. As ações do achado aberto quebram linha quando não cabem.

**Visão geral, 1024.** Cabeçalho de 64 px: "Abrir menu", marca "Vlado." (serifa 28/600, entrelinha 1) e, à direita, "Cota do mês" com o valor (a cota sai da barra lateral, que agora está na gaveta). Conteúdo com preenchimento de 32 px; a mesma estrutura do desktop: título de 36 px com os dois botões à direita, cartão do próximo passo, quatro contagens em linha, perguntas e linha do tempo em duas colunas.

<a id="celular-telas"></a>

### Celular, 390 px

Pranchas: `conferir-achado-{claro,escuro}-390`, `conferir-achado-original-{claro,escuro}-390`, `visao-geral-{claro,escuro}-390`.

Cabeçalho: o do celular do canvas (60 px: "Abrir menu", "Apuração" sobre o nome cortado com reticências, cota à direita). Margens de 16 px. A barra lateral é a mesma gaveta do tablet, com a largura de 256 px.

<a id="cabecalho-celular"></a>

**Cabeçalho do celular, abaixo de 720 px** (aceito pelo Maestro em 23/11/2026, sobre o que entrou com o botão "Configurações" em `29aeafa`). A 375 px, o cabeçalho tinha o menu, o seletor e "Configurações", e o seletor ficava cortado sem reticências ("Escolha uma a"). Abaixo de 720 px, o cabeçalho leva só três coisas:

- **"Abrir menu"**, o botão só com o ícone;
- **"Apuração" sobre o nome:** o seletor ocupa o espaço que sobra (`min-width: 0`, `flex: 1`), e o nome é cortado com reticências (`text-overflow: ellipsis`, `white-space: nowrap`, `overflow: hidden`). O nome inteiro continua nas opções do seletor;
- **a cota à direita:** "R$ 18,40 de 50", em 14 `--theme-muted`, sem quebrar, como na tabela dos [cabeçalhos](#cabecalhos). Ela segue as regras do cartão da cota: some sem a rota ou sem sessão e vira "! Cota esgotada" com o teto atingido. O cabeçalho mostra o mesmo bloco que o [cartão da cota](#barra-lateral) escolhe, o de menor saldo, só no formato curto. Quando for a cota da instalação, o texto é "Cota da instalação R$ 40,00 de 200" (esgotada, "! Cota da instalação esgotada"). A parte da chave própria ("dos quais…" e "Chave própria da redação") não entra no cabeçalho e fica só no cartão. Assim o administrador vê no cabeçalho o mesmo número da barra (C1 da Coruja sobre `3d47814`).

**"Configurações" sai do cabeçalho e vai para a gaveta**, no grupo em que Idioma, Tema e Sair já entram no celular (`.mesa-drawer-controls`, logo abaixo das áreas e acima do cartão da cota e do cartão da pessoa), como o primeiro do grupo. Ela continua aparecendo só para quem tem a capacidade (`data-requer="ia-config"`). A partir de 720 px, volta ao cabeçalho, no lugar de hoje.

Prova: Visão geral e Minha conta a 320, 375 e 430 px, nos dois temas, com um nome de apuração longo, e a gaveta aberta a 375 px.

**Conferir achado, 390.** Coluna única: título de 28 px com o progresso, caixa "Sua pergunta", lista de achados. No achado aberto, as ações ficam empilhadas em botões de 48 px de largura cheia, nesta ordem: "Ver o trecho no original" (secundário), "Confere com o original" (principal), "Precisa de ajuste" (secundário), "Sem suporte" (recusa).

**Original no celular.** "Ver o trecho no original" abre o original numa camada de tela cheia (`conferir-achado-original-*-390`): cabeçalho com "Achados" (volta à lista, devolvendo o foco ao achado) e o selo "Lida por OCR"; nome do documento e página; a folha; zoom e "Abrir o original em nova aba"; no pé, o achado em conferência com as três ações, para conferir sem voltar. Aprovado pelo dono (P12.3).

**Visão geral, 390.** Coluna única com intervalo de 16: rubrica de data; título da apuração em serifa 28/600, entrelinha 1,2 (36 px quebraria em três linhas; decisão do dono, P12.4: 28 px, desde que o título longo caiba em duas linhas; acima disso, a segunda linha termina em reticências e o nome inteiro fica no seletor de apuração); "Trocar de apuração" e "Nova apuração" lado a lado, metade da largura cada; cartão do próximo passo em coluna, com preenchimento 20 e a chamada "Conferir agora" de 48 px; contagens em grade de 2 × 2, intervalo de 12; "Últimas perguntas" e "Linha do tempo documentada" uma abaixo da outra.

**Diálogos no celular:** ver [diálogo de confirmação](#dialogo); a caixa ocupa a largura menos 16 px de cada lado.

<a id="telas-aprovadas"></a>

## Áreas sem tela final, aprovadas pelo dono

> **Derivado, aprovado pelo dono em 21/11/2026** (P14, P14b, P15 e P16). Pranchas em [`aprovacao/`](aprovacao/LEIA-ME.md), cada uma com a faixa verde "Derivado · aprovado pelo dono em 21/11/2026", em 1440 e 390 px, nos dois temas, já com as decisões P11, P12 e a barra de 256 px (P15.7). O canvas não tem tela final destas áreas: a estrutura vem dos wireframes (W02, W04 a W07) e a aparência sai dos componentes acima. As medidas são as das pranchas depois do arredondamento para a grade de 4 px (P11.8). O escuro é a mesma tela com os tokens do escuro. Abaixo de 1280 px a barra lateral vira gaveta ([tablet](#tablet)), e no celular o cabeçalho é o do celular do canvas.

Padrões que se repetem nestas telas:

| Padrão | Medida e token | Onde |
|---|---|---|
| Painel da direita | largura 360 (340 no caderno); fundo `--theme-surface`; borda esquerda 1 px `--theme-line`; preenchimento 28 24 (28 no caderno); coluna com intervalo de 16; rubrica em 14/600 maiúsculas, `--theme-accent` ou `--theme-muted` | caderno, hipóteses, tabelas, pedidos e prazos |
| Cartão aberto ou selecionado | borda 2 px `--theme-accent` e `--sombra-flutuante` | hipótese aberta, pedido aberto, primeira diferença no celular |
| Item a resolver | borda 1 px tracejada `--theme-warning`, fundo `--theme-warning-bg`, texto e origem em 14 `--theme-muted` | lacunas, "falta" das hipóteses, intervalo sem documento |
| Ação de lacuna | botão de contorno `--theme-warning`, fundo `--theme-surface`, texto `--theme-warning`: "Virar pergunta ou pedido" | hipóteses, linha do tempo no celular |
| Título da área | serifa 28/600, entrelinha 1,2, com a contagem em 14 `--theme-muted` alinhada pela base | caderno, documentos, pedidos e prazos |
| Título dentro dos quadros | serifa 22/600 com a contagem em 14 `--theme-muted` | hipóteses, tabelas, comparador |

<a id="caderno"></a>

### Caderno (W04)

Pranchas: `aprovacao/caderno/proposta-*` (modo Conferir, P14.1 e P14.5), `proposta-trechos-*` (P14b.6 e o sinal "revisada", P14b.8) e `proposta-escrever-*` (P14b.7).

| Parte | Medida e token |
|---|---|
| Moldura, 1440 | barra lateral; [cabeçalho da apuração](#cabecalhos) com "Salvo às" à direita; três colunas: esquerda de 272 px (preenchimento 28 16 28 32), centro flexível (preenchimento 28 32, borda esquerda 1 px `--theme-line`) e painel da direita de 340 px |
| Coluna da esquerda | "Nova nota" (secundário, largura cheia); seletor "Notas \| Trechos (n)"; a lista escolhida |
| Seletor segmentado | `role="group"`; fundo `--theme-reading`, raio 12, preenchimento 4, intervalo 4; botões de 40 px, raio 8, `aria-pressed`; o pressionado tem fundo `--theme-surface`, `--sombra-cartao` e peso 600 |
| Nota na lista | `<a>`, preenchimento 12, raio 8; a atual (`aria-current`) com fundo `--theme-soft`, nome 600 e "versão 3 · 2 a resolver" em 14 `--theme-muted` |
| Trecho com fonte (P14b.6) | `<label>` com caixa de seleção de 20 px (`accent-color: --theme-accent`); fundo `--theme-surface`, borda 1 px `--theme-line` (selecionado: `--theme-accent`), raio 12, preenchimento 12 16, intervalo 12; tipo ("Trecho", "Achado do jornalista", "Anotação") em 14/600 `--theme-muted`, citação em serifa 16, fonte e autoria em 14 `--theme-muted`. Abaixo: "2 selecionados (até 20)"; "Inserir no texto" (largura cheia), "Cruzar" e "Perguntar" em grade de duas colunas, intervalo 8, todos secundários; "Registrar trecho com fonte" (principal, largura cheia), que abre o formulário de hoje |
| Topo do centro | título da nota em serifa 28/600; "Nova versão" e "Exportar" (secundários) à direita; abaixo, o par de pílulas "Conferir afirmações" e "Escrever" (`aria-pressed`; ativa verde cheio com texto `--theme-on-primary` 600, inativa com borda `--theme-input-line`) e, à direita, a contagem em 14 `--theme-muted` ("5 afirmações: 3 com fonte · 1 revisada · 1 exagero · 1 sem fonte") |
| Texto no modo Conferir | serifa 18 `--theme-text` (a frase não muda de cor; o sinal está no sublinhado e no rótulo), entrelinha 1,9, até 70 caracteres por linha, parágrafos com intervalo de 16; cada afirmação é `<a>` com sublinhado de 2 px afastado 6 px e, ao lado, a marca em 14/600 sem quebra de linha |
| Quatro sinais (W04) | com fonte: sublinhado contínuo `--theme-accent`, "✓ com fonte"; exagero: tracejado `--theme-warning`, "! exagero"; sem fonte: pontilhado `--theme-input-line`, "○ sem fonte" em `--theme-muted`; revisada (P14b.8): sublinhado **duplo** `--theme-accent` de 1,5 px, "✓ com fonte · revisada por você". Sempre traço e texto |
| Legenda | cartão abaixo do texto, preenchimento 16 20, 14 px: os quatro sinais com o traço de exemplo; "revisada" explica "conferida por uma pessoa logada" |
| Painel da afirmação selecionada | rubrica "Afirmação selecionada"; a frase em serifa 18; cartão do estado (exagero: fundo `--theme-warning-bg`, título "! Mais forte que a fonte"; revisada: fundo `--theme-soft`, borda `--theme-accent-line`, "Ana Lima marcou como revisada hoje, às 14h40"); "Evidência ligada" com a citação e "abrir o original"; no pé, "Ligar outra evidência" e "Reescrever a frase" (secundários) e "Marcar como revisada por mim" (principal) |
| Modo Escrever (P14b.7) | o centro vira um cartão com a barra de formatação (`role="toolbar"`, botões de 40 px, raio 8: "Texto normal ▾", negrito, itálico, "• Lista", "☐ Tarefas", "+ Trecho com fonte" em `--theme-accent` 600 e "Mais" à direita; borda inferior 1 px `--theme-line`) e o texto em serifa 18, entrelinha 1,7, título 22/600; cada fonte no texto é o [selo de fonte em linha](#selo-fonte) ("Fonte 1"); no topo, "As notas são salvas enquanto você escreve." O painel da direita vira "Fontes da nota": lista numerada com a citação, a fonte e "abrir o original", e "Inserir trecho com fonte" no pé |
| Celular, 390 | coluna única, margens de 16. Modo Conferir: seletor de nota no topo (botão de 48 px, largura cheia, "Nota: Texto da reportagem ▾") e a afirmação selecionada num painel no pé da tela com as três ações (P14.5). Escrever: o mesmo seletor, o par "Conferir \| Escrever" em pílulas de meia largura e o editor em largura cheia. Trechos: o seletor "Notas \| Trechos" no topo, a lista em largura cheia e a legenda dos sinais abaixo |

| Estado | Aparência | Origem |
|---|---|---|
| Afirmação selecionada | contorno de 2 px `--theme-accent` afastado 3 px, raio 4, com o fundo da cor do sinal (`--theme-warning-bg` no exagero); o foco do teclado usa o anel de foco por fora | prancha aprovada (P14.1) |
| Vazio | nota sem afirmações: o modo Conferir diz que não há frase com número ou fato a conferir e oferece "Escrever"; sem trechos: "Nenhum trecho com fonte ainda" e "Registrar trecho com fonte" | derivado (W11, regra 1) |
| Revisada | só pessoa logada marca; o painel diz quem e quando | wireframe W04 |
| Editor (perfil) | vê e comenta sem alterar o texto: sem "Escrever", sem "Reescrever a frase" | wireframe W04 |

<a id="quadros"></a>

### Quadros: hipóteses, tabelas, comparador e celular

Pranchas: `aprovacao/quadros/proposta-{hipoteses,tabelas,comparador,mapa,linha-do-tempo}-*`. Cabeçalho dos quadros com as cinco [abas](#abas) (P15.1). Conteúdo com preenchimento 28 40.

**Hipóteses (W05, P15.2).**

| Parte | Medida e token |
|---|---|
| Hipótese aberta | cartão aberto, preenchimento 20 24, intervalo 16; título serifa 18/600; à direita, a contagem em 14 `--theme-muted` ("2 sustentam · 1 contraria · 1 falta") e "Editar" |
| Três colunas | grade de três colunas iguais, intervalo 16 (celular: uma coluna, intervalo 12). Coluna: fundo `--theme-reading`, raio 12, preenchimento 16, intervalo 12, traço de 3 px no topo. Sustenta: contínuo `--theme-accent`, ✓; contraria: contínuo `--theme-danger`, ícone `sinal-sem-suporte`; falta: tracejado `--theme-warning`, ícone `lacuna`. Título da coluna 600 na cor do traço, com o ícone de 16 px |
| Evidência | `<a>` com fundo `--theme-surface`, borda 1 px `--theme-line`, raio 8, preenchimento 12, intervalo 4, sem sublinhado; o que diz em `--theme-text` (o cartão inteiro é o alvo, não um link verde) e, em 14 `--theme-muted`, "fonte · abrir o original" (W05, regra 4). "+ Ligar evidência" é link 600 |
| Item de "falta" | item a resolver com "sem documento" em 14/600 `--theme-warning`; abaixo, a ação de lacuna (W05, regra 5) |
| Hipóteses fechadas | cartão-botão de largura cheia, preenchimento 16 20: título em serifa 18 e a contagem à direita |
| Nova hipótese | formulário no pé: rótulo "Escreva como afirmação que os documentos possam sustentar ou contrariar", "Cancelar" e "Criar"; no celular, "Nova hipótese" sobe para o topo, principal de 48 px |
| Painel "Como ler" | os três sinais com o texto de cada um e a frase de W05, regra 6: "A contagem não é placar: o quadro organiza as evidências, não decide se a hipótese é verdadeira." |

**Tabelas (W06, P15.3).**

| Parte | Medida e token |
|---|---|
| Tabela | dentro de um cartão; células com preenchimento 12 16, filete inferior 1 px `--theme-line`; cabeçalho 14/600 `--theme-muted` em fundo `--theme-reading`; valores à direita, algarismos tabulares, sem quebra |
| Três estados da célula | da fonte: a fonte é link na coluna "Fonte"; corrigida: ícone `sinal-corrigido` de 16 px em `--theme-warning` antes do valor e a linha em `--theme-active`; a conferir: "○ a conferir" em `--theme-muted` e "sem fonte ainda" na coluna da fonte |
| Célula selecionada | anel de foco na célula; o painel da direita ("Célula selecionada") mostra o valor lido pelo OCR riscado em `--theme-muted`, o valor corrigido em serifa 18/600, o campo "Por que corrigiu (obrigatório)", "Abrir original" e "Salvar" lado a lado, e "Histórico desta célula (n)" |
| Cálculo | cartão com preenchimento 16 20: "Cálculo", a operação num botão secundário de 40 px ("Soma ▾"), o intervalo, o resultado em serifa 18/600 e "ver a conta"; abaixo, em 14 `--theme-muted`, o que ficou fora e por quê ("A linha 4 fica fora da soma porque não tem valor conferido") |
| Ações do cabeçalho | "Exportar CSV" (secundário) e "Adicionar linha" (principal); no celular, lado a lado no topo |
| Celular | a tabela rola para o lado dentro do cartão (largura interna de 560 px), com o aviso "A tabela rola para o lado dentro da caixa."; o painel da célula vem abaixo, num cartão |

**Comparador (W07, P15.4).** Quinta aba dos quadros.

| Parte | Medida e token |
|---|---|
| Topo | "Comparador" e "3 diferenças: 2 de valor · 1 de data"; "Anterior" e "Próxima" (secundários) à direita |
| Lados | dois cartões lado a lado, intervalo 16, preenchimento 20, intervalo interno 12: "Lado A" e "Lado B" em 14/600 `--theme-muted`; o documento num botão secundário de largura cheia com "▾"; o trecho em serifa 18, entrelinha 1,8; fonte e "abrir original" em 14 |
| Diferença | retirado: fundo `--theme-danger-bg`, texto `--theme-danger`, riscado, "− " antes; incluído: fundo `--theme-soft`, texto `--theme-accent` 600, "+ " antes; raio 4 e preenchimento 0 4, como realce de texto (o sinal é `aria-hidden`; o risco e o texto bastam). Nunca só cor (W07, regra 2) |
| Conta | cartão com "Diferença de valor", a conta por extenso em serifa 18 ("10.710.000 − 8.750.000 = R$ 1.960.000,00 (22,4%)") e "Guardar como achado a conferir" (principal) |
| Frase do pé | "O comparador mostra o que mudou. Não diz se a mudança é irregular." (W07, regra 8) |
| Celular | os dois lados viram seletores empilhados; as diferenças viram lista de cartões ("1 de 3 · Valor global", o retirado e o incluído um abaixo do outro, a conta na primeira), com a selecionada como cartão aberto; "Guardar como achado a conferir" de largura cheia (W07, regra 7) |

**Mapa e linha do tempo no celular (P15.6).** Em 1440 continuam as telas finais do canvas ([mapa](#mapa), [linha do tempo](#linha-do-tempo)).

| Tela | Estrutura |
|---|---|
| Mapa, 390 | lista de ligações, a leitura acessível que o canvas prevê em "Ver como lista". Um cartão por entidade: forma de 36 px com o ícone do tipo em `--theme-on-primary` (círculo para pessoa, quadrado de raio 9 para empresa, de raio 3 em ameixa para órgão público), nome 600 e "Empresa · 9 documentos" em 14 `--theme-muted`; cada ligação numa linha com filete superior, ícone da relação de 16 px, o tipo em 600 e a outra ponta, e a fonte em 14 `--theme-muted`; ligação a confirmar em `--theme-warning` ("Irmãos? A confirmar:", "sem documento"). Aviso de possível homônimo; "Adicionar ligação"; "O mapa organiza o que os documentos dizem. Ele não avalia se é verdade." |
| Linha do tempo, 390 | coluna única: filtros em pílulas (altura 44, ativo verde cheio), o ano em serifa 36/600 com a contagem, e um evento por item: marco de 32 px à esquerda com o ícone do acontecimento de 16 px (cheio `--theme-accent` para data exata, vazado com borda 2 px para data parcial) e cartão com a data em 600, a qualificação ("data exata" em `--theme-muted`, "dia não informado" em `--theme-warning` 600), o acontecimento em serifa 18, o detalhe em 14 e o [selo de fonte isolado](#selo-fonte). O intervalo sem documento é um item a resolver com a ação de lacuna |

<a id="pedidos-e-prazos"></a>

### Pedidos e prazos (P15.5)

Pranchas: `aprovacao/quadros/proposta-pedidos-e-prazos-*`. Área própria da barra lateral (a aba "Entrevistas e pedidos" de hoje). Sem wireframe: o desenho parte dos campos que a Mesa já tem (`interface/redacao.js`).

| Parte | Medida e token |
|---|---|
| Moldura, 1440 | barra lateral com o item ativo e a pílula clara "1 vence" (P15.7); cabeçalho da apuração com "Exportar pauta interna" (secundário) e "Nova pergunta" (principal); lista com preenchimento 28 32, intervalo 16; painel da direita "Lacunas que pedem contato" |
| Cartão da pergunta | fundo `--theme-surface`, borda 1 px `--theme-line`, raio 12, preenchimento 16 20, intervalo 12. Linha de cima: o tipo num selo neutro ("Pedido via LAI", "Entrevista", "Pedido de informação"), o prazo e, à direita, a situação em 14 `--theme-muted`. Depois, a pergunta em serifa 18 e, em 14 `--theme-muted`, "Destinatário: … · 2 evidências motivam a pergunta" |
| Prazo | vencendo: selo de aviso "! vence em 5 dias · 2 de dezembro" (`--theme-warning` sobre `--theme-warning-bg`, borda `--theme-warning-line`); sem prazo: "sem prazo" em 14 `--theme-muted`; respondido: selo "✓ respondido" (`--theme-accent` sobre `--theme-soft`) e a resposta no lugar da situação ("Resposta: Ofício 88/2025, p. 1") |
| Pergunta aberta | cartão aberto, com "Registrar resposta recebida" (principal) e "Exportar texto do pedido" (secundário) |
| Lacunas que pedem contato | itens a resolver com o que falta e a origem ("Hipótese: …", "Linha do tempo: …", "Achado: …"); "Preparar pergunta" (secundário, largura cheia); "A pauta interna exportada não vai para a fonte: o texto do pedido sai só com as perguntas." |
| Celular, 390 | título e contagem; "Nova pergunta" principal de 48 px e largura cheia; os cartões em coluna (a situação desce para a linha de baixo); as lacunas num cartão no fim |

| Estado | Aparência | Origem |
|---|---|---|
| Vazio | "Nenhuma pergunta preparada ainda", o que a área guarda (pedidos de LAI, entrevistas e pedidos de informação, com prazo) e "Preparar pergunta" | derivado (W11, regra 1) |
| Prazo vencido | selo de erro "✕ venceu em 2 de dezembro" (`--theme-danger`) e a ação "Registrar recurso" | derivado; o cálculo do prazo e o recurso são da Onda 4 (PROD-07) |
| Contador da barra | "n vence" quando há prazo em até 5 dias; some quando não há | derivado |

<a id="documentos"></a>

### Documentos (W02, P16)

Pranchas: `aprovacao/documentos/proposta-*`. Uma tela só para acervo, envio e busca; a área "Cadastrar arquivos" deixa de existir e vira a área de envio desta tela (P16.1 e P16.5; comparativos em `aprovacao/cadastro/`).

| Parte | Medida e token |
|---|---|
| Moldura, 1440 | barra lateral com "Documentos" ativo e a pílula clara "12" (P16.4); cabeçalho da apuração; conteúdo com preenchimento 28 32, intervalo 16 |
| Topo | "Documentos" e "12 de 60" (documentos usados e o limite da redação, PROD-05); à direita, a busca no texto (W02, regra 4): rótulo "Buscar no texto dos documentos" em 14/600 `--theme-muted` e campo de 44 px, até 420 px de largura |
| Área de envio | borda 2 px tracejada `--theme-input-line`, raio 12, preenchimento 24, fundo `--theme-surface`, centrada: "**Arraste arquivos para cá** ou escolha no computador" (link 600) e, em 14 `--theme-muted`, "PDF, DOCX, XLSX, CSV, TXT e imagens · até 50 MB por arquivo". No celular: "Escolher arquivos" (principal, 48 px, largura cheia) e a mesma linha de formatos |
| Envio por arquivo (P16.2) | cartão com fundo `--theme-background`, `aria-busy="true"`, preenchimento 16 20, intervalo 12: "Enviando 3 arquivos" (600) e "Você pode continuar trabalhando e sair desta tela." (W02, regra 3). Uma linha por arquivo, em grade de 260 px, barra e 200 px, intervalo 16: o nome, o [medidor](#medidor) de 8 px e o resultado ("✓ Pronto, 14 pág." em `--theme-accent`; "Lendo pág. 2 de 5" em `--theme-muted`). Falha de um arquivo não derruba os outros (regra 2): ícone `sinal-sem-suporte` e o texto em `--theme-danger` 600 ("Tem macro e não foi lida. O original ficou guardado.") e "O que fazer" (secundário) (regra 6). No celular, cada arquivo vira uma coluna |
| Recibo do lote | última linha do cartão de envio, com filete superior 1 px `--theme-line`: "Recibo do lote: **2 de 3 cadastrados**, 1 pendente. É conferido antes da primeira pergunta." e "Ver recibo" à direita (W02, regra 8) |
| Lista, desktop (P16.3) | tabela num cartão: Documento, Páginas, Leitura e a ação; células com preenchimento 12 16 e filete 1 px `--theme-line`; cabeçalho 14/600 `--theme-muted` em fundo `--theme-reading`; a coluna da ação tem rótulo só para leitor de tela |
| Lista, celular (P16.3) | um cartão por documento, preenchimento 16, intervalo 8: nome 600, páginas em 14 `--theme-muted`, estado de leitura e a ação |
| Três estados de leitura | sempre sinal e texto (W02, regra 5): "✓ Texto do próprio arquivo" em `--theme-accent`; "Lida por OCR: confira números" com o ícone `sinal-parcial` em `--theme-warning` 600; "○ Imagem sem leitura" em `--theme-muted`, com a ação "Ler com OCR" (secundário). Os demais têm "Abrir original" |
| Detalhes técnicos | hash, identificador e versão saem da lista e ficam em "Detalhes técnicos", ao abrir o documento (W02, regra 7) |

| Estado | Aparência | Origem |
|---|---|---|
| Vazio | sem documentos: a área de envio sozinha, com "Nenhum documento nesta apuração ainda" acima; a busca fica desabilitada com a razão | derivado (W11, regra 1) |
| Ocupado | o cartão de envio, com `aria-busy`, uma barra por arquivo e a etapa por extenso | wireframe W02 e W11, regra 2 |
| Erro | por arquivo, no cartão de envio, com o que houve, o que foi preservado e "O que fazer" | wireframe W02, regra 6, e W11, regra 4 |
| Limite | "12 de 60" chega a "60 de 60": a área de envio vira o estado "Limite atingido" ([estados](#estados)) | derivado (W11, regra 7) |

**Detalhes do envio por arquivo** *(derivado, 22/11/2026)*:

- Linha que falhou não tem medidor: o texto do erro ocupa o lugar da barra (grade de 260 px, 1fr e `auto`) e "O que fazer" fica à direita, como secundário de 44 px; no celular, abaixo do texto, alinhado à esquerda. Vale também para o arquivo recusado antes do envio (nome com caracteres que a Mesa não aceita, arquivo acima de 50 MB).
- Resultado em 16, como o nome; só a linha do recibo é 14. "Ver recibo" é [link](#link) 14/600, à direita, também no celular.
- Cabeçalho: "Enviando 3 arquivos" (600) e o aviso em 14 `--theme-muted` na mesma linha, alinhados pela base, intervalo de 8, quebrando quando não cabem. Concluído, o título vira "Envio de 3 arquivos", o aviso sai e o cartão perde o `aria-busy`.
- "Cancelar envio" (secundário) aparece enquanto os bytes sobem (W11, regra 3) e sai quando a leitura passa ao servidor, que não se cancela.
- "Até 50 MB por arquivo" continua a ser o que a pessoa lê. A Mesa divide o envio em lotes de até 50 MB e 100 arquivos, e recusa no navegador o arquivo acima de 50 MB.
- Textos do resultado: "✓ Pronto, 14 pág."; "Lida por OCR: confira números" quando o texto veio do OCR; "Lida em parte: confira as páginas sem texto no original." quando parte das páginas ficou sem texto (sinal parcial, `--theme-warning` 600 nos dois); "Sem texto lido. O original ficou guardado." para a imagem sem leitura, até existir a rota de "Ler com OCR".

**Exceções declaradas, por falta de servidor** *(22/11/2026, a pedido do Maestro)*. A conferência da tela Documentos não barra por elas. Cada uma volta ao desenho aprovado quando o servidor existir, e a tela é conferida de novo nesse ponto.

| O que a prancha mostra | O que a tela mostra até lá | Volta quando |
|---|---|---|
| Busca "Buscar no texto dos documentos" no topo, antes da primeira pergunta (W02, regra 4) | a busca no texto fica como a segunda aba, "Pesquisar no conteúdo" (W02, regra 1, manda a aba sumir); o campo do topo à direita é "Encontrar documento", que filtra pelo nome, no mesmo lugar e medida | houver busca no texto do acervo sem rodada de análise |
| "12 de 60" ao lado do título (documentos usados e o limite da redação, PROD-05) | só a contagem ("12 documentos"), sem limite; o estado "Limite" da tabela acima não aparece | o servidor informar o limite de documentos da redação |
| "Ler com OCR" (secundário) na imagem sem leitura | "○ Imagem sem leitura" sem ação; no envio, "Sem texto lido. O original ficou guardado." | houver rota para pedir OCR de um documento |

**Mais dois estados de leitura** *(derivado, 22/11/2026)*, além dos três da prancha, sempre com sinal e texto (W02, regra 5): PDF com parte das páginas sem texto, "Lida em parte: confira as páginas sem texto" com o ícone `sinal-parcial` em `--theme-warning` 600; erro de leitura ou PDF protegido, "Não foi lido. O original ficou guardado." com o ícone `sinal-sem-suporte` em `--theme-danger` 600. Os dois têm "Abrir original".

**PDF sem nenhuma página com texto** *(derivado, 22/11/2026, na aceitação das capturas sobre `74fc0ab`)*: "○ Sem texto lido" em `--theme-muted`, com "Abrir original" (e "Ler com OCR" quando houver a rota). "○ Imagem sem leitura" vale só para arquivo de imagem; um PDF digitalizado sem texto não é imagem para quem lê a lista. É o mesmo texto do resultado no envio ("Sem texto lido. O original ficou guardado.").

**O que a tela tem além da prancha** *(derivado, 22/11/2026, fase 1)*:

- Abas "Acervo cadastrado" e "Pesquisar no conteúdo" acima do topo, enquanto vale a exceção da busca; no celular, pílulas de 44 (P20b).
- Barra "Leitura" (todos os documentos, ou só os com limitações) com "Atualizar acervo" ao lado, logo acima da lista; a caixa de seleção vai até 420 px, como a busca, e não ocupa a linha inteira no desktop.
- Uma contagem só, a do topo ("2 documentos"). A nota "Os originais estão preservados; a extração não substitui a conferência." pode ficar acima da lista, sem contagem. A versão dos documentos já está no cabeçalho e não se repete no pé da lista.
- "Acervo conferido? Explore o que os documentos permitem afirmar." com "Perguntar aos documentos" (principal) no pé, como próximo passo.
- "Ver recibo" abre o recibo conferido num cartão logo abaixo do cartão de envio. O cartão mostra só o que o envio não mostrou: título 16/600 ("Recibo do lote: 3 de 3 arquivos"), novos e duplicados ("3 novos · nenhum duplicado") e "Detalhes técnicos" com apuração e versão. O resultado de cada arquivo já está no cartão de envio e não se repete. Plural concordado, sem "(s)".

**O que vem de "Cadastrar arquivos" quando a área sai** *(derivado, 22/11/2026, a pedido do Lume, para a R4)*. As duas funções ficam na própria Documentos, que é a tela do acervo (P16.1).

- **Avisos do preparo de PDF**, no topo da tela, entre o título e a área de envio. É um cartão no padrão "Limite atingido" de [estados](#estados): fundo `--theme-warning-bg`, borda 1 px `--theme-warning-line` e título com "!" em `--theme-warning`. Não é erro: nada foi perdido.
  - **PDF cadastrado sem preparo:** título "! Há PDFs ainda sem preparo", com o resumo de hoje ("3 PDFs cadastrados ainda não foram preparados") e "Preparar PDFs pendentes" (secundário). O apoio fica em 14 `--theme-muted`: "Usa as cópias já cadastradas, sem reenviar." Enquanto prepara, o botão fica "Preparando…" e o cartão recebe `aria-busy`. Quando termina, o cartão sai e a linha de estado diz quantos foram preparados.
  - **Extrator de PDF indisponível:** título "! A leitura de PDF não está disponível neste computador", o texto de hoje e, num `<details>` "Detalhes técnicos", o que o ambiente informa. Os dois avisos podem aparecer juntos, um sobre o outro, com intervalo de 8.
- **Páginas do site** (fontes web), só em apuração com site. É um cartão abaixo da lista de documentos, no bloco base, com o título "Páginas de prefeitura.sp.gov.br" (o domínio da apuração, `translate="no"`) em 16/600.
  - **Formulário,** só para quem pode capturar (o dono, contrato 2.4; pela capacidade que `GET /api/sessao` devolve):
    - "Endereço da página": campo `type="url"`, com a dica "https://prefeitura.sp.gov.br/…";
    - "Observação (opcional)";
    - "Capturar página" (secundário, "Capturando…");
    - apoio: "Só páginas deste site. A captura guarda a página como estava agora."
  - **Lista "Páginas capturadas":** uma linha por captura, com o título ou o endereço, a data e "Ler" ([link](#link)). "Ler" abre o texto capturado logo abaixo, como hoje, com o foco no título da leitura. Sem capturas: "Nenhuma página capturada ainda."
  - **Erros:** no campo do endereço, com o texto do servidor (página de outro site, endereço inválido).
  - **Celular:** os campos e o botão em largura cheia.

**O recibo acompanha a pergunta** *(derivado, 22/11/2026, combinado com o Lume para a R4)*. A W02, regra 8, diz que o recibo do lote "é conferido antes da primeira pergunta". Por isso ele não some quando "Cadastrar arquivos" sai: passa a nascer de "Perguntar aos documentos", no pé da Documentos.

- **Quando aparece:** se, nesta visita à Documentos, houve um envio e o recibo dele está pronto, "Perguntar aos documentos" abre Perguntar com o recibo recolhido acima da caixa da pergunta (`#codex-recibo-alerta`). Sem envio nesta visita, Perguntar abre sem ele, como hoje pela barra lateral.
- **Forma:** o aviso em linha da Mesa (`.notice`), um `<details>` fechado. O resumo é "Recibo do último envio · confira as limitações antes de perguntar". Aberto, mostra o mesmo cartão do recibo da Documentos ("Recibo do lote: 3 de 3 arquivos", novos e duplicados, "Detalhes técnicos"), sem repetir ids.
- **Quando some:** ao enviar a primeira pergunta, como hoje, ou ao trocar de apuração.
- **Visita:** enquanto a página não é recarregada; recarregar zera. Combinado com o Lume em 22/11/2026, que o fez junto com o passo 3 da R4.

<a id="nova-apuracao"></a>

### Nova apuração (W01)

*(Derivado, 22/11/2026, a pedido do Lume, para a R4: a área "Cadastrar arquivos" deixa de existir, P16.5.)* Estrutura do wireframe W01 do canvas: uma página própria em três passos, "1 Nome e fontes · 2 Documentos · 3 Conferir recibo". O passo 1 é a página "Nova apuração". Os passos 2 e 3 são a própria tela [Documentos](#documentos), com a área de envio e o recibo. Nada é criado antes do primeiro envio: a apuração nasce nele (`cadastrar` com `novo: true`, contrato, 5.6), como hoje.

**Por onde se chega.** "Nova apuração" (principal) da Visão geral, e qualquer outro "Nova apuração" da Mesa, abre o passo 1. "Adicionar documentos" da Visão geral leva a Documentos com a apuração escolhida, sem os passos.

**Passo 1, "Nova apuração".**

- **Moldura:** a das outras áreas, sem item selecionado na barra. O título "Nova apuração" vem em serifa 28/600. Abaixo dele, a linha de etapas, a mesma do topo de Documentos ("1 Documentos 2 Pergunta…"), com "1 Nome e fontes" ativa e os outros dois passos apagados. No celular, "Passo 1 de 3 · Nome e fontes".
- **Cartão:** um só, de até 720 px.
  - **"Nome da apuração":** [campo](#campo) de 44 px, até 200 caracteres, obrigatório, com a dica "Ex.: Transporte escolar em Vila Serena". Recebe o foco.
  - **"Natureza dos documentos":** caixa com "Documentos públicos" e "Materiais sintéticos", como hoje. Vale para o primeiro envio.
  - **"De onde vêm as fontes?":** grupo de opções (`<fieldset>` com essa legenda), cada opção com o texto de apoio em 14 `--theme-muted`.
    - "Só documentos" (padrão), com o apoio "Padrão. Nada é buscado na internet."
    - "Documentos e um site", com o apoio "Você indica o site; o Vlado só captura páginas dele, a seu pedido." Escolhida esta opção, aparece "Endereço do site": campo com a dica "prefeitura.sp.gov.br", `translate="no"` e o apoio "Só o domínio, exato. Escolhido só agora: depois de criada, a apuração não troca de site."
- **Ações:** à direita, "Cancelar" (secundário), que volta à Visão geral sem criar nada, e "Continuar para documentos" (principal).
- **Erros, junto ao campo**, a 4 px dele e antes do texto de apoio: nome em branco, "Falta o nome. Dê um nome à apuração."; site em branco com a opção escolhida, "Falta o site. Escreva o domínio, por exemplo prefeitura.sp.gov.br."; site inválido, interno ou com caminho, "Site inválido. Use só o domínio, sem https:// nem caminho, por exemplo prefeitura.sp.gov.br." (W01, regra 3). A recusa do servidor no envio vai ao campo a que se refere.

**Passo 2, Documentos de uma apuração ainda por criar.** A tela [Documentos](#documentos) muda em poucos pontos:

- **Topo:** "Nova apuração" e o nome digitado, no lugar do título da apuração. A linha de etapas mostra "2 Documentos" ativa.
- **Pílulas:** sem as abas "Acervo cadastrado" e "Pesquisar no conteúdo", sem a busca e sem a barra "Leitura".
- **Acima da área de envio:** "A apuração é criada no primeiro envio. Antes disso, nada fica guardado." em 14 `--theme-muted`, e o [link](#link) "‹ Nome e fontes", que volta ao passo 1 com os campos preenchidos.
- **No envio:** o cartão de envio por arquivo de sempre. Quando o primeiro lote é aceito, a apuração passa a existir: o seletor do topo passa a ela e a tela vira a Documentos comum.
- **Passo 3:** quando o recibo do lote fica pronto, a linha de etapas marca "3 Conferir recibo" e "Ver recibo" abre o cartão do recibo, como hoje. Depois do recibo conferido, a linha de etapas sai.

**Primeiro envio que falhou** *(22/11/2026, sobre `a373ce7`)*. Quando o primeiro lote falha e a apuração não nasce, a tela fica no passo 2 da Nova apuração, sem as peças da Documentos comum: sem abas, busca, barra "Leitura", o vazio "Escolha uma apuração…" e "Perguntar aos documentos".

- O título continua "Nova apuração" com o nome.
- O cartão de envio mostra o erro do arquivo.
- Acima dele vem o aviso "Esta apuração não chegou a ser criada: o primeiro envio falhou. Recomece a Nova apuração.", em cores de aviso, com a ação "Recomeçar" (secundário), que volta ao passo 1 com os campos preenchidos.
- O diálogo de saída com o envio no ar é "A apuração está sendo criada", com o texto "Sair não cancela o envio: a apuração nasce assim mesmo, e você a encontra depois na Visão geral." e as ações "Ficar" e "Sair e encontrá-la depois".

**Sair no meio.** Quem sai no passo 1 ou no 2, antes do envio, não deixa nada. A Mesa não guarda rascunho de apuração; quando o formulário foi preenchido, pede a confirmação "Sair sem criar a apuração?" (variante simples do [diálogo](#dialogo), ação "Sair").

**Exceções declaradas, por falta de servidor.**

| O que o W01 mostra | O que a tela mostra até lá | Volta quando |
|---|---|---|
| Vários sites, até 10, com apelido, "Adicionar site" e "Remover" (regras 1 a 5) | um site só, sem apelido (o manifesto guarda um domínio) | o manifesto aceitar uma lista, mudança que pede alterar o `AGENTS.md` e revisão de segurança (W01) |
| Adicionar ou remover sites depois, em "Fontes" (regra 4) | o site é escolhido só na criação | houver a área "Fontes", que ainda não tem desenho |

---

<a id="quadros-onda4"></a>

## Quadros na Onda 4: sugestões da IA, formulários e comparação entre processos

> **Derivado, 27/11/2026, a pedido do Maestro (Onda 4, passo 1).** Parte das decisões do dono P45 (25/11, opção a: a IA sugere candidatos para os quadros, cada um preso a uma evidência publicada) e P47 (25/11: seletor comum de evidência e preenchimento do vínculo), da L9 (comparação entre processos: prompts 03 e 04, `prompts/MESA.md:84` e `:104`) e do modelo de `scripts/evidencias.py`. Não há prancha. A aparência sai dos componentes acima, com os tokens de sempre, nos dois temas, medida em 1440 e 375 px (P11.1). Os exemplos usam só dados sintéticos: Vila Serena, Construtora Alfa, Marta Reis, Carlos Prado, Contrato 041/2025 e Ana Lima. O Lume faz a tela e a Viga, o servidor. Se o dono quiser outro desenho, vale o dele.

Três regras valem para a seção inteira:

- **O que está sem pessoa nunca aparece como conferido** (P45). Sugestão da IA, veredito da IA e item confirmado sem conferência no original têm cada um a sua marca, e nenhuma delas usa a aparência da conferência humana ([selo](#selo); [suporte só da IA](#suporte-so-da-ia)).
- **Confirmar não é conferir.** Confirmar uma sugestão põe o item no quadro. Conferir no original continua sendo o que se faz no achado.
- **A diferença não é acusação.** Divergência de data, de desfecho ou de versão aparece em cor neutra ou de aviso, nunca nas cores de erro (W07, regra 8; W11, regra 6).

<a id="sugestao-ia"></a>

### Sugestão da IA nos quadros (P45)

A IA sugere cinco tipos de candidato: pessoa, organização, ligação, acontecimento datado e hipótese. Cada candidato traz a evidência publicada a que está preso, com o localizador. O servidor recusa candidato sem referência válida, então a tela nunca mostra sugestão sem fonte.

**Tabelas não recebem sugestão.** A P45 não prevê candidato de célula. Se um dia vier, valem as mesmas regras: a célula candidata nunca entra num cálculo antes de ser confirmada, e o cálculo diz que a deixou de fora.

**Os três sinais da sugestão.** São os mesmos do veredito da IA (P20a), para a pessoa reconhecer de uma vez tudo o que a IA propôs:

- **sem fundo próprio:** a sugestão fica transparente sobre o fundo do quadro;
- **borda 1 px tracejada `--theme-muted`;**
- **selo "IA · sugestão"** (inglês "AI · suggestion"): a pílula do veredito da IA, sem fundo, com borda 1 px tracejada `--theme-muted`, texto 14/600 `--theme-text` e sem sinal.

Sugestão da IA não é "a confirmar". "A confirmar" é o que uma pessoa marcou sem documento e continua em `--theme-warning` com o tracejado 6 6. A sugestão tem documento, mas ninguém a confirmou ainda: ela fica em `--theme-muted`, e no mapa com o tracejado 10 6. Os contrastes de `--theme-muted` já medidos passam: 5,58 e 6,97 sobre `--theme-surface` e 5,16 e 7,89 sobre `--theme-background`, no claro e no escuro.

| Quadro | Candidato | Forma, 1440 | Forma, 375 |
|---|---|---|---|
| Mapa | pessoa ou organização | nó de 200 px, de altura mínima 80, sem fundo, com borda 1 px tracejada `--theme-muted`. O ícone do tipo vem **vazado**: a forma sem preenchimento, com borda 2 px e desenho interno na cor do tipo (`--mapa-pessoa`, `--mapa-organizacao`; as bordas passam 3:1). Abaixo do nome, o selo "IA · sugestão" no lugar de "Pessoa · 3 documentos"; o tipo vai para o `aria-label` e para o painel | cartão da entidade na lista de ligações, sem fundo, com borda 1 px tracejada `--theme-muted`, a forma de 36 px vazada e o selo abaixo do nome |
| Mapa | ligação | linha de 2 px `--theme-muted`, tracejado **10 6**, ponta arredondada (os outros tracejados são 6 6, "a confirmar", e 2 5, parcial ou não revisado). O rótulo mantém o fundo `--mapa-rotulo-fundo`, que é o do mapa e precisa cobrir a linha; a borda fica 1 px tracejada `--theme-muted` e o texto começa por "IA ·" ("IA · sócia") | linha da ligação com filete superior tracejado `--theme-muted` e o tipo começando por "IA ·" ("IA · sócia de Construtora Alfa"); a fonte em 14 `--theme-muted` |
| Linha do tempo | acontecimento datado | marco de 36 px sem fundo, com borda 2 px tracejada `--theme-muted` e o ícone do tipo de data em `--theme-muted`. Cartão sem fundo, com borda 1 px tracejada `--theme-muted`, e o selo "IA · sugestão" antes da linha do tipo. O [selo de fonte](#selo-fonte) fica, porque a sugestão tem fonte. O trilho continua contínuo: ele liga datas, não afirma nada | marco de 32 px com o mesmo traço e cartão como no 1440 |
| Hipóteses | hipótese | grupo próprio, "Sugestões da IA (2)" (título 16/600), entre a hipótese aberta e as fechadas. Cada uma é um cartão-botão de largura cheia, sem fundo, com borda 1 px tracejada `--theme-muted` e preenchimento 16 20: o enunciado em serifa 18, o selo e, em 14 `--theme-muted`, a evidência ("Contrato 041/2025, p. 1") | o mesmo grupo, em coluna, logo abaixo de "Nova hipótese" |

**Onde aparecem.** No mapa e na linha do tempo, a sugestão ocupa o lugar que teria como item: no anel do mapa e na ordem das datas, para a pessoa ver o que ela muda no quadro. Ao lado da contagem do quadro vem ", 3 sugestões da IA" em 14 `--theme-muted`. A contagem some quando não há sugestão, e ela nunca entra na contagem de itens ("6 acontecimentos · 5 com documento" não muda). A legenda do mapa ganha o item "Sugestão da IA", com a linha 10 6 de exemplo. O "COMO LER" da linha do tempo ganha "Sugestão da IA: marco e cartão tracejados".

**Leitura acessível.** O nome acessível começa pela origem. No nó: "Sugestão da IA: Carlos Prado, pessoa". Na linha: "Sugestão da IA: Marta Reis é sócia da Construtora Alfa". No evento: "Sugestão da IA: assinatura do Contrato 041/2025, 3 de março de 2025". O selo dentro do nó é `aria-hidden`, para não repetir.

<a id="painel-sugestao"></a>

**Painel da sugestão.** Abre ao escolher uma sugestão. Em 1440, ocupa o painel da direita do quadro ([padrão](#telas-aprovadas), 360 px) ou o painel da ligação selecionada no mapa. Em 375 é uma camada de tela cheia, com as ações no pé (P12.3). As partes, de cima para baixo, com intervalo de 16:

| Parte | Medida e token |
|---|---|
| Rubrica | "SUGESTÃO DA IA", 14/600 maiúsculas, `--theme-muted` (não `--theme-accent`: nada foi conferido) |
| O que a IA propõe | serifa 22/600, como o título da ligação selecionada: "Marta Reis é sócia da Construtora Alfa", "Carlos Prado · pessoa", "Assinatura do Contrato 041/2025 · 3 mar 2025, data exata" ou o enunciado da hipótese |
| Evidência | a citação em serifa 16 e, em 14 `--theme-muted`, o localizador e "abrir o original" ("Contrato 041/2025, p. 1, linhas 12 a 14 · abrir o original"). Abaixo, o veredito da revisão da IA ([selo da P20a](#selo), por exemplo "IA · sustentado") e a natureza em 14 `--theme-muted` ("Declaração documental") |
| Origem | em 14 `--theme-muted`: "Da análise de 26/11, às 14h32", com a pergunta num `<details>` "Ver a pergunta" |
| Avisos | os de [avisos do vínculo](#avisos-vinculo), quando valem: análise não revisada, achado retirado, versão substituída. Destino "fora do briefing" é nota, não aviso |
| Ações | "Confirmar" (principal), "Corrigir" e "Descartar" (secundários). Em 1440 ficam numa linha, com intervalo de 8. Em 375 formam uma grade de três colunas de 48 px (`repeat(auto-fit, minmax(min(100%, 6.5rem), 1fr))`, intervalo de 8; cabem em 343 px) |
| Nota do pé | em 14 `--theme-muted`: "Confirmar põe a sugestão no quadro. A conferência no original continua no achado." |

**O que acontece depois de cada ação.**

| Ação | O que acontece | Foco e anúncio |
|---|---|---|
| Confirmar | A sugestão vira item do quadro com os dados que a IA propôs e o vínculo preenchido pela revisão da IA: papel, suporte e natureza da última revisão (P47). O item perde o tracejado de sugestão e segue as regras de sempre do quadro (a linha do mapa fica contínua só com suporte sustentado, senão pontilhada 2 5). O suporte continua mostrado com o selo da IA ("IA · sustentado") até uma pessoa mudá-lo. O item guarda "Confirmado por Ana Lima em 27/11, às 10h05, a partir de sugestão da IA", em 14 `--theme-muted` no painel do item. Hipótese confirmada nasce "em aberto": a situação é sempre declarada por pessoa (`scripts/hipoteses.py`), e a IA nunca a preenche | foco no item novo; `role="status"`: "Sugestão confirmada: Carlos Prado entrou no mapa." |
| Corrigir | Abre o [formulário](#formularios-quadros) do quadro, preenchido com a sugestão, com o título "Corrigir sugestão da IA". Ao salvar, o item nasce com a marca [alterado por pessoa](#alterado-por-pessoa) em cada campo mudado. "Cancelar" volta à sugestão intacta | foco no primeiro campo; ao salvar, no item novo |
| Descartar | Sem diálogo, porque se desfaz: a sugestão sai da vista e vai para "Descartadas (n)", um `<details>` fechado no pé do quadro, em que cada uma tem "Restaurar" (secundário). Restaurar a devolve como sugestão, nunca como item. Se uma análise nova sugerir de novo o mesmo item com a mesma evidência, ele volta direto a "Descartadas", marcado "já descartada em 27/11" | foco na próxima sugestão ou, sem outra, no título do quadro; `role="status"`: "Sugestão descartada. Ela fica em Descartadas, com Restaurar." |

**Quando "Confirmar" fica indisponível.** Usa a variante desabilitada do [botão](#botao), com a razão em 14 `--theme-muted` ligada por `aria-describedby`. "Corrigir" e "Descartar" continuam ativos.

| Caso | Razão |
|---|---|
| Ligação com uma ponta que ainda é sugestão | "Confirme antes Carlos Prado, a outra ponta da ligação." Se essa ponta foi descartada: "Carlos Prado, a outra ponta, está em Descartadas. Restaure-o ou troque a ponta em Corrigir." No formulário de "Corrigir", a ponta pode ser trocada por uma entidade que já está no mapa |
| A revisão da IA retirou o achado da evidência, ou ela foi substituída | "A revisão da IA retirou este achado. Corrija com outra evidência ou descarte." Na versão substituída: "Há uma versão mais nova deste achado. Corrija para ligar a nova versão." |
| O veredito da revisão da IA é não sustentado ou ilegível | "A revisão da IA não sustentou esta evidência. Corrija com outra evidência ou descarte." Ilegível: "A revisão da IA não conseguiu ler esta evidência. Confira no original e corrija, ou descarte." O item não entra no quadro com um suporte que a legenda não descreve |
| A evidência deixou de estar disponível (rodada apagada) | "A evidência não está mais disponível. Descarte ou corrija com outra." |
| Sem permissão de editar o quadro (sem as capacidades de criar e atualizar do quadro na sessão: `hipoteses-criar` e `-atualizar`, `linha-tempo-criar` e `-atualizar`, `mapa-entidade-criar`, `mapa-relacao-criar` e os `-atualizar`) | as três ações ficam indisponíveis, com "Só repórter e editor mudam os quadros." A pessoa continua vendo as sugestões |

| Estado | Aparência | Origem |
|---|---|---|
| Padrão | tabela dos sinais acima | derivado (P20a, P45) |
| Selecionado | borda 2 px **tracejada** `--theme-accent`, com a mesma sombra do nó e do evento selecionados. O tracejado, o selo "IA · sugestão" e a transparência ficam: a seleção nunca tira um dos três sinais (P20a). Na ligação selecionada, o traço passa a 4 px `--theme-accent` e mantém o tracejado 10 6 | derivado; B3 da Coruja sobre `b1528cb` |
| Ao passar o mouse | a borda tracejada passa a `--theme-text`, e o fundo continua transparente | derivado |
| Foco | anel de foco do lado de fora da borda tracejada | regra geral |
| Ocupado | `aria-busy` no painel; o botão escolhido no gerúndio ("Confirmando…", "Descartando…"), os outros dois desabilitados até a resposta | derivado de W11, regra 2 |
| Erro | mensagem em 14 `--theme-danger` acima das ações, com `role="alert"`, no formato de W11: "Não deu para confirmar: a evidência não está mais publicada. Descarte ou corrija com outra." A sugestão continua aberta | derivado de W11, regra 4 |
| Desabilitado | tabela acima | derivado |
| Vazio | sem sugestões, nada aparece: sem grupo, sem contagem e sem "Descartadas" | derivado |

**Para a Viga.** O formato do candidato ainda não está no `MESA.md`, e ele é versionado ali (P45). A tela precisa, por candidato: o tipo (`pessoa`, `organizacao`, `ligacao`, `acontecimento`, `hipotese`), os campos do item no formato do quadro, a referência da evidência publicada com o localizador, a análise de origem (caso, rodada, data), o veredito e a natureza da última revisão da IA, o destino do achado (`incluido`, `fora_do_briefing`, `pendencia`, `retirado`, `substituido`) e, na ligação, quais pontas ainda são sugestão. O estado da sugestão (aberta, confirmada, descartada) com quem decidiu e quando também precisa vir. O que o vínculo precisa guardar para a marca "alterado por pessoa" está em [registro do vínculo](#registro-vinculo).

<a id="formularios-quadros"></a>

### Formulários de criar e editar dos quatro quadros

**Moldura.** Em 1440, o formulário ocupa o painel da direita do quadro (360 px; [padrão](#telas-aprovadas)), no lugar do painel do item selecionado. Enquanto os quadros ficam no cartão com abas sem painel (mapa e linha do tempo), o formulário abre como uma coluna de 360 px à direita, dentro do cartão. Abaixo de 1024 px, e em 375, é uma camada de tela cheia (P12.3). No topo da camada vem "‹ Voltar" (secundário, 44 px) e o título. As ações ficam no pé fixo, que nunca cobre o campo com foco (`scroll-padding-bottom` na altura do pé, UX-19).

| Parte | Medida e token |
|---|---|
| Título | serifa 22/600: "Nova ligação", "Editar acontecimento", "Corrigir sugestão da IA" |
| Campos | o [campo de texto](#campo) de sempre, rótulo acima, com intervalo de 16 entre campos. Os limites de tamanho são os do servidor, e o contador aparece só nos últimos 10% ("980 de 1.000") |
| Evidências | rubrica "EVIDÊNCIAS" (14/600 maiúsculas, `--theme-muted`) e um [cartão do vínculo](#cartao-vinculo) por evidência, com intervalo de 8. Abaixo, "+ Ligar evidência" ([link](#link) 600, 44 px de altura), que abre o [seletor](#seletor-evidencia) |
| Pé | "Cancelar" (secundário) e "Salvar" (principal), à direita, com intervalo de 8. No item já existente, "Retirar…" fica à esquerda, em texto `--theme-danger`, para os quadros que guardam retirada com motivo (linha do tempo e mapa) |

**Campos por quadro.** Nomes e limites como no servidor.

| Quadro | Campos | Regras que a tela mostra antes do servidor |
|---|---|---|
| Hipótese | "Hipótese" (área de texto, até 1.000; rótulo de P15.2: "Escreva como afirmação que os documentos possam sustentar ou contrariar"); "Situação" (grupo de opções: Em aberto, Sustentada, Contrariada, Inconclusiva, Descartada); "O que falta" (lista, cada item até 1.000, com "+ O que falta" e, em cada um, "Virar pergunta ou pedido"); evidências | Sustentada e Contrariada ficam indisponíveis até haver evidência sustentada e documental no papel certo, com a razão "Sustentada pede ao menos uma evidência de suporte sustentada e documental" (e "de contradição", para Contrariada). A situação é sempre escolhida por pessoa; o formulário de "Corrigir sugestão" chega com "Em aberto". Criar uma hipótese continua pelo formulário do pé (P15.2), só com o enunciado; "Editar" abre este formulário completo |
| Acontecimento | "Acontecimento" (área de texto, até 1.000); "Datas", uma ou mais, cada uma com "Tipo de data" (lista com os rótulos de `TIPOS_DATA`: "Data de assinatura", "Data de pagamento"…), "Data" (campo com o apoio "Ano, mês e ano ou dia completo, como o documento traz: 2025, 03/2025 ou 03/03/2025"), "Data aproximada" (caixa de seleção), "Fonte da data" (lista das evidências ligadas a este acontecimento) e "Observação" (até 500); evidências | Ao menos uma evidência de suporte: "Falta a evidência. Ligue ao menos um documento que registre o acontecimento." A precisão vem do que foi digitado e é mostrada logo abaixo do campo, em 14 `--theme-muted` ("Precisão: mês"). Duas datas do mesmo tipo e diferentes não são erro: ficam as duas, com o aviso "Duas datas de assinatura diferentes: 03/03/2025 no Contrato 041/2025 e 05/03/2025 no Termo aditivo nº 1. As duas ficam na linha do tempo; confira no original." |
| Entidade do mapa | "Nome" (até 300); "Tipo" ([seletor segmentado](#caderno): Pessoa \| Organização); "Variantes de nome" (lista, cada uma até 300, com "+ Variante"); "Identificadores" (cada um com tipo: CPF, CNPJ, registro profissional, matrícula ou outro; valor até 100; fonte entre as evidências ligadas); evidências | CPF com 11 dígitos e CNPJ com 14, com o erro no campo ("CPF tem 11 dígitos. Confira o número no documento."). O valor aparece inteiro só enquanto é digitado; salvo, aparece mascarado como no mapa. A confirmação de homônimo continua sendo só de pessoa, no alerta do painel; o formulário não junta entidades |
| Ligação do mapa | "De" e "Para" (caixa de combinação com busca entre as entidades do mapa, mais "+ Nova entidade", que abre o formulário de entidade e volta); "Tipo de relação" (até 120, campo livre, com as sugestões que dão ícone: sócio, irmão, cargo, contrato, pagamento); "Descrição" (opcional, até 2.000); evidências | Mesma entidade nas duas pontas: "A ligação precisa de duas entidades diferentes. Troque uma das pontas." Ao menos uma evidência de suporte. Nota em 14 `--theme-muted` acima do pé: "A linha fica contínua só com evidência de suporte sustentada. Sem ela, fica pontilhada." |
| Tabela | "Título da tabela" (até 300); "Descrição" (opcional, até 2.000); "Colunas", cada uma com nome (até 120), tipo (texto, data, monetário, número) e unidade (até 30). "Adicionar linha" abre uma linha nova com uma célula por coluna, cada uma com valor e fonte (pelo seletor) | Célula sem fonte nasce "○ a conferir". A tabela só acrescenta: linhas não se apagam, e corrigir uma célula continua no painel "Célula selecionada" (P15.3), com justificativa obrigatória e o valor anterior guardado (W06). O cálculo continua só com soma, diferença, contagem e média, com a conta à vista |

**Retirar.** Na linha do tempo e no mapa, "Retirar…" abre o [diálogo](#dialogo) destrutivo com campo: "Retirar “Assinatura do Contrato 041/2025” da linha do tempo?", com "Motivo (obrigatório)" e a ação "Retirar", desabilitada até haver motivo. O item retirado sai da vista e fica no registro, com o motivo.

**Sair com alterações não salvas.** O diálogo destrutivo de sempre: "Descartar alterações" (`apuracao.js:413`).

<a id="cartao-vinculo"></a>

**Cartão do vínculo.** Um por evidência ligada. Fundo `--theme-surface`, borda 1 px `--theme-line`, raio 8, preenchimento 12, coluna com intervalo de 8.

| Parte | Medida e token |
|---|---|
| Cabeça | o tipo da fonte em 14/600 `--theme-muted` ("Achado da IA", "Trecho do caderno"); à direita, a marca "alterado por pessoa" quando houver |
| Citação | serifa 16, até três linhas, com "Mostrar tudo" ([link](#link)) quando passa disso |
| Localizador | 14 `--theme-muted`: "Contrato 041/2025, p. 1, linhas 12 a 14 · abrir o original" |
| Papel | [seletor segmentado](#caderno): Suporte \| Contradição \| Contexto |
| Suporte | lista: Não revisado, Sustentado, Parcial, Não sustentado, Ilegível |
| Natureza | lista: Declaração documental, Alegação atribuída, Inferência, Pendência |
| Justificativa | área de texto, até 2.000 |
| Linha da IA | em 14 `--theme-muted`, só em evidência da IA: "Da revisão da IA:" e o [selo da P20a](#selo) ("IA · sustentado") com a natureza ("declaração documental") |
| Pé | "Desligar" (botão de texto, 44 px de altura, `--theme-danger`) |

As regras do modelo (`scripts/evidencias.py`) aparecem antes do envio, sempre com a razão em 14 `--theme-muted`:

- **Papel "Contexto":** o suporte fica fixo em "Não revisado", desabilitado, com "Evidência de contexto não recebe suporte."
- **Natureza "Pendência":** a opção "Sustentado" fica indisponível, com "Uma pendência nunca é sustentada."
- **Limite de 100 evidências por item:** "+ Ligar evidência" fica indisponível, com "Este item já tem 100 evidências, o limite."

**Preenchimento do vínculo (P47).** De onde vem a evidência decide como o cartão chega:

- **Achado da IA:** papel, suporte e natureza da última revisão da IA, com a linha "Da revisão da IA" visível.
- **Achado retirado** (destino `retirado`, também nas rodadas antigas em que a síntese retirou um achado sustentado, como os de Paranaíta que levaram à P48): papel e natureza da revisão, mas o suporte nasce **"Não revisado"**, com a linha "Da revisão da IA: IA · sustentado · retirado". O vínculo guarda o destino. Se uma pessoa escolher "Sustentado", o campo leva a marca "alterado por pessoa". Assim o veredito de um achado retirado não deixa, sozinho, a linha do mapa contínua nem "Sustentada" disponível na hipótese.
- **Fonte do caderno** (trecho com fonte, anotação, achado do jornalista): suporte em "Não revisado" e natureza sem escolha. O erro no envio é "Falta a natureza. Escolha o que a fonte é: declaração documental, alegação atribuída, inferência ou pendência." Sem linha da IA.
- **Vínculo antigo,** de antes desta marca: sem linha da IA e sem "alterado por pessoa". A tela não deduz nada que o registro não traz.

<a id="alterado-por-pessoa"></a>

**"Alterado por pessoa" (I1).** Quando uma pessoa muda um campo que veio da revisão da IA (papel, suporte ou natureza), o campo ganha, ao lado do rótulo, o ícone `sinal-corrigido` de 16 px e "alterado por Ana Lima", em 14/600 `--theme-warning`. É o mesmo sinal da célula corrigida das tabelas (W06). A linha "Da revisão da IA: sustentado" continua abaixo, para o valor da IA nunca sumir. A cabeça do cartão mostra "Alterado por pessoa", com o mesmo ícone e a mesma cor. Para a própria pessoa, o texto é "alterado por você".

Fora do formulário, onde a evidência aparece (coluna da hipótese, painel da ligação, cartão do evento, painel da afirmação no caderno), a marca vai junto da fonte, em 14 `--theme-muted` com o ícone em `--theme-warning`: "Contrato 041/2025, p. 1 · alterado por Ana Lima · abrir o original". Cada campo alterado tem "Voltar ao da IA" ([link](#link) 14/600), que apaga a revisão humana e por isso pede confirmação (abaixo).

<a id="avisos-vinculo"></a>

**Avisos do vínculo.** Usam o aviso em linha da Mesa (`.notice`: fundo `--theme-warning-bg`, filete esquerdo `--theme-notice-line`, texto `--theme-warning`, `role="status"`), dentro do cartão do vínculo, acima da citação. Nenhum é erro, nem usa as cores de erro.

| Caso | Texto |
|---|---|
| Análise sem revisão de suporte | "Esta análise não passou pela revisão de suporte. O vínculo começa em “não revisado”." |
| Achado retirado pela revisão da IA | "A revisão da IA retirou este achado: «motivo». Ele pode continuar ligado, com o suporte em “não revisado”: só sustenta o item se uma pessoa escolher." |
| Versão substituída | "Há uma versão mais nova deste achado." e "Ligar a versão nova" ([link](#link)), que troca a referência e passa papel, suporte e natureza aos da revisão da versão nova (suporte "não revisado" se a versão nova foi retirada). Com "alterado por pessoa" no vínculo, passa antes pelo diálogo de [apagar revisão](#apagar-revisao) |
| Evidência indisponível (rodada apagada) | "A evidência não está mais disponível. O vínculo fica no registro, mas não abre o original." |

**Fora do briefing não é aviso.** O destino `fora_do_briefing` é um achado sustentado que a síntese deixou de fora. Ele vem como nota em 14 `--theme-muted`, abaixo da linha da IA: "Fora do briefing (sustentado): a revisão sustentou o achado, mas ele não entrou no briefing." O rótulo é o da P48.

<a id="apagar-revisao"></a>

**Confirmação antes de apagar uma revisão humana.** Quatro ações desfazem o que uma pessoa decidiu e passam pelo [diálogo](#dialogo) destrutivo:

- **Desligar** um vínculo com "alterado por pessoa", ou um vínculo do caderno cujo suporte uma pessoa escolheu (qualquer um diferente de "Não revisado");
- **"Ligar a versão nova"** num vínculo com "alterado por pessoa";
- **"Voltar ao da IA"** num campo alterado;
- **desmarcar "revisada"** no caderno (P14b.8).

O diálogo tem a rubrica "APAGAR REVISÃO" e o título "Apagar a revisão de Ana Lima?" ("Apagar a sua revisão?" para a própria pessoa). O texto diz o que muda: "Ana Lima mudou o suporte de “sustentado” (da revisão da IA) para “parcial” em 26/11, às 16h10. O vínculo volta ao que a revisão da IA disse." A ação é "Apagar a revisão" e o foco inicial fica em "Cancelar". Dois casos mudam o texto e a ação:

- **"Ligar a versão nova":** "O vínculo passa à versão nova do achado e volta ao que a revisão dela disse: papel, suporte e natureza. A mudança de Ana Lima (suporte “parcial”, em 26/11, às 16h10) deixa de valer." A ação é "Ligar a versão nova".
- **Vínculo do caderno:** "Ana Lima escolheu o suporte “sustentado” em 26/11, às 16h10. Desligar apaga essa escolha; o trecho continua no caderno." A ação é "Desligar".

Desligar um vínculo sem revisão humana (da IA sem a marca, ou do caderno ainda em "Não revisado") não pede confirmação.

<a id="suporte-so-da-ia"></a>

**Quando o suporte vem só da revisão da IA** (R2 da Coruja sobre `b1528cb`). O suporte é só da IA quando o vínculo mantém o valor da revisão, sem "alterado por pessoa", e ninguém conferiu o achado no original. Nesse caso, nada no quadro usa a aparência da conferência humana:

- **Painel da ligação selecionada:** o selo "✓ 2 evidências conferidas no original" fica só para o que uma pessoa conferiu. O resto vem na pílula da P20a, "IA · 2 evidências sustentadas" (sem fundo, borda tracejada `--theme-muted`, sem sinal). Havendo as duas coisas, as duas pílulas lado a lado: "✓ 1 evidência conferida no original" e "IA · 1 sustentada".
- **Hipótese:** "Com evidência conferida" fica para a evidência conferida por pessoa. Com suporte só da IA, a condição diz "Com evidência sustentada pela revisão da IA", na forma da P20a.
- **Linha do tempo e cartão do vínculo:** a fonte leva o selo "IA · sustentado" no lugar do selo humano.

<a id="registro-vinculo"></a>

**Para a Viga: o registro do vínculo** (R1 e B2 da Coruja sobre `b1528cb`). Hoje o vínculo guarda só `referencia`, `papel`, `suporte`, `natureza` e `justificativa` (`scripts/evidencias.py`). A marca, "Voltar ao da IA", a linha "Da revisão da IA" e o texto dos diálogos pedem mais. O vínculo resolvido precisa trazer:

- os valores da revisão da IA no momento de ligar (papel, suporte, natureza), com a análise e a versão do achado;
- o destino do achado, para o servidor não contar um achado retirado como suporte sem a escolha de uma pessoa;
- por campo mudado: quem mudou, quando e o valor anterior;
- no vínculo do caderno: quem escolheu o suporte e quando;
- se uma pessoa conferiu o achado no original, para separar o suporte só da IA.

Sem esses campos, a tela não mostra a marca: ela não deduz nada que o registro não traz.

<a id="seletor-evidencia"></a>

### Seletor comum de evidência (P47)

Um componente só, aberto por "+ Ligar evidência" nos quatro formulários e por "Ligar outra evidência" no painel da afirmação do caderno (conferência do texto, P14.1). Ele nunca procura fora da apuração aberta.

**Moldura.** O seletor abre no mesmo painel ou camada do formulário, no lugar dele, com "‹ Voltar ao formulário" ([link](#link), 44 px) no topo. Ao abrir, o foco vai ao campo de busca. Ao voltar, vai a "+ Ligar evidência" ou ao cartão novo. No caderno, abre no painel da afirmação (340 px) com "‹ Voltar à afirmação".

| Parte | Medida e token |
|---|---|
| Título | serifa 22/600, "Ligar evidência" |
| Busca | rótulo "Buscar nos achados e no caderno" (14/600 `--theme-muted`), campo de 44 px em largura cheia. Procura no texto do achado, na citação e no nome do documento, a partir do segundo caractere |
| Origem | pílulas de 44 px ([filtro em pílula](#botao), `aria-pressed`): "Tudo", "Achados da IA", "Caderno" |
| Análise | em 14 `--theme-muted`: "Achados da análise mais recente (26/11, 14h32)". "Avançado" é um `<details>` fechado com a lista das análises da apuração, por data e com a pergunta, para escolher outra. Só as desta apuração |
| Resultado | botão de largura cheia, fundo `--theme-surface`, borda 1 px `--theme-line`, raio 8, preenchimento 12, intervalo 4: o tipo em 14/600 `--theme-muted`; o texto em serifa 16, até três linhas; o localizador em 14 `--theme-muted`; na linha de baixo, o estado. Intervalo de 8 entre resultados |
| Estado do resultado | duas marcas que não se confundem: a conferência humana ([selo](#selo) "✓ Conferido no original" ou "○ A conferir"; W05, regra 3) e, no achado da IA, o veredito (selo da P20a). Destino retirado: "retirado pela revisão" em 14/600 `--theme-warning`, e o vínculo nasce com o suporte "Não revisado" ([preenchimento](#cartao-vinculo)); fora do briefing, a nota curta "fora do briefing (sustentado)" em 14 `--theme-muted` |
| Resultado aberto | ao escolher, o resultado vira cartão aberto (borda 2 px `--theme-accent`) com os campos do vínculo já preenchidos (P47), "Abrir o original" (secundário) e "Ligar" (principal) |
| Já ligado | o resultado aparece com "Já ligada a este item" em 14 `--theme-muted` e não abre |

Depois de "Ligar", o seletor fecha, o cartão novo entra no formulário e o foco vai a ele, com `role="status"`: "Evidência ligada."

| Estado | Aparência | Origem |
|---|---|---|
| Padrão | lista dos resultados da análise mais recente, sem busca digitada | derivado |
| Foco | anel no resultado; setas não movem o foco (é lista de botões, não `listbox`), Tab passa de um a outro | regra geral |
| Ocupado | esqueleto de três resultados enquanto busca; nada de piscar abaixo de 0,3 s | W11, regra 2 |
| Erro | bloco de erro do serviço no lugar da lista; a busca digitada fica | W11, regra 4 |
| Desabilitado | "Ligar" indisponível no item que chegou a 100 evidências, com a razão do cartão do vínculo | derivado |
| Vazio, com busca | "Nada encontrado para “Marta”." e "A busca não encontrou. Isso não prova que não esteja nos documentos." com a ação "Limpar a busca" | W11, regra 1 |
| Vazio, sem nada | "Esta apuração ainda não tem achados nem trechos com fonte." e a ação "Fazer uma pergunta" | W11, regra 1 |

<a id="comparar-processos"></a>

### Comparação entre processos (L9)

Quando o acervo tem mais de um processo sobre a mesma matéria, a análise procura o mesmo documento, parecer ou fundamento em mais de um deles e compara os desfechos (`prompts/MESA.md:84`, prompt 03). A revisão confere se o fundamento é de fato o mesmo (versão, data, emissor e trecho) e se os desfechos são comparáveis (mesma questão decidida, mesma fase). Sem essa conferência, a comparação fica como pendência (`prompts/MESA.md:104`, prompt 04). A tela mostra isso no Comparador, a quinta aba dos quadros.

**Modo.** No topo do Comparador vem o [seletor segmentado](#caderno) "Documentos \| Processos" (`role="group"`, `aria-pressed`). Documentos é o comparador de hoje (W07, P15.4). Processos é a vista abaixo. Em 375, o seletor fica em largura cheia.

| Parte, 1440 | Medida e token |
|---|---|
| Topo | "Comparação entre processos" (título dentro dos quadros, serifa 22/600) e "2 comparações · 1 pendente" em 14 `--theme-muted` (pendente: veredito da revisão da IA diferente de sustentado, ou natureza ou destino do achado pendência); "Anterior" e "Próxima" (secundários) à direita, como no Comparador |
| Fundamento comum | cartão no bloco base, preenchimento 20: rubrica "FUNDAMENTO COMUM" (14/600 `--theme-muted`); o fundamento em serifa 18 ("Parecer jurídico nº 12/2025 da Procuradoria de Vila Serena"); a chave que liga os processos numa lista de definições em 14 (Identificador, Data, Emissor, Versão: rótulo em `--theme-muted`, valor em `--theme-text`); a identidade: "= Mesmo arquivo nos dois processos (mesmo hash)" em 14/600 `--theme-text`, com o "=" `aria-hidden` (é a comparação de hash feita pela Mesa, nem conferência humana nem veredito da IA), ou "○ Mesmo fundamento a conferir: versões ou trechos diferentes" em 14 `--theme-muted`, com "Comparar os dois trechos" ([link](#link)), que abre o modo Documentos com os dois lados escolhidos |
| Processo A e B | dois cartões lado a lado, como os lados do Comparador (intervalo 16, preenchimento 20, intervalo interno 12): "Processo A" e "Processo B" em 14/600 `--theme-muted`; o processo em 16/600 ("Processo 2025/118 · Contrato 041/2025 com a Construtora Alfa"); o trecho do fundamento em serifa 16, com o localizador e "abrir o original" em 14; a rubrica "DESFECHO" e o desfecho em serifa 16, com a fonte |
| O que muda | tabela num cartão (o padrão das [tabelas](#quadros)): linhas Questão decidida, Fase, Desfecho; colunas Processo A, Processo B e Comparação. A comparação diz "igual" ou "diferente" em 14/600 `--theme-text`, precedida de "=" ou "≠" `aria-hidden`. A cor é neutra: diferença de desfecho não é aviso nem erro |
| Conferência da comparação | rubrica "CONFERÊNCIA DA COMPARAÇÃO" e o veredito da revisão da IA (selo da P20a, "IA · sustentado" ou "IA · parcial"). Seis linhas, intervalo de 8: mesma versão, mesma data, mesmo emissor, mesmo trecho, mesma questão decidida, mesma fase. São resultado da revisão da IA e vêm na forma da P20a, sem sinal e sem a cor da conferência humana: "IA · mesmo emissor" (texto `--theme-text`, borda tracejada `--theme-muted`), "IA · fase a conferir" (texto e borda `--theme-warning`) e "IA · fases diferentes: recurso e primeira instância" (texto `--theme-text`, borda tracejada `--theme-muted`). A diferença é dita, mas não é erro: mostra só que a comparação não se sustenta |
| Pendência | se alguma linha não disser "mesmo" (e, dentro da exceção abaixo, se a comparação for pendente pela regra do topo), o cartão inteiro da comparação vira item a resolver (borda 1 px tracejada `--theme-warning`, fundo `--theme-warning-bg`), com "! Comparação pendente: falta conferir que o fundamento e os desfechos são comparáveis." em 16/600 `--theme-warning` e a [ação de lacuna](#telas-aprovadas) "Virar pergunta ou pedido" |
| Frase do pé | "A diferença de desfecho não prova irregularidade." em 16, como a frase do Comparador (W07, regra 8) |
| Ações | "Abrir o achado para conferir" (principal), que leva a Conferir achado: a comparação é um achado da análise e se confere lá (W07, regra 5). "Criar hipótese com esta comparação" (secundário) abre o formulário de hipótese com o enunciado em branco, a situação "em aberto" e as evidências dos dois lados ligadas, com o preenchimento da P47 |

**Em 375.** Os dois processos se empilham (W07, regra 7). "O que muda" vira três cartões, um por linha (Questão decidida, Fase, Desfecho), com A e B um abaixo do outro e "igual" ou "diferente" no título do cartão. A conferência vem em coluna e as ações, em largura cheia, com 48 px.

| Estado | Aparência | Origem |
|---|---|---|
| Padrão | acima | derivado (L9) |
| Foco | anel de foco nos controles; "Anterior" e "Próxima" pelo teclado (W07, regra 3) | regra geral |
| Ocupado | esqueleto do fundamento e dos dois lados | W11, regra 2 |
| Erro | bloco de erro do serviço; o modo Documentos continua disponível | W11, regra 4 |
| Desabilitado | "Criar hipótese com esta comparação" indisponível sem permissão de editar o quadro, com "Só repórter e editor mudam os quadros." | derivado |
| Vazio | "Nenhuma comparação entre processos", "A análise compara processos quando o acervo tem mais de um sobre a mesma matéria e o mesmo fundamento aparece em mais de um deles." e "Fazer uma pergunta". Análises feitas com instruções anteriores a esta comparação não a trazem, e a tela não a reconstrói | W11, regra 1 |

**Para a Viga, e exceção declarada.** Hoje a análise guarda a comparação só como texto: na redação do achado e na justificativa das duas evidências (formato `geracao_inicial` e `revisao` do `MESA.md`). Para a vista inteira, a tela precisa, por comparação: a referência do fundamento em cada lado, a chave (identificador, data, emissor, versão), o processo de cada lado, a questão, a fase e o desfecho de cada lado, e o resultado das seis conferências da revisão. Até esses campos existirem, a vista mostra o fundamento, os dois lados com as evidências e a conferência pelo veredito da IA, sem a tabela "O que muda" e sem as seis linhas. A tela não lê o texto livre para montar a tabela. A tabela volta quando os campos chegarem, e a tela é conferida de novo nesse ponto.

---


<a id="contas"></a>

## Contas: Minha conta, Equipe e convite (Onda 2)

> **Derivado, 22/11/2026, a pedido do Maestro.** A estrutura vem dos wireframes W08 e W09 do canvas ([regras](#regras-dos-wireframes)) e das decisões do dono sobre o contrato de contas (P27 e P28). Os dados vêm da entrega 2 de Contas (`lancamento/contas-o2`, `92f06f1`; contrato em `.maestro/equipe/CONTRATO_CONTAS.md`, seções 5.4, 5.5, 5.15 e 8.3; formatos em `testes/test_sessoes_conta.py` e `testes/test_equipe.py`). Não há prancha. A aparência sai dos componentes acima, como nas áreas sem tela final, e a conferência é feita contra o wireframe e esta seção. Se o dono quiser outro desenho, vale o dele. O escuro é a mesma tela com os tokens do escuro.

### Onde ficam

- **Minha conta** abre pelo perfil no rodapé da [barra lateral](#barra-lateral) (W08, regra 1). Abaixo de 1280 px, abre pelo mesmo perfil no pé da gaveta. Com a página aberta, o perfil leva `aria-current="page"` e nenhum item de área fica selecionado. No modo `local`, sem contas, não há perfil nem Minha conta.
- **Para o dono**, Minha conta, Equipe e Configurações são três [abas](#abas) no topo da página, nessa ordem; no celular, pílulas de 44 (P20b). Quem não é dono vê só Minha conta, sem a linha de abas. Cada aba aparece pela capacidade que `GET /api/sessao` devolve: Equipe com `equipe-listar`, Configurações com `ia-config`. A Mesa não decide pelo nome do papel.
- O botão "Configurações" do cabeçalho leva à aba Configurações. "Contas de acesso" continua em Configurações, como hoje, até o convite por e-mail da E3 de Contas. **Ela e as operações `contas-*` só saem na integração em que entram juntos o [convite](#convites) e o ["Esqueci a senha"](#aceitar-convite) da E3** (decisão do dono, P30, e ordem combinada com Contas). Nenhuma entrega tira a tela antiga antes disso, nem que uma das duas partes já esteja pronta: sem as duas, o dono fica sem jeito de incluir alguém ou a pessoa fica sem jeito de recuperar a senha. Depois disso, em Configurações fica só a configuração da IA, com a senha da [tabela](#dialogo-senha).
- **Aceitar convite** (`/aceitar/<token>`) e **Redefinir a senha** (`/redefinir/<token>`) são páginas públicas da família do Entrar ([aceitar convite](#aceitar-convite)).

<a id="configuracoes"></a>

**Configurações, em todos os modos** (decisão do dono P43, 23/11/2026). O formulário do provedor e da chave da IA (`#ia-config`) passa a morar só em Configurações, em todos os modos. É o mesmo elemento, com a mesma lógica de salvar, e não uma cópia: sai de Perguntar e entra na página.

- **No modo `local`:** o botão "Configurações" aparece sempre, no cabeçalho a partir de 720 px e, abaixo disso, na gaveta, como o primeiro do grupo ([cabeçalho do celular](#cabecalho-celular)). Não há perfil, Sair nem abas. A página tem a moldura das outras áreas, com o título "Configurações" (serifa 28/600) e, abaixo dele, um painel com "Provedor e chave da IA" (serifa 22/600) e o formulário. Com a página aberta, o botão leva `aria-pressed="true"`, e nenhum item da barra fica selecionado.
- **Com contas:** a mesma seção, como primeiro painel da aba Configurações. "Contas de acesso" continua abaixo dela até a E3 (P30). Salvar segue a [tabela da senha](#dialogo-senha), como hoje. O texto "O provedor e a chave da IA ficam em Perguntar, em Conexão e opções." sai.
- **Em Perguntar, "Conexão e opções"** fica com o estado da conexão, "Verificar conexão", "Encerrar serviço", o aviso "Processamento online pela API do provedor escolhido, cobrado por uso." e os detalhes técnicos. No lugar do formulário, uma linha em 14 `--theme-muted`: "IA: Anthropic (Claude), modelo padrão." (ou o modelo salvo), seguida do [link](#link) "Alterar em Configurações". O link abre a página e põe o foco no título da seção. Quem não tem `ia-config` vê a linha sem o link.

### Moldura comum

| Parte | Medida e token |
|---|---|
| Conteúdo | como nas outras áreas: preenchimento 28 32, intervalo 16; no celular, 16 |
| Título | serifa 28/600 ([título da área](#telas-aprovadas)): "Minha conta"; na Equipe, o nome da redação, com "6 pessoas" em 14 `--theme-muted` alinhado pela base |
| Linha de estado | logo abaixo das abas, `role="status"`: o resultado da última ação, com ✓ de 16 px e o texto em 14/600 `--theme-accent` ("✓ Senha trocada. 1 outra sessão foi encerrada."). A próxima ação a limpa. Erro não vai aqui: fica junto ao que falhou |
| Cartão | o bloco base de [estados](#estados): fundo `--theme-surface`, borda 1 px `--theme-line`, raio 12, preenchimento 16, coluna com intervalo de 8; título `<h2>` 16/600; texto 16; apoio 14 `--theme-muted` |
| Linha com ação | grade `1fr auto`, intervalo de 12, altura mínima 44, alinhada ao centro; entre linhas, filete 1 px `--theme-line` e 8 de folga. Quando o botão não cabe, ele desce para baixo do texto, alinhado à esquerda |
| Grade | duas colunas iguais, intervalo de 16, alinhadas pelo topo, de 1024 px para cima; abaixo, uma coluna |

Cada cartão carrega sozinho. Enquanto carrega, mostra o esqueleto curto; se falha, mostra o erro do serviço de [estados](#estados) no lugar dele, e os outros cartões seguem. Sessão vencida (401) segue o comportamento geral da Mesa.

<a id="minha-conta"></a>

### Minha conta (W08)

Ordem: à esquerda, Perfil, Entrada e segurança e Seus dados; à direita, Onde sua conta está aberta e Seu uso neste mês. Numa coluna: Perfil, Entrada e segurança, Onde sua conta está aberta, Seu uso neste mês e Seus dados.

| Cartão | Conteúdo e comportamento | Dados |
|---|---|---|
| **Perfil** | nome em 16/600; abaixo, o e-mail em 16, ou, na conta migrada sem e-mail, "login ana.lima" em 14 `--theme-muted`; papel e redação em 14 `--theme-muted` ("Repórter · Redação Serena", como o perfil da barra). "Mudar nome" (secundário) troca a linha do nome por um campo "Nome" (44, até 120 caracteres, já preenchido), com "Salvar" (principal) e "Cancelar" (secundário); em branco, "Falta o nome. Escreva o seu nome."; recusa do servidor abaixo do campo. Abaixo, duas caixas de seleção lado a lado, com rótulo acima (W08): **Idioma** (Português, English), que muda o idioma da Mesa, como o botão do cabeçalho, e grava o idioma da conta, com o apoio "Também é o idioma dos e-mails do Vlado."; **Tema** (Do sistema, Claro, Escuro), que fica só neste navegador, como o botão do cabeçalho, e não vai ao servidor (contrato, 2.3). "Do sistema" grava a escolha `sistema`, e com ela a Mesa segue `prefers-color-scheme`, sem piscar ao abrir. Sem nenhuma escolha guardada, a Mesa abre escura, como sempre abriu. A versão anterior deste texto, em que a Mesa sem escolha seguia o sistema, foi barrada pela Coruja (B1) e revertida em `aa2f1d5` por ordem do Maestro. O e-mail muda por "Trocar e-mail" ([abaixo](#minha-conta)) | `conta-ver`; `conta-atualizar` com `nome` ou `idioma` (`pt`, `en`) |
| **Entrada e segurança** | linha "Senha", com "definida há 12 dias" em 14 `--theme-muted` (de `senha_definida_em`; "definida hoje" no dia), e "Trocar senha" (secundário) à direita. Abaixo, a linha "Segundo fator" ([segundo fator](#segundo-fator)). A chave de acesso fica fora (decisão 4) | `conta-ver` |
| **Onde sua conta está aberta** | uma linha por sessão. A sessão em uso vem primeiro, com "Esta sessão" em 14/600 `--theme-muted` à direita e sem botão: sai-se dela por "Sair". As outras seguem na ordem do servidor (uso mais recente primeiro), com "Encerrar" (secundário). Cada linha tem o aparelho em 16 ("Firefox · Linux", "Aplicativo Android": o texto do servidor, `translate="no"`) e, abaixo, em 14 `--theme-muted`, o último uso e o endereço ("ontem, 21h10 · 189.40.12.7"). Com duas sessões ou mais, "Encerrar todas as outras" (secundário) no pé, e o apoio "Encerrar vale na próxima ação daquele aparelho." (contrato, 8.3). Encerrar é imediato, sem diálogo (W08, regra 5); o botão fica "Encerrando…", a linha sai e a linha de estado diz "✓ Sessão encerrada: Edge · Windows." ou "✓ 2 sessões encerradas." Se o servidor responder "Sessão não encontrada.", a lista recarrega, sem erro | `conta-sessoes`; `conta-sessao-encerrar` com `sessao`; `conta-sessoes-encerrar-outras` |
| **Seu uso neste mês** | "Gasto com IA" em 16 e o valor em 16/600 à direita ("R$ 18,40 de R$ 50": gasto sempre com centavos; teto sem centavos quando inteiro, como na barra); [medidor](#medidor) de 6 px com `aria-label` ("37% da cota usada"); apoio "O teto é definido pelo dono da redação." Esgotada, o cartão vira o aviso da cota esgotada da barra ("! Cota esgotada", cores de aviso). Sem a rota, o cartão some. Sempre em reais, nunca em tokens (W08, regra 7) | `GET /api/cota`, bloco `conta` |
| **Seus dados** | **Termos de uso**, só no `piloto` e quando há versão vigente: "Termos de uso: versão 2026-12-01, aceita em 22 de nov." (`conta-ver` → `termos`) e o [link](#link) "Ler os termos", que abre `termos_vigente.endereco` em outra aba. **Exportar meus dados**: o texto "Baixe um arquivo com o que o Vlado guarda sobre você: perfil, aceites dos termos, sessões, participações e a atividade dos últimos 90 dias. O conteúdo das apurações é da redação e não entra." e o botão "Exportar meus dados" (secundário, "Preparando o arquivo…"), que baixa o JSON de `conta-exportar` com o nome que o servidor manda. Linha de estado: "✓ Arquivo baixado."; quando o arquivo traz `incompleto`, mais "Ainda não traz: " e o que o servidor lista. **Excluir a conta**: o botão "Excluir a conta" (destrutivo), que abre o [diálogo de excluir](#excluir-conta). O cartão fica em todas as contas; a última dona ou o último dono só descobre a recusa ao tentar, com a razão | `conta-ver`; `conta-exportar`; `conta-excluir` |

Datas, nesta página e na Equipe: "agora" no primeiro minuto; "hoje, 14h32"; "ontem, 21h10"; "18 de nov., 09h05"; de outro ano, "18 de nov. de 2025". Em inglês, pelo i18n.

**Diálogo "Trocar senha"** (W08, regra 2). É a variante [com senha](#dialogo-senha), com três campos em coluna e intervalo de 16:

- "Senha atual" (`current-password`);
- "Nova senha" (`new-password`), com o apoio "De 12 a 256 caracteres. Pode colar ou usar o gerenciador de senhas.";
- "Repita a nova senha" (`new-password`).

Texto: "As outras sessões desta conta serão encerradas. Esta continua aberta." Aqui a ação fica habilitada com os campos vazios, ao contrário da variante com senha de um campo só: os erros de campo abaixo é que dizem o que falta. Ação principal "Trocar senha" ("Trocando…").

Antes de enviar, a Mesa confere e põe cada erro no seu campo:

- senha atual em branco: "Falta a senha atual. Digite a senha com que você entra hoje.";
- nova senha fora do tamanho: "A senha deve ter de 12 a 256 caracteres.";
- as duas novas diferentes: "As duas senhas não coincidem. Digite a mesma senha nos dois campos."

Respostas do servidor:

- `senha_atual_incorreta`: "Senha atual incorreta. Confira e tente de novo.", no campo da senha atual;
- `bloqueado`: o texto de bloqueio da [tabela](#dialogo-senha);
- sucesso (`{estado: "senha_trocada", sessoes_encerradas: n}`): o diálogo fecha, a lista de sessões recarrega e a linha de estado diz "✓ Senha trocada." seguido de "Nenhuma outra sessão estava aberta.", "1 outra sessão foi encerrada." ou "3 outras sessões foram encerradas."

**Trocar o próprio e-mail** *(derivado, 22/11/2026; E3 de Contas, `1720332`)*. No Perfil, "Trocar e-mail" (secundário) fica à direita da linha do e-mail. Na conta migrada sem e-mail, o botão é "Cadastrar e-mail". Ele abre a variante [com senha](#dialogo-senha) com o título "Trocar o e-mail da conta", dois campos e a ação principal "Enviar confirmação" ("Enviando…"):

- **Campos:** "E-mail novo" (`type="email"`, `autocomplete="email"`, recebe o foco inicial) e "Sua senha".
- **Texto:** "Enviamos um link ao e-mail novo. O e-mail atual continua valendo, inclusive para entrar, até você abrir o link."
- **Erros antes do envio:** em branco, "Falta o e-mail novo. Escreva o endereço que quer usar."; sem a forma de endereço, "E-mail inválido. Confira o endereço, por exemplo ana@redacao.org."

A resposta é sempre `{estado: "confirmacao_enviada"}`, para endereço livre e para endereço que já é de outra conta (contrato, 5.4). O diálogo fecha e a linha de estado diz "✓ Confirmação enviada ao e-mail novo. Abra o link em até 60 minutos." A tela não diz mais nada, para não contar se o endereço já tem conta. Com o transporte `tela`, a resposta traz `link`, e o diálogo mostra o link como no convite (limitação da seção 8.1 do contrato). O título é "Confirme o e-mail ana@redacao.org" e o texto "Abra o link para confirmar o e-mail novo. Ele vale 60 minutos, uma única vez, e não será mostrado de novo." (proposta do Vitral em `249e5c9`, aceita em 22/11/2026). Um pedido a cada 5 minutos: a recusa do servidor vai ao erro do diálogo.

**Página "Confirmar e-mail"** (`/confirmar-email/<token>`): mais uma seção do Entrar, como [aceitar convite](#aceitar-convite).

- Ao abrir, a página chama `email-confirmar` com o token.
- Sucesso: o cartão do Entrar com o título "E-mail confirmado", o texto "O e-mail da sua conta foi trocado. Use o novo e-mail para entrar." e o [link](#link) "Ir para a Mesa". A sessão aberta continua.
- Link inválido, usado ou vencido: o estado "Este link não vale mais", com o texto do servidor ("Link inválido, usado ou vencido. Peça outro em Minha conta.") e o link "Ir para a entrada".
- Textos aceitos em 22/11/2026 sobre `7c2345c` (Lume), no lugar dos que esta seção trazia.

<a id="segundo-fator"></a>

### Segundo fator (E4a)

*(Derivado, 22/11/2026.)* Estrutura do W08 (linha "Código do autenticador ativo" e "Códigos de reserva") e dos passos 2 e 3 do W10. Dados da E4a de Contas (`lancamento/contas-o2` `85b900a`; contrato, 8.2 e 12): TOTP de 6 dígitos e dez códigos de reserva de uso único, no formato `ABCD-EFGH-JKLM-NPQR` (19 caracteres; a tela mostra o que o servidor manda). A chave de acesso segue fora (decisão 4). O fator é obrigatório para dono e editor no `piloto` pela [pendência](#pendencia-fator), que entra num commit próprio de Contas.

**Na linha "Segundo fator" de Entrada e segurança** (Minha conta), conforme `conta-ver` → `segundo_fator`:

| Estado | Linha | Ações |
|---|---|---|
| Desligado (`ativo: false`) | "○ Segundo fator desligado" e, em 14 `--theme-muted`, "Um código do aplicativo autenticador, além da senha, na entrada." Quando `GET /api/sessao` não traz `conta-fator-remover` em `capacidades` (dono e editor, em todo modo), vem também "Depois de cadastrado, o segundo fator não pode ser removido no seu papel." A tela não diz que o fator é obrigatório: no `local-contas` ele é opcional, e onde é obrigatório quem não o tem não chega a Minha conta, porque vai à [página da pendência](#pendencia-fator) (B1 da Coruja sobre `8ce862e`). | "Cadastrar" (secundário) |
| Ligado | "✓ Código do autenticador ativo" e, em 14 `--theme-muted`, "desde 12 de nov. · 8 códigos de reserva" (`ativado_em`, `codigos_restantes`) | "Gerar novos códigos" e "Trocar de aparelho" (secundários); "Remover" (destrutivo) só quando `GET /api/sessao` traz `conta-fator-remover` em `capacidades`, que nunca vem para dono e editor |
| Ligado, com 3 códigos ou menos | igual ao anterior, mais a linha "! Restam 2 códigos de reserva. Gere novos." em 14/600 `--theme-warning`; com 1, "! Resta 1 código de reserva. Gere novos."; com nenhum, "! Não restam códigos de reserva. Gere novos." | as mesmas |

**Cadastrar** abre o diálogo "Cadastrar o segundo fator", da família do [diálogo](#dialogo). A largura é 480, e no celular a tela cheia menos 16 px de cada lado. A rubrica marca o passo ("PASSO 1 DE 3"), como no W10.

1. **Senha** (variante [com senha](#dialogo-senha)). Texto: "Confirme a sua senha para começar." Ação principal "Continuar" (`conta-fator-iniciar {senha}`).
   - Em "Trocar de aparelho", o mesmo passo tem também o campo "Código do aparelho atual", que aceita o código do aplicativo atual ou um código de reserva, e o texto "O aparelho atual vale até o novo ser confirmado."
2. **Ler o código.** O servidor manda `segredo` e `otpauth` uma vez só.
   - **Texto:** "Abra o aplicativo autenticador do celular e leia o código abaixo. Se não puder ler, digite a chave."
   - **Código QR:** um quadrado de 200 px, centrado, desenhado como descrito abaixo.
   - **Chave em texto:** abaixo do QR, "Chave", com a chave em grupos de 4 caracteres separados por espaço. Usa 16/600, com espaçamento de letra de 1 px e algarismos tabulares, além de `translate="no"`, de `user-select: all` e de "Copiar chave" (secundário).
   - **Campo:** "Código de 6 dígitos", com `inputmode="numeric"`, `autocomplete="one-time-code"` e até 6 caracteres. Recebe o foco.
   - **Apoio:** "Este cadastro vale por 15 minutos. Depois, comece de novo."
   - **Ação:** principal "Confirmar" (`conta-fator-confirmar {codigo}`).
3. **Códigos de reserva** (`codigos_de_reserva`, mostrados uma vez).
   - **Título:** "Guarde os códigos de reserva".
   - **Texto:** "Cada código entra uma vez, se você perder o celular. Eles não aparecem de novo."
   - **Bloco dos códigos:** borda 1 px tracejada `--theme-input-line`, raio 8, preenchimento 12 e grade de duas colunas só quando cada coluna comporta um código inteiro: cada coluna tem no mínimo 15 rem (240 px com a fonte padrão), com 16 px entre colunas, e a segunda abre a partir de 522 px de largura do bloco, contando preenchimento e borda (`repeat(auto-fit, minmax(min(100%, 15rem), 1fr))`). Com a fonte do usuário maior, o limite cresce junto (D2 da Coruja, combinado com o Lume, `8956e0c`). Abaixo disso, uma coluna, o que inclui o celular e o cartão da [pendência](#pendencia-fator). Cada código fica numa linha só, sem quebrar (`white-space: nowrap`), em 16/600, com espaçamento de letra de 1 px, algarismos tabulares e `translate="no"`.
   - **Ações:** "Copiar" e "Baixar" (secundários, lado a lado, como no W10). "Baixar" gera no navegador um arquivo `vlado-codigos-de-reserva.txt`, sem rede. Depois vem "Já guardei" (principal).
   - **Fechar:** neste passo Esc não fecha nem há "Cancelar"; só "Já guardei" fecha, porque os códigos não voltam. Ao fechar, a linha de estado diz "✓ Segundo fator ativado."

| Resposta | O que a tela faz |
|---|---|
| 403 `codigo_invalido` | erro no campo do código: "Código incorreto. Confira no aplicativo e digite o código que aparece agora." |
| 429 `bloqueado` | erro do diálogo: "Muitos códigos errados seguidos. Por 15 minutos, as ações que pedem o código ficam bloqueadas para a sua conta." A ação fica indisponível |
| "Comece de novo o cadastro do segundo fator." | o cadastro passou de 15 minutos: o diálogo volta ao passo 1, com esse texto na linha de estado do diálogo |
| senha | como na [variante com senha](#dialogo-senha) |

**Gerar novos códigos** é a variante com senha com mais um campo, "Código do aplicativo" (aceita também um código de reserva). O título é "Gerar novos códigos de reserva?", o texto "Os códigos atuais param de valer." e a ação principal "Gerar códigos" (`conta-fator-codigos {senha, codigo}`). A resposta abre o passo 3 acima.

**Remover** é a variante com senha destrutiva. O título é "Remover o segundo fator?", o texto "A entrada volta a pedir só a senha. Você pode cadastrar de novo quando quiser." e a ação "Remover segundo fator" (`conta-fator-remover {senha}`). Resultado: "✓ Segundo fator removido."

**O código QR, sem biblioteca de fora.**

- **Desenho:** SVG em linha, gerado no navegador a partir de `otpauth`. Um `<path>` só, com módulos quadrados de tamanho inteiro (`shape-rendering: crispEdges`) e zona de silêncio de 4 módulos.
- **Cores:** módulos `#000000` sobre fundo `#ffffff` nos dois temas. O leitor do celular precisa de escuro sobre claro, e isto é exceção aos tokens, só para o QR.
- **Acessibilidade:** `role="img"` e `aria-label` "Código QR para o aplicativo autenticador. Se não puder ler, use a chave em texto abaixo." A chave em texto é a alternativa, e sem ela o cadastro não se completa.
- **Nada guardado:** o QR e a chave não vão para `localStorage`, histórico nem registro. Somem quando o diálogo fecha.
- **O que o Frontend precisa** para gerar o QR no navegador: um codificador QR, porque a Mesa não tem um. Há dois caminhos.
  - **Recomendado:** pôr em `interface/vendor/` um codificador de código aberto de arquivo único e sem dependências, servido pela própria Mesa, sem CDN, com a licença ao lado. Por exemplo, o "QR Code generator library" do Project Nayuki, licença MIT. Entrar código de terceiros pede o aval do Maestro.
  - **Alternativa:** o Frontend escreve um codificador próprio, em modo byte, correção M, versões 1 a 10, com teste contra vetores conhecidos.

  O endereço tem uns 150 caracteres, o que pede a versão 7 ou 8.

  **Aval do Maestro (22/11/2026):** vale o caminho recomendado. Entra em `interface/vendor/` o "QR Code generator library" do Project Nayuki (MIT, um arquivo), com versão fixa, o hash do arquivo registrado, o arquivo de licença ao lado e a linha correspondente em `docs/AVISOS_DE_LICENCA.md`. Quem vendoriza é o Frontend que fizer o cadastro do fator.

<a id="entrar-fator"></a>

**Entrar, passo 2.** Quando `entrar` responde `{estado: "segundo_fator"}`, o cartão do Entrar troca o formulário. O foco vai para o campo:

- título "Confirme que é você";
- texto "Digite o código de 6 dígitos do aplicativo autenticador.";
- campo "Código do aplicativo" (48 px, `inputmode="numeric"`, `autocomplete="one-time-code"`);
- abaixo do campo, o [link](#link) "Usar um código de reserva". Ele troca o rótulo para "Código de reserva" e o `inputmode` para `text`, aceita espaço, hífen e minúsculas, e passa a ler "Usar o código do aplicativo";
- apoio em 14 `--theme-muted`: "Você tem 5 minutos para digitar o código.", a 4 px do link acima. O campo, o link e o apoio formam um grupo só, com 8 px entre o campo e o link; o intervalo de 18 px do formulário fica só entre os grupos;
- ação principal grande "Entrar" (`entrar-segundo-fator {codigo}`);
- link "Entrar com outra conta", que volta ao formulário.

Respostas:

- 403 `codigo_invalido`: no campo, "Código incorreto. Confira no aplicativo e tente de novo."
- 401 `entrada_expirada`: volta ao formulário de login com a caixa de aviso "A entrada expirou. Digite o login e a senha de novo." O cartão do segundo passo vence em 5 minutos ou com cinco códigos errados.
- 429 `bloqueado`: caixa de aviso com o texto do servidor.
- 200: vai a `destino`, como a entrada.

**Redefinir a senha com segundo fator.** A página não sabe de antemão se a conta tem o fator. Ela envia `{token, senha}`. Se a resposta for 403 `codigo_invalido` sem código enviado, o campo de senha fica preenchido e aparece, abaixo dele, o campo "Código do aplicativo ou de reserva", com o texto "Esta conta tem segundo fator. Digite o código do aplicativo ou um código de reserva." O foco vai para o campo novo, e a ação reenvia `{token, senha, codigo}`. Com o código enviado, `codigo_invalido` põe "Código incorreto. Confira e tente de novo." no campo. O link de recuperação pedido por um dono retira o fator e não pede código (contrato, 12).

<a id="excluir-conta"></a>

**Excluir a conta** (E4b-3, `conta-excluir {senha, nome}`). É a variante [com senha](#dialogo-senha) destrutiva, com o campo do nome antes do da senha, como em "Apagar definitivamente".

- **Título:** "Excluir a sua conta?"
- **Texto, antes dos campos** (decisão 10 do contrato; o texto depende da definição de quem responde pela LGPD, a D6, que está com o dono do projeto, e muda se ela mudar): "Você sai da Mesa agora e não entra mais com esta conta. Suas notas, revisões e conversas ficam com a redação, e a Mesa passa a mostrar o autor como «Conta excluída». O seu nome continua gravado nos registros já feitos e nos backups, que não podem ser reescritos."
- **Campos:** "Digite o seu nome, «Ana Lima», para confirmar" (16/400, só o nome em 600), depois "Sua senha".
- **Ação:** "Excluir a conta" (destrutiva, "Excluindo…"), habilitada só com o nome conferido e a senha preenchida.

Respostas:

| Resposta | O que a tela faz |
|---|---|
| sucesso | a sessão acaba na mesma resposta: a Mesa vai ao Entrar, que mostra na caixa de aviso "A sua conta foi excluída." |
| nome que não confere (o servidor confere antes da senha, e o erro não conta como senha errada) | erro no campo do nome, com o texto do servidor; o foco volta a ele |
| 400 `ultimo_dono` | erro do diálogo: "A redação precisa de ao menos um dono ativo. Antes de excluir a sua conta, torne outra pessoa dono na Equipe." |
| senha errada e bloqueio | como na [variante com senha](#dialogo-senha) |

<a id="pendencia-termos"></a>

**Pendência: termos novos** (E4b-1, só no `piloto`). Quando `GET /api/sessao` traz `termos` em `pendencias`, a página é `GET /conta/termos`, da mesma família da [pendência do segundo fator](#pendencia-fator): marca, cartão centrado de até 440 px e rodapé. Com as duas pendências, a de termos vem primeiro.

- **Rubrica:** "ANTES DE CONTINUAR".
- **Título:** com aceite anterior (`conta-ver` → `termos` não nulo), "Os termos de uso mudaram"; sem nenhum, "Aceite os termos de uso".
- **Texto:** "Para continuar usando o Vlado, leia e aceite os termos de uso e a política de privacidade do teste (versão 2026-12-01)." (`termos_vigente.versao`). Abaixo, o [link](#link) "Ler os termos", aberto em outra aba, para `termos_vigente.endereco`.
- **Caixa de marcar:** "Li e aceito os termos de uso e a política de privacidade do teste." Sem marcar, ao enviar: "Falta aceitar os termos. Marque a caixa para continuar."
- **Ação:** principal grande "Aceitar e abrir a Mesa" (`conta-termos-aceitar {versao}`; sem senha). Depois, a pendência do fator, se houver, ou `/`.
- **Quem não quer aceitar** (ressalva B2 do contrato): abaixo da ação, em 14 `--theme-muted`, "Prefere não aceitar? Você pode baixar seus dados ou excluir a conta.". "Baixar seus dados" e "excluir a conta" são [links](#link): o primeiro baixa o arquivo, como em Minha conta; o segundo abre o [diálogo de excluir](#excluir-conta). Os dois só aparecem quando `pendencias` não traz `segundo_fator`. Com a pendência do fator, o servidor recusa as duas operações (403 `pendencia_de_conta`), e no lugar dos links fica "Depois de cadastrar o segundo fator, você poderá baixar seus dados ou excluir a conta." (B1 da Coruja sobre `b7eee49`).
- **Sair:** o link "Sair", no pé do cartão.
- **Respostas:** `termos_desatualizados` relê a página com a versão nova e mostra "Os termos mudaram enquanto você lia. Confira a versão nova e marque de novo."; as demais vão à caixa de aviso.
- A sessão só alcança `conta-ver`, `conta-termos-aceitar`, `conta-exportar` e `conta-excluir` (contrato, 12); as duas últimas, só sem a pendência do fator.

**Contas inativas** (E4b-4) são só do servidor: o aviso de 180 dias sai por e-mail, com texto de Contas, e a Mesa não tem tela para isso. O que a pessoa vê é a conta desativada, como qualquer outra, e a linha da atividade acima.

<a id="pendencia-fator"></a>

**Pendência: cadastro obrigatório.** Quando `GET /api/sessao` traz `segundo_fator` em `pendencias` (dono e editor no `piloto`, sem o fator), a Mesa não abre nenhuma área. A pendência vale ao entrar e ao aceitar um convite como dono ou editor, que vira o passo 2 do W10. Em vez das áreas, mostra uma página da família do Entrar: marca, cartão centrado de até 440 px e rodapé.

- **Rubrica:** "ANTES DE CONTINUAR".
- **Título:** "Proteja a conta com um segundo passo" (W10, passo 2).
- **Texto:** "Para quem é dono ou editor, o Vlado pede, além da senha, um código do aplicativo autenticador. Cadastre agora para abrir a Mesa."
- **Os três passos:** os mesmos do cadastro, no próprio cartão em vez de diálogo, com a rubrica "PASSO 1 DE 3".
- **Fim:** depois de "Já guardei", a ação "Abrir a Mesa" leva a `/`, que já abre a Mesa, porque a pendência acabou.
- **Sair:** o link "Sair", no pé do cartão, encerra a sessão.
- **Celular:** os passos são telas em sequência (W10, regra 8).

Qualquer outra operação responde 403 `pendencia_de_conta` (contrato, 4.3). Se uma chegar, a Mesa volta a esta página. Combinado com Contas em 22/11/2026: a página é `GET /conta/segundo-fator`. Ela serve o mesmo `entrar.html` de `/entrar`, sem dado de conta no HTML, e o script vê `pendencias: ["segundo_fator"]` em `GET /api/sessao`. Com a pendência, `GET /` responde 303 para ela. A sessão só alcança `GET /api/sessao`, `sessao-sair`, `conta-ver`, `conta-fator-iniciar` e `conta-fator-confirmar`. A página não precisa de mais nada: o texto não leva nome nem papel, e "Sair" usa `sessao-sair`. Não é uma seção da Mesa, e a Mesa (`index.html`) não abre com a pendência.

Na atividade da Equipe: `fator_ativado` "Beltrano ativou o segundo fator"; `fator_removido` "Beltrano removeu o segundo fator"; `fator_codigos_gerados` "Beltrano gerou novos códigos de reserva"; `aparelho_novo` "Beltrano entrou de um aparelho novo"; `codigo_reserva_usado` "Beltrano entrou com um código de reserva"; `fator_bloqueado` "O segundo fator de Beltrano foi bloqueado por muitos códigos errados"; `login_protegido` "A entrada de Beltrano foi protegida por muitas tentativas".

**Detalhes aceitos sobre `cd2337d`** (Vitral, 22/11/2026):

- No diálogo, o passo 1 não repete título: o do diálogo ("Cadastrar o segundo fator" ou "Trocar de aparelho") basta. O passo 3 tem o título "Guarde os códigos de reserva".
- Linhas de estado do diálogo: "Chave copiada.", "Códigos copiados.", "Arquivo baixado." e, quando a área de transferência recusa, "Não deu para copiar. Selecione e copie à mão."
- Se o gerador do QR não carregar, no lugar dele: "Não deu para desenhar o código QR. Digite a chave abaixo no aplicativo." A chave em texto basta.
- Em "Trocar de aparelho", com o código atual em branco, a recusa vem antes do envio: "Falta o código do aparelho atual. Digite o código do aplicativo ou um código de reserva."

<a id="equipe"></a>

### Equipe (W09)

Só para quem tem `equipe-listar`, isto é, o dono. Os dados vêm de `equipe-listar` (`redacao`, `pessoas`, `gasto`, `convites`, que sai vazio na E2).

**Perfil antigo.** Se alguém tem o papel `convidado`, um aviso em linha da Mesa (`.notice`, cores de aviso, `role="status"`) aparece acima da tabela: "2 pessoas ainda têm o perfil antigo de convidado: perguntam só nas apurações liberadas e veem só as próprias conversas. Escolha um papel para cada uma ou remova da redação." (contrato, 2.4, decisão 1).

| Parte | Medida e conteúdo |
|---|---|
| Tabela, de 1024 px para cima | cartão com tabela, como a lista de [Documentos](#documentos): células com preenchimento 12 16 e filete 1 px `--theme-line`; cabeçalho 14/600 `--theme-muted` em fundo `--theme-reading`. Colunas: Pessoa, Papel, Apurações, Uso no mês e a ação, que tem rótulo só para leitor de tela ("Ações") |
| Pessoa | nome em 16 (na própria linha, seguido de "(você)" em 14 `--theme-muted`); abaixo, e-mail ou "login rui.castro" em 14 `--theme-muted`, `translate="no"`. Quando a conta não está ativa, vem uma terceira linha, sempre com sinal e texto, em 14 `--theme-muted`: "○ Desativada"; "◐ Aguardando a senha"; com o link vencido, "◐ Link de ativação vencido" |
| Papel | caixa de seleção de 44 px e largura mínima de 220 px, para caber "Convidado (perfil antigo)" inteiro, também com a linha de Gerenciar aberta; rótulo só para leitor de tela ("Papel de Ana Lima"): Dono, Editor, Repórter, Leitor. No perfil antigo, "Convidado (perfil antigo)" aparece selecionado e indisponível: não se escolhe de novo. Na própria linha, o papel é só texto: o próprio papel muda por outro dono |
| Apurações | "Todas" para dono (`casos` nulo); para os demais, os títulos do catálogo separados por vírgula, até três, e depois "e mais 2"; sem nenhuma, "Nenhuma" em `--theme-muted` |
| Uso no mês | "R$ 18,40" (`gasto.gasto_brl`); "—" quando `gasto` vem nulo. Com teto próprio, abaixo, em 14 `--theme-muted`, "teto R$ 30". Esgotado: "! R$ 50,00 · esgotada" em 14/600 `--theme-warning` |
| Ação | "Gerenciar": `<button>` com cara de [link](#link) (16/600 `--theme-accent`, sublinhado, altura mínima 44), `aria-expanded` e `aria-controls`. A própria linha não tem |
| Lista, abaixo de 1024 px | um cartão por pessoa, preenchimento 16, intervalo 8: nome em 600, e-mail e situação em 14 `--theme-muted`, "Papel" com rótulo visível e caixa de largura cheia, apurações e uso em 14, e "Gerenciar" (secundário, largura cheia) |

**Mudar o papel.** A mudança vale ao escolher. Sem dono no meio, vai direto e a linha de estado diz "✓ Ana Lima agora é Editor. Vale na próxima ação."; enquanto o pedido corre, a caixa fica indisponível. Com dono no meio (o papel atual ou o novo), abre o diálogo [com senha](#dialogo-senha). Do perfil antigo para qualquer papel, abre antes a variante simples: "Converter Cora Dias em Leitor?", com o texto "Leitor lê também o caderno, os achados e o texto das apurações de que participa." e a ação "Converter" (princípio 9 do contrato: a leitura nova é decisão de quem converte). Cancelar ou receber uma recusa devolve a caixa ao papel anterior. Recusa `ultimo_dono`: o texto do servidor na linha de estado, em 14 `--theme-danger`, com `role="alert"`.

**Textos de estado** (linha de estado, aceitos em 22/11/2026 sobre `8a45f08`): "✓ Nome atualizado.", "✓ Idioma da conta salvo.", "✓ Teto de Ana Lima salvo.", "✓ Ana Lima volta a usar o teto padrão.", "✓ Teto padrão salvo.", "✓ A conta de Ana Lima foi desativada." ou "reativada.", "✓ Ana Lima não faz mais parte da redação." Sem marca de gênero no nome da pessoa.

**Gerenciar** abre uma linha abaixo da pessoa, que ocupa todas as colunas. Fundo `--theme-background`, preenchimento 16, três blocos em grade com intervalo de 24; numa coluna no celular. Cada bloco tem título 14/600 maiúsculo em `--theme-muted`:

| Bloco | Conteúdo |
|---|---|
| APURAÇÕES | as apurações da pessoa, uma por linha com ação. Quando ela é a responsável, a linha mostra "responsável" em 14 `--theme-muted` e não tem "Retirar", com o apoio "Quem é responsável não sai da apuração por aqui." Nas demais, "Retirar" (secundário). Abaixo, "Incluir em" (caixa com as apurações da redação em que a pessoa não está) e "Incluir" (secundário). Para dono, só o texto "Todas as apurações da redação." Resultado: "✓ Ana Lima agora participa de Campo Verde." ou "✓ Ana Lima não participa mais de Campo Verde." (`caso-incluir`, `caso-retirar` com `caso` e `conta`) |
| TETO MENSAL | campo "Teto de gasto com IA, em reais", de 44 px e até 160 px de largura, `inputmode="decimal"`, aceitando "30" e "30,50"; "Salvar" (secundário). Apoio: "Padrão da redação: R$ 50. Não passa do teto da redação." Com teto próprio, "Usar o padrão" ([link](#link)) o apaga. A Mesa envia `teto_brl` como texto com ponto ("30.50"), nunca como número, e `null` para voltar ao padrão (`equipe-teto` com `conta`). Recusa: o texto do servidor abaixo do campo |
| ACESSO | conta ativa: "Desativar" e "Remover da redação" (destrutivos), e "Recuperar acesso" ([recuperar](#recuperar)); os botões quebram linha quando a coluna é estreita, como em `259fd1b`, aceito. Conta desativada: "Reativar" (secundário, sem diálogo) e "Remover da redação". Apoio: "Desativar encerra as sessões e para as perguntas em curso; as apurações ficam. Remover exclui a conta." Os diálogos estão na [tabela](#dialogo-senha) |

Criar conta com link e "Recuperar acesso" continuam em "Contas de acesso", em Configurações, até a integração em que entram juntos o convite e o "Esqueci a senha" (P30; [exceções](#contas-excecoes)).

**Abaixo da tabela**, em grade de duas colunas:

| Cartão | Conteúdo | Dados |
|---|---|---|
| **Gasto com IA neste mês** | com `gasto`: "R$ 24,50 de R$ 150" (16/600), o [medidor](#medidor) e o apoio "Cota da redação, definida por quem administra o serviço." Com `gasto` nulo, sem valor nem medidor, o apoio "O gasto da redação aparece aqui quando o serviço passar a contá-lo por redação. O de cada pessoa está na tabela." (contrato, 4.5). Abaixo, em todos os casos, o campo "Teto padrão por pessoa, em reais", igual ao do Gerenciar, com "Salvar"; vazio quer dizer o teto da instalação, e o apoio diz isso | `equipe-listar`; `equipe-teto` sem `conta` |
| **Gasto na chave própria** (P40 b) | dentro do cartão "Gasto com IA neste mês", abaixo do medidor, quando a redação usa chave própria: a linha "Chave própria da redação" com o total (16, valor 600) e o apoio "Pago pela chave da redação: não entra na cota do serviço." (14 `--theme-muted`). Na tabela, em "Uso no mês", logo abaixo do gasto da pessoa e antes do "teto R$ 30", em 14 `--theme-muted`: "dos quais R$ 3,25 com a chave própria". A frase qualifica o valor e vem colada a ele (ressalva sobre `d6cfa77`, que a pôs depois do teto). O valor de cima já inclui essa parte, porque o teto da pessoa vale para as duas chaves (ressalva da Coruja, 23/11/2026); o total da redação na chave própria, ao contrário, não entra na cota do serviço. Sem chave própria, nada disso aparece. Textos do Vitral em `8860212`, aceitos em 23/11/2026 | `equipe-listar` |
| **Atividade recente** | largura das duas colunas. As cinco últimas ações, uma por linha: a frase em 16 e, à direita, a data em 14 `--theme-muted`. Depois, "Mostrar mais" (secundário), que traz 50 de cada vez enquanto houver `proximo`. Só acessos e administração, nunca conteúdo (W09, regra 8). Sem nenhuma: "Nenhuma ação registrada ainda." | `equipe-atividade` com `limite` e `antes` |

Frases da atividade. "Fulano" é `por_nome` e "Beltrano" é `conta_nome`; quando os dois são a mesma conta, a frase usa só o nome dela.

- Sem nome (conta removida): "uma conta removida".
- Sem `por` de conta (operador ou migração): "Quem administra o serviço".

| Tipo | Frase |
|---|---|
| `papel_alterado` | Fulano mudou o papel de Beltrano |
| `conta_desativada` / `conta_reativada` | Fulano desativou / reativou a conta de Beltrano |
| `conta_excluida` | Fulano removeu Beltrano da redação; quando a própria pessoa excluiu a conta, "Uma pessoa excluiu a própria conta" (o nome já não existe) |
| `termos_aceitos` | Beltrano aceitou os termos de uso |
| `conta_desativada_por_inatividade` | A conta de Beltrano foi desativada por inatividade |
| `conta_criada` | Fulano criou a conta de Beltrano |
| `participacao_incluida` / `participacao_retirada` | Fulano incluiu Beltrano numa apuração / retirou Beltrano de uma apuração |
| `responsavel_alterado` | Fulano mudou o responsável de uma apuração |
| `teto_alterado` | Fulano mudou um teto de gasto |
| `senha_trocada` / `senha_definida` | Beltrano trocou / definiu a senha |
| `sessao_encerrada_a_distancia` | Beltrano encerrou sessões em outros aparelhos |
| `conta_atualizada` | Beltrano atualizou o perfil |
| `recuperacao_emitida` | Fulano gerou um novo link de ativação para Beltrano |
| `login_bloqueado` | A entrada de Beltrano foi bloqueada por muitas tentativas |
| `sessao_encerrada` | Beltrano saiu da Mesa |
| `acesso_alterado` | Fulano mudou o acesso de Beltrano |
| `caso_atribuido` | Fulano atribuiu uma apuração a uma pessoa |
| `caso_criado` | Fulano criou uma apuração |
| `primeiro_admin` | A redação foi criada, com Beltrano como dono |
| `migracao_contas` | As contas foram migradas para o novo modelo de acesso |
| `redacao_criada` | A redação foi criada |
| `redacao_suspensa` / `redacao_reativada` / `redacao_encerrada` | A redação foi suspensa / reativada / encerrada por quem administra o serviço |
| qualquer outro | Ação de administração |

As frases de `sessao_encerrada` a `redacao_*` foram propostas pelo Vitral em `8a45f08` (achado D1 da Coruja: tipos que a E2 grava e esta tabela não previa) e aceitas pelo Design em 22/11/2026. No celular, a data vem sempre abaixo da frase, nunca ora ao lado, ora abaixo.

**Só o dono na redação**: a tabela tem uma linha. Antes dos convites, abaixo dela vem o texto da exceção do convite; depois, nada: "Convidar pessoa" está no topo.

<a id="recuperar"></a>

### Recuperar o acesso de outra pessoa (E3)

*(Derivado, 22/11/2026.)* Entra com a E3 de Contas (`1720332`; contrato, 8.2 e 12) e, como os convites, só na integração em que as `contas-*` saem (P30). Recuperar sempre envolve duas partes e pede a senha de quem age. A recuperação da própria conta não é por aqui: é "Esqueci a senha" ou "Trocar senha".

**Onde fica.** No bloco ACESSO do Gerenciar, "Recuperar acesso" é um botão secundário ao lado de "Desativar" e "Remover da redação". Só aparece para conta ativa: a desativada é reativada antes. O apoio do bloco ganha uma frase: "Recuperar manda à pessoa um link para criar uma senha nova; nada muda na conta até ela usar o link." Quando a pessoa é dono, vem mais uma: "Para um dono, outro dono precisa confirmar em até 24 horas."

**Diálogo.** É a variante [com senha](#dialogo-senha), com o título "Recuperar o acesso de Rui Castro?" e a ação principal "Recuperar acesso" ("Recuperando…"). O texto depende do caso. A Mesa sabe o papel da pessoa e o modo (`GET /api/sessao`, `modo`):

| Caso | Texto |
|---|---|
| Não é dono, serviço hospedado | "Rui Castro recebe por e-mail um link para criar uma senha nova. O link vale 24 horas. Nada muda na conta até ele ser usado." |
| Não é dono, Mesa instalada (`local-contas`) | "A Mesa mostra a você um link para Rui Castro criar uma senha nova. Entregue por um canal seguro. O link vale 24 horas." (P33) |
| É dono | "Rui Castro é dono. O pedido espera até 24 horas que outro dono, que não seja você, o confirme. Só então sai o link." |

Respostas de `equipe-recuperar` (`{conta, senha}`):

| Resposta | O que a tela faz |
|---|---|
| `{estado: "enviada", envio: "enviado"}` | o diálogo fecha; linha de estado "✓ Link de recuperação enviado para Rui Castro. Vale 24 horas." |
| `{estado: "enviada", envio: "falha"}` | o diálogo fecha; linha de estado em cores de aviso: "! O e-mail para Rui Castro não saiu. Peça de novo em alguns minutos." |
| `{estado: "confirmada", link}` (só na Mesa instalada) | o diálogo troca o formulário pelo link, como no convite com `tela`: título "Entregue o link a Rui Castro"; texto "Mande por um canal seguro. O link vale 24 horas, uma única vez, e não será mostrado de novo. Nada muda na conta até ele ser usado."; o link só de leitura, "Copiar link" e "Já enviei" |
| `{estado: "aguardando_confirmacao", recuperacao}` | o diálogo fecha; linha de estado "✓ Pedido registrado. Outro dono precisa confirmar a recuperação de Rui Castro até 23 de nov., 19h40."; o pedido aparece no cartão abaixo |
| 400 `recuperacao_pelo_operador` | erro do diálogo com o texto do servidor ("Essa recuperação é feita pelo operador do serviço, pelo terminal."); a ação fica indisponível e sobra "Cancelar". Não é erro de quem pediu: não há terceiro dono, ou o link não tem como chegar à pessoa |
| outras recusas 400 | o texto do servidor no erro do diálogo ("Já há um pedido de recuperação à espera de confirmação para essa conta.", "Um link de recuperação acabou de ser enviado a essa pessoa. Espere alguns minutos.") |
| senha | como na [variante com senha](#dialogo-senha) |

**Cartão "Recuperações à espera de confirmação".** Fica acima da tabela, depois do aviso do perfil antigo, só quando `equipe-listar` traz `recuperacoes`. É o bloco base do cartão, com uma linha com ação por pedido:

- **Linha:** o nome da pessoa em 16 (`conta_nome`). Abaixo, em 14 `--theme-muted`: "pedido por Ana Lima em 22 de nov., 19h40 · vence em 23 de nov., 19h40" (`pedida_por_nome`, `pedida_em`, `expira_em`).
- **Ação:** "Confirmar" (secundário) para quem não é nem quem pediu nem a própria pessoa (`pedida_por` e `conta` contra a conta da sessão). Para essas duas, no lugar do botão, "Aguardando outro dono" em 14 `--theme-muted`. O servidor recusa do mesmo jeito.
- **Diálogo de "Confirmar":** a variante com senha, com o título "Confirmar a recuperação do acesso de Rui Castro?" e a ação principal "Confirmar recuperação". O texto é "Ana Lima pediu em 22 de nov., 19h40. Ao confirmar, Rui Castro recebe por e-mail um link para criar uma senha nova, válido por 24 horas." Na Mesa instalada, a segunda frase vira "Ao confirmar, a Mesa mostra a você o link para entregar a Rui Castro."
- **Respostas** (`equipe-recuperar-confirmar` com `{recuperacao, senha}`): `enviada` e `confirmada` como na tabela acima. "Pedido de recuperação não encontrado." (vencido, de outra redação, ou de quem deixou de ser dono) vai ao erro do diálogo, e a lista recarrega ao fechar.
- O pedido não se cancela pela tela: ele vence sozinho em 24 horas.

Na atividade:

| Tipo | Frase |
|---|---|
| `recuperacao_pedida` | Fulano pediu a recuperação do acesso de Beltrano |
| `recuperacao_confirmada` | Fulano confirmou a recuperação do acesso de Beltrano |
| `senha_redefinida` | Beltrano criou uma senha nova pelo link |
| `redefinicao_pedida` | Beltrano pediu um link para criar uma senha nova |
| `email_troca_pedida` | Beltrano pediu para trocar o e-mail |
| `email_trocado` | Beltrano trocou o e-mail |

Nenhuma frase leva endereço de e-mail.

<a id="convites"></a>

### Convites na Equipe (W09, E3)

*(Derivado, 22/11/2026.)* Entram com a E3 de Contas (`281a468`; `testes/test_convites.py`; contrato, 8.1 e 12). As `contas-*` e "Contas de acesso" saem só na integração em que entram juntos o convite e o "Esqueci a senha" da E3 (P30 e ordem combinada com Contas; ver [onde ficam](#contas)); com ela, a exceção do convite deixa de valer.

**"Convidar pessoa"** é botão principal, à direita do título da Equipe, alinhado pela base (W09). No celular, fica abaixo do título, com largura cheia e 48 px. O título ganha a contagem dos pendentes: "6 pessoas · 2 convites pendentes".

**Diálogo "Convidar pessoa"**, da família do [diálogo](#dialogo), com a ação principal "Convidar" ("Convidando…"). Os campos vêm em coluna, com intervalo de 16:

| Campo | Comportamento |
|---|---|
| E-mail | `type="email"`, `autocomplete="off"`, `translate="no"`; recebe o foco inicial |
| Papel | caixa com Leitor, Repórter, Editor e Dono; vem em Leitor, o menor alcance. Abaixo, em 14 `--theme-muted`, uma linha que diz o que o papel escolhido faz, tirada da regra 1 do W09: "Lê e pergunta.", "Cria apurações e envia documentos.", "Confere e revisa o texto.", "Administra a redação e vê todas as apurações." |
| Apurações | `<fieldset>` com legenda "Apurações" e uma caixa de marcar por apuração da redação, com rolagem a partir de 6 itens. Com o papel Dono, a lista dá lugar ao texto "Dono alcança todas as apurações da redação." O servidor ignora as apurações de um dono |
| Idioma do convite | Português ou English; vem no idioma da conta de quem convida. É o idioma do e-mail e da página do convite |
| Sua senha | só com o papel Dono: o campo da variante [com senha](#dialogo-senha), que aparece abaixo dos outros quando Dono é escolhido (contrato, 5.15) |

Erros:

- antes do envio: e-mail em branco, "Falta o e-mail. Escreva o e-mail da pessoa."; e-mail sem a forma de endereço, "E-mail inválido. Confira o endereço, por exemplo ana@redacao.org.";
- `convite_duplicado` (400): o texto do servidor abaixo do campo E-mail ("Essa pessoa já faz parte da redação." ou "Já há um convite pendente para esse e-mail: reenvie ou cancele o que existe.");
- `limite_de_convites` (429) e as demais recusas: o texto do servidor no erro do diálogo;
- senha: como na [variante com senha](#dialogo-senha).

O resultado depende de como o convite saiu (campo `envio`):

| `envio` | O que a tela faz |
|---|---|
| `enviado` | o diálogo fecha; linha de estado "✓ Convite enviado para ana@redacao.org." |
| `tela` (o servidor devolve `link`) | o diálogo troca o formulário pelo link, sem fechar: título "Envie o link a ana@redacao.org"; texto "Mande por um canal seguro, pessoalmente ou por mensageiro cifrado. O link vale até 29 de nov., uma única vez, e não será mostrado de novo."; campo só de leitura com o link (`translate="no"`), "Copiar link" (secundário) e "Já enviei" (principal), que fecha. Esc e "Já enviei" fecham do mesmo jeito; o link não fica na página depois disso. É o mesmo cuidado da "Contas de acesso" de hoje |
| `falha` | o diálogo fecha; linha de estado em 14/600 `--theme-warning`, com "!" e `role="status"`: "! O e-mail para ana@redacao.org não saiu. O convite está entre os pendentes; reenvie quando quiser." Não é erro de quem convidou: cores de aviso |

A tela não distingue o convite para um e-mail que tem conta em outra redação: a resposta do servidor é a mesma de qualquer outro, e a tela também (contrato, 8.1).

**E-mail em título ou texto corrido** (diálogos de convite, cancelar e link): o endereço quebra só depois de "@" ou antes de um ponto (`<wbr>` nesses lugares), nunca no meio de um nome ("redacaoserena.or / g?"). Ressalva sobre `7971606`, sem barrar; feita em `259fd1b` (título, tabela, cartões e linha de estado).

**Convites pendentes** ficam na mesma tabela das pessoas, depois delas (W09), em `equipe-listar`, campo `convites`:

| Coluna | Conteúdo |
|---|---|
| Pessoa | o e-mail em 16, `translate="no"`; abaixo, em 14 `--theme-muted`, sinal e texto do envio: "◐ Convite enviado há 2 dias · vence em 5 dias" (`enviado`); "◐ Link criado há 2 dias · vence em 5 dias" (`tela`); com `falha`, "! O e-mail não saiu · reenvie", em 14/600 `--theme-warning`. Prazos por `enviado_em` e `expira_em`; no último dia, "vence hoje" |
| Papel | o papel em texto, sem caixa: para mudar, cancela-se e convida-se de novo |
| Apurações | como nas pessoas; "Todas" para dono |
| Uso no mês | "—" |
| Ação | "Reenviar" e "Cancelar convite", os dois com cara de [link](#link) e altura mínima 44, um ao lado do outro, com intervalo de 16, numa coluna de ações com largura mínima de 204 px (aceito em 22/11/2026 sobre `7971606`) |

No celular, cada convite vira um cartão depois dos cartões das pessoas, com as duas ações em botões secundários de largura cheia.

- **Reenviar** age direto, sem diálogo, e gera um link novo: o anterior deixa de valer e o prazo recomeça (`equipe-convite-reenviar` com `convite`). Resultado: com `enviado`, "✓ Convite reenviado para ana@redacao.org. O link anterior deixou de valer."; com `tela`, o mesmo diálogo do link, com o título "Novo link para ana@redacao.org"; com `falha`, o aviso acima. Antes de uma hora, o servidor recusa (429 `limite_de_convites`): o texto dele vai à linha de estado, em 14 `--theme-danger`, com `role="alert"`.
- **Cancelar convite** abre a variante destrutiva: "Cancelar o convite de ana@redacao.org?", com o texto "O link deixa de valer. Dá para convidar o mesmo e-mail de novo, mas cada endereço recebe no máximo três convites da redação por hora, contando os cancelados." (teto do servidor desde `e5743a5`; passar dele dá 429 `limite_de_convites`, com o texto do servidor no erro do diálogo de convidar: "Esse e-mail já recebeu convites demais desta redação na última hora. Espere para convidar de novo.") A ação é "Cancelar convite" e o botão de sair é "Manter convite", não "Cancelar", para não haver dois "Cancelar". Resultado: "✓ Convite de ana@redacao.org cancelado." (`equipe-convite-cancelar` com `convite`).
- Convite que já não existe (cancelado em outra aba, aceito, vencido) responde "Convite não encontrado.": a lista recarrega, sem erro.

Na atividade, frases novas:

| Tipo | Frase |
|---|---|
| `convite_enviado` | Fulano convidou um e-mail |
| `convite_reenviado` | Fulano reenviou um convite |
| `convite_cancelado` | Fulano cancelou um convite |
| `convite_aceito` | Beltrano aceitou o convite e entrou na redação |
| `convite_expirado` | Um convite venceu |

A atividade não leva o e-mail, que é dado de quem ainda não é da redação.

<a id="aceitar-convite"></a>

### Aceitar convite (W10) e redefinir a senha

*(Derivado, 22/11/2026.)* **Foco ao trocar de estado:** quando o cartão troca de estado ("Este convite não vale mais", "E-mail confirmado", "Senha nova salva"), o foco vai para o título, para o leitor de tela anunciar. O título recebe `tabindex="-1"` e **não mostra o anel** (`outline: none` só em `[tabindex="-1"]:focus`). O anel é sinal de controle, e um título não é controle. Em todo elemento interativo o anel continua como está.

São seções novas da página do Entrar (`entrar.html`), irmãs de "Definir sua senha" e "Criar administrador". Usam o mesmo [formulário de entrada](#entrar), com a mesma página, cartão, campos de 48 px, botão grande e rodapé. No desktop, que o canvas não desenha, o cartão fica centrado, com até 440 px de largura. O token vem do caminho da página e é lido pelo script; tem 43 caracteres (letras, números, `_` e `-`). A página não carrega nada de fora (W10 e contrato, 5.2). Combinado com Contas em 22/11/2026: `GET /aceitar/<token>` e `GET /redefinir/<token>` servem o mesmo `entrar.html` de `/entrar` e `/ativar/<token>`, com `Referrer-Policy: no-referrer` e `Cache-Control: no-store`; o script abre a seção pelo caminho.

**Aceitar convite** (`/aceitar/<token>`). Ao abrir, a página chama `convite-consultar` com o token. Enquanto espera, o cartão mostra o esqueleto curto. O idioma da página é o do convite (`idioma`); "English" ou "Português" no rodapé troca.

| Parte | Conteúdo |
|---|---|
| Rubrica | "CONVITE", 14/600 maiúsculas, `--theme-muted` |
| Título | serifa 22/600: "Entre na Redação Serena" (`redacao`) |
| Texto | 16: "Rui Castro convidou **ana@redacao.org** como Repórter." (`convidado_por`, `email` em 600 e `translate="no"`, `papel`). `convidado_por` e `redacao` são texto digitado por alguém: entram só como texto (`textContent`), nunca como HTML nem como link, mesmo que pareçam um endereço. Abaixo, em 14 `--theme-muted`: "Convite válido até 29 de nov." (`expira_em`) |
| E-mail | não é campo: o e-mail do convite está no texto e não muda aqui (W10, regra 3). Um `input` oculto com `autocomplete="username"` e o e-mail permite ao gerenciador de senhas guardar o par certo |
| Seu nome | campo, `autocomplete="name"`, até 120 caracteres; recebe o foco inicial |
| Crie uma senha | [campo de senha](#campo) com "Mostrar", `autocomplete="new-password"`; apoio "De 12 a 256 caracteres. Pode colar ou usar o gerenciador de senhas." (W10). Um campo só, como no W10 |
| Termos | só no `piloto` com versão vigente (`termos_versao` não nulo): a caixa de marcar "Li e aceito os termos de uso e a política de privacidade do teste.", obrigatória, em que "termos de uso e a política de privacidade" é um [link](#link) para `termos_endereco`, aberto em outra aba (`target="_blank"`, `rel="noopener noreferrer"`, nome acessível terminado em "(abre em nova aba)"). O aceite envia a versão lida. Resposta 400 `termos_desatualizados`: a página relê o convite e mostra, no lugar do erro, "Os termos mudaram enquanto você lia. Confira a versão nova e marque de novo.", com a caixa desmarcada. Sem versão vigente, a caixa não aparece (E4b, `c60b673`) |
| Ação | principal grande "Criar conta e entrar" ("Criando a conta…") |
| Aviso de teste | abaixo da ação, o bloco de aviso do Entrar, com o texto do passo 3 do W10: "Antes de começar" (16/600) e "O Vlado está em teste. Use só documentos públicos: trechos são enviados ao provedor de IA." (14) |

Erros de campo: os da entrada ([estados](#estados)), "Falta o nome. Escreva o seu nome." e "A senha deve ter de 12 a 256 caracteres.". Termos sem marcar: "Falta aceitar os termos. Marque a caixa para continuar."

Respostas:

| Resposta | O que a página faz |
|---|---|
| 200 do aceite (`conta`, `csrf`, `destino`) | a sessão já está aberta; vai para `destino` |
| 400 `convite_invalido`, na consulta ou no aceite | o cartão dá lugar ao estado "Convite sem efeito": título "Este convite não vale mais"; texto do servidor ("Convite inválido, cancelado ou vencido. Peça um novo a quem convidou."); [link](#link) "Ir para a entrada". É uma resposta só para todo link que não cria conta: a página não tenta adivinhar a causa (contrato, 8.1) |
| 400 `senha_invalida` | o texto do servidor abaixo do campo da senha |
| 400 `requisicao_invalida` e outros 400 | o texto do servidor; quando fala do nome, abaixo do campo do nome; sem saber o campo, na caixa de aviso do formulário |
| 429 `bloqueado` | caixa de aviso do formulário com o texto do servidor ("Muitas tentativas. Aguarde alguns minutos e tente de novo.") |
| 503 | caixa de aviso: "Registro de acesso indisponível. Avise a administração.", como no Entrar |

**Esqueci a senha.** No Entrar, o link "Esqueci a senha" fica na linha do rótulo da senha, à direita, em 14/600 (o [campo](#campo) do canvas). Ele troca o formulário pela seção "Criar uma senha nova":

- campo E-mail (48 px, `autocomplete="email"`);
- ação principal grande "Enviar link" ("Enviando…");
- [link](#link) "Voltar para a entrada".

A resposta é sempre a mesma (`senha-esqueci`, contrato, 5.3): o cartão mostra "Se houver uma conta com esse e-mail, enviamos um link para criar uma senha nova. Ele vale por 1 hora e uma única vez. Confira também a caixa de spam." e "Voltar para a entrada". Abaixo, em 14 `--theme-muted`: "Entra com um login antigo, sem e-mail? Fale com quem administra o serviço."

Com o transporte `tela` não há a quem mandar o link, e "Esqueci a senha" fica desligado (contrato, 8.1). Nesse caso, no lugar do link, fica o texto de hoje: "Esqueceu a senha? Fale com quem administra o serviço." Combinado com Contas em 22/11/2026: a página lê `GET /api/entrada`, pública e sem sessão, que devolve `{esqueci_senha: true|false}` (`true` só com transporte diferente de `tela`). Com `false`, ou se a leitura falhar, a página mostra o texto e não chama `senha-esqueci`; se chamar mesmo assim, recebe 400 `transporte_indisponivel` e mostra o mesmo texto.

A resposta de `senha-esqueci` é sempre 200 `{estado: "enviado", mensagem}`, igual para e-mail com conta, sem conta e malformado. O servidor manda no máximo uma mensagem a cada 5 minutos por endereço, sem mudar a resposta: pedir de novo mostra o mesmo cartão. A tela usa o próprio texto, acima, que diz também o prazo de 1 hora; não precisa validar a forma do e-mail além de ele não estar em branco ("Falta o e-mail. Escreva o e-mail da sua conta.").

**Redefinir a senha** (`/redefinir/<token>`). Cartão com o título "Crie uma senha nova" e os campos:

- Senha nova: [campo de senha](#campo) com "Mostrar", `autocomplete="new-password"`, com o apoio de tamanho, recebendo o foco inicial;
- Código do autenticador: só quando a conta tiver segundo fator ([exceções](#contas-excecoes)).

A ação é a principal grande "Salvar a senha nova" ("Salvando…"). Respostas:

- sucesso (200 `{estado: "senha_redefinida"}`): o título do cartão passa a "Senha nova salva", o texto é "As sessões abertas desta conta foram encerradas. Entre com a senha nova." e a ação principal "Entrar" leva ao Entrar;
- link desconhecido, usado ou vencido (400 `link_invalido`, uma resposta só): o estado "Este link não vale mais", com o texto do servidor ("Link inválido, usado ou vencido. Peça outro em Esqueci a senha.") e o link "Pedir outro link", que abre "Esqueci a senha";
- 400 `senha_invalida`: o texto abaixo do campo; 400 `requisicao_invalida`: caixa de aviso;
- senha fora do tamanho, 429 e 503: como no aceite.

Combinado com Contas em 22/11/2026: `senha-redefinir` recebe `{token, senha}`, **não abre sessão** e encerra todas as sessões da conta; a pessoa entra depois pelo Entrar, o que mantém o aviso de aparelho novo e, quando existir, o segundo passo. O campo `codigo` é aceito e ignorado até o segundo fator. Depois de redefinir ou trocar a senha, a pessoa recebe um aviso no e-mail da conta; a tela não precisa dizer isso.

<a id="contas-excecoes"></a>

### Exceções declaradas, por falta de servidor ou por decisão do dono

A conferência destas telas não barra por elas. Cada uma volta ao wireframe quando o servidor existir, e a tela é conferida de novo nesse ponto.

| O que o wireframe mostra | O que a tela mostra até lá | Volta quando |
|---|---|---|
| Obrigação do segundo fator para dono e editor (pendência `segundo_fator`) | o cadastro é opcional para todos; a [página da pendência](#pendencia-fator) não aparece | o commit da pendência de Contas, integrado com a tela (contrato, 12) |
| W08 e W10: chave de acesso | fora | não volta: decisão 4 do contrato (P27) |
| W08: cidade aproximada da sessão | aparelho, último uso e endereço | não volta: decisão 5 do contrato (P27) |
| W08: "14 perguntas" no uso do mês | só o valor em reais | `GET /api/cota` trazer a contagem |
| W09: "Convidar pessoa", convites pendentes e "Reenviar" | nada no lugar do botão. Abaixo da tabela, em 14 `--theme-muted`: numa instalação com uma redação só, "Para incluir alguém, crie uma conta em Configurações, Contas de acesso.", com "Contas de acesso" como [link](#link) para a aba; com mais de uma redação, onde `contas-criar` já é recusada (`5e342fe`), "Para incluir alguém na redação, fale com quem administra o serviço." A Mesa não distingue os dois casos (as capacidades são fixas por papel e a recusa só vem na chamada), então mostra sempre o primeiro texto, com o link (aceito em 22/11/2026 sobre `84cdcef`) | volta com a E3 de Contas (`281a468`), já especificada em [convites](#convites). As `contas-*` e "Contas de acesso" saem na mesma integração (P30) |
| W10: "Abrir a apuração de exemplo" e o tour (regra 7) | o aceite vai a `destino`, o destino inicial do servidor | houver apuração de exemplo e tour |
| "Esqueci a senha" com o transporte `tela` | o texto "Esqueceu a senha? Fale com quem administra o serviço." | não volta: decisão 12 do contrato; a produção usa `smtp` |
| W09: cartão "Chave de IA da redação" | a chave continua em Configurações, como hoje, com a senha | houver chave por redação (contrato, 8.5, parte da Plataforma) |
| W09: "aviso em 80%" e "redação convidada para o teste" | só o teto e a contagem de pessoas | o servidor informar o aviso e a situação do teste |
| W09: "Ana entrou de novo aparelho" na atividade | a atividade sem esse evento | houver aparelho conhecido (contrato, 8.2 e 8.3) |
| "Recuperar acesso" na Equipe | fica em Configurações, "Contas de acesso", como hoje (P30) | volta com a E3 de Contas (`1720332`), já especificada em [recuperar](#recuperar), na mesma integração em que as `contas-*` saem |
| Autor de conta removida como "Conta excluída" | o texto de remover não promete a troca | vier o ciclo de vida (contrato, 8.4 e 12) |

### Ganchos com o resto da Mesa

| Gancho | Quem |
|---|---|
| O perfil no rodapé da barra e no pé da gaveta abre Minha conta e recebe `aria-current` | Lume (barra) e Vitral (página) |
| O botão "Configurações" do cabeçalho leva à aba Configurações | Lume |
| As caixas "Idioma" e "Tema" usam o mesmo estado dos botões "English" e "Modo escuro" do cabeçalho. Mudar num lugar muda no outro | Lume e Vitral |
| O estado "Redação suspensa" ([estados](#estados)) vale para a Mesa inteira, a partir de qualquer resposta 403 `redacao_suspensa` | Lume |
| O campo de senha no "Apagar definitivamente" (`gerenciar.js`) e em Configurações (`configuracao_ia.js`) entra na mesma integração em que o servidor passa a pedi-la | Vitral, com Contas |
| As rotas `GET /aceitar/<token>` e `GET /redefinir/<token>` servem a página do Entrar, que abre a seção certa pelo caminho (combinado em 22/11/2026; entram no commit da redefinição de Contas) | Contas (rota) e Vitral (seções) |
| `GET /api/entrada` diz ao Entrar se "Esqueci a senha" está ligado (combinado em 22/11/2026; mesmo commit) | Contas (rota) e Vitral (Entrar) |

---

<a id="regras-dos-wireframes"></a>

## Regras dos wireframes

Transcrição literal das regras de cada wireframe (regra 2 do contrato: cada uma vira critério de aceite e, quando testável, um teste). W04 e W06 trazem as regras num parágrafo sem numeração; a transcrição mantém o parágrafo como está.

**W01 Nova apuração (vários sites)**
1. A lista de sites aceita vários endereços, com limite por apuração (proposta: 10).
2. Cada endereço é um domínio exato; subdomínio conta como outro site e precisa ser adicionado.
3. Site inválido, interno ou repetido é recusado na hora, com a razão junto ao campo.
4. Depois de criada a apuração, sites podem ser adicionados ou removidos em "Fontes"; cada mudança cria nova versão do manifesto e fica no histórico.
5. Remover um site não apaga as capturas já feitas dele.
6. A captura continua sendo só a pedido do jornalista, página por página.

Nota do wireframe: "Muda o que existe hoje: o manifesto guarda um único domínio. Exige alterar o AGENTS.md e passar por revisão de segurança."

**W02 Documentos e envio**
1. Uma só tela para acervo, envio e busca. Somem as abas "Acervo", "Pesquisar" e "Cadastro e recibo".
2. Cada arquivo tem a própria barra e o próprio resultado; a falha de um não derruba os outros.
3. O envio segue em segundo plano: a pessoa pode sair da tela.
4. A busca no texto funciona antes da primeira pergunta à IA.
5. Três estados de leitura, sempre com sinal e texto: do arquivo, por OCR, sem leitura.
6. Erro explica o que houve e o que fazer; nada de "recibo incompleto".
7. Hash, ID e versão ficam em "Detalhes técnicos" de cada documento, fora da lista.
8. O recibo do lote continua existindo e é conferido antes da primeira pergunta.

**W03 Perguntar**
1. Lista de conversas à esquerda; nada de escolher rodada ou versão do corpus.
2. O campo de pergunta fica no fim da coluna e nunca cobre o conteúdo.
3. Estimativa de custo antes de enviar, gasto durante e valor final depois, em reais.
4. O progresso nomeia as seis etapas em linguagem comum e pode ser interrompido.
5. Cada número da resposta leva a fonte ao lado, que abre o original na página.
6. Lacuna é um bloco próprio, com sinal e texto.
7. Conexão, provedor e chave saem daqui e vão para a configuração da organização.
8. Se novos documentos chegaram, a conversa avisa e oferece refazer a pergunta com eles.

**W04 Caderno e conferência do texto**

"Regras: ligar evidência e criar nova versão têm formulário (fase 10). Só pessoa logada marca "revisada". Quatro sinais, sempre com traço e texto: com fonte, exagero, sem fonte, revisada. O editor vê e comenta sem alterar o texto."

**W05 Hipóteses**
1. Criar, editar e arquivar hipótese pela Mesa. Hoje só se lê.
2. Três colunas fixas: sustenta, contraria, falta. Cada uma com sinal, traço e texto próprios.
3. "Ligar evidência" abre a lista de achados já conferidos; achado não conferido aparece marcado como tal.
4. Toda evidência abre o original na página citada.
5. Item de "falta" pode virar pergunta à IA, entrevista ou pedido de LAI.
6. A contagem no cabeçalho não é placar: o quadro organiza, não decide se a hipótese é verdadeira.
7. Estado vazio traz explicação curta e o botão "Nova hipótese".

**W06 Tabelas conferíveis**

"Regras: toda célula tem fonte ou está marcada "a conferir". Correção exige justificativa e guarda o valor anterior. Três estados com sinal e texto: da fonte, corrigida ✎, a conferir ○. Cálculos só soma, diferença, contagem e média, com a conta visível. Navegação por teclado entre células, foco sempre visível. Em tela estreita a tabela rola dentro da própria caixa."

**W07 Comparador**
1. Dois lados, cada um escolhido entre documentos, versões, capturas de site ou declarações já cadastradas.
2. Trecho retirado leva sinal "−" e risco; trecho novo leva "+" e fundo. Nunca só cor.
3. Diferenças de valor e de data são contadas e navegáveis por teclado.
4. A conta de cada diferença aparece por extenso.
5. O resultado vira achado "a conferir", nunca conferido de saída.
6. A comparação pesada roda na fila, fora da trava do servidor, com o padrão único de "ocupado".
7. No celular, os lados se empilham e as diferenças viram lista.
8. O comparador mostra o que mudou. Não diz se a mudança é irregular.

**W08 Minha conta**
1. Página própria, aberta pelo nome no rodapé da barra lateral. Sai de "Apurações e lixeira".
2. Trocar senha pede a atual e encerra as outras sessões.
3. Segundo fator obrigatório para dono e editor; códigos de reserva mostrados uma única vez.
4. Campos de senha aceitam colar e gerenciador de senhas.
5. Lista de sessões com aparelho, cidade aproximada e último uso; encerrar é imediato.
6. Novo acesso gera e-mail de aviso.
7. Uso em reais, nunca em tokens.
8. Excluir conta e exportar dados existem e explicam o que acontece com o trabalho feito.

**W09 Equipe e convites**
1. Quatro papéis: dono (administra), editor (confere e comenta), repórter (cria apurações e envia documentos), leitor (só lê e pergunta).
2. Cada pessoa vê só as apurações que criou ou em que foi incluída. O dono vê todas da própria redação e nenhuma de outra.
3. Convite por e-mail, com prazo; pode ser reenviado ou cancelado.
4. No teste, só o Vlado cria redações. O dono convida pessoas dentro da sua.
5. Gasto em reais, por pessoa e por redação, com teto e aviso.
6. A chave de IA é da redação, não da pessoa, e só o dono a troca.
7. Trocar papel de outro dono ou remover o último dono é bloqueado.
8. A atividade mostra acessos e ações de administração, nunca conteúdo de documentos.

**W10 Aceitar convite**
1. Entrada só por convite. Não existe cadastro aberto nem lista de espera no teste.
2. O link vale por prazo definido e uma única vez; vencido, a tela diz a quem pedir outro.
3. O e-mail vem do convite e não pode ser trocado aqui.
4. Aceite de termos registrado com data e versão.
5. Segundo passo obrigatório para dono e editor, recomendado para os demais. Chave de acesso é alternativa ao código.
6. Códigos de reserva aparecem uma vez.
7. O primeiro acesso termina numa apuração de exemplo com dados fictícios e um tour que pode ser pulado.
8. No celular, os três passos viram telas em sequência.

**W11 Estados: vazio, ocupado, erro** ("Regras para toda a Mesa")
1. Todo estado vazio diz o que é a coisa e traz uma ação.
2. Dois padrões de "ocupado" e só dois: esqueleto para espera curta, barra com etapa para espera longa. Ambos com aria-busy.
3. Espera longa pode ser cancelada e não prende a pessoa na tela.
4. Erro em três partes: o que houve, o que foi preservado, o que fazer. Sem código interno no texto principal; o código fica em "Detalhes".
5. Erro de campo aparece junto ao campo, com aria-invalid, e o foco vai para ele.
6. Erro usa as cores de erro; aviso usa as de aviso. Nunca trocados.
7. Limite de gasto explica o que continua funcionando.
8. Confirmação de ação destrutiva usa o diálogo da Mesa, nunca o do navegador, e oferece desfazer quando possível.
9. Mensagens de mudança de estado são anunciadas a leitor de tela.

---

## Consultas às skills

| Skill | Consulta ou uso | O que entrou aqui |
|---|---|---|
| `design-system` | `references/component-specs.md` e `references/states-and-variants.md` | A forma de cada seção (variantes, medidas, estados) e a ordem de prioridade dos estados (desabilitado acima de ocupado, acima de foco, acima de passar o mouse). |
| `ui-ux-pro-max` | `"focus not obscured" --domain ux` | Foco nunca coberto por conteúdo fixo: o compositor do celular não cobre o elemento focado (UX-19). |
| `ui-ux-pro-max` | `"skeleton loading short wait" --domain ux` | Espera com esqueleto ou progresso estável e `aria-busy`, sem piscar em operação curta (W11, regra 2). |
| `ui-ux-pro-max` | `"error message near field" --domain ux` | Erro abaixo do campo, ligado por `aria-describedby`. |
| `ui-ux-pro-max` | `"empty state action" --domain ux` | Estados vazios derivados sempre com ação. |
| `ui-ux-pro-max` | `"destructive confirmation dialog undo" --domain ux` | Diálogo próprio antes de ação destrutiva; desenho pendente. |
| `dataviz` | `scripts/validate_palette.js` sobre as cores do mapa, nos dois temas | Resultado em `mudancas-de-token.md`, item 10. |

## O que ainda falta desenhar

Pela regra 1 do contrato, nada disto é construído antes de o Design desenhar e o dono aprovar: os formulários de resposta e de recurso dos pedidos de LAI, com o cálculo do prazo (PROD-07); fontes e capturas de site dentro da apuração; lixeira; configuração da organização; página pública; versões de celular das demais telas de desktop (e, no sentido inverso, o Entrar em desktop); faixa de 720 a 1023 px; tema escuro das telas do canvas fora as três de desktop; sem aviso com "Desfazer" por ora (P12.7). Desenhados na fase 3 e aprovados pelo dono em 21/11/2026: diálogo de confirmação, escuro de conferir achado, visão geral e design system, tablet de 1024 px e celular de 390 px de conferir achado e visão geral ([Telas derivadas](#telas-derivadas)). O conjunto de ícones (parte E) está na seção [Conjunto de ícones do Vlado](#conjunto-de-icones), com cinco ícones derivados, aprovados pelo dono em 21/11/2026. Aprovados também em 21/11/2026, em [Áreas sem tela final](#telas-aprovadas): caderno, hipóteses, tabelas, comparador, mapa e linha do tempo no celular, Pedidos e prazos e Documentos. Têm só a captura da Mesa de hoje, sem desenho: Perguntar no desktop (há o W03), Diligências, Apurações e lixeira, e Configurações. Minha conta, Equipe e Configurações (W08 e W09) têm especificação sem prancha em [Contas](#contas), de 22/11/2026. Sugestão da IA nos quadros, formulários de criar e editar dos quatro quadros, o seletor comum de evidência e a comparação entre processos têm especificação sem prancha em [Quadros na Onda 4](#quadros-onda4), de 27/11/2026. Ainda falta, ali, o que depende do servidor: o formato do candidato no `MESA.md` e os campos estruturados da comparação entre processos (Viga). Da fase 10 (P47), falta desenhar a nova versão do texto, o rascunho e a confirmação da reabertura; o seletor já está desenhado.

## Decisões do dono (21/11/2026)

Respostas do dono às perguntas desta especificação e às pranchas de `aprovacao/`, repassadas pelo Maestro (P11, P12, P14, P14b, P15 e P16 da nota de decisões; P20a, P20b, P30 e P34, de 22/11/2026; P45 e P47, de 25/11/2026). Não há pergunta aberta nesta seção.

| Nº | Pergunta | Decisão |
|---|---|---|
| P11.1 | Largura do celular | A imagem de 390 px vale como referência de 375 px. |
| P11.2 | Tamanhos fora dos seis degraus | Tokens de exceção só para 24, 32 e 40 px (`--text-destaque`, `--text-numero`, `--text-marca`). |
| P11.3 | Raios além dos três | 12 px em todos os cartões; 4 px só na folha do documento e no topo das barras. |
| P11.4 | Cor do órgão público | Ameixa validada: `#b0508a` no claro, `#d46a9c` no escuro. |
| P11.5 | Texto que não cabe | Altura mínima no lugar de altura fixa. |
| P11.6 | Ícones na barra lateral | Sem ícones, como no canvas. |
| P11.7 | Quadros sem barra lateral | De propósito, com caminho de volta visível ("‹ Apuração" no cabeçalho dos quadros). |
| P11.8 | Medidas fora da grade de 4 px | Arredondar para a grade de 4 px (para cima). |
| P12.1 | Gaveta | Abaixo de 1280 px. |
| P12.2 | Item ativo no escuro | Verde cheio. |
| P12.3 | Original no celular | Camada de tela cheia com as ações no pé. |
| P12.4 | Título no celular | 28 px, se o título longo couber em duas linhas. |
| P12.5 | Clique no véu | Não fecha o diálogo; "Apagar definitivamente", se puder demorar, vira espera longa cancelável com barra de etapa (W11, regra 3). |
| P12.6 | Rótulos dos oito `confirm()` | Aprovados. |
| P12.7 | Desfazer | Não agora. |
| P14.1 | Caderno em três colunas (W04) | Aprovado como desenhado, com a barra lateral do canvas. |
| P14.5 | Caderno no celular | Seletor de nota no topo e afirmação selecionada num painel no pé. |
| P14b.6 | Trechos com fonte e contribuições | Segunda lista da coluna da esquerda do caderno ("Notas \| Trechos"). |
| P14b.7 | Modo "Escrever" | Como desenhado. |
| P14b.8 | Sinal "revisada" | Sublinhado duplo verde e "revisada por você", como desenhado. |
| P15.1 | Abas dos quadros | Cinco: Hipóteses, Linha do tempo, Mapa de relações, Tabelas, Comparador. "Conferência do texto" vai para o caderno; "Entrevistas e pedidos" vira a área Pedidos e prazos. |
| P15.2 a P15.4 | Hipóteses, Tabelas, Comparador | Como desenhados. |
| P15.5 | Pedidos e prazos | Como desenhado. |
| P15.6 | Mapa e linha do tempo no celular | Mapa como lista de ligações; linha do tempo em coluna única. |
| P15.7 | Contador "1 vence" no item ativo | Pílula clara, com a condição de que rótulo e pílula não quebrem linha. Para cumprir a condição, a barra lateral passa de 232 para 256 px em todas as telas (mudança no canvas aprovado, autorizada pelo dono; `mudancas-de-token.md`, item 7). |
| P16.1 | Documentos | Uma tela só para acervo, envio e busca. |
| P16.2 | Envio | Por arquivo, com o recibo do lote numa linha do cartão de envio. |
| P16.3 | Lista de documentos | Tabela no desktop, cartões no celular. |
| P16.4 | Contador do item ativo | "Documentos 12" vira pílula clara na página atual. |
| P16.5 | Cadastrar arquivos | Deixa de ser área; vira a área de envio de Documentos. |
| P20a | Selo do veredito da IA (22/11/2026) | Pílula sem fundo, borda tracejada e texto com "IA ·"; os selos humanos mantêm fundo, borda contínua e sinal ([selo](#selo)). |
| P20b | Altura das abas em pílula no celular (22/11/2026) | 44 px, pelo alvo de toque; o canvas desenha 40. Mudança no canvas autorizada pelo dono ([abas](#abas)). |
| P34 | Seletor de apuração do topo (22/11/2026) | Segue o canvas, sem caixa. O que precisa de 3:1 (WCAG 1.4.11) é o que o identifica: o texto e a seta ([foco-aa](#foco-aa)). |
| P30 | Saída das `contas-*` (22/11/2026) | Ficam até o convite por e-mail da E3 e saem junto com ele, na mesma integração. A Equipe entra sem "Convidar" e "Contas de acesso" continua em Configurações até lá ([exceções](#contas-excecoes)). |
| P45 | Como a IA entra nos quadros (25/11/2026) | Opção (a): a IA sugere candidatos (pessoa, organização, ligação, acontecimento datado e hipótese), cada um preso a uma evidência publicada; na tela, tracejados como "Sugestão da IA", com Confirmar, Corrigir e Descartar, e só o confirmado vira item ([Sugestão da IA](#sugestao-ia)). |
| P47 | Vincular evidência (25/11/2026) | Seletor comum, com busca no caderno e nos achados da IA ([seletor](#seletor-evidencia)); evidência da IA chega com o tipo e o suporte da última revisão, e qualquer mudança aparece como "alterado por pessoa"; fonte do caderno começa em "não revisado" ([cartão do vínculo](#cartao-vinculo)). |

As 27 pranchas da fase 3 e as de `aprovacao/` foram aprovadas e regeneradas com estas decisões, inclusive a barra de 256 px. As telas finais do canvas em `referencia/telas/` continuam como estão: são o registro do contrato; as decisões acima valem sobre elas onde houver diferença, e `referencia/com-decisoes/` mostra as sete telas com elas aplicadas.
