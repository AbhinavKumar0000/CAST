#!/usr/bin/env python
"""Pilot progress monitor - shows real-time pilot status."""

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


def get_pilot_status():
    """Get current pilot progress."""
    cache_dir = Path('eval/cache/pilot')
    if not cache_dir.exists():
        return {'total_cached': 0, 'models': {}}
    
    results = []
    for f in cache_dir.glob('*.json'):
        with open(f) as fp:
            data = json.load(fp)
        results.append(data)
    
    summary = defaultdict(lambda: defaultdict(lambda: {'ok': 0, 'err': 0, 'invalid_json': 0}))
    
    for r in results:
        model = r['model_short']
        cond = r['condition']
        if r['error']:
            summary[model][cond]['err'] += 1
        else:
            summary[model][cond]['ok'] += 1
            if not r['parsed'].get('valid_json', False):
                summary[model][cond]['invalid_json'] += 1
    
    # Model order
    model_order = ['nemotron-3-ultra', 'glm-5.3', 'llama-3.2-11b']
    
    output = {}
    for model in model_order:
        if model in summary:
            output[model] = {
                'total': sum(c['ok'] + c['err'] for c in summary[model].values()),
                'conditions': dict(summary[model])
            }
    
    return {
        'total_cached': len(results),
        'models': output,
        'timestamp': datetime.now().isoformat()
    }


def print_status():
    """Print formatted pilot status."""
    status = get_pilot_status()
    
    print(f"\n{'='*70}")
    print(f"PILOT PROGRESS MONITOR - {status['timestamp'][:19].replace('T', ' ')}")
    print(f"{'='*70}")
    print(f"Total cached calls: {status['total_cached']} / 360 (3 models × 120 each)")
    print(f"Progress: {status['total_cached']/360*100:.1f}%")
    print()
    
    for model, info in status['models'].items():
        total = info['total']
        print(f"\n{model} ({total}/120 calls):")
        print(f"  {'Condition':<5} {'OK':>3} {'Err':>3} {'InvJSON':>7}")
        print(f"  {'-'*22}")
        for cond in ['C0', 'C0b', 'C1', 'C2']:
            if cond in info['conditions']:
                c = info['conditions'][cond]
                ok = c['ok']
                err = c['err']
                inv = c['invalid_json']
                rate = inv/max(1,ok)*100 if ok else 0
                print(f"  {cond:<5} {ok:>3} {err:>3} {inv:>7} ({rate:.0f}%)")
            else:
                print(f"  {cond:<5} {'0':>3} {'0':>3} {'0':>7}")
        
        inv_total = sum(c['invalid_json'] for c in info['conditions'].values())
        ok_total = sum(c['ok'] for c in info['conditions'].values())
        print(f"  {'TOTAL':<5} {ok_total:>3} {'0':>3} {inv_total:>7} ({inv_total/max(1,ok_total)*100:.1f}%)")
    
    # Next actions
    print(f"\n{'='*70}")
    if status['total_cached'] == 0:
        print("NEXT: nemotron-3-ultra pilot starting...")
    elif status['total_cached'] < 120:
        remaining = 120 - sum(m['total'] for m in status['models'].values() if list(status['models'].keys())[0] == 'nemotron-3-ultra')
        print(f"NEXT: Complete nemotron-3-ultra pilot ({120 - info['total']} remaining)")
    elif status['total_cached'] < 240:
        print("NEXT: Start GLM-5.3 pilot (120 calls)")
    elif status['total_cached'] < 360:
        print("NEXT: Start Llama-3.2-11b pilot (120 calls)")
    else:
        print("ALL PILOTS COMPLETE! Ready for full runs approval.")
    print(f"{'='*70}")


def watch(interval=10):
    """Watch pilot progress continuously."""
    try:
        while True:
            os.system('cls' if os.name == 'nt' else 'clear')
            print_status()
            print(f"\nRefreshing in {interval}s... (Ctrl+C to stop)")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nStopped watching")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--watch', '-w', action='store_true', help='Watch mode')
    parser.add_argument('--interval', '-i', type=int, default=10, help='Watch interval (seconds)')
    parser.add_argument('--json', '-j', action='store_true', help='Output JSON')
    args = parser.parse_args()
    
    if args.watch:
        watch(args.interval)
    elif args.json:
        print(json.dumps(get_pilot_status(), indent=2))
    else:
        print_status()