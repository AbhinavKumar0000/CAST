import json
from collections import Counter
from pathlib import Path

for label, p in [("adhoc/evidence", Path("eval/runs/adhoc/evidence")),
                 ("archive_v2/deterministic", Path("eval/runs/archive_v2/deterministic"))]:
    top1 = Counter()
    top5 = Counter()
    top6 = Counter()
    n = {"Kharif": 0, "Rabi": 0, "Zaid": 0}
    for f in p.iterdir():
        if f.suffix != ".json":
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        if label == "adhoc/evidence":
            cs = d.get("crop_score") or {}
            ranked = cs.get("ranked_crops") or []
            names = [c["crop"] for c in ranked]
            season = (cs.get("current_season") or d.get("season", {}).get("current_season") or "")
        else:
            ab = d.get("ablations", {}).get("full_repo") or {}
            names = ab.get("top6") or []
            season = d.get("season") or ""
        if not names or season not in ("Kharif", "Rabi", "Zaid"):
            continue
        n[season] += 1
        top1[(season, names[0])] += 1
        top5[(season, "Barley" in names[:5])] += 1
        top6[(season, "Barley" in names)] += 1
    print(f"=== {label} ===")
    for season in ("Kharif", "Rabi", "Zaid"):
        b1 = top1.get((season, "Barley"), 0)
        print(f"  {season:6s} n={n[season]:5d}  barley#1={b1:5d} ({100*b1/max(n[season],1):.1f}%)  "
              f"barley-top5={top5.get((season, True), 0):5d}  barley-top6={top6.get((season, True), 0):5d}")