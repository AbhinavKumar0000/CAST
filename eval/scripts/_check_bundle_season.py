import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from eval.common import load_config
from eval.time_anchored import ToolRuntime

cfg = load_config()
ss = [json.loads(l) for l in Path("eval/data/llm_subset.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
s = ss[0]
rt = ToolRuntime(cfg)
b = rt._bundle(s)
print("bundle keys:", list(b.keys()))
print("season value:", json.dumps(b.get("season"), ensure_ascii=False))
print("season type:", type(b.get("season")))
# what season_tool returns to LLM
res = rt.season_tool(s, s["lat"], s["lon"])
print("season_tool result:", json.dumps(res, ensure_ascii=False)[:400])