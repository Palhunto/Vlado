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

Desde o d03a85c (barra lateral com a estrutura do canvas, Onda 3, fase 3) a barra não tem mais Cadastrar documentos,
Apurações e lixeira nem Nova apuração; os botões `#ver-cadastro`, `#ver-gerenciar` e `#mesa-nova` ficam ocultos no DOM
e o Playwright não clica em elemento oculto. Os roteiros chegam a essas telas por `qa_navegacao.cjs`:

| Função | Caminho visível |
|---|---|
| `irParaCadastro(pagina)` | Documentos > aba "Cadastro e recibo" |
| `irParaGerenciar(pagina)` | Visão geral > "Trocar de apuração" (some enquanto não há apuração) |
| `irParaNovaApuracao(pagina)` | Visão geral > "Nova apuração" |

Quando a barra mudar de novo, só `qa_navegacao.cjs` deve mudar. Os helpers supõem viewport de desktop (no celular a
barra é uma gaveta).

## Dívida da QA: cinco roteiros obsoletos (registrada em 22/11/2026)

`qa_homologacao`, `qa_interface_achados`, `qa_lixeira`, `qa_polimento` e `qa_visual` **falham desde antes da Onda 3**:
conferido em 22/11/2026 no `b3b6935` (o `main` da lapidação), no `685c62b` e na ponta da fase 3 do Frontend, com o
mesmo defeito, ou seja, não é consequência da barra lateral nem de nenhuma mudança da Onda 3.

Motivo: foram escritos antes do **contexto persistente do cabeçalho** (`#contexto-caso`, a apuração escolhida no topo
da Mesa). Hoje as telas não mostram mais o seletor próprio da apuração, e os roteiros ainda o esperam:

- `qa_lixeira` e `qa_interface_achados` esperam `#gerenciar-caso` e `#caso` visíveis (`selectOption` esgota o tempo:
  "element is not visible");
- `qa_polimento` espera que, depois de cadastrar, o seletor do cabeçalho passe para a apuração nova
  (`#contexto-caso option:checked`), mas ele continua em "Escolha uma apuração";
- `qa_homologacao` quebra na afirmação da linha ~174 (o 1 esperado volta como `[]`) depois de passar as verificações de
  acesso;
- `qa_visual` precisa de `NODE_PATH` e, com ele, falha ao clicar (mesma família).

O ajuste de caminho da barra (acima) já foi aplicado neles, mas **não os deixa verdes**. Reescrevê-los é trabalho à
parte: trocar os seletores pelo seletor do cabeçalho e pelas telas novas. **Fica para o fim da Onda 3**, quando o
Frontend estabilizar o cabeçalho e as telas novas; reescrever antes seria refazer o trabalho a cada fase. Até lá,
não use esses cinco como prova de nada (nem verde nem vermelho).

Situação conhecida dos demais:

- `qa_extracao_interface` roda e passa em `685c62b`; é o único dos seis que serve de prova hoje. Na ponta da fase 3
  ele falha por uma regressão de produto real (o aviso de extração de PDF não é reverificado ao abrir Cadastro pelo
  caminho novo); foi comunicada ao Frontend.
- Os demais `qa_*` (`qa_apuracao`, `qa_caderno`, `qa_codex`, `qa_desktop`, `qa_mobile` e outros) **não foram
  verificados** nesta rodada; não afirmamos que passam.
