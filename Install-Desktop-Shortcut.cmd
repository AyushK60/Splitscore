@echo off
rem Creates the "SplitScope V2" desktop shortcut for this project folder.
rem Does not touch any other shortcut and needs no administrator rights.
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\launcher\Install-DesktopShortcut.ps1" %*
set RC=%errorlevel%
if %RC% NEQ 0 pause
endlocal & exit /b %RC%
