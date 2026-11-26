# SIMULADOR do Agendador de Tarefas, so para testes: define funcoes com o nome dos cmdlets (que tem prioridade sobre
# os cmdlets de verdade) e executa scripts\agendar.ps1 com elas. Nenhuma tarefa real e criada, alterada ou removida.
# Cada chamada fica registrada no arquivo de estado (JSON), que o teste le.
# Opcoes do agendar.ps1 como lista separada por virgula, sem hifen: "Dados,HorarioDados=09:15" vira -Dados -HorarioDados 09:15.
param([string]$Alvo, [string]$ArquivoEstado, [string]$Opcoes = "", [switch]$FalharLogon)
$argsAgendar = ($Opcoes -split "," | Where-Object { $_ } | ForEach-Object {
    if ($_ -match "=") { $p = $_ -split "=", 2; "-$($p[0]) $($p[1])" } else { "-$_" } }) -join " "

$ErrorActionPreference = "Stop"
$global:estadoSimulado = @{ chamadas = @(); tarefas = @{} }
if (Test-Path $ArquivoEstado) {
    $antigo = Get-Content $ArquivoEstado -Raw | ConvertFrom-Json
    $global:estadoSimulado.chamadas = @($antigo.chamadas)
    foreach ($t in $antigo.tarefas.PSObject.Properties) { $global:estadoSimulado.tarefas[$t.Name] = $t.Value }
}
function Salvar { $global:estadoSimulado | ConvertTo-Json -Depth 8 | Set-Content -Path $ArquivoEstado -Encoding utf8 }
function Anotar($nome, $dados) { $global:estadoSimulado.chamadas += @{ cmdlet = $nome; dados = $dados }; Salvar }

function New-ScheduledTaskAction {
    [CmdletBinding()] param($Execute, $Argument, $WorkingDirectory)
    [pscustomobject]@{ Execute = $Execute; Argument = $Argument; WorkingDirectory = $WorkingDirectory }
}
function New-ScheduledTaskTrigger {
    [CmdletBinding()] param([switch]$Daily, [switch]$AtLogOn, $At, $User)
    [pscustomobject]@{ Tipo = $(if ($Daily) { "Diario" } else { "Logon" }); At = $At; User = $User; Delay = $null }
}
function New-ScheduledTaskSettingsSet {
    [CmdletBinding()] param([switch]$StartWhenAvailable, [switch]$RunOnlyIfNetworkAvailable, $ExecutionTimeLimit,
        [switch]$AllowStartIfOnBatteries, [switch]$DontStopIfGoingOnBatteries, $MultipleInstances, $RestartCount, $RestartInterval)
    [pscustomobject]@{ StartWhenAvailable = [bool]$StartWhenAvailable; RunOnlyIfNetworkAvailable = [bool]$RunOnlyIfNetworkAvailable
        ExecutionTimeLimitMin = $(if ($ExecutionTimeLimit) { $ExecutionTimeLimit.TotalMinutes } else { $null })
        AllowStartIfOnBatteries = [bool]$AllowStartIfOnBatteries; DontStopIfGoingOnBatteries = [bool]$DontStopIfGoingOnBatteries
        MultipleInstances = "$MultipleInstances" }
}
function Register-ScheduledTask {
    [CmdletBinding()] param($TaskPath, $TaskName, $Action, $Trigger, $Settings, $Description, [switch]$Force)
    $gatilhos = @($Trigger)
    $registro = @{ TaskPath = $TaskPath; TaskName = $TaskName; Force = [bool]$Force; Description = $Description
                   Action = $Action; Triggers = $gatilhos; Settings = $Settings }
    if ($FalharLogon -and $gatilhos.Count -gt 1) { Anotar "Register-ScheduledTask(recusada)" $registro; throw "gatilho de logon recusado (simulado)" }
    $chave = "$TaskPath$TaskName"
    if ($global:estadoSimulado.tarefas.ContainsKey($chave) -and -not $Force) { throw "a tarefa ja existe (simulado)" }
    $global:estadoSimulado.tarefas[$chave] = $registro
    Anotar "Register-ScheduledTask" $registro
}
function Unregister-ScheduledTask {
    [CmdletBinding()] param($TaskPath, $TaskName, [switch]$Confirm)
    $global:estadoSimulado.tarefas.Remove("$TaskPath$TaskName")
    Anotar "Unregister-ScheduledTask" @{ TaskPath = $TaskPath; TaskName = $TaskName }
}
function Get-ScheduledTask {
    [CmdletBinding()] param($TaskPath, $TaskName)
    Anotar "Get-ScheduledTask" @{ TaskPath = $TaskPath; TaskName = $TaskName }
    [pscustomobject]@{ TaskName = $TaskName }
}
function Get-ScheduledTaskInfo {
    [CmdletBinding()] param([Parameter(ValueFromPipeline = $true)]$Tarefa)
    process { [pscustomobject]@{ NextRunTime = (Get-Date "2026-12-01 08:20") } }
}

# Trava de seguranca: se algum simulador nao estiver valendo, NAO executa (para nao tocar no Agendador de verdade).
foreach ($nome in "Register-ScheduledTask", "Unregister-ScheduledTask", "Get-ScheduledTask", "New-ScheduledTaskTrigger",
                  "New-ScheduledTaskAction", "New-ScheduledTaskSettingsSet", "Get-ScheduledTaskInfo") {
    if ((Get-Command $nome).CommandType -ne "Function") { throw "simulador nao instalado para ${nome} - abortado" }
}
Salvar
Invoke-Expression "& `"$Alvo`" $argsAgendar"
