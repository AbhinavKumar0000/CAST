"""Inspect run-dir metadata + any config hash/params for reuse eligibility check."""

import json
import os
from pathlib import Path

for d in sorted(Path("eval/runs").iterdir()):
    if not d.is_dir() or d.name.startswith("archive"):
        continue
    files = sorted(f.name for f in d.iterdir())
    print(f"\n=== {d.name} :: {files}")
    for fname in files:
        p = d / fname
        if fname.endswith(".json") and fname != "results.json":
            try:
                head = p.read_text(encoding="utf-8")[:400]
                print(f"  -- {fname}: {head.splitlines()[0][:200]}")
            except Exception as e:
                print(f"  -- {fname}: ERR {e}")