"""Phase 8 ITEM 2 (final): reuse-eligibility for C0/C0b baselines.

Reuse rule (user decision): a (model, cond, sid, repeat=0) record is reusable iff
  1. at least one stored v1 record has prompt_hash == current computed hash
     (current prompts.c0/c0b code at eval/{llm,prompts}.py), proving byte-identical prompt
  2. stored model string == intended model
  3. temperature (0.2) and max_output_tokens (4096) match current config.yaml
     (verified: config diff since STEP A is comments-only + added tools/max_rounds keys)
  4. the record has no error

Canonical v1 NFC sources: the two full nemotron runs 20261011_074835 / 20261011_082444
(union semantics; some sids hold a valid hash in one duplicate and an empty hash in the
other). Every gen failed/empty representative is cross-checked against the union.

Output: eval/results/reuse_report.json + this stdout table.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from eval.common import config_dirs, load_config, read_jsonl
from eval.llm import prompts as P

ROOT = Path(__file__).resolve().parent.parent.parent
cfg = load_config()
dirs = config_dirs(cfg)

CANONICAL_NFC = ["full_nemotron-3-ultra_20261011_074835", "full_nemotron-3-ultra_20261011_082444"]
CANONICAL_LLAMA = ["eval_llama-3.2-11b"]
MODEL_SHORT = {
    "nvidia/nemotron-3-ultra-550b-a55b": "nemotron-3-ultra",
    "meta/llama-3.2-11b-vision-instruct": "llama-3.2-11b",
}
BUILDERS = {"C0": P.prompt_c0, "C0b": P.prompt_c0b}
USES = [  # (model_id, cond, intended_n)
    ("nvidia/nemotron-3-ultra-550b-a55b", "C0b", 500),
    ("nvidia/nemotron-3-ultra-550b-a55b", "C0", 500),
    ("meta/llama-3.2-11b-vision-instruct", "C0b", 150),
    ("meta/llama-3.2-11b-vision-instruct", "C0", 150),
]

subsets = read_jsonl(dirs["llm_subset_path"])
by_sid = {s["scenario_id"]: s for s in subsets}

temp_cfg = cfg["model"]["temperature"]
mt_cfg = cfg["model"]["max_output_tokens"]
print(f"config now: temperature={temp_cfg} max_output_tokens={mt_cfg} "
      f"tools(max_output_tokens_tools,m=..)={cfg['model'].get('max_output_tokens_tools')} "
      f"max_tool_rounds={cfg['model'].get('max_tool_rounds')}")

report = {"config": {"temperature": temp_cfg, "max_output_tokens": mt_cfg}, "reuse": []}

for model_id, cond, intended in USES:
    run_dirs = CANONICAL_NFC if "nemotron" in model_id else CANONICAL_LLAMA
    recs: dict[str, list[dict]] = defaultdict(list)
    for run in run_dirs:
        p = ROOT / "eval/runs" / run / "results.json"
        if not p.exists():
            print(f"  MISSING run dir {run}")
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        items = data if isinstance(data, list) else data.get("results") or data.get("records") or []
        for r in items:
            if r.get("condition") == cond and r.get("repeat", 0) == 0 and r.get("scenario_id") in by_sid:
                recs[r["scenario_id"]].append(r)

    reusable, rerun, reasons = [], [], defaultdict(int)
    for sid in sorted(by_sid)[:intended]:
        pool = recs.get(sid, [])
        good = None
        model_ok = False
        err_count = sum(1 for r in pool if r.get("error"))
        for r in pool:
            if r.get("model") == model_id:
                model_ok = True
            p_new = BUILDERS[cond](by_sid[sid])
            h = hashlib.sha256("\u241f".join([model_id, cond, p_new, sid, "0"]).encode()).hexdigest()
            if r.get("prompt_hash") == h and not r.get("error"):
                good = r
                break
        if good is not None:
            # verify cache file exists for the response
            h = good["prompt_hash"]
            cpath = dirs["cache_dir"] / "llm" / MODEL_SHORT[model_id] / f"{h}.json"
            if not cpath.exists():
                reasons[f"missing_cache:{MODEL_SHORT[model_id]}"] += 1
                rerun.append(sid)
            else:
                reusable.append(sid)
        else:
            blank_only = all(not r.get("prompt_hash") for r in pool)
            if blank_only:
                reasons["blank_prompt_hash"] += 1  # explicitly NOT reusable (user decision)
            elif not model_ok:
                reasons["model_mismatch"] += 1
            elif any(r.get("error") for r in pool):
                reasons["stored_error"] += 1
            else:
                reasons["hash_mismatch"] += 1
            rerun.append(sid)

    is_new_llama = cond + "_x"
    print(f"\n== {model_id} | {cond} | intended={intended}")
    print(f"   reusable={len(reusable)}  re-run-needed={len(rerun)}  reasons={dict(reasons)}")
    report["reuse"].append({
        "model": model_id, "condition": cond, "intended": intended,
        "reusable": reusable, "re_run": rerun, "reasons": dict(reasons),
    })

out = ROOT / "eval/results/reuse_report.json"
out.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(f"\nwrote {out}")
print("note: cached llm_subset n =", len(by_sid))