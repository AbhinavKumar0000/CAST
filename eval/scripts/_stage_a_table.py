import json
from collections import Counter
from pathlib import Path

recs = [r for r in json.load(Path('eval/runs/eval_llama-3.2-11b/results.json').open(encoding='utf-8'))
        if r.get('condition') in ('C1a', 'C2a', 'C2b')]
print('model=meta/llama-3.2-11b-vision-instruct  stages=Stage A  scenarios=150')
for cond in ('C1a', 'C2a', 'C2b'):
    rs = [r for r in recs if r['condition'] == cond]
    n = len(rs)
    valid = sum(1 for r in rs if (r.get('parsed') or {}).get('valid_json'))
    trunc = sum(1 for r in rs if r.get('truncated'))
    forced = sum(1 for r in rs if r.get('forced_final'))
    forced_reasons = Counter(r.get('forced_final_reason', '') for r in rs if r.get('forced_final'))
    unk = sum(r.get('unknown_tool_calls', 0) for r in rs)
    maxr = sum(1 for r in rs if r.get('error') == 'max_rounds_reached')
    n429 = sum(1 for r in rs if '429' in str(r.get('error')))
    per_http = [len(r.get('tool_log') or []) + 1 for r in rs]
    total_http = sum(per_http)
    tools = [len(r.get('tool_log') or []) for r in rs]
    stall_triggered = forced
    print(f'cond={cond}')
    print(f'  valid_json             {valid}/{n} ({valid / n * 100:.1f}%)')
    print(f'  truncated              {trunc}')
    print(f'  forced_final           {forced}  (reasons {dict(forced_reasons) if forced_reasons else "none"})')
    print(f'  raw stall pre-fallback {stall_triggered}/{n} = {stall_triggered / n * 100:.1f}%  (forced_final trigger rate)')
    print(f'  unknown_tool_calls     {unk}  (runs {sum(1 for r in rs if r.get("unknown_tool_calls", 0))})')
    print(f'  max_rounds_reached     {maxr}')
    print(f'  429                    {n429}')
    print(f'  HTTP/scenario          mean={sum(per_http) / n:.2f}  median={sorted(per_http)[n // 2]}  max={max(per_http)}')
    print(f'  total HTTP             {total_http}')
    print(f'  tools/scenario         mean={sum(tools) / n:.2f}')