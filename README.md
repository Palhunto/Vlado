# VLADO

**Versão 1.4.0** (aplicação) · **Instalador 2.1.0** · Licença pendente de decisão do grupo ([AVISOS_DE_LICENCA.md](docs/AVISOS_DE_LICENCA.md))

O Vlado é um assistente de apuração documental. Ele organiza documentos de uma pauta jornalística, responde perguntas com citação de fonte e registra cada afirmação ao documento, à página ou à célula que a sustenta. A revisão final é sempre humana: o sistema organiza e aponta, e não aprova nada por conta própria.

Cadastro, índice e registros não fazem chamadas a modelos. A inferência ocorre somente quando uma pergunta ou complemento é enviado pela Mesa de apuração, pela API do provedor configurado (Anthropic ou OpenAI), com processamento online e cobrança por uso.

## Estado do projeto

- A [release v2.1.0](https://github.com/Palhunto/Vlado/releases/tag/v2.1.0) publica o instalador Windows e o arquivo de verificação SHA-256. O instalador ainda não foi testado numa instalação limpa neste ambiente.
- O projeto é genérico e começa sem nenhum caso ativo. Os resultados desta distribuição são de manutenção e usam materiais sintéticos; não constituem piloto editorial.
- As pendências conhecidas estão listadas ao final deste documento.

## Principais recursos

**Cadastro e leitura de documentos**
- Cópias preservadas de cada original, com ID, hash e recibo por lote, incluindo duplicatas e falhas. O cadastro ocorre antes de qualquer pergunta.
- Extração textual de PDFs com `pypdf`; OCR local (OCRmyPDF e Tesseract) somente nas páginas sem texto nativo, com origem registrada página a página.
- DOCX e XLSX lidos com localizador de parágrafo, tabela ou `Aba!A1`. Fórmulas são gravadas como texto, sem avaliação.

**Perguntas e análise**
- Cada pergunta congela documentos e recibos numa rodada própria, constrói um índice SQLite/FTS5 e executa seis etapas: planejamento, busca, cruzamento assistido, revisão e briefing.
- Complementos preservam o corpus anterior e criam novas rodadas; novos documentos entram numa versão ampliada do corpus.
- Respostas renderizam Markdown com fontes citadas por título e página; hashes, versões e registros ficam em **Detalhes técnicos**.

**Achados e revisão humana**
- Na Mesa, **Conferir** abre as fontes de cada achado da IA, e a pessoa registra um estado: Pendente, Conferida no original, Precisa de ajuste ou Sem suporte suficiente.
- A avaliação humana é salva separadamente, com histórico, e preserva o texto original da IA.
- Correções podem ser levadas à próxima pergunta, com prévia das observações e suas fontes.

**Quadros de evidência**
- **Hipóteses:** o que sustenta, o que contraria e o que falta para cada hipótese.
- **Linha do tempo:** acontecimentos com tipos de data separados e datas parciais.
- **Comparador:** dois trechos ou documentos, com diferenças de valor e de data destacadas no contexto.
- **Mapa de relações:** pessoas e organizações, com evidência em cada ligação e sugestões de homônimos que nunca fundem entidades.
- **Tabelas de apuração:** fonte por célula, correção manual com justificativa e histórico, e cálculos declarados (soma, diferença, contagem e média) sem conversão entre moedas ou unidades.

**Redação, entrevistas e pedidos**
- **Conferência da redação:** o texto é dividido em afirmações, cada uma ligada às evidências do caso. Regras fixas apontam número divergente da fonte, quantificador mais forte, causalidade sem suporte e certeza onde a fonte apenas atribui. Só uma conta autenticada pode marcar uma afirmação como revisada por humano.
- **Entrevistas e pedidos:** lacunas viram perguntas por modelo fixo de texto, ligadas a uma diligência (entrevista, pedido de informação ou LAI).

**Fontes web por apuração (opcional)**
- Cada apuração escolhe, na criação, entre **somente documental** (padrão) e **documentos + web**.
- No segundo modo, a captura é restrita a um único site, informado pelo jornalista, e só ocorre a pedido explícito dele.
- Cada captura recebe ID (`W001`, `W002`…), conteúdo bruto, cópia de texto, endereço pedido e final, data e hora do acesso em UTC, situação HTTP e SHA-256. Redirecionamentos são conferidos a cada salto, e endereços internos ou privados são recusados.
- Texto escondido por CSS externo não é detectado. A limitação está descrita na seção "Decisões e pendências", abaixo.

**Caderno, diligências e continuidade**
- **Caderno:** notas em Markdown com prévia, trechos com fonte e contribuições humanas, exportáveis em Markdown, PDF ou DOCX.
- **Diligências:** responsável, prazo, estado e histórico, com respostas documentais vinculadas e possibilidade de reexame numa nova rodada.
- **Rascunhos e retomada:** a pergunta em preparo é salva enquanto se digita, primeiro no navegador e depois no servidor, por conta. Ao reabrir, a Mesa oferece restaurar ou descartar.

**Interface**
- Mesa de apuração em HTML, CSS e JavaScript, com modo claro e escuro, português e inglês, e área de achados e de caderno.
- Lixeira com exclusão reversível de apurações, conversas e rodadas; a exclusão preserva os arquivos.
- Aplicativo Android com os sabores `sala` e `redacao` (ver [docs/ANDROID.md](docs/ANDROID.md)).

## Fluxo de uma apuração

1. O agente de chat ou a Mesa recebe os documentos e cadastra cada lote, com recibo, antes da pergunta.
2. Com todos os lotes conferidos, a pergunta cria uma rodada com snapshot dos documentos.
3. As seis etapas do fluxo automático produzem os achados, que são publicados e verificados.
4. A revisão humana registra a conferência de cada achado no original.
5. O caderno, os quadros e as diligências usam somente as evidências já registradas.

O detalhamento de cada etapa está em [docs/FLUXO_AUTOMATICO_CODEX.md](docs/FLUXO_AUTOMATICO_CODEX.md) e o percurso completo, do caso à revisão humana, em [docs/FLUXO_PONTA_A_PONTA.md](docs/FLUXO_PONTA_A_PONTA.md).

## Instalação

### Windows, pelo instalador

O **Vlado-Setup.exe** inclui Tesseract, Ghostscript e as bibliotecas necessárias, cria atalhos e pede a criação do administrador na primeira abertura. Não exige Python instalado. Guia completo em [docs/INSTALADOR_WINDOWS.md](docs/INSTALADOR_WINDOWS.md).

Antes de executar, confira o hash com o valor publicado na mesma release:

```powershell
certutil -hashfile Vlado-Setup.exe SHA256
```

O valor deve ser igual ao do arquivo `Vlado-Setup.exe.sha256`. A release 2.1.0 foi gerada a partir da tag `v2.1.0`, no commit `e66aba0`.

### Pelo repositório (desenvolvimento)

- **Abrir mesa.vbs** inicia o serviço em segundo plano e abre o navegador, sem terminal visível.
- **Iniciar pesquisa.cmd** faz o mesmo com console visível.
- **Preparar notebook.cmd** prepara outro Windows: usa o `.venv` do projeto ou um Python 3.12+ do sistema, cria o `.venv`, instala as dependências (`scripts/preparar_notebook.py`) e indica como definir a chave da API.

A versão distribuída abre com catálogo vazio.

## Configuração e chaves

- O provedor e o modelo ficam em `configuracao.json`. Na Mesa, **Perguntar à IA › Conexão e opções** permite escolher o provedor, colar a chave e salvar.
- A chave é guardada em `segredos/chaves.json`, fora do git, ou em variável de ambiente (`ANTHROPIC_API_KEY` ou `OPENAI_API_KEY`), que tem prioridade.
- O navegador só recebe se há chave e os quatro últimos caracteres. Chaves nunca entram em configuração, logs, eventos, rascunhos ou git.
- Os clientes são fixados em `anthropic==2.8.0` e `openai==3.50.0`. Dependências em [requirements.txt](requirements.txt). `scripts/ambiente.py` informa, de forma booleana, se os SDKs e as chaves estão disponíveis.

## Estrutura do repositório

| Pasta | Conteúdo |
| --- | --- |
| `prompts/` | Sete módulos de prompt e o fluxo completo, com hashes ([README](prompts/README.md)) |
| `scripts/` | Cadastro, índice, rodadas, fluxo, quadros, redação, fontes web e integração com a API ([README](scripts/README.md)) |
| `interface/` | Mesa de apuração (HTML, CSS, JavaScript), com Vditor e PDF.js em `vendor/` e fontes em `fonts/` |
| `testes/` | `test_*.py` executados por `unittest discover`; `qa_*.py` que dirigem o navegador com o `.cjs` de mesmo nome |
| `casos/` | Catálogo das apurações (`catalogo.json`); cada caso tem originais, manifesto e cadastros próprios |
| `execucoes/` | Snapshots e saídas por caso e rodada |
| `entrada/` | Local para documentos de outra pauta antes do cadastro ([README](entrada/README.md)) |
| `modelos/` | Formatos vazios de achados, evidências, revisão e retorno humano ([README](modelos/README.md)) |
| `instalador/` | Gerador do Vlado-Setup.exe (PyInstaller e Inno Setup), dependências fixadas e termo de uso |
| `deploy/` | Caddy e variáveis de ambiente de homologação, editorial e demonstração; arquivos `.env` reais ficam fora do git |
| `android/` | Aplicativo Android |
| `docs/` | Guias de uso, verificação, integração, migração e changelog ([CHANGELOG.md](docs/CHANGELOG.md)) |
| `proveniencia/` | Origem do repositório de referência, sem uso como entrada de apuração |

Pastas de trabalho de agentes (`.claude/` e `.maestro/`) estão fora do versionamento, com exceção de `.maestro/equipe/CONTRATO_EVIDENCIA.md`.

## Privacidade e limites

- Usar somente documentos públicos ou materiais sintéticos identificados como tal.
- A inferência é online, no provedor configurado, e é cobrada por uso. Não há garantias adicionais de retenção ou tratamento na conta do provedor. O que é enviado a cada chamada está descrito em [docs/DADOS_NA_INFERENCIA.md](docs/DADOS_NA_INFERENCIA.md).
- O OCR é local, mas seu texto é reconhecimento automático e não substitui a conferência no original.
- A ausência de um resultado de busca não prova ausência no acervo.
- Instruções de projeto (`AGENTS.md`) orientam o agente de chat, mas não constituem bloqueio técnico de rede ou de acesso a pastas.
- A integração por API teve três ensaios pagos com o provedor OpenAI, registrados em [docs/VERIFICACAO.md](docs/VERIFICACAO.md). O provedor Anthropic, que é o padrão, ainda não rodou com chave real. O estado está em [docs/INTEGRACAO_API.md](docs/INTEGRACAO_API.md).
- Para a Mesa hospedada (ambientes separados, contas com login, Docker, HTTPS, limites de gasto, backup e recuperação), ver [docs/GUIA_TECNICO_IMPLANTACAO.md](docs/GUIA_TECNICO_IMPLANTACAO.md).

## Verificações técnicas

Os scripts usam Python 3.12+ com SQLite/FTS5.

```powershell
python scripts/montar_fluxo.py --check
python scripts/verificar_projeto.py
python -m unittest discover -s testes -v
```

Essas verificações confirmam integridade de arquivos e scripts. Não avaliam a qualidade das respostas do assistente, que depende de piloto estabilizado em cada caso. Os resultados registrados estão em [docs/VERIFICACAO.md](docs/VERIFICACAO.md).

## Documentação

- [Guia da interface](docs/INTERFACE_PESQUISA.md) e [cadastro antes da pergunta](docs/CADASTRO_DOCUMENTOS.md)
- [Integração com a API](docs/INTEGRACAO_API.md) e [banco SQLite](docs/BANCO_SQLITE.md)
- [Achados da IA](docs/ACHADOS_IA.md) e [continuidade documental](docs/CONTINUIDADE_DOCUMENTAL.md)
- [Caderno](docs/CADERNO_APURACAO.md), [diligências](docs/DILIGENCIAS.md) e [redação](docs/GUIA_RAPIDO_REDACAO.md)
- [Procedimento de calibração, sem gabarito](docs/PILOTO.md)
- [Migração e procedência](docs/MIGRACAO.md) e [proveniencia/origem_repositorio.json](proveniencia/origem_repositorio.json)

## Decisões e pendências

**Decisões tomadas**
- **Texto escondido por CSS nas capturas:** só o que o próprio HTML esconde (atributo `hidden`, `aria-hidden="true"`, `display:none` ou `visibility:hidden` no `style`) é retirado e marcado com `contem_texto_oculto`. Ocultação por CSS externo, `opacity:0`, `font-size:0`, posicionamento fora da tela e `<details>` fechado não é detectada. Se as fontes web passarem a alimentar o modelo sem leitura humana, a decisão será revista, e a alternativa será renderizar a página num navegador.
- **`innerHTML` do editor de notas:** exceção aceita, com três barreiras: a limpeza do Lute (`sanitize`), a remoção de `<iframe>`, `<object>` e `<embed>` pelo editor e a política de segurança da página (CSP). `testes/editor_notas_seguranca.cjs` verifica as três.

**Pendências**
- **Formulários da redação:** vincular evidência a uma afirmação e enviar nova versão do texto já existem nas rotas (`redacao-vincular`, `redacao-nova-versao`), mas ainda não têm formulário na Mesa. Estão previstos para a fase 10.
- **Mensagens do preparador do notebook:** `Preparar notebook.cmd` e `scripts/preparar_notebook.py` indicam o arquivo `INSTALAR_NO_NOTEBOOK.md`, que não existe mais no repositório. A mensagem precisa ser corrigida.
- **Testes sem executor:** dez arquivos `.cjs` em `testes/` (`compositor`, `conferencia_original`, `erros_en`, `i18n_codex_en`, `lixeira_apagar`, `primeiro_uso`, `qa_comportamentos`, `redacao_entrevistas`, `retomar_conversa` e `versao_achados`) testam funcionalidades, mas nenhum script os executa. Precisam de um `qa_*.py` que os chame ou devem ser removidos.
- **Instalação limpa:** o instalador 2.1.0 precisa de teste de instalação e primeiro uso antes de distribuição.
- **Licença:** o repositório ainda não declara licença para o código; a decisão cabe ao grupo.

**Versões**
- `2.1.0` é a versão do instalador e da release (`instalador/vlado.iss` e `instalador/dependencias.json`).
- `1.4.0` é a versão da aplicação, no campo `versao` de `configuracao.json`.
- Os prompts têm versão própria (`1.4.1`, em `scripts/comum.py`).
- O detalhamento das mudanças por versão está em [docs/CHANGELOG.md](docs/CHANGELOG.md).
