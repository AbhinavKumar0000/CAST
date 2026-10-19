import json
import sys

sys.path.insert(0, ".")
from eval.common import load_config, read_jsonl, config_dirs
from eval.mcp_runtime import McpToolRuntime

cfg = load_config()
rows = read_jsonl(config_dirs(cfg)["llm_subset_path"])[:3]

with McpToolRuntime(cfg) as rt:
    tools = rt.list_tools()
    print("MCP tools:", [t["name"] for t in tools])
    sc = rows[0]
    for name in ["weather_tool", "climate_tool", "season_tool", "risk_tool",
                 "get_soil_by_coordinates", "crop_score"]:
        out = rt.call(sc, name, {"latitude": sc["lat"], "longitude": sc["lon"]})
        print(f"  {name}: keys={sorted(out.keys())[:6]} err={out.get('error')}")
    # missing coords guard
    print("  missing-coord guard:", rt.call(sc, "weather_tool", {}))
