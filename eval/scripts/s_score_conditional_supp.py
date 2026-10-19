"""S-series SUPPLEMENT: Stale@5 where |D|>0 only (registered formula, undefined cells excluded).

Why: PROTOCOL 8.32.4 defines Stale@5 = |top5 ∩ D| / |D| with D = F0 \\ F1, which is
UNDEFINED when |D| = 0. The scorer (eval/scripts/score_s.py stale_at5) returns 0.0
instead, so every pooled/per-set level and contrast in s_scores.json is diluted by
|D| = 0 cells (the mask is identical across conditions, so pooled contrasts are
proportionally shrunk but sign-preserved; see S_REPORT section on deviations).
This supplement recomputes the registered metric under the natural reading
(undefined cells excluded) with the SAME machinery (score_s.cluster_stats,
holm, SEED=42, N_RES=10000, district clusters, pp/ITT, WITH/WITHOUT pilot,
STRICT/LENIENT, per-set + season + pooled, the four registered contrasts).

Offline; NO model calls; reads ONLY eval/results/s_scores_cells.csv.
Writes eval/results/s_scores_conditional.json. Clearly labelled UNREGISTERED
sensitivity for disclosure; the registered outputs remain s_scores.json.

Run:  py -3 eval/scripts/s_score_conditional_supp.py
"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval/scripts"))

import score_s as S  # noqa: E402  (module-level code is constants + functions only)

OUT = ROOT / "eval/results"
CELLS_CSV = OUT / "s_scores_cells.csv"
METRIC = "stale"


def load_rows() -> list[dict]:
    rows = []
    with CELLS_CSV.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            rows.append({
                "model": r["model"],
                "set": r["set"],
                "sid": r["sid"],
                "district": r["district"],
                "season_stratum": r["season_stratum"],
                "cond": r["condition"],
                "mode": r["mode"],
                "pilot": r["pilot"] == "1",
                "usable": r["usable"] == "1",
                "n_D": int(r["n_D"]),
                "stale": float(r["stale"]),
            })
    return rows


def main() -> None:
    rows = load_rows()
    meta = json.loads((OUT / "s_scores.json").read_text(encoding="utf-8"))["meta"]
    sets = meta["run_sets"]
    idx = {(r["model"], r["set"], r["sid"], r["cond"], r["mode"]): r
           for r in rows}
    subsets = {}
    for r in rows:
        subsets.setdefault("WITH_pilot", set()).add(r["sid"])
    subsets["WITHOUT_pilot"] = {s for s in subsets["WITH_pilot"]
                                if not any(r["pilot"] and r["sid"] == s
                                           for r in rows)}
    # pilot membership is per-sid and constant; compute once
    pilot_sids = {r["sid"] for r in rows if r["pilot"]}
    subsets["WITHOUT_pilot"] = subsets["WITH_pilot"] - pilot_sids

    scopes = ["__pooled__"] + sets
    seasons = ["Kharif", "Rabi", "Zaid"]
    levels: dict[str, dict] = {}
    contrasts: dict[str, dict] = {}
    fam: dict[str, list[str]] = defaultdict(list)

    def level_key(m, sub, an, sc, mode, cond):
        return f"{m}|{sub}|{an}|{sc}|{mode}|{cond}|{METRIC}"

    def contrast_key(m, sub, an, sc, mode, pair):
        return f"{m}|{sub}|{an}|{sc}|{mode}|{METRIC}|{pair}"

    def value_ok(c: dict) -> bool:
        """Registered formula: defined only where |D| > 0."""
        return c["n_D"] > 0

    for model in S.MODELS:
        for subset, sids_sub in subsets.items():
            for an in ("pp", "itt"):
                for sc in scopes:
                    use_sets = sets if sc == "__pooled__" else [sc]
                    for mode in S.MODES:
                        for cond in S.CONDS:
                            by_d: dict[str, list[float]] = defaultdict(list)
                            for st in use_sets:
                                for sid in sids_sub:
                                    c = idx[(model, st, sid, cond, mode)]
                                    if not value_ok(c):
                                        continue
                                    if not c["usable"]:
                                        if an == "itt":
                                            # |D| > 0 by construction -> worst = 1.0
                                            by_d[c["district"]].append(
                                                S.worst_value(METRIC, True))
                                        continue
                                    by_d[c["district"]].append(c[METRIC])
                            levels[level_key(model, subset, an, sc, mode, cond)] = \
                                S.cluster_stats(by_d)
                    # registered contrasts (per scope; n_D mask shared across conds)
                    for mode in S.MODES:
                        keys = []
                        for a, b in S.CONTRASTS:
                            pair = f"{a}-{b}"
                            by_d = defaultdict(list)
                            for st in (sets if sc == "__pooled__" else [sc]):
                                for sid in sids_sub:
                                    ca = idx[(model, st, sid, a, mode)]
                                    cb = idx[(model, st, sid, b, mode)]
                                    if not value_ok(ca):
                                        continue  # same cell -> same n_D
                                    if not (ca["usable"] and cb["usable"]):
                                        if an == "itt":
                                            va = (ca[METRIC] if ca["usable"]
                                                  else S.worst_value(METRIC, True))
                                            vb = (cb[METRIC] if cb["usable"]
                                                  else S.worst_value(METRIC, True))
                                            by_d[ca["district"]].append(va - vb)
                                        continue
                                    by_d[ca["district"]].append(
                                        ca[METRIC] - cb[METRIC])
                            stt = S.cluster_stats(by_d)
                            k = contrast_key(model, subset, an, sc, mode, pair)
                            contrasts[k] = stt
                            keys.append(k)
                        fam[f"{model}|{subset}|{an}|{sc}|{mode}|{METRIC}"] = keys
                for season in seasons:
                    for mode in S.MODES:
                        for cond in S.CONDS:
                            by_d = defaultdict(list)
                            for st in sets:
                                for sid in sids_sub:
                                    c = idx[(model, st, sid, cond, mode)]
                                    if c["season_stratum"] != season:
                                        continue
                                    if not value_ok(c):
                                        continue
                                    if not c["usable"]:
                                        if an == "itt":
                                            by_d[c["district"]].append(
                                                S.worst_value(METRIC, True))
                                        continue
                                    by_d[c["district"]].append(c[METRIC])
                            levels[level_key(model, subset, an,
                                             f"season:{season}", mode, cond)] = \
                                S.cluster_stats(by_d)

    for family, keys in fam.items():
        adj = S.holm([contrasts[k].get("p", 1.0) for k in keys])
        for k, pa in zip(keys, adj):
            contrasts[k]["holm"] = float(pa)

    # ---- output ----------------------------------------------------------------
    sig_cells = {mode: sum(1 for r in rows
                           if r["model"] == "llama" and r["cond"] == "C0"
                           and r["n_D"] > 0 and r["mode"] == mode)
                 for mode in S.MODES}
    all_cells_llama = sum(1 for r in rows if r["model"] == "llama"
                          and r["cond"] == "C0" and r["mode"] == "strict")
    ratio = (all_cells_llama / sig_cells["strict"]
             if sig_cells["strict"] else None)
    out = {
        "meta": {
            "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": "eval/results/s_scores_cells.csv",
            "convention": "registered formula: cells with |D|=0 EXCLUDED "
                           "(score_s stale_at5 returns 0 there; see S_REPORT)",
            "metric": METRIC,
            "n_signal_cells_strict": sig_cells["strict"],
            "n_signal_cells_lenient": sig_cells["lenient"],
            "n_all_cells_per_model_setgrid": all_cells_llama,
            "scale_factor_strict": ratio,
            "registered_contrasts": ["C2a-C0b", "C2b-C0b", "C2a-C1a", "C3-C2b"],
            "unregistered_sensitivity": True,
        },
        "levels": levels,
        "contrasts": contrasts,
    }
    (OUT / "s_scores_conditional.json").write_text(
        json.dumps(out, indent=1, sort_keys=False), encoding="utf-8")

    print(f"signal cells: strict={sig_cells['strict']} "
          f"lenient={sig_cells['lenient']} "
          f"(per-model grid = {all_cells_llama}); scale_strict={ratio:.2f}")
    print("\nCONDITIONAL (|D|>0) POOLED WITH_pilot STALE — levels:")
    for model in S.MODELS:
        for an in ("pp", "itt"):
            line = []
            for cond in S.CONDS:
                v = levels[level_key(model, "WITH_pilot",
                                     an, "__pooled__", "strict", cond)]
                line.append(f"{cond}={v['mean']:.3f}[{v['lo']:.3f},"
                            f"{v['hi']:.3f}](n={v['n']})")
            print(f"  {model} {an}: {' '.join(line)}")
    print("\nCONDITIONAL contrasts:")
    for model in S.MODELS:
        for an in ("pp", "itt"):
            for pair in ("C2a-C0b", "C2b-C0b", "C2a-C1a", "C3-C2b"):
                k = contrast_key(model, "WITH_pilot", an, "__pooled__",
                                 "strict", pair)
                v = contrasts[k]
                print(f"  {model} {an} {pair}: d={v['mean']:+.3f} "
                      f"[{v['lo']:+.3f},{v['hi']:+.3f}] p={v['p']:.4g} "
                      f"holm={v['holm']:.4g} n={v['n']}")
    print("\nwrote eval/results/s_scores_conditional.json")


if __name__ == "__main__":
    main()
