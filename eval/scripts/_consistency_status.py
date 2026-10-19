import json
import sys

path = sys.argv[1]
try:
    recs = json.load(open(path, encoding="utf-8"))
except Exception:
    recs = []
fresh = sum(1 for r in recs if r.get("repeat", 0) > 0)
print(f"{len(recs)} {fresh}")
