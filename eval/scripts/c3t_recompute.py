"""C3t recompute (PROTOCOL 8.35): corrected deterministic instrument, all cells.

INSTRUMENT CORRECTION, NOT TUNING. Offline; NO model calls; no frozen file changed.

C3  (registered) = run_deterministic_v2.py::score_crops full_repo — drops real
                   sowing windows before _season_alignment_score (B6, lines 201-203).
C3t (corrected)  = identical pipeline/weights/weights/time anchor/crop list, the ONLY
                   difference being the real sowing_start_week/sowing_end_week are
                   passed into _season_alignment_score (variant C of S_FOLLOWUP S1).

Gates (this script):
  g_det_v1  score_var(use_windows=False, db_v1 rows) == archive_v2/deterministic
            ablations.full_repo.top5 on 10,000/10,000 (else ABORT).
  g_det_v2  score_var(use_windows=False, db_v2 rows) == db_v2/deterministic
            ablations.full_repo.top5 on 10,000/10,000 (else ABORT).
  g_tool    C3t (db_v1 rows) top-5 == stored bundle crop_score top-5, census
            over all 10,000 archive bundles (reported; no abort).
  g_s_base  C3t over the 40 base-archive bundles == C3t over the 40 N0 bundles
            (identity, expected 40/40).

Outputs (new files only):
  eval/results/c3t_archive.json      {sid: top5} C3/C3t x db_v1/db_v2 + gates
  eval/results/c3t_s_full_repo.json  C3t top-5 for every (arm, scenario) S bundle
                                     (same shape as s_c3_full_repo.json)
Run:  py -3 eval/scripts/c3t_recompute.py
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.s_series.base_set import select_base  # noqa: E402
from eval.s_series.perturbations import PERTURBATIONS  # noqa: E402

SRC = ROOT / "eval" / "scripts" / "run_deterministic_v2.py"
ARCH = ROOT / "eval" / "runs" / "archive_v2" / "evidence"
DET_V1 = ROOT / "eval" / "runs" / "archive_v2" / "deterministic"
DET_V2 = ROOT / "eval" / "runs" / "db_v2" / "deterministic"
S_EVID = ROOT / "eval" / "runs" / "s_evidence"
CROP_LOG_V1 = ROOT / "crop_log.csv"
CROP_LOG_V2 = ROOT / "crop_log_v2.csv"
OUT_ARCH = ROOT / "eval" / "results" / "c3t_archive.json"
OUT_S = ROOT / "eval" / "results" / "c3t_s_full_repo.json"

W = {"rainfall": 0.20, "temperature": 0.15, "soil": 0.20,
     "season": 0.30, "risk": 0.15}


def load_defs() -> dict:
    """Exec only the definitions prefix of run_deterministic_v2.py (frozen, read-only)."""
    src = SRC.read_text(encoding="utf-8")
    cut = src.index("EVIDENCE_DIR = Path(")
    ns: dict = {"__name__": "c3t_defs", "__file__": str(SRC)}
    exec(compile(src[:cut], "run_deterministic_v2.py:defs", "exec"), ns)
    for req in ("score_crops", "_season_alignment_score"):
        if req not in ns:
            raise RuntimeError(f"definition {req!r} not found in prefix")
    return ns


def load_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def make_score(ns: dict, rows: list[dict], use_windows: bool):
    """score_crops replica; use_windows=False reproduces the registered pipeline."""

    def score_var(evidence: dict, week: int) -> list[dict]:
        season = evidence["season"].get("current_season", "Unknown")
        month = int(evidence["season"].get("current_month") or 1)
        soil = (evidence["soil"].get("dominant_soil", "")
                if isinstance(evidence["soil"], dict) else "")
        rain = ns["_seasonal_rainfall_estimate"](evidence["climate"], season)
        temp = ns["_current_temperature"](evidence["weather"],
                                          evidence["climate"], month)
        out = []
        for row in rows:
            rm = ns["_score_against_range"](
                rain, ns["_parse_numeric_range"](row.get("Rainfall", "")))
            tm = ns["_score_against_range"](
                temp, ns["_parse_numeric_range"](row.get("Tempreture", "")))
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
            tot = (W["rainfall"] * rm + W["temperature"] * tm
                   + W["soil"] * sm + W["season"] * sa + W["risk"] * rp)
            out.append({"crop": row.get("Crop", ""),
                        "total_score": round(tot, 3), "plantable_now": plant,
                        "scores": {"rainfall": rm, "temperature": tm,
                                   "soil": sm, "season": sa, "risk": rp}})
        out.sort(key=lambda x: (-x["total_score"], x["crop"]))
        return out[:6]

    return score_var


def week_of(bundle: dict) -> int:
    return datetime.strptime(bundle["as_of_date"], "%Y-%m-%d").date().isocalendar().week


def main() -> None:
    ns = load_defs()
    rows_v1 = load_rows(CROP_LOG_V1)
    rows_v2 = load_rows(CROP_LOG_V2)
    det_v1 = make_score(ns, rows_v1, use_windows=False)
    det_v2 = make_score(ns, rows_v2, use_windows=False)
    c3t_v1 = make_score(ns, rows_v1, use_windows=True)
    c3t_v2 = make_score(ns, rows_v2, use_windows=True)

    scen = ROOT / "eval" / "data" / "scenarios.jsonl"
    sids_all = sorted(json.loads(line)["id"]
                      for line in scen.read_text(encoding="utf-8").splitlines()
                      if line.strip())
    missing_det = [s for s in sids_all
                   if not (DET_V1 / f"{s}.json").exists()
                   or not (DET_V2 / f"{s}.json").exists()
                   or not (ARCH / f"{s}.json").exists()]
    if missing_det:
        raise SystemExit(f"ABORT: {len(missing_det)} scenarios missing "
                         f"archive/det records, e.g. {missing_det[:3]}")
    print(f"scenarios: {len(sids_all)} (evidence dir also holds non-bundle "
          f"index/summary JSONs, skipped)")

    arch_db_v1: dict[str, list[str]] = {}
    arch_db_v2: dict[str, list[str]] = {}
    c3t_db_v1: dict[str, list[str]] = {}
    c3t_db_v2: dict[str, list[str]] = {}
    gates = {"g_det_v1": 0, "g_det_v2": 0, "g_tool": 0, "n": 0,
             "g_det_v1_bad": [], "g_det_v2_bad": [], "tool_mismatch_sids": []}
    base40 = set(select_base(40))
    g_tool_base40 = {"match": 0, "n": 0}

    for sid in sids_all:
        ev = json.loads((ARCH / f"{sid}.json").read_text(encoding="utf-8"))
        week = week_of(ev)
        det1 = json.loads((DET_V1 / f"{sid}.json").read_text(encoding="utf-8"))
        det2 = json.loads((DET_V2 / f"{sid}.json").read_text(encoding="utf-8"))
        old1 = det1["ablations"]["full_repo"]["top5"]
        old2 = det2["ablations"]["full_repo"]["top5"]
        nd1 = [c["crop"] for c in det_v1(ev, week)]
        nd2 = [c["crop"] for c in det_v2(ev, week)]
        if nd1 != old1:
            gates["g_det_v1_bad"].append(sid)
        if nd2 != old2:
            gates["g_det_v2_bad"].append(sid)
        t1 = [c["crop"] for c in c3t_v1(ev, week)]
        t2 = [c["crop"] for c in c3t_v2(ev, week)]
        stored = [c["crop"] for c in
                  ((ev.get("crop_score") or {}).get("ranked_crops") or [])[:5]]
        if t1 == stored:
            gates["g_tool"] += 1
        else:
            gates["tool_mismatch_sids"].append(sid)
        if sid in base40:
            g_tool_base40["n"] += 1
            g_tool_base40["match"] += int(t1 == stored)
        arch_db_v1[sid] = old1
        arch_db_v2[sid] = old2
        c3t_db_v1[sid] = t1
        c3t_db_v2[sid] = t2
        gates["n"] += 1
        if gates["n"] % 2000 == 0:
            print(f"  {gates['n']}/{len(sids_all)} ...", flush=True)

    gates["g_det_v1"] = gates["n"] - len(gates["g_det_v1_bad"])
    gates["g_det_v2"] = gates["n"] - len(gates["g_det_v2_bad"])
    print(f"g_det_v1 (C3 replica == archive det, db_v1): "
          f"{gates['g_det_v1']}/{gates['n']}")
    print(f"g_det_v2 (C3 replica == db_v2 det, db_v2):   "
          f"{gates['g_det_v2']}/{gates['n']}")
    print(f"g_tool   (C3t == stored bundle crop_score):  "
          f"{gates['g_tool']}/{gates['n']}  "
          f"(base40: {g_tool_base40['match']}/{g_tool_base40['n']})")
    if gates["g_det_v1"] != gates["n"] or gates["g_det_v2"] != gates["n"]:
        raise SystemExit("ABORT: instrument replica failed vs frozen det records")

    # ---- S-series arm bundles (db_v1 rows; C3t instrument) -------------------
    sets = [s for s in PERTURBATIONS] + ["N0"]
    out_sets: dict[str, dict] = {}
    s_missing: list[str] = []
    s_errors: list[str] = []
    n0_identity = {"match": 0, "n": 0}
    for s in sets:
        out_sets[s] = {}
        for sid in select_base(40):
            fp = S_EVID / s / f"{sid}.json"
            if not fp.exists():
                s_missing.append(f"{s}/{sid}")
                continue
            b = json.loads(fp.read_text(encoding="utf-8"))
            week = week_of(b)
            try:
                ranked = c3t_v1(b, week)
                out_sets[s][sid] = {
                    "top5": [c["crop"] for c in ranked[:5]],
                    "top6": [c["crop"] for c in ranked],
                    "scores": {c["crop"]: c["total_score"] for c in ranked},
                    "week": week,
                }
            except Exception as exc:  # noqa: BLE001
                s_errors.append(f"{s}/{sid}: {exc}")
                out_sets[s][sid] = {"error": str(exc), "top5": []}

    # g_s_base: N0 bundles == archive base bundles under C3t (identity control)
    for sid in select_base(40):
        ev = json.loads((ARCH / f"{sid}.json").read_text(encoding="utf-8"))
        base_t5 = [c["crop"] for c in c3t_v1(ev, week_of(ev))]
        n0_t5 = ((out_sets.get("N0") or {}).get(sid) or {}).get("top5") or []
        n0_identity["n"] += 1
        n0_identity["match"] += int(base_t5 == n0_t5)
    print(f"g_s_base (C3t N0 == C3t archive base):        "
          f"{n0_identity['match']}/{n0_identity['n']}")

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload = {
        "registered": "PROTOCOL 8.35 (instrument correction, not tuning), "
                      "2026-10-19 22:56:19 UTC",
        "generated": now,
        "instruments": {
            "C3": "run_deterministic_v2.py::score_crops full_repo "
                  "(empty sowing windows; registered, unchanged)",
            "C3t": "identical pipeline passing real sowing_start_week/"
                   "sowing_end_week into _season_alignment_score",
            "db_v2 variants": "same two instruments with crop_log_v2 rows",
        },
        "weights": W,
        "gates": {
            "g_det_v1_replica_equals_archive_det": f"{gates['g_det_v1']}/{gates['n']}",
            "g_det_v2_replica_equals_db_v2_det": f"{gates['g_det_v2']}/{gates['n']}",
            "g_tool_c3t_equals_stored_bundle_crop_score":
                f"{gates['g_tool']}/{gates['n']}",
            "g_tool_base40": f"{g_tool_base40['match']}/{g_tool_base40['n']}",
            "g_s_base_c3t_n0_equals_c3t_archive_base":
                f"{n0_identity['match']}/{n0_identity['n']}",
            "tool_mismatch_share": round(
                1 - gates["g_tool"] / max(1, gates["n"]), 6),
            "tool_mismatch_sids_first20": gates["tool_mismatch_sids"][:20],
        },
        "n_scenarios": gates["n"],
        "top5": {"C3_db_v1": arch_db_v1, "C3_db_v2": arch_db_v2,
                 "C3t_db_v1": c3t_db_v1, "C3t_db_v2": c3t_db_v2},
    }
    OUT_ARCH.write_text(json.dumps(payload), encoding="utf-8")
    print(f"wrote {OUT_ARCH}")

    s_payload = {
        "generated": now,
        "registered": "PROTOCOL 8.35 (instrument correction, not tuning)",
        "pipeline": "run_deterministic_v2.py definitions + real sowing windows "
                    "(C3t), full_repo weights, db_v1 crop rows",
        "n_sets": len(sets), "n_sids": 40,
        "n0_identity_vs_archive_base": n0_identity,
        "missing": s_missing, "errors": s_errors,
        "sets": out_sets,
    }
    OUT_S.write_text(json.dumps(s_payload, indent=2, ensure_ascii=False),
                     encoding="utf-8")
    n_cells = sum(len(v) for v in out_sets.values())
    print(f"recomputed S-arm cells: {n_cells} "
          f"(missing={len(s_missing)} errors={len(s_errors)})")
    print(f"wrote {OUT_S}")


if __name__ == "__main__":
    main()
