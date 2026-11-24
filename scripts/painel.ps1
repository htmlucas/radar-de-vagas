# Inicia o painel (Streamlit) em http://localhost:8501.
# Usado pela tarefa "Painel" (ao fazer logon no Windows) e pelo atalho "Radar de Vagas" da Area de Trabalho.
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\painel.ps1 [-AbrirNavegador]
#
# 1. Se o painel ja estiver no ar (porta 8501), nao inicia outro.
# 2. Espera o banco responder (no logon o Docker pode ainda estar subindo; ate 3 minutos).
# 3. Sobe o Streamlit sem janela, com log em dados\logs\painel.log.
#    O script fica rodando enquanto o painel estiver no ar.
# -AbrirNavegador: inicia o painel se preciso, espera ele responder e abre o navegador.

param([switch]$AbrirNavegador, [int]$Porta = 8501)

$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz
$url = "http://localhost:$Porta"

$pastaLogs = Join-Path $raiz "dados\logs"
New-Item -ItemType Directory -Force -Path $pastaLogs | Out-Null
$log = Join-Path $pastaLogs "painel.log"
if ((Test-Path $log) -and ((Get-Item $log).Length -gt 5MB)) { Remove-Item $log -Force }

function Registrar([string]$texto) {
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $texto" | Out-File -FilePath $log -Append -Encoding utf8
}

function PortaAberta([int]$p) {
    $c = New-Object System.Net.Sockets.TcpClient
    try { $c.Connect("127.0.0.1", $p); return $true }
    catch { return $false }
    finally { $c.Close() }
}

# --- Atalho da Area de Trabalho: inicia (se preciso) e abre o navegador
if ($AbrirNavegador) {
    if (-not (PortaAberta $Porta)) {
        Start-Process -FilePath "powershell.exe" -WindowStyle Hidden -ArgumentList @(
            "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$PSCommandPath`"", "-Porta", $Porta)
        foreach ($i in 1..90) {           # espera o painel responder (ate ~3 min)
            Start-Sleep -Seconds 2
            if (PortaAberta $Porta) { break }
        }
    }
    Start-Process $url
    exit 0
}

if (PortaAberta $Porta) { exit 0 }        # ja esta no ar

# --- Porta do banco (POSTGRES_PORT no .env; padrao 5440)
$portaBanco = 5440
$envArq = Join-Path $raiz ".env"
if (Test-Path $envArq) {
    $linha = Select-String -Path $envArq -Pattern '^\s*POSTGRES_PORT\s*=\s*(\d+)' | Select-Object -First 1
    if ($linha) { $portaBanco = [int]$linha.Matches[0].Groups[1].Value }
}

Registrar "=== Iniciando o painel em $url"
foreach ($i in 1..36) {                    # ate 3 minutos esperando o banco
    if (PortaAberta $portaBanco) { break }
    if ($i -eq 1) { Registrar "Aguardando o banco na porta $portaBanco..." }
    Start-Sleep -Seconds 5
}
if (-not (PortaAberta $portaBanco)) {
    Registrar "AVISO: o banco ainda nao responde; o painel sobe mesmo assim e mostra erro ate o banco voltar."
}

$env:PYTHONIOENCODING = "utf-8"
$py = Join-Path $raiz ".venv\Scripts\python.exe"
# via cmd: o PowerShell 5.1 trataria o que o Streamlit escreve no stderr como erro
cmd /c "`"$py`" -m streamlit run vagas/painel/app.py --server.port $Porta --server.headless true >> `"$log`" 2>&1"
$codigo = $LASTEXITCODE
Registrar "=== Painel encerrado (codigo $codigo)"
exit $codigo
