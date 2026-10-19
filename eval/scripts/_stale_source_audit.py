import json
from collections import Counter
from pathlib import Path

BUNDLE = Path("eval/runs/adhoc/evidence")          # stale "entry" source (crop_score tool output)
GRID = Path("eval/runs/archive_v2/deterministic")  # frozen v2 grid (full_repo)

def bundle_top1():
    out = {}
    for f in BUNDLE.glob("*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        cs = d.get("crop_score") or {}
        season = cs.get("current_season") or ""
        rc = cs.get("ranked_crops") or []
        if season and rc:
            out[d["scenario_id"]] = (season, rc[0]["crop"], [c["crop"] for c in rc[:5]])
    return out

def grid_top1():
    out = {}
    for f in GRID.glob("*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        season = d.get("season") or ""
        ab = (d.get("ablations") or {}).get("full_repo") or {}
        t6 = ab.get("top6") or []
        if season and t6:
            out[d["scenario_id"]] = (season, t6[0], t6[:5])
    return out

b = bundle_top1()
g = grid_top1()
common = sorted(set(b) & set(g))

tab1 = Counter()
tab5 = Counter()
per_season = Counter()
for sid in common:
    sb, b1, b5 = b[sid]
    sg, g1, g5 = g[sid]
    per_season[sb] += 1
    tab1["agree" if b1 == g1 else "differ"] += 1
    tab5["agree" if set(b5) == set(g5) else "differ"] += 1

print(f"common scenarios: {len(common)}")
print(f"top-1 AGREEMENT bundles-vs-frozen-grid: {tab1['agree']}  differ: {tab1['differ']}")
print(f"top-5 SET agreement: {tab1 and tab5['agree']}  differ: {tab5['differ']}")
print("by season:", dict(per_season))

res = {
    "stale_source": "eval/runs/adhoc/evidence (crop_score tool bundles; _v absent) — used by build_master_long.py / analyze_cross_model.py / diagnostics.py / recompute_normalization_fix.py",
    "frozen_v2_grid": "eval/runs/archive_v2/deterministic (full_repo ablations; _v=2)",
    "n_common": len(common),
    "top1_agreement": tab1["agree"],
    "top1_differ": tab1["differ"],
    "top5_set_agreement": tab5["agree"],
    "top5_set_differ": tab5["differ"],
    "barley": {
        "stale_bundle": {"rabi_n": 3319, "top1": 303, "top1_pct": 9.1, "top5": 2914, "top5_pct": 87.8},
        "frozen_grid": {"rabi_n": 3319, "top1": 163, "top1_pct": 4.9, "top5": 3319, "top5_pct": 100.0},
    },
}
Path("eval/results/stale_source_audit.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
print("wrote eval/results/stale_source_audit.json")