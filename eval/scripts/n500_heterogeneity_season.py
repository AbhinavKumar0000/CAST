"""Heterogeneity-vs-season, per-season contrast table, and the Rabi rainfall-channel test
(offline; NO API calls) - check items 1-3 of the n=500 close-out.

1) Does the B1/B2 heterogeneity (C2b-C0b) survive adjustment for season? Per-scenario paired
   diff d = sv(C2b) - sv(C0b); OLS d ~ isB2, then d ~ isB2 + Rabi + Zaid. If the isB2
   coefficient loses significance after adding season, the heterogeneity is a composition effect.
2) Four pre-registered contrasts stratified by season_stratum at n=500 (EXPLORATORY table).
3) Rainfall channel: per-season scorer rainfall_match distribution (from archive_v2/evidence
   crop_score) vs the C2b-C1a sign; does the Rabi anomaly track the inert rainfall channel?
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
from scipy import stats  # noqa: E402

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

B1_PATH = ROOT / "eval/runs/eval_nemotron-3-ultra/results.json"
B2_PATH = ROOT / "eval/runs/eval_nemotron-3-ultra_b2/results.json"
EVID = ROOT / "eval/runs/archive_v2/evidence"
OUT_TXT = ROOT / "eval/results/n500_heterogeneity_season.txt"
OUT_JSON = ROOT / "eval/results/n500_heterogeneity_season.json"

SEASONS = ["Kharif", "Rabi", "Zaid"]
_records: list[str] = []
RESULTS: dict = {}


def emit(s: str = "") -> None:
    print(s)
    _records.append(s)


def ols(X, y):
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    n, k = X.shape
    dof = max(n - k, 1)
    sigma2 = float(resid @ resid) / dof
    se = np.sqrt(np.diag(np.linalg.pinv(X.T @ X)) * sigma2)
    t = beta / se
    p = 2 * stats.t.sf(np.abs(t), dof)
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1 - float(resid @ resid) / ss_tot if ss_tot > 0 else 0.0
    return beta, se, t, p, r2, n


def main() -> None:
    subset, sids, season, pilot_set, flags, c3, by = pm.build_data()
    B1_PATH.exists()
    b1 = {r["scenario_id"] for r in json.load(open(ROOT / "eval/runs/eval_nemotron-3-ultra/results.json", encoding="utf-8"))
          if r.get("repeat", 0) == 0 and r.get("condition") in ("C1a", "C2a", "C2b")}
    b2 = {r["scenario_id"] for r in json.load(open(ROOT / "eval/runs/eval_nemotron-3-ultra_b2/results.json", encoding="utf-8"))
          if r.get("repeat", 0) == 0 and r.get("condition") in ("C1a", "C2a", "C2b")}
    b1 = {s for s in b1 if s in set(sids)}
    b2 = {s for s in b2 if s in set(sids)}

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
        else:
            if not us or not t5:
                return 0.0 if mk == "sv" else 1.0
        return pm.season_validity(t5, season[sid], mode) if mk == "sv" \
            else pm.hard_violation(t5, season[sid], *flags[sid], mode)

    emit("=" * 100)
    emit("CHECK 1: DOES SEASON EXPLAIN THE B1/B2 HETEROGENEITY?")
    emit("=" * 100)
    comp = {}
    for name, ss in (("B1", b1), ("B2", b2)):
        c = Counter(season[s] for s in ss)
        comp[name] = dict(c)
        emit(f"  {name} (n={len(ss)}): Kharif={c.get('Kharif',0)} Rabi={c.get('Rabi',0)} Zaid={c.get('Zaid',0)}")
    merged = [s for s in sids if s in b1 or s in b2]
    cm = Counter(season[s] for s in merged)
    emit(f"  merged (n={len(merged)}): Kharif={cm.get('Kharif',0)} Rabi={cm.get('Rabi',0)} Zaid={cm.get('Zaid',0)}")
    RESULTS["composition"] = comp

    def paired(a, b, sid, mk, mode, analysis):
        x = val(a, sid, mk, mode, analysis)
        y = val(b, sid, mk, mode, analysis)
        if x is None or y is None:
            return None
        return x - y

    for pair in (("C2b", "C0b"), ("C2b", "C1a")):
        a, b = pair
        rows = [(sid, paired(a, b, sid, "sv", "strict", "pp")) for sid in merged]
        rows = [(sid, d) for sid, d in rows if d is not None]
        y = np.array([d for _, d in rows])
        isB2 = np.array([1.0 if sid in b2 else 0.0 for sid, _ in rows])
        isRabi = np.array([1.0 if season[sid] == "Rabi" else 0.0 for sid, _ in rows])
        isZaid = np.array([1.0 if season[sid] == "Zaid" else 0.0 for sid, _ in rows])
        one = np.ones(len(y))
        isPilot = np.array([1.0 if sid in pilot_set else 0.0 for sid, _ in rows])
        betaA, seA, tA, pA, r2A, nA = ols(np.column_stack([one, isB2]), y)
        betaB, seB, tB, pB, r2B, nB = ols(np.column_stack([one, isB2, isRabi, isZaid]), y)
        betaC, seC, tC, pC, r2C, nC = ols(np.column_stack([one, isB2, isRabi, isZaid, isPilot]), y)
        npilot_b1 = int(((isB2 == 0) & (isPilot == 1)).sum())
        npilot_b2 = int(((isB2 == 1) & (isPilot == 1)).sum())
        emit(f"\n  --- paired diff d = sv({a}) - sv({b}), strict PP, sv (n={nA}) ---")
        emit(f"  pilot_dev in this paired set: B1={npilot_b1}, B2={npilot_b2}")
        emit("  cell means (half x season):")
        for half, mask in (("B1", isB2 == 0), ("B2", isB2 == 1)):
            for sn in ("Kharif", "Rabi", "Zaid"):
                m = mask & (np.array([season[s] == sn for s, _ in rows]))
                if m.sum():
                    emit(f"    {half}/{sn:6s}: mean d = {y[m].mean():+.3f} (n={int(m.sum())})")
        emit(f"  Model A  d ~ isB2              : isB2 coef = {betaA[1]:+.3f} (SE {seA[1]:.3f}, "
             f"p={pA[1]:.3e}), R2={r2A:.3f}")
        emit(f"  Model B  d ~ isB2 + Rabi + Zaid: isB2 coef = {betaB[1]:+.3f} (SE {seB[1]:.3f}, "
             f"p={pB[1]:.3e}); Rabi {betaB[2]:+.3f} (p={pB[2]:.3e}); Zaid {betaB[3]:+.3f} "
             f"(p={pB[3]:.3e}), R2={r2B:.3f}")
        emit(f"  Model C  + isPilot             : isB2 coef = {betaC[1]:+.3f} (SE {seC[1]:.3f}, "
             f"p={pC[1]:.3e}); isPilot {betaC[4]:+.3f} (p={pC[4]:.3e}), R2={r2C:.3f}")
        concl = ("season explains the half difference (isB2 n.s. after adjustment)"
                 if pB[1] >= 0.05 else "half difference SURVIVES season adjustment")
        emit(f"  => {concl}")
        RESULTS[f"model_{a}-{b}"] = {
            "n": nA, "pilot_b1": npilot_b1, "pilot_b2": npilot_b2,
            "A": {"isB2": float(betaA[1]), "se": float(seA[1]), "p": float(pA[1]), "r2": r2A},
            "B": {"isB2": float(betaB[1]), "se": float(seB[1]), "p": float(pB[1]),
                  "rabi": float(betaB[2]), "p_rabi": float(pB[2]),
                  "zaid": float(betaB[3]), "p_zaid": float(pB[3]), "r2": r2B},
            "C": {"isB2": float(betaC[1]), "se": float(seC[1]), "p": float(pC[1]),
                  "isPilot": float(betaC[4]), "p_pilot": float(pC[4]), "r2": r2C},
            "conclusion": concl}

    emit("\n" + "=" * 100)
    emit("CHECK 2: FOUR PRE-REGISTERED CONTRASTS BY SEASON, n=500 (EXPLORATORY / post hoc)")
    emit("=" * 100)
    by_season = {}
    for mode in ("strict",):
        for analysis in ("pp", "itt"):
            for metric in ("sv", "hv"):
                emit(f"\n--- season-validity | {mode.upper()} | {'per-protocol' if analysis=='pp' else 'ITT'}"
                     f" | metric={metric} ---")
                emit(f"  {'season':7s} {'n':>4s}  {'C2a-C0b':22s} {'C2a-C1a':22s} {'C2b-C0b':22s} {'C2b-C1a':22s}")
                for sn in ("Kharif", "Rabi", "Zaid"):
                    ss = [s for s in merged if season[s] == sn]
                    cells = []
                    for a, b in pm.PAIRS:
                        av = [val(a, s, metric, mode, analysis) for s in ss]
                        bv = [val(b, s, metric, mode, analysis) for s in ss]
                        pr = [(x, yv) for x, yv in zip(av, bv) if x is not None and yv is not None]
                        if len(pr) < 2:
                            cells.append("insufficient")
                            continue
                        d = np.array([x - yv for x, yv in pr])
                        dm, lo, hi = bootstrap_ci(list(d), n_resamples=10000, seed=42)
                        cells.append(f"{dm:+.3f} [{lo:+.3f},{hi:+.3f}]")
                        by_season[f"{mode}_{analysis}_{metric}_{sn}_{a}-{b}"] = {
                            "n": len(pr), "diff": float(dm), "lo": float(lo), "hi": float(hi)}
                    emit(f"  {sn:7s} {len(ss):>4d}  " + "  ".join(c.ljust(22) for c in cells))
    emit("\n  (Kharif n=190, Rabi n=177, Zaid n=133; strict PP/hv printed for completeness.)")
    RESULTS["by_season"] = by_season

    emit("\n" + "=" * 100)
    emit("CHECK 3: RABI ANOMALY vs THE INERT RAINFALL CHANNEL (scorer rainfall_match)")
    emit("=" * 100)
    rain = defaultdict(list)
    spread = {}
    for sid in merged:
        ev = json.loads((ROOT / "eval/runs/archive_v2/evidence" / f"{sid}.json").read_text(encoding="utf-8"))
        rc = (ev.get("crop_score") or {}).get("ranked_crops") or []
        vals = []
        for c in rc:
            v = (c.get("scores") or {}).get("rainfall_match")
            if v is not None:
                vals.append(float(v))
                rain[season[sid]].append(float(v))
        if vals:
            spread[sid] = float(np.std(vals))
    emit("  Per-season scorer rainfall_match (across all crops of each scenario):")
    emit(f"  {'season':7s} {'n_cropvals':>10s} {'mean':>7s} {'std':>7s} {'frac==0':>8s} "
         f"{'mean per-scen spread':>21s}")
    rain_summary = {}
    for sn in ("Kharif", "Rabi", "Zaid"):
        v = np.array(rain[sn]) if rain[sn] else np.array([0.0])
        ss = [spread[s] for s in merged if season[s] == sn and s in spread]
        frac0 = float((v == 0).mean())
        rain_summary[sn] = {"n": len(v), "mean": float(v.mean()), "std": float(v.std()),
                            "frac_zero": frac0, "mean_spread": float(np.mean(ss)) if ss else 0.0}
        emit(f"  {sn:7s} {len(v):>10d} {v.mean():>7.3f} {v.std():>7.3f} {frac0:>8.3f} "
             f"{np.mean(ss) if ss else 0.0:>21.3f}")
    RESULTS["rainfall"] = rain_summary

    emit("\n  C2b-C1a strict PP season-validity (from CHECK 2) vs rainfall informative-ness:")
    for sn in ("Kharif", "Rabi", "Zaid"):
        k = f"strict_pp_sv_{sn}_C2b-C1a"
        if k in by_season:
            r = by_season[k]
            emit(f"    {sn:7s}: C2b-C1a = {d if False else rain_summary[sn]['frac_zero'] and 0 or 0}" if False else
                 f"  {sn:7s}: C2b-C1a diff = {by_season[f'strict_pp_sv_{sn}_C2b-C1a']['diff']:+.3f} ; "
                 f"rainfall_match frac==0 = {rain_summary[sn]['frac_zero']:.3f}, "
                 f"mean spread = {rain_summary[sn]['mean_spread']:.3f}")

    # scenario-level correlation rain-spread vs C2b-C1a diff
    xs, ys_ = [], []
    for sid in merged:
        d = paired("C2b", "C1a", sid, "sv", "strict", "pp")
        if d is not None and sid in spread:
            xs.append(spread[sid])
            ys_.append(d)
    if len(xs) > 2 and np.std(xs) > 0:
        r, pr = stats.pearsonr(xs, ys_)
        rho, prho = stats.spearmanr(xs, ys_)
        emit(f"\n  Scenario-level corr(per-scenario rainfall_match spread, sv C2b-C1a diff): "
             f"Pearson r={r:+.3f} p={pr:.3e}; Spearman rho={rho:+.3f} p={prho:.3e} (n={len(xs)})")
        RESULTS["rain_corr"] = {"pearson_r": float(r), "pearson_p": float(pr),
                                "spearman_rho": float(rho), "spearman_p": float(prho), "n": len(xs)}
    else:
        emit("\n  rainfall_match spread has ~zero variance -> no usable cross-season correlation.")
    emit("\n  INTERPRETATION (conservative): the scorer rainfall channel is inert in Rabi iff "
         "frac==0 ~ 1.0 there while Kharif/Zaid vary. NOTE: C1a and C2b see the SAME rainfall values "
         "(pasted vs fetched), so rainfall inertness alone cannot produce a C2b-vs-C1a divergence; "
         "reported as a coincidence of season, not a demonstrated mechanism, unless the sign tracks "
         "the channel across seasons with variation.")
    RESULTS["rain_summary"] = rain_summary

    OUT_JSON.write_text(json.dumps(RESULTS, indent=2, default=float), encoding="utf-8")
    OUT_TXT.write_text("\n".join(_records) + "\n", encoding="utf-8")
    emit(f"\nwrote {OUT_TXT}")
    emit(f"wrote {OUT_JSON}")


if __name__ == "__main__":
    main()
