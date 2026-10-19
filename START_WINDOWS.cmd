@echo off
setlocal
chcp 65001 >nul
title Water Contract AI - Windows
cd /d "%~dp0"
set PYTHONUTF8=1
py -3.12 -c "import sys; assert sys.version_info[:2] == (3, 12)" >nul 2>&1
if not errorlevel 1 (
  py -3.12 "%~dp0windows_launcher.py" %*
  goto done
)
python -c "import sys; assert sys.version_info[:2] == (3, 12)" >nul 2>&1
if not errorlevel 1 (
  python "%~dp0windows_launcher.py" %*
  goto done
)
echo Python 3.12 was not found.
echo Run INSTALL_WINDOWS.cmd first, then reopen this file.
:done
echo.
pause
endlocal
