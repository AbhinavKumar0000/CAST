import json
from collections import Counter
from pathlib import Path

ss = [json.loads(l) for l in Path("eval/data/llm_subset.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
for n in (10, 20, 30, 60, 100, 150, 500):
    head = ss[:n]
    seasons = Counter(s.get("season_by_month") for s in head)
    print(f"first {n}: season_by_month={dict(seasons)}")
print("all 500:", dict(Counter(s.get("season_by_month") for s in ss)))
for k in ("Kharif", "Rabi", "Zaid"):
    idx = [i for i, s in enumerate(ss) if s.get("season_by_month") == k]
    print(f"  {k}: n={len(idx)} first20={sum(1 for i in idx if i<20)} first150={sum(1 for i in idx if i<150)}")