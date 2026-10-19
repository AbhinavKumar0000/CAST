"""Full LLM evaluation runner - runs all conditions for a model on the LLM subset."""

import json
import os
import sys
import time
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from eval.common import load_config, ensure_dirs, config_dirs, write_json, read_jsonl, ResultMeta
from eval.scenarios import generate
from eval.llm.nvidia_provider import NvidiaProvider
from eval.llm.prompts import prompt_c0, prompt_c0b, prompt_c1, prompt_c2, parse_output, normalize_crop
from eval.evidence import EvidenceProvider

# Model short name mapping
MODEL_SHORT = {
    "nvidia/nemotron-3-ultra-550b-a55b": "nemotron-3-ultra",
    "z-ai/glm-5.3": "glm-5.3",
    "meta/llama-3.2-11b-vision-instruct": "llama-3.2-11b",
}


def cache_key(model: str, condition: str, prompt: str, scenario_id: str, repeat: int) -> str:
    payload = "\u241f".join([model, condition, prompt, scenario_id, str(repeat)])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_cache(cache_dir: Path, key: str):
    path = cache_dir / f"{key}.json"
    if path.exists():
        with path.open() as f:
            return json.load(f)
    return None


def save_cache(cache_dir: Path, key: str, data: dict):
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
    cached = load_cache(provider.cache_dir, key)
    if cached:
        return cached
    
    result = provider.run(prompt, agent="full_run", use_mcp=use_mcp)
    
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
    
    save_cache(provider.cache_dir, key, output)
    return output


def retry_failed(provider: NvidiaProvider, scenarios: list[dict], evidence: dict, 
                results_dir: Path, max_retries: int = 2) -> list[dict]:
    """Retry failed scenario-condition pairs."""
    results_file = results_dir / "results.json"
    if not results_file.exists():
        return []
    
    with results_file.open() as f:
        results = json.load(f)
    
    # Find failed calls grouped by (scenario_id, condition)
    failed = {}
    for r in results:
        if r.get("error"):
            key = (r["scenario_id"], r["condition"])
            if key not in failed:
                failed[key] = []
            failed[key].append(r)
    
    if not failed:
        print("No failed calls to retry")
        return []
    
    print(f"\n{'='*60}")
    print(f"RETRYING {len(failed)} FAILED SCENARIO-CONDITION PAIRS")
    print(f"{'='*60}")
    
    retry_results = []
    for (scenario_id, condition), failures in failed.items():
        sc = next(s for s in scenarios if s['scenario_id'] == scenario_id)
        ev = evidence.get(scenario_id)
        
        for attempt in range(max_retries):
            print(f"  Retry {attempt+1}/{max_retries}: {scenario_id} {condition}")
            result = run_condition(provider, "nvidia/nemotron-3-ultra-550b-a55b", "nemotron-3-ultra", condition, sc, ev)
            if not result.get("error"):
                print(f"    SUCCESS on retry {attempt+1}")
                retry_results.append(result)
                break
            else:
                print(f"    FAILED: {result['error']}")
                if attempt == max_retries - 1:
                    retry_results.append(result)
                time.sleep(5)
    
    return retry_results


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, choices=list(MODEL_SHORT.keys()),
                        help="Model to evaluate")
    parser.add_argument("--scenarios", type=int, default=None,
                        help="Number of scenarios (default: all LLM subset)")
    parser.add_argument("--repeat", type=int, default=1,
                        help="Repeats per scenario for consistency")
    parser.add_argument("--consistency", action="store_true",
                        help="Run consistency test (100 scenarios × 3 repeats)")
    parser.add_argument("--retry-failed", action="store_true",
                        help="After main run, retry failed calls")
    args = parser.parse_args()
    
    model_id = args.model
    short_name = MODEL_SHORT[model_id]
    
    cfg = load_config()
    ensure_dirs(cfg)
    dirs = config_dirs(cfg)
    
    # Override model in config
    cfg["model"]["nvidia"]["name"] = model_id
    cfg["model"]["name"] = model_id
    
    # Load LLM subset
    llm_subset = read_jsonl(dirs['llm_subset_path'])
    if args.consistency:
        # Use first 100 scenarios for consistency test
        scenarios = llm_subset[:100]
        repeats = 3
    else:
        scenarios = llm_subset[:args.scenarios] if args.scenarios else llm_subset
        repeats = args.repeat
    
    print(f"Full LLM run: {short_name} ({model_id})")
    print(f"Scenarios: {len(scenarios)} × {repeats} repeats × 4 conditions = {len(scenarios) * repeats * 4} calls")
    
    # Evidence provider for C1
    evidence_provider = EvidenceProvider(cfg)
    pilot_evidence = {}
    for sc in scenarios:
        bundle = evidence_provider.build(sc)
        pilot_evidence[sc['scenario_id']] = bundle
    
    # Setup provider with cache
    provider = NvidiaProvider(cfg)
    provider.cache_dir = dirs['cache_dir'] / "llm" / short_name
    provider.cache_dir.mkdir(parents=True, exist_ok=True)
    
    # Results storage
    run_id = f"full_{short_name}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    results_dir = dirs['runs_dir'] / run_id
    results_dir.mkdir(parents=True, exist_ok=True)
    
    all_results = []
    total_calls = len(scenarios) * repeats * 4
    call_count = 0
    
    for repeat in range(repeats):
        print(f"\n{'='*60}")
        print(f"REPEAT {repeat + 1}/{repeats}")
        print(f"{'='*60}")
        
        for sc in scenarios:
            sid = sc['scenario_id']
            evidence = pilot_evidence.get(sid)
            
            for condition in ["C0", "C0b", "C1", "C2"]:
                call_count += 1
                print(f"  [{call_count}/{total_calls}] {sid} {condition}", end=" ")
                
                result = run_condition(provider, model_id, short_name, condition, sc, evidence)
                all_results.append(result)
                
                if result["error"]:
                    print(f"ERROR: {result['error']}")
                else:
                    print(f"OK ({result['latency_s']:.1f}s, tok={result['tokens_out']}, tools={result['tool_calls']})"
                          f" json={'Y' if result['parsed'].get('valid_json') else 'N'}")
                
                # Small delay between calls
                time.sleep(0.5)
        
        # Checkpoint after each repeat
        checkpoint_file = results_dir / f"checkpoint_repeat_{repeat}.json"
        with checkpoint_file.open("w") as f:
            json.dump(all_results, f, indent=2)
        print(f"Checkpoint saved: {checkpoint_file}")
    
    # Final save
    final_file = results_dir / "results.json"
    with final_file.open("w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nFinal results saved: {final_file}")
    
    # Retry failed if requested
    if args.retry_failed:
        retry_results = retry_failed(provider, scenarios, pilot_evidence, results_dir)
        if retry_results:
            # Merge retry results (replace failed with successful retries)
            retry_map = {}
            for r in retry_results:
                if not r.get("error"):
                    key = (r["scenario_id"], r["condition"])
                    retry_map[key] = r
            
            for i, r in enumerate(all_results):
                key = (r["scenario_id"], r["condition"])
                if r.get("error") and key in retry_map:
                    all_results[i] = retry_map[key]
            
            # Save updated results
            with final_file.open("w") as f:
                json.dump(all_results, f, indent=2)
            print(f"Updated results saved with retries: {final_file}")
    
    # Quick summary
    print("\n" + "="*60)
    print("RUN SUMMARY")
    print("="*60)
    
    by_cond = defaultdict(lambda: {"ok": 0, "err": 0, "latencies": [], "tools": [], "tokens_out": [], "invalid_json": 0})
    for r in all_results:
        key = (r["model_short"], r["condition"])
        if r["error"]:
            by_cond[key]["err"] += 1
        else:
            by_cond[key]["ok"] += 1
            by_cond[key]["latencies"].append(r["latency_s"])
            by_cond[key]["tools"].append(r["tool_calls"])
            by_cond[key]["tokens_out"].append(r["tokens_out"])
            if not r["parsed"].get("valid_json", False):
                by_cond[key]["invalid_json"] += 1
    
    print(f"\n{'Model':<20} {'Cond':<5} {'OK':>3} {'Err':>3} {'MedianLat':>9} {'AvgTokOut':>9} {'AvgTools':>8} {'InvJSON':>7}")
    print("-" * 80)
    for (model, cond), stats in sorted(by_cond.items()):
        if stats["ok"] > 0:
            lats = sorted(stats["latencies"])
            lat = lats[len(lats)//2]
            avg_out = sum(stats["tokens_out"]) / len(stats["tokens_out"])
            avg_tools = sum(stats["tools"]) / len(stats["tools"])
        else:
            lat = avg_out = avg_tools = 0
        print(f"{model:<20} {cond:<5} {stats['ok']:>3} {stats['err']:>3} {lat:>8.1f}s {avg_out:>9.0f} {avg_tools:>8.1f} {stats['invalid_json']:>7}")
    
    provider.close()
    print(f"\nRun complete! Results in: {results_dir}")


if __name__ == "__main__":
    main()