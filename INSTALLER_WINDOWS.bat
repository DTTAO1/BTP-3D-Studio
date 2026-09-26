@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python n'est pas installe. Installez Python 3.11 ou 3.12 puis relancez ce fichier.
  pause
  exit /b 1
)
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
  echo Installation incomplete. Verifiez la connexion internet et relancez.
  pause
  exit /b 1
)
echo Installation terminee.
pause
