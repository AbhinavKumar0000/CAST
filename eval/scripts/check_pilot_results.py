import json
from pathlib import Path
from collections import defaultdict

runs_dir = Path('eval/runs')
pilot_dirs = sorted([d for d in runs_dir.iterdir() if d.name.startswith('pilot_')])
if pilot_dirs:
    latest = pilot_dirs[-1]
    print('Latest pilot:', latest)
    results_file = latest / 'pilot_results.json'
    if results_file.exists():
        with open(results_file) as f:
            results = json.load(f)
        print('Total results:', len(results))
        
        summary = defaultdict(lambda: {'ok': 0, 'err': 0, 'latencies': [], 'tools': [], 'tokens_in': [], 'tokens_out': [], 'invalid_json': 0})
        
        for r in results:
            key = (r['model_short'], r['condition'])
            if r['error']:
                summary[key]['err'] += 1
            else:
                summary[key]['ok'] += 1
                summary[key]['latencies'].append(r['latency_s'])
                summary[key]['tools'].append(r['tool_calls'])
                summary[key]['tokens_in'].append(r['tokens_in'])
                summary[key]['tokens_out'].append(r['tokens_out'])
                if not r['parsed'].get('valid_json', False):
                    summary[key]['invalid_json'] += 1
        
        print()
        header = '{:<20} {:<5} {:>3} {:>3} {:>9} {:>8} {:>9} {:>8} {:>7}'.format('Model', 'Cond', 'OK', 'Err', 'MedianLat', 'AvgTokIn', 'AvgTokOut', 'AvgTools', 'InvJSON')
        print(header)
        print('-' * 90)
        for (model, cond), stats in sorted(summary.items()):
            if stats['ok'] > 0:
                lats = sorted(stats['latencies'])
                lat = lats[len(lats)//2]
                avg_in = sum(stats['tokens_in']) / len(stats['tokens_in'])
                avg_out = sum(stats['tokens_out']) / len(stats['tokens_out'])
                avg_tools = sum(stats['tools']) / len(stats['tools'])
            else:
                lat = avg_in = avg_out = avg_tools = 0
            line = '{:<20} {:<5} {:>3} {:>3} {:>8.1f}s {:>8.0f} {:>9.0f} {:>8.1f} {:>7}'.format(model, cond, stats['ok'], stats['err'], lat, avg_in, avg_out, avg_tools, stats['invalid_json'])
            print(line)