"""Verify Llama Stage A primary run (C1a/C2a/C2b on llm_subset[:150]) + metrics.

Reads eval/runs/eval_llama-3.2-11b/results.json (primary, non-pilot). Reports
valid_json, truncated, forced_final, unknown_tool_calls, max_rounds_reached,
finish reasons, HTTP/scenario, tokens, latency, per condition.
"""

import json
from collections import Counter, defaultdict
from pathlib import Path

REC = Path("eval/runs/eval_llama-3.2-11b/results.json")
recs = [r for r in json.loads(REC.read_text(encoding="utf-8"))
        if r.get("condition") in ("C1a", "C2a", "C2b")]
print("primary C1a/C2a/C2b records:", len(recs))

bysid = defaultdict(dict)
for r in recs:
    bysid[r["scenario_id"]][r["condition"]] = r
print("complete scenarios (3 conds):", sum(1 for m in bysid.values() if len(m) == 3))

for cond in ("C1a", "C2a", "C2b"):
    rs = [r for r in recs if r["condition"] == cond]
    n = len(rs)
    valid = sum(1 for r in rs if (r.get("parsed") or {}).get("valid_json"))
    trunc = sum(1 for r in rs if r.get("truncated"))
    forced = sum(1 for r in rs if r.get("forced_final"))
    unk = sum(r.get("unknown_tool_calls", 0) for r in rs)
    maxr = sum(1 for r in rs if r.get("error") == "max_rounds_reached")
    http = sorted(len(r.get("tool_log") or []) + 1 for r in rs)
    lat = sorted(r.get("latency_s", 0) for r in rs)
    tok_in = sum(r.get("tokens_in", 0) for r in rs)
    tok_out = sum(r.get("tokens_out", 0) for r in rs)
    finish = Counter(r.get("finish_reason") or "?" for r in rs)
    hmm = sorted(len(r.get("tool_log") or []) for r in rs)
    print(f"\n{cond}: n={n} valid={valid} ({valid/n*100:.1f}%) trunc={trunc} forced={forced} "
          f"unknown={unk} max_rounds={maxr}")
    print(f"  finish={dict(finish)} | HTTP/scen med={http[n//2]} mean={sum(http)/n:.2f} max={max(http)}")
    print(f"  tools med={hmm[n//2]} mean={sum(hmm)/n:.2f} | lat med={lat[n//2]:.0f}s mean={sum(lat)/n:.0f}s")
    print(f"  tokens in/out total={tok_in}/{tok_out}")

# list invalid/truncated/forced for the report
print("\nInvalid / truncated / forced records:")
for r in recs:
    ok = (r.get("parsed") or {}).get("valid_json")
    if not ok or r.get("truncated") or r.get("forced_final"):
        print(f"  {r['scenario_id']} {r['condition']} valid={bool(ok)} trunc={r.get('truncated')} "
              f"forced={r.get('forced_final')} ({r.get('forced_final_reason')}) finish={r.get('finish_reason')} "
              f"tools={len(r.get('tool_log') or [])} unk={r.get('unknown_tool_calls',0)}")