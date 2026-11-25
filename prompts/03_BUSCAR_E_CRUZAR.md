# 03 - Buscar, extrair e cruzar evidências

Executar somente consultas sobre os arquivos autorizados da rodada. Usar busca textual para nomes, identificadores e expressões; complementar com leitura contextual e visual quando disponível. Busca por palavras não prova cobertura semântica completa do acervo.

Para texto indexado, usar `python scripts/banco.py buscar --caso CASO --rodada RODADA --consulta-arquivo entrada/consulta.txt`, preenchendo os IDs reais e salvando a consulta literal nesse arquivo, sem interpolar texto do usuário em código de shell. O modo padrão `comum` combina termos com AND e preserva frases entre aspas. `--modo fts` aceita operadores FTS5 explícitos; `--modo literal` pesquisa substring exata, com distinção de maiúsculas, acentos e pontuação, útil para identificadores. Variantes e sinônimos exigem buscas adicionais registradas; o banco não os infere.

Cada execução devolve JSON e salva seu retorno bruto em arquivo novo em `saidas/consultas_sqlite`. Registrar em `03_buscas.md` o caminho informado em `arquivo_log`, a geração/identidade do índice, consulta efetiva e limites. Conferir total de correspondências, `truncado` e `proximo_deslocamento`; quando necessário, repetir com `--deslocamento` para obter outros resultados. Um retorno `erro_consulta` é erro de ferramenta, não busca sem evidências.

Para ler o contexto integral da unidade, executar `python scripts/banco.py ler --caso CASO --rodada RODADA --referencia REFERENCIA` com o identificador devolvido. Os caminhos de fonte são relativos à pasta da rodada e apontam para `entradas`. Conferir original quando a interpretação depender de tabela/imagem ou houver suspeita de extração incorreta. Linhas de uma cópia de trabalho não são linhas nativas do PDF. A unidade de um texto simples é o próprio arquivo, sem página PDF inventada.

Se o índice estiver ausente, usar `banco.py construir` somente sobre o snapshot dessa rodada; gerações existentes nunca são sobrescritas. Para reconstrução necessária, escolher `--geracao v2` (ou outro ID novo) e informar a mesma geração em todas as operações seguintes. Não reconstruir para esconder divergência de hash nem alterar entradas congeladas. Registrar indisponibilidade, geração escolhida e leituras diretas realmente realizadas.

Registrar em `03_buscas.md` as consultas realmente executadas, ferramenta utilizada, arquivos/páginas consultados, resultados úteis e lacunas. Não inventar um log de buscas que não ocorreram. O relatório tem duas seções obrigatórias:

- "Cobertura": cada documento candidato do plano, lido ou com a exclusão justificada. Antes de declarar algo fora do corpus ou não localizado, cruzar as listas de anexos e as referências das próprias peças com a cobertura e dizer onde procurou.
- "Contraverificação": para cada conclusão ou fundamento central, as buscas feitas pelo que o contraria (ônus da prova, normas do próprio emissor, contradições internas da peça, origem dos dados), registradas também quando não acharam nada. A evidência contrária entra com papel `contradicao`.

Quando o corpus tiver mais de um processo ou procedimento sobre a mesma matéria, procurar se o mesmo documento, parecer ou fundamento aparece em mais de um deles e comparar os desfechos. Um mesmo fundamento com desfechos diferentes é registrado como cruzamento, com os dois lados, a chave que os liga (identificador, data, emissor, versão) e o que muda entre os processos; a diferença de desfecho não prova irregularidade. Se uma ferramenta não puder ler um formato, registrar o impedimento e tentar um derivado autorizado ou pedir a entrada necessária.

Salvar a geração inicial em `04_evidencias_brutas.md`. Para cada passagem: ID E001 etc.; documento; página/campo/linhas observáveis; trecho curto literal; atribuição; contexto; relação com a pergunta; limitação de leitura. Não alterar silenciosamente uma transcrição de OCR. Quando houver divergência visual, registrar a leitura observada e a origem da diferença.

Salvar em `05_cruzamentos_brutos.md`: afirmação ou pista A001 etc.; evidências dos dois lados; chave que permite relacioná-los; o que coincide; o que diverge; diferença de contexto/versão; classificação documental/alegação/inferência/pendente; verificação necessária. Não chamar diferença de contexto de contradição sem demonstrar comparabilidade.

Ao calcular, preservar os operandos e a operação com referências e unidades. Se não houver suporte, manter a lacuna. Não inferir campos faltantes para fechar uma tabela. Não repetir buscas por obrigação; ampliar a consulta quando uma necessidade concreta continuar sem resposta.

Antes de revisar, confirmar que as saídas iniciais foram efetivamente gravadas. Se não houver permissão de gravação, entregar a saída no chat e informar que o operador precisa preservá-la; não afirmar que foi salva.

## Registro estruturado obrigatório da geração inicial

Ler `docs/ACHADOS_IA.md` e o contrato `modelos/ACHADOS.schema.json`. Produzir os dados estruturados durante a busca/cruzamento, usando os mesmos IDs A001/E001 dos relatórios brutos; não extraí-los retrospectivamente do briefing. Os scripts não fazem inferência nem capturam o chat.

Salvar um JSON candidato novo em `execucoes/CASO/RODADA/saidas/achados_busca_r1.json`, com caso/rodada e hash real de `snapshot.json`, `revisao: r1_busca`, `anterior: null`, evidências, vínculos por versão da redação e procedência da etapa `busca`. Identificar os relatórios brutos nos artefatos com hashes atuais e os IDs correspondentes; preencher ferramentas/modelo somente quando observados, usando `null` para modelo desconhecido. `conferencias_humanas` começa vazio; verificação externa permanece não realizada no corpus fechado. Uma pista sem evidência tem natureza `pendencia`.

Para evidência indexada, guardar original/fonte/hashes e a geração, identidade, hash do banco e referência devolvidos por `banco.py`; o localizador precisa corresponder ao intervalo realmente lido. Para leitura direta/visual, usar somente original/derivado do snapshot e localizador suportado pelo guia; se a ferramenta não validar o formato/localização, conservar a pista como pendência, sem fabricar referência.

Executar `python scripts/achados.py registrar --caso CASO --rodada RODADA --arquivo execucoes/CASO/RODADA/saidas/achados_busca_r1.json`, substituindo os IDs. Conferir recibo `publicado_sem_indice` e preservar seu hash da revisão. Corrigir candidatos em arquivos novos em caso de falha. Não iniciar a revisão antes da publicação inicial confirmada. Sem achados, publicar conjunto vazio e os relatórios de busca com seus limites.
