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
OUT = ROOT / "eval/figures/n500"
DATA = OUT / "data"
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

CONDS = ["C0", "C0b", "C1a", "C2a", "C2b", "C3"]
COND_TAG = {"C0": "LLM", "C0b": "LLM v2", "C1a": "pasted", "C2a": "MCP+crop",
            "C2b": "MCP", "C3": "det"}
COLOR = {"C0": "#0072B2", "C0b": "#56B4E9", "C1a": "#009E73",
         "C2a": "#D55E00", "C2b": "#E69F00", "C3": "#000000"}
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
    fig, axes = plt.subplots(1, 2, figsize=(6.6, 2.5))
    rows = []
    for pi, (mk, lab) in enumerate([("sv", "Season validity"),
                                    ("hv", "Hard-constraint violation")]):
        ax = axes[pi]
        xs = np.arange(len(CONDS))
        means = [cells[f"strict_pp_{c}"][mk][0] for c in CONDS]
        los = [cells[f"strict_pp_{c}"][mk][1] for c in CONDS]
        his = [cells[f"strict_pp_{c}"][mk][2] for c in CONDS]
        ns = [cells[f"strict_pp_{c}"][mk][3] for c in CONDS]
        ax.bar(xs, means, color=[COLOR[c] for c in CONDS], width=0.64,
               edgecolor="black", linewidth=0.4)
        ax.errorbar(xs, means, yerr=[np.array(means) - los, np.array(his) - means],
                    fmt="none", ecolor="black", capsize=2.5, lw=0.8)
        for x, m, hi, n in zip(xs, means, his, ns):
            ax.text(x, hi + 0.015, f"{m:.2f}", ha="center", va="bottom", fontsize=6)
            rows.append(dict(metric=mk, condition=CONDS[x], mean=m, lo=los[x], hi=hi, n=n))
        ax.set_xticks(xs)
        ax.set_xticklabels([f"{c}\n{COND_TAG[c]}" for c in CONDS], fontsize=6)
        ax.set_ylim(0, max(his) * 1.2)
        ax.set_ylabel(lab)
        ax.set_title(f"({'ab'[pi]}) {lab}", fontsize=8)
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


def main():
    fig_n01()
    fig_n02()
    fig_n03()
    fig_n04()
    fig_n05()
    fig_n06()
    fig_n07()
    print("n=500 figures written to", OUT)


if __name__ == "__main__":
    main()
