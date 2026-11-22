# VLADO no seu computador (ambiente local, decisão D7)

O servidor foi adiado; a homologação da Onda 1 roda aqui, no Windows com o Docker Desktop. É um projeto Compose
próprio (`vlado-local`), separado dos `vlado-homologacao-*` que já existem: volumes, rede, portas, imagem e cookies
não se misturam, e nada aqui toca neles.

**O que este ambiente é:** a Mesa em HTTPS (certificado de uma autoridade local do Caddy), com dados sintéticos, backup
diário cifrado numa pasta do computador e limites de memória pequenos. **O que não é:** produção. Não ponha dado de
verdade aqui, e a pasta de backup está na mesma máquina, então não protege contra perda do computador.

Tudo se faz com um script, na raiz do repositório, no PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File deploy\vlado-local.ps1 <comando>
```

## Primeira vez (uns 15 minutos)

1. **Docker Desktop ligado** (ícone verde).
2. **Chaves do backup (você).** Instale o `age` (https://github.com/FiloSottile/age/releases, ou `winget install FiloSottile.age`)
   e, **fora da pasta do repositório**, rode `age-keygen -o chave-vlado.txt`. A linha `# public key: age1...` é a chave
   pública. A linha `AGE-SECRET-KEY-1...` é a privada: guarde em **dois lugares** (gerenciador de senhas e cópia
   impressa ou pen drive) e **nunca** no repositório, em e-mail ou em chat. Sem ela nenhum backup abre. Mais detalhes:
   `deploy/BACKUP.md`.
3. **Rode `subir`** uma vez. Ele cria `deploy\ambientes\local.env` (fora do git) a partir do exemplo e para. Abra o
   arquivo e preencha só duas linhas: `VLADO_LOCAL_BACKUP_PASTA` (uma pasta fora do repositório, com barras normais:
   `C:/Users/voce/Vlado-backups-teste`) e `VLADO_BACKUP_DESTINATARIOS` (a chave **pública**, `age1...`).
4. **Rode `subir` de novo.** Na primeira vez constrói a imagem (alguns minutos). No fim mostra o endereço:
   **https://vlado.localhost:9443** (sempre `https://`, e com o `:9443`).
5. **Certificado:** rode `confiar-ca` (abaixo) e abra o endereço no Edge ou no Chrome.
6. **Dados sintéticos:** `semear` cria dois casos e três contas fictícios e mostra, no seu terminal, os links de
   ativação (cada um vale uma vez; quem ativa define a senha). Pode repetir sem duplicar.

## Comandos do dia a dia

| Quero... | Comando |
|---|---|
| Subir (e atualizar depois de mudar o código) | `subir` |
| Parar sem perder nada | `parar` |
| Ver se está de pé, e quanta memória usa | `status` |
| Ler os registros (últimas 200 linhas) de tudo, ou de um serviço (`vlado`, `caddy`, `backup`) | `registros` ou `registros backup` |
| Acompanhar ao vivo | `seguir` ou `seguir vlado` |
| Ver quem acessou (IP, caminho sem o token, status) | `acessos` |
| Criar os casos e contas sintéticos (e rever os links de ativação) | `semear` |
| Fazer um backup agora | `backup` |
| Listar os backups | `backups` |
| Conferir que o último backup abre (não altera nada) | `verificar-backup` |
| Restaurar o último backup | `restaurar` |
| Apagar este ambiente inteiro (dados e CA) | `apagar-tudo` |

Para mais de um ambiente local ou outro arquivo de ambiente: `-Projeto nome -ArquivoEnv caminho`.

## Certificado (a "CA local" do Caddy)

O Caddy cria uma autoridade de certificação própria para este ambiente; sem confiar nela o navegador avisa que o
site é inseguro.

- **Edge e Chrome:** `confiar-ca`. Ele copia o certificado raiz (só a parte pública) para
  `C:\Users\voce\Vlado-local\vlado-local-ca.crt`, mostra a impressão digital e o Windows pergunta se você confia:
  confira e responda Sim. Vale só para o seu usuário. Feche e abra o navegador.
- **Firefox:** `ca`, depois Configurações > Privacidade e segurança > Certificados > Ver certificados > Autoridades >
  Importar, escolha o arquivo acima e marque "Confiar nesta CA para identificar sites".
- **Se apagar o ambiente (`apagar-tudo`) o Caddy cria outra CA**: rode `confiar-ca` de novo.
- **Para parar de confiar:** `esquecer-ca` (remove só a autoridade deste ambiente, pela impressão digital, sem
  tocar nas outras). Faça isso quando terminar de homologar.
- **Cuidado:** a autoridade não é limitada a um nome; quem tivesse a chave dela (que fica no volume `caddy_data`,
  só neste computador) poderia emitir certificados para qualquer site que seu navegador aceita. Por isso: dados
  sintéticos, nada de copiar esse volume, e `esquecer-ca` ao fim.
- Programas que não são o navegador (o `curl` do Windows) podem reclamar de "revogação desconhecida": use
  `curl --ssl-no-revoke --cacert <arquivo> https://vlado.localhost:9443/saude`.

## Limites de memória (cabem em 8 GB junto com os agentes)

Os números abaixo são **tetos**: o que o contêiner não usa fica livre para o Windows e os agentes.

| Serviço | Teto aqui | Padrão de servidor | Uso medido em repouso |
|---|---|---|---|
| App (`vlado`) | **2 GB** | 5 GB | ~120 MB |
| Caddy | 256 MB | 256 MB | ~12 MB |
| Backup (`backup`) | 512 MB | 512 MB | ~50 MB |
| Soma dos tetos | **~2,8 GB** | | ~180 MB |

O pico é o OCR de PDF escaneado grande: a 2 GB um PDF de muitas dezenas de páginas coloridas pode estourar o teto (o
app é encerrado e reinicia; o cadastro desse arquivo falha). Se acontecer, com os agentes parados troque
`VLADO_MEM_LIMITE=3g` em `local.env` e rode `subir`. Os temporários do OCR vão para um volume em disco, não para a
memória; deixe uns 10 GB livres no disco do Docker.

O Docker Desktop leva por padrão metade da RAM (o WSL2). Se quiser garantir que ele nunca tome mais do que o
combinado, é uma decisão sua: crie `C:\Users\voce\.wslconfig` com `[wsl2]`, `memory=4GB`, `swap=2GB`, rode
`wsl --shutdown` e reabra o Docker Desktop (isto derruba também os contêineres da homologação até voltarem).

## Backup e restauração

- **Quando:** todo dia às **12:00 de Brasília** (15:00 UTC) e **uma vez a cada vez que o ambiente sobe**, porque o
  computador pode estar desligado no horário. Retenção: todos dos últimos 7 dias, 4 semanais, 3 mensais.
- **Onde:** os arquivos `vlado-homologacao-AAAAMMDDT...tar.gz.age` na pasta `VLADO_LOCAL_BACKUP_PASTA`. São cifrados:
  sem a chave privada não abrem, nem para você. (O prefixo `homologacao` vem de `VLADO_AMBIENTE`; é o nome do tipo
  de ambiente, não da homologação que já roda aqui.)
- **O que entra:** casos, rodadas, conversas, lixeira, entrada, contas (`acesso/`) e ajustes. **Não entra** a chave de
  API colada na Mesa (`segredos/`): cole de novo depois de restaurar.
- **Ver se funciona:** `backup`, depois `backups`. `status` mostra o serviço `backup` como `healthy`; `unhealthy`
  significa falha, atraso de mais de 72 h ou chave pública faltando (`registros backup` diz qual).
- **Ensaiar a restauração (faça uma vez antes de confiar):** `verificar-backup` pede a chave privada, decifra o
  último backup e confere todos os hashes sem alterar nada. `restaurar` faz o mesmo e depois **substitui** os dados
  deste ambiente (pede para você digitar `RESTAURAR`; para o app, restaura e sobe de novo). Todos entram de novo
  (as sessões são apagadas).
- **A chave privada:** é colada no terminal quando o script pede, sem eco, e só existe na memória daquele comando.
  Não a salve em arquivo dentro do repositório nem junto da pasta de backups.

## Vigia (alerta de que a Mesa caiu): desligada

A vigia (`VLADO_VIGIA_PING_URL`) avisa um serviço de fora (healthchecks.io) que o app respondeu; sem esse endereço
ela não roda, e aqui não faz sentido ter um: com o computador desligado nada avisaria. Vale então olhar `status`.
Se quiser um receptor próprio no futuro, é só preencher a variável.

## Portas e nomes

| | Valor |
|---|---|
| Endereço | `https://vlado.localhost:9443`, só neste computador (`127.0.0.1`) |
| Porta HTTP | fechada de propósito (o redirecionamento do Caddy iria para a 443, que é a da homologação) |
| Projeto Compose | `vlado-local` (volumes `vlado-local_*`, rede `vlado-local_default`) |
| Imagens | `vlado:local-dono` e `vlado-backup:local-dono` (nada em `vlado:local`) |
| Domínio | `vlado.localhost`: não é o `localhost` da homologação, então os cookies não se misturam |

## O que só um servidor real valida

Este ambiente prova a Mesa, o endurecimento dos contêineres, o registro, o backup e a restauração. **Não prova:**

1. **Certificado público:** a emissão pelo Let's Encrypt (portas 80 e 443 abertas, `deploy/Caddyfile`), a renovação e
   o redirecionamento HTTP para HTTPS na porta padrão. Aqui só roda a CA local.
2. **DNS:** o domínio apontando para o servidor e o que o navegador de outras pessoas vê.
3. **Monitor externo e vigia:** alerta quando o servidor cai, e o aviso por silêncio do dead-man's switch
   (`deploy/MONITORAMENTO.md`). Um computador pessoal desliga por motivos que um servidor não tem.
4. **Backup fora da máquina:** o envio por rclone a um S3/SFTP de outro fornecedor, credencial só de gravação, bloqueio
   de objeto, e restaurar a partir dele em outra máquina (`deploy/BACKUP.md`).
5. **E-mail:** qualquer envio (convites, avisos, alerta) e a entrega nas caixas reais.
6. **Carga e rede reais:** outras pessoas ao mesmo tempo, latência, o firewall do provedor, o disco que enche, a
   memória com 4 vCPU e 8 GB só para a Mesa (aqui ela divide a máquina com agentes e a homologação).
7. **Roteiro de incidente de ponta a ponta** (`deploy/INCIDENTE.md`): servidor perdido, restauração em máquina
   nova, troca de chave.
