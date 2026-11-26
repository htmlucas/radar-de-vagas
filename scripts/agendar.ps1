# Cria (ou atualiza) as tarefas do Radar de Vagas no Agendador de Tarefas do Windows:
#   ColetaDiaria - coleta de vagas todo dia no horario e, como rede de seguranca, 3 min depois de fazer
#                  logon (recupera uma coleta perdida com o PC desligado).
#   Painel       - sobe o painel (http://localhost:8501) ao fazer logon, sem janela, como o Docker.
# Tambem cria o atalho "Radar de Vagas" na Area de Trabalho (inicia o painel se preciso e abre o navegador).
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\agendar.ps1 [-Horario 08:00] [-SemPainel]
#
# Remover:  Unregister-ScheduledTask -TaskPath "\RadarDeVagas\" -TaskName "ColetaDiaria" -Confirm:$false
#           Unregister-ScheduledTask -TaskPath "\RadarDeVagas\" -TaskName "Painel" -Confirm:$false
#
# COLETA DE ENGENHARIA DE DADOS (opcional, so quando pedida):
#   ColetaDados  - \RadarDeVagas\ColetaDados: todo dia as 08:20 e 8 min depois do logon (recupera uma coleta perdida),
#                  rodando scripts\coletar_dados.ps1 (log, trava e Python proprios; independente da ColetaDiaria).
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\agendar.ps1 -Dados [-HorarioDados 08:20]
#       registra (ou atualiza, sem duplicar) SOMENTE a tarefa ColetaDados. Nao toca na ColetaDiaria, no Painel nem no atalho.
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\agendar.ps1 -RemoverDados
#       remove SOMENTE a tarefa ColetaDados.
#   Sem -Dados nem -RemoverDados, este script faz exatamente o que fazia antes (nao registra a ColetaDados).

param([string]$Horario = "08:00", [switch]$SemPainel, [switch]$Dados, [string]$HorarioDados = "08:20", [switch]$RemoverDados)

$raiz = Split-Path -Parent $PSScriptRoot
$coletar = Join-Path $raiz "scripts\coletar.ps1"
$painel = Join-Path $raiz "scripts\painel.ps1"
$caminho = "\RadarDeVagas\"
$usuario = "$env:USERDOMAIN\$env:USERNAME"
$base = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File"

# ---------------------------------------------------------------- coleta de Engenharia de Dados (so com -Dados / -RemoverDados)
# Termina aqui (return): o restante do script, que cuida da ColetaDiaria, do Painel e do atalho, nao roda.
if ($RemoverDados) {
    Unregister-ScheduledTask -TaskPath $caminho -TaskName "ColetaDados" -Confirm:$false -ErrorAction SilentlyContinue
    "Tarefa ColetaDados removida (se existia). Nada mais foi alterado."
    return
}
if ($Dados) {
    $coletarDados = Join-Path $raiz "scripts\coletar_dados.ps1"
    if (-not (Test-Path $coletarDados)) { throw "Script nao encontrado: $coletarDados" }
    $acaoDados = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "$base `"$coletarDados`"" -WorkingDirectory $raiz
    $diarioDados = New-ScheduledTaskTrigger -Daily -At $HorarioDados
    $aoLogarDados = New-ScheduledTaskTrigger -AtLogOn -User $usuario
    $aoLogarDados.Delay = "PT8M"       # depois da ColetaDiaria (que roda 3 min apos o logon)
    # StartWhenAvailable: PC desligado no horario? roda ao ligar. IgnoreNew: nunca duas copias desta tarefa ao mesmo tempo.
    $configDados = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -MultipleInstances IgnoreNew
    $descDados = "Radar de Vagas: coleta diaria de vagas de Engenharia de Dados (GitHub, Adzuna, Gmail). Independente da ColetaDiaria."
    try {
        Register-ScheduledTask -TaskPath $caminho -TaskName "ColetaDados" -Action $acaoDados `
            -Trigger @($diarioDados, $aoLogarDados) -Settings $configDados -Description $descDados -Force -ErrorAction Stop | Out-Null
        $logonDados = $true
    } catch {
        Write-Warning "O Windows nao aceitou o gatilho 'ao fazer logon' (precisa de permissao): registrando so o horario diario."
        Register-ScheduledTask -TaskPath $caminho -TaskName "ColetaDados" -Action $acaoDados -Trigger $diarioDados `
            -Settings $configDados -Description $descDados -Force | Out-Null
        $logonDados = $false
    }
    $infoDados = Get-ScheduledTask -TaskPath $caminho -TaskName "ColetaDados" | Get-ScheduledTaskInfo
    "Coleta de dados: todo dia as $HorarioDados" + $(if ($logonDados) { " e 8 min depois de fazer logon" } else { "" }) +
        ". Proxima execucao: $($infoDados.NextRunTime)"
    return
}

# ---------------------------------------------------------------- coleta
$acaoColeta = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "$base `"$coletar`"" -WorkingDirectory $raiz
$diario = New-ScheduledTaskTrigger -Daily -At $Horario
$aoLogar = New-ScheduledTaskTrigger -AtLogOn -User $usuario
$aoLogar.Delay = "PT3M"
# StartWhenAvailable: se o PC estiver desligado no horario, roda assim que ligar
$configColeta = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$descColeta = "Radar de Vagas: coleta diaria de vagas (GitHub, Adzuna, Gmail)."

try {
    Register-ScheduledTask -TaskPath $caminho -TaskName "ColetaDiaria" -Action $acaoColeta `
        -Trigger @($diario, $aoLogar) -Settings $configColeta -Description $descColeta -Force -ErrorAction Stop | Out-Null
    $gatilhoLogon = $true
} catch {
    Write-Warning "O Windows nao aceitou o gatilho 'ao fazer logon' (precisa de permissao): registrando so o horario diario."
    Register-ScheduledTask -TaskPath $caminho -TaskName "ColetaDiaria" -Action $acaoColeta -Trigger $diario `
        -Settings $configColeta -Description $descColeta -Force | Out-Null
    $gatilhoLogon = $false
}
$info = Get-ScheduledTask -TaskPath $caminho -TaskName "ColetaDiaria" | Get-ScheduledTaskInfo
"Coleta: todo dia as $Horario" + $(if ($gatilhoLogon) { " e 3 min depois de fazer logon" } else { "" }) +
    ". Proxima execucao: $($info.NextRunTime)"

# ---------------------------------------------------------------- painel
$desktop = [Environment]::GetFolderPath("Desktop")
$arqAtalho = Join-Path $desktop "Radar de Vagas.lnk"

if ($SemPainel) {
    Unregister-ScheduledTask -TaskPath $caminho -TaskName "Painel" -Confirm:$false -ErrorAction SilentlyContinue
    Remove-Item $arqAtalho -Force -ErrorAction SilentlyContinue
    "Painel automatico desligado (tarefa e atalho removidos, se existiam)."
    return
}

$acaoPainel = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "$base `"$painel`"" -WorkingDirectory $raiz
$gatilhoPainel = New-ScheduledTaskTrigger -AtLogOn -User $usuario
# Sem limite de tempo (o painel fica no ar), reinicia se cair e nao abre um segundo
$configPainel = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
try {
    Register-ScheduledTask -TaskPath $caminho -TaskName "Painel" -Action $acaoPainel -Trigger $gatilhoPainel `
        -Settings $configPainel -Description "Radar de Vagas: painel em http://localhost:8501 (inicia ao fazer logon)." `
        -Force -ErrorAction Stop | Out-Null
    "Painel: inicia sozinho ao fazer logon, em http://localhost:8501."
} catch {
    Write-Warning "Nao foi possivel registrar a tarefa do painel: $($_.Exception.Message)"
}

$sh = New-Object -ComObject WScript.Shell
$atalho = $sh.CreateShortcut($arqAtalho)
$atalho.TargetPath = "powershell.exe"
$atalho.Arguments = "$base `"$painel`" -AbrirNavegador"
$atalho.WorkingDirectory = $raiz
$atalho.WindowStyle = 7                 # minimizada
$atalho.IconLocation = "shell32.dll,13"
$atalho.Description = "Abre o Radar de Vagas (inicia o painel se estiver desligado)."
$atalho.Save()
"Atalho criado: $arqAtalho"
