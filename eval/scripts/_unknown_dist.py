import json
from collections import Counter, defaultdict

recs = json.load(open("eval/runs/eval_llama-3.2-11b/results.json", encoding="utf-8"))
recs = [r for r in recs if r.get("repeat", 0) == 0]

for cond in ("C1a", "C2a", "C2b", "C0", "C0b", "C2", "C1"):
    sub = [r for r in recs if r["condition"] == cond]
    if not sub:
        continue
    n = len(sub)
    valid = sum(1 for r in sub if (r.get("parsed") or {}).get("valid_json"))
    trunc = sum(1 for r in sub if r.get("truncated"))
    forced = sum(1 for r in sub if r.get("forced_final"))
    unknown_runs = sum(1 for r in sub if (r.get("unknown_tool_calls") or 0) > 0)
    unknown_total = sum((r.get("unknown_tool_calls") or 0) for r in sub)
    maxr = sum(1 for r in sub if r.get("max_rounds_reached"))
    print(f"{cond:4s} n={n:3d} valid={valid:3d} trunc={trunc} forced={forced} "
          f"unknown_runs={unknown_runs:3d} unknown_total={unknown_total:3d} max_rounds={maxr}")

print("\n=== unknown-tool per-scenario distribution (C2a) ===")
ua = [(r["scenario_id"], r.get("unknown_tool_calls") or 0) for r in recs if r["condition"] == "C2a"]
dup = [(sid, c) for sid, c in ua if c > 0]
print("scenarios with >=1 unknown:", len(dup))
print("distribution:", dict(sorted(Counter(c for _, c in dup).items())))
print("max:", max([c for _, c in ua]) if ua else 0)
# invented tool names
names = Counter()
for r in recs:
    if r["condition"] in ("C2a", "C2b"):
        for entry in (r.get("tool_log") or []):
            if isinstance(entry, dict) and entry.get("unknown_tool"):
                names[entry.get("tool") or entry.get("name")] += 1
print("invented tool names:", dict(names.most_common(20)))

print("\n=== C2b ===")
ub = [(r["scenario_id"], r.get("unknown_tool_calls") or 0) for r in recs if r["condition"] == "C2b"]
dupb = [(sid, c) for sid, c in ub if c > 0]
print("scenarios with >=1 unknown:", len(dupb))
print("distribution:", dict(sorted(Counter(c for _, c in dupb).items())))
print("max:", max([c for _, c in ub]) if ub else 0)

# sample tool_log entry
for r in recs:
    if (r.get("tool_log") or []):
        print("\nsample tool_log entry:", json.dumps(r["tool_log"][0], default=str)[:300])
        break