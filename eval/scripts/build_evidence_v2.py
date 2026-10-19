"""Phase 8 STEP A: build v2 time-anchored evidence bundles for the LLM subset.

Deterministic, offline (cached weather only). Treats as read-only: v1 bundles under
eval/runs/adhoc/evidence are untouched. v2 bundles go to eval/runs/archive_v2/evidence/.

Usage:  python -u eval/scripts/build_evidence_v2.py [--n 500]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

from eval.common import config_dirs, load_config, read_jsonl  # noqa: E402
from eval.time_anchored import TimeAnchoredBuilder  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

OUT_DIR = Path("eval/runs/archive_v2/evidence")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=500)
    ap.add_argument("--source", choices=["subset", "scenarios", "stress"], default="subset")
    args = ap.parse_args()

    cfg = load_config()
    dirs = config_dirs(cfg)
    if args.source == "subset":
        rows = read_jsonl(dirs["llm_subset_path"])
    elif args.source == "scenarios":
        rows = read_jsonl(dirs["scenarios_path"])
    else:
        rows = read_jsonl(dirs["stress_path"])
    rows = rows[: args.n] if args.n and args.n > 0 else rows

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    builder = TimeAnchoredBuilder(cfg)

    start = time.time()
    written = 0
    drifted_crop = 0
    v1_dir = Path("eval/runs/adhoc/evidence")
    for sc in rows:
        b = builder.build(sc)
        (OUT_DIR / f"{sc['scenario_id']}.json").write_text(
            json.dumps(b, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        written += 1
        v1 = v1_dir / f"{sc['scenario_id']}.json"
        if v1.exists():
            try:
                old = json.loads(v1.read_text(encoding="utf-8"))
                if [c["crop"] for c in old.get("crop_score", {}).get("ranked_crops", [])] != \
                   [c["crop"] for c in b["crop_score"]["ranked_crops"]]:
                    drifted_crop += 1
            except Exception:
                pass
        if written % 100 == 0:
            print(f"  {written}/{len(rows)} bundles ({time.time()-start:.0f}s)", flush=True)

    summary = {
        "v2_out_dir": str(OUT_DIR),
        "n_bundles": written,
        "crop_score_top6_rank_changed_vs_v1": drifted_crop,
        "time_s": round(time.time() - start, 1),
    }
    (OUT_DIR / "_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"v2 evidence: {written} bundles in {summary['time_s']}s")
    print(f"crop_score ranking changed vs v1 bundles: {drifted_crop}/{len(rows)}")
    print(f"location: {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())