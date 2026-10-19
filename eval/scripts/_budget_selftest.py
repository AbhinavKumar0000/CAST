"""Self-test for the UTC-day HTTP budget (PROTOCOL 8.12). No API calls."""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from eval.llm.budget import BudgetExceeded, DailyBudget, seed, utc_today

# 1) read the REAL counter read-only (never seed/overwrite the live file from a test)
real = DailyBudget(4000)
print("real counter status:", real.status())

# 2) behaviour test on a temp path
with tempfile.TemporaryDirectory() as d:
    p = Path(d) / "_b.json"
    seed("2026-10-13", 3372, path=p)   # seed demo on a temp file only
    print("seeded temp:", json.loads(p.read_text()))
    b = DailyBudget(3, p)
    print("fresh:", b.status())
    b.reserve()
    b.reserve(2)
    print("after 3 reserves:", b.status())
    try:
        b.reserve()
        print("ERROR: expected BudgetExceeded")
    except BudgetExceeded as e:
        print("hard-stop OK:", str(e)[:70], "...")

    # day rollover: stale date -> count resets to 0
    p.write_text(json.dumps({"date": "1999-01-01", "count": 999}))
    print("stale-date status:", b.status())

# 3) provider imports cleanly with the budget wired
import eval.llm.nvidia_provider as npv  # noqa: E402
print("provider import OK; DailyBudget referenced:", "DailyBudget" in dir(npv))
print("utc_today:", utc_today())
