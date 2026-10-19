"""Real MCP-client tool runtime for the C2a/C2b harness (Phase 8 transport option).

Drop-in replacement for :class:`eval.time_anchored.ToolRuntime` that reaches the tools
over the Model Context Protocol instead of calling them in-process. It opens one
persistent ``ClientSession`` (official ``mcp`` SDK) against the eval MCP replay server
(``eval/mcp_eval/server.py``) over streamable-http and dispatches each tool call with
``session.call_tool``.

Why this is faithful (Phase 8, transport-equivalence work)
  * The replay server serves the **same frozen, time-anchored evidence bundles** that
    ``eval.time_anchored.TimeAnchoredBuilder`` produces (they are written to
    ``eval/runs/archive_v2/evidence`` by ``eval/scripts/build_evidence_v2.py`` using that
    builder). The server only reads pre-computed JSON -- it never runs the live tools and
    therefore never reaches ``datetime.now()`` or live Open-Meteo.
  * The server is keyed by the ``(latitude, longitude)`` carried by the tool call. The
    harness is scenario-scoped and authoritative (the in-process runtime ignores the
    model's echoed coordinates and uses the scenario's), so this runtime forwards the
    scenario's canonical coordinates. The only change relative to in-process invocation
    is the transport (JSON-RPC over HTTP vs. an in-process function call).
  * The per-tool output is byte-identical to the in-process runtime (verified by
    ``eval/scripts/test_mcp_equivalence.py``), so a model running over MCP sees exactly
    the evidence a model running in-process sees.

``call(scenario, name, args)`` mirrors ``ToolRuntime.call`` exactly, including the
missing-coordinate guard. The C2b allowed-tools gate lives in ``NvidiaProvider`` *before*
the runtime dispatch, so it is transport-independent by construction.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from eval.anyio_compat import install as _install_anyio_compat

# mcp 1.22's client/server subscribe to anyio's generic memory-stream factory,
# which the installed anyio (3.7.1) does not support. See eval/anyio_compat.py.
_install_anyio_compat()

REPO = Path(__file__).resolve().parent.parent

DEFAULT_HOST = os.getenv("MCP_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.getenv("MCP_PORT", "8011"))
DEFAULT_EVIDENCE_DIR = "eval/runs/archive_v2/evidence"
DEFAULT_LOG = "eval/runs/logs/mcp_eval_server.log"


def _tcp_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


class McpToolRuntime:
    """Tool dispatcher backed by a live MCP client session."""

    def __init__(
        self,
        cfg: dict[str, Any] | None = None,
        url: str | None = None,
        autostart: bool = True,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        evidence_dir: str = DEFAULT_EVIDENCE_DIR,
        index_path: str | None = None,
        start_timeout: float = 90.0,
        call_timeout: float = 120.0,
        log_path: str = DEFAULT_LOG,
    ) -> None:
        self.url = url or os.getenv("MCP_EVAL_URL") or f"http://{host}:{port}/mcp"
        parsed = urlparse(self.url)
        self._host = parsed.hostname or host
        self._port = parsed.port or port

        self._proc: subprocess.Popen | None = None
        self._owns_server = False
        self._session: Any = None
        self._tools: list[dict[str, Any]] = []
        self._call_lock = threading.Lock()
        self.call_timeout = call_timeout

        self._connected = threading.Event()
        self._stop_event: asyncio.Event | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._error: str | None = None

        ev = Path(evidence_dir)
        idx = Path(index_path) if index_path else ev / "index.json"
        self._evidence_dir = ev
        self._index_path = idx

        if autostart and not _tcp_open(self._host, self._port):
            self._start_server(host, port, ev, idx, Path(log_path))

        self._thread = threading.Thread(target=self._thread_main, name="mcp-runtime", daemon=True)
        self._thread.start()
        if not self._connected.wait(start_timeout):
            detail = self._error or "timeout waiting for session initialization"
            self.close()
            raise RuntimeError(f"McpToolRuntime failed to connect to {self.url}: {detail}")
        if self._error is not None:
            self.close()
            raise RuntimeError(f"McpToolRuntime connection error: {self._error}")

    # -- server lifecycle ----------------------------------------------------
    def _start_server(self, host: str, port: int, evidence_dir: Path, index_path: Path, log: Path) -> None:
        log.parent.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env["EVAL_EVIDENCE_DIR"] = str(evidence_dir)
        env["EVAL_INDEX"] = str(index_path)
        env["MCP_HOST"] = host
        env["MCP_PORT"] = str(port)
        self._log_handle = log.open("w", encoding="utf-8")
        self._proc = subprocess.Popen(
            [sys.executable, "-u", "-m", "eval.mcp_eval.server"],
            cwd=str(REPO),
            env=env,
            stdout=self._log_handle,
            stderr=subprocess.STDOUT,
        )
        self._owns_server = True
        deadline = time.monotonic() + 60.0
        while time.monotonic() < deadline:
            if _tcp_open(host, port):
                return
            if self._proc.poll() is not None:
                raise RuntimeError(
                    f"MCP replay server exited early (code {self._proc.returncode}); see {log}"
                )
            time.sleep(0.2)
        raise RuntimeError(f"MCP replay server did not open {host}:{port} within 60s; see {log}")

    # -- background event loop ----------------------------------------------
    def _thread_main(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._run())
        except Exception as exc:  # pragma: no cover - surfaced via _error/_connected
            self._error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
            self._connected.set()
        finally:
            self._loop.close()

    async def _run(self) -> None:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        self._stop_event = asyncio.Event()
        async with streamablehttp_client(self.url) as (read, write, _get_sid):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                self._tools = [t.model_dump() for t in listed.tools]
                self._session = session
                self._connected.set()
                await self._stop_event.wait()

    # -- tool dispatch -------------------------------------------------------
    def call(self, scenario: dict[str, Any], name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Dispatch a tool name over MCP. Mirrors ``ToolRuntime.call`` semantics."""
        lat = args.get("latitude")
        lon = args.get("longitude")
        if lat is None or lon is None:
            return {"error": f"{name} requires latitude and longitude.", "tool": name}

        plat = float(scenario["lat"])
        plon = float(scenario["lon"])
        if self._session is None or self._loop is None:
            return {"error": f"MCP session unavailable for '{name}'.", "tool": name, "unknown": True}

        with self._call_lock:
            fut = asyncio.run_coroutine_threadsafe(
                self._session.call_tool(name, {"latitude": plat, "longitude": plon}),
                self._loop,
            )
            try:
                result = fut.result(timeout=self.call_timeout)
            except Exception as exc:
                return {"error": f"MCP call_tool failed for '{name}': {exc}", "tool": name}
        return self._unwrap(result, name)

    @staticmethod
    def _unwrap(result: Any, name: str) -> dict[str, Any]:
        structured = getattr(result, "structuredContent", None)
        if isinstance(structured, dict):
            if set(structured.keys()) == {"result"} and isinstance(structured["result"], dict):
                return structured["result"]
            return structured
        if getattr(result, "isError", False):
            text = ""
            for block in getattr(result, "content", []) or []:
                text = getattr(block, "text", "") or text
            return {"error": text or f"tool '{name}' returned an MCP error", "tool": name}
        for block in getattr(result, "content", []) or []:
            text = getattr(block, "text", None)
            if text:
                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError:
                    pass
                return {"result": text, "tool": name}
        return {"error": "Empty MCP result", "tool": name}

    def list_tools(self) -> list[dict[str, Any]]:
        """Raw tool descriptors from the server (``name``/``description``/``inputSchema``)."""
        return self._tools

    # -- teardown ------------------------------------------------------------
    def close(self) -> None:
        if self._loop is not None and self._stop_event is not None:
            try:
                self._loop.call_soon_threadsafe(self._stop_event.set)
            except RuntimeError:
                pass
        if getattr(self, "_thread", None) is not None:
            self._thread.join(timeout=10)
        if self._owns_server and self._proc is not None and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        if getattr(self, "_log_handle", None) is not None:
            self._log_handle.close()

    def __enter__(self) -> "McpToolRuntime":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()
