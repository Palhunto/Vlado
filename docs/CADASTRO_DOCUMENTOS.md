# Cadastro antes da pergunta

Implementado em 04/11/2026, versão operacional e prompts **1.2.0**, a pedido do usuário. Atualizado em 13/11/2026 para versão operacional e prompts **1.4.0**; o cadastro não faz chamadas de modelo. Cada lote deve ser cadastrado assim que for enviado, antes de qualquer pergunta editorial. O objetivo é contabilizar todos os arquivos recebidos, preservar cópias e evitar que a seleção orientada pela pergunta deixe anexos de fora.

## Na interface

1. Abra `Iniciar pesquisa.cmd`. Em **Cadastrar documentos**, escolha novo caso ou o caso que receberá outro lote.
2. Para um caso novo, informe apenas o nome; o ID é gerado internamente. Indique documentos públicos ou materiais sintéticos e selecione todos os arquivos do envio.
3. Clique em **Enviar e cadastrar agora**. O envio produz imediatamente um recibo por arquivo: nome, ID, hash e condição de novo documento ou duplicata. O inventário mostra o total acumulado do caso, mesmo sem rodada ou pergunta.
4. Confira o número de arquivos do recibo e acrescente outros lotes, se necessário. Só depois envie sua pergunta na conversa da Mesa (ou ao agente de chat), indicando o caso. A seleção no navegador não muda o caso ativo do Codex.

O envio admite até 50 MB e 100 arquivos por lote. O limite de documentos únicos por caso vem da configuração (inicialmente 20). Formatos aceitos: PDF, PNG, JPG/JPEG, TXT, MD, CSV/TSV, XLSX e DOCX. PDFs passam por extração textual automática com `pypdf` e, nas páginas sem texto nativo utilizável, por OCR local. O recibo e o inventário informam o resultado: páginas com texto nativo, reconhecidas por OCR, sem texto e com falha. DOCX e XLSX também ganham cópia de trabalho com localizador (ver [Extração de DOCX e XLSX](#extração-de-docx-e-xlsx)); `.docm`/`.xlsm` são aceitos como originais, mas o conteúdo com macro não é extraído. Imagens avulsas só passam por OCR com a opção explícita `--ocr-imagens`; os demais formatos continuam sem conversão automática.

O iniciador verifica Python 3.12+, SQLite/FTS5 e `pypdf` (o OCR é opcional e informado à parte) no próprio interpretador que abrirá o serviço. A prioridade é `.venv`, runtime do Codex e depois os comandos `python`/`py -3`, sempre com essa verificação. Um Python que apenas responde a `--version` não é suficiente. `Iniciar pesquisa.cmd --verificar-runtime` mostra o ambiente selecionado sem abrir o serviço. Nenhuma dependência é instalada automaticamente.

Se uma instância aberta diretamente estiver sem extrator, a interface informa isso antes do envio; os PDFs recebidos continuam preservados com a falha registrada. O diagnóstico completo fica em **Detalhes técnicos**. Encerre a instância e reabra pelo iniciador atualizado. Para casos ativos com PDFs sem preparação ou com erro, escolha a apuração em **Cadastrar documentos** e use **Preparar PDFs pendentes**, sem reenviar os originais. O botão fica desabilitado se o extrator não estiver disponível. Casos na lixeira precisam ser restaurados explicitamente antes de qualquer preparação.

Se houver formato recusado, arquivo inacessível ou limite excedido, o lote não é confirmado e os arquivos selecionados permanecem na tela para correção. Falha de comunicação deixa o envio sem confirmação: consulte o inventário antes de continuar; reenviar os mesmos bytes identifica duplicatas. Não afirmar recebimento completo quando faltarem itens.

## No chat e nos scripts

O agente deve executar o cadastro ao receber cada lote, sem esperar a pergunta. Não há observador de anexos operando em segundo plano: esse comportamento depende das instruções e da execução pelo agente. Não procurar documentos fora dos anexos/caminhos fornecidos. Se o destino do lote for ambíguo, esclarecer o caso antes de cadastrar.

Na pasta do projeto, com arquivos ilustrativos:

```powershell
python scripts/cadastrar_documentos.py --caso minha_apuracao --novo --titulo "Minha apuração" --natureza publicos --documentos entrada/a.pdf entrada/b.pdf
python scripts/cadastrar_documentos.py --caso minha_apuracao --natureza publicos --documentos entrada/c.pdf
```

`--novo` recusa sobrescrever um caso; sem essa opção, o caso precisa existir. A CLI legada `criar_caso.py` permanece compatível, mas o fluxo atual usa `cadastrar_documentos.py` para ter recibos e acréscimo de lotes. Cadastro não seleciona o caso automaticamente.

## Extração padrão de PDFs

O núcleo compartilhado pelo chat, interface e CLI legada extrai PDFs depois de preservar suas cópias e antes de publicar o lote. Os derivados Markdown ficam em `cadastros/<lote>/derivados/`, vinculados ao mesmo ID do original, com hash de origem, método, página física e linhas da cópia de trabalho. Não são novas fontes independentes. Não há correção editorial, leitura por IA ou validação de tabelas nessa etapa.

Instale `requirements.txt` no Python que executa o cadastro, ou use o runtime do Codex que já disponha de `pypdf`. Se a dependência faltar, o PDF estiver protegido, inválido ou tiver páginas sem texto/com erro, o original continua cadastrado e o recibo explicita a limitação. Uma falha de gravação ou publicação continua interrompendo o lote. Recepção do arquivo e cobertura textual são estados distintos.

Para preparar PDFs de um caso existente sem reenviar arquivos:

```powershell
python scripts/cadastrar_documentos.py --caso minha_apuracao --preparar-pdfs
```

O comando lê somente as cópias preservadas do caso indicado. Registra uma operação de preparação, sem novos documentos; os campos legados `recebidos`/`duplicados` contam os arquivos existentes processados, não novos anexos enviados. Extrações já preparadas são reutilizadas, exceto páginas sem texto ainda não submetidas ao OCR ou com falha de OCR, que são reprocessadas se houver motor; falhas de extração podem ser tentadas novamente. Mudanças nos documentos/derivados/metadados incrementam a versão e reiniciam a aprovação do piloto. Rodadas e gerações de índices existentes ficam intactas. O texto passará ao índice da próxima rodada criada após uma pergunta; este comando não cria índice nem rodada.

## OCR local de páginas digitalizadas

O texto nativo do PDF sempre tem prioridade. O OCR só é aplicado às páginas em que o `pypdf` não obtém texto utilizável (menos de 10 caracteres alfanuméricos, como uma página só com imagem ou só com um número carimbado). Nada é enviado a serviço externo e nenhum modelo de linguagem é chamado: o reconhecimento roda nesta máquina.

- **Motor principal:** OCRmyPDF (`--force-ocr --rotate-pages --sidecar`, restrito às páginas sem texto, saída PDF descartada) com Tesseract e Ghostscript. Idioma padrão `por+eng`.
- **Alternativa:** se o OCRmyPDF ou o Ghostscript faltarem (ou o OCRmyPDF falhar), o PyMuPDF renderiza a página a 300 dpi e a CLI do Tesseract a reconhece. O Tesseract direto roda com `OMP_THREAD_LIMIT=1` quando essa variável não está definida.
- **Orientação da página (OSD):** nos dois motores, o OSD do Tesseract (`osd.traineddata`) só é aceito com confiança de 14 ou mais. Abaixo de 14, quando o OSD sugere giro, o Vlado lê a página nas duas orientações; o giro só vence se a confiança média da leitura girada ficar 10 pontos acima da outra e for de pelo menos 50. No motor principal, a página que a leitura dupla gira vai numa cópia temporária girada do PDF para o OCRmyPDF; o original não é tocado. No motor alternativo, a correção vale só para a imagem.
- **Registro da orientação:** o recibo e o cabeçalho do derivado trazem `ocr_orientacao` por página (decisão, giro aplicado e de onde veio o texto). O recibo traz também `texto_de` por página, `paginas_giradas_antes`, `paginas_tesseract_direto` e `ocr_avisos_orientacao`; o cabeçalho da cópia em texto repete a orientação e os avisos por página. Quando o cabeçalho diz "girada N graus (OSD, confianca X; texto de ocrmypdf)", o giro foi pedido pelo OSD do Vlado e feito ou não pelo OCRmyPDF, que mede a página de novo: em páginas curtas ou em tabelas o texto pode sair de cabeça para baixo mesmo com esse registro, e a página deve ser conferida no original.
- **Custo:** a conferência de orientação soma de 1 a 3 segundos por página digitalizada e roda uma página por vez: um PDF de 12 páginas digitalizadas leva cerca de 35 segundos, contra 20 antes.
- **Limitações conhecidas (pendência da Onda 1):** o motor alternativo (Tesseract direto) ainda lê mal valores em tabelas com fonte de máquina de escrever e em grades com números; e texto todo em maiúsculas girado 180 graus que o OSD vê como reto pode continuar de cabeça para baixo.
- **Original intacto:** o PDF original é copiado byte a byte (hash inalterado). O texto reconhecido entra no mesmo derivado paginado `D###_texto_pdf.md`, com a página física do original, de modo que o índice SQLite/FTS5 e o leitor de fontes o usem sem mudanças e as citações abram a página correta do original.
- **Origem por página:** o cabeçalho do derivado lista `texto_nativo` ou `ocr` por página; o manifesto guarda o mesmo em `paginas_origem` do derivado e, em `extracao_pdf`, `paginas_texto_nativo`, `paginas_ocr`, `paginas_sem_texto`, `paginas_com_erro` (com `etapa` `extracao` ou `ocr`), `ocr_tentado` e `ocr_motor` (motor, versões do OCRmyPDF/Tesseract/Ghostscript ou PyMuPDF e idiomas realmente usados). O resumo do recibo traz as contagens (`paginas_texto_nativo`, `paginas_ocr`, `paginas_sem_texto`, `paginas_com_erro`, `protegidos`).
- **PDF protegido por senha:** não é lido nem reconhecido; o original é preservado e o recibo indica `protegido` (estado `erro`).
- **Reprocessar o que já está cadastrado:** `python scripts/cadastrar_documentos.py --caso ID --preparar-pdfs` aplica OCR aos PDFs cujas páginas sem texto ainda não passaram por OCR (ou cujo OCR falhou) e publica uma **nova versão do corpus**, com novo derivado que substitui o anterior no manifesto atual (`substitui_sha256`). Rodadas e índices anteriores permanecem intactos; o OCR concluído não é repetido.

Variáveis de ambiente (lidas pelo processo que executa o cadastro):

| Variável | Efeito | Padrão |
|---|---|---|
| `VLADO_OCR=0` | desliga o OCR (o PDF fica como antes, com páginas sem texto) | ligado |
| `VLADO_OCR_IDIOMAS` | idiomas do Tesseract, ex.: `por+eng` | `por+eng` |
| `VLADO_TESSERACT` | caminho do executável do Tesseract | `PATH`, depois `C:\Program Files\Tesseract-OCR\tesseract.exe` |
| `VLADO_TESSDATA` | pasta com os `*.traineddata` (`por`, `eng`, `osd`) **e a subpasta `configs/`**, que o OCRmyPDF exige; sem ela o motor principal não funciona e, em `auto`, o Vlado usa a alternativa | `%LOCALAPPDATA%\vlado\tessdata`, se existir |
| `VLADO_OCR_MOTOR` | `auto`, `ocrmypdf` ou `tesseract` | `auto` |
| `VLADO_OCR_TIMEOUT` | segundos por página antes de abortar o processo | 180 |

Os subprocessos rodam sem abrir janelas de console no Windows, com saída capturada e tempo limite. No Docker, `Dockerfile` instala `tesseract-ocr`, `-por`, `-eng`, `-osd`, `ghostscript`, `pngquant` e `unpaper`, e `requirements.txt` fixa `ocrmypdf==16.10.4`. No Windows o Ghostscript não é obrigatório: sem ele, a alternativa PyMuPDF + Tesseract é usada automaticamente. Se nenhum motor estiver disponível, o cadastro segue como antes e o recibo informa `ocr_indisponivel`.

Limites: OCR não é perfeito. Pode errar letras, números, nomes, tabelas, manuscritos, carimbos e colunas, e trocar a ordem de leitura. O recibo e a cobertura do índice não atestam fidelidade: confira sempre a página no original antes de usar uma passagem como evidência. O OCR roda durante o cadastro e pode levar segundos por página; PDFs grandes alongam a requisição. Imagens avulsas (PNG/JPG) não passam por OCR, a menos que o cadastro seja chamado com `--ocr-imagens` (ver abaixo).

## Extração de DOCX e XLSX

`scripts/extrair_office.py` lê os pacotes só com `zipfile` e `xml.etree` da biblioteca padrão, sem rede, sem modelo, sem resolver DTD/entidades e com limite de tamanho descompactado. O cadastro grava `derivados/D###_texto_docx.md` ou `D###_texto_xlsx.md` e registra no manifesto `tipo` (`texto_extraido_docx`/`texto_extraido_xlsx`), `origem` (`extracao_docx`/`extracao_xlsx`), `versao_extrator`, `metodo`, `origem_sha256` e o hash do derivado. O resultado completo fica em `extracao_office` do documento (estado `extraido`, `parcial`, `sem_texto` ou `erro`, `recusa`, `mensagem`, `contagens`, `abas`, `falhas`, `avisos`).

- **DOCX:** parágrafos e células de tabela em ordem, com localizador `P0001` ou `T01 L02 C03` (tabela, linha, coluna da grade); cabeçalhos (`CAB1 P0001`), rodapés (`ROD1 P0001`), notas (`NOTA 1 P0001`, `NOTAFIM 1 P0001`) e comentários (`COMENT 1 P0001`) quando existirem.
- **XLSX:** cada célula preenchida de cada aba com `Aba!A1` (aba entre aspas quando o Excel exigiria), valor gravado, valor exibido para formato numérico simples e fórmula como texto, sem avaliar.
- **Recusas legíveis:** arquivo com macro (`.docm`, `.xlsm` ou `vbaProject`), protegido por senha, corrompido ou acima dos limites continua cadastrado como original, sem derivado, com `estado: erro`, `recusa` e mensagem. O lote não é abortado. Reenviar o mesmo arquivo tenta de novo; uma extração legível não é repetida.
- **Recibo:** `extracao_office_resumo` conta documentos, processados agora, DOCX/XLSX, estados, parágrafos, tabelas, células de tabela, abas, células, fórmulas, falhas e recusas por motivo.

Extrair não é ler nem validar: valores, datas e fórmulas da cópia de trabalho precisam ser conferidos no original antes de virar evidência.

## OCR de imagens avulsas (opcional)

```powershell
python scripts/cadastrar_documentos.py --caso minha_apuracao --documentos entrada/foto.png --ocr-imagens
```

Desligado por padrão. Com `--ocr-imagens`, cada PNG/JPEG do lote passa pela CLI local do Tesseract (`scripts/ocr.py`, mesma configuração `VLADO_*` da tabela acima), sem enviar a imagem a serviço externo e sem modelo. O derivado `D###_texto_ocr.md` entra no manifesto com `tipo: texto_ocr_imagem`, `origem: ocr`, motor, versões, idiomas e o aviso de que o texto precisa ser conferido no original; o documento recebe `ocr_imagem` com o estado. A rotação detectada pelo OSD é só avisada, não corrigida. Sem Tesseract (ou com `VLADO_OCR=0`), a imagem fica `pendente`, sem derivado, com mensagem clara; reenviar a imagem com a opção depois de instalar o motor tenta de novo. O recibo traz `ocr_imagens_resumo` (solicitado, imagens, processadas agora, extraído, sem texto, pendente, erro, sem OCR).

## Preservação e conferência

- Cada arquivo enviado aparece no recibo, inclusive duplicatas por SHA-256. Bytes iguais usam o ID existente; nomes iguais com bytes diferentes recebem IDs distintos e nunca sobrescrevem originais.
- Novos documentos ou preparação de derivados incrementam a versão do corpus, mantêm os IDs anteriores e reiniciam a aprovação do piloto/teste principal para o corpus alterado. Reenvio só de duplicatas com extração já preparada preserva versão e protocolo, acrescentando o recibo.
- Os originais novos e registros ficam em `casos/<id>/cadastros/<lote>/`: `originais/`, `recibo.json`, `manifesto_cadastrado.json` e, em acréscimos, `manifesto_anterior.json`. O manifesto atual autoriza documentos e registra hashes dos recibos. Arquivos já cadastrados por versões anteriores permanecem nos caminhos anteriores.
- O lote é validado e copiado antes da publicação. A publicação usa troca de metadados e restauração em falhas detectadas; cadastro e congelamento de rodada compartilham uma trava, recusando a segunda operação enquanto a primeira estiver em andamento. Não sobrescrever recibos ou rodadas anteriores.
- Quando a pergunta chegar, `nova_rodada.py` confere integridade e congela documentos, manifesto e recibos da versão atual. Hash divergente ou recibo ausente impede a criação da rodada. A rodada anterior conserva seus documentos e seu índice.

Pendências de anexos conhecidos pelo chat precisam ser resolvidas ou explicitamente excluídas pelo usuário antes de criar a rodada. O script só pode conferir arquivos e recibos que lhe foram informados; não consegue descobrir anexos omitidos pelo operador. O recibo deve ser confrontado com o envio original, não apenas com os arquivos que puderam ser abertos.

O restante do fluxo continua após a pergunta: snapshot, índice da rodada, cobertura, planejamento, pesquisa, cruzamento, revisão e briefing. O cadastro prepara o texto dos PDFs (nativo ou por OCR local), mas não executa inferência nem análise editorial. A inferência ocorre online, pela API do provedor configurado, somente depois da pergunta. O cadastro não constitui piloto editorial.
