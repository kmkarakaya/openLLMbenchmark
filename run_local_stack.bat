@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
set "REPO_ROOT=%SCRIPT_DIR%"
set "FRONTEND_DIR=%REPO_ROOT%\frontend"

set "DEFAULT_BACKEND_PORT=8000"
set "DEFAULT_FRONTEND_PORT=3001"
set "MAX_FRONTEND_SCAN=25"

set "MODE=%~1"
if /I "%MODE%"=="backend" goto :backend_mode
if /I "%MODE%"=="frontend" goto :frontend_mode
if /I "%MODE%"=="help" goto :usage
if /I "%MODE%"=="-h" goto :usage
if /I "%MODE%"=="--help" goto :usage

set "BACKEND_PORT=%DEFAULT_BACKEND_PORT%"
set "FRONTEND_PORT=%DEFAULT_FRONTEND_PORT%"
if not "%~1"=="" set "BACKEND_PORT=%~1"
if not "%~2"=="" set "FRONTEND_PORT=%~2"

if not exist "%REPO_ROOT%\api.py" (
  echo [ERROR] api.py not found. Run this script from the repository root.
  exit /b 1
)

if not exist "%FRONTEND_DIR%\package.json" (
  echo [ERROR] frontend\package.json not found.
  exit /b 1
)

set "BACKEND_ALREADY_RUNNING=0"
call :is_port_in_use %BACKEND_PORT%
if "%ERRORLEVEL%"=="0" (
  set "BACKEND_ALREADY_RUNNING=1"
  echo [INFO] Backend port %BACKEND_PORT% is already in use. Reusing existing backend.
) else (
  echo [INFO] Starting backend API window...
  start "openLLMbenchmark API" "%ComSpec%" /k ""%~f0" backend %BACKEND_PORT%"
  timeout /t 2 /nobreak >nul
  call :is_port_in_use %BACKEND_PORT%
  if not "%ERRORLEVEL%"=="0" (
    echo [WARN] Backend did not open port %BACKEND_PORT% yet. Check the backend window for errors.
  )
)

set /a "SCAN_COUNT=0"
:find_frontend_port
call :is_port_in_use %FRONTEND_PORT%
if "%ERRORLEVEL%"=="0" (
  set /a "SCAN_COUNT+=1"
  if %SCAN_COUNT% GTR %MAX_FRONTEND_SCAN% (
    echo [ERROR] Could not find a free frontend port after %MAX_FRONTEND_SCAN% attempts.
    echo [INFO] Try: run_local_stack.bat %BACKEND_PORT% 3100
    exit /b 1
  )
  set /a "FRONTEND_PORT+=1"
  goto :find_frontend_port
)

echo [INFO] Starting frontend UI window...
start "openLLMbenchmark UI" "%ComSpec%" /k ""%~f0" frontend %BACKEND_PORT% %FRONTEND_PORT%"
timeout /t 2 /nobreak >nul
call :is_port_in_use %FRONTEND_PORT%
if not "%ERRORLEVEL%"=="0" (
  echo [WARN] Frontend did not open port %FRONTEND_PORT% yet. Check the frontend window for errors.
)

echo [OK] Services launched.
if "%BACKEND_ALREADY_RUNNING%"=="1" (
  echo [OK] Backend: reused existing instance on port %BACKEND_PORT%.
)
echo [OK] API docs: http://localhost:%BACKEND_PORT%/docs
echo [OK] UI:       http://localhost:%FRONTEND_PORT%
echo.
echo Optional usage:
echo   run_local_stack.bat                     ^(defaults: 8000 / 3001^)
echo   run_local_stack.bat 8001 3002           ^(custom ports^)
echo   run_local_stack.bat backend 8000        ^(backend only^)
echo   run_local_stack.bat frontend 8000 3001  ^(frontend only^)
exit /b 0

:backend_mode
set "BACKEND_PORT=%DEFAULT_BACKEND_PORT%"
if not "%~2"=="" set "BACKEND_PORT=%~2"

cd /d "%REPO_ROOT%"

where python >nul 2>&1
if errorlevel 1 (
  echo [ERROR] python is not available on PATH.
  exit /b 1
)

echo [INFO] Backend starting on port %BACKEND_PORT%...
python -m uvicorn api:app --host 0.0.0.0 --port %BACKEND_PORT%
exit /b %ERRORLEVEL%

:frontend_mode
set "BACKEND_PORT=%DEFAULT_BACKEND_PORT%"
set "FRONTEND_PORT=%DEFAULT_FRONTEND_PORT%"
if not "%~2"=="" set "BACKEND_PORT=%~2"
if not "%~3"=="" set "FRONTEND_PORT=%~3"
set "NEXT_PUBLIC_API_BASE_URL=http://localhost:%BACKEND_PORT%"

if not exist "%FRONTEND_DIR%\package.json" (
  echo [ERROR] frontend\package.json not found.
  exit /b 1
)

where npm >nul 2>&1
if errorlevel 1 (
  echo [ERROR] npm is not available on PATH.
  exit /b 1
)

cd /d "%FRONTEND_DIR%"

if not exist "node_modules" (
  echo [INFO] Installing frontend dependencies...
  npm install
  if errorlevel 1 (
    echo [ERROR] npm install failed.
    exit /b 1
  )
)

echo [INFO] Frontend starting on port %FRONTEND_PORT%...
echo [INFO] API base URL: %NEXT_PUBLIC_API_BASE_URL%
npm run dev -- -p %FRONTEND_PORT%
exit /b %ERRORLEVEL%

:usage
echo Usage:
echo   run_local_stack.bat
echo   run_local_stack.bat [backend_port] [frontend_port]
echo   run_local_stack.bat backend [backend_port]
echo   run_local_stack.bat frontend [backend_port] [frontend_port]
exit /b 0

:is_port_in_use
set "PORT_TO_CHECK=%~1"
powershell -NoProfile -Command ^
  "$p=%PORT_TO_CHECK%; if (Get-NetTCPConnection -State Listen -LocalPort $p -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }" >nul 2>&1
exit /b %ERRORLEVEL%
