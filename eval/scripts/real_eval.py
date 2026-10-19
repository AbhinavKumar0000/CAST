"""STEP 5: real-world independent evaluation (offline; NO API calls).

Scores saved model outputs against the pre-registered real-world reference
(PROTOCOL 8.30). Reads only frozen inputs. Writes:
  - eval/results/real_eval.json
  - eval/results/real_eval_summary.txt

The measured quantity is agreement with actual district cropping patterns.
"""
from __future__ import annotations

import csv
import importlib.util
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from eval.statistics import cliffs_delta, holm_bonferroni  # noqa: E402

CLEAN = ROOT / "eval/real_data/clean/area_by_district_season_year.csv"
SUBSET = ROOT / "eval/data/llm_subset.jsonl"
PILOT = ROOT / "eval/results/pilot_scenario_sets.json"
CROP_LOG = ROOT / "crop_log.csv"
UNVERIFIED = ROOT / "eval/data/ground_truth/UNVERIFIED_FOR_REVIEW.csv"
LLAMA = ROOT / "eval/runs/eval_llama-3.2-11b/results.json"
OUT_JSON = ROOT / "eval/results/real_eval.json"
OUT_TXT = ROOT / "eval/results/real_eval_summary.txt"

N_RES = 10000
SEED = 42
WINDOW_PRIM = {"2015-2016", "2016-2017", "2017-2018", "2018-2019",
               "2019-2020", "2020-2021", "2021-2022", "2022-2023"}
WINDOW_FULL = WINDOW_PRIM | {"2023-2024", "2024-2025"}
PAIRS = [("C2a", "C0b"), ("C2a", "C1a"), ("C2b", "C0b"), ("C2b", "C1a"), ("C3", "C2b")]
COND_ORDER = ["C0", "C0b", "C1a", "C2a", "C2b", "C3"]

_lines: list[str] = []
RES: dict = {}


def emit(s: str = "") -> None:
    print(s)
    _lines.append(s)


def registry() -> set[str]:
    with open(CROP_LOG, encoding="utf-8-sig", newline="") as fh:
        return {r["Crop"].strip() for r in csv.DictReader(fh)}


def load_subset():
    rows = [json.loads(l) for l in SUBSET.read_text(encoding="utf-8").splitlines() if l.strip()]
    district = {r["scenario_id"]: str(r["district"]) for r in rows}
    season = {r["scenario_id"]: str(r["season_stratum"]) for r in rows}
    return [r["scenario_id"] for r in rows], district, season


def load_clean():
    rows = []
    with open(CLEAN, encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            r["area_ha"] = float(r["area_ha"])
            r["production_t"] = float(r["production_t"])
            r["in_vocab"] = (r["in_vocab"] == "True")
            rows.append(r)
    return rows


def build_reference(clean, window, metric="area_ha", restrict=True):
    agg: dict[tuple, dict] = {}
    for r in clean:
        if r["year"] not in window:
            continue
        if restrict and not r["in_vocab"]:
            continue
        key = r["crop_vocab"] if restrict else r["source_crop"]
        agg.setdefault((r["district"], r["season"]), {}).setdefault(key, []).append(r[metric])
    ref = {}
    for cell, crops in agg.items():
        means = sorted(((c, float(np.mean(v))) for c, v in crops.items()),
                       key=lambda x: (-x[1], x[0]))
        ref[cell] = [c for c, _ in means[:5]]
    return ref


def load_outputs(sids_all):
    spec = importlib.util.spec_from_file_location(
        "n500_primary_metrics", ROOT / "eval/scripts/n500_primary_metrics.py")
    pm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pm)
    _, _, _, _, _, c3, by = pm.build_data()
    nemo = dict(by)
    llama = {}
    if LLAMA.exists():
        sset = set(sids_all)
        for rec in json.load(LLAMA.open(encoding="utf-8")):
            if rec.get("repeat", 0) == 0 and rec.get("scenario_id") in sset:
                llama[(rec["condition"], rec["scenario_id"])] = rec
    return {"nemotron": (nemo, c3), "llama": (llama, c3)}


def usable(r):
    if r is None or r.get("error"):
        return False
    p = r.get("parsed") or {}
    return bool(p.get("valid_json")) and not r.get("truncated")


def top5_of(r):
    p = (r or {}).get("parsed") or {}
    return [str(x).strip() for x in (p.get("top5") or [])]


def precision_at_5(model_top5, ref):
    if not ref:
        return 0.0
    return len(set(model_top5) & set(ref)) / min(5, len(ref))


def ndcg_at_5(model_top5, ref):
    refset = set(ref)
    dcg = sum(1.0 / math.log2(i + 2) for i, c in enumerate(model_top5[:5]) if c in refset)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(min(5, len(ref))))
    return dcg / idcg if idcg > 0 else 0.0


def answer(cond, sid, by, c3):
    if cond == "C3":
        return list(c3.get(sid) or []), True
    rec = by.get((cond, sid))
    return top5_of(rec), usable(rec)


def cluster_stats(by_district):
    keys = sorted(by_district)
    if not keys:
        return {"mean": 0.0, "lo": 0.0, "hi": 0.0, "p": 1.0, "n": 0, "k": 0}
    sums = np.array([np.sum(by_district[k]) for k in keys], float)
    cnts = np.array([len(by_district[k]) for k in keys], float)
    obs = float(np.concatenate([np.asarray(by_district[k], float) for k in keys]).mean())
    rng = np.random.default_rng(SEED)
    idx = rng.integers(0, len(keys), size=(N_RES, len(keys)))
    boot = sums[idx].sum(1) / cnts[idx].sum(1)
    lo, hi = (float(x) for x in np.percentile(boot, [2.5, 97.5]))
    cs = sums - cnts * obs
    cb = cs[idx].sum(1) / cnts[idx].sum(1)
    p = max(float((np.abs(cb) >= abs(obs)).mean()), 1.0 / N_RES)
    return {"mean": obs, "lo": lo, "hi": hi, "p": p, "n": int(cnts.sum()), "k": len(keys)}


def values(cond, metric_fn, ref_table, sids_sub, by, c3, district, season, analysis):
    by_d: dict[str, list[float]] = {}
    raw = []
    for sid in sids_sub:
        t5, us = answer(cond, sid, by, c3)
        if not us or not t5:
            if analysis == "itt":
                by_d.setdefault(district[sid], []).append(0.0)
                raw.append(0.0)
            continue
        ref = ref_table.get((district[sid], season[sid]), [])
        v = metric_fn(t5, ref)
        by_d.setdefault(district[sid], []).append(v)
        raw.append(v)
    return by_d, raw


def contrast(a, b, metric_fn, ref_table, sids_sub, by, c3, district, season, analysis):
    by_d: dict[str, list[float]] = {}
    av, bv = [], []
    for sid in sids_sub:
        ta, ua = answer(a, sid, by, c3)
        tb, ub = answer(b, sid, by, c3)
        if not ua or not ta or not ub or not tb:
            if analysis == "itt":
                by_d.setdefault(district[sid], []).append(0.0)
                av.append(0.0)
                bv.append(0.0)
            continue
        ref = ref_table.get((district[sid], season[sid]), [])
        va, vb = metric_fn(ta, ref), metric_fn(tb, ref)
        by_d.setdefault(district[sid], []).append(va - vb)
        av.append(va)
        bv.append(vb)
    st = cluster_stats(by_d)
    st["cliff_d"] = float(cliffs_delta(av, bv)) if av else 0.0
    return st


def evaluate(model_name, by, c3, sids, district, season, ref_tables, pilot):
    present = sorted({c for (c, _) in by})
    conds = [c for c in COND_ORDER if c in present or c == "C3"]
    subsets = {"WITH_pilot": sids, "WITHOUT_pilot": [s for s in sids if s not in pilot]}
    out: dict = {"conditions": conds, "n_scenarios": len(sids)}
    for sub_label, sids_sub in subsets.items():
        sub_out: dict = {}
        for ref_name, ref_table in ref_tables.items():
            for analysis in ("pp", "itt"):
                lvl = {}
                for fn_name, fn in (("Precision@5", precision_at_5), ("nDCG@5", ndcg_at_5)):
                    lvl[fn_name] = {}
                    for cond in conds:
                        by_d, _ = values(cond, fn, ref_table, sids_sub, by, c3,
                                         district, season, analysis)
                        lvl[fn_name][cond] = cluster_stats(by_d)
                # contrasts (Holm over 5 pairs), per metric
                con = {}
                for fn_name, fn in (("Precision@5", precision_at_5), ("nDCG@5", ndcg_at_5)):
                    rows = {}
                    for a, b in PAIRS:
                        if a not in conds or b not in conds:
                            rows[f"{a}-{b}"] = {"insufficient": True}
                            continue
                        rows[f"{a}-{b}"] = contrast(a, b, fn, ref_table, sids_sub, by, c3,
                                                    district, season, analysis)
                    pv = [rows[f"{a}-{b}"].get("p", 1.0) for a, b in PAIRS]
                    adj = holm_bonferroni(pv)
                    for (a, b), pa in zip(PAIRS, adj):
                        rows[f"{a}-{b}"]["holm"] = float(pa)
                    con[fn_name] = rows
                sub_out[f"{ref_name}_{analysis}"] = {"levels": lvl, "contrasts": con}
        out[sub_label] = sub_out
    return out


def per_season(model_name, by, c3, sids, district, season, ref_table):
    seasons = sorted(set(season[s] for s in sids))
    out = {}
    for cond in COND_ORDER:
        if cond != "C3" and not any(c == cond for (c, _) in by):
            continue
        row = {}
        for s in seasons:
            ssids = [x for x in sids if season[x] == s]
            by_d, raw = values(cond, precision_at_5, ref_table, ssids, by, c3,
                               district, season, "pp")
            row[s] = {"n": len(raw), "precision_at_5": float(np.mean(raw)) if raw else 0.0}
        out[cond] = row
    return out


def unverified_check(ref_tables, clean):
    rows = list(csv.DictReader(UNVERIFIED.open(encoding="utf-8")))
    res = []
    for r in rows:
        crop, table, cond = r["crop"], r["table"], r["season_or_condition"]
        entry = {"crop": crop, "table": table, "season_or_condition": cond,
                 "current_status": r["current_status"]}
        if table == "crop_season_table" and cond in ("kharif", "rabi", "zaid"):
            season = {"kharif": "Kharif", "rabi": "Rabi", "zaid": "Zaid"}[cond]
            areas, ndist, ncell = [], 0, 0
            for rr in clean:
                if rr["season"] != season or rr["year"] not in WINDOW_PRIM:
                    continue
                if rr["crop_vocab"] != crop:
                    continue
                areas += [rr["area_ha"]]
                if rr["area_ha"] > 0:
                    ndist += 1
            entry["real_mp_mean_area_ha"] = float(np.mean(areas)) if areas else 0.0
            entry["real_mp_rows_positive"] = ndist
            entry["supported_by_real_data"] = bool(areas and np.mean(areas) > 0)
        res.append(entry)
    return res


def main() -> None:
    reg = registry()
    sids, district, season = load_subset()
    clean = load_clean()
    pilot = set(json.load(PILOT.open(encoding="utf-8"))["pilot_union"])
    outputs = load_outputs(sids)

    ref_tables = {
        "R_prim": build_reference(clean, WINDOW_PRIM, "area_ha", True),
        "R_full": build_reference(clean, WINDOW_FULL, "area_ha", True),
        "R_all": build_reference(clean, WINDOW_PRIM, "area_ha", False),
        "R_prod": build_reference(clean, WINDOW_PRIM, "production_t", True),
    }
    RES["reference_stats"] = {}
    for name, table in ref_tables.items():
        lens = [len(v) for v in table.values()]
        RES["reference_stats"][name] = {"cells": len(table), "mean_len": float(np.mean(lens)),
                                        "min_len": int(min(lens)), "max_len": int(max(lens))}
    src_in_vocab = {r["source_crop"]: r["in_vocab"] for r in clean}
    oov = [sum(1 for c in v if not src_in_vocab.get(c, False)) / min(5, len(v))
           for v in ref_tables["R_all"].values()]
    RES["out_of_vocab_share_top5_R_all"] = float(np.mean(oov))
    RES["vocab_crops_with_no_series"] = sorted(reg - {r["crop_vocab"] for r in clean if r["in_vocab"]})

    RES["models"] = {}
    for model_name, (by, c3) in outputs.items():
        model_sids = sorted({sid for (_, sid) in by})
        emit(f"\n=== model {model_name} ===")
        emit(f"conditions present: {sorted({c for (c,_) in by})}; n_scenarios={len(model_sids)}")
        RES["models"][model_name] = evaluate(model_name, by, c3, model_sids, district, season,
                                             ref_tables, pilot)
        RES["models"][model_name]["per_season_R_prim"] = per_season(
            model_name, by, c3, model_sids, district, season, ref_tables["R_prim"])

    RES["unverified_check"] = unverified_check(ref_tables, clean)

    # ---- console summary (headline = R_prim, pp, WITH_pilot) ----
    for model_name in RES["models"]:
        emit(f"\n===== {model_name}: R_prim | per-protocol | WITH pilot =====")
        block = RES["models"][model_name]["WITH_pilot"]["R_prim_pp"]
        emit(f"{'cond':5s} {'Precision@5 [95% CI]':30s} {'nDCG@5 [95% CI]':30s}")
        for cond in block["levels"]["Precision@5"]:
            p = block["levels"]["Precision@5"][cond]
            n = block["levels"]["nDCG@5"][cond]
            emit(f"{cond:5s} {p['mean']:.3f} [{p['lo']:.3f},{p['hi']:.3f}]".ljust(5 + 30)
                 + f"{n['mean']:.3f} [{n['lo']:.3f},{n['hi']:.3f}]".ljust(30))
        emit("contrasts (Precision@5):")
        for k, v in block["contrasts"]["Precision@5"].items():
            if v.get("insufficient"):
                emit(f"  {k}: insufficient n")
            else:
                emit(f"  {k}: {v['mean']:+.3f} [{v['lo']:+.3f},{v['hi']:+.3f}] "
                     f"Cliff_d={v['cliff_d']:+.3f} p={v['p']:.2e} holm={v['holm']:.2e} n={v['n']}")

    emit(f"\nout-of-vocab share of real top-5 (R_all) = "
         f"{RES['out_of_vocab_share_top5_R_all']:.3f}")
    emit("\nUNVERIFIED crop-season rows vs real data:")
    for e in RES["unverified_check"]:
        if "real_mp_mean_area_ha" in e:
            emit(f"  {e['crop']}/{e['season_or_condition']}: real MP mean area = "
                 f"{e['real_mp_mean_area_ha']:.1f} ha -> "
                 f"{'supported' if e['supported_by_real_data'] else 'NO real area'}")

    OUT_JSON.write_text(json.dumps(RES, indent=2, default=float), encoding="utf-8")
    OUT_TXT.write_text("\n".join(_lines) + "\n", encoding="utf-8")
    emit(f"\nwrote {OUT_JSON}")
    emit(f"wrote {OUT_TXT}")


if __name__ == "__main__":
    main()
