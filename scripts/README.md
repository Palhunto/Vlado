# Scripts de apoio

Todos os caminhos internos são resolvidos a partir desta pasta de projeto, sem depender do diretório do projeto acadêmico pai. Montagem, integridade e snapshot usam a biblioteca padrão do Python; não fazem chamadas de modelos ou rede.

- `montar_fluxo.py`: gera o fluxo e os hashes; `--check` confere sem alterar.
- `verificar_projeto.py`: verifica o corpus ativo e os prompts; `--pacote` também confere as cópias de referência e apoio contra a procedência registrada.
- `criar_caso.py`: cadastra documentos selecionados em uma apuração independente, calcula hashes e cria seu manifesto. Não ativa o caso automaticamente, não mistura pautas e recusa duplicatas idênticas.
- `cadastrar_documentos.py`: entrada atual para cada lote recebido antes da pergunta, em caso novo (`--novo --titulo`) ou existente; confirma todos os itens por recibo, identifica duplicatas, acumula documentos e preserva versões. Não ativa caso nem cria rodada/índice. Ver [cadastro](../docs/CADASTRO_DOCUMENTOS.md). `criar_caso.py` permanece como CLI legada compatível.
- `selecionar_caso.py`: seleciona exatamente um caso cadastrado; `--nenhum` retorna ao início sem caso ativo. Não executa apuração.
- `nova_rodada.py`: congela arquivos e pergunta e, com `indice_sqlite` habilitado, constrói o índice textual da rodada, sem inferência. Recusa IDs inválidos, hashes divergentes, pergunta vazia e sobrescrita. Teste principal exige autorização no manifesto. `--sem-indice` permite congelar sem banco, com motivo a registrar pelo operador.
- `ocr.py`: OCR local (OCRmyPDF/Tesseract, com alternativa PyMuPDF + Tesseract) usado por `extrair_pdf.py` apenas nas páginas sem texto nativo.
- `extrair_pdf.py`: função compartilhada que o cadastro chama por padrão para preparar PDFs em Markdown com páginas/linhas e hashes. Depende de `pypdf` (`requirements.txt`); registra páginas sem texto e falhas. Também funciona como CLI avulsa. Não faz OCR, não corrige e não sobrescreve.
- `indice_sqlite.py`: construção/validação, adaptadores de texto/páginas, busca parametrizada, leitura e cobertura. Usa somente entradas congeladas, sem modelo ou rede.
- `banco.py`: CLI com `construir`, `buscar`, `ler`, `cobertura` e `verificar`; exige caso/rodada explícitos e preserva retornos brutos. Ver [guia SQLite](../docs/BANCO_SQLITE.md).
- `interface_pesquisa.py`: servidor em `127.0.0.1` com cadastro, pesquisa documental, achados e conversa com os documentos, cuja inferência usa a API do provedor configurado. O cadastro não cria rodada; o envio da pergunta pela conversa congela uma rodada e constrói seu índice. Execute diretamente ou abra `Iniciar pesquisa.cmd`. Ver [guia da interface](../docs/INTERFACE_PESQUISA.md).
- `inferencia_api.py`: adaptador `ServidorAPI`, com o mesmo contrato de chamada, envio e notificações que `codex_apuracao.py` já usava. Lê a configuração com `ler_inferencia`; `seguro()` redige chaves; histórico em `conversas/<id>/api_historico.json`, sem imagens; no máximo 60 passos do provedor por etapa; espera de 300 s por chamada de ferramenta; interrupção fecha as chamadas pendentes. Ver [integração](../docs/INTEGRACAO_API.md).
- `provedor_anthropic.py`: Anthropic Messages API, com streaming, `tool_use`/`tool_result` e cache de prompt pelo `cache_control` de nível superior.
- `provedor_openai.py`: OpenAI Responses API, sem estado (`store=False`), com streaming, `function_call`/`function_call_output` e itens de raciocínio criptografados reenviados.
- `codex_apuracao.py`: conversas, eventos e ferramenta `consultar_acervo`, delimitada ao corpus da rodada. Os nomes `codex_*` são mantidos por compatibilidade com rodadas existentes e não indicam uso do Codex.
- `fluxo_codex.py`: controle das seis etapas, comparação adicional na continuidade documental, validação e publicação automática dos achados.
- `continuidade.py`: seleção da versão ampliada do corpus, vínculo à última rodada concluída e validação do comparativo entre achados anteriores e atuais.
- `revisao_humana.py`: marcações humanas em eventos separados, com histórico e vínculo à versão do achado.
- `lixeira.py`: exclusão lógica e restauração de itens, com preservação dos arquivos.
- `rascunhos.py`: rascunho do texto ainda não confirmado por conta, apuração e tela (`POST /api/rascunhos-salvar|ler|listar|descartar`), em `casos/<caso>/rascunhos/`. Versão crescente: a aba com versão antiga recebe 409 com a versão atual, sem sobrescrever. Limites em `limites.RASCUNHOS`; recusa campos e valores com forma de chave; vai para a lixeira e para o apagamento definitivo junto com o caso; convidados guardam só a pergunta.
- `ambiente.py`: diagnóstico das dependências do interpretador utilizado pelo iniciador, inclusive a disponibilidade dos SDKs `anthropic` e `openai` e a presença de cada chave (apenas verdadeiro ou falso).
- `apuracao.py`: notas editáveis por caso, com revisões atômicas separadas das fontes, seleções documentais/IA e controle de conflitos entre janelas.
- `exportar_apuracao.py`: Markdown, PDF real (`reportlab`) e DOCX editável (`python-docx`) com referências legíveis. Ver [aba Apuração](../docs/APURACAO.md).

Exemplo de criação de rodada, **depois de receber uma pergunta real**:

```powershell
python scripts/nova_rodada.py --id R001 --pergunta-arquivo entrada/pergunta.txt
```

O agente deve salvar a pergunta literal em `entrada/pergunta.txt` ou outro arquivo temporário autorizado, sem interpolar seu conteúdo como código de shell. Depois da criação, usar o snapshot em `execucoes/<caso_id>/R001/entradas` como fonte daquela rodada.

Cadastrar e selecionar uma nova pauta, com nomes ilustrativos de arquivos:

```powershell
python scripts/criar_caso.py --id minha_apuracao --titulo "Minha apuracao" --documentos entrada/documento_a.pdf entrada/documento_b.pdf --natureza publicos
python scripts/selecionar_caso.py --id minha_apuracao
```

Para usar o exemplo incluído, selecionar explicitamente `exemplo_covaxin`. Para trocar de pauta, cadastrar/selecionar outro ID. `python scripts/selecionar_caso.py --nenhum` limpa a seleção sem apagar documentos ou rodadas. Os formatos cadastráveis não garantem que todas as ferramentas da sessão consigam lê-los; verificar acesso antes da análise.

Para preparar texto de um PDF novo:

```powershell
python scripts/extrair_pdf.py --pdf entrada/documento.pdf --id D001 --saida entrada/D001_texto_v1.md
```

Registrar o arquivo, o derivado e seus hashes em um novo manifesto antes de autorizar o uso. Não editar hashes apenas para silenciar uma divergência: verificar a causa e versionar a mudança. Alterar corpus requer preparar manifesto e configuração novos, sem mudar o snapshot de uma rodada existente.
# Achados estruturados

`caderno.py` preserva contribuições humanas, origens e cruzamentos sem alterar o corpus ou os achados da IA. `diligencias.py` registra ações, responsáveis, estados e respostas com histórico, sem enviar solicitações. A integração de contexto em `codex_apuracao.py` exige seleção explícita e confere as fontes na versão de destino. Guias: [caderno](../docs/CADERNO_APURACAO.md) e [diligências](../docs/DILIGENCIAS.md).

`achados.py` registra/valida conjuntos versionados e constrói/consulta banco derivado separado, sempre com caso e rodada explícitos. A geração inicial é preservada antes da revisão; o fluxo grava os dados estruturados, sem extraí-los do briefing. Guia: [ACHADOS_IA.md](../docs/ACHADOS_IA.md). Não há chamada de modelo ou aprovação humana automática.

