"""S-series: build perturbed evidence bundles (no LLM) + oracle diagnostics.

Runs the real tools under each perturbation and writes the bundle to
eval/runs/s_evidence/<set>/<sid>.json, then prints the oracle shift (base -> perturbed)
in STRICT and LENIENT modes so we can confirm each arm has signal before any model call.

    py -3 eval/scripts/build_s_evidence.py
    py -3 eval/scripts/build_s_evidence.py --sets W2 D1 WET1
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from eval.common import load_config, ensure_dirs, config_dirs  # noqa: E402
from eval.s_series.builder import PerturbedTimeAnchoredBuilder  # noqa: E402
from eval.s_series.perturbations import ALL_SETS  # noqa: E402
from eval.s_series import base_set, oracle  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sets", nargs="+", default=ALL_SETS)
    ap.add_argument("--n", type=int, default=40)
    args = ap.parse_args()

    cfg = load_config()
    ensure_dirs(cfg)
    dirs = config_dirs(cfg)
    out_root = dirs["runs_dir"] / "s_evidence"
    out_root.mkdir(parents=True, exist_ok=True)

    sids = base_set.select_base(args.n)
    scene = base_set.scenarios_by_id(sids)

    diag: dict[str, dict] = {}
    for set_name in args.sets:
        builder = PerturbedTimeAnchoredBuilder(cfg, set_name)
        set_dir = out_root / set_name
        set_dir.mkdir(parents=True, exist_ok=True)
        d = {"n": 0}
        for mode in ("strict", "lenient"):
            d[mode] = {"flag_changed": 0, "flood_gained": 0, "drought_gained": 0,
                       "heatwave_gained": 0, "newly_infeasible_total": 0,
                       "scenarios_with_signal": 0, "crops": []}
        for sid in sids:
            sc = scene[sid]
            season = sc["season_stratum"]
            bundle = builder.build(sc)
            set_dir.joinpath(f"{sid}.json").write_text(
                json.dumps(bundle, ensure_ascii=False), encoding="utf-8")
            f1 = oracle.flags_of(bundle)
            f0 = base_set.load_evidence_flags(sid)
            d["n"] += 1
            for mode in ("strict", "lenient"):
                m = d[mode]
                if f1 != f0:
                    m["flag_changed"] += 1
                for name in ("flood", "drought", "heatwave"):
                    if f1[name] and not f0[name]:
                        m[f"{name}_gained"] += 1
                newly = oracle.feasible_set(season, f0, mode) - oracle.feasible_set(season, f1, mode)
                m["newly_infeasible_total"] += len(newly)
                if newly:
                    m["scenarios_with_signal"] += 1
                    m["crops"] = sorted(set(m["crops"]) | newly)
        diag[set_name] = d

    print(f"\n=== oracle signal by set, n = {len(sids)} ===")
    print(f"{'set':6s} {'mode':7s} {'flagD':>6s} {'fl+':>4s} {'dr+':>4s} {'hw+':>5s} "
          f"{'|D|tot':>7s} {'sig':>4s}  crops")
    for set_name in args.sets:
        for mode in ("strict", "lenient"):
            m = diag[set_name][mode]
            print(f"{set_name:6s} {mode:7s} {m['flag_changed']:6d} {m['flood_gained']:4d} "
                  f"{m['drought_gained']:4d} {m['heatwave_gained']:5d} "
                  f"{m['newly_infeasible_total']:7d} {m['scenarios_with_signal']:4d} "
                  f"{','.join(m['crops']) if m['crops'] else '-'}")
    (dirs["results_dir"] / "s_oracle_signal.json").write_text(
        json.dumps(diag, indent=2), encoding="utf-8")
    print("\nwrote", dirs["results_dir"] / "s_oracle_signal.json")


if __name__ == "__main__":
    main()
