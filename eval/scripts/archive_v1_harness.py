"""Phase 8 ITEM 2: archive old invalid-harness C1/C2 records (COPY only, nothing deleted).

Old C1/C2 used the pre-time-anchoring harness (v1 conditions, time anchoring bug).
They must not be reused for the STEP D/E analysis; moved out of the live run set into
archive_v2/v1_invalid_harness/ so status/aggregation scripts do not read them.

The full runs 074835/082444 also contain C0/C0b which ARE reused (see reuse_report.json),
so we copy only their C1/C2 records + errors here rather than moving whole directories.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
RUNDIR = ROOT / "eval/runs"
OUT = RUNDIR / "archive_v2" / "v1_invalid_harness"

CANONICAL = ["full_nemotron-3-ultra_20261011_074835", "full_nemotron-3-ultra_20261011_082444",
             "eval_llama-3.2-11b", "eval_glm-5.3"]
OLD_COND = ("C1", "C2")

OUT.mkdir(parents=True, exist_ok=True)

kept = {}
total_old = 0
for run in CANONICAL:
    p = RUNDIR / run / "results.json"
    if not p.exists():
        continue
    data = json.loads(p.read_text(encoding="utf-8"))
    items = data if isinstance(data, list) else data.get("results") or data.get("records") or []
    c12 = [r for r in items if r.get("condition") in OLD_COND]
    total_old += len(c12)
    if c12:
        kept[run] = c12
        (OUT / f"{run}_c1_c2.json").write_text(json.dumps(c12, indent=1), encoding="utf-8")

manifest = {
    "note": "COPY of old invalid-harness C1/C2 records (pre time-anchoring fix). Not reused in STEP D/E.",
    "record_count": total_old,
    "conditions": list(OLD_COND),
    "source_runs": list(kept),
}
(OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

print(json.dumps(manifest, indent=2))
for run, recs in kept.items():
    from collections import Counter
    print(f"  {run}: C1+C2 records copied = {len(recs)}")