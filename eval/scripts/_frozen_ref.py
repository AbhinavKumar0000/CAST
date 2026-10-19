"""Frozen C3 reference accessors — the ONLY sanctioned C3 source for figures/results.

Authoritative C3 recommendation = eval/runs/archive_v2/deterministic (ablations.full_repo).
Risk flags = eval/runs/archive_v2/evidence.risk. The stale eval/runs/adhoc/evidence
`crop_score` bundles must NOT be used as a C3 source: they give Barley #1 in Rabi = 303
(vs 163 on the frozen grid) and agree with the frozen grid on top-1 for only 83.3% of
scenarios (see eval/results/stale_source_audit.json and PROTOCOL.md 8.13).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DET_DIR = ROOT / "eval/runs/archive_v2/deterministic"
EVID_DIR = ROOT / "eval/runs/archive_v2/evidence"


@lru_cache(maxsize=None)
def _det(sid: str) -> dict:
    with (DET_DIR / f"{sid}.json").open(encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=None)
def _evid(sid: str) -> dict:
    with (EVID_DIR / f"{sid}.json").open(encoding="utf-8") as fh:
        return json.load(fh)


def _full_repo(sid: str) -> dict:
    return (_det(sid).get("ablations") or {}).get("full_repo") or {}


def frozen_top5(sid: str) -> list[str]:
    return list(_full_repo(sid).get("top5") or [])


def frozen_top6(sid: str) -> list[str]:
    return list(_full_repo(sid).get("top6") or [])


def frozen_season(sid: str) -> str:
    return _det(sid).get("season") or ""


def frozen_risk(sid: str) -> dict:
    return _evid(sid).get("risk") or {}
