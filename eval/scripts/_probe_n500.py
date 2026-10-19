import json
from pathlib import Path

ROOT = Path(".").resolve()
sub = [json.loads(l) for l in (ROOT/"eval/data/llm_subset.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
print("llm_subset:", len(sub))
print("first/last sid:", sub[0]["scenario_id"], sub[-1]["scenario_id"])
print("keys:", list(sub[0].keys()))
print("season_stratum sample:", sub[0].get("season_stratum"), sub[300].get("season_stratum"))
seasons = {}
for s in sub:
    seasons[s.get("season_stratum")] = seasons.get(s.get("season_stratum"),0)+1
print("season_stratum dist (500):", seasons)

pilot = json.load(open(ROOT/"eval/results/pilot_scenario_sets.json", encoding="utf-8"))
print("pilot keys:", list(pilot.keys()))
pu = pilot["pilot_union"]
print("pilot_union:", len(pu), "sample:", pu[:5])

sids = [s["scenario_id"] for s in sub]
pilot_in = [s for s in sids if s in set(pu)]
print("pilot_dev in 500:", len(pilot_in), "in first150:", len([s for s in sids[:150] if s in set(pu)]))

# deterministic + evidence coverage for 151..500 (and all)
DET = ROOT/"eval/runs/archive_v2/deterministic"
EVID = ROOT/"eval/runs/archive_v2/evidence"
missing_det = [s for s in sids if not (DET/f"{s}.json").exists()]
missing_evid = [s for s in sids if not (EVID/f"{s}.json").exists()]
print("missing deterministic:", len(missing_det), missing_det[:5])
print("missing evidence:", len(missing_evid), missing_evid[:5])

# cache C0/C0b coverage
CACHE = ROOT/"eval/cache/llm/nemotron-3-ultra"
by = {}
for fp in CACHE.glob("*.json"):
    try:
        r = json.load(fp.open(encoding="utf-8"))
    except Exception:
        continue
    if r.get("condition") in ("C0","C0b") and r.get("repeat",0)==0:
        by.setdefault((r["condition"], r["scenario_id"]), r)
c0 = sum(1 for s in sids if ("C0",s) in by)
c0b = sum(1 for s in sids if ("C0b",s) in by)
print("cache C0 for 500:", c0, "C0b for 500:", c0b)
print("cache files total:", len(list(CACHE.glob('*.json'))))

# run results coverage
B1 = ROOT/"eval/runs/eval_nemotron-3-ultra/results.json"
B2 = ROOT/"eval/runs/eval_nemotron-3-ultra_b2/results.json"
r1 = json.load(open(B1, encoding="utf-8"))
r2 = json.load(open(B2, encoding="utf-8"))
s1 = set(x["scenario_id"] for x in r1); s2 = set(x["scenario_id"] for x in r2)
print("B1 sids:", len(s1), "B2 sids:", len(s2), "overlap:", len(s1&s2))
print("union:", len(s1|s2), "==500?", len(s1|s2)==500)
