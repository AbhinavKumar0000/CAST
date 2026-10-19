"""eval-only MCP replay server (thin wrapper; core tools untouched).

Exposes the SAME six tool names with the SAME ``(latitude, longitude)`` signature
as ``mcp_server/server.py``, but returns the pre-computed, date-correct evidence
bundle for the scenario at those coordinates. Those bundles are produced by
``eval/scripts/build_evidence_v2.py`` using ``eval.time_anchored.TimeAnchoredBuilder``
(the frozen, time-anchored offline builder); this server only reads the pre-computed
JSON and never runs the live tools (no ``datetime.now()``, no live Open-Meteo).

Environment:
  EVAL_EVIDENCE_DIR  directory with <scenario_id>.json evidence bundles
  EVAL_INDEX         JSON file mapping "lat,lon" (rounded to 4 dp) -> scenario_id
  MCP_HOST / MCP_PORT  bind address (defaults 127.0.0.1:8011)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field

from eval.anyio_compat import install as _install_anyio_compat

# mcp 1.22's streamable-http server subscribes to anyio's generic memory-stream
# factory; the installed anyio (3.7.1) does not support it. See eval/anyio_compat.py.
_install_anyio_compat()

from mcp.server.fastmcp import FastMCP

MCP_HOST = os.getenv("MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.getenv("MCP_PORT", "8011"))
EVIDENCE_DIR = Path(os.getenv("EVAL_EVIDENCE_DIR", "eval/runs/archive_v2/evidence"))
INDEX_PATH = Path(os.getenv("EVAL_INDEX", str(EVIDENCE_DIR / "index.json")))

mcp = FastMCP(
    name="AgroLLaMA",
    instructions=(
        "Agricultural intelligence tools for Madhya Pradesh, India. "
        "All tools accept latitude/longitude in EPSG:4326 decimal degrees. "
        "Call weather_tool, climate_tool, season_tool, risk_tool, and "
        "get_soil_by_coordinates one-by-one, then call crop_score to obtain "
        "a deterministic ranked crop shortlist."
    ),
    host=MCP_HOST,
    port=MCP_PORT,
)

_INDEX: dict[str, str] | None = None
_BUNDLE_CACHE: dict[str, dict[str, Any]] = {}

# Parameter descriptions must match the harness declarations
# (``NvidiaProvider._build_tools``) so a native MCP client sees an identical
# interface. See eval/scripts/mcp_schema_diff.py.
Latitude = Annotated[float, Field(description="Latitude in decimal degrees")]
Longitude = Annotated[float, Field(description="Longitude in decimal degrees")]


def _key(lat: float, lon: float) -> str:
    return f"{round(float(lat), 4)},{round(float(lon), 4)}"


def _index() -> dict[str, str]:
    global _INDEX
    if _INDEX is None:
        try:
            _INDEX = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
        except FileNotFoundError:
            _INDEX = {}
    return _INDEX


def _bundle(lat: float, lon: float) -> dict[str, Any] | None:
    sid = _index().get(_key(lat, lon))
    if sid is None:
        return None
    if sid not in _BUNDLE_CACHE:
        path = EVIDENCE_DIR / f"{sid}.json"
        if not path.exists():
            return None
        _BUNDLE_CACHE[sid] = json.loads(path.read_text(encoding="utf-8"))
    return _BUNDLE_CACHE[sid]


def _serve(tool_field: str, lat: float, lon: float) -> dict[str, Any]:
    bundle = _bundle(lat, lon)
    if bundle is None:
        return {"error": "No scenario evidence for these coordinates", "tool": tool_field}
    return bundle.get(tool_field, {"error": "missing field", "tool": tool_field})


@mcp.tool()
def weather_tool(latitude: Latitude, longitude: Longitude) -> dict[str, Any]:
    """Get weather forecast data for the coordinates: temperature, rainfall, humidity, and precipitation probability."""
    return _serve("weather", latitude, longitude)


@mcp.tool()
def climate_tool(latitude: Latitude, longitude: Longitude) -> dict[str, Any]:
    """Get climate normals for the region: average rainfall, average temperature, and monthly normals."""
    return _serve("climate", latitude, longitude)


@mcp.tool()
def season_tool(latitude: Latitude, longitude: Longitude) -> dict[str, Any]:
    """Get the current cropping season in IST: Kharif, Rabi, or Zaid."""
    return _serve("season", latitude, longitude)


@mcp.tool()
def risk_tool(latitude: Latitude, longitude: Longitude) -> dict[str, Any]:
    """Get drought, flood, and heatwave risk analysis for the location."""
    return _serve("risk", latitude, longitude)


@mcp.tool()
def get_soil_by_coordinates(latitude: Latitude, longitude: Longitude) -> dict[str, Any]:
    """Get district, dominant soil, soil characteristics, and agricultural suitability for a location in Madhya Pradesh."""
    return _serve("soil", latitude, longitude)


@mcp.tool()
def crop_score(latitude: Latitude, longitude: Longitude) -> dict[str, Any]:
    """Rank the best candidate crops for the coordinates using deterministic scoring over weather, climate, soil, season, and risk evidence."""
    return _serve("crop_score", latitude, longitude)


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
