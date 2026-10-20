"""C3t correction analysis (PROTOCOL 8.35): full metric recomputation.

INSTRUMENT CORRECTION, NOT TUNING. Offline; NO model calls; no frozen file changed.
"""

from __future__ import annotations

import csv
import json
import math
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


def load_gt_season(path: Path) -> dict:
    """Load crop season table: crop -> set of valid seasons (cited and all)."""
    gt = {}
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            crop = row.get("crop") or row.get("Crop") or ""
            season = row.get("season") or ""
            status = row.get("status", "").lower()
            if crop and season:
                gt.setdefault(crop, {"cited": set(), "all": set()})
                gt[crop]["all"].add(season)
                if status == "cited":
                    gt[crop]["cited"].add(season)
    return gt


def load_gt_hard(path: Path) -> dict:
    """Load hard constraints: (crop, constraint_type, condition) -> cited flag."""
    hard = {}
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            ctype = row.get("constraint_type", "")
            crop = row.get("crop", "")
            condition = row.get("condition", "")
            status = row.get("status", "").lower()
            if crop and condition:
                hard[(crop, ctype, condition)] = (status == "cited")
    return hard


def build_real_reference(clean_path: Path, window: tuple, metric: str = "area_ha", restrict: bool = True) -> dict:
    """Build reference top-5 per (district, season) cell from real data."""
    import numpy as np
    agg = defaultdict(lambda: defaultdict(list))
    with clean_path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            year_str = row.get("year", "0")
            # Year format is "2015-2016" - extract first year
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


def season_validity(top5: list[str], scenario_season: str, gt_season: dict, mode: str) -> float:
    """Check if top-1 crop season matches scenario season."""
    if not top5:
        return 0.0
    top1 = top5[0]
    valid_seasons = gt_season.get(top1, {}).get(mode, set())
    return 1.0 if scenario_season in valid_seasons else 0.0


def hard_violation(top5: list[str], risk: dict, gt_hard: dict, mode: str) -> float:
    """Check if any crop in top5 violates hard constraints."""
    if not top5:
        return 0.0
    for crop in top5:
        # Season constraints
        for (hc_crop, hc_type, hc_cond), cited in gt_hard.items():
            if hc_crop != crop or hc_type != "season":
                continue
            if mode == "strict" and not cited:
                return 1.0
            # Check if crop's season matches the forbidden condition
            # The condition is the forbidden season
            # We need to check if the scenario season == forbidden condition
            # But we don't have scenario season here - it's passed separately
            pass
    return 0.0  # Simplified for now


def hard_violation_full(top5: list[str], scenario_season: str, risk: dict, gt_hard: dict, mode: str) -> float:
    """Check if any crop in top5 violates hard constraints for the scenario."""
    if not top5:
        return 0.0
    for crop in top5:
        for (hc_crop, hc_type, hc_cond), cited in gt_hard.items():
            if hc_crop != crop:
                continue
            if mode == "strict" and not cited:
                return 1.0
            if hc_type == "season" and scenario_season == hc_cond:
                return 1.0
            if hc_type == "drought" and (risk.get("drought_probability") or 0) >= 0.4:
                return 1.0
            if hc_type == "flood" and (risk.get("flood_probability") or 0) >= 0.4:
                return 1.0
            if hc_type == "heat" and (risk.get("heatwave_probability") or 0) >= 0.35:
                return 1.0
    return 0.0


def precision_at_5(model_top5, ref):
    if not ref:
        return 0.0
    return len(set(model_top5) & set(ref)) / min(5, len(ref))


def recall_at_5(model_top5, ref):
    if not ref:
        return 0.0
    return len(set(model_top5) & set(ref)) / min(5, len(ref))


def ndcg_at_5(model_top5, ref):
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

    gt_season_v1 = load_gt_season(GT_SEASON_V1)
    gt_season_v12 = load_gt_season(GT_SEASON_V12)
    gt_hard = load_gt_hard(GT_HARD_V1)

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
    district_of = {s["scenario_id"]: s["district"] for s in scenarios}
    season_of = {s["scenario_id"]: s["season_by_month"] for s in scenarios}

    print(f"Loaded {len(scenarios)} scenarios")

    # Load LLM subset
    llm_sids = []
    with LLM_SUBSET.open() as f:
        for line in f:
            if line.strip():
                llm_sids.append(json.loads(line)["scenario_id"])
    print(f"LLM subset: {len(llm_sids)} scenarios")

    # ---- 1. Season validity + hard violation on 10,000 scenarios ----
    print("\n1. Computing season validity + hard violation on 10,000 scenarios...")
    results_10k = {}
    
    for inst_name, inst_func in [
        ("C3_db_v1", det_v1), ("C3_db_v2", det_v2),
        ("C3t_db_v1", c3t_v1), ("C3t_db_v2", c3t_v2)
    ]:
        sv_strict = sv_lenient = hv_strict = hv_lenient = 0
        n = 0
        for scen in scenarios:
            sid = scen["scenario_id"]
            ev = json.loads((ARCH / f"{sid}.json").read_text(encoding="utf-8"))
            week = week_of(ev)
            top5 = [c["crop"] for c in inst_func(ev, week)][:5]
            season = scen["season_by_month"]
            
            sv_strict += season_validity(top5, season, gt_season_v1, "cited")
            sv_lenient += season_validity(top5, season, gt_season_v1, "all")
            hv_strict += hard_violation_full(top5, season, ev["risk"], gt_hard, "strict")
            hv_lenient += hard_violation_full(top5, season, ev["risk"], gt_hard, "lenient")
            n += 1
        
        results_10k[inst_name] = {
            "season_validity_strict": round(sv_strict / n, 6),
            "season_validity_lenient": round(sv_lenient / n, 6),
            "hard_violation_strict": round(hv_strict / n, 6),
            "hard_violation_lenient": round(hv_lenient / n, 6),
            "n": n
        }
        print(f"  {inst_name}: sv_strict={results_10k[inst_name]['season_validity_strict']:.4f}, "
              f"sv_lenient={results_10k[inst_name]['season_validity_lenient']:.4f}, "
              f"hv_strict={results_10k[inst_name]['hard_violation_strict']:.4f}, "
              f"hv_lenient={results_10k[inst_name]['hard_violation_lenient']:.4f}")

    # ---- 2. Real-data metrics on LLM subset ----
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
                district = district_of[sid]
                season = season_of[sid]
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

    # ---- 3. C2a vs C3/C3t match/beat/lose (from clustered inference) ----
    print("\n3. Loading C2a vs C3/C3t breakdown...")
    CLUSTERED_INF = ROOT / "eval" / "results" / "n500_clustered_inference.json"
    if CLUSTERED_INF.exists():
        clustered = json.loads(CLUSTERED_INF.read_text(encoding="utf-8"))
        mbl = clustered.get("match_beat_lose", {})
        print(f"  C2a vs C3 (strict PP sv): {mbl}")
    else:
        mbl = {}
        print("  WARNING: n500_clustered_inference.json not found")

    # ---- 4. S-series metrics (load from S_FOLLOWUP) ----
    print("\n4. Loading S-series metrics...")
    S_FOLLOWUP = ROOT / "eval" / "results" / "s_followup.json"
    if S_FOLLOWUP.exists():
        s_followup = json.loads(S_FOLLOWUP.read_text(encoding="utf-8"))
        print(f"  S_FOLLOWUP keys: {list(s_followup.keys())}")
    else:
        s_followup = {}
        print("  WARNING: s_followup.json not found")

    # ---- 5. 45 WET cases (load from S_FOLLOWUP cases) ----
    print("\n5. Loading 45 WET cases...")
    S_FOLLOWUP_CASES = ROOT / "eval" / "results" / "s_followup_cases.json"
    if S_FOLLOWUP_CASES.exists():
        wet_cases = json.loads(S_FOLLOWUP_CASES.read_text(encoding="utf-8"))
        print(f"  WET cases loaded: {len(wet_cases)} items")
    else:
        wet_cases = {}
        print("  WARNING: s_followup_cases.json not found")

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
        "season_validity_hard_violation_10k": results_10k,
        "real_data_metrics_llm_subset": real_metrics,
        "c2a_vs_c3_match_beat_lose": mbl,
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