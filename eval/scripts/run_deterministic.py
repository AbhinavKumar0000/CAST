"""Deterministic runner: C3 (no-LLM) and ablations on all 10k scenarios.

Re-implements crop scoring with configurable weights for ablation studies.
All free (no LLM API calls).
"""

import json
import sys
import re
import statistics
import csv
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import numpy as np
import pytz
from eval.common import load_config, ensure_dirs, config_dirs, write_json, read_jsonl, ResultMeta
from eval.scenarios import generate
from mcp_server.season_tool import MONTH_TO_SEASON

cfg = load_config()
ensure_dirs(cfg)
dirs = config_dirs(cfg)

scenarios = generate(cfg)
print(f"Running deterministic eval on {len(scenarios)} scenarios...")

# Load crop registry
_CROP_LOG_PATH = Path(__file__).resolve().parent.parent.parent / "crop_log.csv"
CROP_ROWS = []
with _CROP_LOG_PATH.open(encoding="utf-8", newline="") as handle:
    CROP_ROWS = list(csv.DictReader(handle))

IST = pytz.timezone("Asia/Kolkata")
SEASON_MONTHS = {
    "Kharif": [6, 7, 8, 9, 10],
    "Rabi": [11, 12, 1, 2, 3],
    "Zaid": [4, 5],
}
SOIL_KEYWORDS = {
    "black": {"black", "cotton"},
    "alluvial": {"alluvial"},
    "red": {"red"},
    "yellow": {"yellow"},
    "loam": {"loam"},
    "clay": {"clay"},
    "sandy": {"sand", "sandy"},
    "laterite": {"laterite"},
}
RISK_SENSITIVITY_WEIGHTS = {"high": 1.0, "medium": 0.65, "low": 0.35}
RISK_FIELD_ALIASES = {
    "drought": "drought_probability", "flood": "flood_probability",
    "waterlogging": "flood_probability", "heat": "heatwave_probability", "heatwave": "heatwave_probability",
}

def _parse_numeric_range(value: str):
    matches = re.findall(r"\d+(?:\.\d+)?", value or "")
    if not matches: return None
    numbers = [float(match) for match in matches]
    if len(numbers) == 1: return numbers[0], numbers[0]
    return min(numbers[0], numbers[1]), max(numbers[0], numbers[1])

def _score_against_range(value, expected_range):
    if value is None or expected_range is None: return 0.5
    lower, upper = expected_range
    if lower > upper: lower, upper = upper, lower
    if lower <= value <= upper: return 1.0
    span = max(upper - lower, 1.0)
    distance = lower - value if value < lower else value - upper
    return round(max(0.0, 1.0 - (distance / span)), 3)

def _split_seasons(value):
    raw_parts = re.split(r"[\/,]", value or "")
    seasons = [part.strip() for part in raw_parts if part and part.strip()]
    return seasons or ["Annual"]

def _parse_week_tokens(value):
    return [int(token) for token in re.findall(r"\d+", value or "")]

def _parse_sowing_windows(row):
    seasons = _split_seasons(row.get("season_supported", ""))
    starts = _parse_week_tokens(row.get("sowing_start_week", ""))
    ends = _parse_week_tokens(row.get("sowing_end_week", ""))
    if not starts or not ends: return []
    if len(starts) == len(seasons) and len(ends) == len(seasons):
        return [(season, starts[index], ends[index]) for index, season in enumerate(seasons)]
    start = starts[0]; end = ends[0]
    return [(season, start, end) for season in seasons]

def _parse_peak_water_weeks(row):
    return _parse_week_tokens(row.get("peak_water_week", ""))

def _week_distance(current_week, start_week, end_week):
    if start_week <= current_week <= end_week: return 0
    return min(abs(current_week - start_week), abs(current_week - end_week))

def _seasonal_rainfall_estimate(climate, season_name):
    monthly_rainfall = climate.get("monthly_avg_rainfall_mm") or {}
    months = SEASON_MONTHS.get(season_name)
    if not months:
        average = climate.get("avg_rainfall_normal_mm")
        return float(average) * 12 if average is not None else None
    values = []
    for month in months:
        value = monthly_rainfall.get(month) or monthly_rainfall.get(str(month))
        if value is not None: values.append(value)
    if not values:
        average = climate.get("avg_rainfall_normal_mm")
        return float(average) * len(months) if average is not None else None
    return round(sum(float(value) for value in values), 1)

def _current_temperature(weather, climate, current_month):
    if weather.get("avg_temp_c") is not None: return float(weather["avg_temp_c"])
    monthly_temps = climate.get("monthly_avg_temp_c") or {}
    monthly_temp = monthly_temps.get(current_month) or monthly_temps.get(str(current_month))
    if monthly_temp is not None: return float(monthly_temp)
    if climate.get("avg_temp_normal_c") is not None: return float(climate["avg_temp_normal_c"])
    return None

def _extract_soil_categories(text):
    lowered = (text or "").lower()
    categories = set()
    for category, keywords in SOIL_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            categories.add(category)
    return categories

def _score_soil_type_match(crop_soil_text, dominant_soil_text):
    crop_categories = _extract_soil_categories(crop_soil_text)
    soil_categories = _extract_soil_categories(dominant_soil_text)
    if not crop_categories or not soil_categories: return 0.5
    overlap = crop_categories & soil_categories
    if not overlap: return 0.1
    return round(min(1.0, 0.6 + (0.4 * len(overlap) / len(crop_categories))), 3)

def _season_alignment_score(row, current_season, current_week):
    supported_seasons = _split_seasons(row.get("season_supported", ""))
    windows = _parse_sowing_windows(row)
    if "Annual" in supported_seasons:
        if not windows: return 0.6, True
        for _, start_week, end_week in windows:
            if start_week <= current_week <= end_week: return 0.85, True
        return 0.25, False
    if current_season not in supported_seasons: return 0.0, False
    relevant_windows = [window for window in windows if window[0] == current_season]
    if not relevant_windows: return 0.75, True
    for _, start_week, end_week in relevant_windows:
        if start_week <= current_week <= end_week: return 1.0, True
    nearest_distance = min(_week_distance(current_week, start_week, end_week) for _, start_week, end_week in relevant_windows)
    if nearest_distance <= 2: return 0.65, False
    return 0.35, False

def _risk_penalty_score(row, risk, current_week):
    sensitivity_text = row.get("risk_sensitivity") or ""
    peak_weeks = _parse_peak_water_weeks(row)
    peak_multiplier = 1.15 if any(abs(current_week - peak_week) <= 2 for peak_week in peak_weeks) else 1.0
    if not sensitivity_text.strip():
        baseline_penalty = (float(risk.get("drought_probability") or 0) + float(risk.get("flood_probability") or 0) + float(risk.get("heatwave_probability") or 0)) / 3
        return round(max(0.0, 1.0 - (baseline_penalty * 0.3 * peak_multiplier)), 3)
    total_penalty = 0.0
    for part in sensitivity_text.split(","):
        hazard_text, _, level_text = part.partition(":")
        hazard = hazard_text.strip().lower(); level = level_text.strip().lower()
        if not hazard or not level: continue
        risk_field = RISK_FIELD_ALIASES.get(hazard)
        if not risk_field: continue
        probability = float(risk.get(risk_field) or 0.0)
        sensitivity_weight = RISK_SENSITIVITY_WEIGHTS.get(level, 0.5)
        total_penalty += probability * sensitivity_weight * peak_multiplier
    return round(max(0.0, 1.0 - min(total_penalty, 1.0)), 3)

def score_crops(evidence, weights):
    """Score all crops with given weights dict."""
    current_season = evidence["season"].get("current_season", "Unknown")
    now = datetime.now(IST)
    current_week = now.isocalendar().week
    current_month = int(evidence["season"].get("current_month") or now.month)
    dominant_soil = evidence["soil"].get("dominant_soil", "") if isinstance(evidence["soil"], dict) else ""
    
    ranked = []
    for row in CROP_ROWS:
        rainfall_req = _parse_numeric_range(row.get("Rainfall", ""))
        temp_req = _parse_numeric_range(row.get("Tempreture", ""))
        
        rainfall_match = _score_against_range(_seasonal_rainfall_estimate(evidence["climate"], current_season), rainfall_req)
        temperature_match = _score_against_range(_current_temperature(evidence["weather"], evidence["climate"], current_month), temp_req)
        soil_type_match = _score_soil_type_match(row.get("Soil Type", ""), dominant_soil)
        season_alignment, plantable_now = _season_alignment_score(row, current_season, current_week)
        risk_penalty = _risk_penalty_score(row, evidence["risk"], current_week)
        
        total_score = round(
            weights["rainfall"] * rainfall_match +
            weights["temperature"] * temperature_match +
            weights["soil"] * soil_type_match +
            weights["season"] * season_alignment +
            weights["risk"] * risk_penalty, 3
        )
        ranked.append({
            "crop": row.get("Crop", ""),
            "season_supported": row.get("season_supported", ""),
            "plantable_now": plantable_now,
            "total_score": total_score,
            "scores": {
                "rainfall_match": round(rainfall_match, 3),
                "temperature_match": round(temperature_match, 3),
                "soil_type_match": round(soil_type_match, 3),
                "season_alignment": round(season_alignment, 3),
                "risk_penalty": round(risk_penalty, 3),
            },
            "sowing_window": {"start_week": row.get("sowing_start_week", ""), "end_week": row.get("sowing_end_week", "")},
            "days_to_harvest": row.get("days_to_harvest", ""),
            "peak_water_week": row.get("peak_water_week", ""),
        })
    ranked.sort(key=lambda x: (-x["total_score"], x["crop"]))
    return ranked[:6]

# Ablation configs
repo_weights = cfg['ablations']['weights']['repo']
equal_weights = cfg['ablations']['weights']['equal']
sens = cfg['ablations']['weights']['sensitivity_pct']

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
    for direction, mult in [("plus", 1+sens), ("minus", 1-sens)]:
        w = repo_weights.copy(); w[dim] = base_w * mult
        total = sum(w.values()); w = {k: v/total for k, v in w.items()}
        ablation_configs[f"sens_{dim}_{direction}"] = {"tools": ["weather", "climate", "soil", "risk", "season"], "weights": w}

print(f"Running {len(ablation_configs)} ablation configs...")

evidence_dir = dirs['runs_dir'] / 'adhoc' / 'evidence'
results_dir = dirs['runs_dir'] / 'adhoc' / 'deterministic'
results_dir.mkdir(parents=True, exist_ok=True)

for i, sc in enumerate(scenarios):
    if i % 1000 == 0:
        print(f"  {i}/{len(scenarios)}")
    sid = sc['scenario_id']
    evidence_path = evidence_dir / f"{sid}.json"
    if not evidence_path.exists(): continue
    
    with evidence_path.open() as f:
        bundle = json.load(f)
    
    scenario_results = {"scenario_id": sid, "district": sc['district'], "season": bundle['season'].get('current_season'), "ablations": {}}
    
    for ab_name, ab_cfg in ablation_configs.items():
        # Build evidence with available tools
        evidence = {}
        for tool in ["weather", "climate", "soil", "risk", "season"]:
            if tool in ab_cfg["tools"]:
                evidence[tool] = bundle[tool]
            else:
                # Provide minimal dummy evidence so scoring doesn't crash
                if tool == "weather": evidence[tool] = {"avg_temp_c": None}
                elif tool == "climate": evidence[tool] = {"monthly_avg_rainfall_mm": {}, "avg_rainfall_normal_mm": None, "monthly_avg_temp_c": {}, "avg_temp_normal_c": None}
                elif tool == "soil": evidence[tool] = {"dominant_soil": ""}
                elif tool == "risk": evidence[tool] = {"drought_probability": 0.08, "flood_probability": 0.08, "heatwave_probability": 0.08}
                elif tool == "season": evidence[tool] = {"current_season": bundle['season'].get('current_season', 'Kharif'), "current_month": bundle['season'].get('current_month', 6)}
        
        try:
            top_crops = score_crops(evidence, ab_cfg["weights"])
            scenario_results["ablations"][ab_name] = {
                "top5": [c["crop"] for c in top_crops[:5]],
                "top6": [c["crop"] for c in top_crops],
                "scores": {c["crop"]: c["total_score"] for c in top_crops},
            }
        except Exception as e:
            scenario_results["ablations"][ab_name] = {"error": str(e)}
    
    write_json(results_dir / f"{sid}.json", scenario_results)

print("Done!")
meta = ResultMeta.build(cfg, "deterministic_crop_score")
write_json(dirs['results_dir'] / "deterministic_meta.json", meta.as_dict())