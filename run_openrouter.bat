@echo off
setlocal

rem PlantGPT launcher wired to OpenRouter.ai's hosted Free Models Router.
rem Double-click this file, or run it from a terminal, to build and launch
rem the app in Chrome with the image-attachment feature enabled.

set "FLUTTER_BIN=C:\src\flutter\bin\flutter.bat"
if not exist "%FLUTTER_BIN%" set "FLUTTER_BIN=flutter"

set "PROJECT_DIR=D:\PlantGpt-plantGpt_v1\PlantGpt-plantGpt_v1"
set "OPENROUTER_API_KEY=YOUR_API_KEY_HERE"

cd /d "%PROJECT_DIR%"

echo Launching PlantGPT in Chrome, wired to OpenRouter.ai...
call "%FLUTTER_BIN%" run -d chrome --dart-define=OPENROUTER_API_KEY=%OPENROUTER_API_KEY%

echo.
echo App exited or failed to launch. See any error above.
pause
endlocal
