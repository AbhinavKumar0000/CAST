$ErrorActionPreference = 'Stop'
$root = 'C:\Codes\mcp_for_farmers'
$sig = @'
[DllImport("kernel32.dll", SetLastError=true)]
public static extern uint SetThreadExecutionState(uint esFlags);
'@
$t = Add-Type -MemberDefinition $sig -Name 'PowrCons' -Namespace 'KACons' -PassThru

# DECIMAL constants: PowerShell parses 0x80000000 as negative Int32 (cannot convert to UInt32).
[uint32]$ES_CONTINUOUS      = 2147483648
[uint32]$ES_SYSTEM_REQUIRED = 1
$hold  = [uint32]($ES_CONTINUOUS -bor $ES_SYSTEM_REQUIRED)
$clear = [uint32]$ES_CONTINUOUS

$kaLog  = Join-Path $root 'eval\runs\logs\keepawake_consistency.status'
$consSt = Join-Path $root 'eval\runs\logs\consistency.status'

"KA_START $(Get-Date -Format o)" | Out-File -FilePath $kaLog -Encoding utf8
$prev = $t::SetThreadExecutionState($hold)
"KA_HOLD flags=$hold prev=$prev ok=$([bool]($prev -ne 0)) $(Get-Date -Format o)" |
    Out-File -FilePath $kaLog -Append -Encoding utf8

while ($true) {
    Start-Sleep -Seconds 30
    $procs = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
             Where-Object { $_.CommandLine -match 'run_model\.py' }
    $done = $false
    try {
        $st = Get-Content -Raw -LiteralPath (Join-Path $root 'eval\runs\logs\consistency.status') -ErrorAction SilentlyContinue
        if ($st -match 'CONSISTENCY_FINISHED') { $done = $true }
    } catch { $done = $false }
    if (-not $procs -or $done) { break }
}

[void]$t::SetThreadExecutionState($clear)
"KA_END $(Get-Date -Format o)" | Out-File -FilePath $kaLog -Append -Encoding utf8
