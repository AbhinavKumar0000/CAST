"""RETIRED (v1). Superseded by eval/scripts/analyze_deterministic_v2.py, the sole
writer of the canonical eval/results/c3_deterministic_summary.json. This copy
reads the frozen v2 grid but MUST NOT touch the canonical summary: it writes the
v1-suffixed file c3_deterministic_summary.v1.json instead.
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from eval.common import load_config, ensure_dirs, config_dirs, write_json, ResultMeta
from eval.scenarios import generate
from eval.metrics import (
    distinct_crops, shannon_entropy, per_district_differentiation, 
    season_validity_rate, jaccard_similarity
)
import numpy as np

cfg = load_config()
ensure_dirs(cfg)
dirs = config_dirs(cfg)

scenarios = generate(cfg)
by_id = {s['scenario_id']: s for s in scenarios}

# Load stress set
stress_ids = set()
with open(dirs['stress_path']) as f:
    for line in f:
        stress_ids.add(json.loads(line)['scenario_id'])

det_dir = dirs['runs_dir'] / 'archive_v2' / 'deterministic'
files = list(det_dir.glob('*.json'))
print(f"Processing {len(files)} files...")

c3_preds = {}
c3_by_district = defaultdict(list)
c3_by_season = defaultdict(list)

for i, path in enumerate(files):
    with path.open() as f:
        res = json.load(f)
    if 'full_repo' not in res.get('ablations', {}):
        continue
    ab = res['ablations']['full_repo']
    if 'error' in ab:
        continue
    sid = path.stem
    top5 = ab['top5']
    c3_preds[sid] = top5
    district = res.get('district', '')
    season = res.get('season', '')
    c3_by_district[district].append(top5)
    c3_by_season[season].append(top5)
    
    if (i + 1) % 2000 == 0:
        print(f"  {i + 1}/{len(files)}")

print(f"\nC3 scenarios: {len(c3_preds)}")

# Overall metrics
print(f"Distinct crops: {distinct_crops(list(c3_preds.values()))}")
print(f"Shannon entropy: {shannon_entropy(list(c3_preds.values())):.4f}")
print(f"Per-district diff: {per_district_differentiation(c3_by_district):.4f}")

# Season validity
season_valid = []
stress_season_valid = []
normal_season_valid = []
for sid, top5 in c3_preds.items():
    season = by_id[sid]['season_stratum']
    sv = season_validity_rate(top5, season)
    season_valid.append(sv)
    if sid in stress_ids:
        stress_season_valid.append(sv)
    else:
        normal_season_valid.append(sv)

print(f"Season validity overall: {np.mean(season_valid):.4f} (n={len(season_valid)})")
print(f"Season validity stress: {np.mean(stress_season_valid):.4f} (n={len(stress_season_valid)})")
print(f"Season validity normal: {np.mean(normal_season_valid):.4f} (n={len(normal_season_valid)})")

# Per-season breakdown
print("\nPer-season breakdown:")
for season in ['Kharif', 'Rabi', 'Zaid']:
    preds = c3_by_season.get(season, [])
    if preds:
        sv = [season_validity_rate(p, season) for p in preds]
        print(f"  {season}: n={len(preds)}, validity={np.mean(sv):.4f}")

# Ablation comparison
print("\n=== Ablation Analysis ===")
ablation_names = ['full_repo', 'full_equal', 'no_weather', 'no_climate', 'no_soil', 'no_risk', 'no_season']

ablation_preds = {}
for ab_name in ablation_names:
    ab_preds = {}
    for path in files:
        with path.open() as f:
            res = json.load(f)
        if ab_name not in res.get('ablations', {}):
            continue
        ab = res['ablations'][ab_name]
        if 'error' in ab:
            continue
        sid = path.stem
        ab_preds[sid] = ab['top5']
    ablation_preds[ab_name] = ab_preds
    print(f"  {ab_name}: {len(ab_preds)} scenarios")

# Jaccard vs full_repo
print("\nJaccard similarity vs full_repo:")
for ab_name in ['full_equal', 'no_weather', 'no_climate', 'no_soil', 'no_risk', 'no_season']:
    ab_preds = ablation_preds[ab_name]
    jaccards = []
    for sid, pred in ab_preds.items():
        if sid in c3_preds:
            jaccards.append(jaccard_similarity(pred, c3_preds[sid]))
    if jaccards:
        print(f"  {ab_name}: mean Jaccard = {np.mean(jaccards):.4f} (n={len(jaccards)})")

# Sensitivity analysis
print("\n=== Weight Sensitivity ===")
for dim in ['rainfall', 'temperature', 'soil', 'season', 'risk']:
    for direction in ['plus', 'minus']:
        ab_name = f'sens_{dim}_{direction}'
        ab_preds = {}
        for path in files:
            with path.open() as f:
                res = json.load(f)
            if ab_name not in res.get('ablations', {}):
                continue
            ab = res['ablations'][ab_name]
            if 'error' in ab:
                continue
            sid = path.stem
            ab_preds[sid] = ab['top5']
        if ab_preds:
            jaccards = [jaccard_similarity(ab_preds[sid], c3_preds[sid]) for sid in ab_preds if sid in c3_preds]
            print(f"  {ab_name}: mean Jaccard = {np.mean(jaccards):.4f} (n={len(jaccards)})")

# Save summary
summary = {
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
            "validity": float(np.mean([season_validity_rate(p, s) for p in c3_by_season.get(s, [])])) if c3_by_season.get(s) else 0
        } for s in ['Kharif', 'Rabi', 'Zaid']
    }
}

meta = ResultMeta.build(cfg, "deterministic_analysis")
summary["meta"] = meta.as_dict()

write_json(dirs['results_dir'] / "c3_deterministic_summary.v1.json", summary)
print(f"\nSummary saved to {dirs['results_dir'] / 'c3_deterministic_summary.v1.json'}")