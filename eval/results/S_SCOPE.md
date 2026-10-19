# Series S - STEP 1 SCOPE (data sources + perturbation feasibility)

Status: exploratory scope note, **read-only**, awaiting review. No model calls made.
Author: eval harness audit, 2026-10-16. Files inspected: `mcp_server/*.py`,
`eval/evidence.py`, `eval/time_anchored.py`, `eval/weather_cache.py`,
`eval/mcp_eval/server.py`, `eval/mcp_runtime.py`, `eval/scenarios.py`,
`eval/tools/*.py`, `data/processed/*`, `crop_log*.csv`.

Goal of the series: test the core claim that LLM-only advice rests on
training-era knowledge while the MCP tool path lets the model use *current*
data. We do this by feeding the tools **changed conditions** and measuring
whether the tool-using conditions (C1a/C2a/C2b/C3) shift their advice while the
no-tool conditions (C0/C0b) do not.

Hard constraint for the series: **do NOT change any tool/MCP
structure/algorithm/prompt/weight/architecture**. Only the **DATA the tools
read** and the way runs are **launched/recorded** may differ. Shifted inputs are
called **"simulated scenarios"**, never real-time data. Originals are never
overwritten; all artefacts are new files under `eval/`.

---

## 1. What each tool reads (exact sources)

| MCP tool | Backing module | Data source | Live network? | Data file (perturbable) |
|---|---|---|---|---|
| `weather_tool` | `weather_tool.py` | Open-Meteo **forecast** client (7 past + 7 future days) | yes (live) | `eval/cache/weather/<district>.json` (harness) |
| `climate_tool` | `climate_tool.py` | Open-Meteo **archive** normals (2014-2023) | yes (live) | same weather cache (dates `< as_of`) |
| `risk_tool` | `risk_tool.py` | forecast (30 past + 7 fwd) + archive 2019-2023 (SPI-1) | yes (live) | same weather cache |
| `season_tool` | `season_tool.py` | wall clock `datetime.now(IST)` -> month -> season | no | scenario `as_of_date` (frozen clock) |
| `get_soil_by_coordinates` | `soil_tool.py` | `data/processed/mp_districts.geojson` + `data/processed/soil_fixed.json` | no | those two files |
| `crop_score` | `crop_score_tool.py` | the five evidence blocks + `crop_log.csv` (scorer KB) | no | `crop_log*.csv` (scorer KB) |

Notes:
- All weather-derived tools ultimately read the **same per-district daily
  series**: `eval/cache/weather/<district>.json` = Open-Meteo daily arrays
  `temperature_2m_mean/max/min`, `precipitation_sum` for 2013-12-01..2026-01-15
  (51 districts present).
- `crop_score_tool` returns `ranked_crops[:6]` with fixed weights
  (rainfall 0.20, temperature 0.15, soil 0.20, season 0.30, risk 0.15). These
  weights are part of the tool and are **not** touched by this series.
- Season/month map `MONTH_TO_SEASON` is fixed (tool constant); only the *date*
  the clock is pinned to varies.

## 2. How the harness injects data WITHOUT touching tool code

The eval layer already proves the mechanism (this is how every prior run worked):

1. `eval/time_anchored.TimeAnchoredBuilder` monkeypatches the shared Open-Meteo
   client singletons' `.fetch` to return **date-sliced payloads built from the
   weather cache**, freezes `datetime.now` inside `season_tool` /
   `crop_score_tool` to the scenario `as_of_date`, then calls the **real tool
   functions unchanged** (`eval/evidence.py` and `eval/time_anchored.py`).
2. `eval/scripts/build_evidence_v2.py` writes the resulting bundles to
   `eval/runs/archive_v2/evidence/`.
2. `eval/mcp_eval/server.py` (eval-only replay server) serves those bundles by
   `(lat,lon)` over MCP; `eval/mcp_runtime.McpToolRuntime` is the C2a/C2b client.
   The replay server never calls live tools.
3. `eval/scripts/test_mcp_equivalence.py` asserts in-process vs MCP outputs are
   byte-identical.

Consequence: **changing the data that feeds the tools is a data/launch change,
not a code change.** If we regenerate the weather cache (or the crop KB) into a
*perturbed copy* and point the harness at it, every tool (and every MCP client)
serves the perturbed conditions unchanged.

## 3. Perturbation feasibility (per lever)

| Lever | Injectable? | Injection point (no tool change) | In tool-using arms? |
|---|---|---|---|
| Temperature +X deg C | **Yes** | perturb copy of `eval/cache/weather/*.json` (add X to tmean/tmax/tmin) | C1a,C2a,C2b,C3 |
| Rainfall x% (dry/wet) | **Yes** | scale `precipitation_sum` in the weather-cache copy | C1a/C2a/C2b/C3 |
| Delayed monsoon onset | yes | shift rainfall timing in weather series; and/or shift scenario `as_of_date` | C1a/C2a/C2b/C3 |
| Sowing-window heat stress | yes | temperature perturbation concentrated in the sowing/peak window | C1a/C2a/C2b/C3 |
| Beyond-range extremes | yes | larger magnitude on the same weather lever | C1a/C2a/C2b/C3 |
| Soil change | possible (copy `soil_fixed.json`) | geojson/soil files | but not a "changed-condition" lever -> negative control / out of core |
| Crop KB change (Linseed etc.) | possible (inject `crop_log*.csv` via module path) | scorer KB | this is the *db_v2* lever, not climate; keep out of core S set |
| No-tool LLM conditions | by construction unaffected | - | C0/C0b cannot "see" perturbed files |

**Verdict: perturbation IS feasible** for the weather/climate/risk family
(the core of the claim) and for season timing, entirely at the harness layer,
with originals untouched and **zero changes under `mcp_server/`**.

## 3a. One harness hardening item (not a tool change)
`eval/tools/eval_risk_tool._load_weather_cache` hard-codes `Path("eval/cache/weather")`
instead of taking the cfg `cache_dir`. To point risk at a perturbed cache
without ambiguity, S-STEP 2 will either (a) route the perturbed cache through
the cfg override used by `TimeAnchoredBuilder`, and patch the risk-tool lookup
at the eval layer, or (b) run with an isolated cache root. This is an
**eval-layer** change only; `mcp_server/risk_tool.py` is untouched. Flagged here
so the design in S_PLAN is explicit.

## 4. Out of scope (would violate the rules)
- Adding tool parameters (e.g. a "climate scenario" arg) or new MCP tools.
- Changing Open-Meteo base URL/host, scoring weights, prompts, or thresholds.
- Editing any file under `mcp_server/`, or overwriting `crop_log.csv`,
  `data/processed/*`, `eval/cache/weather/*`.
- Describing simulated perturbations as observed/real-time data.

## 5. Forward plan (S-STEP 2..5 - not started)
- **S-STEP 2**: define named perturbation sets with sourced magnitudes
  (warming +1/+2/+3 C; rainfall -20/-40%/+30%; delayed onset 2/4 weeks;
  sowing-window heat stress; combined +2C & -30% rain; one beyond-range;
  negative controls incl. a no-perturbation replay; natural experiments where a
  real historical departure is reusable). Every magnitude cited (IMD / IPCC AR6
  central India) with URL + retrieval date.
- **S-STEP 3**: derive an offline oracle (feasible set + newly infeasible crops)
  from `hard_constraints_v1.1.csv` + `crop_season_table_v1.2.csv`, confirming it
  does not read `crop_log.csv` (same independence argument as `CIRCULARITY.md`).
- **S-STEP 4**: pre-register the S-series metrics and contrasts in `PROTOCOL.md`
  (timestamped).
- **S-STEP 5: STOP** - write `eval/results/S_PLAN.md` (base set, variants,
  calls, tokens, hours, abort rules) and await approval before any model call.

## 5. Evidence partition (proposed, to confirm in S_PLAN)
Base scenarios: reuse the frozen `pilot_dev` / `pilot_union` design discipline
(report per-protocol and ITT with/without the 40 `pilot_dev` rows) so no
scenario is used both to pick perturbations and to report them.

## 6. Reproduce this audit
```
python -u -c "from eval.time_anchored import TimeAnchoredBuilder; \
print(TimeAnchoredBuilder().build({'scenario_id':'TEST','district':'Bhopal',\
'lat':23.2599,'lon':77.4126,'as_of_date':'2024-07-15'})['crop_score']['ranked_crops'])"
```
(uses cached weather only; no network, no writes)
