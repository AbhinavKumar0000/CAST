"""Dump the cached Nemotron C1a/C2a/C2b records for the first-150 sids."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

CACHE = ROOT / "eval/cache/llm/nemotron-3-ultra"
subset = [json.loads(l) for l in (ROOT / "eval/data/llm_subset.jsonl")
          .read_text(encoding="utf-8").splitlines() if l.strip()][:150]
sidset = {s["scenario_id"] for s in subset}

rows = []
for fp in CACHE.glob("*.json"):
    try:
        r = json.load(fp.open(encoding="utf-8"))
    except Exception:
        continue
    if r.get("scenario_id") in sidset and r.get("condition") in ("C1a", "C2a", "C2b"):
        rows.append(r)

rows.sort(key=lambda r: (r.get("condition"), r.get("scenario_id")))
print(f"{'cond':4s} {'scenario':10s} {'finish':8s} {'trunc':5s} {'toks_out':>8s} "
      f"{'tools':>5s} {'unk':>4s} {'forced':>6s} {'timestamp':32s} valid")
for r in rows:
    p = r.get("parsed") or {}
    print(f"{r.get('condition'):4s} {r.get('scenario_id'):10s} "
          f"{str(r.get('finish_reason')):8s} {str(bool(r.get('truncated'))):5s} "
          f"{r.get('tokens_out',0):8d} {r.get('tool_calls',0):5d} "
          f"{r.get('unknown_tool_calls',0):4d} {str(bool(r.get('forced_final'))):6s} "
          f"{str(r.get('timestamp')):32s} {bool(p.get('valid_json'))}")
