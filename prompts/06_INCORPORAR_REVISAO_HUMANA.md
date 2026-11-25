# 06 - Incorporar retorno humano

Executar somente quando o usuário informar uma conferência real. Registrar em `09_retorno_humano.md` o retorno literal ou sua referência, quem conferiu se informado, fontes consultadas se informadas e decisões por afirmação. Ausências permanecem como não informadas.

Separar confirmação, correção, descarte e pendência. Não chamar silêncio, aprovação do formato ou pedido de continuidade de validação factual. Não generalizar a conferência de um campo para o documento inteiro.

Produzir uma nova versão do briefing, por exemplo `10_briefing_revisado_v2.md`, com histórico das alterações e referências. Manter a geração inicial e a revisão assistida intactas. Material de avaliação preenchido pertence ao avaliador e não deve entrar em outra sessão de geração principal.

Acrescentar uma revisão estruturada nova do conjunto, ligada à anterior por revisão/hash. Registrar `conferencias_humanas` somente para A-ID/versão e alcance realmente conferidos, com retorno literal ou referência, decisão, responsável e fontes quando informados; campos desconhecidos permanecem `null`/lista vazia. Um retorno parcial não confirma a redação inteira e não transfere confirmação a versões novas.

Acrescentar procedência `retorno_humano`, artefato/hash do retorno e decisões de destino. Correções na redação exigem nova versão, fontes reabertas e revisão assistida própria antes de inclusão em novo briefing. Associar os hashes dos novos relatórios/briefings; não editar os antigos. Publicar, construir uma geração nova e verificar com `achados.py`, conforme o guia. Na Mesa de apuração, a conferência humana também é feita na tela, pelas pessoas da redação (revisão humana dos achados e conferência da redação), nunca pelo modelo. O agente de chat não registra conferência pela tela nem a simula: ele registra, pelo fluxo assistido acima, só o retorno que o usuário efetivamente trouxe.
