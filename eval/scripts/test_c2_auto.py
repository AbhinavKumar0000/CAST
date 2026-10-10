import os, time, httpx
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv('NVIDIA_API_KEY')
base_url = 'https://integrate.api.nvidia.com/v1'
headers = {'Authorization': 'Bearer ' + api_key, 'Content-Type': 'application/json'}

model_id = 'nvidia/nemotron-3-ultra-550b-a55b'
PROMPT = 'You are an agronomy advisor for Madhya Pradesh, India, with access to agricultural tools.\nDistrict: Bhopal. Coordinates: 23.2599, 77.4126. Date: 2024-07-15.\nYou MUST call ALL of the following tools with the given latitude and longitude before making any recommendation:\n1. weather_tool\n2. climate_tool\n3. season_tool\n4. risk_tool\n5. get_soil_by_coordinates\n6. crop_score\nCall them in any order, but you must call ALL six. After receiving all tool outputs, base your final recommendation strictly on the tool outputs. Do not invent soil, weather, climate, season, risk, or crop suitability values.\nCandidate crops: Soybean, Wheat, Rice, Maize, Cotton, Jowar, Gram, Sugarcane, Mustard, Groundnut, Moong, Urad, Lentil, Barley, Bajra, Sesame (Til), Sunflower, Arhar (Tur), Pea, Kodo-Kutki, Watermelon.\nReturn ONLY a single JSON object, no markdown, no prose outside it:\n{"top5": ["<crop1>", "<crop2>", "<crop3>", "<crop4>", "<crop5>"], "explanation": "<=60 words"}\nUse the exact crop names from the list above. Do not invent crop names. Rank them best-first.'

TOOLS = [
    {'type': 'function', 'function': {'name': 'weather_tool', 'description': 'Get weather.', 'parameters': {'type': 'object', 'properties': {'latitude': {'type': 'number'}, 'longitude': {'type': 'number'}}, 'required': ['latitude', 'longitude']}}},
    {'type': 'function', 'function': {'name': 'climate_tool', 'description': 'Get climate.', 'parameters': {'type': 'object', 'properties': {'latitude': {'type': 'number'}, 'longitude': {'type': 'number'}}, 'required': ['latitude', 'longitude']}}},
    {'type': 'function', 'function': {'name': 'season_tool', 'description': 'Get season.', 'parameters': {'type': 'object', 'properties': {'latitude': {'type': 'number'}, 'longitude': {'type': 'number'}}, 'required': ['latitude', 'longitude']}}},
    {'type': 'function', 'function': {'name': 'risk_tool', 'description': 'Get risk.', 'parameters': {'type': 'object', 'properties': {'latitude': {'type': 'number'}, 'longitude': {'type': 'number'}}, 'required': ['latitude', 'longitude']}}},
    {'type': 'function', 'function': {'name': 'get_soil_by_coordinates', 'description': 'Get soil.', 'parameters': {'type': 'object', 'properties': {'latitude': {'type': 'number'}, 'longitude': {'type': 'number'}}, 'required': ['latitude', 'longitude']}}},
    {'type': 'function', 'function': {'name': 'crop_score', 'description': 'Rank crops.', 'parameters': {'type': 'object', 'properties': {'latitude': {'type': 'number'}, 'longitude': {'type': 'number'}}, 'required': ['latitude', 'longitude']}}},
]

# Test with tool_choice="auto" instead of "required"
payload = {'model': model_id, 'messages': [{'role': 'user', 'content': PROMPT}], 'temperature': 0.2, 'max_tokens': 2048, 'tools': TOOLS, 'tool_choice': 'auto'}

print('Testing C2 with tool_choice="auto"...')
start = time.time()
try:
    with httpx.Client(base_url=base_url, headers=headers, timeout=120.0) as c:
        r = c.post('/chat/completions', json=payload)
    latency = time.time() - start
    print('Status:', r.status_code)
    if r.status_code == 429:
        print('Rate limited')
    elif r.status_code in (402,403,404):
        print('Not accessible:', r.status_code)
        print('Response:', r.text[:200])
    else:
        r.raise_for_status()
        data = r.json()
        print('SUCCESS! Latency:', round(latency,1), 's')
        choices = data.get('choices', [])
        if choices:
            choice = choices[0]
            msg = choice.get('message', {})
            content = msg.get('content') or ''
            print('Content:', content[:300] if content else '(empty)')
            tool_calls = msg.get('tool_calls', [])
            print('Tool calls:', len(tool_calls))
            for tc in tool_calls:
                print('  -', tc['function']['name'])
            usage = data.get('usage', {})
            print('Tokens:', usage.get('prompt_tokens'), '/', usage.get('completion_tokens'))
            print('Finish reason:', choice.get('finish_reason'))
except Exception as e:
    import traceback
    print('Error:', e)
    traceback.print_exc()