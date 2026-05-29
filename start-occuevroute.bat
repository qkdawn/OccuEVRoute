@echo off
setlocal

set "ROOT=%~dp0"
set "PYTHON=python"
if exist "%ROOT%.venv\Scripts\python.exe" set "PYTHON=%ROOT%.venv\Scripts\python.exe"

if /I "%~1"=="--check" goto check

call :verify_tools || exit /b 1

echo Starting OccuEVRoute backend on http://127.0.0.1:9000
start "OccuEVRoute Backend" /D "%ROOT%" cmd /k ""%PYTHON%" -m uvicorn backend.main:app --host 127.0.0.1 --port 9000"

echo Starting OccuEVRoute Vite deployment on http://127.0.0.1:9090
start "OccuEVRoute Frontend" /D "%ROOT%frontend" cmd /k "if not exist node_modules (npm install) && npm run deploy"

timeout /t 5 /nobreak >nul
start "" "http://127.0.0.1:9090"
exit /b 0

:check
call :verify_tools || exit /b 1
echo OccuEVRoute launcher check passed.
exit /b 0

:verify_tools
"%PYTHON%" --version >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install Python or create .venv before running this script.
  exit /b 1
)
where npm >nul 2>nul
if errorlevel 1 (
  echo npm was not found. Install Node.js before running this script.
  exit /b 1
)
exit /b 0
