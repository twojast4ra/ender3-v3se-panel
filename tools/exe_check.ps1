# Runs on the gaming PC: start the built exe for 12 s with the printer connected, check it opens the port, then stop it.
$exe = 'C:\kiro\build\out\Ender3V3SE-panel.exe'
$p = Start-Process -FilePath $exe -PassThru -WorkingDirectory 'C:\kiro\build\out'
Start-Sleep -Seconds 12
$alive = -not $p.HasExited
$cfg = Test-Path 'C:\kiro\build\out\config.json'
$log = Get-ChildItem 'C:\kiro\build\out\logs' -ErrorAction SilentlyContinue | Select-Object -First 1
$logtail = if ($log) { Get-Content $log.FullName | Select-Object -Last 3 } else { @('no log') }
Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
"alive after 12 s: $alive"
"config written: $cfg"
"log: $($log.Name)"
$logtail
Remove-Item 'C:\kiro\build\out\config.json', 'C:\kiro\build\out\logs' -Recurse -Force -ErrorAction SilentlyContinue
