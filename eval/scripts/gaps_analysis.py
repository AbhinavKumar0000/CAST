"""Offline gaps before reading the Nemotron result.

GAP 1: Nemotron pre-registered contrasts under ITT as well as PP (paired diff, 95% CI,
       Cliff's delta, Holm p); explicit direction of C2b-C0b / C2b-C1a under ITT; each
       contrast marked CLAIMABLE only where PP and ITT agree (both significant, same sign).
GAP 2: full hard-violation cells + all four contrasts, STRICT x LENIENT x PP x ITT.
GAP 3: Fidelity-to-C3 (top-5 Jaccard, top-1 agreement) for BOTH models, and per-scenario
       C2a-vs-C3 match/beat/lose on season-validity and hard-violation, counts + %.
GAP 4: Nemotron C1a 8192-truncation bias check (season, stress, evidence length) vs Llama.
All WITH and WITHOUT the 40 pilot_dev scenarios.
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


def _load(name, relpath):
    spec = importlib.util.spec_from_file_location(name, ROOT / relpath)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sa = _load("stage_a_interim_metrics", "eval/scripts/stage_a_interim_metrics.py")
season_validity = sa.season_validity
hard_violation = sa.hard_violation
CONDS = ["C0", "C0b", "C1a", "C2a", "C2b"]
PAIRS = sa.PAIRS

LLAMA = ROOT / "eval/runs/eval_llama-3.2-11b/results.json"
NEMO = ROOT / "eval/runs/eval_nemotron-3-ultra/results.json"
NEMO_CACHE = ROOT / "eval/cache/llm/nemotron-3-ultra"
PILOT = ROOT / "eval/results/pilot_scenario_sets.json"
DET_DIR = ROOT / "eval/runs/archive_v2/deterministic"
EVID_DIR = ROOT / "eval/runs/archive_v2/evidence"
OUT_TXT = ROOT / "eval/results/gaps_analysis.txt"
OUT_JSON = ROOT / "eval/results/gaps_analysis.json"

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
    stress_ids = {json.loads(l)["scenario_id"] for l in (ROOT / "eval/data/stress.jsonl")
                  .read_text(encoding="utf-8").splitlines() if l.strip()}

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

    def load_records(path, conds):
        by = {}
        for r in json.load(open(path, encoding="utf-8")):
            if r.get("repeat", 0) == 0 and r.get("condition") in conds and r.get("scenario_id") in season:
                by[(r["condition"], r["scenario_id"])] = r
        return by

    llama = load_records(LLAMA, set(CONDS))
    nemo = load_records(NEMO, {"C1a", "C2a", "C2b"})
    for fp in NEMO_CACHE.glob("*.json"):
        try:
            r = json.load(fp.open(encoding="utf-8"))
        except Exception:
            continue
        if (r.get("repeat", 0) == 0 and r.get("condition") in ("C0", "C0b")
                and r.get("scenario_id") in season and ("C0" if r["condition"] == "C0" else "C0b", r["scenario_id"]) not in nemo):
            nemo[(r["condition"], r["scenario_id"])] = r

    def usable(r):
        if r is None or r.get("error"):
            return False
        p = r.get("parsed") or {}
        return bool(p.get("valid_json")) and not r.get("truncated")

    def top5_of(r):
        p = (r or {}).get("parsed") or {}
        return [str(x) for x in (p.get("top5") or [])]

    def val(by, cond, sid, mk, mode, analysis):
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

    def cells(by, subset_sids):
        out = {}
        for mode in ("strict", "lenient"):
            for analysis in ("pp", "itt"):
                for cond in CONDS + ["C3"]:
                    sv = [v for sid in subset_sids if (v := val(by, cond, sid, "sv", mode, analysis)) is not None]
                    hv = [v for sid in subset_sids if (v := val(by, cond, sid, "hv", mode, analysis)) is not None]
                    if len(sv) >= 2:
                        out[(mode, analysis, cond, "sv")] = (*bootstrap_ci(sv, n_resamples=10000, seed=42), len(sv))
                        out[(mode, analysis, cond, "hv")] = (*bootstrap_ci(hv, n_resamples=10000, seed=42), len(hv))
        return out

    def contrasts(by, subset_sids):
        out = {}
        for mode in ("strict", "lenient"):
            for analysis in ("pp", "itt"):
                for metric in ("sv", "hv"):
                    pvals, rows = [], []
                    for a, b in PAIRS:
                        av, bv = [], []
                        for sid in subset_sids:
                            x = val(by, a, sid, metric, mode, analysis)
                            y = val(by, b, sid, metric, mode, analysis)
                            if x is None or y is None:
                                continue
                            av.append(x)
                            bv.append(y)
                        if len(av) < 2:
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
                        row["sig"] = pa < 0.05
                        out[(mode, analysis, metric, row["pair"])] = row
        return out

    def print_cells(by, subset_sids, title):
        emit(f"\n{'-'*96}\n{title} (n={len(subset_sids)})\n{'-'*96}")
        C = cells(by, subset_sids)
        for mode in ("strict", "lenient"):
            for analysis in ("pp", "itt"):
                emit(f"\n  {mode.upper()} | {'PP' if analysis=='pp' else 'ITT'}")
                emit(f"  {'cond':5s} {'season-validity [95% CI]':32s} {'n':>4s} | {'hard-violation [95% CI]':32s} {'n':>4s}")
                for cond in CONDS + ["C3"]:
                    s = C.get((mode, analysis, cond, "sv"))
                    h = C.get((mode, analysis, cond, "hv"))
                    if not s:
                        continue
                    emit(f"  {cond:5s} {s[0]:.3f} [{s[1]:.3f},{s[2]:.3f}]".ljust(5 + 32)
                         + f"{s[3]:>4d} | {h[0]:.3f} [{h[1]:.3f},{h[2]:.3f}]".ljust(32 + 6) + f"{h[3]:>4d}")
        return C

    def print_contrasts(C, title):
        emit(f"\n{title}")
        for mode in ("strict", "lenient"):
            for analysis in ("pp", "itt"):
                for metric, ml in (("sv", "season-validity"), ("hv", "hard-violation")):
                    emit(f"\n  metric={ml} | {mode.upper()} | {'per-protocol' if analysis=='pp' else 'ITT'}")
                    for a, b in PAIRS:
                        row = C.get((mode, analysis, metric, f"{a}-{b}"))
                        if not row:
                            emit(f"    {a}-{b}: insufficient n")
                            continue
                        emit(f"    {a}-{b}: n={row['n']:3d} diff={row['diff']:+.3f} "
                             f"[{row['lo']:+.3f},{row['hi']:+.3f}] Cliff_d={row['cliff_d']:+.3f} "
                             f"p={row['p']:.3e} holm={row['holm']:.3e}")

    results: dict = {}
    all_sids, nopilot_sids = sids, [s for s in sids if s not in pilot_set]

    # ---------------- GAP 1 + 2: Nemotron cells + contrasts ----------------
    emit("=" * 96)
    emit("GAP 1 + GAP 2: NEMOTRON pre-registered contrasts (sv AND hv, STRICT/LENIENT x PP/ITT)")
    emit(f"sources: C1a/C2a/C2b fresh B1; C0/C0b reused pre-fix (verified). pairs={PAIRS}")
    emit("=" * 96)
    nC_all = print_cells(nemo, all_sids, "NEMOTRON CELLS: WITH 40 pilot_dev")
    nX_all = contrasts(nemo, all_sids)
    print_contrasts(nX_all, "NEMOTRON CONTRASTS: WITH 40 pilot_dev")
    nC_np = print_cells(nemo, nopilot_sids, "NEMOTRON CELLS: WITHOUT 40 pilot_dev")
    nX_np = contrasts(nemo, nopilot_sids)
    print_contrasts(nX_np, "NEMOTRON CONTRASTS: WITHOUT 40 pilot_dev")

    # claimability (pre-registration: claim only if PP and ITT agree)
    emit(f"\n{'='*96}\nCLAIMABILITY (pre-registration: PP and ITT must BOTH be significant AND same sign)\n{'='*96}")
    claim = {}
    for scen_label, X in (("WITH pilot_dev", nX_all), ("WITHOUT pilot_dev", nX_np)):
        emit(f"\n  [{scen_label}]")
        for metric, ml in (("sv", "season-validity"), ("hv", "hard-violation")):
            for mode in ("strict", "lenient"):
                for a, b in PAIRS:
                    pp = X.get((mode, "pp", metric, f"{a}-{b}"))
                    it = X.get((mode, "itt", metric, f"{a}-{b}"))
                    if not pp or not it:
                        continue
                    same_sign = (pp["diff"] > 0) == (it["diff"] > 0)
                    claimable = pp["sig"] and it["sig"] and same_sign
                    claim[f"{scen_label}|{metric}|{mode}|{a}-{b}"] = {
                        "pp_sig": pp["sig"], "itt_sig": it["sig"], "same_sign": same_sign,
                        "pp_diff": pp["diff"], "itt_diff": it["diff"], "claimable": claimable}
                    emit(f"    {ml:16s} {mode:7s} {a}-{b}: PP(sig={pp['sig']}, {pp['diff']:+.3f}) "
                         f"ITT(sig={it['sig']}, {it['diff']:+.3f}) same_sign={same_sign} -> "
                         f"{'CLAIMABLE' if claimable else 'NOT claimable'}")
    results["claimability"] = claim

    # explicit direction of C2b-C0b / C2b-C1a under ITT
    emit(f"\nDIRECTION under ITT (Nemotron, season-validity):")
    for scen_label, X in (("WITH pilot_dev", nX_all), ("WITHOUT pilot_dev", nX_np)):
        for mode in ("strict", "lenient"):
            for pair in ("C2b-C0b", "C2b-C1a"):
                row = X.get((mode, "itt", "sv", pair))
                if row:
                    emit(f"    [{scen_label}] {mode:7s} sv {pair} ITT diff={row['diff']:+.3f} -> "
                         f"C2b is {'BETTER' if row['diff'] > 0 else 'WORSE'} than the baseline "
                         f"(holm={row['holm']:.2e})")
    emit(f"\nDIRECTION under PP (Nemotron, season-validity), for contrast:")
    for mode in ("strict", "lenient"):
        for pair in ("C2b-C0b", "C2b-C1a"):
            row = nX_all.get((mode, "pp", "sv", pair))
            if row:
                emit(f"    {mode:7s} sv {pair} PP diff={row['diff']:+.3f} holm={row['holm']:.2e} "
                     f"({'sig' if row['sig'] else 'n.s.'})")

    results["nemotron_cells"] = {f"{k[0]}|{k[1]}|{k[2]}|{k[3]}": list(v) for k, v in {**nC_all}.items()}
    results["nemotron_contrasts"] = {f"{k[0]}|{k[1]}|{k[2]}|{k[3]}": v for k, v in nX_all.items()}
    results["nemotron_contrasts_nopilot"] = {f"{k[0]}|{k[1]}|{k[2]}|{k[3]}": v for k, v in nX_np.items()}

    # ---------------- GAP 3: Fidelity to C3 (both models) ----------------
    emit(f"\n{'='*96}\nGAP 3: FIDELITY TO C3 (C2a) - DIAGNOSTIC ONLY (counts and %)\n{'='*96}")

    def jaccard(a, b):
        sa_, sb_ = set(a), set(b)
        return 1.0 if not sa_ and not sb_ else len(sa_ & sb_) / len(sa_ | sb_)

    def fidelity(by, subset_sids, label):
        jac_pp, jac_itt, t1_pp, t1_itt, n_pp = [], [], [], [], 0
        for sid in subset_sids:
            r = by.get(("C2a", sid))
            us, t5, c3t = usable(r), top5_of(r), c3[sid]
            if us:
                n_pp += 1
                jac_pp.append(jaccard(t5, c3t))
                if t5 and c3t:
                    t1_pp.append(1.0 if t5[0] == c3t[0] else 0.0)
            jac_itt.append(jaccard(t5, c3t) if us else 0.0)
            t1_itt.append(1.0 if (us and t5 and c3t and t5[0] == c3t[0]) else 0.0)
        emit(f"\n  [{label}] C2a PP n={n_pp}/{len(subset_sids)}")
        emit(f"    top-5 Jaccard vs C3: PP={np.mean(jac_pp):.4f} | ITT(invalid=0)={np.mean(jac_itt):.4f}")
        emit(f"    top-1 agreement vs C3: PP={np.mean(t1_pp):.4f} | ITT(invalid=0)={np.mean(t1_itt):.4f}")
        out = {"pp_n": n_pp, "jaccard_pp": float(np.mean(jac_pp)), "jaccard_itt": float(np.mean(jac_itt)),
               "top1_pp": float(np.mean(t1_pp)), "top1_itt": float(np.mean(t1_itt))}
        for mode in ("strict", "lenient"):
            for analysis in ("pp", "itt"):
                for metric in ("sv", "hv"):
                    m = b = l = 0
                    for sid in subset_sids:
                        x = val(by, "C2a", sid, metric, mode, analysis)
                        y = val(by, "C3", sid, metric, mode, analysis)
                        if x is None or y is None:
                            continue
                        if abs(x - y) < 1e-9:
                            m += 1
                        elif (metric == "sv" and x > y) or (metric == "hv" and x < y):
                            b += 1
                        else:
                            l += 1
                    tot = m + b + l
                    emit(f"    [{mode.upper()} | {analysis.upper()}] {metric}: match={m} ({m/tot*100:.1f}%) "
                         f"beat={b} ({b/tot*100:.1f}%) lose={l} ({l/tot*100:.1f}%) n={tot}")
                    out[f"{mode}_{analysis}_{metric}"] = {"match": m, "beat": b, "lose": l, "n": tot}
        return out

    results["fidelity"] = {
        "nemotron_with_pilot": fidelity(nemo, all_sids, "NEMOTRON WITH pilot_dev"),
        "nemotron_without_pilot": fidelity(nemo, nopilot_sids, "NEMOTRON WITHOUT pilot_dev"),
        "llama_with_pilot": fidelity(llama, all_sids, "LLAMA WITH pilot_dev"),
        "llama_without_pilot": fidelity(llama, nopilot_sids, "LLAMA WITHOUT pilot_dev"),
    }

    # ---------------- GAP 4: C1a truncation bias ----------------
    emit(f"\n{'='*96}\nGAP 4: C1a 8192-truncation bias (Nemotron 9/150 vs Llama 0/150)\n{'='*96}")

    from eval.common import load_config
    from eval.time_anchored import TimeAnchoredBuilder
    from eval.llm.prompts import prompt_c0, prompt_c1a
    cfg = load_config()
    builder = TimeAnchoredBuilder(cfg)
    ev_len = {}
    for sc in subset:
        ev = builder.build(sc)
        ev_len[sc["scenario_id"]] = len(prompt_c1a(sc, ev))

    def trunc_report(by, label):
        tr = [sid for sid in sids if by.get(("C1a", sid)) and by[("C1a", sid)].get("truncated")]
        keep = [sid for sid in sids if sid not in tr]
        emit(f"\n  [{label}] truncated C1a = {len(tr)}/150")
        if not tr:
            emit("    none -> PP C1a is unbiased by truncation.")
            return {"n_trunc": 0}
        def prof(ids):
            sea = Counter(season[s] for s in ids)
            stress = sum(1 for s in ids if s in stress_ids)
            risk = sum(1 for s in ids if flags[s][0] or flags[s][1])
            lens = [ev_len[s] for s in ids]
            return sea, stress, risk, float(np.mean(lens)), float(np.median(lens))
        s_tr, st_tr, rk_tr, m_tr, md_tr = prof(tr)
        s_kp, st_kp, rk_kp, m_kp, md_kp = prof(keep)
        emit(f"    truncated seasons: {dict(s_tr)} | stress-set {st_tr}/{len(tr)} | risk-flag {rk_tr}/{len(tr)}"
             f" | evidence len mean={m_tr:.0f} med={md_tr:.0f}")
        emit(f"    retained  seasons: {dict(s_kp)} | stress-set {st_kp}/{len(keep)} | risk-flag {rk_kp}/{len(keep)}"
             f" | evidence len mean={m_kp:.0f} med={md_kp:.0f}")
        emit(f"    stress-set rate: truncated {st_tr/len(tr)*100:.1f}% vs retained {st_kp/len(keep)*100:.1f}%")
        emit(f"    risk-flag rate:  truncated {rk_tr/len(tr)*100:.1f}% vs retained {rk_kp/len(keep)*100:.1f}%")
        emit(f"    evidence len:    truncated mean {m_tr:.0f} vs retained mean {m_kp:.0f} "
             f"(delta {m_tr-m_kp:+.0f} chars)")
        return {"n_trunc": len(tr), "trunc_seasons": dict(s_tr), "keep_seasons": dict(s_kp),
                "trunc_stress_pct": st_tr/len(tr)*100, "keep_stress_pct": st_kp/len(keep)*100,
                "trunc_risk_pct": rk_tr/len(tr)*100, "keep_risk_pct": rk_kp/len(keep)*100,
                "trunc_evlen_mean": m_tr, "keep_evlen_mean": m_kp}

    results["gap4"] = {"nemotron": trunc_report(nemo, "NEMOTRON"),
                       "llama": trunc_report(llama, "LLAMA")}

    OUT_JSON.write_text(json.dumps(results, indent=2, default=float), encoding="utf-8")
    OUT_TXT.write_text("\n".join(_records) + "\n", encoding="utf-8")
    emit(f"\nwrote {OUT_TXT}")
    emit(f"wrote {OUT_JSON}")


if __name__ == "__main__":
    main()
