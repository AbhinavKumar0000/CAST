"""Phase 8 STEP C: build eval/data/ground_truth/expert_rating_template.csv.

200 scenarios sampled from the 500-subset, stratified by season x stress, with one row
per (condition, model) output. Re-usable C0/C0b outputs (v1, prompt-identical) and the
v2 deterministic C3 outputs are included now; the Phase 8 STEP F conditions
(C1a/C1b/C2a/C2b) are inserted as PENDING rows that this script fills in when the run
results exist (re-run after STEP F; non-destructive).

The rating column is left blank for blinded 1-5 agronomist ratings; scenario_id/condition
provide the NULLIFED linkage/reveal key kept aside from the rating sheet.
"""

from __future__ import annotations

import csv
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from eval.common import config_dirs, load_config

cfg = load_config()
dirs = config_dirs(cfg)

rng = random.Random(20261013)  # frozen seed

subsets = [json.loads(l) for l in open(dirs["llm_subset_path"], encoding="utf-8")]
by_id = {s["scenario_id"]: s for s in subsets}

results_dirs = [
    Path("eval/runs/eval_nemotron-3-ultra"),
    Path("eval/runs/eval_llama-3.2-11b"),
    Path("eval/runs/eval_glm-5.3"),
    Path("eval/runs/full_nemotron-3-ultra_20261011_074835"),
    Path("eval/runs/full_nemotron-3-ultra_20261011_082444"),
    Path("eval/runs/full_nemotron-3-ultra_20261011_082738"),
]

REUSE_CONDITIONS_OLD = {"C0", "C0b"}  # only these are prompt-identical v1<->v2
PHASE8_CONDITIONS = ["C1a", "C1b", "C2a", "C2b"]


def load_results() -> dict[tuple[str, str, int], dict]:
    """(scenario_id, condition, model_short) -> best record, deduped across dirs."""
    out: dict[tuple[str, str, int], dict] = {}
    for d in results_dirs:
        rfile = d / "results.json"
        if not rfile.exists():
            continue
        try:
            recs = json.loads(rfile.read_text(encoding="utf-8"))
        except Exception:
            continue
        for r in recs:
            if r.get("error"):
                continue
            key = (r["scenario_id"], r["condition"], r.get("model_short", r.get("model", "?")))
            if key not in out:
                out[key] = r
    return out


recs = load_results()
print(f"usable non-error LLM records: {len(recs)}")

# Stratified sample: season x stress buckets from the 500-subset.
stress_ids = set()
for line in open(dirs["stress_path"], encoding="utf-8"):
    stress_ids.add(json.loads(line)["scenario_id"])

buckets: dict[tuple[str, bool], list[str]] = defaultdict(list)
for sc in subsets:
    buckets[(sc["season_stratum"], sc["scenario_id"] in stress_ids)].append(sc["scenario_id"])

sample: list[str] = []
for (season, stress), ids in sorted(buckets.items()):
    k = max(1, round(200 * len(ids) / len(subsets)))
    chosen = rng.sample(ids, min(k, len(ids)))
    sample.extend(chosen)
    print(f"  {season} stress={int(stress)}: {len(ids)} avail, sample {len(chosen)}")

if len(sample) < 200:  # top-up from leftovers
    rest = [s for s in subsets if s["scenario_id"] not in sample]
    sample.extend(rng.sample([s["scenario_id"] for s in rest], 200 - len(sample)))
sample = sample[:200]
print(f"total sample: {len(sample)}")

rows: list[dict[str, str]] = []
for sid in sorted(sample):
    sc = by_id[sid]
    stress = "1" if sid in stress_ids else "0"
    # deterministic C3 (v2)
    det_path = Path("eval/runs/archive_v2/deterministic") / f"{sid}.json"
    if det_path.exists():
        det = json.loads(det_path.read_text(encoding="utf-8"))
        ab = det.get("ablations", {}).get("full_repo", {})
        if ab.get("top5"):
            rows.append({
                "scenario_id": sid, "district": sc["district"], "as_of_date": sc["as_of_date"],
                "season_stratum": sc["season_stratum"], "stress": stress,
                "condition": "C3", "model_short": "deterministic",
                "top5": "|".join(ab["top5"]), "explanation": "[deterministic scorer]",
                "rating": "",
            })
    # reusable LLM conditions
    for cond in sorted(REUSE_CONDITIONS_OLD):
        for (rid, cid, mshort), r in recs.items():
            if cid == cond and rid == sid:
                parsed = r.get("parsed") or {}
                top = parsed.get("top5") or []
                rows.append({
                    "scenario_id": sid, "district": sc["district"], "as_of_date": sc["as_of_date"],
                    "season_stratum": sc["season_stratum"], "stress": stress,
                    "condition": cond, "model_short": mshort,
                    "top5": "|".join(top) if top else "",
                    "explanation": parsed.get("explanation", "")[:300],
                    "rating": "", "cached": "reused-v1",
                })
    # Phase 8 STEP F conditions (pending unless a run result already exists)
    for cond in PHASE8_CONDITIONS:
        existing = [r for (rid, cid, mshort), r in recs.items()
                    if cid == cond and rid == sid and not r.get("error")]
        if existing:
            r = existing[0]
            parsed = r.get("parsed") or {}
            rows.append({
                "scenario_id": sid, "district": sc["district"], "as_of_date": sc["as_of_date"],
                "season_stratum": sc["season_stratum"], "stress": stress,
                "condition": cond, "model_short": existing[0].get("model_short", "?"),
                "top5": "|".join(parsed.get("top5") or []),
                "explanation": parsed.get("explanation", "")[:300],
                "rating": "", "cached": "phase8",
            })
        else:
            rows.append({
                "scenario_id": sid, "district": sc["district"], "as_of_date": sc["as_of_date"],
                "season_stratum": sc["season_stratum"], "stress": stress,
                "condition": cond, "model_short": "(pending-STEPF)",
                "top5": "PENDING", "explanation": "PENDING", "rating": "",
                "cached": "pending",
            })

out_path = Path("eval/data/ground_truth/expert_rating_template.csv")
fieldnames = ["scenario_id", "district", "as_of_date", "season_stratum", "stress",
              "condition", "model_short", "top5", "explanation", "rating", "cached"]
with out_path.open("w", encoding="utf-8", newline="") as fh:
    writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)

from collections import Counter  # noqa: E402
print(f"template rows: {len(rows)}")
print("by condition:", dict(Counter(r['condition'] for r in rows)))
print("by status:", dict(Counter(r.get('cached', 'deterministic') for r in rows)))
print(f"wrote {out_path}")