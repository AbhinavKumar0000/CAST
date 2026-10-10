"""Fetch and document NVIDIA NIM models list."""

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

api_key = os.getenv("NVIDIA_API_KEY")
if not api_key:
    print("ERROR: NVIDIA_API_KEY not set in environment")
    print("Please set it in your terminal: $env:NVIDIA_API_KEY='...'")
    sys.exit(1)

base_url = cfg["model"]["nvidia"].get("base_url", "https://integrate.api.nvidia.com/v1")

print(f"Fetching models from {base_url}/models...")
print(f"Using API key: {api_key[:8]}...")

headers = {"Authorization": f"Bearer {api_key}"}

try:
    with httpx.Client(base_url=base_url, headers=headers, timeout=30.0) as client:
        resp = client.get("/models")
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
raw_path = models_dir / "nvidia_models_raw.json"
raw_path.write_text(json.dumps(raw_output, indent=2))
print(f"Saved raw response to {raw_path}")

# Process models
models = data.get("data", [])
print(f"\nTotal models: {len(models)}")

# Filter for candidate models
candidate_ids = [
    "nvidia/nemotron-3-ultra-550b-a55b",
    "nvidia/nemotron-3-super-120b-a12b",
    "nvidia/nemotron-3-nano-30b-a3b",
    "deepseek-ai/deepseek-v3.2",
    "deepseek-ai/deepseek-v3.1-terminus",
    "moonshotai/kimi-k2-instruct-0905",
    "qwen",
    "meta/llama",
]

print("\n--- Candidate Model Check ---")
candidates_found = {}
for m in models:
    model_id = m.get("id", "")
    for cand in candidate_ids:
        if cand in model_id:
            candidates_found.setdefault(cand, []).append(model_id)

for cand, found_ids in candidates_found.items():
    print(f"  {cand}: {len(found_ids)} match(es)")
    for fid in found_ids:
        m = next((x for x in models if x.get("id") == fid), {})
        owned_by = m.get("owned_by", "unknown")
        context = m.get("context_length", "unknown")
        max_output = m.get("max_output_tokens", "unknown")
        print(f"    - {fid} (owned_by: {owned_by}, context: {context}, max_output: {max_output})")

# Show all models for reference
print("\n--- All Models ---")
for m in models:
    model_id = m.get("id", "")
    owned_by = m.get("owned_by", "unknown")
    context = m.get("context_length", "unknown")
    max_output = m.get("max_output_tokens", "unknown")
    print(f"  - {model_id} (owned_by: {owned_by}, context: {context}, max_output: {max_output})")

# Save candidate list
candidate_list = [{"pattern": c, "matches": candidates_found.get(c, [])} for c in candidate_ids]
cand_path = models_dir / "candidate_models.json"
cand_path.write_text(json.dumps({
    "fetched_at": datetime.now(timezone.utc).isoformat(),
    "candidates": candidate_list,
}, indent=2))
print(f"\nSaved candidate list to {cand_path}")

print("\nDone!")