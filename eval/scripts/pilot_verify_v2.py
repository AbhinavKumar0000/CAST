"""Pilot v2 verification + report (2026-10-13, harness-fix ss8.10).

Checks abort rules (a)(b)(c)(e)(f) and reports per model/condition:
valid_json, truncated, forced_final (reason), unknown_tool_calls, max_rounds_reached,
finish reasons, HTTP requests per scenario, tools called, latency, tokens.
Filter: records tagged pilot_dev=true whose scenario_id is in pilot_v2_scenarios.json.
"""

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from eval.common import load_config
from eval.time_anchored import season_for_date

cfg = load_config()
ss = [json.loads(l) for l in Path("eval/data/llm_subset.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
by_id = {s["scenario_id"]: s for s in ss}
PILOT2 = set(json.loads(Path("eval/results/pilot_v2_scenarios.json").read_text(encoding="utf-8"))["pilot_v2"])
TOOL_SET = {"weather_tool", "climate_tool", "season_tool", "risk_tool", "get_soil_by_coordinates", "crop_score"}
LIVE = ("now", "datetime", "time", "clock", "http", "fetch", "web", "url", "news", "live")

RUNS = {
    "nemotron": "eval/runs/eval_nemotron-3-ultra_pilot_dev/results.json",
    "llama": "eval/runs/eval_llama-3.2-11b_pilot_dev/results.json",
}


def loaded(path):
    recs = json.loads(Path(path).read_text(encoding="utf-8"))
    return [r for r in recs if r.get("pilot_dev") and r["scenario_id"] in PILOT2]


def stats(recs, cond):
    rs = [r for r in recs if r["condition"] == cond]
    n = len(rs)
    if n == 0:
        return None
    errors = Counter(r.get("error") or "ok" for r in rs)
    parsed_ok = sum(1 for r in rs if (r.get("parsed") or {}).get("valid_json") is True)
    truncated = sum(1 for r in rs if r.get("truncated"))
    forced = [r for r in rs if r.get("forced_final")]
    unk = sum(r.get("unknown_tool_calls", 0) for r in rs)
    maxr = sum(1 for r in rs if r.get("error") == "max_rounds_reached")
    http = sum(len(r.get("tool_log") or []) + 1 for r in rs)
    lat = sorted(r.get("latency_s", 0) for r in rs)
    # per-scenario HTTP = tool calls + 1 final
    http_per = sorted(len(r.get("tool_log") or []) + 1 for r in rs)
    return {
        "n": n, "errors": dict(errors),
        "valid_json": parsed_ok, "valid_json_pct": round(parsed_ok / n * 100, 2),
        "truncated": truncated, "truncated_pct": round(truncated / n * 100, 2),
        "forced_final": len(forced), "forced_final_pct": round(len(forced) / n * 100, 2),
        "forced_reasons": Counter(r.get("forced_final_reason", "") for r in forced),
        "unknown_tool_calls": unk, "unknown_runs": sum(1 for r in rs if r.get("unknown_tool_calls", 0)),
        "max_rounds_reached": maxr,
        "finish": Counter(r.get("finish_reason") or "?" for r in rs),
        "http_total": http, "http_per_median": sorted(http_per)[n // 2], "http_per_mean": round(http / n, 2),
        "tools_mean": round(sum(len(r.get("tool_log") or []) for r in rs) / n, 2),
        "lat_mean_s": round(sum(r.get("latency_s", 0) for r in rs) / n, 1),
        "lat_median_s": round(lat[n // 2], 1),
        "tokens_in": sum(r.get("tokens_in", 0) for r in rs),
        "tokens_out": sum(r.get("tokens_out", 0) for r in rs),
    }


def tool_check(recs):
    bad_season, live, crop_in_c2b = [], [], []
    used = Counter()
    for r in recs:
        cond = r["condition"]
        for t in r.get("tool_log") or []:
            name = t["name"]
            used[name] += 1
            if name == "season_tool":
                s = by_id[r["scenario_id"]]
                _, sf = season_for_date(s["as_of_date"])
                if sf != s["season_by_month"] or t.get("unknown_tool"):
                    bad_season.append((r["scenario_id"], cond, sf, s["season_by_month"]))
            if any(z in name.lower() for z in LIVE):
                live.append((r["scenario_id"], cond, name))
            if cond == "C2b" and name == "crop_score":
                crop_in_c2b.append((r["scenario_id"],))
    return bad_season, live, crop_in_c2b, dict(used)


print("=" * 78)
print("PILOT v2 VERIFICATION 2026-10-13 (harness-fix ss8.10; 20 NEW scenarios)")
print("=" * 78)
reports = {}
for m, path in RUNS.items():
    recs = loaded(path)
    reports[m] = recs
    conds = {r["condition"] for r in recs}
    print(f"\n===== {m}  per-condition counts: {{c: sum(1 for r in recs if r['condition']==c) for c in sorted(conds)}}")
    for cond in sorted({r["condition"] for r in recs}):
        s = stats(recs, cond)
        if not s:
            continue
        print(f"  {cond}: n={s['n']} | valid_json={s['valid_json']}/{s['n']} ({s['valid_json_pct']}%) | "
              f"errors={s['errors']} | truncated={s['truncated']} ({s['truncated_pct']}%) | "
              f"forced_final={s['forced_final']} ({s['forced_final_pct']}%) reasons={dict(s['forced_reasons'])}")
        print(f"    unknown_tool_calls={s['unknown_tool_calls']} (runs={s['unknown_runs']}) | "
              f"max_rounds_reached={s['max_rounds_reached']} | finish={dict(s['finish'])}")
        print(f"    HTTP total={s['http_total']} per-scen mean={s['http_per_mean']} median={s['http_per_median']} | "
              f"tools mean={s['tools_mean']} | latency mean={s['lat_mean_s']}s med={s['lat_median_s']}s | "
              f"tok in={s['tokens_in']} out={s['tokens_out']}")

print("\n" + "=" * 78)
print("ABORT RULES")
print("=" * 78)

for m, recs in reports.items():
    bad_season, live, crop_c2b, used = tool_check(recs)
    print(f"\n-- {m}")
    print(f"  (a) season mismatches/unknown season calls: {len(bad_season)} {bad_season[:5]} -> {'PASS' if not bad_season else 'FAIL'}")
    print(f"  (b) live clock/network tool names: {len(live)} {live[:5]} -> {'PASS' if not live else 'FAIL'}")
    print(f"  (c) crop_score in C2b: {len(crop_c2b)} -> {'PASS' if not crop_c2b else 'FAIL'}")
    for cond in sorted({r["condition"] for r in recs}):
        s = stats(recs, cond)
        if s:
            print(f"  (e/429 n/a) {cond} errors: {s['errors']}")

# (e) 429 rate
for m, recs in reports.items():
    n429 = sum(1 for r in recs if "429" in str(r.get("error")))
    n = len(recs)
    print(f"  (e) 429 rate {m}: {n429}/{n} = {round(n429/n*100,2)}% -> {'PASS' if n429/n < 0.10 else 'FAIL'}")

# (f) Nemotron only: valid-JSON >=90% and forced_final <=10% in every tool condition
for cond in ["C1a", "C2a", "C2b"]:
    s = stats(reports["nemotron"], cond)
    if not s:
        continue
    okv = s["valid_json_pct"] >= 90.0
    okf = s["forced_final_pct"] <= 10.0
    print(f"  (f) nemotron {cond}: valid_json {s['valid_json_pct']}% the fine {('PASS' if okv else 'FAIL')} | "
          f"forced_final {s['forced_final_pct']}% (<=10) {'PASS' if okf else 'FAIL'}")

print("\nTool usage (all pilot_v2 records):")
for m, recs in reports.items():
    _, _, _, used = tool_check(recs)
    print(f"  {m}: {used}")