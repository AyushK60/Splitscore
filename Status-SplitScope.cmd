@echo off
rem Shows whether SplitScope V2 is running, its web address, and guidance.
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\launcher\Status-SplitScope.ps1" %*
set RC=%errorlevel%
pause
endlocal & exit /b %RC%
