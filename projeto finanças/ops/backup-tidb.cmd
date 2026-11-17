@echo off
rem Backup diário do TiDB, para o Agendador de Tarefas do Windows.
rem Tudo o que é segredo mora em %USERPROFILE%\backups-financas, fora do
rem repositório: tidb.env (usuário só de leitura) e backup.frase (cifra).
rem Roteiro em ops\BACKUP.md, seção "TiDB na nuvem".

setlocal
set "PASTA=%USERPROFILE%\backups-financas"
set "FIN_BACKUP_DIR=%PASTA%"
set "FIN_BACKUP_SENHA_ARQUIVO=%PASTA%\backup.frase"
if not defined FIN_MYSQL_BIN set "FIN_MYSQL_BIN=C:\laragon\bin\mysql\mysql-8.4.3-winx64\bin"
if not defined FIN_GPG set "FIN_GPG=C:\Program Files\Git\usr\bin\gpg.exe"
set "PYTHONIOENCODING=utf-8"

cd /d "%~dp0.."
echo [%date% %time%] >> "%PASTA%\backup.log"
"..\.venv\Scripts\python.exe" ops\backup.py fazer --origem "%PASTA%\tidb.env" >> "%PASTA%\backup.log" 2>&1
exit /b %errorlevel%
