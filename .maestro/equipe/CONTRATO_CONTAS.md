---
type: reference
title: Contrato de contas
created: 2026-11-22
tags: [contrato, contas, autorizacao, equipe]
related: ['[[PLANO_LANCAMENTO]]', '[[DIAGNOSTICO_LANCAMENTO]]', '[[CONTRATO_EVIDENCIA]]']
---

# Contrato de contas

Este é o contrato do sistema de contas da Onda 2 (branch `lancamento/contas-o2`, criada de `cb9afa8`). Ele define redações, papéis, posse de apuração, a matriz operação × papel, o isolamento entre redações, a migração das contas atuais e o armazenamento, e desenha e-mail, segundo fator, sessões e ciclo de vida. Fecha CON-01 a CON-07, PROD-04 e SEG-07 e liga a cota de CUS-01 às contas.

**O contrato foi aprovado pelo dono do projeto em 22/11/2026 (P28), com duas ressalvas para o código, registradas na seção 11.** O código entra por entregas, e a seção 12 diz o que já existe. Onde o texto diz "hoje", descreve o código em `cb9afa8`. Onde diz "passa a", descreve o que a Onda 2 entrega. Nomes de módulos, operações e campos novos são propostas que este contrato fixa quando for aprovado. As 16 perguntas que a primeira versão levou ao dono do projeto foram respondidas em 22/11/2026 (P27), todas pela recomendação; a seção 11 as registra como decisões, e o texto cita cada uma como "decisão N".

Dois usos da palavra "dono" aparecem aqui. **Dono**, sem complemento, é o papel dentro de uma redação. **Dono do projeto** é quem decide sobre o Vlado.

## 1. Princípios

1. **Negar por padrão.** Operação sem linha na matriz não existe. Apuração sem posse registrada não é alcançada por ninguém. Conta sem participação numa apuração não a vê.
2. **A redação faz parte de toda autorização.** Nos modos com contas, nenhuma sessão tem "todas as apurações": o conjunto ao alcance é sempre uma lista explícita, calculada a partir da redação da conta.
3. **Um ponto só.** Papel, redação e participação são conferidos num único módulo, o portão (seção 4). Os módulos de rota não leem o papel.
4. **O servidor decide.** A interface esconde o que a pessoa não pode fazer, mas nunca é a barreira.
5. **"Não existe" e "não é seu" têm a mesma resposta.** Nenhuma recusa confirma que uma apuração, conversa, pessoa ou redação existe fora do alcance de quem pergunta.
6. **Tudo é relido a cada requisição.** Papel, participação, situação da conta e da redação valem na requisição seguinte à mudança, como hoje.
7. **O identificador da conta nunca muda nem é reaproveitado.** É ele que liga notas, revisões e conversas ao autor.
8. **Segredos não ficam legíveis.** De tokens, sessões e códigos de reserva só se guarda o SHA-256. A semente do segundo fator fica cifrada. Eventos e e-mails não levam senha, token nem hash.
9. **A migração nunca amplia acesso.** Nenhuma conta sai da migração alcançando algo que não alcançava antes.
10. **Sem modelo e sem rede.** O sistema de contas não chama modelo. A única saída de rede é o envio de e-mail, quando houver provedor configurado.

## 2. Modelo

### 2.1 Vocabulário

| Termo | Significado |
|---|---|
| Instalação | Um servidor do Vlado com sua pasta de dados. |
| Operador do Vlado | Quem administra a instalação pelo terminal do servidor. Não tem conta na Mesa (seção 5.16). |
| Redação | A organização. Cada redação convidada é uma (D1). Tudo o que é de uma redação é invisível às outras. |
| Conta | Uma pessoa. Pertence a exatamente uma redação e tem um papel nela. |
| Papel | `dono`, `editor`, `reporter` ou `leitor`. Existe ainda o perfil legado `convidado` (seção 2.4). |
| Apuração | O caso (`casos/<id>`). Pertence a uma redação. |
| Responsável | A conta que responde pela apuração: quem a criou, até o dono transferir. |
| Participação | Ligação entre uma conta e uma apuração da mesma redação. |
| Convite | Pedido de entrada numa redação, enviado por e-mail, com prazo. |
| Autor restrito | Campo `dono` de `conversa.json`. O nome é antigo e não tem relação com o papel dono: marca a conversa aberta por um leitor ou por um convidado. Só o autor acrescenta pergunta a ela e a retoma; o dono e o responsável pela apuração podem cancelar uma execução em curso. As outras são conversas da equipe, que dono, editor e repórter continuam. A regra completa está na seção 5.8. |

Uma conta pertence a uma redação só. Quem trabalha para duas redações convidadas usa dois e-mails (decisão 2).

### 2.2 Redação

| Campo | Forma | Significado |
|---|---|---|
| `id` | `org` + 16 hex | Gerado pelo servidor, nunca escolhido. |
| `nome` | até 120 caracteres, sem caracteres de controle | Mostrado a membros e nos e-mails de convite. |
| `situacao` | `ativa`, `suspensa`, `encerrada` | Suspensa: ninguém da redação opera, mas nada é apagado. |
| `cota_mensal_brl` | decimal ou nulo | Teto mensal de IA pago pelo serviço. Nulo usa o padrão da instalação. Só o operador muda. |
| `teto_por_pessoa_brl` | decimal ou nulo | Teto mensal padrão de cada pessoa. O dono muda, até o teto da redação. |
| `criada_em`, `criada_por` | data UTC, `operador` ou `migracao` | Procedência. |

Só o operador cria, suspende e encerra redações (D3). Nenhuma rota HTTP cria redação, exceto o formulário do primeiro administrador do modo `local-contas`, que cria a redação única daquela instalação.

### 2.3 Conta

| Campo | Forma | Significado |
|---|---|---|
| `id` | 16 hex | `secrets.token_hex(8)`, como hoje. Contas migradas mantêm o mesmo valor. |
| `organizacao` | id de redação | Fixa. Mudar de redação é sair de uma e ser convidado para outra, com conta nova. |
| `papel` | `dono`, `editor`, `reporter`, `leitor`, `convidado` | `convidado` só existe em conta migrada. |
| `email` | endereço em minúsculas, único na instalação | Identifica a pessoa na entrada. Vem do convite. Nulo só em conta migrada que ainda não o informou. |
| `login` | forma atual (`acesso.LOGIN`) | Só em conta migrada. Continua aceito na entrada. |
| `nome` | até 120 caracteres | Informado pela pessoa ao aceitar o convite. |
| `situacao` | `aguardando_senha`, `ativa`, `desativada`, `excluida` | `excluida` é definitiva e guarda só o id (seção 8.4). |
| `teto_mensal_brl` | decimal ou nulo | Teto próprio, definido pelo dono. Nulo usa o da redação. |
| `cota_diaria` | 1 a 500 ou nulo | Só para `convidado`, como hoje. |
| `idioma` | `pt`, `en` | Idioma dos e-mails. O tema continua no navegador. |
| `termos` | `{versao, aceito_em}` | Último aceite (seção 8.4). |

### 2.4 Papéis

| | Dono | Editor | Repórter | Leitor |
|---|---|---|---|---|
| Vê | todas as apurações da redação | as em que foi incluído | as que criou e as em que foi incluído | as em que foi incluído |
| Lê documentos, respostas, achados, quadros, caderno e texto | sim | sim | sim | sim |
| Pergunta à IA | sim | sim | sim | sim, em conversas próprias |
| Cria apuração e envia documentos | sim | não | sim | não |
| Escreve no caderno, em diligências, quadros, tabelas e entrevistas | sim | sim | sim | não |
| Confere achado | sim | sim | sim | não |
| Escreve o texto da matéria e vincula evidências | sim | sim | sim | não |
| Marca afirmação do texto como revisada | sim | sim | **não** | não |
| Inclui pessoas numa apuração | sim | não | só nas que é responsável | não |
| Manda apuração, conversa ou rodada para a lixeira e restaura | sim | não | só nas que é responsável | não |
| Apaga de vez | sim | não | não | não |
| Captura página da web | sim | não | não | não |
| Convida, muda papéis, define tetos, troca a chave de IA, vê a atividade | sim | não | não | não |

**O que o editor faz que o repórter não faz (PROD-04).** O editor marca afirmações do texto como revisadas (`redacao-revisar`): a revisão humana da matéria é dele e do dono, não de quem apurou (decisão 7). Fora isso, o editor faz o trabalho de mesa que hoje exige ser administrador: confere achados, escreve no caderno, abre e responde diligências, edita quadros. O que o editor não faz é o que cria ou destrói: não abre apuração, não envia documentos, não inclui pessoas, não manda nada para a lixeira e não administra a redação.

**O leitor** lê tudo da apuração em que foi incluído (decisão 8) e faz perguntas. As conversas dele são dele: não acrescenta pergunta à conversa de outra pessoa, ninguém acrescenta pergunta à dele (seção 5.8), e ele envia só `caso`, `pergunta` e `conversa`, como o convidado de hoje.

**Captura web** fica com o dono no lançamento. O plano já põe "captura web para quem não é administrador" fora do lançamento.

**Perfil legado `convidado`.** É o convidado de hoje, sem mudança: pergunta nas apurações liberadas, vê só as próprias conversas e guarda só o rascunho da pergunta. Não pode ser atribuído a ninguém depois da migração. O dono converte cada convidado em leitor ou em outro papel pela tela Equipe, ou o remove. Ele existe porque transformar convidado em leitor daria às contas atuais a leitura do caderno, dos achados e do texto das apurações liberadas, o que o princípio 9 proíbe sem decisão humana (decisão 1).

### 2.5 Posse e participação

- **A posse é da redação.** Cada apuração tem um registro `{caso, organizacao, responsavel, criado_por, criado_em, origem}`. A redação de uma apuração nunca muda.
- **Quem cria:** dono e repórter. Quem cria vira responsável e participante.
- **Quem vê:** os participantes. O dono vê todas as apurações da própria redação e nenhuma de outra (W09, regra 2).
- **Quem escreve:** o participante cujo papel escreve (tabela acima).
- **Quem inclui e retira pessoas:** o dono e o responsável. Só entram contas da mesma redação; o armazenamento recusa participação entre redações diferentes.
- **Quem manda para a lixeira e restaura:** o dono e o responsável.
- **Quem apaga de vez:** só o dono, com o nome do item digitado e a senha.
- **A lixeira não muda posse nem alcance.** Uma apuração na lixeira continua da mesma redação, com o mesmo responsável e os mesmos participantes, até ser restaurada ou apagada de vez. O que cada pedido recebe nesse intervalo está na seção 4.6.
- **Responsável exige papel dono ou repórter.** Se o responsável é rebaixado, desativado ou excluído, a apuração fica sem responsável e o dono atribui outro. Uma apuração sem responsável continua visível aos participantes e ao dono.
- **Mudança de papel não mexe nas participações.** A conta continua nas mesmas apurações, com o que o papel novo permite.
- **Conta desativada** mantém as participações (reativar devolve o acesso). **Conta excluída** as perde.

### 2.6 As quatro situações de uma conta diante de uma apuração

| Sigla | Situação | Quando |
|---|---|---|
| P | própria | A conta é a responsável. |
| I | de colega, com inclusão | Mesma redação; a conta participa sem ser responsável. |
| N | de colega, sem inclusão | Mesma redação; a conta não participa. |
| X | de outra redação | A apuração pertence a outra redação. |

O pedido do plano fala em três situações (própria, de colega, de outra redação). "De colega" se divide em I e N porque a regra 2 do W09 separa as duas. Para o dono, P, I e N são iguais: ele alcança todas. Editor, leitor e convidado nunca estão em P, porque não podem ser responsáveis.

## 3. Quem chama: sessão e principal

Hoje `rotas_contas._principal()` relê a conta a cada requisição e entrega `{conta, nome, login, papel, casos, cota_diaria, csrf, expira_em, cliente}`, com `casos: None` para o administrador. Passa a entregar:

```json
{"conta": "9f2c41d07a3be850", "nome": "Ana Lima", "email": "ana@redacaoserena.org", "login": null,
 "papel": "reporter", "organizacao": {"id": "org4b1d9c2e7f3a6051", "nome": "Redação Serena"},
 "casos": ["apuracao_3f…", "apuracao_81…"], "responsavel_de": ["apuracao_3f…"],
 "pendencias": [], "csrf": "…", "sessao": "5d0c7e19a2b4f638", "expira_em": "…", "cliente": "web"}
```

- `casos` é o conjunto ao alcance, sempre explícito. Para o dono, são todas as apurações da redação. **`None` só existe no modo `local`**, sem contas, em que o operador único da máquina alcança tudo.
- `responsavel_de` é o subconjunto em que a conta é responsável.
- `sessao` é um identificador público da sessão, para a lista do W08. Não é o cookie nem o hash dele.
- `pendencias` lista o que a conta deve resolver antes de operar: `segundo_fator` (obrigatório e ainda não cadastrado) e `termos` (versão nova sem aceite). Com pendência, a sessão só alcança `GET /api/sessao`, `sessao-sair` e as operações `conta-*` que resolvem a pendência.

`GET /api/sessao` devolve `conta` (`id`, `nome`, `email`, `login`, `papel`, `casos`), `organizacao`, `pendencias`, `capacidades`, `csrf`, `ambiente`, `modo` e `expira_em`. `capacidades` é a lista das operações que o papel alcança em alguma situação, derivada da matriz, para a interface esconder botões sem repetir a tabela. `index.html` continua recebendo o papel em `data-papel`, agora com os valores novos.

O cookie continua `vlado_sessao`, `HttpOnly; Secure; SameSite=Strict`, com 12 horas de teto e 2 de inatividade. A entrada com segundo fator usa antes um cookie de curta duração, que só serve para enviar o código (seção 8.2).

## 4. O portão: onde a redação é conferida

### 4.1 Ponto único

Hoje a autorização está em três lugares: `rotas_contas._negado` (papel), o parâmetro `casos` que desce até `rotas_evidencia._caso`, e `Conversas._conferir_dono`. O administrador passa por nenhum dos três. Passa a existir um módulo, `scripts/autorizacao.py`, com a matriz como tabela de dados e três funções:

| Função | Devolve |
|---|---|
| `alcance(root, conta)` | O conjunto de apurações ao alcance da conta e o subconjunto em que é responsável, lido do registro de posse. É a única função que calcula alcance. |
| `conferir(principal, operacao, dados)` | O acesso concedido (apuração resolvida, vínculo, se é autor restrito) ou uma recusa da tabela 4.3. |
| `filtrar(principal, operacao, resposta)` | A resposta de uma listagem sem os itens fora do alcance. |

`interface_pesquisa._atender_post` chama `conferir` uma vez, depois de sessão, origem e CSRF e antes de qualquer módulo de rota. As rotas de leitura por `GET` (`/api/catalogo`, `/api/fila`, `/api/cota`) e os downloads passam pelo mesmo `conferir`. As três listagens que juntam itens de várias apurações (`GET /api/catalogo`, `GET /api/fila` e `gerenciar-listar`) passam por `filtrar`, que usa o mesmo `alcance`.

**Como o portão acha a apuração de um pedido.** Cada linha da matriz declara um resolvedor. Operação sem resolvedor declarado não sobe.

| Resolvedor | De onde vem a apuração |
|---|---|
| `caso` | Campo `caso` do corpo. |
| `conversa` | Campo `conversa`: o portão lê o `caso` de `conversa.json`. Se o corpo também traz `caso`, os dois precisam coincidir. |
| `item` | Campo `item`: o portão lê o `caso` do item da lixeira. |
| `lote` | Parâmetro `lote` de `GET /api/fila`: o portão lê o `caso` do lote. |
| `novo` | Não há apuração ainda. O servidor gera o id e registra a posse. |
| `nenhum` | A operação não toca apuração: vale para a própria conta ou para a própria redação. |

Depois de resolvida, a apuração precisa estar em `principal['casos']`. Os identificadores de dentro da apuração (rodada, documento, registro, nota, quadro) já são resolvidos pelos módulos dentro de `casos/<caso>` e `execucoes/<caso>`, como manda o contrato de evidência: um id que só existe em outra apuração sai como inexistente.

**Defesa em profundidade.** O parâmetro `casos` continua descendo até `rotas_evidencia._caso` e `Conversas._conferir_dono`, agora nunca `None` nos modos com contas. Se o portão falhar, a segunda conferência ainda recusa.

### 4.2 Ordem das conferências

1. Host permitido.
2. Sessão válida, conta ativa, redação ativa.
3. Teto do corpo, por papel e operação: quem não alcança a operação nunca tem um corpo grande lido.
4. Origem, token CSRF e tipo do conteúdo.
5. A operação existe.
6. Pendências da conta.
7. O papel alcança a operação e os campos enviados.
8. A apuração do pedido está ao alcance. Se ela está na lixeira, só passam as operações de lixeira (seção 4.6).
9. Regra do objeto: responsável, ou autor da conversa.
10. O módulo da rota valida o resto.

O papel vem antes da apuração. Assim, a recusa por papel depende só de quem pergunta e nunca diz nada sobre a apuração.

**Envio em fluxo.** Nas operações que recebem arquivos em fluxo (`cadastrar` e `codex-documentos-cadastrar`, tipo `application/vnd.vlado.lote`), o corpo lido no passo 3 é só a primeira linha, o manifesto em JSON, de até 64 KB. Os passos 4 a 9 são decididos com o manifesto, que traz `caso`, `conversa` e `novo`. Os bytes dos arquivos só começam a ser lidos pela rota depois do passo 9. Uma recusa em qualquer passo anterior responde sem ler nem gravar nenhum byte de arquivo, e o resto do corpo é descartado como hoje.

### 4.3 Respostas de recusa

| Quando | HTTP | Corpo |
|---|---|---|
| Sem sessão, sessão vencida, conta desativada ou excluída | 401 | `{estado: "sem_sessao", codigo: "sessao_expirada"}`, como hoje |
| Armazenamento de contas ilegível | 503 | `{estado: "indisponivel"}`, como hoje |
| Origem, CSRF ou tipo de conteúdo errados | 403 | Como hoje |
| Operação inexistente ou retirada | 404 | `{erro: "Operação não encontrada."}`, como hoje |
| Redação suspensa | 403 | `{estado: "proibido", codigo: "redacao_suspensa"}` |
| Conta com pendência | 403 | `{estado: "proibido", codigo: "pendencia_de_conta", pendencias: […]}` |
| O papel não alcança a operação, ou alcança só como responsável e a conta participa sem ser | 403 | `{estado: "proibido", codigo: "operacao_proibida"}`, como hoje |
| Campos que o papel não envia | 403 | `codigo: "campos_nao_permitidos"`, como hoje |
| Apuração inexistente, de outra redação, sem participação, sem posse registrada ou com id malformado | 404 | `{estado: "indisponivel", codigo: "caso_indisponivel", erro: "Apuração indisponível para esta conta."}` |
| Conversa inexistente, de outro autor restrito ou de apuração fora do alcance | 400 | `codigo: "conversa_indisponivel"`, como hoje |
| Item da lixeira ou lote fora do alcance | 400 | A mesma resposta do item ou lote inexistente, como hoje |
| Senha de confirmação errada numa operação sensível | 403 | `codigo: "senha_atual_incorreta"`; conta para o teto de tentativas |

As cinco causas de `caso_indisponivel` têm o mesmo corpo, byte a byte, e a mesma sequência de leituras no servidor. A causa verdadeira vai só para o registro de auditoria, no evento `acesso_negado` com `motivo` (`papel`, `sem_participacao`, `outra_redacao`, `inexistente`), para o operador enxergar tentativas de travessia. Esse evento não aparece em `equipe-atividade` nem em nenhuma resposta da Mesa: o motivo distingue "não existe" de "é de outra redação", e mostrá-lo ao dono de uma redação seria o mesmo vazamento por outro caminho. Só o operador o lê, no registro de auditoria. `caso_indisponivel` substitui `caso_nao_liberado`.

### 4.4 Ids de apuração iguais em redações diferentes

Não existem. O espaço de ids é um só por instalação, e o disco continua `casos/<id>` e `execucoes/<id>/<rodada>`, sem pasta por redação: os módulos da Plataforma e do Core não mudam.

- Nos modos com contas, o id de uma apuração nova é sempre gerado pelo servidor (`apuracao_` + 32 hex). O cliente não escolhe mais o id: `novo: true` com `caso` no corpo é recusado. Sem isso, tentar criar um id serviria para descobrir se ele existe em outra redação.
- A posse tem o id da apuração como chave única. Duas redações não conseguem registrar o mesmo id.
- Uma apuração criada pelo terminal (`criar_caso.py`, `cadastrar_documentos.py --novo`) nasce sem posse e fica invisível a todas as contas até o operador atribuí-la (`caso-atribuir`, seção 5.16).
- Os ids de dentro da apuração (R001, D001, ids de registros) se repetem entre apurações, como hoje. Eles só valem dentro da apuração que o portão já conferiu.

### 4.5 O que nunca pode vazar entre redações

| O quê | Onde poderia vazar hoje | Regra |
|---|---|---|
| Existência de apuração, conversa, item ou lote | Mensagens diferentes para "não existe" e "não liberado"; `contas-criar` confere `casos` contra o catálogo inteiro | Tabela 4.3. Toda conferência de ids é feita contra o alcance de quem pede. |
| Títulos de apurações e nomes de arquivos | `casos/catalogo.json`, `lixeira/registro.json` e a fila são da instalação | Só saem por `filtrar`. |
| Existência de e-mail ou conta | Entrada e seus contadores de tentativa, "esqueci a senha", troca de e-mail, convite para e-mail que já tem conta | Em cada caminho, a mesma resposta exista a conta ou não. Entrada: a mesma recusa, os mesmos contadores e o mesmo 429, contados pelo identificador digitado (seção 8.2). "Esqueci a senha": a mesma resposta. `conta-email-trocar` para e-mail já usado responde igual ao livre (seção 5.4). Convite para e-mail de outra redação responde como qualquer convite e fica entre os pendentes (seção 8.1). Limitação conhecida: o transporte `tela` não esconde os dois últimos (seção 8.1). |
| Nomes de pessoas e de redações | Lista de contas e eventos da instalação | `equipe-*` só lê a própria redação. E-mails só citam a redação de quem convida. |
| Contagens | "A Mesa já está com N perguntas em andamento" conta a instalação inteira; número de contas e de lotes | Nenhuma resposta leva número que some redações. Os tetos passam a contar por redação (seção 8.5). |
| Gasto e cota | `GET /api/cota` com o bloco da organização | O bloco da redação só vai ao dono dela. |
| Configuração do servidor | `ambiente` devolve o caminho do Python; `ia-config` devolve os quatro últimos caracteres da chave da instalação | No modo `piloto`, `ambiente` sai sem caminhos e `ia-config` mostra só a chave da própria redação. Da chave do serviço, a redação sabe apenas que existe. |
| Autoria | `criado_por` e `autor` nos registros | Só aparecem em respostas de apurações ao alcance. |

Recursos que continuam compartilhados e não levam dado: o teto de conexões do servidor, a fila de extração (uma redação pode atrasar a outra, sem ver nada dela), os arquivos estáticos e o disco.

**Limitação conhecida: não há teto de disco por redação.** Os limites de hoje são por lote (50 MB, 100 arquivos) e por apuração (20 documentos). Uma redação pode abrir quantas apurações quiser e encher o disco de todas. Isso não vaza dado, mas derruba o serviço para as outras. A regra não entra nesta onda. Quem a faria é a Plataforma, junto com o limite de documentos por organização da Onda 4 (PROD-05, item 5): o registro de posse deste contrato dá a ela o que falta, que é saber de que redação é cada apuração. Até lá, o alerta de disco do monitoramento da Infra avisa o operador, que pode suspender a redação (`redacao-suspender`).

### 4.6 Apuração na lixeira

Mandar uma apuração para a lixeira não muda a posse, o responsável nem as participações. Ela continua em `principal['casos']` de quem a alcançava, e o portão a trata como qualquer outra. É isso que permite `restaurar`, `lixeira-alcance` e `lixeira-apagar`, cujo resolvedor (`item`) chega à apuração e à posse dela.

| Quem pede | O que recebe para uma apuração na lixeira |
|---|---|
| Conta sem alcance (situações N e X) | A recusa de alcance de sempre. A lixeira nunca muda essa resposta, então ela não revela que a apuração existe nem que foi excluída. |
| Conta com alcance, em leitura ou escrita | A recusa de item na lixeira, com a mensagem e o código de hoje (`lixeira.conferir_disponivel`, HTTP 400), em todos os papéis. Hoje cada módulo faz essa conferência por conta própria. Passa a ser feita também no portão, logo depois do alcance, para toda operação que não seja uma das quatro de lixeira abaixo: nenhuma leitura devolve conteúdo de apuração que está na lixeira. |
| `GET /api/catalogo` | Não lista a apuração, como hoje. |
| `gerenciar-listar` | Lista o item entre os da lixeira, para o dono e para o repórter que alcança a apuração. |
| `restaurar` | Dono e responsável, pela matriz. |
| `lixeira-alcance`, `lixeira-apagar` | Só o dono. |

O mesmo vale para conversa e rodada na lixeira: o alcance vem da apuração a que pertencem. Depois do apagamento definitivo, o registro de posse vira uma marca de apuração apagada, que ninguém alcança, e as participações somem. O id não volta a ser usado por nenhuma redação. Durante a quarentena do apagamento, a apuração já está fora do alcance de todos.

## 5. Matriz operação × papel

### 5.1 Como ler

Cada linha é uma operação que existe hoje (114 `POST /api/…` com sessão, 4 públicas e as rotas `GET`) ou uma operação nova da Onda 2, marcada com `*` (30 com sessão e 5 públicas). As colunas D, E, R, L e C são dono, editor, repórter, leitor e convidado legado.

| Célula | Significado |
|---|---|
| `sim` | Permitido em toda apuração ao alcance. Em operação sem apuração, permitido. |
| `resp` | Permitido só nas apurações em que a conta é responsável. |
| `autor` | Permitido só em conversa criada pela própria conta, numa apuração ao alcance. |
| `equipe` | Permitido em conversa da equipe e em conversa de autor restrito da própria conta. Negado em conversa de autor restrito de outra conta (seção 5.8). |
| `equipe ou resp` | Como `equipe`; além disso, o responsável pela apuração alcança qualquer conversa dela. |
| `—` | Negado pelo papel. |

Cada célula se abre nas quatro situações da seção 2.6 por esta regra, sem exceção:

| Célula | P | I | N | X |
|---|---|---|---|---|
| `sim`, coluna D | passa | passa | passa | recusa de alcance |
| `sim`, demais colunas | passa | passa | recusa de alcance | recusa de alcance |
| `resp` | passa | 403 `operacao_proibida` | recusa de alcance | recusa de alcance |
| `autor` | passa na conversa própria; `conversa_indisponivel` na de outro | igual a P | recusa de alcance | recusa de alcance |
| `equipe` | passa em conversa da equipe e na de autor restrito própria; `conversa_indisponivel` na de autor restrito alheio | igual a P | recusa de alcance | recusa de alcance |
| `equipe ou resp` | passa em qualquer conversa da apuração | como `equipe` | recusa de alcance | recusa de alcance |
| `—` | 403 `operacao_proibida` | 403 | 403 | 403 |

Na coluna D, a situação N vale como P em toda célula: o dono alcança todas as apurações da redação.

"Recusa de alcance" é `caso_indisponivel` quando a apuração veio do campo `caso`, `conversa_indisponivel` quando veio de `conversa`, e a resposta de item ou lote inexistente nos outros dois resolvedores. **Em X, nenhum papel passa em nenhuma linha.**

A coluna Tipo diz o que a operação faz: `L` lê, `B` baixa arquivo, `E` escreve, `IA` chama o modelo e gasta cota, `A` administra.

### 5.2 Páginas e leituras por GET

| Rota | Resolvedor | Tipo | D | E | R | L | C | Observação |
|---|---|---|---|---|---|---|---|---|
| `GET /saude` | nenhum | L | pública | | | | | Só `{ok: true}`. |
| `GET /entrar`, `/ativar/<token>`, `/aceitar/<token>`\*, `/redefinir/<token>`\*, `/primeiro-acesso`, arquivos de `rotas_estaticas.ARQUIVOS` | nenhum | L | pública | | | | | Página e arquivos estáticos, sem dado de conta nem de apuração. O token fica no caminho e é lido pelo script da página. |
| `GET /convite/<token>` | nenhum | L | pública | | | | | 410, como hoje (convites da versão 1). |
| `GET /api/primeiro-acesso` | nenhum | L | pública | | | | | Só no modo `local-contas`. |
| `GET /` | nenhum | L | sim | sim | sim | sim | sim | Sem sessão: 303 para `/entrar`. Com pendência: 303 para a página que a resolve. |
| `GET /api/sessao` | nenhum | L | sim | sim | sim | sim | sim | Seção 3. |
| `GET /api/integracao` | nenhum | L | sim | sim | sim | sim | sim | Só capacidades do servidor. |
| `GET /api/catalogo` | nenhum | L | sim | sim | sim | sim | sim | Passa por `filtrar`. |
| `GET /api/fila` | `lote`, `caso` ou nenhum | L | sim | sim | sim | sim | sim | Sem parâmetro, passa por `filtrar`. O recibo vai sem caminho de arquivo. |
| `GET /api/cota` | nenhum | L | sim | sim | sim | sim | sim | A própria conta. O bloco da redação só vai ao dono. |

### 5.3 Antes da sessão

Operações públicas: exigem `Origin` e JSON, aceitam corpo de até 4 KB e contam para o limite por endereço. Não há papel.

| Operação | Tipo | Observação |
|---|---|---|
| `entrar` | A | O campo `login` aceita o e-mail ou o login antigo. Com segundo fator, responde `{estado: "segundo_fator"}` sem abrir sessão. Uma recusa só para toda credencial errada. |
| `entrar-segundo-fator`\* | A | Código do autenticador ou código de reserva; abre a sessão. |
| `ativar`, `ativacao-consultar` | A | Continuam para os links emitidos antes da migração e para a recuperação no modo `local-contas`. |
| `convite-consultar`\* | L | `{token}` devolve redação, e-mail, papel, quem convidou, validade e versão dos termos. |
| `convite-aceitar`\* | A | `{token, nome, senha, termos_versao}` cria a conta e abre a sessão, com a pendência de segundo fator quando for obrigatório. |
| `senha-esqueci`\* | A | `{email}`. A resposta é sempre a mesma, exista a conta ou não. |
| `senha-redefinir`\* | A | `{token, senha, codigo?}`. Conta com segundo fator exige também o código. |
| `primeiro-admin` | A | Só `local-contas`, só de `127.0.0.1`, uma vez. Cria a redação única e o primeiro dono. |

### 5.4 A própria conta

Resolvedor `nenhum`. Toda operação age só sobre a conta da sessão. O id de outra conta nunca é aceito.

| Operação | Tipo | D | E | R | L | C | Observação |
|---|---|---|---|---|---|---|---|
| `sessao-sair` | A | sim | sim | sim | sim | sim | |
| `conta-ver`\* | L | sim | sim | sim | sim | sim | Perfil, redação, papel, segundo fator, termos. |
| `conta-atualizar`\* | E | sim | sim | sim | sim | sim | Nome e idioma. |
| `conta-senha-trocar`\* | A | sim | sim | sim | sim | sim | Pede a senha atual; encerra as outras sessões (W08, regra 2). |
| `conta-email-trocar`\* | A | sim | sim | sim | sim | sim | Pede a senha; confirma pelo e-mail novo e avisa o antigo. E-mail já usado por outra conta, de qualquer redação, responde igual ao livre ("confirmação enviada"): o servidor grava um pedido sem efeito, nada muda na conta e nenhuma mensagem vai ao endereço em uso. |
| `conta-fator-iniciar`\*, `conta-fator-confirmar`\* | A | sim | sim | sim | sim | sim | Cadastro do autenticador; os códigos de reserva aparecem uma vez. |
| `conta-fator-codigos`\* | A | sim | sim | sim | sim | sim | Gera códigos novos e invalida os antigos. Pede senha e código. |
| `conta-fator-remover`\* | A | — | — | sim | sim | sim | Negado a quem tem segundo fator obrigatório. |
| `conta-sessoes`\* | L | sim | sim | sim | sim | sim | W08, regra 5. |
| `conta-sessao-encerrar`\*, `conta-sessoes-encerrar-outras`\* | A | sim | sim | sim | sim | sim | Só sessões da própria conta. |
| `conta-termos-aceitar`\* | A | sim | sim | sim | sim | sim | |
| `conta-exportar`\* | B | sim | sim | sim | sim | sim | Seção 8.4. |
| `conta-excluir`\* | A | sim | sim | sim | sim | sim | Pede a senha e o nome digitado. O último dono ativo é recusado (`ultimo_dono`). |

### 5.5 A redação: equipe, convites, cota e chave

Resolvedor `nenhum`. Toda operação age só sobre a redação da sessão. O id de uma conta, de um convite ou de uma apuração de outra redação responde como inexistente.

| Operação | Tipo | D | E | R | L | C | Observação |
|---|---|---|---|---|---|---|---|
| `equipe-listar`\* | L | sim | — | — | — | — | Pessoas, papéis, apurações de cada uma, gasto do mês, convites pendentes. |
| `equipe-convidar`\*, `equipe-convite-reenviar`\*, `equipe-convite-cancelar`\* | A | sim | — | — | — | — | Seção 8.1. Convidar com o papel dono pede a senha. |
| `equipe-papel`\* | A | sim | — | — | — | — | Recusa rebaixar o último dono ativo. Promover a dono pede a senha. Nunca atribui `convidado`. |
| `equipe-desativar`\*, `equipe-reativar`\*, `equipe-remover`\* | A | sim | — | — | — | — | Recusam o último dono ativo. Desativar encerra as sessões e para as execuções em curso, como hoje. |
| `equipe-recuperar`\*, `equipe-recuperar-confirmar`\* | A | sim | — | — | — | — | Seção 8.2. Nunca devolvem link no modo `piloto`. |
| `equipe-teto`\* | A | sim | — | — | — | — | Teto mensal por pessoa, até o teto da redação. |
| `equipe-atividade`\* | L | sim | — | — | — | — | Acessos e ações de administração da redação, sem conteúdo (W09, regra 8). Não inclui `acesso_negado` (seção 4.3). |
| `ia-config` | L | sim | — | — | — | — | No modo `piloto`: provedor, modelo e a chave da própria redação (presença e quatro últimos caracteres). |
| `ia-config-salvar` | A | sim | — | — | — | — | No modo `piloto`: só grava ou remove a chave da própria redação, e pede a senha. Provedor e modelo da instalação são do operador. Nos modos locais, como hoje. |
| `ambiente` | L | sim | — | sim | — | — | No modo `piloto`, sem caminhos do servidor. |
| `codex-status` | L | sim | sim | sim | sim | sim | Estado da conexão com o provedor; não leva dado de redação. |
| `codex-desligar` | A | sim | — | — | — | — | Só nos modos locais. No `piloto`, recusado a todos (`servico_nao_encerravel`), como hoje. |

**Operações retiradas:** `contas-listar`, `contas-criar`, `contas-atualizar`, `contas-desativar`, `contas-reativar` e `contas-recuperar` saem de `OPERACOES_API` e passam a responder 404, como qualquer operação inexistente, para todos os papéis. As `equipe-*` as substituem. `contas-criar` e `contas-recuperar` devolviam o link a quem pedia, que é o defeito de CON-03. Elas saem na mesma integração em que a tela Equipe do Frontend entra.

### 5.6 Apurações: criação, participação e lixeira

| Operação | Resolvedor | Tipo | D | E | R | L | C | Observação |
|---|---|---|---|---|---|---|---|---|
| `cadastrar` com `novo: true` | `novo` | E | sim | — | sim | — | — | O servidor gera o id e registra posse, responsável e participação. |
| `gerenciar-listar` | nenhum; `caso` opcional | L | sim | — | sim | — | — | Catálogo, lixeira e conversas passam por `filtrar`. |
| `caso-participantes`\* | `caso` | L | sim | sim | sim | sim | — | |
| `caso-incluir`\*, `caso-retirar`\* | `caso` | A | sim | — | resp | — | — | Só contas da mesma redação. Conta de outra redação responde como inexistente. |
| `caso-responsavel`\* | `caso` | A | sim | — | — | — | — | O novo responsável precisa ser dono ou repórter da redação. |
| `excluir` | `caso`; com `tipo: "conversa"`, `caso` e `conversa` | E | sim | — | resp | — | — | Manda apuração, conversa ou rodada para a lixeira. Quando o item é uma conversa, o portão resolve a conversa e exige que ela seja da apuração do pedido, como nas `codex-*`, sem depender da conferência que `Conversas.gerenciar` já faz. A rodada é resolvida dentro da apuração, pelo módulo. |
| `restaurar` | `item` | E | sim | — | resp | — | — | |
| `lixeira-alcance` | `item` | L | sim | — | — | — | — | |
| `lixeira-apagar` | `item` | A | sim | — | — | — | — | Apagamento definitivo. Além do nome do item, passa a pedir a senha. |

### 5.7 Documentos e busca

Resolvedor `caso` em todas.

| Operação | Tipo | D | E | R | L | C |
|---|---|---|---|---|---|---|
| `cadastrar` em apuração existente, `preparar-pdfs` | E | sim | — | sim | — | — |
| `inventario`, `analises`, `buscar`, `ler`, `cobertura` | L | sim | sim | sim | sim | — |
| `original` | B | sim | sim | sim | sim | — |
| `fontes-web-listar`, `fontes-web-abrir` | L | sim | sim | sim | sim | — |
| `fontes-web-capturar` | E | sim | — | — | — | — |

### 5.8 Conversa com os documentos

| Operação | Resolvedor | Tipo | D | E | R | L | C | Observação |
|---|---|---|---|---|---|---|---|---|
| `codex-listar` | `caso` | L | sim | sim | sim | sim | autor | Convidado recebe só as próprias conversas. |
| `codex-perguntar`, conversa nova | `caso` | IA | sim | sim | sim | sim | sim | Leitor e convidado enviam só `caso` e `pergunta`. A conversa deles nasce com autor restrito. |
| `codex-perguntar`, com `conversa` | `caso` e `conversa` | IA | equipe | equipe | equipe | autor | autor | Leitor e convidado enviam só `caso`, `pergunta` e `conversa`. |
| `codex-retomar` | `conversa` | IA | equipe | equipe | equipe | autor | autor | Retomar gasta a cota de quem retoma. |
| `codex-cancelar` | `conversa` | E | sim | equipe | equipe ou resp | autor | autor | Para uma execução em curso. Não gasta cota. |
| `codex-eventos` | `conversa` | L | sim | sim | sim | sim | autor | Leitor e convidado recebem a conversa sem os campos internos e sem o texto bruto de erros, como o convidado de hoje. |
| `codex-original` | `conversa` | B | sim | sim | sim | sim | autor | |
| `codex-observacoes` | `caso` | L | sim | sim | sim | — | — | |
| `codex-corpus-previa`, `codex-caderno-previa`, `codex-diligencias-previa` | `caso` e `conversa` | L | sim | sim | sim | — | — | |
| `codex-documentos-cadastrar` | `caso` e `conversa` | E | equipe | — | equipe | — | — | Continua a conversa com documentos novos. |

**Quem continua uma conversa. A regra é uma só, e vale aqui e na seção 2.1.**

- Há dois tipos de conversa. A **conversa de autor restrito** é a aberta por um leitor ou por um convidado; o campo `dono` de `conversa.json` guarda o id de quem a abriu. A **conversa da equipe** é a aberta por dono, editor ou repórter; o campo `dono` fica vazio, como nas conversas dos administradores de hoje.
- **Ler** (`codex-listar`, `codex-eventos`, `codex-original`): qualquer conta com alcance sobre a apuração lê os dois tipos. O convidado legado lê só as próprias.
- **Acrescentar pergunta, retomar e continuar com documentos:**
  - na conversa de autor restrito, só o autor. Nem o dono acrescenta pergunta à conversa de um leitor;
  - na conversa da equipe, dono, editor e repórter com alcance, como os administradores de hoje. Leitor e convidado, nunca.
- **Cancelar uma execução em curso:** quem pode continuar a conversa, e também o dono e o responsável pela apuração, em qualquer conversa dela. Cancelar não lê nem escreve conteúdo; só para o gasto.
- O autor é conferido pelo id da conta. Um leitor promovido a repórter continua autor das conversas que abriu como leitor.
- Quem não pode continuar uma conversa recebe `conversa_indisponivel`, a mesma resposta da conversa inexistente.

A cota diária de perguntas (`OPERACOES_COM_COTA`) continua valendo só para o convidado. Os quatro papéis são limitados pelos tetos mensais em reais (seção 8.5).

### 5.9 Achados

Resolvedor `caso` em todas.

| Operação | Tipo | D | E | R | L | C |
|---|---|---|---|---|---|---|
| `achados-catalogo`, `achados-buscar`, `achados-detalhe`, `achados-evidencia`, `achados-briefing` | L | sim | sim | sim | sim | — |
| `achados-original`, `achados-exportar` | B | sim | sim | sim | sim | — |
| `achados-revisao-salvar` | E | sim | sim | sim | — | — |

### 5.10 Caderno, notas e diligências

Resolvedor `caso` em todas.

| Operação | Tipo | D | E | R | L | C |
|---|---|---|---|---|---|---|
| `apuracao-listar`, `apuracao-notas`, `apuracao-nota`, `caderno-documentos`, `caderno-listar`, `caderno-detalhe`, `diligencias-listar` | L | sim | sim | sim | sim | — |
| `apuracao-exportar`, `apuracao-original`, `caderno-exportar`, `caderno-original`, `diligencias-original` | B | sim | sim | sim | sim | — |
| `apuracao-salvar`, `apuracao-adicionar`, `apuracao-excluir`, `apuracao-nota-salvar`, `apuracao-nota-inserir`, `apuracao-nota-excluir`, `caderno-salvar`, `caderno-cruzar`, `diligencias-criar`, `diligencias-atualizar`, `diligencias-responder` | E | sim | sim | sim | — | — |

### 5.11 Quadros de evidência e tabelas

Resolvedor `caso` em todas.

| Operação | Tipo | D | E | R | L | C |
|---|---|---|---|---|---|---|
| `hipoteses-listar`, `hipoteses-detalhe`, `hipoteses-quadro`, `linha-tempo-listar`, `linha-tempo-detalhe`, `comparar-evidencias`, `comparar-documentos`, `mapa-ver`, `mapa-homonimos`, `tabelas-listar`, `tabelas-detalhe`, `tabelas-historico-celula`, `tabelas-calcular` | L | sim | sim | sim | sim | — |
| `tabelas-exportar` | B | sim | sim | sim | sim | — |
| `hipoteses-criar`, `hipoteses-atualizar`, `linha-tempo-criar`, `linha-tempo-atualizar`, `mapa-entidade-criar`, `mapa-entidade-atualizar`, `mapa-relacao-criar`, `mapa-relacao-atualizar`, `tabelas-criar`, `tabelas-atualizar`, `tabelas-corrigir` | E | sim | sim | sim | — | — |

### 5.12 Texto da matéria e entrevistas

Resolvedor `caso` em todas.

| Operação | Tipo | D | E | R | L | C |
|---|---|---|---|---|---|---|
| `redacao-listar`, `redacao-conferir`, `redacao-dividir`, `entrevistas-lacunas`, `entrevistas-listar`, `entrevistas-detalhe` | L | sim | sim | sim | sim | — |
| `entrevistas-exportar` | B | sim | sim | sim | sim | — |
| `redacao-criar`, `redacao-nova-versao`, `redacao-vincular`, `entrevistas-preparar`, `entrevistas-editar`, `entrevistas-responder` | E | sim | sim | sim | — | — |
| `redacao-revisar` | E | sim | sim | — | — | — |

### 5.13 Rascunhos e retomada

Resolvedor `caso` em todas. O rascunho é sempre da conta da sessão: ninguém lê o rascunho de outra pessoa, nem o dono.

| Operação | Tipo | D | E | R | L | C | Observação |
|---|---|---|---|---|---|---|---|
| `rascunhos-salvar`, `rascunhos-ler`, `rascunhos-listar`, `rascunhos-descartar` | E | sim | sim | sim | sim | sim | Leitor e convidado só na tela `pergunta`, como o convidado de hoje. |
| `continuidade-resumo` | L | sim | sim | sim | — | — | |

### 5.14 Modos locais

- **`local`** (sem contas): não muda. O operador único da máquina entra na matriz como dono, com `casos: None`, e não há redação nem posse. As operações `conta-*`, `equipe-*` e `caso-*` não existem nesse modo.
- **`local-contas`** (Mesa instalada no Windows): uma redação só, criada pelo formulário do primeiro administrador. A matriz vale inteira. Sem servidor de e-mail, o convite e a recuperação mostram o link na tela de quem pediu, como hoje (seção 8.1). O segundo fator é opcional.

### 5.15 Operações sensíveis pedem a senha de novo

`conta-senha-trocar`, `conta-email-trocar`, `conta-fator-iniciar`, `conta-fator-codigos`, `conta-fator-remover`, `conta-excluir`, `equipe-convidar` (ao convidar como dono), `equipe-papel` (ao promover a dono), `equipe-remover`, `equipe-recuperar`, `ia-config-salvar` e `lixeira-apagar` levam a senha da conta no corpo. Uma sessão aberta num computador esquecido, ou um conteúdo malicioso exibido na Mesa (seção 9), não consegue executá-las.

### 5.16 Operador do Vlado

O operador não tem conta, sessão nem papel na Mesa: em toda linha desta matriz, a célula dele é "sem sessão, 401". Ele age pelo terminal do servidor (decisão 6). O armazenamento recusa qualquer papel fora dos cinco da seção 2.3.

| Comando (`python scripts/acesso.py …`) | O que faz |
|---|---|
| `redacao-criar --nome … --email-dono …` | Cria a redação e convida o primeiro dono (D3). |
| `redacao-listar` | Id, nome, situação, número de pessoas e de apurações, gasto do mês. Só totais. |
| `redacao-suspender`, `redacao-reativar` | Suspende ou devolve o acesso da redação inteira. |
| `redacao-cota` | Define o teto mensal da redação. |
| `redacao-encerrar` | Exporta e agenda o apagamento da redação (seção 8.4). |
| `dono-convidar` | Convida um dono para redação que ficou sem dono ativo. |
| `recuperacao-confirmar` | Segunda confirmação da recuperação de um dono (seção 8.2). |
| `caso-atribuir` | Dá posse a uma apuração criada pelo terminal. |
| `migrar --simular`, `migrar` | Seção 6. |
| `manutencao` | Vence convites, avisa e desativa contas inativas, poda eventos. |

Toda ação do operador vira evento com `por: "operador"`, visível ao dono da redação em `equipe-atividade`. O operador tem acesso ao disco do servidor, e nenhum contrato de contas muda isso: a proteção contra o operador é a regra de D4, só documentos públicos.

### 5.17 Como a matriz vira teste

1. **A matriz é dado, não lógica.** `autorizacao.MATRIZ` tem uma entrada por operação, com resolvedor, tipo e a célula de cada papel. O portão decide lendo essa tabela.
2. **O contrato é a fonte.** Um teste lê as tabelas 5.2 a 5.13 deste arquivo e exige que sejam iguais a `MATRIZ`, operação por operação e célula por célula. Mudar o código sem mudar o contrato, ou o contrário, falha a suíte.
3. **Nada fica de fora.** Outro teste exige que o conjunto de operações de `MATRIZ` seja igual a `interface_pesquisa.OPERACOES_API` mais `OPERACOES_PUBLICAS` mais as rotas `GET`. Rota nova sem linha na matriz falha a suíte. Em 22/11/2026 as 114 operações e as 4 públicas de `cb9afa8` foram conferidas, por script, contra as tabelas 5.2 a 5.13: nenhuma falta (as seis retiradas estão na nota da seção 5.5).
4. **Cada célula é um caso de teste gerado.** `testes/test_matriz_contas.py` percorre operação × papel × situação (P, I, N, X) com `subTest` e faz a requisição HTTP de verdade contra um servidor de teste.
   - Célula que passa: a resposta não é 401, não é 403 e não é recusa de alcance. O corpo do pedido é mínimo, então a rota pode recusar por validação; o que se prova é que a autorização deixou passar.
   - Célula que recusa: o status e o código exatos da tabela 5.1.
   - Recusa em operação de tipo `E`, `IA` ou `A`: além da resposta, nada mudou em `casos/`, `execucoes/`, `conversas/`, `lixeira/` nem no armazenamento de contas (resumo por hash antes e depois).
   - Recusa em operação de tipo `L` ou `B`: o corpo não contém nenhuma das sentinelas da outra redação (título de apuração, nome de arquivo, nome e e-mail de pessoa, nome da redação).
5. **O cenário.** Duas redações semeadas por `scripts/dados_sinteticos.py`. A redação A tem dono, editor, dois repórteres, leitor e convidado, com uma apuração de cada repórter e participações que produzem P, I e N para cada papel. A redação B tem dono e repórter, com uma apuração de **mesmo título** de uma de A e registros de **mesmos ids internos** (R001, D001, mesma `requisicao_id`). Os ids de B são usados pelas sessões de A. Cada apuração de A tem uma conversa da equipe e uma conversa de autor restrito, aberta pelo leitor, para as células `autor`, `equipe` e `equipe ou resp`. Uma apuração de A está na lixeira, para a tabela da seção 4.6.
6. **Travessia, além das células.** `testes/test_isolamento_redacoes.py` cobre o que a matriz não expressa: cada resolvedor (`conversa`, `item`, `lote`) com id da outra redação; referência de evidência de outra apuração dentro de um corpo válido; as três listagens; convite, inclusão e mudança de papel com id de conta da outra redação; a igualdade byte a byte das cinco causas de `caso_indisponivel`. E a enumeração de contas: 11 senhas erradas, de dois endereços, para um e-mail com conta e para um sem conta, com a mesma sequência de status e de corpos; "esqueci a senha" para os dois; `conta-email-trocar` para e-mail livre e para e-mail usado em outra redação; convite para e-mail de outra redação, que responde igual e aparece entre os pendentes.
7. **Invariantes.** Nos modos com contas nenhum principal tem `casos: None`; apuração sem posse não é alcançada por ninguém; nenhum módulo de rota lê `principal['papel']` (teste estático sobre `scripts/rotas_*.py`).

São 108 operações atuais que ficam (as 114 menos as seis retiradas) e 30 novas com sessão, vezes cinco papéis e até quatro situações: mais de 2.000 células. As 4 públicas atuais e as 5 novas têm testes próprios, sem papel. O teste roda sem modelo e sem rede, com o hash de senha rápido que `testes/test_acesso.py` já usa.

## 6. Migração das contas atuais

Hoje `acesso/acesso.json` (`versao: 2`) tem contas `admin` e `convidado`, sessões, tentativas, uso diário e os últimos 1.000 eventos. A migração é feita na primeira leitura pelo código novo, sob a trava do armazenamento, como a migração da versão 1 já faz.

| Hoje | Passa a ser |
|---|---|
| A instalação | Uma redação, a redação inicial. O nome vem de `VLADO_REDACAO_NOME` ou fica "Redação", e o dono o troca depois. |
| Conta `admin` | Dono da redação inicial, **com o mesmo `id`**. |
| Conta `convidado` | Perfil legado `convidado` na redação inicial, com o mesmo `id` e a mesma `cota_diaria`. |
| `casos` do convidado | Participações. Apuração que não existe mais é descartada e anotada no relatório. |
| Toda apuração de `casos/catalogo.json`, inclusive as da lixeira | Posse da redação inicial, sem responsável (`origem: "migracao"`). Os donos alcançam todas, como os administradores de hoje. |
| `login` | Mantido; continua valendo na entrada. O e-mail fica vazio até a pessoa informar. |
| Senha (hash argon2) e link de ativação pendente | Mantidos. |
| `uso` (perguntas do dia) e `primeiro_admin_em` | Mantidos. |
| Eventos | Copiados para a atividade da redação inicial. |
| Sessões e contadores de tentativa | Descartados: todos entram de novo. |
| Gasto do mês da organização `instalacao` em `ajustes/gasto_mensal.json` | Passa a ser o gasto da redação inicial, sem zerar. |

Todo administrador vira dono porque é o único papel que mantém o que ele alcança hoje. Depois, cada redação rebaixa quem na prática é repórter ou editor.

**Por que os identificadores não mudam.** O `id` da conta está gravado em `criado_por.id` das notas, em `conta_id` das revisões e correções, no campo `dono` de `conversa.json`, no nome das pastas de rascunho (`casos/<caso>/rascunhos/<conta>/`), nas chaves do gasto mensal e no registro de auditoria. Com o mesmo `id`, nenhum desses arquivos é tocado e a autoria continua resolvendo. Os registros de apuração não são reescritos em nenhum passo.

**Garantias, cada uma com teste** (`testes/test_migracao_contas.py`, sobre armazenamentos sintéticos):

1. **Não ampliação.** Para cada conta migrada, o conjunto de pares (operação, apuração) permitidos depois está contido no conjunto permitido antes. Vale por construção: o administrador alcançava tudo e vira dono da única redação; o convidado mantém o perfil.
2. **Autoria.** Notas, revisões e conversas criadas antes mostram o mesmo autor depois, e o convidado continua listando as próprias conversas e achando os próprios rascunhos.
3. **Reversível.** O arquivo antigo fica como `acesso.v2.json`, com permissão 0600. O banco novo é escrito num arquivo temporário e só troca de nome no fim; uma queda no meio deixa o `acesso.json` como estava.
4. **Idempotente.** Rodar de novo não duplica nada.
5. **Ensaio.** `acesso.py migrar --simular` imprime o relatório (contas por papel, apurações, participações descartadas, contas sem e-mail) sem gravar. O operador roda numa cópia antes.

**O que muda para as pessoas no primeiro acesso depois da migração:** todos entram de novo; os donos cadastram o segundo fator antes de operar (no modo `piloto`); cada conta é convidada a informar o e-mail, sem o qual não há redefinição de senha nem aviso de novo acesso.

**Instalação de uma redação só.** Depois da migração ela é uma instalação com uma redação, e o operador pode criar outras (D1). O modo `local` não tem contas e não migra nada. No modo `local-contas` a migração é a mesma e a instalação fica com exatamente uma redação; o terminal recusa criar a segunda.

## 7. Armazenamento

**Decisão: contas, redações, posse, participações, convites, sessões e eventos vão para SQLite, em `acesso/contas.sqlite`** (CON-06). O registro de auditoria continua em `registro/auditoria-*.jsonl` e o gasto continua em `ajustes/gasto_mensal.json`.

Razões:

1. **Uma migração só, agora.** A Onda 2 já reescreve o formato. Trocar o armazenamento depois, com dados de várias redações em produção, seria uma segunda migração, mais arriscada que esta, que parte de uma redação e de poucas contas.
2. **Regras que cruzam tabelas.** "Não remover o último dono", "participação só entre conta e apuração da mesma redação" e "um e-mail, uma conta" viram restrições do banco e transações. O arquivo único só as garante por disciplina do código.
3. **Leitura a cada requisição.** Hoje toda requisição lê e interpreta o arquivo inteiro sob uma trava exclusiva entre processos. Com posse e participações, essa leitura cresce com o número de redações. No SQLite é uma consulta por índice, e leitores não bloqueiam uns aos outros.
4. **Escrita parcial.** Hoje cada toque de sessão regrava o arquivo inteiro, e os eventos são cortados em 1.000. Passa a gravar uma linha.
5. **Sem dependência nova.** `sqlite3` é da biblioteca padrão e o projeto já usa SQLite no índice.

Custos, com o que os cobre:

- **Backup.** Copiar um banco em uso pode pegar um estado incompleto. `acesso.py` oferece uma cópia consistente (API de backup do SQLite) e o `backup.py` da Infra passa a usá-la. A restauração chama uma função de `acesso.py` que encerra todas as sessões, no lugar da edição do JSON que faz hoje.
- **Não é legível num editor.** `acesso.py listar` e `migrar --simular` mostram o conteúdo sem segredos.
- **Arquivos que leem `acesso.json` direto:** `scripts/backup.py`, `scripts/registro_acesso.py` (só o texto de ajuda), dez arquivos de teste e quatro documentos (`deploy/INCIDENTE.md`, `deploy/MONITORAMENTO.md`, `docs/CONTRATOS_ENTREGA.md`, `docs/INSTALADOR_WINDOWS.md`). A lista vai para os donos de cada um (seção 10).

Forma do banco, em linhas gerais:

| Tabela | Guarda |
|---|---|
| `organizacoes`, `contas` | Seções 2.2 e 2.3. E-mail e login únicos. |
| `casos` | Posse: `caso` como chave primária, redação, responsável. |
| `participacoes` | Conta e apuração, com a restrição de mesma redação. |
| `convites`, `links` | Hash do token, validade, estado. `links` guarda ativação, redefinição e troca de e-mail. |
| `sessoes` | Hash do cookie, id público, conta, CSRF, validades, cliente, aparelho, IP de criação e do último uso. |
| `fatores`, `codigos_reserva`, `aparelhos` | Semente cifrada e último passo aceito; hash dos códigos; hash das marcas de aparelho conhecido. |
| `tentativas`, `recuperacoes` | Contadores por conta e por conta e endereço; pedidos de recuperação à espera da segunda confirmação. |
| `termos_aceites`, `eventos`, `uso_diario` | Aceites com versão; atividade da redação; cota diária do convidado. |

O banco usa modo WAL, chaves estrangeiras ligadas, escrita em transação imediata, permissão 0600 e versão do esquema em `user_version`. Banco ilegível ou que falha na conferência de integridade responde 503 e não deixa ninguém entrar, como o arquivo ilegível de hoje. O banco fica em disco local do servidor ou em volume Docker local; sistema de arquivos de rede não é suportado.

**A semente do segundo fator é cifrada** (AES-GCM, biblioteca `cryptography`) com uma chave em `segredos/contas.chave`, fora do volume de contas e fora do backup comum, como a chave do registro de auditoria. Quem copiar só o banco não gera códigos (decisão 13). As chaves de IA das redações ficam em `segredos/chaves.json`, numa seção por redação.

## 8. Desenho do que a Onda 2 entrega

Esta seção fixa comportamento, não implementação.

### 8.1 E-mail transacional (CON-02, D7)

- **Uma interface, três transportes.** O código de contas chama `correio.enviar(tipo, para, idioma, dados)`. O transporte vem da configuração:
  - `simulado`: guarda as mensagens em memória. É o dos testes, que leem dali o link.
  - `tela`: não envia; devolve o link a quem pediu. Vale no `local-contas` e, enquanto D7 não fecha, na homologação do `piloto`.
  - `smtp`: envio real, com credenciais só em variáveis de ambiente.
  Trocar de provedor é escrever outro transporte; nada mais muda.
- **Mensagens:** convite, redefinição de senha, aviso de novo acesso, senha trocada, segundo fator alterado, recuperação de conta, muitas tentativas, confirmação de e-mail novo, aviso de conta inativa.
- **Só texto.** Sem HTML, sem imagem, sem link que não seja da própria instalação. Os modelos são versionados, em português e inglês. Nome de pessoa e de redação entram sem quebras de linha.
- **O token só existe no link.** O servidor guarda o hash. Falha de envio aparece ao dono na Equipe, e reenviar gera um token novo e invalida o anterior.
- **Convite:** vale 7 dias, uma única vez. O dono reenvia ou cancela. O e-mail vem do convite e não pode ser trocado ao aceitar (W10, regra 3). O convite leva papel e apurações; ao aceitar, a conta nasce com as participações.
- **Convite para e-mail que já tem conta em outra redação:** quem convida recebe a mesma resposta de qualquer convite. O convite aparece entre os pendentes, pode ser reenviado e cancelado e vence no prazo, como os outros. Quem recebe o e-mail é a pessoa, com a explicação de que no teste uma conta pertence a uma redação só; o link não cria conta. Convite para e-mail que já é da própria redação é recusado dizendo a razão, porque o dono já vê quem é da redação. Para o convite não virar meio de encher a caixa de alguém, cada redação tem teto de convites pendentes (50) e cada convite é reenviado no máximo uma vez por hora.
- **Sem transporte real** (`tela`), "esqueci a senha" fica desligado, porque não há a quem mostrar o link, e a recuperação é feita pelo dono com dupla confirmação (seção 8.2). A produção não sobe com `tela` (decisão 12).
- **Limitação conhecida do transporte `tela`** (modo `local-contas` e homologação do `piloto`). O link aparece na tela de quem pediu, e o servidor não tem como esconder dele o que o link faz. Quem convida um e-mail de outra redação abre o link e vê que ele não cria conta. Quem troca o próprio e-mail por um já usado vê que a confirmação não se completa. No `local-contas` há uma redação só, e isso não revela nada de outra. Na homologação com mais de uma redação, revela que aquele e-mail tem conta em alguma redação, sem dizer qual. A limitação é aceita e fica registrada; com o transporte `smtp` ela não existe.

### 8.2 Senha, segundo fator, tentativas e recuperação (CON-03)

- **Senha:** 12 a 256 caracteres, argon2id, como hoje, aceitando colar e gerenciador (W08, regra 4). Trocar pede a atual e encerra as outras sessões. Redefinir por e-mail usa link de 1 hora e uso único; a conta com segundo fator informa também o código.
- **Segundo fator:** TOTP (RFC 6238, 6 dígitos, 30 segundos, um passo de tolerância). O mesmo código não vale duas vezes. Dez códigos de reserva de uso único, mostrados uma vez.
- **Obrigatório para dono e editor** no modo `piloto`, como dizem as regras do W08 e do W10; o plano dizia só dono (decisão 3). Quem tem a obrigação e ainda não cadastrou fica com a pendência `segundo_fator`.
- **Chave de acesso** (passkey), que o W08 e o W10 mostram como alternativa, fica fora do lançamento (decisão 4).
- **Entrada em dois passos:** senha certa numa conta com segundo fator não abre sessão; devolve um cookie de 5 minutos que só serve para `entrar-segundo-fator`. Cinco códigos errados invalidam esse cookie.
- **Teto por identificador digitado.** Todo contador de falha de entrada é contado pelo identificador que a pessoa digitou (o e-mail ou o login antigo, em minúsculas), **exista a conta ou não**, como o código de hoje já faz com o login (`acesso._chave_tentativa`, `acesso.py:572`). Nenhum contador, bloqueio ou resposta depende de a conta existir.
  - Continua o bloqueio de hoje, por identificador e endereço: 5 falhas, 15 minutos.
  - Acrescenta-se um teto por identificador, somando todos os endereços: 10 falhas em 1 hora põem o identificador em modo protegido por 1 hora.
  - No modo protegido, toda tentativa recebe o mesmo 429, com o corpo `bloqueado` de hoje, haja ou não conta com aquele identificador. Quem manda 11 senhas erradas de dois endereços recebe a mesma sequência de respostas para um e-mail com conta e para um e-mail sem conta.
  - A única tentativa que atravessa o modo protegido é a que traz a marca de um aparelho que aquela conta já usou. Um identificador sem conta não tem aparelho conhecido, e quem ataca uma conta alheia não tem a marca dela: para ele os dois casos são iguais.
  - O contador de um identificador sem conta é guardado e vence como o de uma conta: some quando o prazo acaba e nunca é despejado antes. Quem limita o crescimento da tabela é o teto por endereço (20 tentativas por minuto).
  - O hash de senha continua sendo calculado para identificador sem conta, como hoje, para o tempo de resposta não distinguir os dois casos.
  - O e-mail de aviso de muitas tentativas só sai quando a conta existe, e quem ataca não o vê.
  - As falhas do código do segundo fator contam no mesmo teto. Elas só acontecem depois da senha certa, quando a existência da conta já não é segredo para quem tenta.

  Um bloqueio total permitiria a qualquer pessoa trancar o dono fora sabendo o e-mail dele; o modo protegido para a força bruta distribuída sem dar esse poder.
- **Aparelho conhecido:** um cookie próprio, aleatório e de longa duração, cujo hash fica na conta. Serve ao modo protegido e ao aviso de novo acesso.
- **Recuperação entre administradores, com dupla confirmação.** Recuperar encerra as sessões, invalida senha e segundo fator e manda à pessoa um link para refazer os dois. Sempre há duas partes:
  - Alvo que não é dono: o dono pede e a própria pessoa confirma pelo link, que só ela recebe.
  - Alvo que é dono: outro dono pede e um terceiro dono confirma (`equipe-recuperar-confirmar`). Sem terceiro dono, quem confirma é o operador, pelo terminal.
  - Transporte `tela`: toda recuperação exige a segunda confirmação antes de o link aparecer.
  O dono nunca troca o e-mail de outra pessoa, para a recuperação não virar tomada de conta.
- **O único dono que perdeu senha, aparelho e códigos** é recuperado pelo operador (`dono-convidar`), com aviso ao e-mail do dono e espera de 24 horas (decisão 14).

### 8.3 Sessões e acessos (CON-04)

- **Lista de sessões** da própria conta: aparelho (navegador e sistema, tirados do cabeçalho do navegador), cliente, criação, último uso, endereço e a marca "esta". A cidade aproximada do W08 depende de uma base de localização por IP e fica fora do lançamento (decisão 5).
- **Encerrar** uma sessão ou todas as outras vale na requisição seguinte. Uma espera de eventos já aberta pode durar até 20 segundos depois do encerramento.
- **Acesso com IP.** Toda entrada grava data, aparelho e IP: a pessoa vê as próprias, o registro de auditoria da Onda 1 guarda todas, e o dono vê na atividade "entrou de aparelho novo", sem o IP.
- **Novo acesso avisa por e-mail** quando a entrada vem de aparelho que a conta nunca usou (W08, regra 6).
- **Eventos novos no registro de auditoria:** convite enviado, reenviado, cancelado e aceito; senha trocada e redefinida; segundo fator ativado, removido e recusado; código de reserva usado; sessão encerrada à distância; papel alterado; participação incluída e retirada; responsável alterado; recuperação pedida e confirmada; termos aceitos; conta exportada, excluída e expirada; redação criada, suspensa e encerrada; chave da redação alterada; teto alterado; `acesso_negado` com motivo. Todos seguem a regra do registro: listas fechadas, sem texto livre.

### 8.4 Ciclo de vida (CON-05)

- **Aceite de termos:** o convite mostra a versão vigente, e o aceite grava versão, data e IP. Versão nova gera a pendência `termos` no próximo acesso. O texto é da Documentação e depende de D6.
- **Exportar meus dados:** um arquivo com perfil, redação e papel, aceites, sessões, acessos e eventos da conta, e a lista do que a pessoa criou (tipo, apuração, data, identificador). O conteúdo das apurações não entra: é da redação, e sai pela exportação da apuração (PROD-08).
- **Excluir conta:** pede a senha e o nome digitado. Encerra sessões, apaga senha, segundo fator, e-mail, nome e participações, e deixa só o `id` com a situação `excluida`. O `id` nunca é reaproveitado. O último dono não se exclui.
- **O que acontece com o trabalho feito:** notas, revisões e conversas ficam com a redação. Os registros são encadeados por hash e não podem ser reescritos (contrato de evidência), então o nome continua gravado nos arquivos antigos e nos backups. Na Mesa e nas exportações novas, o autor de conta excluída aparece como "Conta excluída": a troca é feita num ponto só, na saída, pelo `id`. O W08 promete "sem seu nome"; isso vale para o que a Mesa mostra, não para o arquivo histórico (decisão 10).
- **Remover da redação** (`equipe-remover`) tem o mesmo efeito, por decisão do dono.
- **Conta inativa:** 180 dias sem entrar geram um aviso por e-mail; 30 dias depois, a conta é desativada, não apagada. O dono a reativa. Conta `aguardando_senha` cujo convite venceu some com o convite.
- **Redação encerrada** (pelo operador): exportação entregue ao dono, depois apagamento das apurações pela quarentena da Onda 1 e exclusão das contas. O apagamento não alcança backups já feitos; a retenção deles é da Infra e entra na política de privacidade.
- **Quem executa os prazos:** `acesso.py manutencao`, agendado pela Infra uma vez por dia, e a mesma varredura na partida do servidor.

### 8.5 Cota de IA por redação (CUS-01, D2)

- **A ligação é uma função.** `custo.chaves_orcamento(conta)` hoje devolve a organização fixa `instalacao`. Passa a devolver a redação da conta, lida do armazenamento de contas. O gasto de cada pergunta cai na pessoa e na redação dela.
- **Três tetos, mais o do provedor:**
  1. por pessoa, definido pelo dono (`equipe-teto`), nunca acima do da redação;
  2. por redação, definido pelo operador (`redacao-cota`);
  3. da instalação, a soma do que o serviço aceita pagar, definido pelo operador;
  4. o teto no painel do provedor, fora do Vlado.
- **Quem vê o quê:** a pessoa vê o próprio gasto (`GET /api/cota`); o dono vê o da redação e o de cada pessoa (`equipe-listar`); o operador vê o total de cada redação. Sempre em reais.
- **Chave própria da redação (opcional):** o dono a cadastra em `ia-config-salvar`. Com ela, as perguntas da redação usam essa chave e o gasto não desconta da cota paga pelo serviço. O teto por pessoa continua valendo e o gasto continua medido, num lançamento separado. O navegador só vê se a chave existe e os quatro últimos caracteres. Guardar a chave e decidir quem a troca é desta onda; usar a chave da redação na chamada ao provedor é mudança em arquivo da Plataforma (decisão 11).
- **Vizinho barulhento.** O teto de execuções simultâneas e o limite diário de tokens (`limites.conferir_dia`) são hoje da instalação: uma redação consegue esgotá-los para todas. Passam a existir por redação, com um total da instalação por cima, e a mensagem de recusa deixa de citar o número de perguntas da instalação. São mudanças em arquivos da Plataforma (seção 10).

## 9. Reavaliação de S2 e S6 (SEG-07)

As duas decisões foram tomadas em 19/11/2026, quando todo administrador via e podia tudo. Um conteúdo malicioso entre administradores não dava a ninguém um poder que já não tivesse. Com papéis, isso muda dentro da redação: repórter e editor escrevem conteúdo que o dono abre, e o dono pode mais que eles. Entre redações nada muda, porque nenhum conteúdo de uma é exibido a outra enquanto o isolamento da seção 4 valer.

**S2, texto escondido por CSS nas capturas web. Recomendação: manter como está, só com aviso.**

- O risco de S2 é o conteúdo de um site externo levar texto que a pessoa não vê e o modelo lê. Ele não depende de confiança entre contas.
- A captura continua sendo ação de uma pessoa, com endereço dado por ela, e fica com o dono no lançamento (seção 2.4). Um repórter mal-intencionado já pode pôr texto escondido num PDF que ele mesmo envia; a captura não lhe dá poder novo.
- O efeito fica preso à apuração em que a captura entrou.
- A condição da decisão original continua: se as capturas passarem a alimentar o modelo sem leitura humana, S2 é revista. A varredura "contém texto que parece instrução para IA" da Onda 4 (item 13, camada d) reduz o risco restante.
- Reabrir S2 quando a captura for liberada a repórteres, depois do lançamento.

**S6, `innerHTML` do editor de notas. Recomendação: manter a exceção, com condições novas, conferidas antes do portão da Onda 2.**

A exceção deixa de se apoiar na confiança entre administradores e passa a depender só das três barreiras (limpeza do Lute, remoção de `<iframe>`, `<object>` e `<embed>`, CSP). Uma nota escrita por um repórter é aberta no navegador do dono; se as barreiras falharem, é escalada de privilégio dentro da redação. Condições:

1. **A limpeza roda em quem lê.** O servidor guarda o texto que recebe, e um cliente adulterado pode mandar qualquer coisa por `apuracao-nota-salvar`. Toda tela que exibe uma nota (edição, leitura, prévia e exportação em HTML) passa pela mesma limpeza. Teste com nota gravada direto pela rota, sem passar pelo editor.
2. **Bateria ampliada** em `testes/editor_notas_seguranca.cjs`, com o que a CSP não cobre: `<meta http-equiv="refresh">`, `<base>`, `<form>`, `<link>`, `<style>`, SVG com script, `javascript:` e `data:` em links, e elementos com `id` ou `name` iguais aos identificadores que a Mesa usa (403 seletores por id e 59 variáveis globais, UX-13), que permitiriam trocar o comportamento de um botão sem executar script.
3. **Links de nota** abrem com `rel="noopener noreferrer"` e mostram o destino. Uma nota não deve conseguir imitar um aviso da Mesa que leve a pessoa a digitar a senha fora dela.
4. **A CSP não afrouxa.** `script-src 'self'` sem `unsafe-inline` é a barreira que segura as outras duas. Qualquer mudança na CSP passa pelo Revisor.
5. **As operações sensíveis pedem a senha** (seção 5.15), parte que é deste contrato: mesmo que as três barreiras falhem, o conteúdo malicioso não troca senha, não cadastra chave, não promove ninguém a dono e não apaga de vez.
6. **O Revisor ataca com conta de repórter contra sessão de dono** no portão da onda.

As condições 1 a 4 são trabalho do Frontend e do QA; a 5 é deste contrato; a 6 é do Revisor. Se a condição 1 ou a 2 não fechar, a alternativa é o servidor passar a limpar o HTML ao gravar, o que exige uma biblioteca de limpeza e volta ao dono do projeto.

O mesmo cuidado vale para todo texto que uma conta escreve e outra lê: nome de pessoa, nome de redação, título de apuração, nome de arquivo, texto de diligência. Todos entram na tela como texto, nunca como HTML, e as telas W08 e W09 têm teste disso.

## 10. O que muda para os outros agentes

**Arquivos de Contas** (escreve só neles): `scripts/acesso.py`, `scripts/rotas_contas.py`, os demais `scripts/rotas_*.py` e `scripts/interface_pesquisa.py` (nesta onda, pela tabela "Quem escreve onde"), e os módulos novos `scripts/autorizacao.py`, `scripts/correio.py`, `scripts/segundo_fator.py` e `scripts/rotas_equipe.py`. Testes em arquivos novos (`test_matriz_contas.py`, `test_isolamento_redacoes.py`, `test_migracao_contas.py`, `test_convites.py`, `test_segundo_fator.py`, `test_sessoes_conta.py`, `test_ciclo_conta.py`, `test_correio.py`), mais `test_acesso.py` e `test_autorizacao.py`, que são de autorização.

**Pedidos, um por dono de arquivo. Nenhum é feito por Contas sem o aval do Maestro.**

| Para | Pedido |
|---|---|
| Plataforma | `custo.chaves_orcamento` devolve a redação da conta; tetos simultâneos e limite diário por redação; mensagem de recusa sem contagem da instalação; `segredos.ler_chave` com a redação, e a chamada ao provedor usando a chave da redação quando houver; listas fechadas de `registro_acesso.py` com os eventos, papéis e códigos novos e o campo `organizacao`; teto de disco por redação, com PROD-05 na Onda 4 (limitação registrada na seção 4.5). |
| Infra | Backup do banco pela cópia consistente; restauração chamando o encerramento de sessões; `manutencao` agendada; variáveis do SMTP; `cryptography` como dependência direta em `requirements.txt` e no arquivo de trava (já está nele, por via do OCR). |
| Frontend | Telas W08, W09 e W10; `data-papel` com os valores novos e `capacidades`; `piloto.js` deixa de chamar `contas-*`; páginas `/aceitar/` e `/redefinir/`; campo de senha nas operações da seção 5.15; desenho do código QR a partir do endereço `otpauth://` que o servidor entrega (sem CDN); traduções dos códigos novos; condições 1 a 3 de S6. |
| Design | Exceções por escrito ao W08 e ao W10, pelas decisões 4 e 5; estado "redação suspensa"; como o perfil legado `convidado` aparece na Equipe. Configuração da organização continua sem desenho. |
| QA | Os oito testes de outros donos que leem `acesso.json` direto (os outros dois, `test_acesso.py` e `test_autorizacao.py`, são de Contas); bateria de S6; a matriz na suíte rápida. |
| Documentação | Texto e versão dos termos; texto dos e-mails; roteiro do operador (criar redação, migrar, recuperar dono). |
| Produto e Core | Nada muda na forma dos registros. O nome do autor de conta excluída é trocado na saída, sem tocar nos módulos. |

**Os outros agentes podem, sem passar por Contas:** criar operações novas, desde que cada uma entre na matriz com resolvedor, tipo e células, no mesmo commit; ler `principal['conta']` e `principal['organizacao']` para autoria e cota.

**Não podem, sem passar por Contas:** decidir por papel dentro de um módulo de rota; aceitar apuração que não veio do portão; devolver listagem de mais de uma apuração sem `filtrar`; gravar no banco de contas; criar resposta de recusa que diferencie "não existe" de "não é seu"; pôr link, token ou senha em evento, log ou resposta.

**Como pedir mudança neste contrato:** ao agente de Contas, pelo Maestro. Mudança na matriz altera este arquivo e `autorizacao.MATRIZ` no mesmo commit e passa pelo Revisor e pela segunda leitura do Maestro.

## 11. Decisões do dono do projeto

O dono do projeto respondeu às 16 perguntas deste contrato em 22/11/2026 e adotou a recomendação em todas (registro P27 nas decisões do dono). Nenhuma pergunta segue aberta. A decisão 10 ainda depende da confirmação de quem responde pela LGPD (D6), que é Manual Follow-Up do dono do projeto.

| # | Pergunta | Decisão |
|---|---|---|
| 1 | Os convidados atuais continuam como perfil legado `convidado`, ou viram leitor na migração? | Decidido pelo dono em 22/11/2026 (P27): **legado.** Virar leitor daria a eles a leitura do caderno, dos achados e do texto das apurações liberadas sem ninguém ter decidido isso. Cada dono converte quem quiser pela Equipe. |
| 2 | Uma pessoa pode estar em duas redações com a mesma conta? | Decidido pelo dono em 22/11/2026 (P27): **não, no teste.** Uma conta, uma redação. |
| 3 | Segundo fator obrigatório para quem? O plano dizia dono; o W08 e o W10 dizem dono e editor. | Decidido pelo dono em 22/11/2026 (P27): **dono e editor**, como nos wireframes. |
| 4 | A chave de acesso (passkey) do W08 e do W10 entra no lançamento? | Decidido pelo dono em 22/11/2026 (P27): **não.** O Design registra a exceção ao W08 e ao W10. |
| 5 | A lista de sessões mostra "cidade aproximada" (W08, regra 5)? | Decidido pelo dono em 22/11/2026 (P27): **não no lançamento.** Mostra aparelho, data e endereço. O Design registra a exceção ao W08. |
| 6 | O operador do Vlado tem tela na Mesa? | Decidido pelo dono em 22/11/2026 (P27): **não.** Só terminal do servidor. |
| 7 | Quem marca afirmação do texto como revisada? | Decidido pelo dono em 22/11/2026 (P27): **editor e dono.** Quem apurou não revisa a própria matéria. |
| 8 | O leitor lê tudo da apuração em que foi incluído, inclusive diligências, entrevistas e o texto da matéria? | Decidido pelo dono em 22/11/2026 (P27): **sim.** Uma regra só; quem inclui decide. |
| 9 | Quem inclui pessoas numa apuração? | Decidido pelo dono em 22/11/2026 (P27): **o dono e o repórter responsável.** |
| 10 | Ao excluir uma conta, o nome some da tela e das exportações novas, mas continua nos registros antigos e nos backups, que não podem ser reescritos. Aceita? | Decidido pelo dono em 22/11/2026 (P27): **sim, com o texto da tela dizendo isso.** Continua dependendo da confirmação de quem responde pela LGPD (D6). |
| 11 | A chave de IA própria da redação entra inteira na Onda 2? | Decidido pelo dono em 22/11/2026 (P27): **sim**, com a parte da Plataforma. |
| 12 | Enquanto D7 não fecha, a homologação usa o transporte `tela`, com o link mostrado a quem convida e "esqueci a senha" desligado? | Decidido pelo dono em 22/11/2026 (P27): **sim, só na homologação.** A produção não sobe sem envio real. As limitações do transporte `tela` estão na seção 8.1. |
| 13 | A semente do segundo fator é cifrada com a biblioteca `cryptography`, que passa a ser dependência direta? | Decidido pelo dono em 22/11/2026 (P27): **sim.** |
| 14 | O único dono de uma redação perdeu senha, aparelho e códigos. O operador o recupera pelo terminal, com aviso por e-mail e espera de 24 horas? | Decidido pelo dono em 22/11/2026 (P27): **sim.** |
| 15 | Prazos: convite 7 dias; redefinição 1 hora; conta inativa avisada em 180 dias e desativada 30 dias depois; atividade da redação guardada por 90 dias. | Decidido pelo dono em 22/11/2026 (P27): **esses.** |
| 16 | S2 fica como está e S6 fica aceita com as seis condições da seção 9? | Decidido pelo dono em 22/11/2026 (P27): **sim.** |

Depende também de decisões já registradas: D6 (controlador dos dados), para os termos e a política; D7 (e-mail do domínio), para o transporte real.

**Aprovação (P28, 22/11/2026).** O dono do projeto aprovou este contrato na revisão 2 (`22bbc97`), com duas ressalvas para o código:

1. **Rebaixar ou desativar outro dono pede a senha de quem faz.** Vale para `equipe-papel`, quando o alvo é dono e o papel novo não é, e para `equipe-desativar`, quando o alvo é dono. As duas se somam à lista da seção 5.15 e entram com o código das operações `equipe-*`.
2. **O contador de tentativas por identificador sem conta tem teto global.** A seção 8.2 diz que esse contador nunca é despejado antes do prazo e que só o teto por endereço limita a tabela; com a ressalva, o total de contadores de identificadores sem conta passa a ter um teto da instalação. O número e o que acontece ao atingi-lo são fixados na entrega da entrada em dois passos, com teste, e passam pelo Revisor.

Nenhuma das duas muda uma célula da matriz.

## 12. Verificação

**Entrega 1, em código:** o portão (`scripts/autorizacao.py`, com a matriz como dado), redações, papéis, posse e participação em `acesso/contas.sqlite`, a migração do `acesso.json`, as operações `caso-*` e os ganchos no servidor e nas rotas. Rodam hoje:

- `python -m unittest discover -s testes -p test_matriz_contas.py -v`: cada célula da matriz e a igualdade entre este arquivo e `autorizacao.MATRIZ`.
- `python -m unittest discover -s testes -p test_isolamento_redacoes.py -v`: travessia entre redações.
- `python -m unittest discover -s testes -p test_migracao_contas.py -v`: não ampliação, autoria, reversão e repetição.
- `testes/test_acesso.py` e `testes/test_autorizacao.py`, atualizados para o modelo novo.

**O que a entrega 1 ainda não tem,** e onde o código difere do texto até lá:

- As operações de `autorizacao.PENDENTES` (`conta-*`, `equipe-*`, convite, redefinição de senha e segundo fator) respondem 404. As seis `contas-*` continuam, só para o dono e só sobre a própria redação (`autorizacao.TRANSITORIAS`), e saem quando a tela Equipe entrar (seção 5.5).
- `data-papel` leva `admin` para o dono enquanto a interface não conhece os papéis novos; os outros papéis vão com o próprio nome. `GET /api/sessao` já devolve os valores novos e `capacidades`.
- `pendencias` sai sempre vazia: segundo fator e termos entram com a seção 8.
- Tentativas de entrada: vale o bloqueio por identificador e endereço de hoje. O teto por identificador, o modo protegido e o aparelho conhecido (seção 8.2) entram com a entrada em dois passos.
- Chave de IA: numa instalação `piloto` com mais de uma redação, `ia-config-salvar` é recusada a todos e `ia-config` não mostra os quatro últimos caracteres da chave do serviço, até a chave própria de cada redação existir (seção 8.5).
- O registro de auditoria descarta os códigos, motivos, papéis e eventos novos até as listas fechadas de `registro_acesso.py` os receberem (pedido à Plataforma, seção 10); até lá, `acesso_negado` com motivo não chega ao registro.
- Backup: `acesso.copia_consistente` e `acesso.encerrar_todas_as_sessoes` existem, e o `backup.py` ainda não as usa (pedido à Infra, seção 10). Enquanto não usar, uma restauração traz de volta as sessões que estavam no banco copiado.

Chegam com as próximas entregas: `-p test_convites.py`, `-p test_segundo_fator.py`, `-p test_sessoes_conta.py`, `-p test_ciclo_conta.py`, `-p test_correio.py` (seção 8).

Portão da Onda 2: a matriz inteira coberta por teste; o Revisor tenta atravessar de uma redação para outra e não consegue; segunda leitura da matriz pelo Maestro.

**Manual Follow-Up** (exige pessoa; nenhum agente marca como feito): aprovação deste contrato pelo dono do projeto; confirmação, por quem responde pela LGPD (D6), da decisão 10; contratação do envio de e-mail (D7); ensaio da migração numa cópia dos dados reais, pelo operador; conferência do segundo fator no aplicativo Android, que está congelado (D8).

Status: aprovado pelo dono do projeto em 22/11/2026 (P28), com as duas ressalvas da seção 11; entrega 1 em código (seção 12). Revisão 2, de 22/11/2026, sobre `1972f1b`: decisões do dono do projeto registradas (P27); correção do achado B1 do Revisor e da família dele (seções 4.5, 5.4, 8.1 e 8.2); ressalvas do Revisor (seções 4.2, 4.3, 4.5, 5.5, 5.15 e 10); ressalvas M1 a M3 da segunda leitura do Maestro (M1 na seção 5.6; M2 nas seções 2.1, 2.4, 5.1 e 5.8; M3 nas seções 2.5, 4.2 e 4.6).
