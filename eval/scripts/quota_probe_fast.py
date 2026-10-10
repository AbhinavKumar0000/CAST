"""Quick quota probe - 3 minutes per model, concurrency 3."""

import json, os, time, sys
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv('NVIDIA_API_KEY')
base_url = 'https://integrate.api.nvidia.com/v1'
headers = {'Authorization': 'Bearer ' + api_key, 'Content-Type': 'application/json'}

models = [
    ('nvidia/nemotron-3-ultra-550b-a55b', 'nemotron-3-ultra', 3),
    ('z-ai/glm-5.3', 'glm-5.3', 2),  # slower model, keep concurrency 2
    ('meta/llama-3.2-11b-vision-instruct', 'llama-3.2-11b', 3),
]

PROMPT = 'Return JSON: {"top5": ["Wheat", "Rice", "Maize", "Cotton", "Gram"], "explanation": "Test crops for Madhya Pradesh."}'

def single_request(model_id):
    payload = {'model': model_id, 'messages': [{'role': 'user', 'content': PROMPT}], 'temperature': 0.2, 'max_tokens': 100}
    try:
        with httpx.Client(base_url=base_url, headers=headers, timeout=60.0) as c:
            r = c.post('/chat/completions', json=payload)
        if r.status_code == 429:
            return {'status': 'rate_limited'}
        elif r.status_code in (402, 403, 404):
            return {'status': 'not_accessible'}
        else:
            r.raise_for_status()
            return {'status': 'success', 'latency': 0}  # latency measured externally
    except Exception:
        return {'status': 'error'}

results = {}
print('Starting quota probe (3 min per model, concurrency varies)...')
for model_id, short_name, concurrency in models:
    print('\nProbing ' + model_id + ' (concurrency=' + str(concurrency) + ')...')
    latencies = []
    rate_limited = 0
    errors = 0
    start = time.time()
    max_duration = 180  # 3 minutes
    
    # Run requests with concurrency
    while time.time() - start < max_duration:
        batch_start = time.time()
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [executor.submit(single_request, model_id) for _ in range(concurrency)]
            for f in as_completed(futures):
                req_latency = time.time() - batch_start
                res = f.result()
                if res['status'] == 'success':
                    latencies.append(req_latency)
                elif res['status'] == 'rate_limited':
                    rate_limited += 1
                    time.sleep(5)  # brief pause on rate limit
                else:
                    errors += 1
        
        # Small delay between batches
        time.sleep(1)
    
    elapsed = time.time() - start
    successful = len(latencies)
    if latencies:
        latencies.sort()
        median = latencies[len(latencies)//2]
        p95 = latencies[int(len(latencies)*0.95)]
        rpm = (successful / elapsed) * 60 if elapsed > 0 else 0
    else:
        median = p95 = rpm = 0
    
    results[model_id] = {
        'short_name': short_name,
        'successful': successful,
        'elapsed': elapsed,
        'median_latency_s': round(median, 2),
        'p95_latency_s': round(p95, 2),
        'measured_rpm': round(rpm, 1),
        'recommended_rpm': round(rpm * 0.7, 1) if rpm > 0 else 0,
        'concurrency_used': concurrency,
        'rate_limited': rate_limited,
        'errors': errors,
    }
    
    print('  Successful: ' + str(successful) + ', median=' + str(round(median,1)) + 's, p95=' + str(round(p95,1)) + 's, rpm=' + str(round(rpm,1)) + ', rate_limited=' + str(rate_limited))

# Save QUOTA.md
models_dir = Path('eval/data/models')
models_dir.mkdir(parents=True, exist_ok=True)

md = '# Quota Probe Results\n\n'
md += '**Probed at**: ' + datetime.now(timezone.utc).isoformat() + '\n'
md += '**Base URL**: ' + base_url + '\n'
md += '**Test**: 3 min per model, concurrency 2-3\n\n'

md += '| Model | Concurrency | Successful | Median (s) | P95 (s) | Measured RPM | Recommended RPM (70%) | Rate Limited | Errors |\n'
md += '|-------|-------------|------------|------------|---------|--------------|----------------------|--------------|--------|\n'
for model_id, r in results.items():
    md += '| ' + r['short_name'] + ' | ' + str(r['concurrency_used']) + ' | ' + str(r['successful']) + ' | ' + str(r['median_latency_s']) + ' | ' + str(r['p95_latency_s']) + ' | ' + str(r['measured_rpm']) + ' | ' + str(r['recommended_rpm']) + ' | ' + str(r['rate_limited']) + ' | ' + str(r['errors']) + ' |\n'

md += '\n## Per-Model Details\n\n'
for model_id, r in results.items():
    md += '### ' + r['short_name'] + ' (' + model_id + ')\n\n'
    md += '- **Concurrency used**: ' + str(r['concurrency_used']) + '\n'
    md += '- **Duration**: ' + str(round(r['elapsed'])) + 's\n'
    md += '- **Successful**: ' + str(r['successful']) + '\n'
    md += '- **Rate limited**: ' + str(r['rate_limited']) + '\n'
    md += '- **Errors**: ' + str(r['errors']) + '\n'
    md += '- **Median latency**: ' + str(r['median_latency_s']) + 's\n'
    md += '- **P95 latency**: ' + str(r['p95_latency_s']) + 's\n'
    md += '- **Measured RPM**: ' + str(r['measured_rpm']) + '\n'
    md += '- **Recommended RPM (70%)**: ' + str(r['recommended_rpm']) + '\n\n'

md += '## Runner Configuration\n\n'
md += '- **Concurrency**: 3 for nemotron/llama, 2 for GLM\n'
md += '- **Rate limit**: 12 req/min (conservative)\n'
md += '- **Backoff**: 2s base, 60s max, with jitter\n'
md += '- **Daily budget**: 4000 requests\n'
md += '- **Models run SEQUENTIALLY**, never in parallel\n'
md += '- **Auto-pause on 429**, resume after backoff\n'

# Full run time estimate
print('\n=== FULL RUN TIME ESTIMATE ===')
primary = results['nvidia/nemotron-3-ultra-550b-a55b']
second = results['z-ai/glm-5.3']
small = results['meta/llama-3.2-11b-vision-instruct']

# Estimate: Primary 500 scenarios × 4 conditions = 2000 requests
# Each request may need 2-6 API calls (tool calling rounds)
primary_requests = 2000 * 4  # avg 4 calls per scenario
primary_hours = primary_requests / (primary['recommended_rpm'] * 60) if primary['recommended_rpm'] > 0 else 0

second_requests = 150 * 4 * 4  # 150 scenarios × 4 conditions × 4 calls
second_hours = second_requests / (second['recommended_rpm'] * 60) if second['recommended_rpm'] > 0 else 0

small_requests = 150 * 4 * 4
small_hours = small_requests / (small['recommended_rpm'] * 60) if small['recommended_rpm'] > 0 else 0

md += '\n## Full Run Time Estimates\n\n'
md += '| Model | Scenarios | Conditions | Est. Requests | Est. Hours |\n'
md += '|-------|-----------|------------|---------------|------------|\n'
md += '| nemotron-3-ultra | 500 | 4 | ' + str(primary_requests) + ' | ' + str(round(primary_hours, 1)) + ' |\n'
md += '| glm-5.3 | 150 | 4 | ' + str(second_requests) + ' | ' + str(round(second_hours, 1)) + ' |\n'
md += '| llama-3.2-11b | 150 | 4 | ' + str(small_requests) + ' | ' + str(round(small_hours, 1)) + ' |\n'
md += '| **Total (sequential)** | | | | **' + str(round(primary_hours + second_hours + small_hours, 1)) + '** |\n'

print('Primary hours:', round(primary_hours, 1))
print('Second hours:', round(second_hours, 1))
print('Small hours:', round(small_hours, 1))
print('Total:', round(primary_hours + second_hours + small_hours, 1))

(md_path := models_dir / 'QUOTA.md').write_text(md)
print('\nSaved QUOTA.md to', md_path)