---
type: reference
title: Referência visual exportada do canvas "Vlado — Mesa ideal"
created: 2026-11-21
tags: [design, referencia, contrato-visual]
related: ['[[design-system]]', '[[componentes]]', '[[mudancas-de-token]]']
---

# Referência visual exportada do canvas

Esta pasta cumpre a regra 4 do contrato visual (`PLANO_LANCAMENTO.md`, seção "Contrato visual"): o canvas "Vlado — Mesa ideal" exportado em imagens, uma por tela, versionado junto com o código. A partir daqui, o portão de cada tela (regra 5) compara a captura do Frontend com a imagem desta pasta.

## Procedência

| Item | Valor |
|---|---|
| Canvas | "Vlado — Mesa ideal", https://claude.ai/artifact/MufD79bVG1NxFTi8Wsqzf7 (privado do dono) |
| Versão lida | `1795290461-0281`, lida em 21/11/2026 |
| Páginas | "Telas finais" (7 pranchetas) e "Wireframes" (11 pranchetas) |
| Fonte de cada prancheta | `canvas/`, cópia byte a byte dos arquivos publicados (o SHA-256 confere com a listagem do canvas) |

As pranchetas são HTML estático (`renderVals()` devolve `{}` em todas, sem laço nem condição). Por isso a renderização local é fiel: o mesmo HTML, as mesmas fontes, o mesmo tamanho de moldura.

## Como foi exportado

1. `ferramentas/renderizar_canvas.cjs` abre cada prancheta no Chromium do Playwright do projeto (`.ferramentas/node/node_modules`), na largura e altura declaradas em `$preview`, com escala 1 (1 px da imagem = 1 px de CSS, para medir direto na imagem).
2. As fontes são as da própria Mesa (`interface/fonts/SourceSerif4-Roman.ttf` e `SourceSans3-Upright.otf`), no lugar do `<link>` para o Google Fonts que o canvas usa. Todo pedido de rede fora de `file:` é bloqueado.
3. `ferramentas/medir_transbordo.cjs` mede o que passa da moldura. Só o "Entrar" passa (ver abaixo); dele há também a página inteira.
4. As imagens foram regravadas sem metadados (só os pixels) e com compressão PNG sem perda.

Conferência: a imagem `telas/03-design-system-revisado-1440.png` foi posta ao lado da captura que o dono fez no próprio canvas ("Design system revisado@2x.png", 2880 × 2000 px, não versionada). Estrutura, texto, cor e quebras de linha coincidem; a única diferença é a escala (1× aqui, 2× lá).

Para refazer depois de uma mudança aprovada no canvas: ler os arquivos `project/*` do canvas com a ferramenta Artifact, copiar para `canvas/` e rodar:

```
NODE_PATH=.ferramentas/node/node_modules node docs/design/referencia/ferramentas/renderizar_canvas.cjs <pasta com canvas.json e .dc.html> <saída> interface/fonts
NODE_PATH=.ferramentas/node/node_modules node docs/design/referencia/ferramentas/medir_transbordo.cjs <mesma pasta> <saída> interface/fonts
```

## Telas finais (aparência)

| Imagem | Prancheta | Largura × altura | Tema |
|---|---|---|---|
| `telas/01-conferir-achado-1440.png` | Conferir achado (`Main.dc.html`) | 1440 × 900 | claro |
| `telas/02-visao-geral-1440.png` | Visão geral (`Inicio.dc.html`) | 1440 × 900 | claro |
| `telas/03-design-system-revisado-1440.png` | Design system revisado (`Tokens.dc.html`) | 1440 × 1000 | claro, com amostras do escuro |
| `telas/04-pergunta-celular-escuro-390.png` | Pergunta no celular (`Celular.dc.html`) | 390 × 844 | escuro |
| `telas/05-entrar-390.png` | Entrar (`Entrar.dc.html`), moldura | 390 × 844 | claro |
| `telas/05-entrar-390-pagina-inteira.png` | Entrar, conteúdo inteiro | 390 × 1018 | claro |
| `telas/06-mapa-de-relacoes-1440.png` | Mapa de relações (`Mapa.dc.html`) | 1440 × 900 | claro |
| `telas/07-linha-do-tempo-1440.png` | Linha do tempo (`Tempo.dc.html`) | 1440 × 900 | claro |

## Wireframes (estrutura e regras)

Os wireframes são em tons de cinza e medem 1200 × 760 px. Valem pela estrutura e pelas regras numeradas, não pela cor (regra 3 do contrato). As regras estão transcritas, palavra por palavra, em [`../componentes.md`](../componentes.md#regras-dos-wireframes).

| Imagem | Wireframe |
|---|---|
| `wireframes/W01-nova-apuracao-1200.png` | W01 Nova apuração (vários sites) |
| `wireframes/W02-documentos-e-envio-1200.png` | W02 Documentos e envio |
| `wireframes/W03-perguntar-1200.png` | W03 Perguntar |
| `wireframes/W04-caderno-e-conferencia-1200.png` | W04 Caderno e conferência do texto |
| `wireframes/W05-hipoteses-1200.png` | W05 Hipóteses |
| `wireframes/W06-tabelas-conferiveis-1200.png` | W06 Tabelas conferíveis |
| `wireframes/W07-comparador-1200.png` | W07 Comparador |
| `wireframes/W08-minha-conta-1200.png` | W08 Minha conta |
| `wireframes/W09-equipe-e-convites-1200.png` | W09 Equipe e convites |
| `wireframes/W10-aceitar-convite-1200.png` | W10 Aceitar convite |
| `wireframes/W11-estados-1200.png` | W11 Estados: vazio, ocupado, erro |

## O que o canvas não tem, e por isso esta pasta não tem

- **Nenhuma tela existe nas duas larguras.** As telas de desktop estão só em 1440 px; as de celular, só em 390 px (não 375). O plano pede "uma imagem por tela, em 375 e 1440 px" (regra 4 do contrato visual), e a instrução desta fase pediu as duas larguras quando a tela tivesse as duas versões; nenhuma tem. As versões que faltam (celular das telas de desktop, desktop do "Entrar") estão na lista do que o Design ainda desenha.
- **Tema escuro em desktop.** Só a pergunta no celular está no escuro; as demais telas finais estão no claro. O escuro das outras telas segue os tokens (`mudancas-de-token.md`), sem imagem de referência.
- **Telas sem desenho:** pedidos e prazos de LAI, fontes e capturas de site dentro da apuração, lixeira, configuração da organização, página pública, diálogo de confirmação (W11, regra 8) e as versões de celular. São a fase seguinte do Design.

## Defeitos que o próprio canvas traz

A renderização mostra texto que não cabe na caixa desenhada. Nenhum deles muda a especificação de cor ou de medida; todos estão em [`../componentes.md`](../componentes.md#perguntas-para-o-dono) como pergunta ou ressalva.

| Tela | O que acontece | Onde |
|---|---|---|
| Entrar | O conteúdo vai até 1018 px numa moldura de 844 px: o botão "Minha redação quer participar", o aviso de documentos públicos e o rodapé ficam fora da moldura. Num celular real a página rola, então a imagem da página inteira é a referência de conteúdo. | `05-entrar-390-pagina-inteira.png` |
| Mapa de relações | "Construtora Alfa Ltda." e "Pavimenta Sul S.A." quebram em duas linhas e o subtítulo ("Empresa · 9 documentos") passa da caixa de 72 px de altura. | `06-mapa-de-relacoes-1440.png` |
| Conferir achado e Visão geral | Na barra lateral, "Repórter · Redação Serena" quebra em duas linhas dentro do item de 44 px de altura, e "Cota do mês / R$ 18,40 de R$ 50" quebra no cartão de 200 px. | `01-…`, `02-…` |
| W11 | Os botões "Enviar outro", "Manter só o original" e "Retomar de onde parou" quebram em duas linhas dentro de 40 px. É wireframe: vale a estrutura, não a medida. | `W11-estados-1200.png` |
