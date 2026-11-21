# Linha de base da regressão visual

Capturas da Mesa **como estava antes de qualquer mudança visual da Onda 3** (parte A do plano). Servem de
rede de segurança: quem muda uma tela compara, vê o que mudou e, sendo mudança pretendida, refaz a linha de base
no mesmo commit.

Tudo aqui é **sintético**: casos `vila_serena_sintetico` e `campo_verde_aditivo_sintetico` (de
`scripts/dados_sinteticos.py`), contas `demo.*`. Nenhum caso, rodada ou documento real entra, e nenhuma chamada à API
é feita (o servidor sobe sem chave e a regressão visual não envia pergunta).

## Como usar

Uma vez, num ambiente à parte (a imagem da Mesa não leva navegador nem Pillow):

```
python -m venv ~/.cache/vlado-visual-venv        # fora do repositório (.gitignore só cobre .venv/)
~/.cache/vlado-visual-venv/Scripts/pip install -r testes/requirements-teste.txt      # Linux/macOS: bin/pip
~/.cache/vlado-visual-venv/Scripts/python -m playwright install chromium   # só se o Chromium do Playwright ainda não existir
```

Depois, com o Python desse ambiente (o servidor e o semeador sobem sozinhos no Python do projeto: o `.venv`, ou
`--python-servidor`, ou `VLADO_PYTHON_SERVIDOR`):

```
python testes/regressao_visual.py comparar                  # 114 capturas, cerca de 5 min; relatório em tmp/regressao_visual/relatorio.html
python testes/regressao_visual.py gerar                     # refaz a linha de base inteira
python testes/regressao_visual.py comparar --telas codex --larguras 375,1440 --temas escuro   # recorte
```

`comparar` sai com código 1 se alguma captura reprovar, 2 se não houver linha de base para a plataforma. O relatório
mostra referência, atual e diferença (pixels diferentes em vermelho, caixas ao redor das regiões) das reprovadas, e
`relatorio.json` traz os números de todas.

## O que é capturado

Telas: `inicio`, `documentos`, `cadastro`, `codex`, `achados`, `apuracao`, `diligencias`, `quadros`, `gerenciar`,
`caderno`, `configuracoes` (por `/?area=<área>&caso=vila_serena_sintetico`, servidor `local`) e `entrar` (servidor
`local-contas`). Larguras 375, 768, 1024 e 1440 px; temas claro e escuro. Captura de página inteira, então a altura
varia por tela. Nome: `<tela>__<largura>__<tema>.png`.

**Foco de teclado** (`foco_*`): o capturador aperta Tab até o alvo ficar focado com `:focus-visible` e captura com o
anel visível; se o foco não chegar ao alvo, a rodada falha. Alvos: campo de login e botão Entrar na tela de entrar
(375 e 1440 px); botão "Enviar e cadastrar agora", campo "Natureza dos documentos" e, só em 1440 px, o item
"Cadastrar arquivos" da barra lateral, na Mesa (área `cadastro`). Nos dois temas: 18 imagens. Mudar a cor, a
espessura ou o `outline-offset` do foco reprova (verificado: cor do foco no tema claro, 9 de 9 reprovadas; offset
efetivo de 4 px para 2 px, 5 de 5). Nas demais capturas o foco é retirado de propósito, para não aparecer anel.

Hoje o conteúdo é o do estado inicial dos dois casos semeados: sem rodada, sem conversa. As áreas que dependem de
rodada (`achados`, `codex`, `quadros`, `diligencias`) aparecem com o estado vazio; quando houver rodada sintética
semeável, acrescentá-la à semeadura (`regressao_visual_semear.py`) e refazer a linha de base.

## O que fica de fora

Hover, botão pressionado (`:active`), gaveta ou menu aberto (em 375 px a barra lateral fica fechada), diálogos e
`confirm()`, tooltips, listas abertas de `<select>`, estados de validação e de erro de formulário, envio em
andamento, rolagem interna de contêineres, foco em outros elementos além dos cinco alvos acima, `forced-colors`
(alto contraste), impressão, idioma inglês, teclado virtual e orientação do aparelho. Navegadores além do Chromium e
aparelhos reais são Manual Follow-Up (Onda 5). Estados que pedem dados de uma rodada ficam por conta da semeadura.

## Determinismo

Relógio do navegador fixo (15/01/2026 12:00 UTC), fuso UTC, `pt-BR`, movimento reduzido, animações concluídas pelo
Playwright, cursor de texto oculto, barras de rolagem ocultas, fontes só as da Mesa (aguardadas por
`document.fonts.ready`), suavização sem subpixel, perfil de cor sRGB, interface do navegador em `en-US`
(o texto nativo "Choose Files" não depende do idioma do sistema), nenhum pedido a endereço que não seja o do servidor
local (abortado, e a rodada reprova). A CSP da Mesa (`style-src 'self'`) impede injetar CSS; por isso nada é
injetado.

O ambiente do semeador e dos servidores é fixado pelo harness: sem `ANTHROPIC_API_KEY` e `OPENAI_API_KEY` (a Mesa
mostra "chave ausente" e nunca há como chamar um provedor) e com `VLADO_OCR=0` (a linha de base não depende de haver
Tesseract na máquina: a medição digitalizada fica "sem texto extraível" em qualquer ambiente).

A Mesa grava com a hora real do servidor. Os textos de data e hora (`21/11/2026`, `21/11/2026, 17:02:11`,
`Salvo às 17:02`, ISO 8601) são trocados por `‹data›` na DOM antes da captura (lista `MASCARAS` em
`regressao_visual.py`). **Nada além disso é mascarado.** Cada captura só vale depois de duas leituras seguidas
idênticas; se não estabilizar, a rodada inteira falha e nada é gravado.

Rodadas independentes (semeadura nova a cada uma) deram 82 e 83 de 96 imagens idênticas; as demais, ruído de borda
arredondada: no máximo 2 níveis num canal, no máximo 26 pixels por imagem.

## Tolerância

Um pixel conta como diferente se algum canal variar mais de **4** (de 255); a captura é aceita com até **8** pixels
assim. Tamanho de imagem diferente, captura ausente e captura sem referência reprovam sempre. A tolerância é o
dobro do ruído medido e fica nas constantes de `regressao_visual_comparador.py`. Verificado de fato na Mesa
(com a alteração desfeita depois): uma vírgula num texto de `desktop.js` reprovou com 1740 pixels diferentes, e o
fundo do tema claro de `#f6f5f0` para `#f6f5f6` reprovou com 45% da imagem; mover um elemento em 1 px e mudar uma
palavra estão cobertos por `test_regressao_visual.py`. Uma mudança de cor de até 4 níveis num canal passa, por ser
invisível e indistinguível do ruído.

## Plataforma e navegador

A renderização de texto difere entre Windows, Linux e macOS, e entre versões do Chromium. A linha de base fica em
`referencias_visuais/<plataforma>/` (hoje só `windows/`, Chromium 159 pelo Playwright 1.65.2) e só se compara na
mesma plataforma. `manifesto.json` registra navegador, versões, argumentos, máscaras, tolerância e o SHA-256 de cada
imagem; `comparar` avisa quando o navegador mudou. Para ter a linha de Linux, rodar `gerar` numa máquina Linux e
versionar a pasta `linux/`.

## Fora do CI

A comparação é **manual**, antes de integrar mudança visual, e não entra na suíte lenta do CI: o CI roda em Linux, a
linha de base é do Windows, e as duas não batem pixel a pixel. O que roda no CI (suíte rápida) é
`test_regressao_visual.py`: o comparador reprova mudança pequena, a linha de base confere com o manifesto
(imagem apagada ou trocada à mão reprova) e nenhuma imagem é uma página em branco.

## Tamanho

114 imagens PNG sem perda, 12,2 MB no total (as mais pesadas são as telas de 1440 px). Cada
`gerar` completo acrescenta esse tanto ao histórico do git: refazer a linha de base só no portão de cada tela ou fase,
não a cada commit, e usar recorte (`--telas`, `--larguras`, `--temas`) para trocar só o que mudou.

## Achados da primeira captura (estado atual da Mesa, nada corrigido aqui)

- `inicio` estoura na horizontal: página de 890 px a 768 px e de 1061 px a 1024 px (rolagem horizontal).
- A área `apuracao` registra no console um bloqueio da CSP (`style-src 'self'`): estilo inline aplicado por script.
  Fica no manifesto (`erros_do_navegador`); `comparar` avisa se aparecer erro novo.
