"""Identify stress set from built evidence and create LLM subset."""

import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from eval.scenarios import generate
from eval.common import load_config, ensure_dirs, config_dirs

cfg = load_config()
ensure_dirs(cfg)
dirs = config_dirs(cfg)

# Load all scenarios
scenarios = generate(cfg)
by_id = {s['scenario_id']: s for s in scenarios}

# Identify stress set from evidence files
evidence_dir = dirs['runs_dir'] / 'archive_v2' / 'evidence'  # canonical v2 bundles (was: adhoc/evidence)
stress_ids = set()

for path in evidence_dir.glob('*.json'):
    with path.open() as f:
        bundle = json.load(f)
    
    risk = bundle.get('risk', {})
    drought_z = risk.get('drought_z_score_30d', 0)
    heatwave_sev = risk.get('heatwave_severity', 'none')
    flood_prob = risk.get('flood_probability', 0)
    
    is_stress = False
    if drought_z <= -1.5:
        is_stress = True
    if flood_prob >= 0.40:
        is_stress = True
    if heatwave_sev == 'high':
        is_stress = True
    
    if is_stress:
        stress_ids.add(bundle['scenario_id'])

print(f"Stress set size: {len(stress_ids)}")

# Write stress set
stress_path = dirs['stress_path']
stress_scenarios = [s for s in scenarios if s['scenario_id'] in stress_ids]
with stress_path.open('w') as f:
    for s in stress_scenarios:
        f.write(json.dumps(s) + '\n')
print(f"Wrote stress set to {stress_path}")

# Build LLM subset
import numpy as np
rng = np.random.default_rng(int(cfg['seeds']['llm_subset_sampling']))
n = int(cfg['scenarios']['llm_subset']['n'])
min_stress = int(cfg['scenarios']['llm_subset']['min_stress'])

stress_list = [s for s in scenarios if s['scenario_id'] in stress_ids]
non_stress_list = [s for s in scenarios if s['scenario_id'] not in stress_ids]

rng.shuffle(stress_list)
rng.shuffle(non_stress_list)

chosen_stress = stress_list[:min(min_stress, len(stress_list))]
remaining = n - len(chosen_stress)
chosen_non = non_stress_list[:remaining]

if len(chosen_non) < remaining:
    extra = stress_list[len(chosen_stress):len(chosen_stress) + (remaining - len(chosen_non))]
    chosen_stress += extra

subset = chosen_stress + chosen_non
subset.sort(key=lambda s: s['scenario_id'])

llm_subset_path = dirs['llm_subset_path']
with llm_subset_path.open('w') as f:
    for s in subset:
        f.write(json.dumps(s) + '\n')
print(f"LLM subset: {len(subset)} rows ({len(chosen_stress)} stress)")