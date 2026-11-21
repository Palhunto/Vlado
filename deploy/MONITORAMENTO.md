# Monitoramento e alertas

Quando a Mesa cai, alguém precisa saber **sem depender de um usuário reclamar**. Há duas camadas, porque cada uma vê
o que a outra não vê. Passo a passo para o dono e para quem opera; o que é ato de pessoa está marcado **[Dono]**.

## Duas camadas e por que as duas

| Camada | O que é | Pega | Não pega |
|---|---|---|---|
| **A. Batimento de dentro** (serviço `backup`, variável `VLADO_VIGIA_PING_URL`) | A cada minuto confere o `/saude` do app e o disco livre e avisa um endereço do **healthchecks.io**. Se algo falha, avisa `<endereço>/fail` na hora. Se o servidor ou o contêiner parar, **os avisos deixam de chegar** e o serviço alerta pelo silêncio. | App fora do ar, disco quase cheio, servidor desligado, contêiner de backup parado, rede do servidor caída | DNS errado, certificado vencido, porta 443 fechada: de dentro tudo parece bem |
| **B. Verificação de fora** (UptimeRobot ou equivalente) | A cada 5 min acessa `https://<domínio>/saude` pela internet e exige a palavra-chave `"ok": true`. | O que o usuário enfrenta: DNS, certificado, Caddy, firewall, provedor | Disco cheio e backup parado (isso a camada A e o aviso do backup pegam) |

Além disso, o **backup** tem o próprio aviso (`VLADO_BACKUP_PING_URL`): um batimento por dia, e `/fail` quando falha.

### Por que estes serviços

- **healthchecks.io** (para A e para o backup): modelo de "interruptor do homem morto". Quem avisa é o servidor; o
  alerta nasce do **silêncio**, então funciona mesmo com o servidor inteiro fora do ar. Código aberto, plano gratuito
  com vários checks, alertas por e-mail, Telegram, Slack e webhook. O endereço recebe só uma visita vazia ou uma frase
  de estado ("Mesa sem resposta", "Pouco disco livre: 2,0 GB"): nada de conta, caso, documento ou senha.
- **UptimeRobot** (para B): verificação de fora, a cada 5 min no plano gratuito, com palavra-chave e alertas por
  e-mail e mensageiros. Equivalentes: Better Stack, Uptime Kuma. **Uptime Kuma só vale hospedado em outra máquina**: no
  mesmo servidor ele cai junto com a Mesa. Confira os limites vigentes do plano gratuito no site de cada serviço
  (mudam); nenhum plano pago é necessário.
- O alvo `/saude` é público e só responde `{"ok": true}`: não expõe dado nenhum.

## Passo a passo

### 1. [Dono] Criar os checks no healthchecks.io (um conjunto por ambiente)

1. Crie a conta em https://healthchecks.io e um projeto "Vlado".
2. Crie o check **`vlado-<ambiente>-vigia`**: período **1 minuto**, tolerância (grace) **5 minutos**. Copie o endereço
   de batimento (`https://hc-ping.com/<uuid>`).
3. Crie o check **`vlado-<ambiente>-backup`**: período **1 dia**, tolerância **6 horas** (o backup roda às 06:30 UTC).
   Copie o endereço.
4. Em **Integrations**, ligue ao menos **dois canais** (e-mail do dono e Telegram ou Slack de quem opera) e associe aos
   dois checks. Um alerta que só chega a uma caixa de e-mail ignorada não é alerta.

### 2. [Dono digita, operador conduz] Colocar os endereços no ambiente

No `deploy/ambientes/<ambiente>.env` (fora do git; os endereços são segredos leves: quem os conhece pode simular
batimento):

```
VLADO_VIGIA_PING_URL=https://hc-ping.com/<uuid-do-vigia>
VLADO_BACKUP_PING_URL=https://hc-ping.com/<uuid-do-backup>
# VLADO_VIGIA_DISCO_MIN_GB=5        # abaixo disso a vigia avisa falha (padrão 5 GB)
```

Aplicar: `docker compose -p vlado-<ambiente> --env-file deploy/ambientes/<ambiente>.env up -d`. No painel, o check
`vigia` fica verde em um minuto.

### 3. [Dono] Criar o monitor de fora (UptimeRobot)

1. Crie a conta e um monitor do tipo **Keyword**: URL `https://<domínio>/saude`, palavra-chave `"ok": true`, alertar
   quando a palavra **não existe**, intervalo 5 min.
2. Associe os mesmos canais de alerta (e-mail e mensageiro). Se o serviço oferecer aviso de vencimento de certificado,
   ligue (14 e 7 dias antes).
3. Um monitor por ambiente que estiver no ar (editorial, demonstração, homologação com domínio real).

### 4. Fazer o teste do alerta (antes de depender dele, e a cada trimestre)

O alerta só vale se já o vimos disparar. Em **horário combinado**, avisando a equipe:

| Teste | Como | Esperado |
|---|---|---|
| Mesa cai | `docker compose -p vlado-<ambiente> --env-file deploy/ambientes/<ambiente>.env stop vlado` | em até 1 min o check `vigia` fica **vermelho** (falha enviada) e chega o alerta; em até ~10 min o UptimeRobot também alerta |
| Servidor mudo | `stop backup` (para o batimento) e aguarde | em até 6 min o `vigia` alerta pelo **silêncio** (tolerância de 5 min) |
| Backup falha | `exec -T backup python scripts/backup.py rodada` com o destino temporariamente errado em um ambiente de teste | o check `backup` recebe `/fail` e alerta |
| Volta ao normal | `start vlado` e `start backup` (ou `up -d`) | os checks voltam a verde e chega o aviso de recuperação |

Anote data, quem recebeu e em quanto tempo no registro de verificação do ambiente.

## O que cada alerta significa e o que fazer

| Alerta | Significado | Roteiro |
|---|---|---|
| `vigia` vermelho "Mesa sem resposta em /saude" | o app não responde ao serviço de backup, dentro do servidor | `deploy/INCIDENTE.md` > Mesa fora do ar |
| `vigia` vermelho "Pouco disco livre" | o disco do servidor passou do limite | INCIDENTE.md > Disco cheio |
| `vigia` sem batimento (silêncio) | servidor desligado, rede ou Docker parados | INCIDENTE.md > Mesa fora do ar (comece pelo painel do provedor) |
| UptimeRobot alerta e a `vigia` está verde | o problema é de fora: DNS, certificado, firewall, provedor | INCIDENTE.md > Certificado vencido |
| `backup` vermelho ou em atraso | backup falhou ou não rodou | INCIDENTE.md > Backup falhando |

## Registro de acesso (para investigar, não para monitorar)

O Caddy grava uma linha JSON por requisição em `/var/log/caddy/acesso.log` (volume `caddy_logs`): horário, IP, método,
host, caminho com o token mascarado, status, duração e tamanho. **Não grava** corpo, query string, cookies,
Authorization, nem nenhum outro cabeçalho. Rotação: 20 MiB por arquivo, 20 arquivos, no máximo 30 dias. Esse registro
tem **IP de pessoas**: trate como dado pessoal (acesso restrito, 30 dias) e informe a retenção na política de
privacidade do dono. Para ler: `docker compose -p vlado-<ambiente> --env-file ... exec caddy tail -n 100 /var/log/caddy/acesso.log`.

## Pendências que dependem de pessoa

| | Quem |
|---|---|
| Criar conta e os dois checks no healthchecks.io, com dois canais de alerta | Dono |
| Criar o monitor de fora (UptimeRobot ou equivalente) e ligar os alertas | Dono |
| Colocar `VLADO_VIGIA_PING_URL` e `VLADO_BACKUP_PING_URL` no servidor | Dono digita, operador conduz |
| Fazer e registrar o teste do alerta (tabela acima) | Operador, com o dono |
| Decidir quem atende o alerta fora do horário comercial | Dono |
