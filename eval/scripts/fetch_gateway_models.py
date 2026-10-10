"""Fetch and document Kilo Gateway models list."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from eval.common import config_dirs, load_config

cfg = load_config()
dirs = config_dirs(cfg)

# Ensure models directory exists
models_dir = Path(dirs["data_dir"]) / "models"
models_dir.mkdir(parents=True, exist_ok=True)

api_key = os.getenv("KILO_API_KEY")
if not api_key:
    print("ERROR: KILO_API_KEY not set in environment")
    print("Please add KILO_API_KEY to .env file")
    sys.exit(1)

base_url = cfg["model"]["kilo"].get("base_url", "https://api.kilo.ai/api/gateway")

print(f"Fetching models from {base_url}/v1/models...")
print(f"Using API key: {api_key[:8]}...")

headers = {"Authorization": f"Bearer {api_key}"}

try:
    with httpx.Client(base_url=base_url, headers=headers, timeout=30.0) as client:
        resp = client.get("/v1/models")
        resp.raise_for_status()
        data = resp.json()
except Exception as e:
    print(f"Failed to fetch models: {e}")
    sys.exit(1)

# Save raw response with timestamp
raw_output = {
    "fetched_at": datetime.now(timezone.utc).isoformat(),
    "base_url": base_url,
    "response": data,
}
raw_path = models_dir / "gateway_models_raw.json"
raw_path.write_text(json.dumps(raw_output, indent=2))
print(f"Saved raw response to {raw_path}")

# Process models
models = data.get("data", [])
print(f"\nTotal models: {len(models)}")

# Filter free models
free_models = [m for m in models if m.get("id", "").endswith(":free")]
print(f"Free models (ending in :free): {len(free_models)}")

for m in free_models:
    model_id = m.get("id", "")
    owned_by = m.get("owned_by", "unknown")
    context = m.get("context_length", "unknown")
    max_output = m.get("max_output_tokens", "unknown")
    print(f"  - {model_id} (owned_by: {owned_by}, context: {context}, max_output: {max_output})")

# Also show all models for reference
print("\nAll models:")
for m in models:
    model_id = m.get("id", "")
    is_free = " (FREE)" if model_id.endswith(":free") else ""
    owned_by = m.get("owned_by", "unknown")
    context = m.get("context_length", "unknown")
    max_output = m.get("max_output_tokens", "unknown")
    print(f"  - {model_id}{is_free} (owned_by: {owned_by}, context: {context}, max_output: {max_output})")

# Check for specific target models
targets = {
    "PRIMARY": "nvidia/nemotron-3-ultra-550b-a55b:free",
    "minimax": None,
    "stepfun": None,
    "grok-code": None,
    "nemotron-super": None,
}

print("\n--- Target Model Check ---")
for name, target_id in targets.items():
    if target_id:
        found = any(m.get("id") == target_id for m in models)
        print(f"  {name}: {target_id} -> {'FOUND' if found else 'NOT FOUND'}")
    else:
        # Search by pattern
        matches = [m.get("id") for m in models if name.lower() in m.get("id", "").lower()]
        if matches:
            targets[name] = matches[0]
            print(f"  {name}: found -> {matches[0]}")
        else:
            print(f"  {name}: NOT FOUND")

print("\nDone!")