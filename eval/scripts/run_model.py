"""Resumable, chunk-friendly model evaluation runner.

Designed for very slow reasoning models (e.g. z-ai/glm-5.3, ~150-500s/call) where a
single process cannot run for the whole job:

  * Fixed run directory per model:  eval/runs/eval_<short_name>/
  * results.json is rewritten atomically after every completed call, so a killed
    process loses at most one in-flight call and is fully resumable.
  * --max-seconds lets a caller stop gracefully before a hard timeout; unfinished
    calls are simply picked up on the next invocation.
  * A heartbeat is printed every 15s so progress is always visible.

Usage:
    $env:NVIDIA_REQUEST_TIMEOUT="600"
    python -u eval/scripts/run_model.py --model z-ai/glm-5.3 --scenarios 150 --workers 4
    python -u eval/scripts/run_model.py --model z-ai/glm-5.3 --scenarios 150 --workers 4 --max-seconds 5000
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import threading
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from eval.common import load_config, ensure_dirs, config_dirs, read_jsonl
from eval.llm.nvidia_provider import NvidiaProvider
from eval.llm.prompts import (
    prompt_c0, prompt_c0b, prompt_c1, prompt_c1a, prompt_c1b, prompt_c2, parse_output,
)
from eval.time_anchored import TimeAnchoredBuilder, ToolRuntime
from eval.mcp_runtime import McpToolRuntime

ROOT_DIR = Path(__file__).resolve().parent.parent.parent

MODEL_SHORT = {
    "nvidia/nemotron-3-ultra-550b-a55b": "nemotron-3-ultra",
    "z-ai/glm-5.3": "glm-5.3",
    "meta/llama-3.2-11b-vision-instruct": "llama-3.2-11b",
}
# Phase 8 STEP B conditions (C1a fair, C1b oracle relabelled, C2a/C2b tools).
# C0/C0b unchanged; C1==C1b (oracle) is retained as its own label.
CONDITIONS = ["C0", "C0b", "C1a", "C1b", "C2a", "C2b"]

FIVE_TOOLS = ["weather_tool", "climate_tool", "season_tool", "risk_tool", "get_soil_by_coordinates"]
SIX_TOOLS = FIVE_TOOLS + ["crop_score"]


def build_prompt(condition, scenario, evidence=None):
    if condition == "C0":
        return prompt_c0(scenario), False, None
    if condition == "C0b":
        return prompt_c0b(scenario), False, None
    if condition == "C1a":
        return prompt_c1a(scenario, evidence), False, None
    if condition == "C1b":
        return prompt_c1b(scenario, evidence), False, None
    if condition == "C2a":
        return prompt_c2(scenario, SIX_TOOLS), True, SIX_TOOLS
    if condition == "C2b":
        return prompt_c2(scenario, FIVE_TOOLS), True, FIVE_TOOLS
    raise ValueError(f"Unknown condition: {condition}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, choices=list(MODEL_SHORT.keys()))
    ap.add_argument("--scenarios", type=int, default=None)
    ap.add_argument("--scenario-start", type=int, default=0,
                    help="0-based offset into llm_subset for a contiguous slice, e.g. B2 = "
                         "--scenario-start 150 --scenarios 350. Ignored if --scenario-ids is set.")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--max-seconds", type=float, default=None,
                    help="Stop gracefully after this many seconds (resumes next run)")
    ap.add_argument("--retry-errors", action="store_true",
                    help="Also re-run calls that previously produced an error")
    ap.add_argument("--conditions", default="C0,C0b,C1a,C1b,C2a,C2b",
                    help="Comma-separated conditions to run (default: all Phase 8 STEP B)")
    ap.add_argument("--scenario-ids", default="",
                    help="Optional comma-separated scenario_ids (pilot v2 selection); "
                         "ignored if empty. Scenarios are taken from llm_subset in subset order.")
    ap.add_argument("--pilot-dev", action="store_true",
                    help="Tag records with pilot_dev=true, write pilot_dev_scenarios.json, "
                         "and write results to eval_<short>_pilot_dev/ (isolated from primary)")
    ap.add_argument("--tool-transport", choices=["inprocess", "mcp"], default="inprocess",
                    help="How C2 tool calls are executed: 'inprocess' (default; direct "
                         "function calls via ToolRuntime) or 'mcp' (real MCP client -> "
                         "eval/mcp_eval/server.py over streamable-http). Does not change "
                         "the evidence; only the transport.")
    ap.add_argument("--run-suffix", default="",
                    help="Extra suffix appended to the run dir and to the per-model cache "
                         "namespace, to keep a run isolated from primary results.")
    args = ap.parse_args()
    requested_conditions = [c.strip() for c in args.conditions.split(",")]

    model_id = args.model
    short = MODEL_SHORT[model_id]

    cfg = load_config()
    ensure_dirs(cfg)
    dirs = config_dirs(cfg)
    cfg["model"]["nvidia"]["name"] = model_id
    cfg["model"]["name"] = model_id

    llm_subset = read_jsonl(dirs["llm_subset_path"])
    id_set = {s["scenario_id"] for s in llm_subset}
    if args.scenario_ids:
        requested_ids = [x.strip() for x in args.scenario_ids.split(",") if x.strip()]
        unknown_ids = [i for i in requested_ids if i not in id_set]
        if unknown_ids:
            raise SystemExit(f"Unknown scenario_ids: {unknown_ids}")
        scenarios = [s for s in llm_subset if s["scenario_id"] in requested_ids]
    else:
        _start = max(0, args.scenario_start)
        _end = _start + args.scenarios if args.scenarios else None
        scenarios = llm_subset[_start:_end]
    scenario_map = {s["scenario_id"]: s for s in scenarios}
    repeats = range(args.repeat)

    pilot_info_path = Path(str(ROOT_DIR)) / "eval/results/pilot_dev_scenarios.json"
    run_suffix = "_pilot_dev" if args.pilot_dev else ""
    run_suffix += args.run_suffix
    run_dir = dirs["runs_dir"] / f"eval_{short}{run_suffix}"
    run_dir.mkdir(parents=True, exist_ok=True)
    results_file = run_dir / "results.json"

    if args.pilot_dev:
        manifest = {
            "scenario_ids": [s["scenario_id"] for s in scenarios],
            "model": model_id,
            "conditions": requested_conditions,
            "repeat": args.repeat,
            "note": "pilot_dev records; if any prompt/harness change follows, restart the "
                    "pilot and exclude these scenarios from primary analyses (or report with/without).",
        }
        pilot_info_path.parent.mkdir(parents=True, exist_ok=True)
        pilot_info_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"pilot_dev manifest -> {pilot_info_path}")

    # Cache namespace is transport-scoped: an 'mcp' run must NOT silently reuse
    # in-process cached records (that would defeat the transport comparison).
    cache_short = short + ("_mcp" if args.tool_transport == "mcp" else "")
    cache_dir = dirs["cache_dir"] / "llm" / cache_short
    cache_dir.mkdir(parents=True, exist_ok=True)

    def cache_path(model, cond, prompt, sid, rep):
        payload = "\u241f".join([model, cond, prompt, sid, str(rep)])
        return cache_dir / (hashlib.sha256(payload.encode("utf-8")).hexdigest() + ".json")

    results = []
    if results_file.exists():
        try:
            with results_file.open() as f:
                results = json.load(f)
        except Exception as e:
            print(f"WARNING: could not read existing results.json ({e}); starting fresh", flush=True)
            results = []

    done_keys = set()
    for r in results:
        key = (r["scenario_id"], r["condition"], r.get("repeat", 0))
        if r.get("error") and args.retry_errors:
            continue
        done_keys.add(key)

    all_keys = [(s["scenario_id"], c, rep) for rep in repeats for s in scenarios for c in CONDITIONS if c in requested_conditions]
    todo = [k for k in all_keys if k not in done_keys]

    print(f"Model: {model_id} ({short})")
    print(f"Run dir: {run_dir}")
    print(f"Total target calls: {len(all_keys)} | already done: {len(done_keys)} | todo: {len(todo)}")
    print(f"Workers: {args.workers} | request timeout: {os.getenv('NVIDIA_REQUEST_TIMEOUT', '120')}s", flush=True)

    if not todo:
        print("Nothing to do.")
        return

    print("Building evidence bundles (v2, time-anchored)...", flush=True)
    evidence = {}
    if any(c in requested_conditions for c in ("C1", "C1a", "C1b")):
        evidence_provider = TimeAnchoredBuilder(cfg)
        for sc in scenarios:
            evidence[sc["scenario_id"]] = evidence_provider.build(sc)
    print(f"Built {len(evidence)} evidence bundles", flush=True)

    # Phase 8 STEP A: C2 tool calls go through the time-anchored offline runtime
    # (injected clock + cached weather; no live API / datetime.now).
    if args.tool_transport == "mcp":
        tool_runtime = McpToolRuntime(cfg)
        print("Tool transport: mcp (real MCP client -> eval/mcp_eval/server.py over "
              "streamable-http)", flush=True)
    else:
        tool_runtime = ToolRuntime(cfg)
        print("Tool transport: inprocess (ToolRuntime direct calls)", flush=True)
    provider = NvidiaProvider(cfg, tool_runtime=tool_runtime)

    lock = threading.Lock()
    stats = {"done": 0, "ok": 0, "err": 0, "active": 0}
    start = time.time()
    budget_event = threading.Event()

    def save():
        tmp = results_file.with_suffix(".tmp")
        with tmp.open("w") as f:
            json.dump(results, f, indent=2)
        tmp.replace(results_file)

    def heartbeat():
        while True:
            time.sleep(15)
            with lock:
                d, o, e, a = stats["done"], stats["ok"], stats["err"], stats["active"]
            print(f"[heartbeat] {time.time()-start:.0f}s | done {d}/{len(todo)} | ok {o} err {e} active {a}",
                  flush=True)

    def run_one(key):
        if budget_event.is_set():
            return None
        sid, cond, rep = key
        sc = scenario_map[sid]
        prompt, use_mcp, allowed_tools = build_prompt(cond, sc, evidence.get(sid))
        cpath = cache_path(model_id, cond, prompt, sid, rep)
        with lock:
            stats["active"] += 1
        try:
            rec = None
            if cpath.exists():
                try:
                    with cpath.open() as f:
                        cached = json.load(f)
                    if not cached.get("error"):
                        rec = cached
                except Exception:
                    rec = None
            if rec is None:
                # ss8.10 amend (2026-10-13): tool-condition prompts get the raised
                # 8192 cap even when no tools are in the payload (C1a/C1b). C0/C0b
                # keep the non-tool 4096 cap (max_output_tokens=None -> provider default).
                cap = cfg["model"].get("max_output_tokens_tools") if cond in ("C1a", "C1b", "C2a", "C2b") else None
                res = provider.run(prompt, agent="full_run", use_mcp=use_mcp,
                                   scenario=sc if use_mcp else None,
                                   allowed_tools=allowed_tools,
                                   max_output_tokens=cap)
                # PROTOCOL 8.12: budget hard-stop is NOT a model error and must not be
                # recorded/cached - signal a clean stop so the call resumes next UTC day.
                if res.error_type == "budget_exceeded":
                    budget_event.set()
                    return None
                rec = {
                    "model": model_id,
                    "model_short": short,
                    "condition": cond,
                    "scenario_id": sid,
                    "repeat": rep,
                    "prompt_hash": cpath.stem,
                    "text": res.text,
                    "tokens_in": res.tokens_in,
                    "tokens_out": res.tokens_out,
                    "reasoning_tokens": res.reasoning_tokens,
                    "latency_s": res.latency_s,
                    "tool_calls": res.tool_calls,
                    "tool_log": res.tool_log,
                    "finish_reason": res.finish_reason,
                    "error": res.error,
                    "error_type": res.error_type,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "parsed": parse_output(res.text),
                    "unknown_tool_calls": res.unknown_tool_calls,
                    "forced_final": res.forced_final,
                    "forced_final_reason": res.forced_final_reason,
                    "truncated": res.truncated,
                }
                tmp = cpath.with_suffix(".tmp")
                with tmp.open("w") as f:
                    json.dump(rec, f)
                tmp.replace(cpath)
        except Exception as ex:
            rec = {
                "model": model_id, "model_short": short, "condition": cond,
                "scenario_id": sid, "repeat": rep, "prompt_hash": "",
                "text": "", "tokens_in": 0, "tokens_out": 0, "reasoning_tokens": 0,
                "latency_s": 0, "tool_calls": 0, "tool_log": [], "finish_reason": "",
                "error": f"{type(ex).__name__}: {ex}", "error_type": "harness_error",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "parsed": {"valid_json": False},
                "unknown_tool_calls": 0, "forced_final": False,
                "forced_final_reason": "", "truncated": False,
            }
        rec.setdefault("repeat", rep)
        # Fields added in harness-fix ss8.10: default them for pre-fix cached records.
        rec.setdefault("unknown_tool_calls", 0)
        rec.setdefault("forced_final", False)
        rec.setdefault("forced_final_reason", "")
        rec.setdefault("truncated", rec.get("finish_reason") == "length")
        if args.pilot_dev:
            rec["pilot_dev"] = True
        if not args.pilot_dev and rec.get("pilot_dev"):
            rec = dict(rec)  # cached pilot record leaking into a primary run: clear the tag
            rec.pop("pilot_dev", None)
        with lock:
            stats["active"] -= 1
            results.append(rec)
            done_keys.add(key)
            if rec["error"]:
                stats["err"] += 1
            else:
                stats["ok"] += 1
            stats["done"] += 1
            save()
        tag = "OK" if not rec["error"] else f"ERR:{str(rec['error'])[:50]}"
        print(f"  {sid} {cond} r{rep} {tag} ({rec['latency_s']:.0f}s tools={rec['tool_calls']} "
              f"json={'Y' if rec['parsed'].get('valid_json') else 'N'})", flush=True)
        return rec

    threading.Thread(target=heartbeat, daemon=True).start()

    stopped_early = False
    try:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futures = {ex.submit(run_one, k): k for k in todo}
            for fut in as_completed(futures):
                fut.result()
                if budget_event.is_set():
                    stopped_early = True
                    for f in futures:
                        f.cancel()
                    break
                if args.max_seconds and (time.time() - start) >= args.max_seconds:
                    stopped_early = True
                    for f in futures:
                        f.cancel()
                    break
    finally:
        tool_runtime.close()
        provider.close()
        with lock:
            save()

    elapsed = time.time() - start
    remaining = len(todo) - stats["done"]
    print(f"\nFinished this chunk: ok={stats['ok']} err={stats['err']} done={stats['done']}/{len(todo)} "
          f"in {elapsed/60:.1f}min")
    if stopped_early:
        if budget_event.is_set():
            print("Stopped cleanly: UTC-day HTTP budget exhausted. Nothing was recorded as an "
                  "error; re-run the SAME command after 00:00:00Z to resume.")
            print("NEXT RESUME COMMAND: (same command; runner is resumable, cache intact)")
        else:
            print(f"Stopped early by --max-seconds. Remaining for next run: ~{remaining}")
    print(f"Results: {results_file}")

    by_cond = Counter(r["condition"] for r in results)
    print(f"Cumulative results: {len(results)} | {dict(by_cond)}")


if __name__ == "__main__":
    main()
