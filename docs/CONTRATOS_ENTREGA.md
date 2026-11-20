# Contratos da entrega para o Intercept

Documento de trabalho da entrega `entrega-intercept`. Define as interfaces entre as frentes (autenticação e dados; Caderno e interface; Android e distribuição) antes da implementação. Quem muda um contrato atualiza este arquivo.

## 0. Propriedade dos arquivos

| Frente | Arquivos que pode alterar |
| --- | --- |
| A — autenticação e dados | `scripts/acesso.py`, `scripts/interface_pesquisa.py`, `scripts/rotas_*.py` (rotas separadas de `interface_pesquisa.py`), `scripts/codex_apuracao.py` (só checagens de dono/caso), `scripts/backup.py`, `interface/entrar.html` (novo), `interface/entrar.js` (novo), `interface/piloto.js`, bloco `#acesso-painel` do `index.html`, `requirements.txt`, `Dockerfile`, testes `testes/test_acesso*.py`, `testes/test_contas*.py`, `testes/test_autorizacao*.py`, `testes/test_backup.py` |
| B — Caderno | `interface/editor_notas.js`, `interface/apuracao.js`, `interface/caderno.css` (novo), seção `#area-apuracao` e diálogo `#apuracao-adicionar-dialogo` do `index.html`, testes `testes/*caderno*`, `testes/*editor*`, `testes/*checkbox*`, `testes/*rascunho*` |
| C — Mesa em tela estreita | `interface/style.css`, `interface/index.html` (fora dos blocos de A e B), `interface/app.js`, `interface/desktop.js`, `interface/experiencia.js`, `interface/codex.js`, `interface/leitura.js`, `interface/revisao.js`, `interface/gerenciar.js`, `interface/manifest.webmanifest` e ícones (novos), testes `testes/*mobile*`, `testes/qa_visual*` |
| D — Android | `android/` (novo), `docs/ANDROID.md` (novo) |
| Sessão principal | ambientes (`deploy/`, `docker-compose*.yml`, `.env.example`), integração, docs de entrega, empacotamento |

`interface/i18n_en.js` é compartilhado: cada frente acrescenta suas chaves com Edit num bloco comentado próprio (`// Frente A`, `// Frente B`, `// Frente C`), sem reescrever o arquivo.

Ninguém faz commit, stash, reset ou troca de branch. A sessão principal integra e commita.

## 1. Ambientes

`VLADO_AMBIENTE` ∈ `homologacao` | `editorial` | `demonstracao` (padrão `homologacao` no modo hospedado; o modo local continua sem ambiente).

- Cada ambiente é um projeto Compose próprio (`-p vlado-<ambiente>`), com volumes, `.env`, domínio e contas próprios. Nunca compartilham volume.
- `GET /api/sessao` devolve `ambiente`; a interface mostra uma faixa fixa em `homologacao` ("Homologação — dados sintéticos") e em `demonstracao` ("Demonstração — dados sintéticos"). No `editorial` não há faixa.
- O APK da sala aponta só para a origem do ambiente `demonstracao`; o da redação, só para a do `editorial`.

## 2. Contas, sessões e permissões (frente A)

### Armazenamento

`acesso/acesso.json` (ou `VLADO_ACESSO`), `versao: 2`, gravação atômica com trava (como hoje):

```json
{"versao": 2,
 "contas": {"<id>": {"nome": "...", "login": "ana.silva", "papel": "admin|convidado",
   "casos": ["caso_a"], "cota_diaria": 20, "ativa": true,
   "senha_hash": "$argon2id$...|null", "senha_definida_em": "...|null",
   "ativacao": {"token_sha256": "...", "expira_em": "...", "motivo": "criacao|recuperacao"},
   "criada_em": "...", "criada_por": "<id>|cli", "migrada_de_convite": true}},
 "sessoes": {"<sha256(sid)>": {"conta": "<id>", "csrf": "...", "criada_em": "...", "expira_em": "...",
   "ultimo_uso": "...", "cliente": "web|android"}},
 "tentativas": {"<login>": {"falhas": 0, "bloqueado_ate": null}},
 "uso": {"<id>": {"AAAA-MM-DD": 3}},
 "eventos": [{"em": "...", "tipo": "conta_criada|senha_definida|login_falhou|login_bloqueado|conta_desativada|conta_reativada|acesso_alterado|recuperacao_emitida|sessao_encerrada", "conta": "<id>", "por": "<id>|cli"}]}
```

- Hash de senha: `argon2-cffi` (`PasswordHasher` com parâmetros padrão; `check_needs_rehash` no login). Senha mínima de 12 caracteres, máxima de 256.
- Login: `[a-z0-9][a-z0-9._-]{2,63}`, único, comparado em minúsculas.
- Migração v1→v2 automática na primeira leitura: cada convite vira conta com **o mesmo id** (preserva `conta_id` gravado em notas, revisões e conversas como `dono`), `login` derivado do nome e desduplicado, `senha_hash: null`, `ativa: not revogado`; convites expirados viram contas ativas sem senha (entram depois de recuperação). Sessões v1 são descartadas (todos entram de novo). Cópia do arquivo v1 em `acesso/acesso.v1.json` antes de regravar.
- Eventos nunca contêm senha, token, link ou hash; no máximo 1000 eventos (descarta os mais antigos).

### Ativação e recuperação

- Só a administração cria contas (CLI ou Mesa). Criar devolve **uma vez** o link `ORIGEM/ativar/<token>` (token `secrets.token_urlsafe(32)`, guardado só como SHA-256), válido 72 h (configurável 1–168 h), de uso único.
- `/ativar/<token>` mostra o formulário de definir senha (login exibido, não editável). `POST /api/ativar {token, senha}` define a senha, apaga `ativacao`, registra evento e **não** abre sessão automaticamente: leva a `/entrar`.
- Recuperação (`contas-recuperar`): encerra todas as sessões da conta, zera `senha_hash` e emite novo link de ativação (motivo `recuperacao`).
- O CLI imprime o link só no stdout do terminal do administrador (`--saida ARQUIVO` grava com permissão 0600 em vez de imprimir). Links e senhas nunca vão para logs, eventos, capturas ou artefatos.

### Sessão

- `POST /api/entrar {login, senha, cliente?}` — exige `Origin` igual à origem pública e JSON; sem CSRF (ainda não há sessão). Sucesso: `Set-Cookie: vlado_sessao=<sid>; HttpOnly; Secure; SameSite=Strict; Path=/` (sem Max-Age; a validade real é do servidor) e corpo `{"conta": {...pública}, "csrf": "..."}`.
- Falha: resposta única `401 {"codigo": "credenciais", "erro": "Login ou senha incorretos."}` para login inexistente, senha errada, conta sem senha ou desativada (sem revelar qual). 5 falhas seguidas no mesmo login bloqueiam 15 min (`429 {"codigo": "bloqueado"}`); limite adicional de 20 tentativas por minuto por IP (o IP do proxy só é usado com `VLADO_CONFIAR_PROXY=1`, lendo o último salto de `X-Forwarded-For`). A verificação de hash roda mesmo para login inexistente (tempo aproximadamente constante).
- Validade: 12 h absolutas e 2 h de inatividade (`ultimo_uso` atualizado no máximo a cada 60 s). Expirada → 401 `sem_sessao`.
- `GET /api/sessao` → `200 {"conta": {"id","nome","login","papel","casos"}, "csrf", "ambiente", "expira_em"}` ou `401`.
- `POST /api/sessao-sair` encerra a sessão e apaga o cookie.
- Toda requisição autenticada relê a conta: conta desativada, caso retirado ou sessão revogada valem **na requisição seguinte**.
- Página `/` sem sessão → `303 Location: /entrar`. `/entrar` e `/ativar/<token>` servem a página estática `entrar.html` + `entrar.js`, sem dados de caso.
- POST autenticado continua exigindo `Origin` + `X-Session-Token` (CSRF) + JSON, como hoje.
- `GET /saude` continua público e sem dados.

### Papéis

| Operação | admin | convidado |
| --- | --- | --- |
| Contas (`contas-listar`, `contas-criar`, `contas-atualizar`, `contas-desativar`, `contas-reativar`, `contas-recuperar`) | sim | não |
| Cadastro, inventário, preparar PDFs, gerenciar, lixeira, IA/provedor, achados, revisão humana, diligências, Caderno (ler e escrever), exportações, `original`, `buscar`, `ler` | sim | não |
| `codex-status`, `codex-listar`, `codex-perguntar`, `codex-eventos`, `codex-cancelar`, `codex-retomar`, `codex-original`, `sessao-sair`, `GET /api/catalogo` (filtrado), `GET /api/sessao` | sim | só nos casos liberados **e** nas conversas cujo `dono` é a própria conta; a liberação do caso é conferida em cada chamada (inclusive eventos, original e cancelar) |

- Convidado não escreve no Caderno e não recebe exportações. Cota diária por conta (como hoje).
- O último administrador ativo não pode ser desativado nem rebaixado.
- Recusa: `403 {"estado": "proibido", "codigo": "proibido"}`; sessão ausente: `401 {"estado": "sem_sessao"}`.
- A autoria (`conta_id`, `nome`) continua vindo só da sessão.

### Modo local

O modo local (127.0.0.1, operador único, sem login) permanece como está para uso no próprio computador. `GET /api/sessao` no modo local responde 200 com `conta.id: null`, `papel: "admin"`, `modo: "local"` e `ambiente: null`.

### Como ficou implementado (frente A; ajustes ao texto acima)

- Recusa por papel: `403 {"estado": "proibido", "codigo": ...}` mantém códigos específicos já traduzidos pela interface (`operacao_proibida`, `caso_nao_liberado`, `campos_nao_permitidos`, `servico_nao_encerravel`) em vez de um único `proibido`.
- Convidado chamando `codex-eventos|cancelar|original|retomar` em conversa alheia **ou** de caso retirado recebe `400 {"codigo": "conversa_indisponivel"}` (não revela se a conversa existe). A checagem fica em `Conversas._conferir_dono(id, dono, casos)`.
- Endpoint extra sem sessão: `POST /api/ativacao-consultar {token}` → `{login, nome}` (o formulário mostra o login). Erros de ativação: `400 ativacao_invalida` (link inválido, usado, vencido ou conta desativada) e `400 senha_invalida`.
- `POST /api/entrar` devolve também `destino` (`/` para admin; `/?area=codex[&caso=X]` para convidado). O limite por IP responde `429 {"codigo": "bloqueado"}` (mesma resposta do bloqueio por login). Corpo máximo 4 KB.
- `/convite/*` responde `410` com página bilíngue explicando que o acesso agora é por conta (sem cookie).
- `/api/integracao` passa a exigir sessão no modo hospedado.
- `contas-listar` → `{contas, eventos}` (últimos 50 eventos, sem segredos). `contas-criar {nome, login, papel, casos?, cota_diaria?, horas?}` e `contas-recuperar {id, horas?}` → `{conta, link}`; `contas-atualizar {id, nome?, papel?, casos?, cota_diaria?}`; `contas-desativar|reativar {id}` → `{conta}`. Casos precisam existir no catálogo.
- Situação pública da conta: `ativa | desativada | aguardando_senha` (+ `ativacao_vencida`).
- Bloqueio (revisão de segurança): as 5 falhas contam por **login + IP** (chave `login|ip` em `tentativas`), para que quem conhece um login não tranque o dono de fora a partir de outro endereço; o limite de 20/min por IP continua e também vale para `ativar`/`ativacao-consultar`. Contadores velhos (>15 min) são podados e bloqueios vigentes nunca são descartados; no máximo 2000 entradas.
- Eventos: `login_falhou` **não** é gravado (falhas em massa empurrariam a auditoria para fora do limite de 1000); só `login_bloqueado`. Evento extra `migracao_v1`.
- Só um arquivo com `versao` ausente/1 e `convites` é migrado; outra versão é tratada como ilegível (503), nunca sobrescrita.
- Sessão: o cookie aceito tem exatamente 43 caracteres `[A-Za-z0-9_-]` (antes de qualquer trava); argon2 roda com no máximo 4 hashes simultâneos.
- A restauração de backup apaga as sessões gravadas no arquivo de contas e grava `acesso/*` e `segredos/*` com permissão 0600.
- Login migrado de nome sem letras suficientes vira `conta.<nome>`; duplicados ganham `-2`, `-3`. Se `acesso.v1.json` já existir, a cópia vai para `acesso.v1.<carimbo>.json`.
- Página de entrar usa `interface/entrar.css` (novo; o CSP bloqueia estilo inline) além de `/style.css`.
- Backup: a restauração troca o **conteúdo** de cada pasta de dados (preparo e cópia anterior ficam dentro da própria pasta), sem renomear a pasta — funciona com volumes Docker montados e com a raiz `/app` somente leitura. `VLADO_ACESSO` apontando para fora de `acesso/` não entra no backup.

## 3. Editor e salvamento do Caderno (frente B)

- Persistência: só `apuracao-nota-salvar` com `revisao_nota` (já existe). Não criar outro mecanismo de gravação.
- Estados visíveis (`#apuracao-salvamento`): `pendente` "Alterações não salvas" → `salvando` "Salvando…" → `salvo` "Nota salva às HH:MM" (só depois do 200 do servidor com a revisão nova) | `rede` "Sem conexão. Rascunho guardado nesta aba; tentando de novo…" | reconexão volta a `salvando` | `conflito` (para o salvamento automático e oferece copiar/recarregar) | `sessao` "Sessão expirada. Entre de novo; o rascunho continua nesta aba."
- Qualquer mudança no conteúdo (digitação, colagem, troca de estilo, marcar/desmarcar tarefa, inserir referência) passa pelo mesmo `onInput` do `EditorNotas`.
- Rascunho local: `sessionStorage` (aba atual; some ao fechar a aba ou o app), chave `vlado:rascunho:<conta>:<caso>:<nota>`, guardado a cada mudança ainda não confirmada, com `revisao_nota` de base e hora. Apagado após salvamento confirmado e no logout. Ao reabrir a nota com rascunho mais novo que a base, oferece restaurar ou descartar; se a base mudou no servidor, trata como conflito. Nunca em `localStorage`, IndexedDB ou cookie.
- Rascunhos das outras telas (pergunta em preparo e formulários dos quadros de revisão, caderno de seleção, diligências e resposta): `window.Rascunhos` em `interface/continuidade.js`. Cópia imediata em `localStorage` (chave `vlado:rascunho-tela:<conta>:<caso>:<tela>`, a cada mudança; nos modos com contas `<conta>` vem de `/api/sessao` e, enquanto ela não é conhecida, nada é lido nem gravado no navegador; convidados têm no máximo 10 rascunhos abertos por apuração) e cópia durável no servidor (`rascunhos-salvar` com a versão conhecida, 1,2 s depois da última mudança, e na hora em `visibilitychange→hidden` e `pagehide`, com `keepalive` até 60 KB). Estado discreto: "Salvando…" → "Salvo às HH:MM" | "Sem conexão — salvo neste navegador" (reenvia no evento `online`). Ao abrir a tela com rascunho mais novo que o conteúdo, oferece restaurar ou descartar; conflito com outra aba (409 `rascunho_conflito`) oferece "Manter o desta aba" ou "Usar o da outra aba", e nada é gravado enquanto a escolha está aberta. Cada item de um quadro tem o próprio rascunho (`quadro-<nome>/<id>`, com o id calculado do achado, escopo ou origem na tela), e fechar um item não apaga o rascunho de outro. Envio da pergunta ou fechamento do quadro descarta o rascunho; o Sair apaga as cópias deste navegador. Campos de senha/arquivo, nomes com cara de chave e valores com forma de chave de API não são guardados em lugar nenhum. **O texto das notas do Caderno não usa esse mecanismo**: continua só em `sessionStorage` + `apuracao-nota-salvar`, como acima.
- Estilos: seletor com Texto normal (`p`), Título da seção (`h2`), Subtítulo (`h3`); níveis legados (`h1`, `h4`–`h6`) aparecem com o nome real ("Cabeçalho 1 (legado)") e são preservados até o usuário trocar.
- Tarefas: `- [ ] ` / `- [x] ` em Markdown; contagem "n de m tarefas concluídas" na barra da nota.

## 4. Interface em tela estreita (frente C)

- Larguras de referência: 320, 360, 390, 768, 1024, 1365 px; sem rolagem horizontal em nenhuma.
- O botão voltar do Android/navegador volta à área anterior (`history.pushState` por área e por nota/fonte aberta).
- Operação em andamento × retomável: a interface diferencia "Em andamento" de "Conexão perdida — a execução continua no servidor; reconectando" e de "Interrompida — retomar". Base: `situacao`/`retomavel` de `codex-eventos` e falhas de rede.
- Login, ativação e saída funcionam em 320 px com teclado virtual (`autocomplete="username"`/`current-password`/`new-password`).

## 5. Android (frente D)

- WebView em Kotlin, `minSdk 26`, `targetSdk 35`. Variantes `sala` e `redacao`; a origem HTTPS de cada variante vem de propriedade de build (`-PvladoOrigemSala=`, `-PvladoOrigemRedacao=`), nunca de segredo embutido.
- Navegação permitida só na origem configurada; outros links abrem no navegador do sistema. Sem `addJavascriptInterface`, sem acesso a arquivos, sem conteúdo misto; `network_security_config` sem tráfego em texto claro (exceto variante de depuração para homologação local, documentada).
- Downloads (originais, exportações): os POST de download viram `blob:` no JS; o app intercepta e grava via `MediaStore`/SAF; PDF abre com o visualizador do sistema (a página citada é informada na tela; `#page=N` não vale fora do navegador: documentar).
- Voltar: histórico da WebView; na raiz, sai do app.
- Chave de assinatura fora do repositório e do pacote; `keystore.properties` lido de caminho externo.
