"""Verify B1 (Nemotron C1a/C2a/C2b on llm_subset[:150]) after the harness fix.

Mirrors verify_stage_a.py plus the pilot abort checks that are decidable offline:
valid_json / truncated / forced_final / unknown_tool_calls / max_rounds, HTTP per
scenario, latency, and crop_score leakage into C2b.
"""
import json
from collections import Counter, defaultdict
from pathlib import Path

REC = Path("eval/runs/eval_nemotron-3-ultra/results.json")
recs = [r for r in json.loads(REC.read_text(encoding="utf-8"))
        if r.get("condition") in ("C1a", "C2a", "C2b")]
print("B1 C1a/C2a/C2b records:", len(recs))

bysid = defaultdict(dict)
for r in recs:
    bysid[r["scenario_id"]][r["condition"]] = r
print("complete scenarios (3 conds):", sum(1 for m in bysid.values() if len(m) == 3))

unk_names = Counter()
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
    tools = sorted(len(r.get("tool_log") or []) for r in rs)
    finish = Counter(r.get("finish_reason") or "?" for r in rs)
    errs = Counter(r.get("error_type") for r in rs if r.get("error"))
    for r in rs:
        for tc in (r.get("tool_log") or []):
            if tc.get("unknown_tool"):
                unk_names[tc.get("name")] += 1
    print(f"\n{cond}: n={n} valid={valid} ({valid/n*100:.1f}%) trunc={trunc} forced={forced} "
          f"unknown={unk} max_rounds={maxr}")
    print(f"  finish={dict(finish)} | HTTP/scen med={http[n//2]} mean={sum(http)/n:.2f} max={max(http)}")
    print(f"  tools med={tools[n//2]} mean={sum(tools)/n:.2f} | lat med={lat[n//2]:.0f}s mean={sum(lat)/n:.0f}s")
    if errs:
        print(f"  error_types={dict(errs)}")

print("\ninvented tool names:", dict(unk_names))

c2b_cs = sum(1 for r in recs if r["condition"] == "C2b"
             for tc in (r.get("tool_log") or []) if tc.get("name") == "crop_score")
c2b_cs_calls = sum(1 for r in recs if r["condition"] == "C2b" and r.get("tool_calls", 0)
                   and any(tc.get("name") == "crop_score" for tc in (r.get("tool_log") or [])))
print(f"abort check (c): crop_score calls in C2b tool_log = {c2b_cs} (must be 0)")
h429 = sum(1 for r in recs if "429" in str(r.get("error") or "") or r.get("error_type") == "rate_limit")
print(f"abort check (e): 429/rate_limit records = {h429} (must be 0)")

print("\nInvalid / truncated / forced records:")
bad = 0
for r in recs:
    ok = (r.get("parsed") or {}).get("valid_json")
    if not ok or r.get("truncated") or r.get("forced_final"):
        bad += 1
        print(f"  {r['scenario_id']} {r['condition']} valid={bool(ok)} trunc={r.get('truncated')} "
              f"forced={r.get('forced_final')} ({r.get('forced_final_reason')}) finish={r.get('finish_reason')} "
              f"tools={len(r.get('tool_log') or [])} unk={r.get('unknown_tool_calls',0)}")
print(f"total flagged: {bad}")
