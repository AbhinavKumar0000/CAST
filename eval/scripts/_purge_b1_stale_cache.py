"""Quarantine pre-fix Nemotron C1a/C2a/C2b cache records for the first-150 B1 scenarios.

B1 (run_model.py) caches by (model, condition, prompt, sid, repeat); the harness fix
(more output tokens for C1a/C1b + time-anchored C2) did NOT change those keys, so B1
would silently reuse pre-fix records (2 C1a are finish=length @4096; the C2a/C2b batch
predates the time-anchoring fix). Move them aside so B1 is a clean post-fix run.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

CACHE = ROOT / "eval/cache/llm/nemotron-3-ultra"
QUAR = ROOT / "eval/cache/llm/_quarantine_nemotron_prefix_20261014"
CONDS = {"C1a", "C2a", "C2b"}

subset = [json.loads(l) for l in (ROOT / "eval/data/llm_subset.jsonl")
          .read_text(encoding="utf-8").splitlines() if l.strip()][:150]
sidset = {s["scenario_id"] for s in subset}

QUAR.mkdir(parents=True, exist_ok=True)
moved = []
for fp in CACHE.glob("*.json"):
    try:
        r = json.load(fp.open(encoding="utf-8"))
    except Exception:
        continue
    if r.get("condition") in CONDS and r.get("scenario_id") in sidset:
        shutil.move(str(fp), str(QUAR / fp.name))
        moved.append((r.get("condition"), r.get("scenario_id")))

print(f"quarantined {len(moved)} files -> {QUAR}")
from collections import Counter
print("by condition:", dict(Counter(c for c, _ in moved)))

left = 0
for fp in CACHE.glob("*.json"):
    try:
        r = json.load(fp.open(encoding="utf-8"))
    except Exception:
        continue
    if r.get("condition") in CONDS and r.get("scenario_id") in sidset:
        left += 1
print(f"remaining C1a/C2a/C2b for first-150 in cache: {left} (must be 0)")
