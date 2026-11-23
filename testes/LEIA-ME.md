# Testes de navegador (roteiros `qa_*`)

Os roteiros `qa_*.py` sobem uma Mesa com dados sintéticos (um fixture de `test_interface_pesquisa`) e chamam o
`qa_*.cjs` de mesmo nome, que dirige o Chromium pelo Playwright. **Não fazem parte da suíte rápida nem da lenta**
(`executar_suite.py` só descobre `test_*.py`): rodam à mão, um de cada vez, e não são validados pelo CI.
A regressão visual (capturas) é outra coisa: veja `referencias_visuais/LEIA-ME.md`.

## Como rodar

De dentro de `testes/`, com o Python do `.venv` (o `python` do PATH não tem as dependências):

```
PYTHONUTF8=1 ../.venv/Scripts/python.exe qa_extracao_interface.py --modulos-node ../.ferramentas/node/node_modules --saida <pasta>
```

`--modulos-node` aponta para a pasta `node_modules` com o Playwright (em `.ferramentas/`, fora do git). O
`qa_visual.py` não tem essa opção: ele lê `NODE_PATH` do ambiente. Cada roteiro abre um Chromium: rode um por vez
(máquina de 8 GB).

## Navegação pela barra lateral

Desde o d03a85c (barra lateral com a estrutura do canvas, Onda 3, fase 3) a barra não tem mais Apurações e lixeira nem
Nova apuração; os botões `#ver-gerenciar` e `#mesa-nova` ficam ocultos no DOM e o Playwright não clica em elemento
oculto. A área "Cadastrar arquivos" (`#area-cadastro`, `#cadastro-*`) saiu (R4, P16.5): uma apuração nova nasce pela
Nova apuração, e o envio de uma apuração que já existe é a área de envio da tela Documentos. Os roteiros chegam a tudo
isso por `qa_navegacao.cjs`:

| Função | Caminho visível |
|---|---|
| `irParaDocumentos(pagina)` | barra lateral > Documentos (`#area-documentos`: lista, `#documentos-zona`, `#documentos-recibo`) |
| `irParaNovaApuracao(pagina)` | Visão geral > "Nova apuração" (`#area-nova`, passo 1: `#nova-nome`, `#nova-natureza`, `nova-fontes`, `#nova-site`) |
| `criarApuracao(pagina, {nome, natureza, fontes, site})` | passo 1 preenchido e "Continuar para documentos" (passo 2, a tela Documentos, ainda sem apuração) |
| `enviarArquivos(pagina, arquivos)` | envia pela área de envio de Documentos e espera o recibo do lote; o primeiro lote da Nova apuração cria a apuração |
| `irParaGerenciar(pagina)` | Visão geral > "Trocar de apuração" (some enquanto não há apuração) |
| `dialogoConfirmar(pagina)` / `dialogoCancelar(pagina)` | o diálogo próprio de confirmação (UX-16); `page.once('dialog')` não o alcança |

Onde ficou o que o cadastro mostrava: o recibo do lote só conta (`Recibo do lote: N de M arquivos`, novos e duplicados);
identificador, SHA-256 e estado de leitura de cada documento estão na lista `#mesa-acervo-lista` (em "Detalhes técnicos" e
na coluna Leitura); a apuração aberta é `#contexto-caso`; a pesquisa (rodada, geração, consulta) é a aba "Pesquisar no
conteúdo" (`#mesa-aba-pesquisa`); o aviso do extrator e o preparo de PDFs são `#docs-pdf-*`.

Quando a barra mudar de novo, só `qa_navegacao.cjs` deve mudar. Os helpers supõem viewport de desktop (no celular a
barra é uma gaveta).

## Situação dos roteiros (atualizada em 23/11/2026)

Passam, contra `lancamento/frontend-o3`: `qa_homologacao` (15 verificações; o passo do OCR sai como PULADO sem Tesseract;
os passos de contas voltam pela Equipe e pelo Convidar), `qa_extracao_interface` (4), `qa_polimento` (6).

Também passam, depois de reescritos para o diálogo próprio (UX-16) e as telas novas: `qa_experiencia` e `qa_visual` (este com a
espera do sinal "salvo" por observador e três execuções seguidas OK). `qa_homologacao` pede uma base com a Equipe e a contas-o2.
`qa_interface_achados` já migrou o cadastro, mas ainda falha mais adiante (`#achados-revisao` escondido na área Achados): não é prova.

Os demais `qa_*` (`qa_apuracao`, `qa_caderno`, `qa_codex`, `qa_desktop`, `qa_mobile`, `qa_lixeira` e outros) **não foram
verificados** nesta rodada; não afirmamos que passam. `qa_lixeira` espera `#gerenciar-caso` visível e é anterior ao contexto
persistente do cabeçalho.
