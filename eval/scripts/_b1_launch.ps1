$ErrorActionPreference = 'Continue'
$root = 'C:\Codes\mcp_for_farmers'
Set-Location -LiteralPath $root
$env:NVIDIA_REQUEST_TIMEOUT = '600'

$log = Join-Path $root 'eval\runs\logs\b1_nemotron_20261014.log'
$status = Join-Path $root 'eval\runs\logs\b1_nemotron_20261014.status'

"B1_WAITING $(Get-Date -Format o)" | Out-File -FilePath $status -Encoding utf8

$resetUtc = [datetime]::SpecifyKind([datetime]::ParseExact('2026-10-14T00:00:00','yyyy-MM-ddTHH:mm:ss',$null), 'Utc')
while ((Get-Date).ToUniversalTime() -lt $resetUtc) { Start-Sleep -Seconds 20 }

"B1_STARTED $(Get-Date -Format o)" | Out-File -FilePath $status -Append -Encoding utf8

& python -u eval/scripts/run_model.py --model nvidia/nemotron-3-ultra-550b-a55b --scenarios 150 --conditions C1a,C2a,C2b --workers 4 *>&1 | Tee-Object -FilePath $log

"B1_EXIT code=$LASTEXITCODE $(Get-Date -Format o)" | Out-File -FilePath $status -Append -Encoding utf8
