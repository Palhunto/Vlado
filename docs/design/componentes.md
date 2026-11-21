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
| Número de contagem; marca na barra lateral | serifa | 32 / 600 / 1,1 (marca: espaçamento −0,5 px) | `--text-numero` *(novo)* |
| Marca no Entrar | serifa | 40 / 600 / 1 | `--text-marca` *(novo)* |

Serifa = `--fonte-titulo` *(novo)*, Source Serif 4. Sem serifa = `--fonte-interface` *(novo)*, Source Sans 3. Nenhum texto de interface abaixo de 14 px; nenhum campo abaixo de 16 px. Texto de leitura com até 70 caracteres por linha (UX-10).

### Espaço, raio e alvo

- Espaços do canvas: 4, 8, 12, 16, 24, 32 e 48 px na escala; o canvas também usa 6, 10, 14, 18, 20, 22 e 28 px em preenchimentos e intervalos, reproduzidos como estão (pergunta 8).
- Raios: controle 8 px (`--raio-controle`), cartão 12 px (`--raio-cartao`), pílula (`--raio-pilula`). Exceções do canvas: 10 px nos cartões de "Conferir achado" e no cartão da cota; 4 px na folha do documento e no topo das barras (pergunta 3).
- Alvo de toque: 44 px de altura em desktop; 48 px nos controles principais do celular e do Entrar.

### Foco

Todo elemento interativo: `outline: 3px solid var(--theme-focus); outline-offset: 2px` (`--foco-largura`, `--foco-afastamento`, *novos*). Claro: ocre `#8a5a12`; escuro: ocre `#e6bc7a`. Nunca removido, nunca trocado por mudança só de cor. Dentro de contêiner com corte, anel interno (ver `mudancas-de-token.md`, item 2), nunca em botão principal. Origem: canvas (`:focus-visible` de todas as telas e o botão "Em foco" do design system).

### Quebras

720, 1024 e 1280 px (`mudancas-de-token.md`, item 6). O canvas desenha 390 e 1440 px; o que muda entre elas, além do que está escrito em cada componente, ainda será desenhado.

### Movimento

O canvas é estático. Derivado de W11 e UX-08: transição de cor e fundo em 150 ms; nenhuma animação com `prefers-reduced-motion: reduce`, onde o esqueleto e a barra ficam parados e o texto de etapa continua mudando.

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
| Desabilitado | fundo `--theme-sidebar`, borda 1 px `--theme-line`, texto `--theme-muted` 16/400 | canvas ("Indisponível") |
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
| Contêiner | largura 232 (`--mesa-sidebar`); fundo `--theme-sidebar`; borda direita 1 px `--theme-line`; preenchimento 24 16; coluna com intervalo de 24 |
| Marca | "Vlado" e um ponto em `--theme-accent`; serifa 32/600, espaçamento −0,5 px; preenchimento 0 8 |
| Lista de áreas | coluna, intervalo de 4. Ordem: Visão geral, Documentos, Perguntar, Conferir, Quadros, Caderno, Pedidos e prazos |
| Item | `<a>`, altura 44, preenchimento 0 12, raio 8, texto 16 `--theme-text`, sem sublinhado |
| Contador | à direita (`margin-left:auto`), 14 px; quatro formas em `mudancas-de-token.md`, item 8 |
| Cartão da cota | no rodapé (`margin-top:auto`); fundo `--theme-surface`, borda 1 px `--theme-line`, raio 10, preenchimento 12 14, intervalo de 6; linha "Cota do mês" (14 `--theme-muted`) e valor ("R$ 18,40 de R$ 50", 14/600); [medidor](#medidor) |
| Perfil | `<a>` altura 44, preenchimento 0 8, intervalo de 10; avatar de 32 px, círculo `--theme-accent`, iniciais 14/600 `--theme-on-primary`, `aria-hidden`; nome 16/600; papel e redação 14 `--theme-muted`, entrelinha 1,25. Abre "Minha conta" (W08, regra 1) |

| Estado | Aparência | Origem |
|---|---|---|
| Padrão | tabela acima | canvas |
| Selecionado (página atual) | `aria-current="page"`; fundo `--theme-accent`, texto `--theme-on-primary` 600 | canvas |
| Ao passar o mouse | item comum: fundo `--theme-soft` | derivado |
| Foco | anel de foco | canvas (regra geral) |
| Ocupado, erro, desabilitado | não se aplicam | — |
| Vazio | contador some quando é zero | derivado |
| Abaixo de 1024 px | vira gaveta com `inert` quando fechada, aberta pelo botão de menu do cabeçalho | plano (UX-11, UX-17); desenho do tablet pendente |

O canvas não desenha ícones nos itens da barra (pergunta 6).

<a id="medidor"></a>

### Medidor

Barra fina de proporção: cota usada, achados conferidos. Altura 6, raio pílula, trilha `--theme-line`, preenchimento `--theme-accent`. `role="img"` com `aria-label` por extenso ("37% da cota usada", "2 de 6"). Na barra de progresso de envio (design system) e no ocupado longo (W11): altura 8, mesma cor. Estados: padrão (canvas); quando a cota passa do teto, ver [estados](#estados), "Limite atingido".

<a id="cabecalhos"></a>

### Cabeçalhos

| Cabeçalho | Medida e token | Conteúdo | Onde |
|---|---|---|---|
| Da apuração | altura 64; preenchimento 0 32; intervalo de 16; fundo `--theme-surface`; borda inferior 1 px `--theme-line` | "Apuração" (14 `--theme-muted`) sobre o nome (16/600); à direita, estado de salvamento (ícone ✓ de 16 px em `--theme-accent`, traço 2,5, e "Salvo às 14h32" em 14 `--theme-muted`) e botão secundário "Exportar apuração" | Conferir achado |
| Da Visão geral | sem barra; no topo do conteúdo, alinhado pela base, intervalo de 16 | "Apuração · criada em 12 de novembro" (14 `--theme-muted`) sobre o título (serifa 36/600); à direita, "Trocar de apuração" (secundário) e "Nova apuração" (principal) | Visão geral |
| Dos quadros | altura 72; preenchimento 0 32; intervalo de 24; fundo `--theme-surface`; borda inferior 1 px `--theme-line` | "Quadros" (serifa 28/600), [abas](#abas) e ações à direita | Mapa, Linha do tempo |
| Do celular | altura 60; preenchimento 0 12; intervalo de 8; fundo `--theme-sidebar`; borda inferior 1 px `--theme-line` | botão de menu (só ícone), "Apuração" (14 `--theme-muted`) sobre o nome (16/600, cortado com reticências), cota à direita ("R$ 18,40 de 50", 14 `--theme-muted`) | Pergunta no celular |

O estado de salvamento é anunciado a leitor de tela quando muda (W11, regra 9). Erro ao salvar: derivado, troca o ícone por ✕ em `--theme-danger` e o texto por "Não salvou. Tentando de novo".

<a id="abas"></a>

### Abas

Onde: cabeçalho dos quadros. Linha com intervalo de 4. Cada aba é `<a>`: altura 44, preenchimento 0 14, raio 8, texto 16 `--theme-text`. Ativa: `aria-current="page"`, fundo `--theme-soft`, texto `--theme-accent` 600. Foco: anel. Ao passar o mouse (derivado): fundo `--theme-soft`. Ocupado, erro, desabilitado e vazio não se aplicam. Ordem: Hipóteses, Linha do tempo, Mapa de relações, Tabelas. É o único padrão de aba da Mesa (UX-17 aponta três).

<a id="achado"></a>

### Cartão de achado

Onde: Conferir achado. Coluna com intervalo de 12, abaixo do título "Conferir achados" (serifa 28/600) com o progresso ao lado ("2 de 6 conferidos", 14 `--theme-muted`, alinhado pela base, intervalo de 12). A coluna tem preenchimento 28 32 e intervalo de 20 entre título, pergunta e lista.

Estrutura comum: sinal de 28 px à esquerda, texto do achado (16, entrelinha 1,5) e, abaixo, a linha de fonte (14), com intervalo de 6; intervalo de 14 entre sinal e texto; preenchimento 16 18; raio 10 (pergunta 3).

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

Onde: Conferir achado. Fundo `--theme-reading`, raio 10, preenchimento 14 18, intervalo de 4. Rótulo "Sua pergunta" (14 `--theme-muted`) sobre a pergunta (serifa 18). Só leitura: um estado (canvas).

<a id="painel-original"></a>

### Painel do original

Onde: Conferir achado, à direita. `<aside aria-label="Original citado">`.

| Parte | Medida e token |
|---|---|
| Contêiner | largura 520; fundo `--theme-sidebar`; borda esquerda 1 px `--theme-line`; preenchimento 20 24; coluna com intervalo de 14 |
| Topo | nome do documento (16/600) sobre "Página 1 de 1 · original preservado" (14 `--theme-muted`); à direita, selo "Lida por OCR" quando a página veio de OCR |
| Folha | fundo `--pdf-pagina` (branco nos dois temas); borda 1 px `--theme-line`; raio 4 (pergunta 3); sombra 0 1 2 alfa 0,08 (`--sombra-folha`, *nova*); ocupa a altura disponível |
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
| Ocupado | botão "Enviar" vira "Parar" enquanto a resposta chega | wireframe W03 |
| Erro | mensagem de campo abaixo ("Escreva a pergunta antes de enviar.") | derivado de W11 (regra 5) |
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
| Caixa | 200 × 72 (pergunta 5); preenchimento 10 12; intervalo de 10; fundo `--theme-surface`; borda 1 px `--theme-input-line`; raio 12 |
| Ícone do tipo | 36 × 36, `aria-hidden`. Pessoa: círculo `--mapa-pessoa`. Empresa: quadrado com raio 9 em `--mapa-organizacao`. Órgão público: quadrado com raio 3 em `--mapa-orgao` *(novo; cor em aberto, pergunta 4)*. Desenho interno em traço 2, `--theme-on-primary` (branco no claro; escuro: `#172315`, ver `mudancas-de-token.md`, item 10) |
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

Ações do cabeçalho: "Ver como lista" (secundário) e "Adicionar ligação" (principal). O formulário de "Adicionar ligação" é da Onda 4 (PROD-01).

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

| Estado do evento | Aparência | Origem |
|---|---|---|
| Padrão | acima | canvas |
| Selecionado | borda 2 px `--theme-accent`, sombra 0 4 18 alfa 0,08 | canvas (pedido de LAI) |
| Foco | anel no cartão quando ele é focável; no selo de fonte sempre | canvas (regra geral) |
| Ocupado | esqueleto de três cartões | derivado de W11 (regra 2) |
| Erro | não se aplica ao evento; falha ao carregar a lista usa o bloco de erro do serviço | derivado |
| Desabilitado | não se aplica | — |
| Vazio | "Nenhum acontecimento com data ainda" e "Adicionar acontecimento" | derivado de W11 (regra 1) |

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
| Vazio | o que é a coisa e uma ação ("Nenhuma hipótese ainda", "Uma hipótese é uma afirmação que os documentos podem sustentar ou contrariar.", "Criar a primeira") | bloco base; ação principal |
| Ocupado, curto (até 10 s) | esqueleto no lugar do conteúdo, que não aparece se a resposta chega em menos de 0,3 s; `aria-busy` | barras de 14 px de altura, raio 4, fundo `--theme-line`, larguras 70 %, 90 % e 50 % |
| Ocupado, longo (OCR, IA) | etapa por extenso ("Lendo a página 2 de 5"), barra, aviso de que pode sair da tela, "Cancelar"; `aria-busy` | barra como o [medidor](#medidor) de 8 px; "Cancelar" secundário |
| Erro que a pessoa resolve | "✕" e o que houve; o que fazer e o que foi preservado; duas ações | fundo `--theme-danger-bg`, borda 1 px `--theme-danger-line`, título `--theme-danger`; ações principal e secundária |
| Erro do serviço | "✕" e o que houve; o que foi guardado e o que não foi cobrado; "Retomar de onde parou" e "Detalhes" (o código interno fica lá) | como o anterior; "Detalhes" é link |
| Limite atingido | "!" e o limite; o que continua funcionando; "Pedir mais ao dono da redação" | fundo `--theme-warning-bg`, borda 1 px `--theme-warning-line`, título `--theme-warning`; ação secundária |

Erro usa as cores de erro e aviso usa as de aviso, nunca trocadas (W11, regra 6). Mudança de estado é anunciada a leitor de tela (`role="status"` para ocupado e concluído, `role="alert"` para erro; W11, regra 9).

<a id="dialogo"></a>

### Diálogo de confirmação

Sem desenho no canvas. W11, regra 8: "Confirmação de ação destrutiva usa o diálogo da Mesa, nunca o do navegador, e oferece desfazer quando possível." UX-16 pede reusar o diálogo da lixeira. Está na lista do que o Design desenha antes de ser construído (regra 1 do contrato).

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

Os ícones atuais da Mesa (`interface/desktop.js:198-214`) usam traço 1,6 em 18 px, e 15 px em alguns lugares (`.mesa-icon` em `style.css`). O conjunto próprio do Vlado (parte E) é o próximo trabalho do Design e vai harmonizar os traços; até lá, valem os do canvas nas telas do canvas.

---

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

Pela regra 1 do contrato, nada disto é construído antes de o Design desenhar e o dono aprovar: pedidos e prazos de LAI; fontes e capturas de site dentro da apuração; lixeira; configuração da organização; página pública; diálogo de confirmação; versões de celular das telas de desktop (e, no sentido inverso, o Entrar em desktop); faixas de 720 a 1279 px; tema escuro das telas de desktop; conjunto de ícones do Vlado; mapa de relações e linha do tempo com os ícones definitivos (parte E).

## Perguntas para o dono

Nenhuma muda o canvas sem o seu aval. Até a resposta, a especificação segue o que está escrito em cada item.

1. **Largura do celular.** O canvas desenha o celular em 390 px; o plano e o QA usam 375 px. Proposta: a imagem de 390 px vale como referência de 375 px, com as mesmas margens de 16 px e nada fixo em 390. Concorda?
2. **Tamanhos fora dos seis degraus.** O canvas declara seis degraus (14 a 36), mas usa 24 px (frase do "próximo passo"), 32 px (números e marca na barra) e 40 px (marca no Entrar). Proposta: três tokens de exceção com nome (`--text-destaque`, `--text-numero`, `--text-marca`). Ou prefere que esses textos caiam nos degraus (22, 28, 36)?
3. **Raios que o canvas usa além dos três.** "Conferir achado" desenha cartões com 10 px e o cartão da cota tem 10 px também na Visão geral; as outras telas e o design system usam 12 px. A folha do documento e o topo das barras usam 4 px. Proposta: 12 px em todos os cartões; 4 px fica como exceção só para a folha e as barras. Concorda?
4. **Cor do órgão público no mapa.** `#3d4a45` reprova em duas checagens da `dataviz` (lê como cinza). (a) Manter como neutro declarado, com par escuro `#a8b3a9`; ou (b) trocar pela ameixa validada, `#b0508a` no claro e `#d46a9c` no escuro?
5. **Texto que não cabe no desenho.** O nó do mapa tem 72 px fixos e "Construtora Alfa Ltda." transborda; na barra lateral, o papel do perfil e o valor da cota quebram linha dentro de caixas fixas; o Entrar passa da moldura. Proposta: altura mínima no lugar de altura fixa (o caso comum fica igual ao desenho), nome do nó em até duas linhas. Concorda?
6. **Ícones na barra lateral.** O canvas mostra a barra lateral só com texto; a Mesa de hoje tem ícone em cada área (`interface/desktop.js:198-214`). Seguir o canvas (sem ícones) ou manter os ícones?
7. **Quadros sem barra lateral.** As telas do mapa e da linha do tempo não têm a barra lateral de áreas. É tela cheia de propósito, ou a barra foi omitida no desenho?
8. **Medidas fora da grade de 4 px.** O canvas usa preenchimentos de 6, 10, 14, 18 e 22 px. A especificação reproduz as medidas exatas. Prefere assim ou arredondar para a grade de 4 px na implementação (diferença de até 2 px)?
