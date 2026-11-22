# Backup, restauração e retenção (SEG-03)

Passo a passo para o dono e para quem opera o servidor. O que é decisão ou ato de pessoa está marcado como
**[Dono]**: a equipe de agentes não contrata, não digita chaves e não mexe em DNS.

## Como funciona

- O serviço `backup` do Compose roda todo dia no horário configurado (padrão **06:30 UTC**, 03:30 em Brasília).
- Ele lê os volumes de dados **somente leitura** (não consegue corrompê-los nem deixar trava presa), junta tudo num
  arquivo, **cifra com a chave pública** do dono (`age`), envia ao destino fora do servidor (`rclone`), confere o
  tamanho no destino, apaga as cópias vencidas pela retenção e apaga o arquivo local.
- **O servidor só consegue escrever backups, nunca lê-los.** A chave que decifra (privada) fica com o dono, fora do
  servidor, da imagem, do git e dos logs. Quem invadir o servidor não consegue abrir os backups já enviados.
- **Cadastro em curso.** A trava de cadastro da Mesa é o arquivo `casos/.cadastro.trava` (preso com `flock`; nunca é
  apagado). O backup **sonda** a trava sem segurá-la (trava compartilhada, não bloqueante, solta na hora): se estiver
  presa, espera até 15 min; nunca a mantém durante a cópia, para não recusar cadastros de usuários. Como um cadastro
  curto pode começar e terminar dentro dos minutos da cópia, o backup compara o estado (inode, mtime e ctime) do
  arquivo antes e depois: mudou, descarta a cópia e recomeça. Vale para cadastro, preparação de PDFs, congelamento de
  rodada, publicação da captura web, gestão e apagamento. O `flock` funciona entre contêineres que montam o **mesmo
  volume nomeado**; não funciona com bind mount de pasta do Windows nem em SMB/NFS antigo (use volume nomeado).
  Pastas de preparo (`.lote_*`, `.r_*`, `.web_*`, `.preparacao_*`, `.indice_*`, `.publicacao_*`, `.novo_*`) nunca entram no
  backup; uma com menos de 2 h conta como trabalho em andamento, uma mais velha é resto de queda e só vira aviso
  no manifesto (`VLADO_BACKUP_MARCADOR_IDADE_MAX_S`). Cada arquivo é lido de forma estável (tamanho e data não mudam
  durante a leitura; JSON e SQLite são validados). Notas e caderno têm travas próprias e escrita atômica por
  arquivo: ficam cobertos pela leitura estável. Ao restaurar, cada arquivo é conferido pelo hash do manifesto antes
  de qualquer dado ser trocado.
- O estado fica em `/trabalho/estado.json` do volume `backup_trabalho`. O serviço aparece como **unhealthy** em
  `docker compose ps` se não estiver configurado ou se o último sucesso tiver mais de 30 h.

## O que entra e o que não entra (decisão declarada)

| Entra | Fica de fora | Por quê |
|---|---|---|
| casos (originais, derivados, cadastros) **e a fila de extração `casos/.fila/`**, rodadas e índices, conversas, lixeira, entrada, **contas (`acesso/`, com hashes de senha)**, ajustes | `segredos/` (chaves de API coladas na Mesa) | Uma chave de API se cola de novo (ou fica na variável de ambiente do servidor); um backup é mais fácil de vazar que um volume. O volume `segredos` nem é montado no serviço de backup. |
| | dados do Caddy (`caddy_data`: certificado e conta ACME) | O Caddy emite de novo sozinho. |
| | `configuracao.json` e o código | Fazem parte da imagem (`VLADO_VERSAO`). |
| | `casos/.apagando/`, `conversas/.apagando/`, `execucoes/.apagando/` e `lixeira/.apagando/` (quarentena do que foi mandado apagar e os manifestos dos apagamentos em curso) | Dado que a pessoa mandou apagar: nunca entra no backup. |
| | pastas de preparo (`.lote_*`, `.r_*`, `.novo_*`...), `casos/.cadastro.trava`, `casos/.fila/.coordenador` e os `*.lock` | Trabalho em andamento e arquivos de trava, não dados: a Mesa recria a trava no primeiro uso. |

### Quarentena do apagamento (`.apagando/`): FORA do backup

A quarentena é a do apagamento da Plataforma (`scripts/apagamento.py`, `QUARENTENA`). Quando a pessoa manda apagar um caso, uma
conversa ou uma rodada, a Mesa move o dado para `<volume>/.apagando/<id>/`, na raiz de `casos/`, `conversas/` e `execucoes/`, e o
remove em segundo plano; o manifesto de cada apagamento em curso (id, tipo, caso, fase, caminhos relativos, sem título) fica em
`lixeira/.apagando/<item>.json`. Enquanto isso o dado está em quarentena. **O backup exclui as quatro pastas `.apagando`**: é dado que a pessoa mandou apagar, e levá-lo para um backup retido por meses desfaria o apagamento. Diferente
dos marcadores de operação (`.lote_*`, `.indice_*`...), a quarentena **não faz o backup esperar nem recusar**: a remoção pode demorar
e nada ali volta a ser dado. A exclusão vale só na raiz dessas quatro pastas (o prefixo `.apagando`); uma pasta de mesmo nome mais
fundo, dentro de um caso, é dado do caso. **Por que também o manifesto em `lixeira/`:** ele descreve dado que a pessoa mandou apagar e
não serve sem os arquivos (que não estão no backup); restaurado sozinho, só faria a Mesa concluir um apagamento sem nada a remover. O
resto de `lixeira/` (o índice dos itens que a pessoa ainda pode restaurar) continua no backup. Uma restauração não traz a quarentena de
volta. O que já estava em backups anteriores à
ordem de apagar continua neles até a retenção vencer (como já diz o aviso da tela de apagamento).

### Registro de auditoria (`registro/`, SEG-02): FORA do backup, de propósito

A Mesa grava os eventos de autenticação, administração e downloads no volume `registro` (ver `MONITORAMENTO.md`). **Decisão: não
entra no backup.** Motivos: (1) tem **IP de pessoas**, retido por 30 dias; o backup guarda até 6 meses (retenção
`diarios=7,semanais=4,mensais=6`), então incluí-lo quebraria a promessa de retenção; (2) o registro serve para investigar o que
aconteceu, não para restaurar o estado; (3) uma restauração troca a pasta de dados e, se o registro morasse junto, **apagaria o
histórico justamente quando ele é mais necessário**. Por isso ele fica num volume à parte, que o serviço `backup` nem monta, e
a restauração não o toca. A chave das referências do registro fica em `segredos/registro_ref.chave`, fora desse volume e fora do
backup comum (só entra se alguém ligar `VLADO_BACKUP_INCLUIR_SEGREDOS=1`, a decisão consciente de sempre). Para um incidente,
copie o volume `registro` como evidência (`INCIDENTE.md` 5.2).

### Fila de extração (`casos/.fila/`, CONF-02): entra no backup

A Mesa grava os envios em `casos/.fila/<lote>/` (pedido, estado, originais recebidos, cópias de trabalho) e só depois de lidos
e publicados eles passam para `casos/<caso>/`. **Decisão: a fila entra no backup**, no estado em que estiver. Motivo: um envio
ainda não publicado só existe ali (o OCR de um PDF grande leva horas); sem a fila, uma restauração faria o envio sumir sem aviso.
Restaurar um lote pendente faz a Mesa processá-lo de novo, sem dano (publicar de novo é idempotente). Detalhes:

- **Fora:** `casos/.fila/.coordenador` (trava de processo, a Mesa recria ao partir) e `casos/.fila/.novo_<id>` (lote sendo
  montado, renomeado quando completo): este é marcador de operação em andamento, então o backup espera até 15 min por ele e
  nunca o copia; um `.novo_*` com mais de 2 h é resto de queda e só vira aviso.
- **Ordem:** a fila é copiada **antes** das pastas dos casos (ordem alfabética: o ponto vem primeiro). Se um lote for publicado
  durante a cópia, ele aparece nos dois lugares (inofensivo, a publicação é idempotente) e nunca em nenhum. Um teste confere
  essa ordem; se a fila mudar de nome ou de lugar, avise a Infra.
- **Depois de publicado**, `pedido.json`, `estado.json` e `resposta.json` ficam 24 h na fila e vão junto: são pequenos.
- **Custo:** originais e cópias de trabalho de lotes pendentes entram no arquivo do backup; com muitos envios grandes
  ao mesmo tempo, o backup daquela hora fica maior (e um arquivo que muda durante a leitura vira aviso no manifesto, não falha).

Quem quiser incluir as chaves de API precisa montar `segredos` no serviço e definir `VLADO_BACKUP_INCLUIR_SEGREDOS=1`
(decisão consciente; o manifesto registra `segredos_incluidos`).

## Retenção

Padrão `diarios=7,semanais=4,mensais=6`: guarda **todos** os backups dos últimos 7 dias, mais o mais novo de cada uma
das últimas 4 semanas e de cada um dos últimos 6 meses. O mais novo nunca é apagado; só nomes deste ambiente
(`vlado-<ambiente>-...tar.gz.age`) entram na conta. Mude com `VLADO_BACKUP_RETENCAO` no `.env` do ambiente.

## Passo a passo: primeira configuração

### 1. [Dono] Gerar e guardar o par de chaves (uma vez, no seu computador, não no servidor)

```bash
age-keygen -o chave-vlado.txt          # imprime a chave PÚBLICA (age1...) e grava as duas no arquivo
```

- A linha `# public key: age1...` é a **chave pública**: ela vai para `VLADO_BACKUP_DESTINATARIOS`.
- A linha `AGE-SECRET-KEY-1...` é a **chave privada**. Sem ela **nenhum backup abre, para sempre**. Guarde pelo menos
  **duas cópias em lugares diferentes** (gerenciador de senhas e uma cópia impressa ou em pen drive num cofre).
  Nunca no servidor, no git, em e-mail, em chat ou junto do destino dos backups.
- Pode cifrar para **mais de uma chave** (por exemplo, a sua e a de uma pessoa de confiança): separe as chaves
  públicas por vírgula. Qualquer uma das privadas abre o backup.
- Instalar o `age`: https://github.com/FiloSottile/age (Windows, macOS, Linux; ou `apt install age`).

### 2. [Dono] Escolher o destino fora do servidor (decisão D7) e criar as credenciais

Qualquer serviço compatível com S3 (Backblaze B2, Wasabi, Cloudflare R2, MinIO próprio...) ou um servidor SFTP.
Recomendações para o destino:

- bucket **privado**, em **outro fornecedor ou outra conta** que o servidor do Vlado;
- credenciais **só deste bucket**; se o fornecedor permitir, ligue **versionamento / bloqueio de objeto (object
  lock)** com a retenção que o dono decidir, para que um servidor invadido não consiga apagar os backups. Sem isso, a
  credencial precisa poder apagar (a retenção apaga cópias vencidas) e um invasor também poderia;
- anote o endereço do serviço (endpoint), a região, o nome do bucket e o par de chaves de acesso.

### 3. Preencher o ambiente (quem opera, com o dono presente: **o dono digita as chaves**)

No `deploy/ambientes/<ambiente>.env` (fora do git):

```
VLADO_BACKUP_DESTINO=fora:NOME-DO-BUCKET/vlado-<ambiente>
VLADO_BACKUP_DESTINATARIOS=age1...        # a chave PÚBLICA do passo 1
```

E as credenciais do destino em `deploy/ambientes/<ambiente>-backup.env` (também fora do git; `chmod 600`):

```
# S3 compatível
RCLONE_CONFIG_FORA_TYPE=s3
RCLONE_CONFIG_FORA_PROVIDER=Other
RCLONE_CONFIG_FORA_ENDPOINT=https://s3.exemplo.com
RCLONE_CONFIG_FORA_REGION=us-east-1
RCLONE_CONFIG_FORA_ACCESS_KEY_ID=...
RCLONE_CONFIG_FORA_SECRET_ACCESS_KEY=...
```

```
# ou SFTP (rsync/ssh equivalente)
RCLONE_CONFIG_FORA_TYPE=sftp
RCLONE_CONFIG_FORA_HOST=backup.exemplo.com
RCLONE_CONFIG_FORA_USER=vlado
RCLONE_CONFIG_FORA_KEY_PEM=-----BEGIN OPENSSH PRIVATE KEY-----\n...\n-----END OPENSSH PRIVATE KEY-----
```

(No SFTP, o rclone sem `known_hosts` aceita qualquer chave de servidor: o conteúdo continua cifrado, mas um
interceptador poderia impedir os envios. Prefira S3.) O nome `FORA` é o do remoto e deve casar com o prefixo de
`VLADO_BACKUP_DESTINO`. Para um destino em pasta local de teste, use um caminho absoluto no lugar de `fora:...`.

### 4. Subir e conferir

```bash
docker compose -p vlado-<ambiente> --env-file deploy/ambientes/<ambiente>.env up -d --build
docker compose -p vlado-<ambiente> --env-file deploy/ambientes/<ambiente>.env ps          # backup deve estar "healthy"
docker compose -p vlado-<ambiente> --env-file deploy/ambientes/<ambiente>.env exec -T backup python scripts/backup.py rodada
docker compose -p vlado-<ambiente> --env-file deploy/ambientes/<ambiente>.env exec -T backup python scripts/backup.py listar
```

Para testar na hora (sem esperar o horário), `VLADO_BACKUP_AO_INICIAR=1` no `.env` faz uma rodada ao subir.
Opcional: `VLADO_BACKUP_PING_URL` com o endereço de um serviço de "batimento" (healthchecks.io ou similar): recebe um
aviso a cada sucesso e `/fail` a cada falha, e o serviço pode alertar quando o aviso **deixar de chegar**.

## Onde a chave privada pode estar e onde nunca

| Pode | Nunca |
|---|---|
| No cofre do dono: gerenciador de senhas e cópia impressa ou em pen drive guardados | No **disco do servidor** de produção ou de homologação (arquivo, `.env`, histórico do shell, pasta de trabalho) |
| Na **memória** da sessão de quem restaura, durante o comando (variável de ambiente digitada ou colada, depois descartada) | No mesmo lugar que as credenciais do destino dos backups: quem pega as duas abre todos os backups |
| Num pen drive montado só durante a restauração e retirado em seguida | No repositório, em e-mail, em chat, em captura de tela, em volume Docker, na imagem ou em log |

O servidor de produção **só tem a chave pública**. A chave privada entra numa máquina apenas no momento de restaurar, e
a regra é: **não deixar rastro em disco**.

### Como informar a chave sem gravá-la

Em vez de `cat arquivo` (que exige a chave em um arquivo na máquina), cole-a no terminal sem eco e sem histórico:

```bash
IFS= read -rs -d '' VLADO_BACKUP_CHAVE_PRIVADA      # cole a chave, Enter, e Ctrl+D; nada aparece na tela
export VLADO_BACKUP_CHAVE_PRIVADA
# ... comandos de verificar e restaurar abaixo ...
unset VLADO_BACKUP_CHAVE_PRIVADA                    # ao terminar; feche o terminal
```

Se a chave estiver num pen drive, monte-o, leia dele (`VLADO_BACKUP_CHAVE_PRIVADA="$(cat /mnt/pendrive/chave-vlado.txt)"`),
desmonte e retire. Durante o comando a chave existe no ambiente do contêiner de restauração (visível a quem tem acesso
ao Docker daquela máquina, e só enquanto ele roda; o `--rm` o apaga). Por isso: restaure numa máquina em que só quem
restaura tem acesso.

## Ensaio de restauração (faça antes de depender do backup e repita a cada trimestre)

**Faça o ensaio em OUTRA máquina** (o computador do dono ou um servidor temporário com Docker), **não no servidor que
produz os backups**. Motivos: prova que o backup restaura sem depender do servidor original, e a chave privada nunca
chega ao disco que guarda as credenciais do destino. Nessa máquina:

- clone este repositório na mesma versão e crie um `deploy/ambientes/<ambiente>.env` **mínimo**, só com
  `VLADO_AMBIENTE`, `VLADO_DOMINIO` (pode ser `localhost`), `VLADO_VERSAO` e `VLADO_BACKUP_DESTINO`;
- as credenciais do destino ficam em `deploy/ambientes/<ambiente>-backup.env`. **Use uma credencial só de leitura** (crie
  outra no fornecedor, sem permissão de gravar ou apagar), assim a máquina de ensaio não consegue alterar os backups;
- use um projeto separado e vazio (`-p vlado-restauracao`), **nunca** os volumes do ambiente em uso.

```bash
# informe a chave como mostrado acima (read -rs), depois:

# 1) conferir sem restaurar: decifra, confere todos os hashes, não escreve dado nenhum
docker compose -p vlado-restauracao --env-file deploy/ambientes/<ambiente>.env --profile restauracao run --rm -T restauracao \
  python scripts/backup.py verificar --do-destino ultimo --identidade-env VLADO_BACKUP_CHAVE_PRIVADA

# 2) restaurar o último backup em volumes novos
docker compose -p vlado-restauracao --env-file deploy/ambientes/<ambiente>.env --profile restauracao run --rm -T restauracao

# 3) subir a Mesa sobre os dados restaurados e conferir
docker compose -p vlado-restauracao --env-file deploy/ambientes/<ambiente>.env up -d vlado caddy

unset VLADO_BACKUP_CHAVE_PRIVADA
```

Conferir: `/saude` responde; as contas entram (todos precisam fazer login de novo: a restauração apaga as sessões); os
casos e as rodadas abrem; documentos têm o mesmo hash. Ao terminar, `down -v` do projeto de ensaio (é um projeto de
teste: nele pode) e apague a pasta clonada se a máquina não for sua.
Para restaurar um backup específico: `--do-destino NOME-DO-ARQUIVO` (veja os nomes com `listar`).

**A restauração recusa rodar com a Mesa no ar.** Ela troca o conteúdo das pastas de dados; se o app estivesse gravando,
poderia misturar dois estados. O comando procura o app em `VLADO_VIGIA_URL` (padrão `http://vlado:8765/saude`); se ele
responder, a restauração para com uma mensagem. Pare antes: `stop vlado backup`. Só use `--mesmo-com-a-mesa-no-ar` se
tiver certeza de que ninguém está usando e o endereço aponta para outro lugar.

## Em desastre (servidor perdido)

1. Servidor novo com Docker e este repositório na versão (`VLADO_VERSAO`) em uso; `.env` do ambiente e credenciais do
   destino de volta (guarde uma cópia **fora** do servidor, no cofre do dono, **separada da chave privada**).
2. **[Dono]** a chave privada (passo 1) é colada **no terminal** de quem restaura, com `read -rs` (acima), ou lida de
   um pen drive que é retirado em seguida. **Não a grave no disco do servidor novo**: ele passará a guardar as
   credenciais do destino. Se o servidor novo é a única máquina disponível, restaure, `unset` a variável, e só então
   configure o `backup` agendado (que só tem a chave pública).
3. `restauracao` como no ensaio, mas com o `-p` do ambiente real, e depois `up -d`. Se o serviço estiver rodando,
   `stop vlado backup` antes (a restauração se recusa a rodar com o app no ar).
4. Reaponte o DNS (**[Dono]**) quando a Mesa responder no servidor novo.

Perda máxima esperada: o que foi gravado desde o último backup (até 24 h). Para reduzir, rode `rodada` à mão antes de
uma atualização e depois de um cadastro grande.

## Limitações conhecidas (declaradas, sem mudança de código)

São riscos pequenos, medidos ou raciocinados na revisão da fase 2, que ficam como estão por ora. Cada um diz o que
observar.

| | Limitação | O que acontece e o que fazer |
|---|---|---|
| J3 | **Acervo grande com gente trabalhando pode impedir o backup de fechar.** Toda operação que termina durante a cópia (cadastro, congelamento de rodada...) faz o backup recomeçar: três tentativas e nova rodada 60 min depois. Uma cópia de 300 MB levou cerca de 70 s numa máquina carregada. | Com vários gigabytes e uso no horário do backup, ele pode não fechar. O aviso é o serviço `backup` ficar `unhealthy` depois de 30 h sem sucesso. Se acontecer: mude `VLADO_BACKUP_HORARIO_UTC` para a madrugada (o padrão, 06:30 UTC, já é 03:30 em Brasília) ou faça `rodada` à mão quando ninguém estiver cadastrando. |
| J5 | **A assinatura da trava de cadastro é o `stat` do arquivo** (inode, mtime, ctime). Uma operação que comece e termine dentro do mesmo "tique" do relógio do sistema de arquivos em que a anterior soltou a trava não muda o mtime. | Janela de milissegundos, que não se conseguiu provocar. Se um dia um backup restaurado parecer sem um cadastro feito no instante do backup, repita o backup: o seguinte o inclui. |
| J6 | **No Windows (só desenvolvimento) a sonda lê o texto do registro da trava**: depois de uma queda ele fica "ocupada", e o `criar` manual recusa até a próxima operação que use a trava. | Não afeta o servidor (Linux, `flock`). No Windows de desenvolvimento, a recusa passa na próxima operação que use a trava (um cadastro qualquer). |
| J8 | **O volume `tmp_vlado` não tem teto de tamanho** (escolha da I1: temporário de OCR em disco, não em memória, para PDF grande não derrubar o OCR). Um OCR descontrolado pode encher o disco dos dados. | Deixe espaço livre (o exemplo de ambiente pede), e acompanhe o disco: a vigia avisa quando passa do limite (`VLADO_VIGIA_DISCO_MIN_GB`, ver `MONITORAMENTO.md`). O volume é esvaziado a cada partida do app. |
| J2 | A credencial do destino precisa poder apagar (a retenção apaga cópias vencidas); um servidor invadido, então, apaga os backups. | Use versionamento ou bloqueio de objeto no bucket (passo 2 acima). Item do dono (P17). |

## Restauração pela entrada padrão (`restaurar -`)

`python scripts/backup.py restaurar - < dados.tar.gz` lê um `.tar.gz` **em claro** da entrada padrão. O fluxo é gravado em um
arquivo privado (0600) na pasta de trabalho, em blocos de 1 MiB (a memória não cresce com o tamanho), conferido e
apagado ao terminar, com ou sem erro. **Teto: 10 GB**; acima disso a restauração recusa, com mensagem, sem tocar nos
dados. Mude com `VLADO_BACKUP_STDIN_MAX_GB`. Para backups cifrados ou maiores, informe o arquivo ou `--do-destino`.
Se a decifragem ou a leitura falhar (chave errada, arquivo truncado), as pastas temporárias de `/trabalho/tmp` são
removidas na hora.

## Versões do `age` e do `rclone` na imagem de backup

A imagem `backup` instala `age 1.1.1` e `rclone 1.60.1` por versão fixada (`age=1.1.1-1*`, `rclone=1.60.1+dfsg-2*`),
e o build confere o que foi instalado. A fixação deixa passar as correções de segurança do Debian na mesma versão e o
sufixo de recompilação. Se o Debian oferecer outra versão, o build **falha de propósito**: nada muda sozinho. Para
atualizar, troque as duas versões no `Dockerfile` (estágio `backup`) e em `testes/test_dockerfile_endurecido.py`,
reconstrua e refaça o ensaio de restauração.

## Pendências que dependem de pessoa

| | Quem |
|---|---|
| Gerar o par de chaves `age` e guardar a privada em dois lugares | Dono |
| Escolher o destino fora do servidor e criar bucket e credenciais (D7) | Dono |
| Preencher `VLADO_BACKUP_DESTINO`, `VLADO_BACKUP_DESTINATARIOS` e o arquivo de credenciais no servidor | Dono (digita), operador (conduz) |
| Primeiro ensaio de restauração no servidor real e registro do resultado | Operador, com o dono |
| Alerta quando o backup falhar (endereço de batimento ou e-mail do alerta da Onda 1) | Dono escolhe o canal |
