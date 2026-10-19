"""S-series: time-anchored builder that applies a named perturbation (PROTOCOL 8.32).

Subclasses ``eval.time_anchored.TimeAnchoredBuilder`` and overrides ONLY the
per-district weather date-map used by the (unchanged) real tools. ``mcp_server/``
is never modified; originals on disk are never edited.

Usage:
    builder = PerturbedTimeAnchoredBuilder(cfg, "W2")   # +2 C
    runtime = ToolRuntime(cfg, builder=builder)         # in-process tool transport
    evidence = builder.build(scenario)
"""

from __future__ import annotations

from typing import Any

from eval.s_series.perturbations import PERTURBATIONS
from eval.time_anchored import TimeAnchoredBuilder


class PerturbedTimeAnchoredBuilder(TimeAnchoredBuilder):
    def __init__(self, cfg: dict[str, Any] | None = None, set_name: str = "N0") -> None:
        super().__init__(cfg)
        if set_name not in PERTURBATIONS:
            raise ValueError(f"Unknown perturbation set: {set_name}")
        self.set_name = set_name
        self.transform = PERTURBATIONS[set_name]["transform"]
        self._base_maps: dict[str, dict[str, Any]] = {}

    def _base_map(self, district: str) -> dict[str, Any]:
        if district not in self._base_maps:
            # super()._date_map reads the on-disk weather cache (read-only).
            self._base_maps[district] = super()._date_map(district)
        return self._base_maps[district]

    def build(self, scenario: dict[str, Any]) -> dict[str, Any]:
        district = scenario["district"]
        lat = float(scenario["lat"])
        lon = float(scenario["lon"])
        as_of = scenario["as_of_date"]

        base = self._base_map(district)
        date_map = self.transform(base, as_of)

        if date_map.get(as_of) is None:
            raise RuntimeError(
                f"No perturbed weather for {district} on {as_of} (set={self.set_name})"
            )

        self._install_patches(date_map, as_of)
        from mcp_server import (
            climate_tool,
            crop_score_tool,
            risk_tool,
            season_tool,
            soil_tool,
            weather_tool,
        )

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

        from eval.time_anchored import NORMALS_START

        def _iso_between(dm, start, end_exclusive):
            return sorted(d for d in dm if start <= d < end_exclusive)

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
            "_s_set": self.set_name,
            "_climate_normals_days": n_climate_days,
        }
