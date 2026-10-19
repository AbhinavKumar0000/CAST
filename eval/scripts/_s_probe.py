import json, collections
from pathlib import Path
def load(p):
    d=json.load(open(p,encoding="utf-8"))
    return d
nemo=load("eval/runs/eval_nemotron-3-ultra/results.json")
llama=load("eval/runs/eval_llama-3.2-11b/results.json")
def key(rec): return (rec.get("condition"), rec.get("scenario_id"), rec.get("repeat",0))
def cov(recs):
    c=collections.defaultdict(set)
    for r in recs: c[r["condition"]].add(r["scenario_id"])
    return c
cn=cov(nemo); cl=cov(llama)
print("nemo conds:", {k:len(v) for k,v in sorted(cn.items())})
print("llama conds:", {k:len(v) for k,v in sorted(cl.items())})
pilot=set(json.load(open("eval/results/pilot_scenario_sets.json"))["pilot_union"])
print("pilot_union:",len(pilot))
for cond in ["C0","C0b","C1a","C2a","C2b"]:
    both=cn[cond]&cl[cond]
    print(f"{cond}: nemo={len(cn[cond])} llama={len(cl[cond])} both={len(both)} both*pilot={len(both&pilot)}")
# both for all required
req=["C0","C0b","C1a","C2a","C2b"]
both_all=set.intersection(*[cn[c]&cl[c] for c in req])
print("intersection all 5 conds both models:",len(both_all))
import json as J
subset=[J.loads(l) for l in open("eval/data/llm_subset.jsonl",encoding="utf-8")]
sid2season={s["scenario_id"]:s.get("season_stratum") for s in subset}
sid2dist={s["scenario_id"]:s.get("district") for s in subset}
import collections as C
print("season dist in both_all:", C.Counter(sid2season.get(s) for s in sorted(both_all)))
