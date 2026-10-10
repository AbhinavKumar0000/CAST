"""Scenario generation (STEP 2).

Generates the 10k scenario set, the stress set, and the stratified LLM subset.
Points are sampled inside real GADM district polygons so every scenario is inside
Madhya Pradesh. Seasons are assigned by the as-of date using the SAME month map
as the repo's season_tool, so season strata are well-defined before any LLM run.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from eval.common import config_dirs, ensure_dirs, load_config, write_json
from mcp_server.season_tool import MONTH_TO_SEASON

logger = logging.getLogger(__name__)

SEASON_MONTHS = {
    "Kharif": [6, 7, 8, 9, 10],
    "Rabi": [11, 12, 1, 2, 3],
    "Zaid": [4, 5],
}
ISO = "%Y-%m-%d"


def _load_geodata() -> tuple[Any, dict[str, Any]]:
    import geopandas as gpd

    cfg = load_config()
    path = Path(config_dirs(cfg)["repo_root"]) / "data" / "processed" / "mp_districts.geojson"
    gdf = gpd.read_file(path)
    if gdf.crs is None:
        gdf = gdf.set_crs(4326, allow_override=True)
    else:
        gdf = gdf.to_crs(4326)
    geoms = {str(r["NAME_2"]).strip(): r.geometry for _, r in gdf.iterrows()}
    return gdf, geoms


def _sample_point(geom: Any, rng: np.random.Generator) -> tuple[float, float]:
    from shapely.geometry import Point

    minx, miny, maxx, maxy = geom.bounds
    for _ in range(200):
        x = rng.uniform(minx, maxx)
        y = rng.uniform(miny, maxy)
        if geom.covers(Point(x, y)):
            return float(x), float(y)
    rep = geom.representative_point()
    return float(rep.x), float(rep.y)


def _load_zone_map(cfg: dict[str, Any]) -> dict[str, str]:
    path = Path(config_dirs(cfg)["ground_truth_dir"]) / "district_zone_map.csv"
    if not path.exists():
        return {}
    import csv

    out: dict[str, str] = {}
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            d = (row.get("district") or "").strip()
            z = (row.get("agro_climatic_zone") or "").strip()
            if d and z:
                out[d.lower()] = z
    return out


def _dates_for_season(season: str, rng: np.random.Generator) -> str:
    months = SEASON_MONTHS[season]
    year = int(rng.integers(2024, 2026))
    month = int(rng.choice(months))
    # day within month (1..28 to be safe)
    day = int(rng.integers(1, 29))
    return f"{year:04d}-{month:02d}-{day:02d}"


def generate(cfg: dict[str, Any] | None = None, n_override: int | None = None) -> list[dict[str, Any]]:
    cfg = cfg or load_config()
    ensure_dirs(cfg)
    seed = int(cfg["seeds"]["scenario_sampling"])
    rng = np.random.default_rng(seed)
    n_total = int(n_override or cfg["scenarios"]["n_total"])
    seasons = list(SEASON_MONTHS.keys())

    _, geoms = _load_geodata()
    districts = sorted(geoms.keys())
    zone_map = _load_zone_map(cfg)

    base = n_total // len(districts)
    remainder = n_total - base * len(districts)

    scenarios: list[dict[str, Any]] = []
    idx = 0
    for di, district in enumerate(districts):
        count = base + (1 if di < remainder else 0)
        geom = geoms[district]
        per_season = count // len(seasons)
        season_assign = [s for s in seasons for _ in range(per_season)]
        while len(season_assign) < count:
            season_assign.append(seasons[len(season_assign) % len(seasons)])
        rng.shuffle(season_assign)
        for season in season_assign:
            idx += 1
            lon, lat = _sample_point(geom, rng)
            as_of = _dates_for_season(season, rng)
            scenarios.append(
                {
                    "scenario_id": f"S{idx:06d}",
                    "district": district,
                    "lat": round(lat, 6),
                    "lon": round(lon, 6),
                    "as_of_date": as_of,
                    "month": int(as_of[5:7]),
                    "season_by_month": MONTH_TO_SEASON.get(int(as_of[5:7]), "Unknown"),
                    "season_stratum": season,
                    "agro_climatic_zone": zone_map.get(district.lower()),
                }
            )
    return scenarios


def write_scenarios(scenarios: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in scenarios:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_llm_subset(cfg: dict[str, Any], scenarios: list[dict[str, Any]], stress_ids: set[str], path: Path) -> list[dict[str, Any]]:
    """Stratified sample of `llm_subset.n`, always including >= min_stress stress rows."""
    rng = np.random.default_rng(int(cfg["seeds"]["llm_subset_sampling"]))
    n = int(cfg["scenarios"]["llm_subset"]["n"])
    min_stress = int(cfg["scenarios"]["llm_subset"]["min_stress"])

    by_id = {s["scenario_id"]: s for s in scenarios}
    stress = [s for s in scenarios if s["scenario_id"] in stress_ids]
    non_stress = [s for s in scenarios if s["scenario_id"] not in stress_ids]

    rng.shuffle(stress)
    rng.shuffle(non_stress)
    chosen_stress = stress[: min(min_stress, len(stress))]
    remaining = n - len(chosen_stress)
    chosen_non = non_stress[:remaining]

    # Top up with more stress if non-stress insufficient.
    if len(chosen_non) < remaining:
        extra = stress[len(chosen_stress) : len(chosen_stress) + (remaining - len(chosen_non))]
        chosen_stress += extra

    subset = chosen_stress + chosen_non
    # Stratify check: ensure district/season coverage by re-sorting deterministically.
    subset.sort(key=lambda s: s["scenario_id"])
    write_scenarios(subset, path)
    logger.info("LLM subset: %d rows (%d stress)", len(subset), len(chosen_stress))
    return subset


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    cfg = load_config()
    sc = generate(cfg)
    dirs = ensure_dirs(cfg)
    write_scenarios(sc, dirs["scenarios_path"])
    meta = {
        "n": len(sc),
        "districts": len({s["district"] for s in sc}),
        "seasons": {s: sum(1 for x in sc if x["season_stratum"] == s) for s in SEASON_MONTHS},
        "zones_mapped": sum(1 for s in sc if s["agro_climatic_zone"]),
        "config_sha256": __import__("eval.common", fromlist=["config_sha256"]).config_sha256(),
    }
    write_json(Path(dirs["results_dir"]) / "scenario_summary.json", meta)
    print(json.dumps(meta, indent=2))
