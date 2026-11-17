@echo off
rem MTG Commander Deck Tester - Windows launcher. Double-click this file.
setlocal
cd /d "%~dp0"
title MTG Commander Deck Tester

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
  python -c "import sys" >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo Python 3 is not installed.
  echo Install it from https://www.python.org/downloads/windows/
  echo and tick "Add python.exe to PATH" in the installer. Then start this file again.
  pause
  exit /b 1
)
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" || (
  echo Python 3.9 or newer is needed. Install it from https://www.python.org/downloads/windows/
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo First start: setting things up, about a minute...
  %PY% -m venv .venv || (
    echo Could not create the Python environment.
    pause
    exit /b 1
  )
)
fc /b requirements.txt .venv\requirements.installed >nul 2>nul || (
  echo Installing required packages...
  ".venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -r requirements.txt || (
    echo Installing packages failed. Check your internet connection and try again.
    pause
    exit /b 1
  )
  copy /y requirements.txt .venv\requirements.installed >nul
)

".venv\Scripts\python.exe" -m mtg_deck_tester %*
pause
