"""Quantify the normalize_crop fix (buggy vs fixed) on existing outputs."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
import sys
sys.path.insert(0, str(ROOT))

from eval.llm.prompts import ALIASES, CANONICAL_CROPS, normalize_crop
from eval.metrics import accuracy_at_k, jaccard_similarity, season_validity_rate

RUNS = {
    "nemotron": ROOT / "eval/runs/full_nemotron-3-ultra_20261011_082444/results.json",
    "llama": ROOT / "eval/runs/eval_llama-3.2-11b/results.json",
    "glm": ROOT / "eval/runs/eval_glm-5.3/results.json",
}
CONDS = ["C0", "C0b", "C1", "C2"]
DET = ROOT / "eval/runs/archive_v2/deterministic"  # frozen v2 grid (was: adhoc/evidence)


def old_normalize(name):
    if not name:
        return None
    key = re.sub(r"[^a-z0-9 ]", " ", name.strip().lower())
    key = re.sub(r"\s+", " ", key).strip()
    if key in ALIASES:
        return ALIASES[key]
    if key in {c.lower(): c for c in CANONICAL_CROPS}:
        return {c.lower(): c for c in CANONICAL_CROPS}[key]
    return None


def canon(raws, fn):
    out = []
    for raw in raws:
        c = fn(raw)
        if c is not None:
            out.append(c)
    return out


_cache = {}


def grid(sid):
    if sid not in _cache:
        _cache[sid] = json.load(open(DET / f"{sid}.json"))
    return _cache[sid]


def main():
    rows = []
    print(f"{'model':<9}{'cond':<5}{'n':>5}{'len_b':>7}{'len_a':>7}{'OOR%_b':>8}{'OOR%_a':>8}"
          f"{'acc_b':>8}{'acc_a':>8}{'jac_b':>8}{'jac_a':>8}{'sv_b':>8}{'sv_a':>8}")
    for m, p in RUNS.items():
        recs = json.load(open(p))
        for cond in CONDS:
            lens_b, lens_a, oorb, oora, accb, acca, jacb, jaca, svb, sva = [], [], 0, 0, [], [], [], [], [], []
            nslots_b = nslots_a = 0
            for r in recs:
                if r.get("condition") != cond or r.get("error"):
                    continue
                pa = r.get("parsed") or {}
                if not pa.get("valid_json") or not pa.get("top5_raw"):
                    continue
                sid = r["scenario_id"]
                b = grid(sid)
                c3 = (b.get("ablations", {}).get("full_repo") or {}).get("top5") or []
                season = b["season"]
                raws = pa["top5_raw"]
                tb = canon(raws, old_normalize)
                ta = canon(raws, normalize_crop)
                nslots_b += len(raws)
                nslots_a += len(raws)
                oorb += sum(1 for x in raws if old_normalize(x) is None)
                oora += sum(1 for x in raws if normalize_crop(x) is None)
                lens_b.append(len(tb))
                lens_a.append(len(ta))
                accb.append(accuracy_at_k(tb, c3, 5))
                acca.append(accuracy_at_k(ta, c3, 5))
                jacb.append(jaccard_similarity(tb, c3))
                jaca.append(jaccard_similarity(ta, c3))
                svb.append(season_validity_rate(tb, season))
                sva.append(season_validity_rate(ta, season))
            if not lens_b:
                continue
            n = len(lens_b)
            row = dict(model=m, condition=cond, n=n,
                       len_before=float(np.mean(lens_b)), len_after=float(np.mean(lens_a)),
                       oor_before=oorb / nslots_b, oor_after=oora / nslots_a,
                       acc_before=float(np.mean(accb)), acc_after=float(np.mean(acca)),
                       jac_before=float(np.mean(jacb)), jac_after=float(np.mean(jaca)),
                       sv_before=float(np.mean(svb)), sv_after=float(np.mean(sva)))
            rows.append(row)
            print(f"{m:<9}{cond:<5}{n:>5}{row['len_before']:>7.2f}{row['len_after']:>7.2f}"
                  f"{row['oor_before']*100:>7.2f}%{row['oor_after']*100:>7.2f}%"
                  f"{row['acc_before']:>8.3f}{row['acc_after']:>8.3f}"
                  f"{row['jac_before']:>8.3f}{row['jac_after']:>8.3f}"
                  f"{row['sv_before']:>8.3f}{row['sv_after']:>8.3f}")
    out = ROOT / "eval/results/normalization_fix_before_after.json"
    json.dump(rows, open(out, "w"), indent=2)
    print(f"\n[fix] wrote {out}")


if __name__ == "__main__":
    main()