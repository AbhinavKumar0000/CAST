import json
import sys
from collections import Counter
from pathlib import Path

SERIES = {
    "v1-bundles(adhoc/evidence)": ("bundle", Path("eval/runs/adhoc/evidence")),
    "v1-grid(adhoc/deterministic)": ("grid", Path("eval/runs/adhoc/deterministic")),
    "v2-bundles(archive_v2/evidence)": ("bundle", Path("eval/runs/archive_v2/evidence")),
    "v2-grid(archive_v2/deterministic)": ("grid", Path("eval/runs/archive_v2/deterministic")),
}

only = sys.argv[1] if len(sys.argv) > 1 else None
SERIES = {k: v for k, v in SERIES.items() if (only is None or only in k)}

out = {}
for label, (kind, p) in SERIES.items():
    t1 = Counter()
    t5 = Counter()
    n = Counter()
    for f in p.iterdir():
        if f.suffix != ".json":
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        if kind == "bundle":
            cs = d.get("crop_score") or {}
            names = [c["crop"] for c in (cs.get("ranked_crops") or [])]
            season = cs.get("current_season") or (d.get("season") or {}).get("current_season") or ""
        else:
            ab = d.get("ablations", {}).get("full_repo") or {}
            names = ab.get("top6") or []
            season = d.get("season") or ""
        if not names or season not in ("Kharif", "Rabi", "Zaid"):
            continue
        n[season] += 1
        t1[(season, names[0])] += 1
        t5[(season, "Barley" in names[:5])] += 1
    rabi = max(n["Rabi"], 1)
    b1 = t1.get(("Rabi", "Barley"), 0)
    b5 = t5.get(("Rabi", True), 0)
    out[label] = {"n_rabi": n["Rabi"], "rabi_barley_top1": b1,
                  "rabi_barley_top1_pct": round(100 * b1 / rabi, 1),
                  "rabi_barley_top5": b5, "rabi_barley_top5_pct": round(100 * b5 / rabi, 1)}

for k, v in out.items():
    print(f"{k:34s} n_Rabi={v['n_rabi']:5d}  Barley#1={v['rabi_barley_top1']:5d} ({v['rabi_barley_top1_pct']}%)  "
          f"Barley_top5={v['rabi_barley_top5']:5d} ({v['rabi_barley_top5_pct']}%)")

Path("eval/results/_barley_source_audit.json").write_text(json.dumps(out, indent=2), encoding="utf-8")