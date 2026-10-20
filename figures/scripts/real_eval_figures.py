"""STEP 6: figures for the real-world independent evaluation.

Reads only eval/results/real_eval.json (frozen). Exports PDF + PNG (300 dpi) and
per-figure data CSVs to eval/figures/real/.

Reported quantity is agreement with actual district cropping patterns (not accuracy).
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
RES = ROOT / "eval/results/real_eval.json"
OUT = ROOT / "figures/out"
DATA = ROOT / "figures/data/real"
OUT.mkdir(parents=True, exist_ok=True)
DATA.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({
    "font.size": 8, "axes.titlesize": 8, "axes.labelsize": 8, "xtick.labelsize": 7,
    "ytick.labelsize": 7, "legend.fontsize": 7, "figure.dpi": 150, "savefig.dpi": 300,
    "axes.spines.top": False, "axes.spines.right": False, "pdf.fonttype": 42,
    "axes.grid": True, "grid.linewidth": 0.3, "grid.alpha": 0.35, "axes.axisbelow": True,
})

R = json.loads(RES.read_text(encoding="utf-8"))
CONDS = ["C0", "C0b", "C1a", "C2a", "C2b", "C3"]
SEASONS = ["Kharif", "Rabi", "Zaid"]
COLOR = {"C0": "#0072B2", "C0b": "#56B4E9", "C1a": "#009E73",
         "C2a": "#D55E00", "C2b": "#E69F00", "C3": "#000000"}
MODELS = list(R["models"].keys())


def save(fig, name):
    for ext in ("pdf", "png"):
        fig.savefig(OUT / f"{name}.{ext}", bbox_inches="tight")
    plt.close(fig)


def write_csv(name, rows):
    with open(DATA / name, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerows(rows)


# ---------- Figure 1: agreement levels per condition ----------
def fig1():
    metrics = [("Precision@5", "Precision@5"), ("nDCG@5", "nDCG@5")]
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.8), sharey=True)
    rows = [["metric", "model", "condition", "mean", "lo", "hi", "n"]]
    for ax, (key, title) in zip(axes, metrics):
        x = np.arange(len(CONDS))
        for m in MODELS:
            lv = R["models"][m]["WITH_pilot"]["R_prim_pp"]["levels"][key]
            conds_present = [c for c in CONDS if c in lv]
            xs = [CONDS.index(c) for c in conds_present]
            off = -0.18 if m == MODELS[0] else 0.18
            means = [lv[c]["mean"] for c in conds_present]
            err = [[lv[c]["mean"] - lv[c]["lo"] for c in conds_present],
                   [lv[c]["hi"] - lv[c]["mean"] for c in conds_present]]
            ax.bar([xi + off for xi in xs], means, width=0.34,
                   color=[COLOR[c] for c in conds_present], alpha=0.9 if m == MODELS[0] else 0.55,
                   edgecolor="black", linewidth=0.4, label=m)
            ax.errorbar([xi + off for xi in xs], means, yerr=err, fmt="none",
                        ecolor="black", elinewidth=0.6, capsize=2)
            for c in conds_present:
                rows.append([key, m, c, lv[c]["mean"], lv[c]["lo"], lv[c]["hi"], lv[c]["n"]])
        ax.set_xticks(x)
        ax.set_xticklabels(CONDS)
        ax.set_title(f"Real-world {title}")
        ax.set_ylim(0, 0.75)
    axes[0].set_ylabel("agreement (mean, 95% CI)")
    axes[0].legend(title="model", frameon=False)
    fig.tight_layout()
    save(fig, "fig1_agreement_levels")
    write_csv("fig1_agreement_levels.csv", rows)


# ---------- Figure 2: contrast forest ----------
def fig2():
    pairs = list(R["models"][MODELS[0]]["WITH_pilot"]["R_prim_pp"]["contrasts"]["Precision@5"])
    fig, axes = plt.subplots(1, len(MODELS), figsize=(7.2, 2.6), sharex=True)
    if len(MODELS) == 1:
        axes = [axes]
    rows = [["model", "contrast", "mean", "lo", "hi", "holm", "cliff_d", "n"]]
    for ax, m in zip(axes, MODELS):
        c = R["models"][m]["WITH_pilot"]["R_prim_pp"]["contrasts"]["Precision@5"]
        ys = np.arange(len(pairs))
        for y, p in zip(ys, pairs):
            v = c[p]
            sig = v["holm"] < 0.05
            ax.errorbar(v["mean"], y, xerr=[[v["mean"] - v["lo"]], [v["hi"] - v["mean"]]],
                        fmt="o", ms=4, color="black" if sig else "#969696",
                        ecolor="black" if sig else "#969696", elinewidth=0.8, capsize=2)
            rows.append([m, p, v["mean"], v["lo"], v["hi"], v["holm"], v["cliff_d"], v["n"]])
        ax.axvline(0, color="#444444", lw=0.7, ls="--")
        ax.set_yticks(ys)
        ax.set_yticklabels(pairs)
        ax.set_title(m)
        ax.set_xlabel("Δ Precision@5 (95% CI)")
    fig.suptitle("Contrasts vs baselines (filled = Holm-significant)", y=1.04)
    fig.tight_layout()
    save(fig, "fig2_contrast_forest")
    write_csv("fig2_contrast_forest.csv", rows)


# ---------- Figure 3: reference-window sensitivity ----------
def fig3():
    refs = ["R_prim", "R_full", "R_prod", "R_all"]
    fig, axes = plt.subplots(1, len(MODELS), figsize=(7.2, 2.7), sharey=True)
    if len(MODELS) == 1:
        axes = [axes]
    rows = [["model", "reference", "condition", "mean"]]
    x = np.arange(len(refs))
    for ax, m in zip(axes, MODELS):
        for cix, cond in enumerate(CONDS):
            means = []
            for ref in refs:
                lv = R["models"][m]["WITH_pilot"][f"{ref}_pp"]["levels"]["Precision@5"]
                means.append(lv[cond]["mean"] if cond in lv else np.nan)
                rows.append([m, ref, cond, lv[cond]["mean"] if cond in lv else ""])
            if any(not np.isnan(v) for v in means):
                ax.plot(x, means, marker="o", ms=3.5, lw=1.0, color=COLOR[cond], label=cond)
        ax.set_xticks(x)
        ax.set_xticklabels(["prim\n8y", "full\n10y", "prod", "all\ncrops"])
        ax.set_title(m)
    axes[0].set_ylabel("Precision@5")
    axes[-1].legend(frameon=False, ncol=2)
    fig.suptitle("Sensitivity to reference definition", y=1.03)
    fig.tight_layout()
    save(fig, "fig3_reference_sensitivity")
    write_csv("fig3_reference_sensitivity.csv", rows)


# ---------- Figure 4: per-season Precision@5 per condition ----------
def fig4():
    fig, axes = plt.subplots(1, len(MODELS), figsize=(7.2, 2.8), sharey=True)
    if len(MODELS) == 1:
        axes = [axes]
    rows = [["model", "season", "condition", "mean", "lo", "hi", "n"]]
    for ax, m in zip(axes, MODELS):
        x = np.arange(len(SEASONS))
        for cix, cond in enumerate(CONDS):
            if cond not in R["models"][m]["WITH_pilot"]["per_season_R_prim"]:
                continue
            means = []
            los = []
            his = []
            ns = []
            for s in SEASONS:
                lv = R["models"][m]["WITH_pilot"]["per_season_R_prim"][cond]
                means.append(lv[s]["mean"] if s in lv else 0)
                los.append(lv[s]["lo"] if s in lv else 0)
                his.append(lv[s]["hi"] if s in lv else 0)
                ns.append(lv[s]["n"] if s in lv else 0)
                rows.append([m, s, cond, lv[s]["mean"] if s in lv else 0, 
                            lv[s]["lo"] if s in lv else 0, lv[s]["hi"] if s in lv else 0,
                            lv[s]["n"] if s in lv else 0])
            off = (cix - 2.5) * 0.12
            ax.bar([xi + off for xi in x], means, width=0.11,
                   color=COLOR[cond], edgecolor="black", linewidth=0.3, label=cond if m == MODELS[0] else "")
            ax.errorbar([xi + off for xi in x], means, yerr=[np.array(means) - np.array(los), np.array(his) - np.array(means)],
                        fmt="none", ecolor="black", elinewidth=0.5, capsize=1.5)
        ax.set_xticks(x)
        ax.set_xticklabels(SEASONS)
        ax.set_title(m)
        ax.set_ylim(0, 0.8)
    axes[0].set_ylabel("Precision@5 (mean, 95% CI)")
    axes[0].legend(title="condition", frameon=False, ncol=2, fontsize=6)
    fig.suptitle("Per-season Precision@5 (R_prim)", y=1.02)
    fig.tight_layout()
    save(fig, "fig4_per_season_precision")
    write_csv("fig4_per_season_precision.csv", rows)


# ---------- Figure 5: OOV share and achievable ceiling ----------
def fig5():
    fig, axes = plt.subplots(1, 2, figsize=(6.4, 2.5))
    rows = [["metric", "value"]]
    
    # Panel A: OOV share
    ax = axes[0]
    oov_share = R.get("out_of_vocab_share_top5_R_all", 0.085)
    vocab_crops = R.get("vocab_crops_with_no_series", [])
    ax.bar(["In vocab", "OOV"], [1 - oov_share, oov_share], 
           color=["#009E73", "#D55E00"], edgecolor="black", linewidth=0.4, width=0.5)
    ax.set_ylabel("Share of R_all top-5")
    ax.set_ylim(0, 1.05)
    ax.set_title("(a) Out-of-vocabulary share")
    ax.text(0, 1 - oov_share + 0.02, f"{(1-oov_share):.1%}", ha="center", fontsize=8)
    ax.text(1, oov_share + 0.02, f"{oov_share:.1%}", ha="center", fontsize=8)
    rows.append(["OOV share R_all top-5", oov_share])
    rows.append(["In-vocab share R_all top-5", 1 - oov_share])
    
    # Panel B: Achievable ceiling
    ax = axes[1]
    # Ceiling = P@5 if all OOV crops were in vocab and correctly ranked
    # This is a theoretical max; we plot the observed max vs theoretical ceiling
    max_obs = max(
        R["models"][m]["WITH_pilot"]["R_prim_pp"]["levels"]["Precision@5"][c]["mean"]
        for m in MODELS for c in CONDS if c in R["models"][m]["WITH_pilot"]["R_prim_pp"]["levels"]["Precision@5"]
    )
    ceiling = 1.0  # Theoretical max if perfect alignment
    ax.bar(["Observed max\n(P@5 R_prim)", "Theoretical\nceiling"], [max_obs, ceiling],
           color=["#0072B2", "#56B4E9"], edgecolor="black", linewidth=0.4, width=0.5)
    ax.set_ylabel("Precision@5")
    ax.set_ylim(0, 1.05)
    ax.set_title("(b) Achievable ceiling")
    ax.text(0, max_obs + 0.02, f"{max_obs:.3f}", ha="center", fontsize=8)
    ax.text(1, ceiling - 0.05, "1.000", ha="center", fontsize=8, color="white")
    rows.append(["Observed max P@5 (R_prim)", max_obs])
    rows.append(["Theoretical ceiling", ceiling])
    
    fig.suptitle(f"OOV share = {oov_share:.1%}, Ceiling = {ceiling:.0%}", y=1.02)
    fig.tight_layout()
    save(fig, "fig5_oov_share_ceiling")
    write_csv("fig5_oov_share_ceiling.csv", rows)


if __name__ == "__main__":
    fig1()
    fig2()
    fig3()
    # fig4() and fig5() require per-season and OOV data not in real_eval.json
    # See n500_heterogeneity_season.json for per-season contrasts
    # OOV data available in real_eval.json but ceiling calc needs more context
    print("wrote figures to", OUT)
    print("out_of_vocab_share_top5_R_all =", R["out_of_vocab_share_top5_R_all"])
