# VLADO

**Versão 1.4.0.** Assistente de apuração documental com inferência online pela API do provedor configurado (Anthropic ou OpenAI). Inclui cadastro com extração textual de PDFs, índice SQLite/FTS5, fluxo automático de seis etapas, banco separado de achados e conferência humana na interface. A área **Conversa com os documentos** envia as perguntas à API configurada; a chave fica apenas em variável de ambiente do servidor. O uso é cobrado pelo provedor, por uso.

Para retomar o desenvolvimento, ler [AGENTS.md](AGENTS.md) e este README. A configuração e os manifestos de cada caso registram a seleção e o protocolo efetivos.

O [guia do fluxo automático](docs/FLUXO_AUTOMATICO_CODEX.md) descreve as etapas e a publicação dos achados. As [verificações técnicas](docs/VERIFICACAO.md) reúnem os resultados registrados. A integração com a API, incluindo o que ainda não foi verificado em chamada real, está em [INTEGRACAO_API.md](docs/INTEGRACAO_API.md).

O [guia SQLite](docs/BANCO_SQLITE.md) documenta a pesquisa nos documentos. O [guia de achados da IA](docs/ACHADOS_IA.md) descreve registro, revisão, vínculo com o briefing e consulta dos cruzamentos estruturados. Cadastro e índice não executam inferência; a análise online ocorre somente quando uma pergunta é enviada pela Mesa. Resultados antigos não são importados automaticamente. A manutenção usa materiais sintéticos; não é piloto editorial.

Para preparar outro Windows, use **[Preparar notebook.cmd](Preparar%20notebook.cmd)**, que orienta a definição da chave no ambiente. A versão distribuída abre com catálogo vazio. A base de código está na branch inicial main.

## Trabalhar pela interface

Para instalar num computador Windows sem Python, use o **Vlado-Setup.exe**: ele traz Tesseract, Ghostscript e todas as bibliotecas, cria atalhos e pede a criação do administrador na primeira abertura ([guia do instalador](docs/INSTALADOR_WINDOWS.md)). Pelo repositório, no Windows, abra **[Abrir mesa.vbs](Abrir%20mesa.vbs)** para iniciar em segundo plano e abrir o navegador, sem terminal visível. **[Iniciar pesquisa.cmd](Iniciar%20pesquisa.cmd)** continua disponível com console. Em **Perguntar à IA › Conexão e opções**, escolha o provedor (Anthropic ou OpenAI), cole a chave da API e salve; ela fica em `segredos/` (fora do git) e nunca volta ao navegador. Uma variável de ambiente `ANTHROPIC_API_KEY`/`OPENAI_API_KEY` tem prioridade. O botão **English/Português** no topo troca o idioma da interface. Na **Mesa de apuração**, use **Começar uma apuração**, **Adicionar documentos** ou **Retomar trabalho**. O seletor no topo mantém a mesma apuração entre as áreas. Cadastre os documentos, confira o recibo e clique em **Perguntar sobre estes documentos**. Em **Conversa com os documentos**, confira **Verificar conexão** e envie a pergunta. Você pode acompanhar as respostas, abrir o original na página citada, baixar fontes, complementar a conversa e cancelar. O guia [INTEGRACAO_API.md](docs/INTEGRACAO_API.md) descreve chave, configuração, arquitetura, testes e limites. **Encerrar serviço** fecha o backend e interrompe as execuções ativas. Se já havia um servidor aberto antes desta atualização, encerre-o e inicie novamente.

A interface usa um servidor somente no próprio computador e `pypdf` para preparar o texto dos PDFs no cadastro. Cadastrar não inicia apuração. Na área de conversa, enviar uma pergunta cria uma rodada e índice próprios; complementos preservam o corpus congelado e criam novas rodadas. A apuração escolhida no topo vale para toda a Mesa e não altera o caso ativo dos comandos em `configuracao.json`. Análises aparecem por pergunta, data e documentos preservados; a etapa e a versão consultadas continuam explícitas. Áreas e filtros podem ser retomados pelo endereço no navegador. As áreas de pesquisa documental e de achados continuam consultando seus registros versionados; novas perguntas e complementos publicam os achados após concluir e verificar o fluxo automático. Consulte o [guia da interface](docs/INTERFACE_PESQUISA.md) e o [cadastro antes da pergunta](docs/CADASTRO_DOCUMENTOS.md).

Em **Gerenciar e lixeira**, exclua apurações, conversas com seus complementos ou rodadas avulsas e restaure-as quando precisar. A exclusão retira os itens da interface e preserva os arquivos. Execuções em andamento bloqueiam a exclusão. A tela de perguntas também tem **Excluir conversa**.

A apresentação usa nomes legíveis, IDs automáticos no cadastro e citações por título/página. A resposta renderiza Markdown, com andamento recolhido após concluir; hashes, versões e registros ficam em **Detalhes técnicos**. A conexão aparece como **Conectado à API · \<Provedor\> · \<modelo\>**, ou como **Chave de API ausente no servidor**; os alertas apontam páginas sem texto e fontes pendentes. Cores e fontes seguem a referência editorial, com fontes incluídas no projeto. A Mesa abre em modo escuro, com grafite esverdeado, texto marfim e ações em sálvia. O botão **Modo claro / Modo escuro**, no topo, alterna a aparência e salva a preferência neste navegador, quando o armazenamento está disponível.

Em **Achados da IA**, **Conferir** abre as fontes e permite registrar Pendente, Conferida no original, Precisa de ajuste ou Sem suporte suficiente, com observação opcional. Há filtro de pendências, progresso da revisão e exportação com as marcações. A avaliação humana é salva separadamente, com histórico, preservando o texto original da IA.

Para levar correções à próxima pergunta, marque **Levar à próxima pergunta** nos achados com avaliação salva e clique em **Continuar com estas observações**. A prévia mostra as observações e suas fontes; revise a pergunta e envie. A conversa de origem é retomada; uma rodada sem conversa abre uma nova sobre seu corpus congelado. O retorno é registrado na nova rodada e acompanha as seis etapas, com reexame das fontes. Marcações alteradas após a seleção exigem nova seleção. As observações não aprovam automaticamente os novos achados.

Para incorporar uma resposta de assessoria, contrato ou outro lote à mesma conversa, use **Continuar com novos documentos**. Cadastre os arquivos, confira o recibo e escolha **Usar esta versão na próxima pergunta**. O envio cria outra rodada com o corpus ampliado, preservando as anteriores. Após as seis etapas, uma comparação adicional destaca evidências novas, conclusões alteradas, pendências respondidas e achados para nova conferência. Os complementos seguintes usam a versão ampliada; novos cadastros só entram mediante escolha explícita. [Guia da continuidade](docs/CONTINUIDADE_DOCUMENTAL.md).

## Começar no novo projeto

Em **Caderno → Notas e redação**, escreva e edite notas com Markdown e prévia, adicione seleções dos achados da IA ou da pesquisa documental e exporte o caderno salvo em Markdown, PDF ou DOCX editável. As notas pertencem ao caso escolhido e ficam separadas das fontes preservadas. [Uso, persistência e limites](docs/APURACAO.md).

Em **Caderno → Trechos com fonte e contribuições**, registre trechos e achados humanos com documento, página/localização, anotação e autor declarado. Seleções podem formar cruzamentos humanos ou acompanhar explicitamente uma pergunta. [Guia do caderno](docs/CADERNO_APURACAO.md).

Em **Diligências**, crie uma **Nova diligência** livre ou acompanhe ações ligadas aos achados da IA, às referências do briefing ou ao caderno: responsável, prazo, estado e histórico. Cadastre e vincule respostas documentais e use **Retomar esta questão** para reexaminá-las numa nova rodada. Receber uma resposta não encerra automaticamente a pendência. [Guia das diligências](docs/DILIGENCIAS.md).

1. Abra **esta pasta** como projeto no agente de chat que vai usar (por exemplo, Codex ou Claude Code). Também é possível copiar a pasta inteira para outro local e abrir a cópia; nenhum arquivo de execução depende do projeto acadêmico pai.
2. Crie um chat novo e envie o texto de [COMECAR_AQUI.md](COMECAR_AQUI.md).
3. O assistente deve carregar as instruções e ficar pronto para receber documentos. **Nenhum caso começa ativo.**
4. Envie os documentos de uma apuração e identifique a pauta. **Cada lote deve ser cadastrado imediatamente, antes da pergunta**, com cópias preservadas, IDs, hashes e recibo de todos os arquivos, incluindo duplicatas ou falhas. Lotes seguintes são acrescentados ao caso indicado; confira o inventário acumulado. Você também pode cadastrar pela Etapa 1 da interface ou selecionar explicitamente um caso já cadastrado. Sem pergunta, não se cria rodada nem índice.
5. Com todos os lotes conferidos, faça sua pergunta normalmente. O fluxo padrão congela documentos e recibos em uma rodada nova, constrói seu índice textual e executa planejamento, busca, cruzamento assistido, revisão e briefing, guardando os registros desse caso. Arquivos e pergunta no mesmo envio exigem concluir o cadastro primeiro. O índice informa formatos/páginas sem texto e complementa a leitura dos originais.
6. Confira os documentos originais e informe as correções. Para acompanhar cada etapa separadamente, peça **modo por etapas**.

O projeto é genérico. Cada apuração possui documentos, manifesto, versão e rodadas próprios. Os prompts não contêm caso ou pergunta fixos. Esta distribuição começa sem acervos cadastrados.

Para começar com outra pauta, basta enviar os arquivos no novo chat e dizer, por exemplo, que pertencem a uma nova apuração. Não é necessário editar os prompts. Para trocar de caso, selecione o desejado e use um chat novo em testes comparáveis. Só cruzar casos quando você pedir explicitamente e autorizar a seleção documental conjunta.

## Fontes web por apuração

Ao criar uma **nova apuração**, o jornalista escolhe o modo de fontes na tela de cadastro, ou com `--modo-fontes` e `--dominio-permitido` em `scripts/cadastrar_documentos.py --novo`:

- **Somente documental** (`somente_documental`, padrão): a apuração usa apenas os documentos cadastrados, sem acesso à internet.
- **Documentos + web** (`documentos_web`): além dos documentos, o jornalista pode capturar páginas de **um único site**, informado só pelo nome (ex.: `www.exemplo.gov.br`). Subdomínios e outros sites são recusados.

O modo fica gravado no manifesto do caso e não muda depois. Para trocar, crie outra apuração.

No modo com web, a captura é feita pelo painel "Fontes web desta apuração", na tela de cadastro, ou por `python scripts/fontes_web.py --caso ID --url https://…`, sempre a pedido explícito do jornalista ([AGENTS.md](AGENTS.md)):

- **Rede:** só `https`, na porta padrão, e só o site do caso. Os redirecionamentos são seguidos um a um e conferidos a cada salto. O nome do site é resolvido e conferido antes de conectar, e endereços internos, privados ou reservados são recusados.
- **Limites:** 20 MB por página e 60 segundos por captura. Só HTML, texto ou PDF, sem conteúdo comprimido.
- **O que fica registrado:** cada captura recebe um ID `W001`, `W002`… e fica em `casos/<id>/fontes_web/`, separada dos documentos. Ela guarda o conteúdo exatamente como recebido, a cópia de texto, o endereço pedido e o final, a data e a hora do acesso (UTC), a situação HTTP, os cabeçalhos relevantes e o SHA-256. Também ganha uma linha no registro `fontes_web/registro.jsonl`, que só recebe acréscimos.
- **Texto da página:** a cópia de texto deixa de fora scripts, estilos e o que estiver escondido pelo próprio HTML: o atributo `hidden`, `aria-hidden="true"` ou `display:none`/`visibility:hidden` no `style` do elemento. A captura é marcada com `contem_texto_oculto` quando algo foi descartado. Texto escondido de outras formas não é detectado e pode aparecer na cópia sem essa marca. Isso inclui CSS externo ou de um bloco `<style>`, `opacity:0`, `font-size:0`, texto posicionado fora da tela e o conteúdo de um `<details>` fechado. O conteúdo bruto fica preservado como recebido, e o texto é dado da fonte, nunca instrução.
- **Uso na apuração:** as capturas são congeladas na rodada junto com os documentos, entram no índice e são citadas com o endereço e o horário do acesso. Uma captura registra o que o site entregou naquele momento. Ela não prova que a página continue igual e não substitui a conferência no original.

Nenhuma página é aberta, pesquisada ou capturada sem o modo marcado no caso.

## O que foi migrado

| Original | Operação nesta versão |
| --- | --- |
| Descrição do corpus | Inventário verificável, leitura delimitada e descrição com cobertura explícita |
| Planejamento de 5–7 frentes | Plano orientado pela pergunta, normalmente 1–3 frentes conforme a necessidade |
| Agente chamando busca semântica | O agente consulta SQLite/FTS5 das entradas congeladas e lê textos, páginas e imagens autorizadas; registra consultas e usa cálculos quando necessário |
| Avaliação de relevância e detalhamento | Revisão das afirmações contra passagens originais, com status e correções separados |
| Síntese dos relatórios | Briefing restrito ao material sustentado; sem fallback de relatórios reprovados como fatos |
| Interface Flask/Svelte | Conversa com a API do provedor configurado e arquivos persistidos por rodada; pesquisa opcional em interface Python/HTML própria |
| ChromaDB e embeddings | Não utilizados nesta versão; não presumir equivalência de recuperação com RAG vetorial |

O resultado é uma migração do procedimento para operação por agente de chat e pela Mesa de apuração, esta com inferência pela API do provedor configurado. Não se trata de portar o servidor antigo para a nuvem. A procedência está registrada em [docs/MIGRACAO.md](docs/MIGRACAO.md) e [proveniencia/origem_repositorio.json](proveniencia/origem_repositorio.json).

## Pastas

- [prompts](prompts/README.md): sete módulos, fluxo completo e hashes.
- [casos/catalogo.json](casos/catalogo.json): índice das apurações; apenas o caso selecionado pode ser consultado na geração.
- `casos/<id>/originais`: documentos preservados de cada apuração.
- `casos/<id>/manifesto.json`: IDs, hashes, derivados autorizados e estado do piloto daquele caso.
- `casos/<id>/cadastros/<lote>`: originais novos, recibos e versões do manifesto de cada cadastro, inclusive antes da pergunta.
- [entrada](entrada/README.md): local para adicionar documentos de outra pauta antes de configurar um novo manifesto.
- [execucoes](execucoes/README.md): snapshots e saídas por caso e rodada; inicialmente não há resultados de apuração.
- [modelos](modelos/README.md): formatos vazios de registro e revisão.
- [scripts](scripts/README.md): montagem, integridade, preparação de texto, criação de rodadas e integração com a API.
- [docs/MIGRACAO.md](docs/MIGRACAO.md): decisões, limites e fontes da adaptação.
- [docs/PILOTO.md](docs/PILOTO.md): procedimento de calibração, sem gabarito.
- [docs/BANCO_SQLITE.md](docs/BANCO_SQLITE.md): uso do índice, leitura de passagens, cobertura e gerações preservadas.

## Arquivos e privacidade

Usar somente documentos públicos ou materiais sintéticos identificados neste piloto. A inferência da Mesa é online, no provedor configurado, e é cobrada por uso; não atribuir a ela as garantias de processamento local pretendidas no artigo. A chave de API fica na variável de ambiente do servidor ou em `segredos/chaves.json`, fora do git. Para a Mesa hospedada (ambientes separados, contas com login e senha, Docker, HTTPS, limites de gasto, backup e recuperação), siga [docs/GUIA_TECNICO_IMPLANTACAO.md](docs/GUIA_TECNICO_IMPLANTACAO.md). Guia da redação: [docs/GUIA_RAPIDO_REDACAO.md](docs/GUIA_RAPIDO_REDACAO.md); roteiro da sala: [docs/ROTEIRO_APRESENTACAO.md](docs/ROTEIRO_APRESENTACAO.md); app Android: [docs/ANDROID.md](docs/ANDROID.md); o que vai ao provedor: [docs/DADOS_NA_INFERENCIA.md](docs/DADOS_NA_INFERENCIA.md); licenças: [docs/AVISOS_DE_LICENCA.md](docs/AVISOS_DE_LICENCA.md). Não foram configuradas garantias adicionais de retenção ou tratamento de dados na conta do provedor.

O projeto usa `AGENTS.md` para orientar o agente, conforme a [documentação oficial OpenAI](https://learn.chatgpt.com/docs/agent-configuration/agents-md). Instruções de projeto não substituem permissões da aplicação nem garantem bloqueio técnico de rede ou acesso a outras pastas. As condições efetivas precisam constar do registro de cada rodada.

## Verificações técnicas

Os scripts usam Python 3.12+ com SQLite/FTS5. Dependências em [requirements.txt](requirements.txt): `pypdf`, para a extração padrão dos PDFs no cadastro; `ocrmypdf` e `PyMuPDF`, para o OCR local das páginas digitalizadas (exigem Tesseract e, para o OCRmyPDF, Ghostscript no sistema; ver `docs/CADASTRO_DOCUMENTOS.md`); `anthropic==2.8.0` e `openai==3.50.0`, para a Mesa. `scripts/ambiente.py` informa se os SDKs estão disponíveis e se cada chave está definida, apenas como verdadeiro ou falso. O recibo registra dependência ausente, PDF protegido, páginas sem texto e erros sem descartar o original. DOCX e XLSX são lidos no cadastro só com a biblioteca padrão, com localizador de parágrafo, tabela ou `Aba!A1`. Imagens avulsas não passam por OCR automático; `--ocr-imagens` aplica o Tesseract local quando pedido. Rodadas antigas conservam sua cobertura; para preparar os PDFs de um caso já cadastrado, use `python scripts/cadastrar_documentos.py --caso ID --preparar-pdfs`, sem criar rodada ou índice antes da pergunta.

```powershell
python scripts/montar_fluxo.py --check
python scripts/verificar_projeto.py
python -m unittest discover -s testes -v
```

Se `python` não estiver no PATH, o operador pode usar uma instalação Python ou o iniciador, que procura o Python disponível. Nenhum script precisa do caminho do computador que preparou o pacote.

Verificações de arquivos e scripts são distintas de avaliação da qualidade do assistente. O estado do piloto e a autorização de teste principal são próprios de cada caso e ficam em seu manifesto.

Os resultados das verificações de preparação estão em [docs/VERIFICACAO.md](docs/VERIFICACAO.md). A migração para a API ainda não tem chamada real registrada; o estado está em [docs/INTEGRACAO_API.md](docs/INTEGRACAO_API.md).
