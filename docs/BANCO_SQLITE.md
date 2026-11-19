# Uso do índice SQLite/FTS5

Índice documental da versão operacional **1.3.0**, esquema do banco **1**, implementação do índice **1.0.0**. Recupera e permite conferir passagens das entradas congeladas. Não inclui extração automática de entidades/campos, embeddings ou validação factual pelo banco.

## Funcionamento

Depois de uma pergunta real, `nova_rodada.py` congela os arquivos e constrói o índice padrão `v1`. Usa somente originais e derivados autorizados nas entradas congeladas; não consulta o manifesto de trabalho para responder à rodada. Erro de construção impede publicar uma rodada parcial. Cadastro e seleção de caso não indexam nem iniciam apuração.

```text
execucoes/<caso_id>/<rodada>/
  entradas/                         # fontes autorizadas preservadas
  snapshot.json                     # hashes das entradas, sem o índice
  indice/v1/
    apuracao.sqlite                 # derivado reconstruível
    manifesto.json                  # entradas, regras, cobertura e hash do banco
  saidas/consultas_sqlite/
    <identificador_unico>.json      # retorno bruto de busca/leitura/cobertura
```

Cada banco pertence a um caso e uma rodada. Não há banco global nem índice de trabalho mutável nesta entrega. A geração é um nome como `v1` ou `v2`; reconstruir exige nome novo e não sobrescreve o anterior.

## Comandos

Para consultar sem escrever comandos, use a [interface de pesquisa](INTERFACE_PESQUISA.md), aberta por `Iniciar pesquisa.cmd`. Ela usa as mesmas operações e logs abaixo, com seleção explícita de caso/rodada/geração.

Executar na pasta do projeto online. Os nomes abaixo são ilustrativos: não criam caso ou rodada automaticamente.

```powershell
python scripts/banco.py cobertura --caso minha_apuracao --rodada R001
python scripts/banco.py buscar --caso minha_apuracao --rodada R001 --consulta-arquivo entrada/consulta.txt
python scripts/banco.py ler --caso minha_apuracao --rodada R001 --referencia HASH_DEVOLVIDO_NA_BUSCA
python scripts/banco.py verificar --caso minha_apuracao --rodada R001
```

Salvar a consulta como UTF-8 em `entrada/consulta.txt` antes de executar, sem interpolar conteúdo recebido como código de shell. `--consulta-arquivo` é relativo ao projeto e restrito a `entrada/`. A CLI também admite `--consulta` para texto simples fornecido como argumento corretamente citado pelo operador.

| Modo de busca | Comportamento | Exemplo de conteúdo do arquivo |
| --- | --- | --- |
| `comum` (padrão) | Todos os termos; aspas preservam frases. Operadores escritos viram termos comuns | `"prazo de entrega" aditivo` |
| `fts` | Sintaxe FTS5 explícita, sem geração de SQL livre | `"prazo de entrega" OR prorrog*` |
| `literal` | Substring exata, distingue caixa, acentos e pontuação | `AB-123/2026` |

Opções: `--modo`, `--documentos D001 D002`, `--pagina 2` (posição física PDF reconhecida no derivado), `--limite 10` (de 1 a 50), `--deslocamento 10` e `--geracao v1`. Resultados são blocos de texto, com possível sobreposição; total não é contagem de fontes independentes. O modo literal não normaliza identificadores.

O retorno informa consulta recebida/efetiva, filtros, caso/rodada/geração, identidade lógica e hash do banco, cobertura, total, resultados, truncamento e próximo deslocamento. Cada passagem contém referência estável, original e fonte textual com hashes, método, página quando observável e linhas. Caminhos de fontes e logs são relativos à pasta da rodada. `ler` devolve a unidade inteira: página extraída ou arquivo textual.

O JSON bruto é salvo em arquivo novo, inclusive com zero resultados ou erro de consulta. Relacionar `arquivo_log` a `03_buscas.md` e ao inventário. `estado=erro_consulta` causa código de saída 2. Índice ausente, trocado ou com hash divergente também causa código 2; não vira resultado vazio. `verificar` é diagnóstico sem log de busca. JSONs de saída e logs usam UTF-8.

## Construção explícita e reconstrução

```powershell
python scripts/banco.py construir --caso minha_apuracao --rodada R001
python scripts/banco.py construir --caso minha_apuracao --rodada R001 --geracao v2
```

O primeiro comando serve para rodada existente sem índice; recusa substituir `v1`. O segundo cria outra geração. Informar `--geracao v2` nas consultas/leitura/verificação seguintes. Reconstrução equivalente preserva referências e identidade lógica; o arquivo SQLite pode ter hash diferente. O banco é reconstruído das entradas e possui manifesto próprio.

`indice_sqlite: true` habilita construção na criação de rodadas. `nova_rodada.py --sem-indice` permite congelar sem banco diante de limitação técnica; registrar motivo e usar leitura direta autorizada. Configurações antigas sem `indice_sqlite` mantêm o comportamento anterior. Indexar rodada antiga não altera seus prompts, snapshot ou saídas.

Antes de cada operação, a ferramenta verifica autorização congelada, pertencimento dos caminhos ao caso, hashes das fontes, identidade do índice e hash do SQLite. Abre consultas somente para leitura, sem criar banco vazio. A verificação completa confere estrutura, chaves estrangeiras e correspondência entre trechos e FTS. Isso não protege contra alguém que possa reescrever simultaneamente fontes e manifestos.

## Cobertura e localizadores

- `.txt` e `.md` em UTF-8: linhas do arquivo, sem página física inventada.
- Derivado Markdown no formato produzido por [extrair_pdf.py](../scripts/extrair_pdf.py): páginas físicas e linhas da cópia. Cabeçalhos técnicos não entram na busca. Hash de origem deve corresponder ao original; páginas/linhas devem estar em sequência. Incoerências geram erro de leitura na cobertura, sem indexar localizadores duvidosos.
- Derivados de DOCX e XLSX produzidos por [extrair_office.py](../scripts/extrair_office.py) (adaptadores `markdown_docx_v1` e `markdown_xlsx_v1`): uma unidade por seção (`## D001 - documento`, `cabecalho 1`, `notas de rodape`, `aba Plan1` etc.), sem página física. Cada linha mantém o localizador da fonte no texto indexado. Na busca, o resultado traz `formato`, `localizadores` (todas as linhas do trecho), `localizador_inicio`/`localizador_fim` e, nos modos `comum` e `literal`, `localizadores_com_termo` (linhas cujo conteúdo contém algum termo, por comparação simples; conferir no original). `ler` acrescenta `localizador` a cada linha da unidade. `linha_inicio`/`linha_fim` são posições na cópia de trabalho; a citação no original é o localizador (`P0001`, `T01 L02 C03`, `Aba!B3`). Hash de origem divergente, célula de outra aba ou linha sem localizador deixam a fonte inteira em `erro_leitura`.

  | Localizador | Origem | Exemplo |
  |---|---|---|
  | `P0001` | parágrafo do corpo do DOCX, em ordem | `[P0012] texto` |
  | `T01 L02 C03` | célula de tabela do DOCX (tabela, linha, coluna da grade) | `[T01 L02 C03] 1.250,00` |
  | `CAB1 P0001` / `ROD1 P0001` | parágrafo de cabeçalho ou rodapé N | `[CAB1 P0001] Ofício nº 12` |
  | `NOTA n P0001` / `NOTAFIM n P0001` | parágrafo da nota de rodapé ou nota final `n` | `[NOTA 1 P0001] Fonte: …` |
  | `COMENT n P0001` | parágrafo do comentário `n` | `[COMENT 3 P0001] conferir` |
  | `Aba!A1` | célula preenchida do XLSX; aba entre aspas quando o Excel exigiria (`'Folha 1'!B3`) | `[Plan1!B3] 2345.5 \|\| exibido: 2,345.50 \|\| formula: SUM(B1:B2)` |
  | `L0001` | linha do derivado de OCR de imagem | `[L0004] texto reconhecido` |

  No XLSX, a linha traz o valor gravado, o valor exibido (só para formato numérico simples, com separadores do formato do Excel, como `2,345.50` ou `12.5%`, e datas em `AAAA-MM-DD`) e a fórmula como texto, sem avaliar. O índice não recalcula fórmulas nem confere valores; um número achado na busca é conferido na célula do original.
- Derivado de OCR de imagem avulsa (`--ocr-imagens`, adaptador `markdown_ocr_imagem_v1`): uma unidade `## D001 - imagem` com linhas `[L0001]`; o resultado traz `origem_texto: ocr` e `aviso_ocr`.
- Esses adaptadores só reconhecem derivados novos; `REGRAS` e `IMPLEMENTACAO` não mudaram, de modo que índices de rodadas anteriores continuam verificáveis e a reconstrução de PDF e texto dá o mesmo resultado.
- Outros formatos (PDF, imagem, planilha CSV/TSV, DOCX/XLSX com macro, senha ou corrupção): o original é inventariado sem adaptador textual. DOCX e XLSX legíveis entram pelo derivado acima, nunca pelo original. O cadastro agora prepara e autoriza automaticamente derivados paginados de PDFs (texto nativo e, nas páginas digitalizadas, OCR local; a origem de cada página fica no manifesto e no cabeçalho do derivado); o banco pesquisa esses derivados, não o PDF diretamente. PDFs sem camada textual e imagens continuam exigindo OCR ou leitura visual; o banco não executa OCR. Rodadas anteriores à preparação mantêm sua cobertura original.
- Páginas com falha de extração usam o marcador `[ERRO DE EXTRACAO NESTA PAGINA]`: ficam com estado `erro_leitura`, sem indexar o aviso como conteúdo documental. Páginas vazias permanecem `sem_texto`. Os detalhes da falha são preservados no recibo e no manifesto.
- Texto vazio, página sem texto e UTF-8 inválido: condições explícitas por fonte/unidade. Um documento pode ser pesquisável por derivado mesmo que seu original não tenha adaptador.

Blocos têm até quarenta linhas, sobreposição de quatro e não atravessam páginas. Linhas longas são preservadas inteiras; o limite é por linhas. FTS usa `unicode61 remove_diacritics 2`, sem stemming, BM25 e desempate por referência estável. FTS normaliza caixa/acentos e separa pontuação; confirmar identificador exato com modo literal e original. Frases/substrings que ultrapassem blocos podem exigir outra busca e leitura do contexto completo.

Tabelas: `metadados`, `documentos`, `fontes` (originais e derivados com vínculo), `unidades`, `trechos` e `trechos_fts`. Trechos/FTS são preenchidos na mesma transação; o diretório só é publicado depois das verificações. Referências dependem de caso, documento/versão, fonte textual e intervalo; IDs internos não são citações públicas.

O assistente formula consultas e interpreta resultados. SQLite recupera registros com origem. O modelo continua online, a revisão humana permanece necessária e ausência na busca não prova ausência no acervo.

## Verificação técnica

[test_indice_sqlite.py](../testes/test_indice_sqlite.py) usa materiais sintéticos temporários para conferir cadastro/snapshot/índice, isolamento, versões, reconstrução, localizadores, falhas, busca, cobertura e CLI em cópia com caminho diferente. Não é piloto editorial.

```powershell
python scripts/montar_fluxo.py --check
python scripts/verificar_projeto.py
python -m unittest discover -s testes -v
```
