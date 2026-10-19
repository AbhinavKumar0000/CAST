import json
from pathlib import Path

p = Path("eval/runs/eval_llama-3.2-11b/results.json")
data = json.loads(p.read_text(encoding="utf-8"))
c2 = [r for r in data if r.get("condition") == "C2" and not r.get("error")]
print("llama C2 records:", len(c2))
for r in c2[:3]:
    tl = r.get("tool_log") or []
    print(f"  sid={r['scenario_id']} tool_calls={r['tool_calls']} len(tool_log)={len(tl)} "
          f"rounds={[t.get('round') for t in tl][:10]} names={[t.get('name') for t in tl][:10]}")

pn = Path("eval/runs/full_nemotron-3-ultra_20261011_082444/results.json")
data = json.loads(pn.read_text(encoding="utf-8"))
c2 = [r for r in data if r.get("condition") == "C2" and not r.get("error")]
print("\nnemotron C2 records:", len(c2))
for r in c2[:3]:
    tl = r.get("tool_log") or []
    print(f"  sid={r['scenario_id']} tool_calls={r['tool_calls']} len(tool_log)={len(tl)} "
          f"rounds={[t.get('round') for t in tl][:10]} names={[t.get('name') for t in tl][:10]}")

# how many tool calls share a single 'round' value (i.e. parallel batch sizes)
from collections import Counter
for short, path in [("llama", p), ("nemotron", pn)]:
    data = json.loads(path.read_text(encoding="utf-8"))
    c2 = [r for r in data if r.get("condition") == "C2" and not r.get("error")]
    batch = []
    for r in c2:
        tl = r.get("tool_log") or []
        n_rounds = len({t.get("round") for t in tl})
        batch.append((len(tl), n_rounds))
    cnt = Counter(b[1] for b in batch)
    print(f"{short}: tool_log distinct round values -> {dict(cnt)}")