$exe = 'C:\kiro\Ender3V3SE-panel\Ender3V3SE-panel.exe'
Start-Process -FilePath $exe -WorkingDirectory 'C:\kiro\Ender3V3SE-panel'
Start-Sleep -Seconds 14
$procs = Get-Process Ender3V3SE-panel -ErrorAction SilentlyContinue
"instances running: $($procs.Count)"
$log = Get-ChildItem 'C:\kiro\Ender3V3SE-panel\logs' -ErrorAction SilentlyContinue | Select-Object -First 1
if ($log) { "log: $($log.Name)"; Get-Content $log.FullName | Select-Object -Last 4 } else { 'no log written' }
