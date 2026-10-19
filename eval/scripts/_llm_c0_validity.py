"""Phase 8 ITEM 1 (supplement): LLM C0/C0b season-validity + hard-violation under
v1 vs v1.1 cited tables, STRICT vs LENIENT, from archived v1 LLM records (no API).
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
GT = ROOT / "eval/data/ground_truth"


def read_table(name: str) -> list[dict[str, str]]:
    with (GT / name).open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def season_status(crop: str, season: str, season_rows: list[dict[str, str]]) -> str:
    rows_here = [r for r in season_rows if r["crop"] == crop and r["season"] == season]
    cited = [r for r in rows_here if r["status"] == "cited"]
    if cited:
        return "valid"
    if rows_here:
        return "unknown"
    in_table = any(r["crop"] == crop for r in season_rows)
    if not in_table:
        return "unknown"
    return "invalid"


def season_validity(top5: list[str], season: str, season_rows: list[dict[str, str]],
                    mode: str) -> tuple[float, int, int]:
    num = den = 0
    for p in top5:
        st = season_status(p, season, season_rows)
        if st == "valid":
            num += 1
            den += 1
        elif st == "invalid":
            den += 1
        else:
            if mode == "strict":
                den += 1
    return (num / den if den else 0.0), num, den


def hard_violation(top5: list[str], season: str, drought: bool, flood: bool,
                   hard_rows: list[dict[str, str]], mode: str) -> tuple[int, int]:
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


RUNS = {
    "nemotron-3-ultra": [
        Path("eval/runs/full_nemotron-3-ultra_20261011_074835/results.json"),
        Path("eval/runs/full_nemotron-3-ultra_20261011_082444/results.json"),
    ],
    "llama-3.2-11b": [Path("eval/runs/eval_llama-3.2-11b/results.json")],
}
subsets = [json.loads(l) for l in Path("eval/data/llm_subset.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
season_by_sid = {s["scenario_id"]: s["season_by_month"] for s in subsets}

records = {}
for model, paths in RUNS.items():
    for p in paths:
        data = json.loads(p.read_text(encoding="utf-8"))
        items = data if isinstance(data, list) else data.get("results") or data.get("records") or []
        for r in items:
            if r.get("condition") in ("C0", "C0b") and r.get("repeat", 0) == 0:
                key = (model, r["condition"], r["scenario_id"])
                if not r.get("error"):
                    records.setdefault(key, r)

TABLES = {"v1": ("crop_season_table.csv", "hard_constraints.csv"),
          "v1.1": ("crop_season_table_v1.1.csv", "hard_constraints_v1.1.csv")}

print(f"{'table':5s} {'mode':8s} {'model':16s} cond  n   svalid_top5  hard_viol  den")
per = {}
for tag, (sf, hf) in TABLES.items():
    srows = read_table(sf)
    hrows = read_table(hf)
    for mode in ("strict", "lenient"):
        for cond in ("C0", "C0b"):
            for model in ("nemotron-3-ultra", "llama-3.2-11b"):
                n = sv_num = sv_den = h_num = h_den = 0
                for (m, c, sid), r in records.items():
                    if m != model or c != cond or sid not in season_by_sid:
                        continue
                    p = r.get("parsed") or {}
                    if not p.get("valid_json"):
                        continue
                    top5 = p.get("top5") or []
                    if not isinstance(top5, list) or not top5:
                        continue
                    season = season_by_sid[sid]
                    d = f = False
                    n += 1
                    v, num, den = season_validity(top5, season, srows, mode)
                    h, hd = hard_violation(top5, season, d, f, hrows, mode)
                    sv_num += num; sv_den += den; h_num += h; h_den += hd
                rate = sv_num / sv_den if sv_den else float("nan")
                hrate = h_num / h_den if h_den else float("nan")
                print(f"{tag:5s} {mode:8s} {model:16s} {cond}  {n:3d}  {rate:.4f} ({sv_num}/{sv_den})  "
                      f"{h_num:3d}/{h_den:3d} = {hrate:.4f}")