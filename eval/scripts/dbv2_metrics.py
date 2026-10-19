"""STEP 5: database-version agreement test (C3 db_v1 vs C3 db_v2).

Pre-registered in PROTOCOL ss8.31. Offline; no model calls.

Primary: test-period (2020-21..2022-23) real top-5 by mean area, UNRESTRICTED
(canonical names: registry name if in-vocab else raw source name), on the frozen
500-scenario LLM subset. Metrics Precision@5 and nDCG@5, C3 db_v1 vs C3 db_v2,
district-clustered bootstrap 95% CI, paired contrast + Holm over the 2 metrics.

Also: in-sample (build period), sensitivity (2023-24, 2024-25), registry-
restricted secondary, per-season/per-district breakdowns, out-of-vocab ceiling,
and season-validity / hard-violation under db_v2 vs db_v1.

Reads: frozen evidence + db_v1 archive deterministic + db_v2 deterministic.
Writes: eval/results/db_v2_test.{json,txt}.
"""
from __future__ import annotations

import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import numpy as np  # noqa: E402

from eval.statistics import cliffs_delta, holm_bonferroni  # noqa: E402

CLEAN = ROOT / "eval/real_data/clean/area_by_district_season_year.csv"
SUBSET = ROOT / "eval/data/llm_subset.jsonl"
CROP_LOG_V1 = ROOT / "crop_log.csv"
CROP_LOG_V2 = ROOT / "crop_log_v2.csv"
DET_V1 = ROOT / "eval/runs/archive_v2/deterministic"
DET_V2 = ROOT / "eval/runs/db_v2/deterministic"
EVID = ROOT / "eval/runs/archive_v2/evidence"
GT = ROOT / "eval/data/ground_truth"
STRESS = ROOT / "eval/data/stress.jsonl"
OUT_JSON = ROOT / "eval/results/db_v2_test.json"
OUT_TXT = ROOT / "eval/results/db_v2_test.txt"

N_RES, SEED = 10000, 42
BUILD = {"2015-2016", "2016-2017", "2017-2018", "2018-2019", "2019-2020"}
TEST = {"2020-2021", "2021-2022", "2022-2023"}
SENS = {"2023-2024", "2024-2025"}
METRICS = ("Precision@5", "nDCG@5")

_lines: list[str] = []


def emit(s=""):
    print(s)
    _lines.append(s)


def registry(path):
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return {r["Crop"].strip() for r in csv.DictReader(fh)}


def load_clean():
    rows = []
    with CLEAN.open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            r["area_ha"] = float(r["area_ha"])
            r["in_vocab"] = (r["in_vocab"] == "True")
            rows.append(r)
    return rows


def load_subset():
    rows = [json.loads(l) for l in SUBSET.read_text(encoding="utf-8").splitlines() if l.strip()]
    district = {r["scenario_id"]: str(r["district"]) for r in rows}
    season = {r["scenario_id"]: str(r["season_stratum"]) for r in rows}
    return [r["scenario_id"] for r in rows], district, season


def load_c3(det_dir, sids=None):
    out = {}
    for p in det_dir.glob("*.json"):
        if sids is not None and p.stem not in sids:
            continue
        r = json.loads(p.read_text(encoding="utf-8"))
        ab = (r.get("ablations") or {}).get("full_repo")
        if ab and ab.get("top5"):
            out[p.stem] = ab["top5"]
    return out


def build_reference(clean, window, restrict):
    """restrict=True -> in-vocab only, key=crop_vocab. restrict=False -> all crops,
    key=crop_vocab if in-vocab else source_crop (canonical name)."""
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
        means = sorted(((c, float(np.mean(v))) for c, v in crops.items()), key=lambda x: (-x[1], x[0]))
        ref[cell] = [c for c, _ in means[:5]]
    return ref


def precision_at_5(top5, ref):
    return len(set(top5) & set(ref)) / min(5, len(ref)) if ref else 0.0


def ndcg_at_5(top5, ref):
    refset = set(ref)
    dcg = sum(1.0 / math.log2(i + 2) for i, c in enumerate(top5[:5]) if c in refset)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(min(5, len(ref))))
    return dcg / idcg if idcg > 0 else 0.0


def per_scenario(top5_by_sid, sids, district, season, ref, metric):
    fn = precision_at_5 if metric == "Precision@5" else ndcg_at_5
    by_d = defaultdict(list)
    for sid in sids:
        cell = (district[sid], season[sid])
        v = fn(top5_by_sid.get(sid, []), ref.get(cell, []))
        by_d[district[sid]].append(v)
    return by_d


def cluster_stats(by_d):
    keys = sorted(by_d)
    if not keys:
        return {"mean": 0.0, "lo": 0.0, "hi": 0.0, "n": 0, "k": 0}
    sums = np.array([np.sum(by_d[k]) for k in keys], float)
    cnts = np.array([len(by_d[k]) for k in keys], float)
    obs = float(np.concatenate([np.asarray(by_d[k], float) for k in keys]).mean())
    rng = np.random.default_rng(SEED)
    idx = rng.integers(0, len(keys), size=(N_RES, len(keys)))
    boot = sums[idx].sum(1) / cnts[idx].sum(1)
    lo, hi = (float(x) for x in np.percentile(boot, [2.5, 97.5]))
    return {"mean": obs, "lo": lo, "hi": hi, "n": int(cnts.sum()), "k": len(keys)}


def paired_contrast(a_by_sid, b_by_sid, sids, district, season, ref, metric):
    fn = precision_at_5 if metric == "Precision@5" else ndcg_at_5
    by_d = defaultdict(list)
    a_vals, b_vals = [], []
    for sid in sids:
        cell = (district[sid], season[sid])
        av = fn(a_by_sid.get(sid, []), ref.get(cell, []))
        bv = fn(b_by_sid.get(sid, []), ref.get(cell, []))
        by_d[district[sid]].append(av - bv)
        a_vals.append(av)
        b_vals.append(bv)
    keys = sorted(by_d)
    sums = np.array([np.sum(by_d[k]) for k in keys], float)
    cnts = np.array([len(by_d[k]) for k in keys], float)
    obs = float(np.concatenate([np.asarray(by_d[k], float) for k in keys]).mean())
    rng = np.random.default_rng(SEED)
    idx = rng.integers(0, len(keys), size=(N_RES, len(keys)))
    boot = sums[idx].sum(1) / cnts[idx].sum(1)
    lo, hi = (float(x) for x in np.percentile(boot, [2.5, 97.5]))
    cs = sums - cnts * obs
    cb = cs[idx].sum(1) / cnts[idx].sum(1)
    p = float(np.mean(np.abs(cb) >= abs(obs)))
    return {"mean": obs, "lo": lo, "hi": hi, "p": p, "n": int(cnts.sum()),
            "cliff_d": float(cliffs_delta(a_vals, b_vals)), "k": len(keys)}


# ---- season validity / hard violation (same definitions as the frozen script) ----
season_rows = list(csv.DictReader((GT / "crop_season_table_v1.2.csv").open(encoding="utf-8", newline="")))
hard_rows = list(csv.DictReader((GT / "hard_constraints_v1.1.csv").open(encoding="utf-8", newline="")))


def season_status(crop, season):
    here = [r for r in season_rows if r["crop"] == crop and r["season"] == season]
    if any(r["status"] == "cited" for r in here):
        return "valid"
    if any(r["status"] == "contradicted" for r in here):
        return "invalid"
    if here:
        return "unknown"
    if not any(r["crop"] == crop for r in season_rows):
        return "unknown"
    return "invalid"


def season_validity(top5, season, mode):
    num = den = 0
    for p in top5:
        st = season_status(p, season)
        if st == "valid":
            num += 1; den += 1
        elif st == "invalid":
            den += 1
        elif mode == "strict":
            den += 1
    return num / den if den else 0.0


def hard_violation(top5, season, drought, flood, mode):
    sc = [r for r in hard_rows if r["constraint_type"] == "season"]
    dc = [r for r in hard_rows if r["constraint_type"] == "drought"]
    fc = [r for r in hard_rows if r["constraint_type"] == "flood"]
    viol = den = 0
    for p in top5:
        rel = ([r for r in sc if r["crop"] == p and r["condition"] == season]
               + ([r for r in dc if r["crop"] == p] if drought else [])
               + ([r for r in fc if r["crop"] == p] if flood else []))
        cited = any(r["status"] == "cited" for r in rel)
        unknown_only = bool(rel) and not cited
        den += 1
        if cited:
            viol += 1
        elif mode == "strict" and unknown_only:
            viol += 1
        elif mode == "lenient" and unknown_only:
            den -= 1
    return viol, den


def level_table(c3, sids, district, season, ref):
    out = {"levels": {}, "contrast": {}, "holm": {}}
    for metric in METRICS:
        out["levels"][metric] = {}
        for tag, preds in c3.items():
            out["levels"][metric][tag] = cluster_stats(
                per_scenario(preds, sids, district, season, ref, metric))
    pv = []
    for metric in METRICS:
        c = paired_contrast(c3["db_v2"], c3["db_v1"], sids, district, season, ref, metric)
        out["contrast"][metric] = c
        pv.append(c["p"])
    for metric, adj in zip(METRICS, holm_bonferroni(pv)):
        out["holm"][metric] = float(adj)
    return out


def main():
    reg_v1 = registry(CROP_LOG_V1)
    reg_v2 = registry(CROP_LOG_V2)
    clean = load_clean()
    sids, district, season = load_subset()
    sids = [s for s in sids if s in (set(p.stem for p in DET_V1.glob("*.json")))]
    c3_v1 = load_c3(DET_V1, set(sids))
    c3_v2 = load_c3(DET_V2, set(sids))
    c3 = {"db_v1": c3_v1, "db_v2": c3_v2}
    emit(f"subset scenarios with C3: {len(sids)}; db_v1 n={len(c3_v1)} db_v2 n={len(c3_v2)}")

    refs = {
        "R_test_all": build_reference(clean, TEST, False),
        "R_test_reg": build_reference(clean, TEST, True),
        "R_build_all": build_reference(clean, BUILD, False),
        "R_build_reg": build_reference(clean, BUILD, True),
        "R_2023-24": build_reference(clean, {"2023-2024"}, False),
        "R_2024-25": build_reference(clean, {"2024-2025"}, False),
    }
    res = {"n_subset": len(sids), "databases": {"db_v1": sorted(reg_v1), "db_v2": sorted(reg_v2)}}
    res["reference_stats"] = {k: {"cells": len(v),
                                  "mean_len": float(np.mean([len(x) for x in v.values()]))}
                              for k, v in refs.items()}

    # PRIMARY
    res["primary_R_test_all"] = level_table(c3, sids, district, season, refs["R_test_all"])
    # IN-SAMPLE
    res["insample_R_build_all"] = level_table(c3, sids, district, season, refs["R_build_all"])
    # SECONDARY registry-restricted test
    res["secondary_R_test_reg"] = level_table(c3, sids, district, season, refs["R_test_reg"])
    # SENSITIVITY single years
    res["sens_R_2023_24"] = level_table(c3, sids, district, season, refs["R_2023-24"])
    res["sens_R_2024_25"] = level_table(c3, sids, district, season, refs["R_2024-25"])

    # per-season (primary)
    per_season = {}
    for cond, preds in c3.items():
        row = {}
        for s in ["Kharif", "Rabi", "Zaid"]:
            ss = [x for x in sids if season[x] == s]
            st = cluster_stats(per_scenario(preds, ss, district, season, refs["R_test_all"], "Precision@5"))
            row[s] = {"n": st["n"], "precision_at_5": st["mean"]}
        per_season[cond] = row
    res["per_season_primary"] = per_season

    # per-district (primary, Precision@5) - descriptive
    per_district = {}
    for cond, preds in c3.items():
        d = {}
        for dist in sorted(set(district[s] for s in sids)):
            ss = [x for x in sids if district[x] == dist]
            d[dist] = float(np.mean([precision_at_5(preds.get(x, []), refs["R_test_all"].get((dist, season[x]), [])) for x in ss]))
        per_district[cond] = d
    res["per_district_primary"] = per_district

    # Linseed diagnostic: why does db_v2 move agreement?
    ref_all = refs["R_test_all"]
    mask = np.array(["Linseed" in c3["db_v2"].get(s, []) for s in sids])
    p1 = np.array([precision_at_5(c3["db_v1"].get(s, []), ref_all.get((district[s], season[s]), [])) for s in sids])
    p2 = np.array([precision_at_5(c3["db_v2"].get(s, []), ref_all.get((district[s], season[s]), [])) for s in sids])
    res["linseed_diagnostic"] = {
        "ref_cells_with_linseed_in_500": int(sum(1 for s in sids if "Linseed" in ref_all.get((district[s], season[s]), []))),
        "db_v2_top5_with_linseed": int(mask.sum()),
        "db_v2_linseed_true_positives": int(sum(1 for s in sids if "Linseed" in c3["db_v2"].get(s, [])
                                                  and "Linseed" in ref_all.get((district[s], season[s]), []))),
        "p5_db_v1_with_linseed": float(p1[mask].mean()) if mask.any() else None,
        "p5_db_v2_with_linseed": float(p2[mask].mean()) if mask.any() else None,
        "n_with_linseed": int(mask.sum()),
        "p5_db_v1_without_linseed": float(p1[~mask].mean()) if (~mask).any() else None,
        "p5_db_v2_without_linseed": float(p2[~mask].mean()) if (~mask).any() else None,
        "n_without_linseed": int((~mask).sum()),
    }

    # ceiling (out-of-vocab share of primary reference top-5)
    res["ceiling"] = {
        "R_test_all_oov_share_db_v1": out_oov(reg_v1, refs["R_test_all"]),
        "R_test_all_oov_share_db_v2": out_oov(reg_v2, refs["R_test_all"]),
    }
    linseed_slots = sum(1 for v in refs["R_test_all"].values() if "Linseed" in v)
    res["ceiling"]["Linseed_in_reference_cells"] = linseed_slots
    res["ceiling"]["Linseed_total_slots"] = sum(1 for v in refs["R_test_all"].values() for c in v if c == "Linseed")

    # season validity / hard violation over 10,000 (db_v1 vs db_v2)
    c3_all = {"db_v1": load_c3(DET_V1), "db_v2": load_c3(DET_V2)}
    season_of = {}
    risk_flags = {}
    for path in EVID.glob("*.json"):
        ev = json.loads(path.read_text(encoding="utf-8"))
        sid = ev.get("scenario_id")
        season_of[sid] = ev.get("season", {}).get("current_season", "")
        risk = ev.get("risk") or {}
        try:
            d = float(risk.get("drought_z_score_30d", 0)) <= -1.5
            f = float(risk.get("flood_probability", 0)) >= 0.40
        except (TypeError, ValueError):
            d, f = False, False
        risk_flags[sid] = {"drought": d, "flood": f}
    sv_summary = {}
    for tag, preds in c3_all.items():
        for mode in ("strict", "lenient"):
            sv = []
            hv = ht = 0
            by_season = defaultdict(list)
            for sid, top5 in preds.items():
                s = season_of.get(sid, "")
                v = season_validity(top5, s, mode)
                sv.append(v)
                by_season[s].append(v)
                viol, den = hard_violation(top5, s, risk_flags.get(sid, {}).get("drought", False),
                                           risk_flags.get(sid, {}).get("flood", False), mode)
                hv += viol; ht += den
            sv_summary[f"{tag}|{mode}"] = {
                "overall": float(np.mean(sv)),
                "per_season": {s: float(np.mean(by_season[s])) if by_season[s] else 0.0
                               for s in ["Kharif", "Rabi", "Zaid"]},
                "hard_violating": hv, "hard_evaluated": ht,
                "hard_violation_rate": float(hv / ht) if ht else None,
            }
    res["season_validity"] = sv_summary

    OUT_JSON.write_text(json.dumps(res, indent=2, default=float), encoding="utf-8")

    # ---- console/txt summary ----
    emit("\n=== PRIMARY: test-period unrestricted reference (R_test_all), n=500 ===")
    p = res["primary_R_test_all"]
    for metric in METRICS:
        emit(f"  {metric}:")
        for tag in ("db_v1", "db_v2"):
            lv = p["levels"][metric][tag]
            emit(f"    {tag}: {lv['mean']:.4f} [{lv['lo']:.4f},{lv['hi']:.4f}] n={lv['n']}")
        c = p["contrast"][metric]
        emit(f"    db_v2-db_v1: {c['mean']:+.4f} [{c['lo']:+.4f},{c['hi']:+.4f}] "
             f"cliff_d={c['cliff_d']:+.3f} p={c['p']:.2e} holm={p['holm'][metric]:.2e}")
    emit("\n=== IN-SAMPLE: build period (R_build_all), labelled in-sample ===")
    for metric in METRICS:
        lv = res["insample_R_build_all"]["levels"][metric]
        c = res["insample_R_build_all"]["contrast"][metric]
        emit(f"  {metric}: db_v1 {lv['db_v1']['mean']:.4f} db_v2 {lv['db_v2']['mean']:.4f} "
             f"(db_v2-db_v1 {c['mean']:+.4f})")
    emit("\n=== SECONDARY: test restricted to db_v1 21-crop vocab (R_test_reg) ===")
    for metric in METRICS:
        lv = res["secondary_R_test_reg"]["levels"][metric]
        c = res["secondary_R_test_reg"]["contrast"][metric]
        emit(f"  {metric}: db_v1 {lv['db_v1']['mean']:.4f} db_v2 {lv['db_v2']['mean']:.4f} "
             f"db_v2-db_v1 {c['mean']:+.4f} [{c['lo']:+.4f},{c['hi']:+.4f}] p={c['p']:.2e} holm={res['secondary_R_test_reg']['holm'][metric]:.2e}")
    emit("\n=== SENSITIVITY ===")
    for key in ("sens_R_2023_24", "sens_R_2024_25"):
        lv = res[key]["levels"]["Precision@5"]
        cc = res[key]["contrast"]["Precision@5"]
        emit(f"  {key}: db_v1 {lv['db_v1']['mean']:.4f} db_v2 {lv['db_v2']['mean']:.4f} "
             f"contrast {cc['mean']:+.4f} [{cc['lo']:+.4f},{cc['hi']:+.4f}] p={cc['p']:.2e}")
    emit("\n=== PER-SEASON (primary, Precision@5) ===")
    for tag, row in res["per_season_primary"].items():
        emit(f"  {tag}: " + " ".join(f"{s}={row[s]['precision_at_5']:.3f}(n{row[s]['n']})" for s in row))
    ld = res["linseed_diagnostic"]
    emit("\n=== LINSEED DIAGNOSTIC (why db_v2 moves) ===")
    emit(f"  reference cells with Linseed: {ld['ref_cells_with_linseed_in_500']}/500")
    emit(f"  db_v2 recommends Linseed in {ld['db_v2_top5_with_linseed']} scenarios; "
         f"true positives {ld['db_v2_linseed_true_positives']}")
    emit(f"  P@5 where db_v2 has Linseed: {ld['p5_db_v1_with_linseed']:.4f} -> {ld['p5_db_v2_with_linseed']:.4f} (n={ld['n_with_linseed']})")
    emit(f"  P@5 elsewhere: {ld['p5_db_v1_without_linseed']:.4f} -> {ld['p5_db_v2_without_linseed']:.4f} (n={ld['n_without_linseed']})")
    emit("\n=== CEILING (out-of-vocab share of R_test_all top-5) ===")
    emit(f"  db_v1 vocab: {res['ceiling']['R_test_all_oov_share_db_v1']:.4f}")
    emit(f"  db_v2 vocab: {res['ceiling']['R_test_all_oov_share_db_v2']:.4f}")
    emit(f"  Linseed in reference: {res['ceiling']['Linseed_in_reference_cells']} cells, "
         f"{res['ceiling']['Linseed_total_slots']} slots")
    emit("\n=== SEASON VALIDITY / HARD VIOLATION (10,000 C3, GT v1.2) ===")
    for k in ["db_v1|strict", "db_v2|strict", "db_v1|lenient", "db_v2|lenient"]:
        d = res["season_validity"][k]
        emit(f"  {k:14s} overall {d['overall']:.5f}  hard {d['hard_violating']}/{d['hard_evaluated']}"
             f" = {d['hard_violation_rate']:.5f}  Kharif {d['per_season']['Kharif']:.4f}"
             f" Rabi {d['per_season']['Rabi']:.4f} Zaid {d['per_season']['Zaid']:.4f}")
    OUT_TXT.write_text("\n".join(_lines) + "\n", encoding="utf-8")
    emit(f"\nwrote {OUT_JSON}")
    emit(f"wrote {OUT_TXT}")


def out_oov(reg, ref):
    vals = []
    for v in ref.values():
        if not v:
            continue
        o = sum(1 for c in v if c not in reg)
        vals.append(o / min(5, len(v)))
    return float(np.mean(vals))


if __name__ == "__main__":
    main()
