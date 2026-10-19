#!/usr/bin/env python
"""Full LLM run progress monitor - shows real-time full run status."""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from collections import defaultdict

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from eval.common import load_config, config_dirs


def get_full_run_status(model_short: str = None):
    """Get current full run progress for a model."""
    runs_dir = Path('eval/runs')
    if not runs_dir.exists():
        return {'total_calls': 0, 'models': {}, 'run_dir': '', 'data_file': '', 'total_expected': 0}
    
    # Find latest run directory for the model
    if model_short:
        run_dirs = sorted([d for d in runs_dir.iterdir() 
                          if d.is_dir() and d.name.startswith(f'full_{model_short}_')], reverse=True)
    else:
        run_dirs = sorted([d for d in runs_dir.iterdir() 
                          if d.is_dir() and d.name.startswith('full_')], reverse=True)
    
    if not run_dirs:
        return {'total_calls': 0, 'models': {}, 'run_dir': '', 'data_file': '', 'total_expected': 0}
    
    latest_run = run_dirs[0]
    print(f"Monitoring run: {latest_run.name}")
    
    results_file = latest_run / "results.json"
    checkpoint_files = sorted(latest_run.glob("checkpoint_repeat_*.json"))
    
    # Use checkpoint if results.json doesn't exist yet
    data_file = results_file if results_file.exists() else (checkpoint_files[-1] if checkpoint_files else None)
    
    # Also check for checkpoint.json in the run directory
    if not data_file or not data_file.exists():
        checkpoint_json = latest_run / "checkpoint.json"
        if checkpoint_json.exists():
            data_file = checkpoint_json
    
    if not data_file or not data_file.exists():
        return {'total_calls': 0, 'models': {}, 'run_dir': str(latest_run), 'data_file': str(data_file) if data_file else '', 'total_expected': 0}
    
    with open(data_file) as f:
        results = json.load(f)
    
    # Determine total expected from config (not from directory name since it uses timestamps)
    total_expected = 500 * 4  # default: 500 scenarios × 4 conditions
    
    # Determine model from filename or first result
    if model_short is None and results:
        model_short = results[0].get('model_short', 'unknown')
    
    summary = defaultdict(lambda: defaultdict(lambda: {'ok': 0, 'err': 0, 'latencies': [], 'tools': [], 'tokens_out': [], 'invalid_json': 0, 'last_call': ''}))
    
    # Track order of calls for "what's calling now"
    call_order = []
    
    for r in results:
        model = r['model_short']
        cond = r['condition']
        sid = r.get('scenario_id', '')
        call_order.append(f"{sid} {cond}")
        if r['error']:
            summary[model][cond]['err'] += 1
        else:
            summary[model][cond]['ok'] += 1
            summary[model][cond]['latencies'].append(r['latency_s'])
            summary[model][cond]['tools'].append(r['tool_calls'])
            summary[model][cond]['tokens_out'].append(r['tokens_out'])
            if not r['parsed'].get('valid_json', False):
                summary[model][cond]['invalid_json'] += 1
        summary[model][cond]['last_call'] = f"{sid} {cond}"
    
    return {
        'run_dir': str(latest_run),
        'data_file': str(data_file),
        'total_calls': len(results),
        'total_expected': total_expected,
        'models': dict(summary),
        'call_order': call_order,
        'timestamp': datetime.now().isoformat()
    }


def render_bar(percent: float, width: int = 40) -> str:
    """Render a progress bar."""
    filled = int(width * percent / 100)
    bar = "#" * filled + "-" * (width - filled)
    return f"[{bar}] {percent:.1f}%"


def print_status(model_short: str = None):
    """Print formatted full run status."""
    status = get_full_run_status(model_short)
    
    if status['total_calls'] == 0:
        print("No full run data found yet.")
        return
    
    total_done = status['total_calls']
    total_expected = status.get('total_expected', total_done)
    if total_expected < total_done:
        total_expected = total_done
    pct = (total_done / total_expected) * 100 if total_expected > 0 else 0
    remaining = max(0, total_expected - total_done)
    
    print(f"\n{'='*80}")
    print(f"FULL LLM RUN PROGRESS - {status['timestamp'][:19].replace('T', ' ')}")
    print(f"Run dir: {status['run_dir']}")
    print(f"Data file: {status['data_file']}")
    print(f"{'='*80}")
    print(f"Progress: {render_bar(pct)}  ({total_done}/{total_expected} calls, {remaining} remaining)")
    print()
    
    for model, info in status['models'].items():
        model_done = sum(c['ok'] + c['err'] for c in info.values())
        print(f"\n{model} ({model_done} calls done):")
        
        # Show what's currently calling (last call)
        last_calls = [(cond, info[cond].get('last_call', '')) for cond in info if info[cond].get('last_call')]
        if last_calls:
            last_cond, last_sid = last_calls[-1]
            print(f"  Currently: {last_sid} ({last_cond})")
        
        print(f"  {'Condition':<5} {'OK':>4} {'Err':>4} {'MedianLat':>10} {'AvgTokOut':>10} {'AvgTools':>8} {'InvJSON':>7} {'Rate':>6}")
        print(f"  {'-'*60}")
        for cond in ['C0', 'C0b', 'C1', 'C2']:
            if cond in info:
                c = info[cond]
                ok = c['ok']
                err = c['err']
                if ok > 0:
                    lats = sorted(c['latencies'])
                    lat = lats[len(lats)//2]
                    avg_out = sum(c['tokens_out']) / len(c['tokens_out'])
                    avg_tools = sum(c['tools']) / len(c['tools'])
                else:
                    lat = avg_out = avg_tools = 0
                inv = c['invalid_json']
                rate = inv/max(1,ok)*100 if ok else 0
                print(f"  {cond:<5} {ok:>4} {err:>4} {lat:>9.1f}s {avg_out:>10.0f} {avg_tools:>8.1f} {inv:>7} ({rate:>5.1f}%)")
            else:
                print(f"  {cond:<5} {'0':>4} {'0':>4} {'N/A':>10} {'N/A':>10} {'N/A':>8} {'0':>7} ({'0.0%':>6})")
        
        ok_total = sum(c['ok'] for c in info.values())
        err_total = sum(c['err'] for c in info.values())
        inv_total = sum(c['invalid_json'] for c in info.values())
        print(f"  {'TOTAL':<5} {ok_total:>4} {err_total:>4} {'':>10} {'':>10} {'':>8} {inv_total:>7} ({inv_total/max(1,ok_total)*100:>5.1f}%)")
    
    # Overall progress bar
    print(f"\nOverall: {render_bar(pct)}  {total_done}/{total_expected} ({remaining} remaining)")
    print(f"{'='*80}")


def watch(model_short: str = None, interval: int = 15):
    """Watch full run progress continuously."""
    try:
        while True:
            os.system('cls' if os.name == 'nt' else 'clear')
            print_status(model_short)
            print(f"\nRefreshing in {interval}s... (Ctrl+C to stop)")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nStopped watching")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', '-m', help='Model short name (e.g., nemotron-3-ultra)')
    parser.add_argument('--watch', '-w', action='store_true', help='Watch mode')
    parser.add_argument('--interval', '-i', type=int, default=15, help='Watch interval (seconds)')
    args = parser.parse_args()
    
    if args.watch:
        watch(args.model, args.interval)
    else:
        print_status(args.model)