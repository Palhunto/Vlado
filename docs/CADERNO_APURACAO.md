# Caderno da apuração

Para notas com edição/exclusão, Markdown e exportação em PDF/DOCX, use a nova [aba Apuração](APURACAO.md). Este guia descreve o caderno anterior de contribuições imutáveis, preservado para cruzamentos, perguntas e diligências.

O caderno guarda contribuições humanas separadas dos achados produzidos pela IA. Cada registro identifica apuração, versão documental, documento e hash, localização observada, trecho, anotação, data e autor declarado. Esta versão não autentica individualmente o autor.

## Registrar uma passagem

1. Abra **Caderno da apuração**, selecione a apuração e escolha **Adicionar ao caderno da apuração**. Também há esse botão junto às fontes da pesquisa, dos achados e da conversa: selecionar texto dentro da passagem preenche somente essa seleção.
2. Confira o original. Em PDF, informe a página física do arquivo; em outros formatos, informe linhas, células ou outra localização observável.
3. Escolha trecho ou achado, dê um título e identifique a autoria. Achados exigem anotação humana.
4. Salve. O cadastro do caderno não cria rodada, índice ou chamada ao modelo.

O extrator procura o trecho na página do PDF ou no arquivo textual. Se não o localizar, o formulário exige a declaração explícita de transcrição manual após conferir o original. O registro conserva essa limitação. Localizar literalmente um trecho não valida sua interpretação. Os originais permanecem disponíveis para download.

## Cruzar e perguntar

Selecione de dois a vinte registros e use **Criar cruzamento humano**. Escreva a relação e identifique seu autor; os registros e as autorias anteriores continuam vinculados. A exportação JSON inclui somente a seleção explícita, com suas fontes.

Para levar de um a vinte registros a uma pergunta, selecione o destino e clique em **Usar selecionados numa pergunta**. A prévia pode ser retirada; apenas enviar a pergunta inicia a análise. O backend revalida IDs, hashes e fontes e salva `saidas/caderno_recebido.json` na nova rodada. As contribuições acompanham cada etapa, como contexto humano para reexame, sem aprovação automática ou inclusão no índice documental.

Fontes ausentes do corpus da conversa exigem **Continuar com novos documentos**, ou uma nova conversa sobre os documentos cadastrados. Os próximos complementos não recebem novamente os registros por seleção automática; a conversa pode conservar o contexto anterior, indicado nos metadados.

## Preservação

Registros novos ficam em `casos/<id>/caderno/registros/`; suas origens documentais ficam em `caderno/origens/`. Os registros desta área são imutáveis. Reenviar a mesma tentativa não duplica a contribuição; outra tentativa com conteúdo diferente exige novo registro. Falhas de integridade não são apresentadas como caderno vazio. A edição e exclusão individual de notas são oferecidas separadamente na aba Apuração.

Cada contribuição pode originar uma [diligência](DILIGENCIAS.md). O acompanhamento conserva a distinção entre autoria humana e resultado da IA.

## Notas da aba Caderno: salvamento, rascunho e edição

As notas editáveis (aba **Caderno**, área `#area-apuracao`) são gravadas somente por `apuracao-nota-salvar`, com a revisão da nota (`revisao_nota`). O estado aparece ao lado do título da nota:

- **Alterações não salvas** → **Salvando…** → **Nota salva às HH:MM**. "Nota salva" só aparece depois da resposta 200 do servidor com a revisão nova.
- **Sem conexão. Rascunho guardado nesta aba; tentando de novo…** quando a rede falha. O mesmo pedido (mesma `requisicao_id`) é reenviado em intervalos crescentes, e de imediato quando o navegador avisa que voltou a conexão.
- **Conflito**: a nota mudou em outra aba ou janela. O salvamento automático para, nada é sobrescrito e a tela oferece copiar o texto e recarregar.
- **Sessão expirada. Entre de novo; o rascunho continua nesta aba.** O salvamento para até a próxima entrada.

### Rascunho na aba (sessionStorage)

Uma nota pode conter material de reportagem inédito. Por isso o rascunho local fica **apenas na `sessionStorage` da aba atual**: some ao fechar a aba ou o aplicativo, não passa para outras abas e nunca vai para `localStorage`, IndexedDB ou cookie.

- Chave `vlado:rascunho:<conta>:<caso>:<nota>` (no modo local, `<conta>` é `local`). O valor guarda título, texto, `revisao_base` (a revisão sobre a qual o texto foi escrito), a hora e, se havia um salvamento a caminho, o texto enviado.
- É gravado a cada mudança ainda não confirmada (digitação, colagem, troca de estilo, marcar ou desmarcar tarefa, referência inserida) e apagado quando o servidor confirma o salvamento, quando a nota é excluída, quando a pessoa descarta as alterações e no logout (o botão Sair chama `window.limparRascunhosCaderno()`).
- Ao reabrir a nota (por exemplo, depois de recarregar a aba durante uma falha de rede): rascunho igual ao texto salvo é apagado sem perguntar; rascunho sobre a mesma revisão é oferecido com **Restaurar rascunho** ou **Descartar rascunho**, e a edição espera a escolha; rascunho sobre revisão anterior (a nota mudou no servidor) é tratado como conflito, com o texto local na tela para copiar.
- Se o navegador bloquear a `sessionStorage`, o caderno continua salvando no servidor; só não há rascunho.

### Estilos e tarefas

- O seletor de estilo mostra o estilo do bloco onde está o cursor: **Texto normal** (parágrafo), **Título da seção** (`##`) e **Subtítulo** (`###`). Níveis antigos (`#`, `####` a `######`) aparecem como "Cabeçalho n (legado)" e só mudam quando a pessoa escolhe outro estilo. O título da nota continua no campo próprio. No modo Markdown, o seletor fica desativado: escreva `##` e `###`.
- **Negrito**, **Itálico**, **Lista** com marcadores e **Lista de tarefas** ficam à mão; os demais comandos e a troca entre edição visual e Markdown ficam em **Mais**.
- Tarefas são gravadas como `- [ ] ` e `- [x] `. A caixa marca e desmarca por clique, toque ou teclado (Espaço na caixa focada, Espaço logo depois da caixa, ou Ctrl+Enter em qualquer ponto do item), sem mover o cursor; a mudança segue o salvamento automático. A barra da nota mostra "n de m tarefas concluídas".
- Abrir o original a partir de uma fonte e fechá-lo devolve o cursor e a rolagem ao mesmo ponto da nota. No celular, a nota fica em primeiro plano; a lista (com busca) e as fontes abrem em gavetas.

### Verificação

```
node --test testes/caderno_rascunho.cjs testes/caderno_notas.cjs testes/caderno_estilo.cjs testes/editor_sob_demanda.cjs
python testes/qa_caderno_editor.py --modulos-node .ferramentas/node/node_modules --saida %TEMP%\qa_caderno_editor --capturas docs/capturas/caderno --chrome "C:/Program Files/Google/Chrome/Application/chrome.exe"
```

O segundo comando sobe um servidor local temporário (modo local, dados sintéticos, sem chamada de modelo) e confere no Chrome sem janela: a caixa da tarefa (alinhamento, alvo de 44 px, clique, toque e teclado, gravação sem digitação, recarga e ida e volta visual↔Markdown), os estilos e níveis legados, o rascunho após falha de rede simulada e recarga, o conflito entre duas abas, a volta ao ponto da edição depois do original, 320 e 390 px sem rolagem horizontal e os temas claro e escuro. As capturas em `docs/capturas/caderno/` usam apenas dados sintéticos.
