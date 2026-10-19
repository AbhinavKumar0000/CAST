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
dk = json.dumps(disk["climate"], sort_keys=True)
fk = json.dumps(fresh["climate"], sort_keys=True)
print("len disk", len(dk), "len fresh", len(fk))
print("equal:", dk == fk)
if dk != fk:
    for i, (a, c) in enumerate(zip(dk, fk)):
        if a != c:
            print("first char diff at", i)
            print("disk :", dk[max(0, i - 60):i + 60])
            print("fresh:", fk[max(0, i - 60):i + 60])
            break
print("disk key set:", sorted(disk["climate"].keys()))
print("fresh key set:", sorted(fresh["climate"].keys()))
