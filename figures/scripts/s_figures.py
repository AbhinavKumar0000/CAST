"""S-series figures (scoring step 5): PDF + PNG + data CSV per figure.

Every number plotted comes from `eval/results/s_scores.json` (produced by
`eval/scripts/s_score_s.py` -> `score_s.py`, district-clustered bootstrap
N_RES=10000, SEED=42). Figures render data only; no computation beyond
plotting. Primary configuration (stated in each title): pp analysis,
STRICT oracle, WITH_pilot subset; the forest additionally shows ITT.

Outputs (eval/results/figures/):
  stale_by_set, violation_by_set, shift_by_set : per-set x per-condition
      means with 95% CIs, one panel per model.
  contrasts_forest : the four registered contrasts, pooled scope,
      pp (filled) and ITT (open) markers, Holm p annotated (pp).
  false_change : P(Shift@5 > 0 | |D| = 0) per set and condition; displayed as
      "movement not explained by hard-constraint changes" (the scored metric
      is unchanged; soft-score movement is expected). Filename/false_change
      keys unchanged for provenance.
Each figure writes <name>.pdf, <name>.png, <name>.csv.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

SCORES = ROOT / "eval" / "results" / "s_scores.json"
SCORES_COND = ROOT / "eval" / "results" / "s_scores_conditional.json"
S_FOLLOWUP = ROOT / "eval" / "results" / "s_followup.json"
S_ORACLE = ROOT / "eval" / "results" / "s_oracle_signal.json"
OUT_DIR = ROOT / "figures/out"
DATA_DIR = ROOT / "figures/data/s"
OUT_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

MODELS = ["llama", "nemotron"]
CONDS = ["C0", "C0b", "C1a", "C2a", "C2b", "C3"]
TOOL_CONDS = ["C1a", "C2a", "C2b", "C3"]
CONTRASTS = ["C2a-C0b", "C2b-C0b", "C2a-C1a", "C3-C2b"]
COLORS = {"C0": "#8c8c8c", "C0b": "#4d4d4d", "C1a": "#1f77b4",
          "C2a": "#d62728", "C2b": "#ff7f0e", "C3": "#2ca02c"}
SUBSET, MODE = "WITH_pilot", "strict"
CFG = "pp, STRICT, WITH_pilot"

_scores = json.loads(SCORES.read_text(encoding="utf-8"))
_scores_cond = json.loads(SCORES_COND.read_text(encoding="utf-8"))
_followup = json.loads(S_FOLLOWUP.read_text(encoding="utf-8"))
_oracle = json.loads(S_ORACLE.read_text(encoding="utf-8"))
SETS = _scores["meta"]["run_sets"]


def lvl(model: str, scope: str, cond: str, metric: str, analysis: str = "pp") -> dict:
    k = f"{model}|{SUBSET}|{analysis}|{scope}|{MODE}|{cond}|{metric}"
    return _scores["levels"][k]


def lvl_cond(model: str, scope: str, cond: str, metric: str, analysis: str = "pp") -> dict:
    k = f"{model}|{SUBSET}|{analysis}|{scope}|{MODE}|{cond}|{metric}"
    return _scores_cond["levels"][k]


def contrast_key(model: str, pair: str, analysis: str) -> str:
    metric = "stale"
    a, b = pair.split("-")[0], pair.rsplit("-", 1)[1]
    return f"{model}|{SUBSET}|{analysis}|__pooled__|{MODE}|{metric}|{a}-{b}"


def _save(fig, name: str, rows: list[dict], fieldnames: list[str]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for ext in ("pdf", "png"):
        fig.savefig(OUT_DIR / f"{name}.{ext}", dpi=300, bbox_inches="tight")
    with (DATA_DIR / f"{name}.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    plt.close(fig)
    print(f"wrote {name}.pdf/.png/.csv ({len(rows)} rows)")


def _set_axes(ax, title: str) -> None:
    ax.set_title(title, fontsize=10)
    ax.set_ylabel("mean (95% CI)")
    ax.set_xticks(range(len(SETS)))
    ax.set_xticklabels(SETS, rotation=45, ha="right", fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    ax.axhline(0, color="black", lw=0.6)


def metric_by_set(metric: str) -> None:
    rows: list[dict] = []
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 4.6), sharey=True)
    for ax, model in zip(axes, MODELS):
        x = np.arange(len(SETS))
        offsets = np.linspace(-0.3, 0.3, len(CONDS))
        for off, cond in zip(offsets, CONDS):
            ms, los, his = [], [], []
            for s in SETS:
                st = lvl(model, s, cond, metric)
                ms.append(st["mean"])
                los.append(st["mean"] - st["lo"])
                his.append(st["hi"] - st["mean"])
                rows.append({"figure": f"{metric}_by_set", "model": model,
                             "scope": s, "condition": cond, "metric": metric,
                             "analysis": "pp", "mode": MODE, "subset": SUBSET,
                             "mean": f"{st['mean']:.6f}", "lo": f"{st['lo']:.6f}",
                             "hi": f"{st['hi']:.6f}", "p": st["p"], "n": st["n"]})
            ax.errorbar(x + off, ms, yerr=[los, his], fmt="o", ms=4, lw=1,
                        capsize=2, color=COLORS[cond], label=cond)
        _set_axes(ax, f"{model} — {metric}@5 by set ({CFG})")
        if model == "llama":
            ax.legend(fontsize=8, ncol=3, loc="upper left")
    worse = ", higher = worse" if metric in ("stale", "violation") else ""
    fig.suptitle(f"S-series simulated scenarios: {metric}@5{worse} "
                 f"(district-clustered bootstrap 10000/42)", fontsize=11)
    fig.tight_layout()
    _save(fig, f"{metric}_by_set", rows,
          ["figure", "model", "scope", "condition", "metric", "analysis",
           "mode", "subset", "mean", "lo", "hi", "p", "n"])


def contrasts_forest() -> None:
    rows: list[dict] = []
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.8), sharey=True)
    for ax, model in zip(axes, MODELS):
        ypos = np.arange(len(CONTRASTS))
        for i, pair in enumerate(CONTRASTS):
            for analysis, marker, off, face in (("pp", "o", -0.12, "C0"),
                                                ("itt", "s", 0.12, "white")):
                st = _scores["contrasts"][contrast_key(model, pair, analysis)]
                rows.append({"figure": "contrasts_forest", "model": model,
                             "contrast": pair, "analysis": analysis,
                             "metric": "stale", "subset": SUBSET, "mode": MODE,
                             "mean": f"{st['mean']:.6f}", "lo": f"{st['lo']:.6f}",
                             "hi": f"{st['hi']:.6f}", "p": st["p"],
                             "holm": st.get("holm", ""), "n": st["n"]})
                ax.errorbar(st["mean"], i + off,
                            xerr=[[st["mean"] - st["lo"]], [st["hi"] - st["mean"]]],
                            fmt=marker, color=COLORS["C2a"] if analysis == "pp" else "black",
                            markerfacecolor=face if analysis == "itt" else COLORS["C2a"],
                            ms=6, lw=1.4, capsize=3)
                if analysis == "pp":
                    ax.annotate(f"holm={st['holm']:.3g}",
                                (st["hi"], i + off), xytext=(4, -3),
                                textcoords="offset points", fontsize=7)
        ax.axvline(0, color="black", lw=0.8)
        ax.set_yticks(ypos)
        ax.set_yticklabels(CONTRASTS, fontsize=9)
        ax.set_xlabel("Δ Stale@5 (contrast, pp ● / itt □)")
        ax.grid(axis="x", alpha=0.3)
        ax.set_title(f"{model} — registered contrasts, pooled ({CFG})",
                     fontsize=10)
    fig.suptitle("S-series primary contrasts on Stale@5, higher = worse "
                 "(positive = first condition staler)", fontsize=11)
    fig.tight_layout()
    _save(fig, "contrasts_forest", rows,
          ["figure", "model", "contrast", "analysis", "metric", "subset",
           "mode", "mean", "lo", "hi", "p", "holm", "n"])


def false_change_fig() -> None:
    rows: list[dict] = []
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 4.6), sharey=True)
    for ax, model in zip(axes, MODELS):
        x = np.arange(len(SETS))
        offsets = np.linspace(-0.3, 0.3, len(CONDS))
        for off, cond in zip(offsets, CONDS):
            rates, errs = [], []
            for s in SETS:
                fc = _scores["false_change"][f"{model}|{s}|{cond}"]
                r = fc["rate"]
                rows.append({"figure": "false_change", "model": model,
                             "scope": s, "condition": cond,
                             "metric": "shift_gt0_given_no_signal",
                             "n_no_signal": fc["n_no_signal"],
                             "n_changed": fc["n_changed"],
                             "rate": "" if r is None else f"{r:.6f}"})
                rates.append(np.nan if r is None else r)
                n = fc["n_no_signal"] or 1
                errs.append(0.0 if r is None else
                            float(np.sqrt(max(r * (1 - r), 0) / n)))
            ax.errorbar(x + off, rates, yerr=errs, fmt="o", ms=4, lw=1,
                        capsize=2, color=COLORS[cond], label=cond)
        _set_axes(ax, f"{model} — movement not explained by "
                      f"hard-constraint changes ({CFG})")
        ax.set_ylabel("P(Shift@5 > 0 | |D| = 0) ± binomial SE")
        if model == "llama":
            ax.legend(fontsize=8, ncol=3, loc="upper left")
    fig.suptitle("S-series: advice movement not explained by hard-constraint "
                 "changes — soft-score movement is expected", fontsize=11)
    fig.tight_layout()
    _save(fig, "false_change", rows,
          ["figure", "model", "scope", "condition", "metric",
           "n_no_signal", "n_changed", "rate"])


# ---------- Figure F11: Stale@5 conditional (|D|>0) with n exposed ----------
def stale_conditional() -> None:
    rows: list[dict] = []
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 4.6), sharey=True)
    for ax, model in zip(axes, MODELS):
        x = np.arange(len(SETS))
        offsets = np.linspace(-0.3, 0.3, len(TOOL_CONDS))
        for off, cond in zip(offsets, TOOL_CONDS):
            ms, los, his, ns = [], [], [], []
            for s in SETS:
                st = lvl_cond(model, s, cond, "stale")
                ms.append(st["mean"])
                los.append(st["mean"] - st["lo"])
                his.append(st["hi"] - st["mean"])
                ns.append(st["n"])
                rows.append({"figure": "stale_conditional", "model": model,
                             "scope": s, "condition": cond, "metric": "stale",
                             "analysis": "pp", "mode": MODE, "subset": SUBSET,
                             "mean": f"{st['mean']:.6f}", "lo": f"{st['lo']:.6f}",
                             "hi": f"{st['hi']:.6f}", "p": st["p"], "n": st["n"],
                             "n_exposed": st["n"]})
            ax.errorbar(x + off, ms, yerr=[los, his], fmt="o", ms=4, lw=1,
                        capsize=2, color=COLORS[cond], label=cond)
            # Annotate n_exposed above bars
            for xi, m, hi, n in zip(x + off, ms, his, ns):
                if n > 0:
                    ax.text(xi, hi + 0.01, f"n={n}", ha="center", va="bottom", fontsize=6)
        _set_axes(ax, f"{model} — Stale@5 conditional on |D|>0 ({CFG})")
        ax.set_ylabel("Stale@5 (conditional mean, 95% CI)")
        if model == "llama":
            ax.legend(fontsize=8, ncol=2, loc="upper left")
    fig.suptitle("S-series: Stale@5 conditional on signal cells |D|>0 "
                 "(higher = worse, n_exposed shown)", fontsize=11)
    fig.tight_layout()
    _save(fig, "stale_conditional", rows,
          ["figure", "model", "scope", "condition", "metric", "analysis",
           "mode", "subset", "mean", "lo", "hi", "p", "n", "n_exposed"])


# ---------- Figure F12: Exposure-conditioned retention ----------
def retention_fig() -> None:
    rows: list[dict] = []
    fig, axes = plt.subplots(2, 2, figsize=(11, 6), sharex=True, sharey=True)
    analyses = ["pp", "itt"]
    for row, analysis in enumerate(analyses):
        for col, model in enumerate(MODELS):
            ax = axes[row, col]
            x = np.arange(len(CONTRASTS))
            offsets = np.linspace(-0.25, 0.25, len(CONTRASTS))  # small offset per contrast
            # We'll plot one bar per condition (C1a, C2a, C2b, C3) at pooled scope
            conditions = ["C1a", "C2a", "C2b", "C3"]
            offs = np.linspace(-0.15, 0.15, len(conditions))
            for off, cond in zip(offs, conditions):
                means, los, his, ns = [], [], [], []
                for pair in CONTRASTS:
                    key = f"retention|{model}|{cond}|{MODE}|{analysis}"
                    if key in _followup:
                        st = _followup[key]
                        means.append(st["mean"])
                        los.append(st["mean"] - st["lo"])
                        his.append(st["hi"] - st["mean"])
                        ns.append(st["n_exposed_eligible"])
                        rows.append({"figure": "retention", "model": model,
                                     "contrast": pair, "condition": cond,
                                     "analysis": analysis, "mode": MODE,
                                     "mean": f"{st['mean']:.6f}", "lo": f"{st['lo']:.6f}",
                                     "hi": f"{st['hi']:.6f}", "p": st["p"],
                                     "n_exposed": st["n_exposed_eligible"]})
                    else:
                        means.append(np.nan)
                        los.append(0)
                        his.append(0)
                        ns.append(0)
                # Plot only if we have data
                if any(not np.isnan(m) for m in means):
                    x_pos = np.arange(len(CONTRASTS)) + off
                    ax.bar(x_pos, means, width=0.12, color=COLORS[cond],
                           edgecolor="black", linewidth=0.3, label=cond)
                    ax.errorbar(x_pos, means, yerr=[los, his], fmt="none",
                                ecolor="black", capsize=2, lw=0.8)
            _set_axes(ax, f"{model} — {analysis.upper()} retention ({CFG})")
            ax.set_ylabel("Retention (|base∩D∩shift| / |base∩D|)")
            ax.set_ylim(0, 1.05)
            if row == 0 and col == 0:
                ax.legend(fontsize=7, ncol=2, loc="upper left")
    fig.suptitle("S-series: Exposure-conditioned retention by contrast "
                 "(higher = better retention of exposed crops)", fontsize=11)
    fig.tight_layout()
    _save(fig, "retention", rows,
          ["figure", "model", "contrast", "condition", "analysis", "mode",
           "mean", "lo", "hi", "p", "n_exposed"])


# ---------- Figure F13: Delta-violation ----------
def delta_violation_fig() -> None:
    rows: list[dict] = []
    fig, axes = plt.subplots(2, 2, figsize=(11, 6), sharex=True, sharey=True)
    analyses = ["pp", "itt"]
    subsets = ["signal", "all"]
    for row, analysis in enumerate(analyses):
        for col, subset in enumerate(subsets):
            ax = axes[row, col]
            x = np.arange(len(CONTRASTS))
            offsets = np.linspace(-0.2, 0.2, len(MODELS))
            for off, model in zip(offsets, MODELS):
                means, los, his = [], [], []
                for pair in CONTRASTS:
                    key = f"deltaviolation|{model}|{MODE}|{subset}|{analysis}"
                    if key in _followup:
                        st = _followup[key]
                        means.append(st["mean"])
                        los.append(st["mean"] - st["lo"])
                        his.append(st["hi"] - st["mean"])
                        rows.append({"figure": "delta_violation", "model": model,
                                     "contrast": pair, "subset": subset,
                                     "analysis": analysis, "mode": MODE,
                                     "mean": f"{st['mean']:.6f}", "lo": f"{st['lo']:.6f}",
                                     "hi": f"{st['hi']:.6f}", "p": st["p"]})
                    else:
                        means.append(np.nan)
                        los.append(0)
                        his.append(0)
                if any(not np.isnan(m) for m in means):
                    x_pos = np.arange(len(CONTRASTS)) + off
                    ax.errorbar(x_pos, means, yerr=[los, his], fmt="o", ms=5,
                                color=COLORS["C2a"] if model == "llama" else COLORS["C2b"],
                                capsize=3, lw=1.2, label=model)
            ax.axvline(0, color="black", lw=0.8)
            _set_axes(ax, f"{subset.capitalize()} cells — {analysis.upper()} Delta-Violation ({CFG})")
            ax.set_ylabel("Δ Violation@5 (shift − baseline)")
            ax.set_ylim(-0.1, 0.1)
            if row == 0 and col == 0:
                ax.legend(fontsize=8, loc="upper left")
    fig.suptitle("S-series: Delta-violation by contrast and signal subset "
                 "(negative = improvement)", fontsize=11)
    fig.tight_layout()
    _save(fig, "delta_violation", rows,
          ["figure", "model", "contrast", "subset", "analysis", "mode",
           "mean", "lo", "hi", "p"])


# ---------- Figure F15: Tool-output overlap (crop_score echo) ----------
def overlap_fig() -> None:
    rows: list[dict] = []
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 4.6), sharey=True)
    for ax, model in zip(axes, MODELS):
        x = np.arange(len(SETS))
        offsets = np.linspace(-0.3, 0.3, len(TOOL_CONDS))
        for off, cond in zip(offsets, TOOL_CONDS):
            means, los, his = [], [], []
            for s in SETS:
                key = f"{model}|{s}|{cond}"
                if key in _scores["tool_overlap"]:
                    st = _scores["tool_overlap"][key]
                    m = st["mean_overlap"]
                    n = st["n"]
                    se = np.sqrt(m * (1 - m) / n) if n > 0 else 0
                    means.append(m)
                    los.append(se)
                    his.append(se)
                    rows.append({"figure": "overlap", "model": model,
                                 "scope": s, "condition": cond,
                                 "metric": "tool_overlap", "n": n,
                                 "mean": f"{m:.6f}", "lo": f"{m-se:.6f}", "hi": f"{m+se:.6f}"})
                else:
                    means.append(np.nan)
                    los.append(0)
                    his.append(0)
            ax.errorbar(x + off, means, yerr=[los, his], fmt="o", ms=4, lw=1,
                        capsize=2, color=COLORS[cond], label=cond)
        _set_axes(ax, f"{model} — C2a top-5 overlap with stored crop_score ({CFG})")
        ax.set_ylabel("Overlap fraction (Jaccard)")
        ax.set_ylim(0, 1.05)
        if model == "llama":
            ax.legend(fontsize=8, ncol=2, loc="upper left")
    fig.suptitle("S-series: C2a advice echo of crop_score tool "
                 "(1.0 = perfect echo, 0 = no overlap)", fontsize=11)
    fig.tight_layout()
    _save(fig, "overlap", rows,
          ["figure", "model", "scope", "condition", "metric", "n", "mean", "lo", "hi"])


# ---------- Figure F16: Oracle signal per perturbation set ----------
def oracle_signal_fig() -> None:
    rows: list[dict] = []
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 4.6), sharey=True)
    for ax, model in zip(axes, MODELS):
        x = np.arange(len(SETS))
        offsets = np.linspace(-0.3, 0.3, 2)  # strict, lenient
        for off, mode in zip(offsets, ["strict", "lenient"]):
            means, los, his, ns = [], [], [], []
            for s in SETS:
                key = f"N1"
                if key in _oracle:
                    st = _oracle[key][mode]
                    n_signal = st.get("scenarios_with_signal", 0)
                    n_total = st.get("newly_infeasible_total", 40)
                    p = n_signal / n_total if n_total > 0 else 0
                    se = np.sqrt(p * (1 - p) / n_total) if n_total > 0 else 0
                    means.append(p)
                    los.append(se)
                    his.append(se)
                    ns.append(n_signal)
                    rows.append({"figure": "oracle_signal", "model": model,
                                 "scope": s, "mode": mode,
                                 "n_signal": n_signal, "n_total": n_total,
                                 "mean": f"{p:.6f}", "lo": f"{p-se:.6f}", "hi": f"{p+se:.6f}"})
            ax.errorbar(x + off, means, yerr=[los, his], fmt="o", ms=5, lw=1.5,
                        capsize=3, color="#D55E00" if mode == "strict" else "#E69F00",
                        label=mode.capitalize())
        _set_axes(ax, f"{model} — Oracle signal per perturbation set")
        ax.set_ylabel("P(|D| > 0) (fraction of cells with signal)")
        ax.set_ylim(0, 0.5)
        ax.legend(fontsize=8, loc="upper left")
    fig.suptitle("S-series: Oracle signal (fraction of cells where feasible set changes) "
                 "Strict vs Lenient oracle", fontsize=11)
    fig.tight_layout()
    _save(fig, "oracle_signal", rows,
          ["figure", "model", "scope", "mode", "n_signal", "n_total", "mean", "lo", "hi"])


def main() -> None:
    print(f"sets={SETS}")
    metric_by_set("stale")
    metric_by_set("violation")
    metric_by_set("shift")
    contrasts_forest()
    false_change_fig()
    stale_conditional()
    retention_fig()
    delta_violation_fig()
    overlap_fig()
    oracle_signal_fig()


if __name__ == "__main__":
    main()
