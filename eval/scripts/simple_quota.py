import os, time, httpx
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv('NVIDIA_API_KEY')
base_url = 'https://integrate.api.nvidia.com/v1'
headers = {'Authorization': 'Bearer ' + api_key, 'Content-Type': 'application/json'}

models = [
    ('nvidia/nemotron-3-ultra-550b-a55b', 'nemotron-3-ultra'),
    ('z-ai/glm-5.3', 'glm-5.3'),
    ('meta/llama-3.2-11b-vision-instruct', 'llama-3.2-11b'),
]

PROMPT = 'Return JSON: {"top5": ["Wheat", "Rice"], "explanation": "test"}'

for model_id, short_name in models:
    print('Testing ' + model_id + '...')
    latencies = []
    rate_limited = 0
    errors = 0
    start = time.time()
    
    for i in range(15):
        payload = {'model': model_id, 'messages': [{'role': 'user', 'content': PROMPT}], 'temperature': 0.2, 'max_tokens': 100}
        req_start = time.time()
        try:
            with httpx.Client(base_url=base_url, headers=headers, timeout=60.0) as c:
                r = c.post('/chat/completions', json=payload)
            latency = time.time() - req_start
            if r.status_code == 429:
                rate_limited += 1
                print('  Rate limited, waiting...')
                time.sleep(10)
                continue
            elif r.status_code in (402,403,404):
                errors += 1
                print('  Not accessible')
                break
            else:
                r.raise_for_status()
                latencies.append(latency)
                print('  OK (' + str(round(latency,1)) + 's)')
        except Exception as e:
            errors += 1
            print('  Error: ' + str(e))
        time.sleep(3)
    
    elapsed = time.time() - start
    successful = len(latencies)
    if latencies:
        latencies.sort()
        median = latencies[len(latencies)//2]
        p95 = latencies[int(len(latencies)*0.95)]
        rpm = (successful / elapsed) * 60 if elapsed > 0 else 0
    else:
        median = p95 = rpm = 0
    
    print('  ' + short_name + ': ' + str(successful) + '/15, median=' + str(round(median,1)) + 's, p95=' + str(round(p95,1)) + 's, rpm=' + str(round(rpm,1)) + ', rate_limited=' + str(rate_limited))
    time.sleep(5)