"""STEP 1: build eval/results/master_long.csv (one row per scenario x model x condition x repeat).

Reads existing outputs only. Uses the FIXED normalize_crop so agreement metrics are recomputed
from top5_raw. Adds C3 (deterministic) rows for every evaluated scenario.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from eval.llm.prompts import ALIASES, CANONICAL_CROPS, normalize_crop
from eval.metrics import (CANONICAL_CROPS as M_CANON, jaccard_similarity,
                          season_validity_rate, hard_violation_rate,
                          accuracy_at_k, precision_at_k, recall_at_k, ndcg_at_k)

RUNS = {
    "nemotron": (ROOT / "eval/runs/full_nemotron-3-ultra_20261011_082444/results.json", "nemotron-3-ultra"),
    "llama": (ROOT / "eval/runs/eval_llama-3.2-11b/results.json", "llama-3.2-11b"),
    "glm": (ROOT / "eval/runs/eval_glm-5.3/results.json", "glm-5.3"),
}

def _read_pilot_ids():
    p = ROOT / "eval/results/pilot_scenario_sets.json"
    if p.exists():
        return set(json.load(open(p, encoding="utf-8"))["pilot_union"])
    return set()


PILOT_IDS = _read_pilot_ids()
EVID = ROOT / "eval/runs/archive_v2/evidence"       # risk flags (frozen v2)
DET = ROOT / "eval/runs/archive_v2/deterministic"   # C3 recommendation (frozen v2 grid; was adhoc/evidence)
CONDS = ["C0", "C0b", "C1", "C2"]


def old_normalize(name):
    if not name:
        return None
    key = re.sub(r"[^a-z0-9 ]", " ", name.strip().lower())
    key = re.sub(r"\s+", " ", key).strip()
    if key in ALIASES:
        return ALIASES[key]
    look = {c.lower(): c for c in CANONICAL_CROPS}
    return look.get(key)


_bcache = {}


def bundle(sid):
    if sid not in _bcache:
        _bcache[sid] = json.load(open(EVID / f"{sid}.json"))
    return _bcache[sid]


_dcache = {}


def grid(sid):
    if sid not in _dcache:
        _dcache[sid] = json.load(open(DET / f"{sid}.json"))
    return _dcache[sid]


def grid_c3(sid):
    return (grid(sid).get("ablations", {}).get("full_repo") or {}).get("top5") or []


def grid_season(sid):
    return grid(sid)["season"]


def canon_list(raws):
    out, oor = [], 0
    for raw in raws:
        c = normalize_crop(raw)
        if c is None:
            oor += 1
        else:
            out.append(c)
    return out[:5], oor


def buggy_oor(raws):
    return sum(1 for raw in raws if old_normalize(raw) is None)


def err_type(e):
    if not e:
        return ""
    e = str(e)
    if "504" in e or "Timeout" in e or "timed out" in e.lower():
        return "gateway_timeout"
    if "getaddrinfo" in e or "Name or service" in e:
        return "dns"
    if "10054" in e or "connection" in e.lower():
        return "connection_reset"
    if "Max tool" in e or "round" in e.lower():
        return "max_tool_rounds"
    return "other"


def risk_flags(b):
    r = b.get("risk", {})
    return {
        "drought": (r.get("drought_probability") or 0) >= 0.5,
        "flood": (r.get("flood_probability") or 0) >= 0.5,
        "heat": (r.get("heatwave_probability") or 0) >= 0.5,
    }


def main():
    meta = {}
    for line in open(ROOT / "eval/data/scenarios.jsonl", encoding="utf-8"):
        d = json.loads(line)
        meta[d["scenario_id"]] = d
    stress_ids = {json.loads(l)["scenario_id"] for l in open(ROOT / "eval/data/stress.jsonl", encoding="utf-8")}

    rows = []
    seen_scenarios = set()

    for m, (path, short) in RUNS.items():
        recs = json.load(open(path))
        # keep last non-error per key
        best = {}
        for r in recs:
            key = (r["scenario_id"], r["condition"], r.get("repeat", 0))
            r_ok = not r.get("error")
            if key not in best or (r_ok and best[key].get("error")):
                best[key] = r
        for (sid, cond, rep), r in best.items():
            seen_scenarios.add(sid)
            sc = meta[sid]
            b = bundle(sid)
            season = grid_season(sid)
            c3 = grid_c3(sid)
            parsed = r.get("parsed") or {}
            raws = [str(x) for x in parsed.get("top5_raw", [])]
            top5, oor_fixed = canon_list(raws)
            valid_json = bool(parsed.get("valid_json"))
            b_oor = buggy_oor(raws)
            nraw = len(raws)
            flags = risk_flags(b)
            rows.append({
                "scenario_id": sid,
                "pilot_dev": int(sid in PILOT_IDS),
                "district": sc["district"],
                "season": season,
                "agro_climatic_zone": sc.get("agro_climatic_zone") or "",
                "stress": int(sid in stress_ids),
                "model": short,
                "condition": cond,
                "repeat": rep,
                "valid_json": int(valid_json),
                "truncated": "",
                "tool_calls": r.get("tool_calls") if isinstance(r.get("tool_calls"), int) else "",
                "tool_names": "",
                "season_valid": round(season_validity_rate(top5, season), 6),
                "hard_violation": round(hard_violation_rate(top5, season, flags), 6),
                "precision_at_5": "",
                "recall_at_5": "",
                "ndcg_at_5": "",
                "overlap_with_C3": round(jaccard_similarity(top5, c3), 6),
                "out_of_registry_pre": round(oor_fixed / nraw, 6) if nraw else "",
                "out_of_registry_post": round(sum(1 for c in top5 if c not in set(M_CANON)) / len(top5), 6) if top5 else "",
                "out_of_registry_buggy": round(b_oor / nraw, 6) if nraw else "",
                "latency_request_s": "",
                "latency_scenario_s": round(r.get("latency_s"), 3) if r.get("latency_s") is not None else "",
                "tokens_in": r.get("tokens_in") if r.get("tokens_in") is not None else "",
                "tokens_out": r.get("tokens_out") if r.get("tokens_out") is not None else "",
                "tokens_reasoning": r.get("reasoning_tokens") if r.get("reasoning_tokens") is not None else "",
                "error_type": err_type(r.get("error")),
                "top5": "|".join(top5),
                "c3_top5": "|".join(c3),
                "as_of_date": sc["as_of_date"],
                "month": sc["month"],
            })

    # C3 deterministic rows
    for sid in sorted(seen_scenarios):
        sc = meta[sid]
        b = bundle(sid)
        season = grid_season(sid)
        c3 = grid_c3(sid)
        flags = risk_flags(b)
        rows.append({
            "scenario_id": sid, "pilot_dev": int(sid in PILOT_IDS),
            "district": sc["district"], "season": season,
            "agro_climatic_zone": sc.get("agro_climatic_zone") or "",
            "stress": int(sid in stress_ids), "model": "C3", "condition": "C3", "repeat": 0,
            "valid_json": 1, "truncated": "", "tool_calls": "", "tool_names": "",
            "season_valid": round(season_validity_rate(c3, season), 6),
            "hard_violation": round(hard_violation_rate(c3, season, flags), 6),
            "precision_at_5": "", "recall_at_5": "", "ndcg_at_5": "",
            "overlap_with_C3": 1.0,
            "out_of_registry_pre": 0.0, "out_of_registry_post": 0.0, "out_of_registry_buggy": 0.0,
            "latency_request_s": "", "latency_scenario_s": "", "tokens_in": "", "tokens_out": "",
            "tokens_reasoning": "", "error_type": "",
            "top5": "|".join(c3), "c3_top5": "|".join(c3), "as_of_date": sc["as_of_date"], "month": sc["month"],
        })

    cols = list(rows[0].keys())
    out = ROOT / "eval/results/master_long.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"[master] rows={len(rows)} cols={len(cols)} -> {out}")
    from collections import Counter
    c = Counter((r["model"], r["condition"]) for r in rows)
    for k in sorted(c):
        print(f"  {k[0]:<10} {k[1]:<4} {c[k]}")


if __name__ == "__main__":
    main()