import json
import sys

sys.path.insert(0, ".")
from eval.common import load_config, read_jsonl, config_dirs
from eval.time_anchored import TimeAnchoredBuilder, ToolRuntime

cfg = load_config()
dirs = config_dirs(cfg)
rows = read_jsonl(dirs["llm_subset_path"])[:500]
b = TimeAnchoredBuilder(cfg)
tr = ToolRuntime(cfg, builder=b)

TOOLS = ["weather_tool", "climate_tool", "season_tool", "risk_tool",
         "get_soil_by_coordinates", "crop_score"]
FIELD = {"weather_tool": "weather", "climate_tool": "climate", "season_tool": "season",
         "risk_tool": "risk", "get_soil_by_coordinates": "soil", "crop_score": "crop_score"}

for sc in rows[:3]:
    sid = sc["scenario_id"]
    disk = json.load(open("eval/runs/archive_v2/evidence/" + sid + ".json", encoding="utf-8"))
    lat, lon = float(sc["lat"]), float(sc["lon"])
    print("===", sid)
    for t in TOOLS:
        fresh = tr.call(sc, t, {"latitude": lat, "longitude": lon})
        d = disk[FIELD[t]]
        model_fresh = json.dumps(fresh, ensure_ascii=False)
        model_disk = json.dumps(d, ensure_ascii=False)
        canon_fresh = json.dumps(json.loads(model_fresh), sort_keys=True)
        canon_disk = json.dumps(json.loads(model_disk), sort_keys=True)
        rt_fresh = json.dumps(json.loads(json.dumps(fresh)), sort_keys=True)
        rt_disk = json.dumps(json.loads(json.dumps(d)), sort_keys=True)
        print(f"  {t:26s} model-visible-equal={model_fresh==model_disk}  "
              f"sortkeys-equal={canon_fresh==canon_disk}  roundtrip-sortkeys-equal={rt_fresh==rt_disk}")
