@echo off
rem Ender-3 V3 SE control panel. Close Pronterface or any other program using the printer's port first.
cd /d "%~dp0"
where pythonw >nul 2>&1 && (start "" pythonw app.py %* & exit /b 0)
where pyw >nul 2>&1 && (start "" pyw -3 app.py %* & exit /b 0)
echo Python 3 was not found. Install it from https://www.python.org/downloads/ (tick "Add python.exe to PATH"),
echo then run install.cmd once, then this file again.
pause
