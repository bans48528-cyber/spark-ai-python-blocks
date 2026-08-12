@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "START_SCRIPT=%SCRIPT_DIR%scripts\start_web.ps1"

if not exist "%START_SCRIPT%" (
  echo Cannot find "%START_SCRIPT%".
  echo Please keep this file in the project root.
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%START_SCRIPT%"
if errorlevel 1 (
  echo.
  echo Spark AI generator failed to start.
  pause
  exit /b 1
)
