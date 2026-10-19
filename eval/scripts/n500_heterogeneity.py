"""Heterogeneity of the pre-registered contrasts across the B1 (150) and B2 (350) halves,
plus per-season stratification at n=500 (PROTOCOL 8.26).

B1 = eval_nemotron-3-ultra/results.json (150-scenario batch, fresh C1a/C2a/C2b)
B2 = eval_nemotron-3-ultra_b2/results.json (350-scenario batch, fresh C1a/C2a/C2b)

B1 and B2 are disjoint and together form the 500-scenario paired set; C0/C0b come from the
shared verified-reusable cache and C3 from archive_v2 (same reconstruction as
n500_primary_metrics.py).

For each pre-registered contrast (C2a-C0b, C2a-C1a, C2b-C0b, C2b-C1a) this reports the
paired mean difference with a 95% bootstrap CI SEPARATELY on B1, on B2, and on the merged
500, then an interaction estimate Delta = diff(B2) - diff(B1) with a two-sample bootstrap
CI and a two-sided permutation test. Also reports the season composition of B1 vs B2 and
the four contrasts stratified by season_stratum (Kharif/Rabi/Zaid) at n=500.
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

B1_PATH = ROOT / "eval/runs/eval_nemotron-3-ultra/results.json"
B2_PATH = ROOT / "eval/runs/eval_nemotron-3-ultra_b2/results.json"
OUT_TXT = ROOT / "eval/results/n500_heterogeneity.txt"
OUT_JSON = ROOT / "eval/results/n500_heterogeneity.json"

_records: list[str] = []
RESULTS: dict = {}


def emit(s: str = "") -> None:
    print(s)
    _records.append(s)


def _batch_sids(path: Path, universe: set[str]) -> set[str]:
    out = set()
    for r in json.load(open(path, encoding="utf-8")):
        if (r.get("repeat", 0) == 0 and r.get("condition") in ("C1a", "C2a", "C2b")
                and r.get("scenario_id") in universe):
            out.add(r["scenario_id"])
    return out


def two_sample_boot(a, b, n_resamples: int = 10000, seed: int = 42):
    rng = np.random.default_rng(seed)
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    obs = float(a.mean() - b.mean())
    da = rng.choice(a, size=(n_resamples, len(a)), replace=True).mean(axis=1)
    db = rng.choice(b, size=(n_resamples, len(b)), replace=True).mean(axis=1)
    lo, hi = np.percentile(da - db, [2.5, 97.5])
    return obs, float(lo), float(hi)


def permutation_test(a, b, n_perm: int = 5000, seed: int = 42) -> float:
    rng = np.random.default_rng(seed)
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    obs = abs(a.mean() - b.mean())
    pool = np.concatenate([a, b])
    k = len(a)
    cnt = 0
    for _ in range(n_perm):
        rng.shuffle(pool)
        if abs(pool[:k].mean() - pool[k:].mean()) >= obs:
            cnt += 1
    return (cnt + 1) / (n_perm + 1)


def main() -> None:
    subset, sids, season, pilot_set, flags, c3, by = pm.build_data()
    universe = set(sids)
    b1 = _batch_sids(B1_PATH, universe)
    b2 = _batch_sids(B2_PATH, universe)
    b1_sids = [s for s in sids if s in b1]
    b2_sids = [s for s in sids if s in b2]
    merged = b1_sids + b2_sids

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

    def paired_diffs(a, b, sidset, mk, mode, analysis):
        av, bv = [], []
        for sid in sidset:
            x = val(a, sid, mk, mode, analysis)
            y = val(b, sid, mk, mode, analysis)
            if x is None or y is None:
                continue
            av.append(x)
            bv.append(y)
        return np.array(av) - np.array(bv)

    emit("=" * 100)
    emit("HETEROGENEITY / SEASON STRATIFICATION (Nemotron n=500): B1 = 150-scenario batch, "
         "B2 = 350-scenario batch")
    emit("=" * 100)
    emit(f"  B1 distinct sids = {len(b1_sids)} | B2 distinct sids = {len(b2_sids)} | "
         f"overlap = {len(set(b1_sids) & set(b2_sids))} | merged = {len(merged)}")

    comp = {}
    for name, ss in (("B1", b1_sids), ("B2", b2_sids), ("merged", merged)):
        c = Counter(season[s] for s in ss)
        comp[name] = dict(c)
        emit(f"  season composition {name:7s}: Kharif={c.get('Kharif',0)} "
             f"Rabi={c.get('Rabi',0)} Zaid={c.get('Zaid',0)} (n={len(ss)})")
    RESULTS["composition"] = comp
    RESULTS["halves"] = {"b1": len(b1_sids), "b2": len(b2_sids),
                         "overlap": len(set(b1_sids) & set(b2_sids))}

    emit("\n" + "=" * 100)
    emit("PART A: PRE-REGISTERED CONTRASTS ON B1 (150), B2 (350), MERGED (500), + INTERACTION")
    emit("(expected per author: C2b-C0b and C2b-C1a on season-validity ~ +0.061 on B1 vs "
         "+0.157 on B2)")
    emit("=" * 100)

    iact = {}
    for mode in ("strict", "lenient"):
        for analysis in ("pp", "itt"):
            for metric, mk in (("season-validity", "sv"), ("hard-violation", "hv")):
                emit(f"\n--- {mode.upper()} | {'per-protocol' if analysis=='pp' else 'ITT'} | "
                     f"{metric} ---")
                emit(f"  {'contrast':11s} {'B1 diff [95% CI] (n)':38s} "
                     f"{'B2 diff [95% CI] (n)':38s} {'interaction diff(B2)-diff(B1) [95% CI]':44s} perm_p")
                for a, b in PAIRS:
                    d1 = paired_diffs(a, b, b1_sids, mk, mode, analysis)
                    d2 = paired_diffs(a, b, b2_sids, mk, mode, analysis)
                    dm1, lo1, hi1 = bootstrap_ci(list(d1), n_resamples=10000, seed=42)
                    dm2, lo2, hi2 = bootstrap_ci(list(d2), n_resamples=10000, seed=42)
                    inter, ilo, ihi = two_sample_boot(d2, d1)
                    perm_p = permutation_test(d2, d1)
                    key = f"{mode}_{analysis}_{mk}_{a}-{b}"
                    iact[key] = {"b1": {"diff": dm1, "lo": lo1, "hi": hi1, "n": len(d1)},
                                 "b2": {"diff": dm2, "lo": lo2, "hi": hi2, "n": len(d2)},
                                 "interaction": {"diff": inter, "lo": ilo, "hi": ihi, "perm_p": perm_p}}
                    emit(f"  {a}-{b:4s} {dm1:+.3f} [{lo1:+.3f},{hi1:+.3f}] ({len(d1):3d})".ljust(11 + 38)
                         + f" {dm2:+.3f} [{lo2:+.3f},{hi2:+.3f}] ({len(d2):3d})".ljust(38 + 1)
                         + f" {inter:+.3f} [{ilo:+.3f},{ihi:+.3f}]".ljust(44) + f" {perm_p:.4f}")
    RESULTS["interaction"] = iact

    emit("\n" + "=" * 100)
    emit("PART B: PRE-REGISTERED CONTRASTS STRATIFIED BY SEASON (n=500)")
    emit("=" * 100)
    strat = {}
    for mode in ("strict", "lenient"):
        for analysis in ("pp", "itt"):
            for metric, mk in (("season-validity", "sv"), ("hard-violation", "hv")):
                emit(f"\n--- {mode.upper()} | {'per-protocol' if analysis=='pp' else 'ITT'} | "
                     f"{metric} ---")
                for season_name in ("Kharif", "Rabi", "Zaid"):
                    ss = [s for s in merged if season[s] == season_name]
                    emit(f"  [{season_name}] n={len(ss)}")
                    pvals, rows = [], []
                    for a, b in PAIRS:
                        d = paired_diffs(a, b, ss, mk, mode, analysis)
                        if len(d) < 2:
                            continue
                        dm, lo, hi = bootstrap_ci(list(d), n_resamples=10000, seed=42)
                        delta = cliffs_delta(list(d), [0.0] * len(d))
                        _, p = wilcoxon_paired(list(d), [0.0] * len(d))
                        pvals.append(p)
                        rows.append({"pair": f"{a}-{b}", "n": len(d), "diff": dm,
                                     "lo": lo, "hi": hi, "cliff_d": float(delta), "p": float(p)})
                    adj = holm_bonferroni(pvals) if pvals else []
                    for row, pa in zip(rows, adj):
                        row["holm"] = float(pa)
                        strat[f"{mode}_{analysis}_{mk}_{season_name}_{row['pair']}"] = row
                        emit(f"    {row['pair']}: n={row['n']:3d} diff={row['diff']:+.3f} "
                             f"[{row['lo']:+.3f},{row['hi']:+.3f}] Cliff_d={row['cliff_d']:+.3f} "
                             f"p={row['p']:.3e} holm={pa:.3e}")
    RESULTS["by_season"] = strat

    OUT_JSON.write_text(json.dumps(RESULTS, indent=2, default=float), encoding="utf-8")
    OUT_TXT.write_text("\n".join(_records) + "\n", encoding="utf-8")
    emit(f"\nwrote {OUT_TXT}")
    emit(f"wrote {OUT_JSON}")


if __name__ == "__main__":
    main()
