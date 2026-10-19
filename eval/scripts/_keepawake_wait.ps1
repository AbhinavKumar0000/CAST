$ErrorActionPreference = 'Continue'
$root = 'C:\Codes\mcp_for_farmers'
$sig = @'
[DllImport("kernel32.dll", SetLastError=true)]
public static extern uint SetThreadExecutionState(uint esFlags);
'@
$t = Add-Type -MemberDefinition $sig -Name 'PowrWait' -Namespace 'KAWait' -PassThru

[uint32]$ES_CONTINUOUS      = 2147483648
[uint32]$ES_SYSTEM_REQUIRED = 1
$hold  = [uint32]($ES_CONTINUOUS -bor $ES_SYSTEM_REQUIRED)
$clear = [uint32]$ES_CONTINUOUS

$kaLog = Join-Path $root 'eval\runs\logs\keepawake_wait.status'
$consSt = Join-Path $root 'eval\runs\logs\consistency.status'

"KAW_START $(Get-Date -Format o)" | Out-File -FilePath $kaLog -Encoding utf8
$prev = $t::SetThreadExecutionState($hold)
"KAW_HOLD flags=$hold prev=$prev ok=$([bool]($prev -ne 0)) $(Get-Date -Format o)" |
    Out-File -FilePath $kaLog -Append -Encoding utf8

# Hold until the consistency job writes CONSISTENCY_FINISHED (works across the UTC budget
# wait when no run_model.exe is mid-run). Re-assert the flag periodically.
while ($true) {
    Start-Sleep -Seconds 60
    [void]$t::SetThreadExecutionState($hold)
    $done = $false
    try {
        $st = Get-Content -Raw -LiteralPath $consSt -ErrorAction SilentlyContinue
        if ($st -match 'CONSISTENCY_FINISHED') { $done = $true }
    } catch { $done = $false }
    if ($done) { break }
}

[void]$t::SetThreadExecutionState($clear)
"KAW_END $(Get-Date -Format o)" | Out-File -FilePath $kaLog -Append -Encoding utf8
