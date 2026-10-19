"""HTTP / tool-round RECONCILIATION (items 8-11, offline).

Reconciles the "7.0 HTTP/scenario" claim (which counted one HTTP per tool call) with the
measured model-request count, and reports tool-rounds per scenario for BOTH models.

Why 7.0 was wrong: the model emits all 6 tools in ONE response, so requests/scenario = the
number of LLM (tool-call) rounds + 1 final answer request, NOT 6 tools + 1.
The daily budget counter (eval/llm/budget.py::DailyBudget.reserve) increments once per HTTP
ATTEMPT, i.e. it also counts retries -> observed >= base (no-retry) requests.

No network, no API.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

SOURCES = {
    "nemotron B1": (ROOT / "eval/runs/eval_nemotron-3-ultra/results.json",
                    ["C1a", "C2a", "C2b"]),
    "nemotron B2": (ROOT / "eval/runs/eval_nemotron-3-ultra_b2/results.json",
                    ["C1a", "C2a", "C2b"]),
    "nemotron MCP C2a50": (ROOT / "eval/runs/eval_nemotron-3-ultra_mcp_c2a50/results.json",
                           ["C2a"]),
    "llama-3.2-11b": (ROOT / "eval/runs/eval_llama-3.2-11b/results.json",
                      ["C0", "C0b", "C1a", "C2a", "C2b"]),
}
OUT_TXT = ROOT / "eval/results/recon_http_rounds.txt"
OUT_JSON = ROOT / "eval/results/recon_http_rounds.json"

_records: list[str] = []
RESULTS: dict = {}


def emit(s: str = "") -> None:
    print(s)
    _records.append(s)


def tool_rounds(r) -> int:
    tl = r.get("tool_log") or []
    if not tl:
        return 0
    try:
        return max(int(e.get("round", 0)) for e in tl) + 1
    except (TypeError, ValueError):
        return 0


def main() -> None:
    emit("=" * 100)
    emit("HTTP / TOOL-ROUND RECONCILIATION")
    emit("=" * 100)
    emit("base_requests = tool_call_rounds + 1 (final answer); budget counter also counts retries.")

    all_out = {}
    grand: dict[str, Counter] = {}
    totals = {}

    for label, (path, conds) in SOURCES.items():
        if not path.exists():
            print(f"  (missing {path})")
            continue
        recs = [r for r in json.load(open(path, encoding="utf-8")) if r.get("repeat", 0) == 0]
        emit(f"\n=== {label}  ({path.name}) ===")
        emit(f"  {'cond':5s} {'n':>4s} {'mean_tools':>10s} {'rounds_hist {rounds:n}':28s} "
             f"{'mean_rounds':>11s} {'base_req/scen':>13s} {'base_HTTP_total':>15s}")
        model_base = 0
        model_n = 0
        conds_all = sorted({r["condition"] for r in recs})
        for cond in (sorted(set(conds) & set(conds_all)) or conds_all):
            sub = [r for r in recs if r["condition"] == cond]
            if not sub:
                continue
            n = len(sub)
            mt = sum(r.get("tool_calls") or 0 for r in sub) / n
            rounds = [max((e.get("round", 0) for e in (r.get("tool_log") or [])), default=-1) + 1
                      for r in sub]
            hist = dict(sorted(Counter(rounds).items()))
            mean_rounds = sum(rounds) / n
            base_per = sum(rd + 1 for rd in rounds) / n
            base_total = sum(rd + 1 for rd in rounds)
            emit(f"  {cond:5s} {n:4d} {mt:10.2f} {str(hist):28s} {mean_rounds:11.2f} "
                 f"{base_per:13.2f} {base_total:15d}")
            model_base += base_total
            model_n += n
        emit(f"  -- {label}: base (no-retry) HTTP = {model_base} over {model_n} scenario-runs "
             f"= {model_base/model_n:.3f}/scen")
        results_key = {"n": model_n, "base_http": model_base,
                       "base_http_per_scen": model_base / model_n}

        # per-condition detail (recompute for json)
        per_cond = {}
        for cond in (sorted(set(conds) & set(conds_all)) or conds_all):
            sub = [r for r in recs if r["condition"] == cond]
            if not sub:
                continue
            n = len(sub)
            rounds = [max((e.get("round", 0) for e in (r.get("tool_log") or [])), default=-1) + 1
                      for r in sub]
            per_cond[cond] = {
                "n": n,
                "mean_tools": round(sum(r.get("tool_calls") or 0 for r in sub) / n, 3),
                "rounds_hist": {str(k): v for k, v in sorted(Counter(rounds).items())},
                "mean_rounds": round(sum(rounds) / n, 3),
                "base_http_per_scen": round(sum(rd + 1 for rd in rounds) / n, 3),
                "base_http_total": sum(rd + 1 for rd in rounds),
            }
        results_key["by_condition"] = per_cond
        RESULTS[label] = results_key

    emit("\n=== RECONCILIATION of the '7.0 HTTP/scen' claim ===")
    b1 = RESULTS.get("nemotron B1", {}).get("by_condition", {}).get("C2a", {})
    if b1:
        emit(f"  B1 C2a rounds histogram = {b1['rounds_hist']}  (rounds = tool-call rounds)")
        emit(f"  B1 C2a mean tools = {b1['mean_tools']} -> if you WRONGLY count one HTTP per tool: "
             f"{b1['mean_tools']:.1f}+1 = {b1['mean_tools']+1:.1f}/scen  <-- the erroneous '7.0'")
        emit(f"  B1 C2a CORRECT base requests/scen = {b1['base_http_per_scen']} "
             f"({b1['base_http_total']} total) ; budget counter adds retries -> 2.19/scen observed.")
    mcp = RESULTS.get("nemotron MCP C2a50", {}).get("by_condition", {}).get("C2a", {})
    if mcp:
        emit(f"  MCP C2a base = {mcp['base_http_total']} for n={mcp['n']} "
             f"({mcp['base_http_per_scen']}/scen); +retries -> 123 observed (2.12 base + 0.34 retry).")

    emit("\n=== EFFICIENCY: tool-rounds/scenario by model ===")
    for label in ("nemotron B1", "nemotron B2", "llama-3.2-11b"):
        pc = RESULTS.get(label, {}).get("by_condition", {})
        for cond, d in pc.items():
            emit(f"  {label:20s} {cond:5s} mean_rounds={d['mean_rounds']:.2f} "
                 f"tools={d['mean_tools']:.2f} base_req/scen={d['base_http_per_scen']:.2f}")

    OUT_JSON.write_text(json.dumps(RESULTS, indent=2), encoding="utf-8")
    Path(OUT_TXT).write_text("\n".join(_records) + "\n", encoding="utf-8")
    emit(f"\nwrote {OUT_TXT}")
    emit(f"wrote {OUT_JSON}")


if __name__ == "__main__":
    main()
