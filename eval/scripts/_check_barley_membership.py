"""Confirm Barley top5/top1 membership across Rabi scenarios (diagnosis companion)."""

import json
import sys
from collections import Counter
from pathlib import Path

DET_DIR = Path("eval/runs/archive_v2/deterministic")

rabi = 0
barley_top1 = 0
barley_top5 = 0
barley_pos: Counter[int] = Counter()
seasons = Counter()
for path in DET_DIR.glob("*.json"):
    with path.open(encoding="utf-8") as fh:
        res = json.load(fh)
    ab = res.get("ablations", {}).get("full_repo")
    if not ab or not ab.get("top5"):
        continue
    season = res.get("season", "?")
    seasons[season] += 1
    if season != "Rabi":
        continue
    rabi += 1
    top5 = ab["top5"]
    if top5[0] == "Barley":
        barley_top1 += 1
    if "Barley" in top5:
        barley_top5 += 1
        barley_pos[top5.index("Barley") + 1] += 1

print(f"Rabi scenarios: {rabi}")
print(f"Barley in top5: {barley_top5} ({100*barley_top5/max(rabi,1):.1f}%)")
print(f"Barley in top1: {barley_top1} ({100*barley_top1/max(rabi,1):.1f}%)")
print(f"Barley position in top5 (when present): {dict(sorted(barley_pos.items()))}")
print(f"Season totals: {dict(seasons)}")