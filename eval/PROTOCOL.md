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