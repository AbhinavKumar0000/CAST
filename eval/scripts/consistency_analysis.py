"""Consistency analysis (PROTOCOL 8.x STEP E) - SECONDARY, circular-by-construction.

For each model and condition, compares the per-scenario top-5 across repeats 0..2 using:
  * top-5 Jaccard similarity,
  * Kendall tau rank correlation (over the top-5),
  * exact-match (ordered top-5 identical),
  * season-validity delta (repeat-to-repeat drop, for reference).
Reports mean/95% bootstrap CI per (model, condition) over scenarios that have all repeats.
Models: Nemotron (n=500 subset; consistency on first 100) and Llama-3.2-11b.
Writes eval/results/consistency_analysis.{txt,json}. Offline (no API).
"""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from eval.metrics import jaccard_similarity, kendall_tau, exact_match_rate  # noqa: E402
from eval.statistics import bootstrap_ci  # noqa: E402

SOURCES = {
    "nemotron-3-ultra": ROOT / "eval/runs/eval_nemotron-3-ultra/results.json",
    "llama-3.2-11b": ROOT / "eval/runs/eval_llama-3.2-11b/results.json",
}
CONDS = ["C0b", "C1a", "C2a"]
OUT_TXT = ROOT / "eval/results/consistency_analysis.txt"
OUT_JSON = ROOT / "eval/results/consistency_analysis.json"
_records: list[str] = []
RESULTS: dict = {}


def emit(s: str = "") -> None:
    print(s)
    _records.append(s)


def top5(r):
    p = (r or {}).get("parsed") or {}
    return [str(x) for x in (p.get("top5") or [])]


def usable(r):
    if r is None or r.get("error"):
        return False
    p = r.get("parsed") or {}
    return bool(p.get("valid_json")) and not r.get("truncated")


def main() -> None:
    emit("=" * 100)
    emit("CONSISTENCY ANALYSIS (SECONDARY; repeat-to-repeat, circular by construction)")
    emit("=" * 100)
    for model, path in SOURCES.items():
        if not path.exists():
            emit(f"\n{model}: results.json missing")
            continue
        recs = json.load(open(path, encoding="utf-8"))
        by = {}
        for r in recs:
            by.setdefault((r["condition"], r["scenario_id"]), {})[r.get("repeat", 0)] = r
        emit(f"\n{'='*100}\n{model}\n{'='*100}")
        RESULTS[model] = {}
        for cond in CONDS:
            cells = [(sid, reps) for (c, sid), reps in by.items()
                     if c == cond and all(k in reps for k in (0, 1, 2))]
            n_scen = len(cells)
            if n_scen == 0:
                emit(f"  {cond}: no scenarios with all 3 repeats yet")
                continue
            jac, tau, em = [], [], []
            n_pp = 0
            for sid, reps in cells:
                if all(usable(reps[k]) for k in (0, 1, 2)):
                    n_pp += 1
                for a, b in itertools.combinations((0, 1, 2), 2):
                    ta, tb = top5(reps[a]), top5(reps[b])
                    jac.append(jaccard_similarity(ta, tb))
                    tau.append(kendall_tau(ta, tb))
                    em.append(1.0 if ta[:5] == tb[:5] else 0.0)
            jm, jl, ju = bootstrap_ci(jac, n_resamples=10000, seed=42)
            tm = float(np.mean(tau))
            emean = float(np.mean(em))
            emit(f"  {cond:5s} scenarios(all reps)={n_scen:3d} (PP all-reps {n_pp:3d}) | "
                 f"Jaccard={jm:.3f} [{jl:.3f},{ju:.3f}] | Kendall_tau={tm:+.3f} | exact-match={emean:.3f}")
            RESULTS[model][cond] = {"n_scenarios": n_scen, "n_pp": n_pp,
                                    "jaccard": [jm, jl, ju], "kendall_tau": tm, "exact_match": emean}
    emit(f"\nNOTE: these are internal consistency numbers (secondary, circular by construction; "
         f"not primary results - PROTOCOL 8.x).")
    OUT_JSON.write_text(json.dumps(RESULTS, indent=2), encoding="utf-8")
    OUT_TXT.write_text("\n".join(_records) + "\n", encoding="utf-8")
    emit(f"\nwrote {OUT_TXT}")
    emit(f"wrote {OUT_JSON}")


if __name__ == "__main__":
    main()
