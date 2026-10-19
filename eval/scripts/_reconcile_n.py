import json
from pathlib import Path

LLAMA = Path("eval/runs/eval_llama-3.2-11b/results.json")
subset = [json.loads(l) for l in Path("eval/data/llm_subset.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()][:150]
season = {s["scenario_id"] for s in subset}
recs = json.load(open(LLAMA, encoding="utf-8"))

CONDS = ["C0", "C0b", "C1a", "C2a", "C2b"]

print(f"{'cond':5s} {'N':>4s} {'err':>4s} {'vj':>4s} {'trunc':>5s} {'vj&!tr':>6s} {'t5>0':>5s} {'PP':>4s} | excluded: badjson  empty_t5")
for cond in CONDS:
    rows = [r for r in recs if r.get("repeat", 0) == 0 and r["condition"] == cond and r["scenario_id"] in season]
    n = len(rows)
    err = sum(1 for r in rows if r.get("error"))
    vj = sum(1 for r in rows if (r.get("parsed") or {}).get("valid_json"))
    trunc = sum(1 for r in rows if r.get("truncated"))
    vj_notr = sum(1 for r in rows if (r.get("parsed") or {}).get("valid_json") and not r.get("truncated"))
    t5pos = sum(1 for r in rows if (r.get("parsed") or {}).get("top5"))
    pp = sum(1 for r in rows if (not r.get("error")) and (r.get("parsed") or {}).get("valid_json")
             and not r.get("truncated") and (r.get("parsed") or {}).get("top5"))
    badjson = sum(1 for r in rows if not (r.get("parsed") or {}).get("valid_json"))
    empty_t5 = sum(1 for r in rows if (r.get("parsed") or {}).get("valid_json") and not (r.get("parsed") or {}).get("top5"))
    print(f"{cond:5s} {n:4d} {err:4d} {vj:4d} {trunc:5d} {vj_notr:6d} {t5pos:5d} {pp:4d} | {badjson:8d} {empty_t5:8d}")