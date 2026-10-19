"""Stage 1 (offline): diff the MCP server's tool declarations against the harness's.

Compares the descriptors served by eval/mcp_eval/server.py (``list_tools()``) with the
OpenAI-style function declarations the harness sends to the model
(``NvidiaProvider._build_tools``). Checks: tool names, descriptions, parameter names,
types, descriptions, required fields, and enums.

Writes eval/results/mcp_schema_diff.json and prints a human-readable report.
No API calls.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

from eval.common import load_config  # noqa: E402
from eval.llm.nvidia_provider import NvidiaProvider  # noqa: E402
from eval.mcp_runtime import McpToolRuntime  # noqa: E402

RESULTS = REPO / "eval/results/mcp_schema_diff.json"
_STRIP = {"title", "$schema", "default", "$defs", "additionalProperties"}


def normalize(schema: dict) -> dict:
    if not isinstance(schema, dict):
        return {}
    out = {}
    if "type" in schema:
        out["type"] = schema["type"]
    props = schema.get("properties")
    if isinstance(props, dict):
        out["properties"] = {
            k: {kk: vv for kk, vv in (v or {}).items() if kk not in _STRIP}
            for k, v in props.items()
        }
    if "required" in schema:
        out["required"] = sorted(schema["required"])
    if "enum" in schema:
        out["enum"] = schema["enum"]
    return out


def harness_decls(allowed):
    dummy = types.SimpleNamespace(allowed_tools=None)
    return {t["function"]["name"]: t["function"] for t in NvidiaProvider._build_tools(dummy, True, allowed)}


def main() -> int:
    cfg = load_config()
    with McpToolRuntime(cfg) as rt:
        mcp_tools = {t["name"]: t for t in rt.list_tools()}

    decls = harness_decls(sorted(mcp_tools.keys()))
    report = {"tools_mcp": sorted(mcp_tools), "tools_harness": sorted(decls), "differences": {}}

    for name in sorted(set(mcp_tools) | set(decls)):
        diffs = {}
        m = mcp_tools.get(name)
        h = decls.get(name)
        if m is None:
            diffs["missing_in_mcp"] = True
        if h is None:
            diffs["missing_in_harness"] = True
        if m and h:
            if m.get("description") != h.get("description"):
                diffs["description"] = {"mcp": m.get("description"), "harness": h.get("description")}
            ms = normalize(m.get("inputSchema") or {})
            hs = normalize(h.get("parameters") or {})
            if ms != hs:
                diffs["schema"] = {"mcp": ms, "harness": hs}
        if diffs:
            report["differences"][name] = diffs

    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("MCP tools     :", report["tools_mcp"])
    print("Harness tools :", report["tools_harness"])
    if not report["differences"]:
        print("\nNO DIFFERENCES: declarations are identical (names, descriptions, params).")
    else:
        print(f"\n{len(report['differences'])} tool(s) differ:")
        for name, d in report["differences"].items():
            print(f"\n  [{name}]")
            for key, val in d.items():
                print(f"    {key}: {json.dumps(val, ensure_ascii=False)[:600]}")
    print(f"\nReport -> {RESULTS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
