---
type: reference
title: Contrato dos quadros da Onda 4 (sugestões da IA, vínculo, seletor e comparação entre processos)
created: 2026-11-27
tags: [contrato, evidencias, quadros, onda4]
related: ['[[CONTRATO_EVIDENCIA]]']
---

# Contrato dos quadros da Onda 4

Servidor: Viga. Tela: Lume. Decisões do dono P45 (a IA sugere candidatos, cada um preso a uma evidência publicada) e P47 (seletor comum de evidência e preenchimento do vínculo). Especificação da tela em `docs/design/componentes.md#quadros-onda4`. Este contrato completa o `CONTRATO_EVIDENCIA.md` e não muda nada dele: **a referência da evidência não muda de formato** (seção 2 daquele contrato).

Exemplos com dados sintéticos (Vila Serena, Construtora Alfa, Marta Reis, Carlos Prado, Contrato 041/2025, Ana Lima). Hashes encurtados (`…`).

## 0. Regras que valem para tudo

- **Rodadas e itens antigos abrem como sempre.** Todo campo novo é opcional na leitura (seção 7). Rodada sem candidatos devolve lista vazia; vínculo salvo antes desta onda volta sem `revisao_ia` e sem `alteracoes` (a tela não deduz nada).
- **Erros** seguem o padrão de sempre: HTTP 400 com `erro` (português), `codigo` e, quando houver, `parametros`. Os códigos novos estão na seção 6. Permissão continua no portão: sem a capacidade, a resposta é a de hoje (`operacao_proibida`, 403); não há `sem_permissao` à parte.
- **Capacidades.** Leituras novas (`sugestoes-listar`, `evidencia-buscar`, `comparar-processos`) ficam na linha `L`/LEITURA dos quadros; as ações (`sugestoes-confirmar`, `-corrigir`, `-descartar`, `-restaurar`) na linha `E`/MESA, a mesma de `hipoteses-criar` e dos outros `*-criar`/`*-atualizar`. Linhas novas em `autorizacao.py` e `rotas_evidencia.py` dependem do aval da Tranca (o Maestro repassa).
- **Idempotência.** Toda ação leva `requisicao_id` (32 hex), como nos quadros: repetir com o mesmo id e o mesmo conteúdo devolve o mesmo resultado; com outro conteúdo, `tentativa_reutilizada`.

## 1. Formato do candidato (MESA.md e prompt 05)

A IA entrega os candidatos na síntese, numa chave opcional `candidatos` ao lado de `texto` e `destinos`. A chave só é aceita em rodadas congeladas com `VERSAO_MESA` 1.3.0 ou depois (nas outras, continua "Campos não autorizados"). No agente de chat (prompt 05), o mesmo conteúdo vai em `saidas/achados/candidatos/r3_sintese.json`.

```json
{"candidatos": [
  {"chave": "C1", "tipo": "organizacao", "achado_id": "A001", "evidencias": ["E001"],
   "campos": {"nome": "Construtora Alfa Ltda.", "variantes": ["Construtora Alfa"]}},
  {"chave": "C2", "tipo": "pessoa", "achado_id": "A002", "evidencias": ["E003"],
   "campos": {"nome": "Marta Reis", "variantes": []}},
  {"chave": "C3", "tipo": "ligacao", "achado_id": "A002", "evidencias": ["E003"],
   "campos": {"de": "C2", "para": "C1", "tipo": "sócia", "descricao": "Sócia-administradora segundo o contrato social."}},
  {"chave": "C4", "tipo": "acontecimento", "achado_id": "A001", "evidencias": ["E001"],
   "campos": {"descricao": "Assinatura do Contrato 041/2025 entre a Prefeitura de Vila Serena e a Construtora Alfa",
              "datas": [{"tipo": "assinatura", "valor": "2025-03-03", "aproximada": false, "fonte": 0, "observacao": ""}]}},
  {"chave": "C5", "tipo": "hipotese", "achado_id": "A002", "evidencias": ["E003"],
   "campos": {"enunciado": "A sócia da contratada assinou o contrato também como testemunha."}}
]}
```

| Campo | Regra |
|---|---|
| `chave` | `C1` a `C999`, única na lista. Só serve para a ligação apontar as pontas. |
| `tipo` | `pessoa`, `organizacao`, `ligacao`, `acontecimento`, `hipotese`. Tabela não recebe candidato. |
| `achado_id` | achado publicado nesta rodada. Vale qualquer destino; o destino é guardado e mostrado (retirado e pendência nascem como na seção 3.3). |
| `evidencias` | de 1 a 5 E-IDs, cada um ligado a esse achado nos vínculos publicados. Ligação e acontecimento exigem ao menos uma com papel `suporte`. |
| `campos` | pessoa e organização: `nome` (até 300), `variantes` (até 20, cada uma até 300). Ligação: `de` e `para` (chaves de pessoa ou organização desta lista, diferentes), `tipo` (até 120), `descricao` (até 2.000, pode ser vazia). Acontecimento: `descricao` (até 1.000), `datas` (1 a 10; `tipo` de `linha_tempo.TIPOS_DATA`, `valor` AAAA, AAAA-MM ou AAAA-MM-DD, `aproximada`, `fonte` = posição em `evidencias`, padrão 0, `observacao` até 500). Hipótese: `enunciado` (até 1.000). |
| limite | até 40 candidatos por rodada. |

Sem identificadores (CPF, CNPJ) no candidato: dado pessoal fica para a pessoa digitar em "Corrigir". A IA nunca preenche situação de hipótese nem decisão de homônimo.

**Validação no servidor** (`scripts/sugestoes_quadros.py`, sem modelo). A lista malformada (não é lista, mais de 40, chave repetida) recusa a síntese, e o modelo corrige na tentativa seguinte. Um candidato com referência inválida (achado ou E-ID fora da rodada, E-ID que não é do achado, ponta que não existe, campo fora do limite) é **recusado sozinho**: não vira sugestão e fica registrado com o código em `recusados`; o briefing não cai por causa dele. Os aceitos e os recusados vão para `saidas/achados/candidatos/r3_sintese.json` da rodada (imutável, preso por `registros_sha256` à revisão `r3_sintese`). A leitura confere tudo de novo, também nos arquivos do agente de chat.

## 2. Sugestões

Uma sugestão é um candidato aceito, com identidade estável `S` + 32 hex (hash do caso, da rodada, do `registros_sha256` e da chave). As decisões das pessoas ficam em `casos/<caso>/quadros/sugestoes/<S-id>/` como eventos encadeados, no mesmo modelo dos quadros.

### 2.1 `POST /api/sugestoes-listar` (leitura)

Pedido: `{"caso": "vila-serena", "quadro": "mapa" | "linha_tempo" | "hipoteses", "incluir_decididas": false}`. Junta as sugestões de todas as rodadas do caso com candidatos, da mais recente para a mais antiga. Sem `incluir_decididas`, vêm as abertas e as descartadas (para "Descartadas (n)"); as confirmadas só com `true`.

```json
{"caso": "vila-serena", "quadro": "mapa",
 "contagem": {"abertas": 3, "descartadas": 1},
 "sugestoes": [{
   "id": "S4b1c…e2", "tipo": "ligacao", "quadro": "mapa",
   "campos": {"origem": null, "destino": "P9a0f…11", "tipo": "sócia",
              "descricao": "Sócia-administradora segundo o contrato social.",
              "evidencias": [{"referencia": {"tipo": "ia", "caso_id": "vila-serena", "rodada": "R002",
                                             "revisao": "r3_sintese", "registros_sha256": "7c1d…", "evidencia_id": "E003"},
                              "papel": "suporte", "suporte": "sustentado", "natureza": "declaracao_documental",
                              "justificativa": "O contrato social lista Marta Reis como sócia-administradora."}]},
   "pontas": {"origem": {"sugestao_id": "S77aa…01", "estado": "aberta", "item_id": null, "nome": "Marta Reis"},
              "destino": {"sugestao_id": "S0c3e…9f", "estado": "confirmada", "item_id": "P9a0f…11", "nome": "Construtora Alfa Ltda."}},
   "evidencias": [{"referencia": {"…": "a mesma de campos.evidencias[0]"}, "estado": "conferida",
                   "documento": {"documento_id": "D002", "nome": "contrato_social_alfa.pdf"},
                   "localizador": {"tipo": "linhas", "pagina_pdf": 1, "linha_inicio": 12, "linha_fim": 14,
                                   "descricao": "", "legivel": "D002 · página PDF 1 · linhas 12–14"},
                   "trecho": "Marta Reis, sócia-administradora…",
                   "revisao_ia": {"…": "seção 3.1"}, "conferencia_humana": null}],
   "achado": {"id": "A002", "versao": 1, "redacao": "Marta Reis é sócia-administradora da Construtora Alfa.",
              "natureza": "declaracao_documental", "suporte_ia": "sustentado",
              "destino": "incluido", "motivo_destino": "…", "versao_atual": 1},
   "analise": {"caso": "vila-serena", "rodada": "R002", "revisao": "r3_sintese", "registros_sha256": "7c1d…",
               "em_utc": "2026-11-26T17:32:00+00:00", "pergunta": "Quem são os sócios da contratada?"},
   "estado": "aberta", "decisao": null, "descartada_antes": null,
   "bloqueio": "ponta_ainda_sugestao", "avisos": []
 }]}
```

| Campo | Significado |
|---|---|
| `campos` | o item no formato do `*-criar` do quadro, pronto para enviar (sem `caso` e `requisicao_id`). Pessoa e organização: `{tipo, nome, variantes, identificadores: [], evidencias}`; ligação: `{origem, destino, tipo, descricao, evidencias}` (ponta ainda não confirmada vem `null`); acontecimento: `{descricao, datas, evidencias, retirado: false, motivo_retirada: ""}`; hipótese: `{enunciado, situacao: "em_aberto", lacunas: [], evidencias}`. Os vínculos vêm preenchidos pela P47 (seção 3.3). |
| `pontas` | só na ligação: por ponta, a sugestão de origem, o estado dela, o item confirmado (P-ID) e o nome. |
| `evidencias` | cada evidência resolvida como em `conferir_vinculos` (`estado` `conferida` ou `indisponivel`, com `erro`), mais `revisao_ia` e `conferencia_humana` (seção 3.2). |
| `achado` | o achado de origem na revisão da sugestão; `versao_atual` é a última versão do achado na rodada (maior que `versao` quando foi substituída). |
| `analise` | a análise de origem: caso, rodada, revisão, hash, data e a pergunta (até 300 caracteres). |
| `estado` | `aberta`, `confirmada`, `descartada`. |
| `decisao` | `null` ou `{acao: "confirmar"|"corrigir"|"descartar"|"restaurar", por, conta_id, em_utc, item_id, quadro, alterados: ["nome", "variantes", …]}` (`alterados` só no corrigir: os campos do item que a pessoa mudou em relação à sugestão). |
| `descartada_antes` | `null` ou `{sugestao_id, rodada, por, em_utc}`: outra sugestão com o mesmo tipo, os mesmos campos (nome normalizado) e a mesma evidência (documento, hash do original, localizador e trecho) foi descartada; esta nasce `descartada`, sem decisão própria. |
| `bloqueio` | `null` ou o código que impede "Confirmar" agora (seção 6, os seis primeiros). "Corrigir" e "Descartar" não têm bloqueio além da permissão. |
| `avisos` | lista de `analise_sem_revisao`, `achado_retirado`, `versao_substituida`, `evidencia_indisponivel` (texto da tela em #avisos-vinculo). `fora_do_briefing` não é aviso: vem em `achado.destino`. |

`contagem` nunca entra na contagem de itens do quadro.

### 2.2 Ações

Todas: `{"caso", "id": "S…", "requisicao_id", "autor"?}` (o `autor` só no modo sem contas, como nos quadros). Resposta: `{"sugestao": <objeto da 2.1>, "item": <detalhe do item criado ou null>}`.

| Rota | Pedido a mais | O que faz |
|---|---|---|
| `sugestoes-confirmar` | nada | cria o item com `campos` exatamente como listados e marca a sugestão `confirmada`. Recusa com o código de `bloqueio` se houver. Hipótese nasce `em_aberto`. |
| `sugestoes-corrigir` | `"campos": {…}` no formato do `*-criar` do quadro | cria o item com os campos enviados (as regras do quadro valem inteiras, inclusive trocar a ponta por uma entidade já no mapa) e marca `confirmada` com `acao: corrigir` e `alterados`. Os vínculos guardam `alteracoes` por campo (seção 3.1). Não sofre os bloqueios de suporte (a pessoa troca a evidência); a ponta ainda sugestão continua bloqueando se ficar como está (`origem`/`destino` `null`). |
| `sugestoes-descartar` | nada | marca `descartada`. Sem diálogo; desfaz-se com restaurar. |
| `sugestoes-restaurar` | nada | volta a `aberta` (também a nascida `descartada` por `descartada_antes`). Nunca cria item. |

Confirmada não volta: confirmar ou corrigir de novo responde `sugestao_ja_decidida`; descartar uma confirmada também. O item criado depois se edita no quadro, como qualquer item.

## 3. Registro do vínculo (aditivo em `scripts/evidencias.py`)

### 3.1 Campos novos no vínculo salvo (opcionais)

```json
{"referencia": {"tipo": "ia", "…": "…"}, "papel": "suporte", "suporte": "parcial", "natureza": "declaracao_documental",
 "justificativa": "…", "documento_id": "D002", "original_sha256": "…", "localizador": {"…": "…"},
 "revisao_ia": {"rodada": "R002", "revisao": "r3_sintese", "registros_sha256": "7c1d…", "achado_id": "A002", "versao": 1,
                "papel": "suporte", "suporte": "sustentado", "natureza": "declaracao_documental", "destino": "incluido"},
 "alteracoes": {"suporte": {"anterior": "sustentado", "valor": "parcial", "por": "Ana Lima", "conta_id": "c…",
                            "em_utc": "2026-11-26T19:10:00+00:00"}}}
```

- `revisao_ia`: só em referência `ia`, calculado pelo servidor ao ligar (nunca aceito do cliente): o vínculo do achado publicado com essa E-ID (a versão mais nova que a tem), o suporte da última revisão assistida dessa versão (`nao_revisado` sem revisão), a natureza da versão e o destino dessa versão na revisão (`null` em revisão sem síntese).
- `alteracoes`: por campo (`papel`, `suporte`, `natureza`), a última mudança feita por pessoa: valor anterior, valor novo, quem e quando. Calculado pelo servidor a cada salvamento, comparando o enviado com o valor de antes (no vínculo novo, com o preenchimento P47 da seção 3.3). Voltar ao valor da IA apaga a marca do campo. No vínculo do caderno, `alteracoes.suporte` é "quem escolheu o suporte e quando" (anterior `nao_revisado`).
- O cliente nunca envia `revisao_ia` nem `alteracoes`: vêm de volta no detalhe. Um vínculo salvo é reenviado como hoje (forma salva, com os campos novos, se tiver) ou na forma de entrada.

### 3.2 Campos novos no vínculo resolvido (leitura, calculados agora)

Em toda leitura que já resolve vínculos (`*-detalhe`, `hipoteses-quadro`, `linha-tempo-listar`, `mapa-ver`), cada vínculo ganha:

| Campo | Significado |
|---|---|
| `revisao_ia` | o guardado (seção 3.1) ou `null` (vínculo antigo ou do caderno). |
| `alteracoes` | o guardado ou `{}`. |
| `conferencia_humana` | `null` ou `{estado, por, em_utc}` da marca humana do achado dessa evidência na rodada (`conferida_no_original`, `precisa_de_ajuste`, `sem_suporte_suficiente`, `pendente`). |
| `suporte_so_da_ia` | `true` quando há `revisao_ia`, o suporte é o dela, não há `alteracoes.suporte` e `conferencia_humana.estado` não é `conferida_no_original`. |
| `destino_atual` | destino do achado na revisão mais recente da rodada (pode diferir do guardado). |
| `versao_nova` | `null` ou `{referencia, achado_id, versao, revisao_ia}` quando há versão mais nova do achado na rodada: é o que "Ligar a versão nova" envia. |

### 3.3 Preenchimento P47 (o mesmo no seletor, nas sugestões e no cálculo de `alteracoes`)

| Origem | papel | suporte | natureza |
|---|---|---|---|
| achado da IA | o do vínculo publicado | o da última revisão | a da versão |
| achado da IA com destino `retirado` | o do vínculo | **`nao_revisado`** | a da versão |
| achado da IA em análise sem revisão de suporte | o do vínculo | `nao_revisado` | a da versão |
| papel `contexto` | `contexto` | `nao_revisado` | a da versão |
| natureza `pendencia` com suporte `sustentado` (o validador da revisão não deixa, mas a regra fica) | o do vínculo | `nao_revisado` | `pendencia` |
| fonte do caderno | `suporte` (a pessoa muda) | `nao_revisado` | sem preenchimento (a tela exige; o servidor mantém o padrão de hoje, `pendencia`, para não quebrar cliente antigo) |

Mudar o suporte de um achado retirado para `sustentado` é escolha da pessoa e fica em `alteracoes`; só então conta como base da hipótese e da linha contínua do mapa.

### 3.4 Operações sobre o vínculo

Não há rota nova: "Voltar ao da IA" (enviar o valor de `revisao_ia` no campo), "Ligar a versão nova" (trocar a `referencia` pela de `versao_nova`, com os valores de `versao_nova.revisao_ia`) e "Desligar" (tirar o vínculo da lista) são o `*-atualizar` do quadro, como hoje. A confirmação antes de apagar revisão humana é da tela; o servidor não recusa nenhuma dessas três por haver revisão humana.

## 4. Seletor comum de evidência

### `POST /api/evidencia-buscar` (leitura)

Pedido:

```json
{"caso": "vila-serena", "texto": "Marta", "origem": "tudo", "rodada": null,
 "item": {"quadro": "relacoes", "id": "L5d2…aa"}, "limite": 20, "deslocamento": 0}
```

`texto` vazio ou com 2 a 500 caracteres (procura no texto do achado, no trecho e no nome do documento, sem diferenciar maiúsculas e acentos); `origem` `tudo`, `ia` ou `caderno`; `rodada` `null` (a análise mais recente com achados) ou um `R…` desta apuração; `item` opcional (`quadro` `hipoteses`, `linha_tempo`, `entidades`, `relacoes`), para marcar o que já está ligado; `limite` 1 a 50.

```json
{"caso": "vila-serena",
 "analise": {"rodada": "R002", "revisao": "r3_sintese", "registros_sha256": "7c1d…", "em_utc": "2026-11-26T17:32:00+00:00",
             "pergunta": "Quem são os sócios da contratada?", "com_revisao": true},
 "analises": [{"rodada": "R002", "…": "…"}, {"rodada": "R001", "…": "…"}],
 "total": 2, "proximo_deslocamento": null,
 "resultados": [
  {"origem": "ia", "tipo_fonte": "achado_ia", "texto": "Marta Reis é sócia-administradora da Construtora Alfa.",
   "trecho": "Marta Reis, sócia-administradora…", "documento": {"documento_id": "D002", "nome": "contrato_social_alfa.pdf"},
   "localizador": {"legivel": "D002 · página PDF 1 · linhas 12–14", "…": "…"},
   "achado": {"id": "A002", "versao": 1, "destino": "incluido"},
   "revisao_ia": {"…": "seção 3.1"}, "conferencia_humana": {"estado": "conferida_no_original", "por": "Ana Lima", "em_utc": "…"},
   "vinculo_sugerido": {"referencia": {"tipo": "ia", "…": "…"}, "papel": "suporte", "suporte": "sustentado",
                        "natureza": "declaracao_documental", "justificativa": "O contrato social lista…"},
   "ja_ligado": false},
  {"origem": "caderno", "tipo_fonte": "trecho", "texto": "Anotação de Ana Lima sobre o termo aditivo",
   "trecho": "…", "documento": {"documento_id": "D004", "nome": "termo_aditivo_1.pdf"},
   "localizador": {"legivel": "D004 · página PDF 2", "…": "…"}, "achado": null, "revisao_ia": null,
   "conferencia_humana": null, "conferencia_textual": "literal_localizado",
   "vinculo_sugerido": {"referencia": {"tipo": "humana", "…": "…"}, "papel": "suporte", "suporte": "nao_revisado",
                        "natureza": null, "justificativa": ""},
   "ja_ligado": false}]}
```

- Resultado da IA: um por par (evidência, achado) na revisão mais recente da rodada escolhida; a referência aponta essa revisão. No caderno: um por fonte de registro (`trecho`, `achado`, `cruzamento`), com `conferencia_humana: null` (o caderno não tem marca "Conferida no original"; a tela mostra "A conferir") e a `conferencia_textual` da fonte num campo à parte, só informativo. Na IA, `conferencia_textual` não vem.
- Cada resultado traz `estado` (`conferida` ou `indisponivel`, com `erro`), como em `conferir_vinculos`; o indisponível não é ligável.
- `vinculo_sugerido` é o preenchimento da seção 3.3. No caderno, `natureza` vem `null` e `justificativa` vazia: a pessoa preenche.
- Só a apuração aberta: `rodada` de outro caso ou na lixeira é recusada; nada fora de `casos/<caso>` e `execucoes/<caso>`.

## 5. Comparação entre processos

**Caminho escolhido: os campos estruturados entram neste passo**, numa entrega depois das sugestões e do seletor (seção 8). Até lá vale a exceção declarada da especificação (fundamento, dois lados e veredito da IA, sem "O que muda").

Formato no `MESA.md` (bloco `formato:revisao`, chave opcional `comparacoes`, só a partir de `VERSAO_MESA` 1.3.0), porque as seis conferências são resultado da revisão:

```json
{"comparacoes": [{"achado_id": "A004",
  "chave": {"identificador": "Parecer jurídico nº 12/2025", "data": "2025-02-10", "emissor": "Procuradoria de Vila Serena", "versao": "única"},
  "lados": [{"processo": "Processo 2025/118 · Contrato 041/2025", "fundamento": "E007", "questao": "Validade da dispensa",
             "fase": "primeira instância", "desfecho": "Dispensa considerada regular", "desfecho_evidencia": "E008"},
            {"processo": "Processo 2025/201 · Contrato 052/2025", "fundamento": "E009", "questao": "Validade da dispensa",
             "fase": "recurso", "desfecho": "Dispensa anulada", "desfecho_evidencia": "E010"}],
  "conferencias": {"versao": "mesmo", "data": "mesmo", "emissor": "mesmo", "trecho": "diferente",
                   "questao": "mesmo", "fase": "diferente"}}]}
```

Cada conferência é `mesmo`, `diferente` ou `a_conferir`. Os E-IDs têm de ser do achado. A leitura:

`POST /api/comparar-processos` `{"caso", "rodada": null | "R…"}` →
`{"caso", "analise": {…como na seção 4}, "estruturada": true, "comparacoes": [{"achado": {…}, "chave": {…}, "lados": [{"processo", "fundamento": <evidência resolvida>, "questao", "fase", "desfecho", "desfecho_evidencia": <evidência resolvida>}], "conferencias": {…}, "mesmo_arquivo": true|false, "pendente": true|false, "revisao_ia": {…}}]}`.

`mesmo_arquivo` é a comparação dos hashes dos originais dos dois fundamentos (feita pela Mesa). `pendente` segue a regra do topo da especificação (veredito diferente de sustentado, natureza ou destino pendência, ou alguma conferência diferente de `mesmo`). Em rodada sem os campos, `estruturada: false` e `comparacoes: []`; a tela não reconstrói do texto.

## 6. Códigos de recusa novos

| Código | Quando | Onde |
|---|---|---|
| `ponta_ainda_sugestao` | confirmar ligação com uma ponta ainda sugestão aberta (`parametros.ponta`: `origem` ou `destino`) | confirmar, corrigir sem trocar a ponta |
| `ponta_descartada` | a ponta está em Descartadas | idem |
| `achado_retirado` | o achado da evidência tem destino `retirado` | confirmar |
| `versao_substituida` | há versão mais nova do achado na rodada | confirmar |
| `nao_sustentado` | o veredito da última revisão é `nao_sustentado` | confirmar |
| `ilegivel` | o veredito da última revisão é `ilegivel` | confirmar |
| `evidencia_indisponivel` | a rodada foi apagada ou a evidência não resolve mais | confirmar, corrigir com a mesma evidência |
| `sugestao_ja_decidida` | a sugestão já foi confirmada (ou o estado não admite a ação) | confirmar, corrigir, descartar, restaurar |
| `sugestao_inexistente` | `S-id` que não existe nesta apuração | ações |
| `quadro_sugestao_invalido` | `quadro` fora de `mapa`, `linha_tempo`, `hipoteses` | listar |
| `busca_curta` | `texto` com 1 caractere | evidencia-buscar |
| `item_selecionado_invalido` | `item` com quadro ou id inválido, ou que não existe | evidencia-buscar |
| `rodada_sem_achados` | `rodada` pedida sem achados publicados nesta apuração (ou malformada) | evidencia-buscar |
| `vinculo_contexto_com_suporte` | papel `contexto` com suporte diferente de `nao_revisado` (hoje sem código) | todo `*-criar`/`*-atualizar` |
| `vinculo_pendencia_sustentada` | natureza `pendencia` com suporte `sustentado` (hoje sem código) | idem |
| `vinculos_demais` | mais de 100 evidências no item (`parametros.maximo`: 100) | idem |
| `candidatos_invalidos` | a lista `candidatos` da síntese malformada (é para o modelo; a tela não vê) | síntese |

A referência inválida continua `referencia_evidencia_invalida`, e os que já existem (`evidencia_ausente`, `evidencia_original_mudou`, `registro_mudou`, `tentativa_reutilizada`, `quadro_em_uso`…) não mudam. Cada código novo entra com a linha em inglês no `interface/i18n_en.js` no mesmo commit do servidor (senão `testes/erros_en.cjs` fica vermelho); o Lume revisa o texto depois do merge.

## 7. Opcionais na leitura

Tudo o que é novo: `revisao_ia`, `alteracoes`, `conferencia_humana`, `suporte_so_da_ia`, `destino_atual` e `versao_nova` nos vínculos; nas sugestões, `pontas` (só ligação), `decisao`, `descartada_antes`, `bloqueio` e `avisos` podem vir `null`/vazios; `comparar-processos` com `estruturada: false`. Rodada sem `saidas/achados/candidatos/` devolve `sugestoes: []` e `contagem` zerada. Nenhum campo antigo muda de nome, de tipo ou de sentido.

## 8. Ordem de entrega (branch `lancamento/plataforma-o2`)

1. Vínculo (seção 3) e `evidencia-buscar` (seção 4), com os três códigos de regra do modelo.
2. Candidatos no `MESA.md` e no prompt 05, validação na síntese e `saidas/achados/candidatos/r3_sintese.json` (seção 1), `VERSAO_MESA` 1.3.0.
3. `sugestoes-listar` e as quatro ações (seção 2), mapa e linha do tempo primeiro, hipóteses no mesmo commit.
4. Comparação entre processos (seção 5).
5. À parte: R1 e N2 da L5 (conferência do briefing), com a correção da Coruja.

Os hashes vão ao Lume e ao Maestro a cada entrega. Rotas em `rotas_evidencia.py` e linhas em `autorizacao.py`: com o aval da Tranca.
