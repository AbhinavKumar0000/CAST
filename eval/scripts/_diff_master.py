import csv
from pathlib import Path

OLD = Path("eval/results/_presnap_adhoc/master_long.csv")
NEW = Path("eval/results/master_long.csv")


def load(p):
    d = {}
    with p.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            d[(r["scenario_id"], r["model"], r["condition"], r["repeat"])] = r
    return d


o, n = load(OLD), load(NEW)
assert set(o) == set(n), (len(o), len(n))
key_cols = ["season", "top5", "c3_top5", "season_valid", "hard_violation", "overlap_with_C3"]
changed = {c: 0 for c in key_cols}
by_mc = {}
for k in o:
    diffs = [c for c in key_cols if o[k][c] != n[k][c]]
    for c in diffs:
        changed[c] += 1
    if diffs:
        mc = (n[k]["model"], n[k]["condition"])
        by_mc.setdefault(mc, 0)
        by_mc[mc] += 1

print(f"rows compared: {len(o)}")
print("rows changed per column:")
for c in key_cols:
    print(f"  {c:16s}: {changed[c]}")
print("\nrows with any change by (model,condition):")
for k in sorted(by_mc):
    print(f"  {k[0]:<16s} {k[1]:<4s} {by_mc[k]}")

# C3 rows specifically
c3old = {k: v for k, v in o.items() if v["model"] == "C3"}
c3new = {k: v for k, v in n.items() if v["model"] == "C3"}
c3chg = sum(1 for k in c3old if c3old[k]["c3_top5"] != c3new[k]["c3_top5"])
print(f"\nC3 rows: {len(c3old)}; c3_top5 changed in {c3chg}")