"""EXPLORATORY B6 root-cause: bundle crop_score vs registered det pipeline (40 base).

Three rankings per scenario:
  A = stored MCP crop_score (archive_v2/evidence bundle, frozen)
  B = registered det pipeline (run_deterministic_v2 score_crops, empty sowing windows)
  C = SAME det pipeline but passing real sowing windows into _season_alignment_score
Causal test: A != B and A == C  -> "season handling (windows dropped in registered pipeline)".
Also dumps side-by-side top-5s, scores and inputs for the 17 mismatched sids.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from eval.s_series.base_set import select_base  # noqa: E402

SRC = ROOT / "eval" / "scripts" / "run_deterministic_v2.py"
ARCH = ROOT / "eval" / "runs" / "archive_v2" / "evidence"
DET = ROOT / "eval" / "runs" / "archive_v2" / "deterministic"
OUT = ROOT / "eval" / "results" / "s_followup_b6.json"

src = SRC.read_text(encoding="utf-8")
cut = src.index("EVIDENCE_DIR = Path(")
ns = {"__name__": "b6_defs", "__file__": str(SRC)}
exec(compile(src[:cut], "run_deterministic_v2.py:defs", "exec"), ns)
score_crops = ns["score_crops"]
W = {"rainfall": 0.20, "temperature": 0.15, "soil": 0.20, "season": 0.30, "risk": 0.15}


def score_var(evidence, week, use_windows):
    """score_crops replica; use_windows=False reproduces registered pipeline exactly."""
    season = evidence["season"].get("current_season", "Unknown")
    month = int(evidence["season"].get("current_month") or 1)
    soil = evidence["soil"].get("dominant_soil", "") if isinstance(evidence["soil"], dict) else ""
    rain = ns["_seasonal_rainfall_estimate"](evidence["climate"], season)
    temp = ns["_current_temperature"](evidence["weather"], evidence["climate"], month)
    out = []
    for row in ns["CROP_ROWS"]:
        crop = row.get("Crop", "")
        rm = ns["_score_against_range"](rain, ns["_parse_numeric_range"](row.get("Rainfall", "")))
        tm = ns["_score_against_range"](temp, ns["_parse_numeric_range"](row.get("Tempreture", "")))
        sm = ns["_score_soil_type_match"](row.get("Soil Type", ""), soil)
        if use_windows:
            srow = row
        else:
            srow = {"season_supported": row.get("season_supported", ""),
                    "sowing_start_week": "", "sowing_end_week": "",
                    "risk_sensitivity": row.get("risk_sensitivity") or "",
                    "peak_water_week": row.get("peak_water_week", "")}
        sa, plant = ns["_season_alignment_score"](srow, season, week)
        rrow = {"risk_sensitivity": row.get("risk_sensitivity") or "",
                "peak_water_week": row.get("peak_water_week", "")}
        rp = ns["_risk_penalty_score"](rrow, evidence["risk"], week)
        tot = (W["rainfall"] * rm + W["temperature"] * tm + W["soil"] * sm
               + W["season"] * sa + W["risk"] * rp)
        out.append({"crop": crop, "total_score": round(tot, 3), "plantable_now": plant,
                    "scores": {"rainfall": rm, "temperature": tm, "soil": sm,
                               "season": sa, "risk": rp}})
    out.sort(key=lambda x: (-x["total_score"], x["crop"]))
    return out[:6]


sids = select_base(40)
per = []
gate_det = 0
for sid in sids:
    b = json.loads((ARCH / f"{sid}.json").read_text(encoding="utf-8"))
    cs = b["crop_score"]
    det = json.loads((DET / f"{sid}.json").read_text(encoding="utf-8"))["ablations"]["full_repo"]["top5"]
    week = datetime.strptime(b["as_of_date"], "%Y-%m-%d").date().isocalendar().week
    a_full = [{"crop": c["crop"], "total_score": c["total_score"], "scores": c["scores"]}
              for c in cs["ranked_crops"]]
    a_t5 = [c["crop"] for c in a_full[:5]]
    b_rank = score_crops(b, W, week)
    b_t5 = [c["crop"] for c in b_rank[:5]]
    gate_det += (b_t5 == det)
    c_full = score_var(b, week, use_windows=True)
    c_t5 = [c["crop"] for c in c_full[:5]]
    mis = a_t5 != b_t5
    if not mis:
        cause = "(match)" if c_t5 == b_t5 else "NEW-DIVERGENCE-WHEN-WINDOWS-PASSED"
    elif c_t5 == a_t5:
        cause = "season handling (sowing windows dropped in registered pipeline)"
    else:
        cause = "other (variant does not reproduce stored tool output)"
    per.append({"sid": sid, "as_of": b["as_of_date"], "week": week,
                "season": b["season"].get("current_season"), "district": b.get("district"),
                "mismatch": mis, "cause": cause,
                "tool_top5": a_t5, "det_top5": b_t5, "variant_top5": c_t5,
                "tool_ranked": a_full, "det_ranked": b_rank, "variant_ranked": c_full})

print("det instrumentation gate (== archive det):", gate_det, "/ 40")
n_mis = sum(1 for p in per if p["mismatch"])
print("mismatch A vs B:", n_mis)
from collections import Counter
print("causes (all 40):", dict(Counter(p["cause"] for p in per)))
print("variant==tool among mismatched:",
      sum(1 for p in per if p["mismatch"] and p["variant_top5"] == p["tool_top5"]), "/", n_mis)
print("variant==det among matched:",
      sum(1 for p in per if not p["mismatch"] and p["variant_top5"] == p["det_top5"]))

payload = {"registered": "EXPLORATORY (PROTOCOL 8.34 item 1)",
           "instruments": {
               "A": "bundle crop_score (mcp_server/crop_score_tool.py, frozen tool output stored at build)",
               "B": "registered det pipeline (run_deterministic_v2.py::score_crops full_repo)",
               "C": "B but passing real sowing windows to _season_alignment_score"},
           "gate_det_equals_archive": gate_det,
           "n_mismatch": n_mis,
           "causes": dict(Counter(p["cause"] for p in per)),
           "scenarios": per}
OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
print("wrote", OUT)

