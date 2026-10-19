"""Phase 8 ITEM 2: measure HTTP-request rounds + per-run latency/tokens from archived
v1 records (C0/C0b direct; C1/C2 as proxies for C1a/C1b/C2a/C2b).
In provider.run, EVERY tool-loop iteration is one HTTP POST (round_num>=0 tool rounds with
tool calls, plus one final non-tool round). So:
    http_requests_per_scenario = (number of distinct tool rounds used) + 1 final round.
Also report max_tool_rounds prevalence (max_rounds_reached / truncation) in archived C2.
"""

from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

DIRS = {
    "llama-3.2-11b": [Path("eval/runs/eval_llama-3.2-11b")],
    "nemotron-3-ultra": [Path("eval/runs/full_nemotron-3-ultra_20261011_074835"),
                          Path("eval/runs/full_nemotron-3-ultra_20261011_082444")],
}

rows = []

for short, dirs in DIRS.items():
    recs = []
    for d in dirs:
        rf = d / "results.json"
        if not rf.exists():
            continue
        data = json.loads(rf.read_text(encoding="utf-8"))
        items = data if isinstance(data, list) else data.get("results") or data.get("records") or []
        recs.extend(items)
    # dedupe by (scenario_id, condition, repeat) keeping the first valid
    seen = {}
    for r in recs:
        if r.get("error"):
            continue
        key = (r.get("scenario_id"), r.get("condition"), r.get("repeat", 0))
        seen.setdefault(key, r)
    recs = list(seen.values())

    by_cond = defaultdict(list)
    for r in recs:
        c = r.get("condition")
        rounds = set()
        rounds_hits = {}
        for tl in (r.get("tool_log") or []):
            rounds.add(tl.get("round"))
        tool_rounds = len([x for x in rounds if x is not None]) if rounds else 0
        http_req = tool_rounds + 1 if (r.get("tool_log")) else 1
        by_cond[c].append({
            "http": http_req,
            "calls": r.get("tool_calls") or 0,
            "round_nums": sorted([x for x in rounds if x is not None]),
            "lat": r.get("latency_s") or 0,
            "tin": r.get("tokens_in") or 0,
            "tout": r.get("tokens_out") or 0,
            "finish": r.get("finish_reason") or "",
            "errortype": r.get("error_type") or "",
            "trunc": (r.get("parsed") or {}).get("truncated"),
        })

    for c in ("C0", "C0b", "C1", "C2"):
        v = by_cond.get(c, [])
        if not v:
            continue
        http = [x["http"] for x in v]
        calls = [x["calls"] for x in v]
        lats = [x["lat"] for x in v]
        tins = [x["tin"] for x in v]
        touts = [x["tout"] for x in v]
        maxr = sum(1 for x in v if x["errortype"] == "max_rounds_reached" or x["finish"] == "max_rounds_reached")
        n = len(http)
        rnds_hist = Counter(http)
        rows.append({
            "model": short, "cond": c, "n": n,
            "http_mean": statistics.mean(http), "http_median": statistics.median(http),
            "rounds_hist": dict(sorted(rnds_hist.items())),
            "calls_mean": statistics.mean(calls),
            "lat_mean_s": statistics.mean(lats),
            "tin_mean": statistics.mean(tins),
            "tout_mean": statistics.mean(touts),
            "max_rounds_reached": maxr,
            "trunc": (sum(1 for x in v if x["trunc"]) if c in ("C0", "C0b") else None),
        })

for r in rows:
    print(f"{r['model']:16s} {r['cond']:4s} n={r['n']:4d} http_mean={r['http_mean']:.2f} "
          f"med={r['http_median']:.0f} hist={r['rounds_hist']} calls_mean={r['calls_mean']:.2f} "
          f"lat={r['lat_mean_s']:.1f}s tin={r['tin_mean']:.0f} tout={r['tout_mean']:.0f} "
          f"maxr_reached={r['max_rounds_reached']}")

import json as _j
Path("eval/results/_round_stats.json").write_text(_j.dumps(rows, indent=1), encoding="utf-8")
print("\nwrote eval/results/_round_stats.json")