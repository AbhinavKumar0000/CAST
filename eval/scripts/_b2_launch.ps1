$ErrorActionPreference = 'Continue'
$root = 'C:\Codes\mcp_for_farmers'
Set-Location -LiteralPath $root
$env:NVIDIA_REQUEST_TIMEOUT = '600'

$log     = Join-Path $root 'eval\runs\logs\b2_nemotron_20261014.log'
$status  = Join-Path $root 'eval\runs\logs\b2_nemotron_20261014.status'
$results = Join-Path $root 'eval\runs\eval_nemotron-3-ultra_b2\results.json'
$budget  = Join-Path $root 'eval\runs\_http_budget.json'
$target  = 1050   # 350 scenarios x 3 conditions

"B2_LAUNCH $(Get-Date -Format o)" | Out-File -FilePath $status -Encoding utf8

for ($attempt = 1; $attempt -le 4; $attempt++) {
    "B2_ATTEMPT $attempt START $(Get-Date -Format o)" | Out-File -FilePath $status -Append -Encoding utf8

    & python -u eval/scripts/run_model.py --model nvidia/nemotron-3-ultra-550b-a55b `
        --scenario-start 150 --scenarios 350 --conditions C1a,C2a,C2b --workers 4 `
        --run-suffix _b2 *>&1 | Tee-Object -FilePath $log -Append
    $code = $LASTEXITCODE
    "B2_ATTEMPT $attempt exit=$code $(Get-Date -Format o)" | Out-File -FilePath $status -Append -Encoding utf8

    $done = 0
    if (Test-Path -LiteralPath $results) {
        try { $done = (Get-Content -LiteralPath $results -Raw | ConvertFrom-Json).Count } catch { $done = 0 }
    }
    "B2_RESULTS count=$done/$target $(Get-Date -Format o)" | Out-File -FilePath $status -Append -Encoding utf8
    if ($done -ge $target) { break }

    try { $b = Get-Content $budget -Raw | ConvertFrom-Json; $used = [int]$b.count } catch { $used = 0 }
    "B2_BUDGET used=$used $(Get-Date -Format o)" | Out-File -FilePath $status -Append -Encoding utf8
    if ($used -lt 3950) { continue }

    $now = (Get-Date).ToUniversalTime()
    $next = [datetime]::SpecifyKind($now.Date.AddDays(1), 'Utc')
    $wait = [int]($next - $now).TotalSeconds + 30
    "B2_WAIT_UTC_RESET seconds=$wait until=$($next.ToString('o'))" | Out-File -FilePath $status -Append -Encoding utf8
    Start-Sleep -Seconds $wait
}

"B2_FINISHED $(Get-Date -Format o)" | Out-File -FilePath $status -Append -Encoding utf8
