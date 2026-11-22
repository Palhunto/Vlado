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

### Espaço, raio e alvo

- Espaços do canvas: 4, 8, 12, 16, 24, 32 e 48 px na escala. **Decisão do dono (P11.8):** preenchimento, intervalo e margem fora da grade de 4 px arredondam para cima na implementação: 6 → 8, 10 → 12, 14 → 16, 18 → 20, 22 → 24 (e 2 → 4, 42 → 44). As tabelas desta especificação mostram a medida do canvas; o Frontend aplica o arredondamento, e a conferência aceita essa diferença como regra, não como divergência.
- Raios: controle 8 px (`--raio-controle`), cartão 12 px (`--raio-cartao`), pílula (`--raio-pilula`). **Decisão do dono (P11.3):** 12 px em todos os cartões, inclusive os que o canvas desenha com 10 px (achados, caixa da pergunta, cota); 4 px só na folha do documento e no topo das barras (`--raio-folha`).
- Alvo de toque: 44 px de altura no mínimo, em toda largura; 48 px nos controles principais do celular e do Entrar. Controle principal é a ação que conclui a tarefa da tela: o botão principal, as ações empilhadas do achado aberto, "Conferir agora", "Escolher arquivos". Navegação dentro da tela, como as abas em pílula do celular (P20b), não é controle principal e fica no mínimo de 44 px.

### Foco

Todo elemento interativo: `outline: 3px solid var(--theme-focus); outline-offset: 2px` (`--foco-largura`, `--foco-afastamento`, *novos*). Claro: ocre `#8a5a12`; escuro: ocre `#e6bc7a`. Nunca removido, nunca trocado por mudança só de cor. Dentro de contêiner com corte, anel interno (ver `mudancas-de-token.md`, item 2), nunca em botão principal. Origem: canvas (`:focus-visible` de todas as telas e o botão "Em foco" do design system).

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

Ações do cabeçalho: "Ver como lista" (secundário) e "Adicionar ligação" (principal). O formulário de "Adicionar ligação" é da Onda 4 (PROD-01).

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
| Apoio | abaixo do campo, 14 `--theme-muted`: "A senha com que você entra na Mesa." |
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

As operações sensíveis que a E2 ainda não tem (`conta-email-trocar`, `conta-fator-*`, `conta-excluir`, `equipe-convidar` como dono, `equipe-recuperar`) ficam fora da tela até existirem ([exceções](#contas-excecoes)).

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

---

<a id="contas"></a>

## Contas: Minha conta e Equipe (Onda 2)

> **Derivado, 22/11/2026, a pedido do Maestro.** A estrutura vem dos wireframes W08 e W09 do canvas ([regras](#regras-dos-wireframes)) e das decisões do dono sobre o contrato de contas (P27 e P28). Os dados vêm da entrega 2 de Contas (`lancamento/contas-o2`, `92f06f1`; contrato em `.maestro/equipe/CONTRATO_CONTAS.md`, seções 5.4, 5.5, 5.15 e 8.3; formatos em `testes/test_sessoes_conta.py` e `testes/test_equipe.py`). Não há prancha. A aparência sai dos componentes acima, como nas áreas sem tela final, e a conferência é feita contra o wireframe e esta seção. Se o dono quiser outro desenho, vale o dele. O escuro é a mesma tela com os tokens do escuro.

### Onde ficam

- **Minha conta** abre pelo perfil no rodapé da [barra lateral](#barra-lateral) (W08, regra 1). Abaixo de 1280 px, abre pelo mesmo perfil no pé da gaveta. Com a página aberta, o perfil leva `aria-current="page"` e nenhum item de área fica selecionado. No modo `local`, sem contas, não há perfil nem Minha conta.
- **Para o dono**, Minha conta, Equipe e Configurações são três [abas](#abas) no topo da página, nessa ordem; no celular, pílulas de 44 (P20b). Quem não é dono vê só Minha conta, sem a linha de abas. Cada aba aparece pela capacidade que `GET /api/sessao` devolve: Equipe com `equipe-listar`, Configurações com `ia-config`. A Mesa não decide pelo nome do papel.
- O botão "Configurações" do cabeçalho leva à aba Configurações. "Contas de acesso" sai de Configurações na mesma integração em que Equipe entra, junto com as operações `contas-*` (contrato, 5.5). Em Configurações fica só a configuração da IA, com a senha da [tabela](#dialogo-senha).

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
| **Perfil** | nome em 16/600; abaixo, o e-mail em 16, ou, na conta migrada sem e-mail, "login ana.lima" em 14 `--theme-muted`; papel e redação em 14 `--theme-muted` ("Repórter · Redação Serena", como o perfil da barra). "Mudar nome" (secundário) troca a linha do nome por um campo "Nome" (44, até 120 caracteres, já preenchido), com "Salvar" (principal) e "Cancelar" (secundário); em branco, "Falta o nome. Escreva o seu nome."; recusa do servidor abaixo do campo. Abaixo, duas caixas de seleção lado a lado, com rótulo acima (W08): **Idioma** (Português, English), que muda o idioma da Mesa, como o botão do cabeçalho, e grava o idioma da conta, com o apoio "Também é o idioma dos e-mails do Vlado."; **Tema** (Do sistema, Claro, Escuro), que fica só neste navegador, como o botão do cabeçalho, e não vai ao servidor (contrato, 2.3). O e-mail não muda aqui | `conta-ver`; `conta-atualizar` com `nome` ou `idioma` (`pt`, `en`) |
| **Entrada e segurança** | linha "Senha", com "definida há 12 dias" em 14 `--theme-muted` (de `senha_definida_em`; "definida hoje" no dia), e "Trocar senha" (secundário) à direita. As linhas do segundo fator e da chave de acesso ficam fora ([exceções](#contas-excecoes)) | `conta-ver` |
| **Onde sua conta está aberta** | uma linha por sessão. A sessão em uso vem primeiro, com "Esta sessão" em 14/600 `--theme-muted` à direita e sem botão: sai-se dela por "Sair". As outras seguem na ordem do servidor (uso mais recente primeiro), com "Encerrar" (secundário). Cada linha tem o aparelho em 16 ("Firefox · Linux", "Aplicativo Android": o texto do servidor, `translate="no"`) e, abaixo, em 14 `--theme-muted`, o último uso e o endereço ("ontem, 21h10 · 189.40.12.7"). Com duas sessões ou mais, "Encerrar todas as outras" (secundário) no pé, e o apoio "Encerrar vale na próxima ação daquele aparelho." (contrato, 8.3). Encerrar é imediato, sem diálogo (W08, regra 5); o botão fica "Encerrando…", a linha sai e a linha de estado diz "✓ Sessão encerrada: Edge · Windows." ou "✓ 2 sessões encerradas." Se o servidor responder "Sessão não encontrada.", a lista recarrega, sem erro | `conta-sessoes`; `conta-sessao-encerrar` com `sessao`; `conta-sessoes-encerrar-outras` |
| **Seu uso neste mês** | "Gasto com IA" em 16 e o valor em 16/600 à direita ("R$ 18,40 de R$ 50": gasto sempre com centavos; teto sem centavos quando inteiro, como na barra); [medidor](#medidor) de 6 px com `aria-label` ("37% da cota usada"); apoio "O teto é definido pelo dono da redação." Esgotada, o cartão vira o aviso da cota esgotada da barra ("! Cota esgotada", cores de aviso). Sem a rota, o cartão some. Sempre em reais, nunca em tokens (W08, regra 7) | `GET /api/cota`, bloco `conta` |
| **Seus dados** | texto 16: "Exportar seus dados e excluir sua conta ainda não estão na Mesa. Para pedir, fale com o dono da redação." Para o dono, "fale com quem administra o serviço". Sem botões ([exceções](#contas-excecoes)) | nenhum |

Datas, nesta página e na Equipe: "agora" no primeiro minuto; "hoje, 14h32"; "ontem, 21h10"; "18 de nov., 09h05"; de outro ano, "18 de nov. de 2025". Em inglês, pelo i18n.

**Diálogo "Trocar senha"** (W08, regra 2). É a variante [com senha](#dialogo-senha), com três campos em coluna e intervalo de 16:

- "Senha atual" (`current-password`);
- "Nova senha" (`new-password`), com o apoio "De 12 a 256 caracteres. Pode colar ou usar o gerenciador de senhas.";
- "Repita a nova senha" (`new-password`).

Texto: "As outras sessões desta conta serão encerradas. Esta continua aberta." Ação principal "Trocar senha" ("Trocando…").

Antes de enviar, a Mesa confere e põe cada erro no seu campo:

- senha atual em branco: "Falta a senha atual. Digite a senha com que você entra hoje.";
- nova senha fora do tamanho: "A senha deve ter de 12 a 256 caracteres.";
- as duas novas diferentes: "As duas senhas não coincidem. Digite a mesma senha nos dois campos."

Respostas do servidor:

- `senha_atual_incorreta`: "Senha atual incorreta. Confira e tente de novo.", no campo da senha atual;
- `bloqueado`: o texto de bloqueio da [tabela](#dialogo-senha);
- sucesso (`{estado: "senha_trocada", sessoes_encerradas: n}`): o diálogo fecha, a lista de sessões recarrega e a linha de estado diz "✓ Senha trocada." seguido de "Nenhuma outra sessão estava aberta.", "1 outra sessão foi encerrada." ou "3 outras sessões foram encerradas."

<a id="equipe"></a>

### Equipe (W09)

Só para quem tem `equipe-listar`, isto é, o dono. Os dados vêm de `equipe-listar` (`redacao`, `pessoas`, `gasto`, `convites`, que sai vazio na E2).

**Perfil antigo.** Se alguém tem o papel `convidado`, um aviso em linha da Mesa (`.notice`, cores de aviso, `role="status"`) aparece acima da tabela: "2 pessoas ainda têm o perfil antigo de convidado: perguntam só nas apurações liberadas e veem só as próprias conversas. Escolha um papel para cada uma ou remova da redação." (contrato, 2.4, decisão 1).

| Parte | Medida e conteúdo |
|---|---|
| Tabela, de 1024 px para cima | cartão com tabela, como a lista de [Documentos](#documentos): células com preenchimento 12 16 e filete 1 px `--theme-line`; cabeçalho 14/600 `--theme-muted` em fundo `--theme-reading`. Colunas: Pessoa, Papel, Apurações, Uso no mês e a ação, que tem rótulo só para leitor de tela ("Ações") |
| Pessoa | nome em 16 (na própria linha, seguido de "(você)" em 14 `--theme-muted`); abaixo, e-mail ou "login rui.castro" em 14 `--theme-muted`, `translate="no"`. Quando a conta não está ativa, vem uma terceira linha, sempre com sinal e texto, em 14 `--theme-muted`: "○ Desativada"; "◐ Aguardando a senha"; com o link vencido, "◐ Link de ativação vencido" |
| Papel | caixa de seleção de 44 px, com rótulo só para leitor de tela ("Papel de Ana Lima"): Dono, Editor, Repórter, Leitor. No perfil antigo, "Convidado (perfil antigo)" aparece selecionado e indisponível: não se escolhe de novo. Na própria linha, o papel é só texto: o próprio papel muda por outro dono |
| Apurações | "Todas" para dono (`casos` nulo); para os demais, os títulos do catálogo separados por vírgula, até três, e depois "e mais 2"; sem nenhuma, "Nenhuma" em `--theme-muted` |
| Uso no mês | "R$ 18,40" (`gasto.gasto_brl`); "—" quando `gasto` vem nulo. Com teto próprio, abaixo, em 14 `--theme-muted`, "teto R$ 30". Esgotado: "! R$ 50,00 · esgotada" em 14/600 `--theme-warning` |
| Ação | "Gerenciar": `<button>` com cara de [link](#link) (16/600 `--theme-accent`, sublinhado, altura mínima 44), `aria-expanded` e `aria-controls`. A própria linha não tem |
| Lista, abaixo de 1024 px | um cartão por pessoa, preenchimento 16, intervalo 8: nome em 600, e-mail e situação em 14 `--theme-muted`, "Papel" com rótulo visível e caixa de largura cheia, apurações e uso em 14, e "Gerenciar" (secundário, largura cheia) |

**Mudar o papel.** A mudança vale ao escolher. Sem dono no meio, vai direto e a linha de estado diz "✓ Ana Lima agora é Editor. Vale na próxima ação."; enquanto o pedido corre, a caixa fica indisponível. Com dono no meio (o papel atual ou o novo), abre o diálogo [com senha](#dialogo-senha). Do perfil antigo para qualquer papel, abre antes a variante simples: "Converter Cora Dias em Leitor?", com o texto "Leitor lê também o caderno, os achados e o texto das apurações de que participa." e a ação "Converter" (princípio 9 do contrato: a leitura nova é decisão de quem converte). Cancelar ou receber uma recusa devolve a caixa ao papel anterior. Recusa `ultimo_dono`: o texto do servidor na linha de estado, em 14 `--theme-danger`, com `role="alert"`.

**Gerenciar** abre uma linha abaixo da pessoa, que ocupa todas as colunas. Fundo `--theme-background`, preenchimento 16, três blocos em grade com intervalo de 24; numa coluna no celular. Cada bloco tem título 14/600 maiúsculo em `--theme-muted`:

| Bloco | Conteúdo |
|---|---|
| APURAÇÕES | as apurações da pessoa, uma por linha com ação. Quando ela é a responsável, a linha mostra "responsável" em 14 `--theme-muted` e não tem "Retirar", com o apoio "Quem é responsável não sai da apuração por aqui." Nas demais, "Retirar" (secundário). Abaixo, "Incluir em" (caixa com as apurações da redação em que a pessoa não está) e "Incluir" (secundário). Para dono, só o texto "Todas as apurações da redação." Resultado: "✓ Ana Lima agora participa de Campo Verde." ou "✓ Ana Lima não participa mais de Campo Verde." (`caso-incluir`, `caso-retirar` com `caso` e `conta`) |
| TETO MENSAL | campo "Teto de gasto com IA, em reais", de 44 px e até 160 px de largura, `inputmode="decimal"`, aceitando "30" e "30,50"; "Salvar" (secundário). Apoio: "Padrão da redação: R$ 50. Não passa do teto da redação." Com teto próprio, "Usar o padrão" ([link](#link)) o apaga. A Mesa envia `teto_brl` como texto com ponto ("30.50"), nunca como número, e `null` para voltar ao padrão (`equipe-teto` com `conta`). Recusa: o texto do servidor abaixo do campo |
| ACESSO | conta ativa: "Desativar" e "Remover da redação" (destrutivos). Conta desativada: "Reativar" (secundário, sem diálogo) e "Remover da redação". Apoio: "Desativar encerra as sessões e para as perguntas em curso; as apurações ficam. Remover exclui a conta." Os diálogos estão na [tabela](#dialogo-senha) |

O "Recuperar acesso" de hoje sai com as `contas-*` ([exceções](#contas-excecoes)).

**Abaixo da tabela**, em grade de duas colunas:

| Cartão | Conteúdo | Dados |
|---|---|---|
| **Gasto com IA neste mês** | com `gasto`: "R$ 24,50 de R$ 150" (16/600), o [medidor](#medidor) e o apoio "Cota da redação, definida por quem administra o serviço." Com `gasto` nulo, sem valor nem medidor, o apoio "O gasto da redação aparece aqui quando o serviço passar a contá-lo por redação. O de cada pessoa está na tabela." (contrato, 4.5). Abaixo, em todos os casos, o campo "Teto padrão por pessoa, em reais", igual ao do Gerenciar, com "Salvar"; vazio quer dizer o teto da instalação, e o apoio diz isso | `equipe-listar`; `equipe-teto` sem `conta` |
| **Atividade recente** | largura das duas colunas. As cinco últimas ações, uma por linha: a frase em 16 e, à direita, a data em 14 `--theme-muted`. Depois, "Mostrar mais" (secundário), que traz 50 de cada vez enquanto houver `proximo`. Só acessos e administração, nunca conteúdo (W09, regra 8). Sem nenhuma: "Nenhuma ação registrada ainda." | `equipe-atividade` com `limite` e `antes` |

Frases da atividade. "Fulano" é `por_nome` e "Beltrano" é `conta_nome`; quando os dois são a mesma conta, a frase usa só o nome dela.

- Sem nome (conta removida): "uma conta removida".
- Sem `por` de conta (operador ou migração): "Quem administra o serviço".

| Tipo | Frase |
|---|---|
| `papel_alterado` | Fulano mudou o papel de Beltrano |
| `conta_desativada` / `conta_reativada` | Fulano desativou / reativou a conta de Beltrano |
| `conta_excluida` | Fulano removeu Beltrano da redação |
| `conta_criada` | Fulano criou a conta de Beltrano |
| `participacao_incluida` / `participacao_retirada` | Fulano incluiu Beltrano numa apuração / retirou Beltrano de uma apuração |
| `responsavel_alterado` | Fulano mudou o responsável de uma apuração |
| `teto_alterado` | Fulano mudou um teto de gasto |
| `senha_trocada` / `senha_definida` | Beltrano trocou / definiu a senha |
| `sessao_encerrada_a_distancia` | Beltrano encerrou sessões em outros aparelhos |
| `conta_atualizada` | Beltrano atualizou o perfil |
| `recuperacao_emitida` | Fulano gerou um novo link de ativação para Beltrano |
| `login_bloqueado` | A entrada de Beltrano foi bloqueada por muitas tentativas |
| qualquer outro | Ação de administração |

**Só o dono na redação**: a tabela tem uma linha, e abaixo dela vem o texto da exceção do convite.

<a id="contas-excecoes"></a>

### Exceções declaradas, por falta de servidor ou por decisão do dono

A conferência destas telas não barra por elas. Cada uma volta ao wireframe quando o servidor existir, e a tela é conferida de novo nesse ponto.

| O que o wireframe mostra | O que a tela mostra até lá | Volta quando |
|---|---|---|
| W08: código do autenticador e códigos de reserva | as linhas ficam fora | houver segundo fator (contrato, 8.2) |
| W08 e W10: chave de acesso | fora | não volta: decisão 4 do contrato (P27) |
| W08: cidade aproximada da sessão | aparelho, último uso e endereço | não volta: decisão 5 do contrato (P27) |
| W08: "14 perguntas" no uso do mês | só o valor em reais | `GET /api/cota` trazer a contagem |
| W08: "Exportar meus dados" e "Excluir minha conta" | o cartão Seus dados, só com o caminho por pessoa | houver `conta-exportar` e `conta-excluir` (contrato, 8.4); "Excluir" vem com o diálogo com senha e o nome digitado |
| W09: "Convidar pessoa", convites pendentes e "Reenviar" | nada no lugar do botão; abaixo da tabela, em 14 `--theme-muted`, "Para incluir alguém na redação, fale com quem administra o serviço." | houver convite por e-mail (contrato, 8.1) |
| W09: cartão "Chave de IA da redação" | a chave continua em Configurações, como hoje, com a senha | houver chave por redação (contrato, 8.5, parte da Plataforma) |
| W09: "aviso em 80%" e "redação convidada para o teste" | só o teto e a contagem de pessoas | o servidor informar o aviso e a situação do teste |
| W09: "Ana entrou de novo aparelho" na atividade | a atividade sem esse evento | houver aparelho conhecido (contrato, 8.2 e 8.3) |
| "Recuperar acesso" da tela de hoje | fora | houver `equipe-recuperar`, com dupla confirmação (contrato, 8.2) |
| Autor de conta removida como "Conta excluída" | o texto de remover não promete a troca | vier o ciclo de vida (contrato, 8.4 e 12) |

### Ganchos com o resto da Mesa

| Gancho | Quem |
|---|---|
| O perfil no rodapé da barra e no pé da gaveta abre Minha conta e recebe `aria-current` | Lume (barra) e Vitral (página) |
| O botão "Configurações" do cabeçalho leva à aba Configurações | Lume |
| As caixas "Idioma" e "Tema" usam o mesmo estado dos botões "English" e "Modo escuro" do cabeçalho. Mudar num lugar muda no outro | Lume e Vitral |
| O estado "Redação suspensa" ([estados](#estados)) vale para a Mesa inteira, a partir de qualquer resposta 403 `redacao_suspensa` | Lume |
| O campo de senha no "Apagar definitivamente" (`gerenciar.js`) e em Configurações (`configuracao_ia.js`) entra na mesma integração em que o servidor passa a pedi-la | Vitral, com Contas |

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

Pela regra 1 do contrato, nada disto é construído antes de o Design desenhar e o dono aprovar: os formulários de resposta e de recurso dos pedidos de LAI, com o cálculo do prazo (PROD-07); fontes e capturas de site dentro da apuração; lixeira; configuração da organização; página pública; versões de celular das demais telas de desktop (e, no sentido inverso, o Entrar em desktop); faixa de 720 a 1023 px; tema escuro das telas do canvas fora as três de desktop; sem aviso com "Desfazer" por ora (P12.7). Desenhados na fase 3 e aprovados pelo dono em 21/11/2026: diálogo de confirmação, escuro de conferir achado, visão geral e design system, tablet de 1024 px e celular de 390 px de conferir achado e visão geral ([Telas derivadas](#telas-derivadas)). O conjunto de ícones (parte E) está na seção [Conjunto de ícones do Vlado](#conjunto-de-icones), com cinco ícones derivados, aprovados pelo dono em 21/11/2026. Aprovados também em 21/11/2026, em [Áreas sem tela final](#telas-aprovadas): caderno, hipóteses, tabelas, comparador, mapa e linha do tempo no celular, Pedidos e prazos e Documentos. Têm só a captura da Mesa de hoje, sem desenho: Perguntar no desktop (há o W03), Diligências, Apurações e lixeira, e Configurações. Minha conta, Equipe e Configurações (W08 e W09) têm especificação sem prancha em [Contas](#contas), de 22/11/2026.

## Decisões do dono (21/11/2026)

Respostas do dono às perguntas desta especificação e às pranchas de `aprovacao/`, repassadas pelo Maestro (P11, P12, P14, P14b, P15 e P16 da nota de decisões; P20a e P20b, de 22/11/2026). Não há pergunta aberta nesta seção.

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

As 27 pranchas da fase 3 e as de `aprovacao/` foram aprovadas e regeneradas com estas decisões, inclusive a barra de 256 px. As telas finais do canvas em `referencia/telas/` continuam como estão: são o registro do contrato; as decisões acima valem sobre elas onde houver diferença, e `referencia/com-decisoes/` mostra as sete telas com elas aplicadas.
