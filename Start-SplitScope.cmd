@echo off
rem One-click launcher for SplitScope V2. All logic lives in
rem scripts\launcher\Start-SplitScope.ps1; paths with spaces are quoted.
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\launcher\Start-SplitScope.ps1" %*
set RC=%errorlevel%
if %RC% NEQ 0 pause
endlocal & exit /b %RC%
