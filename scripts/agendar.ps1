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

param([string]$Horario = "08:00", [switch]$SemPainel)

$raiz = Split-Path -Parent $PSScriptRoot
$coletar = Join-Path $raiz "scripts\coletar.ps1"
$painel = Join-Path $raiz "scripts\painel.ps1"
$caminho = "\RadarDeVagas\"
$usuario = "$env:USERDOMAIN\$env:USERNAME"
$base = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File"

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
