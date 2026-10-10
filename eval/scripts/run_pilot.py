"""Pilot runner: 30 scenarios × 4 conditions × 3 models.

Uses the LLM subset (500 scenarios), samples 30 stratified scenarios.
Runs all conditions (C0, C0b, C1, C2) for each selected model.
"""

import json
import os
import sys
import time
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict

import httpx
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from eval.common import load_config, ensure_dirs, config_dirs, write_json, read_jsonl, ResultMeta
from eval.scenarios import generate
from eval.llm.nvidia_provider import NvidiaProvider
from eval.llm.prompts import prompt_c0, prompt_c0b, prompt_c1, prompt_c2, parse_output
from eval.evidence import EvidenceProvider

cfg = load_config()
ensure_dirs(cfg)
dirs = config_dirs(cfg)

# Load LLM subset
llm_subset = read_jsonl(dirs['llm_subset_path'])
print(f"LLM subset: {len(llm_subset)} scenarios")

# Sample 30 stratified scenarios for pilot
import numpy as np
rng = np.random.default_rng(cfg['seeds']['llm_subset_sampling'])
pilot_indices = rng.choice(len(llm_subset), size=30, replace=False)
pilot_scenarios = [llm_subset[i] for i in sorted(pilot_indices)]

print(f"Pilot: {len(pilot_scenarios)} scenarios")

# Selected models
MODELS = [
    ("nvidia/nemotron-3-ultra-550b-a55b", "nemotron-3-ultra"),
    ("z-ai/glm-5.3", "glm-5.3"),
    ("meta/llama-3.2-11b-vision-instruct", "llama-3.2-11b"),
]

# Conditions
CONDITIONS = ["C0", "C0b", "C1", "C2"]

# Evidence provider for C1 (context stuffing)
evidence_provider = EvidenceProvider(cfg)

# Cache for LLM calls
cache_dir = Path(dirs['cache_dir']) / "pilot"
cache_dir.mkdir(parents=True, exist_ok=True)

def cache_key(model: str, condition: str, prompt: str, scenario_id: str, repeat: int) -> str:
    payload = "\u241f".join([model, condition, prompt, scenario_id, str(repeat)])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

def load_cache(key: str):
    path = cache_dir / f"{key}.json"
    if path.exists():
        with path.open() as f:
            return json.load(f)
    return None

def save_cache(key: str, data: dict):
    path = cache_dir / f"{key}.json"
    with path.open("w") as f:
        json.dump(data, f)

def run_condition(provider: NvidiaProvider, model_id: str, short_name: str, 
                  condition: str, scenario: dict, evidence: dict = None) -> dict:
    """Run a single condition for a scenario."""
    
    if condition == "C0":
        prompt = prompt_c0(scenario)
        use_mcp = False
    elif condition == "C0b":
        prompt = prompt_c0b(scenario)
        use_mcp = False
    elif condition == "C1":
        prompt = prompt_c1(scenario, evidence)
        use_mcp = False
    elif condition == "C2":
        prompt = prompt_c2(scenario)
        use_mcp = True
    else:
        raise ValueError(f"Unknown condition: {condition}")
    
    # Check cache
    key = cache_key(model_id, condition, prompt, scenario['scenario_id'], 0)
    cached = load_cache(key)
    if cached:
        print(f"    [{condition}] CACHED")
        return cached
    
    print(f"    [{condition}] Calling {short_name}...", end=" ", flush=True)
    result = provider.run(prompt, agent="pilot", use_mcp=use_mcp)
    
    output = {
        "model": model_id,
        "model_short": short_name,
        "condition": condition,
        "scenario_id": scenario['scenario_id'],
        "prompt_hash": key,
        "text": result.text,
        "tokens_in": result.tokens_in,
        "tokens_out": result.tokens_out,
        "reasoning_tokens": result.reasoning_tokens,
        "latency_s": result.latency_s,
        "tool_calls": result.tool_calls,
        "error": result.error,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    
    parsed = parse_output(result.text)
    output["parsed"] = parsed
    
    if result.ok:
        print(f"OK ({result.latency_s:.1f}s, tokens={result.tokens_in}/{result.tokens_out}, tools={result.tool_calls})")
    else:
        print(f"ERROR: {result.error}")
    
    save_cache(key, output)
    return output

def main():
    print("=" * 60)
    print("PILOT RUN: 30 scenarios × 4 conditions × 3 models")
    print("=" * 60)
    
    # Build evidence for C1 for all pilot scenarios
    print("\nBuilding evidence bundles for C1...")
    pilot_evidence = {}
    for sc in pilot_scenarios:
        bundle = evidence_provider.build(sc)
        pilot_evidence[sc['scenario_id']] = bundle
    print(f"Built {len(pilot_evidence)} evidence bundles")
    
    # Results storage
    all_results = []
    run_id = f"pilot_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    results_dir = dirs['runs_dir'] / run_id
    results_dir.mkdir(parents=True, exist_ok=True)
    
    total_calls = len(pilot_scenarios) * len(CONDITIONS) * len(MODELS)
    call_count = 0
    
    for model_id, short_name in MODELS:
        print(f"\n{'='*60}")
        print(f"MODEL: {short_name} ({model_id})")
        print(f"{'='*60}")
        
        provider = NvidiaProvider(cfg)
        
        for sc in pilot_scenarios:
            sid = sc['scenario_id']
            evidence = pilot_evidence.get(sid)
            
            print(f"\nScenario {sid} ({sc['district']}, {sc['season_stratum']}, {sc['as_of_date']})")
            
            for condition in CONDITIONS:
                call_count += 1
                print(f"  Call {call_count}/{total_calls}: {condition}", end=" ")
                
                result = run_condition(provider, model_id, short_name, condition, sc, evidence)
                all_results.append(result)
                
                # Small delay between calls
                time.sleep(1)
        
        provider.close()
    
    # Save all results
    results_file = results_dir / "pilot_results.json"
    with results_file.open("w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nSaved {len(all_results)} results to {results_file}")
    
    # Quick summary
    print("\n" + "="*60)
    print("PILOT SUMMARY")
    print("="*60)
    
    by_model_cond = defaultdict(lambda: {"ok": 0, "err": 0, "latencies": [], "tokens_in": [], "tokens_out": [], "tools": [], "invalid_json": 0})
    
    for r in all_results:
        key = (r["model_short"], r["condition"])
        if r["error"]:
            by_model_cond[key]["err"] += 1
        else:
            by_model_cond[key]["ok"] += 1
            by_model_cond[key]["latencies"].append(r["latency_s"])
            by_model_cond[key]["tokens_in"].append(r["tokens_in"])
            by_model_cond[key]["tokens_out"].append(r["tokens_out"])
            by_model_cond[key]["tools"].append(r["tool_calls"])
            if not r["parsed"].get("valid_json", False):
                by_model_cond[key]["invalid_json"] += 1
    
    print(f"\n{'Model':<20} {'Cond':<5} {'OK':>3} {'Err':>3} {'MedianLat':>9} {'AvgTokIn':>8} {'AvgTokOut':>9} {'AvgTools':>8} {'InvJSON':>7}")
    print("-" * 90)
    for (model, cond), stats in sorted(by_model_cond.items()):
        if stats["ok"] > 0:
            lat = sorted(stats["latencies"])[len(stats["latencies"])//2]
            avg_in = sum(stats["tokens_in"]) / len(stats["tokens_in"])
            avg_out = sum(stats["tokens_out"]) / len(stats["tokens_out"])
            avg_tools = sum(stats["tools"]) / len(stats["tools"])
        else:
            lat = avg_in = avg_out = avg_tools = 0
        print(f"{model:<20} {cond:<5} {stats['ok']:>3} {stats['err']:>3} {lat:>8.1f}s {avg_in:>8.0f} {avg_out:>9.0f} {avg_tools:>8.1f} {stats['invalid_json']:>7}")
    
    # Estimate full run
    print("\n" + "="*60)
    print("FULL RUN ESTIMATE (based on pilot)")
    print("="*60)
    
    total_ok = sum(s["ok"] for s in by_model_cond.values())
    total_err = sum(s["err"] for s in by_model_cond.values())
    avg_lat = np.mean([np.median(s["latencies"]) for s in by_model_cond.values() if s["latencies"]])
    avg_tok_in = np.mean([np.mean(s["tokens_in"]) for s in by_model_cond.values() if s["tokens_in"]])
    avg_tok_out = np.mean([np.mean(s["tokens_out"]) for s in by_model_cond.values() if s["tokens_out"]])
    avg_tools = np.mean([np.mean(s["tools"]) for s in by_model_cond.values() if s["tools"]])
    
    print(f"Pilot success rate: {total_ok}/{total_ok+total_err} = {total_ok/(total_ok+total_err)*100:.1f}%")
    print(f"Avg latency: {avg_lat:.1f}s")
    print(f"Avg tokens in/out: {avg_tok_in:.0f}/{avg_tok_out:.0f}")
    print(f"Avg tool calls: {avg_tools:.1f}")
    print(f"Invalid JSON rate: {sum(s['invalid_json'] for s in by_model_cond.values())}/{total_ok} = {sum(s['invalid_json'] for s in by_model_cond.values())/max(1,total_ok)*100:.1f}%")
    
    # Full run projection
    primary_n = 500
    other_n = 150
    conditions = 4
    repeats = 1
    
    primary_calls = primary_n * conditions * repeats
    other_calls = other_n * conditions * repeats * 2  # 2 other models
    
    total_calls = primary_calls + other_calls
    est_hours = total_calls * avg_lat / 3600
    
    print(f"\nProjected full run:")
    print(f"  Primary (500×4): {primary_calls} calls")
    print(f"  Others (150×4×2): {other_calls} calls")
    print(f"  Total API calls: {total_calls}")
    print(f"  Estimated wall time: {est_hours:.1f} hours")
    print(f"  Estimated tokens: {total_calls * (avg_tok_in + avg_tok_out):.0f}")

if __name__ == "__main__":
    main()