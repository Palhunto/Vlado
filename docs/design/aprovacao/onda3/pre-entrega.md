---
type: reference
title: Lista de pré-entrega da Onda 3
created: 2026-11-22
tags: [design, onda3, portao, acessibilidade]
related: ['[[componentes]]', '[[mudancas-de-token]]', '[[LEIA-ME]]']
---

# Lista de pré-entrega da Onda 3

*Revisão de 22/11/2026: a primeira versão dava como cumpridos os filetes, o foco e a coluna Temas; o medidor da Sonda mostrou o contrário (B1 da Coruja sobre `0750504`).*

Primeiro item do portão da Onda 3 (`PLANO_LANCAMENTO.md`, Onda 3): a lista de pré-entrega da skill `ui-ux-pro-max` (`references/pro-rules.md`, "Pre-Delivery Checklist"), conferida tela por tela na Mesa como está na integração `b5874ad`, com a linha de base visual `db4e032` (130 capturas, `testes/referencias_visuais/windows/`, branch `lancamento/qa-o3`).

**Como foi conferida (22/11/2026).**

- Capturas: cada tela em 375, 768, 1024 e 1440 px, nos dois temas, comparadas com a linha de base de antes da Onda 3 (`3bf52c8`).
- Código: o que a captura não mostra foi conferido em `b5874ad`, como movimento reduzido, alvos, `aria-hidden` e estados desabilitados.
- Tradução para a web: a lista da skill é escrita para aplicativo nativo. "Dynamic Type" vira texto ampliado a 200 %; "safe area" e "gesto" só valem onde a Mesa tem barra fixa ou arrasto.

Legenda:

- **C**: cumprido, com a prova;
- **E**: exceção declarada, com o lugar em que está registrada;
- **F**: falta; vira uma ressalva com dono, na última seção;
- **—**: não se aplica à Mesa, com a razão.

## Itens da Mesa inteira

### Processo

| Item | Estado | Prova ou razão |
|---|---|---|
| Só consultas relevantes à interface | C | `componentes.md`, "Consultas às skills" |
| Passada final por `quick-reference.md` §1 a §3 | C, com ressalva | Esta lista cobre §1 e §2. O §3 (desempenho) é o item "primeira carga em rede móvel medida antes e depois" do portão, separado desta lista |
| Testado em 375 px | C | linha de base `db4e032`, 375 nos dois temas, todas as telas |
| Testado em paisagem | C | 14 telas em 812×375, nos dois temas, sem rolagem lateral (`lancamento/qa-o3` `dbf0281`, `testes/referencias_visuais/windows_extras/`); R6 resolvida |
| Movimento reduzido | C | `prefers-reduced-motion` em `style.css` (5 blocos), `componentes_o3.css`, `caderno.css` e `entrar.css`; o esqueleto não pulsa (`componentes.md`, Movimento) |
| Texto ampliado (equivalente web do Dynamic Type) | C | 14 telas com a página a 200 %, nos dois temas, sem rolagem lateral nem texto cortado (`lancamento/qa-o3` `dbf0281`, `testes/referencias_visuais/windows_extras/`); R6 resolvida |
| Escuro conferido por conta própria | C | contraste de cada par medido nos dois temas em `mudancas-de-token.md`; capturas nos dois temas |
| Alvos ≥ 44 px; nada sob área fixa | C | `min-height: 44px` em `style.css` (17) e `caderno.css` (4); a Mesa não tem barra fixa no pé |

### Aparência

| Item | Estado | Prova ou razão |
|---|---|---|
| Nenhum emoji como ícone | C | sinais em SVG embutido (`interface/app.js:587`); ✓ ○ ◐ ! são caracteres de texto ao lado do rótulo, com `aria-hidden` |
| Ícones de uma família só | C | conjunto do Vlado, traço único (`docs/design/icones/`, `componentes.md#conjunto-de-icones`) |
| Marca oficial com proporção certa | — | a marca "Vlado." é tipográfica, sem arquivo de logotipo |
| Pressionar não mexe no leiaute | C | `button:active` desce 1 px por `transform` (`style.css:869`), sem mudar a caixa |
| Tokens semânticos, sem cor solta por tela | C | `interface/tokens.css`; mudanças em `mudancas-de-token.md` |

### Interação

| Item | Estado | Prova ou razão |
|---|---|---|
| Retorno ao pressionar | C | `transform` ao pressionar e fundo ao passar o mouse (`componentes.md#botao`) |
| Alvos mínimos | C | ver Processo; links dentro do texto ("Ver apurações →", "trocar") seguem a exceção de alvo em linha do WCAG 2.5.8 |
| Tempo de transição por token | C | 150 ms de cor e fundo (`componentes.md`, Movimento) |
| Desabilitado claro e sem ação | **F no escuro** | no claro: fundo `--theme-sidebar` e texto `--theme-muted` (`style.css:876`). No escuro, os botões desabilitados do Caderno, aba Trechos ("Criar cruzamento humano", "Exportar selecionados", "Limpar seleção", "Usar selecionados numa pergunta"), parecem habilitados (`caderno__375__escuro`, `caderno__1440__escuro`) → **R2** |
| Ordem de foco igual à visual; rótulos claros | C para teclado | capturas `foco_*` (o capturador chega ao alvo por Tab). A rodada com leitor de tela é de pessoa (Manual Follow-Up), não de captura |
| Sem gestos em conflito | — | a Mesa não usa gesto; o mapa tem botões e lista |

### Claro e escuro

| Item | Estado | Prova ou razão |
|---|---|---|
| Texto ≥ 4,5:1 nos dois temas | C | `mudancas-de-token.md`, pares medidos |
| Filetes e estados visíveis nos dois temas | **F**, e E no seletor | O medidor de contraste da Sonda (`lancamento/qa-o3` `1ac811d`), sobre esta mesma linha de base, reprova 54 de 1064 anéis de foco e 56 de 124 contornos de campo. São quatro grupos, decididos em `componentes.md#foco-aa`: o anel que encosta no item ativo da barra e das abas e o editor do Caderno sem anel → **R8**; o título da nota sem contorno visível → **R9**; o seletor de apuração do topo sem caixa → **E**, decisão do dono P34. C55 e C58 ficam abaixo de 3:1 e são decorativos (`mudancas-de-token.md`). O desabilitado no escuro é a **R2** |
| Véu de diálogo legível sobre o fundo real | C | o diálogo é opaco sobre `--theme-backdrop`; pranchas `novas/telas/dialogo-*` aprovadas (21/11/2026) |
| Os dois temas testados | C | linha de base com claro e escuro em toda tela |

### Leiaute

| Item | Estado | Prova ou razão |
|---|---|---|
| Áreas seguras | — | página web sem barra fixa no pé nem no topo sobre o conteúdo |
| Rolagem não fica sob barra fixa | C | nenhuma barra fixa cobre conteúdo; o compositor do celular não cobre o foco (UX-19) |
| Celular pequeno, grande e tablet, retrato e paisagem | C | 375, 430, 768, 1024 e 1440 px, e paisagem de 812×375 (`lancamento/qa-o3` `dbf0281`, `testes/referencias_visuais/windows_extras/`); R6 resolvida |
| Margens por largura | C | 16 px no celular, 32 no desktop |
| Ritmo de 4/8 px | C | arredondamento para a grade de 4 px (P11.8) |
| Medida de leitura | C | até 70 caracteres no texto de leitura (UX-10) |

### Acessibilidade

| Item | Estado | Prova ou razão |
|---|---|---|
| Ícone decorativo fora da árvore de acessibilidade | C | `aria-hidden` nos ícones ao lado de texto (`app.js`, `analise.js`, `quadros.js`, `desktop.js`, `codex.js`, `experiencia.js`) |
| Ícone com sentido tem texto | C | nós do mapa com o nome inteiro ao leitor de tela (`b5874ad`); selos com texto |
| Controle só de ícone com nome e estado | C | "Abrir navegação" com `aria-label` e `aria-expanded` (`index.html:49`) |
| Campos com rótulo, dica e erro claro | C | erro junto ao campo (UX-15; `componentes.md#campo` e W11) |
| Cor nunca sozinha | C | estados sempre com sinal e texto (W02, regra 5; P20a) |
| Movimento reduzido e texto ampliado sem quebrar | C | movimento: ver Processo; texto a 200 %: R6 resolvida |
| Interface fixa não cobre o foco | C | UX-19 |
| Arrastar tem alternativa | C | envio por arrasto tem "escolha no computador" e "Escolher arquivos"; o mapa tem a lista |
| Entrada aceita gerenciador de senha e colar | C | Entrar com `autocomplete` e "Mostrar"; nenhuma trava de colar |
| Conteúdo que gira sozinho | — | a Mesa não tem |
| Erros ficam no campo depois do envio; resumo com foco | E | sem resumo de erros: os formulários são curtos e o foco vai ao primeiro campo com erro (`componentes.md#campo`, estado Erro) |

## Tela por tela

Colunas:

- **375**: sem rolagem lateral da página no celular;
- **Temas**: contraste e filetes nos dois temas;
- **Desab.**: desabilitado visível nos dois temas;
- **Corte**: nenhum texto ou controle cortado;
- **Alvos**: controles com 44 px;
- **Desenho**: fora da lista da skill, mas do mesmo portão, a tela confere com o desenho aprovado (contrato visual).

| Tela (captura) | 375 | Temas | Desab. | Corte | Alvos | Desenho |
|---|---|---|---|---|---|---|
| Entrar (`entrar`) | C | C | — | C | C | **F**: ainda é o formulário antigo ("Login", sem a marca de 40 px, a frase, o aviso de teste e o rodapé do canvas) → **R5**. A chave de acesso fica fora por decisão do dono (decisão 4 do contrato de contas) |
| Visão geral (`inicio`) | C | **F** → **R8** (anel da barra lateral); seletor do topo: E (P34) | — | C | C | C (telas derivadas, aprovadas em 21/11/2026). No celular, "Trocar de apuração" e "Adicionar documentos" quebram em duas linhas (altura mínima, P11.5) |
| Documentos (`documentos`) | C | **F** → **R8** (anel da barra lateral); seletor do topo: E (P34) | — | C | C | C, com as exceções declaradas (`componentes.md#documentos`); aceita em 22/11/2026 |
| Cadastrar arquivos (`cadastro`) | C | **F** → **R8** (anel da barra lateral); seletor do topo: E (P34) | — | C | C | **F**: a área deveria deixar de existir e virar a área de envio de Documentos (P16.5) → **R4**. O "Choose Files" em inglês é o controle nativo no idioma do navegador de teste: — |
| Perguntar (`codex`) | C | **F** → **R8** (anel da barra lateral); seletor do topo: E (P34) | — | C | C | E: sem desenho no desktop (`componentes.md`, "O que ainda falta desenhar"); conferida pelos componentes |
| Conferir achados (`achados`) | C | **F** → **R8** (anel da barra lateral); seletor do topo: E (P34) | — | **F**: em 1440 e 1024 px, o botão "Conferir" sai cortado no pé de cada cartão da lista (`achados__1440__claro`, `__escuro`) → **R1** | C | C (canvas "Conferir achado"); "3 achado(s) nesta seleção" usa "(s)" → **R7** |
| Caderno, notas (`apuracao`) | C | **F** → **R8** (anel da barra lateral e do editor) e **R9** (título da nota); seletor do topo: E (P34) | — | C | C | C (P14, P14b) |
| Caderno, trechos (`caderno`) | C | **F** → **R8** (anel da barra lateral); seletor do topo: E (P34) | **F** no escuro → **R2** | C | C | C (P14b.6) |
| Pedidos e prazos (`diligencias`) | C | **F** → **R8** (anel da barra lateral); seletor do topo: E (P34) | — | C | C | **E**: o item "Pedidos e prazos" da barra abre a tela Diligências de hoje, sem a prancha aprovada (P15.5); exceção declarada da Onda 4 (decisão do Maestro, 22/11/2026; ver R3 abaixo) |
| Quadros, hipóteses (`quadros`) | C | **F** → **R8** (anel da barra lateral); seletor do topo: E (P34) | — | C | C | **E**: sete abas e barra lateral, contra cinco abas (P15.1) e quadros sem barra, com "‹ Apuração" (P11.7); hipóteses sem a prancha aprovada (P15.2); exceção declarada da Onda 4 (decisão do Maestro, 22/11/2026; ver R3 abaixo) |
| Linha do tempo (`quadros_linha`) | C | **F** → **R8** (anel da barra lateral); seletor do topo: E (P34) | — | C | C | C (canvas "Tempo", parte E), dentro da moldura de abas da R3 |
| Mapa de relações (`quadros_mapa`) | C | **F** → **R8** (anel da barra lateral); seletor do topo: E (P34) | — | C: o nome do nó corta na segunda linha, mas sai inteiro na lista abaixo e ao leitor de tela (`b5874ad`) | C | C (canvas "Mapa", parte E; escala 1) |
| Apurações e lixeira (`gerenciar`) | C | **F** → **R8** (anel da barra lateral); seletor do topo: E (P34) | — | C | C | E: sem desenho (`componentes.md`, "O que ainda falta desenhar") |
| Configurações (`configuracoes`) | C | **F** → **R8** (anel da barra lateral); seletor do topo: E (P34) | — | C | C | E: sem desenho. No modo `local`, o texto "Adicione contas para outras pessoas" aparece sem o painel de contas → **R7** |
| Foco (`foco_*`) | C | **F** → **R8** | — | — | — | C: anel ocre de 3 px com afastamento de 2 px nos dois temas; o encontro com o item ativo vizinho é a R8 |

Minha conta, Equipe, convite e redefinir a senha (Onda 2) não estão nesta linha de base. São conferidos à parte, contra `componentes.md#contas`.

## Ressalvas

| Nº | O que falta | Onde | Dono |
|---|---|---|---|
| R1 | Botão "Conferir" cortado no pé dos cartões de achado. O cartão deve crescer com o conteúdo, com altura mínima no lugar de fixa (P11.5) | Conferir achados, 1440 e 1024 | Frontend (Lume), junto com as correções do AA (`componentes.md#foco-aa`) |
| R2 | Botão desabilitado no escuro igual ao habilitado. Ele deve usar a aparência "Indisponível" também no escuro (`componentes.md#botao`) | Caderno, aba Trechos, e qualquer botão desabilitado no escuro | Frontend (Lume), junto com as correções do AA (`componentes.md#foco-aa`) |
| R3 | **Exceção declarada, não é falta** (decisão do Maestro, 22/11/2026): Quadros com sete abas e barra lateral, e Pedidos e prazos abrindo Diligências, ficam como estão até a Onda 4, porque a página dos quadros ainda espera desenho. **Volta quando** a Onda 4 entregar a página dos quadros com as cinco abas, sem barra lateral e com "‹ Apuração" (P11.7, P15.1, P15.2) e a área Pedidos e prazos da prancha P15.5; nesse ponto as duas telas são conferidas de novo | Quadros, Pedidos e prazos | Onda 4 |
| R4 | A área "Cadastrar arquivos" continua a existir (P16.5) | Cadastrar arquivos | Frontend (Lume), junto com as correções do AA (`componentes.md#foco-aa`) |
| R5 | O Entrar não segue o canvas: marca, frase, aviso de teste, rodapé e "E-mail" no lugar de "Login" (com a Onda 2, o campo aceita e-mail) | Entrar | Frontend (Lume), na frente do Entrar |
| R6 | Faltam capturas em paisagem de celular, em celular grande (430 px) e com texto a 200 % | linha de base | QA (Sonda) |
| R8 | Anel de foco: na barra lateral e nas abas, encosta no item ativo vizinho (ocre sobre verde, 1,62:1 no claro e 1,05:1 no escuro); no editor do Caderno, não aparece. Correção decidida em `componentes.md#foco-aa`, (a) e (b) | todas as telas da Mesa; Caderno | Frontend (Lume) |
| R9 | Contorno de campo: o título da nota no Caderno tem sublinhado da cor do fundo. Correção decidida em `componentes.md#foco-aa`, (d) | Caderno, notas | Frontend (Lume) |
| R7 | Textos: "3 achado(s)" sem concordância (o plural deve concordar, sem "(s)"); o texto de Configurações no modo `local` fala de contas que não aparecem | Conferir achados, Configurações | Frontend (Lume), junto com as correções do AA (`componentes.md#foco-aa`) |

**Resolvidas e conferidas pelo Design (22/11/2026), em `lancamento/frontend-o3`:**

- R1, em `ccbd4a9`: o botão "Conferir" fica dentro do cartão de achado (provado pelas capturas com a análise R001, em 1440 e 1024, nos dois temas);
- R2, em `ccbd4a9`, com o token `--theme-disabled-text`;
- R4, em `16f9e6e` e `db4124d`: "Cadastrar arquivos" saiu, a Nova apuração vem pelo W01 e o recibo acompanha a pergunta;
- R8 e R9, em `0303919`;
- R7, em `9520fc3` (plural concordado nos achados) e `599e9e2` (Configurações sem o texto de contas). A lista foi medida na linha de base `db4e032`, anterior a esses dois commits;
- R5, em parte, em `7c2345c` e `61d7fe3`: o Entrar ganhou as seções da Onda 2; a conferência com o canvas inteiro fica para a captura nova da linha de base.

- R6, em `dbf0281` (`lancamento/qa-o3`): 84 capturas extras, de 14 telas em 430×932, em paisagem 812×375 e com a página a 200 %, nos dois temas. Nenhuma tem rolagem lateral. O Design aceitou 78 como referência. Em `9e2dd95` (`lancamento/qa-o3`), a Sonda regerou as 14 `nova` com a linha de etapas do passo 1 (correção do Lume em `06d478e`) e os 10 `foco_mesa_*`, e acrescentou 28 capturas de reflow a 320 px (WCAG 1.4.10), sem rolagem lateral em nenhuma. O Design conferiu e aceitou todas em 23/11/2026. A R6 está resolvida por inteiro.

Aberta: só a R3, exceção declarada até a Onda 4. Com isso, a lista de pré-entrega da Onda 3 está cumprida.

R1 e R2 são da lista da skill. R4 e R5 são divergências do desenho aprovado; R3 também, mas é exceção declarada até a Onda 4. R6 é falta de prova. R7 é texto. R8 e R9 são do portão AA (medidor da Sonda, `1ac811d`); o seletor do topo sem caixa não é falta: é a decisão P34 do dono.
