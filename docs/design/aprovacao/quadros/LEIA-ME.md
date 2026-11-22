# Quadros: o que o dono decidiu

**Propostas: derivado, aprovado pelo dono em 21/11/2026** (P15.1 a P15.7, faixa verde nas pranchas). O mapa de relações e a linha do tempo de 1440 px no claro são as telas finais do canvas, com as decisões de 21/11/2026 aplicadas. Especificação em [`componentes.md`](../../componentes.md#quadros) (quadros) e [Pedidos e prazos](../../componentes.md#pedidos-e-prazos). Todas as pranchas seguem as decisões P11 e P12: caminho de volta "‹ Apuração" no cabeçalho, grade de 4 px, 12 px nos cartões, órgão público em ameixa, altura mínima.

| Arquivo | O que é |
|---|---|
| `atual-{claro,escuro}-{1440,390}.png` | a Mesa de hoje, área Quadros de evidência, sem rodada sintética (aba Hipóteses vazia) |
| `proposta-hipoteses-*` | Hipóteses, pelo W05 |
| `proposta-linha-do-tempo-*` | Linha do tempo: canvas em 1440 claro; escuro e 390 derivados |
| `proposta-mapa-*` | Mapa de relações: canvas em 1440 claro; escuro e 390 derivados |
| `proposta-tabelas-*` | Tabelas, pelo W06 |
| `proposta-comparador-*` | Comparador, pelo W07 |
| `proposta-pedidos-e-prazos-*` | a aba "Entrevistas e pedidos" de hoje, como área própria (sem wireframe) |
| `comparativo-hipoteses-*` | Mesa de hoje e proposta de Hipóteses lado a lado |

## O que muda

- **Sete abas viram cinco.** Hoje: Hipóteses, Linha do tempo, Comparador, Tabelas, Mapa de relações, Conferência do texto, Entrevistas e pedidos. Proposta: as quatro do canvas (Hipóteses, Linha do tempo, Mapa de relações, Tabelas) mais o Comparador. "Conferência do texto" já foi para o caderno (W04, aprovado). "Entrevistas e pedidos" vira "Pedidos e prazos", que o canvas já põe na barra lateral, com o contador "1 vence".
- **Hipóteses (W05):** três colunas fixas (sustenta, contraria, falta), cada uma com sinal, traço e texto; toda evidência abre o original; "falta" vira pergunta ou pedido; formulário "Nova hipótese" no pé; à direita, "Como ler" com a frase de W05 de que a contagem não é placar.
- **Tabelas (W06):** cada célula tem fonte ou "○ a conferir"; a célula corrigida leva o ícone de lápis e abre à direita o valor lido pelo OCR riscado, o corrigido e a justificativa obrigatória; cálculo com a conta visível. No celular, a tabela rola dentro da caixa (W06) e a célula selecionada vem abaixo.
- **Comparador (W07):** dois lados escolhidos em seletores; trecho retirado com "−" e risco, trecho novo com "+" e fundo; a conta da diferença por extenso; o resultado vira achado "a conferir". No celular, os lados viram seletores empilhados e as diferenças, lista (W07, regra 7).
- **Pedidos e prazos:** as perguntas preparadas com tipo (pedido via LAI, entrevista, pedido de informação), destinatário, prazo, situação e as evidências que as motivam; à direita, as lacunas que pedem contato (vindas das hipóteses, da linha do tempo e da conferência) e "Preparar pergunta". Os campos são os da Mesa de hoje (`interface/redacao.js`).
- **Mapa e linha do tempo no celular:** o mapa abre como lista de ligações (a leitura acessível que o canvas já prevê em "Ver como lista"); a linha do tempo vira coluna única, com os filtros em pílulas.
- **Celular dos quadros:** as abas viram pílulas que rolam para o lado, e o botão do topo volta à apuração no lugar do menu (P11.7).

## Decisões

Todas respondidas pelo dono em 21/11/2026: 1 a 6 como desenhadas; 7 aprovada com uma condição: o nome do item e a pílula "1 vence" não podem quebrar linha. Medido com as fontes da Mesa, o item ativo precisava de 188 px e a barra de 232 px só tinha 175. O dono escolheu alargar a barra para 256 px em todas as telas, uma mudança no canvas que ele autorizou (`../../mudancas-de-token.md`, item 7). A outra saída, só o número na pílula, foi descartada. As pranchas foram regeneradas com a barra nova.

1. **Cinco abas** (as quatro do canvas mais o Comparador), com "Conferência do texto" no caderno e "Entrevistas e pedidos" como a área "Pedidos e prazos"?
2. **Hipóteses** como desenhado?
3. **Tabelas** como desenhado, com a célula selecionada no painel à direita?
4. **Comparador** como desenhado, como quinta aba dos quadros?
5. **Pedidos e prazos** como desenhado? Não há wireframe: o desenho parte do que a Mesa já faz.
6. **Mapa no celular como lista de ligações** e **linha do tempo em coluna única**?
7. **Contador "1 vence" no item ativo da barra:** pílula clara com texto de aviso (6,59:1 no claro, 9,19:1 no escuro), porque o texto de aviso sobre o verde do item ativo não se lê.
