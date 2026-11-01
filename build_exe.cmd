@echo off
rem Builds a single-file Windows executable with PyInstaller (pip install pyinstaller). Output: dist\Ender3V3SE-panel.exe
cd /d "%~dp0"
python -m PyInstaller --noconfirm --onefile --windowed --name Ender3V3SE-panel app.py
echo Built dist\Ender3V3SE-panel.exe (config.json and logs\ are created next to it on first run).
pause
