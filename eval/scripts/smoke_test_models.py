"""Smoke test NVIDIA NIM candidate models for tool calling and reliability."""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from eval.common import config_dirs, load_config

cfg = load_config()
dirs = config_dirs(cfg)

models_dir = Path(dirs["data_dir"]) / "models"
models_dir.mkdir(parents=True, exist_ok=True)

api_key = os.getenv("NVIDIA_API_KEY")
if not api_key:
    print("ERROR: NVIDIA_API_KEY not set")
    sys.exit(1)

base_url = cfg["model"]["nvidia"].get("base_url", "https://integrate.api.nvidia.com/v1")

# Load candidate models from previous step
cand_path = models_dir / "candidate_models.json"
if not cand_path.exists():
    print("ERROR: candidate_models.json not found. Run fetch_nvidia_models.py first.")
    sys.exit(1)

with cand_path.open() as f:
    cand_data = json.load(f)

# Extract unique model IDs to test
candidate_ids = set()
for c in cand_data["candidates"]:
    for m in c["matches"]:
        candidate_ids.add(m)

# Add some additional models from the full list that might be good
additional = [
    "moonshotai/kimi-k2.6",
    "moonshotai/kimi-k3",
    "deepseek-ai/deepseek-v4.1-flash",
    "z-ai/glm-5.3",
    "nvidia/llama-3.1-nemotron-70b-instruct",
    "nvidia/llama-3.1-nemotron-ultra-253b-v1",
    "mistralai/mistral-large-2-instruct",
    "writer/palmyra-fin-70b-32k",
]
for m in additional:
    candidate_ids.add(m)

candidate_ids = list(candidate_ids)
print(f"Testing {len(candidate_ids)} candidate models...")

# Tool definitions for smoke test
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "weather_tool",
            "description": "Get weather forecast data for the coordinates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "latitude": {"type": "number"},
                    "longitude": {"type": "number"},
                },
                "required": ["latitude", "longitude"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "climate_tool",
            "description": "Get climate normals for the region.",
            "parameters": {
                "type": "object",
                "properties": {
                    "latitude": {"type": "number"},
                    "longitude": {"type": "number"},
                },
                "required": ["latitude", "longitude"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "season_tool",
            "description": "Get the current cropping season in IST.",
            "parameters": {
                "type": "object",
                "properties": {
                    "latitude": {"type": "number"},
                    "longitude": {"type": "number"},
                },
                "required": ["latitude", "longitude"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "risk_tool",
            "description": "Get drought, flood, and heatwave risk analysis.",
            "parameters": {
                "type": "object",
                "properties": {
                    "latitude": {"type": "number"},
                    "longitude": {"type": "number"},
                },
                "required": ["latitude", "longitude"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_soil_by_coordinates",
            "description": "Get district, dominant soil, soil characteristics, and agricultural suitability.",
            "parameters": {
                "type": "object",
                "properties": {
                    "latitude": {"type": "number"},
                    "longitude": {"type": "number"},
                },
                "required": ["latitude", "longitude"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "crop_score",
            "description": "Rank the best candidate crops using deterministic scoring.",
            "parameters": {
                "type": "object",
                "properties": {
                    "latitude": {"type": "number"},
                    "longitude": {"type": "number"},
                },
                "required": ["latitude", "longitude"],
            },
        },
    },
]

# Test prompts
PLAIN_PROMPT = """You are an agronomy advisor for Madhya Pradesh, India.
District: Bhopal. Coordinates: 23.2599, 77.4126. Date: 2024-07-15.
Recommend the best crops to grow for this district around this date.
Candidate crops: Soybean, Wheat, Rice, Maize, Cotton, Jowar, Gram, Sugarcane, Mustard, Groundnut, Moong, Urad, Lentil, Barley, Bajra, Sesame (Til), Sunflower, Arhar (Tur), Pea, Kodo-Kutki, Watermelon.
Return ONLY a single JSON object: {"top5": ["<crop1>", "<crop2>", "<crop3>", "<crop4>", "<crop5>"], "explanation": "<=60 words>"}"""

TOOL_PROMPT = """You are an agronomy advisor for Madhya Pradesh, India, with access to agricultural tools.
District: Bhopal. Coordinates: 23.2599, 77.4126. Date: 2024-07-15.
Use the available tools to gather evidence before deciding:
call weather_tool, climate_tool, season_tool, risk_tool, and get_soil_by_coordinates with the given latitude and longitude, then call crop_score.
Base your decision on the tool outputs and do not invent soil, weather, or risk values.
Candidate crops: Soybean, Wheat, Rice, Maize, Cotton, Jowar, Gram, Sugarcane, Mustard, Groundnut, Moong, Urad, Lentil, Barley, Bajra, Sesame (Til), Sunflower, Arhar (Tur), Pea, Kodo-Kutki, Watermelon.
Return ONLY a single JSON object: {"top5": ["<crop1>", "<crop2>", "<crop3>", "<crop4>", "<crop5>"], "explanation": "<=60 words>"}"""

headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

def test_model(model_id: str, use_tools: bool) -> dict[str, Any]:
    """Test a model with a single request."""
    url = f"{base_url}/chat/completions"
    
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": TOOL_PROMPT if use_tools else PLAIN_PROMPT}],
        "temperature": 0.2,
        "top_p": 1.0,
        "max_tokens": 512,
    }
    if use_tools:
        payload["tools"] = TOOLS
        payload["tool_choice"] = "auto"
    
    start = time.perf_counter()
    try:
        with httpx.Client(base_url=base_url, headers=headers, timeout=120.0) as client:
            resp = client.post("/chat/completions", json=payload)
        
        latency = time.perf_counter() - start
        
        if resp.status_code == 429:
            return {"status": "rate_limited", "latency": latency, "error": "429 Too Many Requests"}
        if resp.status_code in (402, 403, 404):
            return {"status": "not_accessible", "latency": latency, "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
        
        resp.raise_for_status()
        data = resp.json()
        
        choice = data["choices"][0]
        message = choice["message"]
        content = message.get("content") or ""
        tool_calls = message.get("tool_calls", [])
        usage = data.get("usage", {})
        
        # Check if valid JSON in content
        valid_json = False
        if content.strip():
            try:
                parsed = json.loads(content.strip().strip("```json").strip("```"))
                if isinstance(parsed, dict) and "top5" in parsed:
                    valid_json = True
            except:
                pass
        
        return {
            "status": "success",
            "latency": latency,
            "tokens_in": usage.get("prompt_tokens", 0),
            "tokens_out": usage.get("completion_tokens", 0),
            "reasoning_tokens": usage.get("reasoning_tokens", 0),
            "tool_calls": len(tool_calls),
            "tool_call_names": [tc["function"]["name"] for tc in tool_calls],
            "valid_json": valid_json,
            "content_preview": content[:200],
        }
        
    except Exception as e:
        return {"status": "error", "latency": time.perf_counter() - start, "error": str(e)}

# Run smoke tests
results = {}
for i, model_id in enumerate(candidate_ids):
    print(f"\n[{i+1}/{len(candidate_ids)}] Testing {model_id}...")
    
    # Test 1: plain JSON (no tools)
    print("  Plain JSON...", end=" ", flush=True)
    plain_result = test_model(model_id, use_tools=False)
    print(f" {plain_result['status']} ({plain_result.get('latency', 0):.1f}s)")
    
    if plain_result["status"] == "rate_limited":
        print("  Rate limited - waiting 30s...")
        time.sleep(30)
        plain_result = test_model(model_id, use_tools=False)
        print(f"  Retry: {plain_result['status']} ({plain_result.get('latency', 0):.1f}s)")
    
    if plain_result["status"] in ("not_accessible", "error"):
        results[model_id] = {"plain": plain_result, "tool": None}
        continue
    
    # Test 2: with tools
    print("  With tools...", end=" ", flush=True)
    tool_result = test_model(model_id, use_tools=True)
    print(f" {tool_result['status']} ({tool_result.get('latency', 0):.1f}s)")
    
    if tool_result["status"] == "rate_limited":
        print("  Rate limited - waiting 30s...")
        time.sleep(30)
        tool_result = test_model(model_id, use_tools=True)
        print(f"  Retry: {tool_result['status']} ({tool_result.get('latency', 0):.1f}s)")
    
    results[model_id] = {"plain": plain_result, "tool": tool_result}
    
    # Small delay between models
    time.sleep(2)

# Save results
output = {
    "tested_at": datetime.now(timezone.utc).isoformat(),
    "base_url": base_url,
    "temperature": 0.2,
    "max_tokens": 512,
    "results": results,
}
results_path = models_dir / "smoke_test_results.json"
results_path.write_text(json.dumps(output, indent=2))
print(f"\nSaved smoke test results to {results_path}")

# Summary
print("\n=== SMOKE TEST SUMMARY ===")
for model_id, res in results.items():
    plain = res["plain"]
    tool = res["tool"]
    
    plain_ok = plain["status"] == "success"
    tool_ok = tool and tool["status"] == "success" and tool.get("tool_calls", 0) > 0
    valid_json = plain.get("valid_json", False) or (tool and tool.get("valid_json", False))
    
    print(f"{model_id}:")
    print(f"  Plain: {'OK' if plain_ok else 'FAIL'} ({plain.get('latency', 0):.1f}s, json={'Y' if plain.get('valid_json') else 'N'})")
    if tool:
        print(f"  Tools: {'OK' if tool_ok else 'FAIL'} ({tool.get('latency', 0):.1f}s, calls={tool.get('tool_calls', 0)}, json={'Y' if tool.get('valid_json') else 'N'})")
    else:
        print(f"  Tools: SKIPPED (plain failed)")

print("\nDone!")