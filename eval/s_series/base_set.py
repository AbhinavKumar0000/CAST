"""S-series: base scenario set + canonical base-record loading.

Base set B = 40 scenarios, deterministically sampled (seed 42) from the 150-scenario
"common support" (scenarios where both nemotron and llama already have C1a/C2a/C2b in
the canonical runs), stratified across Kharif/Rabi/Zaid. Reusing the canonical base
records means the S run only has to produce the PERTURBED columns.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent

LLM_SUBSET = ROOT / "eval/data/llm_subset.jsonl"
PILOT = ROOT / "eval/results/pilot_scenario_sets.json"
NEMO_B1 = ROOT / "eval/runs/eval_nemotron-3-ultra/results.json"
NEMO_B2 = ROOT / "eval/runs/eval_nemotron-3-ultra_b2/results.json"
NEMO_CACHE = ROOT / "eval/cache/llm/nemotron-3-ultra"
LLAMA = ROOT / "eval/runs/eval_llama-3.2-11b/results.json"
DET_DIR = ROOT / "eval/runs/archive_v2/deterministic"
EVID_DIR = ROOT / "eval/runs/archive_v2/evidence"

SEASON_TARGET = {"Kharif": 13, "Rabi": 16, "Zaid": 11}  # 40 total, proportional


def load_subset() -> list[dict]:
    return [json.loads(l) for l in LLM_SUBSET.read_text(encoding="utf-8").splitlines() if l.strip()]


def common_support() -> list[str]:
    nemo = {
        r["scenario_id"]
        for r in json.loads(NEMO_B1.read_text(encoding="utf-8"))
        if r["condition"] in ("C1a", "C2a", "C2b")
    }
    llama = {
        r["scenario_id"]
        for r in json.loads(LLAMA.read_text(encoding="utf-8"))
        if r["condition"] in ("C1a", "C2a", "C2b")
    }
    return sorted(nemo & llama)


def select_base(n: int = 40, seed: int = 42) -> list[str]:
    subset = load_subset()
    season = {s["scenario_id"]: s["season_stratum"] for s in subset}
    common = common_support()
    rng = np.random.default_rng(seed)
    chosen: list[str] = []
    for season_name, target in SEASON_TARGET.items():
        pool = sorted(s for s in common if season.get(s) == season_name)
        pick = rng.choice(pool, size=min(target, len(pool)), replace=False)
        chosen.extend(sorted(pick.tolist()))
    if len(chosen) < n:
        rest = [s for s in common if s not in chosen]
        extra = rng.choice(sorted(rest), size=n - len(chosen), replace=False)
        chosen.extend(sorted(extra.tolist()))
    return sorted(chosen)


def scenarios_by_id(sids: list[str]) -> dict[str, dict]:
    want = set(sids)
    return {s["scenario_id"]: s for s in load_subset() if s["scenario_id"] in want}


def _usable(r: dict | None) -> bool:
    if r is None or r.get("error"):
        return False
    p = r.get("parsed") or {}
    return bool(p.get("valid_json")) and not r.get("truncated")


def load_base_records(model: str) -> dict[tuple[str, str], dict]:
    """Canonical unperturbed base records for model in {nemotron, llama}.

    nemotron: C1a/C2a/C2b from B1+B2; C0/C0b from the run cache.
    llama   : all conditions from eval_llama-3.2-11b/results.json.
    """
    by: dict[tuple[str, str], dict] = {}
    if model == "llama":
        for r in json.loads(LLAMA.read_text(encoding="utf-8")):
            if r.get("repeat", 0) == 0:
                by[(r["condition"], r["scenario_id"])] = r
        return by

    for src in (NEMO_B1, NEMO_B2):
        for r in json.loads(src.read_text(encoding="utf-8")):
            if r.get("repeat", 0) == 0 and r["condition"] in ("C1a", "C2a", "C2b"):
                by[(r["condition"], r["scenario_id"])] = r
    for fp in NEMO_CACHE.glob("*.json"):
        try:
            r = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        if (r.get("repeat", 0) == 0 and r.get("condition") in ("C0", "C0b")
                and (r["condition"], r["scenario_id"]) not in by):
            by[(r["condition"], r["scenario_id"])] = r
    return by


def load_c3(sid: str) -> list[str]:
    return (json.loads((DET_DIR / f"{sid}.json").read_text(encoding="utf-8"))
            .get("ablations", {}).get("full_repo") or {}).get("top5") or []


def load_evidence_flags(sid: str) -> dict[str, bool]:
    """Oracle flags (flood/drought/heatwave) from the archived base evidence bundle."""
    from eval.s_series.oracle import flags_of

    ev = json.loads((EVID_DIR / f"{sid}.json").read_text(encoding="utf-8"))
    return flags_of(ev.get("risk") or {})
