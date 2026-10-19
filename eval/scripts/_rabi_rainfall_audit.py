import json
from collections import Counter
from pathlib import Path

EVID = Path("eval/runs/archive_v2/evidence")
seasons = Counter()
rm_zero = Counter()
rm_nonzero = Counter()
rabi_scen_with_any_nonzero = 0
rabi_scen = 0
scen_season = {}
per_crop_nonzero = Counter()

for f in EVID.glob("*.json"):
    d = json.loads(f.read_text(encoding="utf-8"))
    cs = d.get("crop_score") or {}
    season = cs.get("current_season") or (d.get("season") or {}).get("current_season") or ""
    seasons[season] += 1
    scen_season[d.get("scenario_id")] = season
    rc = cs.get("ranked_crops") or []
    any_nz = False
    for c in rc:
        rm = (c.get("scores") or {}).get("rainfall_match")
        if rm is None:
            continue
        if season == "Rabi":
            if rm == 0.0:
                rm_zero[c["crop"]] += 1
            else:
                rm_nonzero[c["crop"]] += 1
                any_nz = True
                per_crop_nonzero[c["crop"]] += 1
    if season == "Rabi":
        rabi_scen += 1
        if any_nz:
            rabi_scen_with_any_nonzero += 1

print("scenario season counts:", dict(seasons))
print(f"Rabi scenarios: {rabi_scen}")
print(f"Rabi scenarios where >=1 crop has rainfall_match != 0: {rabi_scen_with_any_nonzero}")
print("Rabi crops with rainfall_match != 0 (count of scenarios):", dict(per_crop_nonzero))
print("distinct Rabi crops with rm==0:", len(rm_zero))
print("distinct Rabi crops with rm!=0:", len(rm_nonzero))