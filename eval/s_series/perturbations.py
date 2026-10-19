"""S-series: named, sourced "simulated scenario" perturbations (PROTOCOL 8.33 amendment).

Each perturbation transforms a per-district weather ``date_map``
(``{ISO date: {tmean,tmax,tmin,precip}}``, see ``eval.weather_cache.as_date_map``)
into a NEW dict. Originals and the on-disk cache are never mutated; nothing in
``mcp_server/`` is imported here.

Transforms take ``(date_map, as_of)`` and return a new dict.

Amendment note (8.33): the original uniform precipitation multipliers
(S.R1/R2/R3 = x0.80/x0.60/x1.30) were replaced. `mcp_server.risk_tool` computes the
drought index as SPI-1 by refitting its gamma reference distribution from the SAME
series, so any uniform rain multiplier is exactly scale-invariant (measured max
|delta drought_z| = 0.00 at x1.30) and never moves the oracle. The replacement arms
change the SHAPE/PHASE/INTENSITY of the series instead (dry spells, heavy-rain weeks,
onset shifts), which do move the standardized indices.
"""
from __future__ import annotations

from datetime import datetime, timedelta

ISO = "%Y-%m-%d"


def _add(delta: float):
    def transform(date_map, as_of):
        out = {}
        for d, rec in date_map.items():
            r = dict(rec)
            for k in ("tmean", "tmax", "tmin"):
                if r.get(k) is not None:
                    r[k] = float(r[k]) + delta
            out[d] = r
        return out

    return transform


def _window_heat(delta: float, window_days: int):
    """Add `delta` to temperatures only within [as_of, as_of+window_days): sowing-window heat."""
    def transform(date_map, as_of):
        start = datetime.strptime(as_of, ISO)
        end = start + timedelta(days=window_days)
        out = {}
        for d, rec in date_map.items():
            r = dict(rec)
            if start <= datetime.strptime(d, ISO) < end:
                for k in ("tmean", "tmax", "tmin"):
                    if r.get(k) is not None:
                        r[k] = float(r[k]) + delta
            out[d] = r
        return out

    return transform


def _dry_window(days: int, factor: float):
    """Scale precipitation by `factor` in [as_of-days, as_of-1] (a dry spell)."""
    def transform(date_map, as_of):
        a = datetime.strptime(as_of, ISO)
        out = {}
        for d, rec in date_map.items():
            r = dict(rec)
            if 0 < (a - datetime.strptime(d, ISO)).days <= days and r.get("precip") is not None:
                r["precip"] = float(r["precip"]) * factor
            out[d] = r
        return out

    return transform


def _wet_week(mm_pattern: list[float]):
    """Set the 7 forecast days [as_of, as_of+6] to the given precipitation pattern (mm)."""
    def transform(date_map, as_of):
        a = datetime.strptime(as_of, ISO)
        out = {}
        for d, rec in date_map.items():
            r = dict(rec)
            off = (datetime.strptime(d, ISO) - a).days
            if 0 <= off < len(mm_pattern):
                r["precip"] = float(mm_pattern[off])
            out[d] = r
        return out

    return transform


def _shift_rain(days: int):
    """Delay the daily precipitation series by `days` (rain that fell on d-`days` now falls on d)."""
    def transform(date_map, as_of):
        out = {}
        for d, rec in date_map.items():
            src = date_map.get((datetime.strptime(d, ISO) - timedelta(days=days)).strftime(ISO))
            r = dict(rec)
            r["precip"] = None if src is None else src.get("precip")
            out[d] = r
        return out

    return transform


def _compose(*transforms):
    def transform(date_map, as_of):
        dm = date_map
        for t in transforms:
            dm = t(dm, as_of)
        return dm

    return transform


def _identity(date_map, as_of):
    return {d: dict(rec) for d, rec in date_map.items()}


def _natural_year(year: int):
    """Substitute the same calendar day's real weather from `year` (in-cache observed data)."""
    def transform(date_map, as_of):
        out = {}
        for d, rec in date_map.items():
            dt = datetime.strptime(d, ISO)
            try:
                src_key = dt.replace(year=year).strftime(ISO)
            except ValueError:
                src_key = dt.replace(year=year, day=28).strftime(ISO)
            src = date_map.get(src_key)
            out[d] = dict(src) if src is not None else dict(rec)
        return out

    return transform


# ---------------------------------------------------------------------------
# Named perturbation sets (S_PERTURBATIONS.md v2 / PROTOCOL 8.33)
# ---------------------------------------------------------------------------
PERTURBATIONS: dict[str, dict] = {
    # temperature / warming
    "W1": {"label": "warm_near", "transform": _add(+1.0)},
    "W2": {"label": "warm_mid", "transform": _add(+2.0)},
    "W3": {"label": "warm_far_beyond", "transform": _add(+3.0)},
    "H1": {"label": "sowing_heat", "transform": _window_heat(+2.0, 21)},
    # precipitation shape (replaces the scale-invariant multipliers)
    "D1": {"label": "dry_spell_30d", "transform": _dry_window(30, 0.10)},
    "D2": {"label": "dry_spell_45d_severe", "transform": _dry_window(45, 0.05)},
    "WET1": {"label": "heavy_rain_week", "transform": _wet_week([60, 60, 60, 5, 5, 5, 5])},
    "WET2": {"label": "extreme_rain_week_beyond", "transform": _wet_week([90, 90, 90, 10, 10, 10, 10])},
    # rainfall phase (onset delay)
    "O1": {"label": "onset_late_2wk", "transform": _shift_rain(+14)},
    "O2": {"label": "onset_late_4wk_beyond", "transform": _shift_rain(+28)},
    # compound
    "C1": {"label": "hot_dry", "transform": _compose(_add(+2.0), _dry_window(30, 0.10))},
    # controls
    "N0": {"label": "identity_control", "transform": _identity},
    "N1": {"label": "cool_reverse_control", "transform": _add(-1.5)},
    # natural experiment
    "NE15": {"label": "natural_2015", "transform": _natural_year(2015)},
}

# Sets that require fresh model runs (N0 is harness-only).
RUN_SETS = ["W1", "W2", "W3", "H1", "D1", "D2", "WET1", "WET2", "O1", "O2", "C1", "N1"]
ALL_SETS = list(PERTURBATIONS.keys())
