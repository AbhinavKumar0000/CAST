"""Phase 8 STEP E: offline dry-run of the STEP F staged LLM run. NO API calls.

Projects requests, tokens and wall-clock for the FINAL staged plan (user decisions):

  Stage A  Llama    C1a/C2a/C2b on 150 (C0b reused from v1 cache; NO new C0/C0b calls)
  Stage B  Nemotron C1a/C2a/C2b on 500 (C0b reused for 472/500; 28 re-runs fresh)
  Stage C  Consistency repeats (Nemotron first, then Llama): 100 scenarios x 3 conds
           (C0b/C1a/C2a) x 3 repeats; repeats 1..2 fresh => 600 fresh/model
  Stage D  OPTIONAL third model on 150 (only if passes smoke rule); C1b oracle on 150
           for Nemotron only. Both treated as optional in this projection.

Run:  python -u eval/scripts/dry_run_phase8.py
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

# Conditions in the final comparison set (STEP C primary family uses C0b baseline).
CONDS_MAIN = ["C0b", "C1a", "C2a", "C2b"]          # per model
CONSISTENCY_CONDS = ["C0b", "C1a", "C2a"]
CONSISTENCY_SCENARIOS = 100
CONSISTENCY_REPEATS_TOTAL = 3                       # repeats 0,1,2; repeat 0 already run -> 2 fresh
CONSISTENCY_FRESH_PER_COND = CONSISTENCY_SCENARIOS * (CONSISTENCY_REPEATS_TOTAL - 1)
ORACLE_N = 150                                      # C1b supplementary (Nemotron only)

PLAN = [
    # (stage, model, subset_n, conds, note)
    ("A", "llama-3.2-11b", 150, CONDS_MAIN, "reuse C0b 150/150; fresh C1a/C2a/C2b"),
    ("B", "nemotron-3-ultra", 500, CONDS_MAIN, "reuse C0b 472/500 (28 re-run); fresh C1a/C2a/C2b"),
]
CONSISTENCY_MODELS = ["nemotron-3-ultra", "llama-3.2-11b"]  # Nemotron first, then Llama

# C1/C2 old-harness records are valid token/latency proxies for C1a/C2a/C2b.
PROXY = {"C1a": "C1", "C2a": "C2", "C2b": "C2", "C1b": "C1"}

# Measured per-model stats: token/latency come ONLY from repeat-0, error-free,
# non-archived v1 records (C0/C0b direct; C1/C2 as proxies for the tool conditions).
RESULT_DIRS = [
    Path("eval/runs/eval_llama-3.2-11b"),
    Path("eval/runs/full_nemotron-3-ultra_20261011_074835"),
    Path("eval/runs/full_nemotron-3-ultra_20261011_082444"),
    Path("eval/runs/eval_glm-5.3"),  # informational only (dropped from main analysis)
]

REUSE = json.loads(
    (Path(__file__).resolve().parent.parent.parent / "eval/results/reuse_report.json").read_text(encoding="utf-8")
)
REUSE_BY = {(u["model"], u["condition"]): (u["intended"], len(u["reusable"]), len(u["re_run"]))
            for u in REUSE["reuse"]}


def load_model_stats() -> dict[str, dict[str, dict]]:
    stats: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for d in RESULT_DIRS:
        rf = d / "results.json"
        if not rf.exists():
            continue
        try:
            recs = json.loads(rf.read_text(encoding="utf-8"))
        except Exception:
            continue
        for r in recs:
            if r.get("error") or r.get("repeat", 0) != 0:
                continue
            m = r.get("model_short", r.get("model", "?"))
            c = r.get("condition")
            out_tokens = int(r.get("tokens_out", 0))
            tokens_in = int(r.get("tokens_in", 0))
            latency = float(r.get("latency_s", 0))
            tcs = int(r.get("tool_calls", 0))
            if out_tokens and tokens_in and latency:
                stats[m][c].append((tokens_in, out_tokens, latency, tcs))
    summary: dict[str, dict[str, dict]] = {}
    for m, conds in stats.items():
        summary[m] = {}
        for c, vals in conds.items():
            n = len(vals)
            summary[m][c] = {
                "n": n,
                "tokens_in_mean": sum(v[0] for v in vals) / n,
                "tokens_out_mean": sum(v[1] for v in vals) / n,
                "latency_s_mean": sum(v[2] for v in vals) / n,
                "tool_calls_mean": sum(v[3] for v in vals) / n,
            }
    return summary


def token_estimate(model: str, cond: str, stats: dict) -> dict:
    if cond in stats.get(model, {}):
        return stats[model][cond]
    proxy = PROXY.get(cond, cond)
    if proxy in stats.get(model, {}):
        rel = dict(stats[model][proxy])
        rel["proxied_from"] = proxy
        return rel
    return {"tokens_in_mean": 2500, "tokens_out_mean": 300, "latency_s_mean": 20.0, "proxied_from": "default"}


def fmt_reuse(model, cond):
    key = ("nvidia/nemotron-3-ultra-550b-a55b", cond) if model == "nemotron-3-ultra" else \
          ("meta/llama-3.2-11b-vision-instruct", cond)
    if key not in REUSE_BY:
        return "n/a"
    n, good, rerun = REUSE_BY[key]
    return f"{good}/{n} cached (re-run {rerun})"


def http_per_scenario(model, cond, stats):
    """HTTP POSTs per scenario. Every provider.run tool-loop iteration is one HTTP POST
    (tool-call rounds + 1 final non-tool round). C0/C0b/C1 have no tools -> 1 request.
    C2a/C2b round counts are NOT recorded in the archived v1 tool_log (empty), so we use
    the measured per-scenario tool_calls + 1 final round (sequential worst case; Llama
    calls 6.41 tools/scenario -> ~7.4 HTTP). Nemotron parallel batches may be lower;
    pilot (STEP A fills tool_log) will refine the real round counts."""
    if cond in ("C0", "C0b", "C1a", "C1b"):
        return 1
    proxy = PROXY.get(cond, cond)
    s = stats.get(model, {}).get(proxy)
    if s and s["n"] > 0:
        return round(s["tool_calls_mean"] + 1.0, 2)
    return 7.0


def main():
    stats = load_model_stats()
    print("Measured per-condition stats from archived v1 records (repeat-0, no error):")
    for m, conds in stats.items():
        for c, s in sorted(conds.items()):
            print(f"  {m:18s} {c:4s} n={s['n']:4d} in={s['tokens_in_mean']:7.0f} "
                  f"out={s['tokens_out_mean']:5.0f} lat={s['latency_s_mean']:6.1f}s")

    total_req = total_in = total_out = total_http = 0
    total_wall_s = 0.0
    workers = 4

    print("\n=== STAGED PLAN (NO API calls in this dry-run) ===")
    for stage, model, n, conds, note in PLAN:
        req = tin = tout = wall = http = 0
        rows = []
        for cond in conds:
            est = token_estimate(model, cond, stats)
            reuse = fmt_reuse(model, cond)
            hp = http_per_scenario(model, cond, stats)
            if cond == "C0b":
                _, good, rerun = REUSE_BY[(("nvidia/nemotron-3-ultra-550b-a55b", cond)
                    if model == "nemotron-3-ultra" else ("meta/llama-3.2-11b-vision-instruct", cond))]
                fresh = rerun  # cached records reused; only hash-mismatch/error sids re-run
            else:
                fresh = n
            req += fresh
            http += fresh * hp
            tin += est["tokens_in_mean"] * fresh
            tout += est["tokens_out_mean"] * fresh
            wall += est["latency_s_mean"] * fresh / workers
            rows.append((cond, fresh, hp, int(est["tokens_in_mean"]), int(est["tokens_out_mean"]),
                         round(est["latency_s_mean"], 1), reuse))
        print(f"\n[Stage {stage}] {model} on {n} scenarios ({note})   approx {req} fresh req / "
              f"{http:,.0f} HTTP / {tin/1e6:.2f}M in / {tout/1e6:.2f}M out / ~{wall/60:.0f} min")
        for cond, fresh, hp, ti, to, lat, reuse in rows:
            print(f"   {cond:4s} fresh={fresh:5d} http/scen~{hp:4.2f}->{fresh*hp:6.0f}  "
                  f"~{ti:5d} in ~{to:4d} out  lat~{lat:5.1f}s  reuse: {reuse}")
        total_req += req; total_in += tin; total_out += tout; total_wall_s += wall; total_http += http

    print("\n=== STAGE C: consistency (Nemotron first, then Llama) ===")
    for model in CONSISTENCY_MODELS:
        req = tin = tout = wall = http = 0
        per_cond = []
        for cc in CONSISTENCY_CONDS:
            est = token_estimate(model, cc, stats)
            hp = http_per_scenario(model, cc, stats)
            fresh = CONSISTENCY_FRESH_PER_COND
            req += fresh
            http += fresh * hp
            tin += est["tokens_in_mean"] * fresh
            tout += est["tokens_out_mean"] * fresh
            wall += est["latency_s_mean"] * fresh / workers
            per_cond.append((cc, fresh, hp, round(est["latency_s_mean"], 1)))
        print(f"  {model}: {CONSISTENCY_SCENARIOS} scen x {len(CONSISTENCY_CONDS)} conds x 3 repeats "
              f"(repeat 0 exists) = {req} fresh / {http:,.0f} HTTP | {tin/1e6:.2f}M in / {tout/1e6:.2f}M out "
              f"/ ~{wall/60:.0f} min")
        for cc, fresh, hp, lat in per_cond:
            print(f"    {cc:4s} fresh={fresh} http/scen~{hp:4.2f}->{fresh*hp:6.0f} lat~{lat}s")
        total_req += req; total_in += tin; total_out += tout; total_wall_s += wall; total_http += http

    print("\n=== STAGE D (OPTIONAL, gated on a passing third family + approval) ===")
    est_c1b = token_estimate("nemotron-3-ultra", "C1b", stats)
    c1b = ORACLE_N
    d_req = c1b; d_http = c1b
    print(f"  C1b oracle: nemotron on {c1b} -> {d_req} fresh / ~{d_http} HTTP, "
          f"{c1b*est_c1b['tokens_in_mean']/1e6:.2f}M in / {c1b*est_c1b['tokens_out_mean']/1e6:.2f}M out, "
          f"lat~{est_c1b['latency_s_mean']}s (~{c1b*est_c1b['latency_s_mean']/(60*workers):.0f} min)")
    print("  third family: none passes the smoke rule so far (403/timeout) -> skipped unless gated pick")

    total_wall_min = total_wall_s / 60.0
    print(f"\n=== TOTAL (stages A-C; D optional) ===")
    print(f"fresh requests: {total_req:,}   HTTP requests (every tool round): {total_http:,.0f}")
    print(f"tokens: {total_in/1e6:,.2f}M in / {total_out/1e6:,.2f}M out "
          f"({(total_in+total_out)/1e6:,.2f}M total)")
    daily = 4000
    print(f"daily budget (config): {daily} HTTP/day  -> HD would need "
          f"{total_http/daily:.1f} days at full utilization")
    print(f"projected wall-clock (fresh, {workers} workers, sequential stages): ~{total_wall_min/60:.1f} h")


if __name__ == "__main__":
    main()