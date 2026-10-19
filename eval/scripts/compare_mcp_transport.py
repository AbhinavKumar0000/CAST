"""Stage 2 (needs a live run): compare an MCP-transport C2a run against in-process C2a.

Reads two ``results.json`` files produced by ``run_model.py`` for the same scenarios
and condition:
  * in-process reference: ``eval/runs/eval_nemotron-3-ultra/results.json`` (B1), C2a
  * MCP candidate:        any run dir passed via ``--mcp-run`` (default
    ``eval/runs/eval_nemotron-3-ultra_mcp_c2a50/results.json``), C2a

Reports, over the intersection of scenario_ids:
  * per-scenario metric agreement: strict/lenient x PP/ITT for season-validity and
    hard-violation (uses the frozen GT tables + risk flags, same as the primary metrics);
  * Fidelity-to-C3 (top-5 Jaccard, top-1 agreement) for each transport;
  * top-5 set/order agreement, valid_json / truncated / unknown_tool / forced_final flags,
    tool_calls and latency distributions.

Writes eval/results/mcp_transport_comparison.json. Pure offline (reads two files).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sa = _load("stage_a_interim_metrics", "eval/scripts/stage_a_interim_metrics.py")

EVID_DIR = ROOT / "eval/runs/archive_v2/evidence"
DET_DIR = ROOT / "eval/runs/archive_v2/deterministic"
DEFAULT_INPROC = ROOT / "eval/runs/eval_nemotron-3-ultra/results.json"
DEFAULT_MCP = ROOT / "eval/runs/eval_nemotron-3-ultra_mcp_c2a50/results.json"
OUT = ROOT / "eval/results/mcp_transport_comparison.json"


def load_cond(path: Path, cond: str):
    by = {}
    for r in json.loads(path.read_text(encoding="utf-8")):
        if r.get("repeat", 0) == 0 and r.get("condition") == cond:
            by[r["scenario_id"]] = r
    return by


def usable(r):
    if r is None or r.get("error"):
        return False
    p = r.get("parsed") or {}
    return bool(p.get("valid_json")) and not r.get("truncated")


def top5(r):
    p = (r or {}).get("parsed") or {}
    return [str(x) for x in (p.get("top5") or [])]


def jaccard(a, b):
    sa_, sb_ = set(a), set(b)
    return 1.0 if not sa_ and not sb_ else len(sa_ & sb_) / len(sa_ | sb_)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--conditions", default="C2a")
    ap.add_argument("--inproc-run", default=str(DEFAULT_INPROC))
    ap.add_argument("--mcp-run", default=str(DEFAULT_MCP))
    args = ap.parse_args()

    mcp_path = Path(args.mcp_run)
    if not mcp_path.exists():
        raise SystemExit(f"MCP run not found: {mcp_path} (run Stage 2 first)")

    inproc = load_cond(Path(args.inproc_run), args.conditions)
    mcp = load_cond(mcp_path, args.conditions)
    if not mcp:
        raise SystemExit(f"No {args.conditions} records in {mcp_path}")

    subset = [json.loads(l) for l in (ROOT / "eval/data/llm_subset.jsonl")
              .read_text(encoding="utf-8").splitlines() if l.strip()]
    season = {s["scenario_id"]: s["season_stratum"] for s in subset}
    sids = sorted(set(inproc) & set(mcp))
    missing_inproc = sorted(set(mcp) - set(inproc))

    flags = {}
    c3 = {}
    for sid in sids:
        ev = json.loads((EVID_DIR / f"{sid}.json").read_text(encoding="utf-8"))
        risk = ev.get("risk") or {}
        try:
            flags[sid] = (float(risk.get("drought_z_score_30d", 0)) <= -1.5,
                          float(risk.get("flood_probability", 0)) >= 0.40)
        except (TypeError, ValueError):
            flags[sid] = (False, False)
        c3[sid] = (json.loads((DET_DIR / f"{sid}.json").read_text(encoding="utf-8"))
                   .get("ablations", {}).get("full_repo") or {}).get("top5") or []

    report: dict = {
        "condition": args.conditions,
        "inproc_run": str(args.inproc_run),
        "mcp_run": str(mcp_path),
        "n_common": len(sids),
        "mcp_scenarios_not_in_inproc": missing_inproc,
        "flags": {}, "top5": {}, "metrics": {}, "fidelity": {},
    }

    # -- run-level flags -----------------------------------------------------
    for label, src in (("inproc", inproc), ("mcp", mcp)):
        rr = [src[s] for s in sids]
        report["flags"][label] = {
            "n": len(rr),
            "usable": sum(usable(r) for r in rr),
            "valid_json": sum(bool((r.get("parsed") or {}).get("valid_json")) for r in rr),
            "truncated": sum(bool(r.get("truncated")) for r in rr),
            "has_error": sum(bool(r.get("error")) for r in rr),
            "unknown_tool_calls_total": int(sum(r.get("unknown_tool_calls", 0) or 0 for r in rr)),
            "forced_final": sum(bool(r.get("forced_final")) for r in rr),
            "finish_reasons": dict(Counter(r.get("finish_reason") for r in rr)),
            "tool_calls_median": float(np.median([r.get("tool_calls", 0) or 0 for r in rr])) if rr else 0.0,
            "latency_s_median": float(np.median([r.get("latency_s", 0) or 0 for r in rr])) if rr else 0.0,
        }

    # -- top5 agreement ------------------------------------------------------
    exact = same_set = 0
    per_scen = []
    for sid in sids:
        a, b = top5(inproc[sid]), top5(mcp[sid])
        if a == b:
            exact += 1
        if set(a) == set(b):
            same_set += 1
        if a != b:
            per_scen.append({"scenario_id": sid, "inproc": a, "mcp": b})
    report["top5"] = {"exact_order": exact, "same_set": same_set, "n": len(sids),
                      "differences": per_scen[:50]}

    # -- metric agreement (strict/lenient x pp/itt, sv/hv) -------------------
    for mode in ("strict", "lenient"):
        for analysis in ("pp", "itt"):

            def val(src, sid, mk):
                r = src[sid]
                us = usable(r)
                t5 = top5(r)
                d, f = flags[sid]
                if analysis == "pp":
                    if not us or not t5:
                        return None
                    return (sa.season_validity(t5, season[sid], mode) if mk == "sv"
                            else sa.hard_violation(t5, season[sid], d, f, mode))
                if not us or not t5:
                    return 0.0 if mk == "sv" else 1.0
                return (sa.season_validity(t5, season[sid], mode) if mk == "sv"
                        else sa.hard_violation(t5, season[sid], d, f, mode))

            for mk in ("sv", "hv"):
                iv = np.array([v for sid in sids if (v := val(inproc, sid, mk)) is not None])
                mv = np.array([v for sid in sids if (v := val(mcp, sid, mk)) is not None])
                n = min(len(iv), len(mv))
                report["metrics"][f"{mode}_{analysis}_{mk}"] = {
                    "inproc_mean": float(iv.mean()) if len(iv) else None,
                    "mcp_mean": float(mv.mean()) if len(mv) else None,
                    "inproc_n": len(iv), "mcp_n": len(mv),
                    "mean_abs_diff": float(np.mean(np.abs(iv[:n] - mv[:n]))) if n else None,
                    "max_abs_diff": float(np.max(np.abs(iv[:n] - mv[:n]))) if n else None,
                }

    # -- fidelity to C3 ------------------------------------------------------
    for label, src in (("inproc", inproc), ("mcp", mcp)):
        jac, t1 = [], []
        for sid in sids:
            t5 = top5(src[sid])
            jac.append(jaccard(t5, c3[sid]))
            t1.append(1.0 if (usable(src[sid]) and t5 and c3[sid] and t5[0] == c3[sid][0]) else 0.0)
        report["fidelity"][label] = {"jaccard": float(np.mean(jac)) if jac else None,
                                     "top1": float(np.mean(t1)) if t1 else None}

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"condition={args.conditions}  n_common={len(sids)}  "
          f"(mcp-only: {len(missing_inproc)})")
    print("\nrun-level flags:")
    for label in ("inproc", "mcp"):
        print(f"  {label:6s}: {json.dumps(report['flags'][label])}")
    print(f"\ntop-5 exact_order={exact}/{len(sids)}  same_set={same_set}/{len(sids)}")
    print("metrics (mean_abs_diff over common):")
    for k, v in report["metrics"].items():
        print(f"  {k:18s} inproc={report['metrics'][k]['inproc_mean']} "
              f"mcp={v['mcp_mean']} maxAbs={v['max_abs_diff']}")
    print("fidelity to C3:", json.dumps(report["fidelity"]))
    print(f"\nReport -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
