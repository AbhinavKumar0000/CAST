# DB_SCOPE - what the recommendation ranking depends on (db_v2 study, STEP 1)

Prepared 2026-10-16 06:23 UTC. Offline, no model calls. Purpose: identify the exact
data files and fields that can change the crop ranking, so that the db_v2 experiment
(update only the database) changes nothing else, and so that any change requiring a
code edit is declared out of scope before it is attempted.

## 1. The crop database

There is exactly ONE crop database file:

- `crop_log.csv` (repo root), 21 data rows + header, sha256
  `581852922f42490e6139fc021cc57da728e39e1fb84d3fad3f07f9cbc08ea304`.
  (Call this **db_v1**. db_v2 will be a separate file; db_v1 is never edited.)

The scorer reads ONLY this file:

- `mcp_server/crop_score_tool.py:17` `_CROP_LOG_PATH = _ROOT / "crop_log.csv"`
- `mcp_server/crop_score_tool.py:50-56` `_load_crop_rows()` (cached in `_CROP_ROWS_CACHE`).
- The deterministic C3 grid replica reads it the same way:
  `eval/scripts/run_deterministic_v2.py:30-31` (`CROP_ROWS`) -> `CROP_PARSED:174-185`.

No other file supplies the crop list. Adding crops therefore needs no code change; it
requires only a new `crop_log.csv` file (db_v2).

## 2. Fields that influence the ranking

Columns of `crop_log.csv`, and whether they affect the score:

| Column | Used by scorer? | Effect on ranking |
|---|---|---|
| `Crop` | yes | candidate name; also the tie-break key `sort(-score, crop)` (`crop_score_tool.py:328`, `run_deterministic_v2.py:214`) |
| `Rainfall` | yes | parsed to a numeric range -> `rainfall_match` (`_score_against_range`) |
| `Tempreture` (sic) | yes | parsed to a numeric range -> `temperature_match` |
| `Soil Type` | yes | free text; matched against `SOIL_KEYWORDS` -> `soil_type_match` |
| `season_supported` | yes | which seasons are allowed -> `season_alignment` (0.0 if current season absent) |
| `risk_sensitivity` | yes | `hazard:level` pairs mapped via `RISK_FIELD_ALIASES` x `RISK_SENSITIVITY_WEIGHTS` -> `risk_penalty` |
| `peak_water_week` | yes | week tokens -> `peak_multiplier` (1.15 near peak) inside `risk_penalty` |
| `sowing_start_week`, `sowing_end_week` | partial | used by the LIVE scorer `crop_score_tool.run()` (season_alignment), but NOT by the C3 deterministic grid - see note below |
| `duration_days`, `days_to_harvest` | output only | echoed in the returned payload; never affect the score |
| `Agro-Climatic Region`, `humidity` | no | never read by the scorer |

Weight vector (fixed, from `eval/config.yaml:137` `ablations.weights.repo`):
`rainfall 0.20, temperature 0.15, soil 0.20, season 0.30, risk 0.15`.

Note on sowing windows. The frozen C3 outputs used in this evaluation
(`eval/runs/archive_v2/deterministic/*.json`) are produced by
`run_deterministic_v2.score_crops()`, which reconstructs the row passed to
`_season_alignment_score` with `sowing_start_week=""` and `sowing_end_week=""`
(`run_deterministic_v2.py:201-205`). With empty week tokens `_parse_sowing_windows`
returns `[]`, so **sowing_start_week / sowing_end_week do not influence C3**. Only
`season_supported` matters there (given season -> 0.75 for a specific supported season,
0.6 for Annual, 0.0 if the current season is not supported). The live scorer
`crop_score_tool.run()` (which fed the LLM tool conditions C1a/C2a/C2b) DOES read the
two sowing-window fields, but those LLM conditions are not re-run here.

For the db_v2 study the C3 ranking therefore depends on these 7 fields only:
`Crop`, `Rainfall`, `Tempreture`, `Soil Type`, `season_supported`, `risk_sensitivity`,
`peak_water_week`.

## 3. Inputs held fixed (NOT part of the database)

The ranking also consumes per-scenario evidence, which is frozen in
`eval/runs/archive_v2/evidence/<sid>.json` and is NOT touched by db_v2:

- `weather.avg_temp_c` (Open-Meteo archive slice) -> temperature channel
- `climate.monthly_avg_rainfall_mm`, `climate.avg_rainfall_normal_mm` -> season rainfall estimate
- `climate.monthly_avg_temp_c`, `climate.avg_temp_normal_c` -> temperature fallback
- `soil.dominant_soil` (from `data/processed/mp_districts.geojson` + `data/processed/soil_fixed.json`) -> soil channel
- `risk.drought_probability`, `flood_probability`, `heatwave_probability` -> risk channel
- `season.current_season`, `season.current_month` -> season channel and rainfall/temperature month set
- time anchor: `current_week` = ISO week of the scenario `as_of_date` (`run_deterministic_v2.py:267`)

These come from `mcp_server/{weather,climate,soil,risk,season}_tool.py`. db_v2 does not
modify any of them.

## 4. Out of scope (would require code edits; not attempted)

These are the only kinds of database change that would need a scorer code change. They
are OUT OF SCOPE for the db_v2 study (PROTOCOL ss8.31) and will not be attempted:

- Introducing a crop whose `season_supported` uses a token absent from `SEASON_MONTHS`
  (`crop_score_tool.py:21-25`). New season names would change the seasonal rainfall
  mapping and are excluded. Allowed season tokens in db_v2: `Kharif`, `Rabi`, `Zaid`,
  `Annual`, and `/`-separated combinations of these.
- Adding a new soil-match keyword to `SOIL_KEYWORDS` or a new hazard name to
  `RISK_FIELD_ALIASES` (`crop_score_tool.py:26-47`). No new keys are added.
- Changing the weight vector or any constant.

Not out of scope (allowed, no code change required): a new crop whose `Soil Type` text
simply contains an existing keyword (e.g. "black", "alluvial"), or contains no keyword
at all (then `soil_type_match = 0.5`); and a new crop whose `risk_sensitivity` is empty
(risk falls back to the 3-hazard baseline average, `crop_score_tool.py:206-212`).

## 5. STEP 1 conclusion

Adding crops to a db_v2 copy of `crop_log.csv` needs NO scorer code change. STEP 1 does
NOT trigger a stop. The experiment can proceed to pre-registration (STEP 2) and to
building db_v2 by editing only the database.
