"""Minimal retry - direct NVIDIA NIM API calls, reusable clients, generous timeouts.

Fixes over the previous version:
  * Read timeout raised to 300s (a 550B reasoning model can exceed 120s).
  * A single shared HTTP client pool is reused for the whole run instead of
    creating (and leaking) a fresh provider for every retry attempt.
  * Removed duplicated function definitions and the ``condition`` NameError
    that crashed every non-C0 retry.
"""

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

from dotenv import load_dotenv
load_dotenv()

from eval.common import load_config, ensure_dirs, config_dirs, read_jsonl
from eval.evidence import EvidenceProvider
from eval.llm.prompts import prompt_c0, prompt_c0b, prompt_c1, prompt_c2, parse_output
import httpx

MODEL = "nvidia/nemotron-3-ultra-550b-a55b"
REQUEST_TIMEOUT = float(os.getenv("NVIDIA_REQUEST_TIMEOUT", "300"))
MAX_WORKERS = int(os.getenv("RETRY_WORKERS", "4"))


def cache_key(model, condition, prompt, scenario_id, repeat):
    payload = "\u241f".join([model, condition, prompt, scenario_id, str(repeat)])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_evidence_context(scenario, evidence):
    parts = []
    if "weather" in evidence:
        w = evidence["weather"]
        parts.append(f"WEATHER: avg_temp={w.get('avg_temp_c')}°C, total_rain={w.get('total_rainfall_mm')}mm, humidity={w.get('avg_humidity')}%, max_temp={w.get('max_temp_c')}°C, min_temp={w.get('min_temp_c')}°C")
    if "climate" in evidence:
        c = evidence["climate"]
        parts.append(f"CLIMATE: avg_temp={c.get('avg_temp_normal_c')}°C, avg_rainfall={c.get('avg_rainfall_normal_mm')}mm/month")
        if "monthly_avg_temp_c" in c:
            parts.append(f"MONTHLY_TEMPS: {c['monthly_avg_temp_c']}")
        if "monthly_avg_rainfall_mm" in c:
            parts.append(f"MONTHLY_RAINFALL: {c['monthly_avg_rainfall_mm']}")
    if "season" in evidence:
        s = evidence["season"]
        parts.append(f"SEASON: current={s.get('current_season')}, month={s.get('current_month')}")
    if "risk" in evidence:
        r = evidence["risk"]
        parts.append(f"RISK: drought_prob={r.get('drought_probability')}, flood_prob={r.get('flood_probability')}, heatwave_prob={r.get('heatwave_probability')}, drought_z={r.get('drought_z_score_30d')}, heatwave_sev={r.get('heatwave_severity')}, flood_prob_idx={r.get('flood_probability')}")
    if "soil" in evidence:
        s = evidence["soil"]
        parts.append(f"SOIL: district={s.get('district')}, dominant={s.get('dominant_soil')}, characteristics={s.get('soil_characteristics')}")
    if "crop_score" in evidence:
        cs = evidence["crop_score"]
        if "ranked_crops" in cs:
            top = cs["ranked_crops"][:10]
            crops = ", ".join([f"{c['crop']}({c['total_score']:.2f})" for c in top])
            parts.append(f"CROP_SCORES: {crops}")
    return "\n".join(parts)


def build_prompt(condition, scenario, evidence=None):
    if condition == "C0":
        base = prompt_c0(scenario)
    elif condition == "C0b":
        base = prompt_c0b(scenario)
    elif condition == "C1":
        base = prompt_c1(scenario, evidence)
    elif condition == "C2":
        base = prompt_c2(scenario)
    else:
        raise ValueError(f"Unknown condition: {condition}")

    ctx = build_evidence_context(scenario, evidence or {})
    if ctx:
        lines = base.split("\n")
        return lines[0] + "\n\nEVIDENCE:\n" + ctx + "\n\n" + "\n".join(lines[1:])
    return base


class SimpleProvider:
    """Round-robin over API keys using a long-lived, reusable client pool."""

    def __init__(self, cfg, max_workers=MAX_WORKERS):
        self.cfg = cfg
        self.base_url = cfg["model"].get("nvidia", {}).get("base_url", "https://integrate.api.nvidia.com/v1")
        self.api_keys = self._load_api_keys()
        if not self.api_keys:
            raise RuntimeError("No NVIDIA API keys found in environment.")
        self._key_index = 0
        self._key_lock = threading.Lock()

        self._clients = []
        for key in self.api_keys:
            self._clients.append(
                httpx.Client(
                    base_url=self.base_url,
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    timeout=httpx.Timeout(REQUEST_TIMEOUT, connect=15.0),
                    limits=httpx.Limits(
                        max_connections=max_workers,
                        max_keepalive_connections=max_workers,
                    ),
                )
            )

    @staticmethod
    def _load_api_keys():
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
        seen, unique = set(), []
        for k in keys:
            if k not in seen:
                seen.add(k)
                unique.append(k)
        return unique

    def _get_next_client(self):
        with self._key_lock:
            client = self._clients[self._key_index]
            self._key_index = (self._key_index + 1) % len(self._clients)
            return client

    def run(self, prompt, use_mcp=False, max_attempts=3):
        system_msg = {
            "role": "system",
            "content": "You are an agricultural advisor that outputs ONLY a valid JSON object. "
                       "Never include any text, explanation, reasoning, or formatting outside the JSON. "
                       "Your response must start with { and end with }. Nothing else.",
        }
        messages = [system_msg, {"role": "user", "content": prompt}]
        payload = {
            "model": MODEL,
            "messages": messages,
            "temperature": 0.2,
            "top_p": 1.0,
            "max_tokens": 4096,
        }

        start_time = time.perf_counter()
        data = None
        last_error = None

        for attempt in range(max_attempts):
            client = self._get_next_client()
            try:
                resp = client.post("/chat/completions", json=payload, timeout=REQUEST_TIMEOUT)
                if resp.status_code == 429:
                    wait = float(resp.headers.get("retry-after") or 0) or (2 ** attempt) * 2
                    time.sleep(min(wait, 60))
                    last_error = f"HTTP 429 rate limited"
                    continue
                if resp.status_code in (402, 403, 404):
                    return {"error": f"HTTP {resp.status_code}: {resp.text[:150]}", "text": "",
                            "latency_s": time.perf_counter() - start_time}
                if resp.status_code >= 500:
                    last_error = f"HTTP {resp.status_code}"
                    time.sleep(min((2 ** attempt) * 2, 60))
                    continue
                resp.raise_for_status()
                data = resp.json()
                break
            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
                if attempt < max_attempts - 1:
                    time.sleep(min((2 ** attempt) * 2, 30))

        if data is None:
            return {"error": last_error or "Max retries", "text": "",
                    "latency_s": time.perf_counter() - start_time}

        message = data["choices"][0]["message"]
        usage = data.get("usage", {})
        return {
            "text": message.get("content") or "",
            "tokens_in": usage.get("prompt_tokens", 0),
            "tokens_out": usage.get("completion_tokens", 0),
            "reasoning_tokens": usage.get("reasoning_tokens", 0),
            "latency_s": time.perf_counter() - start_time,
            "tool_calls": 0,
            "error": None,
        }

    def close(self):
        for client in self._clients:
            client.close()


def _latest_run_with_failures():
    runs_dir = Path("eval/runs")
    best = None
    for d in runs_dir.iterdir():
        if not (d.is_dir() and d.name.startswith("full_nemotron-3-ultra_")):
            continue
        results_file = d / "results.json"
        if not results_file.exists():
            continue
        try:
            with results_file.open() as f:
                data = json.load(f)
        except Exception:
            continue
        if len(data) >= 100:
            failed = {}
            for r in data:
                if r.get("error"):
                    key = (r["scenario_id"], r["condition"], r.get("repeat", 0))
                    failed.setdefault(key, r)
            if failed and (best is None or len(failed) > best[2]):
                best = (d, data, len(failed))
    return best


def main():
    cfg = load_config()
    ensure_dirs(cfg)

    found = _latest_run_with_failures()
    if not found:
        print("No previous runs with failures found")
        return

    latest_run, results, _ = found
    final_file = latest_run / "results.json"

    failed = {}
    for r in results:
        if r.get("error"):
            key = (r["scenario_id"], r["condition"], r.get("repeat", 0))
            failed.setdefault(key, r)

    if not failed:
        print("No failed calls to retry")
        return

    print(f"Run: {latest_run}")
    print(f"Retrying {len(failed)} failed calls with {MAX_WORKERS} workers "
          f"(timeout {REQUEST_TIMEOUT:.0f}s)...")
    print("=" * 60)

    scenarios = read_jsonl(Path("eval/data/llm_subset.jsonl"))[:500]
    scenario_map = {s["scenario_id"]: s for s in scenarios}

    failed_scenario_ids = {k[0] for k in failed}
    print(f"Building evidence for {len(failed_scenario_ids)} failed scenarios...")
    evidence_provider = EvidenceProvider(load_config())
    evidence = {}
    for sid in failed_scenario_ids:
        sc = scenario_map.get(sid)
        if sc is not None:
            evidence[sid] = evidence_provider.build(sc)
    print("Evidence ready.")

    provider = SimpleProvider(cfg)
    print(f"Provider ready with {len(provider.api_keys)} API key(s). Starting...", flush=True)

    progress_lock = threading.RLock()
    stats = {"done": 0, "ok": 0, "fail": 0, "active": 0, "start": time.time(), "by_cond": Counter()}
    total = len(failed)

    def heartbeat():
        while True:
            time.sleep(15)
            with progress_lock:
                d, a = stats["done"], stats["active"]
                elapsed = time.time() - stats["start"]
            print(f"\n[heartbeat] {elapsed/60:.1f}min elapsed, {d}/{total} done, "
                  f"{a} in flight...", flush=True)

    def update_results_file(sid, cond, result_data):
        with progress_lock:
            try:
                with final_file.open() as f:
                    current = json.load(f)
                for i, r in enumerate(current):
                    if (r["scenario_id"] == sid and r["condition"] == cond
                            and r.get("repeat", 0) == 0 and r.get("error")):
                        current[i] = {
                            "model": MODEL,
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
                    json.dump(current, f, indent=2)
                temp_file.replace(final_file)
            except Exception as e:
                print(f"\nWarning: failed to update results file: {e}")

    def run_task(key):
        sid, cond, rep = key
        sc = scenario_map.get(sid)
        if sc is None:
            return sid, cond, False, None
        with progress_lock:
            stats["active"] += 1
        try:
            prompt = build_prompt(cond, sc, evidence.get(sid, {}))
            result = provider.run(prompt, use_mcp=False, max_attempts=3)
            if result.get("error"):
                print(f"  [{sid} {cond} r{rep}] FAILED: {str(result.get('error'))[:80]}", flush=True)
                return sid, cond, False, None
            return sid, cond, True, result
        finally:
            with progress_lock:
                stats["active"] -= 1

    try:
        threading.Thread(target=heartbeat, daemon=True).start()
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(run_task, key): key for key in failed}
            for future in as_completed(futures):
                sid, cond, success, result_data = future.result()
                with progress_lock:
                    stats["done"] += 1
                    if success:
                        stats["ok"] += 1
                        update_results_file(sid, cond, result_data)
                    else:
                        stats["fail"] += 1
                        stats["by_cond"][cond] += 1
                    done, ok, fail = stats["done"], stats["ok"], stats["fail"]
                print(f"  [{sid} {cond}] {'OK' if success else 'FAIL'} ({done}/{total} done, OK:{ok} Fail:{fail})",
                      flush=True)
    finally:
        provider.close()

    print("\nDone!")
    elapsed = time.time() - stats["start"]
    print(f"Final: OK={stats['ok']}, Failed={stats['fail']}, Time: {elapsed/60:.1f}min")
    print(f"By condition: {dict(stats['by_cond'])}")


if __name__ == "__main__":
    main()
