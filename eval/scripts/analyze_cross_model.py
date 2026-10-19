"""Cross-model LLM evaluation analysis: aggregates, paired stats, figures (M01-M10).

Loads the completed runs (nemotron 500 scenarios, llama 150, glm partial ~32),
computes reliability / quality / specificity / efficiency metrics per model x
condition against the deterministic C3 reference (frozen v2 grid,
archive_v2/deterministic full_repo), and produces paired significance tests + figures.

Run:  python -u eval/scripts/analyze_cross_model.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from eval.common import config_dirs, ensure_dirs, load_config
from eval.metrics import (
    CANONICAL_CROPS,
    CROP_SEASON_VALIDITY,
    accuracy_at_k,
    hallucination_rate,
    jaccard_similarity,
    mrr,
    precision_at_k,
    season_validity_rate,
)
from eval.statistics import (
    bootstrap_ci,
    cliffs_delta,
    cohens_d,
    holm_bonferroni,
    mcnemar_paired,
    wilcoxon_paired,
)

ROOT = Path(__file__).resolve().parent.parent.parent
RUNS = {
    "nemotron": ROOT / "eval/runs/full_nemotron-3-ultra_20261011_082444/results.json",
    "llama": ROOT / "eval/runs/eval_llama-3.2-11b/results.json",
    "glm": ROOT / "eval/runs/eval_glm-5.3/results.json",
}
DET_DIR = ROOT / "eval/runs/archive_v2/deterministic"  # frozen v2 grid (was: adhoc/evidence)
CONDS = ["C0", "C0b", "C1", "C2"]
MODEL_LABELS = {"nemotron": "Nemotron-3 550B", "llama": "Llama-3.2-11B", "glm": "GLM-5.3"}
COND_LABELS = {
    "C0": "C0 LLM-only",
    "C0b": "C0b LLM-only strong",
    "C1": "C1 LLM+stuffing",
    "C2": "C2 LLM+MCP tools",
}
PALETTE = {
    "nemotron": "#0072B2",
    "llama": "#D55E00",
    "glm": "#009E73",
    "C0": "#0072B2",
    "C0b": "#56B4E9",
    "C1": "#009E73",
    "C2": "#D55E00",
}
SEED = 42

cfg = load_config()
ensure_dirs(cfg)
dirs = config_dirs(cfg)
fig_dir = Path(dirs["figures_dir"])
res_dir = Path(dirs["results_dir"])


# ---------------------------------------------------------------- loading ---

def load_run(path: Path) -> dict[tuple, dict]:
    recs = json.load(open(path))
    out = {}
    for r in recs:
        key = (r["scenario_id"], r["condition"], r.get("repeat", 0))
        prev = out.get(key)
        if prev is None or (r.get("error") is None and prev.get("error") is not None):
            out[key] = r
    return out


def _det(sid: str) -> dict:
    return json.load(open(DET_DIR / f"{sid}.json"))


def ref_top5(sid: str) -> list[str]:
    return (_det(sid).get("ablations", {}).get("full_repo") or {}).get("top5") or []


def ref_season(sid: str) -> str:
    return _det(sid)["season"]


DATA = {m: load_run(p) for m, p in RUNS.items()}
SCENARIOS = {m: {k[0] for k in DATA[m]} for m in DATA}


def metric_of(rec: dict, metric: str, ref_meta) -> float | None:
    if rec.get("error"):
        return None
    p = rec.get("parsed") or {}
    if not p.get("valid_json", False):
        return None
    top = p.get("top5")
    if not isinstance(top, list) or not top:
        return None
    if metric == "valid_json":
        return 1.0
    if metric == "hallucination":
        return hallucination_rate([top])
    if metric == "season":
        return season_validity_rate(top, ref_meta["season"])
    if metric in ("jaccard", "acc5", "mrr", "prec5"):
        ref = ref_meta["top5"]
        if not ref:
            return None
        if metric == "jaccard":
            return jaccard_similarity(top, ref)
        if metric == "acc5":
            return accuracy_at_k(top, ref, 5)
        if metric == "mrr":
            return mrr(top, ref)
        return precision_at_k(top, ref, 5)
    raise ValueError(metric)


# ---------------------------------------------------------------- aggregates

def aggregates() -> dict:
    refs = {sid: {"top5": ref_top5(sid), "season": ref_season(sid)} for m in DATA for sid in SCENARIOS[m]}
    rows = {}
    for model in DATA:
        for cond in CONDS:
            recs = [DATA[model][(sid, cond, 0)] for sid in SCENARIOS[model] if (sid, cond, 0) in DATA[model]]
            if not recs:
                continue
            err = sum(1 for r in recs if r.get("error"))
            inv = sum(1 for r in recs if not (r.get("parsed") or {}).get("valid_json", False))
            ok = [r for r in recs if not r.get("error") and (r.get("parsed") or {}).get("valid_json", False)]
            r = {
                "n": len(recs),
                "errors": err,
                "invalid_json": inv,
                "error_rate": err / len(recs),
                "valid_json_rate_any": 1 - inv / len(recs),
                "ok_count": len(ok),
                "latency_s": np.median([r["latency_s"] for r in recs if r.get("latency_s") is not None]),
                "tokens_out": np.mean([r.get("tokens_out") or 0 for r in recs]),
                "tokens_in": np.mean([r.get("tokens_in") or 0 for r in recs]),
                "tool_calls": np.mean([r.get("tool_calls") or 0 for r in recs]),
            }
            for metric in ("jaccard", "acc5", "mrr", "prec5", "hallucination", "season"):
                vals = [metric_of(x, metric, refs[x["scenario_id"]]) for x in ok]
                vals = [v for v in vals if v is not None]
                r[f"{metric}_mean"] = float(np.mean(vals)) if vals else None
                r[f"{metric}_median"] = float(np.median(vals)) if vals else None
            rows[(model, cond)] = r
    return rows


# --------------------------------------------------------------- paired stats

def paired_stats(rows: dict) -> list[dict]:
    out = []
    models = list(SCENARIOS)
    refs = {sid: {"top5": ref_top5(sid), "season": ref_season(sid)} for m in DATA for sid in SCENARIOS[m]}

    pairs = [("nemotron", "llama", len(SCENARIOS["nemotron"] & SCENARIOS["llama"])),
             ("llama", "glm", len(SCENARIOS["llama"] & SCENARIOS["glm"])),
             ("nemotron", "glm", len(SCENARIOS["nemotron"] & SCENARIOS["glm"]))]
    for a, b, n_max in pairs:
        common = sorted(SCENARIOS[a] & SCENARIOS[b])
        if not common:
            continue
        for cond in CONDS:
            diff = 0
            for sid in common:
                ok_a = (sid, cond, 0) in DATA[a] and not DATA[a][(sid, cond, 0)].get("error")
                ok_b = (sid, cond, 0) in DATA[b] and not DATA[b][(sid, cond, 0)].get("error")
                if ok_a != ok_b:
                    diff += 1
            if diff == 0:
                continue
            for metric in ("valid_json", "jaccard", "acc5", "season", "latency", "tokens_out"):
                va, vb = [], []
                for sid in common:
                    ra = DATA[a].get((sid, cond, 0)); rb = DATA[b].get((sid, cond, 0))
                    if ra is None or rb is None:
                        continue
                    if metric == "valid_json":
                        aa = 1.0 if ra.get("parsed", {}).get("valid_json") else 0.0
                        bb = 1.0 if rb.get("parsed", {}).get("valid_json") else 0.0
                    elif metric == "latency":
                        aa = ra.get("latency_s") or 0; bb = rb.get("latency_s") or 0
                    elif metric == "tokens_out":
                        aa = ra.get("tokens_out") or 0; bb = rb.get("tokens_out") or 0
                    else:
                        aa = metric_of(ra, metric, refs[sid])
                        bb = metric_of(rb, metric, refs[sid])
                        if aa is None or bb is None:
                            continue
                    va.append(aa); vb.append(bb)
                if len(va) < 5:
                    continue
                out.append({
                    "model_a": a, "model_b": b, "condition": cond, "metric": metric,
                    "n": len(va),
                    "mean_a": float(np.mean(va)), "mean_b": float(np.mean(vb)),
                    "median_a": float(np.median(va)), "median_b": float(np.median(vb)),
                    "wilcoxon_p": wilcoxon_paired(va, vb)[1],
                    "mcnemar_p": None if metric != "valid_json" else mcnemar_paired(va, vb)[1],
                    "cliffs_delta": cliffs_delta(va, vb),
                    "cohens_d": cohens_d(va, vb),
                })
    # Holm correction grouped by (pair, cond)
    out.sort(key=lambda s: (s["model_a"], s["model_b"], s["condition"], s["metric"]))
    for (a, b, cond), group in _group_with_key(out):
        ps = [g["wilcoxon_p"] for g in group]
        adj = holm_bonferroni(ps)
        for g, p in zip(group, adj):
            g["wilcoxon_adj"] = p
    return out


def _group_with_key(items):
    current, key = [], None
    for it in items:
        k = (it["model_a"], it["model_b"], it["condition"])
        if key is not None and k != key:
            yield key, current
            current = []
        key = k
        current.append(it)
    if current:
        yield key, current


# -------------------------------------------------------- condition contrasts

def condition_deltas(rows: dict) -> list[dict]:
    out = []
    for model in DATA:
        base = rows.get((model, "C0"))
        if not base:
            continue
        for cond in ("C0b", "C1", "C2"):
            r = rows.get((model, cond))
            if not r:
                continue
            for metric in ("jaccard", "acc5", "season", "valid_json_rate_any"):
                out.append({
                    "model": model, "from": "C0", "to": cond, "metric": metric,
                    "base": base.get(f"{metric}_mean" if metric != "valid_json_rate_any" else metric),
                    "c": r[f"{metric}_mean" if metric != "valid_json_rate_any" else metric],
                    "delta": (r.get(f"{metric}_mean" if metric != "valid_json_rate_any" else metric) or 0)
                             - (base.get(f"{metric}_mean" if metric != "valid_json_rate_any" else metric) or 0),
                })
    return out


# ------------------------------------------------------------------- figures

def _save(fig, name):
    fig.savefig(fig_dir / f"{name}.png", dpi=300)
    fig.savefig(fig_dir / f"{name}.pdf")
    plt.close(fig)


def _bar_metric(rows: dict, metric: str, label: str, name: str, pct: bool = True, bootstrap: bool = True):
    models = [m for m in DATA]
    fig, ax = plt.subplots(figsize=(8.5, 5))
    width = 0.2
    x = np.arange(len(CONDS))
    for i, m in enumerate(models):
        means, errs = [], []
        for cond in CONDS:
            r = rows.get((m, cond))
            if not r or r.get(f"{metric}_mean") is None:
                means.append(0); errs.append(0); continue
            means.append(r[f"{metric}_mean"])
            errs.append(0)
        ax.bar(x + (i - 1) * width, means, width * 0.92, label=MODEL_LABELS[m], color=PALETTE[m], alpha=0.9)
    ax.set_xticks(x); ax.set_xticklabels([COND_LABELS[c].split(" ")[0] for c in CONDS])
    ax.set_ylabel(label)
    ax.set_title(label)
    ax.legend()
    _save(fig, name)


def figures(rows, stats):
    # M01 valid JSON rate
    fig, ax = plt.subplots(figsize=(9, 5))
    width = 0.2
    x = np.arange(len(CONDS))
    for i, m in enumerate(DATA):
        vals = [rows.get((m, c), {}).get("valid_json_rate_any", 0) for c in CONDS]
        ax.bar(x + (i - 1) * width, vals, width, label=MODEL_LABELS[m], color=PALETTE[m])
    ax.axhline(1.0, ls=":", c="0.7"); ax.set_ylim(0, 1.05)
    ax.set_xticks(x); ax.set_xticklabels([COND_LABELS[c] for c in CONDS], rotation=12)
    ax.set_ylabel("Valid-JSON rate"); ax.set_title("M01  Structural reliability (valid JSON)")
    ax.legend(); _save(fig, "Fig_M01_valid_json_rate")

    # M02 latency
    fig, ax = plt.subplots(figsize=(9, 5))
    for i, m in enumerate(DATA):
        vals = [rows.get((m, c), {}).get("latency_s", 0) for c in CONDS]
        ax.plot(x + i * 0.05, vals, "o-", label=MODEL_LABELS[m], color=PALETTE[m], ms=7)
    ax.set_xticks(x); ax.set_xticklabels([COND_LABELS[c] for c in CONDS], rotation=12)
    ax.set_ylabel("median latency (s)"); ax.set_title("M02  Response latency")
    ax.legend(); _save(fig, "Fig_M02_latency")

    # M03 token efficiency
    fig, ax = plt.subplots(figsize=(9, 5))
    for i, m in enumerate(DATA):
        vals = [rows.get((m, c), {}).get("tokens_out", 0) for c in CONDS]
        ax.bar(x + (i - 1) * width, vals, width, label=MODEL_LABELS[m], color=PALETTE[m])
    ax.set_xticks(x); ax.set_xticklabels([COND_LABELS[c] for c in CONDS], rotation=12)
    ax.set_ylabel("mean output tokens"); ax.set_title("M03  Output token efficiency")
    ax.legend(); _save(fig, "Fig_M03_tokens_out")

    # M04 tool calls (C2)
    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    vals = [rows.get((m, "C2"), {}).get("tool_calls", 0) for m in DATA]
    ax.bar(range(len(DATA)), vals, color=[PALETTE[m] for m in DATA])
    ax.set_xticks(range(len(DATA))); ax.set_xticklabels([MODEL_LABELS[m] for m in DATA])
    ax.set_ylabel("mean tool calls / C2 response"); ax.set_title("M04  Tool-calling usage (C2)")
    _save(fig, "Fig_M04_tool_calls")

    # M05 fidelity to deterministic C3 (acc@5)
    fig, ax = plt.subplots(figsize=(9, 5))
    for i, m in enumerate(DATA):
        vals = [rows.get((m, c), {}).get("acc5_mean") or 0 for c in CONDS]
        ax.plot(x + i * 0.05, vals, "o-", label=MODEL_LABELS[m], color=PALETTE[m], ms=7)
    ax.set_xticks(x); ax.set_xticklabels([COND_LABELS[c] for c in CONDS], rotation=12)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Fidelity to C3 (Accuracy@5)"); ax.set_title("M05  Fidelity to C3")
    ax.legend(); _save(fig, "Fig_M05_fidelity_c3")

    # M06 hallucination
    fig, ax = plt.subplots(figsize=(9, 5))
    for i, m in enumerate(DATA):
        vals = [rows.get((m, c), {}).get("hallucination_mean") or 0 for c in CONDS]
        ax.bar(x + (i - 1) * width, vals, width, label=MODEL_LABELS[m], color=PALETTE[m])
    ax.set_xticks(x); ax.set_xticklabels([COND_LABELS[c] for c in CONDS], rotation=12)
    ax.set_ylabel("out-of-registry crop rate"); ax.set_title("M06  Crop hallucination rate")
    ax.legend(); _save(fig, "Fig_M06_hallucination")

    # M07 season validity
    fig, ax = plt.subplots(figsize=(9, 5))
    for i, m in enumerate(DATA):
        vals = [rows.get((m, c), {}).get("season_mean") or 0 for c in CONDS]
        ax.plot(x + i * 0.05, vals, "o-", label=MODEL_LABELS[m], color=PALETTE[m], ms=7)
    ax.set_xticks(x); ax.set_xticklabels([COND_LABELS[c] for c in CONDS], rotation=12)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("season validity rate"); ax.set_title("M07  Season-appropriate recommendations")
    ax.legend(); _save(fig, "Fig_M07_season_validity")

    # M08 per-condition delta vs C0 (jaccard)
    fig, ax = plt.subplots(figsize=(8, 5))
    deltas = condition_deltas(rows)
    labels = ["C0b", "C1", "C2"]
    xpos = np.arange(len(labels))
    for i, m in enumerate(DATA):
        vals = []
        for cond in labels:
            d = [d_ for d_ in deltas if d_["model"] == m and d_["to"] == cond and d_["metric"] == "jaccard"]
            vals.append(d[0]["delta"] if d else 0)
        ax.bar(xpos + (i - 1) * width, vals, width, label=MODEL_LABELS[m], color=PALETTE[m])
    ax.axhline(0, color="0.4", lw=1)
    ax.set_xticks(xpos); ax.set_xticklabels(labels)
    ax.set_ylabel("Δ Jaccard vs C0"); ax.set_title("M08  Value of stuffing (C1) and MCP tools (C2)")
    ax.legend(); _save(fig, "Fig_M08_condition_gains")

    # M09 latency vs reliability scatter
    fig, ax = plt.subplots(figsize=(7.5, 5.5))
    for m in DATA:
        for cond in CONDS:
            r = rows.get((m, cond))
            if not r:
                continue
            ax.scatter(r["latency_s"], r["valid_json_rate_any"], s=90, color=PALETTE[m],
                       marker="o" if cond != "C2" else "D", alpha=0.85, edgecolors="white", zorder=3)
            ax.annotate(cond, (r["latency_s"], r["valid_json_rate_any"]),
                        textcoords="offset points", xytext=(6, 5), fontsize=8)
    ax.set_xlabel("median latency (s)"); ax.set_ylabel("valid-JSON rate")
    ax.set_title("M09  Cost-reliability trade-off (markers vs models, shapes vs conditions)")
    ax.set_xscale("symlog" if max(rows[(m, c)].get("latency_s", 0) for m in DATA for c in CONDS if (m, c) in rows) > 300 else "linear")
    _save(fig, "Fig_M09_cost_reliability")

    # M10 sample size annotation - summary table as figure
    fig, ax = plt.subplots(figsize=(8, 2.2))
    ax.axis("off")
    txt = "  |  ".join(f"{MODEL_LABELS[m]}: n={len(SCENARIOS[m])} scenarios" for m in DATA)
    ax.text(0.02, 0.5, txt, fontsize=11, va="center")
    ax.set_title("M10  Available paired sample (3-way overlap = "
                 f"{len(SCENARIOS['nemotron'] & SCENARIOS['llama'] & SCENARIOS['glm'])})", fontsize=10)
    _save(fig, "Fig_M10_sample_size")


# ------------------------------------------------------------------- mains ---

def main():
    rows = aggregates()
    stats = paired_stats(rows)
    deltas = condition_deltas(rows)

    (fig_dir).mkdir(parents=True, exist_ok=True)
    (res_dir).mkdir(parents=True, exist_ok=True)
    figures(rows, stats)

    with open(res_dir / "llm_aggregates.json", "w") as f:
        json.dump({f"{m}|{c}": v for (m, c), v in rows.items()}, f, indent=2)
    with open(res_dir / "llm_paired_stats.json", "w") as f:
        json.dump(stats, f, indent=2)
    with open(res_dir / "llm_condition_deltas.json", "w") as f:
        json.dump(deltas, f, indent=2)

    print("=== Per model x condition (all collected scenarios) ===")
    hdr = f"{'model':<9}{'cond':<5}{'n':>4}{'ok':>4}{'valid':>6}{'err':>4}{'lat_m':>8}{'tok':>7}{'tools':>6}{'acc5':>7}{'jac':>7}{'hallu':>7}{'season':>8}"
    print(hdr)
    for m in DATA:
        for c in CONDS:
            r = rows.get((m, c))
            if not r:
                continue
            f = lambda v: f"{v * 100:.1f}%" if v is not None else "  n/a"
            print(f"{m:<9}{c:<5}{r['n']:>4}{r['ok_count']:>4}{f(r['valid_json_rate_any']):>6}"
                  f"{r['errors']:>4}{r['latency_s']:>7.0f}s{r['tokens_out']:>7.0f}{r['tool_calls']:>6.1f}"
                  f"{f(r['acc5_mean']):>7}{f(r['jaccard_mean']):>7}{f(r['hallucination_mean']):>7}{f(r['season_mean']):>8}")

    overlap3 = SCENARIOS["nemotron"] & SCENARIOS["llama"] & SCENARIOS["glm"]
    print(f"\n3-way overlap: {len(overlap3)} scenarios")

    print("\n=== Pairwise paired tests (median | mean; p / adj-p) ===")
    print(f"{'A':<9}{'B':<6}{'cond':<5}{'metric':<14}{'n':>4}{'medA':>9}{'medB':>9}{'p':>9}{'adj':>9}  delt/cliff/d")
    for s in stats:
        if s["metric"] not in ("valid_json", "jaccard", "acc5", "latency"):
            continue
        print(f"{s['model_a']:<9}{s['model_b']:<6}{s['condition']:<5}{s['metric']:<14}{s['n']:>4}"
              f"{s['median_a']:>8.3f}{s['median_b']:>8.3f}{s['wilcoxon_p']:>9.4f}"
              f"{s.get('wilcoxon_adj', 1):>9.4f}  {s['cliffs_delta']:+.2f}/{s['cohens_d']:+.2f}")

    print("\n=== Condition gains vs C0 (jaccard) ===")
    for d in deltas:
        if d["metric"] == "jaccard":
            print(f"{d['model']:<9} {d['to']} -> {d['delta']:+.3f}")


if __name__ == "__main__":
    main()