"""SQLite response cache + checkpointing for LLM calls (STEP 5)."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from eval.common import config_dirs, load_config

SCHEMA = """
CREATE TABLE IF NOT EXISTS llm_cache (
    key TEXT PRIMARY KEY,
    model TEXT,
    condition TEXT,
    scenario_id TEXT,
    repeat INTEGER,
    prompt_sha TEXT,
    use_mcp INTEGER,
    agent TEXT,
    text TEXT,
    tokens_in INTEGER,
    tokens_out INTEGER,
    cost REAL,
    latency_s REAL,
    tool_calls INTEGER,
    error TEXT,
    created_utc TEXT
);
"""


def cache_key(model: str, condition: str, prompt: str, scenario_id: str, repeat: int, agent: str) -> str:
    payload = "\u241f".join([model, condition, prompt, scenario_id, str(repeat), agent])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class LLMCache:
    def __init__(self, cfg: dict[str, Any] | None = None, path: Path | None = None) -> None:
        self.cfg = cfg or load_config()
        self.path = path or (Path(config_dirs(self.cfg)["cache_dir"]) / "llm_cache.sqlite")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.execute(SCHEMA)
        self.conn.commit()

    def get(self, key: str) -> dict[str, Any] | None:
        cur = self.conn.execute("SELECT * FROM llm_cache WHERE key = ? AND error IS NULL", (key,))
        row = cur.fetchone()
        if row is None:
            return None
        cols = [c[0] for c in cur.description]
        rec = dict(zip(cols, row))
        rec["raw_events"] = []
        return rec

    def put(self, key: str, rec: dict[str, Any]) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO llm_cache
            (key, model, condition, scenario_id, repeat, prompt_sha, use_mcp, agent,
             text, tokens_in, tokens_out, cost, latency_s, tool_calls, error, created_utc)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                key,
                rec.get("model"),
                rec.get("condition"),
                rec.get("scenario_id"),
                rec.get("repeat"),
                rec.get("prompt_sha"),
                int(bool(rec.get("use_mcp"))),
                rec.get("agent"),
                rec.get("text"),
                int(rec.get("tokens_in") or 0),
                int(rec.get("tokens_out") or 0),
                float(rec.get("cost") or 0.0),
                float(rec.get("latency_s") or 0.0),
                int(rec.get("tool_calls") or 0),
                rec.get("error"),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self.conn.commit()

    def count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM llm_cache WHERE error IS NULL").fetchone()[0])

    def distinct_calls(self) -> int:
        return self.count()

    def close(self) -> None:
        self.conn.close()


def result_to_record(result: Any, condition: str, scenario_id: str, repeat: int, prompt_sha: str, use_mcp: bool, agent: str) -> dict[str, Any]:
    return {
        "model": result.model,
        "condition": condition,
        "scenario_id": scenario_id,
        "repeat": repeat,
        "prompt_sha": prompt_sha,
        "use_mcp": use_mcp,
        "agent": agent,
        "text": result.text,
        "tokens_in": result.tokens_in,
        "tokens_out": result.tokens_out,
        "cost": result.cost,
        "latency_s": result.latency_s,
        "tool_calls": result.tool_calls,
        "error": result.error,
    }
