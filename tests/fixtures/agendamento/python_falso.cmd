@echo off
rem Python FALSO para testar scripts\coletar_dados.ps1: nao roda nada de verdade. Anota a pasta de trabalho e os argumentos
rem em %FALSO_REGISTRO%, escreve uma linha na saida (que vai para o log) e sai com o codigo de %FALSO_CODIGO%.
rem %FALSO_ESPERA% (segundos, opcional) simula uma coleta demorada.
echo CWD=%CD% ARGS=%* >> "%FALSO_REGISTRO%"
echo saida do python falso: %*
if defined FALSO_ESPERA ping -n %FALSO_ESPERA% 127.0.0.1 >nul
if defined FALSO_CODIGO exit /b %FALSO_CODIGO%
exit /b 0
