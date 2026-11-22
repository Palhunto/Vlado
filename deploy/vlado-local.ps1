<#
.SYNOPSIS
  Sobe, para e cuida do VLADO local (projeto Compose vlado-local) no computador do dono. Roteiro: deploy/LOCAL.md.
.DESCRIPTION
  Uso (na raiz do repositório):  powershell -ExecutionPolicy Bypass -File deploy\vlado-local.ps1 <comando>
  Comandos: subir, parar, status, registros [serviço], seguir [serviço], acessos, semear, backup, backups,
            verificar-backup, restaurar, ca, confiar-ca, esquecer-ca, apagar-tudo, ajuda.
  Nunca mexe nos vlado-homologacao-* nem na imagem vlado:local. A chave privada do backup só é pedida em
  verificar-backup e restaurar, lida sem eco, fica na memória deste processo e é descartada ao terminar.
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

function Escrever($texto, $cor = 'Gray') { Write-Host $texto -ForegroundColor $cor }

function Garantir-Docker {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker não encontrado. Instale e abra o Docker Desktop.' }
    & docker info *> $null
    if ($LASTEXITCODE -ne 0) { throw 'O Docker Desktop não está ligado. Abra-o, espere o ícone ficar verde e tente de novo.' }
}

function Ler-Env {
    # Lê CHAVE=VALOR do arquivo (sem aspas). Cria a partir do exemplo na primeira vez.
    if (-not (Test-Path $ArquivoEnv)) {
        Copy-Item 'deploy/ambientes/local.env.example' $ArquivoEnv
        Escrever "Criei $ArquivoEnv a partir do exemplo. Abra-o, preencha o que diz PREENCHER (pasta de backup e chave PÚBLICA age) e rode de novo." Yellow
        exit 2
    }
    $mapa = @{}
    foreach ($linha in Get-Content $ArquivoEnv -Encoding UTF8) {
        if ($linha -match '^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$') { $mapa[$Matches[1]] = $Matches[2].Trim() }
    }
    return $mapa
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

switch ($Comando) {
    'subir' {
        Garantir-Docker
        $cfg = Ler-Env
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
        Escrever ('Pronto. Abra https://' + $cfg['VLADO_DOMINIO'] + ':' + (($cfg['VLADO_PORTA_HTTPS'] -split ':')[-1]) + ' (primeira vez: rode "confiar-ca").') Green
        Compose ps
    }
    'parar' { Garantir-Docker; Ler-Env | Out-Null; Compose stop; Escrever 'Parado. Os dados continuam nos volumes; "subir" volta.' Green }
    'status' {
        Garantir-Docker; Ler-Env | Out-Null
        Compose ps
        $ids = & docker compose -p $Projeto --env-file $ArquivoEnv -f docker-compose.yml -f deploy/compose.local.yml ps -q
        if ($ids) { & docker stats --no-stream --format 'table {{.Name}}\t{{.MemUsage}}\t{{.CPUPerc}}' @ids }
        Escrever 'Sem vigia: nada avisa sozinho se a Mesa cair. "backup" unhealthy = backup falhou, atrasou ou não está configurado.' Yellow
    }
    'registros' { Garantir-Docker; Ler-Env | Out-Null; Compose logs --tail 200 @Resto }
    'seguir' { Garantir-Docker; Ler-Env | Out-Null; Compose logs --tail 50 -f @Resto }
    'acessos' { Garantir-Docker; Ler-Env | Out-Null; Compose exec -T caddy tail -n 100 /var/log/caddy/acesso.log }
    'backup' { Garantir-Docker; Ler-Env | Out-Null; Compose exec -T backup python scripts/backup.py rodada }
    'backups' { Garantir-Docker; Ler-Env | Out-Null; Compose exec -T backup python scripts/backup.py listar }
    'semear' {
        # Dois casos e três contas sintéticos; os links de ativação (com token) ficam num arquivo 0600 dentro do volume e
        # são mostrados só aqui, no seu terminal. Não roda em ambiente editorial.
        Garantir-Docker; $cfg = Ler-Env
        Compose exec -T vlado python scripts/semear_ambiente.py --origem $cfg['VLADO_ORIGEM'] --saida /app/acesso/links_local.txt
        Escrever 'Links de ativação (use cada um uma vez; quem ativa define a senha):' Cyan
        Compose exec -T vlado cat /app/acesso/links_local.txt
    }
    'verificar-backup' {
        Garantir-Docker; Ler-Env | Out-Null
        $env:VLADO_BACKUP_CHAVE_PRIVADA = Ler-Chave
        try {
            Compose --profile restauracao run --rm -T restauracao python scripts/backup.py verificar --do-destino ultimo --identidade-env VLADO_BACKUP_CHAVE_PRIVADA
            Escrever 'Backup decifrado e conferido (nenhum dado foi alterado).' Green
        }
        finally { Remove-Item Env:\VLADO_BACKUP_CHAVE_PRIVADA -ErrorAction SilentlyContinue }
    }
    'restaurar' {
        Garantir-Docker; Ler-Env | Out-Null
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
    'ca' { Garantir-Docker; Ler-Env | Out-Null; Exportar-CA | Out-Null; Escrever 'Para o navegador confiar nela: deploy\vlado-local.ps1 confiar-ca (Firefox: passo a passo do LOCAL.md).' Gray }
    'confiar-ca' {
        Garantir-Docker; Ler-Env | Out-Null
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
        Garantir-Docker; Ler-Env | Out-Null
        Confirmar $Projeto "Isto APAGA os volumes do projeto '$Projeto': casos, contas, chaves coladas na Mesa e a CA local. Os backups na pasta do computador não são apagados. Os outros projetos não são tocados."
        Compose down -v
        Escrever 'Apagado. Se você instalou a CA no navegador, rode "esquecer-ca" (se ainda tiver o arquivo).' Green
    }
    default {
        Get-Help $PSCommandPath -Detailed | Out-String | Write-Host
    }
}
