@echo off
rem ---------------------------------------------------------------------------
rem  Session TUI - Windows build
rem  Builds dist\session-tui.exe: one file, runs without Python installed.
rem  Needs only Python 3.10+ (https://www.python.org/downloads/).
rem
rem    build.bat            build the .exe
rem    build.bat test       run the offline tests first, then build
rem ---------------------------------------------------------------------------
setlocal
cd /d "%~dp0"

set "PY=python"
where py >nul 2>nul && set "PY=py -3"
%PY% -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>nul
if errorlevel 1 (
    echo Python 3.10 or newer is required: https://www.python.org/downloads/
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [1/4] creating the virtual environment .venv ...
    %PY% -m venv .venv || goto :failed
) else (
    echo [1/4] using the existing .venv
)
set "VENV_PY=.venv\Scripts\python.exe"

echo [2/4] installing dependencies ...
"%VENV_PY%" -m pip install --quiet --disable-pip-version-check -r requirements.txt -r requirements-build.txt || goto :failed

if /i "%~1"=="test" (
    echo [3/4] running the offline tests ...
    "%VENV_PY%" selftest.py || goto :failed
) else (
    echo [3/4] tests skipped ^(use "build.bat test" to run them^)
)

echo [4/4] building dist\session-tui.exe ...
"%VENV_PY%" build_exe.py || goto :failed

echo.
echo done: dist\session-tui.exe
echo try:  dist\session-tui.exe --help
exit /b 0

:failed
echo.
echo build failed
exit /b 1
