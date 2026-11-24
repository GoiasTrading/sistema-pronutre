@echo off
chcp 65001 >nul
title Pronutre - marcar o HD externo da copia de seguranca
cd /d "%~dp0"
echo Ligue o HD externo, espere aparecer em "Este Computador" e digite a letra dele (ex.: E).
set "L="
set /p L= Letra do HD externo: 
set "L=%L::=%"
if "%L%"=="" (echo Nenhuma letra digitada. & pause & exit /b 1)
if /i "%L%"=="C" (echo Escolha o HD externo, nao o disco C. & pause & exit /b 1)
if not exist "%L%:\" (echo A unidade %L%: nao foi encontrada. & pause & exit /b 1)
echo HD da copia de seguranca da Pronutre. Nao apague este arquivo.> "%L%:\PRONUTRE-BACKUP.txt"
echo HD marcado. Fazendo a primeira copia agora (demora mais na primeira vez)...
python servidor_pronutre.py --hd
echo Daqui em diante, sempre que este HD estiver ligado, a copia e feita sozinha (no maximo 1 vez por hora).
pause
