@echo off
cd /d "%~dp0"
title MEGA Sync

:: ============================================================
:: 1. Trouver Python
:: ============================================================
set PYTHON=

:: Chercher python dans le PATH
where python >nul 2>&1
if not errorlevel 1 (
    set PYTHON=python
    goto :check_python_version
)

:: Chercher py launcher (installe avec Python sur Windows)
where py >nul 2>&1
if not errorlevel 1 (
    set PYTHON=py -3
    goto :check_python_version
)

:: Python introuvable
echo.
echo  ERREUR : Python n'est pas installe ou pas dans le PATH.
echo.
echo  1. Telechargez Python sur : https://www.python.org/downloads/
echo  2. IMPORTANT : Cochez "Add Python to PATH" pendant l'installation
echo  3. Relancez ce fichier run.bat
echo.
pause
exit /b 1

:check_python_version
:: Verifier version >= 3.9
for /f "tokens=2" %%v in ('%PYTHON% --version 2^>^&1') do set PY_VER=%%v
echo  Python detecte : %PY_VER%

:: ============================================================
:: 2. Creer le venv si absent
:: ============================================================
if not exist "venv\" (
    echo.
    echo  Creation de l'environnement virtuel...
    %PYTHON% -m venv venv
    if errorlevel 1 (
        echo  ERREUR : Impossible de creer l'environnement virtuel.
        pause
        exit /b 1
    )
    echo  Installation des dependances...
    venv\Scripts\pip install -r requirements.txt --quiet
    if errorlevel 1 (
        echo  ERREUR : Installation des dependances echouee.
        pause
        exit /b 1
    )
    echo  Installation terminee.
)

:: ============================================================
:: 3. Verifier rclone
:: ============================================================
where rclone >nul 2>&1
if errorlevel 1 (
    :: Chercher rclone.exe dans le dossier courant
    if exist "rclone.exe" (
        set PATH=%PATH%;%~dp0
        goto :launch
    )
    echo.
    echo  ERREUR : rclone non installe.
    echo.
    echo  1. Telechargez rclone sur : https://rclone.org/downloads/
    echo     Choisissez : Windows - amd64
    echo  2. Extrayez rclone.exe dans ce dossier : %~dp0
    echo     (ou dans C:\Windows\System32\ pour usage global)
    echo  3. Relancez run.bat
    echo.
    pause
    exit /b 1
)

:: ============================================================
:: 4. Lancer l'application
:: ============================================================
:launch
echo.
echo  Lancement de MEGA Sync...
echo.
venv\Scripts\python main.py
if errorlevel 1 (
    echo.
    echo  L'application s'est arretee avec une erreur.
    pause
)
