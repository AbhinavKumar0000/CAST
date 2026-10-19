"""For mismatched sids, compare store hashes across BOTH duplicate nemotron run files vs current."""

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from eval.common import config_dirs, load_config, read_jsonl
from eval.llm import prompts as P

cfg = load_config()
dirs = config_dirs(cfg)
MODEL = "nvidia/nemotron-3-ultra-550b-a55b"
BUILDERS = {"C0b": P.prompt_c0b, "C0": P.prompt_c0}
subsets = read_jsonl(dirs["llm_subset_path"])
by_sid = {s["scenario_id"]: s for s in subsets}

files = [p for p in Path("eval/runs").glob("full_nemotron*/results.json")]
print("run files:", files)

records = {}
for p in files:
    data = json.loads(p.read_text(encoding="utf-8"))
    items = data if isinstance(data, list) else data.get("results") or data.get("records") or []
    for r in items:
        records.setdefault((r.get("model"), r.get("condition"), r.get("scenario_id"), r.get("repeat", 0)), []).append((p.parent.name, r["prompt_hash"]))

for cond in ("C0b", "C0"):
    mismatch = 0
    for sid in sorted(by_sid):
        recs = records.get((MODEL, cond, sid, 0), [])
        if not recs:
            continue
        p_new = BUILDERS[cond](by_sid[sid])
        new_hash = hashlib.sha256("\u241f".join([MODEL, cond, p_new, sid, "0"]).encode()).hexdigest()
        hashes = {h for _, h in recs}
        if new_hash not in hashes:
            mismatch += 1
            if mismatch <= 3:
                print(f"cond={cond} sid={sid} stored={recs if hashes else 'none'} new_hash={new_hash[:16]}...")
    print(f"cond={cond}: sids where NO stored file has the current hash: {mismatch} / {len(by_sid)}")