"""Fast parallel retry runner with clean progress tracking."""

import json
import os
import sys
import time
import hashlib
import threading
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from eval.common import load_config, ensure_dirs, config_dirs, write_json, read_jsonl
from eval.scenarios import generate
from eval.llm.nvidia_provider import NvidiaProvider
from eval.llm.prompts import prompt_c0, prompt_c0b, prompt_c1, prompt_c2, parse_output
from eval.evidence import EvidenceProvider


def cache_key(model: str, condition: str, prompt: str, scenario_id: str, repeat: int) -> str:
    payload = "\u241f".join([model, condition, prompt, scenario_id, str(repeat)])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_prompt(condition: str, scenario: dict, evidence: dict = None) -> str:
    if condition == "C0":
        return prompt_c0(scenario)
    elif condition == "C0b":
        return prompt_c0b(scenario)
    elif condition == "C1":
        return prompt_c1(scenario, evidence)
    elif condition == "C2":
        return prompt_c2(scenario)
    raise ValueError(f"Unknown condition: {condition}")


# Silent provider for worker threads
class SilentProvider:
    def __init__(self, cfg):
        self.cfg = cfg
        self.base_url = cfg["model"].get("nvidia", {}).get("base_url", "https://integrate.api.nvidia.com/v1")
        self.api_keys = self._load_api_keys()
        self._key_index = 0
        self._key_lock = threading.Lock()
        
        nvidia_cfg = cfg["model"].get("nvidia", {})
        self.model = nvidia_cfg.get("name", "nvidia/nemotron-3-ultra-550b-a55b")
        self.temperature = float(cfg["model"]["temperature"])
        self.top_p = float(cfg["model"]["top_p"])
        self.max_output_tokens = int(cfg["model"]["max_output_tokens"])
        self.max_output_tokens_tools = int(cfg["model"].get("max_output_tokens_tools", 2048))
        self.max_retries = 2
        self.backoff_base = 2.0
        self.backoff_max = 60.0
        self.jitter = True
        
        self._clients = []
        for key in self.api_keys:
            client = httpx.Client(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                timeout=httpx.Timeout(120.0, connect=10.0),
                limits=httpx.Limits(max_connections=1, max_keepalive_connections=1),
            )
            self._clients.append(client)
    
    def _load_api_keys(self):
        keys = []
        for i in range(1, 10):
            key = os.getenv(f"NVIDIA_API_KEY_{i}")
            if key:
                keys.append(key.strip())
        if not keys:
            keys_env = os.getenv("NVIDIA_API_KEYS", "")
            if keys_env:
                keys.extend([k.strip() for k in keys_env.split(",") if k.strip()])
        if not keys:
            single_key = os.getenv("NVIDIA_API_KEY", "")
            if single_key:
                keys.append(single_key.strip())
        seen = set()
        unique_keys = []
        for k in keys:
            if k not in seen:
                seen.add(k)
                unique_keys.append(k)
        return unique_keys
    
    def _get_next_client(self):
        with self._key_lock:
            client = self._clients[self._key_index]
            self._key_index = (self._key_index + 1) % len(self._clients)
            return client
    
    def _build_tools(self, use_mcp: bool):
        if not use_mcp:
            return []
        return [
            {"type": "function", "function": {"name": "weather_tool", "description": "Get weather.", "parameters": {"type": "object", "properties": {"latitude": {"type": "number"}, "longitude": {"type": "number"}}, "required": ["latitude", "longitude"]}}},
            {"type": "function", "function": {"name": "climate_tool", "description": "Get climate.", "parameters": {"type": "object", "properties": {"latitude": {"type": "number"}, "longitude": {"type": "number"}}, "required": ["latitude", "longitude"]}}},
            {"type": "function", "function": {"name": "season_tool", "description": "Get season.", "parameters": {"type": "object", "properties": {"latitude": {"type": "number"}, "longitude": {"type": "number"}}, "required": ["latitude", "longitude"]}}},
            {"type": "function", "function": {"name": "risk_tool", "description": "Get risk.", "parameters": {"type": "object", "properties": {"latitude": {"type": "number"}, "longitude": {"type": "number"}}, "required": ["latitude", "longitude"]}}},
            {"type": "function", "function": {"name": "get_soil_by_coordinates", "description": "Get soil.", "parameters": {"type": "object", "properties": {"latitude": {"type": "number"}, "longitude": {"type": "number"}}, "required": ["latitude", "longitude"]}}},
            {"type": "function", "function": {"name": "crop_score", "description": "Rank crops.", "parameters": {"type": "object", "properties": {"latitude": {"type": "number"}, "longitude": {"type": "number"}}, "required": ["latitude", "longitude"]}}},
        ]
    
    def _execute_tool(self, name: str, args: dict):
        from mcp_server import weather_tool, climate_tool, season_tool, risk_tool, soil_tool, crop_score_tool
        lat, lon = args.get("latitude"), args.get("longitude")
        if name == "weather_tool": return weather_tool.run(lat, lon)
        elif name == "climate_tool": return climate_tool.run(lat, lon)
        elif name == "season_tool": return season_tool.run(lat, lon)
        elif name == "risk_tool": return risk_tool.run(lat, lon)
        elif name == "get_soil_by_coordinates": return soil_tool.run(lat, lon)
        elif name == "crop_score": return crop_score_tool.run(latitude=lat, longitude=lon)
        return {"error": f"Unknown tool: {name}"}
    
    def run(self, prompt: str, use_mcp: bool = False):
        system_msg = {"role": "system", "content": "You are an agricultural advisor that outputs ONLY a valid JSON object. Never include any text, explanation, reasoning, or formatting outside the JSON. Your response must start with { and end with }. Nothing else."}
        messages = [system_msg, {"role": "user", "content": prompt}]
        tools = self._build_tools(use_mcp)
        
        start_time = time.perf_counter()
        total_tokens_in = total_tokens_out = total_reasoning = 0
        
        for round_num in range(10):
            max_tokens = 2048 if use_mcp else 4096
            payload = {
                "model": "nvidia/nemotron-3-ultra-550b-a55b",
                "messages": messages,
                "temperature": 0.2,
                "top_p": 1.0,
                "max_tokens": max_tokens,
            }
            if use_mcp:
                payload["tools"] = self._build_tools(True)
                payload["tool_choice"] = "auto"
            
            tool_calls_count = 0
            for attempt in range(2):
                client = self._get_next_client()
                try:
                    resp = client.post("/chat/completions", json=payload, timeout=120.0)
                    if resp.status_code == 429:
                        time.sleep(2)
                        continue
                    if resp.status_code in (402, 403, 404):
                        return {"error": f"HTTP {resp.status_code}", "text": "", "latency_s": time.perf_counter() - start_time}
                    resp.raise_for_status()
                    data = resp.json()
                    break
                except Exception as e:
                    if attempt == 1:
                        return {"error": str(e), "text": "", "latency_s": time.perf_counter() - start_time}
                    time.sleep(1)
            else:
                return {"error": "Max retries", "text": "", "latency_s": time.perf_counter() - start_time}
            
            choice = data["choices"][0]
            message = choice["message"]
            usage = data.get("usage", {})
            
            tool_calls = message.get("tool_calls", [])
            if tool_calls:
                messages.append({"role": "assistant", "content": message.get("content") or "", "tool_calls": tool_calls})
                for tc in tool_calls:
                    tool_calls_count += 1
                    fn = tc["function"]
                    args = json.loads(fn["arguments"])
                    result = self._execute_tool(fn["name"], args)
                    messages.append({"role": "tool", "tool_call_id": tc["id"], "content": json.dumps(result, ensure_ascii=False)})
                continue
            
            latency = time.perf_counter() - start_time
            usage = data.get("usage", {})
            return {
                "text": message.get("content") or "",
                "tokens_in": usage.get("prompt_tokens", 0),
                "tokens_out": usage.get("completion_tokens", 0),
                "reasoning_tokens": usage.get("reasoning_tokens", 0),
                "latency_s": latency,
                "tool_calls": tool_calls_count,
                "error": None,
            }
        
        return {"error": "Max rounds", "text": "", "latency_s": time.perf_counter() - start_time}


def cache_key(model, condition, prompt, scenario_id, repeat):
    payload = "\u241f".join([model, condition, prompt, scenario_id, str(repeat)])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_prompt(condition, scenario, evidence=None):
    if condition == "C0": return prompt_c0(scenario)
    elif condition == "C0b": return prompt_c0b(scenario)
    elif condition == "C1": return prompt_c1(scenario, evidence)
    elif condition == "C2": return prompt_c2(scenario)
    raise ValueError(f"Unknown condition: {condition}")


def run_fast_retry():
    import json, hashlib, threading
    from datetime import datetime, timezone
    from pathlib import Path
    from collections import Counter
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    # Load config
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from eval.common import load_config, ensure_dirs, config_dirs, read_jsonl
    from eval.scenarios import generate
    from eval.evidence import EvidenceProvider
    from eval.llm.prompts import prompt_c0, prompt_c0b, prompt_c1, prompt_c2, parse_output
    import httpx
    
    cfg = load_config()
    ensure_dirs(cfg)
    dirs = config_dirs(cfg)
    
    # Find latest run with most results
    runs_dir = Path("eval/runs")
    run_dirs = []
    for d in runs_dir.iterdir():
        if d.is_dir() and d.name.startswith("full_nemotron-3-ultra_"):
            results_file = d / "results.json"
            if results_file.exists():
                try:
                    with results_file.open() as f:
                        data = json.load(f)
                    if len(data) >= 100:
                        run_dirs.append((d, len(data)))
                except:
                    pass
    
    if not run_dirs:
        print("No previous runs found")
        return
    
    run_dirs.sort(key=lambda x: x[1], reverse=True)
    latest_run = run_dirs[0][0]
    final_file = latest_run / "results.json"
    
    with final_file.open() as f:
        results = json.load(f)
    
    # Find failed calls
    failed = {}
    for r in results:
        if r.get("error"):
            key = (r["scenario_id"], r["condition"], r.get("repeat", 0))
            if key not in failed:
                failed[key] = r
    
    if not failed:
        print("No failed calls to retry")
        return
    
    print(f"Retrying {len(failed)} failed calls with 4 workers...")
    print("=" * 60)
    
    # Load scenarios and evidence
    llm_subset = read_jsonl(Path("eval/data/llm_subset.jsonl"))
    scenarios = llm_subset[:500]
    scenario_map = {s['scenario_id']: s for s in scenarios}
    
    cfg = load_config()
    ensure_dirs(cfg)
    dirs = config_dirs(cfg)
    evidence_provider = EvidenceProvider(cfg)
    
    failed_scenario_ids = set(key[0] for key in failed.keys())
    print(f"Building evidence for {len(set(key[0] for key in failed.keys()))} failed scenarios...")
    evidence = {}
    for sid in {k[0] for k in failed.keys()}:
        sc = next(s for s in scenarios if s['scenario_id'] == sid)
        evidence[sid] = evidence_provider.build(sc)
    print("Evidence built.")
    
    # Setup
    cfg["model"]["nvidia"]["name"] = "nvidia/nemotron-3-ultra-550b-a55b"
    provider = SilentProvider(cfg)
    
    # Progress tracking
    progress_lock = threading.Lock()
    stats = {'done': 0, 'ok': 0, 'fail': 0, 'start': time.time(), 'by_cond': Counter()}
    total_retries = len(failed) * 2
    print(f"Retrying {len(failed)} failed calls with 4 workers (2 retries each = {len(failed)*2} total)...")
    print("=" * 60)
    
    def print_progress():
        with progress_lock:
            d, s, f = stats['done'], stats['ok'], stats['fail']
            elapsed = time.time() - stats['start']
            rate = s / elapsed * 60 if elapsed > 0 else 0
            pct = (d / (len(failed)*2)) * 100
            bar = "█" * int(pct/5) + "░" * (20 - int(pct/5))
            print(f"\rProgress: [{'█' * int(d/(len(failed)*2)*20)}░] {d}/{total_retries} ({pct:.1f}%) | OK:{s} Fail:{f} Rate:{rate:.1f}/min | Cond:{dict(stats['by_cond'])}", end="", flush=True)
    
    total_retries = len(failed) * 2
    tasks = []
    for (sid, cond, rep) in failed:
        for attempt in [1, 2]:
            tasks.append((sid, cond, 0, attempt))
    
    def run_task(task):
        sid, cond, rep, attempt = task
        sc = next(s for s in scenarios if s['scenario_id'] == sid)
        ev = evidence.get(sid, {})
        
        prompt = build_prompt(cond, sc, ev)
        use_mcp = (cond == "C2")
        
        for retry in range(2):
            provider = SilentProvider(load_config())
            result = provider.run(prompt_c0(scenario) if cond=="C0" else prompt_c0b(scenario) if cond=="C0b" else prompt_c1(scenario,ev) if cond=="C1" else prompt_c2(scenario), use_mcp)
            if not result.get("error"):
                return (scenario_id, cond, True)
            time.sleep(1)
        return (task[0], task[1], False)
    
    # Build evidence
    failed_scenario_ids = set(k[0] for k in failed.keys())
    print(f"Building evidence for {len(failed_scenario_ids)} scenarios...")
    for sid in failed_scenario_ids:
        sc = next(s for s in scenarios if s['scenario_id'] == sid)
        evidence[sid] = EvidenceProvider(load_config()).build(sc)
    print("Evidence ready.")
    
    print(f"Starting {len(failed)*2} retries with 4 workers...")
    print("=" * 60)
    
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(run_task, task): task for task in tasks}
        for future in as_completed(futures):
            sid, cond, success = future.result()
            with progress_lock:
                stats['done'] += 1
                if success:
                    stats['ok'] += 1
                else:
                    stats['fail'] += 1
                    stats['by_cond'][cond] += 1
                stats['done'] += 1
                print_progress()
    
    elapsed = time.time() - stats['start']
    print(f"\n\nDone! OK: {stats['ok']}, Failed: {stats['fail']}, Time: {elapsed/60:.1f}min")
    print(f"By condition: {dict(stats['by_cond'])}")


if __name__ == "__main__":
    import os, json, time, hashlib, threading
    from datetime import datetime, timezone
    from pathlib import Path
    from collections import Counter
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from eval.common import load_config, ensure_dirs, config_dirs, read_jsonl
    from eval.scenarios import generate
    from eval.evidence import EvidenceProvider
    from eval.llm.prompts import prompt_c0, prompt_c0b, prompt_c1, prompt_c2, parse_output
    import httpx
    
    run_fast_retry()