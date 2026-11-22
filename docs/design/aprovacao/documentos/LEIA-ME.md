# Documentos: o que o dono decidiu

**Proposta: derivado, aprovado pelo dono em 21/11/2026** (P16.1 a P16.4, faixa verde). Especificação em [`componentes.md`](../../componentes.md#documentos). Segue o wireframe W02 ("Documentos e envio") na linguagem do canvas, com as decisões de 21/11/2026. Não há tela final de documentos no canvas. A mesma proposta substitui a área "Cadastrar arquivos" (ver `../cadastro/`).

| Arquivo | O que é |
|---|---|
| `atual-{claro,escuro}-{1440,390}.png` | a Mesa de hoje, área Documentos, com os casos sintéticos do semeador |
| `proposta-{claro,escuro}-{1440,390}.png` | a proposta, com o conteúdo do W02 desenhado na prancha |
| `comparativo-{claro,escuro}-{1440,390}.png` | as duas lado a lado |

## O que muda

- **Uma tela só para acervo, envio e busca** (W02, regra 1): somem as abas "Acervo", "Pesquisar" e "Cadastro e recibo", e a área "Cadastrar arquivos" sai da barra lateral.
- **Busca no texto no topo**, que funciona antes da primeira pergunta à IA (regra 4).
- **Área de envio:** arrastar ou escolher no computador, com os formatos e o limite por arquivo. No celular, vira o botão "Escolher arquivos".
- **Envio por arquivo** (regras 2 e 3, UX-05): cada arquivo tem a própria barra e o próprio resultado; a falha de um (planilha com macro) não derruba os outros e diz o que houve e o que fazer (regra 6); o envio segue em segundo plano.
- **Recibo do lote** continua, numa linha do cartão de envio, conferido antes da primeira pergunta (regra 8).
- **Três estados de leitura, com sinal e texto** (regra 5): "✓ Texto do próprio arquivo", "◐ Lida por OCR: confira números" (ícone `sinal-parcial`, porque o caractere ◐ não existe nas fontes da Mesa) e "○ Imagem sem leitura", com "Ler com OCR".
- **Hash, identificador e versão** saem da lista e ficam em "Detalhes técnicos" de cada documento (regra 7).

## Decisões

Todas respondidas pelo dono em 21/11/2026, como desenhadas. A barra lateral das pranchas tem 256 px (P15.7).

1. **Uma tela só** para acervo, envio e busca, sem a área "Cadastrar arquivos" na barra lateral?
2. **Envio por arquivo** como desenhado, com o recibo do lote numa linha do cartão de envio?
3. **Lista de documentos** em tabela no desktop e em cartões no celular?
4. **Contador do item ativo** da barra lateral ("Documentos 12"): na página atual, o número vira pílula clara, porque o texto secundário sobre o verde do item ativo não se lê. Mesma regra da pílula de prazo dos quadros.
