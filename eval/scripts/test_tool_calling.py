import json, os, time, httpx
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv('NVIDIA_API_KEY')
base_url = 'https://integrate.api.nvidia.com/v1'
headers = {'Authorization': 'Bearer ' + api_key, 'Content-Type': 'application/json'}

# Models that passed plain test - now test tool calling
models = ['nvidia/nemotron-3-ultra-550b-a55b', 'nvidia/nemotron-3-super-120b-a12b', 'z-ai/glm-5.3', 'meta/llama-3.2-11b-vision-instruct']

TOOLS = [
    {'type': 'function', 'function': {'name': 'weather_tool', 'description': 'Get weather.', 'parameters': {'type': 'object', 'properties': {'latitude': {'type': 'number'}, 'longitude': {'type': 'number'}}, 'required': ['latitude', 'longitude']}}},
    {'type': 'function', 'function': {'name': 'climate_tool', 'description': 'Get climate.', 'parameters': {'type': 'object', 'properties': {'latitude': {'type': 'number'}, 'longitude': {'type': 'number'}}, 'required': ['latitude', 'longitude']}}},
    {'type': 'function', 'function': {'name': 'season_tool', 'description': 'Get season.', 'parameters': {'type': 'object', 'properties': {'latitude': {'type': 'number'}, 'longitude': {'type': 'number'}}, 'required': ['latitude', 'longitude']}}},
    {'type': 'function', 'function': {'name': 'risk_tool', 'description': 'Get risk.', 'parameters': {'type': 'object', 'properties': {'latitude': {'type': 'number'}, 'longitude': {'type': 'number'}}, 'required': ['latitude', 'longitude']}}},
    {'type': 'function', 'function': {'name': 'get_soil_by_coordinates', 'description': 'Get soil.', 'parameters': {'type': 'object', 'properties': {'latitude': {'type': 'number'}, 'longitude': {'type': 'number'}}, 'required': ['latitude', 'longitude']}}},
    {'type': 'function', 'function': {'name': 'crop_score', 'description': 'Rank crops.', 'parameters': {'type': 'object', 'properties': {'latitude': {'type': 'number'}, 'longitude': {'type': 'number'}}, 'required': ['latitude', 'longitude']}}},
]

PROMPT = 'You are an agronomy advisor with tools. District: Bhopal. Coordinates: 23.2599, 77.4126. Date: 2024-07-15. Call weather_tool, climate_tool, season_tool, risk_tool, get_soil_by_coordinates, then crop_score. Return ONLY: {\"top5\": [\"Wheat\", \"Rice\", \"Maize\", \"Cotton\", \"Gram\"], \"explanation\": \"test\"}'

results = {}
for m in models:
    print('Testing ' + m + ' with tools...', end=' ')
    payload = {'model': m, 'messages': [{'role': 'user', 'content': PROMPT}], 'temperature': 0.2, 'max_tokens': 512, 'tools': TOOLS, 'tool_choice': 'auto'}
    try:
        with httpx.Client(base_url=base_url, headers=headers, timeout=120.0) as c:
            r = c.post('/chat/completions', json=payload)
        if r.status_code in (402,403,404):
            print('not_accessible')
            results[m] = {'tool': {'status': 'not_accessible'}}
        elif r.status_code == 429:
            print('rate_limited')
            results[m] = {'tool': {'status': 'rate_limited'}}
        else:
            r.raise_for_status()
            data = r.json()
            msg = data['choices'][0]['message']
            tool_calls = msg.get('tool_calls', [])
            usage = data.get('usage', {})
            print('success (calls=' + str(len(tool_calls)) + ')')
            results[m] = {'tool': {'status': 'success', 'tool_calls': len(tool_calls), 'tool_names': [tc['function']['name'] for tc in tool_calls], 'tokens_in': usage.get('prompt_tokens', 0), 'tokens_out': usage.get('completion_tokens', 0), 'reasoning_tokens': usage.get('reasoning_tokens', 0)}}
    except Exception as e:
        print('error: ' + str(e))
        results[m] = {'tool': {'status': 'error', 'error': str(e)}}
    time.sleep(3)

print(json.dumps(results, indent=2))