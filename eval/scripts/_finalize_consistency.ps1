$ErrorActionPreference = 'Continue'
$root = 'C:\Codes\mcp_for_farmers'
Set-Location $root
$logs = Join-Path $root 'eval\runs\logs'
$status = Join-Path $logs 'consistency.status'
$marker = Join-Path $logs 'consistency_analysis.status'
$log = Join-Path $logs ('consistency_analysis_' + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.log')

"FINALIZE_START $(Get-Date -Format o)" | Out-File -FilePath $marker -Encoding utf8

# Wait for the launcher to write CONSISTENCY_FINISHED (survives the UTC budget wait).
while ($true) {
    Start-Sleep -Seconds 60
    $done = $false
    try {
        $st = Get-Content -Raw -LiteralPath (Join-Path 'C:\Codes\mcp_for_farmers\eval\runs\logs\consistency.status') -ErrorAction SilentlyContinue
        if ($st -match 'CONSISTENCY_FINISHED') { $done = $true }
    } catch { $done = $false }
    if ($done) { break }
}

"CONSISTENCY_FINISHED_SEEN $(Get-Date -Format o)" | Out-File -FilePath (Join-Path $root 'eval\runs\logs\keepawake_wait.status') -Append -Encoding utf8

$nemo = & python -u eval/scripts/_consistency_status.py eval/runs/eval_nemotron-3-ultra/results.json
$llama = & python -u eval/scripts/_consistency_status.py eval/runs/eval_llama-3.2-11b/results.json
"CONSISTENCY_FINAL nemotron(total fresh)=$nemo llama(total fresh)=$llama $(Get-Date -Format o)" |
    Out-File -FilePath (Join-Path $logs 'consistency.status') -Append -Encoding utf8

& python -u eval/scripts/consistency_analysis.py *>&1 | Tee-Object -FilePath (Join-Path $logs 'consistency_analysis.log') -Append
"CONSISTENCY_ANALYSIS_DONE exit=$LASTEXITCODE $(Get-Date -Format o)" |
    Out-File -FilePath (Join-Path $logs 'consistency.status') -Append -Encoding utf8
