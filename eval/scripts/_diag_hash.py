"""Diagnose nemotron C0/C0b hash mismatches: compare OLD cached prompt text (from cache file
for the stored prompt_hash) vs NEW prompt text recomputed by the current builders."""

from __future__ import annotations

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
MODEL_SHORT = "nemotron-3-ultra"
BUILDERS = {"C0": P.prompt_c0, "C0b": P.prompt_c0b}

subsets = read_jsonl(dirs["llm_subset_path"])
by_sid = {s["scenario_id"]: s for s in subsets}

records = []
for p in Path("eval/runs").glob("*/results.json"):
    if "full_nemotron" not in p.parent.name:
        continue
    data = json.loads(p.read_text(encoding="utf-8"))
    items = data if isinstance(data, list) else data.get("results") or data.get("records") or []
    records.extend(items)

cache = dirs["cache_dir"] / "llm" / MODEL_SHORT

counts = {"C0": {"diff": 0, "same_text": 0, "no_old_cache": 0}, "C0b": {k: 0 for k in ("diff", "same_text", "no_old_cache")}}
examples = {"C0": [], "C0b": []}

for cond in ("C0", "C0b"):
    for r in records:
        if r.get("condition") != cond or r.get("repeat", 0) != 0:
            continue
        sid = r["scenario_id"]
        old_hash = r["prompt_hash"]
        new_prompt = BUILDERS[cond](by_sid[sid])
        payload = "\u241f".join([MODEL, cond, new_prompt, sid, "0"])
        new_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        if old_hash == new_hash:
            continue
        old_file = cache / f"{old_hash}.json"
        if not old_file.exists():
            counts[cond]["no_old_cache"] += 1
            continue
        old = json.loads(old_file.read_text(encoding="utf-8"))
        old_prompt = old.get("prompt") if isinstance(old, dict) else old
        if old_prompt == new_prompt:
            counts[cond]["same_text"] += 1
        else:
            counts[cond]["diff"] += 1
            if len(examples[cond]) < 2:
                # find first differing line
                ol = str(old_prompt).splitlines()
                nl = str(new_prompt).splitlines()
                for i in range(min(len(ol), len(nl))):
                    if ol[i] != nl[i]:
                        examples[cond].append((sid, i, ol[i][:180], nl[i][:180]))
                        break

for cond in ("C0b", "C0"):
    print(f"\ncond={cond}: text_diff={counts[cond]['diff']} text_same_but_hash_diff={counts[cond]['same_text']} "
          f"no_old_cache={counts[cond]['no_old_cache']}")
    for sid, i, o, n in examples[cond]:
        print(f"  sid={sid} line={i}\n    OLD: {o}\n    NEW: {n}")

print("\nold cache key payload scheme candidates: check sha256 of text-only variants for first diff sid")
for cond, sid, i, o, n in (examples["C0"] + examples["C0b"])[:1]:
    rec = [r for r in records if r.get("condition") == cond and r.get("scenario_id") == sid and r.get("repeat", 0) == 0][0]
    target = rec["prompt_hash"]
    p = BUILDERS[cond](by_sid[sid])
    variants = {
        "model|cond|prompt|sid|rep(1f sep)": "\u241f".join([MODEL, cond, p, sid, "0"]),
        "model.cond.prompt.sid.rep": f"{MODEL}.{cond}.{p}.{sid}.0",
        "model|cond|sid|rep|prompt": "\u241f".join([MODEL, cond, sid, "0", p]),
        "cond|sid remove(1f)": p,
        "model|cond|sid|rep": "\u241f".join([MODEL, cond, sid, "0"]),
    }
    for name, pay in variants.items():
        h = hashlib.sha256(pay.encode("utf-8")).hexdigest()
        print(f"  {name}: {'MATCH' if h == target else 'no'}")
    # also try old version WITHOUT prompt (maybe old hash used sid only)
    for name, pay in {"sid only": sid, "cond+model": f"{cond}{MODEL}", "model+cond+sid": f"{MODEL}{cond}{sid}"}.items():
        h = hashlib.sha256(pay.encode("utf-8")).hexdigest()
        print(f"  {name}: {'MATCH' if h == target else 'no'}   ({h[:12]}...)")