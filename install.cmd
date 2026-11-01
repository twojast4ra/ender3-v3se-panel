@echo off
rem One-time setup: installs the one Python package the panel needs (pyserial).
cd /d "%~dp0"
where python >nul 2>&1 && (python -m pip install --user -r requirements.txt & goto done)
where py >nul 2>&1 && (py -3 -m pip install --user -r requirements.txt & goto done)
echo Python 3 was not found. Install it from https://www.python.org/downloads/ (tick "Add python.exe to PATH") and run this again.
pause
exit /b 1
:done
echo.
echo Done. Plug the printer in, switch it on, and run start.cmd.
pause
