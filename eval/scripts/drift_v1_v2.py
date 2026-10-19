"""Compute v1->v2 C3 (full_repo top5) drift and write deterministic_meta.json."""
import json
import sys
from pathlib import Path

v1dir = Path("eval/runs/adhoc/deterministic")
resdir = Path("eval/runs/archive_v2/deterministic")

v1_top5 = {}
for i, p in enumerate(v1dir.glob("*.json")):
    try:
        v1_top5[p.stem] = json.load(p.open(encoding="utf-8"))["ablations"]["full_repo"]["top5"]
    except Exception:
        pass
    if i % 2000 == 0:
        print(f"  v1 {i}", flush=True)

changed = 0
common = 0
for i, p in enumerate(resdir.glob("*.json")):
    try:
        ab = json.load(p.open(encoding="utf-8"))["ablations"].get("full_repo")
    except Exception:
        continue
    if not ab:
        continue
    if p.stem in v1_top5:
        common += 1
        if ab["top5"] != v1_top5[p.stem]:
            changed += 1
    if i % 2000 == 0:
        print(f"  v2 {i}", flush=True)

print("C3 full_repo top5 drift v1->v2:", changed, "/", common, flush=True)
meta = {
    "phase": 8,
    "evidence_version": 2,
    "v2_out": str(resdir),
    "week_anchored_to": "as_of_date",
    "c3_top5_drift_vs_v1": {"changed": changed, "common": common},
    "config_shasum_note": "config.yaml modified in Phase 8 STEP A (max_tool_rounds)",
}
Path("eval/runs/archive_v2/deterministic_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
print("meta written -> eval/runs/archive_v2/deterministic_meta.json", flush=True)
sys.exit(0)