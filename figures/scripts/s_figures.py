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

_data = json.loads(SCORES.read_text(encoding="utf-8"))
SETS = _data["meta"]["run_sets"]


def lvl(model: str, scope: str, cond: str, metric: str, analysis: str = "pp") -> dict:
    k = f"{model}|{SUBSET}|{analysis}|{scope}|{MODE}|{cond}|{metric}"
    return _data["levels"][k]


def contrast_key(model: str, pair: str, analysis: str) -> str:
    metric = "stale"  # registered primary outcome for contrasts
    a, b = pair.split("-")[0], pair.rsplit("-", 1)[1]
    return f"{model}|{SUBSET}|{analysis}|__pooled__|{MODE}|{metric}|{a}-{b}"


def _save(fig, name: str, rows: list[dict], fieldnames: list[str]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for ext in ("pdf", "png"):
        fig.savefig(OUT_DIR / f"{name}.{ext}", dpi=150, bbox_inches="tight")
    with (OUT_DIR / f"{name}.csv").open("w", newline="", encoding="utf-8") as fh:
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
                st = _data["contrasts"][contrast_key(model, pair, analysis)]
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
                fc = _data["false_change"][f"{model}|{s}|{cond}"]
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


def main() -> None:
    print(f"sets={SETS}")
    metric_by_set("stale")
    metric_by_set("violation")
    metric_by_set("shift")
    contrasts_forest()
    false_change_fig()


if __name__ == "__main__":
    main()
