"""STEP 5c: recompute C3 season-validity / hard-violation under ground-truth v1.1
vs v1.2 (only change: Jowar/Rabi and Arhar/Rabi season rows retracted as
'contradicted' by the DES real-area reference). v1.1 tables are untouched.

A 'contradicted' season row is a determinate negative (like 'invalid'): the crop
is treated as NOT valid for that season under BOTH STRICT and LENIENT modes. A
still-'unverified' row keeps the previous behaviour (STRICT=doubtful-counted,
LENIENT=excluded).

Writes eval/results/c3_season_validity_v1.2_vs_v1.1.{txt,json}.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
import numpy as np  # noqa: E402

from eval.common import config_dirs, load_config, write_json  # noqa: E402

cfg = load_config()
dirs = config_dirs(cfg)

GT = ROOT / "eval/data/ground_truth"
EVID = ROOT / "eval/runs/archive_v2/evidence"
DET = ROOT / "eval/runs/archive_v2/deterministic"

stress_ids = set()
with open(dirs["stress_path"], encoding="utf-8") as fh:
    for line in fh:
        stress_ids.add(json.loads(line)["scenario_id"])

risk_flags: dict[str, dict[str, bool]] = {}
for path in EVID.glob("*.json"):
    ev = json.loads(path.read_text(encoding="utf-8"))
    risk = ev.get("risk") or {}
    try:
        d = float(risk.get("drought_z_score_30d", 0)) <= -1.5
        f = float(risk.get("flood_probability", 0)) >= 0.40
    except (TypeError, ValueError):
        d, f = False, False
    risk_flags[ev.get("scenario_id")] = {"drought": d, "flood": f}

TABLE_PAIRS = {
    "v1.1": ("crop_season_table_v1.1.csv", "hard_constraints_v1.1.csv"),
    "v1.2": ("crop_season_table_v1.2.csv", "hard_constraints_v1.1.csv"),
}


def read_table(name):
    with (GT / name).open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def season_status(crop, season, season_rows):
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


def season_validity(top5, season, season_rows, mode):
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
    return (num / den if den else 0.0), num, den


def hard_violation(top5, season, drought, flood, hard_rows, mode):
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


def main() -> None:
    c3_preds = {}
    season_of = {}
    c3_by_season = defaultdict(list)
    for path in DET.glob("*.json"):
        res = json.loads(path.read_text(encoding="utf-8"))
        ab = (res.get("ablations") or {}).get("full_repo")
        if not ab or ab.get("error") or not ab.get("top5"):
            continue
        sid = path.stem
        c3_preds[sid] = ab["top5"]
        season_of[sid] = res.get("season", "")
        c3_by_season[res.get("season", "")].append(ab["top5"])

    lines = [f"C3 scenarios: {len(c3_preds)}",
             "Season-validity under ground-truth v1.1 vs v1.2 (contradicted = invalid).", ""]
    summary = {}
    for tag, (sn, hn) in TABLE_PAIRS.items():
        season_rows = read_table(sn)
        hard_rows = read_table(hn)
        for mode in ("strict", "lenient"):
            sv, st_v, nm_v = [], [], []
            hv = ht = 0
            for sid, top5 in c3_preds.items():
                season = season_of[sid]
                sv.append(season_validity(top5, season, season_rows, mode)[0])
                (st_v if sid in stress_ids else nm_v).append(
                    season_validity(top5, season, season_rows, mode)[0])
                rf = risk_flags.get(sid, {"drought": False, "flood": False})
                viol, den = hard_violation(top5, season, rf["drought"], rf["flood"],
                                           hard_rows, mode)
                hv += viol
                ht += den
            per = {s: float(np.mean([season_validity(p, s, season_rows, mode)[0]
                                     for p in c3_by_season.get(s, [])]))
                   if c3_by_season.get(s) else 0.0 for s in ["Kharif", "Rabi", "Zaid"]}
            summary[f"{tag}|{mode}"] = {
                "overall": float(np.mean(sv)),
                "stress": float(np.mean(st_v)) if st_v else 0.0,
                "normal": float(np.mean(nm_v)) if nm_v else 0.0,
                "per_season": per,
                "hard_violating": hv,
                "hard_evaluated": ht,
                "hard_violation_rate": float(hv / ht) if ht else None,
            }

    lines.append(f"{'table|mode':14s} {'overall':>9s} {'stress':>9s} {'normal':>9s} "
                 f"{'Kharif':>9s} {'Rabi':>9s} {'Zaid':>9s} {'hardrate':>9s}")
    for key in ["v1.1|strict", "v1.2|strict", "v1.1|lenient", "v1.2|lenient"]:
        d = summary[key]
        p = d["per_season"]
        lines.append(f"{key:14s} {d['overall']:9.5f} {d['stress']:9.5f} {d['normal']:9.5f} "
                     f"{p['Kharif']:9.5f} {p['Rabi']:9.5f} {p['Zaid']:9.5f} "
                     f"{(d['hard_violation_rate'] or 0):9.5f}")
    lines.append("")
    for mode in ("strict", "lenient"):
        lines.append(f"DELTA v1.2-v1.1 ({mode}): overall "
                     f"{summary[f'v1.2|{mode}']['overall'] - summary[f'v1.1|{mode}']['overall']:+.5f}; "
                     + " ".join(f"{s} {summary[f'v1.2|{mode}']['per_season'][s] - summary['v1.1|' + mode]['per_season'][s]:+.5f}"
                                for s in ["Kharif", "Rabi", "Zaid"]))

    write_json(ROOT / "eval/results/c3_season_validity_v1.2_vs_v1.1.json",
               {"scenarios": len(c3_preds), "summary": summary,
                "note": "v1.1 tables byte-identical to before; only Jowar/Rabi and "
                        "Arhar/Rabi season rows changed to 'contradicted' in v1.2"})
    (ROOT / "eval/results/c3_season_validity_v1.2_vs_v1.1.txt").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
