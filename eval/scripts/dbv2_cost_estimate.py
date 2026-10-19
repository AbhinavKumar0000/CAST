"""STEP 7: cost/volume estimate to re-run ONLY the LLM conditions on db_v2.

No API calls are made here. We project from the token/request volumes actually
recorded in the saved db_v1 runs. Dollar cost is NOT estimated because these
NVIDIA-hosted models have no public per-token price we can cite; we report the
token + request volumes so cost can be applied with the user's price sheet.

Outputs eval/results/db_v2_cost_estimate.{txt,json}.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "eval/runs"
NEMO = [RUNS / "eval_nemotron-3-ultra/results.json", RUNS / "eval_nemotron-3-ultra_b2/results.json"]
NEMO_CACHE = ROOT / "eval/cache/llm/nemotron-3-ultra"
LLAMA = [RUNS / "eval_llama-3.2-11b/results.json"]
# Conditions that would be re-run on db_v2 (C3 is deterministic, not an LLM call).
CONDS = ["C0", "C0b", "C1a", "C2a", "C2b"]


def load_records(files, cache_dir=None):
    seen = set()
    for f in files:
        for r in json.load(f.open(encoding="utf-8")):
            if r.get("repeat", 0) != 0 or r.get("condition") not in CONDS:
                continue
            key = (r.get("condition"), r.get("scenario_id"))
            if key in seen:
                continue
            seen.add(key)
            yield r
    if cache_dir and cache_dir.exists():
        for fp in cache_dir.glob("*.json"):
            try:
                r = json.load(fp.open(encoding="utf-8"))
            except Exception:
                continue
            if r.get("repeat", 0) != 0 or r.get("condition") not in CONDS:
                continue
            key = (r.get("condition"), r.get("scenario_id"))
            if key in seen:
                continue
            seen.add(key)
            yield r


def stats(files, cache_dir=None):
    per = defaultdict(lambda: {"n": 0, "in": 0, "out": 0, "reason": 0, "tool": 0, "err": 0})
    for r in load_records(files, cache_dir):
        d = per[r["condition"]]
        d["n"] += 1
        d["in"] += int(r.get("tokens_in") or 0)
        d["out"] += int(r.get("tokens_out") or 0)
        d["reason"] += int(r.get("reasoning_tokens") or 0)
        d["tool"] += int(r.get("tool_calls") or 0)
        if r.get("error"):
            d["err"] += 1
    return per


def summarize(name, per):
    lines = [f"===== {name} ====="]
    tot_in = tot_out = tot_req = tot_tool = tot_n = 0
    rows = {}
    for cond in CONDS:
        d = per[cond]
        if not d["n"]:
            continue
        req = d["n"] + d["tool"]  # one request per scenario + one per tool round
        rows[cond] = {
            "scenarios": d["n"],
            "mean_input_tokens_per_req": d["in"] / req,
            "mean_output_tokens_per_req": (d["out"] + d["reason"]) / req,
            "total_input_tokens": d["in"],
            "total_output_tokens": d["out"] + d["reason"],
            "total_requests": req,
            "errors": d["err"],
        }
        lines.append(
            f"  {cond:4s} n={d['n']:3d}  req={req:5d}  "
            f"in={d['in']:>9d} out(+reason)={d['out']+d['reason']:>7d}  "
            f"tool_rounds={d['tool']:4d} err={d['err']}"
        )
        tot_in += d["in"]; tot_out += d["out"] + d["reason"]; tot_req += req; tot_tool += d["tool"]; tot_n += d["n"]
    lines.append(
        f"  TOTAL n={tot_n} requests={tot_req} input_tokens={tot_in} output_tokens={tot_out} "
        f"tool_rounds={tot_tool}"
    )
    return "\n".join(lines), {"per_condition": rows, "total_requests": tot_req,
                              "total_input_tokens": tot_in, "total_output_tokens": tot_out,
                              "total_scenarios": tot_n}


def main():
    lines = [
        "STEP 7 - volume estimate for re-running LLM conditions on db_v2 (NOT executed).",
        "Conditions to re-run: " + ", ".join(CONDS) + " (C3 is deterministic, no API call).",
        "Projection uses token/request volumes ACTUALLY recorded in the db_v1 runs.",
        "Dollar cost omitted: no citable public per-token price for these NVIDIA-hosted models.",
        "",
    ]
    out = {"note": "projection only; no calls made; no invented prices."}
    nemo_txt, nemo = summarize("nemotron-3-ultra (500 scenarios, db_v1 actuals)", stats(NEMO, NEMO_CACHE))
    llama_txt, llama = summarize("llama-3.2-11b (150 scenarios, db_v1 actuals)", stats(LLAMA))
    lines += [nemo_txt, "", llama_txt, ""]
    total_req = nemo["total_requests"] + llama["total_requests"]
    total_in = nemo["total_input_tokens"] + llama["total_input_tokens"]
    total_out = nemo["total_output_tokens"] + llama["total_output_tokens"]
    lines += [
        "===== PROJECTED db_v2 re-run (both models, 5 conditions) =====",
        f"  total requests: {total_req}",
        f"  total input tokens:  {total_in}",
        f"  total output tokens: {total_out}",
        f"  approx sequential time at ~10 req/min: {total_req/600:.1f} hours",
        "",
    ]
    out["projection"] = {"total_requests": total_req, "total_input_tokens": total_in,
                         "total_output_tokens": total_out, "nemotron": nemo, "llama": llama}
    (ROOT / "eval/results/db_v2_cost_estimate.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (ROOT / "eval/results/db_v2_cost_estimate.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
