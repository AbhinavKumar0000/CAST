# AgroLLaMA: Evaluation Harness & Scenarios (Calling, Testing, Scoring)

**Audience:** engineers who must understand *exactly* how the tools are invoked (both at
runtime by the LLM and offline by the evaluation), how the test scenarios are generated,
and how every run becomes a number.

**Scope:** tool invocation (live orchestrator + evaluation harness), scenario generation,
time anchoring, the run harness, scoring, and statistics. The *meaning* of the resulting
figures is in `FIGURES_EXPLAINED.md`; the tools' internal mathematics is in
`TOOLS_REFERENCE.md`.

---

## PART A: How the tools are called

There are **two completely separate callers**. They expose the *same* six tools with the
*same* `(latitude, longitude)` contract, which is the key design property: the product and
the experiment run identical tool code.

| | Live product | Evaluation harness |
|---|---|---|
| Caller | `app/llm/gemini_client.py` | `eval/llm/nvidia_provider.py` |
| Transport | real MCP over streamable-http | in-process `ToolRuntime` (default) or real MCP (`--tool-transport mcp`) |
| Model | Google Gemini | NVIDIA NIM (OpenAI-compatible) |
| Tool set | all six | condition-dependent (5 or 6) |
| Clock/weather | live | pinned to scenario `as_of_date`, cached archive |

### A.1 The live orchestrator path

`app/main.py` receives `POST /analyze {latitude, longitude}` and calls
`app.orchestrator.run_analysis`, which delegates to
`GeminiClient.run_tool_calling_loop` (`app/llm/gemini_client.py`). The loop:

1. On client construction, opens a short-lived MCP session and calls **`list_tools()`** to
   discover the six tools, then converts each MCP schema into a Gemini
   `FunctionDeclaration`. Gemini rejects some JSON-Schema fields (`title`, `$schema`,
   `default`), so those are **recursively stripped** (`gemini_client.py:145-161`).
2. Sends a system prompt (`gemini_client.py:258`, JSON-only) plus the user message
   (coordinates, today's IST date/week, the crop reference table) to Gemini.
3. Gemini returns one or more **function calls**; for each, a fresh MCP session invokes
   **`call_tool(name, args)`**, the server runs the real tool, and the JSON result is
   injected back as a `FunctionResponse`.
4. Repeats up to **15 rounds** until Gemini returns final text.
5. Coerces all outputs to native JSON primitives (`_to_native` / `_to_proto_safe`,
   `gemini_client.py:43-89`), necessary because GeoPandas/NumPy scalars are not
   Proto-safe, and returns `AnalyzeResponse{tool_execution_order, tools_output,
   llm_final_message}`.

Transport is `streamable-http` on `http://<host>:8001/mcp`. Tool *declarations* are fetched
once per client instance; each *call* opens its own session. Because the tool list is
discovered at runtime, adding a tool to the server requires **no** orchestrator change.

### A.2 The evaluation harness path

The evaluator never talks to the live MCP server in the default configuration. Instead,
`eval/scripts/run_model.py` builds an **offline tool runtime** and a provider that serves
tool calls from it.

**Condition → tool set → prompt** mapping (`run_model.py:build_prompt`):

| Condition | Prompt builder | Tools exposed | Uses tool loop |
|---|---|---|---|
| C0 | `prompt_c0` | none | no |
| C0b | `prompt_c0b` | none | no |
| C1a | `prompt_c1a` (raw evidence pasted) | none | no |
| C1b | `prompt_c1b` (leaks C3 ranking) | none | no |
| C2a | `prompt_c2` | **six** (`SIX_TOOLS`) | yes |
| C2b | `prompt_c2` | **five** (`FIVE_TOOLS`, no `crop_score`) | yes |

`FIVE_TOOLS = [weather_tool, climate_tool, season_tool, risk_tool,
get_soil_by_coordinates]`; `SIX_TOOLS = FIVE_TOOLS + [crop_score]`.

The prompt tells the model it **must call all listed tools** before recommending, and
(except for the six-tool set) "do NOT call any other tool".

**Tool execution (`NvidiaProvider._execute_tool`):**

* If a tool name is not in the condition's allowed set, the provider returns a benign
  error string listing the valid tools and instructing the model to emit its JSON now
  (`unknown: True`). This enforces the C2b ablation and prevents C2a-only tools leaking
  into other conditions.
* With an offline `tool_runtime` and a scenario, the call is served by
  `ToolRuntime.call(scenario, name, args)`, deterministic, no network, no wall clock.
* The legacy live path (`mcp_server.*.run`) is retained for backward compatibility only.

**The tool-calling loop (`NvidiaProvider.run`):**

* Up to `max_tool_rounds = 15` rounds (configurable; raised from 10 for six-tool scenarios).
* Completion cap: `max_output_tokens_tools = 2048`; non-tool runs use 4096, but C1a/C1b are
  given 8192 (see §A.4).
* Every tool call is logged with round index, name, args, an output **hash**
  (`sha256(...)[:16]`), and per-call latency (`tool_log`).
* **Harness fix ss8.10**, two safeguards prevent a stalled model burning all rounds:
  * if **two consecutive** unknown-tool calls occur, or
  * the loop reaches **round 12** (`FORCE_FINAL_ROUND`),
  the provider sends **one final request with tools disabled** and a "reply with the JSON
    object only" instruction, and records `forced_final=True` with the reason.
* On retryable HTTP status (429/5xx) the provider rotates API keys round-robin and backs
  off exponentially with jitter.
* A **UTC-day HTTP budget** (default 4,000 requests) is enforced across all provider
  instances via a persisted counter; hitting it raises a clean `budget_exceeded` stop that
  is **not** recorded or cached, so the run resumes the next UTC day.

### A.3 The offline tool runtime (`eval/time_anchored.py`)

`TimeAnchoredBuilder` runs the **real** `mcp_server/` tool code with two injections:

1. **Frozen clock.** A `FrozenDateTime` subclass replaces `datetime` inside
   `season_tool` and `crop_score_tool` (`time_anchored.py:80-94, 191-193`). `now()` and
   `utcnow()` return the scenario's `as_of_date` at 12:00 IST. Because those two modules
   are the *only* wall-clock dependencies, season and `crop_score.current_week` become
   scenario-scoped.
2. **Patched weather clients.** `open_meteo_client.forecast_client.fetch` and
   `archive_client.fetch` are monkey-patched (`time_anchored.py:169-197`) to return
   date-sliced archive payloads shaped exactly like the live API:
   * a request with `past_days ≥ 30` (the risk window) → the 30-past + 7-forecast
     **risk payload**;
   * otherwise → the 7-past + 7-forecast **weather payload**;
   * an archive request starting `2019` → the **SPI payload** (2019–2023 precipitation);
   * any other archive request → the **climate payload**, built **only from dates strictly
     before `as_of_date`** (no look-ahead in the normals).

The TTL caches (`weather_tool._WEATHER_CACHE`, `climate_tool._CLIMATE_CACHE`) are cleared
on every `_install_patches` so no scenario's "current" weather leaks into the next.

`build(scenario)` returns a v2 evidence bundle:
`{scenario_id, district, as_of_date, weather, climate, season, soil, risk, crop_score,
_v: 2, _climate_normals_days}`.

`ToolRuntime` is the thread-safe dispatcher: it builds each scenario's bundle **once**
(cached under a lock) and serves any of the six tool names from it. Its `call` method
rejects calls missing lat/lon and returns the same benign `unknown` error shape for an
unrecognised name.

> **Equivalence guarantee.** `eval/scripts/test_step_a.py` asserts that the per-tool
> outputs served by `ToolRuntime` are **byte-identical** to the bundles built by
> `TimeAnchoredBuilder`, i.e. the LLM (C2a/C2b) and the deterministic reference (C3) see
> *exactly the same numbers*. Nothing under `mcp_server/` is modified by the evaluation.

A real-MCP transport is also available (`run_model.py --tool-transport mcp`), which points
an MCP client at `eval/mcp_eval/server.py` over streamable-http. The cache namespace is
transport-scoped (`_mcp` suffix) so a real-transport run can never silently reuse
in-process cached records; this only changes the *transport*, not the evidence.

### A.3a The provider tool schema (`NvidiaProvider._build_tools`)

Each condition's tools are declared to the model as OpenAI-style function schemas, all with
the same two required arguments `{latitude: number, longitude: number}` and the same
one-line descriptions used by the live MCP server:

| Tool | Description shown to the model |
|---|---|
| `weather_tool` | temperature, rainfall, humidity, precipitation probability |
| `climate_tool` | average rainfall, average temperature, monthly normals |
| `season_tool` | current cropping season in IST: Kharif, Rabi, Zaid |
| `risk_tool` | drought, flood, and heatwave risk analysis |
| `get_soil_by_coordinates` | district, dominant soil, characteristics, suitability (Madhya Pradesh) |
| `crop_score` | deterministic ranking over weather/climate/soil/season/risk |

For C2b the schema list is filtered to drop `crop_score`, so the model cannot even see the
ranker.

### A.4 Output-cap amendment (PROTOCOL ss8.10, 2026-10-13)

`run_model.py:249` gives the **tool-condition prompts without tools** (C1a/C1b) the raised
8192 cap (`max_output_tokens_tools`) even though no tools are in the payload, because the
pasted-evidence prompts are long. C0/C0b keep the non-tool 4096 cap
(`max_output_tokens=None` → provider default). This is recorded so that C1a's truncation
rate at n=500 is interpretable.

---

## PART B: Scenario generation

*File:* `eval/scenarios.py`. Everything is seeded (`config["seeds"]["scenario_sampling"]`)
so the set is reproducible.

### B.1 Distribution over districts and seasons

1. Load `data/processed/mp_districts.geojson`; the district list is the sorted set of
   `NAME_2` values → **51 districts**.
2. `n_total = config.scenarios.n_total` (10,000). Split as evenly as possible:
   `base = n_total // 51`, `remainder = n_total − base × 51`; the first `remainder`
   districts get one extra scenario.
3. Within each district, scenarios are divided evenly across the three seasons
   (`Kharif`, `Rabi`, `Zaid`), the leftover cycled, then **shuffled**.
4. For each scenario:
   * **Point** = `_sample_point(geom, rng)`: sample `(lon, lat)` uniformly in the polygon's
     bounding box and accept the first point inside the geometry (rejection sampling, up
     to a cap, then the representative point). This guarantees the point is inside MP.
   * **Date** = `_dates_for_season(season, rng)`: pick a year in `{2024, 2025}`, a month
     from the season's month list, and a day in `1..28`.
   * `month` = the date's month; `season_by_month` = `MONTH_TO_SEASON[month]` (imported
     from `season_tool`, so it is the same map the tool uses); `season_stratum` = the
     stratum it was sampled for.
   * `agro_climatic_zone` from `ground_truth/district_zone_map.csv` (if present).

Each scenario is `S000001…` with `{scenario_id, district, lat, lon, as_of_date, month,
season_by_month, season_stratum, agro_climatic_zone}`.

### B.2 Stress set and the stratified LLM subset

* A **stress set** flags scenarios in drought / heat / flood conditions (from the evidence
  bundles' risk fields).
* The **LLM subset** (500) is drawn with `config.seeds.llm_subset_sampling`:
  shuffle stress and non-stress separately; take `min(min_stress, #stress)` stress rows;
  fill the remainder with non-stress; if non-stress is insufficient, top up with more
  stress; then **re-sort by `scenario_id`** for determinism. The subset therefore contains
  ≈150 stress rows.

### B.3 The two flip-halves

The 500-subset is run in two contiguous slices for operability:

* **B1** = indices `0..149` (150 scenarios) → `eval/runs/eval_nemotron-3-ultra/`.
* **B2** = indices `150..499` (350 scenarios) → `eval/runs/eval_nemotron-3-ultra_b2/`.

`run_model.py --scenario-start 150 --scenarios 350` produces B2. The merged n=500 primary
analysis concatenates B1+B2. B1/B2 are **near district-disjoint**, which is why the paper
treats the B1-vs-B2 gap as district composition rather than a clean batch effect
(`FIGURES_EXPLAINED.md`, Fig_N04).

### B.4 Deterministic reference over 10,000 scenarios

For **all 10,000** scenarios the deterministic pipeline (`crop_score`, `full_repo` weight
set) runs with ablations and weight sensitivities; the canonical `full_repo` top-5 is the
**C3 reference**. It lives under `eval/runs/archive_v2/deterministic/<sid>.json`, with the
matching risk/evidence bundles under `eval/runs/archive_v2/evidence/<sid>.json`.

### B.5 Weather cache (no per-scenario network)

*File:* `eval/weather_cache.py`. Scenario weather is sliced locally so no scenario makes a
live call and every scenario is reproducible.

* `district_points()` computes a point per district from
  `data/processed/mp_districts.geojson` (`NAME_2` + `representative_point`).
* For each district, **one** Open-Meteo archive request covers `FETCH_START` …
  `FETCH_END` (a wide window so both the climate normals window and the SPI window are
  inside it), daily `temperature_2m_mean/max/min` and `precipitation_sum`.
* Responses are cached to `eval/cache/weather/<district>.json`.
* `load_all()` loops districts with a **5 s sleep** between requests (Open-Meteo free-tier
  rate limit) and logs (but continues past) per-district failures.
* `as_date_map()` converts the Open-Meteo daily arrays into
  `{ISO date: {tmean, tmax, tmin, precip}}`.
* `slice_window(date_map, as_of, past_days, forecast_days)` returns ordered windows:
  `past` = `as_of−past_days … as_of−1`, `future` = `as_of … as_of+forecast_days−1`.

The archive is **reanalysis**, so the "forecast" window is observed values (a **hindcast**),
as stated throughout the report.

---

## PART C: Running, scoring and statistics

### C.1 The run harness (`eval/scripts/run_model.py`)

* Fixed run dir per model: `eval/runs/eval_<short>[suffix]/`; `results.json` is rewritten
  **atomically** after every completed call, so a killed process loses at most one
  in-flight call and is fully resumable.
* `--scenarios N` / `--scenario-start K` select a contiguous slice of the 500-subset;
  `--scenario-ids` selects an explicit pilot set; `--repeat R` repeats; `--workers W`
  parallelises; `--max-seconds` stops gracefully.
* `--conditions C0,C0b,C1a,C1b,C2a,C2b` selects conditions (default: all Phase-8-STEP-B).
* `--pilot-dev` tags records `pilot_dev=true`, writes `pilot_dev_scenarios.json`, and routes
  output to an isolated `eval_<short>_pilot_dev/` run dir.
* `--tool-transport {inprocess,mcp}` picks how C2 tool calls run (evidence unchanged).
* `--run-suffix` isolates a run's dir and cache namespace.
* The per-prompt **cache** (`eval/cache/llm/<short>[_mcp]/<sha256>.json`) keys on
  `model ⧫ condition ⧫ prompt ⧫ scenario_id ⧫ repeat`; cached non-error records are reused.
* A 15-second **heartbeat** prints done/ok/err/active counts.

For each planned `(scenario, condition, repeat)` the runner builds the prompt, runs the
provider (with the appropriate cap), records:
`model, model_short, condition, scenario_id, repeat, parsed{top5, valid_json, …},
tokens_in/out, reasoning_tokens, latency_s, tool_calls, tool_log,
finish_reason, truncated, unknown_tool_calls, forced_final, forced_final_reason, error`.

### B.6a Scoring: from text to `sv`/`hv`

**Parsing** (`eval/llm/prompts.py:parse_output`). Strip code fences, search for a `{...}`
block, and JSON-parse it. Accept `top5` / `Top5` / `crops` (list or single string).
`valid_json = True` iff a JSON object was parsed. The canonical crop list is the 21-crop
registry, and every predicted name is alias-normalised to it (`normalize_crop`; see
`ALIASES` for Hindi/English variants such as `dhan→Rice`, `gehu→Wheat`, `kapas→Cotton`).
Names not in the registry are recorded as `out_of_registry` (the "hallucination" signal)
and dropped from the scored top-5.

**Analysis frames** (`eval/scripts/n500_primary_metrics.py:usable/val`):

* **Per-protocol (PP):** only runs that are **valid, untruncated JSON** with a non-empty
  top-5 are scored.
* **Intention-to-treat (ITT):** *all* planned runs are scored; an invalid/truncated/empty
  output is counted as `sv = 0` and `hv = 1` (worst case), so a model cannot "win" by
  failing to answer.

**Season-validity rate (`sv`)**, fraction of the top-5 crops valid for the scenario's
season, judged against `eval/data/ground_truth/crop_season_table_v1.1.csv`
(`crop, season, sowing_window, harvest_window, status, source_ref, notes`; status is
`cited` or `unverified`):

* `cited` row for (crop, season) → **valid**;
* crop has rows but not for this season, or only `unverified` rows → **unknown**;
* crop absent from the table → **unknown**.
* **STRICT:** `unknown` counts in the denominator (a penalty). **LENIENT:** `unknown` is
  excluded from the denominator.

**Hard-violation rate (`hv`)**, fraction of the top-5 tripping a hard constraint
(`eval/data/ground_truth/hard_constraints_v1.1.csv`:
`constraint_type, crop, condition, severity, status, source_ref, note`):

* For each crop, gather the relevant constraints: its `season` constraint for the
  scenario's season; its `drought` constraints **if** the drought flag is set; its `flood`
  constraints **if** the flood flag is set.
* A **`cited`** hit → violation.
* An `unknown_only` (only `unverified` rows) hit → **violation under STRICT**, **removed
  from the denominator under LENIENT**.
* Flags come from the evidence bundle: **drought** = `drought_z_score_30d ≤ −1.5`;
  **flood** = `flood_probability ≥ 0.40`.

Examples of the constraint content: season hard constraints for Wheat (Kharif/Zaid),
Soybean (Rabi/Zaid), Rice (Zaid), Cotton (Rabi/Zaid), Gram, Mustard, Lentil, Barley, Bajra,
Sesame, Pea, Kodo-Kutki, Watermelon, all `cited`; plus `unverified` drought constraints
for Rice and Sugarcane, and `unverified` flood constraints for Moong, Sesame, Groundnut and
Watermelon.

**Ground-truth tables (v1.1).** The season table flags a handful of rows `unverified`
(e.g. Rabi Rice, Rabi Maize, Rabi Jowar, Rabi Arhar, Zaid Groundnut). v1.1 is the cited
version used for the headline; a v1 predecessor exists but is superseded.

**Pre-registered family & claim rule.** The primary family is the four contrasts
**C2a−C0b, C2a−C1a, C2b−C0b, C2b−C1a** (Holm-corrected within the family). A difference is
**claimable** only if it holds with the **same sign and significance under STRICT and
LENIENT and under PP and ITT** (a 2×2×2 robustness gate).

### B.6b Deterministic-reference diagnostics

For C3 the top-5 comes from `archive_v2/deterministic/<sid>.json`
(`ablations.full_repo.top5`). **Fidelity** to C3 is top-5 Jaccard (and top-1 agreement);
diagnostic only, since C3 is the repo's own system, not external truth. The C2a-vs-C3
**match/beat/lose** counts come from the clustered-inference script's text output and feed
Fig_N07.

### B.7 Statistics

*File:* `eval/statistics.py`.

* **Bootstrap 95% CIs**, 10,000 resamples, fixed `seed=42`, percentile method
  (`bootstrap_ci`); a ratio variant (`bootstrap_ci_ratio`) for pooled rates.
* **Wilcoxon** signed-rank (two-sided, `zero_method="zsplit"`) for paired continuous
  metrics; **McNemar** (continuity-corrected) for paired binary outcomes.
* **Holm–Bonferroni** correction over the pre-registered family (`holm_bonferroni`).
* **Effect sizes** Cliff's δ (rank-based) and Cohen's d (paired: `mean_diff / std_diff`),
  with the interpretation bands printed by `format_effect_size`.
* **Stratified** bootstrap by season; per-condition comparison via `compare_conditions`.

### B.8 The clustering correction

*File:* `eval/scripts/n500_clustered_inference.py`.

Scenarios are **clustered within district** (51 districts, mean ≈ 9.8 scenarios each), and
because `crop_score` ranks from district-determined soil and season, scenarios in the same
district yield similar recommendations → **scenario-level CIs are anti-conservative**.

The script re-does all inference by **resampling districts, not scenarios**:

* **ICC** per condition (variance between districts ÷ total variance) for `sv` and `hv`;
* **design effect** `DEFF = 1 + (m̄ − 1)·ICC` (m̄ = mean cluster size) and **effective
  sample size** `ESS = n / DEFF`;
* a **district-clustered bootstrap** for the four pre-registered contrasts (plus per-season
  and per-half), using a **centered** bootstrap for the p-value, then Holm.

**Point estimates are unchanged**; only the intervals widen. Redoing everything
cluster-aware changes **0 of 16 claimability cells**; every pre-registered conclusion
holds. Key numbers: `sv` ICC **0.166** for C2a (DEFF 2.47, ESS ≈ 203) and 0.084 for C2b;
`hv` ICC **0.241** for C2a (DEFF 3.12, ESS ≈ 160) and 0.070 for C2b. Only the tool-using
conditions cluster strongly (C0/C0b/C1a ≈ 0). The C2b−C0b district effect mean **+0.123**,
between-district SD **0.134**.

### B.9 Cross-model

`PRIMARY = nvidia/nemotron-3-ultra-550b-a55b` (n=500, headline);
`SMALL = meta/llama-3.2-11b-vision-instruct` (n=150); `z-ai/glm-5.3` **dropped** (partial
n=32, degraded endpoint). Cross-model comparisons are reported at the **common n=150**, not
500. The provider is NVIDIA NIM (OpenAI-compatible) with multi-key round-robin,
`temperature=0.2`, `max_output_tokens=4096`.

---

## PART C (cont.): Reproducing a run

```powershell
# 1. Generate scenarios + subset (offline)
python -u eval/scenarios.py

# 2. (Optional) fetch/refresh the per-district weather archive cache (one live call/district)
python -c "from eval.weather_cache import load_all; load_all()"

# 3. Run the primary model - resumable; B1 then B2
$env:NVIDIA_REQUEST_TIMEOUT="600"
python -u eval/scripts/run_model.py --model nvidia/nemotron-3-ultra-550b-a55b --scenarios 150 --workers 4
python -u eval/scripts/run_model.py --model nvidia/nemotron-3-ultra-550b-a55b --scenario-start 150 --scenarios 350 --workers 4

# 4. Score + cluster + figures
python -u eval/scripts/n500_primary_metrics.py
python -u eval/scripts/n500_clustered_inference.py
python -u eval/scripts/n500_figures.py
```

`run_model.py` prints the exact resume instruction if it stops on the UTC budget or
`--max-seconds`.

---

*See also:* `TOOLS_REFERENCE.md` (tool internals), `SYSTEM_GUIDE.md` (runtime product),
`FIGURES_EXPLAINED.md` (figure semantics).
