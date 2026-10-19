"""Evaluation-specific risk tool using pre-cached weather data.

Replaces mcp_server.risk_tool for evaluation runs to avoid Open-Meteo rate limits.
"""

import logging
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

from scipy.stats import gamma, norm

from eval.common import config_dirs, load_config

logger = logging.getLogger(__name__)

SPI_TO_DROUGHT_PROBABILITY = [
    (-2.0, 0.70),
    (-1.5, 0.55),
    (-1.0, 0.22),
]

HEATWAVE_DAYS_35C = 3
HEATWAVE_DAYS_38C = 2
FLOOD_7D_MM = [(200, 0.50), (150, 0.38), (100, 0.28), (50, 0.15), (20, 0.08)]
FLOOD_1DAY_MM = [(80, 0.35), (50, 0.22), (30, 0.12)]


def _load_weather_cache(lat: float, lon: float) -> dict[str, Any] | None:
    """Load pre-cached weather data for a coordinate."""
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
    
    import json
    with cache_path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _filter_date_range(daily: dict[str, list[Any]], start: str, end: str) -> dict[str, list[Any]]:
    """Filter daily data to a date range."""
    times = daily.get("time") or []
    tmax = daily.get("temperature_2m_max") or []
    tmin = daily.get("temperature_2m_min") or []
    precip = daily.get("precipitation_sum") or []
    precip_prob = daily.get("precipitation_probability_max") or []
    
    out = {"time": [], "temperature_2m_max": [], "temperature_2m_min": [], 
           "precipitation_sum": [], "precipitation_probability_max": []}
    
    for i, t in enumerate(times):
        date_str = str(t).split("T")[0]
        if start <= date_str <= end:
            out["time"].append(t)
            out["temperature_2m_max"].append(tmax[i] if i < len(tmax) else None)
            out["temperature_2m_min"].append(tmin[i] if i < len(tmin) else None)
            out["precipitation_sum"].append(precip[i] if i < len(precip) else None)
            out["precipitation_probability_max"].append(precip_prob[i] if i < len(precip_prob) else None)
    
    return out


def _filter_archive_years(daily: dict[str, list[Any]], start_year: int, end_year: int) -> dict[str, list[Any]]:
    """Filter daily data to archive years."""
    times = daily.get("time") or []
    precip = daily.get("precipitation_sum") or []
    
    out = {"time": [], "precipitation_sum": []}
    for i, t in enumerate(times):
        date_str = str(t).split("T")[0]
        year = int(date_str.split("-")[0])
        if start_year <= year <= end_year:
            out["time"].append(t)
            out["precipitation_sum"].append(precip[i] if i < len(precip) else None)
    
    return out


def _fetch_forecast_with_past(
    daily: dict[str, list[Any]],
    as_of: str,
    past_days: int = 30,
    forecast_days: int = 7,
) -> dict[str, list[Any]]:
    """Slice forecast + past days from cached daily data around as_of date."""
    from datetime import date, timedelta
    from eval.weather_cache import _d
    
    a = _d(as_of)
    start = a - timedelta(days=past_days)
    end = a + timedelta(days=forecast_days - 1)
    
    return _filter_date_range(daily, start.isoformat(), end.isoformat())


def _fetch_archive_years(
    daily: dict[str, list[Any]],
    start_year: int = 2019,
    end_year: int = 2023,
) -> dict[str, list[Any]]:
    """Filter archive precipitation for SPI reference distribution."""
    return _filter_archive_years(daily, start_year, end_year)


def _build_monthly_precip_totals(archive_daily: dict[str, list[Any]] | None) -> dict[int, list[float]]:
    """Aggregate archive daily rainfall into monthly totals keyed by calendar month."""
    if not archive_daily:
        return {}
    
    times = archive_daily.get("time") or []
    precip = archive_daily.get("precipitation_sum") or []
    if len(times) != len(precip):
        return {}
    
    totals_by_year_month: dict[tuple[int, int], float] = defaultdict(float)
    for index, timestamp in enumerate(times):
        try:
            date_text = str(timestamp).split("T")[0]
            year_text, month_text, _ = date_text.split("-")
            key = (int(year_text), int(month_text))
        except ValueError:
            continue
        totals_by_year_month[key] += precip[index] or 0.0
    
    monthly_totals: dict[int, list[float]] = defaultdict(list)
    for (_, month), total in sorted(totals_by_year_month.items()):
        monthly_totals[month].append(round(total, 3))
    return dict(monthly_totals)


def _reference_month(times: list[str], n_past: int) -> int | None:
    if not times or n_past <= 0:
        return None
    try:
        date_text = str(times[n_past - 1]).split("T")[0]
        return int(date_text.split("-")[1])
    except (IndexError, ValueError):
        return None


def _calculate_spi_1(
    actual_30d_mm: float,
    times: list[str],
    archive_daily: dict[str, Any] | None,
    n_past: int,
) -> tuple[float, float | None, float | None]:
    """Approximate SPI-1 from a 30-day observed precipitation total."""
    month = _reference_month(times, n_past)
    monthly_totals = _build_monthly_precip_totals(archive_daily)
    historical_values = monthly_totals.get(month or 0, [])
    if len(historical_values) < 2:
        return 0.0, None, None
    
    mean_value = statistics.mean(historical_values)
    std_value = statistics.stdev(historical_values) if len(historical_values) > 1 else None
    zero_probability = sum(1 for value in historical_values if value <= 0) / len(historical_values)
    positive_values = [value for value in historical_values if value > 0]
    
    if not positive_values:
        spi = -2.5 if actual_30d_mm <= 0 else 0.0
        return (
            float(round(spi, 2)),
            float(round(mean_value, 1)),
            float(round(std_value, 1)) if std_value is not None else None,
        )
    
    try:
        if len(set(round(value, 6) for value in positive_values)) < 2:
            raise ValueError("Not enough variability for gamma fit")
        shape, loc, scale = gamma.fit(positive_values, floc=0)
        gamma_cdf = gamma.cdf(max(actual_30d_mm, 0.0), shape, loc=loc, scale=scale)
        cdf = zero_probability + ((1 - zero_probability) * gamma_cdf)
    except Exception:
        rank = sum(1 for value in historical_values if value <= actual_30d_mm)
        cdf = rank / (len(historical_values) + 1)
    
    cdf = min(max(cdf, 1e-6), 1 - 1e-6)
    spi = float(norm.ppf(cdf))
    return (
        float(round(spi, 2)),
        float(round(mean_value, 1)),
        float(round(std_value, 1)) if std_value is not None else None,
    )


def _spi_to_drought_probability(spi: float) -> float:
    for threshold, probability in SPI_TO_DROUGHT_PROBABILITY:
        if spi < threshold:
            return probability
    return 0.08


def _drought_severity_from_spi(spi: float) -> str:
    if spi < -2.0:
        return "severe"
    if spi < -1.5:
        return "moderate"
    if spi < -1.0:
        return "mild"
    return "normal"


def _heatwave_probability(
    max_temps_7d: list[float],
    min_temps_7d: list[float] | None,
) -> tuple[float, str]:
    del min_temps_7d
    if not max_temps_7d:
        return 0.08, "none"
    
    max_temps = [temp for temp in max_temps_7d if temp is not None]
    if not max_temps:
        return 0.08, "none"
    
    absolute_max = max(max_temps)
    consecutive_35 = 0
    max_consecutive_35 = 0
    for temp in max_temps:
        if temp >= 35:
            consecutive_35 += 1
            max_consecutive_35 = max(max_consecutive_35, consecutive_35)
        else:
            consecutive_35 = 0
    consecutive_38 = sum(1 for temp in max_temps if temp >= 38)
    
    if absolute_max >= 40 or consecutive_38 >= HEATWAVE_DAYS_38C or max_consecutive_35 >= 5:
        return 0.52, "high"
    if consecutive_38 >= 1 or max_consecutive_35 >= HEATWAVE_DAYS_35C:
        return 0.35, "moderate"
    if max_consecutive_35 >= 2 or any(temp >= 35 for temp in max_temps):
        return 0.18, "low"
    return 0.08, "none"


def _flood_probability(
    precip_7d: list[float],
    precip_30d: list[float],
) -> tuple[float, str]:
    forecast_precip = [value for value in precip_7d if value is not None]
    recent_precip = [value for value in precip_30d if value is not None]
    total_7d = sum(forecast_precip) if forecast_precip else 0.0
    total_30d = sum(recent_precip) if recent_precip else 0.0
    max_1day = max(forecast_precip) if forecast_precip else 0.0
    
    probability = 0.05
    severity = "low"
    for threshold, base_probability in FLOOD_7D_MM:
        if total_7d >= threshold:
            probability = base_probability
            break
    
    for threshold, increment in FLOOD_1DAY_MM:
        if max_1day >= threshold:
            probability = min(0.65, probability + increment)
            severity = "high" if max_1day >= 50 else "moderate"
            break
    
    if total_30d > 100 and total_7d > 30:
        probability = min(0.70, probability + 0.12)
        severity = "high" if probability >= 0.35 else "moderate"
    
    if probability >= 0.40:
        severity = "high"
    elif probability >= 0.15:
        severity = "moderate"
    
    return round(probability, 2), severity


def run(latitude: float, longitude: float, as_of: str = None) -> dict[str, Any]:
    """Compute drought, flood, and heatwave risks from pre-cached weather data."""
    logger.info("eval_risk_tool.run(lat=%s, lon=%s)", latitude, longitude)
    
    if as_of is None:
        from datetime import date
        as_of = date.today().isoformat()
    
    # Load pre-cached weather data
    daily = _load_weather_cache(latitude, longitude)
    if daily is None:
        logger.warning("No cached weather data for lat=%s, lon=%s", latitude, longitude)
        return {
            "tool": "risk_analysis",
            "drought_probability": 0.08,
            "flood_probability": 0.08,
            "heatwave_probability": 0.08,
            "drought_severity": "normal",
            "drought_z_score_30d": 0.0,
            "drought_climatology_30d_mm": None,
            "drought_climatology_std_mm": None,
            "heatwave_severity": "none",
            "flood_severity": "low",
            "precipitation_30d_mm": 0.0,
            "precipitation_forecast_7d_mm": 0.0,
            "data_period": "cached",
            "error": "No cached weather data available",
        }
    
    # Slice forecast + past days
    forecast = _fetch_forecast_with_past(daily, as_of, past_days=30, forecast_days=7)
    
    # Filter archive for SPI reference (2019-2023)
    archive = _fetch_archive_years(daily, 2019, 2023)
    
    daily_f = (forecast or {}).get("daily") or {}
    times = daily_f.get("time") or []
    max_temps = daily_f.get("temperature_2m_max") or []
    min_temps = daily_f.get("temperature_2m_min") or []
    precipitation = daily_f.get("precipitation_sum") or []
    
    n_total = len(times)
    n_past = 30
    if n_total < 37:
        n_past = min(30, max(0, n_total - 7))
    
    precip_30d = precipitation[:n_past] if n_past else []
    precip_7d = precipitation[n_past : n_past + 7] if len(precipitation) > n_past else (
        precipitation[-7:] if len(precipitation) >= 7 else precipitation
    )
    max_temps_7d = max_temps[n_past : n_past + 7] if len(max_temps) > n_past else (
        max_temps[-7:] if len(max_temps) >= 7 else max_temps
    )
    min_temps_7d = min_temps[n_past : n_past + 7] if len(min_temps) > n_past else (
        min_temps[-7:] if len(min_temps) >= 7 else None
    )
    
    actual_30d_mm = sum(value for value in precip_30d if value is not None)
    archive_daily = archive.get("daily") if archive else None
    spi_score, climatology_mean, climatology_std = _calculate_spi_1(
        actual_30d_mm,
        times,
        archive_daily,
        n_past,
    )
    
    drought_probability = _spi_to_drought_probability(spi_score)
    drought_severity = _drought_severity_from_spi(spi_score)
    heatwave_probability, heatwave_severity = _heatwave_probability(max_temps_7d, min_temps_7d)
    flood_probability, flood_severity = _flood_probability(precip_7d, precip_30d)
    
    return {
        "tool": "risk_analysis",
        "drought_probability": round(drought_probability, 2),
        "flood_probability": round(flood_probability, 2),
        "heatwave_probability": round(heatwave_probability, 2),
        "drought_severity": drought_severity,
        "drought_z_score_30d": spi_score,
        "drought_climatology_30d_mm": climatology_mean,
        "drought_climatology_std_mm": climatology_std,
        "heatwave_severity": heatwave_severity,
        "flood_severity": flood_severity,
        "precipitation_30d_mm": round(actual_30d_mm, 1),
        "precipitation_forecast_7d_mm": round(sum(value for value in precip_7d if value is not None), 1),
        "data_period": "cached_30d_past_7d_forecast",
    }


def _load_weather_cache(lat: float, lon: float) -> dict[str, Any] | None:
    """Load pre-cached weather data for a coordinate."""
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
    
    import json
    with cache_path.open(encoding="utf-8") as fh:
        return json.load(fh)


# Constants
SPI_TO_DROUGHT_PROBABILITY = [
    (-2.0, 0.70),
    (-1.5, 0.55),
    (-1.0, 0.22),
]

HEATWAVE_DAYS_35C = 3
HEATWAVE_DAYS_38C = 2
FLOOD_7D_MM = [(200, 0.50), (150, 0.38), (100, 0.28), (50, 0.15), (20, 0.08)]
FLOOD_1DAY_MM = [(80, 0.35), (50, 0.22), (30, 0.12)]


def _spi_to_drought_probability(spi: float) -> float:
    for threshold, probability in SPI_TO_DROUGHT_PROBABILITY:
        if spi < threshold:
            return probability
    return 0.08


def _drought_severity_from_spi(spi: float) -> str:
    if spi < -2.0:
        return "severe"
    if spi < -1.5:
        return "moderate"
    if spi < -1.0:
        return "mild"
    return "normal"


def _heatwave_probability(
    max_temps_7d: list[float],
    min_temps_7d: list[float] | None,
) -> tuple[float, str]:
    if not max_temps_7d:
        return 0.08, "none"
    
    max_temps = [temp for temp in max_temps_7d if temp is not None]
    if not max_temps:
        return 0.08, "none"
    
    absolute_max = max(max_temps)
    consecutive_35 = 0
    max_consecutive_35 = 0
    for temp in max_temps:
        if temp >= 35:
            consecutive_35 += 1
            max_consecutive_35 = max(max_consecutive_35, consecutive_35)
        else:
            consecutive_35 = 0
    consecutive_38 = sum(1 for temp in max_temps if temp >= 38)
    
    if absolute_max >= 40 or consecutive_38 >= HEATWAVE_DAYS_38C or max_consecutive_35 >= 5:
        return 0.52, "high"
    if consecutive_38 >= 1 or max_consecutive_35 >= HEATWAVE_DAYS_35C:
        return 0.35, "moderate"
    if max_consecutive_35 >= 2 or any(temp >= 35 for temp in max_temps):
        return 0.18, "low"
    return 0.08, "none"


def _flood_probability(
    precip_7d: list[float],
    precip_30d: list[float],
) -> tuple[float, str]:
    forecast_precip = [value for value in precip_7d if value is not None]
    recent_precip = [value for value in precip_30d if value is not None]
    total_7d = sum(forecast_precip) if forecast_precip else 0.0
    total_30d = sum(recent_precip) if recent_precip else 0.0
    max_1day = max(forecast_precip) if forecast_precip else 0.0
    
    probability = 0.05
    severity = "low"
    for threshold, base_probability in FLOOD_7D_MM:
        if total_7d >= threshold:
            probability = base_probability
            break
    
    for threshold, increment in FLOOD_1DAY_MM:
        if max_1day >= threshold:
            probability = min(0.65, probability + increment)
            severity = "high" if max_1day >= 50 else "moderate"
            break
    
    if total_30d > 100 and total_7d > 30:
        probability = min(0.70, probability + 0.12)
        severity = "high" if probability >= 0.35 else "moderate"
    
    if probability >= 0.40:
        severity = "high"
    elif probability >= 0.15:
        severity = "moderate"
    
    return round(probability, 2), severity