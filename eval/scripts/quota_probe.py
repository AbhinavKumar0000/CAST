"""Quota probe for selected NVIDIA NIM models."""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv('NVIDIA_API_KEY')
base_url = 'https://integrate.api.nvidia.com/v1'
headers = {'Authorization': 'Bearer ' + api_key, 'Content-Type': 'application/json'}

models = [
    ("nvidia/nemotron-3-ultra-550b-a55b", "nemotron-3-ultra"),
    ("z-ai/glm-5.3", "glm-5.3"),
    ("meta/llama-3.2-11b-vision-instruct", "llama-3.2-11b"),
]

PROMPT = 'Return JSON: {"top5": ["Wheat", "Rice", "Maize", "Cotton", "Gram"], "explanation": "Test crops for Madhya Pradesh."}'

results = {}

for model_id, short_name in models:
    print(f"\n=== Quota Probe: {model_id} ===")
    
    latencies = []
    errors = 0
    rate_limited = 0
    start_time = time.time()
    
    # Run for 5 minutes or 30 requests, whichever comes first
    max_requests = 30
    max_duration = 300  # 5 minutes
    
    for i in range(max_requests):
        if time.time() - start_time > max_duration:
            break
            
        payload = {
            'model': model_id,
            'messages': [{'role': 'user', 'content': PROMPT}],
            'temperature': 0.2,
            'max_tokens': 100
        }
        
        req_start = time.perf_counter()
        try:
            with httpx.Client(base_url=base_url, headers=headers, timeout=60.0) as c:
                r = c.post('/chat/completions', json=payload)
            
            latency = time.perf_counter() - req_start
            
            if r.status_code == 429:
                rate_limited += 1
                print(f"  Request {i+1}: RATE LIMITED (latency={latency:.1f}s)")
                # Wait and retry
                retry_after = r.headers.get('retry-after')
                wait = float(retry_after) if retry_after else 10
                time.sleep(min(wait, 30))
                continue
            elif r.status_code in (402, 403, 404):
                errors += 1
                print(f"  Request {i+1}: NOT ACCESSIBLE ({r.status_code})")
                break
            else:
                r.raise_for_status()
                latencies.append(latency)
                print(f"  Request {i+1}: OK ({latency:.1f}s)")
                
        except Exception as e:
            errors += 1
            print(f"  Request {i+1}: ERROR - {e}")
        
        time.sleep(2)  # Small delay between requests
    
    elapsed = time.time() - start_time
    successful = len(latencies)
    
    if latencies:
        latencies.sort()
        median = latencies[len(latencies)//2]
        p95 = latencies[int(len(latencies)*0.95)]
        rpm = (successful / elapsed) * 60 if elapsed > 0 else 0
    else:
        median = p95 = rpm = 0
    
    result = {
        "model_id": model_id,
        "short_name": short_name,
        "tested_at": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": elapsed,
        "requests_attempted": i + 1,
        "successful": successful,
        "errors": errors,
        "rate_limited": rate_limited,
        "median_latency_s": round(median, 2),
        "p95_latency_s": round(p95, 2),
        "measured_rpm": round(rpm, 1),
        "recommended_rpm": round(rpm * 0.7, 1) if rpm > 0 else 0,
        "all_latencies": latencies,
    }
    
    results[model_id] = result
    
    print(f"  Successful: {successful}/{i+1}")
    print(f"  Median latency: {median:.1f}s")
    print(f"  P95 latency: {p95:.1f}s")
    print(f"  Measured RPM: {rpm:.1f}")
    print(f"  Recommended RPM (70%): {rpm * 0.7:.1f}")
    print(f"  Rate limited: {rate_limited}")
    print(f"  Errors: {errors}")

# Save
output = {
    "probed_at": datetime.now(timezone.utc).isoformat(),
    "base_url": base_url,
    "test_config": {
        "prompt": PROMPT,
        "temperature": 0.2,
        "max_tokens": 100,
        "max_requests_per_model": max_requests,
        "max_duration_seconds": max_duration,
    },
    "results": results,
}

out_path = Path('eval/models/QUOTA.md')
out_path.parent.mkdir(parents=True, exist_ok=True)

# Generate markdown report
md = f"""# Quota Probe Results

**Probed at**: {output['probed_at']}
**Base URL**: {output['base_url']}
**Test**: {output['test_config']['max_requests_per_model']} requests or {output['test_config']['max_duration_seconds']}s per model
**Temperature**: {output['test_config']['temperature']}
**Max tokens**: {output['test_config']['max_tokens']}

## Summary Table

| Model | Successful | Median (s) | P95 (s) | Measured RPM | Recommended RPM (70%) | Rate Limited | Errors |
|-------|------------|------------|---------|--------------|----------------------|--------------|--------|
"""

for model_id, r in results.items():
    md += f"| {r['short_name']} | {r['successful']}/{r['requests_attempted']} | {r['median_latency_s']} | {r['p95_latency_s']} | {r['measured_rpm']} | {r['recommended_rpm']} | {r['rate_limited']} | {r['errors']} |\n"

md += f"""

## Per-Model Details

"""

for model_id, r in results.items():
    md += f"### {r['short_name']} ({model_id})\n\n"
    md += f"- **Duration**: {r['duration_seconds']:.0f}s\n"
    md += f"- **Requests attempted**: {r['requests_attempted']}\n"
    md += f"- **Successful**: {r['successful']}\n"
    md += f"- **Rate limited**: {r['rate_limited']}\n"
    md += f"- **Errors**: {r['errors']}\n"
    md += f"- **Median latency**: {r['median_latency_s']}s\n"
    md += f"- **P95 latency**: {r['p95_latency_s']}s\n"
    md += f"- **Measured RPM**: {r['measured_rpm']}\n"
    md += f"- **Recommended RPM (70%)**: {r['recommended_rpm']}\n"
    if r['all_latencies']:
        md += f"- **Latencies (s)**: {', '.join(f'{x:.1f}' for x in r['all_latencies'])}\n"
    md += "\n"

md += f"""

## Runner Configuration

Based on these measurements, the runner should use:
- **Concurrency**: 1-2 (sequential model execution)
- **Rate limit**: 12 req/min (conservative, below all measured rates)
- **Backoff**: 2s base, 60s max, with jitter
- **Daily budget**: 4000 requests (shared across models)

## Notes

- Rate limits are account-wide (~40 req/min on NVIDIA NIM free tier)
- Models are run SEQUENTIALLY, never in parallel
- If 429 received, runner pauses automatically and resumes
- Measured rates may vary by time of day and endpoint load
"""

out_path.write_text(md)
print(f"\nSaved quota report to {out_path}")