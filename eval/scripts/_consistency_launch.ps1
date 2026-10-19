$ErrorActionPreference = 'Continue'
$root   = 'C:\Codes\mcp_for_farmers'
Set-Location $root
$env:NVIDIA_REQUEST_TIMEOUT = '600'
$logs   = Join-Path $root 'eval\runs\logs'
$status = Join-Path $logs 'consistency.status'
$budget = Join-Path $root 'eval\runs\_http_budget.json'

$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$targetFresh = 600   # 100 scen x 3 conds x repeats 1..2

"CONSISTENCY_LAUNCH $(Get-Date -Format o)" | Out-File -FilePath $status -Encoding utf8

function Run-Model([string]$Model, [string]$Short) {
    $results = Join-Path $root "eval\runs\eval_$Short\results.json"
    $log = Join-Path $logs "consistency_${Short}_$stamp.log"
    for ($attempt = 1; $attempt -le 6; $attempt++) {
        "CONSISTENCY_ATTEMPT model=$Short attempt=$attempt START $(Get-Date -Format o)" |
            Out-File -FilePath $status -Append -Encoding utf8

        & python -u eval/scripts/run_model.py --model $Model `
            --scenarios 100 --conditions C0b,C1a,C2a --repeat 3 --workers 4 *>&1 |
            Tee-Object -FilePath $log -Append
        $code = $LASTEXITCODE
        "CONSISTENCY_ATTEMPT model=$Short attempt=$attempt exit=$code $(Get-Date -Format o)" |
            Out-File -FilePath $status -Append -Encoding utf8

        $tot = 0; $fresh = 0
        if (Test-Path -LiteralPath $results) {
            $line = & python -u eval/scripts/_consistency_status.py $results
            $parts = "$line".Trim().Split(' ')
            if ($parts.Count -ge 2) { $tot = [int]$parts[0]; $fresh = [int]$parts[1] }
        }
        "CONSISTENCY_STATUS model=$Short total=$tot fresh=$fresh/$targetFresh $(Get-Date -Format o)" |
            Out-File -FilePath $status -Append -Encoding utf8
        if ($fresh -ge $targetFresh) { break }

        try { $b = Get-Content $budget -Raw | ConvertFrom-Json; $used = [int]$b.count } catch { $used = 0 }
        "CONSISTENCY_BUDGET model=$Short used=$used $(Get-Date -Format o)" |
            Out-File -FilePath $status -Append -Encoding utf8
        if ($used -lt 3950) { continue }

        $now = (Get-Date).ToUniversalTime()
        $next = [datetime]::SpecifyKind($now.Date.AddDays(1), 'Utc')
        $wait = [int]($next - $now).TotalSeconds + 30
        "CONSISTENCY_WAIT_UTC_RESET model=$Short seconds=$wait until=$($next.ToString('o'))" |
            Out-File -FilePath $status -Append -Encoding utf8
        Start-Sleep -Seconds $wait
    }
    "CONSISTENCY_MODEL_DONE model=$Short $(Get-Date -Format o)" |
        Out-File -FilePath $status -Append -Encoding utf8
}

Run-Model 'nvidia/nemotron-3-ultra-550b-a55b' 'nemotron-3-ultra'
Run-Model 'meta/llama-3.2-11b-vision-instruct' 'llama-3.2-11b'

"CONSISTENCY_FINISHED $(Get-Date -Format o)" | Out-File -FilePath $status -Append -Encoding utf8
