"""S-series progress view. Read-only; safe to run anytime.

    py -3 eval/scripts/s_status.py
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SETS = ["W1", "W2", "W3", "H1", "D1", "D2", "WET1", "WET2", "O1", "O2", "C1", "NE15", "N1"]
MODELS = [("llama", "llama-3.2-11b"), ("nemotron", "nemotron-3-ultra")]
PER_SET = 120


def bar(done: int, total: int, width: int = 14) -> str:
    if total == 0:
        return " " * width
    n = round(width * done / total)
    return "#" * n + "." * (width - n)


def read_counts(set_name: str, short: str) -> tuple[int, int] | None:
    p = ROOT / "eval" / "runs" / f"s_{set_name}" / f"eval_{short}" / "results.json"
    if not p.exists():
        return None
    try:
        rs = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    ok = sum(1 for r in rs if not r.get("error"))
    return ok, len(rs) - ok


def main() -> None:
    now = datetime.now(timezone.utc)
    print(f"S-series status  local={datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  UTC={now.strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        b = json.loads((ROOT / "eval" / "runs" / "_http_budget.json").read_text(encoding="utf-8"))
        if b.get("date") == now.strftime("%Y-%m-%d"):
            counts = dict(b.get("counts") or {})
            if not counts and b.get("count"):
                counts = {"legacy": int(b["count"])}
            used = sum(int(v) for v in counts.values())
            n_acct = int(b.get("num_accounts") or 4)
            per = int(b.get("limit_per_account") or 4000)
        else:
            used, n_acct, per = 0, 4, 4000
    except (FileNotFoundError, json.JSONDecodeError):
        used, n_acct, per = 0, 4, 4000
    cap = n_acct * per
    nxt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    hrs = (nxt - now).total_seconds() / 3600
    print(f"Budget: {used}/{cap} used today across {n_acct} accounts ({per}/account) "
          f"| left {cap - used} | resets in {hrs:.2f}h")
    print()

    print(f"{'set':6} {'llama ok/err':>14} {'':14}    {'nemotron ok/err':>16}")
    print("-" * 62)
    tot = {"llama": [0, 0], "nemotron": [0, 0]}
    for s in SETS:
        cells = []
        for key, short in MODELS:
            c = read_counts(s, short)
            if c is None:
                cells.append(f"{'--':>14}")
            else:
                ok, err = c
                tot[key][0] += ok
                tot[key][1] += err
                cells.append(f"{str(ok)+'/'+str(err):>14}")
        llama_bar = ""
        c = read_counts(s, "llama-3.2-11b")
        if c:
            llama_bar = bar(c[0], PER_SET)
        print(f"{s:6} {cells[0]} {llama_bar:14}    {cells[1]}")
    print("-" * 62)
    gtotal = PER_SET * len(SETS)
    for key, _ in MODELS:
        ok, err = tot[key]
        print(f"{key:9} ok={ok:4d} err={err:4d} todo={gtotal-ok-err:4d}/{gtotal}  {bar(ok, gtotal, 30)}")
    print(f"grand total target = {gtotal*2} records (13 sets x 120 x 2 models)")
    print("(A set only counts as done when err=0; errored records auto re-run.)")


if __name__ == "__main__":
    main()
