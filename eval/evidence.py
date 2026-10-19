"""Scenario-scoped evidence pipeline (eval-only, read-only w.r.t. core logic).

For a scenario (district, lat, lon, as_of_date) this reproduces exactly the six
tool outputs the live system would produce — but from the Open-Meteo **archive**
sliced to the scenario date, so historical scenarios are reproducible and there is
no per-scenario network call.

How it stays faithful to the core logic:
  * It monkeypatches the shared Open-Meteo client singletons' `.fetch` to return
    date-sliced archive payloads shaped exactly like the live API responses.
  * It freezes `datetime.now()` inside `season_tool` and `crop_score_tool` to the
    scenario date (the only wall-clock dependency in those tools).
  * It then calls the REAL tool functions unchanged.
  * The MCP eval server replays these cached outputs (see eval/mcp_eval/server.py).

Nothing under `mcp_server/` is modified.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import pytz

from eval.common import config_dirs, load_config, write_json
from eval.weather_cache import as_date_map, load_or_fetch_district, slice_window

# Import the real tool modules (unmodified) - but use eval-specific climate/risk tools
from mcp_server import crop_score_tool, season_tool, soil_tool, weather_tool
from mcp_server import open_meteo_client

# Evaluation-specific tools that use pre-cached weather data
from eval.tools import eval_climate_tool, eval_risk_tool

logger = logging.getLogger(__name__)

IST = pytz.timezone("Asia/Kolkata")
ISO = "%Y-%m-%d"


def _iso_dates_between(date_map: dict[str, Any], start: str, end: str) -> list[str]:
    return sorted(d for d in date_map if start <= d <= end)


def _frozen_datetime(as_of_iso: str):
    base_naive = datetime.strptime(as_of_iso + "T12:00:00", "%Y-%m-%dT%H:%M:%S")
    base = IST.localize(base_naive)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: ANN001
            return base if tz is None else base.astimezone(tz)

        @classmethod
        def utcnow(cls):
            return base.astimezone(pytz.utc)

    return FrozenDateTime


class EvidenceProvider:
    """Computes and caches per-scenario tool evidence from archived weather."""

    def __init__(self, cfg: dict[str, Any] | None = None, force_weather: bool = False) -> None:
        self.cfg = cfg or load_config()
        self.force_weather = force_weather
        self._date_maps: dict[str, dict[str, Any]] = {}
        self._patched = False

    # -- weather access ------------------------------------------------------
    def _date_map(self, district: str) -> dict[str, Any]:
        if district not in self._date_maps:
            from eval.weather_cache import district_points

            point = district_points()[district]
            daily = load_or_fetch_district(self.cfg, district, point, force=self.force_weather)
            self._date_maps[district] = as_date_map(daily)
        return self._date_maps[district]

    # -- payload builders ----------------------------------------------------
    def _weather_payload(self, date_map: dict[str, Any], as_of: str) -> dict[str, Any]:
        win = slice_window(date_map, as_of, past_days=7, forecast_days=7)
        days = win["past"] + win["future"]  # 14, past first
        daily = {
            "time": [d["date"] for d in days],
            "temperature_2m_max": [d.get("tmax") for d in days],
            "temperature_2m_min": [d.get("tmin") for d in days],
            "precipitation_sum": [d.get("precip") for d in days],
            "precipitation_probability_max": [None] * len(days),
            "weather_code": [None] * len(days),
        }
        a = date_map.get(as_of, {})
        current = {
            "temperature_2m": a.get("tmean"),
            "relative_humidity_2m": None,
            "precipitation": a.get("precip"),
            "weather_code": None,
        }
        return {"current": current, "daily": daily}

    def _risk_payload(self, date_map: dict[str, Any], as_of: str) -> dict[str, Any]:
        win = slice_window(date_map, as_of, past_days=30, forecast_days=7)
        days = win["past"] + win["future"]  # 37
        return {
            "daily": {
                "time": [d["date"] for d in days],
                "temperature_2m_max": [d.get("tmax") for d in days],
                "temperature_2m_min": [d.get("tmin") for d in days],
                "precipitation_sum": [d.get("precip") for d in days],
                "precipitation_probability_max": [None] * len(days),
            }
        }

    def _climate_payload(self, date_map: dict[str, Any]) -> dict[str, Any]:
        dates = _iso_dates_between(date_map, "2014-01-01", "2023-12-31")
        return {
            "daily": {
                "time": dates,
                "temperature_2m_mean": [date_map[d].get("tmean") for d in dates],
                "precipitation_sum": [date_map[d].get("precip") for d in dates],
            }
        }

    def _spi_archive_payload(self, date_map: dict[str, Any]) -> dict[str, Any]:
        dates = _iso_dates_between(date_map, "2019-01-01", "2023-12-31")
        return {"daily": {"time": dates, "precipitation_sum": [date_map[d].get("precip") for d in dates]}}

    # -- patching ------------------------------------------------------------
    def _install_patches(self, date_map: dict[str, Any], as_of: str) -> None:
        weather_payload = self._weather_payload(date_map, as_of)
        risk_payload = self._risk_payload(date_map, as_of)
        climate_payload = self._climate_payload(date_map)
        spi_payload = self._spi_archive_payload(date_map)

        def fake_forecast_fetch(params: dict[str, Any]) -> dict[str, Any]:
            if int(params.get("past_days", 0)) >= 30:
                return risk_payload
            return weather_payload

        def fake_archive_fetch(params: dict[str, Any]) -> dict[str, Any]:
            start = str(params.get("start_date", ""))
            if start.startswith("2019"):
                return spi_payload
            return climate_payload

        self._orig_forecast_fetch = open_meteo_client.forecast_client.fetch
        self._orig_archive_fetch = open_meteo_client.archive_client.fetch
        open_meteo_client.forecast_client.fetch = fake_forecast_fetch  # type: ignore[assignment]
        open_meteo_client.archive_client.fetch = fake_archive_fetch  # type: ignore[assignment]

        frozen = _frozen_datetime(as_of)
        season_tool.datetime = frozen  # type: ignore[assignment]
        crop_score_tool.datetime = frozen  # type: ignore[assignment]

        # Clear in-memory TTL caches so different dates at the same 0.1deg cell
        # do not collide.
        weather_tool._WEATHER_CACHE.clear()
        # Don't clear climate_tool._CLIMATE_CACHE since we use eval_climate_tool

    # -- public --------------------------------------------------------------
    def build(self, scenario: dict[str, Any]) -> dict[str, Any]:
        district = scenario["district"]
        lat = float(scenario["lat"])
        lon = float(scenario["lon"])
        as_of = scenario["as_of_date"]
        date_map = self._date_map(district)

        self._install_patches(date_map, as_of)
        try:
            weather = weather_tool.run(lat, lon)
            # Use eval-specific climate tool that reads from cache
            climate = eval_climate_tool.run(lat, lon)
            season = season_tool.run(lat, lon)
            soil = soil_tool.run(lat, lon)
            # Use eval-specific risk tool that reads from cache
            risk = eval_risk_tool.run(lat, lon, as_of=as_of)
            crop = crop_score_tool.run(
                latitude=lat,
                longitude=lon,
                weather=weather,
                climate=climate,
                soil=soil,
                risk=risk,
                season=season,
            )
        finally:
            # Restore the real Open-Meteo methods and the real datetime classes.
            open_meteo_client.forecast_client.fetch = self._orig_forecast_fetch  # type: ignore[assignment]
            open_meteo_client.archive_client.fetch = self._orig_archive_fetch  # type: ignore[assignment]
            season_tool.datetime = datetime  # type: ignore[assignment]
            crop_score_tool.datetime = datetime  # type: ignore[assignment]

        return {
            "scenario_id": scenario["scenario_id"],
            "district": district,
            "as_of_date": as_of,
            "weather": weather,
            "climate": climate,
            "season": season,
            "soil": soil,
            "risk": risk,
            "crop_score": crop,
        }


def build_many(scenarios: list[dict[str, Any]], out_dir: Path, cfg: dict[str, Any] | None = None) -> int:
    provider = EvidenceProvider(cfg)
    out_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for sc in scenarios:
        bundle = provider.build(sc)
        write_json(out_dir / f"{sc['scenario_id']}.json", bundle)
        count += 1
    return count


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    cfg = load_config()
    from eval.weather_cache import district_points

    pts = district_points()
    print(f"{len(pts)} districts; building one sample evidence bundle...")
    sample = {
        "scenario_id": "TEST0001",
        "district": "Bhopal",
        "lat": pts["Bhopal"]["lat"],
        "lon": pts["Bhopal"]["lon"],
        "as_of_date": "2024-07-15",
    }
    bundle = EvidenceProvider(cfg).build(sample)
    import json

    print(json.dumps(bundle["risk"], indent=2)[:800])
    print("weather:", json.dumps(bundle["weather"], indent=2)[:400])
    print("crop top3:", [c["crop"] for c in bundle["crop_score"]["ranked_crops"][:3]])
