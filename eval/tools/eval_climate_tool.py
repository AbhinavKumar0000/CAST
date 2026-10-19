"""Evaluation-specific climate tool using pre-cached weather data.

Replaces mcp_server.climate_tool for evaluation runs to avoid Open-Meteo rate limits.
"""

import copy
import json
import logging
import statistics
import time
from pathlib import Path
from typing import Any

from eval.common import config_dirs, load_config

logger = logging.getLogger(__name__)

NORMALS_START = "2014-01-01"
NORMALS_END = "2023-12-31"

# In-memory cache
_CLIMATE_CACHE: dict[tuple[float, float], tuple[float, dict[str, Any]]] = {}


def _cache_key(latitude: float, longitude: float) -> tuple[float, float]:
    return (round(latitude, 1), round(longitude, 1))


def _load_weather_cache(lat: float, lon: float) -> dict[str, Any] | None:
    """Load pre-cached weather data for a coordinate."""
    cfg = load_config()
    dirs = config_dirs(cfg)
    cache_dir = Path(dirs["cache_dir"]) / "weather"
    
    # Find nearest cached district
    from eval.weather_cache import district_points
    points = district_points()
    
    best_district = None
    best_dist = float('inf')
    for district, pt in points.items():
        d = ((pt["lat"] - lat) ** 2 + (pt["lon"] - lon) ** 2) ** 0.5
        if d < best_dist:
            best_dist = d
            best_district = district
    
    if best_district is None:
        return None
    
    safe = "".join(ch if ch.isalnum() else "_" for ch in best_district.lower())
    cache_path = Path("eval/cache/weather") / f"{safe}.json"
    
    if not cache_path.exists():
        return None
    
    with cache_path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _filter_to_normals_period(daily: dict[str, list[Any]]) -> dict[str, list[Any]]:
    """Filter daily data to 2014-2023 normals period."""
    times = daily.get("time") or []
    tmean = daily.get("temperature_2m_mean") or []
    tmax = daily.get("temperature_2m_max") or []
    tmin = daily.get("temperature_2m_min") or []
    precip = daily.get("precipitation_sum") or []
    
    out_times = []
    out_tmean = []
    out_tmax = []
    out_tmin = []
    out_precip = []
    
    for i, t in enumerate(times):
        date_str = str(t).split("T")[0]
        if "2014-01-01" <= date_str <= "2023-12-31":
            out_times.append(t)
            out_tmean.append(tmean[i] if i < len(tmean) else None)
            out_tmax.append(tmax[i] if i < len(tmax) else None)
            out_tmin.append(tmin[i] if i < len(tmin) else None)
            out_precip.append(precip[i] if i < len(precip) else None)
    
    return {
        "time": out_times,
        "temperature_2m_mean": out_tmean,
        "temperature_2m_max": out_tmax,
        "temperature_2m_min": out_tmin,
        "precipitation_sum": out_precip,
    }


def run(latitude: float, longitude: float) -> dict[str, Any]:
    """Fetch long-term climate normals using pre-cached weather data."""
    logger.info("eval_climate_tool.run(lat=%s, lon=%s)", latitude, longitude)
    key = (round(latitude, 1), round(longitude, 1))
    
    # Check in-memory cache
    cached = _CLIMATE_CACHE.get(key)
    if cached:
        cached_at, payload = cached
        if (time.time() - cached_at) < 7 * 24 * 3600:
            logger.debug("eval_climate_tool cache hit for %s", key)
            return copy.deepcopy(payload)
    
    # Load from pre-cached weather data
    daily = _load_weather_cache(latitude, longitude)
    if daily is None:
        logger.warning("No cached weather data for lat=%s, lon=%s", latitude, longitude)
        return {
            "tool": "climate_normals",
            "avg_rainfall_normal_mm": None,
            "avg_temp_normal_c": None,
            "error": "No cached weather data available",
        }
    
    # Filter to normals period (2014-2023)
    daily = _filter_to_normals_period(daily)
    
    temps_raw = daily.get("temperature_2m_mean") or []
    precipitation_raw = daily.get("precipitation_sum") or []
    times = daily.get("time") or []
    
    temps = [v for v in temps_raw if v is not None]
    precipitation = [v for v in precipitation_raw if v is not None]
    
    avg_temp = sum(temps) / len(temps) if temps else None
    total_precipitation = sum(precipitation)
    n_days = len(precipitation)
    n_months = n_days / 30.44 if n_days else 0
    avg_rainfall_per_month = total_precipitation / n_months if n_months > 0 else None
    
    monthly_temp: dict[int, list[float]] = {month: [] for month in range(1, 13)}
    monthly_precip: dict[int, list[float]] = {month: [] for month in range(1, 13)}
    
    for index, timestamp in enumerate(times):
        try:
            date_text = str(timestamp).split("T")[0]
            _, month_text, _ = date_text.split("-")
            month = int(month_text)
        except ValueError:
            continue
        if not 1 <= month <= 12:
            continue
        if index < len(temps_raw) and temps_raw[index] is not None:
            monthly_temp[month].append(temps_raw[index])
        if index < len(precipitation_raw) and precipitation_raw[index] is not None:
            monthly_precip[month].append(precipitation_raw[index])
    
    monthly_avg_temp = {
        month: round(statistics.mean(values), 1) if values else None
        for month, values in monthly_temp.items()
    }
    monthly_avg_precip = {}
    for month, values in monthly_precip.items():
        if values:
            monthly_avg_precip[month] = round(statistics.mean(values) * 30.44, 1)
        else:
            monthly_avg_precip[month] = None
    
    result = {
        "tool": "climate_normals",
        "avg_rainfall_normal_mm": round(avg_rainfall_per_month, 1) if avg_rainfall_per_month is not None else None,
        "avg_temp_normal_c": round(avg_temp, 1) if avg_temp is not None else None,
        "temp_std_dev_c": round(statistics.stdev(temps), 1) if len(temps) > 1 else None,
        "precipitation_std_dev_mm": round(statistics.stdev(precipitation), 1) if len(precipitation) > 1 else None,
        "monthly_avg_temp_c": monthly_avg_temp,
        "monthly_avg_rainfall_mm": monthly_avg_precip,
        "data_period_years": "2014-2023",
    }
    
    _CLIMATE_CACHE[key] = (time.time(), copy.deepcopy(result))
    logger.debug("eval_climate_tool computed from cache for %s", key)
    return result


# Import at bottom to avoid circular
import importlib
time = importlib.import_module("time")
copy = importlib.import_module("copy")