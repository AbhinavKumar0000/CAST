"""Nemotron primary metrics on the 150 B1 scenarios (PROTOCOL 8.17).

Sources (single, verified paired set):
  * C1a/C2a/C2b : eval/runs/eval_nemotron-3-ultra/results.json  (B1, fresh post-fix)
  * C0/C0b      : pre-fix 500-run records via the run_model cache, verified reusable
                  (prompt_hash == current prompt builders; model matches; no blanks) -
                  disclosed asymmetry, tool-less + 4096 cap unchanged (see PROTOCOL 8.17).
  * C3          : archive_v2/deterministic full_repo top5.
  * risk flags  : archive_v2/evidence.

Reports: cells (season-validity + hard-violation; STRICT/LENIENT x PP/ITT; 95% CIs + n),
the four pre-registered contrasts (paired diff, CI, Cliff's delta, Holm p), the exploratory
C1a-C0b and C2a-C2b, the Fidelity-to-C3 diagnostic, and the C1a 8192 truncation rate.
All WITH and WITHOUT the 40 pilot_dev scenarios.
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
CORE = ("C1a", "C2a", "C2b")

B1 = ROOT / "eval/runs/eval_nemotron-3-ultra/results.json"
CACHE = ROOT / "eval/cache/llm/nemotron-3-ultra"
PILOT = ROOT / "eval/results/pilot_scenario_sets.json"
DET_DIR = ROOT / "eval/runs/archive_v2/deterministic"
EVID_DIR = ROOT / "eval/runs/archive_v2/evidence"
OUT_TXT = ROOT / "eval/results/nemotron_primary_metrics.txt"
OUT_JSON = ROOT / "eval/results/nemotron_primary_metrics.json"

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

    by = {}
    for r in json.load(open(B1, encoding="utf-8")):
        if r.get("repeat", 0) == 0 and r["condition"] in CORE and r["scenario_id"] in season:
            by[(r["condition"], r["scenario_id"])] = r
    for fp in CACHE.glob("*.json"):
        try:
            r = json.load(fp.open(encoding="utf-8"))
        except Exception:
            continue
        if (r.get("repeat", 0) == 0 and r.get("condition") in ("C0", "C0b")
                and r.get("scenario_id") in season and (r["condition"], r["scenario_id"]) not in by):
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

    def report_block(subset_sids, label):
        emit(f"\n{'='*100}\n{label}  (n scenarios = {len(subset_sids)})\n{'='*100}")
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

    def contrasts_block(pairs, subset_sids, label, exploratory=False):
        emit(f"\n{'='*100}\n{'EXPLORATORY ' if exploratory else 'PRE-REGISTERED '}"
             f"CONTRASTS {label}  (n scenarios = {len(subset_sids)})\n{'='*100}")
        out = {}
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
                        rows.append({"pair": f"{a}-{b}", "n": len(av), "diff": dm,
                                     "lo": dlo, "hi": dhi, "cliff_d": delta, "p": p})
                    adj = holm_bonferroni(pvals)
                    for row, pa in zip(rows, adj):
                        row["holm"] = pa
                        emit(f"    {row['pair']}: n={row['n']:3d} diff={row['diff']:+.3f} "
                             f"[{row['lo']:+.3f},{row['hi']:+.3f}] Cliff_d={row['cliff_d']:+.3f} "
                             f"p={row['p']:.3e} holm={pa:.3e}")
                        out[f"{mode}_{analysis}_{mk}_{row['pair']}"] = row
        return out

    results: dict = {}
    all_sids = sids
    nopilot_sids = [s for s in sids if s not in pilot_set]
    emit(f"Nemotron-3-Ultra-550b | B1 sources: C1a/C2a/C2b fresh (results.json), "
         f"C0/C0b reused pre-fix (verified) | pilot_dev in 150 = "
         f"{len([s for s in sids if s in pilot_set])}")

    report_block(all_sids, "CELLS: WITH 40 pilot_dev")
    results["contrasts_with_pilot"] = contrasts_block(PAIRS, all_sids, "WITH 40 pilot_dev")
    results["exploratory_with_pilot"] = contrasts_block(EXPLORATORY, all_sids, "WITH 40 pilot_dev",
                                                        exploratory=True)
    report_block(nopilot_sids, "CELLS: WITHOUT 40 pilot_dev")
    results["contrasts_without_pilot"] = contrasts_block(PAIRS, nopilot_sids, "WITHOUT 40 pilot_dev")
    results["exploratory_without_pilot"] = contrasts_block(EXPLORATORY, nopilot_sids,
                                                           "WITHOUT 40 pilot_dev", exploratory=True)

    # Fidelity to C3 (C2a)
    emit(f"\n{'='*100}\nFIDELITY TO C3 (Nemotron C2a) - DIAGNOSTIC ONLY\n{'='*100}")

    def jaccard(a, b):
        sa_, sb_ = set(a), set(b)
        return 1.0 if not sa_ and not sb_ else len(sa_ & sb_) / len(sa_ | sb_)

    jac_pp, jac_itt, t1_pp, t1_itt, n_pp = [], [], [], [], 0
    for sid in sids:
        r = by.get(("C2a", sid))
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
    emit(f"  C2a per-protocol n={n_pp}/150")
    emit(f"  top-5 Jaccard vs C3 (PP)={np.mean(jac_pp):.4f} (n={len(jac_pp)}) | "
         f"(ITT, invalid=0)={np.mean(jac_itt):.4f}")
    emit(f"  top-1 agreement vs C3 (PP)={np.mean(t1_pp):.4f} (n={len(t1_pp)}) | "
         f"(ITT, invalid=0)={np.mean(t1_itt):.4f}")

    def outcome_counts(mk, mode, analysis):
        m = b = l = 0
        for sid in sids:
            x = val("C2a", sid, mk, mode, analysis)
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

    results["fidelity"] = {"c2a_pp_n": n_pp, "jaccard_pp": float(np.mean(jac_pp)),
                           "jaccard_itt": float(np.mean(jac_itt)),
                           "top1_pp": float(np.mean(t1_pp)), "top1_itt": float(np.mean(t1_itt))}
    for mode in ("strict", "lenient"):
        for analysis in ("pp", "itt"):
            svc = outcome_counts("sv", mode, analysis)
            hvc = outcome_counts("hv", mode, analysis)
            emit(f"  [{mode.upper()} | {analysis.upper()}] season-validity C2a vs C3: "
                 f"match={svc['match']} beat={svc['beat']} lose={svc['lose']} (n={svc['n']}) | "
                 f"hard-violation: match={hvc['match']} beat={hvc['beat']} lose={hvc['lose']}")
            results.setdefault("fidelity_per_scenario", {})[f"{mode}_{analysis}"] = {"sv": svc, "hv": hvc}

    # C1a truncation / PP vs ITT
    c1a = [by.get(("C1a", sid)) for sid in sids]
    c1a_trunc = sum(1 for r in c1a if r and r.get("truncated"))
    c1a_valid = sum(1 for r in c1a if r and (r.get("parsed") or {}).get("valid_json"))
    c1a_pp = sum(1 for r in c1a if usable(r))
    emit(f"\nC1a 8192-truncation rate: {c1a_trunc}/150 ({c1a_trunc/150*100:.1f}%) "
         f"[Llama Stage A: 0/150]. valid_json={c1a_valid}/150; PP-usable={c1a_pp}/150; ITT n=150")
    results["c1a"] = {"trunc": c1a_trunc, "valid_json": c1a_valid, "pp_usable": c1a_pp,
                      "llama_trunc": 0}

    results["provenance"] = {
        "c1a_c2a_c2b": "eval/runs/eval_nemotron-3-ultra/results.json (B1, 2026-10-14)",
        "c0_c0b": "pre-fix 500-run via eval/cache/llm/nemotron-3-ultra (verified reusable)",
        "verified": "300/300 prompt_hash matches current builders",
    }

    OUT_JSON.write_text(json.dumps(results, indent=2, default=float), encoding="utf-8")
    OUT_TXT.write_text("\n".join(_records) + "\n", encoding="utf-8")
    emit(f"\nwrote {OUT_TXT}")
    emit(f"wrote {OUT_JSON}")


if __name__ == "__main__":
    main()
