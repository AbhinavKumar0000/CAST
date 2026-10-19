"""Inspect stored result record schema for C0/C0b reuse verification (ITEM 2)."""

import json
from pathlib import Path

for run in ["eval/runs/eval_llama-3.2-11b", "eval/runs/eval_glm-5.3",
            "eval/runs/full_nemotron-3-ultra_20261011_074835",
            "eval/runs/full_nemotron-3-ultra_20261011_082444"]:
    p = Path(run) / "results.json"
    if not p.exists():
        print(f"MISSING {p}")
        continue
    data = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        # maybe {"records": [...]}
        keys = list(data.keys())
        recs = data.get("records") or data.get("results") or []
        print(f"{run}: top-level keys={keys}")
    else:
        recs = data
    print(f"  n_records={len(recs)}")
    if recs:
        r0 = recs[0]
        print(f"  record keys: {sorted(r0.keys())}")
        sample = {k: r0.get(k) for k in ("condition", "model_id", "model", "temperature", "max_tokens", "prompt_hash", "scenario_id", "finish_reason", "tool_calls", "error_type", "max_tool_rounds") if k in r0}
        print(f"  sample: {json.dumps(sample, default=str)[:600]}")
        conds = {}
        for r in recs:
            c = r.get("condition") or r.get("condition_id") or r.get("prompt_name")
            conds[c] = conds.get(c, 0) + 1
        print(f"  conditions: {conds}")
    print()