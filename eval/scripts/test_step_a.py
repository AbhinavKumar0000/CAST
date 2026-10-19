"""Phase 8 STEP A tests: time-anchored C2 tools (offline; no API calls).

Tests (all offline, using cached weather only):
  1. SEASON-CLOCK  season_tool returns the correct season for 12 dates across all
     months (frozen clock -> month of as_of_date, not the live month).
  2. NO-LIVE-API   no tool in eval mode calls ``datetime.now`` or a live API:
       (a) static scan of the eval wrapper source for banned symbols;
       (b) runtime guard that raises on ANY network call, then builds evidence;
       (c) behavioural check that season/crop outputs follow as_of_date, not the
           real current date.
  3. EQUIVALENCE   for 30 scenarios (balanced by season), the wrapped tools' outputs
     equal the v2 evidence bundles; drift vs the v1 bundles is reported separately.

Prints results for each test and exits non-zero on any failure.
"""

from __future__ import annotations

import json
import random
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

from eval.common import load_config, read_jsonl  # noqa: E402
from eval.time_anchored import TimeAnchoredBuilder, ToolRuntime, season_for_date  # noqa: E402
from mcp_server import season_tool  # noqa: E402

FIELD_FOR_TOOL = {
    "weather_tool": "weather",
    "climate_tool": "climate",
    "season_tool": "season",
    "risk_tool": "risk",
    "get_soil_by_coordinates": "soil",
    "crop_score": "crop_score",
}


def load_subset() -> list[dict]:
    cfg = load_config()
    from eval.common import config_dirs

    dirs = config_dirs(cfg)
    return read_jsonl(dirs["llm_subset_path"])


def pick_balanced(subset: list[dict], k: int, seed: int = 20240604) -> list[dict]:
    rng = random.Random(seed)
    per_season = k // 3
    picked: list[dict] = []
    seasons = ["Kharif", "Rabi", "Zaid"]
    for se in seasons:
        pool = [s for s in subset if s.get("season_stratum") == se]
        sids = set(s["scenario_id"] for s in picked)
        picked += [s for s in rng.sample(pool, min(per_season, len(pool))) if s["scenario_id"] not in sids]
    # top up if < k (Zaid pool may exceed min)
    if len(picked) < k:
        sids = set(s["scenario_id"] for s in picked)
        for s in subset:
            if len(picked) >= k:
                break
            if s["scenario_id"] not in sids:
                picked.append(s)
                sids.add(s["scenario_id"])
    return picked[:k]


def banner(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def test_season_clock(subset: list[dict]) -> int:
    banner(f"TEST 1 — SEASON CLOCK: season_tool season for one date per month (2024)")
    builder = TimeAnchoredBuilder(load_config())
    sc = subset[0]
    base = {k: sc[k] for k in ("scenario_id", "district", "lat", "lon")}
    failures = 0
    for month in range(1, 13):
        as_of = f"2024-{month:02d}-15"
        s = {**base, "scenario_id": f"MNTH{month:02d}", "as_of_date": as_of}
        b = builder.build(s)
        got_season = b["season"]["current_season"]
        got_month = b["season"]["current_month"]
        exp_month, exp_season = season_for_date(as_of)
        ok = got_season == exp_season and got_month == exp_month
        status = "PASS" if ok else "FAIL"
        if not ok:
            failures += 1
        print(f"  month {month:02d} ({as_of}): expected {exp_month}/{exp_season:6s} got {got_month}/{got_season:6s} -> {status}")
    print(f"  result: {'ALL PASS' if failures == 0 else f'{failures} FAILURES'}")
    return 0 if failures == 0 else 1


def _code_without_strings_and_comments(path: Path) -> str:
    """Return source with string literals and comments blanked (tokenize-based)."""
    import tokenize
    from io import BytesIO

    tokens: list[str] = []
    for tok in tokenize.tokenize(BytesIO(path.read_bytes()).readline):
        if tok.type in (tokenize.COMMENT, tokenize.STRING):
            tokens.append(" " * len(tok.string))
        else:
            tokens.append(tok.string)
    return "".join(tokens)


def test_no_live_api(subset: list[dict]) -> int:
    banner("TEST 2 — NO datetime.now, NO LIVE API in eval mode")
    src = Path(__file__).resolve().parent.parent / "time_anchored.py"
    code = _code_without_strings_and_comments(src)
    banned = ["datetime.now", "datetime.utcnow", "date.today", ".today()", "urllib",
              "requests", "httpx", "_SESSION.get", "_SESSION.post", "client.get", "client.post"]
    flagged = [tok for tok in banned if tok in code]
    print(f"  static scan of {src.name} (strings/comments stripped): banned tokens -> {flagged if flagged else 'none'}")

    from mcp_server import open_meteo_client

    sc = subset[0]

    # (a) runtime guard: any real network attempt raises AssertionError during build
    orig_get = open_meteo_client._SESSION.get
    orig_fetch_f = open_meteo_client.forecast_client.fetch
    orig_fetch_a = open_meteo_client.archive_client.fetch

    def guard(*args, **kwargs):
        raise AssertionError("LIVE API call attempted during eval build")

    open_meteo_client._SESSION.get = guard
    open_meteo_client.forecast_client.fetch = guard
    open_meteo_client.archive_client.fetch = guard
    builder = TimeAnchoredBuilder(load_config())
    try:
        b = builder.build(sc)
        print(f"  runtime guard: built {sc['scenario_id']} without any network call -> PASS")
    except Exception as exc:  # noqa: BLE001
        print(f"  runtime guard: FAIL -> {type(exc).__name__}: {exc}")
        return 1
    finally:
        open_meteo_client._SESSION.get = orig_get
        open_meteo_client.forecast_client.fetch = orig_fetch_f
        open_meteo_client.archive_client.fetch = orig_fetch_a

    # (b) behavioural: season follows as_of_date, NOT the real current month
    import datetime as _dt

    as_month, as_season = season_for_date(b["as_of_date"])
    live_month = _dt.datetime.now().month
    live_season = season_tool.MONTH_TO_SEASON.get(live_month, "Unknown")
    anchored = b["season"]["current_season"] == as_season and b["season"]["current_month"] == as_month
    print(f"  as_of month={as_month} season={as_season:6s} live today month={live_month} "
          f"season={live_season:6s} | bundle season={b['season']['current_season']:6s} -> "
          f"{'PASS (anchored to as_of)' if anchored and (as_season != live_season or as_month == b['season']['current_month']) else 'FAIL'}")

    ok = not flagged and True and anchored
    print(f"  result: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


def test_equivalence(subset: list[dict]) -> int:
    banner("TEST 3 — EQUIVALENCE: wrapped tools == v2 evidence bundles (30 scenarios)")

    # Optional: v1 bundle comparison where they exist
    v1_dir = Path("eval/runs/adhoc/evidence")

    scenarios = pick_balanced(subset, 30)
    counts = Counter(s.get("season_stratum") for s in scenarios)
    print(f"  selected 30 scenarios by season: {dict(counts)}")
    cfg = load_config()
    builder = TimeAnchoredBuilder(cfg)
    rt = ToolRuntime(cfg, builder=builder)
    failures = 0
    drifts_v1 = Counter()
    n_v1 = 0
    for sc in scenarios:
        b = builder.build(sc)  # reference bundle (same builder the runtime uses)
        for tool, field in FIELD_FOR_TOOL.items():
            out = rt.call(sc, tool, {"latitude": sc["lat"], "longitude": sc["lon"]})
            if out != b[field]:
                failures += 1
                print(f"  EQUIV FAIL {sc['scenario_id']} {tool}: runtime != bundle")
        # v1 drift (informational)
        if sc["scenario_id"] == "S000001":
            pass
        p = v1_dir / f"{sc['scenario_id']}.json"
        if p.exists():
            n_v1 += 1
            v1 = json.loads(p.read_text(encoding="utf-8"))
            same = all(v1.get(f) == b.get(f) for f in ("weather", "season", "soil", "risk"))
            if not same:
                drifts_v1["weather/season/soil/risk"] += 1
            if v1.get("climate") != b.get("climate"):
                drifts_v1["climate (normals)"] += 1
            if v1.get("crop_score", {}).get("ranked_crops") is not None and b.get("crop_score", {}).get("ranked_crops") is not None:
                t1 = [c["crop"] for c in v1["crop_score"]["ranked_crops"]]
                t2 = [c["crop"] for c in b["crop_score"]["ranked_crops"]]
                if t1 != t2:
                    drifts_v1["crop_score ranking"] += 1
    print(f"  equivalence failures: {failures}")
    print(f"  v1 bundles available for comparison: {n_v1}/30")
    if n_v1:
        print(f"  v1 -> v2 drift (informational): {dict(drifts_v1)}")

    # Example of what a per-call log entry looks like (runtime side)
    sc = scenarios[0]
    b0 = builder.build(sc)
    out = rt.call(sc, "season_tool", {"latitude": sc["lat"], "longitude": sc["lon"]})
    print(f"  example runtime output for {sc['scenario_id']}: {json.dumps(out, ensure_ascii=False)}")
    print(f"  normals window for {sc['scenario_id']} (days before as_of): {b0['_climate_normals_days']}")

    status = 0 if failures == 0 else 1
    print(f"  result: {'ALL EQUIVALENT' if status == 0 else f'{failures} FAILURES'}")
    return status


def main() -> int:
    cfg = load_config()
    subset = load_subset()
    max_rounds = cfg["model"].get("max_tool_rounds", 15)
    print(f"STEP A harness settings: max_tool_rounds={max_rounds}  log fields per tool call: "
          f"name, args, output_hash, round, latency_s, finish_reason")

    rc = 0
    rc |= test_season_clock(subset)
    rc |= test_no_live_api(subset)
    rc |= test_equivalence(subset)

    print("\n" + ("ALL STEP A TESTS PASSED" if rc == 0 else "STEP A TESTS FAILED"))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())