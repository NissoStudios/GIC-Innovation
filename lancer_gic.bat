@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
    echo Python est introuvable. Installez Python 3.11 ou une version plus recente.
    pause
    exit /b 1
)

py app.py
if errorlevel 1 (
    echo.
    echo L'application s'est arretee avec une erreur.
    echo Consultez data\gic_agriculture.log pour obtenir les details.
    pause
)

