"""EXPLORATORY (PROTOCOL 8.34 item 1b): impact of B6 on the real-data analysis
real_eval_scorer_vs_final, where C3 (det pipeline) was used as a proxy for the
scorer TOOL (crop_score). Replays the exact script logic twice: scorer = det
(must reproduce published numbers) vs scorer = stored bundle crop_score.
"""
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

RUNS = [ROOT / "eval/runs/eval_nemotron-3-ultra/results.json",
        ROOT / "eval/runs/eval_nemotron-3-ultra_b2/results.json"]
DET = ROOT / "eval/runs/archive_v2/deterministic"
ARCH = ROOT / "eval/runs/archive_v2/evidence"
OUT = ROOT / "eval/results/s_followup_real_impact.json"
CONDS = ["C2a", "C2b"]

spec = importlib.util.spec_from_file_location("re", ROOT / "eval/scripts/real_eval.py")
re = importlib.util.module_from_spec(spec)
spec.loader.exec_module(re)


def load_det_for(sids):
    c3 = {}
    for sid in sids:
        path = DET / f"{sid}.json"
        if not path.exists():
            continue
        res = json.loads(path.read_text(encoding="utf-8"))
        ab = (res.get("ablations") or {}).get("full_repo")
        if ab and not ab.get("error") and ab.get("top5"):
            c3[sid] = ab["top5"]
    return c3


def load_tool5(sids):
    t5, missing = {}, []
    for sid in sids:
        fp = ARCH / f"{sid}.json"
        if not fp.exists():
            missing.append(sid)
            continue
        b = json.loads(fp.read_text(encoding="utf-8"))
        rc = (b.get("crop_score") or {}).get("ranked_crops") or []
        if rc:
            t5[sid] = [c["crop"] for c in rc[:5]]
        else:
            missing.append(sid)
    return t5, missing


def main() -> None:
    sids, district, season = re.load_subset()
    print("subset loaded:", len(sids), flush=True)
    clean = re.load_clean()
    ref = re.build_reference(clean, re.WINDOW_PRIM, "area_ha", True)
    print("reference built", flush=True)
    by = {}
    for p in RUNS:
        if p.exists():
            for r in json.loads(p.read_text(encoding="utf-8")):
                by[(r.get("condition"), r.get("scenario_id"))] = r
    print("records loaded:", len(by), flush=True)
    c3 = load_det_for(sids)
    tool5, tool_missing = load_tool5(sids)
    print("det:", len(c3), "tool:", len(tool5), flush=True)

    common = [s for s in sids if s in c3 and s in tool5]
    diff = [s for s in common if c3[s] != tool5[s]]
    diff_t5_only = [s for s in common if set(c3[s]) != set(tool5[s])]

    def aggregates(scorer):
        scorer_all = [re.precision_at_5(scorer[s], ref.get((district[s], season[s]), []))
                      for s in sids if s in scorer]
        out = {"scorer_precision_at_5_all": float(np.mean(scorer_all)),
               "n_scorer_all": len(scorer_all), "conditions": {}}
        for cond in CONDS:
            rows = []
            for sid in sids:
                r = by.get((cond, sid))
                if not (r and r.get("parsed", {}).get("valid_json")
                        and not r.get("error") and not r.get("truncated")):
                    continue
                final = r["parsed"].get("top5") or []
                sc = scorer.get(sid)
                if not final or not sc:
                    continue
                rref = ref.get((district[sid], season[sid]), [])
                n = min(5, len(final), len(sc))
                rows.append({
                    "ordered_identical": int(list(final) == list(sc)),
                    "set_identical": int(set(final) == set(sc)),
                    "jaccard": len(set(final) & set(sc)) / (len(set(final) | set(sc)) or 1),
                    "positions_identical": sum(1 for i in range(n) if final[i] == sc[i]),
                    "precision_at_5_scorer": re.precision_at_5(sc, rref),
                    "precision_at_5_final": re.precision_at_5(final, rref),
                })
            out["conditions"][cond] = {"n": len(rows), **{
                k: float(np.mean([x[k] for x in rows]))
                for k in ("ordered_identical", "set_identical", "jaccard",
                          "positions_identical", "precision_at_5_scorer",
                          "precision_at_5_final")}} if rows else {}
        return out

    det_agg = aggregates(c3)
    tool_agg = aggregates(tool5)

    payload = {
        "registered": "EXPLORATORY (PROTOCOL 8.34 item 1b)",
        "n_sids": len(sids), "n_common": len(common), "n_tool_missing": len(tool_missing),
        "tool_missing": tool_missing[:10],
        "sids_tool_vs_det_differ_ordered": len(diff),
        "sids_tool_vs_det_differ_set": len(diff_t5_only),
        "share_ordered_differ": len(diff) / max(1, len(common)),
        "scorer_is_det_proxy_for_tool": True,
        "det_proxy": det_agg, "tool_actual": tool_agg,
    }
    OUT.write_text(json.dumps(payload, indent=2, default=float), encoding="utf-8")

    print(f"sids: {len(sids)} common {len(common)}; tool missing {len(tool_missing)}")
    print(f"ordered differ tool vs det: {len(diff)} ({len(diff)/len(common):.3f}); "
          f"set differ: {len(diff_t5_only)}")
    print("\nmetric                          det(proxy)  tool(actual)  delta")
    rowspec = [("P@5 all", "scorer_precision_at_5_all", None)]
    print(f"{'P@5 all':30} {det_agg['scorer_precision_at_5_all']:.4f}   "
          f"{tool_agg['scorer_precision_at_5_all']:.4f}   "
          f"{tool_agg['scorer_precision_at_5_all']-det_agg['scorer_precision_at_5_all']:+.4f}")
    for cond in CONDS:
        for k in ("n", "ordered_identical", "set_identical", "jaccard",
                  "positions_identical", "precision_at_5_scorer",
                  "precision_at_5_final"):
            d = det_agg["conditions"][cond].get(k)
            t = tool_agg["conditions"][cond].get(k)
            if d is None or t is None:
                continue
            fmt = "{:<9}" if k == "n" else "{:<9.4f}"
            print(f"{cond+' '+k:30} " + fmt.format(d) + "  " + fmt.format(t)
                  + ("      " if k == "n" else f"  {t-d:+.4f}"))
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()

