"""Progress tracking and status reporting for evaluation runs."""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from eval.common import load_config, config_dirs

PROGRESS_FILE = Path(__file__).resolve().parent / "runs" / "progress.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_progress(job_name: str, model_id: str, condition: str, total: int) -> dict[str, Any]:
    """Initialize or resume progress tracking for a job."""
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    progress = {
        "job_name": job_name,
        "model_id": model_id,
        "condition": condition,
        "total": total,
        "completed": 0,
        "failed": 0,
        "retried": 0,
        "cached": 0,
        "started_at": _now_iso(),
        "last_update": _now_iso(),
        "last_error": None,
        "requests_per_minute": 0.0,
        "eta_seconds": None,
        "status": "running",
    }
    
    # Try to resume from existing
    if PROGRESS_FILE.exists():
        try:
            existing = json.loads(PROGRESS_FILE.read_text())
            if existing.get("job_name") == job_name:
                progress.update({k: existing.get(k, v) for k, v in progress.items()})
        except Exception:
            pass
    
    write_progress(progress)
    return progress


def update_progress(**kwargs) -> dict[str, Any]:
    """Update progress file with new values."""
    if PROGRESS_FILE.exists():
        progress = json.loads(PROGRESS_FILE.read_text())
    else:
        progress = {}
    
    progress.update(kwargs)
    progress["last_update"] = _now_iso()
    
    # Calculate rate and ETA
    if "completed" in kwargs or "started_at" in progress:
        try:
            started = datetime.fromisoformat(progress["started_at"].replace("Z", "+00:00"))
            elapsed = (datetime.now(timezone.utc) - started).total_seconds()
            completed = progress.get("completed", 0)
            if elapsed > 0 and completed > 0:
                progress["requests_per_minute"] = completed / elapsed * 60
                remaining = progress["total"] - completed
                if progress["requests_per_minute"] > 0:
                    progress["eta_seconds"] = remaining / progress["requests_per_minute"] * 60
        except Exception:
            pass
    
    write_progress(progress)
    return progress


def write_progress(progress: dict[str, Any]) -> None:
    """Write progress to file atomically."""
    tmp = PROGRESS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(progress, indent=2))
    tmp.replace(PROGRESS_FILE)


def read_progress() -> dict[str, Any] | None:
    """Read current progress."""
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text())
    return None


def render_bar(percent: float, width: int = 30) -> str:
    """Render a tqdm-style progress bar."""
    filled = int(width * percent / 100)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {percent:.1f}%"


def format_eta(seconds: float | None) -> str:
    """Format ETA as human-readable string."""
    if seconds is None or seconds < 0:
        return "unknown"
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds/60)}m {int(seconds%60)}s"
    return f"{int(seconds/3600)}h {int((seconds%3600)/60)}m"


def print_status() -> None:
    """Print clean status table."""
    progress = read_progress()
    if not progress:
        print("No active job.")
        return
    
    pct = (progress.get("completed", 0) / progress.get("total", 1)) * 100
    bar = render_bar(pct)
    eta = format_eta(progress.get("eta_seconds"))
    rpm = progress.get("requests_per_minute", 0)
    
    print(f"\n{'='*70}")
    print(f"JOB: {progress['job_name']} | Model: {progress['model_id']} | Condition: {progress['condition']}")
    print(f"{'='*70}")
    print(f"Progress: {bar}  ({progress['completed']}/{progress['total']})")
    print(f"Failed: {progress.get('failed', 0)} | Retried: {progress.get('retried', 0)} | Cached: {progress.get('cached', 0)}")
    print(f"Rate: {rpm:.1f} req/min | ETA: {eta}")
    if progress.get("last_error"):
        print(f"Last error: {progress['last_error'][:100]}")
    print(f"Started: {progress['started_at']} | Updated: {progress['last_update']}")
    print(f"Status: {progress.get('status', 'unknown')}")
    
    # Daily budget
    cfg = load_config()
    daily_budget = cfg["cost_control"]["daily_request_budget"]
    # Count today's requests from cache (simplified)
    used_today = progress.get("completed", 0)  # approximation
    print(f"\nDaily budget: {used_today}/{daily_budget} ({used_today/daily_budget*100:.1f}%)")
    
    print(f"\nNEXT RESUME COMMAND: (same command, runner is resumable)")


def watch_status(interval: int = 5) -> None:
    """Watch status continuously (Ctrl+C to exit)."""
    try:
        while True:
            os.system("cls" if os.name == "nt" else "clear")
            print_status()
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nStopped watching.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--watch", action="store_true", help="Watch mode (refresh every 5s)")
    parser.add_argument("--interval", type=int, default=5, help="Watch interval in seconds")
    args = parser.parse_args()
    
    if args.watch:
        watch_status(args.interval)
    else:
        print_status()