@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

set "PY=python"
where py >nul 2>nul && set "PY=py"

echo [1/3] Instalando dependencias / Installing dependencies...
%PY% -m pip install --upgrade pip
%PY% -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto erro

echo.
echo [2/3] Gerando o EXE / Building the EXE...
%PY% -m PyInstaller --noconsole --onefile --clean --name MonitorController --icon assets\icon.ico --add-data "assets;assets" --collect-all customtkinter --collect-submodules monitorcontrol monitor_controller.py
if errorlevel 1 goto erro

echo.
echo [3/3] Pronto / Done!
echo EXE: %~dp0dist\MonitorController.exe
explorer "%~dp0dist"
pause
exit /b 0

:erro
echo.
echo ERRO no build. Confira se o Python esta instalado e no PATH.
echo BUILD ERROR. Check that Python is installed and on PATH.
pause
exit /b 1
