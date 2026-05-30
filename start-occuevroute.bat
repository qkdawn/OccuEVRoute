@echo off
setlocal

set "ROOT=%~dp0"
set "PYTHON=python"
if exist "%ROOT%.venv\Scripts\python.exe" set "PYTHON=%ROOT%.venv\Scripts\python.exe"

if /I "%~1"=="--check" goto check
if /I "%~1"=="backend" goto backend
if /I "%~1"=="frontend" goto frontend

call :verify_tools || exit /b 1

call :port_listening 9000
if errorlevel 1 (
  echo Starting OccuEVRoute backend on http://127.0.0.1:9000
  start "OccuEVRoute Backend" cmd /k ""%~f0" backend"
) else (
  echo OccuEVRoute backend is already listening on http://127.0.0.1:9000
)

call :wait_http "http://127.0.0.1:9000/api/health" 60 "backend health"
if errorlevel 1 exit /b 1
call :wait_http "http://127.0.0.1:9000/api/boundary" 60 "backend boundary data"
if errorlevel 1 exit /b 1

call :port_listening 9090
if errorlevel 1 (
  echo Starting OccuEVRoute Vite deployment on http://127.0.0.1:9090
  start "OccuEVRoute Frontend" cmd /k ""%~f0" frontend"
) else (
  echo OccuEVRoute frontend is already listening on http://127.0.0.1:9090
)

call :wait_http "http://127.0.0.1:9090" 60 "frontend preview"
if errorlevel 1 exit /b 1
start "" "http://127.0.0.1:9090"
exit /b 0

:backend
cd /d "%ROOT%"
"%PYTHON%" -m uvicorn backend.main:app --host 127.0.0.1 --port 9000
exit /b %errorlevel%

:frontend
cd /d "%ROOT%frontend"
if not exist node_modules call npm install
call npm run deploy
exit /b %errorlevel%

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

:port_listening
powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort %~1 -State Listen -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }" >nul 2>nul
exit /b %errorlevel%

:wait_http
echo Waiting for %~3...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$url = '%~1'; $timeoutSeconds = [int]'%~2'; $deadline = (Get-Date).AddSeconds($timeoutSeconds); do { try { $response = Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 3; if ([int]$response.StatusCode -ge 200 -and [int]$response.StatusCode -lt 300) { exit 0 } } catch { Start-Sleep -Seconds 1 } } while ((Get-Date) -lt $deadline); exit 1" >nul 2>nul
if errorlevel 1 (
  echo Timed out waiting for %~3 at %~1.
  exit /b 1
)
echo %~3 is ready.
exit /b 0
