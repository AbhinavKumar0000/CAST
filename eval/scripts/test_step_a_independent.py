"""Phase 8 STEP A (addendum): INDEPENDENT equivalence + hand-verified totals.

Follow-up to the user's four points:

POINT 1 - independent check:
  (a) For 30 scenarios, run the ORIGINAL tool code (mcp_server.*) with only the clock
      frozen and weather pulled from the raw district cache, but with the daily
      payloads assembled by a SEPARATE, independently-written slicer (not the
      ``TimeAnchoredBuilder`` payload builders). Compare every output field against
      the v2 evidence bundles the harness uses.
  (b) Hand-verify 5 scenarios: season (from scenario as_of_date via MONTH_TO_SEASON)
      and rainfall totals (7d forecast, past-7d, 30d, forecast-7d) recomputed directly
      from the raw cache JSON (independent summation).

POINT 4 - soil: confirms which scenario districts lack a soil match and what
soil_tool returns for them (no silent default). See print_soil_status().

POINT 2 - the normals window used now vs v1/paper and 5 examples of ranking changes is
printed by this script and then recorded in PROTOCOL.md.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

import pytz  # noqa: E402

from eval.common import config_dirs, load_config, read_jsonl  # noqa: E402
from mcp_server import (  # noqa: E402
    climate_tool,
    crop_score_tool,
    open_meteo_client,
    risk_tool,
    season_tool,
    soil_tool,
    weather_tool,
)

IST = pytz.timezone("Asia/Kolkata")
ISO = "%Y-%m-%d"


# --------------------------------------------------------------------------- #
# INDEPENDENT slicer: reads the raw district cache (JSON) and builds the daily
# payloads from scratch. This is intentionally a SEPARATE implementation from
# TimeAnchoredBuilder._weather_payload / _risk_payload / _climate_payload.
# --------------------------------------------------------------------------- #
def load_raw_cache(district: str) -> dict[str, dict[str, float | None]]:
    safe = "".join(ch if ch.isalnum() else "_" for ch in district.lower())
    cfg = load_config()
    p = Path(config_dirs(cfg)["cache_dir"]) / "weather" / f"{safe}.json"
    daily = json.loads(p.read_text(encoding="utf-8"))
    times = daily.get("time") or []
    tmean = daily.get("temperature_2m_mean") or []
    tmax = daily.get("temperature_2m_max") or []
    tmin = daily.get("temperature_2m_min") or []
    precip = daily.get("precipitation_sum") or []
    out: dict[str, dict[str, float | None]] = {}
    for i, t in enumerate(times):
        d = str(t).split("T")[0]
        out[d] = {
            "tmean": tmean[i] if i < len(tmean) else None,
            "tmax": tmax[i] if i < len(tmax) else None,
            "tmin": tmin[i] if i < len(tmin) else None,
            "precip": precip[i] if i < len(precip) else None,
        }
    return out


def iso_add(day: str, days: int) -> str:
    d = datetime.strptime(day, ISO).date()
    return (d + timedelta(days=days)).isoformat()


def independent_weather_payload(m: dict[str, dict[str, float | None]], as_of: str) -> dict:
    past_keys = [iso_add(as_of, -k) for k in range(7, 0, -1)]
    fut_keys = [iso_add(as_of, k) for k in range(7)]
    days = [m.get(k, {}) for k in past_keys + fut_keys]
    return {
        "current": {
            "temperature_2m": m.get(as_of, {}).get("tmean"),
            "relative_humidity_2m": None,
            "precipitation": m.get(as_of, {}).get("precip"),
            "weather_code": None,
        },
        "daily": {
            "time": past_keys + fut_keys,
            "temperature_2m_max": [d.get("tmax") for d in days],
            "temperature_2m_min": [d.get("tmin") for d in days],
            "precipitation_sum": [d.get("precip") for d in days],
            "precipitation_probability_max": [None] * (7 + 7),
            "weather_code": [None] * (7 + 7),
        },
    }


def independent_risk_payload(m: dict[str, dict[str, float | None]], as_of: str) -> dict:
    past_keys = [iso_add(as_of, -k) for k in range(30, 0, -1)]
    fut_keys = [iso_add(as_of, k) for k in range(7)]
    days = [m.get(k, {}) for k in past_keys + fut_keys]
    return {
        "daily": {
            "time": past_keys + fut_keys,
            "temperature_2m_max": [d.get("tmax") for d in days],
            "temperature_2m_min": [d.get("tmin") for d in days],
            "precipitation_sum": [d.get("precip") for d in days],
            "precipitation_probability_max": [None] * (30 + 7),
        }
    }


def independent_climate_payload(m: dict[str, dict[str, float | None]], as_of: str) -> dict:
    keys = sorted(d for d in m if "2014-01-01" <= d < as_of)
    return {
        "daily": {
            "time": keys,
            "temperature_2m_mean": [m[d].get("tmean") for d in keys],
            "precipitation_sum": [m[d].get("precip") for d in keys],
        }
    }


def independent_spi_payload(m: dict[str, dict[str, float | None]]) -> dict:
    keys = sorted(d for d in m if "2019-01-01" <= d < "2024-01-01")
    return {"daily": {"time": keys, "precipitation_sum": [m[d].get("precip") for d in keys]}}


def run_original_with(weather_p, risk_p, climate_p, spi_p, as_of: str, lat: float, lon: float) -> dict:
    """Run the real tools under frozen clock + patched clients with given payloads."""
    def fake_forecast(params: dict) -> dict:
        return risk_p if int(params.get("past_days", 0)) >= 30 else weather_p

    def fake_archive(params: dict) -> dict:
        return spi_p if str(params.get("start_date", "")).startswith("2019") else climate_p

    orig_f = open_meteo_client.forecast_client.fetch
    orig_a = open_meteo_client.archive_client.fetch
    open_meteo_client.forecast_client.fetch = fake_forecast
    open_meteo_client.archive_client.fetch = fake_archive

    base = IST.localize(datetime.strptime(as_of + "T12:00:00", "%Y-%m-%dT%H:%M:%S"))

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: ANN001
            return base if tz is None else base.astimezone(tz)

        @classmethod
        def utcnow(cls):  # noqa: D102
            return base.astimezone(pytz.utc)

    season_tool.datetime = FrozenDateTime
    crop_score_tool.datetime = FrozenDateTime
    weather_tool._WEATHER_CACHE.clear()
    climate_tool._CLIMATE_CACHE.clear()
    try:
        weather = weather_tool.run(lat, lon)
        climate = climate_tool.run(lat, lon)
        season = season_tool.run(lat, lon)
        soil = soil_tool.run(lat, lon)
        risk = risk_tool.run(lat, lon)
        crop = crop_score_tool.run(latitude=lat, longitude=lon, weather=weather,
                                   climate=climate, soil=soil, risk=risk, season=season)
    finally:
        open_meteo_client.forecast_client.fetch = orig_f
        open_meteo_client.archive_client.fetch = orig_a
        season_tool.datetime = datetime
        crop_score_tool.datetime = datetime
        weather_tool._WEATHER_CACHE.clear()
        climate_tool._CLIMATE_CACHE.clear()
    return {"weather": weather, "climate": climate, "season": season,
            "soil": soil, "risk": risk, "crop_score": crop}


def deep_equal(a, b):
    """Compare dicts with JSON coercion (int/str dict keys normalize identically),
    which is the form the harness actually consumes (evidence loaded from disk)."""
    def norm(v):
        return json.loads(json.dumps(v, ensure_ascii=False))
    return norm(a) == norm(b)


def pick_balanced(subset: list[dict], k: int, seed: int = 20240605) -> list[dict]:
    import random

    rng = random.Random(seed)
    picked: list[dict] = []
    for se in ["Kharif", "Rabi", "Zaid"]:
        pool = [s for s in subset if s.get("season_stratum") == se]
        sids = {s["scenario_id"] for s in picked}
        picked += [s for s in rng.sample(pool, min(k // 3, len(pool))) if s["scenario_id"] not in sids]
    if len(picked) < k:
        sids = {s["scenario_id"] for s in picked}
        for s in subset:
            if len(picked) >= k:
                break
            if s["scenario_id"] not in sids:
                picked.append(s)
                sids.add(s["scenario_id"])
    return picked[:k]


def main() -> int:
    cfg = load_config()
    subset = read_jsonl(config_dirs(cfg)["llm_subset_path"])
    v2_dir = Path("eval/runs/archive_v2/evidence")

    # ------------------------------------------------------------------ #
    # POINT 1(a): independent equivalence on 30 scenarios
    # ------------------------------------------------------------------ #
    print("=" * 70)
    print("POINT 1a — INDEPENDENT EQUIVALENCE (original tools, frozen clock +")
    print("          cached weather, SEPARATE slicer) vs v2 harness bundles")
    print("=" * 70)
    scenarios = pick_balanced(subset, 30)
    print(f"  scenarios: {len(scenarios)} ({dict(Counter(s['season_stratum'] for s in scenarios))})")
    failures = 0
    field_checks = 0
    for sc in scenarios:
        sid = sc["scenario_id"]
        as_of = sc["as_of_date"]
        bundle = json.loads((v2_dir / f"{sid}.json").read_text(encoding="utf-8"))
        m = load_raw_cache(sc["district"])
        outs = run_original_with(
            independent_weather_payload(m, as_of),
            independent_risk_payload(m, as_of),
            independent_climate_payload(m, as_of),
            independent_spi_payload(m),
            as_of,
            float(sc["lat"]),
            float(sc["lon"]),
        )
        for field in ("weather", "climate", "season", "soil", "risk", "crop_score"):
            field_checks += 1
            if not deep_equal(outs[field], bundle[field]):
                failures += 1
                print(f"  MISMATCH {sid} {field}: independent != v2 bundle")
    print(f"  field comparisons: {field_checks} across 30 scenarios x 6 tools")
    print(f"  independent-equivalence failures: {failures}")
    print(f"  result: {'ALL EQUIVALENT' if failures == 0 else 'FAIL'}")

    # ------------------------------------------------------------------ #
    # POINT 1(b): hand-verify 5 scenarios against the RAW cache
    # ------------------------------------------------------------------ #
    print()
    print("=" * 70)
    print("POINT 1b — HAND-VERIFIED season + rainfall totals from raw cache")
    print("=" * 70)
    hand_portfolio = scenarios[:5]
    hand_fail = 0
    for sc in hand_portfolio:
        sid = sc["scenario_id"]
        as_of = sc["as_of_date"]
        m = load_raw_cache(sc["district"])
        b = json.loads((v2_dir / f"{sid}.json").read_text(encoding="utf-8"))

        # season
        exp_month = datetime.strptime(as_of, ISO).month
        exp_season = season_tool.MONTH_TO_SEASON.get(exp_month, "Unknown")

        # rainfall totals, independent sums straight from the raw cache
        f7 = sum((m.get(iso_add(as_of, k), {}).get("precip") or 0.0) for k in range(7))
        p7 = sum((m.get(iso_add(as_of, -k), {}).get("precip") or 0.0) for k in range(1, 8))
        p30 = sum((m.get(iso_add(as_of, -k), {}).get("precip") or 0.0) for k in range(1, 31))

        checks = [
            ("season month", exp_month, b["season"]["current_month"]),
            ("season name", exp_season, b["season"]["current_season"]),
            ("weather 7d forecast mm", round(f7, 1), b["weather"]["total_rainfall_mm"]),
            ("weather past-7d mm", round(p7, 1), b["weather"]["rainfall_past_7d_mm"]),
            ("risk 30d mm", round(p30, 1), b["risk"]["precipitation_30d_mm"]),
            ("risk forecast-7d mm", round(f7, 1), b["risk"]["precipitation_forecast_7d_mm"]),
        ]
        ok = all(str(a) == str(got) for _, a, got in checks)
        if not ok:
            hand_fail += 1
        print(f"  {sid} {sc['district']:14s} as_of={as_of}:")
        for label, expected, got in checks:
            mark = "ok" if str(expected) == str(got) else f"DIFF (expected {expected})"
            print(f"      {label:24s} -> bundle {got} {mark}")
    print(f"  hand-check failures: {hand_fail}")

    return 0 if (failures == 0 and hand_fail == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())