"""B2 pre-launch hygiene (offline): validate the remaining 350 scenarios (151..500).

  1. C0/C0b: confirm pre-fix records are reusable (current prompt hash match, model match,
     cap-sane) so B2 can reuse them.
  2. C1a/C2a/C2b: confirm NO stale-cached records exist for 151..500 (B1 only ran 1..150).
     Any file matching the current cache key for these conditions would be silently reused
     by run_model and must be quarantined before B2.

Uses the SAME cache-key formula as run_model. No API calls.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from eval.common import load_config  # noqa: E402
from eval.llm.prompts import prompt_c0, prompt_c0b, prompt_c1a, prompt_c2  # noqa: E402
from eval.scripts.run_model import FIVE_TOOLS, SIX_TOOLS  # noqa: E402
from eval.time_anchored import TimeAnchoredBuilder  # noqa: E402

MODEL_ID = "nvidia/nemotron-3-ultra-550b-a55b"
CACHE = ROOT / "eval/cache/llm/nemotron-3-ultra"
B1_N = 150
B2_SLICE = slice(150, 500)


def key_hash(cond, prompt, sid, rep=0):
    payload = "\u241f".join([MODEL_ID, cond, prompt, sid, str(rep)])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def main() -> int:
    cfg = load_config()
    cap = cfg["model"].get("max_output_tokens")
    subset = [json.loads(l) for l in (ROOT / "eval/data/llm_subset.jsonl")
              .read_text(encoding="utf-8").splitlines() if l.strip()]
    b2 = subset[B2_SLICE]
    print(f"B2 slice: llm_subset[{B1_N}:500] -> {len(b2)} scenarios "
          f"({b2[0]['scenario_id']}..{b2[-1]['scenario_id']})")
    print(f"frozen config: temperature={cfg['model'].get('temperature')} "
          f"max_output_tokens(C0/C0b)={cap}")

    builder = TimeAnchoredBuilder(cfg)
    index = {}
    for fp in CACHE.glob("*.json"):
        try:
            r = json.load(fp.open(encoding="utf-8"))
        except Exception:
            continue
        index.setdefault((r.get("condition"), r.get("scenario_id"), r.get("repeat", 0)), (fp.stem, r))

    # Cohort 1: C0/C0b reuse
    counts = Counter()
    problems = []
    for sc in b2:
        sid = sc["scenario_id"]
        for cond, fn in (("C0", prompt_c0), ("C0b", prompt_c0b)):
            exp = key_hash(cond, fn(sc), sid)
            got = index.get((cond, sid, 0))
            if got is None:
                counts["missing"] += 1
                problems.append(f"MISSING {sid} {cond}")
                continue
            stored_hash, rec = got
            if not stored_hash or stored_hash != exp or rec.get("model") != MODEL_ID:
                counts["mismatch"] += 1
                problems.append(f"MISMATCH {sid} {cond} stored={str(stored_hash)[:12]} exp={exp[:12]}")
                continue
            if rec.get("finish_reason") == "length" or rec.get("tokens_out", 0) > cap:
                counts["cap_suspicious"] += 1
                problems.append(f"CAP {sid} {cond} finish={rec.get('finish_reason')} "
                                f"tokens_out={rec.get('tokens_out')}")
                continue
            counts["reusable"] += 1

    n_pairs = 2 * len(b2)
    print(f"\n[C0/C0b reuse] checked {n_pairs} records -> {dict(counts)}")
    print(f"  REUSABLE {counts['reusable']}/{n_pairs} | needs re-run {n_pairs - counts['reusable']}")

    # Cohort 2: C1a/C2a/C2b must be ABSENT (no stale cache)
    stale = []
    checked = 0
    for sc in b2:
        sid = sc["scenario_id"]
        ev = builder.build(sc)
        for cond, prompt in (
            ("C1a", prompt_c1a(sc, ev)),
            ("C2a", prompt_c2(sc, SIX_TOOLS)),
            ("C2b", prompt_c2(sc, FIVE_TOOLS)),
        ):
            checked += 1
            h = key_hash(cond, prompt, sid)
            if (CACHE / f"{h}.json").exists():
                stale.append(f"{sid} {cond} hash={h[:12]}")
    print(f"\n[C1a/C2a/C2b stale-cache] checked {checked} keys -> stale present = {len(stale)}")
    for s in stale[:50]:
        print("  STALE " + s)

    ok = (counts["reusable"] == n_pairs) and not stale
    print("\nVERDICT:", "READY for B2" if ok else "NOT ready - resolve items above first")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
