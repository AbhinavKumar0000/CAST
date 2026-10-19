$ErrorActionPreference = 'Continue'
$root   = 'C:\Codes\mcp_for_farmers'
$log    = Join-Path $root 'eval\runs\logs\b2_nemotron_20261014.log'
$stat   = Join-Path $root 'eval\runs\logs\b2_nemotron_20261014.status'
$kaLog  = Join-Path $root 'eval\runs\logs\keepawake_b2.status'
$results= Join-Path $root 'eval\runs\eval_nemotron-3-ultra_b2\results.json'
$budget = Join-Path $root 'eval\runs\_http_budget.json'
$target = 1050

$Host.UI.RawUI.WindowTitle = 'B2 progress (Nemotron C1a/C2a/C2b, 350 scenarios)'

while ($true) {
    $now = Get-Date
    $done = 0
    try { $done = (Get-Content -LiteralPath $results -Raw | ConvertFrom-Json).Count } catch { $done = 0 }

    $hb = $null
    try {
        $hbLine = Select-String -LiteralPath $log -Pattern '\[heartbeat\] (\d+)s \| done (\d+)/(\d+) \| ok (\d+) err (\d+) active (\d+)' -AllMatches |
                  Select-Object -Last 1
        if ($hbLine) { $hb = $hbLine.Matches[0] }
    } catch {}

    $elapsed = 0; $ok = 0; $err = 0; $active = 0
    if ($hb) {
        $elapsed = [int]$hb.Groups[1].Value
        $ok      = [int]$hb.Groups[4].Value
        $err     = [int]$hb.Groups[5].Value
        $active  = [int]$hb.Groups[6].Value
    }

    $rate = if ($elapsed -gt 0) { $done / $elapsed } else { 0 }
    $eta  = if ($rate -gt 0) { [int](($target - $done) / $rate) } else { 0 }

    $ka = 'not running'
    try {
        $kaLast = Get-Content -LiteralPath $kaLog -Tail 1
        if ($kaLast -match 'KA_HOLD') { $ka = 'HOLDING (ok)' }
        elseif ($kaLast -match 'KA_END') { $ka = 'released' }
    } catch {}
    $used = 0
    try { $used = [int](Get-Content -LiteralPath $budget -Raw | ConvertFrom-Json).count } catch {}

    $recent = @()
    try { $recent = Get-Content -LiteralPath $log -Tail 8 | Where-Object { $_ -match ' OK \(' } | Select-Object -Last 5 } catch {}

    Clear-Host
    Write-Host '============================================================' -ForegroundColor Cyan
    Write-Host '  B2  Nemotron-3-Ultra  C1a/C2a/C2b  (llm_subset[150:500])' -ForegroundColor Cyan
    Write-Host '============================================================' -ForegroundColor Cyan
    Write-Host ("  Now       : {0}" -f $now.ToString('yyyy-MM-dd HH:mm:ss'))
    if ($elapsed -gt 0) {
        Write-Host ("  Elapsed   : {0:hh\:mm\:ss}   ok={1} err={2} active={3}" -f ([timespan]::FromSeconds($elapsed)), $ok, $err, $active)
    }
    Write-Host ("  Done      : {0}/{1}  ({2:P1})" -f $done, $target, ($done / $target)) -ForegroundColor Green
    if ($rate -gt 0) {
        Write-Host ("  Rate      : {0:N2} calls/min" -f ($rate * 60))
        Write-Host ("  ETA       : {0:N0} min  (~{1})" -f ($eta / 60), $now.AddSeconds($eta).ToString('HH:mm:ss'))
    }
    Write-Host ("  HTTP used : {0}/4000 (UTC {1})" -f $used, (Get-Date).ToUniversalTime().ToString('yyyy-MM-dd'))
    Write-Host ("  Keepawake : {0}" -f $ka) -ForegroundColor Yellow
    Write-Host '  ----------------------------------------------------------'
    $pct = [int](100 * $done / $target)
    $bars = [int]($pct / 2)
    Write-Host ('  [' + ('#' * $bars) + ('.' * (50 - $bars)) + ('] {0}%' -f $pct)) -ForegroundColor Green
    Write-Host '  Recent:'
    foreach ($r in $recent) { Write-Host ("    {0}" -f ($r.Trim())) }
    Write-Host ''

    if ($done -ge $target) { Write-Host '  B2 COMPLETE.' -ForegroundColor Green; break }
    try { if ((Get-Content -LiteralPath $stat -Raw) -match 'B2_FINISHED') { Write-Host '  B2 FINISHED (launcher exited).' -ForegroundColor Green; break } } catch {}

    Start-Sleep -Seconds 15
}
Write-Host 'Watcher exiting. Press Enter to close.' -ForegroundColor Gray
[void](Read-Host)
