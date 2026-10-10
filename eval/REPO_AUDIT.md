# REPO_AUDIT.md — AgroLLaMA MCP repo vs. paper claims

Audit of `C:\Codes\mcp_for_farmers` (git HEAD `5e55090`, "updated readme"; prior commit
`db4d96b` "refactor: migrate AgroLLaMA tools to standards-compliant MCP server").
Produced for the paper *"Domain-Adaptive LLM with Model Context Protocol (MCP) for
Intelligent Decision Support in Precision Agriculture"*.

Every statement below is grounded in the files listed. Where the paper is said to
claim something, that is taken from the task description (the paper itself is not in
this repo); verify wording against the manuscript.

---

## 1. What the repo actually is

- A **FastMCP (streamable-http) server** exposing **six tools** in `mcp_server/server.py`:
  `weather_tool`, `climate_tool`, `season_tool`, `risk_tool`,
  `get_soil_by_coordinates`, `crop_score`.
- A **FastAPI orchestrator** (`app/main.py`, `app/orchestrator.py`,
  `app/llm/gemini_client.py`) that connects a Gemini model to the MCP server and runs a
  function-calling loop, plus a small static web UI (`app/static/`).
- Branding in code/README: **"AgroLLaMA"** (MCP server name, FastAPI title).

## 2. LLM / model actually used

| Item | Actual value | Source |
|---|---|---|
| Model | **`gemini-2.0-flash`** — hard-coded | `app/llm/gemini_client.py:292` |
| SDK | `google-generativeai` (old SDK), pinned `>=0.8.0` | `requirements.txt`, `gemini_client.py:21` |
| System prompt | Tool-first policy, forbids soil fabrication, requires `crop_score` before final answer | `gemini_client.py:258-276` |
| Tool exposure | Live `list_tools()` from the MCP server at client init, converted to Gemini `FunctionDeclaration`s | `gemini_client.py:96-178` |
| Round limit | `max_rounds=15` | `gemini_client.py:310` |
| Seeding / temperature | **None set** (SDK default) | `gemini_client.py:345` |
| Tool-calling style | Sequential (README states Gemini "does not currently emit multiple function calls in one turn") | `README.md:649` |

**API-key status (blocking):** the `GEMINI_API_KEY` in `.env` **fails authentication**
against `generativelanguage.googleapis.com` (both `v1` and `v1beta`): HTTP 401
`ACCESS_TOKEN_TYPE_UNSUPPORTED`. The value is 53 chars with prefix `AQ.A` (a normal
Google AI Studio Gemini key starts with `AIza`). All `ListModels` and `GenerateContent`
attempts via both the old and new SDKs returned 401. **No LLM run can proceed until a
working key is supplied.** (Key value never printed/logged.)

## 3. Real data sources (not what the paper says)

| Data | Actually used | Source |
|---|---|---|
| Short-range weather | **Open-Meteo forecast API** (`past_days=7, forecast_days=7`) | `weather_tool.py:40-51` |
| Climate normals | **Open-Meteo archive API**, **2014-01-01 … 2023-12-31** | `climate_tool.py:13-14,43-49` |
| Drought reference | **Open-Meteo archive API**, **2019 … 2023** monthly precip (SPI-1) | `risk_tool.py:54-72` |
| District boundaries | **GADM India level 2** → `data/processed/mp_districts.geojson` | `README.md:447,1093`; `soil_tool.py:18` |
| Soil metadata | `data/processed/soil_fixed.json`, each row carries `soil_data_source` URLs pointing to **CGWB NAQUIM reports** (`cgwb.gov.in`) | `soil_fixed.json`; `soil_tool.py:19` |
| Crop registry | `crop_log.csv` (hand-authored, 21 crops) | `crop_score_tool.py:17` |

**Not used anywhere in code:** NASA POWER, OpenWeatherMap, IMD station data, CHIRPS.
`IMD`/`CHIRPS` appear **only** as a future-work suggestion (`README.md:1065`).

## 4. Scoring model and thresholds (real values)

### 4.1 `crop_score` weights (deterministic)

`crop_score_tool.py:297-304` and `README.md:494-499`:

```
total_score = 0.20 * rainfall_match
            + 0.15 * temperature_match
            + 0.20 * soil_type_match
            + 0.30 * season_alignment
            + 0.15 * risk_penalty
```

There are **five** weights, not "W1–W3". They are **not** normalized against agronomic
ground truth; README itself calls the vector "a research parameter" (`README.md:518`).
Output is **top 6** crops (`crop_score_tool.py:329`), not top 5.

### 4.2 Risk thresholds

- SPI-1 → drought probability: `< -2.0 → 0.70`, `< -1.5 → 0.55`, `< -1.0 → 0.22`,
  else `0.08` (`risk_tool.py:20-24`). Severity labels severe/moderate/mild/normal.
- Heatwave (7-day): any day `≥40 °C`, or `≥2` days `≥38 °C`, or `≥5` consecutive `≥35 °C`
  → `0.52`; `≥1` day `≥38 °C` or `≥3` consecutive `≥35 °C` → `0.35`; `≥2` days `≥35 °C`
  → `0.18`; else `0.08` (`risk_tool.py:26-27,178-208`).
- Flood (7-day + 1-day + antecedent): base probability by 7-day total
  (`≥200→0.50`, `≥150→0.38`, `≥100→0.28`, `≥50→0.15`, `≥20→0.08`), plus 1-day
  `≥80→+0.35`, `≥50→+0.22`, `≥30→+0.12`, plus antecedent wetness (30d>100 & 7d>30)
  `+0.12`, capped at 0.70 (`risk_tool.py:28-29,211-244`).
- Risk-sensitivity weights in scoring: `high=1.0, medium=0.65, low=0.35`
  (`crop_score_tool.py:36-40`); peak-water proximity multiplier `1.15` within ±2 weeks
  (`crop_score_tool.py:204`).
- Soil match: `0.6 + 0.4·(overlap/|crop_cats|)` if any overlap, else `0.1`; `0.5` if
  either side uncategorisable (`crop_score_tool.py:161-169`).
- Season alignment: `1.0` inside sowing window, `0.65` within 2 weeks of edge,
  `0.35` farther; Annual without window `0.6` (`crop_score_tool.py:172-198`).
- Range scoring: `1.0` inside, linear decay by distance/span, `0.5` if missing
  (`crop_score_tool.py:69-79`).

### 4.3 Season map (`season_tool.py:11-24`)

Kharif = Jun–Oct, Rabi = Nov–Mar, Zaid = Apr–May. **Uses wall-clock `datetime.now(IST)`.**

## 5. Crop registry (`crop_log.csv`)

21 crops (README says 21 × 14 attributes; CSV has 14 columns):
Soybean, Wheat, Rice, Maize, Cotton, Jowar, Gram, Sugarcane, Mustard, Groundnut, Moong,
Urad, Lentil, Barley, Bajra, Sesame (Til), Sunflower, Arhar (Tur), Pea, Kodo-Kutki,
Watermelon.

- Seasons present: Kharif, Rabi, Zaid, Annual, and combos `Kharif/Zaid`, `Rabi/Kharif`.
- The `Agro-Climatic Zone` column holds **one zone per crop** (10 distinct zones). Zones
  are geographic in reality; assigning one zone to a crop is conceptually wrong and used
  nowhere in scoring.
- `risk_sensitivity` is **empty** for Moong, Sunflower, Pea, Urad (scoring falls back to
  the baseline branch `crop_score_tool.py:206-212`).
- **No alias table exists in the repo** for crop names (only 3 *district* aliases in
  `soil_tool.py:21-25`: `east nimar→khandwa`, `west nimar→khargone`,
  `narsimhapur→narsinghpur`).

## 6. Districts

- `mp_districts.geojson`: **51** polygons (GADM level 2 → MP).
- `soil_fixed.json`: **52** records; the extra is **Niwari** (no boundary polygon).
- All 51 GeoJSON names normalize to a soil record; only Niwari is unmatched the other way.
- **The paper's "55 districts" is inconsistent with the repo (51).** MP currently has
  55 official districts; GADM level-2 lags and misses newer/renamed ones.
- `soil_fixed.json` `soil_types` arrays are **empty** for the sampled records; only
  `dominant_soil` is populated → README's "60+ distinct soil types" (`README.md:59`) is
  **not supported by the data**.

## 7. Ground-truth / evaluation status

- **No evaluation harness, no ground truth, no metrics, no figures, no tests for metrics
  exist in the repo.**
- The paper's stated ground truth ("top 5 crops per region based on MP agriculture
  patterns") is **undefined and circular** (it appears to be the registry itself). Nothing
  in the repo corroborates independent district-season crop data.
- `scripts/test_mcp_tools.py` and `scripts/test_e2e_analyze.py` are **smoke tests only**
  (require network + live MCP server); `README.md:1046` confirms there is no unit suite.
- No `pytest` config; `pytest` and `python-docx`, `matplotlib`, `seaborn` are installed
  in the environment but **not** in `requirements.txt`.

## 8. Reproducibility / leakage caveats for any hindcast evaluation

1. **Tools are wall-clock, not as-of-date.** `season_tool`, `crop_score` (current ISO
   week), `weather_tool` and `risk_tool` (open-ended `past_days`/`forecast_days` relative
   to *now*) have **no date parameter**. A scenario dated 2024-06-15 cannot be replayed
   through the tools as-is. An eval-only wrapper must inject archive slices (allowed under
   the rules as a thin wrapper under `eval/`).
2. Open-Meteo archive (`archive-api.open-meteo.com`) is a reanalysis product; it is
   reproducible for historical dates but is **not** a true forecast. Evaluating "next 7
   days" from archive values is a **hindcast** (must be stated in the report).
3. `climate_tool` normals window (2014–2023) **overlaps** scenario dates (2024–2025 not
   included, so no direct leakage), but `risk_tool`'s SPI reference (2019–2023) is fixed
   and does not leak future scenario weather.
4. `crop_score` **self-fetches live** tool data when not handed an evidence bundle
   (`crop_score_tool.py:231-248`): calling it naively would pull *live* weather for a
   historical scenario → leakage. The eval wrapper must pre-populate the evidence bundle.
5. Weather/climate caches are keyed on `(round(lat,1), round(lon,1))` → 0.1° (~11 km)
   grid; distinct scenarios within the same cell share cached values.
6. The SPI-1 gamma fit uses only **5 historical monthly values** (2019–2023) per calendar
   month → unstable; falls back to empirical rank CDF often.

## 9. Discrepancy list (fix the paper)

| # | Paper / README claim | Reality in repo | Action |
|---|---|---|---|
| 1 | Data from NASA POWER | Not used anywhere | Remove or re-source |
| 2 | Data from OpenWeatherMap | Not used | Remove |
| 3 | Data from IMD | Not used (future work only) | Remove or move to future work |
| 4 | Model "AgroLLaMA" (as if a model) | AgroLLaMA is the **MCP server/system name**; the LLM is **Gemini 2.0 Flash** | Reword: system vs model |
| 5 | 55 districts | 51 polygons / 52 soil records | Correct count or explain |
| 6 | "60+ distinct soil types" | `soil_types` arrays empty; only dominant soil | Soften/remove |
| 7 | Weights "W1–W3" | Five weights `(0.20,0.15,0.20,0.30,0.15)` | Correct |
| 8 | Top-5 recommendations | `crop_score` returns top **6** | Correct or re-define |
| 9 | Ground truth = "top 5 crops per region" | Undefined; circular | Replace with independent GT (STEP 3) |
| 10 | Accuracy / risk-reduction numbers | **No measured results exist in repo** | Recompute (this effort) |
| 11 | "most profitable" / yield claims | No yield/price data in repo | Remove unless new data added |
| 12 | "domain-adaptive" (fine-tuned?) | No fine-tuning; off-the-shelf model (`README.md:580`) | Reword: tool-grounded, not fine-tuned |
| 13 | Explainability score / Agro-Climate score | Not in repo | Define or drop; label circular if derived from registry |
| 14 | Seasons model | Uniform state-wide month map; no district monsoon onset | Qualify |
| 15 | Latency numbers | Static estimates, not measured (`README.md:614`) | Re-measure or label as estimates |

## 10. Deliverables created by this audit

- `eval/scripts/probe_models.py`, `eval/scripts/probe_sdk.py` — key/model probes
  (network only; no quota beyond a failed auth attempt).
- This document.

**Open blocking question for the author:** a valid Gemini API key is required before the
LLM conditions (C0, C0b, C1, C2) can run. Everything else (C3, ablations, metrics,
figures, statistics) is free and can proceed without it.
