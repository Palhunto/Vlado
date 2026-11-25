# 05 - Briefing com evidências e limites

Usar a pergunta e os achados revisados, sem acrescentar fatos novos. Preservar vínculo até as passagens originais. Salvar em `08_briefing.md` um briefing de até 600 palavras, salvo pedido diferente, contendo:

1. Rodada, versão do corpus, pergunta e resposta direta no alcance permitido.
2. Achados sustentados, cada um com fonte e localizador próximos da afirmação.
3. Alegações atribuídas e inferências claramente separadas, quando forem relevantes.
4. Divergências comparáveis, citando os dois lados e o limite da comparação.
5. Lacunas, partes não consultadas e diligências necessárias.
6. Limite da revisão assistida e estado da conferência humana.

Não exigir um número mínimo de achados ou ações. Não preservar uma afirmação apenas para reutilizar todas as citações. Se não houver evidência suficiente, responder que não é possível estabelecer a conclusão com o material consultado e indicar o que falta.

Atualizar `registro.json` apenas com etapas e ferramentas realmente observadas, arquivos criados e condições da execução. Não inventar tempo, contagem de tokens, modelo, custo ou aprovação. Diferenciar duração registrada por relógio de estimativa subjetiva.

## Vincular briefing e publicar para consulta

Usar somente as versões revisadas do registro estruturado. Próximo de cada afirmação incluída, citar `[A001@v2]` (ID e versão reais), E-ID, documento e localizador. Essa marca identifica uma redação com suporte `sustentado`; não usar a marca de inclusão em pendências, redações parciais, retiradas ou sem revisão própria. Descrever pendências com seu ID por extenso e classificação, sem apresentá-las como fatos estabelecidos.

Preparar `achados_briefing_r3.json`, revisão `r3_sintese`, autossuficiente e ligada por hash à revisão assistida. Cada revisão tem uma só sucessora: numa rodada feita pela Mesa de apuração, a síntese já foi publicada como `r3_sintese`, e não se publica uma segunda síntese na mesma rodada; uma pergunta nova cria uma rodada nova. Rodadas antigas com a revisão `r3_briefing` continuam válidas e são lidas como estão. Preservar o histórico e acrescentar artefato do briefing com hash, procedência `sintese` e eventos de destino para as versões exatas: `incluido`, `pendencia`, `retirado` ou `substituido`. Na inclusão, informar caminho do briefing e `revisao_suporte`, posição a partir de 1 do evento de revisão assistida que sustenta essa redação. Nos outros destinos, briefing e revisão de suporte são `null`. Se uma nova revisão invalidar inclusão anterior, acrescentar retirada/substituição; conservar o briefing antigo e produzir novo arquivo. Se nada tiver suporte, registrar insuficiência e não criar inclusões artificiais.

Publicar o candidato com `achados.py registrar`, conferir o recibo e construir explicitamente `python scripts/achados.py construir --caso CASO --rodada RODADA --revisao r3_sintese --geracao g1`. Conferir também `achados.py verificar` com esses seletores. Se a geração já existir, escolher ID novo; nunca sobrescrever. Falha na indexação deixa os registros preservados, mas não autoriza anunciar consulta pronta no banco/interface.

No chat, apresentar o resultado e links dos artefatos, revisão/geração disponíveis e limitações de publicação, se houver. Terminar com **Aguardando conferência humana ou nova pergunta.** Não iniciar outra investigação automaticamente.
