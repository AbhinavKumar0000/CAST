"""Build remaining evidence bundles for missing districts."""
import json, sys, re, csv
from datetime import datetime
from pathlib import Path
import numpy as np
import pytz
sys.path.insert(0, '.')
from eval.common import load_config, ensure_dirs, config_dirs, write_json, ResultMeta
from eval.scenarios import generate
from eval.evidence import EvidenceProvider

cfg = load_config()
ensure_dirs(cfg)
dirs = config_dirs(cfg)

scenarios = generate(cfg)
evidence_dir = dirs['runs_dir'] / 'adhoc' / 'evidence'
evidence_files = set(f.stem for f in evidence_dir.glob('*.json'))

missing_districts = ['Sidhi', 'Singrauli', 'Tikamgarh', 'Ujjain', 'Umaria', 'Vidisha', 'West Nimar']
missing_scenarios = [s for s in scenarios if s['district'] in missing_districts and s['scenario_id'] not in evidence_files]

print('Building evidence for ' + str(len(missing_scenarios)) + ' missing scenarios...')

provider = EvidenceProvider(cfg)
built = 0
for i, sc in enumerate(missing_scenarios):
    if i % 200 == 0:
        print('  ' + str(i) + '/' + str(len(missing_scenarios)))
    try:
        bundle = provider.build(sc)
        write_json(evidence_dir / (sc['scenario_id'] + '.json'), bundle)
        built += 1
    except Exception as e:
        print('Failed ' + sc['scenario_id'] + ': ' + str(e))

print('Built ' + str(built) + ' additional evidence bundles')