$ErrorActionPreference = 'Continue'
$src = 'C:\kiro\build\ender3-v3se-panel\dist\Ender3V3SE-panel.exe'
Copy-Item $src 'C:\kiro\build\out\Ender3V3SE-panel.exe' -Force
Copy-Item $src 'C:\kiro\build\Ender3V3SE-panel\Ender3V3SE-panel.exe' -Force
Compress-Archive -Path 'C:\kiro\build\Ender3V3SE-panel' -DestinationPath 'C:\kiro\build\out\Ender3V3SE-panel-windows.zip' -Force
New-Item -ItemType Directory -Force -Path 'C:\kiro\Ender3V3SE-panel' | Out-Null
Copy-Item $src 'C:\kiro\Ender3V3SE-panel\Ender3V3SE-panel.exe' -Force
Copy-Item 'C:\kiro\build\ender3-v3se-panel\README.md' 'C:\kiro\Ender3V3SE-panel\README.md' -Force
Get-FileHash $src -Algorithm SHA256 | Select-Object -ExpandProperty Hash
Get-ChildItem 'C:\kiro\build\out', 'C:\kiro\Ender3V3SE-panel' | Select-Object FullName, Length
