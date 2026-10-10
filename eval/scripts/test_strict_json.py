import os, time, httpx, json
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv('NVIDIA_API_KEY')
base_url = 'https://integrate.api.nvidia.com/v1'
headers = {'Authorization': 'Bearer ' + api_key, 'Content-Type': 'application/json'}

model_id = 'nvidia/nemotron-3-ultra-550b-a55b'

PROMPT = 'You are an agronomy advisor for Madhya Pradesh, India.\nDistrict: Bhopal. Coordinates: 23.2599, 77.4126. Date: 2024-07-15.\nRecommend the best crops to grow for this district around this date.\nCandidate crops (use these exact names): Soybean, Wheat, Rice, Maize, Cotton, Jowar, Gram, Sugarcane, Mustard, Groundnut, Moong, Urad, Lentil, Barley, Bajra, Sesame (Til), Sunflower, Arhar (Tur), Pea, Kodo-Kutki, Watermelon.\nCRITICAL: Your entire response must be a SINGLE JSON object and NOTHING ELSE.\nDo NOT include any explanatory text, markdown, code fences, or prose.\nDo NOT write "Here is the JSON:" or any introduction.\nOutput format:\n{"top5": ["CropName1", "CropName2", "CropName3", "CropName4", "CropName5"], "explanation": "<=60 words"}\nUse EXACT crop names from the candidate list. No invented names. Rank best-first.'

SYSTEM = 'You are an agricultural advisor that outputs ONLY valid JSON. Never include any text, explanation, or formatting outside the JSON object. If you must think, do so internally; output only the final JSON.'

payload = {'model': model_id, 'messages': [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': PROMPT}], 'temperature': 0.2, 'max_tokens': 1024}

print('Testing C0 with system message and strict prompt...')
start = time.time()
try:
    with httpx.Client(base_url=base_url, headers=headers, timeout=60.0) as c:
        r = c.post('/chat/completions', json=payload)
    latency = time.time() - start
    if r.status_code == 429:
        print('Rate limited')
    elif r.status_code in (402,403,404):
        print('Not accessible:', r.status_code)
    else:
        r.raise_for_status()
        data = r.json()
        print('SUCCESS! Latency:', round(latency,1), 's')
        choice = data['choices'][0]
        msg = choice['message']
        content = msg.get('content') or ''
        print('Content:', content)
        print('Valid JSON?', end=' ')
        try:
            parsed = json.loads(content)
            print('YES -', parsed)
        except:
            print('NO')
except Exception as e:
    print('Error:', e)