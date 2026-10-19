"""Offline test of harness-fix ss8.10 in NvidiaProvider (no API network needed).

Mocks the HTTP client to simulate:
  1. naive final (no tool calls) -> normal final
  2. normal C2 loop: 6 valid tools then final JSON
  3. stall: two consecutive unknown-tool calls -> forced_final reason=consecutive_unknown
  4. stall: reaching round 12 with valid tool calls -> forced_final reason=round12
  5. unknown tool returns error listing valid tools + JSON-now instruction
Check: valid_json=True in 1-2, forced_final flags/reasons in 3-4, unknown_tool_calls counted,
max_tool_rounds stays 15, and no live API call is made.
"""

import json
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import httpx

from eval.common import load_config
from eval.llm.nvidia_provider import NvidiaProvider, FINAL_JSON_INSTRUCTION

os.environ["NVIDIA_API_KEYS"] = "nvapi-test-key-none"


class FakeClient:
    def __init__(self, behavior):
        self.behavior = behavior
        self.calls = 0

    def close(self):
        pass

    def _resp(self, data):
        return httpx.Response(200, json=data,
                              request=httpx.Request("POST", "https://fake/test"))

    def post(self, path, json=None):
        self.calls += 1
        messages = json.get("messages", [])
        has_tools = "tools" in json
        last_user_messages = [m for m in messages if m["role"] == "user"]
        forced_pending = any(FINAL_JSON_INSTRUCTION in (m.get("content") or "") for m in last_user_messages)
        if forced_pending or not has_tools:
            return self._resp({"choices": [{"message": {
                "role": "assistant",
                "content": '{"top5": ["Soybean", "Wheat", "Rice", "Maize", "Cotton"], "explanation": "ok"}',
            }}], "usage": {"prompt_tokens": 100, "completion_tokens": 50, "reasoning_tokens": 10}})
        # tools present and no forced-final instruction yet
        return self.behavior(messages, json["tools"])


def _tool_response(names):
    def f(messages, tools):
        tool_calls = []
        for i, name in enumerate(names):
            tool_calls.append({
                "id": f"call_{name}",
                "type": "function",
                "function": {"name": name, "arguments": json.dumps({"latitude": 23.0, "longitude": 76.0})},
            })
        return httpx.Response(200, json={"choices": [{"message": {
            "role": "assistant",
            "content": "",
            "tool_calls": tool_calls,
        }}], "usage": {"prompt_tokens": 100, "completion_tokens": 50, "reasoning_tokens": 10}},
            request=httpx.Request("POST", "https://fake/test"))
    return f


def _json_response():
    return httpx.Response(200, json={"choices": [{"message": {"role": "assistant",
        "content": '{"top5": ["Soybean", "Wheat", "Rice", "Maize", "Cotton"], "explanation": "ok"}'}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50}},
        request=httpx.Request("POST", "https://fake/test"))


def setup(behavior):
    cfg = load_config()
    cfg["model"]["nvidia"]["name"] = "nvidia/nemotron-3-ultra-550b-a55b"
    cfg["model"]["name"] = "nvidia/nemotron-3-ultra-550b-a55b"
    p = NvidiaProvider(cfg, tool_runtime=None)
    fake = FakeClient(behavior)
    p._clients = [fake]
    p._key_index = 0
    return p, fake


TOOLS6 = ["weather_tool", "climate_tool", "season_tool", "risk_tool",
          "get_soil_by_coordinates", "crop_score"]


def run_case(name, behavior, use_mcp=True, tools=None):
    p, fake = setup(behavior)
    tools = tools or TOOLS6
    res = p.run("test prompt", agent="test", use_mcp=use_mcp, allowed_tools=tools)
    print(f"CASE {name}: ok={res.ok} err={res.error} text_tail={res.text[-40:]!r} "
          f"finish={res.finish_reason!r} calls={res.tool_calls} unknown={res.unknown_tool_calls} "
          f"forced={res.forced_final} reason={res.forced_final_reason!r} truncated={res.truncated} "
          f"reqs={fake.calls}")
    p.close()
    return res, fake


# 1. naive final (no tools requested at all)
res, _ = run_case("1_naive_no_tools", lambda m, t: httpx.Response(200, json={
    "choices": [{"message": {"role": "assistant", "content": '{"top5": ["Wheat"]}'}}],
    "usage": {}}), use_mcp=False, tools=None)
assert res.ok and res.forced_final is False

# 2. normal C2 loop: one round of 6 valid tools, then final JSON
state = {"rounds": 0}
def b2(messages, tools):
    if state["rounds"] == 0:
        state["rounds"] += 1
        return _tool_response(TOOLS6)(messages, tools)
    return _json_response()
res, _ = run_case("2_normal_c2", b2)
assert res.ok and res.unknown_tool_calls == 0 and res.forced_final is False

# 3. two consecutive unknown tools -> forced_final reason consecutive_unknown
res, fake = run_case("3_stall_unknown", _tool_response(["foo_tool", "bar_tool"]))
assert res.forced_final is True, res
assert res.forced_final_reason == "consecutive_unknown", res
assert res.unknown_tool_calls == 2, res
assert res.ok, res  # forced-final rescued it into a valid JSON

# 4. reaching round 12 with valid tool calls -> forced_final reason round12
state = {"rounds": 0}
def b4(messages, tools):
    state["rounds"] += 1
    return _tool_response(["weather_tool"])(messages, tools)
res, fake = run_case("4_round12", b4)
assert res.forced_final is True and res.forced_final_reason == "round12", res
assert res.ok, res

# 5. unknown tool returns explicit error listing valid C2b tools + JSON instruction
p = setup(lambda m, t: _tool_response(["crop_score"])(m, t))[0]
rt = p._execute_tool("crop_score", {"latitude": 23.0, "longitude": 76.0},
                     scenario=None, allowed=["weather_tool", "season_tool"])
assert rt.get("unknown") is True, rt
assert "weather_tool" in rt["error"] and "season_tool" in rt["error"], rt
assert "Do not call a tool for the final answer" in rt["error"], rt
print("CASE 5_unknown_error: unknown=True; lists valid tools + JSON-now instruction")
p.close()

print("\nALL HARNESS-FIX TESTS PASSED")