---
type: reference
title: Contrato de evidência
created: 2026-11-19
tags: [contrato, evidencias, equipe]
related: ['[[PLANO_EQUIPE]]']
---

# Contrato de evidência

Este é o contrato do núcleo de evidências (Core) da branch `lapidacao/core-evidencias`. Ele vale para todos os agentes que consomem `scripts/evidencias.py`, `scripts/hipoteses.py`, `scripts/linha_tempo.py`, `scripts/comparador.py` e `scripts/mapa_relacoes.py`, e descreve na seção 5.7 o quadro de tabelas de apuração (`scripts/tabelas_apuracao.py`), montado sobre ele. Os exemplos JSON abaixo foram gerados pela demonstração `scripts/demo_evidencias.py`, sobre dados sintéticos numa pasta temporária, e encurtados (`…`) para leitura. Hashes e IDs são ilustrativos.

`ESQUEMA = 1` (`evidencias.ESQUEMA`). Todo evento salvo e toda evidência resolvida levam `esquema: 1`.

## 1. Princípios

- **Uma evidência nunca é texto livre.** Ela é uma *referência* a uma fonte já registrada no caso: uma evidência (`E-ID`) de um conjunto de achados publicado, ou a fonte de um registro humano do caderno. O Core só a aceita depois de resolvê-la contra o original, com o hash conferido.
- **O caso faz parte da identidade.** IDs de documento (`D001`…) só são únicos dentro do caso. Por isso, a referência sempre leva `caso_id`, e a rodada e a revisão, quando houver.
- **Um vínculo é a referência mais o julgamento.** Ele liga a referência a um item (hipótese, evento, entidade ou relação) e declara o papel, a avaliação de suporte, o tipo de afirmação (`natureza`) e a justificativa.
- **Só acréscimo.** Os quadros gravam eventos encadeados por hash (`anterior_sha256`) em `casos/<caso>/quadros/<colecao>/<id>/NNNNNNNN_<requisicao_id>.json`. A gravação é atômica, com pasta de preparação e `comum.escrever_json(exclusivo=True)`. Nada é sobrescrito, e apagar um registro significa retirá-lo com motivo.
- **Sem modelo e sem rede.** Nenhuma função do Core chama modelo ou rede, nem lê fora de `casos/<caso>` e `execucoes/<caso>`.
- **O quadro não julga.** A situação das hipóteses e as decisões sobre homônimos são declaradas por pessoas. Os quadros só organizam, conferem e apontam lacunas. Nenhum quadro funde entidades nem usa linguagem de fraude, culpa ou causalidade.

## 2. Referência

### 2.1 Referência `ia` (evidência dos achados publicados)

```json
{"tipo": "ia", "caso_id": "alpha", "rodada": "R001", "revisao": "r2",
 "registros_sha256": "3fa9e77e…c50f183", "evidencia_id": "E001"}
```

| Campo | Forma | Significado |
|---|---|---|
| `tipo` | `"ia"` | Origem da referência. |
| `caso_id` | `lixeira.ID_CASO` (`[a-z0-9][a-z0-9_-]{0,63}`) | Caso da evidência; precisa ser igual ao caso ativo. |
| `rodada` | `lixeira.ID_RODADA` (`R[0-9]{3,6}`) | Rodada congelada. |
| `revisao` | `indice_sqlite.ID_GERACAO` | Revisão/geração publicada dos achados. |
| `registros_sha256` | 64 hex | Hash do conjunto de achados da revisão (manifesto). |
| `evidencia_id` | padrão `id` de `modelos/ACHADOS.schema.json` | E-ID dentro da revisão. |

### 2.2 Referência `humana` (fonte de um registro do caderno)

```json
{"tipo": "humana", "caso_id": "alpha", "registro_id": "N81f54065…", "sha256": "418fbf33…", "fonte": 0}
```

| Campo | Forma | Significado |
|---|---|---|
| `tipo` | `"humana"` | Origem da referência. |
| `caso_id` | `ID_CASO` | Caso do registro. |
| `registro_id` | `caderno.ID` (`N[a-f0-9]{32}`) | Registro do caderno. |
| `sha256` | 64 hex | Hash da versão do registro que foi vinculada. |
| `fonte` | inteiro `0..999` | Índice da fonte dentro do registro. |

O conjunto de campos é fechado (`evidencias.CAMPOS_REF`): campo a mais ou a menos é recusado. `evidencias.referencia(ref)` valida só a forma e devolve uma cópia com as chaves ordenadas. `evidencias.chave(ref)` dá o hash canônico da referência.

## 3. Vínculo

### 3.1 Forma de entrada (o que um cliente envia)

```json
{"referencia": { … }, "papel": "suporte", "suporte": "sustentado",
 "natureza": "declaracao_documental", "justificativa": "Por que esta passagem sustenta o item."}
```

`referencia`, `papel` e `justificativa` (até 2000 caracteres) são obrigatórios. `suporte` tem o padrão `nao_revisado`, e `natureza` tem o padrão `pendencia`.

### 3.2 Forma salva (o que os quadros devolvem e aceitam de volta)

```json
{"referencia": {"caso_id": "alpha", "evidencia_id": "E001", "registros_sha256": "3fa9…", "revisao": "r2",
                "rodada": "R001", "tipo": "ia"},
 "papel": "suporte", "suporte": "sustentado", "natureza": "declaracao_documental",
 "justificativa": "…", "documento_id": "D001", "original_sha256": "9603b236…",
 "localizador": {"tipo": "linhas", "pagina_pdf": null, "linha_inicio": 1, "linha_fim": 1,
                 "descricao": "", "legivel": "D001 · linha 1"}}
```

`documento_id`, `original_sha256` e `localizador` são preenchidos pelo Core na resolução; o cliente não os informa. Na atualização, a forma salva pode ser reenviada como está. O Core a resolve de novo e a recusa se o documento ou o original mudaram desde o vínculo.

### 3.3 Valores

| Campo | Valores | Origem |
|---|---|---|
| `papel` | `suporte`, `contradicao`, `contexto` | `evidencias.PAPEIS` (lido do esquema dos achados) |
| `suporte` | `nao_revisado`, `sustentado`, `parcial`, `nao_sustentado`, `ilegivel` | `registros_achados.SUPORTES` |
| `natureza` | `declaracao_documental`, `alegacao_atribuida`, `inferencia`, `pendencia` | `registros_achados.NATUREZAS` |
| `localizador.tipo` | `linhas`, `pagina`, `regiao`, `celula`, `descrito` | `evidencias.TIPOS_LOCALIZADOR` |

O tipo de afirmação (`natureza`) segue o `AGENTS.md`:

- `declaracao_documental`: o próprio documento declara;
- `alegacao_atribuida`: o documento atribui a afirmação a alguém;
- `inferencia`: conclusão de quem vincula, a partir da passagem;
- `pendencia`: ainda não classificado ou sem suporte.

Só as duas primeiras (`evidencias.NATUREZAS_DOCUMENTAIS`) fundamentam uma situação declarada.

### 3.4 Regras do vínculo

- `papel = contexto` exige `suporte = nao_revisado`, porque contexto não recebe avaliação de suporte.
- `natureza = pendencia` nunca pode ter `suporte = sustentado`.
- A mesma referência não pode aparecer duas vezes com o mesmo papel no mesmo item. A mesma passagem (mesmo documento, original, localizador e trecho), vinda de outra revisão ou de outro registro, também não pode se repetir com o mesmo papel.
- Um item aceita no máximo 100 vínculos (`MAXIMO_VINCULOS`).
- A identidade de um vínculo dentro de um item é `(chave(referencia), papel)` (`evidencias.identidade`). Campos que apontam para uma evidência do item por índice seguem essa identidade quando a lista muda (`realocar_fontes`). São eles: `datas[].fonte`, `identificadores[].fonte` e `conferencias[].fontes`. Esses campos nunca seguem a posição na lista.

## 4. Resolução

`evidencias.resolver(root, caso, ref)` devolve a evidência normalizada:

```json
{"esquema": 1, "origem": "ia", "referencia": { … },
 "documento": {"caso_id": "alpha", "rodada": "R001", "corpus_id": "alpha_v1", "origem_id": null,
               "documento_id": "D001", "original_sha256": "9603b236…", "nome": "texto.txt"},
 "localizador": {"tipo": "linhas", "pagina_pdf": null, "linha_inicio": 1, "linha_fim": 1,
                 "descricao": "", "legivel": "D001 · linha 1"},
 "trecho": "A fonte declara valor 12.", "modo": "indexada",
 "fonte_textual": {"arquivo": "entradas/…/D001_texto.txt", "sha256": "9603b236…", "tipo": "original"},
 "conferencia": "trecho_localizado_no_texto_autorizado",
 "atribuicao": "Fonte sintética", "limitacoes": "Não comprova pagamento.",
 "autor": "IA", "origem_autoria": "ia"}
```

Os campos variam conforme a origem:

| Campo | `ia` | `humana` |
|---|---|---|
| `modo` | `indexada`, `direta` ou `visual` | `null` |
| `conferencia` | `leitura_visual` ou `trecho_localizado_no_texto_autorizado` | `literal_localizado` ou `transcricao_humana` |
| `autor` | `"IA"` | autor declarado ou da conta |
| `origem_autoria` | `ia` | `humana_declarada_na_interface` ou `humana_autenticada_pela_conta_da_mesa` |
| `documento.rodada` | rodada da referência | rodada de origem da fonte, que pode ser `null` |
| `documento.origem_id` | `null` | origem do caderno |
| `fonte_textual` | arquivo e hash do texto autorizado, ou `null` | sempre `null` |

### Regras de resolução

Toda recusa é um `ValueError`, sem caminho absoluto na mensagem. `resolver` recusa nestes casos:

1. **Outro caso:** `ref.caso_id` diferente do caso ativo.
2. **Rodada na lixeira:**
   - para `ia`, a rodada da referência está na lixeira (`lixeira.conferir_disponivel`);
   - para `humana`, a rodada de origem da fonte está na lixeira. Uma fonte humana sem rodada continua resolvendo, e a referência volta a resolver quando a rodada é restaurada.
3. **Revisão com outra identidade:** `registros_sha256` diferente do manifesto da revisão.
4. **Evidência fora da revisão:** o E-ID não existe nesta revisão, caso e rodada.
5. **Hash divergente:**
   - para `ia`, o original ou o texto autorizado não confere (`registros_achados.conferir_evidencia`);
   - para `humana`, o `sha256` do registro ou o hash do original não confere (`caderno._carregar` e `caderno._original`).
6. **Fonte ausente, inacessível ou malformada:** rodada, revisão, registro, índice de fonte ou original ausente, permissão negada ou estrutura inesperada.

Há ainda um efeito colateral. Resolver uma evidência `ia` de `modo: indexada` chama `indice_sqlite.ler_passagem`, que acrescenta um log em `execucoes/<caso>/<rodada>/saidas/consultas_sqlite/`. É só acréscimo, como o `AGENTS.md` pede ("preservar logs"), mas abrir um quadro deixa esse rastro.

## 5. API pública

Convenções comuns:

- `root` é a raiz do projeto (`Path`), e `caso` é um `ID_CASO`.
- Erros de validação ou de acesso saem sempre como `ValueError`, com mensagem em português pronta para o usuário.
- Para criar um item, `salvar(root, data, 'criar', conta=None)` recebe:
  - `data = {caso, requisicao_id (32 hex), autor, observacao?, …campos do quadro}`;
  - o ID do item é `prefixo + requisicao_id`.
- Para atualizar, `salvar(root, data, 'atualizar', conta=None)` exige `id` e `anterior_sha256`, igual ao `sha256` atual. Campos ausentes mantêm o estado atual (atualização parcial).
- Repetir o mesmo `requisicao_id` com o mesmo conteúdo é idempotente e devolve o registro atual. Com conteúdo diferente, é recusado.
- `conta` é a conta autenticada da Mesa. Com ela, `origem_autoria` vira `humana_autenticada_pela_conta_da_mesa`; sem ela, vira `humana_declarada_na_interface`.
- Uma trava por coleção (`.trava`) recusa salvamentos simultâneos.

Forma devolvida por `salvar` e `detalhe` (registro):

```json
{"caso": "alpha", "colecao": "hipoteses", "id": "He23121a…", "sha256": "<hash do último evento>",
 "estado": { …campos do quadro…, "origem_autoria": "humana_declarada_na_interface",
             "atualizado_em_utc": "2026-11-19T10:25:42+00:00"},
 "historico": [{"esquema": 1, "caso_id": "alpha", "colecao": "hipoteses", "id": "He23121a…", "sequencia": 1,
                "anterior_sha256": null, "operacao": "criar", "requisicao_id": "…",
                "solicitacao_sha256": "…", "autor": "…", "origem_autoria": "…", "observacao": "",
                "em_utc": "…", "estado": { … }}],
 "divergente": false}
```

`listar` devolve a lista desses registros, do mais recente para o mais antigo. Os itens com histórico divergente vêm no fim, com `divergente: true`, `estado: null` e `erro`. Um item quebrado não derruba os demais.

### 5.1 `evidencias.py`

| Função | Devolve |
|---|---|
| `referencia(ref)` | Cópia canônica da referência; só valida a forma. |
| `chave(ref)` | Hash canônico da referência. |
| `identidade(link)` | `(chave(referencia), papel)`. |
| `resolver(root, caso, ref, cache=None, *, caminho=False)` | Evidência normalizada (seção 4). Com `caminho=True`, devolve `(evidencia, Path do original conferido)`. |
| `original(root, caso, ref)` | `Path` do original, depois de conferir o hash. |
| `validar_vinculo_salvo(item)` | `None`, ou `ValueError` se a forma salva for inválida. Não abre fontes. |
| `vinculos(root, caso, items, *, minimo=0, papeis=PAPEIS, cache=None, preservar_indisponiveis=False)` | Lista de vínculos na forma salva, já resolvidos. Aceita a forma de entrada e a salva. |
| `conferir_vinculos(root, caso, items, cache=None)` | Cada vínculo salvo, acrescido de `estado` (`conferida` ou `indisponivel`), `evidencia` (ou `null`) e `erro`. Nunca falha a listagem. |
| `indice_fonte(valor, items, campo)` | Índice validado de um vínculo do item, ou `None`. |
| `realocar_fontes(antigos, novos, campo)` | Função `mover(indice)` que segue a identidade da evidência. |
| `mesclar(data, atual, padroes)` | Estado mesclado para atualização parcial. |
| `retirada(state)` | `(retirado, motivo)`. Retirar exige motivo. |
| `Colecao(nome, prefixo, campos, normalizar, validar=None, rotulo=None)` | Armazenamento comum, com `pasta`, `detalhe`, `listar` e `salvar`. |
| Constantes | `ESQUEMA`, `PAPEIS`, `ID_EVIDENCIA`, `TIPOS_LOCALIZADOR`, `CAMPOS_REF`, `CAMPOS_VINCULO`, `CAMPOS_SALVOS`, `CAMPOS_LOCALIZADOR`, `NATUREZAS_DOCUMENTAIS`, `HASH`, `MAXIMO_VINCULOS`. |

Funções privadas de outros módulos reaproveitadas pelo Core: `caderno._texto`, `_hash`, `_carregar`, `_original` e `_pasta`; `indice_sqlite._entradas` e `_adaptar`. Elas são dependência declarada do Core. Quem alterar a assinatura delas precisa avisar o Core.

### 5.2 `hipoteses.py`

Coleção `hipoteses`, prefixo `H`.

| Função | Devolve |
|---|---|
| `salvar(root, data, operacao='criar', conta=None)` | Registro. |
| `detalhe(root, caso, id)` / `listar(root, caso)` | Registro / lista de registros. |
| `quadro(root, caso)` | Quadro (abaixo). |

Campos editáveis:

| Campo | Regra |
|---|---|
| `enunciado` | Até 1000 caracteres. |
| `situacao` | Um de `SITUACOES`: `em_aberto`, `sustentada`, `contrariada`, `inconclusiva`, `descartada`. |
| `evidencias` | Vínculos. |
| `lacunas` | Até 50 itens `{descricao, diligencia_id?}`; `diligencia_id` segue `diligencias.ID`. |

A situação `sustentada` exige uma evidência de `suporte` com `suporte = sustentado` e natureza documental. A situação `contrariada` exige o mesmo com papel `contradicao`.

O quadro:

- `sustentam` e `contrariam` só trazem vínculos conferidos;
- os vínculos que não resolvem vão para `indisponiveis`;
- `condicao: "com_evidencia"` exige ao menos um suporte conferido avaliado como `sustentado` e de natureza documental (`declaracao_documental` ou `alegacao_atribuida`). Fora disso, a hipótese sai com `condicao: "pendencia"` e `natureza: "pendencia"`, mais uma lacuna automática (ajuste da [[core-revisao-independente]]);
- ao mudar a situação para `inconclusiva` ou `descartada`, os vínculos salvos cuja fonte ficou indisponível são preservados;
- `situacao_sem_base: true` indica que a situação declarada perdeu a evidência que a fundamentava.

```json
{"caso": "alpha", "total": 2, "divergentes": [],
 "aviso": "Situações declaradas por pessoas; o quadro não avalia veracidade. …",
 "hipoteses": [
  {"id": "He23121a…", "sha256": "2b2b4200…", "enunciado": "O valor foi efetivamente pago.",
   "situacao": "em_aberto", "situacao_declarada_por": "Demonstração sintética", "situacao_sem_base": false,
   "condicao": "pendencia", "natureza": "pendencia",
   "sustentam": [], "contrariam": [], "contexto": [], "indisponiveis": [],
   "faltam": [{"origem": "automatica", "descricao": "Nenhuma evidência de suporte conferida.",
               "diligencia_id": null, "diligencia_estado": null}],
   "atualizado_em_utc": "2026-11-19T10:25:42.834699+00:00"},
  {"id": "H…", "enunciado": "O valor declarado na fonte é 12.", "situacao": "em_aberto",
   "condicao": "com_evidencia", "natureza": "inferencia",
   "sustentam": [{ …vínculo salvo…, "estado": "conferida", "evidencia": { …seção 4… } }],
   "contrariam": [ … ], "contexto": [ … ], "indisponiveis": [],
   "faltam": [{"origem": "registrada", "descricao": "Comprovante de pagamento do valor declarado.",
               "diligencia_id": null, "diligencia_estado": null},
              {"origem": "automatica", "descricao": "Há evidências sustentadas nos dois sentidos; conferir antes de concluir.", "…": "…"}]}]}
```

### 5.3 `linha_tempo.py`

Coleção `linha_do_tempo`, prefixo `T`.

| Função | Devolve |
|---|---|
| `salvar(root, data, operacao='criar', conta=None)` / `detalhe` / `listar` | Registro / lista. |
| `data_parcial(valor)` | `ano`, `mes` ou `dia`. Recusa forma inválida ou data inexistente no calendário. |
| `linha(root, caso, *, tipos=None, incluir_retirados=False)` | Linha do tempo (abaixo). `tipos` filtra por tipo de data. |

Campos editáveis:

| Campo | Regra |
|---|---|
| `descricao` | Até 1000 caracteres. |
| `datas` | De 1 a 10 itens `{tipo, valor, fonte, aproximada?, observacao?}`. |
| `evidencias` | Pelo menos uma de papel `suporte`. |
| `retirado` | Booleano. |
| `motivo_retirada` | Obrigatório ao retirar. |

Regras das datas:

- `valor` aceita `AAAA`, `AAAA-MM` ou `AAAA-MM-DD`. A `precisao` é sempre recalculada a partir do valor.
- `fonte` é o índice do vínculo que documenta a data.
- Uma evidência de `contradicao` não documenta data.
- Uma evidência de `contexto` só documenta data do tipo `declarada_por_fonte`.

`TIPOS_DATA`: `fato` (ocorrência), `emissao_documento` (documento), `assinatura`, `publicacao`, `registro`, `vigencia_inicio`, `vigencia_fim`, `pagamento`, `recebimento`, `declarada_por_fonte`. Tipos diferentes nunca são fundidos.

Ordem das entradas:

- cada data parcial vai para o início do seu período, e a precisão mais grossa vem primeiro: `2020-12-31` < `2021` < `2021-03` < `2021-03-12`;
- isso não afirma que o fato ocorreu no início do período.

Divergências: no mesmo evento, datas diferentes do mesmo tipo geram `divergencias[]`, com `classe` `compativel_precisao_diferente` ou `conflitante`. O Core só as sinaliza; nunca as resolve.

```json
{"caso": "alpha", "total": 4, "divergencias": [], "fontes_indisponiveis": [], "divergentes": [],
 "tipos_data": {"fato": "Data do fato (ocorrência)", "…": "…"},
 "aviso": "Ordem por data registrada; datas parciais vão para o início do período, …",
 "entradas": [
  {"evento_id": "T04a376f9…", "sha256": "7acf8059…", "descricao": "Declaração do valor 12",
   "data": {"tipo": "declarada_por_fonte", "valor": "2021", "precisao": "ano", "aproximada": false,
            "fonte": 1, "observacao": "", "rotulo": "Data declarada por uma fonte"},
   "fonte_da_data": { …vínculo salvo…, "estado": "conferida",
                      "evidencia": {"localizador": {"legivel": "D001 · Linha 2", "…": "…"}, "…": "…"} },
   "fonte_conferida": true, "evidencias": [ … ],
   "divergente": false, "divergencia": null, "retirado": false, "motivo_retirada": ""}]}
```

### 5.4 `comparador.py`

Não grava nada. Compara texto já autorizado.

| Função | Devolve |
|---|---|
| `marcas(texto)` | Datas e valores encontrados no texto. As datas vêm como `{tipo: data\|data_invalida, bruto, normalizado, precisao, posicao, fim}`; os valores, como `{tipo: numero\|valor_monetario\|percentual, bruto, normalizado, valor, unidade, dimensao, posicao, fim}`. |
| `calculo(a, b)` | `None` se não houver valor, ou `{operacao: "b - a", a, b, unidade, diferenca, motivo}`. |
| `comparar_textos(a, b)` | `{identicos, semelhanca, segmentos, alteracoes, truncado, marcas}`. |
| `comparar_evidencias(root, caso, ref_a, ref_b)` | `{caso, a, b, …comparar_textos, aviso}`, em que `a` e `b` são evidências resolvidas (seção 4). |
| `comparar_documentos(root, caso, rodada, doc_a, doc_b, *, contexto=2)` | Comparação linha a linha do texto (nativo ou OCR) de dois documentos da rodada, com `localizador_a/b` e `contexto_a/b`. `contexto` vai de 0 a 10. |

Regras do cálculo:

- a diferença só é calculada com exatamente um valor de cada lado e tipo, unidade e dimensão idênticos;
- não há conversão: `kg` × `t`, `R$` × `US$`, `%` × `R$` ou `kg` × `m` saem com `diferenca: null` e `motivo: "unidades_incompativeis"`;
- mais de um valor de algum lado sai com `motivo: "pareamento_ambiguo"`;
- uma data inexistente (31/02) vira `data_invalida`, sem normalização.

Cada alteração traz:

- `classe`: `valor`, `data`, `valor_e_data` ou `conteudo`;
- `contexto_a`/`contexto_b`: em `comparar_textos`, `{antes, depois}`; em `comparar_documentos`, uma lista de linhas `{pagina_pdf, linha, texto}`;
- `posicao_a`/`posicao_b`: as palavras alteradas, em `comparar_textos`.

```json
{"caso": "gamma", "rodada": "R001",
 "a": {"documento_id": "D001", "original_sha256": "11916…", "fonte": "casos/gamma/…/D001_contrato_v1_sintetico.txt",
       "fonte_sha256": "11916…", "tipo_fonte": "original", "metodo": "Leitura direta de texto UTF-8",
       "paginas_sem_texto": []},
 "b": { … }, "identicos": false, "semelhanca": 0.8, "total_alteracoes": 2, "truncado": false,
 "alteracoes": [
  {"operacao": "substituido", "classe": "valor",
   "a": "Valor global: R$ 8.750.000,00 (…).", "b": "Valor global: R$ 10.937.500,00 (…).",
   "localizador_a": {"pagina_pdf": null, "linha_inicio": 6, "pagina_pdf_fim": null, "linha_fim": 6},
   "localizador_b": {"pagina_pdf": null, "linha_inicio": 6, "pagina_pdf_fim": null, "linha_fim": 6},
   "contexto_a": [{"pagina_pdf": null, "linha": 5, "texto": "Objeto: pavimentacao asfaltica de 12,4 km …"}],
   "contexto_b": [ … ],
   "calculo": {"operacao": "b - a", "a": ["R$ 8750000"], "b": ["R$ 10937500"], "unidade": "R$",
               "diferenca": "2187500", "motivo": null},
   "palavras": {"segmentos": [ … ], "alteracoes": [ … ]}}],
 "marcas": {"somente_a": [ … ], "somente_b": [ … ], "comuns": [ … ]},
 "aviso": "Comparação do texto extraído (nativo ou OCR); conferir no original nomes, valores e tabelas."}
```

### 5.5 `mapa_relacoes.py`

Coleções `entidades` (prefixo `P`) e `relacoes` (prefixo `L`).

| Função | Devolve |
|---|---|
| `salvar_entidade(root, data, operacao='criar', conta=None)` / `detalhe_entidade` / `listar_entidades` | Registro / lista. |
| `salvar_relacao(root, data, operacao='criar', conta=None)` / `detalhe_relacao` / `listar_relacoes` | Registro / lista. |
| `nome_normalizado(valor, tipo='pessoa')` | Nome sem acento, caixa ou partículas. Em organizações, também sem sufixo societário. |
| `mascarar(tipo, valor)` | Forma de exibição de CPF/CNPJ. O valor salvo não muda. |
| `homonimos(root, caso, entidades=None)` | Lista de candidatos a homônimo. |
| `mapa(root, caso, *, incluir_retirados=False)` | `{caso, entidades, relacoes, homonimos, divergentes, aviso}`. |

Campos de uma entidade:

| Campo | Regra |
|---|---|
| `tipo` | `pessoa` ou `organizacao`; não muda depois de criado. |
| `nome` | Obrigatório. |
| `variantes` | Até 20. |
| `identificadores` | Até 20 itens `{tipo, valor, fonte}`. `tipo` está em `TIPOS_ID`: `cpf`, `cnpj`, `registro_profissional`, `matricula`, `outro`. `fonte` é obrigatória, e o CPF/CNPJ é salvo só com dígitos. |
| `evidencias` | Vínculos. |
| `conferencias` | Até 50 itens `{entidade_id, decisao, justificativa, fontes}`. `decisao` está em `DECISOES`: `mesma_entidade`, `entidade_distinta`, `indeterminado`. Decidir algo diferente de `indeterminado` exige `fontes`. A conferência só vale entre entidades do mesmo tipo. |
| `retirado`, `motivo_retirada` | Como na linha do tempo. |

Campos de uma relação:

| Campo | Regra |
|---|---|
| `origem`, `destino` | Entidades registradas e diferentes. |
| `tipo` | Até 120 caracteres. |
| `descricao` | Opcional. |
| `evidencias` | Pelo menos uma de papel `suporte`. |
| `retirado`, `motivo_retirada` | Como na linha do tempo. |

Situações:

- **Relação:**
  - `documentada`, somente com suporte conferido avaliado como `sustentado` e de natureza documental;
  - `inferida`, com suporte `sustentado` só como `inferencia`;
  - `suporte_parcial`;
  - `suporte_nao_revisado`;
  - `sem_suporte_sustentado`;
  - `fonte_indisponivel`.
- **Entidade:**
  - `com_evidencia`;
  - `evidencia_indisponivel`;
  - `sem_evidencia`.

Os homônimos são sugestões e nunca resultam em fusão:

- `motivo` é um de `nome_igual`, `mesmas_palavras`, `nome_contido`, `grafia_parecida` ou `identificador_igual`;
- `situacao` é `pendente` enquanto ninguém decidiu, a própria decisão quando há uma só, ou `decisoes_divergentes`;
- uma decisão `mesma_entidade` não funde as entidades: as duas continuam no mapa.

```json
{"caso": "alpha", "divergentes": [],
 "entidades": [
  {"id": "Pd92bdcd4…", "sha256": "…", "tipo": "pessoa", "nome": "Lúcia Prates", "variantes": [],
   "identificadores": [{"tipo": "matricula", "fonte": 0, "valor_exibicao": "7781"}],
   "evidencias": [ …vínculos conferidos… ], "situacao": "com_evidencia",
   "retirado": false, "motivo_retirada": ""}],
 "relacoes": [
  {"id": "L4b1439b6…", "sha256": "371fc99d…", "origem": "Pd92bdcd4…", "destino": "P08422bc9…",
   "tipo": "fiscal de contrato com", "descricao": "", "evidencias": [ … ], "situacao": "documentada",
   "entidades_disponiveis": true, "retirado": false, "motivo_retirada": ""}],
 "homonimos": [
  {"entidades": ["P07357e0b…", "Pd92bdcd4…"], "nomes": ["Lucia  PRATES", "Lúcia Prates"],
   "motivo": "nome_igual", "identificadores_comuns": [], "identificadores_divergentes": ["matricula"],
   "conferencias": [], "situacao": "pendente",
   "aviso": "Sugestão para conferência humana; as entidades não foram fundidas."}],
 "aviso": "Ligações registradas por pessoas a partir de evidências; não indicam culpa nem causalidade. …"}
```

Na visão do mapa (`mapa-ver`) e em `homonimos`, os identificadores vêm só com `tipo`, `fonte` e `valor_exibicao` (CPF/CNPJ mascarados). `identificadores_comuns` é uma lista de `{"tipo", "valor_exibicao"}`. O valor completo só aparece no detalhe e na resposta de salvamento da entidade.

### 5.6 Rotas HTTP da Mesa (`scripts/rotas_evidencia.py`)

O servidor da Mesa (`scripts/interface_pesquisa.py`) expõe os quadros como `POST /api/<operacao>`. `GET /api/integracao` anuncia `quadros_evidencia: true`. Toda chamada segue as mesmas regras:

- **Método e cabeçalhos:** `POST`, `Content-Type: application/json`, `X-Session-Token: <csrf da sessão>` e `Origin` igual à origem do servidor. O corpo é um objeto JSON. O limite é de 128 KB para as operações de salvar e de 32 KB para as de leitura.
- **Acesso:** só administradores. Sem sessão a resposta é `401 {estado: "sem_sessao", codigo: "sessao_expirada"}`, e o corpo não é interpretado: até 32 KB ele é descartado antes da resposta (no Windows, fechar com bytes não lidos envia um reset que pode perder o 401), e acima disso nem é lido. Um convidado recebe `403 codigo: "operacao_proibida"`. Token ou Origin inválidos dão `403`. As rotas não entram em `OPERACOES_CONVIDADO`.
- **Caso:** `caso` é obrigatório em todo corpo. Ele é validado (`ID_CASO`, existente e fora da lixeira) antes de qualquer leitura. O cliente nunca envia caminhos. Uma referência de outro caso é recusada com `evidencia_outro_caso`, e um ID de outro caso resulta em `registro_inexistente`.
- **Execução:** sob `cadastro_lock`, sem chamada de modelo ou de rede.
- **Sucesso:** `200` com o JSON devolvido pela função do módulo (seções 5.2–5.5).
- **Erro:** `400 {estado: "erro", erro: "<mensagem em português>", codigo: "<código estável>"}`. A interface traduz o `codigo` pelo dicionário `erros` de `interface/i18n_en.js`. Os códigos dos quadros incluem `quadro_sem_caso`, `quadro_campos_invalidos`, `registro_inexistente`, `registro_mudou`, `evidencia_outro_caso`, `historico_divergente`, `tipos_data_invalidos`, `filtro_retirados_invalido`, `documento_fora_da_rodada`, `rodada_comparacao_ausente` e `contexto_comparacao_invalido`. A lista completa está em `scripts/erros.py`.
- **Campos extras:** nas leituras, qualquer campo fora da lista abaixo é recusado com `quadro_campos_invalidos`. Nas operações de salvar, a recusa vem do próprio módulo.

| Operação (`POST /api/…`) | Corpo | Resposta 200 |
|---|---|---|
| `hipoteses-listar` | `{caso}` | `{caso, hipoteses: [registro…]}` |
| `hipoteses-detalhe` | `{caso, id}` | Registro, com `evidencias`: vínculos conferidos contra a fonte (`conferir_vinculos`). |
| `hipoteses-quadro` | `{caso}` | Quadro da seção 5.2 (suporte, contradição, lacunas). |
| `hipoteses-criar` | `{caso, requisicao_id, autor, observacao?, enunciado, situacao, evidencias, lacunas?}` | Registro. |
| `hipoteses-atualizar` | `{caso, requisicao_id, autor, id, anterior_sha256, …campos alterados}` | Registro. |
| `linha-tempo-listar` | `{caso, tipos?: [tipo_data…], incluir_retirados?: bool}` | Linha do tempo da seção 5.3. |
| `linha-tempo-detalhe` | `{caso, id}` | Registro, com `evidencias` conferidas. |
| `linha-tempo-criar` / `-atualizar` | Como em hipóteses, com os campos da seção 5.3. | Registro. |
| `comparar-evidencias` | `{caso, a: referência, b: referência}` | `{caso, a, b, identicos, semelhanca, segmentos, alteracoes, truncado, marcas, aviso}` |
| `comparar-documentos` | `{caso, rodada, documento_a, documento_b, contexto?: 0–10}` | Comparação da seção 5.4, com `localizador_a/b` e `contexto_a/b`. |
| `mapa-ver` | `{caso, incluir_retirados?: bool}` | `{caso, entidades, relacoes, homonimos, divergentes, aviso}` |
| `mapa-homonimos` | `{caso}` | `{caso, homonimos: [candidato…]}` |
| `mapa-entidade-criar` / `-atualizar` | Como em hipóteses, com os campos de entidade da seção 5.5. | Registro. |
| `mapa-relacao-criar` / `-atualizar` | Como em hipóteses, com os campos de relação da seção 5.5. | Registro. |

Testes: `python -m unittest discover -s testes -p test_rotas_evidencia.py -v` (servidor local, dados sintéticos, sessão, convidado e outro caso). Também `testes/test_autorizacao.py` (`SO_ADMIN`) e `testes/test_erros.py` (códigos).

### 5.7 Tabelas de apuração (`scripts/tabelas_apuracao.py`, `scripts/rotas_tabelas.py`)

Quadro montado sobre o Core pela via da seção 7 ("novos quadros sobre `evidencias.Colecao`"), sem mudar `evidencias.py` nem `ESQUEMA`. Armazenamento: `evidencias.Colecao('tabelas', 'Q', …)`, com eventos em `casos/<caso>/quadros/tabelas/<Q…>/`. Cada célula aponta para uma evidência da própria tabela, que é um vínculo salvo do Core (seção 3.2) resolvido contra o original. Dependências privadas reaproveitadas: `linha_tempo.data_parcial`, `caderno._hash`, `rotas_evidencia._caso` e `_sim_nao`. Quem mudar essas funções precisa avisar Tabelas.

**Estado da tabela** (campos editáveis): `titulo` (até 300), `descricao` (até 2000), `colunas`, `linhas`, `evidencias` (vínculos salvos, até 100), `calculos` (até 50), `correcoes` (só as do próprio evento; `[]` nos demais), `retirado` e `motivo_retirada`. Limites: 30 colunas, 500 linhas e 5000 células.

**Coluna:** `{id, nome, tipo, moeda, unidade}`.

- `id` segue `[a-z][a-z0-9_]{0,39}`. `tipo` é `texto`, `data`, `monetario` ou `numero`.
- `monetario` exige `moeda` (`[A-Z]{3}`) e aceita `unidade` opcional como escala declarada pela fonte (`mil`, `milhões`). `numero` exige `unidade`. `texto` e `data` não têm moeda nem unidade.
- Uma coluna registrada nunca muda de id, ordem, tipo, moeda ou unidade. Só o nome muda. Colunas novas entram no fim, com células `pendente` nas linhas existentes.

**Linha:** `{id: "L0001", celulas: {<id da coluna>: célula}}`. Os ids seguem a posição. Linhas só são acrescentadas ao fim; não são retiradas nem reordenadas.

**Célula salva:**

```json
{"valor": "2345.50", "fonte": 0, "estado": "extraido"}
```

| Campo | Regra |
|---|---|
| `valor` | `null` para célula vazia. Texto até 2000 caracteres. Data `AAAA`, `AAAA-MM` ou `AAAA-MM-DD`. Número em texto canônico `-?[0-9]{1,30}(\.[0-9]{1,12})?`, com ponto decimal, sem separador de milhar nem expoente, preservando a escala (`"007.50"` vira `"7.50"`, `"-0.00"` vira `"0.00"`). `1.234,56`, float JSON e `1e3` são recusados. |
| `fonte` | Índice de uma evidência de papel `suporte` em `evidencias` da tabela, ou `null`. Segue a identidade da evidência (`realocar_fontes`), como `datas[].fonte` na linha do tempo. |
| `estado` | `extraido`, `corrigido_manual` ou `pendente`. Sempre calculado, nunca aceito do cliente. `pendente` quando falta valor ou fonte. |

Na visão (`tabelas-detalhe`), a célula traz também `fonte_legivel`, `fonte_conferida` e `ultima_correcao`.

**Correção manual** (`corrigir`, rota `tabelas-corrigir`): pedido `{caso, requisicao_id, autor, observacao?, id, anterior_sha256, correcoes: [{linha, coluna, valor?, fonte?, justificativa?}]}`, com 1 a 100 itens e sem outros campos da tabela.

- Mudar valor ou fonte que já existiam é `correcao`: exige justificativa e deixa a célula `corrigido_manual` (ou `pendente`, se ficar sem valor ou sem fonte).
- Preencher valor ou fonte que faltavam é `preenchimento`: não exige justificativa e deixa a célula `extraido` ou `pendente`.
- O evento novo grava em `estado.correcoes` cada item como `{linha, coluna, tipo, valor_anterior, fonte_anterior, valor, fonte, justificativa}`, com o autor da conta (quando há conta), `origem_autoria`, `conta_id` e `em_utc`. Nenhum evento anterior é alterado.
- Uma célula já registrada não muda por `salvar(…, 'atualizar')`: a linha precisa voltar como está salva (`tabela_celula_registrada`).

**Cálculo declarado:** `{id, nome, operacao, coluna, linhas, celulas, casas_decimais}`.

```json
{"id": "total_2024", "nome": "Total pago em 2024", "operacao": "soma", "coluna": "valor", "linhas": ["L0001", "L0002"]}
```

- `operacao`: `soma`, `diferenca`, `contagem` ou `media`.
- As células vêm de `coluna` (com `linhas` opcional; `null` = todas, na ordem) ou de `celulas: [{linha, coluna}]`. `diferenca` usa exatamente duas células (primeira − segunda). `casas_decimais` (0 a 12) só vale na média.
- Soma, diferença e média exigem colunas com o mesmo `(tipo, moeda, unidade)`. Não há conversão: BRL × USD, BRL × BRL mil e kg × t são recusados já na declaração (`calculo_unidades_incompativeis`).
- As contas usam `decimal.Decimal` em contexto exato (precisão 100, com qualquer arredondamento interceptado). A média é exata quando a divisão termina. Senão, arredonda meio para cima (a metade exata vai para longe do zero), com 6 casas ou com as declaradas, e `arredondamento` registra as casas, a regra e se foram declaradas.
- Célula sem valor recusa soma, diferença e média (`calculo_celula_sem_valor`). O `estado` do resultado é `com_fonte` ou `pendente` (alguma célula `pendente`, listada em `celulas_pendentes`). `fontes_sustentadas` só é verdadeiro sem pendência e quando toda fonte tem suporte `sustentado` e natureza documental, como nos quadros do Core; as demais saem em `fontes_nao_sustentadas`. Na visão da tabela, uma fonte indisponível deixa o cálculo `pendente`, com `fontes_indisponiveis`, e uma conta que falha vem como `recusado`, com `erro`.

**Saída do cálculo** (`calcular`, `calcular_tabela`, rota `tabelas-calcular`). Exemplo ilustrativo, encurtado:

```json
{"id": "total_2024", "nome": "Total pago em 2024", "operacao": "soma", "definicao": {…},
 "celulas": [{"linha": "L0001", "coluna": "valor", "nome_coluna": "Valor", "valor": "1200.00",
              "estado": "extraido", "fonte": 0, "fonte_legivel": "achados alpha/R001/…/E01 …"}, …],
 "n": 2, "grandeza": {"tipo": "monetario", "moeda": "BRL", "unidade": null},
 "expressao": "1200.00 + 1145.50", "resultado": "2345.50", "exato": true, "arredondamento": null,
 "estado": "com_fonte", "celulas_pendentes": [], "fontes_sustentadas": true, "fontes_nao_sustentadas": [],
 "entrada_sha256": "…", "aviso": "…"}
```

A média acrescenta `soma` e `divisor`, e a contagem acrescenta `celulas_sem_valor`. A diferença de percentuais sai em `pontos percentuais`. `entrada_sha256` é o hash canônico de `{operacao, grandeza, casas_decimais, operandos: [[linha, coluna, valor]…]}`: a mesma entrada dá o mesmo hash e o mesmo resultado. `calcular_tabela` refaz a conta sobre qualquer versão do histórico (`sequencia`, 1 = criação) e acrescenta `caso` e `tabela: {id, titulo, sequencia, sha256}`, a versão usada.

**CSV** (`exportar_csv`, rota `tabelas-exportar`): UTF-8 com BOM. Cada coluna da tabela vira três: o valor, `<rótulo> - fonte` (localizador legível da evidência, `PENDENTE: sem fonte` ou `FONTE INDISPONÍVEL: …`) e `<rótulo> - estado`. Texto iniciado por `= + - @` ganha apóstrofo, contra injeção de fórmula. `formato`: `padrao` (vírgula e ponto decimal) ou `excel_br` (ponto e vírgula e vírgula decimal).

| Função | Devolve |
|---|---|
| `salvar(root, data, operation='criar', conta=None)` | Registro compacto. `operation` é `criar` ou `atualizar`. |
| `corrigir(root, data, conta=None)` | Registro compacto. |
| `detalhe(root, caso, id)` / `listar(root, caso)` | Registro(s) da coleção, como na seção 5. |
| `tabela(root, caso, id)` | Visão com células e evidências conferidas, cálculos refeitos e histórico compacto. |
| `quadro(root, caso, *, incluir_retirados=False)` | Lista de tabelas para a Mesa. |
| `calcular(state, definicao)` | Saída do cálculo sobre um estado. |
| `calcular_tabela(root, caso, id, calculo, sequencia=None)` | Saída do cálculo sobre uma versão salva. |
| `historico_celula(root, caso, id, linha, coluna)` | Versões da célula. |
| `exportar_csv(root, caso, id, formato='padrao')` | Texto CSV. |
| Constantes | `TIPOS_COLUNA`, `ESTADOS_CELULA`, `TIPOS_CORRECAO`, `OPERACOES_CALCULO`, `FORMATOS_CSV`, `ID_TABELA`, `CAMPOS_CELULA`, `CAMPOS_CORRECAO`, `CAMPOS_CALCULO`. |

**Rotas:** seguem as regras da seção 5.6, com corpo de salvamento de até 2 MB. `/api/integracao` anuncia `tabelas_apuracao: true`.

| Operação (`POST /api/…`) | Corpo | Resposta 200 |
|---|---|---|
| `tabelas-listar` | `{caso, incluir_retirados?}` | Lista de tabelas. |
| `tabelas-detalhe` | `{caso, id}` | Visão da tabela. |
| `tabelas-historico-celula` | `{caso, id, linha, coluna}` | Versões da célula. |
| `tabelas-calcular` | `{caso, id, calculo: id ou definição, sequencia?}` | Saída do cálculo. |
| `tabelas-criar` / `-atualizar` | Como em hipóteses, com os campos da tabela. | Registro compacto. |
| `tabelas-corrigir` | Pedido de correção acima. | Registro compacto. |
| `tabelas-exportar` | `{caso, id, formato?}` | Anexo `text/csv`, `tabela_<id>.csv`. |

Códigos novos em `scripts/erros.py`, traduzidos em `i18n_en.js`: `tabela_coluna_invalida`, `tabela_colunas_registradas`, `tabela_linha_invalida`, `tabela_celula_invalida`, `tabela_celula_inexistente`, `tabela_celula_registrada`, `tabela_valor_invalido`, `tabela_fonte_invalida`, `tabela_fonte_em_uso`, `tabela_fonte_indisponivel`, `tabela_grande_demais`, `tabela_versao_inexistente`, `correcao_sem_justificativa`, `correcao_invalida`, `calculo_unidades_incompativeis`, `calculo_celula_sem_valor`, `calculo_recusado`, `calculo_invalido`, `calculo_inexistente` e `exportacao_formato_invalido`.

### 5.8 Fontes web por caso (`scripts/fontes_web.py`)

<!-- Seção de lapidacao/fontes-web. Só esse agente edita entre este marcador e o título "### 5.9". -->
Só existe em casos criados no modo `documentos_web` (exceção do `AGENTS.md`). O modo e o domínio único ficam no manifesto do caso, em `fontes_web: {modo, dominio_permitido, definido_em_utc, definido_por}`, e são escolhidos só na criação. O padrão é `somente_documental`, com `dominio_permitido: null`. Manifestos antigos, sem o bloco, valem como `somente_documental`.

**A captura entra pela via do cadastro, como documento do caso.** Não há um terceiro `tipo` de referência. Uma captura recebe um ID `W###` no mesmo espaço dos `D###` do caso. É congelada em `entradas/` pela rodada, entra no índice SQLite como os outros documentos e é citada por uma evidência `ia` (seção 2.1) cujo `documento_id` é o `W###`. A resolução (seção 4) é a mesma: original e texto autorizado conferidos por hash.

**Captura no manifesto** (`capturas_web[]`, só acréscimo; cada captura nova sobe o `corpus_id`):

```json
{"id": "W001", "tipo": "captura_web",
 "url_solicitada": "https://www.exemplo.gov.br/contratos?id=12",
 "url_final": "https://www.exemplo.gov.br/contratos/12",
 "dominio_permitido": "www.exemplo.gov.br",
 "acessado_em_utc": "2026-11-19T12:00:00+00:00", "resposta_concluida_em_utc": "2026-11-19T12:00:01+00:00",
 "status_http": 200, "tipo_conteudo": "text/html",
 "cabecalhos": {"content-type": "text/html; charset=utf-8", "date": "…", "last-modified": "…"},
 "redirecionamentos": [{"de": "…?id=12", "para": "…/contratos/12", "status_http": 302}],
 "endereco_ip": "203.0.113.7",
 "arquivo": "casos/alpha/fontes_web/W001_<hex>/conteudo.html", "sha256": "…", "bytes": 5321,
 "observacao": null, "mesmo_conteudo_que": null,
 "derivados": [{"arquivo": "casos/alpha/fontes_web/W001_<hex>/texto.txt", "sha256": "…",
                "tipo": "texto_extraido_web", "origem_sha256": "…", "metodo": "html.parser …",
                "charset_usado": "utf-8", "caracteres_substituidos": false, "titulo_pagina": "…"}],
 "registro": {"arquivo": "casos/alpha/fontes_web/W001_<hex>/captura.json", "sha256": "…"}}
```

- `arquivo` é o conteúdo bruto, exatamente como recebido (o original). O derivado `texto_extraido_web` (HTML e texto) ou `texto_extraido_pdf` (PDF) é a cópia textual UTF-8 em que valem os localizadores por linha.
- `casos/<caso>/fontes_web/registro.jsonl` recebe uma linha por captura publicada. Ela é só acrescentada, nunca reescrita.
- O conteúdo da página é dado da fonte, nunca instrução.

**Referência e localizador.** A evidência dos achados segue a forma de `registros_achados`, com `documento_id: "W001"`, `original` e `fonte_textual` em `entradas/…` e localizador `linhas`. A descrição leva o endereço e o horário do acesso, como `fontes_web.localizador(captura, linha_inicio, linha_fim, trecho)` monta:

```json
{"modo": "direta", "documento_id": "W001",
 "original": "entradas/casos/alpha/fontes_web/W001_<hex>/conteudo.html", "original_sha256": "…",
 "fonte_textual": "entradas/casos/alpha/fontes_web/W001_<hex>/texto.txt", "fonte_sha256": "…",
 "localizador": {"tipo": "linhas", "pagina_pdf": null, "linha_inicio": 7, "linha_fim": 7,
                 "descricao": "https://www.exemplo.gov.br/contratos/12 (acesso 2026-11-19T12:00:00+00:00), linhas 7–7"},
 "trecho": "Valor global: R$ 1.234,56"}
```

**Regras da captura:**
- recusa tudo fora do modo `documentos_web`;
- aceita só `https` e o host igual ao `dominio_permitido`, com redirecionamentos seguidos à mão (até 5) e conferidos a cada salto;
- resolve o nome, recusa qualquer endereço que não seja público e conecta ao IP conferido;
- limite de 20 MB, 20 s por operação e 60 s no total; só HTML, texto e PDF, sem compressão.
- O `http` e o `127.0.0.1` valem só nos testes, com `fontes_web.TESTE_LOCAL`.

**Rotas** (seção 5.6, só administrador, sem caminhos do cliente e com campos fechados):

| Operação (`POST /api/…`) | Corpo | Resposta 200 |
|---|---|---|
| `fontes-web-listar` | `{caso}` | `{caso_id, modo, dominio_permitido, capturas: [{id, url_solicitada, url_final, acessado_em_utc, status_http, tipo_conteudo, sha256, bytes, observacao, mesmo_conteudo_que}]}` |
| `fontes-web-abrir` | `{caso, captura}` | `{caso_id, dominio_permitido, captura: {…, cabecalhos, redirecionamentos, titulo_pagina}, texto, texto_truncado, aviso}`. Devolve só o texto, nunca o HTML bruto. |
| `fontes-web-capturar` | `{caso, url, observacao?}` | `{caso_id, corpus_id, captura, aviso}`. É a única rota com rede; o download corre fora da `cadastro_lock`. |

Os códigos de erro `fontes_web_*` ficam em `scripts/erros.py` e são traduzidos em `interface/i18n_en.js`. `comum.documentos_e_capturas(manifest)` devolve documentos e capturas na forma de documento. Fica em `comum.py`, sem código de rede, para a cópia portátil de `banco.py` continuar funcionando.

### 5.9 Redação e entrevistas (fase 08)

<!-- Seção de lapidacao/redacao. Só esse agente edita entre este marcador e o título "## 6.". -->
Dois quadros novos sobre `evidencias.Colecao` (via da seção 7), sem mudar `evidencias.py` nem `ESQUEMA`: `redacao` (prefixo `C`, `scripts/conferencia_redacao.py`, ID `C` + 32 hex) e `perguntas` (prefixo `J`, `scripts/entrevistas.py`, ID `J` + 32 hex). Vínculos e `natureza` são os da seção 3, sem mudança. Commits `eba9e83`, `d17d6bc` e o da troca de prefixo na branch `lapidacao/redacao`. O quadro `redacao` usava `W` até a decisão do Core registrada na tabela de prefixos: `W` fica com o ID de documento das capturas web (seção 5.8).

**Texto conferido** (estado do quadro `redacao`): `{titulo (até 300), texto (até 50 000, guardado como enviado, com \r\n → \n), versao (≥ 1), afirmacoes (até 500), revisao}`. `revisao` só existe no evento que registra uma revisão humana (`null` nos demais), como `correcoes` nas tabelas.

**Afirmação** (cada item de `afirmacoes`):

```json
{"id": "F<32 hex>", "texto": "A fonte declara valor 12.", "texto_sha256": "…", "inicio": 0, "fim": 25,
 "tipo": "frase", "evidencias": [ …vínculos salvos (seção 3.2)… ],
 "revisao_humana": null, "reaberta": false, "anterior_id": null, "desde_versao": 1}
```

- `texto == texto_do_registro[inicio:fim]`, conferido a cada leitura. `tipo` é `frase` ou `oracao` (frase dividida por ponto e vírgula). Perguntas e trechos com menos de três palavras não viram afirmação.
- `revisao_humana`: `null` ou `{decisao, observacao, conta_id, responsavel, sequencia, texto_sha256}`. `decisao` usa `revisao_humana.ESTADOS` sem `pendente` (`conferida_no_original`, `precisa_de_ajuste`, `sem_suporte_suficiente`). O campo é próprio deste quadro; `revisao_humana.py` só fornece os estados, porque o armazenamento dele é por achado da IA numa rodada. `conferida_no_original` exige um vínculo de papel `suporte`.
- **Só conta autenticada revisa.** Sem conta (inclusive no modo local), `revisar` recusa com `revisao_humana_sem_conta`. Na leitura, cada `revisao_humana` precisa apontar (`sequencia`) para um evento com `origem_autoria = humana_autenticada_pela_conta_da_mesa`, o mesmo `conta_id` e a mesma decisão; senão o registro sai como histórico divergente.
- **Nova versão do texto:** afirmação de texto idêntico mantém `id`, vínculos e revisão; afirmação parecida (semelhança ≥ 0,6) ganha `id` novo, `anterior_id`, os vínculos da anterior e `reaberta: true`, sem revisão; as demais nascem sem vínculo. Trocar os vínculos de uma afirmação revisada também a reabre.

**Visão** (`conferencia`, rota `redacao-conferir`): cada afirmação traz ainda `evidencias` conferidas (`conferir_vinculos`), `sinais`, `estado_automatico`, `estado` e `indisponiveis`; mais `resumo` (`total`, `por_estado`, `com_sinais`, `reabertas`) e `versoes`.

- `estado_automatico`: `sem_suporte` (nenhum suporte conferido), `suportada` (suporte conferido `sustentado` de natureza documental, sem sinais e sem contradição sustentada) ou `suporte_parcial`. `estado` é `revisada_por_humano` quando há revisão válida; senão, o automático.
- `sinais[]`: `{tipo, trecho, posicao, detalhe}`, com `tipo` em `numero_divergente`, `quantificador_mais_forte`, `causalidade_sem_suporte` ou `certeza_sem_atribuicao`. São regras fixas sobre os trechos das evidências de suporte conferidas, sem modelo; sem trecho textual não há sinal. Nunca mudam um vínculo nem um estado declarado.

**Pergunta** (estado do quadro `perguntas`):

```json
{"origem": {"tipo": "hipotese", "hipotese_id": "H…", "hipotese_sha256": "…", "lacuna": "Ordem bancária do pagamento."},
 "motivo": {"contexto": "O valor declarado foi pago.", "lacuna": "…", "origem_lacuna": "registrada"},
 "pergunta": "A respeito de “…”: pode informar e, se possível, documentar o seguinte ponto: …?",
 "evidencias": [ …vínculos salvos… ], "diligencia_id": "G…", "situacao": "aberta", "respostas": []}
```

- `origem` também pode ser `{tipo: "afirmacao", texto_id, texto_sha256, afirmacao_id}` (afirmação `sem_suporte`). Vem exatamente de `lacunas` e é recusada (`lacuna_origem_mudou`) se o item mudou. `origem_lacuna` é `registrada`, `automatica` ou `afirmacao_sem_suporte`.
- A pergunta é rascunho por modelo de texto fixo, sem IA; a pessoa pode reescrevê-la (`entrevistas-editar`).
- `diligencia_id`: diligência criada junto, com os campos opcionais novos de `diligencias.py` `{tipo: entrevista|pedido_informacao|pedido_lai, destinatario, pergunta_id}`. Diligências sem esses campos continuam válidas, e eles não mudam depois de criados.
- `respostas[]`: `{situacao: respondida|parcial|sem_resposta, referencia, observacao}`. `respondida` e `parcial` exigem `referencia` `humana` (seção 2.2) para o registro do caderno criado com o trecho do documento da resposta, já cadastrado no caso; o documento entra também como resposta da diligência. `sem_resposta` não leva fonte. `situacao` da pergunta é a da última resposta.

**Exportação** (`entrevistas-exportar`, `{caso, ids, formato}`): Markdown em `{caso, formato, nome_arquivo, markdown}`. `pauta` é documento interno, com motivo, contato e evidências conferidas. `pedido` exige perguntas de `pedido_informacao` ou `pedido_lai` com o mesmo destinatário e leva só as perguntas, sem evidências nem anotações internas. Texto de usuário é escapado para não virar marcação.

**Rotas** (`scripts/rotas_redacao.py`), com as regras da seção 5.6 e corpo de salvamento de até 128 KB. `/api/integracao` anuncia `conferencia_redacao: true` e `entrevistas: true`.

| Operação (`POST /api/…`) | Corpo | Resposta 200 |
|---|---|---|
| `redacao-listar` | `{caso}` | `{caso, textos: [{id, sha256, titulo, versao, resumo, atualizado_em_utc}], total, divergentes}` |
| `redacao-conferir` | `{caso, id}` | Visão acima. |
| `redacao-dividir` | `{caso, texto}` | `{caso, afirmacoes: [{inicio, fim, texto, tipo}]}`; não grava. |
| `redacao-criar` | `{caso, requisicao_id, autor, observacao?, titulo, texto}` | Visão. |
| `redacao-nova-versao` | `{…, id, anterior_sha256, texto?, titulo?}` | Visão. |
| `redacao-vincular` | `{…, id, anterior_sha256, afirmacao_id, evidencias}` | Visão. |
| `redacao-revisar` | `{…, id, anterior_sha256, afirmacao_id, decisao, observacao_revisao?}`; exige conta | Visão. |
| `entrevistas-lacunas` | `{caso}` | `{caso, lacunas: [{origem, motivo, evidencias, pergunta_id, situacao}], total, aviso}` |
| `entrevistas-listar` / `-detalhe` | `{caso}` / `{caso, id}` | Pergunta(s) com evidências conferidas, diligência e fonte de cada resposta. |
| `entrevistas-preparar` | `{…, origem, tipo, destinatario, responsavel, prazo?}` | Pergunta. |
| `entrevistas-editar` | `{…, id, anterior_sha256, pergunta}` | Pergunta. |
| `entrevistas-responder` | `{…, id, anterior_sha256, situacao, resposta?, observacao_resposta?}`; `resposta` tem os campos de `caderno.salvar` | Pergunta. |
| `entrevistas-exportar` | `{caso, ids, formato?}` | Markdown acima. |

Códigos novos em `scripts/erros.py`, traduzidos em `i18n_en.js`: `revisao_humana_sem_conta`, `afirmacao_inexistente`, `afirmacao_sem_suporte_vinculado`, `redacao_sem_alteracao`, `redacao_texto_invalido`, `redacao_afirmacoes_demais`, `revisao_humana_invalida`, `vinculos_afirmacao_invalidos`, `lacuna_origem_mudou`, `pergunta_origem_invalida`, `contato_tipo_invalido`, `resposta_sem_fonte`, `resposta_situacao_invalida`, `resposta_fonte_invalida`, `pergunta_sem_alteracao`, `pedido_destinatario_misto` e `exportacao_selecao_invalida`.

Testes: `python -m unittest discover -s testes -p "test_conferencia_redacao.py"` e `-p "test_entrevistas.py"`. As pastas `casos/<caso>/quadros/redacao/` e `quadros/perguntas/` ficam na categoria `quadros_evidencia` do apagamento (seção 6).

## 6. Armazenamento e apagamento

- Os quadros ficam em `casos/<caso>/quadros/{hipoteses,linha_do_tempo,entidades,relacoes,tabelas}/`.
- No alcance do apagamento (`scripts/apagamento.py`), essa pasta é a categoria `quadros_evidencia`, com rótulo na interface (`interface/gerenciar.js` e `i18n_en.js`).
- Apagar uma rodada ou uma conversa não apaga os quadros. Os vínculos para a rodada apagada passam a sair como `indisponivel`.
- Para retirar um item cuja fonte foi apagada, use `retirado: true` com motivo. Nesse caso, os vínculos indisponíveis são preservados como estão (`preservar_indisponiveis`).

## 7. O que outros agentes podem e não podem mudar

**Podem, sem passar pelo Core:**

- consumir a API pública da seção 5 e as formas JSON das seções 2–5;
- criar rotas HTTP, telas, exportações e relatórios que leiam os quadros ou chamem `salvar`;
- acrescentar testes que só usem a API pública e dados sintéticos;
- montar novos quadros sobre `evidencias.Colecao`, `vinculos` e `conferir_vinculos`, num módulo próprio e com nome de coleção novo.

**Não podem, sem passar pelo Core:**

- alterar os campos, os valores ou as regras das referências, dos vínculos, da resolução e dos retornos (seções 2–5), inclusive `PAPEIS`, `SUPORTES`, `NATUREZAS`, `TIPOS_DATA`, `TIPOS_ID` e `DECISOES`;
- gravar diretamente em `casos/<caso>/quadros/`, editar ou apagar eventos, ou contornar a trava ou o encadeamento por hash;
- aceitar uma evidência como texto livre, ou um vínculo sem resolução contra o original;
- marcar uma situação, relação ou homônimo de forma automática, a partir de modelo ou heurística;
- fundir entidades;
- chamar modelo ou rede a partir de `evidencias`, `hipoteses`, `linha_tempo`, `comparador` ou `mapa_relacoes`;
- mudar a assinatura das funções privadas reaproveitadas pelo Core (seção 5.1) sem avisar o Core.

**Prefixos de ID (registro do Core, 2026-11-19).** Cada prefixo tem um só significado na equipe:

| Prefixo | Forma | Uso |
|---|---|---|
| `D` | `D###` | documento cadastrado do caso |
| `W` | `W###` | documento capturado da web (fase 07); mesmo espaço dos `D###`, aparece nas citações |
| `E` | E-ID | evidência dos achados |
| `R` | `R###` | rodada |
| `N` | `N` + 32 hex | registro do caderno |
| `G` | `G` + 32 hex | diligência |
| `H`, `T`, `P`, `L`, `Q` | letra + 32 hex | hipótese, evento da linha do tempo, entidade, relação, tabela |
| `C` | `C` + 32 hex | texto conferido do quadro `redacao` (fase 08) |
| `F` | `F` + 32 hex | afirmação dentro de um texto conferido |
| `J` | `J` + 32 hex | pergunta do quadro `perguntas` |

Decisão: `W` fica com as capturas web, porque é ID de documento visível na citação ("W001 · linhas 7–7"). O quadro `redacao` troca o prefixo de `W` para `C` antes da integração da fase 08. Prefixo novo exige registro nesta tabela.

**Como pedir uma mudança no contrato:** consultar o agente Core (`maestro-cli ask lapidacao/core-evidencias "…"`) ou deixar o pedido no playbook do Core. Toda mudança de forma sobe `ESQUEMA` ou é estritamente aditiva (campo opcional novo), atualiza este arquivo e entra com testes em `testes/test_quadros_evidencia.py`. Mudança incompatível nunca é feita em silêncio.

## 8. Verificação

- `python scripts/demo_evidencias.py`: demonstração sem argumentos, rede ou modelo.
- `python -m unittest discover -s testes -p test_quadros_evidencia.py -v`: testes do contrato.
- `python -m unittest discover -s testes -p test_demo_evidencias.py -v`: teste da demonstração.
- `python -m unittest discover -s testes -p test_rotas_evidencia.py -v`: testes das rotas HTTP da Mesa.
- `python -m unittest discover -s testes -p test_tabelas_apuracao.py -v`: testes das tabelas de apuração e de suas rotas.

Status: publicado — commit 621e8b0 (621e8b0c23d61c58d3c10fae232d836afa8e306e, branch lapidacao/core-evidencias)
