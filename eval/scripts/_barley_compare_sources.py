import json
from pathlib import Path

ADH = Path("eval/runs/adhoc/evidence")
DET = Path("eval/runs/archive_v2/deterministic")

agree = 0
diff = 0
diff_samples = []
for f in DET.iterdir():
    if f.suffix != ".json":
        continue
    sid = f.stem
    det = json.loads(f.read_text(encoding="utf-8"))
    names_d = (det.get("ablations", {}).get("full_repo") or {}).get("top6") or []
    season = det.get("season") or ""
    if season != "Rabi":
        continue
    ah = ADH / f.name
    if not ah.exists():
        continue
    a = json.loads(ah.read_text(encoding="utf-8"))
    cs = a.get("crop_score") or {}
    names_a = [c["crop"] for c in (cs.get("ranked_crops") or [])]
    if not names_d or not names_a:
        continue
    if names_a[0] == names_d[0]:
        agree += 1
    else:
        diff += 1
        if len(diff_samples) < 8:
            diff_samples.append((sid, names_a[0], names_d[0], names_a[:4], names_d[:4]))

print("Rabi scenarios compared:", agree + diff)
print("top1 agree:", agree, " top1 differ:", diff)
for s in diff_samples:
    print("  ", s)