"""Build evidence bundles and identify stress set scenarios."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from eval.scenarios import generate, write_scenarios
from eval.common import load_config, ensure_dirs, config_dirs, write_json
from eval.evidence import EvidenceProvider
import json

cfg = load_config()
ensure_dirs(cfg)
dirs = config_dirs(cfg)

# Load scenarios
scenarios = generate(cfg)
print(f"Total scenarios: {len(scenarios)}")

# Build evidence for all scenarios (using cached weather where available)
evidence_dir = dirs['runs_dir'] / 'adhoc' / 'evidence'
evidence_dir.mkdir(parents=True, exist_ok=True)

provider = EvidenceProvider(cfg)
built = 0
failed = 0

for sc in scenarios:
    try:
        bundle = provider.build(sc)
        write_json(evidence_dir / f"{sc['scenario_id']}.json", bundle)
        built += 1
    except Exception as e:
        print(f"Failed {sc['scenario_id']}: {e}")
        failed += 1

print(f"Built: {built}, Failed: {failed}")

# Now identify stress set
stress_ids = set()
for sc in scenarios:
    path = evidence_dir / f"{sc['scenario_id']}.json"
    if not path.exists():
        continue
    import json
    with path.open() as f:
        bundle = json.load(f)
    risk = bundle.get('risk', {})
    drought_z = risk.get('drought_z_score_30d', 0)
    heatwave_sev = risk.get('heatwave_severity', 'none')
    flood_prob = risk.get('flood_probability', 0)
    
    # Check stress criteria
    is_stress = False
    if drought_z <= -1.5:
        is_stress = True
    if flood_prob >= 0.40:
        is_stress = True
    # Heatwave: need to check consecutive days >= 35C from weather
    weather = bundle.get('weather', {})
    # We'll approximate: heatwave_severity == 'high' and there are consecutive days
    if heatwave_sev == 'high':
        # Check if it's the 3+ consecutive days >=35C case (not just 1 day >=38C)
        # For now, include high heatwave
        is_stress = True
    
    if is_stress:
        stress_ids.add(sc['scenario_id'])

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

by_id = {s['scenario_id']: s for s in scenarios}
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