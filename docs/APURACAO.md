# Aba Apuração

A aba **Apuração** reúne notas editáveis do caso escolhido. As notas são humanas; seleções de achados da IA mantêm essa identificação. Salvar uma nota não cria rodada, não chama o modelo e não aprova nenhuma conclusão.

## Escrever e reunir evidências

1. Abra **Apuração**, confira o caso e clique em **Nova nota**. Preencha título e texto e use **Salvar nota**. O salvamento é explícito; a tela indica alterações ainda não salvas.
2. O texto usa o **Vditor**, em português, começando em **Edição visual**. A barra oferece títulos, negrito, itálico, riscado, links, listas, tarefas, citações, separadores, tabelas e desfazer/refazer. Em **Alternar modo de edição**, escolha **Renderização instantânea** ou **Markdown e prévia**. O conteúdo continua salvo como Markdown; notas anteriores abrem sem migração. O editor sanitiza HTML e a prévia adicional da Mesa continua usando o renderizador seguro das respostas.
3. Reabra uma nota pela lista para editar. **Reabrir notas salvas** consulta o disco. Os dados sobrevivem a recargas do navegador e reinícios do serviço. Ao trocar de nota/caso ou recarregar com alterações pendentes, a interface alerta para o descarte.
4. Na pesquisa documental, selecione texto dentro do trecho e use **Adicionar à apuração**. Escolha uma nota existente ou crie outra. Sem seleção, entra o trecho completo mostrado. A operação salva imediatamente a seleção e suas referências.
5. Na ficha de um achado da IA, o mesmo botão permite copiar a redação selecionada ou completa, com os documentos vinculados àquela versão. Cada evidência textual tem também seu próprio botão. O texto da seleção é conferido contra a origem no backend. A evidência visual sem transcrição acompanha as referências do achado; não se inventa um trecho para ela.
6. Na nota, combine suas observações com as citações inseridas. As referências preservadas aparecem abaixo do editor, com documento, caso, rodada, versão do achado, página PDF quando disponível ou linhas/localização. **Abrir fonte original** abre a cópia preservada após conferir seu hash.

Se houver uma nota com alterações não salvas, salve ou descarte essas alterações antes de adicionar uma evidência. Se outra janela modificar o caderno, o salvamento com revisão antiga é recusado e o rascunho permanece na tela: copie-o, reabra os dados salvos e incorpore sua edição. Não há mesclagem automática.

## Exportar

**Exportar caderno salvo** inclui todas as notas do caso, em ordem de criação, com referências separadas por nota. O botão fica indisponível enquanto o texto tem alterações não salvas.

- **Markdown:** texto UTF-8 com a marcação original e referências legíveis.
- **PDF:** arquivo PDF real, paginado, com fontes incorporadas, acentos e quebra de caminhos longos.
- **DOCX editável:** documento OOXML real, com parágrafos, títulos, negrito, itálico, listas e links. O conteúdo é texto editável, sem capturas de tela ou conversão de HTML disfarçada.

As referências incluem a seleção preservada, o nome e ID do documento, página/localização, caso, rodada, versão/índice, caminho do original dentro do projeto e SHA-256. Os arquivos exportados não incorporam os documentos originais nem concedem acesso a eles: o caminho exige a cópia do projeto correspondente. A numeração de fontes recomeça em cada nota.

## Preservação e limites

As revisões completas ficam em `casos/<id>/apuracao/revisoes/<numero>.json`, publicadas atomicamente sem sobrescrever revisões anteriores. A leitura usa a última revisão. Editar ou excluir uma nota só publica uma revisão desse caderno; documentos, snapshots, saídas da IA e contribuições humanas anteriores não são modificados. A exclusão remove a nota da versão corrente; as revisões anteriores permanecem no disco, sem restauração individual na interface.

O **Caderno da apuração** anterior continua disponível para contribuições imutáveis, cruzamentos, contexto de perguntas e diligências. Não há migração automática entre ele e a aba Apuração. As notas editáveis não são enviadas automaticamente ao modelo e não entram no índice documental.

Limites desta entrega: título de até 200 caracteres, nota de até 200 mil caracteres, seleção de até 12 mil caracteres e estado corrente de até 8 MB. O salvamento é automático por nota, com rascunho na aba e conflito explícito (ver `CADERNO_APURACAO.md`); a autoria vem da conta autenticada. Não há colaboração simultânea com mesclagem, reordenação de notas, incorporação de imagens, OCR ou anexação de documentos aos arquivos exportados. A exportação formata o subconjunto básico do editor; tabelas, Markdown aninhado complexo e outros recursos da prévia não têm fidelidade garantida no PDF/DOCX. Caracteres fora da cobertura das fontes PDF, como alguns emojis, podem não renderizar.

O Vditor 4.0.1 e seus recursos essenciais ficam em `interface/vendor/vditor`, com licença MIT e manifesto de procedência e hashes. O editor não depende de CDN, cache de rascunhos do Vditor, serviços de upload ou renderizadores externos de diagramas/fórmulas. Esses blocos permanecem como código. A política de segurança da Mesa continua restringindo scripts e conexões à própria origem. Se algum arquivo essencial não carregar, a tela avisa e oferece o campo Markdown para continuar a edição e o salvamento.

Editar ou apagar a citação no texto não apaga a seleção preservada nas referências; isso permite conferir a origem após a edição. Referências cuja rodada esteja na lixeira ou cujo arquivo esteja ausente continuam legíveis, mas o download da fonte pode falhar com aviso.

PDF e DOCX exigem `reportlab` e `python-docx`, declarados em `requirements.txt`. O diagnóstico do iniciador verifica essas dependências no Python que executará o serviço. Dependência ausente também produz mensagem explícita na exportação. O backend já aberto precisa ser encerrado e reaberto para carregar o código novo; confira antes se não há execução ativa.

## Verificação reproduzível

`testes/test_apuracao.py` cobre persistência, edição/exclusão com histórico, conflitos, isolamento entre casos, seleções inválidas, reenvio idempotente, integridade das fontes, sessão HTTP e arquivos de exportação. `testes/qa_apuracao.py` e `.cjs` exercitam a interface com documentos sintéticos, incluindo reinício de um servidor de teste independente. As evidências ficam em `docs/qa_apuracao/`; não são documentos da apuração nem avaliação editorial.
