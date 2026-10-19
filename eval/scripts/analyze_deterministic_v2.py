"""Phase 8: C3 + ablation + weight-sensitivity metrics from v2 deterministic outputs.

Reads eval/runs/archive_v2/deterministic/<sid>.json and writes (after archiving the old
one) the canonical eval/results/c3_deterministic_summary.json consumed by Fig14.
Reported season validity is against the scenario's true (as_of-based) season stratum,
identical to analyze_deterministic_full.py.
"""

from __future__ import annotations

import json
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from eval.common import config_dirs, load_config, write_json  # noqa: E402
from eval.metrics import (  # noqa: E402
    distinct_crops,
    jaccard_similarity,
    per_district_differentiation,
    season_validity_rate,
    shannon_entropy,
)
from eval.scenarios import generate  # noqa: E402

import numpy as np

cfg = load_config()
dirs = config_dirs(cfg)
scenarios = generate(cfg)
by_id = {s["scenario_id"]: s for s in scenarios}

stress_ids = set()
with open(dirs["stress_path"], encoding="utf-8") as fh:
    for line in fh:
        stress_ids.add(json.loads(line)["scenario_id"])

DET_DIR = Path("eval/runs/archive_v2/deterministic")
files = list(DET_DIR.glob("*.json"))
print(f"v2 deterministic files: {len(files)}")

c3_preds: dict[str, list[str]] = {}
c3_by_district: dict[str, list[list[str]]] = defaultdict(list)
c3_by_season: dict[str, list[list[str]]] = defaultdict(list)
district_of: dict[str, str] = {}

for path in files:
    with path.open(encoding="utf-8") as fh:
        res = json.load(fh)
    ab = res.get("ablations", {}).get("full_repo")
    if not ab or "error" in ab or not ab.get("top5"):
        continue
    sid = path.stem
    top5 = ab["top5"]
    c3_preds[sid] = top5
    district_of[sid] = res.get("district", "")
    c3_by_district[district_of[sid]].append(top5)
    c3_by_season[res.get("season", "")].append(top5)

print(f"C3 scenarios: {len(c3_preds)}")
print(f"Distinct crops: {distinct_crops(list(c3_preds.values()))}")
print(f"Shannon entropy: {shannon_entropy(list(c3_preds.values())):.4f}")
print(f"Per-district diff: {per_district_differentiation(c3_by_district):.4f}")

season_valid, stress_season_valid, normal_season_valid = [], [], []
for sid, top5 in c3_preds.items():
    sv = season_validity_rate(top5, by_id[sid]["season_stratum"])
    season_valid.append(sv)
    (stress_season_valid if sid in stress_ids else normal_season_valid).append(sv)

print(f"Season validity overall: {np.mean(season_valid):.4f} (n={len(season_valid)})")
print(f"Season validity stress: {np.mean(stress_season_valid):.4f} (n={len(stress_season_valid)})")
print(f"Season validity normal: {np.mean(normal_season_valid):.4f} (n={len(normal_season_valid)})")
print("\nPer-season breakdown:")
for season in ["Kharif", "Rabi", "Zaid"]:
    preds = c3_by_season.get(season, [])
    if preds:
        sv = [season_validity_rate(p, season) for p in preds]
        print(f"  {season}: n={len(preds)}, validity={np.mean(sv):.4f}")

print("\n=== Ablation Analysis (Jaccard vs full_repo, v2) ===")
ablation_names = ["full_equal", "no_weather", "no_climate", "no_soil", "no_risk", "no_season"]
ablation_results: dict[str, dict[str, list[str]]] = {}
for ab_name in ablation_names:
    ab_preds: dict[str, list[str]] = {}
    for path in files:
        with path.open(encoding="utf-8") as fh:
            res = json.load(fh)
        ab = res.get("ablations", {}).get(ab_name)
        if not ab or "error" in ab or not ab.get("top5"):
            continue
        ab_preds[path.stem] = ab["top5"]
    ablation_results[ab_name] = ab_preds
    jac = [jaccard_similarity(pred, c3_preds[sid]) for sid, pred in ab_preds.items() if sid in c3_preds]
    print(f"  {ab_name}: n={len(ab_preds)}, mean Jaccard={np.mean(jac):.4f}" if jac else f"  {ab_name}: n=0")

print("\n=== Weight Sensitivity (Jaccard vs full_repo, v2) ===")
sens_rows = {}
for dim in ["rainfall", "temperature", "soil", "season", "risk"]:
    for direction in ["plus", "minus"]:
        ab_name = f"sens_{dim}_{direction}"
        jacs = []
        for path in files:
            with path.open(encoding="utf-8") as fh:
                res = json.load(fh)
            ab = res.get("ablations", {}).get(ab_name)
            if not ab or "error" in ab or not ab.get("top5"):
                continue
            sid = path.stem
            if sid in c3_preds:
                jacs.append(jaccard_similarity(ab["top5"], c3_preds[sid]))
        if jacs:
            sens_rows[ab_name] = float(np.mean(jacs))
            print(f"  {ab_name}: mean Jaccard={np.mean(jacs):.4f} (n={len(jacs)})")

# Archive the old canonical summary (do not delete), then write the new one.
summary_path = dirs["results_dir"] / "c3_deterministic_summary.json"
archive_dir = Path("eval/runs/archive_v2/previous_v1")
archive_dir.mkdir(parents=True, exist_ok=True)
if summary_path.exists():
    shutil.copy2(summary_path, archive_dir / f"c3_deterministic_summary.v1.{summary_path.stat().st_mtime:.0f}.json")
    print(f"archived old summary -> {archive_dir}")

summary = {
    "phase": 8,
    "evidence_version": 2,
    "week_anchored_to": "as_of_date",
    "c3_distinct_crops": distinct_crops(list(c3_preds.values())),
    "c3_shannon_entropy": float(shannon_entropy(list(c3_preds.values()))),
    "c3_per_district_differentiation": float(per_district_differentiation(c3_by_district)),
    "c3_season_validity_overall": float(np.mean(season_valid)),
    "c3_season_validity_stress": float(np.mean(stress_season_valid)) if stress_season_valid else 0,
    "c3_season_validity_normal": float(np.mean(normal_season_valid)) if normal_season_valid else 0,
    "n_scenarios": len(c3_preds),
    "n_stress": len(stress_season_valid),
    "n_normal": len(normal_season_valid),
    "per_season": {
        s: {
            "n": len(c3_by_season.get(s, [])),
            "validity": float(np.mean([season_validity_rate(p, s) for p in c3_by_season.get(s, [])]))
            if c3_by_season.get(s) else 0,
        }
        for s in ["Kharif", "Rabi", "Zaid"]
    },
    "ablation_jaccard_vs_full": {k: float(np.mean(
        [jaccard_similarity(pred, c3_preds[sid]) for sid, pred in v.items() if sid in c3_preds]
    )) if any(sid in c3_preds for sid in v) else None for k, v in ablation_results.items()},
    "weight_sensitivity_jaccard_vs_full": sens_rows,
    "config_shasum_note": "config.yaml modified in Phase 8 STEP A (max_tool_rounds); v2 runs carry new run ID",
    "generated_at": datetime.now(timezone.utc).isoformat(),
}
write_json(summary_path, summary)
print(f"\nSummary saved to {summary_path}")