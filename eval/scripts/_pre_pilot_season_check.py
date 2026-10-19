"""Pre-pilot offline check: 20 pilot scenarios' expected season (season_by_month) vs
time-anchored season_tool output and vs evidence bundle season. No API calls."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from eval.common import load_config
from eval.time_anchored import TimeAnchoredBuilder, ToolRuntime, season_for_date

cfg = load_config()
ss = [json.loads(l) for l in Path("eval/data/llm_subset.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
pilot = ss[:20]

rt = ToolRuntime(cfg)
print(f"expect: month, season_by_month, season_for_date(as_of), bundle season_tool")
mismatch = 0
for s in pilot:
    sid = s["scenario_id"]
    m, sf = season_for_date(s["as_of_date"])
    bundle = rt._bundle(s)
    from mcp_server.season_tool import MONTH_TO_SEASON  # noqa: E402
    bseason = bundle["season"]
    bs = bseason.get("current_season") if isinstance(bseason, dict) else bseason
    ok = (bs == s["season_by_month"]) and (sf == s["season_by_month"])
    if not ok:
        mismatch += 1
    print(f"{sid} month={int(s['as_of_date'][5:7])} strat={s['season_by_month']!r:8} "
          f"season_for_date={sf!r:8} bundle={bs!r:8} {'OK' if ok else 'MISMATCH'}")

print(f"\ntotal mismatch: {mismatch}/{len(pilot)}")
print("evidence bundle exists for first sid?:",
      Path("eval/runs/archive_v2/evidence", pilot[0]["scenario_id"] + ".json").exists())