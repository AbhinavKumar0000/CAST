"""S-series offline oracle (PROTOCOL 8.32 / 8.33).

Defines, OFFLINE, the agronomic feasibility oracle used to score the S-series runs and
demonstrates it is independent of the system under test. It never reads crop_log.csv.

Inputs (frozen / new, none edited):
  * eval/data/ground_truth/crop_season_table_v1.2.csv   - crop x season validity
  * eval/data/ground_truth/hard_constraints_v1.1.csv    - season/flood/drought blocks
  * eval/data/series/s_heatwave_constraints_v1.0.csv    - NEW heatwave (temperature) blocks
    added in the 8.33 amendment so the warming arm has an oracle term.

Risk indicators come from the replays of ``mcp_server.risk_tool`` (flood_probability,
drought_z_score_30d, heatwave_probability), i.e. from the scenario weather, not model output.

The public API takes a single ``flags`` mapping to avoid positional-argument mistakes:
    flags = oracle.flags_of(bundle)            # {"flood": bool, "drought": bool, "heatwave": bool}
    F = oracle.feasible_set(season, flags, "strict")
"""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
GT = ROOT / "eval/data/ground_truth"
SEASON_TABLE = GT / "crop_season_table_v1.2.csv"

FLOOD_THRESHOLD = 0.40
DROUGHT_Z_THRESHOLD = -1.5
HEATWAVE_THRESHOLD = 0.35
ANNUAL = "Annual"


def _rows(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _load_season_table() -> dict[tuple[str, str], str]:
    out: dict[tuple[str, str], str] = {}
    for r in _rows(SEASON_TABLE):
        status = (r.get("status") or "").strip().lower()
        if status == "contradicted":
            continue
        key = (r["crop"].strip(), r["season"].strip())
        prev = out.get(key)
        if prev is None or (prev == "unverified" and status == "cited"):
            out[key] = status
    return out


def _constraints(*paths: Path) -> dict[str, dict[str, str]]:
    """Return {constraint_type: {crop: status}} over the given constraint files."""
    out: dict[str, dict[str, str]] = {}
    for p in paths:
        for r in _rows(p):
            ct = r["constraint_type"].strip()
            out.setdefault(ct, {})[r["crop"].strip()] = (r.get("status") or "").strip().lower()
    return out


_SEASON_TABLE = _load_season_table()
_CONS = _constraints(
    GT / "hard_constraints_v1.1.csv",
    ROOT / "eval/data/series/s_heatwave_constraints_v1.0.csv",
)
_FLOOD = _CONS.get("flood", {})
_DROUGHT = _CONS.get("drought", {})
_HEATWAVE = _CONS.get("heatwave", {})
_CROPS = sorted({c for (c, _) in _SEASON_TABLE})


def crops() -> list[str]:
    return list(_CROPS)


def flags_of(bundle: dict) -> dict[str, bool]:
    """Extract the three oracle flags from a tool evidence bundle (or a raw risk dict)."""
    risk = bundle.get("risk") if isinstance(bundle, dict) and "risk" in bundle else (bundle or {})

    def num(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return None

    dz = num(risk.get("drought_z_score_30d"))
    fp = num(risk.get("flood_probability"))
    hw = num(risk.get("heatwave_probability"))
    return {
        "flood": fp is not None and fp >= FLOOD_THRESHOLD,
        "drought": dz is not None and dz <= DROUGHT_Z_THRESHOLD,
        "heatwave": hw is not None and hw >= HEATWAVE_THRESHOLD,
    }


def season_valid(crop: str, season: str, mode: str) -> bool:
    status = _SEASON_TABLE.get((crop, season))
    if status is None:
        status = _SEASON_TABLE.get((crop, ANNUAL))
        if status is None:
            return False
    return status == "cited" if mode == "strict" else status in ("cited", "unverified")


def _blocked(crop: str, table: dict[str, str], mode: str) -> bool:
    status = table.get(crop)
    if status is None:
        return False
    return status == "cited" if mode == "strict" else status in ("cited", "unverified")


def feasible(crop: str, season: str, flags: dict[str, bool], mode: str) -> bool:
    if not season_valid(crop, season, mode):
        return False
    if flags.get("flood") and _blocked(crop, _FLOOD, mode):
        return False
    if flags.get("drought") and _blocked(crop, _DROUGHT, mode):
        return False
    if flags.get("heatwave") and _blocked(crop, _HEATWAVE, mode):
        return False
    return True


def feasible_set(season: str, flags: dict[str, bool], mode: str) -> set[str]:
    return {c for c in _CROPS if feasible(c, season, flags, mode)}
