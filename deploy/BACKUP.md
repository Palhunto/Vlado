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
- Se uma operação de vários arquivos estiver em andamento (cadastro, congelamento, salvamento do caderno, índice),
  o backup espera ela terminar (até 15 min) e recomeça do zero se uma aparecer durante a cópia. Cada arquivo é
  lido de forma estável (tamanho e data não mudam durante a leitura; JSON e SQLite são validados). Ao restaurar,
  cada arquivo é conferido pelo hash gravado no manifesto antes de qualquer dado ser trocado.
- O estado fica em `/trabalho/estado.json` do volume `backup_trabalho`. O serviço aparece como **unhealthy** em
  `docker compose ps` se não estiver configurado ou se o último sucesso tiver mais de 30 h.

## O que entra e o que não entra (decisão declarada)

| Entra | Fica de fora | Por quê |
|---|---|---|
| casos (originais, derivados, cadastros), rodadas e índices, conversas, lixeira, entrada, **contas (`acesso/`, com hashes de senha)**, ajustes | `segredos/` (chaves de API coladas na Mesa) | Uma chave de API se cola de novo (ou fica na variável de ambiente do servidor); um backup é mais fácil de vazar que um volume. O volume `segredos` nem é montado no serviço de backup. |
| | dados do Caddy (`caddy_data`: certificado e conta ACME) | O Caddy emite de novo sozinho. |
| | `configuracao.json` e o código | Fazem parte da imagem (`VLADO_VERSAO`). |
| | pastas de preparo (`.lote_*`, `.trava`, `.cadastro.lock`...) | Trabalho em andamento, publicado por renomeação. |

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

## Ensaio de restauração (faça antes de depender do backup e repita a cada trimestre)

Use um projeto separado e vazio, **nunca** os volumes do ambiente em uso. A chave privada vem do ambiente do comando
(`VLADO_BACKUP_CHAVE_PRIVADA`), não de arquivo no servidor.

```bash
# 1) conferir sem restaurar: decifra, confere todos os hashes, não escreve dado nenhum
VLADO_BACKUP_CHAVE_PRIVADA="$(cat /caminho/da/chave-vlado.txt)" \
docker compose -p vlado-restauracao --env-file deploy/ambientes/<ambiente>.env --profile restauracao run --rm -T restauracao \
  python scripts/backup.py verificar --do-destino ultimo --identidade-env VLADO_BACKUP_CHAVE_PRIVADA

# 2) restaurar o último backup em volumes novos
VLADO_BACKUP_CHAVE_PRIVADA="$(cat /caminho/da/chave-vlado.txt)" \
docker compose -p vlado-restauracao --env-file deploy/ambientes/<ambiente>.env --profile restauracao run --rm -T restauracao

# 3) subir a Mesa sobre os dados restaurados e conferir
docker compose -p vlado-restauracao --env-file deploy/ambientes/<ambiente>.env up -d vlado caddy
```

Conferir: `/saude` responde; as contas entram (todos precisam fazer login de novo: a restauração apaga as sessões); os
casos e as rodadas abrem; documentos têm o mesmo hash. Ao terminar, `down -v` do projeto de ensaio.
Para restaurar um backup específico: `--do-destino NOME-DO-ARQUIVO` (veja os nomes com `listar`).

## Em desastre (servidor perdido)

1. Servidor novo com Docker e este repositório na versão (`VLADO_VERSAO`) em uso; `.env` do ambiente e credenciais do
   destino de volta (guarde uma cópia **fora** do servidor, junto da senha do gerenciador do dono).
2. **[Dono]** a chave privada (passo 1), no computador de quem restaura.
3. `restauracao` como no ensaio, mas com o `-p` do ambiente real, e depois `up -d`. Se o serviço estiver rodando,
   `stop vlado backup` antes: ninguém deve gravar durante a restauração.
4. Reaponte o DNS (**[Dono]**) quando a Mesa responder no servidor novo.

Perda máxima esperada: o que foi gravado desde o último backup (até 24 h). Para reduzir, rode `rodada` à mão antes de
uma atualização e depois de um cadastro grande.

## Pendências que dependem de pessoa

| | Quem |
|---|---|
| Gerar o par de chaves `age` e guardar a privada em dois lugares | Dono |
| Escolher o destino fora do servidor e criar bucket e credenciais (D7) | Dono |
| Preencher `VLADO_BACKUP_DESTINO`, `VLADO_BACKUP_DESTINATARIOS` e o arquivo de credenciais no servidor | Dono (digita), operador (conduz) |
| Primeiro ensaio de restauração no servidor real e registro do resultado | Operador, com o dono |
| Alerta quando o backup falhar (endereço de batimento ou e-mail do alerta da Onda 1) | Dono escolhe o canal |
