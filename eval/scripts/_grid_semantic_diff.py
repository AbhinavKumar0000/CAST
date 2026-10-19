"""Semantic diff of the two deterministic grids (adhoc vs archive_v2).

Reports how many scenarios differ in: full_repo top5, season field, and which
top-level keys are present in one grid but not the other. Answers whether
repointing a script from adhoc/deterministic to archive_v2/deterministic can
change any C3 recommendation.
"""
from __future__ import annotations

import json
from pathlib import Path

ADH = Path("eval/runs/adhoc/deterministic")
V2 = Path("eval/runs/archive_v2/deterministic")

adh = {p.stem: p for p in ADH.glob("*.json")}
v2 = {p.stem: p for p in V2.glob("*.json")}
print(f"adhoc/deterministic: {len(adh)}  archive_v2/deterministic: {len(v2)}")
print(f"only in adhoc: {len(set(adh) - set(v2))}  only in v2: {len(set(v2) - set(adh))}")

top5_diff = 0
season_diff = 0
keyset_diff = 0
sample = []
for sid in sorted(set(adh) & set(v2)):
    a = json.loads(adh[sid].read_text(encoding="utf-8"))
    b = json.loads(v2[sid].read_text(encoding="utf-8"))
    ta = a.get("ablations", {}).get("full_repo", {}).get("top5")
    tb = b.get("ablations", {}).get("full_repo", {}).get("top5")
    if ta != tb:
        top5_diff += 1
        if len(sample) < 10:
            sample.append((sid, ta, tb))
    if a.get("season") != b.get("season"):
        season_diff += 1
    if set(a) != set(b):
        keyset_diff += 1

allkeys_a = set()
allkeys_b = set()
for sid in sorted(set(adh) & set(v2))[:500]:
    allkeys_a |= set(json.loads(adh[sid].read_text(encoding="utf-8")))
    allkeys_b |= set(json.loads(v2[sid].read_text(encoding="utf-8")))

print(f"full_repo top5 mismatches: {top5_diff}")
print(f"season-field mismatches:   {season_diff}")
print(f"top-level key-set mismatches: {keyset_diff}")
print(f"keys only in adhoc (sample): {sorted(allkeys_a - allkeys_b)}")
print(f"keys only in v2    (sample): {sorted(allkeys_b - allkeys_a)}")
for sid, ta, tb in sample:
    print(f"  {sid}: adhoc={ta} v2={tb}")

out = {
    "adhoc_n": len(adh),
    "v2_n": len(v2),
    "only_in_adhoc": sorted(set(adh) - set(v2)),
    "only_in_v2": sorted(set(v2) - set(adh)),
    "full_repo_top5_mismatches": top5_diff,
    "season_field_mismatches": season_diff,
    "keyset_mismatches": keyset_diff,
    "keys_only_in_adhoc": sorted(allkeys_a - allkeys_b),
    "keys_only_in_v2": sorted(allkeys_b - allkeys_a),
}
Path("eval/results/_grid_semantic_diff.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
print("wrote eval/results/_grid_semantic_diff.json")
