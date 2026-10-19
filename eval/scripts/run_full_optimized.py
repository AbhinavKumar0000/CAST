"""Optimized full LLM runner with concurrent execution, auto-retry, and resumable checkpoints."""

import json
import os
import sys
import time
import hashlib
import threading
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from eval.common import load_config, ensure_dirs, config_dirs, write_json, read_jsonl, ResultMeta
from eval.scenarios import generate
from eval.llm.nvidia_provider import NvidiaProvider
from eval.llm.prompts import prompt_c0, prompt_c0b, prompt_c1, prompt_c2, parse_output
from eval.evidence import EvidenceProvider

MODEL_SHORT = {
    "nvidia/nemotron-3-ultra-550b-a55b": "nemotron-3-ultra",
    "z-ai/glm-5.3": "glm-5.3",
    "meta/llama-3.2-11b-vision-instruct": "llama-3.2-11b",
}


def cache_key(model: str, condition: str, prompt: str, scenario_id: str, repeat: int) -> str:
    payload = "\u241f".join([model, condition, prompt, scenario_id, str(repeat)])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class OptimizedRunner:
    """High-throughput runner with concurrent execution and granular checkpoints."""
    
    def __init__(self, cfg: dict, model_id: str, scenarios: list, repeats: int = 1,
                 max_workers: int = 4, checkpoint_every: int = 10, build_evidence: bool = True):
        self.cfg = cfg
        self.model_id = model_id
        self.short_name = MODEL_SHORT[model_id]
        self.scenarios = scenarios
        self.repeats = repeats
        self.max_workers = max_workers
        self.checkpoint_every = checkpoint_every
        
        ensure_dirs(cfg)
        dirs = config_dirs(cfg)
        
        # Override model
        cfg["model"]["nvidia"]["name"] = model_id
        cfg["model"]["name"] = model_id
        
        # Setup provider
        self.provider = NvidiaProvider(cfg)
        self.provider.cache_dir = dirs['cache_dir'] / "llm" / self.short_name
        self.provider.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Evidence provider
        self.evidence_provider = EvidenceProvider(cfg)
        
        # Results directory
        run_id = f"full_{self.short_name}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        self.results_dir = dirs['runs_dir'] / run_id
        self.results_dir.mkdir(parents=True, exist_ok=True)
        
        # Checkpoint files
        self.checkpoint_file = self.results_dir / "checkpoint.json"
        self.final_file = self.results_dir / "results.json"
        
        # Build evidence for C1 (only if not in retry mode)
        self.evidence = {}
        if build_evidence:
            print("Building evidence bundles...")
            for sc in scenarios:
                self.evidence[sc['scenario_id']] = self.evidence_provider.build(sc)
            print(f"Built {len(self.evidence)} evidence bundles")
        else:
            print("Skipping evidence build (retry mode)")
        
        # Load existing checkpoint
        self.results = self.load_checkpoint()
        self.completed_keys = set()
        for r in self.results:
            key = (r["scenario_id"], r["condition"], r.get("repeat", 0))
            self.completed_keys.add(key)
        
        self.lock = threading.Lock()
        self.call_count = 0
        self.total_calls = len(scenarios) * repeats * 4
    
    def load_checkpoint(self) -> list:
        if self.checkpoint_file.exists():
            with self.checkpoint_file.open() as f:
                data = json.load(f)
            print(f"Resumed from checkpoint: {len(data)} calls completed")
            return data
        return []
    
    def save_checkpoint(self):
        with self.lock:
            with self.checkpoint_file.open("w") as f:
                json.dump(self.results, f, indent=2)
    
    def build_prompt(self, condition: str, scenario: dict, evidence: dict = None) -> str:
        if condition == "C0":
            return prompt_c0(scenario)
        elif condition == "C0b":
            return prompt_c0b(scenario)
        elif condition == "C1":
            return prompt_c1(scenario, evidence)
        elif condition == "C2":
            return prompt_c2(scenario)
        raise ValueError(f"Unknown condition: {condition}")
    
    def run_single(self, scenario: dict, condition: str, repeat: int, force_refresh: bool = False) -> Optional[dict]:
        """Run a single scenario-condition-repeat combination."""
        key = (scenario['scenario_id'], condition, repeat)
        
        # Check if already completed (unless forcing refresh)
        if key in self.completed_keys and not force_refresh:
            return None
        
        evidence = self.evidence.get(scenario['scenario_id'])
        prompt = self.build_prompt(condition, scenario, evidence)
        use_mcp = (condition == "C2")
        
        # Check cache (unless forcing refresh)
        cache_key_str = cache_key(self.model_id, condition, prompt, scenario['scenario_id'], repeat)
        cache_path = self.provider.cache_dir / f"{cache_key_str}.json"
        
        if cache_path.exists() and not force_refresh:
            with cache_path.open() as f:
                cached = json.load(f)
            # Verify it's for this repeat
            if cached.get("repeat", 0) == repeat:
                with self.lock:
                    self.completed_keys.add(key)
                return cached
        
        # Run with retries
        max_retries = 3
        for attempt in range(max_retries):
            try:
                result = self.provider.run(prompt, agent="full_run", use_mcp=use_mcp)
                
                output = {
                    "model": self.model_id,
                    "model_short": self.short_name,
                    "condition": condition,
                    "scenario_id": scenario['scenario_id'],
                    "repeat": repeat,
                    "prompt_hash": cache_key_str,
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
                
                # Save to cache
                with cache_path.open("w") as f:
                    json.dump(output, f)
                
                return output
                
            except Exception as e:
                if attempt < max_retries - 1:
                    wait = 2 ** attempt + 0.5 * (attempt + 1)
                    time.sleep(wait)
                    continue
                # Final failure
                output = {
                    "model": self.model_id,
                    "model_short": self.short_name,
                    "condition": condition,
                    "scenario_id": scenario['scenario_id'],
                    "repeat": repeat,
                    "prompt_hash": cache_key_str,
                    "text": "",
                    "tokens_in": 0,
                    "tokens_out": 0,
                    "reasoning_tokens": 0,
                    "latency_s": 0,
                    "tool_calls": 0,
                    "error": str(e),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "parsed": {"valid_json": False},
                }
                return output
        
        return None
    
    def run_batch(self, batch: list) -> list:
        """Run a batch of (scenario, condition, repeat) tuples concurrently."""
        futures = {}
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            for scenario, condition, repeat in batch:
                future = executor.submit(self.run_single, scenario, condition, repeat)
                futures[future] = (scenario, condition, repeat)
            
            results = []
            for future in as_completed(futures):
                result = future.result()
                if result:
                    results.append(result)
                    with self.lock:
                        self.results.append(result)
                        self.completed_keys.add((result["scenario_id"], result["condition"], result.get("repeat", 0)))
                        self.call_count += 1
                        
                        # Progress
                        if self.call_count % 1 == 0:
                            pct = (len(self.completed_keys) / self.total_calls) * 100
                            print(f"  [{len(self.completed_keys)}/{self.total_calls}] {result['scenario_id']} {result['condition']} r{result.get('repeat',0)} "
                                  f"OK={result['error'] is None} ({result['latency_s']:.1f}s, tok={result['tokens_out']}, tools={result['tool_calls']}) "
                                  f"json={'Y' if result['parsed'].get('valid_json') else 'N'}")
                
                # Checkpoint periodically
                if self.call_count % self.checkpoint_every == 0:
                    self.save_checkpoint()
        
        return results
    
    def run(self):
        """Run all scenarios with all conditions and repeats."""
        print(f"Full LLM run: {self.short_name} ({self.model_id})")
        print(f"Scenarios: {len(self.scenarios)} × {self.repeats} repeats × 4 conditions = {self.total_calls} calls")
        print(f"Concurrency: {self.max_workers} workers")
        print(f"Already completed: {len(self.completed_keys)}")
        print(f"Remaining: {self.total_calls - len(self.completed_keys)}")
        print("=" * 60)
        
        # Build task list
        tasks = []
        for repeat in range(self.repeats):
            for scenario in self.scenarios:
                for condition in ["C0", "C0b", "C1", "C2"]:
                    key = (scenario['scenario_id'], condition, repeat)
                    if key not in self.completed_keys:
                        tasks.append((scenario, condition, repeat))
        
        print(f"Tasks to execute: {len(tasks)}")
        
        # Process in batches
        batch_size = self.max_workers * 4
        for i in range(0, len(tasks), batch_size):
            batch = tasks[i:i + batch_size]
            print(f"\nBatch {i//batch_size + 1}/{(len(tasks)-1)//batch_size + 1} ({len(batch)} tasks)")
            self.run_batch(batch)
        
        # Final save
        final_file = self.results_dir / "results.json"
        with final_file.open("w") as f:
            json.dump(self.results, f, indent=2)
        print(f"\nFinal results saved: {final_file}")
        self.provider.close()
        
        # Summary
        self.print_summary()
    
    def print_summary(self):
        by_cond = defaultdict(lambda: {"ok": 0, "err": 0, "latencies": [], "tools": [], "tokens_out": [], "invalid_json": 0})
        for r in self.results:
            key = (r["model_short"], r["condition"])
            if r.get("error"):
                by_cond[key]["err"] += 1
            else:
                by_cond[key]["ok"] += 1
                by_cond[key]["latencies"].append(r["latency_s"])
                by_cond[key]["tools"].append(r["tool_calls"])
                by_cond[key]["tokens_out"].append(r["tokens_out"])
                if not r.get("parsed", {}).get("valid_json", False):
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
        
        print(f"\nRun complete! Results in: {self.results_dir}")
    
    def retry_failed(self, max_retries: int = 2):
        """Retry failed calls from the run with the most results."""
        # Find the run directory with the most results for this model
        runs_dir = self.results_dir.parent
        run_dirs = []
        for d in runs_dir.iterdir():
            if d.is_dir() and d.name.startswith(f"full_{self.short_name}_"):
                results_file = d / "results.json"
                if results_file.exists():
                    try:
                        with results_file.open() as f:
                            data = json.load(f)
                        if len(data) >= 100:  # Only consider substantial runs
                            run_dirs.append((d, len(data)))
                    except:
                        pass
        
        if not run_dirs:
            print("No previous run directories with substantial results found for this model")
            return
        
        # Sort by number of results (descending)
        run_dirs.sort(key=lambda x: x[1], reverse=True)
        latest_run = run_dirs[0][0]
        num_results = run_dirs[0][1]
        
        checkpoint_file = latest_run / "checkpoint.json"
        final_file = latest_run / "results.json"
        
        data_file = final_file if final_file.exists() else (latest_run / "checkpoint.json")
        if not data_file.exists():
            print(f"No results data found in {latest_run}")
            return
        
        print(f"Loading results from: {latest_run.name} ({num_results} calls)")
        
        with final_file.open() as f:
            results = json.load(f)
        
        # Find failed calls
        failed = {}
        for r in results:
            if r.get("error"):
                key = (r["scenario_id"], r["condition"], r.get("repeat", 0))
                if key not in failed:
                    failed[key] = r
        
        if not failed:
            print("No failed calls to retry")
            return
        
        print(f"\n{'='*60}")
        print(f"RETRYING {len(failed)} FAILED CALLS (max {max_retries} retries each)")
        print(f"{'='*60}")
        
        # Build evidence only for failed scenarios
        failed_scenario_ids = set(key[0] for key in failed.keys())
        print(f"Building evidence for {len(failed_scenario_ids)} failed scenarios...")
        for sid in failed_scenario_ids:
            sc = next(s for s in self.scenarios if s['scenario_id'] == sid)
            self.evidence[sid] = self.evidence_provider.build(sc)
        print("Evidence built.")
        
        retry_count = 0
        for key, failed_result in failed.items():
            scenario_id, condition, repeat = key
            # Remove from completed_keys so run_single will actually retry
            self.completed_keys.discard(key)
            sc = next(s for s in self.scenarios if s['scenario_id'] == scenario_id)
            evidence = self.evidence.get(scenario_id)
            
            for attempt in range(max_retries):
                print(f"  Retry {attempt+1}/{max_retries}: {scenario_id} {condition} r{repeat}")
                result = self.run_single(sc, condition, repeat, force_refresh=True)
                if result and not result.get("error"):
                    print(f"    SUCCESS on retry {attempt+1}")
                    retry_count += 1
                    # Update the results list
                    for i, r in enumerate(results):
                        if (r["scenario_id"], r["condition"], r.get("repeat", 0)) == key:
                            results[i] = result
                            break
                    break
                else:
                    print(f"    FAILED: {result.get('error', 'Unknown error')}")
                    if attempt == max_retries - 1:
                        print(f"    Gave up after {max_retries} retries")
                time.sleep(2)  # Small delay between retries
        
        # Save updated results back to the original run directory
        with final_file.open("w") as f:
            json.dump(results, f, indent=2)
        print(f"\nUpdated results saved with {retry_count} retries succeeded: {final_file}")
        self.print_summary()


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
    parser.add_argument("--workers", type=int, default=4,
                        help="Max concurrent workers (default: 4)")
    parser.add_argument("--checkpoint-every", type=int, default=10,
                        help="Checkpoint every N calls (default: 10)")
    parser.add_argument("--retry-failed", action="store_true",
                        help="Retry failed calls from previous run")
    args = parser.parse_args()
    
    cfg = load_config()
    ensure_dirs(cfg)
    dirs = config_dirs(cfg)
    
    # Load LLM subset
    llm_subset = read_jsonl(dirs['llm_subset_path'])
    if args.consistency:
        scenarios = llm_subset[:100]
        repeats = 3
    else:
        scenarios = llm_subset[:args.scenarios] if args.scenarios else llm_subset
        repeats = args.repeat
    
    runner = OptimizedRunner(
        cfg=cfg,
        model_id=args.model,
        scenarios=scenarios,
        repeats=repeats,
        max_workers=args.workers,
        checkpoint_every=args.checkpoint_every,
        build_evidence=not args.retry_failed,
    )
    
    if args.retry_failed:
        runner.retry_failed()
    else:
        runner.run()


if __name__ == "__main__":
    main()