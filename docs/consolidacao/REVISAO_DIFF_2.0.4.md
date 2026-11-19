---
type: report
title: Revisão do diff local da entrega 2.0.4
created: 2026-11-19
tags: [consolidacao, windows, docker, 2.0.4]
related: ['[[VERIFICACAO]]', '[[INSTALADOR_WINDOWS]]', '[[GUIA_TECNICO_IMPLANTACAO]]']
---

# Revisão do diff local da entrega 2.0.4

Revisão do diff não commitado sobre `9b8f38e` (`chore: ignora pacotes compactados da entrega`), feita na branch `codex/consolidacao-vlado` em 19/11/2026. São 16 arquivos modificados, com 177 inserções e 37 remoções, mais o arquivo novo `instalador/TERMO_DE_USO.txt`. Para cada arquivo, li o `git diff -- <arquivo>` e o código ao redor de cada trecho. Esta revisão não executou testes; isso fica para a próxima tarefa da fase (ver [[VERIFICACAO]]).

## Resumo por grupo

| Grupo | Arquivos |
| --- | --- |
| Windows 2.0.4 | `scripts/nova_rodada.py`, `scripts/codex_apuracao.py`, `scripts/registros_achados.py`, `scripts/vlado_lancador.py`, `scripts/gerar_instalador.py`, `instalador/vlado.spec`, `instalador/vlado.iss`, `instalador/dependencias.json`, `testes/test_achados.py`, `testes/test_extracao_cadastro_pdf.py`, `docs/INSTALADOR_WINDOWS.md` |
| Termo de uso | `instalador/TERMO_DE_USO.txt` (novo, não rastreado; SHA-256 registrado em `.maestro/playbooks/Initiation/Working/estado_inicial.md`). Uma linha de `instalador/vlado.iss` (`LicenseFile`) também pertence a este grupo; ver a seção de riscos. |
| Docker | `.dockerignore`, `Dockerfile`, `docker-compose.yml`, `deploy/ambientes/homologacao.env.example`, `docs/GUIA_TECNICO_IMPLANTACAO.md` |
| Documentação | Dentro dos grupos acima: `docs/INSTALADOR_WINDOWS.md` (Windows) e `docs/GUIA_TECNICO_IMPLANTACAO.md` (Docker). |

## Windows 2.0.4

### `scripts/nova_rodada.py`

- **O que mudou:** adiciona o gerenciador de contexto `preparar_pasta_rodada(destino)`. Ele recusa um destino que já existe, prepara a rodada em `execucoes/.r_<uuid>/<rodada>` (via `comum.pasta_preparacao`, que herda a ACL da pasta-mãe) e só renomeia para `execucoes/<caso>/<rodada>` quando o bloco termina sem erro. `_criar_rodada` agora usa esse helper. Antes, a preparação ficava em `execucoes/<caso>/.preparacao_<uuid>/<rodada>`. A verificação de existência e o `rename` saíram de `_criar_rodada` e foram para o helper.
- **Problema resolvido:** o caminho temporário repetia o ID do caso e acrescentava um prefixo longo. Com IDs de caso longos e nomes de PDF longos, `entradas/...` passava do limite Win32 tradicional (248 caracteres para pastas, 260 para arquivos), e a primeira pergunta falhava com `[Errno 2]`. Agora o comprimento do caminho temporário não depende do ID do caso.
- **Riscos e inconsistências:**
  - `destino.parent.parent` pressupõe que o destino seja `execucoes/<caso>/<rodada>`. Os dois chamadores atuais respeitam esse formato, mas o helper não valida isso.
  - Em caso de exceção dentro do bloco, o `yield` propaga o erro, o `rename` não acontece e o `finally` de `pasta_preparacao` remove a pasta temporária. O comportamento está correto.
  - Se o processo for interrompido de forma abrupta (energia, kill), pode sobrar um `.r_*` direto em `execucoes/`, e não mais dentro da pasta do caso. Nenhum código encontrado lista os filhos de `execucoes/` como casos. Ainda assim, `scripts/backup.py` copia `execucoes` inteira e levaria a sobra junto. Antes, isso também acontecia dentro da pasta do caso.
  - Em POSIX, `rename` sobre uma pasta vazia existente a substitui silenciosamente. A proteção depende da verificação prévia e da trava `_trava`, que ambos os chamadores mantêm. Esse comportamento já existia antes da mudança.

### `scripts/codex_apuracao.py`

- **O que mudou:** o congelamento de complementos (`Conversas._freeze`, ramo que copia `entradas/` da rodada-base) passou a usar `preparar_pasta_rodada(destination)`, no lugar de `pasta_preparacao(parent, '.preparacao_conversa_')` seguido de `mkdir` e `rename` manuais. O import de `pasta_preparacao`, que ficou sem uso, foi removido.
- **Problema resolvido:** é a mesma falha de caminho longo, agora na passagem de R001 para R002 (complementos). As duas operações passam a usar a mesma pasta temporária curta, como decidido pelo usuário.
- **Riscos e inconsistências:**
  - A rodada só é publicada (`run = destination`) depois de `construir_snapshot`, o que preserva a atomicidade de antes.
  - A verificação de destino existente passou a valer também para complementos. Antes, ela não existia nesse ramo, e o `rename` falharia de qualquer forma no Windows.
  - Nenhum outro uso de `pasta_preparacao` foi removido indevidamente: `apuracao.py`, `caderno.py`, `diligencias.py` e `revisao_humana.py` continuam com `.preparacao_` dentro das próprias pastas, fora do escopo desta correção.

### `scripts/registros_achados.py`

- **O que mudou:** quando `sys._MEIPASS` existe (executável PyInstaller), `SCHEMA` aponta para `<_MEIPASS>/modelo_dados/modelos/ACHADOS.schema.json`. Fora do executável, continua resolvendo pelo repositório.
- **Problema resolvido:** no executável, `Path(__file__).parents[1]` caía na pasta do programa, onde `modelos/` não existe. A validação da geração inicial falhava antes da revisão. `instalador/vlado.spec` já empacotava `modelos/` em `modelo_dados/modelos`, então o novo caminho corresponde ao que o pacote contém.
- **Riscos e inconsistências:**
  - O padrão de resolução é diferente do usado em `interface_pesquisa.py` (`ASSETS` via `getattr(sys, '_MEIPASS', ...)`) e em `vlado_lancador.pasta_pacote()`. Não há helper comum para recursos empacotados, o que aumenta o risco de o mesmo erro reaparecer em outro módulo.
  - Nenhum outro módulo do diff lê `modelos/` ou `prompts/` por `__file__`. Os `ROOT = parents[1]` de `comum.py`, `acesso.py` e `backup.py` são anteriores a esta mudança e não foram avaliados aqui.

### `scripts/vlado_lancador.py`

- **O que mudou:** adiciona `_verificar_https()` e o atalho `principal(['--verificar-https'])`. Esse modo instancia os provedores OpenAI e Anthropic com a chave fictícia `vlado-build-test-key` (literal de teste, não é segredo), fecha os clientes e devolve 0 em caso de sucesso, 1 se a OpenAI falhar e 2 se a Anthropic falhar. Não faz requisição de rede. O atalho roda antes de `pasta_dados()`, da instância única e do redirecionamento de saídas.
- **Problema resolvido:** permite detectar no build a falha de inicialização TLS do 2.0.2 (arquivo de lista de CAs ausente), sem custo de API.
- **Riscos e inconsistências:**
  - O `except Exception` descarta a mensagem. O build fica sabendo qual provedor falhou, mas não o motivo. Como é um executável `--noconsole`, também não há traceback visível.
  - A comparação exata `argv == ['--verificar-https']` impede combinar esse modo com outros argumentos, o que é aceitável para um modo de diagnóstico.
  - O modo só verifica a construção do contexto TLS. Não verifica a cadeia de certificados nem a conectividade.

### `scripts/gerar_instalador.py`

- **O que mudou:** depois do PyInstaller e antes do Inno Setup, executa `build/instalador/pyinstaller/Vlado/Vlado.exe --verificar-https` (timeout de 60 s). O build para em caso de código diferente de 0. A docstring também foi atualizada.
- **Problema resolvido:** impede publicar um instalador cujo executável não consegue inicializar HTTPS.
- **Riscos e inconsistências:**
  - A verificação também roda com `--pular-pyinstaller`. Nesse caso, ela testa um executável antigo, se houver um. Se não houver, `subprocess` lança `FileNotFoundError` em vez da mensagem `SystemExit` padronizada de `executar`.
  - Um `TimeoutExpired` também escapa sem mensagem própria.
  - Os dois casos afetam só a mensagem de erro, não a correção do resultado.

### `instalador/vlado.spec`

- **O que mudou:** se `codex-rejected-cas.pem` existir ao lado de `ssl.py` no Python de build, ele entra no pacote na raiz de `_internal`.
- **Problema resolvido:** a distribuição Python usada no build lê essa lista de desconfiança ao criar cada contexto TLS. Sem o arquivo, o executável 2.0.2 falhava com `[Errno 2]` antes da primeira chamada à API.
- **Riscos e inconsistências:**
  - O arquivo não faz parte do Python oficial: indica um Python de build modificado. O build depende de qual interpretador está em `.venv`. Com um Python padrão, o arquivo não existe e nada é incluído, o que é correto. Com outro Python modificado, o nome ou o local podem ser diferentes. A reprodutibilidade do build depende de registrar qual Python foi usado, e `docs/INSTALADOR_WINDOWS.md` não registra isso.
  - O destino `'.'` pressupõe que, no executável, o `ssl` procure o arquivo ao lado de `_internal/ssl.*`. A verificação `--verificar-https` no build é o que confirma esse pressuposto.

### `instalador/vlado.iss`

- **O que mudou:** a versão padrão passa de `2.0.0` para `2.0.4`. O `LicenseFile` deixa de ser `payload\licencas\AVISOS_DE_LICENCA.txt` e passa a ser `TERMO_DE_USO.txt`, relativo à pasta do `.iss`.
- **Problema resolvido:** a página de licença do assistente passa a mostrar o termo de uso aprovado. Os avisos de licença de terceiros continuam instalados em `{app}\licencas` (seção `[Files]`, linha `payload\licencas\*`).
- **Riscos e inconsistências:**
  - **Dependência entre commits.** A linha `LicenseFile` pertence logicamente ao grupo "termo de uso", mas o plano da fase coloca `vlado.iss` no commit `fix:` e o termo no commit seguinte. Nesse intervalo, o commit `fix:` referencia um arquivo que ainda não está no git. Não é possível dividir o arquivo com `git add -p` sem interação. Conforme a regra da tarefa, a linha fica no commit mais próximo (`fix:`), e o próximo commit (`feat:`) adiciona o termo.
  - A versão também aparece em `instalador/dependencias.json`, mas `gerar_instalador.py` sempre passa `/DVersao=` a partir desse JSON. O valor padrão do `.iss` só vale em compilação manual.

### `instalador/dependencias.json`

- **O que mudou:** `versao_vlado` passa de `2.0.0` para `2.0.4`.
- **Problema resolvido:** alinha a versão exibida e embutida no instalador com a entrega.
- **Riscos e inconsistências:**
  - As versões 2.0.1, 2.0.2 e 2.0.3, citadas em `docs/INSTALADOR_WINDOWS.md`, não têm commit nem registro em `docs/VERIFICACAO.md`, cujo último registro é o 2.0.0.
  - `.env.example` e `deploy/ambientes/*.env.example` continuam com `VLADO_VERSAO=2.0.0`, embora seja a tag da imagem Docker, um eixo diferente.
  - Essas inconsistências de versão ficam para a fase de versões e documentação.

### `testes/test_achados.py`

- **O que mudou:** novo teste `test_schema_carregado_do_pacote_windows`. Ele copia o esquema para um `_internal/modelo_dados/modelos` temporário, simula `sys._MEIPASS` e recarrega `registros_achados.py` com `runpy.run_path`. Depois confere `SCHEMA` e valida a fixture de achados.
- **Problema resolvido:** cobre a regressão do esquema no executável sem precisar do PyInstaller.
- **Riscos e inconsistências:** `run_path` cria uma cópia isolada do módulo e não afeta o módulo importado pelos outros testes. O teste não prova que o `vlado.spec` real empacota o esquema nesse caminho: ele reproduz a estrutura por convenção.

### `testes/test_extracao_cadastro_pdf.py`

- **O que mudou:** novo teste `test_primeira_pergunta_e_complemento_com_limite_de_caminho_do_windows`, pulado sem `pypdf`.
  - O teste simula uma raiz Windows fictícia (`C:\Users\teste\AppData\Local\Vlado`, sem dado pessoal) e substitui `shutil.copyfile` e `shutil.copytree` em `nova_rodada` e `codex_apuracao` por versões que recusam caminhos acima de 248 ou 259 caracteres.
  - Com um ID de caso de 41 caracteres e dois nomes de PDF (curto e longo), executa R001 e o complemento R002 pelas seis etapas, usando `FakeServer` e `agente_fluxo_fixture`, sem chamada à API.
  - Depois confere que R001 continua intacta pelos hashes, que o original e o derivado estão na R002 com o SHA-256 do manifesto, que a busca na R002 encontra o texto e que não sobrou `.r_*`.
- **Problema resolvido:** documenta e protege a correção de caminhos temporários, incluindo R001→R002.
- **Riscos e inconsistências:**
  - O limite é simulado só nas cópias. Gravações de snapshot, índice SQLite e registros não passam pela simulação, e o teste não roda em um Windows real com `LongPathsEnabled` desligado.
  - Substituir o módulo `shutil` inteiro por um mock é seguro hoje, porque os dois módulos só usam `copyfile` e `copytree`. Um uso futuro de outra função de `shutil` nesses módulos viraria um no-op silencioso durante o teste.
  - O teste importa `test_codex_integracao` e `agente_fluxo_fixture` como módulos de nível superior. Funciona com `python -m unittest discover -s testes`, mas não com `python -m unittest testes.test_extracao_cadastro_pdf` a partir da raiz.
  - **Dado possivelmente real:** um dos nomes de PDF sintéticos parece derivado do nome de um documento de caso real, com nome de empresa e data. O conteúdo do PDF é sintético. Só o nome aparece no teste, e o valor não é reproduzido aqui. Recomendo trocar por um nome neutro de mesmo comprimento numa fase seguinte. Não alterei o arquivo nesta revisão.

### `docs/INSTALADOR_WINDOWS.md`

- **O que mudou:**
  - Três parágrafos novos sobre o 2.0.2 (pasta temporária curta), o 2.0.3 (`codex-rejected-cas.pem`) e o 2.0.4 (esquema de achados), com a instrução de usar **Tentar novamente**.
  - Tabela atualizada para 2.0.4: 133.974.955 bytes (127,8 MiB) e SHA-256 `574da2e0…cab5fe`.
  - Novo parágrafo sobre `--verificar-https` no build.
- **Problema resolvido:** registra para quem instala e para quem gera o instalador o que mudou e como conferir o hash.
- **Riscos e inconsistências:**
  - O SHA-256 da tabela confere com `dist/Vlado-Setup.exe` atual (calculado nesta revisão) e com `dist/Vlado-Setup.exe.sha256`.
  - A linha "Arquivo" perdeu o prefixo `dist/`, mas a seção de build continua dizendo "Saída: `dist\Vlado-Setup.exe`". A diferença é pequena e pode ser intencional (arquivo entregue ao usuário).
  - A seção "Teste do instalador (15/11/2026 … build 0bc6a6ff…)" continua descrevendo o 2.0.0. Não há registro equivalente de teste manual do 2.0.4.
  - O guia não menciona que a página de licença do assistente agora mostra o termo de uso.
  - Não registra qual Python de build fornece `codex-rejected-cas.pem`.

## Termo de uso

### `instalador/TERMO_DE_USO.txt` (novo)

- **O que mudou:** novo arquivo, não rastreado, usado como `LicenseFile` do Inno Setup.
- **Problema resolvido:** mostra o termo de uso aprovado pelo usuário na instalação.
- **Riscos e inconsistências:**
  - O conteúdo não foi alterado nem avaliado editorialmente, conforme as regras da fase.
  - O SHA-256 salvo em `Working/estado_inicial.md` deve ser conferido antes do commit `feat:`.
  - Ver acima a dependência com `vlado.iss`.

## Docker

### `.dockerignore`

- **O que mudou:**
  - Passa a excluir do contexto de build `.ferramentas`, `build`, `dist`, `entrega_intercept`, `entrega_intercept.*` e `android/saidas`.
  - Também exclui os arquivos reais de ambiente `deploy/ambientes/*.env` (os `.env.example` continuam incluídos), `**/*.pem` e `**/*.key`.
- **Problema resolvido:** o `Dockerfile` faz `COPY . .`. Sem essas exclusões, a imagem levaria o instalador gerado (cerca de 128 MiB), as ferramentas baixadas, os pacotes de entrega e, principalmente, arquivos de ambiente reais e chaves privadas.
- **Riscos e inconsistências:**
  - `.maestro/`, a pasta dos playbooks do Maestro, que não é rastreada, não está excluída. Num build feito nesta árvore, ela entraria na imagem. Não contém segredos, mas não pertence à aplicação. Sugiro acrescentá-la na fase de validação Docker.
  - Excluir `**/*.pem` também exclui qualquer certificado que a aplicação precise ter na imagem. Hoje nenhum é necessário: o Caddy recebe certificados por volume.

### `Dockerfile`

- **O que mudou:** o `CMD` usa `--origem "${VLADO_ORIGEM:-https://${VLADO_DOMINIO:?…}}"`.
- **Problema resolvido:** na homologação local com portas 8080/8443, a origem pública vista pelo navegador inclui a porta (`https://localhost:8443`). Com `https://${VLADO_DOMINIO}` fixo, a verificação de `Origin` em `interface_pesquisa.py` recusaria as requisições.
- **Riscos e inconsistências:**
  - Em `sh`, a expansão aninhada só exige `VLADO_DOMINIO` quando `VLADO_ORIGEM` está vazia, e isso está correto.
  - `interface_pesquisa.py` exige origem HTTPS no modo piloto, e `VLADO_ORIGEM` passa a ser uma forma de contornar o domínio. Um valor errado só quebra o login, sem abrir acesso.

### `docker-compose.yml`

- **O que mudou:** repassa `VLADO_ORIGEM: ${VLADO_ORIGEM:-}` ao serviço `vlado`.
- **Problema resolvido:** permite definir a origem pelo arquivo de ambiente. Uma string vazia ativa o fallback `:-` do `Dockerfile`.
- **Riscos e inconsistências:** nenhum observado. O Caddy continua usando `VLADO_DOMINIO`.

### `deploy/ambientes/homologacao.env.example`

- **O que mudou:** a instrução de homologação local saiu do cabeçalho e foi para opções comentadas: `localhost`, `Caddyfile.interno`, portas `127.0.0.1:8080` e `127.0.0.1:8443` e `VLADO_ORIGEM=https://localhost:8443`.
- **Problema resolvido:** as portas passam a escutar só em loopback (`"127.0.0.1:8080:80"` é um mapeamento válido no compose), e a origem com porta acompanha a mudança do `Dockerfile`.
- **Riscos e inconsistências:** `VLADO_VERSAO=2.0.0` continua no arquivo (ver versões acima). Não há chave preenchida: as linhas `ANTHROPIC_API_KEY=` e `OPENAI_API_KEY=` continuam vazias e comentadas.

### `docs/GUIA_TECNICO_IMPLANTACAO.md`

- **O que mudou:**
  - O texto de requisitos foi reescrito (servidor Linux com Compose v2, DNS, portas 80/443, 2 vCPU, 4 GB de RAM e 20 GB de disco) e foi recomendado usar `demonstracao` na primeira publicação.
  - Foi incluído `docker compose … config --quiet` para validar a configuração.
  - Todos os comandos `docker compose -p …` passaram a incluir `--env-file deploy/ambientes/<amb>.env`.
  - A homologação local foi atualizada com portas em loopback e `VLADO_ORIGEM`.
  - Foram acrescentados uma lista de conferência antes de distribuir convites e o registro da homologação local de 15/11/2026 sobre a base `9b8f38e`.
- **Problema resolvido:** sem `--env-file`, os comandos `exec`, `ps` e `backup` interpolavam o compose sem o arquivo de ambiente usado no `up`. Sem um `.env` na raiz, eles podiam falhar nas variáveis obrigatórias (`:?`). O guia também passa a documentar o que já foi homologado.
- **Riscos e inconsistências:**
  - O registro de 15/11/2026 é uma afirmação do usuário sobre um teste feito fora desta sessão, não reverificada aqui. A fase de validação Docker deve reproduzir esse teste.
  - O registro diz "base `9b8f38e` com os ajustes de implantação", ou seja, com este diff ainda não commitado. Depois dos commits, convém citar o hash do commit Docker.
  - O comando de semeadura usa `demonstracao.env`, de forma consistente.

## Busca por dados sensíveis no diff

Procurei no diff completo padrões de chave (`sk-…`, `api_key`, `token`, `secret`, `senha`, `password`, `BEGIN …`), caminhos absolutos pessoais (`C:\Users\…`, `/Users/`, nome ou e-mail do usuário), endereços de e-mail, IPs e nomes ligados a casos.

- **Chaves e tokens:** nenhum encontrado. Os únicos literais são a chave fictícia `vlado-build-test-key` e as linhas vazias e comentadas `ANTHROPIC_API_KEY=` e `OPENAI_API_KEY=`.
- **Caminhos pessoais:** nenhum. O único caminho Windows é fictício (`C:\Users\teste\…`). Os IPs são só `127.0.0.1`.
- **Dado de caso real:** um nome de arquivo de teste que parece derivado de documento de caso real (ver `testes/test_extracao_cadastro_pdf.py`), sem conteúdo real. O valor não foi reproduzido aqui.
- **Credenciais em documentação:** não há. O guia continua instruindo a entregar links de ativação por canal seguro.

## Falhas encontradas na verificação

A base é a verificação da tarefa anterior, resumida em `.maestro/playbooks/Initiation/Working/verificacao_pre_commit.md`. Com `.venv/Scripts/python.exe` (Python 3.12.14), fluxo e projeto passaram, e a execução válida da suíte terminou com 415 testes, 405 aprovados, 10 pulados e 0 falhas. Duas execuções anteriores, com o mesmo interpretador, terminaram com um erro intermitente. A investigação encontrou uma única causa, presente em dois pontos dos testes, e nenhuma falha no código de produção. Tudo nesta seção roda com o provedor simulado (`FakeServer`), sem chaves no ambiente e sem chamada à API. Os caminhos `Working/` abaixo são relativos a `.maestro/playbooks/Initiation/`.

### Ambiente: Python do PATH sem dependências (não é falha do código)

O `python` do PATH (Python 3.14 do sistema) roda só 193 testes, com 67 erros de importação, porque faltam `argon2` e outras dependências. Não houve correção: a verificação usa o `.venv` do projeto, que tem o `requirements.txt` instalado. Fica uma observação para a documentação: os comandos de manutenção do `AGENTS.md` usam `python`, e num ambiente novo é preciso ativar o `.venv` antes.

### Falha 1: `test_continuar_documentos.ContinuarDocumentosTest.test_comparacao_ausente_impede_conclusao_e_preserva_publicacoes_parciais` (intermitente)

- **Sintoma:** `FileNotFoundError` ao ler `execucoes/alpha/R002/saidas/codex_execucao.json`, dentro da pasta temporária do teste, em `testes/test_continuar_documentos.py:175`. Aconteceu em 2 de 3 execuções completas (`Working/unittest_venv.log` e `Working/unittest_final.log`). A asserção anterior, `estado == 'incompleto'` (linha 174), passava.
- **Causa:** corrida entre a espera do teste e `Conversas._finish` (`scripts/codex_apuracao.py:903`). `_finish` trabalha o tempo todo sob `self.lock` (um `RLock`), nesta ordem:
  1. grava `meta['estado']` e faz `busy = False`;
  2. calcula `meta['situacao']`;
  3. salva `conversa.json` com `_atomico`, que no Windows repete `os.replace` até 40 vezes, com 25 ms de intervalo, quando recebe `PermissionError` (por exemplo, por causa do antivírus);
  4. registra o evento `estado`;
  5. só então grava `saidas/codex_execucao.json` e o checkpoint.

  O teste esperava o fim com `esperar(lambda: not ctx['busy'])`, ou seja, lia o estado sem a trava. Por isso via `busy == False` no meio de `_finish`, passava pela linha 174 e lia o relatório antes de ele existir. A latência de escrita no Windows amplia essa janela, e é por isso que a falha aparece só às vezes.
- **Não é regressão do diff 2.0.4:** a ordem de `_finish` e o teste vêm do commit de importação `ff816bd`, e o cálculo da situação entrou em `0a0d6ce`, que já está em `main`. Nenhum dos dois aparece no diff. A nova pasta temporária (`preparar_pasta_rodada`) atua só no congelamento, antes da primeira etapa, e a R002 existia: as etapas de busca à síntese gravaram nela. A suspeita da tarefa anterior, de uma ligação com a passagem R001→R002, não se confirmou. A R002 aparece no erro só porque é a rodada criada por esse teste.
- **Reprodução determinística:** `Working/reproduzir_corrida_finish.py` não altera arquivos do projeto. Ele embrulha em memória dois pontos de `_finish` (o cálculo da situação e a gravação do relatório) com um atraso de 0,5 s e roda os testes por nome. Antes da correção, com o atraso, o teste falha sempre com o mesmo `FileNotFoundError` da linha 175 (`Working/corrida_antes_com_atraso.log`). Sem o atraso, passa (`Working/corrida_antes_sem_atraso.log`).
- **Correção (só no teste):** a espera passa a ler o estado por `Conversas.eventos()`, que adquire a mesma trava. Um estado fora de `ACTIVE` (importado de `codex_apuracao`) só fica visível depois que `_finish` terminou e gravou o relatório. É o padrão que `completar` (`testes/agente_fluxo_fixture.py`) e `completar_expansao` já usam, e também o caminho pelo qual a interface acompanha a conversa.

### Falha 2: mesma causa, latente, em `testes/test_retomada_codex.py` (`Base.aguardar_fim`)

- **Sintoma:** `aguardar_fim` esperava `meta['estado']` sem a trava, e `_finish` grava o estado antes da situação e do relatório. Nas três execuções completas observadas não houve falha. Com o atraso injetado, dois testes falham:
  - `SituacoesTest.test_retomar_apos_sem_cota_continua_da_etapa_certa_e_arquiva_o_registro`, na linha 246 (`'em_andamento' != 'sem_cota'`). As linhas 247 e 256 do mesmo teste leem `codex_execucao.json` logo depois da mesma espera.
  - `QuedaEReinicioTest.test_queda_no_meio_da_etapa_retoma_a_mesma_rodada_sem_duplicar`, na linha 92 (situação `em_andamento` em vez de `concluido`).
- **Correção (só no teste):** `aguardar_fim` passa a usar `self.estado(...)`, um helper que a própria classe já tinha e que lê por `eventos()`.

### Esperas conferidas e mantidas

- `test_continuar_documentos.py:115` (`test_mudanca_antes_de_congelar_nao_altera_checkpoint_da_rodada_antiga`): o congelamento falha, e `ctx['run']` continua `None`, porque `perguntar` o zera. Assim `_finish` não grava relatório nem checkpoint. As asserções seguintes (estado, hash do checkpoint da R001 e ausência da R002) não dependem do resto de `_finish`.
- `test_continuar_documentos.py:198` (`test_pendencia_respondida_vincula_ultima_rodada_concluida_a_suporte_novo`): a operação seguinte que depende do fim, `preparar_corpus`, adquire a trava antes de ler.
- `test_extracao_cadastro_pdf.py:135` (teste novo do diff): a espera só distingue entre "turno iniciado" e "falha no congelamento", e o `completar` que vem depois espera por `eventos()`. No caminho de falha, a mensagem do `assert` pode mostrar a situação ainda desatualizada, mas o teste falha do mesmo jeito.
- `test_retomada_codex.py:137`: é seguida de `retomar()`, que adquire a trava.
- Os outros 13 módulos que acionam `Conversas` também passaram pela varredura com o atraso: 136 testes, todos aprovados, 1 pulado (permissões POSIX) (`Working/corrida_varredura_com_atraso.log`). Depois da correção, os dois módulos corrigidos passaram com o atraso: 21 testes, 0 falhas (`Working/corrida_depois_com_atraso.log`).

### Código de produção sem alteração

Os pontos do servidor que dependem do fim da execução (`eventos`, `perguntar`, `retomar`, `cancelar`, `gerenciar`, `preparar_corpus`, `caderno_previa`) adquirem `self.lock` e não enxergam o meio de `_finish`. Mudar a ordem dentro de `_finish` (liberar `busy` por último) alteraria comportamento fora do escopo da falha. Além disso, uma exceção durante a gravação deixaria a conversa presa em `busy`.

Fica uma observação para uma fase futura: `Conversas.listar`, chamada pela operação `codex-listar` (`scripts/interface_pesquisa.py:746`) sem a trava, combina o estado lido de `conversa.json` com `busy` lido sem trava (`scripts/codex_apuracao.py:216`). Na janela de milissegundos entre `busy = False` e o `_save`, a lista pode mostrar "interrompido" por um instante. É só aparência transitória, sem perda de dados. Não foi alterado.

### Verificação depois da correção

| Comando (`.venv`, sem chaves no ambiente) | Resultado |
| --- | --- |
| `scripts/montar_fluxo.py --check` | saída 0, com `OK: fluxo completo e hashes correspondem aos sete modulos.` |
| `scripts/verificar_projeto.py` | saída 0, com `estado: sem_caso_selecionado`, 0 documentos, prompts 1.4.1 e `OK de preparacao` |
| `-m unittest discover -s testes -v` | saída 0. Foram **415 testes: 405 aprovados, 10 pulados, 0 falhas e 0 erros** (1123 s). Os três testes envolvidos na corrida passaram. |

Os 10 pulados são os mesmos da tarefa anterior e dependem de recursos ausentes neste Windows: Tesseract, PyMuPDF e pypdf no OCR (7), links simbólicos (1), permissões POSIX (1) e `VLADO_TESTAR_INICIADOR=1` (1). São pulos, não falhas, e ficam como pendências de ambiente. A lista com os motivos está em `Working/verificacao_pre_commit.md`. Cinco linhas do log têm avisos do pypdf ou do PyMuPDF intercalados antes do `ok`, como na execução anterior. Logs: `Working/fluxo_t5.log`, `Working/projeto_t5.log`, `Working/unittest_t5.log` e `Working/unittest_t5.exit`.

Uma única execução completa limpa não prova a ausência de intermitência. A evidência da correção é a reprodução determinística: o mesmo atraso que derrubava os três testes não os derruba mais.

### Para o commit

As correções são só de teste (`testes/test_continuar_documentos.py` e `testes/test_retomada_codex.py`) e entram no commit `fix:` próprio previsto na tarefa de commits, separado das correções Windows 2.0.4. Sugestão de mensagem: `fix: testes esperam o fim da execução pela trava do gerenciador`. O roteiro de reprodução fica em `.maestro/` e não entra em commit.
