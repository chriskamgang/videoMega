@echo off
cd /d "%~dp0"

:: Creer le venv si absent
if not exist "venv\" (
    echo Preparation de l'environnement Python...
    python -m venv venv
    venv\Scripts\pip install -r requirements.txt
)

:: Verifier rclone
where rclone >nul 2>&1
if errorlevel 1 (
    echo rclone non installe. Telechargez-le sur https://rclone.org/downloads/
    echo Placez rclone.exe dans C:\Windows\System32 ou dans ce dossier.
    pause
    exit /b 1
)

venv\Scripts\python main.py
