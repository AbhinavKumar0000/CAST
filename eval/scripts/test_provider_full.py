from eval.llm.nvidia_provider import NvidiaProvider
from eval.common import load_config

cfg = load_config()
provider = NvidiaProvider(cfg)

# Simple test
prompt = 'Test prompt. Return JSON: {"top5": ["Wheat", "Rice"], "explanation": "test"}'
result = provider.run(prompt, use_mcp=False)
print('Plain:', result.ok, result.latency_s, result.text[:100])

# Tool test
tool_prompt = 'You are an agronomy advisor for Madhya Pradesh, India, with access to agricultural tools.\nDistrict: Bhopal. Coordinates: 23.2599, 77.4126. Date: 2024-07-15.\nYou MUST call ALL of the following tools with the given latitude and longitude before making any recommendation:\n1. weather_tool\n2. climate_tool\n3. season_tool\n4. risk_tool\n5. get_soil_by_coordinates\n6. crop_score\nCall them in any order, but you must call ALL six. After receiving all tool outputs, base your final recommendation strictly on the tool outputs. Do not invent soil, weather, climate, season, risk, or crop suitability values.\nCandidate crops: Soybean, Wheat, Rice, Maize, Cotton, Jowar, Gram, Sugarcane, Mustard, Groundnut, Moong, Urad, Lentil, Barley, Bajra, Sesame (Til), Sunflower, Arhar (Tur), Pea, Kodo-Kutki, Watermelon.\nReturn ONLY a single JSON object, no markdown, no prose outside it:\n{"top5": ["<crop1>", "<crop2>", "<crop3>", "<crop4>", "<crop5>"], "explanation": "<=60 words"}\nUse the exact crop names from the list above. Do not invent crop names. Rank them best-first.'

result = provider.run(tool_prompt, use_mcp=True)
print('Tool:', result.ok, result.latency_s, 'tools=', result.tool_calls)
if result.error:
    print('Error:', result.error)
else:
    print('Text:', result.text[:200])

provider.close()