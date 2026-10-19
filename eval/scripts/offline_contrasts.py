"""OFFLINE items 5-8 (gate; NO API calls).

5. Hard-violation CONTRASTS for Llama C0/C0b/C1a/C2a/C2b, same format as the
   season-validity contrasts: paired diff + 95% bootstrap CI + Cliff's delta +
   Wilcoxon p + Holm(Bonferroni), for STRICT/LENIENT x PP/ITT, WITH and WITHOUT
   the 40 pilot_dev scenarios.
6. EXPLORATORY contrasts C1a-C0b and C2a-C2b (Llama), both metrics.
7. DIAGNOSTIC Fidelity-to-C3 for Llama C2a: top-5 Jaccard + top-1 agreement vs C3
   on the same 150; per-scenario C2a-vs-C3 on season-validity and hard-violation
   (match exactly / beat / lose). Diagnostic only.
8. Unknown-tool rate (C2a/C2b) as a finding, with the C2b-vs-C2a difference.

Metric semantics: PROTOCOL 8.9/8.11, GT tables v1.1. Reuses the exact metric and
statistics code from stage_a_interim_metrics.py (single source of truth).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from eval.statistics import bootstrap_ci, cliffs_delta, holm_bonferroni, wilcoxon_paired  # noqa: E402


def _load_stage_a():
    spec = importlib.util.spec_from_file_location(
        "stage_a_interim_metrics", ROOT / "eval/scripts/stage_a_interim_metrics.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sa = _load_stage_a()
season_validity = sa.season_validity
hard_violation = sa.hard_violation

CONDS = sa.CONDS
PAIRS = sa.PAIRS
EXPLORATORY = [("C1a", "C0b"), ("C2a", "C2b")]

LLAMA = ROOT / "eval/runs/eval_llama-3.2-11b/results.json"
PILOT = ROOT / "eval/results/pilot_scenario_sets.json"
DET_DIR = ROOT / "eval/runs/archive_v2/deterministic"
EVID_DIR = ROOT / "eval/runs/archive_v2/evidence"

OUT_TXT = ROOT / "eval/results/offline_contrasts.txt"
OUT_JSON = ROOT / "eval/results/offline_contrasts.json"

_records: list[str] = []


def emit(s: str = "") -> None:
    print(s)
    _records.append(s)


def main() -> None:
    subset = [json.loads(l) for l in (ROOT / "eval/data/llm_subset.jsonl")
              .read_text(encoding="utf-8").splitlines() if l.strip()][:150]
    sids = [s["scenario_id"] for s in subset]
    season = {s["scenario_id"]: s["season_stratum"] for s in subset}
    pilot_set = set(json.load(open(PILOT, encoding="utf-8"))["pilot_union"])

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

    c3 = {}
    for sid in sids:
        res = json.loads((DET_DIR / f"{sid}.json").read_text(encoding="utf-8"))
        c3[sid] = (res.get("ablations", {}).get("full_repo") or {}).get("top5") or []

    recs = json.load(open(LLAMA, encoding="utf-8"))
    by = {}
    for r in recs:
        if r.get("repeat", 0) == 0 and r["condition"] in CONDS and r["scenario_id"] in season:
            by[(r["condition"], r["scenario_id"])] = r

    def usable(r):
        if r is None or r.get("error"):
            return False
        p = r.get("parsed") or {}
        return bool(p.get("valid_json")) and not r.get("truncated")

    def top5_of(r):
        p = (r or {}).get("parsed") or {}
        return [str(x) for x in (p.get("top5") or [])]

    def val(cond, sid, mk, mode, analysis):
        t5 = c3[sid] if cond == "C3" else top5_of(by.get((cond, sid)))
        us = cond == "C3" or usable(by.get((cond, sid)))
        if analysis == "pp":
            if not us or not t5:
                return None
            return season_validity(t5, season[sid], mode) if mk == "sv" \
                else hard_violation(t5, season[sid], *flags[sid], mode)
        if not us or not t5:
            return 0.0 if mk == "sv" else 1.0
        return season_validity(t5, season[sid], mode) if mk == "sv" \
            else hard_violation(t5, season[sid], *flags[sid], mode)

    def contrasts(pairs, subset_sids, headline_metric, family_label, exploratory=False):
        out = []
        for mode in ("strict", "lenient"):
            for analysis in ("pp", "itt"):
                emit(f"\n--- {family_label} | {mode.upper()} | "
                     f"{'per-protocol' if analysis == 'pp' else 'ITT'} ---")
                emit(f"  metric={headline_metric}")
                pvals, rows = [], []
                for a, b in pairs:
                    av, bv = [], []
                    for sid in subset_sids:
                        x = val(a, sid, headline_metric, mode, analysis)
                        y = val(b, sid, headline_metric, mode, analysis)
                        if x is None or y is None:
                            continue
                        av.append(x)
                        bv.append(y)
                    if len(av) < 2:
                        emit(f"    {a}-{b}: insufficient n")
                        continue
                    diffs = np.array(av) - np.array(bv)
                    dm, dlo, dhi = bootstrap_ci(list(diffs), n_resamples=10000, seed=42)
                    delta = cliffs_delta(av, bv)
                    _, p = wilcoxon_paired(av, bv)
                    pvals.append(p)
                    rows.append({"pair": f"{a}-{b}", "n": len(av), "diff": dm, "lo": dlo,
                                 "hi": dhi, "cliff_d": delta, "p": p})
                adj = holm_bonferroni(pvals)
                for row, pa in zip(rows, adj):
                    row["holm"] = pa
                    emit(f"    {row['pair']}: n={row['n']:3d} diff={row['diff']:+.3f} "
                         f"[{row['lo']:+.3f},{row['hi']:+.3f}] Cliff_d={row['cliff_d']:+.3f} "
                         f"p={row['p']:.3e} holm={pa:.3e}")
                    out.append({"mode": mode, "analysis": analysis, "exploratory": exploratory, **row})
        return out

    results: dict = {}
    all_sids = sids
    nopilot_sids = [s for s in sids if s not in pilot_set]

    emit("=" * 100)
    emit("ITEM 5: HARD-VIOLATION CONTRASTS (Llama) - pre-registered pair family")
    emit(f"pairs={PAIRS}  n_scenarios={len(all_sids)}  "
         f"pilot_dev_in_150={len([s for s in sids if s in pilot_set])}")
    emit("=" * 100)
    results["item5_hard_violation_with_pilot"] = contrasts(PAIRS, all_sids, "hv", "WITH 40 pilot_dev")
    results["item5_hard_violation_without_pilot"] = contrasts(PAIRS, nopilot_sids, "hv", "WITHOUT 40 pilot_dev")

    emit("\n" + "=" * 100)
    emit("ITEM 6: EXPLORATORY CONTRASTS (Llama) - C1a-C0b and C2a-C2b")
    emit("=" * 100)
    results["item6_exploratory_sv"] = contrasts(EXPLORATORY, all_sids, "sv", "EXPLORATORY", exploratory=True)
    results["item6_exploratory_hv"] = contrasts(EXPLORATORY, all_sids, "hv", "EXPLORATORY", exploratory=True)

    # ---------------- ITEM 7: Fidelity to C3 (Llama C2a) ----------------
    emit("\n" + "=" * 100)
    emit("ITEM 7 (DIAGNOSTIC ONLY): Fidelity of Llama C2a to C3 on the same 150")
    emit("=" * 100)

    def jaccard(a, b):
        sa_, sb_ = set(a), set(b)
        if not sa_ and not sb_:
            return 1.0
        return len(sa_ & sb_) / len(sa_ | sb_)

    jac_pp, jac_itt, top1_pp, top1_itt, n_pp = [], [], [], [], 0
    for sid in sids:
        r = by.get(("C2a", sid))
        c3t = c3[sid]
        us = usable(r)
        if us:
            n_pp += 1
            t5 = top5_of(r)
            jac_pp.append(jaccard(t5, c3t))
            if t5 and c3t:
                top1_pp.append(1.0 if t5[0] == c3t[0] else 0.0)
        jac_itt.append(jaccard(top5_of(r), c3t) if us else 0.0)
        if us and top5_of(r) and c3t:
            top1_itt.append(1.0 if top5_of(r)[0] == c3t[0] else 0.0)
        else:
            top1_itt.append(0.0)

    emit(f"  C2a per-protocol n={n_pp}/150")
    emit(f"  top-5 Jaccard vs C3 (PP):    {np.mean(jac_pp):.4f}  (n={len(jac_pp)})")
    emit(f"  top-5 Jaccard vs C3 (ITT, invalid=0): {np.mean(jac_itt):.4f}  (n={len(jac_itt)})")
    emit(f"  top-1 agreement vs C3 (PP):  {np.mean(top1_pp):.4f}  (n={len(top1_pp)})")
    emit(f"  top-1 agreement vs C3 (ITT, invalid=0): {np.mean(top1_itt):.4f}  (n={len(top1_itt)})")
    results["item7_fidelity"] = {
        "c2a_pp_n": n_pp,
        "jaccard_pp": float(np.mean(jac_pp)), "jaccard_pp_n": len(jac_pp),
        "jaccard_itt": float(np.mean(jac_itt)), "jaccard_itt_n": len(jac_itt),
        "top1_pp": float(np.mean(top1_pp)), "top1_pp_n": len(top1_pp),
        "top1_itt": float(np.mean(top1_itt)), "top1_itt_n": len(top1_itt),
    }

    def outcome_counts(mk, mode, analysis):
        match = beat = lose = 0
        for sid in sids:
            x = val("C2a", sid, mk, mode, analysis)
            y = val("C3", sid, mk, mode, analysis)
            if x is None or y is None:
                continue
            if abs(x - y) < 1e-9:
                match += 1
            elif (mk == "sv" and x > y) or (mk == "hv" and x < y):
                beat += 1
            else:
                lose += 1
        return {"match": match, "beat": beat, "lose": lose, "n": match + beat + lose}

    for mode in ("strict", "lenient"):
        for analysis in ("pp", "itt"):
            svc = outcome_counts("sv", mode, analysis)
            hvc = outcome_counts("hv", mode, analysis)
            emit(f"  [{mode.upper()} | {analysis.upper()}] season-validity C2a vs C3: "
                 f"match={svc['match']} beat={svc['beat']} lose={svc['lose']} (n={svc['n']}) | "
                 f"hard-violation: match={hvc['match']} beat={hvc['beat']} lose={hvc['lose']} (n={hvc['n']})")
            results.setdefault("item7_per_scenario", {})[f"{mode}_{analysis}"] = {"sv": svc, "hv": hvc}

    # ---------------- ITEM 8: unknown-tool rate ----------------
    emit("\n" + "=" * 100)
    emit("ITEM 8: Unknown-tool rate (Llama) - finding")
    emit("=" * 100)
    names = {}
    unk = {}
    forced = {}
    for cond in ("C2a", "C2b"):
        runs = 0
        unk_runs = 0
        fo = 0
        per = []
        for sid in sids:
            r = by.get((cond, sid))
            if r is None:
                per.append(0.0)
                continue
            runs += 1
            nu = int(r.get("unknown_tool_calls", 0) or 0)
            if nu > 0:
                unk_runs += 1
            per.append(1.0 if nu > 0 else 0.0)
            if r.get("forced_final"):
                fo += 1
            for tc in (r.get("tool_log") or []):
                if tc.get("unknown_tool"):
                    names[tc.get("name")] = names.get(tc.get("name"), 0) + 1
        unk[cond] = (unk_runs, runs)
        forced[cond] = fo
        unk[cond + "_per"] = per
        emit(f"  {cond}: unknown-tool runs = {unk_runs}/{runs} ({unk_runs / runs * 100:.1f}%), "
             f"forced_final runs = {fo}")

    top_named = sorted(names.items(), key=lambda x: -x[1])
    emit(f"  invented tool names (all runs): {top_named}")

    a = np.array(unk["C2a_per"])
    b = np.array(unk["C2b_per"])
    d = b - a
    dm, dlo, dhi = bootstrap_ci(list(d), n_resamples=10000, seed=42)
    delta = cliffs_delta(list(b), list(a))
    _, p = wilcoxon_paired(list(b), list(a))
    emit(f"  C2b - C2a unknown-run rate diff = {dm:+.3f} [{dlo:+.3f},{dhi:+.3f}] "
         f"Cliff_d={delta:+.3f} p={p:.3e}  (paired, n={len(d)})")
    results["item8_unknown"] = {
        "C2a_runs_unknown": unk["C2a"], "C2b_runs_unknown": unk["C2b"],
        "C2a_forced_final": forced["C2a"], "C2b_forced_final": forced["C2b"],
        "invented_names": names,
        "C2b_minus_C2a_rate": {"diff": dm, "lo": dlo, "hi": dhi, "cliff_d": delta, "p": p, "n": len(d)},
    }

    OUT_JSON.write_text(json.dumps(results, indent=2, default=float), encoding="utf-8")
    OUT_TXT.write_text("\n".join(_records) + "\n", encoding="utf-8")
    emit(f"\nwrote {OUT_TXT}")
    emit(f"wrote {OUT_JSON}")


if __name__ == "__main__":
    main()
