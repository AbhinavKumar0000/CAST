"""EXPLORATORY S-series follow-up analyses — PROTOCOL 8.34 items 2, 3, 5.

Offline; NO model calls; reads only frozen inputs and registered outputs.
Registered outputs (s_scores.json, S_REPORT.md) are NOT modified.

Item 2 — Exposure-conditioned retention (EXPLORATORY metric):
    exposure E = |B ∩ D| where B = the condition's baseline top-5, D = F0 \\ F1;
    retention = |B ∩ D ∩ T| / E, T = shifted top-5, mean over EXPOSED cells,
    district-clustered bootstrap (score_s.cluster_stats, SEED 42, N_RES 10000).
    pp: exposed cells with usable baseline and usable shifted response.
    ITT: exposed cells with usable baseline; unusable shifted response -> worst
    case = 1.0 (all exposed crops retained). Unusable baseline -> exposure
    unknown -> excluded. C0/C0b are excluded from the shifted comparison
    (reused by design, 8.33.4); their baseline exposure is reported for context.

Item 3 — Delta-violation: Violation@5(shift, F1) - Violation@5(baseline, F1),
    pooled WITH_pilot, pp + ITT, strict + lenient, over signal cells (|D|>0)
    and over all cells. ITT: any unknown violation component set to its worst
    (1.0). C0/C0b delta = 0 by construction (reused response), noted not tested.

Item 5 — Power: MDD for the Stale contrasts from the observed conditional
    contrast CIs (s_scores_conditional.json): SE = (hi - lo) / (2 * 1.959964);
    MDD_80 = (z_{1-a/2} + z_0.80) * SE at a = 0.05 and a = 0.0125 (worst Holm
    rank over 4 contrasts).

Gates: cell reconstruction must match s_scores_cells.csv exactly; n_D must
match for every (set, sid, mode).

Writes eval/results/s_followup.json.
Run:  py -3 eval/scripts/s_followup.py
"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import NormalDist

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval/scripts"))

import score_s as S  # noqa: E402  (module-level code is constants + functions only)
from eval.s_series import base_set, oracle  # noqa: E402

OUT = ROOT / "eval/results"
RETENTION_CONDS = ["C1a", "C2a", "C2b", "C3"]
EXPOSURE_ONLY_CONDS = ["C0", "C0b"]


def main() -> None:
    # ---- frozen state (mirrors score_s.main sections 1, 4, 5, 10) ------------
    sids = base_set.select_base(40)
    meta = base_set.scenarios_by_id(sids)
    pilot_all = set(json.loads(
        (OUT / "pilot_scenario_sets.json").read_text(encoding="utf-8"))["pilot_union"])
    sets = S.run_sets()

    base_recs = {m: S.enrich_baseline(m, sids) for m in S.MODELS}
    c3_base = {sid: base_set.load_c3(sid) for sid in sids}
    c3_re = json.loads((OUT / "s_c3_full_repo.json").read_text(encoding="utf-8"))

    pert = {}
    for m in S.MODELS:
        for s in sets:
            recs, _, _ = S.load_pert_records(s, m)
            pert[(m, s)] = recs

    arch = {sid: S.load_archive(sid) for sid in sids}
    season0 = {sid: S.current_season(arch[sid], meta[sid]["as_of_date"]) for sid in sids}
    bundles = {}
    for s in sets:
        for sid in sids:
            b = S.read_bundle(s, sid)
            if b is not None:
                bundles[(s, sid)] = b
    flags0 = {sid: oracle.flags_of(arch[sid]) for sid in sids}
    flags1 = {(s, sid): oracle.flags_of(bundles[(s, sid)])
              for (s, sid) in bundles}
    F: dict[tuple[str, str, str], tuple] = {}
    for (s, sid) in bundles:
        for mode in S.MODES:
            F[(s, sid, mode)] = (
                oracle.feasible_set(season0[sid], flags0[sid], mode),
                oracle.feasible_set(season0[sid], flags1[(s, sid)], mode))
    n_D = {(s, sid, mode): len(F[(s, sid, mode)][0] - F[(s, sid, mode)][1])
           for (s, sid) in bundles for mode in S.MODES}

    # ---- rebuild cells exactly as score_s section 10 -------------------------
    cells: dict[tuple, dict] = {}
    for m in S.MODELS:
        for s in sets:
            recs = pert[(m, s)]
            for cond in S.CONDS:
                for sid in sids:
                    reused = cond in ("C0", "C0b")
                    if reused:
                        rec = base_recs[m].get((cond, sid))
                        top5 = S.top5_of(rec)
                        us = S.usable(rec)
                        t_base = list(top5)
                        us_shift = us
                        base_us = us
                    elif cond == "C3":
                        c3arm = (((c3_re.get("sets") or {}).get(s) or {})
                                 .get(sid) or {})
                        top5 = [str(x).strip() for x in (c3arm.get("top5") or [])]
                        us = bool(top5) and not c3arm.get("error")
                        t_base = list(c3_base[sid])
                        us_shift = us and bool(t_base)
                        base_us = bool(t_base)
                    else:
                        rec = recs.get((cond, sid))
                        top5 = S.top5_of(rec)
                        us = S.usable(rec)
                        b_rec = base_recs[m].get((cond, sid))
                        t_base = S.top5_of(b_rec)
                        us_shift = us and S.usable(b_rec)
                        base_us = S.usable(b_rec)
                    for mode in S.MODES:
                        F0, F1 = F[(s, sid, mode)]
                        d = n_D[(s, sid, mode)]
                        vals = {k: S.metric_value(k, top5, t_base, F0, F1)
                                for k in S.METRICS}
                        cells[(m, s, sid, cond, mode)] = {
                            "model": m, "set": s, "sid": sid, "cond": cond,
                            "mode": mode, "district": meta[sid]["district"],
                            "pilot": sid in pilot_all, "reused": reused,
                            "usable": us, "usable_shift": us_shift,
                            "base_usable": base_us, "n_D": d,
                            "top5_base": t_base, "top5": top5,
                            "F0": F0, "F1": F1, **vals}

    # ---- gate: reconstruction == registered cells CSV ------------------------
    csv_idx = {}
    with (OUT / "s_scores_cells.csv").open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            csv_idx[(r["model"], r["set"], r["sid"], r["condition"], r["mode"])] = r
    mism = []
    for k, c in cells.items():
        r = csv_idx.get(k)
        if r is None:
            mism.append((k, "missing_in_csv"))
            continue
        if (r["top5_base"].split("|") if r["top5_base"] else []) != c["top5_base"]:
            mism.append((k, "top5_base"))
        if (r["top5"].split("|") if r["top5"] else []) != c["top5"]:
            mism.append((k, "top5"))
        if (r["usable"] == "1") != c["usable"] or \
           (r["usable_shift"] == "1") != c["usable_shift"]:
            mism.append((k, "usability"))
        if int(r["n_D"]) != c["n_D"]:
            mism.append((k, "n_D"))
        for mk in ("stale", "violation", "shift", "drop"):
            # registered CSV stores 6-decimal strings
            if abs(float(r[mk]) - c[mk]) > 1e-6:
                mism.append((k, mk))
    gate_ok = not mism and len(csv_idx) == len(cells)
    print(f"[{'PASS' if gate_ok else 'FAIL'}] cell reconstruction matches "
          f"s_scores_cells.csv ({len(cells)} cells, {len(mism)} mismatches)")
    if not gate_ok:
        print("first mismatches:", mism[:10])
        raise SystemExit(1)

    # ---- item 2: exposure + retention ----------------------------------------
    exposure: dict[str, dict] = {}
    retention: dict[str, dict] = {}
    for model in S.MODELS:
        for cond in S.CONDS:
            for mode in S.MODES:
                ind_d: dict[str, list[float]] = defaultdict(list)
                e_d: dict[str, list[float]] = defaultdict(list)
                n_base_us = n_exp = 0
                e_sum = 0.0
                by_pp: dict[str, list[float]] = defaultdict(list)
                by_itt: dict[str, list[float]] = defaultdict(list)
                n_exp_pp = 0
                for s in sets:
                    for sid in sids:
                        c = cells[(model, s, sid, cond, mode)]
                        if not c["base_usable"]:
                            continue  # exposure unknown
                        n_base_us += 1
                        B, T, D = c["top5_base"], c["top5"], c["F0"] - c["F1"]
                        E = set(B) & D
                        ind_d[c["district"]].append(1.0 if E else 0.0)
                        if not E:
                            continue
                        n_exp += 1
                        e_sum += len(E)
                        if cond in EXPOSURE_ONLY_CONDS:
                            continue  # reused by design: no shifted retention
                        ret = len(E & set(T)) / len(E)
                        if c["usable"]:
                            by_pp[c["district"]].append(ret)
                        n_exp_pp += 1
                        # ITT: unusable shifted response -> worst = all retained
                        by_itt[c["district"]].append(ret if c["usable"] else 1.0)
                ek = f"exposure|{model}|{cond}|{mode}"
                st = S.cluster_stats(ind_d)
                exposure[ek] = {
                    "n_base_usable": n_base_us, "n_exposed": n_exp,
                    "share_exposed": st, "mean_E_exposed":
                        (e_sum / n_exp) if n_exp else None}
                if cond in RETENTION_CONDS:
                    retention[f"retention|{model}|{cond}|{mode}|pp"] = {
                        "n_exposed_eligible": n_exp,
                        **S.cluster_stats(by_pp)}
                    retention[f"retention|{model}|{cond}|{mode}|itt"] = {
                        "n_exposed_eligible": n_exp,
                        **S.cluster_stats(by_itt)}

    # ---- item 3: delta-violation --------------------------------------------
    delta: dict[str, dict] = {}
    for model in S.MODELS:
        for cond in RETENTION_CONDS:
            for mode in S.MODES:
                for scope in ("signal", "all"):
                    for an in ("pp", "itt"):
                        by_d: dict[str, list[float]] = defaultdict(list)
                        n = 0
                        for s in sets:
                            for sid in sids:
                                c = cells[(model, s, sid, cond, mode)]
                                if scope == "signal" and c["n_D"] == 0:
                                    continue
                                if an == "pp":
                                    if not (c["usable"] and c["base_usable"]):
                                        continue
                                    v_shift = c["violation"]
                                    v_base = S.violation_at5(c["top5_base"], c["F1"])
                                else:
                                    # unknown component -> worst (violation = 1.0)
                                    v_shift = c["violation"] if c["usable"] else 1.0
                                    if c["base_usable"]:
                                        v_base = S.violation_at5(c["top5_base"],
                                                                 c["F1"])
                                    else:
                                        v_base = 1.0
                                by_d[c["district"]].append(v_shift - v_base)
                                n += 1
                        delta[f"deltaviolation|{model}|{cond}|{mode}|{scope}|{an}"] \
                            = {"n": n, **S.cluster_stats(by_d)}

    # ---- item 5: power / MDD --------------------------------------------------
    cond_json = json.loads((OUT / "s_scores_conditional.json").read_text(
        encoding="utf-8"))
    ndist = NormalDist()
    z80 = ndist.inv_cdf(0.80)
    z_a05 = ndist.inv_cdf(1 - 0.05 / 2)
    z_holm = ndist.inv_cdf(1 - 0.0125 / 2)   # worst rank: 0.05 / 4
    power: dict[str, dict] = {}
    for model in S.MODELS:
        for mode in S.MODES:
            for an in ("pp", "itt"):
                for pair in ("C2a-C0b", "C2b-C0b", "C2a-C1a", "C3-C2b"):
                    k = (f"{model}|WITH_pilot|{an}|__pooled__|{mode}|"
                         f"stale|{pair}")
                    st = cond_json["contrasts"][k]
                    se = (st["hi"] - st["lo"]) / (2 * 1.959963985)
                    power[f"mdd|{model}|{mode}|{an}|{pair}"] = {
                        "observed_d": st["mean"],
                        "se_from_ci": se,
                        "holm_p": st.get("holm"),
                        "n": st["n"],
                        "mdd80_alpha05": (z_a05 + z80) * se,
                        "mdd80_alpha0125_worst_holm": (z_holm + z80) * se,
                        "abs_d_over_mdd80_alpha05": (
                            abs(st["mean"]) / ((z_a05 + z80) * se)
                            if se > 0 else None),
                    }

    # signal-cell counts (57 strict / 104 lenient) for the record
    sig = {mode: sum(1 for s in sets for sid in sids
                     if n_D[(s, sid, mode)] > 0) for mode in S.MODES}

    out = {
        "meta": {
            "registered": "EXPLORATORY (PROTOCOL 8.34, registered "
                          "2026-10-19 02:44:25 UTC)",
            "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "items": {"2": "exposure-conditioned retention",
                      "3": "delta-violation", "5": "power/MDD"},
            "retention_conditions": RETENTION_CONDS,
            "exposure_only_conditions": EXPOSURE_ONLY_CONDS,
            "signal_cells": sig,
            "gates": {"cell_reconstruction_matches_registered_csv": gate_ok},
            "worst_case_conventions": {
                "retention_itt": "unusable shifted response -> 1.0 (all exposed "
                                 "crops retained)",
                "deltaviolation_itt": "unknown violation component -> 1.0",
            },
        },
        "exposure": exposure,
        "retention": retention,
        "delta_violation": delta,
        "power": power,
    }
    (OUT / "s_followup.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")

    # ---- print ----------------------------------------------------------------
    print(f"signal cells: {sig}")
    print("\nEXPOSURE (baseline, WITH_pilot pooled; share [95% CI], n_exp/n_base):")
    for model in S.MODELS:
        for cond in S.CONDS:
            mode = "strict"
            e = exposure[f"exposure|{model}|{cond}|{mode}"]
            st = e["share_exposed"]
            print(f"  {model:9} {cond:4} share={st['mean']:.3f} "
                  f"[{st['lo']:.3f},{st['hi']:.3f}] "
                  f"n_exp={e['n_exposed']:4} n_base={e['n_base_usable']:4}")
    print("\nRETENTION (strict, pooled WITH_pilot; mean [95% CI], n):")
    for model in S.MODELS:
        for cond in RETENTION_CONDS:
            for an in ("pp", "itt"):
                v = retention[f"retention|{model}|{cond}|strict|{an}"]
                print(f"  {model:9} {cond:4} {an:3} {v['mean']:.3f} "
                      f"[{v['lo']:.3f},{v['hi']:.3f}] n={v['n']:4} "
                      f"(exposed={v['n_exposed_eligible']})")
    print("\nDELTA-VIOLATION (strict, pooled WITH_pilot; mean [95% CI], n):")
    for model in S.MODELS:
        for cond in RETENTION_CONDS:
            line = []
            for scope in ("signal", "all"):
                v = delta[f"deltaviolation|{model}|{cond}|strict|{scope}|pp"]
                line.append(f"{scope}={v['mean']:+.3f}[{v['lo']:+.3f},"
                            f"{v['hi']:+.3f}](n={v['n']})")
            print(f"  {model:9} {cond:4} " + " ".join(line))
    print("\nPOWER (strict pp; MDD_80 at alpha=.05 | observed d):")
    for model in S.MODELS:
        for pair in ("C2a-C0b", "C2b-C0b", "C2a-C1a", "C3-C2b"):
            p = power[f"mdd|{model}|strict|pp|{pair}"]
            print(f"  {model:9} {pair:9} MDD={p['mdd80_alpha05']:.3f} "
                  f"d={p['observed_d']:+.3f} "
                  f"(|d|/MDD={p['abs_d_over_mdd80_alpha05']:.2f})")
    print("\nwrote eval/results/s_followup.json")


if __name__ == "__main__":
    main()
