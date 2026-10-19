"""STEP 2/3: paper figures Fig01-Fig14 + tables T1/T2, reading ONLY master_long.csv (+C3 summary).

Style: Okabe-Ito palette (colour = condition, C3 grey), facet = model, no connecting lines for
unordered categories, C3 dashed reference lines, bootstrap CIs, Wilson CIs, Holm-corrected paired
tests. Exports PDF+PNG (300 dpi) and per-figure data CSVs in eval/figures/paper/data/.
"""

from __future__ import annotations

import json
import math
import sys
from itertools import combinations
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from eval.statistics import cliffs_delta  # noqa: E402  (may be absent)

OUT = ROOT / "eval/figures/paper"
DATA = OUT / "data"
OUT.mkdir(parents=True, exist_ok=True)
DATA.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({
    "font.size": 8, "axes.titlesize": 8, "axes.labelsize": 8, "xtick.labelsize": 7,
    "ytick.labelsize": 7, "legend.fontsize": 7, "figure.dpi": 150, "savefig.dpi": 300,
    "axes.spines.top": False, "axes.spines.right": False, "pdf.fonttype": 42,
})

MODELS = ["nemotron-3-ultra", "llama-3.2-11b", "glm-5.3"]
MODEL_LABEL = {"nemotron-3-ultra": "nemotron", "llama-3.2-11b": "llama", "glm-5.3": "glm"}
CONDS = ["C0", "C0b", "C1", "C2"]
COLOR = {"C0": "#0072B2", "C0b": "#56B4E9", "C1": "#009E73", "C2": "#D55E00", "C3": "#000000"}
GREY = "#999999"

df = pd.read_csv(ROOT / "eval/results/master_long.csv")
df["top5_list"] = df["top5"].fillna("").apply(lambda s: [x for x in s.split("|") if x])
df["c3_list"] = df["c3_top5"].fillna("").apply(lambda s: [x for x in s.split("|") if x])
df["any_overlap"] = [1.0 if (set(a) & set(b)) else 0.0 for a, b in zip(df["top5_list"], df["c3_list"])]
df["season_valid"] = pd.to_numeric(df["season_valid"], errors="coerce")
df["overlap_with_C3"] = pd.to_numeric(df["overlap_with_C3"], errors="coerce")
df["valid_json"] = pd.to_numeric(df["valid_json"], errors="coerce")
df["error_type"] = df["error_type"].fillna("").astype(str)
df["is_error"] = df["error_type"] != ""
df["prelim"] = df["model"].eq("glm-5.3")

STATS = {}


def save(fig, name, csv_rows=None, cols=None):
    for ext in ("pdf", "png"):
        fig.savefig(OUT / f"{name}.{ext}", bbox_inches="tight")
    plt.close(fig)
    if csv_rows is not None:
        pd.DataFrame(csv_rows, columns=cols).to_csv(DATA / f"{name}.csv", index=False)
    print(f"[fig] {name}")


def boot_ci(vals, n=2000, seed=0):
    vals = np.asarray([v for v in vals if v == v], float)
    if len(vals) == 0:
        return np.nan, np.nan, np.nan
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(vals), size=(n, len(vals)))
    means = vals[idx].mean(axis=1)
    return float(vals.mean()), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def wilson(k, n):
    if n == 0:
        return np.nan, np.nan, np.nan
    z = 1.96
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, max(0, c - h), min(1, c + h)


def model_n(m):
    return int(df[(df.model == m) & (df.condition == "C0")].shape[0])


def sub(model=None, cond=None, valid_only=True):
    d = df
    if model:
        d = d[d.model == model]
    if cond:
        d = d[d.condition == cond]
    if valid_only:
        d = d[d.valid_json == 1]
    return d


def cond_palette():
    return [COLOR[c] for c in CONDS], [f"{c}\n(n={int(df[(df.condition==c)&(df.model=='nemotron-3-ultra')].shape[0])})" for c in CONDS]


# ---------------------------------------------------------------- Fig01 schematic
def fig01():
    fig, ax = plt.subplots(figsize=(7, 3.2))
    ax.axis("off")
    boxes = [
        (0.02, 0.55, 0.20, 0.35, "Scenarios\n500 MP districts-dates\n(150 stress)", "#F0E442"),
        (0.27, 0.72, 0.20, 0.20, "C0 / C0b\nLLM only", COLOR["C0"]),
        (0.27, 0.48, 0.20, 0.20, "C1\nLLM + evidence\n(incl. C3 rank)", COLOR["C1"]),
        (0.27, 0.24, 0.20, 0.20, "C2\nLLM + MCP tools", COLOR["C2"]),
        (0.53, 0.48, 0.20, 0.20, "3 LLMs\nnemotron / llama / glm", "#CC79A7"),
        (0.78, 0.72, 0.20, 0.20, "Quality\noverlap, season", "#009E73"),
        (0.78, 0.48, 0.20, 0.20, "Reliability\nvalid JSON, errors", "#0072B2"),
        (0.78, 0.24, 0.20, 0.20, "Efficiency\nlatency, tokens", "#D55E00"),
        (0.53, 0.06, 0.20, 0.16, "C3 deterministic\n(no LLM)", GREY),
        (0.78, 0.06, 0.20, 0.16, "Reference\ntop-5 ranking", GREY),
    ]
    for x, y, w, h, t, c in boxes:
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.01",
                                    linewidth=1, edgecolor="black", facecolor=c, alpha=0.85))
        ax.text(x + w / 2, y + h / 2, t, ha="center", va="center", fontsize=7)
    arrows = [((0.22, 0.72), (0.27, 0.82)), ((0.22, 0.72), (0.27, 0.58)),
              ((0.22, 0.72), (0.27, 0.34)), ((0.47, 0.82), (0.53, 0.58)),
              ((0.47, 0.58), (0.53, 0.58)), ((0.47, 0.34), (0.53, 0.58)),
              ((0.73, 0.58), (0.78, 0.82)), ((0.73, 0.58), (0.78, 0.58)),
              ((0.73, 0.58), (0.78, 0.34)), ((0.63, 0.06), (0.78, 0.06)),
              ((0.63, 0.16), (0.60, 0.24))]
    for (x1, y1), (x2, y2) in arrows:
        ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=8,
                                     linewidth=0.8, color="black"))
    save(fig, "Fig01_study_design")


# ---------------------------------------------------------------- Fig02 headline
def fig02():
    metrics = [("season_valid", "Season validity"), ("overlap_with_C3", "Overlap with C3 (Jaccard)")]
    fig, axes = plt.subplots(1, 3, figsize=(7, 2.6))
    rows = []
    # (a),(b) continuous
    for ax, (col, lab) in zip(axes[:2], metrics):
        for mi, m in enumerate(MODELS):
            for ci, c in enumerate(CONDS):
                v = sub(m, c)[col].dropna().values
                mu, lo, hi = boot_ci(v)
                x = ci + (mi - 1) * 0.24
                ax.errorbar(x, mu, yerr=[[mu - lo], [hi - mu]], fmt="o", ms=4,
                            color=COLOR[c], alpha=0.4 + 0.3 * (mi == 0), capsize=2)
                rows.append(dict(panel=lab, model=m, condition=c, mean=mu, lo=lo, hi=hi, n=len(v)))
        c3v = sub("C3", "C3")[col].dropna().values
        c3m, c3lo, c3hi = boot_ci(c3v)
        ax.axhline(c3m, ls="--", lw=1, color="black")
        ax.axhspan(c3lo, c3hi, color="black", alpha=0.08)
        ax.set_xticks(range(len(CONDS)))
        ax.set_xticklabels(CONDS)
        ax.set_ylabel(lab)
        ax.set_title(f"({'ab'[metrics.index((col, lab))]}) {lab}")
        ax.text(0.02, 0.95, f"C3 = {c3m:.2f}", transform=ax.transAxes, fontsize=6, va="top")
        rows.append(dict(panel=lab, model="C3", condition="C3", mean=c3m, lo=c3lo, hi=c3hi, n=len(c3v)))
    # (c) agreement failure = 1 - P(any overlap)
    ax = axes[2]
    for mi, m in enumerate(MODELS):
        d = sub(m)
        for ci, c in enumerate(CONDS):
            dd = d[d.condition == c]
            if len(dd) == 0:
                continue
            k = int((dd.any_overlap == 0).sum())
            p, lo, hi = wilson(k, len(dd))
            x = ci + (mi - 1) * 0.24
            ax.errorbar(x, p, yerr=[[p - lo], [hi - p]], fmt="o", ms=4, color=COLOR[c],
                        alpha=0.4 + 0.3 * (mi == 0), capsize=2)
            rows.append(dict(panel="no-overlap failure", model=m, condition=c, mean=p, lo=lo, hi=hi, n=len(dd)))
    c3fail = 0.0
    ax.axhline(c3fail, ls="--", lw=1, color="black")
    ax.set_xticks(range(len(CONDS))); ax.set_xticklabels(CONDS)
    ax.set_ylabel("Failure rate: no share with C3")
    ax.set_title("(c) Disagreement with C3")
    for m in MODELS:
        ax.plot([], [], "o", color="grey", label=MODEL_LABEL[m])
    ax.legend(frameon=False, loc="upper right")
    fig.tight_layout()
    save(fig, "Fig02_headline", rows, ["panel", "model", "condition", "mean", "lo", "hi", "n"])


# ---------------------------------------------------------------- Fig03 forest
def holm(pvals):
    order = np.argsort(pvals)
    m = len(pvals)
    out = np.empty(m)
    prev = 0.0
    for rank, i in enumerate(order):
        adj = min(1.0, (m - rank) * pvals[i])
        prev = max(prev, adj)
        out[i] = prev
    return out


def fig03():
    from scipy.stats import wilcoxon
    pairs = [("C1", "C0"), ("C2", "C0"), ("C2", "C1")]
    metrics = [("overlap_with_C3", "Jaccard overlap w/ C3"), ("season_valid", "Season validity")]
    tests = []
    for m in MODELS:
        for (a, b) in pairs:
            for col, lab in metrics:
                da = sub(m, a).set_index("scenario_id")[col]
                db = sub(m, b).set_index("scenario_id")[col]
                common = da.index.intersection(db.index)
                x = da.loc[common].values.astype(float)
                y = db.loc[common].values.astype(float)
                ok = ~(np.isnan(x) | np.isnan(y))
                x, y = x[ok], y[ok]
                if len(x) < 3:
                    continue
                diff = y - x
                mu, lo, hi = boot_ci(diff)
                try:
                    p = wilcoxon(y, x).pvalue if np.any(diff != 0) else 1.0
                except Exception:
                    p = 1.0
                tests.append(dict(model=m, pair=f"{b}-{a}", metric=lab, delta=mu, lo=lo, hi=hi,
                                  p=p, n=len(x), cliffs=float(cliffs_delta(y.tolist(), x.tolist()))))
    pv = holm([t["p"] for t in tests])
    for t, pa in zip(tests, pv):
        t["p_holm"] = pa
    STATS["forest"] = tests
    json.dump(tests, open(ROOT / "eval/results/forest_stats.json", "w"), indent=2)

    fig, axes = plt.subplots(1, 2, figsize=(7, 3.4), sharey=True)
    for ax, (col, lab) in zip(axes, metrics):
        ts = [t for t in tests if t["metric"] == lab]
        ypos, ylab = [], []
        row = 0
        for m in MODELS:
            for t in ts:
                if t["model"] != m:
                    continue
                ax.errorbar(t["delta"], row, xerr=[[t["delta"] - t["lo"]], [t["hi"] - t["delta"]]],
                            fmt="o", ms=4, color=COLOR[t["pair"].split("-")[1]], capsize=2)
                star = "*" if t["p_holm"] < 0.05 else "n.s."
                ax.text(t["hi"] + 0.01, row, f"{star} (d={t['cliffs']:+.2f})", fontsize=6, va="center")
                ylab.append(f"{MODEL_LABEL[m]} {t['pair']}")
                ypos.append(row)
                row += 1
            row += 1
        ax.axvline(0, color="black", lw=1, ls="--")
        ax.set_yticks(ypos); ax.set_yticklabels(ylab, fontsize=6)
        ax.set_title(lab)
        ax.set_xlim(-0.25, 0.55)
    fig.text(0.5, 0.01, "Paired within-scenario difference (95% bootstrap CI); Holm-corrected; Cliff's δ",
             ha="center", fontsize=6)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    save(fig, "Fig03_forest_paired_diffs",
         [{k: v for k, v in t.items()} for t in tests],
         ["model", "pair", "metric", "delta", "lo", "hi", "p", "n", "cliffs", "p_holm"])


# ---------------------------------------------------------------- Fig04 violin
def fig04():
    fig, axes = plt.subplots(1, 3, figsize=(7, 2.6), sharey=True)
    rows = []
    for ax, m in zip(axes, MODELS):
        data = [sub(m, c)["overlap_with_C3"].dropna().values for c in CONDS]
        parts = ax.violinplot(data, showextrema=False, widths=0.8)
        for pc, c in zip(parts["bodies"], CONDS):
            pc.set_facecolor(COLOR[c]); pc.set_alpha(0.5)
        bp = ax.boxplot(data, widths=0.15, showfliers=False, patch_artist=True)
        for patch, c in zip(bp["boxes"], CONDS):
            patch.set_facecolor(COLOR[c])
        for i, (vals, c) in enumerate(zip(data, CONDS), start=1):
            if len(vals):
                ax.scatter(np.random.default_rng(0).normal(i, 0.04, len(vals)), vals, s=2,
                           color=COLOR[c], alpha=0.4)
                mu, lo, hi = boot_ci(vals)
                rows.append(dict(model=m, condition=c, mean=mu, lo=lo, hi=hi, n=len(vals)))
        ax.set_xticks(range(1, len(CONDS) + 1)); ax.set_xticklabels(CONDS)
        ax.set_title(f"{MODEL_LABEL[m]} (n={model_n(m)})")
        ax.axhline(sub("C3", "C3")["overlap_with_C3"].mean(), ls="--", color="black", lw=1)
    axes[0].set_ylabel("Jaccard overlap with C3")
    fig.tight_layout()
    save(fig, "Fig04_per_scenario_overlap", rows, ["model", "condition", "mean", "lo", "hi", "n"])


# ---------------------------------------------------------------- Fig05 season x condition
def fig05():
    seasons = ["Kharif", "Rabi", "Zaid"]
    fig, axes = plt.subplots(1, 3, figsize=(7, 2.6), sharey=True)
    rows = []
    for ax, m in zip(axes, MODELS):
        for ci, c in enumerate(CONDS):
            for si, s in enumerate(seasons):
                v = df[(df.model == m) & (df.condition == c) & (df.season == s) & (df.valid_json == 1)]["season_valid"].dropna().values
                mu, lo, hi = boot_ci(v) if len(v) else (np.nan,) * 3
                x = si + (ci - 1.5) * 0.18
                ax.errorbar(x, mu, yerr=[[mu - lo], [hi - mu]] if len(v) else None, fmt="o",
                            ms=4, color=COLOR[c], capsize=2)
                rows.append(dict(model=m, condition=c, season=s, mean=mu, lo=lo, hi=hi, n=len(v)))
        c3 = df[(df.model == "C3") & (df.season.isin(seasons))].groupby("season")["season_valid"].mean()
        for si, s in enumerate(seasons):
            ax.hlines(c3.get(s, np.nan), si - 0.35, si + 0.35, color="black", ls="--", lw=1)
        ax.set_xticks(range(len(seasons))); ax.set_xticklabels(seasons)
        ax.set_title(f"{MODEL_LABEL[m]} (n={model_n(m)})")
    axes[0].set_ylabel("Season validity")
    for c in CONDS:
        axes[0].plot([], [], "o", color=COLOR[c], label=c)
    axes[0].legend(frameon=False, ncol=2, loc="lower left")
    fig.tight_layout()
    save(fig, "Fig05_season_validity_by_season", rows, ["model", "condition", "season", "mean", "lo", "hi", "n"])


# ---------------------------------------------------------------- Fig06 C2 outcomes
def fig06():
    cats = ["valid, season-correct", "valid, wrong season", "invalid JSON", "tool error", "other error"]
    fig, ax = plt.subplots(figsize=(3.5, 2.8))
    rows = []
    bottom = np.zeros(len(MODELS))
    for m_i, m in enumerate(MODELS):
        d = df[(df.model == m) & (df.condition == "C2")]
        n = len(d)
        counts = {
            "valid, season-correct": int(((d.valid_json == 1) & (d.season_valid == 1)).sum()),
            "valid, wrong season": int(((d.valid_json == 1) & (d.season_valid < 1)).sum()),
            "invalid JSON": int(((d.error_type == "") & (d.valid_json == 0)).sum()),
            "tool error": int((d.error_type == "max_tool_rounds").sum()),
            "other error": int((d.error_type.isin(["gateway_timeout", "dns", "connection_reset", "other"]) & (d.error_type != "max_tool_rounds")).sum()),
        }
        for cat in cats:
            rows.append(dict(model=m, category=cat, count=counts[cat], n=n))
    catcolors = {"valid, season-correct": "#009E73", "valid, wrong season": "#F0E442",
                 "invalid JSON": "#D55E00", "tool error": "#CC79A7", "other error": "#999999"}
    for m_i, m in enumerate(MODELS):
        d = df[(df.model == m) & (df.condition == "C2")]
        n = len(d)
        b = 0
        for cat in cats:
            k = int(((d.valid_json == 1) & (d.season_valid == 1)).sum()) if cat == "valid, season-correct" else (
                int(((d.valid_json == 1) & (d.season_valid < 1)).sum()) if cat == "valid, wrong season" else (
                int(((d.error_type == "") & (d.valid_json == 0)).sum()) if cat == "invalid JSON" else (
                int((d.error_type == "max_tool_rounds").sum()) if cat == "tool error" else
                int((d.error_type.isin(["gateway_timeout", "dns", "connection_reset", "other"]) & (d.error_type != "max_tool_rounds")).sum()))))
            frac = k / n if n else 0
            if frac > 0:
                ax.bar(m_i, frac, bottom=b, color=catcolors[cat], edgecolor="white", linewidth=0.5)
                ax.text(m_i, b + frac / 2, str(k), ha="center", va="center", fontsize=6)
            b += frac
    ax.set_xticks(range(len(MODELS))); ax.set_xticklabels([f"{MODEL_LABEL[m]}\n(n={model_n(m)})" for m in MODELS])
    ax.set_ylabel("Fraction of C2 scenarios")
    ax.set_title("C2 outcome breakdown")
    ax.legend(handles=[plt.Rectangle((0, 0), 1, 1, color=catcolors[c]) for c in cats], labels=cats,
              frameon=False, fontsize=5, loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=2)
    fig.tight_layout()
    save(fig, "Fig06_C2_outcome_breakdown", rows, ["model", "category", "count", "n"])


# ---------------------------------------------------------------- Fig07 reliability
def fig07():
    fig, axes = plt.subplots(1, 2, figsize=(7, 2.8))
    rows = []
    for ax, (mask_name, title) in zip(axes, [("invalid_json", "Invalid-JSON failure rate"),
                                             ("any_error", "API / tool failure rate")]):
        for mi, m in enumerate(MODELS):
            for ci, c in enumerate(CONDS):
                d = df[(df.model == m) & (df.condition == c)]
                if not len(d):
                    continue
                if mask_name == "invalid_json":
                    k = int(((d.error_type == "") & (d.valid_json == 0)).sum())
                else:
                    k = int(d.is_error.sum())
                p, lo, hi = wilson(k, len(d))
                x = ci + (mi - 1) * 0.24
                ax.errorbar(x, p, yerr=[[p - lo], [hi - p]], fmt="o", ms=4, color=COLOR[c],
                            alpha=0.4 + 0.3 * (mi == 0), capsize=2)
                rows.append(dict(metric=title, model=m, condition=c, rate=p, lo=lo, hi=hi, n=len(d)))
        ax.set_xticks(range(len(CONDS))); ax.set_xticklabels(CONDS)
        ax.set_ylabel("Failure rate")
        ax.set_title(title)
        ax.set_ylim(-0.01, max(0.15, ax.get_ylim()[1]))
    for m in MODELS:
        axes[0].plot([], [], "o", color="grey", label=MODEL_LABEL[m])
    axes[0].legend(frameon=False, loc="upper right")
    fig.tight_layout()
    save(fig, "Fig07_reliability", rows, ["metric", "model", "condition", "rate", "lo", "hi", "n"])


# ---------------------------------------------------------------- Fig08 efficiency
def fig08():
    fig, axes = plt.subplots(1, 3, figsize=(7, 2.8))
    rows = []
    ax = axes[0]
    for mi, m in enumerate(MODELS):
        data, pos = [], []
        for ci, c in enumerate(CONDS):
            v = df[(df.model == m) & (df.condition == c) & (~df.is_error)]["latency_scenario_s"].dropna().values
            v = v[v > 0]
            data.append(v); pos.append(ci + (mi - 1) * 0.24)
            if len(v):
                rows.append(dict(panel="latency", model=m, condition=c, median=float(np.median(v)), n=len(v)))
        bp = ax.boxplot(data, positions=pos, widths=0.2, showfliers=False, patch_artist=True)
        for patch, c in zip(bp["boxes"], CONDS):
            patch.set_facecolor(COLOR[c]); patch.set_alpha(0.4 + 0.3 * (mi == 0))
    ax.set_yscale("log"); ax.set_xticks(range(len(CONDS))); ax.set_xticklabels(CONDS)
    ax.set_ylabel("Latency (s, log scale)"); ax.set_title("(a) Per-scenario latency")
    ax = axes[1]
    for mi, m in enumerate(MODELS):
        for ci, c in enumerate(CONDS):
            v = df[(df.model == m) & (df.condition == c) & (df.valid_json == 1)]["tokens_out"].dropna().values
            if len(v) == 0:
                continue
            mu, lo, hi = boot_ci(v)
            ax.bar(ci + (mi - 1) * 0.24, mu, width=0.2, color=COLOR[c], alpha=0.4 + 0.3 * (mi == 0))
            rows.append(dict(panel="tokens_out", model=m, condition=c, mean=mu, lo=lo, hi=hi, n=len(v)))
    ax.set_xticks(range(len(CONDS))); ax.set_xticklabels(CONDS)
    ax.set_ylabel("Output tokens"); ax.set_title("(b) Output tokens")
    ax = axes[2]
    for mi, m in enumerate(MODELS):
        for ci, c in enumerate(CONDS):
            v = pd.to_numeric(df[(df.model == m) & (df.condition == c)]["tool_calls"], errors="coerce").dropna().values
            if len(v) == 0:
                continue
            mu, lo, hi = boot_ci(v)
            ax.bar(ci + (mi - 1) * 0.24, mu, width=0.2, color=COLOR[c], alpha=0.4 + 0.3 * (mi == 0))
            rows.append(dict(panel="tool_calls", model=m, condition=c, mean=mu, lo=lo, hi=hi, n=len(v)))
    ax.set_xticks(range(len(CONDS))); ax.set_xticklabels(CONDS)
    ax.set_ylabel("Tool calls per scenario"); ax.set_title("(c) Tool calls")
    fig.tight_layout()
    save(fig, "Fig08_efficiency", rows, ["panel", "model", "condition", "median", "mean", "lo", "hi", "n"])


# ---------------------------------------------------------------- Fig09 cost-quality
def fig09():
    fig, ax = plt.subplots(figsize=(3.7, 3.0))
    rows = []
    pts = []
    for m in MODELS:
        for c in CONDS:
            d = df[(df.model == m) & (df.condition == c) & (~df.is_error) & (df.valid_json == 1)]
            if not len(d):
                continue
            lat = d["latency_scenario_s"].dropna()
            lat = lat[lat > 0]
            qual = d["overlap_with_C3"].mean()
            if not len(lat):
                continue
            x = float(np.median(lat))
            marker = {"nemotron-3-ultra": "o", "llama-3.2-11b": "s", "glm-5.3": "^"}[m]
            ax.scatter(x, qual, marker=marker, s=45, color=COLOR[c], edgecolor="black", linewidth=0.4)
            rows.append(dict(model=m, condition=c, median_latency=x, mean_overlap=qual, n=len(d)))
            pts.append((x, qual, m, c))
    # Pareto frontier (higher quality, lower latency)
    pts_sorted = sorted(pts, key=lambda t: t[0])
    best_q = -1
    pareto = []
    for x, q, m, c in pts_sorted:
        if q > best_q:
            pareto.append((x, q)); best_q = q
    if pareto:
        ax.plot(*zip(*pareto), ls=":", color="black", lw=1, label="Pareto frontier")
    ax.set_xscale("log")
    ax.set_xlabel("Median latency per scenario (s, log)")
    ax.set_ylabel("Mean Jaccard overlap with C3")
    for m, mk in [("nemotron-3-ultra", "o"), ("llama-3.2-11b", "s"), ("glm-5.3", "^")]:
        ax.scatter([], [], marker=mk, color="grey", label=MODEL_LABEL[m])
    for c in CONDS:
        ax.scatter([], [], marker="o", color=COLOR[c], label=c)
    ax.legend(frameon=False, fontsize=6, ncol=2)
    fig.tight_layout()
    save(fig, "Fig09_cost_quality", rows, ["model", "condition", "median_latency", "mean_overlap", "n"])


# ---------------------------------------------------------------- Fig10 tool use
def fig10():
    fig, axes = plt.subplots(1, 2, figsize=(7, 2.8))
    rows = []
    ax = axes[0]
    tc = pd.to_numeric(df[df.condition == "C2"]["tool_calls"], errors="coerce")
    maxc = int(tc.max()) if len(tc) else 6
    for mi, m in enumerate(MODELS):
        d = pd.to_numeric(df[(df.model == m) & (df.condition == "C2")]["tool_calls"], errors="coerce").dropna()
        if not len(d):
            continue
        b = np.bincount(d.astype(int).values, minlength=maxc + 1)
        frac = b / b.sum()
        ax.bar(np.arange(len(frac)) + (mi - 1) * 0.25, frac, width=0.25,
               color=["#0072B2", "#D55E00", "#009E73"][mi], label=MODEL_LABEL[m])
        for j, f in enumerate(frac):
            rows.append(dict(panel="count_dist", model=m, tool_calls=j, frac=float(f), n=int(b.sum())))
    ax.set_xlabel("Number of tool calls (C2)"); ax.set_ylabel("Fraction of scenarios")
    ax.set_title("(a) Tool-call count distribution")
    ax.legend(frameon=False)
    # (b) overlap by tool-call count
    ax = axes[1]
    for m in MODELS:
        d = df[(df.model == m) & (df.condition == "C2") & (df.valid_json == 1)].copy()
        d["tc"] = pd.to_numeric(d["tool_calls"], errors="coerce")
        d = d.dropna(subset=["tc"])
        for tcc in sorted(d.tc.unique()):
            v = d[d.tc == tcc]["overlap_with_C3"].values
            mu, lo, hi = boot_ci(v) if len(v) else (np.nan,) * 3
            ax.errorbar(tcc + (MODELS.index(m) - 1) * 0.08, mu,
                        yerr=[[mu - lo], [hi - mu]] if len(v) else None, fmt="o",
                        ms=4, color=["#0072B2", "#D55E00", "#009E73"][MODELS.index(m)], capsize=2)
            rows.append(dict(panel="quality_by_calls", model=m, tool_calls=int(tcc), mean=mu, lo=lo, hi=hi, n=len(v)))
    ax.set_xlabel("Number of tool calls"); ax.set_ylabel("Mean Jaccard overlap with C3")
    ax.set_title("(b) Quality vs tool-call count")
    ax.axhline(sub("C3", "C3")["overlap_with_C3"].mean(), ls="--", color="black", lw=1)
    fig.tight_layout()
    save(fig, "Fig10_tool_use", rows, ["panel", "model", "tool_calls", "frac", "mean", "lo", "hi", "n"])


# ---------------------------------------------------------------- Fig11 crop frequency
def fig11():
    models_present = MODELS + ["C3"]
    from collections import Counter
    counts = {}
    ent = {}
    for m in models_present:
        c = Counter()
        for lst in df[df.model == m]["top5_list"]:
            c.update(lst)
        counts[m] = c
        tot = sum(c.values())
        ent[m] = -sum((v / tot) * math.log2(v / tot) for v in c.values()) if tot else 0
    allc = Counter()
    for m in models_present:
        allc.update(counts[m])
    top = [c for c, _ in allc.most_common(15)]
    mat = np.array([[counts[m].get(c, 0) / max(1, sum(counts[m].values())) for m in models_present] for c in top])
    fig, ax = plt.subplots(figsize=(3.8, 4.2))
    im = ax.imshow(mat, aspect="auto", cmap="viridis")
    ax.set_xticks(range(len(models_present)))
    ax.set_xticklabels([MODEL_LABEL.get(m, m) for m in models_present], rotation=30, ha="right")
    ax.set_yticks(range(len(top))); ax.set_yticklabels(top, fontsize=6)
    for i in range(len(top)):
        for j in range(len(models_present)):
            ax.text(j, i, f"{mat[i, j]*100:.0f}", ha="center", va="center", fontsize=5,
                    color="white" if mat[i, j] > mat.max() * 0.6 else "black")
    cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cb.set_label("Share of top-5 slots (%)", fontsize=6)
    ax.set_title("Crop frequency (top 15)")
    for j, m in enumerate(models_present):
        ax.text(j, -1.2, f"H={ent[m]:.2f}", ha="center", fontsize=5)
    rows = [dict(crop=c, model=m, share=mat[i][j]) for i, c in enumerate(top) for j, m in enumerate(models_present)]
    fig.tight_layout()
    save(fig, "Fig11_crop_frequency", rows, ["crop", "model", "share"])
    STATS["entropy"] = ent


# ---------------------------------------------------------------- Fig12 stress vs normal
def fig12():
    fig, axes = plt.subplots(1, 2, figsize=(7, 2.8))
    rows = []
    for ax, col, lab in zip(axes, ["overlap_with_C3", "season_valid"],
                            ["Jaccard overlap w/ C3", "Season validity"]):
        for ci, c in enumerate(CONDS):
            for si, s in enumerate([0, 1]):
                vals = []
                for m in MODELS:
                    v = df[(df.model == m) & (df.condition == c) & (df.stress == s) & (df.valid_json == 1)][col].dropna().values
                    if len(v):
                        mu, lo, hi = boot_ci(v)
                        vals.append(mu)
                        rows.append(dict(metric=lab, condition=c, stress=s, model=m, mean=mu, lo=lo, hi=hi, n=len(v)))
                if vals:
                    x = ci + (si - 0.5) * 0.28
                    ax.bar(x, np.mean(vals), width=0.24, color=COLOR[c],
                           alpha=0.9 if s == 1 else 0.45, edgecolor="black", linewidth=0.4)
        ax.set_xticks(range(len(CONDS))); ax.set_xticklabels(CONDS)
        ax.set_ylabel(lab); ax.set_title(lab)
    axes[0].bar([], [], color="grey", alpha=0.9, label="stress")
    axes[0].bar([], [], color="grey", alpha=0.45, label="normal")
    axes[0].legend(frameon=False)
    fig.tight_layout()
    save(fig, "Fig12_stress_vs_normal", rows, ["metric", "condition", "stress", "model", "mean", "lo", "hi", "n"])


# ---------------------------------------------------------------- Fig13 cross-model jaccard
def fig13():
    from eval.metrics import jaccard_similarity
    fig, axes = plt.subplots(1, 4, figsize=(7, 2.3))
    rows = []
    for ax, c in zip(axes, CONDS):
        M = np.eye(3)
        Ns = np.full((3, 3), np.nan)
        for i, j in combinations(range(3), 2):
            a, b = MODELS[i], MODELS[j]
            da = df[(df.model == a) & (df.condition == c) & (df.valid_json == 1)].set_index("scenario_id")["top5_list"]
            db = df[(df.model == b) & (df.condition == c) & (df.valid_json == 1)].set_index("scenario_id")["top5_list"]
            common = da.index.intersection(db.index)
            sims = [jaccard_similarity(list(da.loc[s]), list(db.loc[s])) for s in common]
            val = float(np.mean(sims)) if sims else np.nan
            M[i, j] = M[j, i] = val
            Ns[i, j] = Ns[j, i] = len(common)
            rows.append(dict(condition=c, model_a=a, model_b=b, mean_jaccard=val, n=len(common)))
        im = ax.imshow(M, vmin=0, vmax=1, cmap="magma")
        for i in range(3):
            for j in range(3):
                if i == j:
                    ax.text(j, i, "1", ha="center", va="center", color="white", fontsize=6)
                else:
                    ax.text(j, i, f"{M[i,j]:.2f}\nn={int(Ns[i,j])}", ha="center", va="center",
                            color="white" if M[i, j] > 0.5 else "black", fontsize=5)
        ax.set_xticks(range(3)); ax.set_xticklabels([MODEL_LABEL[m] for m in MODELS], fontsize=6, rotation=30, ha="right")
        ax.set_yticks(range(3)); ax.set_yticklabels([MODEL_LABEL[m] for m in MODELS], fontsize=6)
        ax.set_title(c, fontsize=7)
    fig.suptitle("Cross-model top-5 agreement (Jaccard, nested pairs)", fontsize=8)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    save(fig, "Fig13_cross_model_jaccard", rows, ["condition", "model_a", "model_b", "mean_jaccard", "n"])


# ---------------------------------------------------------------- Fig14 deterministic
def fig14():
    d = json.load(open(ROOT / "eval/results/c3_deterministic_summary.json"))
    fig, axes = plt.subplots(1, 3, figsize=(7, 2.6))
    rows = []
    ax = axes[0]
    names = ["Normal", "Stress", "Overall"]
    vals = [d["c3_season_validity_normal"], d["c3_season_validity_stress"], d["c3_season_validity_overall"]]
    ns = [d["n_normal"], d["n_stress"], d["n_scenarios"]]
    ax.bar(names, vals, color=["#009E73", "#D55E00", GREY])
    for i, (v, n) in enumerate(zip(vals, ns)):
        ax.text(i, v + 0.01, f"{v:.2f}\nn={n}", ha="center", fontsize=6)
    ax.set_ylabel("Season validity"); ax.set_title("(a) C3 by stress")
    ax = axes[1]
    seasons = list(d["per_season"].keys())
    v2 = [d["per_season"][s]["validity"] for s in seasons]
    n2 = [d["per_season"][s]["n"] for s in seasons]
    ax.bar(seasons, v2, color=["#0072B2", "#CC79A7", "#D55E00"])
    for i, (v, n) in enumerate(zip(v2, n2)):
        ax.text(i, v + 0.01, f"{v:.2f}\nn={n}", ha="center", fontsize=6)
    ax.set_ylabel("Season validity"); ax.set_title("(b) C3 by season")
    ax = axes[2]
    metrics = ["Distinct crops", "Shannon entropy", "District differentiation"]
    mvals = [d["c3_distinct_crops"], d["c3_shannon_entropy"], d["c3_per_district_differentiation"]]
    ax.bar(metrics, mvals, color=["#F0E442", "#56B4E9", "#009E73"])
    for i, v in enumerate(mvals):
        ax.text(i, v + 0.02, f"{v:.2f}", ha="center", fontsize=6)
    ax.set_title("(c) C3 specificity")
    ax.tick_params(axis="x", rotation=20, labelsize=6)
    fig.tight_layout()
    for k, v in zip([f"validity_{x}" for x in names] + [f"validity_{s}" for s in seasons] +
                    ["distinct_crops", "shannon_entropy", "district_differentiation"],
                    vals + v2 + mvals):
        rows.append(dict(metric=k, value=v))
    save(fig, "Fig14_deterministic_summary", rows, ["metric", "value"])
    STATS["deterministic"] = d


# ---------------------------------------------------------------- Tables
def tables():
    rows = []
    for m in MODELS + ["C3"]:
        for c in (CONDS + ["C3"]):
            d = df[(df.model == m) & (df.condition == c)]
            if not len(d):
                continue
            dv = d[d.valid_json == 1]
            n = len(d)
            def ci(col, binary=False):
                if binary:
                    k = int(dv[col].sum())
                    p, lo, hi = wilson(k, len(dv)) if len(dv) else (np.nan,) * 3
                    return p, lo, hi
                return boot_ci(dv[col].dropna().values) if len(dv) else (np.nan,) * 3
            j = ci("overlap_with_C3"); s = ci("season_valid"); a = ci("any_overlap", binary=True)
            vj = wilson(int(d.valid_json.sum()), n)
            rows.append(dict(model=m, condition=c, n=n, n_valid=int(d.valid_json.sum()),
                             overlap=j[0], overlap_lo=j[1], overlap_hi=j[2],
                             season=s[0], season_lo=s[1], season_hi=s[2],
                             anyoverlap=a[0], anyoverlap_lo=a[1], anyoverlap_hi=a[2],
                             valid_json=vj[0], valid_json_lo=vj[1], valid_json_hi=vj[2],
                             preliminary=int(m == "glm-5.3")))
    t1 = pd.DataFrame(rows)
    t1.to_csv(OUT / "T1_metrics.csv", index=False)
    # LaTeX + MD
    with open(OUT / "T1_metrics.tex", "w") as f:
        def fmt(r, v, lo, hi):
            return f"{r[v]:.3f} [{r[v+'_lo']:.3f}, {r[v+'_hi']:.3f}]"
        f.write("\\begin{tabular}{llrl}\n\\toprule\nModel & Cond & n & Jaccard w/ C3 [95\\% CI] \\\\\n\\midrule\n")
        for r in rows:
            f.write(f"{r['model']} & {r['condition']} & {r['n']} & {fmt(r,'overlap','overlap_lo','overlap_hi')} \\\\\n")
        f.write("\\bottomrule\n\\end{tabular}\n")
    with open(OUT / "T1_metrics.md", "w") as f:
        f.write("| model | cond | n | Jaccard w/ C3 [95% CI] | Season validity [95% CI] | valid JSON |\n")
        f.write("|---|---|---|---|---|---|\n")
        for r in rows:
            f.write(f"| {r['model']} | {r['condition']} | {r['n']} | "
                    f"{r['overlap']:.3f} [{r['overlap_lo']:.3f},{r['overlap_hi']:.3f}] | "
                    f"{r['season']:.3f} [{r['season_lo']:.3f},{r['season_hi']:.3f}] | "
                    f"{r['valid_json']:.3f} |\n")
    # T2 coverage
    cov = []
    for m in MODELS + ["C3"]:
        for c in (CONDS + ["C3"]):
            d = df[(df.model == m) & (df.condition == c)]
            if not len(d):
                continue
            cov.append(dict(model=m, condition=c, n_scenarios=len(d), n_valid=int(d.valid_json.sum()),
                            n_error=int(d.is_error.sum()), n_error_tool_rounds=int((d.error_type == "max_tool_rounds").sum()),
                            preliminary=int(m == "glm-5.3")))
    pd.DataFrame(cov).to_csv(OUT / "T2_coverage.csv", index=False)
    with open(OUT / "T2_coverage.md", "w") as f:
        f.write("| model | condition | scenarios | valid | errors | tool-round errors | preliminary |\n")
        f.write("|---|---|---|---|---|---|---|\n")
        for r in cov:
            f.write(f"| {r['model']} | {r['condition']} | {r['n_scenarios']} | {r['n_valid']} | "
                    f"{r['n_error']} | {r['n_error_tool_rounds']} | {r['preliminary']} |\n")
    print("[tables] T1_metrics.{csv,tex,md}, T2_coverage.{csv,md}")


def main():
    fig01(); fig02(); fig03(); fig04(); fig05(); fig06(); fig07()
    fig08(); fig09(); fig10(); fig11(); fig12(); fig13(); fig14()
    tables()
    json.dump(STATS, open(ROOT / "eval/results/figure_stats.json", "w"), indent=2, default=str)
    print("[done] figures in", OUT)


if __name__ == "__main__":
    main()