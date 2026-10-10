"""LLM provider abstraction (STEP 4/5).

Two backends behind one blocking `run()`:
  * OpencodeProvider  — shells out to the opencode CLI (`opencode run --format json`).
                        Default; needs no paid key. Uses project config directories for C2.
  * GeminiProvider    — Google Generative Language API (needs GEMINI_API_KEY).

Every call is content-hash cached (see cache.py) by the runner, so a successful
call is never repeated.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from eval.common import load_config, resolve


@dataclass
class LLMResult:
    text: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    cost: float = 0.0
    latency_s: float = 0.0
    tool_calls: int = 0
    error: str | None = None
    raw_events: list[dict[str, Any]] = field(default_factory=list)
    model: str = ""
    agent: str = ""

    @property
    def ok(self) -> bool:
        return self.error is None


class OpencodeProvider:
    """Runs a single prompt through `opencode run --format json`."""

    def __init__(self, cfg: dict[str, Any] | None = None) -> None:
        self.cfg = cfg or load_config()
        oc = self.cfg["model"]["opencode"]
        self.binary = oc.get("binary", "opencode")
        self.extra_args = list(oc.get("extra_args", ["--pure"]))
        self.timeout = int(oc.get("timeout_seconds", 300))
        config_plain_path = resolve(oc["config_plain"])
        config_mcp_path = resolve(oc["config_mcp"])
        self.project_plain = config_plain_path.parent
        self.project_mcp = config_mcp_path.parent
        self.model = self.cfg["model"]["name"]

    def _project_for(self, use_mcp: bool) -> Path:
        return self.project_mcp if use_mcp else self.project_plain

    def run(self, prompt: str, agent: str, use_mcp: bool = False) -> LLMResult:
        env = dict(os.environ)
        env["OPENCODE_DISABLE_AUTOUPDATE"] = "true"
        env.setdefault("OPENCODE_DISABLE_CLAUDE_CODE_SKILLS", "1")
        env.setdefault("OPENCODE_DISABLE_EXTERNAL_SKILLS", "1")

        project_dir = self._project_for(use_mcp)
        cmd = [self.binary, "run", *self.extra_args, "--format", "json", "--dir", str(project_dir), "--agent", agent, "-m", self.model, prompt]
        t0 = time.perf_counter()
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=self.timeout, env=env)
        except subprocess.TimeoutExpired:
            return LLMResult(error="timeout", latency_s=time.perf_counter() - t0, model=self.model, agent=agent)
        latency = time.perf_counter() - t0
        if proc.returncode != 0:
            return LLMResult(
                error=f"exit {proc.returncode}: {(proc.stderr or '')[:300]}",
                latency_s=latency,
                model=self.model,
                agent=agent,
            )
        return self._parse_jsonl(proc.stdout, latency, agent)

    def _parse_jsonl(self, stdout: str, latency: float, agent: str) -> LLMResult:
        text_parts: list[str] = []
        events: list[dict[str, Any]] = []
        tokens_in = tokens_out = cost = 0.0
        tool_calls = 0
        for line in stdout.splitlines():
            line = line.strip()
            if not line or not line.startswith("{"):
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            events.append(ev)
            etype = ev.get("type")
            part = ev.get("part") or {}
            if etype == "text" and part.get("text") and not part.get("synthetic"):
                text_parts.append(part["text"])
            elif etype == "tool":
                tool_calls += 1
            elif etype == "step_finish":
                tk = part.get("tokens") or {}
                tokens_in += int(tk.get("input") or 0) + int((tk.get("cache") or {}).get("read") or 0)
                tokens_out += int(tk.get("output") or 0)
                cost += float(part.get("cost") or 0.0)
        return LLMResult(
            text="\n".join(text_parts).strip(),
            tokens_in=int(tokens_in),
            tokens_out=int(tokens_out),
            cost=float(cost),
            latency_s=latency,
            tool_calls=tool_calls,
            raw_events=events,
            model=self.model,
            agent=agent,
        )


class GeminiProvider:
    """Google Generative Language API backend (same model in every condition)."""

    def __init__(self, cfg: dict[str, Any] | None = None) -> None:
        self.cfg = cfg or load_config()
        from dotenv import load_dotenv

        load_dotenv()
        key = (os.getenv("GEMINI_API_KEY") or "").strip().strip('"').strip("'")
        if not key:
            raise RuntimeError("GEMINI_API_KEY not set")
        import google.generativeai as genai

        genai.configure(api_key=key)
        g = self.cfg["model"].get("gemini", {})
        name = g.get("name")
        if not name:
            name = self._resolve_model(genai, g.get("preference", []))
        self.model = name
        self.temperature = float(self.cfg["model"]["temperature"])
        self.top_p = float(self.cfg["model"]["top_p"])
        self.max_output_tokens = int(self.cfg["model"]["max_output_tokens"])
        self._genai = genai

    def _resolve_model(self, genai: Any, preference: list[str]) -> str:
        available = {m.name.split("/")[-1] for m in genai.list_models()}
        for cand in preference:
            if cand in available:
                return cand
        raise RuntimeError(f"none of the preferred Gemini models available: {preference}")

    def run(self, prompt: str, agent: str = "", use_mcp: bool = False) -> LLMResult:
        gen_cfg = self._genai.types.GenerationConfig(
            temperature=self.temperature,
            top_p=self.top_p,
            max_output_tokens=self.max_output_tokens,
        )
        model = self._genai.GenerativeModel(model_name=self.model)
        t0 = time.perf_counter()
        try:
            resp = model.generate_content(prompt, generation_config=gen_cfg)
        except Exception as exc:  # noqa: BLE001
            return LLMResult(error=f"{type(exc).__name__}: {str(exc)[:300]}", latency_s=time.perf_counter() - t0, model=self.model)
        latency = time.perf_counter() - t0
        usage = getattr(resp, "usage_metadata", None)
        tin = int(getattr(usage, "prompt_token_count", 0) or 0)
        tout = int(getattr(usage, "candidates_token_count", 0) or 0)
        return LLMResult(text=(getattr(resp, "text", "") or "").strip(), tokens_in=tin, tokens_out=tout, latency_s=latency, model=self.model)


def get_provider(cfg: dict[str, Any] | None = None):
    cfg = cfg or load_config()
    provider = cfg["model"]["provider"]
    if provider == "opencode":
        return OpencodeProvider(cfg)
    if provider == "gemini":
        return GeminiProvider(cfg)
    raise ValueError(f"unknown provider: {provider}")
