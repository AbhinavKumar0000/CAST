"""STEP 6: one table - C3 db_v2 beside the existing LLM results (all db_v1).

Every condition is scored on the SAME test-period references as STEP 5:
  - R_test_all  (unrestricted, canonical names, window 2020-21..2022-23)
  - R_test_reg  (db_v1 21-crop vocabulary, same window)
LLM conditions were run on db_v1 and are NOT re-run on db_v2; C3 is recomputed
deterministically under both databases.

Outputs eval/results/db_v2_combined_table.{txt,json}.
"""
from __future__ import annotations

import csv
import importlib.util
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import numpy as np  # noqa: E402

CLEAN = ROOT / "eval/real_data/clean/area_by_district_season_year.csv"
SUBSET = ROOT / "eval/data/llm_subset.jsonl"
LLAMA = ROOT / "eval/runs/eval_llama-3.2-11b/results.json"
DET_V1 = ROOT / "eval/runs/archive_v2/deterministic"
DET_V2 = ROOT / "eval/runs/db_v2/deterministic"
OUT_TXT = ROOT / "eval/results/db_v2_combined_table.txt"
OUT_JSON = ROOT / "eval/results/db_v2_combined_table.json"

TEST = {"2020-2021", "2021-2022", "2022-2023"}
CONDS = ["C0", "C0b", "C1a", "C2a", "C2b"]


def load_clean():
    rows = []
    with (ROOT / "eval/real_data/clean/area_by_district_season_year.csv").open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            r["area_ha"] = float(r["area_ha"])
            r["in_vocab"] = (r["in_vocab"] == "True")
            rows.append(r)
    return rows


def build_reference(clean, window, restrict):
    agg = defaultdict(lambda: defaultdict(list))
    for r in clean:
        if r["year"] not in window:
            continue
        if restrict and not r["in_vocab"]:
            continue
        key = r["crop_vocab"] if r["in_vocab"] else r["source_crop"]
        agg[(r["district"], r["season"])][key].append(r["area_ha"])
    ref = {}
    for cell, crops in agg.items():
        means = sorted(((c, float(sum(v) / len(v))) for c, v in crops.items()), key=lambda x: (-x[1], x[0]))
        ref[cell] = [c for c, _ in means[:5]]
    return ref


def precision_at_5(top5, ref):
    return len(set(top5) & set(ref)) / min(5, len(ref)) if ref else 0.0


def ndcg_at_5(top5, ref):
    rs = set(ref)
    dcg = sum(1.0 / math.log2(i + 2) for i, c in enumerate(top5[:5]) if c in rs)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(min(5, len(ref))))
    return dcg / idcg if idcg > 0 else 0.0


def load_llm():
    rows = [json.loads(l) for l in (ROOT / "eval/data/llm_subset.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    district = {r["scenario_id"]: str(r["district"]) for r in rows}
    season = {r["scenario_id"]: str(r["season_stratum"]) for r in rows}
    spec = importlib.util.spec_from_file_location("n500_primary_metrics", ROOT / "eval/scripts/n500_primary_metrics.py")
    pm = importlib.util.module_from_spec(spec); spec.loader.exec_module(pm)
    _, _, _, _, _, c3, by = pm.build_data()
    nemo = {"by": dict(by), "c3": c3}
    llama = defaultdict(dict)
    if (ROOT / "eval/runs/eval_llama-3.2-11b/results.json").exists():
        for rec in json.load((ROOT / "eval/runs/eval_llama-3.2-11b/results.json").open(encoding="utf-8")):
            if rec.get("repeat", 0) == 0:
                llama[rec["condition"]][rec["scenario_id"]] = rec
    return district, season, nemo, llama


def usable(r):
    if r is None or r.get("error"):
        return False
    p = r.get("parsed") or {}
    return bool(p.get("valid_json")) and not r.get("truncated")


def top5_of(r):
    p = (r or {}).get("parsed") or {}
    return [str(x).strip() for x in (p.get("top5") or [])]


def mean_metric(pairs, ref_full, district, season, metric, only_usable):
    fn = precision_at_5 if metric == "Precision@5" else ndcg_at_5
    vals = []
    for sid, rec in pairs:
        if only_usable and not usable(rec):
            continue
        t5 = top5_of(rec)
        cell = (district.get(sid), season.get(sid))
        vals.append(fn(t5, ref_full.get(cell, [])))
    return float(sum(vals) / len(vals)) if vals else 0.0, len(vals)


def c3_pairs(det_dir, sids):
    out = []
    for sid in sids:
        p = det_dir / f"{sid}.json"
        if p.exists():
            r = json.loads(p.read_text(encoding="utf-8"))
            ab = r["ablations"]["full_repo"]["top5"]
            out.append((sid, {"parsed": {"valid_json": True, "top5": ab}}))
    return out


def main():
    district, season, nemo, llama = load_llm()
    clean = []
    for r in csv.DictReader((ROOT / "eval/real_data/clean/area_by_district_season_year.csv").open(encoding="utf-8")):
        r["area_ha"] = float(r["area_ha"]); r["in_vocab"] = (r["in_vocab"] == "True"); clean.append(r)
    refs = {"R_test_all": "", "R_test_reg": ""}
    # reuse the same builder as STEP 5
    agg_def = {}
    for tag, restrict in (("R_test_all", False), ("R_test_reg", True)):
        agg = defaultdict(lambda: defaultdict(list))
        for r in clean:
            if r["year"] not in TEST:
                continue
            if restrict and not r["in_vocab"]:
                continue
            key = r["crop_vocab"] if r["in_vocab"] else r["source_crop"]
            agg[(r["district"], r["season"])][key].append(r["area_ha"])
        ref = {}
        for cell, crops in agg.items():
            means = sorted(((c, float(np.mean(v))) for c, v in crops.items()), key=lambda x: (-x[1], x[0]))
            ref[cell] = [c for c, _ in means[:5]]
        refs[tag] = ref

    nemo_by_cond = defaultdict(dict)
    for (c, sid), rec in nemo["by"].items():
        nemo_by_cond[c][sid] = rec
    nemo_pairs = dict(nemo_by_cond)
    nemo_sids = sorted({sid for (_, sid) in nemo["by"]})
    llama_sids = sorted({sid for (_c, sid) in [(c, s) for c, d in llama.items() for s in d]})
    c3v1_nemo = c3_pairs(ROOT / "eval/runs/archive_v2/deterministic", nemo_sids)
    c3v2_nemo = c3_pairs(ROOT / "eval/runs/db_v2/deterministic", nemo_sids)
    c3v1_llama = c3_pairs(ROOT / "eval/runs/archive_v2/deterministic", llama_sids)
    c3v2_llama = c3_pairs(ROOT / "eval/runs/db_v2/deterministic", llama_sids)

    res = {"reference": "test window 2020-21..2022-23", "note": "LLM conditions are db_v1 and were NOT re-run on db_v2.", "models": {}}
    lines = ["Combined table - all conditions on the SAME test reference (window 2020-21..2022-23).",
             "LLM conditions used db_v1 and were NOT re-run on db_v2; C3 recomputed under both databases.", ""]
    for model, conds_pairs, c1, c2 in (
        ("nemotron-3-ultra (n=500)", nemo_pairs, c3v1_nemo, c3v2_nemo),
        ("llama-3.2-11b (n=150)", llama, c3v1_llama, c3v2_llama),
    ):
        model_out = {"conditions": {}}
        for ref_tag, ref in refs.items():
            model_out["conditions"][ref_tag] = {}
            for metric in ("Precision@5", "nDCG@5"):
                row = {}
                for cond in ["C0", "C0b", "C1a", "C2a", "C2b"]:
                    pairs = conds_pairs.get(cond, {})
                    pairs = list(pairs.items()) if isinstance(pairs, dict) else []
                    m, n = mean_metric(pairs, ref, district, season, metric, True)
                    if n:
                        row[cond] = {"mean": round(m, 4), "n": n}
                for tag, pairs in (("C3 (db_v1)", c1), ("C3 (db_v2)", c2)):
                    m, n = mean_metric(pairs, ref, district, season, metric, False)
                    row[tag] = {"mean": round(m, 4), "n": n}
                model_out["conditions"][ref_tag][metric] = row
        res["models"][model] = model_out
        lines.append(f"===== {model} =====")
        for ref_tag in ("R_test_all", "R_test_reg"):
            lines.append(f"  reference {ref_tag}:")
            lines.append(f"    {'cond':10s} {'P@5':>8s} {'nDCG@5':>8s}")
            for cond in ["C0", "C0b", "C1a", "C2a", "C2b", "C3 (db_v1)", "C3 (db_v2)"]:
                p = model_out["conditions"][ref_tag]["Precision@5"].get(cond, {})
                nd = model_out["conditions"][ref_tag]["nDCG@5"].get(cond, {})
                ps = f"{p['mean']:.3f}" if p else "  -  "
                ns = f"{nd['mean']:.3f}" if nd else "  -  "
                lines.append(f"    {cond:10s} {ps:>8s} {ns:>8s}")
        lines.append("")

    (ROOT / "eval/results/db_v2_combined_table.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    (ROOT / "eval/results/db_v2_combined_table.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
