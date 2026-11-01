# Runs on the gaming PC: fresh clone, PyInstaller one-file build, portable zip. Output in C:\kiro\build\out
$ErrorActionPreference = 'Continue'
$root = 'C:\kiro\build'
New-Item -ItemType Directory -Force -Path $root | Out-Null
Set-Location $root
if (Test-Path "$root\ender3-v3se-panel") { Remove-Item -Recurse -Force "$root\ender3-v3se-panel" }
git clone -q https://github.com/twojast4ra/ender3-v3se-panel.git
Set-Location "$root\ender3-v3se-panel"
python -m pip install --user --quiet pyserial pyinstaller
python -m PyInstaller --noconfirm --onefile --windowed --name Ender3V3SE-panel app.py 2>&1 | Select-String -Pattern 'completed successfully|ERROR|error:' | ForEach-Object { $_.Line }
$out = "$root\out"
New-Item -ItemType Directory -Force -Path $out | Out-Null
Remove-Item "$out\*" -Force -ErrorAction SilentlyContinue
Copy-Item dist\Ender3V3SE-panel.exe $out
$zipdir = "$root\Ender3V3SE-panel"
if (Test-Path $zipdir) { Remove-Item -Recurse -Force $zipdir }
New-Item -ItemType Directory -Force -Path $zipdir | Out-Null
Copy-Item dist\Ender3V3SE-panel.exe, README.md, LICENSE $zipdir
Compress-Archive -Path $zipdir -DestinationPath "$out\Ender3V3SE-panel-windows.zip" -Force
Get-ChildItem $out | Select-Object Name, Length
