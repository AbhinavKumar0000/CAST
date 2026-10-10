"""Quick smoke test on working models only."""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from eval.common import config_dirs, load_config

cfg = load_config()
dirs = config_dirs(cfg)
models_dir = Path(dirs["data_dir"]) / "models"

api_key = os.getenv("NVIDIA_API_KEY")
base_url = cfg["model"]["nvidia"].get("base_url", "https://integrate.api.nvidia.com/v1")

# Models that worked in initial test
working_models = [
    "nvidia/nemotron-3-ultra-550b-a55b",  # PRIMARY candidate
    "nvidia/nemotron-3-super-120b-a12b",   # Same family, smaller
    "nvidia/llama-3.1-nemotron-70b-instruct",  # Might work
    "moonshotai/kimi-k2.6",  # Different family
    "moonshotai/kimi-k3",    # Different family
    "deepseek-ai/deepseek-v4.1-flash",   # Different family
    "z-ai/glm-5.3",  # Different family
    "meta/llama-3.2-90b-vision-instruct", # Different family
    "meta/llama-3.2-11b-vision-instruct", # Different family
    "mistralai/mistral-large-2-instruct", # Different family
]

TOOLS = [
    {"type": "function", "function": {"name": "weather_tool", "description": "Get weather.", "parameters": {"type": "object", "properties": {"latitude": {"type": "number"}, "longitude": {"type": "number"}}, "required": ["latitude", "longitude"]}}},
    {"type": "function", "function": {"name": "climate_tool", "description": "Get climate normals.", "parameters": {"type": "object", "properties": {"latitude": {"type": "number"}, "longitude": {"type": "number"}}, "required": ["latitude", "longitude"]}}},
    {"type": "function", "function": {"name": "season_tool", "description": "Get season.", "parameters": {"type": "object", "properties": {"latitude": {"type": "number"}, "longitude": {"type": "number"}}, "required": ["latitude", "longitude"]}}},
    {"type": "function", "function": {"name": "risk_tool", "description": "Get risk analysis.", "parameters": {"type": "object", "properties": {"latitude": {"type": "number"}, "longitude": {"type": "number"}}, "required": ["latitude", "longitude"]}}},
    {"type": "function", "function": {"name": "get_soil_by_coordinates", "description": "Get soil info.", "parameters": {"type": "object", "properties": {"latitude": {"type": "number"}, "longitude": {"type": "number"}}, "required": ["latitude", "longitude"]}}},
    {"type": "function", "function": {"name": "crop_score", "description": "Rank crops.", "parameters": {"type": "object", "properties": {"latitude": {"type": "number"}, "longitude": {"type": "number"}}, "required": ["latitude", "longitude"]}}},
]

PLAIN_PROMPT = """You are an agronomy advisor for Madhya Pradesh, India.
District: Bhopal. Coordinates: 23.2599, 77.4126. Date: 2024-07-15.
Candidate crops: Soybean, Wheat, Rice, Maize, Cotton, Jowar, Gram, Sugarcane, Mustard, Groundnut, Moong, Urad, Lentil, Barley, Bajra, Sesame (Til), Sunflower, Arhar (Tur), Pea, Kodo-Kutki, Watermelon.
Return ONLY: {"top5": ["<crop1>", "<crop2>", "<crop3>", "<crop4>", "<crop5>"], "explanation": "<=60 words>"}"""

TOOL_PROMPT = """You are an agronomy advisor with tools.
District: Bhopal. Coordinates: 23.2599, 77.4126. Date: 2024-07-15.
Call weather_tool, climate_tool, season_tool, risk_tool, get_soil_by_coordinates, then crop_score.
Return ONLY: {"top5": ["<crop1>", "<crop2>", "<crop3>", "<crop4>", "<crop5>"], "explanation": "<=60 words>"}"""

headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

def test_once(model_id: str, use_tools: bool) -> dict:
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": TOOL_PROMPT if use_tools else PLAIN_PROMPT}],
        "temperature": 0.2, "top_p": 1.0, "max_tokens": 512,
    }
    if use_tools:
        payload["tools"] = TOOLS
        payload["tool_choice"] = "auto"
    
    start = time.perf_counter()
    try:
        with httpx.Client(base_url=base_url, headers=headers, timeout=60.0) as client:
            resp = client.post("/chat/completions", json=payload)
        latency = time.perf_counter() - start
        
        if resp.status_code in (402, 403, 404):
            return {"status": "not_accessible", "latency": latency}
        if resp.status_code == 429:
            return {"status": "rate_limited", "latency": latency}
        resp.raise_for_status()
        data = resp.json()
        
        choice = data["choices"][0]
        msg = choice["message"]
        content = msg.get("content") or ""
        tool_calls = msg.get("tool_calls", [])
        usage = data.get("usage", {})
        
        valid_json = False
        if content.strip():
            try:
                parsed = json.loads(content.strip().strip("```json").strip("```"))
                if isinstance(parsed, dict) and "top5" in parsed:
                    valid_json = True
            except:
                pass
        
        return {
            "status": "success", "latency": latency,
            "tokens_in": usage.get("prompt_tokens", 0),
            "tokens_out": usage.get("completion_tokens", 0),
            "reasoning_tokens": usage.get("reasoning_tokens", 0),
            "tool_calls": len(tool_calls),
            "tool_names": [tc["function"]["name"] for tc in tool_calls],
            "valid_json": valid_json,
        }
    except httpx.TimeoutException:
        return {"status": "timeout", "latency": time.perf_counter() - start}
    except Exception as e:
        return {"status": "error", "latency": time.perf_counter() - start, "error": str(e)}

results = {}
print(f"Testing {len(working_models)} models...")
for i, model_id in enumerate(working_models):
    print(f"[{i+1}/{len(working_models)}] {model_id}...", end=" ", flush=True)
    
    # Plain test
    r1 = test_once(model_id, False)
    print(f" plain={r1['status']} ({r1.get('latency',0):.1f}s)", end="")
    
    if r1["status"] != "success":
        results[model_id] = {"plain": r1, "tool": None}
        print()
        time.sleep(3)
        continue
    
    # Tool test
    r2 = test_once(model_id, True)
    print(f" tool={r2['status']} ({r2.get('latency',0):.1f}s, calls={r2.get('tool_calls',0)})")
    
    results[model_id] = {"plain": r1, "tool": r2}
    time.sleep(3)

# Save
output = {"tested_at": datetime.now(timezone.utc).isoformat(), "results": results}
models_dir.mkdir(parents=True, exist_ok=True)
(models_dir / "smoke_test_results.json").write_text(json.dumps(output, indent=2))
print(f"\nSaved to {models_dir}/smoke_test_results.json")

# Summary
print("\n=== SUMMARY ===")
for model_id, res in results.items():
    p = res["plain"]
    t = res["tool"]
    print(f"{model_id}: plain={p['status']} ({p.get('latency',0):.1f}s, json={p.get('valid_json')})", end="")
    if t:
        print(f", tool={t['status']} ({t.get('latency',0):.1f}s, calls={t.get('tool_calls',0)}, json={t.get('valid_json')})")
    else:
        print(", tool=SKIPPED")