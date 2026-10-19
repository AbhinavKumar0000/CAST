"""District-clustered inference at n=500 (offline; NO API calls) - final close-out analysis.

Scenarios are clustered within district (~52 districts, ~10 scenarios each) and the B1/B2 halves
are near district-disjoint, so scenario-level CIs/p-values are anti-conservative. This script:
  1) ICC by district for season-validity and hard-violation, with design effect and effective N;
  2) re-computes the four pre-registered contrasts with a DISTRICT-clustered bootstrap
     (resample districts) across strict x lenient x PP x ITT, with Holm;
  3) before/after claimability (16 cells) and per-half / per-season contrasts;
  4) between-district variance in the C2b-C0b effect + the district-level distribution;
  6) n=500 per-scenario C2a-vs-C3 match/beat/lose on sv and hv;
  7) the exact paired C2a-C0b and C2a-C1a figures at n=500.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections import defaultdict
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
PAIRS = pm.PAIRS
CONDS = pm.CONDS
OUT_TXT = ROOT / "eval/results/n500_clustered_inference.txt"
OUT_JSON = ROOT / "eval/results/n500_clustered_inference.json"

_records: list[str] = []
RESULTS: dict = {}
N_RES = 10000


def emit(s: str = "") -> None:
    print(s)
    _records.append(s)


def clustered_paired(by_cluster: dict[str, list[float]], seed: int = 42):
    """District-clustered bootstrap of the mean paired diff. Returns (obs, lo, hi, p, k_clusters, n)."""
    keys = sorted(by_cluster)
    if not keys:
        return 0.0, 0.0, 0.0, 1.0, 0, 0
    sums = np.array([float(np.sum(by_cluster[k])) for k in keys])
    cnts = np.array([len(by_cluster[k]) for k in keys], dtype=float)
    allv = np.concatenate([np.asarray(by_cluster[k], float) for k in keys])
    obs = float(allv.mean())
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(keys), size=(N_RES, len(keys)))
    boot = sums[idx].sum(axis=1) / cnts[idx].sum(axis=1)
    lo, hi = (float(x) for x in np.percentile(boot, [2.5, 97.5]))
    cs = sums - cnts * obs
    cb = cs[idx].sum(axis=1) / cnts[idx].sum(axis=1)
    p = float((np.abs(cb) >= abs(obs)).mean())
    p = max(p, 1.0 / N_RES)
    return obs, lo, hi, p, len(keys), len(allv)


def icc_anova(values: np.ndarray, groups: np.ndarray):
    """One-way random-effects ICC(1), design effect, effective N. Groups = district labels."""
    uniq = sorted(set(groups))
    a = len(uniq)
    N = len(values)
    if a < 2 or N <= a:
        return {"icc": 0.0, "deff": 1.0, "ess": N, "n": N, "k": a, "m_bar": N / max(a, 1)}
    grand = values.mean()
    ssb = ssw = 0.0
    for u in uniq:
        vals = values[groups == u]
        ssb += len(vals) * (vals.mean() - grand) ** 2
        ssw += ((vals - vals.mean()) ** 2).sum()
    dfb, dfw = a - 1, N - a
    msb, msw = ssb / dfb, ssw / dfw
    m_bar = N / a
    denom = msb + (m_bar - 1) * msw
    icc = (msb - msw) / denom if denom > 0 else 0.0
    icc = float(min(max(icc, 0.0), 1.0))
    deff = 1 + (m_bar - 1) * icc
    return {"icc": icc, "deff": deff, "ess": N / deff, "n": N, "k": a, "m_bar": m_bar,
            "msb": float(msb), "msw": float(msw)}


def main() -> None:
    subset, sids, season, pilot_set, flags, c3, by = pm.build_data()
    district = {s["scenario_id"]: str(s.get("district")) for s in subset}
    b1 = set(sids[:150])
    b2 = set(sids[150:])
    merged = list(sids)
    dists_all = sorted({district[s] for s in merged})

    def usable(r):
        if r is None or r.get("error"):
            return False
        p = (r or {}).get("parsed") or {}
        return bool(p.get("valid_json")) and not r.get("truncated")

    def top5_of(r):
        p = (r or {}).get("parsed") or {}
        return [str(x) for x in (p.get("top5") or [])]

    def val(cond, sid, mk, mode, analysis):
        t5 = c3[sid] if cond == "C3" else top5_of(by.get((cond, sid)))
        us = cond == "C3" or usable(by.get((cond, sid)))
        if analysis == "pp" and (not us or not t5):
            return None
        if analysis == "itt" and (not us or not t5):
            return 0.0 if mk == "sv" else 1.0
        return pm.season_validity(t5, season[sid], mode) if mk == "sv" \
            else pm.hard_violation(t5, season[sid], *flags[sid], mode)

    def paired_values(a, b, sid, mk, mode, analysis):
        x = val(a, sid, mk, mode, analysis)
        y = val(b, sid, mk, mode, analysis)
        if x is None or y is None:
            return None
        return x - y

    def cluster_map(sidset, a, b, mk, mode, analysis):
        out: dict[str, list[float]] = defaultdict(list)
        for sid in sidset:
            d = paired_values(a, b, sid, mk, mode, analysis)
            if d is not None:
                out[district[sid]].append(d)
        return out

    def flat(dmap):
        return np.array([v for vs in dmap.values() for v in vs], float)

    # ================= 1: ICC / design effect / ESS =================
    emit("=" * 100)
    emit("1. INTRA-CLASS CORRELATION BY DISTRICT (strict, per-protocol), with design effect & effective N")
    emit("=" * 100)
    emit(f"  districts (merged 500) = {len(dists_all)}; "
         f"mean scenarios/district = {len(merged)/len(dists_all):.2f}; "
         f"min/max = "
         f"{min(len([s for s in merged if district[s]==d]) for d in dists_all)}/"
         f"{max(len([s for s in merged if district[s]==d]) for d in dists_all)}")
    icc_rows = {}
    for mk in ("sv", "hv"):
        emit(f"\n  metric = {mk}")
        emit(f"  {'cond':5s} {'n':>5s} {'k':>4s} {'m_bar':>7s} {'ICC':>7s} {'DEFF':>7s} {'ESS':>7s}")
        for cond in CONDS + ["C3"]:
            vals, grp = [], []
            for sid in merged:
                v = val(cond, sid, mk, "strict", "pp")
                if v is not None:
                    vals.append(v)
                    grp.append(district[sid])
            r = icc_anova(np.array(vals, float), np.array(grp))
            icc_rows[f"{mk}_{cond}"] = r
            emit(f"  {cond:5s} {r['n']:>5d} {r['k']:>4d} {r['m_bar']:>7.2f} {r['icc']:>7.3f} "
                 f"{r['deff']:>7.3f} {r['ess']:>7.1f}")
    # ICC of the primary paired difference
    for pair in (("C2b", "C0b"), ("C2a", "C0b"), ("C2a", "C1a"), ("C2b", "C1a")):
        dmap = cluster_map(merged, pair[0], pair[1], "sv", "strict", "pp")
        vals = np.concatenate([np.array(v) for v in dmap.values()]) if dmap else np.array([])
        grp = np.concatenate([[d] * len(v) for d, v in dmap.items()]) if dmap else np.array([])
        r = icc_anova(vals, grp)
        icc_rows[f"sv_diff_{pair[0]}-{pair[1]}"] = r
        emit(f"  diff {pair[0]}-{pair[1]} sv: n={r['n']} k={r['k']} ICC={r['icc']:.3f} "
             f"DEFF={r['deff']:.3f} ESS={r['ess']:.1f}")
    RESULTS["icc"] = icc_rows

    # ================= 2: clustered contrasts =================
    emit("\n" + "=" * 100)
    emit("2. PRE-REGISTERED CONTRASTS: district-clustered bootstrap (strict x lenient x PP x ITT)")
    emit("=" * 100)
    emit(f"  clustered CIs/p: resample {len(dists_all)} districts with replacement; centered bootstrap p; "
         f"Holm over the 4 pre-registered pairs")
    clustered = {}
    per_cell_p_clustered = {}
    per_cell_p_naive = {}
    for mode in ("strict", "lenient"):
        for analysis in ("pp", "itt"):
            for mk in ("sv", "hv"):
                emit(f"\n  --- {mode.upper()} | {'per-protocol' if analysis=='pp' else 'ITT'} | {mk} ---")
                emit(f"  {'pair':11s} {'naive diff [CI]':34s} {'clustered diff [CI]':34s} "
                     f"{'cl_p':>9s} {'holm_naive':>10s} {'holm_cl':>9s}")
                rows, pnaive, pcl = [], [], []
                for a, b in PAIRS:
                    dmap = cluster_map(merged, a, b, mk, mode, analysis)
                    dm, lo, hi, pclv, k, n = clustered_paired(dmap)
                    dflat = flat(dmap)
                    nm, nlo, nhi = bootstrap_ci(list(dflat), n_resamples=N_RES, seed=42)
                    _, pn = wilcoxon_paired(list(dflat), [0.0] * len(dflat))
                    rows.append((a, b, nm, nlo, nhi, dm, lo, hi, k, n))
                    pnaive.append(pn)
                    pcl.append(pclv)
                hn = holm_bonferroni(pnaive)
                hc = holm_bonferroni(pcl)
                for (a, b, nm, nlo, nhi, dm, lo, hi, k, n), pn, hnv, pc, hcv in zip(
                        rows, pnaive, hn, pcl, hc):
                    key = f"{mode}_{analysis}_{mk}_{a}-{b}"
                    clustered[key] = {"naive": {"diff": nm, "lo": nlo, "hi": nhi, "p": pn, "holm": hnv},
                                      "cluster": {"diff": dm, "lo": lo, "hi": hi, "p": pc, "holm": hcv,
                                                  "k_districts": k, "n": n}}
                    per_cell_p_clustered[key] = pc
                    per_cell_p_naive[key] = pn
                    emit(f"  {a}-{b:4s} {nm:+.3f} [{nlo:+.3f},{nhi:+.3f}]".ljust(11 + 34)
                         + f" {dm:+.3f} [{lo:+.3f},{hi:+.3f}]".ljust(34)
                         + f" {pc:>9.2e} {hnv:>10.2e} {hcv:>9.2e}")
    RESULTS["clustered"] = clustered

    # ================= 3: claimability before/after =================
    emit("\n" + "=" * 100)
    emit("3. CLAIMABILITY (16 cells): naive -> district-clustered")
    emit("=" * 100)
    emit(f"  {'cell':34s} {'naive PP/ITT holm':>26s} {'clustered PP/ITT holm':>26s}  verdict")
    claim = {}
    changed = []
    for mode in ("strict", "lenient"):
        for mk in ("sv", "hv"):
            kpp = {f"{a}-{b}": clustered[f"{mode}_pp_{mk}_{a}-{b}"] for a, b in PAIRS}
            kit = {f"{a}-{b}": clustered[f"{mode}_itt_{mk}_{a}-{b}"] for a, b in PAIRS}
            for a, b in PAIRS:
                k = f"{a}-{b}"
                pp, it = kpp[k], kit[k]
                same_sign_n = (np.sign(pp["naive"]["diff"]) == np.sign(it["naive"]["diff"])) and pp["naive"]["diff"] != 0
                claim_n = bool(same_sign_n and pp["naive"]["holm"] < 0.05 and it["naive"]["holm"] < 0.05)
                same_sign_c = (np.sign(pp["cluster"]["diff"]) == np.sign(it["cluster"]["diff"])) and pp["cluster"]["diff"] != 0
                claim_c = bool(same_sign_c and pp["cluster"]["holm"] < 0.05 and it["cluster"]["holm"] < 0.05)
                cell = f"{mode}_{mk}_{k}"
                claim[cell] = {"naive": claim_n, "clustered": claim_c,
                               "pp_holm_naive": pp["naive"]["holm"], "itt_holm_naive": it["naive"]["holm"],
                               "pp_holm_cl": pp["cluster"]["holm"], "itt_holm_cl": it["cluster"]["holm"]}
                if claim_n != claim_c:
                    changed.append(cell)
                emit(f"  {cell:34s} {pp['naive']['holm']:.2e}/{it['naive']['holm']:.2e}".rjust(34)
                     + f" {pp['cluster']['holm']:.2e}/{it['cluster']['holm']:.2e}".rjust(27)
                     + f"  {'CLAIMABLE' if claim_n else 'not'} -> {'CLAIMABLE' if claim_c else 'not'}"
                     + ("   ** CHANGED **" if claim_n != claim_c else ""))
    emit(f"\n  cells changed: {len(changed)} :: {changed or 'none'}")
    RESULTS["claimability_before_after"] = claim
    RESULTS["claimability_changed"] = changed

    # ---- per-half ----
    emit("\n" + "=" * 100)
    emit("3b. PER-HALF contrasts: naive -> clustered (per-half significance = CI excludes 0)")
    emit("=" * 100)
    half = {}
    for label, sset in (("B1", b1), ("B2", b2)):
        for mode in ("strict", "lenient"):
            for analysis in ("pp", "itt"):
                for mk in ("sv", "hv"):
                    for a, b in PAIRS:
                        dmap = cluster_map([s for s in merged if s in sset], a, b, mk, mode, analysis)
                        if not dmap:
                            continue
                        dm, lo, hi, pc, k, n = clustered_paired(dmap)
                        dflat = flat(dmap)
                        nm, nlo, nhi = bootstrap_ci(list(dflat), n_resamples=N_RES, seed=42)
                        half[f"{label}_{mode}_{analysis}_{mk}_{a}-{b}"] = {
                            "naive": {"diff": nm, "lo": nlo, "hi": nhi},
                            "cluster": {"diff": dm, "lo": lo, "hi": hi, "p": pc, "k": k, "n": n}}
        # compact print for the primary cell
        emit(f"\n  {label} (primary: strict PP sv | strict PP hv)  n={len(sset)}  districts="
             f"{len({district[s] for s in sset})}")
        for mk in ("sv", "hv"):
            for a, b in PAIRS:
                r = half[f"{label}_strict_pp_{mk}_{a}-{b}"]
                sn = r["naive"]; sc = r["cluster"]
                sign = ("sig" if (sc["lo"] > 0 or sc["hi"] < 0) else "ns ")
                emit(f"    {a}-{b:4s} {mk}: naive {sn['diff']:+.3f} [{sn['lo']:+.3f},{sn['hi']:+.3f}] | "
                     f"clustered {sc['diff']:+.3f} [{sc['lo']:+.3f},{sc['hi']:+.3f}] (p={sc['p']:.2e}) -> {sign}")
    RESULTS["per_half"] = half

    # ---- per-season ----
    emit("\n" + "=" * 100)
    emit("3c. PER-SEASON contrasts: naive -> clustered (EXPLORATORY)")
    emit("=" * 100)
    pers = {}
    for sn in ("Kharif", "Rabi", "Zaid"):
        sset = [s for s in merged if season[s] == sn]
        emit(f"\n  [{sn}] n={len(sset)} districts={len({district[s] for s in sset})} (primary strict PP sv)")
        for mk in ("sv", "hv"):
            for a, b in PAIRS:
                dm, lo, hi, pc, k, n = clustered_paired(cluster_map(sset, a, b, "sv" if mk == "sv" else "hv", "strict", "pp"))
                pers[f"{sn}_strict_pp_{mk}_{a}-{b}"] = {"diff": dm, "lo": lo, "hi": hi, "p": pc, "k": k, "n": n}
            emit(f"    {mk}: " + " | ".join(
                f"{a}-{b}:{pers[f'{sn}_strict_pp_{mk}_{a}-{b}']['diff']:+.3f}"
                f"[{pers[f'{sn}_strict_pp_{mk}_{a}-{b}']['lo']:+.3f},"
                f"{pers[f'{sn}_strict_pp_{mk}_{a}-{b}']['hi']:+.3f}]"
                for a, b in PAIRS))
    RESULTS["per_season"] = pers

    # ================= 4: district-level distribution of C2b-C0b =================
    emit("\n" + "=" * 100)
    emit("4. BETWEEN-DISTRICT VARIATION IN THE C2b-C0b EFFECT (strict PP, sv)")
    emit("=" * 100)
    dmap = cluster_map(merged, "C2b", "C0b", "sv", "strict", "pp")
    disc = []
    for dd, vs in dmap.items():
        halfs = sorted({("B1" if s in b1 else "B2") for s in merged
                        if district[s] == dd and paired_values("C2b", "C0b", s, "sv", "strict", "pp") is not None})
        disc.append((dd, float(np.mean(vs)), len(vs), "/".join(halfs)))
    disc_sorted = sorted(disc, key=lambda x: x[1])
    means = np.array([d[1] for d in disc])
    emit(f"  districts={len(disc)}  mean={means.mean():+.3f}  sd(between-district)={means.std(ddof=1):.3f}  "
         f"min={means.min():+.3f}  Q1={np.percentile(means,25):+.3f}  median={np.median(means):+.3f}  "
         f"Q3={np.percentile(means,75):+.3f}  max={means.max():+.3f}")
    r_d = icc_anova(flat(dmap), np.array([d for d, vs in dmap.items() for _ in vs]))
    emit(f"  ICC(d by district)={r_d['icc']:.3f}  DEFF={r_d['deff']:.3f}  ESS={r_d['ess']:.1f}")
    emit(f"  B1/B2 gap (merged batch coefficient) = +0.094 ; between-district SD = {means.std(ddof=1):.3f} "
         f"(gap / SD = {0.094/means.std(ddof=1):.2f})")
    emit("  district-level means (sorted), n and half membership:")
    for dd, m, nn, hh in disc_sorted:
        bar = "#" * int(round((m + 0.5) * 20))
        emit(f"    {dd:16s} {m:+.3f} (n={nn:2d}, {hh:5s}) {bar}")
    RESULTS["district_effect"] = {
        "n_districts": len(disc), "mean": float(means.mean()), "sd_between": float(means.std(ddof=1)),
        "min": float(means.min()), "q1": float(np.percentile(means, 25)),
        "median": float(np.median(means)), "q3": float(np.percentile(means, 75)),
        "max": float(means.max()), "icc": r_d["icc"], "deff": r_d["deff"], "ess": r_d["ess"],
        "gap_over_sd": float(0.094 / means.std(ddof=1)),
        "districts": [{"district": d0, "mean": m, "n": nn, "half": hh} for d0, m, nn, hh in disc_sorted]}

    # ================= 6: C2a-vs-C3 match/beat/lose =================
    emit("\n" + "=" * 100)
    emit("6. n=500 PER-SCENARIO C2a-vs-C3 MATCH/BEAT/LOSE (sv and hv)")
    emit("=" * 100)
    for mk in ("sv", "hv"):
        for mode in ("strict", "lenient"):
            for analysis in ("pp", "itt"):
                m = bb = ll = 0
                for sid in merged:
                    x = val("C2a", sid, mk, mode, analysis)
                    y = val("C3", sid, mk, mode, analysis)
                    if x is None or y is None:
                        continue
                    if abs(x - y) < 1e-9:
                        m += 1
                    elif (mk == "sv" and x > y) or (mk == "hv" and x < y):
                        bb += 1
                    else:
                        ll += 1
                nn = m + bb + ll
                emit(f"  {mk} {mode:7s} {analysis.upper()}: match={m} ({m/nn*100:.1f}%) "
                     f"beat={bb} ({bb/nn*100:.1f}%) lose={ll} ({ll/nn*100:.1f}%) n={nn}")
    RESULTS["c2a_vs_c3"] = "see txt"

    # ================= 7: exact C2a contrasts at n=500 =================
    emit("\n" + "=" * 100)
    emit("7. EXACT PAIRED C2a-C0b and C2a-C1a AT n=500 (naive + clustered)")
    emit("=" * 100)
    for pair in (("C2a", "C0b"), ("C2a", "C1a")):
        a, b = pair
        dmap = cluster_map(merged, a, b, "sv", "strict", "pp")
        dflat = flat(dmap)
        nm, nlo, nhi = bootstrap_ci(list(dflat), n_resamples=N_RES, seed=42)
        _, pn = wilcoxon_paired(list(dflat), [0.0] * len(dflat))
        dm, lo, hi, pc, k, n = clustered_paired(dmap)
        delta = cliffs_delta(list(dflat), [0.0] * len(dflat))
        emit(f"  {a}-{b} (strict PP sv): n={len(dflat)} naive {nm:+.4f} [{nlo:+.4f},{nhi:+.4f}] "
             f"p={pn:.2e} | clustered {dm:+.4f} [{lo:+.4f},{hi:+.4f}] p={pc:.2e} "
             f"Cliff_d={delta:+.3f} (k={k})")
        RESULTS.setdefault("c2a_contrasts", {})[f"{a}-{b}"] = {
            "naive": {"diff": nm, "lo": nlo, "hi": nhi, "p": pn},
            "cluster": {"diff": dm, "lo": lo, "hi": hi, "p": pc, "k": k, "n": n},
            "cliff_delta": float(delta)}

    OUT_JSON.write_text(json.dumps(RESULTS, indent=2, default=float), encoding="utf-8")
    OUT_TXT.write_text("\n".join(_records) + "\n", encoding="utf-8")
    emit(f"\nwrote {OUT_TXT}")
    emit(f"wrote {OUT_JSON}")


if __name__ == "__main__":
    main()
