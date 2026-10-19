"""Dedupe and summarize a resumable run's results.json.

Records may contain duplicates because resumable chunks re-run error keys with
--retry-errors (old error + new attempt). This keeps the *last non-error* record
per (scenario_id, condition, repeat), otherwise the last one, and rewrites the
file atomically (backing up the original). Then prints per-condition stats.

Usage: python -u eval/scripts/finalize_results.py --run eval_llama-3.2-11b
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from eval.common import load_config, ensure_dirs, config_dirs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True, help="Run dir name under eval/runs, e.g. eval_llama-3.2-11b")
    args = ap.parse_args()

    cfg = load_config()
    ensure_dirs(cfg)
    runs_dir = config_dirs(cfg)["runs_dir"]
    run_dir = runs_dir / args.run
    results_file = run_dir / "results.json"
    if not results_file.exists():
        raise SystemExit(f"not found: {results_file}")

    with results_file.open() as f:
        results = json.load(f)
    raw = len(results)

    best = {}
    for r in results:
        key = (r["scenario_id"], r["condition"], r.get("repeat", 0))
        prev = best.get(key)
        if prev is None or (r.get("error") is None and prev.get("error") is not None):
            best[key] = r
    deduped = sorted(best.values(), key=lambda r: (r["scenario_id"], r["condition"]))

    backup = results_file.with_suffix(".json.bak")
    shutil.copyfile(results_file, backup)
    tmp = results_file.with_suffix(".tmp")
    with tmp.open("w") as f:
        json.dump(deduped, f, indent=2)
    tmp.replace(results_file)

    print(f"raw={raw} deduped={len(deduped)} (backup: {backup.name})")

    all_conditional = [r for r in deduped if r["condition"] in ("C0", "C0b", "C1", "C2")]
    models = sorted({r["model_short"] for r in all_conditional})
    print(f"\n{'Model':<16}{'Cond':<5}{'Tot':>5}{'OK':>5}{'Err':>5}{'MedLat':>9}{'AvgTok':>8}{'AvgTools':>10}  InvJSON")
    for model in models:
        rows = [r for r in all_conditional if r["model_short"] == model]
        for cond in ("C0", "C0b", "C1", "C2"):
            rc = [r for r in rows if r["condition"] == cond]
            if not rc:
                continue
            ok = sum(1 for r in rc if not r.get("error"))
            lats = sorted(r.get("latency_s") or 0 for r in rc)
            med_lat = lats[len(lats) // 2] if lats else 0
            avg_tok = sum(r.get("tokens_out") or 0 for r in rc) / len(rc)
            avg_tools = sum(r.get("tool_calls") or 0 for r in rc) / len(rc)
            inv = sum(1 for r in rc if not (r.get("parsed") or {}).get("valid_json", True))
            print(f"{model:<16}{cond:<5}{len(rc):>5}{ok:>5}{len(rc)-ok:>5}{med_lat:>8.0f}s{avg_tok:>8.0f}{avg_tools:>10.1f}  {inv}")
        pct = sum(1 for r in rows if not r.get("error")) / len(rows) * 100
        print(f"{model:<16}{'TOTAL':<5}{'':>5}{'':>5}{'':>5}{'':>9}{'':>8}{'':>10}  {pct:.1f}% OK")

    err_sample = [r for r in all_conditional if r.get("error")]
    if err_sample:
        print("\nError sample:")
        c = Counter(e.get("error", "")[:60] for e in err_sample)
        for msg, n in c.most_common(8):
            print(f"  {n:>3}  {msg}")


if __name__ == "__main__":
    main()