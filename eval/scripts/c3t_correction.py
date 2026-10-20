"""C3t correction analysis (PROTOCOL 8.35): full metric recomputation.

INSTRUMENT CORRECTION, NOT TUNING. Offline; NO model calls; no frozen file changed.

Uses the SAME metric definitions as recompute_season_validity_v1_2.py (earlier registered analysis):
- Season validity: fraction of crops in top5 that are valid for the scenario season
- Hard violation: per-crop check against season/drought/flood constraints, rate = violations / (5 * n_scenarios)
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.scripts.c3t_recompute import load_defs, load_rows, make_score, week_of
from eval.s_series.base_set import select_base
from eval.s_series.perturbations import PERTURBATIONS

ARCH = ROOT / "eval" / "runs" / "archive_v2" / "evidence"
DET_V1 = ROOT / "eval" / "runs" / "archive_v2" / "deterministic"
DET_V2 = ROOT / "eval" / "runs" / "db_v2" / "deterministic"
S_EVID = ROOT / "eval" / "runs" / "s_evidence"
CROP_LOG_V1 = ROOT / "crop_log.csv"
CROP_LOG_V2 = ROOT / "crop_log_v2.csv"
GT_SEASON_V1 = ROOT / "eval" / "data" / "ground_truth" / "crop_season_table_v1.1.csv"
GT_SEASON_V12 = ROOT / "eval" / "data" / "ground_truth" / "crop_season_table_v1.2.csv"
GT_HARD_V1 = ROOT / "eval" / "data" / "ground_truth" / "hard_constraints_v1.1.csv"
REAL_CLEAN = ROOT / "eval" / "real_data" / "clean" / "area_by_district_season_year.csv"
LLM_SUBSET = ROOT / "eval" / "data" / "llm_subset.jsonl"
OUT_DIR = ROOT / "eval" / "results"
REPORT_DIR = ROOT / "eval" / "reports"

OUT_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR.mkdir(parents=True, exist_ok=True)

W = {"rainfall": 0.20, "temperature": 0.15, "soil": 0.20, "season": 0.30, "risk": 0.15}


def load_gt_season(path: Path) -> list[dict]:
    """Load crop season table as list of rows (matching earlier script)."""
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def load_gt_hard(path: Path) -> list[dict]:
    """Load hard constraints as list of rows (matching earlier script)."""
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def season_status(crop: str, season: str, season_rows: list[dict]) -> str:
    """Match earlier recompute_season_validity_v1_2.py logic."""
    rows_here = [r for r in season_rows if r["crop"] == crop and r["season"] == season]
    if any(r["status"] == "cited" for r in rows_here):
        return "valid"
    if any(r["status"] == "contradicted" for r in rows_here):
        return "invalid"
    if rows_here:
        return "unknown"
    if not any(r["crop"] == crop for r in season_rows):
        return "unknown"
    return "invalid"


def season_validity_v1_2(top5: list[str], season: str, season_rows: list[dict], mode: str) -> float:
    """Season validity: fraction of crops in top5 valid for the season (matching earlier script)."""
    num = den = 0
    for p in top5:
        st = season_status(p, season, season_rows)
        if st == "valid":
            num += 1
            den += 1
        elif st == "invalid":
            den += 1
        elif mode == "strict":
            den += 1
    return num / den if den else 0.0


def hard_violation_v1_1(top5: list[str], season: str, drought: bool, flood: bool,
                        hard_rows: list[dict], mode: str) -> tuple[int, int]:
    """Hard violation: per-crop check (matching earlier script). Returns (violations, denominator)."""
    season_c = [r for r in hard_rows if r["constraint_type"] == "season"]
    drought_c = [r for r in hard_rows if r["constraint_type"] == "drought"]
    flood_c = [r for r in hard_rows if r["constraint_type"] == "flood"]
    viol = den = 0
    for p in top5:
        relevant = (
            [r for r in season_c if r["crop"] == p and r["condition"] == season]
            + ([r for r in drought_c if r["crop"] == p] if drought else [])
            + ([r for r in flood_c if r["crop"] == p] if flood else [])
        )
        cited_hit = any(r["status"] == "cited" for r in relevant)
        unknown_only = bool(relevant) and not cited_hit
        den += 1
        if cited_hit:
            viol += 1
        elif mode == "strict" and unknown_only:
            viol += 1
        elif mode == "lenient" and unknown_only:
            den -= 1
    return viol, den


def build_real_reference(clean_path: Path, window: tuple, metric: str = "area_ha", restrict: bool = True) -> dict:
    """Build reference top-5 per (district, season) cell from real data."""
    import numpy as np
    agg = defaultdict(lambda: defaultdict(list))
    with clean_path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            year_str = row.get("year", "0")
            try:
                year = int(year_str.split("-")[0])
            except (ValueError, IndexError):
                year = 0
            if year < window[0] or year > window[1]:
                continue
            in_vocab = row.get("in_vocab", "True") == "True"
            if restrict and not in_vocab:
                continue
            key = row.get("crop_vocab") if restrict else row.get("source_crop")
            district = row.get("district", "")
            season = row.get("season", "")
            val = float(row.get(metric, 0) or 0)
            if district and season and key:
                agg[(district, season)][key].append(val)
    ref = {}
    for cell, crops in agg.items():
        means = sorted(((c, float(np.mean(v))) for c, v in crops.items()),
                       key=lambda x: (-x[1], x[0]))
        ref[cell] = [c for c, _ in means[:5]]
    return ref


def precision_at_5(model_top5, ref):
    if not ref:
        return 0.0
    return len(set(model_top5) & set(ref)) / min(5, len(ref))


def recall_at_5(model_top5, ref):
    if not ref:
        return 0.0
    return len(set(model_top5) & set(ref)) / min(5, len(ref))


def ndcg_at_5(model_top5, ref):
    import math
    refset = set(ref)
    dcg = sum(1.0 / math.log2(i + 2) for i, c in enumerate(model_top5[:5]) if c in refset)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(min(5, len(ref))))
    return dcg / idcg if idcg > 0 else 0.0


def main():
    print("Loading definitions and data...")
    ns = load_defs()
    rows_v1 = load_rows(CROP_LOG_V1)
    rows_v2 = load_rows(CROP_LOG_V2)
    det_v1 = make_score(ns, rows_v1, use_windows=False)
    det_v2 = make_score(ns, rows_v2, use_windows=False)
    c3t_v1 = make_score(ns, rows_v1, use_windows=True)
    c3t_v2 = make_score(ns, rows_v2, use_windows=True)

    # Load GT tables (matching earlier analysis: v1.2 for season, v1.1 for hard)
    gt_season_rows_v12 = load_gt_season(GT_SEASON_V12)
    gt_hard_rows_v11 = load_gt_hard(GT_HARD_V1)

    # Build real references
    print("Building real references...")
    R_prim = build_real_reference(REAL_CLEAN, (2015, 2022), "area_ha", True)
    R_full = build_real_reference(REAL_CLEAN, (2015, 2024), "area_ha", True)
    R_all = build_real_reference(REAL_CLEAN, (2015, 2022), "area_ha", False)
    R_prod = build_real_reference(REAL_CLEAN, (2015, 2022), "production_t", True)
    print(f"  R_prim: {len(R_prim)} cells, R_full: {len(R_full)}, R_all: {len(R_all)}, R_prod: {len(R_prod)}")

    # Load scenarios
    scen_path = ROOT / "eval" / "data" / "scenarios.jsonl"
    scenarios = []
    with scen_path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                scenarios.append(json.loads(line))
    sid_to_scen = {s["scenario_id"]: s for s in scenarios}

    # Load risk flags (matching earlier script: drought_z_score_30d <= -1.5, flood_probability >= 0.40)
    risk_flags = {}
    for path in ARCH.glob("*.json"):
        ev = json.loads(path.read_text(encoding="utf-8"))
        risk = ev.get("risk") or {}
        try:
            d = float(risk.get("drought_z_score_30d", 0)) <= -1.5
            f = float(risk.get("flood_probability", 0)) >= 0.40
        except (TypeError, ValueError):
            d, f = False, False
        risk_flags[ev.get("scenario_id")] = {"drought": d, "flood": f}

    # Load LLM subset
    llm_sids = []
    with LLM_SUBSET.open() as f:
        for line in f:
            if line.strip():
                llm_sids.append(json.loads(line)["scenario_id"])
    print(f"LLM subset: {len(llm_sids)} scenarios")

    # ---- 1. Season validity + hard violation on 10,000 scenarios (matching earlier definition) ----
    print("\n1. Computing season validity + hard violation on 10,000 scenarios (earlier definition)...")
    results_10k = {}
    
    for inst_name, inst_func in [
        ("C3_db_v1", det_v1), ("C3_db_v2", det_v2),
        ("C3t_db_v1", c3t_v1), ("C3t_db_v2", c3t_v2)
    ]:
        sv_strict = sv_lenient = 0.0
        hv_strict_viol = hv_strict_den = 0
        hv_lenient_viol = hv_lenient_den = 0
        n = 0
        for scen in scenarios:
            sid = scen["scenario_id"]
            ev = json.loads((ARCH / f"{sid}.json").read_text(encoding="utf-8"))
            week = week_of(ev)
            top5 = [c["crop"] for c in inst_func(ev, week)][:5]
            season = scen["season_by_month"]
            rf = risk_flags.get(sid, {"drought": False, "flood": False})
            
            # Season validity (fraction of valid crops in top5)
            sv_strict += season_validity_v1_2(top5, season, gt_season_rows_v12, "strict")
            sv_lenient += season_validity_v1_2(top5, season, gt_season_rows_v12, "lenient")
            
            # Hard violation (per-crop)
            viol_s, den_s = hard_violation_v1_1(top5, season, rf["drought"], rf["flood"], gt_hard_rows_v11, "strict")
            viol_l, den_l = hard_violation_v1_1(top5, season, rf["drought"], rf["flood"], gt_hard_rows_v11, "lenient")
            hv_strict_viol += viol_s
            hv_strict_den += den_s
            hv_lenient_viol += viol_l
            hv_lenient_den += den_l
            n += 1
        
        results_10k[inst_name] = {
            "season_validity_strict": round(sv_strict / n, 6),
            "season_validity_lenient": round(sv_lenient / n, 6),
            "hard_violation_strict": round(hv_strict_viol / hv_strict_den, 6) if hv_strict_den else 0,
            "hard_violation_lenient": round(hv_lenient_viol / hv_lenient_den, 6) if hv_lenient_den else 0,
            "n_scenarios": n,
            "n_crop_checks": 5 * n,
        }
        print(f"  {inst_name}: sv_strict={results_10k[inst_name]['season_validity_strict']:.4f}, "
              f"sv_lenient={results_10k[inst_name]['season_validity_lenient']:.4f}, "
              f"hv_strict={results_10k[inst_name]['hard_violation_strict']:.4f}, "
              f"hv_lenient={results_10k[inst_name]['hard_violation_lenient']:.4f}")

    # ---- 2. Real-data metrics on LLM subset (unchanged definition) ----
    print("\n2. Computing real-data metrics on LLM subset...")
    real_metrics = {}
    for inst_name, inst_func in [("C3_db_v1", det_v1), ("C3t_db_v1", c3t_v1)]:
        for ref_name, ref_table in [("R_prim", R_prim), ("R_full", R_full), ("R_all", R_all), ("R_prod", R_prod)]:
            prec_sum = rec_sum = ndcg_sum = 0
            n_eval = 0
            for sid in llm_sids:
                ev = json.loads((ARCH / f"{sid}.json").read_text(encoding="utf-8"))
                week = week_of(ev)
                top5 = [c["crop"] for c in inst_func(ev, week)][:5]
                district = sid_to_scen[sid]["district"]
                season = sid_to_scen[sid]["season_by_month"]
                ref = ref_table.get((district, season), [])
                
                prec_sum += precision_at_5(top5, ref)
                rec_sum += recall_at_5(top5, ref)
                ndcg_sum += ndcg_at_5(top5, ref)
                n_eval += 1
            
            key = f"{inst_name}_{ref_name}"
            real_metrics[key] = {
                "precision_at_5": round(prec_sum / n_eval, 6) if n_eval else 0,
                "recall_at_5": round(rec_sum / n_eval, 6) if n_eval else 0,
                "ndcg_at_5": round(ndcg_sum / n_eval, 6) if n_eval else 0,
                "n_evaluated": n_eval
            }
            print(f"  {key}: P@5={real_metrics[key]['precision_at_5']:.4f}, "
                  f"R@5={real_metrics[key]['recall_at_5']:.4f}, "
                  f"nDCG@5={real_metrics[key]['ndcg_at_5']:.4f} (n={n_eval})")

    # ---- 3. S-series metrics (load from S_FOLLOWUP) ----
    print("\n3. Loading S-series metrics...")
    S_FOLLOWUP = ROOT / "eval" / "results" / "s_followup.json"
    if S_FOLLOWUP.exists():
        s_followup = json.loads(S_FOLLOWUP.read_text(encoding="utf-8"))
    else:
        s_followup = {}

    # ---- 4. 45 WET cases ----
    print("\n4. Loading 45 WET cases...")
    S_FOLLOWUP_CASES = ROOT / "eval" / "results" / "s_followup_cases.json"
    if S_FOLLOWUP_CASES.exists():
        wet_cases = json.loads(S_FOLLOWUP_CASES.read_text(encoding="utf-8"))
    else:
        wet_cases = {}

    # ---- 5. Reconciliation: compare C3 with earlier registered numbers ----
    print("\n5. Reconciliation with earlier registered analysis...")
    earlier = {
        "C3_db_v1": {
            "season_validity_strict": 0.83590,
            "season_validity_lenient": 0.83590,
            "hard_violation_strict": 0.11464,
            "hard_violation_lenient": 0.09459,
            "source": "eval/results/c3_season_validity_v1.2_vs_v1.1.json (v1.2|strict/lenient)",
            "gt_season": "crop_season_table_v1.2.csv (Jowar/Rabi, Arhar/Rabi = contradicted)",
            "gt_hard": "hard_constraints_v1.1.csv",
            "definition": "season_validity = mean over scenarios of (valid crops in top5 / crops checked); hard_violation = total violations / (5 * n_scenarios)"
        }
    }
    
    # Verify our C3_db_v1 matches earlier
    c3_db_v1_sv_strict = results_10k["C3_db_v1"]["season_validity_strict"]
    c3_db_v1_hv_strict = results_10k["C3_db_v1"]["hard_violation_strict"]
    print(f"  Earlier C3 strict sv: 0.83590, Our C3_db_v1 strict sv: {c3_db_v1_sv_strict:.5f}, Match: {abs(c3_db_v1_sv_strict - 0.83590) < 0.0001}")
    print(f"  Earlier C3 strict hv: 0.11464, Our C3_db_v1 strict hv: {c3_db_v1_hv_strict:.5f}, Match: {abs(c3_db_v1_hv_strict - 0.11464) < 0.0001}")

    # ---- Compile results ----
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload = {
        "registered": "PROTOCOL 8.35 (instrument correction, not tuning), 2026-10-19 22:56:19 UTC",
        "generated": now,
        "instruments": {
            "C3": "run_deterministic_v2.py::score_crops full_repo (empty sowing windows; registered, unchanged)",
            "C3t": "identical pipeline passing real sowing_start_week/sowing_end_week into _season_alignment_score",
            "db_v2 variants": "same two instruments with crop_log_v2 rows",
        },
        "weights": W,
        "metric_definitions": {
            "season_validity": "Fraction of crops in top5 valid for scenario season (per-crop check, mean over scenarios). Matches recompute_season_validity_v1_2.py.",
            "hard_violation": "Per-crop check against season/drought/flood constraints; rate = violations / (5 * n_scenarios). Matches recompute_season_validity_v1_2.py.",
        },
        "gt_used": {
            "season": "crop_season_table_v1.2.csv (Jowar/Rabi, Arhar/Rabi = contradicted)",
            "hard": "hard_constraints_v1.1.csv",
        },
        "reconciliation": {
            "earlier_C3_v1.2_strict": earlier["C3_db_v1"],
            "our_C3_db_v1": results_10k["C3_db_v1"],
            "match_sv": abs(c3_db_v1_sv_strict - 0.83590) < 0.0001,
            "match_hv": abs(c3_db_v1_hv_strict - 0.11464) < 0.0001,
        },
        "season_validity_hard_violation_10k": results_10k,
        "real_data_metrics_llm_subset": real_metrics,
        "s_followup_data": s_followup,
        "wet_cases": wet_cases,
    }

    out_file = OUT_DIR / "c3t_correction_analysis.json"
    out_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nWrote {out_file}")

    # Create summary for CORRECTION_NOTE.md
    summary = {
        "season_validity_hard_violation_old_vs_new": {
            "C3_db_v1": results_10k["C3_db_v1"],
            "C3t_db_v1": results_10k["C3t_db_v1"],
            "C3_db_v2": results_10k["C3_db_v2"],
            "C3t_db_v2": results_10k["C3t_db_v2"],
        },
        "real_data_metrics_old_vs_new": {
            "C3_db_v1_R_prim": real_metrics.get("C3_db_v1_R_prim", {}),
            "C3t_db_v1_R_prim": real_metrics.get("C3t_db_v1_R_prim", {}),
            "C3_db_v1_R_full": real_metrics.get("C3_db_v1_R_full", {}),
            "C3t_db_v1_R_full": real_metrics.get("C3t_db_v1_R_full", {}),
            "C3_db_v1_R_all": real_metrics.get("C3_db_v1_R_all", {}),
            "C3t_db_v1_R_all": real_metrics.get("C3t_db_v1_R_all", {}),
            "C3_db_v1_R_prod": real_metrics.get("C3_db_v1_R_prod", {}),
            "C3t_db_v1_R_prod": real_metrics.get("C3t_db_v1_R_prod", {}),
        }
    }
    summary_file = OUT_DIR / "c3t_correction_summary.json"
    summary_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Wrote {summary_file}")


if __name__ == "__main__":
    main()