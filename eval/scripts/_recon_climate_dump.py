import json
import sys

sys.path.insert(0, ".")
from eval.common import load_config, read_jsonl, config_dirs
from eval.time_anchored import TimeAnchoredBuilder

cfg = load_config()
dirs = config_dirs(cfg)
rows = read_jsonl(dirs["llm_subset_path"])[:500]
b = TimeAnchoredBuilder(cfg)
sc = rows[0]
sid = sc["scenario_id"]
disk = json.load(open("eval/runs/archive_v2/evidence/" + sid + ".json", encoding="utf-8"))
fresh = b.build(sc)
print("=== DISK climate ===")
print(json.dumps(disk["climate"], indent=1)[:1500])
print("=== FRESH climate ===")
print(json.dumps(fresh["climate"], indent=1)[:1500])
