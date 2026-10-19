"""Offline audit of the MCP C2a equivalence run's freshness (2026-10-14).

Answers:
  Q1  cache key vs transport: does the key/path isolate MCP from in-process? how many of
      the 50 MCP C2a records were cache-served vs generated fresh?
  Q2  HTTP accounting: what the budget counter counts vs what the 50 calls actually issued
      (derived from the tool-log rounds, since per-attempt HTTP is not stored).
  Q3  freshness: timestamps / any response ids, side by side with the in-process B1 C2a
      records for the same scenario_ids.

Pure offline; reads results.json + the transport-scoped cache dir. No API calls.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

B1 = REPO / "eval/runs/eval_nemotron-3-ultra/results.json"
MCP = REPO / "eval/runs/eval_nemotron-3-ultra_mcp_c2a50/results.json"
MCP_CACHE = REPO / "eval/cache/llm/nemotron-3-ultra_mcp"
INPROC_CACHE = REPO / "eval/cache/llm/nemotron-3-ultra"
MODEL = "nvidia/nemotron-3-ultra-550b-a55b"


def load(path, cond="C2a"):
    by = {}
    for r in json.loads(path.read_text(encoding="utf-8")):
        if r.get("condition") == cond:
            by[r["scenario_id"]] = r
    return by


def cache_key(model, cond, prompt, sid, rep):
    payload = "\u241f".join([model, cond, prompt, sid, str(rep)])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def rounds_of(r):
    return sorted({e.get("round") for e in (r.get("tool_log") or [])})


def est_http(r):
    """post() is called once per tool-bearing round + 1 final; +1 if forced_final."""
    rounds = rounds_of(r)
    n_tool_rounds = len(rounds)
    return n_tool_rounds + 1 + (1 if r.get("forced_final") else 0)


def main() -> int:
    b1 = load(B1)
    mcp = load(MCP)
    sids = sorted(mcp)
    common = sorted(set(b1) & set(mcp))

    print("=" * 90)
    print("Q1  CACHE KEY / TRANSPORT ISOLATION")
    print("=" * 90)
    # Reproduce the cache filename for an MCP record and show where the file lives.
    ex = mcp[common[0]]
    ph = ex.get("prompt_hash")
    key_payload = ("cache key payload = \"\\u241f\".join([model, cond, prompt, sid, rep])  -> "
                   "NO tool_transport term")
    print(f"  {key_payload}")
    print(f"  cache DIR is transport-scoped: run_model uses '<short>_mcp' for mcp "
          f"(eval/scripts/run_model.py:147)")
    print(f"    in-process dir: {INPROC_CACHE}  -> {len(list(INPROC_CACHE.glob('*.json')))} files")
    print(f"    mcp dir       : {MCP_CACHE}  -> {len(list(MCP_CACHE.glob('*.json')))} files")
    # Does the MCP record's cache file exist only in the mcp dir, and carry the SAME prompt_hash
    # as the B1 record (same key payload, different namespace)?
    same_hash = sum(1 for s in common if mcp[s].get("prompt_hash") == b1[s].get("prompt_hash"))
    mcp_file_exists = sum(1 for s in common if (MCP_CACHE / f"{mcp[s]['prompt_hash']}.json").exists())
    b1_file_exists = sum(1 for s in common if (INPROC_CACHE / f"{b1[s]['prompt_hash']}.json").exists())
    print(f"  of {len(common)} shared sids: identical prompt_hash B1 vs MCP = {same_hash}")
    print(f"    B1 record's cache file present in in-process dir: {b1_file_exists}/{len(common)}")
    print(f"    MCP record's cache file present in mcp dir       : {mcp_file_exists}/{len(common)}")
    # Freshness discriminator available in-record: timestamp. Cache-served records keep the
    # original timestamp, so a re-run would carry an old timestamp. All MCP timestamps should
    # cluster at the run time and be absent from B1.
    b1_ts = {b1[s].get("timestamp") for s in common}
    mcp_ts = {mcp[s].get("timestamp") for s in common}
    print(f"  distinct timestamps: B1={len(b1_ts)} MCP={len(mcp_ts)} "
          f"overlap={len(b1_ts & mcp_ts)}")

    print("\n" + "=" * 90)
    print("Q2  HTTP ACCOUNTING")
    print("=" * 90)
    for label, src in (("B1 C2a (in-process, n=150)", b1), ("MCP C2a (n=50)", mcp)):
        rr = list(src.values())
        tot_rounds = sum(len(rounds_of(r)) for r in rr)
        tot_tools = sum(r.get("tool_calls", 0) for r in rr)
        tot_est = sum(est_http(r) for r in rr)
        forced = sum(1 for r in rr if r.get("forced_final"))
        print(f"  {label}:")
        print(f"    scenarios={len(rr)}  tool_calls_total={tot_tools}  "
              f"distinct_rounds_total={tot_rounds}")
        print(f"    est. HTTP attempts = rounds + 1/scen + forced = {tot_est} "
              f"(forced_final={forced})  ->  {tot_est/len(rr):.2f}/scenario")
    mcp50_est = sum(est_http(r) for r in mcp.values())
    print(f"  MCP 50 estimated HTTP = {mcp50_est}; observed budget delta = 947-824 = 123")

    print("\n  per-scenario detail (first 12, MCP): sid rounds tool_calls est_http")
    for s in sids[:12]:
        r = mcp[s]
        print(f"    {s} rounds={len(rounds_of(r))} tool_calls={r.get('tool_calls')} "
              f"est={est_http(r)}")

    def _hist(rr):
        h = {}
        for r in rr:
            k = len(rounds_of(r))
            h[k] = h.get(k, 0) + 1
        return h

    def base_http(rr):
        # exact no-retry post() calls: (max tool-call round + 1) during the loop, +1 final.
        tot = 0
        for r in rr:
            rs = rounds_of(r)
            tot += (max(rs) + 2) if rs else 1
        return tot

    print(f"\n  rounds-per-scenario histogram  B1 C2a={_hist(list(b1.values()))}  "
          f"MCP C2a={_hist(list(mcp.values()))}")
    print(f"  exact no-retry post() calls: B1 C2a={base_http(list(b1.values()))}  "
          f"MCP C2a={base_http(list(mcp.values()))}")
    delta = 947 - 824
    print(f"  MCP: exact no-retry={base_http(list(mcp.values()))} vs budget delta={delta} "
          f"-> excess={delta - base_http(list(mcp.values()))} (retry attempts counted by reserve())")

    # Per-condition B1 actuals -> B2 (350 remaining) projection.
    print("\n  B1 per-condition HTTP (exact no-retry) and B2 projection (350 scenarios):")
    b1_all = json.loads(B1.read_text(encoding="utf-8"))
    proj_total = 0
    for cond in ("C1a", "C2a", "C2b"):
        rr = [r for r in b1_all if r.get("condition") == cond]
        base = base_http(rr)
        per = base / len(rr) if rr else 0
        proj = round(per * 350)
        proj_total += proj
        print(f"    {cond}: n={len(rr)} base_http={base} ({per:.2f}/scen) -> B2 ~{proj} HTTP")
    print(f"    B2 projected total (exact, no retries) ~= {proj_total} HTTP "
          f"(vs 4,900 estimate that assumed 7.0/scen for C2a and 6.0 for C2b)")

    print("\n" + "=" * 90)
    print("Q3  FRESH TIMESTAMPS + IDS (B1 vs MCP), same sids, side by side")
    print("=" * 90)
    print("  fields present in a record:", sorted(mcp[common[0]].keys()))
    for s in common[:4]:
        a, b = b1[s], mcp[s]
        print(f"\n  {s}")
        print(f"    B1 : ts={a.get('timestamp')}  lat={a.get('latency_s'):.1f}s "
              f"tools={a.get('tool_calls')} rounds={rounds_of(a)} finish={a.get('finish_reason')}")
        print(f"    MCP: ts={b.get('timestamp')}  lat={b.get('latency_s'):.1f}s "
              f"tools={b.get('tool_calls')} rounds={rounds_of(b)} finish={b.get('finish_reason')}")
    any_id = [k for r in (list(b1.values()) + list(mcp.values()))
              for k in r.keys() if "id" in k.lower()]
    print(f"\n  record keys containing 'id': {sorted(set(any_id)) or 'NONE'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
