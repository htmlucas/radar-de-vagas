# Coleta de vagas de Engenharia de Dados (usado pela tarefa \RadarDeVagas\ColetaDados; tambem pode rodar a mao).
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\coletar_dados.ps1 [-Forcar] [-DryRun]
#
# 1. Garante que o Docker e o banco estejam no ar (abre o Docker Desktop se estiver fechado).
# 2. Roda `python -m vagas.trilhas.dados.pipeline` com o Python da .venv do projeto.
# 3. Grava tudo em dados\logs\dados-coleta-AAAA-MM-DD.log (apaga logs dados-coleta-* com mais de 30 dias).
#
# INDEPENDENTE DA COLETA LARAVEL (scripts\coletar.ps1):
#   - log proprio (dados-coleta-*.log; o nome nao casa com coleta-*.log, que e da Laravel);
#   - trava propria (abaixo); a trava de 4 horas da Laravel nem e lida nem alterada;
#   - uma falha aqui so afeta esta tarefa: nada da coleta Laravel e tocado.
#
# TRAVA (evita rodar duas vezes quando ha o gatilho diario e o de logon):
#   1. Se a ultima coleta de dados TERMINOU COM SUCESSO ha menos de 4 horas (arquivo dados\logs\dados-coleta-ok.txt),
#      esta execucao e pulada (codigo 0). -Forcar ignora isso.
#   2. Se outra execucao esta rodando agora (arquivo dados\logs\dados-coleta.lock com o PID de um processo vivo,
#      com menos de 90 min), esta execucao e pulada (codigo 0). O -Forcar NAO ignora esta: nunca ha duas ao mesmo tempo.
#      Trava de processo morto ou com mais de 90 min e considerada velha e removida.
#   3. A marca de sucesso so e gravada quando o pipeline termina com codigo 0. Falhou? Nada e gravado e a proxima
#      tentativa (por exemplo, o gatilho de logon) roda normalmente.
#
# CODIGOS DE SAIDA: 0 = coletou ou pulou pela trava | 1 = Docker/banco indisponivel ou erro inesperado
#                   2 = Python da .venv nao encontrado | outro = codigo de saida do pipeline.
#
# -DryRun mostra o que seria usado (Python, pasta, log, trava) sem rodar nada e sem criar arquivos.
# Parametros para testes (a tarefa agendada nao usa): -Raiz (pasta do projeto), -Python (executavel), -SemDocker.

param([switch]$Forcar, [switch]$DryRun, [string]$Raiz = "", [string]$Python = "", [switch]$SemDocker)

$ErrorActionPreference = "Continue"
$raiz = if ($Raiz) { $Raiz } else { Split-Path -Parent $PSScriptRoot }
$pythonExe = if ($Python) { $Python } else { Join-Path $raiz ".venv\Scripts\python.exe" }
$pastaLogs = Join-Path $raiz "dados\logs"
$log = Join-Path $pastaLogs ("dados-coleta-" + (Get-Date -Format "yyyy-MM-dd") + ".log")
$marcaOk = Join-Path $pastaLogs "dados-coleta-ok.txt"
$trava = Join-Path $pastaLogs "dados-coleta.lock"
$janelaMinutos = 240      # sucesso recente: nao coleta de novo
$travaMaxMinutos = 90     # trava mais velha que isso e considerada abandonada
$modulo = "vagas.trilhas.dados.pipeline"

if ($DryRun) {
    "Raiz (diretorio de trabalho): $raiz"
    "Python: $pythonExe (existe: $(Test-Path $pythonExe))"
    "Comando: `"$pythonExe`" -m $modulo"
    "Log: $log"
    "Marca de sucesso: $marcaOk"
    "Trava de execucao: $trava"
    "Janela de sucesso: $janelaMinutos min | trava abandonada apos: $travaMaxMinutos min"
    exit 0
}

New-Item -ItemType Directory -Force -Path $pastaLogs | Out-Null

function Registrar([string]$texto) {
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $texto" | Out-File -FilePath $log -Append -Encoding utf8
}

function SucessoRecente {
    if ($Forcar -or -not (Test-Path $marcaOk)) { return $false }
    try {
        $quando = [datetime]::Parse((Get-Content $marcaOk -TotalCount 1), [Globalization.CultureInfo]::InvariantCulture)
    } catch { return $false }
    $minutos = [int]((Get-Date) - $quando).TotalMinutes
    if ($minutos -ge 0 -and $minutos -lt $janelaMinutos) {
        Registrar "Coleta de dados pulada: a ultima bem-sucedida foi ha $minutos min (use -Forcar para coletar mesmo assim)."
        return $true
    }
    return $false
}

function AdquirirTrava {
    if (Test-Path $trava) {
        $pidAntigo = 0
        [void][int]::TryParse(([string](Get-Content $trava -TotalCount 1 -ErrorAction SilentlyContinue)).Trim(), [ref]$pidAntigo)
        $idade = ((Get-Date) - (Get-Item $trava).LastWriteTime).TotalMinutes
        $vivo = ($pidAntigo -gt 0) -and [bool](Get-Process -Id $pidAntigo -ErrorAction SilentlyContinue)
        if ($vivo -and $idade -lt $travaMaxMinutos) { return $false }
        Registrar "Trava antiga removida (processo $pidAntigo inativo ou mais de $travaMaxMinutos min)."
        Remove-Item $trava -Force -ErrorAction SilentlyContinue
    }
    try {
        # CreateNew e atomico: se duas execucoes chegam juntas, so uma consegue criar o arquivo
        $arq = [System.IO.File]::Open($trava, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::Read)
        $bytes = [Text.Encoding]::ASCII.GetBytes("$PID`r`n$(Get-Date -Format o)")
        $arq.Write($bytes, 0, $bytes.Length)
        $arq.Close()
        return $true
    } catch { return $false }
}

function LiberarTrava { Remove-Item $trava -Force -ErrorAction SilentlyContinue }

function DockerNoAr {
    docker info --format "{{.ServerVersion}}" *> $null
    return ($LASTEXITCODE -eq 0)
}

function GarantirDocker {
    if (DockerNoAr) { return $true }
    $docker = Get-Command docker -ErrorAction SilentlyContinue
    $candidatos = @()
    if ($docker) { $candidatos += Join-Path (Split-Path (Split-Path (Split-Path $docker.Source))) "Docker Desktop.exe" }
    $candidatos += "$env:LOCALAPPDATA\Programs\DockerDesktop\Docker Desktop.exe"
    $candidatos += "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
    $exe = $candidatos | Where-Object { Test-Path $_ } | Select-Object -First 1
    if ($exe) {
        Registrar "Docker parado: abrindo $exe"
        Start-Process -FilePath $exe | Out-Null
        foreach ($i in 1..36) {          # ate 3 minutos
            Start-Sleep -Seconds 5
            if (DockerNoAr) { break }
        }
    }
    return (DockerNoAr)
}

# --- trava de sucesso recente, depois trava de execucao
if (SucessoRecente) { exit 0 }
if (-not (AdquirirTrava)) {
    Registrar "Coleta de dados pulada: ja ha outra execucao em andamento (trava dados-coleta.lock)."
    exit 0
}

$codigo = 1
try {
    if (SucessoRecente) { $codigo = 0 }       # outra execucao terminou enquanto esperavamos a trava
    else {
        Registrar "=== Inicio da coleta de dados"
        Registrar "Diretorio de trabalho: $raiz"
        Registrar "Python: $pythonExe"
        Set-Location $raiz
        if (-not (Test-Path $pythonExe)) {
            Registrar "ERRO: Python da .venv nao encontrado: $pythonExe"
            $codigo = 2
        }
        elseif (-not $SemDocker -and -not (GarantirDocker)) {
            Registrar "ERRO: Docker nao ficou disponivel; coleta de dados cancelada."
            $codigo = 1
        }
        else {
            if (-not $SemDocker) {
                # via cmd: o PowerShell 5.1 trataria o que o Docker escreve no stderr como erro
                cmd /c "docker compose up -d 2>&1" | Out-File -FilePath $log -Append -Encoding utf8
                Start-Sleep -Seconds 3
            }
            $env:PYTHONIOENCODING = "utf-8"
            cmd /c "`"$pythonExe`" -m $modulo 2>&1" | Out-File -FilePath $log -Append -Encoding utf8
            $codigo = $LASTEXITCODE
            if ($codigo -eq 0) { Get-Date -Format o | Set-Content -Path $marcaOk -Encoding ascii }
        }
        Registrar "=== Fim da coleta de dados (codigo $codigo)"
    }
} catch {
    Registrar "ERRO inesperado: $($_.Exception.Message)"
    $codigo = 1
} finally {
    LiberarTrava
}

# --- limpeza de logs antigos (so os desta trilha)
Get-ChildItem $pastaLogs -Filter "dados-coleta-*.log" -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } |
    Remove-Item -Force -ErrorAction SilentlyContinue

exit $codigo
