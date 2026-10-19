"""STAGE A INTERIM METRICS (gate; NO API calls).

Llama C0/C0b/C1a/C2a/C2b + C3 reference on the same 150 nested scenarios
(llm_subset[:150]). Season-validity rate and hard-violation rate, each STRICT and
LENIENT, each per-protocol and ITT, with 95% bootstrap CIs and n per cell. Then the
four pre-registered paired contrasts (Holm family), reported WITH and WITHOUT the
40 pilot_dev scenarios.

Metric semantics follow PROTOCOL.md 8.9/8.11 and recompute_season_validity_cited_v2.py
(GT tables v1.1). Per-protocol = valid, untruncated JSON only. ITT = all planned
scenario-runs; invalid/truncated counts as season-validity 0 and hard-violation 1.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np

from eval.statistics import bootstrap_ci, cliffs_delta, holm_bonferroni, wilcoxon_paired

GT = ROOT / "eval/data/ground_truth"
DET_DIR = ROOT / "eval/runs/archive_v2/deterministic"
EVID_DIR = ROOT / "eval/runs/archive_v2/evidence"
LLAMA = ROOT / "eval/runs/eval_llama-3.2-11b/results.json"
PILOT = ROOT / "eval/results/pilot_scenario_sets.json"

SEASON_TABLE = GT / "crop_season_table_v1.1.csv"
HARD_TABLE = GT / "hard_constraints_v1.1.csv"

CONDS = ["C0", "C0b", "C1a", "C2a", "C2b"]
PAIRS = [("C2a", "C0b"), ("C2a", "C1a"), ("C2b", "C0b"), ("C2b", "C1a")]


def read_table(p):
    with p.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


SEASON_ROWS = read_table(SEASON_TABLE)
HARD_ROWS = read_table(HARD_TABLE)


def season_status(crop, season):
    rows_here = [r for r in SEASON_ROWS if r["crop"] == crop and r["season"] == season]
    if any(r["status"] == "cited" for r in rows_here):
        return "valid"
    if rows_here:
        return "unknown"
    if not any(r["crop"] == crop for r in SEASON_ROWS):
        return "unknown"
    return "invalid"


def season_validity(top5, season, mode):
    num = den = 0
    for p in top5:
        st = season_status(p, season)
        if st == "valid":
            num += 1
            den += 1
        elif st == "invalid":
            den += 1
        elif mode == "strict":
            den += 1
    return (num / den) if den else 0.0


def hard_violation(top5, season, drought, flood, mode):
    season_c = [r for r in HARD_ROWS if r["constraint_type"] == "season"]
    drought_c = [r for r in HARD_ROWS if r["constraint_type"] == "drought"]
    flood_c = [r for r in HARD_ROWS if r["constraint_type"] == "flood"]
    viol = den = 0
    for p in top5:
        relevant = (
            [r for r in season_c if r["crop"] == p and r["condition"] == season]
            + ([r for r in drought_c if r["crop"] == p] if drought else [])
            + ([r for r in flood_c if r["crop"] == p] if flood else [])
        )
        cited_hit = any(r["status"] == "cited" for r in relevant)
        unknown_only = bool(relevant) and not cited_hit
        den += 1
        if cited_hit:
            viol += 1
        elif mode == "strict" and unknown_only:
            viol += 1
        elif mode == "lenient" and unknown_only:
            den -= 1
    return (viol / den) if den else 0.0


def main():
    subset = [json.loads(l) for l in (ROOT / "eval/data/llm_subset.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()][:150]
    sids = [s["scenario_id"] for s in subset]
    season = {s["scenario_id"]: s["season_stratum"] for s in subset}

    pilot = json.load(open(PILOT, encoding="utf-8"))["pilot_union"]
    pilot_set = set(pilot)

    # risk flags
    flags = {}
    for sid in sids:
        ev = json.loads((EVID_DIR / f"{sid}.json").read_text(encoding="utf-8"))
        risk = ev.get("risk") or {}
        try:
            d = float(risk.get("drought_z_score_30d", 0)) <= -1.5
            f = float(risk.get("flood_probability", 0)) >= 0.40
        except (TypeError, ValueError):
            d, f = False, False
        flags[sid] = (d, f)

    # C3 reference top5
    c3 = {}
    for sid in sids:
        res = json.loads((DET_DIR / f"{sid}.json").read_text(encoding="utf-8"))
        c3[sid] = (res.get("ablations", {}).get("full_repo") or {}).get("top5") or []

    # Llama records
    recs = json.load(open(LLAMA, encoding="utf-8"))
    by = {}
    for r in recs:
        if r.get("repeat", 0) == 0 and r["condition"] in CONDS and r["scenario_id"] in season:
            by[(r["condition"], r["scenario_id"])] = r

    def usable(r):
        if r is None:
            return False
        if r.get("error"):
            return False
        p = r.get("parsed") or {}
        return bool(p.get("valid_json")) and not r.get("truncated")

    def top5_of(r):
        p = (r or {}).get("parsed") or {}
        return [str(x) for x in (p.get("top5") or [])]

    # Per-scenario metric values (pp = per-protocol, itt = intention-to-treat)
    def cell_values(cond, mode, analysis, subset_sids):
        sv, hv = [], []
        for sid in subset_sids:
            if cond == "C3":
                t5 = c3[sid]
            else:
                t5 = top5_of(by.get((cond, sid)))
            usable_here = cond == "C3" or usable(by.get((cond, sid)))
            if analysis == "pp":
                if not usable_here or not t5:
                    continue
                sv.append(season_validity(t5, season[sid], mode))
                d, f = flags[sid]
                hv.append(hard_violation(t5, season[sid], d, f, mode))
            else:  # itt
                if not usable_here or not t5:
                    sv.append(0.0)
                    hv.append(1.0)
                else:
                    sv.append(season_validity(t5, season[sid], mode))
                    d, f = flags[sid]
                    hv.append(hard_violation(t5, season[sid], d, f, mode))
        return np.array(sv), np.array(hv)

    def report_block(subset_sids, label):
        print(f"\n{'='*100}\n{label}  (n scenarios = {len(subset_sids)})\n{'='*100}")
        results = {}
        for mode in ("strict", "lenient"):
            for analysis in ("pp", "itt"):
                print(f"\n--- {mode.upper()} | {'per-protocol' if analysis=='pp' else 'ITT'} ---")
                print(f"{'cond':5s} {'season-validity [95% CI]':34s} {'n_sv':>5s} {'hard-violation [95% CI]':34s} {'n_hv':>5s}")
                for cond in CONDS + ["C3"]:
                    sv, hv = cell_values(cond, mode, analysis, subset_sids)
                    if len(sv) < 2:
                        print(f"{cond:5s} (insufficient n)")
                        continue
                    svm, svl, svu = bootstrap_ci(list(sv), n_resamples=10000, seed=42)
                    hvm, hvl, hvu = bootstrap_ci(list(hv), n_resamples=10000, seed=42)
                    print(f"{cond:5s} {svm:.3f} [{svl:.3f},{svu:.3f}]".ljust(5 + 34)
                          + f"{len(sv):>5d} {hvm:.3f} [{hvl:.3f},{hvu:.3f}]".ljust(34) + f"{len(hv):>5d}")
                    results[(mode, analysis, cond, "sv")] = (svm, svl, svu, len(sv))
                    results[(mode, analysis, cond, "hv")] = (hvm, hvl, hvu, len(hv))
        return results

    def contrasts_block(subset_sids, label):
        print(f"\n{'='*100}\nCONTRASTS {label}  (n scenarios = {len(subset_sids)})\n{'='*100}")
        for mode in ("strict", "lenient"):
            for analysis in ("pp", "itt"):
                print(f"\n--- {mode.upper()} | {'per-protocol' if analysis=='pp' else 'ITT'} ---")
                for metric, mk in (("season-validity", "sv"), ("hard-violation", "hv")):
                    print(f"  metric={metric}")
                    pvals, rows = [], []
                    for a, b in PAIRS:
                        av, bv = [], []
                        for sid in subset_sids:
                            def val(cond):
                                t5 = c3[sid] if cond == "C3" else top5_of(by.get((cond, sid)))
                                us = cond == "C3" or usable(by.get((cond, sid)))
                                if analysis == "pp":
                                    if not us or not t5:
                                        return None
                                    return season_validity(t5, season[sid], mode) if mk == "sv" else hard_violation(t5, season[sid], *flags[sid], mode)
                                if not us or not t5:
                                    return 0.0 if mk == "sv" else 1.0
                                return season_validity(t5, season[sid], mode) if mk == "sv" else hard_violation(t5, season[sid], *flags[sid], mode)
                            x, y = val(a), val(b)
                            if x is None or y is None:
                                continue
                            av.append(x)
                            bv.append(y)
                        if len(av) < 2:
                            print(f"    {a}-{b}: insufficient n")
                            continue
                        diffs = np.array(av) - np.array(bv)
                        dmean, dlo, dhi = bootstrap_ci(list(diffs), n_resamples=10000, seed=42)
                        delta = cliffs_delta(av, bv)
                        _, p = wilcoxon_paired(av, bv)
                        pvals.append(p)
                        rows.append((a, b, len(av), dmean, dlo, dhi, delta, p))
                    adj = holm_bonferroni(pvals)
                    for (a, b, n, dmean, dlo, dhi, delta, p), pa in zip(rows, adj):
                        print(f"    {a}-{b}: n={n:3d} diff={dmean:+.3f} [{dlo:+.3f},{dhi:+.3f}] "
                              f"Cliff_d={delta:+.3f} p={p:.3e} holm={pa:.3e}")

    all_sids = sids
    nopilot_sids = [s for s in sids if s not in pilot_set]
    print(f"pilot_dev scenarios present in the 150: {len([s for s in sids if s in pilot_set])}")
    report_block(all_sids, "CELLS: WITH 40 pilot_dev")
    contrasts_block(all_sids, "WITH 40 pilot_dev")
    report_block(nopilot_sids, "CELLS: WITHOUT 40 pilot_dev")
    contrasts_block(nopilot_sids, "WITHOUT 40 pilot_dev")


if __name__ == "__main__":
    main()