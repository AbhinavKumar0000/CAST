"""Ultra-robust retry with aggressive error handling and progress tracking."""

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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from eval.common import load_config, ensure_dirs, config_dirs, read_jsonl
from eval.scenarios import generate
from eval.evidence import EvidenceProvider
from eval.llm.prompts import prompt_c0, prompt_c0b, prompt_c1, prompt_c2, parse_output
import httpx


def cache_key(model, condition, prompt, scenario_id, repeat):
    payload = "\u241f".join([model, condition, prompt, scenario_id, str(repeat)])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class RobustProvider:
    def __init__(self, cfg):
        self.cfg = cfg
        self.base_url = cfg["model"].get("nvidia", {}).get("base_url", "https://integrate.api.nvidia.com/v1")
        self.api_keys = self._load_api_keys()
        self._key_index = 0
        self._key_lock = threading.Lock()
        self.model = "nvidia/nemotron-3-ultra-550b-a55b"
        self.temperature = 0.2
        self.top_p = 1.0
        self.max_output_tokens = 4096
        self.max_output_tokens_tools = 2048
        self.max_retries = 3
        self.backoff_base = 5.0
        self.backoff_max = 120.0
        
        self._clients = []
        for key in self.api_keys:
            client = httpx.Client(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                timeout=httpx.Timeout(180.0, connect=30.0),
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
    
    def _build_tools(self, use_mcp):
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
    
    def _execute_tool(self, name, args):
        from mcp_server import weather_tool, climate_tool, season_tool, risk_tool, soil_tool, crop_score_tool
        lat, lon = args.get("latitude"), args.get("longitude")
        if name == "weather_tool": return weather_tool.run(lat, lon)
        elif name == "climate_tool": return climate_tool.run(lat, lon)
        elif name == "season_tool": return season_tool.run(lat, lon)
        elif name == "risk_tool": return risk_tool.run(lat, lon)
        elif name == "get_soil_by_coordinates": return soil_tool.run(lat, lon)
        elif name == "crop_score": return crop_score_tool.run(latitude=lat, longitude=lon)
        return {"error": f"Unknown tool: {name}"}
    
    def run(self, prompt, use_mcp=False):
        system_msg = {"role": "system", "content": "You are an agricultural advisor that outputs ONLY a valid JSON object. Never include any text, explanation, reasoning, or formatting outside the JSON. Your response must start with { and end with }. Nothing else."}
        messages = [system_msg, {"role": "user", "content": prompt}]
        tools = self._build_tools(use_mcp)
        
        start_time = time.perf_counter()
        
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
            start_time = time.perf_counter()
            
            for attempt in range(3):  # 3 attempts per key
                client = self._get_next_client()
                try:
                    resp = client.post("/chat/completions", json=payload, timeout=180.0)
                    if resp.status_code == 429:
                        wait = 10.0
                        time.sleep(wait)
                        continue
                    if resp.status_code in (402, 403, 404):
                        return {"error": f"HTTP {resp.status_code}", "text": "", "latency_s": time.perf_counter() - start_time}
                    resp.raise_for_status()
                    data = resp.json()
                    break
                except Exception as e:
                    if attempt == 2:
                        return {"error": str(e), "text": "", "latency_s": time.perf_counter() - start_time}
                    wait = 5.0 * (attempt + 1)
                    time.sleep(wait)
            else:
                return {"error": "Max retries", "text": "", "latency_s": time.perf_counter() - start_time}
            
            choice = data["choices"][0]
            message = choice["message"]
            usage = data.get("usage", {})
            
            tool_calls = message.get("tool_calls", [])
            if tool_calls:
                messages.append({"role": "assistant", "content": message.get("content") or "", "tool_calls": tool_calls})
                for tc in tool_calls:
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
                "tool_calls": 0,
                "error": None,
            }
        
        return {"error": "Max rounds", "text": "", "latency_s": time.perf_counter() - start_time}
    
    def _execute_tool(self, name, args):
        from mcp_server import weather_tool, climate_tool, season_tool, risk_tool, soil_tool, crop_score_tool
        lat, lon = args.get("latitude"), args.get("longitude")
        if name == "weather_tool": return weather_tool.run(lat, lon)
        elif name == "climate_tool": return climate_tool.run(lat, lon)
        elif name == "season_tool": return season_tool.run(lat, lon)
        elif name == "risk_tool": return risk_tool.run(lat, lon)
        elif name == "get_soil_by_coordinates": return soil_tool.run(lat, lon)
        elif name == "crop_score": return crop_score_tool.run(latitude=lat, longitude=lon)
        return {"error": f"Unknown tool: {name}"}


def build_prompt(condition, scenario, evidence=None):
    if condition == "C0": return prompt_c0(scenario)
    elif condition == "C0b": return prompt_c0b(scenario)
    elif condition == "C1": return prompt_c1(scenario, evidence)
    elif condition == "C2": return prompt_c2(scenario)
    raise ValueError(f"Unknown condition: {condition}")


def main():
    import json, os, time, hashlib, threading
    from datetime import datetime, timezone
    from pathlib import Path
    from collections import Counter
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import httpx
    
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from eval.common import load_config, ensure_dirs, config_dirs, read_jsonl
    from eval.scenarios import generate
    from eval.evidence import EvidenceProvider
    from eval.llm.prompts import prompt_c0, prompt_c0b, prompt_c1, prompt_c2, parse_output
    import httpx
    
    cfg = load_config()
    ensure_dirs(cfg)
    dirs = config_dirs(cfg)
    
    # Find the latest run with results
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
    print(f"Building evidence for {len(failed_scenario_ids)} failed scenarios...")
    evidence = {}
    for sid in failed_scenario_ids:
        sc = next(s for s in scenarios if s['scenario_id'] == sid)
        evidence[sid] = EvidenceProvider(load_config()).build(sc)
    print("Evidence built.")
    
    cfg["model"]["nvidia"]["name"] = "nvidia/nemotron-3-ultra-550b-a55b"
    
    # Progress tracking
    progress_lock = threading.Lock()
    stats = {'done': 0, 'ok': 0, 'fail': 0, 'start': time.time(), 'by_cond': Counter()}
    total_retries = len(failed) * 3  # 3 retries per failed call
    print(f"Retrying {len(failed)} failed calls with 4 workers (3 retries each)...")
    print("=" * 60)
    
    def print_progress():
        with progress_lock:
            d, s, f = stats['done'], stats['ok'], stats['fail']
            elapsed = time.time() - stats['start']
            rate = stats['ok'] / elapsed * 60 if elapsed > 0 else 0
            pct = (d / (len(failed)*3)) * 100
            bar = "█" * int(d/(len(failed)*3)*20) + "░" * (20 - int(d/(len(failed)*3)*20))
            print(f"\rProgress: [{bar}] {d}/{len(failed)*3} ({pct:.1f}%) | OK:{stats['ok']} Fail:{stats['fail']} Rate:{rate:.1f}/min | Cond:{dict(stats['by_cond'])}", end="", flush=True)
    
    def update_results_file(sid, cond, result_data):
        with progress_lock:
            try:
                with final_file.open() as f:
                    current_results = json.load(f)
                
                for i, r in enumerate(current_results):
                    if (r["scenario_id"] == sid and 
                        r["condition"] == cond and 
                        r.get("repeat", 0) == 0 and
                        r.get("error")):
                        current_results[i] = {
                            "model": "nvidia/nemotron-3-ultra-550b-a55b",
                            "model_short": "nemotron-3-ultra",
                            "condition": cond,
                            "scenario_id": sid,
                            "repeat": 0,
                            "prompt_hash": "",
                            "text": result_data.get("text", ""),
                            "tokens_in": result_data.get("tokens_in", 0),
                            "tokens_out": result_data.get("tokens_out", 0),
                            "reasoning_tokens": result_data.get("reasoning_tokens", 0),
                            "latency_s": result_data.get("latency_s", 0),
                            "tool_calls": result_data.get("tool_calls", 0),
                            "error": None,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "parsed": parse_output(result_data.get("text", "")),
                        }
                        break
                
                temp_file = final_file.with_suffix(".tmp")
                with temp_file.open("w") as f:
                    json.dump(current_results, f, indent=2)
                temp_file.replace(final_file)
            except Exception as e:
                print(f"\nWarning: Failed to update results file: {e}")
    
    def run_task(task):
        sid, cond, rep, attempt = task
        sc = next(s for s in scenarios if s['scenario_id'] == sid)
        ev = evidence.get(sid, {})
        
        if cond == "C0": prompt = prompt_c0(sc)
        elif cond == "C0b": prompt = prompt_c0b(sc)
        elif cond == "C1": prompt = prompt_c1(sc, ev)
        elif cond == "C2": prompt = prompt_c2(sc)
        else: return (sid, cond, False, None)
        
        use_mcp = (cond == "C2")
        
        for retry in range(3):  # 3 retries per attempt
            provider = RobustProvider(load_config())
            result = provider.run(prompt_c0(sc) if cond=="C0" else prompt_c0b(sc) if cond=="C0b" else prompt_c1(sc,ev) if cond=="C1" else prompt_c2(sc), use_mcp)
            if not result.get("error"):
                return (sid, cond, True, result)
            print(f"  [{sid} {cond} r{attempt} retry{retry+1}] FAILED: {result.get('error')[:60]}")
            time.sleep(2)
        return (sid, cond, False, None)
    
    # Build evidence
    failed_scenario_ids = set(k[0] for k in failed.keys())
    print(f"Building evidence for {len(failed_scenario_ids)} failed scenarios...")
    for sid in failed_scenario_ids:
        sc = next(s for s in scenarios if s['scenario_id'] == sid)
        evidence[sid] = EvidenceProvider(load_config()).build(sc)
    print("Evidence ready.")
    
    # Load scenarios
    llm_subset = read_jsonl(Path("eval/data/llm_subset.jsonl"))
    scenarios = llm_subset[:500]
    
    total_retries = len(failed) * 3
    print(f"Starting {len(failed)*3} retries with 4 workers (3 retries each)...")
    print("=" * 60)
    
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(run_task, task): task for task in [(k[0], k[1], k[2], a) for k in failed for a in [1,2,3]]}
        for future in as_completed(futures):
            sid, cond, success, result_data = future.result()
            with progress_lock:
                stats['done'] += 1
                if success:
                    stats['ok'] += 1
                    update_results_file(sid, cond, future.result()[3])
                else:
                    stats['fail'] += 1
                    stats['by_cond'][cond] += 1
                print(f"  [{sid} {cond}] {'OK' if success else 'FAIL'}")
    
    print("\nDone!")
    elapsed = time.time() - stats['start']
    print(f"Final: OK={stats['ok']}, Failed={stats['fail']}, Time: {elapsed/60:.1f}min")
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
    
    main()