"""Stage 1 (offline): the C2b allowed-tools gate over the MCP transport.

Verifies that the real gate (``NvidiaProvider._execute_tool``) behaves identically
when the tool runtime is a real ``McpToolRuntime``:
  * C2b declarations advertise exactly the five tools (no crop_score);
  * a C2b crop_score call is rejected as unknown BEFORE any runtime dispatch;
  * an allowed tool still reaches the MCP runtime and its output is byte-identical
    to the in-process runtime's;
  * a C2a crop_score call is served.

No API calls; the provider is built via ``__new__`` so only the gate attributes are set.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

from eval.common import load_config  # noqa: E402
from eval.llm.nvidia_provider import NvidiaProvider  # noqa: E402
from eval.mcp_runtime import McpToolRuntime  # noqa: E402
from eval.time_anchored import ToolRuntime  # noqa: E402

FIVE_TOOLS = ["weather_tool", "climate_tool", "season_tool", "risk_tool", "get_soil_by_coordinates"]
SIX_TOOLS = FIVE_TOOLS + ["crop_score"]


class SpyRuntime:
    """Wraps a runtime and records dispatched tool names."""

    def __init__(self, inner):
        self.inner = inner
        self.calls: list[str] = []

    def call(self, scenario, name, args):
        self.calls.append(name)
        return self.inner.call(scenario, name, args)


def decl_names(decls):
    return [t["function"]["name"] for t in decls]


def make_provider(allowed):
    prov = NvidiaProvider.__new__(NvidiaProvider)
    prov.allowed_tools = allowed
    return prov


def main() -> int:
    cfg = load_config()
    scenario = json.loads((REPO / "eval/data/llm_subset.jsonl").read_text(encoding="utf-8").splitlines()[0])
    args = {"latitude": scenario["lat"], "longitude": scenario["lon"]}
    failures: list[str] = []

    def check(cond, msg):
        print(("  PASS  " if cond else "  FAIL  ") + msg)
        if not cond:
            failures.append(msg)

    with McpToolRuntime(cfg) as mcp, ToolRuntime(cfg) as inproc:
        dummy = make_provider(None)

        print("Declarations:")
        check(set(decl_names(NvidiaProvider._build_tools(dummy, True, SIX_TOOLS))) == set(SIX_TOOLS),
              "C2a offers all six tools")
        check(set(decl_names(NvidiaProvider._build_tools(dummy, True, FIVE_TOOLS))) == set(FIVE_TOOLS),
              "C2b offers exactly five tools (no crop_score)")

        print("C2b gate (crop_score forbidden):")
        spy = SpyRuntime(mcp)
        c2b = make_provider(FIVE_TOOLS)
        prov = make_provider(None)
        prov.allowed_tools = FIVE_TOOLS
        prov.tool_runtime = spy
        out = prov._execute_tool("crop_score", args, scenario, allowed=FIVE_TOOLS)
        check(out.get("unknown") is True, "crop_score returns unknown=True under C2b")
        check("crop_score" not in spy.calls, "crop_score never reaches the MCP runtime under C2b")

        weather = prov._execute_tool("weather_tool", args, scenario, allowed=FIVE_TOOLS)
        check(spy.calls == ["weather_tool"], "allowed tool dispatches over MCP (not blocked)")
        inproc_weather = inproc.call(scenario, "weather_tool", args)
        check(json.dumps(weather, ensure_ascii=False) == json.dumps(inproc_weather, ensure_ascii=False),
              "weather_tool MCP output == in-process output")

        prov_c2a = make_provider(SIX_TOOLS)
        spy2 = SpyRuntime(mcp)
        prov_c2a.tool_runtime = spy2
        out_c2a = prov_c2a._execute_tool("crop_score", args, scenario, allowed=SIX_TOOLS)
        check(out_c2a.get("unknown") is not True, "C2a crop_score is served (not unknown)")
        check(spy2.calls == ["crop_score"], "C2a crop_score dispatches over MCP")

    print()
    if failures:
        print(f"{len(failures)} CHECK(S) FAILED")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
