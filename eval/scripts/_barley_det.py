import json
from collections import Counter
from pathlib import Path

p = Path("eval/runs/archive_v2/deterministic")
top1 = Counter()
top5 = Counter()
n = {"Kharif": 0, "Rabi": 0, "Zaid": 0}
margins = []
for f in p.iterdir():
    if f.suffix != ".json":
        continue
    d = json.loads(f.read_text(encoding="utf-8"))
    ab = d.get("ablations", {}).get("full_repo") or {}
    names = ab.get("top6") or []
    scores = ab.get("scores") or {}
    season = d.get("season") or ""
    if not names or season not in n:
        continue
    n[season] += 1
    top1[(season, names[0])] += 1
    top5[(season, "Barley" in names[:5])] += 1
    if names[0] == "Barley" and season == "Rabi":
        s1 = scores.get(names[0], 0)
        s2 = scores.get(names[1], 0) if len(names) > 1 else 0
        margins.append(round(s1 - s2, 4))

for season in ("Kharif", "Rabi", "Zaid"):
    b1 = top1.get((season, "Barley"), 0)
    b5 = top5.get((season, True), 0)
    total = max(n[season], 1)
    print(f"{season:6s} n={n[season]:5d}  barley#1={b1:5d} ({100*b1/total:.1f}%)  "
          f"barley-in-top5={b5:5d} ({100*b5/total:.1f}%)")

import statistics
if margins:
    print("\nBarley Rabi #1 wins:", len(margins))
    print("margin mean:", round(statistics.mean(margins), 4), "median:", round(statistics.median(margins), 4))
    print("margin min:", min(margins), "max:", max(margins), "ties(0):", sum(1 for m in margins if m == 0))