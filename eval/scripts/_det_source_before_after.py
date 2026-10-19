"""True before/after for the deterministic-grid repoint.

The canonical c3_deterministic_summary.json was already produced FROM
archive_v2/deterministic (by analyze_deterministic_v2.py), so comparing the
repointed v1 scripts against it does NOT reveal adhoc-vs-v2 drift. This script
computes the canonical metric set from EACH grid independently and diffs them,
which is the number that actually changes when a script is repointed.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from eval.common import config_dirs, load_config  # noqa: E402
from eval.metrics import (  # noqa: E402
    distinct_crops,
    jaccard_similarity,
    per_district_differentiation,
    season_validity_rate,
    shannon_entropy,
)
from eval.scenarios import generate  # noqa: E402

cfg = load_config()
dirs = config_dirs(cfg)
scenarios = generate(cfg)
by_id = {s["scenario_id"]: s for s in scenarios}

stress_ids = set()
with open(dirs["stress_path"], encoding="utf-8") as fh:
    for line in fh:
        stress_ids.add(json.loads(line)["scenario_id"])

ABLATIONS = ["full_equal", "no_weather", "no_climate", "no_soil", "no_risk", "no_season"]
SENS = [f"sens_{d}_{s}" for d in ["rainfall", "temperature", "soil", "season", "risk"] for s in ["plus", "minus"]]


def metrics_for(grid: Path) -> dict:
    files = list(grid.glob("*.json"))
    c3: dict[str, list[str]] = {}
    by_district: dict[str, list[list[str]]] = defaultdict(list)
    by_season: dict[str, list[list[str]]] = defaultdict(list)
    abl: dict[str, dict[str, list[str]]] = {a: {} for a in ABLATIONS}
    sens: dict[str, dict[str, list[str]]] = {s: {} for s in SENS}
    for path in files:
        res = json.loads(path.read_text(encoding="utf-8"))
        ab = res.get("ablations", {})
        fr = ab.get("full_repo")
        if not fr or "error" in fr or not fr.get("top5"):
            continue
        sid = path.stem
        top5 = fr["top5"]
        c3[sid] = top5
        by_district[res.get("district", "")].append(top5)
        by_season[res.get("season", "")].append(top5)
        for a in ABLATIONS:
            v = ab.get(a)
            if v and "error" not in v and v.get("top5"):
                abl[a][sid] = v["top5"]
        for s in SENS:
            v = ab.get(s)
            if v and "error" not in v and v.get("top5"):
                sens[s][sid] = v["top5"]

    sv_all, sv_stress, sv_normal = [], [], []
    for sid, top5 in c3.items():
        sv = season_validity_rate(top5, by_id[sid]["season_stratum"])
        sv_all.append(sv)
        (sv_stress if sid in stress_ids else sv_normal).append(sv)

    return {
        "n_scenarios": len(c3),
        "c3_distinct_crops": distinct_crops(list(c3.values())),
        "c3_shannon_entropy": float(shannon_entropy(list(c3.values()))),
        "c3_per_district_differentiation": float(per_district_differentiation(by_district)),
        "c3_season_validity_overall": float(np.mean(sv_all)),
        "c3_season_validity_stress": float(np.mean(sv_stress)),
        "c3_season_validity_normal": float(np.mean(sv_normal)),
        "n_stress": len(sv_stress),
        "n_normal": len(sv_normal),
        "per_season": {
            s: {"n": len(by_season.get(s, [])),
                "validity": float(np.mean([season_validity_rate(p, s) for p in by_season.get(s, [])])) if by_season.get(s) else 0}
            for s in ["Kharif", "Rabi", "Zaid"]
        },
        "ablation_jaccard_vs_full": {
            a: (float(np.mean([jaccard_similarity(p, c3[sid]) for sid, p in v.items() if sid in c3])) if v else None)
            for a, v in abl.items()
        },
        "weight_sensitivity_jaccard_vs_full": {
            s: (float(np.mean([jaccard_similarity(p, c3[sid]) for sid, p in v.items() if sid in c3])) if v else None)
            for s, v in sens.items()
        },
    }


before = metrics_for(Path("eval/runs/adhoc/deterministic"))
after = metrics_for(Path("eval/runs/archive_v2/deterministic"))

print("=== adhoc/deterministic (BEFORE) ===")
print(json.dumps(before, indent=2))
print("=== archive_v2/deterministic (AFTER) ===")
print(json.dumps(after, indent=2))

print("\n=== DIFF (after - before) ===")


def walk(a, b, p=""):
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            walk(a.get(k), b.get(k), f"{p}.{k}" if p else k)
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if abs(a - b) > 1e-12:
            print(f"  {p}: {a} -> {b}  (delta {b - a:+.6f})")
    else:
        if a != b:
            print(f"  {p}: {a} -> {b}")


walk(before, after)

out = {"before_adhoc": before, "after_archive_v2": after}
Path("eval/results/_det_source_before_after.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
print("\nwrote eval/results/_det_source_before_after.json")
