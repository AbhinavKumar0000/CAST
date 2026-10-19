import csv
import json
from collections import Counter
from pathlib import Path

EVID = Path("eval/runs/adhoc/evidence")

top1 = Counter()
barley_top5 = Counter()
barley_margins = []
barley_by_season = Counter()
n = 0
for f in EVID.iterdir():
    if f.suffix != ".json":
        continue
    b = json.loads(f.read_text(encoding="utf-8"))
    season = b["season"]["current_season"]
    ranked = b.get("crop_score", {}).get("ranked_crops") or []
    if not ranked:
        continue
    n += 1
    names = [c["crop"] for c in ranked]
    top1[(season, names[0])] += 1
    barley_top5[(season, "Barley" in names[:5])] += 1
    if names[0] == "Barley":
        barley_by_season[season] += 1
        s0 = ranked[0]["total_score"]
        s1 = ranked[1]["total_score"] if len(ranked) > 1 else 0
        barley_margins.append((f.name, season, round(s0, 4), round(s1, 4), round(s0 - s1, 4)))

print("bundles seen:", n)
print("\n=== TOP-1 distribution by season ===")
for season in ("Kharif", "Rabi", "Zaid"):
    sub = {c: ct for (s, c), ct in top1.items() if s == season}
    total = sum(sub.values())
    print(f"{season:6s} n={total}: ")
    for c in sorted(sub, key=lambda c: -sub[c]):
        print(f"    {c:16s} {sub[c]:5d}  {100*sub[c]/total:5.1f}%")
print("\nBarley top-1 total by season:", dict(barley_by_season))

print("\n=== Barley in C3 top-5 by season ===")
for season in ("Kharif", "Rabi", "Zaid"):
    hit = barley_top5.get((season, True), 0)
    print(f"  {season:6s} barley-in-top5: {hit}")

print("\n=== Barley top-1 score margins (winning score, 2nd score, margin) ===")
barley_margins.sort(key=lambda r: r[4])
print("min margins (tightest wins):")
for r in barley_margins[:3]:
    print("  ", r)
print("max margins:")
for r in barley_margins[-3:]:
    print("  ", r)
import statistics
margins = [r[4] for r in barley_margins]
if margins:
    print("n wins:", len(margins), "mean margin:", round(statistics.mean(margins), 4),
          "median:", round(statistics.median(margins), 4),
          "tie (0.000):", sum(1 for m in margins if m == 0))

with (Path("eval/results") / "barley_top1_margins.csv").open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["file", "season", "barley_score", "second_score", "margin"])
    w.writerows(barley_margins)
print("wrote eval/results/barley_top1_margins.csv", len(barley_margins), "rows")