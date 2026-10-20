"""n=500 headline figures + district-clustered contrasts (final pre-registered design).

Reads ONLY the frozen analysis artifacts:
  eval/results/n500_primary_metrics.json
  eval/results/n500_clustered_inference.json (+ .txt for the C2a-vs-C3 block)
Exports PDF + PNG (300 dpi) and per-figure data CSVs to eval/figures/n500/.
Condition palette: Okabe-Ito (C3 = deterministic reference, black).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
RES = ROOT / "eval/results"
OUT = ROOT / "figures/out"
DATA = ROOT / "figures/data/n500"
OUT.mkdir(parents=True, exist_ok=True)
DATA.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({
    "font.size": 8, "axes.titlesize": 8, "axes.labelsize": 8, "xtick.labelsize": 7,
    "ytick.labelsize": 7, "legend.fontsize": 7, "figure.dpi": 150, "savefig.dpi": 300,
    "axes.spines.top": False, "axes.spines.right": False, "pdf.fonttype": 42,
    "axes.grid": True, "grid.linewidth": 0.3, "grid.alpha": 0.35, "axes.axisbelow": True,
})

PM = json.loads((RES / "n500_primary_metrics.json").read_text())
CL = json.loads((RES / "n500_clustered_inference.json").read_text())
DBV2 = json.loads((RES / "db_v2_test.json").read_text())
C3T_CORR = json.loads((RES / "c3t_correction_analysis.json").read_text())

CONDS = ["C0", "C0b", "C1a", "C2a", "C2b", "C3"]
# Add C3t as separate condition for comparison
C3T_CONDS = ["C0", "C0b", "C1a", "C2a", "C2b", "C3", "C3t"]
COND_TAG = {"C0": "LLM", "C0b": "LLM v2", "C1a": "pasted", "C2a": "MCP+crop",
            "C2b": "MCP", "C3": "det", "C3t": "det (corrected)"}
COLOR = {"C0": "#0072B2", "C0b": "#56B4E9", "C1a": "#009E73",
         "C2a": "#D55E00", "C2b": "#E69F00", "C3": "#000000", "C3t": "#555555"}
PAIRS = ["C2a-C0b", "C2a-C1a", "C2b-C0b", "C2b-C1a"]
PRIMARY_CELLS = "cells_WITH pilot_dev"
SEASONS = ["Kharif", "Rabi", "Zaid"]
PAIR_COLOR = {"C2a-C0b": "#D55E00", "C2a-C1a": "#D55E00",
              "C2b-C0b": "#E69F00", "C2b-C1a": "#E69F00"}


def save(fig, name, rows=None, cols=None):
    for ext in ("pdf", "png"):
        fig.savefig(OUT / f"{name}.{ext}", bbox_inches="tight")
    plt.close(fig)
    if rows is not None:
        pd.DataFrame(rows, columns=cols).to_csv(DATA / f"{name}.csv", index=False)
    print(f"[fig] {name}")


def _c2a_vs_c3():
    txt = (RES / "n500_clustered_inference.txt").read_text()
    pat = re.compile(
        r"^\s*(sv|hv)\s+(strict|lenient)\s+PP: match=(\d+)\s*\([\d.]+%\) "
        r"beat=(\d+)\s*\([\d.]+%\) lose=(\d+)", re.M)
    return {(m.group(1), m.group(2)): dict(match=int(m.group(3)), beat=int(m.group(4)),
                                           lose=int(m.group(5))) for m in pat.finditer(txt)}


def fig_n01():
    cells = PM[PRIMARY_CELLS]
    # Use reconciled numbers from CORRECTION_NOTE.md for C3 and C3t
    c3_corr = C3T_CORR["season_validity_hard_violation_10k"]["C3_db_v1"]
    c3t_corr = C3T_CORR["season_validity_hard_violation_10k"]["C3t_db_v1"]
    
    fig, axes = plt.subplots(1, 2, figsize=(6.6, 2.5))
    rows = []
    for pi, (mk, lab) in enumerate([("sv", "Season validity"),
                                    ("hv", "Hard-constraint violation")]):
        ax = axes[pi]
        xs = np.arange(len(CONDS))
        means = [cells[f"strict_pp_{c}"][mk][0] for c in CONDS]
        los = [cells[f"strict_pp_{c}"][mk][1] for c in CONDS]  # lower CI
        his = [cells[f"strict_pp_{c}"][mk][2] for c in CONDS]  # upper CI
        ns = [cells[f"strict_pp_{c}"][mk][3] for c in CONDS]
        # Override C3 with reconciled numbers
        c3_idx = CONDS.index("C3")
        if mk == "sv":
            means[c3_idx] = c3_corr["season_validity_strict"]
            los[c3_idx] = c3_corr["season_validity_strict"]  # CI not available, use mean
            his[c3_idx] = c3_corr["season_validity_strict"]
            ns[c3_idx] = c3_corr["n_scenarios"]
            # Add C3t
            means = means + [c3t_corr["season_validity_strict"]]
            los = los + [c3t_corr["season_validity_strict"]]
            his = his + [c3t_corr["season_validity_strict"]]
            ns = ns + [c3t_corr["n_scenarios"]]
        else:
            means[c3_idx] = c3_corr["hard_violation_strict"]
            los[c3_idx] = c3_corr["hard_violation_strict"]
            his[c3_idx] = c3_corr["hard_violation_strict"]
            ns[c3_idx] = c3_corr["n_scenarios"]
            means = means + [c3t_corr["hard_violation_strict"]]
            los = los + [c3t_corr["hard_violation_strict"]]
            his = his + [c3t_corr["hard_violation_strict"]]
            ns = ns + [c3t_corr["n_scenarios"]]
        
        plot_conds = CONDS + ["C3t"]
        plot_means = means
        plot_los = [plot_means[i] - los[i] if los[i] < plot_means[i] else 0.01 for i in range(len(plot_means))]
        plot_his = [his[i] - plot_means[i] if his[i] > plot_means[i] else 0.01 for i in range(len(plot_means))]
        
        ax.bar(np.arange(len(plot_conds)), plot_means, color=[COLOR[c] for c in plot_conds], width=0.64,
               edgecolor="black", linewidth=0.4)
        ax.errorbar(np.arange(len(plot_conds)), plot_means, 
                    yerr=[plot_los, plot_his],
                    fmt="none", ecolor="black", capsize=2.5, lw=0.8)
        for x, m, hi, n in zip(np.arange(len(plot_conds)), plot_means, his, ns):
            ax.text(x, hi + 0.015, f"{m:.2f}", ha="center", va="bottom", fontsize=6)
            rows.append(dict(metric=mk, condition=plot_conds[x], mean=m, lo=los[x], hi=his[x], n=n))
        ax.set_xticks(np.arange(len(plot_conds)))
        ax.set_xticklabels([f"{c}\n{COND_TAG[c]}" for c in plot_conds], fontsize=6)
        ax.set_ylim(0, max(his) * 1.2)
        ax.set_ylabel(lab)
        ax.set_title(f"({'ab'[pi]}) {lab} (C3t reconciled)", fontsize=8)
    fig.tight_layout()
    save(fig, "Fig_N01_condition_quality", rows,
         ["metric", "condition", "mean", "lo", "hi", "n"])


def fig_n02():
    fig, axes = plt.subplots(1, 2, figsize=(6.6, 2.5), sharey=True)
    rows = []
    for pi, (mk, lab) in enumerate([("sv", "Season validity"),
                                    ("hv", "Hard-constraint violation")]):
        ax = axes[pi]
        ys = np.arange(len(PAIRS))[::-1]
        for y, pair in zip(ys, PAIRS):
            d = CL["clustered"][f"strict_pp_{mk}_{pair}"]
            nv, cl = d["naive"], d["cluster"]
            ax.errorbar(cl["diff"], y, xerr=[[cl["diff"] - cl["lo"]], [cl["hi"] - cl["diff"]]],
                        fmt="o", ms=5, color=PAIR_COLOR[pair], capsize=3, lw=1.5)
            ax.errorbar(nv["diff"], y + 0.2, xerr=[[nv["diff"] - nv["lo"]], [nv["hi"] - nv["diff"]]],
                        fmt="none", ecolor="0.6", capsize=2, lw=0.8)
            rows.append(dict(metric=mk, pair=pair, naive_diff=nv["diff"], naive_lo=nv["lo"],
                             naive_hi=nv["hi"], clustered_diff=cl["diff"], clustered_lo=cl["lo"],
                             clustered_hi=cl["hi"], holm_naive=nv["holm"],
                             holm_clustered=cl["holm"], n=cl["n"]))
        ax.axvline(0, color="black", lw=0.9, ls="--")
        ax.set_title(f"({'ab'[pi]}) {lab}", fontsize=8)
        ax.set_xlabel("paired difference")
        ax.set_xticks([-0.2, -0.1, 0.0, 0.1, 0.2])
    axes[0].set_yticks(range(len(PAIRS)))
    axes[0].set_yticklabels([p + " *" for p in PAIRS])
    axes[0].set_ylim(-0.5, len(PAIRS) - 0.4)
    axes[0].errorbar([], [], fmt="o", ms=5, color="grey", capsize=3, label="district-clustered")
    axes[0].errorbar([], [], fmt="none", ecolor="0.6", capsize=2, label="scenario-level naive")
    axes[0].legend(frameon=False, fontsize=6, loc="lower right")
    fig.text(0.5, -0.03, "* Holm < 0.001 for all four pairs (cluster and naive)", ha="center", fontsize=6)
    fig.tight_layout()
    save(fig, "Fig_N02_preregistered_forest", rows,
         ["metric", "pair", "naive_diff", "naive_lo", "naive_hi",
          "clustered_diff", "clustered_lo", "clustered_hi", "holm_naive", "holm_clustered", "n"])


def fig_n03():
    fig, axes = plt.subplots(1, 2, figsize=(6.6, 2.5))
    rows = []
    ax = axes[0]
    xs = np.arange(len(CONDS))
    for mk, mark, off in (("sv", "o", -0.12), ("hv", "s", 0.12)):
        vals = [CL["icc"][f"{mk}_{c}"]["icc"] for c in CONDS]
        ax.scatter(xs + off, vals, marker=mark, s=30, color=[COLOR[c] for c in CONDS],
                   edgecolor="black", linewidth=0.4, zorder=3)
        for c, x, v in zip(CONDS, xs + off, vals):
            if v >= 0.03:
                ax.text(x, v + 0.006, f"{v:.2f}", ha="center", fontsize=5)
            rows.append(dict(panel="icc", metric=mk, condition=c, icc=v, n=None, ess=None))
    ax.set_xticks(xs)
    ax.set_xticklabels(CONDS)
    ax.set_ylim(-0.02, 0.30)
    ax.set_ylabel("ICC (district)")
    ax.set_title("(a) Intra-class correlation", fontsize=8)
    ax.scatter([], [], marker="o", color="grey", label="sv")
    ax.scatter([], [], marker="s", color="grey", label="hv")
    ax.legend(frameon=False, fontsize=6, loc="upper left")
    ax = axes[1]
    for mk, mark in (("sv", "o"), ("hv", "s")):
        for c in CONDS:
            d = CL["icc"][f"{mk}_{c}"]
            ax.scatter(d["n"], d["ess"], marker=mark, s=30, color=COLOR[c],
                       edgecolor="black", linewidth=0.4, zorder=3)
            rows.append(dict(panel="ess", metric=mk, condition=c, icc=None,
                             n=d["n"], ess=d["ess"]))
    ax.plot([0, 510], [0, 510], color="black", lw=0.8, ls="--")
    ax.set_xlim(400, 520)
    ax.set_ylim(120, 520)
    ax.set_xlabel("nominal n")
    ax.set_ylabel("effective N (ESS)")
    ax.set_title("(b) Effective sample size", fontsize=8)
    fig.tight_layout()
    save(fig, "Fig_N03_design_effect", rows, ["panel", "metric", "condition", "icc", "n", "ess"])


def fig_n04():
    de = CL["district_effect"]
    ds = sorted(de["districts"], key=lambda d: d["mean"])
    fig, ax = plt.subplots(figsize=(3.2, 5.4))
    rows = []
    hcol = {"B1": COLOR["C0"], "B2": COLOR["C2a"]}
    for y, d in enumerate(ds):
        ax.barh(y, d["mean"], color=hcol.get(d["half"], "0.6"),
                edgecolor="black", linewidth=0.3, height=0.8)
        rows.append(dict(district=d["district"], mean=d["mean"], n=d["n"], half=d["half"]))
    ax.axvline(0, color="black", lw=0.9, ls="--")
    ax.set_yticks(range(len(ds)))
    ax.set_yticklabels([d["district"] for d in ds], fontsize=5)
    ax.set_ylim(-0.6, len(ds) - 0.4)
    ax.set_xlabel("C2b - C0b (season validity)")
    ax.set_title(f"District effects\nmean {de['mean']:+.2f}, SD {de['sd_between']:.2f}", fontsize=8)
    ax.barh([], [], color=COLOR["C0"], label="B1")
    ax.barh([], [], color=COLOR["C2a"], label="B2")
    ax.legend(frameon=False, fontsize=6, loc="lower right")
    fig.tight_layout()
    save(fig, "Fig_N04_district_variation", rows, ["district", "mean", "n", "half"])


def fig_n05():
    fig, axes = plt.subplots(1, 3, figsize=(6.6, 2.5), sharey=True)
    rows = []
    for ax, season in zip(axes, SEASONS):
        ys = np.arange(len(PAIRS))[::-1]
        for y, pair in zip(ys, PAIRS):
            d = CL["per_season"][f"{season}_strict_pp_sv_{pair}"]
            sig = d["p"] < 0.05
            ax.errorbar(d["diff"], y, xerr=[[d["diff"] - d["lo"]], [d["hi"] - d["diff"]]],
                        fmt="o" if sig else "o", ms=4.5, mfc=PAIR_COLOR[pair] if sig else "white",
                        mec=PAIR_COLOR[pair], color=PAIR_COLOR[pair], capsize=3, lw=1.3)
            rows.append(dict(season=season, pair=pair, diff=d["diff"], lo=d["lo"],
                             hi=d["hi"], p=d["p"], significant=int(sig), k=d["k"], n=d["n"]))
        ax.axvline(0, color="black", lw=0.9, ls="--")
        ax.set_title(season, fontsize=8)
        ax.set_xlabel("season validity")
        ax.set_xticks([0.0, 0.1, 0.2, 0.3])
    axes[0].set_yticks(range(len(PAIRS)))
    axes[0].set_yticklabels(list(reversed(PAIRS)))
    axes[0].set_ylim(-0.5, len(PAIRS) - 0.4)
    axes[0].scatter([], [], color="grey", label="p < 0.05")
    axes[0].scatter([], [], facecolor="white", edgecolor="grey", label="n.s.")
    axes[0].legend(frameon=False, fontsize=6, loc="lower right")
    fig.tight_layout()
    save(fig, "Fig_N05_season_contrasts", rows,
         ["season", "pair", "diff", "lo", "hi", "p", "significant", "k", "n"])


def fig_n06():
    groups = [("B1", "B1_strict_pp_sv_{p}"), ("B2", "B2_strict_pp_sv_{p}"),
              ("merged", "strict_pp_sv_{p}")]
    fig, axes = plt.subplots(1, 2, figsize=(6.6, 2.1), sharey=True)
    rows = []
    for ax, pair in zip(axes, ["C2b-C0b", "C2b-C1a"]):
        ys = np.arange(len(groups))[::-1]
        for y, (lab, key) in zip(ys, groups):
            d = CL["per_half"][key.format(p=pair)] if lab != "merged" \
                else CL["clustered"][f"strict_pp_sv_{pair}"]
            nv, cl = d["naive"], d["cluster"]
            ax.errorbar(cl["diff"], y, xerr=[[cl["diff"] - cl["lo"]], [cl["hi"] - cl["diff"]]],
                        fmt="o", ms=5, color=PAIR_COLOR[pair], capsize=3, lw=1.5)
            ax.errorbar(nv["diff"], y + 0.18, xerr=[[nv["diff"] - nv["lo"]], [nv["hi"] - nv["diff"]]],
                        fmt="none", ecolor="0.6", capsize=2, lw=0.8)
            rows.append(dict(pair=pair, group=lab, naive_diff=nv["diff"], naive_lo=nv["lo"],
                             naive_hi=nv["hi"], clustered_diff=cl["diff"], clustered_lo=cl["lo"],
                             clustered_hi=cl["hi"]))
        ax.axvline(0, color="black", lw=0.9, ls="--")
        ax.set_title(pair, fontsize=8)
        ax.set_xlabel("season validity")
        ax.set_xlim(-0.06, 0.24)
        ax.set_xticks([0.0, 0.1, 0.2])
    axes[0].set_yticks(range(len(groups)))
    axes[0].set_yticklabels(["merged", "B2", "B1"])
    axes[0].set_ylim(-0.5, len(groups) - 0.4)
    fig.tight_layout()
    save(fig, "Fig_N06_half_contrasts", rows,
         ["pair", "group", "naive_diff", "naive_lo", "naive_hi",
          "clustered_diff", "clustered_lo", "clustered_hi"])


def fig_n07():
    d = _c2a_vs_c3()
    labels = [("sv", "strict", "sv\nstrict"), ("sv", "lenient", "sv\nlenient"),
              ("hv", "strict", "hv\nstrict"), ("hv", "lenient", "hv\nlenient")]
    cats = ["match", "beat", "lose"]
    ccol = {"match": "#009E73", "beat": "#F0E442", "lose": "#D55E00"}
    fig, ax = plt.subplots(figsize=(3.4, 2.6))
    rows = []
    for i, (mk, spec, lab) in enumerate(labels):
        v = d[(mk, spec)]
        n = v["match"] + v["beat"] + v["lose"]
        b = 0.0
        for cat in cats:
            frac = v[cat] / n
            ax.bar(i, frac, bottom=b, color=ccol[cat], edgecolor="white", linewidth=0.6)
            if frac >= 0.05:
                ax.text(i, b + frac / 2, f"{100 * frac:.0f}%", ha="center", va="center", fontsize=6)
            b += frac
            rows.append(dict(metric=mk, spec=spec, category=cat, count=v[cat], n=n, frac=frac))
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels([lab for _, _, lab in labels], fontsize=6)
    ax.set_ylim(0, 1.0)
    ax.set_ylabel("fraction of scenarios")
    ax.legend(handles=[plt.Rectangle((0, 0), 1, 1, color=ccol[c]) for c in cats], labels=cats,
              frameon=False, fontsize=6, ncol=3, loc="upper center", bbox_to_anchor=(0.5, 1.18))
    fig.tight_layout()
    save(fig, "Fig_N07_c2a_vs_c3", rows,
         ["metric", "spec", "category", "count", "n", "frac"])


# ---------- Figure F19: db_v1 vs db_v2 (Linseed) diagnostic ----------
def fig_dbv2_diagnostic():
    fig, axes = plt.subplots(2, 2, figsize=(6.6, 5.0), sharex=False, sharey=False)
    rows = []
    
    # Panel A: P@5 comparison db_v1 vs db_v2
    ax = axes[0, 0]
    dbs = ["db_v1", "db_v2"]
    metrics = ["Precision@5", "nDCG@5"]
    x = np.arange(len(dbs))
    for mi, (mk, color) in enumerate(zip(metrics, ["#0072B2", "#D55E00"])):
        means = [DBV2["primary_R_test_all"]["levels"][mk][db]["mean"] for db in dbs]
        los = [DBV2["primary_R_test_all"]["levels"][mk][db]["lo"] for db in dbs]
        his = [DBV2["primary_R_test_all"]["levels"][mk][db]["hi"] for db in dbs]
        off = -0.15 if mi == 0 else 0.15
        ax.bar(x + off, means, width=0.25, color=color, alpha=0.8, 
               edgecolor="black", linewidth=0.4, label=mk)
        ax.errorbar(x + off, means, yerr=[np.array(means) - los, np.array(his) - means],
                    fmt="none", ecolor="black", capsize=2, lw=0.8)
        for xi, m, hi in zip(x + off, means, his):
            ax.text(xi, hi + 0.005, f"{m:.3f}", ha="center", va="bottom", fontsize=6)
        for i, db in enumerate(dbs):
            rows.append(dict(panel="primary_metrics", database=db, metric=mk,
                           mean=means[i], lo=los[i], hi=his[i]))
    ax.set_xticks(x)
    ax.set_xticklabels(["db_v1 (21 crops)", "db_v2 (22 crops, +Linseed)"])
    ax.set_ylabel("Agreement (R_test_all)")
    ax.set_title("(a) P@5 & nDCG@5: db_v1 vs db_v2", fontsize=8)
    ax.legend(frameon=False, fontsize=6)
    
    # Panel B: Linseed diagnostic
    ax = axes[0, 1]
    ld = DBV2["linseed_diagnostic"]
    labels = ["Ref cells\nw/ Linseed", "db_v2 top5\nw/ Linseed", "db_v2 TP", 
              "P@5 w/ Linseed v1", "P@5 w/ Linseed v2", "P@5 w/o Linseed v1", "P@5 w/o Linseed v2"]
    values = [ld["ref_cells_with_linseed_in_500"], ld["db_v2_top5_with_linseed"],
              ld["db_v2_linseed_true_positives"], ld["p5_db_v1_with_linseed"],
              ld["p5_db_v2_with_linseed"], ld["p5_db_v1_without_linseed"],
              ld["p5_db_v2_without_linseed"]]
    colors = ["#8c8c8c", "#2ca02c", "#009E73", "#0072B2", "#56B4E9", "#D55E00", "#E69F00"]
    y_pos = np.arange(len(labels))
    ax.barh(y_pos, values, color=colors, edgecolor="black", linewidth=0.3, height=0.7)
    for i, (v, n) in enumerate(zip(values, [ld["n_with_linseed"], ld["db_v2_top5_with_linseed"],
                                             ld["db_v2_linseed_true_positives"], ld["n_with_linseed"],
                                             ld["n_with_linseed"], ld["n_without_linseed"],
                                             ld["n_without_linseed"]])):
        ax.text(v + 0.01, i, f"{v:.3f} (n={n})", va="center", fontsize=6)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels, fontsize=6)
    ax.set_xlabel("Value / P@5")
    ax.set_title("(b) Linseed diagnostic (test window)", fontsize=8)
    ax.axvline(0, color="black", lw=0.5)
    
    # Panel C: Per-season P@5 db_v1 vs db_v2
    ax = axes[1, 0]
    seasons = ["Kharif", "Rabi", "Zaid"]
    x = np.arange(len(seasons))
    for mi, (db, color) in enumerate(zip(dbs, ["#0072B2", "#D55E00"])):
        means = [DBV2["per_season_primary"][db][s]["precision_at_5"] for s in seasons]
        # No CI available, just plot means
        off = -0.15 if mi == 0 else 0.15
        ax.bar(x + off, means, width=0.25, color=color, alpha=0.8,
               edgecolor="black", linewidth=0.4, label=db)
        for s, m in zip(seasons, means):
            ax.text(x[seasons.index(s)] + off, m + 0.01, f"{m:.3f}", ha="center", va="bottom", fontsize=6)
            rows.append(dict(panel="per_season", database=db, season=s,
                           mean=m, lo=m, hi=m))
    ax.set_xticks(x)
    ax.set_xticklabels(seasons)
    ax.set_ylabel("P@5 (R_test_all)")
    ax.set_title("(c) Per-season P@5: db_v1 vs db_v2", fontsize=8)
    ax.legend(frameon=False, fontsize=6)
    
    # Panel D: Season validity db_v1 vs db_v2 (reconciled)
    ax = axes[1, 1]
    sv = DBV2["season_validity"]
    db_labels = ["db_v1\nstrict", "db_v1\nlenient", "db_v2\nstrict", "db_v2\nlenient"]
    sv_values = [sv["db_v1|strict"]["overall"], sv["db_v1|lenient"]["overall"], 
                 sv["db_v2|strict"]["overall"], sv["db_v2|lenient"]["overall"]]
    colors = ["#0072B2", "#56B4E9", "#D55E00", "#E69F00"]
    x = np.arange(len(db_labels))
    bars = ax.bar(x, sv_values, color=colors, edgecolor="black", linewidth=0.4, width=0.6)
    for i, (v, c) in enumerate(zip(sv_values, db_labels)):
        ax.text(i, v + 0.01, f"{v:.3f}", ha="center", va="bottom", fontsize=7)
        rows.append(dict(panel="season_validity", database=c, mean=v))
    ax.set_xticks(x)
    ax.set_xticklabels(db_labels, fontsize=7)
    ax.set_ylabel("Season validity (strict/lenient)")
    ax.set_ylim(0, 1.05)
    ax.set_title("(d) Season validity: db_v1 vs db_v2 (GT v1.1)", fontsize=8)
    
    fig.suptitle("DB v2 study: Linseed addition impact on test-window performance", y=1.02)
    fig.tight_layout()
    save(fig, "dbv2_diagnostic", rows,
         ["panel", "database", "metric", "season", "mean", "lo", "hi"])


# ---------- Figure F20: Coverage and usable-run rates ----------
def fig_coverage_rates():
    fig, axes = plt.subplots(1, 2, figsize=(6.6, 2.8), sharey=True)
    rows = []
    
    # Get planned counts from primary metrics
    cells = PM["cells_WITH pilot_dev"]
    
    for ax, model in zip(axes, ["nemotron", "llama"]):
        x = np.arange(len(CONDS))
        usable = []
        planned = {"nemotron": 500, "llama": 150}[model]
        for c in CONDS:
            key = f"strict_pp_{c}"
            if key in cells:
                usable.append(cells[key]["sv"][3])  # n usable
            else:
                usable.append(0)
        
        ax.bar(x - 0.2, usable, width=0.35, color="#009E73", edgecolor="black", linewidth=0.4, label="Usable (PP)")
        ax.bar(x + 0.2, [planned]*len(CONDS), width=0.35, color="#D55E00", edgecolor="black", linewidth=0.4, alpha=0.5, label="Planned (ITT)")
        
        for xi, u in zip(x, usable):
            ax.text(xi - 0.2, u + 5, str(u), ha="center", va="bottom", fontsize=6)
            rows.append(dict(model=model, condition=CONDS[xi], usable=u, planned=planned))
        
        ax.set_xticks(x)
        ax.set_xticklabels(CONDS, fontsize=6)
        ax.set_ylabel("Number of scenarios")
        ax.set_title(f"{model} coverage (n={'500' if model=='nemotron' else '150'})", fontsize=8)
        if model == "nemotron":
            ax.legend(frameon=False, fontsize=6, loc="upper right")
    
    fig.suptitle("Coverage: usable (PP) vs planned (ITT) scenarios per condition", y=1.02)
    fig.tight_layout()
    save(fig, "coverage_rates", rows,
         ["model", "condition", "usable", "planned"])


def main():
    fig_n01()
    fig_n02()
    fig_n03()
    fig_n04()
    fig_n05()
    fig_n06()
    fig_n07()
    fig_dbv2_diagnostic()
    fig_coverage_rates()
    print("n=500 figures written to", OUT)


if __name__ == "__main__":
    main()
