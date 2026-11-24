@echo off
chcp 65001 >nul
title Pronutre - instalar o programa do computador servidor
cd /d "%~dp0"
net session >nul 2>&1 || (echo Clique com o botao direito em instalar.bat e escolha "Executar como administrador". & pause & exit /b 1)
where pythonw >nul 2>nul || (echo O Python nao esta instalado. Instale o Python 3 em python.org marcando "Add python.exe to PATH" e rode de novo. & pause & exit /b 1)
if not exist config.ini (
  copy config.exemplo.ini config.ini >nul
  echo Preencha o config.ini que vai abrir agora, salve e rode o instalar.bat de novo.
  notepad config.ini
  exit /b 1
)
echo Testando o acesso ao ERP Pronutre...
python servidor_pronutre.py --teste || (echo. & echo Nao consegui entrar. Confira e-mail e senha no config.ini. & pause & exit /b 1)
set "PYW="
for /f "usebackq delims=" %%p in (`python -c "import sys,os;print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))"`) do set "PYW=%%p"
if not exist "%PYW%" (echo Nao achei o pythonw.exe do Python. & pause & exit /b 1)
schtasks /Create /TN "Pronutre - computador servidor" /TR "\"%PYW%\" \"%~dp0servidor_pronutre.py\"" /SC MINUTE /MO 5 /RU SYSTEM /RL HIGHEST /F >nul
if errorlevel 1 (echo Nao consegui criar a tarefa agendada. & pause & exit /b 1)
schtasks /Run /TN "Pronutre - computador servidor" >nul
echo.
echo Pronto. O programa roda sozinho (o Windows confere a cada 5 minutos se ele esta ligado).
echo Registro em logs\servidor.log dentro da pasta do config.ini.
pause
