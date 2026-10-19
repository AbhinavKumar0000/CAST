"""S-series auto-resume watcher (operational only; no design change).

Runs AFTER the approved PROTOCOL 8.33 plan. It repeatedly invokes the existing
`run_s_series.py` for whichever (model, set) pairs are still incomplete, waiting for the
UTC-day request budget to reset when exhausted, and skipping a model whose endpoint is
down (probe returns non-200, e.g. the nemotron 404 outage) until it recovers.

It does NOT change the harness, perturbations, oracle, prompts, or scoring; it only
schedules the runs the user already approved. Safe to stop/restart at any time (the
underlying runner is resumable and saves incrementally).

    py -3 eval/scripts/s_resume.py            # run until all sets complete
    py -3 eval/scripts/s_resume.py --once     # single pass (for a manual check)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT / ".env")

BUDGET_PATH = ROOT / "eval" / "runs" / "_http_budget.json"
DAILY_BUDGET = 4000
ENDPOINT = "https://integrate.api.nvidia.com/v1/chat/completions"
MODEL_ID = {
    "llama": "meta/llama-3.2-11b-vision-instruct",
    "nemotron": "nvidia/nemotron-3-ultra-550b-a55b",
}
MODEL_SHORT = {"llama": "llama-3.2-11b", "nemotron": "nemotron-3-ultra"}
SETS = ["W1", "W2", "W3", "H1", "D1", "D2", "WET1", "WET2", "O1", "O2", "C1", "NE15", "N1"]
PER_SET = 120
POLL_SECONDS = 600


def log(msg: str) -> None:
    print(f"[s_resume {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}Z] {msg}", flush=True)


def api_keys() -> list[str]:
    return [os.getenv(f"NVIDIA_API_KEY_{i}", "").strip() for i in range(1, 5)
            if os.getenv(f"NVIDIA_API_KEY_{i}", "").strip()]


def budget_left() -> int:
    """Requests still available today across all API-key accounts."""
    try:
        d = json.loads(BUDGET_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return DAILY_BUDGET * 4
    if d.get("date") != datetime.now(timezone.utc).strftime("%Y-%m-%d"):
        return DAILY_BUDGET * 4
    counts = dict(d.get("counts") or {})
    if not counts and d.get("count"):
        counts = {"legacy": int(d["count"])}
    n = int(d.get("num_accounts") or 4)
    limit = int(d.get("limit_per_account") or DAILY_BUDGET)
    return max(0, limit * n - sum(int(v) for v in counts.values()))


def seconds_to_reset() -> float:
    now = datetime.now(timezone.utc)
    nxt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=10, microsecond=0)
    return max(30.0, (nxt - now).total_seconds())


def health(model_key: str, attempts: int = 4, need: int = 3) -> tuple[bool, str]:
    """Probe the endpoint a few times; healthy only if >= ``need`` succeed.

    Guards against intermittent 503s: a single lucky 200 must not start a full run
    (each full set would then burn the per-account budget on retries).
    """
    keys = api_keys()
    if not keys:
        return False, "no api keys"
    payload = {"model": MODEL_ID[model_key], "messages": [{"role": "user", "content": "ok"}],
               "max_tokens": 4, "temperature": 0.2, "top_p": 1.0}
    ok = 0
    last = ""
    for _ in range(attempts):
        try:
            r = httpx.post(ENDPOINT, json=payload,
                           headers={"Authorization": f"Bearer {keys[0]}"}, timeout=60.0)
            if r.status_code == 200:
                ok += 1
                if ok >= need:
                    break
            else:
                last = f"HTTP {r.status_code}: {r.text[:120]}"
        except Exception as e:  # noqa: BLE001
            last = f"{type(e).__name__}: {e}"
    if ok >= need:
        return True, f"{ok}/{attempts} probes ok"
    return False, f"{ok}/{attempts} probes ok; last: {last}"


def remaining_sets(model_key: str) -> list[str]:
    short = MODEL_SHORT[model_key]
    todo = []
    for s in SETS:
        p = ROOT / "eval" / "runs" / f"s_{s}" / f"eval_{short}" / "results.json"
        if not p.exists():
            todo.append(s)
            continue
        try:
            rs = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            todo.append(s)
            continue
        ok = sum(1 for r in rs if not r.get("error"))
        if ok < PER_SET:
            todo.append(s)
    return todo


def run_model(model_key: str, sets: list[str]) -> None:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8",
           "NVIDIA_REQUEST_TIMEOUT": os.getenv("NVIDIA_REQUEST_TIMEOUT", "120")}
    workers = os.getenv("S_WORKERS", "8")
    cmd = [sys.executable, "-u", str(ROOT / "eval" / "scripts" / "run_s_series.py"),
           "--models", model_key, "--sets", *sets, "--workers", workers]
    log(f"RUN {model_key} sets={sets} workers={workers}")
    subprocess.run(cmd, cwd=str(ROOT), env=env, check=False)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="single pass then exit")
    args = ap.parse_args()

    log(f"watcher start | budget_left={budget_left()} | models={list(MODEL_ID)}")
    while True:
        any_left = False
        for m in ("llama", "nemotron"):
            todo = remaining_sets(m)
            if not todo:
                continue
            any_left = True
            healthy, body = health(m)
            if not healthy:
                log(f"{m}: endpoint not healthy -> skip; {body[:120]}")
                continue
            if budget_left() < 50:
                wait = seconds_to_reset()
                if args.once:
                    log(f"{m}: budget exhausted ({budget_left()} left); --once so not sleeping")
                    continue
                log(f"{m}: budget exhausted ({budget_left()} left) -> sleep {wait/3600:.2f}h to UTC reset")
                time.sleep(wait)
                continue
            run_model(m, todo)
        if not any_left:
            log("ALL SETS COMPLETE for both models. Exiting.")
            return
        if args.once:
            log("--once: single pass done.")
            return
        log(f"cycle done (budget_left={budget_left()}); sleeping {POLL_SECONDS}s")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
