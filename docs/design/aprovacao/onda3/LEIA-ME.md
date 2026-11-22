---
type: reference
title: Aprovação visual da Onda 3
created: 2026-11-22
tags: [design, onda3, aprovacao, portao]
related: ['[[pre-entrega]]', '[[componentes]]']
---

# Aprovação visual da Onda 3

Último item do portão da Onda 3: o dono olha a Mesa como ficou e aprova, ou diz o que muda. Isso é Manual Follow-Up: nenhum agente marca como feito.

**O que olhar.** As capturas da linha de base `db4e032`, feita sobre a integração `b5874ad`. Ficam em `testes/referencias_visuais/windows/`, na branch `lancamento/qa-o3` e, depois do merge, na integração. O nome de cada arquivo é `<tela>__<largura>__<tema>.png`, com larguras 375, 768, 1024 e 1440 e temas `claro` e `escuro`. Os dados são sintéticos.

Para ver como era antes da Onda 3, use a mesma captura em `3bf52c8`, por exemplo `git show 3bf52c8:testes/referencias_visuais/windows/inicio__1440__claro.png > antes.png`.

**Em cada tela**, olhe primeiro a de 1440 claro, depois a de 375 claro e por fim a de 1440 escuro. As de 768 e 1024 mostram a gaveta no lugar da barra lateral.

**O que muda em todas as telas:**

- Barra lateral nova, de 256 px, com as sete áreas sem ícones (P11.6, P15.7). O contador do item ativo vira pílula, e o cartão da cota fica no rodapé.
- Cabeçalho com "Apuração", a versão dos documentos, "English" e "Modo escuro".
- Títulos de área em serifa.
- Abaixo de 1280 px, a barra vira gaveta e abre pelo botão de menu.
- Botões e campos de 44 px; anel de foco ocre.

Antes de aprovar, veja a [lista de pré-entrega](pre-entrega.md). Ela tem seis ressalvas com dono (R1, R2 e R4 a R7) e uma exceção declarada até a Onda 4 (R3). Três aparecem nas capturas: o botão cortado em Conferir achados (R1), o desabilitado no escuro (R2) e os quadros no desenho antigo (R3, exceção).

## Ordem

| # | Tela | Capturas (`testes/referencias_visuais/windows/`) | O que mudou |
|---|---|---|---|
| 1 | Entrar | `entrar__1440__claro.png`, `entrar__375__claro.png`, `entrar__1440__escuro.png` | Pouco: tamanhos e cores dos tokens novos. Ainda não é o Entrar do canvas (R5) |
| 2 | Visão geral | `inicio__1440__claro.png`, `inicio__375__claro.png`, `inicio__1440__escuro.png` | "Trocar de apuração" e "Nova apuração" no cartão do topo; "Como começar" desce para o pé; a barra perde "Nova apuração" |
| 3 | Documentos | `documentos__…` | O envio entra na própria tela (P16). A tabela mostra a leitura com sinal e texto ("✓ Texto do próprio arquivo", "○ Sem texto lido"). "Encontrar documento" fica à direita e os detalhes técnicos ficam recolhidos |
| 4 | Perguntar | `codex__…` | Só a moldura nova; o conteúdo é o mesmo |
| 5 | Conferir achados | `achados__…` | Selos novos: o da IA tracejado, com "IA ·" (P20a), e "○ Pendente". Contador "3" no item Conferir. Botão "Conferir" cortado na lista (R1) |
| 6 | Caderno, notas | `apuracao__…` | Abas em pílula; no celular, "Notas" e "Fontes da nota" com contagem |
| 7 | Caderno, trechos | `caderno__…` | Abas em pílula. No escuro, os botões desabilitados parecem habilitados (R2) |
| 8 | Quadros, hipóteses | `quadros__…` | A aba ativa vira pílula; as colunas Sustenta, Contraria e Falta ganham traço no topo. Continuam as sete abas e a barra lateral até a Onda 4 (R3, exceção declarada) |
| 9 | Linha do tempo | `quadros_linha__…` | Redesenho da parte E: agrupada por ano, marco cheio para data exata e vazado para parcial, ícone do tipo, fonte em cada acontecimento, filtros em pílula e "Como ler" |
| 10 | Mapa de relações | `quadros_mapa__…` | Redesenho da parte E: nós com ícone e nome, ligação com o rótulo do tipo, legenda abaixo, lista de pessoas e organizações abaixo do mapa, desenho em escala 1 |
| 11 | Pedidos e prazos | `diligencias__…` | Abre pelo item novo "Pedidos e prazos"; colunas por estado com filete; botões de 44 px. A prancha aprovada fica para a Onda 4 (R3, exceção declarada) |
| 12 | Apurações e lixeira | `gerenciar__…` | Sai da barra lateral; só a moldura nova |
| 13 | Configurações | `configuracoes__…` | Só a moldura nova |
| 14 | Cadastrar arquivos | `cadastro__…` | Só a moldura nova; a área deveria ter saído (R4) |
| 15 | Foco do teclado | `foco_entrar_campo__*`, `foco_entrar_botao__*`, `foco_mesa_campo__*`, `foco_mesa_botao__*`, `foco_mesa_barra__1440__*` | Anel ocre de 3 px, a 2 px do controle, nos dois temas |

`…` quer dizer as mesmas três capturas da linha 2: `__1440__claro.png`, `__375__claro.png` e `__1440__escuro.png`.

Minha conta, Equipe, o convite e redefinir a senha são da Onda 2 e ainda não estão na linha de base. Entram numa aprovação própria quando forem integrados.

## Para responder

Para cada tela: "aprovada", "aprovada com ressalva" ou "muda", e o quê. As ressalvas já têm dono na lista de pré-entrega, e a R3 é exceção até a Onda 4. O dono diz se alguma delas impede a aprovação.
