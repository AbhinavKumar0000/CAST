"""Divergent-crop provenance impact at n=500 (offline; item 8 follow-up; NO API calls).

The scorer registry (crop_log.csv, uncited) and the cited GT tables (v1.1) agree on most
crops but diverge on exactly three: Groundnut, Urad, Sunflower (the cited GT adds a Zaid
season the scorer registry lacks). See eval/results/gt_provenance_audit.json.

This quantifies how many of the 500 paired scenarios contain any divergent crop in C3's
top-5 or in any LLM condition's top-5, then re-computes the four pre-registered contrasts
after removing (stripping) the divergent crops from every top-5 and reports whether the
headline numbers / claimability move.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from eval.statistics import bootstrap_ci, cliffs_delta, holm_bonferroni, wilcoxon_paired  # noqa: E402


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pm = _load("n500_primary_metrics", "eval/scripts/n500_primary_metrics.py")
season_validity = pm.season_validity
hard_violation = pm.hard_violation
PAIRS = pm.PAIRS
CONDS = pm.CONDS

DIVERGENT = {"Groundnut", "Urad", "Sunflower"}
OUT_TXT = ROOT / "eval/results/n500_divergent_crop_impact.txt"
OUT_JSON = ROOT / "eval/results/n500_divergent_crop_impact.json"

_records: list[str] = []
RESULTS: dict = {}


def emit(s: str = "") -> None:
    print(s)
    _records.append(s)


def main() -> None:
    subset, sids, season, pilot_set, flags, c3, by = pm.build_data()

    def usable(r):
        if r is None or r.get("error"):
            return False
        p = r.get("parsed") or {}
        return bool(p.get("valid_json")) and not r.get("truncated")

    def top5_of(r):
        p = (r or {}).get("parsed") or {}
        return [str(x) for x in (p.get("top5") or [])]

    def val(cond, sid, mk, mode, analysis, strip):
        t5 = c3[sid] if cond == "C3" else top5_of(by.get((cond, sid)))
        us = cond == "C3" or usable(by.get((cond, sid)))
        if strip:
            t5 = [c for c in t5 if c not in DIVERGENT]
        if analysis == "pp":
            if not us or not t5:
                return None
        else:
            if not us or not t5:
                return 0.0 if mk == "sv" else 1.0
        return season_validity(t5, season[sid], mode) if mk == "sv" \
            else hard_violation(t5, season[sid], *flags[sid], mode)

    emit("=" * 100)
    emit("DIVERGENT-CROP PROVENANCE IMPACT (Nemotron n=500; crops = Groundnut, Urad, Sunflower)")
    emit("=" * 100)
    emit("  (cited GT adds a Zaid season for these three; the uncited scorer registry lacks it)")

    per_cond = {}
    present_sids: Counter = Counter()
    crop_cond: Counter = Counter()
    for cond in CONDS + ["C3"]:
        n_scen = 0
        crops: Counter = Counter()
        for sid in sids:
            t5 = c3[sid] if cond == "C3" else [str(x) for x in (((by.get((cond, sid)) or {}).get("parsed") or {}).get("top5") or [])]
            hit = set(t5) & DIVERGENT
            if hit:
                n_scen += 1
                present_sids[sid] += 1
                for c in hit:
                    crops[c] += 1
                    crop_cond[(c, cond)] += 1
        per_cond[cond] = {"scenarios_with_divergent": n_scen, "by_crop": dict(crops)}
        emit(f"  {cond:4s}: scenarios with >=1 divergent crop in top-5 = {n_scen}/500 "
             f"({n_scen/500*100:.1f}%)  {dict(crops)}")

    def llm_top5(cond, sid):
        return [str(x) for x in (((by.get((cond, sid)) or {}).get("parsed") or {}).get("top5") or [])]

    any_llm = sum(1 for sid in sids if any(set(llm_top5(c, sid)) & DIVERGENT for c in CONDS))
    c3_sids = sum(1 for sid in sids if set(c3[sid]) & DIVERGENT)
    either = sum(1 for sid in sids if present_sids[sid] > 0)
    emit(f"\n  C3 top-5 has a divergent crop in {c3_sids}/500 scenarios; "
         f"any LLM condition top-5 in {any_llm}/500; either in {either}/500.")
    RESULTS["presence"] = {"per_condition": per_cond, "c3_sids": c3_sids,
                           "any_llm_sids": any_llm, "either_sids": either,
                           "per_crop_per_condition": {f"{c}|{k}": v for (c, k), v in crop_cond.items()}}

    def contrasts(strip):
        out = {}
        for mode in ("strict", "lenient"):
            for analysis in ("pp", "itt"):
                for metric in ("sv", "hv"):
                    pvals, rows = [], []
                    for a, b in PAIRS:
                        av, bv = [], []
                        for sid in sids:
                            x = val(a, sid, metric, mode, analysis, strip)
                            y = val(b, sid, metric, mode, analysis, strip)
                            if x is None or y is None:
                                continue
                            av.append(x)
                            bv.append(y)
                        if len(av) < 2:
                            continue
                        diffs = np.array(av) - np.array(bv)
                        dm, lo, hi = bootstrap_ci(list(diffs), n_resamples=10000, seed=42)
                        delta = cliffs_delta(av, bv)
                        _, p = wilcoxon_paired(av, bv)
                        pvals.append(p)
                        rows.append({"pair": f"{a}-{b}", "n": len(av), "diff": float(dm),
                                     "lo": float(lo), "hi": float(hi),
                                     "cliff_d": float(delta), "p": float(p)})
                    adj = holm_bonferroni(pvals) if pvals else []
                    for row, pa in zip(rows, adj):
                        row["holm"] = float(pa)
                        out[f"{mode}_{analysis}_{metric}_{row['pair']}"] = row
        return out

    base = contrasts(False)
    strip = contrasts(True)
    RESULTS["contrasts_baseline"] = base
    RESULTS["contrasts_stripped"] = strip

    emit("\n" + "=" * 100)
    emit("HEADLINE MOVEMENT: pre-registered contrasts, baseline vs divergent-crops-removed")
    emit("=" * 100)
    for mode in ("strict", "lenient"):
        for analysis in ("pp", "itt"):
            for metric in ("sv", "hv"):
                emit(f"\n--- {mode.upper()} | {'per-protocol' if analysis=='pp' else 'ITT'} | {metric} ---")
                for a, b in PAIRS:
                    k = f"{mode}_{analysis}_{metric}_{a}-{b}"
                    if k not in base or k not in strip:
                        continue
                    rb, rs = base[k], strip[k]
                    moved = rs["diff"] - rb["diff"]
                    emit(f"  {a}-{b}: base {rb['diff']:+.3f} [holm {rb['holm']:.3e}] -> "
                         f"stripped {rs['diff']:+.3f} [holm {rs['holm']:.3e}]  "
                         f"delta={moved:+.3f}  sign_flip="
                         f"{'YES' if np.sign(rb['diff']) != np.sign(rs['diff']) else 'no'}")

    def claimable(c):
        out = {}
        for mode in ("strict", "lenient"):
            for metric in ("sv", "hv"):
                for a, b in PAIRS:
                    kp = f"{mode}_pp_{metric}_{a}-{b}"
                    ki = f"{mode}_itt_{metric}_{a}-{b}"
                    if kp not in c or ki not in c:
                        out[f"{mode}_{metric}_{a}-{b}"] = False
                        continue
                    same = (np.sign(c[kp]["diff"]) == np.sign(c[ki]["diff"])) and c[kp]["diff"] != 0
                    out[f"{mode}_{metric}_{a}-{b}"] = bool(same and c[kp]["holm"] < 0.05
                                                           and c[ki]["holm"] < 0.05)
        return out

    cb, cs = claimable(base), claimable(strip)
    emit("\n" + "=" * 100)
    emit("CLAIMABILITY (sign+significance, PP&ITT): baseline vs stripped")
    emit("=" * 100)
    for k in cb:
        emit(f"  {k}: baseline={'CLAIM' if cb[k] else 'no '} stripped={'CLAIM' if cs[k] else 'no '}"
             f"{'  FLIP' if cb[k] != cs[k] else ''}")
    RESULTS["claimability_baseline"] = cb
    RESULTS["claimability_stripped"] = cs

    OUT_JSON.write_text(json.dumps(RESULTS, indent=2, default=float), encoding="utf-8")
    OUT_TXT.write_text("\n".join(_records) + "\n", encoding="utf-8")
    emit(f"\nwrote {OUT_TXT}")
    emit(f"wrote {OUT_JSON}")


if __name__ == "__main__":
    main()
