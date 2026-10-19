# S-series live progress window. Re-run anytime, or leave it open while the run progresses.
#   powershell -ExecutionPolicy Bypass -File eval/scripts/s_watch.ps1

$env:PYTHONIOENCODING = 'utf-8'
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Set-Location $root

while ($true) {
    Clear-Host
    Write-Host ("=" * 70) -ForegroundColor DarkCyan
    Write-Host ("  S-SERIES LIVE PROGRESS   " + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')) -ForegroundColor Cyan
    Write-Host ("=" * 70) -ForegroundColor DarkCyan

    py -3 eval/scripts/s_status.py

    $w = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
         Where-Object { $_.CommandLine -like '*s_resume*' -or $_.CommandLine -like '*run_s_series*' }
    if ($w) {
        Write-Host ("`nWorker processes: " + (($w.ProcessId) -join ', ')) -ForegroundColor Green
    } else {
        Write-Host "`nNo worker process running (finished, or watcher not started)." -ForegroundColor Yellow
    }

    Write-Host "`n--- tail of run log ---" -ForegroundColor DarkGray
    Get-Content eval/runs/s_resume.log -Tail 6 -ErrorAction SilentlyContinue

    Write-Host "`n(refresh every 15s - Ctrl+C to close)" -ForegroundColor DarkGray
    Start-Sleep -Seconds 15
}
