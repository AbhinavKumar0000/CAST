"""Phase 8 STEP C: recompute C3 season-validity and hard-violation rates using the
independent, source-cited ground-truth tables (eval/data/ground_truth/).

Registry-based season validity (metrics.CROP_SEASON_VALIDITY, from crop_log.csv) stays
in c3_deterministic_summary.json as the *internal* metric. This script emits the
*external* (cited) metric to eval/results/c3_season_validity_cited.json. UNVERIFIED
rows in the tables are reported separately and excluded from cited-only aggregates.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import numpy as np

from eval.common import config_dirs, load_config, write_json
from eval.scenarios import generate

cfg = load_config()
dirs = config_dirs(cfg)
scenarios = generate(cfg)
by_id = {s["scenario_id"]: s for s in scenarios}

stress_ids = set()
with open(dirs["stress_path"], encoding="utf-8") as fh:
    for line in fh:
        stress_ids.add(json.loads(line)["scenario_id"])

# Stress/drought/flood flags come from the v2 evidence bundles' risk output (the
# deterministic files do not embed tool payloads).
EVID_DIR = Path("eval/runs/archive_v2/evidence")
risk_flags: dict[str, dict[str, bool]] = {}
for path in EVID_DIR.glob("*.json"):
    with path.open(encoding="utf-8") as fh:
        ev = json.load(fh)
    risk = ev.get("risk") or {}
    try:
        d = float(risk.get("drought_z_score_30d", 0)) <= -1.5
        f = float(risk.get("flood_probability", 0)) >= 0.40
    except (TypeError, ValueError):
        d, f = False, False
    risk_flags[ev.get("scenario_id")] = {"drought": d, "flood": f}

DET_DIR = Path("eval/runs/archive_v2/deterministic")
GT_DIR = Path("eval/data/ground_truth")


def read_table(name: str) -> list[dict[str, str]]:
    with (GT_DIR / name).open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


season_rows = read_table("crop_season_table.csv")
constraint_rows = read_table("hard_constraints.csv")

# Valid seasons per crop from the CITED rows only.
valid_cited: dict[str, set[str]] = defaultdict(set)
valid_all: dict[str, set[str]] = defaultdict(set)
for r in season_rows:
    crop = r["crop"]
    valid_all[crop].add(r["season"])
    if r["status"] == "cited":
        valid_cited[crop].add(r["season"])


def season_validity(top5: list[str], season: str, valid: dict[str, set[str]]) -> float:
    if not top5:
        return 0.0
    return sum(1 for p in top5 if season in valid.get(p, set())) / len(top5)


# Hard constraints: season type + environmental type.
hard_season: list[dict[str, str]] = [r for r in constraint_rows if r["constraint_type"] == "season"]
hard_drought: list[dict[str, str]] = [r for r in constraint_rows if r["constraint_type"] == "drought"]
hard_flood: list[dict[str, str]] = [r for r in constraint_rows if r["constraint_type"] == "flood"]

c3_preds: dict[str, list[str]] = {}
c3_by_season: dict[str, list[list[str]]] = defaultdict(list)

files = list(DET_DIR.glob("*.json"))
for path in files:
    with path.open(encoding="utf-8") as fh:
        res = json.load(fh)
    ab = res.get("ablations", {}).get("full_repo")
    if not ab or "error" in ab or not ab.get("top5"):
        continue
    sid = path.stem
    c3_preds[sid] = ab["top5"]
    c3_by_season[res.get("season", "")].append(ab["top5"])

print(f"v2 deterministic C3 scenarios: {len(c3_preds)}")


def hard_violation_crops(top5: list[str], season: str, drought: bool, flood: bool,
                         cited_only: bool) -> tuple[int, int]:
    """Return (violating crops, total crops evaluated) under the hard table.

    Cited-only mode ignores UNVERIFIED constraint rows.
    """
    viol, total = 0, 0
    for p in top5:
        if p not in valid_cited and p not in valid_all:
            total += 1
            continue  # out-of-registry crop: counted in total, cannot validate
        total += 1
        if any(
            (not cited_only or r["status"] == "cited") and r["crop"] == p and season == r["condition"]
            for r in hard_season
        ):
            viol += 1
        if drought and any(
            (not cited_only or r["status"] == "cited") and r["crop"] == p for r in hard_drought
        ):
            viol += 1
        if flood and any(
            (not cited_only or r["status"] == "cited") and r["crop"] == p for r in hard_flood
        ):
            viol += 1
    return viol, total


for cited_only in (True, False):
    tag = "cited" if cited_only else "all_rows"
    season_valid, stress_valid, normal_valid = [], [], []
    hard_viol, hard_total = [], []
    for sid, top5 in c3_preds.items():
        sc = by_id[sid]
        season = sc["season_stratum"]
        flags = risk_flags.get(sid, {"drought": False, "flood": False})
        sv = season_validity(top5, season, valid_cited)  # season table: cited only for both modes
        season_valid.append(sv)
        (stress_valid if sid in stress_ids else normal_valid).append(sv)
        v, t = hard_violation_crops(top5, season, flags["drought"], flags["flood"], cited_only)
        hard_viol.append(v)
        hard_total.append(t)

    print(f"\n--- [{tag}] ---")
    print(f"Season validity overall: {np.mean(season_valid):.4f} (n={len(season_valid)})")
    print(f"  stress: {np.mean(stress_valid):.4f} ({len(stress_valid)}) | normal: {np.mean(normal_valid):.4f} ({len(normal_valid)})")
    for season in ["Kharif", "Rabi", "Zaid"]:
        preds = c3_by_season.get(season, [])
        if preds:
            sv = [season_validity(p, season, valid_cited) for p in preds]
            print(f"  {season}: n={len(preds)}, validity={np.mean(sv):.4f}")
    if hard_total:
        print(f"Hard-violation rate: {sum(hard_viol)}/{sum(hard_total)} = {sum(hard_viol) / max(sum(hard_total), 1):.4f}")

    summary = {
        "phase": 8,
        "source_table": "crop_season_table.csv (cited rows) + hard_constraints.csv",
        "mode": tag,
        "frozen_at": "2026-10-13",
        "n_scenarios": len(c3_preds),
        "n_stress": len(stress_valid),
        "n_normal": len(normal_valid),
        "season_validity_overall": float(np.mean(season_valid)),
        "season_validity_stress": float(np.mean(stress_valid)) if stress_valid else 0,
        "season_validity_normal": float(np.mean(normal_valid)) if normal_valid else 0,
        "per_season": {
            s: {
                "n": len(c3_by_season.get(s, [])),
                "validity": float(np.mean([
                    season_validity(p, s, valid_cited) for p in c3_by_season.get(s, [])
                ])) if c3_by_season.get(s) else 0,
            }
            for s in ["Kharif", "Rabi", "Zaid"]
        },
        "hard_violating_crops": int(sum(hard_viol)),
        "hard_total_evaluated": int(sum(hard_total)),
        "hard_violation_rate": float(sum(hard_viol) / max(sum(hard_total), 1)) if hard_total else None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    out = dirs["results_dir"] / "c3_season_validity_cited.json"
    summaries = []
    if out.exists():
        with out.open(encoding="utf-8") as fh:
            existing = json.load(fh)
        summaries = existing.get("modes", []) if isinstance(existing, dict) else existing
    summaries.append(summary)
    write_json(out, {"modes": summaries})
    print(f"Saved {tag} -> {out}")