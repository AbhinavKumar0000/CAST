"""Stage 1 (offline): tool-output equivalence between the in-process and MCP paths.

For 50 scenarios x 6 tools, dispatches the SAME call both ways --
``eval.time_anchored.ToolRuntime`` (in-process, what C2a/C2b used for B1) and
``eval.mcp_runtime.McpToolRuntime`` (real MCP client -> eval/mcp_eval/server.py) --
and compares the outputs exactly as the model would see them.

Checks per call:
  * model-visible payload == ``json.dumps(result, ensure_ascii=False)`` (what
    ``nvidia_provider`` puts in the ``role=tool`` message); MUST be identical.
  * ``output_hash`` payload == ``json.dumps(result, sort_keys=True, ensure_ascii=False)``
    (the logged hash); expected to differ only for ``climate_tool`` (int vs str keys
    in the monthly dicts after a JSON round-trip), which is cosmetic.

Writes eval/results/mcp_equivalence.json. No API calls.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

from eval.common import load_config  # noqa: E402
from eval.mcp_runtime import McpToolRuntime  # noqa: E402
from eval.time_anchored import ToolRuntime  # noqa: E402

RESULTS = REPO / "eval/results/mcp_equivalence.json"
N_SCENARIOS = 50
TOOLS = ["weather_tool", "climate_tool", "season_tool", "risk_tool",
         "get_soil_by_coordinates", "crop_score"]


def main() -> int:
    cfg = load_config()
    scenarios = [
        json.loads(line)
        for line in (REPO / "eval/data/llm_subset.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ][:N_SCENARIOS]

    report = {
        "scenarios": len(scenarios),
        "tools_per_scenario": len(TOOLS),
        "calls": 0,
        "model_visible_identical": 0,
        "output_hash_identical": 0,
        "model_visible_mismatches": [],
        "output_hash_mismatches_by_tool": {},
    }

    inproc = ToolRuntime(cfg)
    with McpToolRuntime(cfg) as mcp:
        for sc in scenarios:
            sid = sc["scenario_id"]
            args = {"latitude": sc["lat"], "longitude": sc["lon"]}
            for name in TOOLS:
                a = inproc.call(sc, name, args)
                b = mcp.call(sc, name, args)
                report["calls"] += 1

                if json.dumps(a, ensure_ascii=False) == json.dumps(b, ensure_ascii=False):
                    report["model_visible_identical"] += 1
                else:
                    report["model_visible_mismatches"].append({
                        "scenario_id": sid, "tool": name,
                        "inprocess": json.dumps(a, ensure_ascii=False)[:500],
                        "mcp": json.dumps(b, ensure_ascii=False)[:500],
                    })

                if json.dumps(a, sort_keys=True, ensure_ascii=False) == json.dumps(b, sort_keys=True, ensure_ascii=False):
                    report["output_hash_identical"] += 1
                else:
                    bt = report["output_hash_mismatches_by_tool"]
                    bt[name] = bt.get(name, 0) + 1

    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    n = report["calls"]
    print(f"calls                   : {n}")
    print(f"model-visible identical : {report['model_visible_identical']}/{n}")
    print(f"output_hash identical   : {report['output_hash_identical']}/{n}")
    if report["model_visible_mismatches"]:
        print(f"\nMODEL-VISIBLE MISMATCHES ({len(report['model_visible_mismatches'])}):")
        for mm in report["model_visible_mismatches"][:10]:
            print(f"  {mm['scenario_id']} {mm['tool']}")
    else:
        print("\nAll model-visible tool outputs byte-identical across transports.")
    if report["output_hash_mismatches_by_tool"]:
        print(f"output_hash (sort_keys) mismatches by tool: {report['output_hash_mismatches_by_tool']}")
    print(f"\nReport -> {RESULTS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
