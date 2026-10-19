"""Step (a): verify Nemotron C0/C0b pre-fix records are reusable for the 150 B1 scenarios.

Reuse test = the run_model cache key, i.e. sha256("\u241f".join([model, cond, prompt, sid, rep]))
computed from the CURRENT prompt builders must equal the stored prompt_hash. A blank/absent
prompt_hash, a model mismatch, or a hash mismatch => NOT reusable (must be re-run fresh).
temperature / max_tokens are not stored per record; reported from the frozen config, plus the
C0/C0b cap sanity check (finish_reason != length and tokens_out <= max_output_tokens).
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from eval.common import load_config
from eval.llm.prompts import prompt_c0, prompt_c0b

MODEL_ID = "nvidia/nemotron-3-ultra-550b-a55b"
CACHE = ROOT / "eval/cache/llm/nemotron-3-ultra"
CONDS = {"C0": prompt_c0, "C0b": prompt_c0b}


def key_hash(cond, prompt, sid, rep=0):
    payload = "\u241f".join([MODEL_ID, cond, prompt, sid, str(rep)])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def main() -> None:
    cfg = load_config()
    temp = cfg["model"].get("temperature")
    cap = cfg["model"].get("max_output_tokens")
    print(f"frozen config: model={MODEL_ID} temperature={temp} max_output_tokens(C0/C0b)={cap}")

    subset = [json.loads(l) for l in (ROOT / "eval/data/llm_subset.jsonl")
              .read_text(encoding="utf-8").splitlines() if l.strip()][:150]

    index = {}
    for fp in CACHE.glob("*.json"):
        try:
            r = json.load(fp.open(encoding="utf-8"))
        except Exception:
            continue
        index.setdefault((r.get("condition"), r.get("scenario_id"), r.get("repeat", 0)), (fp.stem, r))

    counts = Counter()
    problems = []
    for sc in subset:
        sid = sc["scenario_id"]
        for cond, fn in CONDS.items():
            exp = key_hash(cond, fn(sc), sid)
            got = index.get((cond, sid, 0))
            if got is None:
                counts["missing"] += 1
                problems.append(f"MISSING {sid} {cond}")
                continue
            stored_hash, rec = got
            if not stored_hash:
                counts["blank_prompt_hash"] += 1
                problems.append(f"BLANK {sid} {cond}")
                continue
            if rec.get("model") != MODEL_ID:
                counts["model_mismatch"] += 1
                problems.append(f"MODEL {sid} {cond} {rec.get('model')}")
                continue
            if stored_hash != exp:
                counts["hash_mismatch"] += 1
                problems.append(f"HASH {sid} {cond} stored={stored_hash[:12]} exp={exp[:12]}")
                continue
            if rec.get("finish_reason") == "length" or rec.get("tokens_out", 0) > cap:
                counts["cap_suspicious"] += 1
                problems.append(f"CAP {sid} {cond} finish={rec.get('finish_reason')} "
                                f"tokens_out={rec.get('tokens_out')}")
                continue
            counts["reusable"] += 1

    n = len(subset)
    print(f"\nscenarios={n}  C0+C0b pairs checked={2*n}")
    print("counts:", dict(counts))
    print(f"\nREUSABLE: {counts['reusable']}/{2*n}")
    print(f"NEEDS RE-RUN (missing/blank/mismatch/cap): "
          f"{2*n - counts['reusable']}")
    if problems:
        print("\nproblems:")
        for p in problems:
            print("  " + p)


if __name__ == "__main__":
    main()
