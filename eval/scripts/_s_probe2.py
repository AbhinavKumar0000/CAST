import json, collections
from pathlib import Path
pilot=set(json.load(open("eval/results/pilot_scenario_sets.json"))["pilot_union"])
nemo={r["scenario_id"] for r in json.load(open("eval/runs/eval_nemotron-3-ultra/results.json",encoding="utf-8")) if r["condition"] in ("C1a","C2a","C2b")}
llama={r["scenario_id"] for r in json.load(open("eval/runs/eval_llama-3.2-11b/results.json",encoding="utf-8")) if r["condition"] in ("C1a","C2a","C2b")}
common=sorted(nemo&llama)
print("common support:",len(common))
subset=[json.loads(l) for l in open("eval/data/llm_subset.jsonl",encoding="utf-8")]
s2sea={s["scenario_id"]:s["season_stratum"] for s in subset}
print("common season dist:",collections.Counter(s2sea[s] for s in common))
print("common & pilot:",len(set(common)&pilot))
