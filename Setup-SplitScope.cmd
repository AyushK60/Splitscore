@echo off
rem One-time first install: checks Python/Node, creates .venv, installs the
rem project's pinned dependencies, builds the frontend, creates the desktop
rem shortcut. Safe to re-run; needs no administrator rights.
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\launcher\Setup-SplitScope.ps1" %*
set RC=%errorlevel%
if %RC% NEQ 0 pause
endlocal & exit /b %RC%
