@echo off
setlocal EnableExtensions

rem Windows wrapper for zanata_replace_keyword.py
rem Usage:
rem   scripts\zanata_replace_keyword.bat --find "HelloCash" --replace "VitaBirr" --dry-run

set "SCRIPT_DIR=%~dp0"

where py >nul 2>nul
if %ERRORLEVEL%==0 (
  py -3 "%SCRIPT_DIR%zanata_replace_keyword.py" %*
  exit /b %ERRORLEVEL%
)

where python >nul 2>nul
if %ERRORLEVEL%==0 (
  python "%SCRIPT_DIR%zanata_replace_keyword.py" %*
  exit /b %ERRORLEVEL%
)

echo Error: Python was not found. Install Python 3 and ensure "py" or "python" is on PATH.
exit /b 1
