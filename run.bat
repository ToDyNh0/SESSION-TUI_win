@echo off
rem ---------------------------------------------------------------------------
rem  Session TUI - run from source, no build needed.
rem  The first run creates .venv and installs the dependencies.
rem
rem    run.bat                     opens the TUI
rem    run.bat send 05ab... "hi"   any command, same as session-tui.exe
rem ---------------------------------------------------------------------------
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    set "PY=python"
    where py >nul 2>nul && set "PY=py -3"
    call :setup || exit /b 1
)
".venv\Scripts\python.exe" main.py %*
exit /b %errorlevel%

:setup
%PY% -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>nul
if errorlevel 1 (
    echo Python 3.10 or newer is required: https://www.python.org/downloads/
    exit /b 1
)
echo first run: creating .venv and installing dependencies ...
%PY% -m venv .venv || exit /b 1
".venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -r requirements.txt || exit /b 1
exit /b 0
