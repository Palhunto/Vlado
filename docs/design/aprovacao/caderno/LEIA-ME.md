# Caderno: o que o dono decidiu

**Proposta: derivado, aprovado pelo dono em 21/11/2026** (commit `adce9fc`; os pontos abertos, P14b, também aprovados em 21/11/2026). Especificação em [`componentes.md`](../../componentes.md#caderno). Aprovadas como desenhadas: a tela em três colunas do W04 com a barra lateral do canvas (P14.1) e, no celular, o seletor de nota no topo e o painel no pé (P14.5). Segue o wireframe W04 ("Caderno e conferência do texto") na linguagem do canvas. Não há tela final do caderno no canvas.

| Arquivo | O que é |
|---|---|
| `atual-{claro,escuro}-{1440,390}.png` | a Mesa de hoje, área Caderno, com a nota que o semeador sintético cria |
| `proposta-{claro,escuro}-{1440,390}.png` | a proposta, com o conteúdo do W04 desenhado na prancha |
| `comparativo-{claro,escuro}-{1440,390}.png` | as duas lado a lado |

**Correção de 21/11/2026, depois da aprovação:** as frases do modo "Conferir afirmações" saíam em verde. A cor vinha de uma regra de link genérica das pranchas (`.pr a:not(.bt)`), não de decisão de desenho. Agora estão na cor do texto (`--theme-text`), como pede a especificação: o sinal fica no sublinhado e no rótulo ao lado. O layout aprovado não muda. Se o dono preferir o verde, a correção é desfeita.

## O que muda

- Uma tela só para escrever e conferir: notas à esquerda, texto no centro, afirmação selecionada à direita (W04). Somem a barra de etapas (Documentos, Pergunta, Conferência, Caderno) e as abas "Notas e redação" e "Trechos com fonte e contribuições".
- No modo "Conferir afirmações", cada frase leva traço e texto: sublinhado contínuo verde e "✓ com fonte"; tracejado ocre e "! exagero"; pontilhado e "○ sem fonte" (W04: "Quatro sinais, sempre com traço e texto").
- "Salvo às" sobe para o cabeçalho da apuração, como no canvas.
- No celular: a nota se escolhe num seletor no topo, e a afirmação selecionada abre num painel no pé da tela, com as três ações.

## Decisões

Respondidas: 1 e 5, como desenhadas; 2, 3 e 4 respondidas pelas decisões 6 a 8 abaixo.

1. **Aprova a tela em três colunas do W04**, com a barra lateral do canvas?
2. **"Trechos com fonte e contribuições"** não aparece no W04. Os trechos passam a entrar só por "Ligar outra evidência", ou a aba continua em outro lugar?
3. **Modo "Escrever"** (o editor com formatação de hoje) não está desenhado. Desenho em seguida, no mesmo padrão?
4. **Quarto sinal, "revisada".** O W04 o lista, mas o exemplo não o mostra. Proposta: "✓ revisada por você" em verde, ao lado do sinal da fonte. Desenho?
5. **Celular:** seletor de nota no topo e afirmação selecionada num painel no pé. Concorda?

## Pontos abertos, aprovados (P14b)

**Derivado, aprovado pelo dono em 21/11/2026** (faixa verde; decisões 6 a 8, como desenhadas). Pranchas: `proposta-trechos-{claro,escuro}-{1440,390}.png` e `proposta-escrever-{claro,escuro}-{1440,390}.png`, já com as decisões de 21/11/2026.

### Onde ficam "Trechos com fonte e contribuições" (P14.2)

Proposta: **no próprio caderno, como segunda lista da coluna da esquerda**, num seletor "Notas | Trechos (n)". Cada trecho mostra o tipo (trecho, achado do jornalista, anotação), a citação, a fonte e a autoria, com caixa de seleção (até 20). As ações ficam no pé da coluna: "Inserir no texto", "Cruzar", "Perguntar" e "Registrar trecho com fonte", que abre o formulário que já existe (documento, página, trecho e autoria).

Por que aqui:

1. **É material do jornalista, como as notas.** A Mesa de hoje descreve a aba como "trechos, achados e cruzamentos de autoria humana, separados dos resultados da IA". O caderno é o lugar do que é humano; a conferência dos achados é o lugar do que vem da IA.
2. **Alimenta a conferência do W04.** "Ligar outra evidência", no painel da afirmação selecionada, escolhe entre os achados conferidos e estes trechos. Com a lista na mesma tela, ligar e inserir não pedem troca de área.
3. **Não cria área nova** na barra lateral do canvas nem aba nova nos quadros.
4. **No celular** o mesmo seletor fica no topo da página, como o seletor de nota já aprovado (P14.5).

Alternativas descartadas: uma aba própria nos quadros (mistura material bruto com quadros que organizam evidência conferida) e uma área na barra lateral (o canvas tem sete áreas fechadas e a P11.6 manteve a barra como desenhada).

### Modo "Escrever" (P14.3)

O centro vira o editor de hoje, no padrão do canvas: barra de formatação (texto normal, negrito, itálico, lista, tarefas, "+ Trecho com fonte", "Mais"), título serifa 22 e texto serifa 18 com as fontes em pílula ("Fonte 1"); "As notas são salvas enquanto você escreve". À direita, "Fontes da nota" com cada trecho citado e "abrir o original", e "Inserir trecho com fonte" no pé. No celular, o seletor de nota e o par "Conferir | Escrever" no topo, e o editor em largura cheia.

### Quarto sinal, "revisada" (P14.4)

Sublinhado **duplo** verde e o texto "✓ com fonte · revisada por você" ao lado da frase. No painel da afirmação selecionada: "Ana Lima marcou como revisada hoje, às 14h40", lembrando que só pessoa logada marca (W04). A legenda dos quatro sinais fica abaixo do texto. A contagem do topo passa a incluir as revisadas.

### Decisões

6. **Trechos no caderno**, como segunda lista da coluna da esquerda?
7. **Modo "Escrever"** como desenhado?
8. **Sinal "revisada"** com sublinhado duplo verde e o texto "revisada por você"?
