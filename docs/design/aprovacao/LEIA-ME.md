# Telas para aprovação do dono

Pedido do dono em 21/11/2026: ver no desenho novo as áreas da Mesa que não têm tela final no canvas. Cada pasta traz a Mesa de hoje (`atual-*`, só como referência, capturada com dados sintéticos em 127.0.0.1), a proposta derivada (`proposta-*`, na linguagem do canvas, marcada "Derivado · aguarda aprovação do dono") e um `LEIA-ME.md` com o que decidir. Nada aqui é construído antes da aprovação (regra 1 do contrato visual). Em 21/11/2026 o dono aprovou caderno, quadros, Pedidos e prazos, documentos e cadastro (P14, P14b, P15 e P16); a especificação está em [`componentes.md`](../componentes.md#telas-aprovadas). Com a P15.7, a barra lateral de todas as pranchas passou a 256 px.

## Áreas da Mesa e o que já tem desenho

| Área (endereço `?area=`) | Tela final no canvas | Pranchas do Design | Wireframe | Pasta aqui |
|---|---|---|---|---|
| Visão geral (`inicio`) | sim | escuro, 1024 e 390 (`../novas/`) | — | — |
| Conferir achados (`achados`) | sim | escuro, 1024 e 390 (`../novas/`) | — | — |
| Perguntar à IA (`codex`) | só celular, escuro | — | W03 | `perguntar/` (só atual) |
| Caderno (`apuracao`) | não | **proposta aprovada pelo dono em 21/11/2026** | W04 | `caderno/` |
| Quadros (`quadros`): mapa de relações e linha do tempo | sim | escuro e 390 derivados, **aprovados pelo dono em 21/11/2026** | — | `quadros/` |
| Quadros: hipóteses | não | **proposta aprovada pelo dono em 21/11/2026** | W05 | `quadros/` |
| Quadros: tabelas | não | **proposta aprovada pelo dono em 21/11/2026** | W06 | `quadros/` |
| Quadros: comparador | não | **proposta aprovada pelo dono em 21/11/2026** | W07 | `quadros/` |
| Quadros: conferência do texto | não | vai para o caderno (W04) | W04 | `caderno/` |
| Quadros: entrevistas e pedidos (vira "Pedidos e prazos") | não | **proposta aprovada pelo dono em 21/11/2026** | nenhum (pedidos e prazos de LAI estão na lista do que falta desenhar) | `quadros/` |
| Documentos (`documentos`) e Cadastrar arquivos (`cadastro`) | não | **proposta aprovada pelo dono em 21/11/2026** (uma tela só) | W02 | `documentos/`, `cadastro/` |
| Diligências (`diligencias`) | não | — | nenhum | `diligencias/` (só atual) |
| Apurações e lixeira (`gerenciar`) | não | — | nenhum (lixeira na lista do que falta desenhar) | `apuracoes-e-lixeira/` (só atual) |
| Configurações (`configuracoes`) | não | — | W08 e W09 em parte (conta e equipe) | `configuracoes/` (só atual) |
| Entrar | sim | — | W10 (convite) | — |

Ordem de trabalho combinada: caderno, quadros, documentos e cadastro. As capturas das outras áreas ficam só como referência do que existe hoje.

## Como foi feito

- `ferramentas/capturar_mesa.cjs`: a Mesa de hoje, com a pasta de dados preparada por `vlado_lancador.preparar_dados` e semeada por `semear_ambiente.semear` (ambiente de demonstração, sem chamada de modelo), servida em 127.0.0.1 numa porta livre. Uma captura por vez, recortada na janela: 1440 × 900 e 390 × 844, temas claro e escuro.
- `ferramentas/gerar_propostas.cjs`: as propostas, em HTML com os tokens de `../novas/fonte/base.css`, renderizadas pelo mesmo processo das pranchas da fase 3. O conteúdo é sintético e está desenhado na própria prancha.
- `ferramentas/montar_comparativo.py`: junta atual e proposta lado a lado.
