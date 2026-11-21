# Roteiro de incidente

Para quem opera o servidor do Vlado quando algo dá errado. Alertas e como chegam: `deploy/MONITORAMENTO.md`. Backup e
restauração: `deploy/BACKUP.md`. Decisões que cabem ao dono estão marcadas **[Dono]**.

Nos comandos, troque `<amb>` pelo ambiente (`editorial`, `demonstracao`, `homologacao`) e use sempre estas duas
variáveis no terminal do servidor:

```bash
P="vlado-<amb>"                       # nome do projeto Compose
DC="docker compose -p $P --env-file deploy/ambientes/<amb>.env"
```

## Regras para qualquer incidente

1. **Uma pessoa coordena** e anota, com horário, tudo o que vê e faz (linha do tempo). Sem senha, chave ou token
   no registro.
2. **Conter antes de consertar, preservar antes de limpar.** Não apague logs, contêineres, volumes nem contas para
   "ficar limpo". O que parece lixo pode ser a única prova do que aconteceu.
3. **Nunca** use `down` com a opção que remove volumes, nem apague volumes de dados: casos, execuções, conversas e
   contas vivem neles. Para parar o serviço, `stop`; para voltar, `start` ou `up -d`.
4. Em dúvida entre mexer e esperar, espere e pergunte ao dono. A Mesa fora do ar por uma hora custa menos que
   dado perdido.

| Sintoma | Vá para |
|---|---|
| Alerta de Mesa fora do ar, ou usuários sem acesso | 1 |
| Alerta de pouco disco, ou erros de gravação | 2 |
| Navegador acusa certificado inválido ou vencido | 3 |
| Alerta de backup, ou backup em atraso | 4 |
| Acesso estranho, conta ou chave suspeita, vazamento | 5 |
| Perda de dados ou de servidor | 6 |

## 1. Mesa fora do ar

1. Confirme de fora: abra `https://<domínio>/saude` (deve mostrar `{"ok": true}`). Se abre, o problema é local do
   usuário ou intermitente; se não abre, siga.
2. Estado dos serviços: `$DC ps -a`. Procure `unhealthy`, `Exited` ou `Restarting`.
3. Veja o motivo: `$DC logs --tail 100 vlado` e `$DC logs --tail 50 caddy`. Falta de memória:
   `docker inspect -f '{{.State.OOMKilled}}' $P-vlado-1` (`true` = estourou o limite; aumente `VLADO_MEM_LIMITE` ou
   reduza o uso concorrente e reinicie).
4. Se o app caiu e não voltou: `$DC up -d vlado`. Ele reinicia sozinho após queda (`restart: unless-stopped`); se
   reinicia em ciclo, **leia o log antes de insistir**.
5. Se `vlado` está saudável e `caddy` não: `$DC up -d caddy` e veja a seção 3 se o log falar de certificado.
6. Se o servidor inteiro não responde: o painel do provedor (console, reinício da máquina). Depois que subir, o
   Docker reinicia os serviços sozinho; confira com `$DC ps`.
7. Confira ao final: `/saude` de fora, login de uma conta de teste, e se `backup` está `healthy`.
8. Anote causa e duração. Se foi falta de disco ou memória, abra o item de capacidade para o dono.

## 2. Disco cheio

Sinais: alerta "Pouco disco livre", erros de gravação no log, cadastro falhando.

1. Meça sem apagar nada: `df -h`, `docker system df`, e
   `docker run --rm -v ${P}_casos:/d:ro --entrypoint du <imagem-do-app> -sh /d` para um volume de dados.
2. O que **pode** liberar espaço com segurança:
   - **Temporários do OCR** (volume `tmp_vlado`): só têm arquivos de trabalho. `$DC restart vlado` os esvazia na
     partida.
   - **Imagens antigas**: `docker image ls` e remova **só** a etiqueta que não é a atual nem a anterior
     (a anterior serve para reverter): `docker rmi vlado:<versão-antiga>`.
   - **Registro do Caddy** e dos contêineres: já têm rotação (no máximo cerca de 400 MB e 50 MB por serviço); se
     precisar de espaço agora, copie para fora do servidor e deixe a rotação trabalhar.
   - **Rascunho local do backup** (`backup_trabalho`): esvazia sozinho a cada rodada.
3. O que **não** fazer: apagar casos, execuções, conversas, lixeira ou contas; limpar tudo do Docker de uma vez.
   O crescimento real dos dados pede mais disco: avise o dono **[Dono]** (aumentar o volume do servidor é decisão
   dele).
4. Depois de liberar: `$DC restart vlado`, confira `/saude` e rode `$DC exec -T backup python scripts/backup.py rodada`
   (um backup bom de hoje antes de qualquer outra coisa).
5. Prevenção: `VLADO_VIGIA_DISCO_MIN_GB` (padrão 5 GB) avisa antes de faltar espaço; ajuste ao tamanho do disco.

## 3. Certificado vencido ou inválido

O Caddy obtém e renova o certificado sozinho; um problema aqui quase sempre é **rede ou DNS**, não o Caddy.

1. `$DC logs --tail 200 caddy | grep -i -E "obtain|renew|error|challenge"`.
2. Causas comuns: porta **80 ou 443** fechada no firewall do provedor; **DNS** do domínio apontando para outro IP
   **[Dono]** (é ele quem mexe no DNS); limite de emissões do provedor de certificados (espere o prazo informado no
   log); relógio do servidor errado (`date -u`).
3. Corrija a causa e `$DC restart caddy`; ele tenta de novo. Não desligue o HTTPS para "dar um jeito": o login
   trafega senhas.
4. **Não apague** o volume `caddy_data`: ali ficam a conta e os certificados já emitidos.
5. Confira de fora: `echo | openssl s_client -connect <domínio>:443 -servername <domínio> 2>/dev/null | openssl x509 -noout -dates`.
6. Enquanto não resolver, avise os usuários que a Mesa está indisponível; **não os oriente a ignorar o aviso do
   navegador**.

## 4. Backup falhando

1. `$DC logs --tail 50 backup` e `$DC exec -T backup python scripts/backup.py saude`.
2. Leia a mensagem:
   - "não configurado": faltam `VLADO_BACKUP_DESTINO` ou `VLADO_BACKUP_DESTINATARIOS` (deploy/BACKUP.md).
   - "Há operação em andamento": um cadastro longo; ele tenta de novo sozinho. Se persistir por horas, veja se há
     pasta de preparo abandonada (aviso no manifesto) e a Mesa saudável.
   - "rclone falhou": rede do servidor, credencial do destino vencida ou revogada, bucket cheio ou sem permissão.
     Teste: `$DC exec -T backup python scripts/backup.py listar`.
   - "chave PRIVADA" ou "Destinatário inválido": a variável recebeu a chave errada; ponha só a pública `age1...`.
   - disco: seção 2.
3. Corrija e force uma rodada: `$DC exec -T backup python scripts/backup.py rodada`; depois `listar` deve mostrar o
   arquivo novo.
4. Backup parado há mais de um dia com muito cadastro novo? Gere um à mão, cifrado, e leve para fora do servidor:
   `$DC exec -T backup python scripts/backup.py rodada` é o caminho; sem destino, use `criar --cifrar-para` (BACKUP.md).
5. Se o backup nunca foi restaurado, **agende o ensaio de restauração** (BACKUP.md): um backup que nunca restaurou
   é uma suposição.

## 5. Suspeita de invasão

Exemplos: login de quem não deveria, contas ou administradores novos, chave de API com gasto estranho, aviso do
provedor, arquivo ou contêiner desconhecido, backup apagado no destino, vazamento de documento. **Aja como se fosse
real até provar o contrário.**

**Princípios: conter sem destruir; preservar; entender; trocar o que pode estar exposto; avisar; recuperar em ambiente
limpo.**

### 5.1 Conter (primeiros minutos)

1. Avise o dono **[Dono]** agora; ele decide parar o serviço e quem será avisado.
2. Tire a Mesa do ar **sem destruir nada**: `$DC stop caddy` (o público deixa de entrar; contêineres, volumes e
   registros ficam como estão). Se a suspeita for do servidor inteiro, o dono ou o consultor pode isolá-lo na rede
   pelo painel do provedor, **mantendo a máquina ligada** (a memória e os processos também são prova).
3. **Não apague nada**: nem logs, nem contêineres (`stop`, nunca remover), nem volumes, nem contas, nem backups.
   **Não reinicie** o servidor sem necessidade: pode perder prova na memória.

### 5.2 Preservar a evidência

Faça cópias **somente leitura**, guarde **fora do servidor**, calcule o hash e anote quem copiou e quando. Idealmente,
peça ao provedor um **instantâneo (snapshot) do disco** antes de mexer em qualquer coisa.

```bash
mkdir -p evidencia && cd evidencia
$DC ps -a > ps.txt;  docker images --digests > imagens.txt;  docker inspect $(docker ps -aq --filter name=$P) > inspect.json
$DC logs --no-color --timestamps > logs-compose.txt
docker cp $P-caddy-1:/var/log/caddy ./caddy-acesso            # registro de acesso (IPs, caminhos, status; sem segredos)
# volumes de dados, lidos em modo somente leitura:
for v in casos conversas execucoes lixeira acesso ajustes; do
  docker run --rm -u 0 -v ${P}_$v:/d:ro -v "$PWD":/o --entrypoint tar vlado-backup:<versão> czf /o/$v.tgz -C /d .
done
# o host: quem entrou e o que roda
last -a > last.txt; sudo journalctl --since "7 days ago" > journal.txt; ps auxf > processos.txt; ss -tupn > conexoes.txt
sha256sum * > SHA256SUMS
```

Leve a pasta para fora (computador de confiança ou armazenamento do dono) e **não a analise no servidor suspeito**.
O volume `segredos` (chaves de API) fica no servidor: ele não entra na cópia, porque as chaves serão trocadas.

### 5.3 Entender (em cópia, nunca no servidor suspeito)

- **Registro de acesso do Caddy:** horário, IP, método, caminho (tokens mascarados), status. Procure IPs novos, rajadas de
  `/api/entrar` com status 401, acessos a horários estranhos, `/ativar/*` repetidos.
- **Eventos da conta** (`acesso/acesso.json`, campo `eventos`): logins, criação e desativação de contas, quem fez. Os
  eventos não guardam senha, token, link nem hash.
- Compare o hash dos documentos nos casos com os do manifesto de cada caso: qualquer divergência é adulteração.
- Veja o **gasto** nos painéis das chaves de API (Anthropic, OpenAI): consumo fora do padrão indica chave vazada.

### 5.4 Trocar o que pode estar exposto (num ambiente limpo, nesta ordem)

1. **Chaves de API** (Anthropic e OpenAI): o **dono** revoga a chave antiga no painel do provedor e cria outra **[Dono]**.
   A nova é digitada só no servidor limpo (variável de ambiente ou Mesa), nunca no chat, e-mail ou git.
2. **Credenciais do destino do backup** (S3 ou SFTP): revogue e crie novas **[Dono]**; confira se backups antigos
   foram apagados ou trocados no destino (versionamento e bloqueio de objeto ajudam). Atualize
   `deploy/ambientes/<amb>-backup.env` no servidor limpo.
3. **Acesso ao servidor e ao provedor**: troque senhas, revogue chaves SSH conhecidas, exija verificação em duas
   etapas, revise quem tem acesso ao painel.
4. **Contas da Mesa**: para cada conta, `python scripts/acesso.py recuperar ID --origem https://<domínio>` gera novo
   link de ativação e **derruba as sessões**; contas que não devem mais existir, `desativar ID` (também derruba as
   sessões). Entregue os links por canal seguro, um a um. Todas as senhas antigas ficam inválidas.
5. **Endereços de monitoramento** (healthchecks.io e outros): gere novos e atualize o `.env`.
6. **Chave de cifra do backup (age):** a chave **privada** nunca esteve no servidor, então os backups continuam
   protegidos, **a menos que ela mesma tenha vazado** (computador do dono invadido, cópia em local inseguro). Se vazou,
   gere um novo par, troque a chave pública no `.env`, e trate **todos** os backups antigos como expostos.

### 5.5 Recuperar

1. Suba um **servidor novo e limpo** (não reutilize o comprometido) e restaure o último backup **anterior à
   intrusão** (seção 6); `verificar` confere os hashes e `--do-destino NOME` escolhe o arquivo.
2. Aplique as trocas da seção 5.4 antes de reabrir ao público; reaponte o DNS **[Dono]** só no fim.
3. Mantenha o servidor antigo **desligado e intacto** (ou o snapshot) até a conclusão da apuração do incidente.
4. Documente linha do tempo, causa provável, dado afetado e o que mudou.

### 5.6 Quem avisar

Quem avisar, em ordem, com os fatos conhecidos e **sem especular** sobre autoria:

1. **Dono** (imediato) e o responsável técnico.
2. **Provedor de nuvem** (suporte e abuso): pode ajudar com snapshot, logs de acesso e bloqueio.
3. **Equipe e jornalistas com contas**: para trocar senhas e desconfiar de mensagens pedindo links ou senhas.
4. **Titulares dos dados e fontes** presentes nos documentos, se houver risco a elas **[Dono]**.
5. **ANPD** e os titulares, se o incidente puder acarretar risco ou dano relevante (LGPD, art. 48). A ANPD
   usa 3 dias úteis como referência de prazo (Resolução CD/ANPD nº 15/2024): **a decisão e o texto cabem ao dono e à
   assessoria jurídica; confirme o prazo vigente com eles** **[Dono]**.
6. **Autoridade policial**, se houver crime (invasão, extorsão). Entregue a cópia de evidência com os hashes.

Não divulgue detalhes técnicos em público antes de conter e de falar com a assessoria jurídica.

## 6. Restauração

Quando usar: dado corrompido ou apagado, servidor perdido, retorno a um estado anterior à intrusão. Passo a passo
completo e ensaio: `deploy/BACKUP.md`. Resumo:

1. Pare quem grava: `$DC stop vlado backup` (se o ambiente ainda existe; a restauração **se recusa** a rodar com a Mesa no ar). Num servidor novo, suba só o necessário.
2. A chave privada age vem do dono **[Dono]** e é colada no terminal de quem restaura (`IFS= read -rs -d '' VLADO_BACKUP_CHAVE_PRIVADA; export VLADO_BACKUP_CHAVE_PRIVADA`), **nunca gravada em arquivo no servidor** (onde ficam as credenciais do destino); detalhes e o que vale para pen drive em `deploy/BACKUP.md`. Ao terminar, `unset VLADO_BACKUP_CHAVE_PRIVADA`.
3. Conferir sem restaurar: `... run --rm -T restauracao python scripts/backup.py verificar --do-destino ultimo --identidade-env VLADO_BACKUP_CHAVE_PRIVADA`.
4. Restaurar (com a variável já informada como no passo 2): `$DC --profile restauracao run --rm -T restauracao`
   (o último), ou `... restaurar --do-destino NOME --identidade-env VLADO_BACKUP_CHAVE_PRIVADA --substituir`.
   **Antes de substituir dados em uso, preserve uma cópia do estado atual** (5.2): a restauração troca o conteúdo.
5. `$DC up -d`; confira `/saude`, as contas (todas entram de novo: as sessões são apagadas) e abra um caso.
6. Perda máxima: o que foi gravado desde o backup escolhido. Informe os usuários do que precisa ser refeito.

## Contatos (preencher antes de precisar)

| Papel | Nome | Telefone / canal |
|---|---|---|
| Dono | | |
| Responsável técnico | | |
| Suporte do provedor de nuvem | | |
| Assessoria jurídica | | |
| Quem atende alertas fora do horário | | |

## Depois do incidente

Em até uma semana: relato sem culpa (o que aconteceu, o que funcionou, o que faltou), ajuste deste roteiro e dos
alertas, e itens de prevenção com responsável e data.
