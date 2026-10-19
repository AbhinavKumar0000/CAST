"""Phase 8: C3 + tool ablations + weight sensitivity under the v2 runtime.

Reads the v2 time-anchored evidence bundles (eval/runs/archive_v2/evidence) and the
real crop registry, and recomputes the full deterministic grid with the scorer
TIME-ANCHORED: current_week = iso week of the scenario's as_of_date (not the live
datetime), matching the frozen-clock crop_score_tool in the v2 runtime.

Outputs are written to eval/runs/archive_v2/deterministic/<sid>.json (v1 files under
eval/runs/adhoc/deterministic are NOT touched). A drift summary vs the v1 outputs is
printed at the end.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from eval.common import config_dirs, load_config, write_json  # noqa: E402
from eval.scenarios import generate  # noqa: E402

cfg = load_config()
dirs = config_dirs(cfg)

CROP_ROWS = []
with Path("crop_log.csv").open(encoding="utf-8", newline="") as handle:
    CROP_ROWS = list(csv.DictReader(handle))

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
    monthly_temp = monthly_temps.get(current_month) or monthly_temps.get(str(current_month))
    if monthly_temp is not None:
        return float(monthly_temp)
    if climate.get("avg_temp_normal_c") is not None:
        return float(climate["avg_temp_normal_c"])
    return None


def _extract_soil_categories(text):
    lowered = (text or "").lower()
    return {cat for cat, kws in SOIL_KEYWORDS.items() if any(kw in lowered for kw in kws)}


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


CROP_PARSED = []
for row in CROP_ROWS:
    CROP_PARSED.append({
        "crop": row.get("Crop", ""),
        "rainfall_req": _parse_numeric_range(row.get("Rainfall", "")),
        "temp_req": _parse_numeric_range(row.get("Tempreture", "")),
        "soil_text": row.get("Soil Type", ""),
        "seasons": _split_seasons(row.get("season_supported", "")),
        "windows": _parse_sowing_windows(row),
        "peak_weeks": _parse_peak_water_weeks(row),
        "risk_sens": row.get("risk_sensitivity") or "",
    })


def score_crops(evidence, weights, current_week):
    current_season = evidence["season"].get("current_season", "Unknown")
    current_month = int(evidence["season"].get("current_month") or 1)
    dominant_soil = evidence["soil"].get("dominant_soil", "") if isinstance(evidence["soil"], dict) else ""
    rain_est = _seasonal_rainfall_estimate(evidence["climate"], current_season)
    temp_est = _current_temperature(evidence["weather"], evidence["climate"], current_month)
    soil_match_cache = {cp["crop"]: _score_soil_type_match(cp["soil_text"], dominant_soil) for cp in CROP_PARSED}
    ranked = []
    for cp in CROP_PARSED:
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
        ranked.append((cp["crop"], round(total, 3), plantable_now))
    ranked.sort(key=lambda x: (-x[1], x[0]))
    return [{"crop": c, "total_score": s, "plantable_now": p} for c, s, p in ranked[:6]]


repo_weights = cfg["ablations"]["weights"]["repo"]
equal_weights = cfg["ablations"]["weights"]["equal"]
sens = cfg["ablations"]["weights"]["sensitivity_pct"]

ablation_configs = {
    "full_repo": {"tools": ["weather", "climate", "soil", "risk", "season"], "weights": repo_weights},
    "full_equal": {"tools": ["weather", "climate", "soil", "risk", "season"], "weights": equal_weights},
    "no_weather": {"tools": ["climate", "soil", "risk", "season"], "weights": repo_weights},
    "no_climate": {"tools": ["weather", "soil", "risk", "season"], "weights": repo_weights},
    "no_soil": {"tools": ["weather", "climate", "risk", "season"], "weights": repo_weights},
    "no_risk": {"tools": ["weather", "climate", "soil", "season"], "weights": repo_weights},
    "no_season": {"tools": ["weather", "climate", "soil", "risk"], "weights": repo_weights},
}
for dim, base_w in repo_weights.items():
    for direction, mult in [("plus", 1 + sens), ("minus", 1 - sens)]:
        w = repo_weights.copy()
        w[dim] = base_w * mult
        total = sum(w.values())
        w = {k: v / total for k, v in w.items()}
        ablation_configs[f"sens_{dim}_{direction}"] = {"tools": ["weather", "climate", "soil", "risk", "season"], "weights": w}

EVIDENCE_DIR = Path("eval/runs/archive_v2/evidence")
RESULTS_DIR = Path("eval/runs/archive_v2/deterministic")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

scenarios = generate(cfg)
n_done = 0

# v1 deterministic outputs for drift comparison
v1_dir = Path("eval/runs/adhoc/deterministic")
v1_top5 = {}
if v1_dir.exists():
    for p in v1_dir.glob("*.json"):
        try:
            v1_top5[p.stem] = json.loads(p.read_text(encoding="utf-8"))["ablations"]["full_repo"]["top5"]
        except Exception:
            pass

for i, sc in enumerate(scenarios):
    if i % 1000 == 0:
        print(f"  {i}/{len(scenarios)}")
    sid = sc["scenario_id"]
    evidence_path = EVIDENCE_DIR / f"{sid}.json"
    if not evidence_path.exists():
        continue
    bundle = json.loads(evidence_path.read_text(encoding="utf-8"))

    # TIME-ANCHOR: week from as_of_date (frozen clock semantics), not live datetime.
    as_of = bundle.get("as_of_date") or sc["as_of_date"]
    current_week = datetime.strptime(as_of, "%Y-%m-%d").date().isocalendar().week
    scenario_results = {
        "scenario_id": sid, "district": sc["district"],
        "season": bundle["season"].get("current_season"),
        "as_of_date": as_of, "week": current_week, "ablations": {},
    }
    for ab_name, ab_cfg in ablation_configs.items():
        evidence = {}
        for tool in ["weather", "climate", "soil", "risk", "season"]:
            if tool in ab_cfg["tools"]:
                evidence[tool] = bundle[tool]
            else:
                if tool == "weather":
                    evidence[tool] = {"avg_temp_c": None}
                elif tool == "climate":
                    evidence[tool] = {"monthly_avg_rainfall_mm": {}, "avg_rainfall_normal_mm": None,
                                      "monthly_avg_temp_c": {}, "avg_temp_normal_c": None}
                elif tool == "soil":
                    evidence[tool] = {"dominant_soil": ""}
                elif tool == "risk":
                    evidence[tool] = {"drought_probability": 0.08, "flood_probability": 0.08,
                                      "heatwave_probability": 0.08}
                elif tool == "season":
                    evidence[tool] = {"current_season": bundle["season"].get("current_season", "Kharif"),
                                      "current_month": bundle["season"].get("current_month", 6)}
        try:
            top_crops = score_crops(evidence, ab_cfg["weights"], current_week)
            scenario_results["ablations"][ab_name] = {
                "top5": [c["crop"] for c in top_crops[:5]],
                "top6": [c["crop"] for c in top_crops],
                "scores": {c["crop"]: c["total_score"] for c in top_crops},
            }
        except Exception as exc:  # noqa: BLE001
            scenario_results["ablations"][ab_name] = {"error": str(exc)}
    write_json(RESULTS_DIR / f"{sid}.json", scenario_results)
    n_done += 1

# Drift vs v1 C3 (full_repo top5)
changed = 0
common = 0
for p in RESULTS_DIR.glob("*.json"):
    try:
        r = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        continue
    if "full_repo" not in r["ablations"]:
        continue
    t5 = r["ablations"]["full_repo"]["top5"]
    if p.stem in v1_top5:
        common += 1
        if t5 != v1_top5[p.stem]:
            changed += 1

print(f"\nDone: {n_done} scenarios -> {RESULTS_DIR}")
print(f"C3 (full_repo) top-5 drift v1->v2: {changed}/{common} scenarios changed")
print("meta: week anchored to as_of_date (frozen clock); weights from config "
      f"repo={repo_weights} sens={sens}")
meta = {
    "phase": 8, "evidence_version": 2, "v2_out": f"{RESULTS_DIR}",
    "week_anchored_to": "as_of_date",
    "c3_top5_drift_vs_v1": {"changed": changed, "common": common},
    "config_shasum_note": "config.yaml modified in Phase 8 STEP A (max_tool_rounds)",
}
write_json(Path("eval/runs/archive_v2/deterministic_meta.json"), meta)
print("meta -> eval/runs/archive_v2/deterministic_meta.json")