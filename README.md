# AgroLLaMA MCP Evaluation Framework

**Paper:** *Domain-Adaptive LLM with Model Context Protocol (MCP) for Intelligent Decision Support in Precision Agriculture* (crop recommendation, Madhya Pradesh, India)

---

## Project Vision

### The Problem

Crop advisory in rural India has historically depended on either generalised government bulletins or word-of-mouth agronomic knowledge. Neither is calibrated to a specific field's soil, the current week's weather, the active cropping season, or the live hazard environment. Farmers in Madhya Pradesh -- managing 60+ distinct soil types across 10 agro-climatic zones -- make sowing, input, and water-management decisions with essentially no access to location-specific, evidence-grounded reasoning.

Large language models offer fluent agricultural text but are unreliable without grounding: they hallucinate soil types, invent rainfall figures, and ignore the actual calendar.

### What AgroLLaMA Does

AgroLLaMA separates the problem into two parts:

1. **Deterministic evidence collection** -- six tools collect weather, climate normals, seasonal context, multi-hazard risk, geospatial soil intelligence, and a crop-suitability ranking from real data sources and algorithms.
2. **Grounded LLM synthesis** -- The LLM is constrained to call every tool before generating any recommendation, and is explicitly forbidden from fabricating soil or weather data.

The tools are exposed as a **standards-compliant MCP server**. This means any MCP client can use them independently, without going through the LLM orchestrator. The farmer-facing web UI and `/analyze` API are one consumer of those tools; Claude Desktop or a custom agent is another.

### Role of MCP

The Model Context Protocol provides a uniform JSON-Schema-described tool contract between the tool server and any reasoning client. AgroLLaMA uses MCP's `streamable-http` transport: tools are registered once in `mcp_server/server.py` and discoverable by any compliant client via `list_tools()`. Tool invocation, argument passing, and result return all follow the MCP wire format, decoupling the agricultural tools from any particular LLM provider.

---

## System Architecture

### Two-Process Design

```
Process 1 -- FastAPI (port 8000)
+------------------------------------------+
|  app/main.py         HTTP + lifespan      |
|  app/orchestrator.py Gemini loop bridge   |
|  app/llm/            MCP client + LLM     |
|  app/schemas/        Pydantic contracts   |
|  app/static/         Browser UI           |
+------------------+-----------------------+
                   | MCP streamable-http
                   | POST http://127.0.0.1:8001/mcp
                   v
Process 2 -- FastMCP server (port 8001)
+------------------------------------------+
|  mcp_server/server.py   6 @mcp.tool()    |
|  mcp_server/weather_tool.py              |
|  mcp_server/climate_tool.py              |
|  mcp_server/season_tool.py               |
|  mcp_server/risk_tool.py                 |
|  mcp_server/soil_tool.py                 |
|  mcp_server/crop_score_tool.py           |
|  mcp_server/open_meteo_client.py         |
+------------------------------------------+
         |               |            |
   Open-Meteo API    mp_districts   soil_fixed.json
   (forecast +       .geojson      crop_log.csv
    archive)
```

FastAPI auto-starts the MCP server as a subprocess on startup (configurable). Both processes terminate cleanly on Ctrl+C: CTRL_BREAK_EVENT on Windows, SIGTERM on POSIX, with a 6-second grace period before SIGKILL.

### Request Lifecycle

```
C (Browser / curl) -> F (FastAPI :8000) -> G (LLM)
                                    |
                                    | MCP call_tool
                                    v
                                M (FastMCP :8001/mcp) -> O (Open-Meteo APIs)
                                                                -> D (Local Data Assets)
```

### Evidence and Context Flow

```
Latitude/Longitude -> weather_tool (Open-Meteo forecast)
                -> climate_tool (2014-2023 normals)
                -> season_tool (IST calendar)
                -> risk_tool (SPI-1 + heuristics)
                -> soil_tool (GeoPandas R-tree)
                    |
                    v
             Evidence Bundle -> crop_score (Weighted fusion)
                    |
                    v
             crop_log.csv (21 crop priors) -> LLM Prompt
                    |
                    v
             LLM Synthesis -> Crop recommendation + evidence audit trail
```

---

## Repository Structure

```
├── README.md                 # This file
├── LICENSE                   # MIT License
├── CITATION.cff              # Citation metadata
├── DATA_LICENSES.md          # Data source licenses & redistribution status
├── requirements.txt          # Python dependencies (pinned)
├── environment.yml           # Conda environment (pinned)
├── .env.example              # Environment variable template
├── .gitignore                # Git ignore rules
├── Makefile                  # Reproducible pipeline targets
├── src/                      # System code (unchanged)
│   ├── app/                  # FastAPI application
│   ├── mcp_server/           # MCP server with 6 AgroLLaMA tools
│   └── ...
├── eval/                     # Evaluation framework
│   ├── scenarios/            # 10,000 scenarios (district, point, date)
│   ├── data/
│   │   ├── ground_truth/     # Crop season tables, hard constraints
│   │   └── real_data/        # DES/MoA&FW district cropping data
│   ├── scripts/              # Pipeline scripts (numbered by order)
│   ├── results/              # Registered outputs (frozen, never edited)
│   ├── reports/              # Analysis reports
│   └── protocol/             # PROTOCOL.md (frozen)
├── figures/                  # Publication-ready figures
│   ├── scripts/              # Figure generation scripts
│   ├── data/                 # Figure data CSVs
│   ├── out/                  # PDF + PNG outputs
│   └── captions.md           # Facts-only captions
├── docs/                     # Documentation
│   ├── HANDOVER.md           # Per-figure/table handover
│   ├── FIGURE_INDEX.csv      # Figure metadata index
│   ├── GLOSSARY.md           # Terminology
│   ├── ARCHITECTURE.md       # System architecture
│   └── diagrams/             # Architecture/workflow diagrams
├── tests/                    # Unit tests
└── archive/                  # Superseded files (with README)
```

---

## Tool Reference and Algorithms

### Overview

All six tools share the same MCP interface: `(latitude: float, longitude: float) -> dict`. They are registered in `mcp_server/server.py` as thin `@mcp.tool()` wrappers around implementation modules, keeping the MCP contract decoupled from the algorithm.

```
Coordinates (lat, lon) -> weather_tool
                      -> climate_tool
                      -> season_tool
                      -> risk_tool
                      -> soil_tool
                              |
                              v
                      crop_score -> Ranked crop shortlist + evidence bundle
```

### weather_tool -- Short-Horizon Meteorological Summary

**Source file:** `mcp_server/weather_tool.py`

**Purpose:** Produces a 7-day agronomic weather summary including current conditions and recent rainfall, used to assess immediate sowing and crop management viability.

**Data source:** Open-Meteo free forecast API (`api.open-meteo.com/v1/forecast`)

**Algorithm:**
1. Query with `forecast_days=7, past_days=7` to obtain a 14-element daily array.
2. Split at index 7: `[0:7]` is the trailing 7 past days, `[7:14]` is the 7-day forecast.
3. Compute `min_temp_c` and `max_temp_c` from the forecast window.
4. Derive `avg_temp_c` from the current-conditions reading; fall back to `(max_day0 + min_day0) / 2` if unavailable.
5. Sum forecast precipitation as `total_rainfall_mm`; sum past precipitation as `rainfall_past_7d_mm`.
6. Average `precipitation_probability_max` over the forecast window.

**Caching:** Process-local in-memory dict keyed by `(round(lat, 1), round(lon, 1))`. TTL = 3 600 seconds. `copy.deepcopy` on read prevents cache mutation.

**Output keys:** `tool`, `avg_temp_c`, `min_temp_c`, `max_temp_c`, `total_rainfall_mm`, `rainfall_past_7d_mm`, `avg_humidity_percent`, `precipitation_probability_max_7d_percent`, `data_period`

**Complexity:** O(14) local, one HTTP call, network-bound (~300-800 ms cold).

### climate_tool -- Long-Term Climatological Baseline

**Source file:** `mcp_server/climate_tool.py`

**Purpose:** Computes a 10-year climatological baseline (2014-2023) against which current conditions are contextualised. Enables "anomaly vs. normal" reasoning in the crop recommendation.

**Data source:** Open-Meteo archive API (`archive-api.open-meteo.com/v1/archive`)

**Algorithm:**
1. Fetch daily `temperature_2m_mean` and `precipitation_sum` for 2014-01-01 to 2023-12-31 (~3 653 records).
2. Compute overall `avg_temp_normal_c` and `temp_std_dev_c` via `statistics.mean` and `statistics.stdev`.
3. Estimate monthly average rainfall as `mean(daily_precip_for_month) * 30.44` -- a first-order approximation of monthly totals from daily means.
4. Group daily observations by calendar month (1-12); compute `monthly_avg_temp_c` and `monthly_avg_rainfall_mm`.
5. Emit `precipitation_std_dev_mm` for inter-annual variability context.

**Caching:** 7-day TTL in-memory dict (climate normals change slowly; identical to weather cache pattern).

**Output keys:** `tool`, `avg_rainfall_normal_mm`, `avg_temp_normal_c`, `temp_std_dev_c`, `precipitation_std_dev_mm`, `monthly_avg_temp_c`, `monthly_avg_rainfall_mm`, `data_period_years`

**Complexity:** O(N) where N = 3 653 archive days. One HTTP call, network-bound (~1-3 s cold due to archive response size).

**Known limitation:** Monthly precipitation is estimated as `mean_daily * 30.44` rather than computing true calendar-month totals. This introduces small errors for months with significant daily variance.

### season_tool -- Agricultural Calendar Prior

**Source file:** `mcp_server/season_tool.py`

**Purpose:** Encodes the current national crop season as a symbolic prior for both the LLM and the `crop_score` tool. Provides IST-correct month and season name.

**Algorithm:** O(1) dict lookup from `MONTH_TO_SEASON`:
```
Kharif  Jun-Oct   (monsoon; major sowing season)
Rabi    Nov-Mar   (winter; wheat, gram, mustard)
Zaid    Apr-May   (summer; short-duration crops)
```

**Implementation note:** Uses `pytz.timezone("Asia/Kolkata")` to ensure IST correctness regardless of server timezone. The previous UTC-based implementation was corrected in the refactor.

**Output keys:** `tool`, `current_month`, `current_season`

**Known limitation:** Applies a uniform state-wide calendar. District-level monsoon onset variability (e.g., Bundelkhand vs. Nimar) is not modelled. Season boundaries could be refined using rainfall phase detection from climate data.

### risk_tool -- Multi-Hazard Agricultural Risk Assessment

**Source file:** `mcp_server/risk_tool.py`

**Purpose:** Quantifies three agricultural hazards -- drought, heatwave, and flood -- from a combination of recent observations and historical climate distributions.

**Data sources:** Open-Meteo forecast API (30 past days + 7 forecast) and archive API (2019-2023 precipitation).

#### Drought: SPI-1 via Gamma Distribution Fit

The Standardised Precipitation Index at one-month timescale (McKee et al., 1993) is approximated as follows:

1. Aggregate observed 30-day precipitation total: `actual_30d_mm`.
2. Build monthly precipitation totals from 2019-2023 archive data, grouping by `(year, month)` pairs.
3. Extract the reference distribution for the current calendar month (5 historical values).
4. Fit a two-parameter gamma distribution (`scipy.stats.gamma.fit` with `floc=0`) to positive precipitation values, treating zero months as a discrete mass `p0`.
5. Compute the mixed CDF: `F(x) = p0 + (1 - p0) * Gamma_CDF(x)`.
6. Convert to SPI via the inverse standard normal: `SPI = norm.ppf(F(actual_30d_mm))`.
7. Fall back to empirical rank-based CDF if gamma fit fails (fewer than 2 distinct positive values).

SPI-to-drought-probability mapping:

| SPI | Severity | Probability |
|---|---|---|
| < -2.0 | Severe | 0.70 |
| < -1.5 | Moderate | 0.55 |
| < -1.0 | Mild | 0.22 |
| >= -1.0 | Normal | 0.08 |

#### Heatwave: Consecutive Threshold Scoring

Consecutive-day logic over the 7-day forecast:
- `>= 40 C` on any day, or >= 2 days at `>= 38 C`, or >= 5 consecutive days at `>= 35 C` -> probability 0.52 ("high")
- >= 1 day at `>= 38 C` or >= 3 consecutive days at `>= 35 C` -> 0.35 ("moderate")
- >= 2 days at `>= 35 C` -> 0.18 ("low")
- Otherwise -> 0.08 ("none")

#### Flood: Tiered Precipitation Accumulation

Combines three signals with additive probability increments capped at 0.70:

| Signal | Threshold | Base probability |
|---|---|---|
| 7-day forecast total | >= 200 mm | 0.50 |
| 7-day forecast total | >= 150 mm | 0.38 |
| 7-day forecast total | >= 100 mm | 0.28 |
| 7-day forecast total | >= 50 mm | 0.15 |
| 1-day maximum | >= 80 mm | +0.35 |
| 1-day maximum | >= 50 mm | +0.22 |
| Antecedent wetness | 30-day > 100 mm AND 7-day > 30 mm | +0.12 |

**Output keys:** `tool`, `drought_probability`, `flood_probability`, `heatwave_probability`, `drought_severity`, `drought_z_score_30d`, `drought_climatology_30d_mm`, `drought_climatology_std_mm`, `heatwave_severity`, `flood_severity`, `precipitation_30d_mm`, `precipitation_forecast_7d_mm`, `data_period`

**Complexity:** Two HTTP calls (forecast: O(37) days, archive: O(1825) days). Archive aggregation is O(N).

### soil_tool (get_soil_by_coordinates) -- Geospatial District Soil Retrieval

**Source file:** `mcp_server/soil_tool.py`

**Purpose:** Resolves a decimal-degree coordinate to a Madhya Pradesh administrative district and returns structured soil intelligence for that district.

**Data sources:**
- `data/processed/mp_districts.geojson` -- 51 district polygons derived from GADM India level 2, reprojected to EPSG:4326.
- `data/processed/soil_fixed.json` -- 52 district soil records with `dominant_soil`, `soil_characteristics`, and `agricultural_suitability`.

**Algorithm:**
1. **Cold-start initialisation** (once per process, guarded by a `None` sentinel):
   - Load GeoJSON into a `geopandas.GeoDataFrame` via `gpd.read_file`.
   - Ensure CRS is EPSG:4326.
   - Build a `gdf.sindex` (libspatialindex R-tree) for fast bounding-box pre-filtering.
   - Normalise and index soil records by canonical district name.

2. **Name normalisation** (`normalize_district_name`):
   - Strip non-word characters with regex.
   - Lowercase and collapse whitespace.
   - Apply a hardcoded alias table (`east nimar` -> `khandwa`, `west nimar` -> `khargone`, `narsimhapur` -> `narsinghpur`) to bridge historical and current naming conventions.

3. **Point-in-polygon lookup** (`_candidate_rows`):
   - Construct `shapely.geometry.Point(longitude, latitude)`.
   - Query the R-tree spatial index for candidate districts whose bounding box contains the point.
   - Apply exact `geometry.covers(point)` test (inclusive of boundary, unlike `contains`).

4. **Soil join:** Match the first polygon's `NAME_2` field (normalised) against the soil lookup dict.

**Output keys:** `district`, `dominant_soil`, `soil_characteristics`, `agricultural_suitability` (or `error` if outside MP).

**Complexity:** Cold start is I/O-bound (GeoPandas + 2 MB GeoJSON, ~8-12 s). Warm lookup: O(k) where k is the small set of candidates returned by the R-tree (typically 1-3 districts).

### crop_score -- Deterministic Evidence-Fusion Crop Ranking

**Source file:** `mcp_server/crop_score_tool.py`

**Purpose:** Ranks 21 MP crops from `crop_log.csv` using a deterministic weighted multi-criteria scoring model. Provides an auditable, reproducible shortlist before the LLM synthesises its recommendation.

**Evidence inputs:** All five upstream tools (self-fetching if not already in the evidence bundle).

**Scoring model:**
```
total_score = 0.20 * rainfall_match
            + 0.15 * temperature_match
            + 0.20 * soil_type_match
            + 0.30 * season_alignment
            + 0.15 * risk_penalty
```

**Dimension details:**

*Rainfall match (`_score_against_range`):* Compares the seasonal rainfall estimate from `climate_tool` against the crop's `[min, max]` rainfall range from `crop_log.csv`. Score = 1.0 inside the range; decays linearly with distance normalised by range span. Returns 0.5 for missing data.

*Temperature match:* Same range-scoring against `crop_log.csv` temperature bounds, using `weather_tool.avg_temp_c` with climate monthly-normal fallback.

*Soil type match (`_score_soil_type_match`):* Extracts categorical soil keywords (black, alluvial, red, yellow, loam, clay, sandy, laterite) from both the crop's expected soil and the retrieved dominant soil. Score = `0.6 + 0.4 * (overlap / crop_categories)` when any overlap exists; 0.1 if no overlap; 0.5 if either side is uncategorisable.

*Season alignment (`_season_alignment_score`):* Returns 1.0 if the current ISO week is within the crop's `sowing_start_week` to `sowing_end_week` window. Decays to 0.65 if within 2 weeks of the window edge, 0.35 if further. Annual crops are handled separately. Sets `plantable_now: bool`.

*Risk penalty (`_risk_penalty_score`):* Parses the crop's `risk_sensitivity` field (e.g., `"Heat: High, Drought: Medium"`) to extract hazard-level pairs. Multiplies each hazard's live probability by the sensitivity weight (`High=1.0, Medium=0.65, Low=0.35`) and the `peak_water_week` proximity multiplier (1.15 within 2 weeks of peak demand). Returns `max(0, 1 - total_penalty)`.

**Output:** Top 6 crops by `total_score`, each with full sub-score breakdown, `plantable_now` flag, `sowing_window`, and `days_to_harvest`.

**Complexity:** O(C * 5) where C = 21 crops and 5 is the number of scoring dimensions. Dominated by the upstream tool calls if the evidence bundle is not pre-populated.

---

## AI and ML Architecture

### LLM Orchestration

```
GeminiClient.__init__ -> list_tools() via MCP -> cache declarations
                    -> run_tool_calling_loop -> build user prompt
                    -> gemini.generate_content round 1
                    -> {function_calls?} -> yes -> for each fc: _run_async(call_tool)
                                                   -> FunctionResponse injection -> contents.append
                                                   -> back to generate_content
                              -> no -> _get_text_from_response -> final message
                              -> AnalyzeResponse (tool_order + tools_output + message)
```

The tool-calling loop is a bounded retry loop (`max_rounds=15`) over LLM `generate_content` calls. Each round inspects response candidates for `function_call` objects. When found, every requested tool is dispatched through MCP via `asyncio.run(_mcp_call_tool_async(...))`. The structured result is injected back as a `FunctionResponse` part. The loop terminates when the LLM emits only text parts.

### Schema Bridge: MCP to LLM

FastMCP auto-generates JSON Schema for `@mcp.tool()` parameters, including `title` fields and a top-level `"title": "weather_toolArguments"`. The LLM `FunctionDeclaration` API rejects both. The bridge function `_strip_gemini_unsupported` recursively removes `title`, `$schema`, and `default` from the raw MCP `inputSchema` before constructing `content_types.FunctionDeclaration` objects.

### Prompt Engineering

The system prompt enforces three hard constraints:

1. **Tool-first policy:** "Do not generate final output until all required tools are called." The LLM must call tools sequentially, preventing speculative text generation from untooled knowledge.
2. **Soil grounding:** "You are forbidden from guessing or fabricating soil type or crop suitability." If `get_soil_by_coordinates` returns an error (outside MP), the model must report it rather than substituting a prior.
3. **Structured synthesis:** After evidence is complete, "call `crop_score` to obtain a deterministic ranked shortlist before writing recommendations." This ensures the final text is anchored to the scored shortlist.

The user prompt adds three context layers:
- **Temporal grounding:** Today's IST date and current ISO week number, enabling sowing-window reasoning.
- **Crop knowledge injection:** All 21 rows from `crop_log.csv` are serialised into the prompt as structured text.
- **Output format constraint:** "Provide a concise summary plus a list of 3-6 recommended crops with their suitability reasons, plantability timing, and risk warnings."

### What the System Does NOT Use

| Component | Status | Note |
|---|---|---|
| Vector database / embeddings | No | Retrieval is geospatial and tabular |
| Fine-tuning | No | Off-the-shelf LLM |
| Long-term memory | No | Each request is stateless |
| Multimodal inputs | No | Coordinates only (API); map UI is visual coordinate selection |
| Multi-agent decomposition | No | Single controller LLM |
| Learned crop ranking | No | Deterministic weighted scoring |

---

## Research Contributions

### C1: Tool-Grounded Agronomic Reasoning via MCP
AgroLLaMA demonstrates that a standards-compliant MCP server architecture can serve as the evidence layer for an LLM agronomic advisor. The protocol separation means the same six tools are independently usable by Claude Desktop, Cursor, or any future MCP client -- the agricultural intelligence is not locked to one reasoning model.

### C2: SPI-1 Drought Estimation as a Live Inference Tool
The `risk_tool` implements a real-time approximation of the WMO-standard Standardised Precipitation Index at the one-month timescale. Fitting a gamma distribution to 2019-2023 monthly precipitation totals at query time, and mapping the result through the standard normal inverse, produces a calibrated drought probability signal without any pre-computed raster or trained model.

### C3: Geospatial Grounding via R-Tree Point-in-Polygon Retrieval
The `soil_tool` demonstrates that a GeoPandas R-tree spatial index over 51 district polygons provides sub-millisecond warm-path lookup, making geospatial retrieval viable as a synchronous MCP tool. The district-name normalisation pipeline (regex + alias table) and the `geometry.covers()` semantics (boundary-inclusive) are reproducible engineering choices that reduce data mismatch without a full fuzzy-matching stack.

### C4: Deterministic Crop Scoring as an Auditable LLM Pre-Filter
The `crop_score` tool provides a reproducible, inspectable ranking before the LLM writes its recommendation. The evidence trail (sub-scores for rainfall, temperature, soil, season, risk) is included in the API response, enabling human auditors and researchers to verify why a crop was recommended without reading the model's text.

### C5: Evidence-Bundle Architecture for Agricultural AI
The full pipeline -- five deterministic evidence tools followed by a deterministic crop ranker followed by an LLM synthesis -- decouples evidence collection (deterministic, auditable, testable) from explanation generation (stochastic, fluent, context-sensitive). This separation is the central architectural claim of the system.

---

## Evaluation Framework

This repository contains the complete evaluation framework for testing whether giving a general-purpose LLM access to six AgroLLaMA MCP tools improves the quality, safety, specificity, reliability, consistency, and cost of district-level crop recommendations versus an LLM alone -- and how it compares to the deterministic no-LLM system.

The evaluation follows a **frozen protocol** (PROTOCOL.md) registered before any results were computed, with all changes timestamped and auditable.

### Evaluation Conditions

| ID | Label | Tools | Description |
|---|---|---|---|
| C0 | LLM-only | None | Plain prompt (district, coords, date) |
| C0b | LLM-only strong | None | Explicitly told to reason about soil, season, rainfall, temperature, risks |
| C1a | Fair stuffing | Stuffed | Raw tool outputs + candidate crop requirements pasted into prompt |
| C2a | LLM + MCP (proposed) | MCP | LLM calls all 6 tools via function calling |
| C2b | LLM + MCP (no scorer) | MCP (5) | LLM calls 5 tools (excludes crop_score) |
| C3 | No-LLM deterministic | - | Weighted scorer only, time-anchored, run on all 10,000 scenarios |
| C3t | Instrument-corrected C3 | - | Identical pipeline but passes real sowing windows to season alignment |

### Key Results (Summary)

| Metric | C3 (deterministic) | C2a (MCP tools) | C2b (5 tools) | C0b (strong LLM) |
|--------|-------------------|-----------------|---------------|------------------|
| Season Validity (strict) | 0.836 | 0.803 | 0.772 | 0.646 |
| Hard Violation (strict) | 0.115 | 0.161 | 0.151 | 0.292 |
| Real-data P@5 (R_prim) | 0.504 | 0.504 | **0.622** | 0.483 |

**Primary finding:** C2a significantly improves season validity and reduces hard violations vs C0b/C1a (Holm-corrected p < 0.001). C2b (no crop_score tool) matches C2a on violations but not validity. Nemotron C2b achieves highest real-data Precision@5.

### Instrument Correction (PROTOCOL 8.35)

The registered deterministic pipeline (`run_deterministic_v2.py::score_crops` full_repo) drops real sowing windows before calling `_season_alignment_score`. Every analysis that used the registered C3 top-5 as a stand-in for the MCP `crop_score` tool scored an instrument that does not reproduce the tool.

**C3t** = identical pipeline/weights/time anchor/crop list, the ONLY difference being the crop row's real `sowing_start_week`/`sowing_end_week` are passed into `_season_alignment_score`.

**Verification:** `use_windows=False` replica reproduces the registered C3: 40/40 on base set. `use_windows=True` (C3t) reproduces the stored MCP `crop_score` tool output: 40/40 with component scores 102/102. Full census over 10,000 archive bundles: C3t == stored bundle crop_score: 10,000/10,000.

**Key changes (C3 vs C3t):**
- Season Validity (strict, 10k): 0.8359 -> 0.7900
- Hard Violation (strict, 10k): 0.1146 -> 0.1615
- Real-data P@5 (R_prim, n=500): 0.5035 -> 0.4833

---

## Installation

### Prerequisites

- Python 3.10 or newer
- API keys for LLM providers (NVIDIA NIM, Google Gemini, Kilo Gateway)
- GeoPandas and its compiled GDAL/GEOS/PROJ dependencies

### Local Environment

```bash
git clone <repository-url>
cd "MCP for Farmers"

python -m venv .venv
```

Activate:
```bash
# Linux / macOS
source .venv/bin/activate

# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

Install dependencies:
```bash
pip install -r requirements.txt
```

**GeoPandas on Windows** -- if `pip install geopandas` fails due to GDAL binary requirements, install via Conda first:
```bash
conda install -c conda-forge geopandas
pip install -r requirements.txt
```

### Environment Variables

Copy `.env.example` to `.env` and fill in your API keys:
```bash
cp .env.example .env
# Edit .env with your NVIDIA_API_KEY_1..4, GEMINI_API_KEY, KILO_API_KEY
```

---

## Reproducing the Evaluation

All results are **reproducible from stored outputs** -- no API calls needed.

```bash
# Full offline pipeline (uses stored LLM outputs, deterministic recompute)
make all

# Individual targets
make scenarios          # Generate 10,000 scenarios (already done)
make deterministic      # C3 + ablations on 10k (already done)
make eval               # Run LLM conditions (requires API keys)
make figures            # Generate all figures from result files
make test               # Run unit tests
```

**Key principle:** The pipeline uses `eval/runs/` caches and `eval/results/` registered outputs. Re-running `make all` in a fresh environment reproduces every number exactly.

---

## Protocol & Integrity

- **PROTOCOL.md** (eval/protocol/PROTOCOL.md): Frozen evaluation protocol v2.0 (2026-10-13)
- All changes after results are registered with timestamps
- No prompt, weight, threshold, or scenario filtering tuned after inspecting results
- Baselines that win are reported as wins

---

## Data Sources

| Source | Description | License | Access |
|--------|-------------|---------|--------|
| DES/MoA&FW UPAG | District×season×year crop area/production | ODC-By | India Data Portal |
| GADM v4.1 | Administrative boundaries (MP) | CC-BY-4.0 | gadm.org |
| ICAR-CRIDA DACP | District Agriculture Contingency Plans | Govt. of India | Public |
| Open-Meteo | Weather archive (hindcast) | CC-BY-4.0 | open-meteo.com |

Full details in `DATA_LICENSES.md`.

---

## Citation

```bibtex
@article{agrollama2026,
  title={Domain-Adaptive LLM with Model Context Protocol (MCP) for Intelligent Decision Support in Precision Agriculture},
  author={...},
  journal={...},
  year={2026}
}
```

See `CITATION.cff` for complete metadata.

---

## License

MIT License -- see `LICENSE` for details. Data files retain their original licenses (see `DATA_LICENSES.md`).

---

## Contact

For questions about the evaluation framework, contact the authors.