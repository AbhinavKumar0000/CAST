# eval/scripts/run_stage.ps1
# Phase 8 staged-run Windows launcher. NO IMPLIED APPROVAL: a stage only runs when the
# operator starts it explicitly. Wraps run_model.py with logs, PID file, resume support
# and a per-invocation wall-clock budget. The runner itself is resumable (results.json
# is rewritten after every call), so simply re-running the same command continues.
#
# Usage:
#   .\eval\scripts\run_stage.ps1 -Stage A            # Llama 150 (C1a,C2a,C2b)
#   .\eval\scripts\run_stage.ps1 -Stage B -MaxSeconds 3600
#   .\eval\scripts\run_stage.ps1 -Stage C -RepeatFromEx 2
#
# Stages:
#   A  Llama-3.2-11b on 150   (C1a,C2a,C2b)   [C0b reused from v1 cache]
#   B  Nemotron-550b on 500   (C1a,C2a,C2b)   [C0b reused 472/500, 28 re-run]
#   C  consistency Nemotron->Llama: 100 scen x C0b,C1a,C2a, repeats 2..3 (2 fresh each)
#   D  OPTIONAL third family / C1b oracle   (gated on approval, not wired here)

param(
    [Parameter(Mandatory=$true)][ValidateSet("A","B","C","D")] [string]$Stage,
    [int]$MaxSeconds = 7200,
    [int]$Workers = 4,
    [string]$LogDir = "eval/runs/logs/stage$Stage"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)   # .../mcp_for_farmers
Set-Location $root

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$log = Join-Path $LogDir "stage${Stage}_$stamp.log"
$pidFile = Join-Path $LogDir "stage$Stage.pid"

switch ($Stage) {
    "A" {
        $model = "meta/llama-3.2-11b-vision-instruct"
        $conds = "C1a,C2a,C2b"
        $scen  = 150
    }
    "B" {
        $model = "nvidia/nemotron-3-ultra-550b-a55b"
        # C0b re-runs (28 hash-mismatch/error sids) are run together with the fresh conds.
        $conds = "C1a,C2a,C2b"
        $scen  = 500
    }
    "C" {
        # Consistency: run Nemotron first, then Llama, on the same 100 scenarios.
        Write-Host "Stage C is model-paired (Nemotron first, then Llama)."
        Write-Host "Run:  run_model.py --scenarios 100 --conditions C0b,C1a,C2a --repeat 3 --max-seconds ..."
        Write-Host "Repeats 0 already exist in the main run; repeats 1..2 are fresh (600/model)."
        exit 1
    }
    "D" { Write-Host "Stage D is gated on approval; not auto-runnable."; exit 1 }
}

$env:NVIDIA_REQUEST_TIMEOUT = "600"
$cmd = "python -u eval/scripts/run_model.py --model `"$model`" --conditions $conds --scenarios $scen --workers $Workers --max-seconds $MaxSeconds"

Write-Host "Stage $Stage -> $cmd"
Write-Host "Log: $log"

$proc = Start-Process -FilePath "python" -ArgumentList @("-u","eval/scripts/run_model.py","--model",$model,"--conditions",$conds,"--scenarios",[string]$scen,"--workers",[string]$Workers,"--max-seconds",[string]$MaxSeconds) `
    -RedirectStandardOutput $log -RedirectStandardError "$log.err" -PassThru -NoNewWindow
Set-Content -Path $pidFile -Value $proc.Id
Write-Host "Started PID $($proc.Id) (pidfile $pidFile)"
$proc.WaitForExit()
Write-Host "Stage $Stage finished with exit code $($proc.ExitCode); results appended to eval/runs/eval_<model>/results.json"