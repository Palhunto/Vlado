# 05 - Briefing com evidências e limites

Usar a pergunta e os achados revisados, sem acrescentar fatos novos. Preservar vínculo até as passagens originais. Salvar em `08_briefing.md` um briefing com texto principal de até 600 palavras, salvo pedido diferente, com fonte e localizador próximos de cada afirmação. Ele começa pela rodada, a versão do corpus e a pergunta, e segue estas seções, nesta ordem, escolhendo o que entra por relevância editorial e não pela ordem dos achados:

1. "Premissa da pergunta": o que a pergunta supõe e se o corpus confirma, contraria ou não trata disso, com fonte. Uma premissa contrariada é dita antes da resposta.
2. "Resposta direta": responde a cada parte da pergunta, inclusive ao porquê, no alcance que o corpus permite.
3. "Contexto": o estado do procedimento (definitivo ou não, recursos cabíveis e efeito), quem decidiu e como votou quando o corpus diz, o que a decisão não tratou e a data-base dos valores.
4. "Outro lado": para cada pessoa ou entidade a quem um achado atribui conduta ou responsabilidade, a manifestação ou defesa que está no corpus, com fonte, e se a decisão a acolheu, ou "não localizada no corpus"; e quem ouvir, por papel.
5. "Números": para cada valor central, a escala contra uma referência do corpus, os componentes que somam o total, o período, a moeda ou data-base e o recálculo das contas da peça com os operandos citados (operandos = resultado).
6. "Lacunas e diligências": partes não consultadas e, para cada pendência, o destinatário, o meio e o que pedir, sem exigir motivo do requerente; o limite da revisão assistida e o estado da conferência humana.

Uma seção que não se aplica à pergunta diz "não se aplica" e o motivo. Manter separadas as alegações atribuídas, as inferências e as divergências comparáveis, com os dois lados e o limite da comparação. Todo número, data, valor ou quantificador forte ("todos", "tudo", "integralmente") do texto vem do achado citado; a ressalva de alcance parcial de um achado não some no briefing.

Um achado sustentado que não coube no texto principal não é retirado: vai para a seção "Outros achados sustentados", depois do texto principal e fora da conta das 600 palavras, numa linha com o ID e a versão por extenso (A008 v1), a afirmação em uma frase e a fonte do suporte.

Não exigir um número mínimo de achados ou ações. Não preservar uma afirmação apenas para reutilizar todas as citações. Se não houver evidência suficiente, responder que não é possível estabelecer a conclusão com o material consultado e indicar o que falta.

Atualizar `registro.json` apenas com etapas e ferramentas realmente observadas, arquivos criados e condições da execução. Não inventar tempo, contagem de tokens, modelo, custo ou aprovação. Diferenciar duração registrada por relógio de estimativa subjetiva.

## Vincular briefing e publicar para consulta

Usar somente as versões revisadas do registro estruturado. Próximo de cada afirmação incluída, citar `[A001@v2]` (ID e versão reais), E-ID, documento e localizador. Essa marca identifica uma redação com suporte `sustentado`; não usar a marca de inclusão em pendências, redações parciais, retiradas ou sem revisão própria. Descrever pendências com seu ID por extenso e classificação, sem apresentá-las como fatos estabelecidos.

Preparar `achados_briefing_r3.json`, revisão `r3_sintese`, autossuficiente e ligada por hash à revisão assistida. Cada revisão tem uma só sucessora: numa rodada feita pela Mesa de apuração, a síntese já foi publicada como `r3_sintese`, e não se publica uma segunda síntese na mesma rodada; uma pergunta nova cria uma rodada nova. Rodadas antigas com a revisão `r3_briefing` continuam válidas e são lidas como estão. Preservar o histórico e acrescentar artefato do briefing com hash, procedência `sintese` e eventos de destino para as versões exatas: `incluido`, `fora_do_briefing` (o sustentado da lista "Outros achados sustentados", sem a marca de inclusão), `pendencia`, `retirado` ou `substituido`. Na inclusão e no `fora_do_briefing`, informar caminho do briefing e `revisao_suporte`, posição a partir de 1 do evento de revisão assistida que sustenta essa redação. Nos outros destinos, briefing e revisão de suporte são `null`. `retirado` é só do achado derrubado na revisão, nunca do sustentado que não coube. Se uma nova revisão invalidar inclusão anterior, acrescentar retirada/substituição; conservar o briefing antigo e produzir novo arquivo. Se nada tiver suporte, registrar insuficiência e não criar inclusões artificiais.

Publicar o candidato com `achados.py registrar`, conferir o recibo e construir explicitamente `python scripts/achados.py construir --caso CASO --rodada RODADA --revisao r3_sintese --geracao g1`. Conferir também `achados.py verificar` com esses seletores. Se a geração já existir, escolher ID novo; nunca sobrescrever. Falha na indexação deixa os registros preservados, mas não autoriza anunciar consulta pronta no banco/interface.

No chat, apresentar o resultado e links dos artefatos, revisão/geração disponíveis e limitações de publicação, se houver. Terminar com **Aguardando conferência humana ou nova pergunta.** Não iniciar outra investigação automaticamente.
