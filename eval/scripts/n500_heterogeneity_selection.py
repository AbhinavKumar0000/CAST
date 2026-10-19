"""Selection-variable audit of the B1 (150) vs B2 (350) halves + re-test of the C2b-C0b batch
coefficient with the differing covariates added (offline; NO API calls) - close-out checks 1-3.

The B1 150 were a deliberate nested selection; B2 is the remainder. Season is already ruled out
(8.29). Here we compare the halves on everything ELSE the selection could have touched:
  * district distribution, agro-climatic zone distribution,
  * stress.jsonl membership rate,
  * risk-flag rate (drought_z <= -1.5, flood_prob >= 0.40),
  * C3 top-5 score margin (and the top5/top6 cutoff gap),
  * number of season-valid crops available per scenario (GT v1.1 cited) and #crops scored (C3).

Then OLS d = sv(C2b)-sv(C0b) (strict PP) adding whichever covariates differ; if one absorbs the
isB2 coefficient it is named, otherwise the batch effect is recorded as unexplained.
Finally the C2b-C0b / C2b-C1a contrasts are reported for B1, B2 and merged side by side.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
from scipy import stats  # noqa: E402

from eval.statistics import bootstrap_ci  # noqa: E402


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pm = _load("n500_primary_metrics", "eval/scripts/n500_primary_metrics.py")
PAIRS = pm.PAIRS

STRESS = ROOT / "eval/data/stress.jsonl"
SEASON_TABLE = ROOT / "eval/data/ground_truth/crop_season_table_v1.1.csv"
OUT_TXT = ROOT / "eval/results/n500_heterogeneity_selection.txt"
OUT_JSON = ROOT / "eval/results/n500_heterogeneity_selection.json"

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
    with np.errstate(divide="ignore", invalid="ignore"):
        t = np.where(se > 0, beta / se, 0.0)
    p = 2 * stats.t.sf(np.abs(t), dof)
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1 - float(resid @ resid) / ss_tot if ss_tot > 0 else 0.0
    return beta, se, p, r2, n


def perm_mean_diff(a, b, n_perm: int = 5000, seed: int = 42):
    rng = np.random.default_rng(seed)
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    obs = float(a.mean() - b.mean())
    pool = np.concatenate([a, b])
    k = len(a)
    cnt = 0
    for _ in range(n_perm):
        rng.shuffle(pool)
        if abs(pool[:k].mean() - pool[k:].mean()) >= abs(obs):
            cnt += 1
    return obs, (cnt + 1) / (n_perm + 1)


def perm_chi2(labels_a, labels_b, n_perm: int = 2000, seed: int = 42):
    """Chi-square test of independence of half vs category, Monte-Carlo p (sparse-friendly)."""
    cats = sorted(set(labels_a) | set(labels_b))
    idx = {c: i for i, c in enumerate(cats)}
    half = np.array([0] * len(labels_a) + [1] * len(labels_b))
    cat = np.array([idx[c] for c in labels_a] + [idx[c] for c in labels_b])

    def chi2_stat(h, c):
        tab = np.zeros((2, len(cats)))
        for hi, ci in zip(h, c):
            tab[hi, ci] += 1
        row = tab.sum(axis=1, keepdims=True)
        col = tab.sum(axis=0, keepdims=True)
        exp = row @ col / tab.sum()
        with np.errstate(divide="ignore", invalid="ignore"):
            term = np.where(exp > 0, (tab - exp) ** 2 / exp, 0.0)
        return float(term.sum())

    obs = chi2_stat(half, cat)
    rng = np.random.default_rng(seed)
    cnt = 0
    hp = half.copy()
    for _ in range(n_perm):
        rng.shuffle(hp)
        if chi2_stat(hp, cat) >= obs:
            cnt += 1
    dof = len(cats) - 1
    analytic_p = float(stats.chi2.sf(obs, dof)) if dof > 0 else 1.0
    return obs, dof, analytic_p, (cnt + 1) / (n_perm + 1), len(cats)


def main() -> None:
    subset, sids, season, pilot_set, flags, c3, by = pm.build_data()
    b1 = set(sids[:150])
    b2 = set(sids[150:])
    b1_sids = [s for s in sids if s in b1]
    b2_sids = [s for s in sids if s in b2]
    merged = sids[:]

    meta = {s["scenario_id"]: s for s in subset}

    # stress.jsonl membership
    stress_ids = {json.loads(l)["scenario_id"] for l in
                  STRESS.read_text(encoding="utf-8").splitlines() if l.strip()}

    # season-valid crop pool (GT v1.1, status == cited) per season
    cites = {}
    with SEASON_TABLE.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            if row.get("status") == "cited":
                cites.setdefault(row["season"], set()).add(row["crop"])
    n_seasvalid = {sn: len(cc) for sn, cc in cites.items()}

    # per-scenario covariates
    cov = {}
    for sid in merged:
        d, f = flags[sid]
        sc = c3[sid]
        try:
            ev = json.loads((ROOT / "eval/runs/archive_v2/deterministic" / f"{sid}.json")
                            .read_text(encoding="utf-8"))
            scores = ((ev.get("ablations") or {}).get("full_repo") or {}).get("scores") or {}
            vals = sorted([float(v) for v in scores.values()], reverse=True)
        except Exception:
            vals = []
        margin_t1t5 = (vals[0] - vals[4]) if len(vals) >= 5 else 0.0
        margin_t1t2 = (vals[0] - vals[1]) if len(vals) >= 2 else 0.0
        cutoff = (vals[4] - vals[5]) if len(vals) >= 6 else 0.0
        cov[sid] = {
            "district": meta[sid].get("district"),
            "zone": meta[sid].get("agro_climatic_zone"),
            "stress": 1.0 if sid in stress_ids else 0.0,
            "drought": 1.0 if d else 0.0,
            "flood": 1.0 if f else 0.0,
            "margin_t1t5": margin_t1t5,
            "margin_t1t2": margin_t1t2,
            "cutoff_5_6": cutoff,
            "n_seasvalid": float(n_seasvalid.get(season[sid], 0)),
            "n_crops": float(len(vals)),
        }

    emit("=" * 100)
    emit("PART 1: WHICH SELECTION VARIABLES DIFFER BETWEEN B1 (150) AND B2 (350)?")
    emit("=" * 100)
    emit(f"  B1 n={len(b1_sids)}  B2 n={len(b2_sids)}  stress.jsonl size={len(stress_ids)}  "
         f"subset in stress={len(stress_ids & set(merged))}/500")
    diff_flags = {}

    # categorical: district
    da = [cov[s]["district"] for s in b1_sids]
    db = [cov[s]["district"] for s in b2_sids]
    stat, dof, ap, pp, ncat = perm_chi2(da, db)
    emit(f"\n  district: B1 distinct={len(set(da))} B2 distinct={len(set(db))} "
         f"union={ncat} | chi2={stat:.1f} dof={dof} analytic p={ap:.3f} perm_p={pp:.4f}")
    emit(f"    B1 top districts: " + ", ".join(f"{k}={v}" for k, v in Counter(da).most_common(6)))
    emit(f"    B2 top districts: " + ", ".join(f"{k}={v}" for k, v in Counter(db).most_common(8)))
    diff_flags["district"] = {"chi2": stat, "perm_p": pp, "analytic_p": ap, "n_categories": ncat,
                              "b1_distinct": len(set(da)), "b2_distinct": len(set(db))}

    # categorical: zone
    za = [str(cov[s]["zone"]) for s in b1_sids]
    zb = [str(cov[s]["zone"]) for s in b2_sids]
    stat, dof, ap, pp, ncat = perm_chi2(za, zb)
    emit(f"\n  agro_climatic_zone: B1 counts={dict(Counter(za))} B2 counts={dict(Counter(zb))}")
    emit(f"    chi2={stat:.3f} dof={dof} analytic_p={ap:.3f} perm_p={pp:.4f}")
    diff_flags["zone"] = {"chi2": stat, "perm_p": pp, "b1": dict(Counter(za)),
                          "b2": dict(Counter(zb))}

    # continuous covariates
    cont = ["stress", "drought", "flood", "margin_t1t5", "margin_t1t2", "cutoff_5_6",
            "n_seasvalid", "n_crops"]
    emit(f"\n  {'covariate':13s} {'B1 mean':>9s} {'B2 mean':>9s} {'diff':>8s} {'perm_p':>8s}")
    for name in cont:
        a = [cov[s][name] for s in b1_sids]
        b = [cov[s][name] for s in b2_sids]
        dm, pp = perm_mean_diff(a, b)
        RESULTS.setdefault("covariates", {})[name] = {
            "b1_mean": float(np.mean(a)), "b2_mean": float(np.mean(b)),
            "diff": float(dm), "perm_p": pp}
        flag = "  <-- differs" if pp < 0.05 else ""
        emit(f"  {name:13s} {np.mean(a):>9.3f} {np.mean(b):>9.3f} {dm:>+8.3f} {pp:>8.4f}{flag}")

    # season-valid pool per season (context)
    emit(f"\n  season-valid crop pool (GT v1.1 cited): {n_seasvalid}")

    common_dists = set(str(x) for x in da) & set(str(x) for x in db)
    common_dist_scen = [s for s in merged if str(cov[s]["district"]) in common_dists]
    emit(f"\n  district overlap: B1-only={len(set(da)-set(db))} B2-only={len(set(db)-set(da))} "
         f"shared={len(common_dists)}; scenarios in shared districts={len(common_dist_scen)}/500")
    RESULTS["district_overlap"] = {
        "b1_distinct": len(set(da)), "b2_distinct": len(set(db)), "shared": len(common_dists),
        "b1_only": len(set(da) - set(db)), "b2_only": len(set(db) - set(da)),
        "common_district_scenarios": len(common_dist_scen)}

    differing = [n for n in cont if RESULTS["covariates"][n]["perm_p"] < 0.05]
    district_diff = diff_flags["district"]["perm_p"] < 0.05
    zone_diff = diff_flags["zone"]["perm_p"] < 0.05
    emit(f"\n  => continuous covariates that differ (p<0.05): {differing or 'none'}")
    emit(f"  => district differs: {district_diff} (perm_p={diff_flags['district']['perm_p']:.4f}); "
         f"zone differs: {zone_diff} (perm_p={diff_flags['zone']['perm_p']:.4f})")
    RESULTS["differing"] = {"continuous": differing, "district": district_diff, "zone": zone_diff}

    # ---------------- PART 2: regression ----------------
    emit("\n" + "=" * 100)
    emit("PART 2: RE-TEST THE C2b-C0b BATCH COEFFICIENT WITH THE DIFFERING COVARIATES ADDED")
    emit("=" * 100)

    def paired(a, b, sid):
        xs, ys = by.get((a, sid)), by.get((b, sid))

        def v(r):
            p = (r or {}).get("parsed") or {}
            us = r is not None and not r.get("error") and bool(p.get("valid_json")) and not r.get("truncated")
            if not us:
                return None
            t5 = [str(x) for x in (p.get("top5") or [])]
            if not t5:
                return None
            return pm.season_validity(t5, season[sid], "strict")
        x, y = v(xs), v(ys)
        return None if x is None or y is None else x - y

    for a, b in (("C2b", "C0b"), ("C2b", "C1a")):
        rows = [(sid, paired(a, b, sid)) for sid in merged]
        rows = [(sid, d) for sid, d in rows if d is not None]
        y = np.array([d for _, d in rows])
        n = len(y)
        isB2 = np.array([1.0 if sid in b2 else 0.0 for sid, _ in rows])
        isRabi = np.array([1.0 if season[sid] == "Rabi" else 0.0 for sid, _ in rows])
        isZaid = np.array([1.0 if season[sid] == "Zaid" else 0.0 for sid, _ in rows])
        isPilot = np.array([1.0 if sid in pilot_set else 0.0 for sid, _ in rows])
        one = np.ones(n)

        base = [one, isB2, isRabi, isZaid, isPilot]
        covcols = [np.array([cov[sid][k] for sid, _ in rows]) for k in differing]
        # zone dummies (drop first, keep None as its own category)
        zones = sorted({str(cov[sid]["zone"]) for sid, _ in rows})
        zonecols = [np.array([1.0 if str(cov[sid]["zone"]) == z else 0.0 for sid, _ in rows])
                    for z in zones[1:]]
        # district dummies (fixed effect)
        dists = sorted({str(cov[sid]["district"]) for sid, _ in rows})
        distcols = [np.array([1.0 if str(cov[sid]["district"]) == d0 else 0.0 for sid, _ in rows])
                    for d0 in dists[1:]]

        models = {
            "C_base": base,
            "D_cov": base + covcols,
            "E_cov+zone": base + covcols + zonecols,
            "F_districtFE": base + distcols,
        }
        emit(f"\n  --- d = sv({a}) - sv({b}), strict PP (n={n}); differing covars = {differing or 'none'} ---")
        emit(f"  {'model':13s} {'isB2 coef':>10s} {'SE':>7s} {'p':>10s} {'R2':>7s}")
        RESULTS.setdefault(f"regress_{a}-{b}", {})
        for mname, cols in models.items():
            beta, se, pv, r2, nn = ols(np.column_stack(cols), y)
            emit(f"  {mname:13s} {beta[1]:>+10.3f} {se[1]:>7.3f} {pv[1]:>10.3e} {r2:>7.3f}")
            RESULTS[f"regress_{a}-{b}"][mname] = {"isB2": float(beta[1]), "se": float(se[1]),
                                                  "p": float(pv[1]), "r2": float(r2), "n": nn}
        bD = RESULTS[f"regress_{a}-{b}"]["D_cov"]
        verdict = ("covariates ABSORB the batch effect (isB2 n.s.)" if bD["p"] >= 0.05
                   else "batch effect SURVIVES covariate adjustment -> UNEXPLAINED")
        emit(f"  => {verdict}")

        # G: restrict to districts shared by BOTH halves (identifies batch separate from district)
        mrows = [(sid, d) for sid, d in rows if str(cov[sid]["district"]) in common_dists]
        if len(mrows) >= 10:
            ym = np.array([d for _, d in mrows])
            isB2m = np.array([1.0 if sid in b2 else 0.0 for sid, _ in mrows])
            isR = np.array([1.0 if season[sid] == "Rabi" else 0.0 for sid, _ in mrows])
            isZ = np.array([1.0 if season[sid] == "Zaid" else 0.0 for sid, _ in mrows])
            isP = np.array([1.0 if sid in pilot_set else 0.0 for sid, _ in mrows])
            stm = np.array([cov[sid]["stress"] for sid, _ in mrows])
            ds = sorted({str(cov[sid]["district"]) for sid, _ in mrows})
            dcols = [np.array([1.0 if str(cov[sid]["district"]) == z else 0.0 for sid, _ in mrows])
                     for z in ds[1:]]
            Xg = np.column_stack([np.ones(len(ym)), isB2m, isR, isZ, isP, stm] + dcols)
            bg, sg, pg, rg, ng = ols(Xg, ym)
            nb1 = int(((isB2m == 0)).sum())
            nb2 = int(((isB2m == 1)).sum())
            emit(f"  G_shareddist  {bg[1]:>+10.3f} {sg[1]:>7.3f} {pg[1]:>10.3e} {rg:>7.3f}   "
                 f"(n={ng}, shared districts={len(ds)}, B1={nb1} B2={nb2})")
            RESULTS[f"regress_{a}-{b}"]["G_shareddist"] = {
                "isB2": float(bg[1]), "se": float(sg[1]), "p": float(pg[1]), "r2": rg, "n": ng,
                "shared_districts": len(ds), "b1": nb1, "b2": nb2}
            if pg[1] >= 0.05:
                emit("  => within shared districts the batch effect is NOT significant "
                     "(district composition explains it)")
            else:
                emit("  => within shared districts the batch effect PERSISTS -> not a district-composition "
                     "artefact")

    # ---------------- PART 3: C2b contrasts B1/B2/merged ----------------
    emit("\n" + "=" * 100)
    emit("PART 3: C2b CONTRASTS BY HALF (so the heterogeneity is visible, not averaged away)")
    emit("(strict PP, season-validity; diff [95% CI] and two-sample interaction perm p B2-vs-B1)")
    emit("=" * 100)

    def two_sample_boot(a, b, n_resamples=10000, seed=42):
        rng = np.random.default_rng(seed)
        a, b = np.asarray(a, float), np.asarray(b, float)
        obs = float(a.mean() - b.mean())
        da = rng.choice(a, size=(n_resamples, len(a)), replace=True).mean(axis=1)
        db = rng.choice(b, size=(n_resamples, len(b)), replace=True).mean(axis=1)
        lo, hi = np.percentile(da - db, [2.5, 97.5])
        return obs, float(lo), float(hi)

    def perm2(a, b, n_perm=5000, seed=42):
        rng = np.random.default_rng(seed)
        a, b = np.asarray(a, float), np.asarray(b, float)
        obs = abs(a.mean() - b.mean())
        pool = np.concatenate([a, b])
        k = len(a)
        cnt = 0
        for _ in range(n_perm):
            rng.shuffle(pool)
            if abs(pool[:k].mean() - pool[k:].mean()) >= obs:
                cnt += 1
        return (cnt + 1) / (n_perm + 1)

    for a, b in PAIRS:
        if not (a == "C2b" or b == "C2b"):
            continue
        d1 = np.array([paired(a, b, s) for s in b1_sids if paired(a, b, s) is not None])
        d2 = np.array([paired(a, b, s) for s in b2_sids if paired(a, b, s) is not None])
        dm = np.array([paired(a, b, s) for s in merged if paired(a, b, s) is not None])
        m1, l1, h1 = bootstrap_ci(list(d1), n_resamples=10000, seed=42)
        m2, l2, h2 = bootstrap_ci(list(d2), n_resamples=10000, seed=42)
        mm, lm, hm = bootstrap_ci(list(dm), n_resamples=10000, seed=42)
        inter, ilo, ihi = two_sample_boot(d2, d1)
        perm_p = perm2(d2, d1)
        emit(f"\n  {a}-{b}:")
        emit(f"    B1    (n={len(d1):3d}): {m1:+.3f} [{l1:+.3f},{h1:+.3f}]")
        emit(f"    B2    (n={len(d2):3d}): {m2:+.3f} [{l2:+.3f},{h2:+.3f}]")
        emit(f"    merged(n={len(dm):3d}): {mm:+.3f} [{lm:+.3f},{hm:+.3f}]")
        emit(f"    interaction diff(B2)-diff(B1) = {inter:+.3f} [{ilo:+.3f},{ihi:+.3f}], perm_p={perm_p:.4f}")
        RESULTS.setdefault("by_half", {})[f"{a}-{b}"] = {
            "B1": {"diff": float(m1), "lo": float(l1), "hi": float(h1), "n": len(d1)},
            "B2": {"diff": float(m2), "lo": float(l2), "hi": float(h2), "n": len(d2)},
            "merged": {"diff": float(mm), "lo": float(lm), "hi": float(hm), "n": len(dm)},
            "interaction": {"diff": float(inter), "lo": float(ilo), "hi": float(ihi),
                            "perm_p": float(perm_p)}}

    OUT_JSON.write_text(json.dumps(RESULTS, indent=2, default=float), encoding="utf-8")
    OUT_TXT.write_text("\n".join(_records) + "\n", encoding="utf-8")
    emit(f"\nwrote {OUT_TXT}")
    emit(f"wrote {OUT_JSON}")


if __name__ == "__main__":
    main()
