"""Fast parallel retry runner with progress tracking."""

import json
import os
import sys
import time
import hashlib
import threading
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from eval.common import load_config, ensure_dirs, config_dirs, write_json, read_jsonl
from eval.scenarios import generate
from eval.llm.nvidia_provider import NvidiaProvider
from eval.llm.prompts import prompt_c0, prompt_c0b, prompt_c1, prompt_c2, parse_output
from eval.evidence import EvidenceProvider


def cache_key(model: str, condition: str, prompt: str, scenario_id: str, repeat: int) -> str:
    payload = "\u241f".join([model, condition, prompt, scenario_id, str(repeat)])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_prompt(condition: str, scenario: dict, evidence: dict = None) -> str:
    if condition == "C0":
        return prompt_c0(scenario)
    elif condition == "C0b":
        return prompt_c0b(scenario)
    elif condition == "C1":
        return prompt_c1(scenario, evidence)
    elif condition == "C2":
        return prompt_c2(scenario)
    raise ValueError(f"Unknown condition: {condition}")


def run_fast_retry(model_id: str, max_workers: int = 4, max_retries: int = 2):
    """Fast parallel retry with live progress."""
    
    cfg = load_config()
    ensure_dirs(cfg)
    dirs = config_dirs(cfg)
    
    # Load the latest run with most results
    runs_dir = dirs['runs_dir']
    run_dirs = []
    for d in runs_dir.iterdir():
        if d.is_dir() and d.name.startswith(f"full_nemotron-3-ultra_"):
            results_file = d / "results.json"
            if results_file.exists():
                try:
                    with results_file.open() as f:
                        data = json.load(f)
                    if len(data) >= 100:
                        run_dirs.append((d, len(data)))
                except:
                    pass
    
    if not run_dirs:
        print("No previous runs found")
        return
    
    run_dirs.sort(key=lambda x: x[1], reverse=True)
    latest_run = run_dirs[0][0]
    final_file = latest_run / "results.json"
    
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
    
    print(f"Found {len(failed)} failed calls to retry")
    print(f"Using {max_workers} workers, {2} retries each")
    print("=" * 60)
    
    # Build evidence only for failed scenarios
    cfg = load_config()
    ensure_dirs(cfg)
    dirs = config_dirs(cfg)
    
    # Load LLM subset to get scenario details
    llm_subset = read_jsonl(dirs['llm_subset_path'])
    scenarios = llm_subset[:500]  # full subset
    scenario_map = {s['scenario_id']: s for s in scenarios}
    
    evidence_provider = EvidenceProvider(cfg)
    failed_scenario_ids = set(key[0] for key in failed.keys())
    print(f"Building evidence for {len(failed_scenario_ids)} failed scenarios...")
    evidence = {}
    for sid in failed_scenario_ids:
        sc = scenario_map[sid]
        evidence[sid] = evidence_provider.build(sc)
    print("Evidence built.")
    
    # Setup provider
    cfg["model"]["nvidia"]["name"] = "nvidia/nemotron-3-ultra-550b-a55b"
    provider = NvidiaProvider(cfg)
    
    # Thread-safe progress tracking
    progress_lock = threading.Lock()
    stats = {
        'completed': 0,
        'success': 0,
        'failed': 0,
        'start_time': time.time(),
        'by_condition': Counter(),
        'recent': []
    }
    
    def update_progress(result: dict, condition: str, success: bool):
        with progress_lock:
            stats['completed'] += 1
            if success:
                stats['success'] += 1
            else:
                stats['failed'] += 1
                stats['by_condition'][condition] += 1
            stats['recent'].append((result['scenario_id'], condition, 'OK' if success else 'FAIL', result.get('latency_s', 0)))
            if len(stats['recent']) > 20:
                stats['recent'].pop(0)
    
    def print_progress():
        with progress_lock:
            completed = stats['completed']
            success = stats['success']
            failed = stats['failed']
            elapsed = time.time() - stats['start_time']
            rate = stats['success'] / elapsed * 60 if elapsed > 0 else 0
            pct = (completed / total_retries) * 100
            bar = "█" * int(pct/5) + "░" * (20 - int(pct/5))
            print(f"\rProgress: [{'█' * int(pct/5) + '░' * (20 - int(pct/5))}] {completed}/{total_retries} ({pct:.1f}%) | "
                  f"Success: {success} | Failed: {failed} | Rate: {rate:.1f}/min | "
                  f"By cond: {dict(stats['by_condition'])}", end="", flush=True)
    
    # Build retry tasks
    tasks = []
    for key in failed:
        for attempt in range(2):  # max 2 retries
            tasks.append((key, attempt + 1))
    
    total_retries = len(tasks)
    print(f"Total retries: {total_retries} ({len(failed)} failed × 2 retries)")
    print(f"Using {max_workers} workers")
    print("=" * 60)
    
    def retry_single(task):
        (scenario_id, condition, repeat), attempt = task
        sc = next(s for s in scenarios if s['scenario_id'] == scenario_id)
        ev = evidence.get(scenario_id, {})
        
        prompt = build_prompt(condition, sc, ev)
        use_mcp = (condition == "C2")
        cache_key_str = cache_key("nvidia/nemotron-3-ultra-550b-a55b", condition, prompt, scenario_id, 0)
        
        # Run with retries
        for retry in range(2):
            try:
                provider = NvidiaProvider(load_config())
                provider.cache_dir = Path("eval/cache/llm/nemotron-3-ultra")
                result = provider.run(prompt, use_mcp=use_mcp)
                
                if result and not result.get("error"):
                    return {
                        'key': (scenario_id, condition, 0),
                        'attempt': attempt,
                        'retry': retry + 1,
                        'result': {
                            'scenario_id': scenario_id,
                            'condition': condition,
                            'repeat': 0,
                            'text': result.text,
                            'tokens_in': result.tokens_in,
                            'tokens_out': result.tokens_out,
                            'reasoning_tokens': result.reasoning_tokens,
                            'latency_s': result.latency_s,
                            'tool_calls': result.tool_calls,
                            'error': None,
                            'timestamp': datetime.now(timezone.utc).isoformat(),
                            'parsed': parse_output(result.text),
                        }
                    }
            except Exception as e:
                if retry == 1:
                    return {
                        'key': (scenario_id, condition, 0),
                        'attempt': attempt,
                        'retry': retry + 1,
                        'result': {
                            'scenario_id': scenario_id,
                            'condition': condition,
                            'repeat': 0,
                            'text': '',
                            'tokens_in': 0, 'tokens_out': 0, 'reasoning_tokens': 0,
                            'latency_s': 0, 'tool_calls': 0,
                            'error': str(e),
                            'timestamp': datetime.now(timezone.utc).isoformat(),
                            'parsed': {'valid_json': False},
                        }
                    }
            time.sleep(1)  # Small delay between retries
        
        return None
    
    # Run with progress
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(retry_single, task): task for task in tasks}
        
        for future in as_completed(futures):
            result = future.result()
            if result:
                key = result['key']
                cond = key[1]
                success = result['result']['error'] is None
                # Update original results
                # (simplified - just track stats)
                update_progress(result['result'], cond, success)
                print_progress()
            else:
                update_progress({'condition': key[1]}, key[1], False)
                print_progress()
    
    print(f"\n\nRetry complete!")
    print(f"Final: Success={stats['success']}, Failed={stats['failed']}")
    print(f"By condition: {dict(stats['by_condition'])}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=4, help="Max concurrent workers")
    parser.add_argument("--retries", type=int, default=2, help="Max retries per failed call")
    args = parser.parse_args()
    
    run_fast_retry("nvidia/nemotron-3-ultra-550b-a55b", max_workers=args.workers)