"""Nemotron primary metrics at n=500 (PROTOCOL 8.17 extended to the full subset).

Single verified paired set, MERGED:
  * C1a/C2a/C2b : B1 (150, eval_nemotron-3-ultra/results.json) + B2 (350,
                  eval_nemotron-3-ultra_b2/results.json) -> 500 each.
  * C0/C0b      : pre-fix 500-run records via the run_model cache, verified reusable.
  * C3          : archive_v2/deterministic full_repo top5.
  * risk flags  : archive_v2/evidence.

Reports (WITH and WITHOUT the 40 pilot_dev scenarios): coverage, cells, pre-registered
contrasts (+claimability), exploratory contrasts, fidelity-to-C3, and the cross-model note.
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

B1 = ROOT / "eval/runs/eval_nemotron-3-ultra/results.json"
B2 = ROOT / "eval/runs/eval_nemotron-3-ultra_b2/results.json"
CACHE = ROOT / "eval/cache/llm/nemotron-3-ultra"
PILOT = ROOT / "eval/results/pilot_scenario_sets.json"
DET_DIR = ROOT / "eval/runs/archive_v2/deterministic"
EVID_DIR = ROOT / "eval/runs/archive_v2/evidence"
OUT_TXT = ROOT / "eval/results/n500_primary_metrics.txt"
OUT_JSON = ROOT / "eval/results/n500_primary_metrics.json"

_records: list[str] = []
RESULTS: dict = {}


def emit(s: str = "") -> None:
    print(s)
    _records.append(s)


def build_data():
    subset = [json.loads(l) for l in (ROOT / "eval/data/llm_subset.jsonl")
              .read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(subset) == 500, len(subset)
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
    by = {}
    for src in (B1, B2):
        for r in json.load(open(src, encoding="utf-8")):
            if r.get("repeat", 0) == 0 and r["condition"] in ("C1a", "C2a", "C2b") and r["scenario_id"] in season:
                by[(r["condition"], r["scenario_id"])] = r
    for fp in CACHE.glob("*.json"):
        try:
            r = json.load(fp.open(encoding="utf-8"))
        except Exception:
            continue
        if (r.get("repeat", 0) == 0 and r.get("condition") in ("C0", "C0b")
                and r.get("scenario_id") in season and (r["condition"], r["scenario_id"]) not in by):
            by[(r["condition"], r["scenario_id"])] = r
    return subset, sids, season, pilot_set, flags, c3, by


def main() -> None:
    subset, sids, season, pilot_set, flags, c3, by = build_data()

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

    # ---------------- item 1 ----------------
    emit("=" * 100)
    emit("ITEM 1: MERGE / COVERAGE (Nemotron n=500)")
    emit("=" * 100)
    for cond in CONDS + ["C3"]:
        emit(f"  {cond:4s}: distinct sids = "
             f"{sum(1 for s in sids if cond == 'C3' or (cond, s) in by)}/500")
    for cond in CONDS:
        emit(f"  {cond:4s}: PP-usable n = {sum(1 for s in sids if usable(by.get((cond, s))))}/500 "
             f"; ITT n = {sum(1 for s in sids if (cond, s) in by)}/500")
    emit(f"  C3  : non-empty top5 = {sum(1 for s in sids if c3[s])}/500")

    # ---------------- item 2 ----------------
    def cells_block(subset_sids, label):
        emit(f"\n{'='*100}\nITEM 2 CELLS: {label}  (n scenarios = {len(subset_sids)})\n{'='*100}")
        for mode in ("strict", "lenient"):
            for analysis in ("pp", "itt"):
                emit(f"\n--- {mode.upper()} | {'per-protocol' if analysis=='pp' else 'ITT'} ---")
                emit(f"{'cond':5s} {'season-validity [95% CI]':34s} {'n_sv':>5s} "
                     f"{'hard-violation [95% CI]':34s} {'n_hv':>5s}")
                for cond in CONDS + ["C3"]:
                    sv = np.array([v for sid in subset_sids
                                   if (v := val(cond, sid, "sv", mode, analysis)) is not None])
                    hv = np.array([v for sid in subset_sids
                                   if (v := val(cond, sid, "hv", mode, analysis)) is not None])
                    if len(sv) < 2:
                        emit(f"{cond:5s} (insufficient n)")
                        continue
                    svm, svl, svu = bootstrap_ci(list(sv), n_resamples=10000, seed=42)
                    hvm, hvl, hvu = bootstrap_ci(list(hv), n_resamples=10000, seed=42)
                    emit(f"{cond:5s} {svm:.3f} [{svl:.3f},{svu:.3f}]".ljust(5 + 34)
                         + f"{len(sv):>5d} {hvm:.3f} [{hvl:.3f},{hvu:.3f}]".ljust(34) + f"{len(hv):>5d}")
                    RESULTS.setdefault(f"cells_{label}", {})[f"{mode}_{analysis}_{cond}"] = {
                        "sv": [svm, svl, svu, len(sv)], "hv": [hvm, hvl, hvu, len(hv)]}

    # ---------------- items 3/4 ----------------
    def contrasts_block(pairs, subset_sids, label, exploratory=False):
        emit(f"\n{'='*100}\n{'ITEM 4 EXPLORATORY' if exploratory else 'ITEM 3 PRE-REGISTERED'} "
             f"CONTRASTS: {label}  (n scenarios = {len(subset_sids)})\n{'='*100}")
        nested = {}
        for mode in ("strict", "lenient"):
            for analysis in ("pp", "itt"):
                emit(f"\n--- {mode.upper()} | {'per-protocol' if analysis=='pp' else 'ITT'} ---")
                for metric, mk in (("season-validity", "sv"), ("hard-violation", "hv")):
                    emit(f"  metric={metric}")
                    pvals, rows = [], []
                    for a, b in pairs:
                        av, bv = [], []
                        for sid in subset_sids:
                            x = val(a, sid, mk, mode, analysis)
                            y = val(b, sid, mk, mode, analysis)
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
                        rows.append({"pair": f"{a}-{b}", "n": len(av), "diff": float(dm),
                                     "lo": float(dlo), "hi": float(dhi), "cliff_d": float(delta), "p": float(p)})
                    adj = holm_bonferroni(pvals)
                    for row, pa in zip(rows, adj):
                        row["holm"] = float(pa)
                        emit(f"    {row['pair']}: n={row['n']:3d} diff={row['diff']:+.3f} "
                             f"[{row['lo']:+.3f},{row['hi']:+.3f}] Cliff_d={row['cliff_d']:+.3f} "
                             f"p={row['p']:.3e} holm={pa:.3e}")
                        nested.setdefault((mode, analysis, mk), {})[row["pair"]] = row
        return nested

    def claimability(pre, expl, label):
        emit(f"\n--- CLAIMABILITY ({label}) - PP and ITT must AGREE in sign AND be significant "
             f"(Holm<0.05 both); primary family = {len(PAIRS)} pre-registered pairs ---")
        out = {}
        for tag, nested, pairs in (("prereg", pre, PAIRS), ("explor", expl, EXPLORATORY)):
            for mode in ("strict", "lenient"):
                for mk in ("sv", "hv"):
                    pp = nested.get((mode, "pp", mk), {})
                    itt = nested.get((mode, "itt", mk), {})
                    for a, b in pairs:
                        k = f"{a}-{b}"
                        key = f"{tag}_{mode}_{mk}_{k}"
                        if k not in pp or k not in itt:
                            out[key] = {"claimable": False, "note": "insufficient n"}
                            emit(f"  [{tag} {mode:7s}|{mk}] {k}: insufficient n")
                            continue
                        rp, ri = pp[k], itt[k]
                        same_sign = (np.sign(rp["diff"]) == np.sign(ri["diff"])) and rp["diff"] != 0
                        sig_pp = rp["holm"] < 0.05
                        sig_itt = ri["holm"] < 0.05
                        claimable = bool(same_sign and sig_pp and sig_itt)
                        out[key] = {"pp": {"diff": rp["diff"], "holm": rp["holm"], "n": rp["n"]},
                                    "itt": {"diff": ri["diff"], "holm": ri["holm"], "n": ri["n"]},
                                    "same_sign": bool(same_sign), "claimable": claimable}
                        emit(f"  [{tag} {mode:7s}|{mk}] {k}: PP {rp['diff']:+.3f} holm={rp['holm']:.3e} "
                             f"(n={rp['n']}) | ITT {ri['diff']:+.3f} holm={ri['holm']:.3e} (n={ri['n']})"
                             f" -> {'CLAIMABLE' if claimable else 'not'}")
        return out

    # ---------------- item 5 ----------------
    def jaccard(a, b):
        sa_, sb_ = set(a), set(b)
        return 1.0 if (not sa_ and not sb_) else len(sa_ & sb_) / len(sa_ | sb_)

    def fidelity_block(subset_sids, label, cond="C2a"):
        emit(f"\n{'='*100}\nITEM 5 FIDELITY-to-C3 ({cond} vs C3 full_repo): {label} "
             f"(n = {len(subset_sids)})\n{'='*100}")
        jac_pp, jac_itt, t1_pp, t1_itt, n_pp = [], [], [], [], 0
        for sid in subset_sids:
            r = by.get((cond, sid))
            c3t = c3[sid]
            us = usable(r)
            t5 = top5_of(r)
            if us:
                n_pp += 1
                jac_pp.append(jaccard(t5, c3t))
                if t5 and c3t:
                    t1_pp.append(1.0 if t5[0] == c3t[0] else 0.0)
            jac_itt.append(jaccard(t5, c3t) if us else 0.0)
            t1_itt.append(1.0 if (us and t5 and c3t and t5[0] == c3t[0]) else 0.0)
        emit(f"  {cond} per-protocol n = {n_pp}/{len(subset_sids)}")
        emit(f"  top-5 Jaccard vs C3 (PP) = {np.mean(jac_pp):.4f} (n={len(jac_pp)}) | "
             f"(ITT, invalid=0) = {np.mean(jac_itt):.4f}")
        emit(f"  top-1 agreement vs C3 (PP) = {np.mean(t1_pp):.4f} (n={len(t1_pp)}) | "
             f"(ITT, invalid=0) = {np.mean(t1_itt):.4f}")
        out = {"pp_n": n_pp, "jaccard_pp": float(np.mean(jac_pp)), "jaccard_itt": float(np.mean(jac_itt)),
               "top1_pp": float(np.mean(t1_pp)), "top1_itt": float(np.mean(t1_itt))}

        def outcome_counts(mk, mode, analysis):
            m = b = l = 0
            for sid in subset_sids:
                x = val(cond, sid, mk, mode, analysis)
                y = val("C3", sid, mk, mode, analysis)
                if x is None or y is None:
                    continue
                if abs(x - y) < 1e-9:
                    m += 1
                elif (mk == "sv" and x > y) or (mk == "hv" and x < y):
                    b += 1
                else:
                    l += 1
            return {"match": m, "beat": b, "lose": l, "n": m + b + l}

        for mode in ("strict", "lenient"):
            for analysis in ("pp", "itt"):
                svc = outcome_counts("sv", mode, analysis)
                hvc = outcome_counts("hv", mode, analysis)
                nn = svc["n"] or 1
                emit(f"  [{mode.upper()}|{analysis.upper()}] sv C2a vs C3: match={svc['match']} "
                     f"({svc['match']/nn*100:.1f}%) beat={svc['beat']} ({svc['beat']/nn*100:.1f}%) "
                     f"lose={svc['lose']} ({svc['lose']/nn*100:.1f}%) n={svc['n']} || hv: "
                     f"match={hvc['match']} ({hvc['match']/nn*100:.1f}%) beat={hvc['beat']} "
                     f"({hvc['beat']/nn*100:.1f}%) lose={hvc['lose']} ({hvc['lose']/nn*100:.1f}%)")
                out.setdefault("per_scenario", {})[f"{mode}_{analysis}"] = {"sv": svc, "hv": hvc}
        return out

    all_sids = sids
    nopilot_sids = [s for s in sids if s not in pilot_set]

    emit(f"\nITEM 7 (cross-model scope): Nemotron is n=500 (full llm_subset); Llama is n=150. "
         f"Any cross-model comparison is reported at n=150 (common support). "
         f"pilot_dev in the 500 = {len([s for s in sids if s in pilot_set])}; "
         f"WITHOUT-pilot n = {len(nopilot_sids)}.")

    for label, sset in (("WITH pilot_dev", all_sids), ("WITHOUT pilot_dev", nopilot_sids)):
        cells_block(sset, label)
        pre = contrasts_block(PAIRS, sset, label)
        expl = contrasts_block(EXPLORATORY, sset, label, exploratory=True)
        RESULTS[f"contrasts_{label}"] = {f"{m}_{an}_{mk}_{p}": v for (m, an, mk), d in pre.items()
                                         for p, v in d.items()}
        RESULTS[f"exploratory_{label}"] = {f"{m}_{an}_{mk}_{p}": v for (m, an, mk), d in expl.items()
                                           for p, v in d.items()}
        RESULTS[f"claimability_{label}"] = claimability(pre, expl, label)
        RESULTS[f"fidelity_{label}"] = fidelity_block(sset, label)

    # ---------------- C1a truncation ----------------
    c1a = [by.get(("C1a", sid)) for sid in sids]
    trunc = sum(1 for r in c1a if r and r.get("truncated"))
    valid = sum(1 for r in c1a if r and (r.get("parsed") or {}).get("valid_json"))
    ppv = sum(1 for r in c1a if usable(r))
    emit(f"\nC1a 8192-truncation at n=500: truncated={trunc}/500 ({trunc/500*100:.1f}%), "
         f"valid_json={valid}/500, PP-usable={ppv}/500, ITT n=500")
    RESULTS["c1a_500"] = {"trunc": trunc, "valid_json": valid, "pp_usable": ppv}

    RESULTS["provenance"] = {
        "c1a_c2a_c2b": "B1 eval_nemotron-3-ultra/results.json (150) + B2 eval_nemotron-3-ultra_b2/results.json (350)",
        "c0_c0b": "eval/cache/llm/nemotron-3-ultra (pre-fix run; verified reusable)",
        "note": "B1 exit=1 on final flush was a benign file-lock race; results.json intact (1050 records).",
    }
    OUT_JSON.write_text(json.dumps(RESULTS, indent=2, default=float), encoding="utf-8")
    OUT_TXT.write_text("\n".join(_records) + "\n", encoding="utf-8")
    emit(f"\nwrote {OUT_TXT}")
    emit(f"wrote {OUT_JSON}")


if __name__ == "__main__":
    main()
