"""Time-anchored, offline tool runtime + corrected evidence builder (Phase 8, STEP A).

Preferred approach from the protocol: run the REAL tool code in ``mcp_server/`` with an
injected clock and a cached-weather provider, via a wrapper under ``eval/``. Nothing under
``mcp_server/`` is modified.

How it works
  * Weather is sliced from the per-district Open-Meteo ARCHIVE cache
    (``eval.weather_cache``), so there are no live API calls and no look-ahead
    beyond the scenario date is possible.
  * ``datetime.now()/utcnow()`` inside ``mcp_server.season_tool`` and
    ``mcp_server.crop_score_tool`` is pinned to the scenario's ``as_of_date``
    (their only wall-clock dependencies), so season AND the scorer's ``current_week``
    are evaluated as of the scenario date.
  * ``mcp_server.open_meteo_client.forecast_client/archive_client`` are patched to answer
    with date-sliced archive payloads shaped exactly like the live API responses.
  * Climate normals (``climate_tool``) are computed from cached dates STRICTLY BEFORE the
    scenario's ``as_of_date`` (no look-ahead in the normals window).
  * ``crop_score`` derives its week/season from the frozen clock, so the deterministic
    ranking is scenario-scoped too.

Exports
  * ``TimeAnchoredBuilder.build(scenario)`` -> v2 evidence bundle (superset of v1 keys).
  * ``ToolRuntime`` -> thread-safe, scenario-scoped dispatcher whose six tool names and
    ``(latitude, longitude)`` schemas are identical to the live MCP contract. The LLM
    harness (C2a/C2b) calls tools through it.

The equivalence test in ``eval/scripts/test_step_a.py`` asserts that the per-tool outputs
served by ``ToolRuntime`` are byte-identical to the bundles built by ``TimeAnchoredBuilder``,
i.e. that the LLM sees exactly the deterministic evidence C3 evaluates.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Any

import pytz

from eval.common import load_config
from eval.weather_cache import as_date_map, load_or_fetch_district, slice_window
from mcp_server import (
    climate_tool,
    crop_score_tool,
    open_meteo_client,
    risk_tool,
    season_tool,
    soil_tool,
    weather_tool,
)

logger = logging.getLogger(__name__)

IST = pytz.timezone("Asia/Kolkata")
ISO = "%Y-%m-%d"

# The real climate_tool requests this nominal window; we answer with the
# date-sliced subset so normals never include data after the scenario date.
NORMALS_START = "2014-01-01"
SPI_ARCHIVE_START = "2019-01-01"

TOOL_NAMES = (
    "weather_tool",
    "climate_tool",
    "season_tool",
    "risk_tool",
    "get_soil_by_coordinates",
    "crop_score",
)


def season_for_date(as_of: str) -> tuple[int, str]:
    """Return (month, season) for an ISO date using the real season mapping."""
    month = datetime.strptime(as_of, ISO).month
    return month, season_tool.MONTH_TO_SEASON.get(month, "Unknown")


def _frozen_datetime(as_of_iso: str):
    """A datetime subclass whose now()/utcnow() report the scenario date (12:00 IST)."""
    base_naive = datetime.strptime(as_of_iso + "T12:00:00", "%Y-%m-%dT%H:%M:%S")
    base = IST.localize(base_naive)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: ANN001
            return base if tz is None else base.astimezone(tz)

        @classmethod
        def utcnow(cls):  # noqa: D102
            return base.astimezone(pytz.utc)

    return FrozenDateTime


def _iso_between(date_map: dict[str, Any], start: str, end_exclusive: str) -> list[str]:
    return sorted(d for d in date_map if start <= d < end_exclusive)


class TimeAnchoredBuilder:
    """Builds v2 scenario evidence by running the real tool code under
    a frozen clock and a cached-weather provider."""

    def __init__(self, cfg: dict[str, Any] | None = None) -> None:
        self.cfg = cfg or load_config()
        self._date_maps: dict[str, dict[str, Any]] = {}

    # -- weather access ------------------------------------------------------
    def _date_map(self, district: str) -> dict[str, Any]:
        if district not in self._date_maps:
            from eval.weather_cache import district_points

            point = district_points()[district]
            daily = load_or_fetch_district(self.cfg, district, point)
            self._date_maps[district] = as_date_map(daily)
        return self._date_maps[district]

    # -- payload builders ----------------------------------------------------
    def _weather_payload(self, date_map: dict[str, Any], as_of: str) -> dict[str, Any]:
        win = slice_window(date_map, as_of, past_days=7, forecast_days=7)
        days = win["past"] + win["future"]  # past first, length 14
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
        days = win["past"] + win["future"]  # length 37
        return {
            "daily": {
                "time": [d["date"] for d in days],
                "temperature_2m_max": [d.get("tmax") for d in days],
                "temperature_2m_min": [d.get("tmin") for d in days],
                "precipitation_sum": [d.get("precip") for d in days],
                "precipitation_probability_max": [None] * len(days),
            }
        }

    def _climate_payload(self, date_map: dict[str, Any], as_of: str) -> dict[str, Any]:
        # Normals computed ONLY from cached dates before the scenario date.
        dates = _iso_between(date_map, NORMALS_START, as_of)
        return {
            "daily": {
                "time": dates,
                "temperature_2m_mean": [date_map[d].get("tmean") for d in dates],
                "precipitation_sum": [date_map[d].get("precip") for d in dates],
            }
        }

    def _spi_archive_payload(self, date_map: dict[str, Any]) -> dict[str, Any]:
        dates = _iso_between(date_map, SPI_ARCHIVE_START, "2024-01-01")
        return {"daily": {"time": dates, "precipitation_sum": [date_map[d].get("precip") for d in dates]}}

    # -- patching ------------------------------------------------------------
    def _install_patches(self, date_map: dict[str, Any], as_of: str) -> None:
        weather_payload = self._weather_payload(date_map, as_of)
        risk_payload = self._risk_payload(date_map, as_of)
        climate_payload = self._climate_payload(date_map, as_of)
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

        # TTL caches keyed by coordinate cell must not leak across scenarios.
        weather_tool._WEATHER_CACHE.clear()
        climate_tool._CLIMATE_CACHE.clear()

    def _restore(self) -> None:
        open_meteo_client.forecast_client.fetch = self._orig_forecast_fetch  # type: ignore[assignment]
        open_meteo_client.archive_client.fetch = self._orig_archive_fetch  # type: ignore[assignment]
        season_tool.datetime = datetime  # type: ignore[assignment]
        crop_score_tool.datetime = datetime  # type: ignore[assignment]

    # -- public --------------------------------------------------------------
    def build(self, scenario: dict[str, Any]) -> dict[str, Any]:
        """Run the real six tool functions with frozen clock + cached weather."""
        district = scenario["district"]
        lat = float(scenario["lat"])
        lon = float(scenario["lon"])
        as_of = scenario["as_of_date"]
        date_map = self._date_map(district)

        cached = date_map.get(as_of)
        if cached is None:
            raise RuntimeError(f"No cached weather for {district} on {as_of} (look-ahead impossible)")

        self._install_patches(date_map, as_of)
        try:
            weather = weather_tool.run(lat, lon)
            climate = climate_tool.run(lat, lon)
            season = season_tool.run(lat, lon)
            soil = soil_tool.run(lat, lon)
            risk = risk_tool.run(lat, lon)
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
            self._restore()

        n_climate_days = len(_iso_between(date_map, NORMALS_START, as_of))
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
            "_v": 2,
            "_climate_normals_days": n_climate_days,
        }


class ToolRuntime:
    """Thread-safe, scenario-scoped dispatcher serving the six MCP tool contracts.

    Names, descriptions and (latitude, longitude) schemas are identical to the live
    server (see ``NvidiaProvider._build_tools`` / ``mcp_server/server.py``). Each
    scenario's bundle is built ONCE on first access and cached, so repeated tool calls
    are deterministic and fast even with many LLM workers.
    """

    def __init__(self, cfg: dict[str, Any] | None = None, builder: TimeAnchoredBuilder | None = None) -> None:
        self.builder = builder or TimeAnchoredBuilder(cfg)
        self._lock = threading.RLock()
        self._bundles: dict[str, dict[str, Any]] = {}

    def _bundle(self, scenario: dict[str, Any]) -> dict[str, Any]:
        sid = scenario["scenario_id"]
        with self._lock:
            if sid not in self._bundles:
                self._bundles[sid] = self.builder.build(scenario)
            return self._bundles[sid]

    def weather_tool(self, scenario: dict[str, Any], latitude: float, longitude: float) -> dict[str, Any]:
        return self._bundle(scenario)["weather"]

    def climate_tool(self, scenario: dict[str, Any], latitude: float, longitude: float) -> dict[str, Any]:
        return self._bundle(scenario)["climate"]

    def season_tool(self, scenario: dict[str, Any], latitude: float, longitude: float) -> dict[str, Any]:
        return self._bundle(scenario)["season"]

    def risk_tool(self, scenario: dict[str, Any], latitude: float, longitude: float) -> dict[str, Any]:
        return self._bundle(scenario)["risk"]

    def get_soil_by_coordinates(self, scenario: dict[str, Any], latitude: float, longitude: float) -> dict[str, Any]:
        return self._bundle(scenario)["soil"]

    def crop_score(self, scenario: dict[str, Any], latitude: float, longitude: float) -> dict[str, Any]:
        return self._bundle(scenario)["crop_score"]

    def call(self, scenario: dict[str, Any], name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Dispatch a tool name from the MCP contract to its offline implementation."""
        lat = args.get("latitude")
        lon = args.get("longitude")
        if lat is None or lon is None:
            return {"error": f"{name} requires latitude and longitude.", "tool": name}
        fn = getattr(self, name, None)
        if fn is None:
            return {"error": f"Unknown tool '{name}'. Do not call a tool for the final answer; reply with the JSON object now.",
                    "tool": name, "unknown": True}
        return fn(scenario, float(lat), float(lon))

    @property
    def n_bundles(self) -> int:
        with self._lock:
            return len(self._bundles)

    def close(self) -> None:
        """No-op; present so run_model can treat all tool runtimes uniformly."""
        return None

    def __enter__(self) -> "ToolRuntime":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()