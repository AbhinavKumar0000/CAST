"""Bulk Open-Meteo archive cache (one request per district) + local window slicing.

All scenario weather is sliced from this cache so no per-scenario network calls are
made and every scenario is reproducible. The archive is reanalysis, so the "forecast"
window is observed values (a hindcast) — stated throughout the report.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from eval.common import config_dirs, load_config, read_jsonl, write_json
from mcp_server.open_meteo_client import OpenMeteoError, archive_client

logger = logging.getLogger(__name__)

# Window wide enough to cover: 2019-2023 SPI reference, 2014-2023 normals,
# 30-day lookback before 2024-01-01, and 7-day forward from 2025-12-31.
FETCH_START = "2013-12-01"
FETCH_END = "2026-01-15"

DAILY_VARS = "temperature_2m_mean,temperature_2m_max,temperature_2m_min,precipitation_sum"

_ISO = "%Y-%m-%d"


def _d(s: str) -> date:
    return datetime.strptime(s, _ISO).date()


def district_points() -> dict[str, dict[str, float]]:
    """Representative point per district polygon: {district: {lat, lon}}."""
    from eval.common import ensure_dirs

    cfg = load_config()
    ensure_dirs(cfg)
    import geopandas as gpd

    geojson = Path(config_dirs(cfg)["data_dir"]) / ".." / ".." / "data" / "processed" / "mp_districts.geojson"
    geojson = (Path(config_dirs(cfg)["repo_root"]) / "data" / "processed" / "mp_districts.geojson").resolve()
    gdf = gpd.read_file(geojson)
    if gdf.crs is None:
        gdf = gdf.set_crs(4326, allow_override=True)
    else:
        gdf = gdf.to_crs(4326)
    out: dict[str, dict[str, float]] = {}
    for _, row in gdf.iterrows():
        name = str(row.get("NAME_2") or "").strip()
        if not name:
            continue
        pt = row.geometry.representative_point()
        out[name] = {"lat": float(pt.y), "lon": float(pt.x)}
    return out


def _cache_path(cfg: dict[str, Any], district: str) -> Path:
    safe = "".join(ch if ch.isalnum() else "_" for ch in district.lower())
    return Path(config_dirs(cfg)["cache_dir"]) / "weather" / f"{safe}.json"


def fetch_district_archive(lat: float, lon: float) -> dict[str, list[Any]]:
    """One archive request: daily tmean/tmax/tmin/precip for FETCH_START..FETCH_END."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": FETCH_START,
        "end_date": FETCH_END,
        "daily": DAILY_VARS,
        "timezone": "auto",
    }
    return archive_client.fetch(params)


def load_or_fetch_district(cfg: dict[str, Any], district: str, point: dict[str, float], force: bool = False) -> dict[str, Any]:
    path = _cache_path(cfg, district)
    if path.exists() and not force:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    raw = fetch_district_archive(point["lat"], point["lon"])
    daily = raw.get("daily") or {}
    write_json(path, daily)
    logger.info("fetched archive for %s (%d days)", district, len(daily.get("time") or []))
    return daily


def load_all(force: bool = False) -> dict[str, dict[str, Any]]:
    cfg = load_config()
    points = district_points()
    out: dict[str, dict[str, Any]] = {}
    for district, point in points.items():
        try:
            out[district] = load_or_fetch_district(cfg, district, point, force=force)
            time.sleep(5.0)  # respect Open-Meteo rate limits (free tier)
        except OpenMeteoError as exc:
            logger.error("archive fetch failed for %s: %s", district, exc)
    return out


def as_date_map(daily: dict[str, Any]) -> dict[str, dict[str, float | None]]:
    """Convert Open-Meteo daily arrays into {ISO date: {tmean,tmax,tmin,precip}}."""
    times = daily.get("time") or []
    tmean = daily.get("temperature_2m_mean") or []
    tmax = daily.get("temperature_2m_max") or []
    tmin = daily.get("temperature_2m_min") or []
    precip = daily.get("precipitation_sum") or []

    def at(arr: list[Any], i: int) -> float | None:
        return arr[i] if i < len(arr) else None

    out: dict[str, dict[str, float | None]] = {}
    for i, t in enumerate(times):
        out[str(t).split("T")[0]] = {
            "tmean": at(tmean, i),
            "tmax": at(tmax, i),
            "tmin": at(tmin, i),
            "precip": at(precip, i),
        }
    return out


def slice_window(date_map: dict[str, dict[str, Any]], as_of: str, past_days: int, forecast_days: int) -> dict[str, Any]:
    """Return ordered windows: `past` (as_of-past_days..as_of-1), `future` (as_of..+forecast-1)."""
    a = _d(as_of)
    past: list[dict[str, Any]] = []
    future: list[dict[str, Any]] = []
    for k in range(past_days, 0, -1):
        day = (a - timedelta(days=k)).isoformat()
        past.append({"date": day, **date_map.get(day, {})})
    for k in range(forecast_days):
        day = (a + timedelta(days=k)).isoformat()
        future.append({"date": day, **date_map.get(day, {})})
    return {"past": past, "future": future}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    pts = district_points()
    print(f"{len(pts)} districts have representative points")
    first = next(iter(pts.items()))
    print("example:", first)
