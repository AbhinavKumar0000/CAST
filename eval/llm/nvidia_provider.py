"""NVIDIA NIM LLM provider (OpenAI-compatible chat completions with tools).

All benchmark LLM calls go through NVIDIA NIM free endpoints.
Reads NVIDIA_API_KEY from env var. Never logs or prints the key.
"""

from __future__ import annotations

import json
import os
import time
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

from eval.common import load_config

load_dotenv()


@dataclass
class LLMResult:
    text: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    reasoning_tokens: int = 0
    cost: float = 0.0
    latency_s: float = 0.0
    tool_calls: int = 0
    error: str | None = None
    raw_response: dict[str, Any] | None = None
    model: str = ""
    provider: str = "nvidia"

    @property
    def ok(self) -> bool:
        return self.error is None


class NvidiaProvider:
    """NVIDIA NIM provider - OpenAI-compatible /v1/chat/completions with tools."""

    def __init__(self, cfg: dict[str, Any] | None = None) -> None:
        self.cfg = cfg or load_config()
        self.base_url = self.cfg["model"].get("nvidia", {}).get("base_url", "https://integrate.api.nvidia.com/v1")
        self.api_key = os.getenv("NVIDIA_API_KEY")
        if not self.api_key:
            raise RuntimeError("NVIDIA_API_KEY not set in environment. Set it in your terminal: $env:NVIDIA_API_KEY='...'")
        
        nvidia_cfg = self.cfg["model"].get("nvidia", {})
        self.model = nvidia_cfg.get("name", "nvidia/nemotron-3-ultra-550b-a55b")
        self.temperature = float(self.cfg["model"]["temperature"])
        self.top_p = float(self.cfg["model"]["top_p"])
        self.max_output_tokens = int(self.cfg["model"]["max_output_tokens"])
        self.max_output_tokens_tools = int(self.cfg["model"].get("max_output_tokens_tools", 2048))
        
        # Rate limiting
        self.max_concurrency = int(self.cfg["cost_control"].get("max_concurrency", 2))
        self.requests_per_minute = int(self.cfg["cost_control"].get("requests_per_minute", 12))
        self.daily_budget = int(self.cfg["cost_control"].get("daily_request_budget", 4000))
        self.max_retries = int(self.cfg["cost_control"].get("max_retries", 5))
        self.backoff_base = float(self.cfg["cost_control"].get("backoff_base_seconds", 2.0))
        self.backoff_max = float(self.cfg["cost_control"].get("backoff_max_seconds", 60.0))
        self.jitter = self.cfg["cost_control"].get("jitter", True)
        
        # HTTP client with connection pooling
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            timeout=httpx.Timeout(120.0, connect=10.0),
            limits=httpx.Limits(max_connections=self.max_concurrency, max_keepalive_connections=self.max_concurrency),
        )

    def _build_tools(self, use_mcp: bool) -> list[dict[str, Any]]:
        """Build tool declarations for the model."""
        if not use_mcp:
            return []
        
        return [
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

    def _execute_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool call locally (for C2 - we call the actual tool functions)."""
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
            return {"error": f"Unknown tool: {name}", "tool": name}

    def run(self, prompt: str, agent: str = "", use_mcp: bool = False) -> LLMResult:
        """Run a single prompt through NVIDIA NIM with optional tool calling."""
        
        messages = [{"role": "user", "content": prompt}]
        tools = self._build_tools(use_mcp)
        tool_calls_count = 0
        total_tokens_in = 0
        total_tokens_out = 0
        total_reasoning = 0
        start_time = time.perf_counter()
        
        # Tool calling loop (max 10 rounds for 6 tools + synthesis)
        max_rounds = 10
        for round_num in range(max_rounds):
            # Use higher token limit for tool-calling rounds
            max_tokens = self.max_output_tokens_tools if tools else self.max_output_tokens
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": self.temperature,
                "top_p": self.top_p,
                "max_tokens": max_tokens,
            }
            if tools:
                payload["tools"] = tools
                payload["tool_choice"] = "auto"
            
            # Retry logic with exponential backoff
            last_error = None
            for attempt in range(self.max_retries):
                try:
                    resp = self._client.post("/chat/completions", json=payload)
                    
                    if resp.status_code == 429:
                        retry_after = resp.headers.get("retry-after")
                        wait = float(retry_after) if retry_after else self.backoff_base * (2 ** attempt)
                        if self.jitter:
                            wait *= (0.5 + random.random())
                        wait = min(wait, self.backoff_max)
                        time.sleep(wait)
                        continue
                    
                    if resp.status_code in (402, 403, 404):
                        # Partner-only or not accessible
                        return LLMResult(
                            error=f"Model not accessible: HTTP {resp.status_code} - {resp.text[:200]}",
                            latency_s=time.perf_counter() - start_time,
                            model=self.model,
                            provider="nvidia",
                        )
                    
                    resp.raise_for_status()
                    data = resp.json()
                    break
                    
                except httpx.HTTPStatusError as e:
                    last_error = e
                    if e.response.status_code >= 500:
                        wait = self.backoff_base * (2 ** attempt)
                        if self.jitter:
                            wait *= (0.5 + random.random())
                        wait = min(wait, self.backoff_max)
                        time.sleep(wait)
                        continue
                    raise
                except Exception as e:
                    last_error = e
                    wait = self.backoff_base * (2 ** attempt)
                    if self.jitter:
                        wait *= (0.5 + random.random())
                    wait = min(wait, self.backoff_max)
                    time.sleep(wait)
            else:
                return LLMResult(
                    error=f"Max retries exceeded: {last_error}",
                    latency_s=time.perf_counter() - start_time,
                    model=self.model,
                    provider="nvidia",
                )
            
            # Parse response
            choice = data["choices"][0]
            message = choice["message"]
            
            # Track tokens
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
                    args = json.loads(fn["arguments"])
                    
                    result = self._execute_tool(name, args)
                    
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps(result, ensure_ascii=False),
                    })
                
                continue
            
            # No tool calls - final response
            final_text = message.get("content") or ""
            latency = time.perf_counter() - start_time
            
            return LLMResult(
                text=final_text.strip(),
                tokens_in=total_tokens_in,
                tokens_out=total_tokens_out,
                reasoning_tokens=total_reasoning,
                latency_s=latency,
                tool_calls=tool_calls_count,
                raw_response=data,
                model=self.model,
                provider="nvidia",
            )
        
        return LLMResult(
            error="Max tool-calling rounds reached",
            latency_s=time.perf_counter() - start_time,
            model=self.model,
            provider="nvidia",
        )

    def close(self) -> None:
        self._client.close()

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