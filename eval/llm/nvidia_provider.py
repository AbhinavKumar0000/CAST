"""NVIDIA NIM LLM provider (OpenAI-compatible chat completions with tools).

All benchmark LLM calls go through NVIDIA NIM free endpoints.
Supports multiple API keys with round-robin rotation for rate limit bypass.
Reads keys from NVIDIA_API_KEYS env var (comma-separated) or NVIDIA_API_KEY (single).
"""

from __future__ import annotations

import json
import os
import time
import random
import threading
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

from eval.common import load_config
from eval.llm.budget import BudgetExceeded, DailyBudget

load_dotenv()

# Harness-fix ss8.10 (2026-10-13): stall fallback.
FORCE_FINAL_ROUND = 12  # after this many tool-loop rounds, send one final no-tools request
FINAL_JSON_INSTRUCTION = (
    "Do not call any tool. Provide the final JSON using the evidence gathered. "
    "Reply with the final JSON object only; no analysis or explanation text outside the JSON."
)


@dataclass
class LLMResult:
    text: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    reasoning_tokens: int = 0
    cost: float = 0.0
    latency_s: float = 0.0
    tool_calls: int = 0
    tool_log: list[dict[str, Any]] | None = None
    finish_reason: str = ""
    error: str | None = None
    error_type: str = ""
    raw_response: dict[str, Any] | None = None
    model: str = ""
    provider: str = "nvidia"
    unknown_tool_calls: int = 0          # harness-fix ss8.10: invalid/unknown tool-name calls
    forced_final: bool = False           # harness-fix ss8.10: tools disabled, force final JSON
    forced_final_reason: str = ""        # "two_consecutive_unknown" | "round12"
    truncated: bool = False              # finish_reason == "length" (completion cap hit)

    @property
    def ok(self) -> bool:
        return self.error is None


class NvidiaProvider:
    """NVIDIA NIM provider - OpenAI-compatible /v1/chat/completions with tools.
    
    Supports multiple API keys with round-robin rotation to bypass rate limits.
    Each request cycles to the next key automatically.
    """

    def __init__(self, cfg: dict[str, Any] | None = None, tool_runtime: Any = None,
                 allowed_tools: list[str] | None = None) -> None:
        self.cfg = cfg or load_config()
        self.base_url = self.cfg["model"].get("nvidia", {}).get("base_url", "https://integrate.api.nvidia.com/v1")
        self.tool_runtime = tool_runtime  # Phase 8: time-anchored offline runtime for C2a/C2b
        # Phase 8 STEP B: which tool names this provider instance may expose/serve.
        # None = the full six-tool set (C2a). C2b passes the five tools without crop_score.
        self.allowed_tools = allowed_tools
        
        # Load multiple API keys (comma-separated from NVIDIA_API_KEYS, or single from NVIDIA_API_KEY)
        self.api_keys = self._load_api_keys()
        if not self.api_keys:
            raise RuntimeError("No NVIDIA API keys found. Set NVIDIA_API_KEYS (comma-separated) or NVIDIA_API_KEY in environment.")
        
        self._key_index = 0
        self._key_lock = threading.Lock()
        
        nvidia_cfg = self.cfg["model"].get("nvidia", {})
        self.model = nvidia_cfg.get("name", "nvidia/nemotron-3-ultra-550b-a55b")
        self.temperature = float(self.cfg["model"]["temperature"])
        self.top_p = float(self.cfg["model"]["top_p"])
        self.max_output_tokens = int(self.cfg["model"]["max_output_tokens"])
        self.max_output_tokens_tools = int(self.cfg["model"].get("max_output_tokens_tools", 2048))
        # Phase 8 STEP A: tool-loop cap is configurable and reported. Raised to 15
        # (previously hard-coded 10) so 6-tool scenarios have room for the
        # mandated calls plus a synthesis round.
        self.max_tool_rounds = int(self.cfg["model"].get("max_tool_rounds", 15))
        
        # Rate limiting (per key)
        self.max_concurrency = int(self.cfg["cost_control"].get("max_concurrency", 2))
        self.requests_per_minute = int(self.cfg["cost_control"].get("requests_per_minute", 12))
        self.daily_budget = int(self.cfg["cost_control"].get("daily_request_budget", 4000))
        # PROTOCOL 8.12: enforce the 4,000/UTC-day HTTP budget (hard stop). Shared
        # across provider instances via a persisted UTC-day counter.
        self._budget = DailyBudget(self.daily_budget)
        self._budget.register_accounts(len(self.api_keys))
        self.max_retries = int(self.cfg["cost_control"].get("max_retries", 5))
        self.backoff_base = float(self.cfg["cost_control"].get("backoff_base_seconds", 2.0))
        self.backoff_max = float(self.cfg["cost_control"].get("backoff_max_seconds", 60.0))
        self.jitter = self.cfg["cost_control"].get("jitter", True)
        
        # Create one HTTP client per key
        request_timeout = float(
            os.getenv("NVIDIA_REQUEST_TIMEOUT", nvidia_cfg.get("request_timeout_seconds", 120))
        )
        self._clients = []
        for key in self.api_keys:
            client = httpx.Client(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                timeout=httpx.Timeout(request_timeout, connect=15.0),
                limits=httpx.Limits(max_connections=self.max_concurrency, max_keepalive_connections=self.max_concurrency),
            )
            self._clients.append(client)
        
        print(f"[NvidiaProvider] Initialized with {len(self.api_keys)} API keys, request_timeout={request_timeout:.0f}s, round-robin rotation enabled")

    def _load_api_keys(self) -> list[str]:
        """Load API keys from environment variables.
        
        Loads from NVIDIA_API_KEY_1, NVIDIA_API_KEY_2, NVIDIA_API_KEY_3, NVIDIA_API_KEY_4
        Also supports legacy NVIDIA_API_KEYS (comma-separated) and NVIDIA_API_KEY for backwards compatibility.
        """
        keys = []
        
        # Primary: numbered keys (NVIDIA_API_KEY_1, NVIDIA_API_KEY_2, etc.)
        for i in range(1, 10):  # Support up to 9 keys
            key = os.getenv(f"NVIDIA_API_KEY_{i}")
            if key:
                keys.append(key.strip())
        
        # Fallback: comma-separated NVIDIA_API_KEYS
        if not keys:
            keys_env = os.getenv("NVIDIA_API_KEYS", "")
            if keys_env:
                keys.extend([k.strip() for k in keys_env.split(",") if k.strip()])
        
        # Fallback: single NVIDIA_API_KEY
        if not keys:
            single_key = os.getenv("NVIDIA_API_KEY", "")
            if single_key:
                keys.append(single_key.strip())
        
        # Remove duplicates while preserving order
        seen = set()
        unique_keys = []
        for k in keys:
            if k not in seen:
                seen.add(k)
                unique_keys.append(k)
        
        return unique_keys

    def _get_next_client(self) -> tuple[int, httpx.Client]:
        """Get next (account_index, client) in round-robin fashion."""
        with self._key_lock:
            idx = self._key_index
            client = self._clients[idx]
            self._key_index = (idx + 1) % len(self._clients)
            return idx, client

    def _build_tools(self, use_mcp: bool, allowed: list[str] | None = None) -> list[dict[str, Any]]:
        """Build tool declarations for the model.

        ``allowed`` filters which tools are exposed (Phase 8 STEP B). C2b excludes
        crop_score; C2a exposes all six.
        """
        if not use_mcp:
            return []
        allowed = allowed if allowed is not None else self.allowed_tools
        all_tools = [
            {
                "type": "function",
                "function": {
                    "name": "weather_tool",
                    "description": "Get weather forecast data for the coordinates: temperature, rainfall, humidity, and precipitation probability.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "latitude": {"type": "number", "description": "Latitude in decimal degrees"},
                            "longitude": {"type": "number", "description": "Longitude in decimal degrees"},
                        },
                        "required": ["latitude", "longitude"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "climate_tool",
                    "description": "Get climate normals for the region: average rainfall, average temperature, and monthly normals.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "latitude": {"type": "number", "description": "Latitude in decimal degrees"},
                            "longitude": {"type": "number", "description": "Longitude in decimal degrees"},
                        },
                        "required": ["latitude", "longitude"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "season_tool",
                    "description": "Get the current cropping season in IST: Kharif, Rabi, or Zaid.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "latitude": {"type": "number", "description": "Latitude in decimal degrees"},
                            "longitude": {"type": "number", "description": "Longitude in decimal degrees"},
                        },
                        "required": ["latitude", "longitude"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "risk_tool",
                    "description": "Get drought, flood, and heatwave risk analysis for the location.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "latitude": {"type": "number", "description": "Latitude in decimal degrees"},
                            "longitude": {"type": "number", "description": "Longitude in decimal degrees"},
                        },
                        "required": ["latitude", "longitude"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_soil_by_coordinates",
                    "description": "Get district, dominant soil, soil characteristics, and agricultural suitability for a location in Madhya Pradesh.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "latitude": {"type": "number", "description": "Latitude in decimal degrees"},
                            "longitude": {"type": "number", "description": "Longitude in decimal degrees"},
                        },
                        "required": ["latitude", "longitude"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "crop_score",
                    "description": "Rank the best candidate crops for the coordinates using deterministic scoring over weather, climate, soil, season, and risk evidence.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "latitude": {"type": "number", "description": "Latitude in decimal degrees"},
                            "longitude": {"type": "number", "description": "Longitude in decimal degrees"},
                        },
                        "required": ["latitude", "longitude"],
                    },
                },
            },
        ]
        if allowed is not None:
            return [t for t in all_tools if t["function"]["name"] in allowed]
        return all_tools

    def _execute_tool(self, name: str, args: dict[str, Any], scenario: dict[str, Any] | None = None,
                      allowed: list[str] | None = None) -> dict[str, Any]:
        """Execute a tool call for a scenario.

        Phase 8 STEP A: when an offline ``tool_runtime`` is configured (C2a/C2b), tool
        calls are served by the time-anchored wrapper (injected clock + cached weather,
        no live API, no datetime.now). The legacy live path remains for backward
        compatibility with old C2 runs.
        Phase 8 STEP B: ``allowed`` (per-call tool set) blocks serving tools that are not
        part of the condition's tool set (e.g. crop_score for C2b).
        """
        servable = allowed if allowed is not None else self.allowed_tools
        if servable is not None and name not in servable:
            return {
                "error": (f"Unknown tool '{name}'. Valid tools: {', '.join(servable)}. "
                          "Do not call a tool for the final answer; reply with the JSON object now."),
                "tool": name,
                "unknown": True,
            }
        if self.tool_runtime is not None and scenario is not None:
            return self.tool_runtime.call(scenario, name, args)

        from mcp_server import weather_tool, climate_tool, season_tool, risk_tool, soil_tool, crop_score_tool

        lat = args.get("latitude")
        lon = args.get("longitude")

        if name == "weather_tool":
            return weather_tool.run(lat, lon)
        elif name == "climate_tool":
            return climate_tool.run(lat, lon)
        elif name == "season_tool":
            return season_tool.run(lat, lon)
        elif name == "risk_tool":
            return risk_tool.run(lat, lon)
        elif name == "get_soil_by_coordinates":
            return soil_tool.run(lat, lon)
        elif name == "crop_score":
            return crop_score_tool.run(latitude=lat, longitude=lon)
        else:
            return {
                "error": (f"Unknown tool '{name}'. "
                          "Do not call a tool for the final answer; reply with the JSON object now."),
                "tool": name,
                "unknown": True,
            }

    def run(self, prompt: str, agent: str = "", use_mcp: bool = False,
            scenario: dict[str, Any] | None = None,
            allowed_tools: list[str] | None = None,
            max_output_tokens: int | None = None) -> LLMResult:
        """Run a single prompt through NVIDIA NIM with optional tool calling.

        ``scenario`` is required for tool conditions when the offline time-anchored
        runtime is configured (Phase 8 STEP A); tool calls are then executed as of the
        scenario's date with no live API or wall-clock dependency.
        ``allowed_tools`` (STEP B) restricts the tool schema exposed to the model.
        ``max_output_tokens`` (2026-10-13 ss8.10 amend) overrides the completion cap
        per call; used to give tool-condition prompts WITHOUT tools (C1a/C1b) the
        raised 8192 cap (``max_output_tokens_tools``) even though no tools are in the
        payload. C0/C0b pass None -> non-tool cap 4096.

        Harness-fix ss8.10 (2026-10-13): unknown tool calls return a tool error that
        lists the valid tools and instructs the model to reply with the JSON object
        now; two consecutive unknown-tool calls (or reaching round 12) trigger one final
        request with tools disabled (``forced_final``) instructing the model to emit the
        final JSON from gathered evidence. max_tool_rounds stays 15 (unchanged).
        """

        # System message to enforce JSON-only output
        system_msg = {
            "role": "system",
            "content": "You are an agricultural advisor that outputs ONLY a valid JSON object. "
                       "Never include any text, explanation, reasoning, or formatting outside the JSON. "
                       "Your response must start with { and end with }. Nothing else."
        }
        messages = [system_msg, {"role": "user", "content": prompt}]
        tools = self._build_tools(use_mcp, allowed_tools)
        servable = allowed_tools if allowed_tools is not None else self.allowed_tools
        tool_calls_count = 0
        tool_log: list[dict[str, Any]] = []
        total_tokens_in = 0
        total_tokens_out = 0
        total_reasoning = 0
        finish_reason = ""
        consecutive_unknown = 0
        unknown_tool_calls = 0
        start_time = time.perf_counter()

        def finalize(text: str, data: dict[str, Any] | None = None,
                     forced_final: bool = False, forced_final_reason: str = "") -> LLMResult:
            return LLMResult(
                text=text.strip(),
                tokens_in=total_tokens_in,
                tokens_out=total_tokens_out,
                reasoning_tokens=total_reasoning,
                latency_s=time.perf_counter() - start_time,
                tool_calls=tool_calls_count,
                tool_log=tool_log,
                finish_reason=finish_reason,
                truncated=(finish_reason == "length"),
                unknown_tool_calls=unknown_tool_calls,
                forced_final=forced_final,
                forced_final_reason=forced_final_reason,
                raw_response=data,
                model=self.model,
                provider="nvidia",
            )

        def error_result(msg: str, etype: str) -> LLMResult:
            return LLMResult(
                error=msg,
                error_type=etype,
                latency_s=time.perf_counter() - start_time,
                model=self.model,
                provider="nvidia",
                tool_calls=tool_calls_count,
                tool_log=tool_log,
                finish_reason=finish_reason,
                truncated=(finish_reason == "length"),
                unknown_tool_calls=unknown_tool_calls,
                forced_final=False,
                forced_final_reason="",
            )

        def post(req_messages: list[dict[str, Any]], req_tools: list[dict[str, Any]],
                 req_max_tokens: int) -> tuple[dict[str, Any] | None, float, str, str]:
            """POST one chat request with retries/backoff/key rotation on 429/5xx.
            Returns (data, req_latency_s, error, error_type); error is '' on success."""
            payload = {
                "model": self.model,
                "messages": req_messages,
                "temperature": self.temperature,
                "top_p": self.top_p,
                "max_tokens": req_max_tokens,
            }
            if req_tools:
                payload["tools"] = req_tools
                payload["tool_choice"] = "auto"

            last_error = ""
            for attempt in range(self.max_retries):
                acct, client = self._get_next_client()
                try:
                    # PROTOCOL 8.12: count every HTTP attempt (incl. retries) against
                    # the UTC-day budget, PER ACCOUNT (each key = separate account);
                    # hard-stop with a clean, resumable message.
                    try:
                        self._budget.reserve(account=acct)
                    except BudgetExceeded as be:
                        return None, 0.0, str(be), "budget_exceeded"
                    req_start = time.perf_counter()
                    resp = client.post("/chat/completions", json=payload)
                    req_latency_s = time.perf_counter() - req_start

                    if resp.status_code == 429:
                        retry_after = resp.headers.get("retry-after")
                        wait = float(retry_after) if retry_after else self.backoff_base * (2 ** attempt)
                        if self.jitter:
                            wait *= (0.5 + random.random())
                        wait = min(wait, self.backoff_max)
                        time.sleep(wait)
                        continue

                    if resp.status_code in (402, 403, 404):
                        return None, req_latency_s, f"Model not accessible: HTTP {resp.status_code} - {resp.text[:200]}", "model_failure"

                    resp.raise_for_status()
                    return resp.json(), req_latency_s, "", ""

                except httpx.HTTPStatusError as e:
                    last_error = str(e)
                    if e.response.status_code >= 500:
                        wait = self.backoff_base * (2 ** attempt)
                        if self.jitter:
                            wait *= (0.5 + random.random())
                        wait = min(wait, self.backoff_max)
                        time.sleep(wait)
                        continue
                    return None, 0.0, last_error, f"api_status_{e.response.status_code}"
                except Exception as e:
                    last_error = str(e)
                    wait = self.backoff_base * (2 ** attempt)
                    if self.jitter:
                        wait *= (0.5 + random.random())
                    wait = min(wait, self.backoff_max)
                    time.sleep(wait)
            return None, 0.0, f"Max retries exceeded: {last_error}", "model_failure"

        # Tool calling loop (cap from config; reported in run output).
        # Harness-fix ss8.10: at round 12 (i.e. after 12 tool rounds) force a final
        # no-tools request so runs never burn all 15 rounds without a final answer.
        max_rounds = self.max_tool_rounds
        for round_num in range(max_rounds):
            if round_num >= FORCE_FINAL_ROUND:
                messages.append({"role": "user", "content": FINAL_JSON_INSTRUCTION})
                data, rl, err, etype = post(messages, [], self.max_output_tokens_tools)
                if err:
                    return error_result(err, etype)
                choice = data["choices"][0]
                message = choice["message"]
                finish_reason = str(choice.get("finish_reason") or "")
                usage = data.get("usage", {})
                total_tokens_in += usage.get("prompt_tokens", 0)
                total_tokens_out += usage.get("completion_tokens", 0)
                total_reasoning += usage.get("reasoning_tokens", 0)
                return finalize(message.get("content") or "", data,
                                forced_final=True, forced_final_reason="round12")

            max_tokens = (self.max_output_tokens_tools if tools
                          else (max_output_tokens if max_output_tokens is not None
                                else self.max_output_tokens))
            data, req_latency_s, err, etype = post(messages, tools, max_tokens)
            if err:
                return error_result(err, etype)

            choice = data["choices"][0]
            message = choice["message"]
            finish_reason = str(choice.get("finish_reason") or "")

            usage = data.get("usage", {})
            total_tokens_in += usage.get("prompt_tokens", 0)
            total_tokens_out += usage.get("completion_tokens", 0)
            total_reasoning += usage.get("reasoning_tokens", 0)

            tool_calls = message.get("tool_calls", [])

            if tool_calls:
                messages.append({
                    "role": "assistant",
                    "content": message.get("content") or "",
                    "tool_calls": tool_calls,
                })

                for tc in tool_calls:
                    tool_calls_count += 1
                    fn = tc["function"]
                    name = fn["name"]
                    try:
                        args = json.loads(fn["arguments"])
                    except json.JSONDecodeError:
                        args = {"_unparsed": fn["arguments"][:200], "latitude": None, "longitude": None}

                    tool_latency_start = time.perf_counter()
                    result = self._execute_tool(name, args, scenario, allowed=servable)
                    tool_latency_s = time.perf_counter() - tool_latency_start

                    is_unknown = bool(result.get("unknown"))
                    if is_unknown:
                        unknown_tool_calls += 1
                        consecutive_unknown += 1
                    else:
                        consecutive_unknown = 0

                    try:
                        h = hashlib.sha256(
                            json.dumps(result, sort_keys=True, ensure_ascii=False).encode("utf-8")
                        ).hexdigest()[:16]
                    except Exception:
                        h = "n/a"

                    tool_log.append({
                        "round": round_num,
                        "name": name,
                        "args": args,
                        "output_hash": h,
                        "latency_s": round(tool_latency_s, 4),
                        "llm_request_latency_s": round(req_latency_s, 3),
                        "finish_reason": finish_reason,
                        "unknown_tool": is_unknown,
                    })

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps(result, ensure_ascii=False),
                    })

                # Stall fallback (ss8.10): two consecutive unknown-tool calls -> one
                # final request with tools disabled.
                if consecutive_unknown >= 2:
                    messages.append({"role": "user", "content": FINAL_JSON_INSTRUCTION})
                    data2, _, err2, etype2 = post(messages, [], self.max_output_tokens_tools)
                    if err2:
                        return error_result(err2, etype2)
                    choice2 = data2["choices"][0]
                    message2 = choice2["message"]
                    finish_reason = str(choice2.get("finish_reason") or "")
                    usage2 = data2.get("usage", {})
                    total_tokens_in += usage2.get("prompt_tokens", 0)
                    total_tokens_out += usage2.get("completion_tokens", 0)
                    total_reasoning += usage2.get("reasoning_tokens", 0)
                    return finalize(message2.get("content") or "", data2,
                                    forced_final=True, forced_final_reason="consecutive_unknown")

                continue

            # No tool calls - final response
            return finalize(message.get("content") or "", data)

        return LLMResult(
            error="max_rounds_reached",
            error_type="max_rounds_reached",
            latency_s=time.perf_counter() - start_time,
            model=self.model,
            provider="nvidia",
            tool_calls=tool_calls_count,
            tool_log=tool_log,
            finish_reason=finish_reason,
            truncated=(finish_reason == "length"),
            unknown_tool_calls=unknown_tool_calls,
            forced_final=False,
            forced_final_reason="",
        )

    def close(self) -> None:
        for client in self._clients:
            client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def get_provider(cfg: dict[str, Any] | None = None):
    """Factory function to get the configured provider."""
    cfg = cfg or load_config()
    provider = cfg["model"].get("provider", "nvidia")
    
    if provider == "nvidia":
        return NvidiaProvider(cfg)
    elif provider == "gemini":
        from eval.llm.provider import GeminiProvider
        return GeminiProvider(cfg)
    elif provider == "opencode":
        from eval.llm.provider import OpencodeProvider
        return OpencodeProvider(cfg)
    elif provider == "kilo":
        from eval.llm.kilo_provider import KiloProvider
        return KiloProvider(cfg)
    else:
        raise ValueError(f"Unknown provider: {provider}")