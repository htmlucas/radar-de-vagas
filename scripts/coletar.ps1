# Coleta de vagas (usado pelo agendamento diário do Windows; também pode rodar à mão).
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\coletar.ps1
#
# 1. Garante que o Docker e o banco estejam no ar (abre o Docker Desktop se estiver fechado).
# 2. Roda o pipeline (coleta -> bronze -> silver -> notas).
# 3. Grava tudo em dados\logs\coleta-AAAA-MM-DD.log e apaga logs com mais de 30 dias.
#
# A tarefa agendada tem dois gatilhos (todo dia no horario e 3 min depois de fazer logon, para recuperar
# uma coleta perdida com o PC desligado). Se ja houve uma coleta bem-sucedida ha menos de 4 horas, este
# script nao coleta de novo. -Forcar ignora essa trava. O botao "Coletar agora" do painel nao passa por aqui.

param([switch]$Forcar)

$ErrorActionPreference = "Continue"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

$pastaLogs = Join-Path $raiz "dados\logs"
New-Item -ItemType Directory -Force -Path $pastaLogs | Out-Null
$log = Join-Path $pastaLogs ("coleta-" + (Get-Date -Format "yyyy-MM-dd") + ".log")

function Registrar([string]$texto) {
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $texto" | Out-File -FilePath $log -Append -Encoding utf8
}

function DockerNoAr {
    docker info --format "{{.ServerVersion}}" *> $null
    return ($LASTEXITCODE -eq 0)
}

# --- Trava: ja coletou com sucesso ha pouco?
if (-not $Forcar -and (Test-Path $log)) {
    $ultimo = Select-String -Path $log -Pattern 'Fim da coleta \(c.digo 0\)' -Encoding UTF8 | Select-Object -Last 1
    if ($ultimo -and $ultimo.Line -match '(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})') {
        $quando = [datetime]::ParseExact($Matches[1], "yyyy-MM-dd HH:mm:ss", [Globalization.CultureInfo]::InvariantCulture)
        $minutos = [int]((Get-Date) - $quando).TotalMinutes
        if ($minutos -ge 0 -and $minutos -lt 240) {
            Registrar "Coleta pulada: a ultima bem-sucedida foi ha $minutos min (use -Forcar para coletar mesmo assim)."
            exit 0
        }
    }
}

Registrar "=== Início da coleta"

# --- 1. Docker e banco
if (-not (DockerNoAr)) {
    $docker = Get-Command docker -ErrorAction SilentlyContinue
    $candidatos = @()
    if ($docker) { $candidatos += Join-Path (Split-Path (Split-Path (Split-Path $docker.Source))) "Docker Desktop.exe" }
    $candidatos += "$env:LOCALAPPDATA\Programs\DockerDesktop\Docker Desktop.exe"
    $candidatos += "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
    $exe = $candidatos | Where-Object { Test-Path $_ } | Select-Object -First 1
    if ($exe) {
        Registrar "Docker parado: abrindo $exe"
        Start-Process -FilePath $exe | Out-Null
        foreach ($i in 1..36) {          # até 3 minutos
            Start-Sleep -Seconds 5
            if (DockerNoAr) { break }
        }
    }
}
if (-not (DockerNoAr)) {
    Registrar "ERRO: Docker não ficou disponível; coleta cancelada."
    exit 1
}
# via cmd: o PowerShell 5.1 trataria o que o Docker escreve no stderr como erro
cmd /c "docker compose up -d 2>&1" | Out-File -FilePath $log -Append -Encoding utf8
Start-Sleep -Seconds 3

# --- 2. Pipeline
$env:PYTHONIOENCODING = "utf-8"
cmd /c "`"$raiz\.venv\Scripts\python.exe`" -m vagas.pipeline 2>&1" | Out-File -FilePath $log -Append -Encoding utf8
$codigo = $LASTEXITCODE
Registrar "=== Fim da coleta (código $codigo)"

# --- 3. Limpeza de logs antigos
Get-ChildItem $pastaLogs -Filter "coleta-*.log" |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } |
    Remove-Item -Force -ErrorAction SilentlyContinue

exit $codigo
