"""S-series runner (PROTOCOL 8.32): perturbed-condition model runs.

Runs conditions C1a/C2a/C2b for each named perturbation set and model over the fixed
base scenario set, writing to isolated run/cache namespaces. Resumable; never touches
``mcp_server/`` or the original weather cache.

    py -3 eval/scripts/run_s_series.py --models nemotron llama --sets W2 R1 C1
    py -3 eval/scripts/run_s_series.py --sets N0 --conditions C2a   # harness identity check

C0/C0b (no-tool) are NOT run here; the base column is read from the canonical runs.
The per-call cache namespace is isolated PER SET (C2a/C2b prompts are set-invariant, so
sharing a namespace would collide across sets).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from eval.common import load_config, ensure_dirs, config_dirs  # noqa: E402
from eval.llm.nvidia_provider import NvidiaProvider  # noqa: E402
from eval.llm.prompts import prompt_c0, prompt_c0b, prompt_c1a, prompt_c2, parse_output  # noqa: E402
from eval.time_anchored import ToolRuntime  # noqa: E402
from eval.s_series.builder import PerturbedTimeAnchoredBuilder  # noqa: E402
from eval.s_series.perturbations import RUN_SETS, PERTURBATIONS  # noqa: E402
from eval.s_series import base_set  # noqa: E402

MODEL_SHORT = {
    "nvidia/nemotron-3-ultra-550b-a55b": "nemotron-3-ultra",
    "meta/llama-3.2-11b-vision-instruct": "llama-3.2-11b",
}
MODEL_IDS = {
    "nemotron": "nvidia/nemotron-3-ultra-550b-a55b",
    "llama": "meta/llama-3.2-11b-vision-instruct",
}
FIVE_TOOLS = ["weather_tool", "climate_tool", "season_tool", "risk_tool", "get_soil_by_coordinates"]
SIX_TOOLS = FIVE_TOOLS + ["crop_score"]
TOOL_CONDITIONS = ("C1a", "C2a", "C2b")


def build_prompt(condition, scenario, evidence=None):
    if condition == "C0":
        return prompt_c0(scenario), False, None
    if condition == "C0b":
        return prompt_c0b(scenario), False, None
    if condition == "C1a":
        return prompt_c1a(scenario, evidence), False, None
    if condition == "C2a":
        return prompt_c2(scenario, SIX_TOOLS), True, SIX_TOOLS
    if condition == "C2b":
        return prompt_c2(scenario, FIVE_TOOLS), True, FIVE_TOOLS
    raise ValueError(condition)


def run_one_set(model_key, set_name, scenarios, conditions, cfg, dirs, workers, max_seconds):
    model_id = MODEL_IDS[model_key]
    short = MODEL_SHORT[model_id]
    cfg = {**cfg, "model": {**cfg["model"], "name": model_id,
                            "nvidia": {**cfg["model"].get("nvidia", {}), "name": model_id}}}

    run_dir = dirs["runs_dir"] / f"s_{set_name}" / f"eval_{short}"
    run_dir.mkdir(parents=True, exist_ok=True)
    results_file = run_dir / "results.json"
    cache_dir = dirs["cache_dir"] / "llm_s" / f"{short}_{set_name}"
    cache_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    if results_file.exists():
        try:
            results = json.loads(results_file.read_text(encoding="utf-8"))
        except Exception:
            results = []
    done_keys = {(r["scenario_id"], r["condition"], r.get("repeat", 0))
                 for r in results if not r.get("error")}
    all_keys = [(s["scenario_id"], c, 0) for s in scenarios for c in conditions]
    todo = [k for k in all_keys if k not in done_keys]
    scenario_map = {s["scenario_id"]: s for s in scenarios}

    print(f"\n=== set {set_name} ({PERTURBATIONS[set_name]['label']}) | {model_id} ({short}) ===", flush=True)
    print(f"Run dir: {run_dir}\nCalls: {len(results)} done | todo {len(todo)}/{len({k for k in all_keys})}", flush=True)
    if not todo:
        print("Nothing to do.", flush=True)
        return {"set": set_name, "model": model_key, "todo": 0, "ok": 0, "err": 0, "budget": False}

    builder = PerturbedTimeAnchoredBuilder(cfg, set_name)
    runtime = ToolRuntime(cfg, builder=builder)
    provider = NvidiaProvider(cfg, tool_runtime=runtime)

    print("Building perturbed evidence bundles...", flush=True)
    evidence = {}
    if any(c in conditions for c in ("C1a",)):
        for sc in scenarios:
            evidence[sc["scenario_id"]] = builder.build(sc)
    print(f"Built {len(evidence)} bundles", flush=True)

    scenario_map = {s["scenario_id"]: s for s in scenarios}
    lock = threading.Lock()
    stats = {"done": 0, "ok": 0, "err": 0, "active": 0}
    start = time.time()
    budget_event = threading.Event()

    def save():
        tmp = results_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(results, indent=2), encoding="utf-8")
        tmp.replace(results_file)

    stop_hb = threading.Event()

    def heartbeat():
        while not stop_hb.is_set():
            if stop_hb.wait(15):
                break
            with lock:
                d, o, e, a = stats["done"], stats["ok"], stats["err"], stats["active"]
            print(f"[hb {set_name}/{short}] {time.time()-start:.0f}s | {d}/{len(todo)} | ok {o} err {e} active {a}",
                  flush=True)

    def cache_path(cond, prompt, sid, rep):
        key = hashlib.sha256("\x1f".join([model_id, cond, prompt, sid, str(rep)]).encode()).hexdigest()
        return cache_dir / f"{key}.json"

    def run_one(key):
        if budget_event.is_set():
            return None
        sid, cond, rep = key
        sc = scenario_map[sid]
        prompt, use_mcp, allowed = build_prompt(cond, sc, evidence.get(sid))
        cpath = cache_path(cond, prompt, sid, rep)
        with lock:
            stats["active"] += 1
        try:
            rec = None
            if cpath.exists():
                try:
                    cached = json.loads(cpath.read_text(encoding="utf-8"))
                    if not cached.get("error"):
                        rec = cached
                except Exception:
                    rec = None
            if rec is None:
                cap = cfg["model"].get("max_output_tokens_tools") if cond in TOOL_CONDITIONS else None
                res = provider.run(prompt, agent="s_series", use_mcp=use_mcp,
                                   scenario=sc if use_mcp else None, allowed_tools=allowed,
                                   max_output_tokens=cap)
                if res.error_type == "budget_exceeded":
                    budget_event.set()
                    return None
                rec = {
                    "model": model_id, "model_short": short, "condition": cond,
                    "scenario_id": sid, "repeat": rep, "s_set": set_name,
                    "prompt_hash": cpath.stem, "text": res.text,
                    "tokens_in": res.tokens_in, "tokens_out": res.tokens_out,
                    "reasoning_tokens": res.reasoning_tokens, "latency_s": res.latency_s,
                    "tool_calls": res.tool_calls, "tool_log": res.tool_log,
                    "finish_reason": res.finish_reason, "error": res.error,
                    "error_type": res.error_type,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "parsed": parse_output(res.text),
                    "unknown_tool_calls": res.unknown_tool_calls,
                    "forced_final": res.forced_final,
                    "forced_final_reason": getattr(res, "forced_final_reason", ""),
                    "truncated": res.truncated,
                }
                tmp = cpath.with_suffix(".tmp")
                tmp.write_text(json.dumps(rec), encoding="utf-8")
                tmp.replace(cpath)
        except Exception as ex:
            rec = {"model": model_id, "model_short": short, "condition": cond,
                   "scenario_id": sid, "repeat": rep, "s_set": set_name, "text": "",
                   "tokens_in": 0, "tokens_out": 0, "reasoning_tokens": 0, "latency_s": 0,
                   "tool_calls": 0, "tool_log": [], "finish_reason": "",
                   "error": f"{type(ex).__name__}: {ex}", "error_type": "harness_error",
                   "timestamp": datetime.now(timezone.utc).isoformat(),
                   "parsed": {"valid_json": False}, "truncated": False}
        rec.setdefault("truncated", rec.get("finish_reason") == "length")
        with lock:
            stats["active"] -= 1
            results.append(rec)
            if rec.get("error"):
                stats["err"] += 1
            else:
                stats["ok"] += 1
            stats["done"] += 1
            save()
        print(f"  {sid} {cond} {'ERR:'+str(rec['error'])[:40] if rec.get('error') else 'OK'} "
              f"({rec['latency_s']:.0f}s tools={rec['tool_calls']})", flush=True)
        return rec

    threading.Thread(target=heartbeat, daemon=True).start()
    stopped = False
    try:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(run_one, k): k for k in todo}
            for fut in as_completed(futs):
                fut.result()
                if budget_event.is_set() or (max_seconds and time.time() - start >= max_seconds):
                    stopped = True
                    for f in futs:
                        f.cancel()
                    break
    finally:
        stop_hb.set()
        runtime.close()
        provider.close()
        with lock:
            save()

    print(f"Finished {set_name}/{short}: ok={stats['ok']} err={stats['err']} "
          f"done={stats['done']}/{len(todo)} in {(time.time()-start)/60:.1f}min")
    return {"set": set_name, "model": model_key, "todo": len(todo),
            "ok": stats["ok"], "err": stats["err"], "budget": budget_event.is_set(),
            "stopped": stopped}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=["nemotron", "llama"], choices=["nemotron", "llama"])
    ap.add_argument("--sets", nargs="+", default=RUN_SETS)
    ap.add_argument("--conditions", nargs="+", default=list(TOOL_CONDITIONS))
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--workers", type=int, default=int(os.getenv("S_WORKERS", "4")))
    ap.add_argument("--max-seconds", type=float, default=None)
    args = ap.parse_args()

    cfg = load_config()
    ensure_dirs(cfg)
    dirs = config_dirs(cfg)

    sids = base_set.select_base(args.n)
    scenarios = sorted(base_set.scenarios_by_id(sids).values(), key=lambda s: s["scenario_id"])
    manifest = dirs["results_dir"] / "s_base_set.json"
    manifest.write_text(json.dumps({"scenario_ids": sids, "n": len(sids),
                                    "common_support": len(base_set.common_support()),
                                    "seed": 42}, indent=2), encoding="utf-8")
    print(f"Base set: {len(scenarios)} scenarios | manifest {manifest}")
    print(f"Models {args.models} | sets {args.sets} | conditions {args.conditions} | workers {args.workers}")

    t0 = time.time()
    for set_name in args.sets:
        if set_name not in PERTURBATIONS:
            raise SystemExit(f"Unknown set {set_name}")
        for model_key in args.models:
            out = run_one_set(model_key, set_name, scenarios, args.conditions,
                              cfg, dirs, args.workers, args.max_seconds)
            print(f"  -> {out}", flush=True)
            if out.get("budget") or (args.max_seconds and time.time() - t0 >= args.max_seconds):
                print("Stopping (budget/--max-seconds). Re-run the SAME command to resume.", flush=True)
                return
    print(f"\nAll requested sets finished in {(time.time()-t0)/60:.1f} min.", flush=True)


if __name__ == "__main__":
    main()
