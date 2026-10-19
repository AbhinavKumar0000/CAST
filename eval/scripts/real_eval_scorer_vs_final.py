"""STEP 5b: Nemotron C2a vs C2b vs the scorer tool's ranking (report only).

Compares each condition's final top-5 (parsed.top5) with the deterministic
crop_score ranking (C3 = archive_v2 full_repo top5), and reports Precision@5 of
the scorer ranking alone vs the final answer against the headline reference
R_prim (2015-16..2022-23, 21-crop registry).

No interpretation. Writes eval/results/real_eval_scorer_vs_final.{json,txt}.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
import numpy as np  # noqa: E402

RUNS = [ROOT / "eval/runs/eval_nemotron-3-ultra/results.json",
        ROOT / "eval/runs/eval_nemotron-3-ultra_b2/results.json"]
DET = ROOT / "eval/runs/archive_v2/deterministic"
OUT_JSON = ROOT / "eval/results/real_eval_scorer_vs_final.json"
OUT_TXT = ROOT / "eval/results/real_eval_scorer_vs_final.txt"
CONDS = ["C2a", "C2b"]

spec = importlib.util.spec_from_file_location("re", ROOT / "eval/scripts/real_eval.py")
re = importlib.util.module_from_spec(spec)
spec.loader.exec_module(re)


def load_records():
    by: dict[tuple, dict] = {}
    for p in RUNS:
        if not p.exists():
            continue
        for r in json.loads(p.read_text(encoding="utf-8")):
            by[(r.get("condition"), r.get("scenario_id"))] = r
    return by


def load_c3():
    c3: dict[str, list[str]] = {}
    for path in DET.glob("*.json"):
        res = json.loads(path.read_text(encoding="utf-8"))
        ab = (res.get("ablations") or {}).get("full_repo")
        if ab and not ab.get("error") and ab.get("top5"):
            c3[path.stem] = ab["top5"]
    return c3


def usable(r) -> bool:
    return bool(r) and bool((r.get("parsed") or {}).get("valid_json")) \
        and not r.get("error") and not r.get("truncated")


def main() -> None:
    sids, district, season = re.load_subset()
    clean = re.load_clean()
    ref = re.build_reference(clean, re.WINDOW_PRIM, "area_ha", True)
    by = {}
    for p in RUNS:
        if p.exists():
            for r in json.loads(p.read_text(encoding="utf-8")):
                by[(r.get("condition"), r.get("scenario_id"))] = r
    c3 = {}
    for path in DET.glob("*.json"):
        res = json.loads(path.read_text(encoding="utf-8"))
        ab = (res.get("ablations") or {}).get("full_repo")
        if ab and not ab.get("error") and ab.get("top5"):
            c3[path.stem] = ab["top5"]

    scorer_all = [re.precision_at_5(c3[s], ref.get((district[s], season[s]), []))
                  for s in sids if s in c3]

    out: dict = {"scorer_ranking": "C3 = archive_v2 full_repo top5",
                 "reference": "R_prim (2015-16..2022-23, 21-crop registry)",
                 "scorer_precision_at_5_all_500": float(np.mean(scorer_all)),
                 "conditions": {}}
    for cond in CONDS:
        rows = []
        for sid in sids:
            r = by.get((cond, sid))
            if not (r and r.get("parsed", {}).get("valid_json")
                    and not r.get("error") and not r.get("truncated")):
                continue
            final = r["parsed"].get("top5") or []
            scorer = c3.get(sid)
            if not final or not scorer:
                continue
            rref = ref.get((district[sid], season[sid]), [])
            n = min(5, len(final), len(scorer))
            rows.append({
                "scenario_id": sid,
                "ordered_identical": int(list(final) == list(scorer)),
                "set_identical": int(set(final) == set(scorer)),
                "jaccard": len(set(final) & set(scorer)) / (len(set(final) | set(scorer)) or 1),
                "positions_identical": sum(1 for i in range(n) if final[i] == scorer[i]),
                "precision_at_5_scorer": re.precision_at_5(scorer, rref),
                "precision_at_5_final": re.precision_at_5(final, rref),
            })
        agg = {}
        if rows:
            agg = {
                "n": len(rows),
                "ordered_identical_rate": float(np.mean([x["ordered_identical"] for x in rows])),
                "set_identical_rate": float(np.mean([x["set_identical"] for x in rows])),
                "mean_jaccard": float(np.mean([x["jaccard"] for x in rows])),
                "mean_positions_identical_of_5": float(np.mean([x["positions_identical"] for x in rows])),
                "precision_at_5_scorer": float(np.mean([x["precision_at_5_scorer"] for x in rows])),
                "precision_at_5_final": float(np.mean([x["precision_at_5_final"] for x in rows])),
            }
        out["conditions"][cond] = agg

    OUT_JSON.write_text(json.dumps(out, indent=2, default=float), encoding="utf-8")

    lines = ["Nemotron: final answer vs the scorer tool's ranking (report only)", ""]
    lines.append(f"scorer ranking alone, Precision@5 over all 500 scenarios: "
                 f"{out['scorer_precision_at_5_all_500']:.4f}")
    for cond in CONDS:
        a = out["conditions"][cond]
        if not a:
            lines.append(f"{cond}: no usable scenarios")
            continue
        lines.append("")
        lines.append(f"{cond} (n={agg['n']})" if (agg := agg if False else a) else cond)
        lines.append(f"  ordered-identical to scorer : {agg['ordered_identical_rate']:.3f}")
        lines.append(f"  set-identical to scorer     : {agg['set_identical_rate']:.3f}")
        lines.append(f"  mean Jaccard vs scorer      : {agg['mean_jaccard']:.3f}")
        lines.append(f"  mean identical positions /5 : {agg['mean_positions_identical_of_5']:.2f}")
        lines.append(f"  Precision@5 scorer alone    : {agg['precision_at_5_scorer']:.3f}")
        lines.append(f"  Precision@5 final answer    : {agg['precision_at_5_final']:.3f}")
    OUT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
