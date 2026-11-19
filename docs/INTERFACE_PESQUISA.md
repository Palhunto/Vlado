# Interface de pesquisa documental

Interface da versão 1.4.0, com cadastro anterior à pergunta, extração textual de PDFs, conversa com os documentos e consulta aos achados estruturados. A Mesa de apuração separa cadastro, busca documental e conferência de achados, com leitura do briefing junto às fontes. Usa Python e navegador, com `pypdf` para extração; a análise online é feita pela API do provedor configurado, conforme a integração descrita em [INTEGRACAO_API.md](INTEGRACAO_API.md).

## Abrir

No Windows, dê dois cliques em **Iniciar pesquisa.cmd**, na pasta do projeto. O iniciador seleciona um Python com SQLite/FTS5 e extrator de PDF disponíveis, verificando `.venv`, runtime do Codex e depois `python`/`py -3`. Mantenha o terminal aberto durante o uso; encerre com `Ctrl+C`. Use `Iniciar pesquisa.cmd --verificar-runtime` para conferir o interpretador e as dependências sem iniciar o serviço.

Ou execute na pasta do projeto:

```powershell
python scripts/interface_pesquisa.py
```

O navegador abre em [Pesquisa documental](http://127.0.0.1:8765). Se a porta estiver ocupada, use `--porta 8766`; `--sem-abrir` inicia sem abrir o navegador. O servidor escuta somente em `127.0.0.1`, no próprio computador. A análise por IA é feita online, pela API do provedor configurado, somente depois do envio de uma pergunta.

## Usar

Na aba **Apuração**, mantenha notas editáveis do caso escolhido, acrescente seleções da pesquisa documental ou dos achados da IA e exporte o caderno em Markdown, PDF ou DOCX editável. A área anterior **Caderno da apuração** mantém seus registros imutáveis e sua integração com perguntas/diligências. Consulte [APURACAO.md](APURACAO.md). O iniciador agora confere também `python-docx` e `reportlab`, de `requirements.txt`, para oferecer as exportações.

Em **Cadastrar documentos**, escolha uma apuração existente ou informe apenas o nome de uma nova apuração (por exemplo, “Americanas — fatos relevantes”), selecione os arquivos e clique em **Enviar e cadastrar agora**. O identificador é gerado internamente; não há campo de slug para preencher. Cada envio produz recibo de todos os arquivos e inventário acumulado, incluindo duplicatas. É possível acrescentar outros lotes sem pergunta ou rodada. Consulte limites, falhas e preservação no [guia de cadastro](CADASTRO_DOCUMENTOS.md). Depois abra **Perguntar ao Codex** e escolha a apuração pelo nome. O guia **Como começar**, no menu, explica essa sequência sem bloquear o uso.

Quando um caso ativo tiver PDFs pendentes ou com falha de extração, **Preparar PDFs pendentes** tenta preparar o texto das cópias já preservadas e publica novo recibo. Não é necessário selecionar arquivos novamente. Originais e rodadas antigas permanecem intactos. Um aviso único indica quando a instância não tem extrator, e os detalhes do Python ficam recolhidos em **Detalhes técnicos**.

## Leitura e apresentação

O primeiro lote de correções de usabilidade preserva as abas e a identidade visual. **Reconectar acompanhamento** recupera apenas a observação da execução existente; rascunhos são separados por apuração/conversa, com destino indicado e aviso antes de sair da página. Consulte o [funcionamento e os limites dos rascunhos](INTEGRACAO_API.md#recuperação-do-acompanhamento-e-rascunhos).

As seleções de observações dos achados atuam somente nos próprios controles: limpar ou atualizar essa seleção não modifica as caixas nem as seleções internas do caderno ou dos formulários de diligências. Localizadores estruturados são apresentados pelos campos existentes, como descrição, aba, tabela, célula ou região. Se não houver localização legível, aparece **localizador não informado**, sem inferir posição.

Em uma conversa concluída, **Continuar com novos documentos** cadastra outro lote e mostra uma prévia da versão ampliada. Escolher essa versão e enviar a próxima pergunta mantém a conversa, cria outra rodada e acrescenta um comparativo com a última resposta concluída. Os complementos seguintes usam a nova versão. Originais, respostas e marcações anteriores permanecem preservados. O [guia da continuidade](CONTINUIDADE_DOCUMENTAL.md) detalha os estados e a nova conferência.

A pergunta em preparo e os formulários dos quadros são salvos automaticamente: uma cópia imediata neste navegador e, após uma pausa curta (ou ao trocar de aba e ao fechar a página), a cópia no servidor. A linha de estado informa "Salvando…", "Salvo às HH:MM" ou "Sem conexão — salvo neste navegador"; ao reabrir a tela, um rascunho mais recente é oferecido para restaurar ou descartar. Na entrada do caso, a Mesa mostra o que já foi concluído e o que falta (documentos com limitação de extração, próxima etapa da análise, conversas interrompidas, quadros com pendências e rascunhos abertos), cada pendência com link para a área que a resolve. O resumo lê só os registros da apuração ativa e nunca o texto dos rascunhos.

A interface usa a paleta verde profundo, papel, grafite, cobre e névoa, com Source Serif 4 nos títulos e Source Sans 3 na interface e leitura. Os arquivos das fontes e suas licenças estão incluídos em `interface/fonts`; o navegador não consulta servidores externos para carregá-los.

Na conversa, **Conectado à API · Provedor · modelo** resume a conexão, ou **Chave de API ausente no servidor**, quando a chave não está definida no ambiente do servidor. A chave não aparece na tela. **Verificar conexão** e **Encerrar serviço** ficam em **Conexão e opções**. Após a conclusão, os seletores de apuração/conversa e as atualizações de andamento se recolhem; a resposta permanece em destaque. Abra o resumo da apuração para trocar a conversa ou acessar a exclusão. Os textos originais, caminhos de saída, IDs, versões e hashes permanecem em **Detalhes técnicos**.

Durante a execução, **Atualizações de andamento** tem rolagem interna e altura de até metade da tela, limitada a 420 px. Novas mensagens acompanham o fim da lista sem rolar a página. Ao subir para ler mensagens anteriores, a posição é preservada. A região também aceita foco e rolagem pelo teclado. A resposta final permanece fora dessa limitação de altura.

O texto da resposta renderiza títulos, negrito, itálico, listas simples, tabelas, citações, links HTTP(S) e blocos de código. HTML de documentos ou respostas é tratado como texto; imagens e scripts contidos no Markdown não são carregados. Blocos de código e o texto bruto nos detalhes preservam a marcação literal.

As citações usam o nome recebido do documento e a página física observada, como **Fato relevante de 11/01/2023 · página 1**. Clicar abre e focaliza o trecho correspondente na coluna de fontes. O nome é uma apresentação do nome do arquivo cadastrado, não uma confirmação editorial de seu conteúdo ou de sua data. Quando não há página observável, a interface usa as linhas/localizador existentes. Os nomes e as limitações das conversas históricas vêm dos manifestos congelados de suas próprias rodadas; o inventário atual não substitui esse escopo.

**Limitações das fontes** aparece quando há páginas sem texto, erros de extração, metadados congelados indisponíveis ou referências finais sem fonte recuperada na própria rodada. As referências sem suporte ficam marcadas como **Fonte pendente**, com a identidade preservada no texto bruto. A extração continua sem OCR e as limitações semânticas descritas na resposta continuam visíveis.

Em **Pesquisar documentos**, depois da pergunta na conversa:

1. Escolha **apuração (caso)** e **rodada**; depois escolha a **versão da busca documental**. Nenhuma versão é escolhida automaticamente. A seleção da tela não altera `configuracao.json` ou o caso ativo na conversa. Após escolher a rodada, o seletor se recolhe, mantendo o nome/ID/rodada visíveis; **Escolher apuração e rodada** permite trocar a seleção.
2. Confira a cobertura: documentos pesquisáveis, fontes sem adaptador, páginas sem texto e erros de extração são indicados.
3. Digite palavras ou uma expressão. Abra os filtros para selecionar documento, página física do PDF, tamanho da página de resultados ou outro tipo de busca.
4. Em cada resultado, veja documento, página quando disponível, linhas, fonte textual, método e referência. Use **Ver contexto completo**, **Baixar original** ou **Copiar referência**. O original baixado é a cópia congelada da rodada.
5. Use **Anterior/Próxima** para percorrer resultados. **Baixar esta página · JSON** exporta a página de resultados atual, incluindo parâmetros e local do log bruto; não exporta automaticamente todas as páginas. Os caminhos técnicos permanecem em **Registro técnico da consulta** ou nos detalhes de cada resultado.

Os modos são os mesmos da CLI: **Todas as palavras** (`comum`, com aspas para frases), **Texto literal** (`literal`, distingue caixa/acentos/pontuação) e **FTS avançada** (`fts`, aceita `OR` e prefixos com `*`). Filtro por página física só encontra unidades cujo derivado tem essa paginação reconhecida.

## Se não houver rodada ou índice

A tela informa o que falta. Antes da pergunta, use **Cadastrar documentos** para cadastrar e conferir todos os lotes e a extração dos PDFs. Na conversa, selecione a pauta e envie uma pergunta real para preparar a rodada; depois clique em **Atualizar lista**. Rodada sem banco exige construção explícita pelo procedimento do [guia SQLite](BANCO_SQLITE.md). O cadastro da interface extrai texto dos PDFs, mas não congela rodadas, executa OCR ou constrói índices. Reabra o servidor da interface após atualizar seus scripts; atualize a página para carregar os novos arquivos visuais.

O projeto continua sem caso ativo e sem rodada editorial após esta implementação. O exemplo incluído permanece inativo; não foi indexado para preencher a tela. A inspeção da lista usa metadados do catálogo e nomes de diretórios, sem ler os documentos dos casos.

## Rastreabilidade e limites

- Pesquisa, cobertura e contexto usam as mesmas funções do índice e salvam novos JSONs em `saidas/consultas_sqlite` da rodada selecionada. Baixar o original também valida a passagem e registra sua leitura. O campo histórico `ferramenta` dos logs continua identificando `scripts/banco.py`, o contrato compartilhado pelo núcleo; ele não distingue CLI de interface nesta extensão.
- Consultas abrem SQLite somente para leitura, validando hashes e vínculo ao snapshot. Pesquisa e leitura criam logs; cadastro preserva novos originais, recibos e versões do manifesto. A interface não sobrescreve originais, índices, prompts ou registros anteriores.
- A interface serve somente os arquivos estáticos autorizados de HTML, CSS e JavaScript. Download de fonte exige uma referência de passagem validada; o envio recebe bytes e nomes, sem aceitar caminhos do computador como entrada. Requisições de operação exigem token da sessão, JSON e origem local; conteúdo documental é inserido como texto na página.
- Resultados são trechos possivelmente sobrepostos. A busca textual não é recuperação semântica, validação factual ou OCR; ausência de resultado não prova ausência documental. Conferir os originais, sobretudo imagens e tabelas.
- O servidor é um utilitário local, sem contas de usuário ou hospedagem pública. A implementação e seus testes sintéticos não constituem piloto editorial, inferência local ou garantia adicional sobre dados processados no provedor configurado.

O servidor está em [interface_pesquisa.py](../scripts/interface_pesquisa.py); os arquivos visuais ficam em `interface/`. O iniciador e os caminhos internos são relativos ao pacote, permitindo sua cópia para outro diretório.

## Excluir e restaurar

Abra **Gerenciar e lixeira**, escolha uma apuração e use **Excluir apuração**, **Excluir** em uma conversa ou **Excluir** em uma rodada avulsa. A área **Perguntar à IA** também oferece **Excluir conversa** para a conversa selecionada. Uma caixa de confirmação informa o alcance antes de mover o item para a lixeira.

- A exclusão da apuração retira suas conversas e rodadas das listas e consultas da interface.
- A exclusão de uma conversa retira suas rodadas, incluindo perguntas complementares. Rodadas dessa conversa não podem ser excluídas separadamente, pois os complementos dependem do primeiro congelamento.
- Rodadas sem conversa podem ser excluídas individualmente. Os IDs continuam reservados: uma nova rodada não reutiliza os números excluídos.
- Uma execução em andamento bloqueia a exclusão da conversa ou da apuração. Cancele pela tela de perguntas e aguarde o encerramento. O backend também confere esse bloqueio para pedidos de outra janela.
- Use **Restaurar** na lixeira para devolver o item às listas. Se a apuração também estiver excluída, restaure-a primeiro. Restaurar uma apuração mantém excluídas as conversas ou rodadas que já estavam na lixeira por exclusões próprias.

A lixeira é uma exclusão lógica, persistida atomicamente em `lixeira/registro.json`, com identificação do item, data de exclusão e data de eventual restauração. Originais, versões do corpus, snapshots, índices, prompts, eventos e saídas permanecem em seus caminhos. A seleção global em `configuracao.json` continua inalterada. Não há remoção definitiva nem liberação de espaço em disco. Os comandos de consulta por CLI não aplicam o filtro visual da lixeira; ela não é um controle de acesso aos arquivos.

O gerenciamento lê somente metadados de identidade, vínculos e nomes de diretórios. Não consulta o modelo nem lê os documentos para excluir ou restaurar. A implementação fica em `scripts/lixeira.py`, `Conversas.gerenciar` e `interface/gerenciar.js`.
# Área de achados da IA — 1.3.0

Após selecionar caso/rodada, usar **Achados da IA** e escolher explicitamente revisão/versão de consulta próprias. A busca documental não precisa estar preparada para consultar os achados. Depois da escolha, as versões ficam no resumo expansível **Revisão … · consulta … · trocar versão**.

A lista apresenta afirmação, natureza, suporte da revisão pela IA e estado da conferência humana. Selecione um achado para abrir uma única ficha com as evidências, limitações, contexto, original, referência completa e histórico. O primeiro achado da página abre para leitura; isso não registra decisão nem aprovação. **Voltar à lista de achados** retorna o foco à seleção. O alcance dos retornos humanos da redação atual aparece na ficha, separado do suporte da IA; retornos de versões anteriores continuam no histórico. Os filtros adicionais ficam em **Filtrar por fonte, suporte e conferência**. A exportação cobre todas as páginas da seleção filtrada.

## Conferência humana dos achados

Cada afirmação ou cruzamento estruturado recebe uma marcação própria. Use **Conferir**, ao lado do achado ou na ficha, para abrir seus trechos citados, contexto e acesso ao original. Depois da leitura, escolha um dos quatro estados e, se desejar, escreva uma observação de até 500 caracteres. **Salvar marcação** registra a escolha; abrir a janela, consultar fontes ou baixar arquivos mantém o estado existente.

| Estado | Significado |
|---|---|
| Pendente | Ainda não houve conferência humana. |
| Conferida no original | O jornalista verificou que a fonte sustenta a afirmação. |
| Precisa de ajuste | Há erro, exagero ou contexto faltando. |
| Sem suporte suficiente | Os documentos consultados não permitem sustentar a afirmação. |

**Só pendentes** mostra o que falta revisar. O seletor **Conferência do jornalista** também permite filtrar qualquer um dos quatro estados. O progresso, como **6 de 10 achados revisados**, abrange todos os achados da revisão selecionada, independentemente da página e dos filtros. A contagem soma os três estados diferentes de Pendente. É possível retornar um achado a Pendente para reabrir a conferência, preservando o histórico.

As marcações se vinculam ao caso, rodada, revisão canônica dos achados, hash dos registros, ID e versão da afirmação. Outra revisão começa pendente; reconstruções do índice da mesma revisão compartilham suas marcações. Retornos humanos históricos dos registros anteriores continuam disponíveis, com seu alcance, e não são convertidos automaticamente em uma das novas marcações.

**Exportar seleção inteira · JSON** inclui a redação original, os campos originais da IA e, em cada resultado, `revisao_humana` com estado, observação, data e histórico. O campo original `conferencia_humana` continua descrevendo os retornos históricos do relatório; a marcação desta interface fica no novo objeto `revisao_humana`. A exportação respeita os filtros, sem se limitar à página visível, e contém o progresso da revisão inteira.

As avaliações humanas são eventos novos em `execucoes/<caso>/<rodada>/saidas/revisao_humana/<revisao>/eventos/`. Registros da IA, briefing, snapshots e ambos os bancos SQLite ficam intactos. As marcações não são inseridas nas ferramentas de análise do modelo. Uma revisão humana não altera automaticamente a redação, o suporte atribuído pela IA ou a inclusão no briefing; as observações ficam separadas para orientar o trabalho editorial.

O servidor rejeita marcações com identidade de revisão/versão divergente e protege contra sobrescrita por outra janela. Repetir o mesmo salvamento não duplica eventos. Falhas de leitura ou corrupção do histórico são informadas, sem substituir marcações por Pendente. O registro identifica a escolha feita pela interface e seu horário; esta versão não autentica individualmente o jornalista nem comprova a leitura do original. A opção **Conferida no original** requer fontes vinculadas e disponíveis, e representa a declaração expressa de quem usa a tela.

Use **Ler briefing** ou **Ver briefing e referências** para abrir o texto preservado com as referências clicáveis. Uma referência abre sua ficha de fontes ao lado; em telas menores, a ficha aparece abaixo do texto. Há retorno de foco ao marcador e opção de fechar o leitor. A exibição interpreta apenas títulos textuais e marcadores de achados, sem executar HTML ou abrir URLs da fonte. O texto bruto e seu hash permanecem acessíveis. Se a referência cita uma redação antiga, aparece aviso explícito antes da ficha atual, com o histórico aberto: as evidências atuais não são atribuídas silenciosamente à versão citada.

A interface funciona sem texto no índice documental. Não altera registros nem importa Markdown antigo. Erros não são exibidos como ausência de achados. Consulte [ACHADOS_IA.md](ACHADOS_IA.md). A reorganização visual e os testes sintéticos não constituem piloto com jornalistas nem validação editorial.

# Conversa com os documentos

As áreas **Caderno da apuração** e **Diligências** permitem contribuições humanas e acompanhamento entre rodadas. O [caderno](CADERNO_APURACAO.md) guarda passagens com autor declarado, localização e fonte e permite cruzamentos e envio explícito à pergunta. As [diligências](DILIGENCIAS.md) ligam ações aos achados, registram responsáveis/estados e permitem cadastrar respostas e retomar a questão. Recebimento e conclusão são decisões distintas. Esses registros ficam separados das saídas da IA e não autenticam individualmente o jornalista.

A área **Perguntar à IA**, com a seção **Conversa com os documentos**, envia perguntas à API do provedor configurado. O cadastro e a pesquisa manual continuam disponíveis. É possível selecionar um caso cadastrado, enviar uma pergunta, acompanhar mensagens e ferramentas, conferir fontes, baixar originais, cancelar e retomar a conversa. **Abrir mesa.vbs** inicia o serviço sem console visível; **Iniciar pesquisa.cmd** mantém a opção com console. Consulte [INTEGRACAO_API.md](INTEGRACAO_API.md) para o fluxo atual. As descrições históricas abaixo sobre a interface não gerar inferência se aplicam às áreas anteriores de cadastro e consulta, não à nova área de conversa.

