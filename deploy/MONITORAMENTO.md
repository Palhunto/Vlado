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
Authorization, nem nenhum outro cabeçalho. O log padrão do contêiner (o que `docker logs caddy` mostra, inclusive os
erros 502 de quando a Mesa está fora do ar) leva o mesmo filtro: sem URI, sem cabeçalhos de requisição nem de resposta.
Rotação: 20 MiB por arquivo, 20 arquivos, no máximo 30 dias. Esse registro
tem **IP de pessoas**: trate como dado pessoal (acesso restrito, 30 dias) e informe a retenção na política de
privacidade do dono. Para ler: `docker compose -p vlado-<ambiente> --env-file ... exec caddy tail -n 100 /var/log/caddy/acesso.log`.

## Registro de auditoria da Mesa (SEG-02): quem entrou, quem administrou, quem baixou

Além do registro do Caddy (rede), a Mesa grava um registro próprio de **autenticação, administração e downloads**, uma linha
JSON por evento, no volume `registro` (`/app/registro`, arquivo `auditoria-AAAA-MM-DD.jsonl`, um por dia UTC). Cada linha leva
**horário UTC, evento, resultado, conta, IP, origem e operação**:

| Grupo | Eventos |
|---|---|
| Autenticação | `login_ok`, `login_falha` (motivo: `credenciais`, `bloqueado`, `limite_ip`), `login_bloqueado`, `logout`, `sessao_expirada` (motivo `expirada` ou `inatividade`, uma linha por sessão), `senha_definida`, `ativacao_falha` |
| Administração | `conta_criada`, `conta_desativada`, `conta_reativada`, `acesso_alterado` (campos mudados e o papel novo), `recuperacao_emitida`, `primeiro_admin`, `admin_recusada` (operação recusada), `operacao_negada` (convidado tentando o que não pode) |
| Downloads | `download` (tipo `original` ou `exportacao`, operação, tamanho em bytes, resultado `ok`, `falha` ou `interrompido`) |
| Do registro | `evento_arquivado` (um evento que saiu da janela de 1000 do `acesso.json`), `registro_cheio` (com a `classe` que estourou: `anonimo` ou `total`) |

**O que nunca entra, por construção:** só uma lista fechada de campos é aceita, cada um com formato estrito; senha, token,
link de ativação, cookie, chave, pergunta, conteúdo e nome de documento ou de arquivo, e o **nome do caso** não cabem e são
descartados. Duas referências com chave existem para correlacionar sem expor o texto: `login_ref` (login digitado de uma
conta que não existe: pode ser a senha digitada no campo errado) e `caso_ref` (o caso de um download), 12 caracteres de um
HMAC-SHA256 com uma chave aleatória guardada **fora do volume do registro**, em `segredos/registro_ref.chave` (o serviço de
backup não monta `segredos/` e o backup comum não o inclui): quem copiar só o registro não consegue conferir um palpite de senha
ou de caso. A mesma referência aparece sempre que o mesmo texto é usado, o que mostra uma varredura de senhas ou quem baixou do
mesmo caso, sem revelar nada. O `log_message` do servidor continua sem registrar consultas.

**Retenção e tamanho:** 30 dias (`VLADO_REGISTRO_RETENCAO_DIAS`, o mesmo do Caddy), apagados sozinhos. Um anônimo não pode
apagar a auditoria enchendo o dia: (1) o teto `VLADO_REGISTRO_DIA_MAX_MB` (50 por dia) vale **só para as falhas que qualquer um
gera sem conta** (`login_falha`, `ativacao_falha`); passado o teto elas são descartadas e o dia grava um aviso `registro_cheio`
(classe `anonimo`); (2) entrada com sucesso, administração, downloads e os demais eventos têm **cota própria, 4 vezes maior**, e
continuam gravando com o dia cheio de falhas (aviso `registro_cheio`, classe `total`, só se essa cota também estourar); (3) as
falhas repetidas do mesmo IP **acima do limite de 20 por minuto** viram **uma única linha por IP e por minuto**, com a contagem
(`quantidade`), em vez de uma por pedido. Um `registro_cheio` é alerta de inundação: veja o `ip` e a `quantidade` das linhas
agregadas. **IP é dado pessoal**: trate
como o registro do Caddy (acesso restrito, 30 dias) e informe a retenção na política de privacidade. O registro **não entra
no backup** (ver `BACKUP.md`) e a falha ao gravar nunca derruba um pedido (aviso sem conteúdo no log do contêiner).

**Modo local (sem Docker):** a Mesa instalada no Windows ou iniciada a partir do código também grava o registro, em
`<pasta de dados>/registro/` (criada no primeiro evento; fica fora do git, com a chave em `<pasta de dados>/segredos/`).
Vale para o modo `local-contas` e para os downloads do modo `local`: são os mesmos eventos, com o IP `127.0.0.1`.

Para ler (no servidor, só quem opera):

```bash
$DC exec vlado sh -c 'cat /app/registro/auditoria-*.jsonl' > auditoria.jsonl      # tudo
$DC exec vlado sh -c 'grep -h "\"evento\":\"login_falha\"" /app/registro/auditoria-$(date -u +%F).jsonl | tail -50'   # falhas de hoje
$DC exec vlado python -c "import json,sys,collections; c=collections.Counter((l['ip'],l.get('motivo')) for l in map(json.loads, open('/app/registro/auditoria-'+sys.argv[1]+'.jsonl')) if l['evento']=='login_falha'); print(c.most_common(10))" 2026-11-22
```

O que procurar: rajadas de `login_falha` do mesmo `ip` ou do mesmo `login_ref` (varredura de senhas), `login_ok` de IP novo
logo depois de `login_falha`, `recuperacao_emitida` ou `acesso_alterado` que ninguém pediu, `operacao_negada` repetida de um
convidado, `download` em volume ou fora do horário, `registro_cheio` (alguém está inundando o registro).

## IP do cliente atrás de CDN ou WAF (SEG-05): `VLADO_PROXIES_CONFIAVEIS`

O limite de 20 tentativas por minuto e o registro usam o **IP do cliente**. Sem configurar nada, a Mesa confia no último salto
do `X-Forwarded-For` (o Caddy). Atrás de uma CDN ou de um WAF todos os pedidos chegam com o IP da borda e **dividem as 20
tentativas**. A correção é dizer à Mesa quem são os proxies de confiança, no `.env` do ambiente:

```
VLADO_PROXIES_CONFIAVEIS=172.18.0.0/16, 203.0.113.0/24      # a rede do Compose (o Caddy) e as faixas da CDN
```

- A lista aceita IPs e redes (IPv4 e IPv6), separados por vírgula, espaço ou ponto e vírgula. Lista inválida **impede a Mesa de
  subir**, com a mensagem dizendo qual item. Uma rede que cobre quase toda a internet (`0.0.0.0/0`, `::/0`, IPv4 menor que /8,
  IPv6 menor que /16) também **impede a partida**: confiar nela deixaria qualquer cliente escolher o próprio IP e escapar do
  limite e da auditoria. Só `VLADO_PROXIES_CONFIAVEIS_AMPLAS=1` a confirma, por decisão consciente.
- Com a lista, o `X-Forwarded-For` só vale se o par TCP (o Caddy) estiver nela, e o cliente é o **primeiro salto que não está na
  lista, lendo da direita para a esquerda**: o que o cliente escreve à esquerda não é levado em conta, então ele não consegue
  forjar o IP. Um salto ilegível interrompe a leitura e vale o par TCP.
- A rede do Compose: `docker network inspect <projeto>_default` (o campo `Subnet`). As faixas da CDN estão no site do
  fornecedor e mudam: revise a lista a cada trimestre.
- **O Caddy também precisa confiar na CDN**, senão ele descarta o `X-Forwarded-For` dela e escreve só o IP da borda. No
  `deploy/Caddyfile`, nas opções globais, acrescente com as mesmas faixas da CDN (sem a rede do Compose):

  ```
  {
  	servers {
  		trusted_proxies static 203.0.113.0/24
  	}
  }
  ```

  Depois confira com um pedido de teste e `$DC exec vlado grep login_ok /app/registro/auditoria-*.jsonl | tail -1`: o `ip` tem
  de ser o seu, não o da borda.
- Sem a lista o comportamento é o de antes (`VLADO_CONFIAR_PROXY=1` no Compose: último salto). Com a lista, ela vale no lugar
  dessa regra.

## Pendências que dependem de pessoa

| | Quem |
|---|---|
| Criar conta e os dois checks no healthchecks.io, com dois canais de alerta | Dono |
| Criar o monitor de fora (UptimeRobot ou equivalente) e ligar os alertas | Dono |
| Colocar `VLADO_VIGIA_PING_URL` e `VLADO_BACKUP_PING_URL` no servidor | Dono digita, operador conduz |
| Fazer e registrar o teste do alerta (tabela acima) | Operador, com o dono |
| Decidir quem atende o alerta fora do horário comercial | Dono |
| Informar a retenção de 30 dias do registro de auditoria (IP de pessoas) na política de privacidade | Dono |
| Atrás de CDN ou WAF: preencher `VLADO_PROXIES_CONFIAVEIS` e o `trusted_proxies` do Caddy com as faixas dela | Operador, com o dono |
