"""Pilot report 2026-10-13. Reads the two pilot_dev runs (nemotron 20x C1a/C2a/C2b,
llama 20x C2a), checks the five pilot abort rules (a)-(e), and computes the reliability/
efficiency metrics. Offline only.

Abort rules (user, recorded PROTOCOL.md ss8.9):
(a) season tool output differs from scenario season_by_month in any logged call
(b) any live clock or network call detected (unexpected tool name / finish)
(c) C2b calls crop_score
(d) max_rounds_reached > 10% of C2 runs
(e) 429 rate > 10%
"""

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from eval.common import load_config
from eval.time_anchored import ToolRuntime, season_for_date

cfg = load_config()
ss = [json.loads(l) for l in Path("eval/data/llm_subset.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
by_id = {s["scenario_id"]: s for s in ss}
C2_CONDITIONS = ("C2a", "C2b")
TOOL_SET = {"weather_tool", "climate_tool", "season_tool", "risk_tool", "get_soil_by_coordinates", "crop_score"}
LIVE_SIGNAL = ("now", "datetime", "time", "clock", "http", "fetch", "web", "url", "news", "live")

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def season_ok(sc):
    """season tool output for scenario, recomputed deterministically (time-anchored)."""
    s = by_id[sc["scenario_id"]]
    m, sf = season_for_date(s["as_of_date"])
    b = s["season_by_month"]
    return (sf == b), (m, sf, b)

def analyze(records):
    out = defaultdict(dict)
    for cond in sorted({r["condition"] for r in records}):
        rs = [r for r in records if r["condition"] == cond]
        err = [r for r in rs if r.get("error")]
        n = len(rs)
        out[cond] = {
            "n": n,
            "ok": n - len(err),
            "err": len(err),
            "errors": Counter(r["error"] for r in err),
            "valid_json": sum(1 for r in rs if (r.get("parsed") or {}).get("valid_json") is True),
            "max_rounds": sum(1 for r in rs if r.get("error") == "max_rounds_reached"),
            "finish": Counter(r.get("finish_reason") for r in rs),
            "latency": {
                "mean_s": round(sum(r.get("latency_s", 0) for r in rs) / n, 1),
                "p50_s": round(sorted(r.get("latency_s", 0) for r in rs)[n // 2], 1),
                "max_s": round(max(r.get("latency_s", 0) for r in rs), 1),
            },
            "tokens_in": sum(r.get("tokens_in", 0) for r in rs),
            "tokens_out": sum(r.get("tokens_out", 0) for r in rs),
            "http": sum(1 for r in rs for _ in (r.get("tool_log") or [])) + n,
            "tool_calls_mean": round(sum(len(r.get("tool_log") or []) for r in rs) / n, 2),
        }
        # measured tool rounds incl. final: total HTTP = n last rounds + tool calls
        names = Counter()
        for r in rs:
            for t in r.get("tool_log") or []:
                names[t["name"]] += 1
        out[cond]["tool_names"] = dict(names)
        out[cond]["unexpected_tools"] = sorted(set(names) - TOOL_SET)
        out[cond]["live_tools"] = sorted({n for n in names if any(s in n.lower() for s in LIVE_SIGNAL)})
        c2b_crop = sum(1 for r in rs if cond == "C2b" and any(t["name"] == "crop_score" for t in (r.get("tool_log") or [])))
        out[cond]["crop_score_in_c2b"] = c2b_crop
    return out

def check_rules(reports):
    results = {}
    season_bad = []
    for model, recs in RAW.items():
        for r in recs:
            if r.get("condition") in C2_CONDITIONS:
                for t in r.get("tool_log") or []:
                    if t["name"] == "season_tool":
                        ok, _ = season_ok(r)
                        if not ok:
                            season_bad.append((model, r["scenario_id"], t["args"]))
    results["a_season_mismatch"] = season_bad

    live = {}
    hall = {}
    for model, recs in RAW.items():
        u, h = [], []
        for r in recs:
            for t in r.get("tool_log") or []:
                if t["name"] not in TOOL_SET:
                    if any(s in t["name"].lower() for s in LIVE_SIGNAL):
                        u.append((r["scenario_id"], r["condition"], t["name"]))
                    else:
                        h.append((r["scenario_id"], r["condition"], t["name"]))
        live[model] = u
        hall[model] = h
    results["b_live_clock_network"] = live
    results["hallucinated_tools_note"] = hall

    results["c_crop_in_c2b"] = {
        model: {cond: rep["crop_score_in_c2b"] for cond, rep in reports[model].items()}
        for model in reports
    }

    results["d_max_rounds_pct"] = {
        model: {
            cond: round(rep["max_rounds"] / rep["n"] * 100, 1)
            for cond, rep in reports[model].items() if cond in C2_CONDITIONS
        }
        for model in reports
    }

    rate429 = {}
    for model, recs in RAW.items():
        n = len(recs)
        c = sum(1 for r in recs if "429" in str(r.get("error")) or "rate" in str(r.get("error")).lower())
        rate429[model] = round(c / n * 100, 2)
    results["e_429_pct"] = rate429
    return results

RAW = {
    "nemotron": load("eval/runs/eval_nemotron-3-ultra_pilot_dev/results.json"),
    "llama": load("eval/runs/eval_llama-3.2-11b_pilot_dev/results.json"),
}
reports = {m: analyze(recs) for m, recs in RAW.items()}
res = check_rules(reports)

print("=" * 72)
print("PILOT VERIFICATION 2026-10-13  (records tagged pilot_dev=true)")
print("=" * 72)
for cond, rep in reports["nemotron"].items():
    print(f"\n-- Nemotron C1a/C2a/C2b  ({cond}): n={rep['n']} "
          f"ok={rep['ok']} err={rep['err']} valid_json={rep['valid_json']}/{rep['n']}")
    print(f"   finish={dict(rep['finish'])} errors={dict(rep['errors'])}")
    print(f"   latency mean={rep['latency']['mean_s']}s p50={rep['latency']['p50_s']}s max={rep['latency']['max_s']}s | "
          f"tokens in={rep['tokens_in']} out={rep['tokens_out']} | HTTP={rep['http']} | tool_calls={rep['tool_calls_mean']}")
    print(f"   tool calls={sum(rep['tool_names'].values())} names={rep['tool_names']}")
    print(f"   unexpected tools={rep['unexpected_tools']} fill_json={rep['finish']}")

for cond, rep in reports["llama"].items():
    print(f"\n-- Llama C2a: n={rep['n']} ok={rep['ok']} err={rep['err']} valid_json={rep['valid_json']}/{rep['n']}")
    print(f"   finish={dict(rep['finish'])} errors={dict(rep['errors'])}")
    print(f"   latency mean={rep['latency']['mean_s']}s p50={rep['latency']['p50_s']}s max={rep['latency']['max_s']}s | "
          f"tokens in={rep['tokens_in']} out={rep['tokens_out']} | HTTP={rep['http']} | tool_calls={rep['tool_calls_mean']}")
    print(f"   unexpected tools={rep['unexpected_tools']}")

print("\n" + "=" * 72)
print("ABORT RULES")
print("=" * 72)
for name, val in res.items():
    if name == "a_season_mismatch":
        print(f"(a) season mismatch: {val}  -> {'PASS' if not val else 'FAIL'}")
    elif name == "b_live_clock_network":
        bad = any(v for v in val.values())
        print(f"(b) live clock / network calls (tool names with now/time/http/fetch/url/...): {val} -> {'PASS' if not bad else 'FAIL'}")
        print(f"    [note] hallucinated non-live tool names: {res['hallucinated_tools_note']}")
    elif name == "c_crop_in_c2b":
        bad = any(v for m in val.values() for v in m.values())
        print(f"(c) crop_score in C2b: {val} -> {'PASS' if not bad else 'FAIL'}")
    elif name == "hallucinated_tools_note":
        pass
    elif name == "d_max_rounds_pct":
        bad = {m: {c: p for c, p in v.items() if p > 10} for m, v in val.items()}
        bad = {m: v for m, v in bad.items() if v}
        print(f"(d) max_rounds_reached % of C2: {val} -> {'PASS' if not bad else 'FAIL: ' + str(bad)}")
    elif name == "e_429_pct":
        bad = {m: v for m, v in val.items() if v > 10}
        print(f"(e) 429 rate: {val} -> {'PASS' if not bad else 'FAIL'}")

print("\nDetailed max_rounds_reached runs (llama C2a):")
for r in RAW["llama"]:
    if r.get("error") == "max_rounds_reached":
        print("  ", r["scenario_id"], r["condition"], "tools=", len(r.get("tool_log") or []),
              "finish=", r.get("finish_reason"))