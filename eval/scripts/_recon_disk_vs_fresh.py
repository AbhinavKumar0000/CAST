import json
import os
import sys

sys.path.insert(0, ".")
from eval.common import load_config, read_jsonl, config_dirs
from eval.time_anchored import TimeAnchoredBuilder

cfg = load_config()
dirs = config_dirs(cfg)
rows = read_jsonl(dirs["llm_subset_path"])[:500]
b = TimeAnchoredBuilder(cfg)

miss = 0
for sc in rows:
    p = "eval/runs/archive_v2/evidence/" + sc["scenario_id"] + ".json"
    if not os.path.exists(p):
        miss += 1
print("subset scenarios missing on disk:", miss, "/500")

for sc in rows[:3]:
    disk = json.load(open("eval/runs/archive_v2/evidence/" + sc["scenario_id"] + ".json", encoding="utf-8"))
    fresh = b.build(sc)
    same = {k: (json.dumps(disk.get(k), sort_keys=True) == json.dumps(fresh.get(k), sort_keys=True))
            for k in ["weather", "climate", "season", "soil", "risk", "crop_score"]}
    print(sc["scenario_id"], "fields_equal=", same)
