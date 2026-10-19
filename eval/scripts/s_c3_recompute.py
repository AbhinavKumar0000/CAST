"""C3 recompute for S-series scoring (deterministic, free, offline).

Registered pipeline: PROTOCOL 8.32/8.33 + S_PLAN_V2 ("C3 from
`archive_v2/deterministic`"; S_PLAN: "deterministic scorer; recomputed on
perturbed evidence"). This script:

1. loads the scoring DEFINITIONS from `run_deterministic_v2.py` by exec-ing
   its definition prefix only (the file itself is read, never modified or
   executed past `EVIDENCE_DIR = ...`),
2. gate: recomputes the `full_repo` ranking on base evidence
   (`archive_v2/evidence`) and requires 40/40 equality with the frozen
   `archive_v2/deterministic` records,
3. recomputes `full_repo` top5 for every (arm, scenario) bundle in
   `eval/runs/s_evidence/<set>/<sid>.json` for all 14 sets (incl. N0),
4. writes `eval/results/s_c3_full_repo.json`.

Bug log 2026-10-19 (found at scoring, fixed same day, no model call):
score_s.py v1 used the MCP `crop_score` tool output stored in the bundles
as the C3 arm advice. That tool is a separate implementation which
disagrees with the registered det pipeline for 17/40 base scenarios, so
the registered control "N0 Shift@5 = 0" failed for instrument-mismatch
reasons. C3 advice is now computed with the registered pipeline; the
bundle `crop_score` output remains what C2a chain-of-custody and
tool-overlap use (it is what the model actually saw).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.s_series.base_set import select_base, scenarios_by_id  # noqa: E402
from eval.s_series.perturbations import PERTURBATIONS  # noqa: E402

SRC = ROOT / "eval" / "scripts" / "run_deterministic_v2.py"
EVID = ROOT / "eval" / "runs" / "s_evidence"
ARCH_EVID = ROOT / "eval" / "runs" / "archive_v2" / "evidence"
ARCH_DET = ROOT / "eval" / "runs" / "archive_v2" / "deterministic"
OUT = ROOT / "eval" / "results" / "s_c3_full_repo.json"


def load_scoring_defs() -> dict:
    """Exec only the definitions prefix of run_deterministic_v2.py."""
    src = SRC.read_text(encoding="utf-8")
    cut = src.index("EVIDENCE_DIR = Path(")
    ns: dict = {"__name__": "s_c3_recompute_defs", "__file__": str(SRC)}
    exec(compile(src[:cut], "run_deterministic_v2.py:defs", "exec"), ns)
    for req in ("score_crops", "ablation_configs"):
        if req not in ns:
            raise RuntimeError(f"definition {req!r} not found in prefix")
    return ns


def main() -> None:
    ns = load_scoring_defs()
    score_crops = ns["score_crops"]
    full_repo_w = ns["ablation_configs"]["full_repo"]["weights"]

    sids = select_base(40)
    meta = scenarios_by_id(sids)

    # ---- gate: reproduce the frozen base records 40/40 -----------------------
    base_check = {"match": 0, "mismatch": []}
    for sid in sids:
        b = json.loads((ARCH_EVID / f"{sid}.json").read_text(encoding="utf-8"))
        week = datetime.strptime(b["as_of_date"], "%Y-%m-%d").date().isocalendar().week
        top5 = [c["crop"] for c in score_crops(b, full_repo_w, week)[:5]]
        det = json.loads((ARCH_DET / f"{sid}.json").read_text(
            encoding="utf-8"))["ablations"]["full_repo"]["top5"]
        if top5 == det:
            base_check["match"] += 1
        else:
            base_check["mismatch"].append(
                {"sid": sid, "recorded": det, "recomputed": top5})
    if base_check["mismatch"]:
        raise SystemExit(
            "ABORT: recomputed C3 does not reproduce archive_v2/deterministic "
            f"({base_check['match']}/40); frozen inputs must have drifted")

    # ---- recompute every (arm, scenario) bundle ------------------------------
    sets = list(PERTURBATIONS)
    out_sets: dict[str, dict] = {}
    missing: list[str] = []
    errors: list[str] = []
    for s in sets:
        out_sets[s] = {}
        for sid in sids:
            fp = EVID / s / f"{sid}.json"
            if not fp.exists():
                missing.append(f"{s}/{sid}")
                continue
            b = json.loads(fp.read_text(encoding="utf-8"))
            week = datetime.strptime(b["as_of_date"], "%Y-%m-%d").date().isocalendar().week
            try:
                ranked = score_crops(b, full_repo_w, week)
                out_sets[s][sid] = {
                    "top5": [c["crop"] for c in ranked[:5]],
                    "top6": [c["crop"] for c in ranked],
                    "scores": {c["crop"]: c["total_score"] for c in ranked},
                    "week": week,
                }
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{s}/{sid}: {exc}")
                out_sets[s][sid] = {"error": str(exc), "top5": []}

    payload = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "pipeline": "run_deterministic_v2.py::score_crops "
                    "(full_repo ablation, repo weights)",
        "base_check": base_check,
        "n_sets": len(sets),
        "n_sids": len(sids),
        "missing": missing,
        "errors": errors,
        "sets": out_sets,
    }
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    n_cells = sum(len(v) for v in out_sets.values())
    print(f"base gate: {base_check['match']}/40 reproduced")
    print(f"recomputed cells: {n_cells} "
          f"(missing={len(missing)} errors={len(errors)})")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
