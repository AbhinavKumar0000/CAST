"""Phase 8 STEP C review item 1c: diagnose why C3 ranks Barley first in every Rabi
scenario. Uses only local artifacts (v2 evidence bundles + deterministic top5), no
APIs, no climate/scoring code changes.

Prints:
  * top-1 crop distribution per season (from deterministic v2 full_repo top5)
  * Rabi margin stats: Barley vs runner-up score gap, runner-up identity
  * a few example Rabi scenarios with full component breakdown
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from eval.common import config_dirs, load_config
from eval.scenarios import generate

cfg = load_config()
dirs = config_dirs(cfg)
scenarios = generate(cfg)
by_id = {s["scenario_id"]: s for s in scenarios}

DET_DIR = Path("eval/runs/archive_v2/deterministic")
EVID_DIR = Path("eval/runs/archive_v2/evidence")


def parse_range(value: str) -> tuple[float, float] | None:
    nums = re.findall(r"[\d.]+", value or "")
    if not nums:
        return None
    vals = [float(v) for v in nums]
    return (min(vals), max(vals))


def main() -> None:
    # 1) top-1 distribution per season from deterministic v2 files.
    season_top1: dict[str, Counter[str, int]] = defaultdict(Counter)
    n_det = 0
    for path in DET_DIR.glob("*.json"):
        with path.open(encoding="utf-8") as fh:
            res = json.load(fh)
        ab = res.get("ablations", {}).get("full_repo")
        if not ab or not ab.get("top5"):
            continue
        season = res.get("season") or by_id.get(path.stem, {}).get("season_stratum", "?")
        season_top1[season][ab["top5"][0]] += 1
        n_det += 1
    print(f"Deterministic v2 scenarios: {n_det}\n")
    print("Top-1 crop distribution per season:")
    for season, ctr in season_top1.items():
        total = sum(ctr.values())
        top = ctr.most_common()
        s = ", ".join(f"{c}={n} ({100*n/total:.1f}%)" for c, n in top[:6])
        print(f"  {season:7s} n={total:5d}: {s}")
        if len(top) > 6:
            s2 = ", ".join(f"{c}={n}" for c, n in top[6:])
            print(f"           ... rest: {s2}")

    # 2) Rabi margins from evidence bundles.
    print("\n===== Rabi margin analysis (from time-anchored evidence bundles) =====")
    margins: list[float] = []
    runner_up: Counter[str, int] = Counter()
    barley_first = 0
    n_rabi = 0
    diffs = defaultdict(list)      # component gap Barley - runner_up
    by_week_bucket: dict[str, list[float]] = defaultdict(list)
    examples: list[dict] = []

    for path in EVID_DIR.glob("*.json"):
        with path.open(encoding="utf-8") as fh:
            ev = json.load(fh)
        sid = path.stem
        season = ev.get("season") or {}
        if season.get("current_season") != "Rabi":
            continue
        n_rabi += 1
        ranked = (ev.get("crop_score") or {}).get("ranked_crops") or []
        if not ranked:
            continue
        top = ranked[0]
        second = ranked[1] if len(ranked) > 1 else None
        if not second:
            continue
        if top["crop"] == "Barley":
            barley_first += 1
            margin = round(top["total_score"] - second["total_score"], 3)
            margins.append(margin)
            runner_up[second["crop"]] += 1
            for k in ("rainfall_match", "temperature_match", "soil_type_match",
                      "season_alignment", "risk_penalty"):
                diffs[k].append(round(top["scores"][k] - second["scores"][k], 3))
            sc = by_id.get(sid, {})
            wk = int(sc.get("as_of_date", "2026-01-15")[5:7])
            bucket = "Nov-Dec" if wk in (11, 12) else "Jan-Feb" if wk in (1, 2) else "Mar"
            by_week_bucket[bucket].append(margin)
            if len(examples) < 3 or (7 <= len(margins) <= 200 and len(examples) < 6):
                examples.append({
                    "sid": sid, "district": sc.get("district"), "as_of": sc.get("as_of_date"),
                    "margin": margin, "top": top, "second": second,
                })

    import numpy as np
    print(f"Rabi scenarios evaluated: {n_rabi}; Barley is #1 in {barley_first} "
          f"({100*barley_first/max(n_rabi,1):.1f}%)\n")
    if margins:
        arr = np.array(margins)
        print(f"Margin (Barley - runner-up): mean={arr.mean():.4f} median={np.median(arr):.4f} "
              f"min={arr.min():.4f} max={arr.max():.4f}")
        print(f"  margin<0.01 (near ties): {int((arr < 0.01).sum())}/{len(arr)}")
        print(f"Runner-up crop counts: {dict(runner_up.most_common(6))}")
        print("Mean component gaps (Barley - runner-up): "
              + ", ".join(f"{k}={np.mean(v):+.3f}" for k, v in diffs.items()))
        print("Margin by month bucket: "
              + ", ".join(f"{k}: n={len(v)} mean={np.mean(v):.4f}" for k, v in by_week_bucket.items()))

    print("\n----- example scenarios (components) -----")
    for ex in examples[:6]:
        t, s = ex["top"], ex["second"]
        print(f"\n{sid} {ex['district']} as_of={ex['as_of']} margin={ex['margin']}")
        for label, c in (("#1", t), ("#2", s)):
            scs = c["scores"]
            print(f"  {label} {c['crop']:8s} total={c['total_score']:.3f} | rain={scs['rainfall_match']:.2f} "
                  f"temp={scs['temperature_match']:.2f} soil={scs['soil_type_match']:.2f} "
                  f"season={scs['season_alignment']:.2f} risk={scs['risk_penalty']:.2f} "
                  f"win={c['sowing_window']['start_week']}-{c['sowing_window']['end_week']} "
                  f"peak={c['peak_water_week']}")

    # 3) The decisive scoring facts (from crop_log.csv + scorer code, no changes).
    print("\n===== Why Barley leads (scoring mechanics) =====")
    with open("crop_log.csv", encoding="utf-8", newline="") as fh:
        crops = {r["Crop"]: r for r in csv.DictReader(fh)}
    b = crops["Barley"]
    print(f"Barley registry row: season={b['season_supported']} rain={b['Rainfall']} "
          f"temp={b['Tempreture']} soil='{b['Soil Type']}' risk='{b['risk_sensitivity']}' "
          f"sow={b['sowing_start_week']}-{b['sowing_end_week']} peak_water_week={b['peak_water_week']}")

if __name__ == "__main__":
    main()