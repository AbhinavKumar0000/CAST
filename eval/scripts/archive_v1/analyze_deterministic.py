"""RETIRED (v1). Superseded by eval/scripts/analyze_deterministic_v2.py, the sole
writer of the canonical eval/results/c3_deterministic_summary.json. This copy
reads the frozen v2 grid but MUST NOT touch the canonical summary: it writes the
v1-suffixed file c3_deterministic_summary.v1.json instead.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from eval.common import load_config, ensure_dirs, config_dirs, write_json, read_jsonl, ResultMeta
from eval.scenarios import generate
from eval.metrics import (
    accuracy_at_k, precision_at_k, recall_at_k, ndcg_at_k, mrr,
    season_validity_rate, hard_violation_rate, distinct_crops,
    shannon_entropy, per_district_differentiation, hallucination_rate,
    numeric_faithfulness, jaccard_similarity, kendall_tau, exact_match_rate
)
from eval.statistics import (
    bootstrap_ci, wilcoxon_paired, mcnemar_paired, holm_bonferroni,
    cliffs_delta, cohens_d, compare_conditions
)

cfg = load_config()
ensure_dirs(cfg)
dirs = config_dirs(cfg)

# Load scenarios
scenarios = generate(cfg)
by_id = {s['scenario_id']: s for s in scenarios}

# Load stress set
stress_ids = set()
stress_path = dirs['stress_path']
if stress_path.exists():
    with stress_path.open() as f:
        for line in f:
            stress_ids.add(json.loads(line)['scenario_id'])

# Load deterministic results
det_dir = dirs['runs_dir'] / 'archive_v2' / 'deterministic'
det_results = {}
for path in det_dir.glob('*.json'):
    with path.open() as f:
        det_results[path.stem] = json.load(f)

print(f"Loaded {len(det_results)} deterministic results")

# C3 results (full_repo ablation)
c3_preds = {}
c3_by_district = defaultdict(list)
c3_by_season = defaultdict(list)
c3_by_stress = defaultdict(list)

for sid, res in det_results.items():
    if 'full_repo' not in res.get('ablations', {}):
        continue
    ab = res['ablations']['full_repo']
    if 'error' in ab:
        continue
    top5 = ab['top5']
    c3_preds[sid] = top5
    district = res.get('district', '')
    season = res.get('season', '')
    c3_by_district[district].append(top5)
    c3_by_season[season].append(top5)
    c3_by_stress['stress' if sid in stress_ids else 'normal'].append(top5)

print(f"C3 scenarios with predictions: {len(c3_preds)}")

# Compute deterministic metrics (no ground truth - internal registry only)
print("\n=== C3 Deterministic Metrics ===")

# Specificity metrics
print(f"Distinct crops: {distinct_crops(list(c3_preds.values()))}")
print(f"Shannon entropy: {shannon_entropy(list(c3_preds.values())):.4f}")
print(f"Per-district differentiation: {per_district_differentiation(c3_by_district):.4f}")

# Safety metrics (internal season validity)
season_valid = []
for sid, top5 in c3_preds.items():
    season = by_id[sid]['season_stratum']
    sv = season_validity_rate(top5, season)
    season_valid.append(sv)
print(f"Season validity rate (overall): {np.mean(season_valid):.4f}")

stress_season_valid = []
normal_season_valid = []
for sid, top5 in c3_preds.items():
    season = by_id[sid]['season_stratum']
    sv = season_validity_rate(top5, season)
    if sid in stress_ids:
        stress_season_valid.append(sv)
    else:
        normal_season_valid.append(sv)
print(f"Season validity (stress): {np.mean(stress_season_valid):.4f}")
print(f"Season validity (normal): {np.mean(normal_season_valid):.4f}")

# Ablation analysis
print("\n=== Ablation Analysis (C3 variants) ===")
ablation_names = ['full_repo', 'full_equal', 'no_weather', 'no_climate', 'no_soil', 'no_risk', 'no_season']

for ab_name in ablation_names:
    ab_preds = {}
    for sid, res in det_results.items():
        if ab_name not in res.get('ablations', {}):
            continue
        ab = res['ablations'][ab_name]
        if 'error' in ab:
            continue
        ab_preds[sid] = ab['top5']
    
    if not ab_preds:
        print(f"  {ab_name}: NO DATA")
        continue
    
    # Compare to full_repo
    if ab_name != 'full_repo' and 'full_repo' in [a for r in det_results.values() for a in r.get('ablations', {})]:
        # Jaccard similarity
        jaccards = []
        for sid in ab_preds:
            if sid in c3_preds:
                jaccards.append(jaccard_similarity(ab_preds[sid], c3_preds[sid]))
        print(f"  {ab_name}: n={len(ab_preds)}, Jaccard vs full_repo={np.mean(jaccards):.4f}")
    else:
        print(f"  {ab_name}: n={len(ab_preds)}")

# Sensitivity analysis
print("\n=== Weight Sensitivity ===")
for dim in ['rainfall', 'temperature', 'soil', 'season', 'risk']:
    for direction in ['plus', 'minus']:
        ab_name = f'sens_{dim}_{direction}'
        ab_preds = {}
        for sid, res in det_results.items():
            if ab_name not in res.get('ablations', {}):
                continue
            ab = res['ablations'][ab_name]
            if 'error' in ab:
                continue
            ab_preds[sid] = ab['top5']
        if ab_preds:
            jaccards = [jaccard_similarity(ab_preds[sid], c3_preds[sid]) for sid in ab_preds if sid in c3_preds]
            print(f"  {ab_name}: Jaccard vs full_repo={np.mean(jaccards):.4f}")

# Save summary
summary = {
    "c3_distinct_crops": distinct_crops(list(c3_preds.values())),
    "c3_shannon_entropy": shannon_entropy(list(c3_preds.values())),
    "c3_per_district_differentiation": per_district_differentiation(c3_by_district),
    "c3_season_validity_overall": float(np.mean(season_valid)),
    "c3_season_validity_stress": float(np.mean(stress_season_valid)) if stress_season_valid else 0,
    "c3_season_validity_normal": float(np.mean(normal_season_valid)) if normal_season_valid else 0,
    "n_scenarios": len(c3_preds),
    "n_stress": len(stress_season_valid),
    "n_normal": len(normal_season_valid),
}

meta = ResultMeta.build(cfg, "deterministic_analysis")
summary["meta"] = meta.as_dict()

write_json(dirs['results_dir'] / "c3_deterministic_summary.v1.json", summary)
print(f"\nSummary saved to {dirs['results_dir'] / 'c3_deterministic_summary.v1.json'}")