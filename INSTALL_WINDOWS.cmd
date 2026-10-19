@echo off
setlocal
chcp 65001 >nul
title Water Contract AI - Install prerequisites
echo This installs Python 3.12 and Node.js LTS using Microsoft WinGet.
echo Review any installer or agreement prompts yourself.
echo No Windows security policies are changed.
echo.
pause
where winget >nul 2>&1
if errorlevel 1 goto manual
winget install --id Python.Python.3.12 --exact --source winget
winget install --id OpenJS.NodeJS.LTS --exact --source winget
echo.
echo Close this window after installation. Then double-click START_WINDOWS.cmd.
echo If Python or Node.js is still not found, restart Windows once.
goto done
:manual
echo WinGet was not found. Install Python 3.12 and Node.js LTS from:
echo https://www.python.org/downloads/windows/
echo https://nodejs.org/en/download
echo Select Python 3.12, and enable Add python.exe to PATH in its installer.
echo Then reopen START_WINDOWS.cmd.
start "" "https://www.python.org/downloads/windows/"
start "" "https://nodejs.org/en/download"
:done
echo.
pause
endlocal
