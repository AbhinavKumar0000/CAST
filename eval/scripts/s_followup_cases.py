"""EXPLORATORY S-series follow-up — PROTOCOL 8.34 item 6: WET case studies.

5 cases (facts only) where C3 or C2a kept a newly infeasible crop under the
WET1/WET2 shifts. Selection rule (stated, deterministic): mode = strict
(registered primary); candidates = (set in [WET1, WET2], cond in [C3, C2a],
usable top-5, crop in top5 ∩ D, |D| > 0); sorted (cond C3-first, set, sid,
model, crop); pick the first candidate per set within each condition using
DISTINCT scenario ids across picks (C2a: llama for WET1, nemotron for WET2
when available), then fill remaining slots in sorted order (3 C3 + 2 C2a).

Per case: crop, constraint crossed (newly active hazard + constraint-table
status), scorer score/rank and the component scores that keep it ranked.

Offline; NO model calls. Writes eval/results/s_followup_cases.json.
Run:  py -3 eval/scripts/s_followup_cases.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval/scripts"))

import score_s as S  # noqa: E402
from eval.s_series import base_set, oracle  # noqa: E402

OUT = ROOT / "eval/results"
CASE_SETS = ["WET1", "WET2"]
W = {"rainfall": 0.20, "temperature": 0.15, "soil": 0.20,
     "season": 0.30, "risk": 0.15}
HAZARDS = (("flood", oracle._FLOOD), ("drought", oracle._DROUGHT),
           ("heatwave", oracle._HEATWAVE))


def load_defs() -> dict:
    src = (ROOT / "eval/scripts/run_deterministic_v2.py").read_text(encoding="utf-8")
    cut = src.index("EVIDENCE_DIR = Path(")
    ns = {"__name__": "cases_defs", "__file__": "run_deterministic_v2.py"}
    exec(compile(src[:cut], "run_deterministic_v2.py:defs", "exec"), ns)
    return ns


def rank_with(ns: dict, evidence: dict, week: int, use_windows: bool) -> list[dict]:
    """Component-instrumented scorer; use_windows=False == registered pipeline."""
    season = evidence["season"].get("current_season", "Unknown")
    month = int(evidence["season"].get("current_month") or 1)
    soil = evidence["soil"].get("dominant_soil", "") if isinstance(evidence["soil"], dict) else ""
    rain = ns["_seasonal_rainfall_estimate"](evidence["climate"], season)
    temp = ns["_current_temperature"](evidence["weather"], evidence["climate"], month)
    out = []
    for row in ns["CROP_ROWS"]:
        rm = ns["_score_against_range"](rain, ns["_parse_numeric_range"](row.get("Rainfall", "")))
        tm = ns["_score_against_range"](temp, ns["_parse_numeric_range"](row.get("Tempreture", "")))
        sm = ns["_score_soil_type_match"](row.get("Soil Type", ""), soil)
        srow = row if use_windows else {
            "season_supported": row.get("season_supported", ""),
            "sowing_start_week": "", "sowing_end_week": "",
            "risk_sensitivity": row.get("risk_sensitivity") or "",
            "peak_water_week": row.get("peak_water_week", "")}
        sa, _plant = ns["_season_alignment_score"](srow, season, week)
        rrow = {"risk_sensitivity": row.get("risk_sensitivity") or "",
                "peak_water_week": row.get("peak_water_week", "")}
        rp = ns["_risk_penalty_score"](rrow, evidence["risk"], week)
        total = (W["rainfall"] * rm + W["temperature"] * tm + W["soil"] * sm
                 + W["season"] * sa + W["risk"] * rp)
        out.append({"crop": row.get("Crop", ""), "total_score": round(total, 3),
                    "scores": {"rainfall_match": rm, "temperature_match": tm,
                               "soil_type_match": sm, "season_alignment": sa,
                               "risk_penalty": rp},
                    "weighted": {"rainfall": round(W["rainfall"] * rm, 4),
                                 "temperature": round(W["temperature"] * tm, 4),
                                 "soil": round(W["soil"] * sm, 4),
                                 "season": round(W["season"] * sa, 4),
                                 "risk": round(W["risk"] * rp, 4)}})
    out.sort(key=lambda x: (-x["total_score"], x["crop"]))
    return out


def main() -> None:
    ns = load_defs()
    sids = base_set.select_base(40)
    meta = base_set.scenarios_by_id(sids)
    arch = {sid: S.load_archive(sid) for sid in sids}
    season0 = {sid: S.current_season(arch[sid], meta[sid]["as_of_date"]) for sid in sids}
    flags0 = {sid: oracle.flags_of(arch[sid]) for sid in sids}
    c3_re = json.loads((OUT / "s_c3_full_repo.json").read_text(encoding="utf-8"))

    base_recs = {m: S.enrich_baseline(m, sids) for m in S.MODELS}
    pert = {}
    for m in S.MODELS:
        for s in CASE_SETS:
            recs, _, _ = S.load_pert_records(s, m)
            pert[(m, s)] = recs

    cands = []
    for s in CASE_SETS:
        for sid in sids:
            b = S.read_bundle(s, sid)
            flags1 = oracle.flags_of(b)
            D = (oracle.feasible_set(season0[sid], flags0[sid], "strict")
                 - oracle.feasible_set(season0[sid], flags1, "strict"))
            if not D:
                continue
            # C3 candidate (model-independent)
            c3arm = (((c3_re.get("sets") or {}).get(s) or {}).get(sid) or {})
            t5_c3 = [str(x).strip() for x in (c3arm.get("top5") or [])]
            for crop in sorted(set(t5_c3) & D):
                cands.append({"cond": "C3", "set": s, "sid": sid,
                              "model": "model-independent", "crop": crop,
                              "mode": "strict"})
            # C2a candidates (model-specific)
            for model in S.MODELS:
                rec = pert[(model, s)].get(("C2a", sid))
                t5 = S.top5_of(rec)
                if not (S.usable(rec) and t5):
                    continue
                for crop in sorted(set(t5) & D):
                    cands.append({"cond": "C2a", "set": s, "sid": sid,
                                  "model": model, "crop": crop,
                                  "mode": "strict"})

    order_cond = {"C3": 0, "C2a": 1}
    cands.sort(key=lambda c: (order_cond[c["cond"]], c["set"], c["sid"],
                              c["model"], c["crop"]))
    # deterministic diversity: first (sorted) candidate per set within each
    # condition, then fill remaining slots in sorted order
    picked: list[dict] = []
    for cond, want in (("C3", 3), ("C2a", 2)):
        sel = []
        for i, st in enumerate(CASE_SETS):
            prefer = (["llama", "nemotron"] if i % 2 == 0
                      else ["nemotron", "llama"]) if cond == "C2a" else None
            pool = [c for c in cands
                    if c["cond"] == cond and c["set"] == st and c not in sel
                    and c["sid"] not in {x["sid"] for x in sel}]
            if prefer:
                for mdl in prefer:
                    hit = next((c for c in pool if c["model"] == mdl), None)
                    if hit is not None:
                        sel.append(hit)
                        break
            if pool and len(sel) <= i:
                sel.append(pool[0])
        for c in cands:
            if (c["cond"] == cond and c not in sel and len(sel) < want
                    and c["sid"] not in {x["sid"] for x in sel}):
                sel.append(c)
        picked.extend(sel[:want])

    cases = []
    for c in picked:
        s, sid, crop = c["set"], c["sid"], c["crop"]
        b = S.read_bundle(s, sid)
        flags1 = oracle.flags_of(b)
        D = (oracle.feasible_set(season0[sid], flags0[sid], "strict")
             - oracle.feasible_set(season0[sid], flags1, "strict"))
        crossed = []
        for name, table in HAZARDS:
            if flags0[sid].get(name):
                continue
            if flags1.get(name) and oracle._blocked(crop, table, "strict"):
                crossed.append({"hazard": name,
                                "flag_before": flags0[sid].get(name),
                                "flag_after": flags1.get(name),
                                "constraint_table_status": table.get(crop),
                                "mode": "strict"})
        week = (__import__("datetime").datetime.strptime(
            meta[sid]["as_of_date"], "%Y-%m-%d").date().isocalendar().week)

        if c["cond"] == "C3":
            ranked = rank_with(ns, b, week, use_windows=False)
            source = "registered pipeline (run_deterministic_v2::score_crops full_repo)"
        else:
            ranked = rank_with(ns, b, week, use_windows=True)
            source = "MCP crop_score tool (mcp_server/crop_score_tool.py)"
        entry = None
        for i, r in enumerate(ranked):
            if r["crop"] == crop:
                entry = {"rank_full": i + 1, **r}
                break
        if entry is None:
            print(f"  SKIP {s}/{sid}/{c['cond']}: {crop} not in scorer universe")
            continue
        # where the ADVICE ranked it (top-5 position)
        if c["cond"] == "C3":
            t5 = (((c3_re.get("sets") or {}).get(s) or {}).get(sid) or {}).get("top5", [])
        else:
            t5 = S.top5_of(pert[(c["model"], s)].get(("C2a", sid)))
        advice_pos = ([i + 1 for i, x in enumerate(t5) if str(x).strip() == crop]
                      or [None])[0]
        stored_cs = None
        stored_list = (b.get("crop_score") or {}).get("ranked_crops", [])
        for x in stored_list:
            if x["crop"] == crop:
                stored_cs = {"total_score": x["total_score"],
                             "scores": x["scores"],
                             "plantable_now": x["plantable_now"]}
        if c["cond"] == "C3":
            cross = None
        else:
            st_pairs = [(x["crop"], x["total_score"]) for x in stored_list]
            re_pairs = [(r["crop"], r["total_score"]) for r in ranked[:6]]
            cross = st_pairs == re_pairs
        stored_week = (b.get("crop_score") or {}).get("current_week")
        contrib = sorted(entry["weighted"].items(), key=lambda kv: -kv[1])
        cases.append({
            "set": s, "sid": sid, "season": season0[sid],
            "district": meta[sid]["district"], "condition": c["cond"],
            "model": c["model"], "mode": "strict",
            "crop_kept_in_top5": crop,
            "advice_top5_position": advice_pos,
            "D": sorted(D),
            "constraint_crossed": crossed,
            "scorer": {"instrument": source, "rank_full": entry["rank_full"],
                       "total_score": entry["total_score"],
                       "components": entry["scores"],
                       "weighted_contributions": dict(contrib),
                       "stored_bundle_crop_score_if_available": stored_cs,
                       "stored_tool_top6_matches_recompute": cross,
                       "stored_tool_current_week": stored_week,
                       "as_of_week": week},
            "facts_note": ("The scorer's formula contains no hard-constraint "
                           "table; hazard probability enters only via the risk "
                           "penalty component."),
        })

    payload = {"registered": "EXPLORATORY (PROTOCOL 8.34 item 6)",
               "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "selection_rule": (
                   "strict mode; sets WET1/WET2; conditions C3+C2a; usable top-5; "
                   "crop in top5 ∩ D; sorted (cond C3-first, set, sid, model, "
                   "crop); per condition the first candidate from each set with "
                   "distinct scenario ids (C2a: llama for WET1, nemotron for "
                   "WET2 when available), then fill in sorted order "
                   "(3 C3 + 2 C2a)"),
               "n_candidates": len(cands),
               "candidates_by_cond": {
                   "C3": sum(1 for x in cands if x["cond"] == "C3"),
                   "C2a": sum(1 for x in cands if x["cond"] == "C2a")},
               "n_cases": len(cases), "cases": cases}
    (OUT / "s_followup_cases.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"candidates: {payload['candidates_by_cond']} total={len(cands)}")
    for cs in cases:
        cr = cs["constraint_crossed"][0] if cs["constraint_crossed"] else None
        print(f"  {cs['condition']:4} {cs['set']:5} {cs['sid']} "
              f"({cs['model']}) kept {cs['crop_kept_in_top5']} in top5@"
              f"{cs['advice_top5_position']}: {cr['hazard'] if cr else 'NO-REASON'} "
              f"status={cr['constraint_table_status'] if cr else '-'}; "
              f"scorer rank {cs['scorer']['rank_full']} "
              f"score {cs['scorer']['total_score']}")
    print(f"wrote eval/results/s_followup_cases.json ({len(cases)} cases)")


if __name__ == "__main__":
    main()
