"""GT / scorer PROVENANCE AUDIT (offline; items 8-11; NO API calls).

Question: do the deterministic C3 scorer's `season_alignment` component and its
hard/risk filters draw on the SAME registry as the source-cited ground-truth tables
used by the LLM season-validity / hard-violation metrics?

Sources compared:
  * crop_log.csv (repo root)               -> used by run_deterministic_v2.py (C3 scorer:
    season_supported, sowing_*_week, peak_water_week, risk_sensitivity, Rainfall,
    Tempreture, Soil Type). No source/citation column.
  - eval/data/ground_truth/crop_season_table_v1.1.csv   -> used by stage_a_interim_metrics.py
    (LLM season-validity). Per-row source_ref + status.
  - eval/data/ground_truth/hard_constraints_v1.1.csv    -> used by stage_a_interim_metrics.py
    (LLM hard-violation). Per-row source_ref + status.
  - eval/metrics.py CROP_SEASON_VALIDITY / WATER_INTENSIVE_CROPS (legacy hardcoded helpers).
  - eval/data/ground_truth/UNVERIFIED_FOR_REVIEW.csv.
  - eval/config.yaml ablations.weights.repo (scorer season weight).

OFFLINE only: no network, no API.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from eval import metrics as metrics_mod  # noqa: E402

SEASON_TABLE = ROOT / "eval/data/ground_truth/crop_season_table_v1.1.csv"
HARD_TABLE = ROOT / "eval/data/ground_truth/hard_constraints_v1.1.csv"
UNVER = ROOT / "eval/data/ground_truth/UNVERIFIED_FOR_REVIEW.csv"
CROP_LOG = ROOT / "crop_log.csv"
CONFIG = ROOT / "eval/config.yaml"
OUT_TXT = ROOT / "eval/results/gt_provenance_audit.txt"
OUT_JSON = ROOT / "eval/results/gt_provenance_audit.json"

SEASONS = ["Kharif", "Rabi", "Zaid"]
_records: list[str] = []
RESULTS: dict = {}


def emit(s: str = "") -> None:
    print(s)
    _records.append(s)


def split_seasons(v: str) -> set[str]:
    parts = [p.strip() for p in re.split(r"[/,]", v or "") if p.strip()]
    return set(parts) or {"Annual"}


def scorer_seasons(seasons: set[str]) -> set[str]:
    return set(SEASONS) if "Annual" in seasons else {s for s in seasons if s in SEASONS}


def load_cfg_weights() -> dict:
    txt = CONFIG.read_text(encoding="utf-8")
    m = re.search(r"repo:\s*\{([^}]*)\}", txt)
    out = {}
    if m:
        for kv in m.group(1).split(","):
            k, _, v = kv.partition(":")
            try:
                out[k.strip()] = float(v.strip())
            except ValueError:
                pass
    return out


def main() -> None:
    with CROP_LOG.open(encoding="utf-8", newline="") as fh:
        crop_rows = list(csv.DictReader(fh))
    with SEASON_TABLE.open(encoding="utf-8", newline="") as fh:
        season_rows = list(csv.DictReader(fh))
    with HARD_TABLE.open(encoding="utf-8", newline="") as fh:
        hard_rows = list(csv.DictReader(fh))
    with UNVER.open(encoding="utf-8", newline="") as fh:
        unver_rows = list(csv.DictReader(fh))

    emit("=" * 100)
    emit("GT PROVENANCE AUDIT (items 8-11)  -  deterministic scorer vs cited GT tables")
    emit("=" * 100)

    # ---- item 8: registry provenance ----
    emit("\n[8] REGISTRY / PROVENANCE")
    crop_cols = list(crop_rows[0].keys())
    emit(f"  scorer registry   : crop_log.csv columns = {crop_cols}")
    emit(f"                      has source/citation column? "
         f"{any('source' in c.lower() or 'ref' in c.lower() or 'cite' in c.lower() for c in crop_cols)}")
    emit(f"  GT season table   : columns = {list(season_rows[0].keys())}")
    emit(f"  GT hard table     : columns = {list(hard_rows[0].keys())}")
    emit(f"  -> scorer (C3) reads crop_log.csv (UNCITED); LLM metrics (stage_a) read the")
    emit(f"     cited GT tables v1.1. These are SEPARATE source files (no shared key/registry).")

    # ---- item 9: season-membership agreement ----
    emit("\n[9] SCORER SEASONS (crop_log) vs GT CITED SEASONS")
    emit(f"  {'crop':14s} {'scorer(crop_log)':22s} {'GT cited':24s} "
         f"{'metrics.py CROP_SEASON_VALIDITY':30s} agree?")
    diffs = {}
    for row in crop_rows:
        crop = row["Crop"]
        sc = scorer_seasons(split_seasons(row.get("season_supported", "")))
        gt = scorer_seasons({r["season"] for r in season_rows
                             if r["crop"] == crop and r["status"] == "cited"})
        gt_raw = {r["season"] for r in season_rows if r["crop"] == crop}
        mp = metrics_mod.CROP_SEASON_VALIDITY.get(crop, set())
        mp_sc = scorer_seasons(mp)
        agree = (sc == gt) and (sc == mp_sc)
        if not agree:
            diffs[crop] = {"crop_log": sorted(sc), "gt_cited": sorted(gt),
                           "gt_all_status": sorted(gt_raw), "metrics_py": sorted(mp_sc)}
        emit(f"  {crop:24s} {','.join(sorted(sc)):30s} {','.join(sorted(gt)):30s} "
             f"{','.join(sorted(mp_sc)):30s} {'yes' if agree else 'NO'}")
    emit(f"\n  disagreements (scorer/metrics.py vs cited GT): {len(diffs)}")
    for c, d in diffs.items():
        emit(f"    - {c}: crop_log={d['crop_log']}  metrics.py={d['metrics_py']}  "
             f"GT cited={d['gt_cited']}  (GT rows present: {d['gt_all_status']})")
    emit("  NOTE: metrics.CROP_SEASON_VALIDITY == crop_log-derived (its comment says 'from "
         "crop_log.csv'); the cited GT table is a DIFFERENT file and adds cited seasons "
         "(e.g. Groundnut/Urad/Sunflower Zaid or extra) the scorer would call invalid.")
    RESULTS["season_registry_diffs"] = diffs

    # ---- item 9b: scorer season-validity on GT-cited seasons ----
    emit("\n[8b] SCORER SEASON WEIGHT + RISK-SENSITIVITY WEIGHTS")
    w = load_cfg_weights()
    emit(f"  config ablations.weights.repo = {w}  -> scorer 'season' weight = {w.get('season')}")
    emit("  run_deterministic_v2 RISK_SENSITIVITY_WEIGHTS = {high:1.0, medium:0.65, low:0.35}")
    emit("  -> NOTE: 0.35 is the RISK-sensitivity 'low' weight, NOT the season-alignment "
         "weight (which is 0.30 in config.yaml:137).")
    RESULTS["weights"] = {"repo": w, "risk_sensitivity": {"high": 1.0, "medium": 0.65, "low": 0.35}}

    # ---- item 10: hard-constraint registry ----
    emit("\n[10] HARD-CONSTRAINT REGISTRY")
    by_type: dict[str, list] = {}
    for r in hard_rows:
        by_type.setdefault(r["constraint_type"], []).append(r)
    for t, rows in by_type.items():
        cited = [r for r in rows if r["status"] == "cited"]
        unv = [r for r in rows if r["status"].startswith("unverified")]
        emit(f"  type={t:8s} rows={len(rows)} cited={len(cited)} unverified={len(unv)}")
    season_hard = {r["crop"] for r in by_type.get("season", [])}
    drought_hard = {r["crop"] for r in by_type.get("drought", [])}
    flood_hard = {r["crop"] for r in by_type.get("flood", [])}
    emit(f"  season-hard crops   : {sorted(season_hard)}")
    emit(f"  drought-hard crops  : {sorted(drought_hard)}  (statuses: "
         f"{sorted({r['status'] for r in by_type.get('drought', [])})})")
    emit(f"  flood-hard  crops   : {sorted(flood_hard)}  (statuses: "
         f"{sorted({r['status'] for r in by_type.get('flood', [])})})")
    emit(f"  metrics.WATER_INTENSIVE_CROPS = {sorted(metrics_mod.WATER_INTENSIVE_CROPS)}")
    only_metrics = sorted(metrics_mod.WATER_INTENSIVE_CROPS - drought_hard)
    emit(f"  -> drought proxy from metrics.py adds crops NOT in the cited GT drought set: "
         f"{only_metrics}  (metrics.py is a heuristic; the PRIMARY metric (stage_a) uses GT).")
    RESULTS["hard_constraints"] = {
        "season_hard": sorted(season_hard), "drought_hard": sorted(drought_hard),
        "flood_hard": sorted(flood_hard), "metrics_water_intensive": sorted(metrics_mod.WATER_INTENSIVE_CROPS),
    }

    # ---- item 11: unverified counts ----
    emit("\n[11] UNVERIFIED / PENDING ROWS")
    from collections import Counter
    c_table = Counter(r["table"] for r in unver_rows)
    c_stat = Counter(r["current_status"] for r in unver_rows)
    c_type = Counter((r["table"], r["type"]) for r in unver_rows)
    emit(f"  UNVERIFIED_FOR_REVIEW.csv rows =  {len(unver_rows)}")
    emit(f"  by table        : {dict(c_table)}")
    emit(f"  by status       : {dict(c_stat)}")
    for (t, ty), n in sorted(c_type.items()):
        emit(f"    {t:20s} {ty:20s} n={n}")
    emit("  (rows still 'unverified' today = "
         f"{sum(1 for r in unver_rows if r['current_status'] == 'unverified')}; "
         "'cited-v1.1' rows were upgraded in v1.1.)")
    RESULTS["unverified"] = {"n": len(unver_rows), "by_table": dict(c_table),
                             "by_status": dict(c_stat)}

    # ---- conclusion ----
    emit("\n" + "=" * 100)
    emit("CONCLUSION")
    emit("=" * 100)
    emit("  * The deterministic scorer (C3) is built on crop_log.csv, which carries NO source "
         "citations; the LLM metrics (season-validity, hard-violation) are evaluated against the "
         "SEPARATELY cited GT tables (v1.1).")
    emit("  * The two registries AGREE on most crops but DIVERGE on "
         f"{len(diffs)}: {', '.join(diffs) or 'none'} -> the scorer would label some "
         "GT-cited seasons invalid.")
    emit("  * Therefore the scorer's GT dependence is INDEPENDENT of (not shared with) the "
         "evaluated GT tables; report this as a provenance/methods note, and report the "
         "divergent crops explicitly.")
    emit("  * Scorer season weight = 0.30 (config.yaml:137); the 0.35 constant is the "
         "risk-sensitivity 'low' weight.")

    OUT_JSON.write_text(json.dumps(RESULTS, indent=2, default=list), encoding="utf-8")
    OUT_TXT.write_text("\n".join(_records) + "\n", encoding="utf-8")
    emit(f"\nwrote {OUT_TXT}")
    emit(f"wrote {OUT_JSON}")


if __name__ == "__main__":
    main()
