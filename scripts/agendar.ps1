# Cria (ou atualiza) a tarefa diária de coleta no Agendador de Tarefas do Windows.
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\agendar.ps1 [-Horario 08:00]
# Para remover:  Unregister-ScheduledTask -TaskPath "\RadarDeVagas\" -TaskName "ColetaDiaria"

param([string]$Horario = "08:00")

$raiz = Split-Path -Parent $PSScriptRoot
$script = Join-Path $raiz "scripts\coletar.ps1"

$acao = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`"" `
    -WorkingDirectory $raiz
$gatilho = New-ScheduledTaskTrigger -Daily -At $Horario
# StartWhenAvailable: se o PC estiver desligado no horário, roda assim que ligar
$config = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskPath "\RadarDeVagas\" -TaskName "ColetaDiaria" -Action $acao -Trigger $gatilho `
    -Settings $config -Description "Radar de Vagas: coleta diária de vagas (GitHub, Adzuna, Gmail)." -Force |
    Out-Null

$info = Get-ScheduledTask -TaskPath "\RadarDeVagas\" -TaskName "ColetaDiaria" | Get-ScheduledTaskInfo
"Tarefa agendada: todo dia às $Horario. Próxima execução: $($info.NextRunTime)"
