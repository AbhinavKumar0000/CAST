import os, time, httpx
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
    for i in range(3):
        payload = {'model': model_id, 'messages': [{'role': 'user', 'content': PROMPT}], 'temperature': 0.2, 'max_tokens': 100}
        req_start = time.time()
        try:
            with httpx.Client(base_url=base_url, headers=headers, timeout=30.0) as c:
                r = c.post('/chat/completions', json=payload)
            latency = time.time() - req_start
            if r.status_code == 429:
                print('  Rate limited')
                latencies.append(None)
            elif r.status_code in (402,403,404):
                print('  Not accessible')
                break
            else:
                r.raise_for_status()
                latencies.append(latency)
                print('  OK (' + str(round(latency,1)) + 's)')
        except Exception as e:
            print('  Error: ' + str(e))
            latencies.append(None)
        time.sleep(2)
    valid = [x for x in latencies if x is not None]
    if valid:
        valid.sort()
        print('  ' + short_name + ': median=' + str(round(valid[len(valid)//2],1)) + 's, n=' + str(len(valid)))
    print()