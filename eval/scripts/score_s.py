"""S-series scorer (PROTOCOL 8.32 / 8.33). Offline, deterministic, NO model calls.

Computes the pre-registered metrics (Stale@5 primary; Violation@5, Shift@5,
Drop-faithful = 1 - Stale@5), the four pre-registered contrasts (C2a-C0b, C2b-C0b,
C2a-C1a, C3-C2b) with district-clustered bootstrap (N_RES/SEED = 10000/42) and
Holm correction across the four contrasts, per-protocol and ITT, WITH and WITHOUT
pilot_dev, STRICT (primary) and LENIENT (8.33.3 companion for D1/D2; reported for
all arms per S_ORACLE.md section 2), per-set and pooled, plus the pre-scoring sanity
checks (prompt hashes, N0 identity, coverage, chain-of-custody) and controls
(false-change rates, N1 direction, tool-output overlap).

Outputs:
  eval/results/s_scores.json         aggregates + contrasts + controls (flat keys)
  eval/results/s_scores_cells.csv    one row per (model,set,sid,condition,mode)
  eval/results/s_sanity.json         sanity checks, pass/fail with detail
  stdout                            short summary

Run:  py -3 eval/scripts/score_s.py
Tests: eval/tests/test_s_metrics.py imports the metric functions from THIS file.
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.s_series import base_set, oracle  # noqa: E402
from eval.s_series.perturbations import PERTURBATIONS  # noqa: E402
from eval.llm import prompts as P  # noqa: E402
from eval.statistics import holm_bonferroni as holm  # noqa: E402

OUT = ROOT / "eval/results"
RUNS = ROOT / "eval/runs"
EVID = RUNS / "s_evidence"
ARCH_EVID = RUNS / "archive_v2/evidence"

SEED = 42
N_RES = 10000
MODELS = ["llama", "nemotron"]
MODEL_IDS = {"nemotron": "nvidia/nemotron-3-ultra-550b-a55b",
             "llama": "meta/llama-3.2-11b-vision-instruct"}
MODEL_SHORT = {"llama": "llama-3.2-11b", "nemotron": "nemotron-3-ultra"}
CONDS = ["C0", "C0b", "C1a", "C2a", "C2b", "C3"]
TOOL_CONDS = ["C1a", "C2a", "C2b"]
# frozen tool lists, source of truth eval/scripts/run_s_series.py L48-49
FIVE_TOOLS = ["weather_tool", "climate_tool", "season_tool", "risk_tool",
              "get_soil_by_coordinates"]
SIX_TOOLS = FIVE_TOOLS + ["crop_score"]
CONTRASTS = [("C2a", "C0b"), ("C2b", "C0b"), ("C2a", "C1a"), ("C3", "C2b")]
METRICS = ["stale", "violation", "shift", "drop"]
MODES = ["strict", "lenient"]
LENIENT_ARMS = {"D1", "D2"}  # 8.33.3 pre-specified companion analysis
WARM_POOL = ["W1", "W2", "W3", "H1", "C1"]
DRY_POOL = ["D1", "D2"]
TOOLS_TO_BUNDLE = {"weather_tool": "weather", "climate_tool": "climate",
                   "season_tool": "season", "get_soil_by_coordinates": "soil",
                   "risk_tool": "risk", "crop_score": "crop_score"}
# BEFORE-1 recorded hashes of the frozen/pre-registered inputs (2026-10-18)
EXPECTED_SHA256 = {
    "eval/s_series/oracle.py":
        "55d6eed98b1089d72d534861c7d6b36c4b926e8d4d4a75bf5b330edd7242c9d6",
    "eval/s_series/perturbations.py":
        "f9644a6832b4ee4cb55e219a67f3763db6bfb6c4ba0e00077100e58b8546758d",
    "eval/data/series/s_heatwave_constraints_v1.0.csv":
        "9268da6a8b7064dfc8b3787ea007627f87ab243298066772d768bef0ded82af8",
    "eval/data/ground_truth/crop_season_table_v1.2.csv":
        "2d44c97ec1641c2dbec1c4236bd0de80b4de674c5682f74b5eb4fb2b77ff1ddd",
    "eval/data/ground_truth/crop_season_table_v1.1.csv":
        "3a26766d355f1e3c8a945dc5b975fb955d194768025213b42f326ba8d70516d5",
    "eval/data/ground_truth/hard_constraints_v1.1.csv":
        "bb48c4989f8b51e0a42c7ea12735b8665fabaa0fed88c0f6dfad47cccf093eb3",
}


# ---------------------------------------------------------------- metric funcs
def jaccard(a, b) -> float:
    A, B = set(a), set(b)
    if not A and not B:
        return 0.0
    u = A | B
    return len(A & B) / len(u) if u else 0.0


def stale_at5(top5, F0, F1) -> float:
    r"""|top5 ∩ D| / |D| with D = F0 \ F1; 0 when |D| == 0 (registered convention)."""
    D = set(F0) - set(F1)
    if not D:
        return 0.0
    return len(set(top5) & D) / len(D)


def drop_at5(top5, F0, F1) -> float:
    return 1.0 - stale_at5(top5, F0, F1)


def violation_at5(top5, F1) -> float:
    r"""|top5 ∩ (U \ F1)| / min(5, |top5|); 0 when top5 empty."""
    t = list(top5)[:5]
    if not t:
        return 0.0
    Fs = set(F1)
    return sum(1 for c in t if c not in Fs) / len(t)


def shift_at5(top5_base, top5_p) -> float:
    if not top5_base and not top5_p:
        return 0.0          # both empty: no observed change
    return 1.0 - jaccard(top5_base, top5_p)


def metric_value(name: str, top5, top5_base, F0, F1) -> float:
    if name == "stale":
        return stale_at5(top5, F0, F1)
    if name == "violation":
        return violation_at5(top5, F1)
    if name == "shift":
        return shift_at5(top5_base, top5)
    if name == "drop":
        return drop_at5(top5, F0, F1)
    raise ValueError(name)


def worst_value(name: str, has_D: bool) -> float:
    """ITT worst case for an unusable cell (registered: report pp AND ITT)."""
    if name == "stale":
        return 1.0 if has_D else 0.0
    if name == "drop":
        return 0.0 if has_D else 1.0
    return 1.0  # violation, shift


# ------------------------------------------------------------ records/helpers
def top5_of(rec) -> list[str]:
    if not rec or rec.get("error"):
        return []
    p = rec.get("parsed") or {}
    return [str(x).strip() for x in (p.get("top5") or [])][:5]


def usable(rec) -> bool:
    if rec is None or rec.get("error"):
        return False
    p = rec.get("parsed") or {}
    return bool(p.get("valid_json")) and not rec.get("truncated")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prompt_key(model_id: str, cond: str, prompt: str, sid: str, rep: int = 0,
               sep: str = "\x1f") -> str:
    """S runs (run_s_series) use sep='\\x1f'; canonical runs (run_model family)
    use sep='\\u241f' (U+241F). Callers must pass the right separator."""
    return hashlib.sha256(
        sep.join([model_id, cond, prompt, sid, str(rep)]).encode()
    ).hexdigest()


def _coerce_digit_keys(x):
    """Climate month dicts are served with int keys but round-trip through
    JSON as digit strings, flipping the sort_keys order of the hash."""
    if isinstance(x, dict):
        return {(int(k) if isinstance(k, str) and k.isdigit() else k):
                _coerce_digit_keys(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_coerce_digit_keys(v) for v in x]
    return x


def bundle_tool_hashes(bundle: dict, tool_name: str) -> tuple[str, str]:
    """(direct hash, digit-key-coerced hash); runtime may serve either form."""
    key = TOOLS_TO_BUNDLE.get(tool_name)
    if key is None or key not in bundle:
        return ("", "")
    def _h(x):
        return hashlib.sha256(
            json.dumps(x, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()[:16]
    return (_h(bundle[key]), _h(_coerce_digit_keys(bundle[key])))


# ------------------------------------------------------------- bootstrap/CI
_IDX_CACHE: dict[int, np.ndarray] = {}


def _resample_idx(k: int) -> np.ndarray:
    if k not in _IDX_CACHE:
        rng = np.random.default_rng(SEED)
        _IDX_CACHE[k] = rng.integers(0, k, size=(N_RES, k))
    return _IDX_CACHE[k]


def cluster_stats(by_district: dict[str, list[float]]) -> dict:
    """District-clustered bootstrap mean/CI + centered-null p (real_eval pattern)."""
    keys = sorted(by_district)
    if not keys:
        return {"mean": 0.0, "lo": 0.0, "hi": 0.0, "p": 1.0, "n": 0, "k": 0}
    sums = np.array([np.sum(by_district[k]) for k in keys], float)
    cnts = np.array([len(by_district[k]) for k in keys], float)
    obs = float(np.concatenate([np.asarray(by_district[k], float)
                                for k in keys]).mean())
    idx = _resample_idx(len(keys))
    boot = sums[idx].sum(1) / cnts[idx].sum(1)
    lo, hi = (float(x) for x in np.percentile(boot, [2.5, 97.5]))
    cs = sums - cnts * obs
    cb = cs[idx].sum(1) / cnts[idx].sum(1)
    p = max(float((np.abs(cb) >= abs(obs)).mean()), 1.0 / N_RES)
    return {"mean": obs, "lo": lo, "hi": hi, "p": p,
            "n": int(cnts.sum()), "k": len(keys)}


# ------------------------------------------------------------------ loaders
def run_sets() -> list[str]:
    found = set()
    for d in RUNS.glob("s_*/eval_*/results.json"):
        s = d.parent.parent.name[2:]
        if s in PERTURBATIONS:
            found.add(s)
    return [s for s in PERTURBATIONS if s in found]


def load_pert_records(set_name: str, model_key: str):
    """{(cond, sid): record}, repeat==0, duplicates resolved preferring non-error."""
    fp = RUNS / f"s_{set_name}" / f"eval_{MODEL_SHORT[model_key]}" / "results.json"
    out: dict[tuple[str, str], dict] = {}
    if not fp.exists():
        return out, 0, 0
    raw = json.loads(fp.read_text(encoding="utf-8"))
    ok_dups = 0
    for r in raw:
        if r.get("repeat", 0) != 0:
            continue
        k = (r["condition"], r["scenario_id"])
        prev = out.get(k)
        if prev is None:
            out[k] = r
            continue
        both_ok = not prev.get("error") and not r.get("error")
        if both_ok:
            ok_dups += 1
        if prev.get("error") and not r.get("error"):
            out[k] = r
    n_err_left = sum(1 for r in out.values() if r.get("error"))
    return out, ok_dups, n_err_left


def read_bundle(set_name: str, sid: str) -> dict | None:
    p = EVID / set_name / f"{sid}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def load_archive(sid: str) -> dict:
    return json.loads((ARCH_EVID / f"{sid}.json").read_text(encoding="utf-8"))


def enrich_baseline(model_key: str, sids: list[str]) -> dict:
    """Scoring-time bug fix (bug log 2026-10-19, offline, no model call).

    For nemotron the C0/C0b run cache holds unusable records for a few base
    sids while the canonical NFC runs (full_nemotron-3-ultra_*) hold usable
    copies of the same prompts. Replace unusable records with the first
    usable copy found across run stores (deterministic: sorted scan order).
    Prompt identity is still checked against the ORIGINAL records in the
    C0/C0b invariance check (NFC prompt_hash fields are sometimes blank)."""
    recs = dict(base_set.load_base_records(model_key))
    if model_key != "nemotron":
        return recs
    want = {(c, sid) for c in ("C0", "C0b") for sid in sids
            if not usable(recs.get((c, sid)))}
    if not want:
        return recs
    for run_dir in sorted(RUNS.glob("*")):
        fp = run_dir / "results.json"
        if not fp.exists():
            continue
        try:
            raw = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(raw, list):
            continue
        for r in raw:
            if not isinstance(r, dict) or r.get("repeat", 0) != 0:
                continue
            if r.get("condition") not in ("C0", "C0b"):
                continue
            if "nemotron" not in str(r.get("model", "")):
                continue
            k = (r["condition"], r["scenario_id"])
            if k in want and usable(r):
                recs[k] = r
                want.discard(k)
        if not want:
            break
    return recs


def ranked_top5(bundle: dict) -> list[str]:
    rc = (bundle.get("crop_score") or {}).get("ranked_crops") or []
    return [str(r.get("crop")).strip() for r in rc[:5] if r.get("crop")]


def current_season(bundle: dict, fallback_as_of: str | None = None) -> str:
    season = bundle.get("season")
    if isinstance(season, dict) and season.get("current_season"):
        return season["current_season"]
    if fallback_as_of:
        from mcp_server.season_tool import MONTH_TO_SEASON
        return MONTH_TO_SEASON[int(fallback_as_of[5:7])]
    raise ValueError("no season")


def blocked_crops(table: dict[str, str], mode: str) -> set[str]:
    return {c for c in oracle._CROPS if oracle._blocked(c, table, mode)}


# ------------------------------------------------------------------ analysis
def main() -> None:
    t0 = datetime.now(timezone.utc)
    checks: list[dict] = []

    def check(name: str, ok: bool, **detail):
        checks.append({"name": name, "status": "PASS" if ok else "FAIL", **detail})
        print(f"[{'PASS' if ok else 'FAIL'}] {name}"
              + (f" {json.dumps({k: v for k, v in detail.items() if k != 'detail'})}"
                 if detail else ""))

    # ---- 1. frozen oracle inputs unchanged -----------------------------------
    bad = {rel: sha256_file(ROOT / rel) for rel, exp in EXPECTED_SHA256.items()
           if sha256_file(ROOT / rel) != exp}
    check("oracle_input_sha256_unchanged", not bad, mismatches=bad)

    sids = base_set.select_base(40)
    meta = base_set.scenarios_by_id(sids)
    pilot_all = set(json.loads(
        (OUT / "pilot_scenario_sets.json").read_text(encoding="utf-8"))["pilot_union"])
    pilot_in_base = sorted(set(sids) & pilot_all)
    sets = run_sets()
    print(f"sets={sets}")
    print(f"sids={len(sids)} pilot_in_base={len(pilot_in_base)}")

    subsets = {"WITH_pilot": sids,
               "WITHOUT_pilot": [s for s in sids if s not in pilot_all]}

    # ---- 2. baseline records + coverage --------------------------------------
    base_hash_recs = {m: base_set.load_base_records(m) for m in MODELS}
    base_recs = {m: enrich_baseline(m, sids) for m in MODELS}
    base_top = {}
    for m in MODELS:
        for cond in CONDS[:5]:
            for sid in sids:
                if cond == "C3":
                    continue
                base_top[(m, cond, sid)] = top5_of(base_recs[m].get((cond, sid)))
    base_cov = {f"{m}|{c}": {
        "present": sum(1 for sid in sids
                       if base_recs[m].get((c, sid)) is not None),
        "usable": sum(1 for sid in sids
                      if usable(base_recs[m].get((c, sid))))}
        for m in MODELS for c in CONDS[:5]}
    check("baseline_canonical_extraction",
          all(v["present"] == len(sids) for v in base_cov.values()),
          coverage=base_cov)
    c3_base = {sid: base_set.load_c3(sid) for sid in sids}
    check("c3_baseline_nonempty", all(c3_base[sid] for sid in sids),
          n_empty=sum(1 for sid in sids if not c3_base[sid]))
    # registered C3 instrument: run_deterministic_v2 full_repo recomputed on
    # each arm's evidence (s_c3_recompute.py); see its module docstring for
    # the 2026-10-19 bug this replaced (bundle crop_score != det pipeline).
    c3_re = json.loads((OUT / "s_c3_full_repo.json").read_text(encoding="utf-8"))
    _c3bc = c3_re.get("base_check") or {}
    check("c3_recompute_reproduces_frozen_base_40",
          _c3bc.get("match") == len(sids) and not _c3bc.get("mismatch"),
          match=_c3bc.get("match"), n_mismatch=len(_c3bc.get("mismatch") or []))
    c3_miss = [f"{s}/{sid}" for s in sets + ["N0"] for sid in sids
               if not ((c3_re.get("sets") or {}).get(s) or {}).get(sid)
               .get("top5")]
    check("c3_recompute_complete_all_sets", not c3_miss,
          n_missing=len(c3_miss), missing=c3_miss[:5])

    # ---- 3. canonical C0/C0b prompt-hash invariance --------------------------
    # Checked against the ORIGINAL (un-enriched) records with the canonical
    # run separator U+241F; records written without a hash are unverifiable
    # but not mismatches (NFC duplicates sometimes carry prompt_hash='').
    ph_c0 = {"match": 0, "mismatch": [], "unverifiable": 0, "blank_sids": []}
    for m in MODELS:
        mid = MODEL_IDS[m]
        for cond in ("C0", "C0b"):
            builder = P.prompt_c0 if cond == "C0" else P.prompt_c0b
            for sid in sids:
                rec = base_hash_recs[m].get((cond, sid))
                if rec is None:
                    ph_c0["unverifiable"] += 1
                    ph_c0["blank_sids"].append(f"{m}|{cond}|{sid}|absent")
                    continue
                h = prompt_key(mid, cond, builder(meta[sid]), sid, sep="\u241f")
                if not rec.get("prompt_hash"):
                    ph_c0["unverifiable"] += 1
                    ph_c0["blank_sids"].append(f"{m}|{cond}|{sid}")
                elif rec["prompt_hash"] == h:
                    ph_c0["match"] += 1
                else:
                    ph_c0["mismatch"].append(f"{m}|{cond}|{sid}")
    check("c0_c0b_prompt_hash_invariance",
          not ph_c0["mismatch"] and ph_c0["match"] > 0,
          match=ph_c0["match"], unverifiable=ph_c0["unverifiable"],
          mismatch=ph_c0["mismatch"][:5])

    # ---- 4. per-set record loading + coverage + dedupe -----------------------
    pert: dict[tuple[str, str], dict] = {}   # (model,set) -> {(cond,sid): rec}
    coverage: dict[str, int] = {}
    dup_ok = 0
    left_err = 0
    no_c0_rerun = True
    for m in MODELS:
        for s in sets:
            recs, dups, errs = load_pert_records(s, m)
            pert[(m, s)] = recs
            dup_ok += dups
            left_err += errs
            if any(c in recs for c in ("C0", "C0b")):
                no_c0_rerun = False
            for cond in TOOL_CONDS:
                coverage[f"{m}|{s}|{cond}"] = {
                    "present": sum(1 for sid in sids
                                   if recs.get((cond, sid)) is not None),
                    "usable": sum(1 for sid in sids
                                  if usable(recs.get((cond, sid))))}
    # presence is the coverage gate; unusable cells are handled by the
    # registered pp/ITT pair (pp drops them, ITT assigns the worst case)
    present = sum(v["present"] for v in coverage.values())
    usable_n = sum(v["usable"] for v in coverage.values())
    reasons = Counter()
    for (m, s), recs in pert.items():
        for cond in TOOL_CONDS:
            for sid in sids:
                r = recs.get((cond, sid))
                if r is None:
                    reasons[f"{m}|missing"] += 1
                elif not usable(r):
                    if r.get("error"):
                        reasons[f"{m}|error"] += 1
                    elif not (r.get("parsed") or {}).get("valid_json"):
                        reasons[f"{m}|invalid_json"] += 1
                    else:
                        reasons[f"{m}|truncated"] += 1
    check("run_records_present",
          present == 3 * len(sets) * len(sids) * len(MODELS),
          present=present,
          expected=3 * len(sets) * len(sids) * len(MODELS),
          usable=usable_n, unusable=present - usable_n,
          unusable_reasons=dict(reasons))
    check("dedupe_no_duplicate_ok", dup_ok == 0, dup_ok=dup_ok)
    check("usable_after_audit", left_err == 0, error_cells_left=left_err)
    check("c0_c0b_not_rerun_reused_by_design", no_c0_rerun)

    # ---- 5. evidence bundles, oracle sets ------------------------------------
    arch = {sid: load_archive(sid) for sid in sids}
    season0 = {sid: current_season(arch[sid], meta[sid]["as_of_date"]) for sid in sids}
    bundles: dict[tuple[str, str], dict] = {}
    season_bad = []
    for s in sets:
        for sid in sids:
            b = read_bundle(s, sid)
            if b is None:
                continue
            bundles[(s, sid)] = b
            if current_season(b, meta[sid]["as_of_date"]) != season0[sid]:
                season_bad.append(f"{s}/{sid}")
    check("evidence_bundles_complete",
          len(bundles) == len(sets) * len(sids), n=len(bundles),
          expected=len(sets) * len(sids))
    check("season_invariant_across_sets", not season_bad, bad=season_bad[:5])

    # N0 (identity control) bundles join the oracle-set machinery so the
    # N0 stale control below can use F; N0 is not LLM-run and gets no cells.
    for sid in sids:
        b0 = read_bundle("N0", sid)
        if b0 is not None:
            bundles[("N0", sid)] = b0
    sets_f = sets + ["N0"]
    flags0 = {sid: oracle.flags_of(arch[sid]) for sid in sids}
    flags1 = {(s, sid): oracle.flags_of(bundles[(s, sid)])
              for s in sets_f for sid in sids if (s, sid) in bundles}
    F: dict[tuple[str, str, str], set] = {}
    for s in sets_f:
        for sid in sids:
            if (s, sid) not in bundles:
                continue
            for mode in MODES:
                F[(s, sid, mode)] = (
                    oracle.feasible_set(season0[sid], flags0[sid], mode),
                    oracle.feasible_set(season0[sid], flags1[(s, sid)], mode))
    n_D = {(s, sid, mode): len(F[(s, sid, mode)][0] - F[(s, sid, mode)][1])
           for s in sets_f for sid in sids if (s, sid) in bundles
           for mode in MODES}
    signal = {f"{s}|{mode}": {"n_sig": sum(1 for sid in sids if n_D[(s, sid, mode)]),
                              "sum_D": sum(n_D[(s, sid, mode)] for sid in sids)}
              for s in sets for mode in MODES}

    # ---- 6. prompt-hash invariance of the S runs ----------------------------
    ph_s = {"match": 0, "mismatch": [], "per": Counter()}
    ph_invar = {"checked": 0, "bad": []}
    for m in MODELS:
        mid = MODEL_IDS[m]
        for s in sets:
            recs = pert[(m, s)]
            for cond in TOOL_CONDS:
                for sid in sids:
                    rec = recs.get((cond, sid))
                    if rec is None:
                        continue
                    if cond == "C1a":
                        prompt = P.prompt_c1a(meta[sid], bundles[(s, sid)])
                    elif cond == "C2a":
                        prompt = P.prompt_c2(meta[sid], SIX_TOOLS)
                    else:
                        prompt = P.prompt_c2(meta[sid], FIVE_TOOLS)
                    h = prompt_key(mid, cond, prompt, sid)
                    if rec.get("prompt_hash") == h:
                        ph_s["match"] += 1
                    else:
                        ph_s["mismatch"].append(f"{m}|{s}|{cond}|{sid}")
                        ph_s["per"][f"{cond}"] += 1
                    if cond in ("C2a", "C2b"):
                        ph_invar["checked"] += 1
    # set-invariance of C2a/C2b prompt hashes across sets
    for m in MODELS:
        for cond in ("C2a", "C2b"):
            for sid in sids:
                hs = {pert[(m, s)].get((cond, sid), {}).get("prompt_hash")
                      for s in sets}
                hs.discard(None)
                if len(hs) > 1:
                    ph_invar["bad"].append(f"{m}|{cond}|{sid}")
    check("s_run_prompt_hash_recomputation", not ph_s["mismatch"],
          match=ph_s["match"], mismatch=ph_s["mismatch"][:5],
          by_cond=dict(ph_s["per"]))
    check("c2a_c2b_prompt_set_invariant", not ph_invar["bad"],
          bad=ph_invar["bad"][:5])

    # ---- 7. chain of custody: model saw exactly the frozen bundle -----------
    coc = {"checked": 0, "match": 0, "bad": []}
    for m in MODELS:
        for s in sets:
            for sid in sids:
                for cond in ("C2a", "C2b"):
                    rec = pert[(m, s)].get((cond, sid))
                    if not rec or rec.get("error"):
                        continue
                    b = bundles[(s, sid)]
                    for e in rec.get("tool_log") or []:
                        tn = e.get("name")
                        if tn not in TOOLS_TO_BUNDLE:
                            continue
                        coc["checked"] += 1
                        h_direct, h_coerced = bundle_tool_hashes(b, tn)
                        if e.get("output_hash") in (h_direct, h_coerced):
                            coc["match"] += 1
                        else:
                            coc["bad"].append(f"{m}|{s}|{cond}|{sid}|{tn}")
    check("tool_output_chain_of_custody",
          coc["checked"] > 0 and not coc["bad"],
          checked=coc["checked"], match=coc["match"], bad=coc["bad"][:5])

    # ---- 8. canonical crops inside oracle universe --------------------------
    univ = set(oracle.crops())
    missing = sorted(set(P.CANONICAL_CROPS) - univ)
    check("canonical_crops_within_oracle_universe", not missing, missing=missing)

    # ---- 9. N0 identity control (offline; N0 not LLM-run) -------------------
    n0 = {sid: read_bundle("N0", sid) for sid in sids}
    n0_fields = Counter()
    n0_bad = []
    for sid in sids:
        b = n0.get(sid)
        if b is None:
            n0_bad.append(f"{sid}|missing")
            continue
        for f in ("risk", "weather", "climate", "soil", "season", "crop_score"):
            if b.get(f) != arch[sid].get(f):
                n0_bad.append(f"{sid}|{f}")
                n0_fields[f] += 1
    n0_top5 = {sid: (((c3_re.get("sets") or {}).get("N0") or {}).get(sid)
                     or {}).get("top5") or [] for sid in sids}
    n0_shift = {sid: shift_at5(c3_base[sid], n0_top5[sid]) for sid in sids}
    n0_stale = {sid: stale_at5(c3_base[sid],
                               F[("N0", sid, "strict")][0],
                               F[("N0", sid, "strict")][1]) for sid in sids}
    n0_D = [n_D[("N0", sid, mode)] for sid in sids for mode in MODES
            if ("N0", sid, mode) in n_D]
    check("n0_evidence_identity_vs_archive", not n0_bad, bad=n0_bad[:5],
          differing_fields=dict(n0_fields))
    check("n0_shift_control_shift5_zero",
          max(n0_shift.values()) == 0.0, max_shift=max(n0_shift.values()))
    check("n0_oracle_no_signal_strict_and_lenient",
          all(d == 0 for d in n0_D),
          max_D=(max(n0_D) if n0_D else None), n=len(n0_D))
    check("n0_stale_equals_base",
          all(v == 0.0 for v in n0_stale.values()),
          max_stale=max(n0_stale.values()))

    # ---- 10. cell construction ----------------------------------------------
    cells: dict[tuple, dict] = {}   # (model,set,sid,cond,mode) -> cell
    for m in MODELS:
        for s in sets:
            recs = pert[(m, s)]
            for cond in CONDS:
                for sid in sids:
                    reused = cond in ("C0", "C0b")
                    if reused:
                        rec = base_recs[m].get((cond, sid))
                        top5 = top5_of(rec)
                        us = usable(rec)
                        t_base = list(top5)
                        us_shift = us          # t_base comes from the same rec
                    elif cond == "C3":
                        rec = None
                        c3arm = (((c3_re.get("sets") or {}).get(s) or {})
                                 .get(sid) or {})
                        top5 = [str(x).strip()
                                for x in (c3arm.get("top5") or [])]
                        us = bool(top5) and not c3arm.get("error")
                        t_base = list(c3_base[sid])
                        us_shift = us and bool(t_base)
                    else:
                        rec = recs.get((cond, sid))
                        top5 = top5_of(rec)
                        us = usable(rec)
                        b_rec = base_recs[m].get((cond, sid))
                        t_base = top5_of(b_rec)
                        # Shift@5 needs the canonical baseline top5 too
                        us_shift = us and usable(b_rec)
                    for mode in MODES:
                        F0, F1 = F[(s, sid, mode)]
                        d = n_D[(s, sid, mode)]
                        vals = {k: metric_value(k, top5, t_base, F0, F1)
                                for k in METRICS}
                        cells[(m, s, sid, cond, mode)] = {
                            "model": m, "set": s, "sid": sid, "cond": cond,
                            "mode": mode, "district": meta[sid]["district"],
                            "season": season0[sid],
                            "season_stratum": meta[sid]["season_stratum"],
                            "pilot": sid in pilot_all, "reused": reused,
                            "usable": us, "usable_shift": us_shift, "n_D": d,
                            "top5_base": t_base, "top5": top5, **vals}

    # ---- 11. levels ----------------------------------------------------------
    # metric-aware usability: only Shift@5 consumes the baseline top5, so a
    # missing/unusable canonical baseline excludes the cell for shift only.
    def cell_ok(c: dict, metric: str) -> bool:
        return c["usable_shift"] if metric == "shift" else c["usable"]

    scopes = ["__pooled__"] + sets
    season_scopes = ["Kharif", "Rabi", "Zaid"]
    levels: dict[str, dict] = {}

    def level_key(model, subset, analysis, scope, mode, cond, metric):
        return f"{model}|{subset}|{analysis}|{scope}|{mode}|{cond}|{metric}"

    for model in MODELS:
        for subset, sids_sub in subsets.items():
            sid_set = set(sids_sub)
            for analysis in ("pp", "itt"):
                for scope in scopes:
                    use_sets = sets if scope == "__pooled__" else [scope]
                    for mode in MODES:
                        for cond in CONDS:
                            for metric in METRICS:
                                by_d: dict[str, list[float]] = defaultdict(list)
                                for s in use_sets:
                                    for sid in sids_sub:
                                        c = cells[(model, s, sid, cond, mode)]
                                        if not cell_ok(c, metric):
                                            if analysis == "itt":
                                                by_d[c["district"]].append(
                                                    worst_value(metric, c["n_D"] > 0))
                                            continue
                                        by_d[c["district"]].append(c[metric])
                                levels[level_key(model, subset, analysis, scope,
                                                 mode, cond, metric)] = cluster_stats(by_d)
                for season in season_scopes:
                    for mode in MODES:
                        for cond in CONDS:
                            for metric in METRICS:
                                by_d = defaultdict(list)
                                for s in sets:
                                    for sid in sids_sub:
                                        c = cells[(model, s, sid, cond, mode)]
                                        if c["season_stratum"] != season:
                                            continue
                                        if not cell_ok(c, metric):
                                            if analysis == "itt":
                                                by_d[c["district"]].append(
                                                    worst_value(metric, c["n_D"] > 0))
                                            continue
                                        by_d[c["district"]].append(c[metric])
                                levels[level_key(model, subset, analysis,
                                                 f"season:{season}", mode, cond,
                                                 metric)] = cluster_stats(by_d)

    # ---- 12. contrasts -------------------------------------------------------
    contrasts: dict[str, dict] = {}
    fam: dict[str, list[str]] = defaultdict(list)
    for model in MODELS:
        for subset, sids_sub in subsets.items():
            for analysis in ("pp", "itt"):
                for scope in scopes:
                    use_sets = sets if scope == "__pooled__" else [scope]
                    for mode in MODES:
                        for metric in METRICS:
                            keys = []
                            for a, b in CONTRASTS:
                                by_d = defaultdict(list)
                                av, bv = [], []
                                for s in use_sets:
                                    for sid in sids_sub:
                                        ca = cells[(model, s, sid, a, mode)]
                                        cb = cells[(model, s, sid, b, mode)]
                                        ca_ok = cell_ok(ca, metric)
                                        cb_ok = cell_ok(cb, metric)
                                        if not (ca_ok and cb_ok):
                                            if analysis == "itt":
                                                va = (ca[metric] if ca_ok else
                                                      worst_value(metric,
                                                                  ca["n_D"] > 0))
                                                vb = (cb[metric] if cb_ok else
                                                      worst_value(metric,
                                                                  cb["n_D"] > 0))
                                                by_d[ca["district"]].append(va - vb)
                                                av.append(va)
                                                bv.append(vb)
                                            continue
                                        va, vb = ca[metric], cb[metric]
                                        by_d[ca["district"]].append(va - vb)
                                        av.append(va)
                                        bv.append(vb)
                                st = cluster_stats(by_d)
                                st["pair"] = f"{a}-{b}"
                                k = (f"{model}|{subset}|{analysis}|{scope}|{mode}"
                                     f"|{metric}|{a}-{b}")
                                contrasts[k] = st
                                keys.append(k)
                            fam[f"{model}|{subset}|{analysis}|{scope}|{mode}|{metric}"] = keys
    for family, keys in fam.items():
        adj = holm([contrasts[k].get("p", 1.0) for k in keys])
        for k, pa in zip(keys, adj):
            contrasts[k]["holm"] = float(pa)

    # ---- 13. controls / breakdowns ------------------------------------------
    # false-change: Shift@5 > 0 on cells where the oracle did not move (|D|=0)
    false_change: dict[str, dict] = {}
    for model in MODELS:
        for s in sets:
            for cond in CONDS:
                n0d = n0c = 0
                for sid in sids:
                    if s == "N0":
                        continue
                    c = cells[(model, s, sid, cond, "strict")]
                    if c["n_D"] > 0:
                        continue
                    if not c["usable_shift"]:
                        continue
                    n0d += 1
                    if c["shift"] > 0:
                        n0c += 1
                false_change[f"{model}|{s}|{cond}"] = {
                    "n_no_signal": n0d, "n_changed": n0c,
                    "rate": (n0c / n0d) if n0d else None}

    # tool-output overlap: top5 vs frozen crop_score ranked list
    tool_overlap: dict[str, dict] = {}
    for model in MODELS:
        for s in sets:
            for cond in ("C1a", "C2a", "C2b"):
                fr, n = 0.0, 0
                for sid in sids:
                    c = cells[(model, s, sid, cond, "strict")]
                    if not c["usable"] or not c["top5"]:
                        continue
                    ranked = set(ranked_top5(bundles[(s, sid)]))
                    fr += len(set(c["top5"]) & ranked) / len(c["top5"])
                    n += 1
                tool_overlap[f"{model}|{s}|{cond}"] = {
                    "mean_overlap": (fr / n) if n else None, "n": n}

    # N1 direction-reversal control (operationalisation stated in S_REPORT):
    # signed change in the share of blocked crops in top5 vs the base column.
    heat_cited = blocked_crops(oracle._HEATWAVE, "strict")
    drought_all = blocked_crops(oracle._DROUGHT, "lenient")
    direction: dict[str, dict] = {}
    for model in MODELS:
        for s in sets:
            for cond in TOOL_CONDS + ["C3"]:
                for kind, block in (("heat_cited", heat_cited),
                                    ("drought_lenient", drought_all)):
                    ds = []
                    for sid in sids:
                        c = cells[(model, s, sid, cond, "strict")]
                        if not c["usable_shift"] or not c["top5"] or not block:
                            continue
                        base_t = c["top5_base"]
                        sh1 = (len(set(c["top5"]) & block) / min(5, len(c["top5"]))
                               if c["top5"] else 0.0)
                        sh0 = (len(set(base_t) & block) / min(5, len(base_t))
                               if base_t else 0.0)
                        ds.append(sh1 - sh0)
                    direction[f"{model}|{s}|{cond}|{kind}"] = {
                        "mean_delta": (float(np.mean(ds)) if ds else None),
                        "n": len(ds)}
    n1_oracle = {"strict_sig": signal.get("N1|strict"),
                 "lenient_sig": signal.get("N1|lenient"),
                 "expect": "D = {} for all 40 (S_PERTURBATIONS_V2 line 44)"}
    n1_model = {}
    for model in MODELS:
        for kind in ("heat_cited", "drought_lenient"):
            warm = [direction[f"{model}|{s}|C2a|{kind}"]["mean_delta"]
                    for s in WARM_POOL if f"{model}|{s}|C2a|{kind}" in direction]
            dry = [direction[f"{model}|{s}|C2a|{kind}"]["mean_delta"]
                   for s in DRY_POOL if f"{model}|{s}|C2a|{kind}" in direction]
            n1 = direction.get(f"{model}|N1|C2a|{kind}", {}).get("mean_delta")
            ref = [x for x in (warm if kind == "heat_cited" else dry) if x is not None]
            n1_model[f"{model}|{kind}"] = {
                "n1_C2a_delta": n1,
                "warm_pool_mean": (float(np.mean(warm)) if warm else None),
                "dry_pool_mean": (float(np.mean(dry)) if dry else None),
                "reversal_ok": bool(ref and n1 is not None
                                    and n1 > float(np.mean(ref)))}

    # ---- 14. write outputs ---------------------------------------------------
    now = datetime.now(timezone.utc).isoformat()
    OUT.mkdir(parents=True, exist_ok=True)
    cells_csv = OUT / "s_scores_cells.csv"
    cols = ["model", "set", "sid", "district", "season", "season_stratum",
            "condition", "mode", "pilot", "reused", "usable", "usable_shift",
            "n_D", "stale", "violation", "shift", "drop", "top5_base", "top5"]
    with cells_csv.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for key in sorted(cells):
            c = cells[key]
            w.writerow([c["model"], c["set"], c["sid"], c["district"],
                        c["season"], c["season_stratum"], c["cond"], c["mode"],
                        int(c["pilot"]), int(c["reused"]), int(c["usable"]),
                        int(c["usable_shift"]),
                        c["n_D"], f"{c['stale']:.6f}", f"{c['violation']:.6f}",
                        f"{c['shift']:.6f}", f"{c['drop']:.6f}",
                        "|".join(c["top5_base"]), "|".join(c["top5"])])

    sanity = {"generated": now, "checks": checks,
              "c3_recompute": {"pipeline": c3_re.get("pipeline"),
                               "base_check": c3_re.get("base_check"),
                               "n_missing": len(c3_re.get("missing") or []),
                               "n_errors": len(c3_re.get("errors") or [])},
              "prompt_hash": {"c0_c0b": ph_c0, "s_runs": {k: v for k, v in ph_s.items()
                                                          if k != "per"},
                              "s_runs_by_cond": dict(ph_s["per"]),
                              "set_invariance": ph_invar},
              "chain_of_custody": coc, "n0_shift_max": max(n0_shift.values())}
    (OUT / "s_sanity.json").write_text(json.dumps(sanity, indent=2),
                                       encoding="utf-8")

    scores = {
        "meta": {"generated": now, "seed": SEED, "n_res": N_RES,
                 "run_sets": sets, "n_sids": len(sids),
                 "pilot_in_base": pilot_in_base,
                 "n_pilot_in_base": len(pilot_in_base),
                 "models": MODELS, "contrasts": [f"{a}-{b}" for a, b in CONTRASTS],
                 "metrics": METRICS, "modes": MODES,
                 "note_pp_itt": "pp excludes unusable cells; ITT assigns the "
                                "registered worst case (they differ here because "
                                "some cells are unusable); Shift@5 additionally "
                                "requires a usable canonical baseline top5",
                 "note_c3_instrument": "C3 advice = run_deterministic_v2 "
                                        "full_repo pipeline recomputed per arm "
                                        "(eval/results/s_c3_full_repo.json); the "
                                        "MCP crop_score tool output stored in "
                                        "bundles is a separate implementation "
                                        "(17/40 base disagreement) used only for "
                                        "C2a chain-of-custody and tool-overlap",
                 "duration_s": round((datetime.now(timezone.utc) - t0).total_seconds(), 1)},
        "signal": signal,
        "levels": levels,
        "contrasts": contrasts,
        "false_change": false_change,
        "tool_overlap": tool_overlap,
        "n1_direction": {"per_cell": direction, "oracle": n1_oracle,
                         "model_C2a": n1_model,
                         "operationalisation": "signed change of blocked-crop "
                                               "share in top5 vs base; chosen at "
                                               "scoring time (8.32.5 not further "
                                               "specified); disclosed in S_REPORT"},
        "coverage": coverage,
        "n_checks_passed": sum(1 for c in checks if c["status"] == "PASS"),
        "n_checks_failed": sum(1 for c in checks if c["status"] == "FAIL"),
    }
    (OUT / "s_scores.json").write_text(json.dumps(scores, indent=2),
                                       encoding="utf-8")

    print(f"\nchecks: {scores['n_checks_passed']} PASS / "
          f"{scores['n_checks_failed']} FAIL")
    print("\nHEADLINE (pooled, WITH_pilot, pp, strict, Stale@5):")
    for model in MODELS:
        for cond in CONDS:
            k = level_key(model, "WITH_pilot", "pp", "__pooled__", "strict",
                          cond, "stale")
            st = levels[k]
            print(f"  {model:9s} {cond:4s} mean={st['mean']:.3f} "
                  f"CI=[{st['lo']:.3f},{st['hi']:.3f}] p={st['p']:.4g} n={st['n']}")
    print("\nCONTRASTS (pooled, WITH_pilot, pp, strict, Stale@5):")
    for model in MODELS:
        for a, b in CONTRASTS:
            k = (f"{model}|WITH_pilot|pp|__pooled__|strict|stale|{a}-{b}")
            st = contrasts[k]
            print(f"  {model:9s} {a}-{b}: d={st['mean']:+.3f} "
                  f"CI=[{st['lo']:+.3f},{st['hi']:+.3f}] p={st['p']:.4g} "
                  f"holm={st['holm']:.4g} n={st['n']}")
    print(f"\nwrote {cells_csv}")
    print(f"wrote {OUT / 's_sanity.json'}")
    print(f"wrote {OUT / 's_scores.json'}")


if __name__ == "__main__":
    main()
