"""Audit the Nemotron LLM cache for pre-fix records that B1 would silently reuse."""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

CACHE = ROOT / "eval/cache/llm/nemotron-3-ultra"
subset = [json.loads(l) for l in (ROOT / "eval/data/llm_subset.jsonl")
          .read_text(encoding="utf-8").splitlines() if l.strip()][:150]
sids = [s["scenario_id"] for s in subset]
sidset = set(sids)

files = list(CACHE.glob("*.json"))
print(f"cache files: {len(files)}")

by_cond = Counter()
by_cond_150 = Counter()
trunc = defaultdict(int)
unk = defaultdict(int)
forced = defaultdict(int)
ts = defaultdict(list)
for fp in files:
    try:
        r = json.load(fp.open(encoding="utf-8"))
    except Exception:
        continue
    c = r.get("condition")
    by_cond[c] += 1
    if r.get("scenario_id") in sidset:
        by_cond_150[c] += 1
        if r.get("truncated") or r.get("finish_reason") == "length":
            trunc[c] += 1
        if int(r.get("unknown_tool_calls", 0) or 0) > 0:
            unk[c] += 1
        if r.get("forced_final"):
            forced[c] += 1
        if r.get("timestamp"):
            ts[c].append(r["timestamp"])

print("by condition (all cache):", dict(by_cond))
print("by condition (first-150 sids):", dict(by_cond_150))
for c in ("C0", "C0b", "C1", "C1a", "C1b", "C2", "C2a", "C2b"):
    if by_cond_150[c]:
        t = sorted(ts[c])
        print(f"  {c}: n={by_cond_150[c]} truncated={trunc[c]} unknown={unk[c]} "
              f"forced={forced[c]} ts=[{t[0]} .. {t[-1]}]")
print("\nVERDICT: B1 (C1a/C2a/C2b x first-150) would reuse "
      f"{by_cond_150['C1a']+by_cond_150['C2a']+by_cond_150['C2b']} cached pre-fix records."
      if any(by_cond_150[c] for c in ("C1a", "C2a", "C2b")) else
      "\nVERDICT: no C1a/C2a/C2b cache for the first-150 -> B1 is a clean run.")
