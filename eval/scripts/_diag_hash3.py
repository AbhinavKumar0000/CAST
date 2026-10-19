"""Map per-run-file hash validity + empty-hash counts, to chose canonical v1 run source."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from collections import Counter
from eval.common import config_dirs, load_config, read_jsonl
from eval.llm import prompts as P
import hashlib

cfg = load_config()
dirs = config_dirs(cfg)
MODEL = "nvidia/nemotron-3-ultra-550b-a55b"
BUILDERS = {"C0b": P.prompt_c0b, "C0": P.prompt_c0}
subsets = read_jsonl(dirs["llm_subset_path"])
by_sid = {s["scenario_id"]: s for s in subsets}

files = sorted(Path("eval/runs").glob("full_nemotron*/results.json"))
for p in files:
    data = json.loads(p.read_text(encoding="utf-8"))
    items = data if isinstance(data, list) else data.get("results") or data.get("records") or []
    by_cond = Counter(r.get("condition") for r in items)
    empty_hash = sum(1 for r in items if not r.get("prompt_hash"))
    err = sum(1 for r in items if r.get("error"))
    print(f"{p.parent.name}: n={len(items)} conds={dict(by_cond)} empty_hash={empty_hash} with_error={err}")

print("\nSids with EMPTY stored hash in BOTH 074835 and 082444 (repeat 0, C0/C0b):")
seen = set()
for p in [Path("eval/runs/full_nemotron-3-ultra_20261011_074835/results.json"),
          Path("eval/runs/full_nemotron-3-ultra_20261011_082444/results.json")]:
    data = json.loads(p.read_text(encoding="utf-8"))
    items = data if isinstance(data, list) else data.get("results") or data.get("records") or []
    for r in items:
        if r.get("repeat", 0) == 0 and r.get("condition") in ("C0", "C0b") and not r.get("prompt_hash"):
            seen.add((r.get("condition"), r.get("scenario_id")))
print(sorted(seen)[:40])
print(f"total empty-hash (cond, sid) unique: {len(seen)}")