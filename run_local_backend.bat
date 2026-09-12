@echo off
setlocal

rem PlantGPT launcher wired to the local FastAPI backend (backend/), the
rem only network path this client uses (plan Section C.3) - no provider
rem API key is ever embedded here; those live server-side only
rem (backend/.env, never committed). Start the backend first:
rem   cd backend && uvicorn app.main:app --port 8000
rem then run this to launch the client against it in Chrome.

set "FLUTTER_BIN=C:\src\flutter\bin\flutter.bat"
if not exist "%FLUTTER_BIN%" set "FLUTTER_BIN=flutter"

set "PROJECT_DIR=D:\PlantGpt-plantGpt_v1\PlantGpt-plantGpt_v1"
set "API_BASE_URL=http://127.0.0.1:8000"

rem Dev-mode identity headers (see backend/app/modules/auth/service.py) -
rem stand in for real Auth0 login until that exists client-side. Replace
rem with API_SESSION_TOKEN once you have a real session token instead.
set "API_DEV_TENANT_ID=default"
set "API_DEV_USER_ID=dev-user"

cd /d "%PROJECT_DIR%"

echo Launching PlantGPT in Chrome, wired to the local backend at %API_BASE_URL%...
call "%FLUTTER_BIN%" run -d chrome ^
  --dart-define=API_BASE_URL=%API_BASE_URL% ^
  --dart-define=API_DEV_TENANT_ID=%API_DEV_TENANT_ID% ^
  --dart-define=API_DEV_USER_ID=%API_DEV_USER_ID%

echo.
echo App exited or failed to launch. See any error above.
pause
endlocal
