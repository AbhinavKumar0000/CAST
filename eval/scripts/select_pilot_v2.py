"""Select 20 NEW pilot v2 scenarios (exclude pilot v1 sids; 7/7/6 Kharif/Rabi/Zaid).

Deterministic: take llm_subset rows after the first 20, group by season, pick in
subset order until each quota is met. Writes eval/results/pilot_v2_scenarios.json.
"""

import json
from pathlib import Path

PILOT_V1 = {
    "S000006", "S000063", "S000072", "S000137", "S000141", "S000170", "S000190",
    "S000258", "S000279", "S000289", "S000311", "S000335", "S000344", "S000355",
    "S000358", "S000400", "S000425", "S000438", "S000464", "S000467",
}
QUOTA = {"Kharif": 7, "Rabi": 7, "Zaid": 6}

ss = [
    json.loads(l) for l in
    Path("eval/data/llm_subset.jsonl").read_text(encoding="utf-8").splitlines()
    if l.strip()
]

picked: list[dict] = []
counts = {"Kharif": 0, "Rabi": 0, "Zaid": 0}
for s in ss:
    if s["scenario_id"] in PILOT_V1:
        continue
    season = s["season_by_month"]
    if season in QUOTA and counts[season] < QUOTA[season]:
        picked.append(s)
        counts[season] += 1
    if sum(counts.values()) == sum(QUOTA.values()):
        break

print("picked:", len(picked), counts)
for s in picked:
    print(s["scenario_id"], s["month"], s["season_by_month"], s["district"])
ids = [s["scenario_id"] for s in picked]

out = Path("eval/results/pilot_v2_scenarios.json")
out.write_text(json.dumps({
    "pilot_v2": ids,
    "n": len(ids),
    "season_counts": counts,
    "excludes_pilot_v1": True,
    "method": "first rows of llm_subset after pilot v1's first 20, per-season quota 7/7/6",
}, indent=2, ensure_ascii=False), encoding="utf-8")
print("wrote", out)