import json, os, time, httpx
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv('NVIDIA_API_KEY')
base_url = 'https://integrate.api.nvidia.com/v1'
headers = {'Authorization': 'Bearer ' + api_key, 'Content-Type': 'application/json'}

models = ['meta/llama-3.2-90b-vision-instruct', 'meta/llama-3.2-11b-vision-instruct', 'mistralai/mistral-large-2-instruct']

results = {}
for m in models:
    print('Testing ' + m + '...', end=' ')
    payload = {'model': m, 'messages': [{'role': 'user', 'content': 'Return JSON: {\"top5\": [\"Wheat\"], \"explanation\": \"test\"}'}], 'temperature': 0.2, 'max_tokens': 100}
    try:
        with httpx.Client(base_url=base_url, headers=headers, timeout=30.0) as c:
            r = c.post('/chat/completions', json=payload)
        if r.status_code in (402,403,404):
            print('not_accessible')
            results[m] = {'plain': {'status': 'not_accessible'}}
        elif r.status_code == 429:
            print('rate_limited')
            results[m] = {'plain': {'status': 'rate_limited'}}
        else:
            r.raise_for_status()
            print('success')
            results[m] = {'plain': {'status': 'success'}}
    except Exception as e:
        print('error: ' + str(e))
        results[m] = {'plain': {'status': 'error', 'error': str(e)}}
    time.sleep(2)

print(json.dumps(results, indent=2))