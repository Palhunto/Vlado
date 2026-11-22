<#
.SYNOPSIS
  Sobe, para e cuida do VLADO local (projeto Compose vlado-local) no computador do dono. Roteiro: deploy/LOCAL.md.
.DESCRIPTION
  Uso (na raiz do repositório):  powershell -ExecutionPolicy Bypass -File deploy\vlado-local.ps1 <comando>
  Comandos: subir, parar, status, registros [serviço], seguir [serviço], acessos, semear, backup, backups,
            verificar-backup, restaurar, ca, confiar-ca, esquecer-ca, apagar-tudo, ajuda.
  Só age em projeto Compose cujo nome começa com "vlado-local" e cujos contêineres foram criados por este ambiente
  (rótulo com.vlado.ambiente-local): recusa vlado-homologacao e qualquer outro. Recusa também uma etiqueta de imagem que não
  comece com "local-" (nunca regrava vlado:local) e uma porta fora de 127.0.0.1. A chave privada do backup só é pedida
  em verificar-backup e restaurar, lida sem eco, fica na memória deste processo e é descartada ao terminar.
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)][string]$Comando = 'ajuda',
    [Parameter(Position = 1, ValueFromRemainingArguments = $true)][string[]]$Resto = @(),
    [string]$Projeto = 'vlado-local',
    [string]$ArquivoEnv = 'deploy/ambientes/local.env'
)
$ErrorActionPreference = 'Stop'
$Raiz = Split-Path -Parent $PSScriptRoot
Set-Location $Raiz
$PastaCA = Join-Path $HOME 'Vlado-local'
$ArquivoCA = Join-Path $PastaCA ($Projeto + '-ca.crt')
$Rotulo = 'com.vlado.ambiente-local'

function Escrever($texto, $cor = 'Gray') { Write-Host $texto -ForegroundColor $cor }

function Validar-Projeto {
    # A1: este script derruba, restaura e apaga volumes; por isso só toca em projeto do ambiente local.
    if ($Projeto -cnotmatch '^vlado-local[a-z0-9_-]*$') {
        throw "Projeto '$Projeto' recusado: o nome precisa começar com 'vlado-local' (letras minúsculas, números, - e _). Este script nunca age na homologação nem em outro projeto."
    }
}

function Garantir-Docker {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker não encontrado. Instale e abra o Docker Desktop.' }
    & docker info *> $null
    if ($LASTEXITCODE -ne 0) { throw 'O Docker Desktop não está ligado. Abra-o, espere o ícone ficar verde e tente de novo.' }
}

function Conferir-Dono {
    # A1 (segunda barreira): se o projeto já tem contêineres que este ambiente não criou (sem o rótulo), recusa.
    $todos = @(& docker ps -a -q --filter "label=com.docker.compose.project=$Projeto" | Where-Object { $_ })
    if ($todos.Count -eq 0) { return }
    $nossos = @(& docker ps -a -q --filter "label=com.docker.compose.project=$Projeto" --filter "label=$Rotulo=1" | Where-Object { $_ })
    $alheios = @($todos | Where-Object { $nossos -notcontains $_ })
    if ($alheios.Count -gt 0) {
        throw "O projeto '$Projeto' tem $($alheios.Count) contêiner(es) que não foram criados por este ambiente local (sem o rótulo $Rotulo). Recusado: nada foi alterado."
    }
}

function Ler-Env {
    # Lê CHAVE=VALOR do arquivo (sem aspas), valida e devolve. Cria a partir do exemplo na primeira vez.
    if (-not (Test-Path $ArquivoEnv)) {
        Copy-Item 'deploy/ambientes/local.env.example' $ArquivoEnv
        Escrever "Criei $ArquivoEnv a partir do exemplo. Abra-o, preencha o que diz PREENCHER (pasta de backup e chave PÚBLICA age) e rode de novo." Yellow
        exit 2
    }
    $mapa = @{}
    foreach ($linha in Get-Content $ArquivoEnv -Encoding UTF8) {
        if ($linha -match '^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$') { $mapa[$Matches[1]] = $Matches[2].Trim() }
    }
    Validar-Env $mapa
    return $mapa
}

function Validar-Env($cfg) {
    # A2: etiqueta da imagem. Vazia ou ausente faria o compose usar "local" e regravar vlado:local (a da homologação).
    $versao = $cfg['VLADO_VERSAO']
    if (-not $versao -or $versao -cnotmatch '^local-[A-Za-z0-9_.-]+$') {
        throw "VLADO_VERSAO='$versao' recusada em ${ArquivoEnv}: precisa começar com 'local-' (por exemplo local-dono). Vazia ou 'local' regravaria a imagem vlado:local da homologação."
    }
    # A3: a porta. O endereço 127.0.0.1 está fixo no compose.local.yml; aqui só vai o número, e o antigo formato é recusado.
    foreach ($velha in 'VLADO_PORTA_HTTPS', 'VLADO_PORTA_HTTP') {
        if ($cfg.ContainsKey($velha)) {
            throw "$velha não vale mais no ambiente local ($ArquivoEnv): use VLADO_LOCAL_PORTA=<número>. O endereço é sempre 127.0.0.1."
        }
    }
    $porta = $cfg['VLADO_LOCAL_PORTA']
    if (-not $porta -or $porta -cnotmatch '^[0-9]{4,5}$' -or [int]$porta -lt 1024 -or [int]$porta -gt 65535) {
        throw "VLADO_LOCAL_PORTA='$porta' recusada em ${ArquivoEnv}: use só o número da porta, de 1024 a 65535 (por exemplo 9443). Só 127.0.0.1 é publicado."
    }
    $dominio = $cfg['VLADO_DOMINIO']
    if (-not $dominio -or $cfg['VLADO_ORIGEM'] -cne "https://${dominio}:${porta}") {
        throw "VLADO_ORIGEM em $ArquivoEnv precisa ser exatamente https://<VLADO_DOMINIO>:<VLADO_LOCAL_PORTA> (https://${dominio}:${porta})."
    }
    if ($cfg['VLADO_CADDYFILE'] -cne 'deploy/Caddyfile.interno') {
        throw "VLADO_CADDYFILE em $ArquivoEnv precisa ser deploy/Caddyfile.interno (a CA local); o Caddyfile público tentaria emitir certificado de verdade."
    }
    if ($cfg['VLADO_AMBIENTE'] -cnotin @('homologacao', 'demonstracao')) {
        throw "VLADO_AMBIENTE='$($cfg['VLADO_AMBIENTE'])' recusado em ${ArquivoEnv}: o ambiente local é só de dados sintéticos (homologacao ou demonstracao)."
    }
    # O valor validado vence qualquer variável da sua sessão com o mesmo nome (o ambiente do processo vale mais que o arquivo).
    $env:VLADO_VERSAO = $versao
    $env:VLADO_LOCAL_PORTA = $porta
}

function Compose {
    # docker compose do projeto local; para se o comando falhar.
    $base = @('compose', '-p', $Projeto, '--env-file', $ArquivoEnv, '-f', 'docker-compose.yml', '-f', 'deploy/compose.local.yml')
    & docker @base @args
    if ($LASTEXITCODE -ne 0) { throw "docker compose terminou com erro ($LASTEXITCODE)." }
}

function Ler-Chave {
    Escrever 'Cole a chave PRIVADA do backup (linha AGE-SECRET-KEY-1...) e tecle Enter. Nada aparece na tela e nada é gravado em arquivo.' Cyan
    $seguro = Read-Host 'Chave privada' -AsSecureString
    $ponteiro = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($seguro)
    try { $texto = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ponteiro) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ponteiro) }
    if (-not $texto.Trim().StartsWith('AGE-SECRET-KEY-')) { throw 'Isso não parece uma chave privada age (começa com AGE-SECRET-KEY-).' }
    return $texto.Trim()
}

function Confirmar($palavra, $aviso) {
    Escrever $aviso Yellow
    $resposta = Read-Host "Para continuar digite $palavra"
    if ($resposta -cne $palavra) { Escrever 'Cancelado.' Yellow; exit 1 }
}

function Exportar-CA {
    $id = & docker compose -p $Projeto --env-file $ArquivoEnv -f docker-compose.yml -f deploy/compose.local.yml ps -q caddy
    if (-not $id) { throw 'O Caddy do ambiente local não está de pé. Rode "subir" antes.' }
    New-Item -ItemType Directory -Force -Path $PastaCA | Out-Null
    Compose cp 'caddy:/data/caddy/pki/authorities/local/root.crt' $ArquivoCA
    $cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2 $ArquivoCA
    Escrever "Certificado raiz (SÓ a parte pública) salvo em $ArquivoCA" Green
    Escrever "Assunto: $($cert.Subject)   Impressão digital (SHA-1): $($cert.Thumbprint)" Gray
    return $cert
}

# Antes de qualquer comando que mexa no Docker: projeto, arquivo de ambiente e, só então, o Docker e o dono dos contêineres.
$Conhecidos = @('subir', 'parar', 'status', 'registros', 'seguir', 'acessos', 'semear', 'backup', 'backups', 'verificar-backup',
    'restaurar', 'ca', 'confiar-ca', 'esquecer-ca', 'apagar-tudo')
if ($Comando -cnotin $Conhecidos) { $Comando = 'ajuda' }  # comando desconhecido: só a ajuda, sem tocar no Docker
$cfg = $null
if ($Comando -cne 'ajuda') {
    Validar-Projeto
    if ($Comando -cne 'esquecer-ca') {
        $cfg = Ler-Env
        Garantir-Docker
        Conferir-Dono
    }
}

switch ($Comando) {
    'subir' {
        if (-not $cfg['VLADO_LOCAL_BACKUP_PASTA'] -or $cfg['VLADO_LOCAL_BACKUP_PASTA'] -match 'SEU-USUARIO') {
            throw 'Preencha VLADO_LOCAL_BACKUP_PASTA em deploy/ambientes/local.env (a pasta dos backups de teste).'
        }
        New-Item -ItemType Directory -Force -Path $cfg['VLADO_LOCAL_BACKUP_PASTA'] | Out-Null
        if (-not $cfg['VLADO_BACKUP_DESTINATARIOS']) {
            Escrever 'AVISO: VLADO_BACKUP_DESTINATARIOS está vazio. A Mesa sobe, mas o serviço backup fica "unhealthy" e nenhum backup é feito.' Yellow
        }
        if (-not $cfg['VLADO_VIGIA_PING_URL']) {
            Escrever 'AVISO: a vigia (alerta de que a Mesa caiu) está desligada neste ambiente. Use "status" para conferir.' Yellow
        }
        Compose up -d --build
        Escrever ('Pronto. Abra https://' + $cfg['VLADO_DOMINIO'] + ':' + $cfg['VLADO_LOCAL_PORTA'] + ' (primeira vez: rode "confiar-ca").') Green
        Compose ps
    }
    'parar' { Compose stop; Escrever 'Parado. Os dados continuam nos volumes; "subir" volta.' Green }
    'status' {
        Compose ps
        $ids = & docker compose -p $Projeto --env-file $ArquivoEnv -f docker-compose.yml -f deploy/compose.local.yml ps -q
        if ($ids) { & docker stats --no-stream --format 'table {{.Name}}\t{{.MemUsage}}\t{{.CPUPerc}}' @ids }
        Escrever 'Sem vigia: nada avisa sozinho se a Mesa cair. "backup" unhealthy = backup falhou, atrasou ou não está configurado.' Yellow
    }
    'registros' { Compose logs --tail 200 @Resto }
    'seguir' { Compose logs --tail 50 -f @Resto }
    'acessos' { Compose exec -T caddy tail -n 100 /var/log/caddy/acesso.log }
    'backup' { Compose exec -T backup python scripts/backup.py rodada }
    'backups' { Compose exec -T backup python scripts/backup.py listar }
    'semear' {
        # Dois casos e três contas sintéticos; os links de ativação (com token) ficam num arquivo 0600 dentro do volume e
        # são mostrados só aqui, no seu terminal. Não roda em ambiente editorial.
        Compose exec -T vlado python scripts/semear_ambiente.py --origem $cfg['VLADO_ORIGEM'] --saida /app/acesso/links_local.txt
        Escrever 'Links de ativação (use cada um uma vez; quem ativa define a senha):' Cyan
        Compose exec -T vlado cat /app/acesso/links_local.txt
    }
    'verificar-backup' {
        $env:VLADO_BACKUP_CHAVE_PRIVADA = Ler-Chave
        try {
            Compose --profile restauracao run --rm -T restauracao python scripts/backup.py verificar --do-destino ultimo --identidade-env VLADO_BACKUP_CHAVE_PRIVADA
            Escrever 'Backup decifrado e conferido (nenhum dado foi alterado).' Green
        }
        finally { Remove-Item Env:\VLADO_BACKUP_CHAVE_PRIVADA -ErrorAction SilentlyContinue }
    }
    'restaurar' {
        Confirmar 'RESTAURAR' "Isto SUBSTITUI os casos, as contas e o resto dos dados do ambiente local '$Projeto' pelo último backup e encerra as sessões. A homologação e os outros projetos não são tocados."
        $env:VLADO_BACKUP_CHAVE_PRIVADA = Ler-Chave
        try {
            Compose stop vlado backup caddy
            Compose --profile restauracao run --rm -T restauracao python scripts/backup.py verificar --do-destino ultimo --identidade-env VLADO_BACKUP_CHAVE_PRIVADA
            Compose --profile restauracao run --rm -T restauracao
        }
        finally { Remove-Item Env:\VLADO_BACKUP_CHAVE_PRIVADA -ErrorAction SilentlyContinue }
        Compose up -d
        Escrever 'Restaurado. Entre de novo (as sessões foram encerradas) e confira casos e rodadas.' Green
    }
    'ca' { Exportar-CA | Out-Null; Escrever 'Para o navegador confiar nela: deploy\vlado-local.ps1 confiar-ca (Firefox: passo a passo do LOCAL.md).' Gray }
    'confiar-ca' {
        $cert = Exportar-CA
        Escrever 'O Windows vai perguntar se você confia nesta autoridade: confira a impressão digital acima e responda Sim. Vale só para o seu usuário.' Yellow
        Import-Certificate -FilePath $ArquivoCA -CertStoreLocation Cert:\CurrentUser\Root | Out-Null
        Escrever 'Pronto para Edge e Chrome. Feche e abra o navegador. (Firefox: ver LOCAL.md.)' Green
    }
    'esquecer-ca' {
        if (-not (Test-Path $ArquivoCA)) { throw "Não achei $ArquivoCA. Rode 'ca' antes ou remova a autoridade pelo certmgr.msc." }
        $cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2 $ArquivoCA
        $alvo = Join-Path 'Cert:\CurrentUser\Root' $cert.Thumbprint
        if (Test-Path $alvo) { Remove-Item $alvo; Escrever "Removi só a autoridade deste ambiente ($($cert.Thumbprint))." Green }
        else { Escrever 'Esta autoridade não está instalada no seu usuário.' Yellow }
    }
    'apagar-tudo' {
        Confirmar $Projeto "Isto APAGA os volumes do projeto '$Projeto': casos, contas, chaves coladas na Mesa e a CA local. Os backups na pasta do computador não são apagados. Os outros projetos não são tocados."
        Compose down -v
        Escrever 'Apagado. Se você instalou a CA no navegador, rode "esquecer-ca" (se ainda tiver o arquivo).' Green
    }
    default {
        Get-Help $PSCommandPath -Detailed | Out-String | Write-Host
    }
}
