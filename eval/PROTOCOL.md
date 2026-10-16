# PROTOCOL.md — Frozen evaluation protocol

Paper: *Domain-Adaptive LLM with Model Context Protocol (MCP) for Intelligent Decision
Support in Precision Agriculture* (crop recommendation, Madhya Pradesh, India).

Protocol version **1.0.0**. The machine-readable form is `eval/config.yaml`; the
**SHA256 of that file is stamped into every results artefact** so a table/figure can be
traced to the exact configuration that produced it. Nothing in this protocol may be
changed after results are seen to favour one condition. Any change ⇒ new `run_id`.

> **Integrity rule.** Baselines that win are reported as wins. No prompt, weight,
> threshold, or scenario filtering is tuned after inspecting results.

---

## 1. Research question

Does giving a general-purpose LLM access to the six AgroLLaMA MCP tools (weather,
climate normals, season, risk, soil, deterministic crop score) improve the **quality,
safety, specificity, reliability, consistency and cost** of district-level crop
recommendations versus an LLM alone — and how does it compare to the deterministic
no-LLM system?

## 2. LLM Provider

All benchmark LLM calls go through **NVIDIA NIM free endpoints** (OpenAI-compatible
chat completions with tools). Provider config:
- base_url: `https://integrate.api.nvidia.com/v1`
- api_key_env: `NVIDIA_API_KEY` (read from environment, never logged or committed)
- temperature: 0.2, top_p: 1.0, max_output_tokens: 512
- Other providers (Gemini, Kilo Gateway, Opencode) are retained in code but **NOT used** in this evaluation.

## 3. Model Selection Rule (FROZEN before any benchmark run)

The following rule is applied to ALL candidate models returned by `GET /v1/models`:

1. **Callable**: model returns HTTP 200 on a minimal chat completion request.
2. **Tool-calling supported**: model returns valid tool calls on a structured request with 6 AgroLLaMA tools.
3. **Reliability thresholds** (measured over 20 scenario-like smoke test requests: 10 plain JSON, 10 with tools):
   - tool-call success rate ≥ 80%
   - invalid-JSON rate ≤ 10%
   - truncation rate ≤ 5%
4. **Performance**: median latency < 20 s (to keep full runs feasible).

Models failing any threshold are **rejected** and documented with the exact reason.

From the passing models, select **three models from different families**:
- **PRIMARY**: the largest model (by parameter count if stated, else by name ordering) that passes all thresholds.
- **SECOND_FAMILY**: the best passing model from a different model family (e.g., DeepSeek, Moonshot/Kimi, Qwen, Llama).
- **SMALL**: the fastest passing model (to test whether tools help weaker models most).

All rejected models and reasons are documented in `eval/models/MODELS.md`.

## 4. Conditions (all LLM conditions use the **same** model + temperature)

| ID | Name | Tools | Prompt |
|---|---|---|---|
| **C0** | LLM-only | none | short plain prompt: district name, lat/lon, as-of date |
| **C0b** | LLM-only, strong prompt | none | explicitly told to reason about soil, season, rainfall, temperature, drought/heat/flood risk ("best fair baseline") |
| **C1** | LLM + context stuffing | our code fetches tool outputs, pastes them into the prompt | no function calling |
| **C2** | LLM + MCP (proposed) | LLM calls the six tools via NVIDIA function calling | function calling; parallel tool calls encouraged |
| **C3** | No-LLM | deterministic tools + weighted scorer only | rules on all 10,000 scenarios |

- Every LLM condition returns compact JSON
  `{"top5": [<crop names>], "explanation": "<=60 words"}`.
- Crop names normalised with an alias map (`paddy→rice`, `bengal gram→gram`, …). Names
  not in the registry are recorded as `out_of_registry`.
- Model name: `config.model.name` (resolved from `models.list()`; **not assumed**).
  Temperature `0.2`, `top_p` 1.0, `max_output_tokens` 512, no chain-of-thought text.
- **Fallback disclosure:** C2 calls the tool functions directly through the NVIDIA client
  (not a separate MCP server). The report states this. The tool bodies are never modified.

## 5. Scenarios (`eval/data/scenarios.jsonl`)

- **10,000** scenarios = `(district, point-inside-polygon, as-of date)`.
- Stratified by **district** (all available polygons), **season**
  (Kharif/Rabi/Zaid), and **agro-climatic zone**.
- Dates: **2024-01-01 … 2025-12-31** (uniform over days).
- Point-in-polygon: points are sampled inside the real GADM level-2 polygon
  (rejection sampling / representative point + interior jitter), so 100 % are inside MP.
- **Reproducible weather:** one **Open-Meteo archive** request per district for the full
  2024–2025 range, cached to disk; each scenario's `past_days=30` and `forecast_days=7`
  windows are **sliced locally**. No per-scenario weather call.
- **Hindcast disclosure:** the archive is reanalysis, so "next 7 days" are **observed**
  values, not forecasts. Reported explicitly everywhere results are interpreted.

### 5.1 Stress set (`eval/data/stress.jsonl`, ≥ 1,000)

Objective rule applied to **deterministic tool outputs only**, fixed before any LLM run.
A scenario is *stress* if **any** of:

- `drought_z_score_30d <= -1.5`, or
- `max consecutive days >= 35 °C` in the 7-day window `>= 3`, or
- `flood_probability >= 0.40`.

### 5.2 LLM subset (`eval/data/llm_subset.jsonl`, default 500)

Stratified sample of the 10k across district/season/zone, **always including ≥ 150
stress-set scenarios** (ascertainment-controlled). Used for all LLM conditions to bound
API cost.

## 6. Ground truth (`eval/data/ground_truth/`)

The paper's original ground truth ("top 5 crops per region") is undefined and circular.
Replaced with two labelled layers:

- **(a) External GT** — independent district×season major crops / area from public
  sources (ICAR-CRIDA District Agriculture Contingency Plans, State Agriculture Dept /
  data.gov.in). Auto-download where possible; otherwise the author places files in
  `eval/data/ground_truth/` (exact file list requested in the run log). Quality metrics
  are reported here and labelled **external**.
- **(b) Hard-constraint table** — agronomic season-validity and infeasible crop/condition
  pairs, each row carrying a citation. Drives violation metrics.
- **(c) `eval/expert_rating_template.csv`** — blinded, shuffled outputs from all
  conditions for later 1–5 agronomist ratings.

Any metric derived from `crop_log.csv` (the repo registry) is labelled
**internal / potentially circular** and never used as the headline quality metric.

## 7. Metrics (per scenario → aggregate)

- **Quality** vs external & internal GT: Accuracy@5, Precision@5, Recall@5, nDCG@5, MRR.
- **Safety**: season-validity rate; hard-violation rate; stress-set violation rate;
  water-intensive-crop-under-drought rate.
- **Specificity**: distinct crops across districts; Shannon entropy of recommended
  crops; per-district differentiation (are all districts given "rice, wheat"?).
- **Reliability**: hallucination / out-of-registry rate; numeric faithfulness of
  explanation numbers vs tool outputs; tool-call success rate; invalid-JSON rate.
- **Consistency** (100 scenarios × 3 repeats): top-5 Jaccard, Kendall τ, exact-match.
- **Efficiency**: latency, input/output tokens, tool-call count, requests/scenario.
- Secondary only, labelled **"internal consistency scores (circular by construction)"**:
  the paper's Agro-Climate Score and Explainability Score.

Exact formulas are in `eval/metrics.py` and reproduced in the report (§3).

## 8. Statistics

- **Bootstrap 95 % CIs** (10,000 resamples, seed from config) for every aggregate; report
  **mean ± CI** and **n per cell**, never bare means.
- **Paired per-scenario tests** between conditions: Wilcoxon signed-rank (continuous),
  McNemar (binary); **Holm–Bonferroni** correction across the condition-pair family.
- **Effect sizes**: Cliff's δ (non-parametric) and Cohen's d (where meaningful).
- **Stratified** by season, agro-climatic zone, and risk level.
- **Model × condition interaction test**: bootstrap-based interaction test to check if
  tool benefit differs across selected models.

## 9. Cost control

- Disk cache (SQLite) keyed by `hash(model + prompt + tools + scenario + repeat)`;
  successful calls never repeated.
- Checkpoint after every call; the runner resumes with the same command after a crash or
  quota stop.
- Global rate limiter, max concurrency (default 2), exponential backoff + jitter on
  429/5xx, daily request budget (stop cleanly, print resume instructions).
- Compact tool JSON, short system prompts, capped output tokens.
- **DRY-RUN** counts requests/tokens a run would need.
- **PILOT**: 30 scenarios × all conditions → prints projected total requests, tokens and
  wall-clock for the full LLM run, then **stops for author confirmation**.

## 10. Figures & outputs

- 17+ numbered figures (`Fig_E01…`), PNG@300 dpi + PDF, colour-blind-safe palette,
  each with title, axis units, legend, and n.
- **Cross-model figures** (`Fig_M01…M10`) with model names in legends/footers:
  - Fig_M01: grouped bars of headline metrics, model × condition, with 95% bootstrap CIs.
  - Fig_M02: heatmap of Accuracy@5 and season-validity, rows = models, columns = conditions.
  - Fig_M03: "tool benefit" per model = (C2 - C0) and (C2 - C1) with CIs.
  - Fig_M04: tool-calling reliability per model (success, invalid JSON, truncation, retries).
  - Fig_M05: latency / tokens / requests per scenario by model and condition, cost-vs-quality scatter.
  - Fig_M06: consistency (Jaccard, Kendall tau) per model and condition.
  - Fig_M07: crop-frequency heatmaps per model.
  - Fig_M08: agreement between models (top-5 Jaccard) per condition.
  - Fig_M09: model-size vs tool benefit scatter.
  - Fig_M10: model selection summary: smoke-test latency vs tool-call success for ALL candidates.
- Every aggregate exported as CSV and LaTeX in `eval/results/`.
- Report: `eval/report/RESULTS_REPORT.md` + `.docx`, 12 sections incl. a claims audit and
  ready-to-paste replacement text.

## 11. Reproducibility

- `Makefile` targets: `audit, scenarios, deterministic, pilot, llm-run, analyze, figures,
  report`. All resumable.
- Every results file embeds: `run_id`, `protocol_version`, `config_sha256`, `git_commit`,
  `model_name_used`, `timestamp`, `provider`, `model_short_name`, `condition`.
- Seeds fixed in `config.yaml`.

## 12. Known limitations declared up front

Circularity of registry-based metrics; hindcast (not forecast) weather; free-tier NVIDIA
NIM endpoints (non-version-locked, may change or disappear); small paired subset for
comparison models; external ground-truth quality/coverage; open models only so no
commercial-model comparison; prompt sensitivity; tools are wall-clock by design and the
eval uses a read-only injection wrapper under `eval/` (the core tools are **not** modified).

---

# PHASE 8 — ADDENDUM (protocol version 2.0, timestamped below)

Adopted after the v1 results to fix the C2 harness, make baselines fair, and use
independent metrics. **Frozen** before any v2 results were recomputed; nothing below
is adjusted after seeing v2 numbers.

Frozen at: **2026-10-13** (local), recorded in git as the "Phase 8 addendum" commit.

## 8.1 Rules (Phase 8)

1. No API key is ever printed or written to disk/logs.
2. Raw results are never edited. v2 outputs are archived under
   `eval/runs/archive_v2/` and `eval/figures/archive_v2/`; v1 outputs stay in place
   (never deleted).
3. No cherry-picking: condition sets, prompts, weights, and GT tables are FROZEN here
   before v2 numbers are recomputed.
4. Season-validity and hard-constraint tables (§8.5) carry a cited source per row,
   are timestamped, and are never adjusted after results are computed.
5. Each STEP (A–F) reports results and then stops for author approval before any API
   call (STEP E runs, STEP D model choice).

## 8.2 Time anchoring (C2 fix)

- Before v2: `mcp_server/season_tool` and `crop_score_tool` read the LIVE clock
  (`datetime.now(IST)`) → "today's" season and `current_week` even when the scenario is
  dated 2024/2025; weather/climate/risk made LIVE API calls.
- v2: a read-only wrapper under `eval/` (`eval/time_anchored.py`) runs the REAL tool code
  with (a) `datetime` frozen to the scenario `as_of_date` (12:00 IST) and (b) Open-Meteo
  clients patched to answer from the per-district ARCHIVE cache (no live call, no
  look-ahead). `mcp_server/` code is unchanged.
- `max_tool_rounds = 15` (was 10). Exceeding rounds is its own error type
  (`max_rounds_reached`), distinct from `model_failure`.
- Per C2 call the LLM record stores: tool name, arguments, SHA256[:16] output hash,
  round number, tool+LLM latency, finish reason (`tool_log`).

## 8.3 Climate normals window — v1 vs v2 vs paper (exact dates)

| Version | Normals window (climate_tool) | SPI / drought reference | Look-ahead? |
|---|---|---|---|
| Paper & **v1** evidence | fixed **2014-01-01 .. 2023-12-31** for every scenario | live 2019..2023 archive | yes, for `as_of >= 2024` (normals include the whole decade; SPI truncated at fetch date) |
| **v2** evidence | all cached days **`2014-01-01 <= date < as_of_date`** | fixed **2019-01-01 .. 2023-12-31** | **no** |

- For `as_of = 2024-01-01` the v1 and v2 windows coincide. For `as_of` later in 2024 or
  in 2025, v2 is LONGER than v1: the full 2014–2023 decade PLUS the partial current year
  up to the day before `as_of` (e.g. `as_of=2025-06-21` → 2014-01-01..2025-06-20,
  11.5 years), i.e. v2 never contains data after the scenario date.
- Weather window (v2): 14 days `[as_of-7 .. as_of+6]`, past first. Risk window: 37 days
  `[as_of-30 .. as_of+6]`. Both sliced from the cache; the "forecast" 7 days are
  observed hindcast values (as declared in §5).
- Recorded drift (informational, computed 2026-10-13):
  - ranking (crop_score 6) changed **v1→v2 in 1,295 / 10,000 (12.9%)** subset-verified and
    verified over the full 10k; subset 64/500 (12.8%).
  - deterministic C3 `full_repo` top-5 changed **v1→v2 in 1,502 / 10,000 (15.0%)**
    (normals change plus week anchored to `as_of`).
  - v2 10k C3 summary: season validity **overall 0.7479** (stress 0.5477, normal 0.8936);
    per season Kharif 0.9894 / Rabi 0.9865 / **Zaid 0.2639**. Distinct crops 21,
    Shannon entropy 4.029, district differentiation 0.180. v1 archived → `eval/runs/archive_v2/previous_v1/`.

Why the ranking changed: `crop_score` rainfall match (weight 0.20) uses the seasonal
rainfall estimate from monthly rainfall normals, which shift when the current year
(partial) enters the window; soil/temp/season components are unchanged or only weakly
shifted. Five examples (v1 top6 → v2 top6):

| scenario | district | as_of | v1 top6 | v2 top6 |
|---|---|---|---|---|
| S000480 | Anuppur | 2024-07-08 | Sunflower, Arhar, Sesame, Moong, Groundnut, Urad | Sunflower, Arhar, Sesame, Moong, **Urad, Groundnut** (swap 5↔6) |
| S001465 | Bhind | 2024-10-18 | Bajra, Jowar, Watermelon, Sesame, Moong, Mustard | Bajra, Jowar, **Mustard**, Sesame, Moong, Watermelon |
| S001654 | Bhopal | 2025-08-27 | Kodo-Kutki, Arhar, Sunflower, Moong, Rice, Sesame | **Moong**, Kodo-Kutki, Sunflower, Arhar, Rice, Sesame |
| S001681 | Bhopal | 2024-09-12 | Arhar, Sunflower, Moong, Sesame, Rice, Soybean | Arhar, **Moong**, Sunflower, Sesame, Rice, Soybean |
| S001690 | Bhopal | 2025-06-19 | Sunflower, Moong, Arhar, Kodo-Kutki, Sesame, Soybean | **Moong**, Sunflower, Kodo-Kutki, Arhar, Sesame, Soybean |

## 8.4 Condition set (STEP B) — FROZEN

All conditions share model + temperature; crop output contract unchanged.

| ID | Name | Tool set | Prompt contents |
|---|---|---|---|
| **C0** | LLM-only | none | unchanged (plain: district, coords, date) |
| **C0b** | LLM-only strong | none | unchanged (soil/season/rainfall/temp/risk told to consider) |
| **C1a** | Fair stuffing | context pasted, **no function calling** | WEATHER + CLIMATE_NORMALS + SEASON + SOIL + RISK (the raw evidence the tools return) + **CANDIDATE_CROP_REQUIREMENTS** (registry requirements: rainfall/temp range, soil type, season_supported, sowing weeks, days-to-harvest, peak-water week, risk_sensitivity). **NO crop_score, NO ranking, NO suitability scores, NO per-crop match flags.** |
| **C1b** | Oracle (relabelled C1) | context pasted, no function calling | IDENTICAL to v1 `C1` (full `CROP_SCORE` ranking injected). **Upper bound, leaks the answer. Never headline as fair.** `prompt_c1b()` calls `prompt_c1()`. |
| **C2a** | Tools, full set | **six** tools: weather, climate, season, risk, soil, **crop_score** | same "call ALL six" instruction as v1 C2 |
| **C2b** | Tools, no scorer | **five** tools: weather, climate, season, risk, soil | "call ALL five, do NOT call any other tool"; crop_score not exposed or servable |
| **C3** | No-LLM | deterministic + weighted scorer | unchanged reference; v2 run re-scored time-anchored (§8.3) |

- Old v1 labels are retained where applicable: v1 `C1` == v1`C1b` (oracle); there is NO
  "fair stuff" in the v1 set.
- Tool schemas: identical names/descriptions/parameters to the live MCP server for the
  six tools (see `NvidiaProvider._build_tools`); v2 execution via `ToolRuntime`
  (time-anchored, offline).
- Consistency runs use 100 scenarios × 3 repeats of C0b, C1a, C2a (STEP E).

## 8.5 Independent metrics (STEP C) — FROZEN before v2 recompute

- Sourced **crop-season table** → `eval/data/ground_truth/crop_season_table.csv`
  (one row per crop × season, cited source per row; unsourced rows marked `UNVERIFIED`
  and listed for agronomist check). Timestamped at creation; recomputes C3 season
  validity per season (incl. Zaid) under this table.
- **Hard-constraint table** → `eval/data/ground_truth/hard_constraints.csv`
  (infeasible crop/condition pairs, cited); drives hard-violation rates.
- **External GT attempt** → district×season crop stats (ICAR-CRIDA contingency plans,
  data.gov.in, MP agriculture statistics); if unobtainable, exact URLs + expected file
  names are recorded for the author to place in `eval/data/ground_truth/`.
- **Expert template** → `eval/data/ground_truth/expert_rating_template.csv`
  (200 blinded, shuffled outputs, all conditions × models, stratified by season & stress,
  blank 1–5 rating column).
- **Renaming**: `Accuracy@5 vs C3` and `Jaccard vs C3` are renamed **"Fidelity to C3"**
  everywhere; tool-use and consistency are process measures and must NOT appear as
  headline results.
- Registry-derived (`crop_log.csv`) metrics remain labelled internal/circular (§6) and
  are never the headline quality metric.

**STEP C artefacts (created & frozen 2026-10-13, before any STEP F recompute):**
- `eval/data/ground_truth/crop_season_table.csv` — 21 crops × season, cited/UNVERIFIED,
  per-row source (SLBC-MP crop-season PDF, evikas MP, DPD Summer Pulses, TNAU agritech,
  ICAR-CRIDA, technicalkisan, iaspoint; see `GT_SOURCES.md` for URLs).
- `eval/data/ground_truth/hard_constraints.csv` — infeasible crop/condition pairs
  (season + drought + flood type), cited or UNVERIFIED.
- `eval/data/ground_truth/expert_rating_template.csv` — 200 scenarios stratified by
  season×stress; 1,526 rows; C3 + reused C0/C0b filled, C1a/C1b/C2a/C2b = PENDING
  (filled by re-running `build_expert_template.py` after STEP F; non-destructive).
- `eval/results/c3_season_validity_cited.json` — C3 season validity + hard-violation
  recomputed from the CITED rows on the SAME v2 deterministic outputs:
  overall **0.7695** (registry 0.7479), stress 0.6785 / normal 0.8358; per season
  Kharif 0.9894, Rabi **0.7865**, Zaid **0.5293**; hard-violation rate **0.0814**
  (cited) / 0.1146 (all rows).
- v1.1 (2026-10-13, review): `crop_season_table_v1.1.csv` + `hard_constraints_v1.1.csv`
  upgrade **Barley** rows to `cited` (IIWBR-EB53, KhetiVyapar-MP-Rabi, Indiastat-Barley-Rabi);
  `UNVERIFIED_FOR_REVIEW.csv` lists all 13 UNVERIFIED rows; `CHANGELOG.md` documents the
  version bump; `c3_season_validity_cited_v2.json` reports STRICT/LENIENT × v1/v1.1
  (see table above).
- **Finding reported to author (CORRECTED 2026-10-13):** the deterministic C3 Rabi
  recommendation places **Barley inside the top-5 in every one of the 3,319 Rabi
  scenarios** (100% presence: position 1 in 163, 2 in 885, 3 in 685, 4 in 673, 5 in 913).
  Barley is #1 in only **4.9%** (163/3319); Rabi top-1 is Sunflower 44.6%, Pea 19.7%,
  Wheat 17.6%, Mustard 10.8%, Barley 4.9%, Gram 2.3%. The earlier summary "Barley-first
  in all Rabi" was a misstatement of top-5 membership.
- **Why Barley is always in Rabi top-5 (diagnosis, `eval/scripts/analyze_barley_problem.py`, no scorer changes):**
  the rainfall term is effectively dead in Rabi — the seasonal rainfall estimate for
  Rabi months (Nov–Mar normals, typically ≲150 mm) is far below every crop band
  (500–1600 mm), so `rainfall_match=0` for ALL crops; the 0.20·rain channel never
  discriminates. Rabi ranks therefore collapse onto temp (0.15), soil (0.20), season
  (0.30), risk (0.15). Barley's band 12–32 °C, window wk43–47 and **Drought: Low**
  (weakest Rabi risk profile) keep it at or near the top everywhere, while its soil
  string "Medium red and medium black" (mixed red+black) ties it at 0.8 soil vs Wheat/
  Gram 1.0 — why it stays #2–#5 in most cases. **Limitation:** bands are annual not
  season-sliced (800–1400 mm "Rainfall" for barley is an annual figure), so
  rainfall_match cannot rank Rabi crops; margins when Barley IS #1 are tiny
  (median 0.004, 60% < 0.01), i.e. near-ties, and the seed-for-ranks is week/season
  only. Regarded as scorer limitation; **no weight/threshold changes made.**
- **UNVERIFIED vs cited (review item 1a, `c3_season_validity_cited_v2.json`):**
  Barley's Rabi row was UNVERIFIED. STRICT (UNVERIFIED counts invalid) and LENIENT
  (UNVERIFIED excluded from denominator) for v1 (frozen) and v1.1 (Barley now cited):

  | table | mode | season validity overall | stress | normal | Kharif | Rabi | Zaid | hard-viol |
  |---|---|---|---|---|---|---|---|---|
  | v1 | STRICT | 0.7695 | 0.6785 | 0.8358 | 0.9894 | 0.7865 | 0.5293 | 5732/50000 = 0.1146 |
  | v1 | LENIENT | 0.8350 | 0.7112 | 0.9250 | 0.9894 | 0.9837 | 0.5293 | 4071/48339 = 0.0842 |
  | v1.1 | STRICT | 0.8359 | 0.7122 | 0.9259 | 0.9894 | 0.9865 | 0.5293 | 5732/50000 = 0.1146 |
  | v1.1 | LENIENT | 0.8361 | 0.7126 | 0.9260 | 0.9894 | 0.9870 | 0.5293 | 4625/48893 = 0.0946 |

  Frozen v1 cross-checks PASS (strict_season == v1 cited season; strict_hard == v1
  all_rows hard; lenient violations == v1 cited violations). Headline C3 season
  validity: range **0.7695–0.8361**; Rabi range 0.7865 (v1 strict) – 0.9870 (v1.1
  lenient). Zaid 0.5293 is limiting across interpretations.
  Author decision needed: adopt v1.1 (Barley/Rabi cited; corroborated by IIWBR pocket
  guide EB-53, MP rabi 2024-25 sowing target incl. barley 36k ha, Indiastat "Barley
  (Rabi) in Madhya Pradesh") or keep conservative v1.
- **Renaming applied in code/report skeleton**: "Accuracy@5 vs C3" / "Jaccard vs C3"
  → **"Fidelity to C3"** (label + `Fig_M05` title; file renamed Fig_M05_fidelity_c3).

## 8.6 Soil coverage (STEP A point 4)

- All **51 scenario districts have soil matches** (`matched_count=51/51`). The only
  unmatched entry is the orphan soil record "**Niwari**" (a soil row with no GeoJSON
  polygon / no scenario). Scenarios containing "Niwari": **0/500 subset, 0/10 000, 0/4212
  stress**.
- If a district polygon EVER had no soil metadata, `soil_tool` returns empty fields plus
  `note: "District in MP but soil metadata not in database"` — it does NOT silently fall
  back to a default soil. Such a scenario would be flagged `soil_unavailable` and
  excluded/listed; none exist in the v2 evaluation.

## 8.7 Reuse / run policy (STEP E)

- **Only C0 and C0b are prompt-identical v1↔v2.** Their cached results MAY be reused.
- **No old C1 (oracle) or C2 outputs are reused**: C1/C2 prompts/evidence changed (v2
  normals); and the C2 harness was broken (live clock/API). C1b is re-planned ONLY on the
  nested 150-scenario subset, labelled supplementary.
- Reused + recomputed results are merged only in derived tables (`master_long.csv` etc.),
  never by editing raw outputs; `condition`, `tool_names`, per-request latency, and
  `error_type` are explicit columns.
- Any config.yaml change ⇒ new `run_id` + config SHA256 (see §11); v2 runs carry the
  STEP A config hash (incl. `max_tool_rounds`).

## 8.8 Model set (STEP D)

- GLM-5.3 (n=32, ~200–400 s/call, frequent 504s) cannot support comparisons. 
  **Author decision 2026-10-13: option (a) — GLM dropped.** Final model set for the v2
  comparative run is **PRIMARY = Nemotron-3-Ultra-550B** (500-scenario subset) and
  **SMALL = Llama-3.2-11B** (150-scenario subset). GLM cells are excluded from all
  comparison tables and figures; its 32-scenario v1 results remain under
  `eval/runs/eval_glm-5.3/` and are labelled preliminary/supplementary only.
- The full smoke-test table (13 candidates) lives in `eval/models/MODELS.md` (see STEP
  D report); all passing candidates from other families = Nemotron + Llama only.

## 8.9 Pre-registration (STEP D/E) — timestamped 2026-10-13 BEFORE any new API run

Written to protocol before the pilot/staged runs; no new API request has been made
after this timestamp (frozen at 2026-10-13, before ITEM 4 pilot approval).

**Primary metrics (headline):** hard-violation rate and season-validity rate,
**LENIENT** version (UNVERIFIED rows excluded from the denominator). **STRICT**
(UNVERIFIED = invalid) is a sensitivity analysis. A claim is stated only if it holds
under BOTH strict and lenient.

**Secondary metrics:** precision@5 / recall@5 / nDCG@5 (only if independent ground
truth exists), consistency (repeats 2–3 vs repeat 1), reliability (valid-JSON,
tool-call success, max_rounds_reached, invalid-JSON, truncation, tool failure, 429
rates), efficiency (per-request latency, tokens, cost). **"Fidelity to C3" is a
diagnostic only, never a headline.**

**Primary contrasts — one Holm family, per model, on the primary metrics:**
- C2a − C0b
- C2a − C1a
- C2b − C0b
- C2b − C1a

All other contrasts are labelled EXPLORATORY (including any C1a–C0b contrast, cross-model
contrasts outside the family, and all secondary-metric contrasts).

**Prompt freeze:** after the ITEM 4 pilot, prompts may be changed ONLY to fix bugs.
Every change is recorded (hash before/after, reason) and the pilot is restarted from
scratch if any prompt changes.

**Analysis rule:** because a headline hard-violation contrast cannot be computed on
deterministic C3 (no LLM), primary contrasts are LLM-condition contrasts only; C3 stays
a reference row. Zaid season-validity (0.5293) is a known scorer limitation (§8.5) and
is reported per-season, not collapsed into the headline without the per-season split.

**Reuse verification (ITEM 2, 2026-10-13):** old records carry NO config hash and
record temperature / max_output_tokens only implicitly. The claim that archived C0/C0b
runs used temperature=0.2 / max_output_tokens=4096 rests on `git diff eval/config.yaml`
(only comments + added tool-loop keys changed since STEP A; temp/max_tokens untouched).
`eval/results/reuse_report.json` lists every (model, condition, scenario) that is
reusable (prompt hash + model + temp + max_tokens all match, no error) vs re-run-required
(Nemotron C0b: 472 reusable / 28 re-run; Nemotron C0: 463 / 37; Llama C0b/C0: 150 / 0).

**Pilot records (ITEM 4, 2026-10-13):** pilot API calls are tagged `pilot_dev: true`,
written to `eval/runs/eval_<short>_pilot_dev/`, and the 20 scenario IDs go to
`eval/results/pilot_dev_scenarios.json`. If any prompt or harness change follows the
pilot, the pilot is restarted from scratch and the 20 scenarios are excluded from primary
analyses (or primary results are reported with and without them).

## 8.10 Harness-fix deviation (STEP E decision 2026-10-13) — BEFORE pilot v2

**Timestamp:** recorded after ITEM 4 pilot v1 revealed (a) Llama 30% `max_rounds_reached`
(stalled calling hallucinated tools `top5`/`top5_crops`/`top_crops`) and (b) Nemotron C2b
9/20 + C1a 2/20 `finish=length` truncation at the 4096 completion cap (the final tool-run
response uses `max_output_tokens_tools`=2048, lower than the non-tool cap).

**Reason (user decision, pilot v1):** keep both models, no model swap, no round-limit raise.
Fix the harness so every run can converge to a final JSON, and make the fallback itself a
reported reliability metric.

**a. Unknown tool calls.** Any call to a tool name outside the condition's tool set returns
a tool error naming the valid tools plus: *"Do not call a tool for the final answer; reply
with the JSON object now."* Counted per scenario as `unknown_tool_calls`; each tool-log
entry records `unknown_tool: true`.

**b. Stall fallback.** After TWO CONSECUTIVE unknown-tool calls (any orders, within or
across model responses), or at tool-loop round 12 (0-indexed), the harness makes ONE LAST
request with tools disabled and the instruction *"Provide the final JSON using the evidence
gathered"*. Records `forced_final: true` with reason `consecutive_unknown` or `round12`.
`max_tool_rounds` stays 15. Raw stall rate (pre-fallback trigger rate per model/condition)
is reported SEPARATELY from final validity.

**c. Prompt-line addition (tool conditions only).** `FINAL_JSON_ONLY` = "Reply with the
final JSON object only; no analysis or explanation text outside the JSON." appended to
`prompt_c1a`, `prompt_c1` (C1b/C1), and `prompt_c2` (C2a/C2b). C0/C0b prompts UNCHANGED;
verified identical (reuse_report.json re-run 2026-10-13: C0/C0b hashes/fresh-sets unchanged,
Nemotron 472/463 reusable, Llama 150/0; not one extra re-run required).

**d. Disclosed asymmetry in config (2026-10-13).** `max_output_tokens_tools` 2048 -> 8192
applies to ALL tool-condition prompts (C1a/C1b/C2a/C2b), including the tool-LESS
conditions C1a/C1b that carry no tools in the payload. Amendment (2026-10-13): the cap
is passed explicitly by `run_model.py` (`max_output_tokens=` per condition) because the
provider otherwise chose the non-tool 4096 cap for C0/C0b-STYLE no-tool requests
(`nvidia_provider.py:466`); without the override C1a truncated at 4096 (4/20 in pilot
v2). C0/C0b stay at `max_output_tokens`=4096. This is a deliberate, disclosed asymmetry:
tool-condition outputs may be longer (they reason over 5-6 tool outputs); it does not
relax C0/C0b, whose cached records remain reusable. Temperature/top_p/max_output_tokens
unchanged.

**e. Per-response metrics (every condition):** `valid_json`, `truncated`
(finish_reason=="length"), `forced_final`, `unknown_tool_calls`, `max_rounds_reached`,
plus existing valid_json/tool-call success/finish_reason/latency/tokens.

**Two analysis definitions (decided now, before data):**
- **Per-protocol:** primary metrics computed EXCLUDING responses with invalid/truncated JSON
  (valid responses only). Analysed n reported.
- **Intention-to-treat (ITT, sensitivity):** ALL planned scenario-runs enter; any response
  with invalid or truncated JSON counts as FAILING, defined as season-validity=0 and
  hard-violation=1 in that condition cell.
A claim is stated only if it holds under BOTH per-protocol and ITT.

**Pilot v2 (2026-10-13):** 20 NEW scenarios from `llm_subset` (excludes pilot v1 sids;
Kharif 7 / Rabi 7 / Zaid 6), tagged `pilot_dev=true` (see `pilot_v2_scenarios.json`).
Conditions: Nemotron C1a/C2a/C2b (60 scenario-runs); Llama C2a/C2b (40 scenario-runs).
Abort rules: (a) any season-tool output != scenario season; (b) any live clock/network
call; (c) any C2b crop_score call; (e) 429 rate >10%; (f) NEMOTRON ONLY: valid-JSON <90%
or `forced_final` >10% in ANY tool condition. For Llama, stalls/forced_final are RESULTS,
not aborts. First attempt FAILED rule (f) (Nemotron C1a 16/20 valid, 4 `length` at 4096);
root cause fixed by the d-amendment (explicit cap text above) and the affected C1a runs
were re-run at 8192: 20/20 valid, 0 truncated. Pilot v2 stands as the post-amendment run.

**Pilot v1 records retained:** `eval/runs/eval_{nemotron-3-ultra,llama-3.2-11b}_pilot_dev/`
(2026-10-13) are kept and used ONLY for an appendix table "pre-fix failure modes".

## 8.11 CONFIRMED primary-analysis pre-registration — timestamped 2026-10-13T15:42:30Z (UTC)

Confirmed verbatim (restates + consolidates §8.9/§8.10 e) at 2026-10-13T15:42:30Z (UTC)
[corrected 2026-10-13T20:59:22Z: the originally-recorded "2026-10-13T21:12:30Z" was the
local IST wall-clock time of that instant mislabelled as UTC; true UTC instant = 21:12:30
IST − 05:30 = 2026-10-13T15:42:30Z],
BEFORE computing ANY primary metric on collected data (incl. the completed Stage A
Llama run). This is the analysis contract for the Step E/F deliverables.

**Primary metrics (headline, decided before any primary runs):**
1. **Hard-violation rate** (share of scenarios whose output violates the hard-constraint
   table — e.g. off-season crop in the top-5 mix) — reported **LENIENT** (UNVERIFIED rows
   excluded from the denominator) as the headline with **STRICT** (UNVERIFIED = invalid)
   as a sensitivity analysis.
2. **Season-validity rate** (output's top-1 crop season matches the scenario season) —
   same LENIENT headline / STRICT sensitivity split.
A claim is stated only if it holds under BOTH strict and lenient.

**Primary contrasts — one Holm family, per model, on the primary metrics:**
- C2a − C0b
- C2a − C1a
- C2b − C0b
- C2b − C1a
Contrasts computed PAIRED within scenario on the shared scenario set; each primary
contrast is tested with the family-level **Holm–Bonferroni** correction (family = the
four contrasts above, per model, per primary metric). All other contrasts (C1a–C0b,
cross-model, C3 references, secondary-metric contrasts) are labelled EXPLORATORY.

**ITT vs per-protocol (locked at 2026-10-13T15:42:30Z UTC):**
- **Per-protocol:** primary metrics computed EXCLUDING responses with invalid/truncated
  JSON (valid responses only); analysed n reported.
- **ITT (sensitivity):** ALL planned scenario-runs enter; invalid or truncated JSON counts
  as season-validity = 0 and hard-violation = 1 in that condition cell.
A claim is stated only if it holds under BOTH per-protocol and ITT.

**Analytic decisions already frozen here:** C3 is a reference row (no LLM, no valid
hard-violation contrast); Zaid season-validity is a known scorer limitation (§8.5) and is
reported per-season, never collapsed into the headline without the per-season split;
"Fidelity to C3" remains a diagnostic only; reliability/consistency/efficiency are
secondary metrics and any of their contrasts are EXPLORATORY.

## 8.12 Budget-day boundary (recorded 2026-10-13T20:59:22Z UTC)

**Boundary: UTC calendar day (reset at 00:00:00 UTC).** Rationale: every artifact
timestamp in the repo is UTC (`generated_at` uses `+00:00`), NVIDIA NIM quota windows are
UTC-based, and the requirement "4000 HTTP/day" is documented as a daily reset. The
provider reads `cost_control.daily_request_budget: 4000` (`nvidia_provider.py:99`,
`kilo_provider.py:62`) but **does NOT enforce or reset it** — the counter in `status.py:145`
is an approximation (`progress["completed"]`), not a real day boundary. Therefore the
boundary above is a RECORDED MANUAL CONVENTION, not a code-enforced limit.
- Current day = 2026-10-13 UTC. Reported usage for this UTC day = **3,372 / 4,000 (84.3%)**;
  628 remain.
- Next reset instant = **2026-10-14T00:00:00Z = 2026-10-14T05:30:00 IST**. B1 (~2,100 HTTP)
  cannot fit in today's remaining 628 and must not start before the reset + user approval.

**AMENDMENT 2026-10-14: budget is now code-ENFORCED.** `eval/llm/budget.py` (`DailyBudget`)
persists a UTC-day counter to `eval/runs/_http_budget.json`; `NvidiaProvider.post()` calls
`reserve()` immediately before every HTTP attempt (retries included) and hard-stops with
`error_type="budget_exceeded"` when the next request would cross 4,000. `run_model.py` treats
that as a clean stop (nothing cached/recorded as an error) and prints a resume message; the
same command resumes after 00:00:00Z. `status.py` now prints the real counter, not the
`progress["completed"]` estimate. The counter was seeded once with the recorded 2026-10-13
usage (3,372), so today's ceiling is honoured. `kilo_provider.py` is NOT yet wired.

## 8.13 Stale-source audit — bundle `crop_score` vs frozen v2 grid (2026-10-13)

The `adhoc/evidence` bundles (`crop_score` tool output; no `_v`) are the STALE source still
read by `build_master_long.py`, `analyze_cross_model.py`, `diagnostics.py`,
`recompute_normalization_fix.py`. The authoritative C3 is the **frozen v2 grid**
`archive_v2/deterministic` (`full_repo` ablations, `_v=2`). Recorded corrections:
- Barley #1 in Rabi: stale bundle **303/3319 (9.1%)** → frozen grid **163/3319 (4.9%)**.
- Barley top-5 in Rabi: stale bundle **2914 (87.8%)** → frozen grid **3319 (100.0%)**.
- C3 top-1 agreement between the two sources: **8333/10000 (83.3%)**, 1667 differ; top-5 SET
  agreement 5929/10000.
- The earlier summary "Barley first in ALL 3,319 Rabi scenarios" is NOT reproduced by ANY
  archived source and is retracted; the closest true statement is Barley top-5 in 100% of Rabi
  on the frozen v2 grid.

## 8.14 Rabi rainfall channel limitation (recorded 2026-10-13, no weight changes)

In the frozen v2 evidence, `rainfall_match = 0.00` for **all 18 Rabi crops in all 3,319/3,319
Rabi scenarios** (0 scenarios with any non-zero). (10,000-scenario grid = Kharif 3366 + Rabi
3319 + Zaid 3315.) Consequence: **the 0.20 rainfall weight is inert in Rabi; Rabi rankings
are decided by the remaining 0.80 (temperature, soil, season, risk) with median top-1 margin
0.004.** Weights are NOT changed; this is recorded as a scorer limitation for Rabi.

## 8.15 One canonical source: repoint, writer collision, adhoc-reader audit (2026-10-14)

**Canonical sources.** C3 = `eval/runs/archive_v2/deterministic` (`ablations.full_repo.top5`,
`_v=2`). Evidence/risk flags = `eval/runs/archive_v2/evidence` (`_v=2`; adds `as_of_date`+`week`).
`eval/runs/adhoc/*` is v1 provenance only and must not feed analysis/figures/replay.

**Repointed readers** (were `adhoc/evidence` bundles; now archive_v2): `build_master_long.py`,
`analyze_cross_model.py`, `diagnostics.py`, `recompute_normalization_fix.py`,
`generate_figures.py` (grid), `finalize_stress_and_subset.py` (evidence),
`mcp_eval/server.py` default evidence dir (was unwired per DIAGNOSTICS), `_pre_pilot_season_check.py`,
and the `Makefile` `deterministic` target (now runs `analyze_deterministic_v2.py`).
Full disposition list: `eval/results/adhoc_reader_audit.json`. Intentional v1 referencers kept:
`build_evidence_v2.py` (migration input), `run_deterministic_v2.py` / `drift_v1_v2.py` (explicit
drift), the `_barley_*`/`_stale_source_audit.py` audit scripts, the `_diff_*` snapshot diffs.
Kept v1 **producers** (write `adhoc/*`): `build_stress_set.py`, `build_missing_evidence.py`,
`run_deterministic.py`, `run_deterministic_fast.py`, `complete_deterministic.py` (v2 successors:
`build_evidence_v2.py`, `run_deterministic_v2.py`).

**Writer collision fixed.** `c3_deterministic_summary.json` has a single canonical writer,
`analyze_deterministic_v2.py`. The two v1 writers (`analyze_deterministic.py`,
`analyze_deterministic_full.py`) were retired to `eval/scripts/archive_v1/` and now write
`c3_deterministic_summary.v1.json`, so an old script can never silently clobber the canonical.
`figure_stats.json` single writer = `eval/figures_paper.py` (was already unique; no collision).

**Grid equivalence + repoint effect.** `adhoc/deterministic` vs `archive_v2/deterministic`: all
10,000 files differ at the byte level ONLY because v2 adds two keys (`as_of_date`, `week`); every
common field is identical, BUT `full_repo.top5` differs in **1502/10000 (15.0%)** scenarios (e.g.
S000041 top-1 Wheat->Barley; S000048 slot Sesame (Til)->Kodo-Kutki). The true before/after of the
repoint (identical metric code, adhoc-sourced vs archive_v2-sourced) is small but real:
season-validity overall 0.74838 -> 0.74792 (-0.00046); stress 0.548338 -> 0.547673; normal 0.893953
-> 0.893642; Shannon 4.029756 -> 4.029017; per-district 0.181223 -> 0.179667; largest single move
`sens_risk_minus` 0.936833 -> 0.957795 (+0.0210). (See `eval/results/_det_source_before_after.json`
and `_grid_semantic_diff.json`.) The canonical summary was already v2-sourced, so the canonical
numbers are the "after" column; the repoint makes the other scripts agree with it.

**Superseded figures.** `Fig_E01-E06` (`generate_figures.py`; E01-E04,E06 values are HARDCODED
legacy `n=8,628`) are marked superseded by `eval/figures/paper/` (see `eval/figures/SUPERSEDED.md`);
kept, not deleted. Only E05 (crop frequency) is data-driven and it changed under the repoint.

## 8.16 Offline contrasts and diagnostics (2026-10-14, no API calls)

Outputs: `eval/results/offline_contrasts.{txt,json}`; reuses the stage-A metric/statistics
code (`stage_a_interim_metrics.py`) as the single source of truth.

**Item 5 - hard-violation contrasts (Llama, pre-registered pair family; Holm within family).**
STRICT | PP: C2a-C0b -0.247 [-0.291,-0.202] Holm 1.7e-14; C2a-C1a -0.260 Holm 4.4e-13; C2b-C0b
-0.046 (n=85) Holm 0.053 (n.s.); C2b-C1a -0.058 Holm 0.020. STRICT | ITT: C2a-C0b -0.131 Holm
2.9e-05; C2a-C1a -0.141 Holm 4.0e-05; C2b-C0b +0.210 Holm 2.7e-08; C2b-C1a +0.199 Holm 2.9e-07.
Same pattern LENIENT; WITHOUT-pilot similar (C2a-C0b -0.231 PP / -0.140 ITT). Interpretation: C2a
reduces hard-violation vs both baselines; C2b's apparent PP reduction disappears under ITT (its 65
non-PP scenarios count as violation=1), where C2b INCREASES hard-violation vs C0b/C1a.

**Item 6 - exploratory contrasts (Llama).** C1a-C0b is ~0 for both metrics (sv +0.003
[-0.015,+0.021], hv +0.011 [-0.012,+0.033]; both n.s.) => the fair evidence stuffing in the prompt
does nothing. C2a-C2b is large and significant (sv STRICT PP +0.459 Holm 2.5e-12, ITT +0.476;
hv STRICT PP -0.198 Holm 4.5e-06, ITT -0.341). EXPLORATORY.

**Item 7 - Fidelity to C3 (Llama C2a) - DIAGNOSTIC ONLY, never headline.** top-5 Jaccard vs C3:
0.685 (PP, n=148) / 0.676 (ITT, invalid=0). top-1 agreement vs C3: 0.787 (PP, n=127) / 0.667 (ITT).
Per-scenario C2a vs C3: STRICT PP season-validity match=90 beat=3 lose=34; hard-violation
match=95 beat=2 lose=30. So C2a mostly matches C3 and, when it differs, usually loses (C3 better).

**Item 8 - unknown-tool rate (Llama) = finding.** C2a 56/150 runs (37.3%), C2b 75/150 (50.0%);
forced_final runs C2a=3, C2b=9. Invented tool names: `top5_crops` 129, `top5` 2 (all recovered by
the stall fallback). C2b-C2a unknown-run rate = +0.127 [+0.013,+0.240] Cliff_d=+0.127 p=0.030
(paired, n=150): C2b stalls more, consistent with its lower validity.

## 8.17 B1 run - Nemotron C1a/C2a/C2b x150 (2026-10-14)

Ran after the UTC-day reset under the new code-enforced budget. Pre-launch: the run_model
file cache is keyed by (model, condition, prompt, sid, repeat) and the ss8.10 harness fix did
NOT change those keys, so B1 would have silently reused 120 pre-fix Nemotron records (40
pilot_dev scenarios x C1a/C2a/C2b; 2 C1a finish=length @4096; C2a/C2b predating the
time-anchoring fix). Those 120 were quarantined (`eval/cache/llm/_quarantine_nemotron_prefix_20261014`)
so B1 ran all 450 fresh.

Outcome: 450/450 ok, 0 error, 142.9 min; day HTTP = 824/4000. `eval/runs/eval_nemotron-3-ultra/results.json`.
- C1a: valid_json 145/150 (96.7%); 9 finish=length at exactly 8192 tokens (cap confirmed
  applied -> genuine over-length, not the old 4096 bug); per-protocol-usable 141/150.
- C2a: valid 150/150; 7.0 HTTP/scen, 6 tools, median 20s.
- C2b: valid 149/150 (1 finish=length); 6.0 HTTP/scen, 5 tools.
- 0 unknown-tool calls, 0 forced_final, 0 max_rounds; crop_score in C2b = 0; 429 = 0.

Note: B1 holds only C1a/C2a/C2b. Nemotron C0/C0b/C1/C2 were produced by the pre-fix 500-run
(separate run dirs); they are tool-less and thus unaffected by the harness fix, but using them
alongside B1 is a cross-source join that must be decided explicitly before Nemotron primary
contrasts (C2a-C0b etc.) are computed.

## 8.18 Nemotron primary metrics on the 150 (2026-10-14)

Output: `eval/results/nemotron_primary_metrics.{txt,json}` (`eval/scripts/nemotron_primary_metrics.py`,
reuses the stage-A metric/statistics code).

**Reuse verification (step a).** For all 150 B1 scenarios, the Nemotron C0 and C0b records were
checked against the CURRENT prompt builders: the run_model cache key
`sha256(model\u241fcond\u241fprompt\u241fsid\u241frep)` recomputed from `prompt_c0`/`prompt_c0b`
equals the stored `prompt_hash` in **300/300** cases; model id matches; no blank hashes; no cap
suspicion. **0 needed re-running (step b).**

**Disclosed asymmetry (step c).** Nemotron C0/C0b are reused from the pre-fix run
(2026-10-10T15:48Z .. 2026-10-12T01:55Z), prompt-identical, tool-less, 4096 cap unchanged
(config.yaml SHA256 `2C5BC2A74828F3C5D0D451740302E4F7523BD97ABBBDA95C9299787BB54FEA07`,
temperature 0.2); C1a/C2a/C2b are fresh post-fix (2026-10-14). Llama Stage A used the same
reuse policy, so both models are sourced consistently.

**C1a truncation (step d).** 9/150 (6.0%) finish=length at exactly 8192 -> genuine over-length,
not the old 4096 bug (Llama Stage A: 0/150). Reported per-protocol (PP n=141) and ITT (n=150, the
9 counted as failing), as pre-registered.

**Cells (STRICT | PP, 95% CI):** C0 .530, C0b .663, C1a .665 (n=141), C2a .801, C2b .722 (n=149),
C3 .863. ITT: C0 .484, C0b .574, C1a .625, C2a .801, C2b .717. (Hard-violation falls in the same
order: C2a .165 < C2b .153/.159 < C1a .275 < C0b .273 < C0 .391 at PP strict.)

**Pre-registered contrasts (STRICT | PP):** sv C2a-C0b +0.150 [.083,.216] Holm 5.1e-04; C2a-C1a
+0.133 [.085,.186] Holm 5.5e-06; C2b-C0b +0.061 Holm 0.077 (n.s.); C2b-C1a +0.061 Holm 0.077
(n.s.). hv C2a-C0b -0.110 Holm 2.6e-03; C2a-C1a -0.106 Holm 3.8e-04; C2b-C0b -0.114 Holm 5.4e-04;
C2b-C1a -0.119 Holm 8.1e-06. Under ITT all four are significant for both metrics (sv C2a-C0b
+0.227 Holm 8.7e-08 ... C2b-C1a +0.092 Holm 3.9e-03). WITHOUT-pilot is directionally identical
(PP: C2a-C0b +0.114 Holm 0.062, C2a-C1a +0.135 Holm 4.6e-04).

**Exploratory:** C1a-C0b ~ 0 (sv +0.007 Holm 0.92) - the fair evidence stuffing does nothing,
replicating Llama. C2a-C2b small but significant under ITT (sv +0.084 Holm 7.0e-03), n.s. at PP.

**Fidelity to C3 (C2a, diagnostic only):** top-5 Jaccard 0.820, top-1 agreement 0.827 (higher than
Llama's 0.685 / 0.787). Per-scenario vs C3: sv match 107 beat 4 lose 39; hv match 118 beat 1 lose 31.

## 8.19 Four offline gaps on the Nemotron result (2026-10-14)

Output: `eval/results/gaps_analysis.{txt,json}` (`eval/scripts/gaps_analysis.py`, reuses the stage-A
metric/statistics code). All reported WITH and WITHOUT the 40 pilot_dev.

**Gap 1 - ITT contrasts + claimability.** The four pre-registered contrasts are computed under ITT
(paired diff, 95% CI, Cliff's delta, Holm) alongside PP for sv and hv, STRICT and LENIENT. A contrast
is marked CLAIMABLE only where PP and ITT are BOTH significant AND same sign.

- **Direction under ITT (sv):** C2b-C0b = **+0.143** (strict; +0.176 lenient) and C2b-C1a = **+0.092**
  (strict; +0.132 lenient), all significant -> under ITT **C2b is BETTER than the baseline**, the
  opposite of Llama (where Llama C2b-C0b ITT was **-0.210**). The ITT/PP divergence for C2b is a
  Nemotron-specific reversal.
- **Claimable (WITH pilot):** sv strict -> only the two C2a contrasts (C2b pairs n.s. at PP); sv
  lenient -> all four; hv -> all four (strict and lenient).
- **Claimable (WITHOUT pilot):** sv strict -> only C2a-C1a; sv lenient -> all except C2b-C0b; hv ->
  all except C2a-C0b (strict).
- The C2b sv pair is the ONLY family cell whose claimability flips between strict/lenient and
  with/without pilot. This is the primary target of the n=500 extension (B2).

**Gap 2 - Hard-violation cells + all four contrasts (co-primary).** Full hv cells in
`gaps_analysis.txt` (STRICT/LENIENT x PP/ITT). At PP strict: C0 .391, C0b .273, C1a .275, C2a .165,
C2b .153, C3 .104. All four hv contrasts are significant at PP strict (C2a-C0b -0.110; C2a-C1a -0.106;
C2b-C0b -0.114; C2b-C1a -0.119) and under ITT (-0.205/-0.153/-0.211/-0.160), so every hv contrast is
CLAIMABLE WITH pilot (all 8) and nearly all WITHOUT pilot (only C2a-C0b strict PP n.s.). hv is
directionally stable across all 8 cells; unlike sv, hv shows no C2b sign reversal.

**Gap 3 - Fidelity to C3, BOTH models (diagnostic only), counts AND %:**

| model | Jaccard (PP / ITT) | top-1 (PP / ITT) | sv match/beat/lose (strict PP) | hv match/beat/lose (strict PP) |
|---|---|---|---|---|
| Nemotron C2a WITH | 0.820 / 0.820 | 0.827 / 0.827 | 107/4/39 (71.3/2.7/26.0%) | 118/1/31 (78.7/0.7/20.7%) |
| Nemotron C2a WITHOUT | 0.796 / 0.796 | 0.836 / 0.836 | 76/1/33 (69.1/0.9/30.0%) | 82/0/28 (74.5/0.0/25.5%) |
| Llama C2a WITH | 0.685 / 0.676 | 0.787 / 0.667 | 90/3/34 (70.9/2.4/26.8%) | 95/2/30 (74.8/1.6/23.6%) |
| Llama C2a WITHOUT | 0.696 / 0.684 | 0.813 / 0.709 | 67/1/28 (69.8/1.0/29.2%) | 70/1/25 (72.9/1.0/26.0%) |

(Nemotron per-scenario rows n=150 PP=150; Llama sv/hv n=127 PP / 150 ITT. Percentages in the file.)
Nemotron tracks C3 more closely than Llama on both Jaccard and top-1; both models "lose" (score worse
than C3) on ~26-30% of sv and ~20-26% of hv scenarios.

**Gap 4 - C1a 8192-truncation bias (Nemotron 9/150 vs Llama 0/150).** Nemotron C1a truncated 9
(finish=length, exactly 8192). Composition vs the 141 retained: seasons Zaid 2/Kharif 3/Rabi 4 vs
Kharif 44/Rabi 56/Zaid 41; stress-set 44.4% vs 40.4%; risk-flag 22.2% vs 20.6%; evidence length mean
7907 vs 7918 (delta -12 chars). No material systematic difference (composition, stress, risk, and
input length are all within noise on n=9); truncation looks like a per-scenario OUTPUT-verbosity
property, not a scenario-type bias. Effect is bounded: PP C1a .665 vs ITT .625 (the 9 counted as
failures). **Verdict: PP C1a is not materially biased by truncation; report both PP (n=141) and ITT.**

## 8.20 Stage B2 - PROPOSED, NOT LAUNCHED (2026-10-14)

**Status: proposal only.** No launch. B2 runs Nemotron C1a/C2a/C2b on the REMAINING 350 scenarios
(151..500 of `eval/data/llm_subset.jsonl`), completing n=500 per condition.

**B2 was ALWAYS part of the plan** - it is the second half of the pre-registered n=500 Stage B grid,
not an optional-stopping extension triggered by the 150-case result. Deciding to run it now is NOT a
violation of the stopping rule: the stopping rule governs whether to STOP early on a positive result,
not whether to complete the pre-planned sample. **Main scientific value:** resolving the currently
n.s. C2b vs baseline season-validity contrast (STRICT|PP +0.061, Holm 0.077 at n=150) at n=500, where
the paired design has power to separate the two directions (PP n.s. vs ITT significant-positive).

**Cost estimates (from B1 actuals, 150 scenarios, 3 conditions):**

- Calls: 350 x 3 = **1,050**.
- HTTP: B1 used 2,100 (C1a 1.00/scen, C2a 7.00/scen, C2b 6.00/scen) -> B2 ~ **4,900 HTTP** =
  **1.23 days at the 4,000/day cap -> spans 2 UTC-days** (the budget enforcer will split it).
- Tokens: B1 1.71M in / 0.96M out -> B2 ~ **3.99M in / 2.23M out**.
- Wall time: B1 33,981 call-seconds for 150 -> B2 ~79,289 call-seconds / workers: **~5.5 h @4,
  ~3.7 h @6, ~2.8 h @8**.
- C1a will again truncate ~6% at 8192; PP n will be ~330, ITT n=350.

**CORRECTION (see 8.22):** the HTTP figures above are wrong. They assumed one HTTP per tool call, but
the model emits all tools in one response, so C2a ~2.19/scen and C2b ~2.12/scen (measured from B1's
tool logs). B1 actually used 824 HTTP, and **B2 is ~1,860 HTTP, fitting one UTC-day budget** - not
~4,900 spanning two days.

**Pre-launch hygiene (required):** the run_model cache key is unchanged by the harness fix, and the
quarantine only covered the 40 pilot_dev prefix. Verify the remaining 350 C1a/C2a/C2b records are not
stale-cached (they should be absent - B1 only ran 1..150), and re-verify C0/C0b reuse for 151..500
before computing n=500 metrics.

## 8.21 Real MCP transport option + equivalence checks (2026-10-14)

**Scope.** Add an OPTIONAL real MCP-client transport for C2a/C2b tool execution and prove it is
equivalent to the in-process transport. **The in-process path remains the DEFAULT and is unchanged;
no existing results were re-run or altered.** This addresses the audit finding (REPO_AUDIT.md:31 /
DIAGNOSTICS.md:194) that C2a/C2b resolved tool calls in-process via `ToolRuntime` (OpenAI
function-calling) and never exercised the MCP server.

**Provenance / no-live-call guarantee.** `eval/mcp_runtime.py::McpToolRuntime` opens one persistent
`mcp.ClientSession` against `eval/mcp_eval/server.py` over streamable-http. That server serves the
SAME frozen, time-anchored bundles produced by `eval.time_anchored.TimeAnchoredBuilder` (written to
`eval/runs/archive_v2/evidence/` by `eval/scripts/build_evidence_v2.py`); it only reads pre-computed
JSON and never runs the live tools, so it never reaches `datetime.now()` or live Open-Meteo. The
server is keyed by `(round(lat,4), round(lon,4))` via `evidence/index.json` (regenerated; 10,000
keys, 0 collisions at 4 dp). The runtime forwards the scenario's canonical coordinates (the harness
is scenario-authoritative, exactly as in-process), so the only difference vs. the in-process runtime
is the transport (JSON-RPC/HTTP vs. a direct call).

**Wiring.** `run_model.py` gains `--tool-transport {inprocess,mcp}` (default `inprocess`) and
`--run-suffix`; MCP runs write to a separate run dir and to a transport-scoped cache namespace
(`.../llm/<model>_mcp/`) so they cannot silently reuse in-process records. Non-C2 conditions are
unaffected. `ToolRuntime`/`McpToolRuntime` are now interchangeable (both expose `call`, `list_tools`,
`close`, context-manager).

**Stage 1.5 - schema diff** (`eval/scripts/mcp_schema_diff.py` -> `eval/results/mcp_schema_diff.json`):
tool names, descriptions, and parameter schemas were compared between `list_tools()` and
`NvidiaProvider._build_tools`. Initial diff: the MCP-generated schemas omitted the
`latitude`/`longitude` property descriptions. **Change made:** the server parameters are now
`Annotated[float, Field(description=...)]` (`eval/mcp_eval/server.py`) to match the harness. Result
after alignment: **0 differences** across all six tools. (Note: the harness sends `_build_tools`
declarations in BOTH transports, so the model-facing interface was already identical; aligning the
server makes a native MCP client see the same too.)

**Stage 1.6 - tool-output equivalence** (`eval/scripts/test_mcp_equivalence.py` -> `eval/results/mcp_equivalence.json`):
50 scenarios x 6 tools = 300 calls, same scenario/args both ways.
**Model-visible payload identical 300/300** (`json.dumps(result, ensure_ascii=False)`, the exact
string the provider places in the `role=tool` message). The logged `output_hash`
(`json.dumps(result, sort_keys=True, ensure_ascii=False)`) is identical 250/300, differing ONLY for
`climate_tool` (50/50) because the monthly-normals dict has integer keys in-process and string keys
after the JSON round-trip, which `sort_keys` orders differently. This is cosmetic (hash-only); the
model-visible content is byte-identical.

**C2b gate over MCP** (`eval/scripts/test_mcp_transport.py`): all checks pass - C2a advertises/can
call all six tools; C2b advertises exactly five and a `crop_score` call is rejected as unknown
BEFORE any runtime dispatch (spy confirms it never reaches the MCP runtime); an allowed tool over
MCP returns output byte-identical to in-process. The gate lives in `NvidiaProvider` ahead of the
runtime, so it is transport-independent by construction.

**Environment note.** The installed `anyio` (3.7.1) predates the generic
`create_memory_object_stream[T]` API that `mcp` 1.22's client and server use. Rather than mutate the
environment, `eval/anyio_compat.py::install()` replaces the module-level factory with a class that
supports both `f(...)` and `f[T](...)`; it is installed by `eval/mcp_runtime.py` and
`eval/mcp_eval/server.py`. All `mcp` call sites read `anyio.create_memory_object_stream` at call
time, so the shim applies without touching site-packages.

**Stage 2 - live MCP C2a run x50** (`eval/scripts/compare_mcp_transport.py` ->
`eval/results/mcp_transport_comparison.json`). Ran `--conditions C2a --scenarios 50
--tool-transport mcp --run-suffix _mcp_c2a50` (Nemotron; 50/50 ok, 0 err, 6.9 min; results in
`eval/runs/eval_nemotron-3-ultra_mcp_c2a50/results.json`, separate from B1). Comparison vs the
in-process B1 C2a records for the SAME 50 scenario_ids: **top-5 exact order 50/50**; every metric
cell (strict/lenient x PP/ITT x sv/hv) differs by **max |diff| = 0.0**; fidelity-to-C3 identical
(Jaccard 0.848, top-1 0.80); run-level flags identical (valid_json 50/50, truncated 0, unknown-tool
0, forced_final 0, finish_reason `stop` x50, tool_calls median 6). The only difference is per-call
latency (median 28.5 s over MCP vs 19.4 s in-process), expected from the HTTP/JSON-RPC round-trips.
The transport is therefore confirmed equivalent: the model receives identical evidence and produces
identical outputs.

**Framing (write-up).** This equivalence is a **methods-validation check, NOT a finding.** At
temperature 0.2, with byte-identical tool payloads and identical tool schemas, identical model
outputs are the *expected* result. It licenses the claim "the MCP transport is a faithful
re-implementation of the in-process tool path", and nothing more - it is not evidence about tool use
quality, and must not be reported as a result about models or conditions.

## 8.22 MCP equivalence run - freshness audit and HTTP-accounting correction (2026-10-14)

Offline audit (`eval/scripts/_recon_transport_audit.py`) of the Stage 2 MCP C2a x50 run.

**(1) Cache transport isolation.** The run_model cache KEY payload is
`"\u241f".join([model, cond, prompt, sid, rep])` - it does **not** contain the transport. Isolation
is instead by cache **directory**: `run_model.py` uses a `<short>_mcp` namespace for mcp runs
(`:147`). The MCP run therefore used `eval/cache/llm/nemotron-3-ultra_mcp/`, which started empty.
**0 of the 50 MCP C2a records were cache-served; all 50 were generated fresh.** Confirmed by: the
_mcp dir holds exactly 50 files; each MCP record's cache file is present in the _mcp dir (50/50) and
the in-process dir holds the B1 files at the *same* prompt_hash (50/50 identical hashes - the
namespace, not the key, separates them); and the 50 MCP timestamps are distinct from B1's (below).
No purge/re-run was needed.

**(2) HTTP accounting.** The budget counter (`eval/llm/budget.py::DailyBudget.reserve`) counts every
HTTP **attempt including retries** (called immediately before each POST). The earlier "7.00 HTTP/scen
for C2a / 6.00 for C2b" figure was **wrong**: it assumed one HTTP per tool, but the model emits all
six tool calls in a **single** assistant response (tool_log shows one tool-bearing round with
`tool_calls=6`), so a C2a call is ~2 HTTP (one tool-bearing request + one final synthesis request).

- B1 C2a actual (n=150): rounds histogram {1: 137, 2: 9, 6: 4} -> 329 no-retry POSTs = **2.19/scen**.
- MCP C2a actual (n=50): rounds histogram {1: 44, 2: 6} -> 106 no-retry POSTs = **2.12/scen**; budget
  moved 824 -> 947 = **123**, i.e. 106 base + **17 retried attempts** (429/5xx/timeout backoffs the
  counter intentionally includes). The counter is accurate; the 350 expectation was not.

**Correction to 8.20.** B1 actually used 824 HTTP (not 2,100), so **B2 (350 scenarios x C1a/C2a/C2b)
is ~1,860 base HTTP, not ~4,900** (C1a 1.00 + C2a 2.19 + C2b 2.12 per scenario). It fits comfortably
within one 4,000/day budget; the "spans 2 UTC-days" note in 8.20 is superseded.

**(3) Freshness.** Records persist no request/response id (fields are timestamp, prompt_hash,
latency_s, tool_log, tokens, flags); the only in-record freshness signal is `timestamp`. All 50 MCP
records are timestamped `2026-10-14T12:39..12:47Z` (spanning the 6.9-min run); the B1 C2a records for
the same 50 sids are `2026-10-14T00:0xZ`; **overlap = 0**. Examples:
`S000006` B1 2026-10-14T00:01:54Z vs MCP 12:39:44Z; `S000072` B1 00:03:18Z vs MCP 12:40:05Z.

## 8.23 Nemotron primary metrics at n=500 (2026-10-15)

Script `eval/scripts/n500_primary_metrics.py` -> `eval/results/n500_primary_metrics.{txt,json}`.
Single verified paired set, MERGED: C1a/C2a/C2b = B1 (`eval_nemotron-3-ultra`, 150) + B2
(`eval_nemotron-3-ultra_b2`, 350); C0/C0b from the run_model cache (pre-fix run, verified reusable);
C3 `full_repo` top5 from `archive_v2/deterministic`; risk flags from `archive_v2/evidence`.
Metrics follow 8.9/8.11 (slot-fraction season-validity + hard-violation, GT v1.1), STRICT/LENIENT x
PP/ITT, 95% bootstrap CIs, Wilcoxon + Cliff's delta + Holm (family = 4 pairs), WITH and WITHOUT the 40
pilot_dev scenarios. B2's exit=1 was a benign watcher file-lock race on the final `os.replace`;
results.json was already written (1,050 records).

**Coverage** (n = 500 distinct sids/condition; unique (sid,cond)): PP-usable C0 451, C0b 442, C1a 470,
C2a 500, C2b 494, C3 500; ITT n = 500 each. C1a 8192-truncation at n=500: 30/500 (6.0%), valid_json
484, PP-usable 470.

**Strict per-protocol cells (season-validity | hard-violation):** C0 0.551|0.382, C0b 0.646|0.292,
C1a 0.665|0.292, C2a 0.803|0.161, C2b 0.772|0.151, C3 0.863|0.104.

**Pre-registered contrasts - ALL FOUR ARE CLAIMABLE** (PP and ITT agree in sign and both Holm<0.05)
on season-validity and hard-violation, strict and lenient, with and without pilot_dev. The two that
were n.s. at n=150 now resolve decisively (strict, season-validity):
- **C2b-C0b**: PP +0.128 [+0.093,+0.163] Holm 3.59e-12 (n=436); ITT +0.193 Holm 5.93e-22 (n=500).
- **C2b-C1a**: PP +0.105 [+0.074,+0.136] Holm 2.48e-11 (n=465); ITT +0.138 Holm 2.65e-15 (n=500).
- C2a-C0b: PP +0.161 Holm 3.48e-13; ITT +0.232 Holm 2.41e-24. C2a-C1a: PP +0.135 Holm 3.88e-15; ITT
  +0.178 Holm 5.93e-22. (Cliff's delta +0.08..+0.14 strict PP; larger under ITT.)

**Exploratory contrasts are NOT claimable** (PP n.s. while ITT occasionally significant => sign/
significance disagreement): C1a-C0b and C2a-C2b stay inconclusive.

**Fidelity to C3 (C2a vs C3 full_repo, n=500):** top-5 Jaccard 0.8307, top-1 agreement 0.850; strict
per-scenario season-validity match 72.2% / beat 2.6% / lose 25.2%; hard-violation match 79.4% /
beat 0.4% / lose 20.2%. **Scope (item 7):** Nemotron is n=500 (full `llm_subset`); Llama is n=150;
any cross-model comparison is at n=150 (common support).

## 8.23a GT provenance audit - scorer vs cited GT tables (items 8-11, 2026-10-15)

Offline (`eval/scripts/gt_provenance_audit.py` -> `eval/results/gt_provenance_audit.{txt,json}`).

- **Registry.** The C3 scorer (`run_deterministic_v2.py`) reads **`crop_log.csv`** (root), which has
  **no source/citation column**. The LLM metrics used in the primary analysis
  (`stage_a_interim_metrics.py` -> `season_validity` / `hard_violation`) read the **cited** GT tables
  v1.1. `eval/metrics.py::CROP_SEASON_VALIDITY` is crop_log-derived (its own comment says so) and is
  **not** on the primary path. So scorer and evaluated GT are **separate, independent files**.
- **Divergence (3 crops).** With cited rows only: crop_log (and `metrics.py`) call **Groundnut**,
  **Urad** kharif-only and **Sunflower** kharif+rabi, whereas the cited GT table adds **Zaid** for all
  three (and Sunflower keeps rabi). The scorer therefore treats some GT-cited seasons as invalid.
- **Weight.** Scorer season-alignment weight = **0.30** (`config.yaml:137`). The **0.35** constant is
  the risk-sensitivity `low` weight (`RISK_SENSITIVITY_WEIGHTS`), **not** the season weight.
- **Hard constraints.** 29 season rows all `cited`; drought 2 rows (`Rice`, `Sugarcane`) `unverified`;
  flood 5 rows (1 `cited` = Urad; 4 `unverified`). `metrics.WATER_INTENSIVE_CROPS` (a heuristic) adds
  Arhar/Cotton/Maize/Sunflower beyond the cited drought set {Rice, Sugarcane}; legacy, not used by
  `stage_a`.
- **Unverified rows.** `UNVERIFIED_FOR_REVIEW.csv` = 13 rows (crop_season_table 5 season-rows;
  hard_constraints 8) = 10 still `unverified` + 3 upgraded to `cited-v1.1` (Barley). Conclusion:
  the scorer's GT dependence is independent of (not shared with) the evaluated GT tables - a methods
  note; report the 3 divergent crops explicitly.

## 8.24 HTTP / tool-round reconciliation - the "7.0/scenario" number is Llama's (2026-10-15)

Offline (`eval/scripts/recon_http_rounds.py` -> `eval/results/recon_http_rounds.{txt,json}`). Requests
per scenario = (tool-call rounds) + 1 final answer; the budget counter adds retries.
- **Nemotron** (B1 and B2): C1a **1.00**, C2a **2.19**, C2b **2.12-2.18** base requests/scenario -
  the model emits all 6 tools in ONE response (C2a rounds hist {1:137, 2:9, 6:4} at B1).
- **Llama-3.2-11b**: C2a **7.49**, C2b **7.04** base requests/scenario (mean **6.49 / 6.04 tool
  rounds** - one tool per response), C1a/C0/C0b 1.00.
- The erroneous "7.0 HTTP/scen C2a" figure was therefore the **Llama** number (6 tools + 1), mis-
  attributed to Nemotron. **Reportable efficiency finding:** on the identical tool task Nemotron
  single-shots all six tools per turn (~2.2 requests/scen), Llama round-trips one tool per turn
  (~7.5), a ~3.4x request overhead.

## 8.25 Consistency repeats launched (2026-10-15)

PROTOCOL 8.x STEP E design: 100 scenarios x {C0b, C1a, C2a} x 3 repeats (repeat 0 exists; repeats
1-2 fresh => 600 fresh/model), Nemotron then Llama. Launcher
`eval/scripts/_consistency_launch.ps1` (detached, resumable, waits for UTC reset if budget hit),
status `eval/runs/logs/consistency.status`, keep-awake `eval/scripts/_keepawake_consistency.ps1`.
No network/API in this paragraph beyond the launched runs themselves.

## 8.26 Contrast heterogeneity across the B1/B2 halves + season stratification (2026-10-15)

Offline (`eval/scripts/n500_heterogeneity.py` -> `eval/results/n500_heterogeneity.{txt,json}`). B1
(the 150-scenario batch) and B2 (the 350-scenario batch) are disjoint and together form the 500-set.
For each pre-registered contrast we report the paired diff (95% bootstrap CI) on B1, on B2, and merged,
plus an interaction `Delta = diff(B2) - diff(B1)` (two-sample bootstrap CI + two-sided permutation test,
5,000 perms), and the four contrasts stratified by `season_stratum`.

**Season composition.** B1: Kharif 47 / Rabi 60 / Zaid 43 (n=150); B2: Kharif 143 / Rabi 117 / Zaid 90
(n=350); merged: 190 / 177 / 133 (n=500). The halves are **not** season-balanced (B1 is Rabi/Zaid-heavy,
B2 is Kharif-heavy).

**Interaction (strict, season-validity).**
- C2b-C0b: B1 +0.062 [-0.000,+0.126] vs B2 +0.156 [+0.116,+0.198]; **interaction +0.094 [+0.019,+0.169],
  perm p=0.019 -> significant heterogeneity**; replicates the author's expectation (~+0.061 vs ~+0.157).
- C2b-C1a: B1 +0.061 vs B2 +0.124; interaction +0.062 [-0.010,+0.133], perm p=0.078 -> marginal.
- C2a-C0b and C2a-C1a: interaction ~+0.01, perm p>=0.74 -> **stable across halves**.
- Hard-violation interactions are all small and n.s. (|Delta|<=0.034, p>=0.31); ITT dampens but does
  not remove the C2b sv interaction (C2b-C0b p=0.064, C2b-C1a p=0.079).
So the C2a/C1a benefits are homogeneous across the two batches; the extra gain of C2b over C0b/C1a is
concentrated in B2. Part of this tracks the season mix (B2 has proportionally more Kharif, where the
C2b contrasts are largest).

**Season-stratified contrasts (n=500, strict per-protocol season-validity).**
- Kharif (n=190): all four large and significant - C2a-C0b +0.275, C2a-C1a +0.250, C2b-C0b +0.168,
  C2b-C1a +0.142 (Holm<<0.001).
- Rabi (n=177): C2a-C0b +0.119 (Holm 3.7e-6); **C2a-C1a -0.012 (n.s.)**; C2b-C0b +0.061 (Holm 0.030);
  **C2b-C1a -0.067 (Holm 0.014, i.e. C2b is significantly WORSE than C1a on Rabi sv).**
- Zaid (n=133): C2a-C0b +0.053 (n.s.); C2a-C1a +0.167 (Holm 7.2e-12); C2b-C0b +0.163 (Holm 2.6e-4);
  C2b-C1a +0.276 (Holm 2.2e-12).
Effect is **season-dependent**: positive and largest in Kharif/Zaid; in Rabi the C2b contrasts shrink and
C2b-C1a turns negative (the merged +0.105 is a Kharif/Zaid composition effect). Report per-season; the
Rabi C1a>~C2b nuance is a reportable finding, not a blocker. Hard-violation is similarly structured
(Kharif strongest; Rabi C2b-C1a ~ -0.005 n.s.).

## 8.27 Divergent-crop provenance impact at n=500 (2026-10-15)

Offline (`eval/scripts/n500_divergent_crop_impact.py` -> `eval/results/n500_divergent_crop_impact.{txt,json}`).
Follow-up to 8.23a: how much do the three divergent crops (Groundnut, Urad, Sunflower - the cited GT
adds a Zaid season the uncited scorer registry lacks) move the headline.

**Presence.** Scenarios with >=1 divergent crop in top-5: C3 **437/500 (87.4%)** (Sunflower 312,
Groundnut 135, Urad 126); C2a **414/500 (82.8%)**; C1a 216 (43.2%), C2b 157 (31.4%), C0 156 (31.1%),
C0b 137 (27.4%). C3 or any LLM top-5 contain one in 467/500; either in 467. (Sunflower dominates C3/C2a.)

**Robustness.** Removing the three crops from **every** top-5 (scorer and LLM alike) shifts every
pre-registered contrast by <= **0.030**; no sign flips; **all 16 claimability cells (strict/lenient x
sv/hv x 4 pairs) are preserved**. E.g. C2b-C0b strict sv PP 0.128 -> 0.119; C2b-C1a 0.105 -> 0.099.
Conclusion: the divergent-crop GT mismatch is a provenance/limitations note; conclusions are robust to
excluding it. (Item 3 done.)

## 8.28 Corrections log (2026-10-15)

- **Season weight 0.30, not 0.35.** The scorer season-alignment weight is **0.30** (`config.yaml:137`);
  **0.35** is the risk-sensitivity `low` weight (`RISK_SENSITIVITY_WEIGHTS`). Repo-wide grep finds no
remaining file that states 0.35 as the season weight; the only prior occurrences were already
corrected (this section's 8.23a, PROGRESS). The "Barley analysis" referred to is **8.5**, which
already states the season weight as 0.30 (the Barley diagnosis at 8.5 line ~338). No further edit.

## 8.29 Close-out checks (heterogeneity-vs-season, per-season table, Rabi rainfall test) - 2026-10-15

Offline (`eval/scripts/n500_heterogeneity_season.py` -> `eval/results/n500_heterogeneity_season.{txt,json}`).

**Check 1 - is the B1/B2 heterogeneity a season-composition effect?** No, not for C2b-C0b.
Per-scenario paired diff `d = sv(C2b) - sv(C0b)` (strict PP), OLS:
- Composition: B1 47/60/43, B2 143/117/90 (Kharif/Rabi/Zaid) - unbalanced.
- **C2b-C0b:** Model A `d ~ isB2` coefficient **+0.094 (SE 0.038, p=0.015)**; Model B `+ Rabi + Zaid`
  -> **+0.087 (p=0.024)**; Model C `+ isPilot` -> **+0.105 (p=0.017; isPilot p=0.394)**. The half
  difference **SURVIVES both season and pilot_dev adjustment.** Cell means confirm a within-season
  gap (B1 -> B2: Kharif +0.081 -> +0.197, Rabi +0.038 -> +0.073, Zaid +0.077 -> +0.203). **This is a
  genuine B1/B2 batch difference, not a season-composition artefact** - report it (the 150-scenario
  B1 half shows a smaller C2b-C0b gain than the 350-scenario B2 half, in every season).
- **C2b-C1a**: Model A +0.062 (p=0.072); Model B +0.054 (p=0.092) with Rabi -0.205 (p=4.6e-9), Zaid
  +0.138 (p=1.9e-4), R2 0.007 -> 0.167. Here the (already marginal) half difference is **explained by
  season**; the Rabi sign is consistent across halves (B1 -0.073, B2 -0.065), so it is not a batch
  artefact.
- Caveat: adjusted models still have small R2 (0.03); the effect is small/noisy and B1 is underpowered.

**CHECK 2 - four pre-registered contrasts by season, n=500 (EXPLORATORY / post hoc only).**
Script `n500_heterogeneity_season.py` -> `n500_heterogeneity_season.{txt,json}` (PART B of
`n500_heterogeneity.py` agrees). season-validity, STRICT, per-protocol:

| season (n) | C2a-C0b | C2a-C1a | C2b-C0b | C2b-C1a |
|---|---|---|---|---|
| Kharif (190) | +0.275 [+0.211,+0.342] | +0.250 [+0.191,+0.312] | +0.168 [+0.114,+0.225] | +0.142 [+0.091,+0.193] |
| Rabi (177) | +0.119 [+0.072,+0.166] | -0.012 [-0.053,+0.030] | +0.061 [+0.016,+0.107] | -0.067 [-0.110,-0.023] |
| Zaid (133) | +0.053 [-0.034,+0.139] | +0.167 [+0.135,+0.200] | +0.163 [+0.081,+0.246] | +0.276 [+0.220,+0.328] |

(hard-violation STRICT PP and season-validity STRICT ITT are in the txt/json.) These are
EXPLORATORY; the pre-registered merged-n=500 contrasts (8.23) remain the primary results.

**CHECK 3 - does the Rabi anomaly track the inert scorer rainfall channel (8.14)? -> NOT SUPPORTED.**
From `archive_v2/evidence` `crop_score.scores.rainfall_match` (all crops, all 500 scenarios):
Kharif mean 0.909, frac==0 = 0.004 (informative); **Rabi mean 0.000, frac==0 = 1.000 (inert)**;
**Zaid 0.000, frac==0 = 1.000 (also inert)**. The C2b-C1a sv sign is Kharif +0.142, **Rabi -0.067,
Zaid +0.276** - so Rabi and Zaid are *equally* rainfall-inert yet have opposite signs. Scenario-level
correlation between the per-scenario rainfall_match spread and the sv C2b-C1a diff is ~0 (Pearson
r=+0.040 p=0.38; Spearman 0.044 p=0.34). Additionally, C1a and C2b receive the SAME rainfall values
(pasted vs fetched), so rainfall inertness cannot by construction produce a C2b-vs-C1a divergence.
**Conclusion: the rainfall-channel limitation is confirmed (Rabi is inert, as in 8.14) but it does NOT
explain the Rabi C2b-C1a sign; the two co-occur by season only. Do not assert a mechanism.**

### 8.29 (cont.) Selection-variable audit of the B1(150)-vs-B2(350) halves

Offline (`eval/scripts/n500_heterogeneity_selection.py` -> `eval/results/n500_heterogeneity_selection.{txt,json}`).
B1 = `llm_subset[:150]`, B2 = `llm_subset[150:]`. Compares the halves on everything else the nested
selection could have touched (district, agro-climatic zone, stress.jsonl membership, risk flags,
C3 top-5 score margin, season-valid crop pool).

**What differs.**
- **District: differs strongly** (chi2=483.6, dof=50, perm_p=0.0005). B1 = 17 districts; B2 = 35;
  **shared districts = 1** (16/500 scenarios). B1-only=16, B2-only=34 -> the halves are **near
  district-disjoint**; the split tracks the district blocks of the subset, not a random sample.
- **stress.jsonl membership: differs** (B1 0.407 vs B2 0.254, diff +0.152, perm_p=0.0008).
- drought (0.160 vs 0.123, p=0.32), flood (0.053 vs 0.054, p=1.0), C3 margin top1-top5
  (0.111 vs 0.115, p=0.55), top1-top2 (p=0.43), top5/top6 cutoff (p=0.93), n_crops (6 vs 6, p=1.0):
  **no difference**. n_seasvalid (8.31 vs 8.94, p=0.060) marginal, not significant.
- agro-climatic zone is `None` for all 500 (no information).

**Re-test of the C2b-C0b batch coefficient** (d = sv(C2b)-sv(C0b), strict PP, n=437):
baseline (isB2 + Rabi + Zaid + isPilot) isB2 = **+0.105 (p=0.017)**; adding stress -> **+0.088
(p=0.044)**; adding zone dummies -> unchanged +0.088; district FE -> +0.190 (SE 0.216, p=0.38, not
interpretable: near-collinear with isB2 given the 1 shared district); shared-districts-only subset
(n=12) -> non-significant but uninformative. **No single selection variable absorbs the coefficient.**
Season, stress, drought, flood, C3 margins, season-valid pool size and pilot_dev each leave
isB2 ~ +0.09-0.11. Therefore the batch gap is **UNEXPLAINED**, and — because B1/B2 are near
district-disjoint — it is **confounded with the nested district selection** (B1 = the pilot district
set; B2 = the remaining districts). It cannot be attributed to a clean measurement. C2b-C1a half gap
is n.s. in baseline (+0.028, p=0.44) and stays n.s. throughout.

**Reported per-half (so the heterogeneity is visible, not averaged away)** — strict PP, sv:
- C2b-C0b: B1 **+0.062 [-0.000,+0.126]** (n=130) | B2 **+0.156 [+0.116,+0.198]** (n=307) |
  merged **+0.128 [+0.094,+0.163]** (n=437); interaction **+0.094, perm_p=0.0186**.
- C2b-C1a: B1 **+0.061 [+0.001,+0.123]** (n=140) | B2 **+0.124 [+0.087,+0.160]** (n=325) |
  merged **+0.105 [+0.074,+0.136]** (n=465); interaction **+0.062, perm_p=0.0784**.

The merged n=500 contrasts (8.23) remain the primary result; the half split is reported alongside as
a **district-region segmented** view and the batch difference is disclosed as unexplained/confounded
with the nested district selection.

## 8.29a Consistency repeats (2026-10-15) - PENDING / to be completed when repeats land

100 scenarios x {C0b,C1a,C2a} x 3 repeats (repeat 0 exists; repeats 1-2 fresh). Analysis script
`eval/scripts/consistency_analysis.py` -> `eval/results/consistency_analysis.{txt,json}` (mean/95% CI
of within-scenario top-5 Jaccard across repeats, per model/condition). Consistency numbers are
secondary and circular by construction (temp 0.2, identical payloads); they must not appear as primary
results. FILL IN on completion. **After this, the eval is CLOSED.**

## 8.29b District-clustered inference at n=500 (2026-10-15)

Offline (`eval/scripts/n500_clustered_inference.py` -> `eval/results/n500_clustered_inference.{txt,json}`).
Scenarios are clustered within district (**51 districts**, mean 9.8 scenarios/district, range 3-20), and
B1/B2 are near district-disjoint (8.29 cont.), so the scenario-level CIs/p-values in 8.23 were
anti-conservative. All inference below resamples **districts** (not scenarios); p-values are centered
cluster-bootstrap p (10,000 resamples); Holm over the 4 pre-registered pairs.

**1. ICC by district, design effect, effective N (strict, per-protocol).**

| metric | condition | n | k | m_bar | ICC | DEFF | ESS |
|---|---|---|---|---|---|---|---|
| sv | C0 | 451 | 51 | 8.84 | 0.022 | 1.17 | 386 |
| sv | C0b | 443 | 51 | 8.69 | 0.000 | 1.00 | 443 |
| sv | C1a | 470 | 51 | 9.22 | 0.000 | 1.00 | 470 |
| sv | C2a | 500 | 51 | 9.80 | **0.166** | **2.47** | **203** |
| sv | C2b | 494 | 51 | 9.69 | 0.084 | 1.73 | 285 |
| sv | C3 | 500 | 51 | 9.80 | 0.000 | 1.00 | 500 |
| hv | C0 | 451 | 51 | 8.84 | 0.017 | 1.13 | 399 |
| hv | C2a | 500 | 51 | 9.80 | **0.241** | **3.12** | **160** |
| hv | C2b | 494 | 51 | 9.69 | 0.070 | 1.61 | 306 |
| hv | C3 | 500 | 51 | 9.80 | 0.052 | 1.46 | 342 |

Only the **tool-using** conditions (C2a/C2b) are materially clustered: the crop_score tool output is
district-determined, so scenarios in the same district get similar recommendations. C0/C0b/C1a are
near-zero; C3 sv is exactly 0 (deterministic). The **contrast** is far less clustered than the levels:
ICC(d) for C2b-C0b sv = **0.000** (DEFF 1.0, ESS 437); C2a-C0b sv 0.096 (ESS 254), C2a-C1a sv 0.082
(ESS 281), C2b-C1a sv 0.030 (ESS 374) - the shared district structure largely cancels in the paired
difference.

**2. District-clustered contrasts (all 16 cells).** Taken together with the (unchanged) point
estimates, the clustered CIs widen modestly and every pre-registered conclusion holds. Strict PP sv:
C2a-C0b **+0.161 [+0.107,+0.214]** (cl_p=1e-4, Holm 4e-4); C2a-C1a **+0.135 [+0.094,+0.176]**;
C2b-C0b **+0.128 [+0.093,+0.160]**; C2b-C1a **+0.105 [+0.069,+0.140]**. (Lenient and hv/ITT in txt/json;
all 16 clustered Holm = 4.0e-4, the bootstrap floor.) The naive vs clustered point estimates are
identical (paired), only the CIs widen.

**3. Claimability before -> after: 0 of 16 cells change.** All 16 (strict/lenient x sv/hv x 4 pairs)
are **CLAIMABLE** under both naive and district-clustered inference (PP and ITT agree in sign, Holm<0.05
both). Per-half: B1 **C2b-C1a sv** moves to **not significant** under clustering (+0.061 naive vs
clustered [-0.004,+0.139], p=0.091); B1 C2b-C0b sv is borderline ([+0.000,+0.123], p=0.047); all B2
and all hv cells stay significant. Per-season (EXPLORATORY, strict PP, clustered): Kharif all four
large and significant; Rabi C2a-C1a -0.012 n.s. and **C2b-C1a -0.067 negative**, C2a-C0b +0.119 and
C2b-C0b +0.061 significant; Zaid C2a-C0b +0.053 n.s., others significant.

**4. Between-district variation in the C2b-C0b effect (reframing the batch finding).** District-level
means of d = sv(C2b)-sv(C0b) (strict PP, 51 districts): mean **+0.123**, between-district
**SD 0.134**, range **-0.171 (Burhanpur) to +0.400 (Barwani)**, Q1 +0.068, median +0.125, Q3 +0.200.
ICC(d)=0.000, DEFF 1.0 (the district spread is within the within-district noise). The B1/B2 gap
(+0.094) is **0.70 between-district SDs** and is the difference between two district *sets*, not a
clean batch effect: B1 draws low-effect districts (Burhanpur, Dhar, Bhopal, Betul, Dewas), B2 draws
the higher-effect remainder (Ujjain, Mandsaur, Katni, Jhabua, Panna). **Presented as district-level
variation**, consistent with 8.29-cont.: the merged n=500 contrast is unchanged; the half split is a
district-region cut and the C2b-C0b "batch" gap is district heterogeneity.

**6. C2a-vs-C3 match/beat/lose at n=500 (per scenario).** sv: match **361 (72.2%)**, beat 13 (2.6%),
lose 126 (25.2%) - identical strict/lenient and PP/ITT (C2a is 100% usable). hv: strict match 397
(79.4%), beat 2 (0.4%), lose 101 (20.2%); lenient match 406 (81.2%), beat 1 (0.2%), lose 93 (18.6%).

**7. Exact paired C2a contrasts at n=500 (strict PP sv).** C2a-C0b **+0.1614 [+0.1234,+0.2006]**,
p=9.0e-14 (naive); clustered +0.1614 [+0.1069,+0.2141], p=1e-4; Cliff_d +0.233. C2a-C1a
**+0.1353 [+0.1055,+0.1660]**, p=9.7e-16; clustered +0.1353 [+0.0942,+0.1758]; Cliff_d +0.217.

## 8.30 Real-world independent evaluation - PRE-REGISTERED 2026-10-16 05:40 UTC

Frozen BEFORE any scoring. This section is the analysis plan for the external
(real-world) evaluation; it is not edited after STEP 5 begins. Companion artefacts:
`eval/real_data/SOURCES.md` (STEP 1), `QA.md` (STEP 2), `CIRCULARITY.md` (STEP 3).

### 8.30.1 Scope and non-negotiables

- Offline. No new model/LLM call is made. Only pre-existing saved outputs are read.
- The measured quantity is **agreement with actual district cropping patterns**, not
  accuracy of the system. The word "accuracy" is not used anywhere in this evaluation.
- The reference is derived from public DES/MoA&FW data and is held out from the system
  under test (see CIRCULARITY.md).
- No existing scorer weight, threshold, prompt, GT table or saved result is modified.

### 8.30.2 Reference construction (fixed)

Source: `eval/real_data/clean/area_by_district_season_year.csv` (10,304 rows; 51
districts x 3 seasons x 10 years; area in hectares).
Cells: the 153 (district, season) pairs.

- **R_prim (headline).** Window 2015-16 .. 2022-23 (8 years). For each cell, compute
  mean `area_ha` per crop over the years present, restrict to the 21-crop registry,
  rank by mean area descending. The reference top-5 = the first five. Summer maps to
  Zaid. Some Zaid cells have fewer than 5 in-vocab crops (QA.md); the effective k is
  `min(5, |R_prim(cell)|)`.
- **R_full (sensitivity, window).** Same, window 2015-16 .. 2024-25 (Pea over its 8
  available years, per QA.md).
- **R_all (secondary, all-crop).** Window 2015-16 .. 2022-23, ranking over ALL DES
  crops (no 21-crop restriction). Used for the out-of-vocab share and as an
  all-crop sensitivity. This is the mitigation agreed for CIRCULARITY F3.
- **R_prod (sensitivity).** Same window and registry restriction as R_prim, ranked by
  mean `production_t` instead of area.

R_prim is the headline reference; R_full, R_all and R_prod are reported as secondary.

### 8.30.3 System outputs (fixed)

- Nemotron (n=500): C1a/C2a/C2b from `eval/runs/eval_nemotron-3-ultra/results.json`
  (150) plus `eval/runs/eval_nemotron-3-ultra_b2/results.json` (350); C0/C0b from the
  `eval/cache/llm/nemotron-3-ultra` records; C3 from
  `eval/runs/archive_v2/deterministic/*.json` (`ablations.full_repo.top5`).
- Llama (`meta/llama-3.2-11b-vision-instruct`) from
  `eval/runs/eval_llama-3.2-11b/results.json` for all conditions present.
- A model's answer is the ordered list `parsed.top5`, names normalised to the registry
  exactly as in STEP 2. Usability (per-protocol) mirrors `n500_primary_metrics.usable`:
  no error, `valid_json` true, not truncated. ITT counts every attempted scenario with
  non-usable answers scored as zero hits.

### 8.30.3b Which registry crops are comparable

19 of 21 registry crops have a real district series (QA.md §3). Kodo-Kutki and
Watermelon have none in the window; if a model recommends them they are counted as
non-matches, and this is disclosed in the report.

### 8.30.4 Metrics (per scenario, then aggregated)

- `hits` = |model top-5 ∩ reference top-5| (set intersection).
- **Precision@5** = hits / min(5, |reference top-5|).
- **nDCG@5** = DCG@5 / IDCG@5, binary gain (1 if the crop is in the reference top-5,
  else 0), discount log2(rank+1), IDCG over the ideal ordering of min(5, |reference|)
  relevant crops.
- **Out-of-vocab share**: over R_all top-5, the fraction of reference crops that are
  outside the 21-crop registry (mean over cells; per season).
- Secondary: unweighted hit count, MRR as descriptive support only.

### 8.30.5 Inference and contrasts

- Each condition's level = mean over its scored scenarios; 95% CI by **district-
  clustered bootstrap** (resample the 51 districts, 10,000 resamples, seed 42),
  mirroring `n500_clustered_inference.py`.
- Paired contrasts on the per-scenario metric: **C2a-C0b, C2a-C1a, C2b-C0b, C2b-C1a,
  and C3-C2b**. p-value = centered district-cluster bootstrap; Holm-Bonferroni over the
  5-contrast family. Primary claim family = Precision@5 and nDCG@5 on R_prim.
- Reported per model separately and both with and without the 40 `pilot_union`
  scenarios. Per-season and per-district breakdowns are descriptive.
- R_full, R_all and R_prod are sensitivity and are not part of the claim family.

### 8.30.6 The 13 UNVERIFIED rows (descriptive only)

For each of the 13 rows in `eval/data/ground_truth/UNVERIFIED_FOR_REVIEW.csv` (5
crop_season_table season rows: Rice/Rabi, Maize/Rabi, Jowar/Rabi, Arhar/Rabi, plus
constraint rows), report whether the real district series supports or contradicts the
claim (for example, nonzero Rabi area vs zero). This is a report only; no ground-truth
file is edited.

### 8.30.7 Anti-tuning and contact points

- The reference and metric definitions above are fixed at this timestamp. No scoring
  code may be tuned to the reference once STEP 5 starts.
- If a reference cell is empty or short, the metric truncates rather than imputes; no
  data is fabricated.
- Outputs: `eval/scripts/real_eval.py` -> `eval/results/REAL_EVAL_REPORT.md` and
  figures under `eval/figures/real/`.