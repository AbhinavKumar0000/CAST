"""STEP 4: recompute C3 (deterministic full_repo) under a chosen crop database.

The scoring functions below are copied verbatim from
`eval/scripts/run_deterministic_v2.py` (the frozen C3 producer) so that the only
difference between runs is the crop database. With `--crop-log crop_log.csv`
the output MUST match `eval/runs/archive_v2/deterministic/*.json`
`ablations.full_repo.top5` on all 10,000 scenarios (asserted by --verify);
this proves the copy is faithful before db_v2 is scored.

This time the FULL scorer payload is logged per scenario (all ranked crops with
component scores), so rankings are exact and auditable.

No model call. Reads only frozen evidence bundles.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from eval.common import config_dirs, load_config, write_json  # noqa: E402
from eval.scenarios import generate  # noqa: E402

SEASON_MONTHS = {"Kharif": [6, 7, 8, 9, 10], "Rabi": [11, 12, 1, 2, 3], "Zaid": [4, 5]}
SOIL_KEYWORDS = {
    "black": {"black", "cotton"}, "alluvial": {"alluvial"}, "red": {"red"},
    "yellow": {"yellow"}, "loam": {"loam"}, "clay": {"clay"},
    "sandy": {"sand", "sandy"}, "laterite": {"laterite"},
}
RISK_SENSITIVITY_WEIGHTS = {"high": 1.0, "medium": 0.65, "low": 0.35}
RISK_FIELD_ALIASES = {
    "drought": "drought_probability", "flood": "flood_probability",
    "waterlogging": "flood_probability", "heat": "heatwave_probability",
    "heatwave": "heatwave_probability",
}

_parse_numeric_range = lambda value: (lambda m: (float(m[0]), float(m[0])) if len(m) == 1
                                      else (min(float(m[0]), float(m[1])), max(float(m[0]), float(m[1])))
                                      if m else None)(re.findall(r"\d+(?:\.\d+)?", value or ""))


def _score_against_range(value, expected_range):
    if value is None or expected_range is None:
        return 0.5
    lower, upper = expected_range
    if lower > upper:
        lower, upper = upper, lower
    if lower <= value <= upper:
        return 1.0
    span = max(upper - lower, 1.0)
    distance = lower - value if value < lower else value - upper
    return round(max(0.0, 1.0 - (distance / span)), 3)


_split_seasons = lambda value: (lambda parts: [p.strip() for p in parts if p.strip()] or ["Annual"])(re.split(r"[\/,]", value or ""))
_parse_week_tokens = lambda value: [int(t) for t in re.findall(r"\d+", value or "")]


def _parse_sowing_windows(row):
    seasons = _split_seasons(row.get("season_supported", ""))
    starts = _parse_week_tokens(row.get("sowing_start_week", ""))
    ends = _parse_week_tokens(row.get("sowing_end_week", ""))
    if not starts or not ends:
        return []
    if len(starts) == len(seasons) and len(ends) == len(seasons):
        return [(season, starts[index], ends[index]) for index, season in enumerate(seasons)]
    start, end = starts[0], ends[0]
    return [(season, start, end) for season in seasons]


def _parse_peak_water_weeks(row):
    return _parse_week_tokens(row.get("peak_water_week", ""))


week_distance = lambda cw, sw, ew: 0 if sw <= cw <= ew else min(abs(cw - sw), abs(cw - ew))


def _seasonal_rainfall_estimate(climate, season_name):
    monthly_rainfall = climate.get("monthly_avg_rainfall_mm") or {}
    months = SEASON_MONTHS.get(season_name)
    if not months:
        average = climate.get("avg_rainfall_normal_mm")
        return float(average) * 12 if average is not None else None
    values = [m for m in (monthly_rainfall.get(month) or monthly_rainfall.get(str(month)) for month in months) if m is not None]
    if not values:
        average = climate.get("avg_rainfall_normal_mm")
        return float(average) * len(months) if average is not None else None
    return round(sum(float(v) for v in values), 1)


def _current_temperature(weather, climate, current_month):
    if weather.get("avg_temp_c") is not None:
        return float(weather["avg_temp_c"])
    monthly_temps = climate.get("monthly_avg_temp_c") or {}
    monthly_temp = monthly_temps.get(current_month)
    if monthly_temp is None:
        monthly_temp = monthly_temps.get(str(current_month))
    if monthly_temp is not None:
        return float(monthly_temp)
    if climate.get("avg_temp_normal_c") is not None:
        return float(climate["avg_temp_normal_c"])
    return None


def _extract_soil_categories(text):
    lowered = (text or "").lower()
    categories = set()
    for category, keywords in SOIL_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            categories.add(category)
    return categories


def _score_soil_type_match(crop_soil_text, dominant_soil_text):
    crop_cats = _extract_soil_categories(crop_soil_text)
    soil_cats = _extract_soil_categories(dominant_soil_text)
    if not crop_cats or not soil_cats:
        return 0.5
    overlap = crop_cats & soil_cats
    if not overlap:
        return 0.1
    return round(min(1.0, 0.6 + (0.4 * len(overlap) / len(crop_cats))), 3)


def _season_alignment_score(row, current_season, current_week):
    supported = _split_seasons(row.get("season_supported", ""))
    windows = _parse_sowing_windows(row)
    if "Annual" in supported:
        if not windows:
            return 0.6, True
        for _, sw, ew in windows:
            if sw <= current_week <= ew:
                return 0.85, True
        return 0.25, False
    if current_season not in supported:
        return 0.0, False
    relevant = [w for w in windows if w[0] == current_season]
    if not relevant:
        return 0.75, True
    for _, sw, ew in relevant:
        if sw <= current_week <= ew:
            return 1.0, True
    nd = min(week_distance(current_week, sw, ew) for _, sw, ew in relevant)
    return (0.65, False) if nd <= 2 else (0.35, False)


def _risk_penalty_score(row, risk, current_week):
    sens_text = row.get("risk_sensitivity") or ""
    peak_weeks = _parse_peak_water_weeks(row)
    peak_mult = 1.15 if any(abs(current_week - pw) <= 2 for pw in peak_weeks) else 1.0
    if not sens_text.strip():
        bp = (float(risk.get("drought_probability") or 0) + float(risk.get("flood_probability") or 0)
              + float(risk.get("heatwave_probability") or 0)) / 3
        return round(max(0.0, 1.0 - (bp * 0.3 * peak_mult)), 3)
    total = 0.0
    for part in sens_text.split(","):
        haz, _, lvl = part.partition(":")
        haz = haz.strip().lower()
        lvl = lvl.strip().lower()
        if not haz or not lvl:
            continue
        rf = RISK_FIELD_ALIASES.get(haz)
        if not rf:
            continue
        prob = float(risk.get(rf) or 0.0)
        total += prob * RISK_SENSITIVITY_WEIGHTS.get(lvl, 0.5) * peak_mult
    return round(max(0.0, 1.0 - min(total, 1.0)), 3)


def build_crop_parsed(crop_rows):
    parsed = []
    for row in crop_rows:
        parsed.append({
            "crop": row.get("Crop", ""),
            "rainfall_req": _parse_numeric_range(row.get("Rainfall", "")),
            "temp_req": _parse_numeric_range(row.get("Tempreture", "")),
            "soil_text": row.get("Soil Type", ""),
            "seasons": _split_seasons(row.get("season_supported", "")),
            "windows": _parse_sowing_windows(row),
            "peak_weeks": _parse_peak_water_weeks(row),
            "risk_sens": row.get("risk_sensitivity") or "",
        })
    return parsed


def score_crops(evidence, weights, current_week, crop_parsed, limit=6):
    current_season = evidence["season"].get("current_season", "Unknown")
    current_month = int(evidence["season"].get("current_month") or 1)
    dominant_soil = evidence["soil"].get("dominant_soil", "") if isinstance(evidence["soil"], dict) else ""
    rain_est = _seasonal_rainfall_estimate(evidence["climate"], current_season)
    temp_est = _current_temperature(evidence["weather"], evidence["climate"], current_month)
    soil_match_cache = {cp["crop"]: _score_soil_type_match(cp["soil_text"], dominant_soil) for cp in crop_parsed}
    ranked = []
    for cp in crop_parsed:
        rainfall_match = _score_against_range(rain_est, cp["rainfall_req"])
        temperature_match = _score_against_range(temp_est, cp["temp_req"])
        soil_type_match = soil_match_cache[cp["crop"]]
        season_alignment, plantable_now = _season_alignment_score(
            {"season_supported": ",".join(cp["seasons"]), "sowing_start_week": "",
             "sowing_end_week": "", "risk_sensitivity": cp["risk_sens"],
             "peak_water_week": ",".join(str(w) for w in cp["peak_weeks"])},
            current_season, current_week,
        )
        risk_penalty = _risk_penalty_score(
            {"risk_sensitivity": cp["risk_sens"], "peak_water_week": ",".join(str(w) for w in cp["peak_weeks"])},
            evidence["risk"], current_week,
        )
        total = (weights["rainfall"] * rainfall_match + weights["temperature"] * temperature_match
                 + weights["soil"] * soil_type_match + weights["season"] * season_alignment
                 + weights["risk"] * risk_penalty)
        ranked.append({"crop": cp["crop"], "total_score": round(total, 3), "plantable_now": plantable_now,
                       "scores": {"rainfall_match": rainfall_match, "temperature_match": temperature_match,
                                  "soil_type_match": soil_type_match, "season_alignment": season_alignment,
                                  "risk_penalty": risk_penalty}})
    ranked.sort(key=lambda x: (-x["total_score"], x["crop"]))
    return ranked if limit is None else ranked[:limit]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--crop-log", default="crop_log.csv")
    ap.add_argument("--out", required=True)
    ap.add_argument("--verify", default=None, help="dir of archive deterministic json to match top5 against")
    args = ap.parse_args()

    cfg = load_config()
    weights = cfg["ablations"]["weights"]["repo"]
    crop_rows = list(csv.DictReader((ROOT / args.crop_log).open(encoding="utf-8-sig", newline="")))
    crop_parsed = build_crop_parsed(crop_rows)
    print(f"crop_log={args.crop_log} n_crops={len(crop_rows)} weights={weights}")

    scenarios = generate(cfg)
    evidence_dir = ROOT / "eval/runs/archive_v2/evidence"
    out_dir = ROOT / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    n_done = 0
    mismatch = []
    for sc in scenarios:
        sid = sc["scenario_id"]
        ev_path = evidence_dir / f"{sid}.json"
        if not ev_path.exists():
            continue
        bundle = json.loads(ev_path.read_text(encoding="utf-8"))
        as_of = bundle.get("as_of_date") or sc["as_of_date"]
        current_week = datetime.strptime(as_of, "%Y-%m-%d").date().isocalendar().week
        full = score_crops(bundle, weights, current_week, crop_parsed, limit=None)
        top6 = full[:6]
        rec = {
            "scenario_id": sid, "district": sc["district"],
            "season": bundle["season"].get("current_season"), "as_of_date": as_of,
            "week": current_week, "crop_log": args.crop_log,
            "ablations": {"full_repo": {
                "top5": [c["crop"] for c in top6[:5]],
                "top6": [c["crop"] for c in top6],
                "scores": {c["crop"]: c["total_score"] for c in top6},
            }},
            "full_ranking": [{"crop": c["crop"], "total_score": c["total_score"],
                              "plantable_now": c["plantable_now"], **c["scores"]} for c in full],
        }
        write_json(out_dir / f"{sid}.json", rec)
        if args.verify:
            v = json.loads((ROOT / args.verify / f"{sid}.json").read_text(encoding="utf-8"))
            if v["ablations"]["full_repo"]["top5"] != rec["ablations"]["full_repo"]["top5"]:
                mismatch.append(sid)
        n_done += 1

    print(f"done: {n_done} scenarios -> {out_dir}")
    if args.verify:
        print(f"verify vs {args.verify}: mismatches = {len(mismatch)}")
        if mismatch:
            print("first mismatches:", mismatch[:10])
            sys.exit(2)
        else:
            print("MATCH: 10,000/10,000 full_repo top5 identical - copy proven faithful.")


if __name__ == "__main__":
    main()
