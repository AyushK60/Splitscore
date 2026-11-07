@echo off
rem Stops only the SplitScope server that the launcher started (never any
rem other Python process or anything else using the port).
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\launcher\Stop-SplitScope.ps1" %*
set RC=%errorlevel%
if %RC% NEQ 0 pause
endlocal & exit /b %RC%
