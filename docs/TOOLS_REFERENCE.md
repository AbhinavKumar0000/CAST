# AgroLLaMA: Tools Reference (Engineering & Mathematics)

**Audience:** engineers who must understand, reproduce, debug or extend the AgroLLaMA
tools *at the algorithmic level*. Every formula, threshold, map and constant used by the
six tools is written out here.

**Scope:** the six tools exposed by the MCP server (`mcp_server/`). How the tools are
*called by the LLM* and how the *evaluation* drives them is a separate document
(`EVAL_HARNESS_AND_SCENARIOS.md`); the meaning of the result figures is in
`FIGURES_EXPLAINED.md`.

**Source of truth:** the numbers below are copied from the code, not from prose. Where a
value is a design decision (a weight, a threshold), it is marked *(constant)*; where it is
an external data contract (an API field), it is marked *(API)*.

---

## 0. The tool contract and shared conventions

### 0.1 What a "tool" is here

Each tool is an ordinary Python module under `mcp_server/` that exposes a single entry
point `run(...)` returning a **plain `dict`**. In `mcp_server/server.py` every module is
wrapped by a *thin* `@mcp.tool()` function whose **name, docstring and parameter signature
are the public contract** the LLM sees over MCP. The wrappers add no logic:

| MCP tool name | Wrapper line | Delegates to |
|---|---|---|
| `weather_tool` | `server.py:54` | `weather_tool.run(latitude, longitude)` |
| `climate_tool` | `server.py:60` | `climate_tool.run(latitude, longitude)` |
| `season_tool` | `server.py:66` | `season_tool.run(latitude, longitude)` |
| `risk_tool` | `server.py:72` | `risk_tool.run(latitude, longitude)` |
| `get_soil_by_coordinates` | `server.py:78` | `soil_tool.run(latitude, longitude)` |
| `crop_score` | `server.py:84` | `crop_score_tool.run(latitude=, longitude=)` |

Five of the six take exactly `(latitude, longitude)` in **EPSG:4326 decimal degrees**.
`crop_score` also accepts five *optional* evidence dicts (see §7). The FastMCP server's
own `instructions` string tells the model the intended call order: weather → climate →
season → risk → soil → crop_score.

### 0.2 Caching convention

Both network tools cache in an **in-process module-level dict** keyed on the coordinate
rounded to **0.1°**:

```python
def _cache_key(latitude, longitude):
    return (round(latitude, 0.1), round(longitude, 0.1))
```

0.1° ≈ 11 km, so nearby lookups share one entry. The cache stores `(timestamp, payload)`
and the payload is **deep-copied out** so a caller mutating the result cannot corrupt the
cache. This cache is per-process, per-worker; it is **not** shared across processes. The
evaluation harness clears these caches between scenarios (see the harness doc) because a
scenario's "current" weather must not leak into the next.

| Tool | Cache | TTL | Line |
|---|---|---|---|
| `weather_tool` | `_WEATHER_CACHE` | **1 hour** (`3600 s`) | `weather_tool.py:13` |
| `climate_tool` | `_CLIMATE_CACHE` | **7 days** (`604800 s`) | `climate_tool.py:15` |
| `season_tool` | none | n/a | n/a |
| `risk_tool` | none (relies on the shared HTTP client + upstream) | n/a | n/a |
| `soil_tool` | module-level GeoDataFrame + spatial index + soil dict (loaded once) | process lifetime | `soil_tool.py:27-31` |
| `crop_score_tool` | `_CROP_ROWS_CACHE` (the parsed CSV rows) | process lifetime | `crop_score_tool.py:18` |

### 0.3 The shared HTTP client (`mcp_server/open_meteo_client.py`)

All Open-Meteo access goes through one wrapper with:

- a shared `requests.Session` (connection reuse);
- **5 retry attempts** (`max_retries=5`, *constant*);
- **exponential backoff starting at 5 s, doubling** with jitter, then a typed
  `OpenMeteoError` on final failure;
- two configured clients: **`forecast_client`** (timeout **12 s**) and `archive_client`
  (timeout **20 s**).

The evaluation freezes/patches the `fetch` method of these two clients to serve cached
archive data (see harness doc); the tool code itself is never modified.

### 0.3a External API endpoints

| Tool | Open-Meteo endpoint | Access |
|---|---|---|
| `weather_tool` | `api.open-meteo.com/v1/forecast` | `forecast_client` |
| `risk_tool` | `forecast` (past+forecast) **and** `archive-api.open-meteo.com/v1/archive` | both clients |
| `climate_tool` | `archive-api.open-meteo.com/v1/archive` | `archive_client` |

---

## 1. `weather_tool`: short-horizon weather

*File:* `mcp_server/weather_tool.py`. *Question:* "What is the weather doing here over the
next ~week?"

### 1.1 Request

```
params = {
  latitude, longitude,
  current = temperature_2m, relative_humidity_2m, precipitation, weather_code,
  daily   = temperature_2m_max, temperature_2m_min, precipitation_sum,
            precipitation_probability_max, weather_code,
  timezone = "auto",
  forecast_days = 7,
  past_days    = 7,
}
```

So the daily arrays have **14 entries**: 7 past days `[0..6]`, then 7 forecast days
`[7..13]`.

### 1.2 Algorithm

1. If the cache has a fresh entry, return it (deep copy).
2. Otherwise fetch. On `OpenMeteoError`, return the null-shaped result **plus an `error`
   string** (the tool never raises outside).
3. If `len(array) == 14`, split `forecast = arr[7:14]`, `past = arr[:7]`; otherwise fall
   back to the last 7 / first 7 (defensive, for short responses).
4. **min/max temp** over the *forecast* window; ignore `None`.
5. **Forecast rainfall** = Σ forecast `precipitation_sum`; **past rainfall** = Σ past.
6. **Average temperature**, preference order:
   - the `current.temperature_2m` value, if present;
   - else `(valid_max_temps[0] + valid_min_temps[0]) / 2` if `current` is missing;
   - else `(min_temp + max_temp) / 2`;
   - else `None`.
7. **Rain probability** = mean of the forecast-window
   `precipitation_probability_max` (non-null), rounded to integer.

### 1.3 Output schema

| Key | Meaning |
|---|---|
| `tool` | `"weather"` |
| `avg_temp_c` | average temperature, 1 dp |
| `min_temp_c`, `max_temp_c` | forecast-window extremes, 1 dp |
| `total_rainfall_mm` | Σ next-7-day rainfall, 1 dp |
| `rainfall_past_7d_mm` | Σ previous-7-day rainfall, 1 dp |
| `avg_humidity_percent` | current relative humidity, int (may be `None`) |
| `precipitation_probability_max_7d_percent` | mean rain probability, int |
| `data_period` | `"current_plus_7d_forecast"` |

---

## 2. `climate_tool`: long-term climate normals

*File:* `mcp_server/climate_tool.py`. *Question:* "What is *normal* here across the year?"

### 2.1 Request

```
start_date = "2014-01-01"   # NORMALS_START (constant)
end_date   = "2023-12-31"   # NORMALS_END   (constant)
daily      = temperature_2m_mean, precipitation_sum
```

Ten calendar years of daily archive. Cache TTL 7 days.

### 2.2 Algorithm

1. Drop `None` from temps and precipitation.
2. `avg_temp_normal_c` = mean of all daily mean temps.
3. `avg_rainfall_normal_mm` = **total precipitation ÷ number of months**, where
   `months = len(times)/30.44` (a year is taken as 12 × 30.44 days). This yields a
   **per-month average rainfall**.
4. Bucket daily values by **calendar month** (1–12).
5. `monthly_avg_temp_c[m]` = mean of that month's daily means (1 dp).
6. `monthly_avg_rainfall_mm[m]` = mean of that month's *daily* precipitation **× 30.44**
   (1 dp) → an estimate of the monthly total.
7. Population standard deviations (`statistics.stdev`, sample, requires ≥2 values):
   `temp_std_dev_c`, `precipitation_std_dev_mm`.

### 2.3 Output schema

| Key | Meaning |
|---|---|
| `tool` | `"climate_normals"` |
| `avg_rainfall_normal_mm` | average mm per month (2014–2023) |
| `avg_temp_normal_c` | 10-year mean temperature |
| `temp_std_dev_c`, `precipitation_std_dev_mm` | sample std devs |
| `monthly_avg_temp_c` | `{1..12: temp}` |
| `monthly_avg_rainfall_mm` | `{1..12: mm/month}` |
| `data_period_years` | `"2014-2023"` |

> **Note for the scorer:** `crop_score_tool` reads `monthly_avg_rainfall_mm` (and, as a
> fallback, `avg_rainfall_normal_mm`) to build its seasonal rainfall estimate. The naming
> difference between `monthly_avg_rainfall_mm` (the key the tool emits) and
> `monthly_avg_rainfall_mm` read in `crop_score_tool._seasonal_rainfall_estimate` is
> intentional, see §7.4.

---

## 3. `season_tool`: the cropping season

*File:* `mcp_server/season_tool.py`. *Question:* "Which cropping season are we in?"

### 2.x (pure calendar)

The entire tool is a fixed dictionary and the current month in India Standard Time:

```python
MONTH_TO_SEASON = {
  1: Rabi, 2: Rabi, 3: Rabi,
  4: Zaid, 5: Zaid,
  6: Kharif, 7: Kharif, 8: Kharif, 9: Kharif, 10: Kharif,
  11: Rabi, 12: Rabi,
}
```

`now = datetime.now(pytz.timezone("Asia/Kolkata"))`, `current_month = now.month`, and
`current_season = MONTH_TO_SEASON[current_month]`.

| Month(s) | Season |
|---|---|
| Jun–Oct (6–10) | **Kharif** |
| Nov–Mar (11,12,1,2,3) | **Rabi** |
| Apr–May (4–5) | **Zaid** |

Output: `{"tool": "season", "current_month": m, "current_season": s}`. No network, no
cache. **This exact map is imported by the evaluation** (`eval/scenarios.py` and
`eval/time_anchored.py` import `MONTH_TO_SEASON`), so the season the tool reports and the
season a scenario is scored against can never diverge.

---

## 3b. Risk semantics used everywhere else

Two thresholds are re-used as the "stress" definitions in the evaluation and in the
scorer's risk channel. They are derived from this tool's outputs:

* **drought flag**, `drought_z_score_30d ≤ −1.5` (moderate-or-worse SPI-1).
* **flood flag**, `flood_probability ≥ 0.40`.

---

## 4. `risk_tool`: drought, heatwave and flood

*File:* `mcp_server/risk_tool.py`. *Question:* "How risky is it here right now?"

### 4.1 Two data windows

* **Forecast** request: `past_days=30, forecast_days=7`, fields `temperature_2m_max/min`,
  `precipitation_sum`, `precipitation_probability_max` → 37 days total (`[0..29]` past,
  `[30..36]` forecast). If the response is short, `n_past = min(30, max(0, n_total − 7))`.
* **Archive** request: `2019-01-01 → 2023-12-31`, field `precipitation_sum`, the
  reference climatology for the drought index **only**.

Windowing code (`risk_tool.py:270-279`):
- `precip_30d = precipitation[:n_past]`
- `precip_7d  = precipitation[n_past : n_past+7]` (fallback: last 7, else all)
- `max_temps_7d = max_temps[n_past : n_past+7]` (same fallbacks)
- `min_temps_7d = min_temps[n_past : n_past+7]` (may be `None`)

### 4.2 Drought: SPI-1 (the mathematically involved part)

The tool builds a 1-month **Standardised Precipitation Index** from a fitted gamma
distribution and converts it to a probability. Step by step:

1. **Monthly climatology.** From the 2019–2023 archive, sum daily precipitation into
   monthly totals `(year, month) → total`, then group by **calendar month**:
   `monthly_totals[month] = [totals across the 5 years]`. This is a list of 5 values per
   calendar month.
2. **Reference month.** `_reference_month` reads the calendar month of the day at index
   `n_past − 1` (i.e. the last *past* day, the scenario "today"). The observed 30-day
   total is compared against that calendar month's distribution.
3. If fewer than 2 historical values exist → SPI `0.0` with no climatology (degenerate).
4. **Zero handling.** `zero_probability = (#monthly totals ≤ 0) / N`. Only strictly
   positive monthly totals are fed to the gamma fit.
5. **Gamma fit.** If there is enough variability (≥2 distinct positive values):
   ```python
   shape, loc, scale = gamma.fit(positive_values, floc=0)   # loc pinned to 0
   gamma_cdf = gamma.cdf(max(actual_30d_mm, 0.0), shape, loc=0, scale=scale)
   cdf = zero_probability + (1 - zero_probability) * gamma_cdf
   ```
   If the fit fails (too few distinct values) → **rank fallback**:
   `cdf = (#historical ≤ actual) / (N + 1)`.
6. **Probabilistic transform.** Clip `cdf` into `[1e-6, 1−1e-6]`, then
   ```python
   spi = norm.ppf(cdf)      # standard normal quantile → SPI value
   ```
7. **SPI → drought probability** *(constant table)* (`risk_tool.py:20-24`):

   | SPI condition | Drought probability |
   |---|---|
   | `spi < −2.0` | 0.70 |
   | `−2.0 ≤ spi < −1.5` | 0.55 |
   | `−1.5 ≤ spi < −1.0` | 0.22 |
   | `spi ≥ −1.0` | 0.08 |

8. **SPI → severity**: severe `< −2.0`, moderate `< −1.5`, mild `< −1.0`, else normal.

The tool also echoes the fitted climatology: `drought_climatology_30d_mm` (mean of the
historical monthly totals) and `drought_climatology_std_mm` (their sample std).

### 4.3 Heatwave

Inputs: the 7-day forecast `temperature_2m_max`. Algorithm:

* `absolute_max` = max of the 7 daily maxima.
* `max_consecutive_35` = longest run of consecutive days with `tmax ≥ 35`.
* `consecutive_38` = count of days with `tmax ≥ 38` (not necessarily consecutive).

Scoring *(constant)*:

| Condition | Probability | Severity |
|---|---|---|
| `absolute_max ≥ 40` **or** `consecutive_38 ≥ 2` **or** `max_consecutive_35 ≥ 5` | 0.52 | high |
| `consecutive_38 ≥ 1` **or** `max_consecutive_35 ≥ 3` | 0.35 | moderate |
| `max_consecutive_35 ≥ 2` **or** any day `≥ 35` | 0.18 | low |
| otherwise | 0.08 | none |

### 4.4 Flood

Inputs: 7-day forecast precipitation and the 30-day past precipitation.

* `total_7d = Σ precip_7d`, `total_30d = Σ precip_30d`, `max_1day = max(precip_7d)`.
* **Base probability from 7-day total** *(constant)*:

  | 7-day total | base probability |
  |---|---|
  | ≥ 200 mm | 0.50 |
  | ≥ 150 mm | 0.38 |
  | ≥ 100 mm | 0.28 |
  | ≥ 50 mm | 0.15 |
  | ≥ 20 mm | 0.08 |
  | else | 0.05 |

* **Single-day intensity increments** *(constant)*: `max_1day ≥ 80 → +0.35` (severity
  high); `≥ 50 → +0.22` (moderate); `≥ 30 → +0.12`; capped at `0.65`.
* **Antecedent wetness**: if `total_30d > 100` **and** `total_7d > 30` → `+0.12`,
  capped at `0.70`.
* **Final severity**: `prob ≥ 0.40` → high; `≥ 0.15` → moderate; else low.

### 4.5 Output schema

| Key | Meaning |
|---|---|
| `tool` | `"risk_analysis"` |
| `drought_probability` / `drought_severity` | from SPI-1 |
| `drought_z_score_30d` | the SPI value itself |
| `drought_climatology_30d_mm`, `drought_climatology_std_mm` | fitted reference mean/std |
| `heatwave_probability` / `heatwave_severity` | from §4.3 |
| `flood_probability` / `flood_severity` | from §4.4 |
| `precipitation_30d_mm` | observed 30-day total |
| `precipitation_forecast_7d_mm` | forecast 7-day total |
| `data_period` | `"30d_past_7d_forecast"` |

---

## 5. `get_soil_by_coordinates`: district & soil lookup

*File:* `mcp_server/soil_tool.py`. *Question:* "Which MP district is this, and what is its
dominant soil?" (The tool is deliberately **not** named `soil_tool` in the MCP contract, to
discourage the model from guessing soil.)

### 5.1 One-time initialisation (`initialize_soil_data`)

1. Read `data/processed/mp_districts.geojson` with GeoPandas. Force CRS to **EPSG:4326**
   (reproject if a CRS exists, else assume 4326). Districts are identified by `NAME_2`.
2. Build `gdf.sindex`, the **spatial index** for fast candidate lookup.
3. Read `data/processed/soil_fixed.json`; for each record build
   `normalize_district_name(district) → {district, dominant_soil, soil_characteristics,
   agricultural_suitability}`. `agricultural_suitability` falls back to a legacy
   `suitability` key.
4. Compute a **match summary** (`get_district_match_summary`): counts plus the lists of
   unmatched GeoJSON districts and unmatched soil records (after normalisation).
   Initialisation is guarded by a module-level error flag; failure returns an `error` dict
   from `run` rather than raising.

### 5.2 District-name normalisation

```python
def normalize_district_name(name):
    cleaned = re.sub(r"[^\w\s]", " ", name or "").lower()
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return KNOWN_DISTRICT_ALIASES.get(cleaned, cleaned)
```

Aliases *(constant)*: `east nimar → khandwa`, `west nimar → khargone`,
`narsimhapur → narsinghpur`. Normalisation makes boundary names and soil names agree even
where the two sources spell them differently.

### 5.3 Lookup (`run`)

1. Build `shapely.geometry.Point(longitude, latitude)` (note the **lon, lat** order) and
   reject invalid points.
2. `_candidate_rows`: query the spatial index for candidate polygons, then keep the ones
   whose geometry **`covers` the point** (robust for boundary points). Return empty if none.
3. If no polygon covers the point → `{"error": "Outside Madhya Pradesh"}`.
4. Read the district's `NAME_2`, normalise it, and look it up in the soil table.
   - If the district *is* in MP but has **no soil record** → return the district name with
     empty soil fields and `"note": "District in MP but soil metadata not in database"`
     (missing metadata is reported, never silently defaulted).
   - Otherwise return the four soil fields.

### 5.4 Output schema

`{district, dominant_soil, soil_characteristics, agricultural_suitability}` on success, or
`{"error": ...}` on failure.

> **Coverage:** all **51 scenario districts** have soil matches. The only unmatched soil
> record is the orphan **"Niwari"** (a soil row with no polygon and no scenario).

---

## 6. The crop registry (`crop_log.csv`)

This CSV is the knowledge base shared by `crop_score_tool` and the C1a/C2 prompt builders.
**21 crops.** Columns: `sr. no., Crop, Agro-Climatic Zone, Soil Type, Rainfall,
Tempreture, humidity_range_percent, season_supported, risk_sensitivity, duration_days,
sowing_start_week, sowing_end_week, days_to_harvest, peak_water_week`.

| # | Crop | Season(s) | Rainfall (mm) | Temp (°C) | Sowing weeks | Days→harvest | Peak-water wk | Risk sensitivity |
|---|---|---|---|---|---|---|---|---|
| 1 | Soybean | Kharif | 800–1200 | 25–32 | 24–27 | 105 | 31 | Heat:High, Drought:Medium, Flood:Medium |
| 2 | Wheat | Rabi | 1200–1400 | 15–30 | 43–47 | 130 | 4 | Heat:High, Drought:Medium |
| 3 | Rice | Kharif | 1200–1600 | 25–35 | 24–28 | 125 | 34 | Drought:High, Flood:Low |
| 4 | Maize | Kharif | 800–1000 | 21–27 | 24–27 | 100 | 31 | Heat:High, Flood:Medium, Drought:Medium |
| 5 | Cotton | Kharif | 800–1000 | 21–43 | 22–26 | 190 | 33 | Drought:Medium, Flood:High |
| 6 | Jowar | Kharif | 800–1000 | 15–40 | 23–27 | 120 | 30 | Drought:Low |
| 7 | Gram | Rabi | 1200–1400 | 20–25 | 42–46 | 125 | 2 | Drought:Low |
| 8 | Sugarcane | **Annual** | 1200–1600 | 28–32 | 7–13 | 420 | 24 | Drought:High |
| 9 | Mustard | Rabi | 800–1000 | 18–25 | 41–45 | 125 | 1 | Frost:High |
| 10 | Groundnut | Kharif | 800–1000 | 25–35 | 24–28 | 110 | 31 | Drought:Medium |
| 11 | Moong | Kharif/**Zaid** | 800–1200 | 25–35 | 24\|8 – 27\|13 | 70 | 29\|14 | n/a |
| 12 | Urad | Kharif | 800–1000 | 25–35 | 24–28 | 80 | 30 | n/a |
| 13 | Lentil | Rabi | 1000–1400 | 18–30 | 42–46 | 125 | 2 | Drought:Medium |
| 14 | Barley | Rabi | 800–1400 | 12–32 | 43–47 | 130 | 3 | Drought:Low |
| 15 | Bajra | Kharif | 800–1000 | 15–40 | 23–27 | 100 | 29 | Drought:Low |
| 16 | Sesame (Til) | Kharif | 800–1400 | 20–35 | 24–28 | 90 | 29 | Waterlogging:High, Hail:High |
| 17 | Sunflower | Rabi/Kharif | 1200–1600 | 20–30 | 42\|24 – 46\|28 | 100 | 2\|31 | n/a |
| 18 | Arhar (Tur) | Kharif | 1200–1400 | 20–40 | 24–28 | 165 | 33 | Drought:Low |
| 19 | Pea | Rabi | 1000–1400 | 15–25 | 42–45 | 105 | 1 | n/a |
| 20 | Kodo-Kutki | Kharif | 1200–1600 | 26–29 | 24–27 | 110 | 30 | Drought:Low |
| 21 | Watermelon | **Zaid** | 500–700 | 24–32 | 7–11 | 90 | 14 | Flood:High, Heat:Medium |

Notes:
* Multi-season crops store slash-separated values; multi-window crops store `a|b`
  vertical bars (e.g. Moong sowing weeks `24|8`, i.e. Kharif window 24–27 and Zaid window
  8–13; peak-water `29|14`).
* These exact 21 names are the canonical registry used for alias normalisation in the
  evaluation (`eval/llm/prompts.py:CANONICAL_CROPS`).

---

## 7. `crop_score`: the deterministic ranker

*File:* `mcp_server/crop_score_tool.py`. *Question:* "Given all the evidence, which crops
rank best right now?" This is the tool that turns the other five tools' numbers into a
ranking, and it is the **only** place an LLM could otherwise "reason"; here it is pure
arithmetic.

### 7.1 Inputs & evidence assembly

`run(latitude=None, longitude=None, weather=..., climate=..., soil=..., risk=..., season=...)`.

* If called with a full evidence bundle (as the evaluator does), no network is touched.
* If any of the five evidence keys is missing, `_build_evidence` calls the corresponding
  tool for the coordinates (so a bare `crop_score(lat, lon)` fetches everything itself).
* Raises `ValueError` if neither a full bundle nor coordinates are supplied.

### 7.2 The reference clock

```python
now = datetime.now(IST)
current_week  = now.isocalendar().week          # ISO week 1..53
current_month = season.current_month or now.month
current_season = season.current_season or "Unknown"
dominant_soil  = soil.dominant_soil
```

The evaluator pins `datetime` here (and in `season_tool`) to the scenario date, so
`current_week` is scenario-scoped.

### 7.3 Parsing helpers

* `_parse_numeric_range("800-1200")` → `(800.0, 1200.0)`; a single number → `(x, x)`;
  empty/invalid → `None`. Regex `\d+` extracts every integer in the string.
* `_split_seasons("Kharif/Zaid")` → `["Kharif", "Zaid"]`; empty → `["Annual"]`.
* `_parse_week_tokens("24|8")` → `[24, 8]`.
* `_parse_sowing_windows(row)` pairs seasons with start/end week lists when the lengths
  match, else broadcasts the first window across all seasons.

### 7.4 The five scoring channels

Every channel returns a value in `[0, 1]`. The crop's total is their fixed weighted sum
(§7.5). The weights are *(constant)*.

Let *R = rainfall_requirement*, *T = temperature_requirement* (both `(lo, hi)`), and let
`band_score(x, (lo, hi))` be the shared helper:

```
if x is None or band is None:            return 0.5            # unknown → neutral
if lo <= x <= hi:                        return 1.0
span = max(hi - lo, 1.0)
d = (lo - x) if x < lo else (x - hi)
return round(max(0.0, 1.0 - d/span), 3)                         # linear decay outside band
```

**(a) `rainfall_match` (weight 0.20).**
Compute the scenario's **seasonal rainfall estimate** from the climate normals:
`_seasonal_rainfall_estimate(climate, season)`:

* Look up the season's months from `SEASON_MONTHS` (`Kharif [6..10]`, `Rabi [11,12,1,2,3]`,
  `Zaid [4,5]`).
* Sum `climate.monthly_avg_rainfall_mm` for those months (accepting int or str keys).
* If no monthly data, fall back to `avg_rainfall_normal_mm × (#months)`.
* For an `Annual` crop (no season months), use `avg_rainfall_normal_mm × 12`.

Then `rainfall_match = band_score(seasonal_rainfall, R)`.

> **Known limitation (Rabi).** Rabi rainfall normals are far below every crop's rainfall
> band, so `band_score` floors near 0 for **all** crops in Rabi, the rainfall channel
> carries no discrimination in Rabi. This is declared in PROTOCOL §8.14 and is a *scorer*
> limitation, not an LLM finding; no weights were changed. See `FIGURES_EXPLAINED.md`
> (Fig_N05).

* **`temperature_match`** = `band_score(current_temperature, T)`, where
  `current_temperature` prefers `weather.avg_temp_c`, then the climate month's mean temp,
  then `climate.avg_temp_normal_c`.
* **`soil_type_match`** = keyword-overlap between the crop's `Soil Type` text and the
  district's `dominant_soil`:

  ```
  crop_cats   = categories keyword-matched in crop soil text
  soil_cats   = categories keyword-matched in dominant soil text
  if either is empty:        return 0.5
  if overlap empty:          return 0.1
  return round(min(1.0, 0.6 + 0.4 * |overlap| / |crop_cats|), 3)
  ```

  Categories *(constant)* map keywords to buckets: `black ← {black, cotton}`,
  `alluvial ← {alluvial}`, `red ← {red}`, `yellow ← {yellow}`, `loam ← {loam}`,
  `clay ← {clay}`, `sandy ← {sand, sandy}`, `laterite ← {laterite}`.

* **`season_alignment`** returns `(score, plantable_now)`:

  | Situation | score | plantable |
  |---|---|---|
  | Season is `Annual` and no window parsed | 0.60 | True |
  | ... window contains current week | 0.85 | True |
  | ... else | 0.25 | False |
  | Current season **not** supported by the crop | 0.00 | False |
  | Supported, but no window for this season | 0.75 | True |
  | Supported, current week **inside** window | 1.00 | True |
  | Supported, nearest window ≤ 2 weeks away | 0.65 | False |
  | Supported, nearest window > 2 weeks away | 0.35 | False |

  (`_week_distance` is 0 inside the window, else the min distance to either endpoint.)

* **`risk_penalty`**:

  ```
  peak_multiplier = 1.15 if |current_week − any peak_water_week| ≤ 2 else 1.0
  if crop has no risk_sensitivity text:
      penalty = (drought + flood + heatwave probabilities) / 3
      return round(max(0, 1 − penalty * 0.3 * peak_multiplier), 3)
  else, for each "Hazard: Level" part (split on comma):
      map hazard → probability field:  drought→drought_probability,
          flood/waterlogging→flood_probability, heat/heatwave→heatwave_probability
      weight = {high: 1.0, medium: 0.65, low: 0.35}
      total_penalty += probability * weight
  return round(max(0, 1 − total_penalty * peak_multiplier), 3)
  ```

  Unrecognised hazard names (e.g. `Frost`, `Hail`) contribute nothing.

### 7.5 Weighted total

```python
total_score = round(
      0.20 * rainfall_match
    + 0.15 * temperature_match
    + 0.20 * soil_type_match
    + 0.30 * season_alignment
    + 0.15 * risk_penalty,
    3,
)
```

**Season alignment carries the largest weight (0.30)**, the design intent is that
seasonally appropriate crops win. Ranking is `total_score` descending; the output returns
the **top 5**.

### 7.6 Output schema

```
{
  "crop": ...,                # canonical crop name
  "season_supported": ...,    # raw registry string
  "plantable_now": bool,      # from season_alignment
  "total_score": float,
  "scores": { rainfall_match, temperature_match, soil_type_match,
              season_alignment, risk_penalty },
  "sowing_window": { "start_week": ..., "end_week": ... }
}
```

plus the wrapper `{tool, current_week, current_season, ranked_crops (≤5)}` returned by
`run` (the per-crop list above is the item schema).

### 7.7 Emergent behaviour worth knowing

Because `soil_type_match`, `season_alignment` and much of `risk_penalty` depend on the
**district** (soil) and the **season** (month), scenarios in the same district and season
tend to receive very similar rankings. This is *why* the evaluation is clustered by
district and why the clustering correction matters (`FIGURES_EXPLAINED.md`, Fig_N03/N04).

---

## 8. Quick reference appendices

### 8.1 Season map

`Kharif {6,7,8,9,10}`, `Rabi {11,12,1,2,3}`, `Zaid {4,5}`.

### 8.2 Scorer weights

`rainfall 0.20 · temperature 0.15 · soil 0.20 · season 0.30 · risk 0.15`.

### 8.3 Risk thresholds

* SPI→drought prob: `−2.0→0.70, −1.5→0.55, −1.0→0.22, else 0.08`.
* Heatwave: `40 °C | 2×38 | 5×35 → 0.52`; `1×38 | 3×35 → 0.35`; else 0.18/0.08.
* Flood: 7-day base `200/150/100/50/20 mm → 0.50/0.38/0.28/0.15/0.08`; 1-day
  `80/50/30 mm → +0.35/+0.22/+0.12`; wet antecedent `+0.12`.
* Evaluation stress flags: drought `z ≤ −1.5`, flood `prob ≥ 0.40`.

### 8.4 External data window constants

* `weather_tool`: 7 past + 7 forecast days.
* `climate_tool`: `2014-01-01 → 2023-12-31`.
* `risk_tool`: forecast `past_days=30, forecast_days=7`; SPI archive `2019–2023`.

### 8.5 HTTP client

`requests.Session`, **5 retries**, exponential backoff from 5 s (doubling, jittered);
forecast timeout 12 s, archive timeout 20 s; typed `OpenMeteoError` on final failure.

---

*See also:* `SYSTEM_GUIDE.md` (how the tools are served over MCP and wired into the
FastAPI + Gemini orchestrator), `EVAL_HARNESS_AND_SCENARIOS.md` (how the tools are called
during the study), `FIGURES_EXPLAINED.md` (the result figures).
