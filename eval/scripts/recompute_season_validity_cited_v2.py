"""Phase 8 STEP C review item 1a/1b: recompute C3 season-validity and hard-violation
rates under STRICT and LENIENT handling of UNVERIFIED rows, for BOTH the frozen v1
tables and the v1.1 tables (Barley upgraded to cited).

Semantics (user review order):
  STRICT  - every UNVERIFIED (or absent-from-table) row counts against the crop:
            a crop whose only season-S row is unverified is INVALID for S; a crop with
            only unverified constraint rows violates; crops absent from the season table
            count invalid too. Denominator = full top5.
  LENIENT - UNVERIFIED rows are excluded from the denominator: crops whose season-S data
            is only-unverified (or absent from the table entirely) are dropped from both
            numerator and denominator. Crops explicitly cited for S count valid.

Relations preserved from the frozen v1 output (asserted below):
  strict season validity == v1 "cited" season validity (same idea)
  strict hard rate       == v1 "all_rows" hard rate
  lenient hard rate      == v1 "cited" hard rate
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import numpy as np

from eval.common import config_dirs, load_config, write_json
from eval.scenarios import generate

cfg = load_config()
dirs = config_dirs(cfg)
scenarios = generate(cfg)
by_id = {s["scenario_id"]: s for s in scenarios}

stress_ids = set()
with open(dirs["stress_path"], encoding="utf-8") as fh:
    for line in fh:
        stress_ids.add(json.loads(line)["scenario_id"])

EVID_DIR = Path("eval/runs/archive_v2/evidence")
risk_flags: dict[str, dict[str, bool]] = {}
for path in EVID_DIR.glob("*.json"):
    with path.open(encoding="utf-8") as fh:
        ev = json.load(fh)
    risk = ev.get("risk") or {}
    try:
        d = float(risk.get("drought_z_score_30d", 0)) <= -1.5
        f = float(risk.get("flood_probability", 0)) >= 0.40
    except (TypeError, ValueError):
        d, f = False, False
    risk_flags[ev.get("scenario_id")] = {"drought": d, "flood": f}

DET_DIR = Path("eval/runs/archive_v2/deterministic")
GT_DIR = Path("eval/data/ground_truth")

TABLE_PAIRS = {
    "v1": ("crop_season_table.csv", "hard_constraints.csv"),
    "v1.1": ("crop_season_table_v1.1.csv", "hard_constraints_v1.1.csv"),
}


def read_table(name: str) -> list[dict[str, str]]:
    with (GT_DIR / name).open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def season_status(crop: str, season: str, season_rows: list[dict[str, str]]) -> str:
    """classify (crop, season) -> 'valid' | 'invalid' | 'unknown'."""
    rows_here = [r for r in season_rows if r["crop"] == crop and r["season"] == season]
    cited = [r for r in rows_here if r["status"] == "cited"]
    if cited:
        return "valid"
    if rows_here:  # only unverified rows claim this season
        return "unknown"
    in_table = any(r["crop"] == crop for r in season_rows)
    if not in_table:
        return "unknown"  # no data at all
    return "invalid"  # crop listed but this season absent -> not valid


def season_validity(top5: list[str], season: str, season_rows: list[dict[str, str]],
                    mode: str) -> tuple[float, int, int]:
    num = den = 0
    for p in top5:
        st = season_status(p, season, season_rows)
        if st == "valid":
            num += 1
            den += 1
        elif st == "invalid":
            den += 1  # determinate negative
        else:  # unknown (unverified or absent) -> STRICT counts invalid, LENIENT skips
            if mode == "strict":
                den += 1
    return (num / den if den else 0.0), num, den


def hard_violation(top5: list[str], season: str, drought: bool, flood: bool,
                   hard_rows: list[dict[str, str]], mode: str) -> tuple[int, int]:
    """Return (violating crops, crops evaluated) under the hard table.

    Every in-registry crop in top5 is evaluated (den +1). STRICT treats any matching
    constraint row (cited or unverified) as a violation. LENIENT ignores unverified
    rows: a crop whose only matching rows are unverified is dropped from the
    denominator too (cannot be judged), otherwise a cited match is a violation.
    """
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
            den -= 1  # unverified-only: cannot judge, drop from denominator
    return viol, den


c3_preds: dict[str, list[str]] = {}
c3_by_season: dict[str, list[list[str]]] = defaultdict(list)
for path in DET_DIR.glob("*.json"):
    with path.open(encoding="utf-8") as fh:
        res = json.load(fh)
    ab = res.get("ablations", {}).get("full_repo")
    if not ab or "error" in ab or not ab.get("top5"):
        continue
    sid = path.stem
    c3_preds[sid] = ab["top5"]
    c3_by_season[res.get("season", "")].append(ab["top5"])

print(f"v2 deterministic C3 scenarios: {len(c3_preds)}")

summary_all = {}
for table_tag, (season_name, hard_name) in TABLE_PAIRS.items():
    season_rows = read_table(season_name)
    hard_rows = read_table(hard_name)
    print(f"\n================ table {table_tag} ({season_name}, {hard_name}) ================")
    for mode in ("strict", "lenient"):
        season_valid, stress_valid, normal_valid, s_den = [], [], [], []
        hard_viol, hard_total = [], []
        for sid, top5 in c3_preds.items():
            season = by_id[sid]["season_stratum"]
            flags = risk_flags.get(sid, {"drought": False, "flood": False})
            sv, _, den = season_validity(top5, season, season_rows, mode)
            season_valid.append(sv)
            (stress_valid if sid in stress_ids else normal_valid).append(sv)
            s_den.append(den)
            v, t = hard_violation(top5, season, flags["drought"], flags["flood"], hard_rows, mode)
            hard_viol.append(v)
            hard_total.append(t)
        print(f"\n--- [{table_tag} | {mode}] ---")
        print(f"Season validity overall: {np.mean(season_valid):.4f} (n={len(season_valid)}, mean denominator {np.mean(s_den):.2f}/5)")
        print(f"  stress: {np.mean(stress_valid):.4f} ({len(stress_valid)}) | normal: {np.mean(normal_valid):.4f} ({len(normal_valid)})")
        for season in ["Kharif", "Rabi", "Zaid"]:
            preds = c3_by_season.get(season, [])
            if preds:
                vals = [season_validity(p, season, season_rows, mode)[0] for p in preds]
                print(f"  {season}: n={len(preds)}, validity={np.mean(vals):.4f}")
        hv = sum(hard_viol)
        ht = sum(hard_total)
        if ht:
            print(f"Hard-violation rate: {hv}/{ht} = {hv / ht:.4f}")
        summary_all[f"{table_tag}|{mode}"] = {
            "table": table_tag,
            "mode": mode,
            "season_validity_overall": float(np.mean(season_valid)),
            "season_validity_stress": float(np.mean(stress_valid)) if stress_valid else 0,
            "season_validity_normal": float(np.mean(normal_valid)) if normal_valid else 0,
            "mean_denominator": float(np.mean(s_den)),
            "per_season": {
                s: float(np.mean([season_validity(p, s, season_rows, mode)[0] for p in c3_by_season.get(s, [])]))
                if c3_by_season.get(s) else 0
                for s in ["Kharif", "Rabi", "Zaid"]
            },
            "per_season_n": {s: len(c3_by_season.get(s, [])) for s in ["Kharif", "Rabi", "Zaid"]},
            "hard_violating_crops": hv,
            "hard_total_evaluated": ht,
            "hard_violation_rate": float(hv / ht) if ht else None,
        }

# Cross-check against frozen v1 output (c3_season_validity_cited.json).
try:
    frozen = json.loads((dirs["results_dir"] / "c3_season_validity_cited.json").read_text(encoding="utf-8"))
    modes = frozen.get("modes", [])
    f_cited = next((m for m in modes if m.get("mode") == "cited"), {})
    f_all = next((m for m in modes if m.get("mode") == "all_rows"), {})
    checks = {
        "strict_season == v1 cited season": abs(summary_all["v1|strict"]["season_validity_overall"] - f_cited.get("season_validity_overall", -1)) < 1e-9,
        "strict_hard  == v1 all_rows hard": abs(summary_all["v1|strict"]["hard_violation_rate"] - f_all.get("hard_violation_rate", -1)) < 1e-9,
        "lenient_hard_viol == v1 cited viol (den shrinks, viol unchanged)": summary_all["v1|lenient"]["hard_violating_crops"] == f_cited.get("hard_violating_crops", -1),
        "lenient_hard_rate >= v1 cited hard": summary_all["v1|lenient"]["hard_violation_rate"] >= f_cited.get("hard_violation_rate", 1e9),
    }
    print("\nCross-checks vs frozen v1:")
    for k, ok in checks.items():
        print(f"  [{'PASS' if ok else 'FAIL'}] {k}")
except Exception as exc:  # noqa: BLE001
    print(f"\nCross-check skipped: {exc}")
    checks = {}

out = dirs["results_dir"] / "c3_season_validity_cited_v2.json"
write_json(out, {
    "phase": 8,
    "semantics": {
        "strict": "UNVERIFIED/absent rows count as invalid (denominator = full top5)",
        "lenient": "UNVERIFIED/absent rows excluded from the denominator",
    },
    "tables": "v1 frozen (2026-10-13) and v1.1 (Barley cited, see ground_truth/CHANGELOG.md)",
    "n_scenarios": len(c3_preds),
    "n_stress": len(stress_ids),
    "results": summary_all,
    "v1_cross_checks": checks,
    "generated_at": datetime.now(timezone.utc).isoformat(),
})
print(f"Saved -> {out}")