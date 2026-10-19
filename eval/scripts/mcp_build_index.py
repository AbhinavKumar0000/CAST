"""Build the coordinate->scenario index consumed by the eval MCP replay server.

``eval/mcp_eval/server.py`` serves frozen, time-anchored evidence bundles (built by
``eval.time_anchored.TimeAnchoredBuilder``) looked up by the ``(latitude, longitude)``
that the MCP tool call carries. It reads a JSON map ``"<lat_4dp>,<lon_4dp>" -> scenario_id``
from ``$EVAL_INDEX`` (default ``eval/runs/archive_v2/evidence/index.json``).

This script regenerates that map deterministically from the scenario definitions. It
writes nothing else and touches no bundles.

Usage:  python -u eval/scripts/mcp_build_index.py [--source subset|scenarios|stress]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

from eval.common import config_dirs, load_config, read_jsonl  # noqa: E402

OUT_DIR = Path("eval/runs/archive_v2/evidence")


def key(lat: float, lon: float) -> str:
    return f"{round(float(lat), 4)},{round(float(lon), 4)}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["subset", "scenarios", "stress"], default="scenarios")
    args = ap.parse_args()

    cfg = load_config()
    dirs = config_dirs(cfg)
    src = {"subset": dirs["llm_subset_path"], "scenarios": dirs["scenarios_path"], "stress": dirs["stress_path"]}[args.source]
    rows = read_jsonl(src)

    index: dict[str, str] = {}
    collisions: list[tuple[str, str, str]] = []
    present = 0
    for sc in rows:
        k = key(sc["lat"], sc["lon"])
        sid = sc["scenario_id"]
        if k in index and index[k] != sid:
            collisions.append((k, index[k], sid))
            continue
        index[k] = sid
        if (OUT_DIR / f"{sid}.json").exists():
            present += 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "index.json").write_text(json.dumps(index, indent=0, sort_keys=True), encoding="utf-8")

    print(f"source={src} rows={len(rows)} index_keys={len(index)} bundles_present={present}")
    print(f"4dp collisions: {len(collisions)}")
    for c in collisions[:10]:
        print("  collision", c)
    print(f"wrote {OUT_DIR / 'index.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
