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
dc = disk["climate"]["daily"]
fc = fresh["climate"]["daily"]
print("sid", sid, "as_of", sc["as_of_date"])
print("disk keys", sorted(disk["climate"].keys()), "fresh keys", sorted(fresh["climate"].keys()))
print("disk n_days", len(dc["time"]), "fresh n_days", len(fc["time"]))
print("disk first/last", dc["time"][0], dc["time"][-1])
print("fresh first/last", fc["time"][0], fc["time"][-1])
# summary fields
for k in disk["climate"].keys():
    if k != "daily":
        print("disk", k, "=", str(disk["climate"][k])[:200])
        print("fresh", k, "=", str(fresh["climate"][k])[:200])
# compare overlapping
dt = dc["time"]; ft = fc["time"]
print("times equal:", dt == ft)
# find where differ
for i, (a, bb) in enumerate(zip(dt, ft)):
    if a != bb:
        print("first time diff at", i, a, bb)
        break
