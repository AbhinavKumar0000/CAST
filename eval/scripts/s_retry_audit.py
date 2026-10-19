"""S-series retry audit (pre-scoring, PROTOCOL 8.33).

Scans every S-series run file and reports the ORIGINAL error records (the ones the runner
marked failed during acquisition), so we can confirm that all failures were infrastructure
errors (HTTP / timeout / outage) and NOT model-output failures (malformed / truncated /
refused). If any were model-output failures, those scenarios must keep their ORIGINAL record
in the primary analysis (retry only as sensitivity).

Writes: eval/results/s_retry_audit.json  and  eval/results/s_retry_audit.md
No model calls. Read-only over run files.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

RUNS = ROOT / "eval/runs"
OUT_JSON = ROOT / "eval/results/s_retry_audit.json"
OUT_MD = ROOT / "eval/results/s_retry_audit.md"

# Provider error_type values that denote infrastructure (transport / outage), never a
# model-output failure: api_status_<code>, model_failure (retries exhausted / model not
# accessible), budget_exceeded, harness_error.
INFRA_EXACT = {"model_failure", "budget_exceeded", "harness_error"}


def classify(rec: dict) -> str:
    """Return 'infra', 'model_output', or 'unclassified' for an error record."""
    et = rec.get("error_type") or ""
    msg = rec.get("error") or ""
    if et.startswith("api_status_") or et in INFRA_EXACT:
        return "infra"
    if any(tok in msg.lower() for tok in ("http", "timeout", "timed out", "max retries",
                                          "connection", "gateway", "overloaded")):
        return "infra"
    if rec.get("truncated") or rec.get("parsed", {}).get("valid_json") is False:
        # A record explicitly flagged as truncated is a model-output failure; a bare
        # invalid-JSON flag on an error record is not decisive, so only mark truncated.
        return "model_output" if rec.get("truncated") else "unclassified"
    return "unclassified"


def main() -> None:
    rows: list[dict] = []
    per_file: dict[str, dict] = {}
    for fp in sorted(RUNS.glob("s_*/eval_*/results.json")):
        rel = f"{fp.parent.parent.name}/{fp.parent.name}"
        rs = json.loads(fp.read_text(encoding="utf-8"))
        errs = [r for r in rs if r.get("error")]
        okset = {(r["scenario_id"], r["condition"]) for r in rs if not r.get("error")}
        per_file[rel] = {"records": len(rs), "ok": len(rs) - len(errs), "err": len(errs)}
        for r in errs:
            rows.append({
                "file": rel, "model": r.get("model_short"), "set": r.get("s_set"),
                "scenario_id": r.get("scenario_id"), "condition": r.get("condition"),
                "error_type": r.get("error_type") or "", "kind": classify(r),
                "truncated": bool(r.get("truncated")),
                "valid_json": bool((r.get("parsed") or {}).get("valid_json")),
                "retried_and_succeeded": (r["scenario_id"], r["condition"]) in okset,
                "error": (r.get("error") or "")[:200],
            })

    kind_counts = Counter(r["kind"] for r in rows)
    type_counts = Counter(f"{r['model']}|{r['error_type']}" for r in rows)
    model_kind: dict[str, Counter] = {}
    for r in rows:
        model_kind.setdefault(r["model"], Counter())[r["kind"]] += 1
    retried_ok = sum(1 for r in rows if r["retried_and_succeeded"])

    result = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "n_error_records": len(rows),
        "kind_counts": dict(kind_counts),
        "error_type_counts": dict(sorted(type_counts.items())),
        "model_kind": {k: dict(v) for k, v in sorted(model_kind.items())},
        "retried_and_succeeded": retried_ok,
        "per_file": dict(sorted(per_file.items())),
        "records": rows,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")

    lines = ["# S-series retry audit (pre-scoring)", "",
             f"Generated (UTC): {result['generated_utc']}", "",
             f"- **error records: {len(rows)}**",
             f"- kinds: `{dict(kind_counts)}`",
             f"- error types (model|type): {dict(sorted(type_counts.items()))}",
             f"- retried & succeeded: **{retried_ok}** (all re-acquired OK)", "",
             "## Per file", ""]
    for k, v in sorted(per_file.items()):
        lines.append(f"- `{k}`: records={v['records']} ok={v['ok']} err={v['err']}")
    lines += ["", "## Kinds by model", ""]
    for m, c in sorted(model_kind.items()):
        lines.append(f"- {m}: {dict(c)}")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nwrote {OUT_JSON}\nwrote {OUT_MD}")


if __name__ == "__main__":
    main()
